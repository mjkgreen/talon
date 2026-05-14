# matthews-agentic-setup

Autonomous agentic coding system. Accepts a task, executes it via sub-agents, self-reviews, iterates until passing, records proof-of-work, and posts to the Kanban board.

## Quick start

```bash
cp .env.example .env          # fill in OPENAI_API_KEY and set AGENT_PROVIDER=openai
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

## Model selection

Set `AGENT_MODEL` in `.env` using LiteLLM's provider-prefix format:

```
AGENT_MODEL=openai/gpt-4o              OPENAI_API_KEY=sk-...
AGENT_MODEL=openai/o3                  # stronger reasoning
AGENT_MODEL=gemini/gemini-2.0-flash    GEMINI_API_KEY=...
AGENT_MODEL=anthropic/claude-sonnet-4-6  ANTHROPIC_API_KEY=sk-ant-...
AGENT_MODEL=groq/llama3-70b-8192       GROQ_API_KEY=...
```

Full provider list: https://docs.litellm.ai/docs/providers

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
| `src/providers/` | Provider abstraction: `get_provider()` returns Anthropic or OpenAI client |
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

See `.env.example` for the full list. Minimum required (OpenAI):

```
OPENAI_API_KEY=sk-...
AGENT_PROVIDER=openai
```
