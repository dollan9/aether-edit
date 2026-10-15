"""
AETHER-EDIT: Master Application Entrypoint
Spawns the FastAPI REST Server & WebSocket RPC, Watchdog Ingestion Daemon,
MCP Server, and launches the PySide6 Cybernetic Telemetry Observatory GUI.
"""

import argparse
import logging
import os
import sys
import threading
import time

import uvicorn
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from api.rest_server import create_app
from api.ws_manager import WebSocketManager
from config import (
    REST_HOST,
    REST_PORT,
    ensure_directories,
)
from core.llm_director import LLMDirector
from core.state_manager import StateManager
from engine.realtime_compositor import RealtimeCompositor
from engine.renderer import HardwareRenderer
from ingest.watcher import MediaWatcher
from simulation import run_autonomous_simulation
from ui.main_window import MainWindow

# Configure clean logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aether_edit.main")


def start_uvicorn_server(app) -> None:
    """Launch Uvicorn in a background daemon thread."""
    config = uvicorn.Config(
        app,
        host=REST_HOST,
        port=REST_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="AETHER-EDIT Autonomous NLE & Telemetry Observatory")
    parser.add_argument(
        "--simulate-agents",
        action="store_true",
        help="Launch autonomous 3-agent simulation self-test upon startup",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless REST/WebSocket editing server without GUI",
    )
    parser.add_argument(
        "--mcp-stdio",
        action="store_true",
        help="Run Model Context Protocol server over stdio for external AI coding agents",
    )
    args = parser.parse_args()

    # 1. Initialize workspaces and directories
    ensure_directories()

    # 2. Instantiate core singletons
    state_manager = StateManager()
    compositor = RealtimeCompositor(state_manager)
    renderer = HardwareRenderer(state_manager)
    ws_manager = WebSocketManager()
    director = LLMDirector()

    # 3. If --mcp-stdio is specified, run MCP server directly
    if args.mcp_stdio:
        import asyncio
        from api.mcp_server import run_stdio_mcp_server
        logger.info("Starting AETHER-EDIT MCP Server over stdio...")
        asyncio.run(run_stdio_mcp_server(state_manager, compositor, renderer))
        return

    # 4. Start FastAPI REST & WebSocket Control Plane in background daemon thread
    app = create_app(state_manager, compositor, renderer, ws_manager)
    server_thread = threading.Thread(
        target=start_uvicorn_server,
        args=(app,),
        daemon=True,
        name="UvicornServerThread",
    )
    server_thread.start()
    logger.info(f"AETHER-EDIT REST & WebSocket Server active on http://{REST_HOST}:{REST_PORT}")

    # 5. Start Media Pool Watchdog Ingestion Daemon
    watcher = MediaWatcher(state_manager)
    watcher.start()

    # 6. If --simulate-agents is specified, start autonomous simulation in background
    if args.simulate_agents:
        sim_thread = threading.Thread(
            target=run_autonomous_simulation,
            args=(state_manager,),
            daemon=True,
            name="AutonomousSimulationWorker",
        )
        sim_thread.start()

    # 7. Headless mode check
    if args.headless:
        logger.info("Running in headless mode. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            logger.info("Stopping AETHER-EDIT headless daemon.")
        finally:
            watcher.stop()
            compositor.release()
        return

    # 8. Start PySide6 Qt GUI Application
    # Enable high-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("AETHER-EDIT")

    window = MainWindow(
        state_manager=state_manager,
        compositor=compositor,
        renderer=renderer,
        director=director,
    )
    window.show()

    try:
        sys.exit(qt_app.exec())
    finally:
        logger.info("Shutting down AETHER-EDIT workers...")
        watcher.stop()
        compositor.release()


if __name__ == "__main__":
    main()
