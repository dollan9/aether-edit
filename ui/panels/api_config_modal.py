"""
AETHER-EDIT: API Configuration & Autonomous Director Modal
Allows human supervisor to supply LLM API keys (OpenAI, Anthropic, Gemini, DeepSeek),
configure MCP server port, and dispatch high-level autonomous editing directives.
"""

import asyncio
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import (
    ANTHROPIC_API_KEY,
    DEEPSEEK_API_KEY,
    GEMINI_API_KEY,
    MCP_PORT,
    OPENAI_API_KEY,
)
from core.event_bus import event_bus
from core.llm_director import LLMDirector
from ui.theme import CYBER_PALETTE, FONT_FAMILY_MONO


class ApiConfigModal(QDialog):
    """Configuration popup for AI agent keys, MCP port, and Director prompt dispatch."""

    def __init__(self, director: LLMDirector, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.director = director
        self.setWindowTitle("CYBERNETIC CONTROL // API & AUTONOMOUS AGENT CONFIG")
        self.resize(580, 520)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {CYBER_PALETTE['bg_panel']};
                color: #FFFFFF;
                border: 1px solid {CYBER_PALETTE['border_subtle']};
            }}
            QLineEdit, QTextEdit, QComboBox {{
                background-color: {CYBER_PALETTE['bg_inset']};
                border: 1px solid {CYBER_PALETTE['border_subtle']};
                color: {CYBER_PALETTE['accent_cyan']};
                font-family: {FONT_FAMILY_MONO};
                padding: 6px;
                border-radius: 3px;
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
                border: 1px solid {CYBER_PALETTE['accent_cyan']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("AI AGENT & LLM DIRECTOR CONFIGURATION")
        title.setProperty("class", "HeaderLabel")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        # Provider Selector
        self.provider_combo = QComboBox()
        self.provider_combo.addItems([
            "Autonomous Heuristic Director (Offline / Self-Contained)",
            "Gemini 1.5 / 2.0 / Flash",
            "OpenAI (GPT-4o / o1)",
            "Anthropic (Claude 3.5 Sonnet)",
            "DeepSeek (V3 / R1)",
        ])
        form.addRow("Agent Engine Provider:", self.provider_combo)

        # API Key Inputs
        self.gemini_key_edit = QLineEdit(GEMINI_API_KEY)
        self.gemini_key_edit.setEchoMode(QLineEdit.Password)
        self.gemini_key_edit.setPlaceholderText("Paste Gemini API Key...")
        form.addRow("Gemini API Key:", self.gemini_key_edit)

        self.openai_key_edit = QLineEdit(OPENAI_API_KEY)
        self.openai_key_edit.setEchoMode(QLineEdit.Password)
        self.openai_key_edit.setPlaceholderText("Paste OpenAI API Key...")
        form.addRow("OpenAI API Key:", self.openai_key_edit)

        self.anthropic_key_edit = QLineEdit(ANTHROPIC_API_KEY)
        self.anthropic_key_edit.setEchoMode(QLineEdit.Password)
        self.anthropic_key_edit.setPlaceholderText("Paste Anthropic API Key...")
        form.addRow("Anthropic API Key:", self.anthropic_key_edit)

        self.deepseek_key_edit = QLineEdit(DEEPSEEK_API_KEY)
        self.deepseek_key_edit.setEchoMode(QLineEdit.Password)
        self.deepseek_key_edit.setPlaceholderText("Paste DeepSeek API Key...")
        form.addRow("DeepSeek API Key:", self.deepseek_key_edit)

        self.mcp_port_edit = QLineEdit(str(MCP_PORT))
        form.addRow("MCP Server Port:", self.mcp_port_edit)

        layout.addLayout(form)

        # High-Level Autonomous Director Prompt
        prompt_label = QLabel("AUTONOMOUS DIRECTOR EDITING DIRECTIVE:")
        prompt_label.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {CYBER_PALETTE['accent_magenta']}; font-family: {FONT_FAMILY_MONO};"
        )
        layout.addWidget(prompt_label)

        self.prompt_text = QTextEdit()
        self.prompt_text.setPlainText(
            "Edit a high-retention 3-minute video from the raw footage, cut all dead air, "
            "zoom in on high-stress audio peaks, add dynamic subtitles, and sync tension music."
        )
        self.prompt_text.setFixedHeight(80)
        layout.addWidget(self.prompt_text)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.launch_btn = QPushButton("LAUNCH AUTONOMOUS DIRECTOR")
        self.launch_btn.setProperty("class", "PrimaryAccent")
        self.launch_btn.setFixedHeight(32)
        self.launch_btn.clicked.connect(self._launch_director)
        btn_layout.addWidget(self.launch_btn)

        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _launch_director(self) -> None:
        prompt = self.prompt_text.toPlainText().strip()
        provider_idx = self.provider_combo.currentIndex()
        provider = "heuristic"
        key = None

        if provider_idx == 1:
            provider = "gemini"
            key = self.gemini_key_edit.text().strip()
        elif provider_idx == 2:
            provider = "openai"
            key = self.openai_key_edit.text().strip()
        elif provider_idx == 3:
            provider = "anthropic"
            key = self.anthropic_key_edit.text().strip()
        elif provider_idx == 4:
            provider = "deepseek"
            key = self.deepseek_key_edit.text().strip()

        event_bus.emit_terminal_log("DIRECTOR", f"Triggered autonomous direction via {provider}", "INFO")

        # Run on event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(
                self.director.start_autonomous_direction(prompt, provider=provider, api_key=key)
            )
        self.accept()
