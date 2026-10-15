"""
AETHER-EDIT: FFmpeg Proxy & Audio Waveform Peak Generator
Generates 540p all-intra (GOP=1) scrubbable proxy videos, extracted thumbnails,
and normalized 50Hz audio peaks for lightning-fast UI rendering.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import (
    DEFAULT_VIDEO_ENCODER,
    FFMPEG_PATH,
    FFPROBE_PATH,
    NVENC_AVAILABLE,
    PROXIES_DIR,
    PROXY_HEIGHT,
)
from core.schema import TechnicalMeta

logger = logging.getLogger("aether_edit.proxy_generator")


class ProxyGenerator:
    """Handles technical metadata probing, 540p all-intra proxy encoding, and waveform generation."""

    def __init__(self, proxies_dir: Path = PROXIES_DIR) -> None:
        self.proxies_dir = Path(proxies_dir)
        self.proxies_dir.mkdir(parents=True, exist_ok=True)

    def probe_technical_meta(self, file_path: Path) -> TechnicalMeta:
        """Extract exact technical metadata using ffprobe and OpenCV fallback."""
        meta = TechnicalMeta()
        file_path_str = str(file_path.resolve())

        try:
            cmd = [
                FFPROBE_PATH,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path_str,
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video" and meta.total_frames == 0:
                        meta.width = int(stream.get("width", 1920))
                        meta.height = int(stream.get("height", 1080))
                        meta.video_codec = stream.get("codec_name", "h264")

                        # Parse fps
                        r_frame_rate = stream.get("r_frame_rate", "60/1")
                        if "/" in r_frame_rate:
                            num, den = r_frame_rate.split("/")
                            meta.fps = round(float(num) / max(1.0, float(den)), 2)
                        else:
                            meta.fps = float(r_frame_rate)

                        dur = stream.get("duration")
                        if dur:
                            meta.duration_sec = float(dur)
                        nb_frames = stream.get("nb_frames")
                        if nb_frames and nb_frames.isdigit():
                            meta.total_frames = int(nb_frames)

                    elif stream.get("codec_type") == "audio":
                        meta.audio_codec = stream.get("codec_name", "aac")
                        meta.sample_rate = int(stream.get("sample_rate", 48000))
                        meta.channels = int(stream.get("channels", 2))

                # Format level duration fallback
                if meta.duration_sec <= 0.0:
                    meta.duration_sec = float(data.get("format", {}).get("duration", 0.0))
        except Exception as e:
            logger.warning(f"ffprobe failed for {file_path_str}: {e}, falling back to OpenCV")

        # Fallback to OpenCV if duration or total frames missing
        if meta.duration_sec <= 0.0 or meta.total_frames == 0:
            try:
                cap = cv2.VideoCapture(file_path_str)
                if cap.isOpened():
                    meta.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or meta.width)
                    meta.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or meta.height)
                    meta.fps = float(cap.get(cv2.CAP_PROP_FPS) or meta.fps)
                    meta.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    if meta.fps > 0 and meta.total_frames > 0:
                        meta.duration_sec = meta.total_frames / meta.fps
                    cap.release()
            except Exception as cv_e:
                logger.error(f"OpenCV metadata fallback failed: {cv_e}")

        if meta.total_frames == 0 and meta.duration_sec > 0 and meta.fps > 0:
            meta.total_frames = int(meta.duration_sec * meta.fps)

        return meta

    def generate_proxy(self, input_path: Path, asset_id: str) -> Tuple[Path, Path]:
        """
        Encode 540p all-intra (-g 1) proxy and extract a 64x36 thumbnail at midpoint.
        Returns: (proxy_path, thumbnail_path)
        """
        proxy_path = self.proxies_dir / f"{asset_id}_proxy_540p.mp4"
        thumb_path = self.proxies_dir / f"{asset_id}_thumb.jpg"

        # 1. Generate Proxy Video (-g 1 all-intra for instant frame-seeking)
        scale_filter = f"scale=-2:{PROXY_HEIGHT}"
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_path.resolve()),
            "-vf", scale_filter,
            "-g", "1",  # Every frame is an I-frame
        ]

        if NVENC_AVAILABLE:
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", "p4",
                "-cq", "26",
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "24",
            ])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            str(proxy_path.resolve()),
        ])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            if res.returncode != 0:
                logger.warning(f"Hardware proxy encode failed; retrying with libx264: {res.stderr.decode('utf-8', errors='ignore')}")
                # Fallback to software encode
                cmd[cmd.index("-c:v") + 1] = "libx264"
                cmd[cmd.index("-preset") + 1] = "ultrafast"
                cmd[cmd.index("-cq")] = "-crf"
                subprocess.run(cmd, check=True, timeout=180)
        except Exception as e:
            logger.error(f"Proxy generation error: {e}")
            raise e

        # 2. Extract Midpoint Thumbnail (64x36)
        try:
            meta = self.probe_technical_meta(input_path)
            midpoint = max(0.5, meta.duration_sec / 2.0)
            thumb_cmd = [
                FFMPEG_PATH,
                "-y",
                "-ss", f"{midpoint:.2f}",
                "-i", str(input_path.resolve()),
                "-vf", "scale=64:36",
                "-vframes", "1",
                "-q:v", "3",
                str(thumb_path.resolve()),
            ]
            subprocess.run(thumb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        except Exception as e:
            logger.warning(f"Thumbnail generation error: {e}")

        return proxy_path, thumb_path

    def generate_waveform_peaks(
        self, input_path: Path, samples_per_sec: int = 50
    ) -> List[float]:
        """
        Extract downsampled 8kHz mono audio and compute 50Hz normalized waveform peaks (0.0 to 1.0).
        """
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_path.resolve()),
            "-vn",
            "-ac", "1",
            "-ar", "8000",
            "-f", "f32le",
            "pipe:1",
        ]

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if proc.returncode != 0 or not proc.stdout:
                logger.warning("No audio stream found or extraction failed; returning flat waveform")
                return [0.0] * 50

            # Decode raw float32 PCM samples
            audio_samples = np.frombuffer(proc.stdout, dtype=np.float32)
            if len(audio_samples) == 0:
                return [0.0] * 50

            # Calculate chunk size for 50 samples/second (8000 Hz / 50 = 160 samples per chunk)
            chunk_size = max(1, 8000 // samples_per_sec)
            num_chunks = len(audio_samples) // chunk_size

            if num_chunks == 0:
                return [float(np.max(np.abs(audio_samples)))]

            chunks = audio_samples[: num_chunks * chunk_size].reshape((num_chunks, chunk_size))
            peaks = np.max(np.abs(chunks), axis=1)

            # Normalize globally to 0.0 - 1.0
            max_val = float(np.max(peaks))
            if max_val > 0.0001:
                normalized_peaks = (peaks / max_val).tolist()
            else:
                normalized_peaks = peaks.tolist()

            return [round(float(p), 4) for p in normalized_peaks]

        except Exception as e:
            logger.error(f"Waveform peak calculation failed: {e}")
            return [0.0] * 50
