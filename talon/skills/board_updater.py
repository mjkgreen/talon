"""
board-updater skill
-------------------
Posts the run result (verdict, video link, PR URL) to Linear or GitHub Projects.

Phase 1: stub — prints the payload and returns None.
Phase 2: implement Linear API + GitHub Projects API calls.

Linear:  Set LINEAR_API_KEY + LINEAR_TEAM_ID in .env
GitHub:  Set GITHUB_TOKEN + GITHUB_REPO in .env
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import anthropic
from rich.console import Console

from talon.types import RunState, RunStatus

console = Console()

LINEAR_API_KEY = os.getenv("LINEAR_API_KEY")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")


def _format_payload(state: RunState, video_url: str | None, pr_url: str | None) -> dict:
    last_review = state.review_results[-1] if state.review_results else None
    return {
        "run_id": state.run_id,
        "goal": state.goal,
        "status": state.status,
        "iterations": state.iteration,
        "score": last_review.score if last_review else None,
        "verdict": last_review.verdict if last_review else None,
        "video_url": video_url,
        "pr_url": pr_url,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def _post_to_linear(payload: dict) -> str | None:
    """Post a comment/update to Linear. Returns issue URL or None."""
    if not LINEAR_API_KEY or not LINEAR_TEAM_ID:
        return None

    try:
        import urllib.request

        title = f"[{payload['status'].upper()}] {payload['goal'][:60]}"
        body = (
            f"**Run ID:** {payload['run_id']}\n"
            f"**Score:** {payload['score']}\n"
            f"**Iterations:** {payload['iterations']}\n"
        )
        if payload["video_url"]:
            body += f"**Video:** {payload['video_url']}\n"
        if payload["pr_url"]:
            body += f"**PR:** {payload['pr_url']}\n"

        body_escaped = body.replace("\n", "\\n")
        mutation = f"""
        mutation {{
          issueCreate(input: {{
            teamId: "{LINEAR_TEAM_ID}"
            title: "{title}"
            description: "{body_escaped}"
          }}) {{
            issue {{ url }}
          }}
        }}
        """
        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=json.dumps({"query": mutation}).encode(),
            headers={
                "Authorization": LINEAR_API_KEY,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("data", {}).get("issueCreate", {}).get("issue", {}).get("url")
    except Exception as e:
        console.print(f"  [red]Linear post failed: {e}[/red]")
        return None


async def run(
    state: RunState,
    video_path: str | None = None,
    pr_url: str | None = None,
) -> str | None:
    """
    Post run results to Linear or GitHub Projects.
    Returns the board item URL, or None if not configured.
    """
    video_url = f"file://{video_path}" if video_path else None
    payload = _format_payload(state, video_url, pr_url)

    console.print(f"\n[bold blue]board-updater[/bold blue] status={state.status}")
    console.print(json.dumps(payload, indent=2, default=str))

    board_url: str | None = None

    if LINEAR_API_KEY:
        board_url = await _post_to_linear(payload)
        if board_url:
            console.print(f"  [green]Posted to Linear: {board_url}[/green]")
    else:
        console.print(
            "  [dim](Linear/GitHub not configured — set LINEAR_API_KEY or GITHUB_TOKEN)[/dim]"
        )

    return board_url
