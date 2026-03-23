"""
Theme definitions for VPX Achievement Watcher.
Each theme is a dict with keys: name, icon, primary, accent, border, bg, description
"""

THEMES = {
    "neon_blue": {
        "name": "Neon Blue",
        "icon": "💙",
        "primary": "#00E5FF",
        "accent": "#FF7F00",
        "border": "#00E5FF",
        "bg": "#080C16",
        "description": "Default look, cyan + orange",
    },
    "retro_arcade": {
        "name": "Retro Arcade",
        "icon": "🟢",
        "primary": "#33FF33",
        "accent": "#FFFF00",
        "border": "#33FF33",
        "bg": "#0A0A0A",
        "description": "Green monochrome CRT",
    },
    "classic_pinball": {
        "name": "Classic Pinball",
        "icon": "🟡",
        "primary": "#FFD700",
        "accent": "#FF2020",
        "border": "#FFD700",
        "bg": "#1A0A00",
        "description": "Gold & red, warm",
    },
    "stealth": {
        "name": "Stealth",
        "icon": "⚫",
        "primary": "#888888",
        "accent": "#AAAAAA",
        "border": "#555555",
        "bg": "#0D0D0D",
        "description": "Minimal, muted grays",
    },
    "synthwave": {
        "name": "Synthwave",
        "icon": "💜",
        "primary": "#FF00FF",
        "accent": "#00FFFF",
        "border": "#FF00FF",
        "bg": "#0D001A",
        "description": "80s retrowave, pink + cyan",
    },
    "lava": {
        "name": "Lava",
        "icon": "🔴",
        "primary": "#FF4500",
        "accent": "#FFD700",
        "border": "#FF4500",
        "bg": "#1A0800",
        "description": "Fire & ember",
    },
    "arctic": {
        "name": "Arctic",
        "icon": "🔵",
        "primary": "#87CEEB",
        "accent": "#FFFFFF",
        "border": "#87CEEB",
        "bg": "#0A1520",
        "description": "Cold, icy blues",
    },
    "royal_purple": {
        "name": "Royal Purple",
        "icon": "👑",
        "primary": "#9B59B6",
        "accent": "#F1C40F",
        "border": "#9B59B6",
        "bg": "#120A1A",
        "description": "Regal purple + gold",
    },
    "toxic_green": {
        "name": "Toxic Green",
        "icon": "☢️",
        "primary": "#39FF14",
        "accent": "#FF073A",
        "border": "#39FF14",
        "bg": "#0A0F0A",
        "description": "Radioactive neon",
    },
    "midnight_gold": {
        "name": "Midnight Gold",
        "icon": "✨",
        "primary": "#C9A84C",
        "accent": "#FFFFFF",
        "border": "#C9A84C",
        "bg": "#0F0F0F",
        "description": "Elegant, premium",
    },
    "cyberpunk": {
        "name": "Cyberpunk",
        "icon": "⚡",
        "primary": "#F6E716",
        "accent": "#FF003C",
        "border": "#F6E716",
        "bg": "#0D0221",
        "description": "Yellow/pink on dark",
    },
    "ocean": {
        "name": "Ocean",
        "icon": "🌊",
        "primary": "#0077B6",
        "accent": "#48CAE4",
        "border": "#0077B6",
        "bg": "#03111A",
        "description": "Deep blue gradients",
    },
}

DEFAULT_THEME = "neon_blue"

def get_theme(theme_id: str) -> dict:
    """Return theme dict by ID, falling back to default."""
    return THEMES.get(theme_id, THEMES[DEFAULT_THEME])

def get_theme_color(cfg, key: str) -> str:
    """Get a specific theme color from current config.
    key is one of: primary, accent, border, bg
    Falls back to neon_blue defaults."""
    theme_id = (cfg.OVERLAY or {}).get("theme", DEFAULT_THEME)
    theme = get_theme(theme_id)
    return theme.get(key, THEMES[DEFAULT_THEME][key])

def list_themes() -> list:
    """Return list of (theme_id, theme_dict) tuples in display order."""
    order = [
        "neon_blue", "retro_arcade", "classic_pinball", "stealth",
        "synthwave", "lava", "arctic", "royal_purple",
        "toxic_green", "midnight_gold", "cyberpunk", "ocean",
    ]
    return [(tid, THEMES[tid]) for tid in order if tid in THEMES]
