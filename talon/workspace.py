"""
Per-run workspace isolation.

Each run gets its own directory so concurrent runs never conflict.

- If base_dir is a git repo  -> git worktree add on branch talon/run-<id>
- If base_dir is a plain dir -> shutil.copytree into workspace/<id>/
- If base_dir is None        -> fresh empty workspace/<id>/

The isolated path is stored in RunState.workspace so it can be inspected
or used for PR creation after the run completes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()

WORKSPACE_BASE = os.getenv("WORKSPACE_DIR", "./workspace")


def _goal_to_slug(goal: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")[:45].rstrip("-")
    return slug or "task"


def _is_git_repo(path: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(path),
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def setup(
    run_id: str,
    base_dir: str | None = None,
    repo_url: str | None = None,
    repo_branch: str | None = None,
    direct: bool = False,
    goal: str | None = None,
) -> str:
    """
    Create and return an isolated workspace path for this run.

    Args:
        run_id:      Unique run identifier.
        base_dir:    Existing project directory to branch from, or None for fresh.
        repo_url:    URL to git clone.
        repo_branch: Branch to checkout after cloning (None = repo default).
        direct:      If True and base_dir is set, use base_dir as-is (no copy or
                     worktree).  The agents will edit the real files on disk.
    """
    if direct and base_dir:
        base = Path(base_dir).resolve()
        console.print(f"  [dim]workspace -> {base} (direct — editing real files)[/dim]")
        return str(base)

    run_ws = Path(WORKSPACE_BASE) / run_id

    if repo_url:
        run_ws.parent.mkdir(parents=True, exist_ok=True)
        if run_ws.exists():
            shutil.rmtree(run_ws)

        console.print(f"  [dim]Cloning repository for run {run_id}...[/dim]")
        try:
            clone_cmd = ["git", "clone"]
            if repo_branch:
                clone_cmd += ["--branch", repo_branch, "--single-branch"]
            clone_cmd += [repo_url, str(run_ws)]
            subprocess.run(clone_cmd, check=True, capture_output=True, text=True, timeout=120)
            branch_label = f" branch={repo_branch}" if repo_branch else ""
            console.print(f"  [dim]workspace -> {run_ws} (cloned{branch_label})[/dim]")
            return str(run_ws)
        except subprocess.TimeoutExpired:
            shutil.rmtree(run_ws, ignore_errors=True)
            raise RuntimeError(f"git clone timed out after 120 s: {repo_url}")
        except subprocess.CalledProcessError as e:
            console.print(f"  [red]Failed to clone repo: {e.stderr}[/red]")
            # Fall through to the rest of the logic if clone fails

    if base_dir is None:
        run_ws.mkdir(parents=True, exist_ok=True)
        console.print(f"  [dim]workspace -> {run_ws} (fresh)[/dim]")
        return str(run_ws)

    base = Path(base_dir).resolve()
    run_ws.parent.mkdir(parents=True, exist_ok=True)

    if _is_git_repo(base):
        slug = _goal_to_slug(goal) if goal else f"run-{run_id}"
        branch = f"talon/{slug}-{run_id[:6]}"
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(run_ws)],
            cwd=str(base),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print(f"  [dim]workspace -> {run_ws} (worktree branch={branch})[/dim]")
            return str(run_ws)
        console.print(
            f"  [yellow]git worktree failed ({result.stderr.strip()}),"
            " falling back to copy[/yellow]"
        )

    _COPY_IGNORE = shutil.ignore_patterns(
        ".git",
        "node_modules",
        ".next",
        ".nuxt",
        "venv",
        ".venv",
        "__pycache__",
        "*.pyc",
        "dist",
        "build",
        ".tox",
        "workspace",
        "runs",
    )
    shutil.copytree(str(base), str(run_ws), dirs_exist_ok=True, ignore=_COPY_IGNORE)
    console.print(f"  [dim]workspace -> {run_ws} (copy of {base})[/dim]")
    return str(run_ws)


def ensure_planner_clone(
    project_id: int,
    repo_url: str,
    selected_branch: str | None = None,
) -> str:
    """Return a local clone of the repo for the planner to explore.

    Tries to update an existing clone first; falls back to a fresh clone.
    Blocking — call via asyncio.to_thread.
    """
    planner_dir = Path(WORKSPACE_BASE) / f"planner-{project_id}"

    if planner_dir.exists():
        try:
            result = subprocess.run(
                ["git", "pull", "--ff-only", "--quiet"],
                cwd=str(planner_dir),
                capture_output=True,
                timeout=60,
            )
            if result.returncode == 0:
                console.print(f"  [dim]planner clone updated: {planner_dir}[/dim]")
                return str(planner_dir)
        except Exception:
            pass
        shutil.rmtree(str(planner_dir), ignore_errors=True)

    planner_dir.parent.mkdir(parents=True, exist_ok=True)
    clone_cmd = ["git", "clone"]
    if selected_branch:
        clone_cmd += ["--branch", selected_branch, "--single-branch"]
    clone_cmd += [repo_url, str(planner_dir)]

    try:
        subprocess.run(clone_cmd, check=True, capture_output=True, text=True, timeout=120)
        console.print(f"  [dim]planner clone ready: {planner_dir}[/dim]")
        return str(planner_dir)
    except subprocess.TimeoutExpired:
        shutil.rmtree(str(planner_dir), ignore_errors=True)
        raise RuntimeError("git clone timed out after 120 s")
    except subprocess.CalledProcessError as e:
        shutil.rmtree(str(planner_dir), ignore_errors=True)
        raise RuntimeError(f"Failed to clone repo for planner: {e.stderr}")


def teardown(run_id: str, base_dir: str | None, run_workspace: str) -> None:
    """
    Remove the isolated workspace. Called on failed/max-iterations runs.
    Passing runs keep their workspace for inspection and PR creation.
    """
    ws = Path(run_workspace)
    if not ws.exists():
        return

    if base_dir and _is_git_repo(Path(base_dir).resolve()):
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(ws)],
            cwd=str(Path(base_dir).resolve()),
            capture_output=True,
        )
    else:
        shutil.rmtree(str(ws), ignore_errors=True)

    console.print(f"  [dim]workspace removed: {ws}[/dim]")
