"""Re-export all input/hook symbols from the root input_hook module."""
import sys
import os

# Add project root to path so we can import from root-level input_hook.py
# File lives at src/vpx_achievement_watcher/input/hooks.py → 3 parents up = src/
# then one more = project root
from pathlib import Path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, _PROJECT_ROOT)

from input_hook import *
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
