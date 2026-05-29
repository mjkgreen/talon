"""
browser-validator skill
-----------------------
Validates the running app using the browser-use AI agent.

The agent reads the plan's success criteria and navigates + interacts with
the app to verify each one. Produces a GIF walkthrough and video.

Setup:
  pip install -e .
  playwright install chromium

Enable:
  BROWSER_VALIDATOR_ENABLED=true in .env
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
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
    Agent = None  # type: ignore[assignment,misc]
    BrowserProfile = None  # type: ignore[assignment,misc]
    ChatLiteLLM = None  # type: ignore[assignment,misc]
    _BROWSER_USE_AVAILABLE = False

try:
    from playwright.async_api import async_playwright  # type: ignore

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None  # type: ignore[assignment,misc]
    _PLAYWRIGHT_AVAILABLE = False

console = Console()

ENABLED = os.getenv("BROWSER_VALIDATOR_ENABLED", "false").lower() == "true"
MAX_STEPS = int(os.getenv("BROWSER_TEST_MAX_STEPS", "20"))
MAX_FAILURES = int(os.getenv("BROWSER_TEST_MAX_FAILURES", "10"))
ACTION_TIMEOUT = int(os.getenv("BROWSER_ACTION_TIMEOUT", "10000"))


def _discover_routes(workspace: str) -> list[str]:
    """Scan a Next.js workspace and return verified route paths from the filesystem."""
    ws = Path(workspace)
    routes: list[str] = []

    def _app_path_to_route(rel: str) -> str:
        rel = rel.replace("\\", "/")
        # Strip leading 'app/' prefix (relative to the base dir we searched under)
        if rel.startswith("app/"):
            rel = rel[4:]
        # Strip trailing page.* filename
        for suffix in (
            "/page.tsx",
            "/page.ts",
            "/page.jsx",
            "/page.js",
            "page.tsx",
            "page.ts",
            "page.jsx",
            "page.js",
        ):
            if rel.endswith(suffix):
                rel = rel[: -len(suffix)]
                break
        # Strip Next.js route groups like (auth)/ or (tabs)/
        rel = re.sub(r"\([^/]+\)/", "", rel)
        rel = rel.strip("/")
        return "/" + rel if rel else "/"

    def _pages_path_to_route(rel: str) -> str:
        rel = rel.replace("\\", "/")
        if rel.startswith("pages/"):
            rel = rel[6:]
        for ext in (".tsx", ".ts", ".jsx", ".js"):
            if rel.endswith(ext):
                rel = rel[: -len(ext)]
                break
        if rel == "index" or rel.endswith("/index"):
            rel = rel[:-6].rstrip("/") if rel.endswith("/index") else ""
        rel = rel.strip("/")
        return "/" + rel if rel else "/"

    # Support both root-level and src/ variants (e.g. src/app/, src/pages/)
    for base in (ws, ws / "src"):
        app_dir = base / "app"
        if app_dir.is_dir():
            for f in app_dir.rglob("*"):
                if f.is_file() and f.stem == "page" and f.suffix in {".tsx", ".ts", ".jsx", ".js"}:
                    try:
                        rel = str(f.relative_to(base))
                        routes.append(_app_path_to_route(rel))
                    except Exception:
                        pass

        pages_dir = base / "pages"
        if pages_dir.is_dir():
            for f in pages_dir.rglob("*"):
                if not f.is_file() or f.suffix not in {".tsx", ".ts", ".jsx", ".js"}:
                    continue
                if f.stem.startswith("_"):
                    continue
                try:
                    rel = str(f.relative_to(base)).replace("\\", "/")
                    if rel.startswith("pages/api/"):
                        continue
                    routes.append(_pages_path_to_route(rel))
                except Exception:
                    pass

    seen: set[str] = set()
    result: list[str] = []
    for r in routes:
        if r not in seen:
            seen.add(r)
            result.append(r)
    result.sort()
    return result


def _build_task(
    goal: str,
    app_url: str,
    criteria: list[str],
    test_user: str | None,
    test_password: str | None,
    validation_steps: list[str] | None = None,
    known_routes: list[str] | None = None,
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
    routes_section = ""
    if known_routes:
        route_list = "\n".join(f"- {r}" for r in known_routes)
        routes_section = (
            f"\n\nVerified routes (confirmed from the codebase — use these exact paths):\n"
            f"{route_list}\n"
            f"If a navigation step references a path not in this list, "
            f"navigate to the closest matching verified route instead."
        )
    steps_section = ""
    if validation_steps:
        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(validation_steps))
        steps_section = (
            f"\n\nNavigation steps (follow in order — generated from the app's "
            f"routes and UI structure):\n{numbered}"
        )
    nav_instruction = (
        "Follow the navigation steps above in order, then verify each success criterion."
        if validation_steps
        else "Navigate the app, interact as a real user would, and verify each criterion."
    )
    return (
        f"You are a QA engineer validating a web application.\n\n"
        f"App URL: {app_url}\n"
        f"Goal implemented: {goal}\n\n"
        f"Success criteria to verify:\n{criteria_text}"
        f"{routes_section}"
        f"{steps_section}"
        f"{creds}\n\n"
        f"{nav_instruction} "
        f"For each criterion state whether it PASSED (✓) or FAILED (✗) and why.\n\n"
        f"When done, output ONLY this JSON on the final line "
        f"(no markdown fences, no trailing text):\n"
        f'{{"verified": ["<criterion>", ...], '
        f'"failed": ["<criterion>", ...], '
        f'"summary": "<one-sentence outcome>"}}'
    )


def _parse_result(text: str | None, criteria: list[str]) -> tuple[list[str], list[str], str]:
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
                        for kw in [
                            "bundling",
                            "compiling",
                            "loading",
                            "webpack",
                            "metro",
                            "please wait",
                        ]
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
            "Run: pip install -e . && playwright install chromium"
        )
        return None

    console.print(f"\n[bold green]browser-validator[/bold green] {app_url}")

    max_steps = int(os.getenv("BROWSER_TEST_MAX_STEPS", str(MAX_STEPS)))
    max_failures = int(os.getenv("BROWSER_TEST_MAX_FAILURES", str(MAX_FAILURES)))
    console.print(
        f"  [dim]browser-validator[/dim] max_steps={max_steps}  max_failures={max_failures}"
    )
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

    # Fast programmatic route scan (Next.js only) used as a hint for nav_planner
    known_routes: list[str] = []
    if state.workspace:
        try:
            known_routes = _discover_routes(state.workspace)
        except Exception:
            pass

    # Nav planner: workspace-verified navigation steps (highest priority)
    nav_steps: list[str] = []
    if state.workspace:
        try:
            from talon.skills import nav_planner as _nav_planner

            nav_steps = await _nav_planner.run(
                goal=state.goal,
                workspace=state.workspace,
                criteria=criteria,
                app_url=app_url,
                hint_routes=known_routes or None,
            )
        except Exception as e:
            console.print(f"  [yellow]browser-validator[/yellow] nav-planner failed: {e}")

    reviewer_steps = (
        state.review_results[-1].navigation_steps
        if state.review_results and state.review_results[-1].navigation_steps
        else []
    )
    # Priority: nav_planner (workspace-verified) > reviewer steps > plan steps
    validation_steps = (
        nav_steps
        or reviewer_steps
        or (state.plan_result.validation_steps if state.plan_result else [])
    )
    task = _build_task(
        state.goal,
        app_url,
        criteria,
        test_user,
        test_password,
        validation_steps,
        known_routes or None,
    )

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
                    video_path=None,
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
        record_video_dir=str(video_dir),
        record_video_size={"width": 1280, "height": 720},
        storage_state=storage_state,
    )
    llm = ChatLiteLLM(model=resolve_model("reviewer"))
    agent = Agent(
        task=task,
        llm=llm,
        browser_profile=profile,
        max_failures=max_failures,
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

    # Copy screenshots into the run directory and store just the basename.
    # The server route /api/runs/{run_id}/screenshots/{filename} serves from runs/{run_id}/,
    # so files must live there — not in whatever temp dir browser-use chose.
    screenshot_paths: list[str] = []
    for raw in history.screenshot_paths() or []:
        if not raw:
            continue
        src = Path(raw)
        if src.exists():
            dest = video_dir / src.name
            try:
                if src != dest:
                    shutil.copy2(src, dest)
            except Exception:
                dest = src
            screenshot_paths.append(dest.name)
        elif src.name:
            screenshot_paths.append(src.name)

    # Locate and rename recorded video.
    # browser-use 0.12+ saves via its recording watchdog as a UUID-named .mp4;
    # Playwright direct recording saves .webm. Search for both.
    video_path: str | None = None
    _proof_names = {"proof.webm", "proof.mp4"}
    video_candidates = [
        f
        for f in video_dir.rglob("*")
        if f.suffix in {".mp4", ".webm"} and f.name not in _proof_names
    ]
    if video_candidates:
        video_candidates.sort(key=lambda f: f.stat().st_size, reverse=True)
        src_video = video_candidates[0]
        target = video_dir / f"proof{src_video.suffix}"
        try:
            if target.exists():
                target.unlink()
            src_video.rename(target)
        except Exception:
            target = src_video
        video_path = str(target)
        console.print(f"  [dim]browser-validator[/dim] video → {target.name}")

    gif_final = gif_path if Path(gif_path).exists() else None
    if gif_final:
        console.print("  [dim]browser-validator[/dim] GIF → proof.gif")

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
