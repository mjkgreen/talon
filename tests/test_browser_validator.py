"""Tests for the browser_validator skill (browser-use implementation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from talon.types import BrowserAssertion, BrowserTestResult, PlanResult, RunState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_history(
    final_text: str,
    is_successful: bool = True,
    screenshot_paths: list | None = None,
):
    history = MagicMock()
    history.final_result = MagicMock(return_value=final_text)
    history.is_successful = MagicMock(return_value=is_successful)
    history.screenshot_paths = MagicMock(return_value=screenshot_paths or [])
    return history


# ---------------------------------------------------------------------------
# Unit tests: _parse_result
# ---------------------------------------------------------------------------


class TestParseResult:
    def test_valid_json_parsed(self):
        from talon.skills.browser_validator import _parse_result

        text = '{"verified": ["Login works"], "failed": [], "summary": "All good"}'
        v, f, s = _parse_result(text, ["Login works"])
        assert v == ["Login works"]
        assert f == []
        assert s == "All good"

    def test_json_with_failed_parsed(self):
        from talon.skills.browser_validator import _parse_result

        text = (
            'Some prose here.\n'
            '{"verified": ["A"], "failed": ["B"], "summary": "One failed"}'
        )
        v, f, s = _parse_result(text, ["A", "B"])
        assert "A" in v
        assert "B" in f

    def test_none_input_returns_all_failed(self):
        from talon.skills.browser_validator import _parse_result

        criteria = ["C1", "C2"]
        v, f, s = _parse_result(None, criteria)
        assert v == []
        assert f == criteria

    def test_malformed_json_falls_back(self):
        from talon.skills.browser_validator import _parse_result

        text = "The app seems to be working fine."
        v, f, s = _parse_result(text, ["Criterion"])
        # Falls back to empty lists and raw summary
        assert v == []
        assert f == []
        assert text[:400] in s or s in text[:400]

    def test_empty_criteria(self):
        from talon.skills.browser_validator import _parse_result

        text = '{"verified": [], "failed": [], "summary": "No criteria"}'
        v, f, s = _parse_result(text, [])
        assert v == []
        assert f == []


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
    async def test_browser_use_not_available_returns_none(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Test the homepage")
        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "_BROWSER_USE_AVAILABLE", False):
                result = await browser_validator.run(state, "http://localhost:8080", str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_successful_run_returns_browser_test_result(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Page should load")
        history = _make_history(
            '{"verified": [], "failed": [], "summary": "Page loaded fine"}'
        )
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=history)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "_BROWSER_USE_AVAILABLE", True):
                with patch("talon.skills.browser_validator.Agent", return_value=mock_agent):
                    with patch("talon.skills.browser_validator.BrowserProfile"):
                        with patch("talon.skills.browser_validator.ChatLiteLLM"):
                            with patch("talon.skills.browser_validator.resolve_model", return_value="m"):
                                with patch("talon.skills.browser_validator._preflight_wait", new_callable=AsyncMock):
                                    result = await browser_validator.run(
                                        state, "http://localhost:8080", str(tmp_path)
                                    )

        assert isinstance(result, BrowserTestResult)

    @pytest.mark.asyncio
    async def test_run_with_criteria_builds_assertions(self, tmp_path):
        from talon.skills import browser_validator

        plan = PlanResult(approach="t", phases=[], success_criteria=["Login works", "Dashboard loads"])
        state = RunState(goal="Test login", plan_result=plan)
        history = _make_history(
            '{"verified": ["Login works", "Dashboard loads"], "failed": [], "summary": "All good"}'
        )
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=history)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "_BROWSER_USE_AVAILABLE", True):
                with patch("talon.skills.browser_validator.Agent", return_value=mock_agent):
                    with patch("talon.skills.browser_validator.BrowserProfile"):
                        with patch("talon.skills.browser_validator.ChatLiteLLM"):
                            with patch("talon.skills.browser_validator.resolve_model", return_value="m"):
                                with patch("talon.skills.browser_validator._preflight_wait", new_callable=AsyncMock):
                                    result = await browser_validator.run(
                                        state, "http://localhost:8080", str(tmp_path)
                                    )

        assert result is not None
        assert result.score == pytest.approx(1.0)
        assert result.passed is True
        assert len(result.assertions) == 2
        assert all(a.passed for a in result.assertions)

    @pytest.mark.asyncio
    async def test_failed_criteria_lowers_score(self, tmp_path):
        from talon.skills import browser_validator

        plan = PlanResult(approach="t", phases=[], success_criteria=["Feature A", "Feature B"])
        state = RunState(goal="Test features", plan_result=plan)
        history = _make_history(
            '{"verified": ["Feature A"], "failed": ["Feature B"], "summary": "One failed"}'
        )
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=history)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "_BROWSER_USE_AVAILABLE", True):
                with patch("talon.skills.browser_validator.Agent", return_value=mock_agent):
                    with patch("talon.skills.browser_validator.BrowserProfile"):
                        with patch("talon.skills.browser_validator.ChatLiteLLM"):
                            with patch("talon.skills.browser_validator.resolve_model", return_value="m"):
                                with patch("talon.skills.browser_validator._preflight_wait", new_callable=AsyncMock):
                                    result = await browser_validator.run(
                                        state, "http://localhost:8080", str(tmp_path)
                                    )

        assert result is not None
        assert result.score == pytest.approx(0.5)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_agent_exception_returns_error_result(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Test something")
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=Exception("Connection refused"))

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "_BROWSER_USE_AVAILABLE", True):
                with patch("talon.skills.browser_validator.Agent", return_value=mock_agent):
                    with patch("talon.skills.browser_validator.BrowserProfile"):
                        with patch("talon.skills.browser_validator.ChatLiteLLM"):
                            with patch("talon.skills.browser_validator.resolve_model", return_value="m"):
                                with patch("talon.skills.browser_validator._preflight_wait", new_callable=AsyncMock):
                                    result = await browser_validator.run(
                                        state, "http://localhost:8080", str(tmp_path)
                                    )

        assert result is not None
        assert result.passed is False
        assert result.error is not None
        assert "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_no_criteria_uses_agent_success(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Generic test")
        history = _make_history("Everything looks good.", is_successful=True)
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=history)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "_BROWSER_USE_AVAILABLE", True):
                with patch("talon.skills.browser_validator.Agent", return_value=mock_agent):
                    with patch("talon.skills.browser_validator.BrowserProfile"):
                        with patch("talon.skills.browser_validator.ChatLiteLLM"):
                            with patch("talon.skills.browser_validator.resolve_model", return_value="m"):
                                with patch("talon.skills.browser_validator._preflight_wait", new_callable=AsyncMock):
                                    result = await browser_validator.run(
                                        state, "http://localhost:8080", str(tmp_path)
                                    )

        assert result is not None
        assert result.passed is True
        assert result.score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_on_progress_callback_called(self, tmp_path):
        from talon.skills import browser_validator

        state = RunState(goal="Test with progress")
        history = _make_history('{"verified": [], "failed": [], "summary": "Done"}')
        progress_calls: list[BrowserTestResult] = []

        async def _progress(partial: BrowserTestResult) -> None:
            progress_calls.append(partial)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=history)

        with patch.object(browser_validator, "ENABLED", True):
            with patch.object(browser_validator, "_BROWSER_USE_AVAILABLE", True):
                with patch("talon.skills.browser_validator.Agent", return_value=mock_agent):
                    with patch("talon.skills.browser_validator.BrowserProfile"):
                        with patch("talon.skills.browser_validator.ChatLiteLLM"):
                            with patch("talon.skills.browser_validator.resolve_model", return_value="m"):
                                with patch("talon.skills.browser_validator._preflight_wait", new_callable=AsyncMock):
                                    await browser_validator.run(
                                        state,
                                        "http://localhost:8080",
                                        str(tmp_path),
                                        on_progress=_progress,
                                    )

        assert len(progress_calls) >= 1
        assert progress_calls[0].summary.startswith("Initializing")


# ---------------------------------------------------------------------------
# Type tests
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
            screenshots=["/runs/abc/shot.png"],
            video_path="/runs/abc/proof.webm",
            gif_path="/runs/abc/proof.gif",
            steps=5,
        )
        restored = BrowserTestResult.model_validate_json(result.model_dump_json())
        assert restored.passed is True
        assert restored.score == pytest.approx(0.75)
        assert len(restored.assertions) == 2
        assert restored.assertions[1].passed is False
        assert restored.gif_path == "/runs/abc/proof.gif"

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
