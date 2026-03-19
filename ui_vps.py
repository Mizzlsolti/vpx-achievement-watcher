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

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QFont, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QWidget, QFrame, QSizePolicy, QProgressDialog, QApplication,
    QMessageBox,
)

VPSDB_URL = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/main/db/vpsdb.json"
VPS_IMG_BASE_URL = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/main/img/"
VPSDB_TTL = 24 * 3600  # 24 hours in seconds
MAX_PICKER_RESULTS = 80  # Maximum entries shown in VpsPickerDialog

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
                print(f"[VpsImageLoader] invalid filename extracted from img_url: {img_url!r}")
                return
            cache_dir = p_vps_img(self.cfg)
            cache_path = os.path.join(cache_dir, filename)

            if os.path.isfile(cache_path):
                with open(cache_path, "rb") as f:
                    data = f.read()
            else:
                full_url = VPS_IMG_BASE_URL + filename
                print(f"[VpsImageLoader] downloading {full_url}")
                try:
                    req = urllib.request.Request(full_url, headers={"User-Agent": "vpx-achievement-watcher"})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = resp.read()
                except Exception as dl_err:
                    print(f"[VpsImageLoader] download error for {img_url}: {dl_err}")
                    return
                ensure_dir(cache_dir)
                with open(cache_path, "wb") as f:
                    f.write(data)

            # --- Try Qt native decode first ---
            pixmap = QPixmap()
            if pixmap.loadFromData(data) and not pixmap.isNull():
                print(f"[VpsImageLoader] loaded {img_url} via Qt native")
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
                    print(f"[VpsImageLoader] loaded {img_url} via Pillow+PNG fallback")
                    self.image_ready.emit(img_url, pixmap2)
                    return
                else:
                    print(f"[VpsImageLoader] Pillow converted but QPixmap still null for {img_url}")
            except ImportError:
                print(f"[VpsImageLoader] Pillow not installed – cannot decode {img_url} (install Pillow: pip install Pillow)")
            except Exception as pil_err:
                print(f"[VpsImageLoader] Pillow decode error for {img_url}: {pil_err}")

        except Exception as e:
            print(f"[VpsImageLoader] unexpected error for {img_url}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# VPS table entry widget for the list
# ─────────────────────────────────────────────────────────────────────────────

class _TableEntryWidget(QWidget):
    """Custom widget showing image + table info for VpsPickerDialog list."""

    def __init__(self, table: dict, rom_match: bool, parent=None):
        super().__init__(parent)
        self.table = table
        self.img_url = table.get("imgUrl", "")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        if rom_match:
            marker = QFrame()
            marker.setFixedWidth(3)
            marker.setStyleSheet("background: #00E5FF;")
            layout.addWidget(marker, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.img_label = QLabel("🎰")
        self.img_label.setFixedSize(100, 100)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background:#1a1a1a; border:1px solid #444; font-size:28px;")
        layout.addWidget(self.img_label, alignment=Qt.AlignmentFlag.AlignTop)

        info = QWidget()
        info_lay = QVBoxLayout(info)
        info_lay.setContentsMargins(8, 0, 0, 0)
        info_lay.setSpacing(2)

        # Line 1: Name + ROM-Match badge
        name_row = QHBoxLayout()
        raw_name = table.get('name', 'Unknown')
        name = re.sub(r'\s*\(.*\)', '', raw_name)
        name = re.sub(r'\s*\[.*\]', '', name).strip()
        lbl_name = QLabel(f"<b>{name}</b>")
        lbl_name.setStyleSheet("color:#FFFFFF; font-size:13px; padding-bottom:2px;")
        lbl_name.setWordWrap(True)
        name_row.addWidget(lbl_name)

        if rom_match:
            lbl_badge = QLabel("✅ ROM-Match")
            lbl_badge.setStyleSheet("color:#00E5FF; background:#003333; border:1px solid #00E5FF; padding:2px 5px; font-size:10px; border-radius:3px;")
            name_row.addWidget(lbl_badge)
        name_row.addStretch()
        info_lay.addLayout(name_row)

        # Line 2: Manufacturer · Year · Type
        mfr = table.get("manufacturer", "")
        year = str(table.get("year", "")) if table.get("year") else ""
        ttype = table.get("type", "")
        sub_parts = [p for p in [mfr, year, ttype] if p]
        lbl_sub = QLabel(" · ".join(sub_parts))
        lbl_sub.setStyleSheet("color:#999; font-size:11px;")
        info_lay.addWidget(lbl_sub)

        # Line 3: Theme | Designers
        theme = ", ".join(table.get("theme") or [])
        designers = ", ".join(table.get("designers") or [])
        line3_parts = []
        if theme:
            line3_parts.append(f"Theme: {theme}")
        if designers:
            line3_parts.append(f"Designers: {designers}")
        if line3_parts:
            lbl_line3 = QLabel("  |  ".join(line3_parts))
            lbl_line3.setStyleSheet("color:#888; font-size:10px;")
            lbl_line3.setWordWrap(True)
            info_lay.addWidget(lbl_line3)

        # Line 4: ROM names (flattened from romFiles entries)
        all_roms: list = []
        for rg in (table.get("romFiles") or []):
            for rf in (rg.get("romFiles") or []):
                if isinstance(rf, str) and rf not in all_roms:
                    all_roms.append(rf)
        if all_roms:
            roms_text = ", ".join(all_roms[:8])
            if len(all_roms) > 8:
                roms_text += f", … (+{len(all_roms) - 8})"
            lbl_roms = QLabel(f"ROMs: {roms_text}")
            lbl_roms.setStyleSheet("color:#7AC; font-size:10px;")
            info_lay.addWidget(lbl_roms)

        # Line 5: Table file count + players (tableFiles only, no B2S/ROM groups)
        table_files = table.get("tableFiles") or []
        n_tables = len(table_files)
        players = table.get("players", "")
        count_parts = []
        if n_tables:
            count_parts.append(f"{n_tables} table file{'s' if n_tables != 1 else ''}")
        if players:
            count_parts.append(f"{players}p")
        if count_parts:
            lbl_counts = QLabel("Files: " + ", ".join(count_parts))
            lbl_counts.setStyleSheet("color:#666; font-size:10px;")
            info_lay.addWidget(lbl_counts)

        # Table Authors (from tableFiles[].authors)
        seen_authors: list[str] = []
        for tf in table_files:
            for a in (tf.get("authors") or []):
                if a and a not in seen_authors:
                    seen_authors.append(a)
        if seen_authors:
            MAX_AUTHORS = 6
            authors_display = ", ".join(seen_authors[:MAX_AUTHORS])
            if len(seen_authors) > MAX_AUTHORS:
                authors_display += f" +{len(seen_authors) - MAX_AUTHORS} more"
            lbl_authors = QLabel(f"Table Authors: {authors_display}")
            lbl_authors.setStyleSheet("color:#CCA; font-size:10px;")
            lbl_authors.setWordWrap(True)
            info_lay.addWidget(lbl_authors)

        # Table Versions (from tableFiles[].version)
        seen_versions: list[str] = []
        for tf in table_files:
            v = tf.get("version", "")
            if v and v not in seen_versions:
                seen_versions.append(v)
        if seen_versions:
            MAX_VERSIONS = 6
            versions_display = ", ".join(seen_versions[:MAX_VERSIONS])
            if len(seen_versions) > MAX_VERSIONS:
                versions_display += f" +{len(seen_versions) - MAX_VERSIONS} more"
            lbl_versions = QLabel(f"Versions: {versions_display}")
            lbl_versions.setStyleSheet("color:#CCA; font-size:10px;")
            info_lay.addWidget(lbl_versions)

        # Latest Update (most recent updatedAt across all tableFiles)
        latest_ts = max(
            (tf.get("updatedAt") for tf in table_files if isinstance(tf.get("updatedAt"), (int, float))),
            default=None,
        )
        if latest_ts is not None:
            from datetime import datetime, timezone
            try:
                dt = datetime.fromtimestamp(latest_ts / 1000, tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                date_str = str(latest_ts)
            lbl_updated = QLabel(f"Last Updated: {date_str}")
            lbl_updated.setStyleSheet("color:#888; font-size:10px;")
            info_lay.addWidget(lbl_updated)

        # Download Sources (total URL count across all tableFiles[].urls[])
        total_urls = 0
        for tf in table_files:
            total_urls += len(tf.get("urls") or [])
        if total_urls:
            lbl_dl = QLabel(f"Downloads: {total_urls} source{'s' if total_urls != 1 else ''} available")
            lbl_dl.setStyleSheet("color:#888; font-size:10px;")
            info_lay.addWidget(lbl_dl)

        # Line 6: ID + optional IPDB link
        table_id = table.get("id", "")
        ipdb_url = table.get("IPDBUrl", "")
        id_html_parts = []
        if table_id:
            id_html_parts.append(f"ID: {table_id}")
        if ipdb_url:
            id_html_parts.append(f'<a href="{ipdb_url}" style="color:#FF7F00;">IPDB</a>')
        if id_html_parts:
            lbl_id = QLabel("  |  ".join(id_html_parts))
            lbl_id.setStyleSheet("color:#888; font-size:10px;")
            lbl_id.setOpenExternalLinks(True)
            info_lay.addWidget(lbl_id)

        info_lay.addStretch()
        layout.addWidget(info, stretch=1)

    def set_image(self, pixmap: QPixmap):
        scaled = pixmap.scaled(
            self.img_label.width(), self.img_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.img_label.setPixmap(scaled)
        self.img_label.setText("")


# ─────────────────────────────────────────────────────────────────────────────
# VPS Picker Dialog
# ─────────────────────────────────────────────────────────────────────────────

class VpsPickerDialog(QDialog):
    """Visual VPS table picker with lazy-loaded images and search."""

    def __init__(self, cfg, tables: List[dict], rom: str, table_title: str, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.tables = tables
        self.rom = rom
        self.table_title = table_title
        self.selected_table: Optional[dict] = None
        self._image_cache: Dict[str, QPixmap] = {}
        self._loaders: List[VpsImageLoader] = []
        self._entry_widgets: Dict[int, _TableEntryWidget] = {}  # list row -> widget

        self.setWindowTitle(f"Select VPS Table — {table_title} [{rom}]")
        self.setMinimumSize(680, 600)
        self.setStyleSheet("background:#111; color:#DDD;")

        layout = QVBoxLayout(self)

        # Search field
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Search table name...")
        self.txt_search.setStyleSheet("background:#1a1a1a; color:#DDD; border:1px solid #555; padding:4px;")
        self.txt_search.textChanged.connect(self._on_search)
        layout.addWidget(self.txt_search)

        # Results list
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget {background:#111; border:1px solid #333;} "
            "QListWidget::item:selected {background:#003D00;} "
            "QListWidget::item:hover {background:#1a1a1a;}"
        )
        self.list_widget.setSpacing(2)
        self.list_widget.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.list_widget)

        # Buttons
        btn_row = QHBoxLayout()
        btn_remove = QPushButton("❌ Remove Assignment")
        btn_remove.setStyleSheet("background:#3D0000; color:#FF3B30; border:1px solid #FF3B30;")
        btn_remove.clicked.connect(self._remove_assignment)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background:#222; color:#AAA;")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("✅ Select")
        btn_ok.setStyleSheet("background:#003D00; color:#00E5FF; font-weight:bold; border:1px solid #00E5FF;")
        btn_ok.clicked.connect(self._accept_selection)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        # Pre-fill search and populate list
        self.txt_search.setText(table_title)
        self._populate_list(table_title)

    def _populate_list(self, search_term: str):
        self.list_widget.clear()
        self._entry_widgets.clear()
        self._stop_loaders()

        results = _vps_find(self.tables, search_term, self.rom)
        if not results:
            results = self.tables[:50]  # fallback: show first 50

        for idx, table in enumerate(results[:MAX_PICKER_RESULTS]):
            rom_match = _table_has_rom(table, self.rom)
            entry_widget = _TableEntryWidget(table, rom_match)
            item = QListWidgetItem()
            item.setSizeHint(QSize(400, 110))
            item.setData(Qt.ItemDataRole.UserRole, table)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, entry_widget)
            self._entry_widgets[idx] = entry_widget

            # Start lazy image load
            img_url = table.get("imgUrl", "")
            if img_url:
                if img_url in self._image_cache:
                    entry_widget.set_image(self._image_cache[img_url])
                else:
                    loader = VpsImageLoader(self.cfg, img_url, self)
                    loader.image_ready.connect(self._on_image_ready)
                    self._loaders.append(loader)
                    loader.start()

    def _on_search(self, text: str):
        self._populate_list(text)

    def _on_image_ready(self, url: str, pixmap: QPixmap):
        self._image_cache[url] = pixmap
        for idx, widget in self._entry_widgets.items():
            if widget.img_url == url:
                widget.set_image(pixmap)

    def _accept_selection(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        self.selected_table = items[0].data(Qt.ItemDataRole.UserRole)
        self._stop_loaders()
        self.accept()

    def _remove_assignment(self):
        self.selected_table = None
        self._stop_loaders()
        self.done(2)  # special code for "remove"

    def _stop_loaders(self):
        for loader in self._loaders:
            try:
                loader.image_ready.disconnect()
                loader.quit()
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
