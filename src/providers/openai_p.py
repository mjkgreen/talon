"""
OpenAI provider — wraps the OpenAI SDK.

Converts Anthropic-format tool schemas (input_schema) to OpenAI format
(parameters) so that src/tools.py TOOL_DEFINITIONS work unchanged.

Message history is built in OpenAI format:
  assistant with tool calls → role=assistant, tool_calls=[...]
  tool results             → role=tool, tool_call_id=...
"""
from __future__ import annotations

import asyncio
import json
import os

from src.providers.base import BaseProvider, ProviderResponse, ToolCall, ToolResult

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool schema format to OpenAI function format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


class OpenAIProvider:
    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            ) from e
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = MAX_TOKENS,
    ) -> ProviderResponse:
        # OpenAI puts the system prompt as the first message
        full_messages = [{"role": "system", "content": system}, *messages]

        kwargs: dict = dict(
            model=MODEL,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        if tools:
            kwargs["tools"] = _to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"

        raw = await asyncio.to_thread(self._client.chat.completions.create, **kwargs)

        msg = raw.choices[0].message
        text: str | None = msg.content or None
        tool_calls: list[ToolCall] = []

        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                ))

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return ProviderResponse(text=text, tool_calls=tool_calls, stop_reason=stop_reason, raw=raw)

    def append_assistant(self, messages: list[dict], response: ProviderResponse) -> None:
        msg = response.raw.choices[0].message
        entry: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(entry)

    def append_tool_results(self, messages: list[dict], results: list[ToolResult]) -> None:
        for r in results:
            messages.append({"role": "tool", "tool_call_id": r.id, "content": r.content})
