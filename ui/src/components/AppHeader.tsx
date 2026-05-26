import { Folder, GitBranch, Plus, RefreshCw, Settings as SettingsIcon, Zap } from "lucide-react";
import { GithubLogo } from "../constants";
import type { Project } from "../types";

interface AppHeaderProps {
  activeProject: Project | undefined;
  workspaceBadgeText: string | null;
  modelBadge: string | null;
  showGithubSync: boolean;
  syncing: boolean;
  onSyncIssues: () => void;
  onAddTask: () => void;
  onOpenSettings: () => void;
}

export function AppHeader({
  activeProject,
  workspaceBadgeText,
  modelBadge,
  showGithubSync,
  syncing,
  onSyncIssues,
  onAddTask,
  onOpenSettings,
}: AppHeaderProps) {
  return (
    <header className="mb-4 flex justify-between items-end">
      <div>
        <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent flex items-center gap-3">
          <img src="/favicon.svg" alt="Talon" className="w-12 h-12 flex-shrink-0" />
          Talon Board
        </h1>
        <div className="flex items-center gap-2 mt-2">
          <div className="text-neutral-400 text-sm">Autonomous Agent Tracker</div>
          {workspaceBadgeText && (
            <div
              className="flex items-center gap-1.5 text-xs bg-neutral-800 border border-neutral-700 text-neutral-300 px-2 py-0.5 rounded-full cursor-default"
              title="Active Workspace"
            >
              {activeProject?.workspace_mode === "github" ? (
                <GithubLogo size={10} />
              ) : (
                <Folder size={10} className="text-neutral-400" />
              )}
              <span className="max-w-[200px] truncate">{workspaceBadgeText}</span>
            </div>
          )}
          {activeProject?.workspace_mode === "github" && activeProject?.selected_branch && (
            <div
              className="flex items-center gap-1.5 text-xs bg-neutral-800 border border-neutral-700 text-neutral-300 px-2 py-0.5 rounded-full cursor-default"
              title="Target Branch"
            >
              <GitBranch size={10} className="text-neutral-400" />
              <span className="max-w-[160px] truncate">{activeProject.selected_branch}</span>
            </div>
          )}
          {modelBadge && (
            <button
              onClick={onOpenSettings}
              className="flex items-center gap-1.5 text-xs bg-neutral-800 border border-neutral-700 text-neutral-300 px-2 py-0.5 rounded-full hover:border-blue-500/60 transition-colors"
              title="Click to configure AI provider"
            >
              <Zap size={10} className="text-blue-400" />
              {modelBadge}
            </button>
          )}
        </div>
      </div>
      <div className="flex gap-3 items-center">
        {showGithubSync && (
          <button
            onClick={onSyncIssues}
            disabled={syncing}
            className="text-sm bg-neutral-800 hover:bg-neutral-700 text-neutral-300 px-3 py-2 rounded flex items-center gap-2 transition-colors border border-neutral-700 disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            Sync Issues
          </button>
        )}
        <button
          onClick={onAddTask}
          className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded flex items-center gap-2 text-sm transition-colors"
        >
          <Plus size={16} /> Add Task
        </button>
        <button
          onClick={onOpenSettings}
          className="p-2 bg-neutral-800 hover:bg-neutral-700 rounded text-neutral-400 hover:text-white transition-colors"
          title="Settings"
        >
          <SettingsIcon size={20} />
        </button>
      </div>
    </header>
  );
}
