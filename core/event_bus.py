"""
AETHER-EDIT: Event Bus Bridge
High-throughput thread-safe bridge connecting Asyncio workers, FastAPI endpoints,
and the PySide6 UI thread via Qt Signals and event queues.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("aether_edit.event_bus")


class EventBus(QObject):
    """
    Thread-safe event dispatcher. Signals emitted here are safely queued
    into the Qt Main Event Loop from any worker thread or asyncio task.
    """
    # UI Notification Signals
    timeline_updated = Signal(object)      # Payload: TimelineState
    media_registered = Signal(object)      # Payload: MediaAsset
    agent_heartbeat = Signal(object)       # Payload: AgentState
    telemetry_metric = Signal(str, float)  # metric_name, value
    terminal_log = Signal(str, str, str)   # agent_id, message, level
    render_progress = Signal(float, str)   # progress_pct (0-100), status
    playback_tick = Signal(float)          # playhead_sec

    def __init__(self) -> None:
        super().__init__()
        self._async_listeners: List[Callable[[str, Any], Any]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def register_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the running asyncio event loop for websocket/rest fan-out."""
        self._loop = loop

    def add_async_listener(self, listener: Callable[[str, Any], Any]) -> None:
        """Add an async listener (e.g. WebSocket broadcaster)."""
        if listener not in self._async_listeners:
            self._async_listeners.append(listener)

    def remove_async_listener(self, listener: Callable[[str, Any], Any]) -> None:
        if listener in self._async_listeners:
            self._async_listeners.remove(listener)

    def emit_timeline_update(self, timeline_state: Any) -> None:
        """Dispatch timeline mutation to UI and WebSocket listeners."""
        self.timeline_updated.emit(timeline_state)
        self._dispatch_async("timeline_update", timeline_state)

    def emit_media_registered(self, media_asset: Any) -> None:
        """Dispatch media pool asset update to UI and WebSocket listeners."""
        self.media_registered.emit(media_asset)
        self._dispatch_async("media_registered", media_asset)

    def emit_agent_heartbeat(self, agent_state: Any) -> None:
        """Dispatch agent playhead or task status update."""
        self.agent_heartbeat.emit(agent_state)
        self._dispatch_async("agent_heartbeat", agent_state)

    def emit_telemetry_metric(self, name: str, value: float) -> None:
        """Stream a real-time oscilloscope metric (ops/sec, rms, latency, motion)."""
        self.telemetry_metric.emit(name, float(value))
        self._dispatch_async("telemetry_metric", {"name": name, "value": float(value)})

    def emit_terminal_log(self, agent_id: str, message: str, level: str = "INFO") -> None:
        """Log an event to the cybernetic terminal HUD."""
        self.terminal_log.emit(agent_id, message, level)
        self._dispatch_async("terminal_log", {
            "agent_id": agent_id,
            "message": message,
            "level": level,
        })

    def emit_render_progress(self, progress: float, status: str) -> None:
        """Update hardware rendering progress bar and status."""
        self.render_progress.emit(float(progress), status)
        self._dispatch_async("render_progress", {"progress": float(progress), "status": status})

    def emit_playback_tick(self, playhead_sec: float) -> None:
        """Broadcast real-time playhead advancement."""
        self.playback_tick.emit(float(playhead_sec))

    def _dispatch_async(self, event_type: str, data: Any) -> None:
        """Schedule notification into the asyncio loop if registered."""
        if not self._loop or not self._async_listeners:
            return

        for listener in self._async_listeners:
            if self._loop.is_running():
                asyncio.run_coroutine_threadsafe(listener(event_type, data), self._loop)


# Global singleton Event Bus
event_bus: EventBus = EventBus()
