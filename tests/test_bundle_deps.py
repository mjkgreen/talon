"""
Smoke tests for PyInstaller bundle dependencies.

These tests verify that packages whose data files must be explicitly bundled
actually work. They are cheap to run locally and catch the class of error that
only surfaces in the .exe — where __file__ points to a temp extraction dir
instead of site-packages, so any package that reads files relative to itself
will silently fail.

Run before every release build:
    pytest tests/test_bundle_deps.py -v
"""

from pathlib import Path

import pytest


class TestLitellm:
    def test_model_prices_backup_file_exists(self):
        import litellm

        backup = Path(litellm.__file__).parent / "model_prices_and_context_window_backup.json"
        assert backup.exists(), (
            f"litellm backup pricing file missing: {backup}\n"
            "Fix: add collect_all('litellm') to talon-server.spec datas"
        )

    def test_model_prices_backup_is_valid_json(self):
        import json
        import litellm

        backup = Path(litellm.__file__).parent / "model_prices_and_context_window_backup.json"
        data = json.loads(backup.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and len(data) > 0


class TestTiktoken:
    def test_cl100k_base_encoding_resolves(self):
        """cl100k_base is used by OpenAI and Anthropic model cost calculations."""
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        assert enc is not None

    def test_cl100k_base_can_encode(self):
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode("hello world")
        assert len(tokens) > 0

    def test_tiktoken_ext_importable(self):
        """tiktoken_ext is a separate package containing the actual encoding
        definitions (cl100k_base etc.). Without it bundled, get_encoding() raises
        'Unknown encoding' even though tiktoken itself imports fine."""
        import tiktoken_ext.openai_public  # noqa: F401


class TestCertifi:
    def test_ca_bundle_exists(self):
        """HTTPS calls to AI providers fail if the CA bundle is missing."""
        import certifi

        bundle = Path(certifi.where())
        assert bundle.exists(), (
            f"certifi CA bundle missing: {bundle}\n"
            "Fix: add collect_data_files('certifi') to talon-server.spec datas"
        )

    def test_ca_bundle_non_empty(self):
        import certifi

        assert Path(certifi.where()).stat().st_size > 0


class TestProviderImports:
    """Verify provider packages import cleanly — broken __init__ is caught early."""

    def test_anthropic_importable(self):
        anthropic = pytest.importorskip("anthropic")
        from importlib.metadata import version
        assert version("anthropic")

    def test_openai_importable(self):
        import openai
        from importlib.metadata import version
        assert version("openai")

    def test_litellm_importable(self):
        import litellm  # noqa: F401 — verifies the import doesn't crash
        from importlib.metadata import version
        assert version("litellm")
