import React, { useState, useEffect, useRef } from 'react';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';
import { Play, CheckCircle2, AlertCircle, Clock, Trash2, Plus, Settings as SettingsIcon, RefreshCw, ArrowLeft, Check, X, FileText, Activity, Folder } from 'lucide-react';

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
  created_at: string;
  updated_at: string;
}

interface Repo {
  full_name: string;
  name: string;
}

const COLUMNS = ['Backlog', 'In Progress', 'Done', 'Failed'];

export default function KanbanBoard() {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [newTitle, setNewTitle] = useState('');
  
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newDescription, setNewDescription] = useState('');
  
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [runState, setRunState] = useState<any>(null);
  const [loadingRunState, setLoadingRunState] = useState(false);
  const [liveRunStates, setLiveRunStates] = useState<Record<number, any>>({});
  const [runErrors, setRunErrors] = useState<Record<number, string>>({});
  // Wizard State: 0 = Hidden, 1 = Mode Select, 2 = Auth/Path, 3 = Repo Select (GitHub only)
  const [wizardStep, setWizardStep] = useState(0);
  const [isConfigured, setIsConfigured] = useState(true);

  const [workspaceMode, setWorkspaceMode] = useState<'github' | 'local' | 'none' | ''>('');
  const [localPath, setLocalPath] = useState('');
  const [selectedRepo, setSelectedRepo] = useState('');
  const [, setHasGithubToken] = useState(false);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [browsing, setBrowsing] = useState(false);

  type DeviceFlow = { device_code: string; user_code: string; verification_uri: string; interval: number };
  const [deviceFlow, setDeviceFlow] = useState<DeviceFlow | null>(null);
  const [deviceFlowStatus, setDeviceFlowStatus] = useState<'idle' | 'pending' | 'complete' | 'expired'>('idle');
  const [deviceFlowError, setDeviceFlowError] = useState('');
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetchIssues();
    fetchSettings();
    const wsUrl = window.location.protocol === 'https:' ? 'wss://' : 'ws://' + window.location.host + '/ws';
    const ws = new WebSocket(import.meta.env.DEV ? 'ws://localhost:8080/ws' : wsUrl);
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'issue_updated') {
        setIssues(prev => {
          const exists = prev.find(i => i.id === data.issue.id);
          if (exists) {
            return prev.map(i => i.id === data.issue.id ? data.issue : i);
          }
          return [data.issue, ...prev];
        });
        // Keep the selected issue detail in sync (picks up run_id when agent starts)
        setSelectedIssue(prev => prev?.id === data.issue.id ? data.issue : prev);
      } else if (data.type === 'issue_deleted') {
        setIssues(prev => prev.filter(i => i.id !== data.issue_id));
      } else if (data.type === 'run_state_updated') {
        setLiveRunStates(prev => ({ ...prev, [data.issue_id]: data.state }));
      } else if (data.type === 'run_error') {
        setRunErrors(prev => ({ ...prev, [data.issue_id]: data.error }));
      }
    };

    return () => ws.close();
  }, []);

  const apiUrl = (path: string) => import.meta.env.DEV ? `http://localhost:8080${path}` : path;

  useEffect(() => {
    const runId = selectedIssue?.run_id;
    if (runId) {
      setLoadingRunState(true);
      fetch(apiUrl(`/api/runs/${runId}`))
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          setRunState(data);
          setLoadingRunState(false);
        })
        .catch(() => setLoadingRunState(false));
    } else {
      setRunState(null);
    }
  // Only re-fetch when the issue itself or its run_id changes, not on every status update
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIssue?.id, selectedIssue?.run_id]);

  const fetchIssues = async () => {
    const res = await fetch(apiUrl('/api/issues'));
    if (res.ok) setIssues(await res.json());
  };

  const fetchSettings = async () => {
    try {
      const res = await fetch(apiUrl('/api/settings'));
      if (res.ok) {
        const data = await res.json();
        const hasToken = !!data.github_token;
        const hasRepo = !!data.selected_repo;
        const mode: string = data.workspace_mode || '';
        const lpath: string = data.local_path || '';

        setHasGithubToken(hasToken);
        if (hasRepo) setSelectedRepo(data.selected_repo);
        if (lpath) setLocalPath(lpath);

        // Migrate legacy config (token+repo but no mode) to "github" mode silently
        if (!mode && hasToken && hasRepo) {
          await fetch(apiUrl('/api/settings'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workspace_mode: 'github' }),
          });
          setWorkspaceMode('github');
          setIsConfigured(true);
          return;
        }

        setWorkspaceMode(mode as 'github' | 'local' | 'none' | '');

        let configured = false;
        if (mode === 'none') configured = true;
        else if (mode === 'local') configured = !!lpath;
        else if (mode === 'github') configured = hasToken && hasRepo;

        setIsConfigured(configured);
        if (!configured) setWizardStep(1);
      }
    } catch (e) {
      console.error("Failed to fetch settings", e);
    }
  };

  const fetchRepos = async () => {
    setLoadingRepos(true);
    try {
      const res = await fetch(apiUrl('/api/github/repos'));
      if (res.ok) {
        setRepos(await res.json());
      }
    } catch (e) {
      console.error(e);
    }
    setLoadingRepos(false);
  };

  const selectMode = async (mode: 'github' | 'local' | 'none') => {
    setWorkspaceMode(mode);
    await fetch(apiUrl('/api/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_mode: mode }),
    });
    if (mode === 'none') {
      setIsConfigured(true);
      setWizardStep(0);
    } else {
      setWizardStep(2);
      if (mode === 'github') {
        setDeviceFlow(null);
        setDeviceFlowStatus('idle');
        setDeviceFlowError('');
      }
    }
  };

  const startDeviceFlow = async () => {
    setDeviceFlowError('');
    const res = await fetch(apiUrl('/api/auth/github/start'), { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setDeviceFlowError(err.detail || 'Failed to start GitHub auth. Is GITHUB_CLIENT_ID set?');
      return;
    }
    const data: DeviceFlow & { expires_in: number } = await res.json();
    setDeviceFlow(data);
    setDeviceFlowStatus('pending');
  };

  useEffect(() => {
    if (deviceFlowStatus !== 'pending' || !deviceFlow) return;
    const intervalMs = (deviceFlow.interval + 1) * 1000;
    pollIntervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(apiUrl('/api/auth/github/poll'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ device_code: deviceFlow.device_code }),
        });
        const data = await res.json();
        if (data.status === 'complete') {
          clearInterval(pollIntervalRef.current!);
          setDeviceFlowStatus('complete');
          setHasGithubToken(true);
          await fetchRepos();
          setWizardStep(3);
        } else if (data.status === 'expired') {
          clearInterval(pollIntervalRef.current!);
          setDeviceFlowStatus('expired');
        }
      } catch {
        // ignore transient network errors, keep polling
      }
    }, intervalMs);
    return () => { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceFlowStatus, deviceFlow]);

  const saveLocalPathAndFinish = async () => {
    await fetch(apiUrl('/api/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ local_path: localPath }),
    });
    setIsConfigured(true);
    setWizardStep(0);
  };

  const saveRepoAndFinish = async () => {
    await fetch(apiUrl('/api/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selected_repo: selectedRepo }),
    });
    setIsConfigured(true);
    setWizardStep(0);
  };

  const syncGithubIssues = async () => {
    if (!selectedRepo) return;
    setSyncing(true);
    const res = await fetch(apiUrl('/api/github/sync'), { method: 'POST' });
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
    
    const res = await fetch(apiUrl('/api/issues'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle, description: newDescription, status: 'Backlog' })
    });
    
    if (res.ok) {
      setNewTitle('');
      setNewDescription('');
      setIsAddModalOpen(false);
    }
  };

  const deleteIssue = async (id: number) => {
    await fetch(apiUrl(`/api/issues/${id}`), { method: 'DELETE' });
  };

  const onDragEnd = async (result: any) => {
    if (!result.destination) return;
    
    const sourceStatus = result.source.droppableId;
    const destStatus = result.destination.droppableId;
    const issueId = parseInt(result.draggableId);

    if (sourceStatus === destStatus) return;

    setIssues(prev => prev.map(i => i.id === issueId ? { ...i, status: destStatus } : i));

    await fetch(apiUrl(`/api/issues/${issueId}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: destStatus })
    });
  };

  const getIssuesByStatus = (status: string) => issues.filter(i => i.status === status).sort((a, b) => b.id - a.id);

  return (
    <div className="min-h-screen bg-neutral-900 text-neutral-100 p-8 font-sans relative">
      <div className="max-w-7xl mx-auto">
        <header className="mb-8 flex justify-between items-end">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent flex items-center gap-3">
              Talon Board
            </h1>
            <div className="text-neutral-400 mt-2 flex items-center gap-3">
               Autonomous Agent Tracker
               {workspaceMode === 'github' && selectedRepo && (
                 <span className="bg-neutral-800 text-xs px-2 py-1 rounded flex items-center gap-1 border border-neutral-700">
                   <GithubLogo size={12} /> {selectedRepo}
                 </span>
               )}
               {workspaceMode === 'local' && localPath && (
                 <span className="bg-neutral-800 text-xs px-2 py-1 rounded flex items-center gap-1 border border-neutral-700">
                   <Folder size={12} /> {localPath}
                 </span>
               )}
            </div>
          </div>
          
          <div className="flex gap-4 items-center">
            {workspaceMode === 'github' && selectedRepo && (
              <button
                onClick={syncGithubIssues}
                disabled={syncing}
                className="text-sm bg-neutral-800 hover:bg-neutral-700 text-neutral-300 px-3 py-2 rounded flex items-center gap-2 transition-colors border border-neutral-700 disabled:opacity-50"
              >
                <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
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
              onClick={() => setWizardStep(1)}
              className="p-2 bg-neutral-800 hover:bg-neutral-700 rounded text-neutral-400 hover:text-white transition-colors"
            >
              <SettingsIcon size={20} />
            </button>
          </div>
        </header>

        <DragDropContext onDragEnd={onDragEnd}>
          <div className="flex gap-6 h-[calc(100vh-200px)]">
            {COLUMNS.map(column => (
              <div key={column} className="flex-1 flex flex-col bg-neutral-800/50 rounded-xl overflow-hidden border border-neutral-800">
                <div className="p-4 border-b border-neutral-800 bg-neutral-800/80 flex justify-between items-center">
                  <h2 className="font-semibold text-neutral-300">{column}</h2>
                  <span className="bg-neutral-700 text-xs px-2 py-1 rounded-full text-neutral-300">
                    {getIssuesByStatus(column).length}
                  </span>
                </div>
                
                <Droppable droppableId={column}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className={`flex-1 p-4 overflow-y-auto ${snapshot.isDraggingOver ? 'bg-neutral-800/80' : ''}`}
                    >
                      {getIssuesByStatus(column).map((issue, index) => (
                        <Draggable key={issue.id} draggableId={issue.id.toString()} index={index}>
                          {(provided, snapshot) => (
                              <div
                                ref={provided.innerRef}
                                {...provided.draggableProps}
                                {...provided.dragHandleProps}
                                onClick={() => setSelectedIssue(issue)}
                                className={`bg-neutral-800 border border-neutral-700 p-4 rounded-lg mb-3 shadow-sm cursor-pointer
                                  ${snapshot.isDragging ? 'shadow-lg border-blue-500/50' : 'hover:border-neutral-600'}
                                  transition-colors group`}
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
                                {issue.status === 'In Progress' && (
                                  <span className="flex items-center gap-1 text-blue-400 bg-blue-400/10 px-2 py-1 rounded">
                                    <Play size={12} className="animate-pulse" /> Agent running
                                  </span>
                                )}
                                {issue.status === 'Done' && (
                                  <span className="flex items-center gap-1 text-green-400 bg-green-400/10 px-2 py-1 rounded">
                                    <CheckCircle2 size={12} /> Passed
                                  </span>
                                )}
                                {issue.status === 'Failed' && (
                                  <span className="flex items-center gap-1 text-red-400 bg-red-400/10 px-2 py-1 rounded">
                                    <AlertCircle size={12} /> Needs Work
                                  </span>
                                )}
                                {issue.status === 'Backlog' && (
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
            ))}
          </div>
        </DragDropContext>
      </div>

      {isAddModalOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
          <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-xl w-full max-w-lg shadow-2xl">
            <h2 className="text-xl font-bold mb-4">Add New Task</h2>
            <form onSubmit={addIssue} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Title</label>
                <input 
                  type="text" 
                  value={newTitle}
                  onChange={e => setNewTitle(e.target.value)}
                  autoFocus
                  placeholder="e.g., Create a new landing page"
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-300 mb-1">Description (Optional)</label>
                <textarea 
                  value={newDescription}
                  onChange={e => setNewDescription(e.target.value)}
                  placeholder="Provide any additional context, instructions, or acceptance criteria for the agent..."
                  rows={5}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all resize-none"
                />
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button 
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 text-sm text-neutral-400 hover:text-white"
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  disabled={!newTitle.trim()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded text-sm transition-colors"
                >
                  Create Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {wizardStep > 0 && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
          <div className="bg-neutral-900 border border-neutral-800 p-8 rounded-2xl w-full max-w-md shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-32 bg-blue-500/10 blur-3xl rounded-full pointer-events-none" />

            {/* Step 1: Choose workspace mode */}
            {wizardStep === 1 && (
              <div className="relative">
                <h2 className="text-2xl font-bold mb-2">Workspace Setup</h2>
                <p className="text-sm text-neutral-400 mb-6">Where should Talon work when running tasks?</p>
                <div className="space-y-3">
                  <button
                    onClick={() => selectMode('github')}
                    className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-blue-500/60 bg-neutral-800/50 hover:bg-blue-500/5 transition-all group"
                  >
                    <div className="flex items-center gap-3 mb-1">
                      <GithubLogo size={18} />
                      <span className="font-medium text-sm">GitHub Repository</span>
                    </div>
                    <p className="text-xs text-neutral-500 ml-7">Clone a repo from GitHub and work in an isolated branch per run.</p>
                  </button>
                  <button
                    onClick={() => selectMode('local')}
                    className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-blue-500/60 bg-neutral-800/50 hover:bg-blue-500/5 transition-all group"
                  >
                    <div className="flex items-center gap-3 mb-1">
                      <Folder size={18} />
                      <span className="font-medium text-sm">Local Directory</span>
                    </div>
                    <p className="text-xs text-neutral-500 ml-7">Point Talon at a folder on this machine. Uses git worktrees when available.</p>
                  </button>
                  <button
                    onClick={() => selectMode('none')}
                    className="w-full text-left p-4 rounded-xl border border-neutral-700 hover:border-neutral-600 bg-neutral-800/50 hover:bg-neutral-800 transition-all"
                  >
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-neutral-400 font-medium text-sm">No Workspace</span>
                    </div>
                    <p className="text-xs text-neutral-500">Run tasks in a fresh empty workspace each time.</p>
                  </button>
                </div>
                {isConfigured && (
                  <button onClick={() => setWizardStep(0)} className="mt-5 text-sm text-neutral-500 hover:text-neutral-300 transition-colors">
                    Cancel
                  </button>
                )}
              </div>
            )}

            {/* Step 2a: GitHub device flow */}
            {wizardStep === 2 && workspaceMode === 'github' && (
              <div className="relative">
                <button onClick={() => setWizardStep(1)} className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors">
                  <ArrowLeft size={14} /> Back
                </button>
                <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
                  <GithubLogo size={22} /> Connect GitHub
                </h2>
                <p className="text-sm text-neutral-400 mb-6">
                  Authorize Talon via GitHub's device flow — no passwords or tokens to copy.
                </p>

                {deviceFlowStatus === 'idle' && (
                  <>
                    {deviceFlowError && (
                      <div className="mb-4 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">{deviceFlowError}</div>
                    )}
                    <button
                      onClick={startDeviceFlow}
                      className="w-full py-3 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-colors"
                    >
                      <GithubLogo size={16} /> Authorize with GitHub
                    </button>
                  </>
                )}

                {(deviceFlowStatus === 'pending' || deviceFlowStatus === 'complete') && deviceFlow && (
                  <div className="space-y-4">
                    <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-5 text-center">
                      <p className="text-xs text-neutral-500 mb-2">Visit this URL and enter the code:</p>
                      <a
                        href={deviceFlow.verification_uri}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-400 hover:underline text-sm font-mono block mb-4"
                      >
                        {deviceFlow.verification_uri}
                      </a>
                      <div className="bg-neutral-900 border border-neutral-700 rounded-lg px-6 py-3 inline-block">
                        <span className="text-2xl font-mono font-bold tracking-widest text-white">{deviceFlow.user_code}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-neutral-400">
                      <RefreshCw size={14} className="animate-spin shrink-0" />
                      Waiting for authorization…
                    </div>
                  </div>
                )}

                {deviceFlowStatus === 'expired' && (
                  <div className="space-y-4">
                    <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                      Code expired. Click below to try again.
                    </div>
                    <button
                      onClick={() => { setDeviceFlowStatus('idle'); setDeviceFlow(null); }}
                      className="w-full py-3 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-xl text-sm font-medium transition-colors"
                    >
                      Restart Authorization
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Step 2b: Local directory path */}
            {wizardStep === 2 && workspaceMode === 'local' && (
              <div className="relative">
                <button onClick={() => setWizardStep(1)} className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors">
                  <ArrowLeft size={14} /> Back
                </button>
                <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
                  <Folder size={22} /> Local Directory
                </h2>
                <p className="text-sm text-neutral-400 mb-6">
                  Enter the absolute path to the project folder on this machine.
                </p>
                <div className="mb-6">
                  <label className="block text-sm font-medium text-neutral-300 mb-2">Project Path</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={localPath}
                      onChange={e => setLocalPath(e.target.value)}
                      autoFocus
                      placeholder="/Users/you/projects/my-app"
                      className="flex-1 bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                    <button
                      type="button"
                      onClick={async () => {
                        setBrowsing(true);
                        try {
                          const res = await fetch(apiUrl('/api/local/browse'));
                          if (res.ok) {
                            const data = await res.json();
                            if (data.path) setLocalPath(data.path);
                          }
                        } finally {
                          setBrowsing(false);
                        }
                      }}
                      disabled={browsing}
                      className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 rounded-lg text-sm text-neutral-300 transition-colors whitespace-nowrap flex items-center gap-2 disabled:opacity-50"
                    >
                      {browsing ? <RefreshCw size={14} className="animate-spin" /> : <Folder size={14} />}
                      {browsing ? 'Opening…' : 'Browse…'}
                    </button>
                  </div>
                  <p className="text-xs text-neutral-600 mt-2">Git repos get an isolated worktree per run; plain dirs are copied.</p>
                </div>
                <div className="flex justify-between items-center">
                  {isConfigured && (
                    <button onClick={() => setWizardStep(0)} className="text-sm text-neutral-500 hover:text-neutral-300 transition-colors">Cancel</button>
                  )}
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

            {/* Step 3: GitHub repo selection */}
            {wizardStep === 3 && (
              <div className="relative">
                <button onClick={() => setWizardStep(2)} className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors">
                  <ArrowLeft size={14} /> Back
                </button>
                <h2 className="text-2xl font-bold mb-2">Select Repository</h2>
                <p className="text-sm text-neutral-400 mb-6">Choose the codebase you want Talon to work on.</p>
                <div className="mb-6">
                  <label className="block text-sm font-medium text-neutral-300 mb-2">Target Repository</label>
                  <div className="relative">
                    <select
                      value={selectedRepo}
                      onChange={e => setSelectedRepo(e.target.value)}
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all appearance-none text-neutral-200"
                    >
                      <option value="">Select a repository…</option>
                      {repos.map(r => (
                        <option key={r.full_name} value={r.full_name}>{r.full_name}</option>
                      ))}
                    </select>
                    <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none">
                      <svg className="w-4 h-4 text-neutral-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                    </div>
                  </div>
                  {loadingRepos && <p className="text-xs text-blue-400 mt-2 animate-pulse">Loading your repositories…</p>}
                </div>
                <div className="flex justify-between items-center mt-8">
                  {isConfigured && (
                    <button onClick={() => setWizardStep(0)} className="text-sm text-neutral-500 hover:text-neutral-300 transition-colors">Cancel</button>
                  )}
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
      {selectedIssue && (() => {
        const activeRunState = liveRunStates[selectedIssue.id] || runState;
        const runError = runErrors[selectedIssue.id];
        const isLive = selectedIssue.status === 'In Progress' && !!liveRunStates[selectedIssue.id];
        return (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
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
                    selectedIssue.status === 'Done' ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                    selectedIssue.status === 'Failed' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                    selectedIssue.status === 'In Progress' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                    'bg-neutral-800 text-neutral-400 border border-neutral-700'
                  }`}>
                    {selectedIssue.status === 'In Progress' && <Play size={10} className="animate-pulse" />}
                    {selectedIssue.status === 'Done' && <CheckCircle2 size={10} />}
                    {selectedIssue.status === 'Failed' && <AlertCircle size={10} />}
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

              {selectedIssue.status === 'In Progress' && !activeRunState && !runError && (
                <div className="flex items-center gap-3 p-4 bg-blue-500/10 border border-blue-500/20 rounded-xl text-blue-400 text-sm">
                  <RefreshCw size={16} className="animate-spin shrink-0" />
                  Agent is starting up — logs will appear here shortly...
                </div>
              )}

              {loadingRunState && !activeRunState && (
                <div className="flex items-center justify-center p-12 text-neutral-500 gap-3">
                  <RefreshCw size={20} className="animate-spin" /> Fetching agent logs...
                </div>
              )}

              {activeRunState && (
                <div className="space-y-6">
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
                    <div className="p-0">
                      {(!activeRunState.executor_results || activeRunState.executor_results.length === 0) && (
                        <div className="p-8 text-center text-neutral-500 text-sm flex flex-col items-center gap-3">
                          <RefreshCw size={20} className="animate-spin text-blue-500" />
                          Agent initializing — decomposing goal into subtasks...
                        </div>
                      )}
                      {activeRunState.executor_results?.map((res: any, idx: number) => (
                        <div key={idx} className="border-b border-neutral-800 last:border-0">
                          <div className="p-4 bg-neutral-900/50">
                            <h4 className="text-sm font-medium text-blue-300 mb-3 flex items-center gap-2">
                              Iteration {idx + 1}
                              {isLive && idx === activeRunState.executor_results.length - 1 && !activeRunState.review_results?.[idx] && (
                                <span className="text-xs text-neutral-500 flex items-center gap-1">
                                  <RefreshCw size={10} className="animate-spin" /> reviewing...
                                </span>
                              )}
                            </h4>
                            {res.subtasks?.length > 0 && (
                              <div className="mb-3 space-y-1">
                                {res.subtasks.map((st: any, si: number) => {
                                  const stResult = res.subtask_results?.[si];
                                  return (
                                    <div key={si} className="flex items-start gap-2 text-xs text-neutral-400">
                                      <span className={`mt-0.5 shrink-0 ${stResult?.success ? 'text-green-400' : 'text-neutral-600'}`}>
                                        {stResult ? (stResult.success ? '✓' : '✗') : '○'}
                                      </span>
                                      <span>{st.description}</span>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                            <div className="bg-neutral-950 p-4 rounded border border-neutral-800/50 overflow-x-auto">
                              <pre className="text-xs text-neutral-400 font-mono whitespace-pre-wrap">{res.aggregated_output || "No output yet"}</pre>
                            </div>
                          </div>

                          {activeRunState.review_results?.[idx] && (
                            <div className="p-4 border-t border-neutral-800/50">
                              <div className="flex items-center gap-3 mb-2">
                                <span className={`text-xs px-2 py-1 rounded font-medium ${activeRunState.review_results[idx].verdict === 'pass' ? 'bg-green-500/10 text-green-400' : 'bg-amber-500/10 text-amber-400'}`}>
                                  Review: {activeRunState.review_results[idx].verdict.toUpperCase()}
                                </span>
                                <span className="text-xs text-neutral-500">
                                  Score: {Math.round((activeRunState.review_results[idx].score ?? 0) * 10)}/10
                                </span>
                              </div>
                              {activeRunState.review_results[idx].summary && (
                                <div className="bg-neutral-950 p-4 rounded border border-neutral-800/50 mb-2">
                                  <p className="text-xs text-neutral-300">{activeRunState.review_results[idx].summary}</p>
                                </div>
                              )}
                              {activeRunState.review_results[idx].blocking_issues?.length > 0 && (
                                <div className="text-xs text-red-400 space-y-1 mt-2">
                                  {activeRunState.review_results[idx].blocking_issues.map((issue: string, bi: number) => (
                                    <div key={bi} className="flex items-start gap-1">
                                      <span className="shrink-0">✗</span> {issue}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          {activeRunState.refinement_results?.[idx] && (
                            <div className="p-4 border-t border-neutral-800/30 bg-amber-500/5">
                              <div className="text-xs text-amber-400 font-medium mb-2">Refinement plan for next iteration</div>
                              <div className="text-xs text-neutral-400 space-y-1">
                                {activeRunState.refinement_results[idx].changes_planned?.map((c: string, ci: number) => (
                                  <div key={ci} className="flex items-start gap-1">
                                    <span className="shrink-0 text-amber-500">→</span> {c}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}

                      {isLive && activeRunState.executor_results?.length > 0 &&
                        activeRunState.executor_results.length > (activeRunState.review_results?.length ?? 0) && (
                        <div className="p-4 flex items-center gap-2 text-xs text-neutral-500 border-t border-neutral-800">
                          <RefreshCw size={12} className="animate-spin" /> Waiting for reviewer...
                        </div>
                      )}
                    </div>
                  </div>

                  {activeRunState.video_path && (
                    <div className="bg-neutral-950 border border-neutral-800 rounded-xl overflow-hidden">
                      <div className="bg-neutral-900 border-b border-neutral-800 p-4">
                        <h3 className="text-sm font-medium text-neutral-300 flex items-center gap-2">
                          <Play size={16} className="text-blue-400" />
                          Video Verification
                        </h3>
                      </div>
                      <div className="p-4 flex justify-center bg-black">
                        <video
                          controls
                          className="max-w-full max-h-[400px] rounded border border-neutral-800"
                          src={apiUrl(`/api/runs/${activeRunState.run_id}/video`)}
                        >
                          Your browser does not support the video tag.
                        </video>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {!activeRunState && !runError && !loadingRunState && selectedIssue.run_id && (
                <div className="p-8 text-center text-neutral-500 border border-neutral-800/50 border-dashed rounded-xl">
                  <div className="mb-2">No logs found for run <code className="bg-neutral-800 px-1 py-0.5 rounded text-xs">{selectedIssue.run_id}</code></div>
                  <div className="text-xs">Check the server terminal for error details.</div>
                </div>
              )}

              {!activeRunState && !runError && !loadingRunState && !selectedIssue.run_id && selectedIssue.status !== 'In Progress' && (
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