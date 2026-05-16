Run the **refiner** skill: translate reviewer feedback into a precise action plan for the next execution pass.

## Usage

```
/refiner <run-id>
```

**$ARGUMENTS** is the run ID with a non-passing review. The refiner reads the latest `ReviewFeedback` and produces `RefinementResult`.

## What it does

1. Reads the last `ReviewFeedback` (blocking issues, failed criteria, suggestions)
2. Reads the previous `ExecutorResult` (what was already built)
3. Synthesises a `RefinementResult` with:
   - **changes_planned**: specific, named changes to make
   - **refined_instructions**: a paragraph of instructions for the next executor pass

The refiner does **not** rewrite code itself — it produces the plan that the next `/task-executor` iteration uses.

## Loop position

```
task-executor → self-reviewer → [fail] → refiner → task-executor (next iteration)
                              → [pass] → browser-validator → board-updater
```

## Run the full loop

The loop runs automatically with:

```bash
python -m src.main run "your goal" 
```

Max iterations is controlled by `MAX_ITERATIONS` in `.env` (default: 3).
