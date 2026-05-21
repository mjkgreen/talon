import pytest

from talon.config import _resolution_source, model_config_summary, resolve_model


class TestAutoSelection:
    def test_anthropic_only(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        assert resolve_model("orchestrator") == "anthropic/claude-opus-4-7"
        assert resolve_model("subagent") == "anthropic/claude-sonnet-4-6"
        assert resolve_model("reviewer") == "anthropic/claude-opus-4-7"
        assert resolve_model("refiner") == "anthropic/claude-sonnet-4-6"

    def test_gemini_only(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        assert resolve_model("orchestrator") == "gemini/gemini-flash-latest"
        assert resolve_model("subagent") == "gemini/gemini-flash-latest"
        assert resolve_model("refiner") == "gemini/gemini-flash-latest"

    def test_openai_only(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert resolve_model("orchestrator") == "openai/o3"
        assert resolve_model("subagent") == "openai/gpt-4o"

    def test_no_keys_raises(self):
        with pytest.raises(RuntimeError, match="No LLM API key"):
            resolve_model("orchestrator")

    def test_multi_provider_picks_highest_priority(self, monkeypatch):
        # Both Anthropic and Gemini available — Anthropic wins for orchestrator
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        assert resolve_model("orchestrator") == "anthropic/claude-opus-4-7"


class TestGlobalOverride:
    def test_agent_model_used_for_all_roles(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("AGENT_MODEL", "openai/gpt-4o")
        for role in ["orchestrator", "subagent", "reviewer", "refiner"]:
            assert resolve_model(role) == "openai/gpt-4o"

    def test_agent_model_beats_auto(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("AGENT_MODEL", "gemini/gemini-flash-latest ")
        assert resolve_model("orchestrator") == "gemini/gemini-flash-latest "


class TestPerRoleOverride:
    def test_role_var_beats_agent_model(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("ORCHESTRATOR_MODEL", "openai/o3")
        monkeypatch.setenv("AGENT_MODEL", "gemini/gemini-flash-latest")
        assert resolve_model("orchestrator") == "openai/o3"
        assert resolve_model("subagent") == "gemini/gemini-flash-latest"

    def test_each_role_independently_overridable(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("ORCHESTRATOR_MODEL", "openai/o3")
        monkeypatch.setenv("REFINER_MODEL", "gemini/gemini-flash-latest")
        assert resolve_model("orchestrator") == "openai/o3"
        assert resolve_model("subagent") == "anthropic/claude-sonnet-4-6"
        assert resolve_model("refiner") == "gemini/gemini-flash-latest"


class TestResolutionSource:
    def test_source_per_role_var(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRATOR_MODEL", "openai/o3")
        assert _resolution_source("orchestrator") == "ORCHESTRATOR_MODEL"

    def test_source_agent_model(self, monkeypatch):
        monkeypatch.setenv("AGENT_MODEL", "gemini/gemini-flash-latest")
        assert _resolution_source("subagent") == "AGENT_MODEL"

    def test_source_auto(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        assert _resolution_source("subagent") == "auto"


class TestSummary:
    def test_all_roles_present(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        summary = model_config_summary()
        assert set(summary.keys()) == {"orchestrator", "subagent", "reviewer", "refiner"}

    def test_summary_has_model_and_source(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        for info in model_config_summary().values():
            assert "model" in info
            assert "source" in info
