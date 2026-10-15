"""
AETHER-EDIT: Multi-Track Telemetry Timeline Observatory Panel (Bottom Panel)
Custom QPainter canvas with dynamically scaling timecode ruler, audio waveform bars,
ducking spline envelopes, effect pills, and 60 FPS lerp-animated multi-agent laser playheads.
"""

import math
from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.event_bus import event_bus
from core.schema import AgentState, EffectType, TimelineClip, TimelineState, Track, TrackType
from core.state_manager import StateManager
from ui.theme import CYBER_PALETTE, FONT_FAMILY_MONO


class TimelineCanvas(QWidget):
    """
    High-performance QPainter timeline viewport.
    Renders tracks, clips, waveforms, and smoothly lerps agent laser playheads at 60 FPS.
    """

    def __init__(self, state_manager: StateManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state_manager = state_manager

        # Viewport zoom & scroll metrics
        self.px_per_sec: float = 75.0  # Zoom level
        self.scroll_x: float = 0.0     # Horizontal scroll offset in pixels
        self.header_width: int = 150   # Left track header width
        self.ruler_height: int = 28    # Top ruler height
        self.track_height: int = 48    # Height of each track row

        # Supervisor Playhead
        self.playhead_sec: float = 0.0

        # Multi-Agent Live Playhead Cursors
        # agent_id -> {"target_sec": float, "current_sec": float, "color": QColor, "task": str}
        self.agent_cursors: Dict[str, Dict] = {}

        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

        # 60 FPS Lerp Animation Timer (16.6ms)
        self.lerp_timer = QTimer(self)
        self.lerp_timer.timeout.connect(self._animate_agent_cursors)
        self.lerp_timer.start(16)

        # Listen to state updates
        event_bus.timeline_updated.connect(self.on_timeline_updated)
        event_bus.agent_heartbeat.connect(self.on_agent_heartbeat)
        event_bus.playback_tick.connect(self.on_playback_tick)

    def on_timeline_updated(self, timeline: TimelineState) -> None:
        # Sync agents from timeline
        for agent_id, agent in timeline.active_agents.items():
            self.on_agent_heartbeat(agent)
        self.update()

    def on_agent_heartbeat(self, agent: AgentState) -> None:
        if agent.agent_id not in self.agent_cursors:
            self.agent_cursors[agent.agent_id] = {
                "target_sec": agent.playhead_sec,
                "current_sec": agent.playhead_sec,
                "color": QColor(agent.color_hex),
                "task": agent.current_task,
                "role": agent.role,
            }
        else:
            cur = self.agent_cursors[agent.agent_id]
            cur["target_sec"] = agent.playhead_sec
            cur["color"] = QColor(agent.color_hex)
            cur["task"] = agent.current_task

    def on_playback_tick(self, sec: float) -> None:
        self.playhead_sec = sec
        self.update()

    def _animate_agent_cursors(self) -> None:
        """Smoothly lerp agent cursors toward their target timestamps at 60 FPS."""
        needs_repaint = False
        for cur in self.agent_cursors.values():
            diff = cur["target_sec"] - cur["current_sec"]
            if abs(diff) > 0.005:
                # 60 FPS exponential lerp
                cur["current_sec"] += diff * 0.18
                needs_repaint = True
            else:
                cur["current_sec"] = cur["target_sec"]

        if needs_repaint:
            self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Mouse wheel zooms horizontally when Ctrl is pressed, or scrolls horizontally."""
        modifiers = event.modifiers()
        num_degrees = event.angleDelta().y()

        if modifiers & Qt.ControlModifier:
            # Zoom in / out
            factor = 1.15 if num_degrees > 0 else 0.85
            self.px_per_sec = max(20.0, min(400.0, self.px_per_sec * factor))
        else:
            # Horizontal scroll
            self.scroll_x = max(0.0, self.scroll_x - (num_degrees * 0.75))

        self.update()

    def mousePressEvent(self, event) -> None:
        """Click to scrub supervisor playhead (no clip dragging allowed)."""
        x = event.position().x()
        if x >= self.header_width:
            timeline_x = x - self.header_width + self.scroll_x
            sec = max(0.0, timeline_x / self.px_per_sec)
            self.playhead_sec = sec
            event_bus.emit_playback_tick(sec)
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        timeline = self.state_manager.get_timeline()

        # 1. Background Fill
        painter.fillRect(QRectF(0, 0, w, h), QColor(CYBER_PALETTE["bg_main"]))

        # 2. Draw Tracks & Clips
        y_cursor = self.ruler_height
        for idx, track in enumerate(timeline.tracks):
            track_rect = QRectF(self.header_width, y_cursor, w - self.header_width, self.track_height)
            # Alternating subtle track row background
            bg_color = QColor("#0D131F") if idx % 2 == 0 else QColor("#101726")
            painter.fillRect(track_rect, bg_color)
            painter.setPen(QPen(QColor(CYBER_PALETTE["border_subtle"]), 1))
            painter.drawLine(0, int(y_cursor + self.track_height), int(w), int(y_cursor + self.track_height))

            # Draw Clips on Track
            for clip in track.clips:
                self._draw_clip(painter, clip, track.track_type, y_cursor)

            y_cursor += self.track_height

        # 3. Draw Left Track Headers (Static frozen column)
        self._draw_track_headers(painter, timeline.tracks)

        # 4. Draw Timecode Ruler (Top)
        self._draw_timecode_ruler(painter, w)

        # 5. Draw Multi-Agent Live Laser Playheads (CRITICAL VISUAL FEATURE)
        self._draw_agent_lasers(painter, h)

        # 6. Draw Supervisor Playhead (White vertical laser line)
        sup_x = self.header_width + (self.playhead_sec * self.px_per_sec) - self.scroll_x
        if sup_x >= self.header_width:
            painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
            painter.drawLine(int(sup_x), 0, int(sup_x), int(h))
            # Supervisor diamond badge
            diamond = QPolygonF([
                QPointF(sup_x, 0),
                QPointF(sup_x - 5, 8),
                QPointF(sup_x, 16),
                QPointF(sup_x + 5, 8),
            ])
            painter.setBrush(QBrush(QColor(CYBER_PALETTE["accent_cyan"])))
            painter.drawPolygon(diamond)

    def _draw_timecode_ruler(self, painter: QPainter, w: float) -> None:
        ruler_rect = QRectF(0, 0, w, self.ruler_height)
        painter.fillRect(ruler_rect, QColor("#111726"))
        painter.setPen(QPen(QColor(CYBER_PALETTE["border_subtle"]), 1))
        painter.drawLine(0, self.ruler_height, int(w), self.ruler_height)

        # Draw left header corner box
        painter.fillRect(QRectF(0, 0, self.header_width, self.ruler_height), QColor("#0A0E17"))
        painter.setFont(QFont(FONT_FAMILY_MONO, 8, QFont.Bold))
        painter.setPen(QColor(CYBER_PALETTE["accent_cyan"]))
        painter.drawText(12, 18, "TIMELINE // TRACKS")

        # Dynamic Tick Intervals based on zoom level
        if self.px_per_sec > 150:
            step_sec = 1.0
        elif self.px_per_sec > 60:
            step_sec = 5.0
        else:
            step_sec = 10.0

        painter.setFont(QFont(FONT_FAMILY_MONO, 7))
        start_t = math.floor(self.scroll_x / (step_sec * self.px_per_sec)) * step_sec
        max_t = start_t + (w / self.px_per_sec) + step_sec

        t = start_t
        while t <= max_t:
            x = self.header_width + (t * self.px_per_sec) - self.scroll_x
            if x >= self.header_width:
                # Major tick
                painter.setPen(QPen(QColor("#475569"), 1))
                painter.drawLine(int(x), self.ruler_height - 10, int(x), self.ruler_height)
                # Label
                tc = f"{int(t//60):02d}:{int(t%60):02d}"
                painter.setPen(QColor(CYBER_PALETTE["text_muted"]))
                painter.drawText(int(x + 4), self.ruler_height - 4, tc)
            t += step_sec

    def _draw_track_headers(self, painter: QPainter, tracks: List[Track]) -> None:
        y = self.ruler_height
        for idx, trk in enumerate(tracks):
            header_rect = QRectF(0, y, self.header_width, self.track_height)
            painter.fillRect(header_rect, QColor("#0E1422"))
            painter.setPen(QPen(QColor(CYBER_PALETTE["border_subtle"]), 1))
            painter.drawRect(header_rect)

            # Track type indicator pill
            pill_color = QColor(CYBER_PALETTE["accent_cyan"])
            icon = "▸"
            if trk.track_type == TrackType.AUDIO:
                pill_color = QColor(CYBER_PALETTE["accent_green"])
                icon = "♫"
            elif trk.track_type == TrackType.EFFECT:
                pill_color = QColor(CYBER_PALETTE["accent_purple"])
                icon = "❖"
            elif trk.track_type == TrackType.SUBTITLE:
                pill_color = QColor(CYBER_PALETTE["accent_magenta"])
                icon = "💬"

            painter.setFont(QFont(FONT_FAMILY_MONO, 9, QFont.Bold))
            painter.setPen(pill_color)
            painter.drawText(10, int(y + 28), f"{icon} {trk.track_name}")

            y += self.track_height

    def _draw_clip(
        self, painter: QPainter, clip: TimelineClip, track_type: TrackType, track_y: int
    ) -> None:
        x1 = self.header_width + (clip.timeline_start_sec * self.px_per_sec) - self.scroll_x
        clip_w = max(4.0, (clip.timeline_end_sec - clip.timeline_start_sec) * self.px_per_sec)
        clip_h = self.track_height - 6
        y1 = track_y + 3

        if x1 + clip_w < self.header_width or x1 > self.width():
            return  # Offscreen culling

        clip_rect = QRectF(x1, y1, clip_w, clip_h)

        # Select color gradient based on track type or agent
        base_color = QColor(clip.color_hex)
        grad = QLinearGradient(x1, y1, x1, y1 + clip_h)
        c1 = QColor(base_color)
        c1.setAlpha(180)
        c2 = QColor(base_color)
        c2.setAlpha(100)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)

        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(base_color, 1))
        painter.drawRoundedRect(clip_rect, 3, 3)

        # Clip Title
        painter.setFont(QFont(FONT_FAMILY_MONO, 8, QFont.Bold))
        painter.setPen(QColor("#FFFFFF"))
        title_text = f"{clip.name} [{clip.created_by_agent}]"
        painter.drawText(QRectF(x1 + 6, y1 + 3, clip_w - 12, 16), Qt.AlignLeft, title_text)

        # If Audio Track: Draw vertical waveform peaks and volume ducking curve
        if track_type == TrackType.AUDIO and clip.asset_id:
            asset = self.state_manager.get_media_asset(clip.asset_id)
            if asset and asset.audio_telemetry.waveform_peaks:
                peaks = asset.audio_telemetry.waveform_peaks
                num_peaks = len(peaks)
                if num_peaks > 0:
                    wave_pen = QPen(QColor(0, 245, 212, 130), 1)
                    painter.setPen(wave_pen)
                    mid_y = y1 + (clip_h / 2.0)
                    step = max(1, int(clip_w / min(num_peaks, int(clip_w))))

                    for px_offset in range(0, int(clip_w), 2):
                        ratio = px_offset / clip_w
                        peak_idx = int(ratio * num_peaks)
                        if peak_idx < num_peaks:
                            amp = peaks[peak_idx] * (clip_h / 2.0 - 4)
                            vx = x1 + px_offset
                            painter.drawLine(int(vx), int(mid_y - amp), int(vx), int(mid_y + amp))

            # Continuous green ducking spline envelope curve
            if clip.audio_envelope.volume_keyframes:
                curve_path = QPainterPath()
                first = True
                for kf in clip.audio_envelope.volume_keyframes:
                    kx = x1 + (kf.time_offset_sec * self.px_per_sec)
                    # -14dB maps to 70% height down
                    norm_gain = max(0.0, min(1.0, (kf.value + 30.0) / 36.0))
                    ky = y1 + clip_h - (norm_gain * (clip_h - 10) + 5)
                    if first:
                        curve_path.moveTo(kx, ky)
                        first = False
                    else:
                        curve_path.lineTo(kx, ky)
                painter.setPen(QPen(QColor(CYBER_PALETTE["accent_green"]), 2))
                painter.drawPath(curve_path)

        # If Effects / Subtitles Track: Render color-coded effect pills
        if track_type in (TrackType.EFFECT, TrackType.SUBTITLE):
            pill_rect = QRectF(x1 + 4, y1 + clip_h - 14, min(clip_w - 8, 80), 10)
            painter.fillRect(pill_rect, QColor(CYBER_PALETTE["accent_magenta"]))

    def _draw_agent_lasers(self, painter: QPainter, total_h: float) -> None:
        """Draw 2px wide vertical laser lines and glowing rectangular flag badges for active agents."""
        for agent_id, data in self.agent_cursors.items():
            cur_sec = data["current_sec"]
            laser_x = self.header_width + (cur_sec * self.px_per_sec) - self.scroll_x
            if laser_x < self.header_width or laser_x > self.width():
                continue

            color = data["color"]

            # 1. Glowing Laser Line spanning from top of ruler through all tracks
            glow_pen = QPen(color, 2)
            painter.setPen(glow_pen)
            painter.drawLine(int(laser_x), 0, int(laser_x), int(total_h))

            # 2. Downward-pointing Triangle Pointer
            triangle = QPolygonF([
                QPointF(laser_x - 6, self.ruler_height),
                QPointF(laser_x + 6, self.ruler_height),
                QPointF(laser_x, self.ruler_height + 8),
            ])
            painter.setBrush(QBrush(color))
            painter.drawPolygon(triangle)

            # 3. Glowing Rectangular Flag Badge at Top of Ruler
            badge_text = f"[{agent_id}]"
            font = QFont(FONT_FAMILY_MONO, 8, QFont.Bold)
            painter.setFont(font)
            text_w = painter.fontMetrics().horizontalAdvance(badge_text) + 12
            badge_rect = QRectF(laser_x - (text_w / 2.0), 3, text_w, 18)

            # Glow border & filled badge
            painter.fillRect(badge_rect, QColor(10, 14, 23, 230))
            painter.setPen(QPen(color, 1.5))
            painter.drawRoundedRect(badge_rect, 3, 3)

            painter.setPen(color)
            painter.drawText(badge_rect, Qt.AlignCenter, badge_text)


class TimelinePanel(QFrame):
    """Bottom Full-Width Multi-Track Timeline Panel."""

    def __init__(self, state_manager: StateManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state_manager = state_manager
        self.setProperty("class", "CyberPanel")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Header bar
        header_layout = QHBoxLayout()
        header = QLabel("MULTI-TRACK AGENT TIMELINE (READ-ONLY OBSERVATORY)")
        header.setProperty("class", "HeaderLabel")
        header_layout.addWidget(header)
        header_layout.addStretch()

        legend = QLabel(
            f"<font color='{CYBER_PALETTE['accent_cyan']}'>● AGENT_01</font> &nbsp;&nbsp;"
            f"<font color='{CYBER_PALETTE['accent_green']}'>● AUDIO_AGENT</font> &nbsp;&nbsp;"
            f"<font color='{CYBER_PALETTE['accent_magenta']}'>● VFX_AGENT</font>"
        )
        legend.setStyleSheet(f"font-family: {FONT_FAMILY_MONO}; font-size: 11px;")
        header_layout.addWidget(legend)

        main_layout.addLayout(header_layout)

        # Canvas
        self.canvas = TimelineCanvas(self.state_manager)
        main_layout.addWidget(self.canvas, stretch=1)
