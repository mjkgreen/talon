"""
workspace-cleaner skill
-----------------------
Runs after a successful execution but before PR creation.
Identifies and cleans up scratchpads, debug scripts, and temporary
artifacts that shouldn't be committed to the repository.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console

from talon.providers import get_provider
from talon.types import RunState

console = Console()

_CLEANER_SYSTEM = """\
You are an expert repository cleaner.
A coding agent has just finished implementing a task. You are reviewing the git status
to ensure no temporary files, debug scripts, logs, or scratchpads are committed.

You will be given the original goal and the output of `git status --porcelain`.
Analyze the untracked and modified files.

Return ONLY a JSON object specifying which files should be deleted and which should be added to .gitignore.
Do not delete source code, test files that belong to the test suite, configuration, or intended artifacts.
ONLY delete obvious scratchpads (e.g. `test_script.py`, `debug.log`, `temp.json`, `run.sh`).

Schema:
{
  "files_to_delete": ["path/to/temp.py"],
  "files_to_gitignore": ["path/to/.env.local"]
}
"""


class _CleanerDecision(BaseModel):
    files_to_delete: list[str] = []
    files_to_gitignore: list[str] = []


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        result = subprocess.CompletedProcess(args, returncode=1)
        result.stdout = ""
        result.stderr = f"directory not found: {cwd}"
        return result


async def run(state: RunState) -> None:
    """
    Review uncommitted changes in the workspace and clean up temp files.
    """
    if not state.workspace:
        return

    # Check git status for untracked/modified files
    status_cmd = _git(["status", "--porcelain"], state.workspace)
    if status_cmd.returncode != 0:
        return
        
    status_output = status_cmd.stdout.strip()
    if not status_output:
        return  # No changes

    untracked_files = set()
    for line in status_output.splitlines():
        if line.startswith("?? ") or line.startswith("A ") or line.startswith("AM "):
            untracked_files.add(line[3:].strip().strip('"'))

    provider = get_provider("refiner")  # Using refiner since it's a fast reasoning model
    
    prompt = (
        f"Original Goal: {state.goal}\n\n"
        f"Git Status (--porcelain):\n{status_output}\n\n"
        "Identify temporary debug scripts and scratchpads. Output JSON."
    )

    console.print("\n[bold yellow]workspace-cleaner[/bold yellow] reviewing changes...")
    
    response = await provider.chat(
        system=_CLEANER_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        tools=[],
        max_tokens=1024,
    )
    
    raw = (response.text or "").strip()
    
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end+1]
            
    try:
        data = json.loads(raw)
        decision = _CleanerDecision.model_validate(data)
    except (json.JSONDecodeError, ValueError) as e:
        console.print(f"  [yellow]Failed to parse cleaner JSON: {e}[/yellow]")
        return

    workspace_path = Path(state.workspace)
    deleted = []
    ignored = []

    # Handle deletions
    for file_path in decision.files_to_delete:
        if file_path not in untracked_files:
            console.print(f"  [dim]Skipping deletion of '{file_path}' (not an untracked file)[/dim]")
            continue
            
        full_path = workspace_path / file_path
        # Safety check: ensure we're inside the workspace
        try:
            full_path = full_path.resolve()
            if workspace_path.resolve() in full_path.parents and full_path.exists():
                if full_path.is_file():
                    full_path.unlink()
                    deleted.append(file_path)
                elif full_path.is_dir():
                    # Just skip directories for safety, they shouldn't usually be scratchpads
                    pass
        except Exception:
            pass

    # Handle gitignore
    if decision.files_to_gitignore:
        gitignore_path = workspace_path / ".gitignore"
        try:
            with open(gitignore_path, "a") as f:
                f.write("\n# Auto-ignored by Talon workspace-cleaner\n")
                for item in decision.files_to_gitignore:
                    if item not in untracked_files:
                        console.print(f"  [dim]Skipping gitignore of '{item}' (not a new untracked/added file)[/dim]")
                        continue
                    _git(["rm", "--cached", "-q", item], str(workspace_path))
                    f.write(f"{item}\n")
                    ignored.append(item)
        except Exception:
            pass
            
    if deleted:
        console.print(f"  [yellow]Deleted temporary files:[/yellow] {', '.join(deleted)}")
    if ignored:
        console.print(f"  [yellow]Added to .gitignore:[/yellow] {', '.join(ignored)}")
        
    if not deleted and not ignored:
        console.print("  [dim]No cleanup needed.[/dim]")
