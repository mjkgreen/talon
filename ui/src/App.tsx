import React, { useState, useEffect } from 'react';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';
import { Play, CheckCircle2, AlertCircle, Clock, Trash2, Plus, Settings as SettingsIcon, RefreshCw, ArrowLeft, ArrowRight, Check } from 'lucide-react';

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
  
  // Wizard State: 0 = Hidden, 1 = PAT Step, 2 = Repo Step
  const [wizardStep, setWizardStep] = useState(0);
  const [isConfigured, setIsConfigured] = useState(true);
  
  const [githubToken, setGithubToken] = useState('');
  const [selectedRepo, setSelectedRepo] = useState('');
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [syncing, setSyncing] = useState(false);

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
      } else if (data.type === 'issue_deleted') {
        setIssues(prev => prev.filter(i => i.id !== data.issue_id));
      }
    };

    return () => ws.close();
  }, []);

  const apiUrl = (path: string) => import.meta.env.DEV ? `http://localhost:8080${path}` : path;

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
        
        if (hasToken) setGithubToken(data.github_token);
        if (hasRepo) setSelectedRepo(data.selected_repo);
        
        setIsConfigured(hasToken && hasRepo);

        // Enforce wizard if missing credentials
        if (!hasToken) {
          setWizardStep(1);
        } else if (!hasRepo) {
          setWizardStep(2);
          fetchRepos(); // Safe to fetch since API uses DB token
        }
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

  const saveTokenAndContinue = async () => {
    // Save token to DB
    await fetch(apiUrl('/api/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ github_token: githubToken })
    });
    // Immediately fetch repos using the newly saved token
    await fetchRepos();
    setWizardStep(2);
  };

  const saveRepoAndFinish = async () => {
    await fetch(apiUrl('/api/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selected_repo: selectedRepo })
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
      body: JSON.stringify({ title: newTitle, status: 'Backlog' })
    });
    
    if (res.ok) setNewTitle('');
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
               {selectedRepo && (
                 <span className="bg-neutral-800 text-xs px-2 py-1 rounded flex items-center gap-1 border border-neutral-700">
                   <GithubLogo size={12} /> {selectedRepo}
                 </span>
               )}
            </div>
          </div>
          
          <div className="flex gap-4 items-center">
            {selectedRepo && (
              <button 
                onClick={syncGithubIssues} 
                disabled={syncing}
                className="text-sm bg-neutral-800 hover:bg-neutral-700 text-neutral-300 px-3 py-2 rounded flex items-center gap-2 transition-colors border border-neutral-700 disabled:opacity-50"
              >
                <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} /> 
                Sync Issues
              </button>
            )}
            <form onSubmit={addIssue} className="flex gap-2">
              <input
                type="text"
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                placeholder="Add a new task..."
                className="bg-neutral-800 border border-neutral-700 rounded px-4 py-2 text-sm focus:outline-none focus:border-blue-500 w-64"
              />
              <button type="submit" className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded flex items-center gap-2 text-sm transition-colors">
                <Plus size={16} /> Add
              </button>
            </form>
            <button 
              onClick={() => {
                // If opening settings from the gear icon, start at step 1
                setWizardStep(1);
              }}
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
                              className={`bg-neutral-800 border border-neutral-700 p-4 rounded-lg mb-3 shadow-sm
                                ${snapshot.isDragging ? 'shadow-lg border-blue-500/50' : 'hover:border-neutral-600'}
                                transition-colors group`}
                            >
                              <div className="flex justify-between items-start mb-2">
                                <span className="text-xs text-neutral-500 font-mono">T-{issue.id}</span>
                                <button 
                                  onClick={() => deleteIssue(issue.id)}
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

      {wizardStep > 0 && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50 backdrop-blur-sm">
          <div className="bg-neutral-900 border border-neutral-800 p-8 rounded-2xl w-full max-w-md shadow-2xl relative overflow-hidden">
             
             {/* Decorative background glow */}
             <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-32 bg-blue-500/10 blur-3xl rounded-full pointer-events-none" />

             {wizardStep === 1 && (
               <div className="relative">
                  <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
                    <GithubLogo size={24} /> Connect GitHub
                  </h2>
                  <p className="text-sm text-neutral-400 mb-6">
                    Talon needs a GitHub Personal Access Token (PAT) to clone your codebase and sync issues.
                  </p>
                  
                  <div className="bg-blue-500/10 border border-blue-500/20 p-4 rounded-lg mb-6">
                    <h3 className="text-sm font-semibold text-blue-400 mb-2">How to get a PAT:</h3>
                    <ol className="text-xs text-blue-300/80 space-y-2 list-decimal list-inside">
                      <li>Go to <a href="https://github.com/settings/tokens/new?scopes=repo&description=Talon+Agent" target="_blank" rel="noreferrer" className="text-blue-400 hover:underline font-medium">GitHub Token Settings</a></li>
                      <li>Ensure the <strong>repo</strong> scope is checked (this allows Talon to clone the code and read/write issues/PRs)</li>
                      <li>Generate and copy the token</li>
                    </ol>
                  </div>

                  <div className="mb-6">
                    <label className="block text-sm font-medium text-neutral-300 mb-2">Personal Access Token</label>
                    <input 
                      type="password" 
                      value={githubToken}
                      onChange={e => setGithubToken(e.target.value)}
                      placeholder="ghp_..."
                      className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
                    />
                  </div>

                  <div className="flex justify-end gap-3">
                    {isConfigured && (
                      <button onClick={() => setWizardStep(0)} className="px-5 py-2.5 text-sm text-neutral-400 hover:text-white transition-colors">Cancel</button>
                    )}
                    <button 
                      onClick={saveTokenAndContinue}
                      disabled={!githubToken}
                      className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                    >
                      Next Step <ArrowRight size={16} />
                    </button>
                  </div>
               </div>
             )}

             {wizardStep === 2 && (
               <div className="relative">
                  <button onClick={() => setWizardStep(1)} className="text-neutral-500 hover:text-neutral-300 mb-4 flex items-center gap-1 text-sm transition-colors">
                    <ArrowLeft size={14} /> Back to Token
                  </button>
                  <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
                    Select Repository
                  </h2>
                  <p className="text-sm text-neutral-400 mb-6">
                    Choose the codebase you want Talon to work on.
                  </p>

                  <div className="mb-6">
                    <label className="block text-sm font-medium text-neutral-300 mb-2">Target Repository</label>
                    <div className="relative">
                      <select
                        value={selectedRepo}
                        onChange={e => setSelectedRepo(e.target.value)}
                        className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all appearance-none text-neutral-200"
                      >
                        <option value="">Select a repository...</option>
                        {repos.map(r => (
                          <option key={r.full_name} value={r.full_name}>{r.full_name}</option>
                        ))}
                      </select>
                      <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none">
                        <svg className="w-4 h-4 text-neutral-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                      </div>
                    </div>
                    {loadingRepos && <p className="text-xs text-blue-400 mt-2 animate-pulse">Loading your repositories...</p>}
                  </div>

                  <div className="flex justify-end gap-3 mt-8">
                    {isConfigured && (
                      <button onClick={() => setWizardStep(0)} className="px-5 py-2.5 text-sm text-neutral-400 hover:text-white transition-colors">Cancel</button>
                    )}
                    <button 
                      onClick={saveRepoAndFinish}
                      disabled={!selectedRepo}
                      className="px-5 py-2.5 bg-green-600 hover:bg-green-500 disabled:bg-neutral-800 disabled:text-neutral-500 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                    >
                      Complete Setup <Check size={16} />
                    </button>
                  </div>
               </div>
             )}
          </div>
        </div>
      )}
    </div>
  );
}