TABLE_EMOJI_KEYWORDS: dict[str, str] = {
    "mars":        "🛸",  "alien":      "👽",  "space":     "🚀",
    "monster":     "👹",  "dracula":    "🧛",  "vampire":   "🧛",
    "castle":      "🏰",  "medieval":   "⚔️",  "knight":    "🗡️",
    "magic":       "🎩",  "wizard":     "🧙",  "sorcerer":  "🧙",
    "circus":      "🎪",  "carnival":   "🎪",  "funhouse":  "🤡",
    "pirate":      "🏴‍☠️", "treasure":   "💰",  "gold":      "💰",
    "jungle":      "🌴",  "safari":     "🦁",  "gorilla":   "🦍",
    "race":        "🏎️",  "speed":      "💨",  "motor":     "🏍️",
    "fish":        "🐟",  "shark":      "🦈",  "ocean":     "🌊",
    "rock":        "🎸",  "band":       "🎸",  "music":     "🎵",
    "star":        "⭐",  "galaxy":     "🌌",  "twilight":  "🌀",
    "fire":        "🔥",  "phoenix":    "🔥",  "dragon":    "🐉",
    "indiana":     "🤠",  "adventure":  "🗺️",  "tomb":      "⚰️",
    "robot":       "🤖",  "terminator": "🤖",  "machine":   "⚙️",
    "family":      "👨‍👩‍👧‍👦", "addams":    "🫰",  "munster":   "👻",
    "ghost":       "👻",  "scared":     "💀",  "horror":    "🎃",
    "world cup":   "⚽",  "football":   "🏈",  "basket":    "🏀",
    "cactus":      "🌵",  "western":    "🤠",  "canyon":    "🏜️",
    "elvis":       "🕺",  "party":      "🎉",  "wedding":   "💍",
    "police":      "🚔",  "detective":  "🔍",  "spy":       "🕵️",
    "road":        "🛣️",  "truck":      "🚛",  "taxi":      "🚕",
    "junk":        "♻️",  "wreck":      "💥",
    "cat":         "🐱",  "panther":    "🐆",
    "whirlwind":   "🌪️",  "storm":      "⛈️",  "tornado":   "🌪️",
}

MANUFACTURER_EMOJI: dict[str, str] = {
    "Williams":  "🟡",
    "Bally":     "🔴",
    "Stern":     "🟠",
    "Data East": "🔵",
    "Gottlieb":  "🟢",
    "Sega":      "🔷",
    "Capcom":    "🟣",
    "Premier":   "⬜",
    "Midway":    "🟤",
}

DEFAULT_OVERLAY = {
    "scale_pct": 50,
    "background": "auto",
    "portrait_mode": False,
    "portrait_rotate_ccw": False,
    "lines_per_category":12,
    "toggle_input_source": "keyboard",
    "toggle_vk": 120,
    "toggle_joy_button": 2,
    "font_family": "Segoe UI",
    "base_title_size": 17,
    "base_body_size": 12,
    "base_hint_size": 10,
    "use_xy": False,
    "pos_x": 100,
    "pos_y": 100,
    "prefer_ascii_icons": False,
    "auto_show_on_end": True,
    "live_updates": False,
    "ach_toast_custom": False,
    "ach_toast_x_landscape": 100,
    "ach_toast_y_landscape": 100,
    "ach_toast_x_portrait": 100,
    "ach_toast_y_portrait": 100,
    "ach_toast_portrait": False,
    "ach_toast_rotate_ccw": False,
    "ch_timer_custom": False,                
    "ch_timer_saved": False,                 
    "ch_timer_x_landscape": 100,
    "ch_timer_y_landscape": 100,
    "ch_timer_x_portrait": 100,
    "ch_timer_y_portrait": 100,
    "ch_timer_portrait": False,               
    "ch_timer_rotate_ccw": False,  
    "ch_ov_custom": False,
    "ch_ov_saved": False,
    "ch_ov_x_landscape": 100,
    "ch_ov_y_landscape": 100,
    "ch_ov_x_portrait": 100,
    "ch_ov_y_portrait": 100,
    "ch_ov_portrait": False,
    "ch_ov_rotate_ccw": False,
    "overlay_auto_close": False,
    "automatic_creation": True,
    "heat_bar_custom": False,
    "heat_bar_saved": False,
    "heat_bar_x_landscape": 20,
    "heat_bar_y_landscape": 100,
    "heat_bar_x_portrait": 20,
    "heat_bar_y_portrait": 100,
    "heat_bar_portrait": False,
    "heat_bar_rotate_ccw": False,
}
DEFAULT_OVERLAY.update({
    "challenge_hotkey_input_source": "keyboard",
    "challenge_hotkey_vk": 0x7A,   
    "challenge_hotkey_joy_button": 3,
    "challenge_left_input_source": "keyboard",
    "challenge_left_vk": 0x25,
    "challenge_left_joy_button": 4,
    "challenge_right_input_source": "keyboard",
    "challenge_right_vk": 0x27,
    "challenge_right_joy_button": 5,
})
DEFAULT_OVERLAY.setdefault("ch_hotkey_debounce_ms", 120)
DEFAULT_OVERLAY.setdefault("ch_finalize_delay_ms", 2000)
DEFAULT_OVERLAY.setdefault("low_performance_mode", False)
DEFAULT_OVERLAY.setdefault("anim_main_transitions", True)
DEFAULT_OVERLAY.setdefault("anim_main_glow", True)
DEFAULT_OVERLAY.setdefault("anim_main_score_progress", True)
DEFAULT_OVERLAY.setdefault("anim_main_highlights", True)
DEFAULT_OVERLAY.setdefault("anim_toast", True)
DEFAULT_OVERLAY.setdefault("anim_status", True)
DEFAULT_OVERLAY.setdefault("anim_challenge", True)
DEFAULT_OVERLAY.setdefault("status_overlay_enabled", True)
DEFAULT_OVERLAY.setdefault("status_overlay_portrait", False)
DEFAULT_OVERLAY.setdefault("status_overlay_rotate_ccw", False)
DEFAULT_OVERLAY.setdefault("status_overlay_x_portrait", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_y_portrait", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_x_landscape", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_y_landscape", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_saved", False)

CHALLENGES_ENABLED = True

# Windows virtual key codes for flipper buttons used in Heat Challenge
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1

# Heat Challenge rate constants (units per second unless noted)
HEAT_HOLD_RATE = 22.5      # heat gained per second while flipper is held
HEAT_PRESS_BURST = 7.5     # instant heat added on initial flipper press
HEAT_COOLDOWN_RATE = 10.0  # heat lost per second while flippers are released

EXCLUDED_FIELDS = {
    "Last Game Start", "Last Printout", "Last Replay", "Champion Reset", "Clock Last Set", "Coins Cleared",
    "Factory Setting", "Recent Paid Cred", "Recent Serv. Cred", "Burn-in Time", "Totals Cleared", "Audits Cleared",
     "Last Serv. Cred"
}
EXCLUDED_FIELDS_LC = {s.lower() for s in EXCLUDED_FIELDS}

DEFAULT_LOG_SUPPRESS = [
    "[SNAP] pregame player_count detected",
    "[HOOK] Global keyboard hook installed",
    "[HOOK] toggle fired",
    "[HOTKEY] Registered WM_HOTKEY",
    "[CTRL] map miss for candidate",         
    "[CTRL] base-map miss for candidate",    
]

GITHUB_BASE = "https://raw.githubusercontent.com/tomlogic/pinmame-nvram-maps/475fa3619134f5aa732ccd80244e1613e7e6e9a1"
INDEX_URL = f"{GITHUB_BASE}/index.json"
ROMNAMES_URL = f"{GITHUB_BASE}/romnames.json"
VPXTOOL_EXE = "vpxtool.exe"
VPXTOOL_DIRNAME = "tools"
VPXTOOL_URL = "https://github.com/francisdb/vpxtool/releases/download/v0.26.0/vpxtool-Windows-x86_64-v0.26.0.zip"

PREFETCH_MODE = "background"
PREFETCH_LOG_EVERY = 50
ROLLING_HISTORY_PER_ROM = 10
