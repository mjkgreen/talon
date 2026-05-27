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
from talon.tools import TOOL_DEFINITIONS, dispatch_tool, list_files
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
- validation_steps: ordered list of concrete browser navigation instructions a QA agent
  should follow to verify the goal. Write these while you still have the workspace open —
  you can see the routes, auth flows, and UI structure. Each step is a single imperative
  sentence the browser agent can execute literally. Include:
    1. A login step if the app requires authentication (include the login URL and note
       "use test credentials").
    2. Navigation steps (exact URLs or named UI elements like tab labels/menu items).
    3. Interaction steps (clicks, toggles, form submissions) that reach the feature.
    4. Verification steps matching each success criterion ("Verify that…").
  Aim for 4–8 steps. Omit steps the browser agent can discover itself.

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
  "success_criteria": ["<verifiable criterion>", ...],
  "validation_steps": [
    "Navigate to <app_url>/login and log in with test credentials",
    "Click the '<tab name>' tab in the navigation bar",
    "Perform the action that exercises the feature",
    "Verify that <observable outcome matching a success criterion>"
  ]
}
"""

_MAX_EXPLORE_TURNS = int(os.getenv("PLANNER_MAX_TURNS", "500"))


def _extract_json_object(text: str) -> str:
    """Return the first top-level JSON object found in *text*, or '' if none."""
    start = text.find("{")
    if start == -1:
        return ""
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


def _workspace_snapshot(working_dir: str, max_files: int = 200) -> str:
    """Return a compact file-tree string for the workspace root."""
    try:
        data = list_files(".", working_dir)
        files = data.get("files", [])
        lines = files[:max_files]
        if len(files) > max_files:
            lines.append(f"... [{len(files) - max_files} more files]")
        return "\n".join(lines)
    except Exception:
        return "(could not list workspace files)"


async def run(goal: str, working_dir: str | None = None) -> PlanResult:
    console.print("\n[bold blue]planner[/bold blue]")
    console.print(f"  Goal: {goal[:100]}")
    console.print(f"  Working dir: {working_dir or '(none)'}")

    if working_dir:
        snapshot = await asyncio.to_thread(_workspace_snapshot, working_dir)
        workspace_note = (
            f"Working directory: {working_dir}\n\n"
            f"File tree (top-level):\n{snapshot}\n\n"
            "Use read_file / list_files / search_files to explore further if needed."
        )
    else:
        workspace_note = "No working directory — plan from scratch based on the goal alone."

    user_message = f"Goal: {goal}\n\n{workspace_note}"

    provider = get_provider("planner")
    messages: list[dict] = [{"role": "user", "content": user_message}]
    tools = _READ_ONLY_TOOLS if working_dir else []

    # Deny-list: these tools are never safe for the planner regardless of what
    # the model requests (some providers hallucinate tool calls not in the schema).
    _BLOCKED_TOOLS = frozenset({"write_file", "run_command"})

    raw_plan: str = ""
    turns = 0

    for _ in range(_MAX_EXPLORE_TURNS):
        turns += 1
        response = await provider.chat(
            system=_PLANNER_SYSTEM,
            messages=messages,
            tools=tools,
            max_tokens=8192,
        )
        provider.append_assistant(messages, response)

        if response.stop_reason == "end_turn":
            candidate = (response.text or "").strip()
            # Model may prefix with reasoning text — extract the JSON object.
            extracted = _extract_json_object(candidate)
            if extracted:
                raw_plan = extracted
                break
            # No JSON yet; nudge the model to emit only the JSON.
            console.print("  [yellow]planner: no JSON in response, requesting JSON output[/yellow]")
            _nudge = (
                "Please output only the JSON plan now — "
                "no prose, no markdown fences, just the raw JSON object."
            )
            messages.append({"role": "user", "content": _nudge})

        async def _call(tc) -> ToolResult:
            if tc.name in _BLOCKED_TOOLS:
                console.print(f"  [red]planner: blocked disallowed tool call: {tc.name}[/red]")
                return ToolResult(
                    id=tc.id,
                    content=json.dumps(
                        {
                            "error": (
                                f"Tool '{tc.name}' is not available to the planner."
                                " Use only: read_file, list_files, search_files."
                            )
                        }
                    ),
                )
            console.print(f"  [dim]planner tool:[/dim] {tc.name}({list(tc.input.values())[:2]})")
            result_str = await asyncio.to_thread(
                dispatch_tool, tc.name, tc.input, working_dir or "."
            )
            return ToolResult(id=tc.id, content=result_str)

        tool_results = await asyncio.gather(*[_call(tc) for tc in response.tool_calls])

        provider.append_tool_results(messages, list(tool_results))

    if not raw_plan:
        raise RuntimeError(f"Planner did not produce a plan after {turns} turns")

    try:
        data = json.loads(raw_plan)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Planner returned invalid JSON: {e}\nRaw: {raw_plan[:300]!r}") from e

    plan = PlanResult(
        approach=data.get("approach", ""),
        constraints=data.get("constraints", []),
        phases=[PlanPhase(**p) for p in data.get("phases", [])],
        success_criteria=data.get("success_criteria", []),
        validation_steps=data.get("validation_steps", []),
    )

    console.print(f"  Approach: {plan.approach[:120]}")
    console.print(
        f"  Phases: {len(plan.phases)}  Criteria: {len(plan.success_criteria)}"
        f"  Steps: {len(plan.validation_steps)}  Explore turns: {turns}"
    )
    return plan
