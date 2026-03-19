"""VPS (Virtual Pinball Spreadsheet) integration: picker dialog, image loader, search logic."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Any, List

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

VPSDB_URL = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/main/db/vpsdb.json"
VPSDB_TTL = 24 * 3600  # 24 hours in seconds
MAX_PICKER_RESULTS = 100  # Maximum entries shown in VpsPickerDialog

# ─────────────────────────────────────────────────────────────────────────────
# VPS-DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_vpsdb(cfg) -> Optional[List[dict]]:
    """Load vpsdb.json, using a local cache with 24-hour TTL."""
    from watcher_core import f_vpsdb_cache, ensure_dir
    cache_path = f_vpsdb_cache(cfg)
    try:
        if os.path.isfile(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < VPSDB_TTL:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
    except Exception:
        pass  # fall through to download

    # Download fresh copy
    try:
        req = urllib.request.Request(VPSDB_URL, headers={"User-Agent": "vpx-achievement-watcher"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        ensure_dir(os.path.dirname(cache_path))
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(raw)
        return data
    except Exception:
        # Try stale cache as fallback
        try:
            if os.path.isfile(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return None


def _load_vps_mapping(cfg) -> dict:
    """Load vps_id_mapping.json, returning {} on error."""
    from watcher_core import f_vps_mapping
    path = f_vps_mapping(cfg)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_vps_mapping(cfg, mapping: dict):
    """Save vps_id_mapping.json."""
    from watcher_core import f_vps_mapping, ensure_dir
    path = f_vps_mapping(cfg)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)


def _normalize_term(term: str) -> str:
    """Normalize a search term the same way VPin Studio does."""
    term = re.sub(r"[_'\-\.]+", " ", term)
    term = re.sub(r"\bThe\s+", "", term, flags=re.IGNORECASE)
    term = re.sub(r",\s*The\b", "", term, flags=re.IGNORECASE)
    if "(" in term:
        term = term[:term.index("(")]
    return term.lower().strip()


def _find_internal(tables: List[dict], term: str) -> List[dict]:
    results = []
    for table in tables:
        name = _normalize_term(table.get("name", ""))
        if term in name:
            results.append(table)
    return results


def _vps_find(tables: List[dict], search_term: str, rom: Optional[str] = None) -> List[dict]:
    """Search VPS DB tables using the same logic as VPin Studio's VPS.find()."""
    if not tables:
        return []

    # 1. Try direct ROM match first
    if rom:
        rom_lower = rom.lower()
        for table in tables:
            for rom_group in (table.get("romFiles") or []):
                for rf in (rom_group.get("romFiles") or []):
                    if isinstance(rf, str) and rf.lower() == rom_lower:
                        return [table]

    # 2. Name-based search with progressive shortening fallback
    term = _normalize_term(search_term)
    results = _find_internal(tables, term)
    while not results and " " in term:
        term = term[:term.rfind(" ")].strip()
        results = _find_internal(tables, term)

    # 3. If still no results, try using the ROM identifier prefix as a name search
    #    (e.g., "acd_170h" → "acd") to handle tables missing ROM file listings
    if not results and rom:
        prefix = re.split(r"[_\d]+", rom.lower())[0].strip()
        if len(prefix) >= 3:
            results = _find_internal(tables, prefix)

    # Sort ROM-matching entries first
    if rom and results:
        rom_lower = rom.lower()
        def _has_rom(t):
            for rg in (t.get("romFiles") or []):
                for rf in (rg.get("romFiles") or []):
                    if isinstance(rf, str) and rf.lower() == rom_lower:
                        return True
            return False
        rom_matches = [t for t in results if _has_rom(t)]
        others = [t for t in results if not _has_rom(t)]
        results = rom_matches + others

    return results


def _table_has_rom(table: dict, rom: str) -> bool:
    """Return True if this VPS table entry contains the given ROM identifier."""
    rom_lower = rom.lower()
    for rg in (table.get("romFiles") or []):
        for rf in (rg.get("romFiles") or []):
            if isinstance(rf, str) and rf.lower() == rom_lower:
                return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Image download worker
# ─────────────────────────────────────────────────────────────────────────────

class _ImgFetcher(QThread):
    ready = pyqtSignal(str, QPixmap)  # vps_id, pixmap

    VPS_IMG_BASE = (
        "https://raw.githubusercontent.com/"
        "VirtualPinballSpreadsheet/vps-db/main/img/"
    )
    LOCAL_CACHE = Path("tools/vps/img")

    def __init__(self, vps_id: str, img_filename: str, parent=None):
        super().__init__(parent)
        self.vps_id = vps_id
        self.img_filename = img_filename

    def run(self):
        self.LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
        local = self.LOCAL_CACHE / self.img_filename
        if not local.exists():
            url = self.VPS_IMG_BASE + self.img_filename
            try:
                urllib.request.urlretrieve(url, local)
            except Exception:
                return
        pix = QPixmap(str(local))
        if not pix.isNull():
            pix = pix.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
            self.ready.emit(self.vps_id, pix)


# ─────────────────────────────────────────────────────────────────────────────
# VPS Picker Dialog — 2-column table view
# ─────────────────────────────────────────────────────────────────────────────

class VpsPickerDialog(QDialog):
    """2-column table VPS picker with per-version selection."""

    def __init__(self, cfg, tables: List[dict], rom: str, table_title: str, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.tables = tables
        self.rom = rom
        self.table_title = table_title
        self.selected_table: Optional[dict] = None
        self.selected_table_file: Optional[dict] = None
        self._row_data: List[tuple] = []  # (table, table_file) per row

        self.setWindowTitle(f"Select VPS Table — {table_title} [{rom}]")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)
        self.setStyleSheet("background:#1a1a1a; color:#DDD;")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Header ───────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        lbl_hdr = QLabel("Tables 🛈")
        lbl_hdr.setStyleSheet("color:#FFFFFF; font-size:18px; font-weight:bold;")
        hdr.addWidget(lbl_hdr)
        hdr.addStretch()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Search table name…")
        self.txt_search.setFixedWidth(320)
        self.txt_search.setStyleSheet(
            "background:#2a2a2a; color:#DDD; border:1px solid #555;"
            " border-radius:4px; padding:5px 8px; font-size:13px;"
        )
        self.txt_search.textChanged.connect(self._on_search)
        hdr.addWidget(self.txt_search)
        root.addLayout(hdr)

        # ── Table widget ──────────────────────────────────────────────────────
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)
        self.table_widget.setHorizontalHeaderLabels(["Table / Type / Features", "Authors · Version · Date"])
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setShowGrid(True)
        self.table_widget.verticalHeader().setVisible(False)
        # Both columns get equal stretch (50/50)
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_widget.setStyleSheet(
            "QTableWidget {"
            "  background:#1a1a1a; color:#DDD; gridline-color:#333;"
            "  border:none; font-size:12px; outline:0;"
            "}"
            "QTableWidget::item { padding:6px 8px; }"
            "QTableWidget::item:selected {"
            "  background:#003344; color:#00E5FF;"
            "  border-left:2px solid #00E5FF;"
            "}"
            "QTableWidget::item:hover { background:#2e2e2e; }"
            "QHeaderView::section {"
            "  background:#2a2a2a; color:#888; border:none;"
            "  padding:4px 8px; font-size:11px;"
            "}"
            "QScrollBar:vertical { background:#222; width:10px; }"
            "QScrollBar::handle:vertical { background:#555; border-radius:5px; }"
        )
        self.table_widget.itemSelectionChanged.connect(self._on_row_selected)
        self.table_widget.cellDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.table_widget, stretch=1)

        # ── Footer buttons ────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#333;")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_remove = QPushButton("❌ Remove Assignment")
        btn_remove.setStyleSheet(
            "background:#3D0000; color:#FF3B30; border:1px solid #FF3B30;"
            " padding:6px 14px; border-radius:4px;"
        )
        btn_remove.clicked.connect(self._remove_assignment)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(
            "background:#2a2a2a; color:#AAA; border:1px solid #555;"
            " padding:6px 14px; border-radius:4px;"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("✅ Select")
        btn_ok.setStyleSheet(
            "background:#003D00; color:#00E5FF; font-weight:bold;"
            " border:1px solid #00E5FF; padding:6px 14px; border-radius:4px;"
        )
        btn_ok.clicked.connect(self._accept_selection)
        btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

        # Pre-fill search with clean table name and populate table
        clean_title = self._clean_table_title(table_title)
        self.txt_search.setText(clean_title)
        self._populate_table(clean_title)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _clean_table_title(title: str) -> str:
        """Strip brackets, parentheses and extra info — keep only the table name."""
        name = re.sub(r'\s*\[.*?\]', '', title)
        name = re.sub(r'\s*\(.*?\)', '', name)
        return name.strip()

    # ── Table management ──────────────────────────────────────────────────────

    def _populate_table(self, search_term: str):
        self.table_widget.setRowCount(0)
        self._row_data.clear()
        self.selected_table = None
        self.selected_table_file = None

        results = _vps_find(self.tables, search_term, self.rom)
        if not results:
            results = self.tables[:50]

        # Flatten: one row per tableFile entry
        entries: List[tuple] = []
        for table in results:
            rom_match = _table_has_rom(table, self.rom)
            table_files = table.get("tableFiles") or []
            if table_files:
                for tf in table_files:
                    entries.append((table, tf, rom_match))
                    if len(entries) >= MAX_PICKER_RESULTS:
                        break
            else:
                entries.append((table, {}, rom_match))
            if len(entries) >= MAX_PICKER_RESULTS:
                break

        self.table_widget.setRowCount(len(entries))
        for row, (table, table_file, rom_match) in enumerate(entries):
            # ── Column 0: name + type + features + table-id + file-id ─────────
            raw_name = table.get("name", "Unknown")
            name = re.sub(r'\s*\(.*?\)', '', raw_name)
            name = re.sub(r'\s*\[.*?\]', '', name).strip()

            ttype = table.get("type", "")
            features = [f.upper() for f in (table_file.get("features") or []) if isinstance(f, str)]
            vps_id = table.get("id", "")          # table-level VPS ID
            tf_id = table_file.get("id", "")      # tableFile-level ID

            parts = [name]
            if ttype:
                parts.append(f"[{ttype}]")
            if features:
                parts.append("  " + "  ".join(features[:8]))
            # Show table VPS ID
            if vps_id:
                parts.append(f"  [{vps_id}]")
            # Show tableFile ID only if different from table ID
            if tf_id and tf_id != vps_id:
                parts.append(f"  [{tf_id}]")
            col0_text = "  ".join(parts)

            item0 = QTableWidgetItem(col0_text)
            # Left-align text in column 0
            item0.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item0.setToolTip(raw_name)
            self.table_widget.setItem(row, 0, item0)

            # ── Column 1: authors + version/id + date + ROM match ─────────────
            authors = table_file.get("authors") or []
            authors_text = ", ".join(authors[:4])
            if len(authors) > 4:
                authors_text += "…"

            tf_ver = table_file.get("version", "")
            id_text = tf_ver or tf_id or ""

            date_str = ""
            ts = table_file.get("updatedAt")
            if isinstance(ts, (int, float)) and ts > 0:
                try:
                    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                    date_str = dt.strftime("%d.%m.%Y")
                except Exception:
                    pass

            col1_parts = []
            if authors_text:
                col1_parts.append(authors_text)
            if id_text:
                col1_parts.append(id_text)
            if date_str:
                col1_parts.append(date_str)
            if rom_match:
                col1_parts.append("✅")
            col1_text = "  ·  ".join(col1_parts)

            item1 = QTableWidgetItem(col1_text)
            item1.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.table_widget.setItem(row, 1, item1)

            self._row_data.append((table, table_file))

        self.table_widget.resizeRowsToContents()

    def _on_search(self, text: str):
        self._populate_table(text)

    def _on_row_selected(self):
        rows = self.table_widget.selectedItems()
        if not rows:
            return
        row = self.table_widget.currentRow()
        if 0 <= row < len(self._row_data):
            self.selected_table, self.selected_table_file = self._row_data[row]

    def _on_double_click(self, row: int, _col: int):
        if 0 <= row < len(self._row_data):
            self.selected_table, self.selected_table_file = self._row_data[row]
            self._accept_selection()

    def _accept_selection(self):
        if not self.selected_table:
            return
        self.accept()

    def _remove_assignment(self):
        self.selected_table = None
        self.selected_table_file = None
        self.done(2)  # special code for "remove"


# ─────────────────────────────────────────────────────────────────────────────
# VPS Achievement Info Dialog
# ─────────────────────────────────────────────────────────────────────────────

class VpsAchievementInfoDialog(QDialog):
    """Show achievement details with VPS table info."""

    def __init__(self, cfg, rom: str, title: str, rule: Optional[dict], unlock_entry: Any, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(f"ℹ️  {title}")
        self.setMinimumSize(500, 320)
        self.setStyleSheet("background:#111; color:#DDD;")

        layout = QVBoxLayout(self)

        # Header
        lbl_title = QLabel(f"<b style='font-size:14px; color:#00E5FF;'>🏆 {title}</b>")
        lbl_title.setWordWrap(True)
        layout.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#333;")
        layout.addWidget(sep)

        # Info
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # VPS table info
        mapping = _load_vps_mapping(cfg)
        vps_id = mapping.get(rom)

        if vps_id:
            tables = _load_vpsdb(cfg)
            vps_entry = None
            if tables:
                for t in tables:
                    if t.get("id") == vps_id:
                        vps_entry = t
                        break

            if vps_entry:
                name = vps_entry.get("name", "")
                mfr = vps_entry.get("manufacturer", "")
                year = vps_entry.get("year", "")
                right_lay.addWidget(QLabel(f"<b style='color:#FF7F00; font-size:13px;'>{name}</b>"))
                right_lay.addWidget(QLabel(f"<span style='color:#999;'>{{mfr}} · {{year}}</span>"))
                right_lay.addWidget(QLabel(f"<span style='color:#555; font-size:10px;'>ID: {{vps_id}}</span>"))
            else:
                right_lay.addWidget(QLabel(f"<span style='color:#888;'>VPS-ID: {{vps_id}} (not in local cache)</span>"))
        else:
            lbl_no = QLabel("🎰 No VPS mapping set")
            lbl_no.setStyleSheet("color:#666;")
            right_lay.addWidget(lbl_no)
            lbl_hint = QLabel("<a href='#' style='color:#00E5FF;'>→ Assign in 'Available Maps' tab</a>")
            lbl_hint.setStyleSheet("color:#00E5FF;")
            right_lay.addWidget(lbl_hint)

        right_lay.addSpacing(8)

        # Achievement details
        if rule:
            right_lay.addWidget(QLabel(f"<b style='color:#DDD;'>ROM:</b>  <span style='color:#00E5FF;'>{rom}</span>"))
            cond = rule.get("condition", {}) or {}
            rtype = str(cond.get("type", "")).lower()
            field = cond.get("field", "")
            target = cond.get("min", "")
            if rtype:
                right_lay.addWidget(QLabel(f"<b style='color:#DDD;'>Type:</b>  <span style='color:#999;'>{rtype}</span>"))
            if field:
                right_lay.addWidget(QLabel(f"<b style='color:#DDD;'>Field:</b>  <span style='color:#999;'>{field}</span>"))
            if target:
                right_lay.addWidget(QLabel(f"<b style='color:#DDD;'>Target:</b>  <span style='color:#FF7F00;'>{target}</span>"))

        # Unlock date
        if unlock_entry is not None:
            ts = None
            if isinstance(unlock_entry, dict):
                ts = unlock_entry.get("ts")
            if ts:
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone()
                    date_str = dt.strftime("%Y-%m-%d  %H:%M")
                    right_lay.addSpacing(4)
                    right_lay.addWidget(QLabel(f"✅ <b style='color:#00E5FF;'>Unlocked on:</b>"))
                    right_lay.addWidget(QLabel(f"📅 <span style='color:#DDD;'>{date_str}</span>"))
                except Exception:
                    right_lay.addWidget(QLabel("✅ <span style='color:#00E5FF;'>Unlocked</span>"))
            else:
                right_lay.addSpacing(4)
                right_lay.addWidget(QLabel("✅ <span style='color:#00E5FF;'>Unlocked</span>"))
        else:
            right_lay.addSpacing(4)
            right_lay.addWidget(QLabel("🔒 <span style='color:#666;'>Not yet unlocked</span>"))

        right_lay.addStretch()
        layout.addWidget(right)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background:#222; color:#AAA; margin-top:8px;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)