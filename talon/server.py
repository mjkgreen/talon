"""
FastAPI Server → API, Webhooks, WebSockets, and UI serving.

Start:
  talon serve [--port 8080]
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import traceback
from datetime import datetime
from typing import Optional

import httpx
from fastapi import (
    BackgroundTasks,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rich.console import Console

from talon import db

console = Console()

WEBHOOK_LABEL = os.getenv("WEBHOOK_LABEL", "agent-task")
LINEAR_SECRET = os.getenv("LINEAR_WEBHOOK_SECRET", "")
GITHUB_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_RUNS", "3"))
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

# Maps DB settings keys → environment variable names for AI/model config
_DB_TO_ENV: dict[str, str] = {
    "anthropic_api_key":  "ANTHROPIC_API_KEY",
    "openai_api_key":     "OPENAI_API_KEY",
    "gemini_api_key":     "GEMINI_API_KEY",
    "groq_api_key":       "GROQ_API_KEY",
    "mistral_api_key":    "MISTRAL_API_KEY",
    "agent_model":        "AGENT_MODEL",
    "orchestrator_model": "ORCHESTRATOR_MODEL",
    "subagent_model":     "SUBAGENT_MODEL",
    "reviewer_model":     "REVIEWER_MODEL",
    "refiner_model":      "REFINER_MODEL",
    "max_iterations":     "MAX_ITERATIONS",
    "agent_max_tokens":   "AGENT_MAX_TOKENS",
}

_API_KEY_SETTINGS = {
    "anthropic_api_key", "openai_api_key", "gemini_api_key",
    "groq_api_key", "mistral_api_key",
}

app = FastAPI(title="Talon Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For Vite dev server
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


def _has_llm_configured() -> bool:
    """Return True if at least one AI provider API key is available."""
    keys = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"]
    return any(os.getenv(k) for k in keys)


async def _apply_db_settings_to_env() -> None:
    """Load AI/model settings from DB into os.environ.

    DB-stored values fill in missing env vars only — system env (set in .env
    or the process environment) always takes precedence.
    """
    settings = await db.get_all_settings()
    for db_key, env_key in _DB_TO_ENV.items():
        value = settings.get(db_key)
        if value and not os.environ.get(env_key):
            os.environ[env_key] = value


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


async def _run_loop(
    goal: str,
    source: str,
    issue_id: int | None = None,
    working_dir: str | None = None,
    project_id: int | None = None,
) -> None:
    sem = _get_semaphore()
    if sem.locked():
        console.print(f"[yellow]Webhook queued (at concurrency limit): {goal[:60]}[/yellow]")

    if issue_id:
        await db.update_issue(issue_id, db.IssueUpdate(status="In Progress"))
        await broadcast_issue_update(issue_id)

    # Guard: refuse to run if no LLM provider is configured
    if not _has_llm_configured():
        console.print("[red]No AI provider configured — set an API key in Settings.[/red]")
        if issue_id:
            await manager.broadcast({
                "type": "run_error",
                "issue_id": issue_id,
                "error": "No AI provider configured. Add an API key in Settings.",
            })
            await db.update_issue(issue_id, db.IssueUpdate(status="Failed"))
            await broadcast_issue_update(issue_id)
        return

    async with sem:
        console.print(f"\n[bold green]-  Triggered[/bold green] [{source}] {goal[:80]}")
        try:
            from talon.loop import run

            async def on_step(state):
                if issue_id:
                    if state.iteration == 0:
                        await db.update_issue(issue_id, db.IssueUpdate(run_id=state.run_id))
                        await broadcast_issue_update(issue_id)

                    await manager.broadcast(
                        {
                            "type": "run_state_updated",
                            "issue_id": issue_id,
                            "state": state.model_dump(mode="json"),
                        }
                    )

            async def on_log(message: str):
                if issue_id:
                    await manager.broadcast(
                        {
                            "type": "run_log",
                            "issue_id": issue_id,
                            "message": message,
                        }
                    )

            # Resolve workspace settings: project-level first, fall back to global
            github_token = await db.get_setting("github_token")
            if project_id:
                project = await db.get_project(project_id)
                workspace_mode = project.workspace_mode if project else await db.get_setting("workspace_mode")
                selected_repo = project.selected_repo if project else await db.get_setting("selected_repo")
                local_path = project.local_path if project else await db.get_setting("local_path")
            else:
                workspace_mode = await db.get_setting("workspace_mode")
                selected_repo = await db.get_setting("selected_repo")
                local_path = await db.get_setting("local_path")

            repo_url = None
            base_dir = working_dir
            if workspace_mode == "github" and github_token and selected_repo:
                repo_url = f"https://x-access-token:{github_token}@github.com/{selected_repo}.git"
            elif workspace_mode == "local" and local_path:
                base_dir = local_path

            edit_local_directly = (
                workspace_mode == "local"
                and bool(local_path)
                and await db.get_setting("edit_local_directly") == "true"
            )
            push_on_pass_setting = await db.get_setting("push_on_pass")
            create_pr = push_on_pass_setting != "false"  # default True

            state = await run(
                goal=goal,
                working_dir=base_dir,
                repo_url=repo_url,
                skip_board=False,
                direct_workspace=edit_local_directly,
                create_pr=create_pr,
                on_step=on_step,
                on_log=on_log,
            )

            if issue_id:
                final_status = "Done" if state.status == "passed" else "Failed"
                await db.update_issue(
                    issue_id, db.IssueUpdate(status=final_status, run_id=state.run_id)
                )
                await broadcast_issue_update(issue_id)

        except Exception as e:
            try:
                console.print(f"[red]Loop error: {e}[/red]")
                console.print(traceback.format_exc())
            except Exception:
                pass
            if issue_id:
                try:
                    await manager.broadcast(
                        {
                            "type": "run_error",
                            "issue_id": issue_id,
                            "error": str(e),
                        }
                    )
                except Exception:
                    pass
                await db.update_issue(issue_id, db.IssueUpdate(status="Failed"))
                await broadcast_issue_update(issue_id)


@app.on_event("startup")
async def startup_event():
    await db.init_db()
    await _apply_db_settings_to_env()
    stalled = await db.reset_stalled_issues()
    for issue_id in stalled:
        await broadcast_issue_update(issue_id)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# --- Settings ---


@app.get("/api/settings")
async def get_settings():
    settings = await db.get_all_settings()
    # Mask all sensitive key values
    for key in _API_KEY_SETTINGS | {"github_token"}:
        if settings.get(key):
            settings[key] = "***" + settings[key][-4:]
    # Computed fields for the frontend
    settings["has_llm_configured"] = _has_llm_configured()
    for provider_env, provider_name in [
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("OPENAI_API_KEY", "openai"),
        ("GEMINI_API_KEY", "google"),
        ("GROQ_API_KEY", "groq"),
        ("MISTRAL_API_KEY", "mistral"),
    ]:
        if os.getenv(provider_env):
            settings["active_provider"] = provider_name
            break
    else:
        settings["active_provider"] = None
    return settings


@app.post("/api/settings")
async def update_settings(updates: db.SettingsUpdate):
    # --- GitHub token (existing) ---
    if updates.github_token and not updates.github_token.startswith("***"):
        await db.set_setting("github_token", updates.github_token)

    # --- Legacy global workspace (kept for webhook-triggered runs and migration) ---
    if updates.selected_repo is not None:
        await db.set_setting("selected_repo", updates.selected_repo)
    if updates.local_path is not None:
        await db.set_setting("local_path", updates.local_path)
    if updates.workspace_mode is not None:
        await db.set_setting("workspace_mode", updates.workspace_mode)

    # --- Local workspace behaviour ---
    if updates.edit_local_directly is not None:
        await db.set_setting("edit_local_directly", updates.edit_local_directly)
    if updates.push_on_pass is not None:
        await db.set_setting("push_on_pass", updates.push_on_pass)

    # --- AI keys, model routing, run limits (all share the same DB key as field name) ---
    for db_key, env_key in _DB_TO_ENV.items():
        val = getattr(updates, db_key, None)
        if val is None:
            continue
        if val == "":
            await db.delete_setting(db_key)
            os.environ.pop(env_key, None)
        elif db_key in _API_KEY_SETTINGS and val.startswith("***"):
            pass  # masked display value from frontend — don't overwrite with the mask
        else:
            await db.set_setting(db_key, val)
            os.environ[env_key] = val

    return {"ok": True}


# --- Project CRUD ---


@app.get("/api/projects")
async def list_projects():
    return await db.list_projects()


@app.post("/api/projects")
async def create_project(p: db.ProjectCreate):
    project = await db.create_project(p)
    await manager.broadcast({"type": "project_created", "project": project.model_dump()})
    return project


@app.patch("/api/projects/{project_id}")
async def update_project(project_id: int, updates: db.ProjectUpdate):
    project = await db.update_project(project_id, updates)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await manager.broadcast({"type": "project_updated", "project": project.model_dump()})
    return project


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    all_projects = await db.list_projects()
    if len(all_projects) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last project")
    deleted = await db.delete_project(project_id)
    if deleted:
        await manager.broadcast({"type": "project_deleted", "project_id": project_id})
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Project not found")


# --- GitHub OAuth ---


class _GitHubPollRequest(BaseModel):
    device_code: str


class _GitHubExchangeRequest(BaseModel):
    code: str
    state: str


@app.get("/api/auth/github/authorize")
async def github_auth_authorize():
    """Return a GitHub OAuth authorize URL. Electron opens this in the system browser.
    GitHub redirects to talon://oauth-callback?code=...&state=... which Electron intercepts
    and forwards to /api/auth/github/exchange."""
    import secrets

    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=400,
            detail=(
                "GITHUB_CLIENT_ID not configured. "
                "Register an OAuth App at github.com/settings/developers."
            ),
        )
    state = secrets.token_urlsafe(16)
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&scope=repo"
        f"&state={state}"
        f"&redirect_uri=talon://oauth-callback"
    )
    return {"url": url, "state": state}


@app.post("/api/auth/github/exchange")
async def github_auth_exchange(body: _GitHubExchangeRequest):
    """Exchange an OAuth code for an access token and save it. Called by Electron after
    it catches the talon://oauth-callback deep link."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=400,
            detail="GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET not configured.",
        )
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": body.code,
                "redirect_uri": "talon://oauth-callback",
            },
        )
    data = res.json()
    if "access_token" not in data:
        raise HTTPException(
            status_code=400,
            detail=data.get("error_description", "Token exchange failed"),
        )
    await db.set_setting("github_token", data["access_token"])
    await manager.broadcast({"type": "github_auth_complete"})
    return {"status": "complete"}


@app.get("/api/local/browse")
async def browse_local_folder():
    """Open a native OS folder-picker dialog and return the selected path."""
    def _pick() -> str:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select project folder")
        root.destroy()
        return path or ""

    path = await asyncio.get_running_loop().run_in_executor(None, _pick)
    return {"path": path}


@app.post("/api/auth/github/start")
async def github_auth_start():
    """Initiate GitHub Device Flow. Returns user_code and verification_uri."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=400,
            detail=(
                "GITHUB_CLIENT_ID not configured. "
                "Register an OAuth App at github.com/settings/developers."
            ),
        )
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://github.com/login/device/code",
            headers={"Accept": "application/json"},
            json={"client_id": GITHUB_CLIENT_ID, "scope": "repo"},
        )
    if res.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to initiate GitHub device flow")
    data = res.json()
    return {
        "device_code": data["device_code"],
        "user_code": data["user_code"],
        "verification_uri": data["verification_uri"],
        "expires_in": data.get("expires_in", 900),
        "interval": data.get("interval", 5),
    }


@app.post("/api/auth/github/poll")
async def github_auth_poll(body: _GitHubPollRequest):
    """Poll GitHub for a device flow token. Saves token to DB on success."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=400, detail="GITHUB_CLIENT_ID not configured")
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            json={
                "client_id": GITHUB_CLIENT_ID,
                "device_code": body.device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
    data = res.json()
    error = data.get("error")
    if error in ("authorization_pending", "slow_down"):
        return {"status": "pending"}
    if error in ("expired_token", "access_denied"):
        return {"status": "expired"}
    if "access_token" in data:
        await db.set_setting("github_token", data["access_token"])
        return {"status": "complete"}
    return {"status": "error", "detail": error}


@app.get("/api/github/repos")
async def list_github_repos():
    token = await db.get_setting("github_token")
    if not token:
        raise HTTPException(status_code=401, detail="GitHub token not configured")

    async with httpx.AsyncClient() as client:
        res = await client.get(
            "https://api.github.com/user/repos?per_page=100&sort=updated",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        if res.status_code != 200:
            raise HTTPException(
                status_code=res.status_code, detail="Failed to fetch repos from GitHub"
            )
        repos = res.json()
        return [{"full_name": r["full_name"], "name": r["name"]} for r in repos]


@app.post("/api/github/sync")
async def sync_github_issues(project_id: Optional[int] = Query(default=None)):
    token = await db.get_setting("github_token")
    # Resolve repo from project or global settings
    if project_id:
        project = await db.get_project(project_id)
        repo = project.selected_repo if project else await db.get_setting("selected_repo")
    else:
        repo = await db.get_setting("selected_repo")

    if not token or not repo:
        raise HTTPException(status_code=400, detail="GitHub token or repo not configured")

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        if res.status_code != 200:
            raise HTTPException(
                status_code=res.status_code, detail="Failed to fetch issues from GitHub"
            )

        issues = res.json()
        synced = 0
        existing = await db.list_issues(project_id=project_id)
        existing_titles = {i.title for i in existing}

        for issue in issues:
            if "pull_request" in issue:
                continue
            title = issue["title"]
            if title not in existing_titles:
                body = issue.get("body") or ""
                new_issue = await db.create_issue(
                    db.IssueCreate(title=title, description=body, status="Backlog", project_id=project_id)
                )
                await broadcast_issue_update(new_issue.id)
                synced += 1

        return {"ok": True, "synced": synced}


# --- Issues ---


@app.get("/api/issues")
async def get_issues(project_id: Optional[int] = Query(default=None)):
    return await db.list_issues(project_id=project_id)


@app.get("/api/runs/{run_id}")
async def get_run_state(run_id: str):
    run_dir = os.path.join(os.getenv("RUNS_DIR", "./runs"), run_id)
    state_file = os.path.join(run_dir, "state.json")
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)

    runs_dir_path = os.getenv("RUNS_DIR", "./runs")
    if os.path.exists(runs_dir_path):
        for item in os.listdir(runs_dir_path):
            if item.startswith(run_id) or run_id.startswith(item):
                alt_state = os.path.join(runs_dir_path, item, "state.json")
                if os.path.exists(alt_state):
                    with open(alt_state, "r") as f:
                        return json.load(f)

    raise HTTPException(status_code=404, detail=f"Run state not found for {run_id} at {state_file}")


@app.get("/api/runs/{run_id}/video")
async def get_run_video(run_id: str):
    run_dir = os.path.join(os.getenv("RUNS_DIR", "./runs"), run_id)
    state_file = os.path.join(run_dir, "state.json")
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            video_path = data.get("video_path")
            if video_path and os.path.exists(video_path):
                return FileResponse(video_path)
    raise HTTPException(status_code=404, detail="Video not found")


@app.post("/api/issues")
async def create_issue(issue: db.IssueCreate, background_tasks: BackgroundTasks):
    new_issue = await db.create_issue(issue)
    await broadcast_issue_update(new_issue.id)
    if new_issue.status == "In Progress":
        background_tasks.add_task(
            _run_loop,
            f"{issue.title}\n\n{issue.description}",
            "ui",
            new_issue.id,
            None,
            issue.project_id,
        )
    return new_issue


@app.patch("/api/issues/{issue_id}")
async def update_issue(issue_id: int, updates: db.IssueUpdate, background_tasks: BackgroundTasks):
    old_issue = await db.get_issue(issue_id)
    if not old_issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    is_requeue = updates.status == "In Progress" and old_issue.status != "In Progress"
    if is_requeue:
        updates = updates.model_copy(update={"clear_run_id": True})

    updated = await db.update_issue(issue_id, updates)
    await broadcast_issue_update(issue_id)

    if is_requeue:
        background_tasks.add_task(
            _run_loop,
            f"{updated.title}\n\n{updated.description}",
            "ui",
            updated.id,
            None,
            updated.project_id,
        )

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

    project_id = await db.get_first_project_id()
    issue = await db.create_issue(
        db.IssueCreate(title=title, description=description, status="In Progress", project_id=project_id)
    )
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

    project_id = await db.get_first_project_id()
    issue = await db.create_issue(
        db.IssueCreate(title=title, description=body_text, status="In Progress", project_id=project_id)
    )
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
