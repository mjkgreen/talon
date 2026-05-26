import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  Download,
  FileText,
  Play,
  RefreshCw,
  Settings,
  Video,
  X,
} from "lucide-react";
import { apiUrl } from "../utils";
import type { Issue, PlanResult, RunState, IterationResult } from "../types";
import { StatusBadge, detectLimitHint } from "./issue-detail/helpers";
import { PlanSection } from "./issue-detail/PlanSection";
import { IterationContent } from "./issue-detail/PhaseSection";

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
    issue.status === "Queued" || issue.status === "Backlog" ? "plan" : "trace",
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
      if (num > maxLogIteration) maxLogIteration = num;
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

        {/* Macro tab bar */}
        <div className="flex border-b border-neutral-800 mb-6 shrink-0 gap-6">
          <button
            onClick={() => setMacroTab("plan")}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              macroTab === "plan"
                ? "border-violet-500 text-white"
                : "border-transparent text-neutral-500 hover:text-neutral-300"
            }`}
          >
            Plan
          </button>
          <button
            onClick={() => setMacroTab("trace")}
            className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
              macroTab === "trace"
                ? "border-blue-500 text-white"
                : "border-transparent text-neutral-500 hover:text-neutral-300"
            }`}
          >
            Execution Trace
          </button>
          {(activeRunState?.video_path || activeRunState?.browser_result?.gif_path) && (
            <button
              onClick={() => setMacroTab("video")}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
                macroTab === "video"
                  ? "border-green-500 text-white"
                  : "border-transparent text-neutral-500 hover:text-neutral-300"
              }`}
            >
              <Video size={14} /> Verification
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto pr-2 space-y-6">
          {issue.description && (
            <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl p-5">
              <h3 className="text-sm font-medium text-neutral-400 mb-3 uppercase tracking-wider">
                Description
              </h3>
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
                      <span className="inline-flex items-center gap-1">
                        <Settings size={11} /> Settings → Limits
                      </span>{" "}
                      and re-run.
                    </div>
                  </div>
                </div>
              )}

              {(runError || activeRunState?.error) &&
                (() => {
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
                          const cachePct =
                            inTok > 0 ? Math.round((cacheRead / inTok) * 100) : 0;
                          if (totalTok === 0) return null;
                          return (
                            <div className="flex items-center gap-2 text-xs text-neutral-500 font-mono">
                              <span title="Total tokens">
                                {totalTok >= 1000
                                  ? `${(totalTok / 1000).toFixed(1)}k`
                                  : totalTok}{" "}
                                tok
                              </span>
                              {cachePct > 0 && (
                                <span title="Cache hit rate" className="text-green-600">
                                  {cachePct}% cached
                                </span>
                              )}
                              {cost > 0 && (
                                <span title="Estimated cost" className="text-yellow-600">
                                  ${cost.toFixed(4)}
                                </span>
                              )}
                            </div>
                          );
                        })()}
                        <span className="text-xs text-neutral-500 font-mono">
                          Run: {activeRunState.run_id}
                        </span>
                      </div>
                    </div>

                    {/* Iteration tabs */}
                    {tabCount > 0 && (
                      <div className="flex border-b border-neutral-800 bg-neutral-900/30 overflow-x-auto">
                        {tabIndices.map((idx: number) => {
                          const review = activeRunState.review_results?.[idx];
                          const isActiveTab =
                            activeTraceTab === idx || (activeTraceTab === "plan" && idx === 0);
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
                                className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                  isPassing
                                    ? "bg-green-400"
                                    : isFailing
                                      ? "bg-amber-400"
                                      : isRunning
                                        ? "bg-blue-400 animate-pulse"
                                        : "bg-neutral-600"
                                }`}
                              />
                              Iteration {idx + 1}
                              {isRunning && (
                                <RefreshCw size={10} className="animate-spin text-neutral-500" />
                              )}
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

                    {tabCount > 0 &&
                      (() => {
                        const iterIdx =
                          typeof activeTraceTab === "number" ? activeTraceTab : 0;
                        const clampedTab = Math.min(iterIdx, tabCount - 1);
                        const currentIteration: IterationResult = iterations[clampedTab] || {
                          subtasks: [],
                          subtask_results: [],
                          aggregated_output: "",
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

          {/* Video verification panel */}
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

          {/* GIF-only panel (no video) */}
          {macroTab === "video" &&
            !activeRunState?.video_path &&
            activeRunState?.browser_result?.gif_path && (
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

          {macroTab === "trace" &&
            !activeRunState &&
            !runError &&
            !loadingRunState &&
            issue.run_id && (
              <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
                <div className="mb-2">
                  No logs found for run{" "}
                  <code className="bg-neutral-800 px-1 py-0.5 rounded text-xs">{issue.run_id}</code>
                </div>
                <div className="text-xs">Check the server terminal for error details.</div>
              </div>
            )}

          {macroTab === "trace" &&
            !activeRunState &&
            !runError &&
            !loadingRunState &&
            !issue.run_id &&
            issue.status !== "In Progress" && (
              <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
                Agent has not started yet. Drag to "In Progress" to begin execution.
              </div>
            )}
        </div>
      </div>
    </div>
  );
}
