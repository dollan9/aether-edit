# Architectural Decision Records (ADRs) & Engineering Conventions

### ADR-01: Deterministic FFmpeg Filter Graph via -filter_complex_script
- **Context**: Passing dozens of clip overlays and transforms directly as CLI command-line arguments exceeds Windows 8191-character command line limits.
- **Decision**: FilterGraphCompiler compiles all video, zoom, audio, and ducking instructions into a temporary `filter_complex.txt` file and passes `-filter_complex_script <path>` to FFmpeg.
- **Consequence**: Bypasses all CLI length constraints and allows arbitrary track complexity.

### ADR-02: 540p All-Intra (-g 1) Scrubbable Proxies
- **Context**: Standard long-GOP H.264 video files incur significant decoding latency when seeking arbitrary non-keyframe timestamps.
- **Decision**: Ingest automatically encodes 540p proxies with `-g 1` (every frame is an I-frame).
- **Consequence**: Seeking and scrubbing in the preview viewport is instantaneous with sub-millisecond response times.

### ADR-03: Thread-Safe QtSignal Event Bus Fan-Out
- **Context**: FastAPI, Uvicorn, and background Watchdog threads run outside the Qt main thread. Directly modifying PySide6 UI elements from foreign threads causes crashes.
- **Decision**: `core/event_bus.py` uses PySide6 `Signal` emitters which automatically queue messages into Qt's main event loop safely.

### ADR-04: Model Context Protocol (MCP) 2.x Architecture
- **Context**: In `mcp>=2.0`, `FastMCP` was transitioned to `MCPServer`.
- **Decision**: Implement `MCPServer` from `mcp.server.mcpserver` with structured tools for telemetry, timeline inspection, batch editing, silence cutting, and frame inspection.
