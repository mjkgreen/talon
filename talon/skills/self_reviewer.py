"""
self-reviewer skill
-------------------
Evaluates an ExecutorResult against the original goal.
Uses a tool-use loop to read files and run verification commands before
rendering a structured JSON verdict.
"""

from __future__ import annotations

import asyncio
import json
import os
import re

from rich.console import Console

from talon.providers import get_provider
from talon.providers.base import ToolResult
from talon.tools import TOOL_DEFINITIONS, dispatch_tool
from talon.types import ExecutorResult, ReviewCriterion, ReviewFeedback, ReviewVerdict

console = Console()

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

# Reviewer gets read-only tools only
_REVIEWER_TOOLS = [
    t
    for t in TOOL_DEFINITIONS
    if t["name"] in {"read_file", "list_files", "run_command", "search_files"}
]


def _build_review_prompt(goal: str, executor_result: ExecutorResult, working_dir: str) -> str:
    files_summary = (
        "\n".join(f"  - {f}" for r in executor_result.subtask_results for f in r.files_modified)
        or "  (none reported)"
    )
    commands_summary = (
        "\n".join(f"  - {c}" for r in executor_result.subtask_results for c in r.commands_run)
        or "  (none)"
    )
    subtask_outputs = "\n\n".join(
        f"Subtask [{r.subtask.id}]: {r.subtask.description}\n"
        f"Acceptance criteria: {r.subtask.acceptance_criteria}\n"
        f"Output: {r.output[:1000]}"
        for r in executor_result.subtask_results
    )
    return (
        f"Original goal: {goal}\n\n"
        f"Working directory: {working_dir}\n\n"
        f"Files reportedly modified:\n{files_summary}\n\n"
        f"Commands reportedly run:\n{commands_summary}\n\n"
        f"Agent's subtask outputs:\n{subtask_outputs}\n\n"
        "---\nUsing the tools available, verify the implementation against the goal.\n"
        "Then output your verdict JSON."
    )


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from reviewer output, handling prose and code fences."""
    # 1. Try the raw text first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 2. Extract from ```json ... ``` or ``` ... ``` blocks anywhere in text
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find the first { ... } spanning the whole JSON object
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    return None


async def run(goal: str, executor_result: ExecutorResult, working_dir: str) -> ReviewFeedback:
    provider = get_provider("reviewer")
    iteration = executor_result.iteration

    console.print(f"\n[bold yellow]self-reviewer[/bold yellow] iteration={iteration}")

    messages: list[dict] = [
        {"role": "user", "content": _build_review_prompt(goal, executor_result, working_dir)}
    ]
    raw_verdict = ""

    for _turn in range(10):
        response = await provider.chat(
            system=_REVIEWER_SYSTEM,
            messages=messages,
            tools=_REVIEWER_TOOLS,
            max_tokens=MAX_TOKENS,
        )
        provider.append_assistant(messages, response)

        if response.stop_reason == "end_turn":
            raw_verdict = response.text or ""
            break

        tool_results: list[ToolResult] = []
        for tc in response.tool_calls:
            result_str = await asyncio.to_thread(dispatch_tool, tc.name, tc.input, working_dir)
            tool_results.append(ToolResult(id=tc.id, content=result_str))
        provider.append_tool_results(messages, tool_results)

    data = _extract_json(raw_verdict)
    if data is None:
        console.print("  [red]Warning: could not parse reviewer JSON, defaulting to fail[/red]")
        console.print(f"  [dim]Raw reviewer output (first 500 chars): {raw_verdict[:500]!r}[/dim]")
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
    console.print(
        f"  [{color}]{icon} verdict={feedback.verdict} score={feedback.score:.2f}[/{color}]"
    )
    for issue in feedback.blocking_issues:
        console.print(f"  [red]  - {issue}[/red]")

    return feedback
