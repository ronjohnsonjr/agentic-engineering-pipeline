import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()

GITHUB_API_URL = "https://api.github.com"


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


async def _handle_payload(payload: dict) -> None:
    action = payload.get("action", "")
    data = payload.get("data", {})

    github_repo = os.environ.get("GITHUB_REPOSITORY", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    default_ref = os.environ.get("GITHUB_DEFAULT_BRANCH", "main")

    if not github_repo or not github_token:
        logger.warning("GITHUB_REPOSITORY or GITHUB_TOKEN not set; skipping dispatch")
        return

    issue_id = data.get("id", "")
    issue_title = data.get("title", "")

    if action == "update" and data.get("state", {}).get("name") == "In Progress":
        await _dispatch_workflow(
            repo=github_repo,
            workflow_id="issue-to-pr.yml",
            ref=default_ref,
            inputs={"issue_id": issue_id, "issue_title": issue_title},
            github_token=github_token,
        )

    elif action == "update":
        added_labels = [
            lbl["name"]
            for lbl in payload.get("updatedFrom", {}).get("labels", {}).get("nodes", [])
            if lbl["name"] == "dogfood"
        ]
        current_labels = [
            lbl["name"]
            for lbl in data.get("labels", {}).get("nodes", [])
        ]
        if "dogfood" in current_labels and "dogfood" not in added_labels:
            # label was just added
            pass

        # Simpler: check if dogfood label present in current payload and was just set
        if action == "update" and "dogfood" in current_labels:
            previous_labels = [
                lbl["name"]
                for lbl in (
                    payload.get("updatedFrom", {})
                    .get("labelIds", [])
                )
            ]
            # Trigger if dogfood is newly added
            newly_added = payload.get("type") == "Issue" and any(
                lbl["name"] == "dogfood"
                for lbl in data.get("labels", {}).get("nodes", [])
            )
            if newly_added:
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
