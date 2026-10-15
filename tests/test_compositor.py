"""
Unit tests for Realtime Compositor and Base64 Vision Inspection Frames
"""

import tempfile
from pathlib import Path
import numpy as np

from core.schema import BatchActionType, BatchOperation
from core.state_manager import StateManager
from engine.realtime_compositor import RealtimeCompositor


def test_realtime_compositor_blank_canvas():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = StateManager(timeline_path=Path(tmpdir) / "tl.json")
        compositor = RealtimeCompositor(sm)

        frame = compositor.render_composite_frame(timeline_sec=0.0, target_resolution=(640, 360))
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (360, 640, 3)

        b64 = compositor.get_frame_base64_jpeg(timeline_sec=0.0)
        assert isinstance(b64, str)
        assert len(b64) > 100
