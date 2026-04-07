from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.config import AppConfig
from core.watcher_core import Watcher, ensure_dir, log
from core.tutorial import TutorialWizardDialog


class Bridge(QObject):
    overlay_trigger = pyqtSignal()
    overlay_show = pyqtSignal()
    mini_info_show = pyqtSignal(str, int)
    ach_toast_show = pyqtSignal(str, str, int)
    achievements_updated = pyqtSignal()
    
    prefetch_started = pyqtSignal()
    prefetch_progress = pyqtSignal(str)
    prefetch_finished = pyqtSignal(str)
    level_up_show = pyqtSignal(str, int)   # (level_name, level_number)
    status_overlay_show = pyqtSignal(str, int, str)  # (message, seconds, color_hex)
    close_secondary_overlays = pyqtSignal()
    session_ended = pyqtSignal(str)  # (rom)
    session_started = pyqtSignal(str, str)  # (rom, table_name)
    duel_received = pyqtSignal(str, str, str)    # (opponent_name, table_name, duel_id)
    duel_accepted = pyqtSignal(str)              # (duel_id)
    duel_result = pyqtSignal(str, str, int, int) # (duel_id, result, your_score, their_score)
    duel_expired = pyqtSignal(str)               # (duel_id)
    duel_info_show = pyqtSignal(str, int, str)   # (message, seconds, color_hex)


def _authors_match(script_authors: list, vps_table: dict) -> bool:
    """Check if any script author matches any author in any tableFile of the VPS entry."""
    if not script_authors:
        return False
    script_set = {a.lower().strip() for a in script_authors}
    for tf in (vps_table.get("tableFiles") or []):
        for a in (tf.get("authors") or []):
            a_norm = a.lower().strip()
            for sa in script_set:
                if sa == a_norm or sa in a_norm or a_norm in sa:
                    return True
    return False


def _parse_version(v_str):
    """Parse a version string like '2.5' or '2.5.1' into a comparable tuple of ints."""
    try:
        return tuple(map(int, str(v_str).split('.')))
    except Exception:
        return (0,)


def main():
    # MainWindow is defined in Achievement_watcher.py which imports this module.
    # By the time main() is called (via `if __name__ == "__main__": main()` at the
    # end of Achievement_watcher.py), the module is already fully loaded in
    # sys.modules as "__main__" (direct run) or "Achievement_watcher" (imported).
    import sys as _sys
    _aw_mod = _sys.modules.get("Achievement_watcher") or _sys.modules.get("__main__")
    if _aw_mod is None or not hasattr(_aw_mod, "MainWindow"):
        raise RuntimeError(
            "main() must be called from Achievement_watcher.py (MainWindow not found)"
        )
    MainWindow = _aw_mod.MainWindow

    cfg = AppConfig.load()
    app = QApplication(sys.argv)
    for sub in [
        os.path.join("tools", "NVRAM_Maps", "maps"),
        os.path.join("session_stats", "Highlights"),
        os.path.join("Achievements", "rom_specific_achievements"),
    ]:
        ensure_dir(os.path.join(cfg.BASE, sub))
    bridge = Bridge()
    watcher = Watcher(cfg, bridge)
    win = MainWindow(cfg, watcher, bridge)
    try:
        win._install_global_keyboard_hook()
    except Exception:
        pass
    try:
        win._register_global_hotkeys()
    except Exception:
        pass
    if cfg.FIRST_RUN:
        cfg.FIRST_RUN = False
        cfg.save()
    if not cfg.TUTORIAL_COMPLETED:
        win.showNormal()
        tutorial = TutorialWizardDialog(cfg, win)
        tutorial.show()
    else:
        win.hide()
    code = app.exec()
    cfg.save()
    sys.exit(code)
