import React from "react";
import { Check, CheckCircle2, Circle, RefreshCw, XCircle } from "lucide-react";
import type { PhaseResult, PlanResult, IterationResult, ReviewResult, RefinementResult } from "../../types";
import { SubtaskList } from "./SubtaskComponents";
import { LogLines } from "./helpers";
import { parseLiveSubtasks, parseLivePhases, type ParsedLivePhase } from "./parseUtils";

export function PhaseSection({
  phase,
  totalPhases,
  isLive,
  isActive,
  logs,
}: {
  phase: PhaseResult | ParsedLivePhase;
  totalPhases: number | null;
  isLive: boolean;
  isActive: boolean;
  logs: string[];
}) {
  const isDone = "status" in phase ? phase.status === "completed" : phase.subtask_results.length > 0;
  const isRunning = isLive && isActive && !isDone;

  return (
    <div className="border-b border-neutral-800/50 last:border-b-0">
      <div className="px-4 py-2 flex items-center gap-2 bg-neutral-900/40">
        <span className="text-xs font-mono text-neutral-600 shrink-0">
          {phase.phase_index + 1}/{totalPhases ?? "?"}
        </span>
        {isRunning ? (
          <RefreshCw size={12} className="animate-spin text-blue-400 shrink-0" />
        ) : isDone ? (
          <CheckCircle2 size={12} className="text-green-400 shrink-0" />
        ) : (
          <Circle size={12} className="text-neutral-600 shrink-0" />
        )}
        <span
          className={`text-xs font-medium ${
            isDone ? "text-neutral-400" : isRunning ? "text-neutral-200" : "text-neutral-600"
          }`}
        >
          {phase.phase_name}
        </span>
      </div>
      {phase.subtasks.length > 0 && (
        <div className="pl-6">
          <SubtaskList
            subtasks={phase.subtasks}
            subtaskResults={phase.subtask_results}
            isLive={isLive && isActive}
            isLatest={isLive && isActive}
            logs={logs}
          />
        </div>
      )}
    </div>
  );
}

export function IterationContent({
  iteration,
  iterationIndex,
  review,
  refinement,
  isLive,
  isLatest,
  logs,
  scrollRef,
  planResult,
}: {
  iteration: IterationResult;
  iterationIndex: number;
  review: ReviewResult;
  refinement: RefinementResult;
  isLive: boolean;
  isLatest: boolean;
  logs: string[];
  scrollRef: React.RefObject<HTMLDivElement | null>;
  planResult: PlanResult | null;
}) {
  const startStr = `=== Iteration ${iterationIndex + 1}/`;
  const endStr = `=== Iteration ${iterationIndex + 2}/`;
  const startIndex = logs.findIndex((l) => l.startsWith(startStr));
  const endIndex = logs.findIndex((l) => l.startsWith(endStr));

  let iterLogs: string[];
  if (startIndex !== -1) {
    iterLogs = endIndex !== -1 ? logs.slice(startIndex, endIndex) : logs.slice(startIndex);
  } else if (iterationIndex === 0) {
    iterLogs = endIndex !== -1 ? logs.slice(0, endIndex) : logs;
  } else {
    iterLogs = [];
  }

  const livePhases = parseLivePhases(iterLogs);
  const persistedPhases: PhaseResult[] = iteration.phases?.length > 0 ? iteration.phases : [];

  const phaseMap = new Map<number, PhaseResult | ParsedLivePhase>();
  for (const p of livePhases) phaseMap.set(p.phase_index, p);
  for (const p of persistedPhases) phaseMap.set(p.phase_index, p);

  if (planResult) {
    planResult.phases.forEach((ph, i) => {
      if (!phaseMap.has(i)) {
        phaseMap.set(i, {
          phase_index: i,
          phase_name: ph.name,
          subtasks: [],
          subtask_results: [],
        } as ParsedLivePhase);
      }
    });
  }

  const mergedPhases = Array.from(phaseMap.entries())
    .sort(([a], [b]) => a - b)
    .map(([, ph]) => ph);

  const activePhaseIndex =
    livePhases.length > 0 ? livePhases[livePhases.length - 1].phase_index : -1;
  const totalPhases: number | null = planResult
    ? planResult.phases.length
    : mergedPhases.length > 0
      ? mergedPhases.length
      : null;

  const { subtasks: liveSubtasks, subtask_results: liveResults } = parseLiveSubtasks(iterLogs);
  const displaySubtasks =
    iteration.subtasks && iteration.subtasks.length > 0 ? iteration.subtasks : liveSubtasks;
  const displayResults =
    iteration.subtask_results && iteration.subtask_results.length > 0
      ? iteration.subtask_results
      : liveResults;

  return (
    <div>
      {mergedPhases.length > 0 ? (
        <div className="border-b border-neutral-800/50">
          {mergedPhases.map((ph, pi) => (
            <PhaseSection
              key={pi}
              phase={ph}
              totalPhases={totalPhases}
              isLive={isLive}
              isActive={isLive && ph.phase_index === activePhaseIndex}
              logs={iterLogs}
            />
          ))}
        </div>
      ) : (
        displaySubtasks?.length > 0 && (
          <SubtaskList
            subtasks={displaySubtasks}
            subtaskResults={displayResults}
            isLive={isLive}
            isLatest={isLatest}
            logs={logs}
          />
        )
      )}

      {iterLogs.length > 0 && (
        <div className="hidden">
          <LogLines lines={iterLogs} scrollRef={isLatest ? scrollRef : undefined} />
        </div>
      )}

      {isLive && isLatest && !review && !!iteration.aggregated_output && (
        <div className="px-4 py-3 border-b border-neutral-800/50 flex items-center gap-2 text-xs text-neutral-500">
          <RefreshCw size={12} className="animate-spin" /> Waiting for reviewer...
        </div>
      )}

      {review && (
        <div className="p-4 border-b border-neutral-800/50">
          <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">Review</div>
          <div className="flex items-center gap-3 mb-3">
            <span
              className={`text-xs px-2 py-1 rounded font-medium ${
                review.verdict === "pass"
                  ? "bg-green-500/10 text-green-400"
                  : "bg-amber-500/10 text-amber-400"
              }`}
            >
              {review.verdict.toUpperCase()}
            </span>
            <span className="text-xs text-neutral-500">
              Score: {Math.round((review.score ?? 0) * 10)}/10
            </span>
          </div>
          {review.summary && (
            <div className="bg-neutral-900 p-4 rounded border border-neutral-800/50 mb-3">
              <p className="text-xs text-neutral-300">{review.summary}</p>
            </div>
          )}
          {review.blocking_issues?.length > 0 && (
            <div className="text-xs text-red-400 space-y-1">
              {review.blocking_issues.map((issue: string, bi: number) => (
                <div key={bi} className="flex items-start gap-1">
                  <span className="shrink-0">
                    <XCircle size={12} />
                  </span>{" "}
                  {issue}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {refinement && (
        <div className="p-4 bg-amber-500/5">
          <div className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-3">
            Refinement plan
          </div>
          <div className="text-xs text-neutral-400 space-y-1.5">
            {refinement.changes_planned?.map((c: string, ci: number) => (
              <div key={ci} className="flex items-start gap-1.5">
                <span className="shrink-0 text-amber-500">
                  <Check size={12} />
                </span>{" "}
                {c}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
