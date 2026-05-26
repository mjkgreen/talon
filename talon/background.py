"""
Background task functions for the Talon server.
Handles the autonomous loop, planner, and plan-refiner background tasks.
"""

from __future__ import annotations

import asyncio
import json
import os
import traceback
from pathlib import Path

from rich.console import Console

from talon import db

console = Console()

MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_RUNS", "3"))

_semaphore: asyncio.Semaphore | None = None
_planning_issues: set[int] = set()


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


def _has_llm_configured() -> bool:
    keys = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
    ]
    return any(os.getenv(k) for k in keys)


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


def _reset_stalled_verifications() -> None:
    """Find all run states on disk and reset `verification_running` to False if stuck as True."""
    import json as _json

    from rich.console import Console as _Console

    _console = _Console()
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
                            data = _json.load(f)
                        if isinstance(data, dict) and data.get("verification_running"):
                            _console.print(
                                f"[yellow]Resetting stalled verification_running"
                                f" for run: {run_id}[/yellow]"
                            )
                            data["verification_running"] = False
                            with open(state_file, "w", encoding="utf-8") as f:
                                _json.dump(data, f, indent=2)
                    except _json.JSONDecodeError:
                        continue
                    except Exception as e:
                        _console.print(
                            f"[red]Error resetting stalled verification run {run_id}: {e}[/red]"
                        )


async def _run_planner_bg(issue_id: int, goal: str) -> None:
    from talon.routers.websocket import manager

    _planning_issues.add(issue_id)
    await manager.broadcast({"type": "plan_started", "issue_id": issue_id})
    try:
        from talon.skills.planner import run as planner_run

        plan = await planner_run(goal=goal)
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
    from talon.routers.websocket import manager

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


async def _run_loop(
    goal: str,
    source: str,
    issue_id: int | None = None,
    working_dir: str | None = None,
    project_id: int | None = None,
) -> None:
    from talon.routers.websocket import broadcast_issue_update, manager

    sem = _get_semaphore()
    if sem.locked():
        console.print(f"[yellow]Webhook queued (at concurrency limit): {goal[:60]}[/yellow]")

    if issue_id:
        await db.update_issue(issue_id, db.IssueUpdate(status="In Progress"))
        await broadcast_issue_update(issue_id)

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
                        {"type": "run_log", "issue_id": issue_id, "message": message}
                    )

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
            create_pr = push_on_pass_setting != "false"

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
                        {"type": "run_error", "issue_id": issue_id, "error": str(e)}
                    )
                except Exception:
                    pass
                await db.update_issue(issue_id, db.IssueUpdate(status="Failed"))
                await broadcast_issue_update(issue_id)


async def _resume_loop(issue_id: int, run_id: str) -> None:
    from talon.routers.websocket import broadcast_issue_update, manager

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
    from talon.routers.websocket import manager

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

        if not project_test_user and not project_cookie_file:
            await manager.broadcast(
                {
                    "type": "run_log",
                    "issue_id": issue_id,
                    "message": (
                        "No test credentials configured."
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
