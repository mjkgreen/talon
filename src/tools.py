"""
Tool implementations that sub-agents can call via Anthropic tool_use.
Each function maps 1-to-1 with a tool definition in TOOL_DEFINITIONS.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Tool schemas (passed to Anthropic messages.create as `tools=`)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file. Path is relative to the working directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to working_dir"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file, creating parent directories as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories under a path. Supports glob patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to working_dir"},
                "pattern": {"type": "string", "description": "Optional glob pattern, e.g. '**/*.py'"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run a shell command in the working directory. "
            "Returns stdout, stderr, and exit code. "
            "Avoid interactive commands. Timeout is 60 seconds."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "working_dir": {
                    "type": "string",
                    "description": "Sub-directory within working_dir to run in (optional)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_files",
        "description": "Search for a string pattern across files using grep.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Grep pattern"},
                "path": {"type": "string", "description": "Directory to search in (relative to working_dir)"},
                "file_pattern": {"type": "string", "description": "File glob, e.g. '*.py'"},
            },
            "required": ["pattern", "path"],
        },
    },
]


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------

def read_file(path: str, working_dir: str) -> dict:
    full = Path(working_dir) / path
    try:
        return {"content": full.read_text(), "path": str(full)}
    except FileNotFoundError:
        return {"error": f"File not found: {path}"}
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str, working_dir: str) -> dict:
    full = Path(working_dir) / path
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        return {"written": str(full), "bytes": len(content)}
    except Exception as e:
        return {"error": str(e)}


def list_files(path: str, working_dir: str, pattern: str | None = None) -> dict:
    base = Path(working_dir) / path
    try:
        if pattern:
            matches = [str(p.relative_to(working_dir)) for p in base.glob(pattern)]
        else:
            matches = [str(p.relative_to(working_dir)) for p in sorted(base.iterdir())]
        return {"files": matches}
    except Exception as e:
        return {"error": str(e)}


def run_command(command: str, working_dir: str, sub_dir: str | None = None) -> dict:
    cwd = Path(working_dir) / sub_dir if sub_dir else Path(working_dir)
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 60 seconds", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "exit_code": -1}


def search_files(pattern: str, path: str, working_dir: str, file_pattern: str | None = None) -> dict:
    base = str(Path(working_dir) / path)
    cmd = ["grep", "-r", "--include", file_pattern or "*", "-n", pattern, base]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().splitlines()
        return {"matches": lines, "count": len(lines)}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Dispatcher — routes tool_use calls to implementations
# ---------------------------------------------------------------------------

def dispatch_tool(tool_name: str, tool_input: dict, working_dir: str) -> str:
    """Execute a tool call and return result as JSON string."""
    try:
        if tool_name == "read_file":
            result = read_file(tool_input["path"], working_dir)
        elif tool_name == "write_file":
            result = write_file(tool_input["path"], tool_input["content"], working_dir)
        elif tool_name == "list_files":
            result = list_files(tool_input["path"], working_dir, tool_input.get("pattern"))
        elif tool_name == "run_command":
            result = run_command(tool_input["command"], working_dir, tool_input.get("working_dir"))
        elif tool_name == "search_files":
            result = search_files(
                tool_input["pattern"],
                tool_input["path"],
                working_dir,
                tool_input.get("file_pattern"),
            )
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
    except KeyError as e:
        result = {"error": f"Missing required parameter: {e}"}
    except Exception as e:
        result = {"error": str(e)}

    return json.dumps(result)
