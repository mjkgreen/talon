import React from "react";
import { AlertCircle, CheckCircle2, Play } from "lucide-react";

export function logLineClass(line: string): string {
  if (line.startsWith("===")) return "text-blue-500";
  if (line.startsWith("->")) return "text-cyan-500";
  if (line.startsWith("Files modified:")) return "text-green-500";
  if (line.includes("modified:")) return "text-green-600";
  return "text-neutral-400";
}

export function LogLines({
  lines,
  scrollRef,
}: {
  lines: string[];
  scrollRef?: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      ref={scrollRef}
      className="bg-black/30 px-4 py-3 font-mono text-xs max-h-44 overflow-y-auto overflow-x-hidden"
    >
      {lines.map((line, i) => (
        <div key={i} className="leading-relaxed flex gap-2 min-w-0">
          <span className="text-neutral-700 shrink-0 select-none">[server]</span>
          <span className={`break-words min-w-0 ${logLineClass(line)}`}>{line}</span>
        </div>
      ))}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const base = "text-xs px-2 py-1 rounded-full flex items-center gap-1";
  if (status === "Done")
    return (
      <span className={`${base} bg-green-500/10 text-green-400 border border-green-500/20`}>
        <CheckCircle2 size={10} /> {status}
      </span>
    );
  if (status === "Failed")
    return (
      <span className={`${base} bg-red-500/10 text-red-400 border border-red-500/20`}>
        <AlertCircle size={10} /> {status}
      </span>
    );
  if (status === "In Progress")
    return (
      <span className={`${base} bg-blue-500/10 text-blue-400 border border-blue-500/20`}>
        <Play size={10} className="animate-pulse" /> {status}
      </span>
    );
  return (
    <span className={`${base} bg-neutral-800 text-neutral-400 border border-neutral-700`}>{status}</span>
  );
}

export interface LimitHint {
  message: string;
  setting: string;
}

export function detectLimitHint(error: string): LimitHint | null {
  const e = error.toLowerCase();
  if (
    e.includes("context_window") ||
    e.includes("context window") ||
    e.includes("token count exceeds") ||
    e.includes("maximum number of tokens") ||
    e.includes("context_window_exceeded") ||
    e.includes("max_tokens")
  ) {
    return {
      message: "The model hit its token limit.",
      setting: "Increase Max tokens per agent call in Settings → Limits.",
    };
  }
  if (
    e.includes("rate limit") ||
    e.includes("ratelimit") ||
    e.includes("too many requests") ||
    e.includes("429")
  ) {
    return {
      message: "The provider rate-limited the request.",
      setting: "Try switching to a different model or provider in Settings → Model.",
    };
  }
  if (e.includes("timeout") || e.includes("timed out")) {
    return {
      message: "An agent call timed out.",
      setting: "The model may be overloaded — retry, or switch models in Settings → Model.",
    };
  }
  return null;
}
