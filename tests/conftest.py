import pytest


@pytest.fixture(autouse=True)
def clear_model_env(monkeypatch):
    """Wipe all provider API keys and model overrides before each test."""
    for key in [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "GROQ_API_KEY", "MISTRAL_API_KEY", "COHERE_API_KEY",
        "AGENT_MODEL", "ORCHESTRATOR_MODEL", "SUBAGENT_MODEL",
        "REVIEWER_MODEL", "REFINER_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)
