"""
Anthropic provider — wraps the Anthropic SDK.

Uses prompt caching (cache_control: ephemeral) on system prompts to cut cost
on repeated iterations within the same run.
"""
from __future__ import annotations

import asyncio
import os

import anthropic

from src.providers.base import BaseProvider, ProviderResponse, ToolCall, ToolResult

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))


class AnthropicProvider:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = MAX_TOKENS,
    ) -> ProviderResponse:
        kwargs: dict = dict(
            model=MODEL,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools

        raw = await asyncio.to_thread(self._client.messages.create, **kwargs)

        text: str | None = None
        tool_calls: list[ToolCall] = []

        for block in raw.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))
            elif hasattr(block, "text"):
                text = block.text

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return ProviderResponse(text=text, tool_calls=tool_calls, stop_reason=stop_reason, raw=raw)

    def append_assistant(self, messages: list[dict], response: ProviderResponse) -> None:
        # Anthropic expects the raw content block list as the assistant message
        messages.append({"role": "assistant", "content": response.raw.content})

    def append_tool_results(self, messages: list[dict], results: list[ToolResult]) -> None:
        messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r.id, "content": r.content}
                for r in results
            ],
        })
