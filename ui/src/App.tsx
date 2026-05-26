import React, { useState, useEffect, useRef } from "react";
import type { DropResult } from "@hello-pangea/dnd";

import { apiUrl } from "./utils";
import type { Issue, PlanResult, RunState } from "./types";
import { useAppData } from "./hooks/useAppData";
import { useWebSocket } from "./hooks/useWebSocket";
import { AppHeader } from "./components/AppHeader";
import { KanbanBoard } from "./components/KanbanBoard";
import { ProjectTabs } from "./components/ProjectTabs";
import { AddTaskModal } from "./components/AddTaskModal";
import { NewProjectModal } from "./components/NewProjectModal";
import { NoLlmGuardModal } from "./components/NoLlmGuardModal";
import { SetupWizard } from "./components/SetupWizard";
import { SettingsModal } from "./components/SettingsModal";
import type { EnvVarRow } from "./components/SettingsModal";
import { IssueDetailModal } from "./components/IssueDetailModal";

export default function App() {
  const data = useAppData();
  const {
    issues, setIssues, projects, setProjects,
    activeProjectId, activeProjectIdRef, setActiveProject,
    repos, loadingRepos, fetchRepos,
    branches, loadingBranches, selectedBranch, setSelectedBranch,
    workspaceMode, setWorkspaceMode,
    localPath, setLocalPath,
    selectedRepo, setSelectedRepo,
    browsing, setBrowsing,
    hasLlm, isConfigured, activeProvider,
    keyDrafts, setKeyDrafts,
    modelDrafts, setModelDrafts,
    maxIterations, setMaxIterations,
    maxTokens, setMaxTokens,
    reviewerMaxToolTurns, setReviewerMaxToolTurns,
    editLocalDirectly, setEditLocalDirectly,
    pushOnPass, setPushOnPass,
    wizardStep, setWizardStep,
    wizardKeys, setWizardKeys,
    savingWizardKeys, setSavingWizardKeys,
    fetchIssues, fetchSettings, fetchBranches,
  } = data;

  // --- Add task modal ---
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [isCreatingTask, setIsCreatingTask] = useState(false);

  // --- Issue detail modal ---
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [runState, setRunState] = useState<RunState | null>(null);
  const [loadingRunState, setLoadingRunState] = useState(false);
  const [activeTraceTab, setActiveTraceTab] = useState<"plan" | number>("plan");
  const followLatestRef = useRef(true);
  const [editingPlan, setEditingPlan] = useState(false);
  const [planDraft, setPlanDraft] = useState<PlanResult | null>(null);

  // --- Workspace error (invalid / stale path detected server-side) ---
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);

  // --- GitHub OAuth ---
  const [githubAuthStatus, setGithubAuthStatus] = useState<"idle" | "waiting" | "error">("idle");
  const [githubAuthError, setGithubAuthError] = useState("");
  const githubPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- LLM guard ---
  const [noLlmGuardOpen, setNoLlmGuardOpen] = useState(false);

  // --- Settings modal ---
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"ai" | "model" | "workspace" | "environment" | "limits">("ai");
  const [savingSettings, setSavingSettings] = useState(false);
  const [advancedModelOpen, setAdvancedModelOpen] = useState(false);
  const [maxConcurrentRuns, setMaxConcurrentRuns] = useState("3");
  const [browserTestMaxSteps, setBrowserTestMaxSteps] = useState("20");

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
  const [syncing, setSyncing] = useState(false);

  // --- WebSocket ---
  const stopGithubPoll = () => {
    if (githubPollRef.current) {
      clearInterval(githubPollRef.current);
      githubPollRef.current = null;
    }
  };

  const { liveRunStates, runErrors, runLogs, planningIssues } = useWebSocket(
    activeProjectIdRef,
    fetchIssues,
    {
      onIssueUpdated: (issue) => {
        setIssues((prev) => {
          const exists = prev.find((i) => i.id === issue.id);
          if (exists) return prev.map((i) => (i.id === issue.id ? issue : i));
          return [issue, ...prev];
        });
      },
      onIssueDeleted: (issueId) => setIssues((prev) => prev.filter((i) => i.id !== issueId)),
      onSelectedIssueSync: (issue) =>
        setSelectedIssue((prev) => (prev?.id === issue.id ? issue : prev)),
      onGithubAuthComplete: () => {
        stopGithubPoll();
        setGithubAuthStatus("idle");
        fetchRepos().then(() => setWizardStep(4));
      },
      onProjectCreated: (project) => setProjects((prev) => [...prev, project]),
      onProjectUpdated: (project) =>
        setProjects((prev) => prev.map((p) => (p.id === project.id ? project : p))),
      onProjectDeleted: (projectId) =>
        setProjects((prev) => prev.filter((p) => p.id !== projectId)),
      onWorkspaceInvalid: (data) => {
        if (data.issue_id) {
          setIssues((prev) =>
            prev.map((i) => (i.id === data.issue_id ? { ...i, status: "Backlog" } : i))
          );
        }
        setWorkspaceError(data.error ?? "Workspace is invalid or no longer exists.");
        setWizardStep(2);
      },
    },
  );

  // ===================== effects =====================

  useEffect(() => {
    const runId = selectedIssue?.run_id;
    if (runId) {
      Promise.resolve().then(() => setLoadingRunState(true));
      fetch(apiUrl(`/api/runs/${runId}`))
        .then((res) => (res.ok ? res.json() : null))
        .then((d) => { setRunState(d); setLoadingRunState(false); })
        .catch(() => setLoadingRunState(false));
    } else {
      Promise.resolve().then(() => setRunState(null));
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
    if (count > 0) Promise.resolve().then(() => setActiveTraceTab(count - 1));
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
    const _parseEnvVarRows = (raw: string | undefined): EnvVarRow[] => {
      if (!raw) return [];
      try {
        const obj = JSON.parse(raw) as Record<string, string>;
        return Object.entries(obj).map(([key, value]) => ({ key, value }));
      } catch {
        return [];
      }
    };

    const handleFocus = async () => {
      const res = await fetch(apiUrl("/api/projects"));
      if (!res.ok) return;
      const list = await res.json();
      setProjects(list);
      const active = list.find((p: { id: number }) => p.id === activeProjectIdRef.current);
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

  // Sync settings that are stored in useAppData hook (maxConcurrentRuns, browserTestMaxSteps)
  // These come back via fetchSettings in the hook but we mirror them locally for SettingsModal
  useEffect(() => {
    // Initial fetch to populate maxConcurrentRuns and browserTestMaxSteps
    fetch(apiUrl("/api/settings"))
      .then((r) => r.ok ? r.json() : null)
      .then((d) => {
        if (!d) return;
        setMaxConcurrentRuns(d.max_concurrent_runs || "3");
        setBrowserTestMaxSteps(d.browser_test_max_steps || "20");
      })
      .catch(() => {});
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

  const cancelGithubAuth = () => {
    stopGithubPoll();
    setGithubAuthStatus("idle");
  };

  const startGithubOAuth = async () => {
    setGithubAuthError("");
    const res = await fetch(apiUrl("/api/auth/github/authorize"));
    if (!res.ok) {
      const err = (await res.json().catch(() => ({}))) as { detail?: string };
      setGithubAuthError(err.detail || "Failed to start GitHub auth. Is GITHUB_CLIENT_ID set?");
      return;
    }
    const d = (await res.json()) as { url: string; state: string };
    setGithubAuthStatus("waiting");

    const talonWindow = (window as unknown as { talon?: { openExternal: (url: string) => void } }).talon;
    if (talonWindow?.openExternal) {
      talonWindow.openExternal(d.url);
    } else {
      window.open(d.url, "_blank", "noopener,noreferrer");
    }

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
      data.fetchProjects();
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
      data.fetchProjects();
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
    const url = activeProjectId
      ? apiUrl(`/api/github/sync?project_id=${activeProjectId}`)
      : apiUrl("/api/github/sync");
    const res = await fetch(url, { method: "POST" });
    if (res.ok) {
      const d = await res.json();
      alert(`Synced ${d.synced} new issues from GitHub!`);
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
    const _parseEnvVarRows = (raw: string | undefined): EnvVarRow[] => {
      if (!raw) return [];
      try {
        const obj = JSON.parse(raw) as Record<string, string>;
        return Object.entries(obj).map(([key, value]) => ({ key, value }));
      } catch {
        return [];
      }
    };
    void _parseEnvVarRows; // suppress unused warning
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
    await data.fetchProjects();
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
      const project = await res.json();
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
    setProjects((prev) =>
      prev.map((p) => (p.id === renamingProjectId ? { ...p, name: renamingName.trim() } : p)),
    );
    setRenamingProjectId(null);
  };

  // ===================== derived =====================

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const showGithubSync =
    activeProject?.workspace_mode === "github" && !!activeProject?.selected_repo;
  const modelBadge = activeProvider
    ? `${activeProvider} · ${modelDrafts.agent_model || "auto"}`
    : null;
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
        <AppHeader
          activeProject={activeProject}
          workspaceBadgeText={workspaceBadgeText ?? null}
          modelBadge={modelBadge}
          showGithubSync={showGithubSync}
          syncing={syncing}
          onSyncIssues={syncGithubIssues}
          onAddTask={() => setIsAddModalOpen(true)}
          onOpenSettings={() => { setSettingsOpen(true); setSettingsTab("ai"); }}
        />

        <ProjectTabs
          projects={projects}
          activeProjectId={activeProjectId}
          renamingProjectId={renamingProjectId}
          renamingName={renamingName}
          renameInputRef={renameInputRef}
          setRenamingName={setRenamingName}
          setRenamingProjectId={setRenamingProjectId}
          onSelectProject={setActiveProject}
          onStartRename={startRename}
          onFinishRename={finishRename}
          onDeleteProject={deleteProject}
          onNewProject={() => setNewProjectModalOpen(true)}
        />

        <KanbanBoard
          issues={issues}
          planningIssues={planningIssues}
          liveRunStates={liveRunStates}
          onDragEnd={onDragEnd}
          onDeleteIssue={deleteIssue}
          onSelectIssue={setSelectedIssue}
          onPauseIssue={pauseIssue}
          onResumeIssue={resumeIssue}
          onRestartIssue={restartIssue}
        />
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
          onClose={() => { setNewProjectModalOpen(false); setNewProjectName(""); }}
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
          onConfigureWorkspace={() => { setSettingsOpen(false); setWizardStep(2); }}
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
