from __future__ import annotations

import hashlib
import hmac
import json
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from talon import db
from talon.background import _run_loop
from talon.routers.websocket import broadcast_issue_update

router = APIRouter()

WEBHOOK_LABEL = os.getenv("WEBHOOK_LABEL", "agent-task")
LINEAR_SECRET = os.getenv("LINEAR_WEBHOOK_SECRET", "")
GITHUB_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


def _verify_hmac(secret: str, body: bytes, received: str, prefix: str = "") -> bool:
    """Constant-time HMAC-SHA256 verification. Returns True if no secret configured."""
    if not secret:
        return True
    expected = prefix + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)


def _extract_labels(items: list[dict]) -> list[str]:
    return [item.get("name", "") for item in items]


@router.post("/webhook/linear")
async def linear_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    linear_signature: str = Header(default="", alias="Linear-Signature"),
) -> dict:
    body = await request.body()
    if not _verify_hmac(LINEAR_SECRET, body, linear_signature):
        raise HTTPException(status_code=401, detail="Invalid Linear signature")

    payload = json.loads(body)
    if payload.get("action") != "create" or payload.get("type") != "Issue":
        return {"ok": True, "skipped": "not an issue create event"}

    data = payload.get("data", {})
    labels = _extract_labels(data.get("labels", []))
    if WEBHOOK_LABEL and WEBHOOK_LABEL not in labels:
        return {"ok": True, "skipped": f"label '{WEBHOOK_LABEL}' not present"}

    title = data.get("title", "")
    description = data.get("description", "") or ""

    project_id = await db.get_first_project_id()
    issue = await db.create_issue(
        db.IssueCreate(
            title=title, description=description, status="In Progress", project_id=project_id
        )
    )
    await broadcast_issue_update(issue.id)

    goal = f"{title}\n\n{description}".strip() if description else title
    background_tasks.add_task(_run_loop, goal, "linear", issue.id)
    return {"ok": True, "triggered": True, "goal": goal[:80]}


@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default="", alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(default="", alias="X-Hub-Signature-256"),
) -> dict:
    body = await request.body()
    if not _verify_hmac(GITHUB_SECRET, body, x_hub_signature_256, prefix="sha256="):
        raise HTTPException(status_code=401, detail="Invalid GitHub signature")

    payload = json.loads(body)
    if x_github_event != "issues" or payload.get("action") != "opened":
        return {"ok": True, "skipped": "not an issue opened event"}

    issue_data = payload.get("issue", {})
    labels = _extract_labels(issue_data.get("labels", []))
    if WEBHOOK_LABEL and WEBHOOK_LABEL not in labels:
        return {"ok": True, "skipped": f"label '{WEBHOOK_LABEL}' not present"}

    title = issue_data.get("title", "")
    body_text = issue_data.get("body", "") or ""

    project_id = await db.get_first_project_id()
    issue = await db.create_issue(
        db.IssueCreate(
            title=title, description=body_text, status="In Progress", project_id=project_id
        )
    )
    await broadcast_issue_update(issue.id)

    goal = f"{title}\n\n{body_text}".strip() if body_text else title
    background_tasks.add_task(_run_loop, goal, "github", issue.id)
    return {"ok": True, "triggered": True, "goal": goal[:80]}
