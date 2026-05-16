"""
Webhook listener — receives Linear and GitHub events and triggers the agent loop.

Start:
  talon serve [--port 8080]

Linear setup:
  Settings → API → Webhooks → URL: https://your-host/webhook/linear
  Set LINEAR_WEBHOOK_SECRET in .env

GitHub setup:
  Repo → Settings → Webhooks → URL: https://your-host/webhook/github
  Content type: application/json · Events: Issues
  Set GITHUB_WEBHOOK_SECRET in .env

Filtering:
  Only issues whose labels include WEBHOOK_LABEL (default: "agent-task") trigger a run.
  Set WEBHOOK_LABEL="" to accept all issues.

Concurrency:
  MAX_CONCURRENT_RUNS (default 3) caps simultaneous loop executions.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from rich.console import Console

console = Console()

WEBHOOK_LABEL = os.getenv("WEBHOOK_LABEL", "agent-task")
LINEAR_SECRET = os.getenv("LINEAR_WEBHOOK_SECRET", "")
GITHUB_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_RUNS", "3"))

app = FastAPI(title="Agent Webhook", version="1.0.0")

# Initialised on first request (needs running event loop)
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


def _verify_hmac(secret: str, body: bytes, received: str, prefix: str = "") -> bool:
    """Constant-time HMAC-SHA256 verification. Returns True if no secret configured."""
    if not secret:
        return True
    expected = prefix + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)


def _extract_labels(items: list[dict]) -> list[str]:
    return [item.get("name", "") for item in items]


async def _run_loop(goal: str, source: str, working_dir: str | None = None) -> None:
    sem = _get_semaphore()
    if sem.locked():
        console.print(f"[yellow]Webhook queued (at concurrency limit): {goal[:60]}[/yellow]")
    async with sem:
        console.print(f"\n[bold green]▶ Webhook trigger[/bold green] [{source}] {goal[:80]}")
        try:
            from talon.loop import run

            await run(goal=goal, working_dir=working_dir, skip_board=False)
        except Exception as e:
            console.print(f"[red]Loop error: {e}[/red]")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/webhook/linear")
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
    goal = f"{title}\n\n{description}".strip() if description else title

    background_tasks.add_task(_run_loop, goal, "linear")
    return {"ok": True, "triggered": True, "goal": goal[:80]}


@app.post("/webhook/github")
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

    issue = payload.get("issue", {})
    labels = _extract_labels(issue.get("labels", []))
    if WEBHOOK_LABEL and WEBHOOK_LABEL not in labels:
        return {"ok": True, "skipped": f"label '{WEBHOOK_LABEL}' not present"}

    title = issue.get("title", "")
    body_text = issue.get("body", "") or ""
    goal = f"{title}\n\n{body_text}".strip() if body_text else title

    background_tasks.add_task(_run_loop, goal, "github")
    return {"ok": True, "triggered": True, "goal": goal[:80]}
