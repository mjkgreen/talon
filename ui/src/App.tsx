import React, { useState, useEffect, useRef } from "react";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import type { DropResult } from "@hello-pangea/dnd";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Folder,
  GitBranch,
  Lightbulb,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Settings as SettingsIcon,
  Trash2,
  X,
  Zap,
} from "lucide-react";

import { COLUMNS, GithubLogo } from "./constants";
import { apiUrl } from "./utils";
import type { Issue, Project, PlanResult, Repo, RunState } from "./types";
import { AddTaskModal } from "./components/AddTaskModal";
import { NewProjectModal } from "./components/NewProjectModal";
import { NoLlmGuardModal } from "./components/NoLlmGuardModal";
import { SetupWizard } from "./components/SetupWizard";
import { SettingsModal } from "./components/SettingsModal";
import type { EnvVarRow } from "./components/SettingsModal";
import { IssueDetailModal } from "./components/IssueDetailModal";

export default function KanbanBoard() {
  // --- Issues & projects ---
  const [issues, setIssues] = useState<Issue[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectIdState] = useState<number | null>(null);

  // --- Add task modal ---
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [isCreatingTask, setIsCreatingTask] = useState(false);

  // --- Issue detail modal ---
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [loadingRunState, setLoadingRunState] = useState(false);
  const [liveRunStates, setLiveRunStates] = useState<Record<number, RunState>>({});
  const [runErrors, setRunErrors] = useState<Record<number, string>>({});
  const [runLogs, setRunLogs] = useState<Record<number, string[]>>({});
  const [activeTraceTab, setActiveTraceTab] = useState<"plan" | number>("plan");
  const followLatestRef = useRef(true);
  const [planningIssues, setPlanningIssues] = useState<Set<number>>(new Set());
  const [editingPlan, setEditingPlan] = useState(false);
  const [planDraft, setPlanDraft] = useState<PlanResult | null>(null);

  // --- Workspace error (invalid / stale path detected server-side) ---
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);

  // --- First-run wizard ---
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardKeys, setWizardKeys] = useState<Record<string, string>>({});
  const [savingWizardKeys, setSavingWizardKeys] = useState(false);

  // --- Workspace config ---
  const [workspaceMode, setWorkspaceMode] = useState<"github" | "local" | "none" | "">("");
  const [localPath, setLocalPath] = useState("");
  const [selectedRepo, setSelectedRepo] = useState("");
  const [selectedBranch, setSelectedBranch] = useState("");
  const [branches, setBranches] = useState<string[]>([]);
  const [loadingBranches, setLoadingBranches] = useState(false);
  const [, setHasGithubToken] = useState(false);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [githubAuthStatus, setGithubAuthStatus] = useState<"idle" | "waiting" | "error">("idle");
  const [githubAuthError, setGithubAuthError] = useState("");
  const githubPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- AI / LLM ---
  const [hasLlm, setHasLlm] = useState(false);
  const [isConfigured, setIsConfigured] = useState(true);
  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [noLlmGuardOpen, setNoLlmGuardOpen] = useState(false);

  // --- Settings modal ---
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"ai" | "model" | "workspace" | "environment" | "limits">("ai");
  const [savingSettings, setSavingSettings] = useState(false);
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [modelDrafts, setModelDrafts] = useState<Record<string, string>>({});
  const [advancedModelOpen, setAdvancedModelOpen] = useState(false);
  const [maxIterations, setMaxIterations] = useState("5");
  const [maxTokens, setMaxTokens] = useState("");
  const [reviewerMaxToolTurns, setReviewerMaxToolTurns] = useState("50");
  const [maxConcurrentRuns, setMaxConcurrentRuns] = useState("3");
  const [browserTestMaxSteps, setBrowserTestMaxSteps] = useState("20");
  const [editLocalDirectly, setEditLocalDirectly] = useState(false);
  const [pushOnPass, setPushOnPass] = useState(true);

  // --- Per-project environment settings ---
  const [startCommand, setStartCommand] = useState("");
  const [envVarRows, setEnvVarRows] = useState<EnvVarRow[]>([]);
  const [envContent, setEnvContent] = useState("");
  const [cookieFile, setCookieFile] = useState("");
  const [testUser, setTestUser] = useState("");
  const [testPassword, setTestPassword] = useState("");

  // --- Project management ---
  const [newProjectModalOpen, setNewProjectModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const [renamingProjectId, setRenamingProjectId] = useState<number | null>(null);
  const [renamingName, setRenamingName] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const activeProjectIdRef = useRef<number | null>(null);

  // ===================== helpers =====================

  const _parseEnvVarRows = (raw: string | undefined): EnvVarRow[] => {
    if (!raw) return [];
    try {
      const obj = JSON.parse(raw) as Record<string, string>;
      return Object.entries(obj).map(([key, value]) => ({ key, value }));
    } catch {
      return [];
    }
  };

  const setActiveProject = (id: number) => {
    setActiveProjectIdState(id);
    activeProjectIdRef.current = id;
    localStorage.setItem("talon_active_project", String(id));
    fetchIssues(id);
    const project = projects.find((p) => p.id === id);
    if (project) {
      setLocalPath(project.local_path || "");
      setSelectedRepo(project.selected_repo || "");
      setSelectedBranch(project.selected_branch || "");
      setWorkspaceMode(project.workspace_mode as "github" | "local" | "none" | "");
      setStartCommand(project.start_command || "");
      setEnvVarRows(_parseEnvVarRows(project.project_env_vars));
      setEnvContent(project.env_content || "");
      setCookieFile(project.cookie_file || "");
      setTestUser(project.test_user || "");
      setTestPassword(project.test_password || "");
    }
  };

  // ===================== data fetching =====================

  const fetchIssues = async (projId?: number | null) => {
    const id = projId !== undefined ? projId : activeProjectId;
    const url = id != null ? apiUrl(`/api/issues?project_id=${id}`) : apiUrl("/api/issues");
    const res = await fetch(url);
    if (res.ok) {
      const data: Issue[] = await res.json();
      setIssues(data);
      data.forEach((issue) => {
        if (issue.run_id) {
          fetch(apiUrl(`/api/runs/${issue.run_id}`))
            .then((r) => (r.ok ? r.json() : null))
            .then((state) => {
              if (state) {
                setLiveRunStates((prev) => ({ ...prev, [issue.id]: state }));
              }
            })
            .catch(() => {});
        }
      });
    }
  };

  const fetchProjects = async (): Promise<number | null> => {
    const res = await fetch(apiUrl("/api/projects"));
    if (!res.ok) return null;
    const list: Project[] = await res.json();
    setProjects(list);

    const syncWorkspaceFromProject = (project: Project) => {
      setLocalPath(project.local_path || "");
      setSelectedRepo(project.selected_repo || "");
      setSelectedBranch(project.selected_branch || "");
      setWorkspaceMode(project.workspace_mode as "github" | "local" | "none" | "");
      setStartCommand(project.start_command || "");
      setEnvVarRows(_parseEnvVarRows(project.project_env_vars));
      setEnvContent(project.env_content || "");
      setCookieFile(project.cookie_file || "");
      setTestUser(project.test_user || "");
      setTestPassword(project.test_password || "");
    };

    const stored = localStorage.getItem("talon_active_project");
    const storedId = stored ? parseInt(stored) : null;
    if (storedId) {
      const match = list.find((p) => p.id === storedId);
      if (match) {
        setActiveProjectIdState(storedId);
        activeProjectIdRef.current = storedId;
        syncWorkspaceFromProject(match);
        return storedId;
      }
    }
    if (list.length > 0) {
      setActiveProjectIdState(list[0].id);
      activeProjectIdRef.current = list[0].id;
      localStorage.setItem("talon_active_project", String(list[0].id));
      syncWorkspaceFromProject(list[0]);
      return list[0].id;
    }
    return null;
  };

  const fetchSettings = async () => {
    try {
      const res = await fetch(apiUrl("/api/settings"));
      if (!res.ok) return;
      const data = await res.json();

      const llmOk = !!data.has_llm_configured;
      setHasLlm(llmOk);
      setActiveProvider(data.active_provider || null);
      setIsConfigured(llmOk);
      if (!llmOk) setWizardStep(1);

      setKeyDrafts({
        anthropic_api_key: data.anthropic_api_key || "",
        openai_api_key: data.openai_api_key || "",
        gemini_api_key: data.gemini_api_key || "",
        groq_api_key: data.groq_api_key || "",
        mistral_api_key: data.mistral_api_key || "",
      });
      setModelDrafts({
        agent_model: data.agent_model || "",
        orchestrator_model: data.orchestrator_model || "",
        subagent_model: data.subagent_model || "",
        reviewer_model: data.reviewer_model || "",
        refiner_model: data.refiner_model || "",
      });
      setMaxIterations(data.max_iterations || "5");
      setMaxTokens(data.agent_max_tokens || "");
      setReviewerMaxToolTurns(data.reviewer_max_tool_turns || "50");
      setMaxConcurrentRuns(data.max_concurrent_runs || "3");
      setBrowserTestMaxSteps(data.browser_test_max_steps || "20");
      setEditLocalDirectly(data.edit_local_directly === "true");
      setPushOnPass(data.push_on_pass !== "false");

      setHasGithubToken(!!data.github_token);
    } catch (e) {
      console.error("Failed to fetch settings", e);
    }
  };

  const fetchRepos = async () => {
    setLoadingRepos(true);
    try {
      const res = await fetch(apiUrl("/api/github/repos"));
      if (res.ok) setRepos(await res.json());
    } catch (e) {
      console.error(e);
    }
    setLoadingRepos(false);
  };

  const fetchBranches = async (repoFullName: string) => {
    if (!repoFullName) {
      setBranches([]);
      setSelectedBranch("");
      return;
    }
    setLoadingBranches(true);
    try {
      const [owner, repo] = repoFullName.split("/");
      const res = await fetch(apiUrl(`/api/github/repos/${owner}/${repo}/branches`));
      if (res.ok) {
        const data = await res.json() as { default_branch: string; branches: string[] };
        setBranches(data.branches);
        setSelectedBranch((prev) => prev || data.default_branch);
      }
    } catch (e) {
      console.error(e);
    }
    setLoadingBranches(false);
  };

  // ===================== effects =====================

  // Sync branch state from the active project
  useEffect(() => {
    const project = projects.find((p) => p.id === activeProjectId);
    if (project?.selected_branch) {
      setSelectedBranch(project.selected_branch);
    }
  }, [activeProjectId, projects]);

  // Fetch branches when wizard step 4 opens with a repo already selected
  useEffect(() => {
    if (wizardStep === 4 && selectedRepo) {
      setSelectedBranch("");
      fetchBranches(selectedRepo);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wizardStep]);

  useEffect(() => {
    const init = async () => {
      const projId = await fetchProjects();
      await Promise.all([fetchIssues(projId), fetchSettings()]);
    };
    init();

    let ws: WebSocket;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let alive = true;

    const handleMessage = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      if (data.type === "issue_updated") {
        setIssues((prev) => {
          if (data.issue.status === "In Progress") {
            const was = prev.find((i) => i.id === data.issue.id);
            if (!was || was.status !== "In Progress") {
              setRunLogs((logs) => ({ ...logs, [data.issue.id]: [] }));
            }
          }
          const exists = prev.find((i) => i.id === data.issue.id);
          if (exists) return prev.map((i) => (i.id === data.issue.id ? data.issue : i));
          return [data.issue, ...prev];
        });
        setSelectedIssue((prev) => (prev?.id === data.issue.id ? data.issue : prev));
      } else if (data.type === "issue_deleted") {
        setIssues((prev) => prev.filter((i) => i.id !== data.issue_id));
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
          setIssues((prev) => prev.map((i) => (i.id === data.issue.id ? data.issue : i)));
          setSelectedIssue((prev) => (prev?.id === data.issue.id ? data.issue : prev));
        }
      } else if (data.type === "plan_error") {
        setPlanningIssues((prev) => {
          const next = new Set(prev);
          next.delete(data.issue_id);
          return next;
        });
      } else if (data.type === "github_auth_complete") {
        stopGithubPoll();
        setGithubAuthStatus("idle");
        setHasGithubToken(true);
        fetchRepos().then(() => setWizardStep(4));
      } else if (data.type === "project_created") {
        setProjects((prev) => [...prev, data.project]);
      } else if (data.type === "project_updated") {
        setProjects((prev) => prev.map((p) => (p.id === data.project.id ? data.project : p)));
      } else if (data.type === "project_deleted") {
        setProjects((prev) => prev.filter((p) => p.id !== data.project_id));
      } else if (data.type === "workspace_invalid") {
        // Revert the issue to Backlog (server already did this, just sync UI)
        if (data.issue_id) {
          setIssues((prev) =>
            prev.map((i) => (i.id === data.issue_id ? { ...i, status: "Backlog" } : i))
          );
          setPlanningIssues((prev) => {
            const next = new Set(prev);
            next.delete(data.issue_id);
            return next;
          });
        }
        setWorkspaceError(data.error ?? "Workspace is invalid or no longer exists.");
        setWizardStep(2);
      }
    };

    const connect = () => {
      const wsUrl =
        window.location.protocol === "https:"
          ? "wss://" + window.location.host + "/ws"
          : "ws://" + window.location.host + "/ws";
      ws = new WebSocket(import.meta.env.DEV ? "ws://localhost:8080/ws" : wsUrl);
      ws.onopen = () => fetchIssues(activeProjectIdRef.current);
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

  useEffect(() => {
    const runId = selectedIssue?.run_id;
    if (runId) {
      Promise.resolve().then(() => {
        setLoadingRunState(true);
      });
      fetch(apiUrl(`/api/runs/${runId}`))
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          setRunState(data);
          setLoadingRunState(false);
        })
        .catch(() => setLoadingRunState(false));
    } else {
      Promise.resolve().then(() => {
        setRunState(null);
      });
    }
  }, [selectedIssue?.id, selectedIssue?.run_id]);

  useEffect(() => {
    Promise.resolve().then(() => {
      setActiveTraceTab("plan");
      setEditingPlan(false);
      setPlanDraft(null);
    });
    followLatestRef.current = true;
  }, [selectedIssue?.id]);

  useEffect(() => {
    if (!selectedIssue || !followLatestRef.current) return;
    const state = liveRunStates[selectedIssue.id];
    const count = state?.executor_results?.length ?? 0;
    if (count > 0) {
      Promise.resolve().then(() => {
        setActiveTraceTab(count - 1);
      });
    }
  }, [selectedIssue?.id, liveRunStates]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (renamingProjectId !== null && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingProjectId]);

  // Re-sync project workspace state whenever the window regains focus so stale
  // paths (e.g. configured in another tab or updated externally) are detected.
  useEffect(() => {
    const handleFocus = async () => {
      const res = await fetch(apiUrl("/api/projects"));
      if (!res.ok) return;
      const list: Project[] = await res.json();
      setProjects(list);
      const active = list.find((p) => p.id === activeProjectIdRef.current);
      if (active) {
        setLocalPath(active.local_path || "");
        setSelectedRepo(active.selected_repo || "");
        setSelectedBranch(active.selected_branch || "");
        setWorkspaceMode(active.workspace_mode as "github" | "local" | "none" | "");
        setStartCommand(active.start_command || "");
        setEnvVarRows(_parseEnvVarRows(active.project_env_vars));
        setEnvContent(active.env_content || "");
        setCookieFile(active.cookie_file || "");
        setTestUser(active.test_user || "");
        setTestPassword(active.test_password || "");
      }
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ===================== actions =====================

  const selectMode = async (mode: "github" | "local" | "none") => {
    setWorkspaceMode(mode);
    await fetch(apiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_mode: mode }),
    });
    if (activeProjectId) {
      await fetch(apiUrl(`/api/projects/${activeProjectId}`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_mode: mode }),
      });
    }
    if (mode === "none") {
      setWizardStep(0);
    } else {
      // Re-seed path/repo from the active project so the wizard input starts
      // with that project's current value, not a stale global setting.
      const proj = projects.find((p) => p.id === activeProjectId);
      if (mode === "local") {
        setLocalPath(proj?.local_path || "");
      } else if (mode === "github") {
        setSelectedRepo(proj?.selected_repo || "");
        setSelectedBranch(proj?.selected_branch || "");
        setGithubAuthStatus("idle");
        setGithubAuthError("");
      }
      setWizardStep(3);
    }
  };

  const stopGithubPoll = () => {
    if (githubPollRef.current) {
      clearInterval(githubPollRef.current);
      githubPollRef.current = null;
    }
  };

  const cancelGithubAuth = () => {
    stopGithubPoll();
    setGithubAuthStatus("idle");
  };

  const startGithubOAuth = async () => {
    setGithubAuthError("");
    // Use the web flow (OAuth redirect via talon:// deep link). Device flow is
    // unreliable because GitHub requires "Device Flow" to be explicitly enabled
    // in the OAuth App settings; the web flow works with any OAuth App.
    const res = await fetch(apiUrl("/api/auth/github/authorize"));
    if (!res.ok) {
      const err = (await res.json().catch(() => ({}))) as { detail?: string };
      setGithubAuthError(err.detail || "Failed to start GitHub auth. Is GITHUB_CLIENT_ID set?");
      return;
    }
    const data = (await res.json()) as { url: string; state: string };
    setGithubAuthStatus("waiting");

    const talonWindow = (window as unknown as { talon?: { openExternal: (url: string) => void } }).talon;
    if (talonWindow?.openExternal) {
      talonWindow.openExternal(data.url);
    } else {
      window.open(data.url, "_blank", "noopener,noreferrer");
    }

    // Poll /api/settings as a fallback in case the deep-link fires before the
    // WebSocket message, or the WS reconnects after the exchange completes.
    // Snapshot the token *before* auth so we only advance on a newly-saved token.
    const tokenBefore =
      (
        (await fetch(apiUrl("/api/settings"))
          .then((r) => r.json())
          .catch(() => ({}))) as { github_token?: string }
      ).github_token ?? "";
    stopGithubPoll();
    githubPollRef.current = setInterval(async () => {
      try {
        const settingsRes = await fetch(apiUrl("/api/settings"));
        if (!settingsRes.ok) return;
        const settings = (await settingsRes.json()) as { github_token?: string };
        if (settings.github_token && settings.github_token !== tokenBefore) {
          stopGithubPoll();
          setGithubAuthStatus("idle");
          setHasGithubToken(true);
          fetchRepos().then(() => setWizardStep(4));
        }
      } catch (e) {
        console.error("GitHub auth poll error", e);
      }
    }, 3000);
  };

  const saveLocalPathAndFinish = async () => {
    await fetch(apiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ local_path: localPath }),
    });
    if (activeProjectId) {
      await fetch(apiUrl(`/api/projects/${activeProjectId}`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_mode: "local", local_path: localPath }),
      });
      fetchProjects();
    }
    setWorkspaceError(null);
    setWizardStep(0);
  };

  const saveRepoAndFinish = async () => {
    await fetch(apiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_repo: selectedRepo }),
    });
    if (activeProjectId) {
      await fetch(apiUrl(`/api/projects/${activeProjectId}`), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace_mode: "github",
          selected_repo: selectedRepo,
          selected_branch: selectedBranch || null,
        }),
      });
      fetchProjects();
    }
    setWorkspaceError(null);
    setWizardStep(0);
  };

  const saveWizardKeysAndContinue = async () => {
    const anyKey = Object.values(wizardKeys).some((v) => v.trim());
    if (anyKey) {
      setSavingWizardKeys(true);
      await fetch(apiUrl("/api/settings"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(wizardKeys),
      });
      await fetchSettings();
      setSavingWizardKeys(false);
    }
    setWizardStep(2);
  };

  const syncGithubIssues = async () => {
    setSyncing(true);
    const url = activeProjectId ? apiUrl(`/api/github/sync?project_id=${activeProjectId}`) : apiUrl("/api/github/sync");
    const res = await fetch(url, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      alert(`Synced ${data.synced} new issues from GitHub!`);
      fetchIssues();
    } else {
      alert("Failed to sync issues.");
    }
    setSyncing(false);
  };

  const addIssue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setIsCreatingTask(true);
    try {
      const res = await fetch(apiUrl("/api/issues"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newTitle,
          description: newDescription,
          status: "Backlog",
          project_id: activeProjectId,
        }),
      });
      if (res.ok) {
        const created: Issue = await res.json();
        setIssues((prev) => (prev.find((i) => i.id === created.id) ? prev : [created, ...prev]));
        setNewTitle("");
        setNewDescription("");
        setIsAddModalOpen(false);
      }
    } finally {
      setIsCreatingTask(false);
    }
  };

  const deleteIssue = async (id: number) => {
    setIssues((prev) => prev.filter((i) => i.id !== id));
    await fetch(apiUrl(`/api/issues/${id}`), { method: "DELETE" });
  };

  const pauseIssue = async (id: number) => {
    await fetch(apiUrl(`/api/issues/${id}/pause`), { method: "POST" });
  };

  const resumeIssue = async (id: number) => {
    setIssues((prev) => prev.map((i) => (i.id === id ? { ...i, status: "In Progress" } : i)));
    await fetch(apiUrl(`/api/issues/${id}/resume`), { method: "POST" });
  };

  const restartIssue = async (id: number) => {
    if (!confirm("Are you sure you want to restart this task and run all iterations from scratch?")) return;
    setIssues((prev) => prev.map((i) => (i.id === id ? { ...i, status: "In Progress" } : i)));
    await fetch(apiUrl(`/api/issues/${id}/restart`), { method: "POST" });
  };

  const onDragEnd = async (result: DropResult) => {
    if (!result.destination) return;
    const sourceStatus = result.source.droppableId;
    const destStatus = result.destination.droppableId;
    const issueId = parseInt(result.draggableId);
    if (sourceStatus === destStatus) return;
    if (destStatus === "In Progress" && !hasLlm) {
      setNoLlmGuardOpen(true);
      return;
    }
    const project = projects.find((p) => p.id === activeProjectId);
    const noWorkspace = !project?.workspace_mode || project.workspace_mode === "none";
    if (destStatus === "In Progress" && noWorkspace) {
      setWizardStep(2);
      return;
    }
    setIssues((prev) => prev.map((i) => (i.id === issueId ? { ...i, status: destStatus } : i)));
    await fetch(apiUrl(`/api/issues/${issueId}`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: destStatus }),
    });
  };

  const saveSettings = async () => {
    setSavingSettings(true);
    await fetch(apiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...keyDrafts,
        ...modelDrafts,
        max_iterations: maxIterations,
        agent_max_tokens: maxTokens,
        reviewer_max_tool_turns: reviewerMaxToolTurns,
        max_concurrent_runs: maxConcurrentRuns,
        browser_test_max_steps: browserTestMaxSteps,
      }),
    });
    await fetchSettings();
    setSavingSettings(false);
  };

  const saveEnvironment = async () => {
    if (!activeProjectId) return;
    setSavingSettings(true);
    const envObj: Record<string, string> = {};
    envVarRows.forEach(({ key, value }) => {
      if (key.trim()) envObj[key.trim()] = value;
    });
    await fetch(apiUrl(`/api/projects/${activeProjectId}`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        start_command: startCommand || null,
        project_env_vars: Object.keys(envObj).length ? JSON.stringify(envObj) : null,
        env_content: envContent || null,
        cookie_file: cookieFile || null,
        test_user: testUser || null,
        test_password: testPassword || null,
      }),
    });
    await fetchProjects();
    setSavingSettings(false);
  };

  const toggleEditLocalDirectly = async (value: boolean) => {
    setEditLocalDirectly(value);
    await fetch(apiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ edit_local_directly: value ? "true" : "false" }),
    });
  };

  const togglePushOnPass = async (value: boolean) => {
    setPushOnPass(value);
    await fetch(apiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ push_on_pass: value ? "true" : "false" }),
    });
  };

  const createProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    setCreatingProject(true);
    const res = await fetch(apiUrl("/api/projects"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newProjectName.trim(), workspace_mode: "" }),
    });
    if (res.ok) {
      const project: Project = await res.json();
      setNewProjectName("");
      setNewProjectModalOpen(false);
      setActiveProject(project.id);
    }
    setCreatingProject(false);
  };

  const deleteProject = async (projectId: number) => {
    if (projects.length <= 1) {
      alert("Cannot delete the last project.");
      return;
    }
    if (!confirm("Delete this project and all its tasks?")) return;
    await fetch(apiUrl(`/api/projects/${projectId}`), { method: "DELETE" });
    const remaining = projects.filter((p) => p.id !== projectId);
    setProjects(remaining);
    if (activeProjectId === projectId) {
      if (remaining.length > 0) {
        setActiveProject(remaining[0].id);
      } else {
        setActiveProjectIdState(null);
        setIssues([]);
      }
    }
  };

  const startRename = (projectId: number, currentName: string) => {
    setRenamingProjectId(projectId);
    setRenamingName(currentName);
  };

  const finishRename = async () => {
    if (!renamingProjectId || !renamingName.trim()) {
      setRenamingProjectId(null);
      return;
    }
    await fetch(apiUrl(`/api/projects/${renamingProjectId}`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: renamingName.trim() }),
    });
    setProjects((prev) => prev.map((p) => (p.id === renamingProjectId ? { ...p, name: renamingName.trim() } : p)));
    setRenamingProjectId(null);
  };

  // ===================== derived =====================

  const getIssuesByStatus = (status: string) => issues.filter((i) => i.status === status).sort((a, b) => b.id - a.id);

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const showGithubSync = activeProject?.workspace_mode === "github" && !!activeProject?.selected_repo;
  const modelBadge = activeProvider ? `${activeProvider} · ${modelDrafts.agent_model || "auto"}` : null;
  const workspaceBadgeText =
    activeProject?.workspace_mode === "github"
      ? activeProject.selected_repo
      : activeProject?.workspace_mode === "local"
        ? activeProject.local_path
        : null;

  // ===================== render =====================

  return (
    <div className="min-h-screen bg-neutral-900 text-neutral-100 font-sans relative">
      <div className="max-w-7xl mx-auto px-8 pt-8">
        {/* Header */}
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
                  onClick={() => {
                    setSettingsOpen(true);
                    setSettingsTab("ai");
                  }}
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
                onClick={syncGithubIssues}
                disabled={syncing}
                className="text-sm bg-neutral-800 hover:bg-neutral-700 text-neutral-300 px-3 py-2 rounded flex items-center gap-2 transition-colors border border-neutral-700 disabled:opacity-50"
              >
                <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
                Sync Issues
              </button>
            )}
            <button
              onClick={() => setIsAddModalOpen(true)}
              className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded flex items-center gap-2 text-sm transition-colors"
            >
              <Plus size={16} /> Add Task
            </button>
            <button
              onClick={() => {
                setSettingsOpen(true);
                setSettingsTab("ai");
              }}
              className="p-2 bg-neutral-800 hover:bg-neutral-700 rounded text-neutral-400 hover:text-white transition-colors"
              title="Settings"
            >
              <SettingsIcon size={20} />
            </button>
          </div>
        </header>

        {/* Project tabs */}
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
                  if (renamingProjectId !== project.id) setActiveProject(project.id);
                }}
              >
                {renamingProjectId === project.id ? (
                  <input
                    ref={renameInputRef}
                    value={renamingName}
                    onChange={(e) => setRenamingName(e.target.value)}
                    onBlur={finishRename}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") finishRename();
                      if (e.key === "Escape") setRenamingProjectId(null);
                    }}
                    className="bg-transparent border-b border-blue-500 outline-none text-white w-28 text-sm"
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      startRename(project.id, project.name);
                    }}
                  >
                    {project.name}
                  </span>
                )}
                {isActive && projects.length > 1 && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteProject(project.id);
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
            onClick={() => setNewProjectModalOpen(true)}
            className="flex items-center gap-1 px-3 py-2 text-sm text-neutral-500 hover:text-neutral-300 rounded-t-lg hover:bg-neutral-800/50 transition-colors border-t border-x border-transparent"
            title="New project"
          >
            <Plus size={14} />
          </button>
        </div>

        {/* Kanban board */}
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
                            {column === "Backlog" ? "Add a task to get started" : `No ${column.toLowerCase()} tasks`}
                          </div>
                        )}
                        {colIssues.map((issue, index) => (
                          <Draggable key={issue.id} draggableId={issue.id.toString()} index={index}>
                            {(provided, snapshot) => (
                              <div
                                ref={provided.innerRef}
                                {...provided.draggableProps}
                                {...provided.dragHandleProps}
                                onClick={() => setSelectedIssue(issue)}
                                className={`bg-neutral-800 border border-neutral-700 p-4 rounded-lg mb-3 shadow-sm cursor-pointer ${
                                  snapshot.isDragging ? "shadow-lg border-blue-500/50" : "hover:border-neutral-600"
                                } transition-colors group`}
                              >
                                <div className="flex justify-between items-start mb-2">
                                  <span className="text-xs text-neutral-500 font-mono">T-{issue.id}</span>
                                  <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                    {issue.status === "In Progress" && liveRunStates[issue.id]?.status !== "paused" && (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          pauseIssue(issue.id);
                                        }}
                                        title="Pause Agent"
                                        className="text-neutral-500 hover:text-yellow-400 p-0.5 rounded hover:bg-neutral-700"
                                      >
                                        <Pause size={13} />
                                      </button>
                                    )}
                                    {((issue.status === "In Progress" && liveRunStates[issue.id]?.status === "paused") ||
                                      (issue.status === "Failed" && issue.run_id)) && (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          resumeIssue(issue.id);
                                        }}
                                        title="Resume Agent"
                                        className="text-neutral-500 hover:text-green-400 p-0.5 rounded hover:bg-neutral-700"
                                      >
                                        <Play size={13} />
                                      </button>
                                    )}
                                    {(issue.status === "Failed" || issue.status === "Done") && (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          restartIssue(issue.id);
                                        }}
                                        title="Restart Agent"
                                        className="text-neutral-500 hover:text-blue-400 p-0.5 rounded hover:bg-neutral-700"
                                      >
                                        <RotateCcw size={13} />
                                      </button>
                                    )}
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        if (window.confirm("Delete this issue? This cannot be undone.")) {
                                          deleteIssue(issue.id);
                                        }
                                      }}
                                      title="Delete task"
                                      className="text-neutral-500 hover:text-red-400 p-0.5 rounded hover:bg-neutral-700"
                                    >
                                      <Trash2 size={13} />
                                    </button>
                                  </div>
                                </div>
                                <h3 className="text-sm font-medium text-neutral-200 mb-3">{issue.title}</h3>
                                <div className="flex items-center gap-3 text-xs">
                                   {issue.status === "In Progress" && (
                                    liveRunStates[issue.id]?.status === "paused" ? (
                                      <span className="flex items-center gap-1 text-yellow-400 bg-yellow-400/10 px-2 py-1 rounded">
                                        <Pause size={12} /> Agent paused
                                      </span>
                                    ) : (
                                      <span className="flex items-center gap-1 text-blue-400 bg-blue-400/10 px-2 py-1 rounded">
                                        <Play size={12} className="animate-pulse" /> Agent running
                                      </span>
                                    )
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
                                  {issue.status === "Backlog" && !planningIssues.has(issue.id) && issue.plan_json && (
                                    <span className="flex items-center gap-1 text-violet-400 bg-violet-400/10 px-2 py-1 rounded">
                                      <Lightbulb size={12} /> Plan ready
                                    </span>
                                  )}
                                  {issue.status === "Backlog" && !planningIssues.has(issue.id) && !issue.plan_json && (
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
      </div>

      {/* Modals */}
      {isAddModalOpen && (
        <AddTaskModal
          newTitle={newTitle}
          setNewTitle={setNewTitle}
          newDescription={newDescription}
          setNewDescription={setNewDescription}
          isSubmitting={isCreatingTask}
          onClose={() => setIsAddModalOpen(false)}
          onSubmit={addIssue}
        />
      )}

      {newProjectModalOpen && (
        <NewProjectModal
          newProjectName={newProjectName}
          setNewProjectName={setNewProjectName}
          creatingProject={creatingProject}
          onClose={() => {
            setNewProjectModalOpen(false);
            setNewProjectName("");
          }}
          onSubmit={createProject}
        />
      )}

      {noLlmGuardOpen && (
        <NoLlmGuardModal
          onDismiss={() => setNoLlmGuardOpen(false)}
          onOpenSettings={() => {
            setNoLlmGuardOpen(false);
            setSettingsOpen(true);
            setSettingsTab("ai");
          }}
        />
      )}

      <SetupWizard
        wizardStep={wizardStep}
        setWizardStep={setWizardStep}
        wizardKeys={wizardKeys}
        setWizardKeys={setWizardKeys}
        savingWizardKeys={savingWizardKeys}
        isConfigured={isConfigured}
        workspaceMode={workspaceMode}
        localPath={localPath}
        setLocalPath={setLocalPath}
        browsing={browsing}
        setBrowsing={setBrowsing}
        selectedRepo={selectedRepo}
        setSelectedRepo={(repo) => {
          setSelectedRepo(repo);
          setSelectedBranch("");
          fetchBranches(repo);
        }}
        repos={repos}
        loadingRepos={loadingRepos}
        selectedBranch={selectedBranch}
        setSelectedBranch={setSelectedBranch}
        branches={branches}
        loadingBranches={loadingBranches}
        githubAuthStatus={githubAuthStatus}
        githubAuthError={githubAuthError}
        onSelectMode={selectMode}
        onStartGithubOAuth={startGithubOAuth}
        onCancelGithubAuth={cancelGithubAuth}
        onSaveLocalPath={saveLocalPathAndFinish}
        onSaveRepo={saveRepoAndFinish}
        onSaveWizardKeys={saveWizardKeysAndContinue}
        workspaceError={workspaceError}
      />

      {settingsOpen && (
        <SettingsModal
          settingsTab={settingsTab}
          setSettingsTab={setSettingsTab}
          keyDrafts={keyDrafts}
          setKeyDrafts={setKeyDrafts}
          modelDrafts={modelDrafts}
          setModelDrafts={setModelDrafts}
          maxIterations={maxIterations}
          setMaxIterations={setMaxIterations}
          maxTokens={maxTokens}
          setMaxTokens={setMaxTokens}
          reviewerMaxToolTurns={reviewerMaxToolTurns}
          setReviewerMaxToolTurns={setReviewerMaxToolTurns}
          maxConcurrentRuns={maxConcurrentRuns}
          setMaxConcurrentRuns={setMaxConcurrentRuns}
          browserTestMaxSteps={browserTestMaxSteps}
          setBrowserTestMaxSteps={setBrowserTestMaxSteps}
          advancedModelOpen={advancedModelOpen}
          setAdvancedModelOpen={setAdvancedModelOpen}
          savingSettings={savingSettings}
          hasLlm={hasLlm}
          activeProvider={activeProvider}
          activeProject={activeProject}
          editLocalDirectly={editLocalDirectly}
          pushOnPass={pushOnPass}
          startCommand={startCommand}
          setStartCommand={setStartCommand}
          envVarRows={envVarRows}
          setEnvVarRows={setEnvVarRows}
          envContent={envContent}
          setEnvContent={setEnvContent}
          cookieFile={cookieFile}
          setCookieFile={setCookieFile}
          testUser={testUser}
          setTestUser={setTestUser}
          testPassword={testPassword}
          setTestPassword={setTestPassword}
          onSave={saveSettings}
          onSaveEnvironment={saveEnvironment}
          onClose={() => setSettingsOpen(false)}
          onConfigureWorkspace={() => {
            setSettingsOpen(false);
            setWizardStep(2);
          }}
          onToggleEditLocal={toggleEditLocalDirectly}
          onTogglePushOnPass={togglePushOnPass}
        />
      )}

      {selectedIssue && (
        <IssueDetailModal
          key={selectedIssue.id}
          issue={selectedIssue}
          projects={projects}
          liveRunStates={liveRunStates}
          runState={runState}
          runErrors={runErrors}
          runLogs={runLogs}
          loadingRunState={loadingRunState}
          planningIssues={planningIssues}
          activeTraceTab={activeTraceTab}
          setActiveTraceTab={setActiveTraceTab}
          editingPlan={editingPlan}
          setEditingPlan={setEditingPlan}
          planDraft={planDraft}
          setPlanDraft={setPlanDraft}
          followLatestRef={followLatestRef}
          onClose={() => setSelectedIssue(null)}
        />
      )}
    </div>
  );
}
