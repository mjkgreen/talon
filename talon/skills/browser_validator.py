"""
browser-validator skill
-----------------------
Spins up a Playwright browser, navigates the app, records a video
proof-of-work, and takes screenshots at goal-relevant URLs.

The LLM is asked which paths to visit based on the goal; it then visits
each one and records the session as a .webm video.

To enable:
  pip install talon-agent[browser]
  playwright install chromium
  Set BROWSER_VALIDATOR_ENABLED=true in .env
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urljoin

from rich.console import Console

from talon.types import RunState

console = Console()

ENABLED = os.getenv("BROWSER_VALIDATOR_ENABLED", "false").lower() == "true"


async def _get_nav_paths(goal: str, app_url: str) -> list[str]:
    """Ask the LLM which URL paths to visit to validate the goal."""
    from talon.providers import get_provider

    provider = get_provider("reviewer")
    prompt = (
        f"App URL: {app_url}\n"
        f"Goal: {goal}\n\n"
        "List the URL paths to visit to verify this goal was achieved. "
        'Output a JSON array of path strings only, e.g. ["/", "/health"]. '
        "Include at most 5 paths. No prose, no markdown fences."
    )
    response = await provider.chat(
        system="You are a QA engineer. Output only valid JSON.",
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        max_tokens=256,
    )
    raw = (response.text or '["/"]\n').strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        paths = json.loads(raw)
        return [p for p in paths if isinstance(p, str)][:5] or ["/"]
    except (json.JSONDecodeError, TypeError):
        return ["/"]


async def run(state: RunState, app_url: str, runs_dir: str) -> str | None:
    """
    Navigate the app at app_url, visit goal-relevant paths, and record
    a video walkthrough. Returns the local .webm path, or None on failure.
    """
    if not ENABLED:
        console.print(
            "\n[dim]browser-validator[/dim] "
            "[dim](disabled — set BROWSER_VALIDATOR_ENABLED=true)[/dim]"
        )
        return None

    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError:
        console.print(
            "\n[yellow]browser-validator[/yellow] Playwright not installed. "
            "Run: pip install 'talon-agent[browser]' && playwright install chromium"
        )
        return None

    console.print(f"\n[bold green]browser-validator[/bold green] recording {app_url}")

    nav_paths = await _get_nav_paths(state.goal, app_url)
    console.print(f"  Paths to visit: {nav_paths}")

    video_dir = Path(runs_dir) / state.run_id
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = str(video_dir / "proof.webm")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(
            record_video_dir=str(video_dir),
            record_video_size={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        try:
            for i, path in enumerate(nav_paths):
                url = urljoin(app_url.rstrip("/") + "/", path.lstrip("/"))
                console.print(f"  [{i + 1}/{len(nav_paths)}] {url}")
                try:
                    await page.goto(url, timeout=15_000)
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                    shot = str(video_dir / f"screenshot-{i:02d}-{path.strip('/') or 'root'}.png")
                    await page.screenshot(path=shot, full_page=True)
                except Exception as e:
                    console.print(f"  [yellow]  ↳ {url}: {e}[/yellow]")
        finally:
            await context.close()
            await browser.close()

    console.print(f"  [green]Video saved: {video_path}[/green]")
    return video_path
