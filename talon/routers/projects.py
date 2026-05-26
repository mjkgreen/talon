from __future__ import annotations

from fastapi import APIRouter, HTTPException

from talon import db
from talon.routers.websocket import manager

router = APIRouter()


@router.get("/api/projects")
async def list_projects():
    return await db.list_projects()


@router.post("/api/projects")
async def create_project(p: db.ProjectCreate):
    project = await db.create_project(p)
    await manager.broadcast({"type": "project_created", "project": project.model_dump()})
    return project


@router.patch("/api/projects/{project_id}")
async def update_project(project_id: int, updates: db.ProjectUpdate):
    project = await db.update_project(project_id, updates)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await manager.broadcast({"type": "project_updated", "project": project.model_dump()})
    return project


@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    all_projects = await db.list_projects()
    if len(all_projects) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last project")
    deleted = await db.delete_project(project_id)
    if deleted:
        await manager.broadcast({"type": "project_deleted", "project_id": project_id})
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Project not found")
