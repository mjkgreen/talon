"""
FastAPI Server ?" API, Webhooks, WebSockets, and UI serving.

Start:
  talon serve [--port 8080]
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console

from talon import db

console = Console()

WEBHOOK_LABEL = os.getenv("WEBHOOK_LABEL", "agent-task")
LINEAR_SECRET = os.getenv("LINEAR_WEBHOOK_SECRET", "")
GITHUB_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_RUNS", "3"))

app = FastAPI(title="Talon Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

async def broadcast_issue_update(issue_id: int):
    issue = await db.get_issue(issue_id)
    if issue:
        await manager.broadcast({"type": "issue_updated", "issue": issue.model_dump()})

async def _run_loop(goal: str, source: str, issue_id: int | None = None, working_dir: str | None = None) -> None:
    sem = _get_semaphore()
    if sem.locked():
        console.print(f"[yellow]Webhook queued (at concurrency limit): {goal[:60]}[/yellow]")
    
    if issue_id:
        await db.update_issue(issue_id, db.IssueUpdate(status="In Progress"))
        await broadcast_issue_update(issue_id)
        
    async with sem:
        console.print(f"\n[bold green]-  Triggered[/bold green] [{source}] {goal[:80]}")
        try:
            from talon.loop import run
            
            async def on_step(state):
                if issue_id:
                    # Update run_id in DB on first step
                    if state.iteration == 0 and not getattr(state, "_db_updated", False):
                        await db.update_issue(issue_id, db.IssueUpdate(run_id=state.run_id))
                        state._db_updated = True
                        
                    # Broadcast run state to UI
                    await manager.broadcast({
                        "type": "run_state_updated",
                        "issue_id": issue_id,
                        "state": state.model_dump()
                    })

            state = await run(goal=goal, working_dir=working_dir, skip_board=False, on_step=on_step)
            
            if issue_id:
                final_status = "Done" if state.status == "passed" else "Failed"
                await db.update_issue(issue_id, db.IssueUpdate(status=final_status, run_id=state.run_id))
                await broadcast_issue_update(issue_id)
                
        except Exception as e:
            console.print(f"[red]Loop error: {e}[/red]")
            if issue_id:
                await db.update_issue(issue_id, db.IssueUpdate(status="Failed"))
                await broadcast_issue_update(issue_id)

@app.on_event("startup")
async def startup_event():
    await db.init_db()

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# --- REST APIs for Kanban ---

@app.get("/api/issues")
async def get_issues():
    return await db.list_issues()

@app.post("/api/issues")
async def create_issue(issue: db.IssueCreate, background_tasks: BackgroundTasks):
    new_issue = await db.create_issue(issue)
    await broadcast_issue_update(new_issue.id)
    if new_issue.status == "Backlog":
        # Don't run automatically unless placed elsewhere?
        # Actually, let's just create it. The user can drag to trigger.
        pass
    elif new_issue.status == "In Progress":
        background_tasks.add_task(_run_loop, f"{issue.title}\n\n{issue.description}", "ui", new_issue.id)
    return new_issue

@app.patch("/api/issues/{issue_id}")
async def update_issue(issue_id: int, updates: db.IssueUpdate, background_tasks: BackgroundTasks):
    old_issue = await db.get_issue(issue_id)
    if not old_issue:
        raise HTTPException(status_code=404, detail="Issue not found")
        
    updated = await db.update_issue(issue_id, updates)
    await broadcast_issue_update(issue_id)
    
    # If dragged into In Progress from Backlog, trigger run
    if updates.status == "In Progress" and old_issue.status != "In Progress":
        background_tasks.add_task(_run_loop, f"{updated.title}\n\n{updated.description}", "ui", updated.id)
        
    return updated

@app.delete("/api/issues/{issue_id}")
async def delete_issue(issue_id: int):
    deleted = await db.delete_issue(issue_id)
    if deleted:
        await manager.broadcast({"type": "issue_deleted", "issue_id": issue_id})
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Issue not found")

# --- WebSockets ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- Webhooks (Legacy/Optional Sync) ---

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
    
    # Mirror linear issue to local SQLite
    issue = await db.create_issue(db.IssueCreate(title=title, description=description, status="In Progress"))
    await broadcast_issue_update(issue.id)

    goal = f"{title}\n\n{description}".strip() if description else title
    background_tasks.add_task(_run_loop, goal, "linear", issue.id)
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

    issue_data = payload.get("issue", {})
    labels = _extract_labels(issue_data.get("labels", []))
    if WEBHOOK_LABEL and WEBHOOK_LABEL not in labels:
        return {"ok": True, "skipped": f"label '{WEBHOOK_LABEL}' not present"}

    title = issue_data.get("title", "")
    body_text = issue_data.get("body", "") or ""
    
    # Mirror github issue to local SQLite
    issue = await db.create_issue(db.IssueCreate(title=title, description=body_text, status="In Progress"))
    await broadcast_issue_update(issue.id)

    goal = f"{title}\n\n{body_text}".strip() if body_text else title
    background_tasks.add_task(_run_loop, goal, "github", issue.id)
    return {"ok": True, "triggered": True, "goal": goal[:80]}

# --- UI Serving ---

ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "dist")

if os.path.exists(ui_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(ui_dir, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_ui(full_path: str):
        path = os.path.join(ui_dir, full_path)
        if os.path.exists(path) and os.path.isfile(path):
            return FileResponse(path)
        return FileResponse(os.path.join(ui_dir, "index.html"))
