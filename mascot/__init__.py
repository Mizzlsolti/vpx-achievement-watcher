"""mascot — Mascot companion package for VPX Achievement Watcher.

Exports the main classes and shared state from the mascot sub-modules.
"""

from mascot.trophy_data import _TROPHIE_SHARED, _TrophieMemory
from mascot.trophy_render import _TrophieDrawWidget, _PinballDrawWidget
from mascot.trophy_widgets import GUITrophie, OverlayTrophie
from mascot.mascot_memory import MascotMemorySystem

__all__ = [
    "GUITrophie",
    "OverlayTrophie",
    "_TROPHIE_SHARED",
    "_TrophieMemory",
    "_TrophieDrawWidget",
    "_PinballDrawWidget",
    "MascotMemorySystem",
]
