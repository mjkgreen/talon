"""
planner skill
-------------
Runs once before the executor loop.
Explores the workspace via tool calls (read_file, list_files, search_files),
then produces a structured plan (approach, constraints, phases, success criteria)
that guides the executor's task decomposition.
"""

from __future__ import annotations

import asyncio
import json
import os

from rich.console import Console

from talon.providers import get_provider
from talon.providers.base import ToolResult
from talon.tools import TOOL_DEFINITIONS, dispatch_tool
from talon.types import PlanPhase, PlanResult

console = Console()

# Planner only gets read-only tools — no writes, no shell commands.
_READ_ONLY_TOOLS = [
    t for t in TOOL_DEFINITIONS if t["name"] in {"read_file", "list_files", "search_files"}
]

_PLANNER_SYSTEM = """\
You are a senior software architect. Your job is to explore the workspace and then
produce a phased execution plan for the given goal.

## Workflow
1. EXPLORE: Use list_files, read_file, and search_files to understand what already
   exists — directory layout, tech stack, existing modules, conventions, test setup.
   Read as many files as you need. There is no rush.
2. PLAN: Once you have enough context, output the plan as valid JSON (schema below).
   When you output JSON, stop calling tools — that ends the planning step.

## Planning rules
- Build on what already exists. Do not recreate modules, patterns, or conventions
  the workspace already has.
- phases: 2–5 sequential phases. Each executes fully before the next begins.
  Within a phase, parallel sub-agents do the work, so avoid intra-phase dependencies.
  Name each phase with an imperative verb phrase ("Add authentication middleware").
  Description must name the exact files/modules created or edited and state what
  prior-phase output it depends on.
  dependencies: list of 0-based phase indices (documentation only).
  Typical split: schema/config → models/services → API routes → tests → integration.
- success_criteria: concrete and testable ("pytest exits 0", "GET /health returns 200").
- approach: ≤3 sentences high-level strategy.

## Output format
Output ONLY valid JSON. No prose, no markdown fences.

{
  "approach": "<1-3 sentence strategy>",
  "constraints": ["<constraint or assumption>", ...],
  "phases": [
    {
      "name": "<imperative verb phrase>",
      "description": "<files/modules touched and dependency on prior phases>",
      "dependencies": []
    }
  ],
  "success_criteria": ["<verifiable criterion>", ...]
}
"""

_MAX_EXPLORE_TURNS = int(os.getenv("PLANNER_MAX_TURNS", "500"))


async def run(goal: str, working_dir: str | None = None) -> PlanResult:
    console.print("\n[bold blue]planner[/bold blue]")
    console.print(f"  Goal: {goal[:100]}")

    workspace_note = (
        f"Working directory: {working_dir}\nStart by listing files to orient yourself."
        if working_dir
        else "No working directory — plan from scratch based on the goal alone."
    )
    user_message = f"Goal: {goal}\n\n{workspace_note}"

    provider = get_provider("orchestrator")
    messages: list[dict] = [{"role": "user", "content": user_message}]
    tools = _READ_ONLY_TOOLS if working_dir else []

    raw_plan: str = ""
    turns = 0

    for _ in range(_MAX_EXPLORE_TURNS):
        turns += 1
        response = await provider.chat(
            system=_PLANNER_SYSTEM,
            messages=messages,
            tools=tools,
            max_tokens=4096,
        )
        provider.append_assistant(messages, response)

        if response.stop_reason == "end_turn":
            raw_plan = (response.text or "").strip()
            break

        tool_results: list[ToolResult] = []
        for tc in response.tool_calls:
            console.print(f"  [dim]planner tool:[/dim] {tc.name}({list(tc.input.values())[:2]})")
            result_str = await asyncio.to_thread(
                dispatch_tool, tc.name, tc.input, working_dir or "."
            )
            tool_results.append(ToolResult(id=tc.id, content=result_str))

        provider.append_tool_results(messages, tool_results)

    if not raw_plan:
        raise RuntimeError(f"Planner did not produce a plan after {turns} turns")

    if raw_plan.startswith("```"):
        raw_plan = raw_plan.split("```")[1]
        if raw_plan.startswith("json"):
            raw_plan = raw_plan[4:]

    try:
        data = json.loads(raw_plan)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Planner returned invalid JSON: {e}\nRaw: {raw_plan[:300]!r}") from e

    plan = PlanResult(
        approach=data.get("approach", ""),
        constraints=data.get("constraints", []),
        phases=[PlanPhase(**p) for p in data.get("phases", [])],
        success_criteria=data.get("success_criteria", []),
    )

    console.print(f"  Approach: {plan.approach[:120]}")
    console.print(
        f"  Phases: {len(plan.phases)}  Criteria: {len(plan.success_criteria)}"
        f"  Explore turns: {turns}"
    )
    return plan
