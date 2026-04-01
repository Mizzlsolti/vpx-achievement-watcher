"""
Pinball Arcade Qt stylesheet – imported by Achievement_watcher.py.
Keeping the CSS in its own file makes the main module easier to read.
Includes a dynamic multi-theme system; Neon Blue reproduces the original
hardcoded look exactly.
"""

from __future__ import annotations

# ── Theme definitions ─────────────────────────────────────────────────────────

THEMES: dict[str, dict] = {
    "neon_blue": {
        "name": "Neon Blue",
        "icon": "💙",
        "primary": "#00E5FF",
        "accent": "#FF7F00",
        "border": "#00E5FF",
        "bg": "#080C16",
        "description": "Default look, cyan + orange",
        "page_accents": ["#00E5FF", "#FF7F00", "#00C86E", "#B450FF"],
    },
    "retro_arcade": {
        "name": "Retro Arcade",
        "icon": "🟢",
        "primary": "#33FF33",
        "accent": "#FFFF00",
        "border": "#33FF33",
        "bg": "#0A0A0A",
        "description": "Green & yellow on black – CRT monitor feel",
        "page_accents": ["#33FF33", "#FFFF00", "#FF9900", "#00CCFF"],
    },
    "classic_pinball": {
        "name": "Classic Pinball",
        "icon": "🟡",
        "primary": "#FFD700",
        "accent": "#FF4040",
        "border": "#FFD700",
        "bg": "#1A0A00",
        "description": "Gold & red on warm dark – classic machine glow",
        "page_accents": ["#FFD700", "#FF4040", "#FF8C00", "#FFAA00"],
    },
    "stealth": {
        "name": "Stealth",
        "icon": "⚫",
        "primary": "#999999",
        "accent": "#CCCCCC",
        "border": "#666666",
        "bg": "#0D0D0D",
        "description": "Muted grays – minimal and unobtrusive",
        "page_accents": ["#999999", "#CCCCCC", "#777777", "#AAAAAA"],
    },
    "synthwave": {
        "name": "Synthwave",
        "icon": "💜",
        "primary": "#FF44FF",
        "accent": "#00FFFF",
        "border": "#FF44FF",
        "bg": "#0D001A",
        "description": "Hot pink & cyan – 80s retrowave neon",
        "page_accents": ["#FF44FF", "#00FFFF", "#FF00AA", "#9900FF"],
    },
    "lava": {
        "name": "Lava",
        "icon": "🔴",
        "primary": "#FF6633",
        "accent": "#FFD700",
        "border": "#FF4500",
        "bg": "#1A0800",
        "description": "Orange & gold on ember – volcanic heat",
        "page_accents": ["#FF6633", "#FFD700", "#FF4500", "#FF9900"],
    },
    "arctic": {
        "name": "Arctic",
        "icon": "🔵",
        "primary": "#87CEEB",
        "accent": "#E0F0FF",
        "border": "#87CEEB",
        "bg": "#0A1520",
        "description": "Ice blue & frost white – cold and clear",
        "page_accents": ["#87CEEB", "#E0F0FF", "#5BB8D4", "#B0D8F0"],
    },
    "royal_purple": {
        "name": "Royal Purple",
        "icon": "👑",
        "primary": "#BB77DD",
        "accent": "#F1C40F",
        "border": "#9B59B6",
        "bg": "#120A1A",
        "description": "Lavender & gold – regal and elegant",
        "page_accents": ["#BB77DD", "#F1C40F", "#9B59B6", "#CC88EE"],
    },
    "toxic_green": {
        "name": "Toxic Green",
        "icon": "☢️",
        "primary": "#39FF14",
        "accent": "#FF073A",
        "border": "#39FF14",
        "bg": "#0A0F0A",
        "description": "Neon green & red – radioactive glow",
        "page_accents": ["#39FF14", "#FF073A", "#CCFF00", "#00FF88"],
    },
    "cyberpunk": {
        "name": "Cyberpunk",
        "icon": "⚡",
        "primary": "#F6E716",
        "accent": "#FF003C",
        "border": "#F6E716",
        "bg": "#0D0221",
        "description": "Electric yellow & neon pink – high contrast future",
        "page_accents": ["#F6E716", "#FF003C", "#00FFCC", "#FF6600"],
    },
    "ocean": {
        "name": "Ocean",
        "icon": "🌊",
        "primary": "#48CAE4",
        "accent": "#90E0EF",
        "border": "#0077B6",
        "bg": "#03111A",
        "description": "Light blue harmony – deep sea calm",
        "page_accents": ["#48CAE4", "#90E0EF", "#0077B6", "#00B4D8"],
    },
    "midnight_gold": {
        "name": "Midnight Gold",
        "icon": "✨",
        "primary": "#FFD700",
        "accent": "#FFA500",
        "border": "#DAA520",
        "bg": "#0A0A14",
        "description": "Gold & amber on midnight – luxury feel",
        "page_accents": ["#FFD700", "#FFA500", "#DAA520", "#FFCC00"],
    },
    "cherry_blossom": {
        "name": "Cherry Blossom",
        "icon": "🌸",
        "primary": "#FFB7C5",
        "accent": "#FF69B4",
        "border": "#FF69B4",
        "bg": "#1A0A12",
        "description": "Soft pink & rose – delicate and warm",
        "page_accents": ["#FFB7C5", "#FF69B4", "#FF99BB", "#FFD0DD"],
    },
    "forest": {
        "name": "Forest",
        "icon": "🌲",
        "primary": "#228B22",
        "accent": "#90EE90",
        "border": "#2E8B57",
        "bg": "#0A120A",
        "description": "Deep green & leaf – natural woodland",
        "page_accents": ["#228B22", "#90EE90", "#2E8B57", "#66CC44"],
    },
    "sunset": {
        "name": "Sunset",
        "icon": "🌅",
        "primary": "#FF6347",
        "accent": "#FFD700",
        "border": "#FF4500",
        "bg": "#1A0A05",
        "description": "Tomato red & gold – warm evening glow",
        "page_accents": ["#FF6347", "#FFD700", "#FF4500", "#FF8C00"],
    },
}

DEFAULT_THEME = "neon_blue"

_THEME_ORDER = [
    "neon_blue", "retro_arcade", "classic_pinball", "stealth",
    "synthwave", "lava", "arctic", "royal_purple",
    "toxic_green", "cyberpunk", "ocean",
    "midnight_gold", "cherry_blossom", "forest", "sunset",
]


def get_theme(theme_id: str) -> dict:
    """Return the theme dict for *theme_id*, falling back to the default."""
    return THEMES.get(theme_id, THEMES[DEFAULT_THEME])


def get_theme_color(cfg, key: str) -> str:
    """Return a single color string from the active theme stored in *cfg*."""
    theme_id = (cfg.OVERLAY or {}).get("theme", DEFAULT_THEME)
    theme = get_theme(theme_id)
    return theme.get(key, THEMES[DEFAULT_THEME].get(key, "#000000"))


def list_themes() -> list[tuple[str, dict]]:
    """Return an ordered list of (theme_id, theme_dict) tuples."""
    return [(tid, THEMES[tid]) for tid in _THEME_ORDER if tid in THEMES]


# ── Dynamic stylesheet generation ─────────────────────────────────────────────

def generate_stylesheet(theme_id: str = DEFAULT_THEME) -> str:
    """Generate the application QSS stylesheet for the given *theme_id*."""
    t = get_theme(theme_id)
    primary = t["primary"]
    accent = t["accent"]
    return f"""
        /* --- Basis: Tiefschwarz (Cabinet) --- */
        QMainWindow, QDialog, QWidget {{
            background-color: #121212;
            color: #E0E0E0;
            font-family: 'Segoe UI', sans-serif;
            font-size: 10pt;
        }}

        /* --- Die Haupt-Tabs --- */
        QTabWidget::pane {{
            border: 1px solid #333333;
            background-color: #181818;
            border-radius: 4px;
        }}
        QTabBar::tab {{
            background-color: #222222;
            color: #777777;
            padding: 10px 22px;
            border: 1px solid #333333;
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 3px;
            font-weight: bold;
            font-size: 11pt;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: #2A2A2A;
            color: #FFFFFF;
        }}
        QTabBar::tab:selected {{
            background-color: #181818;
            color: {accent};
            border-top: 3px solid {accent};
        }}

        /* --- Buttons (Arcade Style mit Metallic-Gradient) --- */
        QPushButton {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #383838, stop:1 #252525);
            color: #FFFFFF;
            border: 1px solid #555555;
            border-radius: 5px;
            padding: 7px 16px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            border: 1px solid {accent};
            color: {accent};
            background-color: #2C2C2C;
        }}
        QPushButton:pressed {{
            background-color: {accent};
            color: #000000;
            border: 1px solid {accent};
        }}

        /* --- Panels (Groupboxen für die Struktur) --- */
        QGroupBox {{
            border: 1px solid #444444;
            border-radius: 6px;
            margin-top: 20px;
            background-color: #1A1A1A;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            left: 15px;
            color: {primary};
            font-weight: bold;
            font-size: 11pt;
        }}

        /* --- Textfelder & Listen (z.B. für Stats) --- */
        QTextBrowser, QTextEdit {{
            background-color: #0A0A0A;
            border: 1px solid #333333;
            border-radius: 4px;
            color: #FFB000;
        }}

        /* --- Eingabefelder --- */
        QLineEdit, QComboBox, QSpinBox {{
            background-color: #222222;
            color: #FFFFFF;
            border: 1px solid #555555;
            border-radius: 3px;
            padding: 5px;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {primary};
        }}

        /* --- Slider (Für Volume & Skalierung) --- */
        QSlider::groove:horizontal {{
            border: 1px solid #444;
            height: 8px;
            background: #222;
            border-radius: 4px;
        }}
        QSlider::sub-page:horizontal {{
            background: {accent};
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background: #FFFFFF;
            border: 2px solid #777;
            width: 14px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 7px;
        }}

        /* --- Checkboxen --- */
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid #666;
            border-radius: 4px;
            background-color: #222;
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {accent};
        }}
        QCheckBox::indicator:checked {{
            background-color: {primary};
            border: 1px solid {primary};
        }}
        """


# ── Backward-compatibility alias ─────────────────────────────────────────────

pinball_arcade_style = generate_stylesheet(DEFAULT_THEME)


