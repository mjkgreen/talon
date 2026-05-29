"""
Model resolution for each agent role.

Resolution order (first match wins):
  1. {ROLE}_MODEL env var  (e.g. ORCHESTRATOR_MODEL=gemini/gemini-3.1-pro)
  2. AGENT_MODEL           (global fallback — current behaviour preserved)
  3. Auto-select           (scan available API keys, pick best for the role)

To add a new provider: add its API key env var to _PROVIDER_KEYS and add
its models to the priority lists below.
"""

from __future__ import annotations

import os

# Maps provider prefix → the env var that holds its API key
_PROVIDER_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
}

# Env var that holds each role's model override
ROLE_ENV: dict[str, str] = {
    "orchestrator": "ORCHESTRATOR_MODEL",
    "planner": "PLANNER_MODEL",
    "subagent": "SUBAGENT_MODEL",
    "reviewer": "REVIEWER_MODEL",
    "refiner": "REFINER_MODEL",
}

# Per-role priority list: first model whose provider has an API key wins.
# Tuned for what each role actually needs (reasoning vs. coding vs. speed).
ROLE_PRIORITY: dict[str, list[str]] = {
    # Orchestrator: decomposes the goal — needs strong reasoning & planning
    "orchestrator": [
        "openai/o3",
        "anthropic/claude-sonnet-4-6",
        "gemini/gemini-flash-latest",
        "openai/gpt-4o",
        "groq/llama3-70b-8192",
        "mistral/mistral-large-latest",
    ],
    # Planner: workspace exploration + phased plan — speed > max reasoning
    "planner": [
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-4o",
        "gemini/gemini-flash-latest",
        "gemini/gemini-flash-latest",
        "groq/llama3-70b-8192",
        "mistral/mistral-large-latest",
    ],
    # Subagent: writes code with tool-use loop — needs coding strength & speed
    "subagent": [
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-4o",
        "gemini/gemini-flash-latest",
        "mistral/mistral-large-latest",
        "groq/llama3-70b-8192",
        "anthropic/claude-haiku-4-5-20251001",
        "openai/gpt-4o-mini",
    ],
    # Reviewer: strict quality gate — needs thorough analysis, like orchestrator
    "reviewer": [
        "anthropic/claude-sonnet-4-6",
        "openai/o3",
        "openai/gpt-4o",
        "gemini/gemini-flash-latest",
        "groq/llama3-70b-8192",
        "mistral/mistral-large-latest",
    ],
    # Refiner: synthesis task, lighter than orchestrator — speed matters more
    "refiner": [
        "anthropic/claude-sonnet-4-6",
        "gemini/gemini-flash-latest",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "groq/llama3-70b-8192",
        "mistral/mistral-large-latest",
    ],
}


def _provider_of(model: str) -> str:
    return model.split("/")[0] if "/" in model else model


def _available_providers() -> set[str]:
    return {p for p, key in _PROVIDER_KEYS.items() if os.getenv(key)}


def resolve_fallback_models(role: str, primary: str) -> list[str]:
    """Return ordered fallback models for *role*, excluding *primary* and unavailable providers."""
    available = _available_providers()
    return [m for m in ROLE_PRIORITY.get(role, []) if m != primary and _provider_of(m) in available]


def resolve_model(role: str) -> str:
    """
    Return the LiteLLM model string to use for `role`.

    Raises RuntimeError if no API key is configured for any candidate model.
    """
    # 1. Explicit per-role override
    env_var = ROLE_ENV.get(role)
    if env_var:
        explicit = os.getenv(env_var)
        if explicit:
            return explicit

    # 2. Global fallback
    global_model = os.getenv("AGENT_MODEL")
    if global_model:
        return global_model

    # 3. Auto-select from priority list
    available = _available_providers()
    if not available:
        raise RuntimeError(
            "No LLM API key found. Set at least one of: " + ", ".join(_PROVIDER_KEYS.values())
        )
    for model in ROLE_PRIORITY.get(role, []):
        if _provider_of(model) in available:
            return model

    raise RuntimeError(
        f"No model available for role '{role}' given providers: {available}. "
        "Add a model for this role to ROLE_PRIORITY in src/config.py."
    )


def _resolution_source(role: str) -> str:
    """Return a short label describing how the model was chosen (for display)."""
    env_var = ROLE_ENV.get(role)
    if env_var and os.getenv(env_var):
        return env_var
    if os.getenv("AGENT_MODEL"):
        return "AGENT_MODEL"
    return "auto"


def model_config_summary() -> dict[str, dict[str, str]]:
    """Return resolved model + source for each role. Used by loop.py at startup."""
    summary = {}
    for role in ROLE_ENV:
        try:
            summary[role] = {
                "model": resolve_model(role),
                "source": _resolution_source(role),
            }
        except RuntimeError as e:
            summary[role] = {"model": "ERROR", "source": str(e)}
    return summary
