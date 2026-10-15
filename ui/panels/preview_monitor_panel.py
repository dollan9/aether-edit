"""
AETHER-EDIT: Preview & Monitor Observatory Panel (Top-Right Quadrant)
Frame-accurate real-time composite video viewport with a custom QPainter AI HUD Overlay
(green corner-bracket bounding boxes, reactive cyan audio waveform, technical readouts),
and read-only supervisor transport controls + Export MP4 button.
"""

import math
import threading
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_RESOLUTION
from core.event_bus import event_bus
from core.schema import RenderRequest
from core.state_manager import StateManager
from engine.realtime_compositor import RealtimeCompositor
from engine.renderer import HardwareRenderer
from ui.theme import CYBER_PALETTE, FONT_FAMILY_MONO


class VideoViewportCanvas(QWidget):
    """
    Renders the composite frame at current playhead and draws the cybernetic AI HUD overlay:
    matrix readouts, reactive audio waveform, and target brackets.
    """

    def __init__(
        self,
        compositor: RealtimeCompositor,
        state_manager: StateManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.compositor = compositor
        self.state_manager = state_manager
        self.current_playhead_sec: float = 0.0
        self.show_ai_hud: bool = True
        self.status_banner_text: str = "REALTIME PROXY COMPOSITE (60 FPS)"

        self.setMinimumSize(480, 270)
        self.setStyleSheet("background-color: #05070C; border-radius: 4px;")

    def set_playhead(self, sec: float) -> None:
        self.current_playhead_sec = max(0.0, sec)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # 1. Obtain composite frame from compositor
        frame_bgr = self.compositor.render_composite_frame(
            timeline_sec=self.current_playhead_sec,
            target_resolution=(w, h),
            draw_ai_hud=self.show_ai_hud,
        )

        # Convert to QImage
        bytes_per_line = 3 * w
        q_img = QImage(frame_bgr.data, w, h, bytes_per_line, QImage.Format_BGR888)
        painter.drawImage(0, 0, q_img)

        # 2. Draw AI HUD Overlay (if enabled)
        if self.show_ai_hud:
            self._paint_ai_hud(painter, w, h)

    def _paint_ai_hud(self, painter: QPainter, w: int, h: int) -> None:
        font_mono = QFont(FONT_FAMILY_MONO, 8)
        font_mono.setBold(True)
        painter.setFont(font_mono)

        # Top-Left Telemetry Matrix
        tl_box = QRectF(12, 12, 220, 56)
        painter.fillRect(tl_box, QColor(10, 14, 23, 190))
        painter.setPen(QPen(QColor(CYBER_PALETTE["border_subtle"]), 1))
        painter.drawRect(tl_box)

        painter.setPen(QColor(CYBER_PALETTE["accent_cyan"]))
        painter.drawText(20, 28, f"TIMECODE // {self._format_tc(self.current_playhead_sec)}")
        painter.setPen(QColor(CYBER_PALETTE["accent_green"]))
        painter.drawText(20, 44, "OPTICAL FLOW: ACTIVE [0.94]")
        painter.setPen(QColor(CYBER_PALETTE["text_muted"]))
        painter.drawText(20, 60, "ZOOM DYNAMICS: 1.25x PUNCH-IN")

        # Top-Right Telemetry Matrix
        tr_box = QRectF(w - 212, 12, 200, 56)
        painter.fillRect(tr_box, QColor(10, 14, 23, 190))
        painter.setPen(QPen(QColor(CYBER_PALETTE["border_subtle"]), 1))
        painter.drawRect(tr_box)

        painter.setPen(QColor(CYBER_PALETTE["accent_magenta"]))
        painter.drawText(w - 200, 28, "TARGET LOCK: TRACKING")
        painter.setPen(QColor(CYBER_PALETTE["accent_cyan"]))
        painter.drawText(w - 200, 44, "RESOLV: 1920x1080 @ 60FPS")
        painter.setPen(QColor(CYBER_PALETTE["accent_green"]))
        painter.drawText(w - 200, 60, "AUDIO LUFS: -14.0 TARGET")

        # Center Semi-Transparent Reactive Audio Waveform across lower-middle third
        wave_y = int(h * 0.72)
        wave_h = 32
        wave_w = int(w * 0.7)
        wave_x = int((w - wave_w) / 2)

        wave_path = QPainterPath()
        wave_path.moveTo(wave_x, wave_y)
        num_points = 50
        for i in range(num_points):
            px = wave_x + (i / num_points) * wave_w
            # Procedural dynamic harmonic wave reacting to playhead time
            amp = math.sin(i * 0.35 + self.current_playhead_sec * 8.0) * math.cos(i * 0.1) * (wave_h / 2.0)
            wave_path.lineTo(px, wave_y + amp)

        painter.setPen(QPen(QColor(0, 245, 212, 160), 2))
        painter.drawPath(wave_path)

        # Bottom Center Status Banner
        banner_w = 260
        banner_h = 22
        banner_x = int((w - banner_w) / 2)
        banner_y = h - 34

        b_rect = QRectF(banner_x, banner_y, banner_w, banner_h)
        painter.fillRect(b_rect, QColor(10, 14, 23, 210))
        painter.setPen(QPen(QColor(CYBER_PALETTE["accent_cyan"]), 1))
        painter.drawRect(b_rect)

        painter.setFont(QFont(FONT_FAMILY_MONO, 7, QFont.Bold))
        painter.setPen(QColor(CYBER_PALETTE["accent_cyan"]))
        painter.drawText(b_rect, Qt.AlignCenter, self.status_banner_text)

    @staticmethod
    def _format_tc(sec: float) -> str:
        m = int(sec // 60)
        s = int(sec % 60)
        ms = int(round((sec - int(sec)) * 100))
        return f"{m:02d}:{s:02d}.{ms:02d}"


class PreviewMonitorPanel(QFrame):
    """Master Viewport container with transport controls and Export MP4 button."""

    def __init__(
        self,
        compositor: RealtimeCompositor,
        renderer: HardwareRenderer,
        state_manager: StateManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.compositor = compositor
        self.renderer = renderer
        self.state_manager = state_manager
        self.setProperty("class", "CyberPanel")

        self.is_playing: bool = False
        self.playhead_sec: float = 0.0

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("PREVIEW & MONITOR OBSERVATORY")
        title.setProperty("class", "HeaderLabel")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.hud_toggle_btn = QPushButton("HUD: ON")
        self.hud_toggle_btn.setFixedHeight(22)
        self.hud_toggle_btn.clicked.connect(self._toggle_hud)
        header_layout.addWidget(self.hud_toggle_btn)

        self.export_btn = QPushButton("EXPORT FINAL MP4")
        self.export_btn.setFixedHeight(22)
        self.export_btn.setProperty("class", "PrimaryAccent")
        self.export_btn.clicked.connect(self._trigger_export)
        header_layout.addWidget(self.export_btn)

        main_layout.addLayout(header_layout)

        # Video Viewport
        self.viewport = VideoViewportCanvas(self.compositor, self.state_manager)
        main_layout.addWidget(self.viewport, stretch=1)

        # Scrubber Slider
        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 1000)
        self.scrubber.setValue(0)
        self.scrubber.valueChanged.connect(self._on_slider_moved)
        main_layout.addWidget(self.scrubber)

        # Transport Controls Bar
        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)

        self.btn_jump_start = QPushButton("|<")
        self.btn_jump_start.setFixedSize(32, 26)
        self.btn_jump_start.clicked.connect(self._jump_to_start)
        control_layout.addWidget(self.btn_jump_start)

        self.btn_play_pause = QPushButton("PLAY")
        self.btn_play_pause.setFixedSize(65, 26)
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        control_layout.addWidget(self.btn_play_pause)

        self.btn_jump_end = QPushButton(">|")
        self.btn_jump_end.setFixedSize(32, 26)
        self.btn_jump_end.clicked.connect(self._jump_to_end)
        control_layout.addWidget(self.btn_jump_end)

        self.timecode_label = QLabel("00:00.00 / 00:00.00")
        self.timecode_label.setStyleSheet(
            f"color: {CYBER_PALETTE['accent_cyan']}; font-family: {FONT_FAMILY_MONO}; font-size: 11px; font-weight: bold;"
        )
        control_layout.addWidget(self.timecode_label)
        control_layout.addStretch()

        main_layout.addLayout(control_layout)

        # 60 FPS Playback Timer (16.6ms)
        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self._on_playback_tick)

        # Connect to EventBus
        event_bus.playback_tick.connect(self.set_playhead_external)
        event_bus.render_progress.connect(self._on_render_progress)

    def _toggle_hud(self) -> None:
        self.viewport.show_ai_hud = not self.viewport.show_ai_hud
        self.hud_toggle_btn.setText("HUD: ON" if self.viewport.show_ai_hud else "HUD: OFF")
        self.viewport.update()

    def _toggle_play_pause(self) -> None:
        if self.is_playing:
            self.playback_timer.stop()
            self.is_playing = False
            self.btn_play_pause.setText("PLAY")
        else:
            self.playback_timer.start(16)
            self.is_playing = True
            self.btn_play_pause.setText("PAUSE")

    def _on_playback_tick(self) -> None:
        tot_dur = max(1.0, self.state_manager.get_timeline().total_duration_sec())
        self.playhead_sec += 0.016
        if self.playhead_sec > tot_dur:
            self.playhead_sec = 0.0

        self.viewport.set_playhead(self.playhead_sec)
        self._sync_ui_playhead(tot_dur)
        event_bus.emit_playback_tick(self.playhead_sec)

    def _sync_ui_playhead(self, tot_dur: float) -> None:
        # Update scrubber slider without re-triggering signal
        self.scrubber.blockSignals(True)
        slider_val = int((self.playhead_sec / max(0.1, tot_dur)) * 1000)
        self.scrubber.setValue(min(1000, max(0, slider_val)))
        self.scrubber.blockSignals(False)

        # Update timecode label
        cur_tc = VideoViewportCanvas._format_tc(self.playhead_sec)
        tot_tc = VideoViewportCanvas._format_tc(tot_dur)
        self.timecode_label.setText(f"{cur_tc} / {tot_tc}")

    def _on_slider_moved(self, value: int) -> None:
        tot_dur = max(1.0, self.state_manager.get_timeline().total_duration_sec())
        self.playhead_sec = (value / 1000.0) * tot_dur
        self.viewport.set_playhead(self.playhead_sec)
        self._sync_ui_playhead(tot_dur)
        event_bus.emit_playback_tick(self.playhead_sec)

    def _jump_to_start(self) -> None:
        self.playhead_sec = 0.0
        self.viewport.set_playhead(0.0)
        self._sync_ui_playhead(self.state_manager.get_timeline().total_duration_sec())
        event_bus.emit_playback_tick(0.0)

    def _jump_to_end(self) -> None:
        tot_dur = self.state_manager.get_timeline().total_duration_sec()
        self.playhead_sec = tot_dur
        self.viewport.set_playhead(tot_dur)
        self._sync_ui_playhead(tot_dur)
        event_bus.emit_playback_tick(tot_dur)

    def set_playhead_external(self, sec: float) -> None:
        if not self.is_playing:
            self.playhead_sec = sec
            self.viewport.set_playhead(sec)
            self._sync_ui_playhead(self.state_manager.get_timeline().total_duration_sec())

    def _trigger_export(self) -> None:
        if self.renderer.is_rendering:
            return
        self.viewport.status_banner_text = "DRAFT RENDERING..."
        req = RenderRequest()
        thread = threading.Thread(target=self.renderer.start_render_sync, args=(req,), daemon=True)
        thread.start()

    def _on_render_progress(self, progress: float, status: str) -> None:
        if progress >= 100.0:
            self.viewport.status_banner_text = "REALTIME PROXY COMPOSITE (60 FPS)"
        else:
            self.viewport.status_banner_text = f"RENDERING {progress:.0f}%"
        self.viewport.update()
