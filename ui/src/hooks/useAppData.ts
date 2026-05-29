import { useState, useEffect, useRef } from "react";
import type { Issue, Project, Repo } from "../types";
import { apiUrl } from "../utils";

export function useAppData() {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectIdState] = useState<number | null>(null);
  const activeProjectIdRef = useRef<number | null>(null);

  const [repos, setRepos] = useState<Repo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [branches, setBranches] = useState<string[]>([]);
  const [loadingBranches, setLoadingBranches] = useState(false);

  const [workspaceMode, setWorkspaceMode] = useState<"github" | "local" | "none" | "">("");
  const [localPath, setLocalPath] = useState("");
  const [selectedRepo, setSelectedRepo] = useState("");
  const [selectedBranch, setSelectedBranch] = useState("");
  const [, setHasGithubToken] = useState(false);
  const [browsing, setBrowsing] = useState(false);

  const [hasLlm, setHasLlm] = useState(false);
  const [isConfigured, setIsConfigured] = useState(true);
  const [activeProvider, setActiveProvider] = useState<string | null>(null);

  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [modelDrafts, setModelDrafts] = useState<Record<string, string>>({});
  const [maxIterations, setMaxIterations] = useState("5");
  const [maxTokens, setMaxTokens] = useState("");
  const [reviewerMaxToolTurns, setReviewerMaxToolTurns] = useState("50");
  const [editLocalDirectly, setEditLocalDirectly] = useState(false);
  const [pushOnPass, setPushOnPass] = useState(true);
  const [autoFallback, setAutoFallback] = useState(true);

  const [wizardStep, setWizardStep] = useState(0);
  const [wizardKeys, setWizardKeys] = useState<Record<string, string>>({});
  const [savingWizardKeys, setSavingWizardKeys] = useState(false);

  const setActiveProject = (id: number) => {
    setActiveProjectIdState(id);
    activeProjectIdRef.current = id;
    localStorage.setItem("talon_active_project", String(id));
    fetchIssues(id);
  };

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
        claude_code_api_key: data.claude_code_api_key || "",
        openai_api_key: data.openai_api_key || "",
        codex_api_key: data.codex_api_key || "",
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
      setEditLocalDirectly(data.edit_local_directly === "true");
      setPushOnPass(data.push_on_pass !== "false");
      setAutoFallback(data.auto_fallback !== "false");

      const hasToken = !!data.github_token;
      const hasRepo = !!data.selected_repo;
      const mode: string = data.workspace_mode || "";
      const lpath: string = data.local_path || "";
      setHasGithubToken(hasToken);
      if (hasRepo) setSelectedRepo(data.selected_repo);
      if (lpath) setLocalPath(lpath);
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

  useEffect(() => {
    const init = async () => {
      const projId = await fetchProjects();
      await Promise.all([fetchIssues(projId), fetchSettings()]);
    };
    init();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const project = projects.find((p) => p.id === activeProjectId);
    if (project?.selected_branch) setSelectedBranch(project.selected_branch);
  }, [activeProjectId, projects]);

  useEffect(() => {
    if (wizardStep === 4 && selectedRepo) {
      setSelectedBranch("");
      fetchBranches(selectedRepo);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wizardStep]);

  return {
    issues, setIssues,
    projects, setProjects,
    activeProjectId,
    activeProjectIdRef,
    setActiveProject,
    repos, loadingRepos, fetchRepos,
    branches, loadingBranches,
    selectedBranch, setSelectedBranch,
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
    autoFallback, setAutoFallback,
    wizardStep, setWizardStep,
    wizardKeys, setWizardKeys,
    savingWizardKeys, setSavingWizardKeys,
    fetchIssues, fetchProjects, fetchSettings, fetchBranches,
  };
}
