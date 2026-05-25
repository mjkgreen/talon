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
  selected_branch?: string;
  local_path?: string;
  start_command?: string;
  project_env_vars?: string;
  env_content?: string;
  cookie_file?: string;
  test_user?: string;
  test_password?: string;
  created_at: string;
  updated_at: string;
}

export interface Repo {
  full_name: string;
  name: string;
}

export interface SubtaskType {
  id: string;
  description: string;
  acceptance_criteria: string[];
}

export interface SubtaskResultType {
  subtask: SubtaskType;
  output: string;
  files_modified: string[];
  commands_run: string[];
  success: boolean;
  error?: string;
}

export interface PhaseResult {
  phase_index: number;
  phase_name: string;
  phase_description: string;
  subtasks: SubtaskType[];
  subtask_results: SubtaskResultType[];
  aggregated_output: string;
  status: "pending" | "running" | "completed" | "failed";
  timestamp: string;
}

export interface IterationResult {
  goal: string;
  phases: PhaseResult[];
  subtasks: SubtaskType[];
  subtask_results: SubtaskResultType[];
  aggregated_output: string;
  iteration: number;
  timestamp: string;
}

// Aliases for backward compat
export type Subtask = SubtaskType;
export type SubtaskResult = SubtaskResultType;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type RunState = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ReviewResult = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type RefinementResult = any;
