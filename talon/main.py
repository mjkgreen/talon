"""
CLI entry point for the autonomous agent system.

Usage:
  talon run "Add user authentication to the Express API"
  talon run "..." --working-dir ./my-project --url http://localhost:3000
  (defaults to the current directory when --working-dir is omitted)
  talon list
  talon review <run-id>
  talon cleanup <run-id>
  talon pause <run-id>    pause a running loop between iterations
  talon resume <run-id>   resume a paused or failed run from checkpoint
  talon retry <run-id>    alias for resume
  talon serve [--port 8080]
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path

# On Windows the console code page defaults to CP1252, which mangles UTF-8
# box-drawing characters emitted by Rich. Switch to UTF-8 (65001) first, then
# rewrap stdout/stderr so Python also encodes as UTF-8.
if sys.platform == "win32":
    import ctypes

    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

console = Console()

_PROVIDER_KEYS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
]


def _check_env() -> None:
    if not any(os.getenv(k) for k in _PROVIDER_KEYS):
        console.print(
            "[red]Error: no LLM API key found. Set at least one of: "
            + ", ".join(_PROVIDER_KEYS)
            + "[/red]"
        )
        sys.exit(1)


def cmd_run(goal: str, working_dir: str | None, app_url: str | None, skip_board: bool) -> None:
    from talon.loop import run

    _check_env()
    state = asyncio.run(
        run(goal=goal, working_dir=working_dir, app_url=app_url, skip_board=skip_board)
    )
    runs_dir = os.getenv("RUNS_DIR", "./runs")
    console.print(f"\n[dim]Full run saved to: {Path(runs_dir) / state.run_id / 'state.json'}[/dim]")
    if state.workspace:
        console.print(f"[dim]Workspace kept at:  {state.workspace}[/dim]")
    if state.pr_url:
        console.print(f"[green]PR opened:           {state.pr_url}[/green]")
    if state.board_url:
        console.print(f"[green]Board updated:       {state.board_url}[/green]")
    sys.exit(0 if state.status == "passed" else 1)


def cmd_list() -> None:
    runs_dir = Path(os.getenv("RUNS_DIR", "./runs"))
    if not runs_dir.exists():
        console.print("No runs yet.")
        return

    table = Table(title="Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Iter")
    table.add_column("PR")
    table.add_column("Goal")

    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        state_file = run_dir / "state.json"
        if not state_file.exists():
            continue
        data = json.loads(state_file.read_text())
        last_review = data["review_results"][-1] if data["review_results"] else {}
        score = f"{last_review.get('score', 0):.2f}" if last_review else "—"
        status = data["status"]
        color = "green" if status == "passed" else ("yellow" if status == "paused" else "red")
        pr = data.get("pr_url") or "—"
        pr_display = f"[link={pr}]#{pr.split('/')[-1]}[/link]" if pr != "—" else "—"
        table.add_row(
            data["run_id"],
            f"[{color}]{status}[/{color}]",
            score,
            str(data["iteration"]),
            pr_display,
            data["goal"][:50],
        )

    console.print(table)


def cmd_review(run_id: str) -> None:
    runs_dir = Path(os.getenv("RUNS_DIR", "./runs"))
    state_file = runs_dir / run_id / "state.json"
    if not state_file.exists():
        console.print(f"[red]Run not found: {run_id}[/red]")
        sys.exit(1)
    console.print_json(state_file.read_text())


def cmd_cleanup(run_id: str) -> None:
    """Remove the isolated workspace for a completed run."""
    runs_dir = Path(os.getenv("RUNS_DIR", "./runs"))
    state_file = runs_dir / run_id / "state.json"
    if not state_file.exists():
        console.print(f"[red]Run not found: {run_id}[/red]")
        sys.exit(1)

    data = json.loads(state_file.read_text())
    ws = data.get("workspace")
    if not ws:
        console.print(f"[dim]Run {run_id} has no workspace to clean up.[/dim]")
        return

    from talon import workspace

    working_dir = None  # we don't track the original base_dir; teardown handles both cases
    workspace.teardown(run_id, working_dir, ws)

    # Clear workspace field in state
    data["workspace"] = None
    state_file.write_text(json.dumps(data, indent=2))
    console.print(f"[green]Cleaned up workspace for run {run_id}[/green]")


def cmd_pause(run_id: str) -> None:
    """Write a pause sentinel file; the running loop picks it up between iterations."""
    from datetime import datetime

    runs_dir = Path(os.getenv("RUNS_DIR", "./runs"))
    state_file = runs_dir / run_id / "state.json"
    if not state_file.exists():
        console.print(f"[red]Run not found: {run_id}[/red]")
        sys.exit(1)
    data = json.loads(state_file.read_text())
    if data["status"] != "running":
        console.print(f"[yellow]Run {run_id} is not running (status: {data['status']})[/yellow]")
        sys.exit(1)
    sentinel = runs_dir / run_id / "pause.signal"
    sentinel.write_text(datetime.utcnow().isoformat(), encoding="utf-8")
    console.print(f"[green]Pause signal sent to {run_id}.[/green]")
    console.print("[dim]The run will stop after the current iteration completes.[/dim]")


def cmd_resume(run_id: str) -> None:
    """Resume a PAUSED or FAILED run from its last completed checkpoint."""
    from talon.loop import resume

    _check_env()
    try:
        state = asyncio.run(resume(run_id=run_id))
    except (FileNotFoundError, RuntimeError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    runs_dir = os.getenv("RUNS_DIR", "./runs")
    console.print(f"\n[dim]Full run saved to: {Path(runs_dir) / state.run_id / 'state.json'}[/dim]")
    if state.workspace:
        console.print(f"[dim]Workspace at:        {state.workspace}[/dim]")
    sys.exit(0 if state.status == "passed" else 1)


def cmd_retry(run_id: str) -> None:
    """Retry a FAILED run from the last safe checkpoint (alias for resume)."""
    cmd_resume(run_id)


def cmd_serve(port: int) -> None:
    """Start the webhook listener server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed. Run: pip install uvicorn[/red]")
        sys.exit(1)

    _check_env()
    console.print(f"[bold blue]Webhook server[/bold blue] listening on http://0.0.0.0:{port}")
    console.print("  POST /webhook/linear  — Linear issue created")
    console.print("  POST /webhook/github  — GitHub issue opened")
    console.print("  GET  /health          — health check")
    console.print("  GET  /docs            — OpenAPI docs\n")

    from talon.server import app

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        console.print(__doc__)
        return

    cmd = args[0]

    if cmd == "run":
        if len(args) < 2:
            console.print("[red]Usage: talon run <goal>[/red]")
            sys.exit(1)
        goal = args[1]
        working_dir = os.getcwd()
        app_url = None
        skip_board = False
        i = 2
        while i < len(args):
            if args[i] == "--working-dir" and i + 1 < len(args):
                working_dir = args[i + 1]
                i += 2
            elif args[i] == "--url" and i + 1 < len(args):
                app_url = args[i + 1]
                i += 2
            elif args[i] == "--skip-board":
                skip_board = True
                i += 1
            else:
                i += 1
        cmd_run(goal, working_dir, app_url, skip_board)

    elif cmd == "list":
        cmd_list()

    elif cmd == "review":
        if len(args) < 2:
            console.print("[red]Usage: talon review <run-id>[/red]")
            sys.exit(1)
        cmd_review(args[1])

    elif cmd == "cleanup":
        if len(args) < 2:
            console.print("[red]Usage: talon cleanup <run-id>[/red]")
            sys.exit(1)
        cmd_cleanup(args[1])

    elif cmd == "pause":
        if len(args) < 2:
            console.print("[red]Usage: talon pause <run-id>[/red]")
            sys.exit(1)
        cmd_pause(args[1])

    elif cmd == "resume":
        if len(args) < 2:
            console.print("[red]Usage: talon resume <run-id>[/red]")
            sys.exit(1)
        cmd_resume(args[1])

    elif cmd == "retry":
        if len(args) < 2:
            console.print("[red]Usage: talon retry <run-id>[/red]")
            sys.exit(1)
        cmd_retry(args[1])

    elif cmd == "serve":
        port = 8080
        i = 1
        while i < len(args):
            if args[i] == "--port" and i + 1 < len(args):
                port = int(args[i + 1])
                i += 2
            else:
                i += 1
        cmd_serve(port)

    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")
        console.print("Commands: run, list, review, cleanup, pause, resume, retry, serve")
        sys.exit(1)


if __name__ == "__main__":
    main()
