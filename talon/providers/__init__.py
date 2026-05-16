"""
Provider factory.

  get_provider(role)  →  LiteLLMProvider configured for that role's model.

Model resolution is handled by src.config.resolve_model — see that module
for the full priority/override logic.
"""

from __future__ import annotations

from talon.config import resolve_model
from talon.providers.base import BaseProvider
from talon.providers.litellm_p import LiteLLMProvider


def get_provider(role: str = "subagent") -> BaseProvider:
    model = resolve_model(role)
    return LiteLLMProvider(model=model)
