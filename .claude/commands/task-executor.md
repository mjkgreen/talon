Run the **task-executor** skill: decompose a goal into subtasks and spawn parallel sub-agents to implement it.

## Usage

```
/task-executor <goal> [--working-dir <path>] [--skip-board]
```

**$ARGUMENTS** is the goal. If empty, ask the user to describe what they want built.

## What it does

1. Sends the goal to Claude, which returns 3–7 concrete subtasks with acceptance criteria
2. Spawns one sub-agent per subtask (running concurrently via `asyncio.gather`)
3. Each sub-agent has filesystem + shell tool access and runs its own tool-use loop
4. Aggregates all subtask outputs into an `ExecutorResult`

The result feeds into `/self-reviewer` for evaluation.

## Run it

```bash
talon run "$ARGUMENTS" --skip-board
```

Or run the full loop (executor → reviewer → refiner → repeat):

```bash
talon run "$ARGUMENTS"
```

## Output

Saves a full audit trail to `./runs/<run-id>/state.json`.
Print recent runs with: `talon list`
