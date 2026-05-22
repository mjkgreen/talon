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
from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH)  # repo root
UI_DIST = ROOT / "ui" / "dist"

block_cipher = None

# UPX is unsupported on Apple Silicon (arm64) and can corrupt macOS binaries.
USE_UPX = sys.platform != "darwin"

# Collect data files required at runtime
LITELLM_DATAS = collect_data_files("litellm")
CERTIFI_DATAS = collect_data_files("certifi")  # CA bundle for HTTPS calls (litellm/openai/anthropic)

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
    binaries=[],
    datas=(
        [(str(UI_DIST), "ui/dist")] if UI_DIST.exists() else []
    ) + LITELLM_DATAS + CERTIFI_DATAS,
    hiddenimports=HIDDEN_IMPORTS,
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
        console=False,     # No console window — output goes to Electron via pipe
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
