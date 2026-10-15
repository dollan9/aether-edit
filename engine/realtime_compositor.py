"""
AETHER-EDIT: Real-Time Proxy Timeline Compositor
Frame-accurate OpenCV compositing engine for proxy playback and AI agent vision inspection.
Produces base64 JPEG frames for GET /api/v1/preview/frame and 60 FPS viewport rendering.
"""

import base64
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from config import DEFAULT_RESOLUTION
from core.schema import EffectType, TimelineClip, TimelineState, TrackType
from core.state_manager import StateManager

logger = logging.getLogger("aether_edit.realtime_compositor")


class RealtimeCompositor:
    """Frame-accurate proxy compositing engine with caching and vision inspection support."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager
        self._cap_cache: Dict[str, cv2.VideoCapture] = {}
        self._lock = threading.Lock()

    def get_capture(self, file_path: str) -> Optional[cv2.VideoCapture]:
        with self._lock:
            if file_path not in self._cap_cache:
                cap = cv2.VideoCapture(file_path)
                if cap.isOpened():
                    self._cap_cache[file_path] = cap
                else:
                    return None
            return self._cap_cache[file_path]

    def release(self) -> None:
        with self._lock:
            for cap in self._cap_cache.values():
                cap.release()
            self._cap_cache.clear()

    def render_composite_frame(
        self,
        timeline_sec: float,
        target_resolution: Tuple[int, int] = (960, 540),
        draw_ai_hud: bool = True,
    ) -> np.ndarray:
        """
        Renders a composite BGR frame for the specified timeline timestamp.
        Layers video tracks bottom-to-top, overlays subtitles, and draws AI bounding boxes.
        """
        timeline = self.state_manager.get_timeline()
        width, height = target_resolution

        # Create base black canvas
        canvas = np.zeros((height, width, 3), dtype=np.uint8)

        # 1. Composite Video Tracks
        for track in timeline.tracks:
            if track.track_type != TrackType.VIDEO or track.muted:
                continue

            for clip in track.clips:
                if clip.timeline_start_sec <= timeline_sec < clip.timeline_end_sec:
                    clip_frame = self._render_clip_frame(clip, timeline_sec, width, height)
                    if clip_frame is not None:
                        # Overlay onto canvas (non-black pixels or direct copy)
                        canvas = clip_frame

        # 2. Render Active Subtitle Captions
        sub_track = next(
            (t for t in timeline.tracks if t.track_type == TrackType.SUBTITLE and not t.muted), None
        )
        if sub_track:
            for clip in sub_track.clips:
                if clip.timeline_start_sec <= timeline_sec < clip.timeline_end_sec:
                    text = clip.name.replace("Sub_", "")
                    for eff in clip.effects:
                        if eff.effect_type == EffectType.SUBTITLE_CAPTION:
                            text = eff.parameters.get("text", text)

                    self._draw_pop_in_subtitle(canvas, text, width, height)

        # 3. Draw AI HUD Overlay (Bounding boxes from active asset telemetry)
        if draw_ai_hud:
            self._draw_ai_bounding_boxes(canvas, timeline, timeline_sec, width, height)

        return canvas

    def _render_clip_frame(
        self, clip: TimelineClip, timeline_sec: float, width: int, height: int
    ) -> Optional[np.ndarray]:
        if not clip.asset_id:
            return None

        asset = self.state_manager.get_media_asset(clip.asset_id)
        if not asset:
            return None

        # Prefer 540p proxy for instant seeking
        media_path = asset.proxy_path or asset.absolute_path
        if not Path(media_path).exists():
            return None

        cap = self.get_capture(media_path)
        if not cap:
            return None

        # Calculate source frame offset
        rel_time = timeline_sec - clip.timeline_start_sec
        source_sec = clip.source_in_sec + (rel_time * clip.playback_speed)
        fps = asset.technical_meta.fps or 60.0
        frame_number = int(source_sec * fps)

        with self._lock:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            if not ret or frame is None:
                return None

        # Resize to canvas resolution
        frame_resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)

        # Check for dynamic punch-in zoom
        has_zoom = any(
            e.effect_type == EffectType.DYNAMIC_ZOOM for e in clip.effects
        ) or any(k.value > 1.0 for k in clip.transform.scale_x)

        if has_zoom:
            zoom_factor = 1.25
            for e in clip.effects:
                if e.effect_type == EffectType.DYNAMIC_ZOOM:
                    zoom_factor = float(e.parameters.get("zoom_factor", 1.25))
            for k in clip.transform.scale_x:
                if k.value > 1.0:
                    zoom_factor = max(zoom_factor, k.value)

            crop_w = int(width / zoom_factor)
            crop_h = int(height / zoom_factor)
            x1 = (width - crop_w) // 2
            y1 = (height - crop_h) // 2
            cropped = frame_resized[y1 : y1 + crop_h, x1 : x1 + crop_w]
            frame_resized = cv2.resize(cropped, (width, height), interpolation=cv2.INTER_LINEAR)

        return frame_resized

    def _draw_pop_in_subtitle(
        self, canvas: np.ndarray, text: str, width: int, height: int
    ) -> None:
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = 1.2
        thickness = 2
        # Text dimensions
        (t_w, t_h), _ = cv2.getTextSize(text, font, font_scale, thickness)
        x = (width - t_w) // 2
        y = height - 60

        # Drop shadow (black outline)
        cv2.putText(canvas, text, (x + 2, y + 2), font, font_scale, (0, 0, 0), thickness + 3, cv2.LINE_AA)
        # Glowing Cyber Cyan font (#00F5D4 -> BGR: 212, 245, 0)
        cv2.putText(canvas, text, (x, y), font, font_scale, (212, 245, 0), thickness, cv2.LINE_AA)

    def _draw_ai_bounding_boxes(
        self, canvas: np.ndarray, timeline: TimelineState, timeline_sec: float, width: int, height: int
    ) -> None:
        # Find active video clip
        for track in timeline.tracks:
            if track.track_type != TrackType.VIDEO:
                continue
            for clip in track.clips:
                if clip.timeline_start_sec <= timeline_sec < clip.timeline_end_sec and clip.asset_id:
                    asset = self.state_manager.get_media_asset(clip.asset_id)
                    if not asset:
                        continue
                    fps = asset.technical_meta.fps or 60.0
                    rel_sec = clip.source_in_sec + (timeline_sec - clip.timeline_start_sec) * clip.playback_speed
                    frame_idx = int(rel_sec * fps)

                    # Look for bounding boxes within +/- 5 frames
                    nearest_key = None
                    min_dist = 6
                    for k in asset.visual_telemetry.bounding_boxes.keys():
                        dist = abs(k - frame_idx)
                        if dist < min_dist:
                            min_dist = dist
                            nearest_key = k

                    if nearest_key is not None:
                        boxes = asset.visual_telemetry.bounding_boxes[nearest_key]
                        for b in boxes:
                            x1 = int(b.bbox_norm[0] * width)
                            y1 = int(b.bbox_norm[1] * height)
                            x2 = int(b.bbox_norm[2] * width)
                            y2 = int(b.bbox_norm[3] * height)

                            # Neon Green Bounding Box (#10B981 -> BGR: 129, 185, 16)
                            color = (129, 185, 16)
                            # Draw corner brackets
                            bracket_len = max(8, int((x2 - x1) * 0.2))
                            # Top-left
                            cv2.line(canvas, (x1, y1), (x1 + bracket_len, y1), color, 2)
                            cv2.line(canvas, (x1, y1), (x1, y1 + bracket_len), color, 2)
                            # Top-right
                            cv2.line(canvas, (x2, y1), (x2 - bracket_len, y1), color, 2)
                            cv2.line(canvas, (x2, y1), (x2, y1 + bracket_len), color, 2)
                            # Bottom-left
                            cv2.line(canvas, (x1, y2), (x1 + bracket_len, y2), color, 2)
                            cv2.line(canvas, (x1, y2), (x1, y2 - bracket_len), color, 2)
                            # Bottom-right
                            cv2.line(canvas, (x2, y2), (x2 - bracket_len, y2), color, 2)
                            cv2.line(canvas, (x2, y2), (x2, y2 - bracket_len), color, 2)

                            # Label badge
                            label_text = f"[{b.label.upper()} {int(b.confidence*100)}%]"
                            cv2.putText(
                                canvas, label_text, (x1, max(15, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA
                            )

    def get_frame_base64_jpeg(self, timeline_sec: float, quality: int = 85) -> str:
        """Composite frame at timestamp and encode to base64 JPEG string."""
        frame = self.render_composite_frame(timeline_sec=timeline_sec, draw_ai_hud=True)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        ret, buf = cv2.imencode(".jpg", frame, encode_param)
        if not ret:
            raise RuntimeError("JPEG frame encoding failed")
        return base64.b64encode(buf).decode("utf-8")
