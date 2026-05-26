from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from talon import db
from talon.background import (
    _has_llm_configured,
    _resume_loop,
    _run_loop,
    _run_plan_refiner_bg,
    _run_planner_bg,
    _run_verification_bg,
)
from talon.routers.websocket import broadcast_issue_update

router = APIRouter()


class _PlanUpdate(BaseModel):
    plan_json: str


class _CommentAdd(BaseModel):
    comment: str


@router.get("/api/issues")
async def get_issues(project_id: int | None = None):
    return await db.list_issues(project_id=project_id)


@router.post("/api/issues")
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


@router.patch("/api/issues/{issue_id}/plan")
async def update_issue_plan(issue_id: int, body: _PlanUpdate):
    issue = await db.update_issue(issue_id, db.IssueUpdate(plan_json=body.plan_json))
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    await broadcast_issue_update(issue_id)
    return issue


@router.post("/api/issues/{issue_id}/plan/comments")
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


@router.post("/api/issues/{issue_id}/plan/refine")
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


@router.patch("/api/issues/{issue_id}")
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


@router.post("/api/issues/{issue_id}/plan/regenerate")
async def regenerate_issue_plan(issue_id: int, background_tasks: BackgroundTasks):
    issue = await db.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not _has_llm_configured():
        raise HTTPException(status_code=400, detail="No LLM configured")
    goal = f"{issue.title}\n\n{issue.description}".strip()
    # Clear comments and regenerate plan from scratch
    await db.update_issue(issue_id, db.IssueUpdate(plan_comments="[]"))
    background_tasks.add_task(_run_planner_bg, issue_id, goal)
    return {"ok": True}


@router.post("/api/issues/{issue_id}/pause")
async def pause_issue_run(issue_id: int):
    from talon.routers.websocket import manager

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


@router.post("/api/issues/{issue_id}/resume")
async def resume_issue_run(issue_id: int, background_tasks: BackgroundTasks):
    issue = await db.get_issue(issue_id)
    if not issue or not issue.run_id:
        raise HTTPException(status_code=404, detail="Run not found for issue")

    background_tasks.add_task(_resume_loop, issue_id, issue.run_id)
    return {"status": "resuming"}


@router.post("/api/issues/{issue_id}/restart")
async def restart_issue_run(issue_id: int, background_tasks: BackgroundTasks):
    issue = await db.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

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


@router.post("/api/issues/{issue_id}/verify")
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


@router.delete("/api/issues/{issue_id}")
async def delete_issue(issue_id: int):
    from talon.routers.websocket import manager

    deleted = await db.delete_issue(issue_id)
    if deleted:
        await manager.broadcast({"type": "issue_deleted", "issue_id": issue_id})
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Issue not found")
