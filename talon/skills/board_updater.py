"""
board-updater skill
-------------------
Posts the run result (verdict, video link, PR URL) to Linear or GitHub Projects.

Linear:          Set LINEAR_API_KEY + LINEAR_TEAM_ID in .env
GitHub Projects: Set GITHUB_TOKEN + GITHUB_REPO + GITHUB_PROJECT_NUMBER in .env

Both can be active simultaneously.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime

from rich.console import Console

from talon.db import sync_get_setting
from talon.types import RunState, RunStatus

console = Console()

LINEAR_API_KEY = os.getenv("LINEAR_API_KEY")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
_pn = os.getenv("GITHUB_PROJECT_NUMBER", "")
GITHUB_PROJECT_NUMBER: int | None = int(_pn) if _pn.isdigit() else None


def _get_github_token() -> str:
    return os.getenv("GITHUB_TOKEN") or sync_get_setting("github_token") or ""


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


def _build_body(payload: dict) -> str:
    lines = [
        f"**Run ID:** `{payload['run_id']}`",
        f"**Score:** {payload['score']}",
        f"**Iterations:** {payload['iterations']}",
    ]
    if payload["pr_url"]:
        lines.append(f"**PR:** {payload['pr_url']}")
    if payload["video_url"]:
        lines.append(f"**Video:** {payload['video_url']}")
    return "\n".join(lines)


async def _post_to_linear(payload: dict) -> str | None:
    if not LINEAR_API_KEY or not LINEAR_TEAM_ID:
        return None
    try:
        title = f"[{payload['status'].upper()}] {payload['goal'][:60]}"
        body_escaped = _build_body(payload).replace("\n", "\\n")
        mutation = (
            "mutation { issueCreate(input: {"
            f' teamId: "{LINEAR_TEAM_ID}"'
            f' title: "{title}"'
            f' description: "{body_escaped}"'
            " }) { issue { url } } }"
        )
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


def _graphql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {_get_github_token()}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


async def _post_to_github_projects(payload: dict) -> str | None:
    """Add a draft issue to GitHub Projects v2. Returns the project URL."""
    if not _get_github_token() or not GITHUB_REPO or not GITHUB_PROJECT_NUMBER:
        return None
    try:
        owner, repo = GITHUB_REPO.split("/", 1)
    except ValueError:
        console.print(f"  [red]GITHUB_REPO must be 'owner/repo', got: {GITHUB_REPO}[/red]")
        return None

    try:
        result = _graphql(
            """
            query($owner: String!, $repo: String!, $number: Int!) {
              repository(owner: $owner, name: $repo) {
                projectV2(number: $number) { id url }
              }
            }
            """,
            {"owner": owner, "repo": repo, "number": GITHUB_PROJECT_NUMBER},
        )
        project = result["data"]["repository"]["projectV2"]
        project_id = project["id"]
        project_url = project["url"]

        title = f"[{payload['status'].upper()}] {payload['goal'][:60]}"
        _graphql(
            """
            mutation($projectId: ID!, $title: String!, $body: String!) {
              addProjectV2DraftIssue(input: {
                projectId: $projectId
                title: $title
                body: $body
              }) { projectItem { id } }
            }
            """,
            {
                "projectId": project_id,
                "title": title,
                "body": _build_body(payload),
            },
        )
        return project_url

    except urllib.error.HTTPError as e:
        err = e.read().decode()
        console.print(f"  [red]GitHub Projects post failed ({e.code}): {err[:200]}[/red]")
        return None
    except Exception as e:
        console.print(f"  [red]GitHub Projects post failed: {e}[/red]")
        return None


async def run(
    state: RunState,
    video_path: str | None = None,
    pr_url: str | None = None,
) -> str | None:
    """
    Post run results to Linear and/or GitHub Projects.
    Returns the first board item URL obtained, or None if nothing is configured.
    """
    video_url = f"file://{video_path}" if video_path else None
    payload = _format_payload(state, video_url, pr_url)

    status_color = "green" if state.status == RunStatus.PASSED else "red"
    console.print(
        f"\n[bold blue]board-updater[/bold blue] "
        f"[{status_color}]{state.status}[/{status_color}] "
        f"score={payload['score']}"
    )

    board_url: str | None = None

    if LINEAR_API_KEY:
        url = await _post_to_linear(payload)
        if url:
            console.print(f"  [green]Linear: {url}[/green]")
            board_url = board_url or url

    if _get_github_token() and GITHUB_PROJECT_NUMBER:
        url = await _post_to_github_projects(payload)
        if url:
            console.print(f"  [green]GitHub Projects: {url}[/green]")
            board_url = board_url or url

    if not board_url:
        console.print(
            "  [dim](no board configured — set LINEAR_API_KEY or "
            "GITHUB_TOKEN + GITHUB_PROJECT_NUMBER)[/dim]"
        )

    return board_url
