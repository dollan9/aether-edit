"""
AETHER-EDIT: Media Pool Observatory Panel (Top-Left Quadrant)
Renders live video thumbnails, AI ingestion badges, technical metadata,
and provides an interactive Telemetry JSON Inspector Drawer.
"""

import json
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import MEDIA_POOL_DIR
from core.event_bus import event_bus
from core.schema import IngestStatus, MediaAsset
from core.state_manager import StateManager
from ui.theme import CYBER_PALETTE, FONT_FAMILY_MONO


class TelemetryInspectorDialog(QDialog):
    """Read-only cybernetic modal displaying full multi-modal telemetry JSON."""

    def __init__(self, asset: MediaAsset, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"TELEMETRY INSPECTOR // {asset.filename}")
        self.resize(720, 600)
        self.setStyleSheet(f"background-color: {CYBER_PALETTE['bg_panel']}; color: #FFFFFF;")

        layout = QVBoxLayout(self)

        title = QLabel(f"ASSET TELEMETRY: {asset.filename} ({asset.asset_id})")
        title.setStyleSheet(
            f"color: {CYBER_PALETTE['accent_cyan']}; font-family: {FONT_FAMILY_MONO}; font-weight: bold; font-size: 14px;"
        )
        layout.addWidget(title)

        text_view = QTextEdit()
        text_view.setReadOnly(True)
        text_view.setStyleSheet(f"""
            background-color: {CYBER_PALETTE['bg_inset']};
            color: {CYBER_PALETTE['accent_green']};
            font-family: {FONT_FAMILY_MONO};
            font-size: 12px;
            border: 1px solid {CYBER_PALETTE['border_subtle']};
        """)

        # Serialize full asset telemetry
        data = {
            "asset_id": asset.asset_id,
            "filename": asset.filename,
            "ingest_status": asset.ingest_status.value,
            "technical_meta": asset.technical_meta.model_dump(),
            "silence_intervals": [s.model_dump() for s in asset.audio_telemetry.silence_intervals],
            "loudness_spikes": [s.model_dump() for s in asset.audio_telemetry.loudness_spikes],
            "transcript_segments": [s.model_dump() for s in asset.audio_telemetry.transcript],
            "scene_cuts": [s.model_dump() for s in asset.visual_telemetry.scene_cuts],
            "bounding_boxes_summary": {
                f"frame_{k}": [b.model_dump() for b in v]
                for k, v in list(asset.visual_telemetry.bounding_boxes.items())[:20]
            },
        }
        text_view.setPlainText(json.dumps(data, indent=2))
        layout.addWidget(text_view)

        close_btn = QPushButton("CLOSE INSPECTOR")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class MediaAssetCard(QFrame):
    """Custom cybernetic card item for each media file in media_pool/."""

    def __init__(self, asset: MediaAsset, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.asset = asset
        self.setObjectName("MediaAssetCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#MediaAssetCard {{
                background-color: {CYBER_PALETTE['bg_inset']};
                border: 1px solid {CYBER_PALETTE['border_subtle']};
                border-radius: 4px;
                padding: 4px;
            }}
            QFrame#MediaAssetCard:hover {{
                border: 1px solid {CYBER_PALETTE['accent_cyan']};
                background-color: #162032;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # 1. Left Thumbnail (64x36)
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(64, 36)
        self.thumb_label.setStyleSheet("background-color: #0A0E17; border-radius: 2px;")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self._load_thumbnail()
        layout.addWidget(self.thumb_label)

        # 2. Center Metadata
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_lbl = QLabel(asset.filename)
        name_lbl.setStyleSheet("font-weight: 700; font-size: 12px; color: #F8FAFC;")
        info_layout.addWidget(name_lbl)

        sub_text = (
            f"<font color='{CYBER_PALETTE['accent_green']}'>●</font> "
            f"<font color='{CYBER_PALETTE['text_muted']}'>{asset.technical_meta.duration_sec:.1f}s | "
            f"{asset.technical_meta.width}x{asset.technical_meta.height} | {asset.technical_meta.fps:.0f}fps</font>"
        )
        sub_lbl = QLabel(sub_text)
        sub_lbl.setStyleSheet("font-size: 10px;")
        info_layout.addWidget(sub_lbl)

        layout.addLayout(info_layout, stretch=1)

        # 3. Right Status Pill Badge
        self.badge_lbl = QLabel()
        self.update_badge(asset.ingest_status)
        layout.addWidget(self.badge_lbl)

    def _load_thumbnail(self) -> None:
        # Check if thumbnail image exists
        thumb_file = Path(MEDIA_POOL_DIR.parent / "proxies" / f"{self.asset.asset_id}_thumb.jpg")
        if thumb_file.exists():
            pix = QPixmap(str(thumb_file)).scaled(
                64, 36, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self.thumb_label.setPixmap(pix)
        else:
            self.thumb_label.setText("VID")
            self.thumb_label.setStyleSheet(
                f"color: {CYBER_PALETTE['text_dim']}; font-family: {FONT_FAMILY_MONO}; font-size: 10px;"
            )

    def update_badge(self, status: IngestStatus) -> None:
        if status == IngestStatus.READY:
            text = "AI Analyzed"
            color = CYBER_PALETTE["accent_green"]
            bg = "#10B98122"
        elif status == IngestStatus.ERROR:
            text = "ERROR"
            color = "#EF4444"
            bg = "#EF444422"
        else:
            text = f"{status.value[:10]}..."
            color = CYBER_PALETTE["accent_cyan"]
            bg = "#00F5D422"

        self.badge_lbl.setText(f" {text} ")
        self.badge_lbl.setStyleSheet(f"""
            color: {color};
            background-color: {bg};
            border: 1px solid {color};
            border-radius: 8px;
            font-size: 9px;
            font-weight: bold;
            font-family: {FONT_FAMILY_MONO};
            padding: 2px 6px;
        """)

    def mousePressEvent(self, event) -> None:
        dialog = TelemetryInspectorDialog(self.asset, self)
        dialog.exec()


class MediaPoolPanel(QFrame):
    """Master Media Pool widget container."""

    def __init__(self, state_manager: StateManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state_manager = state_manager
        self.setProperty("class", "CyberPanel")

        self.cards: Dict[str, MediaAssetCard] = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Header bar
        header_layout = QHBoxLayout()
        title = QLabel("MEDIA POOL")
        title.setProperty("class", "HeaderLabel")
        header_layout.addWidget(title)
        header_layout.addStretch()

        reindex_btn = QPushButton("RE-INDEX")
        reindex_btn.setFixedHeight(24)
        reindex_btn.clicked.connect(self._on_reindex)
        header_layout.addWidget(reindex_btn)

        main_layout.addLayout(header_layout)

        # Scroll Area for Cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none; background: transparent;")

        self.card_container = QWidget()
        self.card_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.card_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch()

        self.scroll.setWidget(self.card_container)
        main_layout.addWidget(self.scroll)

        # Connect to event bus
        event_bus.media_registered.connect(self.on_media_registered)

        # Populate initial media
        self.refresh_list()

    def refresh_list(self) -> None:
        assets = self.state_manager.list_media_assets()
        for a in assets:
            self.on_media_registered(a)

    def on_media_registered(self, asset: MediaAsset) -> None:
        """Add or update an asset card dynamically."""
        if asset.asset_id in self.cards:
            card = self.cards[asset.asset_id]
            card.asset = asset
            card._load_thumbnail()
            card.update_badge(asset.ingest_status)
        else:
            card = MediaAssetCard(asset, self.card_container)
            self.cards[asset.asset_id] = card
            # Insert above the bottom stretch
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def _on_reindex(self) -> None:
        event_bus.emit_terminal_log("SYSTEM", "Scanning media pool directory...", "INFO")
        self.refresh_list()
