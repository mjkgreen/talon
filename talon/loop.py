"""
Core orchestration loop
-----------------------
planner → executor → reviewer → [pass] → browser-validator → board-updater → done
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
from talon.providers.litellm_p import _run_accumulator
from talon.skills import (
    board_updater,
    browser_validator,
    planner,
    pr_creator,
    refiner,
    self_reviewer,
    task_executor,
    workspace_cleaner,
)
from talon.types import ExecutorResult, PhaseResult, PlanResult, ReviewVerdict, RunState, RunStatus

console = Console()

MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))
RUNS_DIR = os.getenv("RUNS_DIR", "./runs")


def _save_state(state: RunState) -> None:
    acc = _run_accumulator.get()
    if acc is not None:
        state.total_input_tokens = acc.get("input_tokens", 0)
        state.total_output_tokens = acc.get("output_tokens", 0)
        state.total_cache_read_tokens = acc.get("cache_read_tokens", 0)
        state.total_cost_usd = round(acc.get("cost_usd", 0.0), 6)
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
    total_tok = state.total_input_tokens + state.total_output_tokens
    cache_pct = (
        round(state.total_cache_read_tokens / state.total_input_tokens * 100)
        if state.total_input_tokens > 0
        else 0
    )
    console.print(
        f"[{color}]Status: {state.status}[/{color}]  "
        f"Iterations: {state.iteration}/{MAX_ITERATIONS}  "
        f"Duration: {(state.finished_at - state.started_at).total_seconds():.1f}s  "
        f"[dim]Tokens: {total_tok:,}  Cache: {cache_pct}%  Cost: ${state.total_cost_usd:.4f}[/dim]"
    )
    if state.final_output:
        console.print(Panel(state.final_output[:500], title="Final output", border_style=color))


async def run(
    goal: str,
    working_dir: str | None = None,
    app_url: str | None = None,
    repo_url: str | None = None,
    repo_branch: str | None = None,
    skip_board: bool = False,
    direct_workspace: bool = False,
    create_pr: bool = True,
    plan: PlanResult | None = None,
    on_step: Callable[[RunState], Awaitable[None]] | None = None,
    on_log: Callable[[str], Awaitable[None]] | None = None,
) -> RunState:
    """
    Run the full autonomous loop for the given goal.

    Args:
        goal:             The high-level coding goal.
        working_dir:      Existing project dir to branch from (git worktree or
                          copy).  None → fresh isolated workspace per run.
        app_url:          URL to validate with browser-validator (optional).
        repo_url:         URL of a git repository to clone.
        skip_board:       Skip posting to Linear/GitHub.
        direct_workspace: When True the agents edit working_dir in place — no
                          copy or worktree is created, and teardown is skipped.
        create_pr:        When False skip PR creation after a passing run.

    Returns:
        RunState with full audit trail.
    """
    state = RunState(goal=goal)

    # Start a fresh token/cost accumulator for this run. All LLM calls made
    # within this coroutine (and tasks that inherit this context) will add to it.
    _acc: dict = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_created_tokens": 0,
        "cost_usd": 0.0,
    }
    _acc_token = _run_accumulator.set(_acc)

    # Save and notify the frontend immediately so the UI transitions out of
    # "Agent is starting up" before workspace setup even begins.
    _save_state(state)
    if on_step:
        await on_step(state)

    try:
        try:
            # --- Isolate workspace for this run ---
            # Run in a thread so git/copytree never blocks the asyncio event loop.
            # Blocking the loop freezes WebSocket heartbeats and drops connections.
            run_workspace = await asyncio.to_thread(
                workspace.setup,
                state.run_id,
                working_dir,
                repo_url=repo_url,
                repo_branch=repo_branch,
                direct=direct_workspace,
                goal=goal,
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
            # --- Step 0: Plan ---
            if plan is None:
                plan = await planner.run(goal=goal, working_dir=run_workspace)
            else:
                console.print("\n[bold blue]planner[/bold blue] (using pre-computed backlog plan)")
            state.plan_result = plan
            _save_state(state)
            if on_step:
                await on_step(state)

            for i in range(1, MAX_ITERATIONS + 1):
                state.iteration = i
                _save_state(state)
                if on_step:
                    await on_step(state)
                console.print(Rule(f"Iteration {i}/{MAX_ITERATIONS}", style="blue"))
                if on_log:
                    await on_log(f"=== Iteration {i}/{MAX_ITERATIONS} ===")

                # --- Step 1: Execute ---
                # Save partial state after each phase completes so the UI shows
                # incremental progress without waiting for the full iteration.
                in_progress_exec: ExecutorResult | None = None

                async def on_phase_complete(phase_result: PhaseResult) -> None:
                    nonlocal in_progress_exec
                    prior_phases = in_progress_exec.phases if in_progress_exec else []
                    all_phases = prior_phases + [phase_result]
                    partial_aggregated = "\n\n".join(
                        f"## Phase {ph.phase_index + 1}: {ph.phase_name}\n{ph.aggregated_output}"
                        for ph in all_phases
                    )
                    in_progress_exec = ExecutorResult(
                        goal=goal,
                        phases=all_phases,
                        aggregated_output=partial_aggregated,
                        iteration=i,
                    )
                    if state.executor_results and state.executor_results[-1].iteration == i:
                        state.executor_results[-1] = in_progress_exec
                    else:
                        state.executor_results.append(in_progress_exec)
                    _save_state(state)
                    if on_step:
                        await on_step(state)

                exec_result = await task_executor.run(
                    goal=goal,
                    working_dir=run_workspace,
                    iteration=i,
                    refinement=refinement,
                    plan=plan,
                    on_log=on_log,
                    on_phase_complete=on_phase_complete,
                )
                # Replace the in-progress entry with the final result
                if state.executor_results and state.executor_results[-1].iteration == i:
                    state.executor_results[-1] = exec_result
                else:
                    state.executor_results.append(exec_result)
                _save_state(state)
                if on_step:
                    await on_step(state)

                # --- Step 2: Review ---
                review = await self_reviewer.run(
                    goal=goal,
                    executor_result=exec_result,
                    working_dir=run_workspace,
                    plan=plan,
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
        # Never tear down a direct workspace — those are real files on disk.
        if state.status != RunStatus.PASSED and not direct_workspace:
            await asyncio.to_thread(workspace.teardown, state.run_id, working_dir, run_workspace)
            state.workspace = None

        # --- Step 4: Browser validate (optional) ---
        if app_url and state.status == RunStatus.PASSED:
            browser_result = await browser_validator.run(state, app_url, RUNS_DIR)
            state.browser_result = browser_result
            state.video_path = browser_result.video_path if browser_result else None
            _save_state(state)
        if on_step:
            await on_step(state)

        # --- Step 4.5: Clean up ---
        if state.status == RunStatus.PASSED:
            await workspace_cleaner.run(state)
            _save_state(state)
            if on_step:
                await on_step(state)

        # --- Step 5: Create PR ---
        if state.status == RunStatus.PASSED and create_pr:
            pr_url = await pr_creator.run(state, working_dir)
            state.pr_url = pr_url
            _save_state(state)
        if on_step:
            await on_step(state)

        # --- Step 6: Board update ---
        if not skip_board:
            board_url = await board_updater.run(state)
            state.board_url = board_url
            _save_state(state)
        if on_step:
            await on_step(state)

        _print_footer(state)
        return state
    finally:
        _run_accumulator.reset(_acc_token)
