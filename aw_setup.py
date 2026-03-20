"""
aw_setup.py - Standalone Achievement Watcher Setup Wizard
==========================================================
Run this file directly to configure the three core paths before (or
instead of) launching the main Achievement Watcher application:

    python aw_setup.py

The wizard reads any existing config.json from the same directory and
pre-fills the fields so that re-running it acts as an "edit config"
flow.  On completion it writes config.json in the same format that
Achievement_watcher.py expects, so no manual editing is required.

This entry-point is designed to be packaged separately (e.g. compiled
to AW_Setup.exe via PyInstaller) while sharing all logic with the main
application through the existing ui_dialogs / watcher_core modules.
"""

from __future__ import annotations

import sys
import os

# ---------------------------------------------------------------------------
# Ensure we can locate sibling modules (watcher_core, ui_dialogs, …) when
# this file is run directly or compiled to a standalone executable.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PyQt6.QtWidgets import QApplication, QMessageBox

from watcher_core import AppConfig
from ui_dialogs import SetupWizardDialog


def run_setup() -> int:
    """Launch the setup wizard and return an exit code (0 = success, 1 = cancelled)."""
    app = QApplication.instance() or QApplication(sys.argv)

    cfg = AppConfig.load()

    dlg = SetupWizardDialog(cfg)
    dlg.setWindowTitle("Achievement Watcher – Initial Setup")

    result = dlg.exec()

    if result == SetupWizardDialog.DialogCode.Accepted:
        QMessageBox.information(
            None,
            "Setup complete",
            f"Configuration saved.\n\nBase: {cfg.BASE}\nNVRAM: {cfg.NVRAM_DIR}"
            + (f"\nTables: {cfg.TABLES_DIR}" if cfg.TABLES_DIR else ""),
        )
        return 0

    return 1


def main() -> None:
    sys.exit(run_setup())


if __name__ == "__main__":
    main()
