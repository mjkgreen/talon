"""
CLI entry point for the autonomous agent system.

Usage:
  talon run "Add user authentication to the Express API"
  talon run "..." --working-dir ./my-project --url http://localhost:3000
  talon list
  talon review <run-id>
  talon cleanup <run-id>
  talon serve [--port 8080]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

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
        color = "green" if status == "passed" else "red"
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
        working_dir = None
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
        console.print("Commands: run, list, review, cleanup, serve")
        sys.exit(1)


if __name__ == "__main__":
    main()
