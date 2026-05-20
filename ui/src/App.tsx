import React, { useState, useEffect, useRef } from "react";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import {
  Play,
  CheckCircle2,
  AlertCircle,
  Clock,
  Trash2,
  Plus,
  Settings as SettingsIcon,
  RefreshCw,
  ArrowLeft,
  Check,
  X,
  FileText,
  Activity,
  Folder,
  Key,
  ChevronDown,
  ChevronRight,
  Zap,
} from "lucide-react";

const GithubLogo = ({ size = 24 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
  </svg>
);

interface Issue {
  id: number;
  title: string;
  description: string;
  status: string;
  run_id?: string;
  project_id?: number;
  created_at: string;
  updated_at: string;
}

interface Project {
  id: number;
  name: string;
  workspace_mode: string;
  selected_repo?: string;
  local_path?: string;
  created_at: string;
  updated_at: string;
}

interface Repo {
  full_name: string;
  name: string;
}

const COLUMNS = ["Backlog", "In Progress", "Done", "Failed"];

const API_KEY_PROVIDERS = [
  { field: "anthropic_api_key", label: "Anthropic", placeholder: "sk-ant-…" },
  { field: "openai_api_key",    label: "OpenAI",    placeholder: "sk-…" },
  { field: "gemini_api_key",    label: "Google Gemini", placeholder: "AIza…" },
  { field: "groq_api_key",      label: "Groq",      placeholder: "gsk_…" },
  { field: "mistral_api_key",   label: "Mistral",   placeholder: "…" },
];

const MODEL_ROLES = [
  { field: "orchestrator_model", label: "Orchestrator",     hint: "Goal decomposition" },
  { field: "subagent_model",     label: "Sub-agent / Coder", hint: "Code writing" },
  { field: "reviewer_model",     label: "Reviewer",          hint: "Quality gate" },
  { field: "refiner_model",      label: "Refiner",           hint: "Fix planning" },
];

export default function KanbanBoard() {
  // --- Issues & projects ---
  const [issues, setIssues] = useState<Issue[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectIdState] = useState<number | null>(null);

  // --- Add task modal ---
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");

  // --- Issue detail modal ---
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [runState, setRunState] = useState<any>(null);
  const [loadingRunState, setLoadingRunState] = useState(false);
  const [liveRunStates, setLiveRunStates] = useState<Record<number, any>>({});
  const [runErrors, setRunErrors] = useState<Record<number, string>>({});
  const [runLogs, setRunLogs] = useState<Record<number, string[]>>({});
  const [activeIterationTab, setActiveIterationTab] = useState(0);
  const followLatestRef = useRef(true);
  const activityLogRef = useRef<HTMLDivElement>(null);

  // --- First-run wizard ---
  // 0=hidden 1=AI keys (first-run) 2=workspace mode 3=auth/path 4=repo select
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardKeys, setWizardKeys] = useState<Record<string, string>>({});
  const [savingWizardKeys, setSavingWizardKeys] = useState(false);

  // --- Workspace config (shared by wizard + settings) ---
  const [workspaceMode, setWorkspaceMode] = useState<"github" | "local" | "none" | "">("");
  const [localPath, setLocalPath] = useState("");
  const [selectedRepo, setSelectedRepo] = useState("");
  const [, setHasGithubToken] = useState(false);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [githubAuthStatus, setGithubAuthStatus] = useState<"idle" | "waiting" | "error">("idle");
  const [githubAuthError, setGithubAuthError] = useState("");

  // --- AI / LLM ---
  const [hasLlm, setHasLlm] = useState(false);
  const [isConfigured, setIsConfigured] = useState(true);
  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [noLlmGuardOpen, setNoLlmGuardOpen] = useState(false);

  // --- Settings modal ---
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"ai" | "model" | "workspace" | "limits">("ai");
  const [savingSettings, setSavingSettings] = useState(false);
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [modelDrafts, setModelDrafts] = useState<Record<string, string>>({});
  const [advancedModelOpen, setAdvancedModelOpen] = useState(false);
  const [maxIterations, setMaxIterations] = useState("3");
  const [maxTokens, setMaxTokens] = useState("");
  const [editLocalDirectly, setEditLocalDirectly] = useState(false);
  const [pushOnPass, setPushOnPass] = useState(true);

  // --- Project management ---
  const [newProjectModalOpen, setNewProjectModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const [renamingProjectId, setRenamingProjectId] = useState<number | null>(null);
  const [renamingName, setRenamingName] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const activeProjectIdRef = useRef<number | null>(null);

  const apiUrl = (path: string) => (import.meta.env.DEV ? `http://localhost:8080${path}` : path);

  // ===================== helpers =====================

  const setActiveProject = (id: number) => {
    setActiveProjectIdState(id);
    activeProjectIdRef.current = id;
    localStorage.setItem("talon_active_project", String(id));
    fetchIssues(id);
  };

  // ===================== data fetching =====================

  const fetchIssues = async (projId?: number | null) => {
    const id = projId !== undefined ? projId : activeProjectId;
    const url = id != null ? apiUrl(`/api/issues?project_id=${id}`) : apiUrl("/api/issues");
    const res = await fetch(url);
    if (res.ok) setIssues(await res.json());
  };

  const fetchProjects = async (): Promise<number | null> => {
    const res = await fetch(apiUrl("/api/projects"));
    if (!res.ok) return null;
    const list: Project[] = await res.json();
    setProjects(list);
    const stored = localStorage.getItem("talon_active_project");
    const storedId = stored ? parseInt(stored) : null;
    if (storedId && list.find((p) => p.id === storedId)) {
      setActiveProjectIdState(storedId);
      activeProjectIdRef.current = storedId;
      return storedId;
    } else if (list.length > 0) {
      setActiveProjectIdState(list[0].id);
      activeProjectIdRef.current = list[0].id;
      localStorage.setItem("talon_active_project", String(list[0].id));
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
        openai_api_key:    data.openai_api_key    || "",
        gemini_api_key:    data.gemini_api_key    || "",
        groq_api_key:      data.groq_api_key      || "",
        mistral_api_key:   data.mistral_api_key   || "",
      });
      setModelDrafts({
        agent_model:        data.agent_model        || "",
        orchestrator_model: data.orchestrator_model || "",
        subagent_model:     data.subagent_model     || "",
        reviewer_model:     data.reviewer_model     || "",
        refiner_model:      data.refiner_model      || "",
      });
      setMaxIterations(data.max_iterations || "3");
      setMaxTokens(data.agent_max_tokens || "");
      setEditLocalDirectly(data.edit_local_directly === "true");
      setPushOnPass(data.push_on_pass !== "false");

      const hasToken = !!data.github_token;
      const hasRepo  = !!data.selected_repo;
      const mode: string = data.workspace_mode || "";
      const lpath: string = data.local_path || "";
      setHasGithubToken(hasToken);
      if (hasRepo) setSelectedRepo(data.selected_repo);
      if (lpath)   setLocalPath(lpath);
      if (!mode && hasToken && hasRepo) {
        await fetch(apiUrl("/api/settings"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace_mode: "github" }),
        });
        setWorkspaceMode("github");
        return;
      }
      setWorkspaceMode(mode as "github" | "local" | "none" | "");
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

  // ===================== effects =====================

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
          const exists = prev.find((i) => i.id === data.issue.id);
          if (data.issue.status === "In Progress") {
            const was = prev.find((i) => i.id === data.issue.id);
            if (!was || was.status !== "In Progress") {
              setRunLogs((logs) => ({ ...logs, [data.issue.id]: [] }));
            }
          }
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
      } else if (data.type === "github_auth_complete") {
        setGithubAuthStatus("idle");
        setHasGithubToken(true);
        fetchRepos().then(() => setWizardStep(4));
      } else if (data.type === "project_created") {
        setProjects((prev) => [...prev, data.project]);
      } else if (data.type === "project_updated") {
        setProjects((prev) => prev.map((p) => (p.id === data.project.id ? data.project : p)));
      } else if (data.type === "project_deleted") {
        setProjects((prev) => prev.filter((p) => p.id !== data.project_id));
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
      ws.onclose = () => { if (alive) reconnectTimer = setTimeout(connect, 2000); };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => { alive = false; clearTimeout(reconnectTimer); ws?.close(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const runId = selectedIssue?.run_id;
    if (runId) {
      setLoadingRunState(true);
      fetch(apiUrl(`/api/runs/${runId}`))
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => { setRunState(data); setLoadingRunState(false); })
        .catch(() => setLoadingRunState(false));
    } else {
      setRunState(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIssue?.id, selectedIssue?.run_id]);

  useEffect(() => {
    setActiveIterationTab(0);
    followLatestRef.current = true;
  }, [selectedIssue?.id]);

  useEffect(() => {
    if (!selectedIssue || !followLatestRef.current) return;
    const state = liveRunStates[selectedIssue.id];
    const count = state?.executor_results?.length ?? 0;
    if (count > 0) setActiveIterationTab(count - 1);
  }, [selectedIssue?.id, liveRunStates]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (renamingProjectId !== null && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingProjectId]);

  useEffect(() => {
    const el = activityLogRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [runLogs, selectedIssue?.id]);

  // ===================== actions =====================

  // Workspace wizard
  const selectMode = async (mode: "github" | "local" | "none") => {
    setWorkspaceMode(mode);
    await fetch(apiUrl("/api/settings"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_mode: mode }),
    });
    if (activeProjectId) {
      await fetch(apiUrl(`/api/projects/${activeProjectId}`), {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_mode: mode }),
      });
    }
    if (mode === "none") {
      setWizardStep(0);
    } else {
      setWizardStep(3);
      if (mode === "github") { setGithubAuthStatus("idle"); setGithubAuthError(""); }
    }
  };

  const startGithubOAuth = async () => {
    setGithubAuthError("");
    const res = await fetch(apiUrl("/api/auth/github/authorize"));
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setGithubAuthError(err.detail || "Failed to start GitHub auth. Is GITHUB_CLIENT_ID set?");
      return;
    }
    const data: { url: string } = await res.json();
    setGithubAuthStatus("waiting");
    if (typeof window !== "undefined" && (window as any).talon?.openExternal) {
      (window as any).talon.openExternal(data.url);
    } else {
      window.open(data.url, "_blank", "noopener,noreferrer");
    }
  };

  const saveLocalPathAndFinish = async () => {
    await fetch(apiUrl("/api/settings"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ local_path: localPath }),
    });
    if (activeProjectId) {
      await fetch(apiUrl(`/api/projects/${activeProjectId}`), {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_mode: "local", local_path: localPath }),
      });
      fetchProjects();
    }
    setWizardStep(0);
  };

  const saveRepoAndFinish = async () => {
    await fetch(apiUrl("/api/settings"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_repo: selectedRepo }),
    });
    if (activeProjectId) {
      await fetch(apiUrl(`/api/projects/${activeProjectId}`), {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_mode: "github", selected_repo: selectedRepo }),
      });
      fetchProjects();
    }
    setWizardStep(0);
  };

  const saveWizardKeysAndContinue = async () => {
    const anyKey = Object.values(wizardKeys).some((v) => v.trim());
    if (anyKey) {
      setSavingWizardKeys(true);
      await fetch(apiUrl("/api/settings"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(wizardKeys),
      });
      await fetchSettings();
      setSavingWizardKeys(false);
    }
    setWizardStep(2);
  };

  // GitHub sync
  const syncGithubIssues = async () => {
    setSyncing(true);
    const url = activeProjectId
      ? apiUrl(`/api/github/sync?project_id=${activeProjectId}`)
      : apiUrl("/api/github/sync");
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

  // Issues
  const addIssue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    const res = await fetch(apiUrl("/api/issues"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: newTitle, description: newDescription,
        status: "Backlog", project_id: activeProjectId,
      }),
    });
    if (res.ok) {
      const created: Issue = await res.json();
      setIssues((prev) => (prev.find((i) => i.id === created.id) ? prev : [created, ...prev]));
      setNewTitle(""); setNewDescription(""); setIsAddModalOpen(false);
    }
  };

  const deleteIssue = async (id: number) => {
    setIssues((prev) => prev.filter((i) => i.id !== id));
    await fetch(apiUrl(`/api/issues/${id}`), { method: "DELETE" });
  };

  const onDragEnd = async (result: any) => {
    if (!result.destination) return;
    const sourceStatus = result.source.droppableId;
    const destStatus = result.destination.droppableId;
    const issueId = parseInt(result.draggableId);
    if (sourceStatus === destStatus) return;
    if (destStatus === "In Progress" && !hasLlm) {
      setNoLlmGuardOpen(true);
      return;
    }
    setIssues((prev) => prev.map((i) => (i.id === issueId ? { ...i, status: destStatus } : i)));
    await fetch(apiUrl(`/api/issues/${issueId}`), {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: destStatus }),
    });
  };

  // Settings
  const saveSettings = async () => {
    setSavingSettings(true);
    await fetch(apiUrl("/api/settings"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...keyDrafts, ...modelDrafts,
        max_iterations: maxIterations,
        agent_max_tokens: maxTokens,
      }),
    });
    await fetchSettings();
    setSavingSettings(false);
  };

  const toggleEditLocalDirectly = async (value: boolean) => {
    setEditLocalDirectly(value);
    await fetch(apiUrl("/api/settings"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ edit_local_directly: value ? "true" : "false" }),
    });
  };

  const togglePushOnPass = async (value: boolean) => {
    setPushOnPass(value);
    await fetch(apiUrl("/api/settings"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ push_on_pass: value ? "true" : "false" }),
    });
  };

  // Projects
  const createProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    setCreatingProject(true);
    const res = await fetch(apiUrl("/api/projects"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newProjectName.trim(), workspace_mode: "none" }),
    });
    if (res.ok) {
      const project: Project = await res.json();
      setNewProjectName(""); setNewProjectModalOpen(false);
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
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: renamingName.trim() }),
    });
    setProjects((prev) =>
      prev.map((p) => (p.id === renamingProjectId ? { ...p, name: renamingName.trim() } : p))
    );
    setRenamingProjectId(null);
  };

  // ===================== derived =====================

  const getIssuesByStatus = (status: string) =>
    issues.filter((i) => i.status === status).sort((a, b) => b.id - a.id);

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const showGithubSync =
    activeProject?.workspace_mode === "github" && !!activeProject?.selected_repo;
  const modelBadge = activeProvider
    ? `${activeProvider} · ${modelDrafts.agent_model || "auto"}`
    : null;

  // ===================== render =====================

  return (
    <div className="min-h-screen bg-neutral-900 text-neutral-100 font-sans relative">
      <div className="max-w-7xl mx-auto px-8 pt-8">

        {/* ── Header ── */}
        <header className="mb-4 flex justify-between items-end">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent flex items-center gap-3">
              <img src="/favicon.svg" alt="Talon" className="w-12 h-12 flex-shrink-0" />
              Talon Board
            </h1>
            <div className="flex items-center gap-2 mt-2">
              <div className="text-neutral-400 text-sm">Autonomous Agent Tracker</div>
              {modelBadge && (
                <button
                  onClick={() => { setSettingsOpen(true); setSettingsTab("ai"); }}
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
              onClick={() => { setSettingsOpen(true); setSettingsTab("ai"); }}
              className="p-2 bg-neutral-800 hover:bg-neutral-700 rounded text-neutral-400 hover:text-white transition-colors"
              title="Settings"
            >
              <SettingsIcon size={20} />
            </button>
          </div>
        </header>

        {/* ── Project tabs ── */}
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
                onClick={() => { if (renamingProjectId !== project.id) setActiveProject(project.id); }}
              >
                {renamingProjectId === project.id ? (
                  <input
                    ref={renameInputRef}
                    value={renamingName}
                    onChange={(e) => setRenamingName(e.target.value)}
                    onBlur={finishRename}
                    onKeyDown={(e) => { if (e.key === "Enter") finishRename(); if (e.key === "Escape") setRenamingProjectId(null); }}
                    className="bg-transparent border-b border-blue-500 outline-none text-white w-28 text-sm"
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span onDoubleClick={(e) => { e.stopPropagation(); startRename(project.id, project.name); }}>
                    {project.name}
                  </span>
                )}
                {isActive && projects.length > 1 && (
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteProject(project.id); }}
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

        {/* ── Kanban board ── */}
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
                                  <button
                                    onClick={(e) => { e.stopPropagation(); deleteIssue(issue.id); }}
                                    className="text-neutral-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                                  >
                                    <Trash2 size={14} />
                                  </button>
                                </div>
                                <h3 className="text-sm font-medium text-neutral-200 mb-3">{issue.title}</h3>
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
                                  {issue.status === "Backlog" && (
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

      {/* ══════════════════════════════════════
          Add Task Modal
      ══════════════════════════════════════ */}
      {isAddModalOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-xl w-full max-w-lg shadow-2xl">
            <h2 className="text-xl font-bold mb-4">Add New Task</h2>
            <form onSubmit={addIssue} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Title</label>
                <input
                  type="text" value={newTitle} onChange={(e) => setNewTitle(e.target.value)}
                  autoFocus placeholder="e.g., Create a new landing page"
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Description (Optional)</label>
                <textarea
                  value={newDescription} onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Provide any additional context or acceptance criteria for the agent..."
                  rows={5}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all resize-none"
                />
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button type="button" onClick={() => setIsAddModalOpen(false)} className="px-4 py-2 text-sm text-neutral-400 hover:text-white">Cancel</button>
                <button type="submit" disabled={!newTitle.trim()} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded text-sm transition-colors">
                  Create Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          New Project Modal
      ══════════════════════════════════════ */}
      {newProjectModalOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-xl w-full max-w-sm shadow-2xl">
            <h2 className="text-lg font-bold mb-4">New Project</h2>
            <form onSubmit={createProject} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Project name</label>
                <input
                  type="text" value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)}
                  autoFocus placeholder="My App"
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
              </div>
              <p className="text-xs text-neutral-500">You can configure the workspace (GitHub repo or local folder) in Settings after creation.</p>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => { setNewProjectModalOpen(false); setNewProjectName(""); }} className="px-4 py-2 text-sm text-neutral-400 hover:text-white">Cancel</button>
                <button type="submit" disabled={!newProjectName.trim() || creatingProject} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded text-sm transition-colors flex items-center gap-2">
                  {creatingProject ? <RefreshCw size={14} className="animate-spin" /> : null}
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          No-LLM Guard Modal
      ══════════════════════════════════════ */}
      {noLlmGuardOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-neutral-900 border border-amber-500/30 p-6 rounded-xl w-full max-w-sm shadow-2xl text-center">
            <div className="w-12 h-12 rounded-full bg-amber-500/10 flex items-center justify-center mx-auto mb-4">
              <Key size={24} className="text-amber-400" />
            </div>
            <h2 className="text-lg font-bold mb-2">No AI provider configured</h2>
            <p className="text-sm text-neutral-400 mb-6">Add an API key in Settings before running tasks.</p>
            <div className="flex gap-3 justify-center">
              <button onClick={() => setNoLlmGuardOpen(false)} className="px-4 py-2 text-sm text-neutral-400 hover:text-white">Dismiss</button>
              <button
                onClick={() => { setNoLlmGuardOpen(false); setSettingsOpen(true); setSettingsTab("ai"); }}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm transition-colors"
              >
                Open Settings
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          First-Run Wizard
      ══════════════════════════════════════ */}
      {wizardStep > 0 && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
          <div className="bg-neutral-900 border border-neutral-800 p-8 rounded-2xl w-full max-w-md shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-32 bg-blue-500/10 blur-3xl rounded-full pointer-events-none" />

            {/* Step 1: AI Provider (first-run) */}
            {wizardStep === 1 && (
              <div className="relative">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center">
                    <Key size={16} className="text-blue-400" />
                  </div>
                  <h2 className="text-2xl font-bold">Add an API key</h2>
                </div>
                <p className="text-sm text-neutral-400 mb-6">
                  Talon needs access to at least one AI provider to run tasks.
                </p>
                <div className="space-y-3 mb-6">
                  {API_KEY_PROVIDERS.map(({ field, label, placeholder }) => (
                    <div key={field}>
                      <label className="block text-xs font-medium text-neutral-400 mb-1">{label}</label>
                      <input
                        type="password"
                        value={wizardKeys[field] || ""}
                        onChange={(e) => setWizardKeys((prev) => ({ ...prev, [field]: e.target.value }))}
                        placeholder={placeholder}
                        className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                      />
                    </div>
                  ))}
                </div>
                <div className="flex justify-between items-center">
                  <button
                    onClick={() => setWizardStep(2)}
                    className="text-sm text-neutral-500 hover:text-neutral-300 transition-colors"
                  >
                    Skip for now
                  </button>
                  <button
                    onClick={saveWizardKeysAndContinue}
                    disabled={savingWizardKeys || !Object.values(wizardKeys).some((v) => v.trim())}
                    className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                  >
                    {savingWizardKeys ? <RefreshCw size={14} className="animate-spin" /> : null}
                    Continue →
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: Choose workspace mode */}
            {wizardStep === 2 && (
              <div className="relative">
                {!isConfigured && (
                  <button onClick={() => setWizardStep(1)} className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors">
                    <ArrowLeft size={14} /> Back
                  </button>
                )}
                <h2 className="text-2xl font-bold mb-2">Workspace Setup</h2>
                <p className="text-sm text-neutral-400 mb-6">Where should Talon work when running tasks?</p>
                <div className="space-y-3">
                  <button onClick={() => selectMode("github")} className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-blue-500/60 bg-neutral-800/50 hover:bg-blue-500/5 transition-all">
                    <div className="flex items-center gap-3 mb-1"><GithubLogo size={18} /><span className="font-medium text-sm">GitHub Repository</span></div>
                    <p className="text-xs text-neutral-500 ml-7">Clone a repo from GitHub and work in an isolated branch per run.</p>
                  </button>
                  <button onClick={() => selectMode("local")} className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-blue-500/60 bg-neutral-800/50 hover:bg-blue-500/5 transition-all">
                    <div className="flex items-center gap-3 mb-1"><Folder size={18} /><span className="font-medium text-sm">Local Directory</span></div>
                    <p className="text-xs text-neutral-500 ml-7">Point Talon at a folder on this machine.</p>
                  </button>
                  <button onClick={() => selectMode("none")} className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-neutral-600 bg-neutral-800/50 hover:bg-neutral-800 transition-all">
                    <div className="flex items-center gap-3 mb-1"><span className="text-neutral-400 font-medium text-sm">No Workspace</span></div>
                    <p className="text-xs text-neutral-500">Run tasks in a fresh empty workspace each time.</p>
                  </button>
                </div>
                <button onClick={() => setWizardStep(0)} className="mt-5 text-sm text-neutral-500 hover:text-neutral-300 transition-colors">
                  {isConfigured ? "Cancel" : "Skip for now"}
                </button>
              </div>
            )}

            {/* Step 3a: GitHub device flow */}
            {wizardStep === 3 && workspaceMode === "github" && (
              <div className="relative">
                <button onClick={() => setWizardStep(2)} className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors">
                  <ArrowLeft size={14} /> Back
                </button>
                <h2 className="text-2xl font-bold mb-2 flex items-center gap-2"><GithubLogo size={22} /> Connect GitHub</h2>
                <p className="text-sm text-neutral-400 mb-6">Authorize Talon via GitHub's device flow — no passwords or tokens to copy.</p>
                {githubAuthError && (
                  <div className="mb-4 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">{githubAuthError}</div>
                )}
                {githubAuthStatus === "idle" && (
                  <button onClick={startGithubOAuth} className="w-full py-3 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-colors">
                    <GithubLogo size={16} /> Login with GitHub
                  </button>
                )}
                {githubAuthStatus === "waiting" && (
                  <div className="space-y-4">
                    <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-5 text-center">
                      <p className="text-sm text-neutral-400">A browser window has opened for GitHub authorization.</p>
                      <p className="text-xs text-neutral-500 mt-2">Once you approve, this window will advance automatically.</p>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-neutral-400"><RefreshCw size={14} className="animate-spin shrink-0" /> Waiting for authorization…</div>
                    <button onClick={() => setGithubAuthStatus("idle")} className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors">Cancel</button>
                  </div>
                )}
              </div>
            )}

            {/* Step 3b: Local directory */}
            {wizardStep === 3 && workspaceMode === "local" && (
              <div className="relative">
                <button onClick={() => setWizardStep(2)} className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors">
                  <ArrowLeft size={14} /> Back
                </button>
                <h2 className="text-2xl font-bold mb-2 flex items-center gap-2"><Folder size={22} /> Local Directory</h2>
                <p className="text-sm text-neutral-400 mb-6">Enter the absolute path to the project folder on this machine.</p>
                <div className="mb-6">
                  <label className="block text-sm font-medium text-neutral-300 mb-2">Project Path</label>
                  <div className="flex gap-2">
                    <input
                      type="text" value={localPath} onChange={(e) => setLocalPath(e.target.value)}
                      autoFocus placeholder="/Users/you/projects/my-app"
                      className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                    <button
                      type="button"
                      onClick={async () => {
                        setBrowsing(true);
                        try {
                          const res = await fetch(apiUrl("/api/local/browse"));
                          if (res.ok) { const d = await res.json(); if (d.path) setLocalPath(d.path); }
                        } finally { setBrowsing(false); }
                      }}
                      disabled={browsing}
                      className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-lg text-sm text-neutral-300 transition-colors whitespace-nowrap flex items-center gap-2 disabled:opacity-50"
                    >
                      {browsing ? <RefreshCw size={14} className="animate-spin" /> : <Folder size={14} />}
                      {browsing ? "Opening…" : "Browse…"}
                    </button>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <button onClick={() => setWizardStep(0)} className="text-sm text-neutral-500 hover:text-neutral-300 transition-colors">Cancel</button>
                  <button
                    onClick={saveLocalPathAndFinish}
                    disabled={!localPath.trim()}
                    className="px-5 py-2.5 bg-green-600 hover:bg-green-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ml-auto"
                  >
                    Save <Check size={16} />
                  </button>
                </div>
              </div>
            )}

            {/* Step 4: GitHub repo selection */}
            {wizardStep === 4 && (
              <div className="relative">
                <button onClick={() => setWizardStep(3)} className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors">
                  <ArrowLeft size={14} /> Back
                </button>
                <h2 className="text-2xl font-bold mb-2">Select Repository</h2>
                <p className="text-sm text-neutral-400 mb-6">Choose the codebase you want Talon to work on.</p>
                <div className="mb-6">
                  <label className="block text-sm font-medium text-neutral-300 mb-2">Target Repository</label>
                  <div className="relative">
                    <select
                      value={selectedRepo}
                      onChange={(e) => setSelectedRepo(e.target.value)}
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all appearance-none text-neutral-200"
                    >
                      <option value="">Select a repository…</option>
                      {repos.map((r) => <option key={r.full_name} value={r.full_name}>{r.full_name}</option>)}
                    </select>
                    <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none">
                      <svg className="w-4 h-4 text-neutral-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                    </div>
                  </div>
                  {loadingRepos && <p className="text-xs text-blue-400 mt-2 animate-pulse">Loading your repositories…</p>}
                </div>
                <div className="flex justify-between items-center mt-8">
                  <button onClick={() => setWizardStep(0)} className="text-sm text-neutral-500 hover:text-neutral-300 transition-colors">Cancel</button>
                  <button
                    onClick={saveRepoAndFinish}
                    disabled={!selectedRepo}
                    className="px-5 py-2.5 bg-green-600 hover:bg-green-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ml-auto"
                  >
                    Complete Setup <Check size={16} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          Settings Modal
      ══════════════════════════════════════ */}
      {settingsOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-lg shadow-2xl flex flex-col max-h-[90vh]">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-neutral-800">
              <h2 className="text-lg font-bold flex items-center gap-2"><SettingsIcon size={18} className="text-neutral-400" /> Settings</h2>
              <button onClick={() => setSettingsOpen(false)} className="p-1.5 text-neutral-500 hover:text-white bg-neutral-800 hover:bg-neutral-700 rounded-lg transition-colors"><X size={18} /></button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-neutral-800">
              {(["ai", "model", "workspace", "limits"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setSettingsTab(tab)}
                  className={`px-5 py-3 text-sm font-medium transition-colors capitalize ${
                    settingsTab === tab
                      ? "border-b-2 border-blue-500 text-white"
                      : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  {tab === "ai" ? "AI Provider" : tab === "model" ? "Model" : tab === "workspace" ? "Workspace" : "Limits"}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">

              {/* AI Provider tab */}
              {settingsTab === "ai" && (
                <div className="space-y-4">
                  <p className="text-xs text-neutral-500">Add at least one API key to enable agent runs. Existing keys are shown masked.</p>
                  {API_KEY_PROVIDERS.map(({ field, label, placeholder }) => (
                    <div key={field}>
                      <label className="block text-sm font-medium text-neutral-300 mb-1">{label}</label>
                      <div className="flex gap-2">
                        <input
                          type="password"
                          value={keyDrafts[field] || ""}
                          onChange={(e) => setKeyDrafts((prev) => ({ ...prev, [field]: e.target.value }))}
                          placeholder={keyDrafts[field]?.startsWith("***") ? keyDrafts[field] : placeholder}
                          className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                        />
                        {keyDrafts[field] && (
                          <button
                            onClick={() => setKeyDrafts((prev) => ({ ...prev, [field]: "" }))}
                            className="px-3 py-2 text-xs text-neutral-500 hover:text-red-400 bg-neutral-800 border border-neutral-700 rounded-lg transition-colors"
                            title="Clear key"
                          >
                            Clear
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                  {hasLlm && activeProvider && (
                    <div className="text-xs text-green-400 bg-green-400/10 border border-green-400/20 rounded-lg p-3 flex items-center gap-2">
                      <Check size={12} />
                      Active provider: <strong>{activeProvider}</strong>
                    </div>
                  )}
                </div>
              )}

              {/* Model tab */}
              {settingsTab === "model" && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-neutral-300 mb-1">Global model</label>
                    <input
                      type="text"
                      value={modelDrafts.agent_model || ""}
                      onChange={(e) => setModelDrafts((prev) => ({ ...prev, agent_model: e.target.value }))}
                      placeholder="Leave blank for Auto (recommended)"
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                    <p className="text-xs text-neutral-600 mt-1">Example: <code>anthropic/claude-opus-4-7</code> or <code>gemini/gemini-2.0-flash</code></p>
                  </div>

                  <button
                    onClick={() => setAdvancedModelOpen((v) => !v)}
                    className="flex items-center gap-2 text-sm text-neutral-400 hover:text-neutral-200 transition-colors"
                  >
                    {advancedModelOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    Advanced model settings (per-role)
                  </button>

                  {advancedModelOpen && (
                    <div className="space-y-3 pl-4 border-l border-neutral-800">
                      <p className="text-xs text-neutral-500">Override the model for each agent role. Leave blank to use the global model (or Auto).</p>
                      {MODEL_ROLES.map(({ field, label, hint }) => (
                        <div key={field}>
                          <label className="block text-xs font-medium text-neutral-400 mb-1">
                            {label} <span className="text-neutral-600">— {hint}</span>
                          </label>
                          <input
                            type="text"
                            value={modelDrafts[field] || ""}
                            onChange={(e) => setModelDrafts((prev) => ({ ...prev, [field]: e.target.value }))}
                            placeholder="blank = use global / Auto"
                            className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                          />
                        </div>
                      ))}
                      <p className="text-xs text-neutral-600">Per-workspace model overrides coming in v2.</p>
                    </div>
                  )}
                </div>
              )}

              {/* Workspace tab */}
              {settingsTab === "workspace" && (
                <div className="space-y-4">
                  {activeProject ? (
                    <>
                      <div className="bg-neutral-800/50 border border-neutral-700 rounded-xl p-4">
                        <div className="text-xs text-neutral-500 mb-1">Current project</div>
                        <div className="font-medium text-neutral-200">{activeProject.name}</div>
                        <div className="mt-3 space-y-1 text-sm">
                          <div className="flex items-center gap-2 text-neutral-400">
                            <span className="text-neutral-600">Mode:</span>
                            <span className="capitalize">{activeProject.workspace_mode || "none"}</span>
                          </div>
                          {activeProject.workspace_mode === "github" && activeProject.selected_repo && (
                            <div className="flex items-center gap-2 text-neutral-400">
                              <GithubLogo size={13} />
                              <span>{activeProject.selected_repo}</span>
                            </div>
                          )}
                          {activeProject.workspace_mode === "local" && activeProject.local_path && (
                            <div className="flex items-center gap-2 text-neutral-400">
                              <Folder size={13} />
                              <span className="font-mono text-xs">{activeProject.local_path}</span>
                            </div>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => { setSettingsOpen(false); setWizardStep(2); }}
                        className="w-full py-2.5 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-lg text-sm text-neutral-300 transition-colors"
                      >
                        Configure workspace…
                      </button>
                      <p className="text-xs text-neutral-600">Changes the workspace for the current project tab.</p>
                    </>
                  ) : (
                    <p className="text-sm text-neutral-500">No active project selected.</p>
                  )}

                  {/* Behaviour toggles */}
                  <div className="space-y-3 pt-2 border-t border-neutral-800">
                    {activeProject?.workspace_mode === "local" && (
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <div className="text-sm font-medium text-neutral-300">Edit local files directly</div>
                          <div className="text-xs text-neutral-500 mt-0.5">Agents edit the real files on disk — no isolated copy or worktree</div>
                        </div>
                        <button
                          onClick={() => toggleEditLocalDirectly(!editLocalDirectly)}
                          className={`relative flex-shrink-0 inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${editLocalDirectly ? "bg-blue-600" : "bg-neutral-700"}`}
                          aria-pressed={editLocalDirectly}
                        >
                          <span className={`inline-block h-3 w-3 rounded-full bg-white shadow transition-transform ${editLocalDirectly ? "translate-x-5" : "translate-x-1"}`} />
                        </button>
                      </div>
                    )}
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <div className="text-sm font-medium text-neutral-300">Push changes & open PR on pass</div>
                        <div className="text-xs text-neutral-500 mt-0.5">Commit, push branch, and create a GitHub PR when a run succeeds</div>
                      </div>
                      <button
                        onClick={() => togglePushOnPass(!pushOnPass)}
                        className={`relative flex-shrink-0 inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${pushOnPass ? "bg-blue-600" : "bg-neutral-700"}`}
                        aria-pressed={pushOnPass}
                      >
                        <span className={`inline-block h-3 w-3 rounded-full bg-white shadow transition-transform ${pushOnPass ? "translate-x-5" : "translate-x-1"}`} />
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Limits tab */}
              {settingsTab === "limits" && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-neutral-300 mb-1">Max iterations</label>
                    <input
                      type="number" min={1} max={10}
                      value={maxIterations}
                      onChange={(e) => setMaxIterations(e.target.value)}
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                    <p className="text-xs text-neutral-600 mt-1">How many executor→reviewer→refiner cycles before giving up (default: 3)</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-neutral-300 mb-1">Max tokens per agent call</label>
                    <input
                      type="number" min={1024}
                      value={maxTokens}
                      onChange={(e) => setMaxTokens(e.target.value)}
                      placeholder="Default (model limit)"
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-neutral-800 flex justify-end gap-3">
              <button onClick={() => setSettingsOpen(false)} className="px-4 py-2 text-sm text-neutral-400 hover:text-white">Cancel</button>
              {settingsTab !== "workspace" && (
                <button
                  onClick={saveSettings}
                  disabled={savingSettings}
                  className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                >
                  {savingSettings ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                  Save settings
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════
          Issue Detail Modal
      ══════════════════════════════════════ */}
      {selectedIssue &&
        (() => {
          const activeRunState = liveRunStates[selectedIssue.id] || runState;
          const runError = runErrors[selectedIssue.id];
          const isLive = selectedIssue.status === "In Progress" && !!liveRunStates[selectedIssue.id];
          return (
            <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
              <div className="bg-neutral-900 border border-neutral-800 p-8 rounded-2xl w-full max-w-4xl shadow-2xl relative overflow-hidden flex flex-col h-[90vh]">
                <button
                  onClick={() => setSelectedIssue(null)}
                  className="absolute top-4 right-4 p-2 text-neutral-500 hover:text-white bg-neutral-800 hover:bg-neutral-700 rounded-lg transition-colors z-10"
                >
                  <X size={20} />
                </button>

                <div className="flex items-start gap-4 mb-6 pr-12">
                  <div className="bg-neutral-800 p-3 rounded-xl border border-neutral-700 text-blue-400">
                    <FileText size={24} />
                  </div>
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-xs font-mono text-neutral-500 bg-neutral-950 px-2 py-1 rounded">T-{selectedIssue.id}</span>
                      <span className={`text-xs px-2 py-1 rounded-full flex items-center gap-1 ${
                        selectedIssue.status === "Done" ? "bg-green-500/10 text-green-400 border border-green-500/20"
                        : selectedIssue.status === "Failed" ? "bg-red-500/10 text-red-400 border border-red-500/20"
                        : selectedIssue.status === "In Progress" ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                        : "bg-neutral-800 text-neutral-400 border border-neutral-700"
                      }`}>
                        {selectedIssue.status === "In Progress" && <Play size={10} className="animate-pulse" />}
                        {selectedIssue.status === "Done" && <CheckCircle2 size={10} />}
                        {selectedIssue.status === "Failed" && <AlertCircle size={10} />}
                        {selectedIssue.status}
                      </span>
                    </div>
                    <h2 className="text-2xl font-bold text-white">{selectedIssue.title}</h2>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto pr-2 space-y-6">
                  {selectedIssue.description && (
                    <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl p-5">
                      <h3 className="text-sm font-medium text-neutral-400 mb-3 uppercase tracking-wider">Description</h3>
                      <div className="text-neutral-300 text-sm whitespace-pre-wrap">{selectedIssue.description}</div>
                    </div>
                  )}

                  {(runError || activeRunState?.error) && (
                    <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-sm text-red-400">
                      <div className="font-medium mb-1">Agent error</div>
                      <pre className="text-xs font-mono whitespace-pre-wrap text-red-300/80">{runError || activeRunState?.error}</pre>
                    </div>
                  )}

                  {selectedIssue.status === "In Progress" && !activeRunState && !runError && (() => {
                    const earlyLogs = runLogs[selectedIssue.id] ?? [];
                    return earlyLogs.length > 0 ? (
                      <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                        <div className="bg-neutral-900 border-b border-neutral-800 p-4 flex items-center gap-2">
                          <Activity size={16} className="text-blue-400" />
                          <span className="text-sm font-medium text-neutral-300">Execution Trace</span>
                          <span className="flex items-center gap-1 text-xs text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded-full ml-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                            Live
                          </span>
                        </div>
                        <div
                          ref={activityLogRef}
                          className="bg-black/30 px-4 py-3 font-mono text-xs max-h-44 overflow-y-auto overflow-x-hidden"
                        >
                          {earlyLogs.map((line, i) => (
                            <div key={i} className="leading-relaxed flex gap-2 min-w-0">
                              <span className="text-neutral-700 shrink-0 select-none">[server]</span>
                              <span className={`break-words min-w-0 ${
                                line.startsWith("===") ? "text-blue-500" :
                                line.startsWith("->") ? "text-cyan-500" :
                                line.startsWith("Files modified:") ? "text-green-500" :
                                line.includes("modified:") ? "text-green-600" :
                                "text-neutral-400"
                              }`}>{line}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-3 p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl text-blue-400 text-sm">
                        <RefreshCw size={16} className="animate-spin shrink-0" />
                        Agent is starting up — logs will appear here shortly...
                      </div>
                    );
                  })()}

                  {loadingRunState && !activeRunState && (
                    <div className="flex items-center justify-center p-12 text-neutral-500 gap-3">
                      <RefreshCw size={20} className="animate-spin" /> Fetching agent logs...
                    </div>
                  )}

                  {activeRunState &&
                    (() => {
                      const iterations: any[] = activeRunState.executor_results ?? [];
                      const totalIterations = iterations.length;
                      const clampedTab = totalIterations === 0 ? 0 : Math.min(activeIterationTab, totalIterations - 1);
                      const currentIteration = iterations[clampedTab];
                      const currentReview = activeRunState.review_results?.[clampedTab];
                      const currentRefinement = activeRunState.refinement_results?.[clampedTab];
                      const logs = runLogs[selectedIssue.id] ?? [];
                      return (
                        <div className="space-y-4">
                          <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                            <div className="bg-neutral-900 border-b border-neutral-800 p-4 flex justify-between items-center">
                              <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                                <Activity size={16} className="text-blue-400" />
                                Execution Trace
                                {isLive && (
                                  <span className="flex items-center gap-1 text-xs text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded-full ml-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                                    Live
                                  </span>
                                )}
                              </h3>
                              <span className="text-xs text-neutral-500 font-mono">Run: {activeRunState.run_id}</span>
                            </div>

                            {logs.length > 0 && (
                              <div
                                ref={activityLogRef}
                                className="border-b border-neutral-800/50 bg-black/30 px-4 py-3 font-mono text-xs max-h-44 overflow-y-auto overflow-x-hidden"
                              >
                                {logs.map((line, i) => (
                                  <div key={i} className="leading-relaxed flex gap-2 min-w-0">
                                    <span className="text-neutral-700 shrink-0 select-none">[server]</span>
                                    <span className={`break-words min-w-0 ${
                                      line.startsWith("===") ? "text-blue-500" :
                                      line.startsWith("->") ? "text-cyan-500" :
                                      line.startsWith("Files modified:") ? "text-green-500" :
                                      line.includes("modified:") ? "text-green-600" :
                                      "text-neutral-400"
                                    }`}>{line}</span>
                                  </div>
                                ))}
                              </div>
                            )}

                            {totalIterations === 0 ? (
                              <div className="p-8 text-center text-neutral-500 text-sm flex flex-col items-center gap-3">
                                {logs.length === 0 ? (
                                  <>
                                    <RefreshCw size={20} className="animate-spin text-blue-500" />
                                    Agent initializing — decomposing goal into subtasks...
                                  </>
                                ) : (
                                  <span className="text-neutral-600 text-xs">Waiting for subtasks to complete…</span>
                                )}
                              </div>
                            ) : (
                              <>
                                <div className="flex border-b border-neutral-800 bg-neutral-900/30 overflow-x-auto">
                                  {iterations.map((_: any, idx: number) => {
                                    const review = activeRunState.review_results?.[idx];
                                    const isActive = clampedTab === idx;
                                    const isPassing = review?.verdict === "pass";
                                    const isFailing = review && review.verdict !== "pass";
                                    const isRunning = isLive && idx === totalIterations - 1 && !review;
                                    return (
                                      <button
                                        key={idx}
                                        onClick={() => { setActiveIterationTab(idx); followLatestRef.current = idx === totalIterations - 1; }}
                                        className={`flex items-center gap-2 px-4 py-3 text-xs font-medium whitespace-nowrap border-b-2 transition-colors ${
                                          isActive ? "border-blue-500 text-white bg-neutral-800/50" : "border-transparent text-neutral-500 hover:text-neutral-300 hover:bg-neutral-800/30"
                                        }`}
                                      >
                                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isPassing ? "bg-green-400" : isFailing ? "bg-amber-400" : isRunning ? "bg-blue-400 animate-pulse" : "bg-neutral-600"}`} />
                                        Iteration {idx + 1}
                                        {isRunning && <RefreshCw size={10} className="animate-spin text-neutral-500" />}
                                      </button>
                                    );
                                  })}
                                </div>

                                {currentIteration && (
                                  <div>
                                    {currentIteration.subtasks?.length > 0 && (
                                      <div className="p-4 border-b border-neutral-800/50">
                                        <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">Subagents</div>
                                        <div className="space-y-1.5">
                                          {currentIteration.subtasks.map((st: any, si: number) => {
                                            const stResult = currentIteration.subtask_results?.[si];
                                            return (
                                              <div key={si} className="flex items-start gap-2 text-xs text-neutral-400">
                                                <span className={`mt-0.5 shrink-0 ${stResult?.success ? "text-green-400" : stResult ? "text-red-400" : "text-neutral-600"}`}>
                                                  {stResult ? (stResult.success ? "✓" : "✗") : "○"}
                                                </span>
                                                <span>{st.description}</span>
                                              </div>
                                            );
                                          })}
                                        </div>
                                      </div>
                                    )}

                                    <div className="p-4 border-b border-neutral-800/50">
                                      <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">Output</div>
                                      <div className="bg-neutral-900 p-4 rounded border border-neutral-800/50 overflow-x-auto">
                                        <pre className="text-xs text-neutral-400 font-mono whitespace-pre-wrap">{currentIteration.aggregated_output || "No output yet"}</pre>
                                      </div>
                                      {isLive && clampedTab === totalIterations - 1 && !currentReview && (
                                        <div className="mt-3 flex items-center gap-2 text-xs text-neutral-500">
                                          <RefreshCw size={12} className="animate-spin" /> Waiting for reviewer...
                                        </div>
                                      )}
                                    </div>

                                    {currentReview && (
                                      <div className="p-4 border-b border-neutral-800/50">
                                        <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">Review</div>
                                        <div className="flex items-center gap-3 mb-3">
                                          <span className={`text-xs px-2 py-1 rounded font-medium ${currentReview.verdict === "pass" ? "bg-green-500/10 text-green-400" : "bg-amber-500/10 text-amber-400"}`}>
                                            {currentReview.verdict.toUpperCase()}
                                          </span>
                                          <span className="text-xs text-neutral-500">Score: {Math.round((currentReview.score ?? 0) * 10)}/10</span>
                                        </div>
                                        {currentReview.summary && (
                                          <div className="bg-neutral-900 p-4 rounded border border-neutral-800/50 mb-3">
                                            <p className="text-xs text-neutral-300">{currentReview.summary}</p>
                                          </div>
                                        )}
                                        {currentReview.blocking_issues?.length > 0 && (
                                          <div className="text-xs text-red-400 space-y-1">
                                            {currentReview.blocking_issues.map((issue: string, bi: number) => (
                                              <div key={bi} className="flex items-start gap-1"><span className="shrink-0">✗</span> {issue}</div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    {currentRefinement && (
                                      <div className="p-4 bg-amber-500/5">
                                        <div className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-3">Refinement plan</div>
                                        <div className="text-xs text-neutral-400 space-y-1.5">
                                          {currentRefinement.changes_planned?.map((c: string, ci: number) => (
                                            <div key={ci} className="flex items-start gap-1.5"><span className="shrink-0 text-amber-500">→</span> {c}</div>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </>
                            )}
                          </div>

                          {activeRunState.video_path && (
                            <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                              <div className="bg-neutral-900 border-b border-neutral-800 p-4">
                                <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                                  <Play size={16} className="text-blue-400" /> Video Verification
                                </h3>
                              </div>
                              <div className="p-4 flex justify-center bg-black">
                                <video controls className="max-w-full max-h-[400px] rounded border border-neutral-800" src={apiUrl(`/api/runs/${activeRunState.run_id}/video`)}>
                                  Your browser does not support the video tag.
                                </video>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })()}

                  {!activeRunState && !runError && !loadingRunState && selectedIssue.run_id && (
                    <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
                      <div className="mb-2">No logs found for run <code className="bg-neutral-800 px-1 py-0.5 rounded text-xs">{selectedIssue.run_id}</code></div>
                      <div className="text-xs">Check the server terminal for error details.</div>
                    </div>
                  )}

                  {!activeRunState && !runError && !loadingRunState && !selectedIssue.run_id && selectedIssue.status !== "In Progress" && (
                    <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
                      Agent has not started yet. Drag to "In Progress" to begin execution.
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })()}
    </div>
  );
}
