Run the **browser-validator** skill: spin up Playwright, navigate the app, and record a video proof-of-work.

## Usage

```
/browser-validator <app-url>
```

**$ARGUMENTS** is the URL of the running application to validate (e.g. `http://localhost:3000`).

## What it does

1. Launches a Chromium browser via Playwright
2. Navigates the app URL
3. Waits for network idle, takes a screenshot
4. Records a `.webm` video of the session
5. Saves video to `./runs/<run-id>/proof.webm`

## Enable it

```bash
pip install playwright
playwright install chromium
```

Then add to `.env`:

```
BROWSER_VALIDATOR_ENABLED=true
```

## Run with the full loop

```bash
python -m src.main run "your goal" --url http://localhost:3000
```

The browser-validator only runs if the loop reaches `pass` status.

## Phase 2 additions (TODO)

- Goal-specific navigation steps (e.g. "log in, create a post, verify it appears")
- Visual regression comparison
- Accessibility checks with axe-core
