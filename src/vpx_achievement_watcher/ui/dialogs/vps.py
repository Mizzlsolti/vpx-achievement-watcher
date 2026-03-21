"""Backward-compatible re-exports for ui_vps."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from vpx_achievement_watcher.ui.dialogs.vps import *
