from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/api/runs/{run_id}")
async def get_run_state(run_id: str):
    run_dir = os.path.join(os.getenv("RUNS_DIR", "./runs"), run_id)
    state_file = os.path.join(run_dir, "state.json")
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)

    runs_dir_path = os.getenv("RUNS_DIR", "./runs")
    if os.path.exists(runs_dir_path):
        for item in os.listdir(runs_dir_path):
            if item.startswith(run_id) or run_id.startswith(item):
                alt_state = os.path.join(runs_dir_path, item, "state.json")
                if os.path.exists(alt_state):
                    with open(alt_state, "r") as f:
                        return json.load(f)

    raise HTTPException(status_code=404, detail=f"Run state not found for {run_id}")


@router.get("/api/runs/{run_id}/video")
async def get_run_video(run_id: str):
    run_dir = os.path.join(os.getenv("RUNS_DIR", "./runs"), run_id)
    state_file = os.path.join(run_dir, "state.json")
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            video_path = data.get("video_path")
            if video_path and os.path.exists(video_path):
                return FileResponse(video_path)
    raise HTTPException(status_code=404, detail="Video not found")


@router.get("/api/runs/{run_id}/gif")
async def get_run_gif(run_id: str):
    run_dir = os.path.join(os.getenv("RUNS_DIR", "./runs"), run_id)
    state_file = os.path.join(run_dir, "state.json")
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            br = data.get("browser_result") or {}
            gif_path = br.get("gif_path")
            if gif_path and os.path.exists(gif_path):
                return FileResponse(gif_path, media_type="image/gif")
    raise HTTPException(status_code=404, detail="GIF not found")


@router.get("/api/runs/{run_id}/screenshots/{filename}")
async def get_run_screenshot(run_id: str, filename: str):
    """Serve individual screenshot PNGs from the run's video directory."""
    from pathlib import Path as _Path
    runs_dir = os.getenv("RUNS_DIR", "./runs")
    run_dir = _Path(os.path.realpath(os.path.join(runs_dir, run_id)))
    screenshot_path = _Path(os.path.realpath(os.path.join(str(run_dir), filename)))
    if not screenshot_path.is_relative_to(run_dir):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not screenshot_path.exists() or screenshot_path.suffix != ".png":
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(screenshot_path), media_type="image/png")
