from talon.types import (
    ExecutorResult, ReviewFeedback, ReviewVerdict, RefinementResult,
    RunState, RunStatus, Subtask, SubtaskResult,
)


class TestRunState:
    def test_defaults(self):
        s = RunState(goal="test goal")
        assert s.status == RunStatus.RUNNING
        assert s.iteration == 0
        assert s.workspace is None
        assert s.video_path is None
        assert s.board_url is None
        assert len(s.run_id) > 0

    def test_run_id_unique(self):
        a, b = RunState(goal="x"), RunState(goal="x")
        assert a.run_id != b.run_id

    def test_round_trip_json(self):
        s = RunState(goal="round trip")
        restored = RunState.model_validate_json(s.model_dump_json())
        assert restored.goal == s.goal
        assert restored.run_id == s.run_id
        assert restored.status == s.status

    def test_workspace_field(self):
        s = RunState(goal="x")
        s.workspace = "/tmp/talon/run-abc"
        assert s.workspace == "/tmp/talon/run-abc"


class TestSubtask:
    def test_auto_id(self):
        t = Subtask(description="Do something")
        assert len(t.id) > 0

    def test_acceptance_criteria_default_empty(self):
        t = Subtask(description="task")
        assert t.acceptance_criteria == []


class TestReviewFeedback:
    def test_verdict_enum(self):
        assert ReviewVerdict.PASS == "pass"
        assert ReviewVerdict.FAIL == "fail"
        assert ReviewVerdict.NEEDS_WORK == "needs_work"

    def test_score_range(self):
        f = ReviewFeedback(
            verdict=ReviewVerdict.PASS,
            score=0.9,
            summary="Looks good",
            criteria=[],
            blocking_issues=[],
            suggestions=[],
            iteration=1,
        )
        assert 0.0 <= f.score <= 1.0


class TestRunStatus:
    def test_all_statuses(self):
        assert RunStatus.RUNNING == "running"
        assert RunStatus.PASSED == "passed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.MAX_ITERATIONS == "max_iterations"
