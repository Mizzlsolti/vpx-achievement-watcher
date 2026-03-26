
from __future__ import annotations

import random
import subprocess
import hashlib
import shutil
import os, sys, time, json, re, glob, threading, uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict, Counter

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    import requests
except Exception:
    requests = None

try:
    import win32gui
except Exception:
    win32gui = None

import ctypes
from ctypes import wintypes
import ssl
from urllib.request import Request, urlopen

def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.isdir(base):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    return os.path.join(APP_DIR, rel)

WATCHER_VERSION = "2.6"


def _strip_version_from_name(name: str) -> str:
    """Remove all trailing parenthesised/bracketed suffixes from table names.

    Examples:
        "Medieval Madness (Williams)"        -> "Medieval Madness"
        "AC/DC (Premium) (V1.13b)"           -> "AC/DC"
        "Theatre of Magic [VPX]"             -> "Theatre of Magic"
        "Attack from Mars (Remake) (2.0)"    -> "Attack from Mars"
    """
    result = name
    while True:
        # Use separate patterns for each delimiter type to avoid matching
        # unbalanced pairs such as "(Name]".
        stripped = re.sub(r"\s*\([^\)]*\)\s*$", "", result, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"\s*\[[^\]]*\]\s*$", "", stripped, flags=re.IGNORECASE).strip()
        if stripped == result:
            break
        result = stripped
    return result


# Alias used by callers that want to strip all parenthesised/bracketed suffixes.
_clean_table_name = _strip_version_from_name


def _fetch_json_url(url: str, timeout: int = 25) -> dict:
    ua = "AchievementWatcher/1.0 (+https://github.com/Mizzlsolti)"
    if requests:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": ua})
        r.raise_for_status()
        return r.json()
    req = Request(url, headers={"User-Agent": ua})
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        raw = resp.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return json.loads(raw)

def _fetch_bytes_url(url: str, timeout: int = 25) -> bytes:
    ua = "AchievementWatcher/1.0 (+https://github.com/Mizzlsolti)"
    if requests:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": ua})
        r.raise_for_status()
        return r.content
    req = Request(url, headers={"User-Agent": ua})
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        return resp.read()

from input_hook import (
    JOYINFOEX, JOY_RETURNALL, JOYERR_NOERROR, _joyGetPosEx,
    RIDEV_INPUTSINK, WM_KEYDOWN, WM_SYSKEYDOWN, WM_HOTKEY, WH_KEYBOARD_LL,
    KBDLLHOOKSTRUCT, GlobalKeyHook,
    RAWINPUTDEVICE, _RegisterRawInputDevices,
    _MapVirtualKeyW, _GetKeyNameTextW,
    vk_to_name, vk_to_name_en, vsc_to_vk,
    get_vpx_ini_path_for_current_user, parse_vpx_flipper_bindings,
    register_raw_input_for_window,
)

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

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
DEFAULT_OVERLAY.setdefault("overlay_page2_enabled", True)
DEFAULT_OVERLAY.setdefault("overlay_page3_enabled", True)
DEFAULT_OVERLAY.setdefault("overlay_page4_enabled", True)
DEFAULT_OVERLAY.setdefault("overlay_page5_enabled", True)
DEFAULT_OVERLAY.setdefault("status_overlay_enabled", True)
DEFAULT_OVERLAY.setdefault("status_overlay_rotate_ccw", False)
DEFAULT_OVERLAY.setdefault("status_overlay_x_portrait", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_y_portrait", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_x_landscape", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_y_landscape", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_saved", False)
DEFAULT_OVERLAY.setdefault("sound_enabled", False)
DEFAULT_OVERLAY.setdefault("sound_volume", 20)
DEFAULT_OVERLAY.setdefault("sound_pack", "arcade")
DEFAULT_OVERLAY.setdefault("sound_events", {})
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

def is_excluded_field(label: str) -> bool:
    ll = str(label or "").strip().lower()
    return (
        ll in EXCLUDED_FIELDS_LC or
        "reset" in ll or
        "cleared" in ll or
        "factory" in ll or
        "timestamp" in ll or
        "game time" in ll or
        ("last" in ll and ("printout" in ll or "replay" in ll)) or
        ("last" in ll and "game" in ll)
    )

DEFAULT_LOG_SUPPRESS = [
    "[HOOK] Global keyboard hook installed",
    "[HOOK] toggle fired",
    "[HOTKEY] Registered WM_HOTKEY",
    "[CTRL] map miss for candidate",         
    "[CTRL] base-map miss for candidate",    
]
 
@dataclass
class AppConfig:
    BASE: str = r"C:\vPinball\VPX Achievement Watcher"
    NVRAM_DIR: str = r"C:\vPinball\VisualPinball\VPinMAME\nvram"
    TABLES_DIR: str = r"C:\vPinball\VisualPinball\Tables"
    OVERLAY: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_OVERLAY))
    FIRST_RUN: bool = True
    TUTORIAL_COMPLETED: bool = False
    LOG_CTRL: bool = False
    LOG_SUPPRESS: List[str] = field(default_factory=lambda: list(DEFAULT_LOG_SUPPRESS))
    CLOUD_ENABLED: bool = False
    CLOUD_BACKUP_ENABLED: bool = False
    CLOUD_URL: str = "https://vpx-achievements-watcher-lb-default-rtdb.europe-west1.firebasedatabase.app/"

    @staticmethod
    def load(path: str = CONFIG_FILE) -> "AppConfig":
        if not os.path.exists(path):
            return AppConfig(FIRST_RUN=True)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            ov = dict(DEFAULT_OVERLAY)
            loaded_ov = data.get("OVERLAY", {})
            
            allowed_keys = [
                "scale_pct", "background", "portrait_mode", "portrait_rotate_ccw", 
                "lines_per_category", "font_family", "overlay_auto_close",
                "pos_x", "pos_y", "use_xy", "overlay_pos_saved",
                "base_body_size", "base_title_size", "base_hint_size",
                
                "toggle_input_source", "toggle_vk", "toggle_joy_button",
                "challenge_hotkey_input_source", "challenge_hotkey_vk", "challenge_hotkey_joy_button",
                "challenge_left_input_source", "challenge_left_vk", "challenge_left_joy_button",
                "challenge_right_input_source", "challenge_right_vk", "challenge_right_joy_button",
                
                "ach_toast_custom", "ach_toast_saved", "ach_toast_x_landscape", "ach_toast_y_landscape", 
                "ach_toast_x_portrait", "ach_toast_y_portrait", "ach_toast_portrait", "ach_toast_rotate_ccw",
                
                "ch_timer_custom", "ch_timer_saved", "ch_timer_x_landscape", "ch_timer_y_landscape", 
                "ch_timer_x_portrait", "ch_timer_y_portrait", "ch_timer_portrait", "ch_timer_rotate_ccw",
                
                "ch_ov_custom", "ch_ov_saved", "ch_ov_x_landscape", "ch_ov_y_landscape", 
                "ch_ov_x_portrait", "ch_ov_y_portrait", "ch_ov_portrait", "ch_ov_rotate_ccw",
                
                "flip_counter_custom", "flip_counter_saved", "flip_counter_x_landscape", "flip_counter_y_landscape", 
                "flip_counter_x_portrait", "flip_counter_y_portrait", "flip_counter_portrait", "flip_counter_rotate_ccw",
                
                "heat_bar_custom", "heat_bar_saved", "heat_bar_x_landscape", "heat_bar_y_landscape",
                "heat_bar_x_portrait", "heat_bar_y_portrait", "heat_bar_portrait", "heat_bar_rotate_ccw",
                
                "notifications_portrait", "notifications_rotate_ccw", "notifications_saved",
                "notifications_x_landscape", "notifications_y_landscape", "notifications_x_portrait", "notifications_y_portrait",
                
                "status_overlay_enabled", "status_overlay_portrait", "status_overlay_rotate_ccw",
                "status_overlay_saved", "status_overlay_x_landscape", "status_overlay_y_landscape",
                "status_overlay_x_portrait", "status_overlay_y_portrait",
                
                "player_name", "player_id", "flip_counter_goal_total", 
                "challenges_voice_volume", "challenges_voice_mute",
                "low_performance_mode",
                "anim_main_transitions", "anim_main_glow", "anim_main_score_progress",
                "anim_main_highlights", "anim_toast", "anim_status", "anim_challenge",
                "overlay_page2_enabled", "overlay_page3_enabled",
                "overlay_page4_enabled", "overlay_page5_enabled",
                "sound_enabled", "sound_volume", "sound_pack", "sound_events",
            ]
            
            for k in list(loaded_ov.keys()):
                if k not in allowed_keys:
                    del loaded_ov[k]
                    
            ov.update(loaded_ov)

            cloud_enabled = bool(data.get("CLOUD_ENABLED", False))
            cloud_backup_enabled = bool(data.get("CLOUD_BACKUP_ENABLED", False))
            if not cloud_enabled:
                cloud_backup_enabled = False

            return AppConfig(
                BASE=data.get("BASE", AppConfig.BASE),
                NVRAM_DIR=data.get("NVRAM_DIR", AppConfig.NVRAM_DIR),
                TABLES_DIR=data.get("TABLES_DIR", AppConfig.TABLES_DIR),
                OVERLAY=ov,
                FIRST_RUN=bool(data.get("FIRST_RUN", False)),
                TUTORIAL_COMPLETED=bool(data.get("TUTORIAL_COMPLETED", False)),
                CLOUD_ENABLED=cloud_enabled,
                CLOUD_BACKUP_ENABLED=cloud_backup_enabled,
            )
        except Exception as e:
            print(f"[LOAD ERROR] {e}")
            return AppConfig(FIRST_RUN=True)

    def save(self, path: str = CONFIG_FILE) -> None:
        try:
            clean_overlay = {}
            ov = getattr(self, "OVERLAY", {})
            allowed_keys = [
                "scale_pct", "background", "portrait_mode", "portrait_rotate_ccw", 
                "lines_per_category", "font_family", "overlay_auto_close",
                "pos_x", "pos_y", "use_xy", "overlay_pos_saved",
                "base_body_size", "base_title_size", "base_hint_size",
                
                "toggle_input_source", "toggle_vk", "toggle_joy_button",
                "challenge_hotkey_input_source", "challenge_hotkey_vk", "challenge_hotkey_joy_button",
                "challenge_left_input_source", "challenge_left_vk", "challenge_left_joy_button",
                "challenge_right_input_source", "challenge_right_vk", "challenge_right_joy_button",
                
                "ach_toast_custom", "ach_toast_saved", "ach_toast_x_landscape", "ach_toast_y_landscape", 
                "ach_toast_x_portrait", "ach_toast_y_portrait", "ach_toast_portrait", "ach_toast_rotate_ccw",
                
                "ch_timer_custom", "ch_timer_saved", "ch_timer_x_landscape", "ch_timer_y_landscape", 
                "ch_timer_x_portrait", "ch_timer_y_portrait", "ch_timer_portrait", "ch_timer_rotate_ccw",
                
                "ch_ov_custom", "ch_ov_saved", "ch_ov_x_landscape", "ch_ov_y_landscape", 
                "ch_ov_x_portrait", "ch_ov_y_portrait", "ch_ov_portrait", "ch_ov_rotate_ccw",
                
                "flip_counter_custom", "flip_counter_saved", "flip_counter_x_landscape", "flip_counter_y_landscape", 
                "flip_counter_x_portrait", "flip_counter_y_portrait", "flip_counter_portrait", "flip_counter_rotate_ccw",
                
                "heat_bar_custom", "heat_bar_saved", "heat_bar_x_landscape", "heat_bar_y_landscape",
                "heat_bar_x_portrait", "heat_bar_y_portrait", "heat_bar_portrait", "heat_bar_rotate_ccw",
                
                "notifications_portrait", "notifications_rotate_ccw", "notifications_saved",
                "notifications_x_landscape", "notifications_y_landscape", "notifications_x_portrait", "notifications_y_portrait",
                
                "status_overlay_enabled", "status_overlay_portrait", "status_overlay_rotate_ccw",
                "status_overlay_saved", "status_overlay_x_landscape", "status_overlay_y_landscape",
                "status_overlay_x_portrait", "status_overlay_y_portrait",
                
                "player_name", "player_id", "flip_counter_goal_total", 
                "challenges_voice_volume", "challenges_voice_mute",
                "low_performance_mode",
                "anim_main_transitions", "anim_main_glow", "anim_main_score_progress",
                "anim_main_highlights", "anim_toast", "anim_status", "anim_challenge",
                "overlay_page2_enabled", "overlay_page3_enabled",
                "overlay_page4_enabled", "overlay_page5_enabled",
                "sound_enabled", "sound_volume", "sound_pack", "sound_events",
            ]
            
            for k in allowed_keys:
                if k in ov:
                    clean_overlay[k] = ov[k]

            cloud_enabled_val = getattr(self, "CLOUD_ENABLED", False)
            cloud_backup_val = getattr(self, "CLOUD_BACKUP_ENABLED", False)
            if not cloud_enabled_val:
                cloud_backup_val = False

            to_dump = {
                "BASE": getattr(self, "BASE", r"C:\vPinball\VPX Achievement Watcher"),
                "NVRAM_DIR": getattr(self, "NVRAM_DIR", r"C:\vPinball\VisualPinball\VPinMAME\nvram"),
                "TABLES_DIR": getattr(self, "TABLES_DIR", r"C:\vPinball\VisualPinball\Tables"),
                "CLOUD_ENABLED": cloud_enabled_val,
                "CLOUD_BACKUP_ENABLED": cloud_backup_val,
                "FIRST_RUN": getattr(self, "FIRST_RUN", False),
                "TUTORIAL_COMPLETED": getattr(self, "TUTORIAL_COMPLETED", False),
                "OVERLAY": clean_overlay
            }
            
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
                
            with open(path, "w", encoding="utf-8") as f:
                json.dump(to_dump, f, indent=2)
        except Exception as e:
            print(f"CRITICAL ERROR: Could not save config.json -> {e}")

def p_maps(cfg):         return os.path.join(cfg.BASE, "tools", "NVRAM_Maps")
def p_local_maps(cfg):   return os.path.join(p_maps(cfg), "maps")
def p_session(cfg):      return os.path.join(cfg.BASE, "session_stats")
def p_highlights(cfg):   return os.path.join(p_session(cfg), "Highlights")
def p_achievements(cfg): return os.path.join(cfg.BASE, "Achievements")
def p_rom_spec(cfg):     return os.path.join(p_achievements(cfg), "rom_specific_achievements")
def f_global_ach(cfg):   return os.path.join(p_achievements(cfg), "global_achievements.json")
def f_achievements_state(cfg: "AppConfig") -> str:
    return os.path.join(p_achievements(cfg), "achievements_state.json")
def f_log(cfg):          return os.path.join(cfg.BASE, "watcher.log")
def f_index(cfg):        return os.path.join(p_maps(cfg), "index.json")
def f_romnames(cfg):     return os.path.join(p_maps(cfg), "romnames.json")
def p_vps(cfg):          return os.path.join(cfg.BASE, "tools", "vps")
def p_vps_img(cfg):      return os.path.join(p_vps(cfg), "img")
def f_vps_mapping(cfg):  return os.path.join(p_vps(cfg), "vps_id_mapping.json")
def f_vpsdb_cache(cfg):  return os.path.join(p_vps(cfg), "vpsdb.json")
def f_legacy_cleanup_marker(cfg: "AppConfig") -> str:
    """Marker file indicating that the one-time legacy progress cleanup has already run."""
    return os.path.join(p_achievements(cfg), ".legacy_progress_cleaned")
def f_progress_upload_log(cfg: "AppConfig") -> str:
    """Tracks which (rom, vps_id) combos have already had progress uploaded."""
    return os.path.join(p_achievements(cfg), "progress_upload_log.json")


def _load_progress_upload_log(cfg) -> dict:
    """Load the progress upload log dict {rom: vps_id}."""
    path = f_progress_upload_log(cfg)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_progress_upload_log(cfg, log_data: dict):
    """Save the progress upload log dict {rom: vps_id}."""
    path = f_progress_upload_log(cfg)
    ensure_dir(os.path.dirname(path))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
    except Exception:
        pass


def _migrate_runtime_dirs(cfg):
    """One-time migration from old flat structure to new grouped structure."""

    # NVRAM_Maps: root → tools/NVRAM_Maps
    old_maps = os.path.join(cfg.BASE, "NVRAM_Maps")
    new_maps = p_maps(cfg)
    if os.path.isdir(old_maps) and not os.path.isdir(new_maps):
        ensure_dir(os.path.dirname(new_maps))
        shutil.move(old_maps, new_maps)

    # achievements_state.json: root → Achievements/
    old_state = os.path.join(cfg.BASE, "achievements_state.json")
    new_state = f_achievements_state(cfg)
    if os.path.isfile(old_state) and not os.path.isfile(new_state):
        ensure_dir(os.path.dirname(new_state))
        shutil.move(old_state, new_state)

    # global_achievements.json: root → Achievements/
    old_global = os.path.join(cfg.BASE, "global_achievements.json")
    new_global = f_global_ach(cfg)
    if os.path.isfile(old_global) and not os.path.isfile(new_global):
        ensure_dir(os.path.dirname(new_global))
        shutil.move(old_global, new_global)

    # rom_specific_achievements: root → Achievements/
    old_rom_spec = os.path.join(cfg.BASE, "rom_specific_achievements")
    new_rom_spec = p_rom_spec(cfg)
    if os.path.isdir(old_rom_spec) and not os.path.isdir(new_rom_spec):
        ensure_dir(os.path.dirname(new_rom_spec))
        shutil.move(old_rom_spec, new_rom_spec)

    # challenges: root → session_stats/challenges
    old_challenges = os.path.join(cfg.BASE, "challenges")
    new_challenges = os.path.join(p_session(cfg), "challenges")
    if os.path.isdir(old_challenges) and not os.path.isdir(new_challenges):
        ensure_dir(os.path.dirname(new_challenges))
        shutil.move(old_challenges, new_challenges)

    # vps_id_mapping.json: root → tools/vps/
    old_vps_mapping = os.path.join(cfg.BASE, "vps_id_mapping.json")
    new_vps_mapping = f_vps_mapping(cfg)
    if os.path.isfile(old_vps_mapping) and not os.path.isfile(new_vps_mapping):
        ensure_dir(os.path.dirname(new_vps_mapping))
        shutil.move(old_vps_mapping, new_vps_mapping)

    # vpsdb.json: tools/ → tools/vps/
    old_vpsdb = os.path.join(cfg.BASE, "tools", "vpsdb.json")
    new_vpsdb = f_vpsdb_cache(cfg)
    if os.path.isfile(old_vpsdb) and not os.path.isfile(new_vpsdb):
        ensure_dir(os.path.dirname(new_vpsdb))
        shutil.move(old_vpsdb, new_vpsdb)

    # Clean up old .txt session dumps
    if os.path.isdir(p_session(cfg)):
        for fn in os.listdir(p_session(cfg)):
            if fn.lower().endswith(".txt"):
                try:
                    os.remove(os.path.join(p_session(cfg), fn))
                except Exception:
                    pass

    # Clean up old .session.json history files in Highlights
    if os.path.isdir(p_highlights(cfg)):
        for fn in os.listdir(p_highlights(cfg)):
            if fn.lower().endswith(".session.json"):
                try:
                    os.remove(os.path.join(p_highlights(cfg), fn))
                except Exception:
                    pass

    # Migrate notifications: merge old files into new unified store
    try:
        import notifications as _notif
        _notif.migrate_notifications(cfg)
    except Exception:
        pass

GITHUB_BASE = "https://raw.githubusercontent.com/tomlogic/pinmame-nvram-maps/475fa3619134f5aa732ccd80244e1613e7e6e9a1"
INDEX_URL = f"{GITHUB_BASE}/index.json"
ROMNAMES_URL = f"{GITHUB_BASE}/romnames.json"
VPXTOOL_EXE = "vpxtool.exe"
VPXTOOL_DIRNAME = "tools"
VPXTOOL_PATH = os.path.join(APP_DIR, VPXTOOL_DIRNAME, VPXTOOL_EXE)
VPXTOOL_URL = "https://github.com/francisdb/vpxtool/releases/download/v0.26.0/vpxtool-Windows-x86_64-v0.26.0.zip"


def ensure_vpxtool(cfg: AppConfig) -> str | None:
    import zipfile
    import io
    try:
        if os.path.isfile(VPXTOOL_PATH):
            return VPXTOOL_PATH

        log(cfg, f"[VPXTOOL] Download from {VPXTOOL_URL}...")
        data = _fetch_bytes_url(VPXTOOL_URL, timeout=30)
        ensure_dir(os.path.dirname(VPXTOOL_PATH))
        
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            with open(VPXTOOL_PATH, "wb") as f:
                f.write(z.read("vpxtool.exe"))

        try:
            os.chmod(VPXTOOL_PATH, 0o755)
        except Exception:
            pass

        log(cfg, f"[VPXTOOL] Successfully downloaded and unzipped -> {VPXTOOL_PATH}")
        return VPXTOOL_PATH
    except Exception as e:
        log(cfg, f"[VPXTOOL] download failed: {e}", "ERROR")
        return None

def run_vpxtool_get_rom(cfg: AppConfig, vpx_path: str, suppress_warn: bool = False) -> str | None:

    if not vpx_path or not os.path.isfile(vpx_path):
        return None

    exe = ensure_vpxtool(cfg)
    if not exe:
        return None
    try:
        key = os.path.abspath(vpx_path).lower()
    except Exception:
        key = str(vpx_path)
    if not hasattr(run_vpxtool_get_rom, "_warned_keys"):
        run_vpxtool_get_rom._warned_keys = set()
    warned = run_vpxtool_get_rom._warned_keys 

    cmd = [exe, "romname", vpx_path]
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=0x08000000
        )
        out = ((cp.stdout or "") + "\n" + (cp.stderr or "")).strip()

        if cp.returncode != 0:
            if key not in warned:
                if not suppress_warn:
                    log(cfg, f"[VPXTOOL] romname failed rc={cp.returncode}: {out}", "WARN")
                warned.add(key)
            return None

        lines = (cp.stdout or "").strip().splitlines()
        if lines:
            rom = lines[-1].strip().strip('"').strip("'")
            if re.fullmatch(r"[A-Za-z0-9_]+", rom or ""):
                if key in warned:
                    warned.discard(key)
                return rom

        m = re.search(r"\b([A-Za-z0-9_]{2,})\b", out)
        if m:
            if key in warned:
                warned.discard(key)
            return m.group(1)

        if key not in warned:
            if not suppress_warn:
                log(cfg, f"[VPXTOOL] romname returned no parsable output: {out}", "WARN")
            warned.add(key)
        return None

    except Exception as e:
        if key not in warned:
            if not suppress_warn:
                log(cfg, f"[VPXTOOL] romname exception: {e}", "WARN")
            warned.add(key)
        return None


def run_vpxtool_get_script_authors(cfg: "AppConfig", vpx_path: str) -> list:
    """
    Runs: vpxtool script show "<vpx_path>"
    Parses the VBS script output for author names from comment lines.
    Returns a list of author name strings (possibly empty).
    No logging — silent failure is OK.
    """
    if not vpx_path or not os.path.isfile(vpx_path):
        return []

    exe = ensure_vpxtool(cfg)
    if not exe:
        return []

    cmd = [exe, "script", "show", vpx_path]
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=0x08000000,
            encoding="utf-8",
            errors="replace",
        )
        script = cp.stdout or ""
        return _parse_authors_from_script(script)
    except Exception:
        return []


def run_vpxtool_info_show(cfg: "AppConfig", vpx_path: str) -> dict:
    """
    Runs: vpxtool info show "<vpx_path>"
    Parses the human-readable key: value output into a dict.
    Returns a dict with keys like 'table_name', 'version', 'author', 'release_date',
    'description', 'blurb', 'rules', 'save_revision', 'save_date', 'vpx_version'.
    Returns {} on any failure (silent).
    """
    if not vpx_path or not os.path.isfile(vpx_path):
        return {}

    exe = ensure_vpxtool(cfg)
    if not exe:
        return {}

    cmd = [exe, "info", "show", vpx_path]
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=0x08000000,
            encoding="utf-8",
            errors="replace",
        )
        output = cp.stdout or ""
        result = {}
        for line in output.splitlines():
            m = re.match(r"^\s*(.+?):\s+(.*)$", line)
            if m:
                raw_key = m.group(1).strip()
                value = m.group(2).strip()
                key = re.sub(r"\s+", "_", raw_key).lower()
                result[key] = value
        return result
    except Exception:
        return {}


def _parse_authors_from_script(script: str) -> list:
    """
    Parse author names from a VBS script.
    Looks for comment lines containing author indicators.
    Returns a deduplicated list of primary author name tokens.

    Primary author patterns searched (case-insensitive):
      ' Table by JPSalas
      ' Author: nFozzy, Fleep
      ' Authors: Brad1X, Sixtoe
      ' Created by Tom Tower
      ' VPX by Dozer
      ' VPX recreation by g5k
      ' Original by George H
      ' Adapted by Flukemaster

    Lines after a '  Thanks to:' / '  Credits:' marker are treated as
    contributor credits and excluded from the primary author list.
    """
    authors = []
    seen = set()
    in_credits_section = False

    # Detect entry into a thanks/credits block
    _credits_re = re.compile(r"^\s*'[^']*(?:thanks?\s+to|credits?)\s*:", re.IGNORECASE)

    # Match comment lines with primary author-like patterns.
    # vpx(?:\s+\w+)*\s+by handles "VPX by", "VPX recreation by", "VPX conversion by", etc.
    _primary_re = re.compile(
        r"^\s*'[^']*(?:author(?:s)?|created\s+by|table\s+by|vpx(?:\s+\w+)*\s+by"
        r"|original\s+by|adapted\s+by|remake\s+by|mod\s+by|script\s+by"
        r"|recreation\s+by|conversion\s+by|made\s+by)\s*:?\s*(.+)",
        re.IGNORECASE,
    )

    for line in script.splitlines():
        # Entering a thanks/credits section — stop collecting primary authors
        if _credits_re.match(line):
            in_credits_section = True
            continue
        if in_credits_section:
            continue

        m = _primary_re.match(line)
        if m:
            raw = m.group(1).strip().strip("'").strip()
            # Split on common separators: comma, ampersand, " and ", " & "
            tokens = re.split(r"\s*[,&]\s*|\s+and\s+", raw, flags=re.IGNORECASE)
            for tok in tokens:
                tok = tok.strip().strip("'\"").strip()
                # Remove trailing version/year info like "(v1.0)" or "2024"
                tok = re.sub(r"\s*[\(\[].*", "", tok).strip()
                if tok and len(tok) >= 2:
                    key = tok.lower()
                    if key not in seen:
                        seen.add(key)
                        authors.append(tok)
    return authors


PREFETCH_MODE = "background"
PREFETCH_LOG_EVERY = 50
ROLLING_HISTORY_PER_ROM = 10

def ensure_dir(path): os.makedirs(path, exist_ok=True)
def _ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _set_folder_hidden(path: str):
    """Set Windows FILE_ATTRIBUTE_HIDDEN on *path*. No-op on non-Windows."""
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x02
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass

DEFAULT_LOG_SUPPRESS = [
    "[SNAP] pregame player_count detected",
    "[HOOK] Global keyboard hook installed",
    "[HOOK] toggle fired",
    "[HOTKEY] Registered WM_HOTKEY",
    "[CTRL] map miss for candidate",
    "[CTRL] base-map miss for candidate",
]
quiet_prefixes: tuple[str, ...] = ()

def log(cfg: AppConfig, msg: str, level: str = "INFO"):
    try:
        suppress_list = (getattr(cfg, "LOG_SUPPRESS", None) or DEFAULT_LOG_SUPPRESS) if cfg else DEFAULT_LOG_SUPPRESS
        for pat in suppress_list:
            if pat and pat in str(msg):
                return
    except Exception:
        pass
    line = f"[{_ts()}] [{level}] {msg}"
    suppress_console = any(str(msg).startswith(p) for p in quiet_prefixes) if quiet_prefixes else False
    try:
        ensure_dir(os.path.dirname(f_log(cfg)))
        with open(f_log(cfg), "a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except Exception:
        pass
    if not suppress_console:
        print(line)

def _raw_load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _raw_save_json(path, obj):
    tmp = None
    try:
        ensure_dir(os.path.dirname(path))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.flush()
        try:
            os.replace(tmp, path)
        except Exception:
            os.rename(tmp, path)
        return True
    except Exception:
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False

# ==========================================
# ANTI-CHEAT SECURITY
# ==========================================
LEGACY_SALT = "VPX_S3cr3t_H4sh_9921!"
BASE_SALT = "VpX_W@tcher_2024!"

def _generate_legacy_signature(data: dict) -> str:
    d = dict(data)
    d.pop("_signature", None)
    s = json.dumps(d, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256((s + LEGACY_SALT).encode('utf-8')).hexdigest()

def _generate_signature(data: dict) -> str:
    d = dict(data)
    d.pop("_signature", None)
    
    score_val = str(d.get("score", "0"))
    duration_val = str(d.get("duration", "0"))
    session_val = str(d.get("session_id", "none"))
    
    dynamic_salt = f"{score_val}_{duration_val}_{session_val}_{BASE_SALT}"
    s = json.dumps(d, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256((s + dynamic_salt).encode('utf-8')).hexdigest()

def _is_secure_path(path: str) -> bool:
    """Determines whether a file should be protected by anti-tamper signature.

    Uses a whitelist approach: only gameplay-relevant local state files that
    can directly affect achievements, scores, or progress are protected.
    Non-critical files (config, caches, tool data, reference/definition files)
    are intentionally left unsigned.

    Protected categories:
    - Achievement state (achievements_state.json)
    - Challenge result history (session_stats/challenges/history/*.json)
    - Session summary data (session_stats/Highlights/*.summary.json)
    - Active player session state (session_stats/Highlights/activePlayers/*.json)
    """
    if not path:
        return False
    p = path.lower().replace("\\", "/")

    if not p.endswith(".json"):
        return False

    # Achievement state – the main persisted achievement/progress store
    if p.endswith("achievements_state.json"):
        return True

    # Challenge result history – local score/result records per ROM
    if "/session_stats/challenges/history/" in p:
        return True

    # Session summary files – per-session result snapshots used for display and uploads
    if "/session_stats/highlights/" in p and p.endswith(".summary.json"):
        return True

    # Active player session state – in-progress session data
    if "/session_stats/highlights/activeplayers/" in p:
        return True

    return False

def load_json(path, default=None):
    data = _raw_load_json(path, None)
    if data is None:
        return default
        
    if _is_secure_path(path) and isinstance(data, dict):
        sig = data.pop("_signature", None)
        if not sig:
            # Unsigned legacy file (e.g. from v2.5) – do not block; migrate to v2.6 protection now.
            print(f"[SECURITY] Unsigned legacy file detected: {path}. Upgrading to v2.6 protection now.")
            save_json(path, data)
            return data
            
        expected_new = _generate_signature(data)
        expected_legacy = _generate_legacy_signature(data)
        
        if sig == expected_new:
            # File is already on the new security standard
            data["_signature"] = sig
        elif sig == expected_legacy:
            # File is using the old security standard - allow it to load
            print(f"[SECURITY] Legacy save file detected: {path}. Access granted. Upgrading immediately.")
            data["_signature"] = sig
            save_json(path, data)
        else:
            print(f"\n[SECURITY] TAMPERING DETECTED IN: {path}")
            print("[SECURITY] The file has been blocked and will not be loaded!\n")
            return default
            
    return data

def save_json(path, obj):
    if _is_secure_path(path) and isinstance(obj, dict):
        try:
            obj["_signature"] = _generate_signature(obj)
        except Exception:
            pass
    return _raw_save_json(path, obj)

secure_save_json = save_json
secure_load_json = load_json

def write_text(path, text):
    tmp = None
    try:
        ensure_dir(os.path.dirname(path))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass
        try:
            os.replace(tmp, path)
        except Exception:
            os.rename(tmp, path)
        return True
    except Exception:
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False

def _is_weird_value(x: int) -> bool:
    try:
        return abs(int(x)) >= 400_000_000
    except Exception:
        return False

def apply_tooltips(owner, tips: dict):
    for name, text in (tips or {}).items():
        try:
            w = getattr(owner, name, None)
            if w:
                w.setToolTip(text)
        except Exception:
            pass

def sanitize_filename(s):
    s = re.sub(r"[^\w\-. ]+", "_", str(s))
    return s.strip().replace(" ", "_")

LEVEL_TABLE = [
    (0,    1,  "🪙 Rookie"),
    (10,   2,  "🥉 Apprentice"),
    (25,   3,  "🥈 Veteran"),
    (50,   4,  "🥇 Expert"),
    (100,  5,  "🏆 Master"),
    (200,  6,  "💎 Grand Master"),
    (400,  7,  "👑 Pinball Legend"),
    (750,  8,  "🔥 Pinball God"),
    (1200, 9,  "⚡ Multiball King"),
    (2000, 10, "🌟 VPX Elite"),
]

PRESTIGE_THRESHOLD = 2000   # Achievements per prestige round
MAX_PRESTIGE = 5            # Maximum prestige stars

# ─── Achievement Rarity ───────────────────────────────────────────────
RARITY_TIERS = [
    (50.0, "Common",    "#FFFFFF"),
    (25.0, "Uncommon",  "#4CAF50"),
    (10.0, "Rare",      "#2196F3"),
    (5.0,  "Epic",      "#9C27B0"),
    (0.0,  "Legendary", "#FF9800"),
]

def compute_rarity(unlocked_by: int, total_players: int) -> dict:
    """Compute rarity tier for an achievement based on how many players unlocked it."""
    if total_players <= 0:
        return {"tier": "Unknown", "color": "#888888", "pct": 0.0}
    pct = (unlocked_by / total_players) * 100
    for threshold, name, color in RARITY_TIERS:
        if pct >= threshold:
            return {"tier": name, "color": color, "pct": round(pct, 1)}
    return {"tier": "Legendary", "color": "#FF9800", "pct": round(pct, 1)}

def compute_player_level(state: dict) -> dict:
    """
    Compute the player level from the achievements state.
    Counts all unique unlocked achievement titles across global + all session ROMs (deduped).
    Returns dict with keys: level (int), name (str), icon (str), label (str), total (int),
    next_at (int), progress_pct (float), prev_at (int), max_level (bool),
    effective (int), prestige (int), prestige_display (str), fully_maxed (bool)
    """
    seen = set()
    # global
    for entries in (state.get("global") or {}).values():
        for e in (entries or []):
            t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
            if t:
                seen.add(t)
    # session (all ROMs)
    for entries in (state.get("session") or {}).values():
        for e in (entries or []):
            t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
            if t:
                seen.add(t)
    total = len(seen)

    # Prestige calculation
    prestige = min(total // PRESTIGE_THRESHOLD, MAX_PRESTIGE)
    prestige_display = "★" * prestige + "☆" * (MAX_PRESTIGE - prestige)
    if prestige < MAX_PRESTIGE:
        effective = total - (prestige * PRESTIGE_THRESHOLD)
    else:
        effective = max(0, total - prestige * PRESTIGE_THRESHOLD)

    current_level = 1
    current_name = LEVEL_TABLE[0][2]
    prev_at = 0
    next_at = LEVEL_TABLE[1][0] if len(LEVEL_TABLE) > 1 else effective + 1

    for threshold, lvl, name in LEVEL_TABLE:
        if effective >= threshold:
            current_level = lvl
            current_name = name
            prev_at = threshold
        else:
            next_at = threshold
            break
    else:
        next_at = prev_at  # max level reached

    icon = current_name.split(" ")[0]  # the emoji
    label = " ".join(current_name.split(" ")[1:])  # the name without emoji

    if next_at > prev_at:
        progress_pct = round((effective - prev_at) / (next_at - prev_at) * 100, 1)
    else:
        progress_pct = 100.0  # max level

    max_level = current_level == LEVEL_TABLE[-1][1]
    fully_maxed = prestige >= MAX_PRESTIGE and max_level

    return {
        "level": current_level,
        "name": current_name,
        "icon": icon,
        "label": label,
        "total": total,
        "next_at": next_at,
        "prev_at": prev_at,
        "progress_pct": progress_pct,
        "max_level": max_level,
        "effective": effective,
        "prestige": prestige,
        "prestige_display": prestige_display,
        "fully_maxed": fully_maxed,
    }


# ──────────────────────────────────────────────────────────────────────────────
# BADGES
# ──────────────────────────────────────────────────────────────────────────────

BADGE_DEFINITIONS = [
    # (id, icon, name, description)
    # Milestones
    ("first_steps",       "🐣", "First Steps",        "Unlock your very first achievement"),
    ("getting_started",   "🎯", "Getting Started",     "Unlock 5 unique achievements"),
    ("deca",              "🔟", "Deca",                "Unlock 10 unique achievements"),
    ("half_century",      "5️⃣",  "Half Century",        "Unlock 50 unique achievements"),
    ("century",           "💯", "Century",             "Unlock 100 unique achievements"),
    ("hoarder",           "🏗️", "Hoarder",             "Unlock 500 unique achievements"),
    ("thousandaire",      "🏛️", "Thousandaire",        "Unlock 1000 unique achievements"),
    # Prestige
    ("first_star",        "⭐", "First Star",          "Reach Prestige 1"),
    ("two_stars",         "⭐", "Rising Star",         "Reach Prestige 2"),
    ("three_stars",       "⭐", "Superstar",           "Reach Prestige 3"),
    ("four_stars",        "🌟", "Elite Star",          "Reach Prestige 4"),
    ("five_stars",        "👑", "Maximum Prestige",    "Reach Prestige 5 — Fully Maxed"),
    # Challenges
    ("challenger",        "⚔️", "Challenger",          "Complete your first challenge"),
    ("timed_10",          "⏱️", "Time Trial",          "Complete 10 Timed challenges"),
    ("flip_pro",          "🏓", "Flip Pro",            "Complete a Pro Flip challenge"),
    ("heat_10",           "🌡️", "Heat Survivor",       "Complete 10 Heat challenges"),
    ("triple_threat",     "🎯", "Triple Threat",       "Complete all 3 challenge types on one table"),
    ("challenge_50",      "🏋️", "Challenge Addict",    "Complete 50 challenges total"),
    # Exploration
    ("explorer",          "🗺️", "Explorer",            "Play 10 different tables"),
    ("globetrotter",      "🌍", "Globetrotter",        "Play tables from 5 different manufacturers"),
    ("bally_fan",         "🅱️", "Bally Fan",           "Play 5 different Bally tables"),
    ("williams_fan",      "🔷", "Williams Fan",        "Play 5 different Williams tables"),
    ("stern_fan",         "⚡", "Stern Fan",           "Play 5 different Stern tables"),
    ("gottlieb_fan",      "🔶", "Gottlieb Fan",        "Play 5 different Gottlieb tables"),
    # Playtime
    ("dedicated",         "⏰", "Dedicated",           "Accumulate 10 hours of total playtime"),
    ("marathon",          "🏃", "Marathon",            "Accumulate 50 hours of total playtime"),
    ("addict",            "🕹️", "Addict",              "Accumulate 100 hours of total playtime"),
    ("long_session",      "🌙", "Endurance",           "Play a single session for 60+ minutes"),
    # Special
    ("hot_streak",        "🔥", "Hot Streak",          "Unlock 5 achievements in a single session"),
    ("night_owl",         "🦉", "Night Owl",           "Start a session after midnight (00:00–05:00)"),
    ("speed_demon",       "⚡", "Speed Demon",         "Unlock 3 achievements within 5 minutes"),
    # Rarity
    ("rare_finder",       "🔵", "Rare Finder",         "Unlock a Rare achievement"),
    ("epic_hunter",       "🟣", "Epic Hunter",         "Unlock an Epic achievement"),
    ("legendary_hunter",  "🟠", "Legendary Hunter",    "Unlock a Legendary achievement"),
    # Cloud / Level
    ("cloud_pioneer",     "☁️", "Cloud Pioneer",       "Complete your first cloud upload"),
    ("level_5",           "🏅", "Level 5",             "Reach Player Level 5"),
    ("level_10",          "🎖️", "Level 10",            "Reach Player Level 10"),
]

BADGE_LOOKUP = {b[0]: b for b in BADGE_DEFINITIONS}


def _gather_badge_stats(cfg: "AppConfig", state: dict, watcher=None, rarity_cache: dict = None) -> dict:
    """Collect all statistics needed for badge evaluation."""
    stats = {}
    try:
        # Total unique achievements
        seen = set()
        for entries in (state.get("global") or {}).values():
            for e in (entries or []):
                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                if t:
                    seen.add(t)
        for entries in (state.get("session") or {}).values():
            for e in (entries or []):
                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                if t:
                    seen.add(t)
        stats["total_achievements"] = len(seen)
    except Exception:
        stats["total_achievements"] = 0

    try:
        lv = compute_player_level(state)
        stats["level"] = lv["level"]
        stats["prestige"] = lv["prestige"]
        stats["fully_maxed"] = lv["fully_maxed"]
    except Exception:
        stats["level"] = 1
        stats["prestige"] = 0
        stats["fully_maxed"] = False

    try:
        stats["roms_played"] = list(state.get("roms_played") or [])
    except Exception:
        stats["roms_played"] = []

    # Manufacturer counts from roms_played using watcher INDEX
    mfr_roms: dict = {}  # manufacturer -> set of roms
    try:
        if watcher is not None:
            for rom in stats["roms_played"]:
                mfr = watcher._get_manufacturer_from_rom(rom) if hasattr(watcher, "_get_manufacturer_from_rom") else None
                if mfr:
                    mfr_roms.setdefault(mfr, set()).add(rom)
    except Exception:
        pass
    stats["mfr_roms"] = mfr_roms
    stats["num_manufacturers"] = len(mfr_roms)

    # Challenge counts
    try:
        history_dir = os.path.join(cfg.BASE, "session_stats", "challenges", "history")
        challenge_counts: dict = {}  # kind -> count
        roms_with_challenges: dict = {}  # rom -> set of challenge kinds
        total_challenges = 0
        if os.path.isdir(history_dir):
            for fname in os.listdir(history_dir):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(history_dir, fname)
                try:
                    hist = secure_load_json(fpath, {}) or {}
                    for entry in (hist.get("results") or []):
                        kind = str(entry.get("kind") or "").lower()
                        rom = str(entry.get("rom") or "")
                        if kind:
                            challenge_counts[kind] = challenge_counts.get(kind, 0) + 1
                            total_challenges += 1
                        if kind and rom:
                            roms_with_challenges.setdefault(rom, set()).add(kind)
                except Exception:
                    continue
        stats["challenge_counts"] = challenge_counts
        stats["total_challenges"] = total_challenges
        stats["roms_with_all_3_challenges"] = any(
            len(kinds) >= 3 for kinds in roms_with_challenges.values()
        )
        # Check for Pro Flip (target_flips <= 100)
        has_flip_pro = False
        if os.path.isdir(history_dir):
            for fname in os.listdir(history_dir):
                if not fname.endswith(".json") or has_flip_pro:
                    continue
                fpath = os.path.join(history_dir, fname)
                try:
                    hist = secure_load_json(fpath, {}) or {}
                    for entry in (hist.get("results") or []):
                        if str(entry.get("kind") or "").lower() == "flip":
                            tf = int(entry.get("target_flips") or 0)
                            diff = str(entry.get("difficulty") or "").lower()
                            if tf <= 100 and tf > 0 or diff == "pro":
                                has_flip_pro = True
                                break
                except Exception:
                    continue
        stats["has_flip_pro"] = has_flip_pro
    except Exception:
        stats["challenge_counts"] = {}
        stats["total_challenges"] = 0
        stats["roms_with_all_3_challenges"] = False
        stats["has_flip_pro"] = False

    # Playtime from session stats txt/json files
    try:
        playtime_sec = 0
        max_session_sec = 0
        stats_dir = os.path.join(cfg.BASE, "session_stats")
        if os.path.isdir(stats_dir):
            highlights_dir = os.path.join(stats_dir, "Highlights")
            if os.path.isdir(highlights_dir):
                for fname in os.listdir(highlights_dir):
                    if fname.endswith(".summary.json"):
                        fpath = os.path.join(highlights_dir, fname)
                        try:
                            data = secure_load_json(fpath, {}) or {}
                            dur = int(data.get("duration_sec") or data.get("playtime_sec") or 0)
                            playtime_sec += dur
                            if dur > max_session_sec:
                                max_session_sec = dur
                        except Exception:
                            continue
        stats["total_playtime_sec"] = playtime_sec
        stats["max_session_sec"] = max_session_sec
    except Exception:
        stats["total_playtime_sec"] = 0
        stats["max_session_sec"] = 0

    # Max session unlocks (hot_streak): check from session state
    try:
        max_session_unlocks = 0
        for entries in (state.get("session") or {}).values():
            if entries:
                max_session_unlocks = max(max_session_unlocks, len(entries))
        stats["max_session_unlocks"] = max_session_unlocks
    except Exception:
        stats["max_session_unlocks"] = 0

    # Speed demon: 3 achievements within 5 minutes
    # Check session entries for timestamps
    try:
        speed_demon = False
        for entries in (state.get("session") or {}).values():
            if not entries or len(entries) < 3:
                continue
            ts_list = []
            for e in entries:
                if isinstance(e, dict) and e.get("ts"):
                    try:
                        from datetime import datetime as _dt
                        t = _dt.fromisoformat(str(e["ts"]).replace("Z", "+00:00"))
                        ts_list.append(t.timestamp())
                    except Exception:
                        pass
            if len(ts_list) >= 3:
                ts_list.sort()
                for i in range(len(ts_list) - 2):
                    if ts_list[i + 2] - ts_list[i] <= 300:
                        speed_demon = True
                        break
        stats["speed_demon"] = speed_demon
    except Exception:
        stats["speed_demon"] = False

    # Night owl: check recent session start times from summary files
    try:
        night_owl = False
        highlights_dir = os.path.join(cfg.BASE, "session_stats", "Highlights")
        if os.path.isdir(highlights_dir):
            for fname in os.listdir(highlights_dir):
                if fname.endswith(".summary.json"):
                    fpath = os.path.join(highlights_dir, fname)
                    try:
                        data = secure_load_json(fpath, {}) or {}
                        ts_str = str(data.get("ts") or data.get("start_ts") or "")
                        if ts_str:
                            from datetime import datetime as _dt
                            try:
                                t = _dt.fromisoformat(ts_str.replace("Z", "+00:00"))
                            except Exception:
                                continue
                            hour = t.hour
                            if 0 <= hour < 5:
                                night_owl = True
                                break
                    except Exception:
                        continue
        stats["night_owl"] = night_owl
    except Exception:
        stats["night_owl"] = False

    # Rarity checks
    try:
        has_rare = False
        has_epic = False
        has_legendary = False
        if rarity_cache and isinstance(rarity_cache, dict):
            for rom_cache in rarity_cache.values():
                if isinstance(rom_cache, dict):
                    for title, info in rom_cache.items():
                        if isinstance(info, dict):
                            tier = str(info.get("tier") or info.get("rarity") or "").lower()
                        else:
                            tier = str(info).lower()
                        if tier == "rare":
                            has_rare = True
                        elif tier == "epic":
                            has_epic = True
                        elif tier == "legendary":
                            has_legendary = True
        stats["has_rare"] = has_rare
        stats["has_epic"] = has_epic
        stats["has_legendary"] = has_legendary
    except Exception:
        stats["has_rare"] = False
        stats["has_epic"] = False
        stats["has_legendary"] = False

    # Cloud pioneer: check if any cloud upload has been done
    try:
        cloud_upload_done = bool(state.get("cloud_upload_done", False))
        stats["cloud_upload_done"] = cloud_upload_done
    except Exception:
        stats["cloud_upload_done"] = False

    return stats


BADGE_CHECKS = {
    "first_steps":      lambda s: s["total_achievements"] >= 1,
    "getting_started":  lambda s: s["total_achievements"] >= 5,
    "deca":             lambda s: s["total_achievements"] >= 10,
    "half_century":     lambda s: s["total_achievements"] >= 50,
    "century":          lambda s: s["total_achievements"] >= 100,
    "hoarder":          lambda s: s["total_achievements"] >= 500,
    "thousandaire":     lambda s: s["total_achievements"] >= 1000,
    "first_star":       lambda s: s["prestige"] >= 1,
    "two_stars":        lambda s: s["prestige"] >= 2,
    "three_stars":      lambda s: s["prestige"] >= 3,
    "four_stars":       lambda s: s["prestige"] >= 4,
    "five_stars":       lambda s: s["fully_maxed"],
    "challenger":       lambda s: s["total_challenges"] >= 1,
    "timed_10":         lambda s: s["challenge_counts"].get("timed", 0) >= 10,
    "flip_pro":         lambda s: s["has_flip_pro"],
    "heat_10":          lambda s: s["challenge_counts"].get("heat", 0) >= 10,
    "triple_threat":    lambda s: s["roms_with_all_3_challenges"],
    "challenge_50":     lambda s: s["total_challenges"] >= 50,
    "explorer":         lambda s: len(s["roms_played"]) >= 10,
    "globetrotter":     lambda s: s["num_manufacturers"] >= 5,
    "bally_fan":        lambda s: len(s["mfr_roms"].get("Bally", set())) >= 5,
    "williams_fan":     lambda s: len(s["mfr_roms"].get("Williams", set())) >= 5,
    "stern_fan":        lambda s: len(s["mfr_roms"].get("Stern", set())) >= 5,
    "gottlieb_fan":     lambda s: len(s["mfr_roms"].get("Gottlieb", set())) >= 5,
    "dedicated":        lambda s: s["total_playtime_sec"] >= 36000,   # 10 hours
    "marathon":         lambda s: s["total_playtime_sec"] >= 180000,  # 50 hours
    "addict":           lambda s: s["total_playtime_sec"] >= 360000,  # 100 hours
    "long_session":     lambda s: s["max_session_sec"] >= 3600,       # 60 minutes
    "hot_streak":       lambda s: s["max_session_unlocks"] >= 5,
    "night_owl":        lambda s: s["night_owl"],
    "speed_demon":      lambda s: s["speed_demon"],
    "rare_finder":      lambda s: s["has_rare"],
    "epic_hunter":      lambda s: s["has_epic"],
    "legendary_hunter": lambda s: s["has_legendary"],
    "cloud_pioneer":    lambda s: s["cloud_upload_done"],
    "level_5":          lambda s: s["level"] >= 5,
    "level_10":         lambda s: s["level"] >= 10,
}


def evaluate_badges(state: dict, cfg: "AppConfig", watcher=None, rarity_cache: dict = None) -> tuple:
    """Evaluate all badges and return (all_earned_ids, newly_earned_ids).

    Non-blocking: catches all exceptions internally.
    """
    try:
        already_earned = set(state.get("badges") or [])
        stats = _gather_badge_stats(cfg, state, watcher=watcher, rarity_cache=rarity_cache)
        newly_earned = []
        all_earned = list(already_earned)
        for badge_id, check_fn in BADGE_CHECKS.items():
            if badge_id in already_earned:
                continue
            try:
                if check_fn(stats):
                    newly_earned.append(badge_id)
                    all_earned.append(badge_id)
            except Exception:
                pass
        return all_earned, newly_earned
    except Exception:
        return list(state.get("badges") or []), []

import urllib.request
