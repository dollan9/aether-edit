"""
AETHER-EDIT: Standalone Executable Packaging Script
Bundles backend, PySide6 GUI, MCP Server, and dependencies into a standalone Windows .exe using PyInstaller.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"


def build_executable() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 60)
    print("[AETHER-EDIT] Launching Standalone PyInstaller Build...")
    print("=" * 60)

    # Ensure clean build environment
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            print(f"Cleaning previous build artifact: {d}")
            try:
                shutil.rmtree(d)
            except Exception as e:
                print(f"Warning: could not delete {d}: {e}")

    # Build PyInstaller argument list
    pyinstaller_args = [
        sys.executable,
        "-m", "PyInstaller",
        "--name=aether_edit",
        "--onedir",
        "--noconfirm",
        "--clean",
        # Hidden imports for dynamic FastAPI, MCP, and PySide6 dispatch
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=websockets.legacy",
        "--hidden-import=websockets.legacy.server",
        "--hidden-import=pydantic",
        "--hidden-import=pydantic.deprecated",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=scipy",
        "--hidden-import=psutil",
        "--hidden-import=pynvml",
        "--hidden-import=watchdog",
        "--hidden-import=mcp",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        # Collect submodules
        "--collect-all=fastapi",
        "--collect-all=starlette",
        "--collect-all=mcp",
        str(BASE_DIR / "main.py"),
    ]

    print(f"Executing: {' '.join(pyinstaller_args[:6])} ...")
    res = subprocess.run(pyinstaller_args, cwd=str(BASE_DIR))

    if res.returncode == 0:
        exe_path = DIST_DIR / "aether_edit" / "aether_edit.exe"
        print("=" * 60)
        print(f"[SUCCESS] Standalone executable compiled to:\n{exe_path}")
        print("=" * 60)
    else:
        print("=" * 60)
        print(f"[FAILED] Build failed with exit code {res.returncode}")
        print("=" * 60)
        sys.exit(res.returncode)


if __name__ == "__main__":
    build_executable()
