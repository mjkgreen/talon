import { Key } from "lucide-react";

interface NoLlmGuardModalProps {
  onDismiss: () => void;
  onOpenSettings: () => void;
}

export function NoLlmGuardModal({ onDismiss, onOpenSettings }: NoLlmGuardModalProps) {
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
      <div className="bg-neutral-900 border border-amber-500/30 p-6 rounded-xl w-full max-w-sm shadow-2xl text-center">
        <div className="w-12 h-12 rounded-full bg-amber-500/10 flex items-center justify-center mx-auto mb-4">
          <Key size={24} className="text-amber-400" />
        </div>
        <h2 className="text-lg font-bold mb-2">No AI provider configured</h2>
        <p className="text-sm text-neutral-400 mb-6">Add an API key in Settings before running tasks.</p>
        <div className="flex gap-3 justify-center">
          <button onClick={onDismiss} className="px-4 py-2 text-sm text-neutral-400 hover:text-white">
            Dismiss
          </button>
          <button
            onClick={onOpenSettings}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm transition-colors"
          >
            Open Settings
          </button>
        </div>
      </div>
    </div>
  );
}
