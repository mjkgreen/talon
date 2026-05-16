"""
Core orchestration loop
-----------------------
executor → reviewer → [pass] → browser-validator → board-updater → done
                    → [fail/needs_work] → refiner → executor (next iteration)
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from src.config import model_config_summary
from src.types import ReviewVerdict, RunState, RunStatus
from src.skills import task_executor, self_reviewer, refiner, browser_validator, board_updater

console = Console()

MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))
RUNS_DIR = os.getenv("RUNS_DIR", "./runs")
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "./workspace")


def _save_state(state: RunState) -> None:
    run_dir = Path(RUNS_DIR) / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(
        state.model_dump_json(indent=2)
    )


def _print_header(goal: str, run_id: str) -> None:
    cfg = model_config_summary()
    model_lines = "\n".join(
        f"  [dim]{role:<14}[/dim] {info['model']}  [dim]({info['source']})[/dim]"
        for role, info in cfg.items()
    )
    console.print(Panel(
        f"[bold]Goal:[/bold] {goal}\n[dim]Run ID: {run_id}[/dim]\n\n{model_lines}",
        title="[bold blue]Autonomous Agent Loop[/bold blue]",
        border_style="blue",
    ))


def _print_footer(state: RunState) -> None:
    color = "green" if state.status == RunStatus.PASSED else "red"
    console.print(Rule(style=color))
    console.print(
        f"[{color}]Status: {state.status}[/{color}]  "
        f"Iterations: {state.iteration}/{MAX_ITERATIONS}  "
        f"Duration: {(state.finished_at - state.started_at).total_seconds():.1f}s"
    )
    if state.final_output:
        console.print(Panel(state.final_output[:500], title="Final output", border_style=color))


async def run(
    goal: str,
    working_dir: str | None = None,
    app_url: str | None = None,
    skip_board: bool = False,
) -> RunState:
    """
    Run the full autonomous loop for the given goal.

    Args:
        goal:        The high-level coding goal.
        working_dir: Directory where agents read/write code.
        app_url:     URL to validate with browser-validator (optional).
        skip_board:  Skip posting to Linear/GitHub.

    Returns:
        RunState with full audit trail.
    """
    working_dir = working_dir or WORKSPACE_DIR
    Path(working_dir).mkdir(parents=True, exist_ok=True)

    state = RunState(goal=goal)
    _print_header(goal, state.run_id)
    _save_state(state)

    refinement = None

    for i in range(1, MAX_ITERATIONS + 1):
        state.iteration = i
        console.print(Rule(f"Iteration {i}/{MAX_ITERATIONS}", style="blue"))

        # --- Step 1: Execute ---
        exec_result = await task_executor.run(
            goal=goal,
            working_dir=working_dir,
            iteration=i,
            refinement=refinement,
        )
        state.executor_results.append(exec_result)
        _save_state(state)

        # --- Step 2: Review ---
        review = await self_reviewer.run(
            goal=goal,
            executor_result=exec_result,
            working_dir=working_dir,
        )
        state.review_results.append(review)
        _save_state(state)

        if review.verdict == ReviewVerdict.PASS:
            state.status = RunStatus.PASSED
            state.final_output = exec_result.aggregated_output
            break

        if i == MAX_ITERATIONS:
            state.status = RunStatus.MAX_ITERATIONS
            state.final_output = exec_result.aggregated_output
            break

        # --- Step 3: Refine (only if more iterations remain) ---
        refinement = await refiner.run(
            goal=goal,
            executor_result=exec_result,
            feedback=review,
        )
        state.refinement_results.append(refinement)
        _save_state(state)

    state.finished_at = datetime.utcnow()

    # --- Step 4: Browser validate (optional) ---
    if app_url and state.status == RunStatus.PASSED:
        video_path = await browser_validator.run(state, app_url, RUNS_DIR)
        state.video_path = video_path
        _save_state(state)

    # --- Step 5: Board update ---
    if not skip_board:
        board_url = await board_updater.run(state, state.video_path)
        state.board_url = board_url
        _save_state(state)

    _print_footer(state)
    return state
