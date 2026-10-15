"""
AETHER-EDIT: Global Configuration & Hardware Diagnostics
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

# Base Project Directories
BASE_DIR: Path = Path(__file__).resolve().parent
WORKSPACE_DIR: Path = BASE_DIR / "workspace"
MEDIA_POOL_DIR: Path = WORKSPACE_DIR / "media_pool"
PROXIES_DIR: Path = WORKSPACE_DIR / "proxies"
EXPORTS_DIR: Path = WORKSPACE_DIR / "exports"
TELEMETRY_DIR: Path = WORKSPACE_DIR / "telemetry"
TIMELINE_FILE: Path = WORKSPACE_DIR / "timeline.json"
REGISTRY_FILE: Path = WORKSPACE_DIR / "media_registry.json"

# Network & Server Settings
REST_HOST: str = "127.0.0.1"
REST_PORT: int = 8765
MCP_HOST: str = "127.0.0.1"
MCP_PORT: int = 8766
WS_URL: str = f"ws://{REST_HOST}:{REST_PORT}/ws"
API_BASE_URL: str = f"http://{REST_HOST}:{REST_PORT}/api/v1"

# Timeline & Compositing Defaults
DEFAULT_RESOLUTION: Tuple[int, int] = (1920, 1080)
DEFAULT_FPS: float = 60.0
PROXY_HEIGHT: int = 540
AUDIO_NORMALIZATION_LUFS: float = -14.0
SILENCE_THRESHOLD_DB: float = -38.0
SILENCE_MIN_DURATION_SEC: float = 0.35
SILENCE_PADDING_SEC: float = 0.08

# LLM Providers & Keys
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")


def detect_ffmpeg() -> str:
    """Locate the ffmpeg executable on PATH or bundled with application."""
    ffmpeg_exe = shutil.which("ffmpeg")
    if ffmpeg_exe:
        return ffmpeg_exe
    # Fallback to local win64 bundle if available
    local_bin = BASE_DIR / "bin" / "ffmpeg.exe"
    if local_bin.exists():
        return str(local_bin)
    return "ffmpeg"


def detect_ffprobe() -> str:
    """Locate the ffprobe executable on PATH or bundled with application."""
    ffprobe_exe = shutil.which("ffprobe")
    if ffprobe_exe:
        return ffprobe_exe
    local_bin = BASE_DIR / "bin" / "ffprobe.exe"
    if local_bin.exists():
        return str(local_bin)
    return "ffprobe"


FFMPEG_PATH: str = detect_ffmpeg()
FFPROBE_PATH: str = detect_ffprobe()


def check_nvenc_support() -> bool:
    """Query FFmpeg encoders to verify whether h264_nvenc is available and functional."""
    try:
        res = subprocess.run(
            [FFMPEG_PATH, "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if "h264_nvenc" in res.stdout:
            # Run a micro test encode to ensure driver compatibility
            test_cmd = [
                FFMPEG_PATH,
                "-y",
                "-f", "lavfi",
                "-i", "testsrc=size=64x64:rate=1:duration=0.1",
                "-c:v", "h264_nvenc",
                "-f", "null",
                "-"
            ]
            test_res = subprocess.run(
                test_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            return test_res.returncode == 0
    except Exception:
        pass
    return False


NVENC_AVAILABLE: bool = check_nvenc_support()
DEFAULT_VIDEO_ENCODER: str = "h264_nvenc" if NVENC_AVAILABLE else "libx264"
DEFAULT_HEVC_ENCODER: str = "hevc_nvenc" if NVENC_AVAILABLE else "libx265"


def ensure_directories() -> None:
    """Ensure all required workspace and telemetry directories exist on disk."""
    for d in (
        WORKSPACE_DIR,
        MEDIA_POOL_DIR,
        PROXIES_DIR,
        EXPORTS_DIR,
        TELEMETRY_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


# Initialize folders upon module load
ensure_directories()
