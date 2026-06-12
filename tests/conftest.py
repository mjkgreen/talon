import pytest


@pytest.fixture(autouse=True)
def clear_model_env(monkeypatch):
    """Wipe all provider API keys and model overrides before each test."""
    for key in [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "AGENT_MODEL",
        "ORCHESTRATOR_MODEL",
        "SUBAGENT_MODEL",
        "REVIEWER_MODEL",
        "REFINER_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def reset_webhook_secrets(monkeypatch):
    """Reset webhook module-level secrets before each test.

    browser_use calls load_dotenv() at import time, which sets WEBHOOK secrets
    from .env before talon.routers.webhooks is imported (so they get baked into
    the module constants). test_bad_signature_rejected also reloads the module
    while secrets are set, leaving them dirty for subsequent tests.
    Patching the module attributes directly is the only reliable fix.
    """
    try:
        import talon.routers.webhooks as wh

        monkeypatch.setattr(wh, "LINEAR_SECRET", "")
        monkeypatch.setattr(wh, "GITHUB_SECRET", "")
    except ImportError:
        pass
