"""
AETHER-EDIT: FastAPI REST Service & Agent RPC Control Plane
Runs on http://127.0.0.1:8765. Enforces X-Agent-ID, handles atomic batch transactions,
media telemetry queries, preview frame base64 encoding, and hardware rendering.
"""

import asyncio
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import psutil
from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import DEFAULT_VIDEO_ENCODER, NVENC_AVAILABLE
from core.event_bus import event_bus
from core.schema import (
    AgentState,
    BatchRequest,
    MediaAsset,
    RenderRequest,
    TimelineState,
)
from core.state_manager import StateManager
from engine.realtime_compositor import RealtimeCompositor
from engine.renderer import HardwareRenderer
from api.ws_manager import WebSocketManager

logger = logging.getLogger("aether_edit.rest_server")


class RegisterAgentRequest(BaseModel):
    agent_id: str
    role: str = "EDITOR"
    preferred_color: str = "#00F5D4"


class HeartbeatRequest(BaseModel):
    agent_id: str
    playhead_sec: float
    task: str = "EDITING"
    latency_ms: float = 0.0


class MediaSearchRequest(BaseModel):
    query: Optional[str] = None
    min_motion: Optional[float] = None
    min_spike_db: Optional[float] = None
    classification: Optional[str] = None


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    event_bus.register_async_loop(loop)
    event_bus.add_async_listener(app.state.ws_manager.broadcast_event)
    yield


def create_app(
    state_manager: StateManager,
    compositor: RealtimeCompositor,
    renderer: HardwareRenderer,
    ws_manager: WebSocketManager,
) -> FastAPI:
    app = FastAPI(
        title="AETHER-EDIT Control Plane",
        version="1.0.0",
        description="Autonomous Non-Linear Video Editor & Telemetry Observatory API",
        lifespan=lifespan,
    )
    app.state.ws_manager = ws_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------------------------------
    # WebSocket Route
    # -------------------------------------------------------------------------

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await ws_manager.connect(websocket)
        try:
            while True:
                # Keepalive ping/pong
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)
        except Exception:
            await ws_manager.disconnect(websocket)

    # -------------------------------------------------------------------------
    # Agent Registration & Heartbeat
    # -------------------------------------------------------------------------

    @app.post("/api/v1/agents/register", response_model=AgentState)
    def register_agent(req: RegisterAgentRequest) -> AgentState:
        agent = state_manager.register_agent(
            agent_id=req.agent_id,
            role=req.role,
            color_hex=req.preferred_color,
        )
        return agent

    @app.post("/api/v1/agents/heartbeat", response_model=AgentState)
    def agent_heartbeat(req: HeartbeatRequest) -> AgentState:
        agent = state_manager.update_agent_heartbeat(
            agent_id=req.agent_id,
            playhead_sec=req.playhead_sec,
            task=req.task,
            latency_ms=req.latency_ms,
        )
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    # -------------------------------------------------------------------------
    # Media Pool & Telemetry Queries
    # -------------------------------------------------------------------------

    @app.get("/api/v1/media", response_model=List[MediaAsset])
    def get_all_media() -> List[MediaAsset]:
        return state_manager.list_media_assets()

    @app.get("/api/v1/media/{asset_id}/telemetry")
    def get_media_telemetry(asset_id: str) -> Dict[str, Any]:
        asset = state_manager.get_media_asset(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail=f"MediaAsset {asset_id} not found")
        return {
            "asset_id": asset.asset_id,
            "filename": asset.filename,
            "technical_meta": asset.technical_meta.model_dump(),
            "ingest_status": asset.ingest_status.value,
            "audio_telemetry": asset.audio_telemetry.model_dump(),
            "visual_telemetry": asset.visual_telemetry.model_dump(),
        }

    @app.post("/api/v1/media/search")
    def search_media(req: MediaSearchRequest) -> List[Dict[str, Any]]:
        assets = state_manager.list_media_assets()
        results: List[Dict[str, Any]] = []

        query_str = (req.query or "").lower().strip()

        for a in assets:
            matches: Dict[str, Any] = {"asset_id": a.asset_id, "filename": a.filename, "hits": []}

            # Search spoken transcript words
            if query_str:
                for seg in a.audio_telemetry.transcript:
                    for w in seg.words:
                        if query_str in w.word.lower():
                            matches["hits"].append({
                                "type": "TRANSCRIPT",
                                "word": w.word,
                                "timestamp": w.start,
                                "confidence": w.confidence,
                            })

            # Filter by motion score
            if req.min_motion is not None:
                for cut in a.visual_telemetry.scene_cuts:
                    if cut.avg_motion_score >= req.min_motion:
                        matches["hits"].append({
                            "type": "HIGH_MOTION",
                            "start_sec": cut.start_sec,
                            "motion_score": cut.avg_motion_score,
                        })

            # Filter by loudness spikes
            if req.min_spike_db is not None or req.classification:
                for spike in a.audio_telemetry.loudness_spikes:
                    match_db = req.min_spike_db is None or spike.peak_db >= req.min_spike_db
                    match_class = req.classification is None or req.classification.lower() in spike.classification.lower()
                    if match_db and match_class:
                        matches["hits"].append({
                            "type": "LOUDNESS_SPIKE",
                            "timestamp": spike.timestamp,
                            "peak_db": spike.peak_db,
                            "classification": spike.classification,
                        })

            if matches["hits"] or (not query_str and req.min_motion is None and req.min_spike_db is None):
                results.append(matches)

        return results

    # -------------------------------------------------------------------------
    # Timeline & Atomic Batch Mutations
    # -------------------------------------------------------------------------

    @app.get("/api/v1/timeline", response_model=TimelineState)
    def get_timeline() -> TimelineState:
        return state_manager.get_timeline()

    @app.post("/api/v1/timeline/batch", response_model=TimelineState)
    def batch_mutate_timeline(
        req: BatchRequest,
        x_agent_id: Optional[str] = Header(None, alias="X-Agent-ID"),
    ) -> TimelineState:
        agent_id = x_agent_id or "AGENT_ANONYMOUS"
        try:
            new_timeline = state_manager.execute_batch(
                operations=req.operations,
                mode=req.mode,
                agent_id=agent_id,
            )
            return new_timeline
        except Exception as e:
            logger.error(f"Batch execution failed for agent {agent_id}: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    # -------------------------------------------------------------------------
    # Preview & Frame Inspection (Base64 JPEG for AI Vision)
    # -------------------------------------------------------------------------

    @app.get("/api/v1/preview/frame")
    def preview_frame(timeline_sec: float = Query(0.0, ge=0.0)) -> Dict[str, Any]:
        """Composites and returns base64 JPEG frame at specified timestamp."""
        try:
            b64_img = compositor.get_frame_base64_jpeg(timeline_sec)
            return {
                "timeline_sec": timeline_sec,
                "format": "jpeg",
                "base64_data": b64_img,
            }
        except Exception as e:
            logger.error(f"Failed extracting preview frame at {timeline_sec}s: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -------------------------------------------------------------------------
    # Hardware Rendering
    # -------------------------------------------------------------------------

    @app.post("/api/v1/render/start")
    def start_render(req: Optional[RenderRequest] = None) -> Dict[str, Any]:
        if renderer.is_rendering:
            raise HTTPException(status_code=409, detail="A render is currently in progress")

        render_thread = threading.Thread(
            target=renderer.start_render_sync,
            args=(req,),
            daemon=True,
            name="RenderWorker",
        )
        render_thread.start()

        return {
            "status": "STARTED",
            "message": "Hardware render dispatched to background worker",
            "encoder": req.encoder if req and req.encoder else DEFAULT_VIDEO_ENCODER,
        }

    # -------------------------------------------------------------------------
    # System Hardware & Latency Telemetry
    # -------------------------------------------------------------------------

    @app.get("/api/v1/status/system")
    def system_status() -> Dict[str, Any]:
        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        gpu_info = {"available": False, "utilization_pct": 0, "vram_used_mb": 0, "vram_total_mb": 0}
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            vram = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_info = {
                "available": True,
                "name": pynvml.nvmlDeviceGetName(handle),
                "utilization_pct": util.gpu,
                "vram_used_mb": int(vram.used / (1024 * 1024)),
                "vram_total_mb": int(vram.total / (1024 * 1024)),
            }
        except Exception:
            pass

        return {
            "cpu_percent": cpu_pct,
            "ram_used_mb": int(mem.used / (1024 * 1024)),
            "ram_total_mb": int(mem.total / (1024 * 1024)),
            "gpu": gpu_info,
            "nvenc_enabled": NVENC_AVAILABLE,
        }

    return app
