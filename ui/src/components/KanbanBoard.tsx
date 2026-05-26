import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import type { DropResult } from "@hello-pangea/dnd";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Lightbulb,
  Play,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { COLUMNS } from "../constants";
import type { Issue } from "../types";

interface KanbanBoardProps {
  issues: Issue[];
  planningIssues: Set<number>;
  onDragEnd: (result: DropResult) => void;
  onDeleteIssue: (id: number) => void;
  onSelectIssue: (issue: Issue) => void;
}

export function KanbanBoard({
  issues,
  planningIssues,
  onDragEnd,
  onDeleteIssue,
  onSelectIssue,
}: KanbanBoardProps) {
  const getIssuesByStatus = (status: string) =>
    issues.filter((i) => i.status === status).sort((a, b) => b.id - a.id);

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <div className="flex gap-6 h-[calc(100vh-220px)] border-t border-neutral-800 pt-6">
        {COLUMNS.map((column) => {
          const colIssues = getIssuesByStatus(column);
          return (
            <div
              key={column}
              className="flex-1 flex flex-col bg-neutral-800/50 rounded-xl overflow-hidden border border-neutral-800"
            >
              <div className="p-4 border-b border-neutral-800 bg-neutral-800/80 flex justify-between items-center">
                <h2 className="font-semibold text-neutral-300 text-sm">{column}</h2>
                <span className="bg-neutral-700 text-xs px-2 py-1 rounded-full text-neutral-300">
                  {colIssues.length}
                </span>
              </div>
              <Droppable droppableId={column}>
                {(provided, snapshot) => (
                  <div
                    ref={provided.innerRef}
                    {...provided.droppableProps}
                    className={`flex-1 p-4 overflow-y-auto ${snapshot.isDraggingOver ? "bg-neutral-800/80" : ""}`}
                  >
                    {colIssues.length === 0 && (
                      <div className="text-neutral-700 text-xs text-center mt-4 select-none">
                        {column === "Backlog"
                          ? "Add a task to get started"
                          : `No ${column.toLowerCase()} tasks`}
                      </div>
                    )}
                    {colIssues.map((issue, index) => (
                      <Draggable key={issue.id} draggableId={issue.id.toString()} index={index}>
                        {(provided, snapshot) => (
                          <div
                            ref={provided.innerRef}
                            {...provided.draggableProps}
                            {...provided.dragHandleProps}
                            onClick={() => onSelectIssue(issue)}
                            className={`bg-neutral-800 border border-neutral-700 p-4 rounded-lg mb-3 shadow-sm cursor-pointer ${
                              snapshot.isDragging
                                ? "shadow-lg border-blue-500/50"
                                : "hover:border-neutral-600"
                            } transition-colors group`}
                          >
                            <div className="flex justify-between items-start mb-2">
                              <span className="text-xs text-neutral-500 font-mono">
                                T-{issue.id}
                              </span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onDeleteIssue(issue.id);
                                }}
                                className="text-neutral-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                            <h3 className="text-sm font-medium text-neutral-200 mb-3">
                              {issue.title}
                            </h3>
                            <div className="flex items-center gap-3 text-xs">
                              {issue.status === "In Progress" && (
                                <span className="flex items-center gap-1 text-blue-400 bg-blue-400/10 px-2 py-1 rounded">
                                  <Play size={12} className="animate-pulse" /> Agent running
                                </span>
                              )}
                              {issue.status === "Done" && (
                                <span className="flex items-center gap-1 text-green-400 bg-green-400/10 px-2 py-1 rounded">
                                  <CheckCircle2 size={12} /> Passed
                                </span>
                              )}
                              {issue.status === "Failed" && (
                                <span className="flex items-center gap-1 text-red-400 bg-red-400/10 px-2 py-1 rounded">
                                  <AlertCircle size={12} /> Needs Work
                                </span>
                              )}
                              {issue.status === "Backlog" && planningIssues.has(issue.id) && (
                                <span className="flex items-center gap-1 text-violet-400 bg-violet-400/10 px-2 py-1 rounded">
                                  <RefreshCw size={12} className="animate-spin" /> Planning...
                                </span>
                              )}
                              {issue.status === "Backlog" &&
                                !planningIssues.has(issue.id) &&
                                issue.plan_json && (
                                  <span className="flex items-center gap-1 text-violet-400 bg-violet-400/10 px-2 py-1 rounded">
                                    <Lightbulb size={12} /> Plan ready
                                  </span>
                                )}
                              {issue.status === "Backlog" &&
                                !planningIssues.has(issue.id) &&
                                !issue.plan_json && (
                                  <span className="flex items-center gap-1 text-neutral-400">
                                    <Clock size={12} /> Queued
                                  </span>
                                )}
                            </div>
                          </div>
                        )}
                      </Draggable>
                    ))}
                    {provided.placeholder}
                  </div>
                )}
              </Droppable>
            </div>
          );
        })}
      </div>
    </DragDropContext>
  );
}
