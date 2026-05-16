"""
browser-validator skill
-----------------------
Spins up a Playwright browser, navigates the app, and records a video
proof-of-work. Returns the path to the recorded video.

Phase 1: stub — logs intent and returns None.
Phase 2: install playwright, implement recording.

To enable:
  pip install playwright
  playwright install chromium
  Set BROWSER_VALIDATOR_ENABLED=true in .env
"""
from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console

from talon.types import RunState

console = Console()

ENABLED = os.getenv("BROWSER_VALIDATOR_ENABLED", "false").lower() == "true"


async def run(state: RunState, app_url: str, runs_dir: str) -> str | None:
    """
    Navigate the app at app_url and record a video walkthrough.
    Returns the local path to the video file, or None if disabled/failed.
    """
    if not ENABLED:
        console.print(
            "\n[dim]browser-validator[/dim] [dim](disabled — set BROWSER_VALIDATOR_ENABLED=true)[/dim]"
        )
        return None

    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError:
        console.print(
            "\n[yellow]browser-validator[/yellow] Playwright not installed. "
            "Run: pip install playwright && playwright install chromium"
        )
        return None

    console.print(f"\n[bold green]browser-validator[/bold green] recording {app_url}")
    video_path = str(Path(runs_dir) / state.run_id / "proof.webm")
    Path(video_path).parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(
            record_video_dir=str(Path(video_path).parent),
            record_video_size={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        try:
            await page.goto(app_url, timeout=15_000)
            await page.wait_for_load_state("networkidle", timeout=10_000)
            # TODO: add goal-specific navigation steps
            await page.screenshot(path=str(Path(video_path).parent / "screenshot.png"))
        finally:
            await context.close()
            await browser.close()

    console.print(f"  Video saved: {video_path}")
    return video_path
