from __future__ import annotations

import configparser
import os

import ctypes
from ctypes import wintypes

_winmm = ctypes.WinDLL("winmm", use_last_error=True)
_user2 = ctypes.WinDLL("user32", use_last_error=True)

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
WH_KEYBOARD_LL = 13

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]

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
                            from PyQt6.QtCore import QTimer
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

            # Fallbacks for LShift/RShift
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
