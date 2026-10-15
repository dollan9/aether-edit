"""
AETHER-EDIT: Cybernetic Aesthetic Theme & QSS Stylesheets
Deep Obsidian Void (#0A0E17), Panel Dark (#111726), Cyber Cyan (#00F5D4),
Neon Magenta (#FF2A85), Electric Purple (#9B5DE5), Matrix Green (#10B981)
"""

from typing import Dict

CYBER_PALETTE: Dict[str, str] = {
    "bg_main": "#0A0E17",          # Deep Obsidian Void
    "bg_panel": "#111726",         # Panel Background
    "bg_inset": "#070A10",         # Terminal & Graph Inset
    "border_subtle": "#1E293B",    # 1px border
    "border_highlight": "#2DD4BF33", # Subtle cyan glow border
    "accent_cyan": "#00F5D4",      # Cyber Cyan
    "accent_magenta": "#FF2A85",   # Neon Magenta
    "accent_purple": "#9B5DE5",    # Electric Purple
    "accent_green": "#10B981",     # Matrix Green
    "accent_amber": "#F59E0B",     # Amber Warning
    "text_primary": "#F8FAFC",     # Bright Crisp White
    "text_muted": "#94A3B8",       # Technical Gray
    "text_dim": "#475569",         # Deep Slate
}

FONT_FAMILY_MONO = "Consolas, 'JetBrains Mono', 'Fira Code', 'Courier New', monospace"
FONT_FAMILY_SANS = "'Segoe UI', Inter, -apple-system, sans-serif"


def get_app_stylesheet() -> str:
    """Generate global application QSS stylesheet."""
    return f"""
    QMainWindow {{
        background-color: {CYBER_PALETTE['bg_main']};
        color: {CYBER_PALETTE['text_primary']};
    }}

    QWidget {{
        background-color: transparent;
        color: {CYBER_PALETTE['text_primary']};
        font-family: {FONT_FAMILY_SANS};
        font-size: 13px;
    }}

    /* Cybernetic Panel Frame */
    QFrame.CyberPanel {{
        background-color: {CYBER_PALETTE['bg_panel']};
        border: 1px solid {CYBER_PALETTE['border_subtle']};
        border-radius: 4px;
    }}

    QLabel {{
        color: {CYBER_PALETTE['text_primary']};
    }}

    QLabel.HeaderLabel {{
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: {CYBER_PALETTE['accent_cyan']};
        font-family: {FONT_FAMILY_MONO};
        text-transform: uppercase;
    }}

    QLabel.MutedLabel {{
        color: {CYBER_PALETTE['text_muted']};
        font-size: 11px;
    }}

    /* Interactive Buttons */
    QPushButton {{
        background-color: #1E293B;
        color: {CYBER_PALETTE['accent_cyan']};
        border: 1px solid #334155;
        border-radius: 3px;
        padding: 5px 12px;
        font-family: {FONT_FAMILY_MONO};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.5px;
    }}

    QPushButton:hover {{
        background-color: #2DD4BF22;
        border: 1px solid {CYBER_PALETTE['accent_cyan']};
        color: #FFFFFF;
    }}

    QPushButton:pressed {{
        background-color: #2DD4BF44;
    }}

    QPushButton.PrimaryAccent {{
        background-color: {CYBER_PALETTE['accent_cyan']};
        color: #0A0E17;
        font-weight: 700;
        border: none;
    }}

    QPushButton.PrimaryAccent:hover {{
        background-color: #38F8DE;
        color: #000000;
    }}

    QPushButton.DangerAccent {{
        background-color: #EF444422;
        color: #EF4444;
        border: 1px solid #EF4444;
    }}

    QPushButton.DangerAccent:hover {{
        background-color: #EF4444;
        color: #FFFFFF;
    }}

    /* Terminal Console */
    QTextEdit.TerminalConsole {{
        background-color: {CYBER_PALETTE['bg_inset']};
        color: {CYBER_PALETTE['accent_green']};
        font-family: {FONT_FAMILY_MONO};
        font-size: 12px;
        border: 1px solid {CYBER_PALETTE['border_subtle']};
        border-radius: 3px;
        padding: 6px;
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background: {CYBER_PALETTE['bg_inset']};
        width: 8px;
        margin: 0px;
    }}

    QScrollBar::handle:vertical {{
        background: #334155;
        min-height: 20px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {CYBER_PALETTE['accent_cyan']};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: {CYBER_PALETTE['bg_inset']};
        height: 8px;
        margin: 0px;
    }}

    QScrollBar::handle:horizontal {{
        background: #334155;
        min-width: 20px;
        border-radius: 4px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {CYBER_PALETTE['accent_cyan']};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* Progress Bar */
    QProgressBar {{
        background-color: {CYBER_PALETTE['bg_inset']};
        border: 1px solid {CYBER_PALETTE['border_subtle']};
        border-radius: 2px;
        text-align: center;
        color: #FFFFFF;
        font-family: {FONT_FAMILY_MONO};
        font-size: 11px;
    }}

    QProgressBar::chunk {{
        background-color: {CYBER_PALETTE['accent_cyan']};
        border-radius: 2px;
    }}

    /* Sliders */
    QSlider::groove:horizontal {{
        border: 1px solid #1E293B;
        height: 4px;
        background: #0F172A;
        border-radius: 2px;
    }}

    QSlider::sub-page:horizontal {{
        background: {CYBER_PALETTE['accent_cyan']};
        border-radius: 2px;
    }}

    QSlider::handle:horizontal {{
        background: #FFFFFF;
        border: 1px solid {CYBER_PALETTE['accent_cyan']};
        width: 12px;
        margin-top: -4px;
        margin-bottom: -4px;
        border-radius: 6px;
    }}

    QSlider::handle:horizontal:hover {{
        background: {CYBER_PALETTE['accent_cyan']};
    }}
    """
