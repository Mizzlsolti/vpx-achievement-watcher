"""ui/update_banner.py – Persistent "update available" banner shown at the top of the main window."""
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
import webbrowser

_RELEASES_URL = "https://github.com/Mizzlsolti/vpx-achievement-watcher/releases/latest"

_STYLE_ORANGE = (
    "#UpdateBanner { background-color: #FF7F00; color: #000; border-radius: 4px; }"
    "#UpdateBanner QLabel { color: #000; font-weight: bold; }"
    "#UpdateBanner QPushButton { background-color: #000; color: #FF7F00; "
    "                            border: none; padding: 4px 12px; border-radius: 3px; font-weight: bold; }"
    "#UpdateBanner QPushButton:hover { background-color: #222; }"
)

_STYLE_RED = (
    "#UpdateBanner { background-color: #CC0000; color: #FFF; border-radius: 4px; }"
    "#UpdateBanner QLabel { color: #FFF; font-weight: bold; }"
    "#UpdateBanner QPushButton { background-color: #fff; color: #CC0000; "
    "                            border: none; padding: 4px 12px; border-radius: 3px; font-weight: bold; }"
    "#UpdateBanner QPushButton:hover { background-color: #ddd; }"
)


class UpdateBanner(QFrame):
    """Yellow/orange banner shown at the top of MainWindow when a newer release is available.

    Hidden by default; call set_update_available(tag, current) to show an orange
    "update available" banner, or set_update_required(min_version, current) to show
    a red, non-dismissable "update required" banner when the cloud has blocked
    this version.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateBanner")
        self.setStyleSheet(_STYLE_ORANGE)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)

        self._lbl = QLabel("⬆️  A new version is available!")
        lay.addWidget(self._lbl)
        lay.addStretch(1)

        self._btn_download = QPushButton("Download Update")
        self._btn_download.clicked.connect(lambda: webbrowser.open(_RELEASES_URL))
        lay.addWidget(self._btn_download)

        self._btn_dismiss = QPushButton("✕")
        self._btn_dismiss.setFixedWidth(28)
        self._btn_dismiss.clicked.connect(self.hide)
        lay.addWidget(self._btn_dismiss)

        self.hide()

    def set_update_available(self, new_version: str, current_version: str):
        """Show the orange "update available" banner."""
        self.setStyleSheet(_STYLE_ORANGE)
        self._lbl.setText(
            f"⬆️  Update available: v{new_version} (you have v{current_version}). "
            "Click 'Download Update' to get the latest release."
        )
        self._btn_dismiss.show()
        self.show()

    def set_update_required(self, min_version: str, current_version: str):
        """Show the red, non-dismissable "update required" banner."""
        self.setStyleSheet(_STYLE_RED)
        self._lbl.setText(
            f"🛑  Cloud disabled: this version (v{current_version}) is no longer supported. "
            f"Update to v{min_version} or newer to re-enable duels and leaderboards."
        )
        self._btn_dismiss.hide()
        self.show()
