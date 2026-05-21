import React from "react";
import { RefreshCw } from "lucide-react";

interface NewProjectModalProps {
  newProjectName: string;
  setNewProjectName: (v: string) => void;
  creatingProject: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function NewProjectModal({
  newProjectName,
  setNewProjectName,
  creatingProject,
  onClose,
  onSubmit,
}: NewProjectModalProps) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
      <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-xl w-full max-w-sm shadow-2xl">
        <h2 className="text-lg font-bold mb-4">New Project</h2>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-neutral-300 mb-1">Project name</label>
            <input
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              autoFocus
              placeholder="My App"
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
            />
          </div>
          <p className="text-xs text-neutral-500">
            You can configure the workspace (GitHub repo or local folder) in Settings after creation.
          </p>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-neutral-400 hover:text-white">
              Cancel
            </button>
            <button
              type="submit"
              disabled={!newProjectName.trim() || creatingProject}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded text-sm transition-colors flex items-center gap-2"
            >
              {creatingProject ? <RefreshCw size={14} className="animate-spin" /> : null}
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
