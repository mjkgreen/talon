"""
workspace-starter
-----------------
Autonomous development server manager.

Detects and starts a local dev server in the workspace, resolves its URL
dynamically (log scanning + port probing), and provides lifecycle cleanup.

Port conflicts across concurrent runs are managed via a module-level
in-process port registry with asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
from pathlib import Path

from rich.console import Console

console = Console()

_DEFAULT_PROBE_PORTS = [3000, 5173, 8000, 8080, 4000, 4200, 5000, 8888]
STARTUP_TIMEOUT = int(os.getenv("WORKSPACE_STARTER_TIMEOUT", "60"))

_claimed_ports: set[int] = set()
_port_lock: asyncio.Lock | None = None


class StartupTimeoutError(Exception):
    """Raised when the dev server does not become reachable within STARTUP_TIMEOUT."""


def _get_port_lock() -> asyncio.Lock:
    global _port_lock
    if _port_lock is None:
        _port_lock = asyncio.Lock()
    return _port_lock


def _find_venv_python(workspace: Path) -> str | None:
    for candidate in [
        workspace / ".venv" / "Scripts" / "python.exe",  # Windows
        workspace / ".venv" / "bin" / "python",  # Unix
        workspace / "venv" / "Scripts" / "python.exe",
        workspace / "venv" / "bin" / "python",
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def detect_start_command(workspace_dir: str) -> str | None:
    """Inspect workspace_dir and return an appropriate start command, or None."""
    d = Path(workspace_dir)

    pkg = d / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if "dev" in scripts:
                return "npm run dev"
            if "start" in scripts:
                return "npm run start"
        except (json.JSONDecodeError, OSError):
            pass

    python = _find_venv_python(d) or "python"

    for entry in ("main.py", "app.py", "server.py"):
        if (d / entry).exists():
            module = entry[:-3]
            return f"{python} -m uvicorn {module}:app --reload"

    if (d / "manage.py").exists():
        return f"{python} manage.py runserver"

    if (d / "pyproject.toml").exists() or (d / "requirements.txt").exists():
        return f"{python} -m uvicorn app:app --reload"

    if (d / "go.mod").exists():
        return "go run ."

    return None


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(("127.0.0.1", port)) == 0


async def _claim_port(preferred: list[int]) -> int:
    lock = _get_port_lock()
    async with lock:
        for port in preferred:
            if port not in _claimed_ports and not _is_port_in_use(port):
                _claimed_ports.add(port)
                return port
        # Fallback: let the OS assign an ephemeral port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            _claimed_ports.add(port)
            return port


async def _release_port(port: int) -> None:
    lock = _get_port_lock()
    async with lock:
        _claimed_ports.discard(port)


async def _scan_logs_for_url(proc: asyncio.subprocess.Process, timeout: float) -> str | None:
    """Read stdout and return the first localhost URL line found."""
    pattern = re.compile(r"https?://(?:localhost|127\.0\.0\.1):\d+", re.IGNORECASE)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            remaining = deadline - loop.time()
            line_bytes = await asyncio.wait_for(
                proc.stdout.readline(),  # type: ignore[union-attr]
                timeout=min(remaining, 2.0),
            )
            line = line_bytes.decode(errors="replace")
            match = pattern.search(line)
            if match:
                return match.group(0)
        except asyncio.TimeoutError:
            continue
        except Exception:
            break
    return None


async def _poll_port(port: int, timeout: float) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if _is_port_in_use(port):
            return True
        await asyncio.sleep(0.5)
    return False


async def _resolve_url(proc: asyncio.subprocess.Process, port: int, startup_timeout: float) -> str:
    """Race log scanning against port polling; return the resolved URL."""
    log_task = asyncio.create_task(_scan_logs_for_url(proc, startup_timeout))
    poll_task = asyncio.create_task(_poll_port(port, startup_timeout))

    done, pending = await asyncio.wait(
        {log_task, poll_task},
        timeout=startup_timeout,
        return_when=asyncio.FIRST_COMPLETED,
    )

    for t in pending:
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    if log_task in done:
        try:
            url = log_task.result()
            if url:
                return url
        except Exception:
            pass

    if poll_task in done:
        try:
            if poll_task.result():
                return f"http://localhost:{port}"
        except Exception:
            pass

    raise StartupTimeoutError(f"Dev server did not start within {startup_timeout}s on port {port}")


def _parse_env_file(path: str) -> dict[str, str]:
    """Parse a .env file into a dict, ignoring comments and blank lines."""
    result: dict[str, str] = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            if key:
                result[key] = value
    except Exception as e:
        console.print(f"[yellow]workspace-starter[/yellow] could not read env file {path}: {e}")
    return result


async def start_workspace_server(
    workspace_dir: str,
    extra_env: dict[str, str] | None = None,
    start_command: str | None = None,
    env_file: str | None = None,
) -> tuple[asyncio.subprocess.Process, str, int]:
    """
    Auto-detect and start a development server in workspace_dir.

    Returns (process, url, port).  Always call stop_workspace_server() in a
    finally block to terminate the subprocess and free the port.

    Raises:
        StartupTimeoutError: if the server is not reachable within STARTUP_TIMEOUT.
        ValueError: if no start command can be detected and none was provided.
    """
    cmd = start_command or detect_start_command(workspace_dir)
    if not cmd:
        raise ValueError(
            f"Could not detect a start command in {workspace_dir}. "
            "Set start_command in project settings."
        )

    port = await _claim_port(_DEFAULT_PROBE_PORTS)
    file_env = _parse_env_file(env_file) if env_file else {}
    env = {**os.environ, **file_env, "PORT": str(port), **(extra_env or {})}

    console.print(
        f"\n[bold cyan]workspace-starter[/bold cyan] launching [dim]{cmd}[/dim] on port {port}"
    )

    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=workspace_dir,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        url = await _resolve_url(proc, port, float(STARTUP_TIMEOUT))
    except StartupTimeoutError:
        proc.terminate()
        await _release_port(port)
        raise

    console.print(f"  [green]ready[/green] {url}")
    return proc, url, port


async def stop_workspace_server(proc: asyncio.subprocess.Process, port: int) -> None:
    """Terminate the dev server subprocess and release its port."""
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    await _release_port(port)
    console.print("[dim]workspace-starter: server stopped[/dim]")
