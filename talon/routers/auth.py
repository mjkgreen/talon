from __future__ import annotations

import asyncio
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from talon import db
from talon.routers.websocket import manager

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")


class _GitHubExchangeRequest(BaseModel):
    code: str
    state: str


class _GitHubPollRequest(BaseModel):
    device_code: str


@router.get("/api/auth/github/authorize")
async def github_auth_authorize():
    """Return a GitHub OAuth authorize URL for Electron's system browser."""
    import secrets

    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=400,
            detail=(
                "GITHUB_CLIENT_ID not configured. "
                "Register an OAuth App at github.com/settings/developers."
            ),
        )
    state = secrets.token_urlsafe(16)
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&scope=repo"
        f"&state={state}"
        f"&redirect_uri=talon://oauth-callback"
    )
    return {"url": url, "state": state}


@router.post("/api/auth/github/exchange")
async def github_auth_exchange(body: _GitHubExchangeRequest):
    """Exchange an OAuth code for an access token and save it."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=400,
            detail="GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET not configured.",
        )
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": body.code,
                "redirect_uri": "talon://oauth-callback",
            },
        )
    data = res.json()
    if "access_token" not in data:
        raise HTTPException(
            status_code=400,
            detail=data.get("error_description", "Token exchange failed"),
        )
    await db.set_setting("github_token", data["access_token"])
    await manager.broadcast({"type": "github_auth_complete"})
    return {"status": "complete"}


@router.post("/api/auth/github/start")
async def github_auth_start():
    """Initiate GitHub Device Flow. Returns user_code and verification_uri."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=400,
            detail=(
                "GITHUB_CLIENT_ID not configured. "
                "Register an OAuth App at github.com/settings/developers."
            ),
        )
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://github.com/login/device/code",
            headers={"Accept": "application/json"},
            json={"client_id": GITHUB_CLIENT_ID, "scope": "repo"},
        )
    if res.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to initiate GitHub device flow")
    data = res.json()
    return {
        "device_code": data["device_code"],
        "user_code": data["user_code"],
        "verification_uri": data["verification_uri"],
        "expires_in": data.get("expires_in", 900),
        "interval": data.get("interval", 5),
    }


@router.post("/api/auth/github/poll")
async def github_auth_poll(body: _GitHubPollRequest):
    """Poll GitHub for a device flow token. Saves token to DB on success."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=400, detail="GITHUB_CLIENT_ID not configured")
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                json={
                    "client_id": GITHUB_CLIENT_ID,
                    "device_code": body.device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
        data = res.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub token poll failed: {exc}") from exc
    error = data.get("error")
    if error in ("authorization_pending", "slow_down"):
        return {"status": "pending"}
    if error in ("expired_token", "access_denied"):
        return {"status": "expired"}
    if "access_token" in data:
        await db.set_setting("github_token", data["access_token"])
        await manager.broadcast({"type": "github_auth_complete"})
        return {"status": "complete"}
    return {"status": "error", "detail": error}


@router.get("/api/local/browse")
async def browse_local_folder():
    """Open a native OS folder-picker dialog and return the selected path."""

    def _pick() -> str:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select project folder")
        root.destroy()
        return path or ""

    path = await asyncio.get_running_loop().run_in_executor(None, _pick)
    return {"path": path}
