"""
Shared types and protocol for LLM providers.

Both AnthropicProvider and OpenAIProvider implement BaseProvider so that
skills are provider-agnostic. The only provider-specific details are:
  - how messages are appended to history (format differs)
  - how tool schemas are converted (Anthropic input_schema vs OpenAI parameters)
  - prompt caching (Anthropic-only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ToolResult:
    id: str
    content: str  # JSON string from dispatch_tool


@dataclass
class ProviderResponse:
    text: str | None  # populated when stop_reason == "end_turn"
    tool_calls: list[ToolCall]  # populated when stop_reason == "tool_use"
    stop_reason: str  # "end_turn" | "tool_use" | "error"
    raw: Any = field(repr=False)  # original SDK response for debugging
    usage: dict | None = None  # token counts and cost, if available


@runtime_checkable
class BaseProvider(Protocol):
    async def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
        response_format: dict | None = None,
    ) -> ProviderResponse:
        """Single API call. Returns a normalized ProviderResponse."""
        ...

    def append_assistant(self, messages: list[dict], response: ProviderResponse) -> None:
        """Append the assistant turn to messages in provider-native format."""
        ...

    def append_tool_results(self, messages: list[dict], results: list[ToolResult]) -> None:
        """Append tool results to messages in provider-native format."""
        ...
