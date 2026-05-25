"""Tests for the browser_validator skill."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from talon.types import BrowserAssertion, BrowserTestResult, RunState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_call(tc_id: str, tc_name: str, tc_input: dict):
    """Create a mock tool call with explicit attribute assignment (MagicMock `name` param is reserved)."""
    tc = MagicMock()
    tc.id = tc_id
    tc.name = tc_name
    tc.input = tc_input
    return tc


def _make_page(
    url: str = "http://localhost:8080/",
    title: str = "Test Page",
    body_text: str = "Hello World",
    inner_html: str = "<body>Hello World</body>",
    locator_count: int = 1,
    locator_text: str = "Hello World",
):
    page = AsyncMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.inner_text = AsyncMock(return_value=body_text)
    page.content = AsyncMock(return_value=inner_html)
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.select_option = AsyncMock()
    page.screenshot = AsyncMock()

    locator = AsyncMock()
    locator.count = AsyncMock(return_value=locator_count)
    locator.first = AsyncMock()
    locator.first.inner_text = AsyncMock(return_value=locator_text)
    page.locator = MagicMock(return_value=locator)

    return page


# ---------------------------------------------------------------------------
# Unit tests: _dispatch_browser_tool
# ---------------------------------------------------------------------------


class TestDispatchBrowserTool:
    @pytest.mark.asyncio
    async def test_navigate_returns_url_and_title(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page(url="http://localhost/", title="My App")
        result_str, is_done = await _dispatch_browser_tool(
            "navigate", {"url": "http://localhost/"}, page, tmp_path, [], [], [0]
        )
        assert is_done is False
        data = json.loads(result_str)
        assert data["title"] == "My App"
        assert data["url"] == "http://localhost/"

    @pytest.mark.asyncio
    async def test_assert_element_pass(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page(locator_count=1, locator_text="Welcome")
        assertions: list[BrowserAssertion] = []
        result_str, is_done = await _dispatch_browser_tool(
            "assert_element",
            {"selector": "h1", "description": "Heading exists", "expected_text": "welcome"},
            page,
            tmp_path,
            assertions,
            [],
            [0],
        )
        assert is_done is False
        assert len(assertions) == 1
        assert assertions[0].passed is True

    @pytest.mark.asyncio
    async def test_assert_element_fail_not_found(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page(locator_count=0)
        assertions: list[BrowserAssertion] = []
        await _dispatch_browser_tool(
            "assert_element",
            {"selector": "#missing", "description": "Should exist"},
            page,
            tmp_path,
            assertions,
            [],
            [0],
        )
        assert assertions[0].passed is False
        assert assertions[0].actual == "element not found"

    @pytest.mark.asyncio
    async def test_assert_url_pass(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page(url="http://localhost:8080/health")
        assertions: list[BrowserAssertion] = []
        await _dispatch_browser_tool(
            "assert_url",
            {"description": "Health endpoint", "expected_pattern": "/health"},
            page,
            tmp_path,
            assertions,
            [],
            [0],
        )
        assert assertions[0].passed is True

    @pytest.mark.asyncio
    async def test_assert_url_fail(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page(url="http://localhost:8080/")
        assertions: list[BrowserAssertion] = []
        await _dispatch_browser_tool(
            "assert_url",
            {"description": "Health endpoint", "expected_pattern": "/health"},
            page,
            tmp_path,
            assertions,
            [],
            [0],
        )
        assert assertions[0].passed is False

    @pytest.mark.asyncio
    async def test_take_screenshot_increments_counter(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page()
        screenshots: list[str] = []
        counter = [0]
        await _dispatch_browser_tool(
            "take_screenshot", {"name": "home"}, page, tmp_path, [], screenshots, counter
        )
        await _dispatch_browser_tool(
            "take_screenshot", {"name": "about"}, page, tmp_path, [], screenshots, counter
        )
        assert counter[0] == 2
        assert len(screenshots) == 2
        assert "screenshot-00-home.png" in screenshots[0]
        assert "screenshot-01-about.png" in screenshots[1]

    @pytest.mark.asyncio
    async def test_mark_done_returns_is_done_true(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page()
        result_str, is_done = await _dispatch_browser_tool(
            "mark_done", {"passed": True, "summary": "All good"}, page, tmp_path, [], [], [0]
        )
        assert is_done is True
        assert json.loads(result_str)["done"] is True

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page()
        result_str, is_done = await _dispatch_browser_tool(
            "nonexistent_tool", {}, page, tmp_path, [], [], [0]
        )
        assert is_done is False
        assert "error" in json.loads(result_str)

    @pytest.mark.asyncio
    async def test_playwright_exception_returns_error_json(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page()
        page.goto = AsyncMock(side_effect=Exception("net::ERR_CONNECTION_REFUSED"))
        result_str, is_done = await _dispatch_browser_tool(
            "navigate", {"url": "http://badhost/"}, page, tmp_path, [], [], [0]
        )
        assert is_done is False
        data = json.loads(result_str)
        assert "error" in data
        assert "ERR_CONNECTION_REFUSED" in data["error"]

    @pytest.mark.asyncio
    async def test_click_returns_selector(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page()
        result_str, is_done = await _dispatch_browser_tool(
            "click", {"selector": "button#submit"}, page, tmp_path, [], [], [0]
        )
        assert is_done is False
        assert json.loads(result_str)["clicked"] == "button#submit"
        page.click.assert_called_once_with("button#submit", timeout=10000)

    @pytest.mark.asyncio
    async def test_fill_returns_selector(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page()
        result_str, is_done = await _dispatch_browser_tool(
            "fill",
            {"selector": "input#email", "value": "user@example.com"},
            page,
            tmp_path,
            [],
            [],
            [0],
        )
        assert is_done is False
        assert json.loads(result_str)["filled"] == "input#email"
        page.fill.assert_called_once_with("input#email", "user@example.com")

    @pytest.mark.asyncio
    async def test_get_page_content_truncates(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page(body_text="x" * 5000)
        result_str, is_done = await _dispatch_browser_tool(
            "get_page_content", {}, page, tmp_path, [], [], [0]
        )
        assert is_done is False
        assert len(json.loads(result_str)["text"]) == 4000

    @pytest.mark.asyncio
    async def test_get_element_text_returns_text(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page(body_text="Hello")
        result_str, is_done = await _dispatch_browser_tool(
            "get_element_text", {"selector": "h1"}, page, tmp_path, [], [], [0]
        )
        assert is_done is False
        assert json.loads(result_str)["text"] == "Hello"

    @pytest.mark.asyncio
    async def test_wait_for_element_calls_playwright(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page()
        result_str, is_done = await _dispatch_browser_tool(
            "wait_for_element",
            {"selector": "#spinner", "timeout_ms": 5000},
            page,
            tmp_path,
            [],
            [],
            [0],
        )
        assert is_done is False
        assert json.loads(result_str)["found"] == "#spinner"
        page.wait_for_selector.assert_called_once_with("#spinner", timeout=5000)

    @pytest.mark.asyncio
    async def test_select_option_returns_value(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page()
        result_str, is_done = await _dispatch_browser_tool(
            "select_option",
            {"selector": "select#lang", "value": "en"},
            page,
            tmp_path,
            [],
            [],
            [0],
        )
        assert is_done is False
        assert json.loads(result_str)["selected"] == "en"
        page.select_option.assert_called_once_with("select#lang", "en")

    @pytest.mark.asyncio
    async def test_assert_element_should_not_exist_but_does(self, tmp_path):
        from talon.skills.browser_validator import _dispatch_browser_tool

        page = _make_page(locator_count=1, locator_text="Error banner")
        assertions: list[BrowserAssertion] = []
        await _dispatch_browser_tool(
            "assert_element",
            {"selector": ".error", "description": "No error shown", "should_exist": False},
            page,
            tmp_path,
            assertions,
            [],
            [0],
        )
        assert assertions[0].passed is False
        assert assertions[0].actual == "Error banner"

    @pytest.mark.asyncio
    async def test_mark_done_not_called_sets_error_field(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Quick test")

        end_response = MagicMock()
        end_response.stop_reason = "end_turn"
        end_response.tool_calls = []

        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(return_value=end_response)
        mock_provider.append_assistant = MagicMock()
        mock_provider.append_tool_results = MagicMock()

        mock_page = _make_page()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_playwright_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "get_provider", return_value=mock_provider):
                with patch.object(
                    browser_validator, "async_playwright", return_value=mock_playwright_cm
                ):
                    result = await browser_validator.run(
                        state, "http://localhost:8080", str(tmp_path)
                    )

        assert result is not None
        assert result.error == "Agent did not call mark_done"


# ---------------------------------------------------------------------------
# Integration tests: run()
# ---------------------------------------------------------------------------


class TestBrowserValidatorRun:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Test the homepage")
        with patch.object(browser_validator, "ENABLED", False):
            result = await browser_validator.run(state, "http://localhost:8080", str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_playwright_import_error_returns_none(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Test the homepage")
        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "async_playwright", None):
                result = await browser_validator.run(state, "http://localhost:8080", str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_run_returns_browser_test_result(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Page should load")

        nav_response = MagicMock()
        nav_response.stop_reason = "tool_use"
        nav_response.tool_calls = [
            _make_tool_call("t1", "navigate", {"url": "http://localhost:8080/"})
        ]

        assert_response = MagicMock()
        assert_response.stop_reason = "tool_use"
        assert_response.tool_calls = [
            _make_tool_call(
                "t2", "assert_element", {"selector": "body", "description": "Body exists"}
            )
        ]

        done_response = MagicMock()
        done_response.stop_reason = "tool_use"
        done_response.tool_calls = [
            _make_tool_call("t3", "mark_done", {"passed": True, "summary": "Page loaded fine"})
        ]

        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(side_effect=[nav_response, assert_response, done_response])
        mock_provider.append_assistant = MagicMock()
        mock_provider.append_tool_results = MagicMock()

        mock_page = _make_page(url="http://localhost:8080/", locator_count=1, locator_text="body")
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_playwright_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "get_provider", return_value=mock_provider):
                with patch.object(
                    browser_validator, "async_playwright", return_value=mock_playwright_cm
                ):
                    result = await browser_validator.run(
                        state, "http://localhost:8080", str(tmp_path)
                    )

        assert isinstance(result, BrowserTestResult)
        assert result.passed is True
        assert result.summary == "Page loaded fine"

    @pytest.mark.asyncio
    async def test_failed_assertion_lowers_score(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Check two things")

        assert1_response = MagicMock()
        assert1_response.stop_reason = "tool_use"
        assert1_response.tool_calls = [
            _make_tool_call(
                "t1", "assert_element", {"selector": "#exists", "description": "Present element"}
            )
        ]

        assert2_response = MagicMock()
        assert2_response.stop_reason = "tool_use"
        assert2_response.tool_calls = [
            _make_tool_call(
                "t2", "assert_element", {"selector": "#missing", "description": "Missing element"}
            )
        ]

        done_response = MagicMock()
        done_response.stop_reason = "tool_use"
        done_response.tool_calls = [
            _make_tool_call("t3", "mark_done", {"passed": False, "summary": "One check failed"})
        ]

        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(
            side_effect=[assert1_response, assert2_response, done_response]
        )
        mock_provider.append_assistant = MagicMock()
        mock_provider.append_tool_results = MagicMock()

        mock_page = _make_page()
        # For first assert: count=1, for second: count=0
        counts = [1, 0]
        count_idx = [0]

        async def dynamic_count():
            val = counts[count_idx[0] % len(counts)]
            count_idx[0] += 1
            return val

        locator = AsyncMock()
        locator.count = dynamic_count
        locator.first = AsyncMock()
        locator.first.inner_text = AsyncMock(return_value="text")
        mock_page.locator = MagicMock(return_value=locator)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_playwright_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "get_provider", return_value=mock_provider):
                with patch.object(
                    browser_validator, "async_playwright", return_value=mock_playwright_cm
                ):
                    result = await browser_validator.run(
                        state, "http://localhost:8080", str(tmp_path)
                    )

        assert result is not None
        assert result.score == pytest.approx(0.5)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_max_steps_stops_loop(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Navigate forever")

        nav_response = MagicMock()
        nav_response.stop_reason = "tool_use"
        nav_response.tool_calls = [
            _make_tool_call("t1", "navigate", {"url": "http://localhost:8080/"})
        ]

        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(return_value=nav_response)
        mock_provider.append_assistant = MagicMock()
        mock_provider.append_tool_results = MagicMock()

        mock_page = _make_page()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_playwright_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "MAX_STEPS", 3):
                with patch.object(browser_validator, "get_provider", return_value=mock_provider):
                    with patch.object(
                        browser_validator, "async_playwright", return_value=mock_playwright_cm
                    ):
                        result = await browser_validator.run(
                            state, "http://localhost:8080", str(tmp_path)
                        )

        assert result is not None
        assert mock_provider.chat.call_count == 3

    @pytest.mark.asyncio
    async def test_result_video_path_is_set(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Quick test")

        done_response = MagicMock()
        done_response.stop_reason = "tool_use"
        done_response.tool_calls = [
            _make_tool_call("t1", "mark_done", {"passed": True, "summary": "Done"})
        ]

        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(return_value=done_response)
        mock_provider.append_assistant = MagicMock()
        mock_provider.append_tool_results = MagicMock()

        mock_page = _make_page()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_playwright_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "get_provider", return_value=mock_provider):
                with patch.object(
                    browser_validator, "async_playwright", return_value=mock_playwright_cm
                ):
                    result = await browser_validator.run(
                        state, "http://localhost:8080", str(tmp_path)
                    )

        assert result is not None
        assert result.video_path is not None
        assert result.video_path.endswith("proof.webm")


# ---------------------------------------------------------------------------
# Type tests: TestBrowserTypes
# ---------------------------------------------------------------------------


class TestBrowserTypes:
    def test_browser_assertion_defaults(self):
        a = BrowserAssertion(description="test", passed=True)
        assert a.selector is None
        assert a.expected is None
        assert a.actual is None

    def test_browser_test_result_round_trip(self):
        result = BrowserTestResult(
            passed=True,
            score=0.75,
            summary="Three of four passed",
            assertions=[
                BrowserAssertion(description="A", passed=True),
                BrowserAssertion(description="B", passed=False, actual="not found"),
            ],
            screenshots=["/runs/abc/screenshot-00-home.png"],
            video_path="/runs/abc/proof.webm",
            steps=5,
        )
        restored = BrowserTestResult.model_validate_json(result.model_dump_json())
        assert restored.passed is True
        assert restored.score == pytest.approx(0.75)
        assert len(restored.assertions) == 2
        assert restored.assertions[1].passed is False

    def test_run_state_browser_result_field(self):
        state = RunState(goal="Test goal")
        assert state.browser_result is None
        br = BrowserTestResult(passed=True, score=1.0, summary="ok")
        state.browser_result = br
        assert state.browser_result.passed is True

    def test_run_state_json_round_trip_with_browser_result(self):
        state = RunState(
            goal="Test goal",
            browser_result=BrowserTestResult(
                passed=False,
                score=0.5,
                summary="Half passed",
                assertions=[BrowserAssertion(description="x", passed=False)],
            ),
        )
        restored = RunState.model_validate_json(state.model_dump_json())
        assert restored.browser_result is not None
        assert restored.browser_result.score == pytest.approx(0.5)
        assert len(restored.browser_result.assertions) == 1
