"""
AETHER-EDIT: Hardware-Accelerated Video Render Engine
Async Subprocess FFmpeg NVENC execution with real-time stdout progress parsing,
automatic encoder fallback to libx264, and progress event dispatch.
"""

import asyncio
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from config import (
    DEFAULT_VIDEO_ENCODER,
    EXPORTS_DIR,
    FFMPEG_PATH,
    NVENC_AVAILABLE,
)
from core.event_bus import event_bus
from core.schema import RenderRequest
from core.state_manager import StateManager
from engine.filter_graph import FilterGraphCompiler

logger = logging.getLogger("aether_edit.renderer")


class HardwareRenderer:
    """Manages asynchronous video rendering with NVENC and real-time progress parsing."""

    def __init__(self, state_manager: StateManager, exports_dir: Path = EXPORTS_DIR) -> None:
        self.state_manager = state_manager
        self.exports_dir = Path(exports_dir)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.compiler = FilterGraphCompiler(state_manager, exports_dir)
        self.is_rendering: bool = False
        self._current_process: Optional[subprocess.Popen] = None

    def start_render_sync(self, request: Optional[RenderRequest] = None) -> Path:
        """Execute synchronous render (runs in background thread)."""
        if self.is_rendering:
            raise RuntimeError("Render already in progress")

        self.is_rendering = True
        req = request or RenderRequest()
        output_name = req.output_filename or f"aether_render_{int(time.time())}.mp4"
        if not output_name.endswith(".mp4"):
            output_name += ".mp4"
        output_path = self.exports_dir / output_name

        try:
            event_bus.emit_terminal_log("RENDER", f"Compiling filter graph for {output_name}...", "INFO")
            inputs, filter_script, _, total_duration = self.compiler.compile(
                output_name=output_path.stem,
                burn_subtitles=req.burn_subtitles,
            )

            # Build FFmpeg command
            cmd = [FFMPEG_PATH, "-y"]
            for inp in inputs:
                cmd.extend(["-i", inp])

            # Use -filter_complex_script to avoid Windows CLI length constraints
            clean_script_path = str(filter_script.resolve())
            cmd.extend([
                "-filter_complex_script", clean_script_path,
                "-map", "[outv]",
                "-map", "[outa]",
            ])

            # Select encoder
            encoder = req.encoder or DEFAULT_VIDEO_ENCODER
            if encoder == "h264_nvenc" and NVENC_AVAILABLE:
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-preset", "p5",
                    "-cq", "20",
                    "-b:v", "12M",
                    "-maxrate", "18M",
                    "-bufsize", "24M",
                ])
            else:
                cmd.extend([
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "18",
                ])

            cmd.extend([
                "-c:a", "aac",
                "-b:a", "256k",
                "-ar", "48000",
                "-progress", "pipe:1",
                str(output_path.resolve()),
            ])

            event_bus.emit_terminal_log("RENDER", f"Launching NVENC render: {encoder}", "INFO")

            # Launch subprocess and parse stdout progress
            self._current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            current_time_sec = 0.0
            fps_str = "0"
            speed_str = "1x"

            while True:
                line = self._current_process.stdout.readline()
                if not line and self._current_process.poll() is not None:
                    break

                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    if key == "out_time_ms":
                        # out_time_ms is in microseconds
                        try:
                            current_time_sec = float(val) / 1_000_000.0
                        except ValueError:
                            pass
                    elif key == "fps":
                        fps_str = val
                    elif key == "speed":
                        speed_str = val
                    elif key == "progress" and val == "continue":
                        progress_pct = min(99.0, (current_time_sec / max(0.1, total_duration)) * 100.0)
                        status = f"{progress_pct:.1f}% | {fps_str} FPS | Speed: {speed_str}"
                        event_bus.emit_render_progress(progress_pct, status)

            ret_code = self._current_process.wait()
            if ret_code != 0:
                err_msg = self._current_process.stderr.read()
                logger.error(f"FFmpeg render failed (code {ret_code}): {err_msg}")
                event_bus.emit_terminal_log("RENDER", f"Render failed: {err_msg[:200]}", "ERROR")
                raise RuntimeError(f"FFmpeg render process exited with code {ret_code}")

            event_bus.emit_render_progress(100.0, "Export Complete!")
            event_bus.emit_terminal_log(
                "RENDER", f"Successfully exported master: {output_path.name}", "SUCCESS"
            )
            return output_path

        finally:
            self.is_rendering = False
            self._current_process = None
