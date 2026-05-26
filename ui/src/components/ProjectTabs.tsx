import { Plus, X } from "lucide-react";
import type { Project } from "../types";

interface ProjectTabsProps {
  projects: Project[];
  activeProjectId: number | null;
  renamingProjectId: number | null;
  renamingName: string;
  renameInputRef: { current: HTMLInputElement | null };
  setRenamingName: (v: string) => void;
  setRenamingProjectId: (v: number | null) => void;
  onSelectProject: (id: number) => void;
  onStartRename: (id: number, name: string) => void;
  onFinishRename: () => void;
  onDeleteProject: (id: number) => void;
  onNewProject: () => void;
}

export function ProjectTabs({
  projects,
  activeProjectId,
  renamingProjectId,
  renamingName,
  renameInputRef,
  setRenamingName,
  setRenamingProjectId,
  onSelectProject,
  onStartRename,
  onFinishRename,
  onDeleteProject,
  onNewProject,
}: ProjectTabsProps) {
  return (
    <div className="flex items-end gap-1 mb-0 overflow-x-auto">
      {projects.map((project) => {
        const isActive = project.id === activeProjectId;
        return (
          <div
            key={project.id}
            className={`group relative flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-lg cursor-pointer border-t border-x transition-colors whitespace-nowrap ${
              isActive
                ? "bg-neutral-800 border-neutral-700 text-white"
                : "bg-neutral-900 border-transparent text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/50"
            }`}
            onClick={() => {
              if (renamingProjectId !== project.id) onSelectProject(project.id);
            }}
          >
            {renamingProjectId === project.id ? (
              <input
                ref={renameInputRef}
                value={renamingName}
                onChange={(e) => setRenamingName(e.target.value)}
                onBlur={onFinishRename}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onFinishRename();
                  if (e.key === "Escape") setRenamingProjectId(null);
                }}
                className="bg-transparent border-b border-blue-500 outline-none text-white w-28 text-sm"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span
                onDoubleClick={(e) => {
                  e.stopPropagation();
                  onStartRename(project.id, project.name);
                }}
              >
                {project.name}
              </span>
            )}
            {isActive && projects.length > 1 && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteProject(project.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-neutral-500 hover:text-red-400 transition-opacity ml-1"
              >
                <X size={12} />
              </button>
            )}
          </div>
        );
      })}
      <button
        onClick={onNewProject}
        className="flex items-center gap-1 px-3 py-2 text-sm text-neutral-500 hover:text-neutral-300 rounded-t-lg hover:bg-neutral-800/50 transition-colors border-t border-x border-transparent"
        title="New project"
      >
        <Plus size={14} />
      </button>
    </div>
  );
}
