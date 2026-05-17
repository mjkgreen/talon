# talon-agent

Autonomous agentic coding system. Accepts a task, executes it via sub-agents, self-reviews, iterates until passing, records proof-of-work, and posts to the Kanban board.

## Quick start

```bash
cp .env.example .env          # fill in ANTHROPIC_API_KEY at minimum
pip install -e .
talon run "Add a /health endpoint to the Express app" --working-dir ./workspace
```

## Architecture

```
Goal input
   │
   ▼
task-executor          Decomposes goal → subtasks, runs N parallel sub-agents
   │                   Each sub-agent: tool-use loop (read/write/run/search)
   ▼
self-reviewer          Inspects files + runs tests, returns pass/fail + score
   │
   ├─ pass ────────────► browser-validator   (Playwright video recording)
   │                          │
   │                          ▼
   │                     board-updater       (Linear / GitHub Projects)
   │
   └─ fail/needs_work ──► refiner            (synthesises action plan)
                               │
                               └────────────► task-executor (next iteration)
```

Max iterations: `MAX_ITERATIONS` env var (default 3).

## Skills (Claude Code slash commands)

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `/task-executor`     | Decompose goal + run parallel sub-agents           |
| `/self-reviewer`     | Evaluate output against goal, return pass/fail     |
| `/refiner`           | Translate feedback into next-iteration action plan |
| `/browser-validator` | Playwright recording (requires extra setup)        |
| `/board-updater`     | Post results to Linear / GitHub Projects           |

## CLI commands

```bash
talon run "goal"              # full loop
talon run "goal" --skip-board # skip Linear/GitHub post
talon run "goal" --url http://localhost:3000  # + browser validate
talon list                    # show all runs
talon review <run-id>         # dump run state JSON
```

## Key files

| Path | Purpose |
|------|---------|
| `talon/types.py` | Pydantic models: `RunState`, `ExecutorResult`, `ReviewFeedback`, … |
| `talon/tools.py` | Tool implementations: `read_file`, `write_file`, `run_command`, `search_files` |
| `talon/skills/task_executor.py` | Goal decomposition + parallel sub-agent runner |
| `talon/skills/self_reviewer.py` | Reviewer with tool-use loop and JSON verdict |
| `talon/skills/refiner.py` | Feedback → action plan synthesis |
| `talon/skills/browser_validator.py` | Playwright video proof (enable with env var) |
| `talon/skills/board_updater.py` | Linear / GitHub Projects poster |
| `talon/loop.py` | Orchestrates the full loop |
| `talon/main.py` | CLI entry point |
| `runs/` | Per-run audit trails (`state.json`) |
| `workspace/` | Default working directory for sub-agents |

## Environment variables

See `.env.example` for the full list. Model routing uses LiteLLM.

**Auto mode** (recommended): set API keys, leave model vars unset — the system picks the best model for each role.

**Global override**: one model for all roles:
```
AGENT_MODEL=gemini/gemini-2.0-flash   GEMINI_API_KEY=...
```

**Per-role assignment** (full control):
```
ORCHESTRATOR_MODEL=gemini/gemini-3-pro    # goal decomposition (reasoning-heavy)
SUBAGENT_MODEL=anthropic/claude-sonnet-4-6  # code writing
REVIEWER_MODEL=gemini/gemini-3-pro        # quality gate (reasoning-heavy)
REFINER_MODEL=gemini/gemini-2.0-flash       # fix planning (speed-optimised)
```

Resolution order per role: `{ROLE}_MODEL` → `AGENT_MODEL` → auto.  
Full provider list: https://docs.litellm.ai/docs/providers

## Phase 2 TODOs

- [ ] Browser validator: add goal-specific navigation steps
- [ ] Board updater: GitHub Projects API integration
- [ ] Board updater: auto-create PR from workspace diff
- [ ] Webhook listener: Linear/GitHub → trigger loop automatically
- [ ] Parallelism cap: `asyncio_throttle` to avoid API rate limits
- [ ] Workspace isolation: git worktree per run
