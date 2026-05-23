import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiosqlite
from pydantic import BaseModel


def _default_db_path() -> str:
    """Return the platform-appropriate user-data path for the database.

    Precedence: BOARD_DB_PATH env var → platformdirs user_data_dir → ./runs/board.db fallback.
    """
    if env := os.getenv("BOARD_DB_PATH"):
        return env
    try:
        from platformdirs import user_data_dir

        data_dir = Path(user_data_dir("Talon", "Chasqui"))
        data_dir.mkdir(parents=True, exist_ok=True)
        return str(data_dir / "board.db")
    except Exception:
        return "./runs/board.db"


DB_PATH = _default_db_path()


class Project(BaseModel):
    id: int
    name: str
    workspace_mode: str
    selected_repo: Optional[str] = None
    selected_branch: Optional[str] = None
    local_path: Optional[str] = None
    created_at: str
    updated_at: str


class ProjectCreate(BaseModel):
    name: str
    workspace_mode: str = "none"
    selected_repo: Optional[str] = None
    selected_branch: Optional[str] = None
    local_path: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    workspace_mode: Optional[str] = None
    selected_repo: Optional[str] = None
    selected_branch: Optional[str] = None
    local_path: Optional[str] = None


class Issue(BaseModel):
    id: int
    title: str
    description: str
    status: str
    run_id: Optional[str] = None
    project_id: Optional[int] = None
    plan_json: Optional[str] = None
    plan_comments: Optional[str] = None
    created_at: str
    updated_at: str


class IssueCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "Backlog"
    project_id: Optional[int] = None


class IssueUpdate(BaseModel):
    status: Optional[str] = None
    run_id: Optional[str] = None
    clear_run_id: bool = False  # explicitly NULL-out run_id (separate from setting one)
    plan_json: Optional[str] = None
    plan_comments: Optional[str] = None


class SettingsUpdate(BaseModel):
    # Workspace (legacy global; mirrored to default project)
    github_token: Optional[str] = None
    selected_repo: Optional[str] = None
    local_path: Optional[str] = None
    workspace_mode: Optional[str] = None  # "github" | "local" | "none"
    # AI provider API keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    # Model routing
    agent_model: Optional[str] = None
    orchestrator_model: Optional[str] = None
    subagent_model: Optional[str] = None
    reviewer_model: Optional[str] = None
    refiner_model: Optional[str] = None
    # Run limits
    max_iterations: Optional[str] = None
    agent_max_tokens: Optional[str] = None
    reviewer_max_tool_turns: Optional[str] = None
    # Local workspace behaviour
    edit_local_directly: Optional[str] = None  # "true" | "false"
    push_on_pass: Optional[str] = None         # "true" | "false"


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                workspace_mode TEXT NOT NULL DEFAULT 'none',
                selected_repo TEXT,
                local_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                run_id TEXT,
                project_id INTEGER REFERENCES projects(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.commit()

        # Migration: add project_id column to issues if missing (pre-v1 schema)
        try:
            await db.execute("ALTER TABLE issues ADD COLUMN project_id INTEGER REFERENCES projects(id)")
            await db.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        # Migration: add plan_json column to issues if missing
        try:
            await db.execute("ALTER TABLE issues ADD COLUMN plan_json TEXT")
            await db.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        # Migration: add plan_comments column to issues if missing
        try:
            await db.execute("ALTER TABLE issues ADD COLUMN plan_comments TEXT")
            await db.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        # Migration: add selected_branch column to projects if missing
        try:
            await db.execute("ALTER TABLE projects ADD COLUMN selected_branch TEXT")
            await db.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        # Migration: seed default project from global settings when none exist
        async with db.execute("SELECT COUNT(*) FROM projects") as cursor:
            count = (await cursor.fetchone())[0]
        if count == 0:
            now = datetime.utcnow().isoformat()
            async with db.execute(
                "SELECT key, value FROM settings WHERE key IN ('workspace_mode', 'selected_repo', 'local_path')"
            ) as cursor:
                rows = await cursor.fetchall()
            s = {row[0]: row[1] for row in rows}
            cursor = await db.execute(
                "INSERT INTO projects (name, workspace_mode, selected_repo, local_path, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                ("Default", s.get("workspace_mode", "none"), s.get("selected_repo"), s.get("local_path"), now, now),
            )
            default_id = cursor.lastrowid
            await db.execute("UPDATE issues SET project_id = ? WHERE project_id IS NULL", (default_id,))
            await db.commit()


def sync_get_setting(key: str) -> Optional[str]:
    """Synchronous setting read for use in non-async contexts (e.g. skills)."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None
    except sqlite3.OperationalError:
        return None


async def get_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )
        await db.commit()


async def delete_setting(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM settings WHERE key = ?", (key,))
        await db.commit()


async def get_all_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}


# --- Project CRUD ---


async def create_project(p: ProjectCreate) -> Project:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO projects (name, workspace_mode, selected_repo, selected_branch, local_path, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p.name, p.workspace_mode, p.selected_repo, p.selected_branch, p.local_path, now, now),
        )
        await db.commit()
        return await get_project(cursor.lastrowid)


async def get_project(project_id: int) -> Optional[Project]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return Project(**dict(row))
    return None


async def list_projects() -> List[Project]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM projects ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            return [Project(**dict(row)) for row in rows]


async def get_first_project_id() -> Optional[int]:
    """Return the ID of the first project (by creation order), or None if no projects exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM projects ORDER BY id ASC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def update_project(project_id: int, updates: ProjectUpdate) -> Optional[Project]:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        fields = []
        values = []
        if updates.name is not None:
            fields.append("name = ?")
            values.append(updates.name)
        if updates.workspace_mode is not None:
            fields.append("workspace_mode = ?")
            values.append(updates.workspace_mode)
        if updates.selected_repo is not None:
            fields.append("selected_repo = ?")
            values.append(updates.selected_repo or None)  # "" → NULL to allow clearing
        if updates.selected_branch is not None:
            fields.append("selected_branch = ?")
            values.append(updates.selected_branch or None)  # "" → NULL to allow clearing
        if updates.local_path is not None:
            fields.append("local_path = ?")
            values.append(updates.local_path or None)  # "" → NULL to allow clearing
        if not fields:
            return await get_project(project_id)
        fields.append("updated_at = ?")
        values.append(now)
        values.append(project_id)
        await db.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", tuple(values))
        await db.commit()
        return await get_project(project_id)


async def delete_project(project_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM issues WHERE project_id = ?", (project_id,))
        cursor = await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()
        return cursor.rowcount > 0


# --- Issue CRUD ---


async def create_issue(issue: IssueCreate) -> Issue:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO issues (title, description, status, project_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (issue.title, issue.description, issue.status, issue.project_id, now, now),
        )
        await db.commit()
        issue_id = cursor.lastrowid
        return await get_issue(issue_id)


async def get_issue(issue_id: int) -> Optional[Issue]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return Issue(**dict(row))
    return None


async def list_issues(project_id: Optional[int] = None) -> List[Issue]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if project_id is not None:
            async with db.execute(
                "SELECT * FROM issues WHERE project_id = ? ORDER BY updated_at DESC", (project_id,)
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute("SELECT * FROM issues ORDER BY updated_at DESC") as cursor:
                rows = await cursor.fetchall()
        return [Issue(**dict(row)) for row in rows]


async def update_issue(issue_id: int, updates: IssueUpdate) -> Optional[Issue]:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        fields = []
        values = []
        if updates.status is not None:
            fields.append("status = ?")
            values.append(updates.status)
        if updates.clear_run_id:
            fields.append("run_id = ?")
            values.append(None)
        elif updates.run_id is not None:
            fields.append("run_id = ?")
            values.append(updates.run_id)
        if updates.plan_json is not None:
            fields.append("plan_json = ?")
            values.append(updates.plan_json)
        if updates.plan_comments is not None:
            fields.append("plan_comments = ?")
            values.append(updates.plan_comments)

        if not fields:
            return await get_issue(issue_id)

        fields.append("updated_at = ?")
        values.append(now)
        values.append(issue_id)

        query = f"UPDATE issues SET {', '.join(fields)} WHERE id = ?"
        await db.execute(query, tuple(values))
        await db.commit()
        return await get_issue(issue_id)


async def reset_stalled_issues() -> list[int]:
    """At startup, move any 'In Progress' issues to 'Failed'.

    Covers server crash, Ctrl-C, or any other mid-run interruption that left
    the DB in an inconsistent state.  Returns the list of affected issue IDs.
    """
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM issues WHERE status = 'In Progress'"
        ) as cursor:
            rows = await cursor.fetchall()
        stalled_ids = [row[0] for row in rows]
        if stalled_ids:
            await db.execute(
                "UPDATE issues SET status = 'Failed', updated_at = ? WHERE status = 'In Progress'",
                (now,),
            )
            await db.commit()
    return stalled_ids


async def delete_issue(issue_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM issues WHERE id = ?", (issue_id,))
        await db.commit()
        return cursor.rowcount > 0
