import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from talon.skills.pr_creator import _commit_and_push, _create_github_pr
from talon.types import ReviewFeedback, ReviewVerdict, RunState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_repo(path: Path) -> Path:
    """Init a bare 'remote' and a working clone; return the clone path."""
    remote = path / "remote.git"
    remote.mkdir()
    subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True)

    repo = path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@talon.dev"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Talon Test"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, capture_output=True)

    (repo / "main.py").write_text("# entry")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "HEAD:main"], cwd=repo, capture_output=True)

    return repo


def _make_worktree(repo: Path, run_id: str) -> Path:
    """Create a worktree branch matching what workspace.setup() would create."""
    branch = f"agent/run-{run_id}"
    wt = repo.parent / f"wt-{run_id}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(wt)],
        cwd=repo,
        capture_output=True,
    )
    return wt


def _make_state(workspace: str | None = None) -> RunState:
    s = RunState(goal="Add a health endpoint")
    s.workspace = workspace
    return s


# ---------------------------------------------------------------------------
# _commit_and_push
# ---------------------------------------------------------------------------


class TestCommitAndPush:
    def test_pushes_clean_worktree(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        run_id = "abc123"
        wt = _make_worktree(repo, run_id)

        branch = _commit_and_push(str(wt), run_id, "Add health endpoint")
        assert branch == f"agent/run-{run_id}"

    def test_commits_changes_before_push(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        run_id = "def456"
        wt = _make_worktree(repo, run_id)

        (wt / "new_file.py").write_text("# new")
        branch = _commit_and_push(str(wt), run_id, "Add health endpoint")
        assert branch is not None

        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(wt),
            capture_output=True,
            text=True,
        )
        assert "Add health endpoint" in log.stdout

    def test_long_goal_truncated_in_commit(self, tmp_path):
        repo = _make_git_repo(tmp_path)
        run_id = "ghi789"
        wt = _make_worktree(repo, run_id)

        (wt / "f.py").write_text("x")
        long_goal = "A" * 200
        branch = _commit_and_push(str(wt), run_id, long_goal)
        assert branch is not None

        log = subprocess.run(
            ["git", "log", "--format=%s", "-1"],
            cwd=str(wt),
            capture_output=True,
            text=True,
        )
        subject = log.stdout.strip()
        assert len(subject) <= 80  # "feat: " + 69 chars + "…"

    def test_returns_none_on_bad_working_dir(self):
        branch = _commit_and_push("/tmp/nonexistent-talon-test-xyz", "run1", "goal")
        assert branch is None


# ---------------------------------------------------------------------------
# _create_github_pr
# ---------------------------------------------------------------------------


class TestCreateGithubPr:
    def _mock_response(self, pr_url: str):
        response = MagicMock()
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        response.read.return_value = json.dumps({"html_url": pr_url}).encode()
        return response

    def test_returns_pr_url(self, monkeypatch):
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_TOKEN", "tok")
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_REPO", "owner/repo")

        state = _make_state()
        pr_url = "https://github.com/owner/repo/pull/42"

        with patch("urllib.request.urlopen", return_value=self._mock_response(pr_url)):
            result = _create_github_pr("agent/run-abc", state, "owner/repo")

        assert result == pr_url

    def test_includes_score_when_review_present(self, monkeypatch):
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_TOKEN", "tok")
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_REPO", "owner/repo")

        state = _make_state()
        state.review_results.append(
            ReviewFeedback(
                verdict=ReviewVerdict.PASS,
                score=0.95,
                summary="Looks good",
                criteria=[],
                blocking_issues=[],
                suggestions=[],
                iteration=1,
            )
        )

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return self._mock_response("https://github.com/owner/repo/pull/1")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _create_github_pr("agent/run-abc", state, "owner/repo")

        assert "95%" in captured["body"]["body"]

    def test_returns_none_on_http_error(self, monkeypatch):
        import urllib.error

        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_TOKEN", "tok")
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_REPO", "owner/repo")

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="",
                code=422,
                msg="Unprocessable",
                hdrs=None,
                fp=MagicMock(read=lambda: b"err"),
            ),
        ):
            result = _create_github_pr("agent/run-abc", _make_state(), "owner/repo")

        assert result is None


# ---------------------------------------------------------------------------
# pr_creator.run()
# ---------------------------------------------------------------------------


class TestPrCreatorRun:
    @pytest.mark.asyncio
    async def test_skips_when_no_workspace(self, monkeypatch):
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_TOKEN", "tok")
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_REPO", "owner/repo")
        from talon.skills import pr_creator

        result = await pr_creator.run(_make_state(workspace=None), None)
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_when_no_token(self, monkeypatch):
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_TOKEN", "")
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_REPO", "owner/repo")
        from talon.skills import pr_creator

        result = await pr_creator.run(_make_state(workspace="/tmp"), None)
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_non_git_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_TOKEN", "tok")
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_REPO", "owner/repo")
        plain = tmp_path / "plain"
        plain.mkdir()
        from talon.skills import pr_creator

        result = await pr_creator.run(_make_state(workspace=str(plain)), None)
        assert result is None

    @pytest.mark.asyncio
    async def test_full_flow(self, tmp_path, monkeypatch):
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_TOKEN", "tok")
        monkeypatch.setattr("talon.skills.pr_creator.GITHUB_REPO", "owner/repo")

        repo = _make_git_repo(tmp_path)
        run_id = "full01"
        wt = _make_worktree(repo, run_id)
        (wt / "app.py").write_text("# new feature")

        state = _make_state(workspace=str(wt))
        state.run_id = run_id

        pr_url = "https://github.com/owner/repo/pull/99"

        response = MagicMock()
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        response.read.return_value = json.dumps({"html_url": pr_url}).encode()

        from talon.skills import pr_creator

        with patch("urllib.request.urlopen", return_value=response):
            result = await pr_creator.run(state, None)

        assert result == pr_url
