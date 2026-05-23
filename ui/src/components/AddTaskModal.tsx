import React from "react";
import { RefreshCw } from "lucide-react";

interface AddTaskModalProps {
  newTitle: string;
  setNewTitle: (v: string) => void;
  newDescription: string;
  setNewDescription: (v: string) => void;
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

export function AddTaskModal({
  newTitle,
  setNewTitle,
  newDescription,
  setNewDescription,
  isSubmitting = false,
  onClose,
  onSubmit,
}: AddTaskModalProps) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
      <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-xl w-full max-w-lg shadow-2xl">
        <h2 className="text-xl font-bold mb-4">Add New Task</h2>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-neutral-300 mb-1">Title</label>
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              autoFocus
              placeholder="e.g., Create a new landing page"
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-300 mb-1">Description (Optional)</label>
            <textarea
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Provide any additional context or acceptance criteria for the agent..."
              rows={5}
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all resize-none"
            />
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-neutral-400 hover:text-white">
              Cancel
            </button>
            <button
              type="submit"
              disabled={!newTitle.trim() || isSubmitting}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded text-sm transition-colors flex items-center gap-2"
            >
              {isSubmitting && <RefreshCw size={13} className="animate-spin" />}
              {isSubmitting ? "Creating..." : "Create Task"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
