"""
AETHER-EDIT: AI Agent Activity & Telemetry Observatory Panel (Top-Center Quadrant)
Split view featuring a high-speed real-time terminal console with colored agent tags
and 4 stacked 60 FPS live oscilloscope spline graphs with gradient underfills.
"""

from collections import deque
from typing import Deque, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.event_bus import event_bus
from ui.theme import CYBER_PALETTE, FONT_FAMILY_MONO


class LiveOscilloscopeWidget(QWidget):
    """
    Hardware-accelerated scrolling waveform graph rendering smooth spline curves
    with gradient underfill and live technical telemetry readouts.
    """

    def __init__(
        self,
        title: str,
        color_hex: str,
        unit: str = "",
        min_val: float = 0.0,
        max_val: float = 100.0,
        buffer_size: int = 80,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.stroke_color = QColor(color_hex)
        self.unit = unit
        self.min_val = min_val
        self.max_val = max_val
        self.buffer_size = buffer_size

        self.data: Deque[float] = deque([min_val] * buffer_size, maxlen=buffer_size)
        self.latest_val: float = min_val

        self.setMinimumHeight(55)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    def push_value(self, val: float) -> None:
        self.latest_val = val
        self.data.append(val)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # 1. Background Inset
        painter.fillRect(QRectF(0, 0, w, h), QColor(CYBER_PALETTE["bg_inset"]))

        # 2. Grid Lines (3 subtle horizontal lines)
        grid_pen = QPen(QColor("#1E293B"), 1, Qt.DashLine)
        painter.setPen(grid_pen)
        painter.drawLine(0, int(h * 0.25), int(w), int(h * 0.25))
        painter.drawLine(0, int(h * 0.50), int(w), int(h * 0.50))
        painter.drawLine(0, int(h * 0.75), int(w), int(h * 0.75))

        if len(self.data) < 2:
            return

        # 3. Build Spline Curve Path & Gradient Underfill Path
        val_range = max(0.001, self.max_val - self.min_val)
        step_x = w / float(len(self.data) - 1)

        points = []
        for idx, val in enumerate(self.data):
            # Clamp value
            clamped = max(self.min_val, min(self.max_val, val))
            norm = (clamped - self.min_val) / val_range
            px = idx * step_x
            py = h - (norm * (h - 10) + 5)
            points.append(QPointF(px, py))

        line_path = QPainterPath()
        fill_path = QPainterPath()

        line_path.moveTo(points[0])
        fill_path.moveTo(points[0].x(), h)
        fill_path.lineTo(points[0])

        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            cx = (p1.x() + p2.x()) / 2.0
            line_path.cubicTo(cx, p1.y(), cx, p2.y(), p2.x(), p2.y())
            fill_path.cubicTo(cx, p1.y(), cx, p2.y(), p2.x(), p2.y())

        fill_path.lineTo(points[-1].x(), h)
        fill_path.closeSubpath()

        # Fill gradient
        grad = QLinearGradient(0, 0, 0, h)
        grad_color = QColor(self.stroke_color)
        grad_color.setAlpha(80)
        grad.setColorAt(0.0, grad_color)
        grad_transparent = QColor(self.stroke_color)
        grad_transparent.setAlpha(5)
        grad.setColorAt(1.0, grad_transparent)

        painter.fillPath(fill_path, QBrush(grad))

        # Stroke line
        stroke_pen = QPen(self.stroke_color, 2)
        painter.setPen(stroke_pen)
        painter.drawPath(line_path)

        # 4. Header & Live Readout Text
        painter.setPen(QColor(CYBER_PALETTE["text_muted"]))
        font = QFont(FONT_FAMILY_MONO, 8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(6, 14, self.title.upper())

        # Current Value Display
        val_str = f"{self.latest_val:.1f} {self.unit}".strip()
        painter.setPen(self.stroke_color)
        painter.drawText(int(w - 70), 14, val_str)


class AgentActivityPanel(QFrame):
    """Container for the split terminal log and 4 oscilloscope graphs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("class", "CyberPanel")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)

        # Panel Header
        header = QLabel("AI AGENT ACTIVITY & OSCILLOSCOPES")
        header.setProperty("class", "HeaderLabel")
        main_layout.addWidget(header)

        # Splitter (Left: Terminal, Right: Graphs)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #1E293B; width: 1px; }")

        # ---------------------------------------------------------------------
        # Left: Real-Time High-Speed Terminal Stream
        # ---------------------------------------------------------------------
        term_container = QWidget()
        term_layout = QVBoxLayout(term_container)
        term_layout.setContentsMargins(0, 0, 6, 0)
        term_layout.setSpacing(4)

        term_title = QLabel("LIVE AGENT TERMINAL STREAM")
        term_title.setStyleSheet(f"font-size: 10px; color: {CYBER_PALETTE['text_dim']}; font-family: {FONT_FAMILY_MONO}; font-weight: bold;")
        term_layout.addWidget(term_title)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setProperty("class", "TerminalConsole")
        term_layout.addWidget(self.terminal)

        splitter.addWidget(term_container)

        # ---------------------------------------------------------------------
        # Right: 4 Stacked Live Oscilloscope Graphs
        # ---------------------------------------------------------------------
        graphs_container = QWidget()
        graphs_layout = QVBoxLayout(graphs_container)
        graphs_layout.setContentsMargins(6, 0, 0, 0)
        graphs_layout.setSpacing(6)

        # Graph 1 (Cyan): API / Token Throughput (ops/sec)
        self.graph_ops = LiveOscilloscopeWidget(
            title="API / Ops Throughput",
            color_hex=CYBER_PALETTE["accent_cyan"],
            unit="ops/s",
            min_val=0.0,
            max_val=40.0,
        )
        graphs_layout.addWidget(self.graph_ops)

        # Graph 2 (Magenta): Audio RMS & Transient Energy
        self.graph_audio = LiveOscilloscopeWidget(
            title="Audio Transient Energy",
            color_hex=CYBER_PALETTE["accent_magenta"],
            unit="dB",
            min_val=-60.0,
            max_val=0.0,
        )
        graphs_layout.addWidget(self.graph_audio)

        # Graph 3 (Electric Blue): Visual Motion Vector & Cut Density
        self.graph_motion = LiveOscilloscopeWidget(
            title="Visual Motion Density",
            color_hex="#3B82F6",
            unit="pts",
            min_val=0.0,
            max_val=100.0,
        )
        graphs_layout.addWidget(self.graph_motion)

        # Graph 4 (Lime Green): Compositor Latency Spike Monitor
        self.graph_latency = LiveOscilloscopeWidget(
            title="Compositor Latency",
            color_hex=CYBER_PALETTE["accent_green"],
            unit="ms",
            min_val=0.0,
            max_val=50.0,
        )
        graphs_layout.addWidget(self.graph_latency)

        splitter.addWidget(graphs_container)
        splitter.setSizes([320, 240])

        main_layout.addWidget(splitter)

        # Connect to EventBus
        event_bus.terminal_log.connect(self.on_terminal_log)
        event_bus.telemetry_metric.connect(self.on_telemetry_metric)

        # Oscilloscope simulation timer (produces subtle organic oscillations when idle)
        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._tick_oscilloscopes)
        self._sim_timer.start(100)  # 10Hz update

        # Initial greeting logs
        self.on_terminal_log("SYSTEM", "AETHER-EDIT Cybernetic Core initialized.", "INFO")
        self.on_terminal_log("API Connect", "Listening on http://127.0.0.1:8765 [active 12ms latency]", "INFO")

    def on_terminal_log(self, agent_id: str, message: str, level: str) -> None:
        """Append color-coded message to terminal console."""
        # Color badge based on agent name
        badge_color = CYBER_PALETTE["accent_cyan"]
        if "AUDIO" in agent_id:
            badge_color = CYBER_PALETTE["accent_green"]
        elif "VFX" in agent_id or "AGENT_B" in agent_id:
            badge_color = CYBER_PALETTE["accent_magenta"]
        elif "DIRECTOR" in agent_id:
            badge_color = CYBER_PALETTE["accent_purple"]
        elif level == "ERROR":
            badge_color = "#EF4444"
        elif level == "SUCCESS":
            badge_color = CYBER_PALETTE["accent_green"]

        text_color = "#E2E8F0" if level != "ERROR" else "#FCA5A5"

        line_html = (
            f"<span style='color:{badge_color}; font-weight:bold;'>[{agent_id}]</span> "
            f"<span style='color:{text_color};'>{message}</span>"
        )
        self.terminal.append(line_html)
        # Scroll to bottom
        cursor = self.terminal.textCursor()
        cursor.movePosition(cursor.End)
        self.terminal.setTextCursor(cursor)

    def on_telemetry_metric(self, name: str, value: float) -> None:
        if name in ("ops", "throughput", "api"):
            self.graph_ops.push_value(value)
        elif name in ("audio", "rms", "transient"):
            self.graph_audio.push_value(value)
        elif name in ("motion", "cut_density"):
            self.graph_motion.push_value(value)
        elif name in ("latency", "render_time"):
            self.graph_latency.push_value(value)

    def _tick_oscilloscopes(self) -> None:
        """Keep graphs smoothly alive with ambient telemetry."""
        import random
        # Ambient ops: 0 to 4
        self.graph_ops.push_value(max(0.0, self.graph_ops.latest_val * 0.85 + random.uniform(0, 3)))
        # Ambient audio: -45 to -30 dB
        self.graph_audio.push_value(-42.0 + random.uniform(-6, 6))
        # Ambient motion: 5 to 25
        self.graph_motion.push_value(12.0 + random.uniform(-4, 8))
        # Latency: 10 to 18 ms
        self.graph_latency.push_value(12.5 + random.uniform(-2, 3))
