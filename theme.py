"""
Dynamic theme system for VPX Achievement Watcher.

Provides ThemeColors dataclass, preset themes, build_stylesheet(),
get_stylesheet(), and the tc() accessor used throughout the UI.
"""

from dataclasses import dataclass


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert a #RRGGBB hex color to CSS rgba(r,g,b,alpha) string."""
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


@dataclass
class ThemeColors:
    """Named color slots for a UI theme."""
    accent_primary: str       # main accent (orange in DMD Classic)
    accent_secondary: str     # secondary accent (cyan in DMD Classic)
    bg_base: str              # darkest background
    bg_panel: str             # panel background
    bg_input: str             # input field background
    bg_elevated: str          # slightly lighter background
    border_subtle: str        # subtle borders
    border_medium: str        # medium borders
    text_primary: str         # main text
    text_secondary: str       # secondary/dim text
    text_muted: str           # very muted text
    success: str              # success / positive color
    danger: str               # danger / error color
    warning: str              # warning color
    stats_text: str           # stats / numeric readout color

    def accent_primary_rgba(self, alpha: float) -> str:
        """Return accent_primary as rgba(r,g,b,alpha) CSS string."""
        return _hex_to_rgba(self.accent_primary, alpha)

    def accent_secondary_rgba(self, alpha: float) -> str:
        """Return accent_secondary as rgba(r,g,b,alpha) CSS string."""
        return _hex_to_rgba(self.accent_secondary, alpha)


# ---------------------------------------------------------------------------
# Preset themes
# ---------------------------------------------------------------------------

PRESET_THEMES: dict = {
    "dmd_classic": ThemeColors(
        accent_primary="#FF7F00",
        accent_secondary="#00E5FF",
        bg_base="#121212",
        bg_panel="#1A1A1A",
        bg_input="#222222",
        bg_elevated="#181818",
        border_subtle="#333333",
        border_medium="#555555",
        text_primary="#E0E0E0",
        text_secondary="#999999",
        text_muted="#666666",
        success="#00C853",
        danger="#FF3B30",
        warning="#FFB000",
        stats_text="#FFB000",
    ),
    "neon_vapor": ThemeColors(
        accent_primary="#FF00FF",
        accent_secondary="#BF00FF",
        bg_base="#0D0010",
        bg_panel="#160020",
        bg_input="#1E0030",
        bg_elevated="#130018",
        border_subtle="#3A0050",
        border_medium="#5A0080",
        text_primary="#F0D0FF",
        text_secondary="#CC88EE",
        text_muted="#884499",
        success="#00FF99",
        danger="#FF3366",
        warning="#FF99FF",
        stats_text="#FF99FF",
    ),
    "emerald_machine": ThemeColors(
        accent_primary="#00E676",
        accent_secondary="#69FF47",
        bg_base="#001008",
        bg_panel="#001A0D",
        bg_input="#002214",
        bg_elevated="#00150A",
        border_subtle="#003320",
        border_medium="#005530",
        text_primary="#C8FFD4",
        text_secondary="#88DDAA",
        text_muted="#447755",
        success="#00C853",
        danger="#FF3B30",
        warning="#FFCC00",
        stats_text="#69FF47",
    ),
    "arctic_frost": ThemeColors(
        accent_primary="#80D8FF",
        accent_secondary="#E0F7FA",
        bg_base="#0A0F14",
        bg_panel="#111820",
        bg_input="#162030",
        bg_elevated="#0E1520",
        border_subtle="#1E3040",
        border_medium="#2E4860",
        text_primary="#DDEFFF",
        text_secondary="#90BBCC",
        text_muted="#4A7080",
        success="#00E5FF",
        danger="#FF5555",
        warning="#FFE082",
        stats_text="#80D8FF",
    ),
    "crimson_blitz": ThemeColors(
        accent_primary="#FF3B30",
        accent_secondary="#FF8A65",
        bg_base="#120A0A",
        bg_panel="#1C1010",
        bg_input="#241414",
        bg_elevated="#180C0C",
        border_subtle="#3D1A1A",
        border_medium="#5C2828",
        text_primary="#FFE0E0",
        text_secondary="#DD9999",
        text_muted="#885555",
        success="#66BB6A",
        danger="#FF0000",
        warning="#FFA726",
        stats_text="#FF8A65",
    ),
    "solar_flare": ThemeColors(
        accent_primary="#FFD600",
        accent_secondary="#FF9800",
        bg_base="#100D00",
        bg_panel="#1A1500",
        bg_input="#221B00",
        bg_elevated="#181200",
        border_subtle="#3D3000",
        border_medium="#5C4800",
        text_primary="#FFF8DC",
        text_secondary="#DDCC88",
        text_muted="#887733",
        success="#A5D6A7",
        danger="#FF5252",
        warning="#FF9800",
        stats_text="#FFD600",
    ),
    "midnight_cobalt": ThemeColors(
        accent_primary="#4488FF",
        accent_secondary="#00BFFF",
        bg_base="#080C14",
        bg_panel="#0E1420",
        bg_input="#141C2E",
        bg_elevated="#0B1018",
        border_subtle="#1A2840",
        border_medium="#263D60",
        text_primary="#D0E4FF",
        text_secondary="#8899CC",
        text_muted="#445577",
        success="#29B6F6",
        danger="#FF5252",
        warning="#FFA726",
        stats_text="#4488FF",
    ),
    "cyber_punk": ThemeColors(
        accent_primary="#FF006E",
        accent_secondary="#FFEA00",
        bg_base="#08000E",
        bg_panel="#120016",
        bg_input="#1A0020",
        bg_elevated="#0E0012",
        border_subtle="#330040",
        border_medium="#550066",
        text_primary="#FFE0FF",
        text_secondary="#DD88CC",
        text_muted="#774455",
        success="#39FF14",
        danger="#FF006E",
        warning="#FFEA00",
        stats_text="#FFEA00",
    ),
    "carbon_steel": ThemeColors(
        accent_primary="#90A4AE",
        accent_secondary="#CFD8DC",
        bg_base="#0A0A0A",
        bg_panel="#141414",
        bg_input="#1C1C1C",
        bg_elevated="#111111",
        border_subtle="#2A2A2A",
        border_medium="#3D3D3D",
        text_primary="#ECEFF1",
        text_secondary="#90A4AE",
        text_muted="#546E7A",
        success="#80CBC4",
        danger="#EF5350",
        warning="#FFCA28",
        stats_text="#B0BEC5",
    ),
    "toxic_acid": ThemeColors(
        accent_primary="#C6FF00",
        accent_secondary="#76FF03",
        bg_base="#060A00",
        bg_panel="#0D1400",
        bg_input="#141C00",
        bg_elevated="#0A1000",
        border_subtle="#2A3800",
        border_medium="#405400",
        text_primary="#F0FFD0",
        text_secondary="#AABB66",
        text_muted="#667733",
        success="#00E676",
        danger="#FF5252",
        warning="#FFD600",
        stats_text="#C6FF00",
    ),
}

# Human-readable display names (for UI)
THEME_DISPLAY_NAMES: dict = {
    "dmd_classic":     "DMD Classic",
    "neon_vapor":      "Neon Vapor",
    "emerald_machine": "Emerald Machine",
    "arctic_frost":    "Arctic Frost",
    "crimson_blitz":   "Crimson Blitz",
    "solar_flare":     "Solar Flare",
    "midnight_cobalt": "Midnight Cobalt",
    "cyber_punk":      "Cyber Punk",
    "carbon_steel":    "Carbon Steel",
    "toxic_acid":      "Toxic Acid",
}


# ---------------------------------------------------------------------------
# Stylesheet builder
# ---------------------------------------------------------------------------

def build_stylesheet(colors: ThemeColors) -> str:
    """Generate the full Qt stylesheet for the given ThemeColors."""
    c = colors
    return f"""
        /* --- Base: deep black (cabinet) --- */
        QMainWindow, QDialog, QWidget {{
            background-color: {c.bg_base};
            color: {c.text_primary};
            font-family: 'Segoe UI', sans-serif;
            font-size: 10pt;
        }}

        /* --- Main tabs --- */
        QTabWidget::pane {{
            border: 1px solid {c.border_subtle};
            background-color: {c.bg_elevated};
            border-radius: 4px;
        }}
        QTabBar::tab {{
            background-color: {c.bg_input};
            color: {c.text_muted};
            padding: 10px 22px;
            border: 1px solid {c.border_subtle};
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
            background-color: {c.bg_elevated};
            color: {c.accent_primary};
            border-top: 3px solid {c.accent_primary};
        }}

        /* --- Buttons --- */
        QPushButton {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #383838, stop:1 #252525);
            color: #FFFFFF;
            border: 1px solid {c.border_medium};
            border-radius: 5px;
            padding: 7px 16px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            border: 1px solid {c.accent_primary};
            color: {c.accent_primary};
            background-color: #2C2C2C;
        }}
        QPushButton:pressed {{
            background-color: {c.accent_primary};
            color: #000000;
            border: 1px solid {c.accent_primary};
        }}

        /* --- Group boxes --- */
        QGroupBox {{
            border: 1px solid {c.border_medium};
            border-radius: 6px;
            margin-top: 20px;
            background-color: {c.bg_panel};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            left: 15px;
            color: {c.accent_secondary};
            font-weight: bold;
            font-size: 11pt;
        }}

        /* --- Text browsers / editors --- */
        QTextBrowser, QTextEdit {{
            background-color: #0A0A0A;
            border: 1px solid {c.border_subtle};
            border-radius: 4px;
            color: {c.stats_text};
        }}

        /* --- Input fields --- */
        QLineEdit, QComboBox, QSpinBox {{
            background-color: {c.bg_input};
            color: #FFFFFF;
            border: 1px solid {c.border_medium};
            border-radius: 3px;
            padding: 5px;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {c.accent_secondary};
        }}

        /* --- Sliders --- */
        QSlider::groove:horizontal {{
            border: 1px solid {c.border_medium};
            height: 8px;
            background: {c.bg_input};
            border-radius: 4px;
        }}
        QSlider::sub-page:horizontal {{
            background: {c.accent_primary};
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

        /* --- Checkboxes --- */
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid #666;
            border-radius: 4px;
            background-color: {c.bg_input};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {c.accent_primary};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c.accent_secondary};
            border: 1px solid {c.accent_secondary};
        }}
        """


def get_stylesheet(theme_key: str) -> str:
    """Return the built stylesheet for the given theme key.

    Falls back to 'dmd_classic' if the key is unknown.
    """
    colors = PRESET_THEMES.get(theme_key, PRESET_THEMES["dmd_classic"])
    return build_stylesheet(colors)


# ---------------------------------------------------------------------------
# Active-theme accessor
# ---------------------------------------------------------------------------

_active_colors: ThemeColors = PRESET_THEMES["dmd_classic"]


def set_active_theme(theme_key: str) -> None:
    """Set the module-level active theme."""
    global _active_colors
    _active_colors = PRESET_THEMES.get(theme_key, PRESET_THEMES["dmd_classic"])


def tc() -> ThemeColors:
    """Return the currently active ThemeColors instance."""
    return _active_colors


# ---------------------------------------------------------------------------
# Backward-compatibility shim
# ---------------------------------------------------------------------------

# Keep pinball_arcade_style available so that any third-party code that still
# imports it directly doesn't break immediately.
pinball_arcade_style = build_stylesheet(PRESET_THEMES["dmd_classic"])
