# talon-agent

Autonomous agentic coding system. Give it a goal; it decomposes the work into subtasks, runs parallel sub-agents to implement them, reviews the result, iterates until passing, records a video walkthrough, and posts to your Kanban board — no Matthew required.

## How it works

```
Goal
 │
 ▼
orchestrator        Decomposes goal → 3–7 subtasks with acceptance criteria
 │
 ▼
sub-agents ×N       One agent per subtask, run concurrently
 │                  Each has read/write/shell tool access in the workspace
 ▼
reviewer            Reads files, runs tests, returns pass/fail + score (0–1)
 │
 ├─ pass ─────────► browser-validator   Records a Playwright video proof-of-work
 │                        │
 │                        ▼
 │                   board-updater      Posts result + video to Linear / GitHub Projects
 │
 └─ fail ─────────► refiner            Synthesises blocking issues → action plan
                         │
                         └──────────────► sub-agents (next iteration, max 3)
```

## Quick start

```bash
cp .env.example .env      # add at least one API key
pip install -e .
talon run "Add a /health endpoint to the Flask app" --working-dir ./workspace
```

## Model configuration

Powered by [LiteLLM](https://docs.litellm.ai/docs/providers) — swap providers by changing one env var. Three modes:

### Auto (recommended)
Set whichever API keys you have. The system picks the best available model for each role.

```bash
# .env
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
# No model vars needed — auto-selects based on what's available
```

Auto-selection priority per role:

| Role | Task | Prefers |
|------|------|---------|
| `orchestrator` | Goal decomposition | Opus → o3 → Gemini Pro → Sonnet |
| `subagent` | Code writing | Sonnet → GPT-4o → Gemini Pro → Flash |
| `reviewer` | Quality gate | Opus → o3 → Gemini Pro → Sonnet |
| `refiner` | Fix planning | Sonnet → Flash → GPT-4o → Haiku |

### Global override
One model for everything:
```bash
AGENT_MODEL=gemini/gemini-2.0-flash
GEMINI_API_KEY=...
```

### Per-role assignment
Full control:
```bash
ORCHESTRATOR_MODEL=gemini/gemini-1.5-pro    # reasoning-heavy
SUBAGENT_MODEL=anthropic/claude-sonnet-4-6  # coding
REVIEWER_MODEL=gemini/gemini-1.5-pro        # reasoning-heavy
REFINER_MODEL=gemini/gemini-2.0-flash       # speed-optimised
```

Per-role vars override `AGENT_MODEL` which overrides auto. The run header always shows which model was picked for each role and why.

## CLI

```bash
talon run "goal"                          # full loop
talon run "goal" --working-dir ./my-app  # branch from existing project
talon run "goal" --url http://localhost:3000  # + browser recording
talon run "goal" --skip-board             # skip Linear/GitHub post
talon list                                # show all runs + workspaces
talon review <run-id>                     # dump run state JSON
talon cleanup <run-id>                    # remove kept workspace
talon serve [--port 8080]                 # start webhook listener
```

## Workspace isolation

Every run gets its own isolated directory so concurrent runs never conflict.

| `--working-dir` | Behaviour |
|-----------------|-----------|
| Not set | Fresh empty `workspace/<run-id>/` |
| Plain directory | Copied into `workspace/<run-id>/` |
| Git repository | `git worktree add` on branch `agent/run-<id>` |

On **pass**: workspace is kept at `workspace/<run-id>/` — inspect the code or create a PR.  
On **fail**: workspace is removed automatically.  
Use `talon cleanup <run-id>` to remove a kept workspace when done.

## Webhook listener

Start the server once; it triggers a full loop run whenever a tagged issue arrives.

```bash
talon serve --port 8080
```

### Linear setup
1. Linear → Settings → API → Webhooks → add URL: `https://your-host/webhook/linear`
2. Set `LINEAR_WEBHOOK_SECRET` in `.env`
3. Create issues with the label `agent-task` (configurable via `WEBHOOK_LABEL`)

### GitHub setup
1. Repo → Settings → Webhooks → add URL: `https://your-host/webhook/github`
2. Content type: `application/json`, event: **Issues**
3. Set `GITHUB_WEBHOOK_SECRET` in `.env`
4. Open issues with the label `agent-task`

The server accepts up to `MAX_CONCURRENT_RUNS` (default 3) simultaneous runs; additional triggers are queued. A `/health` endpoint and auto-generated `/docs` (OpenAPI) are available.

## Claude Code slash commands

| Command | Description |
|---------|-------------|
| `/task-executor` | Decompose goal + run parallel sub-agents |
| `/self-reviewer` | Evaluate output, return pass/fail + score |
| `/refiner` | Translate feedback into next-iteration action plan |
| `/browser-validator` | Playwright video proof-of-work |
| `/board-updater` | Post results to Linear / GitHub Projects |

## Codebase

| Path | Purpose |
|------|---------|
| `talon/config.py` | Model resolution: per-role env vars, global fallback, auto-select |
| `talon/providers/litellm_p.py` | LiteLLM wrapper — normalises tool calling across all providers |
| `talon/tools.py` | Tool implementations: `read_file`, `write_file`, `run_command`, `search_files` |
| `talon/types.py` | Pydantic models: `RunState`, `ExecutorResult`, `ReviewFeedback`, … |
| `talon/skills/task_executor.py` | Goal decomposition + concurrent sub-agent runner |
| `talon/skills/self_reviewer.py` | Reviewer tool-use loop + JSON verdict |
| `talon/skills/refiner.py` | Blocking issues → refined action plan |
| `talon/skills/browser_validator.py` | Playwright recording (opt-in) |
| `talon/skills/board_updater.py` | Linear API poster |
| `talon/loop.py` | Orchestrates the full loop, persists state after every step |
| `talon/main.py` | CLI entry point |
| `runs/<id>/state.json` | Full audit trail for every run |
| `workspace/` | Default directory where sub-agents read/write code |

## Environment variables

See `.env.example` for the full annotated list. Required minimum: one API key.

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Enables `anthropic/*` models |
| `OPENAI_API_KEY` | Enables `openai/*` models |
| `GEMINI_API_KEY` | Enables `gemini/*` models |
| `GROQ_API_KEY` | Enables `groq/*` models |
| `AGENT_MODEL` | Global model override (all roles) |
| `ORCHESTRATOR_MODEL` | Per-role override |
| `SUBAGENT_MODEL` | Per-role override |
| `REVIEWER_MODEL` | Per-role override |
| `REFINER_MODEL` | Per-role override |
| `MAX_ITERATIONS` | Executor→reviewer loop limit (default: 3) |
| `LINEAR_API_KEY` | Post results to Linear |
| `BROWSER_VALIDATOR_ENABLED` | Enable Playwright recording (default: false) |

## Browser validator setup

```bash
pip install playwright
playwright install chromium
# .env
BROWSER_VALIDATOR_ENABLED=true
```

## Roadmap

- [ ] Browser validator: goal-specific navigation steps
- [ ] Board updater: GitHub Projects API
- [ ] Board updater: auto-create PR from workspace diff
- [ ] Rate-limit concurrent sub-agent API calls (`asyncio_throttle`)
- [ ] Test suite
