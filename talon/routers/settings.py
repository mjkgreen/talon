from __future__ import annotations

import os

from fastapi import APIRouter

from talon import db

router = APIRouter()

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


def _has_llm_configured() -> bool:
    keys = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
    ]
    return any(os.getenv(k) for k in keys)


async def apply_db_settings_to_env() -> None:
    """Load AI/model settings from DB into os.environ.

    DB-stored values fill in missing env vars only — system env always takes precedence.
    """
    settings = await db.get_all_settings()
    for db_key, env_key in _DB_TO_ENV.items():
        value = settings.get(db_key)
        if value:
            os.environ[env_key] = value


@router.get("/api/settings")
async def get_settings():
    settings = await db.get_all_settings()
    for key in _API_KEY_SETTINGS | {"github_token"}:
        if settings.get(key):
            settings[key] = "***" + settings[key][-4:]
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


@router.post("/api/settings")
async def update_settings(updates: db.SettingsUpdate):
    if updates.github_token and not updates.github_token.startswith("***"):
        await db.set_setting("github_token", updates.github_token)

    if updates.selected_repo is not None:
        await db.set_setting("selected_repo", updates.selected_repo)
    if updates.local_path is not None:
        await db.set_setting("local_path", updates.local_path)
    if updates.workspace_mode is not None:
        await db.set_setting("workspace_mode", updates.workspace_mode)

    if updates.edit_local_directly is not None:
        await db.set_setting("edit_local_directly", updates.edit_local_directly)
    if updates.push_on_pass is not None:
        await db.set_setting("push_on_pass", updates.push_on_pass)

    for db_key, env_key in _DB_TO_ENV.items():
        val = getattr(updates, db_key, None)
        if val is None:
            continue
        if val == "":
            await db.delete_setting(db_key)
            os.environ.pop(env_key, None)
        elif db_key in _API_KEY_SETTINGS and val.startswith("***"):
            pass
        else:
            await db.set_setting(db_key, val)
            os.environ[env_key] = val

    return {"ok": True}
