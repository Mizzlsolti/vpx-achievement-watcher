"""Backward-compatible re-exports for theme."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from vpx_achievement_watcher.ui.theme import *
