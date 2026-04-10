from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QObject, QSharedMemory, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.config import AppConfig
from core.watcher_core import Watcher, ensure_dir, log
from ui.setup_wizard import SetupWizardDialog


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

    # Single-instance guard — prevent multiple copies of the app from running
    _shared = QSharedMemory("VPXAchievementWatcherSingleInstance")
    if not _shared.create(1):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(
            None,
            "VPX Achievement Watcher",
            "VPX Achievement Watcher is already running.\nOnly one instance is allowed.",
        )
        sys.exit(1)
    app._single_instance_guard = _shared  # prevent garbage collection

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

    # ── Setup Wizard logic ──────────────────────────────────────────────────
    # Scenario 1: first_setup_done == True → skip wizard, normal start
    first_setup_done = bool(cfg.OVERLAY.get("first_setup_done", False))
    player_name = (cfg.OVERLAY.get("player_name") or "").strip()
    player_id = (cfg.OVERLAY.get("player_id") or "").strip()

    if first_setup_done:
        # Scenario 1: Already set up — start minimized in system tray
        win.hide()
    elif (
        player_name and player_name.lower() != "player"
        and player_id and player_id != "0000"
        and len(player_id) == 4
    ):
        # Scenario 2: Existing player who updated — mark setup done, start minimized
        cfg.OVERLAY["first_setup_done"] = True
        cfg.save()
        win.hide()
    else:
        # Scenario 3: New player / fresh install — show Setup Wizard
        win.showNormal()
        wizard = SetupWizardDialog(cfg, win)
        wizard.exec()  # modal — blocks until wizard is completed
        # After wizard, refresh System tab fields so they reflect the new values
        try:
            if hasattr(win, "txt_player_name"):
                win.txt_player_name.setText(cfg.OVERLAY.get("player_name", ""))
            if hasattr(win, "txt_player_id"):
                win.txt_player_id.setText(cfg.OVERLAY.get("player_id", ""))
            if hasattr(win, "chk_cloud_enabled"):
                win.chk_cloud_enabled.blockSignals(True)
                win.chk_cloud_enabled.setChecked(cfg.CLOUD_ENABLED)
                win.chk_cloud_enabled.blockSignals(False)
            if cfg.CLOUD_ENABLED and hasattr(win, "_lock_player_identity_fields"):
                win._lock_player_identity_fields(True)
            if cfg.CLOUD_ENABLED:
                if hasattr(win, "_cloud_btns_overlay"):
                    win._cloud_btns_overlay.hide()
                if hasattr(win, "btn_backup_cloud"):
                    win.btn_backup_cloud.setEnabled(True)
                if hasattr(win, "btn_restore_cloud"):
                    win.btn_restore_cloud.setEnabled(True)
                if hasattr(win, "chk_cloud_backup"):
                    win.chk_cloud_backup.setVisible(True)
        except Exception:
            pass
    code = app.exec()
    cfg.save()
    sys.exit(code)
