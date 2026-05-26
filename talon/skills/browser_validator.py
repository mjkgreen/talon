"""
browser-validator skill
-----------------------
Validates the running app using an AI-driven browser agent (browser-use).

The agent reads the plan's success criteria and navigates + interacts with
the app to verify each one. Produces a GIF walkthrough and optional MP4 video.

Runs automatically when --url is passed to `talon run` — no extra env flag needed.

Setup:
  pip install talon-agent[browser]   # installs browser-use + pillow
  playwright install chromium        # or use system Chrome via BROWSER_EXECUTABLE_PATH

Optional MP4 video recording (requires ffmpeg):
  pip install "browser-use[video]"
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from rich.console import Console

from talon.config import resolve_model
from talon.types import BrowserValidationResult, RunState

console = Console()

MAX_STEPS = int(os.getenv("BROWSER_MAX_STEPS", "25"))


def _build_task(goal: str, app_url: str, criteria: list[str]) -> str:
    criteria_text = (
        "\n".join(f"- {c}" for c in criteria)
        if criteria
        else "- The app is running and accessible at the given URL"
    )
    return (
        f"You are a QA engineer validating a web application.\n\n"
        f"App URL: {app_url}\n"
        f"Goal implemented: {goal}\n\n"
        f"Success criteria to verify:\n{criteria_text}\n\n"
        f"Navigate the app and interact with it as a real user would. "
        f"For each criterion: navigate to the relevant page, perform any needed "
        f"interactions (form fills, button clicks, navigation), and confirm the "
        f"expected outcome is present.\n\n"
        f"When you have verified all criteria, output ONLY this JSON on the final line "
        f"(no markdown fences, no trailing text):\n"
        f'{{"verified": ["<criterion text>", ...], '
        f'"failed": ["<criterion text>", ...], '
        f'"summary": "<one sentence outcome>"}}'
    )


def _parse_result(
    text: str | None, criteria: list[str]
) -> tuple[list[str], list[str], str]:
    if not text:
        return [], list(criteria), "Browser agent returned no result"

    # Try the last JSON-shaped object in the output
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

    # Fallback: return raw summary, no structured breakdown
    return [], [], text[:400]


async def run(state: RunState, app_url: str, runs_dir: str) -> BrowserValidationResult | None:
    """
    Launch a browser-use agent to validate the app against plan success criteria.
    Returns a BrowserValidationResult with proof artifacts, or None on hard failure.
    """
    try:
        from browser_use import Agent, BrowserProfile  # type: ignore
        from browser_use.llm.litellm import ChatLiteLLM  # type: ignore
    except ImportError:
        console.print(
            "\n[yellow]browser-validator[/yellow] browser-use not installed. "
            "Run: pip install 'talon-agent[browser]'"
        )
        return None

    console.print(f"\n[bold green]browser-validator[/bold green] {app_url}")

    criteria = state.plan_result.success_criteria if state.plan_result else []
    task = _build_task(state.goal, app_url, criteria)

    video_dir = Path(runs_dir) / state.run_id
    video_dir.mkdir(parents=True, exist_ok=True)
    gif_path = str(video_dir / "proof.gif")

    llm = ChatLiteLLM(model=resolve_model("reviewer"))
    profile = BrowserProfile(
        headless=True,
        record_video_dir=video_dir,
        record_video_size={"width": 1280, "height": 720},
    )

    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser_profile=profile,
            max_failures=3,
            generate_gif=gif_path,
        )

        history = await agent.run(max_steps=MAX_STEPS)

        mp4_files = sorted(video_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        video_path = str(mp4_files[-1]) if mp4_files else None
        shot_paths = [p for p in (history.screenshot_paths() or []) if p]

        final_text = history.final_result()
        verified, failed, summary = _parse_result(final_text, criteria)

        gif_exists = Path(gif_path).exists()
        console.print(
            f"  [green]Done[/green]  "
            f"verified={len(verified)}  failed={len(failed)}  "
            f"gif={'✓' if gif_exists else '✗'}  video={'✓' if video_path else '✗'}"
        )

        return BrowserValidationResult(
            verified_criteria=verified,
            failed_criteria=failed,
            summary=summary,
            video_path=video_path,
            gif_path=gif_path if gif_exists else None,
            screenshot_paths=[str(p) for p in shot_paths],
        )

    except Exception as e:
        console.print(f"  [red]browser-validator failed: {e}[/red]")
        return None
