"""
plan_refiner skill
------------------
Revises an existing plan based on user feedback comments.
"""

from __future__ import annotations

import json

from rich.console import Console

from talon.providers import get_provider
from talon.types import PlanPhase, PlanResult

console = Console()

_REFINER_SYSTEM = """\
You are a senior software architect. You have been given an existing implementation plan
and user feedback comments. Revise the plan to incorporate all the feedback.

Output ONLY valid JSON matching the schema below. No prose, no markdown fences.

Schema:
{
  "approach": "<1-3 sentence high-level strategy>",
  "constraints": ["<constraint or assumption>", ...],
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
- Incorporate ALL user feedback comments into the revised plan.
- Keep what works in the existing plan; only change what the feedback targets.
- phases: 2-5 ordered phases. dependencies is a list of 0-based phase indices.
- success_criteria must be concrete and testable (e.g. "pytest exits 0", "GET /health returns 200").
"""


async def run(goal: str, current_plan: PlanResult, comments: list[str]) -> PlanResult:
    console.print("\n[bold blue]plan-refiner[/bold blue]")
    console.print(f"  Incorporating {len(comments)} comment(s)")

    provider = get_provider("orchestrator")
    comments_text = "\n".join(f"- {c}" for c in comments)
    user_content = (
        f"Goal: {goal}\n\n"
        f"Current plan:\n{current_plan.model_dump_json(indent=2)}\n\n"
        f"User feedback:\n{comments_text}\n\n"
        "Please revise the plan to address the feedback."
    )

    response = await provider.chat(
        system=_REFINER_SYSTEM,
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
            f"Plan refiner returned invalid JSON: {e}\nRaw: {raw[:300]!r}"
        ) from e

    plan = PlanResult(
        approach=data.get("approach", ""),
        constraints=data.get("constraints", []),
        phases=[PlanPhase(**p) for p in data.get("phases", [])],
        success_criteria=data.get("success_criteria", []),
    )

    console.print(f"  Revised approach: {plan.approach[:120]}")
    return plan
