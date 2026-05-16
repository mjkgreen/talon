import json
from pathlib import Path

import pytest

from talon.tools import TOOL_DEFINITIONS, dispatch_tool


@pytest.fixture
def wd(tmp_path):
    return str(tmp_path)


class TestReadWrite:
    def test_write_then_read(self, wd):
        w = json.loads(dispatch_tool("write_file", {"path": "hello.txt", "content": "hi"}, wd))
        assert "written" in w

        r = json.loads(dispatch_tool("read_file", {"path": "hello.txt"}, wd))
        assert r["content"] == "hi"

    def test_write_creates_nested_dirs(self, wd):
        dispatch_tool("write_file", {"path": "a/b/c.txt", "content": "deep"}, wd)
        assert Path(wd, "a", "b", "c.txt").read_text() == "deep"

    def test_read_missing_returns_error(self, wd):
        r = json.loads(dispatch_tool("read_file", {"path": "nope.txt"}, wd))
        assert "error" in r

    def test_write_returns_byte_count(self, wd):
        r = json.loads(dispatch_tool("write_file", {"path": "f.txt", "content": "abc"}, wd))
        assert r["bytes"] == 3


class TestListFiles:
    def test_lists_created_files(self, wd):
        Path(wd, "a.py").touch()
        Path(wd, "b.py").touch()
        r = json.loads(dispatch_tool("list_files", {"path": "."}, wd))
        assert len(r["files"]) == 2

    def test_glob_pattern(self, wd):
        Path(wd, "main.py").touch()
        Path(wd, "README.md").touch()
        r = json.loads(dispatch_tool("list_files", {"path": ".", "pattern": "*.py"}, wd))
        assert all(f.endswith(".py") for f in r["files"])

    def test_missing_dir_returns_error(self, wd):
        r = json.loads(dispatch_tool("list_files", {"path": "nonexistent"}, wd))
        assert "error" in r


class TestRunCommand:
    def test_echo(self, wd):
        r = json.loads(dispatch_tool("run_command", {"command": "echo hello"}, wd))
        assert r["stdout"].strip() == "hello"
        assert r["exit_code"] == 0

    def test_failing_command(self, wd):
        r = json.loads(dispatch_tool("run_command", {"command": "false"}, wd))
        assert r["exit_code"] != 0

    def test_stderr_captured(self, wd):
        r = json.loads(dispatch_tool("run_command", {"command": "echo err >&2"}, wd))
        assert "err" in r["stderr"]

    def test_working_dir_respected(self, wd):
        sub = Path(wd, "sub")
        sub.mkdir()
        r = json.loads(dispatch_tool("run_command", {"command": "pwd", "working_dir": "sub"}, wd))
        assert "sub" in r["stdout"]


class TestSearchFiles:
    def test_finds_pattern(self, wd):
        Path(wd, "foo.py").write_text("def hello(): pass\n")
        r = json.loads(dispatch_tool("search_files", {"pattern": "hello", "path": "."}, wd))
        assert r["count"] >= 1

    def test_no_matches(self, wd):
        Path(wd, "foo.py").write_text("def world(): pass\n")
        r = json.loads(dispatch_tool("search_files", {"pattern": "zzznomatch", "path": "."}, wd))
        assert r["count"] == 0


class TestDispatchUnknown:
    def test_unknown_tool_returns_error(self, wd):
        r = json.loads(dispatch_tool("nonexistent", {}, wd))
        assert "error" in r

    def test_missing_required_param_returns_error(self, wd):
        r = json.loads(dispatch_tool("read_file", {}, wd))
        assert "error" in r


class TestToolDefinitions:
    def test_all_tools_defined(self):
        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert names == {"read_file", "write_file", "list_files", "run_command", "search_files"}

    def test_each_has_input_schema(self):
        for tool in TOOL_DEFINITIONS:
            assert "input_schema" in tool
            assert "properties" in tool["input_schema"]
