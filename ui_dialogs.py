"""Backward-compatible re-exports for ui_dialogs."""
import sys, os
_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
from vpx_achievement_watcher.ui.dialogs import *
