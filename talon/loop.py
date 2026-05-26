"""
Core orchestration loop
-----------------------
planner → executor → reviewer → [pass] → browser-validator → board-updater → done
                              → [fail/needs_work] → refiner → executor (next iteration)
"""

from __future__ import annotations

import asyncio
import os
import subprocess
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
from talon.types import (
    ExecutorResult,
    PhaseResult,
    PlanResult,
    RefinementResult,
    ReviewVerdict,
    RunState,
    RunStatus,
)

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


def _load_state(run_id: str) -> RunState:
    state_file = Path(RUNS_DIR) / run_id / "state.json"
    if not state_file.exists():
        raise FileNotFoundError(f"No run found: {run_id}")
    return RunState.model_validate_json(state_file.read_text(encoding="utf-8"))


def _pause_sentinel(run_id: str) -> Path:
    return Path(RUNS_DIR) / run_id / "pause.signal"


def _is_pause_requested(run_id: str) -> bool:
    return _pause_sentinel(run_id).exists()


def _clear_pause_sentinel(run_id: str) -> None:
    _pause_sentinel(run_id).unlink(missing_ok=True)


def _derive_resume_point(
    state: RunState,
) -> tuple[bool, int, RefinementResult | None]:
    """Returns (needs_planning, start_iteration, last_refinement)."""
    needs_planning = state.plan_result is None
    last_complete = max(state.completed_iterations, default=0)
    last_refinement = state.refinement_results[-1] if state.refinement_results else None
    return needs_planning, last_complete + 1, last_refinement


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


_UI_EXTENSIONS = frozenset(
    {
        ".tsx",
        ".jsx",
        ".ts",
        ".js",
        ".html",
        ".css",
        ".scss",
        ".less",
        ".vue",
        ".svelte",
        ".astro",
    }
)
_UI_PATH_FRAGMENTS = frozenset(
    {
        "ui/",
        "frontend/",
        "src/components/",
        "src/pages/",
        "src/views/",
        "src/layouts/",
        "public/",
        "static/",
        "templates/",
    }
)


def _is_ui_file(fp: str) -> bool:
    normalized = fp.replace("\\", "/").lower()
    return Path(fp).suffix.lower() in _UI_EXTENSIONS or any(
        frag in normalized for frag in _UI_PATH_FRAGMENTS
    )


def _detect_ui_changes(exec_results: list[ExecutorResult], workspace_dir: str) -> bool:
    """Return True if any subtask modified a UI/frontend file."""
    for exec_result in exec_results:
        for sr in exec_result.subtask_results:
            if any(_is_ui_file(fp) for fp in sr.files_modified):
                return True

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if any(_is_ui_file(fp) for fp in result.stdout.strip().splitlines() if fp):
            return True
    except Exception:
        pass

    return False


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
    start_command: str | None = None,
    project_env_vars: dict[str, str] | None = None,
    env_content: str | None = None,
    cookie_file: str | None = None,
    test_user: str | None = None,
    test_password: str | None = None,
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
    state = RunState(
        goal=goal,
        origin_dir=working_dir,
        origin_repo_url=repo_url,
        origin_repo_branch=repo_branch,
        direct_workspace=direct_workspace,
    )

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
            if on_log:
                await on_log(f"[FAILED] Run crashed: {e}")
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
                if _is_pause_requested(state.run_id):
                    _clear_pause_sentinel(state.run_id)
                    state.status = RunStatus.PAUSED
                    _save_state(state)
                    if on_step:
                        await on_step(state)
                    console.print(f"\n[yellow]Run {state.run_id} paused.[/yellow]")
                    return state

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
                    run_id=state.run_id,
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
                state.completed_iterations.append(i)
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
            if on_log:
                await on_log(f"[FAILED] Run crashed: {e}")
            raise

        state.finished_at = datetime.utcnow()

        # Keep workspace on pass (code is ready for review / PR creation).
        # Remove on fail to avoid accumulating broken directories.
        # Never tear down a direct workspace — those are real files on disk.
        if state.status != RunStatus.PASSED and not direct_workspace:
            await asyncio.to_thread(workspace.teardown, state.run_id, working_dir, run_workspace)
            state.workspace = None

        # --- Detect UI changes ---
        if run_workspace:
            state.ui_changes_detected = _detect_ui_changes(state.executor_results, run_workspace)
            _save_state(state)
            if on_step:
                await on_step(state)

        # --- Step 4: Browser validate (optional) ---
        effective_url = app_url or (
            os.getenv("DEFAULT_APP_URL") if state.ui_changes_detected else None
        )
        _server_proc: asyncio.subprocess.Process | None = None
        _server_port: int | None = None
        try:
            if not effective_url and state.ui_changes_detected and run_workspace:
                try:
                    from talon.skills import workspace_starter

                    (
                        _server_proc,
                        effective_url,
                        _server_port,
                    ) = await workspace_starter.start_workspace_server(
                        run_workspace,
                        extra_env=project_env_vars,
                        start_command=start_command,
                        env_content=env_content,
                    )
                except Exception as _ws_err:
                    console.print(f"[yellow]workspace-starter: {_ws_err}[/yellow]")

            if effective_url and state.status == RunStatus.PASSED:

                async def _on_browser_progress(partial):
                    state.browser_result = partial
                    _save_state(state)
                    if on_step:
                        await on_step(state)

                browser_result = await browser_validator.run(
                    state,
                    effective_url,
                    RUNS_DIR,
                    on_progress=_on_browser_progress,
                    cookie_file=cookie_file,
                    test_user=test_user,
                    test_password=test_password,
                )
                if browser_result is not None:
                    state.browser_result = browser_result
                    state.video_path = browser_result.video_path
                _save_state(state)
        finally:
            if _server_proc is not None and _server_port is not None:
                from talon.skills import workspace_starter as _ws_mod

                await _ws_mod.stop_workspace_server(_server_proc, _server_port)
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


async def resume(
    run_id: str,
    on_step: Callable[[RunState], Awaitable[None]] | None = None,
    on_log: Callable[[str], Awaitable[None]] | None = None,
) -> RunState:
    """Resume a PAUSED or FAILED run from its last checkpoint.

    Skips planning if a plan already exists and skips iterations that
    have already completed (execute + review both finished).

    Raises:
        FileNotFoundError: run_id does not exist.
        RuntimeError: run is already PASSED, or still shows RUNNING
                      (which may mean another process is active).
    """
    state = _load_state(run_id)

    if state.status == RunStatus.PASSED:
        raise RuntimeError(f"Run {run_id} already passed — nothing to resume.")

    _clear_pause_sentinel(run_id)
    state.status = RunStatus.RUNNING
    state.error = None
    _save_state(state)
    if on_step:
        await on_step(state)

    needs_planning, start_iteration, last_refinement = _derive_resume_point(state)

    # Recover workspace if it no longer exists on disk.
    run_workspace = state.workspace
    if not run_workspace or not Path(run_workspace).exists():
        console.print(
            "[yellow]Workspace missing — recreating (prior code changes may be lost)[/yellow]"
        )
        if state.origin_dir is None and not state.origin_repo_url:
            console.print(
                "[yellow]Warning: origin_dir unknown (old run). Using a fresh workspace.[/yellow]"
            )
        run_workspace = await asyncio.to_thread(
            workspace.setup,
            state.run_id,
            state.origin_dir,
            repo_url=state.origin_repo_url,
            repo_branch=state.origin_repo_branch,
            direct=state.direct_workspace,
            goal=state.goal,
        )
        state.workspace = run_workspace
        _save_state(state)

    refinement: RefinementResult | None = last_refinement

    try:
        if needs_planning:
            plan = await planner.run(goal=state.goal, working_dir=run_workspace)
            state.plan_result = plan
            _save_state(state)
            if on_step:
                await on_step(state)
        else:
            plan = state.plan_result
            console.print("\n[bold blue]planner[/bold blue] (skipping — checkpoint plan exists)")

        _print_header(state.goal, state.run_id)

        for i in range(start_iteration, MAX_ITERATIONS + 1):
            if _is_pause_requested(run_id):
                _clear_pause_sentinel(run_id)
                state.status = RunStatus.PAUSED
                _save_state(state)
                if on_step:
                    await on_step(state)
                console.print(f"\n[yellow]Run {run_id} paused at iteration {i}.[/yellow]")
                return state

            state.iteration = i
            _save_state(state)
            if on_step:
                await on_step(state)
            console.print(Rule(f"Iteration {i}/{MAX_ITERATIONS} (resumed)", style="blue"))
            if on_log:
                await on_log(f"=== Iteration {i}/{MAX_ITERATIONS} (resumed) ===")

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
                    goal=state.goal,
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
                goal=state.goal,
                working_dir=run_workspace,
                iteration=i,
                refinement=refinement,
                plan=plan,
                on_log=on_log,
                on_phase_complete=on_phase_complete,
                run_id=run_id,
            )
            if state.executor_results and state.executor_results[-1].iteration == i:
                state.executor_results[-1] = exec_result
            else:
                state.executor_results.append(exec_result)
            _save_state(state)
            if on_step:
                await on_step(state)

            review = await self_reviewer.run(
                goal=state.goal,
                executor_result=exec_result,
                working_dir=run_workspace,
                plan=plan,
            )
            state.review_results.append(review)
            state.completed_iterations.append(i)
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

            refinement = await refiner.run(
                goal=state.goal,
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
        if on_log:
            await on_log(f"[FAILED] Run crashed: {e}")
        raise

    state.finished_at = datetime.utcnow()

    # --- Detect UI changes ---
    if run_workspace:
        state.ui_changes_detected = _detect_ui_changes(state.executor_results, run_workspace)
        _save_state(state)
        if on_step:
            await on_step(state)

    # --- Step 4: Browser validate (optional) ---
    effective_url = os.getenv("DEFAULT_APP_URL") if state.ui_changes_detected else None
    if effective_url and state.status == RunStatus.PASSED:

        async def _on_resume_browser_progress(partial):
            state.browser_result = partial
            _save_state(state)
            if on_step:
                await on_step(state)

        browser_result = await browser_validator.run(
            state, effective_url, RUNS_DIR, on_progress=_on_resume_browser_progress
        )
        if browser_result is not None:
            state.browser_result = browser_result
            state.video_path = browser_result.video_path
        _save_state(state)
    if on_step:
        await on_step(state)

    _print_footer(state)
    return state
