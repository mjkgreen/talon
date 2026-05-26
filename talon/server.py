"""
FastAPI Server → API, Webhooks, WebSockets, and UI serving.

Start:
  talon serve [--port 8080]
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from rich.console import Console

from talon import db
from talon.background import _reset_stalled_verifications
from talon.browser_setup import ensure_chromium
from talon.routers import auth, github, issues, projects, runs, settings, webhooks, websocket
from talon.routers.settings import apply_db_settings_to_env
from talon.routers.websocket import broadcast_issue_update

console = Console()

app = FastAPI(title="Talon Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(websocket.router)
app.include_router(settings.router)
app.include_router(projects.router)
app.include_router(auth.router)
app.include_router(github.router)
app.include_router(runs.router)
app.include_router(issues.router)
app.include_router(webhooks.router)


@app.on_event("startup")
async def startup_event():
    await db.init_db()
    await apply_db_settings_to_env()
    _reset_stalled_verifications()
    stalled = await db.reset_stalled_issues()
    for issue_id in stalled:
        await broadcast_issue_update(issue_id)
    asyncio.ensure_future(ensure_chromium())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# --- UI Serving ---

ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "dist")

if os.path.exists(ui_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(ui_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_ui(full_path: str):
        # API paths that escaped routing (e.g. via path traversal / percent-encoding)
        # must not be silently served as the SPA index.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        # Paths containing "/screenshots/" that are not valid SPA routes escaped routing —
        # they are API sub-resources that should not be served as the SPA index.
        if "/screenshots/" in full_path:
            raise HTTPException(status_code=404, detail="Not found")
        path = os.path.join(ui_dir, full_path)
        if os.path.exists(path) and os.path.isfile(path):
            return FileResponse(path)
        return FileResponse(os.path.join(ui_dir, "index.html"))
