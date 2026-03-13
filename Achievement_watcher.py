
from __future__ import annotations

import configparser
import random
import subprocess
import hashlib
import os, sys, time, json, re, glob, threading, uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple, ClassVar
from collections import defaultdict, Counter
from PyQt6.QtGui import QFontMetrics

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QTextBrowser, QSystemTrayIcon, QMenu, QFileDialog, QMessageBox, QTabWidget,
    QCheckBox, QSlider, QComboBox, QDialog, QGroupBox, QColorDialog, QLineEdit,
    QFontComboBox, QSpinBox, QDoubleSpinBox, QGridLayout
)
from PyQt6.QtCore import (Qt, pyqtSignal, QEvent, QTimer, QRect,
                          QAbstractNativeEventFilter, QCoreApplication, QObject, QPoint, pyqtSlot)
from PyQt6.QtGui import (QIcon, QColor, QFont, QTransform, QPixmap,
                         QPainter, QImage, QPen)

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
_winmm = ctypes.WinDLL("winmm", use_last_error=True)
_user2 = ctypes.WinDLL("user32", use_last_error=True)
import ssl
from urllib.request import Request, urlopen

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

class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD), ("dwYpos", wintypes.DWORD), ("dwZpos", wintypes.DWORD),
        ("dwRpos", wintypes.DWORD), ("dwUpos", wintypes.DWORD), ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD), ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD), ("dwReserved1", wintypes.DWORD), ("dwReserved2", wintypes.DWORD),
    ]
JOY_RETURNALL = 0x000000FF
JOYERR_NOERROR = 0
_joyGetPosEx = _winmm.joyGetPosEx
_joyGetPosEx.argtypes = [wintypes.UINT, ctypes.POINTER(JOYINFOEX)]
_joyGetPosEx.restype = wintypes.UINT

RIDEV_INPUTSINK = 0x00000100
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_HOTKEY = 0x0312 

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", ctypes.c_ushort),
        ("usUsage", ctypes.c_ushort),
        ("dwFlags", ctypes.c_uint),
        ("hwndTarget", wintypes.HWND),
    ]
_RegisterRawInputDevices = _user2.RegisterRawInputDevices
_RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), ctypes.c_uint, ctypes.c_uint]
_RegisterRawInputDevices.restype = wintypes.BOOL

_MapVirtualKeyW = _user2.MapVirtualKeyW
_MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_MapVirtualKeyW.restype = wintypes.UINT
_GetKeyNameTextW = _user2.GetKeyNameTextW
_GetKeyNameTextW.argtypes = [wintypes.LONG, ctypes.c_wchar_p, ctypes.c_int]
_GetKeyNameTextW.restype = ctypes.c_int

def vk_to_name(vk: int) -> str:
    try:
        sc = _MapVirtualKeyW(vk, 0)
        lparam = (sc << 16)
        buf = ctypes.create_unicode_buffer(64)
        if _GetKeyNameTextW(lparam, buf, 64) > 0:
            return buf.value
    except Exception:
        pass
    return f"VK 0x{vk:02X}"

def vk_to_name_en(vk: int) -> str:
    try:
        vk = int(vk)
    except Exception:
        return "VK ?"
    if 0x70 <= vk <= 0x7B:
        return f"F{vk - 0x6F}"
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"

    english = {
        0x08: "Backspace",
        0x09: "Tab",
        0x0D: "Enter",
        0x10: "Shift",
        0x11: "Ctrl",
        0x12: "Alt",
        0x13: "Pause",
        0x14: "Caps Lock",
        0x1B: "Esc",
        0x20: "Space",
        0x21: "Page Up",
        0x22: "Page Down",
        0x23: "End",
        0x24: "Home",
        0x25: "Left Arrow",
        0x26: "Up Arrow",
        0x27: "Right Arrow",
        0x28: "Down Arrow",
        0x2C: "Print Screen",
        0x2D: "Insert",
        0x2E: "Delete",
        0x5B: "Left Win",
        0x5C: "Right Win",
        0x5D: "Menu",
        0x90: "Num Lock",
        0x91: "Scroll Lock",
        0x6A: "Num *",
        0x6B: "Num +",
        0x6D: "Num -",
        0x6E: "Num .",
        0x6F: "Num /",
        0xA0: "Left Shift",
        0xA1: "Right Shift",
        0xA2: "Left Ctrl",
        0xA3: "Right Ctrl",
        0xA4: "Left Alt",
        0xA5: "Right Alt",
    }
    if vk in english:
        return english[vk]

    return f"VK 0x{vk:02X}"

def vsc_to_vk(scan_code: int) -> int:
    try:
        return int(_MapVirtualKeyW(int(scan_code), 0x01) or 0)
    except Exception:
        return 0

def get_vpx_ini_path_for_current_user() -> str | None:
    try:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        ini = os.path.join(appdata, "VPinballX", "VPinballX.ini")
        return ini if os.path.isfile(ini) else None
    except Exception:
        return None

def parse_vpx_flipper_bindings(ini_path: str) -> dict:
    out = {'vk_left': 0, 'vk_right': 0, 'joy_left': 0, 'joy_right': 0}
    if not ini_path or not os.path.isfile(ini_path):
        return out
    try:
        cp = configparser.ConfigParser(strict=False)
        cp.optionxform = str
        with open(ini_path, "r", encoding="utf-8", errors="ignore") as f:
            cp.read_file(f)

        if cp.has_section("Player"):
            def _get_int(name: str) -> int:
                try:
                    raw = (cp.get("Player", name, fallback="") or "").strip()
                    if not raw:
                        return 0
                    return int(raw)
                except Exception:
                    return 0

            l_sc = _get_int("LFlipKey")
            r_sc = _get_int("RFlipKey")
            jl = _get_int("JoyLFlipKey")
            jr = _get_int("JoyRFlipKey")

            vk_l = vsc_to_vk(l_sc) if l_sc else 0
            vk_r = vsc_to_vk(r_sc) if r_sc else 0

            # Fallbacks für LShift/RShift
            if not vk_l and l_sc == 42:  # DI scancode for LShift
                vk_l = 0xA0  # VK_LSHIFT
            if not vk_r and r_sc == 54:  # DI scancode for RShift
                vk_r = 0xA1  # VK_RSHIFT

            out.update({
                'vk_left': vk_l,
                'vk_right': vk_r,
                'joy_left': jl,
                'joy_right': jr,
            })
    except Exception:
        pass
    return out

def register_raw_input_for_window(hwnd: int) -> bool:
    devices = (RAWINPUTDEVICE * 3)(
        RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd),
        RAWINPUTDEVICE(0x01, 0x04, RIDEV_INPUTSINK, hwnd),
        RAWINPUTDEVICE(0x01, 0x05, RIDEV_INPUTSINK, hwnd),
    )
    ok = _RegisterRawInputDevices(devices, 3, ctypes.sizeof(RAWINPUTDEVICE))
    return bool(ok)

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
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
    "[HOOK] Global keyboard hook installed",
    "[HOOK] toggle fired",
    "[HOTKEY] Registered WM_HOTKEY",
    "[CTRL] map miss for candidate",         
    "[CTRL] base-map miss for candidate",    
]
 
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

def run_vpxtool_get_rom(cfg: AppConfig, vpx_path: str) -> str | None:

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
            log(cfg, f"[VPXTOOL] romname returned no parsable output: {out}", "WARN")
            warned.add(key)
        return None

    except Exception as e:
        if key not in warned:
            log(cfg, f"[VPXTOOL] romname exception: {e}", "WARN")
            warned.add(key)
        return None

PREFETCH_MODE = "background"
PREFETCH_LOG_EVERY = 50
ROLLING_HISTORY_PER_ROM = 10

def ensure_dir(path): os.makedirs(path, exist_ok=True)
def _ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

# ==========================================
# ANTI-CHEAT SECURITY
# ==========================================
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

import urllib.request

class CloudSync:
    @staticmethod
    def upload_score(cfg: AppConfig, category: str, rom: str, score: int, extra_data: dict = None):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or score <= 0 or not pname or pname.lower() == "player":
            return
        
        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip()
        
        pid_key = f"p_{pid}"
        if extra_data:
            if category == "flip" and "target_flips" in extra_data:
                pid_key = f"p_{pid}_f{extra_data['target_flips']}"
            elif category == "time" and "target_time" in extra_data:
                pid_key = f"p_{pid}_t{extra_data['target_time']}"
            elif "difficulty" in extra_data:
                clean_diff = str(extra_data["difficulty"]).replace(" ", "")
                pid_key = f"p_{pid}_{clean_diff}"
        
        endpoint = f"{url}/scores/{category}/{rom}/{pid_key}.json"
        
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
            
            payload = {"name": pname, "score": score, "ts": datetime.now(timezone.utc).isoformat()}
            if extra_data: payload.update(extra_data)
                
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=5) as resp:
                    log(cfg, f"[CLOUD] Uploaded {category.upper()} Score for {rom}: {score}")
            except Exception as e:
                log(cfg, f"[CLOUD] Upload failed: {e}", "WARN")
                
        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def upload_achievement_progress(cfg: AppConfig, rom: str, unlocked: int, total: int):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or total <= 0 or not pname or pname.lower() == "player":
            return
            
        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = cfg.OVERLAY.get("player_id", "unknown")
        endpoint = f"{url}/progress/{rom}/{pid}.json"
        
        def _task():
            percentage = round((unlocked / total) * 100, 1)
            payload = {
                "name": pname,
                "unlocked": unlocked,
                "total": total,
                "percentage": percentage,
                "ts": datetime.now(timezone.utc).isoformat()
            }
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=5) as resp:
                    log(cfg, f"[CLOUD] Uploaded Achievement Progress for {rom}: {unlocked}/{total} ({percentage}%)")
            except Exception as e:
                log(cfg, f"[CLOUD] Progress upload failed: {e}", "WARN")
        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def fetch_data(cfg: AppConfig, node_path: str) -> list:
        if not cfg.CLOUD_URL or not node_path: 
            return []
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
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
            log(cfg, f"[CLOUD] Fetch error for {endpoint}: {e}", "ERROR")
            return []

class Watcher:
    MIN_SEGMENTS_FOR_CLASSIFICATION = 1
    SUMMARY_FILENAME = "session_latest.summary.json"

    # -------------------------------------------------------------------------
    # Initialization & Setup
    # -------------------------------------------------------------------------

    def __init__(self, cfg: AppConfig, bridge: "Bridge"):
        self.cfg = cfg
        self.bridge = bridge
        self._stop = threading.Event()
        self._flush_lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self._last_logged_rom = None

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
        self.INDEX: Dict[str, Any] = {}
        self.ROMNAMES: Dict[str, Any] = {}
        
        self._field_layout_cache: Dict[str, Dict[str, Any]] = {}
        self.current_segment_provisional_diff: Dict[str, int] = {}
        self.include_current_segment_in_overlay = True
        self._control_fields_cache: Dict[str, List[dict]] = {}  
        
        self.snapshot_mode = True
        self.snap_initialized = False
        self.field_stats = {}
        self.bootstrap_phase = False
        
        self._flip_init_state()

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
        return (
            os.path.isfile(os.path.join(maps_dir, f"{rom}.json")) or
            os.path.isfile(os.path.join(maps_dir, f"{rom}.map.json"))
        )
 
    def _has_any_map(self, rom: str) -> bool:
        if not rom:
            return False
        try:
            m1 = os.path.join(p_local_maps(self.cfg), f"{rom}.json")
            m2 = os.path.join(p_local_maps(self.cfg), f"{rom}.map.json")
            if os.path.isfile(m1) or os.path.isfile(m2):
                return True
            fields, _ = self._try_load_map_for(rom)
            return bool(fields)
        except Exception:
            return False
 
    def _emit_mini_info_if_missing_map(self, rom: str, seconds: int = 5):
        import os, time, win32gui
        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG

        try:
            if not rom:
                return
            if self._has_any_map(rom):
                return

            maps_dir = p_local_maps(self.cfg)
            cand1 = os.path.join(maps_dir, f"{rom}.json")
            cand2 = os.path.join(maps_dir, f"{rom}.map.json")
            if os.path.isfile(cand1) or os.path.isfile(cand2):
                return

            shown = getattr(self, "_mini_info_shown_for_rom", None)
            if not isinstance(shown, set):
                shown = set()
            if rom in shown:
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

            while not self._stop.is_set():
                try:
                    if not self.game_active:
                        return
                except Exception:
                    return

                if _vpx_window_visible():
                    msg = f"NVRAM map not found for {rom}."
                    dur = max(3, int(seconds))
                    try:
                        QMetaObject.invokeMethod(
                            self.bridge,
                            "challenge_info_show",
                            Qt.ConnectionType.QueuedConnection,
                            Q_ARG(str, msg),
                            Q_ARG(int, dur),
                            Q_ARG(str, "#FF3B30")
                        )
                        shown.add(rom)
                        self._mini_info_shown_for_rom = shown
                        log(self.cfg, f"[INFO] Mini overlay (no map) shown (window detected) for {rom}")
                    except Exception as e:
                        log(self.cfg, f"[OVERLAY] mini info emit failed: {e}", "WARN")
                    return

                time.sleep(0.5)

        except Exception as e:
            log(self.cfg, f"[OVERLAY] mini info init failed: {e}", "WARN")
               
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
            return [50, 100, 250, 500]
        if "balls played" in f:
            return [100, 250, 500]
        if "extra ball" in f:
            return [10, 20, 30]
        if "ball save" in f:
            return [20, 50, 100]
        if "jackpot" in f:
            return [25, 50, 100, 150]
        if "multiball" in f:
            return [10, 25, 50]
        if "ramp" in f:
            return [100, 200, 300, 500]
        if "loop" in f or "orbit" in f:
            return [100, 200, 500]
        if "spinner" in f:
            return [100, 200, 500]
        if "target" in f:
            return [200, 400, 800]
        if "modes completed" in f or ("mode" in f and "complete" in f):
            return [10, 25, 50]
        if "modes started" in f or ("mode" in f and "start" in f):
            return [25, 50, 100]
        return [50, 100, 250, 500]     

    def _generate_default_global_rules(self) -> list[dict]:
        rules: list[dict] = []
        seen: set[str] = set()
        for mins in [10, 15, 20, 30, 35, 45, 60]:
            title = self._unique_title(f"Global – {mins} Minutes", seen)
            rules.append({
                "title": title,
                "scope": "global",
                "condition": {"type": "session_time", "min_seconds": int(mins * 60)}
            })

        candidate_fields = [
            "Games Started", "Balls Played", "Ramps Made", "Jackpots",
            "Total Multiballs", "Loops", "Spinner", "Drop Targets",
            "Orbits", "Combos", "Extra Balls", "Ball Saves",
            "Modes Started", "Modes Completed"
        ]

        total_target = 50
        ci = 0
        while len(rules) < total_target and candidate_fields:
            fld = candidate_fields[ci % len(candidate_fields)]
            for m in self._overall_milestones_for_field(fld):
                if len(rules) >= total_target:
                    break
                title = self._unique_title(f"Global – {fld} {m}", seen)
                rules.append({
                    "title": title,
                    "scope": "global",
                    "condition": {"type": "nvram_overall", "field": fld, "min": int(m)}
                })
            ci += 1
        return rules[:total_target]        
            
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
                if "feature" in sec or "histogram" in sec or "champion" in sec or "mode" in sec:
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
            if lbl in priority_set and ("score" in lbl.lower() or "histogram" in lbl.lower() or "champion" in lbl.lower()):
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
            title = self._unique_title(f"{rom} – {mins} Minutes (Session)", seen_titles)
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
                title = self._unique_title(f"{rom} – {fld} {int(m)} (Session)", seen_titles)
                rules.append({
                    "title": title,
                    "condition": {"type": "nvram_delta", "field": fld, "min": int(m)},
                    "scope": "session"
                })
                used_session_per_field[fld] = cnt + 1
                remaining_session -= 1

        if save_json(path, {"rules": rules}):
            log(self.cfg, f"[ROM_SPEC] created {path} with {len(rules)} session-only rules (included priority fields)")

    def _ach_persist_after_session(self, end_audits: dict, duration_sec: int, nplayers: int):
        if not self.current_rom or not self._has_any_map(self.current_rom):
            return
            
        try:
            _awarded, _all_global, awarded_meta = self._evaluate_achievements(
                self.current_rom, self.start_audits, end_audits, duration_sec
            )
        except Exception as e:
            log(self.cfg, f"[ACH] eval failed: {e}", "WARN")
            awarded_meta = []

        try:
            from_ga = [m for m in (awarded_meta or []) if (m.get("origin") == "global_achievements")]
            if from_ga:
                self._ach_record_unlocks("global", self.current_rom, from_ga)
                try:
                    self._emit_achievement_toasts(from_ga, seconds=5)
                except Exception:
                    pass
        except Exception as e:
            log(self.cfg, f"[ACH] persist global failed: {e}", "WARN")

        try:
            sess_achs_p1 = self._evaluate_player_session_achievements(1, self.current_rom) or []
            if sess_achs_p1:
                self._ach_record_unlocks("session", self.current_rom, list(sess_achs_p1))
                try:
                    self._emit_achievement_toasts(sess_achs_p1, seconds=5)
                except Exception:
                    pass
        except Exception as e:
            log(self.cfg, f"[ACH] persist session failed: {e}", "WARN")

        try:
            from PyQt6.QtCore import QTimer
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                log(self.cfg, "[OVERLAY] auto-show triggered (postgame)")
                QTimer.singleShot(500, lambda: self.bridge.overlay_show.emit())
        except Exception as e:
            log(self.cfg, f"[OVERLAY] auto-show failed: {e}", "WARN")
    
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
            p_rom_spec(self.cfg),
            p_custom(self.cfg),
        ]:
            ensure_dir(d)

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

        ensure_file(f_index(self.cfg), INDEX_URL)
        ensure_file(f_romnames(self.cfg), ROMNAMES_URL)
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

    # -------------------------------------------------------------------------
    # NVRAM Map Loading & Decoding
    # -------------------------------------------------------------------------

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

            entry = (self.INDEX or {}).get(rom)
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
        base_rom = (self.ROMNAMES or {}).get(name)
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
        nv_path = os.path.join(self.cfg.NVRAM_DIR, rom + ".nv")
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

    # -------------------------------------------------------------------------
    # VPX Process & Window Management
    # -------------------------------------------------------------------------

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
        return bool(visible["flag"])

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


    # -------------------------------------------------------------------------
    # Challenge & Flipper Input Handling
    # -------------------------------------------------------------------------

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
            time.sleep(0.02)
            
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
            self._flip_stop_inputs()
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
                log(self.cfg, "[CHALLENGE] VPX Player window closed early. Aborting challenge.")
                kind = str(ch.get("kind", "")).lower()
                
                if kind == "timed":
                    self.stop_timed_challenge()
                elif kind == "flip":
                    self.stop_flip_challenge()
                else:
                    try:
                        self.bridge.challenge_timer_stop.emit()
                        self.bridge.flip_counter_total_hide.emit()
                    except Exception:
                        pass
                    
                ch["active"] = False
                ch["pending_kill_at"] = None
                self.challenge = ch
                return

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

            out_dir = os.path.join(self.cfg.BASE, "challenges", "history")
            ensure_dir(out_dir)
            path = os.path.join(out_dir, f"{sanitize_filename(rom)}.json")
            hist = secure_load_json(path, {"results": []}) or {"results": []}
            hist.setdefault("results", []).append(payload)
            secure_save_json(path, hist)
            
            CloudSync.upload_score(self.cfg, kind, rom, int(score), extra)
            
            ch["result_recorded"] = True
            self.challenge = ch

            try:
                phrase = f"{str(kind or '').capitalize()} challenge finished."
                self.bridge.challenge_speak.emit(phrase)
            except Exception:
                pass
            try:
                score_txt = f"{int(score):,d}".replace(",", ".")
                self.bridge.challenge_info_show.emit(f"Score: {score_txt}", 8, "#FFFFFF")
            except Exception:
                pass

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

    # -------------------------------------------------------------------------
    # Session & Score Analysis
    # -------------------------------------------------------------------------

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

        cdir = p_custom(self.cfg)
        placeholder = "put_your_custom_achievements_here_click_me.json"
        if os.path.isdir(cdir):
            for fn in os.listdir(cdir):
                if not fn.lower().endswith(".json"):
                    continue
                if fn.lower() == placeholder:
                    continue  # nur diese eine Datei ignorieren
                data = load_json(os.path.join(cdir, fn), {}) or {}
                if isinstance(data.get("rules"), list):
                    rules.extend(data["rules"])
                for ex in data.get("examples", []) or []:
                    if isinstance(ex, dict) and ex.get("rom") == rom:
                        achs = ex.get("achievements", [])
                        if isinstance(achs, list):
                            rules.extend(achs)
        out, seen = [], set()
        for r in rules:
            t = r.get("title") or "Achievement"
            if t in seen:
                continue
            seen.add(t)
            out.append(r)
        return out

    def _evaluate_player_session_achievements(self, pid: int, rom: str) -> list:
        if pid not in self.players:
            return []
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
        for rule in rules:
            title = rule.get("title") or "Achievement"
            
            if title.strip() in already_unlocked:
                continue

            cond = rule.get("condition", {}) or {}
            rtype = cond.get("type")
            field = cond.get("field")
            try:
                if rtype == "nvram_delta":
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 0))
                    if deltas.get(field, 0) >= need:
                        awarded.append(title)

                elif rtype == "session_time":
                    min_s = int(cond.get("min_seconds", cond.get("min", 0)))
                    if play_sec >= min_s:
                        awarded.append(title)
            except Exception:
                continue

        out, seen_field = [], set()
        for title in awarded:
            parts = title.split("–")
            if len(parts) > 1:
                field_name = parts[-1].strip().split(" ")[0]
            else:
                field_name = title
            if field_name in seen_field:
                continue
            seen_field.add(field_name)
            out.append(title)
        return out

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

        payload = {
            "player": 1,
            "playtime_sec": play_sec,
            "score": score_abs,
            "highlights": highlights,
        }

        save_json(os.path.join(active_dir, f"{self.current_rom}_P1.json"), payload)

        try:
            for pid_old in (2, 3, 4):
                fp = os.path.join(active_dir, f"{self.current_rom}_P{pid_old}.json")
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
            
        try:
            _awarded, _all_global, awarded_meta = self._evaluate_achievements(
                self.current_rom, self.start_audits, end_audits, duration_sec
            )
        except Exception as e:
            log(self.cfg, f"[ACH] eval failed: {e}", "WARN")
            awarded_meta = []

        try:
            global_hits = [m for m in (awarded_meta or []) if (m.get("origin") == "global_achievements")]
            if global_hits:
                self._ach_record_unlocks("global", self.current_rom, global_hits)
                self._emit_achievement_toasts(global_hits, seconds=5)
        except Exception as e:
            log(self.cfg, f"[ACH] persist global failed: {e}", "WARN")

        try:
            session_hits = self._evaluate_player_session_achievements(1, self.current_rom) or []
            if session_hits:
                self._ach_record_unlocks("session", self.current_rom, list(session_hits))
                self._emit_achievement_toasts(session_hits, seconds=5)
        except Exception as e:
            log(self.cfg, f"[ACH] persist session failed: {e}", "WARN")

    # -------------------------------------------------------------------------
    # Achievement Evaluation & Persistence
    # -------------------------------------------------------------------------

    def _evaluate_achievements(self, rom: str, start_audits: dict, end_audits: dict, duration_sec: int) -> tuple[list[str], list[str], list[dict]]:
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
        all_titles = []
        seen_all = set()
        seen_aw = set()
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
                    if sv < need <= ev and title not in seen_aw:
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
                    if d >= need and title not in seen_aw:
                        awarded.append(title); seen_aw.add(title)
                        awarded_meta.append({"title": title, "origin": origin})
                elif rtype == "session_time":
                    min_s = int(cond.get("min_seconds", cond.get("min", 0)))
                    if int(duration_sec or 0) >= min_s and title not in seen_aw:
                        awarded.append(title); seen_aw.add(title)
                        awarded_meta.append({"title": title, "origin": origin})
            except Exception:
                continue
        return awarded, all_titles, awarded_meta
        
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
        cdir = p_custom(self.cfg)
        placeholder = "put_your_custom_achievements_here_click_me.json"
        if os.path.isdir(cdir):
            for fn in os.listdir(cdir):
                if not fn.lower().endswith(".json"):
                    continue
                if fn.lower() == placeholder:
                    continue
                fpath = os.path.join(cdir, fn)
                data = load_json(fpath, {}) or {}

                for r in (data.get("rules") or []):
                    if not isinstance(r, dict):
                        continue
                    if self._is_rule_global(r, origin="custom"):
                        t = (r.get("title") or "Achievement").strip()
                        if t not in seen_titles:
                            seen_titles.add(t)
                            r2 = dict(r)
                            r2["_origin"] = "custom"
                            rules_out.append(r2)
                for ex in (data.get("examples") or []):
                    if not isinstance(ex, dict) or ex.get("rom") != rom:
                        continue
                    for r in (ex.get("achievements") or []):
                        if not isinstance(r, dict):
                            continue
                        if self._is_rule_global(r, origin="custom"):
                            t = (r.get("title") or "Achievement").strip()
                            if t not in seen_titles:
                                seen_titles.add(t)
                                r2 = dict(r)
                                r2["_origin"] = "custom"
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
                if isinstance(cur, list) and len(cur) >= 40:
                    return
            except Exception:
                pass
        try:
            rules = self._generate_default_global_rules()
            save_json(path, {"rules": rules})
            log(self.cfg, f"global_achievements.json created/refreshed with {len(rules)} rules")
        except Exception as e:
            log(self.cfg, f"[GLOBAL_ACH] generation failed: {e}", "WARN")

    def _ensure_custom_placeholder(self):
        path = os.path.join(p_custom(self.cfg), "PUT_YOUR_CUSTOM_ACHIEVEMENTS_HERE_CLICK_ME.json")
        if not os.path.exists(path):
            payload = {
                "examples": [
                    {
                        "rom": "afm_113b",
                        "achievements": [
                            {
                                "title": "AFM – First Game (Session)",
                                "scope": "session",
                                "condition": {
                                    "type": "nvram_delta",
                                    "field": "Games Started",
                                    "min": 1
                                }
                            },
                            {
                                "title": "AFM – 10 Ramps (Session)",
                                "scope": "session",
                                "condition": {
                                    "type": "nvram_delta",
                                    "field": "Ramps Made",
                                    "min": 10
                                }
                            },
                            {
                                "title": "AFM – 5 Minutes (Session)",
                                "scope": "session",
                                "condition": {
                                    "type": "session_time",
                                    "min_seconds": 300
                                }
                            },
                            {
                                "title": "AFM – 15 Minutes (Global)",
                                "scope": "global",
                                "condition": {
                                    "type": "session_time",
                                    "min_seconds": 900
                                }
                            }
                        ]
                    }
                ]
            }
            save_json(path, payload)
            log(self.cfg, "Custom placeholder created")

    def _rolling_txt_limit(self, rom: Optional[str]):
        if not rom:
            return
        patterns = [
            os.path.join(p_session(self.cfg), f"{sanitize_filename(rom)}__*.txt"),
            os.path.join(p_session(self.cfg), f"*_{sanitize_filename(rom)}_*.txt")
        ]
        files = []
        for pat in patterns:
            files.extend(glob.glob(pat))
        files = sorted(files, key=lambda x: os.path.getmtime(x))
        while len(files) > ROLLING_HISTORY_PER_ROM:
            old = files.pop(0)
            try:
                os.remove(old)
                log(self.cfg, f"Session limit reached – removed oldest: {old}")
            except Exception as e:
                log(self.cfg, f"Could not remove old session: {e}", "WARN")

    def _highlights_history_limit(self, keep: int = 10):
        try:
            ensure_dir(p_highlights(self.cfg))
            combined = glob.glob(os.path.join(p_highlights(self.cfg), "*.session.json"))
            latest_path = os.path.join(p_highlights(self.cfg), "session_latest.json")
            cand = [p for p in combined if os.path.abspath(p) != os.path.abspath(latest_path)]
            cand.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            for pth in cand[keep:]:
                try:
                    os.remove(pth)
                except Exception as e:
                    log(self.cfg, f"[HIGHLIGHTS] Could not remove {pth}: {e}", "WARN")
        except Exception as e:
            log(self.cfg, f"[HIGHLIGHTS] History enforcement failed: {e}", "WARN")

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
            }

            save_json(summary_path, payload)

            try:
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                hist_path = os.path.join(p_highlights(self.cfg), f"{ts}.session.json")
                save_json(hist_path, payload)
            except Exception as e:
                log(self.cfg, f"[SUMMARY] write historical session failed: {e}", "WARN")

        except Exception as e:
            log(self.cfg, f"[SUMMARY] export failed: {e}", "WARN")


    def _ach_state_load(self) -> dict:
        p = f_achievements_state(self.cfg)
        return secure_load_json(p, {"global": {}, "session": {}})

    def _ach_state_save(self, state: dict):
        p = f_achievements_state(self.cfg)
        secure_save_json(p, state)

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

    def _ach_record_unlocks(self, kind: str, rom: str, titles: list):
        if not rom or not titles:
            return
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        state = self._ach_state_load()
        bucket = state.setdefault(kind, {})
        lst = bucket.setdefault(rom, [])

        def _entry_title(e):
            try:
                return str(e.get("title")).strip()
            except Exception:
                return str(e).strip()
        seen = { _entry_title(e) for e in lst if _entry_title(e) }
        added = 0
        for t in titles:
            if isinstance(t, dict):
                title = str(t.get("title", "")).strip()
                if not title or title in seen:
                    continue
                entry = {"title": title, "ts": now_iso}
                if t.get("origin"):
                    entry["origin"] = str(t["origin"])
                lst.append(entry)
                seen.add(title)
                added += 1
            else:
                title = str(t).strip()
                if not title or title in seen:
                    continue
                lst.append({"title": title, "ts": now_iso})
                seen.add(title)
                added += 1
        if added:
            self._ach_state_save(state)
            try:
                if getattr(self, "bridge", None) and hasattr(self.bridge, "achievements_updated"):
                    self.bridge.achievements_updated.emit()
            except Exception:
                pass
  
    def _emit_achievement_toasts(self, titles, seconds: int = 5):
        try:
            for t in titles or []:
                if isinstance(t, dict):
                    title = str(t.get("title", "")).strip()
                else:
                    title = str(t).strip()
                    
                title = title.replace(" (Session)", "").replace(" (Global)", "")
                
                if title:
                    try:
                        self.bridge.ach_toast_show.emit(title, self.current_rom or "", int(seconds))
                    except Exception:
                        pass
        except Exception:
            pass  
  
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

    # -------------------------------------------------------------------------
    # Session Lifecycle Management
    # -------------------------------------------------------------------------

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
        is_challenge = str(ch.get("kind", "")).lower() in ("timed", "oneball", "flip")
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
                            CloudSync.upload_achievement_progress(self.cfg, self.current_rom, unlocked_total, total_achs)
                    except Exception as e:
                        log(self.cfg, f"[CLOUD] Progress upload failed: {e}", "WARN")

            try:
                if (self.cfg.OVERLAY or {}).get("auto_show_on_end", True) and not is_challenge:
                    if self.current_rom and self._has_any_map(self.current_rom):
                        self.bridge.overlay_show.emit()
                    else:
                        log(self.cfg, f"[OVERLAY] Skipped auto-show because no NVRAM map exists for {self.current_rom}")
            except Exception as e:
                log(self.cfg, f"[OVERLAY] auto-show emit failed: {e}", "WARN")

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

            if cache_path == vpx_path and cache_rom and (now - cache_ts) < 120:
                rom = cache_rom
            else:
                rom = run_vpxtool_get_rom(self.cfg, vpx_path)
                if rom:
                    self._rom_detect_cache = {"vpx_path": vpx_path, "rom": rom, "ts": now}
                    try:
                        log(self.cfg, f"[ROM] VPXTOOL: {rom}")
                    except Exception:
                        pass

        clean_table = table_fragment[:-4] if table_fragment.lower().endswith(".vpx") else table_fragment

        if not rom:
            try:
                log(self.cfg, f"[ROM] vpxtool failed for table '{vpx_filename}'", "WARN")
            except Exception:
                pass
            return None

        return {"table": clean_table, "rom": rom, "vpx_file": vpx_path or ""}

    # -------------------------------------------------------------------------
    # Monitoring Loop & Thread Control
    # -------------------------------------------------------------------------

    def _thread_main(self):
        log(self.cfg, ">>> watcher thread running")
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

                if active_rom is None and rom:
                    self.on_session_start(rom, is_rom=True)
                    active_rom = rom
                    self._emit_mini_info_if_missing_map(rom, 5)

                elif active_rom and rom and rom != active_rom:
                    self.on_session_end()
                    active_rom = None
                    self.on_session_start(rom, is_rom=True)
                    active_rom = rom
                    self._emit_mini_info_if_missing_map(rom, 5)

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
            else:
                if active_rom is not None:

                    self._missing_table_ticks += 1
                    if self._missing_table_ticks >= 4: 
                        self.on_session_end()
                        active_rom = None
                        self._missing_table_ticks = 0

            time.sleep(0.5)

    def start(self):
        if getattr(self, "thread", None) and self.thread.is_alive():
            return
        try:
            self.bootstrap()
        except Exception as e:
            log(self.cfg, f"[BOOTSTRAP] failed: {e}", "WARN")
        try:
            self._ensure_global_ach()
        except Exception as e:
            log(self.cfg, f"[GLOBAL_ACH] ensure failed: {e}", "WARN")
        try:
            self._ensure_custom_placeholder()
        except Exception as e:
            log(self.cfg, f"[CUSTOM_PLACEHOLDER] ensure failed: {e}", "WARN")
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
            
class Bridge(QObject):
    overlay_trigger = pyqtSignal()
    overlay_show = pyqtSignal()
    mini_info_show = pyqtSignal(str, int)
    ach_toast_show = pyqtSignal(str, str, int)
    challenge_timer_start = pyqtSignal(int)
    challenge_timer_stop = pyqtSignal()
    challenge_warmup_show = pyqtSignal(int, str)
    challenge_info_show = pyqtSignal(str, int, str)
    challenge_speak = pyqtSignal(str)
    achievements_updated = pyqtSignal()
    flip_counter_total_show = pyqtSignal(int, int, int)  
    flip_counter_total_update = pyqtSignal(int, int, int)
    flip_counter_total_hide = pyqtSignal()   
    
    prefetch_started = pyqtSignal()
    prefetch_progress = pyqtSignal(str)
    prefetch_finished = pyqtSignal(str)                     

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]

WH_KEYBOARD_LL = 13

class GlobalKeyHook:
    def __init__(self, bindings: list[dict]):
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._hook = None
        self._proc = None
        self._bindings = list(bindings or [])

    def update_bindings(self, bindings: list[dict]):
        self._bindings = list(bindings or [])

    def _callback(self, nCode, wParam, lParam):
        try:
            if nCode == 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = int(kb.vkCode)
                for b in self._bindings:
                    try:
                        want = int(b.get("get_vk", lambda: -1)())
                    except Exception:
                        want = -1
                    if want and vk == want:
                        cb = b.get("on_press")
                        if cb:
                            QTimer.singleShot(0, cb)
        except Exception:
            pass
        return self._user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def install(self):
        if self._hook:
            return
        CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
        self._proc = CMPFUNC(self._callback)
        hMod = self._kernel32.GetModuleHandleW(None)
        self._hook = self._user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, hMod, 0)

    def uninstall(self):
        if self._hook:
            try:
                self._user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
        self._hook = None
        self._proc = None
        
class SetupWizardDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Initial Setup – Achievement Paths")
        self.resize(640, 320)
        main = QVBoxLayout(self)
        info = QLabel(
            "Welcome!\n\n"
            "Select paths for:\n"
            "  1) Base achievements data\n"
            "  2) VPinMAME NVRAM directory\n"
            "  3) (Optional) Tables directory\n\n"
            "You can re-run this wizard later."
        )
        info.setWordWrap(True)
        main.addWidget(info)
        def row(label, val, title):
            lay = QHBoxLayout()
            edit = QLineEdit(val)
            btn = QPushButton("…")
            def pick():
                d = QFileDialog.getExistingDirectory(self, title, edit.text().strip() or os.path.expanduser("~"))
                if d:
                    edit.setText(d)
            btn.clicked.connect(pick)
            lay.addWidget(QLabel(label))
            lay.addWidget(edit, 1)
            lay.addWidget(btn)
            return lay, edit
        lay_base, self.ed_base = row("Base:", self.cfg.BASE, "Select Achievements Base Folder")
        lay_nv, self.ed_nvram = row("NVRAM:", self.cfg.NVRAM_DIR, "Select NVRAM Directory")
        lay_tab, self.ed_tables = row("Tables:", self.cfg.TABLES_DIR, "Select Tables Directory (optional)")
        main.addLayout(lay_base); main.addLayout(lay_nv); main.addLayout(lay_tab)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#c04020;font-weight:bold;")
        main.addWidget(self.lbl_status)
        btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_ok = QPushButton("Apply & Start")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._accept_if_valid)
        btns.addStretch(1); btns.addWidget(btn_cancel); btns.addWidget(btn_ok)
        main.addLayout(btns)
        self.btn_ok = btn_ok
        self.ed_base.textChanged.connect(self._validate)
        self.ed_nvram.textChanged.connect(self._validate)
        self._validate()

    def _validate(self):
        base = self.ed_base.text().strip()
        nvram = self.ed_nvram.text().strip()
        errors = []
        if not base:
            errors.append("Missing base path")
        if nvram and not os.path.isdir(nvram):
            errors.append("NVRAM dir does not exist")
        self.btn_ok.setEnabled(len(errors) == 0)
        self.lbl_status.setText(" / ".join(errors) if errors else "")

    def _accept_if_valid(self):
        self._validate()
        if not self.btn_ok.isEnabled():
            return
        self.cfg.BASE = os.path.abspath(self.ed_base.text().strip())
        if self.ed_nvram.text().strip():
            self.cfg.NVRAM_DIR = os.path.abspath(self.ed_nvram.text().strip())
        if self.ed_tables.text().strip():
            self.cfg.TABLES_DIR = os.path.abspath(self.ed_tables.text().strip())
        self.cfg.FIRST_RUN = False
        self._ensure_base_layout()
        self.cfg.save()
        log(self.cfg, f"[SETUP] BASE={self.cfg.BASE} NVRAM={self.cfg.NVRAM_DIR} TABLES={self.cfg.TABLES_DIR}")
        self.accept()

    def _ensure_base_layout(self):
        try:
            ensure_dir(self.cfg.BASE)
            for sub in [
                "NVRAM_Maps",
                "NVRAM_Maps/maps",
                "session_stats",
                "session_stats/Highlights",
                "rom_specific_achievements",
                "custom_achievements",
            ]:
                ensure_dir(os.path.join(self.cfg.BASE, sub))
        except Exception:
            pass

class OverlayWindow(QWidget):
    TITLE_OFFSET_X = 0
    TITLE_OFFSET_Y = 0
    CLAMP_TITLE = True
    ROTATION_DEBOUNCE_MS = 1

    def _resolve_background_url(self, bg: str) -> str | None:
        def is_img(p: str) -> bool:
            return p.lower().endswith((".png", ".jpg", ".jpeg"))
        if isinstance(bg, str) and bg and bg.lower() != "auto":
            if os.path.isfile(bg) and is_img(bg):
                return bg.replace("\\", "/")
        for fn in ("overlay_bg.png", "overlay_bg.jpg", "overlay_bg.jpeg"):
            p = os.path.join(APP_DIR, fn)
            if os.path.isfile(p):
                return p.replace("\\", "/")
        return None

    def _show_live_unrotated(self):
        try:
            self.rotated_label.hide()
        except Exception:
            pass
        try:
            self.container.show()
            self.text_container.show()
            self.title.show()
            self.body.show()
        except Exception:
            pass

    def _icon_local(self, key: str) -> str:
        use_emojis = not bool(self.parent_gui.cfg.OVERLAY.get("prefer_ascii_icons", False))
        if use_emojis:
            emoji_map = {
                "best_ball": "🔥",
                "extra_ball": "➕",
            }
            return emoji_map.get(key, "•")
        else:
            ascii_map = {
                "best_ball": "[BB]",
                "extra_ball": "[EB]",
            }
            return ascii_map.get(key, "[*]")

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._layout_positions)
        if self.portrait_mode:
            QTimer.singleShot(0, lambda: self.request_rotation(force=True))
        else:
            QTimer.singleShot(0, self._show_live_unrotated)
            
    def _alpha_bbox(self, img: QImage, min_alpha: int = 8) -> QRect:
        w, h = img.width(), img.height()
        if w == 0 or h == 0:
            return QRect(0, 0, 0, 0)
        top = None
        left = None
        right = -1
        bottom = -1
        for y in range(h):
            for x in range(w):
                if img.pixelColor(x, y).alpha() >= min_alpha:
                    if top is None:
                        top = y
                    bottom = y
                    if left is None or x < left:
                        left = x
                    if x > right:
                        right = x
        if top is None:
            return QRect(0, 0, 0, 0)
        return QRect(left, top, right - left + 1, bottom - top + 1)

    def _ref_screen_geometry(self) -> QRect:
        try:
            win = self.windowHandle()
            if win and win.screen():
                return win.screen().geometry()
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        screens = QApplication.screens() or []
        return screens[0].geometry() if screens else QRect(0, 0, 1280, 720)

    def _register_raw_input(self):
        try:
            hwnd = int(self.winId())
            register_raw_input_for_window(hwnd)
        except Exception:
            pass

    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Watchtower Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ov = self.parent_gui.cfg.OVERLAY
        self.scale_pct = int(ov.get("scale_pct", 100))
        self.portrait_mode = bool(ov.get("portrait_mode", True))
        self.rotate_ccw = bool(ov.get("portrait_rotate_ccw", True))
        self.position = "center"
        self.lines_per_category = int(ov.get("lines_per_category", 5))
        
        self.font_family = ov.get("font_family", "Segoe UI")
        self._base_title_size = int(ov.get("base_title_size", 36))
        self._base_body_size = int(ov.get("base_body_size", 20))
        self._base_hint_size = int(ov.get("base_hint_size", 16))
        self._body_pt = self._base_body_size
        self._current_combined = None
        self._current_title = None
        self._rotation_pending = False
        self._apply_geometry()
        self.bg_url = self._resolve_background_url(ov.get("background", "auto"))
        self.container = QWidget(self)
        self.container.setObjectName("overlay_bg")
        self.container.setGeometry(0, 0, self.width(), self.height())
        if self.bg_url:
            css = ("QWidget#overlay_bg {"
                   f"border-image: url('{self.bg_url}') 0 0 0 0 stretch stretch;"
                   "background:rgba(0,0,0,255);border:2px solid #00E5FF;border-radius:18px;}")
        else:
            css = ("QWidget#overlay_bg {background:rgba(0,0,0,255);"
                   "border:2px solid #00E5FF;border-radius:18px;}")
        self.container.setStyleSheet(css)
        self.text_container = QWidget(self)
        self.text_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.text_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.text_container.setGeometry(0, 0, self.width(), self.height())
        self.title = QLabel("Highlights", self.text_container)
        self.body = QLabel(self.text_container)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setWordWrap(True)
        for lab in (self.title, self.body):
            lab.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            lab.setAutoFillBackground(False)
            
        self.title.setStyleSheet("color:#FFFFFF;background:transparent;")
        self.body.setStyleSheet("color:#FFFFFF;background:transparent;")
        
        self._apply_scale(self.scale_pct)
        self.rotated_label = QLabel(self)
        self.rotated_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rotated_label.setStyleSheet("background:transparent;")
        self.rotated_label.hide()
        self._rot_in_progress = False
        self._font_update_in_progress = False
        self._layout_positions()
        QTimer.singleShot(0, self._register_raw_input)

    def request_rotation(self, force: bool = False):
        if not self.portrait_mode:
            return
        if self._rotation_pending and not force:
            return
        self._rotation_pending = True
        def _do():
            try:
                self._apply_rotation_snapshot(force=True)
            finally:
                self._rotation_pending = False
        QTimer.singleShot(self.ROTATION_DEBOUNCE_MS if not force else 0, _do)

    def _apply_geometry(self):
        ref = self._ref_screen_geometry()
        if self.portrait_mode:
            base_h = int(ref.height() * 0.55)
            base_w = int(base_h * 9 / 16)
        else:
            base_w = int(ref.width() * 0.40)
            base_h = int(ref.height() * 0.30)
        w = max(120, int(base_w * self.scale_pct / 100))
        h = max(120, int(base_h * self.scale_pct / 100))
        screens = QApplication.screens() or []
        if screens:
            vgeo = screens[0].geometry()
            for s in screens[1:]:
                vgeo = vgeo.united(s.geometry())
        else:
            vgeo = QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY
        if ov.get("use_xy", False):
            x = int(ov.get("pos_x", 0))
            y = int(ov.get("pos_y", 0))
        else:
            pad = 20
            pos = (getattr(self, "position", "center") or "center").lower()
            mapping = {
                "top-left": (vgeo.left() + pad, vgeo.top() + pad),
                "top-right": (vgeo.right() - w - pad, vgeo.top() + pad),
                "bottom-left": (vgeo.left() + pad, vgeo.bottom() - h - pad),
                "bottom-right": (vgeo.right() - w - pad, vgeo.bottom() - h - pad),
                "center-top": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.top() + pad),
                "center-bottom": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.bottom() - h - pad),
                "center-left": (vgeo.left() + pad, vgeo.top() + (vgeo.height() - h) // 2),
                "center-right": (vgeo.right() - w - pad, vgeo.top() + (vgeo.height() - h) // 2),
                "center": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.top() + (vgeo.height() - h) // 2)
            }
            x, y = mapping.get(pos, mapping["center"])
        self.setGeometry(x, y, w, h)
        if hasattr(self, "container"):
            self.container.setGeometry(0, 0, w, h)
        if hasattr(self, "text_container"):
            self.text_container.setGeometry(0, 0, w, h)

    def _layout_positions(self):
        self._layout_positions_for(self.width(), self.height())
        if self.portrait_mode:
            self.request_rotation()

    def _layout_positions_for(self, w: int, h: int, portrait_pre_render: bool = False):
        if hasattr(self, "text_container"):
            self.text_container.setGeometry(0, 0, w, h)
        pad = 24
        try:
            self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.title.setIndent(0)
            self.title.setMargin(0)
            self.title.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.title.adjustSize()
        t_h = self.title.sizeHint().height()
        if not self.portrait_mode:
            self.title.setGeometry(0, pad, w, t_h)
            body_top = self.title.y() + t_h + 10
            body_h = h - body_top - pad
            body_w = int(w * 0.9)
            body_x = (w - body_w) // 2
            try:
                self.body.setContentsMargins(0, 0, 0, 0)
            except Exception:
                pass
            self.body.setGeometry(body_x, body_top, body_w, max(80, body_h))
            return
        self.title.setGeometry(0, pad, w, t_h)
        body_w = int(w * 0.92)
        body_x = (w - body_w) // 2
        body_top = pad + t_h + 10
        body_h = h - body_top - pad
        try:
            self.body.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.body.setGeometry(body_x, body_top, body_w, max(80, body_h))

    def _apply_scale(self, scale_pct: int):
        r = scale_pct / 100.0
        body_pt = max(4, int(round(self._base_body_size * r)))
        title_pt = max(6, int(round(body_pt * 1.35)))
        
        self._body_pt = body_pt
        self.title.setFont(QFont(self.font_family, title_pt, QFont.Weight.Bold))
        self.body.setFont(QFont(self.font_family, body_pt))
        self.body.setStyleSheet(f"color:#FFFFFF;background:transparent;font-size:{body_pt}pt;font-family:'{self.font_family}';")

    def _composition_mode_source_over(self):
        try:
            return QPainter.CompositionMode.CompositionMode_SourceOver
        except Exception:
            try:
                return getattr(QPainter, "CompositionMode_SourceOver")
            except Exception:
                return None

    def _apply_rotation_snapshot(self, force: bool = False):
        if not self.portrait_mode:
            self.rotated_label.hide()
            self.container.show()
            self.text_container.show()
            self.title.show()
            self.body.show()
            return
        if getattr(self, "_rot_in_progress", False):
            return
        self._rot_in_progress = True
        try:
            W, H = self.width(), self.height()
            if W <= 0 or H <= 0:
                return
            angle = -90 if getattr(self, "rotate_ccw", True) else 90
            if self.bg_url and os.path.isfile(self.bg_url):
                pm = QPixmap(self.bg_url)
                if not pm.isNull():
                    rot_pm = pm.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
                    scaled = rot_pm.scaled(W, H, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                           Qt.TransformationMode.SmoothTransformation)
                    sw, sh = scaled.width(), scaled.height()
                    cx = max(0, (sw - W) // 2)
                    cy = max(0, (sh - H) // 2)
                    bg_img = scaled.copy(cx, cy, min(W, sw - cx), min(H, sh - cy)).toImage().convertToFormat(
                        QImage.Format.Format_ARGB32_Premultiplied)
                else:
                    bg_img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied); bg_img.fill(Qt.GlobalColor.black)
            else:
                bg_img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied); bg_img.fill(Qt.GlobalColor.black)
            pre_w, pre_h = H, W
            old_geom = self.text_container.geometry()
            old_title_vis = self.title.isVisible()
            old_body_vis = self.body.isVisible()
            self.text_container.setGeometry(0, 0, pre_w, pre_h)
            self.title.setVisible(True)
            self.body.setVisible(True)
            self._layout_positions_for(pre_w, pre_h, portrait_pre_render=False)
            QApplication.processEvents()
            content_pre = QImage(pre_w, pre_h, QImage.Format.Format_ARGB32_Premultiplied)
            content_pre.fill(Qt.GlobalColor.transparent)
            p_all = QPainter(content_pre)
            try:
                self.text_container.render(p_all)
            finally:
                p_all.end()
            content_rot = content_pre.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            self.container.hide()
            self.text_container.hide()
            final_img = QImage(bg_img)
            p_final = QPainter(final_img)
            try:
                mode = self._composition_mode_source_over()
                if mode is not None:
                    p_final.setCompositionMode(mode)
                dx = (W - content_rot.width()) // 2
                dy = (H - content_rot.height()) // 2
                p_final.drawImage(dx, dy, content_rot)

                pen = QPen(QColor("#00E5FF"))
                pen.setWidth(2)
                p_final.setPen(pen)
                p_final.setBrush(Qt.BrushStyle.NoBrush)
                p_final.drawRoundedRect(1, 1, W - 2, H - 2, 18, 18)
            finally:
                p_final.end()
            self.text_container.setGeometry(old_geom)
            self.title.setVisible(old_title_vis)
            self.body.setVisible(old_body_vis)

            self.rotated_label.setGeometry(0, 0, W, H)
            self.rotated_label.setPixmap(QPixmap.fromImage(final_img))
            self.rotated_label.show()
            self.rotated_label.raise_()
        except Exception as e:
            print("[overlay] portrait render failed:", e)
            self.rotated_label.hide()
            self.container.show()
            self.text_container.show()
        finally:
            self._rot_in_progress = False

    def apply_font_from_cfg(self, ov: dict):
        if getattr(self, "_font_update_in_progress", False):
            return
        self._font_update_in_progress = True
        try:
            self.font_family = ov.get("font_family", self.font_family)
            self._base_body_size = int(ov.get("base_body_size", self._base_body_size))
            self._base_title_size = int(ov.get("base_title_size", self._base_title_size))
            self._base_hint_size = int(ov.get("base_hint_size", self._base_hint_size))
            self._apply_scale(self.scale_pct)
            def _finish():
                try:
                    if self._current_combined:
                        self._render_fixed_columns()
                    else:
                        self._layout_positions()
                        self.request_rotation(force=True)
                finally:
                    self._font_update_in_progress = False
            QTimer.singleShot(0, _finish)
        except Exception:
            self._font_update_in_progress = False

    def apply_portrait_from_cfg(self, ov: dict):
        self.portrait_mode = bool(ov.get("portrait_mode", self.portrait_mode))
        self.rotate_ccw = bool(ov.get("portrait_rotate_ccw", self.rotate_ccw))
        self._apply_geometry()
        self._layout_positions()
        if self.portrait_mode:
            self.request_rotation(force=True)
        else:
            self._show_live_unrotated()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.container.setGeometry(0, 0, self.width(), self.height())
        self._layout_positions()
        if self.portrait_mode:
            self.request_rotation()
        else:
            self._show_live_unrotated()

    def set_placeholder(self, session_title: Optional[str] = None):
        self._current_combined = None
        self._current_title = session_title or "Highlights"
        self.title.setText(self._current_title)
        self.body.setText("<div>Loading highlights …</div>")
        self._layout_positions()
        self.request_rotation(force=True)

    def set_html(self, html: str, session_title: Optional[str] = None):
        self._current_combined = None
        self._current_title = "Highlights" if session_title is None else session_title
        self.title.setText(self._current_title)
        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self._layout_positions()
        self.request_rotation(force=True)

    def set_combined(self, combined: dict, session_title: Optional[str] = None):
        self._current_combined = combined or {}
        self._current_title = "Highlights" if session_title is None else session_title
        self._render_fixed_columns()

        total_achs = 0
        unlocked_total = 0
        pct = 0.0
        try:
            if rom_name and rom_name != "Unknown ROM" and self.parent_gui.watcher._has_any_map(rom_name):
                s_rules = self.parent_gui.watcher._collect_player_rules_for_rom(rom_name)
                
                unique_achs = set()
                for r in s_rules:
                    if isinstance(r, dict) and r.get("title"):
                        unique_achs.add(str(r.get("title")).strip())
                total_achs = len(unique_achs)
                
                if total_achs > 0:
                    state = self.parent_gui.watcher._ach_state_load()
                    
                    unlocked_titles = set()
                    for e in state.get("session", {}).get(rom_name, []):
                        t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                        if t: unlocked_titles.add(t)
                        
                    unlocked_total = len(unlocked_titles)
                    pct = round((unlocked_total / total_achs) * 100, 1)
        except Exception:
            pass

        total_achs = 0
        unlocked_total = 0
        pct = 0.0
        try:
            if rom_name and rom_name != "Unknown ROM" and self.parent_gui.watcher._has_any_map(rom_name):
                g_rules = self.parent_gui.watcher._collect_global_rules_for_rom(rom_name)
                s_rules = self.parent_gui.watcher._collect_player_rules_for_rom(rom_name)
                total_achs = len(g_rules) + len(s_rules)
                
                if total_achs > 0:
                    state = self.parent_gui.watcher._ach_state_load()
                    unlocked_g = len(state.get("global", {}).get(rom_name, []))
                    unlocked_s = len(state.get("session", {}).get(rom_name, []))
                    unlocked_total = unlocked_g + unlocked_s
                    pct = round((unlocked_total / total_achs) * 100, 1)
        except Exception:
            pass

        style = """
        <style>
          table.hltable { border-collapse: collapse; margin: 0 auto; width: auto; font-size: 1.1em; }
          .hltable th, .hltable td { padding: 0.35em 1.2em; border-bottom: 1px solid rgba(255,255,255,0.15); white-space: nowrap; color: #E0E0E0; }
          .hltable th { text-align: center; background: rgba(0, 229, 255, 0.15); color: #00E5FF; font-weight: bold; font-size: 1.1em; }
          .hltable td.left { text-align: left; }
          .hltable td.right { text-align: right; font-weight: bold; font-size: 1.15em; color: #FF7F00; }
          .rom-title { text-align: center; font-size: 1.6em; font-weight: bold; color: #FFFFFF; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 0.2em; margin-top: 0.4em; }
          .score-box { text-align: center; font-size: 2.2em; font-weight: bold; margin-bottom: 1.0em; color: #00E5FF; }
        </style>
        """

        def block(entry: dict):
            hld = (entry.get("highlights") or {})
            deltas = (entry.get("deltas") or {})
            
            try:
                score_abs = int(entry.get("score", 0) or 0)
            except Exception:
                score_abs = 0

            lines = []
            
            lines.append(f"<div class='rom-title'>{esc(rom_name)}</div>")
            
            if total_achs > 0:
                safe_pct = max(0.1, min(100.0, pct))
                rem_pct = 100.0 - safe_pct
                
                bar_html = f"""
                <div style='text-align: center; color: #FFFFFF; font-weight: bold; font-size: 1.15em; margin-bottom: 0.3em;'>
                    {unlocked_total} / {total_achs} ({pct}%)
                </div>
                <table align='center' width='75%' style='border: 1px solid #555; background: #1A1A1A; margin-bottom: 1.5em;' cellpadding='0' cellspacing='0'>
                    <tr>
                        <td width='{safe_pct}%' style='background: #FF7F00; height: 12px;'>&nbsp;</td>
                        <td width='{rem_pct}%' style='height: 12px;'>&nbsp;</td>
                    </tr>
                </table>
                """
                lines.append(bar_html)
            else:
                lines.append("<div style='margin-bottom: 1.2em;'></div>")

            if score_abs > 0:
                sc_txt = f"{score_abs:,d}".replace(",", ".")
                lines.append(f"<div class='score-box'>Score: {sc_txt}</div>")
            else:
                lines.append("<div style='margin-bottom: 1.8em;'></div>")

            lines.append("<table align='center' style='border-collapse: collapse; margin: 0 auto; width: auto;'><tr>")
            
            lines.append("<td valign='top' style='padding-right: 20px; border-right: 1px solid rgba(255, 255, 255, 0.4);'>")
            lines.append("<table class='hltable'>")
            has_high = False
            for cat in ["Power", "Precision", "Fun"]:
                arr = hld.get(cat, [])
                if arr:
                    has_high = True
                    lines.append(f"<tr><th colspan='2'>{esc(cat)}</th></tr>")
                    for x in arr[:max(1, limit)]:
                        parts = x.rsplit(" – ", 1)
                        if len(parts) == 2:
                            name, val = parts[0], parts[1]
                        else:
                            name, val = x, ""
                        lines.append(f"<tr><td class='left'>{esc(name)}</td><td class='right'>{esc(val)}</td></tr>")
            lines.append("</table>")
            if not has_high:
                lines.append("<div style='text-align:center; color:#888; margin-top:1em;'>(No Highlights yet)</div>")
            lines.append("</td>")

            lines.append("<td valign='top' style='padding-left: 20px; border:none;'>")
            lines.append("<table class='hltable'>")
            
            if not deltas:
                lines.append("<tr><td colspan='2' style='text-align:center; color:#888; border:none;'>(No actions yet)</td></tr>")
            else:
                items = sorted(list(deltas.items()), key=lambda x: int(x[1]), reverse=True)
                
                max_rows = 13 
                if len(items) <= max_rows * 2:
                    cols = 2
                else:
                    cols = 3 
                
                max_items = max_rows * cols
                display_items = items[:max_items]
                
                header_html = ""
                for c in range(cols):
                    border = " style='border-left: 2px solid rgba(255,255,255,0.2); padding-left: 1.2em;'" if c > 0 else ""
                    header_html += f"<th{border}>Action</th><th>Count</th>"
                lines.append(f"<tr>{header_html}</tr>")
                
                for i in range(0, len(display_items), cols):
                    row_html = ""
                    for c in range(cols):
                        idx = i + c
                        border = " style='border-left: 2px solid rgba(255,255,255,0.2); padding-left: 1.2em;'" if c > 0 else ""
                        if idx < len(display_items):
                            k, v = display_items[idx]
                            v_str = f"+{v:,}".replace(",", ".")
                            row_html += f"<td class='left'{border}>{esc(k)}</td><td class='right'>{esc(v_str)}</td>"
                        else:
                            row_html += f"<td class='left'{border}></td><td class='right'></td>"
                            
                    lines.append(f"<tr>{row_html}</tr>")
                    
                if len(items) > max_items:
                    lines.append(f"<tr><td colspan='{cols * 2}' style='text-align:center; color:#888; font-size:0.9em;'>(+ {len(items)-max_items} more actions)</td></tr>")
                    
            lines.append("</table>")
            lines.append("</td>")
            
            lines.append("</tr></table>")
            return "".join(lines)

        if not players:
            self.body.setText("<div>-</div>")
            self._layout_positions()
            self.request_rotation(force=True)
            return

        html = style + "<div align='center' style='width:100%;'>" + \
               "".join(f"{block(p)}" for p in players) + \
               "</div>"

        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self._layout_positions()
        self.request_rotation(force=True)
        
class MiniInfoOverlay(QWidget):
    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Info")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ov = self.parent_gui.cfg.OVERLAY or {}
        base_pt = int(ov.get("base_body_size", 20))
        self._body_pt = max(12, base_pt + 3)          
        self._font_family = ov.get("font_family", "Segoe UI")
        self._red = "#FF3B30"                          
        self._hint = "#DDDDDD"                         
        self._bg_color = QColor(0, 0, 0, 255)
        self._radius = 16
        self._pad_w = 28
        self._pad_h = 22
        self._max_text_width = 520
        self._portrait_mode = bool(ov.get("portrait_mode", True))
        self._rotate_ccw = bool(ov.get("portrait_rotate_ccw", True))
        self._remaining = 0
        self._base_msg = ""
        self._last_center = (960, 540)
        self._snap_label = QLabel(self)
        self._snap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snap_label.setStyleSheet("background:transparent;")
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        self.hide()

    def _primary_center(self) -> tuple[int, int]:
        try:
            scr = QApplication.primaryScreen()
            geo = scr.geometry() if scr else QRect(0, 0, 1280, 720)
            return geo.left() + geo.width() // 2, geo.top() + geo.height() // 2
        except Exception:
            return 640, 360

    def _compose_html(self) -> str:
        return (
            f"<span style='color:{self._red};'>{self._base_msg}</span>"
            f"<br><span style='color:{self._hint};'>closing in {self._remaining}…</span>"
        )

    def _render_message_image(self, html: str) -> QImage:
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet(f"color:{self._red};background:transparent;")
        tmp.setFont(QFont(self._font_family, self._body_pt))
        tmp.setWordWrap(True)
        tmp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tmp.setText(html)
        tmp.setFixedWidth(self._max_text_width)
        tmp.adjustSize()
        text_w = tmp.width()
        text_h = tmp.sizeHint().height()
        W = max(200, text_w + self._pad_w)
        H = max(60,  text_h + self._pad_h)
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._bg_color)
            p.drawRoundedRect(0, 0, W, H, self._radius, self._radius)
            margin_left = (W - text_w) // 2
            margin_top = (H - text_h) // 2
            tmp.render(p, QPoint(margin_left, margin_top))
        finally:
            p.end()
        return img

    def _refresh_view(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._portrait_mode = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
        self._rotate_ccw = bool(ov.get("notifications_rotate_ccw", ov.get("portrait_rotate_ccw", True)))

        html = self._compose_html()
        img = self._render_message_image(html)

        if self._portrait_mode:
            angle = -90 if self._rotate_ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        W, H = img.width(), img.height()
        
        use_saved = bool(ov.get("notifications_saved", False))
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        
        if use_saved:
            if self._portrait_mode:
                x = int(ov.get("notifications_x_portrait", 100))
                y = int(ov.get("notifications_y_portrait", 100))
            else:
                x = int(ov.get("notifications_x_landscape", 100))
                y = int(ov.get("notifications_y_landscape", 100))
        else:
            cx, cy = self._last_center
            x = int(cx - W // 2)
            y = int(cy - H // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(), min(y, geo.bottom() - H))

        self.setGeometry(x, y, W, H)
        self._snap_label.setGeometry(0, 0, W, H)
        self._snap_label.setPixmap(QPixmap.fromImage(img))
        self.show()
        self.raise_()

    def _on_tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self.hide()
            return
        self._refresh_view()

    def show_info(self, message: str, seconds: int = 5, center: tuple[int, int] | None = None, color_hex: str | None = None):
        self._base_msg = str(message or "").strip()
        self._remaining = max(1, int(seconds))
        if color_hex:
            try:
                self._red = color_hex
            except Exception:
                pass
        self._last_center = self._primary_center()
        self._timer.stop()
        self._refresh_view()
        self._timer.start()

def read_active_players(base_dir: str):
    ap_dir = os.path.join(base_dir, "session_stats", "Highlights", "activePlayers")
    if not os.path.isdir(ap_dir):
        return []

    # Nur P1 laden
    p1_files = []
    try:
        for fn in os.listdir(ap_dir):
            if re.search(r"_P1\.json$", fn, re.IGNORECASE):
                p1_files.append(os.path.join(ap_dir, fn))
    except Exception:
        return []

    if not p1_files:
        return []

    p1_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    fp = p1_files[0]

    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [{
            "id": 1,
            "highlights": data.get("highlights", {}),
            "playtime_sec": int(data.get("playtime_sec", 0) or 0),
            "score": int(data.get("score", 0) or 0),
            "title": data.get("title", "Player 1"),
            "player": 1,
        }]
    except Exception:
        return []



class FlipCounterOverlay(QWidget):
    def __init__(self, parent: "MainWindow", total: int, remaining: int, goal: int):
        super().__init__(None)
        self.parent_gui = parent
        self._total = int(total)
        self._remaining = int(remaining)
        self._goal = int(goal)
        self.setWindowTitle("Flip Counter")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background:transparent;")

        self._render_and_place()
        self.show()
        self.raise_()
        try:
            import win32gui, win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
        except Exception:
            pass

    def _compose_image(self) -> QImage:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = int(ov.get("base_body_size", 20))
        title_pt = max(body_pt + 2, int(ov.get("base_title_size", int(body_pt * 1.35))))
        
        title_color = QColor("#FF7F00")
        hi_color = QColor ("#FFFFFF")

        title = f"Total flips: {int(self._total)}/{int(self._goal)}"
        sub = f"Remaining: {int(max(0, self._remaining))}"

        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)

        pad = max(12, int(body_pt * 0.9))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_w = fm_title.horizontalAdvance(title)
        sub_w = fm_body.horizontalAdvance(sub)
        text_w = max(title_w, sub_w)
        text_h = fm_title.height() + vgap + fm_body.height()
        content_w = max(280, text_w + 2 * pad)
        content_h = max(96, text_h + 2 * pad)

        img = QImage(content_w, content_h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            bg = QColor(0, 0, 0, 255)
            radius = 16
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(0, 0, content_w, content_h, radius, radius)
            
            pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(1, 1, content_w - 2, content_h - 2, radius, radius)

            p.setPen(title_color); p.setFont(f_title)
            p.drawText(QRect(0, pad, content_w, fm_title.height()),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), title)

            p.setPen(hi_color); p.setFont(f_body)
            p.drawText(QRect(0, pad + fm_title.height() + vgap, content_w, fm_body.height()),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), sub)
        finally:
            p.end()

        portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
        if portrait:
            ccw = bool(ov.get("flip_counter_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        ov = self.parent_gui.cfg.OVERLAY or {}
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("flip_counter_saved", ov.get("flip_counter_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("flip_counter_x_portrait", 100))
                y = int(ov.get("flip_counter_y_portrait", 100))
            else:
                x = int(ov.get("flip_counter_x_landscape", 100))
                y = int(ov.get("flip_counter_y_landscape", 100))
        else:
            pad = 40
            x = int(geo.left() + pad)
            y = int(geo.top() + pad)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.setGeometry(x, y, W, H)
        self._label.setGeometry(0, 0, W, H)
        self._label.setPixmap(QPixmap.fromImage(img))
        self.show()
        self.raise_()

    def update_counts(self, total: int, remaining: int, goal: int):
        self._total = int(total)
        self._remaining = int(remaining)
        self._goal = int(goal)
        self._render_and_place()
        
class FlipCounterPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 380, height_hint: int = 130):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Flip Counter")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._base_w = max(220, int(width_hint))
        self._base_h = max(90, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()

        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h

        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("flip_counter_x_portrait", 100))
            y0 = int(ov.get("flip_counter_y_portrait", 100))
        else:
            x0 = int(ov.get("flip_counter_x_landscape", 100))
            y0 = int(ov.get("flip_counter_y_landscape", 100))

        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("flip_counter_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h

            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            x = min(max(geo.left(), x), geo.right() - self._w)
            y = min(max(geo.top(),  y), geo.bottom() - self._h)
            self.setGeometry(x, y, self._w, self._h)
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(0, 0, 0, 200))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Drag to position.\nClick the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            x = min(max(geo.left(), target.x()), geo.right() - self._w)
            y = min(max(geo.top(),  target.y()), geo.bottom() - self._h)
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())

class TimerPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 400, height_hint: int = 120):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Challenge Timer")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._base_w = max(200, int(width_hint))
        self._base_h = max(80, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("ch_timer_x_portrait", 100))
            y0 = int(ov.get("ch_timer_y_portrait", 100))
        else:
            x0 = int(ov.get("ch_timer_x_landscape", 100))
            y0 = int(ov.get("ch_timer_y_landscape", 100))
        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ch_timer_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h

            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            x = min(max(geo.left(), x), geo.right() - self._w)
            y = min(max(geo.top(),  y), geo.bottom() - self._h)
            self.setGeometry(x, y, self._w, self._h)
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(0, 0, 0, 200))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Drag to position.\nClick the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            x = min(max(geo.left(), target.x()), geo.right() - self._w)
            y = min(max(geo.top(),  target.y()), geo.bottom() - self._h)
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())

class ToastPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 420, height_hint: int = 120):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Achievement Toast")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._base_w = max(200, int(width_hint))
        self._base_h = max(80, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("ach_toast_x_portrait", 100))
            y0 = int(ov.get("ach_toast_y_portrait", 100))
        else:
            x0 = int(ov.get("ach_toast_x_landscape", 100))
            y0 = int(ov.get("ach_toast_y_landscape", 100))
        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        new_portrait = bool(self._portrait)
        if new_portrait != old_portrait:
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h
            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            x = min(max(geo.left(), x), geo.right() - self._w)
            y = min(max(geo.top(),  y), geo.bottom() - self._h)
            self.setGeometry(x, y, self._w, self._h)
        self.update()
        
    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(0, 0, 0, 200))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Drag to position.\nClick the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            x = min(max(geo.left(), target.x()), geo.right() - self._w)
            y = min(max(geo.top(),  target.y()), geo.bottom() - self._h)
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())

class ChallengeOVPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 500, height_hint: int = 200):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Challenge Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._base_w = max(260, int(width_hint))
        self._base_h = max(120, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("ch_ov_x_portrait", 100))
            y0 = int(ov.get("ch_ov_y_portrait", 100))
        else:
            x0 = int(ov.get("ch_ov_x_landscape", 100))
            y0 = int(ov.get("ch_ov_y_landscape", 100))
        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h
            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            x = min(max(geo.left(), x), geo.right() - self._w)
            y = min(max(geo.top(),  y), geo.bottom() - self._h)
            self.setGeometry(x, y, self._w, self._h)
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(0, 0, 0, 200))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Drag to position.\nClick the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            x = min(max(geo.left(), target.x()), geo.right() - self._w)
            y = min(max(geo.top(),  target.y()), geo.bottom() - self._h)
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())

class MiniInfoPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 420, height_hint: int = 100):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Mini Info Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._base_w = max(200, int(width_hint))
        self._base_h = max(80, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
            
        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._screen_geo()
        
        if bool(ov.get("notifications_saved", False)):
            if self._portrait:
                x0 = int(ov.get("notifications_x_portrait", 100))
                y0 = int(ov.get("notifications_y_portrait", 100))
            else:
                x0 = int(ov.get("notifications_x_landscape", 100))
                y0 = int(ov.get("notifications_y_landscape", 100))
        else:
            # Wenn noch nie gespeichert, starte in der Mitte
            x0 = int(geo.left() + (geo.width() - self._w) // 2)
            y0 = int(geo.top() + (geo.height() - self._h) // 2)
            
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            scr = QApplication.primaryScreen()
            if scr:
                return scr.availableGeometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("notifications_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h
            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            x = min(max(geo.left(), x), geo.right() - self._w)
            y = min(max(geo.top(),  y), geo.bottom() - self._h)
            self.setGeometry(x, y, self._w, self._h)
        self.update()
        
    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(0, 0, 0, 200))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Drag to position.\nClick the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            x = min(max(geo.left(), target.x()), geo.right() - self._w)
            y = min(max(geo.top(),  target.y()), geo.bottom() - self._h)
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())
        
class OverlayPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        self._w, self._h = self._calc_overlay_size()
        
        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._safe_screen_geo()
        
        if bool(ov.get("use_xy", False)):
            x0 = int(ov.get("pos_x", 100))
            y0 = int(ov.get("pos_y", 100))
        else:
            x0 = int(geo.left() + (geo.width() - self._w) // 2)
            y0 = int(geo.top() + (geo.height() - self._h) // 2)
            
        w_clamp = min(self._w, geo.width())
        h_clamp = min(self._h, geo.height())
        
        x = max(geo.left(), min(x0, geo.right() - w_clamp))
        y = max(geo.top(),  min(y0, geo.bottom() - h_clamp))
        
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _safe_screen_geo(self) -> QRect:
        try:
            scr = QApplication.primaryScreen()
            if scr:
                return scr.availableGeometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("portrait_mode", True))
            self._ccw = bool(ov.get("portrait_rotate_ccw", True))
        except Exception:
            self._portrait = True
            self._ccw = True

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        scale_pct = int(ov.get("scale_pct", 100))
        ref = self._safe_screen_geo()
        if self._portrait:
            base_h = int(ref.height() * 0.55)
            base_w = int(base_h * 9 / 16)
        else:
            base_w = int(ref.width() * 0.40)
            base_h = int(ref.height() * 0.30)
        w = max(120, int(base_w * scale_pct / 100))
        h = max(120, int(base_h * scale_pct / 100))
        return w, h
        
    def apply_portrait_from_cfg(self):
        self._sync_from_cfg()
        self._w, self._h = self._calc_overlay_size()
        g = self.geometry()
        x, y = g.x(), g.y()
        geo = self._safe_screen_geo()
        w_clamp = min(self._w, geo.width())
        h_clamp = min(self._h, geo.height())
        x = max(geo.left(), min(x, geo.right() - w_clamp))
        y = max(geo.top(),  min(y, geo.bottom() - h_clamp))
        self.setGeometry(x, y, self._w, self._h)
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(0, 0, 0, 200))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Drag to position.\nClick the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._safe_screen_geo()
            w_clamp = min(self._w, geo.width())
            h_clamp = min(self._h, geo.height())
            x = max(geo.left(), min(target.x(), geo.right() - w_clamp))
            y = max(geo.top(),  min(target.y(), geo.bottom() - h_clamp))
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())

class AchToastWindow(QWidget):
    finished = pyqtSignal()
    def __init__(self, parent: "MainWindow", title: str, rom: str, seconds: int = 5):
        super().__init__(None)
        self.parent_gui = parent
        self._title = str(title or "").strip()
        self._rom = str(rom or "").strip()
        self._seconds = max(1, int(seconds))
        self._is_closing = False  
        self.setWindowTitle("Achievement")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background:transparent;")
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._remaining = self._seconds
        self._render_and_place()
        self._timer.start()
        self.show()
        self.raise_()

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._remaining = 0
            try:
                self._timer.stop()
            except Exception:
                pass
            
            if not getattr(self, "_is_closing", False):
                self._is_closing = True
                try:
                    self.finished.emit()
                except Exception:
                    pass
                QTimer.singleShot(200, self.close)
            return
        self._render_and_place()

    def closeEvent(self, e):
        if not getattr(self, "_is_closing", False):
            self._is_closing = True
            try:
                self.finished.emit()
            except Exception:
                pass
        super().closeEvent(e)

    def _icon_pixmap(self, size: int = 40) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setBrush(QColor("#FFD700"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, size, size)
            p.setBrush(QColor("#FFFFFF"))
            cx = int(size * 0.25)
            cs = int(size * 0.5)
            p.drawEllipse(cx, cx, cs, cs)
        finally:
            p.end()
        return pm
        
    def _compose_image(self) -> QImage:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = int(ov.get("base_body_size", 20))
        title_pt = max(body_pt + 2, int(ov.get("base_title_size", int(body_pt * 1.35))))
        
        # Feste Theme-Farben
        title_color = QColor("#FF7F00") # Orange
        text_color = QColor("#FFFFFF")  # Weiß
        
        title = self._title or "Achievement unlocked"
        sub = self._rom or ""
        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)
        icon_sz = max(28, int(body_pt * 2.0))
        pad = max(12, int(body_pt * 0.8))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_w = fm_title.horizontalAdvance(title)
        sub_w = fm_body.horizontalAdvance(sub) if sub else 0
        text_w = max(title_w, sub_w)
        text_h = fm_title.height() + (vgap + fm_body.height() if sub else 0)
        content_h = max(icon_sz, text_h)
        W = pad + icon_sz + gap + text_w + pad
        H = pad + content_h + pad
        W = max(W, 320)
        H = max(H, max(96, int(body_pt * 4.8)))
        
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        
        bg = QColor(0, 0, 0, 200)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        radius = 16
        p.drawRoundedRect(0, 0, W, H, radius, radius)
        
        # Eisblauer Rahmen
        pen = QPen(QColor("#00E5FF"))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, W - 2, H - 2, radius, radius)
        
        pm = self._icon_pixmap(icon_sz)
        iy = int((H - icon_sz) / 2)
        p.drawPixmap(pad, iy, pm)
        x_text = pad + icon_sz + gap
        text_top = int((H - text_h) / 2)
        
        p.setPen(title_color)
        p.setFont(f_title)
        p.drawText(QRect(x_text, text_top, W - x_text - pad, fm_title.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        if sub:
            p.setPen(text_color)
            p.setFont(f_body)
            p.drawText(QRect(x_text, text_top + fm_title.height() + vgap,
                             W - x_text - pad, fm_body.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)
        p.end()
        
        portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
        if portrait:
            ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        return img

    def _render_and_place(self):
        try:
            img = self._compose_image()
            W, H = img.width(), img.height()
            ov = self.parent_gui.cfg.OVERLAY or {}
            portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            use_saved = bool(ov.get("ach_toast_saved", ov.get("ach_toast_custom", False)))
            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)
            if use_saved:
                if portrait:
                    x = int(ov.get("ach_toast_x_portrait", 100))
                    y = int(ov.get("ach_toast_y_portrait", 100))
                else:
                    x = int(ov.get("ach_toast_x_landscape", 100))
                    y = int(ov.get("ach_toast_y_landscape", 100))
            else:
                pad = 40
                x = int(geo.right() - W - pad)
                y = int(geo.bottom() - H - pad)

            x = max(geo.left(), min(x, geo.right() - W))
            y = max(geo.top(),  min(y,  geo.bottom() - H))
            self.setGeometry(x, y, W, H)
            self._label.setGeometry(0, 0, W, H)
            self._label.setPixmap(QPixmap.fromImage(img))
            self.show()
            self.raise_()
            try:
                import win32gui, win32con 
                hwnd = int(self.winId())
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
                )
            except Exception:
                pass
        except Exception as e:
            print(f"[TOAST] render_and_place failed: {e}")

class AchToastManager(QObject):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.parent_gui = parent
        self._queue: list[tuple[str, str, int]] = []
        self._active = False
        self._active_window: Optional[AchToastWindow] = None

    def enqueue(self, title: str, rom: str, seconds: int = 5):
        """Fügt einen Toast in die Warteschlange ein."""
        self._queue.append((title, rom, seconds))
        if not self._active:
            self._show_next()

    def _show_next(self):
        if not self._queue:
            self._active = False
            self._active_window = None
            return
        
        self._active = True
        title, rom, seconds = self._queue.pop(0)
        win = AchToastWindow(self.parent_gui, title, rom, seconds)
        win.finished.connect(self._on_finished)
        self._active_window = win

    def _on_finished(self):
        self._active_window = None
        QTimer.singleShot(250, self._show_next)

class ChallengeCountdownOverlay(QWidget):
    def __init__(self, parent, total_seconds: int = 300):
        super().__init__(parent)
        self.parent_gui = parent
        self._left = max(1, int(total_seconds))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(400, 120)
        self.show()
        try:
            import win32gui, win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
        except Exception:
            pass
        self._render_and_place()

    def _tick(self):
        self._left -= 1
        if self._left <= 0:
            self._left = 0
            try:
                self._timer.stop()
                self._render_and_place()  
            except Exception:
                pass
            QTimer.singleShot(200, self.close)
            return
        self._render_and_place()

    def _render_and_place(self):
        img = self._compose_image()
        if img is None:
            return
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("ch_timer_saved", ov.get("ch_timer_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_timer_x_portrait", 100))
                y = int(ov.get("ch_timer_y_portrait", 100))
            else:
                x = int(ov.get("ch_timer_x_landscape", 100))
                y = int(ov.get("ch_timer_y_landscape", 100))
        else:
            pad = 40
            x = int(geo.left() + pad)
            y = int(geo.bottom() - H - pad)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def _compose_image(self):
        w, h = 400, 120
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(Qt.GlobalColor.white)
        p.fillRect(0, 0, w, h, QColor(0, 0, 0, 255))
        mins, secs = divmod(self._left, 60)
        txt = f"{mins:02d}:{secs:02d}"
        font = QFont("Segoe UI", 48, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, txt)
        p.end()
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_timer_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pass
        return img

    def paintEvent(self, _evt):
        if hasattr(self, "_pix"):
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()
            
class ChallengeSelectOverlay(QWidget):
    def __init__(self, parent: "MainWindow", selected_idx: int = 0):
        super().__init__(parent)
        self.parent_gui = parent
        self._selected = 0 if int(selected_idx) % 2 == 0 else 1
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pulse_t = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50) 
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._pulse_timer.start()
        self._pix = None
        self._render_and_place()
        self.show()
        self.raise_()
        try:
            import win32gui, win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
        except Exception:
            pass

    def closeEvent(self, e):
        try:
            if getattr(self, "_pulse_timer", None):
                self._pulse_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.08) % 1.0
        self._render_and_place()

    def set_selected(self, idx: int):
        self._selected = 0 if int(idx) % 2 == 0 else 1
        self._render_and_place()

    def apply_portrait_from_cfg(self):
        self._render_and_place()

    def _compose_image(self) -> QImage:
        from math import sin, pi

        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        base_body_pt = int(ov.get("base_body_size", 20))
        hint_pt = int(ov.get("base_hint_size", max(12, base_body_pt * 0.8)))
        
        text_color = QColor("#FFFFFF")
        hi_color = QColor("#FF7F00")

        if int(getattr(self, "_selected", 0) or 0) % 2 == 0:
            title_text = "Timed Challenge"
            desc_text = "3:00 minutes playing time."
        else:
            title_text = "Flip Challenge"
            desc_text = "Count Left+Right flips until chosen target."

        w, h = 520, 200
        pad_lr = 20
        top_pad = 24
        bottom_pad = 18
        hint_gap = 10
        avail_w = w - 2 * pad_lr

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 255))
            radius = 16
            p.drawRoundedRect(0, 0, w, h, radius, radius)
            
            pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(1, 1, w - 2, h - 2, radius, radius)

            title_pt = base_body_pt + 6
            desc_pt = max(10, base_body_pt)
            min_title = 12
            min_desc = 10

            flags_wrap_center = int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap)

            def measure_heights(t_pt: int, d_pt: int) -> tuple[int, int]:
                fm_t = QFontMetrics(QFont(font_family, t_pt, QFont.Weight.Bold))
                fm_d = QFontMetrics(QFont(font_family, d_pt))
                rect = QRect(0, 0, avail_w, 10000)
                t_bbox = fm_t.boundingRect(rect, flags_wrap_center, title_text)
                d_bbox = fm_d.boundingRect(rect, flags_wrap_center, desc_text)
                return t_bbox.height(), d_bbox.height()

            fm_hint = QFontMetrics(QFont(font_family, hint_pt))
            hint_h = fm_hint.height()
            max_content_h = h - top_pad - bottom_pad - hint_gap - hint_h

            for _ in range(64):
                t_h, d_h = measure_heights(title_pt, desc_pt)
                total = t_h + 6 + d_h
                if total <= max_content_h:
                    break
                if title_pt > min_title: title_pt -= 1
                if desc_pt > min_desc: desc_pt -= 1
                if title_pt <= min_title and desc_pt <= min_desc: break

            t_h, d_h = measure_heights(title_pt, desc_pt)
            block_h = t_h + 6 + d_h
            content_top = top_pad + max(0, (max_content_h - block_h) // 2)

            p.setPen(hi_color)
            p.setFont(QFont(font_family, title_pt, QFont.Weight.Bold))
            title_rect = QRect(pad_lr, content_top, avail_w, t_h)
            p.drawText(title_rect, flags_wrap_center, title_text)

            p.setPen(text_color)
            p.setFont(QFont(font_family, desc_pt))
            desc_rect = QRect(pad_lr, title_rect.bottom() + 6, avail_w, d_h)
            p.drawText(desc_rect, flags_wrap_center, desc_text)

            p.setPen(QColor("#AAAAAA"))
            p.setFont(QFont(font_family, hint_pt))
            hint_rect = QRect(0, h - bottom_pad - hint_h, w, hint_h)
            p.drawText(hint_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), "Press Hotkey to start")

            # Eisblaue pulsierende Pfeile
            amp = 0.5 + 0.5 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
            alpha = 110 + int(120 * amp)
            scale = 0.9 + 0.2 * amp
            wobble = 2.0 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
            base_h = 18
            ah = int(base_h * scale)
            aw = max(8, int(ah * 0.6))
            cy = title_rect.center().y()
            left_cx = pad_lr + 24 + int(-wobble)
            right_cx = w - pad_lr - 24 + int(wobble)
            
            arrow_color = QColor("#00E5FF")
            arrow_color.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(arrow_color)

            p.drawPolygon(*[QPoint(left_cx - aw // 2, cy), QPoint(left_cx + aw // 2, cy - ah // 2), QPoint(left_cx + aw // 2, cy + ah // 2)])
            p.drawPolygon(*[QPoint(right_cx + aw // 2, cy), QPoint(right_cx - aw // 2, cy - ah // 2), QPoint(right_cx - aw // 2, cy + ah // 2)])

        finally:
            try: p.end()
            except Exception: pass

        try:
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception: pass

        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("ch_ov_saved", ov.get("ch_ov_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_ov_x_portrait", 100))
                y = int(ov.get("ch_ov_y_portrait", 100))
            else:
                x = int(ov.get("ch_ov_x_landscape", 100))
                y = int(ov.get("ch_ov_y_landscape", 100))
        else:
            x = int(geo.left() + (geo.width() - W) // 2)
            y = int(geo.top()  + (geo.height() - H) // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()

class FlipDifficultyOverlay(QWidget):
    def __init__(self, parent: "MainWindow", selected_idx: int = 1,
                 options: list[tuple[str, int]] = None):
        super().__init__(parent)
        self.parent_gui = parent

        # default options expanded/reordered
        default_options = [("Easy", 400), ("Medium", 300), ("Difficult", 200), ("Pro", 100)]
        self._options = list(options) if isinstance(options, list) and options else default_options

        # clamp selection to available options
        self._selected = max(0, min(int(selected_idx or 0), len(self._options) - 1))

        self._pulse_t = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._pulse_timer.start()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pix = None
        self._render_and_place()
        self.show()
        self.raise_()
        try:
            import win32gui, win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
        except Exception:
            pass

    def closeEvent(self, e):
        try:
            if getattr(self, "_pulse_timer", None):
                self._pulse_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.08) % 1.0
        self._render_and_place()

    def set_selected(self, idx: int):
        self._selected = max(0, min(int(idx or 0), len(self._options) - 1))
        self._render_and_place()

    def selected_option(self) -> tuple[str, int]:
        return self._options[self._selected]

    def apply_portrait_from_cfg(self):
        self._render_and_place()

    def _compose_image(self) -> QImage:
        from math import sin, pi
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        base_body_pt = int(ov.get("base_body_size", 20))
        hint_pt = int(ov.get("base_hint_size", max(12, base_body_pt * 0.8)))
        text_color = QColor("#FFFFFF")
        hi_color = QColor("#FF7F00")

        w, h = 560, 240
        pad_lr = 24
        top_pad = 26
        bottom_pad = 18
        gap_title_desc = 8
        avail_w = w - 2 * pad_lr

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 255))
            radius = 16
            p.drawRoundedRect(0, 0, w, h, radius, radius)
            pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(1, 1, w - 2, h - 2, radius, radius)

            title = "Flip Challenge – Choose difficulty"
            p.setPen(hi_color)
            p.setFont(QFont(font_family, base_body_pt + 6, QFont.Weight.Bold))
            fm_t = QFontMetrics(QFont(font_family, base_body_pt + 6, QFont.Weight.Bold))
            t_h = fm_t.height()
            p.drawText(QRect(pad_lr, top_pad, avail_w, t_h),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), title)

            y0 = top_pad + t_h + gap_title_desc
            n = max(1, len(self._options))
            spacing = 15
            total_spacing = spacing * (n - 1)
            box_w = max(80, int((avail_w - total_spacing) / n))
            box_h = 100

            def draw_option(ix: int, name: str, flips: int, selected: bool):
                x = pad_lr + ix * (box_w + spacing)
                rect = QRect(x, y0, box_w, box_h)
                
                if selected:
                    amp = 0.5 + 0.5 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
                    alpha = 40 + int(60 * amp)
                    p.fillRect(rect.adjusted(-4, -4, 4, 4), QColor(255, 127, 0, alpha)) # Oranger Pulse
                    p.setPen(QPen(QColor("#00E5FF"), 2))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
                    
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, 10, 10)

                p.setPen(QColor("#FF7F00") if selected else QColor("#FFFFFF"))
                p.setFont(QFont(font_family, base_body_pt + (2 if selected else 0), QFont.Weight.Bold))
                fm_n = QFontMetrics(QFont(font_family, base_body_pt + (2 if selected else 0), QFont.Weight.Bold))
                name_h = fm_n.height()
                p.drawText(QRect(x, y0 + 10, box_w, name_h),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), name)
                
                p.setFont(QFont(font_family, base_body_pt))
                p.drawText(QRect(x, y0 + 10 + name_h + 6, box_w, base_body_pt + 8),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), f"{int(flips)} flips")

            for i, (nm, fl) in enumerate(self._options):
                draw_option(i, nm, fl, i == self._selected)

            p.setPen(QColor("#AAAAAA"))
            p.setFont(QFont(font_family, hint_pt))
            p.drawText(QRect(0, h - bottom_pad - 18, w, 18),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                       "Select with Left/Right, press Hotkey to start")
        finally:
            try: p.end()
            except Exception: pass

        try:
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception: pass
        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        use_saved = bool(ov.get("ch_ov_saved", ov.get("ch_ov_custom", False)))
        portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_ov_x_portrait", 100)); y = int(ov.get("ch_ov_y_portrait", 100))
            else:
                x = int(ov.get("ch_ov_x_landscape", 100)); y = int(ov.get("ch_ov_y_landscape", 100))
        else:
            x = int(geo.left() + (geo.width() - W) // 2)
            y = int(geo.top()  + (geo.height() - H) // 2)
        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()

import threading, time, os

class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig, watcher: Watcher, bridge: Bridge):
        super().__init__()
        self.cfg = cfg
        self.watcher = watcher
        self.bridge = bridge
        self.setWindowTitle("VPX Achievement Watcher")
        self.resize(1350, 800)
        
        icon = self._get_icon()
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        
        if "player_id" not in self.cfg.OVERLAY:
            self.cfg.OVERLAY["player_id"] = str(uuid.uuid4())[:4]
            self.cfg.save()
            
        self.main_tabs = QTabWidget()
        self.setCentralWidget(self.main_tabs)

        self.bridge.overlay_trigger.connect(self._on_overlay_trigger)
        self.bridge.overlay_show.connect(self._show_overlay_latest)
        self.bridge.mini_info_show.connect(self._on_mini_info_show)
        self.bridge.ach_toast_show.connect(self._on_ach_toast_show)
        self._ach_toast_mgr = AchToastManager(self)
        self.bridge.achievements_updated.connect(self.update_achievements_tab)
        self.bridge.challenge_info_show.connect(self._on_challenge_info_show)
        self.bridge.challenge_timer_start.connect(self._on_challenge_timer_start)
        self.bridge.challenge_timer_stop.connect(self._on_challenge_timer_stop)
        self.bridge.challenge_warmup_show.connect(self._on_challenge_warmup_show)
        self.bridge.challenge_speak.connect(self._on_challenge_speak)
        
        self.bridge.prefetch_started.connect(self._on_prefetch_started)
        self.bridge.prefetch_progress.connect(self._on_prefetch_progress)
        self.bridge.prefetch_finished.connect(self._on_prefetch_finished)
        
        self._prefetch_blink_timer = QTimer(self)
        self._prefetch_blink_timer.setInterval(600)  # Blink-Intervall in ms
        self._prefetch_blink_timer.timeout.connect(self._on_prefetch_blink)
        self._prefetch_blink_state = False
        self._prefetch_msg = ""

        self._build_tab_dashboard()
        self._build_tab_appearance()
        self._build_tab_controls()
        self._build_tab_stats()
        self._build_tab_progress()        
        self._build_tab_available_maps()   
        self._build_tab_cloud() 
        self._build_tab_system()

        self.register_flip_counter_handlers()

        self.timer_stats = QTimer(self)
        self.timer_stats.timeout.connect(self.update_stats)
        self.timer_stats.start(4000)

        self.overlay_refresh_timer = QTimer(self)
        self.overlay_refresh_timer.setInterval(2000)
        self.overlay_refresh_timer.timeout.connect(self._refresh_overlay_live)
        if bool(self.cfg.OVERLAY.get("live_updates", False)):
            self.overlay_refresh_timer.start()

        self.overlay_auto_close_timer = QTimer(self)
        self.overlay_auto_close_timer.setSingleShot(True)
        self.overlay_auto_close_timer.timeout.connect(self._hide_overlay)

        self._joy_toggle_last_mask = 0
        self._joy_toggle_timer = QTimer(self)
        self._joy_toggle_timer.setInterval(50)
        self._joy_toggle_timer.timeout.connect(self._on_joy_toggle_poll)

        self._apply_toggle_source()
        self._last_toggle_ts = 0.0

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            menu = QMenu()
            menu.addAction("Open", self._show_from_tray)
            menu.addAction("Quit GUI", self.quit_all)
            self.tray.setContextMenu(menu)
            self.tray.show()
            
            QTimer.singleShot(1500, lambda: self.tray.showMessage(
                "VPX Achievement Watcher", 
                "Watcher is running in the background!", 
                QSystemTrayIcon.MessageIcon.Information, 
                3000
            ))
        else:
            self.tray = None

        self._overlay_cycle = {"sections": [], "idx": -1}
        self._overlay_busy = False
        self._overlay_last_action = 0.0
        self.overlay = None

        self._challenge_select = None
        self._ch_ov_selected_idx = 0
        self._ch_active_source = None
        self._last_ch_event_src = None
        self._ch_pick_flip_diff = False
        self._ch_flip_diff_idx = 1  
        self._flip_diff_options = [("Easy", 400), ("Medium", 300), ("Difficult", 200), ("Pro", 100)]
        self._flip_diff_select = None

        self.watcher.start()

        self._apply_theme()
        self._check_for_updates() 
        self._init_tooltips_main()
        self._init_overlay_tooltips()

        try:
            self.update_achievements_tab()
            self._init_achievements_timer()
        except Exception:
            pass

        self._refresh_input_bindings()

    def register_flip_counter_handlers(self):
        try:
            self.bridge.flip_counter_total_show.connect(self._on_flip_total_show)
            self.bridge.flip_counter_total_update.connect(self._on_flip_total_update)
            self.bridge.flip_counter_total_hide.connect(self._on_flip_total_hide)
        except Exception:
            pass
        self._flip_total_win = None
        self._flip_counter_picker = None

    def _on_flip_total_show(self, total: int, remaining: int, goal: int):
        try:
            if self._flip_total_win:
                try:
                    self._flip_total_win.close()
                    self._flip_total_win.deleteLater()
                except Exception:
                    pass
            self._flip_total_win = FlipCounterOverlay(self, total, remaining, goal)
        except Exception:
            self._flip_total_win = None

    def _on_flip_total_update(self, total: int, remaining: int, goal: int):
        try:
            if not self._flip_total_win:
                self._on_flip_total_show(total, remaining, goal)
            else:
                self._flip_total_win.update_counts(total, remaining, goal)
        except Exception:
            pass

    def _on_flip_total_hide(self):
        try:
            if self._flip_total_win:
                self._flip_total_win.close()
                self._flip_total_win.deleteLater()
        except Exception:
            pass
        self._flip_total_win = None
        
    def _in_game_now(self) -> bool:
        try:
            w = getattr(self, "watcher", None)
            return bool(w and (w.game_active or w._vp_player_visible()))
        except Exception:
            return False
  
    def _on_flip_counter_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["flip_counter_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass
            
    def _on_flip_counter_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["flip_counter_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass            
            
    def _on_flip_counter_place_clicked(self):
        picker = getattr(self, "_flip_counter_picker", None)
        if picker:
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()

            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["flip_counter_x_portrait"] = int(x)
                self.cfg.OVERLAY["flip_counter_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["flip_counter_x_landscape"] = int(x)
                self.cfg.OVERLAY["flip_counter_y_landscape"] = int(y)
            self.cfg.OVERLAY["flip_counter_saved"] = True
            self.cfg.OVERLAY["flip_counter_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._flip_counter_picker = None
            self.btn_flip_counter_place.setText("Place / Save Flip-Counter position")
            return
        self._flip_counter_picker = FlipCounterPositionPicker(self, width_hint=380, height_hint=130)
        self.btn_flip_counter_place.setText("Save Flip-Counter position")

    def _on_flip_counter_test(self):
        try:
            goal = int(self.cfg.OVERLAY.get("flip_counter_goal_total", 400))
            
            if getattr(self, "_flip_total_test_win", None):
                try: 
                    self._flip_total_test_win.close()
                except Exception: 
                    pass
                    
            self._flip_total_test_win = FlipCounterOverlay(self, total=123, remaining=max(0, goal - 123), goal=goal)
            
            QTimer.singleShot(6000, lambda: (self._flip_total_test_win.close() if self._flip_total_test_win else None))
        except Exception:
            pass
       
    def _challenge_is_active(self) -> bool:
        try:
            ch = getattr(self.watcher, "challenge", {}) or {}
            if not ch.get("active"):
                return False
            if not self._in_game_now():
                ch["active"] = False
                ch["pending_kill_at"] = None
                self.watcher.challenge = ch
                return False
            cur_rom = getattr(self.watcher, "current_rom", None)
            ch_rom = ch.get("rom")
            if cur_rom and ch_rom and str(cur_rom) != str(ch_rom):
                ch["active"] = False
                ch["pending_kill_at"] = None
                self.watcher.challenge = ch
                return False
            return True
        except Exception:
            return False
 
    def _get_hotkey_mods_now(self) -> int:
        import ctypes
        user32 = ctypes.windll.user32

        def pressed(vk: int) -> bool:
            state = user32.GetKeyState(vk)
            return (state & 0x8000) != 0

        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_WIN = 0x0008

        mods = 0
        if pressed(0x10) or pressed(0xA0) or pressed(0xA1):  # Shift / LShift / RShift
            mods |= MOD_SHIFT
        if pressed(0x11) or pressed(0xA2) or pressed(0xA3):  # Ctrl / LCtrl / RCtrl
            mods |= MOD_CONTROL
        if pressed(0x12) or pressed(0xA4) or pressed(0xA5):  # Alt / LAlt / RAlt
            mods |= MOD_ALT
        if pressed(0x5B) or pressed(0x5C):                   # Win links/rechts
            mods |= MOD_WIN

        return mods

    def _fmt_hotkey_label(self, vk: int, mods: int) -> str:
        parts = []
        if mods & 0x0002: parts.append("Ctrl")
        if mods & 0x0004: parts.append("Shift")
        if mods & 0x0001: parts.append("Alt")
        if mods & 0x0008: parts.append("Win")
        parts.append(vk_to_name_en(int(vk)))
        return "+".join(parts)
 
    def _on_overlay_auto_close_toggle(self, state: int):
        enabled = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["overlay_auto_close"] = bool(enabled)
        self.cfg.save()
        try:
            if enabled and self.overlay and self.overlay.isVisible():
                self._start_overlay_auto_close_timer()
            else:
                self.overlay_auto_close_timer.stop()
        except Exception:
            pass

    def _start_overlay_auto_close_timer(self):
        try:
            if bool(self.cfg.OVERLAY.get("overlay_auto_close", False)):
                self.overlay_auto_close_timer.stop()
                self.overlay_auto_close_timer.start(60 * 1000)
        except Exception:
            pass
            
    def _on_ch_ov_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_ov_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_ov_picker") and isinstance(self._ch_ov_picker, ChallengeOVPositionPicker):
                self._ch_ov_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._refresh_challenge_select_overlay()

    def _on_ch_ov_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_ov_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_ov_picker") and isinstance(self._ch_ov_picker, ChallengeOVPositionPicker):
                self._ch_ov_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._refresh_challenge_select_overlay()

    def _on_ch_ov_place_clicked(self):
        picker = getattr(self, "_ch_ov_picker", None)
        if picker and isinstance(picker, ChallengeOVPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ch_ov_x_portrait"] = int(x)
                self.cfg.OVERLAY["ch_ov_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ch_ov_x_landscape"] = int(x)
                self.cfg.OVERLAY["ch_ov_y_landscape"] = int(y)
            self.cfg.OVERLAY["ch_ov_saved"] = True
            self.cfg.OVERLAY["ch_ov_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._ch_ov_picker = None
            self.btn_ch_ov_place.setText("Place / Save ChallengeOV position")
            self._refresh_challenge_select_overlay()
            return
        self._ch_ov_picker = ChallengeOVPositionPicker(self, width_hint=520, height_hint=200)
        self.btn_ch_ov_place.setText("Save ChallengeOV position")
        
    def _on_ch_src_changed(self, kind: str, src: str):
        key = f"challenge_{kind}_input_source"
        self.cfg.OVERLAY[key] = str(src)
        self.cfg.save()
        if kind == "hotkey":
            self.lbl_ch_hotkey_binding.setText(self._challenge_binding_label_text("hotkey"))
        elif kind == "left":
            self.lbl_ch_left_binding.setText(self._challenge_binding_label_text("left"))
        else:
            self.lbl_ch_right_binding.setText(self._challenge_binding_label_text("right"))
        self._refresh_input_bindings()

    def _on_ach_toast_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ach_toast_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ach_toast_place_clicked(self):
        picker = getattr(self, "_toast_picker", None)
        if picker and isinstance(picker, ToastPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ach_toast_x_portrait"] = int(x)
                self.cfg.OVERLAY["ach_toast_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ach_toast_x_landscape"] = int(x)
                self.cfg.OVERLAY["ach_toast_y_landscape"] = int(y)
            self.cfg.OVERLAY["ach_toast_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._toast_picker = None
            self.btn_ach_toast_place.setText("Place / Save position")
            return
        
        body_pt = int(self.cfg.OVERLAY.get("base_body_size", 20))
        width_hint = 420 + max(0, (body_pt - 20) * 6)
        height_hint = 120 + max(0, (body_pt - 20) * 2)
        self._toast_picker = ToastPositionPicker(self, width_hint=width_hint, height_hint=height_hint)
        self.btn_ach_toast_place.setText("Save position")

    def _on_mini_info_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["notifications_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_mini_info_picker") and isinstance(self._mini_info_picker, MiniInfoPositionPicker):
                self._mini_info_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_mini_info_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["notifications_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_mini_info_picker") and isinstance(self._mini_info_picker, MiniInfoPositionPicker):
                self._mini_info_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_mini_info_place_clicked(self):
        picker = getattr(self, "_mini_info_picker", None)
        if picker and isinstance(picker, MiniInfoPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["notifications_x_portrait"] = int(x)
                self.cfg.OVERLAY["notifications_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["notifications_x_landscape"] = int(x)
                self.cfg.OVERLAY["notifications_y_landscape"] = int(y)
            self.cfg.OVERLAY["notifications_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._mini_info_picker = None
            self.btn_mini_info_place.setText("Place / Save position")
            return
        
        self._mini_info_picker = MiniInfoPositionPicker(self, width_hint=420, height_hint=100)
        self.btn_mini_info_place.setText("Save position")

    def _on_mini_info_test(self):
        # Ruft das Fenster direkt auf, ohne auf ein offenes Spiel zu warten!
        if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
            self._mini_overlay = MiniInfoOverlay(self)
        self._mini_overlay.show_info("TEST: System Notification Overlay", seconds=5, color_hex="#FF3B30")

    def _open_challenge_select_overlay(self):
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self.bridge.challenge_info_show.emit(
                    "Challenge can only be started in-game.",
                    3,
                    "#FF3B30"
                )
            except Exception:
                pass
            return

        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            if not current_rom or not self.watcher._has_any_map(current_rom):
                try:
                    self.bridge.challenge_info_show.emit(
                        "Challenges disabled: No NVRAM map found for this table.",
                        4,
                        "#FF3B30"
                    )
                    self.bridge.challenge_speak.emit("Challenge disabled. Map missing.")
                except Exception:
                    pass
                return
        except Exception:
            pass

        try:
            if getattr(self, "_challenge_select", None):
                try:
                    self._challenge_select.close()
                    self._challenge_select.deleteLater()
                except Exception:
                    pass
            self._challenge_select = ChallengeSelectOverlay(self, selected_idx=int(self._ch_ov_selected_idx))
            self._challenge_select.show()
            self._challenge_select.raise_()
            if self._ch_active_source is None and self._last_ch_event_src:
                self._ch_active_source = self._last_ch_event_src
            try:
                import time as _time
                self._ch_ov_opened_at = _time.monotonic()
            except Exception:
                self._ch_ov_opened_at = 0.0
        except Exception as e:
            try:
                log(self.cfg, f"[UI] open ChallengeSelectOverlay failed: {e}", "WARN")
            except Exception:
                pass

    def _close_challenge_select_overlay(self):
        try:
            if getattr(self, "_challenge_select", None):
                self._challenge_select.hide()
                self._challenge_select.close()
                self._challenge_select.deleteLater()
        except Exception:
            pass
        self._challenge_select = None
        self._ch_active_source = None
        try:
            self._ch_ov_opened_at = 0.0
        except Exception:
            pass

    def _refresh_challenge_select_overlay(self):
        ovw = getattr(self, "_challenge_select", None)
        if ovw:
            try:
                ovw.apply_portrait_from_cfg()
            except Exception:
                pass
                
    def _on_ch_timer_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_timer_portrait"] = bool(is_checked)
        self.cfg.OVERLAY["flip_counter_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_timer_picker") and isinstance(self._ch_timer_picker, TimerPositionPicker):
                self._ch_timer_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        try:
            if hasattr(self, "_flip_counter_picker") and isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ch_timer_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_timer_rotate_ccw"] = bool(is_ccw)
        self.cfg.OVERLAY["flip_counter_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_timer_picker") and isinstance(self._ch_timer_picker, TimerPositionPicker):
                self._ch_timer_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        try:
            if hasattr(self, "_flip_counter_picker") and isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ch_timer_place_clicked(self):
        picker = getattr(self, "_ch_timer_picker", None)
        if picker and isinstance(picker, TimerPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ch_timer_x_portrait"] = int(x)
                self.cfg.OVERLAY["ch_timer_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ch_timer_x_landscape"] = int(x)
                self.cfg.OVERLAY["ch_timer_y_landscape"] = int(y)
            self.cfg.OVERLAY["ch_timer_saved"] = True
            self.cfg.OVERLAY["ch_timer_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._ch_timer_picker = None
            self.btn_ch_timer_place.setText("Place / Save timer position")
            return
        self._ch_timer_picker = TimerPositionPicker(self, width_hint=400, height_hint=120)
        self.btn_ch_timer_place.setText("Save timer position")

    def _on_overlay_place_clicked(self):
        picker = getattr(self, "_overlay_picker", None)
        if picker and isinstance(picker, OverlayPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            self.cfg.OVERLAY["pos_x"] = int(x)
            self.cfg.OVERLAY["pos_y"] = int(y)
            self.cfg.OVERLAY["use_xy"] = True
            self.cfg.OVERLAY["overlay_pos_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._overlay_picker = None
            self.btn_overlay_place.setText("Place / Save overlay position")

            if self.overlay:
                self.overlay._apply_geometry()
                self.overlay._layout_positions()
                self.overlay.request_rotation(force=True)
            return
        self._overlay_picker = OverlayPositionPicker(self)
        self.btn_overlay_place.setText("Save position")

    def _on_mini_info_show(self, rom: str, seconds: int = 10):
        msg = f"NVRAM map not found for {rom}. It will be generated automatically after a full game."

        def _player_visible() -> bool:
            try:
                w = getattr(self, "watcher", None)
                return bool(w and w._vp_player_visible())
            except Exception:
                return False

        def _show_now():
            try:
                if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                    self._mini_overlay = MiniInfoOverlay(self)
                self._mini_overlay.show_info(msg, seconds=max(1, int(seconds)))
            except Exception as e:
                try:
                    log(self.cfg, f"[UI] Mini overlay show failed: {e}")
                except Exception:
                    pass
        if _player_visible():
            _show_now()
            return
        tries = {"n": 0}
        
        def _retry():
            if _player_visible():
                _show_now()
                return
            tries["n"] += 1
            if tries["n"] < 8:
                QTimer.singleShot(250, _retry)
        QTimer.singleShot(250, _retry)

    def _first_screen_geometry(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                return screens[0].geometry()
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _msgbox_topmost(self, kind: str, title: str, text: str):
        box = QMessageBox(self)
        box.setWindowTitle(str(title))
        box.setText(str(text))
        box.setIcon(QMessageBox.Icon.Information if kind == "info" else QMessageBox.Icon.Warning)
        box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        box.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        box.setModal(True)
        box.show()
        box.raise_()
        return box.exec()

    def _on_challenge_timer_start(self, total_seconds: int):
        try:
            try:
                if hasattr(self, "_challenge_timer_delay") and self._challenge_timer_delay:
                    self._challenge_timer_delay.stop()
                    self._challenge_timer_delay.deleteLater()
            except Exception:
                pass
            self._challenge_timer_delay = None

            try:
                if hasattr(self, "_challenge_timer") and self._challenge_timer:
                    self._challenge_timer.close()
                    self._challenge_timer.deleteLater()
            except Exception:
                pass
            self._challenge_timer = None
            warmup_sec = int(getattr(self, "_ch_warmup_sec", 10))
            play_sec = max(1, int(total_seconds or 0) - warmup_sec)

            self._challenge_timer_delay = QTimer(self)
            self._challenge_timer_delay.setSingleShot(True)

            def _spawn():
                try:
                    if hasattr(self, "_challenge_timer") and self._challenge_timer:
                        self._challenge_timer.close()
                        self._challenge_timer.deleteLater()
                except Exception:
                    pass
                self._challenge_timer = None
                try:
                    log(self.cfg, f"[CHALLENGE] countdown spawn – seconds={play_sec}")
                except Exception:
                    pass
                try:
                    self._challenge_timer = ChallengeCountdownOverlay(self, play_sec)
                except Exception:
                    self._challenge_timer = None
            self._challenge_timer_delay.timeout.connect(lambda: QTimer.singleShot(0, _spawn))
            self._challenge_timer_delay.start(warmup_sec * 1000)
        except Exception:
            pass

    def _repair_data_folders(self):
        try:
            ensure_dir(self.cfg.BASE)
            for sub in [
                "NVRAM_Maps", "NVRAM_Maps/maps", "session_stats",
                "rom_specific_achievements", "custom_achievements",
            ]:
                ensure_dir(os.path.join(self.cfg.BASE, sub))
            try:
                self.watcher.bootstrap()
            except Exception as e:
                log(self.cfg, f"[REPAIR] bootstrap failed: {e}", "WARN")
            self._msgbox_topmost(
                "info", "Repair",
                "Base folders repaired.\n\nIf maps are still missing, please click 'Cache maps now (prefetch)'\n"
                "or simply start a ROM (maps will then be loaded on demand)."
            )
            log(self.cfg, "[REPAIR] base folders ensured and index/romnames fetched (if missing)")
        except Exception as e:
            log(self.cfg, f"[REPAIR] failed: {e}", "ERROR")
            self._msgbox_topmost("warn", "Repair", f"Repair failed:\n{e}")

    def _mods_for_vk(self, vk: int) -> int:
        return 0
            
    def _on_ch_timer_test(self):
        try:
            win = ChallengeCountdownOverlay(self, total_seconds=10)
            try:
                win._kill_vpx = lambda: (win.close())
            except Exception:
                pass
            QTimer.singleShot(12000, lambda: (win.close() if hasattr(win, "close") else None))
        except Exception:
            pass
            
    def _on_ch_ov_test(self):
        try:
            if getattr(self, "_challenge_select", None):
                try:
                    self._challenge_select.close()
                    self._challenge_select.deleteLater()
                except Exception:
                    pass
            self._challenge_select = ChallengeSelectOverlay(self, selected_idx=int(self._ch_ov_selected_idx))
            self._challenge_select.show()
            self._challenge_select.raise_()
            QTimer.singleShot(5000, self._close_challenge_select_overlay)
        except Exception:
            pass

    def _start_selected_challenge(self):
        idx = int(getattr(self, "_ch_ov_selected_idx", 0) or 0) % 2
        try:
            if idx == 0:
                self.watcher.start_timed_challenge()
            else:
                self.watcher.start_flip_challenge(500)
        except Exception:
            pass

    def _challenge_binding_label_text(self, kind: str) -> str:
        if kind == "hotkey":
            src = str(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_hotkey_joy_button", 3))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_hotkey_vk", 0x7A))
            mods = int(self.cfg.OVERLAY.get("challenge_hotkey_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        if kind == "left":
            src = str(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_left_joy_button", 4))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_left_vk", 0x25))
            mods = int(self.cfg.OVERLAY.get("challenge_left_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        if kind == "right":
            src = str(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_right_joy_button", 5))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_right_vk", 0x27))
            mods = int(self.cfg.OVERLAY.get("challenge_right_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        return "Current: (none)"
        
    def _on_ch_volume_changed(self, val: int):
        self.lbl_ch_volume.setText(f"{val}%")
        self.cfg.OVERLAY["challenges_voice_volume"] = int(val)
        self.cfg.save()

    def _on_ch_mute_toggled(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["challenges_voice_mute"] = bool(is_checked)
        self.cfg.save()
    
    def _ch_results_path(self, rom: str) -> str:
        return os.path.join(self.cfg.BASE, "challenges", "history", f"{sanitize_filename(rom)}.json")

    def _update_challenges_results_view(self):
        try:
            hist_dir = os.path.join(self.cfg.BASE, "challenges", "history")
            if not os.path.isdir(hist_dir):
                self.ch_results_view.setHtml("<div style='color:#888; text-align:center; margin-top:20px;'>(no results yet)</div>")
                return

            timed_items = []
            flip_items = []
            for fn in os.listdir(hist_dir):
                if not fn.lower().endswith(".json"):
                    continue
                fpath = os.path.join(hist_dir, fn)
                data = secure_load_json(fpath, {"results": []}) or {"results": []}
                for it in (data.get("results") or []):
                    try:
                        kind = str(it.get("kind", "") or "").lower()
                        if kind not in ("timed", "flip"):
                            continue
                        rom = str(it.get("rom", "") or "")
                        score = int(it.get("score", 0) or 0)
                        dur_s = int(it.get("duration_sec", 0) or 0)
                        ts = str(it.get("ts", "") or "")
                        
                        diff_str = it.get("difficulty", "")
                        if not diff_str:
                            tf = int(it.get("target_flips", 0) or 0)
                            if tf > 0:
                                if tf <= 100: diff_str = "Pro"
                                elif tf <= 200: diff_str = "Difficult"
                                elif tf <= 300: diff_str = "Medium"
                                elif tf <= 400: diff_str = "Easy"
                                else: diff_str = f"{tf} Flips"
                            else:
                                diff_str = "-"

                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if dt.tzinfo is not None:
                                dt = dt.astimezone().replace(tzinfo=None)
                        except Exception:
                            dt = datetime.min

                        item = {
                            "rom": rom, 
                            "score": score, 
                            "duration_sec": dur_s, 
                            "_dt": dt, 
                            "difficulty": diff_str
                        }
                        
                        if kind == "timed":
                            timed_items.append(item)
                        else:
                            flip_items.append(item)
                    except Exception:
                        continue

            timed_items.sort(key=lambda x: x.get("_dt") or datetime.min, reverse=True)
            flip_items.sort(key=lambda x: x.get("_dt") or datetime.min, reverse=True)

            LIMIT = 30
            timed_items = timed_items[:LIMIT]
            flip_items = flip_items[:LIMIT]

            def fmt_score(n: int) -> str:
                try:
                    return f"{int(n):,d}".replace(",", ".")
                except Exception:
                    return str(n)

            css = """
            <style>
              table { border-collapse: collapse; margin-top: 5px; }
              th, td { padding: 8px 10px; border-bottom: 1px solid #444; white-space: nowrap; }
              th { background: #1A1A1A; font-weight: bold; color: #00E5FF; }
              td.left { color: #FFFFFF; font-weight: bold; } 
              td.val { color: #FF7F00; font-weight: bold; } 
              td.diff { color: #AAAAAA; font-style: italic; } 
              h4 { margin: 5px 0 10px 0; color: #FFFFFF; font-size: 1.4em; text-align: left; text-transform: uppercase; letter-spacing: 2px; }
            </style>
            """

            def tbl(title: str, items: list[dict], is_flip: bool) -> str:
                if is_flip:
                    head = "<tr><th align='left'>ROM</th><th align='right'>Difficulty</th><th align='right'>Score</th><th align='right'>Duration</th></tr>"
                else:
                    head = "<tr><th align='left'>ROM</th><th align='right'>Score</th><th align='right'>Duration</th></tr>"
                
                if not items:
                    cols = 4 if is_flip else 3
                    body = f"<tr><td colspan='{cols}' align='center' style='color:#888; border:none; padding-top:20px;'>(no results)</td></tr>"
                else:
                    rows = []
                    for it in items:
                        rom = it.get("rom", "")
                        sc = fmt_score(it.get("score", 0))
                        dur = self._fmt_hms(int(it.get("duration_sec", 0)))
                        
                        if is_flip:
                            diff_label = it.get("difficulty", "-")
                            rows.append(f"<tr><td align='left' class='left'>{rom}</td><td align='right' class='diff'>{diff_label}</td><td align='right' class='val'>{sc}</td><td align='right' class='val'>{dur}</td></tr>")
                        else:
                            rows.append(f"<tr><td align='left' class='left'>{rom}</td><td align='right' class='val'>{sc}</td><td align='right' class='val'>{dur}</td></tr>")
                    body = "".join(rows)
                
                return f"<h4>{title}</h4><table width='100%'>{head}{body}</table>"

            html_left = tbl("Timed", timed_items, False)
            html_right = tbl("Flip", flip_items, True)
            
            html = (
                css +
                "<table width='100%' style='border:none; margin-top:5px;'><tr>"
                f"<td valign='top' style='padding-right:20px; width:50%; border:none;'>{html_left}</td>"
                f"<td valign='top' style='padding-left:20px; width:50%; border:none; border-left:1px solid #555;'>{html_right}</td>"
                "</tr></table>"
            )
            self.ch_results_view.setHtml(html)
        except Exception:
            self.ch_results_view.setHtml("<div style='color:#FF3B30; text-align:center;'>(error while loading results)</div>")
            
    def _on_bind_ch_clicked(self, kind: str):
        src = self.cfg.OVERLAY.get(f"challenge_{kind}_input_source", "keyboard")
        if src == "joystick":
            dlg = QDialog(self)
            dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
            dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            dlg.setWindowTitle("Joystick binding")
            dlg.resize(420, 160)
            lay = QVBoxLayout(dlg)
            lbl = QLabel("Press any joystick button to bind…\n(Timeout in 10 seconds; ESC to cancel)")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl)

            cancelled = {"flag": False}

            def custom_keyPressEvent(event):
                if event.key() == Qt.Key.Key_Escape:
                    cancelled["flag"] = True
                    dlg.reject()
                else:
                    QDialog.keyPressEvent(dlg, event)
            dlg.keyPressEvent = custom_keyPressEvent

            def _read_buttons_mask() -> int:
                jix = JOYINFOEX()
                jix.dwSize = ctypes.sizeof(JOYINFOEX)
                jix.dwFlags = JOY_RETURNALL
                mask_all = 0
                for jid in range(16):
                    try:
                        if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                            mask_all |= int(jix.dwButtons)
                    except Exception:
                        continue
                return mask_all

            baseline = _read_buttons_mask()
            start_ts = time.time()
            timer = QTimer(dlg)

            def _poll():
                nonlocal baseline
                if cancelled["flag"]:
                    timer.stop()
                    return
                try:
                    mask = _read_buttons_mask()
                    newly = mask & ~baseline
                    baseline = mask
                    if newly:
                        lsb = newly & -newly
                        idx = lsb.bit_length() - 1
                        button_num = idx + 1
                        self.cfg.OVERLAY[f"challenge_{kind}_joy_button"] = int(button_num)
                        self.cfg.save()
                        if kind == "hotkey":
                            self.lbl_ch_hotkey_binding.setText(self._challenge_binding_label_text("hotkey"))
                        elif kind == "left":
                            self.lbl_ch_left_binding.setText(self._challenge_binding_label_text("left"))
                        else:
                            self.lbl_ch_right_binding.setText(self._challenge_binding_label_text("right"))
                        timer.stop()
                        dlg.accept()
                        self._refresh_input_bindings()
                        return
                    if time.time() - start_ts > 10.0:
                        timer.stop()
                        dlg.reject()
                except Exception:
                    pass

            timer.setInterval(35)
            timer.timeout.connect(_poll)
            timer.start()
            dlg.exec()
            return

        # Keyboard-Binding
        class _TmpKeyCaptureFilter(QAbstractNativeEventFilter):
            def __init__(self, cb, self_ref):
                super().__init__()
                self.cb = cb
                self.self_ref = self_ref
                self._done = False

            def nativeEventFilter(self, eventType, message):
                if self._done:
                    return False, 0
                try:
                    if eventType == b"windows_generic_MSG":
                        msg = ctypes.wintypes.MSG.from_address(int(message))
                        if msg.message in (WM_KEYDOWN, WM_SYSKEYDOWN):
                            vk = int(msg.wParam)
                            if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                                return False, 0
                            mods = self.self_ref._get_hotkey_mods_now()
                            self._done = True
                            self.cb(vk, mods)
                except Exception:
                    pass
                return False, 0

        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard binding")
        dlg.resize(360, 140)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        lay = QVBoxLayout(dlg)
        lbl = QLabel("Press key (with optional Ctrl/Shift/Alt/Win)…\n(ESC to cancel)")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

        cancelled = {"flag": False}

        def local_keyPressEvent(evt):
            if evt.key() == Qt.Key.Key_Escape:
                cancelled["flag"] = True
                try:
                    QCoreApplication.instance().removeNativeEventFilter(fil)
                except Exception:
                    pass
                dlg.reject()
        dlg.keyPressEvent = local_keyPressEvent

        def on_vk(vk: int, mods: int):
            if cancelled["flag"]:
                return
            try:
                QCoreApplication.instance().removeNativeEventFilter(fil)
            except Exception:
                pass

            self.cfg.OVERLAY[f"challenge_{kind}_vk"] = int(vk)
            self.cfg.OVERLAY[f"challenge_{kind}_mods"] = int(mods)
            self.cfg.save()

            if kind == "hotkey":
                self.lbl_ch_hotkey_binding.setText(self._challenge_binding_label_text("hotkey"))
            elif kind == "left":
                self.lbl_ch_left_binding.setText(self._challenge_binding_label_text("left"))
            else:
                self.lbl_ch_right_binding.setText(self._challenge_binding_label_text("right"))

            dlg.accept()
            self._refresh_input_bindings()

        fil = _TmpKeyCaptureFilter(on_vk, self)
        QCoreApplication.instance().installNativeEventFilter(fil)
        dlg.exec()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

    def _open_flip_difficulty_overlay(self):
        try:
            if getattr(self, "_challenge_select", None):
                try:
                    self._challenge_select.hide()
                except Exception:
                    pass
            if getattr(self, "_flip_diff_select", None):
                try:
                    self._flip_diff_select.close()
                    self._flip_diff_select.deleteLater()
                except Exception:
                    pass
            self._flip_diff_select = FlipDifficultyOverlay(self, selected_idx=int(self._ch_flip_diff_idx),
                                                           options=list(self._flip_diff_options))
            self._flip_diff_select.show()
            self._flip_diff_select.raise_()
            self._ch_pick_flip_diff = True
        except Exception:
            self._flip_diff_select = None
            self._ch_pick_flip_diff = False

    def _close_flip_difficulty_overlay(self):
        try:
            if getattr(self, "_flip_diff_select", None):
                self._flip_diff_select.hide()
                self._flip_diff_select.close()
                self._flip_diff_select.deleteLater()
        except Exception:
            pass
        self._flip_diff_select = None
        self._ch_pick_flip_diff = False

    def _on_challenge_hotkey(self):
        try:
            import time as _time
            debounce_ms_cfg = int(self.cfg.OVERLAY.get("ch_hotkey_debounce_ms", 120))
            debounce_ms = max(120, debounce_ms_cfg)
            now = _time.monotonic()
            last = float(getattr(self, "_last_ch_hotkey_ts", 0.0) or 0.0)
            if debounce_ms > 0 and (now - last) < (debounce_ms / 1000.0):
                return
            self._last_ch_hotkey_ts = now
        except Exception:
            pass

        if not self._in_game_now():
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            try:
                self.bridge.challenge_info_show.emit(
                    "Challenge can only be started in-game.",
                    3,
                    "#FF3B30"
                )
            except Exception:
                pass
            return

        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            if not current_rom or not self.watcher._has_any_map(current_rom):
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
                try:
                    self.bridge.challenge_info_show.emit(
                        "Challenges disabled: No NVRAM map found.",
                        3,
                        "#FF3B30"
                    )
                except Exception:
                    pass
                return
        except Exception:
            pass

        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                name, flips = self._flip_diff_select.selected_option()
            except Exception:
                name, flips = ("Medium", 400)
            self._close_flip_difficulty_overlay()
            self._close_challenge_select_overlay()
            try:
                self.watcher.start_flip_challenge(int(flips))
            except Exception:
                pass
            return

        ovw = getattr(self, "_challenge_select", None)
        if ovw and ovw.isVisible():
            sel = int(getattr(self, "_ch_ov_selected_idx", 0) or 0) % 2
            if sel == 0:
                self._close_challenge_select_overlay()
                try:
                    self.watcher.start_timed_challenge()
                except Exception:
                    pass
                return
            else:
                self._open_flip_difficulty_overlay()
                return
        self._open_challenge_select_overlay()

    def _on_challenge_left(self):
        try:
            import time as _time
            now = _time.monotonic()
            if (now - float(getattr(self, "_last_ch_nav_ts", 0.0) or 0.0)) < 0.12:
                return
            self._last_ch_nav_ts = now
        except Exception:
            pass
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            return
        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                n = len(self._flip_diff_options)
                self._ch_flip_diff_idx = (int(self._ch_flip_diff_idx) - 1) % n
                self._flip_diff_select.set_selected(self._ch_flip_diff_idx)
            except Exception:
                pass
            return
        ovw = getattr(self, "_challenge_select", None)
        if not (ovw and ovw.isVisible()):
            return
        src = getattr(self, "_last_ch_event_src", None)
        if self._ch_active_source and src and self._ch_active_source != src:
            self._ch_active_source = src
        self._ch_ov_selected_idx = (int(self._ch_ov_selected_idx) - 1) % 2
        try:
            ovw.set_selected(self._ch_ov_selected_idx)
        except Exception:
            pass

    def _on_challenge_right(self):
        try:
            import time as _time
            now = _time.monotonic()
            if (now - float(getattr(self, "_last_ch_nav_ts", 0.0) or 0.0)) < 0.12:
                return
            self._last_ch_nav_ts = now
        except Exception:
            pass
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            return
        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                n = len(self._flip_diff_options)
                self._ch_flip_diff_idx = (int(self._ch_flip_diff_idx) + 1) % n
                self._flip_diff_select.set_selected(self._ch_flip_diff_idx)
            except Exception:
                pass
            return
        ovw = getattr(self, "_challenge_select", None)
        if not (ovw and ovw.isVisible()):
            return
        src = getattr(self, "_last_ch_event_src", None)
        if self._ch_active_source and src and self._ch_active_source != src:
            self._ch_active_source = src
        self._ch_ov_selected_idx = (int(self._ch_ov_selected_idx) + 1) % 2
        try:
            ovw.set_selected(self._ch_ov_selected_idx)
        except Exception:
            pass

    def _install_challenge_key_handling(self):
        try:
            if getattr(self, "_challenge_keyhook", None):
                try:
                    self._challenge_keyhook.uninstall()
                except Exception:
                    pass
        except Exception:
            pass
        self._challenge_keyhook = None
        if getattr(self.cfg, "LOG_CTRL", False):
            log(self.cfg, "[HOTKEY] challenge low-level hook disabled (using WM_HOTKEY)")
                    
    def _fmt_hms(self, seconds: int) -> str:
        try:
            seconds = int(seconds or 0)
        except Exception:
            seconds = 0
        d = seconds // 86400
        h = (seconds % 86400) // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if d > 0:
            return f"{d}d {h:02d}:{m:02d}:{s:02d}"
        return f"{h:02d}:{m:02d}:{s:02d}"
               
    def quit_all(self):
        self.cfg.save()
        try:
            if self.tray:
                self.tray.hide()
        except Exception:
            pass
        try:
            if getattr(self, "watcher", None):
                self.watcher.stop()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass
        try:
            QApplication.instance().quit()
        except Exception:
            pass
           
    def _prefetch_maps_now(self):
        try:
            self.watcher.start_prefetch_background()
            maps_dir = os.path.join(self.cfg.BASE, "NVRAM_Maps", "maps")
            QMessageBox.information(
                self, "Prefetch",
                f"Prefetch started. Missing maps are being cached in the background at:\n"
                f"{maps_dir}\n"
                "See watcher.log for progress."
            )
            log(self.cfg, "[PREFETCH] started by user")
        except Exception as e:
            log(self.cfg, f"[PREFETCH] failed: {e}", "ERROR")
            QMessageBox.warning(self, "Prefetch", f"Prefetch failed:\n{e}")
    def _style(self, widget, css: str):
        try:
            if widget:
                widget.setStyleSheet(css)
        except Exception:
            pass

    def _apply_theme(self):
        app = QApplication.instance()
        # Fusion ist die beste Basis für starke Custom-Themes
        app.setStyle("Fusion") 
        
        pinball_arcade_style = """
        /* --- Basis: Tiefschwarz (Cabinet) --- */
        QMainWindow, QDialog, QWidget {
            background-color: #121212;
            color: #E0E0E0;
            font-family: 'Segoe UI', sans-serif;
            font-size: 10pt;
        }

        /* --- Die Haupt-Tabs --- */
        QTabWidget::pane {
            border: 1px solid #333333;
            background-color: #181818;
            border-radius: 4px;
        }
        QTabBar::tab {
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
        }
        QTabBar::tab:hover:!selected {
            background-color: #2A2A2A;
            color: #FFFFFF;
        }
        QTabBar::tab:selected {
            background-color: #181818;
            color: #FF7F00; /* Williams DMD Orange! */
            border-top: 3px solid #FF7F00;
        }

        /* --- Buttons (Arcade Style mit Metallic-Gradient) --- */
        QPushButton {
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #383838, stop:1 #252525);
            color: #FFFFFF;
            border: 1px solid #555555;
            border-radius: 5px;
            padding: 7px 16px;
            font-weight: bold;
        }
        QPushButton:hover {
            border: 1px solid #FF7F00; /* DMD Orange Glow */
            color: #FF7F00;
            background-color: #2C2C2C;
        }
        QPushButton:pressed {
            background-color: #FF7F00;
            color: #000000;
            border: 1px solid #FF7F00;
        }

        /* --- Panels (Groupboxen für die Struktur) --- */
        QGroupBox {
            border: 1px solid #444444;
            border-radius: 6px;
            margin-top: 20px;
            background-color: #1A1A1A;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            left: 15px;
            color: #00E5FF; /* LED Eisblau! */
            font-weight: bold;
            font-size: 11pt;
        }

        /* --- Textfelder & Listen (z.B. für Stats) --- */
        QTextBrowser, QTextEdit {
            background-color: #0A0A0A; /* Noch dunkler für Kontrast */
            border: 1px solid #333333;
            border-radius: 4px;
            color: #FFB000; /* Leichtes Orange/Amber für Stats */
        }
        
        /* --- Eingabefelder --- */
        QLineEdit, QComboBox, QSpinBox {
            background-color: #222222;
            color: #FFFFFF;
            border: 1px solid #555555;
            border-radius: 3px;
            padding: 5px;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
            border: 1px solid #00E5FF; /* Blauer Fokus-Glow */
        }

        /* --- Slider (Für Volume & Skalierung) --- */
        QSlider::groove:horizontal {
            border: 1px solid #444;
            height: 8px;
            background: #222;
            border-radius: 4px;
        }
        QSlider::sub-page:horizontal {
            background: #FF7F00; /* DMD Orange Füllung */
            border-radius: 4px;
        }
        QSlider::handle:horizontal {
            background: #FFFFFF;
            border: 2px solid #777;
            width: 14px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 7px;
        }

        /* --- Checkboxen --- */
        QCheckBox::indicator {
            width: 18px; 
            height: 18px;
            border: 1px solid #666;
            border-radius: 4px;
            background-color: #222;
        }
        QCheckBox::indicator:hover {
            border: 1px solid #FF7F00;
        }
        QCheckBox::indicator:checked {
            background-color: #00E5FF; /* Eisblauer Haken */
            border: 1px solid #00E5FF;
        }
        """
        app.setStyleSheet(pinball_arcade_style)

        self._style(getattr(self, "btn_minimize", None), "background:#005c99; color:white; border:none;")
        self._style(getattr(self, "btn_quit", None), "background:#8a2525; color:white; border:none;")
        self._style(getattr(self, "btn_restart", None), "background:#008040; color:white; border:none;")

    # ==========================================
    # TAB 1: DASHBOARD
    # ==========================================
    def _build_tab_dashboard(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp_status = QGroupBox("System Status")
        lay_status = QVBoxLayout(grp_status)
        self.status_label = QLabel("🟢 Watcher: RUNNING...")
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00E5FF; padding: 10px;")
        lay_status.addWidget(self.status_label)
        layout.addWidget(grp_status)

        grp_actions = QGroupBox("Quick Actions")
        lay_actions = QHBoxLayout(grp_actions)
        self.btn_restart = QPushButton("Restart Engine")
        self.btn_restart.setStyleSheet("background:#008040; border:none;")
        self.btn_restart.clicked.connect(self._restart_watcher)
        self.btn_minimize = QPushButton("Minimize to Tray")
        self.btn_minimize.setStyleSheet("background:#005c99; border:none;")
        self.btn_minimize.clicked.connect(self.hide)
        self.btn_quit = QPushButton("Quit GUI")
        self.btn_quit.setStyleSheet("background:#8a2525; border:none;")
        self.btn_quit.clicked.connect(self.quit_all)
        
        lay_actions.addWidget(self.btn_restart)
        lay_actions.addStretch(1)
        lay_actions.addWidget(self.btn_minimize)
        lay_actions.addWidget(self.btn_quit)
        layout.addWidget(grp_actions)
        
        lbl_info = QLabel("\n(Play a game of VPX to see stats and highlights...)")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setStyleSheet("color: #777;")
        layout.addWidget(lbl_info)
        layout.addStretch(1)

        self.main_tabs.addTab(tab, "🏠 Dashboard")

    # ==========================================
    # TAB 2: APPEARANCE (Grid Layout)
    # ==========================================
    def _build_tab_appearance(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_style = QGroupBox("Global Styling")
        lay_style = QGridLayout(grp_style)
        
        self.cmb_font_family = QFontComboBox()
        self.cmb_font_family.setCurrentFont(QFont(self.cfg.OVERLAY.get("font_family", "Segoe UI")))
        self.cmb_font_family.currentFontChanged.connect(self._on_font_family_changed)
        
        self.spn_font_size = QSpinBox()
        self.spn_font_size.setRange(8, 64)
        self.spn_font_size.setValue(int(self.cfg.OVERLAY.get("base_body_size", 20)))
        self.spn_font_size.valueChanged.connect(self._on_font_size_changed)

        self.sld_scale = QSlider(Qt.Orientation.Horizontal)
        self.sld_scale.setMinimum(30); self.sld_scale.setMaximum(300)
        self.sld_scale.setValue(int(self.cfg.OVERLAY.get("scale_pct", 100)))
        self.sld_scale.valueChanged.connect(self._on_overlay_scale)
        self.lbl_scale = QLabel(f"{self.sld_scale.value()}%")

        lay_style.addWidget(QLabel("Font Family:"), 0, 0)
        lay_style.addWidget(self.cmb_font_family, 0, 1)
        lay_style.addWidget(QLabel("Base Size:"), 0, 2)
        lay_style.addWidget(self.spn_font_size, 0, 3)
        
        lay_style.addWidget(QLabel("Overlay Scale:"), 1, 0)
        lay_style.addWidget(self.sld_scale, 1, 1)
        lay_style.addWidget(self.lbl_scale, 1, 2)

        layout.addWidget(grp_style)

        grp_pos = QGroupBox("Widget Placement & Orientation")
        lay_pos = QGridLayout(grp_pos)

        def create_overlay_box(title, chk_port, chk_ccw, btn_place, btn_test=None, btn_hide=None, extra=None):
            box = QVBoxLayout()
            box.addWidget(QLabel(f"<b>{title}</b>"))
            box.addWidget(chk_port); box.addWidget(chk_ccw)
            btns = QHBoxLayout(); btns.addWidget(btn_place)
            if btn_test: btns.addWidget(btn_test)
            if btn_hide: btns.addWidget(btn_hide)
            box.addLayout(btns)
            if extra: box.addWidget(extra)
            box.addStretch(1)
            return box

        # 1) Main Overlay
        self.chk_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_portrait.setChecked(bool(self.cfg.OVERLAY.get("portrait_mode", True))); self.chk_portrait.stateChanged.connect(self._on_portrait_toggle)
        self.chk_portrait_ccw = QCheckBox("Rotate CCW"); self.chk_portrait_ccw.setChecked(bool(self.cfg.OVERLAY.get("portrait_rotate_ccw", True))); self.chk_portrait_ccw.stateChanged.connect(self._on_portrait_ccw_toggle)
        self.btn_overlay_place = QPushButton("Place"); self.btn_overlay_place.clicked.connect(self._on_overlay_place_clicked)
        self.btn_toggle_now = QPushButton("Test"); self.btn_toggle_now.clicked.connect(self._on_overlay_test_clicked)
        self.btn_hide = QPushButton("Hide"); self.btn_hide.clicked.connect(self._hide_overlay)
        self.chk_overlay_auto_close = QCheckBox("Auto-Close 1 min"); self.chk_overlay_auto_close.setChecked(bool(self.cfg.OVERLAY.get("overlay_auto_close", False))); self.chk_overlay_auto_close.stateChanged.connect(self._on_overlay_auto_close_toggle)
        box_main = create_overlay_box("Main Stats Overlay", self.chk_portrait, self.chk_portrait_ccw, self.btn_overlay_place, self.btn_toggle_now, self.btn_hide, self.chk_overlay_auto_close)

        # 2) Toasts
        self.chk_ach_toast_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ach_toast_portrait.setChecked(bool(self.cfg.OVERLAY.get("ach_toast_portrait", True))); self.chk_ach_toast_portrait.stateChanged.connect(self._on_ach_toast_portrait_toggle)
        self.chk_ach_toast_ccw = QCheckBox("Rotate CCW"); self.chk_ach_toast_ccw.setChecked(bool(self.cfg.OVERLAY.get("ach_toast_rotate_ccw", True))); self.chk_ach_toast_ccw.stateChanged.connect(self._on_ach_toast_ccw_toggle)
        self.btn_ach_toast_place = QPushButton("Place"); self.btn_ach_toast_place.clicked.connect(self._on_ach_toast_place_clicked)
        self.btn_test_toast = QPushButton("Test"); self.btn_test_toast.clicked.connect(lambda: self._ach_toast_mgr.enqueue("TEST – Achievement", "test_rom", 5))
        box_toast = create_overlay_box("Achievement Toasts", self.chk_ach_toast_portrait, self.chk_ach_toast_ccw, self.btn_ach_toast_place, self.btn_test_toast)

        # 3) Challenge Menu
        self.chk_ch_ov_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ch_ov_portrait.setChecked(bool(self.cfg.OVERLAY.get("ch_ov_portrait", True))); self.chk_ch_ov_portrait.stateChanged.connect(self._on_ch_ov_portrait_toggle)
        self.chk_ch_ov_ccw = QCheckBox("Rotate CCW"); self.chk_ch_ov_ccw.setChecked(bool(self.cfg.OVERLAY.get("ch_ov_rotate_ccw", True))); self.chk_ch_ov_ccw.stateChanged.connect(self._on_ch_ov_ccw_toggle)
        self.btn_ch_ov_place = QPushButton("Place"); self.btn_ch_ov_place.clicked.connect(self._on_ch_ov_place_clicked)
        self.btn_ch_ov_test = QPushButton("Test"); self.btn_ch_ov_test.clicked.connect(self._on_ch_ov_test)
        box_ch_sel = create_overlay_box("Challenge Menu", self.chk_ch_ov_portrait, self.chk_ch_ov_ccw, self.btn_ch_ov_place, self.btn_ch_ov_test)

        # 4) Timers & Counters
        self.chk_ch_timer_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ch_timer_portrait.setChecked(bool(self.cfg.OVERLAY.get("ch_timer_portrait", True))); self.chk_ch_timer_portrait.stateChanged.connect(self._on_ch_timer_portrait_toggle)
        self.chk_ch_timer_ccw = QCheckBox("Rotate CCW"); self.chk_ch_timer_ccw.setChecked(bool(self.cfg.OVERLAY.get("ch_timer_rotate_ccw", True))); self.chk_ch_timer_ccw.stateChanged.connect(self._on_ch_timer_ccw_toggle)
        box_tc = QVBoxLayout(); box_tc.addWidget(QLabel("<b>Timers & Counters</b>")); box_tc.addWidget(self.chk_ch_timer_portrait); box_tc.addWidget(self.chk_ch_timer_ccw)
        btn_r1 = QHBoxLayout(); self.btn_ch_timer_place = QPushButton("Place Timer"); self.btn_ch_timer_place.clicked.connect(self._on_ch_timer_place_clicked); self.btn_ch_timer_test = QPushButton("Test Timer"); self.btn_ch_timer_test.clicked.connect(self._on_ch_timer_test); btn_r1.addWidget(self.btn_ch_timer_place); btn_r1.addWidget(self.btn_ch_timer_test)
        btn_r2 = QHBoxLayout(); self.btn_flip_counter_place = QPushButton("Place Counter"); self.btn_flip_counter_place.clicked.connect(self._on_flip_counter_place_clicked); self.btn_flip_counter_test = QPushButton("Test Counter"); self.btn_flip_counter_test.clicked.connect(self._on_flip_counter_test); btn_r2.addWidget(self.btn_flip_counter_place); btn_r2.addWidget(self.btn_flip_counter_test)
        box_tc.addLayout(btn_r1); box_tc.addLayout(btn_r2); box_tc.addStretch(1)

        self.chk_flip_counter_portrait = self.chk_ch_timer_portrait
        self.chk_flip_counter_ccw = self.chk_ch_timer_ccw

        # 5) NEU: Mini Info / Notifications Overlay
        self.chk_mini_info_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_mini_info_portrait.setChecked(bool(self.cfg.OVERLAY.get("notifications_portrait", True))); self.chk_mini_info_portrait.stateChanged.connect(self._on_mini_info_portrait_toggle)
        self.chk_mini_info_ccw = QCheckBox("Rotate CCW"); self.chk_mini_info_ccw.setChecked(bool(self.cfg.OVERLAY.get("notifications_rotate_ccw", True))); self.chk_mini_info_ccw.stateChanged.connect(self._on_mini_info_ccw_toggle)
        self.btn_mini_info_place = QPushButton("Place"); self.btn_mini_info_place.clicked.connect(self._on_mini_info_place_clicked)
        self.btn_mini_info_test = QPushButton("Test"); self.btn_mini_info_test.clicked.connect(self._on_mini_info_test)
        box_mini_info = create_overlay_box("System Notifications", self.chk_mini_info_portrait, self.chk_mini_info_ccw, self.btn_mini_info_place, self.btn_mini_info_test)

        lay_pos.addLayout(box_main, 0, 0); lay_pos.addLayout(box_toast, 0, 1)
        lay_pos.addLayout(box_ch_sel, 1, 0); lay_pos.addLayout(box_tc, 1, 1)
        lay_pos.addLayout(box_mini_info, 2, 0) # Fügt die Box in die 3. Zeile ein

        layout.addWidget(grp_pos)
        layout.addStretch(1)
        self.main_tabs.addTab(tab, "🎨 Appearance")

    # ==========================================
    # TAB 3: CONTROLS
    # ==========================================
    def _build_tab_controls(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_inputs = QGroupBox("Input Bindings & Hotkeys")
        lay_inputs = QGridLayout(grp_inputs)
        
        self.cmb_toggle_src = QComboBox(); self.cmb_toggle_src.addItems(["keyboard", "joystick"]); self.cmb_toggle_src.setCurrentText(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")); self.cmb_toggle_src.currentTextChanged.connect(self._on_toggle_source_changed)
        self.btn_bind_toggle = QPushButton("Bind..."); self.btn_bind_toggle.clicked.connect(self._on_bind_toggle_clicked)
        self.lbl_toggle_binding = QLabel(self._toggle_binding_label_text())
        
        self.cmb_ch_hotkey_src = QComboBox(); self.cmb_ch_hotkey_src.addItems(["keyboard", "joystick"]); self.cmb_ch_hotkey_src.setCurrentText(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")); self.cmb_ch_hotkey_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("hotkey", s))
        self.btn_ch_hotkey_bind = QPushButton("Bind..."); self.btn_ch_hotkey_bind.clicked.connect(lambda: self._on_bind_ch_clicked("hotkey"))
        self.lbl_ch_hotkey_binding = QLabel(self._challenge_binding_label_text("hotkey"))

        self.cmb_ch_left_src = QComboBox(); self.cmb_ch_left_src.addItems(["keyboard", "joystick"]); self.cmb_ch_left_src.setCurrentText(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")); self.cmb_ch_left_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("left", s))
        self.btn_ch_left_bind = QPushButton("Bind..."); self.btn_ch_left_bind.clicked.connect(lambda: self._on_bind_ch_clicked("left"))
        self.lbl_ch_left_binding = QLabel(self._challenge_binding_label_text("left"))

        self.cmb_ch_right_src = QComboBox(); self.cmb_ch_right_src.addItems(["keyboard", "joystick"]); self.cmb_ch_right_src.setCurrentText(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")); self.cmb_ch_right_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("right", s))
        self.btn_ch_right_bind = QPushButton("Bind..."); self.btn_ch_right_bind.clicked.connect(lambda: self._on_bind_ch_clicked("right"))
        self.lbl_ch_right_binding = QLabel(self._challenge_binding_label_text("right"))

        lay_inputs.addWidget(QLabel("<b>Show/Hide Stats Overlay:</b>"), 0, 0); lay_inputs.addWidget(self.cmb_toggle_src, 0, 1); lay_inputs.addWidget(self.btn_bind_toggle, 0, 2); lay_inputs.addWidget(self.lbl_toggle_binding, 0, 3)
        lay_inputs.addWidget(QLabel("<hr>"), 1, 0, 1, 4)
        lay_inputs.addWidget(QLabel("<b>Challenge Action / Start:</b>"), 2, 0); lay_inputs.addWidget(self.cmb_ch_hotkey_src, 2, 1); lay_inputs.addWidget(self.btn_ch_hotkey_bind, 2, 2); lay_inputs.addWidget(self.lbl_ch_hotkey_binding, 2, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Nav Left:</b>"), 3, 0); lay_inputs.addWidget(self.cmb_ch_left_src, 3, 1); lay_inputs.addWidget(self.btn_ch_left_bind, 3, 2); lay_inputs.addWidget(self.lbl_ch_left_binding, 3, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Nav Right:</b>"), 4, 0); lay_inputs.addWidget(self.cmb_ch_right_src, 4, 1); lay_inputs.addWidget(self.btn_ch_right_bind, 4, 2); lay_inputs.addWidget(self.lbl_ch_right_binding, 4, 3)
        lay_inputs.setColumnStretch(3, 1); layout.addWidget(grp_inputs)

        grp_voice = QGroupBox("Voice & Audio")
        lay_voice = QVBoxLayout(grp_voice)
        row_v1 = QHBoxLayout(); row_v1.addWidget(QLabel("AI Voice Volume (Challenges):"))
        self.sld_ch_volume = QSlider(Qt.Orientation.Horizontal); self.sld_ch_volume.setRange(0, 100); self.sld_ch_volume.setValue(int(self.cfg.OVERLAY.get("challenges_voice_volume", 80))); self.sld_ch_volume.valueChanged.connect(self._on_ch_volume_changed)
        row_v1.addWidget(self.sld_ch_volume); self.lbl_ch_volume = QLabel(f"{self.sld_ch_volume.value()}%"); row_v1.addWidget(self.lbl_ch_volume)
        self.chk_ch_voice_mute = QCheckBox("Mute all spoken announcements"); self.chk_ch_voice_mute.setChecked(bool(self.cfg.OVERLAY.get("challenges_voice_mute", False))); self.chk_ch_voice_mute.stateChanged.connect(self._on_ch_mute_toggled)
        lay_voice.addLayout(row_v1); lay_voice.addWidget(self.chk_ch_voice_mute); layout.addWidget(grp_voice)

        layout.addStretch(1)
        self.main_tabs.addTab(tab, "🕹️ Controls")

    # ==========================================
    # TAB 4: RECORDS & STATS
    # ==========================================
    def _build_tab_stats(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        self.stats_tabs = QTabWidget()
        
        ach_tab = QWidget()
        ach_layout = QHBoxLayout(ach_tab)
        self.ach_view_global = QTextBrowser()
        self.ach_view_pl = QTextBrowser()
        box_g = QVBoxLayout(); box_g.addWidget(QLabel("<b>🌍 Global NVRAM Unlocks</b>")); box_g.addWidget(self.ach_view_global)
        box_s = QVBoxLayout(); box_s.addWidget(QLabel("<b>👤 Player Session Unlocks</b>")); box_s.addWidget(self.ach_view_pl)
        ach_layout.addLayout(box_g); ach_layout.addLayout(box_s)
        self.stats_tabs.addTab(ach_tab, "🏆 Achievements")

        self.stats_views = {}
        self.stats_views["global"] = QTextBrowser()
        self.stats_tabs.addTab(self.stats_views["global"], "🌍 Global NVRAM Dumps")
        self.stats_views[1] = QTextBrowser()
        self.stats_tabs.addTab(self.stats_views[1], "👤 Player Session Deltas")

        ch_tab = QWidget()
        ch_layout = QVBoxLayout(ch_tab)
        self.ch_results_view = QTextBrowser()
        ch_layout.addWidget(QLabel("<b>Latest Challenge Results</b>"))
        ch_layout.addWidget(self.ch_results_view)
        self.stats_tabs.addTab(ch_tab, "⚔️ Challenge Leaderboards")

        layout.addWidget(self.stats_tabs)
        self.main_tabs.addTab(tab, "📊 Records & Stats")
        
        try: self._update_challenges_results_view()
        except Exception: pass

    # ==========================================
    # TAB 5: CLOUD LEADERBOARD
    # ==========================================
    def _build_tab_cloud(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp_controls = QGroupBox("Global Cloud Leaderboard")
        lay_ctrl = QHBoxLayout(grp_controls)
        
        self.cmb_cloud_category = QComboBox()
        self.cmb_cloud_category.addItems(["Achievement Progress", "Timed Challenge", "Flip Challenge"])        
        self.cmb_cloud_category.currentIndexChanged.connect(self._on_cloud_cat_changed)
        
        self.cmb_cloud_diff = QComboBox()
        self.cmb_cloud_diff.addItems(["All Difficulties", "Pro", "Difficult", "Medium", "Easy"])
        self.cmb_cloud_diff.hide() 
        
        self.txt_cloud_rom = QLineEdit()
        self.txt_cloud_rom.setPlaceholderText("Enter ROM Name (e.g. afm_113b)")
        
        self.btn_cloud_fetch = QPushButton("Fetch Highscores ☁️")
        self.btn_cloud_fetch.setStyleSheet("background:#00E5FF; color:black; font-weight:bold;")
        self.btn_cloud_fetch.clicked.connect(self._fetch_cloud_leaderboard)
        
        lay_ctrl.addWidget(QLabel("Category:"))
        lay_ctrl.addWidget(self.cmb_cloud_category)
        lay_ctrl.addWidget(self.cmb_cloud_diff)
        lay_ctrl.addWidget(QLabel("ROM:"))
        lay_ctrl.addWidget(self.txt_cloud_rom)
        lay_ctrl.addWidget(self.btn_cloud_fetch)
        layout.addWidget(grp_controls)
        
        self.cloud_view = QTextBrowser()
        self.cloud_view.setHtml("<div style='text-align:center; color:#888; margin-top:20px;'>(Enter a ROM and click Fetch)</div>")
        layout.addWidget(self.cloud_view)
        
        self.main_tabs.addTab(tab, "☁️ Cloud")

    def _on_cloud_cat_changed(self, idx: int):
        if idx == 2:
            self.cmb_cloud_diff.show()
        else:
            self.cmb_cloud_diff.hide()

    def _fetch_cloud_leaderboard(self):
        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
        
        cat_index = self.cmb_cloud_category.currentIndex()
        cat_map = {0: "progress", 1: "timed", 2: "flip"}
        category = cat_map.get(cat_index, "progress")
        rom = self.txt_cloud_rom.text().strip().lower()
        selected_diff = self.cmb_cloud_diff.currentText() if category == "flip" else None
        
        if not rom:
            self.cloud_view.setHtml("<div style='color:#FF3B30;'>(Please enter a ROM name first)</div>")
            return
            
        if not self.cfg.CLOUD_URL:
            self.cloud_view.setHtml("<div style='color:#FF3B30;'>(No Firebase URL configured in System Tab!)</div>")
            return

        self.cloud_view.setHtml("<div style='color:#00E5FF;'>Fetching data from cloud...</div>")
        
        def _bg_fetch():
            if category == "progress":
                data = CloudSync.fetch_data(self.cfg, f"progress/{rom}")
                if data:
                    data.sort(key=lambda x: float(x.get("percentage", 0)), reverse=True)
            else:
                data = CloudSync.fetch_data(self.cfg, f"scores/{category}/{rom}")
                if data:
                    if category == "flip" and selected_diff != "All Difficulties":
                        filtered_data = []
                        for row in data:
                            diff_str = str(row.get("difficulty", "")).strip()
                            if not diff_str:
                                tf = int(row.get("target_flips", 0) or 0)
                                if tf <= 100: diff_str = "Pro"
                                elif tf <= 200: diff_str = "Difficult"
                                elif tf <= 300: diff_str = "Medium"
                                elif tf <= 400: diff_str = "Easy"
                                else: diff_str = f"{tf} Flips"
                            
                            if diff_str.lower() == selected_diff.lower():
                                filtered_data.append(row)
                        data = filtered_data
                        
                    data.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
                    
            html = self._generate_cloud_html(data, category, rom, selected_diff)
            QMetaObject.invokeMethod(self.cloud_view, "setHtml", Qt.ConnectionType.QueuedConnection, Q_ARG(str, html))
            
        threading.Thread(target=_bg_fetch, daemon=True).start()

    def _generate_cloud_html(self, data: list, category: str, rom: str, selected_diff: str = None) -> str:
        css = """
        <style>
          table { border-collapse: collapse; width: 100%; margin-top: 10px; }
          th, td { padding: 10px; border-bottom: 1px solid #444; color: #FFF; text-align: center; vertical-align: middle; }
          th { background: #1A1A1A; color: #00E5FF; font-weight: bold; }
          td.rank { font-weight: bold; color: #FF7F00; font-size: 1.2em; width: 50px; }
          td.name { font-weight: bold; text-align: left; }
          td.score { color: #00B050; font-weight: bold; font-size: 1.2em; }
          .title { font-size: 1.5em; color: #FFF; text-transform: uppercase; font-weight: bold; text-align: center; margin-bottom: 10px; }
          .bar-bg { background: #222; border-radius: 10px; width: 100%; height: 22px; position: relative; border: 1px solid #555; }
          .bar-text { position: absolute; top: 0; left: 0; width: 100%; height: 100%; text-align: center; color: #FFF; font-size: 12px; font-weight: bold; line-height: 22px; text-shadow: 1px 1px 2px #000; }
        </style>
        """
        if not data:
            return f"<div style='text-align:center; color:#888; margin-top:20px;'>No cloud records found for {rom.upper()}</div>"
            
        if category == "progress":
            title_cat = "Achievement Progress"
        elif category == "flip" and selected_diff and selected_diff != "All Difficulties":
            title_cat = f"Flip Challenge ({selected_diff})"
        else:
            title_cat = f"{category.upper()} Challenge"
            
        html = [css, f"<div class='title'>Leaderboard: {rom.upper()} ({title_cat})</div>"]
        
        show_diff_col = (category == "flip" and (not selected_diff or selected_diff == "All Difficulties"))
        
        if category == "progress":
            html.append("<table><tr><th>Rank</th><th style='text-align:left;'>Player</th><th style='width: 50%;'>Progress</th><th>Date</th></tr>")
        elif show_diff_col:
            html.append("<table><tr><th>Rank</th><th style='text-align:left;'>Player</th><th>Difficulty</th><th>Score</th><th>Date</th></tr>")
        else:
            html.append("<table><tr><th>Rank</th><th style='text-align:left;'>Player</th><th>Score</th><th>Date</th></tr>")
        
        for i, row in enumerate(data):
            rank = i + 1
            name = row.get("name", "Unknown")
            ts = row.get("ts", "")[:10]
            medal = "🏆" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
            
            if category == "progress":
                unlocked = int(row.get('unlocked', 0))
                total = int(row.get('total', 1))
                pct = float(row.get('percentage', 0))
                
                bar = f"""
                <div class='bar-bg'>
                    <div style='background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7F00, stop:1 #FFD700); width: {pct}%; height: 100%; border-radius: 9px;'></div>
                    <div class='bar-text'>{unlocked} / {total} ({pct}%)</div>
                </div>
                """
                html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}</td><td>{bar}</td><td>{ts}</td></tr>")
            elif category == "flip":
                score = f"{int(row.get('score', 0)):,d}".replace(",", ".")
                if show_diff_col:
                    diff_str = row.get("difficulty", "")
                    if not diff_str:
                        tf = int(row.get("target_flips", 0))
                        if tf > 0:
                            if tf <= 100: diff_str = "Pro"
                            elif tf <= 200: diff_str = "Difficult"
                            elif tf <= 300: diff_str = "Medium"
                            elif tf <= 400: diff_str = "Easy"
                            else: diff_str = f"{tf} Flips"
                        else:
                            diff_str = "-"
                    html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}</td><td style='color:#AAAAAA; font-style:italic;'>{diff_str}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
                else:
                    html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
            else:
                score = f"{int(row.get('score', 0)):,d}".replace(",", ".")
                html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
            
        html.append("</table>")
        return "".join(html)
        
    def _build_tab_progress(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp = QGroupBox("Local Achievement Progress")
        lay = QVBoxLayout(grp)
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Select ROM:"))
        self.cmb_progress_rom = QComboBox()
        self.cmb_progress_rom.currentIndexChanged.connect(self._on_progress_rom_changed)
        row.addWidget(self.cmb_progress_rom)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setStyleSheet("background:#00E5FF; color:black; font-weight:bold;")
        btn_refresh.clicked.connect(self._refresh_progress_roms)
        row.addWidget(btn_refresh)
        lay.addLayout(row)
        
        self.progress_view = QTextBrowser()
        lay.addWidget(self.progress_view)
        
        layout.addWidget(grp)
        self.main_tabs.addTab(tab, "📈 Progress")
        
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, self._refresh_progress_roms)

    def _refresh_progress_roms(self):
        self.cmb_progress_rom.blockSignals(True)
        self.cmb_progress_rom.clear()
        
        roms = set()
        
        state = self.watcher._ach_state_load()
        roms.update(state.get("global", {}).keys())
        roms.update(state.get("session", {}).keys())
        
        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        if os.path.isdir(stats_dir):
            for fn in os.listdir(stats_dir):
                if fn.lower().endswith(".txt"):
                    parts = fn.split("__")
                    if len(parts) >= 2:
                        roms.add(parts[0])
                        
        valid_roms = sorted([r for r in roms if self.watcher._has_any_map(r)])
        
        self.cmb_progress_rom.addItem("Global")
        
        if valid_roms:
            self.cmb_progress_rom.addItems(valid_roms)
            
        self.cmb_progress_rom.blockSignals(False)
        self._on_progress_rom_changed()

    def _on_progress_rom_changed(self):
        rom = self.cmb_progress_rom.currentText()
        if not rom:
            self.progress_view.setHtml("<div style='text-align:center; color:#888;'>(No data available)</div>")
            return
            
        state = self.watcher._ach_state_load()
        unlocked_titles = set()
        all_rules = []

        if rom == "Global":
            import json, os
            gp = f_global_ach(self.cfg)
            if os.path.exists(gp):
                try:
                    with open(gp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        all_rules = data.get("rules", [])
                except Exception:
                    pass
            for r_key, entries in state.get("global", {}).items():
                for e in entries:
                    t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                    unlocked_titles.add(t)
        else:
            s_rules = self.watcher._collect_player_rules_for_rom(rom)
            
            seen_rule_titles = set()
            for r in s_rules:
                if isinstance(r, dict) and r.get("title"):
                    t = str(r.get("title")).strip()
                    if t not in seen_rule_titles:
                        seen_rule_titles.add(t)
                        all_rules.append(r)
            
            for e in state.get("session", {}).get(rom, []):
                t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                unlocked_titles.add(t)
        
        if not all_rules:
            if rom == "Global":
                self.progress_view.setHtml("<div style='color:#FF7F00; text-align:center;'>No global achievements defined.</div>")
            else:
                self.progress_view.setHtml("<div style='color:#FF7F00; text-align:center;'>No specific achievements defined for this ROM.</div>")
            return
            
        html = ["<style>table {width:100%; border-collapse:collapse;} td {padding:8px; border-bottom:1px solid #444;} .unlocked {color:#00E5FF; font-weight:bold;} .locked {color:#666;}</style>"]
        
        unlocked_count = 0
        cells = []
        for r in all_rules:
            title = str(r.get("title", "Unknown")).strip()
            clean_title = title.replace(" (Session)", "").replace(" (Global)", "")
            
            if title in unlocked_titles or clean_title in unlocked_titles:
                unlocked_count += 1
                cells.append(f"<td class='unlocked'>✅ {clean_title}</td>")
            else:
                cells.append(f"<td class='locked'>🔒 {clean_title}</td>")
                
        pct = round((unlocked_count / len(all_rules)) * 100, 1) if all_rules else 0
        
        rom_label = "Global Achievements" if rom == "Global" else f"ROM: {rom.upper()}"
        html.append(f"<div style='font-size:1.4em; color:#FFFFFF; text-align:center; margin-bottom:5px; font-weight:bold;'>{rom_label}</div>")
        html.append(f"<div style='font-size:1.2em; color:#FF7F00; text-align:center; margin-bottom:15px; font-weight:bold;'>Progress: {unlocked_count} / {len(all_rules)} ({pct}%)</div>")
        
        html.append("<table>")
        COLUMNS = 4
        for i in range(0, len(cells), COLUMNS):
            html.append("<tr>")
            for j in range(COLUMNS):
                if i + j < len(cells):
                    html.append(cells[i + j])
                else:
                    html.append("<td></td>")
            html.append("</tr>")
        html.append("</table>")
        
        final_html = "".join(html)

        try:
            sb = self.progress_view.verticalScrollBar()
            old_val = sb.value()
            self.progress_view.setHtml(final_html)
            sb.setValue(old_val)
        except Exception:
            self.progress_view.setHtml(final_html)
            
    def _build_tab_available_maps(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp = QGroupBox("Supported Tables (from Cloud/Index)")
        lay = QVBoxLayout(grp)
        
        row = QHBoxLayout()
        self.txt_map_search = QLineEdit()
        self.txt_map_search.setPlaceholderText("Search for Table or ROM...")
        self.txt_map_search.textChanged.connect(self._filter_available_maps)
        row.addWidget(self.txt_map_search)
        
        btn_refresh = QPushButton("🔄 Load List")
        btn_refresh.setStyleSheet("background:#FF7F00; color:black; font-weight:bold;")
        btn_refresh.clicked.connect(self._refresh_available_maps)
        row.addWidget(btn_refresh)
        lay.addLayout(row)
        
        self.maps_view = QTextBrowser()
        lay.addWidget(self.maps_view)
        
        layout.addWidget(grp)
        self.main_tabs.addTab(tab, "📚 Available Maps")
        self._all_maps_cache = []

    def _refresh_available_maps(self):
        self.maps_view.setHtml("<div style='color:#00E5FF; text-align:center; font-size:1.2em; margin-top:20px;'>Loading maps from database... Please wait.</div>")
        QApplication.processEvents()
        
        index_roms = list(self.watcher.INDEX.keys())
        all_roms = sorted(list(set(index_roms)))
        
        self._all_maps_cache = []
        romnames = self.watcher.ROMNAMES or {}
        
        for rom in all_roms:
            if rom.startswith("_"): continue
            title = romnames.get(rom, "Unknown Table")
            self._all_maps_cache.append((rom, title))
            
        self._filter_available_maps()

    def _filter_available_maps(self):
        query = self.txt_map_search.text().lower()
        
        if not self._all_maps_cache:
            self.maps_view.setHtml("<div style='color:#888; text-align:center; margin-top:20px;'>(Click 'Load List' to see all supported tables)</div>")
            return
            
        html = ["<style>table {width:100%; border-collapse:collapse;} th {text-align:left; color:#FF7F00; padding:8px; border-bottom:2px solid #555; background:#111;} td {padding:6px 8px; border-bottom:1px solid #333; color:#DDD; font-weight:bold;}</style>"]
        html.append(f"<div style='margin-bottom:15px; color:#00E5FF; font-weight:bold;'>The online database currently contains NVRAM maps for {len(self._all_maps_cache)} tables.</div>")
        
        html.append("<table><tr><th>Table Name</th><th>ROM Identifier</th><th style='border-left: 2px solid #555; padding-left:15px;'>Table Name</th><th>ROM Identifier</th></tr>")
        
        filtered_items = []
        for rom, title in self._all_maps_cache:
            if query in rom.lower() or query in title.lower():
                filtered_items.append((title, rom))
                if len(filtered_items) > 800: # UI-Freeze Schutz
                    break
                    
        for i in range(0, len(filtered_items), 2):
            title1, rom1 = filtered_items[i]
            html.append("<tr>")
            
            html.append(f"<td>{title1}</td><td style='color:#888;'>{rom1}</td>")
            
            if i + 1 < len(filtered_items):
                title2, rom2 = filtered_items[i + 1]
                html.append(f"<td style='border-left: 2px solid #333; padding-left:15px;'>{title2}</td><td style='color:#888;'>{rom2}</td>")
            else:
                html.append("<td style='border-left: 2px solid #333; padding-left:15px;'></td><td></td>")
                
            html.append("</tr>")
                
        if len(filtered_items) > 800:
            html.append("<tr><td colspan='4' style='color:#FF3B30; text-align:center; padding-top:15px;'>(List truncated... Please refine your search)</td></tr>")
                    
        html.append("</table>")
        self.maps_view.setHtml("".join(html))

    # ==========================================
    # TAB: SYSTEM
    # ==========================================
    def _build_tab_system(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_profile = QGroupBox("Player Profile & Cloud Setup")
        lay_profile = QGridLayout(grp_profile)
        
        self.txt_player_name = QLineEdit()
        self.txt_player_name.setText(self.cfg.OVERLAY.get("player_name", "Player"))
        self.txt_player_name.textChanged.connect(self._save_player_name) 
        
        self.txt_player_id = QLineEdit()
        self.txt_player_id.setText(self.cfg.OVERLAY.get("player_id", "0000"))
        self.txt_player_id.setMaxLength(4)
        self.txt_player_id.setFixedWidth(60)
        self.txt_player_id.textChanged.connect(self._save_player_id)
        
        self.chk_cloud_enabled = QCheckBox("Enable Cloud Sync")
        self.chk_cloud_enabled.setChecked(self.cfg.CLOUD_ENABLED)
        self.chk_cloud_enabled.stateChanged.connect(self._save_cloud_settings)
        
        lay_profile.addWidget(QLabel("Display Name:"), 0, 0)
        lay_profile.addWidget(self.txt_player_name, 0, 1)
        lay_profile.addWidget(QLabel("Player ID (Restore):"), 0, 2)
        lay_profile.addWidget(self.txt_player_id, 0, 3)
        lay_profile.addWidget(self.chk_cloud_enabled, 1, 0, 1, 4)
        
        layout.addWidget(grp_profile)

        grp_paths = QGroupBox("Directory Setup")
        lay_paths = QGridLayout(grp_paths)
        self.base_label = QLabel(f"BASE: {self.cfg.BASE}")
        self.btn_base = QPushButton("Browse..."); self.btn_base.clicked.connect(self.change_base)
        self.nvram_label = QLabel(f"NVRAM: {self.cfg.NVRAM_DIR}")
        self.btn_nvram = QPushButton("Browse..."); self.btn_nvram.clicked.connect(self.change_nvram)
        self.tables_label = QLabel(f"TABLES: {self.cfg.TABLES_DIR}")
        self.btn_tables = QPushButton("Browse..."); self.btn_tables.clicked.connect(self.change_tables)
        lay_paths.addWidget(self.btn_base, 0, 0); lay_paths.addWidget(self.base_label, 0, 1)
        lay_paths.addWidget(self.btn_nvram, 1, 0); lay_paths.addWidget(self.nvram_label, 1, 1)
        lay_paths.addWidget(self.btn_tables, 2, 0); lay_paths.addWidget(self.tables_label, 2, 1)
        lay_paths.setColumnStretch(1, 1); layout.addWidget(grp_paths)

        grp_maint = QGroupBox("Maintenance Tools")
        lay_maint = QVBoxLayout(grp_maint)
        self.btn_repair = QPushButton("Repair Data Folders")
        self.btn_repair.clicked.connect(self._repair_data_folders)
        self.btn_prefetch = QPushButton("Force Cache NVRAM Maps")
        self.btn_prefetch.clicked.connect(self._prefetch_maps_now)
        lay_maint.addWidget(self.btn_repair)
        lay_maint.addWidget(self.btn_prefetch)
        
        lbl_id_warning = QLabel(
            "⚠️ <b>IMPORTANT: Keep your Player ID safe!</b><br>"
            "Do not share your 4-character Player ID with anyone. "
            "Please write it down or save it somewhere safe!"
        )
        lbl_id_warning.setWordWrap(True)
        lbl_id_warning.setStyleSheet("color: #FF7F00; margin-top: 15px; font-size: 10pt; background: #111; padding: 10px; border: 1px solid #FF7F00; border-radius: 5px;")
        lay_maint.addWidget(lbl_id_warning)
        
        layout.addWidget(grp_maint)
        layout.addStretch(1)
        self.main_tabs.addTab(tab, "⚙️ System")

    # ==========================================
    # CLEAN SAVE METHODS
    # ==========================================
    def _save_cloud_settings(self):
        if self.chk_cloud_enabled.isChecked():
            pname = self.txt_player_name.text().strip().lower()
            if not pname or pname == "player":
                self._msgbox_topmost("warn", "Cloud Sync", "Please enter a valid player name in the profile first!")
                self.chk_cloud_enabled.blockSignals(True)
                self.chk_cloud_enabled.setChecked(False)
                self.chk_cloud_enabled.blockSignals(False)
                return
        self.cfg.CLOUD_ENABLED = self.chk_cloud_enabled.isChecked()
        self.cfg.save()
        
    def _save_player_name(self, name):
        self.cfg.OVERLAY["player_name"] = name.strip()
        self.cfg.save()
        if not name.strip() or name.strip().lower() == "player":
            if getattr(self, "chk_cloud_enabled", None) and self.chk_cloud_enabled.isChecked():
                self.chk_cloud_enabled.blockSignals(True)
                self.chk_cloud_enabled.setChecked(False)
                self.chk_cloud_enabled.blockSignals(False)
                self.cfg.CLOUD_ENABLED = False
                self.cfg.save()

    def _save_player_id(self, player_id):
        self.cfg.OVERLAY["player_id"] = player_id.strip()
        self.cfg.save()

    def _init_tooltips_main(self):
        def _set_tip(attr: str, tip: str):
            try:
                w = getattr(self, attr, None)
                if w:
                    w.setToolTip(tip)
            except Exception:
                pass
                
        # Dashboard Tab
        _set_tip("btn_restart", "Restarts the background engine (useful if the tracker hangs).")
        _set_tip("btn_quit", "Completely closes the application and stops all background tracking.")
        _set_tip("btn_minimize", "Minimizes the window to the Windows system tray.")
        _set_tip("status_label", "Current status of the background watcher engine.")
        
        # Controls Tab
        _set_tip("cmb_toggle_src", "Choose whether to use a keyboard key or joystick button to show/hide the main overlay.")
        _set_tip("btn_bind_toggle", "Assign the hotkey used to show/hide the main stats overlay.")
        _set_tip("lbl_toggle_binding", "Currently assigned hotkey for the main overlay.")
        _set_tip("cmb_ch_hotkey_src", "Input source for the challenge 'Action/Start' button.")
        _set_tip("btn_ch_hotkey_bind", "Assign the hotkey used to start challenges or select options.")
        _set_tip("lbl_ch_hotkey_binding", "Currently assigned hotkey for challenge actions.")
        _set_tip("cmb_ch_left_src", "Input source for navigating left in challenge menus.")
        _set_tip("btn_ch_left_bind", "Assign the hotkey used to navigate left.")
        _set_tip("lbl_ch_left_binding", "Currently assigned left navigation hotkey.")
        _set_tip("cmb_ch_right_src", "Input source for navigating right in challenge menus.")
        _set_tip("btn_ch_right_bind", "Assign the hotkey used to navigate right.")
        _set_tip("lbl_ch_right_binding", "Currently assigned right navigation hotkey.")
        _set_tip("sld_ch_volume", "Adjust the volume of the AI voice announcements.")
        _set_tip("chk_ch_voice_mute", "Completely disable spoken voice announcements during challenges.")
        
        # Cloud Tab
        _set_tip("cmb_cloud_category", "Select the leaderboard category you want to view.")
        _set_tip("txt_cloud_rom", "Type the ROM name exactly as it appears in VPX (e.g. afm_113b).")
        _set_tip("btn_cloud_fetch", "Download and display the global highscores from the cloud.")
        
        # System Tab
        _set_tip("txt_player_name", "Enter your display name (used for local records and leaderboards).")
        _set_tip("txt_player_id", "Your unique 4-character ID. Keep this safe to restore your cloud progress after a reinstall!")
        _set_tip("chk_cloud_enabled", "Turn automatic cloud sync for scores and progress on or off.")
        _set_tip("btn_repair", "Recreates missing folders and downloads the base database if corrupted.")
        _set_tip("btn_prefetch", "Forces a background download of all missing NVRAM maps from the internet.")
        _set_tip("base_label", "Current base directory for achievements data.")
        _set_tip("btn_base", "Change the main folder where achievement data and history is saved.")
        _set_tip("nvram_label", "Current NVRAM folder path.")
        _set_tip("btn_nvram", "Change the folder where VPinMAME stores its .nv files.")
        _set_tip("tables_label", "Current VPX tables folder path (optional).")
        _set_tip("btn_tables", "Change the folder where Visual Pinball tables (.vpx) are located.")

    def _init_overlay_tooltips(self):
        tips = {
            # Appearance Tab - Global Styling
            "cmb_font_family": "Select the font style for all text in the overlays.",
            "spn_font_size": "Adjust the base font size (automatically scales headers and body text).",
            "sld_scale": "Scale the main overlay up or down in overall size (percentage).",
            "lbl_scale": "Current overlay scale in percent.",
            
            # Appearance Tab - Main Stats Overlay
            "chk_portrait": "Rotate the main overlay 90 degrees for portrait/cabinet screens.",
            "chk_portrait_ccw": "Rotate counter-clockwise (instead of clockwise) for portrait mode.",
            "btn_overlay_place": "Open a draggable window to set and save the position of the main overlay.",
            "btn_toggle_now": "Instantly show or hide the main overlay for testing.",
            "btn_hide": "Forcefully hide the main overlay if it's currently visible.",
            "chk_overlay_auto_close": "Automatically hide the main overlay after 60 seconds of inactivity.",
            
            # Appearance Tab - Achievement Toasts
            "chk_ach_toast_portrait": "Rotate achievement unlock popups for portrait screens.",
            "chk_ach_toast_ccw": "Rotate achievement popups counter-clockwise.",
            "btn_ach_toast_place": "Set and save the screen position for achievement popups.",
            "btn_test_toast": "Trigger a test achievement popup to check your placement.",
            
            # Appearance Tab - Challenge Menu
            "chk_ch_ov_portrait": "Rotate the challenge selection menu for portrait screens.",
            "chk_ch_ov_ccw": "Rotate the challenge selection menu counter-clockwise.",
            "btn_ch_ov_place": "Set and save the screen position for the challenge menu.",
            "btn_ch_ov_test": "Show the challenge selection menu for testing.",
            
            # Appearance Tab - Timers & Counters
            "chk_ch_timer_portrait": "Rotate timers and counters for portrait screens.",
            "chk_ch_timer_ccw": "Rotate timers and counters counter-clockwise.",
            "btn_ch_timer_place": "Set and save the screen position for the countdown timer.",
            "btn_ch_timer_test": "Show a test countdown timer to check your placement.",
            "btn_flip_counter_place": "Set and save the screen position for the flip challenge counter.",
            "btn_flip_counter_test": "Show a test flip counter to check your placement.",
            
            # Appearance Tab - System Notifications (Mini Info Overlay)
            "chk_mini_info_portrait": "Rotate system notifications (errors, warnings, info) for portrait screens.",
            "chk_mini_info_ccw": "Rotate system notifications counter-clockwise.",
            "btn_mini_info_place": "Set and save the screen position for system notifications.",
            "btn_mini_info_test": "Trigger a test notification to check your placement."
        }
        apply_tooltips(self, tips)
        
    def _init_settings_tooltips(self):
        pass
     
    def update_achievements_tab(self):
        state = secure_load_json(f_achievements_state(self.cfg), {}) or {}
        global_map = state.get("global", {}) or {}
        session_map = state.get("session", {}) or {}
        
        def build_columns_html(data_map: dict) -> str:
            roms = sorted(data_map.keys(), key=lambda s: str(s).lower())
            if not roms:
                return "<div>(no data)</div>"
            cols = []
            for rom in roms:
                entries = data_map.get(rom, []) or []
                items = []
                for e in entries:
                    if isinstance(e, dict):
                        title = str(e.get("title", "")).strip()
                    else:
                        title = str(e).strip()
                        
                    title = title.replace(" (Session)", "").replace(" (Global)", "")
                    
                    if title:
                        items.append(title)
                if not items:
                    continue
                lines = [f"<div style='font-weight:700;margin-bottom:4px;'>{rom}</div>"]
                for it in items:
                    lines.append(f"<div style='margin:2px 0;'>{it}</div>")
                cols.append("".join(lines))
            if not cols:
                return "<div>(no data)</div>"
            html = "<table width='100%'><tr>" + "".join(
                f"<td valign='top' style='padding:0 14px;'>{c}</td>" for c in cols
            ) + "</tr></table>"
            return html
            
        try:
            html_g = build_columns_html(global_map)
            self.ach_view_global.setHtml(html_g)
        except Exception:
            pass

        try:
            html_pl = build_columns_html(session_map)
            self.ach_view_pl.setHtml(html_pl)
        except Exception:
            pass 
        try:
            if hasattr(self, "cmb_progress_rom"):
                self._on_progress_rom_changed()
        except Exception:
            pass

    def _on_ach_toast_custom_toggled(self, state: int):
        use = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_custom"] = bool(use)
        if not use:
            self.cfg.OVERLAY["ach_toast_saved"] = False
        self.cfg.save()

    def _init_achievements_timer(self):
        try:
            self.timer_achievements = QTimer(self)
            self.timer_achievements.setInterval(5000)  # 5 seconds
            self.timer_achievements.timeout.connect(self.update_achievements_tab)
            self.timer_achievements.start()
        except Exception:
            pass 
 
    def _get_icon(self) -> QIcon:
        try:
            p = resource_path("watcher.ico")
            if os.path.isfile(p):
                ic = QIcon(p)
                if not ic.isNull():
                    return ic
        except Exception:
            pass
        try:
            p2 = os.path.join(APP_DIR, "watcher.ico")
            if os.path.isfile(p2):
                ic = QIcon(p2)
                if not ic.isNull():
                    return ic
        except Exception:
            pass

        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        try:
            painter = QPainter(pm)
            painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            painter.setBrush(QColor("#202020"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(1, 1, 30, 30, 6, 6)
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), "AW")
            painter.end()
        except Exception:
            pm.fill(QColor("#202020"))
        return QIcon(pm)

    def _on_portrait_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["portrait_rotate_ccw"] = is_ccw
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_portrait_from_cfg(self.cfg.OVERLAY)
            self.overlay.request_rotation(force=True)
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
            
    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        self.cfg.save()
        try:
            if getattr(self, "tray", None) and self.tray and self.tray.isVisible():
                self.hide()
                event.ignore()
                return
        except Exception:
            pass
        try:
            self._unregister_global_hotkeys()
        except Exception:
            pass
        try:
            self._uninstall_global_keyboard_hook()
        except Exception:
            pass
        try:
            if getattr(self, "watcher", None):
                self.watcher.stop()
        except Exception:
            pass
        event.accept()

    def change_base(self):
        d = QFileDialog.getExistingDirectory(self, "Select BASE directory", self.cfg.BASE)
        if d:
            self.cfg.BASE = d
            self.base_label.setText(f"BASE: {d}")
            self.cfg.save()

    def change_nvram(self):
        d = QFileDialog.getExistingDirectory(self, "Select NVRAM directory", self.cfg.NVRAM_DIR)
        if d:
            self.cfg.NVRAM_DIR = d
            self.nvram_label.setText(f"NVRAM: {d}")
            self.cfg.save()

    def change_tables(self):
        d = QFileDialog.getExistingDirectory(self, "Select TABLES directory", self.cfg.TABLES_DIR)
        if d:
            self.cfg.TABLES_DIR = d
            self.tables_label.setText(f"TABLES (optional): {d}")
            self.cfg.save()

    def _extract_block(self, text: str, header: str) -> str:
        lines = text.splitlines()
        block = []
        capture = False
        for line in lines:
            s = line.strip()
            if s.startswith(f"=== {header} ==="):
                capture = True
                block = []
                continue
            if capture and s.startswith("===") and not s.startswith(f"=== {header} ==="):
                break
            if capture:
                block.append(line)

        if not block:
            return f"<p>No data found for {header}</p>"

        style = """
        <style>
        table { border-collapse: collapse; }
        .inner td { padding: 3px 6px; white-space:nowrap; }
        .inner td:first-child { text-align: left; }
        .inner td:last-child { text-align: right; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        h3 { margin-top: 12px; }
        h4 { margin-top: 10px; margin-bottom: 4px; border-bottom: 1px solid #ccc; }
        </style>
        """
        html = style + f"<h3>{header}</h3>"
        current_section = None
        rows: List[Tuple[str, str]] = []
        skip_section = False

        def flush():
            nonlocal html, rows, current_section
            if rows:
                sec_title = current_section or ""
                if sec_title:
                    html += f"<h4>{sec_title}</h4>"
                html += self._render_multi_columns(rows, 4)
                rows = []
        for raw in block:
            stripped = raw.rstrip()
            if not stripped:
                continue
            st = stripped.strip()
            if st.endswith(":"):
                tag = st[:-1].strip()
                flush()
                low = tag.lower()
                if low in ("achievements (unlocked)", "session achievements"):
                    current_section = None
                    skip_section = True
                else:
                    current_section = tag
                    skip_section = False
                continue
            if skip_section:
                continue
            parts = st.split()
            if len(parts) >= 2:
                key = " ".join(parts[:-1])
                val = parts[-1]
                rows.append((key, val))
            else:
                rows.append((st, ""))
        flush()
        return html

    def _read_latest_session_txt(self) -> str:

        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        if not os.path.isdir(stats_dir):
            return ""
        try:
            txt_files = [os.path.join(stats_dir, fn) for fn in os.listdir(stats_dir)
                         if fn.lower().endswith(".txt")]
            if not txt_files:
                return ""
            latest = max(txt_files, key=lambda p: os.path.getmtime(p))
            with open(latest, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return ""

    def _read_latest_session_txt_path(self) -> str:
        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        if not os.path.isdir(stats_dir):
            return ""
        try:
            txt_files = [
                os.path.join(stats_dir, fn)
                for fn in os.listdir(stats_dir)
                if fn.lower().endswith(".txt")
            ]
            if not txt_files:
                return ""
            return max(txt_files, key=lambda p: os.path.getmtime(p))
        except Exception:
            return ""
            
    def _read_raw_nvram_for_current_or_last_rom(self) -> tuple[str, bytes]:
        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            rom = ""

        if not rom:
            p = self._read_latest_session_txt_path()
            if p and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if line.lower().startswith("rom:"):
                                rom = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass

        if not rom:
            return "", b""

        nv_path = os.path.join(self.cfg.NVRAM_DIR, f"{rom}.nv")
        try:
            with open(nv_path, "rb") as f:
                return rom, f.read()
        except Exception:
            return rom, b""      
      
    def _build_global_parsed_nvram_html(self) -> str:

        style = """
        <style>
          table { border-collapse: collapse; }
          th, td { padding: 0.2em 0.5em; border-bottom: 1px solid rgba(255,255,255,0.15); white-space: nowrap; }
          th { text-align: left; background: rgba(255,255,255,0.05); }
          th.right { text-align: right; }
          td.val { text-align: right; font-weight: bold; color: #FFFFFF; }
          .meta { color: rgba(255,255,255,0.6); margin-bottom: 0.5em; }
        </style>
        """
        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            pass

        if not rom:
            p = self._read_latest_session_txt_path()
            if p and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if line.lower().startswith("rom:"):
                                rom = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass

        if not rom:
            return style + "<div align='center'>(Global Snapshot: ROM unknown)</div>"

        audits, _, _ = self.watcher.read_nvram_audits_with_autofix(rom)

        if not audits:
            return style + f"<div align='center'>(Global Snapshot: No readable NVRAM data found for ROM <b>{rom}</b>)</div>"

        meta = f"<div class='meta'><b>ROM:</b> {rom} &nbsp;&nbsp; <b>All NVRAM values</b></div>"
        
        COLUMNS = 5
        
        rows = ["<tr>"]
        for _ in range(COLUMNS):
            rows.append("<th>Feld / Name</th><th class='right'>Wert</th>")
        rows.append("</tr>")
        
        items = []
        for key in sorted(audits.keys(), key=lambda x: str(x).lower()):
            val = audits[key]
            if isinstance(val, int):
                val_str = f"{val:,}".replace(",", ".")
            else:
                val_str = str(val)
            items.append((key, val_str))

        for i in range(0, len(items), COLUMNS):
            rows.append("<tr>")
            for j in range(COLUMNS):
                if i + j < len(items):
                    key, val_str = items[i + j]
                    rows.append(f"<td>{key}</td><td class='val'>{val_str}</td>")
                else:
                    rows.append("<td></td><td></td>")
            rows.append("</tr>")

        return style + f"<div align='center'>{meta}<table align='center'>" + "".join(rows) + "</table></div>"
      
    @staticmethod
    def _render_multi_columns(rows: List[Tuple[str, str]], columns: int) -> str:
        if columns <= 0:
            columns = 1
        per_col = (len(rows) + columns - 1) // columns
        html = "<table width='100%'><tr>"
        for c in range(columns):
            start = c * per_col
            end = start + per_col
            col_rows = rows[start:end]
            html += "<td valign='top'><table class='inner'>"
            for k, v in col_rows:
                html += f"<tr><td>{k}</td><td>{v}</td></tr>"
            html += "</table></td>"
        html += "</tr></table>"
        return html

    def _parse_player_snapshot(self, content: str, pid: int) -> dict:
        out = {"playtime": "", "achievements": [], "deltas": []}
        if not content:
            return out
        lines = content.splitlines()
        in_block = False
        in_achs = False
        in_deltas = False

        for raw in lines:
            s = raw.rstrip()  
            st = s.strip()
            if st.startswith(f"=== Player {pid} Snapshot ==="):
                in_block = True
                in_achs = False
                in_deltas = False
                continue
            if in_block and st.startswith("===") and not st.startswith(f"=== Player {pid} Snapshot ==="):
                break
            if not in_block:
                continue
            if st.lower().startswith("playtime:"):
                out["playtime"] = st.partition(":")[2].strip()
                continue
            if st.endswith(":"):
                t = st[:-1].strip().lower()
                in_achs = (t == "session achievements")
                in_deltas = (t == "session deltas")
                continue
            if in_achs and st:
                if (s.startswith("  ") or s.startswith("\t")):
                    out["achievements"].append(st)
                continue
            if in_deltas and st:
                if (s.startswith("  ") or s.startswith("\t")):
                    parts = st.split()
                    if len(parts) >= 2:
                        key = " ".join(parts[:-1])
                        val = parts[-1]
                        try:
                            ival = int(val)
                            if ival > 0:
                                out["deltas"].append((key, val))
                        except Exception:
                            pass
                continue
        return out

    def _build_player_snapshots_html(self, content: str = "") -> str:
        """
        SINGLE-PLAYER MODE:
        Shows Player 1 snapshot (only changes > 0). 
        Fetches live data or, if the game is closed, persistently loads from session_latest.summary.json.
        """
        def esc(x: Any) -> str:
            return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        style = """
        <style>
          table { border-collapse: collapse; margin-top: 10px; }
          th, td { padding: 0.2em 0.5em; border-bottom: 1px solid rgba(255,255,255,0.15); white-space: nowrap; }
          th { text-align: left; background: rgba(255,255,255,0.05); }
          th.right { text-align: right; }
          td.val { text-align: right; font-weight: bold; color: #00B050; }
          .meta { color: rgba(255,255,255,0.6); margin-bottom: 0.5em; font-size: 0.9em; }
        </style>
        """

        active_deltas = {}
        playtime_str = ""

        try:
            if hasattr(self, "watcher") and getattr(self.watcher, "game_active", False):
                player_data = self.watcher.players.get(1, {})
                live_deltas = player_data.get("session_deltas", {})
                play_sec = int(player_data.get("active_play_seconds", 0.0))
                for k, v in live_deltas.items():
                    if int(v) > 0:
                        active_deltas[k] = int(v)
                if play_sec > 0:
                    m, s = divmod(play_sec, 60)
                    playtime_str = f"{m}m {s}s"
        except Exception:
            pass

        if not active_deltas:
            try:
                import json
                summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        p_list = data.get("players", [])
                        if p_list:
                            p1 = p_list[0]
                            saved_deltas = p1.get("deltas", {})
                            for k, v in saved_deltas.items():
                                if int(v) > 0:
                                    active_deltas[k] = int(v)
                            
                            play_sec = int(p1.get("playtime_sec", 0))
                            if play_sec > 0:
                                m, s = divmod(play_sec, 60)
                                playtime_str = f"{m}m {s}s"
            except Exception:
                pass

        html_lines = []
        html_lines.append("<div align='center'>")
        
        if playtime_str:
            html_lines.append(f"<div class='meta'>Playtime: {esc(playtime_str)} &nbsp;&nbsp;|&nbsp;&nbsp; Actions from the (last) session</div>")

        if not active_deltas:
            html_lines.append("<div style='color:#888; margin-top: 15px;'>(No actions registered in this/last session yet...)</div>")
        else:
            COLUMNS = 3
            html_lines.append("<table align='center'><tr>")
            for _ in range(COLUMNS):
                html_lines.append("<th>Action</th><th class='right'>Count</th>")
            html_lines.append("</tr>")

            items = sorted(list(active_deltas.items()), key=lambda x: str(x[0]).lower())

            for i in range(0, len(items), COLUMNS):
                html_lines.append("<tr>")
                for j in range(COLUMNS):
                    if i + j < len(items):
                        key, value = items[i + j]
                        val_str = f"{value:,}".replace(",", ".")
                        html_lines.append(f"<td>{esc(key)}</td><td class='val'>+{val_str}</td>")
                    else:
                        html_lines.append("<td></td><td></td>")
                html_lines.append("</tr>")

            html_lines.append("</table>")
            
        html_lines.append("</div>")

        return style + "".join(html_lines)

    def update_stats(self):
        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        content = ""
        if os.path.isdir(stats_dir):
            try:
                txt_files = [os.path.join(stats_dir, fn) for fn in os.listdir(stats_dir)
                             if fn.lower().endswith(".txt")]
                if txt_files:
                    latest = max(txt_files, key=lambda p: os.path.getmtime(p))
                    with open(latest, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
            except Exception:
                pass

        def _set_html_preserve_scroll(browser, html):
            try:
                sb = browser.verticalScrollBar()
                old_val = sb.value()
                old_max = max(1, sb.maximum())
                at_bottom_before = (old_val >= old_max - 2)
                ratio = old_val / old_max if old_max > 0 else 0.0
                browser.setHtml(html)
                new_max = max(1, sb.maximum())
                if at_bottom_before:
                    sb.setValue(sb.maximum())
                else:
                    new_val = int(round(ratio * new_max))
                    sb.setValue(max(0, min(new_val, new_max)))
            except Exception:
                try:
                    browser.setHtml(html)
                except Exception:
                    pass

        try:
            if "global" in self.stats_views:
                html_global = self._gui_stats_global_html()
                _set_html_preserve_scroll(self.stats_views["global"], html_global)
        except Exception:
            pass

        try:
            if 1 in self.stats_views:
                html_p1 = self._gui_stats_player1_html(content)
                _set_html_preserve_scroll(self.stats_views[1], html_p1)
        except Exception:
            pass

    def _gui_stats_global_html(self) -> str:
        style = """
        <style>
          table { border-collapse: collapse; margin-top: 10px; }
          th, td { padding: 0.2em 0.5em; border-bottom: 1px solid #444; white-space: nowrap; color: #E0E0E0; }
          th { text-align: left; background: #1A1A1A; font-weight: bold; color: #00E5FF; }
          th.right { text-align: right; }
          td.val { text-align: right; font-weight: bold; color: #FF7F00; }
          .meta { color: #888888; margin-bottom: 0.8em; font-size: 1.1em; font-weight: bold; text-align: center; }
          .rom-title { font-size: 1.6em; font-weight: bold; color: #FFFFFF; text-align: center; margin-bottom: 5px; text-transform: uppercase; }
        </style>
        """
        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            pass

        import os, json
        summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
        
        if not rom:
            p = self._read_latest_session_txt_path()
            if p and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if line.lower().startswith("rom:"):
                                rom = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass

        if not rom and os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rom = data.get("rom", "")
            except Exception:
                pass

        if not rom:
            rom = "Unknown"

        audits, _, _ = self.watcher.read_nvram_audits_with_autofix(rom)
        
        if not audits and os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("rom") == rom:
                        audits = data.get("end_audits", {})
            except Exception:
                pass

        html_lines = ["<div align='center'>"]
        html_lines.append(f"<div class='rom-title'>ROM: {rom}</div>")
        html_lines.append(f"<div class='meta'>All global values</div>")

        if not audits:
            html_lines.append(f"<div style='color:#888; margin-top: 15px;'>(No readable NVRAM data for {rom} found...)</div>")
        else:
            COLUMNS = 5
            html_lines.append("<table align='center'><tr>")
            for _ in range(COLUMNS):
                html_lines.append("<th>Field / Name</th><th class='right'>Value</th>")
            html_lines.append("</tr>")

            items = sorted(list(audits.items()), key=lambda x: str(x[0]).lower())

            for i in range(0, len(items), COLUMNS):
                html_lines.append("<tr>")
                for j in range(COLUMNS):
                    if i + j < len(items):
                        key, val = items[i + j]
                        if isinstance(val, int):
                            val_str = f"{val:,}".replace(",", ".")
                        else:
                            val_str = str(val)
                        html_lines.append(f"<td>{key}</td><td class='val'>{val_str}</td>")
                    else:
                        html_lines.append("<td></td><td></td>")
                html_lines.append("</tr>")

            html_lines.append("</table>")
            
        html_lines.append("</div>")
        return style + "".join(html_lines)

    def _gui_stats_player1_html(self, content: str = "") -> str:
        def esc(x) -> str:
            return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        style = """
        <style>
          table { border-collapse: collapse; margin-top: 10px; }
          th, td { padding: 0.2em 0.5em; border-bottom: 1px solid #444; white-space: nowrap; color: #E0E0E0; }
          th { text-align: left; background: #1A1A1A; font-weight: bold; color: #00E5FF; }
          th.right { text-align: right; }
          td.val { text-align: right; font-weight: bold; color: #FF7F00; }
          .meta { color: #888888; margin-bottom: 0.8em; font-size: 1.1em; font-weight: bold; text-align: center; }
          .rom-title { font-size: 1.6em; font-weight: bold; color: #FFFFFF; text-align: center; margin-bottom: 5px; text-transform: uppercase; }
        </style>
        """

        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            pass
        if not rom and content:
            for line in content.splitlines():
                if line.lower().startswith("rom:"):
                    rom = line.split(":", 1)[1].strip()
                    break
                    
        import os, json
        summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
        if not rom and os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rom = data.get("rom", "")
            except Exception:
                pass
                
        if not rom:
            rom = "Unknown"

        active_deltas = {}
        playtime_str = ""

        try:
            if hasattr(self, "watcher") and getattr(self.watcher, "game_active", False):
                player_data = self.watcher.players.get(1, {})
                live_deltas = player_data.get("session_deltas", {})
                play_sec = int(player_data.get("active_play_seconds", 0.0))
                for k, v in live_deltas.items():
                    if int(v) > 0:
                        active_deltas[k] = int(v)
                if play_sec > 0:
                    m, s = divmod(play_sec, 60)
                    playtime_str = f"{m}m {s}s"
        except Exception:
            pass

        if not active_deltas:
            try:
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        p_list = data.get("players", [])
                        if p_list:
                            p1 = p_list[0]
                            saved_deltas = p1.get("deltas", {})
                            for k, v in saved_deltas.items():
                                if int(v) > 0:
                                    active_deltas[k] = int(v)
                            play_sec = int(p1.get("playtime_sec", 0))
                            if play_sec > 0:
                                m, s = divmod(play_sec, 60)
                                playtime_str = f"{m}m {s}s"
            except Exception:
                pass

        html_lines = ["<div align='center'>"]
        html_lines.append(f"<div class='rom-title'>ROM: {esc(rom)}</div>")
        
        if playtime_str:
            html_lines.append(f"<div class='meta'>Playtime: {esc(playtime_str)} &nbsp;&nbsp;|&nbsp;&nbsp; Actions from session</div>")
        else:
            html_lines.append(f"<div class='meta'>Actions from session</div>")

        if not active_deltas:
            html_lines.append("<div style='color:#888; margin-top: 15px;'>(No actions registered in this/last session yet...)</div>")
        else:
            COLUMNS = 3
            html_lines.append("<table align='center'><tr>")
            for _ in range(COLUMNS):
                html_lines.append("<th>Action</th><th class='right'>Count</th>")
            html_lines.append("</tr>")

            items = sorted(list(active_deltas.items()), key=lambda x: str(x[0]).lower())

            for i in range(0, len(items), COLUMNS):
                html_lines.append("<tr>")
                for j in range(COLUMNS):
                    if i + j < len(items):
                        key, value = items[i + j]
                        val_str = f"{value:,}".replace(",", ".")
                        html_lines.append(f"<td>{esc(key)}</td><td class='val'>+{val_str}</td>")
                    else:
                        html_lines.append("<td></td><td></td>")
                html_lines.append("</tr>")

            html_lines.append("</table>")
            
        html_lines.append("</div>")

        return style + "".join(html_lines)

    def _refresh_overlay_live(self):
        if not bool(self.cfg.OVERLAY.get("live_updates", False)):
            return
        try:
            if self.watcher and (self.watcher.game_active or self.watcher._vp_player_visible()):
                try:
                    if self.overlay and self.overlay.isVisible():
                        self.overlay.hide()
                except Exception:
                    pass
                return
        except Exception:
            pass
        if not self.overlay or not self.overlay.isVisible():
            return
        if not self.watcher:
            return
        try:
            import time as _time
            if (_time.monotonic() - getattr(self, "_overlay_last_action", 0.0)) < 0.35:
                return
        except Exception:
            pass
        if getattr(self, "_overlay_busy", False):
            return
        try:
            self._overlay_busy = True

            try:
                self.watcher.force_flush()
            except Exception:
                pass
            
            # Neu bauen und rendern der einzigen Seite!
            self._prepare_overlay_sections()
            secs = self._overlay_cycle.get("sections", [])
            if not secs:
                self._hide_overlay()
                self._overlay_cycle = {"sections": [], "idx": -1}
                return
            
            self._show_overlay_section(secs[0])
            
        finally:
            self._overlay_busy = False

    def _has_highlights(self, entry: dict) -> bool:
        h = entry.get("highlights", {}) or {}
        for cat in ("Power", "Precision", "Fun"):
            if h.get(cat):
                return True
        return False

    def _prepare_overlay_sections(self):
        def _played_entry(p: dict) -> bool:
            try:
                if int(p.get("playtime_sec", 0) or 0) > 0:
                    return True
            except Exception:
                pass
            try:
                if int(p.get("score", 0) or 0) > 0:
                    return True
            except Exception:
                pass
            h = p.get("highlights", {}) or {}
            return any(h.get(cat) for cat in ("Power", "Precision", "Fun"))

        sections = []
        players_raw = read_active_players(self.cfg.BASE)
        combined_players = []
        if players_raw:
            for p in players_raw:
                if not _played_entry(p):
                    continue
                combined_players.append({
                    "id": int(p.get("id", 0)),
                    "highlights": p.get("highlights", {}),
                    "playtime_sec": p.get("playtime_sec", 0),
                    "score": int(p.get("score", 0) or 0),
                })
        
        active_ids = [e for e in combined_players if 1 <= int(e.get("id", 0)) <= 4]
        is_single_player = (len(active_ids) <= 1)
        if is_single_player and combined_players:
            p1 = next((e for e in combined_players if int(e.get("id", 0)) == 1), None)
            combined_players = [p1] if p1 else [combined_players[0]]

        if combined_players:
            # --- Hole die Deltas für unsere einzige Seite ---
            active_deltas = {}
            try:
                live_deltas = self.watcher.players.get(1, {}).get("session_deltas", {})
                for k, v in live_deltas.items():
                    if int(v) > 0:
                        active_deltas[k] = int(v)
            except Exception:
                pass

            if not active_deltas:
                try:
                    import json
                    summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
                    if os.path.isfile(summary_path):
                        with open(summary_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            saved_deltas = data.get("players", [])[0].get("deltas", {})
                            for k, v in saved_deltas.items():
                                if int(v) > 0:
                                    active_deltas[k] = int(v)
                except Exception:
                    pass

            for p in combined_players:
                p["deltas"] = active_deltas

            sections.append({
                "kind": "combined_players",
                "players": combined_players,
                "title": "Session Overview"
            })
            
        self._overlay_cycle = {"sections": sections, "idx": -1}
        
    def _show_overlay_section(self, payload: dict):
        self._ensure_overlay()
        kind = str(payload.get("kind", "")).lower()
        title = str(payload.get("title", "") or "").strip()
        if kind == "combined_players":
            combined = {"players": payload.get("players", [])}
            self.overlay.set_combined(combined, session_title=title or "Active Player Highlights")
            self.overlay.show(); self.overlay.raise_()
            self._start_overlay_auto_close_timer()
            return
        if kind == "html":
            html = payload.get("html", "") or "<div>-</div>"
            self.overlay.set_html(html, session_title=title)
            self.overlay.show(); self.overlay.raise_()
            self._start_overlay_auto_close_timer()
            return
        combined = {"players": [payload]}
        title2 = f"Highlights – {payload.get('title','')}".strip()
        self.overlay.set_combined(combined, session_title=title2)
        self.overlay.show(); self.overlay.raise_()
        self._start_overlay_auto_close_timer()

    def _cycle_overlay_button(self): 

        try:
            if self.watcher and self.watcher.game_active:
                try:
                    if self.overlay and self.overlay.isVisible():
                        self.overlay.hide()
                except Exception:
                    pass
                try:
                    if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                        self._mini_overlay = MiniInfoOverlay(self)
                    self._mini_overlay.show_info("Overlay only available after VPX end", seconds=3, color_hex="#FF3B30")
                except Exception:
                    pass
                return
        except Exception:
            pass
        if getattr(self, "_overlay_busy", False):
            return
        self._overlay_busy = True
        try:
            ov = getattr(self, "overlay", None)
            if not ov or not ov.isVisible():
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
                if not secs:
                    self._msgbox_topmost("info", "Overlay", "No contents available (Global/Player).")
                    return
                self._overlay_cycle["idx"] = 0
                self._show_overlay_section(secs[0])
            else:
                secs = self._overlay_cycle.get("sections", [])
                if not secs:
                    self._prepare_overlay_sections()
                    secs = self._overlay_cycle.get("sections", [])
                    if not secs:
                        self._hide_overlay()
                        self._overlay_cycle = {"sections": [], "idx": -1}
                        return
                    self._overlay_cycle["idx"] = 0
                    self._show_overlay_section(secs[0])
                    return
                idx = int(self._overlay_cycle.get("idx", -1))
                idx = 0 if idx < 0 else idx + 1
                if idx >= len(secs):
                    self._hide_overlay()
                    self._overlay_cycle = {"sections": [], "idx": -1}
                else:
                    self._overlay_cycle["idx"] = idx
                    self._show_overlay_section(secs[idx])
        finally:
            import time as _time
            self._overlay_last_action = _time.monotonic()
            self._overlay_busy = False

    def _speak_en(self, text: str):
        try:
            if bool(self.cfg.OVERLAY.get("challenges_voice_mute", False)):
                return

            vol = int(self.cfg.OVERLAY.get("challenges_voice_volume", 80))
            vol = max(0, min(100, vol))
            try:
                import win32com.client 
                sp = win32com.client.Dispatch("SAPI.SpVoice")
                sp.Volume = vol
                sp.Speak(str(text))
                return
            except Exception:
                pass
        except Exception:
            pass

    def _on_challenge_warmup_show(self, seconds: int, message: str):
        try:
            try:
                self._ch_warmup_sec = int(seconds)
            except Exception:
                self._ch_warmup_sec = 10

            if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                self._mini_overlay = MiniInfoOverlay(self)
            self._mini_overlay.show_info(str(message), max(1, int(seconds)), color_hex="#FF3B30")
            if not hasattr(self, "_ch_last_spoken"):
                self._ch_last_spoken = {}
            now = time.time()
            last = float(self._ch_last_spoken.get("timed", 0.0) or 0.0)
            if now - last > 2.0:
                QTimer.singleShot(0, lambda: self._speak_en("Timed challenge started"))
                self._ch_last_spoken["timed"] = now
        except Exception:
            pass

    def _on_challenge_timer_stop(self):
        try:
            if hasattr(self, "_challenge_timer_delay") and self._challenge_timer_delay:
                self._challenge_timer_delay.stop()
                self._challenge_timer_delay.deleteLater()
        except Exception:
            pass
        self._challenge_timer_delay = None

        try:
            if hasattr(self, "_challenge_timer") and self._challenge_timer:
                self._challenge_timer.close()
                self._challenge_timer.deleteLater()
        except Exception:
            pass
        self._challenge_timer = None

    def _on_challenge_info_show(self, message: str, seconds: int, color_hex: str = "#FFFFFF"):
        try:
            if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                self._mini_overlay = MiniInfoOverlay(self)
            self._mini_overlay.show_info(str(message), max(1, int(seconds)), color_hex=str(color_hex or "#FFFFFF"))
        except Exception:
            pass
        try:
            self._update_challenges_results_view()
        except Exception:
            pass

    def _on_challenge_speak(self, phrase: str):
        self._speak_en(str(phrase or ""))

    def _ensure_overlay(self):
        if self.overlay is None:
            self.overlay = OverlayWindow(self)
        self.overlay.portrait_mode = bool(self.cfg.OVERLAY.get("portrait_mode", True))
        self.overlay._apply_geometry()
        self.overlay._layout_positions()
        self.overlay.request_rotation(force=True)

    def _show_overlay_latest(self):
        from PyQt6.QtCore import QTimer
        import time as _time

        def _do_show():
            try:
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
                if not secs:
                    return
                self._ensure_overlay()
                self._overlay_cycle["idx"] = 0
                self._show_overlay_section(secs[0])
                try:
                    self._overlay_last_action = _time.monotonic()
                except Exception:
                    pass
            except Exception:
                pass
        try:
            w = getattr(self, "watcher", None)
            if w and w._vp_player_visible():
                tries = {"n": 0}
                def _poll():
                    try:
                        if not w._vp_player_visible():
                            _do_show()
                            return
                    except Exception:
                        _do_show()
                        return
                    tries["n"] += 1
                    if tries["n"] < 32:
                        QTimer.singleShot(250, _poll)
                    else:
                        _do_show()
                QTimer.singleShot(250, _poll)
                return
        except Exception:
            pass
        _do_show()
        
    def _on_automap_sampler_started(self, rom: str):
        try:
            self._on_mini_info_show(rom, seconds=10)
        except Exception as e:
            try:
                log(self.cfg, f"[CTRL] mini overlay trigger failed on automap start: {e}")
            except Exception:
                pass

    def _maybe_start_automap(self, rom: str):
        log(self.cfg, f"[AUTOMAP] sampler started for {rom}")
        self._on_automap_sampler_started(rom)
           
    def _on_ach_toast_show(self, title: str, rom: str, seconds: int = 5):
        try:
            self._ach_toast_mgr.enqueue(title, rom, max(1, int(seconds)))
        except Exception:
            pass

    def _hide_overlay(self):
        if self.overlay and self.overlay.isVisible():
            self.overlay.hide()
        try:
            self.overlay_auto_close_timer.stop()
        except Exception:
            pass

        if self.overlay and self.overlay.isVisible():
            self.overlay.hide()
            
    def _toggle_overlay(self):
        if self.watcher and self.watcher.game_active and self.watcher.current_rom:
            if bool(self.cfg.OVERLAY.get("live_updates", False)):
                try:
                    self.watcher.force_flush()
                except Exception:
                    pass
        self._cycle_overlay_button()

    def _on_overlay_test_clicked(self):
        self._ensure_overlay()
        
        dummy_data = {
            "players": [{
                "id": 1,
                "playtime_sec": 420,
                "score": 42069000,
                "deltas": {
                    "Ramps Made": 15,
                    "Jackpots": 4,
                    "Drop Targets": 22,
                    "Loops": 8,
                    "Spinner": 45
                },
                "highlights": {
                    "Power": ["🔥 Best Ball – 12.5M", "💥 Multiball Frenzy – 2", "➕ Extra Balls – 1"],
                    "Precision": ["🏹 Rampage – 15", "🎯 Combo King – 4", "🌀 Spinner Madness – 45"],
                    "Fun": ["💀 Tilted – 1"]
                }
            }]
        }
        
        old_rom = getattr(self.watcher, "current_rom", None)
        self.watcher.current_rom = "test_pinball_table"
        
        try:
            self.overlay.set_combined(dummy_data, session_title="Test Highlights")
            self.overlay.show()
            self.overlay.raise_()
            
            QTimer.singleShot(10000, self._hide_overlay)
        finally:
            self.watcher.current_rom = old_rom

    def _on_toggle_keyboard_event(self):
        now = time.monotonic()
        if now - getattr(self, "_last_toggle_ts", 0.0) < 0.40:
            return
        self._last_toggle_ts = now
        if getattr(self, "_overlay_busy", False):
            return
            
        try:
            if getattr(self, "_challenge_select", None) and self._challenge_select.isVisible():
                return
            if getattr(self, "_flip_diff_select", None) and self._flip_diff_select.isVisible():
                return
        except Exception:
            pass

        self._cycle_overlay_button()

    def _on_joy_toggle_poll(self):
        def _need_ch(kind: str) -> int | None:
            if str(self.cfg.OVERLAY.get(f"challenge_{kind}_input_source", "keyboard")).lower() != "joystick":
                return None
            try:
                return int(self.cfg.OVERLAY.get(f"challenge_{kind}_joy_button", 0) or 0)
            except Exception:
                return None
        overlay_src = str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower()
        overlay_btn = int(self.cfg.OVERLAY.get("toggle_joy_button", 0) or 0) if overlay_src == "joystick" else 0
        j_hotkey = _need_ch("hotkey")
        j_left   = _need_ch("left")
        j_right  = _need_ch("right")

        def _bit(btn: int | None) -> int:
            try:
                b = int(btn or 0)
                return (1 << (b - 1)) if b > 0 else 0
            except Exception:
                return 0
        overlay_bit = _bit(overlay_btn)
        hotkey_bit  = _bit(j_hotkey)
        left_bit    = _bit(j_left)
        right_bit   = _bit(j_right)
        interested_mask = overlay_bit | hotkey_bit | left_bit | right_bit
        if interested_mask == 0:
            self._joy_toggle_last_mask = 0
            return
        jix = JOYINFOEX()
        jix.dwSize = ctypes.sizeof(JOYINFOEX)
        jix.dwFlags = JOY_RETURNALL
        mask_all = 0
        for jid in range(16):
            try:
                if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                    mask_all |= int(jix.dwButtons)
            except Exception:
                continue

        newly = (mask_all & ~getattr(self, "_joy_toggle_last_mask", 0))
        self._joy_toggle_last_mask = mask_all
        if newly == 0:
            return
        if hotkey_bit and (newly & hotkey_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_hotkey()
            return
        if left_bit and (newly & left_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_left()
            return
        if right_bit and (newly & right_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_right()
            return
        if overlay_bit and (newly & overlay_bit):
            try:
                ch_ov_visible = bool(getattr(self, "_challenge_select", None) and self._challenge_select.isVisible())
                diff_ov_visible = bool(getattr(self, "_flip_diff_select", None) and self._flip_diff_select.isVisible())
            except Exception:
                ch_ov_visible = False
                diff_ov_visible = False
            if ch_ov_visible or diff_ov_visible or self._challenge_is_active():
                return
            self._cycle_overlay_button()
            return
        
    def _on_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["portrait_mode"] = is_checked
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_portrait_from_cfg(self.cfg.OVERLAY)
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_lines_per_category_changed(self, val: int):
        self.cfg.OVERLAY["lines_per_category"] = int(val)
        self.cfg.save()
        try:
            if self.overlay and self.overlay.isVisible():
                self._refresh_overlay_live()
        except Exception:
            pass

    def _on_overlay_scale(self, val: int):
        self.lbl_scale.setText(f"{val}%")
        self.cfg.OVERLAY["scale_pct"] = int(val)
        self.cfg.save()
        if self.overlay:
            self.overlay.scale_pct = int(val)
            self.overlay._apply_scale(int(val))
            self.overlay._apply_geometry()
            self.overlay._layout_positions()
            self.overlay.request_rotation(force=True)
        try:
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_toggle_source_changed(self, src: str):
        self.cfg.OVERLAY["toggle_input_source"] = src
        self.cfg.save()
        self.lbl_toggle_binding.setText(self._toggle_binding_label_text())
        self._apply_toggle_source()
        self._refresh_input_bindings()
        
    def _apply_toggle_source(self):
        try:
            src_overlay = str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower()
            any_ch_joy = any(
                str(self.cfg.OVERLAY.get(f"challenge_{k}_input_source", "keyboard")).lower() == "joystick"
                for k in ("hotkey", "left", "right")
            )
            need_poll = (src_overlay == "joystick") or any_ch_joy
            if need_poll:
                self._joy_toggle_timer.start()
            else:
                self._joy_toggle_timer.stop()
                self._joy_toggle_last_mask = 0
        except Exception:
            try:
                self._joy_toggle_timer.stop()
            except Exception:
                pass
            self._joy_toggle_last_mask = 0
            
    def _refresh_input_bindings(self):
        try:
            self._install_global_keyboard_hook()  
        except Exception:
            pass
        try:
            self._register_global_hotkeys()       
        except Exception:
            pass
        try:
            self._install_challenge_key_handling()  
        except Exception:
            pass     

    def _on_bind_toggle_clicked(self):
        # 1. Globale Hotkeys deaktivieren
        self._unregister_global_hotkeys()
        self._uninstall_global_keyboard_hook()
        
        src = self.cfg.OVERLAY.get("toggle_input_source", "keyboard")
        is_joy = (src == "joystick")
        
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        dlg.setWindowTitle("Binding")
        dlg.resize(360, 140)
        
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        
        cancelled = {"flag": False}
        start_ts = time.time()
        
        def update_lbl():
            elapsed = time.time() - start_ts
            rem = max(0.0, 10.0 - elapsed)
            btn_txt = "joystick button" if is_joy else "key"
            lbl.setText(f"Press any {btn_txt} to bind…\n(Timeout in {rem:.1f}s; ESC to cancel)")
            return elapsed

        update_lbl()
        
        class _UnifiedFilter(QAbstractNativeEventFilter):
            def __init__(self, parent_ref):
                super().__init__()
                self.parent = parent_ref
                self._done = False
                
            def nativeEventFilter(self, eventType, message):
                if self._done:
                    return False, 0
                try:
                    if eventType == b"windows_generic_MSG":
                        msg = ctypes.wintypes.MSG.from_address(int(message))
                        if msg.message in (0x0100, 0x0104): # WM_KEYDOWN, WM_SYSKEYDOWN
                            vk = int(msg.wParam)
                            
                            if vk == 0x1B:
                                self._done = True
                                cancelled["flag"] = True
                                QTimer.singleShot(0, dlg.reject)
                                return True, 0
                                
                            if not is_joy:
                                if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                                    return False, 0 
                                    
                                lp = int(msg.lParam)
                                scancode = (lp >> 16) & 0xFF
                                extended = (lp >> 24) & 0x01

                                if vk == 0x10:
                                    if scancode == 42: vk = 0xA0
                                    elif scancode == 54: vk = 0xA1
                                elif vk == 0x11: 
                                    vk = 0xA3 if extended else 0xA2
                                    
                                self._done = True
                                self.parent.cfg.OVERLAY["toggle_vk"] = int(vk)
                                self.parent.cfg.save()
                                QTimer.singleShot(0, dlg.accept)
                                return True, 0
                except Exception:
                    pass
                return False, 0

        fil = _UnifiedFilter(self)
        QCoreApplication.instance().installNativeEventFilter(fil)

        def _read_buttons_mask() -> int:
            jix = JOYINFOEX()
            jix.dwSize = ctypes.sizeof(JOYINFOEX)
            jix.dwFlags = JOY_RETURNALL
            m_all = 0
            for jid in range(16):
                try:
                    if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                        m_all |= int(jix.dwButtons)
                except Exception:
                    continue
            return m_all
            
        baseline = _read_buttons_mask() if is_joy else 0
        timer = QTimer(dlg)
        
        def _poll():
            if cancelled["flag"]:
                timer.stop()
                return
                
            elapsed = update_lbl()
            
            if is_joy:
                try:
                    mask = _read_buttons_mask()
                    newly = mask & ~baseline
                    if newly:
                        lsb = newly & -newly
                        idx = lsb.bit_length() - 1
                        btn_num = idx + 1
                        self.cfg.OVERLAY["toggle_joy_button"] = int(btn_num)
                        self.cfg.save()
                        timer.stop()
                        dlg.accept()
                        return
                except Exception:
                    pass
                    
            if elapsed > 10.0:
                timer.stop()
                dlg.reject()

        timer.setInterval(35)
        timer.timeout.connect(_poll)
        timer.start()

        def cleanup():
            try:
                QCoreApplication.instance().removeNativeEventFilter(fil)
            except Exception:
                pass
            self.lbl_toggle_binding.setText(self._toggle_binding_label_text())
            self._refresh_input_bindings()
            
        dlg.finished.connect(cleanup)
        dlg.exec()


    def _on_bind_ch_clicked(self, kind: str):
        self._unregister_global_hotkeys()
        self._uninstall_global_keyboard_hook()
        
        src = self.cfg.OVERLAY.get(f"challenge_{kind}_input_source", "keyboard")
        is_joy = (src == "joystick")
        
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        dlg.setWindowTitle("Binding")
        dlg.resize(360, 140)
        
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        
        cancelled = {"flag": False}
        start_ts = time.time()
        
        def update_lbl():
            elapsed = time.time() - start_ts
            rem = max(0.0, 10.0 - elapsed)
            btn_txt = "joystick button" if is_joy else "key"
            lbl.setText(f"Press any {btn_txt} to bind…\n(Timeout in {rem:.1f}s; ESC to cancel)")
            return elapsed

        update_lbl()

        class _UnifiedFilter(QAbstractNativeEventFilter):
            def __init__(self, parent_ref):
                super().__init__()
                self.parent = parent_ref
                self._done = False
                
            def nativeEventFilter(self, eventType, message):
                if self._done:
                    return False, 0
                try:
                    if eventType == b"windows_generic_MSG":
                        msg = ctypes.wintypes.MSG.from_address(int(message))
                        if msg.message in (0x0100, 0x0104):
                            vk = int(msg.wParam)
                            
                            if vk == 0x1B:
                                self._done = True
                                cancelled["flag"] = True
                                QTimer.singleShot(0, dlg.reject)
                                return True, 0
                                
                            if not is_joy:
                                if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                                    return False, 0
                                    
                                mods = self.parent._get_hotkey_mods_now()
                                self._done = True
                                self.parent.cfg.OVERLAY[f"challenge_{kind}_vk"] = int(vk)
                                self.parent.cfg.OVERLAY[f"challenge_{kind}_mods"] = int(mods)
                                self.parent.cfg.save()
                                QTimer.singleShot(0, dlg.accept)
                                return True, 0
                except Exception:
                    pass
                return False, 0

        fil = _UnifiedFilter(self)
        QCoreApplication.instance().installNativeEventFilter(fil)

        def _read_buttons_mask() -> int:
            jix = JOYINFOEX()
            jix.dwSize = ctypes.sizeof(JOYINFOEX)
            jix.dwFlags = JOY_RETURNALL
            m_all = 0
            for jid in range(16):
                try:
                    if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                        m_all |= int(jix.dwButtons)
                except Exception:
                    continue
            return m_all

        baseline = _read_buttons_mask() if is_joy else 0
        timer = QTimer(dlg)

        def _poll():
            if cancelled["flag"]:
                timer.stop()
                return
                
            elapsed = update_lbl()
            
            if is_joy:
                try:
                    mask = _read_buttons_mask()
                    newly = mask & ~baseline
                    if newly:
                        lsb = newly & -newly
                        idx = lsb.bit_length() - 1
                        btn_num = idx + 1
                        self.cfg.OVERLAY[f"challenge_{kind}_joy_button"] = int(btn_num)
                        self.cfg.save()
                        timer.stop()
                        dlg.accept()
                        return
                except Exception:
                    pass
                    
            if elapsed > 10.0:
                timer.stop()
                dlg.reject()

        timer.setInterval(35)
        timer.timeout.connect(_poll)
        timer.start()

        def cleanup():
            try:
                QCoreApplication.instance().removeNativeEventFilter(fil)
            except Exception:
                pass
                
            if kind == "hotkey":
                self.lbl_ch_hotkey_binding.setText(self._challenge_binding_label_text("hotkey"))
            elif kind == "left":
                self.lbl_ch_left_binding.setText(self._challenge_binding_label_text("left"))
            else:
                self.lbl_ch_right_binding.setText(self._challenge_binding_label_text("right"))
                
            self._refresh_input_bindings()

        dlg.finished.connect(cleanup)
        dlg.exec()

    def _toggle_binding_label_text(self) -> str:
        src = self.cfg.OVERLAY.get("toggle_input_source", "keyboard")
        if src == "joystick":
            btn = int(self.cfg.OVERLAY.get("toggle_joy_button", 2))
            return f"Current: joystick button {btn}"
        else:
            vk = int(self.cfg.OVERLAY.get("toggle_vk", 120))
            return f"Current: {vk_to_name_en(vk)}"

    def _on_overlay_trigger(self):
        self._toggle_overlay()

    def _on_font_family_changed(self, qfont: QFont):
        family = qfont.family()
        self.cfg.OVERLAY["font_family"] = family
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_font_from_cfg(self.cfg.OVERLAY)

    def _on_font_size_changed(self, val: int):
        body = int(val)
        self.cfg.OVERLAY["base_body_size"] = body
        self.cfg.OVERLAY["base_title_size"] = int(round(body * 1.4))
        self.cfg.OVERLAY["base_hint_size"] = int(round(body * 0.8))
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_font_from_cfg(self.cfg.OVERLAY)
            self.overlay._apply_geometry()
            self.overlay._layout_positions()
            self.overlay.request_rotation(force=True)

    def _restart_watcher(self):
        try:
            if self.watcher:
                self.watcher.stop()
        except Exception:
            pass
        self.watcher = Watcher(self.cfg, self.bridge)
        self.watcher.start()
        self.status_label.setText("Watcher: running")
        self.status_label.setStyleSheet("font: bold 14px 'Segoe UI'; color:#107c10;")
        
    def _install_global_keyboard_hook(self):
        try:
            if getattr(self, "_global_keyhook", None):
                try:
                    self._global_keyhook.uninstall()
                except Exception:
                    pass
            self._global_keyhook = None
        except Exception as e:
            log(self.cfg, f"[HOTKEY] disable hook failed: {e}", "WARN")

    def _register_global_hotkeys(self):
        try:
            try:
                self._unregister_global_hotkeys()
            except Exception:
                pass
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            MOD_NOREPEAT = 0x4000
            ids = {
                "overlay_toggle": 0xA11,
                "ch_hotkey":      0xA21,
                "ch_left":        0xA22,
                "ch_right":       0xA23,
            }

            def _reg(_id: int, vk: int):
                mods = (int(self._mods_for_vk(int(vk))) | MOD_NOREPEAT)
                user32.RegisterHotKey(wintypes.HWND(hwnd), _id, mods, int(vk))

            def _reg_ch(_id: int, vk: int, mods_cfg: int):
                mods = (int(mods_cfg) | MOD_NOREPEAT)
                user32.RegisterHotKey(wintypes.HWND(hwnd), _id, mods, int(vk))
            if str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower() == "keyboard":
                vk_overlay = int(self.cfg.OVERLAY.get("toggle_vk", 120))  # F9
                _reg(ids["overlay_toggle"], vk_overlay)
            if str(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_hotkey_vk", 0x7A))
                mods = int(self.cfg.OVERLAY.get("challenge_hotkey_mods", 0))
                _reg_ch(ids["ch_hotkey"], vk, mods)
            if str(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_left_vk", 0x25))
                mods = int(self.cfg.OVERLAY.get("challenge_left_mods", 0))
                _reg_ch(ids["ch_left"], vk, mods)
            if str(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_right_vk", 0x27))
                mods = int(self.cfg.OVERLAY.get("challenge_right_mods", 0))
                _reg_ch(ids["ch_right"], vk, mods)
            class _HotkeyFilter(QAbstractNativeEventFilter):
                def __init__(self, parent_ref, ids_map):
                    super().__init__()
                    self.p = parent_ref
                    self.ids = ids_map
                def nativeEventFilter(self, eventType, message):
                    try:
                        if eventType == b"windows_generic_MSG":
                            msg = ctypes.wintypes.MSG.from_address(int(message))
                            if msg.message == WM_HOTKEY:
                                hid = int(msg.wParam)
                                if hid == self.ids["overlay_toggle"]:
                                    QTimer.singleShot(0, self.p._on_toggle_keyboard_event)
                                elif hid == self.ids["ch_hotkey"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_hotkey)
                                elif hid == self.ids["ch_left"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_left)
                                elif hid == self.ids["ch_right"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_right)
                    except Exception:
                        pass
                    return False, 0
            self._hotkey_ids = ids
            self._hotkey_filter = _HotkeyFilter(self, ids)
            QCoreApplication.instance().installNativeEventFilter(self._hotkey_filter)
            if getattr(self.cfg, "LOG_CTRL", False):
                log(self.cfg, "[HOTKEY] Registered overlay + challenge hotkeys (keyboard)")
        except Exception as e:
            log(self.cfg, f"[HOTKEY] register failed: {e}", "WARN")
       
    def _uninstall_global_keyboard_hook(self):
        try:
            if getattr(self, "_global_keyhook", None):
                self._global_keyhook.uninstall()
                self._global_keyhook = None
                log(self.cfg, "[HOOK] Global keyboard hook uninstalled")
        except Exception as e:
            log(self.cfg, f"[HOOK] uninstall failed: {e}", "WARN")

    def _unregister_global_hotkeys(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            if getattr(self, "_hotkey_ids", None):
                for _name, _id in list(self._hotkey_ids.items()):
                    try:
                        user32.UnregisterHotKey(wintypes.HWND(hwnd), _id)
                    except Exception:
                        pass
            self._hotkey_ids = {}
        except Exception:
            pass
        try:
            if getattr(self, "_hotkey_filter", None):
                QCoreApplication.instance().removeNativeEventFilter(self._hotkey_filter)  # type: ignore
        except Exception:
            pass
        self._hotkey_filter = None
     
    # ==========================================
    # PREFETCH STATUS ANIMATIONS
    # ==========================================
    def _on_prefetch_started(self):
        self._prefetch_msg = "Checking for missing files..."
        if hasattr(self, "_prefetch_blink_timer"):
            self._prefetch_blink_timer.start()
        self._update_prefetch_label()

    def _on_prefetch_progress(self, msg: str):
        self._prefetch_msg = str(msg)
        self._update_prefetch_label()

    def _on_prefetch_blink(self):
        self._prefetch_blink_state = not getattr(self, "_prefetch_blink_state", False)
        self._update_prefetch_label()

    def _update_prefetch_label(self):
        color = "#FF3B30" if getattr(self, "_prefetch_blink_state", False) else "#333333"
        html = (
            f"🔴 Watcher: PREFETCH IN PROGRESS - {self._prefetch_msg} "
            f"<span style='color:{color}; font-weight:bold;'>PLEASE WAIT</span>"
        )
        self.status_label.setText(html)
        self.status_label.setStyleSheet("font-size: 12pt; color: #FF7F00; padding: 10px;")

    def _on_prefetch_finished(self, msg: str):
        try:
            if hasattr(self, "_prefetch_blink_timer"):
                self._prefetch_blink_timer.stop()
        except Exception:
            pass
        self.status_label.setText(f"🟢 {msg}")
        self.status_label.setStyleSheet("font-size: 11pt; color: #00B050; padding: 10px;")
        QTimer.singleShot(10000, self._reset_status_label)

    def _reset_status_label(self):
        self.status_label.setText("🟢 Watcher: RUNNING...")
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00E5FF; padding: 10px;")

    def _restart_watcher(self):
        try:
            if self.watcher:
                self.watcher.stop()
        except Exception:
            pass
        self.watcher = Watcher(self.cfg, self.bridge)
        self.watcher.start()
        self._reset_status_label()

    def _check_for_updates(self):
        CURRENT_VERSION = "2.2"
        
        def _task():
            try:
                import urllib.request
                import json
                import ssl
                
                url = f"{self.cfg.CLOUD_URL.rstrip('/')}/app_info.json"
                
                req = urllib.request.Request(url)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    
                if data and isinstance(data, dict):
                    latest = str(data.get("latest_version", CURRENT_VERSION))
                    
                    def parse_v(v_str):
                        try:
                            return tuple(map(int, str(v_str).split('.')))
                        except Exception:
                            return (0,)
                    
                    if parse_v(latest) > parse_v(CURRENT_VERSION):
                        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                        msg = f"An important update is available!\n\nCurrent version: {CURRENT_VERSION}\nNew version: {latest}\n\nPlease download the latest version to ensure that cloud sync and achievements work properly."
                        QMetaObject.invokeMethod(self, "_show_update_warning", Qt.ConnectionType.QueuedConnection, Q_ARG(str, msg))
            except Exception as e:
                pass 
                
        threading.Thread(target=_task, daemon=True).start()

    @pyqtSlot(str)
    def _show_update_warning(self, msg: str):
        QMessageBox.warning(self, "Update available!", msg)
     
def main():
    cfg = AppConfig.load()
    app = QApplication(sys.argv)
    need_wizard = cfg.FIRST_RUN or not os.path.isdir(cfg.BASE)
    if need_wizard:
        if not os.path.isdir(cfg.BASE):
            home_alt = os.path.join(os.path.expanduser("~"), "Achievements")
            if not os.path.exists(cfg.BASE) and not os.path.exists(home_alt):
                cfg.BASE = home_alt
        wiz = SetupWizardDialog(cfg)
        if wiz.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
    for sub in [
        "NVRAM_Maps/maps",
        "session_stats/Highlights",
        "rom_specific_achievements",
        "custom_achievements",
    ]:
        ensure_dir(os.path.join(cfg.BASE, sub))
    bridge = Bridge()
    watcher = Watcher(cfg, bridge)
    win = MainWindow(cfg, watcher, bridge)
    try:
        win._install_global_keyboard_hook()
    except Exception:
        pass
    try:
        win._register_global_hotkeys()
    except Exception:
        pass
    if cfg.FIRST_RUN:
        cfg.FIRST_RUN = False
        cfg.save()
    win.hide()
    code = app.exec()
    cfg.save()
    sys.exit(code)

if __name__ == "__main__":

    main()

