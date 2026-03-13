from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import QApplication, QDialog

from config import AppConfig, ensure_dir
from process_manager import Watcher
from gui import Bridge, SetupWizardDialog, MainWindow


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
        "NVRAM_Maps/maps",
        "session_stats/Highlights",
        "rom_specific_achievements",
        "custom_achievements",
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
