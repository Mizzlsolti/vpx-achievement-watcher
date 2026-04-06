from __future__ import annotations

import os
import platform
import sys
import urllib.parse
import webbrowser

from PyQt6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QFileDialog, QTextEdit, QFrame, QGridLayout,
)
from PyQt6.QtCore import Qt, QTimer

from core.watcher_core import AppConfig, WATCHER_VERSION, log, ensure_dir, _strip_version_from_name


_REPO_ISSUES_URL = "https://github.com/Mizzlsolti/vpx-achievement-watcher/issues/new"


class FeedbackDialog(QDialog):
    """Dialog for submitting bug reports / feature requests as GitHub Issues."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🐛 Report Bug / Suggest Feature")
        self.setMinimumWidth(520)
        self.setStyleSheet(
            "QDialog { background: #1a1a1a; color: #e0e0e0; }"
            "QLabel { color: #e0e0e0; }"
            "QGroupBox { color: #FF7F00; border: 1px solid #444; margin-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
            "QLineEdit, QTextEdit, QComboBox {"
            "  background: #222; color: #e0e0e0; border: 1px solid #555; padding: 4px; }"
            "QPushButton { background: #333; color: #e0e0e0; border: 1px solid #555;"
            "  padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:disabled { color: #666; }"
        )

        main = QVBoxLayout(self)
        main.setSpacing(10)

        lbl_info = QLabel(
            "Found a bug or have a suggestion?\n"
            "Fill in the details – your browser will open with a pre-filled GitHub issue."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #00E5FF; font-size: 9pt;")
        main.addWidget(lbl_info)

        # Type selector
        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Type:"))
        self.cmb_type = QComboBox()
        self.cmb_type.setStyleSheet(
            "QComboBox QAbstractItemView { min-height: 24px; }"
        )
        self.cmb_type.addItem("🐛 Bug Report", "bug")
        self.cmb_type.addItem("💡 Feature Request / Suggestion", "enhancement")
        row_type.addWidget(self.cmb_type, 1)
        main.addLayout(row_type)

        # Title
        main.addWidget(QLabel("Title:"))
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Brief summary …")
        main.addWidget(self.ed_title)

        # Body
        main.addWidget(QLabel("Description:"))
        self.ed_body = QTextEdit()
        self.ed_body.setPlaceholderText(
            "Describe the bug / suggestion in as much detail as possible …\n\n"
            "Steps to reproduce (for bugs):\n1. …\n2. …"
        )
        self.ed_body.setMinimumHeight(140)
        main.addWidget(self.ed_body)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_submit = QPushButton("📤 Submit")
        self.btn_submit.setStyleSheet(
            "QPushButton { background-color: #FF7F00; color: #FFFFFF; font-weight: bold;"
            "  border: none; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e06d00; }"
            "QPushButton:disabled { background-color: #555555; color: #999999; }"
        )
        self.btn_submit.clicked.connect(self._submit)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_submit)
        main.addLayout(btn_row)

    def _submit(self) -> None:
        title = self.ed_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Title Missing", "Please enter a title.")
            return

        issue_type = self.cmb_type.currentData()
        user_body = self.ed_body.toPlainText().strip()

        # Append system info
        sysinfo = (
            f"\n\n---\n**System Info**\n"
            f"- App Version: {WATCHER_VERSION}\n"
            f"- Python: {sys.version}\n"
            f"- OS: {platform.platform()}"
        )
        full_body = (user_body + sysinfo) if user_body else sysinfo.lstrip()

        labels = "bug,from-app" if issue_type == "bug" else "enhancement,from-app"
        url = (
            f"{_REPO_ISSUES_URL}"
            f"?title={urllib.parse.quote(title)}"
            f"&body={urllib.parse.quote(full_body)}"
            f"&labels={urllib.parse.quote(labels)}"
        )
        webbrowser.open(url)

        QMessageBox.information(
            self,
            "Browser Opened",
            "Your browser has been opened with the pre-filled issue.\n"
            "Please click 'Submit new issue' on GitHub to complete.",
        )
        self.accept()



# ─────────────────────────────────────────────────────────────────────────────
# AchievementBeatenDialog
# ─────────────────────────────────────────────────────────────────────────────

class AchievementBeatenDialog(QDialog):
    """Popup shown when the user's achievement progress has been beaten by another player."""

    def __init__(self, cfg, notif_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Achievement-Progress Beaten!")
        self.setMinimumWidth(500)
        self.setStyleSheet("background:#1a1a1a; color:#DDD;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        lbl_hdr = QLabel("<b style='font-size:14px; color:#FF7F00;'>🎯 Achievement-Progress Beaten!</b>")
        lbl_hdr.setWordWrap(True)
        layout.addWidget(lbl_hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#333;")
        layout.addWidget(sep)

        rom = notif_data.get("rom", "")
        your_score = float(notif_data.get("your_score", 0.0))
        new_leader_name = str(notif_data.get("new_leader_name", ""))
        new_leader_score = float(notif_data.get("new_leader_score", 0.0))

        # Resolve table name from parent watcher ROMNAMES if available
        try:
            romnames = (getattr(parent.watcher, "ROMNAMES", None) or {}) if (parent and hasattr(parent, "watcher")) else {}
        except Exception:
            romnames = {}
        table_name = _strip_version_from_name(romnames.get(rom, rom)) if rom else rom

        # Table info via VPS data
        vps_id = ""
        try:
            from core.config import p_vps_img
            from .vps import _load_vps_mapping, _load_vpsdb
            mapping = _load_vps_mapping(cfg)
            vps_id = mapping.get(rom, "") if mapping else ""

            if vps_id:
                # Reuse VPS data to embed hero panel inline
                tables = _load_vpsdb(cfg)
                vps_entry = None
                tf_entry = None
                if tables:
                    for t in tables:
                        if t.get("id") == vps_id:
                            vps_entry = t
                            break
                        for tf in (t.get("tableFiles") or []):
                            if tf.get("id") == vps_id:
                                vps_entry = t
                                tf_entry = tf
                                break
                        if vps_entry:
                            break

                if vps_entry:
                    from .vps import VpsHeroPanel, _process_pending_image_callbacks
                    img_dir = p_vps_img(cfg)
                    hero = VpsHeroPanel(img_dir, parent=self)
                    hero.update_selection(vps_entry, tf_entry or {})
                    layout.addWidget(hero)
                    self._cb_timer = QTimer(self)
                    self._cb_timer.timeout.connect(_process_pending_image_callbacks)
                    self._cb_timer.start(80)
                else:
                    self._add_basic_info(layout, rom, vps_id, table_name)
            else:
                self._add_basic_info(layout, rom, "", table_name)
        except Exception:
            self._add_basic_info(layout, rom, "", table_name)

        # Styled card: table info
        card_lines = []
        if table_name:
            card_lines.append(
                f"<span style='color:#FF7F00;'><b>🎮 Table:</b></span> <span style='color:#DDD;'>{table_name}</span>"
            )
        if rom:
            card_lines.append(
                f"<span style='color:#FF7F00;'><b>🔧 ROM:</b></span> <span style='color:#DDD;'>{rom}</span>"
            )
        if vps_id:
            card_lines.append(
                f"<span style='color:#FF7F00;'><b>🆔 VPS ID:</b></span> <span style='color:#DDD;'>{vps_id}</span>"
            )
        if card_lines:
            card_html = "<br>".join(card_lines)
            lbl_card = QLabel(f"<div style='line-height:1.6;'>{card_html}</div>")
            lbl_card.setWordWrap(True)
            lbl_card.setStyleSheet(
                "background:#111; border:1px solid #333; border-radius:6px; padding:10px; margin-top:6px;"
            )
            layout.addWidget(lbl_card)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#333;")
        layout.addWidget(sep2)

        # Score comparison — grid layout
        leader_display = new_leader_name if new_leader_name else "Unknown"
        score_grid = QGridLayout()
        score_grid.setHorizontalSpacing(12)
        score_grid.setVerticalSpacing(6)

        lbl_your_txt = QLabel("<span style='font-size:13px; color:#FF7F00;'>↓ Your Progress</span>")
        lbl_your_pct = QLabel(f"<b style='font-size:14px; color:#FF3B30;'>{your_score:.1f}%</b>")
        lbl_your_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        score_grid.addWidget(lbl_your_txt, 0, 0)
        score_grid.addWidget(lbl_your_pct, 0, 1)

        lbl_leader_txt = QLabel(f"<span style='font-size:13px; color:#00C853;'>↑ New Leader: {leader_display}</span>")
        lbl_leader_pct = QLabel(f"<b style='font-size:14px; color:#00C853;'>{new_leader_score:.1f}%</b>")
        lbl_leader_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        score_grid.addWidget(lbl_leader_txt, 1, 0)
        score_grid.addWidget(lbl_leader_pct, 1, 1)

        layout.addLayout(score_grid)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(
            "QPushButton { background-color:#00E5FF; color:#000000; font-weight:bold;"
            " padding:4px 16px; border-radius:3px; border:none; }"
        )
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _add_basic_info(self, layout: QVBoxLayout, rom: str, vps_id: str, table_name: str = ""):
        """Fallback: show table info as a styled card."""
        card_lines = []
        if table_name:
            card_lines.append(
                f"<span style='color:#FF7F00;'><b>🎮 Table:</b></span> <span style='color:#DDD;'>{table_name}</span>"
            )
        if rom:
            card_lines.append(
                f"<span style='color:#FF7F00;'><b>🔧 ROM:</b></span> <span style='color:#DDD;'>{rom}</span>"
            )
        if vps_id:
            card_lines.append(
                f"<span style='color:#FF7F00;'><b>🆔 VPS ID:</b></span> <span style='color:#DDD;'>{vps_id}</span>"
            )
        if card_lines:
            card_html = "<br>".join(card_lines)
            lbl_card = QLabel(f"<div style='line-height:1.6;'>{card_html}</div>")
            lbl_card.setWordWrap(True)
            lbl_card.setStyleSheet(
                "background:#111; border:1px solid #333; border-radius:6px; padding:10px; margin-top:6px;"
            )
            layout.addWidget(lbl_card)
