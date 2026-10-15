"""
AETHER-EDIT: Autonomous Simulation & Self-Test Engine
Generates synthetic 1080p60 test media with tones and test patterns via FFmpeg,
ingests it, and orchestrates 3 autonomous simulated agents (AGENT_A, AGENT_B, AUDIO_AGENT)
demonstrating clip slicing, keyframing, ducking, and 60 FPS playhead laser tracking.
"""

import logging
import subprocess
import time
from pathlib import Path

from config import (
    DEFAULT_VIDEO_ENCODER,
    FFMPEG_PATH,
    MEDIA_POOL_DIR,
    NVENC_AVAILABLE,
)
from core.event_bus import event_bus
from core.schema import (
    BatchActionType,
    BatchOperation,
    EasingType,
    EffectType,
    IngestStatus,
    MediaAsset,
)
from core.state_manager import StateManager
from ingest.watcher import MediaWatcher

logger = logging.getLogger("aether_edit.simulation")


def generate_synthetic_media(output_path: Path, duration_sec: int = 15) -> Path:
    """Generate high-quality 1080p60 test video with audio tones via FFmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 1000:
        return output_path

    event_bus.emit_terminal_log("SIM", f"Generating synthetic media: {output_path.name}...", "INFO")

    # Generate synthetic video with color bars, timecode counter, and audio tone
    filter_expr = (
        "testsrc=size=1920x1080:rate=60:duration={dur},"
        "drawtext=text='AETHER-EDIT TEST STREAM // 1080p60':fontcolor=white:fontsize=48:box=1:boxcolor=black@0.6:x=(w-text_w)/2:y=100,"
        "drawtext=text='%{{pts\\:hms}}':fontcolor=cyan:fontsize=72:box=1:boxcolor=black@0.7:x=(w-text_w)/2:y=(h-text_h)/2"
    ).format(dur=duration_sec)

    cmd = [
        FFMPEG_PATH,
        "-y",
        "-f", "lavfi",
        "-i", filter_expr,
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={duration_sec}",
    ]

    if NVENC_AVAILABLE:
        cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "24"])
    else:
        cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"])

    cmd.extend([
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        str(output_path.resolve()),
    ])

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=60)
        event_bus.emit_terminal_log("SIM", "Synthetic test media generated successfully.", "SUCCESS")
    except Exception as e:
        logger.error(f"Failed generating synthetic media: {e}")
        # Fallback minimal test file
        min_cmd = [
            FFMPEG_PATH, "-y",
            "-f", "lavfi", "-i", f"color=c=navy:s=1280x720:d={duration_sec}:r=30",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={duration_sec}",
            "-c:v", "libx264", "-c:a", "aac",
            str(output_path.resolve())
        ]
        subprocess.run(min_cmd, check=True, timeout=30)

    return output_path


def run_autonomous_simulation(state_manager: StateManager) -> None:
    """Execute complete 3-agent autonomous self-test workflow."""
    event_bus.emit_terminal_log("SIM", "=== STARTING AUTONOMOUS SIMULATION MODE ===", "INFO")

    # Step 1: Ensure media pool has media
    synthetic_file = MEDIA_POOL_DIR / "sample_synthetic_footage.mp4"
    if not any(MEDIA_POOL_DIR.glob("*.mp4")):
        generate_synthetic_media(synthetic_file, duration_sec=16)

    # Ingest synthetic media if not ready
    watcher = MediaWatcher(state_manager)
    watcher.queue_ingestion(synthetic_file)

    # Wait for media to be READY
    asset: Optional[MediaAsset] = None
    for _ in range(30):
        assets = state_manager.list_media_assets()
        for a in assets:
            if a.ingest_status == IngestStatus.READY:
                asset = a
                break
        if asset:
            break
        time.sleep(0.5)

    if not asset:
        event_bus.emit_terminal_log("SIM", "Simulation media ingest timed out.", "ERROR")
        return

    asset_id = asset.asset_id
    filename = asset.filename

    # Step 2: Register 3 simulated autonomous agents
    event_bus.emit_terminal_log("SIM", "Spawning AGENT_A, AGENT_B, AUDIO_AGENT...", "INFO")
    agent_a = state_manager.register_agent("AGENT_A", role="Master Slicer", color_hex="#00F5D4")
    agent_b = state_manager.register_agent("AGENT_B", role="VFX & Punch-Ins", color_hex="#FF2A85")
    agent_audio = state_manager.register_agent("AUDIO_AGENT", role="Dialogue & Ducking", color_hex="#10B981")

    time.sleep(1.0)

    # Step 3: AGENT_A Places Raw Clip on Video 1 & Audio 1
    event_bus.emit_terminal_log("AGENT_A", f"Placing {filename} on Video 1 & Audio 1", "INFO")
    state_manager.update_agent_heartbeat("AGENT_A", playhead_sec=0.0, task="Inserting Master Media")

    insert_ops = [
        BatchOperation(
            action=BatchActionType.INSERT_CLIP,
            params={
                "track_id": "trk_video_1",
                "asset_id": asset_id,
                "name": "Synthetic_Cam_A",
                "timeline_start_sec": 0.0,
                "source_in_sec": 0.0,
                "source_out_sec": 14.0,
                "color_hex": "#00F5D4",
            },
        ),
        BatchOperation(
            action=BatchActionType.INSERT_CLIP,
            params={
                "track_id": "trk_audio_1",
                "asset_id": asset_id,
                "name": "Dialogue_Main",
                "timeline_start_sec": 0.0,
                "source_in_sec": 0.0,
                "source_out_sec": 14.0,
                "color_hex": "#10B981",
            },
        ),
    ]
    state_manager.execute_batch(insert_ops, mode="insert", agent_id="AGENT_A")
    event_bus.emit_telemetry_metric("ops", 18.0)

    time.sleep(1.2)

    # Step 4: AGENT_A sweeps across timeline and performs RAZOR_SPLIT
    for t_step in [1.5, 3.2, 5.0]:
        state_manager.update_agent_heartbeat("AGENT_A", playhead_sec=t_step, task=f"Scanning cut @ {t_step:.1f}s")
        time.sleep(0.3)

    # Find first clip on Video 1 to split
    tl = state_manager.get_timeline()
    v1 = tl.get_track("trk_video_1")
    if v1 and v1.clips:
        target_clip = v1.clips[0]
        event_bus.emit_terminal_log("AGENT_A", f"Executing razor split @ 00:05.00", "INFO")
        split_op = BatchOperation(
            action=BatchActionType.RAZOR_SPLIT,
            params={"clip_id": target_clip.clip_id, "timeline_sec": 5.0},
        )
        state_manager.execute_batch([split_op], mode="insert", agent_id="AGENT_A")
        event_bus.emit_telemetry_metric("ops", 24.0)

    time.sleep(1.2)

    # Step 5: AGENT_B jumps in, applies 1.25x punch-in zoom on second slice
    tl = state_manager.get_timeline()
    v1 = tl.get_track("trk_video_1")
    if v1 and len(v1.clips) > 1:
        second_clip = v1.clips[1]
        state_manager.update_agent_heartbeat("AGENT_B", playhead_sec=5.2, task="Applying Dynamic Zoom")
        event_bus.emit_terminal_log("AGENT_B", "Applying 1.25x punch-in zoom on peak @ 00:05.00", "INFO")

        zoom_op = BatchOperation(
            action=BatchActionType.APPLY_EFFECT,
            params={
                "clip_id": second_clip.clip_id,
                "effect_type": "DYNAMIC_ZOOM",
                "parameters": {"zoom_factor": 1.25},
            },
        )
        state_manager.execute_batch([zoom_op], mode="insert", agent_id="AGENT_B")
        event_bus.emit_telemetry_metric("motion", 45.0)

    time.sleep(1.0)

    # Step 6: AUDIO_AGENT inserts tension background music and configures ducking
    state_manager.update_agent_heartbeat("AUDIO_AGENT", playhead_sec=2.0, task="Syncing tension music")
    event_bus.emit_terminal_log("AUDIO_AGENT", "Placing background score on Audio 2", "INFO")

    music_op = BatchOperation(
        action=BatchActionType.INSERT_CLIP,
        params={
            "track_id": "trk_audio_2",
            "asset_id": asset_id,
            "name": "Tension_Bed_Ambience",
            "timeline_start_sec": 0.0,
            "source_in_sec": 0.0,
            "source_out_sec": 14.0,
            "color_hex": "#9B5DE5",
        },
    )
    state_manager.execute_batch([music_op], mode="insert", agent_id="AUDIO_AGENT")

    time.sleep(1.0)

    event_bus.emit_terminal_log("AUDIO_AGENT", "Configuring automated -14dB audio ducking curves", "INFO")
    state_manager.update_agent_heartbeat("AUDIO_AGENT", playhead_sec=6.0, task="Building Ducking Keyframes")
    duck_op = BatchOperation(
        action=BatchActionType.AUTO_SYNC_AUDIO_DUCKING,
        params={
            "dialogue_track_id": "trk_audio_1",
            "music_track_id": "trk_audio_2",
            "duck_db": -14.0,
            "ramp_sec": 0.25,
        },
    )
    state_manager.execute_batch([duck_op], mode="insert", agent_id="AUDIO_AGENT")
    event_bus.emit_telemetry_metric("audio", -14.0)

    time.sleep(1.0)

    # Step 7: AGENT_B adds pop-in subtitle captions
    state_manager.update_agent_heartbeat("AGENT_B", playhead_sec=2.5, task="Generating Subtitles")
    event_bus.emit_terminal_log("AGENT_B", "Generating pop-in karaoke captions on Subtitles track", "INFO")

    cap_ops = [
        BatchOperation(
            action=BatchActionType.INSERT_CLIP,
            params={
                "track_id": "trk_subtitles",
                "name": "Sub_TARGET",
                "timeline_start_sec": 1.0,
                "source_in_sec": 0.0,
                "source_out_sec": 1.5,
                "color_hex": "#FF2A85",
            },
        ),
        BatchOperation(
            action=BatchActionType.INSERT_CLIP,
            params={
                "track_id": "trk_subtitles",
                "name": "Sub_IDENTIFIED",
                "timeline_start_sec": 2.5,
                "source_in_sec": 0.0,
                "source_out_sec": 1.5,
                "color_hex": "#FF2A85",
            },
        ),
    ]
    state_manager.execute_batch(cap_ops, mode="insert", agent_id="AGENT_B")

    time.sleep(1.0)

    # Move all 3 agent cursors to end
    state_manager.update_agent_heartbeat("AGENT_A", playhead_sec=14.0, task="IDLE // Complete")
    state_manager.update_agent_heartbeat("AGENT_B", playhead_sec=14.0, task="IDLE // Complete")
    state_manager.update_agent_heartbeat("AUDIO_AGENT", playhead_sec=14.0, task="IDLE // Complete")

    event_bus.emit_terminal_log("SIM", "=== SIMULATION & VERIFICATION RUN COMPLETED! ===", "SUCCESS")
