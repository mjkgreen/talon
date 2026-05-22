import React from "react";
import { ArrowLeft, Check, Folder, Key, RefreshCw } from "lucide-react";
import { GithubLogo, API_KEY_PROVIDERS } from "../constants";
import { apiUrl } from "../utils";
import type { Repo } from "../types";

interface SetupWizardProps {
  wizardStep: number;
  setWizardStep: (v: number) => void;
  wizardKeys: Record<string, string>;
  setWizardKeys: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  savingWizardKeys: boolean;
  isConfigured: boolean;
  workspaceMode: "github" | "local" | "none" | "";
  localPath: string;
  setLocalPath: (v: string) => void;
  browsing: boolean;
  setBrowsing: (v: boolean) => void;
  selectedRepo: string;
  setSelectedRepo: (v: string) => void;
  repos: Repo[];
  loadingRepos: boolean;
  githubAuthStatus: "idle" | "waiting" | "error";
  githubAuthError: string;
  onSelectMode: (mode: "github" | "local" | "none") => void;
  onStartGithubOAuth: () => void;
  onCancelGithubAuth: () => void;
  onSaveLocalPath: () => void;
  onSaveRepo: () => void;
  onSaveWizardKeys: () => void;
}

export function SetupWizard({
  wizardStep,
  setWizardStep,
  wizardKeys,
  setWizardKeys,
  savingWizardKeys,
  isConfigured,
  workspaceMode,
  localPath,
  setLocalPath,
  browsing,
  setBrowsing,
  selectedRepo,
  setSelectedRepo,
  repos,
  loadingRepos,
  githubAuthStatus,
  githubAuthError,
  onSelectMode,
  onStartGithubOAuth,
  onCancelGithubAuth,
  onSaveLocalPath,
  onSaveRepo,
  onSaveWizardKeys,
}: SetupWizardProps) {
  if (wizardStep === 0) return null;

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
      <div className="bg-neutral-900 border border-neutral-800 p-8 rounded-2xl w-full max-w-md shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-32 bg-blue-500/10 blur-3xl rounded-full pointer-events-none" />

        {wizardStep === 1 && (
          <div className="relative">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center">
                <Key size={16} className="text-blue-400" />
              </div>
              <h2 className="text-2xl font-bold">Add an API key</h2>
            </div>
            <p className="text-sm text-neutral-400 mb-6">
              Talon needs access to at least one AI provider to run tasks.
            </p>
            <div className="space-y-3 mb-6">
              {API_KEY_PROVIDERS.map(({ field, label, placeholder }) => (
                <div key={field}>
                  <label className="block text-xs font-medium text-neutral-400 mb-1">{label}</label>
                  <input
                    type="password"
                    value={wizardKeys[field] || ""}
                    onChange={(e) => setWizardKeys((prev) => ({ ...prev, [field]: e.target.value }))}
                    placeholder={placeholder}
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-between items-center">
              <button
                onClick={() => setWizardStep(2)}
                className="text-sm text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                Skip for now
              </button>
              <button
                onClick={onSaveWizardKeys}
                disabled={savingWizardKeys || !Object.values(wizardKeys).some((v) => v.trim())}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
              >
                {savingWizardKeys ? <RefreshCw size={14} className="animate-spin" /> : null}
                Continue →
              </button>
            </div>
          </div>
        )}

        {wizardStep === 2 && (
          <div className="relative">
            {!isConfigured && (
              <button
                onClick={() => setWizardStep(1)}
                className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors"
              >
                <ArrowLeft size={14} /> Back
              </button>
            )}
            <h2 className="text-2xl font-bold mb-2">Workspace Setup</h2>
            <p className="text-sm text-neutral-400 mb-6">Where should Talon work when running tasks?</p>
            <div className="space-y-3">
              <button
                onClick={() => onSelectMode("github")}
                className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-blue-500/60 bg-neutral-800/50 hover:bg-blue-500/5 transition-all"
              >
                <div className="flex items-center gap-3 mb-1">
                  <GithubLogo size={18} />
                  <span className="font-medium text-sm">GitHub Repository</span>
                </div>
                <p className="text-xs text-neutral-500 ml-7">
                  Clone a repo from GitHub and work in an isolated branch per run.
                </p>
              </button>
              <button
                onClick={() => onSelectMode("local")}
                className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-blue-500/60 bg-neutral-800/50 hover:bg-blue-500/5 transition-all"
              >
                <div className="flex items-center gap-3 mb-1">
                  <Folder size={18} />
                  <span className="font-medium text-sm">Local Directory</span>
                </div>
                <p className="text-xs text-neutral-500 ml-7">Point Talon at a folder on this machine.</p>
              </button>
              <button
                onClick={() => onSelectMode("none")}
                className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-neutral-600 bg-neutral-800/50 hover:bg-neutral-800 transition-all"
              >
                <div className="flex items-center gap-3 mb-1">
                  <span className="text-neutral-400 font-medium text-sm">No Workspace</span>
                </div>
                <p className="text-xs text-neutral-500">Run tasks in a fresh empty workspace each time.</p>
              </button>
            </div>
            <button
              onClick={() => setWizardStep(0)}
              className="mt-5 text-sm text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              {isConfigured ? "Cancel" : "Skip for now"}
            </button>
          </div>
        )}

        {wizardStep === 3 && workspaceMode === "github" && (
          <div className="relative">
            <button
              onClick={() => setWizardStep(2)}
              className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors"
            >
              <ArrowLeft size={14} /> Back
            </button>
            <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
              <GithubLogo size={22} /> Connect GitHub
            </h2>
            <p className="text-sm text-neutral-400 mb-6">
              Authorize Talon via GitHub's device flow — no passwords or tokens to copy.
            </p>
            {githubAuthError && (
              <div className="mb-4 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                {githubAuthError}
              </div>
            )}
            {githubAuthStatus === "idle" && (
              <button
                onClick={onStartGithubOAuth}
                className="w-full py-3 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-colors"
              >
                <GithubLogo size={16} /> Login with GitHub
              </button>
            )}
            {githubAuthStatus === "waiting" && (
              <div className="space-y-4">
                <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-5 text-center space-y-2">
                  <p className="text-sm text-neutral-300">A browser window has opened.</p>
                  <p className="text-xs text-neutral-500">Authorize Talon on GitHub, then return here — this screen will advance automatically.</p>
                </div>
                <div className="flex items-center gap-2 text-sm text-neutral-400">
                  <RefreshCw size={14} className="animate-spin shrink-0" /> Waiting for authorization…
                </div>
                <button
                  onClick={onCancelGithubAuth}
                  className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        )}

        {wizardStep === 3 && workspaceMode === "local" && (
          <div className="relative">
            <button
              onClick={() => setWizardStep(2)}
              className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors"
            >
              <ArrowLeft size={14} /> Back
            </button>
            <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
              <Folder size={22} /> Local Directory
            </h2>
            <p className="text-sm text-neutral-400 mb-6">
              Enter the absolute path to the project folder on this machine.
            </p>
            <div className="mb-6">
              <label className="block text-sm font-medium text-neutral-300 mb-2">Project Path</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={localPath}
                  onChange={(e) => setLocalPath(e.target.value)}
                  autoFocus
                  placeholder="/Users/you/projects/my-app"
                  className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
                <button
                  type="button"
                  onClick={async () => {
                    setBrowsing(true);
                    try {
                      const res = await fetch(apiUrl("/api/local/browse"));
                      if (res.ok) {
                        const d = await res.json();
                        if (d.path) setLocalPath(d.path);
                      }
                    } finally {
                      setBrowsing(false);
                    }
                  }}
                  disabled={browsing}
                  className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-lg text-sm text-neutral-300 transition-colors whitespace-nowrap flex items-center gap-2 disabled:opacity-50"
                >
                  {browsing ? <RefreshCw size={14} className="animate-spin" /> : <Folder size={14} />}
                  {browsing ? "Opening…" : "Browse…"}
                </button>
              </div>
            </div>
            <div className="flex justify-between items-center">
              <button
                onClick={() => setWizardStep(0)}
                className="text-sm text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={onSaveLocalPath}
                disabled={!localPath.trim()}
                className="px-5 py-2.5 bg-green-600 hover:bg-green-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ml-auto"
              >
                Save <Check size={16} />
              </button>
            </div>
          </div>
        )}

        {wizardStep === 4 && (
          <div className="relative">
            <button
              onClick={() => setWizardStep(3)}
              className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors"
            >
              <ArrowLeft size={14} /> Back
            </button>
            <h2 className="text-2xl font-bold mb-2">Select Repository</h2>
            <p className="text-sm text-neutral-400 mb-6">Choose the codebase you want Talon to work on.</p>
            <div className="mb-6">
              <label className="block text-sm font-medium text-neutral-300 mb-2">Target Repository</label>
              <div className="relative">
                <select
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all appearance-none text-neutral-200"
                >
                  <option value="">Select a repository…</option>
                  {repos.map((r) => (
                    <option key={r.full_name} value={r.full_name}>
                      {r.full_name}
                    </option>
                  ))}
                </select>
                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none">
                  <svg className="w-4 h-4 text-neutral-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>
              {loadingRepos && (
                <p className="text-xs text-blue-400 mt-2 animate-pulse">Loading your repositories…</p>
              )}
            </div>
            <div className="flex justify-between items-center mt-8">
              <button
                onClick={() => setWizardStep(0)}
                className="text-sm text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={onSaveRepo}
                disabled={!selectedRepo}
                className="px-5 py-2.5 bg-green-600 hover:bg-green-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ml-auto"
              >
                Complete Setup <Check size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
