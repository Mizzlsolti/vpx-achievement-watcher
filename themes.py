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
        # Per-page accent colours that cycle as the user navigates overlay pages.
        # Only neon_blue defines these; other themes use their border colour on all pages.
        "page_accents": [
            "#00E5FF",  # page 0: cyan  (default/highlights)
            "#FF7F00",  # page 1: orange (achievement progress)
            "#00C86E",  # page 2: green  (other views)
            "#B450FF",  # page 3: purple (cloud/VPS)
        ],
    },
    "retro_arcade": {
        "name": "Retro Arcade",
        "icon": "🟢",
        "primary": "#33FF33",
        "accent": "#FFFF00",
        "border": "#33FF33",
        "bg": "#0A0A0A",
        "description": "Green & yellow on black – CRT monitor feel",
    },
    "classic_pinball": {
        "name": "Classic Pinball",
        "icon": "🟡",
        "primary": "#FFD700",
        "accent": "#FF4040",
        "border": "#FFD700",
        "bg": "#1A0A00",
        "description": "Gold & red on warm dark – classic machine glow",
    },
    "stealth": {
        "name": "Stealth",
        "icon": "⚫",
        "primary": "#999999",
        "accent": "#CCCCCC",
        "border": "#666666",
        "bg": "#0D0D0D",
        "description": "Muted grays – minimal and unobtrusive",
    },
    "synthwave": {
        "name": "Synthwave",
        "icon": "💜",
        "primary": "#FF44FF",
        "accent": "#00FFFF",
        "border": "#FF44FF",
        "bg": "#0D001A",
        "description": "Hot pink & cyan – 80s retrowave neon",
    },
    "lava": {
        "name": "Lava",
        "icon": "🔴",
        "primary": "#FF6633",
        "accent": "#FFD700",
        "border": "#FF4500",
        "bg": "#1A0800",
        "description": "Orange & gold on ember – volcanic heat",
    },
    "arctic": {
        "name": "Arctic",
        "icon": "🔵",
        "primary": "#87CEEB",
        "accent": "#E0F0FF",
        "border": "#87CEEB",
        "bg": "#0A1520",
        "description": "Ice blue & frost white – cold and clear",
    },
    "royal_purple": {
        "name": "Royal Purple",
        "icon": "👑",
        "primary": "#BB77DD",
        "accent": "#F1C40F",
        "border": "#9B59B6",
        "bg": "#120A1A",
        "description": "Lavender & gold – regal and elegant",
    },
    "toxic_green": {
        "name": "Toxic Green",
        "icon": "☢️",
        "primary": "#39FF14",
        "accent": "#FF073A",
        "border": "#39FF14",
        "bg": "#0A0F0A",
        "description": "Neon green & red – radioactive glow",
    },
    "cyberpunk": {
        "name": "Cyberpunk",
        "icon": "⚡",
        "primary": "#F6E716",
        "accent": "#FF003C",
        "border": "#F6E716",
        "bg": "#0D0221",
        "description": "Electric yellow & neon pink – high contrast future",
    },
    "ocean": {
        "name": "Ocean",
        "icon": "🌊",
        "primary": "#48CAE4",
        "accent": "#90E0EF",
        "border": "#0077B6",
        "bg": "#03111A",
        "description": "Light blue harmony – deep sea calm",
    },
    "midnight_gold": {
        "name": "Midnight Gold",
        "icon": "✨",
        "primary": "#FFD700",
        "accent": "#FFA500",
        "border": "#DAA520",
        "bg": "#0A0A14",
        "description": "Gold & amber on midnight – luxury feel",
    },
    "cherry_blossom": {
        "name": "Cherry Blossom",
        "icon": "🌸",
        "primary": "#FFB7C5",
        "accent": "#FF69B4",
        "border": "#FF69B4",
        "bg": "#1A0A12",
        "description": "Soft pink & rose – delicate and warm",
    },
    "forest": {
        "name": "Forest",
        "icon": "🌲",
        "primary": "#228B22",
        "accent": "#90EE90",
        "border": "#2E8B57",
        "bg": "#0A120A",
        "description": "Deep green & leaf – natural woodland",
    },
    "sunset": {
        "name": "Sunset",
        "icon": "🌅",
        "primary": "#FF6347",
        "accent": "#FFD700",
        "border": "#FF4500",
        "bg": "#1A0A05",
        "description": "Tomato red & gold – warm evening glow",
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
        "toxic_green", "cyberpunk", "ocean",
        "midnight_gold", "cherry_blossom", "forest", "sunset",
    ]
    return [(tid, THEMES[tid]) for tid in order if tid in THEMES]
