
from __future__ import annotations

import configparser
import random
import subprocess
import hashlib
import copy
import os, sys, time, json, re, glob, threading, uuid
import urllib.parse as _urlparse
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict, Counter
from PyQt6.QtGui import QFontMetrics

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QTextBrowser, QSystemTrayIcon, QMenu, QFileDialog, QMessageBox, QTabWidget,
    QCheckBox, QSlider, QComboBox, QDialog, QGroupBox, QColorDialog, QLineEdit,
    QFontComboBox, QSpinBox, QDoubleSpinBox, QGridLayout, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressDialog, QScrollArea, QCompleter,
    QFrame,
)
from PyQt6.QtCore import (Qt, pyqtSignal, QEvent, QTimer, QRect,
                          QAbstractNativeEventFilter, QCoreApplication, QObject, QPoint, pyqtSlot,
                          QThread, QUrl, QStringListModel)
from PyQt6.QtGui import (QIcon, QColor, QFont, QTransform, QPixmap,
                         QPainter, QImage, QPen)

try:
    import win32gui
except Exception:
    win32gui = None

import ctypes
from ctypes import wintypes
import ssl
from urllib.request import Request, urlopen

from watcher_core import (
    APP_DIR, AppConfig, CloudSync, Watcher,
    JOYINFOEX, JOYERR_NOERROR, JOY_RETURNALL, _joyGetPosEx,
    WM_HOTKEY, WM_KEYDOWN, WM_SYSKEYDOWN,
    KBDLLHOOKSTRUCT, GlobalKeyHook,
    ensure_dir, log, resource_path, sanitize_filename,
    apply_tooltips, f_achievements_state, f_global_ach,
    register_raw_input_for_window, secure_load_json, secure_save_json, vk_to_name_en,
    compute_player_level, LEVEL_TABLE, PRESTIGE_THRESHOLD, compute_rarity, RARITY_TIERS,
    f_vps_mapping, f_vpsdb_cache, run_vpxtool_get_rom,
    run_vpxtool_get_script_authors,
    run_vpxtool_info_show,
    _strip_version_from_name,
)

from ui_dialogs import SetupWizardDialog, FeedbackDialog
from tutorial import TutorialWizardDialog
from theme import pinball_arcade_style, generate_stylesheet, list_themes, get_theme, DEFAULT_THEME, get_theme_color
from ui_cloud_stats import CloudStatsMixin
from ui_dashboard import DashboardMixin
from ui_player import PlayerMixin
from ui_progress import ProgressMixin
from ui_appearance import AppearanceMixin
from ui_system import SystemMixin

from ui_vps import (
    VpsPickerDialog, VpsAchievementInfoDialog, CloudProgressVpsInfoDialog,
    _load_vpsdb, _load_vps_mapping, _save_vps_mapping, _vps_find, _table_has_rom,
    _normalize_term, _find_table_file_by_filename_and_authors,
)

import notifications as _notif
import sound

from ui_overlay import (
    OverlayWindow,
    MiniInfoOverlay,
    StatusOverlay,
    StatusOverlayPositionPicker,
    read_active_players,
    FlipCounterOverlay,
    FlipCounterPositionPicker,
    TimerPositionPicker,
    ToastPositionPicker,
    ChallengeOVPositionPicker,
    MiniInfoPositionPicker,
    OverlayPositionPicker,
    AchToastWindow,
    AchToastManager,
    ChallengeCountdownOverlay,
    ChallengeSelectOverlay,
    FlipDifficultyOverlay,
    HeatBarometerOverlay,
    HeatBarPositionPicker,
    ChallengeStartCountdown,
)

class _AvailableMapsWorker(QThread):
    """Background worker that scans TABLES_DIR and builds the available-maps list."""
    progress = pyqtSignal(int, int, str)   # (current_index, total, filename)
    finished = pyqtSignal(list)            # sorted list of entry dicts

    def __init__(self, cfg, watcher, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.watcher = watcher
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        romnames = self.watcher.ROMNAMES or {}

        # Build base list from cloud index
        index_roms = set(k for k in (self.watcher.INDEX or {}).keys() if not k.startswith("_"))
        entries: dict = {}
        for rom in index_roms:
            title = romnames.get(rom, "Unknown Table")
            entries[rom] = {"rom": rom, "title": title, "has_map": False, "is_local": False, "vps_id": "", "vpx_path": ""}

        # Collect all .vpx files first so we can report total count
        tables_dir = getattr(self.cfg, "TABLES_DIR", None)
        vpx_files = []
        if tables_dir and os.path.isdir(tables_dir):
            for root, _dirs, files in os.walk(tables_dir):
                for fname in files:
                    if fname.lower().endswith(".vpx"):
                        vpx_files.append((root, fname))

        # Build a lowercase-to-original-key map once for O(1) case-insensitive lookups
        entries_lower: dict = {k.lower(): k for k in entries}

        total = len(vpx_files)
        for i, (root, fname) in enumerate(vpx_files):
            if self._cancel:
                break
            self.progress.emit(i, total, fname)
            vpx_path = os.path.join(root, fname)
            try:
                rom = run_vpxtool_get_rom(self.cfg, vpx_path, suppress_warn=True)
            except Exception:
                rom = None
            if not rom:
                continue
            # Normalize ROM to lowercase for case-insensitive matching against cloud index
            rom_lower = rom.lower()
            matched_key = entries_lower.get(rom_lower)
            if matched_key:
                rom = matched_key
            elif rom not in entries:
                title = romnames.get(rom) or romnames.get(rom_lower) or fname.rsplit(".", 1)[0]
                entries[rom] = {"rom": rom, "title": title, "has_map": False, "is_local": False, "vps_id": "", "vpx_path": ""}
                entries_lower[rom_lower] = rom
            entries[rom]["is_local"] = True
            entries[rom]["vpx_path"] = vpx_path   # store path for later author extraction

            # Store vpx_info metadata for richer table display
            try:
                vpx_info = run_vpxtool_info_show(self.cfg, vpx_path)
                if vpx_info:
                    entries[rom]["vpx_info"] = vpx_info
                    # Use table_name from info if the current title is just the filename
                    info_name = (vpx_info.get("table_name") or "").strip()
                    if info_name and entries[rom]["title"] == fname.rsplit(".", 1)[0]:
                        entries[rom]["title"] = info_name
            except Exception:
                pass

        # Check NVRAM-Map availability (with family fallback, same as during gameplay)
        for rom, entry in entries.items():
            if self._cancel:
                break
            try:
                if self.watcher._has_any_map(rom):
                    entry["has_map"] = True
                else:
                    fields, src, matched = self.watcher._resolve_map_from_index_then_family(rom)
                    entry["has_map"] = bool(fields)
            except Exception:
                entry["has_map"] = False

        # Load current VPS mappings
        mapping = _load_vps_mapping(self.cfg)
        for rom, entry in entries.items():
            entry["vps_id"] = mapping.get(rom, mapping.get(rom.lower(), ""))

        result = sorted(entries.values(), key=lambda e: e["title"].lower())
        self.finished.emit(result)


class Bridge(QObject):
    overlay_trigger = pyqtSignal()
    overlay_show = pyqtSignal()
    mini_info_show = pyqtSignal(str, int)
    ach_toast_show = pyqtSignal(str, str, int)
    challenge_timer_start = pyqtSignal(int)
    challenge_timer_stop = pyqtSignal()
    challenge_warmup_show = pyqtSignal(int, str)
    challenge_info_show = pyqtSignal(str, int, str)
    challenge_speak = pyqtSignal(str)
    achievements_updated = pyqtSignal()
    flip_counter_total_show = pyqtSignal(int, int, int)  
    flip_counter_total_update = pyqtSignal(int, int, int)
    flip_counter_total_hide = pyqtSignal()
    heat_bar_show = pyqtSignal()
    heat_bar_update = pyqtSignal(int)
    heat_bar_hide = pyqtSignal()
    
    prefetch_started = pyqtSignal()
    prefetch_progress = pyqtSignal(str)
    prefetch_finished = pyqtSignal(str)
    level_up_show = pyqtSignal(str, int)   # (level_name, level_number)
    status_overlay_show = pyqtSignal(str, int, str)  # (message, seconds, color_hex)
    close_secondary_overlays = pyqtSignal()
    session_ended = pyqtSignal(str)  # (rom)


def _authors_match(script_authors: list, vps_table: dict) -> bool:
    """Check if any script author matches any author in any tableFile of the VPS entry."""
    if not script_authors:
        return False
    script_set = {a.lower().strip() for a in script_authors}
    for tf in (vps_table.get("tableFiles") or []):
        for a in (tf.get("authors") or []):
            a_norm = a.lower().strip()
            for sa in script_set:
                if sa == a_norm or sa in a_norm or a_norm in sa:
                    return True
    return False


def _parse_version(v_str):
    """Parse a version string like '2.5' or '2.5.1' into a comparable tuple of ints."""
    try:
        return tuple(map(int, str(v_str).split('.')))
    except Exception:
        return (0,)


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
            from watcher_core import p_vps_img
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
                    from ui_vps import VpsHeroPanel, _process_pending_image_callbacks
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
            "background:#00E5FF; color:#000; font-weight:bold; padding:4px 16px; border-radius:3px;"
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


class MainWindow(QMainWindow, CloudStatsMixin, DashboardMixin, PlayerMixin,
                 ProgressMixin, AppearanceMixin, SystemMixin):
    CURRENT_VERSION = "2.7"

    def __init__(self, cfg: AppConfig, watcher: Watcher, bridge: Bridge):
        super().__init__()
        self.cfg = cfg
        self.watcher = watcher
        self.bridge = bridge
        self.setWindowTitle("VPX Achievement Watcher")
        self.resize(1606, 1155)
        
        icon = self._get_icon()
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        
        if "player_id" not in self.cfg.OVERLAY:
            self.cfg.OVERLAY["player_id"] = str(uuid.uuid4())[:4]
            self.cfg.save()

        # Last successfully validated player identity — used to revert fields on conflict.
        self._validated_player_name = self.cfg.OVERLAY.get("player_name", "").strip()
        self._validated_player_id = self.cfg.OVERLAY.get("player_id", "").strip()
            
        self.main_tabs = QTabWidget()
        self.setCentralWidget(self.main_tabs)

        self.bridge.overlay_trigger.connect(self._on_overlay_trigger)
        self.bridge.overlay_show.connect(self._show_overlay_latest)
        self.bridge.mini_info_show.connect(self._on_mini_info_show)
        self.bridge.ach_toast_show.connect(self._on_ach_toast_show)
        self._ach_toast_mgr = AchToastManager(self)
        self.bridge.challenge_info_show.connect(self._on_challenge_info_show)
        self.bridge.challenge_timer_start.connect(self._on_challenge_timer_start)
        self.bridge.challenge_timer_stop.connect(self._on_challenge_timer_stop)
        self.bridge.challenge_warmup_show.connect(self._on_challenge_warmup_show)
        self.bridge.challenge_speak.connect(self._on_challenge_speak)
        
        self.bridge.prefetch_started.connect(self._on_prefetch_started)
        self.bridge.prefetch_progress.connect(self._on_prefetch_progress)
        self.bridge.prefetch_finished.connect(self._on_prefetch_finished)
        self.bridge.level_up_show.connect(self._on_level_up)
        self.bridge.achievements_updated.connect(self._refresh_level_display)
        self.bridge.status_overlay_show.connect(self._on_status_overlay_show)
        self.bridge.achievements_updated.connect(self._refresh_dashboard_cards)
        self.bridge.close_secondary_overlays.connect(self._close_secondary_overlays)
        self.bridge.session_ended.connect(self._on_session_ended)
        
        self._prefetch_blink_timer = QTimer(self)
        self._prefetch_blink_timer.setInterval(600)  # Blink-Intervall in ms
        self._prefetch_blink_timer.timeout.connect(self._on_prefetch_blink)
        self._prefetch_blink_state = False
        self._prefetch_msg = ""
        self._rarity_cache: dict = {}  # {rom: {"data": {...}, "ts": float, "total_players": int}}

        self._build_tab_dashboard()
        self._build_tab_player()
        self._build_tab_appearance()
        self._build_tab_controls()
        self._build_tab_stats()
        self._build_tab_progress()        
        self._build_tab_available_maps()   
        self._build_tab_cloud() 
        self._build_tab_system()

        self.register_flip_counter_handlers()
        self.register_heat_bar_handlers()

        self.timer_stats = QTimer(self)
        self.timer_stats.timeout.connect(self.update_stats)
        self.timer_stats.start(4000)

        self.overlay_refresh_timer = QTimer(self)
        self.overlay_refresh_timer.setInterval(2000)
        self.overlay_refresh_timer.timeout.connect(self._refresh_overlay_live)
        if bool(self.cfg.OVERLAY.get("live_updates", False)):
            self.overlay_refresh_timer.start()

        self.overlay_auto_close_timer = QTimer(self)
        self.overlay_auto_close_timer.setSingleShot(True)
        self.overlay_auto_close_timer.timeout.connect(self._hide_overlay)

        self._joy_toggle_last_mask = 0
        self._joy_toggle_timer = QTimer(self)
        self._joy_toggle_timer.setInterval(120)
        self._joy_toggle_timer.timeout.connect(self._on_joy_toggle_poll)

        self._apply_toggle_source()
        self._last_toggle_ts = 0.0

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            menu = QMenu()
            menu.addAction("Open", self._show_from_tray)
            menu.addAction("Quit GUI", self.quit_all)
            self.tray.setContextMenu(menu)
            self.tray.show()
            
            QTimer.singleShot(1500, lambda: self.tray.showMessage(
                "VPX Achievement Watcher", 
                "Watcher is running in the background!", 
                QSystemTrayIcon.MessageIcon.Information, 
                3000
            ))
        else:
            self.tray = None

        self._overlay_cycle = {"sections": [], "idx": -1}
        self._overlay_busy = False
        self._overlay_last_action = 0.0
        self.overlay = None
        self._overlay_page = 0  # current page in the 4-page main overlay (0=Main Stats, 1=Achievement Progress, 2=Challenge Leaderboard, 3=Cloud Leaderboard)

        self._challenge_select = None
        self._challenge_select_test = None
        self._ch_ov_selected_idx = 0
        self._ch_active_source = None
        self._last_ch_event_src = None
        self._ch_pick_flip_diff = False
        self._ch_flip_diff_idx = 1  
        self._flip_diff_options = [("Easy", 400), ("Medium", 300), ("Difficult", 200), ("Pro", 100), ("← Back", -1)]
        self._flip_diff_select = None
        self._mini_test_idx = 0
        self._status_overlay_test_idx = 0
        # Transient state flags for the status badge
        self._status_badge_state: str | None = None
        self._status_badge_explicit: tuple[str, str] | None = None
        # Poll timer: updates/hides the status badge based on game state (~2 s interval)
        self._status_badge_timer = QTimer(self)
        self._status_badge_timer.setInterval(2000)
        self._status_badge_timer.timeout.connect(self._poll_status_badge)
        self._status_badge_timer.start()

        self.watcher.start()

        if self.cfg.CLOUD_ENABLED and self.cfg.CLOUD_URL:
            CloudSync.cleanup_legacy_progress(self.cfg)

        self._apply_theme()
        self._check_for_updates()
        self._init_tooltips_main()
        self._init_overlay_tooltips()

        self._refresh_input_bindings()

    def quit_all(self):
        self.cfg.save()
        try:
            if self.tray:
                self.tray.hide()
        except Exception:
            pass
        try:
            if getattr(self, "watcher", None):
                self.watcher.stop()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass
        try:
            QApplication.instance().quit()
        except Exception:
            pass
           

    # ==========================================
    # TAB HELP TEXTS & HELPERS
    # ==========================================
    _TAB_HELP = {
        "dashboard": (
            "<b>🏠 Dashboard</b><br><br>"
            "The Dashboard gives you a quick overview of the watcher status and the latest session information.<br><br>"
            "• <b>System Status</b>: Shows whether the watcher engine is running and VPX is active.<br>"
            "• <b>Session Summary</b>: Overview of the last and current play session including "
            "score, achievements, and cloud status.<br>"
            "• <b>Notifications</b>: System messages and event notifications.<br>"
            "• <b>Quick Actions</b>: Restart the engine, minimize to tray, or quit the application."
        ),
        "player": (
            "<b>👤 Player</b><br><br>"
            "The Player tab shows your level progress and badge collection.<br><br>"
            "• <b>Player Level</b>: Your current level and progress bar based on unlocked achievements. "
            "Reach Prestige 1–5 by unlocking 2000 achievements per star.<br>"
            "• <b>Level Table</b>: All levels from Rookie to VPX Elite with their achievement thresholds.<br>"
            "• <b>Badges</b>: 37 collectible badges earned through gameplay milestones. "
            "Earn badges by unlocking achievements, completing challenges, reaching levels, "
            "accumulating playtime, and more. "
            "Use the <b>Display Badge</b> dropdown to choose which badge icon appears next to "
            "your name on cloud leaderboards."
        ),
        "progress": (
            "<b>📈 Progress</b><br><br>"
            "The Progress tab shows your local achievement progress for each table.<br><br>"
            "• Select a ROM from the dropdown at the top.<br>"
            "• The view lists all available achievements with their current status "
            "(unlocked ✅ / locked 🔒).<br>"
            "• Click an achievement link to see more details.<br>"
            "• Use <b>🔄 Refresh</b> to reload the list."
        ),
        "appearance_overlay": (
            "<b>🖼 Overlay</b><br><br>"
            "The Overlay sub-tab lets you configure the visual style of all overlays.<br><br>"
            "• <b>Style</b>: Choose the font family and base size for the overlays.<br>"
            "• <b>Widget Placement</b>: Position and rotate each overlay window "
            "(Main Overlay, Toast, Challenge Menu, Timers &amp; Counters, System Notifications, Heat Bar, Status Overlay).<br>"
            "• <b>Switch All Portrait ↔ Landscape</b>: Use the orange button at the top of the "
            "Widget Placement section to toggle <i>all</i> overlay orientations between Portrait and "
            "Landscape mode in one click.<br>"
            "• Use <b>Place</b> to open a positioning window and <b>Test</b> to preview "
            "the overlay.<br>"
            "• <b>Overlay Pages</b>: Enable or disable individual pages of the main stats overlay "
            "(Pages 2–5). Page 1 (Highlights & Score) is always active. "
            "Disabled pages are skipped when cycling through the overlay with the navigation hotkeys."
        ),
        "appearance_theme": (
            "<b>🎨 Theme</b><br><br>"
            "Customize the visual appearance of the app and overlays.<br><br>"
            "• <b>Active Theme</b>: Select a theme from the dropdown and click <b>Apply Theme</b> to switch.<br>"
            "• <b>Color Preview</b>: Shows the four main colors of the selected theme "
            "(Primary, Accent, Border, Background).<br>"
            "• <b>Overlay Preview / Test</b>: Preview each overlay with the current theme. "
            "Click <b>Test</b> to open a live preview.<br>"
            "• <b>Available Themes</b>: Browse all 15 built-in themes with their color schemes and descriptions.<br><br>"
            "Theme changes affect the main application window, all overlay windows, achievement toasts, "
            "and challenge UI elements. The default theme is <b>Neon Blue</b> (cyan + orange)."
        ),
        "appearance_sound": (
            "<b>🔊 Sound</b><br><br>"
            "Configure sound effects for overlay events.<br><br>"
            "• <b>Enable Sound Effects</b>: Master toggle to enable or disable all sounds.<br>"
            "• <b>Volume</b>: Adjust the global volume for all sound effects (0–100%).<br>"
            "• <b>Sound Pack</b>: Choose between different sound packs (e.g. Zaptron, Retro).<br><br>"
            "<b>Events:</b><br>"
            "Each event can be individually enabled or disabled. Click the ▶ button to preview the sound.<br><br>"
            "• <b>Achievement Unlock</b>: Plays when a new achievement is earned.<br>"
            "• <b>Level Up</b>: Plays when your player level increases.<br>"
            "• <b>Challenge Start</b>: Plays when a challenge begins.<br>"
            "• <b>Challenge End</b>: Plays when a challenge finishes.<br>"
            "• <b>Overlay Open</b>: Plays when the stats overlay opens.<br>"
            "• <b>Overlay Close</b>: Plays when the stats overlay closes."
        ),
        "available_maps": (
            "<b>📚 Available Maps</b><br><br>"
            "This tab lists all known tables from the cloud index and your local VPX installation.<br><br>"
            "• <b>Search</b>: Filter by table name or ROM name.<br>"
            "• <b>🎯 Local tables with nvram map</b>: Show only locally installed tables that have an NVRAM mapping.<br>"
            "• <b>⚡ Auto-Match All</b>: Automatically assign VPS-IDs to all local ROMs by matching table names, authors and ROM files against the VPS database.<br>"
            "• <b>🔄 Load List</b>: Scan your tables directory and refresh the list.<br><br>"
            "<b>Columns:</b><br>"
            "• <b>Table Name</b>: Display name of the table.<br>"
            "• <b>ROM</b>: The ROM identifier used by VPinMAME.<br>"
            "• <b>NVRAM Map</b>: ✅ if an NVRAM mapping file exists for this ROM, ❌ if not.<br>"
            "• <b>Local</b>: 🟠 if a matching .vpx file was found in your tables directory.<br>"
            "• <b>VPS-ID</b>: The linked Virtual Pinball Spreadsheet ID (if assigned).<br>"
            "• <b>Author</b>: Table author(s) extracted from the .vpx file metadata.<br>"
            "• <b>+</b>: Detail button — opens VPS info dialog to view or assign VPS-ID."
        ),
        "controls": (
            "<b>🕹️ Controls</b><br><br>"
            "The Controls tab lets you configure hotkeys and input bindings for the overlay and challenges.<br><br>"
            "• <b>Show/Hide Stats Overlay</b>: Bind a keyboard key or joystick button to toggle the stats overlay.<br>"
            "• <b>Challenge Action / Start</b>: Bind a key or button to start or trigger a challenge action.<br>"
            "• <b>Challenge Left / Right</b>: Bind keys or buttons for left/right challenge navigation.<br>"
            "• Select <b>keyboard</b> or <b>joystick</b> as the input source for each binding, then click <b>Bind…</b> and press your desired key or button.<br>"
            "• <b>AI Voice Volume</b>: Adjust the volume of spoken announcements during challenges.<br>"
            "• <b>Mute</b>: Silence all voice announcements."
        ),
        "cloud": (
            "<b>☁️ Cloud</b><br><br>"
            "The Cloud tab lets you browse the global leaderboard stored in the cloud.<br><br>"
            "• <b>Category</b>: Choose between Achievement Progress, Timed Challenge, Flip Challenge, or Heat Challenge.<br>"
            "• <b>ROM</b>: Enter the ROM name of the table you want to look up (e.g. <i>afm_113b</i>).<br>"
            "• Click <b>Fetch Highscores ☁️</b> to load the leaderboard for that ROM."
        ),
        "system_general": (
            "<b>⚙️ General</b><br><br>"
            "The General sub-tab is where you manage your player profile, cloud sync, performance settings, "
            "and feedback.<br><br>"
            "• <b>Player Profile</b>: Set your display name and 4-character player ID. "
            "The player ID is required for cloud sync and data recovery — keep it safe!<br>"
            "• <b>Cloud Sync</b>: Enable cloud synchronisation and automatic progress backup.<br>"
            "• <b>Performance &amp; Animations</b>: Enable or disable overlay animations individually, "
            "or activate Low Performance Mode to disable all animations at once.<br>"
            "• <b>Feedback</b>: Report bugs or suggestions directly from here."
        ),
        "system_maintenance": (
            "<b>🔧 Maintenance</b><br><br>"
            "The Maintenance sub-tab lets you manage directories and perform maintenance operations.<br><br>"
            "• <b>Directory Setup</b>: Configure paths for BASE, NVRAM, and tables directories.<br>"
            "• <b>Maintenance</b>: Repair data folders, force the map cache, update databases, "
            "or install an app update."
        ),
        "stats": (
            "<b>📊 Records &amp; Stats</b><br><br>"
            "The Records &amp; Stats tab gives you an overview of high scores and statistics.<br><br>"
            "• <b>🌍 Global NVRAM Dumps</b>: All saved NVRAM scores for the selected table "
            "across all players.<br>"
            "• <b>👤 Player Session Deltas</b>: Your personal score changes per session.<br>"
            "• <b>⚔️ Challenge Leaderboards</b>: Rankings from the latest challenge results."
        ),
    }

    def _add_tab_help_button(self, layout, help_key: str):
        """Adds a help button (❓) anchored to the bottom-right of the given layout."""
        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("❓")
        btn.setFixedSize(28, 28)
        btn.setToolTip("Show help for this tab")
        btn.setStyleSheet(
            "QPushButton { background: #1a1a1a; color: #FF7F00; border: 1px solid #FF7F00; "
            "border-radius: 14px; font-size: 11pt; font-weight: bold; padding: 0; }"
            "QPushButton:hover { background: #FF7F00; color: #000; }"
        )
        btn.clicked.connect(lambda: self._show_tab_help(help_key))
        row.addWidget(btn)
        layout.addLayout(row)

    def _show_tab_help(self, help_key: str):
        """Displays a tab-specific help dialog."""
        text = self._TAB_HELP.get(help_key, "No help available.")
        box = QMessageBox(self)
        box.setWindowTitle("Help")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Information)
        box.exec()

    def _show_cloud_rules(self):
        """Displays the Cloud Leaderboard rules dialog."""
        text = (
            "<b>📜 Cloud Leaderboard – Rules</b><br><br>"
            "The Cloud Leaderboards are a shared ranking of all players. "
            "To keep them fair and reliable, the following rules apply:<br><br>"

            "<b>1. Mapping Is Mandatory</b><br>"
            "Only tables that are correctly mapped to a VPS-ID can upload scores to the cloud. "
            "<b>No mapping → no upload → no leaderboard entry.</b> "
            "Make sure your tables show a green checkmark (✅) in the Available Maps list.<br><br>"

            "<b>2. Player Profile Required</b><br>"
            "Your player name must not be empty or set to the default \"Player\". "
            "You also need a valid 4-character Player ID. "
            "Without these, all uploads will be blocked.<br><br>"

            "<b>3. Cloud Sync Must Be Enabled</b><br>"
            "Cloud Sync must be turned on in the System tab, otherwise no data will be transmitted.<br><br>"

            "<b>4. Anti-Cheat &amp; Validation</b><br>"
            "Every upload is validated server-side. Submissions can receive the following status:<br>"
            "• 🟢 <b>Accepted</b> – All good, score counts on the leaderboard<br>"
            "• 🟠 <b>Flagged</b> – Suspicious, held for manual review (not visible on the leaderboard until cleared)<br>"
            "• 🔴 <b>Rejected</b> – Invalid (missing data, duplicate, outdated version, etc.)<br><br>"

            "<b>5. Keep Your Watcher Version Up To Date</b><br>"
            "Outdated Watcher versions will be rejected by the server. Always keep the app updated.<br><br>"

            "<b>6. Fair Play</b><br>"
            "Manipulated scores, impossible results, or spam uploads are automatically detected and blocked.<br><br>"

            "<b>⚠️ In Summary:</b><br>"
            "No Mapping + No Profile + No Cloud Sync = <b>No place on the Leaderboard.</b><br>"
            "Keep your tables mapped, your profile complete, and the app up to date – "
            "then nothing stands in the way of your participation! 🏆"
        )
        box = QMessageBox(self)
        box.setWindowTitle("📜 Cloud Leaderboard Rules")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Information)
        box.exec()

    # ==========================================
    # TAB 3: CONTROLS
    # ==========================================
    def _build_tab_controls(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_inputs = QGroupBox("Input Bindings & Hotkeys")
        lay_inputs = QGridLayout(grp_inputs)
        
        self.cmb_toggle_src = QComboBox(); self.cmb_toggle_src.addItems(["keyboard", "joystick"]); self.cmb_toggle_src.setCurrentText(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")); self.cmb_toggle_src.currentTextChanged.connect(self._on_toggle_source_changed)
        self.btn_bind_toggle = QPushButton("Bind..."); self.btn_bind_toggle.clicked.connect(self._on_bind_toggle_clicked)
        self.lbl_toggle_binding = QLabel(self._toggle_binding_label_text())
        
        self.cmb_ch_hotkey_src = QComboBox(); self.cmb_ch_hotkey_src.addItems(["keyboard", "joystick"]); self.cmb_ch_hotkey_src.setCurrentText(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")); self.cmb_ch_hotkey_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("hotkey", s))
        self.btn_ch_hotkey_bind = QPushButton("Bind..."); self.btn_ch_hotkey_bind.clicked.connect(lambda: self._on_bind_ch_clicked("hotkey"))
        self.lbl_ch_hotkey_binding = QLabel(self._challenge_binding_label_text("hotkey"))

        self.cmb_ch_left_src = QComboBox(); self.cmb_ch_left_src.addItems(["keyboard", "joystick"]); self.cmb_ch_left_src.setCurrentText(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")); self.cmb_ch_left_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("left", s))
        self.btn_ch_left_bind = QPushButton("Bind..."); self.btn_ch_left_bind.clicked.connect(lambda: self._on_bind_ch_clicked("left"))
        self.lbl_ch_left_binding = QLabel(self._challenge_binding_label_text("left"))

        self.cmb_ch_right_src = QComboBox(); self.cmb_ch_right_src.addItems(["keyboard", "joystick"]); self.cmb_ch_right_src.setCurrentText(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")); self.cmb_ch_right_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("right", s))
        self.btn_ch_right_bind = QPushButton("Bind..."); self.btn_ch_right_bind.clicked.connect(lambda: self._on_bind_ch_clicked("right"))
        self.lbl_ch_right_binding = QLabel(self._challenge_binding_label_text("right"))

        lay_inputs.addWidget(QLabel("<b>Show/Hide Stats Overlay:</b>"), 0, 0); lay_inputs.addWidget(self.cmb_toggle_src, 0, 1); lay_inputs.addWidget(self.btn_bind_toggle, 0, 2); lay_inputs.addWidget(self.lbl_toggle_binding, 0, 3)
        lay_inputs.addWidget(QLabel("<hr>"), 1, 0, 1, 4)
        lay_inputs.addWidget(QLabel("<b>Challenge Action / Start:</b>"), 2, 0); lay_inputs.addWidget(self.cmb_ch_hotkey_src, 2, 1); lay_inputs.addWidget(self.btn_ch_hotkey_bind, 2, 2); lay_inputs.addWidget(self.lbl_ch_hotkey_binding, 2, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Left:</b>"), 3, 0); lay_inputs.addWidget(self.cmb_ch_left_src, 3, 1); lay_inputs.addWidget(self.btn_ch_left_bind, 3, 2); lay_inputs.addWidget(self.lbl_ch_left_binding, 3, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Right:</b>"), 4, 0); lay_inputs.addWidget(self.cmb_ch_right_src, 4, 1); lay_inputs.addWidget(self.btn_ch_right_bind, 4, 2); lay_inputs.addWidget(self.lbl_ch_right_binding, 4, 3)
        lay_inputs.setColumnStretch(3, 1); layout.addWidget(grp_inputs)

        grp_voice = QGroupBox("Voice & Audio")
        lay_voice = QVBoxLayout(grp_voice)
        row_v1 = QHBoxLayout(); row_v1.addWidget(QLabel("AI Voice Volume (Challenges):"))
        self.sld_ch_volume = QSlider(Qt.Orientation.Horizontal); self.sld_ch_volume.setRange(0, 100); self.sld_ch_volume.setValue(int(self.cfg.OVERLAY.get("challenges_voice_volume", 80))); self.sld_ch_volume.valueChanged.connect(self._on_ch_volume_changed)
        row_v1.addWidget(self.sld_ch_volume); self.lbl_ch_volume = QLabel(f"{self.sld_ch_volume.value()}%"); row_v1.addWidget(self.lbl_ch_volume)
        self.chk_ch_voice_mute = QCheckBox("Mute all spoken announcements"); self.chk_ch_voice_mute.setChecked(bool(self.cfg.OVERLAY.get("challenges_voice_mute", False))); self.chk_ch_voice_mute.stateChanged.connect(self._on_ch_mute_toggled)
        lay_voice.addLayout(row_v1); lay_voice.addWidget(self.chk_ch_voice_mute); layout.addWidget(grp_voice)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "controls")
        self.main_tabs.addTab(tab, "🕹️ Controls")

    def _build_tab_available_maps(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp = QGroupBox("Supported Tables (from Cloud/Index + Local Scan)")
        lay = QVBoxLayout(grp)

        # Toolbar row
        row = QHBoxLayout()
        self.txt_map_search = QLineEdit()
        self.txt_map_search.setPlaceholderText("🔍 Search Table or ROM...")
        self.txt_map_search.textChanged.connect(self._filter_available_maps)
        self._map_search_completer_model = QStringListModel([], self)
        self._map_search_completer = QCompleter(self._map_search_completer_model, self)
        self._map_search_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._map_search_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._map_search_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._map_search_completer.setMaxVisibleItems(12)
        self._map_search_completer.popup().setStyleSheet(
            "QListView {"
            "  background: #222; color: #e0e0e0;"
            "  border: 1px solid #FF7F00;"
            "  selection-background-color: #FF7F00;"
            "  selection-color: #000;"
            "  font-size: 10pt;"
            "}"
        )
        self.txt_map_search.setCompleter(self._map_search_completer)
        row.addWidget(self.txt_map_search)

        btn_refresh = QPushButton("🔄 Load List")
        btn_refresh.setStyleSheet("background:#FF7F00; color:black; font-weight:bold;")
        btn_refresh.clicked.connect(self._refresh_available_maps)
        row.addWidget(btn_refresh)

        self.btn_nvram_filter = QPushButton("🎯 Local tables with nvram map")
        self.btn_nvram_filter.setCheckable(True)
        self.btn_nvram_filter.setChecked(False)
        self.btn_nvram_filter.setStyleSheet(
            "QPushButton {background:#222; color:#FF7F00; border:1px solid #FF7F00;} "
            "QPushButton:checked {background:#3D2600; color:#FF7F00; border:1px solid #FF7F00; font-weight:bold;}"
        )
        self.btn_nvram_filter.toggled.connect(self._filter_available_maps)
        row.addWidget(self.btn_nvram_filter)

        btn_auto = QPushButton("⚡ Auto-Match All")
        btn_auto.setStyleSheet("background:#003333; color:#00E5FF; border:1px solid #00E5FF;")
        btn_auto.clicked.connect(self._on_vps_auto_match_all)
        row.addWidget(btn_auto)

        lay.addLayout(row)

        # Legend bar
        lbl_legend = QLabel(
            "Legend:  ✅ = NVRAM Map available  |  ❌ = No NVRAM Map  |  🟠 = Local .vpx found"
        )
        lbl_legend.setStyleSheet("color:#777; font-size:10px; padding:2px 4px;")
        lay.addWidget(lbl_legend)

        # Table widget
        self.maps_table = QTableWidget(0, 7)
        self.maps_table.setHorizontalHeaderLabels(["Table Name", "ROM", "NVRAM Map", "Local", "VPS-ID", "Author", "+"])
        self.maps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.maps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.maps_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.maps_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.maps_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.maps_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.maps_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.maps_table.setColumnWidth(6, 36)
        self.maps_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.maps_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.maps_table.setStyleSheet(
            "QTableWidget {background:#111; color:#DDD; gridline-color:#333;} "
            "QHeaderView::section {background:#1a1a1a; color:#FF7F00; padding:4px; border-bottom:2px solid #555;} "
            "QTableWidget::item:selected {background:#003D00;}"
        )
        lay.addWidget(self.maps_table)

        layout.addWidget(grp)

        row = QHBoxLayout()
        row.addStretch(1)

        btn_rules = QPushButton("📜 Cloud Rules")
        btn_rules.setFixedSize(140, 28)
        btn_rules.setToolTip("Show Cloud Leaderboard rules")
        btn_rules.setStyleSheet(
            "QPushButton { background: #FF3B30; color: #FFFFFF; border: 1px solid #FF3B30; "
            "border-radius: 14px; font-size: 10pt; font-weight: bold; padding: 0 8px; }"
            "QPushButton:hover { background: #CC2F27; color: #FFF; }"
        )
        btn_rules.clicked.connect(self._show_cloud_rules)
        row.addWidget(btn_rules)

        btn_help = QPushButton("❓")
        btn_help.setFixedSize(28, 28)
        btn_help.setToolTip("Show help for this tab")
        btn_help.setStyleSheet(
            "QPushButton { background: #1a1a1a; color: #FF7F00; border: 1px solid #FF7F00; "
            "border-radius: 14px; font-size: 11pt; font-weight: bold; padding: 0; }"
            "QPushButton:hover { background: #FF7F00; color: #000; }"
        )
        btn_help.clicked.connect(lambda: self._show_tab_help("available_maps"))
        row.addWidget(btn_help)

        layout.addLayout(row)
        self.main_tabs.addTab(tab, "📚 Available Maps")
        # Cache: list of dicts {rom, title, has_map, is_local, vps_id}
        self._all_maps_cache = []

        # Load persisted cache from disk on startup
        cache_path = os.path.join(self.cfg.BASE, "tools", "available_maps_cache.json")
        try:
            if os.path.isfile(cache_path):
                with open(cache_path, "r", encoding="utf-8") as _f:
                    _data = json.load(_f)
                if isinstance(_data, list):
                    self._all_maps_cache = _data
                    self._filter_available_maps()
                    self._update_map_search_completer()
                    self._update_cloud_rom_completer()
        except Exception:
            pass

    def _refresh_available_maps(self):
        # Cancel any previously running worker
        if hasattr(self, "_maps_worker") and self._maps_worker and self._maps_worker.isRunning():
            self._maps_worker.cancel()
            self._maps_worker.wait()

        self.maps_table.setRowCount(0)
        self.maps_table.setRowCount(1)
        info_item = QTableWidgetItem("⏳ Loading… Please wait.")
        info_item.setForeground(QColor("#00E5FF"))
        self.maps_table.setItem(0, 0, info_item)

        self._maps_progress_dlg = QProgressDialog("Scanning tables…", "Cancel", 0, 0, self)
        self._maps_progress_dlg.setWindowTitle("🔄 Load List")
        self._maps_progress_dlg.setMinimumDuration(0)
        self._maps_progress_dlg.setModal(True)
        self._maps_progress_dlg.show()
        QApplication.processEvents()

        self._maps_worker = _AvailableMapsWorker(self.cfg, self.watcher, self)
        self._maps_progress_dlg.canceled.connect(self._maps_worker.cancel)

        def _on_progress(current, total, fname):
            if total:
                self._maps_progress_dlg.setMaximum(total)
                self._maps_progress_dlg.setValue(current)
                self._maps_progress_dlg.setLabelText(
                    f"Scanning: {fname}\n({current}/{total} files)"
                )

        def _on_finished(entries):
            self._maps_progress_dlg.close()
            self._all_maps_cache = entries
            # Persist cache to disk
            cache_path = os.path.join(self.cfg.BASE, "tools", "available_maps_cache.json")
            try:
                ensure_dir(os.path.dirname(cache_path))
                with open(cache_path, "w", encoding="utf-8") as _f:
                    json.dump(entries, _f)
            except Exception:
                pass
            self._filter_available_maps()
            self._update_map_search_completer()
            self._update_cloud_rom_completer()
            # Notify about ROMs missing a VPS-ID
            try:
                missing_roms = [
                    e["rom"] for e in entries
                    if e.get("is_local") and e.get("has_map") and not e.get("vps_id", "")
                ]
                self._add_vps_missing_notification(len(missing_roms), missing_roms)
            except Exception:
                pass

        self._maps_worker.progress.connect(_on_progress)
        self._maps_worker.finished.connect(_on_finished)
        self._maps_worker.start()

    def _filter_available_maps(self):
        query = self.txt_map_search.text().lower()
        nvram_only = self.btn_nvram_filter.isChecked()

        if not self._all_maps_cache:
            self.maps_table.setRowCount(1)
            item = QTableWidgetItem("(Click '🔄 Load List' to see supported tables)")
            item.setForeground(QColor("#888"))
            self.maps_table.setItem(0, 0, item)
            return

        filtered = []
        for entry in self._all_maps_cache:
            rom = entry["rom"]
            title = entry["title"]
            if query and query not in rom.lower() and query not in title.lower():
                continue
            if nvram_only and not (entry["has_map"] and entry["is_local"]):
                continue
            filtered.append(entry)
            if len(filtered) > 800:
                break

        self.maps_table.setRowCount(0)
        self.maps_table.setRowCount(len(filtered))

        # Re-load mapping to get fresh VPS-IDs
        mapping = _load_vps_mapping(self.cfg)
        # Pre-load VPS DB once for author lookups
        _vpsdb_tables = _load_vpsdb(self.cfg) or []

        for row, entry in enumerate(filtered):
            rom = entry["rom"]
            title = entry["title"]
            has_map = entry["has_map"]
            is_local = entry["is_local"]
            vps_id = mapping.get(rom, "")

            def _make_item(text, color=None, align=None):
                it = QTableWidgetItem(text)
                if color:
                    it.setForeground(QColor(color))
                if align:
                    it.setTextAlignment(align)
                return it

            self.maps_table.setItem(row, 0, _make_item(title))
            self.maps_table.setItem(row, 1, _make_item(rom, "#888"))
            self.maps_table.setItem(row, 2, _make_item("✅" if has_map else "❌",
                                                        "#00E5FF" if has_map else "#555",
                                                        Qt.AlignmentFlag.AlignCenter))
            self.maps_table.setItem(row, 3, _make_item("🟠" if is_local else "",
                                                        align=Qt.AlignmentFlag.AlignCenter))
            self.maps_table.setItem(row, 4, _make_item(vps_id, "#00E5FF" if vps_id else "#444"))

            # Author column: look up authors from VPS DB when a VPS-ID is assigned
            author_text = ""
            if vps_id:
                try:
                    for t in _vpsdb_tables:
                        if t.get("id") == vps_id:
                            # Table-level match: no specific tableFile, no authors
                            break
                        for tf in (t.get("tableFiles") or []):
                            if tf.get("id") == vps_id:
                                author_text = ", ".join(tf.get("authors") or [])
                                break
                        else:
                            continue
                        break
                except Exception:
                    author_text = ""
            self.maps_table.setItem(row, 5, _make_item(author_text, "#AAA" if author_text else "#444"))

            # + picker button (only for entries with an NVRAM map)
            if has_map:
                btn = QPushButton("+")
                btn.setFixedSize(30, 28)
                btn.setStyleSheet(
                    "QPushButton {background:#2a1800; color:#FF7F00; border:1px solid #FF7F00; font-weight:bold; font-size:16px;} "
                    "QPushButton:hover {background:#4a2e00;}"
                )
                btn.clicked.connect(lambda checked, r=rom, t=title: self._on_vps_picker_clicked(r, t))
                self.maps_table.setCellWidget(row, 6, btn)

    def _on_vps_picker_clicked(self, rom: str, title: str):
        """Open the VPS picker dialog for the given ROM."""
        tables = _load_vpsdb(self.cfg)
        if tables is None:
            QMessageBox.warning(self, "VPS-DB not available",
                                "Could not load vpsdb.json.\nCheck your internet connection and try again.")
            return

        dlg = VpsPickerDialog(self.cfg, tables, rom, title, parent=self)
        result = dlg.exec()

        mapping = _load_vps_mapping(self.cfg)
        if result == QDialog.DialogCode.Accepted and dlg.selected_table:
            tf = dlg.selected_table_file or {}
            mapping[rom] = tf.get("id", "") or dlg.selected_table.get("id", "")
            _save_vps_mapping(self.cfg, mapping)
            self._cloud_upload_vps_mapping()
        elif result == 2:  # "Remove assignment"
            mapping.pop(rom, None)
            _save_vps_mapping(self.cfg, mapping)
            self._cloud_upload_vps_mapping()

        # Update cache entry
        for entry in self._all_maps_cache:
            if entry["rom"] == rom:
                entry["vps_id"] = mapping.get(rom, "")
                break

        self._filter_available_maps()

    def _update_map_search_completer(self):
        """Update the Available Maps tab search autocomplete suggestions from the maps cache."""
        cache = getattr(self, '_all_maps_cache', None) or []
        suggestions = []
        seen = set()
        for entry in cache:
            rom = entry.get("rom", "")
            title = entry.get("title", "")
            if rom and rom not in seen:
                seen.add(rom)
                suggestions.append(rom)
            if title and title not in seen:
                seen.add(title)
                suggestions.append(title)
        suggestions.sort(key=str.lower)
        if hasattr(self, '_map_search_completer_model'):
            self._map_search_completer_model.setStringList(suggestions)

    def _update_cloud_rom_completer(self):
        """Update the Cloud tab ROM search autocomplete suggestions from the maps cache."""
        cache = getattr(self, '_all_maps_cache', None) or []
        suggestions = []
        seen = set()
        for entry in cache:
            rom = entry.get("rom", "")
            if rom and rom not in seen:
                seen.add(rom)
                suggestions.append(rom)
        suggestions.sort(key=str.lower)
        # Also add ROMNAMES keys and table titles for full name search
        try:
            romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
            extra = set(romnames.keys()) | set(romnames.values())
            all_items = sorted(set(suggestions) | extra, key=str.lower)
        except Exception:
            all_items = suggestions
        if hasattr(self, '_cloud_rom_completer_model'):
            self._cloud_rom_completer_model.setStringList(all_items)

    def _on_vps_auto_match_all(self):
        """Attempt automatic VPS match for all local ROMs that have an NVRAM map."""
        # Only process local entries WITH nvram map
        local_entries = [e for e in self._all_maps_cache if e.get("is_local") and e.get("has_map")]
        if not local_entries:
            QMessageBox.information(self, "Auto-Match",
                                    "No local ROMs with NVRAM map found.\n"
                                    "Make sure tables are loaded and have NVRAM maps (click '🔄 Load List' first).")
            return

        tables = _load_vpsdb(self.cfg)
        if tables is None:
            QMessageBox.warning(self, "VPS-DB not available",
                                "Could not load vpsdb.json.\nCheck your internet connection and try again.")
            return

        mapping = _load_vps_mapping(self.cfg)

        progress = QProgressDialog("Running Auto-Match…", "Cancel", 0, len(local_entries), self)
        progress.setWindowTitle("⚡ Auto-Match All")
        progress.setMinimumDuration(0)

        matched_rom = 0
        matched_author_name = 0
        matched_name = 0
        matched_info_name = 0
        skipped_existing = 0
        matched_tablefile_id = 0

        def _resolve_id(table: dict, tf: Optional[dict]) -> str:
            if tf:
                tf_id = tf.get("id", "")
                if tf_id:
                    return tf_id
            return table.get("id", "")

        for i, entry in enumerate(local_entries):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            QApplication.processEvents()

            rom = entry["rom"]
            title = entry["title"]
            vpx_path = entry.get("vpx_path", "")

            # Skip if already mapped
            if mapping.get(rom, ""):
                skipped_existing += 1
                continue

            # Get script authors via vpxtool script show
            script_authors = []
            if vpx_path and os.path.isfile(vpx_path):
                try:
                    script_authors = run_vpxtool_get_script_authors(self.cfg, vpx_path)
                except Exception:
                    script_authors = []

            # Get table metadata via vpxtool info show
            vpx_info = {}
            if vpx_path and os.path.isfile(vpx_path):
                try:
                    vpx_info = run_vpxtool_info_show(self.cfg, vpx_path)
                except Exception:
                    vpx_info = {}

            # Merge authors from info show as additional signal (canonical author field)
            info_author = (vpx_info.get("author") or "").strip()
            if info_author:
                info_author_tokens = [
                    t for t in re.split(r"\s+", info_author)
                    if t and "@" not in t and not re.match(r"https?://", t) and not re.search(r"\.\w{2,}$", t)
                ]
                if not info_author_tokens:
                    parts = info_author.split()
                    info_author_tokens = [parts[0]] if parts else []
                # Add info_author tokens not already present in script_authors
                script_set_lower = {a.lower() for a in script_authors}
                for tok in info_author_tokens:
                    if tok.lower() not in script_set_lower:
                        script_authors.append(tok)
                        script_set_lower.add(tok.lower())

            # Use table_name from vpxtool info show as primary search term if available
            info_table_name = (vpx_info.get("table_name") or "").strip()
            info_version = (vpx_info.get("version") or "").strip()
            search_title = info_table_name if info_table_name else title

            if info_table_name and info_table_name != title:
                log(self.cfg, f"[VPS-MATCH] {rom}: using vpx_info table_name='{info_table_name}' instead of romnames title='{title}'")

            results = _vps_find(tables, search_title, rom)
            # Fallback: if info table_name gave no results but differs from title, try original title
            if not results and info_table_name and info_table_name != title:
                results = _vps_find(tables, title, rom)
            if not results:
                continue

            top = results[0]
            is_rom_match = _table_has_rom(top, rom)
            is_exact_name = (
                _normalize_term(title) == _normalize_term(top.get("name", ""))
            )
            is_author_match = _authors_match(script_authors, top)
            is_info_name_match = bool(
                info_table_name
                and _normalize_term(info_table_name) == _normalize_term(top.get("name", ""))
            )

            # Try to find the exact tableFile via .vpx filename + script authors + version
            vpx_basename = os.path.basename(vpx_path) if vpx_path else ""
            best_table_file = None
            if vpx_basename:
                best_table_file = _find_table_file_by_filename_and_authors(
                    top, vpx_basename, script_authors, info_version
                )

            if is_rom_match:
                matched_rom += 1
            elif is_author_match and (is_exact_name or is_info_name_match):
                matched_author_name += 1
            elif is_exact_name:
                matched_name += 1
            elif is_info_name_match:
                matched_info_name += 1
            else:
                continue

            resolved_id = _resolve_id(top, best_table_file)
            mapping[rom] = resolved_id
            if best_table_file:
                matched_tablefile_id += 1
                log(self.cfg, f"[VPS-MATCH] {rom} → tableFile.id={resolved_id} (via filename+author)")
            else:
                log(self.cfg, f"[VPS-MATCH] {rom} → table.id={resolved_id} (no tableFile match)")

        matched = matched_rom + matched_author_name + matched_name + matched_info_name
        progress.setValue(len(local_entries))
        _save_vps_mapping(self.cfg, mapping)
        self._cloud_upload_vps_mapping()

        # Refresh cache vps_id entries
        for entry in self._all_maps_cache:
            entry["vps_id"] = mapping.get(entry["rom"], "")

        self._filter_available_maps()

        details = []
        if matched_rom:
            details.append(f"{matched_rom} via ROM identifier")
        if matched_author_name:
            details.append(f"{matched_author_name} via author + name")
        if matched_name:
            details.append(f"{matched_name} via exact name")
        if matched_info_name:
            details.append(f"{matched_info_name} via vpx info name")
        if skipped_existing:
            details.append(f"{skipped_existing} already mapped (skipped)")
        match_detail = f" ({', '.join(details)})" if details else ""
        tablefile_line = f"\n  → of which {matched_tablefile_id} matched to exact tableFile version" if matched_tablefile_id else ""
        QMessageBox.information(self, "Auto-Match Complete",
                                f"Auto-match finished.\n{matched} table(s) matched{match_detail}.{tablefile_line}\n\n⚠️ Please review the assignments manually to ensure correctness.")

    def _init_tooltips_main(self):
        def _set_tip(attr: str, tip: str):
            try:
                w = getattr(self, attr, None)
                if w:
                    w.setToolTip(tip)
            except Exception:
                pass
                
        # Dashboard Tab
        _set_tip("btn_restart", "Restarts the background engine (useful if the tracker hangs).")
        _set_tip("btn_quit", "Completely closes the application and stops all background tracking.")
        _set_tip("btn_minimize", "Minimizes the window to the Windows system tray.")
        _set_tip("status_label", "Current status of the background watcher engine.")
        
        # Controls Tab
        _set_tip("cmb_toggle_src", "Choose whether to use a keyboard key or joystick button to show/hide the main overlay.")
        _set_tip("btn_bind_toggle", "Assign the hotkey used to show/hide the main stats overlay.")
        _set_tip("lbl_toggle_binding", "Currently assigned hotkey for the main overlay.")
        _set_tip("cmb_ch_hotkey_src", "Input source for the challenge 'Action/Start' button.")
        _set_tip("btn_ch_hotkey_bind", "Assign the hotkey used to start challenges or select options.")
        _set_tip("lbl_ch_hotkey_binding", "Currently assigned hotkey for challenge actions.")
        _set_tip("cmb_ch_left_src", "Input source for navigating left in Challenge menus.")
        _set_tip("btn_ch_left_bind", "Assign the hotkey used to navigate left in Challenge menus.")
        _set_tip("lbl_ch_left_binding", "Currently assigned left navigation hotkey (used to navigate Challenge menus).")
        _set_tip("cmb_ch_right_src", "Input source for navigating right in Challenge menus.")
        _set_tip("btn_ch_right_bind", "Assign the hotkey used to navigate right in Challenge menus.")
        _set_tip("lbl_ch_right_binding", "Currently assigned right navigation hotkey (used to navigate Challenge menus).")
        _set_tip("sld_ch_volume", "Adjust the volume of the AI voice announcements.")
        _set_tip("chk_ch_voice_mute", "Completely disable spoken voice announcements during challenges.")
        
        # Cloud Tab
        _set_tip("cmb_cloud_category", "Select the leaderboard category you want to view.")
        _set_tip("txt_cloud_rom", "Type the ROM name exactly as it appears in VPX (e.g. afm_113b).")
        _set_tip("btn_cloud_fetch", "Download and display the global highscores from the cloud.")
        
        # System Tab
        _set_tip("txt_player_name", "Enter your display name (used for local records and leaderboards).")
        _set_tip("txt_player_id", "Your unique 4-character ID. Keep this safe to restore your cloud progress after a reinstall!")
        _set_tip("chk_cloud_enabled", "Turn automatic cloud sync for scores and progress on or off.")
        _set_tip("chk_cloud_backup", "Enable automatic backup of your achievement progress, scores, and VPS mapping to the cloud.")
        _set_tip("btn_repair", "Recreates missing folders and downloads the base database if corrupted.")
        _set_tip("btn_prefetch", "Forces a background download of all missing NVRAM maps from the internet.")
        _set_tip("base_label", "Current base directory for achievements data.")
        _set_tip("btn_base", "Change the main folder where achievement data and history is saved.")
        _set_tip("nvram_label", "Current NVRAM folder path.")
        _set_tip("btn_nvram", "Change the folder where VPinMAME stores its .nv files.")
        _set_tip("tables_label", "Current VPX tables folder path (optional).")
        _set_tip("btn_tables", "Change the folder where Visual Pinball tables (.vpx) are located.")

    def _init_overlay_tooltips(self):
        tips = {
            # Appearance Tab - Global Styling
            "cmb_font_family": "Select the font style for all text in the overlays.",
            "spn_font_size": "Adjust the base font size (automatically scales headers and body text).",
            "sld_scale": "Scale the main overlay up or down in overall size (percentage).",
            "lbl_scale": "Current overlay scale in percent.",
            
            # Appearance Tab - Main Stats Overlay
            "chk_portrait": "Rotate the main overlay 90 degrees for portrait/cabinet screens.",
            "chk_portrait_ccw": "Rotate counter-clockwise (instead of clockwise) for portrait mode.",
            "btn_overlay_place": "Open a draggable window to set and save the position of the main overlay.",
            "btn_toggle_now": "Instantly show or hide the main overlay for testing.",
            "btn_hide": "Forcefully hide the main overlay if it's currently visible.",
            "chk_overlay_auto_close": "Automatically hide the main overlay after 60 seconds of inactivity.",
            
            # Appearance Tab - Achievement Toasts
            "chk_ach_toast_portrait": "Rotate achievement unlock popups for portrait screens.",
            "chk_ach_toast_ccw": "Rotate achievement popups counter-clockwise.",
            "btn_ach_toast_place": "Set and save the screen position for achievement popups.",
            "btn_test_toast": "Trigger a test achievement popup to check your placement.",
            
            # Appearance Tab - Challenge Menu
            "chk_ch_ov_portrait": "Rotate the challenge selection menu for portrait screens.",
            "chk_ch_ov_ccw": "Rotate the challenge selection menu counter-clockwise.",
            "btn_ch_ov_place": "Set and save the screen position for the challenge menu.",
            "btn_ch_ov_test": "Show the challenge selection menu for testing.",
            
            # Appearance Tab - Timers & Counters
            "chk_ch_timer_portrait": "Rotate timers and counters for portrait screens.",
            "chk_ch_timer_ccw": "Rotate timers and counters counter-clockwise.",
            "btn_ch_timer_place": "Set and save the screen position for the countdown timer.",
            "btn_ch_timer_test": "Show a test countdown timer to check your placement.",
            "btn_flip_counter_place": "Set and save the screen position for the flip challenge counter.",
            "btn_flip_counter_test": "Show a test flip counter to check your placement.",
            
            # Appearance Tab - System Notifications (Mini Info Overlay)
            "chk_mini_info_portrait": "Rotate system notifications (errors, warnings, info) for portrait screens.",
            "chk_mini_info_ccw": "Rotate system notifications counter-clockwise.",
            "btn_mini_info_place": "Set and save the screen position for system notifications.",
            "btn_mini_info_test": "Trigger a test notification to check your placement.",
            
            # Appearance Tab - Status Overlay (cloud / leaderboard status)
            "chk_status_overlay_enabled": "Show or hide the Status Overlay for cloud and leaderboard submission feedback.",
            "chk_status_overlay_portrait": "Rotate the Status Overlay 90 degrees for portrait/cabinet screens.",
            "chk_status_overlay_ccw": "Rotate the Status Overlay counter-clockwise.",
            "btn_status_overlay_place": "Set and save the screen position for the Status Overlay.",
            "btn_status_overlay_test": "Trigger a test Status Overlay message to check your placement.",

            # Appearance Tab - Switch All button
            "btn_switch_all_orientation": "Toggle all overlay widgets between Portrait and Landscape mode at once.",
        }
        apply_tooltips(self, tips)
        
    def _init_settings_tooltips(self):
        pass
     
    def _on_ach_toast_custom_toggled(self, state: int):
        use = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_custom"] = bool(use)
        if not use:
            self.cfg.OVERLAY["ach_toast_saved"] = False
        self.cfg.save()

    def _get_icon(self) -> QIcon:
        try:
            p = resource_path("watcher.ico")
            if os.path.isfile(p):
                ic = QIcon(p)
                if not ic.isNull():
                    return ic
        except Exception:
            pass
        try:
            p2 = os.path.join(APP_DIR, "watcher.ico")
            if os.path.isfile(p2):
                ic = QIcon(p2)
                if not ic.isNull():
                    return ic
        except Exception:
            pass

        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        try:
            painter = QPainter(pm)
            painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            painter.setBrush(QColor("#202020"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(1, 1, 30, 30, 6, 6)
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), "AW")
            painter.end()
        except Exception:
            pm.fill(QColor("#202020"))
        return QIcon(pm)

    def _on_portrait_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["portrait_rotate_ccw"] = is_ccw
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_portrait_from_cfg(self.cfg.OVERLAY)
            self.overlay.request_rotation(force=True)
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
            
    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        self.cfg.save()
        try:
            if getattr(self, "tray", None) and self.tray and self.tray.isVisible():
                self.hide()
                event.ignore()
                return
        except Exception:
            pass
        try:
            self._unregister_global_hotkeys()
        except Exception:
            pass
        try:
            self._uninstall_global_keyboard_hook()
        except Exception:
            pass
        try:
            if getattr(self, "watcher", None):
                self.watcher.stop()
        except Exception:
            pass
        event.accept()

    def change_base(self):
        d = QFileDialog.getExistingDirectory(self, "Select BASE directory", self.cfg.BASE)
        if d:
            self.cfg.BASE = d
            self.base_label.setText(f"BASE: {d}")
            self.cfg.save()

    def change_nvram(self):
        d = QFileDialog.getExistingDirectory(self, "Select NVRAM directory", self.cfg.NVRAM_DIR)
        if d:
            self.cfg.NVRAM_DIR = d
            self.nvram_label.setText(f"NVRAM: {d}")
            self.cfg.save()

    def change_tables(self):
        d = QFileDialog.getExistingDirectory(self, "Select TABLES directory", self.cfg.TABLES_DIR)
        if d:
            self.cfg.TABLES_DIR = d
            self.tables_label.setText(f"TABLES (optional): {d}")
            self.cfg.save()
            if hasattr(self, "watcher") and self.watcher and hasattr(self.watcher, "_installed_roms_scan_done"):
                self.watcher._installed_roms_scan_done = False
                self.watcher._installed_roms_scan_cache = {}

    def _refresh_overlay_live(self):
        if not bool(self.cfg.OVERLAY.get("live_updates", False)):
            return
        # Only refresh page 0 (Main Stats); other pages have static content
        if getattr(self, "_overlay_page", 0) != 0:
            return
        try:
            if self.watcher and (self.watcher.game_active or self.watcher._vp_player_visible()):
                try:
                    if self.overlay and self.overlay.isVisible():
                        self.overlay.hide()
                except Exception:
                    pass
                return
        except Exception:
            pass
        if not self.overlay or not self.overlay.isVisible():
            return
        if not self.watcher:
            return
        try:
            import time as _time
            if (_time.monotonic() - getattr(self, "_overlay_last_action", 0.0)) < 0.35:
                return
        except Exception:
            pass
        if getattr(self, "_overlay_busy", False):
            return
        try:
            self._overlay_busy = True

            try:
                self.watcher.force_flush()
            except Exception:
                pass
            
            self._prepare_overlay_sections()
            secs = self._overlay_cycle.get("sections", [])
            if not secs:
                self._hide_overlay()
                self._overlay_cycle = {"sections": [], "idx": -1}
                return
            
            self._show_overlay_section(secs[0])
            
        finally:
            self._overlay_busy = False

    def _has_highlights(self, entry: dict) -> bool:
        h = entry.get("highlights", {}) or {}
        for cat in ("Power", "Precision", "Fun"):
            if h.get(cat):
                return True
        return False

    def _prepare_overlay_sections(self):
        def _played_entry(p: dict) -> bool:
            try:
                if int(p.get("playtime_sec", 0) or 0) > 0:
                    return True
            except Exception:
                pass
            try:
                if int(p.get("score", 0) or 0) > 0:
                    return True
            except Exception:
                pass
            h = p.get("highlights", {}) or {}
            return any(h.get(cat) for cat in ("Power", "Precision", "Fun"))

        sections = []

        # Prefer the in-memory snapshot cache (avoids a disk read race where the
        # file hasn't been flushed yet but the overlay signal has already arrived).
        players_raw = []
        try:
            cached = getattr(self.watcher, "_overlay_snapshot_cache", None)
            if cached and isinstance(cached, dict):
                players_raw = [{
                    "id": 1,
                    "highlights": cached.get("highlights", {}),
                    "playtime_sec": int(cached.get("playtime_sec", 0) or 0),
                    "score": int(cached.get("score", 0) or 0),
                    "title": "Player 1",
                    "player": 1,
                    "rom": cached.get("rom", ""),
                }]
        except Exception:
            pass

        if not players_raw:
            players_raw = read_active_players(self.cfg.BASE)

        combined_players = []
        if players_raw:
            for p in players_raw:
                if not _played_entry(p):
                    continue
                combined_players.append({
                    "id": int(p.get("id", 0)),
                    "highlights": p.get("highlights", {}),
                    "playtime_sec": p.get("playtime_sec", 0),
                    "score": int(p.get("score", 0) or 0),
                    "rom": p.get("rom", ""),
                })
        
        active_ids = [e for e in combined_players if 1 <= int(e.get("id", 0)) <= 4]
        is_single_player = (len(active_ids) <= 1)
        if is_single_player and combined_players:
            p1 = next((e for e in combined_players if int(e.get("id", 0)) == 1), None)
            combined_players = [p1] if p1 else [combined_players[0]]

        if combined_players:
            # --- Hole die Deltas für unsere einzige Seite ---
            active_deltas = {}
            try:
                live_deltas = self.watcher.players.get(1, {}).get("session_deltas", {})
                for k, v in live_deltas.items():
                    if int(v) > 0:
                        active_deltas[k] = int(v)
            except Exception:
                pass

            summary_rom = ""
            try:
                import json
                summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        summary_rom = data.get("rom", "")
                        if not active_deltas:
                            saved_deltas = data.get("players", [])[0].get("deltas", {})
                            for k, v in saved_deltas.items():
                                if int(v) > 0:
                                    active_deltas[k] = int(v)
            except Exception:
                pass

            for p in combined_players:
                p["deltas"] = active_deltas

            resolved_rom = (
                getattr(self.watcher, "current_rom", "")
                or next(iter(combined_players), {}).get("rom", "")
                or summary_rom
            )
            sections.append({
                "kind": "combined_players",
                "players": combined_players,
                "title": "Session Overview",
                "rom_name": resolved_rom,
            })
            
        self._overlay_cycle = {"sections": sections, "idx": -1}
        
    def _show_overlay_section(self, payload: dict):
        from PyQt6.QtWidgets import QApplication
        self._ensure_overlay()
        already_visible = self.overlay.isVisible()
        kind = str(payload.get("kind", "")).lower()
        title = str(payload.get("title", "") or "").strip()

        def _update_and_show(update_cb):
            """Apply content update and show/raise the overlay as needed."""
            if already_visible:
                # Overlay is already on screen: use a smooth transition instead
                # of a hard content swap, which would cause a visible flash.
                self.overlay.transition_to(update_cb)
            else:
                update_cb()
                # Allow Qt to process any pending layout/paint events so that
                # font metrics are fully initialized before we measure geometry.
                QApplication.processEvents()
                # Re-run layout positions after processEvents() so title height
                # and body positions are computed with now-correct font metrics.
                # Using _layout_positions_for() directly avoids scheduling an
                # extra rotation timer (which _layout_positions() would do for
                # portrait mode).  This prevents the first-open blink/distortion
                # where sizeHint() returned stale values before the first paint.
                self.overlay._layout_positions_for(
                    self.overlay.width(), self.overlay.height()
                )
                if self.overlay.portrait_mode:
                    self.overlay._apply_rotation_snapshot(force=True)
                else:
                    # Ensure live (unrotated) widgets are explicitly visible
                    # before show() so no blank flash occurs on first open.
                    self.overlay._show_live_unrotated()
                # Prevent showEvent from re-triggering layout/rotation and
                # causing additional blink frames.
                self.overlay._ensuring = True
                try:
                    self.overlay.show()
                    self.overlay.raise_()
                finally:
                    self.overlay._ensuring = False
            self._start_overlay_auto_close_timer()
            try:
                self.overlay.set_nav_arrows(True)
            except Exception:
                pass

        if kind == "combined_players":
            combined = {"players": payload.get("players", []), "rom_name": payload.get("rom_name", "")}
            _update_and_show(lambda: self.overlay.set_combined(
                combined, session_title=title or "Active Player Highlights"))
            return
        if kind == "html":
            html = payload.get("html", "") or "<div>-</div>"
            _update_and_show(lambda: self.overlay.set_html(html, session_title=title))
            return
        combined = {"players": [payload]}
        title2 = f"Highlights – {payload.get('title','')}".strip()
        _update_and_show(lambda: self.overlay.set_combined(combined, session_title=title2))

    # ------------------------------------------------------------------
    # Overlay page navigation (4 pages cycled via challenge_left/right)
    # ------------------------------------------------------------------

    def _navigate_overlay_page(self, direction: int):
        """Cycle to the next/previous overlay page, skipping disabled pages."""
        ov = self.cfg.OVERLAY or {}
        # Build list of enabled page indices (page 0 is always enabled)
        enabled_pages = [0]
        if ov.get("overlay_page2_enabled", True):
            enabled_pages.append(1)
        if ov.get("overlay_page3_enabled", True):
            enabled_pages.append(2)
        if ov.get("overlay_page4_enabled", True):
            enabled_pages.append(3)
        if ov.get("overlay_page5_enabled", True):
            enabled_pages.append(4)

        if not enabled_pages:
            enabled_pages = [0]

        current = int(getattr(self, "_overlay_page", 0))
        if current in enabled_pages:
            current_idx = enabled_pages.index(current)
        else:
            current_idx = 0

        new_idx = (current_idx + direction) % len(enabled_pages)
        self._overlay_page = enabled_pages[new_idx]

        try:
            self._show_overlay_page(self._overlay_page)
        except Exception as e:
            try:
                from watcher_core import log
                log(self.cfg, f"[OVERLAY] page navigation failed: {e}", "WARN")
            except Exception:
                pass

    def _show_page_with_transition(self, content_cb):
        """Show/update the overlay using *content_cb*.

        When the overlay is already visible a slide+fade transition is used so
        the page change is animated without flickering.  On the first open the
        normal full-show sequence is used (layout, rotation, show/raise).
        Always restarts the auto-close timer and shows navigation arrows.
        """
        from PyQt6.QtWidgets import QApplication
        if self.overlay.isVisible():
            self.overlay.transition_to(content_cb)
        else:
            content_cb()
            QApplication.processEvents()
            if self.overlay.portrait_mode:
                self.overlay._apply_rotation_snapshot(force=True)
            else:
                self.overlay._show_live_unrotated()
            self.overlay._ensuring = True
            try:
                self.overlay.show()
                self.overlay.raise_()
            finally:
                self.overlay._ensuring = False
        self._start_overlay_auto_close_timer()
        try:
            self.overlay.set_nav_arrows(True)
        except Exception:
            pass

    def _show_overlay_page(self, page_idx: int):
        """Show one of the 5 overlay pages."""
        from PyQt6.QtWidgets import QApplication
        self._ensure_overlay()
        if page_idx == 0:
            self._vpc_page5_data = None
            # Page 1: Main Stats (existing combined-players view)
            secs = self._overlay_cycle.get("sections", [])
            if not secs:
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
            if secs:
                self._show_overlay_section(secs[0])
            else:
                self._show_page_with_transition(
                    lambda: self.overlay.set_html(
                        "<div style='text-align:center; color:#888; padding:20px;'>(No session data available)</div>",
                        "Session Overview",
                    )
                )
        elif page_idx == 1:
            self._vpc_page5_data = None
            # Page 2: Local Achievement Progress for last played ROM
            css, header_html, rows = self._overlay_page2_html()
            self._show_page_with_transition(
                lambda: self.overlay.set_html_scrollable(css, header_html, rows, "Achievement Progress")
            )
        elif page_idx == 2:
            self._vpc_page5_data = None
            # Page 3: Local Challenge Leaderboard (1:1 mirror of GUI)
            html = self._overlay_page3_html()
            self._show_page_with_transition(
                lambda: self.overlay.set_html(html, "Challenge Leaderboard")
            )
        elif page_idx == 3:
            self._vpc_page5_data = None
            # Page 4: Cloud Leaderboard (dynamic)
            self._overlay_page4_show()
        elif page_idx == 4:
            # Page 5: VPC Weekly Challenge Leaderboard
            self._overlay_page5_show()

    def _get_last_played_rom(self) -> str:
        """Return the ROM key of the last played session (non-challenge or challenge)."""
        import json as _json
        try:
            summary_path = os.path.join(
                self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json"
            )
            if os.path.isfile(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                rom = str(data.get("rom", "") or "")
                if rom:
                    return rom
        except Exception:
            pass
        try:
            rom = (
                getattr(self.watcher, "current_rom", None)
                or getattr(self.watcher, "_last_logged_rom", None)
            )
            if rom:
                return str(rom)
        except Exception:
            pass
        return ""

    def _get_last_session_context(self) -> dict:
        """Determine what was last played: non-challenge session or a challenge, and return metadata."""
        import json as _json
        from datetime import datetime
        from watcher_core import secure_load_json

        ctx = {"rom": "", "table_name": "", "is_challenge": False, "kind": "", "difficulty": ""}

        # Last non-challenge session from summary
        summary_path = os.path.join(
            self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json"
        )
        last_normal_ts = None
        normal_rom = ""
        normal_table = ""
        try:
            if os.path.isfile(summary_path):
                last_normal_ts = os.path.getmtime(summary_path)
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                normal_rom = str(data.get("rom", "") or "")
                normal_table = str(data.get("table", "") or "")
        except Exception:
            pass

        # Last challenge session from challenge history files
        last_challenge_ts = None
        challenge_rom = ""
        challenge_kind = ""
        challenge_difficulty = ""
        hist_dir = os.path.join(self.cfg.BASE, "session_stats", "challenges", "history")
        try:
            if os.path.isdir(hist_dir):
                latest_item = None
                latest_dt = None
                for fn in os.listdir(hist_dir):
                    if not fn.lower().endswith(".json"):
                        continue
                    fpath = os.path.join(hist_dir, fn)
                    data = secure_load_json(fpath, {"results": []}) or {"results": []}
                    for it in (data.get("results") or []):
                        try:
                            ts = str(it.get("ts", "") or "")
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if dt.tzinfo is not None:
                                dt = dt.astimezone().replace(tzinfo=None)
                            if latest_dt is None or dt > latest_dt:
                                latest_dt = dt
                                latest_item = it
                        except Exception:
                            continue
                if latest_item and latest_dt:
                    last_challenge_ts = latest_dt.timestamp()
                    challenge_rom = str(latest_item.get("rom", "") or "")
                    challenge_kind = str(latest_item.get("kind", "") or "").lower()
                    challenge_difficulty = str(latest_item.get("difficulty", "") or "")
        except Exception:
            pass

        # Pick the more recent context
        if last_challenge_ts is not None and last_normal_ts is not None:
            if last_challenge_ts >= last_normal_ts:
                ctx.update({"rom": challenge_rom, "is_challenge": True,
                            "kind": challenge_kind, "difficulty": challenge_difficulty})
            else:
                ctx.update({"rom": normal_rom, "table_name": normal_table})
        elif last_challenge_ts is not None:
            ctx.update({"rom": challenge_rom, "is_challenge": True,
                        "kind": challenge_kind, "difficulty": challenge_difficulty})
        elif last_normal_ts is not None:
            ctx.update({"rom": normal_rom, "table_name": normal_table})

        # Resolve table name from ROMNAMES if not already set
        if ctx["rom"] and not ctx["table_name"]:
            try:
                romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
                ctx["table_name"] = romnames.get(ctx["rom"], "")
            except Exception:
                pass

        return ctx

    def _overlay_page2_html(self) -> tuple:
        """Return (css, header_html, rows) for Page 2: Achievement Progress.

        ``rows`` is a list of ``<tr>`` HTML strings for use with
        ``OverlayWindow.set_html_scrollable()``.  The Python-level QTimer scroll
        in OverlayWindow replaces the old CSS-animation approach (which is not
        supported by Qt's QLabel RichText renderer).
        """
        import html as _html_mod

        def esc(s):
            return _html_mod.escape(str(s))

        rom = self._get_last_played_rom()
        table_name = ""
        if rom:
            try:
                romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
                table_name = _strip_version_from_name(romnames.get(rom, ""))
            except Exception:
                pass

        if rom:
            header = f"Last Played: {table_name}" if table_name else f"Last Played: {rom}"
        else:
            header = "No recent play data available"

        _tc_primary = get_theme_color(self.cfg, "primary")
        _tc_accent = get_theme_color(self.cfg, "accent")
        css = (
            "<style>"
            "table{width:100%;border-collapse:collapse;}"
            "td{font-size:0.9em;padding:4px 6px;border-bottom:1px solid #333;}"
            f".unlocked{{color:{_tc_primary};font-weight:bold;}}"
            ".locked{color:#555;}"
            f".hdr{{color:{_tc_accent};font-size:1.15em;font-weight:bold;text-align:center;padding:6px 0;}}"
            ".prog{color:#FFFFFF;font-size:0.95em;text-align:center;margin-bottom:6px;}"
            "</style>"
        )

        if not rom or not self.watcher._has_any_map(rom):
            header_html = (
                f"<div class='hdr'>{esc(header)}</div>"
                "<div style='text-align:center;color:#888;padding:18px;'>"
                "No achievement data for this ROM.</div>"
            )
            return css, header_html, []

        try:
            state = self.watcher._ach_state_load()
        except Exception:
            state = {"global": {}, "session": {}}

        all_rules = []
        unlocked_titles = set()
        try:
            s_rules = self.watcher._collect_player_rules_for_rom(rom)
            seen = set()
            for r in s_rules:
                if isinstance(r, dict) and r.get("title"):
                    t = str(r["title"]).strip()
                    if t not in seen:
                        seen.add(t)
                        all_rules.append(r)
        except Exception:
            pass
        for e in state.get("session", {}).get(rom, []):
            t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
            unlocked_titles.add(t)

        if not all_rules:
            header_html = (
                f"<div class='hdr'>{esc(header)}</div>"
                "<div style='text-align:center;color:#888;padding:18px;'>"
                "No specific achievements defined for this ROM.</div>"
            )
            return css, header_html, []

        unlocked_count = 0
        cells = []
        # Pull rarity data from cache for this ROM
        _overlay_rarity: dict = {}
        _cached_r = self._rarity_cache.get(rom)
        if _cached_r:
            _overlay_rarity = _cached_r.get("data", {})
        for r in all_rules:
            title = str(r.get("title", "Unknown")).strip()
            clean = title.replace(" (Session)", "").replace(" (Global)", "")
            ri = _overlay_rarity.get(title) or _overlay_rarity.get(clean)
            rarity_suffix = (
                f"<br><span style='font-size:0.65em;color:{esc(ri['color'])};'>"
                f"{esc(ri['tier'])} ({esc(str(ri['pct']))}%)</span>"
                if ri else ""
            )
            if title in unlocked_titles or clean in unlocked_titles:
                unlocked_count += 1
                cells.append(f"<td class='unlocked'>✅ {esc(clean)}{rarity_suffix}</td>")
            else:
                cells.append(f"<td class='locked'>🔒 {esc(clean)}{rarity_suffix}</td>")

        pct = round((unlocked_count / len(all_rules)) * 100, 1) if all_rules else 0.0
        try:
            _state_for_lv = self.watcher._ach_state_load()
            _lv = compute_player_level(_state_for_lv)
            level_badge = f"{_lv['icon']} {_lv['label']} • Level {_lv['level']} • {_lv['total']} Achievements"
        except Exception:
            level_badge = ""

        header_html = (
            f"<div class='hdr'>{esc(header)}</div>"
            + (f"<div style='color:{_tc_accent};font-size:0.9em;text-align:center;margin-bottom:2px;'>{esc(level_badge)}</div>" if level_badge else "")
            + f"<div class='prog'>Progress: {unlocked_count} / {len(all_rules)} ({pct}%)</div>"
        )

        # Always use 4 columns so the table is compact and consistent at any scale
        COLS = 4
        rows = []
        for i in range(0, len(cells), COLS):
            row = "<tr>"
            for j in range(COLS):
                if i + j < len(cells):
                    row += cells[i + j]
                else:
                    row += "<td></td>"
            row += "</tr>"
            rows.append(row)

        return css, header_html, rows

    def _overlay_page3_html(self) -> str:
        """Generate HTML for Page 3: Local Challenge Leaderboard (mirrors the GUI view)."""
        try:
            return self._build_challenges_results_html()
        except Exception:
            return "<div style='color:#FF3B30;text-align:center;'>(Error loading challenge leaderboard)</div>"

    def _overlay_page4_show(self):
        """Show Page 4: Cloud Leaderboard. Fetches data in the background."""
        import html as _html_mod
        import threading

        self._ensure_overlay()
        ctx = self._get_last_session_context()

        # Build dynamic header
        is_challenge = ctx.get("is_challenge", False)
        kind = ctx.get("kind", "")
        difficulty = ctx.get("difficulty", "")
        table_name = ctx.get("table_name", "")
        rom = ctx.get("rom", "")

        kind_labels = {"timed": "Timed Challenge", "flip": "Flip Challenge", "heat": "Heat Challenge"}
        if is_challenge:
            ch_label = kind_labels.get(kind, "Challenge")
            header_title = f"{ch_label} – {difficulty}" if difficulty else ch_label
        else:
            header_title = table_name if table_name else (rom.upper() if rom else "Cloud Leaderboard")

        _tc_accent = get_theme_color(self.cfg, "accent")
        cloud_sync_msg = ""
        if not self.cfg.CLOUD_ENABLED:
            cloud_sync_msg = (
                f"<div style='color:{_tc_accent};font-weight:bold;font-size:1.05em;"
                f"text-align:center;padding:8px 12px;border:1px solid {_tc_accent};"
                "border-radius:6px;margin-bottom:10px;'>"
                "If you want to participate, enable cloud sync."
                "</div>"
            )

        header_html = (
            f"<div style='color:{_tc_accent};font-size:1.15em;font-weight:bold;"
            f"text-align:center;padding:6px 0;margin-bottom:4px;'>"
            f"{_html_mod.escape(header_title)}</div>"
            + cloud_sync_msg
        )

        if self.cfg.CLOUD_ENABLED and rom:
            loading_html = header_html + (
                "<div style='color:#888;text-align:center;padding:16px;'>Fetching cloud data…</div>"
            )
        else:
            loading_html = header_html + (
                "<div style='color:#888;text-align:center;padding:16px;'>(No ROM data available)</div>"
                if not rom else ""
            )

        self._show_page_with_transition(lambda: self.overlay.set_html(loading_html, "Cloud Leaderboard"))

        if not (self.cfg.CLOUD_ENABLED and rom):
            return

        # Fetch cloud data in background
        from watcher_core import CloudSync

        def _do_fetch():
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            try:
                player_ids = CloudSync.fetch_player_ids(self.cfg)
                data = []
                if is_challenge:
                    cat = kind if kind in ("timed", "flip", "heat") else "timed"
                    if cat == "flip":
                        paths = [f"players/{pid}/scores/flip" for pid in player_ids]
                        batch = CloudSync.fetch_parallel(self.cfg, paths)
                        for path, flip_node in batch.items():
                            if flip_node and isinstance(flip_node, dict):
                                for rom_key, entry in flip_node.items():
                                    if rom_key == rom or rom_key.startswith(f"{rom}_"):
                                        if entry and isinstance(entry, dict):
                                            data.append(entry)
                    else:
                        paths = [f"players/{pid}/scores/{cat}/{rom}" for pid in player_ids]
                        batch = CloudSync.fetch_parallel(self.cfg, paths)
                        for path in paths:
                            entry = batch.get(path)
                            if entry and isinstance(entry, dict):
                                data.append(entry)
                    if data:
                        if cat == "flip" and difficulty and difficulty != "All Difficulties":
                            data = [
                                r for r in data
                                if str(r.get("difficulty", "")).strip().lower() == difficulty.lower()
                            ]
                        data.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
                    selected_diff = difficulty if (is_challenge and kind == "flip") else None
                    cat_for_html = cat
                else:
                    paths = [f"players/{pid}/progress/{rom}" for pid in player_ids]
                    batch = CloudSync.fetch_parallel(self.cfg, paths)
                    for path in paths:
                        entry = batch.get(path)
                        if entry and isinstance(entry, dict):
                            data.append(entry)
                    if data:
                        data.sort(key=lambda x: float(x.get("percentage", 0)), reverse=True)
                    selected_diff = None
                    cat_for_html = "progress"

                if not data:
                    final_html = header_html + (
                        "<div style='color:#FF3B30;text-align:center;padding:16px;'>Failed to fetch cloud data.</div>"
                    )
                else:
                    cloud_body = self._generate_cloud_html(data, cat_for_html, rom, selected_diff, include_info_badges=False)
                    final_html = header_html + cloud_body

                QMetaObject.invokeMethod(
                    self, "_overlay_set_cloud_html",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, final_html)
                )
            except Exception as e:
                print(f"[CLOUD OVERLAY] fetch failed: {e}")
                error_html = header_html + (
                    "<div style='color:#FF3B30;text-align:center;padding:16px;'>Failed to fetch cloud data.</div>"
                )
                QMetaObject.invokeMethod(
                    self, "_overlay_set_cloud_html",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, error_html)
                )

        threading.Thread(target=_do_fetch, daemon=True).start()

    def _generate_vpc_html_portrait(self, b64_img, week_text, table_name, overlay_w, overlay_h):
        # Use full overlay dimensions — image already contains all branding/week info.
        avail_w = overlay_w
        avail_h = overlay_h

        # The API returns 640x752 portrait images (aspect ratio 640/752).
        aspect = 640.0 / 752.0

        # Fit image within available bounds while preserving aspect ratio.
        img_w = avail_w
        img_h = int(img_w / aspect)

        if img_h > avail_h:
            img_h = avail_h
            img_w = int(img_h * aspect)

        img_w = max(100, img_w)
        img_h = max(int(100 / aspect), img_h)

        # Use <table> centering — the only reliable method in Qt's RichText engine.
        return (
            f"<table width='100%' height='100%'><tr><td align='center' valign='middle'>"
            f"<img src='data:image/png;base64,{b64_img}' width='{img_w}' height='{img_h}' />"
            f"</td></tr></table>"
        )

    def _generate_vpc_html_landscape(self, b64_img, week_text, table_name, overlay_w, overlay_h):
        # Use full overlay dimensions — image already contains all branding/week info.
        avail_w = overlay_w
        avail_h = overlay_h

        # The API returns 1920x1080 landscape images (16:9 aspect ratio).
        aspect = 16.0 / 9.0

        # Fit image within available bounds while preserving aspect ratio.
        img_w = avail_w
        img_h = int(img_w / aspect)

        if img_h > avail_h:
            img_h = avail_h
            img_w = int(img_h * aspect)

        img_w = max(100, img_w)
        img_h = max(56, img_h)

        # Use <table> centering — the only reliable method in Qt's RichText engine.
        # Fixed pixel width/height prevent Qt from misaligning percentage-based images.
        return (
            f"<table width='100%' height='100%'><tr><td align='center' valign='middle'>"
            f"<img src='data:image/png;base64,{b64_img}' width='{img_w}' height='{img_h}' />"
            f"</td></tr></table>"
        )

    def _refresh_vpc_page5(self):
        """Recalculate and redisplay the VPC image for the current overlay size."""
        data = getattr(self, '_vpc_page5_data', None)
        if not data:
            return
        b64_img = data['b64_img']
        week_text = data['week_text']
        table_name = data['table_name']
        is_portrait = data['is_portrait']

        if is_portrait:
            # Portrait overlay renders content in a landscape pre-canvas (H×W).
            # Use pre-canvas dimensions so the image fills it edge-to-edge.
            pre_w = self.overlay.height() if self.overlay else 1920
            pre_h = self.overlay.width() if self.overlay else 1080
            final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, pre_w, pre_h)
        else:
            overlay_w = self.overlay.width() if self.overlay else 1920
            overlay_h = self.overlay.height() if self.overlay else 1080
            final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, overlay_w, overlay_h)

        self.overlay.set_html_fullsize(final_html, "VPC Weekly")

    def _overlay_page5_show(self):
        """Show Page 5: VPC Weekly Competition (Live Data + Official Image)."""
        from PyQt6.QtCore import QObject, pyqtSignal
        import urllib.request
        import json
        import base64
        import threading
        import ssl
        import time as _time

        self._ensure_overlay()

        # Check TTL-based memory cache (~5 minutes)
        _VPC_CACHE_TTL_SECONDS = 300
        vpc_cache = getattr(self, '_vpc_cache', None)
        if vpc_cache and (_time.time() - vpc_cache.get('ts', 0)) < _VPC_CACHE_TTL_SECONDS:
            cached = vpc_cache
            is_portrait = getattr(self.overlay, 'portrait_mode', False) if self.overlay else False
            b64_img = cached['b64_img']
            week_text = cached['week_text']
            table_name = cached['table_name']
            if is_portrait:
                pre_w = self.overlay.height() if self.overlay else 1920
                pre_h = self.overlay.width() if self.overlay else 1080
                final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, pre_w, pre_h)
            else:
                overlay_w = self.overlay.width() if self.overlay else 1920
                overlay_h = self.overlay.height() if self.overlay else 1080
                final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, overlay_w, overlay_h)
            self._vpc_page5_data = {
                'b64_img': b64_img,
                'week_text': week_text,
                'table_name': table_name,
                'is_portrait': is_portrait,
            }
            self._show_page_with_transition(lambda: self.overlay.set_html_fullsize(final_html, "VPC Weekly"))
            return

        # Recommended PyQt6 pattern for cross-thread UI updates
        class VpcWorkerSignals(QObject):
            update_ui = pyqtSignal(str, str)

        signals = VpcWorkerSignals()
        signals.update_ui.connect(self.overlay.set_html_fullsize)

        # Show loading screen
        _tc_primary = get_theme_color(self.cfg, "primary")
        loading_html = (
            f"<div style='color:{_tc_primary};font-size:1.15em;font-weight:bold;text-align:center;padding:6px 0;'>"
            f"VPC Weekly Challenge</div>"
            f"<div style='color:#888;text-align:center;padding:16px;'>Fetching live Challenge data & image...</div>"
        )
        self._show_page_with_transition(lambda: self.overlay.set_html_fullsize(loading_html, "VPC Weekly"))

        def _fetch_vpc_challenge():
            try:
                # SSL workaround for Windows systems with missing/outdated CA certificates
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                # 1. Challenge-Daten (Text/Infos) über die GET API abrufen
                req_api = urllib.request.Request(
                    "https://virtualpinballchat.com/vpc/api/v1/currentWeek?channelName=competition-corner",
                    headers={'User-Agent': 'VPX-Achievement-Watcher'}
                )
                with urllib.request.urlopen(req_api, timeout=10, context=ctx) as response:
                    api_data = json.loads(response.read().decode('utf-8'))

                if isinstance(api_data, list) and len(api_data) > 0:
                    week_data = api_data[0]
                else:
                    week_data = api_data

                table_name = week_data.get("tableName", week_data.get("table", "Unknown Table"))
                week_number = week_data.get("weekNumber", "")

                week_text = f"Week {week_number} - " if week_number else ""

                # 2. Ausrichtung erkennen (Portrait oder Landscape) – komplett getrennte Pfade
                is_portrait = getattr(self.overlay, 'portrait_mode', False) if self.overlay else False

                if is_portrait:
                    # Portrait overlay: content is rendered in a landscape pre-canvas
                    # (H×W = overlay height × overlay width) before being rotated 90°.
                    # Request the landscape VPC image so it fills the pre-canvas perfectly.
                    vpc_payload = json.dumps({
                        "layout": "landscape"
                    }).encode('utf-8')

                    req_img = urllib.request.Request(
                        "https://virtualpinballchat.com/vpc/api/v1/generateWeeklyLeaderboard",
                        data=vpc_payload,
                        headers={
                            'Content-Type': 'application/json',
                            'User-Agent': 'VPX-Achievement-Watcher'
                        },
                        method='POST'
                    )

                    with urllib.request.urlopen(req_img, timeout=45, context=ctx) as img_response:
                        img_data = img_response.read()

                    b64_img = base64.b64encode(img_data).decode('utf-8')
                    # Use pre-canvas dimensions (H×W) so the image fills the canvas edge-to-edge.
                    pre_w = self.overlay.height() if self.overlay else 1920
                    pre_h = self.overlay.width() if self.overlay else 1080
                    final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, pre_w, pre_h)

                else:
                    # Landscape: eigener API-Aufruf mit layout="landscape"
                    landscape_payload = json.dumps({
                        "layout": "landscape"
                    }).encode('utf-8')

                    req_img_landscape = urllib.request.Request(
                        "https://virtualpinballchat.com/vpc/api/v1/generateWeeklyLeaderboard",
                        data=landscape_payload,
                        headers={
                            'Content-Type': 'application/json',
                            'User-Agent': 'VPX-Achievement-Watcher'
                        },
                        method='POST'
                    )

                    with urllib.request.urlopen(req_img_landscape, timeout=45, context=ctx) as img_response:
                        img_data = img_response.read()

                    b64_img = base64.b64encode(img_data).decode('utf-8')
                    overlay_w = self.overlay.width() if self.overlay else 1920
                    overlay_h = self.overlay.height() if self.overlay else 1080
                    final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, overlay_w, overlay_h)

                # Cache raw data so the slider can recalculate the image
                self._vpc_page5_data = {
                    'b64_img': b64_img,
                    'week_text': week_text,
                    'table_name': table_name,
                    'is_portrait': is_portrait,
                }

                # Store TTL cache for fast re-open (~5 min TTL)
                self._vpc_cache = {
                    'b64_img': b64_img,
                    'week_text': week_text,
                    'table_name': table_name,
                    'ts': _time.time(),
                }

                # Slider hook: When overlay scale changes, recalculate the image
                try:
                    self.overlay.resizeEvent_original  # check if already hooked
                except AttributeError:
                    _orig = self.overlay.resizeEvent
                    self.overlay.resizeEvent_original = _orig
                    _self = self  # Reference to Achievement_watcher instance

                    def _hooked_resize(event, _orig=_orig, _aw=_self):
                        _orig(event)
                        if getattr(_aw, '_vpc_page5_data', None):
                            _aw._refresh_vpc_page5()

                    self.overlay.resizeEvent = _hooked_resize

                # Über das definierte Signal emitten, damit PyQt6 es sicher in den Main-Thread schiebt!
                signals.update_ui.emit(final_html, "VPC Weekly")

            except Exception as e:
                import traceback
                traceback.print_exc()
                error_html = (
                    f"<div style='color:#FF5555;text-align:center;padding:16px;'>"
                    f"Error loading VPC Challenge:<br><span style='font-size:0.8em;'>{str(e)}</span></div>"
                )
                signals.update_ui.emit(error_html, "VPC Weekly")

        threading.Thread(target=_fetch_vpc_challenge, daemon=True).start()

    def _cycle_overlay_button(self):
        # ── cooldown: ignore rapid re-triggers within 500 ms ──
        import time as _time
        _now = _time.monotonic()
        if _now - getattr(self, "_overlay_last_action", 0.0) < 0.50:
            return
        # Record this attempt immediately so all exit paths respect the cooldown
        self._overlay_last_action = _now

        try:
            if self.watcher and self.watcher.game_active:
                # Wenn eine Challenge aktiv ist oder gestartet wird → nichts tun
                ch = getattr(self.watcher, "challenge", {}) or {}
                if ch.get("active") or ch.get("suppress_big_overlay_once"):
                    return
                try:
                    if self.overlay and self.overlay.isVisible():
                        self.overlay.hide()
                except Exception:
                    pass
                try:
                    if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                        self._mini_overlay = MiniInfoOverlay(self)
                    self._mini_overlay.show_info("Overlay only available after VPX end", seconds=3, color_hex="#FF3B30")
                except Exception:
                    pass
                return
        except Exception:
            pass
        if getattr(self, "_overlay_busy", False):
            return
        self._overlay_busy = True
        try:
            ov = getattr(self, "overlay", None)
            if not ov or not ov.isVisible():
                # Open overlay on page 0 (Main Stats)
                self._overlay_page = 0
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
                if not secs:
                    self._msgbox_topmost("info", "Overlay", "No contents available (Global/Player).")
                    return
                self._overlay_cycle["idx"] = 0
                self._show_overlay_section(secs[0])
            else:
                # Overlay already visible – cycle to next enabled page, close after last
                ov = self.cfg.OVERLAY or {}
                enabled_pages = [0]
                if ov.get("overlay_page2_enabled", True):
                    enabled_pages.append(1)
                if ov.get("overlay_page3_enabled", True):
                    enabled_pages.append(2)
                if ov.get("overlay_page4_enabled", True):
                    enabled_pages.append(3)
                if ov.get("overlay_page5_enabled", True):
                    enabled_pages.append(4)
                current = int(getattr(self, "_overlay_page", 0))
                if current in enabled_pages:
                    current_idx = enabled_pages.index(current)
                else:
                    current_idx = 0
                next_idx = current_idx + 1
                if next_idx >= len(enabled_pages):
                    # After last enabled page → close overlay
                    self._hide_overlay()
                else:
                    next_page = enabled_pages[next_idx]
                    self._overlay_page = next_page
                    self._show_overlay_page(next_page)
        finally:
            import time as _time
            self._overlay_last_action = _time.monotonic()
            self._overlay_busy = False

    def _speak_en(self, text: str):
        try:
            if bool(self.cfg.OVERLAY.get("challenges_voice_mute", False)):
                return

            vol = int(self.cfg.OVERLAY.get("challenges_voice_volume", 80))
            vol = max(0, min(100, vol))
            try:
                import win32com.client 
                sp = win32com.client.Dispatch("SAPI.SpVoice")
                sp.Volume = vol
                sp.Speak(str(text))
                return
            except Exception:
                pass
        except Exception:
            pass

    def _on_challenge_warmup_show(self, seconds: int, message: str):
        try:
            try:
                self._ch_warmup_sec = int(seconds)
            except Exception:
                self._ch_warmup_sec = 10

            if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                self._mini_overlay = MiniInfoOverlay(self)
            self._mini_overlay.show_info(str(message), max(1, int(seconds)), color_hex="#FF3B30")
            if not hasattr(self, "_ch_last_spoken"):
                self._ch_last_spoken = {}
            now = time.time()
            last = float(self._ch_last_spoken.get("timed", 0.0) or 0.0)
            if now - last > 2.0:
                QTimer.singleShot(0, lambda: self._speak_en("Timed challenge started"))
                self._ch_last_spoken["timed"] = now
        except Exception:
            pass

    def _on_challenge_timer_stop(self):
        try:
            if hasattr(self, "_challenge_timer_delay") and self._challenge_timer_delay:
                self._challenge_timer_delay.stop()
                self._challenge_timer_delay.deleteLater()
        except Exception:
            pass
        self._challenge_timer_delay = None

        try:
            if hasattr(self, "_challenge_timer") and self._challenge_timer:
                self._challenge_timer.close()
                self._challenge_timer.deleteLater()
        except Exception:
            pass
        self._challenge_timer = None

    def _on_challenge_info_show(self, message: str, seconds: int, color_hex: str = "#FFFFFF"):
        try:
            msg_lower = str(message or "").lower()
            col = str(color_hex or "").upper()
            if "challenge complete" in msg_lower or "time's up" in msg_lower:
                sound.play_sound(self.cfg, "challenge_complete")
            elif col == "#FF3B30" or "aborted" in msg_lower or "fail" in msg_lower:
                sound.play_sound(self.cfg, "challenge_fail")
        except Exception:
            pass
        try:
            if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                self._mini_overlay = MiniInfoOverlay(self)
            self._mini_overlay.show_info(str(message), max(1, int(seconds)), color_hex=str(color_hex or "#FFFFFF"))
        except Exception:
            pass
        try:
            self._update_challenges_results_view()
        except Exception:
            pass

    def _on_challenge_speak(self, phrase: str):
        self._speak_en(str(phrase or ""))

    def _ensure_overlay(self):
        if self.overlay is None:
            self.overlay = OverlayWindow(self)
        self.overlay.portrait_mode = bool(self.cfg.OVERLAY.get("portrait_mode", True))
        self.overlay._ensuring = True          # suppress showEvent double-work
        self.overlay._apply_geometry()
        self.overlay._layout_positions()
        self.overlay.request_rotation(force=True)
        # 50ms > QTimer.singleShot(0) delay in request_rotation, so the rotation
        # pipeline has started before we release the flag.
        QTimer.singleShot(50, lambda: setattr(self.overlay, '_ensuring', False))

    def _show_overlay_latest(self):
        from PyQt6.QtCore import QTimer
        import time as _time

        def _do_show():
            try:
                # Don't auto-open the main overlay when a challenge is active or
                # being started (suppress_big_overlay_once is set at challenge start
                # before the first challenge notification fires).
                try:
                    _w = getattr(self, "watcher", None)
                    ch = getattr(_w, "challenge", {}) if _w is not None else {}
                    if (ch or {}).get("active") or (ch or {}).get("suppress_big_overlay_once"):
                        return
                except Exception:
                    pass
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
                if not secs:
                    return
                self._ensure_overlay()
                self._overlay_cycle["idx"] = 0
                self._overlay_page = 0
                self._show_overlay_section(secs[0])
                try:
                    self._overlay_last_action = _time.monotonic()
                except Exception:
                    pass
            except Exception:
                pass
        try:
            w = getattr(self, "watcher", None)
            if w and w._vp_player_visible():
                tries = {"n": 0}
                def _poll():
                    try:
                        if not w._vp_player_visible():
                            _do_show()
                            return
                    except Exception:
                        _do_show()
                        return
                    tries["n"] += 1
                    if tries["n"] < 16:
                        QTimer.singleShot(150, _poll)
                    else:
                        _do_show()
                QTimer.singleShot(150, _poll)
                return
        except Exception:
            pass
        _do_show()
        
    def _on_automap_sampler_started(self, rom: str):
        try:
            self._on_mini_info_show(rom, seconds=10)
        except Exception as e:
            try:
                log(self.cfg, f"[CTRL] mini overlay trigger failed on automap start: {e}")
            except Exception:
                pass

    def _maybe_start_automap(self, rom: str):
        log(self.cfg, f"[AUTOMAP] sampler started for {rom}")
        self._on_automap_sampler_started(rom)
           
    def _on_ach_toast_show(self, title: str, rom: str, seconds: int = 5):
        try:
            self._ach_toast_mgr.enqueue(title, rom, max(1, int(seconds)))
        except Exception:
            pass

    def _on_level_up(self, level_name: str, level_number: int):
        try:
            toast_title = f"LEVEL UP!  {level_name}"
            self._ach_toast_mgr.enqueue_level_up(toast_title, level_number, seconds=6)
        except Exception:
            pass
        try:
            self._refresh_level_display()
        except Exception:
            pass

    def _hide_overlay(self):
        if self.overlay and self.overlay.isVisible():
            self.overlay.hide()
        try:
            self.overlay_auto_close_timer.stop()
        except Exception:
            pass
        try:
            if self.overlay:
                self.overlay.set_nav_arrows(False)
        except Exception:
            pass
        if self.overlay and self.overlay.isVisible():
            self.overlay.hide()

    def _toggle_overlay(self):
        if self.watcher and self.watcher.game_active and self.watcher.current_rom:
            if bool(self.cfg.OVERLAY.get("live_updates", False)):
                try:
                    self.watcher.force_flush()
                except Exception:
                    pass
        self._cycle_overlay_button()

    def _on_overlay_test_clicked(self):
        self._ensure_overlay()
        
        dummy_data = {
            "players": [{
                "id": 1,
                "playtime_sec": 420,
                "score": 42069000,
                "deltas": {
                    "Ramps Made": 15,
                    "Jackpots": 4,
                    "Drop Targets": 22,
                    "Loops": 8,
                    "Spinner": 45
                },
                "highlights": {
                    "Power": ["🔥 Best Ball – 12.5M", "💥 Multiball Frenzy – 2", "➕ Extra Balls – 1"],
                    "Precision": ["🏹 Rampage – 15", "🎯 Combo King – 4", "🌀 Spinner Madness – 45"],
                    "Fun": ["💀 Tilted – 1"]
                }
            }]
        }
        
        old_rom = getattr(self.watcher, "current_rom", None)
        self.watcher.current_rom = "test_pinball_table"
        
        try:
            self.overlay.set_combined(dummy_data, session_title="Test Highlights")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            if self.overlay.portrait_mode:
                self.overlay._apply_rotation_snapshot(force=True)
            else:
                self.overlay._show_live_unrotated()
            self.overlay._ensuring = True
            try:
                self.overlay.show()
                self.overlay.raise_()
            finally:
                self.overlay._ensuring = False

            QTimer.singleShot(10000, self._hide_overlay)
        finally:
            self.watcher.current_rom = old_rom

    def _on_toggle_keyboard_event(self):
        now = time.monotonic()
        if now - getattr(self, "_last_toggle_ts", 0.0) < 0.40:
            return
        self._last_toggle_ts = now
        if getattr(self, "_overlay_busy", False):
            return
            
        try:
            if getattr(self, "_challenge_select", None) and self._challenge_select.isVisible():
                return
            if getattr(self, "_flip_diff_select", None) and self._flip_diff_select.isVisible():
                return
        except Exception:
            pass

        # Während Challenge keine Overlay-Toggle erlauben
        try:
            ch = getattr(self.watcher, "challenge", {}) or {}
            if ch.get("active") or ch.get("suppress_big_overlay_once"):
                return
        except Exception:
            pass

        self._cycle_overlay_button()

    def _on_joy_toggle_poll(self):
        def _need_ch(kind: str) -> int | None:
            if str(self.cfg.OVERLAY.get(f"challenge_{kind}_input_source", "keyboard")).lower() != "joystick":
                return None
            try:
                return int(self.cfg.OVERLAY.get(f"challenge_{kind}_joy_button", 0) or 0)
            except Exception:
                return None
        overlay_src = str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower()
        overlay_btn = int(self.cfg.OVERLAY.get("toggle_joy_button", 0) or 0) if overlay_src == "joystick" else 0
        j_hotkey = _need_ch("hotkey")
        j_left   = _need_ch("left")
        j_right  = _need_ch("right")

        def _bit(btn: int | None) -> int:
            try:
                b = int(btn or 0)
                return (1 << (b - 1)) if b > 0 else 0
            except Exception:
                return 0
        overlay_bit = _bit(overlay_btn)
        hotkey_bit  = _bit(j_hotkey)
        left_bit    = _bit(j_left)
        right_bit   = _bit(j_right)
        interested_mask = overlay_bit | hotkey_bit | left_bit | right_bit
        if interested_mask == 0:
            self._joy_toggle_last_mask = 0
            return
        jix = JOYINFOEX()
        jix.dwSize = ctypes.sizeof(JOYINFOEX)
        jix.dwFlags = JOY_RETURNALL
        mask_all = 0
        for jid in range(16):
            try:
                if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                    mask_all |= int(jix.dwButtons)
            except Exception:
                continue

        newly = (mask_all & ~getattr(self, "_joy_toggle_last_mask", 0))
        self._joy_toggle_last_mask = mask_all
        if newly == 0:
            return
        if hotkey_bit and (newly & hotkey_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_hotkey()
            return
        if left_bit and (newly & left_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_left()
            return
        if right_bit and (newly & right_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_right()
            return
        if overlay_bit and (newly & overlay_bit):
            try:
                ch_ov_visible = bool(getattr(self, "_challenge_select", None) and self._challenge_select.isVisible())
                diff_ov_visible = bool(getattr(self, "_flip_diff_select", None) and self._flip_diff_select.isVisible())
            except Exception:
                ch_ov_visible = False
                diff_ov_visible = False
            if ch_ov_visible or diff_ov_visible or self._challenge_is_active():
                return
            self._cycle_overlay_button()
            return
        
    def _on_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["portrait_mode"] = is_checked
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_portrait_from_cfg(self.cfg.OVERLAY)
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_lines_per_category_changed(self, val: int):
        self.cfg.OVERLAY["lines_per_category"] = int(val)
        self.cfg.save()
        try:
            if self.overlay and self.overlay.isVisible():
                self._refresh_overlay_live()
        except Exception:
            pass

    def _on_overlay_scale(self, val: int):
        self.lbl_scale.setText(f"{val}%")
        self.cfg.OVERLAY["scale_pct"] = int(val)
        self.cfg.save()
        if self.overlay:
            self.overlay.scale_pct = int(val)
            self.overlay._apply_scale(int(val))
            self.overlay._apply_geometry()
            if getattr(self, '_vpc_page5_data', None):
                # VPC page 5 is active — recalculate image dimensions for new overlay size
                self._refresh_vpc_page5()
            else:
                self.overlay._refresh_current_content()
        try:
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_secondary_overlay_fonts()

    def _on_toggle_source_changed(self, src: str):
        self.cfg.OVERLAY["toggle_input_source"] = src
        self.cfg.save()
        self.lbl_toggle_binding.setText(self._toggle_binding_label_text())
        self._apply_toggle_source()
        self._refresh_input_bindings()
        
    def _apply_toggle_source(self):
        try:
            src_overlay = str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower()
            any_ch_joy = any(
                str(self.cfg.OVERLAY.get(f"challenge_{k}_input_source", "keyboard")).lower() == "joystick"
                for k in ("hotkey", "left", "right")
            )
            need_poll = (src_overlay == "joystick") or any_ch_joy
            if need_poll:
                self._joy_toggle_timer.start()
            else:
                self._joy_toggle_timer.stop()
                self._joy_toggle_last_mask = 0
        except Exception:
            try:
                self._joy_toggle_timer.stop()
            except Exception:
                pass
            self._joy_toggle_last_mask = 0
            
    def _refresh_input_bindings(self):
        try:
            self._install_global_keyboard_hook()  
        except Exception:
            pass
        try:
            self._register_global_hotkeys()       
        except Exception:
            pass
        try:
            self._install_challenge_key_handling()  
        except Exception:
            pass     

    def _on_bind_toggle_clicked(self):
        # 1. Globale Hotkeys deaktivieren
        self._unregister_global_hotkeys()
        self._uninstall_global_keyboard_hook()
        
        src = self.cfg.OVERLAY.get("toggle_input_source", "keyboard")
        is_joy = (src == "joystick")
        
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        dlg.setWindowTitle("Binding")
        dlg.resize(360, 140)
        
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        
        cancelled = {"flag": False}
        start_ts = time.time()
        
        def update_lbl():
            elapsed = time.time() - start_ts
            rem = max(0.0, 10.0 - elapsed)
            btn_txt = "joystick button" if is_joy else "key"
            lbl.setText(f"Press any {btn_txt} to bind…\n(Timeout in {rem:.1f}s; ESC to cancel)")
            return elapsed

        update_lbl()
        
        class _UnifiedFilter(QAbstractNativeEventFilter):
            def __init__(self, parent_ref):
                super().__init__()
                self.parent = parent_ref
                self._done = False
                
            def nativeEventFilter(self, eventType, message):
                if self._done:
                    return False, 0
                try:
                    if eventType == b"windows_generic_MSG":
                        msg = ctypes.wintypes.MSG.from_address(int(message))
                        if msg.message in (0x0100, 0x0104): # WM_KEYDOWN, WM_SYSKEYDOWN
                            vk = int(msg.wParam)
                            
                            if vk == 0x1B:
                                self._done = True
                                cancelled["flag"] = True
                                QTimer.singleShot(0, dlg.reject)
                                return True, 0
                                
                            if not is_joy:
                                if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                                    return False, 0 
                                    
                                lp = int(msg.lParam)
                                scancode = (lp >> 16) & 0xFF
                                extended = (lp >> 24) & 0x01

                                if vk == 0x10:
                                    if scancode == 42: vk = 0xA0
                                    elif scancode == 54: vk = 0xA1
                                elif vk == 0x11: 
                                    vk = 0xA3 if extended else 0xA2
                                    
                                self._done = True
                                self.parent.cfg.OVERLAY["toggle_vk"] = int(vk)
                                self.parent.cfg.save()
                                QTimer.singleShot(0, dlg.accept)
                                return True, 0
                except Exception:
                    pass
                return False, 0

        fil = _UnifiedFilter(self)
        QCoreApplication.instance().installNativeEventFilter(fil)

        def _read_buttons_mask() -> int:
            jix = JOYINFOEX()
            jix.dwSize = ctypes.sizeof(JOYINFOEX)
            jix.dwFlags = JOY_RETURNALL
            m_all = 0
            for jid in range(16):
                try:
                    if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                        m_all |= int(jix.dwButtons)
                except Exception:
                    continue
            return m_all
            
        baseline = _read_buttons_mask() if is_joy else 0
        timer = QTimer(dlg)
        
        def _poll():
            if cancelled["flag"]:
                timer.stop()
                return
                
            elapsed = update_lbl()
            
            if is_joy:
                try:
                    mask = _read_buttons_mask()
                    newly = mask & ~baseline
                    if newly:
                        lsb = newly & -newly
                        idx = lsb.bit_length() - 1
                        btn_num = idx + 1
                        self.cfg.OVERLAY["toggle_joy_button"] = int(btn_num)
                        self.cfg.save()
                        timer.stop()
                        dlg.accept()
                        return
                except Exception:
                    pass
                    
            if elapsed > 10.0:
                timer.stop()
                dlg.reject()

        timer.setInterval(35)
        timer.timeout.connect(_poll)
        timer.start()

        def cleanup():
            try:
                QCoreApplication.instance().removeNativeEventFilter(fil)
            except Exception:
                pass
            self.lbl_toggle_binding.setText(self._toggle_binding_label_text())
            self._refresh_input_bindings()
            
        dlg.finished.connect(cleanup)
        dlg.exec()


    def _on_bind_ch_clicked(self, kind: str):
        self._unregister_global_hotkeys()
        self._uninstall_global_keyboard_hook()
        
        src = self.cfg.OVERLAY.get(f"challenge_{kind}_input_source", "keyboard")
        is_joy = (src == "joystick")
        
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        dlg.setWindowTitle("Binding")
        dlg.resize(360, 140)
        
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        
        cancelled = {"flag": False}
        start_ts = time.time()
        
        def update_lbl():
            elapsed = time.time() - start_ts
            rem = max(0.0, 10.0 - elapsed)
            btn_txt = "joystick button" if is_joy else "key"
            lbl.setText(f"Press any {btn_txt} to bind…\n(Timeout in {rem:.1f}s; ESC to cancel)")
            return elapsed

        update_lbl()

        class _UnifiedFilter(QAbstractNativeEventFilter):
            def __init__(self, parent_ref):
                super().__init__()
                self.parent = parent_ref
                self._done = False
                
            def nativeEventFilter(self, eventType, message):
                if self._done:
                    return False, 0
                try:
                    if eventType == b"windows_generic_MSG":
                        msg = ctypes.wintypes.MSG.from_address(int(message))
                        if msg.message in (0x0100, 0x0104):
                            vk = int(msg.wParam)
                            
                            if vk == 0x1B:
                                self._done = True
                                cancelled["flag"] = True
                                QTimer.singleShot(0, dlg.reject)
                                return True, 0
                                
                            if not is_joy:
                                if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                                    return False, 0
                                    
                                mods = self.parent._get_hotkey_mods_now()
                                self._done = True
                                self.parent.cfg.OVERLAY[f"challenge_{kind}_vk"] = int(vk)
                                self.parent.cfg.OVERLAY[f"challenge_{kind}_mods"] = int(mods)
                                self.parent.cfg.save()
                                QTimer.singleShot(0, dlg.accept)
                                return True, 0
                except Exception:
                    pass
                return False, 0

        fil = _UnifiedFilter(self)
        QCoreApplication.instance().installNativeEventFilter(fil)

        def _read_buttons_mask() -> int:
            jix = JOYINFOEX()
            jix.dwSize = ctypes.sizeof(JOYINFOEX)
            jix.dwFlags = JOY_RETURNALL
            m_all = 0
            for jid in range(16):
                try:
                    if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                        m_all |= int(jix.dwButtons)
                except Exception:
                    continue
            return m_all

        baseline = _read_buttons_mask() if is_joy else 0
        timer = QTimer(dlg)

        def _poll():
            if cancelled["flag"]:
                timer.stop()
                return
                
            elapsed = update_lbl()
            
            if is_joy:
                try:
                    mask = _read_buttons_mask()
                    newly = mask & ~baseline
                    if newly:
                        lsb = newly & -newly
                        idx = lsb.bit_length() - 1
                        btn_num = idx + 1
                        self.cfg.OVERLAY[f"challenge_{kind}_joy_button"] = int(btn_num)
                        self.cfg.save()
                        timer.stop()
                        dlg.accept()
                        return
                except Exception:
                    pass
                    
            if elapsed > 10.0:
                timer.stop()
                dlg.reject()

        timer.setInterval(35)
        timer.timeout.connect(_poll)
        timer.start()

        def cleanup():
            try:
                QCoreApplication.instance().removeNativeEventFilter(fil)
            except Exception:
                pass
                
            if kind == "hotkey":
                self.lbl_ch_hotkey_binding.setText(self._challenge_binding_label_text("hotkey"))
            elif kind == "left":
                self.lbl_ch_left_binding.setText(self._challenge_binding_label_text("left"))
            else:
                self.lbl_ch_right_binding.setText(self._challenge_binding_label_text("right"))
                
            self._refresh_input_bindings()

        dlg.finished.connect(cleanup)
        dlg.exec()

    def _toggle_binding_label_text(self) -> str:
        src = self.cfg.OVERLAY.get("toggle_input_source", "keyboard")
        if src == "joystick":
            btn = int(self.cfg.OVERLAY.get("toggle_joy_button", 2))
            return f"Current: joystick button {btn}"
        else:
            vk = int(self.cfg.OVERLAY.get("toggle_vk", 120))
            return f"Current: {vk_to_name_en(vk)}"

    def _on_overlay_trigger(self):
        self._toggle_overlay()

    def _on_font_family_changed(self, qfont: QFont):
        family = qfont.family()
        self.cfg.OVERLAY["font_family"] = family
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_font_from_cfg(self.cfg.OVERLAY)
        self._update_secondary_overlay_fonts()

    def _on_font_size_changed(self, val: int):
        body = int(val)
        self.cfg.OVERLAY["base_body_size"] = body
        self.cfg.OVERLAY["base_title_size"] = int(round(body * 1.4))
        self.cfg.OVERLAY["base_hint_size"] = int(round(body * 0.8))
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_font_from_cfg(self.cfg.OVERLAY)
            self.overlay._apply_geometry()
        self._update_secondary_overlay_fonts()

    def _update_secondary_overlay_fonts(self):
        mini = getattr(self, "_mini_overlay", None)
        if mini is not None:
            mini.update_font()
        for attr in ("_flip_total_win", "_flip_total_test_win"):
            flip = getattr(self, attr, None)
            if flip is not None:
                flip.update_font()
        for attr in ("_challenge_select", "_challenge_select_test", "_flip_diff_select", "_challenge_timer"):
            win = getattr(self, attr, None)
            if win is not None and win.isVisible():
                win.update_font()

    def _install_global_keyboard_hook(self):
        try:
            if getattr(self, "_global_keyhook", None):
                try:
                    self._global_keyhook.uninstall()
                except Exception:
                    pass
            self._global_keyhook = None
        except Exception as e:
            log(self.cfg, f"[HOTKEY] disable hook failed: {e}", "WARN")

    def _register_global_hotkeys(self):
        try:
            try:
                self._unregister_global_hotkeys()
            except Exception:
                pass
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            MOD_NOREPEAT = 0x4000
            ids = {
                "overlay_toggle": 0xA11,
                "ch_hotkey":      0xA21,
                "ch_left":        0xA22,
                "ch_right":       0xA23,
            }

            def _reg(_id: int, vk: int):
                mods = (int(self._mods_for_vk(int(vk))) | MOD_NOREPEAT)
                user32.RegisterHotKey(wintypes.HWND(hwnd), _id, mods, int(vk))

            def _reg_ch(_id: int, vk: int, mods_cfg: int):
                mods = (int(mods_cfg) | MOD_NOREPEAT)
                user32.RegisterHotKey(wintypes.HWND(hwnd), _id, mods, int(vk))
            if str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower() == "keyboard":
                vk_overlay = int(self.cfg.OVERLAY.get("toggle_vk", 120))  # F9
                _reg(ids["overlay_toggle"], vk_overlay)
            if str(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_hotkey_vk", 0x7A))
                mods = int(self.cfg.OVERLAY.get("challenge_hotkey_mods", 0))
                _reg_ch(ids["ch_hotkey"], vk, mods)
            if str(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_left_vk", 0x25))
                mods = int(self.cfg.OVERLAY.get("challenge_left_mods", 0))
                _reg_ch(ids["ch_left"], vk, mods)
            if str(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_right_vk", 0x27))
                mods = int(self.cfg.OVERLAY.get("challenge_right_mods", 0))
                _reg_ch(ids["ch_right"], vk, mods)
            class _HotkeyFilter(QAbstractNativeEventFilter):
                def __init__(self, parent_ref, ids_map):
                    super().__init__()
                    self.p = parent_ref
                    self.ids = ids_map
                def nativeEventFilter(self, eventType, message):
                    try:
                        if eventType == b"windows_generic_MSG":
                            msg = ctypes.wintypes.MSG.from_address(int(message))
                            if msg.message == WM_HOTKEY:
                                hid = int(msg.wParam)
                                if hid == self.ids["overlay_toggle"]:
                                    QTimer.singleShot(0, self.p._on_toggle_keyboard_event)
                                elif hid == self.ids["ch_hotkey"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_hotkey)
                                elif hid == self.ids["ch_left"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_left)
                                elif hid == self.ids["ch_right"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_right)
                    except Exception:
                        pass
                    return False, 0
            self._hotkey_ids = ids
            self._hotkey_filter = _HotkeyFilter(self, ids)
            QCoreApplication.instance().installNativeEventFilter(self._hotkey_filter)
            if getattr(self.cfg, "LOG_CTRL", False):
                log(self.cfg, "[HOTKEY] Registered overlay + challenge hotkeys (keyboard)")
        except Exception as e:
            log(self.cfg, f"[HOTKEY] register failed: {e}", "WARN")
       
    def _uninstall_global_keyboard_hook(self):
        try:
            if getattr(self, "_global_keyhook", None):
                self._global_keyhook.uninstall()
                self._global_keyhook = None
                log(self.cfg, "[HOOK] Global keyboard hook uninstalled")
        except Exception as e:
            log(self.cfg, f"[HOOK] uninstall failed: {e}", "WARN")

    def _unregister_global_hotkeys(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            if getattr(self, "_hotkey_ids", None):
                for _name, _id in list(self._hotkey_ids.items()):
                    try:
                        user32.UnregisterHotKey(wintypes.HWND(hwnd), _id)
                    except Exception:
                        pass
            self._hotkey_ids = {}
        except Exception:
            pass
        try:
            if getattr(self, "_hotkey_filter", None):
                QCoreApplication.instance().removeNativeEventFilter(self._hotkey_filter)  # type: ignore
        except Exception:
            pass
        self._hotkey_filter = None
     
    def _overlay_set_cloud_html(self, html: str):
        """Thread-safe slot to update the cloud leaderboard overlay HTML."""
        try:
            if (
                getattr(self, "_overlay_page", -1) == 3
                and self.overlay
                and self.overlay.isVisible()
            ):
                self.overlay.set_html(html, "Cloud Leaderboard")
                try:
                    self.overlay.set_nav_arrows(True)
                except Exception:
                    pass
        except Exception:
            pass

def main():
    cfg = AppConfig.load()
    app = QApplication(sys.argv)
    need_wizard = cfg.FIRST_RUN or not os.path.isdir(cfg.BASE)
    if need_wizard:
        if not os.path.isdir(cfg.BASE):
            home_alt = os.path.join(os.path.expanduser("~"), "Achievements")
            if not os.path.exists(cfg.BASE) and not os.path.exists(home_alt):
                cfg.BASE = home_alt
        wiz = SetupWizardDialog(cfg)
        if wiz.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
    for sub in [
        os.path.join("tools", "NVRAM_Maps", "maps"),
        os.path.join("session_stats", "Highlights"),
        os.path.join("Achievements", "rom_specific_achievements"),
    ]:
        ensure_dir(os.path.join(cfg.BASE, sub))
    bridge = Bridge()
    watcher = Watcher(cfg, bridge)
    win = MainWindow(cfg, watcher, bridge)
    try:
        win._install_global_keyboard_hook()
    except Exception:
        pass
    try:
        win._register_global_hotkeys()
    except Exception:
        pass
    if cfg.FIRST_RUN:
        cfg.FIRST_RUN = False
        cfg.save()
    if not cfg.TUTORIAL_COMPLETED:
        win.showNormal()
        tutorial = TutorialWizardDialog(cfg, win)
        tutorial.show()
    else:
        win.hide()
    code = app.exec()
    cfg.save()
    sys.exit(code)

if __name__ == "__main__":

    main()

