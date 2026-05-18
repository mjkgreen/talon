import os
import sqlite3
from datetime import datetime
from typing import List, Optional

import aiosqlite
from pydantic import BaseModel

DB_PATH = os.getenv("BOARD_DB_PATH", "./runs/board.db")


class Issue(BaseModel):
    id: int
    title: str
    description: str
    status: str
    run_id: Optional[str]
    created_at: str
    updated_at: str


class IssueCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "Backlog"


class IssueUpdate(BaseModel):
    status: Optional[str] = None
    run_id: Optional[str] = None


class SettingsUpdate(BaseModel):
    github_token: Optional[str] = None
    selected_repo: Optional[str] = None
    local_path: Optional[str] = None
    workspace_mode: Optional[str] = None  # "github" | "local" | "none"


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                run_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()


def sync_get_setting(key: str) -> Optional[str]:
    """Synchronous setting read for use in non-async contexts (e.g. skills)."""
    if not os.path.exists(DB_PATH):
        return None
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None


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


async def get_all_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}


async def create_issue(issue: IssueCreate) -> Issue:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO issues (title, description, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (issue.title, issue.description, issue.status, now, now),
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


async def list_issues() -> List[Issue]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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
        if updates.run_id is not None:
            fields.append("run_id = ?")
            values.append(updates.run_id)

        if not fields:
            return await get_issue(issue_id)

        fields.append("updated_at = ?")
        values.append(now)
        values.append(issue_id)

        query = f"UPDATE issues SET {', '.join(fields)} WHERE id = ?"
        await db.execute(query, tuple(values))
        await db.commit()
        return await get_issue(issue_id)


async def delete_issue(issue_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM issues WHERE id = ?", (issue_id,))
        await db.commit()
        return cursor.rowcount > 0
