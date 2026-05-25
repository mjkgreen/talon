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
import re
import traceback
from datetime import datetime
from pathlib import Path
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
MAX_CONCURRENT_DEFAULT = 3
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

# Maps DB settings keys → environment variable names for AI/model config
_DB_TO_ENV: dict[str, str] = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
    "groq_api_key": "GROQ_API_KEY",
    "mistral_api_key": "MISTRAL_API_KEY",
    "agent_model": "AGENT_MODEL",
    "orchestrator_model": "ORCHESTRATOR_MODEL",
    "subagent_model": "SUBAGENT_MODEL",
    "reviewer_model": "REVIEWER_MODEL",
    "refiner_model": "REFINER_MODEL",
    "max_iterations": "MAX_ITERATIONS",
    "agent_max_tokens": "AGENT_MAX_TOKENS",
    "reviewer_max_tool_turns": "REVIEWER_MAX_TOOL_TURNS",
    "max_concurrent_runs": "MAX_CONCURRENT_RUNS",
    "browser_test_max_steps": "BROWSER_TEST_MAX_STEPS",
}

_API_KEY_SETTINGS = {
    "anthropic_api_key",
    "openai_api_key",
    "gemini_api_key",
    "groq_api_key",
    "mistral_api_key",
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
        limit = int(os.getenv("MAX_CONCURRENT_RUNS", str(MAX_CONCURRENT_DEFAULT)))
        _semaphore = asyncio.Semaphore(limit)
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
    keys = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
    ]
    return any(os.getenv(k) for k in keys)


async def _apply_db_settings_to_env() -> None:
    """Load AI/model settings from DB into os.environ.

    DB-stored values take precedence and overwrite process/env settings.
    """
    settings = await db.get_all_settings()
    for db_key, env_key in _DB_TO_ENV.items():
        value = settings.get(db_key)
        if value:
            os.environ[env_key] = value


def _reset_stalled_verifications() -> None:
    """Find all run states on disk and reset `verification_running` to False if stuck as True."""
    runs_dir_path = os.getenv("RUNS_DIR", "./runs")
    if os.path.exists(runs_dir_path):
        for run_id in os.listdir(runs_dir_path):
            run_dir = os.path.join(runs_dir_path, run_id)
            if os.path.isdir(run_dir):
                state_file = os.path.join(run_dir, "state.json")
                if os.path.exists(state_file):
                    try:
                        if os.path.getsize(state_file) == 0:
                            continue
                        with open(state_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if isinstance(data, dict) and data.get("verification_running"):
                            console.print(f"[yellow]Resetting stalled verification_running for run: {run_id}[/yellow]")
                            data["verification_running"] = False
                            with open(state_file, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=2)
                    except json.JSONDecodeError:
                        # Skip empty or corrupted JSON files cleanly
                        continue
                    except Exception as e:
                        console.print(f"[red]Error resetting stalled verification run {run_id}: {e}[/red]")


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

_planning_issues: set[int] = set()


def _check_workspace(workspace_mode: str | None, local_path: str | None) -> str | None:
    """Return an error string if the workspace is unusable, or None if it's fine."""
    if workspace_mode == "local":
        if not local_path:
            return "Local workspace is configured but no path is set."
        p = Path(local_path)
        if not p.exists():
            return f"Workspace directory not found: {local_path}"
        if not p.is_dir():
            return f"Workspace path is not a directory: {local_path}"
    return None


async def _run_planner_bg(issue_id: int, goal: str) -> None:
    """Generate a plan for a backlog issue and store it. Runs as a background task."""
    _planning_issues.add(issue_id)
    await manager.broadcast({"type": "plan_started", "issue_id": issue_id})
    try:
        # Resolve workspace so the planner can explore the actual codebase.
        working_dir: str | None = None
        plan_project_id: int | None = None
        issue = await db.get_issue(issue_id)
        if issue and issue.project_id:
            plan_project_id = issue.project_id
            project = await db.get_project(issue.project_id)
            if project:
                if project.workspace_mode == "local":
                    ws_error = _check_workspace(project.workspace_mode, project.local_path)
                    if ws_error:
                        await manager.broadcast(
                            {
                                "type": "workspace_invalid",
                                "issue_id": issue_id,
                                "project_id": plan_project_id,
                                "error": ws_error,
                            }
                        )
                        await manager.broadcast(
                            {"type": "plan_error", "issue_id": issue_id, "error": ws_error}
                        )
                        return
                    working_dir = project.local_path
                elif project.workspace_mode == "github":
                    github_token = await db.get_setting("github_token")
                    if not github_token:
                        ws_error = (
                            "GitHub workspace configured but no GitHub token found"
                            " — please re-authenticate."
                        )
                        await manager.broadcast(
                            {
                                "type": "workspace_invalid",
                                "issue_id": issue_id,
                                "project_id": plan_project_id,
                                "error": ws_error,
                            }
                        )
                        await manager.broadcast(
                            {"type": "plan_error", "issue_id": issue_id, "error": ws_error}
                        )
                        return
                    if not project.selected_repo:
                        ws_error = "GitHub workspace configured but no repository selected."
                        await manager.broadcast(
                            {
                                "type": "workspace_invalid",
                                "issue_id": issue_id,
                                "project_id": plan_project_id,
                                "error": ws_error,
                            }
                        )
                        await manager.broadcast(
                            {"type": "plan_error", "issue_id": issue_id, "error": ws_error}
                        )
                        return
                    repo_url = (
                        f"https://x-access-token:{github_token}"
                        f"@github.com/{project.selected_repo}.git"
                    )
                    try:
                        from talon import workspace as _workspace

                        working_dir = await asyncio.to_thread(
                            _workspace.ensure_planner_clone,
                            plan_project_id,
                            repo_url,
                            project.selected_branch or None,
                        )
                    except Exception as clone_err:
                        console.print(
                            f"[yellow]Planner clone failed for project"
                            f" {plan_project_id}: {clone_err}[/yellow]"
                        )
                        # Non-fatal: plan without workspace exploration

        from talon.skills.planner import run as planner_run

        plan = await planner_run(goal=goal, working_dir=working_dir)
        plan_json = plan.model_dump_json()
        await db.update_issue(issue_id, db.IssueUpdate(plan_json=plan_json))
        issue = await db.get_issue(issue_id)
        await manager.broadcast(
            {
                "type": "plan_ready",
                "issue_id": issue_id,
                "issue": issue.model_dump() if issue else None,
            }
        )
    except Exception as e:
        console.print(f"[yellow]Planner failed for issue {issue_id}: {e}[/yellow]")
        await manager.broadcast({"type": "plan_error", "issue_id": issue_id, "error": str(e)})
    finally:
        _planning_issues.discard(issue_id)


async def _run_plan_refiner_bg(issue_id: int, goal: str) -> None:
    """Refine an existing plan using user feedback comments. Runs as a background task."""
    _planning_issues.add(issue_id)
    await manager.broadcast({"type": "plan_started", "issue_id": issue_id})
    try:
        issue = await db.get_issue(issue_id)
        if not issue or not issue.plan_json:
            raise ValueError("No existing plan to refine")
        from talon.types import PlanResult

        current_plan = PlanResult.model_validate_json(issue.plan_json)
        comments: list[str] = json.loads(issue.plan_comments or "[]")

        from talon.skills.plan_refiner import run as plan_refiner_run

        new_plan = await plan_refiner_run(goal=goal, current_plan=current_plan, comments=comments)

        await db.update_issue(
            issue_id,
            db.IssueUpdate(plan_json=new_plan.model_dump_json(), plan_comments="[]"),
        )
        updated = await db.get_issue(issue_id)
        await manager.broadcast(
            {
                "type": "plan_ready",
                "issue_id": issue_id,
                "issue": updated.model_dump() if updated else None,
            }
        )
    except Exception as e:
        console.print(f"[yellow]Plan refiner failed for issue {issue_id}: {e}[/yellow]")
        await manager.broadcast({"type": "plan_error", "issue_id": issue_id, "error": str(e)})
    finally:
        _planning_issues.discard(issue_id)


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
            await manager.broadcast(
                {
                    "type": "run_error",
                    "issue_id": issue_id,
                    "error": "No AI provider configured. Add an API key in Settings.",
                }
            )
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
                workspace_mode = (
                    project.workspace_mode if project else await db.get_setting("workspace_mode")
                )
                selected_repo = (
                    project.selected_repo if project else await db.get_setting("selected_repo")
                )
                selected_branch = project.selected_branch if project else None
                local_path = project.local_path if project else await db.get_setting("local_path")
            else:
                workspace_mode = await db.get_setting("workspace_mode")
                selected_repo = await db.get_setting("selected_repo")
                selected_branch = None
                local_path = await db.get_setting("local_path")

            ws_error = _check_workspace(workspace_mode, local_path)
            if ws_error:
                console.print(f"[red]Workspace invalid for issue {issue_id}: {ws_error}[/red]")
                if issue_id:
                    await manager.broadcast(
                        {
                            "type": "workspace_invalid",
                            "issue_id": issue_id,
                            "project_id": project_id,
                            "error": ws_error,
                        }
                    )
                    await db.update_issue(issue_id, db.IssueUpdate(status="Backlog"))
                    await broadcast_issue_update(issue_id)
                return

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

            # Load project-level server/env settings
            project_start_command: str | None = None
            project_env_vars: dict[str, str] | None = None
            project_env_content: str | None = None
            project_cookie_file: str | None = None
            project_test_user: str | None = None
            project_test_password: str | None = None
            if project_id:
                _proj = await db.get_project(project_id)
                if _proj:
                    project_start_command = _proj.start_command or None
                    project_env_content = _proj.env_content or None
                    project_cookie_file = _proj.cookie_file or None
                    project_test_user = _proj.test_user or None
                    project_test_password = _proj.test_password or None
                    if _proj.project_env_vars:
                        try:
                            project_env_vars = json.loads(_proj.project_env_vars)
                        except Exception:
                            pass

            # Load pre-computed plan from backlog phase (if any)
            precomputed_plan = None
            if issue_id:
                stored_issue = await db.get_issue(issue_id)
                if stored_issue and stored_issue.plan_json:
                    from talon.types import PlanResult

                    try:
                        precomputed_plan = PlanResult.model_validate_json(stored_issue.plan_json)
                    except Exception:
                        pass

            state = await run(
                goal=goal,
                working_dir=base_dir,
                repo_url=repo_url,
                repo_branch=selected_branch or None,
                skip_board=False,
                direct_workspace=edit_local_directly,
                create_pr=create_pr,
                plan=precomputed_plan,
                on_step=on_step,
                on_log=on_log,
                start_command=project_start_command,
                project_env_vars=project_env_vars,
                env_content=project_env_content,
                cookie_file=project_cookie_file,
                test_user=project_test_user,
                test_password=project_test_password,
            )

            if issue_id:
                if state.status == "passed":
                    final_status = "Done"
                elif state.status == "paused":
                    final_status = "Paused"
                else:
                    final_status = "Failed"
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
    _reset_stalled_verifications()
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
    try:
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
    except Exception as exc:
        console.print_exception()
        raise HTTPException(status_code=502, detail=f"GitHub token poll failed: {exc}") from exc
    error = data.get("error")
    if error in ("authorization_pending", "slow_down"):
        return {"status": "pending"}
    if error in ("expired_token", "access_denied"):
        return {"status": "expired"}
    if "access_token" in data:
        await db.set_setting("github_token", data["access_token"])
        await manager.broadcast({"type": "github_auth_complete"})
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


@app.get("/api/github/repos/{owner}/{repo}/branches")
async def list_repo_branches(owner: str, repo: str):
    token = await db.get_setting("github_token")
    if not token:
        raise HTTPException(status_code=401, detail="GitHub token not configured")

    async with httpx.AsyncClient() as client:
        repo_res = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        branches_res = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/branches?per_page=100",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )

    if repo_res.status_code != 200 or branches_res.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch branch info from GitHub")

    default_branch = repo_res.json().get("default_branch", "main")
    branches = [b["name"] for b in branches_res.json()]
    return {"default_branch": default_branch, "branches": branches}


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
                    db.IssueCreate(
                        title=title, description=body, status="Backlog", project_id=project_id
                    )
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


@app.get("/api/runs/{run_id}/screenshots/{filename}")
async def get_run_screenshot(run_id: str, filename: str):
    """Serve individual screenshot PNGs from the run's video directory."""
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+", run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    run_dir = Path(os.path.realpath(os.path.join(os.getenv("RUNS_DIR", "./runs"), run_id)))
    screenshot_path = Path(os.path.realpath(os.path.join(str(run_dir), filename)))
    if not screenshot_path.is_relative_to(run_dir):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not screenshot_path.exists() or screenshot_path.suffix != ".png":
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(screenshot_path), media_type="image/png")


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
    elif new_issue.status == "Backlog" and _has_llm_configured():
        background_tasks.add_task(
            _run_planner_bg,
            new_issue.id,
            f"{issue.title}\n\n{issue.description}".strip(),
        )
    return new_issue


class _PlanUpdate(BaseModel):
    plan_json: str


@app.patch("/api/issues/{issue_id}/plan")
async def update_issue_plan(issue_id: int, body: _PlanUpdate):
    issue = await db.update_issue(issue_id, db.IssueUpdate(plan_json=body.plan_json))
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    await broadcast_issue_update(issue_id)
    return issue


class _CommentAdd(BaseModel):
    comment: str


@app.post("/api/issues/{issue_id}/plan/comments")
async def add_plan_comment(issue_id: int, body: _CommentAdd):
    issue = await db.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    comments: list[str] = json.loads(issue.plan_comments or "[]")
    text = body.comment.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    comments.append(text)
    await db.update_issue(issue_id, db.IssueUpdate(plan_comments=json.dumps(comments)))
    await broadcast_issue_update(issue_id)
    return {"ok": True}


@app.post("/api/issues/{issue_id}/plan/refine")
async def refine_issue_plan(issue_id: int, background_tasks: BackgroundTasks):
    issue = await db.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not issue.plan_json:
        raise HTTPException(status_code=400, detail="No plan to refine")
    if not _has_llm_configured():
        raise HTTPException(status_code=400, detail="No LLM configured")
    goal = f"{issue.title}\n\n{issue.description}".strip()
    background_tasks.add_task(_run_plan_refiner_bg, issue_id, goal)
    return {"ok": True}


async def _resume_loop(issue_id: int, run_id: str) -> None:
    sem = _get_semaphore()
    if sem.locked():
        console.print(f"[yellow]Resume queued (at concurrency limit) for issue {issue_id}[/yellow]")

    await db.update_issue(issue_id, db.IssueUpdate(status="In Progress"))
    await broadcast_issue_update(issue_id)

    async with sem:
        console.print(
            f"\n[bold green]-  Resumed[/bold green] [ui] issue {issue_id} (run: {run_id})"
        )
        try:
            from talon.loop import resume

            async def on_step(state):
                await manager.broadcast(
                    {
                        "type": "run_state_updated",
                        "issue_id": issue_id,
                        "state": state.model_dump(mode="json"),
                    }
                )

            async def on_log(message: str):
                await manager.broadcast(
                    {
                        "type": "run_log",
                        "issue_id": issue_id,
                        "message": message,
                    }
                )

            state = await resume(
                run_id=run_id,
                on_step=on_step,
                on_log=on_log,
            )

            if state.status == "passed":
                final_status = "Done"
            elif state.status == "paused":
                final_status = "Paused"
            else:
                final_status = "Failed"
            await db.update_issue(issue_id, db.IssueUpdate(status=final_status))
            await broadcast_issue_update(issue_id)

        except Exception as e:
            try:
                console.print(f"[red]Resume error: {e}[/red]")
                console.print(traceback.format_exc())
            except Exception:
                pass
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


async def _run_verification_bg(issue_id: int, run_id: str) -> None:
    _server_proc = None
    _server_port = None
    state = None
    try:
        from talon.loop import _load_state, _save_state
        from talon.skills import browser_validator

        state = _load_state(run_id)

        # Mark as in-progress and clear old results immediately so the UI shows a clean slate.
        state.verification_running = True
        state.browser_result = None
        state.video_path = None
        _save_state(state)
        await manager.broadcast(
            {
                "type": "run_state_updated",
                "issue_id": issue_id,
                "state": state.model_dump(mode="json"),
            }
        )

        # Load project-level settings so verify has the same context as the original run.
        issue = await db.get_issue(issue_id)
        project = await db.get_project(issue.project_id) if issue and issue.project_id else None

        project_start_command = project.start_command if project else None
        project_env_vars_raw = project.project_env_vars if project else None
        project_env_vars: dict[str, str] | None = None
        if project_env_vars_raw:
            try:
                import json as _json

                project_env_vars = _json.loads(project_env_vars_raw)
            except Exception:
                pass
        project_env_content = project.env_content if project else None
        project_cookie_file = project.cookie_file if project else None
        project_test_user = project.test_user if project else None
        project_test_password = project.test_password if project else None

        static_url = await db.get_setting("default_app_url") or os.getenv("DEFAULT_APP_URL")
        app_url: str | None = None

        # Determine which directory to boot the dev server from.
        # Passed runs keep their isolated workspace; failed runs tear it down,
        # so fall back to the project's local_path in that case.
        # Resolve a potentially relative workspace path against WORKSPACE_DIR.
        # state.workspace may be stored as a relative path (e.g. "workspace/abc123"),
        # so resolve it before calling os.path.isdir.
        workspace_to_start: str | None = None
        if state.workspace:
            candidate = state.workspace
            if not os.path.isabs(candidate):
                candidate = os.path.join(
                    os.getenv("WORKSPACE_DIR", "./workspace"), os.path.basename(candidate)
                )
            candidate = os.path.abspath(candidate)
            if os.path.isdir(candidate):
                workspace_to_start = candidate

        console.print(
            f"[cyan]verification[/cyan] workspace={workspace_to_start!r}  (raw={state.workspace!r})"
        )
        if not workspace_to_start:
            console.print(
                "[yellow]verification[/yellow] workspace not found — falling back to default URL"
            )

        if workspace_to_start:
            from talon.skills import workspace_starter

            detected_cmd = project_start_command or workspace_starter.detect_start_command(
                workspace_to_start
            )
            console.print(
                f"[cyan]verification[/cyan] workspace: {workspace_to_start}"
                f"  cmd: {detected_cmd or '(none detected)'}"
            )
            await manager.broadcast(
                {
                    "type": "run_log",
                    "issue_id": issue_id,
                    "message": (
                        f"Starting dev server: {detected_cmd or '(auto-detect)'}"
                        f"  in {workspace_to_start}"
                    ),
                }
            )
            try:
                (
                    _server_proc,
                    app_url,
                    _server_port,
                ) = await workspace_starter.start_workspace_server(
                    workspace_to_start,
                    extra_env=project_env_vars,
                    start_command=project_start_command,
                    env_content=project_env_content,
                )
                await manager.broadcast(
                    {
                        "type": "run_log",
                        "issue_id": issue_id,
                        "message": f"Dev server ready at {app_url}",
                    }
                )
            except Exception as _ws_err:
                _err_detail = (
                    f"{type(_ws_err).__name__}: {_ws_err}"
                    if str(_ws_err)
                    else type(_ws_err).__name__
                )
                console.print(f"[yellow]workspace-starter failed: {_err_detail}[/yellow]")
                _user_hint = (
                    " No start command could be detected automatically."
                    if isinstance(_ws_err, ValueError)
                    else " The start command may be wrong for this project."
                )
                state.verification_running = False
                from talon.loop import _save_state as _ss_inner

                _ss_inner(state)
                await manager.broadcast(
                    {
                        "type": "run_state_updated",
                        "issue_id": issue_id,
                        "state": state.model_dump(mode="json"),
                    }
                )
                await manager.broadcast(
                    {
                        "type": "run_error",
                        "issue_id": issue_id,
                        "error": (
                            f"Dev server failed to start: {_err_detail}."
                            f"{_user_hint}"
                            " Set a custom start command in Project Settings → Start Command."
                        ),
                    }
                )
                return

        # Fall back to the configured default URL only when no workspace was found.
        if not app_url:
            app_url = static_url

        if not app_url:
            await manager.broadcast(
                {
                    "type": "run_error",
                    "issue_id": issue_id,
                    "error": (
                        "No application URL configured for verification."
                        " Set DEFAULT_APP_URL or configure the project workspace."
                    ),
                }
            )
            return

        # Warn if no auth credentials are configured — the user should set these before testing.
        if not project_test_user and not project_cookie_file:
            await manager.broadcast(
                {
                    "type": "run_log",
                    "issue_id": issue_id,
                    "message": (
                        "⚠️  No test credentials configured."
                        " If your app requires login, set test_user /"
                        " test_password in project settings."
                    ),
                }
            )

        await manager.broadcast(
            {
                "type": "run_log",
                "issue_id": issue_id,
                "message": f"=== Re-running Browser Verification on {app_url} ===",
            }
        )

        async def _on_browser_progress(partial):
            state.browser_result = partial
            _save_state(state)
            await manager.broadcast(
                {
                    "type": "run_state_updated",
                    "issue_id": issue_id,
                    "state": state.model_dump(mode="json"),
                }
            )

        runs_dir = os.getenv("RUNS_DIR", "./runs")
        browser_result = await browser_validator.run(
            state,
            app_url,
            runs_dir,
            on_progress=_on_browser_progress,
            cookie_file=project_cookie_file,
            test_user=project_test_user,
            test_password=project_test_password,
        )
        if browser_result is not None:
            state.browser_result = browser_result
            state.video_path = browser_result.video_path
        state.verification_running = False
        _save_state(state)

        await manager.broadcast(
            {
                "type": "run_state_updated",
                "issue_id": issue_id,
                "state": state.model_dump(mode="json"),
            }
        )
        await manager.broadcast(
            {
                "type": "run_log",
                "issue_id": issue_id,
                "message": "=== Browser Verification Completed ===",
            }
        )
    except Exception as e:
        console.print(f"[red]Verification error: {e}[/red]")
        await manager.broadcast(
            {"type": "run_error", "issue_id": issue_id, "error": f"Verification failed: {e}"}
        )
    finally:
        if _server_proc is not None and _server_port is not None:
            from talon.skills import workspace_starter as _ws_mod

            await _ws_mod.stop_workspace_server(_server_proc, _server_port)
        # If the task exited before clearing the flag (exception path), clear it now.
        if state is not None and state.verification_running:
            from talon.loop import _save_state as _ss

            state.verification_running = False
            _ss(state)
            await manager.broadcast(
                {
                    "type": "run_state_updated",
                    "issue_id": issue_id,
                    "state": state.model_dump(mode="json"),
                }
            )


@app.post("/api/issues/{issue_id}/verify")
async def verify_issue_run(issue_id: int, background_tasks: BackgroundTasks):
    issue = await db.get_issue(issue_id)
    if not issue or not issue.run_id:
        raise HTTPException(status_code=404, detail="Run not found for issue")
    if issue.status not in ("Done", "Failed"):
        raise HTTPException(
            status_code=400, detail="Cannot run verification until execution is complete."
        )

    background_tasks.add_task(_run_verification_bg, issue_id, issue.run_id)
    return {"status": "verification_started"}


@app.post("/api/issues/{issue_id}/pause")
async def pause_issue_run(issue_id: int):
    issue = await db.get_issue(issue_id)
    if not issue or not issue.run_id:
        raise HTTPException(status_code=404, detail="Run not found for issue")

    runs_dir = Path(os.getenv("RUNS_DIR", "./runs"))
    state_file = runs_dir / issue.run_id / "state.json"
    if not state_file.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {issue.run_id}")

    sentinel = runs_dir / issue.run_id / "pause.signal"
    sentinel.write_text(datetime.utcnow().isoformat(), encoding="utf-8")

    await manager.broadcast(
        {
            "type": "run_log",
            "issue_id": issue_id,
            "message": "--> Pause requested. The agent will pause gracefully after the current iteration completes.",
        }
    )

    return {"status": "paused_signal_sent"}


@app.post("/api/issues/{issue_id}/resume")
async def resume_issue_run(issue_id: int, background_tasks: BackgroundTasks):
    issue = await db.get_issue(issue_id)
    if not issue or not issue.run_id:
        raise HTTPException(status_code=404, detail="Run not found for issue")

    background_tasks.add_task(_resume_loop, issue_id, issue.run_id)
    return {"status": "resuming"}


@app.post("/api/issues/{issue_id}/restart")
async def restart_issue_run(issue_id: int, background_tasks: BackgroundTasks):
    issue = await db.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Trigger a fresh run
    # Set status to Backlog temporarily to clear run_id in the loop
    await db.update_issue(issue_id, db.IssueUpdate(status="Backlog", clear_run_id=True))
    updated = await db.get_issue(issue_id)
    await broadcast_issue_update(issue_id)

    background_tasks.add_task(
        _run_loop,
        f"{updated.title}\n\n{updated.description}",
        "ui",
        updated.id,
        None,
        updated.project_id,
    )
    return {"status": "restarting"}


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
        db.IssueCreate(
            title=title, description=description, status="In Progress", project_id=project_id
        )
    )
    await broadcast_issue_update(issue.id)

    goal = f"{title}\n\n{description}".strip() if description else title
    background_tasks.add_task(_run_loop, goal, "linear", issue.id, None, project_id)
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
        db.IssueCreate(
            title=title, description=body_text, status="In Progress", project_id=project_id
        )
    )
    await broadcast_issue_update(issue.id)

    goal = f"{title}\n\n{body_text}".strip() if body_text else title
    background_tasks.add_task(_run_loop, goal, "github", issue.id, None, project_id)
    return {"ok": True, "triggered": True, "goal": goal[:80]}


# --- UI Serving ---

ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "dist")

if os.path.exists(ui_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(ui_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_ui(full_path: str):
        # API paths that escaped routing (e.g. via path traversal / percent-encoding)
        # must not be silently served as the SPA index.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        path = os.path.join(ui_dir, full_path)
        if os.path.exists(path) and os.path.isfile(path):
            return FileResponse(path)
        return FileResponse(os.path.join(ui_dir, "index.html"))
