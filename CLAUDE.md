# matthews-agentic-setup

Autonomous agentic coding system. Accepts a task, executes it via sub-agents, self-reviews, iterates until passing, records proof-of-work, and posts to the Kanban board.

## Quick start

```bash
cp .env.example .env          # fill in ANTHROPIC_API_KEY at minimum
pip install -r requirements.txt
python -m src.main run "Add a /health endpoint to the Express app" --working-dir ./workspace
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
python -m src.main run "goal"              # full loop
python -m src.main run "goal" --skip-board # skip Linear/GitHub post
python -m src.main run "goal" --url http://localhost:3000  # + browser validate
python -m src.main list                    # show all runs
python -m src.main review <run-id>         # dump run state JSON
```

## Key files

| Path | Purpose |
|------|---------|
| `src/types.py` | Pydantic models: `RunState`, `ExecutorResult`, `ReviewFeedback`, … |
| `src/tools.py` | Tool implementations: `read_file`, `write_file`, `run_command`, `search_files` |
| `src/skills/task_executor.py` | Goal decomposition + parallel sub-agent runner |
| `src/skills/self_reviewer.py` | Reviewer with tool-use loop and JSON verdict |
| `src/skills/refiner.py` | Feedback → action plan synthesis |
| `src/skills/browser_validator.py` | Playwright video proof (enable with env var) |
| `src/skills/board_updater.py` | Linear / GitHub Projects poster |
| `src/loop.py` | Orchestrates the full loop |
| `src/main.py` | CLI entry point |
| `runs/` | Per-run audit trails (`state.json`) |
| `workspace/` | Default working directory for sub-agents |

## Environment variables

See `.env.example` for the full list. Minimum required:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Phase 2 TODOs

- [ ] Browser validator: add goal-specific navigation steps
- [ ] Board updater: GitHub Projects API integration
- [ ] Board updater: auto-create PR from workspace diff
- [ ] Webhook listener: Linear/GitHub → trigger loop automatically
- [ ] Parallelism cap: `asyncio_throttle` to avoid API rate limits
- [ ] Workspace isolation: git worktree per run
