from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
)

from watcher_core import AppConfig, log, ensure_dir


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
                "NVRAM_Maps",
                "NVRAM_Maps/maps",
                "session_stats",
                "session_stats/Highlights",
                "rom_specific_achievements",
                "custom_achievements",
            ]:
                ensure_dir(os.path.join(self.cfg.BASE, sub))
        except Exception:
            pass
