import hashlib
import hmac
import json

import pytest
import respx
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.integrations.linear.webhook import app, router, GITHUB_API_URL


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


WEBHOOK_SECRET = "test-secret"
GITHUB_REPO = "org/repo"
GITHUB_TOKEN = "ghp_testtoken"


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("LINEAR_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("GITHUB_REPOSITORY", GITHUB_REPO)
    monkeypatch.setenv("GITHUB_TOKEN", GITHUB_TOKEN)
    monkeypatch.setenv("GITHUB_DEFAULT_BRANCH", "main")


@pytest.fixture
def client():
    return TestClient(_make_app(), raise_server_exceptions=False)


def _post_webhook(client, payload: dict, secret: str = WEBHOOK_SECRET) -> httpx.Response:
    body = json.dumps(payload).encode()
    sig = _sign(body, secret)
    return client.post(
        "/webhooks/linear",
        content=body,
        headers={"Content-Type": "application/json", "linear-signature": sig},
    )


class TestHealthEndpoint:
    def test_health_returns_200(self):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestExportedAppWebhookRoute:
    def test_exported_app_has_linear_webhook_route(self):
        client = TestClient(app, raise_server_exceptions=False)
        payload = {"type": "Issue", "action": "create", "data": {}}
        body = json.dumps(payload).encode()
        resp = client.post(
            "/webhooks/linear",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401


class TestSignatureValidation:
    def test_valid_signature_returns_200(self, client):
        payload = {"type": "Issue", "action": "create", "data": {"id": "i1", "title": "T"}}
        resp = _post_webhook(client, payload)
        assert resp.status_code == 200

    def test_invalid_signature_returns_401(self, client):
        payload = {"type": "Issue", "action": "create", "data": {}}
        body = json.dumps(payload).encode()
        resp = client.post(
            "/webhooks/linear",
            content=body,
            headers={"Content-Type": "application/json", "linear-signature": "sha256=badhash"},
        )
        assert resp.status_code == 401

    def test_missing_signature_returns_401(self, client):
        payload = {"type": "Issue", "action": "create", "data": {}}
        body = json.dumps(payload).encode()
        resp = client.post(
            "/webhooks/linear",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_no_secret_configured_skips_validation(self, client, monkeypatch):
        monkeypatch.setenv("LINEAR_WEBHOOK_SECRET", "")
        payload = {"type": "Issue", "action": "create", "data": {}}
        body = json.dumps(payload).encode()
        resp = client.post(
            "/webhooks/linear",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200


class TestStateChangeDispatch:
    @respx.mock
    def test_trigger_status_fires_repository_dispatch(self, client):
        """Default trigger status ("In Progress") fires a repository_dispatch event."""
        dispatch_url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/dispatches"
        respx.post(dispatch_url).mock(return_value=httpx.Response(204))

        payload = {
            "type": "Issue",
            "action": "update",
            "data": {
                "id": "issue-1",
                "title": "Build it",
                "state": {"id": "s2", "name": "In Progress"},
                "labels": {"nodes": []},
            },
        }
        resp = _post_webhook(client, payload)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @respx.mock
    def test_repository_dispatch_payload_contains_issue_fields(self, client):
        """The repository_dispatch client_payload includes issue_id and issue_title."""
        dispatch_url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/dispatches"
        mock_route = respx.post(dispatch_url).mock(return_value=httpx.Response(204))

        payload = {
            "type": "Issue",
            "action": "update",
            "data": {
                "id": "issue-42",
                "title": "Implement feature X",
                "state": {"id": "s2", "name": "In Progress"},
                "labels": {"nodes": []},
            },
        }
        _post_webhook(client, payload)

        assert mock_route.called
        sent = json.loads(mock_route.calls[0].request.content)
        assert sent["event_type"] == "linear-issue-ready"
        assert sent["client_payload"]["issue_id"] == "issue-42"
        assert sent["client_payload"]["issue_title"] == "Implement feature X"
        assert sent["client_payload"]["trigger_status"] == "In Progress"

    @respx.mock
    def test_custom_trigger_status_fires_repository_dispatch(self, client, monkeypatch):
        """LINEAR_TRIGGER_STATUS env var overrides the default trigger status."""
        monkeypatch.setenv("LINEAR_TRIGGER_STATUS", "Ready for Agent")
        dispatch_url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/dispatches"
        respx.post(dispatch_url).mock(return_value=httpx.Response(204))

        payload = {
            "type": "Issue",
            "action": "update",
            "data": {
                "id": "issue-1",
                "title": "Build it",
                "state": {"id": "s3", "name": "Ready for Agent"},
                "labels": {"nodes": []},
            },
        }
        resp = _post_webhook(client, payload)
        assert resp.status_code == 200

    @respx.mock
    def test_default_status_does_not_fire_when_custom_status_set(self, client, monkeypatch):
        """When LINEAR_TRIGGER_STATUS is overridden, default "In Progress" no longer fires."""
        monkeypatch.setenv("LINEAR_TRIGGER_STATUS", "Ready for Agent")
        # No mock needed — respx raises if any unregistered URL is called
        payload = {
            "type": "Issue",
            "action": "update",
            "data": {
                "id": "issue-1",
                "title": "Build it",
                "state": {"id": "s2", "name": "In Progress"},
                "labels": {"nodes": []},
            },
        }
        resp = _post_webhook(client, payload)
        assert resp.status_code == 200

    @respx.mock
    def test_non_trigger_state_does_not_dispatch(self, client):
        """States that don't match the trigger status produce no dispatch."""
        payload = {
            "type": "Issue",
            "action": "update",
            "data": {
                "id": "issue-1",
                "title": "Build it",
                "state": {"id": "s1", "name": "Todo"},
                "labels": {"nodes": []},
            },
        }
        resp = _post_webhook(client, payload)
        assert resp.status_code == 200


class TestDogfoodLabelDispatch:
    @respx.mock
    def test_dogfood_label_added_dispatches_dogfood_workflow(self, client):
        dispatch_url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/actions/workflows/agentic-issue-to-pr.yml/dispatches"
        respx.post(dispatch_url).mock(return_value=httpx.Response(204))

        payload = {
            "type": "Issue",
            "action": "update",
            "data": {
                "id": "issue-2",
                "title": "Dogfood this",
                "state": {"id": "s1", "name": "Todo"},
                "labels": {"nodes": [{"id": "l1", "name": "dogfood"}]},
            },
            "updatedFrom": {"labelIds": []},
        }
        resp = _post_webhook(client, payload)
        assert resp.status_code == 200
