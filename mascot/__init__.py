"""mascot — Mascot companion package for VPX Achievement Watcher.

Exports the main classes and shared state from the mascot sub-modules.
"""

from mascot.mascot import (
    GUITrophie,
    OverlayTrophie,
    _TROPHIE_SHARED,
    _TrophieMemory,
    _TrophieDrawWidget,
    _PinballDrawWidget,
)
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
