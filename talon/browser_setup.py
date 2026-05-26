"""
Ensure playwright Chromium browsers are available at runtime.

Called once at server startup as a background task so browser validation
works out of the box in the packaged exe — no manual `playwright install`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def _chromium_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def _install_chromium() -> None:
    try:
        from playwright._impl._driver import compute_driver_executable

        driver = compute_driver_executable()

        # get_driver_env was added in playwright ~1.30; fall back to os.environ.
        try:
            from playwright._impl._driver import get_driver_env

            env = get_driver_env()
        except ImportError:
            env = os.environ.copy()

        result = subprocess.run(
            [str(driver), "install", "chromium"],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            log.info("playwright: chromium installed successfully")
        else:
            log.warning("playwright: chromium install failed:\n%s", result.stderr)
    except Exception as exc:
        log.warning("playwright: chromium install failed: %s", exc)


async def ensure_chromium() -> None:
    """Download Chromium in a background thread if it is not already present."""
    if _chromium_installed():
        return
    log.info("playwright: chromium not found — installing in background (first run)")
    await asyncio.to_thread(_install_chromium)
