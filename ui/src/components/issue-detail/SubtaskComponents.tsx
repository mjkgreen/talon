import { useState } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, Circle, RefreshCw, XCircle } from "lucide-react";
import type { SubtaskType, SubtaskResultType } from "../../types";

type Subtask = SubtaskType;
type SubtaskResult = SubtaskResultType;

export function SubtaskItem({
  st,
  stResult,
  isRunning,
  liveDone,
  iconColor,
  textColor,
}: {
  st: Subtask;
  stResult: SubtaskResult | undefined;
  isRunning: boolean;
  liveDone: boolean;
  iconColor: string;
  textColor: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasOutput = !!stResult?.output;
  const filesModified: string[] = stResult?.files_modified ?? [];

  return (
    <div className="flex flex-col gap-1 text-xs">
      <div className="flex items-start gap-2">
        <span className={`mt-0.5 shrink-0 ${iconColor}`}>
          {isRunning ? (
            <RefreshCw size={12} className="animate-spin" />
          ) : stResult?.success || liveDone ? (
            <CheckCircle2 size={12} />
          ) : stResult ? (
            <XCircle size={12} />
          ) : (
            <Circle size={12} />
          )}
        </span>
        <div className="flex-1 min-w-0">
          <div className={textColor}>{st.description}</div>
          {filesModified.length > 0 && (
            <div className="mt-0.5 text-neutral-600 font-mono truncate">
              {filesModified.slice(0, 3).join(", ")}
              {filesModified.length > 3 && ` +${filesModified.length - 3} more`}
            </div>
          )}
        </div>
        {hasOutput && (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="shrink-0 text-neutral-600 hover:text-neutral-400 mt-0.5"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        )}
      </div>
      {expanded && stResult?.output && (
        <div className="ml-5 bg-neutral-950 rounded border border-neutral-800/50 p-2 overflow-x-auto max-h-64">
          <pre className="text-xs text-neutral-500 font-mono whitespace-pre-wrap">{stResult.output}</pre>
        </div>
      )}
    </div>
  );
}

export function SubtaskList({
  subtasks,
  subtaskResults,
  isLive,
  isLatest,
  logs,
}: {
  subtasks: Subtask[];
  subtaskResults: SubtaskResult[];
  isLive: boolean;
  isLatest: boolean;
  logs: string[];
}) {
  const doneCount = subtasks.filter((st) => {
    const stResult = subtaskResults?.find((r: SubtaskResult) => r.subtask?.id === st.id);
    const liveDone = !stResult && isLive && logs.some((line) => line.startsWith(`[${st.id}]`));
    return (stResult && stResult.success) || liveDone;
  }).length;
  const totalCount = subtasks.length;
  const allDone = doneCount >= totalCount;

  return (
    <div className="p-4 border-b border-neutral-800/50">
      <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3 flex items-center gap-2">
        Subagents
        {isLive && isLatest && !allDone && (
          <span className="font-normal normal-case text-neutral-600">
            {doneCount}/{totalCount} complete
          </span>
        )}
      </div>
      <div className="space-y-2">
        {subtasks.map((st: Subtask, si: number) => {
          const stResult = subtaskResults?.find((r: SubtaskResult) => r.subtask?.id === st.id);
          const liveStarted =
            !stResult && isLive && logs.some((line) => line.startsWith("->") && line.includes(`[${st.id}]`));
          const liveDone =
            !stResult && isLive && logs.some((line) => line.startsWith(`[${st.id}]`));
          const isRunning = liveStarted && !liveDone;

          const iconColor = stResult?.success
            ? "text-green-400"
            : stResult
              ? "text-red-400"
              : liveDone
                ? "text-green-400"
                : isRunning
                  ? "text-blue-400"
                  : "text-neutral-700";

          const textColor =
            isRunning
              ? "text-neutral-300"
              : stResult?.success || liveDone
                ? "text-neutral-400"
                : "text-neutral-500";

          return (
            <SubtaskItem
              key={si}
              st={st}
              stResult={stResult}
              isRunning={isRunning}
              liveDone={liveDone}
              iconColor={iconColor}
              textColor={textColor}
            />
          );
        })}
      </div>
    </div>
  );
}
