"""
LiteLLM provider — unified interface for any model via litellm.acompletion().

Switch models by setting AGENT_MODEL in .env:
  anthropic/claude-sonnet-4-6    → Anthropic (needs ANTHROPIC_API_KEY)
  openai/gpt-4o                  → OpenAI    (needs OPENAI_API_KEY)
  gemini/gemini-flash-latest     → Gemini    (needs GEMINI_API_KEY)
  groq/llama3-70b-8192           → Groq      (needs GROQ_API_KEY)
  mistral/mistral-large-latest   → Mistral   (needs MISTRAL_API_KEY)

LiteLLM reads each provider's API key from the standard env var automatically.
Tool schemas are converted from Anthropic format (input_schema) to
OpenAI/LiteLLM format (parameters) since that is the common wire format.
"""

from __future__ import annotations

import json
import os

import litellm

from talon.providers.base import ProviderResponse, ToolCall, ToolResult

litellm.drop_params = True  # silently drop unsupported params per-provider

_DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 8096


def _to_litellm_tools(tools: list[dict]) -> list[dict]:
    """Convert Anthropic-format tool schemas to OpenAI/LiteLLM function format."""
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


class LiteLLMProvider:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        # Read env at call time so live changes from the Settings UI take effect
        # without restarting the server.
        model = self._model or os.getenv("AGENT_MODEL", _DEFAULT_MODEL)
        if max_tokens is None:
            max_tokens = int(os.getenv("AGENT_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS)))
        timeout = int(os.getenv("AGENT_LLM_TIMEOUT_SECS", "120"))

        full_messages = [{"role": "system", "content": system}, *messages]
        kwargs: dict = dict(model=model, messages=full_messages, max_tokens=max_tokens)
        if tools:
            kwargs["tools"] = _to_litellm_tools(tools)
            kwargs["tool_choice"] = "auto"

        raw = await litellm.acompletion(**kwargs, timeout=timeout)
        msg = raw.choices[0].message

        text: str | None = msg.content or None
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        input=json.loads(tc.function.arguments),
                    )
                )

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
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(entry)

    def append_tool_results(self, messages: list[dict], results: list[ToolResult]) -> None:
        for r in results:
            messages.append({"role": "tool", "tool_call_id": r.id, "content": r.content})
