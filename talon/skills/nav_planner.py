"""
nav-planner skill
-----------------
Explores the workspace to discover actual routes and produce verified navigation
steps for the browser validator.

Unlike the self-reviewer (which generates steps as a side effect of code review)
this skill has a single job: read the framework's route definitions and build a
precise, file-confirmed navigation plan.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re

from rich.console import Console

from talon.providers import get_provider
from talon.providers.base import ToolResult
from talon.tools import TOOL_DEFINITIONS, dispatch_tool

console = Console()

_MAX_TURNS = int(os.getenv("NAV_PLANNER_MAX_TURNS", "100"))

_READ_ONLY_TOOLS = [
    t for t in TOOL_DEFINITIONS if t["name"] in {"read_file", "list_files", "search_files"}
]

_SYSTEM = """\
You are a navigation planner. Your ONLY job is to explore a web/mobile app workspace
and produce a precise, verified list of browser navigation steps for a QA agent.

Mandatory workflow — complete ALL steps before outputting:

STEP 1: DETECT FRAMEWORK
  - read_file("package.json") — look for next, react-router, expo, vue, nuxt, svelte, remix
  - If no package.json: read_file("requirements.txt") or read_file("pyproject.toml")
  - This determines where routes live.

STEP 2: FIND THE FEATURE ROUTES (goal-focused — do NOT read unrelated files)
  FIRST: search_files for keywords from the goal to find relevant screens quickly.
  THEN: read only the files that implement the goal's feature.
  IGNORE: any screens, routes, or components unrelated to the goal.

  Framework-specific route location (to find the right file paths):
  - Next.js app router:   list_files("app") — page.tsx/page.js files are routes
  - Next.js pages router: list_files("pages") — filenames are routes
  - Expo / React Native:  search_files("Stack.Screen|Tab.Screen|<Screen") — read navigators
  - React Router v6:      search_files("createBrowserRouter|path:") — read router config
  - SvelteKit:            list_files("src/routes") — +page.svelte files are routes
  - Nuxt:                 list_files("pages") — .vue files are routes
  - Vue Router:           read_file("src/router/index.ts") or equivalent
  - Express / Fastify:    search_files("router.get|router.post|app.get") — read router files
  - FastAPI:              search_files("@router.get|@app.get") — read route files
  - Flask:                search_files("@app.route|@blueprint.route") — read route files
  - Django:               read_file("urls.py") or search_files("urlpatterns")

STEP 3: READ THE FEATURE FILES
  - Read the specific screen/component/route files that implement the goal's feature
  - Read the file that handles user profile/settings if the goal involves user data
  - If auth is needed, find and read the login route/screen file to get the exact path
  - STOP reading once you have enough to write the steps — do not explore tangents

STEP 4: BUILD VERIFIED STEPS
  - Write steps only using routes/screens you confirmed by reading files in STEPS 2 & 3
  - Start from the login screen if the app requires authentication
  - Navigate directly to the feature — no unnecessary detours
  - Match each verification step to a specific success criterion

CRITICAL RULES:
- Never reference a URL or screen name you did not confirm by reading a file
- "I found it in the file tree" is NOT enough — you must read_file to confirm content
- If unsure whether a route exists, run search_files before referencing it
- 4–8 steps total
- Output ONLY a JSON array on the final line (no prose, no markdown fences):
  ["Navigate to ...", "Click ...", "Verify that ..."]
"""


def _extract_json_array(text: str) -> list[str] | None:
    """
    Extract a list of strings from LLM output. Tries multiple strategies in order:
    1. JSON/Python array inside a fenced code block
    2. Raw JSON array (double-quoted strings)
    3. Python-style list literal (single-quoted, via ast.literal_eval)
    4. Numbered / bulleted lines as a last resort
    """

    def _is_str_list(obj) -> bool:
        return isinstance(obj, list) and len(obj) > 0 and all(isinstance(s, str) for s in obj)

    # 1. Fenced code block: ```json [...] ``` or ``` [...] ```
    fence = re.search(r"```(?:json|python)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        for loader in (json.loads, ast.literal_eval):
            try:
                data = loader(candidate)
                if _is_str_list(data):
                    return [str(s) for s in data]
            except Exception:
                pass

    # 2 & 3. Walk backwards through [ positions — try JSON then ast.literal_eval
    for m in reversed(list(re.finditer(r"\[", text))):
        start = m.start()
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
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    for loader in (json.loads, ast.literal_eval):
                        try:
                            data = loader(candidate)
                            if _is_str_list(data):
                                return [str(s) for s in data]
                        except Exception:
                            pass
                    break  # try next [ position

    # 4. Numbered / bulleted list fallback
    lines = [
        re.sub(r"^\s*(?:\d+[.)]\s*|-\s*|\*\s*)", "", ln).strip()
        for ln in text.splitlines()
        if re.match(r"^\s*(?:\d+[.)]\s+|-\s+|\*\s+)\S", ln)
    ]
    if len(lines) >= 2:
        return lines

    return None


async def run(
    goal: str,
    workspace: str,
    criteria: list[str],
    app_url: str,
    hint_routes: list[str] | None = None,
) -> list[str]:
    """
    Explore workspace to discover routes and return verified navigation steps.

    Args:
        goal:        The original implementation goal.
        workspace:   Absolute path to the run workspace.
        criteria:    Success criteria the browser agent must verify.
        app_url:     Base URL of the running app (e.g. http://localhost:3000).
        hint_routes: Programmatically discovered routes (Next.js fast-scan) passed
                     as context so the LLM can verify rather than rediscover.

    Returns:
        Ordered list of navigation step strings, or [] on failure.
    """
    console.print("\n[bold cyan]nav-planner[/bold cyan]")

    criteria_text = "\n".join(f"  - {c}" for c in criteria) if criteria else "  (none)"

    hint_section = ""
    if hint_routes:
        route_list = "\n".join(f"  - {r}" for r in hint_routes)
        hint_section = (
            f"\n\nProgrammatically discovered routes (verify these by reading the files "
            f"and use as a starting point):\n{route_list}"
        )

    user_message = (
        f"Goal: {goal}\n\n"
        f"App URL: {app_url}\n\n"
        f"Success criteria to cover:\n{criteria_text}"
        f"{hint_section}\n\n"
        f"Working directory: {workspace}\n\n"
        "Follow the mandatory workflow above and output the navigation steps JSON array."
    )

    provider = get_provider("subagent")
    messages: list[dict] = [{"role": "user", "content": user_message}]
    raw_output = ""

    for turn in range(_MAX_TURNS):
        response = await provider.chat(
            system=_SYSTEM,
            messages=messages,
            tools=_READ_ONLY_TOOLS,
            max_tokens=4096,
        )
        provider.append_assistant(messages, response)

        if response.stop_reason == "end_turn":
            raw_output = response.text or ""
            break

        tool_results: list[ToolResult] = []
        for tc in response.tool_calls:
            console.print(f"  [dim]nav-planner:[/dim] {tc.name}({list(tc.input.values())[:2]})")
            result_str = await asyncio.to_thread(dispatch_tool, tc.name, tc.input, workspace)
            tool_results.append(ToolResult(id=tc.id, content=result_str))
        provider.append_tool_results(messages, tool_results)

    if not raw_output:
        # Exhausted turns without end_turn — ask for JSON now
        messages.append(
            {
                "role": "user",
                "content": (
                    "Output your final navigation steps JSON array now — "
                    "no prose, no markdown fences, just the array."
                ),
            }
        )
        response = await provider.chat(
            system=_SYSTEM,
            messages=messages,
            tools=[],
            max_tokens=1024,
        )
        raw_output = response.text or ""

    steps = _extract_json_array(raw_output)

    # If the model returned prose instead of JSON, ask it to output just the array
    if not steps and raw_output:
        console.print(
            f"  [yellow]nav-planner[/yellow] prose output, requesting JSON correction\n"
            f"  [dim]raw ({len(raw_output)} chars): {raw_output[:300]!r}[/dim]"
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your previous response was not a JSON array. "
                    "Based on the files you already read, output ONLY the navigation steps "
                    "as a JSON array — no prose, no markdown fences:\n"
                    '["step 1", "step 2", ...]'
                ),
            }
        )
        correction = await provider.chat(
            system=_SYSTEM,
            messages=messages,
            tools=[],
            max_tokens=1024,
        )
        steps = _extract_json_array(correction.text or "")
        if not steps:
            console.print(
                f"  [yellow]nav-planner[/yellow] correction also failed — using fallback\n"
                f"  [dim]correction ({len(correction.text or '')} chars): "
                f"{(correction.text or '')[:200]!r}[/dim]"
            )

    if steps:
        console.print(f"  [dim]nav-planner[/dim] {len(steps)} verified steps")
        for i, s in enumerate(steps, 1):
            console.print(f"    [dim]{i}.[/dim] {s[:100]}")

    return steps or []
