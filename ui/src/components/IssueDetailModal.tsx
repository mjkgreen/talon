import React, { useEffect, useRef } from "react";
import {
  Activity,
  AlertCircle,
  Check,
  CheckCircle2,
  FileText,
  Lightbulb,
  Pencil,
  Play,
  RefreshCw,
  X,
} from "lucide-react";
import { apiUrl } from "../utils";
import type { Issue, PlanPhase, PlanResult } from "../types";

interface IssueDetailModalProps {
  issue: Issue;
  liveRunStates: Record<number, any>;
  runState: any;
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

function LogLines({ lines, scrollRef }: { lines: string[]; scrollRef?: React.RefObject<HTMLDivElement> }) {
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
        {!isPlanning && storedPlan && !editingPlan && (
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
                    <span className="text-neutral-600 shrink-0 mt-0.5">○</span>
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
    </div>
  );
}

function PlanTabContent({
  plan,
  totalIterations,
  isLive,
  reviewResults,
}: {
  plan: PlanResult;
  totalIterations: number;
  isLive: boolean;
  reviewResults: any[];
}) {
  const anyPassed = !!(reviewResults?.some((r: any) => r.verdict === "pass"));
  return (
    <div className="p-4 space-y-4">
      <div>
        <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-2">Approach</div>
        <p className="text-sm text-neutral-300 leading-relaxed">{plan.approach}</p>
      </div>
      {plan.constraints?.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-2">Constraints</div>
          <ul className="space-y-1">
            {plan.constraints.map((c: string, ci: number) => (
              <li key={ci} className="text-xs text-neutral-400 flex items-start gap-2">
                <span className="text-neutral-600 shrink-0 mt-0.5">—</span>
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
      {plan.phases?.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-2">Phases</div>
          <div className="space-y-2">
            {plan.phases.map((ph: PlanPhase, pi: number) => {
              const done = pi < totalIterations;
              const active = pi === totalIterations - 1 && isLive;
              return (
                <div key={pi} className="flex items-start gap-2 text-xs">
                  <span
                    className={`mt-0.5 shrink-0 font-mono ${done ? "text-green-400" : active ? "text-blue-400" : "text-neutral-600"}`}
                  >
                    {done ? "✓" : active ? "→" : "○"}
                  </span>
                  <div>
                    <span
                      className={
                        done ? "text-neutral-400 line-through" : active ? "text-white font-medium" : "text-neutral-500"
                      }
                    >
                      {ph.name}
                    </span>
                    <span className="text-neutral-600 ml-2">{ph.description}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
      {plan.success_criteria?.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-2">Success Criteria</div>
          <div className="space-y-1.5">
            {plan.success_criteria.map((sc: string, si: number) => (
              <div key={si} className="flex items-start gap-2 text-xs">
                <span className={`shrink-0 mt-0.5 ${anyPassed ? "text-green-400" : "text-neutral-600"}`}>
                  {anyPassed ? "✓" : "○"}
                </span>
                <span className={anyPassed ? "text-neutral-400" : "text-neutral-500"}>{sc}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function IterationContent({
  iteration,
  review,
  refinement,
  isLive,
  isLatest,
  logs,
}: {
  iteration: any;
  review: any;
  refinement: any;
  isLive: boolean;
  isLatest: boolean;
  logs: string[];
}) {
  return (
    <div>
      {iteration.subtasks?.length > 0 && (
        <SubtaskList
          subtasks={iteration.subtasks}
          subtaskResults={iteration.subtask_results}
          isLive={isLive}
          isLatest={isLatest}
          logs={logs}
        />
      )}

      <div className="p-4 border-b border-neutral-800/50">
        <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">Output</div>
        <div className="bg-neutral-900 p-4 rounded border border-neutral-800/50 overflow-x-auto">
          <pre className="text-xs text-neutral-400 font-mono whitespace-pre-wrap">
            {iteration.aggregated_output || "No output yet"}
          </pre>
        </div>
        {isLive && isLatest && !review && (
          <div className="mt-3 flex items-center gap-2 text-xs text-neutral-500">
            <RefreshCw size={12} className="animate-spin" /> Waiting for reviewer...
          </div>
        )}
      </div>

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
                  <span className="shrink-0">✗</span> {issue}
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
                <span className="shrink-0 text-amber-500">→</span> {c}
              </div>
            ))}
          </div>
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
  subtasks: any[];
  subtaskResults: any[];
  isLive: boolean;
  isLatest: boolean;
  logs: string[];
}) {
  const doneCount = subtaskResults?.length ?? 0;
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
        {subtasks.map((st: any, si: number) => {
          const stResult = subtaskResults?.[si];
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

          const filesModified: string[] = stResult?.files_modified ?? [];

          return (
            <div key={si} className="flex items-start gap-2 text-xs">
              <span className={`mt-0.5 shrink-0 ${iconColor}`}>
                {isRunning ? (
                  <RefreshCw size={10} className="animate-spin" />
                ) : stResult?.success || liveDone ? (
                  "✓"
                ) : stResult ? (
                  "✗"
                ) : (
                  "○"
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
            </div>
          );
        })}
      </div>
    </div>
  );
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
  const logs = runLogs[issue.id] ?? [];

  useEffect(() => {
    const el = activityLogRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  const activeRunState = liveRunStates[issue.id] || runState;
  const runError = runErrors[issue.id];
  const isLive = issue.status === "In Progress" && !!liveRunStates[issue.id];
  const iterations: any[] = activeRunState?.executor_results ?? [];
  const totalIterations = iterations.length;
  const plan: PlanResult | null = activeRunState?.plan_result ?? null;

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

        <div className="flex-1 overflow-y-auto pr-2 space-y-6">
          {issue.description && (
            <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl p-5">
              <h3 className="text-sm font-medium text-neutral-400 mb-3 uppercase tracking-wider">Description</h3>
              <div className="text-neutral-300 text-sm whitespace-pre-wrap">{issue.description}</div>
            </div>
          )}

          {issue.status === "Backlog" && (
            <PlanSection
              issue={issue}
              planningIssues={planningIssues}
              editingPlan={editingPlan}
              setEditingPlan={setEditingPlan}
              planDraft={planDraft}
              setPlanDraft={setPlanDraft}
            />
          )}

          {(runError || activeRunState?.error) && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-sm text-red-400">
              <div className="font-medium mb-1">Agent error</div>
              <pre className="text-xs font-mono whitespace-pre-wrap text-red-300/80">
                {runError || activeRunState?.error}
              </pre>
            </div>
          )}

          {issue.status === "In Progress" && !activeRunState && !runError && (
            logs.length > 0 ? (
              <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                <div className="bg-neutral-900 border-b border-neutral-800 p-4 flex items-center gap-2">
                  <Activity size={16} className="text-blue-400" />
                  <span className="text-sm font-medium text-neutral-300">Execution Trace</span>
                  <span className="flex items-center gap-1 text-xs text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded-full ml-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                    Live
                  </span>
                </div>
                <LogLines lines={logs} scrollRef={activityLogRef} />
              </div>
            ) : (
              <div className="flex items-center gap-3 p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl text-blue-400 text-sm">
                <RefreshCw size={16} className="animate-spin shrink-0" />
                Agent is starting up — logs will appear here shortly...
              </div>
            )
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
                  <span className="text-xs text-neutral-500 font-mono">Run: {activeRunState.run_id}</span>
                </div>

                {logs.length > 0 && (
                  <div className="border-b border-neutral-800/50">
                    <LogLines lines={logs} scrollRef={activityLogRef} />
                  </div>
                )}

                {(plan || totalIterations > 0) && (
                  <div className="flex border-b border-neutral-800 bg-neutral-900/30 overflow-x-auto">
                    {plan && (
                      <button
                        onClick={() => setActiveTraceTab("plan")}
                        className={`flex items-center gap-2 px-4 py-3 text-xs font-medium whitespace-nowrap border-b-2 transition-colors ${
                          activeTraceTab === "plan"
                            ? "border-blue-500 text-white bg-neutral-800/50"
                            : "border-transparent text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/30"
                        }`}
                      >
                        <Lightbulb size={12} /> Plan
                      </button>
                    )}
                    {iterations.map((_: any, idx: number) => {
                      const review = activeRunState.review_results?.[idx];
                      const isActiveTab = activeTraceTab === idx;
                      const isPassing = review?.verdict === "pass";
                      const isFailing = review && review.verdict !== "pass";
                      const isRunning = isLive && idx === totalIterations - 1 && !review;
                      return (
                        <button
                          key={idx}
                          onClick={() => {
                            setActiveTraceTab(idx);
                            followLatestRef.current = idx === totalIterations - 1;
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

                {activeTraceTab === "plan" && plan && (
                  <PlanTabContent
                    plan={plan}
                    totalIterations={totalIterations}
                    isLive={isLive}
                    reviewResults={activeRunState.review_results ?? []}
                  />
                )}

                {activeTraceTab !== "plan" && totalIterations === 0 && (
                  <div className="p-8 text-center text-neutral-500 text-sm flex flex-col items-center gap-3">
                    {logs.length === 0 ? (
                      <>
                        <RefreshCw size={20} className="animate-spin text-blue-500" />
                        Agent initializing — decomposing goal into subtasks...
                      </>
                    ) : (
                      <span className="text-neutral-600 text-xs">Waiting for subtasks to complete…</span>
                    )}
                  </div>
                )}

                {!plan && totalIterations === 0 && (
                  <div className="p-8 text-center text-neutral-500 text-sm flex flex-col items-center gap-3">
                    <RefreshCw size={20} className="animate-spin text-blue-500" />
                    Agent initializing...
                  </div>
                )}

                {activeTraceTab !== "plan" && totalIterations > 0 && (() => {
                  const iterIdx = typeof activeTraceTab === "number" ? activeTraceTab : 0;
                  const clampedTab = Math.min(iterIdx, totalIterations - 1);
                  const currentIteration = iterations[clampedTab];
                  if (!currentIteration) return null;
                  return (
                    <IterationContent
                      iteration={currentIteration}
                      review={activeRunState.review_results?.[clampedTab]}
                      refinement={activeRunState.refinement_results?.[clampedTab]}
                      isLive={isLive}
                      isLatest={clampedTab === totalIterations - 1}
                      logs={logs}
                    />
                  );
                })()}
              </div>

              {activeRunState.video_path && (
                <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                  <div className="bg-neutral-900 border-b border-neutral-800 p-4">
                    <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                      <Play size={16} className="text-blue-400" /> Video Verification
                    </h3>
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
            </div>
          )}

          {!activeRunState && !runError && !loadingRunState && issue.run_id && (
            <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
              <div className="mb-2">
                No logs found for run{" "}
                <code className="bg-neutral-800 px-1 py-0.5 rounded text-xs">{issue.run_id}</code>
              </div>
              <div className="text-xs">Check the server terminal for error details.</div>
            </div>
          )}

          {!activeRunState && !runError && !loadingRunState && !issue.run_id && issue.status !== "In Progress" && (
            <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
              Agent has not started yet. Drag to "In Progress" to begin execution.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
