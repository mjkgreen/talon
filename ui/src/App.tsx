import React, { useState, useEffect } from 'react';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';
import { Play, CheckCircle2, AlertCircle, Clock, Trash2, Plus } from 'lucide-react';

interface Issue {
  id: number;
  title: string;
  description: string;
  status: string;
  run_id?: string;
  created_at: string;
  updated_at: string;
}

const COLUMNS = ['Backlog', 'In Progress', 'Done', 'Failed'];

export default function KanbanBoard() {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [newTitle, setNewTitle] = useState('');

  useEffect(() => {
    fetchIssues();
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

  const fetchIssues = async () => {
    const url = import.meta.env.DEV ? 'http://localhost:8080/api/issues' : '/api/issues';
    const res = await fetch(url);
    if (res.ok) {
      setIssues(await res.json());
    }
  };

  const addIssue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    
    const url = import.meta.env.DEV ? 'http://localhost:8080/api/issues' : '/api/issues';
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle, status: 'Backlog' })
    });
    
    if (res.ok) {
      setNewTitle('');
    }
  };

  const deleteIssue = async (id: number) => {
    const url = import.meta.env.DEV ? `http://localhost:8080/api/issues/${id}` : `/api/issues/${id}`;
    await fetch(url, { method: 'DELETE' });
  };

  const onDragEnd = async (result: any) => {
    if (!result.destination) return;
    
    const sourceStatus = result.source.droppableId;
    const destStatus = result.destination.droppableId;
    const issueId = parseInt(result.draggableId);

    if (sourceStatus === destStatus) return;

    // Optimistic update
    setIssues(prev => prev.map(i => i.id === issueId ? { ...i, status: destStatus } : i));

    const url = import.meta.env.DEV ? `http://localhost:8080/api/issues/${issueId}` : `/api/issues/${issueId}`;
    await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: destStatus })
    });
  };

  const getIssuesByStatus = (status: string) => {
    return issues.filter(i => i.status === status).sort((a, b) => b.id - a.id);
  };

  return (
    <div className="min-h-screen bg-neutral-900 text-neutral-100 p-8 font-sans">
      <div className="max-w-7xl mx-auto">
        <header className="mb-8 flex justify-between items-end">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">
              Talon Board
            </h1>
            <p className="text-neutral-400 mt-2">Autonomous Agent Task Tracker</p>
          </div>
          
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
    </div>
  );
}