"""
refiner skill
-------------
Takes reviewer feedback + the previous executor result and produces
refined instructions for the next executor iteration.

It does NOT re-implement code itself — it synthesises the reviewer's
blocking issues and suggestions into a clear action plan that the
task-executor will use on the next pass.
"""
from __future__ import annotations

import asyncio
import json
import os

import anthropic
from rich.console import Console

from src.types import ExecutorResult, ReviewFeedback, RefinementResult

console = Console()

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))

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


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _build_refiner_prompt(
    goal: str,
    executor_result: ExecutorResult,
    feedback: ReviewFeedback,
) -> str:
    blocking = "\n".join(f"- {i}" for i in feedback.blocking_issues) or "(none)"
    suggestions = "\n".join(f"- {s}" for s in feedback.suggestions) or "(none)"
    criteria_failed = "\n".join(
        f"- {c.criterion}: {c.evidence}"
        for c in feedback.criteria
        if not c.met
    ) or "(all criteria met)"

    prev_summary = executor_result.aggregated_output[:2000]

    return f"""\
Original goal: {goal}

Previous implementation summary (truncated):
{prev_summary}

Reviewer verdict: {feedback.verdict} (score={feedback.score:.2f})
Reviewer summary: {feedback.summary}

Blocking issues (MUST fix):
{blocking}

Failed criteria:
{criteria_failed}

Non-blocking suggestions (address if possible):
{suggestions}

---
Produce the refined action plan JSON.
"""


async def run(
    goal: str,
    executor_result: ExecutorResult,
    feedback: ReviewFeedback,
) -> RefinementResult:
    """Entry point for the refiner skill."""
    client = _client()
    iteration = feedback.iteration

    console.print(f"\n[bold magenta]refiner[/bold magenta] iteration={iteration}")

    prompt = _build_refiner_prompt(goal, executor_result, feedback)

    response = await asyncio.to_thread(
        client.messages.create,
        model=MODEL,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": _REFINER_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
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
                f"Re-implement the goal addressing these issues: "
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
