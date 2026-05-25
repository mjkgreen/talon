"""Tests for GET /api/runs/{run_id}/screenshots/{filename}."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from talon.server import app

client = TestClient(app, raise_server_exceptions=False)


def _make_run(tmp_path: Path, run_id: str, filename: str, content: bytes = b"PNG") -> Path:
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    screenshot = run_dir / filename
    screenshot.write_bytes(content)
    return screenshot


class TestScreenshotEndpoint:
    def test_serves_valid_png(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUNS_DIR", str(tmp_path))
        _make_run(tmp_path, "abc123", "screenshot-00-home.png")
        resp = client.get("/api/runs/abc123/screenshots/screenshot-00-home.png")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    def test_returns_404_for_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUNS_DIR", str(tmp_path))
        (tmp_path / "abc123").mkdir()
        resp = client.get("/api/runs/abc123/screenshots/nonexistent.png")
        assert resp.status_code == 404

    def test_returns_404_for_non_png(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUNS_DIR", str(tmp_path))
        _make_run(tmp_path, "abc123", "proof.webm", b"WEBM")
        resp = client.get("/api/runs/abc123/screenshots/proof.webm")
        assert resp.status_code == 404

    def test_rejects_invalid_run_id(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUNS_DIR", str(tmp_path))
        resp = client.get("/api/runs/../../etc/screenshots/passwd.png")
        assert resp.status_code in (400, 404)

    def test_rejects_path_traversal_in_filename(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUNS_DIR", str(tmp_path))
        (tmp_path / "abc123").mkdir()
        resp = client.get("/api/runs/abc123/screenshots/../../../etc/passwd.png")
        assert resp.status_code in (400, 404)

    def test_rejects_run_id_with_slash(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUNS_DIR", str(tmp_path))
        resp = client.get("/api/runs/abc%2F..%2Fetc/screenshots/x.png")
        assert resp.status_code in (400, 404)
