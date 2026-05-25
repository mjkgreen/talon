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

import asyncio
import json
import os
import random

from asyncio_throttle import Throttler

_GLOBAL_THROTTLER = Throttler(rate_limit=int(os.getenv("TALON_RPM_LIMIT", "300")), period=60.0)

# Optimize LiteLLM import/startup performance
# (disables slow AWS/Boto3 stream shape checks and telemetry)
os.environ["DISABLE_BOTO3_CHECK"] = "True"
os.environ["LITELLM_TELEMETRY"] = "False"
os.environ["DISABLE_LITELLM_TELEMETRY"] = "True"
os.environ["LITELLM_MODE"] = "production"

import litellm

from talon.providers.base import ProviderResponse, ToolCall, ToolResult

litellm.drop_params = True  # silently drop unsupported params per-provider
litellm.telemetry = False
litellm.turn_off_message_logging = True

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
        response_format: dict | None = None,
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
        if response_format:
            kwargs["response_format"] = response_format

        max_rate_limit_retries = 5
        base_delay = 2.0
        timeout_retried = False
        context_pruned = False
        last_error = None
        
        for attempt in range(max_rate_limit_retries + 1):
            try:
                async with _GLOBAL_THROTTLER:
                    raw = await litellm.acompletion(**kwargs, timeout=timeout)
                break
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_timeout = "timeout" in err_str or isinstance(e, asyncio.TimeoutError) or getattr(e, "status_code", None) == 408
                is_rate_limit = "rate limit" in err_str or "429" in err_str or getattr(e, "status_code", None) == 429
                
                is_context_error = (
                    "context_window" in err_str
                    or "contextwindow" in err_str
                    or "context window" in err_str
                    or "token count exceeds" in err_str
                    or "maximum number of tokens" in err_str
                    or "context_window_exceeded" in err_str
                )
                
                if is_timeout and not timeout_retried and attempt < max_rate_limit_retries:
                    print(f"[LiteLLM] Timeout occurred. Retrying in 5s... ({e})")
                    await asyncio.sleep(5)
                    timeout_retried = True
                    continue
                    
                if is_rate_limit and attempt < max_rate_limit_retries:
                    retry_after = getattr(e, "response", None)
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    if retry_after and hasattr(retry_after, "headers"):
                        retry_val = retry_after.headers.get("Retry-After")
                        if retry_val and retry_val.isdigit():
                            delay = max(delay, int(retry_val))
                    print(f"[LiteLLM] Rate limited. Retrying in {delay:.1f}s... (Attempt {attempt+1}/{max_rate_limit_retries})")
                    await asyncio.sleep(delay)
                    continue
                    
                if is_context_error and len(messages) > 7 and not context_pruned and attempt < max_rate_limit_retries:
                    # Prune older tool result messages in-place to recover.
                    cutoff = len(messages) - 6
                    for i in range(1, cutoff):
                        if messages[i].get("role") == "tool":
                            messages[i] = {
                                "role": "tool",
                                "tool_call_id": messages[i].get("tool_call_id"),
                                "content": "[Tool result truncated to save context window space]",
                            }
                    full_messages = [{"role": "system", "content": system}, *messages]
                    kwargs["messages"] = full_messages
                    context_pruned = True
                    continue
                    
                raise e
        else:
            if last_error:
                raise last_error
                
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
