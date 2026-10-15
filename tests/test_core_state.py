"""
Unit tests for Core State Engine, Pydantic v2 Schemas, and Atomic Operations
"""

import tempfile
from pathlib import Path
import pytest

from core.schema import (
    BatchActionType,
    BatchOperation,
    IngestStatus,
    MediaAsset,
    TimelineClip,
    TimelineState,
    TrackType,
)
from core.state_manager import StateManager


@pytest.fixture
def temp_state_manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        tl_path = Path(tmpdir) / "timeline.json"
        reg_path = Path(tmpdir) / "registry.json"
        sm = StateManager(timeline_path=tl_path, registry_path=reg_path)
        yield sm


def test_default_timeline_initialization(temp_state_manager):
    tl = temp_state_manager.get_timeline()
    assert tl.project_name == "Aether_Master_Cut"
    assert tl.version == 1
    assert len(tl.tracks) == 6
    track_ids = [t.track_id for t in tl.tracks]
    assert "trk_video_1" in track_ids
    assert "trk_audio_1" in track_ids
    assert "trk_subtitles" in track_ids


def test_insert_clip_and_version_increment(temp_state_manager):
    op = BatchOperation(
        action=BatchActionType.INSERT_CLIP,
        params={
            "track_id": "trk_video_1",
            "name": "Test_Clip_1",
            "timeline_start_sec": 0.0,
            "source_in_sec": 0.0,
            "source_out_sec": 5.0,
            "color_hex": "#00F5D4",
        },
    )
    tl = temp_state_manager.execute_batch([op], mode="insert", agent_id="TEST_AGENT")
    assert tl.version == 2
    track = tl.get_track("trk_video_1")
    assert len(track.clips) == 1
    clip = track.clips[0]
    assert clip.name == "Test_Clip_1"
    assert clip.timeline_start_sec == 0.0
    assert clip.timeline_end_sec == 5.0


def test_razor_split(temp_state_manager):
    # Insert initial 10s clip
    op_insert = BatchOperation(
        action=BatchActionType.INSERT_CLIP,
        params={
            "clip_id": "clip_to_split",
            "track_id": "trk_video_1",
            "name": "Original_Clip",
            "timeline_start_sec": 0.0,
            "source_in_sec": 0.0,
            "source_out_sec": 10.0,
        },
    )
    temp_state_manager.execute_batch([op_insert], mode="insert", agent_id="TEST_AGENT")

    # Split at 4.0 seconds
    op_split = BatchOperation(
        action=BatchActionType.RAZOR_SPLIT,
        params={"clip_id": "clip_to_split", "timeline_sec": 4.0},
    )
    tl = temp_state_manager.execute_batch([op_split], mode="insert", agent_id="SPLIT_AGENT")
    track = tl.get_track("trk_video_1")
    assert len(track.clips) == 2

    c1 = track.clips[0]
    c2 = track.clips[1]
    assert c1.timeline_start_sec == 0.0
    assert c1.timeline_end_sec == 4.0
    assert c1.source_out_sec == 4.0

    assert c2.timeline_start_sec == 4.0
    assert c2.timeline_end_sec == 10.0
    assert c2.source_in_sec == 4.0


def test_atomic_transaction_rollback(temp_state_manager):
    """Verify that if one operation in a batch fails, the entire batch rolls back."""
    initial_version = temp_state_manager.get_timeline().version

    valid_op = BatchOperation(
        action=BatchActionType.INSERT_CLIP,
        params={
            "track_id": "trk_video_1",
            "name": "Should_Be_Rolled_Back",
            "timeline_start_sec": 0.0,
            "source_in_sec": 0.0,
            "source_out_sec": 5.0,
        },
    )
    # Invalid operation: RAZOR_SPLIT on non-existent clip
    invalid_op = BatchOperation(
        action=BatchActionType.RAZOR_SPLIT,
        params={"clip_id": "non_existent_clip_uuid", "timeline_sec": 2.0},
    )

    with pytest.raises(Exception):
        temp_state_manager.execute_batch([valid_op, invalid_op], mode="insert")

    # State must have rolled back completely
    tl = temp_state_manager.get_timeline()
    assert tl.version == initial_version
    track = tl.get_track("trk_video_1")
    assert len(track.clips) == 0


def test_undo_redo(temp_state_manager):
    op = BatchOperation(
        action=BatchActionType.INSERT_CLIP,
        params={
            "track_id": "trk_video_1",
            "name": "Undo_Me",
            "timeline_start_sec": 0.0,
            "source_in_sec": 0.0,
            "source_out_sec": 3.0,
        },
    )
    temp_state_manager.execute_batch([op])
    assert len(temp_state_manager.get_timeline().get_track("trk_video_1").clips) == 1

    # Undo
    temp_state_manager.undo()
    assert len(temp_state_manager.get_timeline().get_track("trk_video_1").clips) == 0

    # Redo
    temp_state_manager.redo()
    assert len(temp_state_manager.get_timeline().get_track("trk_video_1").clips) == 1


def test_agent_registration_and_heartbeat(temp_state_manager):
    agent = temp_state_manager.register_agent("AGENT_TEST", "Colorist", "#FF2A85")
    assert agent.agent_id == "AGENT_TEST"
    assert agent.role == "Colorist"

    hb = temp_state_manager.update_agent_heartbeat(
        "AGENT_TEST", playhead_sec=14.5, task="Grading shadows"
    )
    assert hb.playhead_sec == 14.5
    assert hb.current_task == "Grading shadows"
