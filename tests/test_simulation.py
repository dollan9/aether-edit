"""
End-to-end test for Autonomous Simulation Mode
"""

import tempfile
from pathlib import Path

from core.schema import IngestStatus
from core.state_manager import StateManager
from simulation import generate_synthetic_media, run_autonomous_simulation


def test_simulation_workflow():
    with tempfile.TemporaryDirectory() as tmpdir:
        tl_path = Path(tmpdir) / "timeline.json"
        reg_path = Path(tmpdir) / "registry.json"
        sm = StateManager(timeline_path=tl_path, registry_path=reg_path)

        # 1. Test synthetic media generation (micro 3s file for speedy unit test)
        sample_path = Path(tmpdir) / "synthetic_test.mp4"
        generated = generate_synthetic_media(sample_path, duration_sec=3)
        assert generated.exists()
        assert generated.stat().st_size > 1000

        # 2. Run simulation pipeline
        run_autonomous_simulation(sm)

        # Verify agents were registered
        tl = sm.get_timeline()
        assert "AGENT_A" in tl.active_agents
        assert "AGENT_B" in tl.active_agents
        assert "AUDIO_AGENT" in tl.active_agents

        # Verify clips were populated and split
        v1 = tl.get_track("trk_video_1")
        assert v1 is not None
        assert len(v1.clips) >= 2

        # Verify audio ducking keyframes
        a2 = tl.get_track("trk_audio_2")
        assert a2 is not None
        assert len(a2.clips) >= 1
        assert len(a2.clips[0].audio_envelope.volume_keyframes) >= 2

        # Verify subtitles
        sub = tl.get_track("trk_subtitles")
        assert sub is not None
        assert len(sub.clips) >= 2
