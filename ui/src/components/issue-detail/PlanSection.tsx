import React, { useState } from "react";
import { Check, Circle, Lightbulb, MessageSquare, Pencil, RefreshCw } from "lucide-react";
import type { Issue, PlanResult } from "../../types";
import { apiUrl } from "../../utils";

export function PlanSection({
  issue,
  planningIssues,
  editingPlan,
  setEditingPlan,
  planDraft,
  setPlanDraft,
  // onRegeneratePlan, onStartExecution, isActionPending are handled by parent
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  onRegeneratePlan: _onRegeneratePlan,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  onStartExecution: _onStartExecution,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  isActionPending: _isActionPending,
}: {
  issue: Issue;
  planningIssues: Set<number>;
  editingPlan: boolean;
  setEditingPlan: (v: boolean) => void;
  planDraft: PlanResult | null;
  setPlanDraft: React.Dispatch<React.SetStateAction<PlanResult | null>>;
  onRegeneratePlan?: () => void;
  onStartExecution?: () => void;
  isActionPending?: boolean;
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
            <button
              onClick={savePlan}
              className="text-xs text-green-400 hover:text-green-300 flex items-center gap-1"
            >
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
            <div className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">
              Approach
            </div>
            {editingPlan ? (
              <textarea
                className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-neutral-200 focus:outline-none focus:border-violet-500 resize-none"
                rows={3}
                value={planDraft?.approach ?? ""}
                onChange={(e) =>
                  setPlanDraft((p) => (p ? { ...p, approach: e.target.value } : p))
                }
              />
            ) : (
              <p className="text-sm text-neutral-300 leading-relaxed">{displayPlan.approach}</p>
            )}
          </div>

          {displayPlan.phases?.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-2">
                Phases
              </div>
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
                    <span className="text-neutral-600 shrink-0 mt-0.5">
                      <Circle size={12} className="text-neutral-500" />
                    </span>
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

      {storedPlan && !editingPlan && (
        <div className="border-t border-neutral-800/50 px-5 py-4 space-y-3">
          <div className="text-xs font-semibold text-neutral-500 uppercase tracking-wider flex items-center gap-2">
            <MessageSquare size={12} /> Feedback
          </div>
          {comments.length > 0 && (
            <div className="space-y-1.5">
              {comments.map((c, ci) => (
                <div key={ci} className="flex items-start gap-2 text-xs">
                  <span className="text-neutral-600 shrink-0 mt-0.5">
                    <MessageSquare size={12} className="text-neutral-500" />
                  </span>
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
              {isPlanning ? (
                <RefreshCw size={11} className="animate-spin" />
              ) : (
                <Lightbulb size={11} />
              )}
              Refine Plan
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
