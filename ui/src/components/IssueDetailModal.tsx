import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  XCircle,
  Video,
  Download,
  FileText,
  Lightbulb,
  MessageSquare,
  Pencil,
  Play,
  RefreshCw,
  Settings,
  X,
} from "lucide-react";
import { apiUrl } from "../utils";
import type { Issue, PlanResult, PhaseResult, RunState, SubtaskType, SubtaskResultType, IterationResult, ReviewResult, RefinementResult } from "../types";

// Backward-compat aliases used by SubtaskList
type Subtask = SubtaskType;
type SubtaskResult = SubtaskResultType;

interface IssueDetailModalProps {
  issue: Issue;
  liveRunStates: Record<number, RunState>;
  runState: RunState | null;
  runErrors: Record<number, string>;
  runLogs: Record<number, string[]>;
  loadingRunState: boolean;
  planningIssues: Set<number>;
  activeTraceTab: "plan" | number;
  setActiveTraceTab: (v: "plan" | number) => void;
  editingPlan: boolean;
  setEditingPlan: (v: boolean) => void;
  planDraft: PlanResult | null;
  setPlanDraft: React.Dispatch<React.SetStateAction<PlanResult | null>>;
  followLatestRef: React.MutableRefObject<boolean>;
  onClose: () => void;
}

function logLineClass(line: string) {
  if (line.startsWith("===")) return "text-blue-500";
  if (line.startsWith("->")) return "text-cyan-500";
  if (line.startsWith("Files modified:")) return "text-green-500";
  if (line.includes("modified:")) return "text-green-600";
  return "text-neutral-400";
}

function LogLines({ lines, scrollRef }: { lines: string[]; scrollRef?: React.RefObject<HTMLDivElement | null> }) {
  return (
    <div
      ref={scrollRef}
      className="bg-black/30 px-4 py-3 font-mono text-xs max-h-44 overflow-y-auto overflow-x-hidden"
    >
      {lines.map((line, i) => (
        <div key={i} className="leading-relaxed flex gap-2 min-w-0">
          <span className="text-neutral-700 shrink-0 select-none">[server]</span>
          <span className={`break-words min-w-0 ${logLineClass(line)}`}>{line}</span>
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const base = "text-xs px-2 py-1 rounded-full flex items-center gap-1";
  if (status === "Done")
    return (
      <span className={`${base} bg-green-500/10 text-green-400 border border-green-500/20`}>
        <CheckCircle2 size={10} /> {status}
      </span>
    );
  if (status === "Failed")
    return (
      <span className={`${base} bg-red-500/10 text-red-400 border border-red-500/20`}>
        <AlertCircle size={10} /> {status}
      </span>
    );
  if (status === "In Progress")
    return (
      <span className={`${base} bg-blue-500/10 text-blue-400 border border-blue-500/20`}>
        <Play size={10} className="animate-pulse" /> {status}
      </span>
    );
  return (
    <span className={`${base} bg-neutral-800 text-neutral-400 border border-neutral-700`}>{status}</span>
  );
}

function PlanSection({
  issue,
  planningIssues,
  editingPlan,
  setEditingPlan,
  planDraft,
  setPlanDraft,
}: {
  issue: Issue;
  planningIssues: Set<number>;
  editingPlan: boolean;
  setEditingPlan: (v: boolean) => void;
  planDraft: PlanResult | null;
  setPlanDraft: React.Dispatch<React.SetStateAction<PlanResult | null>>;
}) {
  const [commentDraft, setCommentDraft] = useState("");

  const isPlanning = planningIssues.has(issue.id);
  const storedPlan: PlanResult | null = issue.plan_json
    ? (() => {
        try {
          return JSON.parse(issue.plan_json!);
        } catch {
          return null;
        }
      })()
    : null;
  const displayPlan = editingPlan ? planDraft : storedPlan;
  const comments: string[] = issue.plan_comments
    ? (() => {
        try {
          return JSON.parse(issue.plan_comments);
        } catch {
          return [];
        }
      })()
    : [];

  const savePlan = async () => {
    if (!planDraft) return;
    await fetch(apiUrl(`/api/issues/${issue.id}/plan`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_json: JSON.stringify(planDraft) }),
    });
    setEditingPlan(false);
    setPlanDraft(null);
  };

  const addComment = async () => {
    const text = commentDraft.trim();
    if (!text) return;
    setCommentDraft("");
    await fetch(apiUrl(`/api/issues/${issue.id}/plan/comments`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment: text }),
    });
  };

  const refinePlan = async () => {
    await fetch(apiUrl(`/api/issues/${issue.id}/plan/refine`), { method: "POST" });
  };

  return (
    <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-neutral-800/50">
        <h3 className="text-sm font-medium text-neutral-400 uppercase tracking-wider flex items-center gap-2">
          <Lightbulb size={14} className="text-violet-400" /> Implementation Plan
        </h3>
        {isPlanning && (
          <span className="text-xs text-violet-400 flex items-center gap-1">
            <RefreshCw size={11} className="animate-spin" /> Generating...
          </span>
        )}
        {!isPlanning && storedPlan && !editingPlan && issue.status === "Backlog" && (
          <button
            onClick={() => {
              setEditingPlan(true);
              setPlanDraft(storedPlan);
            }}
            className="text-xs text-neutral-500 hover:text-white flex items-center gap-1 transition-colors"
          >
            <Pencil size={12} /> Edit
          </button>
        )}
        {editingPlan && (
          <div className="flex items-center gap-2">
            <button onClick={savePlan} className="text-xs text-green-400 hover:text-green-300 flex items-center gap-1">
              <Check size={12} /> Save
            </button>
            <button
              onClick={() => {
                setEditingPlan(false);
                setPlanDraft(null);
              }}
              className="text-xs text-neutral-500 hover:text-white"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {isPlanning && !storedPlan && (
        <div className="p-5 text-xs text-neutral-500 flex items-center gap-2">
          <RefreshCw size={12} className="animate-spin text-violet-400" />
          Analysing your goal and generating an implementation plan...
        </div>
      )}

      {displayPlan && (
        <div className="p-5 space-y-4">
          <div>
            <div className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">Approach</div>
            {editingPlan ? (
              <textarea
                className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-violet-500 resize-none"
                rows={3}
                value={planDraft?.approach ?? ""}
                onChange={(e) => setPlanDraft((p) => (p ? { ...p, approach: e.target.value } : p))}
              />
            ) : (
              <p className="text-sm text-neutral-300 leading-relaxed">{displayPlan.approach}</p>
            )}
          </div>

          {displayPlan.phases?.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-2">Phases</div>
              <div className="space-y-2">
                {displayPlan.phases.map((ph, pi) => (
                  <div key={pi} className="flex items-start gap-2 text-xs">
                    <span className="text-neutral-600 shrink-0 mt-0.5 font-mono">{pi + 1}.</span>
                    <div className="flex-1">
                      <span className="text-neutral-300 font-medium">{ph.name}</span>
                      {editingPlan ? (
                        <input
                          className="block w-full mt-1 bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-xs text-neutral-300 focus:outline-none focus:border-violet-500"
                          value={planDraft?.phases[pi]?.description ?? ""}
                          onChange={(e) =>
                            setPlanDraft((p) => {
                              if (!p) return p;
                              const phases = p.phases.map((ph2, i) =>
                                i === pi ? { ...ph2, description: e.target.value } : ph2,
                              );
                              return { ...p, phases };
                            })
                          }
                        />
                      ) : (
                        <span className="text-neutral-500 ml-2">{ph.description}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {displayPlan.success_criteria?.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-2">
                Success Criteria
              </div>
              <div className="space-y-1.5">
                {displayPlan.success_criteria.map((sc, si) => (
                  <div key={si} className="flex items-start gap-2 text-xs">
                    <span className="text-neutral-600 shrink-0 mt-0.5"><Circle size={12} className="text-neutral-500" /></span>
                    {editingPlan ? (
                      <input
                        className="flex-1 bg-neutral-900 border border-neutral-700 rounded px-2 py-1 text-xs text-neutral-300 focus:outline-none focus:border-violet-500"
                        value={planDraft?.success_criteria[si] ?? ""}
                        onChange={(e) =>
                          setPlanDraft((p) => {
                            if (!p) return p;
                            const success_criteria = p.success_criteria.map((s, i) =>
                              i === si ? e.target.value : s,
                            );
                            return { ...p, success_criteria };
                          })
                        }
                      />
                    ) : (
                      <span className="text-neutral-400">{sc}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Feedback section — shown when plan exists and not in edit mode */}
      {storedPlan && !editingPlan && (
        <div className="border-t border-neutral-800/50 px-5 py-4 space-y-3">
          <div className="text-xs font-semibold text-neutral-500 uppercase tracking-wider flex items-center gap-2">
            <MessageSquare size={12} /> Feedback
          </div>
          {comments.length > 0 && (
            <div className="space-y-1.5">
              {comments.map((c, ci) => (
                  <div key={ci} className="flex items-start gap-2 text-xs">
                    <span className="text-neutral-600 shrink-0 mt-0.5"><MessageSquare size={12} className="text-neutral-500" /></span>
                    <span className="text-neutral-400">{c}</span>
                </div>
              ))}
            </div>
          )}
          <textarea
            className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-xs text-neutral-200 focus:outline-none focus:border-violet-500 resize-none"
            rows={2}
            placeholder="Add feedback for the plan refiner... (Ctrl+Enter to submit)"
            value={commentDraft}
            onChange={(e) => setCommentDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) addComment();
            }}
          />
          <div className="flex gap-2">
            <button
              onClick={addComment}
              disabled={!commentDraft.trim() || isPlanning || issue.status !== "Backlog"}
              className="text-xs text-neutral-300 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 px-3 py-1.5 rounded transition-colors disabled:opacity-40"
            >
              Add Comment
            </button>
            <button
              onClick={refinePlan}
              disabled={comments.length === 0 || isPlanning || issue.status !== "Backlog"}
              className="text-xs text-violet-300 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/30 px-3 py-1.5 rounded transition-colors disabled:opacity-40 flex items-center gap-1.5"
              title={comments.length === 0 ? "Add a comment first" : "Refine plan based on feedback"}
            >
              {isPlanning
                ? <RefreshCw size={11} className="animate-spin" />
                : <Lightbulb size={11} />
              }
              Refine Plan
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


function parseLiveSubtasks(iterLogs: string[]): { subtasks: Subtask[]; subtask_results: SubtaskResult[] } {
  const subtasks: Subtask[] = [];
  const subtask_results: SubtaskResult[] = [];

  for (const line of iterLogs) {
    const launchMatch = line.match(/^->\s+Sub-agent\s+\[([a-f0-9]+)\]\s+(.*)$/i);
    if (launchMatch) {
      const id = launchMatch[1];
      const description = launchMatch[2];
      if (!subtasks.some(st => st.id === id)) {
        subtasks.push({ id, description, acceptance_criteria: [] });
      }
    }

    const doneMatch = line.match(/^\[([a-f0-9]+)\]\s+(done|modified:.*)$/i);
    if (doneMatch) {
      const id = doneMatch[1];
      const outcome = doneMatch[2];
      const files_modified = outcome.startsWith("modified:") 
        ? outcome.substring("modified:".length).split(",").map(f => f.trim()) 
        : [];
      
      if (!subtask_results.some(r => r.subtask?.id === id)) {
        const subtask = subtasks.find(st => st.id === id) || { id, description: "", acceptance_criteria: [] as string[] };
        subtask_results.push({
          subtask,
          success: true,
          files_modified,
          commands_run: [],
          output: "Success"
        });
      }
    }
  }

  return { subtasks, subtask_results };
}


interface ParsedLivePhase {
  phase_index: number;
  phase_name: string;
  subtasks: SubtaskType[];
  subtask_results: SubtaskResultType[];
}

function parseLivePhases(logs: string[]): ParsedLivePhase[] {
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
    if (launch && !current.subtasks.find(s => s.id === launch[1]))
      current.subtasks.push({ id: launch[1], description: launch[2], acceptance_criteria: [] });

    const done = line.match(/^\[([a-f0-9]+)\]\s+(done|modified:.*)$/i);
    if (done && !current.subtask_results.find(r => r.subtask?.id === done[1])) {
      const files = done[2].startsWith("modified:")
        ? done[2].slice("modified:".length).split(",").map(f => f.trim())
        : [];
      const subtask = current.subtasks.find(s => s.id === done[1]) ?? { id: done[1], description: "", acceptance_criteria: [] as string[] };
      current.subtask_results.push({ subtask, success: true, files_modified: files, commands_run: [], output: "" });
    }
  }
  return phases;
}

function PhaseSection({
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

function IterationContent({
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
  const startIndex = logs.findIndex(l => l.startsWith(startStr));
  const endIndex = logs.findIndex(l => l.startsWith(endStr));

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

  // Merge persisted (completed) and live (in-progress) phases by index.
  // Persisted takes priority — it has the full completed data.
  // Live fills in phases that have started but aren't persisted yet.
  const phaseMap = new Map<number, PhaseResult | ParsedLivePhase>();
  for (const p of livePhases) phaseMap.set(p.phase_index, p);
  for (const p of persistedPhases) phaseMap.set(p.phase_index, p); // overwrite live with persisted

  // Add plan stubs for future phases not yet seen in logs
  if (planResult) {
    planResult.phases.forEach((ph, i) => {
      if (!phaseMap.has(i)) {
        phaseMap.set(i, { phase_index: i, phase_name: ph.name, subtasks: [], subtask_results: [] } as ParsedLivePhase);
      }
    });
  }

  const mergedPhases = Array.from(phaseMap.entries())
    .sort(([a], [b]) => a - b)
    .map(([, ph]) => ph);

  // The actively running phase is the last one seen in live logs (not yet completed).
  const activePhaseIndex = livePhases.length > 0 ? livePhases[livePhases.length - 1].phase_index : -1;
  const totalPhases: number | null = planResult ? planResult.phases.length : mergedPhases.length > 0 ? mergedPhases.length : null;

  // Fallback flat subtask data for old run states that have no phases
  const { subtasks: liveSubtasks, subtask_results: liveResults } = parseLiveSubtasks(iterLogs);
  const displaySubtasks = iteration.subtasks && iteration.subtasks.length > 0 ? iteration.subtasks : liveSubtasks;
  const displayResults = iteration.subtask_results && iteration.subtask_results.length > 0 ? iteration.subtask_results : liveResults;

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
      ) : displaySubtasks?.length > 0 && (
        <SubtaskList
          subtasks={displaySubtasks}
          subtaskResults={displayResults}
          isLive={isLive}
          isLatest={isLatest}
          logs={logs}
        />
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
              className={`text-xs px-2 py-1 rounded font-medium ${review.verdict === "pass" ? "bg-green-500/10 text-green-400" : "bg-amber-500/10 text-amber-400"}`}
            >
              {review.verdict.toUpperCase()}
            </span>
            <span className="text-xs text-neutral-500">Score: {Math.round((review.score ?? 0) * 10)}/10</span>
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
                  <span className="shrink-0"><XCircle size={12} /></span> {issue}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {refinement && (
        <div className="p-4 bg-amber-500/5">
          <div className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-3">Refinement plan</div>
          <div className="text-xs text-neutral-400 space-y-1.5">
            {refinement.changes_planned?.map((c: string, ci: number) => (
              <div key={ci} className="flex items-start gap-1.5">
                <span className="shrink-0 text-amber-500"><Check size={12} /></span> {c}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SubtaskItem({
  st,
  stResult,
  isRunning,
  liveDone,
  iconColor,
  textColor,
}: {
  st: Subtask;
  stResult: SubtaskResult | undefined;
  isRunning: boolean;
  liveDone: boolean;
  iconColor: string;
  textColor: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasOutput = !!stResult?.output;
  const filesModified: string[] = stResult?.files_modified ?? [];

  return (
    <div className="flex flex-col gap-1 text-xs">
      <div className="flex items-start gap-2">
        <span className={`mt-0.5 shrink-0 ${iconColor}`}>
          {isRunning ? (
            <RefreshCw size={12} className="animate-spin" />
          ) : stResult?.success || liveDone ? (
            <CheckCircle2 size={12} />
          ) : stResult ? (
            <XCircle size={12} />
          ) : (
            <Circle size={12} />
          )}
        </span>
        <div className="flex-1 min-w-0">
          <div className={textColor}>{st.description}</div>
          {filesModified.length > 0 && (
            <div className="mt-0.5 text-neutral-600 font-mono truncate">
              {filesModified.slice(0, 3).join(", ")}
              {filesModified.length > 3 && ` +${filesModified.length - 3} more`}
            </div>
          )}
        </div>
        {hasOutput && (
          <button
            onClick={() => setExpanded(e => !e)}
            className="shrink-0 text-neutral-600 hover:text-neutral-400 mt-0.5"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        )}
      </div>
      {expanded && stResult?.output && (
        <div className="ml-5 bg-neutral-950 rounded border border-neutral-800/50 p-2 overflow-x-auto max-h-64">
          <pre className="text-xs text-neutral-500 font-mono whitespace-pre-wrap">{stResult.output}</pre>
        </div>
      )}
    </div>
  );
}

function SubtaskList({
  subtasks,
  subtaskResults,
  isLive,
  isLatest,
  logs,
}: {
  subtasks: Subtask[];
  subtaskResults: SubtaskResult[];
  isLive: boolean;
  isLatest: boolean;
  logs: string[];
}) {
  const doneCount = subtasks.filter(st => {
    const stResult = subtaskResults?.find((r: SubtaskResult) => r.subtask?.id === st.id);
    const liveDone = !stResult && isLive && logs.some((line) => line.startsWith(`[${st.id}]`));
    return (stResult && stResult.success) || liveDone;
  }).length;
  const totalCount = subtasks.length;
  const allDone = doneCount >= totalCount;

  return (
    <div className="p-4 border-b border-neutral-800/50">
      <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3 flex items-center gap-2">
        Subagents
        {isLive && isLatest && !allDone && (
          <span className="font-normal normal-case text-neutral-600">
            {doneCount}/{totalCount} complete
          </span>
        )}
      </div>
      <div className="space-y-2">
        {subtasks.map((st: Subtask, si: number) => {
          const stResult = subtaskResults?.find((r: SubtaskResult) => r.subtask?.id === st.id);
          const liveStarted =
            !stResult && isLive && logs.some((line) => line.startsWith("->") && line.includes(`[${st.id}]`));
          const liveDone =
            !stResult && isLive && logs.some((line) => line.startsWith(`[${st.id}]`));
          const isRunning = liveStarted && !liveDone;

          const iconColor = stResult?.success
            ? "text-green-400"
            : stResult
              ? "text-red-400"
              : liveDone
                ? "text-green-400"
                : isRunning
                  ? "text-blue-400"
                  : "text-neutral-700";

          const textColor =
            isRunning ? "text-neutral-300" : stResult?.success || liveDone ? "text-neutral-400" : "text-neutral-500";

          return (
            <SubtaskItem
              key={si}
              st={st}
              stResult={stResult}
              isRunning={isRunning}
              liveDone={liveDone}
              iconColor={iconColor}
              textColor={textColor}
            />
          );
        })}
      </div>
    </div>
  );
}

interface LimitHint {
  message: string;
  setting: string;
}

function detectLimitHint(error: string): LimitHint | null {
  const e = error.toLowerCase();
  if (
    e.includes("context_window") || e.includes("context window") ||
    e.includes("token count exceeds") || e.includes("maximum number of tokens") ||
    e.includes("context_window_exceeded") || e.includes("max_tokens")
  ) {
    return {
      message: "The model hit its token limit.",
      setting: "Increase Max tokens per agent call in Settings → Limits.",
    };
  }
  if (e.includes("rate limit") || e.includes("ratelimit") || e.includes("too many requests") || e.includes("429")) {
    return {
      message: "The provider rate-limited the request.",
      setting: "Try switching to a different model or provider in Settings → Model.",
    };
  }
  if (e.includes("timeout") || e.includes("timed out")) {
    return {
      message: "An agent call timed out.",
      setting: "The model may be overloaded — retry, or switch models in Settings → Model.",
    };
  }
  return null;
}

export function IssueDetailModal({
  issue,
  liveRunStates,
  runState,
  runErrors,
  runLogs,
  loadingRunState,
  planningIssues,
  activeTraceTab,
  setActiveTraceTab,
  editingPlan,
  setEditingPlan,
  planDraft,
  setPlanDraft,
  followLatestRef,
  onClose,
}: IssueDetailModalProps) {
  const activityLogRef = useRef<HTMLDivElement>(null);
  const logs = React.useMemo(() => runLogs[issue.id] ?? [], [runLogs, issue.id]);
  const [macroTab, setMacroTab] = useState<"plan" | "trace" | "video">(
    issue.status === "Queued" || issue.status === "Backlog" ? "plan" : "trace"
  );

  useEffect(() => {
    const el = activityLogRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  const activeRunState = liveRunStates[issue.id] || runState;
  const runError = runErrors[issue.id];
  const isLive = issue.status === "In Progress" && !!liveRunStates[issue.id];
  const iterations: IterationResult[] = activeRunState?.executor_results ?? [];
  let maxLogIteration = 0;
  for (const line of logs) {
    const match = line.match(/^=== Iteration (\d+)\/\d+ ===/);
    if (match) {
      const num = parseInt(match[1], 10);
      if (num > maxLogIteration) {
        maxLogIteration = num;
      }
    }
  }
  const tabCount = Math.max(iterations.length, activeRunState?.iteration || 0, maxLogIteration);
  const tabIndices = Array.from({ length: tabCount }, (_, i) => i);

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
      <div className="bg-neutral-900 border border-neutral-800 p-8 rounded-2xl w-full max-w-4xl shadow-2xl relative overflow-hidden flex flex-col h-[90vh]">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 text-neutral-500 hover:text-white bg-neutral-800 hover:bg-neutral-700 rounded-lg transition-colors z-10"
        >
          <X size={20} />
        </button>

        <div className="flex items-start gap-4 mb-6 pr-12">
          <div className="bg-neutral-800 p-3 rounded-xl border border-neutral-700 text-blue-400">
            <FileText size={24} />
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-xs font-mono text-neutral-500 bg-neutral-950 px-2 py-1 rounded">
                T-{issue.id}
              </span>
              <StatusBadge status={issue.status} />
            </div>
            <h2 className="text-2xl font-bold text-white">{issue.title}</h2>
          </div>
        </div>

        <div className="flex border-b border-neutral-800 mb-6 shrink-0 gap-6">
          <button
            onClick={() => setMacroTab("plan")}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              macroTab === "plan" ? "border-violet-500 text-white" : "border-transparent text-neutral-500 hover:text-neutral-300"
            }`}
          >
            Plan
          </button>
          <button
            onClick={() => setMacroTab("trace")}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              macroTab === "trace" ? "border-blue-500 text-white" : "border-transparent text-neutral-500 hover:text-neutral-300"
            }`}
          >
            Execution Trace
          </button>
          {(activeRunState?.video_path || activeRunState?.browser_result?.gif_path) && (
            <button
              onClick={() => setMacroTab("video")}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                macroTab === "video" ? "border-green-500 text-white" : "border-transparent text-neutral-500 hover:text-neutral-300"
              }`}
            >
              <Video size={14} /> Verification
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto pr-2 space-y-6">
          {issue.description && (
            <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl p-5">
              <h3 className="text-sm font-medium text-neutral-400 mb-3 uppercase tracking-wider">Description</h3>
              <div className="text-neutral-300 text-sm whitespace-pre-wrap">{issue.description}</div>
            </div>
          )}

          {macroTab === "plan" && (
            <PlanSection
              issue={issue}
              planningIssues={planningIssues}
              editingPlan={editingPlan}
              setEditingPlan={setEditingPlan}
              planDraft={planDraft}
              setPlanDraft={setPlanDraft}
            />
          )}

          {macroTab === "trace" && (
            <>
              {activeRunState?.status === "max_iterations" && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4 text-sm text-yellow-400 flex gap-3">
                  <AlertCircle size={16} className="shrink-0 mt-0.5" />
                  <div>
                    <div className="font-medium mb-1">Max iterations reached</div>
                    <div className="text-yellow-300/80 text-xs">
                      The agent exhausted all retry cycles without passing review. Increase{" "}
                      <strong>Max iterations</strong> in{" "}
                      <span className="inline-flex items-center gap-1"><Settings size={11} /> Settings → Limits</span>{" "}
                      and re-run.
                    </div>
                  </div>
                </div>
              )}

              {(runError || activeRunState?.error) && (() => {
                const raw = runError || activeRunState?.error || "";
                const hint = detectLimitHint(raw);
                return (
                  <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-sm text-red-400">
                    <div className="font-medium mb-1">Agent error</div>
                    <pre className="text-xs font-mono whitespace-pre-wrap text-red-300/80">{raw}</pre>
                    {hint && (
                      <div className="mt-3 pt-3 border-t border-red-500/20 text-xs text-yellow-300/90 flex gap-2">
                        <AlertCircle size={13} className="shrink-0 mt-0.5" />
                        <span>
                          <strong>{hint.message}</strong> {hint.setting}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })()}

          {issue.status === "In Progress" && !activeRunState && !runError && (
            <div className="flex items-center gap-3 p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl text-blue-400 text-sm">
              <RefreshCw size={16} className="animate-spin shrink-0" />
              Agent is starting up...
            </div>
          )}

          {loadingRunState && !activeRunState && (
            <div className="flex items-center justify-center p-12 text-neutral-500 gap-3">
              <RefreshCw size={20} className="animate-spin" /> Fetching agent logs...
            </div>
          )}

          {activeRunState && (
            <div className="space-y-4">
              <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                <div className="bg-neutral-900 border-b border-neutral-800 p-4 flex justify-between items-center">
                  <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                    <Activity size={16} className="text-blue-400" />
                    Execution Trace
                    {isLive && (
                      <span className="flex items-center gap-1 text-xs text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded-full ml-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                        Live
                      </span>
                    )}
                  </h3>
                  <div className="flex items-center gap-3">
                    {(() => {
                      const inTok = activeRunState.total_input_tokens ?? 0;
                      const outTok = activeRunState.total_output_tokens ?? 0;
                      const cacheRead = activeRunState.total_cache_read_tokens ?? 0;
                      const cost = activeRunState.total_cost_usd ?? 0;
                      const totalTok = inTok + outTok;
                      const cachePct = inTok > 0 ? Math.round(cacheRead / inTok * 100) : 0;
                      if (totalTok === 0) return null;
                      return (
                        <div className="flex items-center gap-2 text-xs text-neutral-500 font-mono">
                          <span title="Total tokens">{totalTok >= 1000 ? `${(totalTok / 1000).toFixed(1)}k` : totalTok} tok</span>
                          {cachePct > 0 && <span title="Cache hit rate" className="text-green-600">{cachePct}% cached</span>}
                          {cost > 0 && <span title="Estimated cost" className="text-yellow-600">${cost.toFixed(4)}</span>}
                        </div>
                      );
                    })()}
                    <span className="text-xs text-neutral-500 font-mono">Run: {activeRunState.run_id}</span>
                  </div>
                  </div>

                {tabCount > 0 && (
                  <div className="flex border-b border-neutral-800 bg-neutral-900/30 overflow-x-auto">
                    {tabIndices.map((idx: number) => {
                      const review = activeRunState.review_results?.[idx];
                      const isActiveTab = activeTraceTab === idx || (activeTraceTab === "plan" && idx === 0);
                      const isPassing = review?.verdict === "pass";
                      const isFailing = review && review.verdict !== "pass";
                      const isRunning = isLive && idx === tabCount - 1 && !review;
                      return (
                        <button
                          key={idx}
                          onClick={() => {
                            setActiveTraceTab(idx);
                            followLatestRef.current = idx === tabCount - 1;
                          }}
                          className={`flex items-center gap-2 px-4 py-3 text-xs font-medium whitespace-nowrap border-b-2 transition-colors ${
                            isActiveTab
                              ? "border-blue-500 text-white bg-neutral-800/50"
                              : "border-transparent text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/30"
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full shrink-0 ${isPassing ? "bg-green-400" : isFailing ? "bg-amber-400" : isRunning ? "bg-blue-400 animate-pulse" : "bg-neutral-600"}`}
                          />
                          Iteration {idx + 1}
                          {isRunning && <RefreshCw size={10} className="animate-spin text-neutral-500" />}
                        </button>
                      );
                    })}
                  </div>
                )}

                {tabCount === 0 && (
                  <div className="p-8 text-center text-neutral-500 text-sm flex flex-col items-center gap-3">
                    <RefreshCw size={20} className="animate-spin text-blue-500" />
                    Agent initializing... decomposing goal into subtasks...
                  </div>
                )}

                {tabCount > 0 && (() => {
                  const iterIdx = typeof activeTraceTab === "number" ? activeTraceTab : 0;
                  const clampedTab = Math.min(iterIdx, tabCount - 1);
                  const currentIteration = iterations[clampedTab] || {
                    subtasks: [],
                    subtask_results: [],
                    aggregated_output: ""
                  };
                  return (
                    <IterationContent
                      iteration={currentIteration}
                      iterationIndex={clampedTab}
                      review={activeRunState.review_results?.[clampedTab]}
                      refinement={activeRunState.refinement_results?.[clampedTab]}
                      isLive={isLive}
                      isLatest={clampedTab === tabCount - 1}
                      logs={logs}
                      scrollRef={activityLogRef}
                      planResult={activeRunState?.plan_result ?? null}
                    />
                  );
                })()}
              </div>
            </div>
          )}
            </>
          )}

          {macroTab === "video" && activeRunState?.video_path && (
            <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
              <div className="bg-neutral-900 border-b border-neutral-800 p-4 flex items-center justify-between">
                <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                  <Play size={16} className="text-blue-400" /> Video Verification
                </h3>
                {activeRunState?.browser_result?.gif_path && (
                  <a
                    href={apiUrl(`/api/runs/${activeRunState.run_id}/gif`)}
                    download="browser-validation.gif"
                    className="flex items-center gap-1.5 text-xs text-neutral-400 hover:text-white bg-neutral-800 hover:bg-neutral-700 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    <Download size={13} /> Download GIF
                  </a>
                )}
              </div>
              <div className="p-4 flex justify-center bg-black">
                <video
                  controls
                  className="max-w-full max-h-[400px] rounded border border-neutral-800"
                  src={apiUrl(`/api/runs/${activeRunState.run_id}/video`)}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
            </div>
          )}

          {macroTab === "video" && !activeRunState?.video_path && activeRunState?.browser_result?.gif_path && (
            <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
              <div className="bg-neutral-900 border-b border-neutral-800 p-4 flex items-center justify-between">
                <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                  <Play size={16} className="text-blue-400" /> Browser Validation
                </h3>
                <a
                  href={apiUrl(`/api/runs/${activeRunState.run_id}/gif`)}
                  download="browser-validation.gif"
                  className="flex items-center gap-1.5 text-xs text-neutral-400 hover:text-white bg-neutral-800 hover:bg-neutral-700 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <Download size={13} /> Download GIF
                </a>
              </div>
              <div className="p-4 flex justify-center bg-black">
                <img
                  src={apiUrl(`/api/runs/${activeRunState.run_id}/gif`)}
                  alt="Browser validation recording"
                  className="max-w-full max-h-[400px] rounded border border-neutral-800"
                />
              </div>
            </div>
          )}

          {macroTab === "trace" && !activeRunState && !runError && !loadingRunState && issue.run_id && (
            <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
              <div className="mb-2">
                No logs found for run{" "}
                <code className="bg-neutral-800 px-1 py-0.5 rounded text-xs">{issue.run_id}</code>
              </div>
              <div className="text-xs">Check the server terminal for error details.</div>
            </div>
          )}

          {macroTab === "trace" && !activeRunState && !runError && !loadingRunState && !issue.run_id && issue.status !== "In Progress" && (
            <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
              Agent has not started yet. Drag to "In Progress" to begin execution.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
