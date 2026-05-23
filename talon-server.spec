# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Talon server binary.
#
# Build:
#   pip install pyinstaller
#   pyinstaller talon-server.spec
#
# Output:
#   dist/talon-server        (macOS / Linux — one-dir bundle for signing)
#   dist/talon-server.exe    (Windows — one-file exe)
#
# The binary is then bundled by electron-builder as an extraResource.

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_all, copy_metadata

ROOT = Path(SPECPATH)  # repo root
UI_DIST = ROOT / "ui" / "dist"

block_cipher = None

# UPX is unsupported on Apple Silicon (arm64) and can corrupt macOS binaries.
USE_UPX = sys.platform != "darwin"

# collect_all gathers data files + binaries + hidden imports in one call.
# Use it for packages that load files or extensions relative to __file__ at runtime.
_lit_d,  _lit_b,  _lit_h  = collect_all("litellm")
_oai_d,  _oai_b,  _oai_h  = collect_all("openai")
_ant_d,  _ant_b,  _ant_h  = collect_all("anthropic")
_tik_d,  _tik_b,  _tik_h  = collect_all("tiktoken")
_tikx_d, _tikx_b, _tikx_h = collect_all("tiktoken_ext")  # separate pkg with encoding defs (cl100k_base etc.)
_ws_d,   _ws_b,   _ws_h   = collect_all("websockets")    # websockets C extension for uvicorn WebSocket support
CERTIFI_DATAS = collect_data_files("certifi")  # CA bundle for HTTPS calls

# tiktoken >=0.13 registers encodings (cl100k_base etc.) via importlib.metadata
# entry_points — the .dist-info directory must be in the bundle for lookups to work.
TIKTOKEN_METADATA = copy_metadata("tiktoken")

EXTRA_DATAS    = _lit_d  + _oai_d  + _ant_d  + _tik_d  + _tikx_d + _ws_d  + CERTIFI_DATAS + TIKTOKEN_METADATA
EXTRA_BINARIES = _lit_b  + _oai_b  + _ant_b  + _tik_b  + _tikx_b + _ws_b
EXTRA_HIDDEN   = _lit_h  + _oai_h  + _ant_h  + _tik_h  + _tikx_h + _ws_h

# ---------------------------------------------------------------------------
# Hidden imports
# litellm relies heavily on runtime imports; list the most common providers.
# ---------------------------------------------------------------------------
HIDDEN_IMPORTS = [
    # uvicorn internals
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # fastapi / starlette
    "fastapi",
    "starlette.middleware.cors",
    "starlette.staticfiles",
    "starlette.responses",
    "starlette.websockets",
    # anyio (required by FastAPI/starlette >= 0.20, often missed by PyInstaller)
    "anyio",
    "anyio._backends._asyncio",
    "anyio._backends._trio",
    # sniffio (anyio dependency)
    "sniffio",
    # h11 (uvicorn HTTP/1.1 implementation)
    "h11",
    # aiosqlite
    "aiosqlite",
    # pydantic
    "pydantic",
    "pydantic.v1",
    # httpx
    "httpx",
    "httpcore",
    # litellm providers (add as needed)
    "litellm",
    "litellm.main",
    "litellm.utils",
    "litellm.integrations",
    "litellm.integrations.custom_logger",
    "openai",
    "anthropic",
    # platformdirs
    "platformdirs",
    # rich
    "rich",
    "rich.console",
    # python-dotenv
    "dotenv",
    # asyncio
    "asyncio",
    "email.mime.text",
    "email.mime.multipart",
]

a = Analysis(
    [str(ROOT / "talon" / "server_entry.py")],
    pathex=[str(ROOT)],
    binaries=EXTRA_BINARIES,
    datas=(
        [(str(UI_DIST), "ui/dist")] if UI_DIST.exists() else []
    ) + EXTRA_DATAS,
    hiddenimports=HIDDEN_IMPORTS + EXTRA_HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Playwright browser binaries are huge — exclude them. Users who need
    # browser validation should install playwright separately via pip.
    excludes=["playwright"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform == "win32":
    # One-file exe on Windows — easier distribution, no directory to sign.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="talon-server",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=USE_UPX,
        upx_exclude=[],
        runtime_tmpdir=None,
        # console=True keeps sys.stdout/stderr connected to the pipe Electron sets up.
        # console=False causes PyInstaller's bootloader to set sys.stdout=None on
        # Windows, preventing the PORT announcement from ever reaching Electron.
        # The console window is suppressed by windowsHide:true in Electron's spawn().
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    # One-dir bundle on macOS / Linux for notarisation / AppImage signing.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="talon-server",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=USE_UPX,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=USE_UPX,
        upx_exclude=[],
        name="talon-server",
    )
