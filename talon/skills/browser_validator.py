"""
browser-validator skill
-----------------------
Validates the running app using the browser-use AI agent.

The agent reads the plan's success criteria and navigates + interacts with
the app to verify each one. Produces a GIF walkthrough and video.

Setup:
  pip install talon-agent[browser]   # installs browser-use + pillow
  playwright install chromium

Enable:
  BROWSER_VALIDATOR_ENABLED=true in .env
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from rich.console import Console

from talon.config import resolve_model
from talon.types import BrowserAssertion, BrowserTestResult, RunState

try:
    from browser_use import Agent, BrowserProfile
    from browser_use.llm.litellm import ChatLiteLLM

    _BROWSER_USE_AVAILABLE = True
except ImportError:
    _BROWSER_USE_AVAILABLE = False

try:
    from playwright.async_api import async_playwright  # type: ignore

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

console = Console()

ENABLED = os.getenv("BROWSER_VALIDATOR_ENABLED", "false").lower() == "true"
MAX_STEPS = int(os.getenv("BROWSER_TEST_MAX_STEPS", "20"))
ACTION_TIMEOUT = int(os.getenv("BROWSER_ACTION_TIMEOUT", "10000"))


def _build_task(
    goal: str,
    app_url: str,
    criteria: list[str],
    test_user: str | None,
    test_password: str | None,
) -> str:
    criteria_text = (
        "\n".join(f"- {c}" for c in criteria)
        if criteria
        else "- The app is running and accessible at the given URL"
    )
    creds = ""
    if test_user or test_password:
        creds = (
            f"\n\nTest credentials (use if prompted to log in):\n"
            f"  Username/Email: {test_user or '(not set)'}\n"
            f"  Password: {test_password or '(not set)'}"
        )
    return (
        f"You are a QA engineer validating a web application.\n\n"
        f"App URL: {app_url}\n"
        f"Goal implemented: {goal}\n\n"
        f"Success criteria to verify:\n{criteria_text}"
        f"{creds}\n\n"
        f"Navigate the app, interact as a real user would, and verify each criterion. "
        f"For each criterion state whether it PASSED (✓) or FAILED (✗) and why.\n\n"
        f"When done, output ONLY this JSON on the final line "
        f"(no markdown fences, no trailing text):\n"
        f'{{"verified": ["<criterion>", ...], '
        f'"failed": ["<criterion>", ...], '
        f'"summary": "<one-sentence outcome>"}}'
    )


def _parse_result(
    text: str | None, criteria: list[str]
) -> tuple[list[str], list[str], str]:
    """Parse verified/failed criteria lists from the agent's final output."""
    if not text:
        return [], list(criteria), "Browser agent returned no result"

    # Try to extract the trailing JSON object
    matches = list(re.finditer(r'\{[^{}]*"verified"\s*:\s*\[', text, re.DOTALL))
    if matches:
        start = matches[-1].start()
        try:
            data = json.loads(text[start:])
            return (
                data.get("verified", []),
                data.get("failed", []),
                data.get("summary", text[:300]),
            )
        except json.JSONDecodeError:
            pass

    # Fallback: no structured breakdown, return raw summary
    return [], [], text[:400]


async def _preflight_wait(app_url: str, cookie_file: str | None = None) -> None:
    """Open the app once without recording to let the dev server compile/bundle."""
    if not _PLAYWRIGHT_AVAILABLE:
        return
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=["--disable-gpu"])
            ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
            if cookie_file:
                try:
                    raw = json.loads(Path(cookie_file).read_text(encoding="utf-8"))
                    await ctx.add_cookies(raw)
                except Exception:
                    pass
            page = await ctx.new_page()
            try:
                await page.goto(app_url, timeout=ACTION_TIMEOUT)
                await page.wait_for_load_state("load", timeout=ACTION_TIMEOUT)
                for _ in range(45):
                    body = (await page.inner_text("body") or "").strip().lower()
                    if body and not any(
                        kw in body
                        for kw in ["bundling", "compiling", "loading", "webpack", "metro", "please wait"]
                    ):
                        break
                    await asyncio.sleep(1.0)
            except Exception as e:
                console.print(f"  [yellow]browser-validator[/yellow] pre-flight warning: {e}")
            finally:
                await ctx.close()
                await browser.close()
    except Exception as e:
        console.print(f"  [yellow]browser-validator[/yellow] pre-flight error (continuing): {e}")


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
    Run a browser-use Agent to validate the app against the plan's success criteria.
    Returns a BrowserTestResult with artifacts, or None if disabled/unavailable.
    """
    if not ENABLED:
        console.print(
            "\n[dim]browser-validator[/dim] "
            "[dim](disabled — set BROWSER_VALIDATOR_ENABLED=true)[/dim]"
        )
        return None

    if not _BROWSER_USE_AVAILABLE:
        console.print(
            "\n[yellow]browser-validator[/yellow] browser-use not installed. "
            "Run: pip install 'talon-agent[browser]' && playwright install chromium"
        )
        return None

    console.print(f"\n[bold green]browser-validator[/bold green] {app_url}")

    max_steps = int(os.getenv("BROWSER_TEST_MAX_STEPS", str(MAX_STEPS)))
    criteria = state.plan_result.success_criteria if state.plan_result else []
    planned_assertions = list(criteria)

    video_dir = Path(runs_dir) / state.run_id
    video_dir.mkdir(parents=True, exist_ok=True)
    gif_path = str(video_dir / "proof.gif")

    # Cookie injection: convert Playwright cookie array → storage_state JSON
    storage_state: str | None = None
    if cookie_file:
        try:
            raw_cookies = json.loads(Path(cookie_file).read_text(encoding="utf-8"))
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir=str(video_dir)
            )
            json.dump({"cookies": raw_cookies, "origins": []}, tmp)
            tmp.close()
            storage_state = tmp.name
            console.print(f"  [dim]browser-validator[/dim] loaded cookies from {cookie_file}")
        except Exception as e:
            console.print(f"  [yellow]browser-validator[/yellow] cookie load failed: {e}")

    # Pre-flight: trigger dev-server compilation before recording starts
    console.print("  [dim]browser-validator[/dim] pre-flight compilation check…")
    await _preflight_wait(app_url, cookie_file=cookie_file)

    task = _build_task(state.goal, app_url, criteria, test_user, test_password)

    steps = [0]

    async def _on_step(browser_state, agent_output, step_num: int) -> None:
        steps[0] = step_num
        if on_progress:
            await on_progress(
                BrowserTestResult(
                    passed=False,
                    score=0.0,
                    summary=f"Testing… (step {step_num})",
                    assertions=[],
                    planned_assertions=planned_assertions,
                    screenshots=[],
                    video_path=str(video_dir / "proof.webm"),
                    steps=step_num,
                )
            )

    if on_progress:
        await on_progress(
            BrowserTestResult(
                passed=False,
                score=0.0,
                summary="Initializing browser verification…",
                assertions=[],
                planned_assertions=planned_assertions,
                screenshots=[],
                video_path=str(video_dir / "proof.webm"),
                steps=0,
            )
        )

    profile = BrowserProfile(
        headless=True,
        record_video_dir=video_dir,
        record_video_size={"width": 1280, "height": 720},
        storage_state=storage_state,
    )
    llm = ChatLiteLLM(model=resolve_model("reviewer"))
    agent = Agent(
        task=task,
        llm=llm,
        browser_profile=profile,
        max_failures=3,
        generate_gif=gif_path,
        register_new_step_callback=_on_step,
    )

    try:
        history = await agent.run(max_steps=max_steps)
    except Exception as e:
        console.print(f"  [red]browser-validator[/red] agent error: {e}")
        return BrowserTestResult(
            passed=False,
            score=0.0,
            summary=f"Agent error: {e}",
            assertions=[],
            planned_assertions=planned_assertions,
            screenshots=[],
            video_path=None,
            steps=steps[0],
            error=str(e),
        )

    final_text = history.final_result()
    verified, failed_list, summary = _parse_result(final_text, criteria)

    # Build BrowserAssertion objects
    assertions: list[BrowserAssertion] = [
        BrowserAssertion(description=c, passed=True) for c in verified
    ] + [BrowserAssertion(description=c, passed=False) for c in failed_list]

    # Fallback: if JSON parsing failed, use agent's own success flag
    if not verified and not failed_list:
        agent_success = history.is_successful()
        overall_passed = (
            agent_success
            if agent_success is not None
            else "failed" not in (final_text or "").lower()
        )
        score = 1.0 if overall_passed else 0.0
    else:
        total = len(criteria) if criteria else (len(verified) + len(failed_list))
        score = len(verified) / total if total > 0 else 1.0
        overall_passed = len(failed_list) == 0

    # Screenshot paths from history
    screenshot_paths: list[str] = [
        p for p in (history.screenshot_paths() or []) if p is not None
    ]

    # Locate and rename recorded video
    video_path: str | None = None
    webm_files = [f for f in video_dir.glob("*.webm") if f.name != "proof.webm"]
    if webm_files:
        webm_files.sort(key=lambda f: f.stat().st_size, reverse=True)
        target = video_dir / "proof.webm"
        try:
            if target.exists():
                target.unlink()
            webm_files[0].rename(target)
        except Exception:
            target = webm_files[0]
        video_path = str(target)
        console.print(f"  [dim]browser-validator[/dim] video → {target.name}")

    gif_final = gif_path if Path(gif_path).exists() else None
    if gif_final:
        console.print(f"  [dim]browser-validator[/dim] GIF → proof.gif")

    console.print(
        f"  [{'green' if overall_passed else 'red'}]"
        f"{'PASSED' if overall_passed else 'FAILED'}[/{'green' if overall_passed else 'red'}]  "
        f"score={score:.0%}  steps={steps[0]}  verified={len(verified)}  failed={len(failed_list)}"
    )

    return BrowserTestResult(
        passed=overall_passed,
        score=score,
        summary=summary or ("PASSED" if overall_passed else "FAILED"),
        assertions=assertions,
        planned_assertions=planned_assertions,
        screenshots=screenshot_paths,
        video_path=video_path,
        gif_path=gif_final,
        steps=steps[0],
    )
