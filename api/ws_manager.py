"""
AETHER-EDIT: Real-Time WebSocket Connection Manager
Streams agent cursor positions, terminal logs, oscilloscope telemetry,
and timeline state diffs at 60Hz to connected UI clients and external agents.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("aether_edit.ws_manager")


class WebSocketManager:
    """Manages active WebSocket connections and fans out event bus broadcasts."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast_event(self, event_type: str, data: Any) -> None:
        """Serialize and broadcast an event to all connected clients."""
        if not self.active_connections:
            return

        # Prepare payload
        payload = {
            "type": event_type,
            "data": data if not hasattr(data, "model_dump") else data.model_dump(),
        }

        try:
            raw_text = json.dumps(payload, default=str)
        except Exception as e:
            logger.error(f"Failed to serialize broadcast payload: {e}")
            return

        dead_connections: Set[WebSocket] = set()
        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_text(raw_text)
                except (WebSocketDisconnect, RuntimeError):
                    dead_connections.add(connection)
                except Exception as e:
                    logger.warning(f"Error broadcasting to client: {e}")
                    dead_connections.add(connection)

            for dead in dead_connections:
                self.active_connections.discard(dead)
