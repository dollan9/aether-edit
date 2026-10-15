"""
AETHER-EDIT: Model Context Protocol (MCP) Server
Exposes structured editing, telemetry querying, frame inspection, and rendering tools
for external coding agents (Cursor, Claude Code, Windsurf, Qoder) over stdio and SSE.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer

from core.schema import BatchActionType, BatchOperation, RenderRequest
from core.state_manager import StateManager
from engine.realtime_compositor import RealtimeCompositor
from engine.renderer import HardwareRenderer

logger = logging.getLogger("aether_edit.mcp_server")


def create_mcp_server(
    state_manager: StateManager,
    compositor: RealtimeCompositor,
    renderer: HardwareRenderer,
) -> MCPServer:
    """Create and configure the AETHER-EDIT Model Context Protocol server."""
    server = MCPServer(
        name="aether-edit-mcp",
        version="1.0.0",
        instructions="AETHER-EDIT Autonomous Video Editor & Telemetry Observatory Tool Suite",
    )

    @server.tool(
        name="list_media_telemetry",
        description="List all media assets in the media pool with technical metadata, transcript summaries, and silence intervals.",
    )
    def list_media_telemetry() -> str:
        assets = state_manager.list_media_assets()
        data = [
            {
                "asset_id": a.asset_id,
                "filename": a.filename,
                "status": a.ingest_status.value,
                "technical_meta": a.technical_meta.model_dump(),
                "silence_intervals_count": len(a.audio_telemetry.silence_intervals),
                "scene_cuts_count": len(a.visual_telemetry.scene_cuts),
                "transcript_segments_count": len(a.audio_telemetry.transcript),
            }
            for a in assets
        ]
        return json.dumps(data, indent=2)

    @server.tool(
        name="inspect_timeline",
        description="Returns the complete JSON timeline state including tracks, clips, keyframes, effects, and active agent cursors.",
    )
    def inspect_timeline() -> str:
        tl = state_manager.get_timeline()
        return tl.model_dump_json(indent=2)

    @server.tool(
        name="batch_edit_timeline",
        description="Executes an atomic batch of timeline operations (INSERT_CLIP, RAZOR_SPLIT, TRIM_CLIP, RIPPLE_DELETE, ADD_KEYFRAME, APPLY_EFFECT). Automatically rolls back on error.",
    )
    def batch_edit_timeline(
        operations: List[Dict[str, Any]],
        mode: str = "insert",
        agent_id: str = "MCP_AGENT",
    ) -> str:
        batch_ops: List[BatchOperation] = []
        for op in operations:
            batch_ops.append(
                BatchOperation(
                    action=BatchActionType(op["action"]),
                    params=op.get("params", {}),
                )
            )

        new_tl = state_manager.execute_batch(batch_ops, mode=mode, agent_id=agent_id)
        return json.dumps({
            "status": "SUCCESS",
            "new_version": new_tl.version,
            "total_duration_sec": new_tl.total_duration_sec(),
        })

    @server.tool(
        name="auto_cut_silences",
        description="Automatically slices dead air / silences out of a dialogue clip or asset based on telemetry with configurable padding.",
    )
    def auto_cut_silences(
        asset_id: str,
        clip_id: Optional[str] = None,
        padding_sec: float = 0.08,
        agent_id: str = "MCP_AGENT",
    ) -> str:
        op = BatchOperation(
            action=BatchActionType.AUTO_SLICE_SILENCE,
            params={
                "asset_id": asset_id,
                "clip_id": clip_id,
                "padding_sec": padding_sec,
            },
        )
        new_tl = state_manager.execute_batch([op], mode="insert", agent_id=agent_id)
        return json.dumps({
            "status": "SUCCESS",
            "message": "Silences sliced",
            "version": new_tl.version,
            "duration": new_tl.total_duration_sec(),
        })

    @server.tool(
        name="inspect_rendered_frame",
        description="Composites the exact timeline at timeline_sec (including active clips, transforms, text, and bounding boxes) and returns base64 JPEG data.",
    )
    def inspect_rendered_frame(timeline_sec: float) -> str:
        b64_data = compositor.get_frame_base64_jpeg(timeline_sec)
        return json.dumps({
            "timeline_sec": timeline_sec,
            "format": "jpeg",
            "base64_data": b64_data,
        })

    @server.tool(
        name="trigger_export",
        description="Triggers the final FFmpeg NVENC hardware render pipeline into ./workspace/exports/.",
    )
    def trigger_export(
        output_filename: str = "mcp_export.mp4",
        encoder: str = "h264_nvenc",
        burn_subtitles: bool = True,
    ) -> str:
        req = RenderRequest(
            output_filename=output_filename,
            encoder=encoder,
            burn_subtitles=burn_subtitles,
        )
        import threading
        t = threading.Thread(target=renderer.start_render_sync, args=(req,), daemon=True)
        t.start()
        return json.dumps({
            "status": "STARTED",
            "output_filename": output_filename,
            "encoder": encoder,
        })

    return server


async def run_stdio_mcp_server(
    state_manager: StateManager,
    compositor: RealtimeCompositor,
    renderer: HardwareRenderer,
) -> None:
    """Launch the MCP server in standard I/O mode."""
    server = create_mcp_server(state_manager, compositor, renderer)
    await server.run_stdio_async()
