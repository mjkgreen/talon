from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class ReviewVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_WORK = "needs_work"


class Subtask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str
    acceptance_criteria: list[str] = []


class SubtaskResult(BaseModel):
    subtask: Subtask
    output: str
    files_modified: list[str] = []
    commands_run: list[str] = []
    success: bool
    error: Optional[str] = None


class ExecutorResult(BaseModel):
    goal: str
    subtasks: list[Subtask]
    subtask_results: list[SubtaskResult]
    aggregated_output: str
    iteration: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ReviewCriterion(BaseModel):
    criterion: str
    met: bool
    evidence: str


class ReviewFeedback(BaseModel):
    verdict: ReviewVerdict
    score: float  # 0.0 – 1.0
    summary: str
    criteria: list[ReviewCriterion]
    blocking_issues: list[str]
    suggestions: list[str]
    iteration: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RefinementResult(BaseModel):
    feedback: ReviewFeedback
    changes_planned: list[str]
    refined_instructions: str
    iteration: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RunStatus(str, Enum):
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    MAX_ITERATIONS = "max_iterations"


class RunState(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    goal: str
    iteration: int = 0
    status: RunStatus = RunStatus.RUNNING
    executor_results: list[ExecutorResult] = []
    review_results: list[ReviewFeedback] = []
    refinement_results: list[RefinementResult] = []
    final_output: Optional[str] = None
    workspace: Optional[str] = None   # path to isolated run workspace
    video_path: Optional[str] = None
    pr_url: Optional[str] = None
    board_url: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
