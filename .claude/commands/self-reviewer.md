Run the **self-reviewer** skill: evaluate whether an executor's output actually satisfies the original goal.

## Usage

```
/self-reviewer <run-id>
```

**$ARGUMENTS** is the run ID to review. Use `/task-executor` to generate a run first.

## What it does

1. Reads the `ExecutorResult` from the run's `state.json`
2. Inspects the files in the working directory using read/list/run tools
3. Derives evaluation criteria from the original goal
4. Outputs a `ReviewFeedback` with:
   - **verdict**: `pass` / `needs_work` / `fail`
   - **score**: 0.0 – 1.0
   - **criteria**: per-criterion pass/fail with evidence
   - **blocking_issues**: must-fix items
   - **suggestions**: non-blocking improvements

## Run it

```bash
# Review the latest run
python -m src.main list          # find a run-id
python -m src.main review <run-id>
```

Or run the full loop which includes review automatically:

```bash
python -m src.main run "your goal here"
```

## Pass threshold

- `pass` → score ≥ 0.85 and no blocking issues
- `needs_work` → score ≥ 0.5, ≤ 2 blocking issues (refiner can handle)
- `fail` → score < 0.5 or > 2 blocking issues
