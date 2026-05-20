"""Tests for talon/db.py — project CRUD, migration, list_issues filtering, helpers."""

import os
import tempfile

import pytest

import talon.db as db
from talon.server import _has_llm_configured


@pytest.fixture(autouse=True)
async def isolated_db(tmp_path, monkeypatch):
    """Point DB_PATH at a fresh temp file for every test."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", db_file)
    await db.init_db()
    yield


# ── Project CRUD ──────────────────────────────────────────────────────────────


async def test_create_and_get_project():
    p = await db.create_project(db.ProjectCreate(name="Alpha", workspace_mode="none"))
    assert p.id is not None
    assert p.name == "Alpha"
    assert p.workspace_mode == "none"

    fetched = await db.get_project(p.id)
    assert fetched is not None
    assert fetched.id == p.id


async def test_list_projects():
    await db.create_project(db.ProjectCreate(name="P1", workspace_mode="none"))
    await db.create_project(db.ProjectCreate(name="P2", workspace_mode="github"))
    projects = await db.list_projects()
    # migration seeds "Default" project, so we have 3 total
    names = [p.name for p in projects]
    assert "P1" in names
    assert "P2" in names


async def test_update_project():
    p = await db.create_project(db.ProjectCreate(name="Beta", workspace_mode="none"))
    updated = await db.update_project(p.id, db.ProjectUpdate(name="Beta-v2", workspace_mode="local"))
    assert updated.name == "Beta-v2"
    assert updated.workspace_mode == "local"


async def test_update_project_clear_string_fields():
    p = await db.create_project(
        db.ProjectCreate(name="C", workspace_mode="github", selected_repo="org/repo")
    )
    # clear selected_repo by passing empty string
    updated = await db.update_project(p.id, db.ProjectUpdate(selected_repo=""))
    assert updated.selected_repo is None


async def test_delete_project():
    p = await db.create_project(db.ProjectCreate(name="ToDelete", workspace_mode="none"))
    # seed a second project so the delete succeeds (first is Default from migration)
    result = await db.delete_project(p.id)
    assert result is True
    assert await db.get_project(p.id) is None


async def test_get_project_not_found():
    result = await db.get_project(99999)
    assert result is None


# ── Issue list filtering ───────────────────────────────────────────────────────


async def test_list_issues_filtered_by_project():
    p1 = await db.create_project(db.ProjectCreate(name="P1", workspace_mode="none"))
    p2 = await db.create_project(db.ProjectCreate(name="P2", workspace_mode="none"))

    await db.create_issue(db.IssueCreate(title="Task A", project_id=p1.id))
    await db.create_issue(db.IssueCreate(title="Task B", project_id=p2.id))

    issues_p1 = await db.list_issues(project_id=p1.id)
    assert len(issues_p1) == 1
    assert issues_p1[0].title == "Task A"

    issues_p2 = await db.list_issues(project_id=p2.id)
    assert len(issues_p2) == 1
    assert issues_p2[0].title == "Task B"


async def test_list_issues_no_filter_returns_all():
    p = await db.create_project(db.ProjectCreate(name="P", workspace_mode="none"))
    await db.create_issue(db.IssueCreate(title="T1", project_id=p.id))
    await db.create_issue(db.IssueCreate(title="T2", project_id=p.id))
    all_issues = await db.list_issues()
    assert len(all_issues) >= 2


# ── Migration: Default project seeding ────────────────────────────────────────


async def test_migration_seeds_default_project():
    projects = await db.list_projects()
    assert len(projects) >= 1
    assert projects[0].name == "Default"


async def test_get_first_project_id():
    first_id = await db.get_first_project_id()
    assert first_id is not None
    projects = await db.list_projects()
    assert first_id == projects[0].id


# ── Settings helpers ──────────────────────────────────────────────────────────


async def test_delete_setting():
    await db.set_setting("foo", "bar")
    assert await db.get_setting("foo") == "bar"
    await db.delete_setting("foo")
    assert await db.get_setting("foo") is None


# ── _has_llm_configured ───────────────────────────────────────────────────────


def test_has_llm_configured_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert _has_llm_configured() is True


def test_has_llm_configured_without_keys(monkeypatch):
    for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"]:
        monkeypatch.delenv(k, raising=False)
    assert _has_llm_configured() is False


def test_has_llm_configured_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert _has_llm_configured() is True
