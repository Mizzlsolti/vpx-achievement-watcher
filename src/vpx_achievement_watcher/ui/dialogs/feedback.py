from __future__ import annotations

import os
import platform
import sys
import urllib.parse
import webbrowser

from PyQt6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QFileDialog, QTextEdit,
)

from vpx_achievement_watcher.core.config import AppConfig
from vpx_achievement_watcher.utils.version import WATCHER_VERSION
from vpx_achievement_watcher.core.helpers import log, ensure_dir


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
            "QPushButton { background: #FF7F00; color: #fff; font-weight: bold;"
            "  border: none; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #e06d00; }"
            "QPushButton:disabled { background: #555; color: #999; }"
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
