# Contributing to Talon

## Dev setup

```bash
git clone https://github.com/your-org/talon-agent
cd talon-agent
pip install -e ".[dev]"
cp .env.example .env  # add at least one provider API key
```

## Running tests

```bash
python -m pytest          # all tests
python -m pytest --tb=short  # compact output
python -m pytest tests/test_tools.py  # single file
```

Tests run without any API keys — all LLM calls are absent from the test suite by design.

## Linting

```bash
ruff check .      # lint
ruff format .     # auto-format
```

CI enforces both. Run them before pushing.

## Project layout

```
talon/
  config.py          # model resolution (per-role env vars → auto)
  types.py           # Pydantic models shared across the system
  tools.py           # file/shell tools available to sub-agents
  workspace.py       # per-run isolation (git worktree or copy)
  webhook.py         # FastAPI webhook server (Linear + GitHub)
  loop.py            # orchestrates the full executor→reviewer→refiner loop
  main.py            # CLI entry point
  providers/         # LiteLLM wrapper
  skills/            # task_executor, self_reviewer, refiner, browser_validator, board_updater
tests/               # pytest suite (no API calls required)
.claude/commands/    # Claude Code slash commands
```

## Adding a new tool

1. Implement the function in `talon/tools.py` — it receives `(input: dict, working_dir: str)` and returns a JSON-serialisable dict.
2. Add an entry to `TOOL_DEFINITIONS` in the same file (Anthropic `input_schema` format).
3. Register the name in `dispatch_tool`.
4. Add tests in `tests/test_tools.py`.

## Adding a new provider

Talon uses LiteLLM, so any provider supported there works automatically — just set the relevant API key and use the `provider/model` format in env vars. See `talon/config.py` for the priority lists.

## Pull requests

- Keep PRs focused: one feature or fix per PR.
- Tests are required for new behaviour.
- Lint must pass (`ruff check .`).
- Update `README.md` if you change user-facing behaviour or env vars.
