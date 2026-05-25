# talon-agent

Autonomous agentic coding system. Accepts a task, executes it via sub-agents, self-reviews, iterates until passing, records proof-of-work, and posts to the Kanban board.

## Quick start

```bash
cp .env.example .env          # fill in ANTHROPIC_API_KEY at minimum
pip install -e .
talon run "Add a /health endpoint to the Express app" --working-dir ./workspace
```

To run the UI server (Kanban board + REST API):
```bash
talon serve [--port 8080]
```

## Architecture

```
Goal input
   │
   ▼
planner                Explores workspace (read/list/search) → phased plan
   │                   (approach, constraints, phases, success criteria)
   │
   │ [optional: plan stored; user reviews/comments; plan_refiner revises]
   │
   ▼
task-executor          Iterates phases sequentially; within each phase runs
   │                   N parallel sub-agents (tool-use loop: read/write/run/search)
   │                   Each run gets an isolated workspace (git worktree or copy)
   ▼
workspace-cleaner      Removes debug scripts / temp files before commit
   │
   ▼
self-reviewer          Reads files, runs tests, checks plan success criteria
   │                   returns pass/fail + score (0–1)
   │
   ├─ pass ────────────► pr-creator          (commit + push branch + open GitHub PR)
   │                          │
   │                          ▼
   │                     browser-validator   (Playwright screenshot/video recording)
   │                          │
   │                          ▼
   │                     board-updater       (Linear / GitHub Projects)
   │
   └─ fail/needs_work ──► refiner            (synthesises action plan)
                               │
                               └────────────► task-executor (next iteration)
```

Max iterations: `MAX_ITERATIONS` env var (default 3).
Planner explore turns: `PLANNER_MAX_TURNS` env var (default 500).
Max concurrent server runs: `MAX_CONCURRENT_RUNS` (default 5).

## Workspace isolation

Every run gets its own isolated directory so concurrent runs never conflict:

| Base directory | Strategy |
|---|---|
| Git repo | `git worktree add` on branch `talon/<slug>-<id>` |
| Plain directory | `shutil.copytree` (excludes `.git`, `node_modules`, `venv`, `dist`, …) |
| None | Fresh empty directory |
| `direct=True` | Use base dir as-is — agents edit real files |

The run workspace path is stored in `RunState.workspace`. Workspaces for failed runs are removed by `workspace.teardown()`; passing runs are kept for inspection and PR creation.

A separate per-project `planner-<project_id>/` clone is kept in `WORKSPACE_DIR` so the planner can explore the repo without blocking run workspaces.

## Skills (Claude Code slash commands)

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `/task-executor`     | Decompose goal + run parallel sub-agents           |
| `/self-reviewer`     | Evaluate output against goal, return pass/fail     |
| `/refiner`           | Translate feedback into next-iteration action plan |
| `/browser-validator` | Playwright screenshot/video recording              |
| `/board-updater`     | Post results to Linear / GitHub Projects           |

## CLI commands

```bash
talon run "goal"                     # full loop
talon run "goal" --skip-board        # skip Linear/GitHub post
talon run "goal" --url http://localhost:3000  # + browser validate
talon run "goal" --working-dir ./path        # set workspace base
talon list                           # show all runs
talon review <run-id>                # dump run state JSON
talon cleanup <run-id>               # remove run workspace
talon pause <run-id>                 # request pause after current iteration
talon resume <run-id>                # resume paused or failed run from checkpoint
talon retry <run-id>                 # alias for resume
talon serve [--port 8080]            # start FastAPI server + Kanban UI
```

## Key files

| Path | Purpose |
|------|---------|
| `talon/types.py` | Pydantic models: `RunState`, `ExecutorResult`, `PhaseResult`, `ReviewFeedback`, `PlanResult`, … |
| `talon/tools.py` | Tool implementations: `read_file`, `write_file`, `run_command`, `search_files` |
| `talon/config.py` | Model resolution per role; `resolve_model(role)` and `model_config_summary()` |
| `talon/db.py` | SQLite CRUD (aiosqlite): `Project`, `Issue`, `Settings`; `init_db()`, `reset_stalled_issues()` |
| `talon/server.py` | FastAPI app: REST API, WebSocket `/ws`, webhooks, GitHub OAuth, UI serving |
| `talon/workspace.py` | Per-run workspace isolation: git worktrees, directory copies, fresh dirs, planner clones |
| `talon/skills/planner.py` | Workspace-exploring planner; outputs `PlanResult` |
| `talon/skills/plan_refiner.py` | Revises an existing plan given user feedback comments |
| `talon/skills/task_executor.py` | Phase-sequential, intra-phase-parallel execution engine |
| `talon/skills/workspace_cleaner.py` | Removes temp files / debug scripts before commit |
| `talon/skills/self_reviewer.py` | Plan-aware reviewer with tool-use loop and JSON verdict |
| `talon/skills/refiner.py` | Feedback → action plan synthesis |
| `talon/skills/pr_creator.py` | Commits workspace diff, pushes branch, opens GitHub PR |
| `talon/skills/browser_validator.py` | Playwright screenshot/video proof |
| `talon/skills/board_updater.py` | Linear / GitHub Projects poster |
| `talon/loop.py` | Orchestrates the full loop; `run()` and `resume()` entry points |
| `talon/main.py` | CLI entry point |
| `talon/providers/` | LiteLLM provider abstraction (`base.py`, `litellm_p.py`) |
| `runs/` | Per-run audit trails (`state.json`, `pause.signal`) |
| `workspace/` | Isolated run workspaces + planner clones |

## Server API

The FastAPI server (`talon serve`) exposes:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET/POST` | `/api/settings` | Read / update global settings (API keys masked) |
| `GET/POST` | `/api/projects` | List / create projects |
| `PATCH/DELETE` | `/api/projects/{id}` | Update / delete project |
| `GET/POST` | `/api/issues` | List / create issues (Backlog triggers planner; In Progress triggers run) |
| `PATCH/DELETE` | `/api/issues/{id}` | Update status / delete issue |
| `PATCH` | `/api/issues/{id}/plan` | Replace stored plan JSON |
| `POST` | `/api/issues/{id}/plan/comments` | Add feedback comment |
| `POST` | `/api/issues/{id}/plan/refine` | Re-run plan_refiner with stored comments |
| `POST` | `/api/issues/{id}/verify` | Re-run browser validation on completed run |
| `POST` | `/api/issues/{id}/pause` | Write `pause.signal` sentinel |
| `POST` | `/api/issues/{id}/resume` | Resume paused/failed run |
| `POST` | `/api/issues/{id}/restart` | Fresh run from scratch |
| `GET` | `/api/runs/{run_id}` | Read `state.json` |
| `GET` | `/api/runs/{run_id}/video` | Serve Playwright recording |
| `GET` | `/api/runs/{run_id}/screenshots/{filename}` | Serve screenshot PNGs |
| `GET` | `/api/github/repos` | List repos for authenticated user |
| `GET` | `/api/github/repos/{owner}/{repo}/branches` | List branches |
| `POST` | `/api/github/sync` | Import open GitHub issues → local board |
| `GET` | `/api/auth/github/authorize` | Start OAuth App flow |
| `POST` | `/api/auth/github/exchange` | Exchange OAuth code for token |
| `POST` | `/api/auth/github/start` | Start Device Flow |
| `POST` | `/api/auth/github/poll` | Poll Device Flow token |
| `GET` | `/api/local/browse` | Open native OS folder picker |
| `WebSocket` | `/ws` | Real-time push events |
| `POST` | `/webhook/linear` | Linear issue-created webhook |
| `POST` | `/webhook/github` | GitHub issue-opened webhook |

WebSocket event types: `plan_started`, `plan_ready`, `plan_error`, `issue_updated`, `issue_deleted`, `project_created`, `project_updated`, `project_deleted`, `run_state_updated`, `run_log`, `run_error`, `workspace_invalid`, `github_auth_complete`.

## Database

SQLite at `BOARD_DB_PATH` (default: platform user data dir via `platformdirs`, fallback `./runs/board.db`).

Tables: `settings` (key/value), `projects`, `issues`.

`db.reset_stalled_issues()` runs at startup to move any `In Progress` issues (crashed mid-run) to `Failed`.

Settings stored in DB are synced to `os.environ` at startup so existing skill code reading env vars continues to work.

## Environment variables

See `.env.example` for the full list. Model routing uses LiteLLM.

**Auto mode** (recommended): set API keys, leave model vars unset — the system picks the best model for each role.

**Global override**: one model for all roles:
```
AGENT_MODEL=gemini/gemini-flash-latest     GEMINI_API_KEY=...
```

**Per-role assignment** (full control):
```
ORCHESTRATOR_MODEL=anthropic/claude-opus-4-7   # goal decomposition (reasoning-heavy)
PLANNER_MODEL=anthropic/claude-sonnet-4-6      # workspace exploration + phased plan
SUBAGENT_MODEL=anthropic/claude-sonnet-4-6     # code writing
REVIEWER_MODEL=anthropic/claude-opus-4-7       # quality gate (reasoning-heavy)
REFINER_MODEL=anthropic/claude-sonnet-4-6      # fix planning
```

Resolution order per role: `{ROLE}_MODEL` → `AGENT_MODEL` → auto.
Full provider list: https://docs.litellm.ai/docs/providers

**Server / infrastructure:**
```
BOARD_DB_PATH=./runs/board.db        # override SQLite path
WORKSPACE_DIR=./workspace            # base dir for isolated run workspaces
RUNS_DIR=./runs                      # base dir for run state files
MAX_CONCURRENT_RUNS=5                # server-side concurrency cap
WEBHOOK_LABEL=agent-task             # Linear/GitHub label required to trigger a run
LINEAR_WEBHOOK_SECRET=...            # HMAC secret for Linear webhook validation
GITHUB_WEBHOOK_SECRET=...            # HMAC secret for GitHub webhook validation
GITHUB_CLIENT_ID=...                 # GitHub OAuth App client ID
GITHUB_CLIENT_SECRET=...             # GitHub OAuth App client secret
DEFAULT_APP_URL=http://localhost:3000 # URL used for browser verification re-runs
```

**Run behaviour:**
```
MAX_ITERATIONS=3                     # max reviewer→refiner→executor cycles
AGENT_MAX_TOKENS=8192                # token budget per sub-agent call
REVIEWER_MAX_TOOL_TURNS=10           # tool-use turns limit for the reviewer
PLANNER_MAX_TURNS=500                # max turns for workspace exploration
EDIT_LOCAL_DIRECTLY=false            # true = agents edit real files (no isolation)
PUSH_ON_PASS=true                    # false = skip PR creation after passing run
GITHUB_TOKEN=...                     # PAT for PR creation (or use GitHub OAuth)
GITHUB_REPO=owner/repo               # target repo for PRs (auto-detected from git remote)
GITHUB_BASE_BRANCH=main              # PR base branch
```

## Pause / resume

A run can be paused between iterations by writing a `pause.signal` file to the run directory (via `talon pause <run-id>` or `POST /api/issues/{id}/pause`). The loop checks for this sentinel after each iteration and saves `RunState.status = "paused"`. Resuming (`talon resume` / `POST /api/issues/{id}/resume`) calls `loop.resume(run_id)`, which reloads state and continues from the last completed iteration.

## TODOs

- [ ] Browser validator: add goal-specific navigation steps
- [ ] Board updater: GitHub Projects API integration
- [ ] Webhook listener: auto-create project/issue from Linear/GitHub label without manual sync
- [ ] Parallelism cap: `asyncio_throttle` to avoid API rate limits
- [ ] Electron shell: deep-link `talon://oauth-callback` handling
