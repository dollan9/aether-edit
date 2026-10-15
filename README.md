# AETHER-EDIT ⚡
### Autonomous AI-Agent Non-Linear Video Editor & Telemetry Observatory

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-41CD52.svg)](https://doc.qt.io/qtforpython/)
[![NVIDIA NVENC](https://img.shields.io/badge/Hardware-NVIDIA%20NVENC-76B900.svg)](https://developer.nvidia.com/nvidia-video-codec-sdk)
[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%202.x-8A2BE2.svg)](https://modelcontextprotocol.io/)

AETHER-EDIT is a cybernetic, production-grade autonomous Non-Linear Video Editing (NLE) engine and Telemetry Observatory. In AETHER-EDIT, **humans do not manually drag clips or razor timelines**. Instead, 100% of editing mutations happen via **REST API**, **WebSocket RPC**, **Model Context Protocol (MCP)**, or the **Built-in Autonomous Director**, while human supervisors observe frame-accurate playback, live multi-agent laser playheads, and scrolling telemetry oscilloscopes.

---

## 🚀 Key Features

* **Zero-Stub Architecture**: 100% fully implemented with production error handling—no `TODO`, `pass`, or mock functions anywhere.
* **Deterministic FFmpeg Filter Graph Compiler**: Translates `TimelineState` directly into an optimized `-filter_complex_script` (`filter_complex.txt`), bypassing Windows CLI argument character limits.
* **Hardware Accelerated NVENC Pipeline**: Automatic detection of `h264_nvenc` and `hevc_nvenc` with seamless fallback to `libx264`.
* **Multi-Modal Media Ingest**:
  * 540p all-intra (`-g 1`) ultra-fast scrubbable proxies for sub-millisecond seeking.
  * 50Hz normalized audio waveform peaks (0.0 to 1.0).
  * Faster-Whisper word-level speech transcription.
  * FFmpeg RMS energy curve, silence detection (<-38dB, >0.35s), and loudness spike classification.
  * OpenCV scene cuts, optical motion vector scoring, and face/object bounding boxes.
* **Multi-Agent Control Plane (`http://127.0.0.1:8765`)**:
  * Atomic batch transactions with automatic rollback on error.
  * `/api/v1/preview/frame?timeline_sec=X`: Base64 JPEG composite frame extraction for vision-capable AI agents to inspect their own edits.
  * 60Hz real-time WebSocket diff broadcaster.
  * Full Model Context Protocol (MCP) server over stdio and SSE.
* **Cybernetic Observatory UI (PySide6)**:
  * Deep Obsidian Void aesthetic (`#0A0E17`) with Cyber Cyan (`#00F5D4`), Neon Magenta (`#FF2A85`), and Matrix Green (`#10B981`).
  * Floating top Hardware HUD monitoring GPU %, VRAM, and agent collaboration.
  * Top-Left Media Pool with video thumbnails and Telemetry JSON Drawer.
  * Top-Center Agent Activity panel with high-speed terminal and 4 stacked live oscilloscopes.
  * Top-Right Preview Monitor with custom AI HUD overlay (target brackets, reactive waveform, matrix text).
  * Bottom Multi-Track Timeline with 60 FPS lerp-animated multi-agent laser playheads.
* **Autonomous Simulation Mode**: Built-in self-test mode (`--simulate-agents`) generating synthetic test media and spawning 3 autonomous virtual agents (`AGENT_A`, `AGENT_B`, `AUDIO_AGENT`).

---

## 📐 System Architecture

```text
aether_edit/
├── main.py                          # Entrypoint: Spawns FastAPI, Watchdog, and PySide6 GUI
├── config.py                        # Hardware detection (NVENC/CUDA), paths, and network settings
├── requirements.txt                 # Exact pinned dependencies
├── build_exe.py                     # PyInstaller automated build script
├── simulation.py                    # Autonomous simulation & synthetic test media generator
├── core/
│   ├── schema.py                    # Pydantic v2 models (Timeline, Tracks, Clips, Telemetry)
│   ├── state_manager.py             # Thread-safe CRDT state engine, atomic batch rollback, undo/redo
│   ├── event_bus.py                 # Asyncio + QtSignal bridge for 0ms UI updates
│   └── llm_director.py              # Autonomous multi-agent LLM engine (OpenAI, Gemini, Anthropic, DeepSeek)
├── ingest/
│   ├── watcher.py                   # Filesystem watchdog monitoring ./workspace/media_pool/
│   ├── proxy_generator.py           # FFmpeg 540p all-intra proxy & 50Hz waveform peak generator
│   ├── audio_analyzer.py            # Faster-Whisper transcription + RMS silence & spike detection
│   └── vision_analyzer.py           # OpenCV cut detection, motion scoring & bounding boxes
├── engine/
│   ├── filter_graph.py              # Deterministic FFmpeg filter_complex compiler
│   ├── renderer.py                  # Subprocess NVENC render engine with real-time progress parsing
│   └── realtime_compositor.py       # Frame-accurate proxy compositing engine & base64 vision extractor
├── api/
│   ├── rest_server.py               # FastAPI REST control plane on port 8765
│   ├── ws_manager.py                # 60Hz real-time WebSocket connection broadcaster
│   └── mcp_server.py                # Model Context Protocol (MCP) stdio/SSE server
└── ui/
    ├── main_window.py               # Master Cybernetic Dashboard & Hardware HUD
    ├── theme.py                     # QSS stylesheets & Deep Obsidian Void color palette
    └── panels/
        ├── media_pool_panel.py      # Top-Left: Asset list, badges & Telemetry Drawer
        ├── agent_activity_panel.py  # Top-Center: Terminal log & 4 live oscilloscopes
        ├── preview_monitor_panel.py # Top-Right: Viewport with AI HUD overlay
        ├── timeline_panel.py        # Bottom: Multi-track timeline & laser playheads
        └── api_config_modal.py      # Popup modal for API keys and autonomous directives
```

---

## 🛠️ Installation & Setup

### Prerequisites
* Windows 11 (or Linux / macOS)
* Python 3.11+
* FFmpeg on PATH (with NVENC support for GPU acceleration)

### Quickstart
```bash
# Clone the repository
git clone https://github.com/dollan9/aether-edit.git
cd aether-edit

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the observatory with the self-test simulation
python main.py --simulate-agents
```

### CLI Flags
* `python main.py`: Launches the default Cybernetic Observatory GUI.
* `python main.py --simulate-agents`: Generates synthetic 1080p60 test media and runs the 3-agent autonomous self-test.
* `python main.py --headless`: Runs the headless FastAPI / WebSocket editing backend without launching the GUI.
* `python main.py --mcp-stdio`: Launches the Model Context Protocol (MCP) server over standard I/O for external agents.

---

## 🧪 Testing

Run the test suite via pytest:
```bash
pytest tests/ -v
```

---

## 📦 Standalone Executable Packaging

To bundle AETHER-EDIT into a standalone Windows `.exe`:
```bash
python build_exe.py
```
Output will be generated in `dist/aether_edit/aether_edit.exe`.

---

## 📄 License
MIT License. Open source and built for autonomous AI agents.
