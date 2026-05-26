import { useState, useEffect, useRef } from "react";
import type { Issue, Project, RunState } from "../types";

interface WebSocketCallbacks {
  onIssueUpdated: (issue: Issue) => void;
  onIssueDeleted: (issueId: number) => void;
  onSelectedIssueSync: (updatedIssue: Issue) => void;
  onGithubAuthComplete: () => void;
  onProjectCreated: (project: Project) => void;
  onProjectUpdated: (project: Project) => void;
  onProjectDeleted: (projectId: number) => void;
  onWorkspaceInvalid?: (data: { issue_id?: number; error?: string }) => void;
}

export function useWebSocket(
  activeProjectIdRef: React.MutableRefObject<number | null>,
  fetchIssues: (projId?: number | null) => void,
  callbacks: WebSocketCallbacks,
) {
  const [liveRunStates, setLiveRunStates] = useState<Record<number, RunState>>({});
  const [runErrors, setRunErrors] = useState<Record<number, string>>({});
  const [runLogs, setRunLogs] = useState<Record<number, string[]>>({});
  const [planningIssues, setPlanningIssues] = useState<Set<number>>(new Set());

  const cbRef = useRef(callbacks);
  cbRef.current = callbacks;
  const fetchIssuesRef = useRef(fetchIssues);
  fetchIssuesRef.current = fetchIssues;

  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let alive = true;

    const handleMessage = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      const cb = cbRef.current;

      if (data.type === "issue_updated") {
        if (data.issue.status === "In Progress") {
          setRunLogs((logs) => {
            const was = logs[data.issue.id];
            return was !== undefined ? logs : { ...logs, [data.issue.id]: [] };
          });
        }
        cb.onIssueUpdated(data.issue);
        cb.onSelectedIssueSync(data.issue);
      } else if (data.type === "issue_deleted") {
        cb.onIssueDeleted(data.issue_id);
      } else if (data.type === "run_state_updated") {
        setLiveRunStates((prev) => ({ ...prev, [data.issue_id]: data.state }));
      } else if (data.type === "run_log") {
        setRunLogs((prev) => {
          const current = prev[data.issue_id] ?? [];
          return { ...prev, [data.issue_id]: [...current, data.message] };
        });
      } else if (data.type === "run_error") {
        setRunErrors((prev) => ({ ...prev, [data.issue_id]: data.error }));
      } else if (data.type === "plan_started") {
        setPlanningIssues((prev) => new Set([...prev, data.issue_id]));
      } else if (data.type === "plan_ready") {
        setPlanningIssues((prev) => {
          const next = new Set(prev);
          next.delete(data.issue_id);
          return next;
        });
        if (data.issue) {
          cb.onIssueUpdated(data.issue);
          cb.onSelectedIssueSync(data.issue);
        }
      } else if (data.type === "plan_error") {
        setPlanningIssues((prev) => {
          const next = new Set(prev);
          next.delete(data.issue_id);
          return next;
        });
      } else if (data.type === "github_auth_complete") {
        cb.onGithubAuthComplete();
      } else if (data.type === "project_created") {
        cb.onProjectCreated(data.project);
      } else if (data.type === "project_updated") {
        cb.onProjectUpdated(data.project);
      } else if (data.type === "project_deleted") {
        cb.onProjectDeleted(data.project_id);
      } else if (data.type === "workspace_invalid") {
        cb.onWorkspaceInvalid?.(data);
      }
    };

    const connect = () => {
      const wsUrl =
        window.location.protocol === "https:"
          ? "wss://" + window.location.host + "/ws"
          : "ws://" + window.location.host + "/ws";
      ws = new WebSocket(import.meta.env.DEV ? "ws://localhost:8080/ws" : wsUrl);
      ws.onopen = () => fetchIssuesRef.current(activeProjectIdRef.current);
      ws.onmessage = handleMessage;
      ws.onclose = () => {
        if (alive) reconnectTimer = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
    };
    connect();

    return () => {
      alive = false;
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { liveRunStates, runErrors, runLogs, planningIssues };
}
