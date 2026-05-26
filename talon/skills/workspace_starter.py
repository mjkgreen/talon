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


def _detect_js_framework(pkg_data: dict) -> str | None:
    """Return a framework slug from package.json dependency keys."""
    deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
    if "expo" in deps:
        return "expo"
    if "next" in deps:
        return "next"
    if "nuxt" in deps or "nuxt3" in deps:
        return "nuxt"
    if "@angular/core" in deps:
        return "angular"
    if "@sveltejs/kit" in deps:
        return "sveltekit"
    if "svelte" in deps:
        return "svelte"
    if "vite" in deps or "@vitejs/plugin-react" in deps or "@vitejs/plugin-vue" in deps:
        return "vite"
    if "react-scripts" in deps:
        return "cra"
    return None


def _scan_readme_for_command(workspace: Path) -> str | None:
    """Look inside README / CONTRIBUTING for an npm/yarn/pnpm start command."""
    _start_kws = ("dev", "start", "serve", "develop")
    for name in ("README.md", "readme.md", "CONTRIBUTING.md"):
        p = workspace / name
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # Prefer commands inside fenced code blocks first, then bare inline ticks.
        for pattern in (
            r"```(?:bash|sh|shell|console)?\n(.*?)\n```",
            r"`((?:npm run|yarn|pnpm) [\w:-]+)`",
        ):
            for m in re.finditer(pattern, text, re.DOTALL | re.IGNORECASE):
                block = m.group(1)
                for line in block.splitlines():
                    line = line.strip().strip("`$").strip()
                    if any(line.startswith(p) for p in ("npm run", "yarn ", "pnpm ")):
                        if any(kw in line for kw in _start_kws):
                            return line
        break  # only look at the first README found
    return None


def detect_start_command(workspace_dir: str) -> str | None:
    """Inspect workspace_dir and return an appropriate start command, or None."""
    d = Path(workspace_dir)

    pkg = d / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            framework = _detect_js_framework(data)

            # Framework-aware command selection
            if framework == "expo":
                # Expo is a React Native framework; --web serves in browser
                if "web" in scripts:
                    return "npm run web"
                return "npx expo start --web"
            if framework in ("next", "nuxt", "vite", "sveltekit", "svelte"):
                if "dev" in scripts:
                    return "npm run dev"
            if framework == "angular":
                return "npm run start" if "start" in scripts else "npx ng serve"
            if framework == "cra":
                return "npm start" if "start" in scripts else "npx react-scripts start"

            # Generic script priority: dev > start > serve > develop
            for name in ("dev", "start", "serve", "develop"):
                if name in scripts:
                    return f"npm run {name}"
        except (json.JSONDecodeError, OSError):
            pass

    # README / CONTRIBUTING hint
    readme_cmd = _scan_readme_for_command(d)
    if readme_cmd:
        return readme_cmd

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
    # Check IPv4
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
    except Exception:
        pass
    # Check IPv6
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            if s.connect_ex(("::1", port)) == 0:
                return True
    except Exception:
        pass
    return False


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


async def _read_and_drain_logs(
    proc: asyncio.subprocess.Process, url_future: asyncio.Future[str]
) -> None:
    pattern = re.compile(r"https?://(?:localhost|127\.0\.0\.1):\d+", re.IGNORECASE)
    try:
        while True:
            line_bytes = await proc.stdout.readline()  # type: ignore[union-attr]
            if not line_bytes:
                break
            line = line_bytes.decode(errors="replace")
            # Log the output cleanly so developers can diagnose server issues
            console.print(f"  [dim][dev-server][/dim] {line.strip()}")
            match = pattern.search(line)
            if match and not url_future.done():
                url_future.set_result(match.group(0))
    except Exception as e:
        if not url_future.done():
            url_future.set_exception(e)


async def _resolve_url(proc: asyncio.subprocess.Process, port: int, startup_timeout: float) -> str:
    """Race log scanning against port polling; return resolved URL and continuously drain logs."""
    loop = asyncio.get_event_loop()
    url_future: asyncio.Future[str] = loop.create_future()

    # Start the continuous background log reader and drainer task.
    # This prevents the OS pipe buffer from filling up and stalling the server.
    asyncio.create_task(_read_and_drain_logs(proc, url_future))

    # Port poller task
    async def poll_port_task() -> str:
        deadline = loop.time() + startup_timeout
        while loop.time() < deadline:
            if _is_port_in_use(port):
                return f"http://localhost:{port}"
            await asyncio.sleep(0.5)
        raise StartupTimeoutError(
            f"Dev server did not start within {startup_timeout}s on port {port}"
        )

    poll_task = asyncio.create_task(poll_port_task())

    try:
        done, pending = await asyncio.wait(
            {url_future, poll_task},
            timeout=startup_timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

        for t in pending:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

        if url_future.done() and not url_future.cancelled():
            try:
                return url_future.result()
            except Exception:
                pass

        if poll_task.done() and not poll_task.cancelled():
            return poll_task.result()

    except Exception:
        pass

    raise StartupTimeoutError(f"Dev server did not start within {startup_timeout}s on port {port}")


def _parse_env_lines(lines: list[str]) -> dict[str, str]:
    """Parse .env-format lines into a dict, ignoring comments and blank lines."""
    result: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def _parse_env_text(content: str) -> dict[str, str]:
    """Parse a raw .env string (pasted by the user) into a dict."""
    return _parse_env_lines(content.splitlines())


async def start_workspace_server(
    workspace_dir: str,
    extra_env: dict[str, str] | None = None,
    start_command: str | None = None,
    env_content: str | None = None,
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
    file_env = _parse_env_text(env_content) if env_content else {}
    env = {
        **os.environ,
        **file_env,
        "PORT": str(port),
        "EXPO_PORT": str(port),
        "EXPO_PACKAGER_PORT": str(port),
        "RCT_METRO_PORT": str(port),
        "EXPO_WEBPACK_PORT": str(port),
        "BROWSER": "none",
        "EXPO_NO_BROWSER": "1",
        **(extra_env or {}),
    }

    # Install npm dependencies if node_modules is missing (worktrees/copies exclude them).
    ws_path = Path(workspace_dir)
    if (ws_path / "package.json").exists() and not (ws_path / "node_modules").exists():
        install_cmd = "npm ci" if (ws_path / "package-lock.json").exists() else "npm install"
        console.print(
            f"[cyan]workspace-starter[/cyan] node_modules missing"
            f" — running [dim]{install_cmd}[/dim]"
        )
        install_proc = await asyncio.create_subprocess_shell(
            install_cmd,
            cwd=workspace_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            await asyncio.wait_for(install_proc.wait(), timeout=180.0)
        except asyncio.TimeoutError:
            install_proc.kill()
            await _release_port(port)
            raise StartupTimeoutError(f"npm install timed out after 180s in {workspace_dir}")
        if install_proc.returncode != 0:
            await _release_port(port)
            raise RuntimeError(
                f"{install_cmd} failed (exit {install_proc.returncode}) in {workspace_dir}"
            )

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

    # Give the process a moment, then check it didn't exit immediately.
    await asyncio.sleep(1.0)
    if proc.returncode is not None:
        try:
            snippet = await asyncio.wait_for(proc.stdout.read(2048), timeout=1.0)  # type: ignore[union-attr]
            detail = snippet.decode(errors="replace").strip()
        except Exception:
            detail = ""
        await _release_port(port)
        raise RuntimeError(
            f"Dev server process exited immediately (code {proc.returncode})"
            + (f":\n{detail[:300]}" if detail else "")
        )

    try:
        url = await _resolve_url(proc, port, float(STARTUP_TIMEOUT))
    except StartupTimeoutError:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass  # process already exited
        await _release_port(port)
        raise

    console.print(f"  [green]ready[/green] {url}")
    return proc, url, port


async def stop_workspace_server(proc: asyncio.subprocess.Process, port: int) -> None:
    """Terminate the dev server subprocess and release its port."""
    if proc.returncode is None:
        import sys

        if sys.platform == "win32":
            import subprocess

            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            except Exception:
                pass
        else:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            if sys.platform != "win32":
                proc.kill()
            await proc.wait()
    await _release_port(port)
    console.print("[dim]workspace-starter: server stopped[/dim]")
