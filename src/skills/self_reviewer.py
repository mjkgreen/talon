"""
self-reviewer skill
-------------------
Evaluates an ExecutorResult against the original goal.
Returns a ReviewFeedback with verdict (pass/fail/needs_work), score 0–1,
per-criterion evaluation, blocking issues, and actionable suggestions.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import anthropic
from rich.console import Console

from src.types import ExecutorResult, ReviewCriterion, ReviewFeedback, ReviewVerdict
from src.tools import dispatch_tool, TOOL_DEFINITIONS

console = Console()

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))

_REVIEWER_SYSTEM = """\
You are a rigorous code reviewer acting as quality gate for an autonomous coding agent.
Your job is to evaluate whether the agent's output satisfies the original goal.

You have read-only access to the filesystem via tools. Use them to inspect files and run
verification commands (tests, linters, type checkers) before rendering a verdict.

Output ONLY valid JSON matching this schema (no prose, no markdown fences):

{
  "verdict": "pass" | "fail" | "needs_work",
  "score": <float 0.0–1.0>,
  "summary": "<one sentence conclusion>",
  "criteria": [
    {
      "criterion": "<what was checked>",
      "met": <true|false>,
      "evidence": "<concrete evidence from the code or command output>"
    }
  ],
  "blocking_issues": ["<issue that MUST be fixed before passing>"],
  "suggestions": ["<non-blocking improvement>"]
}

Verdict rules:
- "pass"       → score >= 0.85 AND no blocking_issues
- "needs_work" → score >= 0.5 AND at most 2 blocking_issues (refiner can fix these)
- "fail"       → score < 0.5 OR more than 2 blocking_issues

Be strict but fair. Verify claims by reading files, don't take the agent's word for it.
"""

# Read-only subset of tools for the reviewer
_REVIEWER_TOOLS = [t for t in TOOL_DEFINITIONS if t["name"] in {"read_file", "list_files", "run_command", "search_files"}]


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _build_review_prompt(goal: str, executor_result: ExecutorResult, working_dir: str) -> str:
    files_summary = "\n".join(
        f"  - {f}" for r in executor_result.subtask_results for f in r.files_modified
    ) or "  (none reported)"

    commands_summary = "\n".join(
        f"  - {c}" for r in executor_result.subtask_results for c in r.commands_run
    ) or "  (none)"

    subtask_outputs = "\n\n".join(
        f"Subtask [{r.subtask.id}]: {r.subtask.description}\n"
        f"Acceptance criteria: {r.subtask.acceptance_criteria}\n"
        f"Output: {r.output[:1000]}"
        for r in executor_result.subtask_results
    )

    return f"""\
Original goal: {goal}

Working directory: {working_dir}

Files reportedly modified:
{files_summary}

Commands reportedly run:
{commands_summary}

Agent's subtask outputs:
{subtask_outputs}

---
Using the tools available, verify the implementation against the goal.
Then output your verdict JSON.
"""


async def run(goal: str, executor_result: ExecutorResult, working_dir: str) -> ReviewFeedback:
    """Entry point for the self-reviewer skill."""
    client = _client()
    iteration = executor_result.iteration

    console.print(f"\n[bold yellow]self-reviewer[/bold yellow] iteration={iteration}")

    prompt = _build_review_prompt(goal, executor_result, working_dir)
    messages: list[dict] = [{"role": "user", "content": prompt}]

    raw_verdict = ""

    for _turn in range(10):
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": _REVIEWER_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=_REVIEWER_TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    raw_verdict = block.text
            break

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result_str = await asyncio.to_thread(dispatch_tool, block.name, block.input, working_dir)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    # Parse verdict
    raw = raw_verdict.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat unparseable output as a fail
        console.print(f"  [red]Warning: could not parse reviewer JSON, defaulting to fail[/red]")
        data = {
            "verdict": "fail",
            "score": 0.0,
            "summary": "Reviewer output was not valid JSON.",
            "criteria": [],
            "blocking_issues": ["Reviewer could not parse agent output."],
            "suggestions": [],
        }

    feedback = ReviewFeedback(
        verdict=ReviewVerdict(data["verdict"]),
        score=float(data.get("score", 0.0)),
        summary=data.get("summary", ""),
        criteria=[ReviewCriterion(**c) for c in data.get("criteria", [])],
        blocking_issues=data.get("blocking_issues", []),
        suggestions=data.get("suggestions", []),
        iteration=iteration,
    )

    icon = "✓" if feedback.verdict == ReviewVerdict.PASS else "✗"
    color = "green" if feedback.verdict == ReviewVerdict.PASS else "red"
    console.print(f"  [{color}]{icon} verdict={feedback.verdict} score={feedback.score:.2f}[/{color}]")
    if feedback.blocking_issues:
        for issue in feedback.blocking_issues:
            console.print(f"  [red]  • {issue}[/red]")

    return feedback
