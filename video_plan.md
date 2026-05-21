# Plan: Browser Validator — Passive Recorder → LLM-Driven UI Test Agent

## Context

The `browser_validator` skill currently visits URLs, records a `.webm` video, and takes screenshots — but makes no assertions and has no interactive capability. The frontend already has a "Verification" tab in `IssueDetailModal.tsx` that shows only a video player when `video_path` is set. This plan delivers both sides: the backend LLM-driven tool-use loop that produces structured `BrowserTestResult` data, and the frontend that surfaces assertions, score, and screenshots alongside the video.

## Files to Modify / Create

| File | Change |
|---|---|
| `talon/types.py` | Add `BrowserAssertion`, `BrowserTestResult`; patch `RunState` |
| `talon/skills/browser_validator.py` | Full rewrite |
| `talon/loop.py` | 5-line update to Step 4 block (lines 212–216) |
| `talon/server.py` | Add `/api/runs/{run_id}/screenshots/{filename}` endpoint |
| `.env.example` | Add 2 new env vars |
| `ui/src/types.ts` | Add `BrowserAssertion`, `BrowserTestResult` interfaces |
| `ui/src/components/IssueDetailModal.tsx` | Expand "Verification" tab to show assertions + screenshots |
| `tests/test_browser_validator.py` | New test file |

---

## Step 1 — `talon/types.py`: New types + `RunState` field

Add after line 103 (end of file):

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

`video_path` stays as a convenience field on `RunState`; `loop.py` populates it from `browser_result.video_path`. The server's existing `/api/runs/{run_id}/video` endpoint reads `state.json["video_path"]` — no change needed there.

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

| Tool | Playwright call | Notes |
|---|---|---|
| `navigate(url)` | `page.goto` + `wait_for_load_state("networkidle")` | Returns title + final URL |
| `click(selector, timeout_ms?)` | `page.click` + networkidle wait | |
| `fill(selector, value)` | `page.fill` | |
| `get_page_content(include_html?)` | `page.inner_text("body")` | HTML truncated to 4000 chars |
| `get_element_text(selector)` | `page.inner_text(selector)` | |
| `assert_element(selector, description, expected_text?, should_exist?)` | `page.locator(selector).count()` + `inner_text` | **Records** `BrowserAssertion` |
| `assert_url(description, expected_pattern)` | `re.search(pattern, page.url)` | **Records** `BrowserAssertion` |
| `wait_for_element(selector, timeout_ms?)` | `page.wait_for_selector` | |
| `take_screenshot(name)` | `page.screenshot(path=..., full_page=True)` | Appended to `screenshots` list |
| `select_option(selector, value)` | `page.select_option` | |
| `mark_done(passed, summary)` | — | Returns `is_done=True`, ends loop |

### System prompt (`_BROWSER_AGENT_SYSTEM`)

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
- Use get_page_content to orient yourself when page structure is unclear.
- Prefer specific selectors (id, data-testid, aria-label) over generic ones.
- If a selector fails, try an alternative before recording a failure.
- If the app is unreachable, immediately call mark_done(passed=false).
- You have a budget of {max_steps} tool calls. Use them efficiently.
- Every action must be a tool call — no prose output.
```

### `_dispatch_browser_tool(tool_name, tool_input, page, video_dir, assertions, screenshots, counter) -> tuple[str, bool]`

Pure `async` function (no `asyncio.to_thread` — Playwright is natively async). Returns `(json_result_str, is_done)`. `is_done` is `True` only on `mark_done`.

- `counter` is `list[int]` (mutable single-element container) for screenshot numbering — avoids `nonlocal`, keeps function independently testable.
- All Playwright exceptions caught and returned as `{"error": str(e), "tool": name}` — never crash the loop.
- `assert_element`: `page.locator(selector).count()` for existence, `.first.inner_text()` for text comparison (case-insensitive substring).
- `assert_url`: `re.search(pattern, page.url, re.IGNORECASE)`, falls back to substring if pattern is invalid regex.
- `take_screenshot`: saves to `video_dir / f"screenshot-{n:02d}-{name}.png"` and appends path to `screenshots`.

### `run(state, app_url, runs_dir) -> BrowserTestResult | None`

Return type changes from `str | None` to `BrowserTestResult | None`.

Core structure (mirrors `self_reviewer.py` tool-use loop):

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
            break  # LLM stopped without mark_done

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

score = sum(1 for a in assertions if a.passed) / max(len(assertions), 1)
return BrowserTestResult(
    passed=final_passed, score=score, summary=final_summary,
    assertions=assertions, screenshots=screenshots,
    video_path=str(video_dir / "proof.webm"), steps=steps,
)
```

**Provider role**: `get_provider("reviewer")` — analytical model fits browser testing.

**Import block** (top of rewritten file):
```python
from talon.providers import get_provider
from talon.providers.base import ToolResult
from talon.types import BrowserAssertion, BrowserTestResult, RunState
```

---

## Step 3 — `talon/loop.py`: Update Step 4 (lines 212–216)

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

`board_updater.run(state, state.video_path, state.pr_url)` on line 230 is unchanged.

---

## Step 4 — `talon/server.py`: Add screenshot endpoint

Add after the existing `/api/runs/{run_id}/video` endpoint (around line 700):

```python
@app.get("/api/runs/{run_id}/screenshots/{filename}")
async def get_run_screenshot(run_id: str, filename: str):
    """Serve individual screenshot PNGs from the run's video directory."""
    run_dir = os.path.join(os.getenv("RUNS_DIR", "./runs"), run_id)
    screenshot_path = os.path.join(run_dir, filename)
    # Prevent path traversal: ensure the resolved path stays inside run_dir
    if not os.path.realpath(screenshot_path).startswith(os.path.realpath(run_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not os.path.exists(screenshot_path) or not filename.endswith(".png"):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(screenshot_path, media_type="image/png")
```

---

## Step 5 — `.env.example`: Add 2 new variables

Expand the browser section (currently lines 53–54):

```
# --- Browser validator ----------------------------------------------
BROWSER_VALIDATOR_ENABLED=false   # set true to enable LLM-driven UI testing
BROWSER_TEST_MAX_STEPS=20         # max tool-use steps per browser test session
BROWSER_ACTION_TIMEOUT=10000      # Playwright action timeout in milliseconds
```

---

## Step 6 — `ui/src/types.ts`: New browser types

Add after line 12 (after `PlanResult`):

```typescript
export interface BrowserAssertion {
  description: string;
  selector: string | null;
  expected: string | null;
  actual: string | null;
  passed: boolean;
}

export interface BrowserTestResult {
  passed: boolean;
  score: number;         // 0.0–1.0
  summary: string;
  assertions: BrowserAssertion[];
  screenshots: string[]; // absolute server-side paths; derive filename for API call
  video_path: string | null;
  steps: number;
  error: string | null;
}
```

`RunState` remains `any` — the existing modal accesses `activeRunState?.browser_result` via optional chaining, so no strict typing is required. Keep the eslint-disable comment.

---

## Step 7 — `ui/src/components/IssueDetailModal.tsx`: Expand "Verification" tab

### 7a — Tab visibility condition (line 657)

Change:
```tsx
{(activeRunState?.video_path) && (
```
To:
```tsx
{(activeRunState?.video_path || activeRunState?.browser_result) && (
```

This makes the tab appear whenever either a video or structured browser result is present.

### 7b — Tab content (lines 795–811)

Replace the current single `<video>` block with a richer layout:

```tsx
{macroTab === "video" &&
  (activeRunState?.video_path || activeRunState?.browser_result) && (
  <div className="space-y-4">

    {/* Summary header */}
    {activeRunState?.browser_result && (
      <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p className="text-sm text-neutral-400 mb-1">Browser Test</p>
          <p className="text-sm text-neutral-200">{activeRunState.browser_result.summary}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-4">
          <span className="text-xs text-neutral-500">
            {Math.round(activeRunState.browser_result.score * 100)}%
          </span>
          {activeRunState.browser_result.passed ? (
            <span className="flex items-center gap-1 text-xs text-green-400 bg-green-400/10 border border-green-400/20 px-2 py-1 rounded-full">
              <CheckCircle2 size={12} /> Passed
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-red-400 bg-red-400/10 border border-red-400/20 px-2 py-1 rounded-full">
              <AlertCircle size={12} /> Failed
            </span>
          )}
        </div>
      </div>
    )}

    {/* Assertions list */}
    {activeRunState?.browser_result?.assertions?.length > 0 && (
      <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
        <div className="bg-neutral-900 border-b border-neutral-800 p-4">
          <h3 className="text-sm font-medium text-neutral-300">
            Assertions ({activeRunState.browser_result.assertions.filter((a: BrowserAssertion) => a.passed).length}/
            {activeRunState.browser_result.assertions.length} passed)
          </h3>
        </div>
        <div className="divide-y divide-neutral-800">
          {activeRunState.browser_result.assertions.map((assertion: BrowserAssertion, i: number) => (
            <div key={i} className="flex items-start gap-3 p-3">
              {assertion.passed ? (
                <CheckCircle2 size={14} className="text-green-400 mt-0.5 shrink-0" />
              ) : (
                <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
              )}
              <div className="min-w-0">
                <p className="text-sm text-neutral-200">{assertion.description}</p>
                {assertion.selector && (
                  <p className="text-xs text-neutral-500 font-mono mt-0.5">{assertion.selector}</p>
                )}
                {!assertion.passed && assertion.actual && (
                  <p className="text-xs text-red-400 mt-0.5">actual: {assertion.actual}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    )}

    {/* Video player */}
    {activeRunState?.video_path && (
      <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
        <div className="bg-neutral-900 border-b border-neutral-800 p-4">
          <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
            <Play size={16} className="text-blue-400" /> Video Recording
          </h3>
        </div>
        <div className="p-4 flex justify-center bg-black">
          <video
            controls
            className="max-w-full max-h-[400px] rounded border border-neutral-800"
            src={apiUrl(`/api/runs/${activeRunState.run_id}/video`)}
          >
            Your browser does not support the video tag.
          </video>
        </div>
      </div>
    )}

    {/* Screenshots strip */}
    {activeRunState?.browser_result?.screenshots?.length > 0 && (
      <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
        <div className="bg-neutral-900 border-b border-neutral-800 p-4">
          <h3 className="text-sm font-medium text-neutral-300">
            Screenshots ({activeRunState.browser_result.screenshots.length})
          </h3>
        </div>
        <div className="p-4 flex gap-3 overflow-x-auto">
          {activeRunState.browser_result.screenshots.map((absPath: string, i: number) => {
            const filename = absPath.split(/[\\/]/).pop() ?? absPath;
            return (
              <img
                key={i}
                src={apiUrl(`/api/runs/${activeRunState.run_id}/screenshots/${filename}`)}
                alt={filename}
                className="h-32 w-auto rounded border border-neutral-700 shrink-0 object-cover cursor-pointer hover:border-neutral-500 transition-colors"
                title={filename}
                onClick={() => window.open(
                  apiUrl(`/api/runs/${activeRunState.run_id}/screenshots/${filename}`),
                  "_blank"
                )}
              />
            );
          })}
        </div>
      </div>
    )}

  </div>
)}
```

### 7c — Add `BrowserAssertion` import to the component

At the top of `IssueDetailModal.tsx`, update the types import:
```tsx
import type { Issue, Project, PlanResult, RunState, BrowserAssertion } from "../types";
```

Lucide icons `CheckCircle2` and `AlertCircle` are already imported in `App.tsx` — verify they're also imported in `IssueDetailModal.tsx` (or add them).

---

## Step 8 — `tests/test_browser_validator.py`: New test file

### Unit tests: `TestDispatchBrowserTool` (mock `page` via `AsyncMock`)
- `test_navigate_returns_url_and_title`
- `test_assert_element_pass` — locator count=1, text matches → `passed=True`, assertion appended
- `test_assert_element_fail_not_found` — locator count=0 → `passed=False`, `actual="element not found"`
- `test_assert_url_pass` / `test_assert_url_fail`
- `test_take_screenshot_increments_counter` — two calls → `counter[0]==2`, 2 entries in `screenshots`
- `test_mark_done_returns_is_done_true`
- `test_unknown_tool_returns_error`
- `test_playwright_exception_returns_error_json` — `page.goto` raises → `{"error": ...}`, `is_done=False`

### Integration tests: `TestBrowserValidatorRun` (mock provider + mock Playwright context)
- `test_disabled_returns_none`
- `test_playwright_import_error_returns_none`
- `test_successful_run_returns_browser_test_result` — navigate → assert_element → mark_done
- `test_failed_assertion_lowers_score` — 2 assertions, 1 fails → `score==0.5`, `passed=False`
- `test_max_steps_stops_loop` — provider always returns navigate, never mark_done
- `test_result_video_path_is_set`

### Type tests: `TestBrowserTypes`
- `test_browser_assertion_defaults`
- `test_browser_test_result_round_trip` — JSON round-trip via `model_dump_json`
- `test_run_state_browser_result_field`
- `test_run_state_json_round_trip_with_browser_result`

---

## Known edge cases addressed

- **SPA `networkidle` timeout**: caught in `_dispatch_browser_tool`, returned as error JSON — loop continues.
- **Multiple tool calls per turn**: inner `for tc in response.tool_calls` loop; on `mark_done`, result appended before `break`.
- **Video file timing**: Playwright writes `.webm` only after `context.close()`. `video_path` is pre-set; file is ready before `board_updater` runs (Step 6 is after Step 4).
- **Screenshot path traversal**: server endpoint uses `os.path.realpath` to verify path stays inside `run_dir` before serving.
- **No assertions made**: if LLM calls `mark_done` without any `assert_*` calls, `score` is `1.0` if `passed=True`, else `0.0`.
- **`screenshots` paths are absolute (server-side)**: UI extracts just the filename via `.split(/[\\/]/).pop()` and constructs the API URL.

---

## Implementation order (dependencies)

```
1. talon/types.py          — foundation; everything else imports from here
2. talon/skills/browser_validator.py  — imports BrowserAssertion, BrowserTestResult
3. talon/loop.py           — imports BrowserTestResult indirectly via state
4. talon/server.py         — add screenshot endpoint (independent)
5. .env.example            — add env vars (independent)
6. ui/src/types.ts         — add TS interfaces (independent)
7. ui/src/components/IssueDetailModal.tsx  — consumes BrowserAssertion type
8. tests/test_browser_validator.py  — new test file (after step 2)
```

---

## Verification

### Unit tests (no browser, no API key)
```bash
pytest tests/test_browser_validator.py -v
pytest tests/ -v   # regression check
```

### Type check
```bash
mypy talon/types.py talon/skills/browser_validator.py talon/loop.py talon/server.py
```

### Manual backend smoke test
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
# Expected: BrowserTestResult(passed=True, score=1.0, assertions=[...], video_path='...')
```

### UI smoke test (full loop)
```bash
talon serve   # start the web UI
# In another terminal:
talon run "The homepage should load and display a directory listing" \
  --url http://localhost:8080 --skip-board
# Open http://localhost:8080, find the run card, click it
# → "Verification" tab should appear with assertions list, video, and screenshot strip
```
