"""
setup_wizard.py – First-Run Setup Wizard (3 pages)

A modal QDialog that appears when the app starts for the first time.
It walks the user through:
  Page 1 – Player Name & Player ID
  Page 2 – Cloud Sync toggle (with async cloud validation)
  Page 3 – Setup Complete summary

Usage (called from app/bootstrap.py):
    wizard = SetupWizardDialog(cfg, main_window)
    wizard.exec()  # modal – blocks until complete
"""

from __future__ import annotations

import copy
import random
import string
import threading

from PyQt6.QtCore import (
    Qt, QTimer, QMetaObject, Q_ARG, pyqtSlot, QRegularExpression,
)
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QDialog, QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QGroupBox, QGridLayout,
)


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_DIALOG_STYLE = """
QDialog {
    background: #111111;
    color: #DDDDDD;
}
QLabel {
    color: #DDDDDD;
    background: transparent;
}
QGroupBox {
    color: #AAAAAA;
    border: 1px solid #333333;
    border-radius: 6px;
    margin-top: 8px;
    font-size: 9pt;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #888888;
}
QLineEdit {
    background: #1C1C1C;
    color: #DDDDDD;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 10pt;
}
QLineEdit:focus {
    border: 1px solid #FF7F00;
}
QPushButton {
    background: #222222;
    color: #DDDDDD;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 9pt;
    min-width: 80px;
}
QPushButton:hover {
    background: #2A2A2A;
    border-color: #FF7F00;
}
QPushButton:pressed {
    background: #1A1A1A;
}
QPushButton:disabled {
    color: #555555;
    background: #1A1A1A;
    border-color: #333333;
}
QPushButton#btn_primary {
    background: #FF7F00;
    color: #000000;
    font-weight: bold;
    border-color: #FF7F00;
}
QPushButton#btn_primary:hover {
    background: #E07000;
}
QPushButton#btn_primary:disabled {
    background: #6B3600;
    color: #333333;
    border-color: #4A2700;
}
QCheckBox {
    color: #DDDDDD;
    font-size: 10pt;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #555555;
    border-radius: 3px;
    background: #1C1C1C;
}
QCheckBox::indicator:checked {
    background: #FF7F00;
    border-color: #FF7F00;
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_player_id() -> str:
    """Generate a random 4-character alphanumeric Player ID.

    Uses uppercase letters and digits, excluding ambiguous characters:
    0 (zero), O (letter O), 1 (one), I (letter I), L (letter L).
    """
    safe_chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(safe_chars, k=4))


def start_countdown(button: QPushButton, label_text: str, seconds: int = 5) -> None:
    """Disable *button* for *seconds* seconds with a visible countdown.

    The button text changes to ``"<label_text> (N)"`` while counting down
    and reverts to ``label_text`` when the button is re-enabled.

    Parameters
    ----------
    button:
        The QPushButton to disable and re-enable.
    label_text:
        The final text the button should display when enabled.
    seconds:
        How many seconds to wait before enabling.  Default: 5.
    """
    button.setEnabled(False)
    remaining = [seconds]

    def _tick():
        if remaining[0] > 0:
            button.setText(f"{label_text} ({remaining[0]})")
            remaining[0] -= 1
        else:
            button.setText(label_text)
            button.setEnabled(True)
            timer.stop()

    timer = QTimer(button)
    timer.setInterval(1000)
    timer.timeout.connect(_tick)
    _tick()   # show initial countdown text immediately
    timer.start()


# ---------------------------------------------------------------------------
# Setup Wizard dialog
# ---------------------------------------------------------------------------

class SetupWizardDialog(QDialog):
    """Modal 3-page first-run Setup Wizard.

    Parameters
    ----------
    cfg:
        Live ``AppConfig`` object.  Updated and saved when the wizard
        completes.
    parent:
        The main application window.
    """

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg

        # Collect wizard choices here while navigating pages
        self._chosen_name: str = ""
        self._chosen_id: str = _generate_player_id()
        # Pre-fill with existing values if already set
        existing_name = (cfg.OVERLAY.get("player_name") or "").strip()
        if existing_name and existing_name.lower() != "player":
            self._chosen_name = existing_name
        existing_id = (cfg.OVERLAY.get("player_id") or "").strip()
        if existing_id and existing_id != "0000" and len(existing_id) == 4:
            self._chosen_id = existing_id

        self._cloud_enabled: bool = False

        # ── Window setup ──────────────────────────────────────────────────
        self.setWindowTitle("VPX Achievement Watcher – Setup")
        self.resize(520, 480)
        self.setStyleSheet(_DIALOG_STYLE)

        # Prevent closing via X or Escape key — wizard must be completed
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )

        # ── Root layout ───────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._page1 = self._build_page1()
        self._page2 = self._build_page2()
        self._page3 = self._build_page3()
        self._stack.addWidget(self._page1)
        self._stack.addWidget(self._page2)
        self._stack.addWidget(self._page3)

        self._stack.setCurrentIndex(0)
        start_countdown(self._btn_next_p1, "Next →", 5)

    # -----------------------------------------------------------------------
    # Block close / escape
    # -----------------------------------------------------------------------

    def closeEvent(self, event):
        """Prevent the dialog from being dismissed without completion."""
        event.ignore()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.ignore()
            return
        super().keyPressEvent(event)

    # -----------------------------------------------------------------------
    # Page builders
    # -----------------------------------------------------------------------

    def _build_page1(self) -> QWidget:
        """Page 1: Player Name + Player ID."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # Header
        lbl_title = QLabel("🎯 Welcome to VPX Achievement Watcher!")
        lbl_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #FF7F00;")
        lbl_sub = QLabel("Let's get you set up in 30 seconds.")
        lbl_sub.setStyleSheet("font-size: 10pt; color: #AAAAAA;")
        lay.addWidget(lbl_title)
        lay.addWidget(lbl_sub)

        # ── Player Name group ─────────────────────────────────────────────
        grp_name = QGroupBox("👤 Player Name")
        grp_name.setStyleSheet(
            "QGroupBox { color: #CCCCCC; border: 1px solid #333; border-radius: 6px;"
            " margin-top: 8px; font-size: 9pt; padding: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        lay_name = QVBoxLayout(grp_name)
        lay_name.setSpacing(6)

        self._txt_name = QLineEdit()
        self._txt_name.setPlaceholderText("Enter your player name…")
        self._txt_name.setText(self._chosen_name)
        _name_rx = QRegularExpression(r"[\p{L}\d /\\!\"§$%&()\-_,.:;]*")
        self._txt_name.setValidator(QRegularExpressionValidator(_name_rx, self._txt_name))

        lbl_name_hint = QLabel(
            'ℹ️ Allowed: Letters, numbers, spaces, and / \\ ! " § $ % & ( ) - _ , . : ;'
        )
        lbl_name_hint.setWordWrap(True)
        lbl_name_hint.setStyleSheet("color: #777777; font-size: 8pt;")

        lbl_name_warn = QLabel("⚠️ The name \"Player\" is not allowed.  ⚠️ Name must be unique — duplicates are rejected.")
        lbl_name_warn.setWordWrap(True)
        lbl_name_warn.setStyleSheet("color: #888888; font-size: 8pt;")

        lay_name.addWidget(self._txt_name)
        lay_name.addWidget(lbl_name_hint)
        lay_name.addWidget(lbl_name_warn)
        lay.addWidget(grp_name)

        # ── Player ID group ───────────────────────────────────────────────
        grp_id = QGroupBox("🔑 Player ID")
        grp_id.setStyleSheet(
            "QGroupBox { color: #CCCCCC; border: 1px solid #333; border-radius: 6px;"
            " margin-top: 8px; font-size: 9pt; padding: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        lay_id = QVBoxLayout(grp_id)
        lay_id.setSpacing(6)

        id_row = QHBoxLayout()
        self._txt_id = QLineEdit()
        self._txt_id.setText(self._chosen_id)
        self._txt_id.setMaxLength(4)
        self._txt_id.setFixedWidth(70)
        self._txt_id.setStyleSheet("font-family: monospace; font-size: 12pt; letter-spacing: 2px;")
        id_row.addWidget(self._txt_id)
        id_row.addStretch(1)
        lay_id.addLayout(id_row)

        lbl_id_important = QLabel(
            "⚠️ IMPORTANT: Write this down!  This ID restores your progress on a new PC.  "
            "Do not share it with anyone."
        )
        lbl_id_important.setWordWrap(True)
        lbl_id_important.setStyleSheet(
            "color: #FF7F00; font-size: 8pt; background: #1A0D00;"
            " border: 1px solid #FF7F00; border-radius: 4px; padding: 6px;"
        )

        lbl_id_returning = QLabel(
            "🔄 Returning player?  Enter your old ID here.  Name must match."
        )
        lbl_id_returning.setWordWrap(True)
        lbl_id_returning.setStyleSheet("color: #777777; font-size: 8pt;")

        lay_id.addWidget(lbl_id_important)
        lay_id.addWidget(lbl_id_returning)
        lay.addWidget(grp_id)

        # ── Error label ───────────────────────────────────────────────────
        self._lbl_error_p1 = QLabel("")
        self._lbl_error_p1.setWordWrap(True)
        self._lbl_error_p1.setStyleSheet("color: #FF4444; font-size: 9pt; min-height: 20px;")
        lay.addWidget(self._lbl_error_p1)

        lay.addStretch(1)

        # ── Button row ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_next_p1 = QPushButton("Next →")
        self._btn_next_p1.setObjectName("btn_primary")
        self._btn_next_p1.clicked.connect(self._on_next_p1)
        btn_row.addWidget(self._btn_next_p1)
        lay.addLayout(btn_row)

        return page

    def _build_page2(self) -> QWidget:
        """Page 2: Cloud Sync."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        lbl_title = QLabel("☁️ Cloud Sync")
        lbl_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #FF7F00;")
        lay.addWidget(lbl_title)

        # ── Cloud Sync group ──────────────────────────────────────────────
        grp_cloud = QGroupBox()
        grp_cloud.setStyleSheet(
            "QGroupBox { border: 1px solid #333; border-radius: 6px;"
            " margin-top: 4px; padding: 12px; }"
        )
        lay_cloud = QVBoxLayout(grp_cloud)
        lay_cloud.setSpacing(10)

        # Toggle row
        toggle_row = QHBoxLayout()
        lbl_toggle = QLabel("Enable Cloud Sync?")
        lbl_toggle.setStyleSheet("font-size: 11pt; font-weight: bold; color: #DDDDDD;")
        self._chk_cloud = QCheckBox()
        self._chk_cloud.setChecked(True)
        toggle_row.addWidget(lbl_toggle)
        toggle_row.addStretch(1)
        toggle_row.addWidget(self._chk_cloud)
        lay_cloud.addLayout(toggle_row)

        lbl_required = QLabel(
            "Required for:\n"
            "  • Score Duels & Tournaments\n"
            "  • Global Leaderboards\n"
            "  • Sharing progress with others"
        )
        lbl_required.setStyleSheet("color: #AAAAAA; font-size: 9pt;")
        lay_cloud.addWidget(lbl_required)

        lbl_privacy = QLabel(
            "Your scores are uploaded securely.  No personal data is shared."
        )
        lbl_privacy.setWordWrap(True)
        lbl_privacy.setStyleSheet("color: #777777; font-size: 8pt;")
        lay_cloud.addWidget(lbl_privacy)

        lay.addWidget(grp_cloud)

        # ── Overlay reminder ──────────────────────────────────────────────
        lbl_overlay_reminder = QLabel(
            "🖼️ Don't forget to configure your Overlays!\n\n"
            "After setup, go to:\n"
            "Appearance → Overlay\n\n"
            "Position all overlays for your screen.\n\n"
            "⚠️ Without this, overlays may appear in wrong positions during gameplay!"
        )
        lbl_overlay_reminder.setWordWrap(True)
        lbl_overlay_reminder.setStyleSheet(
            "color: #FF7F00; font-size: 8pt; background: #1A0D00;"
            " border: 1px solid #FF7F00; border-radius: 4px; padding: 6px;"
        )
        lay.addWidget(lbl_overlay_reminder)

        # ── Error label ───────────────────────────────────────────────────
        self._lbl_error_p2 = QLabel("")
        self._lbl_error_p2.setWordWrap(True)
        self._lbl_error_p2.setStyleSheet("color: #FF4444; font-size: 9pt; min-height: 20px;")
        lay.addWidget(self._lbl_error_p2)

        lay.addStretch(1)

        # ── Button row ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_back_p2 = QPushButton("← Back")
        self._btn_back_p2.clicked.connect(self._on_back_p2)
        btn_row.addWidget(self._btn_back_p2)
        btn_row.addStretch(1)
        self._btn_finish_p2 = QPushButton("Finish")
        self._btn_finish_p2.setObjectName("btn_primary")
        self._btn_finish_p2.clicked.connect(self._on_finish_p2)
        btn_row.addWidget(self._btn_finish_p2)
        lay.addLayout(btn_row)

        return page

    def _build_page3(self) -> QWidget:
        """Page 3: Setup Complete."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        lbl_title = QLabel("✅ Setup Complete!")
        lbl_title.setStyleSheet("font-size: 16pt; font-weight: bold; color: #00C86E;")
        lay.addWidget(lbl_title)

        self._lbl_welcome = QLabel("")
        self._lbl_welcome.setStyleSheet("font-size: 12pt; color: #DDDDDD;")
        lay.addWidget(self._lbl_welcome)

        self._lbl_summary = QLabel("")
        self._lbl_summary.setStyleSheet("font-size: 10pt; color: #AAAAAA;")
        lay.addWidget(self._lbl_summary)

        lbl_next = QLabel(
            "📌 Next steps:\n"
            "  1. Go to the Available Maps tab\n"
            "  2. Load the map list\n"
            "  3. Assign VPS-IDs to your tables\n"
            "  4. Configure your hotkeys in the 🕹️ Controls tab\n\n"
            "VPS-IDs are required for Duels & Leaderboards.\n\n"
            "🕹️ The Controls tab lets you bind the overlay toggle key,\n"
            "duel accept/decline keys, and the show/hide GUI hotkey.\n"
            "Cabinet users: map these to flipper or MagnaSave buttons!\n\n"
            "💡 Use the ❓ Help buttons in each tab for detailed explanations."
        )
        lbl_next.setStyleSheet("font-size: 9pt; color: #AAAAAA; line-height: 150%;")
        lbl_next.setWordWrap(True)
        lay.addWidget(lbl_next)

        lay.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_letsgo = QPushButton("🚀  Let's Go!")
        self._btn_letsgo.setObjectName("btn_primary")
        self._btn_letsgo.clicked.connect(self._on_letsgo)
        btn_row.addWidget(self._btn_letsgo)
        lay.addLayout(btn_row)

        return page

    # -----------------------------------------------------------------------
    # Navigation / Validation
    # -----------------------------------------------------------------------

    def _on_next_p1(self):
        """Validate Page 1 and advance to Page 2."""
        name = self._txt_name.text().strip()
        pid = self._txt_id.text().strip().upper()

        name_empty = not name
        name_reserved = name.lower() == "player"
        # Validate against same regex as system.py line 192
        rx = QRegularExpression(r"[\p{L}\d /\\!\"§$%&()\-_,.:;]*")
        match = rx.match(name)
        name_invalid_chars = not (match.hasMatch() and match.capturedLength() == len(name))
        id_invalid = not pid or len(pid) != 4

        if name_empty and id_invalid:
            self._lbl_error_p1.setText("⛔ Please enter a valid name and a valid 4-character Player ID.")
            return
        if name_empty:
            self._lbl_error_p1.setText("⛔ Please enter a player name.")
            return
        if name_reserved:
            self._lbl_error_p1.setText("⛔ The name 'Player' is not allowed.")
            return
        if name_invalid_chars:
            self._lbl_error_p1.setText("⛔ Invalid characters in name.")
            return
        if id_invalid:
            self._lbl_error_p1.setText("⛔ Player ID must be exactly 4 characters.")
            return

        self._lbl_error_p1.setText("")
        self._chosen_name = name
        self._chosen_id = pid.upper()
        self._txt_id.setText(self._chosen_id)

        self._stack.setCurrentIndex(1)
        start_countdown(self._btn_finish_p2, "Finish", 5)

    def _on_back_p2(self):
        """Go back to Page 1."""
        self._lbl_error_p2.setText("")
        self._stack.setCurrentIndex(0)

    def _on_finish_p2(self):
        """Validate Page 2 and either save or run cloud check."""
        self._lbl_error_p2.setText("")
        cloud_on = self._chk_cloud.isChecked()

        if not cloud_on:
            # No cloud check needed — save and go to Page 3
            self._cloud_enabled = False
            self._save_config()
            self._show_page3()
            return

        # Cloud ON → run async validation
        self._btn_finish_p2.setEnabled(False)
        self._btn_back_p2.setEnabled(False)
        self._btn_finish_p2.setText("Checking…")

        cfg_snap = copy.copy(self.cfg)
        cfg_snap.CLOUD_ENABLED = True
        pid = self._chosen_id
        pname = self._chosen_name

        def _check():
            try:
                from core.cloud_sync import CloudSync
                result = CloudSync.validate_player_identity(cfg_snap, pid, pname)
            except Exception as exc:
                result = {"ok": False, "reason": "error", "msg": f"⛔ Cloud check failed: {exc}"}
            QMetaObject.invokeMethod(
                self, "_on_cloud_result",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(bool, bool(result.get("ok", False))),
                Q_ARG(str, str(result.get("reason", ""))),
                Q_ARG(str, str(result.get("msg", ""))),
            )

        threading.Thread(target=_check, daemon=True).start()

    @pyqtSlot(bool, str, str)
    def _on_cloud_result(self, ok: bool, reason: str, msg: str):
        """Slot: called on GUI thread after cloud validation completes."""
        self._btn_back_p2.setEnabled(True)

        if ok:
            self._cloud_enabled = True
            self._save_config()
            # Upload player name to cloud immediately (same as system.py does)
            self._upload_player_name_async()
            self._show_page3()
            return

        # Validation failed — show error, re-enable finish button
        self._btn_finish_p2.setText("Finish")
        start_countdown(self._btn_finish_p2, "Finish", 5)

        # Map reason codes to user-friendly messages
        if reason == "name_reserved":
            self._lbl_error_p2.setText("⛔ The name 'Player' cannot be used.")
        elif reason == "id_conflict":
            self._lbl_error_p2.setText(
                "⛔ This Player ID is already registered to another player.  "
                "Please choose a different 4-character ID, or enter the correct name for this ID."
            )
        elif reason == "name_conflict":
            self._lbl_error_p2.setText(
                "⛔ This name is already in use by another player.  Please choose a different name."
            )
        else:
            self._lbl_error_p2.setText(msg or "⛔ Cloud validation failed.  Please try again.")

    def _on_letsgo(self):
        """Close the wizard after completion."""
        self.accept()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _save_config(self):
        """Persist wizard choices to config."""
        self.cfg.OVERLAY["player_name"] = self._chosen_name
        self.cfg.OVERLAY["player_id"] = self._chosen_id
        self.cfg.CLOUD_ENABLED = self._cloud_enabled
        self.cfg.OVERLAY["first_setup_done"] = True
        self.cfg.save()

    def _upload_player_name_async(self):
        """Upload the player name to the cloud in a background thread."""
        if not self.cfg.CLOUD_URL:
            return
        pid = self._chosen_id.strip().lower()
        name = self._chosen_name.strip()
        if not pid or not name or name.lower() == "player":
            return
        cfg_ref = self.cfg

        def _upload():
            try:
                from core.cloud_sync import CloudSync
                CloudSync.set_node(cfg_ref, f"players/{pid}/achievements/name", name)
            except Exception:
                pass

        threading.Thread(target=_upload, daemon=True).start()

    def _show_page3(self):
        """Populate and show the completion page."""
        self._lbl_welcome.setText(f"Welcome, {self._chosen_name}! 🎉")
        cloud_str = "✅ Enabled" if self._cloud_enabled else "❌ Disabled"
        self._lbl_summary.setText(
            f"Your Player ID: {self._chosen_id}\n"
            f"Cloud Sync: {cloud_str}"
        )
        self._stack.setCurrentIndex(2)
