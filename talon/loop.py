"""
Core orchestration loop
-----------------------
executor → reviewer → [pass] → browser-validator → board-updater → done
                    → [fail/needs_work] → refiner → executor (next iteration)
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from talon import workspace
from talon.config import model_config_summary
from talon.skills import (
    board_updater,
    browser_validator,
    pr_creator,
    refiner,
    self_reviewer,
    task_executor,
)
from talon.types import ReviewVerdict, RunState, RunStatus

console = Console()

MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))
RUNS_DIR = os.getenv("RUNS_DIR", "./runs")


def _save_state(state: RunState) -> None:
    run_dir = Path(RUNS_DIR) / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _print_header(goal: str, run_id: str) -> None:
    cfg = model_config_summary()
    model_lines = "\n".join(
        f"  [dim]{role:<14}[/dim] {info['model']}  [dim]({info['source']})[/dim]"
        for role, info in cfg.items()
    )
    console.print(
        Panel(
            f"[bold]Goal:[/bold] {goal}\n[dim]Run ID: {run_id}[/dim]\n\n{model_lines}",
            title="[bold blue]Autonomous Agent Loop[/bold blue]",
            border_style="blue",
        )
    )


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
    repo_url: str | None = None,
    skip_board: bool = False,
    on_step: Callable[[RunState], Awaitable[None]] | None = None,
) -> RunState:
    """
    Run the full autonomous loop for the given goal.

    Args:
        goal:        The high-level coding goal.
        working_dir: Existing project dir to branch from (git worktree or copy).
                     None → fresh isolated workspace per run.
        app_url:     URL to validate with browser-validator (optional).
        repo_url:    URL of a git repository to clone.
        skip_board:  Skip posting to Linear/GitHub.

    Returns:
        RunState with full audit trail.
    """
    state = RunState(goal=goal)

    # Save and notify the frontend immediately so the UI transitions out of
    # "Agent is starting up" before workspace setup even begins.
    _save_state(state)
    if on_step:
        await on_step(state)

    try:
        # --- Isolate workspace for this run ---
        # Run in a thread so git/copytree never blocks the asyncio event loop.
        # Blocking the loop freezes WebSocket heartbeats and drops connections.
        run_workspace = await asyncio.to_thread(
            workspace.setup, state.run_id, working_dir, repo_url=repo_url
        )
        state.workspace = run_workspace

        _print_header(goal, state.run_id)
        _save_state(state)
    except Exception as e:
        state.status = RunStatus.FAILED
        state.error = str(e)
        state.finished_at = datetime.utcnow()
        _save_state(state)
        raise

    refinement = None

    try:
        for i in range(1, MAX_ITERATIONS + 1):
            state.iteration = i
            console.print(Rule(f"Iteration {i}/{MAX_ITERATIONS}", style="blue"))

            # --- Step 1: Execute ---
            exec_result = await task_executor.run(
                goal=goal,
                working_dir=run_workspace,
                iteration=i,
                refinement=refinement,
            )
            state.executor_results.append(exec_result)
            _save_state(state)
            if on_step:
                await on_step(state)

            # --- Step 2: Review ---
            review = await self_reviewer.run(
                goal=goal,
                executor_result=exec_result,
                working_dir=run_workspace,
            )
            state.review_results.append(review)
            _save_state(state)
            if on_step:
                await on_step(state)

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
            if on_step:
                await on_step(state)

    except Exception as e:
        state.status = RunStatus.FAILED
        state.error = str(e)
        state.finished_at = datetime.utcnow()
        _save_state(state)
        raise

    state.finished_at = datetime.utcnow()

    # Keep workspace on pass (code is ready for review / PR creation).
    # Remove on fail to avoid accumulating broken directories.
    if state.status != RunStatus.PASSED:
        await asyncio.to_thread(workspace.teardown, state.run_id, working_dir, run_workspace)
        state.workspace = None

    # --- Step 4: Browser validate (optional) ---
    if app_url and state.status == RunStatus.PASSED:
        video_path = await browser_validator.run(state, app_url, RUNS_DIR)
        state.video_path = video_path
        _save_state(state)
    if on_step:
        await on_step(state)

    # --- Step 5: Create PR ---
    if state.status == RunStatus.PASSED:
        pr_url = await pr_creator.run(state, working_dir)
        state.pr_url = pr_url
        _save_state(state)
    if on_step:
        await on_step(state)

    # --- Step 6: Board update ---
    if not skip_board:
        board_url = await board_updater.run(state, state.video_path, state.pr_url)
        state.board_url = board_url
        _save_state(state)
    if on_step:
        await on_step(state)

    _print_footer(state)
    return state
