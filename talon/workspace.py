"""
Per-run workspace isolation.

Each run gets its own directory so concurrent runs never conflict.

- If base_dir is a git repo  → git worktree add on branch agent/run-<id>
- If base_dir is a plain dir → shutil.copytree into workspace/<id>/
- If base_dir is None        → fresh empty workspace/<id>/

The isolated path is stored in RunState.workspace so it can be inspected
or used for PR creation after the run completes.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()

WORKSPACE_BASE = os.getenv("WORKSPACE_DIR", "./workspace")


def _is_git_repo(path: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(path), capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def setup(run_id: str, base_dir: str | None = None) -> str:
    """
    Create and return an isolated workspace path for this run.

    Args:
        run_id:   Unique run identifier.
        base_dir: Existing project directory to branch from, or None for fresh.
    """
    run_ws = Path(WORKSPACE_BASE) / run_id

    if base_dir is None:
        run_ws.mkdir(parents=True, exist_ok=True)
        console.print(f"  [dim]workspace → {run_ws} (fresh)[/dim]")
        return str(run_ws)

    base = Path(base_dir).resolve()
    run_ws.parent.mkdir(parents=True, exist_ok=True)

    if _is_git_repo(base):
        branch = f"agent/run-{run_id}"
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(run_ws)],
            cwd=str(base), capture_output=True, text=True,
        )
        if result.returncode == 0:
            console.print(f"  [dim]workspace → {run_ws} (worktree branch={branch})[/dim]")
            return str(run_ws)
        console.print(
            f"  [yellow]git worktree failed ({result.stderr.strip()}), falling back to copy[/yellow]"
        )

    shutil.copytree(str(base), str(run_ws), dirs_exist_ok=True)
    console.print(f"  [dim]workspace → {run_ws} (copy of {base})[/dim]")
    return str(run_ws)


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
            cwd=str(Path(base_dir).resolve()), capture_output=True,
        )
    else:
        shutil.rmtree(str(ws), ignore_errors=True)

    console.print(f"  [dim]workspace removed: {ws}[/dim]")
