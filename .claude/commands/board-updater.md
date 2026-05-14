Run the **board-updater** skill: post the run result (verdict, score, video link, PR URL) to Linear or GitHub Projects.

## Usage

```
/board-updater <run-id>
```

**$ARGUMENTS** is the run ID to report. Reads from `./runs/<run-id>/state.json`.

## What it does

1. Reads `RunState` from the run directory
2. Formats a payload (run ID, goal, status, score, iterations, video URL, PR URL)
3. Posts to Linear (creates an issue) or prints payload if not configured

## Configure Linear

Add to `.env`:

```
LINEAR_API_KEY=lin_api_...
LINEAR_TEAM_ID=your-team-id
```

## Configure GitHub Projects (Phase 2)

```
GITHUB_TOKEN=ghp_...
GITHUB_REPO=owner/repo
```

## Run with the full loop

The board-updater runs automatically at the end of every loop (pass or fail).
Skip it with `--skip-board`:

```bash
python -m src.main run "your goal" --skip-board
```

## Phase 2 additions (TODO)

- Auto-create GitHub PR from the run's working directory
- Post video link as PR comment
- Update Linear issue status based on PR review outcome
- Webhook trigger for new Kanban card → loop start
