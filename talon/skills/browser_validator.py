"""
browser-validator skill
-----------------------
LLM-driven UI test agent: navigates the app, runs assertions, records video.

To enable:
  pip install talon-agent[browser]
  playwright install chromium
  Set BROWSER_VALIDATOR_ENABLED=true in .env
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Awaitable, Callable

from rich.console import Console

from talon.providers import get_provider
from talon.providers.base import ToolResult
from talon.types import BrowserAssertion, BrowserTestResult, RunState

try:
    from playwright.async_api import async_playwright  # type: ignore
except ImportError:
    async_playwright = None  # type: ignore[assignment]

console = Console()

ENABLED = os.getenv("BROWSER_VALIDATOR_ENABLED", "false").lower() == "true"
MAX_STEPS = int(os.getenv("BROWSER_TEST_MAX_STEPS", "20"))
ACTION_TIMEOUT = int(os.getenv("BROWSER_ACTION_TIMEOUT", "10000"))
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))

BROWSER_TOOL_DEFINITIONS = [
    {
        "name": "navigate",
        "description": "Navigate to a URL and wait for the page to load.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to navigate to"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "click",
        "description": "Click an element on the page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS or text selector"},
                "timeout_ms": {"type": "integer", "description": "Timeout in ms"},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "fill",
        "description": "Fill an input field with a value.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["selector", "value"],
        },
    },
    {
        "name": "get_page_content",
        "description": "Get the visible text content of the page body.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_html": {
                    "type": "boolean",
                    "description": "Include raw HTML (truncated to 4000 chars)",
                },
            },
        },
    },
    {
        "name": "get_element_text",
        "description": "Get the inner text of a specific element.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "assert_element",
        "description": "Assert that an element exists and optionally contains expected text. Records a BrowserAssertion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "description": {"type": "string"},
                "expected_text": {"type": "string"},
                "should_exist": {"type": "boolean", "default": True},
            },
            "required": ["selector", "description"],
        },
    },
    {
        "name": "assert_url",
        "description": "Assert the current URL matches a pattern. Records a BrowserAssertion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "expected_pattern": {"type": "string"},
            },
            "required": ["description", "expected_pattern"],
        },
    },
    {
        "name": "wait_for_element",
        "description": "Wait for an element to appear on the page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "timeout_ms": {"type": "integer"},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "take_screenshot",
        "description": "Take a full-page screenshot and save it as proof.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short label for the filename"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "select_option",
        "description": "Select an option from a <select> element.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["selector", "value"],
        },
    },
    {
        "name": "mark_done",
        "description": "Signal that testing is complete. Must be called to end the session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean", "description": "Overall test verdict"},
                "summary": {"type": "string", "description": "One-sentence summary"},
            },
            "required": ["passed", "summary"],
        },
    },
]

_BROWSER_AGENT_SYSTEM = (
    "You are an expert QA engineer performing automated UI testing. Your job is to verify\n"
    "that the application satisfies the stated goal by interacting with it through browser tools.\n\n"
    "Workflow:\n"
    "1. Navigate to the app URL.\n"
    "2. Exercise the flows related to the goal (fill forms, click buttons, navigate pages).\n"
    "3. Use assert_element and assert_url to formally record pass/fail at each key state.\n"
    "4. Take screenshots at major transitions as visual proof.\n"
    "5. Call mark_done with your overall verdict when done.\n\n"
    "Rules:\n"
    "- Always navigate before asserting.\n"
    "- Use get_page_content to orient yourself when page structure is unclear.\n"
    "- Prefer specific selectors (id, data-testid, aria-label) over generic ones.\n"
    "- If a selector fails, try an alternative before recording a failure.\n"
    "- If the app is unreachable, immediately call mark_done(passed=false).\n"
    "- You have a budget of {max_steps} tool calls. Use them efficiently.\n"
    "- Every action must be a tool call — no prose output."
)


async def _dispatch_browser_tool(
    tool_name: str,
    tool_input: dict,
    page,
    video_dir: Path,
    assertions: list[BrowserAssertion],
    screenshots: list[str],
    counter: list[int],
) -> tuple[str, bool]:
    """Dispatch a single browser tool call. Returns (json_result, is_done)."""
    try:
        if tool_name == "navigate":
            url = tool_input["url"]
            await page.goto(url, timeout=ACTION_TIMEOUT)
            await page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
            title = await page.title()
            final_url = page.url
            return json.dumps({"title": title, "url": final_url}), False

        elif tool_name == "click":
            selector = tool_input["selector"]
            timeout = tool_input.get("timeout_ms", ACTION_TIMEOUT)
            await page.click(selector, timeout=timeout)
            await page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
            return json.dumps({"clicked": selector}), False

        elif tool_name == "fill":
            await page.fill(tool_input["selector"], tool_input["value"])
            return json.dumps({"filled": tool_input["selector"]}), False

        elif tool_name == "get_page_content":
            text = await page.inner_text("body")
            result: dict = {"text": text[:4000]}
            if tool_input.get("include_html"):
                html = await page.content()
                result["html"] = html[:4000]
            return json.dumps(result), False

        elif tool_name == "get_element_text":
            text = await page.inner_text(tool_input["selector"])
            return json.dumps({"text": text}), False

        elif tool_name == "assert_element":
            selector = tool_input["selector"]
            description = tool_input["description"]
            expected_text = tool_input.get("expected_text")
            should_exist = tool_input.get("should_exist", True)

            count = await page.locator(selector).count()
            exists = count > 0
            actual = None
            passed = exists == should_exist

            if exists and expected_text is not None:
                actual = await page.locator(selector).first.inner_text()
                passed = expected_text.lower() in actual.lower()

            if not exists and should_exist:
                actual = "element not found"
            elif exists and not should_exist:
                actual = await page.locator(selector).first.inner_text()

            assertion = BrowserAssertion(
                description=description,
                selector=selector,
                expected=expected_text,
                actual=actual,
                passed=passed,
            )
            assertions.append(assertion)
            return json.dumps({"passed": passed, "actual": actual}), False

        elif tool_name == "assert_url":
            description = tool_input["description"]
            pattern = tool_input["expected_pattern"]
            current_url = page.url
            try:
                matched = bool(re.search(pattern, current_url, re.IGNORECASE))
            except re.error:
                matched = pattern in current_url
            assertion = BrowserAssertion(
                description=description,
                selector=None,
                expected=pattern,
                actual=current_url,
                passed=matched,
            )
            assertions.append(assertion)
            return json.dumps({"passed": matched, "url": current_url}), False

        elif tool_name == "wait_for_element":
            timeout = tool_input.get("timeout_ms", ACTION_TIMEOUT)
            await page.wait_for_selector(tool_input["selector"], timeout=timeout)
            return json.dumps({"found": tool_input["selector"]}), False

        elif tool_name == "take_screenshot":
            n = counter[0]
            counter[0] += 1
            name = re.sub(r"[^\w\-]", "_", tool_input["name"])[:40]
            path = str(video_dir / f"screenshot-{n:02d}-{name}.png")
            await page.screenshot(path=path, full_page=True)
            screenshots.append(path)
            return json.dumps({"saved": path}), False

        elif tool_name == "select_option":
            await page.select_option(tool_input["selector"], tool_input["value"])
            return json.dumps({"selected": tool_input["value"]}), False

        elif tool_name == "mark_done":
            return json.dumps({"done": True}), True

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}), False

    except Exception as e:
        return json.dumps({"error": str(e), "tool": tool_name}), False


async def run(
    state: RunState,
    app_url: str,
    runs_dir: str,
    on_progress: Callable[[BrowserTestResult], Awaitable[None]] | None = None,
    cookie_file: str | None = None,
    test_user: str | None = None,
    test_password: str | None = None,
) -> BrowserTestResult | None:
    """
    Run an LLM-driven browser test session against app_url.
    Returns a BrowserTestResult, or None on failure/disabled.

    on_progress is called after each tool round with a partial BrowserTestResult
    so callers can stream incremental state to the UI.
    """
    if not ENABLED:
        console.print(
            "\n[dim]browser-validator[/dim] "
            "[dim](disabled — set BROWSER_VALIDATOR_ENABLED=true)[/dim]"
        )
        return None

    if async_playwright is None:
        console.print(
            "\n[yellow]browser-validator[/yellow] Playwright not installed. "
            "Run: pip install 'talon-agent[browser]' && playwright install chromium"
        )
        return None

    console.print(f"\n[bold green]browser-validator[/bold green] testing {app_url}")

    provider = get_provider("reviewer")
    video_dir = Path(runs_dir) / state.run_id
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(video_dir / "proof.webm")

    # Gather execution context dynamically to guide the browser validator on any task
    all_files_modified = set()
    aggregated_outputs = []
    for er in state.executor_results:
        for sr in er.subtask_results:
            if sr.files_modified:
                all_files_modified.update(sr.files_modified)
            if sr.output:
                aggregated_outputs.append(sr.output)

    files_str = ", ".join(sorted(list(all_files_modified))) if all_files_modified else "(none)"
    outputs_str = "\n---\n".join(aggregated_outputs) if aggregated_outputs else "(none)"

    creds_hint = ""
    if test_user or test_password:
        creds_hint = (
            f"\n\nTest account credentials (use these to log in if prompted):\n"
            f"  Username / Email: {test_user or '(not set)'}\n"
            f"  Password: {test_password or '(not set)'}"
        )
    system = _BROWSER_AGENT_SYSTEM.format(max_steps=MAX_STEPS) + creds_hint
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Goal: {state.goal}\n"
                f"App URL: {app_url}\n\n"
                f"Files Modified During Execution:\n{files_str}\n\n"
                f"Actions / Execution Results Summary:\n{outputs_str}\n\n"
                "Your job is to test and verify the relevant changes that were made in this run.\n"
                "Using the browser tools, navigate the application and work through the flows of the changed files/features "
                "to prove they work, taking screenshots of major states as visual proof.\n"
                "Call mark_done with your overall verdict when done."
            ),
        }
    ]

    assertions: list[BrowserAssertion] = []
    screenshots: list[str] = []
    counter = [0]
    final_passed = False
    final_summary = "Test did not complete"
    mark_done_called = False
    steps = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(
            record_video_dir=str(video_dir),
            record_video_size={"width": 1280, "height": 720},
        )
        if cookie_file:
            try:
                raw_cookies = json.loads(Path(cookie_file).read_text(encoding="utf-8"))
                await context.add_cookies(raw_cookies)
                console.print(f"  [dim]browser-validator[/dim] loaded cookies from {cookie_file}")
            except Exception as _ce:
                console.print(
                    f"  [yellow]browser-validator[/yellow] "
                    f"failed to load cookies from {cookie_file}: {_ce}"
                )
        page = await context.new_page()

        try:
            for _turn in range(MAX_STEPS):
                response = await provider.chat(
                    system=system,
                    messages=messages,
                    tools=BROWSER_TOOL_DEFINITIONS,
                    max_tokens=MAX_TOKENS,
                )
                provider.append_assistant(messages, response)
                steps += 1

                if response.stop_reason == "end_turn":
                    break

                if not response.tool_calls:
                    break

                tool_results = []
                done = False
                for tc in response.tool_calls:
                    result_str, is_done = await _dispatch_browser_tool(
                        tc.name,
                        tc.input,
                        page,
                        video_dir,
                        assertions,
                        screenshots,
                        counter,
                    )
                    tool_results.append(ToolResult(id=tc.id, content=result_str))
                    if is_done:
                        final_passed = tc.input.get("passed", False)
                        final_summary = tc.input.get("summary", "")
                        mark_done_called = True
                        done = True
                        provider.append_tool_results(messages, tool_results)
                        break

                if not done:
                    provider.append_tool_results(messages, tool_results)
                if done:
                    break

                if on_progress:
                    partial_score = (
                        (sum(1 for a in assertions if a.passed) / len(assertions))
                        if assertions
                        else 0.0
                    )
                    await on_progress(
                        BrowserTestResult(
                            passed=False,
                            score=partial_score,
                            summary=f"Testing… ({steps} steps, {len(assertions)} assertions)",
                            assertions=list(assertions),
                            screenshots=list(screenshots),
                            video_path=video_path,
                            steps=steps,
                        )
                    )
        finally:
            await context.close()
            await browser.close()

    if not assertions:
        score = 1.0 if final_passed else 0.0
    else:
        score = sum(1 for a in assertions if a.passed) / len(assertions)

    console.print(
        f"  [{'green' if final_passed else 'red'}]"
        f"{'PASSED' if final_passed else 'FAILED'}[/{'green' if final_passed else 'red'}] "
        f"score={score:.0%} steps={steps} assertions={len(assertions)}"
    )

    return BrowserTestResult(
        passed=final_passed,
        score=score,
        summary=final_summary,
        assertions=assertions,
        screenshots=screenshots,
        video_path=video_path,
        steps=steps,
        error=None if mark_done_called else "Agent did not call mark_done",
    )
