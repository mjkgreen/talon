"""
task-executor skill
-------------------
1. Receives a goal (and optional refinement instructions from a previous iteration)
2. Asks Claude to decompose it into concrete subtasks with acceptance criteria
3. Spawns one sub-agent per subtask (concurrent asyncio tasks)
4. Each sub-agent runs its own tool-use loop (read/write/run/search)
5. Aggregates results into an ExecutorResult
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime

import anthropic
from rich.console import Console

from src.types import ExecutorResult, ReviewFeedback, RefinementResult, Subtask, SubtaskResult
from src.tools import TOOL_DEFINITIONS, dispatch_tool

console = Console()

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "8096"))

# Prompt caching: long system prompts are cached to reduce cost on repeated runs
_EXECUTOR_SYSTEM = """\
You are a senior software engineer acting as a task orchestrator.
Your job is to decompose a high-level goal into concrete, independently-executable subtasks.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- Each subtask must be self-contained and independently executable.
- Produce 3–7 subtasks. Prefer fewer, larger tasks over many tiny ones.
- acceptance_criteria must be specific and verifiable (e.g. "File src/auth.py exists and contains class UserAuth").

Schema:
{
  "subtasks": [
    {
      "description": "<imperative sentence describing the task>",
      "acceptance_criteria": ["<verifiable criterion 1>", ...]
    }
  ]
}
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


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


async def _decompose_goal(client: anthropic.Anthropic, goal: str, refinement: str | None) -> list[Subtask]:
    """Ask Claude to break the goal into subtasks. Returns parsed Subtask list."""
    user_content = f"Goal: {goal}"
    if refinement:
        user_content += f"\n\nRefinement instructions from previous review:\n{refinement}"

    response = await asyncio.to_thread(
        client.messages.create,
        model=MODEL,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": _EXECUTOR_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if the model ignores the instruction
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    return [Subtask(**s) for s in data["subtasks"]]


async def _run_subagent(
    client: anthropic.Anthropic,
    subtask: Subtask,
    goal: str,
    working_dir: str,
    iteration: int,
) -> SubtaskResult:
    """Run a single sub-agent with tool-use loop to complete one subtask."""
    console.print(f"  [cyan]→ Sub-agent[/cyan] [{subtask.id}] {subtask.description[:70]}")

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

    # Agentic loop: keep going until stop_reason is "end_turn"
    for _turn in range(20):  # safety cap
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": _SUBAGENT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # Collect assistant message
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Extract final text output
            for block in response.content:
                if hasattr(block, "text"):
                    final_output = block.text
            break

        if response.stop_reason != "tool_use":
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            result_str = await asyncio.to_thread(dispatch_tool, block.name, block.input, working_dir)

            # Track side effects for reporting
            if block.name == "write_file":
                files_modified.append(block.input.get("path", ""))
            elif block.name == "run_command":
                commands_run.append(block.input.get("command", ""))

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return SubtaskResult(
        subtask=subtask,
        output=final_output or "(no output)",
        files_modified=files_modified,
        commands_run=commands_run,
        success=bool(final_output),
    )


async def run(
    goal: str,
    working_dir: str,
    iteration: int = 1,
    refinement: RefinementResult | None = None,
) -> ExecutorResult:
    """Entry point for the task-executor skill."""
    client = _client()
    refinement_text = refinement.refined_instructions if refinement else None

    console.print(f"\n[bold blue]task-executor[/bold blue] iteration={iteration}")
    console.print(f"  Goal: {goal[:100]}")

    subtasks = await _decompose_goal(client, goal, refinement_text)
    console.print(f"  Decomposed into {len(subtasks)} subtask(s)")

    # Run all sub-agents concurrently
    results = await asyncio.gather(
        *[_run_subagent(client, st, goal, working_dir, iteration) for st in subtasks],
        return_exceptions=False,
    )

    # Aggregate
    aggregated = "\n\n".join(
        f"[{r.subtask.id}] {r.subtask.description}\n{r.output}" for r in results
    )
    all_files = sorted({f for r in results for f in r.files_modified})
    console.print(f"  Files modified: {all_files or '(none)'}")

    return ExecutorResult(
        goal=goal,
        subtasks=subtasks,
        subtask_results=list(results),
        aggregated_output=aggregated,
        iteration=iteration,
    )
