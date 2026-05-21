# Plan: Browser Validator — Passive Recorder → LLM-Driven UI Test Agent

## Context

The `browser_validator` skill currently visits URLs, records a `.webm` video, and takes screenshots — but it makes no assertions and has no interactive capability. It cannot verify goal-specific behavior (form submission, redirects, element text, etc.). The Phase 2 CLAUDE.md TODO calls out "add goal-specific navigation steps." This plan delivers that: a full LLM-driven tool-use loop where the model dynamically clicks, fills, asserts, and records structured pass/fail evidence — matching the architectural pattern already used in `self_reviewer.py`.

## Files to Modify / Create

| File | Change |
|---|---|
| `talon/types.py` | Add `BrowserAssertion`, `BrowserTestResult`; patch `RunState` |
| `talon/skills/browser_validator.py` | Full rewrite |
| `talon/loop.py` | 5-line update to Step 4 block (lines 205–210) |
| `.env.example` | Add 2 new env vars |
| `tests/test_browser_validator.py` | New file (~180 lines) |

---

## Step 1 — `talon/types.py`: New types + `RunState` field

Add after line 103 (end of `RunState`):

```python
class BrowserAssertion(BaseModel):
    description: str
    selector: Optional[str] = None      # None for URL assertions
    expected: Optional[str] = None
    actual: Optional[str] = None
    passed: bool


class BrowserTestResult(BaseModel):
    passed: bool
    score: float                         # assertion pass rate, 0.0–1.0
    summary: str
    assertions: list[BrowserAssertion] = []
    screenshots: list[str] = []          # absolute file paths
    video_path: Optional[str] = None
    steps: int = 0                       # total tool calls made
    error: Optional[str] = None
```

Add to `RunState` after `video_path` (line 98):

```python
    browser_result: Optional[BrowserTestResult] = None
```

`video_path` stays as a convenience field; `loop.py` populates it from `browser_result.video_path`.

---

## Step 2 — `talon/skills/browser_validator.py`: Full rewrite

### Module-level constants
```python
ENABLED = os.getenv("BROWSER_VALIDATOR_ENABLED", "false").lower() == "true"
MAX_STEPS = int(os.getenv("BROWSER_TEST_MAX_STEPS", "20"))
ACTION_TIMEOUT = int(os.getenv("BROWSER_ACTION_TIMEOUT", "10000"))  # ms
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))
```

### Browser tool definitions (`BROWSER_TOOL_DEFINITIONS`)

11 tools in Anthropic `input_schema` format (LiteLLMProvider converts to `parameters` at call time):

| Tool | Description |
|---|---|
| `navigate(url)` | `page.goto` + `wait_for_load_state("networkidle")`, returns title + final URL |
| `click(selector, timeout_ms?)` | `page.click`, then `networkidle` wait |
| `fill(selector, value)` | `page.fill` |
| `get_page_content(include_html?)` | `page.inner_text("body")` + URL/title; HTML truncated at 4000 chars |
| `get_element_text(selector)` | `page.inner_text(selector)` |
| `assert_element(selector, description, expected_text?, should_exist?)` | **Records** `BrowserAssertion`. Uses `page.locator(selector).count()` then `inner_text` comparison |
| `assert_url(description, expected_pattern)` | **Records** `BrowserAssertion`. `re.search(pattern, page.url)` |
| `wait_for_element(selector, timeout_ms?)` | `page.wait_for_selector` |
| `take_screenshot(name)` | `page.screenshot(path=video_dir/f"screenshot-{n:02d}-{name}.png", full_page=True)` |
| `select_option(selector, value)` | `page.select_option` |
| `mark_done(passed, summary)` | Returns `is_done=True` — ends the loop |

### System prompt

```
You are an expert QA engineer performing automated UI testing. Your job is to verify
that the application satisfies the stated goal by interacting with it through browser tools.

Workflow:
1. Navigate to the app URL.
2. Exercise the flows related to the goal (fill forms, click buttons, navigate pages).
3. Use assert_element and assert_url to formally record pass/fail at each key state.
4. Take screenshots at major transitions as visual proof.
5. Call mark_done with your overall verdict when done.

Rules:
- Always navigate before asserting.
- Use get_page_content to orient yourself when the page structure is unclear.
- Prefer specific selectors (id, data-testid, aria-label) over generic ones.
- If a selector fails, try an alternative before recording a failure.
- If the app is unreachable, call mark_done(passed=false) immediately.
- You have a budget of {max_steps} tool calls. Use them efficiently.
- Every action must be a tool call — no prose output.
```

### `_dispatch_browser_tool(tool_name, tool_input, page, video_dir, assertions, screenshots, counter) -> tuple[str, bool]`

Pure `async` function (no `asyncio.to_thread` — Playwright is natively async). Returns `(json_result_str, is_done)`. `is_done` is `True` only on `mark_done`.

- `counter` is `list[int]` (single-element mutable container) to track screenshot numbering across calls without `nonlocal`.
- All Playwright exceptions are caught and returned as `{"error": str(e)}` — never crash the loop.
- `assert_element`: uses `page.locator(selector)` + `.count()` for existence check, `.first.inner_text()` for text check.
- `assert_url`: uses `re.search(pattern, page.url, re.IGNORECASE)` with fallback to substring if regex is invalid.

### `run(state, app_url, runs_dir) -> BrowserTestResult | None`

Return type changes from `str | None` to `BrowserTestResult | None`.

Structure (mirrors `self_reviewer.py` tool-use loop):

```python
async with async_playwright() as pw:
    browser = await pw.chromium.launch()
    context = await browser.new_context(
        record_video_dir=str(video_dir),
        record_video_size={"width": 1280, "height": 720},
    )
    page = await context.new_page()

    for _turn in range(MAX_STEPS):
        response = await provider.chat(system=system, messages=messages,
                                       tools=BROWSER_TOOL_DEFINITIONS, max_tokens=MAX_TOKENS)
        provider.append_assistant(messages, response)

        if response.stop_reason == "end_turn":
            break  # LLM stopped without mark_done — treat as incomplete

        tool_results, done = [], False
        for tc in response.tool_calls:
            result_str, is_done = await _dispatch_browser_tool(...)
            tool_results.append(ToolResult(id=tc.id, content=result_str))
            if is_done:
                final_passed = tc.input["passed"]
                final_summary = tc.input["summary"]
                done = True
                provider.append_tool_results(messages, tool_results)
                break

        if not done:
            provider.append_tool_results(messages, tool_results)
        if done:
            break

    await context.close()
    await browser.close()

score = (# passed assertions) / max(len(assertions), 1)
return BrowserTestResult(passed=final_passed, score=score, summary=final_summary,
                          assertions=assertions, screenshots=screenshots,
                          video_path=str(video_dir / "proof.webm"), steps=steps)
```

**Provider role**: `get_provider("reviewer")` — same as today. Analytical model fits browser testing.

**Import block** (top of rewritten file):
```python
from talon.providers import get_provider
from talon.providers.base import ToolResult
from talon.types import BrowserAssertion, BrowserTestResult, RunState
```

---

## Step 3 — `talon/loop.py`: Update Step 4 (lines 205–210)

Replace:
```python
video_path = await browser_validator.run(state, app_url, RUNS_DIR)
state.video_path = video_path
```

With:
```python
browser_result = await browser_validator.run(state, app_url, RUNS_DIR)
if browser_result is not None:
    state.browser_result = browser_result
    state.video_path = browser_result.video_path
```

`board_updater.run(state, state.video_path, state.pr_url)` on line 223 is unchanged — `state.video_path` still holds the `.webm` path.

---

## Step 4 — `.env.example`: Add 2 new variables

In the browser section (currently line 53–54), expand to:

```
# --- Browser validator ----------------------------------------------
BROWSER_VALIDATOR_ENABLED=false   # set true to enable LLM-driven UI testing
BROWSER_TEST_MAX_STEPS=20         # max tool-use steps per browser test session
BROWSER_ACTION_TIMEOUT=10000      # Playwright action timeout in milliseconds
```

---

## Step 5 — `tests/test_browser_validator.py`: New test file

### Unit tests: `TestDispatchBrowserTool` (mock `page` via `AsyncMock`)
- `test_navigate_returns_url_and_title`
- `test_assert_element_pass` — locator count=1, text matches → `passed=True`, assertion appended
- `test_assert_element_fail_not_found` — locator count=0 → `passed=False`, `actual="element not found"`
- `test_assert_url_pass` / `test_assert_url_fail`
- `test_take_screenshot_increments_counter` — two calls → `counter[0]==2`, two entries in `screenshots`
- `test_mark_done_returns_is_done_true`
- `test_unknown_tool_returns_error`
- `test_playwright_exception_returns_error_json` — `page.goto` raises → returns `{"error": ...}`, `is_done=False`

### Integration tests: `TestBrowserValidatorRun` (mock provider + mock Playwright context)
- `test_disabled_returns_none`
- `test_playwright_import_error_returns_none`
- `test_successful_run_returns_browser_test_result` — provider returns navigate → assert_element → mark_done
- `test_failed_assertion_lowers_score` — 2 assertions, 1 fails → `score==0.5`, `passed=False`
- `test_max_steps_stops_loop` — provider always returns navigate, never mark_done → loop exhausts
- `test_result_video_path_is_set`

### Type tests: `TestBrowserTypes`
- `test_browser_assertion_defaults`
- `test_browser_test_result_round_trip` — JSON round-trip via `model_dump_json`
- `test_run_state_browser_result_field` — defaults to `None`, can be set
- `test_run_state_json_round_trip_with_browser_result`

---

## Known edge cases addressed

- **SPA `networkidle` timeout**: caught in `_dispatch_browser_tool`, returned as error JSON — loop continues.
- **Multiple tool calls per turn**: inner `for tc in response.tool_calls` loop; on `mark_done`, remaining results are appended before `break`.
- **Video file timing**: Playwright writes `.webm` only after `context.close()`. The `video_path` string is pre-set to `proof.webm` before the loop; file existence is guaranteed by the time `board_updater` runs (Step 6 is after Step 4 in `loop.py`).
- **No assertions made**: if LLM calls `mark_done` without any `assert_*` calls, `score` is `1.0` if `passed=True`, else `0.0`.

---

## Verification

### Unit tests (no browser, no API key)
```bash
pytest tests/test_browser_validator.py -v
pytest tests/ -v   # regression — all existing tests must pass
```

### Type check
```bash
mypy talon/types.py talon/skills/browser_validator.py talon/loop.py
```

### Manual smoke test (browser + API key required)
```bash
# Terminal 1
python -m http.server 8080

# Terminal 2
BROWSER_VALIDATOR_ENABLED=true python -c "
import asyncio
from talon.types import RunState
from talon.skills import browser_validator
state = RunState(goal='The page should display a directory listing')
r = asyncio.run(browser_validator.run(state, 'http://localhost:8080', './runs'))
print(r)
"
# Expected: BrowserTestResult(passed=True, score=1.0, assertions=[...], video_path='.../proof.webm')
```

### Full loop test
```bash
talon run "The homepage should load and display a heading" \
  --url http://localhost:8080 --skip-board
# Inspect ./runs/<run_id>/state.json — browser_result should be populated
```
