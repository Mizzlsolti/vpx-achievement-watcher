"""Windows input hook utilities: ctypes structures, Win32 bindings, GlobalKeyHook."""
from __future__ import annotations

import configparser
import ctypes
import os
import sys
import threading
from ctypes import wintypes
from typing import Callable, Dict, List, Optional

_IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

JOY_RETURNALL: int = 0xFF
JOYERR_NOERROR: int = 0

WM_KEYDOWN: int = 0x0100
WM_SYSKEYDOWN: int = 0x0104
WM_HOTKEY: int = 0x0312

WH_KEYBOARD_LL: int = 13

RIDEV_INPUTSINK: int = 0x00000100

# ---------------------------------------------------------------------------
# ctypes structures
# ---------------------------------------------------------------------------

if _IS_WINDOWS:
    class JOYINFOEX(ctypes.Structure):
        _fields_ = [
            ("dwSize",        wintypes.DWORD),
            ("dwFlags",       wintypes.DWORD),
            ("dwXpos",        wintypes.DWORD),
            ("dwYpos",        wintypes.DWORD),
            ("dwZpos",        wintypes.DWORD),
            ("dwRpos",        wintypes.DWORD),
            ("dwUpos",        wintypes.DWORD),
            ("dwVpos",        wintypes.DWORD),
            ("dwButtons",     wintypes.DWORD),
            ("dwButtonNumber", wintypes.DWORD),
            ("dwPOV",         wintypes.DWORD),
            ("dwReserved1",   wintypes.DWORD),
            ("dwReserved2",   wintypes.DWORD),
        ]

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode",      wintypes.DWORD),
            ("scanCode",    wintypes.DWORD),
            ("flags",       wintypes.DWORD),
            ("time",        wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [
            ("usUsagePage", ctypes.c_ushort),
            ("usUsage",     ctypes.c_ushort),
            ("dwFlags",     wintypes.DWORD),
            ("hwndTarget",  wintypes.HWND),
        ]

else:
    # Non-Windows dummy structures so that imports don't fail
    class JOYINFOEX:  # type: ignore[no-redef]
        dwSize = 0
        dwFlags = 0
        dwXpos = 0
        dwYpos = 0
        dwZpos = 0
        dwRpos = 0
        dwUpos = 0
        dwVpos = 0
        dwButtons = 0
        dwButtonNumber = 0
        dwPOV = 0
        dwReserved1 = 0
        dwReserved2 = 0

    class KBDLLHOOKSTRUCT:  # type: ignore[no-redef]
        vkCode = 0
        scanCode = 0
        flags = 0
        time = 0
        dwExtraInfo = 0

    class RAWINPUTDEVICE:  # type: ignore[no-redef]
        usUsagePage = 0
        usUsage = 0
        dwFlags = 0
        hwndTarget = 0

# ---------------------------------------------------------------------------
# Win32 API function bindings
# ---------------------------------------------------------------------------

if _IS_WINDOWS:
    _joyGetPosEx = ctypes.windll.winmm.joyGetPosEx
    _joyGetPosEx.argtypes = [wintypes.UINT, ctypes.POINTER(JOYINFOEX)]
    _joyGetPosEx.restype = wintypes.UINT

    _RegisterRawInputDevices = ctypes.windll.user32.RegisterRawInputDevices
    _RegisterRawInputDevices.argtypes = [
        ctypes.POINTER(RAWINPUTDEVICE),
        wintypes.UINT,
        wintypes.UINT,
    ]
    _RegisterRawInputDevices.restype = wintypes.BOOL

    _MapVirtualKeyW = ctypes.windll.user32.MapVirtualKeyW
    _MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    _MapVirtualKeyW.restype = wintypes.UINT

    _GetKeyNameTextW = ctypes.windll.user32.GetKeyNameTextW
    _GetKeyNameTextW.argtypes = [wintypes.LONG, wintypes.LPWSTR, ctypes.c_int]
    _GetKeyNameTextW.restype = ctypes.c_int

else:
    def _joyGetPosEx(jid, pji):  # type: ignore[misc]
        return 1  # not JOYERR_NOERROR

    def _RegisterRawInputDevices(devices, count, size):  # type: ignore[misc]
        return False

    def _MapVirtualKeyW(code, map_type):  # type: ignore[misc]
        return 0

    def _GetKeyNameTextW(lparam, buf, size):  # type: ignore[misc]
        return 0

# ---------------------------------------------------------------------------
# GlobalKeyHook
# ---------------------------------------------------------------------------

class GlobalKeyHook:
    """Low-level Windows keyboard hook (WH_KEYBOARD_LL).

    *bindings* is a list of dicts, each with:
      - ``"get_vk"``: a zero-argument callable that returns the target VK code
        (``int``).  Evaluated on every key event, so it can be dynamic.
      - ``"on_press"``: a zero-argument callable invoked when that VK is pressed.
    """

    def __init__(self, bindings: List[Dict]) -> None:
        self._bindings = bindings
        self._hook: Optional[int] = None
        self._hook_proc = None  # must hold a reference to prevent GC

    def install(self) -> None:
        if not _IS_WINDOWS:
            return
        if self._hook is not None:
            return  # already installed

        _HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_void_p,
        )

        bindings = self._bindings

        def _hook_proc(nCode: int, wParam: int, lParam: int) -> int:
            try:
                if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    vk = int(kb.vkCode)
                    for binding in bindings:
                        try:
                            bvk = int(binding["get_vk"]())
                            if bvk and bvk == vk:
                                binding["on_press"]()
                        except Exception:
                            pass
            except Exception:
                pass
            return ctypes.windll.user32.CallNextHookEx(
                self._hook, nCode, wParam, lParam
            )

        self._hook_proc = _HOOKPROC(_hook_proc)
        self._hook = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_proc,
            None,
            0,
        )

    def uninstall(self) -> None:
        if not _IS_WINDOWS or self._hook is None:
            return
        ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._hook_proc = None

# ---------------------------------------------------------------------------
# register_raw_input_for_window
# ---------------------------------------------------------------------------

def register_raw_input_for_window(hwnd: int) -> None:
    """Register the keyboard as a raw-input source for *hwnd*.

    Uses ``RIDEV_INPUTSINK`` so that input is received even when the window
    does not have focus.
    """
    if not _IS_WINDOWS:
        return
    rid = RAWINPUTDEVICE()
    rid.usUsagePage = 0x01   # HID_USAGE_PAGE_GENERIC
    rid.usUsage = 0x06       # HID_USAGE_GENERIC_KEYBOARD
    rid.dwFlags = RIDEV_INPUTSINK
    rid.hwndTarget = hwnd
    _RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE))

# ---------------------------------------------------------------------------
# VK / scancode helpers
# ---------------------------------------------------------------------------

# MAPVK_VK_TO_VSC = 0, MAPVK_VSC_TO_VK = 1, MAPVK_VK_TO_CHAR = 2
_MAPVK_VK_TO_VSC = 0
_MAPVK_VSC_TO_VK = 1


def vsc_to_vk(scancode: int) -> int:
    """Convert a keyboard scan-code to a Virtual-Key code.

    Returns 0 if the conversion fails or on non-Windows platforms.
    """
    if not _IS_WINDOWS:
        return 0
    try:
        return int(_MapVirtualKeyW(scancode, _MAPVK_VSC_TO_VK))
    except Exception:
        return 0


def vk_to_name(vk: int) -> str:
    """Return the locale-specific display name for a Virtual-Key code.

    Falls back to ``vk_to_name_en`` on error or non-Windows platforms.
    """
    if not _IS_WINDOWS:
        return vk_to_name_en(vk)
    try:
        scancode = int(_MapVirtualKeyW(vk, _MAPVK_VK_TO_VSC))
        if scancode == 0:
            return vk_to_name_en(vk)
        # GetKeyNameTextW takes an LPARAM-style value; the scan code occupies
        # bits 16-23 (8 bits).  Shifting an 8-bit scan code left by 16 places
        # it in exactly the right position.
        lparam = (scancode & 0xFF) << 16
        buf = ctypes.create_unicode_buffer(64)
        result = int(_GetKeyNameTextW(lparam, buf, len(buf)))
        if result > 0:
            return buf.value
    except Exception:
        pass
    return vk_to_name_en(vk)


# Static English-language VK-code name table for the most common keys.
_VK_NAME_EN: Dict[int, str] = {
    0x01: "LButton",    0x02: "RButton",    0x03: "Cancel",
    0x04: "MButton",    0x05: "XButton1",   0x06: "XButton2",
    0x08: "Backspace",  0x09: "Tab",
    0x0C: "Clear",      0x0D: "Enter",
    0x10: "Shift",      0x11: "Ctrl",       0x12: "Alt",
    0x13: "Pause",      0x14: "CapsLock",
    0x1B: "Esc",
    0x20: "Space",
    0x21: "PgUp",       0x22: "PgDn",
    0x23: "End",        0x24: "Home",
    0x25: "Left",       0x26: "Up",
    0x27: "Right",      0x28: "Down",
    0x2C: "PrintScreen", 0x2D: "Insert",    0x2E: "Delete",
    0x30: "0",          0x31: "1",          0x32: "2",          0x33: "3",
    0x34: "4",          0x35: "5",          0x36: "6",          0x37: "7",
    0x38: "8",          0x39: "9",
    0x41: "A",          0x42: "B",          0x43: "C",          0x44: "D",
    0x45: "E",          0x46: "F",          0x47: "G",          0x48: "H",
    0x49: "I",          0x4A: "J",          0x4B: "K",          0x4C: "L",
    0x4D: "M",          0x4E: "N",          0x4F: "O",          0x50: "P",
    0x51: "Q",          0x52: "R",          0x53: "S",          0x54: "T",
    0x55: "U",          0x56: "V",          0x57: "W",          0x58: "X",
    0x59: "Y",          0x5A: "Z",
    0x5B: "LWin",       0x5C: "RWin",       0x5D: "Menu",
    0x60: "Num0",       0x61: "Num1",       0x62: "Num2",       0x63: "Num3",
    0x64: "Num4",       0x65: "Num5",       0x66: "Num6",       0x67: "Num7",
    0x68: "Num8",       0x69: "Num9",
    0x6A: "Num*",       0x6B: "Num+",       0x6C: "NumSep",
    0x6D: "Num-",       0x6E: "Num.",       0x6F: "Num/",
    0x70: "F1",         0x71: "F2",         0x72: "F3",         0x73: "F4",
    0x74: "F5",         0x75: "F6",         0x76: "F7",         0x77: "F8",
    0x78: "F9",         0x79: "F10",        0x7A: "F11",        0x7B: "F12",
    0x7C: "F13",        0x7D: "F14",        0x7E: "F15",        0x7F: "F16",
    0x80: "F17",        0x81: "F18",        0x82: "F19",        0x83: "F20",
    0x84: "F21",        0x85: "F22",        0x86: "F23",        0x87: "F24",
    0x90: "NumLock",    0x91: "ScrollLock",
    0xA0: "LShift",     0xA1: "RShift",
    0xA2: "LCtrl",      0xA3: "RCtrl",
    0xA4: "LAlt",       0xA5: "RAlt",
    0xBA: ";",          0xBB: "=",          0xBC: ",",
    0xBD: "-",          0xBE: ".",          0xBF: "/",
    0xC0: "`",
    0xDB: "[",          0xDC: "\\",         0xDD: "]",
    0xDE: "'",
}


def vk_to_name_en(vk: int) -> str:
    """Return an English display name for a Virtual-Key code.

    Uses the static mapping table; falls back to ``"VK_0x{vk:02X}"`` for
    unknown codes.
    """
    try:
        vk = int(vk)
        return _VK_NAME_EN.get(vk, f"VK_0x{vk:02X}")
    except Exception:
        return "?"

# ---------------------------------------------------------------------------
# VPinballX INI helpers
# ---------------------------------------------------------------------------

def get_vpx_ini_path_for_current_user() -> str:
    """Return the path of the VPinballX.ini for the current Windows user.

    Checks common installation locations in order of preference.  Returns an
    empty string when no INI file is found or on non-Windows platforms.
    """
    if not _IS_WINDOWS:
        return ""

    candidates: List[str] = []

    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")

    if appdata:
        candidates.append(os.path.join(appdata, "VPinball", "VPinballX.ini"))
        candidates.append(os.path.join(appdata, "VirtualPinball", "VPinballX.ini"))

    if localappdata:
        candidates.append(os.path.join(localappdata, "VPinball", "VPinballX.ini"))
        candidates.append(os.path.join(localappdata, "VirtualPinball", "VPinballX.ini"))

    # Check VPX own-directory paths that are sometimes used.
    # Use the system drive (typically C:) and also check D: as a common
    # secondary drive for VPX installations.
    system_drive = os.environ.get("SystemDrive", "C:")
    drives = [system_drive]
    if system_drive.upper() != "D:":
        drives.append("D:")
    for drive in drives:
        for folder in ("VPinball", "VPinball10", "Visual Pinball", "VPX"):
            candidates.append(os.path.join(drive + os.sep, folder, "VPinballX.ini"))

    for path in candidates:
        if os.path.isfile(path):
            return path

    return ""


def parse_vpx_flipper_bindings(ini_path: str) -> Dict[str, int]:
    """Parse VPinballX.ini and return the flipper key/button bindings.

    Returns a dict with keys ``vk_left``, ``vk_right``, ``joy_left``,
    ``joy_right`` (all ``int``).  Missing or unreadable values default to 0.
    """
    result: Dict[str, int] = {
        "vk_left":   0,
        "vk_right":  0,
        "joy_left":  0,
        "joy_right": 0,
    }
    if not ini_path:
        return result

    try:
        parser = configparser.RawConfigParser()
        parser.read(ini_path, encoding="utf-8")

        # VPX stores bindings in the [Player] section.
        # Common key names (case-insensitive via RawConfigParser):
        #   LFlipKey   / RFlipKey        – keyboard VK codes
        #   JoyLFlipBtn / JoyRFlipBtn    – joystick button numbers (1-based)
        for section in parser.sections():
            sl = section.lower()
            if sl not in ("player", "keys", "keyboard"):
                continue
            def _get_int(keys: List[str]) -> int:
                for k in keys:
                    try:
                        val = parser.get(section, k, fallback=None)
                        if val is not None:
                            return int(str(val).strip())
                    except Exception:
                        pass
                return 0

            vk_l = _get_int(["LFlipKey", "LFlip", "LeftFlipKey"])
            vk_r = _get_int(["RFlipKey", "RFlip", "RightFlipKey"])
            joy_l = _get_int(["JoyLFlipBtn", "JoyLFlip", "JoyLeftFlipBtn"])
            joy_r = _get_int(["JoyRFlipBtn", "JoyRFlip", "JoyRightFlipBtn"])

            if vk_l:
                result["vk_left"] = vk_l
            if vk_r:
                result["vk_right"] = vk_r
            if joy_l:
                result["joy_left"] = joy_l
            if joy_r:
                result["joy_right"] = joy_r

    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Public __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Structures
    "JOYINFOEX",
    "KBDLLHOOKSTRUCT",
    "RAWINPUTDEVICE",
    # Constants
    "JOY_RETURNALL",
    "JOYERR_NOERROR",
    "WM_KEYDOWN",
    "WM_SYSKEYDOWN",
    "WM_HOTKEY",
    "WH_KEYBOARD_LL",
    "RIDEV_INPUTSINK",
    # Win32 function bindings
    "_joyGetPosEx",
    "_RegisterRawInputDevices",
    "_MapVirtualKeyW",
    "_GetKeyNameTextW",
    # Classes
    "GlobalKeyHook",
    # Helper functions
    "vk_to_name",
    "vk_to_name_en",
    "vsc_to_vk",
    "get_vpx_ini_path_for_current_user",
    "parse_vpx_flipper_bindings",
    "register_raw_input_for_window",
]
