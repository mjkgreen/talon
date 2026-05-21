export interface PlanPhase {
  name: string;
  description: string;
  dependencies: number[];
}

export interface PlanResult {
  approach: string;
  constraints: string[];
  phases: PlanPhase[];
  success_criteria: string[];
}

export interface BrowserAssertion {
  description: string;
  selector: string | null;
  expected: string | null;
  actual: string | null;
  passed: boolean;
}

export interface BrowserTestResult {
  passed: boolean;
  score: number;
  summary: string;
  assertions: BrowserAssertion[];
  screenshots: string[];
  video_path: string | null;
  steps: number;
  error: string | null;
}

export interface Issue {
  id: number;
  title: string;
  description: string;
  status: string;
  run_id?: string;
  project_id?: number;
  plan_json?: string;
  plan_comments?: string;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: number;
  name: string;
  workspace_mode: string;
  selected_repo?: string;
  local_path?: string;
  created_at: string;
  updated_at: string;
}

export interface Repo {
  full_name: string;
  name: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type RunState = any;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Subtask = any;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type SubtaskResult = any;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type IterationResult = any;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ReviewResult = any;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type RefinementResult = any;
