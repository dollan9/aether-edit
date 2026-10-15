"""
AETHER-EDIT: Media Ingestion Watchdog Daemon
Monitors ./workspace/media_pool/ for media drops, calculates SHA-256 hashes,
and coordinates Proxy, Audio, and Vision telemetry analysis workers.
"""

import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Set
from uuid import uuid4

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config import MEDIA_POOL_DIR
from core.event_bus import event_bus
from core.schema import IngestStatus, MediaAsset
from core.state_manager import StateManager
from ingest.audio_analyzer import AudioAnalyzer
from ingest.proxy_generator import ProxyGenerator
from ingest.vision_analyzer import VisionAnalyzer

logger = logging.getLogger("aether_edit.watcher")

VALID_EXTENSIONS: Set[str] = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".wav", ".mp3", ".m4a"
}


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 checksum of a media file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()


class MediaHandler(FileSystemEventHandler):
    """Handles newly created and modified media files in media_pool/."""

    def __init__(self, watcher: "MediaWatcher") -> None:
        super().__init__()
        self.watcher = watcher

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() in VALID_EXTENSIONS:
            self.watcher.queue_ingestion(p)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() in VALID_EXTENSIONS:
            self.watcher.queue_ingestion(p)


class MediaWatcher:
    """Watchdog monitor and ingestion pipeline manager."""

    def __init__(
        self,
        state_manager: StateManager,
        media_dir: Path = MEDIA_POOL_DIR,
    ) -> None:
        self.state_manager = state_manager
        self.media_dir = Path(media_dir)
        self.media_dir.mkdir(parents=True, exist_ok=True)

        self.proxy_gen = ProxyGenerator()
        self.audio_analyzer = AudioAnalyzer()
        self.vision_analyzer = VisionAnalyzer()

        self._observer: Optional[Observer] = None
        self._processing_paths: Set[str] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the watchdog filesystem observer and scan existing files."""
        self.scan_existing_media()

        self._observer = Observer()
        handler = MediaHandler(self)
        self._observer.schedule(handler, str(self.media_dir.resolve()), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        logger.info(f"Media watcher active on: {self.media_dir.resolve()}")

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None

    def scan_existing_media(self) -> None:
        """Scan media pool folder on startup and ingest unanalyzed assets."""
        for p in self.media_dir.iterdir():
            if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS:
                self.queue_ingestion(p)

    def queue_ingestion(self, file_path: Path) -> None:
        """Enqueue file for background processing."""
        path_str = str(file_path.resolve())
        with self._lock:
            if path_str in self._processing_paths:
                return
            self._processing_paths.add(path_str)

        thread = threading.Thread(
            target=self._process_file_pipeline,
            args=(file_path,),
            daemon=True,
            name=f"Ingest-{file_path.name}",
        )
        thread.start()

    def _process_file_pipeline(self, file_path: Path) -> None:
        path_str = str(file_path.resolve())
        try:
            # Wait for file write completion (file size stabilization)
            stable_size = -1
            for _ in range(20):
                if file_path.exists():
                    current_size = file_path.stat().st_size
                    if current_size == stable_size and current_size > 0:
                        break
                    stable_size = current_size
                time.sleep(0.25)

            if not file_path.exists() or file_path.stat().st_size == 0:
                return

            file_hash = calculate_file_hash(file_path)

            # Check if already registered
            existing_assets = self.state_manager.list_media_assets()
            for ea in existing_assets:
                if ea.file_hash == file_hash and ea.ingest_status == IngestStatus.READY:
                    logger.info(f"Asset {file_path.name} already analyzed and ready.")
                    return

            asset_id = str(uuid4())
            rel_path = str(file_path.relative_to(self.media_dir))
            asset = MediaAsset(
                asset_id=asset_id,
                filename=file_path.name,
                relative_path=rel_path,
                absolute_path=path_str,
                file_hash=file_hash,
                ingest_status=IngestStatus.GENERATING_PROXY,
            )
            self.state_manager.register_or_update_media(asset)
            event_bus.emit_terminal_log("INGEST", f"Ingesting: {file_path.name} (SHA: {file_hash[:8]})", "INFO")

            # 1. Technical Meta & 540p All-Intra Proxy
            meta = self.proxy_gen.probe_technical_meta(file_path)
            asset.technical_meta = meta
            proxy_path, thumb_path = self.proxy_gen.generate_proxy(file_path, asset_id)
            asset.proxy_path = str(proxy_path.resolve())

            # Generate 50Hz waveform peaks
            peaks = self.proxy_gen.generate_waveform_peaks(file_path)
            asset.audio_telemetry.waveform_peaks = peaks
            self.state_manager.register_or_update_media(asset)

            # 2. Audio Telemetry Analysis
            self.state_manager.set_media_status(asset_id, IngestStatus.ANALYZING_AUDIO)
            event_bus.emit_terminal_log("INGEST", f"Analyzing audio & Whisper transcript: {file_path.name}", "INFO")
            audio_telemetry = self.audio_analyzer.analyze_audio(file_path)
            # Retain previously generated waveform peaks
            audio_telemetry.waveform_peaks = peaks
            asset.audio_telemetry = audio_telemetry
            self.state_manager.register_or_update_media(asset)

            # 3. Vision Telemetry Analysis
            self.state_manager.set_media_status(asset_id, IngestStatus.ANALYZING_VISION)
            event_bus.emit_terminal_log("INGEST", f"Analyzing scene cuts & bounding boxes: {file_path.name}", "INFO")
            vision_telemetry = self.vision_analyzer.analyze_video(proxy_path)
            asset.visual_telemetry = vision_telemetry

            # 4. Finalize READY Status
            asset.ingest_status = IngestStatus.READY
            self.state_manager.register_or_update_media(asset)
            event_bus.emit_terminal_log(
                "INGEST",
                f"Asset READY: {file_path.name} ({len(vision_telemetry.scene_cuts)} cuts, {len(audio_telemetry.silence_intervals)} silences)",
                "SUCCESS",
            )

        except Exception as e:
            logger.error(f"Ingest pipeline failure for {file_path.name}: {e}", exc_info=True)
            self.state_manager.set_media_status(
                asset_id if "asset_id" in locals() else str(uuid4()),
                IngestStatus.ERROR,
                error=str(e),
            )
            event_bus.emit_terminal_log("INGEST", f"Failed ingesting {file_path.name}: {e}", "ERROR")
        finally:
            with self._lock:
                self._processing_paths.discard(path_str)
