# talon-agent

Autonomous agentic coding system. Give it a goal; it decomposes the work into subtasks, runs parallel sub-agents to implement them, reviews the result, iterates until passing, records a video walkthrough, and posts to your Kanban board.

Available as a **desktop app** (Electron + bundled Python server) or as a standalone CLI/server.

[![GitHub release](https://img.shields.io/github/v/release/mjkgreen/talon?cacheSeconds=300)](https://github.com/mjkgreen/talon/releases/latest)

**[⬇ Download the latest release](https://github.com/mjkgreen/talon/releases/latest)**  
Windows `.exe` · macOS `.dmg` · Linux `.AppImage`

---

## Description

`talon-agent` is an advanced AI-powered orchestrator and agentic workspace automation system designed to take high-level software development goals and turn them into fully executed, verified code changes. 

Instead of relying on a single context window to write code and perform tasks, `talon-agent` utilizes a multi-role, parallel agent architecture to decompose complex goals, execute subtasks simultaneously in isolated workspaces, strictly review output results against automated test suites, and iteratively refine codebases until all acceptance criteria are met.

### How It Works

The system operates via a continuous loop of workspace exploration, phased planning, parallel execution, self-review, refinement, and verification. Below is a high-level flowchart of the workflow:

```text
Goal
 │
 ▼
planner             Explores workspace (read/list/search) → produces phased plan
 │                  (approach, constraints, phases, success criteria)
 ▼
orchestrator        Iterates through each plan phase sequentially
 │                  Decomposes each phase into parallel subtasks
 ▼
sub-agents ×N       One agent per subtask, run concurrently within each phase
 │                  Each has read/write/shell tool access in the workspace
 ▼
reviewer            Reads files, runs tests, checks every success criterion;
 │                  returns pass/fail + score (0–1)
 │
 ├─ pass ─────────► browser-validator   Records a video proof-of-work (coming soon)
 │                        │
 │                        ▼
 │                   board-updater      Posts result + video to Linear / GitHub Projects
 │
 └─ fail ─────────► refiner            Synthesises blocking issues → action plan
                         │
                         └──────────────► loops back to planner/sub-agents (next iteration, max set via settings)
```

### Agent Roles

1. **Planner**: Before execution begins, the planner explores the workspace using read-only tools (`read_file`, `list_files`, `search_files`) to understand the existing codebase, conventions, and tech stack. It then produces a structured multi-phase plan (approach, constraints, ordered phases, success criteria) that guides all subsequent execution.
2. **Orchestrator**: Iterates through plan phases sequentially. For each phase it decomposes the work into 1–7 concurrent subtasks tailored to that phase's scope and the output of prior phases.
3. **Sub-agents (xN)**: Executed concurrently within a phase. Each sub-agent functions as an independent developer equipped with terminal and filesystem tools (`read_file`, `write_file`, `run_command`, `search_files`) to implement their specific subtask in the workspace.
4. **Reviewer**: Inspects the modified workspace files, runs user-defined test suites, evaluates the result against every success criterion from the plan, and assigns a passing grade or failure along with a score (0.0–1.0).
5. **Refiner**: Active only on task failures. It analyzes the reviewer's feedback, aggregates test failures and compiler warnings, and produces a revised action plan for the next iteration.
6. **Browser Validator**: (Opt-in) Uses Playwright to navigate the application, performs basic UI sanity checks, and records a high-definition walkthrough video to serve as visual proof-of-work.
7. **Board Updater**: Automatically posts run summaries, code changes, and visual walkthrough links to project management boards (e.g., Linear or GitHub Projects).

---

## Prerequisites

Before running or developing `talon-agent`, ensure your local system meets the following requirements:

### System Environment
* **Python**: `python >= 3.11` (specifically tested on Python `3.11` and `3.12`).
* **Operating System**: macOS, Linux, or Windows.
  * *Note for Windows users:* Set `PYTHONUTF8=1` in your environment to prevent character encoding issues.
* **Git**: Git must be installed and globally accessible on your system's `PATH`. This is required for workspace isolation (creating worktrees).

### LLM Credentials
At least one API key from a supported provider is required. Model routing is powered by **LiteLLM**. Available providers include:
* **Anthropic** (`ANTHROPIC_API_KEY`): Used for Claude models (e.g., `claude-4.6-sonnet`, `claude-4.7-opus`).
* **OpenAI** (`OPENAI_API_KEY`): Used for GPT models (e.g., `gpt-4o`, `o3-mini`).
* **Google Gemini** (`GEMINI_API_KEY`): Used for Gemini models (e.g., `gemini-3.1-pro`, `gemini-flash-latest`).
* **Groq** (`GROQ_API_KEY`): Used for Llama and Mixtral models.
* **Mistral** (`MISTRAL_API_KEY`): Used for Mistral Large and Codestral models.
* **Cohere** (`COHERE_API_KEY`): Used for Command R+ models.

### Optional Requirements
* **Node.js & npm**: `node >= 18` and `npm >= 9`. Required only if you intend to run the React frontend or compile the Electron desktop app from source.
* **Playwright**: Required only if you plan to enable the `browser-validator` for recording visual walkthrough videos.

---

## Installation

You can run `talon-agent` in standalone developer mode (CLI / Server) or build/install the desktop app.

### 1. Developer CLI / Server Installation

Clone the repository and set up a virtual environment:

```bash
# Clone the repository
git clone https://github.com/mjkgreen/talon.git
cd talon

# Create and activate a virtual environment
python -m venv venv

# On macOS / Linux:
source venv/bin/activate

# On Windows (Command Prompt):
.\venv\Scripts\activate

# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
```

Install the package and its dependencies:

```bash
# Basic installation (CLI and Core Agent only)
pip install -e .

# Full installation (including testing packages and browser validator)
pip install -e ".[dev,browser]"
```

Configure your environment file:

```bash
# Copy template and edit with your API keys and configuration
cp .env.example .env
```

### 2. Browser Validator Setup

If you want to use the automated Playwright visual validation feature, make sure the `browser` optional dependencies are installed, then run:

```bash
pip install playwright
playwright install chromium
```

To enable this feature, configure your `.env` file with:

```bash
BROWSER_VALIDATOR_ENABLED=true
```

### 3. Building the Desktop App from Source

The `electron/` directory contains an Electron wrapper that compiles the React frontend and packages the FastAPI backend into a single, self-contained desktop installation.

To package and build the desktop app locally:

```bash
# 1. Build the React UI
cd ui
npm ci
npm run build
cd ..

# 2. Bundle the Python server with PyInstaller
pyinstaller talon-server.spec   # outputs dist/talon-server (or talon-server.exe)

# 3. Build the Electron installer
cd electron
npm install
npm run build:mac   # For macOS (builds .dmg / .app)
# or npm run build:win   # For Windows (builds .exe installer)
# or npm run build:linux # For Linux (builds .AppImage / .deb)
```

The compiled installers will land in the `electron/release/` directory.

### 4. GitHub OAuth Setup (Desktop)

To use GitHub integrations (OAuth Login and PR Creation) inside the local desktop app, register an OAuth application on GitHub (`github.com/settings/developers`) with:
* **Homepage URL**: `http://localhost`
* **Callback URL**: `talon://oauth-callback`

Once registered, add the client credentials to your `.env` file:

```bash
GITHUB_CLIENT_ID=your_client_id_here
GITHUB_CLIENT_SECRET=your_client_secret_here
```

---

## CLI Usage

`talon-agent` provides a versatile CLI with subcommands for triggering loops, checking active workspaces, auditing logs, cleaning up disk space, and hosting webhooks.

### Commands Reference

| Command   | Arguments  | Flags                                                 | Description                                                                    |
| :-------- | :--------- | :---------------------------------------------------- | :----------------------------------------------------------------------------- |
| `run`     | `"<goal>"` | `--working-dir <path>`, `--url <url>`, `--skip-board` | Decomposes and executes a development task in an isolated workspace.           |
| `list`    | None       | None                                                  | Displays a summary table of all previous and active runs with their statuses.  |
| `review`  | `<run-id>` | None                                                  | Dumps the full detailed `state.json` file of a run in raw JSON to stdout.      |
| `cleanup` | `<run-id>` | None                                                  | Deletes the isolated workspace directory of a run if it was successfully kept. |
| `serve`   | None       | `--port <port_number>`                                | Starts the FastAPI webhook listener to process issues from Linear and GitHub.  |

### Flag Details
* `--working-dir <path>`: Points the sub-agents to an existing local codebase repository. If not specified, the system starts with a fresh, empty workspace.
* `--url <url>`: Used by the Playwright validator to determine which local/staging site to navigate, test, and record.
* `--skip-board`: Instructs the agent to bypass updating any board integrations (e.g., Linear, GitHub Projects) upon passing.
* `--port <port_number>`: Port on which the webhook FastAPI server will listen. Defaults to `8080`.

### Command Examples

#### 1. Executing a Standalone Coding Goal
```bash
talon run "Add a /health endpoint to the Flask app"
```

#### 2. Running an Agent Loop on an Existing Project Workspace with Browser Validation
```bash
talon run "Fix CSS button alignment on the homepage" --working-dir ../my-frontend-app --url http://localhost:3000
```

#### 3. Listing Completed and Active Runs
```bash
talon list
```

#### 4. Auditing a Completed Run
```bash
talon review run-20241024-1234
```

#### 5. Cleaning Up Workspace Files After a Successful Run
```bash
talon cleanup run-20241024-1234
```

#### 6. Launching the Webhook Server
```bash
talon serve --port 8080
```

### Workspace Isolation

To prevent concurrent agent runs from clobbering each other, every execution run receives its own sandboxed workspace.

| `--working-dir`     | Behavior                                                                                                                 |
| :------------------ | :----------------------------------------------------------------------------------------------------------------------- |
| **Not set**         | A fresh, empty directory is created at `workspace/<run-id>/`.                                                            |
| **Plain directory** | The entire directory contents are copied into `workspace/<run-id>/`.                                                     |
| **Git repository**  | An isolated branch named `talon/<goal-slug>-<short-id>` is created via `git worktree add` to preserve the parent repository structure. |

* **On Success (Pass)**: The workspace is kept intact at `workspace/<run-id>/` to allow manual verification, inspection, or manual PR creation. Use `talon cleanup <run-id>` to remove it later.
* **On Failure (Fail)**: The workspace directory is automatically cleaned up and deleted to avoid cluttering your filesystem.

---

## Environment Variables Reference

Below is a complete reference of the configuration variables supported by `talon-agent`. Copy `.env.example` to `.env` and fill in your values.

| Variable                    | Type    | Default / Example             | Description                                                             |
| :-------------------------- | :------ | :---------------------------- | :---------------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`         | String  | `sk-ant-...`                  | API key to enable `anthropic/*` models (e.g., Claude 3.5 Sonnet).       |
| `OPENAI_API_KEY`            | String  | `sk-...`                      | API key to enable `openai/*` models (e.g., GPT-4o, o3-mini).            |
| `GEMINI_API_KEY`            | String  | `...`                         | API key to enable `gemini/*` models (e.g., Gemini 2.0 Flash).           |
| `GROQ_API_KEY`              | String  | `...`                         | API key to enable `groq/*` models (e.g., Llama 3).                      |
| `MISTRAL_API_KEY`           | String  | `...`                         | API key to enable `mistral/*` models (e.g., Mistral Large).             |
| `COHERE_API_KEY`            | String  | `...`                         | API key to enable `cohere/*` models (e.g., Command R+).                 |
| `PYTHONUTF8`                | Integer | `1`                           | Forces Windows Python to use UTF-8 encoding. Safe on all platforms.     |
| `AGENT_MODEL`               | String  | `gemini/gemini-flash-latest`     | Global model override. If set, all agent roles default to this model.   |
| `ORCHESTRATOR_MODEL`        | String  | `gemini/gemini-pro-latest`    | Model override for the Orchestrator (goal decomposition).               |
| `SUBAGENT_MODEL`            | String  | `anthropic/claude-sonnet-4-6` | Model override for the Sub-agent (code writing and tool-use loop).      |
| `REVIEWER_MODEL`            | String  | `gemini/gemini-pro-latest`    | Model override for the Reviewer (quality gate).                         |
| `REFINER_MODEL`             | String  | `gemini/gemini-flash-latest`  | Model override for the Refiner (fix synthesis and next-loop planning).  |
| `MAX_ITERATIONS`            | Integer | `3`                           | Maximum number of try-review-refine iterations before failing a run.    |
| `PLANNER_MAX_TURNS`         | Integer | `500`                         | Maximum tool-call turns the planner may use to explore the workspace.   |
| `REVIEWER_MAX_TOOL_TURNS`   | Integer | `500`                         | Maximum tool-call turns the reviewer may use to inspect the workspace.  |
| `AGENT_MAX_TOKENS`          | Integer | `8096`                        | Maximum token ceiling for single LLM generation calls.                  |
| `WORKSPACE_DIR`             | String  | `./workspace`                 | Base directory under which individual run workspaces are generated.     |
| `RUNS_DIR`                  | String  | `./runs`                      | Directory where full execution histories and state files are saved.     |
| `LINEAR_API_KEY`            | String  | `lin_api_...`                 | API key used to query and update cards on Linear.                       |
| `LINEAR_TEAM_ID`            | String  | `...`                         | Linear team ID where issues are monitored and processed.                |
| `GITHUB_TOKEN`              | String  | `ghp_...`                     | Personal Access Token to create branches, open PRs, and update boards.  |
| `GITHUB_REPO`               | String  | `owner/repo`                  | GitHub target repository in `owner/repo` format.                        |
| `GITHUB_BASE_BRANCH`        | String  | `main`                        | Base branch to target when creating Pull Requests.                      |
| `GITHUB_PROJECT_NUMBER`     | Integer | `1`                           | GitHub Projects v2 board number from the workspace project URL.         |
| `BROWSER_VALIDATOR_ENABLED` | Boolean | `false`                       | Set to `true` to enable Playwright-based UI testing and recording.      |
| `WEBHOOK_LABEL`             | String  | `agent-task`                  | Issue label required to trigger a run (set to `""` to accept all).      |
| `LINEAR_WEBHOOK_SECRET`     | String  | `...`                         | Secret key to verify incoming HMAC signature webhooks from Linear.      |
| `GITHUB_WEBHOOK_SECRET`     | String  | `...`                         | Secret key to verify incoming HMAC signature webhooks from GitHub.      |
| `MAX_CONCURRENT_RUNS`       | Integer | `3`                           | Maximum simultaneous agent execution tasks on the webhook server.       |
| `GITHUB_CLIENT_ID`          | String  | `...`                         | Client ID for the registered GitHub OAuth application.                  |
| `GITHUB_CLIENT_SECRET`      | String  | `...`                         | Client Secret for the registered GitHub OAuth application.              |
| `BOARD_DB_PATH`             | String  | `~/.local/share/...`          | Path to local SQLite database tracking runs. Defaults to platform dirs. |

### Model Configuration Modes

`talon-agent` provides three flexible modes to configure which LLMs power which parts of the agentic pipeline:

#### 1. Auto Selection Mode (Recommended)
Leave all model environment variables (`AGENT_MODEL`, `ORCHESTRATOR_MODEL`, etc.) unset. The system will automatically detect which API keys are available in your `.env` file and route the highest quality model to each role.

Auto-selection priority per role:

| Role           | Task               | Prefers                              |
| :------------- | :----------------- | :----------------------------------- |
| `orchestrator` | Goal decomposition | Opus → o3 → Gemini Pro → Sonnet      |
| `subagent`     | Code writing       | Sonnet → GPT-4o → Gemini Pro → Flash |
| `reviewer`     | Quality gate       | Opus → o3 → Gemini Pro → Sonnet      |
| `refiner`      | Fix planning       | Sonnet → Flash → GPT-4o → Haiku      |

#### 2. Global Override Mode
Force all agent roles to use a single model:
```bash
# .env
AGENT_MODEL=gemini/gemini-flash-latest```

#### 3. Per-Role Overrides Mode
Assign specific models to specific roles for fine-grained cost, speed, and capability tuning:
```bash
# .env
ORCHESTRATOR_MODEL=openai/o3              # Heavy reasoning
SUBAGENT_MODEL=anthropic/claude-sonnet-4-6  # High-quality coding
REVIEWER_MODEL=openai/o3                  # Strict review analysis
REFINER_MODEL=gemini/gemini-flash-latest     # Fast planning synthesis
```

Per-role overrides take precedence over the global `AGENT_MODEL`, which in turn takes precedence over the `Auto` selection mode.

---

## Webhook Listener

Run `talon serve` on your server once to listen for incoming tasks and trigger automated agent runs whenever specified labels are applied to issues.

The webhook server manages a run queue up to `MAX_CONCURRENT_RUNS` (default 3) to execute simultaneous agent processes. A health check is available at `/health` and OpenAPI documentation can be inspected at `/docs`.

### Linear Setup

1. Go to **Linear** → **Settings** → **API** → **Webhooks**.
2. Click **Add Webhook** and configure the endpoint: `https://your-domain.com/webhook/linear`.
3. Set `LINEAR_WEBHOOK_SECRET` in your `.env` to verify incoming payload signatures.
4. Ensure target issues carry the label `agent-task` (or whatever label is defined under `WEBHOOK_LABEL`).

### GitHub Setup

1. In your target repository, go to **Settings** → **Webhooks** → **Add Webhook**.
2. Specify Payload URL: `https://your-domain.com/webhook/github`.
3. Set Content type to `application/json`.
4. Select individual events: **Issues**.
5. Set `GITHUB_WEBHOOK_SECRET` in your `.env` to verify signatures.
6. Issues carrying the label `agent-task` (or matching `WEBHOOK_LABEL`) will automatically spawn agent runs when opened or updated.

---

## Claude Code Slash Commands

If you interact with `talon-agent` workflows from within interactive terminal assistants, the following internal sub-modules and functions correspond to specific slash commands:

| Command              | Description                                                                            |
| :------------------- | :------------------------------------------------------------------------------------- |
| `/task-executor`     | Decomposes the goal and runs concurrent sub-agents in parallel.                        |
| `/self-reviewer`     | Reviews file changes, runs test suites, and outputs a pass/fail score.                 |
| `/refiner`           | Analyzes test output/warnings and structures the next iteration's action plan.         |
| `/browser-validator` | Initiates the Playwright session, performs navigation checks, and saves the recording. |
| `/board-updater`     | Connects to Linear/GitHub API endpoints and uploads run statuses and files.            |

---

## Codebase Directory Structure

| Path                                | Purpose                                                                                      |
| :---------------------------------- | :------------------------------------------------------------------------------------------- |
| `talon/config.py`                   | Model resolution logic: handles overrides, fallback, and key scanning.                       |
| `talon/providers/litellm_p.py`      | LiteLLM client wrapper providing normalized tool-calling APIs across vendors.                |
| `talon/tools.py`                    | Implementation of sub-agent tools: `read_file`, `write_file`, `run_command`, `search_files`. |
| `talon/types.py`                    | Pydantic model schemas: `RunState`, `ExecutorResult`, `PhaseResult`, `ReviewFeedback`, etc.  |
| `talon/skills/planner.py`           | Workspace-exploring planner: uses read-only tools then outputs a multi-phase plan.           |
| `talon/skills/task_executor.py`     | Phase-sequential, intra-phase-parallel execution engine.                                     |
| `talon/skills/self_reviewer.py`     | Reviewer with plan-aware success-criteria verification loop.                                 |
| `talon/skills/refiner.py`           | Logic to distill logs into actionable developer instructions.                                |
| `talon/skills/browser_validator.py` | Playwright interface logic for visually recording page runs.                                 |
| `talon/skills/board_updater.py`     | Connector logic to post update summaries to board integrations.                              |
| `talon/loop.py`                     | Orchestrates the top-level main execution pipeline loop; streams phase-complete events.      |
| `talon/main.py`                     | Defines the local user CLI interface.                                                        |
| `talon/server_entry.py`             | PyInstaller standalone entry point. Finds ports, spawns fastapi.                             |
| `talon-server.spec`                 | Spec configuration file for building Python server binaries via PyInstaller.                 |
| `electron/`                         | Node project containing main/preload scripts for the Electron desktop wrapper.               |
| `runs/<id>/state.json`              | Stores full execution logs, agent thoughts, and tools history for each run.                  |
| `workspace/`                        | Local directory containing generated workspace checkouts or copied folders.                  |

---

## Changelog

### 0.6.0

**Workspace-exploring planner** — The planner now runs a full tool-use loop before producing a plan. It calls `list_files`, `read_file`, and `search_files` (read-only) to understand the existing codebase structure, conventions, and tech stack, then generates a phased plan grounded in what already exists. Configurable via `PLANNER_MAX_TURNS` (default 500).

**Phased execution** — The executor no longer treats a goal as a single flat list of subtasks. It now iterates through the planner's phases sequentially. Within each phase, subtasks run in parallel as before. Each phase receives the aggregated output of prior phases as context, preventing rework and intra-phase dependency conflicts.

**Incremental UI progress** — The loop emits a `on_phase_complete` callback after each phase finishes, which immediately persists partial state and pushes a WebSocket update. The task detail panel in the UI now shows each phase with a status indicator (pending / running / complete) and updates in real time as execution progresses, rather than waiting for the full iteration to finish.

**Plan-aware reviewer** — The self-reviewer now receives the full plan (approach, phases, constraints, success criteria) and is instructed to verify each success criterion explicitly, not just the overall goal description.

**Branch selection** — Projects that use a GitHub repository can now target a specific branch. The setup wizard (step 4) shows a branch dropdown that loads all branches for the selected repo and pre-selects the repo default. The selected branch is stored in the project database and passed through to `git clone --branch --single-branch` when the workspace is set up. A branch badge is shown in the main toolbar for the active project.

**UI polish** — Task creation now shows a spinner and disables the submit button while the API call is in flight. Subtasks in the task detail panel show expandable output sections (click the chevron to inspect agent output for any subtask).

**New API endpoint** — `GET /api/github/repos/{owner}/{repo}/branches` returns the list of branches and the repo default branch.

**Goal-based branch naming** — Worktree and PR branches are now named `talon/<goal-slug>-<short-id>` (e.g. `talon/add-health-endpoint-a3f2b1`) instead of the generic `agent/run-<id>`. The slug is derived from the goal text, making branches immediately recognisable in GitHub.

**Reviewer tool turn limit raised** — `REVIEWER_MAX_TOOL_TURNS` default increased from 50 to 500, matching the planner, so the reviewer can thoroughly inspect large workspaces without hitting the limit.

**GitHub token priority** — `board_updater` and `pr_creator` now prefer the token stored in the app's settings database over the `GITHUB_TOKEN` environment variable, so the in-app GitHub login always takes precedence.

**Windows UTF-8 console fix** — `talon` CLI now calls `SetConsoleOutputCP(65001)` (via `ctypes`) before rewrapping `stdout`/`stderr`, correctly switching the Windows console code page to UTF-8 and preventing garbled box-drawing characters from Rich.

---

### 0.5.x

- 0.5.2: fix reviewer JSON failures, raise tool turn limit, add limit hints in UI
- 0.5.1: bump version
- 0.5.0: bundle tiktoken/litellm/certifi data in PyInstaller exe; fix cl100k_base encoding

---

## Roadmap

- [ ] **Browser Validator**: Support customized, goal-specific browser navigation steps via subtask definitions.
- [ ] **Board Updater**: Add direct integration with GitHub Projects v2 boards.
- [ ] **Board Updater**: Implement automatic creation of pull requests directly from workspace changes.
- [ ] **API Optimizations**: Introduce rate-limiting controls (`asyncio_throttle`) for concurrent agent API calls.
- [ ] **Automated Test Suite**: Expand unit and integration test coverage.