from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional
from urllib.request import Request, urlopen

try:
    import requests
except Exception:
    requests = None

# ---------------------------------------------------------------------------
# Application paths
# ---------------------------------------------------------------------------

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

# ---------------------------------------------------------------------------
# Overlay defaults & constants
# ---------------------------------------------------------------------------

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
    "base_title_size": 15,
    "base_body_size": 12,
    "base_hint_size": 16,
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
CHALLENGES_ENABLED = True

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
    "[SNAP] pregame player_count detected",
    "[HOOK] Global keyboard hook installed",
    "[HOOK] toggle fired",
    "[HOTKEY] Registered WM_HOTKEY",
    "[CTRL] map miss for candidate",
    "[CTRL] base-map miss for candidate",
]
quiet_prefixes: tuple[str, ...] = ()

# ---------------------------------------------------------------------------
# AppConfig dataclass
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    BASE: str = r"C:\vPinball\Achievements"
    NVRAM_DIR: str = r"C:\vPinball\VisualPinball\VPinMAME\nvram"
    TABLES_DIR: str = r"C:\vPinball\VisualPinball\Tables"
    OVERLAY: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_OVERLAY))
    FIRST_RUN: bool = True
    LOG_CTRL: bool = False
    LOG_SUPPRESS: List[str] = field(default_factory=lambda: list(DEFAULT_LOG_SUPPRESS))
    CLOUD_ENABLED: bool = True
    CLOUD_URL: str = "https://vpx-achievements-watcher-lb-default-rtdb.europe-west1.firebasedatabase.app/"

    ALLOWED_OVERLAY_KEYS: ClassVar[List[str]] = [
        "scale_pct", "background", "portrait_mode", "portrait_rotate_ccw",
        "lines_per_category", "font_family", "overlay_auto_close",
        "pos_x", "pos_y", "use_xy", "overlay_pos_saved",

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

        "notifications_portrait", "notifications_rotate_ccw", "notifications_saved",
        "notifications_x_landscape", "notifications_y_landscape", "notifications_x_portrait", "notifications_y_portrait",

        "player_name", "player_id", "flip_counter_goal_total",
        "challenges_voice_volume", "challenges_voice_mute",
    ]

    @staticmethod
    def load(path: str = CONFIG_FILE) -> "AppConfig":
        if not os.path.exists(path):
            return AppConfig(FIRST_RUN=True)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            ov = dict(DEFAULT_OVERLAY)
            loaded_ov = data.get("OVERLAY", {})

            for k in list(loaded_ov.keys()):
                if k not in AppConfig.ALLOWED_OVERLAY_KEYS:
                    del loaded_ov[k]

            ov.update(loaded_ov)

            return AppConfig(
                BASE=data.get("BASE", AppConfig.BASE),
                NVRAM_DIR=data.get("NVRAM_DIR", AppConfig.NVRAM_DIR),
                TABLES_DIR=data.get("TABLES_DIR", AppConfig.TABLES_DIR),
                OVERLAY=ov,
                FIRST_RUN=bool(data.get("FIRST_RUN", False)),
                CLOUD_ENABLED=bool(data.get("CLOUD_ENABLED", True)),
            )
        except Exception as e:
            print(f"[LOAD ERROR] {e}")
            return AppConfig(FIRST_RUN=True)

    def save(self, path: str = CONFIG_FILE) -> None:
        try:
            clean_overlay = {}
            ov = getattr(self, "OVERLAY", {})

            for k in AppConfig.ALLOWED_OVERLAY_KEYS:
                if k in ov:
                    clean_overlay[k] = ov[k]

            to_dump = {
                "BASE": getattr(self, "BASE", r"C:\vPinball\Achievements"),
                "NVRAM_DIR": getattr(self, "NVRAM_DIR", r"C:\vPinball\VisualPinball\VPinMAME\nvram"),
                "TABLES_DIR": getattr(self, "TABLES_DIR", r"C:\vPinball\VisualPinball\Tables"),
                "CLOUD_ENABLED": getattr(self, "CLOUD_ENABLED", True),
                "FIRST_RUN": getattr(self, "FIRST_RUN", False),
                "OVERLAY": clean_overlay
            }

            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(to_dump, f, indent=2)
        except Exception as e:
            print(f"CRITICAL ERROR: Could not save config.json -> {e}")

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def p_maps(cfg):         return os.path.join(cfg.BASE, "NVRAM_Maps")
def p_local_maps(cfg):   return os.path.join(p_maps(cfg), "maps")
def p_session(cfg):      return os.path.join(cfg.BASE, "session_stats")
def p_highlights(cfg):   return os.path.join(p_session(cfg), "Highlights")
def p_rom_spec(cfg):     return os.path.join(cfg.BASE, "rom_specific_achievements")
def p_custom(cfg):       return os.path.join(cfg.BASE, "custom_achievements")
def f_global_ach(cfg):   return os.path.join(cfg.BASE, "global_achievements.json")
def f_achievements_state(cfg: "AppConfig") -> str:
    return os.path.join(cfg.BASE, "achievements_state.json")
def f_log(cfg):          return os.path.join(cfg.BASE, "watcher.log")
def f_index(cfg):        return os.path.join(p_maps(cfg), "index.json")
def f_romnames(cfg):     return os.path.join(p_maps(cfg), "romnames.json")

GITHUB_BASE = "https://raw.githubusercontent.com/tomlogic/pinmame-nvram-maps/475fa3619134f5aa732ccd80244e1613e7e6e9a1"
INDEX_URL = f"{GITHUB_BASE}/index.json"
ROMNAMES_URL = f"{GITHUB_BASE}/romnames.json"
VPXTOOL_EXE = "vpxtool.exe"
VPXTOOL_DIRNAME = "tools"
VPXTOOL_PATH = os.path.join(APP_DIR, VPXTOOL_DIRNAME, VPXTOOL_EXE)
VPXTOOL_URL = "https://github.com/francisdb/vpxtool/releases/download/v0.26.0/vpxtool-Windows-x86_64-v0.26.0.zip"

# ---------------------------------------------------------------------------
# Logging & file I/O utilities
# ---------------------------------------------------------------------------

def ensure_dir(path): os.makedirs(path, exist_ok=True)
def _ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

# ---------------------------------------------------------------------------
# Anti-cheat security
# ---------------------------------------------------------------------------

ANTI_CHEAT_SALT = "VPX_S3cr3t_H4sh_9921!"

def _generate_signature(data: dict) -> str:
    d = dict(data)
    d.pop("_signature", None)
    s = json.dumps(d, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256((s + ANTI_CHEAT_SALT).encode('utf-8')).hexdigest()

def _is_secure_path(path: str) -> bool:
    """Prüft, ob eine Datei durch Anti-Cheat geschützt werden soll."""
    if not path: return False
    p = path.lower().replace("\\", "/")

    if p.endswith("config.json"): return False
    if "nvram_maps" in p: return False
    if "custom_achievements" in p: return False
    if p.endswith("index.json") or p.endswith("romnames.json"): return False

    if not p.endswith(".json"): return False

    return True

def load_json(path, default=None):
    data = _raw_load_json(path, None)
    if data is None:
        return default

    if _is_secure_path(path) and isinstance(data, dict):
        sig = data.pop("_signature", None)
        if not sig:
            print(f"\n[SECURITY] NO SIGNATURE FOUND IN: {path}")
            print("[SECURITY] The file has been blocked and will not be loaded!\n")
            return default

        expected = _generate_signature(data)
        if sig != expected:
            print(f"\n[SECURITY] TAMPERING DETECTED IN: {path}")
            print("[SECURITY] The file has been blocked and will not be loaded!\n")
            return default

        data["_signature"] = sig

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

# ---------------------------------------------------------------------------
# General utilities
# ---------------------------------------------------------------------------

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

def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.isdir(base):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    return os.path.join(APP_DIR, rel)

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
