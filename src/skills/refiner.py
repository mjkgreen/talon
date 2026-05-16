"""
refiner skill
-------------
Translates reviewer feedback into a precise action plan for the next
executor iteration. Single API call — no tool use needed.
"""
from __future__ import annotations

import asyncio
import json
import os

from rich.console import Console

from src.providers import get_provider
from src.types import ExecutorResult, ReviewFeedback, RefinementResult

console = Console()

_REFINER_SYSTEM = """\
You are a technical lead translating code-review feedback into a precise action plan.
Given the original goal, the reviewer's verdict, and the previous implementation summary,
output a JSON object with the following schema (no prose, no markdown fences):

{
  "changes_planned": [
    "<specific, concrete change to make, e.g. 'Add input validation to POST /users endpoint'>"
  ],
  "refined_instructions": "<paragraph of instructions for the next execution pass, incorporating all blocking issues>"
}

Rules:
- Address every blocking issue from the reviewer.
- Preserve what already works — don't throw away good code.
- Be specific: name files, functions, and test cases.
- Keep refined_instructions under 400 words.
"""


def _build_prompt(goal: str, executor_result: ExecutorResult, feedback: ReviewFeedback) -> str:
    blocking = "\n".join(f"- {i}" for i in feedback.blocking_issues) or "(none)"
    suggestions = "\n".join(f"- {s}" for s in feedback.suggestions) or "(none)"
    criteria_failed = "\n".join(
        f"- {c.criterion}: {c.evidence}" for c in feedback.criteria if not c.met
    ) or "(all criteria met)"

    return (
        f"Original goal: {goal}\n\n"
        f"Previous implementation summary (truncated):\n{executor_result.aggregated_output[:2000]}\n\n"
        f"Reviewer verdict: {feedback.verdict} (score={feedback.score:.2f})\n"
        f"Reviewer summary: {feedback.summary}\n\n"
        f"Blocking issues (MUST fix):\n{blocking}\n\n"
        f"Failed criteria:\n{criteria_failed}\n\n"
        f"Non-blocking suggestions (address if possible):\n{suggestions}\n\n"
        "---\nProduce the refined action plan JSON."
    )


async def run(goal: str, executor_result: ExecutorResult, feedback: ReviewFeedback) -> RefinementResult:
    provider = get_provider("refiner")
    iteration = feedback.iteration

    console.print(f"\n[bold magenta]refiner[/bold magenta] iteration={iteration}")

    response = await provider.chat(
        system=_REFINER_SYSTEM,
        messages=[{"role": "user", "content": _build_prompt(goal, executor_result, feedback)}],
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
    except json.JSONDecodeError:
        data = {
            "changes_planned": ["Re-attempt all blocking issues from reviewer feedback."],
            "refined_instructions": (
                "Re-implement the goal addressing these issues: "
                + "; ".join(feedback.blocking_issues)
            ),
        }

    result = RefinementResult(
        feedback=feedback,
        changes_planned=data.get("changes_planned", []),
        refined_instructions=data.get("refined_instructions", ""),
        iteration=iteration,
    )

    console.print(f"  Planned {len(result.changes_planned)} change(s):")
    for change in result.changes_planned:
        console.print(f"  [magenta]  • {change}[/magenta]")

    return result
