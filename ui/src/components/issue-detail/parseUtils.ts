import type { SubtaskType, SubtaskResultType } from "../../types";

type Subtask = SubtaskType;
type SubtaskResult = SubtaskResultType;

export interface ParsedLivePhase {
  phase_index: number;
  phase_name: string;
  subtasks: SubtaskType[];
  subtask_results: SubtaskResultType[];
}

export function parseLiveSubtasks(iterLogs: string[]): {
  subtasks: Subtask[];
  subtask_results: SubtaskResult[];
} {
  const subtasks: Subtask[] = [];
  const subtask_results: SubtaskResult[] = [];

  for (const line of iterLogs) {
    const launchMatch = line.match(/^->\s+Sub-agent\s+\[([a-f0-9]+)\]\s+(.*)$/i);
    if (launchMatch) {
      const id = launchMatch[1];
      const description = launchMatch[2];
      if (!subtasks.some((st) => st.id === id)) {
        subtasks.push({ id, description, acceptance_criteria: [] });
      }
    }

    const doneMatch = line.match(/^\[([a-f0-9]+)\]\s+(done|modified:.*)$/i);
    if (doneMatch) {
      const id = doneMatch[1];
      const outcome = doneMatch[2];
      const files_modified = outcome.startsWith("modified:")
        ? outcome.substring("modified:".length).split(",").map((f) => f.trim())
        : [];

      if (!subtask_results.some((r) => r.subtask?.id === id)) {
        const subtask = subtasks.find((st) => st.id === id) || {
          id,
          description: "",
          acceptance_criteria: [] as string[],
        };
        subtask_results.push({
          subtask,
          success: true,
          files_modified,
          commands_run: [],
          output: "Success",
        });
      }
    }
  }

  return { subtasks, subtask_results };
}

export function parseLivePhases(logs: string[]): ParsedLivePhase[] {
  const phases: ParsedLivePhase[] = [];
  let current: ParsedLivePhase | null = null;

  for (const line of logs) {
    const phaseMatch = line.match(/^=== Phase (\d+): (.+) ===$/);
    if (phaseMatch) {
      current = {
        phase_index: parseInt(phaseMatch[1], 10) - 1,
        phase_name: phaseMatch[2],
        subtasks: [],
        subtask_results: [],
      };
      phases.push(current);
      continue;
    }
    if (!current) continue;

    const launch = line.match(/^->\s+Sub-agent\s+\[([a-f0-9]+)\]\s+(.*)$/i);
    if (launch && !current.subtasks.find((s) => s.id === launch[1]))
      current.subtasks.push({ id: launch[1], description: launch[2], acceptance_criteria: [] });

    const done = line.match(/^\[([a-f0-9]+)\]\s+(done|modified:.*)$/i);
    if (done && !current.subtask_results.find((r) => r.subtask?.id === done[1])) {
      const files = done[2].startsWith("modified:")
        ? done[2].slice("modified:".length).split(",").map((f) => f.trim())
        : [];
      const subtask = current.subtasks.find((s) => s.id === done[1]) ?? {
        id: done[1],
        description: "",
        acceptance_criteria: [] as string[],
      };
      current.subtask_results.push({
        subtask,
        success: true,
        files_modified: files,
        commands_run: [],
        output: "",
      });
    }
  }
  return phases;
}
