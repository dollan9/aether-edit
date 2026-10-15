"""
Unit tests for Deterministic FFmpeg Filter Graph Compiler
"""

import tempfile
from pathlib import Path

from core.schema import (
    BatchActionType,
    BatchOperation,
    ClipEffect,
    EffectType,
    MediaAsset,
    TechnicalMeta,
    TimelineClip,
    TimelineState,
    Track,
    TrackType,
)
from core.state_manager import StateManager
from engine.filter_graph import FilterGraphCompiler


def test_empty_timeline_compiler():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = StateManager(timeline_path=Path(tmpdir) / "tl.json")
        compiler = FilterGraphCompiler(sm, exports_dir=Path(tmpdir))

        inputs, script_path, ass_path, dur = compiler.compile(output_name="test_out")
        assert len(inputs) == 0
        assert script_path.exists()
        assert dur >= 1.0

        content = script_path.read_text(encoding="utf-8")
        assert "color=c=black" in content
        assert "anullsrc" in content
        assert "[outv]" in content
        assert "[outa]" in content


def test_filter_graph_with_media_and_effects():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = StateManager(timeline_path=Path(tmpdir) / "tl.json")
        compiler = FilterGraphCompiler(sm, exports_dir=Path(tmpdir))

        # Register mock media asset
        dummy_video = Path(tmpdir) / "dummy.mp4"
        dummy_video.write_bytes(b"dummy_bytes")

        asset = MediaAsset(
            asset_id="asset_123",
            filename="dummy.mp4",
            relative_path="dummy.mp4",
            absolute_path=str(dummy_video.resolve()),
            file_hash="dummyhash",
            technical_meta=TechnicalMeta(width=1920, height=1080, fps=60.0, duration_sec=10.0),
        )
        sm.register_or_update_media(asset)

        # Place clip with dynamic zoom effect
        op = BatchOperation(
            action=BatchActionType.INSERT_CLIP,
            params={
                "track_id": "trk_video_1",
                "asset_id": "asset_123",
                "name": "Zoom_Clip",
                "timeline_start_sec": 0.0,
                "source_in_sec": 0.0,
                "source_out_sec": 5.0,
            },
        )
        sm.execute_batch([op])

        # Apply zoom effect
        clip_id = sm.get_timeline().get_track("trk_video_1").clips[0].clip_id
        zoom_op = BatchOperation(
            action=BatchActionType.APPLY_EFFECT,
            params={
                "clip_id": clip_id,
                "effect_type": "DYNAMIC_ZOOM",
                "parameters": {"zoom_factor": 1.25},
            },
        )
        sm.execute_batch([zoom_op])

        inputs, script_path, ass_path, dur = compiler.compile(output_name="test_zoom")
        assert len(inputs) == 1
        assert str(dummy_video.resolve()) in inputs[0]

        script = script_path.read_text(encoding="utf-8")
        assert "trim=start=0.000:end=5.000" in script
        assert "crop=" in script  # Dynamic punch-in zoom crop
        assert "loudnorm=I=-14" in script
