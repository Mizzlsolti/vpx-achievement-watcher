"""Entry point for vpx_achievement_watcher package."""
from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import QApplication, QDialog

from vpx_achievement_watcher.core.config import AppConfig
from vpx_achievement_watcher.core.watcher import Watcher
from vpx_achievement_watcher.core.helpers import ensure_dir

from vpx_achievement_watcher.ui.bridge import Bridge
from vpx_achievement_watcher.ui.main_window import MainWindow
from vpx_achievement_watcher.ui.dialogs import SetupWizardDialog


def main():
    cfg = AppConfig.load()
    app = QApplication(sys.argv)
    need_wizard = cfg.FIRST_RUN or not os.path.isdir(cfg.BASE)
    if need_wizard:
        if not os.path.isdir(cfg.BASE):
            home_alt = os.path.join(os.path.expanduser("~"), "Achievements")
            if not os.path.exists(cfg.BASE) and not os.path.exists(home_alt):
                cfg.BASE = home_alt
        wiz = SetupWizardDialog(cfg)
        if wiz.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
    for sub in [
        os.path.join("tools", "NVRAM_Maps", "maps"),
        os.path.join("session_stats", "Highlights"),
        os.path.join("Achievements", "rom_specific_achievements"),
        os.path.join("Achievements", "custom_achievements"),
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
    win.hide()
    code = app.exec()
    cfg.save()
    sys.exit(code)


if __name__ == "__main__":
    main()
