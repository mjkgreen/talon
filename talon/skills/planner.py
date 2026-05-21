"""
planner skill
-------------
Runs once before the executor loop.
Produces a structured plan (approach, constraints, phases, success criteria)
that guides the executor's task decomposition.
"""

from __future__ import annotations

import json

from rich.console import Console

from talon.providers import get_provider
from talon.types import PlanPhase, PlanResult

console = Console()

_PLANNER_SYSTEM = """\
You are a senior software architect. Analyze the goal and produce a structured
implementation plan that will guide parallel coding sub-agents.

Output ONLY valid JSON matching the schema below. No prose, no markdown fences.

Schema:
{
  "approach": "<1-3 sentence high-level strategy>",
  "constraints": ["<constraint or assumption to keep in mind>", ...],
  "phases": [
    {
      "name": "<phase name>",
      "description": "<what this phase accomplishes and which files/areas it touches>",
      "dependencies": []
    }
  ],
  "success_criteria": ["<specific, verifiable criterion>", ...]
}

Rules:
- phases: 2-5 ordered phases. dependencies is a list of 0-based phase indices this phase
  must wait for (empty means it can start immediately / run in parallel).
- success_criteria must be concrete and testable (e.g. "pytest exits 0", "GET /health returns 200").
- Keep approach under 3 sentences.
"""


async def run(goal: str) -> PlanResult:
    console.print("\n[bold blue]planner[/bold blue]")
    console.print(f"  Goal: {goal[:100]}")

    provider = get_provider("orchestrator")
    response = await provider.chat(
        system=_PLANNER_SYSTEM,
        messages=[{"role": "user", "content": f"Goal: {goal}"}],
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
            f"Planner returned invalid JSON: {e}\nRaw: {raw[:300]!r}"
        ) from e

    plan = PlanResult(
        approach=data.get("approach", ""),
        constraints=data.get("constraints", []),
        phases=[PlanPhase(**p) for p in data.get("phases", [])],
        success_criteria=data.get("success_criteria", []),
    )

    console.print(f"  Approach: {plan.approach[:120]}")
    console.print(f"  Phases: {len(plan.phases)}  Criteria: {len(plan.success_criteria)}")
    return plan
