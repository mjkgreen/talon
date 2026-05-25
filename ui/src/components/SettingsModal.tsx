import React from "react";
import { Check, ChevronDown, ChevronRight, Folder, Plus, RefreshCw, Settings as SettingsIcon, Trash2, Upload, X } from "lucide-react";
import { GithubLogo, API_KEY_PROVIDERS, MODEL_ROLES } from "../constants";
import type { Project } from "../types";

export interface EnvVarRow {
  key: string;
  value: string;
}

interface SettingsModalProps {
  settingsTab: "ai" | "model" | "workspace" | "environment" | "limits";
  setSettingsTab: (v: "ai" | "model" | "workspace" | "environment" | "limits") => void;
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
  startCommand: string;
  setStartCommand: (v: string) => void;
  envVarRows: EnvVarRow[];
  setEnvVarRows: React.Dispatch<React.SetStateAction<EnvVarRow[]>>;
  envContent: string;
  setEnvContent: (v: string) => void;
  cookieFile: string;
  setCookieFile: (v: string) => void;
  testUser: string;
  setTestUser: (v: string) => void;
  testPassword: string;
  setTestPassword: (v: string) => void;
  onSave: () => void;
  onSaveEnvironment: () => void;
  onClose: () => void;
  onConfigureWorkspace: () => void;
  onToggleEditLocal: (v: boolean) => void;
  onTogglePushOnPass: (v: boolean) => void;
}

const TAB_LABELS: Record<string, string> = {
  ai: "AI Provider",
  model: "Model",
  workspace: "Workspace",
  environment: "Environment",
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
  startCommand,
  setStartCommand,
  envVarRows,
  setEnvVarRows,
  envContent,
  setEnvContent,
  cookieFile,
  setCookieFile,
  testUser,
  setTestUser,
  testPassword,
  setTestPassword,
  onSave,
  onSaveEnvironment,
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

        <div className="flex border-b border-neutral-800 overflow-x-auto">
          {(["ai", "model", "workspace", "environment", "limits"] as const).map((tab) => (
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

          {settingsTab === "environment" && (
            <div className="space-y-5">
              {!activeProject ? (
                <p className="text-sm text-neutral-500">No active project selected.</p>
              ) : (
                <>
                  <p className="text-xs text-neutral-500">
                    These settings are saved per-project and injected when Talon auto-starts your
                    dev server during browser validation.
                  </p>

                  <div>
                    <label className="block text-sm font-medium text-neutral-300 mb-1">
                      Start command
                    </label>
                    <input
                      type="text"
                      value={startCommand}
                      onChange={(e) => setStartCommand(e.target.value)}
                      placeholder="Auto-detect (leave blank)"
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                    <p className="text-xs text-neutral-600 mt-1">
                      Override auto-detection. Example: <code>npm run custom-dev</code>
                    </p>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-sm font-medium text-neutral-300">
                        Environment variables
                      </label>
                      <button
                        onClick={() =>
                          setEnvVarRows((prev) => [...prev, { key: "", value: "" }])
                        }
                        className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                      >
                        <Plus size={12} /> Add variable
                      </button>
                    </div>
                    {envVarRows.length === 0 ? (
                      <p className="text-xs text-neutral-600 italic">
                        No variables — injected into the dev server subprocess on startup.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {envVarRows.map((row, i) => (
                          <div key={i} className="flex gap-2 items-center">
                            <input
                              type="text"
                              value={row.key}
                              onChange={(e) =>
                                setEnvVarRows((prev) =>
                                  prev.map((r, idx) =>
                                    idx === i ? { ...r, key: e.target.value } : r
                                  )
                                )
                              }
                              placeholder="KEY"
                              className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-1.5 text-xs font-mono focus:outline-none focus:border-blue-500 transition-all"
                            />
                            <span className="text-neutral-600 text-xs">=</span>
                            <input
                              type="text"
                              value={row.value}
                              onChange={(e) =>
                                setEnvVarRows((prev) =>
                                  prev.map((r, idx) =>
                                    idx === i ? { ...r, value: e.target.value } : r
                                  )
                                )
                              }
                              placeholder="value"
                              className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-1.5 text-xs font-mono focus:outline-none focus:border-blue-500 transition-all"
                            />
                            <button
                              onClick={() =>
                                setEnvVarRows((prev) => prev.filter((_, idx) => idx !== i))
                              }
                              className="text-neutral-600 hover:text-red-400 transition-colors"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                    <p className="text-xs text-neutral-600 mt-2">
                      Use <code>NODE_ENV=test</code> or <code>MOCK_AUTH=true</code> to bypass
                      auth screens during validation.
                    </p>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-sm font-medium text-neutral-300">
                        .env content
                      </label>
                      <label className="flex items-center gap-1 text-xs text-neutral-400 hover:text-neutral-200 cursor-pointer transition-colors">
                        <Upload size={12} />
                        Upload file
                        <input
                          type="file"
                          accept=".env,text/plain"
                          className="hidden"
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (!file) return;
                            const reader = new FileReader();
                            reader.onload = (ev) => setEnvContent(ev.target?.result as string ?? "");
                            reader.readAsText(file);
                            e.target.value = "";
                          }}
                        />
                      </label>
                    </div>
                    <textarea
                      value={envContent}
                      onChange={(e) => setEnvContent(e.target.value)}
                      placeholder={"DATABASE_URL=postgresql://...\nNEXT_PUBLIC_API_URL=http://localhost:8000"}
                      rows={4}
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all resize-y"
                    />
                    <p className="text-xs text-neutral-600 mt-1">
                      Paste or upload your <code>.env</code> file. Injected into the dev server
                      subprocess. Variables set in the key-value list above take precedence.
                    </p>
                  </div>

                  <div className="pt-2 border-t border-neutral-800 space-y-3">
                    <div className="text-sm font-medium text-neutral-300">Test account credentials</div>
                    <p className="text-xs text-neutral-500">
                      If the app has a login screen, the browser agent will use these to sign in
                      automatically.
                    </p>
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1">
                        Username / Email
                      </label>
                      <input
                        type="text"
                        value={testUser}
                        onChange={(e) => setTestUser(e.target.value)}
                        placeholder="test@example.com"
                        className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-neutral-400 mb-1">
                        Password
                      </label>
                      <input
                        type="password"
                        value={testPassword}
                        onChange={(e) => setTestPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-neutral-300 mb-1">
                      Auth cookie file
                    </label>
                    <input
                      type="text"
                      value={cookieFile}
                      onChange={(e) => setCookieFile(e.target.value)}
                      placeholder="/path/to/cookies.json (optional)"
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                    <p className="text-xs text-neutral-600 mt-1">
                      Path to a Netscape/JSON cookie file. Loaded into Playwright before
                      navigating, bypassing login screens.
                    </p>
                  </div>
                </>
              )}
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
              onClick={settingsTab === "environment" ? onSaveEnvironment : onSave}
              disabled={savingSettings}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            >
              {savingSettings ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
              {settingsTab === "environment" ? "Save environment" : "Save settings"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
