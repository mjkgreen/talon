import React from "react";
import { Check, ChevronDown, ChevronRight, Folder, RefreshCw, Settings as SettingsIcon, X } from "lucide-react";
import { GithubLogo, API_KEY_PROVIDERS, MODEL_ROLES } from "../constants";
import type { Project } from "../types";

interface SettingsModalProps {
  settingsTab: "ai" | "model" | "workspace" | "limits";
  setSettingsTab: (v: "ai" | "model" | "workspace" | "limits") => void;
  keyDrafts: Record<string, string>;
  setKeyDrafts: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  modelDrafts: Record<string, string>;
  setModelDrafts: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  maxIterations: string;
  setMaxIterations: (v: string) => void;
  maxTokens: string;
  setMaxTokens: (v: string) => void;
  reviewerMaxToolTurns: string;
  setReviewerMaxToolTurns: (v: string) => void;
  maxConcurrentRuns: string;
  setMaxConcurrentRuns: (v: string) => void;
  advancedModelOpen: boolean;
  setAdvancedModelOpen: React.Dispatch<React.SetStateAction<boolean>>;
  savingSettings: boolean;
  hasLlm: boolean;
  activeProvider: string | null;
  activeProject: Project | undefined;
  editLocalDirectly: boolean;
  pushOnPass: boolean;
  onSave: () => void;
  onClose: () => void;
  onConfigureWorkspace: () => void;
  onToggleEditLocal: (v: boolean) => void;
  onTogglePushOnPass: (v: boolean) => void;
}

const TAB_LABELS: Record<string, string> = {
  ai: "AI Provider",
  model: "Model",
  workspace: "Workspace",
  limits: "Limits",
};

function Toggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`relative flex-shrink-0 inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${on ? "bg-blue-600" : "bg-neutral-700"}`}
      aria-pressed={on}
    >
      <span
        className={`inline-block h-3 w-3 rounded-full bg-white shadow transition-transform ${on ? "translate-x-5" : "translate-x-1"}`}
      />
    </button>
  );
}

export function SettingsModal({
  settingsTab,
  setSettingsTab,
  keyDrafts,
  setKeyDrafts,
  modelDrafts,
  setModelDrafts,
  maxIterations,
  setMaxIterations,
  maxTokens,
  setMaxTokens,
  reviewerMaxToolTurns,
  setReviewerMaxToolTurns,
  maxConcurrentRuns,
  setMaxConcurrentRuns,
  advancedModelOpen,
  setAdvancedModelOpen,
  savingSettings,
  hasLlm,
  activeProvider,
  activeProject,
  editLocalDirectly,
  pushOnPass,
  onSave,
  onClose,
  onConfigureWorkspace,
  onToggleEditLocal,
  onTogglePushOnPass,
}: SettingsModalProps) {
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-lg shadow-2xl flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between p-6 border-b border-neutral-800">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <SettingsIcon size={18} className="text-neutral-400" /> Settings
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 text-neutral-500 hover:text-white bg-neutral-800 hover:bg-neutral-700 rounded-lg transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex border-b border-neutral-800">
          {(["ai", "model", "workspace", "limits"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setSettingsTab(tab)}
              className={`px-5 py-3 text-sm font-medium transition-colors capitalize ${
                settingsTab === tab
                  ? "border-b-2 border-blue-500 text-white"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {settingsTab === "ai" && (
            <div className="space-y-4">
              <p className="text-xs text-neutral-500">
                Add at least one API key to enable agent runs. Existing keys are shown masked.
              </p>
              {API_KEY_PROVIDERS.map(({ field, label, placeholder }) => (
                <div key={field}>
                  <label className="block text-sm font-medium text-neutral-300 mb-1">{label}</label>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={keyDrafts[field] || ""}
                      onChange={(e) => setKeyDrafts((prev) => ({ ...prev, [field]: e.target.value }))}
                      placeholder={keyDrafts[field]?.startsWith("***") ? keyDrafts[field] : placeholder}
                      className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                    {keyDrafts[field] && (
                      <button
                        onClick={() => setKeyDrafts((prev) => ({ ...prev, [field]: "" }))}
                        className="px-3 py-2 text-xs text-neutral-500 hover:text-red-400 bg-neutral-800 border border-neutral-700 rounded-lg transition-colors"
                        title="Clear key"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {hasLlm && activeProvider && (
                <div className="text-xs text-green-400 bg-green-400/10 border border-green-400/20 rounded-lg p-3 flex items-center gap-2">
                  <Check size={12} />
                  Active provider: <strong>{activeProvider}</strong>
                </div>
              )}
            </div>
          )}

          {settingsTab === "model" && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Global model</label>
                <input
                  type="text"
                  value={modelDrafts.agent_model || ""}
                  onChange={(e) => setModelDrafts((prev) => ({ ...prev, agent_model: e.target.value }))}
                  placeholder="Leave blank for Auto (recommended)"
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
                <p className="text-xs text-neutral-600 mt-1">
                  Example: <code>anthropic/claude-opus-4-7</code> or <code>gemini/gemini-flash-latest</code>
                </p>
              </div>

              <button
                onClick={() => setAdvancedModelOpen((v) => !v)}
                className="flex items-center gap-2 text-sm text-neutral-400 hover:text-neutral-200 transition-colors"
              >
                {advancedModelOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Advanced model settings (per-role)
              </button>

              {advancedModelOpen && (
                <div className="space-y-3 pl-4 border-l border-neutral-800">
                  <p className="text-xs text-neutral-500">
                    Override the model for each agent role. Leave blank to use the global model (or Auto).
                  </p>
                  {MODEL_ROLES.map(({ field, label, hint }) => (
                    <div key={field}>
                      <label className="block text-xs font-medium text-neutral-400 mb-1">
                        {label} <span className="text-neutral-600">— {hint}</span>
                      </label>
                      <input
                        type="text"
                        value={modelDrafts[field] || ""}
                        onChange={(e) => setModelDrafts((prev) => ({ ...prev, [field]: e.target.value }))}
                        placeholder="blank = use global / Auto"
                        className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                      />
                    </div>
                  ))}
                  <p className="text-xs text-neutral-600">Per-workspace model overrides coming in v2.</p>
                </div>
              )}
            </div>
          )}

          {settingsTab === "workspace" && (
            <div className="space-y-4">
              {activeProject ? (
                <>
                  <div className="bg-neutral-800/50 border border-neutral-700 rounded-xl p-4">
                    <div className="text-xs text-neutral-500 mb-1">Current project</div>
                    <div className="font-medium text-neutral-200">{activeProject.name}</div>
                    <div className="mt-3 space-y-1 text-sm">
                      <div className="flex items-center gap-2 text-neutral-400">
                        <span className="text-neutral-600">Mode:</span>
                        <span className="capitalize">{activeProject.workspace_mode || "none"}</span>
                      </div>
                      {activeProject.workspace_mode === "github" && activeProject.selected_repo && (
                        <div className="flex items-center gap-2 text-neutral-400">
                          <GithubLogo size={13} />
                          <span>{activeProject.selected_repo}</span>
                        </div>
                      )}
                      {activeProject.workspace_mode === "local" && activeProject.local_path && (
                        <div className="flex items-center gap-2 text-neutral-400">
                          <Folder size={13} />
                          <span className="font-mono text-xs">{activeProject.local_path}</span>
                        </div>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={onConfigureWorkspace}
                    className="w-full py-2.5 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-lg text-sm text-neutral-300 transition-colors"
                  >
                    Configure workspace…
                  </button>
                  <p className="text-xs text-neutral-600">Changes the workspace for the current project tab.</p>
                </>
              ) : (
                <p className="text-sm text-neutral-500">No active project selected.</p>
              )}

              <div className="space-y-3 pt-2 border-t border-neutral-800">
                {activeProject?.workspace_mode === "local" && (
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-sm font-medium text-neutral-300">Edit local files directly</div>
                      <div className="text-xs text-neutral-500 mt-0.5">
                        Agents edit the real files on disk — no isolated copy or worktree
                      </div>
                    </div>
                    <Toggle on={editLocalDirectly} onToggle={() => onToggleEditLocal(!editLocalDirectly)} />
                  </div>
                )}
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-neutral-300">Push changes & open PR on pass</div>
                    <div className="text-xs text-neutral-500 mt-0.5">
                      Commit, push branch, and create a GitHub PR when a run succeeds
                    </div>
                  </div>
                  <Toggle on={pushOnPass} onToggle={() => onTogglePushOnPass(!pushOnPass)} />
                </div>
              </div>
            </div>
          )}

          {settingsTab === "limits" && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Max iterations</label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
                <p className="text-xs text-neutral-600 mt-1">
                  How many executor→reviewer→refiner cycles before giving up (default: 5)
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Max tokens per agent call</label>
                <input
                  type="number"
                  min={1024}
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(e.target.value)}
                  placeholder="Default (model limit)"
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Reviewer max tool turns</label>
                <input
                  type="number"
                  min={10}
                  max={200}
                  value={reviewerMaxToolTurns}
                  onChange={(e) => setReviewerMaxToolTurns(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
                <p className="text-xs text-neutral-600 mt-1">
                  How many file reads / commands the reviewer can run before outputting its verdict (default: 50)
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Max concurrent runs</label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maxConcurrentRuns}
                  onChange={(e) => setMaxConcurrentRuns(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
                <p className="text-xs text-neutral-600 mt-1">
                  How many issues can run simultaneously. Paused issues do not count. Takes effect on restart (default: 3)
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="p-6 border-t border-neutral-800 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm text-neutral-400 hover:text-white">
            Cancel
          </button>
          {settingsTab !== "workspace" && (
            <button
              onClick={onSave}
              disabled={savingSettings}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            >
              {savingSettings ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
              Save settings
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
