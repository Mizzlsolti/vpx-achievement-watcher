"""Backward-compatible entry point – delegates to the new package."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from vpx_achievement_watcher.__main__ import main
from vpx_achievement_watcher.ui.main_window import MainWindow
from vpx_achievement_watcher.ui.bridge import Bridge

if __name__ == "__main__":
    main()
