"""
task-executor skill
-------------------
1. Decomposes a goal into 3–7 subtasks (single call, no tools)
2. Spawns one sub-agent per subtask concurrently
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
from talon.types import ExecutorResult, PlanResult, RefinementResult, Subtask, SubtaskResult

console = Console()

MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))
MAX_SUBAGENTS = int(os.getenv("MAX_SUBAGENTS", "7"))


def _executor_system(max_subagents: int) -> str:
    return f"""\
You are a senior software engineer acting as a task orchestrator.
Your job is to decompose a high-level goal into concrete, independently-executable subtasks.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- Each subtask must be self-contained and independently executable.
- Choose the number of subtasks that best fits the goal's complexity: 1–{max_subagents}.
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


def _plan_context(plan: PlanResult) -> str:
    lines = [f"Approach: {plan.approach}"]
    if plan.constraints:
        lines.append("Constraints:\n" + "\n".join(f"- {c}" for c in plan.constraints))
    if plan.phases:
        phase_text = "\n".join(
            f"  {i}. {p.name}: {p.description}" for i, p in enumerate(plan.phases)
        )
        lines.append(f"Planned phases (use as subtask guidance):\n{phase_text}")
    if plan.success_criteria:
        lines.append(
            "Success criteria:\n" + "\n".join(f"- {c}" for c in plan.success_criteria)
        )
    return "\n\n".join(lines)


async def _decompose_goal(
    goal: str,
    refinement: str | None,
    max_subagents: int,
    plan: PlanResult | None = None,
) -> list[Subtask]:
    provider = get_provider("orchestrator")
    user_content = f"Goal: {goal}"
    if plan:
        user_content += f"\n\nImplementation plan:\n{_plan_context(plan)}"
    if refinement:
        user_content += f"\n\nRefinement instructions from previous review:\n{refinement}"

    response = await provider.chat(
        system=_executor_system(max_subagents),
        messages=[{"role": "user", "content": user_content}],
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
        raise RuntimeError(
            f"Orchestrator returned invalid JSON: {e}\nRaw: {raw[:300]!r}"
        ) from e
    subtasks = [Subtask(**s) for s in data["subtasks"]]
    return subtasks[:max_subagents]


async def _run_subagent(
    subtask: Subtask,
    goal: str,
    working_dir: str,
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

    # If the tool-use loop ended without a text summary, request one explicitly.
    if not final_output:
        summary_response = await provider.chat(
            system=_SUBAGENT_SYSTEM,
            messages=messages + [
                {"role": "user", "content": "Summarize what you did and what the outcome was."}
            ],
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


async def run(
    goal: str,
    working_dir: str,
    iteration: int = 1,
    refinement: RefinementResult | None = None,
    plan: PlanResult | None = None,
    on_log: Callable[[str], Awaitable[None]] | None = None,
) -> ExecutorResult:
    refinement_text = refinement.refined_instructions if refinement else None

    console.print(f"\n[bold blue]task-executor[/bold blue] iteration={iteration}")
    console.print(f"  Goal: {goal[:100]}")

    subtasks = await _decompose_goal(goal, refinement_text, MAX_SUBAGENTS, plan=plan)
    console.print(f"  Decomposed into {len(subtasks)} subtask(s)")
    if on_log:
        await on_log(f"Decomposed into {len(subtasks)} subtask(s)")

    results = await asyncio.gather(*[
        _run_subagent(st, goal, working_dir, on_log) for st in subtasks
    ])

    aggregated = "\n\n".join(
        f"[{r.subtask.id}] {r.subtask.description}\n{r.output}" for r in results
    )
    all_files = sorted({f for r in results for f in r.files_modified})
    console.print(f"  Files modified: {all_files or '(none)'}")
    if on_log:
        await on_log(f"Files modified: {list(all_files) if all_files else '(none)'}")

    return ExecutorResult(
        goal=goal,
        subtasks=subtasks,
        subtask_results=list(results),
        aggregated_output=aggregated,
        iteration=iteration,
    )
