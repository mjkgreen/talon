"""
Provider factory.

Model is selected via AGENT_MODEL in .env using LiteLLM's provider-prefix format:
  anthropic/claude-sonnet-4-6    ANTHROPIC_API_KEY
  openai/gpt-4o                  OPENAI_API_KEY
  gemini/gemini-2.0-flash        GEMINI_API_KEY
  groq/llama3-70b-8192           GROQ_API_KEY

Full model list: https://docs.litellm.ai/docs/providers
"""
from __future__ import annotations

import os

from src.providers.base import BaseProvider
from src.providers.litellm_p import LiteLLMProvider


def get_provider() -> BaseProvider:
    model = os.getenv("AGENT_MODEL", "anthropic/claude-sonnet-4-6")
    return LiteLLMProvider(model=model)
