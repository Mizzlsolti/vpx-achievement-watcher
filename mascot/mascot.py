"""mascot.py — backward-compatible re-export shim.

All symbols have been moved to:
  mascot.trophy_data    – constants, data structures, _TrophieMemory
  mascot.trophy_render  – _ActionToast, _SpeechBubble, _TrophieDrawWidget, _PinballDrawWidget
  mascot.trophy_widgets – GUITrophie, OverlayTrophie
"""
from mascot.trophy_data import (
    _TROPHIE_SHARED,
    _ZANK_COOLDOWN_MS,
    _IDLE_BICKER_MIN_COOLDOWN_MS,
    _IDLE_BICKER_MAX_COOLDOWN_MS,
    _IDLE_BICKER_MIN_COOLDOWN_GUI_MS,
    _IDLE_BICKER_MAX_COOLDOWN_GUI_MS,
    IDLE, TALKING, HAPPY, SAD, SLEEPY, SURPRISED, DISMISSING,
    _ZANK_PAIRS, _ZANK_GUI_LINES, _ZANK_OVERLAY_LINES,
    _IDLE_BICKER_EXCHANGES,
    _GUI_TIPS, _GUI_EVENT_TIPS, _GUI_IDLE_TIPS, _GUI_RANDOM, _GUI_ZANK, _GUI_DUEL,
    _OV_ROM_START, _OV_SESSION_END, _OV_CHALLENGE, _OV_HEAT, _OV_FLIP, _OV_IDLE,
    _OV_DAYTIME, _OV_RANDOM, _OV_ZANK, _OV_DUEL,
    _TrophieMemory,
)
from mascot.trophy_render import (
    _ActionToast,
    _SpeechBubble,
    _TrophieDrawWidget,
    _PinballDrawWidget,
)
from mascot.trophy_widgets import (
    GUITrophie,
    OverlayTrophie,
)

__all__ = [
    "_TROPHIE_SHARED",
    "_ZANK_COOLDOWN_MS",
    "_IDLE_BICKER_MIN_COOLDOWN_MS",
    "_IDLE_BICKER_MAX_COOLDOWN_MS",
    "_IDLE_BICKER_MIN_COOLDOWN_GUI_MS",
    "_IDLE_BICKER_MAX_COOLDOWN_GUI_MS",
    "IDLE", "TALKING", "HAPPY", "SAD", "SLEEPY", "SURPRISED", "DISMISSING",
    "_ZANK_PAIRS", "_ZANK_GUI_LINES", "_ZANK_OVERLAY_LINES",
    "_IDLE_BICKER_EXCHANGES",
    "_GUI_TIPS", "_GUI_EVENT_TIPS", "_GUI_IDLE_TIPS", "_GUI_RANDOM", "_GUI_ZANK", "_GUI_DUEL",
    "_OV_ROM_START", "_OV_SESSION_END", "_OV_CHALLENGE", "_OV_HEAT", "_OV_FLIP", "_OV_IDLE",
    "_OV_DAYTIME", "_OV_RANDOM", "_OV_ZANK", "_OV_DUEL",
    "_TrophieMemory",
    "_ActionToast",
    "_SpeechBubble",
    "_TrophieDrawWidget",
    "_PinballDrawWidget",
    "GUITrophie",
    "OverlayTrophie",
]
