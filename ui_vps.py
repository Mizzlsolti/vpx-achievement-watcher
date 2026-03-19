"""VPS (Virtual Pinball Spreadsheet) integration: picker dialog, image loader, search logic."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QCursor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea,
    QWidget, QFrame, QSizePolicy,
    QMessageBox, QGridLayout,
)

VPSDB_URL = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/main/db/vpsdb.json"
VPS_IMG_BASE_URL = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/main/img/"
VPSDB_TTL = 24 * 3600  # 24 hours in seconds
MAX_PICKER_RESULTS = 30  # Maximum entries shown in VpsPickerDialog

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
    term = re.sub(r"[_'\-\.]", " ", term)
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
# Background image loader
# ─────────────────────────────────────────────────────────────────────────────

class VpsImageLoader(QThread):
    """Download a VPS table image in background, cache it locally, and emit a QPixmap when done."""
    image_ready = pyqtSignal(str, QPixmap)  # (img_url key, pixmap)

    def __init__(self, cfg, img_url: str, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.img_url = img_url  # filename from vpsdb, e.g. "attack_from_mars.webp"

    def run(self):
        img_url = self.img_url
        if not img_url:
            return
        try:
            from watcher_core import p_vps_img, ensure_dir
            filename = img_url.rstrip("/").split("/")[-1]
            if not filename or ".." in filename or "/" in filename or "\\" in filename:
                return
            cache_dir = p_vps_img(self.cfg)
            cache_path = os.path.join(cache_dir, filename)

            if os.path.isfile(cache_path):
                with open(cache_path, "rb") as f:
                    data = f.read()
            else:
                full_url = VPS_IMG_BASE_URL + filename
                try:
                    req = urllib.request.Request(full_url, headers={"User-Agent": "vpx-achievement-watcher"})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = resp.read()
                except Exception:
                    return
                ensure_dir(cache_dir)
                with open(cache_path, "wb") as f:
                    f.write(data)

            # --- Try Qt native decode first ---
            pixmap = QPixmap()
            if pixmap.loadFromData(data) and not pixmap.isNull():
                self.image_ready.emit(img_url, pixmap)
                return

            # --- Fallback: Pillow → PNG → QPixmap ---
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                png_bytes = buf.read()
                pixmap2 = QPixmap()
                if pixmap2.loadFromData(png_bytes) and not pixmap2.isNull():
                    self.image_ready.emit(img_url, pixmap2)
            except Exception:
                pass

        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Feature-tag colour map (used by _VpsTableCard)
# ─────────────────────────────────────────────────────────────────────────────

_TAG_COLORS: Dict[str, str] = {
    "FASTFLIPS": "#FF4444",
    "SSF":       "#00BFFF",
    "LUT":       "#888888",
    "DOF":       "#4444FF",
    "MOD":       "#AA44FF",
    "NFOZZY":    "#FF8800",
    "FLEEP":     "#FFCC00",
    "VPU PATCH": "#00AA44",
}

_CARD_WIDTH  = 270
_CARD_HEIGHT = 320
_IMG_HEIGHT  = 160


# ─────────────────────────────────────────────────────────────────────────────
# Card widget — one card per tableFile entry
# ─────────────────────────────────────────────────────────────────────────────

class _VpsTableCard(QWidget):
    """Card widget showing a single tableFile version of a VPS table."""

    clicked       = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(self, table: dict, table_file: dict, rom_match: bool, parent=None):
        super().__init__(parent)
        self.table      = table
        self.table_file = table_file
        self.img_url    = table_file.get("imgUrl", "") or table.get("imgUrl", "")
        self._selected  = False
        self._rom_match = rom_match

        self.setFixedWidth(_CARD_WIDTH)
        self.setFixedHeight(_CARD_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("VpsCard")
        self._apply_style(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Image area ──────────────────────────────────────────────────────
        self.img_label = QLabel("🎰")
        self.img_label.setFixedSize(_CARD_WIDTH, _IMG_HEIGHT)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet(
            "background:#1a1a1a; border:none; font-size:40px; border-radius:0px;"
        )
        self.img_label.setScaledContents(False)
        outer.addWidget(self.img_label)

        # ── Text content area ────────────────────────────────────────────────
        content = QWidget()
        content.setObjectName("cardContent")
        content.setStyleSheet(
            "QWidget#cardContent { background: transparent; }"
        )
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(10, 8, 10, 8)
        content_lay.setSpacing(4)
        content.setFixedHeight(_CARD_HEIGHT - _IMG_HEIGHT)

        # Table name (bold, white, 14 px) — strip manufacturer/version info in parentheses/brackets
        raw_name = table.get("name", "Unknown")
        name = re.sub(r'\s*\(.*?\)', '', raw_name)
        name = re.sub(r'\s*\[.*?\]', '', name).strip()
        lbl_name = QLabel(name)
        lbl_name.setWordWrap(True)
        lbl_name.setStyleSheet("color:#FFFFFF; font-size:13px; font-weight:bold;")
        lbl_name.setMaximumHeight(36)
        content_lay.addWidget(lbl_name)

        # Authors + type badge row
        authors_row = QHBoxLayout()
        authors_row.setSpacing(6)
        authors = table_file.get("authors") or []
        authors_text = ", ".join(authors[:4])
        if len(authors) > 4:
            authors_text += "…"
        lbl_authors = QLabel(authors_text or "—")
        lbl_authors.setStyleSheet("color:#AAAAAA; font-size:10px;")
        lbl_authors.setWordWrap(False)
        lbl_authors.setMaximumHeight(28)
        authors_row.addWidget(lbl_authors, stretch=1)

        ttype = table.get("type", "")
        if ttype:
            lbl_type = QLabel(ttype)
            lbl_type.setStyleSheet(
                "color:#FFFFFF; background:#444; border-radius:3px;"
                " padding:1px 5px; font-size:10px; font-weight:bold;"
            )
            lbl_type.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            authors_row.addWidget(lbl_type)
        content_lay.addLayout(authors_row)

        # Feature tags
        features: list = []
        for feat in (table_file.get("features") or []):
            if isinstance(feat, str):
                features.append(feat.upper())
        if features:
            tags_row = QHBoxLayout()
            tags_row.setSpacing(4)
            tags_row.setContentsMargins(0, 2, 0, 2)
            for feat in features[:8]:
                color = _TAG_COLORS.get(feat, "#666666")
                dot = QLabel(feat)
                dot.setStyleSheet(
                    f"color:#FFFFFF; background:{color}; border-radius:3px;"
                    f" padding:1px 6px; font-size:9px; font-weight:bold;"
                )
                dot.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                tags_row.addWidget(dot)
            tags_row.addStretch()
            content_lay.addLayout(tags_row)

        # ROM-match badge
        if rom_match:
            lbl_rom = QLabel("✅ ROM-Match")
            lbl_rom.setStyleSheet(
                "color:#00E5FF; background:#003333; border:1px solid #00E5FF;"
                " border-radius:3px; padding:2px 6px; font-size:10px;"
            )
            lbl_rom.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            content_lay.addWidget(lbl_rom)

        # Bottom row: version ID + date
        bottom_row = QHBoxLayout()
        tf_id  = table_file.get("id", "")
        tf_ver = table_file.get("version", "")
        id_text = tf_id or tf_ver or ""
        lbl_id = QLabel(id_text)
        lbl_id.setStyleSheet("color:#666; font-size:10px; font-family:monospace;")
        bottom_row.addWidget(lbl_id, stretch=1)

        ts = table_file.get("updatedAt")
        if isinstance(ts, (int, float)) and ts > 0:
            from datetime import datetime, timezone
            try:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                date_str = dt.strftime("%d.%m.%Y")
            except Exception:
                date_str = ""
            if date_str:
                lbl_date = QLabel(date_str)
                lbl_date.setStyleSheet("color:#666; font-size:10px;")
                lbl_date.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                bottom_row.addWidget(lbl_date)

        content_lay.addLayout(bottom_row)
        content_lay.addStretch()
        outer.addWidget(content, stretch=1)

    # ── Style helpers ────────────────────────────────────────────────────────

    def _apply_style(self, hovered: bool):
        if self._selected:
            border_color = "#00E5FF"
            border_width = 2
        elif self._rom_match:
            border_color = "#00E5FF"
            border_width = 1
        elif hovered:
            border_color = "#888888"
            border_width = 1
        else:
            border_color = "#444444"
            border_width = 1
        self.setStyleSheet(
            f"QWidget#VpsCard {{"
            f" background: #2a2a2a;"
            f" border: {border_width}px solid {border_color};"
            f" border-radius: 8px;"
            f"}}"
        )

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style(False)

    def set_image(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            _CARD_WIDTH, _IMG_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.img_label.setPixmap(scaled)
        self.img_label.setText("")

    # ── Event overrides ──────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event):
        if not self._selected:
            self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._selected:
            self._apply_style(False)
        super().leaveEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# VPS Picker Dialog — card-grid view
# ─────────────────────────────────────────────────────────────────────────────

class VpsPickerDialog(QDialog):
    """Card-grid VPS table picker with per-version selection and lazy-loaded images."""

    _GRID_COLS = 3

    def __init__(self, cfg, tables: List[dict], rom: str, table_title: str, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.tables = tables
        self.rom = rom
        self.table_title = table_title
        self.selected_table: Optional[dict] = None
        self.selected_table_file: Optional[dict] = None
        self._image_cache: Dict[str, QPixmap] = {}
        self._loaders: List[VpsImageLoader] = []
        self._cards: List[_VpsTableCard] = []
        self._selected_card: Optional[_VpsTableCard] = None

        self.setWindowTitle(f"Select VPS Table — {table_title} [{rom}]")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 820)
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

        # ── Scroll area with card grid ────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            "QScrollArea { border: none; background: #1a1a1a; }"
            "QScrollBar:vertical { background:#222; width:10px; }"
            "QScrollBar::handle:vertical { background:#555; border-radius:5px; }"
        )
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background:#1a1a1a;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setHorizontalSpacing(6)
        self.grid_layout.setVerticalSpacing(6)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)
        self.scroll.setWidget(self.grid_container)
        root.addWidget(self.scroll, stretch=1)

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

        # Pre-fill search and populate grid
        self.txt_search.setText(table_title)
        self._populate_grid(table_title)

    # ── Grid management ───────────────────────────────────────────────────────

    def _clear_grid(self):
        self._stop_loaders()
        self._cards.clear()
        self._selected_card = None
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _populate_grid(self, search_term: str):
        self._clear_grid()

        results = _vps_find(self.tables, search_term, self.rom)
        if not results:
            results = self.tables[:50]

        # Flatten: one card per tableFile entry (up to MAX_PICKER_RESULTS cards total)
        card_entries: List[tuple] = []  # (table, table_file, rom_match)
        for table in results:
            rom_match = _table_has_rom(table, self.rom)
            table_files = table.get("tableFiles") or []
            if table_files:
                for tf in table_files:
                    card_entries.append((table, tf, rom_match))
                    if len(card_entries) >= MAX_PICKER_RESULTS:
                        break
            else:
                # Table with no tableFiles: show one card with empty tableFile
                card_entries.append((table, {}, rom_match))
            if len(card_entries) >= MAX_PICKER_RESULTS:
                break

        _loading_urls: set = set()
        for i, (table, table_file, rom_match) in enumerate(card_entries):
            card = _VpsTableCard(table, table_file, rom_match)
            card.clicked.connect(lambda t=table, tf=table_file, c=card: self._on_card_clicked(t, tf, c))
            card.double_clicked.connect(lambda t=table, tf=table_file, c=card: self._on_card_double_clicked(t, tf, c))
            row, col = divmod(i, self._GRID_COLS)
            self.grid_layout.addWidget(card, row, col)
            self._cards.append(card)

            # Lazy image load
            img_url = table_file.get("imgUrl", "") or table.get("imgUrl", "")
            if img_url:
                if img_url in self._image_cache:
                    card.set_image(self._image_cache[img_url])
                elif img_url not in _loading_urls:
                    _loading_urls.add(img_url)
                    loader = VpsImageLoader(self.cfg, img_url, self)
                    loader.image_ready.connect(self._on_image_ready)
                    self._loaders.append(loader)
                    loader.start()

        # Fill remaining cells in last row so grid doesn't stretch
        total = len(card_entries)
        remainder = total % self._GRID_COLS
        if remainder:
            for col in range(remainder, self._GRID_COLS):
                placeholder = QWidget()
                placeholder.setFixedWidth(_CARD_WIDTH)
                placeholder.setStyleSheet("background:transparent;")
                row = total // self._GRID_COLS
                self.grid_layout.addWidget(placeholder, row, col)

    def _on_search(self, text: str):
        self._populate_grid(text)

    def _on_image_ready(self, url: str, pixmap: QPixmap):
        self._image_cache[url] = pixmap
        for card in self._cards:
            if card.img_url == url:
                card.set_image(pixmap)

    def _on_card_clicked(self, table: dict, table_file: dict, card: _VpsTableCard):
        if self._selected_card and self._selected_card is not card:
            self._selected_card.set_selected(False)
        self._selected_card = card
        card.set_selected(True)
        self.selected_table      = table
        self.selected_table_file = table_file or None

    def _on_card_double_clicked(self, table: dict, table_file: dict, card: _VpsTableCard):
        self._on_card_clicked(table, table_file, card)
        self._accept_selection()

    def _accept_selection(self):
        if not self.selected_table:
            return
        self._stop_loaders()
        self.accept()

    def _remove_assignment(self):
        self.selected_table      = None
        self.selected_table_file = None
        self._stop_loaders()
        self.done(2)  # special code for "remove"

    def _stop_loaders(self):
        for loader in self._loaders:
            try:
                loader.image_ready.disconnect()
                loader.quit()
                loader.wait(200)
            except Exception:
                pass
        self._loaders.clear()

    def closeEvent(self, event):
        self._stop_loaders()
        super().closeEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# VPS Achievement Info Dialog
# ─────────────────────────────────────────────────────────────────────────────

class VpsAchievementInfoDialog(QDialog):
    """Show achievement details with VPS table image."""

    def __init__(self, cfg, rom: str, title: str, rule: Optional[dict], unlock_entry: Any, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._loaders: List[VpsImageLoader] = []
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

        body = QHBoxLayout()

        # Left: table image
        self.img_label = QLabel("🎰")
        self.img_label.setFixedSize(120, 120)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background:#1a1a1a; border:1px solid #444; font-size:40px; border-radius:4px;")
        body.addWidget(self.img_label, alignment=Qt.AlignmentFlag.AlignTop)

        # Right: info
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(12, 0, 0, 0)

        # VPS table info
        mapping = _load_vps_mapping(cfg)
        vps_id = mapping.get(rom)
        self._img_url = ""

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
                right_lay.addWidget(QLabel(f"<span style='color:#999;'>{mfr} · {year}</span>"))
                right_lay.addWidget(QLabel(f"<span style='color:#555; font-size:10px;'>ID: {vps_id}</span>"))
                self._img_url = vps_entry.get("imgUrl", "")
                if self._img_url:
                    loader = VpsImageLoader(self.cfg, self._img_url, self)
                    loader.image_ready.connect(self._on_image_ready)
                    self._loaders.append(loader)
                    loader.start()
            else:
                right_lay.addWidget(QLabel(f"<span style='color:#888;'>VPS-ID: {vps_id} (not in local cache)</span>"))
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
        body.addWidget(right, stretch=1)
        layout.addLayout(body)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background:#222; color:#AAA; margin-top:8px;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_image_ready(self, url: str, pixmap: QPixmap):
        scaled = pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.img_label.setPixmap(scaled)
        self.img_label.setText("")

    def closeEvent(self, event):
        for loader in self._loaders:
            try:
                loader.image_ready.disconnect()
                loader.quit()
            except Exception:
                pass
        super().closeEvent(event)
