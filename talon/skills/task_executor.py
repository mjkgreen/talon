"""
task-executor skill
-------------------
1. Iterates through planner phases sequentially
2. Decomposes each phase into parallel subtasks (single LLM call per phase)
3. Each sub-agent runs its own tool-use loop (read/write/run/search)
4. Aggregates into ExecutorResult
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Awaitable, Callable

from rich.console import Console

from talon.providers import get_provider
from talon.providers.base import ToolResult
from talon.tools import TOOL_DEFINITIONS, dispatch_tool
from talon.types import (
    ExecutorResult,
    PhaseResult,
    PhaseStatus,
    PlanPhase,
    PlanResult,
    RefinementResult,
    Subtask,
    SubtaskResult,
)

console = Console()

MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))
MAX_SUBAGENTS = int(os.getenv("MAX_SUBAGENTS", "7"))


def _executor_system(max_subagents: int) -> str:
    return f"""\
You are a senior software engineer acting as a task orchestrator.
Your job is to decompose a specific implementation phase into concrete,
independently-executable subtasks.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- Each subtask must be self-contained and independently executable within this phase.
- Choose the number of subtasks that best fits the phase's complexity: 1–{max_subagents}.
  Prefer fewer, larger tasks over many tiny ones.
- acceptance_criteria must be specific and verifiable (e.g. "src/auth.py contains class UserAuth").

Schema:
{{
  "subtasks": [
    {{
      "description": "<imperative sentence describing the task>",
      "acceptance_criteria": ["<verifiable criterion 1>", ...]
    }}
  ]
}}
"""


_SUBAGENT_SYSTEM = """\
You are a senior software engineer executing a specific coding task.
You have access to filesystem and shell tools. Use them to implement the task completely.

Rules:
- Always read existing files before modifying them.
- Write clean, production-quality code.
- Run tests or validation commands when available.
- When done, output a concise summary of what you did.
- If blocked, explain why and what you attempted.
"""


async def _decompose_phase(
    phase: PlanPhase,
    phase_index: int,
    goal: str,
    completed_phase_outputs: list[str],
    refinement: str | None,
    max_subagents: int,
) -> list[Subtask]:
    provider = get_provider("orchestrator")
    parts = [
        f"Overall goal: {goal}",
        f"Current phase ({phase_index + 1}): {phase.name}\n{phase.description}",
    ]
    if completed_phase_outputs:
        prior = "\n\n".join(
            f"Phase {i + 1} output:\n{out[:800]}" for i, out in enumerate(completed_phase_outputs)
        )
        parts.append(f"Completed phases (context only — do not redo this work):\n{prior}")
    if refinement:
        parts.append(f"Refinement from previous review:\n{refinement}")

    response = await provider.chat(
        system=_executor_system(max_subagents),
        messages=[{"role": "user", "content": "\n\n".join(parts)}],
        tools=[],
        max_tokens=2048,
    )

    raw = (response.text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Orchestrator returned invalid JSON: {e}\nRaw: {raw[:300]!r}") from e
    subtasks = [Subtask(**s) for s in data["subtasks"]]
    return subtasks[:max_subagents]


async def _run_subagent(
    subtask: Subtask,
    goal: str,
    working_dir: str,
    phase_name: str,
    phase_context: str,
    on_log: Callable[[str], Awaitable[None]] | None = None,
) -> SubtaskResult:
    console.print(f"  [cyan]-> Sub-agent[/cyan] [{subtask.id}] {subtask.description}")
    if on_log:
        await on_log(f"-> Sub-agent [{subtask.id}] {subtask.description}")
    provider = get_provider("subagent")

    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Overall goal: {goal}\n\n"
                f"Current phase: {phase_name}\n"
                f"{phase_context}\n\n"
                f"Your specific task: {subtask.description}\n\n"
                f"Acceptance criteria:\n"
                + "\n".join(f"- {c}" for c in subtask.acceptance_criteria)
                + f"\n\nWorking directory: {working_dir}\n"
                "Use the provided tools to complete the task, then summarize what you did."
            ),
        }
    ]

    files_modified: list[str] = []
    commands_run: list[str] = []
    final_output = ""

    for _turn in range(20):
        response = await provider.chat(
            system=_SUBAGENT_SYSTEM,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            max_tokens=MAX_TOKENS,
        )
        provider.append_assistant(messages, response)

        if response.stop_reason == "end_turn":
            final_output = response.text or ""
            break

        tool_results: list[ToolResult] = []
        for tc in response.tool_calls:
            result_str = await asyncio.to_thread(dispatch_tool, tc.name, tc.input, working_dir)
            if tc.name == "write_file":
                files_modified.append(tc.input.get("path", ""))
            elif tc.name == "run_command":
                commands_run.append(tc.input.get("command", ""))
            tool_results.append(ToolResult(id=tc.id, content=result_str))

        provider.append_tool_results(messages, tool_results)

    if not final_output:
        summary_response = await provider.chat(
            system=_SUBAGENT_SYSTEM,
            messages=messages
            + [{"role": "user", "content": "Summarize what you did and what the outcome was."}],
            tools=[],
            max_tokens=1024,
        )
        final_output = summary_response.text or ""

    did_work = bool(files_modified or commands_run)
    if on_log:
        if files_modified:
            await on_log(f"[{subtask.id}] modified: {', '.join(files_modified)}")
        else:
            await on_log(f"[{subtask.id}] done")
    return SubtaskResult(
        subtask=subtask,
        output=final_output or "(no output — no files written or commands run)",
        files_modified=files_modified,
        commands_run=commands_run,
        success=bool(final_output) or did_work,
    )


async def _execute_phase(
    phase: PlanPhase,
    phase_index: int,
    goal: str,
    completed_phases: list[PhaseResult],
    refinement: str | None,
    working_dir: str,
    max_subagents: int,
    on_log: Callable[[str], Awaitable[None]] | None,
    on_phase_complete: Callable[[PhaseResult], Awaitable[None]] | None,
) -> PhaseResult:
    completed_outputs = [p.aggregated_output for p in completed_phases]
    subtasks = await _decompose_phase(
        phase, phase_index, goal, completed_outputs, refinement, max_subagents
    )

    phase_context = (
        "\n\n".join(
            f"Phase {i + 1} ({completed_phases[i].phase_name}):\n"
            f"{completed_phases[i].aggregated_output[:600]}"
            for i in range(len(completed_phases))
        )
        or "(this is the first phase)"
    )

    if on_log:
        await on_log(f"=== Phase {phase_index + 1}: {phase.name} ===")
    console.print(f"  Decomposed into {len(subtasks)} subtask(s)")

    results = await asyncio.gather(
        *[
            _run_subagent(st, goal, working_dir, phase.name, phase_context, on_log)
            for st in subtasks
        ]
    )

    aggregated = "\n\n".join(
        f"[{r.subtask.id}] {r.subtask.description}\n{r.output}" for r in results
    )
    all_files = sorted({f for r in results for f in r.files_modified})
    if on_log and all_files:
        await on_log(f"Phase {phase_index + 1} files modified: {list(all_files)}")

    phase_result = PhaseResult(
        phase_index=phase_index,
        phase_name=phase.name,
        phase_description=phase.description,
        subtasks=subtasks,
        subtask_results=list(results),
        aggregated_output=aggregated,
        status=PhaseStatus.COMPLETED,
    )
    if on_phase_complete:
        await on_phase_complete(phase_result)
    return phase_result


async def run(
    goal: str,
    working_dir: str,
    iteration: int = 1,
    refinement: RefinementResult | None = None,
    plan: PlanResult | None = None,
    on_log: Callable[[str], Awaitable[None]] | None = None,
    on_phase_complete: Callable[[PhaseResult], Awaitable[None]] | None = None,
) -> ExecutorResult:
    refinement_text = refinement.refined_instructions if refinement else None

    console.print(f"\n[bold blue]task-executor[/bold blue] iteration={iteration}")
    console.print(f"  Goal: {goal[:100]}")

    phases_to_run: list[PlanPhase] = plan.phases if plan and plan.phases else []
    if not phases_to_run:
        phases_to_run = [PlanPhase(name="Execute goal", description=goal[:200], dependencies=[])]

    # Execute phases using a dependency-aware DAG scheduler.
    # Phases whose `dependencies` are all satisfied run concurrently.
    # Phases with no dependencies all start in the first round.
    n = len(phases_to_run)
    completed_map: dict[int, PhaseResult] = {}

    while len(completed_map) < n:
        ready = [
            i
            for i in range(n)
            if i not in completed_map
            and all(d in completed_map for d in phases_to_run[i].dependencies)
        ]
        if not ready:
            raise RuntimeError("Phase dependency cycle or unsatisfiable dependency detected")

        prior = [completed_map[i] for i in sorted(completed_map)]
        if len(ready) > 1:
            names = ", ".join(f"'{phases_to_run[i].name}'" for i in ready)
            console.print(f"  [blue]Phases (parallel):[/blue] {names}")
        else:
            idx = ready[0]
            console.print(f"  [blue]Phase {idx + 1}/{n}:[/blue] {phases_to_run[idx].name}")

        batch = await asyncio.gather(
            *[
                _execute_phase(
                    phase=phases_to_run[i],
                    phase_index=i,
                    goal=goal,
                    completed_phases=prior,
                    refinement=refinement_text,
                    working_dir=working_dir,
                    max_subagents=MAX_SUBAGENTS,
                    on_log=on_log,
                    on_phase_complete=on_phase_complete,
                )
                for i in ready
            ]
        )
        for i, result in zip(ready, batch):
            completed_map[i] = result

    completed = [completed_map[i] for i in range(n)]

    aggregated = "\n\n".join(
        f"## Phase {ph.phase_index + 1}: {ph.phase_name}\n{ph.aggregated_output}"
        for ph in completed
    )
    all_files = sorted(
        {f for ph in completed for sr in ph.subtask_results for f in sr.files_modified}
    )
    console.print(f"  Files modified: {all_files or '(none)'}")
    if on_log:
        await on_log(f"Files modified: {list(all_files) if all_files else '(none)'}")

    return ExecutorResult(
        goal=goal,
        phases=completed,
        aggregated_output=aggregated,
        iteration=iteration,
    )
