"""
Unit tests for FastAPI REST Control Plane Endpoints
"""

import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.rest_server import create_app
from api.ws_manager import WebSocketManager
from core.state_manager import StateManager
from engine.realtime_compositor import RealtimeCompositor
from engine.renderer import HardwareRenderer


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = StateManager(
            timeline_path=Path(tmpdir) / "tl.json",
            registry_path=Path(tmpdir) / "reg.json",
        )
        comp = RealtimeCompositor(sm)
        rend = HardwareRenderer(sm, exports_dir=Path(tmpdir))
        ws = WebSocketManager()
        app = create_app(sm, comp, rend, ws)
        with TestClient(app) as test_client:
            yield test_client


def test_agent_registration_endpoint(client):
    res = client.post(
        "/api/v1/agents/register",
        json={"agent_id": "AGENT_UNIT", "role": "VFX", "preferred_color": "#FF2A85"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["agent_id"] == "AGENT_UNIT"
    assert data["role"] == "VFX"


def test_timeline_endpoint(client):
    res = client.get("/api/v1/timeline")
    assert res.status_code == 200
    data = res.json()
    assert "tracks" in data
    assert len(data["tracks"]) >= 4


def test_batch_mutation_endpoint(client):
    batch_payload = {
        "mode": "insert",
        "operations": [
            {
                "action": "INSERT_CLIP",
                "params": {
                    "track_id": "trk_video_1",
                    "name": "API_Inserted_Clip",
                    "timeline_start_sec": 0.0,
                    "source_in_sec": 0.0,
                    "source_out_sec": 8.0,
                },
            }
        ],
    }
    res = client.post(
        "/api/v1/timeline/batch",
        json=batch_payload,
        headers={"X-Agent-ID": "API_AGENT"},
    )
    assert res.status_code == 200
    data = res.json()
    v1 = next(t for t in data["tracks"] if t["track_id"] == "trk_video_1")
    assert len(v1["clips"]) == 1
    assert v1["clips"][0]["name"] == "API_Inserted_Clip"


def test_system_status_endpoint(client):
    res = client.get("/api/v1/status/system")
    assert res.status_code == 200
    data = res.json()
    assert "cpu_percent" in data
    assert "gpu" in data
