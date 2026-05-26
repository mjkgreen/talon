"""
Background task functions for the Talon server.
Handles the autonomous loop, planner, and plan-refiner background tasks.
"""

from __future__ import annotations

import asyncio
import json
import os
import traceback

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
