import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  FileText,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Settings,
  Video,
  X,
} from "lucide-react";
import { apiUrl } from "../utils";
import type { Issue, Project, PlanResult, RunState, IterationResult, BrowserAssertion } from "../types";
import { StatusBadge, detectLimitHint } from "./issue-detail/helpers";
import { PlanSection } from "./issue-detail/PlanSection";
import { IterationContent } from "./issue-detail/PhaseSection";

interface IssueDetailModalProps {
  issue: Issue;
  projects: Project[];
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
  projects,
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
  const [isActionPending, setIsActionPending] = useState(false);
  const activeProject = projects.find((p) => p.id === issue.project_id);

  const handlePause = async () => {
    setIsActionPending(true);
    try {
      await fetch(apiUrl(`/api/issues/${issue.id}/pause`), { method: "POST" });
    } finally {
      setIsActionPending(false);
    }
  };

  const handleResume = async () => {
    setIsActionPending(true);
    try {
      await fetch(apiUrl(`/api/issues/${issue.id}/resume`), { method: "POST" });
    } finally {
      setIsActionPending(false);
    }
  };

  const handleRestart = async () => {
    if (!confirm("Are you sure you want to restart this task and run all iterations from scratch?")) return;
    setIsActionPending(true);
    try {
      await fetch(apiUrl(`/api/issues/${issue.id}/restart`), { method: "POST" });
    } finally {
      setIsActionPending(false);
    }
  };

  const handleRegeneratePlan = async () => {
    if (!confirm("Are you sure you want to regenerate the implementation plan? This will clear any comments you've added.")) return;
    setIsActionPending(true);
    try {
      await fetch(apiUrl(`/api/issues/${issue.id}/plan/regenerate`), { method: "POST" });
    } finally {
      setIsActionPending(false);
    }
  };

  const handleStartExecution = async () => {
    setIsActionPending(true);
    try {
      await fetch(apiUrl(`/api/issues/${issue.id}`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "In Progress" }),
      });
    } finally {
      setIsActionPending(false);
    }
  };

  const handleVerify = async () => {
    setIsActionPending(true);
    try {
      await fetch(apiUrl(`/api/issues/${issue.id}/verify`), { method: "POST" });
      // Don't clear isActionPending here — let the WS event take over so there's
      // no flash between the POST returning and verification_running becoming true.
    } catch {
      setIsActionPending(false);
    }
  };

  useEffect(() => {
    const el = activityLogRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  const activeRunState = liveRunStates[issue.id] || runState;
  const runError = runErrors[issue.id];
  const isLive = issue.status === "In Progress" && !!liveRunStates[issue.id];
  const isVerifying = isActionPending || !!activeRunState?.verification_running;
  const missingAuth =
    !!activeProject &&
    !activeProject.test_user &&
    !activeProject.test_password &&
    !activeProject.cookie_file;

  // Once the server confirms verification is running (or it finishes), release the
  // local pending flag — isVerifying stays true via verification_running anyway.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (activeRunState?.verification_running != null) {
      setIsActionPending(false);
    }
  }, [activeRunState?.verification_running, activeRunState?.browser_result]);

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
        <div className="absolute top-4 right-14 flex items-center gap-2 z-10 bg-neutral-900 border border-neutral-800 p-1 rounded-lg">
          {issue.status === "In Progress" && activeRunState?.status !== "paused" && (
            <button
              onClick={handlePause}
              disabled={isActionPending}
              className="flex items-center gap-1.5 text-xs text-yellow-400 bg-yellow-400/10 hover:bg-yellow-400/20 border border-yellow-500/20 px-2.5 py-1 rounded-md font-medium transition-colors"
              title="Pause Agent between iterations"
            >
              <Pause size={12} /> Pause
            </button>
          )}

          {((issue.status === "In Progress" && activeRunState?.status === "paused") ||
            (issue.status === "Failed" && issue.run_id)) && (
            <button
              onClick={handleResume}
              disabled={isActionPending}
              className="flex items-center gap-1.5 text-xs text-green-400 bg-green-400/10 hover:bg-green-400/20 border border-green-500/20 px-2.5 py-1 rounded-md font-medium transition-colors"
              title="Resume Agent execution from last checkpoint"
            >
              <Play size={12} /> Resume
            </button>
          )}

          {(issue.status === "Failed" || issue.status === "Done") && (
            <button
              onClick={handleRestart}
              disabled={isActionPending}
              className="flex items-center gap-1.5 text-xs text-blue-400 bg-blue-400/10 hover:bg-blue-400/20 border border-blue-500/20 px-2.5 py-1 rounded-md font-medium transition-colors"
              title="Restart Agent execution from scratch"
            >
              <RotateCcw size={12} /> Restart
            </button>
          )}

          {issue.status === "Backlog" && issue.plan_json && (
            <>
              <button
                onClick={handleRegeneratePlan}
                disabled={isActionPending || planningIssues.has(issue.id)}
                className="flex items-center gap-1.5 text-xs text-neutral-400 hover:text-neutral-200 bg-neutral-800 border border-neutral-700 px-2.5 py-1 rounded-md font-medium transition-colors"
                title="Regenerate plan from scratch"
              >
                <RotateCcw size={12} /> Regenerate Plan
              </button>
              <button
                onClick={handleStartExecution}
                disabled={isActionPending}
                className="flex items-center gap-1.5 text-xs text-violet-400 bg-violet-400/10 hover:bg-violet-400/20 border border-violet-500/20 px-2.5 py-1 rounded-md font-medium transition-colors"
                title="Approve plan and start execution"
              >
                <Play size={12} /> Run Agent
              </button>
            </>
          )}

          {issue.status === "Backlog" && !issue.plan_json && (
            <button
              onClick={handleRegeneratePlan}
              disabled={isActionPending || planningIssues.has(issue.id)}
              className="flex items-center gap-1.5 text-xs text-violet-400 bg-violet-400/10 hover:bg-violet-400/20 border border-violet-500/20 px-2.5 py-1 rounded-md font-medium transition-colors"
              title="Start planning"
            >
              <RefreshCw size={12} className={planningIssues.has(issue.id) ? "animate-spin" : ""} /> Generate Plan
            </button>
          )}
        </div>

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
          {activeRunState && (
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
              onRegeneratePlan={handleRegeneratePlan}
              onStartExecution={handleStartExecution}
              isActionPending={isActionPending}
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
                        {activeRunState?.status === "paused" ? (
                          <>
                            <Pause size={20} className="text-yellow-400" />
                            <span>Agent is paused. You can resume or restart execution using the controls at the top right.</span>
                          </>
                        ) : (
                          <>
                            <RefreshCw size={20} className="animate-spin text-blue-500" />
                            <span>Agent initializing... decomposing goal into subtasks...</span>
                          </>
                        )}
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

          {macroTab === "video" && activeRunState && (
            <div className="space-y-4">
              <div className="flex justify-between items-center bg-neutral-950/40 p-4 border border-neutral-800 rounded-xl">
                <div>
                  <h4 className="text-sm font-medium text-neutral-200">On-Demand Verification</h4>
                  <p className="text-xs text-neutral-500">Run or retry browser automation and screenshot validation for this task.</p>
                </div>
                <button
                  onClick={handleVerify}
                  disabled={isVerifying || (issue.status !== "Done" && issue.status !== "Failed")}
                  className="flex items-center gap-1.5 text-xs text-green-400 bg-green-400/10 hover:bg-green-400/20 border border-green-500/20 px-3 py-1.5 rounded-lg font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  title={issue.status !== "Done" && issue.status !== "Failed" ? "Cannot run verification until agent execution is complete" : "Run browser verification / validation"}
                >
                  <RefreshCw size={12} className={isVerifying ? "animate-spin" : ""} />
                  {isVerifying ? "Verifying..." : "Run Verification"}
                </button>
              </div>

              {/* Auth warning — show when no credentials are configured */}
              {missingAuth && (
                <div className="flex items-start gap-2 text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded-lg px-3 py-2.5">
                  <AlertCircle size={14} className="shrink-0 mt-0.5" />
                  <span>
                    No test credentials configured. If your app requires login, add{" "}
                    <span className="font-medium">test_user</span> and{" "}
                    <span className="font-medium">test_password</span> in project settings before running verification.
                  </span>
                </div>
              )}

              {/* Case 0: verification started but dev server still booting (no result yet) */}
              {activeRunState.verification_running && !activeRunState.browser_result && (
                <div className="flex items-center gap-3 border border-blue-500/20 bg-blue-500/5 rounded-xl px-4 py-3">
                  <RefreshCw size={16} className="animate-spin text-blue-400 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-blue-300">Starting verification…</p>
                    <p className="text-xs text-neutral-400 mt-0.5">Booting dev server and preparing browser tests. Check the activity log for details.</p>
                  </div>
                </div>
              )}

              {/* Case 1: run still in progress or old run without detection data */}
              {!activeRunState.verification_running &&
               activeRunState.ui_changes_detected == null &&
               !activeRunState.browser_result && !activeRunState.video_path && (
                <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
                  Browser validation runs after the task completes.
                </div>
              )}

              {/* Case 2: no UI changes detected */}
              {!activeRunState.verification_running && activeRunState.ui_changes_detected === false && (
                <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
                  No UI or frontend files were modified in this run.
                </div>
              )}

              {/* Case 3: UI changes detected but no browser validation ran */}
              {!activeRunState.verification_running &&
               activeRunState.ui_changes_detected === true &&
               !activeRunState.browser_result && !activeRunState.video_path && (
                <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
                  <p className="mb-2">UI changes detected.</p>
                  <p className="text-xs">
                    Set{" "}
                    <code className="bg-neutral-800 px-1 py-0.5 rounded">DEFAULT_APP_URL</code>
                    {" "}in your{" "}
                    <code className="bg-neutral-800 px-1 py-0.5 rounded">.env</code>
                    {" "}to enable automatic browser validation.
                  </p>
                </div>
              )}

              {/* Case 4: browser validation ran — full results */}
              {(activeRunState.browser_result || activeRunState.video_path) && (() => {
                const br = activeRunState.browser_result;
                const isRunning = !!activeRunState.verification_running || (br && (br.summary?.startsWith("Testing…") || br.summary?.startsWith("Initializing")));
                return (
                  <>
                    {/* Summary header */}
                    {br && (
                      <div className={`border rounded-xl p-4 space-y-2 ${isRunning ? "bg-blue-500/5 border-blue-500/20" : br.passed ? "bg-green-500/5 border-green-500/20" : "bg-neutral-950 border-neutral-800"}`}>
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm text-neutral-400 mb-1">Browser Test</p>
                            <p className="text-sm text-neutral-200">{br.summary}</p>
                          </div>
                          <div className="flex items-center gap-3 shrink-0 ml-4">
                            {!isRunning && (
                              <span className="text-xs text-neutral-500">
                                {Math.round(br.score * 100)}%
                              </span>
                            )}
                            <span className="text-xs text-neutral-600">
                              {br.steps} steps
                            </span>
                            {isRunning ? (
                              <span className="flex items-center gap-1 text-xs text-blue-400 bg-blue-400/10 border border-blue-400/20 px-2 py-1 rounded-full">
                                <RefreshCw size={12} className="animate-spin" /> Running
                              </span>
                            ) : br.passed ? (
                              <span className="flex items-center gap-1 text-xs text-green-400 bg-green-400/10 border border-green-400/20 px-2 py-1 rounded-full">
                                ✓ Passed
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-xs text-red-400 bg-red-400/10 border border-red-400/20 px-2 py-1 rounded-full">
                                <AlertCircle size={12} /> Failed
                              </span>
                            )}
                          </div>
                        </div>
                        {!isRunning && br.error && (
                          <p className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded-lg px-3 py-2">
                            {br.error}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Assertions list */}
                    {((activeRunState.browser_result?.assertions?.length || 0) > 0 || (activeRunState.browser_result?.planned_assertions?.length || 0) > 0) && (
                      (() => {
                        const planned = activeRunState.browser_result?.planned_assertions || [];
                        const executed = activeRunState.browser_result?.assertions || [];

                        const items = planned.map((pDesc: string) => {
                          const match = executed.find(
                            (e: BrowserAssertion) =>
                              e.description.toLowerCase().includes(pDesc.toLowerCase()) ||
                              pDesc.toLowerCase().includes(e.description.toLowerCase())
                          );
                          return {
                            description: pDesc,
                            status: match ? (match.passed ? "passed" : "failed") : "pending",
                            selector: match?.selector || null,
                            actual: match?.actual || null,
                          };
                        });

                        const unmatchedExecuted = executed.filter(
                          (e: BrowserAssertion) =>
                            !planned.some(
                              (pDesc: string) =>
                                e.description.toLowerCase().includes(pDesc.toLowerCase()) ||
                                pDesc.toLowerCase().includes(e.description.toLowerCase())
                            )
                        );

                        const displayItems = [
                          ...items,
                          ...unmatchedExecuted.map((e: BrowserAssertion) => ({
                            description: e.description,
                            status: e.passed ? ("passed" as const) : ("failed" as const),
                            selector: e.selector,
                            actual: e.actual,
                          })),
                        ];

                        const totalPassed = displayItems.filter((item) => item.status === "passed").length;
                        const totalCount = displayItems.length;

                        return (
                          <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                            <div className="bg-neutral-900 border-b border-neutral-800 p-4">
                              <h3 className="text-sm font-medium text-neutral-300">
                                Assertions ({totalPassed}/{totalCount} passed)
                              </h3>
                            </div>
                            <div className="divide-y divide-neutral-800">
                              {displayItems.map((item, i) => (
                                <div key={i} className="flex items-start gap-3 p-3">
                                  {item.status === "passed" && (
                                    <span className="text-green-400 mt-0.5 shrink-0">✓</span>
                                  )}
                                  {item.status === "failed" && (
                                    <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
                                  )}
                                  {item.status === "pending" && (
                                    <span className="text-neutral-500 mt-0.5 shrink-0">○</span>
                                  )}
                                  <div className="min-w-0">
                                    <p className={`text-sm ${item.status === "pending" ? "text-neutral-500" : "text-neutral-200"}`}>
                                      {item.description}
                                    </p>
                                    {item.selector && (
                                      <p className="text-xs text-neutral-500 font-mono mt-0.5">{item.selector}</p>
                                    )}
                                    {item.status === "failed" && item.actual && (
                                      <p className="text-xs text-red-400 mt-0.5">actual: {item.actual}</p>
                                    )}
                                    {item.status === "pending" && (
                                      <p className="text-xs text-neutral-600 italic mt-0.5">pending verification...</p>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })()
                    )}

                    {/* Video player */}
                    {activeRunState.video_path && (
                      <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                        <div className="bg-neutral-900 border-b border-neutral-800 p-4">
                          <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                            <Play size={16} className="text-blue-400" /> Video Recording
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

                    {/* Screenshots strip */}
                    {activeRunState.browser_result?.screenshots?.length > 0 && (
                      <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                        <div className="bg-neutral-900 border-b border-neutral-800 p-4">
                          <h3 className="text-sm font-medium text-neutral-300">
                            Screenshots ({activeRunState.browser_result.screenshots.length})
                          </h3>
                        </div>
                        <div className="p-4 flex gap-3 overflow-x-auto">
                          {activeRunState.browser_result.screenshots.map((absPath: string, i: number) => {
                            const filename = absPath.split(/[\\/]/).pop() ?? absPath;
                            return (
                              <img
                                key={i}
                                src={apiUrl(`/api/runs/${activeRunState.run_id}/screenshots/${filename}`)}
                                alt={filename}
                                className="h-32 w-auto rounded border border-neutral-700 shrink-0 object-cover cursor-pointer hover:border-neutral-500 transition-colors"
                                title={filename}
                                onClick={() => window.open(
                                  apiUrl(`/api/runs/${activeRunState.run_id}/screenshots/${filename}`),
                                  "_blank"
                                )}
                              />
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                );
              })()}
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
