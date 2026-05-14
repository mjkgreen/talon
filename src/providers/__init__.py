"""
Provider factory. Select via AGENT_PROVIDER env var.

  AGENT_PROVIDER=anthropic  (default) → AnthropicProvider (with prompt caching)
  AGENT_PROVIDER=openai               → OpenAIProvider    (gpt-4o / o3)
"""
from __future__ import annotations

import os

from src.providers.base import BaseProvider


def get_provider() -> BaseProvider:
    name = os.getenv("AGENT_PROVIDER", "anthropic").lower().strip()
    if name == "openai":
        from src.providers.openai_p import OpenAIProvider
        return OpenAIProvider()
    from src.providers.anthropic_p import AnthropicProvider
    return AnthropicProvider()
