"""
Tests for talon/server_entry.py — the PyInstaller binary entry point.

These tests catch the class of bug where the PORT announcement never reaches
Electron (causing the 30-second startup timeout). The key regression was
PyInstaller console=False setting sys.stdout=None on Windows, which prevented
print(f"PORT:{port}", flush=True) from ever reaching the parent process.

Run before every release build:
    pytest tests/test_server_entry.py -v
"""

import http.client
import io
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_line_with_timeout(stream, timeout: float = 10.0) -> str | None:
    """Read one line from *stream* with a wall-clock timeout.

    Returns the decoded, stripped line, or None if the timeout expires first.
    Works on all platforms (avoids select() which is unreliable on Windows pipes).
    """
    result: list[bytes] = []
    ready = threading.Event()

    def _reader() -> None:
        try:
            result.append(stream.readline())
        except Exception:
            result.append(b"")
        ready.set()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    if not ready.wait(timeout):
        return None
    return result[0].decode("utf-8", errors="replace").strip() if result else None


def _spawn_server(tmp_db: str) -> subprocess.Popen:
    """Spawn server_entry as a subprocess the same way Electron does."""
    return subprocess.Popen(
        [sys.executable, "-m", "talon.server_entry"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "BOARD_DB_PATH": tmp_db,
        },
    )


# ---------------------------------------------------------------------------
# _find_free_port()
# ---------------------------------------------------------------------------

class TestFindFreePort:
    def test_returns_integer(self):
        from talon.server_entry import _find_free_port
        assert isinstance(_find_free_port(), int)

    def test_port_in_valid_range(self):
        from talon.server_entry import _find_free_port
        port = _find_free_port()
        assert 1024 <= port <= 65535

    def test_port_is_actually_free(self):
        """The returned port must be bindable immediately."""
        from talon.server_entry import _find_free_port
        port = _find_free_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))  # raises if already in use

    def test_successive_calls_usually_differ(self):
        from talon.server_entry import _find_free_port
        ports = {_find_free_port() for _ in range(5)}
        assert len(ports) > 1


# ---------------------------------------------------------------------------
# stdout reconstruction (the console=False / sys.stdout=None regression)
# ---------------------------------------------------------------------------

class TestStdoutReconstruction:
    """
    Verify the fd-1 reconstruction logic in server_entry.py works.

    On Windows with PyInstaller console=False the bootloader sets
    sys.stdout=None.  server_entry.py reconstructs it from fd 1.  If that
    reconstruction fails silently (the except-pass block) PORT is never sent.
    These tests verify the underlying mechanism is sound without touching the
    real sys.stdout of the test process.
    """

    def test_fd1_is_open(self):
        """fd 1 must be a valid, open file descriptor."""
        # os.fstat raises OSError if the fd is closed.
        os.fstat(1)

    def test_fd1_fileio_constructable(self):
        """io.FileIO(1, closefd=False) must not raise."""
        fio = io.FileIO(1, closefd=False)
        assert fio is not None
        # Do NOT close — closefd=False means we don't own it.

    def test_fd1_fileio_mode_w_is_writable(self):
        """FileIO(1, mode='w') must advertise itself as writable.

        The default mode='r' creates a read-only wrapper — a latent bug that
        would make print() raise UnsupportedOperation even after reconstruction.
        We check writable() rather than actually writing because pytest may
        have redirected fd 1 to a capture pipe.
        """
        fio = io.FileIO(1, mode="w", closefd=False)
        assert fio.writable(), "FileIO(1, mode='w') should be writable"

        wrapper = io.TextIOWrapper(
            fio, encoding="utf-8", errors="replace", line_buffering=True,
        )
        assert wrapper.writable()


# ---------------------------------------------------------------------------
# Full subprocess smoke tests (mirrors what Electron does at launch)
# ---------------------------------------------------------------------------

class TestServerEntrySubprocess:
    """
    Spawn server_entry as a child process and interact with it exactly as
    Electron's main.js does: read PORT from stdout, then poll /health.
    """

    def test_port_announced_before_timeout(self, tmp_path):
        """PORT:<n> must appear on stdout within 10 seconds of process start."""
        proc = _spawn_server(str(tmp_path / "board.db"))
        try:
            line = _read_line_with_timeout(proc.stdout, timeout=10)
            if line is None:
                stderr = proc.stderr.read(2000).decode(errors="replace")
                pytest.fail(
                    f"No output from server_entry within 10 s.\nstderr: {stderr}"
                )
            assert line.startswith("PORT:"), (
                f"Expected 'PORT:<n>' but got: {line!r}\n"
                f"stderr: {proc.stderr.read(2000).decode(errors='replace')}"
            )
            port = int(line.split(":", 1)[1])
            assert 1024 <= port <= 65535
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_health_endpoint_responds_200(self, tmp_path):
        """
        Full Electron-style startup: spawn → read PORT → poll /health → 200 OK.

        This is the exact sequence that causes the 30-second timeout when
        broken.  If PORT is never announced (sys.stdout=None on Windows) or if
        the server never becomes healthy, this test fails immediately instead of
        waiting 30 seconds.
        """
        proc = _spawn_server(str(tmp_path / "board.db"))
        port = None
        try:
            # Step 1: read PORT announcement from stdout
            line = _read_line_with_timeout(proc.stdout, timeout=10)
            assert line is not None, "No stdout from server_entry within 10 s"
            assert line.startswith("PORT:"), f"Unexpected first line: {line!r}"
            port = int(line.split(":", 1)[1])

            # Step 2: poll /health until the server is accepting connections
            deadline = time.monotonic() + 20
            last_exc: Exception | None = None
            while time.monotonic() < deadline:
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                    conn.request("GET", "/health")
                    resp = conn.getresponse()
                    assert resp.status == 200, f"/health returned {resp.status}"
                    body = resp.read()
                    assert b"ok" in body.lower()
                    return  # success
                except Exception as exc:
                    last_exc = exc
                    time.sleep(0.3)
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            stderr_tail = proc.stderr.read(2000).decode(errors="replace")
            pytest.fail(
                f"Server on port {port} never became healthy within 20 s.\n"
                f"Last error: {last_exc}\nstderr: {stderr_tail}"
            )
        finally:
            proc.terminate()
            proc.wait(timeout=5)
