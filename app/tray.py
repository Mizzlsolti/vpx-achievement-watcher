from __future__ import annotations

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtCore import QTimer


class TrayMixin:

    def _setup_tray(self, icon):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            menu = QMenu()
            menu.addAction("Open", self._show_from_tray)
            menu.addAction("Quit GUI", self.quit_all)
            self.tray.setContextMenu(menu)
            self.tray.show()

            QTimer.singleShot(1500, lambda: self.tray.showMessage(
                "VPX Achievement Watcher",
                "Watcher is running in the background!",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            ))
        else:
            self.tray = None

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()
        if getattr(self, "_trophie_gui", None):
            if self.cfg.OVERLAY.get("trophie_gui_enabled", True):
                QTimer.singleShot(400, self._trophie_gui.re_greet)
