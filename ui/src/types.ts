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

export interface Issue {
  id: number;
  title: string;
  description: string;
  status: string;
  run_id?: string;
  project_id?: number;
  plan_json?: string;
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
