"""VPS (Virtual Pinball Spreadsheet) integration: picker dialog, image loader, search logic."""

from __future__ import annotations

import functools
import hashlib
import json
import os
import queue
import re
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Any, List

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
from theme import tc
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QFrame, QScrollArea, QSizePolicy, QProgressBar,
)

VPSDB_URL = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/main/db/vpsdb.json"
VPSDB_TTL = 24 * 3600  # 24 hours in seconds
MAX_PICKER_RESULTS = 100  # Maximum entries shown in VpsPickerDialog

# ─────────────────────────────────────────────────────────────────────────────
# VPS feature-tag colour palette
# Colours are derived from the VPS spreadsheet visual identity and community
# conventions for each feature tag.  Where an exact upstream colour is not
# published the palette uses a stable, distinctive mapping so each tag always
# looks the same regardless of the order it appears.
# ─────────────────────────────────────────────────────────────────────────────

_VPS_FEATURE_COLORS: dict[str, tuple[str, str, str]] = {
    # tag           background  foreground  border
    "SSF":          ("#1A0000",  "#FF4040",  "#FF4040"),   # Surround Sound Feedback  – red
    "NFOZZY":       ("#1A1700",  "#F5E642",  "#C8BC00"),   # NFozzy physics           – yellow
    "HYBRID":       ("#1A0020",  "#CC55FF",  "#9900CC"),   # Hybrid physics           – purple
    "VR":           ("#000833",  "#5599FF",  "#2266DD"),   # Virtual Reality          – blue
    "FLEEP":        ("#001818",  "#00CCCC",  "#009999"),   # Fleep sounds             – teal
    "LUT":          ("#1A0D00",  "#FF9900",  "#CC6600"),   # Look-Up Table lighting   – orange
    "4K":           ("#181400",  "#FFD700",  "#AA9000"),   # 4 K rendering            – gold
    "DOF":          ("#001400",  "#44DD44",  "#228822"),   # Direct Output Framework  – green
    "FASTFLIPS":    ("#1A0000",  "#FF7777",  "#CC2222"),   # Fast Flips physics       – light red
    "FAST FLIPS":   ("#1A0000",  "#FF7777",  "#CC2222"),
    "LIGHTMAPS":    ("#00001A",  "#7799FF",  "#3355CC"),   # Lightmaps                – cornflower
    "LIGHT MAPS":   ("#00001A",  "#7799FF",  "#3355CC"),
    "MOD":          ("#0D1A00",  "#88FF44",  "#559900"),   # Modification             – lime
    "ORIGINAL":     ("#1A1A00",  "#FFEE88",  "#BBAA00"),   # Original table           – pale gold
    "FS":           ("#001A1A",  "#44FFCC",  "#008866"),   # Full Screen              – cyan-green
    "2K":           ("#101010",  "#BBBBBB",  "#666666"),   # 2 K rendering            – grey
    "B2S":          ("#0A001A",  "#BB66FF",  "#7700BB"),   # Backglass (B2S)          – violet
    "NIGHT":        ("#080010",  "#8888EE",  "#4444AA"),   # Night mode               – indigo
    "HIGHRES":      ("#001508",  "#33FF99",  "#009944"),   # High resolution          – mint
    "TOPPER":       ("#1A1000",  "#FF9944",  "#BB5500"),   # Topper support           – amber
    "POPPER":       ("#1A0A00",  "#FFAA44",  "#BB6600"),   # Popper integration       – warm orange
}

def _vps_feature_default():
    """Return the generic VPS feature color fallback using the active theme."""
    c = tc().accent_secondary
    return ("#003333", c, c)


def _vps_feature_stylesheet(tag: str) -> str:
    """Return a QLabel stylesheet string with the correct VPS colour for *tag*.

    Falls back to the generic cyan style when the tag is not in the palette.
    """
    key = tag.upper().strip()
    bg, fg, border = _VPS_FEATURE_COLORS.get(key, _vps_feature_default())
    return (
        f"QLabel {{ background:{bg}; color:{fg}; font-size:9px;"
        f" border:1px solid {border}; border-radius:3px; padding:1px 4px; }}"
    )


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


def _extract_manufacturer_year(term: str):
    """Extract manufacturer and year from a table_name like 'Attack from Mars (Bally 1995)'.

    Returns (manufacturer_lower, year_str) or (None, None) if the parenthetical
    does not look like 'Manufacturer Year'.  Parentheticals that look like ROM
    version strings (e.g. '1.13b / S1.1') are ignored.
    """
    m = re.search(r"\(([^)]+)\)\s*$", term)
    if not m:
        return None, None
    content = m.group(1).strip()
    year_m = re.search(r"\b(19\d{2}|20\d{2})\b", content)
    year = year_m.group(1) if year_m else None
    if year:
        mfr = content[: year_m.start()].strip().rstrip("-,").strip()
        if mfr and re.fullmatch(r"[A-Za-z][A-Za-z0-9 ]*", mfr):
            return mfr.lower(), year
        return None, year
    # No 4-digit year found — don't treat the whole content as a manufacturer
    return None, None


def _find_internal(
    tables: List[dict],
    term: str,
    manufacturer: Optional[str] = None,
    year: Optional[str] = None,
) -> List[dict]:
    results = []
    for table in tables:
        name = _normalize_term(table.get("name", ""))
        if term in name:
            results.append(table)

    if len(results) <= 1 or (not manufacturer and not year):
        return results

    # Rank by relevance: exact name match scores highest, then manufacturer/year bonuses
    def _score(table: dict) -> int:
        name = _normalize_term(table.get("name", ""))
        score = 0
        if name == term:
            score += 10
        if manufacturer and (table.get("manufacturer") or "").lower() == manufacturer:
            score += 3
        if year and str(table.get("year") or "") == str(year):
            score += 2
        return score

    results.sort(key=_score, reverse=True)
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
    # Extract manufacturer/year from parenthetical in search_term for ranking
    manufacturer, year = _extract_manufacturer_year(search_term)
    term = _normalize_term(search_term)
    results = _find_internal(tables, term, manufacturer, year)
    while not results and " " in term:
        term = term[:term.rfind(" ")].strip()
        results = _find_internal(tables, term, manufacturer, year)

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


def _find_table_file_by_filename_and_authors(
    table: dict,
    vpx_basename: str,
    script_authors: list,
    info_version: Optional[str] = None,
) -> Optional[dict]:
    """Search table["tableFiles"] for the best match by .vpx filename and/or script authors.

    Match priority:
      1. fileName match AND author match AND version match → perfect match
      2. fileName match AND author match → best match
      3. fileName match only → good
      4. Author match AND version match → good fallback
      5. Author match only → fallback

    vpx_basename: e.g. "AC-DC_Premium_1_3_nFozzy_Roth.vpx" (filename without path)
    script_authors: list of author strings from the VPX script
    info_version: version string from vpxtool info show (e.g. "1.1"), used as bonus signal

    Returns the matching tableFile dict, or None if no match.
    """
    if not table:
        return None

    vpx_lower = vpx_basename.lower()
    vpx_stem = re.sub(r"\.vpx$", "", vpx_lower)
    script_set = {a.lower().strip() for a in (script_authors or [])}
    info_ver_norm = info_version.strip().lstrip("v").lower() if info_version else None

    best_filename_and_author: Optional[dict] = None
    best_filename: Optional[dict] = None
    best_author_version: Optional[dict] = None
    best_author: Optional[dict] = None

    for tf in (table.get("tableFiles") or []):
        tf_name = (tf.get("fileName") or "").lower()
        tf_stem = re.sub(r"\.vpx$", "", tf_name)

        # fileName match: exact or substring (without extension)
        exact_match = tf_name == vpx_lower
        tf_contains_vpx = bool(tf_stem and tf_stem in vpx_stem)
        vpx_contains_tf = bool(vpx_stem and vpx_stem in tf_stem)
        filename_match = exact_match or tf_contains_vpx or vpx_contains_tf

        # author match: same logic as _authors_match — at least one author overlaps
        author_match = False
        if script_set:
            for a in (tf.get("authors") or []):
                a_norm = a.lower().strip()
                for sa in script_set:
                    if sa == a_norm or sa in a_norm or a_norm in sa:
                        author_match = True
                        break
                if author_match:
                    break

        # version match: info_version matches or is contained in the tableFile version
        version_match = False
        if info_ver_norm:
            tf_ver = (tf.get("version") or "").strip().lstrip("v").lower()
            if tf_ver and (info_ver_norm in tf_ver or tf_ver in info_ver_norm):
                version_match = True

        if filename_match and author_match and version_match:
            return tf  # perfect match — can't do better
        elif filename_match and author_match:
            if best_filename_and_author is None:
                best_filename_and_author = tf
        elif filename_match and best_filename is None:
            best_filename = tf
        elif author_match and version_match and best_author_version is None:
            best_author_version = tf
        elif author_match and best_author is None:
            best_author = tf

    return best_filename_and_author or best_filename or best_author_version or best_author


# ─────────────────────────────────────────────────────────────────────────────
# Image caching helpers
# ─────────────────────────────────────────────────────────────────────────────

_IMG_MEM_CACHE: dict = {}           # url -> QPixmap (or None = failed)
_IMG_LOADING: set = set()           # urls currently being fetched
_IMG_LOCK = threading.Lock()
_IMG_CALLBACK_QUEUE: queue.SimpleQueue = queue.SimpleQueue()

# Card / hero dimensions
_CARD_IMG_W = 140
_CARD_IMG_H = 105
_HERO_IMG_W = 420
_HERO_IMG_H = 315

# Font stack: Segoe UI on Windows, system sans-serif elsewhere
_FONT_UI = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def _table_sub_parts(table: dict) -> List[str]:
    """Return [manufacturer, year, type] parts for display (non-empty only)."""
    return [
        p for p in [
            table.get("manufacturer", ""),
            str(table["year"]) if table.get("year") else "",
            table.get("type", ""),
        ] if p
    ]


def _format_authors(authors: list) -> str:
    """Join all author names without truncation."""
    if not authors:
        return ""
    return ", ".join(authors)


def _resolve_img_url(table: dict, table_file: dict) -> Optional[str]:
    """Return the best available preview image URL for a table/tableFile."""
    url = (table_file or {}).get("imgUrl") or (table or {}).get("imgUrl")
    return url if isinstance(url, str) and url.startswith("http") else None


def _img_disk_path(img_dir: str, url: str) -> str:
    """Deterministic local cache path for a URL."""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[-1] or ".webp"
    name = hashlib.md5(url.encode()).hexdigest() + ext
    return os.path.join(img_dir, name)


def _load_image_async(url: str, img_dir: str, callback) -> None:
    """Load or download a preview image asynchronously.

    Queues *callback(QPixmap)* to run in the Qt main thread via
    ``_process_pending_image_callbacks()``.  Does nothing when the URL is
    empty or the image is already loading.
    """
    if not url:
        return

    with _IMG_LOCK:
        if url in _IMG_MEM_CACHE:
            pix = _IMG_MEM_CACHE[url]
            if pix is not None:
                _IMG_CALLBACK_QUEUE.put((callback, pix))
            return
        if url in _IMG_LOADING:
            return
        _IMG_LOADING.add(url)

    cache_file = _img_disk_path(img_dir, url)

    def _worker():
        try:
            if not os.path.isfile(cache_file):
                try:
                    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "vpx-achievement-watcher"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = resp.read()
                    with open(cache_file, "wb") as fh:
                        fh.write(data)
                except Exception:
                    with _IMG_LOCK:
                        _IMG_MEM_CACHE[url] = None
                        _IMG_LOADING.discard(url)
                    return

            pix = QPixmap(cache_file)
            with _IMG_LOCK:
                _IMG_MEM_CACHE[url] = pix if not pix.isNull() else None
                _IMG_LOADING.discard(url)
            if not pix.isNull():
                _IMG_CALLBACK_QUEUE.put((callback, pix))
        except Exception:
            with _IMG_LOCK:
                _IMG_MEM_CACHE[url] = None
                _IMG_LOADING.discard(url)

    threading.Thread(target=_worker, daemon=True).start()


def _process_pending_image_callbacks() -> None:
    """Drain the callback queue — must be called from the Qt main thread."""
    while not _IMG_CALLBACK_QUEUE.empty():
        try:
            cb, pix = _IMG_CALLBACK_QUEUE.get_nowait()
            try:
                cb(pix)
            except RuntimeError:
                pass  # underlying C++ widget already deleted
        except Exception:
            pass


def _make_placeholder_pixmap(w: int, h: int) -> QPixmap:
    """Create a simple dark placeholder with a pinball emoji."""
    pix = QPixmap(w, h)
    pix.fill(QColor("#1a1a1a"))
    painter = QPainter(pix)
    painter.setPen(QColor("#444"))
    f = QFont("Segoe UI", max(10, h // 8))
    painter.setFont(f)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "🎰")
    painter.end()
    return pix


def _format_date(ts) -> str:
    """Convert a millisecond timestamp to DD.MM.YYYY, or ''."""
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%d.%m.%Y")
        except Exception:
            pass
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# VpsCardWidget — one entry in the card list
# ─────────────────────────────────────────────────────────────────────────────

class VpsCardWidget(QFrame):
    """Horizontal card showing thumbnail + metadata for a single VPS tableFile."""

    card_clicked = pyqtSignal(object, object)         # (table, table_file)
    card_double_clicked = pyqtSignal(object, object)  # (table, table_file)

    _STYLE_NORMAL   = "VpsCardWidget{background:#1e1e1e;border:1px solid #333;border-radius:6px;}"
    _STYLE_HOVER    = "VpsCardWidget{background:#252525;border:1px solid #555;border-radius:6px;}"

    @property
    def _STYLE_SELECTED(self):
        return f"VpsCardWidget{{background:#0d2a33;border:2px solid {tc().accent_secondary};border-radius:6px;}}"

    def __init__(self, table: dict, table_file: dict, rom_match: bool, img_dir: str, parent=None):
        super().__init__(parent)
        self.table = table
        self.table_file = table_file
        self._selected = False
        self._img_url = _resolve_img_url(table, table_file)

        self.setMinimumHeight(_CARD_IMG_H + 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._STYLE_NORMAL)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(10)

        # ── Thumbnail ─────────────────────────────────────────────────────────
        self.lbl_img = QLabel()
        self.lbl_img.setFixedSize(_CARD_IMG_W, _CARD_IMG_H)
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setStyleSheet(
            "background:#111; border:1px solid #2a2a2a; border-radius:3px;"
        )
        self.lbl_img.setPixmap(_make_placeholder_pixmap(_CARD_IMG_W, _CARD_IMG_H))
        lay.addWidget(self.lbl_img)

        # ── Metadata ──────────────────────────────────────────────────────────
        meta = QVBoxLayout()
        meta.setContentsMargins(0, 2, 0, 2)
        meta.setSpacing(2)

        # Title + ROM match badge
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        raw_name = table.get("name", "Unknown")
        clean_name = re.sub(r'\s*[\(\[].*?[\)\]]', '', raw_name).strip()
        lbl_name = QLabel(clean_name)
        lbl_name.setStyleSheet("color:#FFFFFF; font-size:13px; font-weight:bold;")
        lbl_name.setWordWrap(True)
        title_row.addWidget(lbl_name, stretch=1)
        if rom_match:
            lbl_rom = QLabel("✅ ROM")
            lbl_rom.setStyleSheet(
                "color:#00C800; font-size:10px; font-weight:bold; padding:0 4px;"
            )
            title_row.addWidget(lbl_rom)
        meta.addLayout(title_row)

        # Manufacturer · year · type
        sub_parts = _table_sub_parts(table)
        if sub_parts:
            lbl_sub = QLabel("  ·  ".join(sub_parts))
            lbl_sub.setStyleSheet("color:#888; font-size:11px;")
            lbl_sub.setWordWrap(True)
            meta.addWidget(lbl_sub)

        # Authors
        authors_text = _format_authors(table_file.get("authors") or [])
        if authors_text:
            lbl_authors = QLabel(f"👤 {authors_text}")
            lbl_authors.setStyleSheet("color:#AAA; font-size:11px;")
            lbl_authors.setWordWrap(True)
            meta.addWidget(lbl_authors)

        # Version · date
        ver_parts = []
        version = table_file.get("version", "")
        if version:
            ver_parts.append(f"v{version}")
        date_s = _format_date(table_file.get("updatedAt"))
        if date_s:
            ver_parts.append(date_s)
        if ver_parts:
            lbl_ver = QLabel("  ·  ".join(ver_parts))
            lbl_ver.setStyleSheet("color:#666; font-size:11px;")
            lbl_ver.setWordWrap(True)
            meta.addWidget(lbl_ver)

        # Feature tags
        features = [f.upper() for f in (table_file.get("features") or []) if isinstance(f, str)]
        if features:
            feat_row = QHBoxLayout()
            feat_row.setContentsMargins(0, 0, 0, 0)
            feat_row.setSpacing(3)
            for feat in features:
                lbl_f = QLabel(feat)
                lbl_f.setStyleSheet(_vps_feature_stylesheet(feat))
                feat_row.addWidget(lbl_f)
            feat_row.addStretch()
            meta.addLayout(feat_row)

        meta.addStretch()
        lay.addLayout(meta, stretch=1)

        # Kick off async image load
        if self._img_url:
            _load_image_async(self._img_url, img_dir, self._on_image_loaded)

    # ── Image callback ────────────────────────────────────────────────────────

    def _on_image_loaded(self, pixmap: QPixmap) -> None:
        try:
            if pixmap and not pixmap.isNull():
                self.lbl_img.setPixmap(
                    pixmap.scaled(
                        _CARD_IMG_W, _CARD_IMG_H,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        except RuntimeError:
            pass

    # ── Selection state ───────────────────────────────────────────────────────

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setStyleSheet(self._STYLE_SELECTED if selected else self._STYLE_NORMAL)

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.card_clicked.emit(self.table, self.table_file)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.card_double_clicked.emit(self.table, self.table_file)
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event):
        if not self._selected:
            self.setStyleSheet(self._STYLE_HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._selected:
            self.setStyleSheet(self._STYLE_NORMAL)
        super().leaveEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# VpsHeroPanel — selected-table detail area at the top of the picker
# ─────────────────────────────────────────────────────────────────────────────

class VpsHeroPanel(QFrame):
    """Detail/hero panel that updates whenever the user selects a card."""

    def __init__(self, img_dir: str, parent=None):
        super().__init__(parent)
        self.img_dir = img_dir
        self._current_url: Optional[str] = None

        self.setMinimumHeight(_HERO_IMG_H + 20)
        self.setStyleSheet(
            "VpsHeroPanel{background:#151515; border:1px solid #2a2a2a; border-radius:6px;}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(14)

        # ── Image ─────────────────────────────────────────────────────────────
        self.lbl_img = QLabel()
        self.lbl_img.setFixedSize(_HERO_IMG_W, _HERO_IMG_H)
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setStyleSheet(
            "background:#111; border:1px solid #2a2a2a; border-radius:4px;"
        )
        self.lbl_img.setPixmap(_make_placeholder_pixmap(_HERO_IMG_W, _HERO_IMG_H))
        lay.addWidget(self.lbl_img)

        # ── Details ───────────────────────────────────────────────────────────
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(4)

        self.lbl_name = QLabel("— no selection —")
        self.lbl_name.setStyleSheet(
            "color:#FFFFFF; font-size:16px; font-weight:bold;"
        )
        self.lbl_name.setWordWrap(True)
        details.addWidget(self.lbl_name)

        self.lbl_sub = QLabel()
        self.lbl_sub.setStyleSheet("color:#888; font-size:12px;")
        self.lbl_sub.setWordWrap(True)
        details.addWidget(self.lbl_sub)

        self.lbl_authors = QLabel()
        self.lbl_authors.setStyleSheet("color:#AAA; font-size:12px;")
        self.lbl_authors.setWordWrap(True)
        details.addWidget(self.lbl_authors)

        self.lbl_ver = QLabel()
        self.lbl_ver.setStyleSheet("color:#666; font-size:11px;")
        self.lbl_ver.setWordWrap(True)
        details.addWidget(self.lbl_ver)

        # Feature-tag row: use a dedicated container widget so we can clear it
        self.feat_widget = QWidget()
        self.feat_widget.setStyleSheet("QWidget { background: transparent; }")
        self._feat_lay = QHBoxLayout(self.feat_widget)
        self._feat_lay.setContentsMargins(0, 0, 0, 0)
        self._feat_lay.setSpacing(4)
        details.addWidget(self.feat_widget)

        self.lbl_ids = QLabel()
        self.lbl_ids.setStyleSheet("color:#3a3a3a; font-size:10px;")
        self.lbl_ids.setWordWrap(True)
        details.addWidget(self.lbl_ids)

        details.addStretch()
        lay.addLayout(details, stretch=1)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_selection(self, table: Optional[dict], table_file: Optional[dict]) -> None:
        table = table or {}
        table_file = table_file or {}

        # Name
        raw_name = table.get("name", "")
        self.lbl_name.setText(
            re.sub(r'\s*[\(\[].*?[\)\]]', '', raw_name).strip() if raw_name else "— no selection —"
        )

        # Manufacturer · year · type
        self.lbl_sub.setText("  ·  ".join(_table_sub_parts(table)))

        # Authors
        authors_text = _format_authors(table_file.get("authors") or [])
        self.lbl_authors.setText(f"👤 {authors_text}" if authors_text else "")

        # Version · date
        ver_parts = []
        version = table_file.get("version", "")
        if version:
            ver_parts.append(f"v{version}")
        date_s = _format_date(table_file.get("updatedAt"))
        if date_s:
            ver_parts.append(date_s)
        self.lbl_ver.setText("  ·  ".join(ver_parts))

        # Features
        self._clear_features()
        features = [f.upper() for f in (table_file.get("features") or []) if isinstance(f, str)]
        for feat in features:
            lbl_f = QLabel(feat)
            lbl_f.setStyleSheet(_vps_feature_stylesheet(feat))
            self._feat_lay.addWidget(lbl_f)
        if features:
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            spacer.setStyleSheet("QWidget { background: transparent; }")
            self._feat_lay.addWidget(spacer)

        # IDs
        table_id = table.get("id", "")
        tf_id = table_file.get("id", "")
        id_parts = []
        if table_id:
            id_parts.append(f"table: {table_id}")
        if tf_id and tf_id != table_id:
            id_parts.append(f"file: {tf_id}")
        self.lbl_ids.setText("  ·  ".join(id_parts))

        # Image
        img_url = _resolve_img_url(table, table_file)
        if img_url and img_url != self._current_url:
            self._current_url = img_url
            self.lbl_img.setPixmap(_make_placeholder_pixmap(_HERO_IMG_W, _HERO_IMG_H))
            _load_image_async(img_url, self.img_dir, self._on_image_loaded)
        elif not img_url:
            self._current_url = None
            self.lbl_img.setPixmap(_make_placeholder_pixmap(_HERO_IMG_W, _HERO_IMG_H))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_features(self) -> None:
        while self._feat_lay.count():
            item = self._feat_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

    def _on_image_loaded(self, pixmap: QPixmap) -> None:
        try:
            if pixmap and not pixmap.isNull():
                self.lbl_img.setPixmap(
                    pixmap.scaled(
                        _HERO_IMG_W, _HERO_IMG_H,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        except RuntimeError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# VPS Picker Dialog — image-driven card picker
# ─────────────────────────────────────────────────────────────────────────────

class VpsPickerDialog(QDialog):
    """Visual card-grid VPS picker with hero panel and async image previews."""

    def __init__(self, cfg, tables: List[dict], rom: str, table_title: str, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.tables = tables
        self.rom = rom
        self.table_title = table_title
        self.selected_table: Optional[dict] = None
        self.selected_table_file: Optional[dict] = None
        self._card_entries: List[tuple] = []   # (table, table_file) per card
        self._cards: List[VpsCardWidget] = []
        self._selected_idx: int = -1

        from watcher_core import p_vps_img
        self._img_dir = p_vps_img(cfg)

        self.setWindowTitle(f"Select VPS Table — {table_title} [{rom}]")
        self.setMinimumSize(980, 820)
        self.resize(1100, 940)
        self.setStyleSheet("background:#141414; color:#DDD;")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Header: title + search ────────────────────────────────────────────
        hdr = QHBoxLayout()
        lbl_hdr = QLabel("🎰  VPS Table Picker")
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

        # ── Hero panel ────────────────────────────────────────────────────────
        self.hero = VpsHeroPanel(self._img_dir, parent=self)
        root.addWidget(self.hero)

        # ── Card scroll area ──────────────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { background:#141414; border:none; }"
            "QScrollBar:vertical { background:#1e1e1e; width:10px; }"
            "QScrollBar::handle:vertical { background:#555; border-radius:5px; min-height:20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        )

        self._card_container = QWidget()
        self._card_container.setStyleSheet("background:#141414;")
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(4, 4, 4, 4)
        self._card_layout.setSpacing(6)
        self._card_layout.addStretch()

        self.scroll.setWidget(self._card_container)
        root.addWidget(self.scroll, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#333;")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_remove = QPushButton("❌ Remove Assignment")
        btn_remove.setStyleSheet(
            f"background:#3D0000; color:{tc().danger}; border:1px solid {tc().danger};"
            " padding:6px 14px; border-radius:4px;"
        )
        btn_remove.clicked.connect(self._remove_assignment)
        btn_row.addWidget(btn_remove)
        btn_row.addStretch()

        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("color:#555; font-size:11px;")
        btn_row.addWidget(self.lbl_count)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(
            "background:#2a2a2a; color:#AAA; border:1px solid #555;"
            " padding:6px 14px; border-radius:4px;"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("✅ Select")
        btn_ok.setStyleSheet(
            f"background:#003D00; color:{tc().accent_secondary}; font-weight:bold;"
            f" border:1px solid {tc().accent_secondary}; padding:6px 14px; border-radius:4px;"
        )
        btn_ok.clicked.connect(self._accept_selection)
        btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

        # Poll the image-callback queue every 80 ms.  Images are downloaded on
        # daemon threads; results are posted to _IMG_CALLBACK_QUEUE (thread-safe)
        # and consumed here, safely on the Qt main thread.
        self._cb_timer = QTimer(self)
        self._cb_timer.timeout.connect(_process_pending_image_callbacks)
        self._cb_timer.start(80)

        # Pre-fill and populate (block the textChanged signal so _on_search is
        # not triggered; we call _populate_cards once explicitly below, keeping
        # image-loading callbacks valid for the cards we actually display).
        clean_title = self._clean_table_title(table_title)
        self.txt_search.blockSignals(True)
        self.txt_search.setText(clean_title)
        self.txt_search.blockSignals(False)
        self._populate_cards(clean_title)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _clean_table_title(title: str) -> str:
        """Strip brackets, parentheses and extra info — keep only the table name."""
        name = re.sub(r'\s*\[.*?\]', '', title)
        name = re.sub(r'\s*\(.*?\)', '', name)
        return name.strip()

    # ── Card management ───────────────────────────────────────────────────────

    def _populate_cards(self, search_term: str) -> None:
        """Rebuild the card list from search results."""
        # Deselect & clear
        self._cards.clear()
        self._card_entries.clear()
        self._selected_idx = -1
        self.selected_table = None
        self.selected_table_file = None

        # Remove old card widgets (keep the trailing stretch at position -1)
        while self._card_layout.count() > 1:
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Build entry list
        results = _vps_find(self.tables, search_term, self.rom)
        if not results:
            results = self.tables[:50]

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

        # Create cards
        for idx, (table, table_file, rom_match) in enumerate(entries):
            card = VpsCardWidget(
                table, table_file, rom_match, self._img_dir,
                parent=self._card_container,
            )
            card.card_clicked.connect(
                functools.partial(self._on_card_selected, idx)
            )
            card.card_double_clicked.connect(
                functools.partial(self._on_card_activated, idx)
            )
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)
            self._cards.append(card)
            self._card_entries.append((table, table_file))

        n = len(entries)
        self.lbl_count.setText(f"{n} result{'s' if n != 1 else ''}")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_search(self, text: str) -> None:
        self._populate_cards(text)

    def _on_card_selected(self, idx: int, table: dict, table_file: dict) -> None:
        if 0 <= self._selected_idx < len(self._cards):
            self._cards[self._selected_idx].set_selected(False)
        self._selected_idx = idx
        if 0 <= idx < len(self._cards):
            self._cards[idx].set_selected(True)
        self.selected_table = table
        self.selected_table_file = table_file
        self.hero.update_selection(table, table_file)

    def _on_card_activated(self, idx: int, table: dict, table_file: dict) -> None:
        self._on_card_selected(idx, table, table_file)
        self._accept_selection()

    def _accept_selection(self) -> None:
        if not self.selected_table:
            return
        self.accept()

    def _remove_assignment(self) -> None:
        self.selected_table = None
        self.selected_table_file = None
        self.done(2)  # special return code for "remove"


# ─────────────────────────────────────────────────────────────────────────────
# VPS Achievement Info Dialog
# ─────────────────────────────────────────────────────────────────────────────

class VpsAchievementInfoDialog(QDialog):
    """Show achievement details with VPS table info."""

    # Emitted when the user clicks the "Assign in Available Maps" link.
    navigate_to_available_maps = pyqtSignal()

    def __init__(self, cfg, rom: str, title: str, rule: Optional[dict], unlock_entry: Any, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(f"ℹ️  {title}")
        self.setMinimumSize(500, 320)
        self.setStyleSheet("background:#111; color:#DDD;")

        layout = QVBoxLayout(self)

        # Header
        lbl_title = QLabel(f"<b style='font-size:14px; color:{tc().accent_secondary};'>🏆 {title}</b>")
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
        # Use only the VPS-ID that was recorded at unlock time (immutable snapshot).
        # Do not fall back to the current mapping so historical context is preserved.
        vps_id = unlock_entry.get("vps_id") if isinstance(unlock_entry, dict) else None

        if vps_id:
            tables = _load_vpsdb(cfg)
            vps_entry = None
            tf_entry = None
            if tables:
                for t in tables:
                    if t.get("id") == vps_id:
                        vps_entry = t
                        break
                    # Also search inside tableFiles so tableFile.id values resolve correctly
                    for tf in (t.get("tableFiles") or []):
                        if tf.get("id") == vps_id:
                            vps_entry = t
                            tf_entry = tf
                            break
                    if vps_entry:
                        break

            if vps_entry:
                name = vps_entry.get("name", "")
                mfr = vps_entry.get("manufacturer", "")
                year = vps_entry.get("year", "")
                right_lay.addWidget(QLabel(f"<b style='color:{tc().accent_primary}; font-size:13px;'>{name}</b>"))
                right_lay.addWidget(QLabel(f"<span style='color:#999;'>{mfr} · {year}</span>"))
                if tf_entry:
                    tf_version = tf_entry.get("version", "")
                    tf_authors = ", ".join(tf_entry.get("authors") or [])
                    if tf_version:
                        right_lay.addWidget(QLabel(f"<span style='color:#AAA; font-size:11px;'>Version: {tf_version}</span>"))
                    if tf_authors:
                        right_lay.addWidget(QLabel(f"<span style='color:#AAA; font-size:11px;'>Authors: {tf_authors}</span>"))
                    right_lay.addWidget(QLabel(f"<span style='color:#555; font-size:10px;'>tableFile.id: {vps_id}</span>"))
                else:
                    right_lay.addWidget(QLabel(f"<span style='color:#555; font-size:10px;'>ID: {vps_id}</span>"))
            else:
                right_lay.addWidget(QLabel(f"<span style='color:#888;'>VPS-ID: {vps_id} (not in local cache)</span>"))
        else:
            lbl_no = QLabel("No VPS-ID at unlock time")
            lbl_no.setStyleSheet("color:#666;")
            right_lay.addWidget(lbl_no)
            lbl_hint = QLabel(f"<a href='#available_maps' style='color:{tc().accent_secondary};'>→ Assign in 'Available Maps' tab</a>")
            lbl_hint.setStyleSheet(f"color:{tc().accent_secondary};")
            lbl_hint.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            lbl_hint.setOpenExternalLinks(False)
            lbl_hint.linkActivated.connect(lambda _href: (self.navigate_to_available_maps.emit(), self.accept()))
            right_lay.addWidget(lbl_hint)

        right_lay.addSpacing(8)

        # Achievement details
        if rule:
            right_lay.addWidget(QLabel(f"<b style='color:#DDD;'>ROM:</b>  <span style='color:{tc().accent_secondary};'>{rom}</span>"))
            cond = rule.get("condition", {}) or {}
            rtype = str(cond.get("type", "")).lower()
            field = cond.get("field", "")
            target = cond.get("min", "")
            if rtype:
                right_lay.addWidget(QLabel(f"<b style='color:#DDD;'>Type:</b>  <span style='color:#999;'>{rtype}</span>"))
            if field:
                right_lay.addWidget(QLabel(f"<b style='color:#DDD;'>Field:</b>  <span style='color:#999;'>{field}</span>"))
            if target:
                right_lay.addWidget(QLabel(f"<b style='color:#DDD;'>Target:</b>  <span style='color:{tc().accent_primary};'>{target}</span>"))

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
                    right_lay.addWidget(QLabel(f"✅ <b style='color:{tc().accent_secondary};'>Unlocked on:</b>"))
                    right_lay.addWidget(QLabel(f"📅 <span style='color:#DDD;'>{date_str}</span>"))
                except Exception:
                    right_lay.addWidget(QLabel(f"✅ <span style='color:{tc().accent_secondary};'>Unlocked</span>"))
            else:
                right_lay.addSpacing(4)
                right_lay.addWidget(QLabel(f"✅ <span style='color:{tc().accent_secondary};'>Unlocked</span>"))
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


# ─────────────────────────────────────────────────────────────────────────────
# Cloud Progress VPS Info Dialog
# ─────────────────────────────────────────────────────────────────────────────

class CloudProgressVpsInfoDialog(QDialog):
    """Show VPS table info for a cloud-progress entry.

    When *breakdown* is provided (a ``{vps_id: unlock_count}`` dict) and
    contains more than one entry, each contributing table is shown with its
    percentage share.  For a single table the full :class:`VpsHeroPanel` is
    used so the hero image, feature tags and all metadata are visible.
    """

    def __init__(
        self,
        cfg,
        vps_id: str,
        table_name: str = "",
        breakdown: Optional[dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("ℹ️  Cloud Progress — Table Info")
        self.setMinimumWidth(640)
        self.setStyleSheet("background:#111; color:#DDD;")

        from watcher_core import p_vps_img
        self._img_dir = p_vps_img(cfg)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        lbl_hdr = QLabel(f"<b style='font-size:14px; color:{tc().accent_secondary};'>🎰 Cloud Progress — Table Info</b>")
        lbl_hdr.setWordWrap(True)
        layout.addWidget(lbl_hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#333;")
        layout.addWidget(sep)

        # Resolve all entries from vpsdb
        tables = _load_vpsdb(cfg)
        # Normalise breakdown: ensure the primary vps_id is represented
        if breakdown and isinstance(breakdown, dict) and len(breakdown) > 0:
            bd: dict = dict(breakdown)
        elif vps_id:
            bd = {vps_id: 1}
        else:
            bd = {}

        resolved: list = []  # list of (table, table_file, count, pct)
        if tables and bd:
            total_count = max(sum(bd.values()), 1)

            # First pass: resolve each vps_id to (vps_entry, tf_entry, count).
            # A vps_id may be a top-level game ID *or* a tableFile ID.  Both can
            # legitimately appear in the breakdown when the VPS mapping was updated
            # mid-session, causing duplicate entries for the same physical table.
            raw: list = []  # (vps_entry, tf_entry, count)
            for vid, count in sorted(bd.items(), key=lambda x: -x[1]):
                vps_entry = None
                tf_entry = None
                for t in tables:
                    if t.get("id") == vid:
                        vps_entry = t
                        break
                    for tf in (t.get("tableFiles") or []):
                        if tf.get("id") == vid:
                            vps_entry = t
                            tf_entry = tf
                            break
                    if vps_entry:
                        break
                raw.append((vps_entry, tf_entry, count))

            # Second pass: deduplicate entries that resolve to the same top-level
            # game table.  Merge counts and prefer the entry that has a specific
            # tableFile (tf_entry) over a bare top-level match, so the richer
            # metadata is always shown.  Unresolved (None) entries are only kept
            # when no valid table entries were found at all.
            dedup: dict = {}  # game_id -> [vps_entry, tf_entry, merged_count]
            none_count = 0
            for vps_entry, tf_entry, count in raw:
                if vps_entry is None:
                    none_count += count
                    continue
                # Use a per-object fallback so entries without an 'id' are never
                # accidentally merged with each other.
                game_id = vps_entry.get("id") or id(vps_entry)
                if game_id not in dedup:
                    dedup[game_id] = [vps_entry, tf_entry, count]
                else:
                    slot = dedup[game_id]
                    slot[2] += count  # accumulate count
                    # Prefer the entry that carries tableFile metadata
                    if tf_entry is not None and slot[1] is None:
                        slot[0] = vps_entry
                        slot[1] = tf_entry

            for vps_entry, tf_entry, count in sorted(dedup.values(), key=lambda item: -item[2]):  # descending by count
                pct = round(count / total_count * 100, 1)
                resolved.append((vps_entry, tf_entry, count, pct))

            # Include unresolved entries only when there are no valid table matches
            if not resolved and none_count > 0:
                resolved = [(None, None, none_count, 100.0)]
        elif vps_id:
            # vpsdb unavailable: show limited info from URL params
            resolved = [(None, None, 1, 100.0)]

        self._cb_timer = QTimer(self)
        self._cb_timer.timeout.connect(_process_pending_image_callbacks)
        self._cb_timer.start(80)

        multi = len(resolved) > 1

        if not resolved:
            lbl_none = QLabel("<span style='color:#888;'>No VPS table information available.</span>")
            layout.addWidget(lbl_none)
        elif not multi:
            # ── Single table: full hero panel ──────────────────────────────
            vps_entry, tf_entry, _count, _pct = resolved[0]
            if vps_entry:
                hero = VpsHeroPanel(self._img_dir, parent=self)
                hero.update_selection(vps_entry, tf_entry or {})
                layout.addWidget(hero)
            else:
                self._add_unknown_table_info(layout, vps_id, table_name)
        else:
            # ── Multiple tables: scrollable list with percentage bars ───────
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea{border:none;} QScrollBar:vertical{width:8px;}")
            container = QWidget()
            container.setStyleSheet("background:#111;")
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(10)

            for vps_entry, tf_entry, _count, pct in resolved:
                entry_widget = self._build_table_entry(vps_entry, tf_entry, pct)
                vbox.addWidget(entry_widget)

            vbox.addStretch()
            scroll.setWidget(container)
            layout.addWidget(scroll)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background:#222; color:#AAA; margin-top:8px;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _add_unknown_table_info(self, layout: QVBoxLayout, vps_id: str, table_name: str) -> None:
        """Fallback: show plain text when the vps_id is not in the local cache."""
        if table_name:
            lbl = QLabel(f"<b style='color:{tc().accent_primary}; font-size:13px;'>{table_name}</b>")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
        if vps_id:
            lbl_id = QLabel(f"<span style='color:#888; font-size:11px;'>VPS-ID: {vps_id} (not in local cache)</span>")
            lbl_id.setWordWrap(True)
            layout.addWidget(lbl_id)
        else:
            lbl_no = QLabel("<span style='color:#888;'>No VPS table information available.</span>")
            layout.addWidget(lbl_no)

    def _build_table_entry(self, vps_entry: Optional[dict], tf_entry: Optional[dict], pct: float) -> QWidget:
        """Build a compact widget showing one table + its percentage contribution."""
        wrapper = QWidget()
        wrapper.setStyleSheet("background:#1a1a1a; border-radius:6px;")
        vbox = QVBoxLayout(wrapper)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        # Percentage row
        pct_row = QHBoxLayout()
        pct_label = QLabel(f"<b style='color:{tc().accent_secondary}; font-size:13px;'>{pct:.1f}%</b>")
        pct_row.addWidget(pct_label)
        pct_row.addStretch()
        vbox.addLayout(pct_row)

        # Progress bar
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(round(pct)))
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            "QProgressBar{background:#333; border-radius:3px; border:none;}"
            f"QProgressBar::chunk{{background:{tc().accent_secondary}; border-radius:3px;}}"
        )
        vbox.addWidget(bar)

        if vps_entry:
            card = VpsCardWidget(
                vps_entry,
                tf_entry or {},
                False,
                self._img_dir,
                parent=wrapper,
            )
            vbox.addWidget(card)
        else:
            lbl_no = QLabel("<span style='color:#888; font-size:11px;'>VPS ID not in local cache</span>")
            vbox.addWidget(lbl_no)

        return wrapper

    def closeEvent(self, event):
        self._cb_timer.stop()
        super().closeEvent(event)