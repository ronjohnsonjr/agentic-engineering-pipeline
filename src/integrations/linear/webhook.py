import hashlib
import hmac
import logging
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()

GITHUB_API_URL = "https://api.github.com"

# Default trigger status — override with LINEAR_TRIGGER_STATUS env var.
# Set to "Ready for Agent" (or any Linear state name) to avoid firing on
# every "In Progress" transition.
DEFAULT_TRIGGER_STATUS = "In Progress"


def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


async def _dispatch_workflow(
    repo: str,
    workflow_id: str,
    ref: str,
    inputs: dict,
    github_token: str,
) -> None:
    url = f"{GITHUB_API_URL}/repos/{repo}/actions/workflows/{workflow_id}/dispatches"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"ref": ref, "inputs": inputs}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code not in (200, 204):
            logger.error(
                "Failed to dispatch workflow %s: %s %s",
                workflow_id,
                resp.status_code,
                resp.text,
            )
        else:
            logger.info("Dispatched workflow %s for repo %s", workflow_id, repo)


async def _dispatch_repository_event(
    repo: str,
    event_type: str,
    client_payload: dict,
    github_token: str,
) -> None:
    """Fire a repository_dispatch event so any workflow listening on that
    event_type can pick it up — no need to hard-code a workflow file name."""
    url = f"{GITHUB_API_URL}/repos/{repo}/dispatches"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"event_type": event_type, "client_payload": client_payload}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code not in (200, 204):
            logger.error(
                "Failed to dispatch repository event %s: %s %s",
                event_type,
                resp.status_code,
                resp.text,
            )
        else:
            logger.info(
                "Dispatched repository event %s for repo %s", event_type, repo
            )


async def _handle_payload(payload: dict) -> None:
    action = payload.get("action", "")
    data = payload.get("data", {})

    github_repo = os.environ.get("GITHUB_REPOSITORY", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    default_ref = os.environ.get("GITHUB_DEFAULT_BRANCH", "main")
    trigger_status = os.environ.get("LINEAR_TRIGGER_STATUS", DEFAULT_TRIGGER_STATUS)

    if not github_repo or not github_token:
        logger.warning("GITHUB_REPOSITORY or GITHUB_TOKEN not set; skipping dispatch")
        return

    issue_id = data.get("id", "")
    issue_title = data.get("title", "")
    current_state = data.get("state", {}).get("name", "")

    if action == "update" and current_state == trigger_status:
        # Fire a repository_dispatch event so any workflow listening on
        # "linear-issue-ready" can handle it — decouples the webhook from
        # the specific workflow file name.
        await _dispatch_repository_event(
            repo=github_repo,
            event_type="linear-issue-ready",
            client_payload={
                "issue_id": issue_id,
                "issue_title": issue_title,
                "trigger_status": current_state,
                "ref": default_ref,
            },
            github_token=github_token,
        )

    elif action == "update":
        current_labels = [
            lbl["name"]
            for lbl in data.get("labels", {}).get("nodes", [])
        ]

        # Trigger dogfood workflow when the dogfood label is newly added
        if payload.get("type") == "Issue" and "dogfood" in current_labels:
            await _dispatch_workflow(
                repo=github_repo,
                workflow_id="agentic-issue-to-pr.yml",
                ref=default_ref,
                inputs={"issue_id": issue_id, "issue_title": issue_title},
                github_token=github_token,
            )


@router.post("/webhooks/linear")
async def linear_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> dict:
    webhook_secret = os.environ.get("LINEAR_WEBHOOK_SECRET", "")
    body = await request.body()

    if webhook_secret:
        signature = request.headers.get("linear-signature", "")
        if not _verify_signature(body, signature, webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    background_tasks.add_task(_handle_payload, payload)
    return {"ok": True}
