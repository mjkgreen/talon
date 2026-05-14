"""
CLI entry point for the autonomous agent system.

Usage:
  python -m src.main run "Add user authentication to the Express API"
  python -m src.main run "..." --working-dir ./my-project --url http://localhost:3000
  python -m src.main review --run-id <id>
  python -m src.main list
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


def _check_env() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]Error: ANTHROPIC_API_KEY not set. Copy .env.example to .env and fill it in.[/red]")
        sys.exit(1)


def cmd_run(goal: str, working_dir: str | None, app_url: str | None, skip_board: bool) -> None:
    from src.loop import run

    _check_env()
    state = asyncio.run(
        run(goal=goal, working_dir=working_dir, app_url=app_url, skip_board=skip_board)
    )

    runs_dir = os.getenv("RUNS_DIR", "./runs")
    run_file = Path(runs_dir) / state.run_id / "state.json"
    console.print(f"\n[dim]Full run saved to: {run_file}[/dim]")
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
    table.add_column("Iterations")
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
        table.add_row(
            data["run_id"],
            f"[{color}]{status}[/{color}]",
            score,
            str(data["iteration"]),
            data["goal"][:60],
        )

    console.print(table)


def cmd_review(run_id: str) -> None:
    runs_dir = Path(os.getenv("RUNS_DIR", "./runs"))
    state_file = runs_dir / run_id / "state.json"
    if not state_file.exists():
        console.print(f"[red]Run not found: {run_id}[/red]")
        sys.exit(1)
    data = json.loads(state_file.read_text())
    console.print_json(json.dumps(data))


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        console.print(__doc__)
        return

    cmd = args[0]

    if cmd == "run":
        if len(args) < 2:
            console.print("[red]Usage: python -m src.main run <goal>[/red]")
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
            console.print("[red]Usage: python -m src.main review <run-id>[/red]")
            sys.exit(1)
        cmd_review(args[1])

    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")
        console.print("Commands: run, list, review")
        sys.exit(1)


if __name__ == "__main__":
    main()
