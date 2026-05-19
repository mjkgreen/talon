"""
Entry point for the PyInstaller bundle and Electron sidecar.

Finds a free TCP port, announces it on stdout so Electron can connect,
then starts uvicorn. Handles SIGTERM / Windows CTRL_BREAK_EVENT for
clean shutdown.
"""
from __future__ import annotations

import signal
import socket
import sys


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    port = _find_free_port()

    # Announce the port immediately — Electron reads this line before showing the window.
    print(f"PORT:{port}", flush=True)

    # Graceful shutdown on SIGTERM (Linux/macOS) and Ctrl+C.
    def _shutdown(signum, frame):  # noqa: ANN001
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    import uvicorn
    from talon.server import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        # Disable the default startup/shutdown log lines to keep stdout clean
        # (Electron only reads the PORT: line).
        access_log=False,
    )


if __name__ == "__main__":
    main()
