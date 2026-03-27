"""
aweditor.py – AWEditor: Custom Achievement Editor for Non-ROM Tables
=====================================================================
Provides the AWEditorMixin class, which adds the "🎯 AWEditor" tab to the
main window.  The tab lets users create custom achievements for tables that
have no VPinMAME ROM / NVRAM map and therefore cannot use the normal
achievement-detection pipeline.

Trigger mechanism overview
--------------------------
1. AWEditor generates two files:
     • aw_{TableName}.vbs   – VBScript with a FireAchievement() Sub
     • {TableName}.custom.json – Achievement rule definitions
2. The user copies the .vbs next to the .vpx and adds a LoadScript call.
3. During gameplay the VBScript writes a <event>.trigger file into the
   custom_events/ folder.
4. A separate watchdog (future PR) detects the file and shows a toast.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading  # noqa: F401 – available for subclasses
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from theme import get_theme_color
from watcher_core import (
    ensure_dir,
    ensure_vpxtool,
    p_aweditor,
    p_custom_events,
    p_local_maps,
    run_vpxtool_get_rom,
)

# ---------------------------------------------------------------------------
# Event pattern catalogue
# ---------------------------------------------------------------------------

# Each entry: (regex_pattern, title, event_name, default_checked)
_EVENT_PATTERNS: list[tuple[str, str, str, bool]] = [
    (r"Sub.*Multi[_]?[Bb]all",        "Multiball",     "multiball",     True),
    (r"Sub.*SuperJackpot|Sub.*Super_Jackpot", "Super Jackpot", "super_jackpot", False),
    (r"Sub.*Jackpot",                  "Jackpot",       "jackpot",       True),
    (r"Sub.*Wizard[_]?Mode|Sub.*Wizard", "Wizard Mode", "wizard_mode",   True),
    (r"Sub.*Extra[_]?Ball",            "Extra Ball",    "extra_ball",    False),
    (r"Sub.*Mission",                  "Mission",       "mission",       False),
    (r"Sub.*Combo",                    "Combo",         "combo",         False),
    (r"Sub.*Ramp.*Hit",                "Ramp Hit",      "ramp_hit",      False),
    (r"Sub.*Loop",                     "Loop Shot",     "loop_shot",     False),
    (r"Sub.*Spinner",                  "Spinner",       "spinner",       False),
    (r"Sub.*Skill[_]?[Ss]hot",        "Skillshot",     "skillshot",     False),
    (r"Sub.*Bumper.*Hit",              "Bumper Hit",    "bumper_hit",    False),
    (r"Sub.*Slingshot|Sub.*Sling\b",   "Slingshot",     "slingshot",     False),
    (r"Sub.*Target.*Hit|Sub.*DropTarget", "Target Hit", "target_hit",    False),
    (r"Sub.*Kickback",                 "Kickback",      "kickback",      False),
    (r"Sub.*Outlane",                  "Outlane Save",  "outlane_save",  False),
]

# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _ScanTablesWorker(QThread):
    """Scans TABLES_DIR for .vpx files that have no ROM or no NVRAM map."""

    finished = pyqtSignal(list)  # list of vpx filenames (basename only)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg

    def run(self):
        results: list[str] = []
        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        if not tables_dir or not os.path.isdir(tables_dir):
            self.finished.emit(results)
            return

        for fname in sorted(os.listdir(tables_dir)):
            if not fname.lower().endswith(".vpx"):
                continue
            vpx_path = os.path.join(tables_dir, fname)
            try:
                rom = run_vpxtool_get_rom(self.cfg, vpx_path, suppress_warn=True)
                if rom:
                    # Has a ROM – skip if it also has a map
                    m1 = os.path.join(p_local_maps(self.cfg), f"{rom}.json")
                    m2 = os.path.join(p_local_maps(self.cfg), f"{rom}.map.json")
                    if os.path.isfile(m1) or os.path.isfile(m2):
                        continue
                results.append(fname)
            except Exception:
                results.append(fname)

        self.finished.emit(results)


class _AnalyzeScriptWorker(QThread):
    """Reads the VBScript of a .vpx file and finds matching event Subs."""

    finished = pyqtSignal(list)  # list of (title, sub_name, line_no, event_name, default_checked)

    def __init__(self, cfg, vpx_path: str, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.vpx_path = vpx_path

    def run(self):
        findings: list[tuple[str, str, int, str, bool]] = []
        exe = ensure_vpxtool(self.cfg)
        if not exe:
            self.finished.emit(findings)
            return
        try:
            cp = subprocess.run(
                [exe, "script", "show", self.vpx_path],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=0x08000000,  # CREATE_NO_WINDOW – suppress console popup on Windows
                encoding="utf-8",
                errors="replace",
            )
            script = cp.stdout or ""
        except Exception:
            self.finished.emit(findings)
            return

        seen_events: set[str] = set()
        for lineno, line in enumerate(script.splitlines(), start=1):
            stripped = line.strip()
            for pattern, title, event_name, default_checked in _EVENT_PATTERNS:
                if event_name in seen_events:
                    continue
                if re.search(pattern, stripped, re.IGNORECASE):
                    # Extract the Sub name (everything after "Sub " up to first "(" or space)
                    m = re.match(r"Sub\s+(\w+)", stripped, re.IGNORECASE)
                    sub_name = m.group(1) if m else stripped
                    findings.append((title, sub_name, lineno, event_name, default_checked))
                    seen_events.add(event_name)
                    break  # only first pattern match per line

        self.finished.emit(findings)


# ---------------------------------------------------------------------------
# AWEditorMixin
# ---------------------------------------------------------------------------

class AWEditorMixin:
    """
    Mixin that adds the '🎯 AWEditor' tab to the MainWindow.

    Expects the host class to provide:
        self.cfg          – AppConfig instance
        self.main_tabs    – QTabWidget
        self._add_tab_help_button(layout, key) – bottom-right help button helper
        self._show_tab_help(key) – help dialog helper
    """

    def _build_tab_aweditor(self):
        """Build the 🎯 AWEditor tab and add it to main_tabs."""
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(10, 10, 10, 6)
        outer.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QLabel(
            "<span style='font-size:15px; font-weight:bold; color:#E0E0E0;'>"
            "🎯 AWEditor – Custom Achievements for Non-ROM Tables</span>"
        )
        hdr.setWordWrap(True)
        outer.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#333;")
        outer.addWidget(sep)

        # ── Table selector row ─────────────────────────────────────────────
        row_table = QHBoxLayout()
        row_table.addWidget(QLabel("Table:"))

        self._aw_cmb_tables = QComboBox()
        self._aw_cmb_tables.setMinimumWidth(340)
        self._aw_cmb_tables.setStyleSheet(
            "QComboBox { background:#222; color:#E0E0E0; border:1px solid #444;"
            " border-radius:4px; padding:3px 6px; }"
            "QComboBox::drop-down { border:0; }"
            "QComboBox QAbstractItemView { background:#222; color:#E0E0E0; selection-background-color:#444; }"
        )
        self._aw_cmb_tables.setToolTip(
            "Select a table without a ROM / NVRAM map to create custom achievements for"
        )
        row_table.addWidget(self._aw_cmb_tables, stretch=1)

        self._aw_btn_scan = QPushButton("🔄 Scan")
        self._aw_btn_scan.setFixedWidth(80)
        self._aw_btn_scan.setStyleSheet(self._aw_btn_style())
        self._aw_btn_scan.setToolTip(
            "Rescan the Tables directory for .vpx files without a ROM or NVRAM map (refreshes cache)"
        )
        self._aw_btn_scan.clicked.connect(self._aw_scan_tables)
        row_table.addWidget(self._aw_btn_scan)

        outer.addLayout(row_table)

        # ── Analyze button ────────────────────────────────────────────────
        self._aw_btn_analyze = QPushButton("🔍 Analyze Script")
        self._aw_btn_analyze.setStyleSheet(self._aw_btn_style())
        self._aw_btn_analyze.setToolTip(
            "Extract the VBScript from the selected table and detect common event Subs"
        )
        self._aw_btn_analyze.clicked.connect(self._aw_analyze_script)
        outer.addWidget(self._aw_btn_analyze)

        # ── Detected events group ─────────────────────────────────────────
        grp_detected = QGroupBox("📋 Detected Events in Table Script")
        grp_detected.setStyleSheet(self._aw_groupbox_style())
        detected_layout = QVBoxLayout(grp_detected)

        scroll_det = QScrollArea()
        scroll_det.setWidgetResizable(True)
        scroll_det.setMinimumHeight(140)
        scroll_det.setMaximumHeight(220)
        scroll_det.setStyleSheet("QScrollArea { border: none; background: #181818; }")

        self._aw_detected_container = QWidget()
        self._aw_detected_container.setStyleSheet("background:#181818;")
        self._aw_detected_vbox = QVBoxLayout(self._aw_detected_container)
        self._aw_detected_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._aw_detected_vbox.setSpacing(3)

        self._aw_no_events_lbl = QLabel(
            "<i style='color:#666;'>Click '🔍 Analyze Script' to scan the selected table.</i>"
        )
        self._aw_detected_vbox.addWidget(self._aw_no_events_lbl)

        scroll_det.setWidget(self._aw_detected_container)
        detected_layout.addWidget(scroll_det)
        outer.addWidget(grp_detected)

        # ── Custom achievements group ──────────────────────────────────────
        grp_custom = QGroupBox("✏️ Custom Achievements")
        grp_custom.setStyleSheet(self._aw_groupbox_style())
        custom_outer = QVBoxLayout(grp_custom)

        self._aw_btn_add = QPushButton("+ Add Achievement")
        self._aw_btn_add.setStyleSheet(self._aw_btn_style())
        self._aw_btn_add.setToolTip(
            "Add a new custom achievement row with title, description and event name"
        )
        self._aw_btn_add.clicked.connect(self._aw_add_row)
        custom_outer.addWidget(self._aw_btn_add)

        scroll_cust = QScrollArea()
        scroll_cust.setWidgetResizable(True)
        scroll_cust.setMinimumHeight(120)
        scroll_cust.setMaximumHeight(240)
        scroll_cust.setStyleSheet("QScrollArea { border: none; background: #181818; }")

        self._aw_rows_container = QWidget()
        self._aw_rows_container.setStyleSheet("background:#181818;")
        self._aw_rows_vbox = QVBoxLayout(self._aw_rows_container)
        self._aw_rows_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._aw_rows_vbox.setSpacing(5)

        scroll_cust.setWidget(self._aw_rows_container)
        custom_outer.addWidget(scroll_cust)
        outer.addWidget(grp_custom)

        # Internal state
        self._aw_custom_rows: list[dict] = []   # list of {"title": QLineEdit, "desc": QLineEdit, "event": QLineEdit, "frame": QFrame}
        self._aw_detected_rows: list[dict] = []  # list of {"chk": QCheckBox, "title": str, "sub": str, "lineno": int, "event": str}

        # ── Bottom row: Export + Status + Help ───────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#333;")
        outer.addWidget(sep2)

        btn_row = QHBoxLayout()
        self._aw_btn_export = QPushButton("💾 Export VBS + JSON")
        self._aw_btn_export.setStyleSheet(
            f"QPushButton {{ background:{get_theme_color(self.cfg, 'primary')}; color:#000;"
            " font-weight:bold; border-radius:5px; padding:5px 12px; }}"
            f"QPushButton:hover {{ background:{get_theme_color(self.cfg, 'accent')}; }}"
        )
        self._aw_btn_export.setToolTip(
            "Export the VBS trigger script and JSON achievement definitions to the AWEditor folder"
        )
        self._aw_btn_export.clicked.connect(self._aw_export)
        btn_row.addWidget(self._aw_btn_export)

        btn_row.addStretch(1)

        self._aw_status_lbl = QLabel("")
        self._aw_status_lbl.setStyleSheet("color:#aaa; font-size:9pt;")
        btn_row.addWidget(self._aw_status_lbl)

        outer.addLayout(btn_row)

        self._add_tab_help_button(outer, "aweditor")

        self.main_tabs.addTab(tab, "🎯 AWEditor")

        # Load from cache or kick off initial scan
        self._aw_init_tables()

    # ------------------------------------------------------------------
    # Styling helpers
    # ------------------------------------------------------------------

    def _aw_btn_style(self) -> str:
        primary = get_theme_color(self.cfg, "primary")
        accent  = get_theme_color(self.cfg, "accent")
        return (
            f"QPushButton {{ background:{primary}; color:#000;"
            " font-weight:bold; border-radius:4px; padding:4px 10px; }}"
            f"QPushButton:hover {{ background:{accent}; }}"
        )

    def _aw_groupbox_style(self) -> str:
        accent = get_theme_color(self.cfg, "accent")
        return (
            "QGroupBox { background:#141414; border:1px solid #333; border-radius:6px;"
            " margin-top:8px; font-weight:bold; color:#E0E0E0; }"
            f"QGroupBox::title {{ subcontrol-origin:margin; left:10px; color:{accent}; }}"
        )

    def _aw_lineedit_style(self, invalid: bool = False) -> str:
        border = "#cc3333" if invalid else "#444"
        return (
            f"QLineEdit {{ background:#2a2a2a; color:#E0E0E0; border:1px solid {border};"
            " border-radius:3px; padding:2px 5px; }}"
        )

    # ------------------------------------------------------------------
    # Table scan
    # ------------------------------------------------------------------

    def _aw_scan_tables(self):
        self._aw_btn_scan.setEnabled(False)
        self._aw_btn_scan.setText("⏳")
        self._aw_status_lbl.setText("Scanning tables…")
        worker = _ScanTablesWorker(self.cfg, parent=self)
        worker.finished.connect(self._aw_on_scan_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        # Keep a reference so the thread is not garbage-collected
        self._aw_scan_worker = worker

    def _aw_on_scan_done(self, tables: list[str]):
        self._aw_cmb_tables.clear()
        if tables:
            self._aw_cmb_tables.addItems(tables)
            self._aw_status_lbl.setText(f"Found {len(tables)} table(s).")
        else:
            self._aw_status_lbl.setText("No Non-ROM tables found. Check Tables directory in System tab.")
        self._aw_btn_scan.setEnabled(True)
        self._aw_btn_scan.setText("🔄 Scan")
        self._aw_save_cache(tables)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _aw_cache_path(self) -> str:
        return os.path.join(p_aweditor(self.cfg), "aweditor_scan_cache.json")

    def _aw_load_cache(self) -> list[str] | None:
        """Return the cached table list if it matches the current tables_dir, else None."""
        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        try:
            with open(self._aw_cache_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("tables_dir") == tables_dir and isinstance(data.get("results"), list):
                return data["results"]
        except Exception:
            pass
        return None

    def _aw_save_cache(self, tables: list[str]) -> None:
        """Persist scan results to the cache file."""
        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        path = self._aw_cache_path()
        try:
            ensure_dir(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tables_dir": tables_dir,
                        "results": tables,
                        "cached_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception:
            pass

    def _aw_init_tables(self) -> None:
        """On startup: populate the dropdown from cache if available, else run a full scan."""
        cached = self._aw_load_cache()
        if cached is not None:
            self._aw_cmb_tables.clear()
            if cached:
                self._aw_cmb_tables.addItems(cached)
                self._aw_status_lbl.setText(f"Found {len(cached)} table(s) (cached).")
            else:
                self._aw_status_lbl.setText(
                    "No Non-ROM tables found (cached). Check Tables directory in System tab."
                )
        else:
            self._aw_scan_tables()

    # ------------------------------------------------------------------
    # Script analysis
    # ------------------------------------------------------------------

    def _aw_analyze_script(self):
        fname = self._aw_cmb_tables.currentText()
        if not fname:
            self._aw_status_lbl.setText("⚠ Please select a table first.")
            return

        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        if not tables_dir:
            self._aw_status_lbl.setText("⚠ Tables directory not configured.")
            return

        vpx_path = os.path.join(tables_dir, fname)
        if not os.path.isfile(vpx_path):
            self._aw_status_lbl.setText(f"⚠ File not found: {vpx_path}")
            return

        self._aw_btn_analyze.setEnabled(False)
        self._aw_status_lbl.setText("Analyzing script…")

        worker = _AnalyzeScriptWorker(self.cfg, vpx_path, parent=self)
        worker.finished.connect(self._aw_on_analyze_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self._aw_analyze_worker = worker

    def _aw_on_analyze_done(self, findings: list):
        # Clear previous
        while self._aw_detected_vbox.count():
            item = self._aw_detected_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._aw_detected_rows.clear()

        if not findings:
            lbl = QLabel("<i style='color:#666;'>No common events detected in the script.</i>")
            self._aw_detected_vbox.addWidget(lbl)
            self._aw_status_lbl.setText("Analysis complete. No known events found.")
        else:
            for title, sub_name, lineno, event_name, default_checked in findings:
                row_w = QWidget()
                row_w.setStyleSheet("background:transparent;")
                row_h = QHBoxLayout(row_w)
                row_h.setContentsMargins(4, 2, 4, 2)

                chk = QCheckBox()
                chk.setChecked(default_checked)
                chk.setStyleSheet("QCheckBox { color:#E0E0E0; }")
                chk.setToolTip("Check to include this event as an achievement trigger")
                row_h.addWidget(chk)

                lbl = QLabel(
                    f"<span style='color:#E0E0E0; font-weight:bold;'>{title}</span>"
                    f"<span style='color:#888;'> → Sub {sub_name}()</span>"
                    f"<span style='color:#555;'>  Ln {lineno}</span>"
                )
                lbl.setStyleSheet("background:transparent;")
                row_h.addWidget(lbl, stretch=1)

                self._aw_detected_vbox.addWidget(row_w)
                self._aw_detected_rows.append({
                    "chk": chk,
                    "title": title,
                    "sub": sub_name,
                    "lineno": lineno,
                    "event": event_name,
                })

            self._aw_status_lbl.setText(f"Found {len(findings)} event(s).")

        self._aw_btn_analyze.setEnabled(True)

    # ------------------------------------------------------------------
    # Custom achievement rows
    # ------------------------------------------------------------------

    def _aw_add_row(self, title: str = "", desc: str = "", event: str = ""):
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background:#1e1e1e; border:1px solid #333; border-radius:4px; }"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(6)

        lbl_t = QLabel("🏆 Title:")
        lbl_t.setStyleSheet("color:#aaa; background:transparent; border:none;")
        h.addWidget(lbl_t)

        ed_title = QLineEdit(title)
        ed_title.setPlaceholderText("e.g. Ramp Combo King")
        ed_title.setStyleSheet(self._aw_lineedit_style())
        ed_title.setToolTip("Achievement title shown in the toast notification")
        h.addWidget(ed_title, stretch=2)

        lbl_d = QLabel("📝 Desc:")
        lbl_d.setStyleSheet("color:#aaa; background:transparent; border:none;")
        h.addWidget(lbl_d)

        ed_desc = QLineEdit(desc)
        ed_desc.setPlaceholderText("e.g. Hit 5 ramps in a row")
        ed_desc.setStyleSheet(self._aw_lineedit_style())
        ed_desc.setToolTip("Short description of how to unlock this achievement")
        h.addWidget(ed_desc, stretch=2)

        lbl_e = QLabel("🎯 Event:")
        lbl_e.setStyleSheet("color:#aaa; background:transparent; border:none;")
        h.addWidget(lbl_e)

        ed_event = QLineEdit(event)
        ed_event.setPlaceholderText("e.g. ramp_combo_5x")
        ed_event.setStyleSheet(self._aw_lineedit_style())
        ed_event.setToolTip("Unique event identifier (lowercase, a-z, 0-9, underscores only)")
        ed_event.setMaximumWidth(160)
        h.addWidget(ed_event)

        # Validate event name on text change
        def _validate():
            txt = ed_event.text()
            invalid = bool(txt) and not re.fullmatch(r"[a-z0-9_]+", txt)
            ed_event.setStyleSheet(self._aw_lineedit_style(invalid))

        ed_event.textChanged.connect(_validate)

        btn_rm = QPushButton("🗑️")
        btn_rm.setFixedSize(30, 26)
        btn_rm.setToolTip("Remove this achievement")
        btn_rm.setStyleSheet(
            "QPushButton { background:#3a1a1a; color:#cc3333; border:1px solid #cc3333;"
            " border-radius:4px; font-size:10pt; }"
            "QPushButton:hover { background:#cc3333; color:#fff; }"
        )

        row_dict = {"title": ed_title, "desc": ed_desc, "event": ed_event, "frame": frame}
        self._aw_custom_rows.append(row_dict)

        def _remove():
            self._aw_rows_vbox.removeWidget(frame)
            frame.deleteLater()
            if row_dict in self._aw_custom_rows:
                self._aw_custom_rows.remove(row_dict)

        btn_rm.clicked.connect(_remove)
        h.addWidget(btn_rm)

        self._aw_rows_vbox.addWidget(frame)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _aw_export(self):
        fname = self._aw_cmb_tables.currentText()
        if not fname:
            self._aw_status_lbl.setText("⚠ No table selected.")
            return

        table_stem = os.path.splitext(fname)[0]  # e.g. "JP_JurassicPark_VPW"

        # Collect detected events that are checked
        rules: list[dict] = []
        for row in self._aw_detected_rows:
            if row["chk"].isChecked():
                rules.append({
                    "title":       row["title"] + "!",
                    "description": f"Trigger: {row['sub']}()",
                    "condition":   {"type": "event", "event": row["event"]},
                })

        # Collect custom achievement rows
        for row in self._aw_custom_rows:
            t  = row["title"].text().strip()
            d  = row["desc"].text().strip()
            ev = row["event"].text().strip()
            if not t or not ev:
                continue
            if not re.fullmatch(r"[a-z0-9_]+", ev):
                self._aw_status_lbl.setText(f"⚠ Invalid event name: '{ev}' – use only a-z, 0-9, _")
                return
            rules.append({
                "title":       t,
                "description": d,
                "condition":   {"type": "event", "event": ev},
            })

        if not rules:
            self._aw_status_lbl.setText("⚠ No achievements selected. Add or check some first.")
            return

        out_dir = p_aweditor(self.cfg)
        ensure_dir(out_dir)
        ensure_dir(p_custom_events(self.cfg))

        # ── Write JSON ────────────────────────────────────────────────
        json_name = f"{table_stem}.custom.json"
        json_path = os.path.join(out_dir, json_name)
        payload = {
            "table_file": fname,
            "rules": rules,
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not write JSON: {e}")
            return

        # ── Write VBS ─────────────────────────────────────────────────
        vbs_name = f"aw_{table_stem}.vbs"
        vbs_path = os.path.join(out_dir, vbs_name)

        # VBScript path needs backslashes and trailing backslash
        events_path_vbs = p_custom_events(self.cfg).replace("/", "\\").rstrip("\\") + "\\"

        # Build comment lines for detected events
        detected_lines: list[str] = []
        for row in self._aw_detected_rows:
            if row["chk"].isChecked():
                detected_lines.append(
                    f'\'   FireAchievement "{row["event"]}"'
                    f'        → Add to Sub {row["sub"]}()'
                    f'    Line {row["lineno"]}'
                )

        # Build comment lines for custom events
        custom_lines: list[str] = []
        for row in self._aw_custom_rows:
            ev = row["event"].text().strip()
            t  = row["title"].text().strip()
            if ev and re.fullmatch(r"[a-z0-9_]+", ev):
                custom_lines.append(
                    f'\'   FireAchievement "{ev}"'
                    f'    → Your custom event ({t})'
                )

        detected_block = "\n".join(detected_lines) if detected_lines else "\'   (none selected)"
        custom_block   = "\n".join(custom_lines)   if custom_lines   else "\'   (none defined)"

        vbs_content = f"""\
' ═══════════════════════════════════════════════════════════════════
'   VPX Achievement Watcher – Custom Achievement Triggers
'   Table: {fname}
'   Generated by AWEditor
'
'   INSTALLATION:
'   1. Copy this file next to your .vpx table file
'   2. Open the table in VPX Editor (File > Open)
'   3. Open Script Editor (View > Script or F12)
'   4. Add this line near the top of your table script:
'        LoadScript "aw_{table_stem}.vbs"
'   5. For custom achievements, add FireAchievement calls
'      at the appropriate places (see comments below)
'
'   ⚠️  IMPORTANT: Do NOT rename this file to {table_stem}.vbs !
'   If the .vbs has the same base name as the .vpx, VPX will
'   REPLACE the entire table script and completely break the table.
'   The "aw_" prefix keeps this file additive (loaded via LoadScript).
' ═══════════════════════════════════════════════════════════════════

Dim AW_EventPath
AW_EventPath = "{events_path_vbs}"

Sub FireAchievement(eventName)
    On Error Resume Next
    Dim fso, f
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set f = fso.CreateTextFile(AW_EventPath & eventName & ".trigger", True)
    f.WriteLine eventName
    f.WriteLine Now
    f.Close
    Set f = Nothing
    Set fso = Nothing
    On Error Goto 0
End Sub

' ── Auto-Detected Events ─────────────────────────────────────────
' These are called when specific Subs in your table execute.
' The FireAchievement calls below need to be placed inside the
' corresponding Subs in your table script.
'
{detected_block}

' ── Custom Events ─────────────────────────────────────────────────
' Place these calls where the event happens in your table script:
'
{custom_block}
"""

        try:
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(vbs_content)
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not write VBS: {e}")
            return

        rel_out = os.path.relpath(out_dir, self.cfg.BASE) if hasattr(self.cfg, "BASE") else out_dir
        self._aw_status_lbl.setText(
            f"✅ Exported {vbs_name} + {json_name} → {rel_out}"
        )
