from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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


class PlanPhase(BaseModel):
    name: str
    description: str
    dependencies: list[int] = []


class PlanResult(BaseModel):
    approach: str
    constraints: list[str] = []
    phases: list[PlanPhase] = []
    success_criteria: list[str] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BrowserAssertion(BaseModel):
    description: str
    selector: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    passed: bool


class BrowserTestResult(BaseModel):
    passed: bool
    score: float
    summary: str
    assertions: list[BrowserAssertion] = []
    screenshots: list[str] = []
    video_path: Optional[str] = None
    steps: int = 0
    error: Optional[str] = None


class RunState(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    goal: str
    iteration: int = 0
    status: RunStatus = RunStatus.RUNNING
    plan_result: Optional[PlanResult] = None
    executor_results: list[ExecutorResult] = []
    review_results: list[ReviewFeedback] = []
    refinement_results: list[RefinementResult] = []
    final_output: Optional[str] = None
    workspace: Optional[str] = None  # path to isolated run workspace
    video_path: Optional[str] = None
    browser_result: Optional[BrowserTestResult] = None
    pr_url: Optional[str] = None
    board_url: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
