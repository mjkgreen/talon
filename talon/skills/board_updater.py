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
from datetime import datetime

import httpx
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
    return sync_get_setting("github_token") or os.getenv("GITHUB_TOKEN", "")


def _gif_url(state: RunState) -> str | None:
    """Return a public URL for the browser-validation GIF, if available."""
    public_base = os.getenv("TALON_PUBLIC_URL", "").rstrip("/")
    if public_base and state.browser_result and state.browser_result.gif_path:
        return f"{public_base}/api/runs/{state.run_id}/gif"
    return None


def _build_body(state: RunState) -> str:
    last_review = state.review_results[-1] if state.review_results else None
    score_str = f"{last_review.score:.0%}" if last_review else "N/A"

    lines: list[str] = [
        f"**Run ID:** `{state.run_id}`",
        f"**Status:** {state.status}",
        f"**Score:** {score_str}  |  **Iterations:** {state.iteration}",
    ]

    if state.total_cost_usd:
        total_tok = state.total_input_tokens + state.total_output_tokens
        cache_pct = (
            round(state.total_cache_read_tokens / state.total_input_tokens * 100)
            if state.total_input_tokens > 0 else 0
        )
        tok_str = f"{total_tok / 1000:.1f}k" if total_tok >= 1000 else str(total_tok)
        lines.append(
            f"**Tokens:** {tok_str}  |  **Cache hit:** {cache_pct}%  |  **Cost:** ${state.total_cost_usd:.4f}"
        )

    if state.pr_url:
        lines.append(f"**PR:** {state.pr_url}")

    if state.browser_result:
        br = state.browser_result
        if br.verified_criteria:
            lines.append("\n**Verified:**")
            lines.extend(f"- ✅ {c}" for c in br.verified_criteria)
        if br.failed_criteria:
            lines.append("\n**Failed:**")
            lines.extend(f"- ❌ {c}" for c in br.failed_criteria)
        gif = _gif_url(state)
        if gif:
            lines.append(f"\n![Browser validation]({gif})")
        elif br.summary:
            lines.append(f"\n**Validation:** {br.summary}")

    return "\n".join(lines)


async def _post_to_linear(state: RunState) -> str | None:
    if not LINEAR_API_KEY or not LINEAR_TEAM_ID:
        return None
    try:
        status_label = state.status.upper() if hasattr(state.status, "upper") else str(state.status).upper()
        title = f"[{status_label}] {state.goal[:60]}"
        body_escaped = _build_body(state).replace('"', '\\"').replace("\n", "\\n")
        mutation = (
            "mutation { issueCreate(input: {"
            f' teamId: "{LINEAR_TEAM_ID}"'
            f' title: "{title}"'
            f' description: "{body_escaped}"'
            " }) { issue { url } } }"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.linear.app/graphql",
                content=json.dumps({"query": mutation}).encode(),
                headers={"Authorization": LINEAR_API_KEY, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("issueCreate", {}).get("issue", {}).get("url")
    except Exception as e:
        console.print(f"  [red]Linear post failed: {e}[/red]")
        return None


async def _graphql(query: str, variables: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
            headers={
                "Authorization": f"Bearer {_get_github_token()}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _post_to_github_projects(state: RunState) -> str | None:
    """Add a draft issue to GitHub Projects v2. Returns the project URL."""
    if not _get_github_token() or not GITHUB_REPO or not GITHUB_PROJECT_NUMBER:
        return None
    try:
        owner, repo = GITHUB_REPO.split("/", 1)
    except ValueError:
        console.print(f"  [red]GITHUB_REPO must be 'owner/repo', got: {GITHUB_REPO}[/red]")
        return None

    try:
        result = await _graphql(
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

        status_label = state.status.upper() if hasattr(state.status, "upper") else str(state.status).upper()
        title = f"[{status_label}] {state.goal[:60]}"
        await _graphql(
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
                "body": _build_body(state),
            },
        )
        return project_url

    except Exception as e:
        console.print(f"  [red]GitHub Projects post failed: {e}[/red]")
        return None


async def run(state: RunState) -> str | None:
    """
    Post run results to Linear and/or GitHub Projects.
    Returns the first board item URL obtained, or None if nothing is configured.
    """
    last_review = state.review_results[-1] if state.review_results else None
    score = last_review.score if last_review else None

    status_color = "green" if state.status == RunStatus.PASSED else "red"
    console.print(
        f"\n[bold blue]board-updater[/bold blue] "
        f"[{status_color}]{state.status}[/{status_color}] "
        f"score={score}"
    )

    board_url: str | None = None

    if LINEAR_API_KEY:
        url = await _post_to_linear(state)
        if url:
            console.print(f"  [green]Linear: {url}[/green]")
            board_url = board_url or url

    if _get_github_token() and GITHUB_PROJECT_NUMBER:
        url = await _post_to_github_projects(state)
        if url:
            console.print(f"  [green]GitHub Projects: {url}[/green]")
            board_url = board_url or url

    if not board_url:
        console.print(
            "  [dim](no board configured — set LINEAR_API_KEY or "
            "GITHUB_TOKEN + GITHUB_PROJECT_NUMBER)[/dim]"
        )

    return board_url

