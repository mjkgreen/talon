# talon-agent

Autonomous agentic coding system. Accepts a task, executes it via sub-agents, self-reviews, iterates until passing, records proof-of-work, and posts to the Kanban board.

## Quick start

```bash
cp .env.example .env          # fill in OPENAI_API_KEY and set AGENT_PROVIDER=openai
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

## Model selection

Three modes — pick one in `.env`:

**Auto** (just set API keys, leave model vars unset):
```
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
# System picks best model per role from what's available
```

**Global override** (one model everywhere):
```
AGENT_MODEL=openai/gpt-4o   OPENAI_API_KEY=sk-...
```

**Per-role** (full control):
```
ORCHESTRATOR_MODEL=openai/o3                  # reasoning
SUBAGENT_MODEL=openai/gpt-4o                  # coding
REVIEWER_MODEL=openai/o3                      # strict review
REFINER_MODEL=gemini/gemini-flash-latest          # fast synthesis
```

Full provider list: https://docs.litellm.ai/docs/providers

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
| `talon/providers/` | Provider abstraction: `get_provider()` returns Anthropic or OpenAI client |
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

See `.env.example` for the full list. Minimum required (OpenAI):

```
OPENAI_API_KEY=sk-...
AGENT_PROVIDER=openai
```
