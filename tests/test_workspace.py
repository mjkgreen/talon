import subprocess
from pathlib import Path

import pytest

from talon.workspace import setup, teardown, _is_git_repo


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    ws_dir = tmp_path / "workspaces"
    monkeypatch.setenv("WORKSPACE_DIR", str(ws_dir))
    # Reload module so WORKSPACE_BASE picks up the new env var
    import importlib, talon.workspace
    importlib.reload(talon.workspace)
    from talon.workspace import setup as s, teardown as t
    yield tmp_path, s, t
    importlib.reload(talon.workspace)


class TestFreshWorkspace:
    def test_creates_directory(self, ws_env):
        _, s, t = ws_env
        ws = s("run-fresh-001")
        assert Path(ws).is_dir()

    def test_teardown_removes_directory(self, ws_env):
        _, s, t = ws_env
        ws = s("run-fresh-002")
        t("run-fresh-002", None, ws)
        assert not Path(ws).exists()

    def test_teardown_nonexistent_is_safe(self, ws_env):
        _, s, t = ws_env
        t("run-noop", None, "/tmp/talon-test-nonexistent-xyz")  # should not raise


class TestPlainDirCopy:
    def test_copies_files(self, ws_env, tmp_path):
        _, s, t = ws_env
        src = tmp_path / "project"
        src.mkdir()
        (src / "main.py").write_text("print('hello')")
        (src / "README.md").write_text("# project")

        ws = s("run-copy-001", base_dir=str(src))
        assert (Path(ws) / "main.py").read_text() == "print('hello')"
        assert (Path(ws) / "README.md").exists()

    def test_teardown_removes_copy(self, ws_env, tmp_path):
        _, s, t = ws_env
        src = tmp_path / "src2"
        src.mkdir()
        ws = s("run-copy-002", base_dir=str(src))
        t("run-copy-002", str(src), ws)
        assert not Path(ws).exists()

    def test_original_untouched(self, ws_env, tmp_path):
        _, s, t = ws_env
        src = tmp_path / "src3"
        src.mkdir()
        (src / "keep.txt").write_text("original")
        ws = s("run-copy-003", base_dir=str(src))
        Path(ws, "keep.txt").write_text("modified")
        assert (src / "keep.txt").read_text() == "original"


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@talon.dev"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Talon Test"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True)
    (repo / "main.py").write_text("# entry point")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    return repo


class TestGitWorktree:
    def test_worktree_created(self, ws_env, git_repo):
        _, s, t = ws_env
        ws = s("run-wt-001", base_dir=str(git_repo))
        assert Path(ws).is_dir()

    def test_worktree_is_git_repo(self, ws_env, git_repo):
        _, s, t = ws_env
        ws = s("run-wt-002", base_dir=str(git_repo))
        assert _is_git_repo(Path(ws))

    def test_worktree_has_source_files(self, ws_env, git_repo):
        _, s, t = ws_env
        ws = s("run-wt-003", base_dir=str(git_repo))
        assert (Path(ws) / "main.py").exists()

    def test_worktree_teardown(self, ws_env, git_repo):
        _, s, t = ws_env
        ws = s("run-wt-004", base_dir=str(git_repo))
        t("run-wt-004", str(git_repo), ws)
        assert not Path(ws).exists()


class TestIsGitRepo:
    def test_plain_dir_is_not_git(self, tmp_path):
        assert not _is_git_repo(tmp_path)

    def test_git_repo_detected(self, git_repo):
        assert _is_git_repo(git_repo)
