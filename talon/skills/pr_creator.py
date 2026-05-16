"""
pr-creator skill
----------------
After a passing run, commits any workspace changes, pushes the worktree branch,
and opens a GitHub pull request.

Required env vars (both must be set):
  GITHUB_TOKEN   — personal access token or app token with repo + pull-request write
  GITHUB_REPO    — "owner/repo" (e.g. "acme/my-app")

Optional:
  GITHUB_BASE_BRANCH — target branch for the PR (default: "main")
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from rich.console import Console

from talon.types import RunState

console = Console()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "main")


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        result = subprocess.CompletedProcess(args, returncode=1)
        result.stdout = ""
        result.stderr = f"directory not found: {cwd}"
        return result


def _commit_and_push(workspace: str, run_id: str, goal: str) -> str | None:
    """Stage uncommitted changes, commit, push. Returns branch name or None on failure."""
    branch = f"agent/run-{run_id}"

    status = _git(["status", "--porcelain"], workspace)
    if status.returncode != 0:
        console.print(f"  [red]git status failed: {status.stderr.strip()}[/red]")
        return None

    if status.stdout.strip():
        _git(["add", "-A"], workspace)
        short = goal[:69] + "…" if len(goal) > 72 else goal
        commit = _git(["commit", "-m", f"feat: {short}\n\n[talon run-id: {run_id}]"], workspace)
        if commit.returncode != 0:
            console.print(f"  [red]git commit failed: {commit.stderr.strip()}[/red]")
            return None

    push = _git(["push", "--set-upstream", "origin", branch], workspace)
    if push.returncode != 0:
        console.print(f"  [red]git push failed: {push.stderr.strip()}[/red]")
        return None

    return branch


def _create_github_pr(branch: str, state: RunState) -> str | None:
    """Open a PR via the GitHub REST API. Returns the PR html_url."""
    last_review = state.review_results[-1] if state.review_results else None
    score_str = f"{last_review.score:.0%}" if last_review else "N/A"

    title = state.goal[:72] if len(state.goal) <= 72 else state.goal[:69] + "…"
    body_lines = [
        "## Summary",
        "",
        state.goal,
        "",
        "## Talon run details",
        "",
        f"- **Run ID:** `{state.run_id}`",
        f"- **Iterations:** {state.iteration}",
        f"- **Review score:** {score_str}",
    ]
    if state.video_path:
        body_lines.append(f"- **Video:** `{state.video_path}`")

    payload = json.dumps({
        "title": title,
        "body": "\n".join(body_lines),
        "head": branch,
        "base": GITHUB_BASE_BRANCH,
    }).encode()

    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/pulls",
        data=payload,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("html_url")
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        console.print(f"  [red]GitHub PR creation failed ({e.code}): {err[:200]}[/red]")
        return None
    except Exception as e:
        console.print(f"  [red]GitHub PR creation failed: {e}[/red]")
        return None


async def run(state: RunState, working_dir: str | None) -> str | None:
    """
    Commit workspace changes, push the branch, and open a GitHub PR.
    Returns the PR URL, or None if not applicable or not configured.
    """
    if not state.workspace:
        return None

    if not GITHUB_TOKEN or not GITHUB_REPO:
        console.print("  [dim]pr-creator: GITHUB_TOKEN/GITHUB_REPO not set, skipping[/dim]")
        return None

    from talon.workspace import _is_git_repo
    if not _is_git_repo(Path(state.workspace)):
        console.print("  [dim]pr-creator: workspace is not a git repo, skipping[/dim]")
        return None

    console.print("\n[bold blue]pr-creator[/bold blue] committing and pushing workspace…")

    branch = _commit_and_push(state.workspace, state.run_id, state.goal)
    if not branch:
        console.print("  [yellow]pr-creator: could not push branch, skipping PR creation[/yellow]")
        return None

    pr_url = _create_github_pr(branch, state)
    if pr_url:
        console.print(f"  [green]PR opened: {pr_url}[/green]")
    return pr_url
