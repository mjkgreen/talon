"""
pr-creator skill
----------------
After a passing run, commits any workspace changes, pushes an agent branch,
and opens a GitHub pull request.

Required env vars (or DB settings):
  GITHUB_TOKEN   — personal access token or app token with repo + pull-request write
  GITHUB_REPO    — "owner/repo" (e.g. "acme/my-app"); auto-detected from git
                   remote when not set

Optional:
  GITHUB_BASE_BRANCH — target branch for the PR (default: "main")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from rich.console import Console

from talon.db import sync_get_setting
from talon.types import RunState

console = Console()

GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "main")


def _get_github_token() -> str:
    return sync_get_setting("github_token") or os.getenv("GITHUB_TOKEN", "")


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        result = subprocess.CompletedProcess(args, returncode=1)
        result.stdout = ""
        result.stderr = f"directory not found: {cwd}"
        return result


def _detect_github_repo(workspace: str) -> str | None:
    """Infer 'owner/repo' from the git remote URL when GITHUB_REPO is not set."""
    result = _git(["remote", "get-url", "origin"], workspace)
    if result.returncode != 0:
        return None
    m = re.search(r"github\.com[:/]([^/]+/[^/\s]+?)(?:\.git)?$", result.stdout.strip())
    return m.group(1) if m else None


def _goal_to_slug(goal: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")[:45].rstrip("-")
    return slug or "task"


def _commit_and_push(workspace: str, run_id: str, goal: str) -> str | None:
    """Stage uncommitted changes, commit, push. Returns branch name or None on failure.

    Handles two cases:
    - Worktree mode: already on talon/<slug>-{run_id} branch → commit + push.
    - Direct mode: on the user's own branch → stash, create agent branch,
      pop stash, commit + push, return to original branch.
    """
    agent_branch = f"talon/{_goal_to_slug(goal)}-{run_id[:6]}"

    status = _git(["status", "--porcelain"], workspace)
    if status.returncode != 0:
        console.print(f"  [red]git status failed: {status.stderr.strip()}[/red]")
        return None

    current = _git(["branch", "--show-current"], workspace)
    current_branch = current.stdout.strip() if current.returncode == 0 else ""

    on_agent_branch = current_branch == agent_branch or current_branch == f"talon/run-{run_id}"
    has_changes = bool(status.stdout.strip())

    if not on_agent_branch:
        # Direct workspace: move changes to a fresh agent branch without
        # disturbing the user's working branch.
        if has_changes:
            stash = _git(["stash", "push", "-m", f"talon-{run_id}"], workspace)
            if stash.returncode != 0:
                console.print(f"  [red]git stash failed: {stash.stderr.strip()}[/red]")
                return None

        create = _git(["checkout", "-b", agent_branch], workspace)
        if create.returncode != 0:
            console.print(f"  [red]git checkout -b failed: {create.stderr.strip()}[/red]")
            if has_changes:
                _git(["stash", "pop"], workspace)
            return None

        if has_changes:
            pop = _git(["stash", "pop"], workspace)
            if pop.returncode != 0:
                console.print(f"  [red]git stash pop failed: {pop.stderr.strip()}[/red]")
                _git(["checkout", current_branch], workspace)
                return None

    if has_changes:
        _git(["add", "-A"], workspace)
        short = goal[:69] + "…" if len(goal) > 72 else goal
        commit = _git(["commit", "-m", f"feat: {short}\n\n[talon run-id: {run_id}]"], workspace)
        if commit.returncode != 0:
            console.print(f"  [red]git commit failed: {commit.stderr.strip()}[/red]")
            if not on_agent_branch and current_branch:
                _git(["checkout", current_branch], workspace)
            return None

    push = _git(["push", "--set-upstream", "origin", agent_branch], workspace)
    if push.returncode != 0:
        console.print(f"  [red]git push failed: {push.stderr.strip()}[/red]")
        if not on_agent_branch and current_branch:
            _git(["checkout", current_branch], workspace)
        return None

    # Return to user's original branch after the push so their local state is
    # unchanged (they can review and merge the PR from GitHub).
    if not on_agent_branch and current_branch:
        _git(["checkout", current_branch], workspace)

    return agent_branch


def _create_github_pr(branch: str, state: RunState, repo: str) -> str | None:
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

    payload = json.dumps(
        {
            "title": title,
            "body": "\n".join(body_lines),
            "head": branch,
            "base": GITHUB_BASE_BRANCH,
        }
    ).encode()

    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/pulls",
        data=payload,
        headers={
            "Authorization": f"Bearer {_get_github_token()}",
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
    Commit workspace changes, push an agent branch, and open a GitHub PR.
    Returns the PR URL, or None if not applicable or not configured.
    """
    if not state.workspace:
        return None

    token = _get_github_token()
    if not token:
        console.print(
            "  [dim]pr-creator: not authenticated with GitHub — sign in via Settings[/dim]"
        )
        return None

    from talon.workspace import _is_git_repo

    if not _is_git_repo(Path(state.workspace)):
        console.print("  [dim]pr-creator: workspace is not a git repo, skipping[/dim]")
        return None

    repo = GITHUB_REPO or _detect_github_repo(state.workspace)
    if not repo:
        console.print(
            "  [dim]pr-creator: GITHUB_REPO not set and no GitHub remote found, skipping[/dim]"
        )
        return None

    console.print("\n[bold blue]pr-creator[/bold blue] committing and pushing workspace…")

    branch = _commit_and_push(state.workspace, state.run_id, state.goal)
    if not branch:
        console.print("  [yellow]pr-creator: could not push branch, skipping PR creation[/yellow]")
        return None

    pr_url = _create_github_pr(branch, state, repo)
    if pr_url:
        console.print(f"  [green]PR opened: {pr_url}[/green]")
    return pr_url
