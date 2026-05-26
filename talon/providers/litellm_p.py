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

Optimizations:
  - Anthropic prompt caching on system prompt and tool schemas (cache_control)
  - asyncio-throttle rate limiting (AGENT_LLM_RATE_LIMIT calls/sec, 0 = off)
  - Per-call token/cost logging
"""

from __future__ import annotations

import json
import os

# Optimize LiteLLM import/startup performance
# (disables slow AWS/Boto3 stream shape checks and telemetry)
os.environ["DISABLE_BOTO3_CHECK"] = "True"
os.environ["LITELLM_TELEMETRY"] = "False"
os.environ["DISABLE_LITELLM_TELEMETRY"] = "True"
os.environ["LITELLM_MODE"] = "production"

import litellm
from asyncio_throttle import Throttler

from talon.providers.base import ProviderResponse, ToolCall, ToolResult

litellm.drop_params = True  # silently drop unsupported params per-provider
litellm.telemetry = False
litellm.turn_off_message_logging = True

_DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 8096

# Rate limiter — shared across all provider instances.
# Set AGENT_LLM_RATE_LIMIT=N to cap at N LLM calls/second (0 = disabled).
_RATE_LIMIT = int(os.getenv("AGENT_LLM_RATE_LIMIT", "0"))
_THROTTLER: Throttler | None = Throttler(rate_limit=_RATE_LIMIT, period=1) if _RATE_LIMIT > 0 else None


def _to_litellm_tools(tools: list[dict], cache_last: bool = False) -> list[dict]:
    """Convert Anthropic-format tool schemas to OpenAI/LiteLLM function format.

    When cache_last=True, marks the final tool with Anthropic cache_control so
    the entire tool block is eligible for prompt caching.
    """
    converted = [
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
    if cache_last and converted:
        converted[-1]["cache_control"] = {"type": "ephemeral"}
    return converted


def _make_system_message(system: str, cache: bool) -> dict:
    """Build the system entry for the messages list.

    When cache=True (Anthropic models), wraps the text in a content-block list
    with cache_control so the system prompt is eligible for prompt caching.
    """
    if cache:
        return {
            "role": "system",
            "content": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        }
    return {"role": "system", "content": system}


def _extract_usage(raw) -> dict | None:
    """Pull token counts and estimated cost from a LiteLLM ModelResponse."""
    usage = getattr(raw, "usage", None)
    if not usage:
        return None
    result: dict = {
        "input_tokens": getattr(usage, "prompt_tokens", 0),
        "output_tokens": getattr(usage, "completion_tokens", 0),
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0),
        "cache_created_tokens": getattr(usage, "cache_creation_input_tokens", 0),
    }
    try:
        result["cost_usd"] = litellm.completion_cost(raw)
    except Exception:
        result["cost_usd"] = None
    return result


class LiteLLMProvider:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> ProviderResponse:
        # Read env at call time so live changes from the Settings UI take effect
        # without restarting the server.
        model = self._model or os.getenv("AGENT_MODEL", _DEFAULT_MODEL)
        if max_tokens is None:
            max_tokens = int(os.getenv("AGENT_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS)))
        timeout = int(os.getenv("AGENT_LLM_TIMEOUT_SECS", "120"))

        is_anthropic = model.startswith("anthropic/")
        system_msg = _make_system_message(system, cache=is_anthropic)
        full_messages = [system_msg, *messages]

        tools_converted = _to_litellm_tools(tools, cache_last=is_anthropic) if tools else []

        kwargs: dict = dict(model=model, messages=full_messages, max_tokens=max_tokens)
        if tools_converted:
            kwargs["tools"] = tools_converted
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format

        try:
            if _THROTTLER:
                async with _THROTTLER:
                    raw = await litellm.acompletion(**kwargs, timeout=timeout)
            else:
                raw = await litellm.acompletion(**kwargs, timeout=timeout)
        except Exception as e:
            err_str = str(e).lower()
            is_context_error = (
                "context_window" in err_str
                or "contextwindow" in err_str
                or "context window" in err_str
                or "token count exceeds" in err_str
                or "maximum number of tokens" in err_str
                or "context_window_exceeded" in err_str
            )
            if is_context_error and len(messages) > 6:
                # Prune older tool result messages in-place to recover.
                cutoff = len(messages) - 6
                for i in range(1, cutoff):
                    if messages[i].get("role") == "tool":
                        messages[i] = {
                            "role": "tool",
                            "tool_call_id": messages[i].get("tool_call_id"),
                            "content": "[Tool result truncated to save context window space]",
                        }
                full_messages = [system_msg, *messages]
                kwargs["messages"] = full_messages
                if _THROTTLER:
                    async with _THROTTLER:
                        raw = await litellm.acompletion(**kwargs, timeout=timeout)
                else:
                    raw = await litellm.acompletion(**kwargs, timeout=timeout)
            else:
                raise e

        msg = raw.choices[0].message
        usage_data = _extract_usage(raw)

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
        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw=raw,
            usage=usage_data,
        )

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
