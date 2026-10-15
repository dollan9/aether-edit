"""
AETHER-EDIT: Master Cybernetic Telemetry Dashboard (MainWindow)
Integrates Media Pool, Agent Activity & Oscilloscopes, Preview Monitor Viewport,
Multi-Track Timeline, and Top System Telemetry HUD.
"""

import threading
import time
from typing import Optional

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from config import MEDIA_POOL_DIR, NVENC_AVAILABLE, REST_PORT
from core.event_bus import event_bus
from core.llm_director import LLMDirector
from core.state_manager import StateManager
from engine.realtime_compositor import RealtimeCompositor
from engine.renderer import HardwareRenderer
from ui.panels.agent_activity_panel import AgentActivityPanel
from ui.panels.api_config_modal import ApiConfigModal
from ui.panels.media_pool_panel import MediaPoolPanel
from ui.panels.preview_monitor_panel import PreviewMonitorPanel
from ui.panels.timeline_panel import TimelinePanel
from ui.theme import CYBER_PALETTE, FONT_FAMILY_MONO, get_app_stylesheet

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_PYNVML = True
except Exception:
    HAS_PYNVML = False


class MainWindow(QMainWindow):
    """Master Cybernetic Telemetry Observatory Dashboard."""

    def __init__(
        self,
        state_manager: StateManager,
        compositor: RealtimeCompositor,
        renderer: HardwareRenderer,
        director: LLMDirector,
    ) -> None:
        super().__init__()
        self.state_manager = state_manager
        self.compositor = compositor
        self.renderer = renderer
        self.director = director

        self.setWindowTitle("AETHER-EDIT // AUTONOMOUS AI-AGENT NLE & TELEMETRY OBSERVATORY")
        self.resize(1600, 960)
        self.setStyleSheet(get_app_stylesheet())

        self.sim_thread: Optional[threading.Thread] = None
        self._init_ui()

        # Telemetry HUD Polling Timer (every 500ms)
        self.hud_timer = QTimer(self)
        self.hud_timer.timeout.connect(self._poll_system_hud)
        self.hud_timer.start(500)

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(8, 6, 8, 8)
        root_layout.setSpacing(6)

        # ---------------------------------------------------------------------
        # Top Header Bar & Hardware HUD
        # ---------------------------------------------------------------------
        header_bar = QFrame()
        header_bar.setFixedHeight(44)
        header_bar.setStyleSheet(f"""
            background-color: {CYBER_PALETTE['bg_panel']};
            border: 1px solid {CYBER_PALETTE['border_subtle']};
            border-radius: 4px;
            padding: 2px 10px;
        """)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(10, 0, 10, 0)
        header_layout.setSpacing(16)

        # Left: Brand Logo & Title
        title_box = QLabel("⚡ AETHER-EDIT &nbsp;<font color='#94A3B8'>// AUTONOMOUS NLE OBSERVATORY</font>")
        title_box.setStyleSheet(
            f"font-family: {FONT_FAMILY_MONO}; font-weight: 800; font-size: 13px; color: {CYBER_PALETTE['accent_cyan']}; letter-spacing: 1px;"
        )
        header_layout.addWidget(title_box)

        # Demo / Self-Test Simulation Button
        self.btn_simulation = QPushButton("▶ SELF-TEST SIMULATION")
        self.btn_simulation.setFixedHeight(26)
        self.btn_simulation.setProperty("class", "PrimaryAccent")
        self.btn_simulation.clicked.connect(self.trigger_simulation_mode)
        header_layout.addWidget(self.btn_simulation)

        header_layout.addStretch()

        # Right: Floating Status HUD
        self.hud_api = QPushButton("● LLM API: CONNECTED")
        self.hud_api.setFixedHeight(24)
        self.hud_api.setStyleSheet(f"color: {CYBER_PALETTE['accent_green']}; border-color: #10B98144;")
        self.hud_api.clicked.connect(self._open_api_modal)
        header_layout.addWidget(self.hud_api)

        self.hud_agents = QLabel("● AGENTS: ACTIVE (0)")
        self.hud_agents.setStyleSheet(f"font-family: {FONT_FAMILY_MONO}; font-size: 11px; color: {CYBER_PALETTE['accent_cyan']}; font-weight: bold;")
        header_layout.addWidget(self.hud_agents)

        self.hud_gpu = QLabel("● GPU: NVIDIA RTX [0% | 0 MB]")
        self.hud_gpu.setStyleSheet(f"font-family: {FONT_FAMILY_MONO}; font-size: 11px; color: {CYBER_PALETTE['accent_magenta']}; font-weight: bold;")
        header_layout.addWidget(self.hud_gpu)

        self.hud_server = QLabel(f"● REST/MCP: ONLINE (:{REST_PORT})")
        self.hud_server.setStyleSheet(f"font-family: {FONT_FAMILY_MONO}; font-size: 11px; color: {CYBER_PALETTE['accent_green']}; font-weight: bold;")
        header_layout.addWidget(self.hud_server)

        root_layout.addWidget(header_bar)

        # ---------------------------------------------------------------------
        # Main Splitter (Top Panels: 55%, Bottom Timeline: 45%)
        # ---------------------------------------------------------------------
        main_v_splitter = QSplitter(Qt.Vertical)
        main_v_splitter.setStyleSheet("QSplitter::handle { background-color: #1E293B; height: 2px; }")

        # Top Horizontal Splitter: Media Pool (25%) | Agent Activity (35%) | Preview Monitor (40%)
        top_h_splitter = QSplitter(Qt.Horizontal)
        top_h_splitter.setStyleSheet("QSplitter::handle { background-color: #1E293B; width: 2px; }")

        self.panel_media_pool = MediaPoolPanel(self.state_manager)
        self.panel_agent_activity = AgentActivityPanel()
        self.panel_preview_monitor = PreviewMonitorPanel(
            self.compositor, self.renderer, self.state_manager
        )

        top_h_splitter.addWidget(self.panel_media_pool)
        top_h_splitter.addWidget(self.panel_agent_activity)
        top_h_splitter.addWidget(self.panel_preview_monitor)
        top_h_splitter.setSizes([380, 520, 640])

        main_v_splitter.addWidget(top_h_splitter)

        # Bottom Full-Width Multi-Track Timeline (45%)
        self.panel_timeline = TimelinePanel(self.state_manager)
        main_v_splitter.addWidget(self.panel_timeline)

        main_v_splitter.setSizes([520, 400])
        root_layout.addWidget(main_v_splitter, stretch=1)

    def _open_api_modal(self) -> None:
        modal = ApiConfigModal(self.director, self)
        modal.exec()

    def _poll_system_hud(self) -> None:
        """Poll hardware and active agents every 500ms."""
        tl = self.state_manager.get_timeline()
        active_count = len(tl.active_agents)
        self.hud_agents.setText(f"● AGENTS: ACTIVE ({active_count})")

        # GPU metrics
        if HAS_PYNVML:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                used_mb = int(mem.used / (1024 * 1024))
                self.hud_gpu.setText(f"● GPU: RTX [{util.gpu}% | {used_mb} MB]")
            except Exception:
                pass
        else:
            cpu_pct = int(psutil.cpu_percent(interval=None))
            self.hud_gpu.setText(f"● CPU: [{cpu_pct}% | NVENC OK]" if NVENC_AVAILABLE else f"● CPU: [{cpu_pct}%]")

    def trigger_simulation_mode(self) -> None:
        """Launch autonomous multi-agent simulation self-test in background."""
        if self.sim_thread and self.sim_thread.is_alive():
            event_bus.emit_terminal_log("SIM", "Simulation already active.", "WARN")
            return

        self.btn_simulation.setEnabled(False)
        self.btn_simulation.setText("SIMULATING...")

        from simulation import run_autonomous_simulation
        self.sim_thread = threading.Thread(
            target=run_autonomous_simulation,
            args=(self.state_manager,),
            daemon=True,
            name="SimWorker",
        )
        self.sim_thread.start()
