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

from watcher_core import AppConfig, WATCHER_VERSION, log, ensure_dir


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


class SetupWizardDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Initial Setup – Achievement Paths")
        self.resize(640, 320)
        main = QVBoxLayout(self)
        info = QLabel(
            "Welcome!\n\n"
            "Select paths for:\n"
            "  1) Base achievements data\n"
            "  2) VPinMAME NVRAM directory\n"
            "  3) (Optional) Tables directory\n\n"
            "You can re-run this wizard later."
        )
        info.setWordWrap(True)
        main.addWidget(info)
        def row(label, val, title):
            lay = QHBoxLayout()
            edit = QLineEdit(val)
            btn = QPushButton("…")
            def pick():
                d = QFileDialog.getExistingDirectory(self, title, edit.text().strip() or os.path.expanduser("~"))
                if d:
                    edit.setText(d)
            btn.clicked.connect(pick)
            lay.addWidget(QLabel(label))
            lay.addWidget(edit, 1)
            lay.addWidget(btn)
            return lay, edit
        lay_base, self.ed_base = row("Base:", self.cfg.BASE, "Select Achievements Base Folder")
        lay_nv, self.ed_nvram = row("NVRAM:", self.cfg.NVRAM_DIR, "Select NVRAM Directory")
        lay_tab, self.ed_tables = row("Tables:", self.cfg.TABLES_DIR, "Select Tables Directory (optional)")
        main.addLayout(lay_base); main.addLayout(lay_nv); main.addLayout(lay_tab)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#c04020;font-weight:bold;")
        main.addWidget(self.lbl_status)
        btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_ok = QPushButton("Apply & Start")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._accept_if_valid)
        btns.addStretch(1); btns.addWidget(btn_cancel); btns.addWidget(btn_ok)
        main.addLayout(btns)
        self.btn_ok = btn_ok
        self.ed_base.textChanged.connect(self._validate)
        self.ed_nvram.textChanged.connect(self._validate)
        self._validate()

    def _validate(self):
        base = self.ed_base.text().strip()
        nvram = self.ed_nvram.text().strip()
        errors = []
        if not base:
            errors.append("Missing base path")
        if nvram and not os.path.isdir(nvram):
            errors.append("NVRAM dir does not exist")
        self.btn_ok.setEnabled(len(errors) == 0)
        self.lbl_status.setText(" / ".join(errors) if errors else "")

    def _accept_if_valid(self):
        self._validate()
        if not self.btn_ok.isEnabled():
            return
        self.cfg.BASE = os.path.abspath(self.ed_base.text().strip())
        if self.ed_nvram.text().strip():
            self.cfg.NVRAM_DIR = os.path.abspath(self.ed_nvram.text().strip())
        if self.ed_tables.text().strip():
            self.cfg.TABLES_DIR = os.path.abspath(self.ed_tables.text().strip())
        self.cfg.FIRST_RUN = False
        self._ensure_base_layout()
        self.cfg.save()
        log(self.cfg, f"[SETUP] BASE={self.cfg.BASE} NVRAM={self.cfg.NVRAM_DIR} TABLES={self.cfg.TABLES_DIR}")
        self.accept()

    def _ensure_base_layout(self):
        try:
            ensure_dir(self.cfg.BASE)
            for sub in [
                os.path.join("tools", "NVRAM_Maps"),
                os.path.join("tools", "NVRAM_Maps", "maps"),
                "session_stats",
                os.path.join("session_stats", "Highlights"),
                os.path.join("Achievements", "rom_specific_achievements"),
            ]:
                ensure_dir(os.path.join(self.cfg.BASE, sub))
        except Exception:
            pass
