from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from talon.providers.litellm_p import (
    LiteLLMProvider,
    _make_system_message,
    _run_accumulator,
    _to_litellm_tools,
)
from talon.tools import TOOL_DEFINITIONS


class TestToolSchemaConversion:
    def test_count_preserved(self):
        assert len(_to_litellm_tools(TOOL_DEFINITIONS)) == len(TOOL_DEFINITIONS)

    def test_function_type(self):
        for tool in _to_litellm_tools(TOOL_DEFINITIONS):
            assert tool["type"] == "function"

    def test_all_fields_present(self):
        for tool in _to_litellm_tools(TOOL_DEFINITIONS):
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn

    def test_input_schema_becomes_parameters(self):
        converted = _to_litellm_tools(TOOL_DEFINITIONS)
        for orig, conv in zip(TOOL_DEFINITIONS, converted):
            assert conv["function"]["parameters"] == orig["input_schema"]

    def test_all_tool_names_present(self):
        names = {t["function"]["name"] for t in _to_litellm_tools(TOOL_DEFINITIONS)}
        assert names == {"read_file", "write_file", "list_files", "run_command", "search_files"}

    def test_empty_list(self):
        assert _to_litellm_tools([]) == []

    def test_cache_last_adds_cache_control_to_last_tool(self):
        converted = _to_litellm_tools(TOOL_DEFINITIONS, cache_last=True)
        assert converted[-1].get("cache_control") == {"type": "ephemeral"}
        for tool in converted[:-1]:
            assert "cache_control" not in tool

    def test_cache_last_false_adds_no_cache_control(self):
        converted = _to_litellm_tools(TOOL_DEFINITIONS, cache_last=False)
        for tool in converted:
            assert "cache_control" not in tool

    def test_cache_last_empty_list_safe(self):
        assert _to_litellm_tools([], cache_last=True) == []


class TestMakeSystemMessage:
    def test_plain_format_for_non_anthropic(self):
        msg = _make_system_message("Be helpful.", cache=False)
        assert msg["role"] == "system"
        assert msg["content"] == "Be helpful."

    def test_cached_format_is_content_block_list(self):
        msg = _make_system_message("Be helpful.", cache=True)
        assert msg["role"] == "system"
        assert isinstance(msg["content"], list)
        assert len(msg["content"]) == 1
        block = msg["content"][0]
        assert block["type"] == "text"
        assert block["text"] == "Be helpful."
        assert block["cache_control"] == {"type": "ephemeral"}


class TestRunAccumulator:
    @pytest.mark.asyncio
    async def test_accumulates_usage_across_calls(self):
        acc: dict = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
                     "cache_created_tokens": 0, "cost_usd": 0.0}
        token = _run_accumulator.set(acc)
        try:
            provider = LiteLLMProvider("anthropic/claude-haiku-4-5-20251001")

            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 100
            mock_usage.completion_tokens = 50
            mock_usage.cache_read_input_tokens = 80
            mock_usage.cache_creation_input_tokens = 20

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Done"
            mock_response.choices[0].message.tool_calls = None
            mock_response.usage = mock_usage

            with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
                with patch("litellm.completion_cost", return_value=0.005):
                    await provider.chat("sys", [{"role": "user", "content": "hi"}], tools=[])
                    await provider.chat("sys", [{"role": "user", "content": "hi"}], tools=[])

            assert acc["input_tokens"] == 200
            assert acc["output_tokens"] == 100
            assert acc["cache_read_tokens"] == 160
            assert abs(acc["cost_usd"] - 0.01) < 1e-9
        finally:
            _run_accumulator.reset(token)

    @pytest.mark.asyncio
    async def test_no_accumulation_without_active_context(self):
        # With no active accumulator, chat() should still work normally
        provider = LiteLLMProvider("anthropic/claude-haiku-4-5-20251001")

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 25
        mock_usage.cache_read_input_tokens = 0
        mock_usage.cache_creation_input_tokens = 0

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OK"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage = mock_usage

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            with patch("litellm.completion_cost", return_value=0.001):
                resp = await provider.chat("sys", [{"role": "user", "content": "hi"}], tools=[])
        assert resp.text == "OK"


class TestLiteLLMProviderPruning:
    @pytest.mark.asyncio
    async def test_context_window_exceeded_retry_and_pruning(self):

        provider = LiteLLMProvider("test-model")
        messages = [
            {"role": "user", "content": "Initial prompt"},
            {"role": "assistant", "content": "Let me read a file"},
            {"role": "tool", "tool_call_id": "1", "content": "A" * 5000},
            {"role": "assistant", "content": "Let me run a command"},
            {"role": "tool", "tool_call_id": "2", "content": "B" * 5000},
            {"role": "assistant", "content": "Another step"},
            {"role": "tool", "tool_call_id": "3", "content": "C" * 5000},
            {"role": "assistant", "content": "Final step"},
        ]

        # We have 8 messages.
        # len(messages) = 8.
        # cutoff = len(messages) - 6 = 2.
        # Any 'tool' message between index 1 and 2 will be pruned.
        # messages[2] is a tool message, but wait! Index 2 is not < 2.
        # Let's make the list longer to trigger pruning of at least one tool message:
        messages = [
            {"role": "user", "content": "Initial prompt"},
            {"role": "assistant", "content": "Let me read a file"},
            {"role": "tool", "tool_call_id": "1", "content": "A" * 5000},
            {"role": "assistant", "content": "Let me run a command"},
            {"role": "tool", "tool_call_id": "2", "content": "B" * 5000},
            {"role": "assistant", "content": "Another step"},
            {"role": "tool", "tool_call_id": "3", "content": "C" * 5000},
            {"role": "assistant", "content": "Yet another step"},
            {"role": "tool", "tool_call_id": "4", "content": "D" * 5000},
            {"role": "assistant", "content": "Final step"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Success response after pruning"
        mock_response.choices[0].message.tool_calls = None

        # Mock acompletion to raise error first, then succeed
        side_effects = [
            Exception("ContextWindowExceeded: The input token count exceeds limit"),
            mock_response,
        ]

        with patch(
            "litellm.acompletion", new_callable=AsyncMock, side_effect=side_effects
        ) as mock_acompletion:
            resp = await provider.chat("System instructions", messages, tools=[])
            assert resp.text == "Success response after pruning"
            assert mock_acompletion.call_count == 2

            # Assert that the messages are pruned in-place.
            # Index 2 (tool_call_id="1") is truncated: 2 < cutoff (len - 6 = 4).
            # Index 4 (tool_call_id="2") is NOT truncated: 4 is not < 4.
            assert "truncated to save context window space" in messages[2]["content"]
            assert messages[4]["content"] == "B" * 5000
