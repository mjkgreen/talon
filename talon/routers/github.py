from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from talon import db
from talon.routers.websocket import broadcast_issue_update

router = APIRouter()


@router.get("/api/github/repos")
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


@router.get("/api/github/repos/{owner}/{repo}/branches")
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


@router.post("/api/github/sync")
async def sync_github_issues(project_id: Optional[int] = Query(default=None)):
    token = await db.get_setting("github_token")
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
