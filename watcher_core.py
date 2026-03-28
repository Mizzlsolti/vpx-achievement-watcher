
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
                "theme",
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
                "theme",
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
def p_aweditor(cfg):     return os.path.join(cfg.BASE, "tools", "AWeditor")
def p_custom_events(cfg): return os.path.join(p_aweditor(cfg), "custom_events")
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

GITHUB_BASE = "https://raw.githubusercontent.com/tomlogic/pinmame-nvram-maps/eb0d7cf16c8df0ac60664eb83df1d19ee498f31e"
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

class CloudSync:
    _upload_skip_warned: bool = False
    _upload_skip_warned_lock = threading.Lock()

    # Client-side dedup: track (dedup_key -> timestamp) for recent competitive uploads.
    # Keys expire implicitly after _DEDUP_WINDOW_SEC seconds.
    _DEDUP_WINDOW_SEC: float = 60.0
    _recent_score_uploads: dict = {}
    _recent_score_uploads_lock = threading.Lock()
    _recent_progress_uploads: dict = {}
    _recent_progress_uploads_lock = threading.Lock()

    # Short-window dedup for full-achievements uploads to suppress burst duplicates that
    # arise when multiple callers (e.g. _ach_record_unlocks + _persist_and_toast) fire
    # upload_full_achievements for the same player within the same session-end cycle.
    _FULL_ACH_DEDUP_WINDOW_SEC: float = 5.0
    _recent_full_ach_uploads: dict = {}
    _recent_full_ach_uploads_lock = threading.Lock()

    # Notification message shown when a cloud upload is blocked due to missing VPS-ID.
    _BLOCKED_NO_VPS_MESSAGE: str = "Cloud Upload Blocked · No VPS-ID assigned\nGo to 'Available Maps' to assign this table"

    @staticmethod
    def _warn_missing_player_name(cfg: AppConfig) -> bool:
        """Returns True if player name is missing/default and upload should be skipped.
        Logs a once-only warning on the first occurrence."""
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not pname or pname.lower() == "player":
            with CloudSync._upload_skip_warned_lock:
                if not CloudSync._upload_skip_warned:
                    log(cfg, "[CLOUD] Upload skipped: Please set a player name (not 'Player') in System tab to enable cloud uploads.", "WARN")
                    CloudSync._upload_skip_warned = True
            return True
        return False

    @staticmethod
    def _emit_submission_state(cfg: "AppConfig", resp_body: str, bridge: Optional["Bridge"]) -> None:
        """Parse a server response body for submission_state and emit the status overlay signal.

        Handles structured responses: ``{"submission_state": "accepted"|"flagged"|"rejected"}``.
        Silently ignores empty bodies, plain-text, or legacy Firebase-style responses so that
        backwards compatibility with servers that do not return structured state is preserved.
        """
        if not bridge:
            return
        try:
            resp_data = json.loads(resp_body)
            if not isinstance(resp_data, dict):
                return
            state = str(resp_data.get("submission_state", "") or "").lower().strip()
            if state == "accepted":
                bridge.status_overlay_show.emit("Online · Verified", 0, "#00C853")
            elif state == "flagged":
                bridge.status_overlay_show.emit("Online · Flagged", 0, "#FFA500")
            elif state == "rejected":
                bridge.status_overlay_show.emit("Online · Rejected", 0, "#FF3B30")
        except Exception:
            pass

    @staticmethod
    def _notify_cloud_blocked(bridge: Optional["Bridge"], message: str) -> None:
        """Emit a status overlay badge when a cloud upload is locally blocked.

        Uses the same status_overlay_show signal as _emit_submission_state so the
        in-game badge reflects the blocked state with a consistent visual style.
        Silently no-ops when bridge is None (e.g. headless / test contexts).
        """
        if not bridge:
            return
        try:
            bridge.status_overlay_show.emit(message, 0, "#FFA500")
        except Exception:
            pass

    @staticmethod
    def validate_player_identity(cfg: AppConfig, player_id: str, player_name: str) -> dict:
        """Check whether player_id and player_name are valid and unique in the cloud.

        Returns ``{"ok": True}`` when the identity is valid, or
        ``{"ok": False, "reason": "name_reserved"|"id_conflict"|"name_conflict", "msg": "..."}``
        when validation fails.

        Scenarios:
        - Name is "Player" or "player" (case-insensitive) → name_reserved (always, even when cloud is off)
        - ID new + Name new → ok
        - ID exists + stored name matches entered name → ok (Cloud Restore)
        - ID exists + stored name does NOT match → id_conflict
        - Name already used by a different ID → name_conflict
        - Cloud URL missing or cloud disabled → server checks skipped (ok), but name_reserved still checked
        """
        player_id = (player_id or "").strip()
        player_name = (player_name or "").strip()

        # Always block the reserved default name, regardless of cloud state.
        if player_name.lower() == "player":
            return {
                "ok": False,
                "reason": "name_reserved",
                "msg": (
                    "⛔ Reserved Name — The name 'Player' cannot be used. "
                    "Please choose a different name."
                ),
            }

        if not player_id or not player_name:
            return {"ok": True}

        # Server-side checks require a reachable cloud and cloud sync enabled.
        if not cfg.CLOUD_URL or not cfg.CLOUD_ENABLED:
            return {"ok": True}

        existing_ids = CloudSync.fetch_player_ids(cfg)

        # Check 1: if this ID already exists, verify the stored name matches.
        if player_id in existing_ids:
            stored_name = CloudSync.fetch_node(cfg, f"players/{player_id}/achievements/name")
            if not isinstance(stored_name, str) or not stored_name.strip():
                # Fall back to a progress entry for the stored name.
                try:
                    progress = CloudSync.fetch_node(cfg, f"players/{player_id}/progress")
                    if isinstance(progress, dict) and progress:
                        first_entry = next(iter(progress.values()), None)
                        if isinstance(first_entry, dict):
                            stored_name = first_entry.get("name", "")
                except Exception as _e:
                    log(cfg, f"[CLOUD] validate_player_identity: progress fallback error for {player_id}: {_e}", "WARN")
                    stored_name = ""

            if isinstance(stored_name, str) and stored_name.strip():
                if stored_name.strip().lower() != player_name.lower():
                    return {
                        "ok": False,
                        "reason": "id_conflict",
                        "msg": (
                            "⛔ Player ID Conflict — This Player ID is already registered to a "
                            "different player name. Please choose a different Player ID or enter "
                            "the correct name."
                        ),
                    }

        # Check 2: if the entered name is already used by a different player ID.
        other_ids = [pid for pid in existing_ids if pid != player_id]
        if other_ids:
            paths = [f"players/{pid}/achievements/name" for pid in other_ids]
            batch = CloudSync.fetch_parallel(cfg, paths, max_workers=20)
            for _path, name_data in batch.items():
                if isinstance(name_data, str) and name_data.strip().lower() == player_name.lower():
                    return {
                        "ok": False,
                        "reason": "name_conflict",
                        "msg": (
                            "⛔ Duplicate Player Name — This player name is already in use by "
                            "another player. Please choose a different name."
                        ),
                    }

        return {"ok": True}

    @staticmethod
    def cleanup_legacy_progress(cfg: AppConfig) -> None:
        """Delete cloud progress entries that lack a vps_id (legacy entries uploaded before
        VPS mapping was mandatory).  Runs only once per installation, guarded by a marker file.
        Executes in a background thread to avoid blocking the UI.
        """
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not cfg.CLOUD_BACKUP_ENABLED:
            return

        marker = f_legacy_cleanup_marker(cfg)
        if os.path.isfile(marker):
            return

        pid = str(cfg.OVERLAY.get("player_id", "")).strip()
        if not pid or pid == "unknown":
            return

        def _task():
            try:
                # Write marker first so that a crash mid-cleanup doesn't re-run
                # on restart (partial cleanup is better than an infinite loop).
                try:
                    ensure_dir(os.path.dirname(marker))
                    with open(marker, "w", encoding="utf-8") as _f:
                        _f.write("1")
                except Exception as e:
                    log(cfg, f"[CLOUD] cleanup_legacy_progress: could not write marker: {e}", "WARN")

                progress_data = CloudSync.fetch_node(cfg, f"players/{pid}/progress")
                if not isinstance(progress_data, dict):
                    return

                _url = cfg.CLOUD_URL.strip().rstrip('/')
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                for rom, entry in progress_data.items():
                    if not isinstance(entry, dict):
                        continue
                    vps_id = (entry.get("vps_id") or "").strip()
                    if vps_id:
                        continue
                    # Delete legacy entry
                    endpoint = f"{_url}/players/{pid}/progress/{rom}.json"
                    try:
                        del_req = urllib.request.Request(endpoint, method="DELETE")
                        with urllib.request.urlopen(del_req, timeout=5, context=ctx):
                            pass
                        log(cfg, f"[CLOUD] Deleted legacy progress entry for {rom}: missing vps_id")
                    except Exception as e:
                        log(cfg, f"[CLOUD] Failed to delete legacy progress for {rom}: {e}", "WARN")
            except Exception as e:
                log(cfg, f"[CLOUD] cleanup_legacy_progress error: {e}", "WARN")

        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def upload_score(cfg: AppConfig, category: str, rom: str, score: int, extra_data: dict = None, bridge: Optional["Bridge"] = None):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or score <= 0:
            return
        if not cfg.CLOUD_BACKUP_ENABLED:
            return
        if CloudSync._warn_missing_player_name(cfg):
            return
        # Block upload if no VPS-ID assigned for this ROM
        try:
            from ui_vps import _load_vps_mapping
            _vps_mapping = _load_vps_mapping(cfg)
            _vps_id = (_vps_mapping.get(rom) or "").strip()
            if not _vps_id:
                log(cfg, f"[CLOUD] upload_score blocked for {rom}: no VPS-ID assigned", "WARN")
                CloudSync._notify_cloud_blocked(bridge, CloudSync._BLOCKED_NO_VPS_MESSAGE)
                return
            # Inject vps_id into extra_data so it gets included in the payload
            if extra_data is None:
                extra_data = {}
            extra_data = dict(extra_data)
            extra_data.setdefault("vps_id", _vps_id)
            # Enrich extra_data with VPS table metadata (table_name, author, version)
            try:
                from ui_vps import _load_vpsdb
                tables = _load_vpsdb(cfg)
                if tables:
                    for t in tables:
                        vps_entry = None
                        tf_entry = None
                        if t.get("id") == _vps_id:
                            vps_entry = t
                        else:
                            for tf in (t.get("tableFiles") or []):
                                if tf.get("id") == _vps_id:
                                    vps_entry = t
                                    tf_entry = tf
                                    break
                        if vps_entry:
                            table_name = vps_entry.get("name", "")
                            if table_name:
                                extra_data["table_name"] = table_name
                            if tf_entry:
                                version = tf_entry.get("version", "")
                                authors = tf_entry.get("authors") or []
                                if version:
                                    extra_data["version"] = version
                                if authors:
                                    extra_data["author"] = ", ".join(authors)
                            break
            except Exception:
                pass
        except Exception as e:
            log(cfg, f"[CLOUD] upload_score blocked for {rom}: VPS mapping error: {e}", "WARN")
            return
        
        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip()
        if not pid or pid == "unknown":
            log(cfg, f"[CLOUD] upload_score blocked for {rom}: no valid player_id", "WARN")
            return

        rom_key = rom
        if extra_data:
            if category == "flip" and "target_flips" in extra_data:
                rom_key = f"{rom}_f{extra_data['target_flips']}"
            elif category == "time" and "target_time" in extra_data:
                rom_key = f"{rom}_t{extra_data['target_time']}"
            elif "difficulty" in extra_data:
                clean_diff = str(extra_data["difficulty"]).replace(" ", "")
                rom_key = f"{rom}_{clean_diff}"

        # Client-side dedup: skip if an identical (pid, category, rom_key, score) was already
        # submitted within the dedup window to reduce accidental replay uploads.
        _dedup_key = f"{pid}|{category}|{rom_key}|{score}"
        _now = time.time()
        with CloudSync._recent_score_uploads_lock:
            # Prune expired entries to prevent unbounded growth over long sessions.
            _cutoff = _now - CloudSync._DEDUP_WINDOW_SEC
            CloudSync._recent_score_uploads = {
                k: v for k, v in CloudSync._recent_score_uploads.items() if v > _cutoff
            }
            _last_ts = CloudSync._recent_score_uploads.get(_dedup_key, 0.0)
            if _now - _last_ts < CloudSync._DEDUP_WINDOW_SEC:
                return
            CloudSync._recent_score_uploads[_dedup_key] = _now

        endpoint = f"{url}/players/{pid}/scores/{category}/{rom_key}.json"
        
        def _task():
            try:
                req = urllib.request.Request(endpoint)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                if data and isinstance(data, dict):
                    if score <= int(data.get("score", 0)):
                        return
            except Exception:
                pass 
            
            payload = {"name": pname, "score": score, "ts": datetime.now(timezone.utc).isoformat(), "watcher_version": WATCHER_VERSION}
            if extra_data: payload.update(extra_data)
            # Include selected badge for leaderboard display
            try:
                _ach_state = secure_load_json(f_achievements_state(cfg), {})
                _sel_badge = str(_ach_state.get("selected_badge") or "").strip()
                if _sel_badge:
                    payload["selected_badge"] = _sel_badge
            except Exception:
                pass
                
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=5) as resp:
                    resp_body = resp.read().decode()
                    log(cfg, f"[CLOUD] Uploaded {category.upper()} Score for {rom}: {score}")
                    CloudSync._emit_submission_state(cfg, resp_body, bridge)
            except Exception as e:
                log(cfg, f"[CLOUD] Upload failed: {e}", "WARN")
                
        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def upload_achievement_progress(cfg: AppConfig, rom: str, unlocked: int, total: int, bridge: Optional["Bridge"] = None):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or total <= 0:
            return
        if not cfg.CLOUD_BACKUP_ENABLED:
            return
        if CloudSync._warn_missing_player_name(cfg):
            return
        # Block upload if no VPS-ID assigned for this ROM
        try:
            from ui_vps import _load_vps_mapping
            _vps_mapping = _load_vps_mapping(cfg)
            _vps_id = (_vps_mapping.get(rom) or "").strip()
            if not _vps_id:
                log(cfg, f"[CLOUD] upload_achievement_progress blocked for {rom}: no VPS-ID assigned", "WARN")
                CloudSync._notify_cloud_blocked(bridge, CloudSync._BLOCKED_NO_VPS_MESSAGE)
                return
            _extra_vps_id = _vps_id
        except Exception as e:
            log(cfg, f"[CLOUD] upload_achievement_progress blocked for {rom}: VPS mapping error: {e}", "WARN")
            return

        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip()
        if not pid or pid == "unknown":
            log(cfg, f"[CLOUD] upload_achievement_progress blocked for {rom}: no valid player_id", "WARN")
            return

        # Client-side dedup: skip if the same (pid, rom, unlocked, total) was already submitted
        # within the dedup window to avoid redundant repeated progress writes.
        _dedup_key = f"{pid}|{rom}|{unlocked}|{total}"
        _now = time.time()
        with CloudSync._recent_progress_uploads_lock:
            # Prune expired entries to prevent unbounded growth over long sessions.
            _cutoff = _now - CloudSync._DEDUP_WINDOW_SEC
            CloudSync._recent_progress_uploads = {
                k: v for k, v in CloudSync._recent_progress_uploads.items() if v > _cutoff
            }
            _last_ts = CloudSync._recent_progress_uploads.get(_dedup_key, 0.0)
            if _now - _last_ts < CloudSync._DEDUP_WINDOW_SEC:
                return
            CloudSync._recent_progress_uploads[_dedup_key] = _now

        endpoint = f"{url}/players/{pid}/progress/{rom}.json"
        
        def _task():
            percentage = round((unlocked / total) * 100, 1)
            payload = {
                "name": pname,
                "unlocked": unlocked,
                "total": total,
                "percentage": percentage,
                "ts": datetime.now(timezone.utc).isoformat(),
                "watcher_version": WATCHER_VERSION,
            }
            # Include selected badge for leaderboard display
            try:
                _ach_state = secure_load_json(f_achievements_state(cfg), {})
                _sel_badge = str(_ach_state.get("selected_badge") or "").strip()
                payload["selected_badge"] = _sel_badge  # Always include, even if empty
            except Exception:
                pass
            if _extra_vps_id:
                payload["vps_id"] = _extra_vps_id
                try:
                    from ui_vps import _load_vpsdb
                    tables = _load_vpsdb(cfg)
                    if tables:
                        for t in tables:
                            vps_entry = None
                            tf_entry = None
                            if t.get("id") == _extra_vps_id:
                                vps_entry = t
                            else:
                                for tf in (t.get("tableFiles") or []):
                                    if tf.get("id") == _extra_vps_id:
                                        vps_entry = t
                                        tf_entry = tf
                                        break
                            if vps_entry:
                                table_name = vps_entry.get("name", "")
                                if table_name:
                                    payload["table_name"] = table_name
                                if tf_entry:
                                    version = tf_entry.get("version", "")
                                    authors = tf_entry.get("authors") or []
                                    if version:
                                        payload["version"] = version
                                    if authors:
                                        payload["author"] = ", ".join(authors)
                                break
                except Exception:
                    pass
            # Build vps_id_breakdown: count of unlocked achievements per vps_id
            try:
                ach_state = secure_load_json(f_achievements_state(cfg), {"global": {}, "session": {}})
                rom_achievements = ach_state.get("session", {}).get(rom, []) or []
                breakdown: dict = {}
                for ach in rom_achievements:
                    if isinstance(ach, dict):
                        vid = (ach.get("vps_id") or "").strip()
                        if vid:
                            breakdown[vid] = breakdown.get(vid, 0) + 1
                if breakdown:
                    payload["vps_id_breakdown"] = breakdown
            except Exception:
                pass
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=5) as resp:
                    resp_body = resp.read().decode()
                    log(cfg, f"[CLOUD] Uploaded Achievement Progress for {rom}: {unlocked}/{total} ({percentage}%)")
                    CloudSync._emit_submission_state(cfg, resp_body, bridge)
            except Exception as e:
                log(cfg, f"[CLOUD] Progress upload failed: {e}", "WARN")
        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def fetch_data(cfg: AppConfig, node_path: str) -> list:
        if not cfg.CLOUD_URL or not node_path: 
            return []
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        _MAX_RETRIES = 3
        for _attempt in range(_MAX_RETRIES):
            try:
                import urllib.request
                import ssl
                req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
                    raw_data = resp.read().decode('utf-8')
                    data = json.loads(raw_data)
                if not data: return []
                if isinstance(data, dict): return list(data.values())
                elif isinstance(data, list): return [x for x in data if x is not None]
                return []
            except Exception as e:
                if "UNEXPECTED_EOF_WHILE_READING" in str(e) and _attempt < _MAX_RETRIES - 1:
                    time.sleep(1 * (_attempt + 1))
                    continue
                log(cfg, f"[CLOUD] Fetch error for {endpoint}: {e}", "ERROR")
                return []

    @staticmethod
    def fetch_player_ids(cfg: AppConfig) -> list:
        """Return the list of all player IDs stored under /players/ using a shallow fetch."""
        if not cfg.CLOUD_URL:
            return []
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/players.json?shallow=true"
        _MAX_RETRIES = 3
        for _attempt in range(_MAX_RETRIES):
            try:
                import urllib.request
                import ssl
                req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                if isinstance(data, dict):
                    return list(data.keys())
                return []
            except Exception as e:
                if "UNEXPECTED_EOF_WHILE_READING" in str(e) and _attempt < _MAX_RETRIES - 1:
                    time.sleep(1 * (_attempt + 1))
                    continue
                log(cfg, f"[CLOUD] fetch_player_ids error: {e}", "ERROR")
                return []

    @staticmethod
    def fetch_node(cfg: AppConfig, node_path: str):
        """Fetch a single Firebase node and return the raw parsed object (dict, list, or None)."""
        if not cfg.CLOUD_URL or not node_path:
            return None
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        _MAX_RETRIES = 3
        for _attempt in range(_MAX_RETRIES):
            try:
                import urllib.request
                import ssl
                req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                if "UNEXPECTED_EOF_WHILE_READING" in str(e) and _attempt < _MAX_RETRIES - 1:
                    time.sleep(1 * (_attempt + 1))
                    continue
                log(cfg, f"[CLOUD] fetch_node error for {endpoint}: {e}", "ERROR")
                return None

    @staticmethod
    def fetch_parallel(cfg: AppConfig, node_paths: list, max_workers: int = 10) -> dict:
        """Fetch multiple Firebase nodes in parallel using ThreadPoolExecutor.

        Returns a dict mapping each node_path to its fetched data (or None on error).
        Turns N sequential requests into ~1 round-trip of parallel requests.
        """
        import concurrent.futures
        if not node_paths:
            return {}
        results = {}

        def _fetch_one(node_path):
            return node_path, CloudSync.fetch_node(cfg, node_path)

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(node_paths))) as executor:
            futures = {executor.submit(_fetch_one, path): path for path in node_paths}
            for future in concurrent.futures.as_completed(futures):
                try:
                    path, data = future.result()
                    results[path] = data
                except Exception as e:
                    path = futures.get(future, "unknown")
                    log(cfg, f"[CLOUD] fetch_parallel error for {path}: {e}", "ERROR")
        return results

    @staticmethod
    def set_node(cfg: AppConfig, node_path: str, data) -> bool:
        """Write (PUT) arbitrary data to a Firebase node. Returns True on success."""
        if not cfg.CLOUD_URL or not node_path:
            return False
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        try:
            import ssl
            payload = json.dumps(data).encode('utf-8')
            put_req = urllib.request.Request(endpoint, data=payload, method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(put_req, timeout=10, context=ctx) as resp:
                pass
            return True
        except Exception as e:
            log(cfg, f"[CLOUD] set_node error for {endpoint}: {e}", "WARN")
            return False

    @staticmethod
    def restore_from_cloud(cfg: AppConfig) -> bool:
        """Restore local achievement state from the cloud.

        Fetches ``players/{pid}/achievements`` and reconstructs the local
        ``achievements_state.json``.  Also fetches ``players/{pid}/progress``
        and merges ROM entries into ``roms_played`` and updates the local
        ``progress_upload_log.json`` so that already-uploaded progress entries
        are not re-sent after a restore.  After merging ``roms_played``, the
        method re-evaluates global achievement rules from ``global_achievements.json``
        that can be resolved without a running Watcher instance:

        * ``nvram_tally`` rules — sums the target field across all played ROMs
          by reading cached ``end_audits`` from each ROM's session summary file
          (``session_stats/Highlights/{rom}.summary.json``).
        * ``rom_count`` rules with ``manufacturer == "__any__"`` — checks whether
          enough distinct ROMs have been played (``min`` threshold only; rules that
          require per-manufacturer or per-brand counts are skipped because they
          need a running Watcher instance to resolve ROM → manufacturer mappings).

        Finally fetches ``players/{pid}/vps_mapping`` and saves it to the local
        ``vps_id_mapping.json``.

        Returns ``True`` on success, ``False`` when a critical step fails.
        """
        if not cfg.CLOUD_URL or not cfg.CLOUD_ENABLED:
            log(cfg, "[CLOUD] restore_from_cloud: cloud not enabled", "WARN")
            return False

        pid = str(cfg.OVERLAY.get("player_id", "")).strip()
        if not pid or pid == "unknown":
            log(cfg, "[CLOUD] restore_from_cloud: no valid player_id set", "WARN")
            return False

        # ── 1. Fetch achievements node ────────────────────────────────────────
        data = CloudSync.fetch_node(cfg, f"players/{pid}/achievements")
        if not data or not isinstance(data, dict):
            log(cfg, f"[CLOUD] restore_from_cloud: no achievements data found for player {pid}", "WARN")
            return False

        # ── 2. Reconstruct local achievements state ───────────────────────────
        state = {
            "global": {"__global__": data.get("global", [])},
            "session": data.get("session", {}),
            "roms_played": data.get("roms_played", []),
            "badges": data.get("badges", []),
            "selected_badge": data.get("selected_badge", ""),
        }
        if not isinstance(state["session"], dict):
            state["session"] = {}
        if not isinstance(state["roms_played"], list):
            state["roms_played"] = []

        # ── 3. Fetch progress node, enrich state, update local upload log ─────
        try:
            progress_data = CloudSync.fetch_node(cfg, f"players/{pid}/progress")
            if isinstance(progress_data, dict) and progress_data:
                log_data = _load_progress_upload_log(cfg)
                for rom, entry in progress_data.items():
                    if not isinstance(entry, dict) or not rom:
                        continue
                    vps_id = str(entry.get("vps_id") or "").strip()
                    if vps_id:
                        log_data[rom] = vps_id
                    # Populate roms_played from progress data
                    if rom not in state["roms_played"]:
                        state["roms_played"].append(rom)
                    # Warn when a ROM has unlocked achievements but no session
                    # entries could be reconstructed (cloud achievements node
                    # was stale when the progress was last written).
                    unlocked = entry.get("unlocked", 0)
                    if unlocked > 0 and rom not in state["session"]:
                        log(
                            cfg,
                            f"[CLOUD] restore_from_cloud: ROM '{rom}' has {unlocked} unlocked "
                            f"achievement(s) in progress but no session details in cloud — "
                            f"session details could not be fully reconstructed",
                            "WARN",
                        )
                _save_progress_upload_log(cfg, log_data)
                log(
                    cfg,
                    f"[CLOUD] restore_from_cloud: progress log restored for {len(progress_data)} ROM(s)",
                )
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: progress restore failed (non-critical): {e}", "WARN")

        # ── 3.5. Re-evaluate global achievements from local NVRAM summary data ─
        try:
            _global_rules_raw = load_json(f_global_ach(cfg))
            if isinstance(_global_rules_raw, list):
                _global_rules_for_restore = _global_rules_raw
            elif isinstance(_global_rules_raw, dict):
                _global_rules_for_restore = _global_rules_raw.get("rules") or []
            else:
                _global_rules_for_restore = []

            if _global_rules_for_restore:
                _roms_played = list(state.get("roms_played") or [])
                _already_global = {
                    str(e.get("title", "")).strip()
                    for entries in state.get("global", {}).values()
                    for e in (entries if isinstance(entries, list) else [])
                    if isinstance(e, dict)
                }

                # Load end_audits from session summary files for each played ROM
                _rom_audits_lc: dict = {}  # rom -> {field_lowercase: value}
                for _r in _roms_played:
                    _summary_path = os.path.join(p_highlights(cfg), f"{_r}.summary.json")
                    if os.path.isfile(_summary_path):
                        try:
                            _summary_data = secure_load_json(_summary_path, {})
                            _audits = _summary_data.get("end_audits", {})
                            if isinstance(_audits, dict) and _audits:
                                _rom_audits_lc[_r] = {k.lower(): v for k, v in _audits.items()}
                        except Exception:
                            pass

                _newly_global: list = []
                _now_iso = datetime.now(timezone.utc).isoformat()

                for _rule in _global_rules_for_restore:
                    if not isinstance(_rule, dict):
                        continue
                    _title = (_rule.get("title") or "").strip()
                    if not _title or _title in _already_global:
                        continue
                    _cond = _rule.get("condition") or {}
                    if not isinstance(_cond, dict):
                        continue
                    _rtype = str(_cond.get("type") or "").lower()

                    if _rtype == "nvram_tally":
                        _field = str(_cond.get("field") or "").strip()
                        if not _field or is_excluded_field(_field):
                            continue
                        try:
                            _need = int(_cond.get("min", 1))
                        except (TypeError, ValueError):
                            continue
                        _field_lc = _field.lower()
                        _total = 0
                        for _r in _roms_played:
                            _aud = _rom_audits_lc.get(_r, {})
                            try:
                                _total += int(_aud.get(_field_lc, 0))
                            except (TypeError, ValueError):
                                pass
                        if _total >= _need:
                            _newly_global.append({"title": _title, "ts": _now_iso, "origin": "global_achievements"})
                            _already_global.add(_title)

                    elif _rtype == "rom_count":
                        _manufacturer = str(_cond.get("manufacturer") or "").strip()
                        if _manufacturer != "__any__":
                            # Cannot resolve manufacturer without a running Watcher instance – skip
                            continue
                        _min_brands = _cond.get("min_brands")
                        if _min_brands is not None:
                            # Cannot determine per-brand counts without a running Watcher instance – skip
                            continue
                        try:
                            _need = int(_cond.get("min", 1))
                        except (TypeError, ValueError):
                            continue
                        if len(set(_roms_played)) >= _need:
                            _newly_global.append({"title": _title, "ts": _now_iso, "origin": "global_achievements"})
                            _already_global.add(_title)

                if _newly_global:
                    _global_lst = state.setdefault("global", {}).setdefault("__global__", [])
                    if not isinstance(_global_lst, list):
                        state["global"]["__global__"] = []
                        _global_lst = state["global"]["__global__"]
                    _global_lst.extend(_newly_global)
                    log(
                        cfg,
                        f"[CLOUD] restore_from_cloud: {len(_newly_global)} global achievement(s) "
                        f"re-evaluated and restored from local NVRAM data",
                    )
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: global achievement re-evaluation failed (non-critical): {e}", "WARN")

        # ── 4. Save the enriched state and recompute level ────────────────────
        try:
            secure_save_json(f_achievements_state(cfg), state)
            lv = compute_player_level(state)
            log(
                cfg,
                f"[CLOUD] restore_from_cloud: achievements restored for player {pid} "
                f"(level {lv['level']}, {lv['total']} achievements)",
            )
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: failed to save achievements state: {e}", "WARN")
            return False

        # ── 5. Fetch vps_mapping node and save locally ────────────────────────
        try:
            vps_data = CloudSync.fetch_node(cfg, f"players/{pid}/vps_mapping")
            if vps_data and isinstance(vps_data, dict):
                from ui_vps import _save_vps_mapping
                _save_vps_mapping(cfg, vps_data)
                log(cfg, f"[CLOUD] restore_from_cloud: VPS mapping restored: {len(vps_data)} entries")
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: VPS mapping restore failed (non-critical): {e}", "WARN")

        return True

    @staticmethod
    def upload_full_achievements(cfg: AppConfig, state: dict, player_name: str):
        """Upload the full achievements state (global + session + roms_played) to Firebase
        under /players/{pid}/achievements.json. Called automatically after each session
        and each achievement unlock when cloud sync is enabled."""
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL:
            return
        if not cfg.CLOUD_BACKUP_ENABLED:
            return
        pname = player_name.strip() if player_name else cfg.OVERLAY.get("player_name", "Player").strip()
        if not pname or pname.lower() == "player":
            with CloudSync._upload_skip_warned_lock:
                if not CloudSync._upload_skip_warned:
                    log(cfg, "[CLOUD] Upload skipped: Please set a player name (not 'Player') in System tab to enable cloud uploads.", "WARN")
                    CloudSync._upload_skip_warned = True
            return
        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip()

        # Dedup: suppress burst duplicates when multiple callers fire within the same
        # session-end cycle (e.g. _ach_record_unlocks + _persist_and_toast).
        _now = time.time()
        with CloudSync._recent_full_ach_uploads_lock:
            _last_ts = CloudSync._recent_full_ach_uploads.get(pid, 0.0)
            if _now - _last_ts < CloudSync._FULL_ACH_DEDUP_WINDOW_SEC:
                return
            CloudSync._recent_full_ach_uploads[pid] = _now

        endpoint = f"{url}/players/{pid}/achievements.json"

        def _task():
            global_entries = []
            try:
                global_entries = list(state.get("global", {}).get("__global__", []) or [])
            except Exception:
                pass
            session_entries = {}
            try:
                session_entries = dict(state.get("session", {}) or {})
            except Exception:
                pass
            roms_played = []
            try:
                roms_played = list(state.get("roms_played", []) or [])
            except Exception:
                pass
            lv = compute_player_level(state)
            badges = list(state.get("badges") or [])
            selected_badge = state.get("selected_badge", "")
            payload = {
                "name": pname,
                "ts": datetime.now(timezone.utc).isoformat(),
                "watcher_version": WATCHER_VERSION,
                "global": global_entries,
                "session": session_entries,
                "roms_played": roms_played,
                "player_level": lv["level"],
                "player_level_name": lv["name"],
                "player_prestige": lv["prestige"],
                "player_prestige_display": lv["prestige_display"],
                "player_fully_maxed": lv["fully_maxed"],
                "badges": badges,
                "badge_count": len(badges),
                "selected_badge": selected_badge,
            }
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=10) as resp:
                    log(cfg, "[CLOUD] Full achievements backup uploaded")
            except Exception as e:
                log(cfg, f"[CLOUD] upload_full_achievements failed: {e}", "WARN")

        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def fetch_rarity_for_rom(cfg: AppConfig, rom: str) -> tuple:
        """
        Fetch all players' achievement data from cloud and compute rarity for each
        achievement title of the given ROM.

        Returns: ({achievement_title: {tier, color, pct}, ...}, total_players)
        """
        player_ids = CloudSync.fetch_player_ids(cfg)
        if not player_ids:
            return {}, 0

        paths = [f"players/{pid}/achievements" for pid in player_ids]
        batch = CloudSync.fetch_parallel(cfg, paths)

        total_players = 0
        title_counts: dict = {}

        for path, data in batch.items():
            if not data or not isinstance(data, dict):
                continue
            session = data.get("session", {})
            rom_entries = session.get(rom, [])
            if not rom_entries:
                continue
            total_players += 1
            seen_titles: set = set()
            for e in rom_entries:
                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    title_counts[t] = title_counts.get(t, 0) + 1

        result: dict = {}
        for title, count in title_counts.items():
            result[title] = compute_rarity(count, total_players)

        # Cache rarity data back to cloud under players/{pid}/rarity_cache/{rom}.
        # Store as a list of {title, tier, color, pct} entries instead of a dict
        # keyed by achievement title: Firebase Realtime Database forbids certain
        # characters (. $ # [ ] /) in key names and achievement titles can contain
        # them (e.g. "Dr. Dude").  The in-memory `result` dict returned below is
        # always computed locally from player data and is never read back from this
        # Firebase node, so no reverse transformation is needed on the read path.
        try:
            if result and cfg.CLOUD_URL and cfg.CLOUD_ENABLED:
                overlay = cfg.OVERLAY if isinstance(cfg.OVERLAY, dict) else {}
                pid = str(overlay.get("player_id", "unknown")).strip()
                safe_rom = rom.replace("/", "_").replace(".", "_")
                result_list = [{"title": t, **info} for t, info in result.items()]
                CloudSync.set_node(
                    cfg,
                    f"players/{pid}/rarity_cache/{safe_rom}",
                    {"data": result_list, "total_players": total_players,
                     "ts": datetime.now(timezone.utc).isoformat()},
                )
        except Exception:
            pass

        return result, total_players


class Watcher:
    MIN_SEGMENTS_FOR_CLASSIFICATION = 1
    SUMMARY_FILENAME = "session_latest.summary.json"
    
    def __init__(self, cfg: AppConfig, bridge: "Bridge"):
        self.cfg = cfg
        self.bridge = bridge
        self._stop = threading.Event()
        self._flush_lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self._last_logged_rom = None
        self._map_found_logged_roms: set = set()
        self._rom_spec_batch: Optional[list] = None

        self.current_table: Optional[str] = None
        self.current_rom: Optional[str] = None
        self.start_time: Optional[float] = None
        self.game_active: bool = False
        self.start_audits: Dict[str, Any] = {}
        self.current_player = 1
        self.players: Dict[int, Dict[str, Any]] = {}
        self.ball_track = {
            "active": False, "index": 0, "start_time": None,
            "score_base": 0, "last_balls_played": None, "balls": []
        }
        self._last_audits_global: Dict[str, Any] = {}
        self._nvram_cache_rom: str = ""
        self._nvram_cache_mtime: float = 0.0
        self._nvram_cache_result: Tuple[Dict[str, Any], List[str], bool] = ({}, [], False)
        self.INDEX: Dict[str, Any] = {}
        self.ROMNAMES: Dict[str, Any] = {}
        
        self._field_layout_cache: Dict[str, Dict[str, Any]] = {}
        self.current_segment_provisional_diff: Dict[str, int] = {}
        self.include_current_segment_in_overlay = True
        self._control_fields_cache: Dict[str, List[dict]] = {}

        self._installed_roms_scan_cache: dict = {}   # manufacturer -> set of ROM names; '__all_with_map__' -> all ROMs with maps
        self._installed_roms_scan_done: bool = False
        self._rom_emoji_cache: dict = {}  # rom -> emoji string
        
        self.snapshot_mode = True
        self.snap_initialized = False
        self.field_stats = {}
        self.bootstrap_phase = False

        # In-memory cache of the last overlay snapshot payload (avoids disk read race)
        self._overlay_snapshot_cache: Optional[dict] = None

        self._flip_init_state()
        self._toasted_titles: set = set()

    def _map_fields_for_rom(self, rom: str) -> list[str]:
        out = []
        try:
            fields, _src = self.load_map_for_rom(rom)
            for f in (fields or []):
                lbl = str(f.get("label") or f.get("name") or "").strip()
                if not lbl:
                    continue
                ll = lbl.lower()
                if "score" in ll:
                    continue
                if is_excluded_field(lbl) or self.NOISE_REGEX.search(lbl):
                    continue
                out.append(lbl)
        except Exception:
            pass
        # unique preserve order
        seen = set()
        uniq = []
        for x in out:
            k = x.lower()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(x)
        return uniq

    def _flip_init_state(self):
        self._flip = {
            "active": False,
            "threshold": 500,
            "left": 0,
            "right": 0,
            "vk_left": 0,
            "vk_right": 0,
            "joy_left": 0,
            "joy_right": 0,
            "started_at": 0.0,
        }
        self._flip_inputs = {
            "kbd": None,
            "joy_running": False,
            "joy_thread": None,
            "joy_prev_masks": {},
        }
        self._heat_inputs = {
            "joy_running": False,
            "joy_thread": None,
        }

    def start_challenge_input_bindings(self) -> None:

        if getattr(self, "_ch_inputs", None) and self._ch_inputs.get("running"):
            return
        debounce_ms = int((self.cfg.OVERLAY or {}).get("ch_hotkey_debounce_ms", 120))
        self._ch_inputs = {
            "running": True,
            "active_source": None, 
            "nav_enabled": False,
            "last_press_ts": 0.0,
            "debounce_s": max(0.01, debounce_ms / 1000.0),
            "joy_running": False,
            "joy_last": 0,
            "kbd": None,
            "joy_thread": None,
        }
        try:
            hot_vk = int((self.cfg.OVERLAY or {}).get("challenge_hotkey_vk", 0x7A))
            left_vk = int((self.cfg.OVERLAY or {}).get("challenge_left_vk", 0x25))
            right_vk = int((self.cfg.OVERLAY or {}).get("challenge_right_vk", 0x27))
            kb_bindings = [
                {"get_vk": lambda hv=hot_vk: hv, "on_press": lambda: self._on_challenge_hotkey_press("keyboard")},
                {"get_vk": lambda lv=left_vk: lv, "on_press": lambda: self._on_challenge_nav_left("keyboard")},
                {"get_vk": lambda rv=right_vk: rv, "on_press": lambda: self._on_challenge_nav_right("keyboard")},
            ]
            self._ch_inputs["kbd"] = GlobalKeyHook(kb_bindings)
            self._ch_inputs["kbd"].install()
            log(self.cfg, "[CH-INPUT] Global keyboard hook installed for challenge controls")
        except Exception as e:
            log(self.cfg, f"[CH-INPUT] Keyboard hook install failed: {e}", "WARN")
        try:
            self._ch_inputs["joy_running"] = True
            t = threading.Thread(target=self._joystick_poll_loop, daemon=True, name="ChallengeJoyPoll")
            self._ch_inputs["joy_thread"] = t
            t.start()
            log(self.cfg, "[CH-INPUT] Joystick polling started for challenge controls")
        except Exception as e:
            log(self.cfg, f"[CH-INPUT] Joystick thread start failed: {e}", "WARN")
 
    def _player_balls_count(self, pid: int) -> int:
        try:
            balls = self.ball_track.get("balls", []) or []
            return sum(1 for b in balls if int(b.get("pid", 1)) == 1)
        except Exception:
            return 0
            
    def _alt_f4_visual_pinball_player(self, wait_ms: int = 3000) -> bool:
        try:
            import ctypes, time
            from ctypes import wintypes
            import win32gui, win32con, win32api
            pids = set()
            hwnds = []
            def _cb(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    title = (win32gui.GetWindowText(hwnd) or "").strip()
                    if title.startswith("Visual Pinball Player"):
                        hwnds.append(hwnd)
                        pid = wintypes.DWORD(0)
                        ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
                        if pid.value:
                            pids.add(int(pid.value))
                except Exception:
                    pass
                return True
            win32gui.EnumWindows(_cb, None)
            if not hwnds:
                return True  
            VK_MENU = 0x12   
            VK_F4 = 0x73
            KEYEVENTF_KEYUP = 0x0002
            for hwnd in hwnds:
                try:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    time.sleep(0.05)
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                    except Exception:
                        try:
                            fg = win32gui.GetForegroundWindow()
                            tid1 = ctypes.windll.user32.GetWindowThreadProcessId(fg, None)
                            tid2 = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                            ctypes.windll.user32.AttachThreadInput(tid1, tid2, True)
                            win32gui.SetForegroundWindow(hwnd)
                            ctypes.windll.user32.AttachThreadInput(tid1, tid2, False)
                        except Exception:
                            pass
                    time.sleep(0.05)
                    win32api.keybd_event(VK_MENU, 0, 0, 0)
                    time.sleep(0.01)
                    win32api.keybd_event(VK_F4, 0, 0, 0)
                    time.sleep(0.02)
                    win32api.keybd_event(VK_F4, 0, KEYEVENTF_KEYUP, 0)
                    time.sleep(0.01)
                    win32api.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
                    time.sleep(0.05)
                except Exception:
                    continue
            k32 = ctypes.windll.kernel32
            SYNCHRONIZE = 0x00100000
            handles = []
            for pid in pids:
                try:
                    h = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
                    if h:
                        handles.append(h)
                except Exception:
                    pass
            if handles:
                arr_type = wintypes.HANDLE * len(handles)
                arr = arr_type(*handles)
                k32.WaitForMultipleObjects(len(handles), arr, True, int(wait_ms))
                for h in handles:
                    try:
                        k32.CloseHandle(h)
                    except Exception:
                        pass
            else:
                time.sleep(min(1.0, wait_ms / 1000.0))
            still = []
            try:
                out = subprocess.check_output(["tasklist"], creationflags=0x08000000).decode(errors="ignore").lower()
                for pid in pids:
                    if str(pid) in out:
                        still.append(pid)
            except Exception:
                pass

            return len(still) == 0
        except Exception:
            return False
 
    def _base_map_exists(self, rom: str) -> bool:

        if not rom:
            return False
        maps_dir = p_local_maps(self.cfg)
        for candidate in (f"{rom}.json", f"{rom}.map.json"):
            path = os.path.join(maps_dir, candidate)
            if os.path.isfile(path):
                # Verify it is a real NVRAM map and not a custom achievements file.
                # A real map has "fields"; a custom achievements file has "rules" but
                # no "fields".  If we cannot read it, err on the side of treating it
                # as a real map (return True).
                try:
                    with open(path, "r", encoding="utf-8") as _f:
                        _data = json.load(_f)
                    if (
                        isinstance(_data, dict)
                        and "rules" in _data
                        and "fields" not in _data
                    ):
                        continue  # custom achievements file – not a real map
                except Exception:
                    pass
                return True
        return False

    def _has_any_map(self, rom: str) -> bool:
        if not rom:
            return False
        try:
            m1 = os.path.join(p_local_maps(self.cfg), f"{rom}.json")
            m2 = os.path.join(p_local_maps(self.cfg), f"{rom}.map.json")
            for candidate in (m1, m2):
                if os.path.isfile(candidate):
                    # Verify it is a real NVRAM map and not a custom achievements file.
                    # A real map has "fields"; a custom achievements file has "rules"
                    # but no "fields".  If we cannot read it, treat as real map.
                    try:
                        with open(candidate, "r", encoding="utf-8") as _f:
                            _data = json.load(_f)
                        if (
                            isinstance(_data, dict)
                            and "rules" in _data
                            and "fields" not in _data
                        ):
                            continue  # custom achievements file – not a real map
                    except Exception:
                        pass
                    return True
            fields, _ = self._try_load_map_for(rom)
            return bool(fields)
        except Exception:
            return False
 
    def _emit_mini_info_if_missing_map(self, rom: str, seconds: int = 5, *, table: str = ""):
        """Non-blocking: spawns a background thread to wait for VPX window and show info.

        Works for two cases:
        - ROM-based table with no NVRAM map (rom is non-empty, no map found)
        - No-ROM original VPX table (rom is empty, table name provided via ``table``)
        """
        import threading
        def _worker():
            import time
            try:
                import win32gui
            except ImportError:
                return
            try:
                # Determine the display identifier (ROM name or table name)
                identifier = rom or table
                if not identifier:
                    return
                # For ROM-based tables skip if a map already exists; for no-ROM tables
                # there can never be an NVRAM map, so we always show the notification.
                if rom and self._has_any_map(rom):
                    return
                # Requirement 2: If the user has already created a custom achievements
                # file for this table in AWEditor, suppress the "no map" notification –
                # they clearly know there is no NVRAM map and have handled it themselves.
                if table:
                    _custom_json = os.path.join(p_aweditor(self.cfg), f"{table}.custom.json")
                    if os.path.isfile(_custom_json):
                        return
                log(self.cfg, f"[OVERLAY] no-map worker start: identifier={identifier!r}")

                shown = getattr(self, "_mini_info_shown_for_rom", None)
                if not isinstance(shown, set):
                    shown = set()
                if identifier in shown:
                    return

                def _vpx_window_visible() -> bool:
                    found = False
                    def _cb(hwnd, _):
                        nonlocal found
                        try:
                            title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
                            if "visual pinball player" in title and win32gui.IsWindowVisible(hwnd):
                                found = True
                                return False
                        except Exception:
                            pass
                        return True
                    try:
                        win32gui.EnumWindows(_cb, None)
                    except Exception:
                        return False
                    return found

                for _ in range(120):  # max 60 s – VPX can take a while to show its window
                    if self._stop.is_set():
                        return
                    try:
                        if not self.game_active:
                            return
                    except Exception:
                        return
                    if _vpx_window_visible():
                        if rom:
                            msg = f"No NVRAM map found for ROM '{identifier}'."
                        else:
                            msg = f"No NVRAM map for '{identifier}'. Use AWEditor for custom achievements."
                        dur = max(3, int(seconds))
                        try:
                            self.bridge.challenge_info_show.emit(msg, dur, "#FF3B30")
                            shown.add(identifier)
                            self._mini_info_shown_for_rom = shown
                            log(self.cfg, f"[INFO] Mini overlay (no map) shown for {identifier!r}")
                        except Exception as e:
                            log(self.cfg, f"[OVERLAY] mini info emit failed: {e}", "WARN")
                        return
                    time.sleep(0.5)
            except Exception as e:
                log(self.cfg, f"[OVERLAY] mini info worker failed: {e}", "WARN")

        try:
            t = threading.Thread(target=_worker, daemon=True, name="MiniInfoMissingMap")
            t.start()
        except Exception:
            pass

    def _emit_mini_info_if_missing_vps_id(self, rom: str, seconds: int = 8):
        """Non-blocking: spawns a background thread to warn if cloud sync is enabled but no VPS-ID is set for the ROM."""
        import threading
        def _worker():
            import time
            try:
                import win32gui
            except ImportError:
                return
            try:
                if not rom:
                    return
                if not self.cfg.CLOUD_ENABLED:
                    return
                if not self._has_any_map(rom):
                    return

                shown = getattr(self, "_mini_info_vps_shown_for_rom", None)
                if not isinstance(shown, set):
                    shown = set()
                if rom in shown:
                    return

                try:
                    from ui_vps import _load_vps_mapping
                    mapping = _load_vps_mapping(self.cfg)
                    if mapping.get(rom):
                        return
                except Exception:
                    return

                def _vpx_window_visible() -> bool:
                    found = False
                    def _cb(hwnd, _):
                        nonlocal found
                        try:
                            title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
                            if "visual pinball player" in title and win32gui.IsWindowVisible(hwnd):
                                found = True
                                return False
                        except Exception:
                            pass
                        return True
                    try:
                        win32gui.EnumWindows(_cb, None)
                    except Exception:
                        return False
                    return found

                for _ in range(40):  # max 20s warten
                    if self._stop.is_set():
                        return
                    # Don't abort on game_active=False – short sessions would never see the
                    # notification because game_active can become False before the VPX window
                    # is detected by the poll.  Only _stop (watcher shutdown) should abort.
                    # Don't show while a challenge is active; the challenge start
                    # message would appear before this notification otherwise.
                    try:
                        if getattr(self, "challenge", {}).get("active", False):
                            return
                    except Exception:
                        pass
                    if _vpx_window_visible():
                        msg = f"No VPS-ID set for {rom}. Progress will NOT be uploaded to cloud.\nGo to 'Available Maps' tab to assign."
                        dur = max(5, int(seconds))
                        try:
                            self.bridge.challenge_info_show.emit(msg, dur, "#FF7F00")
                            shown.add(rom)
                            self._mini_info_vps_shown_for_rom = shown
                            log(self.cfg, f"[INFO] Mini overlay (no VPS-ID) shown for {rom}")
                        except Exception as e:
                            log(self.cfg, f"[OVERLAY] mini info vps emit failed: {e}", "WARN")
                        return
                    time.sleep(0.5)
            except Exception as e:
                log(self.cfg, f"[OVERLAY] mini info vps worker failed: {e}", "WARN")

        try:
            t = threading.Thread(target=_worker, daemon=True, name="MiniInfoMissingVpsId")
            t.start()
        except Exception:
            pass

    def _plausible_counter(self, label: str) -> bool:
        if not label:
            return False
        l = label.lower()
        keys = [
            "games", "balls", "ramp", "bumper", "spinner", "extra",
            "bonus", "hits", "made", "served", "targets", "loops",
            "lane", "kicks", "multiball", "jackpot", "mode"
        ]
        return any(k in l for k in keys)

    def _session_milestones_for_field(self, field_label: str) -> list[int]:
        f = (field_label or "").lower()
        if "extra ball" in f:
            return [3, 5]
        if "ball save" in f:
            return [3, 5, 10]
        if "jackpot" in f:
            return [1, 3, 5, 10, 15]
        if "multiball" in f:
            return [1, 3, 5]
        if "ramp" in f:
            return [5, 10, 15, 20, 25]
        if "loop" in f or "orbit" in f:
            return [3, 5, 10, 15]
        if "spinner" in f:
            return [10, 20, 30, 50]
        if "target" in f:
            return [10, 20, 30, 50]
        if "mode" in f:
            return [1, 3, 5, 10]
        return [1, 3, 5, 10, 15, 20, 25, 30]
        
    def _overall_milestones_for_field(self, field_label: str) -> list[int]:
        f = (field_label or "").lower()
        if "games started" in f:
            return [50, 100, 250, 500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 25000, 30000, 50000]
        if "balls played" in f:
            return [100, 250, 500, 1000, 2500, 5000, 10000, 15000, 25000, 50000, 75000, 100000]
        if "extra ball" in f:
            return [10, 20, 30, 50, 100, 250, 500, 1000, 2500, 5000]
        if "ball save" in f:
            return [20, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        if "jackpot" in f:
            return [25, 50, 100, 150, 300, 500, 1000, 2500, 5000, 10000]
        if "multiball" in f:
            return [10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
        if "ramp" in f:
            return [100, 200, 300, 500, 1000, 2500, 5000, 10000, 25000, 50000]
        if "loop" in f or "orbit" in f:
            return [100, 200, 500, 1000, 2500, 5000, 10000, 25000]
        if "modes completed" in f or ("mode" in f and "complete" in f):
            return [10, 25, 50, 100, 250, 500, 1000, 2500]
        if "modes started" in f or ("mode" in f and "start" in f):
            return [25, 50, 100, 250, 500, 1000, 2500, 5000]
        return [50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000]

    def _generate_default_global_rules(self) -> list[dict]:
        rules: list[dict] = []
        seen: set[str] = set()
        candidate_fields = [
            "Games Started", "Balls Played", "Ramps Made", "Jackpots",
            "Total Multiballs", "Loops",
            "Combos", "Extra Balls", "Ball Saves",
        ]

        total_target = 150
        ci = 0
        while len(rules) < total_target and candidate_fields:
            if ci >= len(candidate_fields):
                break
            fld = candidate_fields[ci % len(candidate_fields)]
            for m in self._overall_milestones_for_field(fld):
                if len(rules) >= total_target:
                    break
                title = self._unique_title(f"Global – {fld}: {m} Total", seen)
                rules.append({
                    "title": title,
                    "scope": "global",
                    "condition": {"type": "nvram_tally", "field": fld, "min": int(m)}
                })
            ci += 1

        # --- Manufacturer-based global achievements ---
        MANUFACTURER_ACHIEVEMENTS = [
            # Rookie: play 3 different tables of a manufacturer
            {"title": "Bally Rookie",      "type": "rom_count", "manufacturer": "Bally",     "min": 3},
            {"title": "Williams Rookie",   "type": "rom_count", "manufacturer": "Williams",  "min": 3},
            {"title": "Stern Rookie",      "type": "rom_count", "manufacturer": "Stern",     "min": 3},
            {"title": "Data East Rookie",  "type": "rom_count", "manufacturer": "Data East", "min": 3},
            {"title": "Gottlieb Rookie",   "type": "rom_count", "manufacturer": "Gottlieb",  "min": 3},
            {"title": "Sega Rookie",       "type": "rom_count", "manufacturer": "Sega",      "min": 3},
            {"title": "Capcom Rookie",     "type": "rom_count", "manufacturer": "Capcom",    "min": 3},
            # Veteran: play 5 different tables of a manufacturer
            {"title": "Bally Veteran",     "type": "rom_count", "manufacturer": "Bally",     "min": 5},
            {"title": "Williams Veteran",  "type": "rom_count", "manufacturer": "Williams",  "min": 5},
            {"title": "Stern Veteran",     "type": "rom_count", "manufacturer": "Stern",     "min": 5},
            {"title": "Data East Veteran", "type": "rom_count", "manufacturer": "Data East", "min": 5},
            {"title": "Gottlieb Veteran",  "type": "rom_count", "manufacturer": "Gottlieb",  "min": 5},
            # Master: play all installed tables of a manufacturer
            {"title": "Bally Master",      "type": "rom_complete_set", "manufacturer": "Bally"},
            {"title": "Williams Master",   "type": "rom_complete_set", "manufacturer": "Williams"},
            {"title": "Stern Master",      "type": "rom_complete_set", "manufacturer": "Stern"},
            {"title": "Data East Master",  "type": "rom_complete_set", "manufacturer": "Data East"},
            {"title": "Gottlieb Master",   "type": "rom_complete_set", "manufacturer": "Gottlieb"},
            {"title": "Sega Master",       "type": "rom_complete_set", "manufacturer": "Sega"},
            {"title": "Capcom Master",     "type": "rom_complete_set", "manufacturer": "Capcom"},
            # Cross-brand
            {"title": "Brand Explorer",    "type": "rom_count", "manufacturer": "__any__",   "min_brands": 3},
            {"title": "Brand Connoisseur", "type": "rom_count", "manufacturer": "__any__",   "min_brands": 5},
            {"title": "Brand Master",      "type": "rom_count", "manufacturer": "__any__",   "min_brands": 7},
            # Combo / Era
            {"title": "Golden Age",        "type": "rom_multi_brand", "manufacturers": ["Bally", "Williams", "Gottlieb"]},
            {"title": "Modern Era",        "type": "rom_multi_brand", "manufacturers": ["Stern", "Data East", "Sega"]},
            # Collector milestones (any manufacturer)
            {"title": "Table Tourist",     "type": "rom_count", "manufacturer": "__any__",   "min": 10},
            {"title": "Table Explorer",    "type": "rom_count", "manufacturer": "__any__",   "min": 20},
            {"title": "Complete Collector", "type": "rom_complete_set", "manufacturer": "__any__"},
            # Extra
            {"title": "Midway Rookie",     "type": "rom_count", "manufacturer": "Midway",    "min": 3},
            {"title": "Midway Master",     "type": "rom_complete_set", "manufacturer": "Midway"},
            {"title": "Premier Rookie",    "type": "rom_count", "manufacturer": "Premier",   "min": 3},
        ]
        for ach in MANUFACTURER_ACHIEVEMENTS:
            t = ach["title"]
            atype = ach["type"]
            if atype == "rom_multi_brand":
                rules.append({
                    "title": t,
                    "scope": "global",
                    "condition": {
                        "type": "rom_multi_brand",
                        "manufacturers": ach["manufacturers"],
                    },
                })
            elif atype == "rom_complete_set":
                rules.append({
                    "title": t,
                    "scope": "global",
                    "condition": {
                        "type": "rom_complete_set",
                        "manufacturer": ach["manufacturer"],
                    },
                })
            else:
                cond: dict = {"type": "rom_count", "manufacturer": ach["manufacturer"]}
                if "min" in ach:
                    cond["min"] = ach["min"]
                if "min_brands" in ach:
                    cond["min_brands"] = ach["min_brands"]
                rules.append({
                    "title": t,
                    "scope": "global",
                    "condition": cond,
                })

        # --- Challenge-based global achievements ---
        CHALLENGE_ACHIEVEMENTS = [
            # Timed challenges
            {"title": "Complete Your First Timed Challenge",  "challenge_type": "timed", "min": 1},
            {"title": "Complete 5 Timed Challenges",          "challenge_type": "timed", "min": 5},
            {"title": "Complete 10 Timed Challenges",         "challenge_type": "timed", "min": 10},
            {"title": "Complete 25 Timed Challenges",         "challenge_type": "timed", "min": 25},
            {"title": "Complete 50 Timed Challenges",         "challenge_type": "timed", "min": 50},
            # Flip challenges
            {"title": "Complete Your First Flip Challenge",   "challenge_type": "flip",  "min": 1},
            {"title": "Complete 5 Flip Challenges",           "challenge_type": "flip",  "min": 5},
            {"title": "Complete 10 Flip Challenges",          "challenge_type": "flip",  "min": 10},
            {"title": "Complete 25 Flip Challenges",          "challenge_type": "flip",  "min": 25},
            {"title": "Complete 50 Flip Challenges",          "challenge_type": "flip",  "min": 50},
            # Heat challenges
            {"title": "Complete Your First Heat Challenge",   "challenge_type": "heat",  "min": 1},
            {"title": "Complete 5 Heat Challenges",           "challenge_type": "heat",  "min": 5},
            {"title": "Complete 10 Heat Challenges",          "challenge_type": "heat",  "min": 10},
            {"title": "Complete 25 Heat Challenges",          "challenge_type": "heat",  "min": 25},
            {"title": "Complete 50 Heat Challenges",          "challenge_type": "heat",  "min": 50},
        ]
        for ach in CHALLENGE_ACHIEVEMENTS:
            rules.append({
                "title": ach["title"],
                "scope": "global",
                "condition": {
                    "type": "challenge_count",
                    "challenge_type": ach["challenge_type"],
                    "min": ach["min"],
                },
            })

        return rules        
            
    def _ensure_rom_specific(self, rom: str, audits: dict):
        if not rom or not audits:
            return
        path = os.path.join(p_rom_spec(self.cfg), f"{rom}.ach.json")
        if os.path.exists(path):
            return

        priority_set = set()
        
        fields_meta, _ = self.load_map_for_rom(rom)
        priority_fields = []
        if fields_meta:
            for f in fields_meta:
                sec = str(f.get("section", "")).lower()
                if "feature" in sec or "champion" in sec or "mode" in sec:
                    lbl = str(f.get("label") or f.get("name") or "")
                    if lbl and lbl in audits:
                        priority_fields.append(lbl)
                        priority_set.add(lbl) # Direkt ins Set schreiben

        target_session_total = max(36, len(priority_fields) * 2 + 15)
        session_time_minutes = [5, 10, 15, 20, 30, 45]
        max_session_milestones_per_field = 2
        max_session_uses_per_field = 2

        def ok_label(lbl: str) -> bool:
            if not isinstance(lbl, str) or not lbl.strip():
                return False
            ll = lbl.lower()
            if lbl not in priority_set and "score" in ll:
                return False
            if lbl not in priority_set and (is_excluded_field(lbl) or self.NOISE_REGEX.search(lbl)):
                return False
            if ll in {"current_player", "player_count", "current_ball", "balls played", "credits", "tilted", "game over", "tilt warnings"}:
                return False
            return True

        def category(lbl: str) -> str:
            ll = (lbl or "").lower()
            if any(k in ll for k in ["extra ball", "ball save", "multiball", "jackpot", "wizard"]):
                return "power"
            if any(k in ll for k in ["ramp", "loop", "orbit", "spinner", "target", "combo"]):
                return "precision"
            if any(k in ll for k in ["mode", "lock", "locks lit", "balls locked"]):
                return "progress"
            if any(k in ll for k in ["games started", "balls played"]):
                return "meta"
            return "other"

        def uniq(seq):
            seen = set()
            out = []
            for x in seq:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        def session_cap_for(lbl: str) -> int:
            l = (lbl or "").lower()
            if "extra ball" in l: return 5
            if "ball save" in l:  return 10
            if "jackpot" in l:    return 10
            if "multiball" in l:  return 3
            if "ramp" in l:       return 20
            if "loop" in l or "orbit" in l: return 10
            if "spinner" in l:    return 30
            if "target" in l:     return 30
            if "mode" in l:       return 5
            return 15

        def pick_session_milestones(lbl: str) -> list[int]:
            if lbl in priority_set and ("score" in lbl.lower() or "champion" in lbl.lower()):
                return [1]
            mils = self._session_milestones_for_field(lbl) or []
            cap = session_cap_for(lbl)
            mils = [m for m in mils if m <= cap]
            if not mils:
                return [1] if lbl in priority_set else []
            if len(mils) == 1:
                return [mils[0]]
            low = mils[0]
            mid = mils[max(1, len(mils)//2 - 1)]
            return uniq([low, mid])[:max_session_milestones_per_field]

        int_fields = [k for k, v in audits.items() if isinstance(v, int)]
        plausible = [k for k in int_fields if self._plausible_counter(k) and ok_label(k)]

        map_fields = self._map_fields_for_rom(rom)
        ordered = uniq([*priority_fields, *map_fields, *plausible]) or map_fields or plausible or int_fields
        ordered = [f for f in ordered if ok_label(f)]

        cats = {"power": [], "precision": [], "progress": [], "meta": [], "other": []}
        for f in ordered:
            cats[category(f)].append(f)

        rr = [
            ("power", cats["power"]),
            ("precision", cats["precision"]),
            ("progress", cats["progress"]),
            ("meta", cats["meta"]),
            ("other", cats["other"]),
        ]

        session_fields = []
        for f in priority_fields:
            if f in ordered and f not in session_fields:
                session_fields.append(f)

        target_session_unique_fields = max(15, len(session_fields) + 10)
        idxs = {k: 0 for k, _ in rr}
        while len(session_fields) < target_session_unique_fields:
            progressed = False
            for key, arr in rr:
                i = idxs[key]
                while i < len(arr) and arr[i] in session_fields:
                    i += 1
                idxs[key] = i
                if i < len(arr):
                    session_fields.append(arr[i])
                    idxs[key] = i + 1
                    progressed = True
            if not progressed:
                break

        if not session_fields:
            session_fields = ordered[:target_session_unique_fields]

        rules: list[dict] = []
        seen_titles: set[str] = set()

        for mins in session_time_minutes:
            secs = int(mins * 60)
            title = self._unique_title(f"{rom} – Play {mins} Minutes", seen_titles)
            rules.append({
                "title": title,
                "condition": {"type": "session_time", "min_seconds": secs},
                "scope": "session"
            })

        remaining_session = max(0, target_session_total - len(rules))
        used_session_per_field: dict[str, int] = {}

        for fld in session_fields:
            if remaining_session <= 0:
                break
            fl = (fld or "").lower()
            if "games started" in fl:
                continue
            picks = pick_session_milestones(fld)
            if not picks:
                continue
            for m in picks:
                if remaining_session <= 0:
                    break
                cnt = used_session_per_field.get(fld, 0)
                if cnt >= max_session_uses_per_field:
                    break
                title = self._unique_title(f"{rom} – {fld}: {int(m)}", seen_titles)
                rules.append({
                    "title": title,
                    "condition": {"type": "nvram_delta", "field": fld, "min": int(m)},
                    "scope": "session"
                })
                used_session_per_field[fld] = cnt + 1
                remaining_session -= 1

        if save_json(path, {"rules": rules}):
            batch = getattr(self, "_rom_spec_batch", None)
            if isinstance(batch, list):
                batch.append((rom, len(rules)))
            else:
                log(self.cfg, f"[ROM_SPEC] created {path} with {len(rules)} session-only rules (included priority fields)")

    def _unique_title(self, title: str, seen: set[str]) -> str:
        base = title.strip()
        if base not in seen:
            seen.add(base)
            return base
        i = 2
        while True:
            cand = f"{base} #{i}"
            if cand not in seen:
                seen.add(cand)
                return cand
            i += 1

    def _milestones(self, kind: str) -> list[int]:
        if kind == "session":
            return [1, 3, 5, 7, 10, 12, 15, 20, 25, 30, 40, 50]
        if kind == "overall":
            return [25, 50, 75, 100, 150, 200, 300, 400, 500, 750, 1000]
        if kind == "time":
            return [180, 300, 480, 600, 720, 900, 1200, 1500, 1800, 2400, 3000]
        return []

    def bootstrap(self):
        for d in [
            self.cfg.BASE,
            p_maps(self.cfg),
            p_local_maps(self.cfg),
            p_session(self.cfg),
            p_highlights(self.cfg),
            p_achievements(self.cfg),
            p_rom_spec(self.cfg),
            p_aweditor(self.cfg),
            p_custom_events(self.cfg),
        ]:
            ensure_dir(d)

        _set_folder_hidden(p_session(self.cfg))
        _set_folder_hidden(p_achievements(self.cfg))

        def ensure_file(path, url):
            if os.path.exists(path):
                return
            try:
                data = _fetch_bytes_url(url, timeout=25)
                ensure_dir(os.path.dirname(path))
                with open(path, "wb") as f:
                    f.write(data)
                log(self.cfg, f"Downloaded {url} -> {path}")
            except Exception as e:
                log(self.cfg, f"Could not download {url}: {e}", "ERROR")

        def refresh_file(path, url):
            """Always attempt a fresh download; fall back to existing local file on failure."""
            try:
                data = _fetch_bytes_url(url, timeout=25)
                ensure_dir(os.path.dirname(path))
                with open(path, "wb") as f:
                    f.write(data)
                log(self.cfg, f"Refreshed {url} -> {path}")
            except Exception as e:
                if os.path.exists(path):
                    log(self.cfg, f"Could not refresh {url}, keeping existing file: {e}", "WARN")
                else:
                    log(self.cfg, f"Could not download {url} and no local copy exists: {e}", "ERROR")

        refresh_file(f_index(self.cfg), INDEX_URL)
        refresh_file(f_romnames(self.cfg), ROMNAMES_URL)
        from ui_vps import VPSDB_URL as _VPSDB_URL
        ensure_file(f_vpsdb_cache(self.cfg), _VPSDB_URL)
        try:
            ensure_vpxtool(self.cfg)
        except Exception as e:
            log(self.cfg, f"[VPXTOOL] ensure failed: {e}", "WARN")

        self.INDEX = load_json(f_index(self.cfg), {}) or {}
        self.ROMNAMES = load_json(f_romnames(self.cfg), {}) or {}
            
    def _prefetch_worker(self):
        try:
            if hasattr(self, "bridge") and hasattr(self.bridge, "prefetch_started"):
                self.bridge.prefetch_started.emit()
        except Exception:
            pass

        if not self.INDEX:
            log(self.cfg, "Prefetch: INDEX empty, attempting reload...", "WARN")
            try:
                self.INDEX = load_json(f_index(self.cfg), {}) or {}
                if not self.INDEX:
                    mj = _fetch_json_url(INDEX_URL, timeout=25)
                    save_json(f_index(self.cfg), mj)
                    self.INDEX = mj or {}
            except Exception as e:
                msg = f"Prefetch aborted: cannot load INDEX: {e}"
                log(self.cfg, msg, "ERROR")
                try:
                    if hasattr(self, "bridge") and hasattr(self.bridge, "prefetch_finished"):
                        self.bridge.prefetch_finished.emit(msg)
                except Exception:
                    pass
                return
                
        unique_rels = set()
        total_roms = 0
        for rom, entry in self.INDEX.items():
            if str(rom).startswith("_"):
                continue
            total_roms += 1
            rel = entry if isinstance(entry, str) else (entry.get("path") or entry.get("file"))
            if not rel:
                continue
            if rel.startswith("maps/"):
                rel = rel[len("maps/"):]
            unique_rels.add(rel)
            
        downloaded = 0
        for rel in sorted(unique_rels):
            local = os.path.join(p_local_maps(self.cfg), rel.replace("/", os.sep))
            if os.path.exists(local):
                continue
            try:
                url = f"{GITHUB_BASE}/maps/{rel.lstrip('/')}"
                mj = _fetch_json_url(url, timeout=25)
                if save_json(local, mj):
                    downloaded += 1
                    if downloaded % PREFETCH_LOG_EVERY == 0:
                        prog_msg = f"downloaded {downloaded} unique maps..."
                        log(self.cfg, f"Prefetch progress: {prog_msg}")
                        try:
                            if hasattr(self, "bridge") and hasattr(self.bridge, "prefetch_progress"):
                                self.bridge.prefetch_progress.emit(prog_msg)
                        except Exception:
                            pass
            except Exception as e:
                log(self.cfg, f"Prefetch miss {rel}: {e}", "WARN")
                
        fin_msg = f"Prefetch finished. ROMs in index: {total_roms}, unique map files: {len(unique_rels)}, newly downloaded: {downloaded}"
        log(self.cfg, fin_msg)
        try:
            if hasattr(self, "bridge") and hasattr(self.bridge, "prefetch_finished"):
                self.bridge.prefetch_finished.emit(fin_msg)
        except Exception:
            pass

    def start_prefetch_background(self):
        if PREFETCH_MODE != "background":
            log(self.cfg, "Prefetch disabled (mode != background)")
            return
        threading.Thread(target=self._prefetch_worker, daemon=True).start()

    @staticmethod
    def _to_int(v, default=2):
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            try:
                if s.startswith("0x"):
                    return int(s, 16)
                return int(s)
            except Exception:
                return default
        return default

    def parse_map(self, mj):
        fields: List[Dict[str, Any]] = []
        if not isinstance(mj, dict):
            return fields

        if isinstance(mj.get("fields"), list):
            for f in mj["fields"]:
                if not isinstance(f, dict):
                    continue
                label = str(f.get("label") or f.get("name") or "field")
                ll = label.strip().lower()
                if ll in {"current_player", "player_count", "p2 score", "p3 score", "p4 score"}:
                    continue
                fields.append({
                    "name": f.get("name") or f.get("label") or "field",
                    "label": f.get("label") or f.get("name") or "field",
                    "offset": self._to_int(f.get("offset", f.get("start", 0)), 0),
                    "size": self._to_int(f.get("size", f.get("length", 2)), 2),
                    "encoding": f.get("encoding") or None,
                    "endian": f.get("endian") or None,
                    "scale": float(f.get("scale") or 1.0),
                    "signed": bool(f.get("signed", False)),
                    "mask": self._to_int(f.get("mask", 0), 0),
                    "value_offset": self._to_int(f.get("value_offset", f.get("offset_adjust", f.get("valueoffset", 0))), 0)
                })
            return fields

        if isinstance(mj.get("game_state"), dict):
            gs = mj["game_state"]
            scores = gs.get("scores")
            if isinstance(scores, list) and scores:
                sc = scores[0]  # nur P1
                if isinstance(sc, dict) and "start" in sc:
                    fields.append({
                        "name": "P1 Score",
                        "label": "P1 Score",
                        "offset": self._to_int(sc.get("start", 0), 0),
                        "size": self._to_int(sc.get("length", 2), 2),
                        "encoding": sc.get("encoding") or "bcd",
                        "endian": sc.get("endian") or None,
                        "scale": float(sc.get("scale") or 1.0),
                        "signed": bool(sc.get("signed", False)),
                        "mask": self._to_int(sc.get("mask", 0), 0),
                        "value_offset": self._to_int(sc.get("value_offset", sc.get("offset", 0)), 0)
                    })

            def add_gs(name_in: str, label_out: str | None = None):
                ent = gs.get(name_in)
                if not isinstance(ent, dict) or "start" not in ent:
                    return
                lab = label_out or str(ent.get("label") or name_in)
                ll = lab.strip().lower()
                if ll in {"current_player", "player_count"}:
                    return
                fields.append({
                    "name": label_out or name_in,
                    "label": lab,
                    "offset": self._to_int(ent.get("start", 0), 0),
                    "size": self._to_int(ent.get("length", ent.get("size", 1)), 1),
                    "encoding": ent.get("encoding") or None,
                    "endian": ent.get("endian") or None,
                    "scale": float(ent.get("scale") or 1.0),
                    "signed": bool(ent.get("signed", False)),
                    "mask": self._to_int(ent.get("mask", 0), 0),
                    "value_offset": self._to_int(ent.get("value_offset", ent.get("offset", 0)), 0)
                })

            add_gs("credits", "Credits")
            add_gs("current_ball", "current_ball")
            if "ball_count" in gs:
                add_gs("ball_count", "Balls Played")
            add_gs("tilted", "Tilted")
            add_gs("game_over", "Game Over")
            add_gs("extra_balls", "Extra Balls")
            add_gs("tilt_warnings", "Tilt Warnings")

        def _extract_nested(node, parent_label="", top_key=""):
            if isinstance(node, dict):
                if ("start" in node or "offset" in node):
                    label = str(node.get("label") or node.get("name") or parent_label)
                    if label and label.lower() not in {"current_player", "player_count"}:
                        if not any(f["label"] == label for f in fields):
                            fields.append({
                                "name": label,
                                "label": label,
                                "offset": self._to_int(node.get("offset", node.get("start", 0)), 0),
                                "size": self._to_int(node.get("size", node.get("length", 1)), 1),
                                "encoding": node.get("encoding") or None,
                                "endian": node.get("endian") or None,
                                "scale": float(node.get("scale") or 1.0),
                                "signed": bool(node.get("signed", False)),
                                "mask": self._to_int(node.get("mask", 0), 0),
                                "value_offset": self._to_int(node.get("value_offset", node.get("offset_adjust", 0)), 0),
                                "section": top_key
                            })
                else:
                    current_label = str(node.get("label") or node.get("name") or parent_label)
                    for k, v in node.items():
                        if isinstance(v, (dict, list)):
                            child_label = current_label
                            if current_label and k in {"score", "initials", "timestamp"}:
                                child_label = f"{current_label} {k.title()}"
                            _extract_nested(v, child_label, top_key if top_key else str(k))
            elif isinstance(node, list):
                for item in node:
                    _extract_nested(item, parent_label, top_key)

        _extract_nested(mj.get("audits", {}))
        _extract_nested(mj.get("adjustments", {}), top_key="adjustments")
        _extract_nested(mj.get("high_scores", []), top_key="high_scores")
        _extract_nested(mj.get("mode_champions", []), top_key="mode_champions")

        return fields
        
    def _try_load_map_for(self, rom: str) -> tuple[Optional[list[dict]], Optional[str]]:
        try:
            local1 = os.path.join(p_local_maps(self.cfg), rom + ".json")
            if os.path.exists(local1):
                fields = self.parse_map(load_json(local1, {}) or {})
                if fields:
                    return fields, local1

            local2 = os.path.join(p_local_maps(self.cfg), rom + ".map.json")
            if os.path.exists(local2):
                fields = self.parse_map(load_json(local2, {}) or {})
                if fields:
                    return fields, local2

            entry = (self.INDEX or {}).get(rom) or (self.INDEX or {}).get(rom.lower())
            if entry:
                rel = entry if isinstance(entry, str) else (entry.get("path") or entry.get("file"))
                if rel:
                    fields, p = self._load_map_from_local_rel(rel)
                    if fields:
                        return fields, p
        except Exception:
            pass
        return None, None

    def _resolve_map_from_index_then_family(self, rom: str) -> tuple[Optional[list[dict]], Optional[str], Optional[str]]:
        if not rom:
            return None, None, None

        fields, src = self._try_load_map_for(rom)
        if fields:
            return fields, src, rom

        for cand in self._all_rom_candidates(rom):
            if cand.lower() == rom.lower():
                continue
            try:
                f2, s2 = self._try_load_map_for(cand)
            except Exception:
                f2, s2 = None, None
            if f2:
                return f2, s2, cand

        return None, None, None

    def load_map_for_rom(self, rom: str):
        fields, src, matched = self._resolve_map_from_index_then_family(rom)

        try:
            if fields and matched and matched.lower() != (rom or "").lower():
                log(self.cfg, f"[MAP] family fallback: {rom} -> {matched}")
                no_map_set = getattr(self, "_no_map_logged_for_roms", None)
                if isinstance(no_map_set, set):
                    no_map_set.discard(str(rom).lower())
            elif not fields:
                key = str(rom or "").lower()
                no_map_set = getattr(self, "_no_map_logged_for_roms", None)
                if not isinstance(no_map_set, set):
                    no_map_set = set()
                    self._no_map_logged_for_roms = no_map_set
                if key and key not in no_map_set:
                    log(self.cfg, f"[MAP] no nvram map found for ROM '{rom}' (after family fallback)", "WARN")
                    no_map_set.add(key)
            else:
                no_map_set = getattr(self, "_no_map_logged_for_roms", None)
                if isinstance(no_map_set, set):
                    no_map_set.discard(str(rom).lower())
                logged = getattr(self, "_map_found_logged_roms", None)
                if not isinstance(logged, set):
                    logged = set()
                    self._map_found_logged_roms = logged
                if rom not in logged and self.current_rom and rom == self.current_rom:
                    log(self.cfg, f"[MAP] direct map found for ROM '{rom}' (source: {src})")
                    logged.add(rom)
        except Exception:
            pass

        return fields, src

    def _all_rom_candidates(self, rom: str) -> list[str]:
        name = (rom or "").strip()
        out: list[str] = []
        seen = set()
        def add(x: str):
            x = (x or "").strip()
            if not x:
                return
            xl = x.lower()
            if xl not in seen:
                seen.add(xl)
                out.append(x)
        add(name)
        rn = self.ROMNAMES or {}
        base_rom = rn.get(name) or rn.get(name.lower())
        if base_rom and base_rom != name:
            add(base_rom)
        for c in self._family_rom_candidates(name):
            add(c)
        return out
          
    def _load_map_from_local_rel(self, rel) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        if rel.startswith("maps/"):
            rel = rel[len("maps/"):]
        local = os.path.join(p_local_maps(self.cfg), rel.replace("/", os.sep))
        if not os.path.exists(local):
            try:
                url = f"{GITHUB_BASE}/maps/{rel.lstrip('/')}"
                mj = _fetch_json_url(url, timeout=25)
                save_json(local, mj)
            except Exception as e:
                log(self.cfg, f"Map fetch failed {rel}: {e}", "WARN")
                return None, None
        mj = load_json(local, {}) or {}
        return self.parse_map(mj), local

    def _family_rom_candidates(self, rom: str) -> list[str]:
        name = (rom or "").strip()
        nlow = name.lower()
        out: list[str] = []
        def add(x: str):
            x = (x or "").strip()
            if x and x.lower() != nlow and x not in out:
                out.append(x)
        m = re.match(r"^([a-z0-9]+?)[a-z]+$", nlow)
        if m:
            add(m.group(1))
        pre_us = nlow.split("_")[0]
        if pre_us and pre_us != nlow:
            add(pre_us)
        m2 = re.match(r"^([a-z]+[0-9]+)", nlow)
        if m2:
            add(m2.group(1))
        if pre_us and pre_us != nlow:
            m3 = re.match(r"^([a-z]+)_([0-9]+)", nlow)
            if m3:
                add(m3.group(1) + m3.group(2))
        family_prefixes = []
        if m2:
            family_prefixes.append(m2.group(1))  # afm113
        if pre_us:
            family_prefixes.append(pre_us)       # afm
        seen_fp = set()
        family_prefixes = [fp for fp in family_prefixes if not (fp in seen_fp or seen_fp.add(fp))]
        for fp in family_prefixes:
            for key in sorted(self.INDEX.keys()):
                kl = key.lower()
                if kl.startswith(fp) and kl != nlow:
                    add(key)
        return out

    @staticmethod
    def decode_bcd(raw: bytes) -> Optional[int]:
        digits = []
        for b in raw:
            hi, lo = (b >> 4) & 0xF, b & 0xF
            if hi > 9 or lo > 9:
                return None
            digits.append(str(hi))
            digits.append(str(lo))
        s = "".join(digits).lstrip("0")
        return int(s) if s else 0

    @staticmethod
    def decode_uint(raw: bytes, endian: Optional[str], signed: bool) -> int:
        e = "big" if (endian or "be") in ("be", "big") else "little"
        return int.from_bytes(raw, e, signed=bool(signed))

    @staticmethod
    def _plausibility_score(label, value):
        if value is None:
            return 1e12
        if value < 0:
            return 1e9
        caps = {"bumper": 200000, "spinner": 500000, "ramp": 200000, "ball": 100000, "extra": 10000}
        v = str(label).lower()
        cap = 500000
        for k, c in caps.items():
            if k in v:
                cap = c
                break
        penalty = (value - cap) * 10 if value > cap else 0
        return value + penalty

    def _decode_field_value(self, raw: bytes, fld: dict):
        offset = int(fld["offset"])
        size = int(fld["size"])
        enc = (fld.get("encoding") or "").lower() or None
        endian = fld.get("endian") or "be"
        signed = bool(fld.get("signed", False))
        scale = float(fld.get("scale", 1.0))
        if offset < 0 or offset + size > len(raw):
            return None
        window = raw[offset: offset + size]
        
        if enc in ("ch", "ascii", "string"):
            return "".join(chr(b) for b in window if 32 <= b <= 126).strip()

        if enc == "bcd":
            val = self.decode_bcd(window)
        elif enc in ("int", "uint", "sint"):
            val = self.decode_uint(window, endian, signed)
        elif enc == "bool":
            val = self.decode_uint(window, endian, False)
            val = 1 if int(val or 0) != 0 else 0
        else:
            val = self.decode_uint(window, endian, signed)
            
        if val is None:
            return None
        try:
            mask = int(fld.get("mask", 0) or 0)
            if mask:
                val = int(val) & mask
        except Exception:
            pass
        if scale != 1.0:
            try:
                val = int(int(val) * scale)
            except Exception:
                val = int(val)
        try:
            vo = int(fld.get("value_offset", 0) or 0)
            if vo:
                val = int(val) + vo
        except Exception:
            pass
        return int(val)

    def auto_fix_field(self, raw: bytes, base_enc, base_end, base_size, signed, label):
        sizes = sorted({int(base_size or 2), int(base_size or 2) + 1, int(base_size or 2) + 2})
        candidates = []
        for sz in sizes:
            if sz > len(raw):
                continue
            chunk = raw[:sz]
            encs = [base_enc] if base_enc else [None, "bcd"]
            if "bcd" not in encs:
                encs.append("bcd")
            for enc in encs:
                if enc == "bcd":
                    val = self.decode_bcd(chunk)
                    if val is not None:
                        candidates.append((val, {"encoding": "bcd", "endian": None, "size": sz}))
                else:
                    for e in ("be", "le"):
                        val = self.decode_uint(chunk, e, signed)
                        candidates.append((val, {"encoding": None, "endian": e, "size": sz}))
        best, cfg, best_score = None, None, 1e18
        for val, c in candidates:
            sc = self._plausibility_score(label, int(val))
            if sc < best_score:
                best, cfg, best_score = int(val), c, sc
        return best, cfg

    def _load_cached_layout(self, rom: str):
        return self._field_layout_cache.get(rom)

    def _store_cached_layout(self, rom: str, layout_fields: List[dict]):
        self._field_layout_cache[rom] = {
            "fields": layout_fields,
            "cache_time": time.time()
        }

    def read_nvram_audits_with_autofix(self, rom: str) -> Tuple[Dict[str, Any], List[str], bool]:
        if not rom:
            return {}, [], False
        # mtime-based NVRAM read cache – skip re-read if file unchanged
        nv_path = os.path.join(self.cfg.NVRAM_DIR, rom + ".nv")
        try:
            mt = os.path.getmtime(nv_path)
            if rom == self._nvram_cache_rom and mt == self._nvram_cache_mtime:
                return self._nvram_cache_result
        except Exception:
            pass
        if not os.path.exists(nv_path):
            return {}, [], False
        try:
            with open(nv_path, "rb") as f:
                raw = f.read()
        except Exception:
            return {}, [], False

        cached = self._load_cached_layout(rom)
        if cached:
            audits = {}
            notes: List[str] = []
            for fld in cached["fields"]:
                try:
                    label = fld["label"]
                    val = self._decode_field_value(raw, fld)
                    if val is None:
                        continue
                    audits[label] = val
                except Exception:
                    continue
            try:
                self._ensure_rom_specific(rom, audits)
            except Exception as e:
                log(self.cfg, f"[ROM_SPEC] ensure failed (cached path): {e}", "WARN")
            self._nvram_cache_rom = rom
            try:
                self._nvram_cache_mtime = os.path.getmtime(nv_path)
            except Exception:
                self._nvram_cache_mtime = 0.0
            self._nvram_cache_result = (audits, notes, False)
            return audits, notes, False

        fields, _ = self.load_map_for_rom(rom)
        if not fields:
            return {}, [], False

        audits, notes, fixed_fields = {}, [], []
        for fld in fields:
            try:
                label = (fld.get("label") or fld.get("name") or "field")
                offset = int(fld.get("offset", 0))
                size = int(fld.get("size", 2))
                enc = (fld.get("encoding") or "").lower() or None
                endian = (fld.get("endian") or "").lower() or None
                scale = float(fld.get("scale") or 1.0)
                signed = bool(fld.get("signed", False))
                if offset < 0 or offset + size > len(raw):
                    continue

                if enc in ("ch", "ascii", "string", "wpc_rtc"):
                    val = self._decode_field_value(raw, fld)
                    if val is not None:
                        audits[label] = val
                    fixed_fields.append(fld)
                    continue

                win_len = max(4, min(6, size + 2))
                window = raw[offset: min(len(raw), offset + win_len)]
                best, cfg = self.auto_fix_field(window, enc, endian, size, signed, label)
                val = int(best or 0)
                if scale != 1.0:
                    val = int(val * scale)
                audits[label] = val

                enc_new = (cfg or {}).get("encoding")
                end_new = (cfg or {}).get("endian")
                size_new = int((cfg or {}).get("size") or size)
                spec = {
                    "name": fld.get("name") or label,
                    "label": label,
                    "offset": offset,
                    "size": size_new,
                    "encoding": enc_new,
                    "endian": end_new,
                    "scale": scale,
                    "signed": signed,
                    "mask": self._to_int(fld.get("mask", 0), 0),
                    "value_offset": self._to_int(fld.get("value_offset", 0), 0),
                    "section": fld.get("section", ""),
                }
                fixed_fields.append(spec)

                if (enc_new or None) != (enc or None) or (end_new or None) != (endian or None) or size_new != size:
                    notes.append(f"[AUTO-FIX] {label}: enc {enc}->{enc_new}, endian {endian}->{end_new}, size {size}->{size_new}")
            except Exception as e:
                notes.append(f"[READ-WARN] {fld} -> {e}")

        self._store_cached_layout(rom, fixed_fields)
        try:
            self._ensure_rom_specific(rom, audits)
        except Exception as e:
            log(self.cfg, f"[ROM_SPEC] ensure failed: {e}", "WARN")

        self._nvram_cache_rom = rom
        try:
            self._nvram_cache_mtime = os.path.getmtime(nv_path)
        except Exception:
            self._nvram_cache_mtime = 0.0
        self._nvram_cache_result = (audits, notes, False)
        return audits, notes, False

    HIGHLIGHT_RULES = {
        "multiball": {"cat": "Power", "emoji": "💥", "label": "Multiball Frenzy", "type": "count"},
        "jackpot": {"cat": "Power", "emoji": "🎯", "label": "Jackpot Hunter", "type": "count"},
        "super_jackpot": {"cat": "Power", "emoji": "💎", "label": "Super Jackpot", "type": "count"},
        "triple_jackpot": {"cat": "Power", "emoji": "👑", "label": "Triple Jackpot", "type": "count"},
        "ball_save": {"cat": "Power", "emoji": "🛡️", "label": "Ball Saves", "type": "count"},
        "extra_ball": {"cat": "Power", "emoji": "➕", "label": "Extra Balls", "type": "count"},
        "special_award": {"cat": "Power", "emoji": "🎁", "label": "Special Awards", "type": "count"},
        "mode_completed": {"cat": "Power", "emoji": "🏆", "label": "Modes Completed", "type": "count"},
        "best_ball": {"cat": "Power", "emoji": "🔥", "label": "Best Ball", "type": "always"},
        "wizard_mode": {"cat": "Power", "emoji": "🧙", "label": "Wizard Mode", "type": "flag"},
        "loops": {"cat": "Precision", "emoji": "🔁", "label": "Loop Machine", "type": "count"},
        "spinner": {"cat": "Precision", "emoji": "🌀", "label": "Spinner Madness", "type": "count"},
        "combo": {"cat": "Precision", "emoji": "🎯", "label": "Combo King", "type": "count"},
        "drop_targets": {"cat": "Precision", "emoji": "🎯", "label": "Target Slayer", "type": "count"},
        "ramps": {"cat": "Precision", "emoji": "🏹", "label": "Rampage", "type": "count"},
        "orbit": {"cat": "Precision", "emoji": "🌌", "label": "Orbit Runner", "type": "count"},
        "skillshot": {"cat": "Precision", "emoji": "🎯", "label": "Skill Shot", "type": "count"},
        "super_skillshot": {"cat": "Precision", "emoji": "💥", "label": "Super Skill Shot", "type": "count"},
        "mode_starts": {"cat": "Precision", "emoji": "🎬", "label": "Modes Started", "type": "count"},
        "tilt_warnings": {"cat": "Fun", "emoji": "🛡️", "label": "Tilt Warnings", "type": "count"},
        "tilt": {"cat": "Fun", "emoji": "💀", "label": "Tilted", "type": "count"},
        "devils_number": {"cat": "Fun", "emoji": "👹", "label": "Devil’s Number", "type": "flag"},
        "match": {"cat": "Fun", "emoji": "🎲", "label": "Match Lucky", "type": "count"},
    }
    EVENT_KEYWORDS = {
        "super_jackpot": ["super jackpot", "super-jackpot", "super jp", "super jp."],
        "triple_jackpot": ["triple jackpot", "triple-jackpot", "triple jp", "triple jp."],
        "jackpot": ["jackpot", " jp", " jp.", "jackpots"],
        "multiball": ["multiball", "multi-ball", "multi ball", "multiballs", "m.b.", "mb start"],
        "ball_save": ["ball save", "ball saves"],
        "extra_ball": ["extra ball", "extra balls", "e.b.", "ex. ball"],
        "special_award": ["special"],
        "loops": ["loop", "loops"],
        "spinner": ["spinner"],
        "combo": ["combo", "combos"],
        "drop_targets": ["drop target", "targets"],
        "ramps": ["ramp", "ramps"],
        "orbit": ["orbit", "orbits"],
        "super_skillshot": ["super skill", "super skillshot"],
        "skillshot": ["skill shot", "skillshot"],
        "mode_completed": ["mode complete", "modes completed", "wave compl", "mission compl"],
        "mode_starts": ["mode start", "modes started", "wave start", "mission start", "atk. start"],
        "tilt_warnings": ["tilt warn", "tilt warning", "tilt warnings"],
        "tilt": [" tilt ", "tilted"],
        "match": ["match awards", "match lucky"],
        "wizard_mode": ["wizard mode", "wizard", "universe start", "universe won", "ruler of the universe"],
    }
    NOISE_REGEX = re.compile(r"(minutes on|play time|recent|total .*slot|paid cred|serv|factory|reset|cleared|burn|clock|coins|h\.s\.t\.d)", re.I)
    KEYWORD_FALLBACK = [
        "jackpot", "multiball", "skill", "mode", "lock", "locks", "extra", "ball save", "save", "wave",
        "combo", "martian", "video", "hurry", "random", "tilt", "wizard",
        "games started", "balls locked", "locks lit", "extra balls", "ball saves", "bonus", "mode start",
        "mode compl", "annihil", "martn.", "strobe"
    ]

    def _find_vpx_pid(self) -> Optional[int]:
        if not win32gui:
            return None
        hwnd = {"h": None}
        def _cb(h, _):
            if win32gui.IsWindowVisible(h):
                title = win32gui.GetWindowText(h)
                if title.startswith("Visual Pinball - ["):
                    hwnd["h"] = h
                    return False
            return True
        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            return None
        if not hwnd["h"]:
            return None
        pid = wintypes.DWORD(0)
        try:
            ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd["h"]), ctypes.byref(pid))
            return int(pid.value or 0) or None
        except Exception:
            return None

    def _vp_player_visible(self) -> bool:
        if not win32gui:
            return False
        now = time.time()
        cache = getattr(self, "_vp_visible_cache", None)
        if cache and (now - cache[0]) < 0.3:
            return cache[1]
        visible = {"flag": False}
        def _cb(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = (win32gui.GetWindowText(hwnd) or "").strip()
                    if title.startswith("Visual Pinball Player"):
                        visible["flag"] = True
                        return False
            except Exception:
                pass
            return True
        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            return False
        result = bool(visible["flag"])
        self._vp_visible_cache = (now, result)
        return result

    def _get_vp_player_rect(self) -> tuple[int, int, int, int] | None:
        if not win32gui:
            return None
        rect = {"ok": False, "x": 0, "y": 0, "w": 0, "h": 0}
        def _cb(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = (win32gui.GetWindowText(hwnd) or "").strip()
                if title.startswith("Visual Pinball Player"):
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    rect["ok"] = True
                    rect["x"], rect["y"] = int(left), int(top)
                    rect["w"], rect["h"] = int(right - left), int(bottom - top)
                    return False
            except Exception:
                pass
            return True
        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            return None
        if rect["ok"] and rect["w"] > 0 and rect["h"] > 0:
            return rect["x"], rect["y"], rect["w"], rect["h"]
        return None

    def _graceful_close_visual_pinball_player(self, wait_ms: int = 2500) -> bool:   
        try:
            import ctypes
            from ctypes import wintypes
            WM_CLOSE = 0x0010
            try:
                import win32gui
            except Exception:
                win32gui = None

            if not win32gui:
                return False
            pids = set()

            def _cb(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    title = win32gui.GetWindowText(hwnd) or ""
                    if title.startswith("Visual Pinball Player"):
                        try:
                            ctypes.windll.user32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0)
                        except Exception:
                            pass
                        pid = wintypes.DWORD(0)
                        ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
                        if pid.value:
                            pids.add(int(pid.value))
                except Exception:
                    pass
                return True
            win32gui.EnumWindows(_cb, None)
            if not pids:
                return True 
            k32 = ctypes.windll.kernel32
            SYNCHRONIZE = 0x00100000
            handles = []
            for pid in pids:
                try:
                    h = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
                    if h:
                        handles.append(h)
                except Exception:
                    pass
            if not handles:
                import time as _time
                _time.sleep(min(1.0, wait_ms / 1000.0))
            else:
                arr_type = wintypes.HANDLE * len(handles)
                arr = arr_type(*handles)
                k32.WaitForMultipleObjects(len(handles), arr, True, int(wait_ms))
                for h in handles:
                    try:
                        k32.CloseHandle(h)
                    except Exception:
                        pass
            try:
                still = []
                out = subprocess.check_output(
                    ["tasklist"], creationflags=0x08000000
                ).decode(errors="ignore").lower()
                for pid in pids:
                    if str(pid) in out:
                        still.append(pid)
                return len(still) == 0
            except Exception:
                return False
        except Exception:
            return False
            
    def _kill_vpx_process(self):
        try:
            import ctypes, subprocess, time
            from ctypes import wintypes
            try:
                self._alt_f4_visual_pinball_player(wait_ms=800)
            except Exception as e:
                log(self.cfg, f"[CHALLENGE] Alt+F4 path failed: {e}", "WARN")

            try:
                import win32gui, win32con
                def _cb(hwnd, _):
                    try:
                        if not win32gui.IsWindowVisible(hwnd):
                            return True
                        title = (win32gui.GetWindowText(hwnd) or "").strip()
                        if title.startswith("Visual Pinball Player") or title.startswith("Visual Pinball - ["):
                            try:
                                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    return True
                win32gui.EnumWindows(_cb, None)
            except Exception:
                pass

            try:
                deadline = time.time() + 1.8
                while time.time() < deadline:
                    out = subprocess.check_output(["tasklist"], creationflags=0x08000000).decode(errors="ignore").lower()
                    if "vpinball" not in out:
                        log(self.cfg, "[CHALLENGE] VPX closed via Alt+F4 + WM_CLOSE")
                        return
                    time.sleep(0.15)
            except Exception:
                pass

            try:
                for img in ("VPinballX64.exe", "VPinballX.exe", "VPinballX_GL.exe", "VPinball.exe"):
                    try:
                        subprocess.run(
                            ["taskkill", "/IM", img, "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x08000000
                        )
                    except Exception:
                        continue
            except Exception:
                pass
            log(self.cfg, "[CHALLENGE] WARNING: fallback hard kill executed", "WARN")
        except Exception as e:
            log(self.cfg, f"[CHALLENGE] _kill_vpx_process failed: {e}", "WARN")


    def start_timed_challenge(self, total_seconds: int = 190):
        try:
            if not self.game_active or not self.current_rom:
                log(self.cfg, "[CHALLENGE] timed: ignored (no active game)", "WARN")
                return
            ch = getattr(self, "challenge", {}) or {}
            if ch.get("active") and ch.get("kind") == "timed":
                log(self.cfg, "[CHALLENGE] timed already active – ignored duplicate")
                return
            warmup = 10
            total = max(1, int(total_seconds))
            countdown = max(1, total - warmup)
            ch.clear()
            ch.update({
                "active": True,
                "kind": "timed",
                "rom": self.current_rom,
                "table": self.current_table,
                "started_at": time.time(),
                "end_at": time.time() + total,
                "pending_kill_at": None,
                "suppress_big_overlay_once": True,
            })
            self.challenge = ch
            try:
                self.bridge.challenge_warmup_show.emit(warmup, "Timed challenge – warm-up")
                self.bridge.challenge_timer_start.emit(total)
            except Exception:
                pass
            log(self.cfg, f"[CHALLENGE] timed armed – warmup={warmup}s, countdown={countdown}s (total={total}s)")
        except Exception as e:
            log(self.cfg, f"[CHALLENGE] timed start failed: {e}", "WARN")

    def stop_timed_challenge(self):      
        ch = getattr(self, "challenge", {})
        if ch.get("kind") == "timed":
            ch["active"] = False
            self.challenge = ch
            try:
                self.bridge.challenge_timer_stop.emit()
            except Exception:
                pass
            log(self.cfg, "[CHALLENGE] timed stopped")

    def _flip_start_inputs(self):
        ini = get_vpx_ini_path_for_current_user()
        binds = parse_vpx_flipper_bindings(ini or "")
        self._flip["vk_left"] = int(binds.get("vk_left", 0) or 0)
        self._flip["vk_right"] = int(binds.get("vk_right", 0) or 0)
        self._flip["joy_left"] = int(binds.get("joy_left", 0) or 0)
        self._flip["joy_right"] = int(binds.get("joy_right", 0) or 0)
        try:
            kbs = []
            if self._flip["vk_left"]:
                kbs.append({"get_vk": lambda: self._flip["vk_left"], "on_press": lambda: self._flip_on_kbd_press("L")})
            if self._flip["vk_right"]:
                kbs.append({"get_vk": lambda: self._flip["vk_right"], "on_press": lambda: self._flip_on_kbd_press("R")})
            if kbs:
                self._flip_inputs["kbd"] = GlobalKeyHook(kbs)
                self._flip_inputs["kbd"].install()
                log(self.cfg, "[FLIP] Keyboard hook installed for flipper keys")
        except Exception as e:
            log(self.cfg, f"[FLIP] Keyboard hook failed: {e}", "WARN")
        try:
            self._flip_inputs["joy_running"] = True
            t = threading.Thread(target=self._flip_joy_poll_loop, daemon=True, name="FlipJoyPoll")
            self._flip_inputs["joy_thread"] = t
            t.start()
            log(self.cfg, "[FLIP] Joystick polling started for flipper buttons")
        except Exception as e:
            log(self.cfg, f"[FLIP] Joystick thread start failed: {e}", "WARN")

    def _flip_stop_inputs(self):
        try:
            self._flip_inputs["joy_running"] = False
        except Exception:
            pass
        try:
            if self._flip_inputs.get("kbd"):
                self._flip_inputs["kbd"].uninstall()
        except Exception:
            pass
        self._flip_inputs["kbd"] = None
        self._flip_inputs["joy_thread"] = None
        self._flip_inputs["joy_prev_masks"] = {}

    def _flip_on_kbd_press(self, side: str):
        try:
            self._flip_inc(side)
        except Exception:
            pass

    def _flip_joy_poll_loop(self):
        want_left = int(self._flip.get("joy_left", 0) or 0)
        want_right = int(self._flip.get("joy_right", 0) or 0)

        def bit_for(btn: int) -> int:
            return (1 << (int(btn) - 1)) if int(btn) > 0 else 0

        bit_left = bit_for(want_left)
        bit_right = bit_for(want_right)
        jix = JOYINFOEX()
        jix.dwSize = ctypes.sizeof(JOYINFOEX)
        jix.dwFlags = JOY_RETURNALL
        prev = self._flip_inputs.get("joy_prev_masks", {}) or {}
        while bool(self._flip_inputs.get("joy_running", False)):
            mask_all = 0
            for jid in range(16):
                try:
                    if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                        cur = int(jix.dwButtons)
                        old = int(prev.get(jid, 0))
                        newly = cur & ~old
                        prev[jid] = cur
                        if newly:
                            if bit_left and (newly & bit_left):
                                self._flip_inc("L")
                            if bit_right and (newly & bit_right):
                                self._flip_inc("R")
                except Exception:
                    continue
            self._flip_inputs["joy_prev_masks"] = prev
            time.sleep(0.04)
            
    def _flip_inc(self, side: str):
        if not self._flip.get("active"):
            return

        if side == "L":
            self._flip["left"] = int(self._flip.get("left", 0)) + 1
        elif side == "R":
            self._flip["right"] = int(self._flip.get("right", 0)) + 1
        left = int(self._flip.get("left", 0))
        right = int(self._flip.get("right", 0))
        total = left + right
        goal_total = int(self._flip.get("threshold", (self.cfg.OVERLAY or {}).get("flip_counter_goal_total", 400)))
        remaining = max(0, int(goal_total) - int(total))
        try:
            self.bridge.flip_counter_total_update.emit(int(total), int(remaining), int(goal_total))
        except Exception:
            try:
                self.bridge.flip_counter_update.emit(int(left), int(right), int(goal_total), 0)
            except Exception:
                pass
        if total >= int(goal_total):
            self._flip_check()

    def _flip_check(self):
        if not self._flip.get("active"):
            return
        try:
            audits_now = None
            try:
                audits_now, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
            except Exception:
                audits_now = None
            if audits_now:
                try:
                    self._last_audits_global = dict(audits_now)
                except Exception:
                    pass
                try:
                    duration_now = int(time.time() - (self.start_time or time.time()))
                    self.export_overlay_snapshot(audits_now, duration_now, on_demand=True)
                except Exception:
                    pass
                ch = getattr(self, "challenge", {}) or {}
                ch["prekill_end"] = dict(audits_now)
                self.challenge = ch
            try:
                self._kill_vpx_process()
            except Exception:
                pass

            ch = getattr(self, "challenge", {}) or {}
            ch["active"] = False
            ch["pending_kill_at"] = None
            ch["completed"] = True 
            self.challenge = ch
            log(self.cfg, "[CHALLENGE] flip finished – Alt+F4 + WM_CLOSE executed")
        except Exception as e:
            log(self.cfg, f"[FLIP] finalize failed: {e}", "WARN")
        finally:
            try:
                self.bridge.flip_counter_total_hide.emit()
            except Exception:
                try:
                    self.bridge.flip_counter_hide.emit()
                except Exception:
                    pass
            self._flip_stop_inputs()

    def start_flip_challenge(self, threshold: int = 500):
        try:
            if not self.game_active or not self.current_rom:
                log(self.cfg, "[CHALLENGE] flip: ignored (no active game)", "WARN")
                return

            ch = getattr(self, "challenge", {}) or {}
            if ch.get("active"):
                log(self.cfg, "[CHALLENGE] flip: another challenge already active – ignored", "WARN")
                return

            goal_total = int(threshold or (self.cfg.OVERLAY or {}).get("flip_counter_goal_total", 400))
            self._flip["active"] = True
            self._flip["threshold"] = max(1, int(goal_total))
            self._flip["left"] = 0
            self._flip["right"] = 0
            self._flip["started_at"] = time.time()

            # Single-player enforced
            try:
                if self.snapshot_mode:
                    self.snap_players_in_game = 1
                    self.snap_players_locked = True
                    self.current_player = 1
                    self._cp_rotate_lock_until = time.time() + 36000.0
            except Exception:
                pass

            ch.clear()
            ch.update({
                "active": True,
                "kind": "flip",
                "rom": self.current_rom,
                "table": self.current_table,
                "started_at": time.time(),
                "end_at": None,
                "pending_kill_at": None,
                "suppress_big_overlay_once": True,
                "threshold": int(goal_total), 
            })
            self.challenge = ch

            try:
                self.bridge.challenge_info_show.emit(
                    f"Flip Challenge – Total Goal: {int(goal_total)}", 4, "#FFFFFF"
                )
                self.bridge.challenge_speak.emit("Flip challenge armed")
            except Exception:
                pass

            try:
                self.bridge.flip_counter_total_show.emit(0, int(goal_total), int(goal_total))
            except Exception:
                try:
                    self.bridge.flip_counter_show.emit(0, 0, int(goal_total), 0)
                except Exception:
                    pass

            self._flip_start_inputs()
            log(self.cfg, f"[CHALLENGE] flip armed – total goal={int(goal_total)} (single-player enforced)")
        except Exception as e:
            log(self.cfg, f"[CHALLENGE] flip start failed: {e}", "WARN")

    def stop_flip_challenge(self):
        try:
            self._flip_stop_inputs()
        except Exception:
            pass
        try:
            self._flip["active"] = False
        except Exception:
            pass
        try:
            self.bridge.flip_counter_total_hide.emit()
        except Exception:
            try:
                self.bridge.flip_counter_hide.emit()
            except Exception:
                pass

        ch = getattr(self, "challenge", {}) or {}
        if ch.get("kind") == "flip":
            ch["active"] = False
            ch["pending_kill_at"] = None
            self.challenge = ch
            log(self.cfg, "[CHALLENGE] flip stopped")

    def start_heat_challenge(self):
        try:
            if not self.game_active or not self.current_rom:
                log(self.cfg, "[CHALLENGE] heat: ignored (no active game)", "WARN")
                return

            ch = getattr(self, "challenge", {}) or {}
            if ch.get("active"):
                log(self.cfg, "[CHALLENGE] heat: another challenge already active – ignored", "WARN")
                return

            # Single-player enforced
            try:
                if self.snapshot_mode:
                    self.snap_players_in_game = 1
                    self.snap_players_locked = True
                    self.current_player = 1
                    self._cp_rotate_lock_until = time.time() + 36000.0
            except Exception:
                pass

            ini = get_vpx_ini_path_for_current_user()
            binds = parse_vpx_flipper_bindings(ini or "")
            vk_left = int(binds.get("vk_left", 0) or 0) or VK_LSHIFT
            vk_right = int(binds.get("vk_right", 0) or 0) or VK_RSHIFT
            joy_left = int(binds.get("joy_left", 0) or 0)
            joy_right = int(binds.get("joy_right", 0) or 0)

            ch.clear()
            ch.update({
                "active": True,
                "kind": "heat",
                "rom": self.current_rom,
                "table": self.current_table,
                "started_at": time.time(),
                "end_at": None,
                "pending_kill_at": None,
                "suppress_big_overlay_once": True,
                "heat": 0.0,
                "heat_last_time": time.time(),
                "heat_prev_pressed": False,
                "vk_left": vk_left,
                "vk_right": vk_right,
                "joy_left": joy_left,
                "joy_right": joy_right,
                "joy_pressed": False,
            })
            self.challenge = ch

            try:
                self._heat_inputs["joy_running"] = True
                t = threading.Thread(target=self._heat_joy_poll_loop, daemon=True, name="HeatJoyPoll")
                self._heat_inputs["joy_thread"] = t
                t.start()
                log(self.cfg, "[HEAT] Joystick polling started for flipper held-state")
            except Exception as e:
                log(self.cfg, f"[HEAT] Joystick thread start failed: {e}", "WARN")

            try:
                self.bridge.challenge_info_show.emit("Heat Challenge – Don't overheat!", 4, "#FF7F00")
                self.bridge.challenge_speak.emit("Heat challenge armed")
            except Exception:
                pass

            try:
                self.bridge.heat_bar_show.emit()
            except Exception:
                pass

            log(self.cfg, "[CHALLENGE] heat armed – keep flippers cool!")
        except Exception as e:
            log(self.cfg, f"[CHALLENGE] heat start failed: {e}", "WARN")

    def stop_heat_challenge(self):
        try:
            self._heat_inputs["joy_running"] = False
        except Exception:
            pass
        try:
            t = self._heat_inputs.get("joy_thread")
            if t and t.is_alive():
                t.join(timeout=0.5)
        except Exception:
            pass
        self._heat_inputs["joy_thread"] = None
        ch = getattr(self, "challenge", {})
        if ch.get("kind") == "heat":
            ch["active"] = False
            self.challenge = ch
            try:
                self.bridge.heat_bar_hide.emit()
            except Exception:
                pass
            log(self.cfg, "[CHALLENGE] heat stopped")

    def _heat_joy_poll_loop(self):
        """Background thread: poll joystick held-state for the Heat Challenge."""
        try:
            ch = getattr(self, "challenge", {}) or {}
            want_left = int(ch.get("joy_left", 0) or 0)
            want_right = int(ch.get("joy_right", 0) or 0)

            def bit_for(btn: int) -> int:
                return (1 << (int(btn) - 1)) if int(btn) > 0 else 0

            bit_left = bit_for(want_left)
            bit_right = bit_for(want_right)

            if not bit_left and not bit_right:
                return  # no joystick bindings – nothing to poll

            jix = JOYINFOEX()
            jix.dwSize = ctypes.sizeof(JOYINFOEX)
            jix.dwFlags = JOY_RETURNALL

            while bool(self._heat_inputs.get("joy_running", False)):
                held = False
                for jid in range(16):
                    try:
                        if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                            cur = int(jix.dwButtons)
                            if (bit_left and (cur & bit_left)) or (bit_right and (cur & bit_right)):
                                held = True
                                break
                    except Exception:
                        continue
                ch = getattr(self, "challenge", {}) or {}
                if ch.get("kind") == "heat" and ch.get("active"):
                    ch["joy_pressed"] = held
                    self.challenge = ch
                else:
                    break
                time.sleep(0.1)
        except Exception as e:
            log(self.cfg, f"[HEAT] joy poll loop failed: {e}", "WARN")

    def _clear_challenge_state(self):
        try:
            self.bridge.flip_counter_total_hide.emit()
        except Exception:
            pass
        try:
            self.bridge.challenge_timer_stop.emit()
        except Exception:
            pass
        try:
            self.bridge.heat_bar_hide.emit()
        except Exception:
            pass
        try:
            self._flip_stop_inputs()
        except Exception:
            pass
        try:
            self._heat_inputs["joy_running"] = False
        except Exception:
            pass
            
        try:
            ch = getattr(self, "challenge", {})
            if isinstance(ch, dict):
                ch["active"] = False
                ch["pending_kill_at"] = None
        except Exception:
            pass
        try:
            self.challenge = {}
        except Exception:
            pass

    def _challenge_tick(self, audits: dict):
        try:
            ch = getattr(self, "challenge", {}) or {}
            if not ch or not ch.get("active"):
                return
            now = time.time()

            if not self._vp_player_visible():
                # Grace Period: erst nach 3s Unsichtbarkeit abbrechen
                grace_start = float(ch.get("_vpx_gone_since", 0.0))
                if grace_start == 0.0:
                    ch["_vpx_gone_since"] = now
                    self.challenge = ch
                    return  # noch NICHT abbrechen
                elif (now - grace_start) < 3.0:
                    return  # noch innerhalb Grace Period
                # Ab hier: VPX war > 3s nicht sichtbar → jetzt abbrechen
                log(self.cfg, "[CHALLENGE] VPX Player window gone for >3s. Aborting challenge.")
                kind = str(ch.get("kind", "")).lower()
                
                if kind == "timed":
                    self.stop_timed_challenge()
                elif kind == "flip":
                    self.stop_flip_challenge()
                elif kind == "heat":
                    self.stop_heat_challenge()
                else:
                    try:
                        self.bridge.challenge_timer_stop.emit()
                        self.bridge.flip_counter_total_hide.emit()
                    except Exception:
                        pass
                    
                ch["active"] = False
                ch["pending_kill_at"] = None
                ch.pop("_vpx_gone_since", None)
                self.challenge = ch
                return
            else:
                # VPX ist sichtbar → Grace-Timer zurücksetzen
                if ch.get("_vpx_gone_since"):
                    ch.pop("_vpx_gone_since", None)
                    self.challenge = ch

            if ch.get("kind") == "timed":
                end_at = float(ch.get("end_at", 0.0) or 0.0)
                if now >= end_at:
                    try:
                        time.sleep(0.15)
                    except Exception:
                        pass
                    audits_now = audits
                    try:
                        audits_now2, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                        if audits_now2:
                            audits_now = audits_now2
                    except Exception:
                        pass
                    if audits_now:
                        try:
                            self._last_audits_global = dict(audits_now)
                        except Exception:
                            pass
                        try:
                            duration_now = int(now - (self.start_time or now))
                            self.export_overlay_snapshot(audits_now, duration_now, on_demand=True)
                        except Exception:
                            pass
                        ch["prekill_end"] = dict(audits_now)
                        self.challenge = ch

                    # 3) VPX schließen
                    try:
                        self._kill_vpx_process()
                    except Exception:
                        pass

                    ch["active"] = False
                    ch["pending_kill_at"] = None
                    ch["completed"] = True 
                    self.challenge = ch
                    log(self.cfg, "[CHALLENGE] timed finished – Alt+F4 + WM_CLOSE executed")
                    return

            if ch.get("kind") == "heat":
                try:
                    now_t = time.time()
                    last_t = float(ch.get("heat_last_time", now_t) or now_t)
                    delta = min(now_t - last_t, 1.5)
                    ch["heat_last_time"] = now_t

                    vk_l = int(ch.get("vk_left", 0) or 0) or VK_LSHIFT
                    vk_r = int(ch.get("vk_right", 0) or 0) or VK_RSHIFT
                    try:
                        import ctypes as _ctypes
                        lshift = bool(_ctypes.windll.user32.GetAsyncKeyState(vk_l) & 0x8000)
                        rshift = bool(_ctypes.windll.user32.GetAsyncKeyState(vk_r) & 0x8000)
                    except Exception:
                        lshift = False
                        rshift = False

                    joy_held = bool(ch.get("joy_pressed", False))
                    pressed = lshift or rshift or joy_held
                    prev_pressed = bool(ch.get("heat_prev_pressed", False))
                    heat = float(ch.get("heat", 0.0) or 0.0)

                    if pressed:
                        heat += HEAT_HOLD_RATE * delta
                        if pressed and not prev_pressed:
                            heat += HEAT_PRESS_BURST
                    else:
                        heat -= HEAT_COOLDOWN_RATE * delta

                    heat = max(0.0, min(100.0, heat))
                    ch["heat"] = heat
                    ch["heat_prev_pressed"] = pressed
                    self.challenge = ch

                    try:
                        self.bridge.heat_bar_update.emit(int(heat))
                    except Exception:
                        pass

                    if heat >= 100.0:
                        log(self.cfg, "[CHALLENGE] heat reached 100% – killing VPX")
                        audits_now = audits
                        try:
                            audits_now2, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                            if audits_now2:
                                audits_now = audits_now2
                        except Exception:
                            pass
                        if audits_now:
                            try:
                                self._last_audits_global = dict(audits_now)
                            except Exception:
                                pass
                            try:
                                duration_now = int(now - (self.start_time or now))
                                self.export_overlay_snapshot(audits_now, duration_now, on_demand=True)
                            except Exception:
                                pass
                            ch["prekill_end"] = dict(audits_now)

                        try:
                            self._kill_vpx_process()
                        except Exception:
                            pass

                        ch["active"] = False
                        ch["pending_kill_at"] = None
                        ch["completed"] = True
                        self.challenge = ch

                        try:
                            self._heat_inputs["joy_running"] = False
                        except Exception:
                            pass
                        try:
                            self.bridge.heat_bar_hide.emit()
                        except Exception:
                            pass
                        log(self.cfg, "[CHALLENGE] heat finished – VPX killed")
                        return
                except Exception as e:
                    log(self.cfg, f"[CHALLENGE] heat tick failed: {e}", "WARN")

        except Exception as e:
            log(self.cfg, f"[CHALLENGE] tick failed: {e}", "WARN")
 
    def _challenge_best_final_score(self, end_audits: dict, pid: int = 1) -> int:
        # Single-player only
        try:
            v = int((end_audits or {}).get("P1 Score", 0) or 0)
            if v > 0:
                return v

            cache = getattr(self, "_last_audits_global", {}) or {}
            cv = int(cache.get("P1 Score", 0) or 0)
            if cv > 0:
                return cv

            balls = (self.ball_track or {}).get("balls", []) or []
            if balls:
                best_ball = max(balls, key=lambda b: (int(b.get("score", 0)), int(b.get("duration", 0))))
                bv = int(best_ball.get("score", 0) or 0)
                if bv > 0:
                    return bv
        except Exception:
            pass
        return 0

    def _inject_best_score_for_timed(self, end_audits: dict) -> dict:
        try:
            ch = getattr(self, "challenge", {}) or {}
            if str(ch.get("kind", "")).lower() != "timed":
                return dict(end_audits or {})

            ea = dict(end_audits or {})
            best = self._challenge_best_final_score(ea, pid=1)
            if best > 0:
                ea["P1 Score"] = best
                log(self.cfg, f"[CHALLENGE] timed: injected best P1 Score={best}")
            return ea
        except Exception:
            return dict(end_audits or {})
            
    def _challenge_record_result(self, kind: str, end_audits: dict, duration_sec: int):
        try:
            ch = getattr(self, "challenge", {}) or {}

            if not ch.get("completed", False):
                log(self.cfg, f"[CHALLENGE] Aborted early by player. Score NOT recorded/uploaded.")
                return

            now = time.time()
            started_at = float(ch.get("started_at", now))
            if (now - started_at) < 2.0:
                return

            if ch.get("result_recorded"):
                return

            rom = ch.get("rom") or self.current_rom or ""
            key = f"{rom}|{str(kind or '').lower()}"

            last = getattr(self, "_ch_result_recent", {"k": "", "ts": 0.0})
            if last.get("k") == key and (now - float(last.get("ts", 0.0))) < 5.0:
                return
            self._ch_result_recent = {"k": key, "ts": now}

            if not rom:
                return

            table = ch.get("table") or self.current_table or ""
            try:
                score = int(self._challenge_best_final_score(end_audits, pid=1) or 0)
            except Exception:
                score = 0

            payload = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": str(kind or ""),
                "rom": rom,
                "table": table,
                "duration_sec": int(duration_sec or 0),
                "score": int(score)
            }

            extra = {}
            if str(kind or "").lower() == "flip":
                tf = int(ch.get("threshold", 0))
                payload["target_flips"] = tf
                
                if tf <= 100: diff_name = "Pro"
                elif tf <= 200: diff_name = "Difficult"
                elif tf <= 300: diff_name = "Medium"
                elif tf <= 400: diff_name = "Easy"
                else: diff_name = f"{tf} Flips"
                
                payload["difficulty"] = diff_name
                extra = {"target_flips": tf, "difficulty": diff_name}

            out_dir = os.path.join(self.cfg.BASE, "session_stats", "challenges", "history")
            ensure_dir(out_dir)
            path = os.path.join(out_dir, f"{sanitize_filename(rom)}.json")
            hist = secure_load_json(path, {"results": []}) or {"results": []}
            hist.setdefault("results", []).append(payload)
            secure_save_json(path, hist)

            # Re-evaluate challenge_count achievements immediately after recording
            try:
                self._evaluate_challenge_count_achievements()
            except Exception:
                pass

            CloudSync.upload_score(self.cfg, kind, rom, int(score), extra, bridge=self.bridge)
            
            ch["result_recorded"] = True
            self.challenge = ch

            try:
                phrase = f"{str(kind or '').capitalize()} challenge finished."
                self.bridge.challenge_speak.emit(phrase)
            except Exception:
                pass
            try:
                score_txt = f"{int(score):,d}".replace(",", ".")
                if str(kind or "").lower() == "timed":
                    title = "TIME'S UP!"
                else:
                    title = "CHALLENGE COMPLETE!"
                self.bridge.challenge_info_show.emit(f"{title}<br>Score: {score_txt}", 8, "#FFFFFF")
            except Exception as e:
                log(self.cfg, f"[CHALLENGE] score overlay emit failed: {e}", "WARN")

            try:
                deadline = time.time() + 3.0
                while self._vp_player_visible() and time.time() < deadline:
                    time.sleep(0.1)
            except Exception:
                pass

        except Exception as e:
            log(self.cfg, f"[CHALLENGE] record result failed: {e}", "WARN")
                
    @staticmethod
    def _is_number(x):
        try:
            int(x)
            return True
        except Exception:
            return False

    @staticmethod
    def _extract_numeric(value):
        try:
            return int(value)
        except Exception:
            try:
                return int(float(value))
            except Exception:
                return 0

    @staticmethod
    def _player_field_filter(audits: dict, pid: int) -> dict:
        prefix = f"P{pid} "
        return {k: v for k, v in audits.items() if isinstance(k, str) and k.startswith(prefix)}

    def _find_score_from_audits(self, audits: dict, pid: Optional[int] = None) -> int:
        """
        SINGLE-PLAYER MODE: nur P1.
        """
        def _is_num(x):
            try:
                int(x)
                return True
            except Exception:
                return False

        val = (audits or {}).get("P1 Score")
        if _is_num(val):
            return int(val)

        val = (audits or {}).get("Score")
        return int(val) if _is_num(val) else 0

    def _build_events_from_deltas(self, deltas: dict) -> dict:
        events = {k: 0 for k in self.HIGHLIGHT_RULES.keys()}
        for label, val in deltas.items():
            if not isinstance(val, int) or val <= 0:
                continue
                
            l = str(label).lower()
            
            if any(noise in l for noise in ["max ", "count", "system", "percent", "boost", "allow", "level"]):
                continue

            # 2. Treffer sammeln
            matched_keys = []
            for key, words in self.EVENT_KEYWORDS.items():
                if any(w in l for w in words):
                    matched_keys.append(key)
            
            if "super_jackpot" in matched_keys and "jackpot" in matched_keys:
                matched_keys.remove("jackpot")
            if "triple_jackpot" in matched_keys and "jackpot" in matched_keys:
                matched_keys.remove("jackpot")
            if "super_skillshot" in matched_keys and "skillshot" in matched_keys:
                matched_keys.remove("skillshot")
            if "mode_completed" in matched_keys and "mode_starts" in matched_keys:
                matched_keys.remove("mode_starts")
                
            if "jackpot" in matched_keys and "multiball" in matched_keys:
                matched_keys.remove("multiball")
            if "super_jackpot" in matched_keys and "multiball" in matched_keys:
                matched_keys.remove("multiball")
                
            for key in matched_keys:
                events[key] = events.get(key, 0) + int(val)
                
        return events

    def _attribute_events(self, audits: dict) -> bool:
        if not audits or not getattr(self, "current_player", None) or (self.current_player not in self.players):
            try:
                self._last_global_for_player_attr = {
                    k: v for k, v in audits.items() if isinstance(k, str) and not k.startswith("P")
                }
            except Exception:
                pass
            return False
        try:
            prev = getattr(self, "_last_global_for_player_attr", {}) or {}
            cur_player = int(self.current_player or 1)
            player_rec = self.players.setdefault(cur_player, {
                "start_audits": self._player_field_filter(self.start_audits, cur_player) or {f"P{cur_player} Score": 0},
                "last_audits": self._player_field_filter(self.start_audits, cur_player) or {f"P{cur_player} Score": 0},
                "active_play_seconds": 0.0,
                "start_time": time.time(),
                "session_deltas": {},
                "event_counts": {},
            })
        except Exception:
            return False
            
        changed = False
        ignore_list = {"current_ball", "game over", "tilted", "credits", "player_count", "total plays", "1 player games", "2 player games", "3 player games", "4 player games"}
        
        for label, val_now in (audits or {}).items():
            if not isinstance(label, str):
                continue
            if label.startswith("P"):
                continue
            
            if is_excluded_field(label) or label.lower() in ignore_list:
                continue
                
            ll = label.lower()
            if "score" in ll:
                continue
            try:
                now_i = int(val_now or 0)
            except Exception:
                continue
            try:
                old_i = int(prev.get(label, 0) or 0)
            except Exception:
                old_i = 0
            diff = now_i - old_i
            if diff <= 0:
                continue
            try:
                sd = player_rec.setdefault("session_deltas", {})
                sd[label] = sd.get(label, 0) + int(diff)
            except Exception:
                pass
            for ev_key, words in (self.EVENT_KEYWORDS or {}).items():
                if any(w in ll for w in words):
                    try:
                        ec = player_rec.setdefault("event_counts", {})
                        ec[ev_key] = ec.get(ev_key, 0) + int(diff)
                        changed = True
                    except Exception:
                        pass
                    break
        try:
            self._last_global_for_player_attr = {
                k: v for k, v in audits.items() if isinstance(k, str) and not k.startswith("P")
            }
        except Exception:
            pass
        return bool(changed)

    def _icon(self, key: str, prefer_ascii: bool | None = None) -> str:
        ov = getattr(self.cfg, "OVERLAY", {}) or {}
        use_ascii = ov.get("prefer_ascii_icons", True) if prefer_ascii is None else bool(prefer_ascii)
        if use_ascii:
            ascii_map = {
                "best_ball": "[BB]",
                "wizard_mode": "[WZ]",
                "multiball": "[MB]",
                "jackpot": "[JP]",
                "super_jackpot": "[SJP]",
                "triple_jackpot": "[TJP]",
                "ball_save": "[BS]",
                "extra_ball": "[EB]",
                "special_award": "[SPC]",
                "mode_completed": "[MODE✓]",
                "loops": "[LOOP]",
                "spinner": "[SPIN]",
                "combo": "[COMBO]",
                "drop_targets": "[DT]",
                "ramps": "[RAMP]",
                "orbit": "[ORBIT]",
                "skillshot": "[SS]",
                "super_skillshot": "[SS+]",
                "mode_starts": "[MODE]",
                "tilt_warnings": "[TILT!]",
                "tilt": "[TILT]",
                "devils_number": "[666]",
                "match": "[MATCH]",
                "initials": "[INIT]",
            }
            return ascii_map.get(key, "[*]")
        else:
            emoji_map = {
                "best_ball": "🔥",
                "wizard_mode": "🧙",
                "multiball": "💥",
                "jackpot": "🎯",
                "super_jackpot": "💎",
                "triple_jackpot": "👑",
                "ball_save": "🛡️",
                "extra_ball": "➕",
                "special_award": "🎁",
                "mode_completed": "🏆",
                "loops": "🔁",
                "spinner": "🌀",
                "combo": "🎯",
                "drop_targets": "🎯",
                "ramps": "🏹",
                "orbit": "🌌",
                "skillshot": "🎯",
                "super_skillshot": "💥",
                "mode_starts": "🎬",
                "tilt_warnings": "🛡️",
                "tilt": "💀",
                "devils_number": "👹",
                "match": "🎲",
                "initials": "✍️",
            }
            return emoji_map.get(key, "•")
            
    def analyze_session(self, stats: dict) -> dict:
        events = stats.get("events", {}) or {}
        duration_sec = int(stats.get("duration_sec", 0) or 0)
        lines_per_cat = int((self.cfg.OVERLAY or {}).get("lines_per_category", 5))
        out = {"Power": [], "Precision": [], "Fun": []}
        buckets = {"Power": [], "Precision": [], "Fun": []}
        for key, rule in (self.HIGHLIGHT_RULES or {}).items():
            if key == "best_ball":
                continue
            cat = rule.get("cat", "Fun")
            typ = rule.get("type", "count")
            icon = self._icon(key)
            if typ == "count":
                val = int(events.get(key, 0) or 0)
                if val > 0:
                    base_w = 100
                    weight = base_w + val
                    label = f"{icon} {rule.get('label','')}".strip()
                    buckets[cat].append((weight, f"{label} – {val}"))
            elif typ == "flag":
                v = events.get(key, False)
                if isinstance(v, str):
                    v = v.strip()
                    if v:
                        buckets[cat].append((150, f"{icon} {rule.get('label','')} – {v}"))
                elif bool(v):
                    buckets[cat].append((150, f"{icon} {rule.get('label','')} – Yes"))
        for cat in ["Power", "Precision", "Fun"]:
            arr = sorted(buckets[cat], key=lambda x: x[0], reverse=True)[:max(1, lines_per_cat)]
            out[cat] = [s for _, s in arr]
        return out

    def _get_balls_played(self, audits: dict) -> Optional[int]:
        kl = {str(k).lower(): k for k in audits.keys()}
        for key in ["balls played", "games balls played", "total balls played"]:
            if key in kl:
                try:
                    return int(audits[kl[key]])
                except Exception:
                    pass
        for lk, orig in kl.items():
            if lk == "ball count" or ("ball" in lk and "count" in lk):
                try:
                    return int(audits[orig])
                except Exception:
                    continue
        for lk, orig in kl.items():
            if "balls" in lk and "played" in lk:
                try:
                    return int(audits[orig])
                except Exception:
                    continue
        return None

    def _nv_get_int_ci(self, audits: dict, label: str, default: int = 0) -> int:
        try:
            kl = {str(k).lower(): k for k in audits.keys()}
            key = kl.get(label.lower())
            if key is None:
                return int(default)
            return int(audits.get(key, default) or default)
        except Exception:
            return int(default)

    def _ball_reset(self, start_audits: dict):
        self.ball_track.update({
            "active": True,
            "index": 1,
            "start_time": time.time(),
            "current_pid": int(getattr(self, "current_player", 1) or 1),
            "score_base": self._find_score_from_audits(start_audits, pid=int(getattr(self, "current_player", 1) or 1)),
            "last_balls_played": self._get_balls_played(start_audits),
            "balls": []
        })

    def _ball_finalize_current(self, current_audits: dict, force: bool = False):
        if not self.ball_track.get("active"):
            return
        now = time.time()
        pid = int(self.ball_track.get("current_pid") or getattr(self, "current_player", 1) or 1)
        cur_score = self._find_score_from_audits(current_audits, pid=pid)
        base_score = int(self.ball_track.get("score_base", 0))
        ball_score = max(0, int(cur_score) - base_score)
        if ball_score == 0 and cur_score > 0 and base_score == 0:
            ball_score = cur_score
        duration = int(now - (self.ball_track.get("start_time") or now))
        if force or ball_score > 0 or duration > 0:
            entry = {
                "pid": pid,
                "num": self.ball_track.get("index", 1),
                "score": int(ball_score),
                "score_abs": int(cur_score),
                "duration": duration
            }
            self.ball_track["balls"].append(entry)
            self.ball_track["index"] = int(self.ball_track.get("index", 1)) + 1
            self.ball_track["start_time"] = now
            self.ball_track["score_base"] = cur_score

    def _ball_update(self, current_audits: dict):
        if not self.ball_track.get("active"):
            return
        cp = int(getattr(self, "current_player", 1) or 1)
        if cp != int(self.ball_track.get("current_pid") or cp):
            self._ball_finalize_current(current_audits, force=False)
            self.ball_track["current_pid"] = cp
            self.ball_track["start_time"] = time.time()
            self.ball_track["score_base"] = self._find_score_from_audits(current_audits, pid=cp)
        bp = self._get_balls_played(current_audits)
        if bp is None:
            return
        if self.ball_track.get("last_balls_played") is None:
            self.ball_track["last_balls_played"] = bp
            return
        if bp > int(self.ball_track.get("last_balls_played", 0)):
            self._ball_finalize_current(current_audits, force=False)
            self.ball_track["last_balls_played"] = bp
            cp = int(getattr(self, "current_player", 1) or 1)
            self.ball_track["current_pid"] = cp
            self.ball_track["start_time"] = time.time()
            self.ball_track["score_base"] = self._find_score_from_audits(current_audits, pid=cp)
  
    def _best_ball_for_player(self, pid: int):
        try:
            balls = [b for b in self.ball_track.get("balls", []) if int(b.get("pid", 0)) == pid]
            if not balls:
                return None
            return max(balls, key=lambda b: (int(b.get("score", 0)), int(b.get("duration", 0))))
        except Exception:
            return None

    def _init_player_snaps(self, start_audits: dict):
        self.players.clear()
        now = time.time()
        for pid in range(1, 5):
            snap = self._player_field_filter(start_audits, pid)
            if not snap:
                snap = {f"P{pid} Score": 0}
            self.players[pid] = {
                "start_audits": dict(snap),
                "last_audits": dict(snap),
                "active_play_seconds": 0.0,
                "start_time": now,
                "session_deltas": {},
                "event_counts": {},
            }
        self._last_tick_time = time.time()
        self._last_global_for_player_attr = {
            k: v for k, v in start_audits.items() if isinstance(k, str) and not k.startswith("P")
        }

    def _compute_session_deltas(self, start: dict, end: dict) -> dict:
        out = {}
        if not isinstance(end, dict):
            return out
        start = start or {}
        
        ignore_list = {"current_ball", "game over", "tilted", "credits", "player_count", "1 player games", "2 player games", "3 player games", "4 player games"}
        
        for k, ve in end.items():
            if not isinstance(k, str) or k.startswith("P"):
                continue
                
            if is_excluded_field(k) or k.lower() in ignore_list:
                continue
                
            try:
                s = int(start.get(k, 0) or 0)
                e = int(ve or 0)
            except Exception:
                continue
            d = e - s
            if d < 0:
                d = 0
            if d > 0:
                out[k] = d
        return out
        
    def _build_session_stats(self, start_audits: dict, end_audits: dict, duration_sec: int) -> dict:
        deltas = self._compute_session_deltas(start_audits, end_audits)
        events = self._build_events_from_deltas(deltas)
        score_final = self._find_score_from_audits(end_audits)
        events["devils_number"] = ("666" in str(score_final))
        initials = ""
        for k in end_audits.keys():
            if "initial" in str(k).lower():
                initials = str(end_audits.get(k) or "").strip()
                break
        events["initials"] = initials
        return {"score": score_final, "duration_sec": duration_sec, "events": events}

    def _collect_player_rules_for_rom(self, rom: str) -> list:
        rules = []
        rpath = os.path.join(p_rom_spec(self.cfg), f"{rom}.ach.json")
        if os.path.exists(rpath):
            data = load_json(rpath, {}) or {}
            if isinstance(data.get("rules"), list):
                rules.extend(data["rules"])

        out, seen = [], set()
        for r in rules:
            t = r.get("title") or "Achievement"
            if t in seen:
                continue
            seen.add(t)
            out.append(r)
        return out

    def _evaluate_player_session_achievements(self, pid: int, rom: str) -> tuple[list, list]:
        if pid not in self.players:
            return [], []
        player = self.players[pid]
        deltas = player.get("session_deltas", {}) or {}
        play_sec = int(player.get("active_play_seconds", 0.0))
        rules = self._collect_player_rules_for_rom(rom)

        state = self._ach_state_load()
        unlocked_session = state.get("session", {}).get(rom, [])
        def _get_title(e):
            if isinstance(e, dict): return str(e.get("title")).strip()
            return str(e).strip()
        already_unlocked = { _get_title(e) for e in unlocked_session if _get_title(e) }

        awarded = []
        retriggered = []
        for rule in rules:
            title = rule.get("title") or "Achievement"

            cond = rule.get("condition", {}) or {}
            rtype = cond.get("type")
            field = cond.get("field")
            is_met = False
            try:
                if rtype == "nvram_delta":
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 0))
                    if deltas.get(field, 0) >= need:
                        is_met = True

                elif rtype == "session_time":
                    min_s = int(cond.get("min_seconds", cond.get("min", 0)))
                    if play_sec >= min_s:
                        is_met = True
            except Exception:
                continue

            if is_met:
                if title.strip() in already_unlocked:
                    retriggered.append(title)
                else:
                    awarded.append(title)

        best_per_field = {}
        non_field_titles = []

        for title in awarded:
            parts = title.split("–", 1)
            if len(parts) > 1:
                right = parts[1].strip()
                m = re.match(r'^(.+?):\s*(\d+)$', right)
                if m:
                    field_name = m.group(1).strip()
                    tier_value = int(m.group(2))
                    if field_name not in best_per_field or tier_value > best_per_field[field_name][0]:
                        best_per_field[field_name] = (tier_value, title)
                    continue
            non_field_titles.append(title)

        out = non_field_titles + [t for _, t in sorted(best_per_field.values())]
        return out, retriggered

    def _augment_player_events_with_flags(self, score_abs: int, end_audits: dict, events: dict) -> dict:
        out = dict(events or {})
        try:
            if "666" in str(score_abs):
                out["devils_number"] = True
        except Exception:
            pass
        try:
            ini_key = None
            for k in (end_audits or {}).keys():
                if "initial" in str(k).lower():
                    ini_key = k
                    break
            if ini_key:
                val = str(end_audits.get(ini_key) or "").strip()
                if val:
                    out["initials"] = val
        except Exception:
            pass
        return out

    def export_overlay_snapshot(self, end_audits: dict, duration_sec: int, on_demand: bool = False) -> str:
        """
        SINGLE-PLAYER MODE:
        Exportiert nur Player-1-Highlightdatei.
        """
        try:
            if on_demand and (self.game_active or self._vp_player_visible()):
                return os.path.join(p_highlights(self.cfg), "activePlayers")
        except Exception:
            pass

        self._latest_end_audits_cache = dict(end_audits)
        try:
            self._ball_finalize_current(end_audits, force=True)
        except Exception as e:
            log(self.cfg, f"[BALL] finalize current failed: {e}", "WARN")

        active_dir = os.path.join(p_highlights(self.cfg), "activePlayers")
        ensure_dir(active_dir)

        pid = 1
        rec = self.players.get(pid, {})
        play_sec = int(rec.get("active_play_seconds", 0.0) or 0)
        deltas_for_player = rec.get("session_deltas", {}) or {}
        events_from_deltas = self._build_events_from_deltas(deltas_for_player)

        events_from_counts = {}
        try:
            for k, v in (rec.get("event_counts", {}) or {}).items():
                events_from_counts[k] = int(v or 0)
        except Exception:
            events_from_counts = {}

        merged_events = dict(events_from_deltas)
        for k, v in events_from_counts.items():
            merged_events[k] = max(int(merged_events.get(k, 0) or 0), int(v or 0))

        analysis_sec = play_sec if play_sec > 0 else int(duration_sec or 0)
        try:
            score_abs = int(self._find_score_from_audits(end_audits, pid=1) or 0)
        except Exception:
            score_abs = 0

        try:
            n_balls = self._player_balls_count(1)
            if isinstance(n_balls, int) and n_balls >= 0:
                if merged_events.get("skillshot", 0) > n_balls:
                    merged_events["skillshot"] = n_balls
        except Exception:
            pass

        events_aug = self._augment_player_events_with_flags(score_abs, end_audits, merged_events)
        pseudo_stats = {
            "score": score_abs,
            "duration_sec": analysis_sec,
            "events": events_aug,
        }

        try:
            highlights = self.analyze_session(pseudo_stats)
        except Exception as e:
            log(self.cfg, f"[HIGHLIGHTS] analyze_session failed for P1: {e}", "WARN")
            highlights = {"Power": [], "Precision": [], "Fun": []}

        # For no-ROM custom-events tables, include unlocked custom achievements in highlights
        if not self.current_rom and self.current_table:
            try:
                _custom_json = os.path.join(p_aweditor(self.cfg), f"{self.current_table}.custom.json")
                if os.path.isfile(_custom_json):
                    _state = self._ach_state_load()
                    _custom_ach = []
                    for _e in _state.get("session", {}).get(self.current_table, []):
                        _t = str(_e.get("title", "")).strip() if isinstance(_e, dict) else str(_e).strip()
                        if _t:
                            _custom_ach.append(_t)
                    if _custom_ach:
                        highlights.setdefault("Fun", [])
                        for _ca in _custom_ach:
                            if _ca not in highlights["Fun"]:
                                highlights["Fun"].append(_ca)
            except Exception as e:
                log(self.cfg, f"[CUSTOM_EVENTS] highlights inject failed: {e}", "WARN")

        _save_key = self.current_rom or self.current_table or "__no_session__"
        payload = {
            "player": 1,
            "rom": self.current_rom,
            "table": self.current_table,
            "playtime_sec": play_sec,
            "score": score_abs,
            "highlights": highlights,
        }

        # Cache the payload in memory so the overlay can read it without waiting for disk I/O
        self._overlay_snapshot_cache = payload

        save_json(os.path.join(active_dir, f"{_save_key}_P1.json"), payload)

        try:
            for pid_old in (2, 3, 4):
                fp = os.path.join(active_dir, f"{_save_key}_P{pid_old}.json")
                if os.path.isfile(fp):
                    os.remove(fp)
        except Exception:
            pass

        if not on_demand:
            log(self.cfg, "[EXPORT] session-only activePlayers written (P1 only)")
        return active_dir

    def _persist_and_toast_achievements(self, end_audits: dict, duration_sec: int):
        if not self.current_rom or not self._has_any_map(self.current_rom):
            log(self.cfg, f"[ACH] Evaluation skipped: No NVRAM map found for '{self.current_rom}'")
            return

        log(self.cfg, f"[ACH] Starting achievement evaluation for '{self.current_rom}'")

        # Track roms_played in achievements_state (Anti-Cheat protected)
        try:
            rom_state = self._ach_state_load()
            roms_played = list(rom_state.get("roms_played") or [])
            if self.current_rom not in roms_played:
                roms_played.append(self.current_rom)
                rom_state["roms_played"] = roms_played
                self._ach_state_save(rom_state)
                mfr = self._get_manufacturer_from_rom(self.current_rom)
                log(self.cfg, f"[GLOBAL_ACH] roms_played updated: {self.current_rom} (manufacturer: {mfr})")
        except Exception as e:
            log(self.cfg, f"[ACH] roms_played update failed: {e}", "WARN")

        try:
            _awarded, _all_global, awarded_meta, retriggered_meta = self._evaluate_achievements(
                self.current_rom, self.start_audits, end_audits, duration_sec
            )
        except Exception as e:
            log(self.cfg, f"[ACH] eval failed: {e}", "WARN")
            awarded_meta = []
            retriggered_meta = []

        log(self.cfg, f"[ACH] Evaluation result: {len(awarded_meta) if awarded_meta else 0} awarded, {len(retriggered_meta) if retriggered_meta else 0} retriggered")

        try:
            global_hits = [m for m in (awarded_meta or []) if (m.get("origin") == "global_achievements")]
            global_rt = [m for m in (retriggered_meta or []) if (m.get("origin") == "global_achievements")]
            if global_hits or global_rt:
                self._ach_record_unlocks("global", self.current_rom, global_hits, retriggered=global_rt)
            if global_hits:
                self._emit_achievement_toasts(global_hits, seconds=5, rom_override="")
        except Exception as e:
            log(self.cfg, f"[ACH] persist global failed: {e}", "WARN")

        try:
            session_hits, session_rt = self._evaluate_player_session_achievements(1, self.current_rom)
            if session_hits or session_rt:
                self._ach_record_unlocks("session", self.current_rom, list(session_hits), retriggered=list(session_rt))
            if session_hits:
                self._emit_achievement_toasts(session_hits, seconds=5)
        except Exception as e:
            log(self.cfg, f"[ACH] persist session failed: {e}", "WARN")

        try:
            if self.cfg.CLOUD_ENABLED:
                state = self._ach_state_load()
                player_name = self.cfg.OVERLAY.get("player_name", "Player")
                # Mark cloud upload done for cloud_pioneer badge
                state["cloud_upload_done"] = True
                self._ach_state_save(state)
                CloudSync.upload_full_achievements(self.cfg, state, player_name)
        except Exception as e:
            log(self.cfg, f"[ACH] full achievements upload failed: {e}", "WARN")

        # Evaluate badges
        try:
            state = self._ach_state_load()
            all_earned, newly_earned = evaluate_badges(state, self.cfg, watcher=self)
            if newly_earned:
                state["badges"] = all_earned
                self._ach_state_save(state)
                for badge_id in newly_earned:
                    try:
                        bdef = BADGE_LOOKUP.get(badge_id)
                        if bdef:
                            badge_title = f"{bdef[1]} {bdef[2]}"
                            self.bridge.ach_toast_show.emit(badge_title, "🏅 Badge Unlocked!", 6)
                    except Exception:
                        pass
                log(self.cfg, f"[BADGES] Newly earned: {newly_earned}")
        except Exception as e:
            log(self.cfg, f"[BADGES] evaluate_badges failed: {e}", "WARN")

    def _evaluate_achievements(self, rom: str, start_audits: dict, end_audits: dict, duration_sec: int) -> tuple[list[str], list[str], list[dict], list[dict]]:
        global_rules = self._collect_global_rules_for_rom(rom)

        deltas_ci = {}
        for k, _ve in (end_audits or {}).items():
            try:
                ve_i = int(self._nv_get_int_ci(end_audits, str(k), 0))
                vs_i = int(self._nv_get_int_ci(start_audits, str(k), 0))
                d = ve_i - vs_i
            except Exception:
                d = 0
            if d < 0:
                d = 0
            deltas_ci[str(k)] = d
        awarded = []
        awarded_meta = []
        retriggered_meta = []
        all_titles = []
        seen_all = set()
        seen_aw = set()
        seen_rt = set()

        # Pre-load state for rom_count / rom_complete_set / rom_multi_brand evaluation
        _rom_state_cache: dict | None = None
        _installed_roms_cache: dict = {}  # manufacturer -> set of ROM names
        _mfr_cache: dict = {}  # rom -> manufacturer (cached to avoid repeated regex)
        _rom_audits_cache: dict = {}  # rom -> audits dict (for nvram_tally cross-ROM reads)

        def _rom_state() -> dict:
            nonlocal _rom_state_cache
            if _rom_state_cache is None:
                _rom_state_cache = self._ach_state_load()
            return _rom_state_cache

        def _installed_roms(manufacturer: str) -> set:
            if manufacturer not in _installed_roms_cache:
                _installed_roms_cache[manufacturer] = self._scan_installed_roms_by_manufacturer(manufacturer)
            return _installed_roms_cache[manufacturer]

        def _mfr_for(r: str) -> str | None:
            if r not in _mfr_cache:
                _mfr_cache[r] = self._get_manufacturer_from_rom(r)
            return _mfr_cache[r]

        # Check for rom_complete_set revocations before evaluating rules
        try:
            state_pre = _rom_state()
            already_global = {
                str(e.get("title", "")).strip()
                for entries in state_pre.get("global", {}).values()
                for e in entries
            }
            roms_played_pre = set(state_pre.get("roms_played") or [])
            revoked = False
            for rule in global_rules:
                cond_pre = (rule.get("condition") or {}) if isinstance(rule, dict) else {}
                if str(cond_pre.get("type") or "").lower() != "rom_complete_set":
                    continue
                t_pre = (rule.get("title") or "Achievement").strip()
                if t_pre not in already_global:
                    continue
                mfr_pre = cond_pre.get("manufacturer", "")
                installed_pre = _installed_roms(mfr_pre)
                if not installed_pre:
                    continue
                new_tables = installed_pre - roms_played_pre
                if new_tables:
                    # Revoke: remove from global unlocks and reset tally
                    for r_key, entries in list(state_pre.get("global", {}).items()):
                        state_pre["global"][r_key] = [
                            e for e in entries
                            if str(e.get("title", "")).strip() != t_pre
                        ]
                    tally_bucket = state_pre.setdefault("global_tally", {})
                    if t_pre in tally_bucket:
                        del tally_bucket[t_pre]
                    revoked = True
                    log(self.cfg, f"[GLOBAL_ACH] rom_complete_set revoked for '{t_pre}': {len(new_tables)} new table(s) found ({', '.join(sorted(new_tables))})")
            if revoked:
                self._ach_state_save(state_pre)
                _rom_state_cache = state_pre
        except Exception:
            pass

        # Track whether the rom_state was modified by new-type rules so we save once at end
        _rom_state_dirty = False

        for rule in global_rules:
            title = (rule.get("title") or "Achievement").strip()
            if title not in seen_all:
                seen_all.add(title)
                all_titles.append(title)
            cond = (rule.get("condition") or {}) if isinstance(rule, dict) else {}
            rtype = str(cond.get("type") or "").lower()
            origin = rule.get("_origin") or ""
            try:
                if rtype == "nvram_overall":
                    field = cond.get("field")
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 1))
                    sv = int(self._nv_get_int_ci(start_audits, field, 0))
                    ev = int(self._nv_get_int_ci(end_audits, field, 0))
                    if sv < need <= ev:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title); seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                elif rtype == "nvram_delta":
                    field = cond.get("field")
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 1))
                    de = int(self._nv_get_int_ci(end_audits, field, 0))
                    ds = int(self._nv_get_int_ci(start_audits, field, 0))
                    d = de - ds
                    if d < 0:
                        d = 0
                    if d >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title); seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                elif rtype == "nvram_tally":
                    field = cond.get("field")
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 1))

                    state = self._ach_state_load()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }

                    delta = self._fuzzy_sum_deltas(deltas_ci, field)
                    roms_played = list(state.get("roms_played") or [])
                    abs_val = self._sum_field_across_all_roms(field, roms_played, _rom_audits_cache)

                    tally_bucket = state.setdefault("global_tally", {})
                    tally = tally_bucket.setdefault(title, {"progress": 0, "entries": []})

                    if not (title in already_global) and delta > 0:
                        now_iso = datetime.now(timezone.utc).isoformat()
                        tally["entries"].append({"rom": rom, "delta": delta, "ts": now_iso})
                        tally["progress"] += delta

                    effective_progress = max(int(tally["progress"]), abs_val)
                    tally["progress"] = effective_progress
                    self._ach_state_save(state)

                    if effective_progress >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})

                elif rtype == "rom_count":
                    state = _rom_state()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }
                    roms_played = list(state.get("roms_played") or [])
                    manufacturer = cond.get("manufacturer", "")
                    if manufacturer == "__any__":
                        min_brands = cond.get("min_brands")
                        if min_brands is not None:
                            # Count distinct brands represented in roms_played
                            brands = {_mfr_for(r) for r in roms_played}
                            brands.discard(None)
                            progress = len(brands)
                            need = int(min_brands)
                        else:
                            # Count total distinct ROMs
                            progress = len(set(roms_played))
                            need = int(cond.get("min", 1))
                    else:
                        played_for_mfr = {r for r in roms_played if _mfr_for(r) == manufacturer}
                        progress = len(played_for_mfr)
                        need = int(cond.get("min", 1))
                        if progress < need:
                            if self.cfg.LOG_CTRL:
                                log(self.cfg, f"[GLOBAL_ACH] rom_count '{title}': {progress}/{need} ({manufacturer}) – played={list(played_for_mfr)}, roms_played={roms_played}")
                    # Update tally for progress display (batched save at end)
                    state.setdefault("global_tally", {})[title] = {"progress": progress}
                    _rom_state_dirty = True
                    if progress >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                            log(self.cfg, f"[GLOBAL_ACH] rom_count triggered: '{title}' ({progress}/{need} tables played)")

                elif rtype == "rom_complete_set":
                    state = _rom_state()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }
                    manufacturer = cond.get("manufacturer", "")
                    roms_played = set(state.get("roms_played") or [])
                    installed = _installed_roms(manufacturer)
                    if not installed:
                        continue
                    installed_count = len(installed)
                    played_count = len(installed & roms_played)
                    # Store installed_count in global_tally for progress display (batched save at end)
                    state.setdefault("global_tally", {})[title] = {"progress": played_count, "installed_count": installed_count}
                    _rom_state_dirty = True
                    if played_count >= installed_count:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                            log(self.cfg, f"[GLOBAL_ACH] rom_complete_set triggered: '{title}' ({played_count}/{installed_count} tables played)")

                elif rtype == "rom_multi_brand":
                    state = _rom_state()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }
                    manufacturers = cond.get("manufacturers") or []
                    roms_played = list(state.get("roms_played") or [])
                    # Pre-compute set of manufacturers represented in roms_played
                    played_brands = {_mfr_for(r) for r in roms_played}
                    played_brands.discard(None)
                    brands_with_roms = {mfr for mfr in manufacturers if mfr in played_brands}
                    progress = len(brands_with_roms)
                    need = len(manufacturers)
                    # Update tally for progress display (batched save at end)
                    state.setdefault("global_tally", {})[title] = {"progress": progress, "installed_count": need}
                    _rom_state_dirty = True
                    if progress >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                            log(self.cfg, f"[GLOBAL_ACH] rom_multi_brand triggered: '{title}' ({progress}/{need} brands played)")

                elif rtype == "challenge_count":
                    state = _rom_state()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }
                    challenge_type = str(cond.get("challenge_type") or "").lower()
                    need = int(cond.get("min", 1))
                    count = self._count_completed_challenges(challenge_type)
                    # Update tally for progress display (batched save at end)
                    state.setdefault("global_tally", {})[title] = {"progress": count}
                    _rom_state_dirty = True
                    if count >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                            log(self.cfg, f"[GLOBAL_ACH] challenge_count triggered: '{title}' ({count}/{need} {challenge_type} challenges)")

            except Exception:
                continue

        # Batch-save the rom_state if any new-type rules updated it
        if _rom_state_dirty and _rom_state_cache is not None:
            try:
                self._ach_state_save(_rom_state_cache)
            except Exception:
                pass

        return awarded, all_titles, awarded_meta, retriggered_meta
        
    def _count_completed_challenges(self, challenge_type: str) -> int:
        """Count completed challenges of a given type from the challenge history folder."""
        count = 0
        history_dir = os.path.join(self.cfg.BASE, "session_stats", "challenges", "history")
        if not os.path.isdir(history_dir):
            return 0
        try:
            for fname in os.listdir(history_dir):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(history_dir, fname)
                try:
                    hist = secure_load_json(fpath, {}) or {}
                    for entry in (hist.get("results") or []):
                        if str(entry.get("kind") or "").lower() == challenge_type:
                            count += 1
                except Exception:
                    continue
        except Exception:
            pass
        return count

    def _evaluate_challenge_count_achievements(self):
        """Evaluate challenge_count global achievements and award any newly reached ones."""
        try:
            gp = f_global_ach(self.cfg)
            if not os.path.exists(gp):
                return
            data = load_json(gp, {}) or {}
            rules = [r for r in (data.get("rules") or []) if isinstance(r, dict)]
            state = self._ach_state_load()
            already_global = {
                str(e.get("title", "")).strip()
                for entries in state.get("global", {}).values()
                for e in entries
            }
            awarded_meta = []
            for rule in rules:
                cond = (rule.get("condition") or {}) if isinstance(rule, dict) else {}
                if str(cond.get("type") or "").lower() != "challenge_count":
                    continue
                title = (rule.get("title") or "").strip()
                if not title or title in already_global:
                    continue
                challenge_type = str(cond.get("challenge_type") or "").lower()
                need = int(cond.get("min", 1))
                count = self._count_completed_challenges(challenge_type)
                # Update tally for progress display
                state.setdefault("global_tally", {})[title] = {"progress": count}
                if count >= need:
                    awarded_meta.append({"title": title, "origin": "global_achievements"})
                    log(self.cfg, f"[GLOBAL_ACH] challenge_count triggered: '{title}' ({count}/{need} {challenge_type} challenges)")
            if awarded_meta:
                self._ach_record_unlocks("global", self.current_rom or "__challenge__", awarded_meta)
                self._ach_state_save(state)
                try:
                    self._emit_achievement_toasts(awarded_meta, seconds=5)
                except Exception:
                    pass
            else:
                self._ach_state_save(state)
        except Exception as e:
            log(self.cfg, f"[GLOBAL_ACH] challenge_count eval failed: {e}", "WARN")

    def _collect_global_rules_for_rom(self, rom: str) -> list[dict]:
        rules_out = []
        seen_titles = set()

        gp = f_global_ach(self.cfg)
        if os.path.exists(gp):
            data = load_json(gp, {}) or {}
            for r in (data.get("rules") or []):
                if not isinstance(r, dict):
                    continue
                if self._is_rule_global(r, origin="global_achievements"):
                    t = (r.get("title") or "Achievement").strip()
                    if t not in seen_titles:
                        seen_titles.add(t)
                        r2 = dict(r)
                        r2["_origin"] = "global_achievements"
                        rules_out.append(r2)
        rpath = os.path.join(p_rom_spec(self.cfg), f"{rom}.ach.json")
        if os.path.exists(rpath):
            data = load_json(rpath, {}) or {}
            for r in (data.get("rules") or []):
                if not isinstance(r, dict):
                    continue
                if self._is_rule_global(r, origin="rom_specific"):
                    t = (r.get("title") or "Achievement").strip()
                    if t not in seen_titles:
                        seen_titles.add(t)
                        r2 = dict(r)
                        r2["_origin"] = "rom_specific"
                        rules_out.append(r2)
        return rules_out     
        
    def _is_rule_global(self, rule: dict, origin: str) -> bool:
        scope = str(rule.get("scope") or "").strip().lower()
        return scope == "global"
 
    def _ensure_global_ach(self):
        path = f_global_ach(self.cfg)
        if os.path.exists(path):
            try:
                data = load_json(path, {}) or {}
                cur = data.get("rules") or []
                if isinstance(cur, list) and len(cur) >= 136:  # 150 nvram_tally + manufacturer + challenge rules (19 session_time rules removed)
                    # Force regeneration if any removed categories are still present
                    REMOVED_FIELDS = {"Drop Targets", "Spinner", "Orbits", "Modes Started", "Modes Completed"}
                    has_removed = any(
                        cond.get("field") in REMOVED_FIELDS
                        for r in cur
                        if isinstance(r, dict)
                        for cond in [r.get("condition", {})]
                        if isinstance(cond, dict) and cond.get("type") == "nvram_tally"
                    )
                    has_global_session_time = any(
                        isinstance(r, dict)
                        and isinstance(r.get("condition"), dict)
                        and r["condition"].get("type") == "session_time"
                        and str(r.get("scope", "")).lower() == "global"
                        for r in cur
                    )
                    if not has_removed and not has_global_session_time:
                        return
            except Exception:
                pass
        try:
            rules = self._generate_default_global_rules()
            save_json(path, {"rules": rules})
            log(self.cfg, f"global_achievements.json created/refreshed with {len(rules)} rules")
        except Exception as e:
            log(self.cfg, f"[GLOBAL_ACH] generation failed: {e}", "WARN")

    def _export_summary(self, end_audits: dict, duration_sec: int):
        from datetime import timezone
        summary_path = os.path.join(p_highlights(self.cfg), self.SUMMARY_FILENAME)
        try:
            best_ball = None
            try:
                balls = self.ball_track.get("balls", [])
                if balls:
                    best_ball = max(balls, key=lambda b: (int(b.get("score", 0)), int(b.get("duration", 0))))
            except Exception:
                best_ball = None

            try:
                global_deltas = self._compute_session_deltas(self.start_audits, end_audits)
            except Exception:
                global_deltas = {}

            p1 = self.players.get(1, {}) or {}
            players_out = [{
                "player": 1,
                "playtime_sec": int(p1.get("active_play_seconds", 0.0) or 0),
                "deltas": {k: v for k, v in (p1.get("session_deltas", {}) or {}).items() if "score" not in k.lower()},
                "events": p1.get("event_counts", {}) or {},
            }]

            payload = {
                "rom": self.current_rom,
                "table": self.current_table,
                "duration_sec": int(duration_sec or 0),
                "best_ball": best_ball,
                "players": players_out,
                "end_audits": end_audits,
                "global_deltas": global_deltas,
                "end_timestamp": datetime.now(timezone.utc).isoformat(),
                # Convenience fields for dashboard display
                "score": int(best_ball.get("score", 0)) if isinstance(best_ball, dict) else None,
            }

            save_json(summary_path, payload)

        except Exception as e:
            log(self.cfg, f"[SUMMARY] export failed: {e}", "WARN")


    def _ach_state_load(self) -> dict:
        p = f_achievements_state(self.cfg)
        return secure_load_json(p, {"global": {}, "session": {}})

    def _ach_state_save(self, state: dict):
        p = f_achievements_state(self.cfg)
        secure_save_json(p, state)

    # Maps known ROM prefixes to their manufacturer names.
    # Prefix matching is used: exact ROM name, then progressively shorter underscore-split segments,
    # then just the leading alphabetic characters.
    MANUFACTURER_MAP: dict[str, str] = {
        # Bally
        "afm": "Bally", "tom": "Bally", "mm": "Bally", "cv": "Bally",
        "cp": "Bally", "cftbl": "Bally", "pz": "Bally", "fh": "Bally", "bbb": "Bally",
        "trucksp": "Bally", "theatre": "Bally", "scared": "Bally", "eatpm": "Bally",
        "centaur": "Bally", "paragon": "Bally", "eightball": "Bally", "medusa": "Bally",
        "xenon": "Bally", "vector": "Bally", "embryon": "Bally", "speakesy": "Bally",
        "hotdoggin": "Bally", "mystic": "Bally", "fireball": "Bally", "frontier": "Bally",
        "harlem": "Bally", "ngndshkr": "Bally", "goldball": "Bally", "grandslm": "Bally",
        "kosteel": "Bally", "xsandos": "Bally", "blackblt": "Bally", "cybrnaut": "Bally",
        "beatclck": "Bally", "atlantis": "Bally", "spy_hunter": "Bally",
        "flashgdn": "Bally", "smman": "Bally",
        # Williams
        "ts": "Williams", "t2": "Williams", "ij": "Williams", "wcs": "Williams",
        "dw": "Williams", "br": "Williams", "rs": "Williams", "ft": "Williams",
        "gi": "Williams", "hurr": "Williams", "dm": "Williams",
        "tz": "Williams", "ww": "Williams", "taf": "Williams", "nf": "Williams",
        "bop": "Williams", "whirl": "Williams", "rollr": "Williams",
        "ss": "Williams", "taxi": "Williams", "pool": "Williams", "diner": "Williams",
        "jy": "Williams", "poto": "Williams", "esha": "Williams", "fire": "Williams",
        "sttng": "Williams", "jd": "Williams", "afv": "Williams", "cc": "Williams",
        "corv": "Williams", "dh": "Williams", "i500": "Williams", "jb": "Williams",
        "jm": "Williams", "ngg": "Williams", "pop": "Williams", "sc": "Williams",
        "sf2": "Williams", "tod": "Williams", "totan": "Williams", "wd": "Williams",
        "congo": "Williams", "dracula": "Williams", "mb": "Williams",
        "nbaf": "Williams", "cactjack": "Williams", "strik": "Williams",
        # Stern (modern)
        "godzilla": "Stern", "deadpool": "Stern", "got": "Stern", "munsters": "Stern",
        "aerosmith": "Stern", "lotr": "Stern", "sopranos": "Stern", "simpsons": "Stern",
        "metallica": "Stern", "twd": "Stern", "mustang": "Stern", "starwars": "Stern",
        "ghostbusters": "Stern", "batman66": "Stern", "kiss": "Stern", "wpt": "Stern",
        "elvis": "Stern", "ironman": "Stern", "xmen": "Stern", "transformers": "Stern",
        "avatar": "Stern", "tron": "Stern", "acdc": "Stern", "spider": "Stern",
        "avengers": "Stern", "nbafastbreak": "Stern",
        # Data East
        "lw3": "Data East", "tftc": "Data East", "hook": "Data East", "btmn": "Data East",
        "rab": "Data East", "gnr": "Data East", "stwr": "Data East", "tmnt": "Data East",
        "trek": "Data East", "simp": "Data East", "wwfr": "Data East", "mn_180": "Data East",
        "rctycn": "Data East", "aar": "Data East",
        # Gottlieb / Premier
        "cue": "Gottlieb", "teed": "Gottlieb", "sprbrk": "Gottlieb", "gladiatr": "Gottlieb",
        "shaq": "Gottlieb", "freddy": "Gottlieb", "wipe": "Gottlieb", "sfight2": "Gottlieb",
        "silvslug": "Gottlieb", "waterwld": "Gottlieb",
        # Sega
        "baywatch": "Sega", "mav": "Sega", "frankenstein": "Sega", "id4": "Sega",
        "twister": "Sega", "apollo": "Sega", "gw": "Sega", "jpark": "Sega",
        "swtril": "Sega", "spacejam": "Sega", "viprsega": "Sega", "ctcheese": "Sega",
        "goldeneye": "Sega", "xfiles": "Sega", "starship": "Sega", "harley": "Sega",
        "godzilla_sega": "Sega", "lostspc": "Sega",
        # Capcom
        "kp": "Capcom", "bbb_capcom": "Capcom", "pm": "Capcom", "flip": "Capcom",
        "bsv": "Capcom", "kingspin": "Capcom",
    }

    def _get_manufacturer_from_rom(self, rom: str) -> str | None:
        """Return the manufacturer for a given ROM name, e.g. 'Bally' for 'afm_113b'.

        Lookup order:
        1. MANUFACTURER_MAP — exact match on the lowercased ROM name.
        2. MANUFACTURER_MAP — progressively shorter underscore-delimited prefixes
           (e.g. 'afm_113b' → tries 'afm_113b', then 'afm').
        3. MANUFACTURER_MAP — leading alphabetic characters only
           (e.g. 'afm113' → 'afm').
        4. ROMNAMES regex fallback (legacy behaviour, skips bare version strings).
        """
        rom_lower = rom.lower()
        # 1. Exact match
        if rom_lower in self.MANUFACTURER_MAP:
            return self.MANUFACTURER_MAP[rom_lower]
        # 2. Progressively shorter underscore-split prefixes
        parts = rom_lower.split("_")
        for i in range(len(parts) - 1, 0, -1):
            prefix = "_".join(parts[:i])
            if prefix in self.MANUFACTURER_MAP:
                return self.MANUFACTURER_MAP[prefix]
        # 3. Leading alphabetic characters (strips trailing digits / underscores)
        base_m = re.match(r'^([a-z]+)(?=\d|_|$)', rom_lower)
        if base_m and base_m.group(1) in self.MANUFACTURER_MAP:
            return self.MANUFACTURER_MAP[base_m.group(1)]
        # 4. Fallback: parse ROMNAMES entry (e.g. "Table Name (Manufacturer)")
        name = self.ROMNAMES.get(rom) if hasattr(self, "ROMNAMES") else None
        if not name:
            return None
        m = re.search(r'\(([^)]+)\)$', str(name).strip())
        if m:
            val = m.group(1)
            # Ignore version strings like "1.13b / S1.1" — manufacturer names never start with a digit
            if re.match(r'^\d', val):
                return None
            return val
        return None

    def _resolve_emoji_for_rom(self, rom: str) -> str:
        """Automatically resolve a fitting emoji for a ROM based on table name keywords."""
        romnames = getattr(self, "ROMNAMES", {}) or {}
        table_name = romnames.get(rom, "").lower()

        # 1. Keyword match on table name (longest keywords first to prefer specific matches)
        for keyword, emoji in sorted(TABLE_EMOJI_KEYWORDS.items(),
                                     key=lambda x: len(x[0]), reverse=True):
            if keyword in table_name:
                return emoji

        # 2. Manufacturer fallback
        mfr = self._get_manufacturer_from_rom(rom)
        if mfr and mfr in MANUFACTURER_EMOJI:
            return MANUFACTURER_EMOJI[mfr]

        # 3. Generic pinball fallback
        return "🎯"

    # Keyword patterns for fuzzy matching of canonical global field names to ROM-specific NVRAM labels.
    # Each entry maps a canonical name to a list of keyword-tuples; ALL keywords in a tuple must be
    # present (case-insensitive) in an NVRAM field name for it to match.
    _NVRAM_TALLY_PATTERNS: dict[str, list[tuple[str, ...]]] = {
        "Ball Saves":       [("ball save",), ("ball saver",)],
        "Ramps Made":       [("ramp",)],
        # "jckpot" covers abbreviated spellings like "TROPICAL JCKPOTS"
        "Jackpots":         [("jackpot",), ("jckpot",)],
        "Total Multiballs": [("multiball",), ("multi-ball",)],
        "Loops":            [("loop",)],
        "Combos":           [("combo",)],
        "Extra Balls":      [("extra ball",)],
        "Games Started":    [("games started",), ("games played",)],
        "Balls Played":     [("balls played",), ("ball count",), ("total balls",)],
        # "MINUTES ON" is the standard WPC/Williams NVRAM field for cumulative play time in minutes.
        # "minute" covers abbreviated variants like "MINUTES ON" or "Minutes On".
        "MINUTES ON":       [("minutes on",), ("minute",)],
    }

    def _fuzzy_sum_deltas(self, deltas_ci: dict, canonical_field: str) -> int:
        """Return the sum of all deltas from fields in deltas_ci that match canonical_field.

        First tries an exact key lookup (current behaviour).  If that yields 0, falls back to
        keyword-based fuzzy matching so that ROM-specific labels like "Ball Saver Cnt" are
        matched by the canonical name "Ball Saves".
        """
        exact = int(deltas_ci.get(canonical_field, 0) or 0)
        if exact > 0:
            return exact

        patterns = self._NVRAM_TALLY_PATTERNS.get(canonical_field)
        if not patterns:
            return 0

        total = 0
        counted: set[str] = set()
        for k, v in deltas_ci.items():
            kl = k.lower()
            for kws in patterns:
                if all(kw in kl for kw in kws):
                    if k not in counted:
                        total += int(v or 0)
                        counted.add(k)
                    break
        return total

    def _fuzzy_sum_field(self, audits: dict, canonical_field: str) -> int:
        """Return the sum of all values in *audits* that fuzzy-match *canonical_field*.

        Uses the same _NVRAM_TALLY_PATTERNS as _fuzzy_sum_deltas so that
        ROM-specific labels like "MAIN M.B. JACKPOTS" are matched by "Jackpots".
        Falls back to exact case-insensitive lookup when no pattern entry exists.
        """
        patterns = self._NVRAM_TALLY_PATTERNS.get(canonical_field)
        if not patterns:
            return int(self._nv_get_int_ci(audits, canonical_field, 0))

        total = 0
        counted: set[str] = set()
        for k, v in audits.items():
            kl = k.lower()
            for kws in patterns:
                if all(kw in kl for kw in kws):
                    if k not in counted:
                        try:
                            total += int(v or 0)
                        except (ValueError, TypeError):
                            pass
                        counted.add(k)
                    break
        return total

    def _sum_field_across_all_roms(self, field: str, roms_played: list,
                                    _audits_cache: dict | None = None) -> int:
        """Sum *field* across all played ROMs using fuzzy NVRAM label matching.

        *roms_played* is the list of ROM names from the achievements state.
        *_audits_cache* is an optional dict keyed by ROM name that is populated on
        first use so repeated calls during one evaluation pass avoid re-reading files.
        """
        # Activate batch-logging mode so _ensure_rom_specific collects ROM_SPEC
        # creation events instead of logging them individually.
        batch_not_active = not isinstance(getattr(self, "_rom_spec_batch", None), list)
        if batch_not_active:
            self._rom_spec_batch = []
        total = 0
        try:
            for r in roms_played:
                try:
                    if _audits_cache is not None:
                        if r not in _audits_cache:
                            audits, _, _ = self.read_nvram_audits_with_autofix(r)
                            _audits_cache[r] = audits
                        audits = _audits_cache[r]
                    else:
                        audits, _, _ = self.read_nvram_audits_with_autofix(r)
                    if audits:
                        total += self._fuzzy_sum_field(audits, field)
                except Exception:
                    continue
        finally:
            if batch_not_active:
                collected = self._rom_spec_batch or []
                self._rom_spec_batch = None
                if collected:
                    seen: set[str] = set()
                    unique = []
                    for r, n in collected:
                        if r not in seen:
                            seen.add(r)
                            unique.append((r, n))
                    if unique:
                        summary = ", ".join(f"{r} ({n})" for r, n in unique)
                        log(self.cfg, f"[ROM_SPEC] Batch-generated achievement rules for {len(unique)} ROM(s): {summary}")
        return total

    def _scan_installed_roms_by_manufacturer(self, manufacturer: str) -> set:
        """Scan TABLES_DIR for .vpx files and return ROM names matching the given manufacturer.
        Only includes ROMs that have an available NVRAM map (consistent with roms_played tracking).
        If manufacturer is '__any__', return all map-having ROMs found regardless of manufacturer.
        Results are cached after the first scan to avoid repeated blocking filesystem walks."""
        # Return from cache if available
        if self._installed_roms_scan_done:
            if manufacturer == "__any__":
                return set(self._installed_roms_scan_cache.get("__all_with_map__", set()))
            return set(self._installed_roms_scan_cache.get(manufacturer, set()))

        # First call: do the full scan ONCE and cache ALL results
        result_all: set = set()  # all ROMs with maps
        result_by_mfr: dict = {}
        tables_dir = getattr(self.cfg, "TABLES_DIR", None)
        if tables_dir and os.path.isdir(tables_dir):
            skipped = 0
            vpxtool_warn = 0
            for root, _dirs, files in os.walk(tables_dir):
                for fname in files:
                    if not fname.lower().endswith(".vpx"):
                        continue
                    vpx_path = os.path.join(root, fname)
                    try:
                        rom = run_vpxtool_get_rom(self.cfg, vpx_path, suppress_warn=True)
                    except Exception:
                        rom = None
                    if not rom:
                        vpxtool_warn += 1
                        continue
                    # Only include ROMs that have an NVRAM map — consistent with roms_played tracking
                    # (roms_played is only updated when _has_any_map() is True)
                    if not self._has_any_map(rom):
                        skipped += 1
                        continue
                    result_all.add(rom)
                    mfr = self._get_manufacturer_from_rom(rom)
                    if mfr:
                        result_by_mfr.setdefault(mfr, set()).add(rom)
                    self._rom_emoji_cache[rom] = self._resolve_emoji_for_rom(rom)
            if skipped > 0 or vpxtool_warn > 0:
                log(self.cfg, f"[SCAN] Table scan complete: {len(result_all)} ROMs with maps, {skipped} skipped (no map), {vpxtool_warn} vpxtool warnings", "INFO")

        self._installed_roms_scan_cache = dict(result_by_mfr)
        self._installed_roms_scan_cache["__all_with_map__"] = result_all
        self._installed_roms_scan_done = True

        if manufacturer == "__any__":
            return set(result_all)
        return set(result_by_mfr.get(manufacturer, set()))

    def _append_nvram_dump_block(self, lines: list[str], audits: dict):
        if not isinstance(audits, dict) or not audits:
            lines.append("(none)")
            return

        for k in sorted(audits.keys(), key=lambda x: str(x).lower()):
            try:
                label = str(k)
            except Exception:
                label = repr(k)

            try:
                value = audits.get(k, "")
            except Exception:
                value = ""

            try:
                value_txt = str(value)
            except Exception:
                value_txt = repr(value)

            lines.append(f"{label:<30} {value_txt}")

    def _ach_record_unlocks(self, kind: str, rom: str, titles: list, retriggered: list = None, skip_cloud: bool = False):
        if not rom or (not titles and not retriggered):
            return
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        state = self._ach_state_load()
        old_level_info = compute_player_level(state)
        bucket = state.setdefault(kind, {})
        storage_key = "__global__" if kind == "global" else rom
        lst = bucket.setdefault(storage_key, [])

        def _entry_title(e):
            try:
                return str(e.get("title")).strip()
            except Exception:
                return str(e).strip()

        # Build a mapping of existing entries by title to easily find and update them
        existing_by_title = {}
        for e in lst:
            if isinstance(e, dict):
                t_val = _entry_title(e)
                if t_val:
                    existing_by_title[t_val] = e

        _current_vps_id = ""
        try:
            from ui_vps import _load_vps_mapping
            _vps_mapping = _load_vps_mapping(self.cfg)
            _current_vps_id = (_vps_mapping.get(rom) or "").strip()
        except Exception:
            pass

        added = 0
        updated = 0
        for t in titles:
            if isinstance(t, dict):
                title = str(t.get("title", "")).strip()
                origin = t.get("origin")
            else:
                title = str(t).strip()
                origin = None

            if not title:
                continue

            if title in existing_by_title:
                # Already unlocked – skip; backfill only happens on re-trigger (see below)
                continue

            # New achievement
            entry = {"title": title, "ts": now_iso}
            if origin:
                entry["origin"] = str(origin)
            if _current_vps_id:
                entry["vps_id"] = _current_vps_id
            lst.append(entry)
            existing_by_title[title] = entry
            added += 1

        # Process retriggered achievements: backfill vps_id only if the entry has none (freeze semantics)
        for t in (retriggered or []):
            if isinstance(t, dict):
                title = str(t.get("title", "")).strip()
            else:
                title = str(t).strip()
            if not title:
                continue
            if title in existing_by_title:
                existing_entry = existing_by_title[title]
                stored_vps = (existing_entry.get("vps_id") or "").strip()
                if _current_vps_id and not stored_vps:
                    existing_entry["vps_id"] = _current_vps_id
                    updated += 1
                    try:
                        toast_title = f"{title}\n{rom}\nVPS-ID linked"
                        self.bridge.ach_toast_show.emit(toast_title, rom, 5)
                    except Exception:
                        pass

        if added or updated:
            self._ach_state_save(state)
            if added:
                new_level_info = compute_player_level(state)
                if new_level_info["level"] > old_level_info["level"]:
                    try:
                        self.bridge.level_up_show.emit(new_level_info["name"], new_level_info["level"])
                    except Exception:
                        pass
            try:
                if getattr(self, "bridge", None) and hasattr(self.bridge, "achievements_updated"):
                    self.bridge.achievements_updated.emit()
            except Exception:
                pass
            try:
                if not skip_cloud and self.cfg.CLOUD_ENABLED:
                    player_name = self.cfg.OVERLAY.get("player_name", "Player")
                    CloudSync.upload_full_achievements(self.cfg, state, player_name)
            except Exception:
                pass
  
    def _emit_achievement_toasts(self, titles, seconds: int = 5, rom_override: str | None = None):
        try:
            already_shown = getattr(self, "_toasted_titles", set())
            for t in titles or []:
                if isinstance(t, dict):
                    title = str(t.get("title", "")).strip()
                else:
                    title = str(t).strip()

                title = title.replace(" (Session)", "").replace(" (Global)", "")

                if title and title not in already_shown:
                    already_shown.add(title)
                    rom_value = rom_override if rom_override is not None else (self.current_rom or "")
                    log(self.cfg, f"[ACH] Emitting toast: '{title}' rom='{rom_value}'")
                    try:
                        self.bridge.ach_toast_show.emit(title, rom_value, int(seconds))
                    except Exception as e:
                        log(self.cfg, f"[ACH] Toast emit failed: {e}", "WARN")
            self._toasted_titles = already_shown
        except Exception as e:
            log(self.cfg, f"[ACH] _emit_achievement_toasts error: {e}", "WARN")
  
    def _on_session_end_record_achievements(self, rom: str, session_titles: list, global_titles: list):
        try:
            session_titles = session_titles or []
            global_titles = global_titles or []
            self._ach_record_unlocks("session", rom, session_titles)
            self._ach_record_unlocks("global", rom, global_titles)
            out = []
            for t in session_titles:
                if isinstance(t, dict):
                    out.append(t)
                else:
                    out.append({"title": str(t), "origin": "session"})
            for t in global_titles:
                if isinstance(t, dict):
                    out.append(t)
                else:
                    out.append({"title": str(t), "origin": "global"})
            self.last_unlocked_achievements = out
        except Exception:
            pass
  
    def on_session_start(self, table_or_rom: str, is_rom: bool = False):
        if is_rom:
            self.current_rom = table_or_rom
            self.current_table = f"(ROM only: {self.current_rom})"
            self._table_load_ts = time.time()
        else:
            self.current_table = table_or_rom

        try:
            cands = self._all_rom_candidates(self.current_rom or "")
            log(self.cfg, f"[ROM] candidates for {self.current_rom}: {cands[:12]}")
        except Exception:
            pass

        self.start_time = time.time()
        self.game_active = True
        self.players.clear()
        self._toasted_titles = set()

        self.start_audits, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)

        try:
            self._ensure_rom_specific(self.current_rom, self.start_audits)
        except Exception as e:
            log(self.cfg, f"[ROM_SPEC] generation failed: {e}", "WARN")

        self._last_audits_global = dict(self.start_audits)

        try:
            self._ball_reset(self.start_audits)
        except Exception as e:
            log(self.cfg, f"[BALL] reset failed: {e}", "WARN")

    def _ensure_singleplayer_min_playtime(self, nplayers: int, duration_sec: int) -> None:
        try:
            if int(nplayers) == 1:
                cur = int(self.players.get(1, {}).get("active_play_seconds") or 0)
                if cur < int(duration_sec):
                    self.players.setdefault(1, {})["active_play_seconds"] = int(duration_sec)
        except Exception:
            pass
           
    def on_session_end(self):
        if not self.game_active:
            return

        ch = getattr(self, "challenge", {}) or {}
        is_challenge = str(ch.get("kind", "")).lower() in ("timed", "oneball", "flip", "heat")
        ch_aborted = is_challenge and not ch.get("completed", False)

        if is_challenge:
            try:
                if hasattr(self.bridge, "flip_counter_total_hide"):
                    self.bridge.flip_counter_total_hide.emit()
            except Exception: pass
            
            try:
                if hasattr(self.bridge, "challenge_timer_stop"):
                    self.bridge.challenge_timer_stop.emit() 
            except Exception: pass
            
            try:
                if hasattr(self, "_flip_stop_inputs"):
                    self._flip_stop_inputs()
            except Exception: pass

            try:
                self._heat_inputs["joy_running"] = False
            except Exception: pass

            try:
                if hasattr(self.bridge, "heat_bar_hide"):
                    self.bridge.heat_bar_hide.emit()
            except Exception: pass
            
            if ch_aborted:
                try:
                    self.bridge.challenge_info_show.emit("Challenge Aborted!", 3, "#FF3B30")
                except Exception: pass

        # 2. DELAY NUR BEI ERFOLG (Verhindert langes Warten beim manuellen Abbruch)
        if is_challenge and not ch_aborted:
            try:
                delay_ms = int((self.cfg.OVERLAY or {}).get("ch_finalize_delay_ms", 2000))
                if delay_ms > 0:
                    time.sleep(max(0.0, delay_ms / 1000.0))
            except Exception:
                pass

        try:
            end_ts = time.time()
            duration_sec = int(end_ts - (self.start_time or end_ts))
            duration_str = str(timedelta(seconds=duration_sec))
            pre = ch.get("prekill_end") if isinstance(ch.get("prekill_end", None), dict) else None
            self._session_rom_for_notif = self.current_rom

            if is_challenge:
                try:
                    end_audits, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                except Exception as e:
                    log(self.cfg, f"[END] read end audits (challenge) failed: {e}", "WARN")
                    end_audits = {}
                if not end_audits:
                    end_audits = dict(pre) if pre else dict(self._last_audits_global)
            else:
                if pre:
                    end_audits = dict(pre)
                else:
                    try:
                        end_audits, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                        if not end_audits:
                            raise RuntimeError("Empty end_audits")
                    except Exception as e:
                        log(self.cfg, f"[END] read end audits failed, using last known: {e}", "WARN")
                        end_audits = dict(self._last_audits_global)

            nplayers = 1
            seg_deltas = {1: self._compute_session_deltas(self.start_audits, end_audits)}
            self.players.setdefault(1, {
                "start_audits": self._player_field_filter(self.start_audits, 1) or {"P1 Score": 0},
                "last_audits": self._player_field_filter(end_audits, 1) or {"P1 Score": 0},
                "active_play_seconds": float(self.players.get(1, {}).get("active_play_seconds", 0.0)),
                "start_time": self.players.get(1, {}).get("start_time", time.time()),
                "session_deltas": {},
                "event_counts": self.players.get(1, {}).get("event_counts", {}),
            })
            self.players[1]["session_deltas"] = dict(seg_deltas.get(1, {}) or {})
            self.players[1]["active_play_seconds"] = max(
                int(self.players[1].get("active_play_seconds", 0) or 0),
                int(duration_sec)
            )

            if is_challenge:
                log(self.cfg, f"[SESSION END] Challenge finished: rom={self.current_rom}, duration={duration_str}. Skipping NVRAM dumps and regular achievements.")
                try:
                    if str(ch.get("kind", "")).lower() == "timed":
                        end_audits = self._inject_best_score_for_timed(end_audits)
                    if not ch.get("result_recorded", False):
                        self._challenge_record_result(str(ch.get("kind")), end_audits, duration_sec)
                except Exception as e:
                    log(self.cfg, f"[CHALLENGE] result finalize failed: {e}", "WARN")
            else:
                log(self.cfg, f"[SESSION END] Normal session finished: rom={self.current_rom}, duration={duration_str}")
                try:
                    self._export_summary(end_audits, duration_sec)
                except Exception as e:
                    log(self.cfg, f"[SUMMARY] export failed: {e}", "WARN")

                try:
                    self.export_overlay_snapshot(end_audits, duration_sec)
                except Exception as e:
                    log(self.cfg, f"[OVERLAY] export snapshot failed: {e}", "WARN")

                # Fire the overlay signal immediately after the snapshot data is ready,
                # before slow achievement persistence and cloud uploads.
                try:
                    if (self.cfg.OVERLAY or {}).get("auto_show_on_end", True):
                        if self.current_rom and self._has_any_map(self.current_rom):
                            self.bridge.overlay_show.emit()
                        elif not self.current_rom and self.current_table:
                            # No-ROM table: show overlay if custom events are configured
                            _custom_json = os.path.join(
                                p_aweditor(self.cfg), f"{self.current_table}.custom.json"
                            )
                            if os.path.isfile(_custom_json):
                                self.bridge.overlay_show.emit()
                            else:
                                log(self.cfg, f"[OVERLAY] Skipped auto-show: no NVRAM map and no custom events for '{self.current_table}'")
                        else:
                            log(self.cfg, f"[OVERLAY] Skipped auto-show because no NVRAM map exists for '{self.current_rom}'")
                except Exception as e:
                    log(self.cfg, f"[OVERLAY] auto-show emit failed: {e}", "WARN")

                try:
                    self._persist_and_toast_achievements(end_audits, duration_sec)
                except Exception as e:
                    log(self.cfg, f"[ACHIEVEMENTS] persist/toast failed: {e}", "WARN")

                if self.current_rom and self._has_any_map(self.current_rom):
                    try:
                        s_rules = self._collect_player_rules_for_rom(self.current_rom)
                        
                        unique_achs = set()
                        for r in s_rules:
                            if isinstance(r, dict) and r.get("title"):
                                unique_achs.add(str(r.get("title")).strip())
                        total_achs = len(unique_achs)
                        
                        if total_achs > 0:
                            state = self._ach_state_load()
                            
                            unlocked_titles = set()
                            for e in state.get("session", {}).get(self.current_rom, []):
                                t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                                if t: unlocked_titles.add(t)
                                
                            unlocked_total = len(unlocked_titles)
                            _rom = self.current_rom
                            _cfg = self.cfg
                            _br = self.bridge
                            threading.Thread(
                                target=lambda _c=_cfg, _r=_rom, _ut=unlocked_total, _ta=total_achs, _b=_br:
                                    CloudSync.upload_achievement_progress(_c, _r, _ut, _ta, bridge=_b),
                                daemon=True,
                            ).start()
                            # Retroactive upload: if this ROM now has a VPS-ID but was previously
                            # blocked (progress_upload_log has no entry or a different vps_id),
                            # the upload above will succeed this time. Record the vps_id used.
                            try:
                                from ui_vps import _load_vps_mapping
                                _vps_mapping = _load_vps_mapping(self.cfg)
                                _vps_id = (_vps_mapping.get(self.current_rom) or "").strip()
                                if _vps_id:
                                    _upload_log = _load_progress_upload_log(self.cfg)
                                    _prev_vps_id = _upload_log.get(self.current_rom, "")
                                    if _prev_vps_id != _vps_id:
                                        _upload_log[self.current_rom] = _vps_id
                                        _save_progress_upload_log(self.cfg, _upload_log)
                                        log(self.cfg, f"[CLOUD] Progress upload log updated for {self.current_rom} -> vps_id={_vps_id}")
                            except Exception as e:
                                log(self.cfg, f"[CLOUD] Progress upload log update failed: {e}", "WARN")
                    except Exception as e:
                        log(self.cfg, f"[CLOUD] Progress upload failed: {e}", "WARN")

        finally:
            self.current_table = None
            self.current_rom = None
            self.start_time = None
            self.game_active = False
            self.start_audits = {}
            self.challenge = {} 
            self.players.clear()
            self.ball_track.update({"active": False, "index": 0, "start_time": None, "score_base": 0, "last_balls_played": None, "balls": []})
            self._last_audits_global = {}
            self.snap_initialized = False
            self.field_stats.clear()
            self.bootstrap_phase = False
            self.current_segment_provisional_diff = {}
            try:
                if hasattr(self.bridge, 'close_secondary_overlays'):
                    self.bridge.close_secondary_overlays.emit()
            except Exception:
                pass
            try:
                _ended_rom = getattr(self, "_session_rom_for_notif", None)
                if _ended_rom and hasattr(self.bridge, "session_ended"):
                    self.bridge.session_ended.emit(_ended_rom)
            except Exception:
                pass
            self._session_rom_for_notif = None
                
    def monitor_table(self) -> Optional[Dict[str, str]]:
        if not win32gui:
            return None

        def _cb(hwnd, acc):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.startswith("Visual Pinball - ["):
                    acc.append(title)

        wins = []
        try:
            win32gui.EnumWindows(_cb, wins)
        except Exception:
            return None

        if not wins:
            return None

        title = wins[0]
        if not (title.startswith("Visual Pinball - [") and title.endswith("]")):
            return None

        table_fragment = title[len("Visual Pinball - ["):-1]
        vpx_filename = table_fragment if table_fragment.lower().endswith(".vpx") else table_fragment + ".vpx"

        vpx_path = os.path.join(self.cfg.TABLES_DIR, vpx_filename)
        if not os.path.isfile(vpx_path):
            alt = os.path.join(self.cfg.TABLES_DIR, table_fragment)
            vpx_path = alt if os.path.isfile(alt) else None

        cache = getattr(self, "_rom_detect_cache", None)
        if not isinstance(cache, dict):
            cache = {"vpx_path": None, "rom": None, "ts": 0.0}
            self._rom_detect_cache = cache

        rom = None
        if vpx_path and os.path.isfile(vpx_path):
            now = time.time()
            cache_path = cache.get("vpx_path")
            cache_rom = cache.get("rom")
            cache_ts = float(cache.get("ts") or 0.0)

            if cache_path == vpx_path and (now - cache_ts) < 120:
                rom = cache_rom
            else:
                rom = run_vpxtool_get_rom(self.cfg, vpx_path)
                self._rom_detect_cache = {"vpx_path": vpx_path, "rom": rom, "ts": now}
                if rom:
                    try:
                        if getattr(self, "_last_logged_rom", None) != rom:
                            log(self.cfg, f"[ROM] VPXTOOL: {rom}")
                            self._last_logged_rom = rom
                    except Exception:
                        pass
                else:
                    try:
                        log(self.cfg, f"[ROM] vpxtool failed for table '{vpx_filename}'", "WARN")
                    except Exception:
                        pass

        clean_table = table_fragment[:-4] if table_fragment.lower().endswith(".vpx") else table_fragment

        return {"table": clean_table, "rom": rom or "", "vpx_file": vpx_path or ""}

    def _poll_custom_events(self) -> None:
        """Detect .trigger files written by AWEditor VBScripts and fire the matching achievements.

        The VBScript ``FireAchievement(eventName)`` sub creates
        ``<custom_events_dir>/<eventName>.trigger``.  This method is called on
        every watcher loop iteration while a table session is active.  For each
        trigger file found it:

        1. Looks up matching rules (``condition.type == "event"``) from every
           ``*.custom.json`` file in the AWEditor output directory.
        2. Emits an achievement toast for each matching rule.
        3. Persists the unlock to achievements_state under the "session" bucket.
        4. Deletes the trigger file so the same event can fire again next time.
        """
        try:
            ce_dir = p_custom_events(self.cfg)
            if not os.path.isdir(ce_dir):
                return

            trigger_files = [
                f for f in os.listdir(ce_dir)
                if f.lower().endswith(".trigger") and os.path.isfile(os.path.join(ce_dir, f))
            ]
            if not trigger_files:
                return

            # Build event → [rule, ...] mapping from all *.custom.json files
            aw_dir = p_aweditor(self.cfg)
            event_rules: dict[str, list] = {}
            try:
                for fname in os.listdir(aw_dir):
                    if not fname.lower().endswith(".custom.json"):
                        continue
                    fpath = os.path.join(aw_dir, fname)
                    try:
                        data = load_json(fpath, {}) or {}
                        for r in (data.get("rules") or []):
                            if not isinstance(r, dict):
                                continue
                            cond = r.get("condition") or {}
                            if cond.get("type") == "event" and cond.get("event"):
                                ev = str(cond["event"])
                                event_rules.setdefault(ev, []).append(r)
                    except Exception as e:
                        log(self.cfg, f"[CUSTOM_EVENTS] Failed to load {fname}: {e}", "WARN")
            except Exception as e:
                log(self.cfg, f"[CUSTOM_EVENTS] Failed to scan aweditor dir: {e}", "WARN")

            # Debounce / cooldown bookkeeping – shared across all trigger files in this poll
            _COOLDOWN_SECS = 3.0
            _cooldown: dict = getattr(self, "_custom_event_cooldown", {})
            if not isinstance(_cooldown, dict):
                _cooldown = {}
            self._custom_event_cooldown = _cooldown
            _poll_now = time.time()

            for tf in trigger_files:
                event_name = tf[: -len(".trigger")]
                tf_path = os.path.join(ce_dir, tf)

                # Debounce: if the same event fired very recently (e.g. the table
                # script calls FireAchievement multiple times in quick succession due
                # to switch-bounce or a rapid loop), silently delete the stale trigger
                # file and skip this iteration so the UI and log are not spammed.
                _last = _cooldown.get(event_name, 0.0)
                if _poll_now - _last < _COOLDOWN_SECS:
                    # Cooldown active – remove the trigger file to prevent accumulation
                    try:
                        os.remove(tf_path)
                    except Exception:
                        pass
                    continue

                matched_rules = event_rules.get(event_name, [])
                if matched_rules:
                    # Check which achievements are already unlocked to avoid repeat toasts
                    table_key = (self.current_table or self.current_rom or "").strip() or "__custom__"
                    try:
                        _state = self._ach_state_load()
                        _already_unlocked = {
                            str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                            for e in _state.get("session", {}).get(table_key, [])
                        }
                    except Exception:
                        _already_unlocked = set()

                    for rule in matched_rules:
                        title = str(rule.get("title") or event_name).strip()
                        log(self.cfg, f"[CUSTOM_EVENTS] Event '{event_name}' → achievement '{title}'")
                        # Only show toast for first-time unlocks (once per profile)
                        if title not in _already_unlocked:
                            try:
                                self.bridge.ach_toast_show.emit(title, self.current_table or "", 5)
                            except Exception as e:
                                log(self.cfg, f"[CUSTOM_EVENTS] toast emit failed: {e}", "WARN")

                    # Persist unlocks; custom achievements must NOT be uploaded to the cloud
                    try:
                        self._ach_record_unlocks("session", table_key, matched_rules, skip_cloud=True)
                    except Exception as e:
                        log(self.cfg, f"[CUSTOM_EVENTS] persist failed: {e}", "WARN")

                    # Record fire time for debounce so the same event cannot spam the
                    # UI within the cooldown window.  Only record on a successful match
                    # so that events without a rule can still be retried immediately
                    # (e.g. after the user adds the rule in AWEditor mid-session).
                    _cooldown[event_name] = _poll_now
                else:
                    log(self.cfg, f"[CUSTOM_EVENTS] No rule found for event '{event_name}'", "WARN")

                # Always remove the trigger file so it can fire again next time
                try:
                    os.remove(tf_path)
                    log(self.cfg, f"[CUSTOM_EVENTS] Removed trigger file '{tf}'")
                except Exception as e:
                    log(self.cfg, f"[CUSTOM_EVENTS] Failed to remove trigger '{tf}': {e}", "WARN")
        except Exception as e:
            log(self.cfg, f"[CUSTOM_EVENTS] poll error: {e}", "WARN")

    def _thread_main(self):
        log(self.cfg, ">>> watcher thread running")
        # Lower thread priority so VPX always gets CPU scheduler priority
        try:
            THREAD_PRIORITY_BELOW_NORMAL = -1
            handle = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadPriority(handle, THREAD_PRIORITY_BELOW_NORMAL)
            log(self.cfg, "[WATCHER] thread priority set to BELOW_NORMAL")
        except Exception as e:
            log(self.cfg, f"[WATCHER] could not set thread priority: {e}", "WARN")
        active_rom = None
        if not hasattr(self, "_last_live_export_ts"):
            self._last_live_export_ts = 0.0
        self._missing_table_ticks = 0  
        while not self._stop.is_set():
            now_loop = time.time()
            dt = now_loop - getattr(self, "_last_tick_time", now_loop)
            if dt < 0 or dt > 5:
                dt = 0.5
            self._last_tick_time = now_loop

            try:
                upd = self.monitor_table()
            except Exception as e:
                log(self.cfg, f"[WATCHER] monitor error: {e}", "WARN")
                upd = None

            if upd:
                self._missing_table_ticks = 0  
                rom = (upd.get("rom") or "").strip()
                table = (upd.get("table") or "").strip()
                # Use ROM as the session key when available; fall back to table name
                # so that original VPX tables without a ROM can still be tracked.
                session_key = rom or table

                if active_rom is None and session_key:
                    if rom:
                        self.on_session_start(rom, is_rom=True)
                    else:
                        self.on_session_start(table, is_rom=False)
                    active_rom = session_key
                    self._emit_mini_info_if_missing_map(rom, 5, table=table)
                    if rom:
                        self._emit_mini_info_if_missing_vps_id(rom, 8)

                elif active_rom and session_key and session_key != active_rom:
                    self.on_session_end()
                    active_rom = None
                    if rom:
                        self.on_session_start(rom, is_rom=True)
                    else:
                        self.on_session_start(table, is_rom=False)
                    active_rom = session_key
                    self._emit_mini_info_if_missing_map(rom, 5, table=table)
                    if rom:
                        self._emit_mini_info_if_missing_vps_id(rom, 8)

                if active_rom:
                    audits, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                    audits_ctl = audits 

                    ch = getattr(self, "challenge", {}) or {}
                    is_chal_active = ch.get("active", False)

                    try:
                        now2 = time.time()
                        if self.current_rom and self.cfg.OVERLAY.get("live_updates", False) and (now2 - self._last_live_export_ts >= 2.0):
                            if not is_chal_active:
                                duration_sec = int(now2 - (self.start_time or now2))
                                self.export_overlay_snapshot(audits, duration_sec, on_demand=True)
                            self._last_live_export_ts = now2
                    except Exception as e:
                        log(self.cfg, f"[EXPORT] live export failed: {e}", "WARN")

                    self.current_segment_provisional_diff = {}

                    self.current_player = 1
                    try:
                        if 1 in self.players:
                            self.players[1]["active_play_seconds"] = float(self.players[1].get("active_play_seconds", 0.0)) + dt
                    except Exception:
                        pass

                    try:
                        changed = bool(self._attribute_events(audits_ctl))
                        if changed and self.cfg.OVERLAY.get("live_updates", False) and not is_chal_active:
                            duration_now = int(time.time() - (self.start_time or time.time()))
                            self.export_overlay_snapshot(audits, duration_now, on_demand=True)
                            self._last_live_export_ts = time.time()
                    except Exception as e:
                        log(self.cfg, f"[HIGHLIGHTS] live attribute failed: {e}", "WARN")

                    self.players.setdefault(1, {
                        "start_audits": self._player_field_filter(self.start_audits, 1) or {"P1 Score": 0},
                        "last_audits": self._player_field_filter(self.start_audits, 1) or {"P1 Score": 0},
                        "active_play_seconds": 0.0,
                        "start_time": time.time(),
                        "session_deltas": {},
                        "event_counts": {},
                    })
                    p1_audits = self._player_field_filter(audits, 1)
                    if p1_audits:
                        self.players[1]["last_audits"].update(p1_audits)

                    try:
                        self._challenge_tick(audits_ctl)
                    except Exception as e:
                        log(self.cfg, f"[CHALLENGE] tick failed in loop: {e}", "WARN")

                    if self.snapshot_mode:
                        try:
                            self._ball_update(audits_ctl)
                        except Exception as e:
                            log(self.cfg, f"[BALL] update failed: {e}", "WARN")

                    # Poll custom_events/ for .trigger files (AWEditor watchdog)
                    try:
                        self._poll_custom_events()
                    except Exception as e:
                        log(self.cfg, f"[CUSTOM_EVENTS] poll failed: {e}", "WARN")
            else:
                if active_rom is not None:

                    self._missing_table_ticks += 1
                    if self._missing_table_ticks >= 4: 
                        self.on_session_end()
                        active_rom = None
                        self._missing_table_ticks = 0

            # Sleep longer while game is active to reduce CPU/IO pressure on VPX
            if active_rom is not None:
                time.sleep(1.0)
            else:
                time.sleep(2.0)

    def start(self):
        if getattr(self, "thread", None) and self.thread.is_alive():
            return
        try:
            _migrate_runtime_dirs(self.cfg)
        except Exception as e:
            log(self.cfg, f"[MIGRATE] failed: {e}", "WARN")
        try:
            self.bootstrap()
        except Exception as e:
            log(self.cfg, f"[BOOTSTRAP] failed: {e}", "WARN")
        try:
            self._ensure_global_ach()
        except Exception as e:
            log(self.cfg, f"[GLOBAL_ACH] ensure failed: {e}", "WARN")
        try:
            self.start_prefetch_background()
        except Exception as e:
            log(self.cfg, f"[PREFETCH] auto-start failed: {e}", "WARN")
        self._stop.clear()
        self.thread = threading.Thread(target=self._thread_main, daemon=True, name="WatcherThread")
        self.thread.start()

    def stop(self):
        try:
            self._stop.set()
            if getattr(self, "thread", None):
                self.thread.join(timeout=3)
        except Exception:
            pass

        if self.game_active:
            try:
                self.on_session_end()
            except Exception as e:
                log(self.cfg, f"[WATCHER] on_session_end during stop failed: {e}", "WARN")

        log(self.cfg, "[WATCHER] stopped")
            
