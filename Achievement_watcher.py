
from __future__ import annotations

import configparser
import random
import subprocess
import hashlib
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
from theme import pinball_arcade_style
from ui_cloud_stats import CloudStatsMixin

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
            if rom not in entries:
                title = romnames.get(rom, fname.rsplit(".", 1)[0])
                entries[rom] = {"rom": rom, "title": title, "has_map": False, "is_local": False, "vps_id": "", "vpx_path": ""}
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
            entry["vps_id"] = mapping.get(rom, "")

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


class MainWindow(QMainWindow, CloudStatsMixin):
    CURRENT_VERSION = "2.6"
    _HIGHSCORE_POLL_INTERVAL_MS = 300_000   # 5 minutes
    _NOTIF_COOLDOWN_HOURS = 24              # dedup window for highscore_beaten per ROM

    def __init__(self, cfg: AppConfig, watcher: Watcher, bridge: Bridge):
        super().__init__()
        self.cfg = cfg
        self.watcher = watcher
        self.bridge = bridge
        self.setWindowTitle("VPX Achievement Watcher")
        self.resize(1606, 1145)
        
        icon = self._get_icon()
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        
        if "player_id" not in self.cfg.OVERLAY:
            self.cfg.OVERLAY["player_id"] = str(uuid.uuid4())[:4]
            self.cfg.save()
            
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

        self._apply_theme()
        self._check_for_updates()
        self._init_tooltips_main()
        self._init_overlay_tooltips()

        self._refresh_input_bindings()

    def register_flip_counter_handlers(self):
        try:
            self.bridge.flip_counter_total_show.connect(self._on_flip_total_show)
            self.bridge.flip_counter_total_update.connect(self._on_flip_total_update)
            self.bridge.flip_counter_total_hide.connect(self._on_flip_total_hide)
        except Exception:
            pass
        self._flip_total_win = None
        self._flip_counter_picker = None

    def register_heat_bar_handlers(self):
        try:
            self.bridge.heat_bar_show.connect(self._on_heat_bar_show)
            self.bridge.heat_bar_update.connect(self._on_heat_bar_update)
            self.bridge.heat_bar_hide.connect(self._on_heat_bar_hide)
        except Exception:
            pass
        self._heat_bar_win = None
        self._heat_bar_picker = None

    def _on_heat_bar_show(self):
        try:
            if self._heat_bar_win:
                try:
                    self._heat_bar_win.close()
                    self._heat_bar_win.deleteLater()
                except Exception:
                    pass
            self._heat_bar_win = HeatBarometerOverlay(self)
        except Exception:
            self._heat_bar_win = None

    def _on_heat_bar_update(self, heat: int):
        try:
            if not self._heat_bar_win:
                self._on_heat_bar_show()
            else:
                self._heat_bar_win.set_heat(heat)
        except Exception:
            pass

    def _on_heat_bar_hide(self):
        try:
            if self._heat_bar_win:
                self._heat_bar_win.close()
                self._heat_bar_win.deleteLater()
        except Exception:
            pass
        self._heat_bar_win = None

    def _on_heat_bar_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["heat_bar_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if isinstance(self._heat_bar_picker, HeatBarPositionPicker):
                self._heat_bar_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_heat_bar_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["heat_bar_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if isinstance(self._heat_bar_picker, HeatBarPositionPicker):
                self._heat_bar_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_heat_bar_place_clicked(self):
        picker = getattr(self, "_heat_bar_picker", None)
        if picker:
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()

            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("heat_bar_portrait", ov.get("portrait_mode", False)))
            if portrait:
                self.cfg.OVERLAY["heat_bar_x_portrait"] = int(x)
                self.cfg.OVERLAY["heat_bar_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["heat_bar_x_landscape"] = int(x)
                self.cfg.OVERLAY["heat_bar_y_landscape"] = int(y)
            self.cfg.OVERLAY["heat_bar_saved"] = True
            self.cfg.OVERLAY["heat_bar_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._heat_bar_picker = None
            self.btn_heat_bar_place.setText("Place / Save Heat Bar position")
            return
        self._heat_bar_picker = HeatBarPositionPicker(self, width_hint=48, height_hint=260)
        self.btn_heat_bar_place.setText("Save Heat Bar position")

    def _on_heat_bar_test(self):
        try:
            if getattr(self, "_heat_bar_test_win", None):
                try:
                    self._heat_bar_test_win.close()
                except Exception:
                    pass
            self._heat_bar_test_win = HeatBarometerOverlay(self)
            self._heat_bar_test_win.set_heat(70)
            QTimer.singleShot(6000, lambda: (self._heat_bar_test_win.close() if self._heat_bar_test_win else None))
        except Exception:
            pass

    def _on_flip_total_show(self, total: int, remaining: int, goal: int):
        try:
            if self._flip_total_win:
                try:
                    self._flip_total_win.close()
                    self._flip_total_win.deleteLater()
                except Exception:
                    pass
            self._flip_total_win = FlipCounterOverlay(self, total, remaining, goal)
        except Exception:
            self._flip_total_win = None

    def _on_flip_total_update(self, total: int, remaining: int, goal: int):
        try:
            if not self._flip_total_win:
                self._on_flip_total_show(total, remaining, goal)
            else:
                self._flip_total_win.update_counts(total, remaining, goal)
        except Exception:
            pass

    def _on_flip_total_hide(self):
        try:
            if self._flip_total_win:
                self._flip_total_win.close()
                self._flip_total_win.deleteLater()
        except Exception:
            pass
        self._flip_total_win = None
        
    def _in_game_now(self) -> bool:
        try:
            w = getattr(self, "watcher", None)
            return bool(w and (w.game_active or w._vp_player_visible()))
        except Exception:
            return False
  
    def _on_flip_counter_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["flip_counter_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass
            
    def _on_flip_counter_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["flip_counter_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass            
            
    def _on_flip_counter_place_clicked(self):
        picker = getattr(self, "_flip_counter_picker", None)
        if picker:
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()

            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["flip_counter_x_portrait"] = int(x)
                self.cfg.OVERLAY["flip_counter_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["flip_counter_x_landscape"] = int(x)
                self.cfg.OVERLAY["flip_counter_y_landscape"] = int(y)
            self.cfg.OVERLAY["flip_counter_saved"] = True
            self.cfg.OVERLAY["flip_counter_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._flip_counter_picker = None
            self.btn_flip_counter_place.setText("Place / Save Flip-Counter position")
            return
        self._flip_counter_picker = FlipCounterPositionPicker(self, width_hint=380, height_hint=130)
        self.btn_flip_counter_place.setText("Save Flip-Counter position")

    def _on_flip_counter_test(self):
        try:
            goal = int(self.cfg.OVERLAY.get("flip_counter_goal_total", 400))
            
            if getattr(self, "_flip_total_test_win", None):
                try: 
                    self._flip_total_test_win.close()
                except Exception: 
                    pass
                    
            self._flip_total_test_win = FlipCounterOverlay(self, total=123, remaining=max(0, goal - 123), goal=goal)
            
            QTimer.singleShot(6000, lambda: (self._flip_total_test_win.close() if self._flip_total_test_win else None))
        except Exception:
            pass
       
    def _challenge_is_active(self) -> bool:
        try:
            ch = getattr(self.watcher, "challenge", {}) or {}
            if not ch.get("active"):
                return False
            if not self._in_game_now():
                ch["active"] = False
                ch["pending_kill_at"] = None
                self.watcher.challenge = ch
                return False
            cur_rom = getattr(self.watcher, "current_rom", None)
            ch_rom = ch.get("rom")
            if cur_rom and ch_rom and str(cur_rom) != str(ch_rom):
                ch["active"] = False
                ch["pending_kill_at"] = None
                self.watcher.challenge = ch
                return False
            return True
        except Exception:
            return False
 
    def _get_hotkey_mods_now(self) -> int:
        import ctypes
        user32 = ctypes.windll.user32

        def pressed(vk: int) -> bool:
            state = user32.GetKeyState(vk)
            return (state & 0x8000) != 0

        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_WIN = 0x0008

        mods = 0
        if pressed(0x10) or pressed(0xA0) or pressed(0xA1):  # Shift / LShift / RShift
            mods |= MOD_SHIFT
        if pressed(0x11) or pressed(0xA2) or pressed(0xA3):  # Ctrl / LCtrl / RCtrl
            mods |= MOD_CONTROL
        if pressed(0x12) or pressed(0xA4) or pressed(0xA5):  # Alt / LAlt / RAlt
            mods |= MOD_ALT
        if pressed(0x5B) or pressed(0x5C):                   # Win links/rechts
            mods |= MOD_WIN

        return mods

    def _fmt_hotkey_label(self, vk: int, mods: int) -> str:
        parts = []
        if mods & 0x0002: parts.append("Ctrl")
        if mods & 0x0004: parts.append("Shift")
        if mods & 0x0001: parts.append("Alt")
        if mods & 0x0008: parts.append("Win")
        parts.append(vk_to_name_en(int(vk)))
        return "+".join(parts)
 
    def _on_overlay_auto_close_toggle(self, state: int):
        enabled = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["overlay_auto_close"] = bool(enabled)
        self.cfg.save()
        try:
            if enabled and self.overlay and self.overlay.isVisible():
                self._start_overlay_auto_close_timer()
            else:
                self.overlay_auto_close_timer.stop()
        except Exception:
            pass

    def _start_overlay_auto_close_timer(self):
        try:
            if bool(self.cfg.OVERLAY.get("overlay_auto_close", False)):
                self.overlay_auto_close_timer.stop()
                self.overlay_auto_close_timer.start(60 * 1000)
        except Exception:
            pass
            
    def _on_ch_ov_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_ov_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_ov_picker") and isinstance(self._ch_ov_picker, ChallengeOVPositionPicker):
                self._ch_ov_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._refresh_challenge_select_overlay()
        self._update_switch_all_button_label()

    def _on_ch_ov_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_ov_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_ov_picker") and isinstance(self._ch_ov_picker, ChallengeOVPositionPicker):
                self._ch_ov_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._refresh_challenge_select_overlay()

    def _on_ch_ov_place_clicked(self):
        picker = getattr(self, "_ch_ov_picker", None)
        if picker and isinstance(picker, ChallengeOVPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ch_ov_x_portrait"] = int(x)
                self.cfg.OVERLAY["ch_ov_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ch_ov_x_landscape"] = int(x)
                self.cfg.OVERLAY["ch_ov_y_landscape"] = int(y)
            self.cfg.OVERLAY["ch_ov_saved"] = True
            self.cfg.OVERLAY["ch_ov_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._ch_ov_picker = None
            self.btn_ch_ov_place.setText("Place / Save ChallengeOV position")
            self._refresh_challenge_select_overlay()
            return
        self._ch_ov_picker = ChallengeOVPositionPicker(self, width_hint=520, height_hint=200)
        self.btn_ch_ov_place.setText("Save ChallengeOV position")
        
    def _on_ch_src_changed(self, kind: str, src: str):
        key = f"challenge_{kind}_input_source"
        self.cfg.OVERLAY[key] = str(src)
        self.cfg.save()
        if kind == "hotkey":
            self.lbl_ch_hotkey_binding.setText(self._challenge_binding_label_text("hotkey"))
        elif kind == "left":
            self.lbl_ch_left_binding.setText(self._challenge_binding_label_text("left"))
        else:
            self.lbl_ch_right_binding.setText(self._challenge_binding_label_text("right"))
        self._refresh_input_bindings()

    def _on_ach_toast_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_ach_toast_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ach_toast_place_clicked(self):
        picker = getattr(self, "_toast_picker", None)
        if picker and isinstance(picker, ToastPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ach_toast_x_portrait"] = int(x)
                self.cfg.OVERLAY["ach_toast_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ach_toast_x_landscape"] = int(x)
                self.cfg.OVERLAY["ach_toast_y_landscape"] = int(y)
            self.cfg.OVERLAY["ach_toast_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._toast_picker = None
            self.btn_ach_toast_place.setText("Place / Save position")
            return

        self._toast_picker = ToastPositionPicker(self)
        self.btn_ach_toast_place.setText("Save position")

    def _on_mini_info_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["notifications_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_mini_info_picker") and isinstance(self._mini_info_picker, MiniInfoPositionPicker):
                self._mini_info_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_mini_info_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["notifications_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_mini_info_picker") and isinstance(self._mini_info_picker, MiniInfoPositionPicker):
                self._mini_info_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_mini_info_place_clicked(self):
        picker = getattr(self, "_mini_info_picker", None)
        if picker and isinstance(picker, MiniInfoPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["notifications_x_portrait"] = int(x)
                self.cfg.OVERLAY["notifications_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["notifications_x_landscape"] = int(x)
                self.cfg.OVERLAY["notifications_y_landscape"] = int(y)
            self.cfg.OVERLAY["notifications_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._mini_info_picker = None
            self.btn_mini_info_place.setText("Place / Save position")
            return
        
        self._mini_info_picker = MiniInfoPositionPicker(self, width_hint=420, height_hint=100)
        self.btn_mini_info_place.setText("Save position")

    _MINI_TEST_MESSAGES = [
        ("CHALLENGE COMPLETE!<br>Score: 42.069.000", "#00C853"),
        ("TIME'S UP!<br>Score: 42.069.000", "#00C853"),
        (
            "NVRAM map not found for afm_113b.",
            "#FF3B30",
        ),
        ("Challenge Aborted!", "#FF3B30"),
        ("Challenge can only be started in-game.", "#FF3B30"),
    ]

    def _on_mini_info_test(self):
        # Ruft das Fenster direkt auf, ohne auf ein offenes Spiel zu warten!
        if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
            self._mini_overlay = MiniInfoOverlay(self)
        msg, color = self._MINI_TEST_MESSAGES[self._mini_test_idx % len(self._MINI_TEST_MESSAGES)]
        self._mini_test_idx = (self._mini_test_idx + 1) % len(self._MINI_TEST_MESSAGES)
        self._mini_overlay.show_info(msg, seconds=5, color_hex=color)

    # ------------------------------------------------------------------
    # Status Overlay handlers
    # ------------------------------------------------------------------

    def _on_status_overlay_enabled_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_enabled"] = bool(is_checked)
        self.cfg.save()

    def _on_status_overlay_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_status_overlay_picker") and isinstance(self._status_overlay_picker, StatusOverlayPositionPicker):
                self._status_overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_status_overlay_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_status_overlay_picker") and isinstance(self._status_overlay_picker, StatusOverlayPositionPicker):
                self._status_overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_status_overlay_place_clicked(self):
        picker = getattr(self, "_status_overlay_picker", None)
        if picker and isinstance(picker, StatusOverlayPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("status_overlay_portrait", False))
            if portrait:
                self.cfg.OVERLAY["status_overlay_x_portrait"] = int(x)
                self.cfg.OVERLAY["status_overlay_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["status_overlay_x_landscape"] = int(x)
                self.cfg.OVERLAY["status_overlay_y_landscape"] = int(y)
            self.cfg.OVERLAY["status_overlay_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._status_overlay_picker = None
            self.btn_status_overlay_place.setText("Place / Save position")
            return

        self._status_overlay_picker = StatusOverlayPositionPicker(self)
        self.btn_status_overlay_place.setText("Save position")

    # Agreed status states for the persistent status badge (traffic-light semantics)
    _STATUS_TEST_MESSAGES = [
        ("Online · Tracking",  "#00C853"),   # Green
        ("Online · Pending",   "#FFA500"),   # Yellow
        ("Online · Verified",  "#00C853"),   # Green
        ("Offline · Local",    "#FFA500"),   # Yellow
        ("Cloud Off · Local",  "#FF3B30"),   # Red
    ]

    def _on_status_overlay_test(self):
        """Cycle through the agreed status states for visual testing."""
        if not hasattr(self, "_status_overlay") or self._status_overlay is None:
            self._status_overlay = StatusOverlay(self)
        msg, color = self._STATUS_TEST_MESSAGES[self._status_overlay_test_idx % len(self._STATUS_TEST_MESSAGES)]
        self._status_overlay_test_idx = (self._status_overlay_test_idx + 1) % len(self._STATUS_TEST_MESSAGES)
        self._status_overlay.update_status(msg, color)

    def _determine_status_state(self) -> tuple[str, str]:
        """Return (status_text, color_hex) that reflects the current tracking state.

        Traffic-light semantics:
          Green:  Online · Tracking / Online · Verified
          Yellow: Online · Pending  / Offline · Local
          Red:    Cloud Off · Local
        """
        cloud_enabled = bool(getattr(self.cfg, "CLOUD_ENABLED", False))
        cloud_url = str(getattr(self.cfg, "CLOUD_URL", "") or "").strip()
        if not cloud_enabled or not cloud_url:
            return ("Cloud Off · Local", "#FF3B30")
        w = getattr(self, "watcher", None)
        game_active = bool(w and getattr(w, "game_active", False))
        if not game_active:
            return ("Offline · Local", "#FFA500")
        # Check for an externally set pending/verified flag (set by _on_status_overlay_show)
        pending_state = getattr(self, "_status_badge_state", None)
        if pending_state == "pending":
            return ("Online · Pending", "#FFA500")
        if pending_state == "verified":
            return ("Online · Verified", "#00C853")
        if pending_state == "flagged":
            return ("Online · Flagged", "#FFA500")
        if pending_state == "rejected":
            return ("Online · Rejected", "#FF3B30")
        return ("Online · Tracking", "#00C853")

    def _on_status_overlay_show(self, message: str, seconds: int = 5, color_hex: str = ""):
        """Handle an externally-triggered status update.

        The message is expected to be one of the agreed status texts.  When
        cloud/leaderboard code submits a score it can emit status_overlay_show
        with the relevant state.  The badge is kept persistent; callers must
        not rely on auto-dismiss behavior.
        """
        if not bool(self.cfg.OVERLAY.get("status_overlay_enabled", True)):
            return
        # Map message/color to our known state flags so _determine_status_state
        # can pick them up during the next poll cycle.
        lc = str(message or "").lower()
        if "pending" in lc:
            self._status_badge_state = "pending"
        elif "verified" in lc or "accepted" in lc:
            self._status_badge_state = "verified"
        elif "flagged" in lc:
            self._status_badge_state = "flagged"
        elif "rejected" in lc:
            self._status_badge_state = "rejected"
        else:
            self._status_badge_state = None
        # Also pass the explicit color if provided
        if color_hex:
            txt = str(message or "").strip()
            self._status_badge_explicit = (txt, color_hex)
        else:
            self._status_badge_explicit = None
        # Force an immediate badge refresh via the poll timer mechanism
        self._poll_status_badge()

    def _poll_status_badge(self):
        """Poll game state and show/update/hide the status badge accordingly.

        Called every ~2 seconds by ``_status_badge_timer``.  Also called
        directly from ``_on_status_overlay_show`` for immediate feedback.
        """
        try:
            if not bool(self.cfg.OVERLAY.get("status_overlay_enabled", True)):
                if hasattr(self, "_status_overlay") and self._status_overlay:
                    self._status_overlay.hide_badge()
                return
            in_game = self._in_game_now()
            if not in_game:
                if hasattr(self, "_status_overlay") and self._status_overlay:
                    self._status_overlay.hide_badge()
                # Reset transient state flags when leaving a game
                self._status_badge_state = None
                self._status_badge_explicit = None
                return
            # Determine what to show
            explicit = getattr(self, "_status_badge_explicit", None)
            if explicit:
                txt, color = explicit
            else:
                txt, color = self._determine_status_state()
            if not hasattr(self, "_status_overlay") or self._status_overlay is None:
                self._status_overlay = StatusOverlay(self)
            self._status_overlay.update_status(txt, color)
        except Exception:
            pass

    def _open_challenge_select_overlay(self):
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self.bridge.challenge_info_show.emit(
                    "Challenge can only be started in-game.",
                    3,
                    "#FF3B30"
                )
            except Exception:
                pass
            return

        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            if not current_rom or not self.watcher._has_any_map(current_rom):
                try:
                    self.bridge.challenge_info_show.emit(
                        "Challenges disabled: No NVRAM map found for this table.",
                        4,
                        "#FF3B30"
                    )
                    self.bridge.challenge_speak.emit("Challenge disabled. Map missing.")
                except Exception:
                    pass
                return
        except Exception:
            pass

        try:
            if getattr(self, "_challenge_select", None):
                try:
                    self._challenge_select.close()
                    self._challenge_select.deleteLater()
                except Exception:
                    pass
            self._challenge_select = ChallengeSelectOverlay(self, selected_idx=int(self._ch_ov_selected_idx))
            self._challenge_select.show()
            self._challenge_select.raise_()
            if self._ch_active_source is None and self._last_ch_event_src:
                self._ch_active_source = self._last_ch_event_src
            try:
                import time as _time
                self._ch_ov_opened_at = _time.monotonic()
            except Exception:
                self._ch_ov_opened_at = 0.0
        except Exception as e:
            try:
                log(self.cfg, f"[UI] open ChallengeSelectOverlay failed: {e}", "WARN")
            except Exception:
                pass

    def _close_challenge_select_overlay(self):
        try:
            if getattr(self, "_challenge_select", None):
                self._challenge_select.hide()
                self._challenge_select.close()
                self._challenge_select.deleteLater()
        except Exception:
            pass
        self._challenge_select = None
        self._ch_active_source = None
        try:
            self._ch_ov_opened_at = 0.0
        except Exception:
            pass

    def _close_secondary_overlays(self):
        """Close all secondary overlay windows (NOT the main overlay) when VPX exits."""
        for attr in ('_challenge_timer', '_challenge_select', '_flip_diff_select',
                     '_flip_total_win', '_heat_bar_win'):
            win = getattr(self, attr, None)
            if win is not None:
                try:
                    win.close()
                    win.deleteLater()
                except Exception:
                    pass
                setattr(self, attr, None)
        if getattr(self, '_status_overlay', None) is not None:
            try:
                self._status_overlay.close()
                self._status_overlay.deleteLater()
            except Exception:
                pass
            self._status_overlay = None
        if getattr(self, '_mini_overlay', None) is not None:
            try:
                self._mini_overlay.close()
                self._mini_overlay.deleteLater()
            except Exception:
                pass
            self._mini_overlay = None
        if hasattr(self, '_ach_toast_mgr'):
            try:
                mgr = self._ach_toast_mgr
                mgr._queue.clear()
                if mgr._active_window is not None:
                    try:
                        mgr._active_window.close()
                        mgr._active_window.deleteLater()
                    except Exception:
                        pass
                    mgr._active_window = None
                mgr._active = False
            except Exception:
                pass

    def _refresh_challenge_select_overlay(self):
        ovw = getattr(self, "_challenge_select", None)
        if ovw:
            try:
                ovw.apply_portrait_from_cfg()
            except Exception:
                pass
                
    def _on_ch_timer_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_timer_portrait"] = bool(is_checked)
        self.cfg.OVERLAY["flip_counter_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_timer_picker") and isinstance(self._ch_timer_picker, TimerPositionPicker):
                self._ch_timer_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        try:
            if hasattr(self, "_flip_counter_picker") and isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_ch_timer_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_timer_rotate_ccw"] = bool(is_ccw)
        self.cfg.OVERLAY["flip_counter_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_timer_picker") and isinstance(self._ch_timer_picker, TimerPositionPicker):
                self._ch_timer_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        try:
            if hasattr(self, "_flip_counter_picker") and isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ch_timer_place_clicked(self):
        picker = getattr(self, "_ch_timer_picker", None)
        if picker and isinstance(picker, TimerPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ch_timer_x_portrait"] = int(x)
                self.cfg.OVERLAY["ch_timer_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ch_timer_x_landscape"] = int(x)
                self.cfg.OVERLAY["ch_timer_y_landscape"] = int(y)
            self.cfg.OVERLAY["ch_timer_saved"] = True
            self.cfg.OVERLAY["ch_timer_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._ch_timer_picker = None
            self.btn_ch_timer_place.setText("Place / Save timer position")
            return
        self._ch_timer_picker = TimerPositionPicker(self, width_hint=400, height_hint=120)
        self.btn_ch_timer_place.setText("Save timer position")

    def _on_overlay_place_clicked(self):
        picker = getattr(self, "_overlay_picker", None)
        if picker and isinstance(picker, OverlayPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            self.cfg.OVERLAY["pos_x"] = int(x)
            self.cfg.OVERLAY["pos_y"] = int(y)
            self.cfg.OVERLAY["use_xy"] = True
            self.cfg.OVERLAY["overlay_pos_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._overlay_picker = None
            self.btn_overlay_place.setText("Place / Save overlay position")

            if self.overlay:
                self.overlay._apply_geometry()
                self.overlay._layout_positions()
                self.overlay.request_rotation(force=True)
            return
        self._overlay_picker = OverlayPositionPicker(self)
        self.btn_overlay_place.setText("Save position")

    def _on_mini_info_show(self, rom: str, seconds: int = 10):
        msg = f"NVRAM map not found for {rom}."
        try:
            sound.play_sound(self.cfg, "toast_info")
        except Exception:
            pass

        def _player_visible() -> bool:
            try:
                w = getattr(self, "watcher", None)
                return bool(w and w._vp_player_visible())
            except Exception:
                return False

        def _show_now():
            try:
                if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                    self._mini_overlay = MiniInfoOverlay(self)
                self._mini_overlay.show_info(msg, seconds=max(1, int(seconds)))
            except Exception as e:
                try:
                    log(self.cfg, f"[UI] Mini overlay show failed: {e}")
                except Exception:
                    pass
        if _player_visible():
            _show_now()
            return
        tries = {"n": 0}
        
        def _retry():
            if _player_visible():
                _show_now()
                return
            tries["n"] += 1
            if tries["n"] < 8:
                QTimer.singleShot(250, _retry)
        QTimer.singleShot(250, _retry)

    def _first_screen_geometry(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                return screens[0].geometry()
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _msgbox_topmost(self, kind: str, title: str, text: str):
        box = QMessageBox(self)
        box.setWindowTitle(str(title))
        box.setText(str(text))
        box.setIcon(QMessageBox.Icon.Information if kind == "info" else QMessageBox.Icon.Warning)
        box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        box.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        box.setModal(True)
        box.show()
        box.raise_()
        return box.exec()

    def _on_challenge_timer_start(self, total_seconds: int):
        try:
            sound.play_sound(self.cfg, "challenge_start")
        except Exception:
            pass
        try:
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
            warmup_sec = int(getattr(self, "_ch_warmup_sec", 10))
            play_sec = max(1, int(total_seconds or 0) - warmup_sec)

            self._challenge_timer_delay = QTimer(self)
            self._challenge_timer_delay.setSingleShot(True)

            def _spawn():
                try:
                    if hasattr(self, "_challenge_timer") and self._challenge_timer:
                        self._challenge_timer.close()
                        self._challenge_timer.deleteLater()
                except Exception:
                    pass
                self._challenge_timer = None
                try:
                    log(self.cfg, f"[CHALLENGE] countdown spawn – seconds={play_sec}")
                except Exception:
                    pass
                try:
                    # Show 3…2…1…GO! countdown before the actual challenge timer
                    csd = ChallengeStartCountdown(None)
                    csd.finished.connect(lambda: _launch_timer(csd))
                    csd.start()
                except Exception:
                    _launch_timer(None)

            def _launch_timer(csd_widget=None):
                try:
                    if csd_widget is not None:
                        csd_widget.close()
                except Exception:
                    pass
                try:
                    self._challenge_timer = ChallengeCountdownOverlay(self, play_sec)
                except Exception:
                    self._challenge_timer = None

            self._challenge_timer_delay.timeout.connect(lambda: QTimer.singleShot(0, _spawn))
            self._challenge_timer_delay.start(warmup_sec * 1000)
        except Exception:
            pass

    def _repair_data_folders(self):
        try:
            ensure_dir(self.cfg.BASE)
            for sub in [
                os.path.join("tools", "NVRAM_Maps"),
                os.path.join("tools", "NVRAM_Maps", "maps"),
                "session_stats",
                os.path.join("Achievements", "rom_specific_achievements"),
                os.path.join("Achievements", "custom_achievements"),
            ]:
                ensure_dir(os.path.join(self.cfg.BASE, sub))
            try:
                self.watcher.bootstrap()
            except Exception as e:
                log(self.cfg, f"[REPAIR] bootstrap failed: {e}", "WARN")
            self._msgbox_topmost(
                "info", "Repair",
                "Base folders repaired.\n\nIf maps are still missing, please click 'Cache maps now (prefetch)'\n"
                "or simply start a ROM (maps will then be loaded on demand)."
            )
            log(self.cfg, "[REPAIR] base folders ensured and index/romnames fetched (if missing)")
        except Exception as e:
            log(self.cfg, f"[REPAIR] failed: {e}", "ERROR")
            self._msgbox_topmost("warn", "Repair", f"Repair failed:\n{e}")

    def _mods_for_vk(self, vk: int) -> int:
        return 0
            
    def _on_ch_timer_test(self):
        try:
            win = ChallengeCountdownOverlay(self, total_seconds=10)
            try:
                win._kill_vpx = lambda: (win.close())
            except Exception:
                pass
            QTimer.singleShot(12000, lambda: (win.close() if hasattr(win, "close") else None))
        except Exception:
            pass
            
    def _on_ch_ov_test(self):
        try:
            if getattr(self, "_challenge_select_test", None):
                try:
                    self._challenge_select_test.close()
                    self._challenge_select_test.deleteLater()
                except Exception:
                    pass
            self._challenge_select_test = ChallengeSelectOverlay(self, selected_idx=int(self._ch_ov_selected_idx))
            self._challenge_select_test.show()
            self._challenge_select_test.raise_()

            def _close_test():
                try:
                    w = getattr(self, "_challenge_select_test", None)
                    if w:
                        w.close()
                        w.deleteLater()
                except Exception:
                    pass
                self._challenge_select_test = None

            QTimer.singleShot(5000, _close_test)
        except Exception:
            pass

    def _start_selected_challenge(self):
        idx = int(getattr(self, "_ch_ov_selected_idx", 0) or 0) % 4
        try:
            has_map = False
            try:
                current_rom = getattr(self.watcher, "current_rom", None)
                has_map = bool(current_rom and self.watcher._has_any_map(current_rom))
            except Exception:
                has_map = True
            if not has_map:
                return
            if idx == 0:
                self.watcher.start_timed_challenge()
            elif idx == 2:
                self.watcher.start_heat_challenge()
            elif idx == 1:
                self.watcher.start_flip_challenge(500)
        except Exception:
            pass

    def _challenge_binding_label_text(self, kind: str) -> str:
        if kind == "hotkey":
            src = str(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_hotkey_joy_button", 3))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_hotkey_vk", 0x7A))
            mods = int(self.cfg.OVERLAY.get("challenge_hotkey_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        if kind == "left":
            src = str(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_left_joy_button", 4))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_left_vk", 0x25))
            mods = int(self.cfg.OVERLAY.get("challenge_left_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        if kind == "right":
            src = str(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_right_joy_button", 5))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_right_vk", 0x27))
            mods = int(self.cfg.OVERLAY.get("challenge_right_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        return "Current: (none)"
        
    def _on_ch_volume_changed(self, val: int):
        self.lbl_ch_volume.setText(f"{val}%")
        self.cfg.OVERLAY["challenges_voice_volume"] = int(val)
        self.cfg.save()

    def _on_ch_mute_toggled(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["challenges_voice_mute"] = bool(is_checked)
        self.cfg.save()
    
    def _ch_results_path(self, rom: str) -> str:
        return os.path.join(self.cfg.BASE, "session_stats", "challenges", "history", f"{sanitize_filename(rom)}.json")

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

    def _open_flip_difficulty_overlay(self):
        try:
            if getattr(self, "_challenge_select", None):
                try:
                    self._challenge_select.hide()
                except Exception:
                    pass
            if getattr(self, "_flip_diff_select", None):
                try:
                    self._flip_diff_select.close()
                    self._flip_diff_select.deleteLater()
                except Exception:
                    pass
            self._flip_diff_select = FlipDifficultyOverlay(self, selected_idx=int(self._ch_flip_diff_idx),
                                                           options=list(self._flip_diff_options))
            self._flip_diff_select.show()
            self._flip_diff_select.raise_()
            self._ch_pick_flip_diff = True
        except Exception:
            self._flip_diff_select = None
            self._ch_pick_flip_diff = False

    def _close_flip_difficulty_overlay(self):
        try:
            if getattr(self, "_flip_diff_select", None):
                self._flip_diff_select.hide()
                self._flip_diff_select.close()
                self._flip_diff_select.deleteLater()
        except Exception:
            pass
        self._flip_diff_select = None
        self._ch_pick_flip_diff = False

    def _on_challenge_hotkey(self):
        try:
            import time as _time
            debounce_ms_cfg = int(self.cfg.OVERLAY.get("ch_hotkey_debounce_ms", 120))
            debounce_ms = max(120, debounce_ms_cfg)
            now = _time.monotonic()
            last = float(getattr(self, "_last_ch_hotkey_ts", 0.0) or 0.0)
            if debounce_ms > 0 and (now - last) < (debounce_ms / 1000.0):
                return
            self._last_ch_hotkey_ts = now
        except Exception:
            pass

        if not self._in_game_now():
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            try:
                self.bridge.challenge_info_show.emit(
                    "Challenge can only be started in-game.",
                    3,
                    "#FF3B30"
                )
            except Exception:
                pass
            return

        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            _has_map = bool(current_rom and self.watcher._has_any_map(current_rom))
        except Exception:
            _has_map = True

        if not _has_map:
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            try:
                self.bridge.challenge_info_show.emit(
                    "No NVRAM map available. Challenges require a map for score.",
                    3,
                    "#FF3B30"
                )
            except Exception:
                pass
            return

        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                name, flips = self._flip_diff_select.selected_option()
            except Exception:
                name, flips = ("Medium", 400)
            if int(flips) == -1:
                # Back/cancel: close flip difficulty overlay and re-show challenge select
                self._close_flip_difficulty_overlay()
                try:
                    ovw = getattr(self, "_challenge_select", None)
                    if ovw:
                        ovw.show()
                        ovw.raise_()
                    else:
                        self._open_challenge_select_overlay()
                except Exception:
                    pass
                return
            self._close_flip_difficulty_overlay()
            self._close_challenge_select_overlay()
            try:
                self.watcher.start_flip_challenge(int(flips))
            except Exception:
                pass
            return

        ovw = getattr(self, "_challenge_select", None)
        if ovw and ovw.isVisible():
            sel = int(getattr(self, "_ch_ov_selected_idx", 0) or 0) % 4
            if sel == 3:
                self._close_challenge_select_overlay()
                return
            elif sel == 0:
                self._close_challenge_select_overlay()
                try:
                    self.watcher.start_timed_challenge()
                except Exception:
                    pass
                return
            elif sel == 2:
                self._close_challenge_select_overlay()
                try:
                    self.watcher.start_heat_challenge()
                except Exception:
                    pass
                return
            else:
                self._open_flip_difficulty_overlay()
                return
        self._open_challenge_select_overlay()

    def _on_challenge_left(self):
        try:
            import time as _time
            now = _time.monotonic()
            if (now - float(getattr(self, "_last_ch_nav_ts", 0.0) or 0.0)) < 0.12:
                return
            self._last_ch_nav_ts = now
        except Exception:
            pass
        # Challenge left/right no longer navigates overlay pages
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            return
        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            if not (current_rom and self.watcher._has_any_map(current_rom)):
                # No NVRAM map – only allow navigating between Heat (2) and Exit (3)
                current = int(self._ch_ov_selected_idx) % 4
                if current == 3:
                    self._ch_ov_selected_idx = 2
                    ovw = getattr(self, "_challenge_select", None)
                    if ovw and ovw.isVisible():
                        try:
                            ovw.set_selected(2)
                        except Exception:
                            pass
                return
        except Exception:
            pass
        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                n = len(self._flip_diff_options)
                self._ch_flip_diff_idx = (int(self._ch_flip_diff_idx) - 1) % n
                self._flip_diff_select.set_selected(self._ch_flip_diff_idx)
            except Exception:
                pass
            return
        ovw = getattr(self, "_challenge_select", None)
        if not (ovw and ovw.isVisible()):
            return
        src = getattr(self, "_last_ch_event_src", None)
        if self._ch_active_source and src and self._ch_active_source != src:
            self._ch_active_source = src
        self._ch_ov_selected_idx = (int(self._ch_ov_selected_idx) - 1) % 4
        try:
            ovw.set_selected(self._ch_ov_selected_idx)
        except Exception:
            pass

    def _on_challenge_right(self):
        try:
            import time as _time
            now = _time.monotonic()
            if (now - float(getattr(self, "_last_ch_nav_ts", 0.0) or 0.0)) < 0.12:
                return
            self._last_ch_nav_ts = now
        except Exception:
            pass
        # Challenge left/right no longer navigates overlay pages
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            return
        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            if not (current_rom and self.watcher._has_any_map(current_rom)):
                # No NVRAM map – only allow navigating between Heat (2) and Exit (3)
                current = int(self._ch_ov_selected_idx) % 4
                if current == 2:
                    self._ch_ov_selected_idx = 3
                    ovw = getattr(self, "_challenge_select", None)
                    if ovw and ovw.isVisible():
                        try:
                            ovw.set_selected(3)
                        except Exception:
                            pass
                return
        except Exception:
            pass
        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                n = len(self._flip_diff_options)
                self._ch_flip_diff_idx = (int(self._ch_flip_diff_idx) + 1) % n
                self._flip_diff_select.set_selected(self._ch_flip_diff_idx)
            except Exception:
                pass
            return
        ovw = getattr(self, "_challenge_select", None)
        if not (ovw and ovw.isVisible()):
            return
        src = getattr(self, "_last_ch_event_src", None)
        if self._ch_active_source and src and self._ch_active_source != src:
            self._ch_active_source = src
        self._ch_ov_selected_idx = (int(self._ch_ov_selected_idx) + 1) % 4
        try:
            ovw.set_selected(self._ch_ov_selected_idx)
        except Exception:
            pass

    def _install_challenge_key_handling(self):
        try:
            if getattr(self, "_challenge_keyhook", None):
                try:
                    self._challenge_keyhook.uninstall()
                except Exception:
                    pass
        except Exception:
            pass
        self._challenge_keyhook = None
        if getattr(self.cfg, "LOG_CTRL", False):
            log(self.cfg, "[HOTKEY] challenge low-level hook disabled (using WM_HOTKEY)")
                    
    def _fmt_hms(self, seconds: int) -> str:
        try:
            seconds = int(seconds or 0)
        except Exception:
            seconds = 0
        d = seconds // 86400
        h = (seconds % 86400) // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if d > 0:
            return f"{d}d {h:02d}:{m:02d}:{s:02d}"
        return f"{h:02d}:{m:02d}:{s:02d}"
               
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
           
    def _prefetch_maps_now(self):
        try:
            self.watcher.start_prefetch_background()
            maps_dir = os.path.join(self.cfg.BASE, "tools", "NVRAM_Maps", "maps")
            QMessageBox.information(
                self, "Prefetch",
                f"Prefetch started. Missing maps are being cached in the background at:\n"
                f"{maps_dir}\n"
                "See watcher.log for progress."
            )
            log(self.cfg, "[PREFETCH] started by user")
        except Exception as e:
            log(self.cfg, f"[PREFETCH] failed: {e}", "ERROR")
            QMessageBox.warning(self, "Prefetch", f"Prefetch failed:\n{e}")
    def _style(self, widget, css: str):
        try:
            if widget:
                widget.setStyleSheet(css)
        except Exception:
            pass

    def _apply_theme(self):
        app = QApplication.instance()
        # Fusion ist die beste Basis für starke Custom-Themes
        app.setStyle("Fusion") 
        
        app.setStyleSheet(pinball_arcade_style)

        self._style(getattr(self, "btn_minimize", None), "background:#005c99; color:white; border:none;")
        self._style(getattr(self, "btn_quit", None), "background:#8a2525; color:white; border:none;")
        self._style(getattr(self, "btn_restart", None), "background:#008040; color:white; border:none;")

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
            "Theme settings coming soon."
        ),
        "appearance_sound": (
            "<b>🔊 Sound</b><br><br>"
            "Sound settings coming soon."
        ),
        "available_maps": (
            "<b>📚 Available Maps</b><br><br>"
            "This tab lists all known tables from the cloud index and your local VPX installation.<br><br>"
            "• <b>Search</b>: Filter by table name or ROM name.<br>"
            "• <b>🎯 Local tables with nvram map</b>: Show only local tables that have an NVRAM mapping.<br>"
            "• <b>⚡ Auto-Match All</b>: Automatically assign VPS-IDs to all local ROMs.<br>"
            "• <b>Columns</b>: Table name, ROM, NVRAM Map (✅/❌), local .vpx found (🟠), "
            "VPS-ID, author, and a detail button (+)."
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
    # TAB 1: DASHBOARD
    # ==========================================
    def _build_tab_dashboard(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp_status = QGroupBox("System Status")
        lay_status = QVBoxLayout(grp_status)
        self.status_label = QLabel("🟢 Watcher: RUNNING...")
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00E5FF; padding: 10px;")
        lay_status.addWidget(self.status_label)
        layout.addWidget(grp_status)

        # ── Session Summary: Last Run & Run Status cards ────────────────────────────
        grp_run_cards = QGroupBox("Session Summary")
        lay_run_cards = QHBoxLayout(grp_run_cards)

        # Left card: Last Run
        grp_last = QGroupBox("Last Run")
        lay_last = QVBoxLayout(grp_last)
        self.lbl_lr_table = QLabel("Table:  —")
        self.lbl_lr_score = QLabel("Score:  —")
        self.lbl_lr_achievements = QLabel("Achievements:  —")
        self.lbl_lr_result = QLabel("Last run:  —")
        for lbl in (self.lbl_lr_table, self.lbl_lr_score, self.lbl_lr_achievements, self.lbl_lr_result):
            lbl.setStyleSheet("color: #CCC; font-size: 9pt; padding: 2px 0;")
            lay_last.addWidget(lbl)
        lay_last.addStretch(1)

        # Right card: Run Status
        grp_run_status = QGroupBox("Run Status")
        lay_rs = QVBoxLayout(grp_run_status)
        self.lbl_rs_table = QLabel("Table:  —")
        self.lbl_rs_session = QLabel("Session:  —")
        self.lbl_rs_cloud = QLabel("Cloud:  —")
        self.lbl_rs_leaderboard = QLabel("Leaderboard:  —")
        for lbl in (self.lbl_rs_table, self.lbl_rs_session, self.lbl_rs_cloud, self.lbl_rs_leaderboard):
            lbl.setStyleSheet("color: #CCC; font-size: 9pt; padding: 2px 0;")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lay_rs.addWidget(lbl)
        lay_rs.addStretch(1)

        lay_run_cards.addWidget(grp_last)
        lay_run_cards.addWidget(grp_run_status)
        layout.addWidget(grp_run_cards)

        # ── 📬 Notifications ────────────────────────────────────────────────────
        grp_notif = QGroupBox("📬 Notifications")
        lay_notif_outer = QVBoxLayout(grp_notif)
        lay_notif_outer.setContentsMargins(6, 6, 6, 6)
        lay_notif_outer.setSpacing(4)

        # Top-right "Clear All" button
        row_notif_header = QHBoxLayout()
        row_notif_header.addStretch(1)
        btn_notif_clear = QPushButton("🗑️ Clear All")
        btn_notif_clear.setFixedHeight(22)
        btn_notif_clear.setStyleSheet(
            "QPushButton { background: #3a1a1a; color: #CC4444; border: 1px solid #5a2a2a; "
            "border-radius: 3px; font-size: 8pt; padding: 0 6px; }"
            "QPushButton:hover { background: #5a2a2a; }"
        )
        btn_notif_clear.clicked.connect(self._on_notif_clear_all)
        row_notif_header.addWidget(btn_notif_clear)
        lay_notif_outer.addLayout(row_notif_header)

        # Scroll area with notification rows
        notif_scroll = QScrollArea()
        notif_scroll.setWidgetResizable(True)
        notif_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        notif_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        notif_scroll.setFixedHeight(180)
        notif_scroll.setStyleSheet(
            "QScrollArea { background: #0e0e0e; border: 1px solid #2a2a2a; border-radius: 4px; }"
        )
        self._notif_container = QWidget()
        self._notif_container.setStyleSheet("background: transparent;")
        self._notif_list_layout = QVBoxLayout(self._notif_container)
        self._notif_list_layout.setContentsMargins(4, 4, 4, 4)
        self._notif_list_layout.setSpacing(2)
        self._notif_list_layout.addStretch(1)
        notif_scroll.setWidget(self._notif_container)
        lay_notif_outer.addWidget(notif_scroll)

        layout.addWidget(grp_notif)

        grp_actions = QGroupBox("Quick Actions")
        lay_actions = QHBoxLayout(grp_actions)
        self.btn_restart = QPushButton("Restart Engine")
        self.btn_restart.setStyleSheet("background:#008040; border:none;")
        self.btn_restart.clicked.connect(self._restart_watcher)
        self.btn_minimize = QPushButton("Minimize to Tray")
        self.btn_minimize.setStyleSheet("background:#005c99; border:none;")
        self.btn_minimize.clicked.connect(self.hide)
        self.btn_quit = QPushButton("Quit GUI")
        self.btn_quit.setStyleSheet("background:#8a2525; border:none;")
        self.btn_quit.clicked.connect(self.quit_all)

        lay_actions.addWidget(self.btn_restart)
        lay_actions.addStretch(1)
        lay_actions.addWidget(self.btn_minimize)
        lay_actions.addWidget(self.btn_quit)

        # Legend
        lbl_legend = QLabel(
            "<span style='color:#00C853;'>●</span> Green = online/verified"
            "&nbsp;&nbsp;&nbsp;"
            "<span style='color:#FFA500;'>●</span> Yellow = pending/local"
            "&nbsp;&nbsp;&nbsp;"
            "<span style='color:#FF3B30;'>●</span> Red = cloud off and table off"
        )
        lbl_legend.setTextFormat(Qt.TextFormat.RichText)
        lbl_legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_legend.setStyleSheet("color: #888; font-size: 9pt; padding: 4px;")
        layout.addWidget(lbl_legend)

        layout.addWidget(grp_actions)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "dashboard")

        self.main_tabs.addTab(tab, "🏠 Dashboard")
        QTimer.singleShot(1500, self._refresh_dashboard_cards)
        self._dashboard_refresh_timer = QTimer(self)
        self._dashboard_refresh_timer.setInterval(10000)
        self._dashboard_refresh_timer.timeout.connect(self._refresh_dashboard_cards)
        self._dashboard_refresh_timer.start()

        # Highscore-beaten polling timer (5 min, only when cloud enabled)
        self._highscore_poll_timer = QTimer(self)
        self._highscore_poll_timer.setInterval(self._HIGHSCORE_POLL_INTERVAL_MS)
        self._highscore_poll_timer.timeout.connect(self._poll_highscore_beaten)
        if getattr(self.cfg, "CLOUD_ENABLED", False):
            self._highscore_poll_timer.start()

    # ==========================================
    # TAB 2: PLAYER
    # ==========================================
    def _build_tab_player(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_level = QGroupBox("👑 Player Level")
        lay_level = QVBoxLayout(grp_level)

        self.lbl_prestige_stars = QLabel("☆☆☆☆☆")
        self.lbl_prestige_stars.setStyleSheet(
            "font-size: 22pt; font-weight: bold; color: #FFD700; "
            "padding: 4px 10px; letter-spacing: 8px;"
        )
        self.lbl_prestige_stars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_level.addWidget(self.lbl_prestige_stars)

        self.lbl_level_icon_name = QLabel("🪙  <b>Rookie</b>   Level 1")
        self.lbl_level_icon_name.setStyleSheet("font-size: 16pt; font-weight: bold; color: #FF7F00; padding: 6px 10px;")
        self.lbl_level_icon_name.setTextFormat(Qt.TextFormat.RichText)

        self.bar_level = QProgressBar()
        self.bar_level.setRange(0, 100)
        self.bar_level.setValue(0)
        self.bar_level.setTextVisible(False)
        self.bar_level.setFixedHeight(18)
        self.bar_level.setStyleSheet(
            "QProgressBar { border: 1px solid #444; border-radius: 4px; background: #222; }"
            "QProgressBar::chunk { background: #FF7F00; border-radius: 3px; }"
        )

        row_level_info = QHBoxLayout()
        self.lbl_level_count = QLabel("0 Achievements unlocked")
        self.lbl_level_count.setStyleSheet("color: #00E5FF; font-size: 10pt;")
        self.lbl_level_next = QLabel("")
        self.lbl_level_next.setStyleSheet("color: #888; font-size: 9pt;")
        self.lbl_level_next.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_level_info.addWidget(self.lbl_level_count)
        row_level_info.addStretch(1)
        row_level_info.addWidget(self.lbl_level_next)

        lay_level.addWidget(self.lbl_level_icon_name)
        lay_level.addWidget(self.bar_level)
        lay_level.addLayout(row_level_info)

        grp_level_table = QGroupBox("Level Table")
        lay_level_table = QVBoxLayout(grp_level_table)
        lv_browser = QTextBrowser()
        lv_browser.setMinimumHeight(280)
        lv_browser.setStyleSheet("background: #111; border: 1px solid #333;")
        lay_level_table.addWidget(lv_browser)
        self.lv_table_browser = lv_browser

        # ── Badges (inside Player Level, side by side with Level Table) ───────
        grp_badges = QGroupBox("🏅 Badges")
        lay_badges = QVBoxLayout(grp_badges)

        # Badge grid (flow of emoji icons)
        self.wgt_badge_grid = QWidget()
        self._badge_grid_layout = QGridLayout(self.wgt_badge_grid)
        self._badge_grid_layout.setSpacing(4)
        self._badge_grid_layout.setContentsMargins(4, 4, 4, 4)
        lay_badges.addWidget(self.wgt_badge_grid)

        # Badge count + selected badge display dropdown
        row_badge_bottom = QHBoxLayout()
        self.lbl_badge_count = QLabel("0 / 37 Badges")
        self.lbl_badge_count.setStyleSheet("color: #FF7F00; font-size: 10pt; font-weight: bold;")
        row_badge_bottom.addWidget(self.lbl_badge_count)
        row_badge_bottom.addStretch(1)
        lbl_display_badge = QLabel("Display Badge:")
        lbl_display_badge.setStyleSheet("color: #CCC; font-size: 9pt;")
        row_badge_bottom.addWidget(lbl_display_badge)
        self.cmb_badge_select = QComboBox()
        self.cmb_badge_select.setMinimumWidth(180)
        self.cmb_badge_select.setToolTip("Choose which badge icon to display next to your name on leaderboards")
        self.cmb_badge_select.currentIndexChanged.connect(self._on_badge_select_changed)
        row_badge_bottom.addWidget(self.cmb_badge_select)
        lay_badges.addLayout(row_badge_bottom)

        # Level Table (~40%) + Badges (~60%) side by side
        row_level_badges = QHBoxLayout()
        row_level_badges.addWidget(grp_level_table, 40)
        row_level_badges.addWidget(grp_badges, 60)
        lay_level.addLayout(row_level_badges)
        layout.addWidget(grp_level)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "player")

        self.main_tabs.addTab(tab, "👤 Player")
        QTimer.singleShot(1500, self._refresh_level_display)

    # ==========================================
    # TAB 3: APPEARANCE (Grid Layout)
    # ==========================================
    def _build_tab_appearance(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        appearance_subtabs = QTabWidget()
        tab_layout.addWidget(appearance_subtabs)

        # ── Overlay sub-tab ────────────────────────────────────────────────────
        overlay_tab = QWidget()
        overlay_tab_layout = QVBoxLayout(overlay_tab)
        overlay_tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        scroll.setWidget(inner)
        overlay_tab_layout.addWidget(scroll)

        grp_style = QGroupBox("Global Styling")
        lay_style = QGridLayout(grp_style)
        
        self.cmb_font_family = QFontComboBox()
        self.cmb_font_family.setCurrentFont(QFont(self.cfg.OVERLAY.get("font_family", "Segoe UI")))
        self.cmb_font_family.currentFontChanged.connect(self._on_font_family_changed)
        
        self.spn_font_size = QSpinBox()
        self.spn_font_size.setRange(8, 64)
        self.spn_font_size.setValue(int(self.cfg.OVERLAY.get("base_body_size", 20)))
        self.spn_font_size.valueChanged.connect(self._on_font_size_changed)

        self.sld_scale = QSlider(Qt.Orientation.Horizontal)
        self.sld_scale.setMinimum(30); self.sld_scale.setMaximum(300)
        self.sld_scale.setValue(int(self.cfg.OVERLAY.get("scale_pct", 100)))
        self.sld_scale.valueChanged.connect(self._on_overlay_scale)
        self.lbl_scale = QLabel(f"{self.sld_scale.value()}%")
        self.btn_scale_reset = QPushButton("100%")
        self.btn_scale_reset.setToolTip("Reset Overlay Scale to 100%")
        self.btn_scale_reset.clicked.connect(lambda: self.sld_scale.setValue(100))

        lay_style.addWidget(QLabel("Overlay Scale:"), 0, 0)
        lay_style.addWidget(self.sld_scale, 0, 1)
        lay_style.addWidget(self.lbl_scale, 0, 2)
        lay_style.addWidget(self.btn_scale_reset, 0, 3)

        lay_style.addWidget(QLabel("Font Family:"), 1, 0)
        lay_style.addWidget(self.cmb_font_family, 1, 1)
        lay_style.addWidget(QLabel("Base Size:"), 1, 2)
        lay_style.addWidget(self.spn_font_size, 1, 3)

        layout.addWidget(grp_style)

        grp_pos = QGroupBox("Widget Placement & Orientation")
        lay_pos = QGridLayout(grp_pos)

        self.btn_switch_all_orientation = QPushButton("🔄 Switch All → Portrait")
        self.btn_switch_all_orientation.setStyleSheet(
            "QPushButton { background: #FF7F00; color: #000; font-weight: bold; padding: 6px 16px; border-radius: 6px; font-size: 10pt; }"
            "QPushButton:hover { background: #FFA040; }"
        )
        self.btn_switch_all_orientation.clicked.connect(self._on_switch_all_portrait_landscape)
        _row_switch = QHBoxLayout()
        _row_switch.addWidget(self.btn_switch_all_orientation)
        _row_switch.addStretch(1)
        lay_pos.addLayout(_row_switch, 0, 0, 1, 2)

        def create_overlay_box(title, chk_port, chk_ccw, btn_place, btn_test=None, btn_hide=None, extra=None):
            box = QVBoxLayout()
            box.addWidget(QLabel(f"<b>{title}</b>"))
            box.addWidget(chk_port); box.addWidget(chk_ccw)
            btns = QHBoxLayout(); btns.addWidget(btn_place)
            if btn_test: btns.addWidget(btn_test)
            if btn_hide: btns.addWidget(btn_hide)
            box.addLayout(btns)
            if extra: box.addWidget(extra)
            box.addStretch(1)
            return box

        # 1) Main Overlay
        self.chk_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_portrait.setChecked(bool(self.cfg.OVERLAY.get("portrait_mode", True))); self.chk_portrait.stateChanged.connect(self._on_portrait_toggle)
        self.chk_portrait_ccw = QCheckBox("Rotate CCW"); self.chk_portrait_ccw.setChecked(bool(self.cfg.OVERLAY.get("portrait_rotate_ccw", True))); self.chk_portrait_ccw.stateChanged.connect(self._on_portrait_ccw_toggle)
        self.btn_overlay_place = QPushButton("Place"); self.btn_overlay_place.clicked.connect(self._on_overlay_place_clicked)
        self.btn_toggle_now = QPushButton("Test"); self.btn_toggle_now.clicked.connect(self._on_overlay_test_clicked)
        self.btn_hide = QPushButton("Hide"); self.btn_hide.clicked.connect(self._hide_overlay)
        self.chk_overlay_auto_close = QCheckBox("Auto-Close 1 min"); self.chk_overlay_auto_close.setChecked(bool(self.cfg.OVERLAY.get("overlay_auto_close", False))); self.chk_overlay_auto_close.stateChanged.connect(self._on_overlay_auto_close_toggle)
        box_main = create_overlay_box("Main Stats Overlay", self.chk_portrait, self.chk_portrait_ccw, self.btn_overlay_place, self.btn_toggle_now, self.btn_hide, self.chk_overlay_auto_close)

        # 2) Toasts
        self.chk_ach_toast_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ach_toast_portrait.setChecked(bool(self.cfg.OVERLAY.get("ach_toast_portrait", True))); self.chk_ach_toast_portrait.stateChanged.connect(self._on_ach_toast_portrait_toggle)
        self.chk_ach_toast_ccw = QCheckBox("Rotate CCW"); self.chk_ach_toast_ccw.setChecked(bool(self.cfg.OVERLAY.get("ach_toast_rotate_ccw", True))); self.chk_ach_toast_ccw.stateChanged.connect(self._on_ach_toast_ccw_toggle)
        self.btn_ach_toast_place = QPushButton("Place"); self.btn_ach_toast_place.clicked.connect(self._on_ach_toast_place_clicked)
        self.btn_test_toast = QPushButton("Test"); self.btn_test_toast.clicked.connect(lambda: self._ach_toast_mgr.enqueue("TEST – Achievement", "test_rom", 5))
        box_toast = create_overlay_box("Achievement Toasts", self.chk_ach_toast_portrait, self.chk_ach_toast_ccw, self.btn_ach_toast_place, self.btn_test_toast)

        # 3) Challenge Menu
        self.chk_ch_ov_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ch_ov_portrait.setChecked(bool(self.cfg.OVERLAY.get("ch_ov_portrait", True))); self.chk_ch_ov_portrait.stateChanged.connect(self._on_ch_ov_portrait_toggle)
        self.chk_ch_ov_ccw = QCheckBox("Rotate CCW"); self.chk_ch_ov_ccw.setChecked(bool(self.cfg.OVERLAY.get("ch_ov_rotate_ccw", True))); self.chk_ch_ov_ccw.stateChanged.connect(self._on_ch_ov_ccw_toggle)
        self.btn_ch_ov_place = QPushButton("Place"); self.btn_ch_ov_place.clicked.connect(self._on_ch_ov_place_clicked)
        self.btn_ch_ov_test = QPushButton("Test"); self.btn_ch_ov_test.clicked.connect(self._on_ch_ov_test)
        box_ch_sel = create_overlay_box("Challenge Menu", self.chk_ch_ov_portrait, self.chk_ch_ov_ccw, self.btn_ch_ov_place, self.btn_ch_ov_test)

        # 4) Timers & Counters
        self.chk_ch_timer_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ch_timer_portrait.setChecked(bool(self.cfg.OVERLAY.get("ch_timer_portrait", True))); self.chk_ch_timer_portrait.stateChanged.connect(self._on_ch_timer_portrait_toggle)
        self.chk_ch_timer_ccw = QCheckBox("Rotate CCW"); self.chk_ch_timer_ccw.setChecked(bool(self.cfg.OVERLAY.get("ch_timer_rotate_ccw", True))); self.chk_ch_timer_ccw.stateChanged.connect(self._on_ch_timer_ccw_toggle)
        box_tc = QVBoxLayout(); box_tc.addWidget(QLabel("<b>Timers & Counters</b>")); box_tc.addWidget(self.chk_ch_timer_portrait); box_tc.addWidget(self.chk_ch_timer_ccw)
        btn_r1 = QHBoxLayout(); self.btn_ch_timer_place = QPushButton("Place Timer"); self.btn_ch_timer_place.clicked.connect(self._on_ch_timer_place_clicked); self.btn_ch_timer_test = QPushButton("Test Timer"); self.btn_ch_timer_test.clicked.connect(self._on_ch_timer_test); btn_r1.addWidget(self.btn_ch_timer_place); btn_r1.addWidget(self.btn_ch_timer_test)
        btn_r2 = QHBoxLayout(); self.btn_flip_counter_place = QPushButton("Place Counter"); self.btn_flip_counter_place.clicked.connect(self._on_flip_counter_place_clicked); self.btn_flip_counter_test = QPushButton("Test Counter"); self.btn_flip_counter_test.clicked.connect(self._on_flip_counter_test); btn_r2.addWidget(self.btn_flip_counter_place); btn_r2.addWidget(self.btn_flip_counter_test)
        box_tc.addLayout(btn_r1); box_tc.addLayout(btn_r2); box_tc.addStretch(1)

        self.chk_flip_counter_portrait = self.chk_ch_timer_portrait
        self.chk_flip_counter_ccw = self.chk_ch_timer_ccw

        # 5) NEU: Mini Info / Notifications Overlay
        self.chk_mini_info_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_mini_info_portrait.setChecked(bool(self.cfg.OVERLAY.get("notifications_portrait", True))); self.chk_mini_info_portrait.stateChanged.connect(self._on_mini_info_portrait_toggle)
        self.chk_mini_info_ccw = QCheckBox("Rotate CCW"); self.chk_mini_info_ccw.setChecked(bool(self.cfg.OVERLAY.get("notifications_rotate_ccw", True))); self.chk_mini_info_ccw.stateChanged.connect(self._on_mini_info_ccw_toggle)
        self.btn_mini_info_place = QPushButton("Place"); self.btn_mini_info_place.clicked.connect(self._on_mini_info_place_clicked)
        self.btn_mini_info_test = QPushButton("Test"); self.btn_mini_info_test.clicked.connect(self._on_mini_info_test)
        box_mini_info = create_overlay_box("System Notifications", self.chk_mini_info_portrait, self.chk_mini_info_ccw, self.btn_mini_info_place, self.btn_mini_info_test)

        # 6) Heat Bar
        self.chk_heat_bar_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_heat_bar_portrait.setChecked(bool(self.cfg.OVERLAY.get("heat_bar_portrait", False))); self.chk_heat_bar_portrait.stateChanged.connect(self._on_heat_bar_portrait_toggle)
        self.chk_heat_bar_ccw = QCheckBox("Rotate CCW"); self.chk_heat_bar_ccw.setChecked(bool(self.cfg.OVERLAY.get("heat_bar_rotate_ccw", True))); self.chk_heat_bar_ccw.stateChanged.connect(self._on_heat_bar_ccw_toggle)
        self.btn_heat_bar_place = QPushButton("Place"); self.btn_heat_bar_place.clicked.connect(self._on_heat_bar_place_clicked)
        self.btn_heat_bar_test = QPushButton("Test"); self.btn_heat_bar_test.clicked.connect(self._on_heat_bar_test)
        box_heat_bar = create_overlay_box("Heat Bar (Heat Challenge)", self.chk_heat_bar_portrait, self.chk_heat_bar_ccw, self.btn_heat_bar_place, self.btn_heat_bar_test)

        # 7) Status Overlay (cloud / leaderboard status messages)
        self.chk_status_overlay_enabled = QCheckBox("Enabled"); self.chk_status_overlay_enabled.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_enabled", True))); self.chk_status_overlay_enabled.stateChanged.connect(self._on_status_overlay_enabled_toggle)
        self.chk_status_overlay_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_status_overlay_portrait.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_portrait", False))); self.chk_status_overlay_portrait.stateChanged.connect(self._on_status_overlay_portrait_toggle)
        self.chk_status_overlay_ccw = QCheckBox("Rotate CCW"); self.chk_status_overlay_ccw.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_rotate_ccw", False))); self.chk_status_overlay_ccw.stateChanged.connect(self._on_status_overlay_ccw_toggle)
        self.btn_status_overlay_place = QPushButton("Place"); self.btn_status_overlay_place.clicked.connect(self._on_status_overlay_place_clicked)
        self.btn_status_overlay_test = QPushButton("Test"); self.btn_status_overlay_test.clicked.connect(self._on_status_overlay_test)
        box_status_overlay = QVBoxLayout()
        box_status_overlay.addWidget(QLabel("<b>Status Overlay</b>"))
        box_status_overlay.addWidget(self.chk_status_overlay_enabled)
        box_status_overlay.addWidget(self.chk_status_overlay_portrait)
        box_status_overlay.addWidget(self.chk_status_overlay_ccw)
        _btns_status = QHBoxLayout(); _btns_status.addWidget(self.btn_status_overlay_place); _btns_status.addWidget(self.btn_status_overlay_test)
        box_status_overlay.addLayout(_btns_status)
        box_status_overlay.addStretch(1)

        lay_pos.addLayout(box_main, 1, 0); lay_pos.addLayout(box_toast, 1, 1)
        lay_pos.addLayout(box_ch_sel, 2, 0); lay_pos.addLayout(box_tc, 2, 1)
        lay_pos.addLayout(box_mini_info, 3, 0); lay_pos.addLayout(box_heat_bar, 3, 1)
        lay_pos.addLayout(box_status_overlay, 4, 0)

        layout.addWidget(grp_pos)

        # ── Overlay Pages toggle ────────────────────────────────────────────────
        grp_pages = QGroupBox("📄 Overlay Pages")
        lay_pages = QVBoxLayout(grp_pages)

        lbl_page1 = QLabel("Page 1 (Highlights & Score) is always active.")
        lbl_page1.setStyleSheet("color: #FF7F00; font-size: 9pt;")
        lay_pages.addWidget(lbl_page1)

        lbl_hint = QLabel("Disable pages you don't need — they will be skipped when cycling through the overlay.")
        lbl_hint.setStyleSheet("color: #AAA; font-size: 9pt; font-style: italic;")
        lbl_hint.setWordWrap(True)
        lay_pages.addWidget(lbl_hint)

        self.chk_overlay_page2 = QCheckBox("Page 2: Achievement Progress")
        self.chk_overlay_page2.setChecked(bool(self.cfg.OVERLAY.get("overlay_page2_enabled", True)))
        self.chk_overlay_page2.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page2)

        self.chk_overlay_page3 = QCheckBox("Page 3: Challenge Leaderboard")
        self.chk_overlay_page3.setChecked(bool(self.cfg.OVERLAY.get("overlay_page3_enabled", True)))
        self.chk_overlay_page3.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page3)

        self.chk_overlay_page4 = QCheckBox("Page 4: Cloud Leaderboard")
        self.chk_overlay_page4.setChecked(bool(self.cfg.OVERLAY.get("overlay_page4_enabled", True)))
        self.chk_overlay_page4.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page4)

        self.chk_overlay_page5 = QCheckBox("Page 5: VPC Leaderboard")
        self.chk_overlay_page5.setChecked(bool(self.cfg.OVERLAY.get("overlay_page5_enabled", True)))
        self.chk_overlay_page5.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page5)

        layout.addWidget(grp_pages)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "appearance_overlay")
        self._update_switch_all_button_label()
        appearance_subtabs.addTab(overlay_tab, "🖼 Overlay")

        # ── Theme sub-tab (placeholder) ────────────────────────────────────────
        theme_tab = QWidget()
        theme_layout = QVBoxLayout(theme_tab)
        theme_layout.addWidget(QLabel("Theme settings coming soon..."))
        theme_layout.addStretch(1)
        self._add_tab_help_button(theme_layout, "appearance_theme")
        appearance_subtabs.addTab(theme_tab, "🎨 Theme")

        # ── Sound sub-tab ──────────────────────────────────────────────────────
        sound_tab = QWidget()
        sound_outer = QVBoxLayout(sound_tab)
        sound_scroll = QScrollArea()
        sound_scroll.setWidgetResizable(True)
        sound_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sound_inner = QWidget()
        sound_layout = QVBoxLayout(sound_inner)
        sound_layout.setContentsMargins(8, 8, 8, 8)

        # Title
        lbl_sound_title = QLabel("🔊 Sound Effects")
        lbl_sound_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #FF7F00; padding: 4px 0;")
        sound_layout.addWidget(lbl_sound_title)

        # Enable + Volume row
        row_enable = QHBoxLayout()
        self.chk_sound_enabled = QCheckBox("Enable Sound Effects")
        self.chk_sound_enabled.setChecked(bool(self.cfg.OVERLAY.get("sound_enabled", True)))
        def _on_sound_enabled(state):
            self.cfg.OVERLAY["sound_enabled"] = bool(state)
            self.cfg.save()
        self.chk_sound_enabled.stateChanged.connect(_on_sound_enabled)
        row_enable.addWidget(self.chk_sound_enabled)
        row_enable.addSpacing(20)

        lbl_vol = QLabel("Volume:")
        row_enable.addWidget(lbl_vol)
        self.sld_sound_volume = QSlider(Qt.Orientation.Horizontal)
        self.sld_sound_volume.setRange(0, 100)
        self.sld_sound_volume.setValue(int(self.cfg.OVERLAY.get("sound_volume", sound.DEFAULT_VOLUME)))
        self.sld_sound_volume.setFixedWidth(180)
        self.sld_sound_volume.setStyleSheet(
            "QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #FF7F00; width: 14px; margin: -4px 0; border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #FF7F00; border-radius: 3px; }"
        )
        self.lbl_sound_vol_pct = QLabel(f"{self.sld_sound_volume.value()}%")
        self.lbl_sound_vol_pct.setMinimumWidth(36)
        def _on_sound_volume(val):
            self.lbl_sound_vol_pct.setText(f"{val}%")
            self.cfg.OVERLAY["sound_volume"] = val
            self.cfg.save()
        self.sld_sound_volume.valueChanged.connect(_on_sound_volume)
        row_enable.addWidget(self.sld_sound_volume)
        row_enable.addWidget(self.lbl_sound_vol_pct)
        row_enable.addStretch(1)
        sound_layout.addLayout(row_enable)

        # Sound Pack
        row_pack = QHBoxLayout()
        lbl_pack = QLabel("Sound Pack:")
        lbl_pack.setStyleSheet("font-weight: bold;")
        row_pack.addWidget(lbl_pack)
        self.cmb_sound_pack = QComboBox()
        self.cmb_sound_pack.setFixedWidth(160)
        for pack_id, pack_name in sound.SOUND_PACKS.items():
            self.cmb_sound_pack.addItem(pack_name, pack_id)
        cur_pack = str(self.cfg.OVERLAY.get("sound_pack", "zaptron"))
        idx = self.cmb_sound_pack.findData(cur_pack)
        if idx >= 0:
            self.cmb_sound_pack.setCurrentIndex(idx)
        def _on_sound_pack(idx):
            self.cfg.OVERLAY["sound_pack"] = self.cmb_sound_pack.itemData(idx)
            self.cfg.save()
        self.cmb_sound_pack.currentIndexChanged.connect(_on_sound_pack)
        row_pack.addWidget(self.cmb_sound_pack)
        row_pack.addStretch(1)
        sound_layout.addLayout(row_pack)

        # Events group
        lbl_events = QLabel("Events")
        lbl_events.setStyleSheet("font-size: 11pt; font-weight: bold; color: #00E5FF; margin-top: 6px;")
        sound_layout.addWidget(lbl_events)

        tbl_sound = QTableWidget(len(sound.SOUND_EVENTS), 3)
        tbl_sound.setHorizontalHeaderLabels(["Event", "Enabled", "Test"])
        tbl_sound.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tbl_sound.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        tbl_sound.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tbl_sound.setColumnWidth(1, 60)
        tbl_sound.setColumnWidth(2, 50)
        tbl_sound.verticalHeader().setDefaultSectionSize(28)
        tbl_sound.verticalHeader().setVisible(False)
        tbl_sound.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl_sound.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl_sound.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl_sound.setShowGrid(False)
        tbl_sound.setAlternatingRowColors(True)
        tbl_sound.setStyleSheet(
            "QTableWidget { background: #111; alternate-background-color: #1a1a1a; border: 1px solid #333; }"
            "QTableWidget::item { padding: 2px 6px; }"
        )

        cur_events = self.cfg.OVERLAY.get("sound_events") or {}

        for row, (event_id, event_label) in enumerate(sound.SOUND_EVENTS):
            lbl_item = QTableWidgetItem(event_label)
            lbl_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tbl_sound.setItem(row, 0, lbl_item)

            chk_event = QCheckBox()
            chk_event.setChecked(bool(cur_events.get(event_id, True)))
            chk_event.setToolTip(f"Enable/disable sound for {event_label}")
            chk_event.setStyleSheet(
                "QCheckBox::indicator { width: 18px; height: 18px; }"
                "QCheckBox::indicator:checked { background: #00E5FF; border: 1px solid #00B8D4; border-radius: 2px; }"
                "QCheckBox::indicator:unchecked { background: #333; border: 1px solid #555; border-radius: 2px; }"
            )

            def _make_event_handler(eid):
                def _handler(state):
                    ev = self.cfg.OVERLAY.setdefault("sound_events", {})
                    ev[eid] = bool(state)
                    self.cfg.save()
                return _handler

            chk_event.stateChanged.connect(_make_event_handler(event_id))
            cell_chk = QWidget()
            cell_lay = QHBoxLayout(cell_chk)
            cell_lay.setContentsMargins(0, 0, 0, 0)
            cell_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_lay.addWidget(chk_event)
            tbl_sound.setCellWidget(row, 1, cell_chk)

            btn_test = QPushButton("▶")
            btn_test.setFixedSize(32, 24)
            btn_test.setToolTip(f"Preview sound for {event_label}")
            btn_test.setStyleSheet(
                "QPushButton { background: #333; color: #00E5FF; border: 1px solid #555; border-radius: 3px; font-size: 14px; padding: 0px; }"
                "QPushButton:hover { background: #444; }"
                "QPushButton:pressed { background: #555; }"
            )

            def _make_preview(eid):
                def _preview():
                    sound.play_sound_preview(self.cfg, eid)
                return _preview

            btn_test.clicked.connect(_make_preview(event_id))
            cell_btn = QWidget()
            cell_btn_lay = QHBoxLayout(cell_btn)
            cell_btn_lay.setContentsMargins(2, 1, 2, 1)
            cell_btn_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_btn_lay.addWidget(btn_test)
            tbl_sound.setCellWidget(row, 2, cell_btn)

        tbl_sound.resizeRowsToContents()
        tbl_sound.setMinimumHeight(len(sound.SOUND_EVENTS) * 28 + 30)
        sound_layout.addWidget(tbl_sound)

        sound_layout.addStretch(1)
        self._add_tab_help_button(sound_layout, "appearance_sound")
        sound_scroll.setWidget(sound_inner)
        sound_outer.addWidget(sound_scroll)
        appearance_subtabs.addTab(sound_tab, "🔊 Sound")

        self.main_tabs.addTab(tab, "🎨 Appearance")

    def _portrait_checkboxes(self):
        """Returns the list of all overlay portrait-mode checkboxes."""
        return [
            self.chk_portrait,
            self.chk_ach_toast_portrait,
            self.chk_ch_ov_portrait,
            self.chk_ch_timer_portrait,
            self.chk_mini_info_portrait,
            self.chk_heat_bar_portrait,
            self.chk_status_overlay_portrait,
        ]

    def _ccw_checkboxes(self):
        """Returns the list of all overlay CCW-rotation checkboxes."""
        return [
            self.chk_portrait_ccw,
            self.chk_ach_toast_ccw,
            self.chk_ch_ov_ccw,
            self.chk_ch_timer_ccw,
            self.chk_mini_info_ccw,
            self.chk_heat_bar_ccw,
            self.chk_status_overlay_ccw,
        ]

    def _update_switch_all_button_label(self):
        """Updates the Switch All button label to reflect current portrait checkbox state."""
        try:
            if any(chk.isChecked() for chk in self._portrait_checkboxes()):
                self.btn_switch_all_orientation.setText("🔄 Switch All → Landscape")
            else:
                self.btn_switch_all_orientation.setText("🔄 Switch All → Portrait")
        except AttributeError:
            # During _build_tab_appearance() the checkboxes are created one by one;
            # stateChanged may fire before all 7 checkboxes or the button exist yet.
            pass

    def _on_switch_all_portrait_landscape(self):
        """Toggles all overlay portrait + CCW checkboxes between Portrait and Landscape at once."""
        should_be_portrait = not any(chk.isChecked() for chk in self._portrait_checkboxes())
        for chk in self._portrait_checkboxes():
            chk.setChecked(should_be_portrait)
        for chk in self._ccw_checkboxes():
            chk.setChecked(should_be_portrait)
        self.cfg.save()
        self._update_switch_all_button_label()

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

    def _build_tab_progress(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp = QGroupBox("Local Achievement Progress")
        lay = QVBoxLayout(grp)
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Select Table:"))
        self.cmb_progress_rom = QComboBox()
        self.cmb_progress_rom.currentIndexChanged.connect(self._on_progress_rom_changed)
        row.addWidget(self.cmb_progress_rom)

        self.lbl_progress_rom_name = QLabel("")
        self.lbl_progress_rom_name.setStyleSheet("color:#00E5FF; font-weight:bold; margin-left: 10px;")
        row.addWidget(self.lbl_progress_rom_name)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setStyleSheet("background:#00E5FF; color:black; font-weight:bold;")
        btn_refresh.clicked.connect(self._refresh_progress_roms)
        row.addWidget(btn_refresh)
        lay.addLayout(row)
        
        self.progress_view = QTextBrowser()
        self.progress_view.setOpenLinks(False)
        self.progress_view.anchorClicked.connect(self._on_progress_anchor_clicked)
        lay.addWidget(self.progress_view)
        
        layout.addWidget(grp)
        self._add_tab_help_button(layout, "progress")
        self.main_tabs.addTab(tab, "📈 Progress")
        
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, self._refresh_progress_roms)

    def _refresh_progress_roms(self):
        self.cmb_progress_rom.blockSignals(True)
        self.cmb_progress_rom.clear()
        
        roms = set()
        
        state = self.watcher._ach_state_load()
        roms.update(state.get("global", {}).keys())
        roms.update(state.get("session", {}).keys())
        
        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        if os.path.isdir(stats_dir):
            for fn in os.listdir(stats_dir):
                if fn.lower().endswith(".txt"):
                    parts = fn.split("__")
                    if len(parts) >= 2:
                        roms.add(parts[0])
                        
        valid_roms = sorted([r for r in roms if self.watcher._has_any_map(r)])
        
        self.cmb_progress_rom.addItem("Global", "Global")
        
        if valid_roms:
            romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
            for r in valid_roms:
                title = _strip_version_from_name(romnames.get(r, r))
                self.cmb_progress_rom.addItem(title, r)
            
        self.cmb_progress_rom.blockSignals(False)
        self._on_progress_rom_changed()

    def _get_manufacturer_progress_for_display(self, cond: dict, global_tally: dict, title: str) -> tuple:
        """Return (progress, need) for display in the progress bar for manufacturer-based conditions.
        Reads roms_played from global_tally cache stored by _evaluate_achievements."""
        rtype = str(cond.get("type") or "").lower()
        tally = global_tally.get(title, {})
        progress = int(tally.get("progress", 0))
        if rtype == "rom_count":
            manufacturer = cond.get("manufacturer", "")
            if manufacturer == "__any__":
                min_brands = cond.get("min_brands")
                if min_brands is not None:
                    return progress, int(min_brands)
                else:
                    return progress, int(cond.get("min", 1))
            else:
                return progress, int(cond.get("min", 1))
        elif rtype == "rom_complete_set":
            installed_count = int(tally.get("installed_count", 0))
            if installed_count > 0:
                return progress, installed_count
            # installed_count not yet cached (no session evaluated); show progress/progress
            # to avoid division-by-zero, use max(progress, 1) as the denominator
            return progress, max(progress, 1)
        elif rtype == "rom_multi_brand":
            manufacturers = cond.get("manufacturers") or []
            installed_count = int(tally.get("installed_count", len(manufacturers)))
            return progress, installed_count
        return 0, 1

    def _fetch_rarity_bg(self, rom):
        """Fetch rarity data in background and refresh progress tab when done."""
        def _worker():
            try:
                rarity_data, total = CloudSync.fetch_rarity_for_rom(self.cfg, rom)
                self._rarity_cache[rom] = {"data": rarity_data, "ts": time.time(), "total_players": total}
                from PyQt6.QtCore import QTimer as _QTimer
                _QTimer.singleShot(0, self._on_progress_rom_changed)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _on_progress_rom_changed(self):
        rom = self.cmb_progress_rom.currentData()
        if not rom:
            rom = self.cmb_progress_rom.currentText()

        # Update colored ROM name label next to the dropdown
        self.lbl_progress_rom_name.setText(rom if (rom and rom != "Global") else "")

        if not rom:
            self.progress_view.setHtml("<div style='text-align:center; color:#888;'>(No data available)</div>")
            return

        # ── Rarity: trigger background fetch when cloud is enabled ──────────
        _RARITY_TTL = 300  # 5 minutes
        if self.cfg.CLOUD_ENABLED and rom != "Global":
            cached = self._rarity_cache.get(rom)
            if cached is None or (time.time() - cached.get("ts", 0)) > _RARITY_TTL:
                self._fetch_rarity_bg(rom)
        rarity_map: dict = {}
        if rom != "Global":
            cached = self._rarity_cache.get(rom)
            if cached:
                rarity_map = cached.get("data", {})

        state = self.watcher._ach_state_load()
        unlocked_titles = set()
        all_rules = []

        if rom == "Global":
            import json, os
            gp = f_global_ach(self.cfg)
            if os.path.exists(gp):
                try:
                    with open(gp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        all_rules = data.get("rules", [])
                except Exception:
                    pass
            for r_key, entries in state.get("global", {}).items():
                for e in entries:
                    t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                    unlocked_titles.add(t)
        else:
            s_rules = self.watcher._collect_player_rules_for_rom(rom)
            
            seen_rule_titles = set()
            for r in s_rules:
                if isinstance(r, dict) and r.get("title"):
                    t = str(r.get("title")).strip()
                    if t not in seen_rule_titles:
                        seen_rule_titles.add(t)
                        all_rules.append(r)
            
            for e in state.get("session", {}).get(rom, []):
                t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                unlocked_titles.add(t)
        
        if not all_rules:
            if rom == "Global":
                self.progress_view.setHtml("<div style='color:#FF7F00; text-align:center;'>No global achievements defined.</div>")
            else:
                self.progress_view.setHtml("<div style='color:#FF7F00; text-align:center;'>No specific achievements defined for this ROM.</div>")
            return
            
        global_tally = state.get("global_tally", {}) if rom == "Global" else {}

        # Pre-compute live NVRAM totals for nvram_tally so that the progress
        # bars reflect actual NVRAM data even without a recent session evaluation.
        _live_nvram_cache: dict = {}  # field -> live total across all played ROMs
        _live_nvram_audits: dict = {}  # rom -> audits (shared across field lookups)
        _roms_played_for_live: list = list(state.get("roms_played") or []) if rom == "Global" else []

        def _live_nvram_total(field: str) -> int:
            if not _roms_played_for_live:
                return 0
            if field not in _live_nvram_cache:
                try:
                    val = self.watcher._sum_field_across_all_roms(
                        field, _roms_played_for_live, _live_nvram_audits
                    )
                except Exception:
                    val = 0
                _live_nvram_cache[field] = val
            return _live_nvram_cache[field]

        html = ["<style>table {border-collapse:collapse;} td {width:25%; padding:3px 4px; border-bottom:1px solid #444; text-align:center;} .unlocked {color:#00E5FF; font-weight:bold;} .locked {color:#666; font-size:0.85em;}</style>"]

        def _tooltip_for_rule(rule, unlocked=False):
            cond = rule.get("condition", {}) or {}
            rtype = str(cond.get("type", "")).lower()
            prefix = "✅ Unlocked! " if unlocked else ""
            if rtype == "session_time":
                seconds = cond.get("min_seconds", cond.get("min", 0))
                mins = round(int(seconds) / 60)
                return f"{prefix}Accumulate {mins} minutes of total play time across all sessions"
            elif rtype == "nvram_tally":
                field = cond.get("field", "")
                need = int(cond.get("min", 1))
                return f"{prefix}Reach {need} total {field} across all played tables"
            elif rtype == "rom_count":
                mfr = cond.get("manufacturer", "")
                if mfr == "__any__":
                    min_brands = cond.get("min_brands")
                    if min_brands:
                        return f"{prefix}Play tables from {int(min_brands)} different manufacturers"
                    else:
                        return f"{prefix}Play {int(cond.get('min', 1))} different tables"
                return f"{prefix}Play {int(cond.get('min', 1))} different {mfr} tables"
            elif rtype == "rom_complete_set":
                mfr = cond.get("manufacturer", "")
                if mfr == "__any__":
                    return f"{prefix}Play every installed table"
                return f"{prefix}Play every installed {mfr} table"
            elif rtype == "rom_multi_brand":
                mfrs = cond.get("manufacturers", [])
                return f"{prefix}Play at least one table from each: {', '.join(mfrs)}"
            elif rtype == "challenge_count":
                ct = cond.get("challenge_type", "")
                need = int(cond.get("min", 1))
                return f"{prefix}Complete {need} {ct} challenge{'s' if need != 1 else ''}"
            return prefix + "Achievement"

        unlocked_count = 0
        cells = []
        for r in all_rules:
            title = str(r.get("title", "Unknown")).strip()
            clean_title = title.replace(" (Session)", "").replace(" (Global)", "")

            # Build ℹ️ info link for ROM-specific achievements only
            if rom != "Global":
                encoded = _urlparse.quote(title, safe="")
                info_link = f" <a href='achinfo://{rom}/{encoded}' style='color:#00E5FF; text-decoration:none;'>ℹ️</a>"
            else:
                info_link = ""

            # Rarity label (ROM-specific only, when cloud data is available)
            rarity_label = ""
            if rarity_map:
                ri = rarity_map.get(title) or rarity_map.get(clean_title)
                if ri:
                    rarity_label = (
                        f"<br><span style='font-size:0.7em;color:{ri['color']};'>"
                        f"{ri['tier']} ({ri['pct']}%)</span>"
                    )

            if title in unlocked_titles or clean_title in unlocked_titles:
                unlocked_count += 1
                tooltip = _tooltip_for_rule(r, unlocked=True).replace("'", "&#39;")
                cells.append(f"<td class='unlocked' title='{tooltip}'>✅ {clean_title}{info_link}{rarity_label}</td>")
            else:
                cond = r.get("condition", {}) or {}
                rtype_display = str(cond.get("type", "")).lower()
                tooltip = _tooltip_for_rule(r, unlocked=False).replace("'", "&#39;")
                if rom == "Global" and rtype_display in ("nvram_tally", "rom_count", "rom_complete_set", "rom_multi_brand", "challenge_count"):
                    if rtype_display in ("nvram_tally", "challenge_count"):
                        need = int(cond.get("min", 1))
                        tally = global_tally.get(title, {})
                        cached_progress = int(tally.get("progress", 0))
                        field = cond.get("field") or ""
                        live_progress = _live_nvram_total(field) if field else 0
                        progress = max(cached_progress, live_progress)
                        cells.append(
                            f"<td class='locked' title='{tooltip}'>🔒 {clean_title}<br>"
                            f"<span style='font-size:0.75em;color:#FF7F00;'>{progress}/{need}</span>{rarity_label}</td>"
                        )
                    else:
                        progress, need = self._get_manufacturer_progress_for_display(cond, global_tally, title)
                        cells.append(
                            f"<td class='locked' title='{tooltip}'>🔒 {clean_title}<br>"
                            f"<span style='font-size:0.75em;color:#FF7F00;'>{progress}/{need}</span>{rarity_label}</td>"
                        )
                else:
                    cells.append(f"<td class='locked' title='{tooltip}'>🔒 {clean_title}{rarity_label}</td>")
                
        pct = round((unlocked_count / len(all_rules)) * 100, 1) if all_rules else 0
        
        if rom == "Global":
            rom_label = "Global Achievements"
        else:
            romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
            clean_rom = _strip_version_from_name(romnames.get(rom, "")) or romnames.get(rom, "") or rom
            rom_label = clean_rom
        html.append(f"<div style='font-size:1.1em; color:#FFFFFF; text-align:center; margin-bottom:5px; font-weight:bold;'>{rom_label}</div>")

        html.append(f"<div style='font-size:1.0em; color:#FF7F00; text-align:center; margin-bottom:8px; font-weight:bold;'>Progress: {unlocked_count} / {len(all_rules)} ({pct}%)</div>")

        # ── Rarity legend ──────────────────────────────────────────────────────
        if rarity_map:
            rarity_tooltips = {
                "Common": "Unlocked by more than 50% of players",
                "Uncommon": "Unlocked by 20–50% of players",
                "Rare": "Unlocked by 5–20% of players",
                "Epic": "Unlocked by 1–5% of players",
                "Legendary": "Unlocked by less than 1% of players",
            }
            legend_parts = "".join(
                f"<span style='color:{color}; margin:0 6px; cursor:help;' "
                f"title='{rarity_tooltips.get(name, '')}'>"
                f"■ {name}</span>"
                for _, name, color in RARITY_TIERS
            )
            html.append(
                f"<div style='text-align:center; font-size:0.78em; margin-bottom:18px;'>"
                f"Rarity: {legend_parts}</div>"
            )

        html.append("<table align='center' width='100%'>")
        COLUMNS = 4
        for i in range(0, len(cells), COLUMNS):
            html.append("<tr>")
            for j in range(COLUMNS):
                if i + j < len(cells):
                    html.append(cells[i + j])
                else:
                    html.append("<td></td>")
            html.append("</tr>")
        html.append("</table>")
        
        final_html = "".join(html)

        try:
            sb = self.progress_view.verticalScrollBar()
            old_val = sb.value()
            self.progress_view.setHtml(final_html)
            sb.setValue(old_val)
        except Exception:
            self.progress_view.setHtml(final_html)

    def _on_progress_anchor_clicked(self, url):
        """Handle ℹ️ anchor clicks in the progress view."""
        url_str = url.toString() if isinstance(url, QUrl) else str(url)
        if not url_str.startswith("achinfo://"):
            return
        # Parse achinfo://ROM/ENCODED_TITLE
        rest = url_str[len("achinfo://"):]
        parts = rest.split("/", 1)
        if len(parts) < 2:
            return
        rom = parts[0]
        title = _urlparse.unquote(parts[1])

        # Find the rule for this achievement
        rule = None
        try:
            s_rules = self.watcher._collect_player_rules_for_rom(rom)
            for r in s_rules:
                if isinstance(r, dict):
                    t = str(r.get("title", "")).strip()
                    clean = t.replace(" (Session)", "").replace(" (Global)", "")
                    if t == title or clean == title:
                        rule = r
                        break
        except Exception:
            pass

        # Find unlock entry (with timestamp if available)
        # Search both session and global achievement buckets to handle
        # all achievement types (session-specific and global).
        unlock_entry = None
        try:
            state = self.watcher._ach_state_load()
            # 1. Search session achievements for this ROM
            for e in state.get("session", {}).get(rom, []):
                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                clean = t.replace(" (Session)", "").replace(" (Global)", "")
                if t == title or clean == title:
                    unlock_entry = e if isinstance(e, dict) else {"title": e}
                    break
            # 2. If not found, also search the global "__global__" bucket
            if unlock_entry is None:
                for e in state.get("global", {}).get("__global__", []):
                    t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                    clean = t.replace(" (Session)", "").replace(" (Global)", "")
                    if t == title or clean == title:
                        unlock_entry = e if isinstance(e, dict) else {"title": e}
                        break
        except Exception:
            pass

        dlg = VpsAchievementInfoDialog(self.cfg, rom, title, rule, unlock_entry, parent=self)
        dlg.navigate_to_available_maps.connect(lambda: setattr(dlg, "_navigate_requested", True))
        dlg.exec()
        if getattr(dlg, "_navigate_requested", False):
            for i in range(self.main_tabs.count()):
                if "Available Maps" in self.main_tabs.tabText(i):
                    self.main_tabs.setCurrentIndex(i)
                    break

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

    # ==========================================
    # TAB: SYSTEM
    # ==========================================
    def _build_tab_system(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        system_subtabs = QTabWidget()
        self.system_subtabs = system_subtabs
        tab_layout.addWidget(system_subtabs)

        # ── General sub-tab ────────────────────────────────────────────────────
        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)

        # --- 👤 Player Profile ---
        grp_profile = QGroupBox("👤 Player Profile")
        lay_profile = QGridLayout(grp_profile)

        self.txt_player_name = QLineEdit()
        self.txt_player_name.setText(self.cfg.OVERLAY.get("player_name", "Player"))
        self.txt_player_name.textChanged.connect(self._save_player_name)

        self.txt_player_id = QLineEdit()
        self.txt_player_id.setText(self.cfg.OVERLAY.get("player_id", "0000"))
        self.txt_player_id.setMaxLength(4)
        self.txt_player_id.setFixedWidth(60)
        self.txt_player_id.textChanged.connect(self._save_player_id)

        lay_profile.addWidget(QLabel("Display Name:"), 0, 0)
        lay_profile.addWidget(self.txt_player_name, 0, 1)
        lay_profile.addWidget(QLabel("Player ID (Restore):"), 0, 2)
        lay_profile.addWidget(self.txt_player_id, 0, 3)

        lbl_id_warning = QLabel(
            "⚠️ <b>IMPORTANT: Keep your Player ID safe!</b><br>"
            "Do not share your 4-character Player ID with anyone. "
            "Please write it down or save it somewhere safe!"
        )
        lbl_id_warning.setWordWrap(True)
        lbl_id_warning.setStyleSheet("color: #FF7F00; margin-top: 8px; font-size: 10pt; background: #111; padding: 10px; border: 1px solid #FF7F00; border-radius: 5px;")
        lay_profile.addWidget(lbl_id_warning, 1, 0, 1, 4)

        layout.addWidget(grp_profile)

        # --- ☁️ Cloud Sync & Backup ---
        grp_cloud = QGroupBox("☁️ Cloud Sync & Backup")
        lay_cloud = QVBoxLayout(grp_cloud)

        self.chk_cloud_enabled = QCheckBox("Enable Cloud Sync")
        self.chk_cloud_enabled.setChecked(self.cfg.CLOUD_ENABLED)
        self.chk_cloud_enabled.stateChanged.connect(self._save_cloud_settings)
        lay_cloud.addWidget(self.chk_cloud_enabled)

        self.chk_cloud_backup = QCheckBox("💾 Auto-Backup Progress to Cloud")
        self.chk_cloud_backup.setToolTip(
            "When enabled, your achievement progress, challenge scores, and VPS mapping "
            "are automatically uploaded to the cloud for backup purposes. "
            "Use 'Restore from Cloud' to recover your data on a new PC."
        )
        self.chk_cloud_backup.setChecked(self.cfg.CLOUD_BACKUP_ENABLED)
        self.chk_cloud_backup.setVisible(self.cfg.CLOUD_ENABLED)
        self.chk_cloud_backup.stateChanged.connect(self._save_cloud_backup_settings)
        lay_cloud.addWidget(self.chk_cloud_backup)

        lay_cloud_btns = QHBoxLayout()

        self.btn_backup_cloud = QPushButton("☁️ Backup to Cloud")
        self.btn_backup_cloud.setToolTip(
            "Manually upload your full achievement data, VPS mapping, and ROM progress to the cloud. "
            "Use this to create an immediate backup of your current data."
        )
        self.btn_backup_cloud.setVisible(self.cfg.CLOUD_ENABLED)
        self.btn_backup_cloud.clicked.connect(self._manual_cloud_backup)
        lay_cloud_btns.addWidget(self.btn_backup_cloud)

        self.btn_restore_cloud = QPushButton("☁️ Restore from Cloud")
        self.btn_restore_cloud.setToolTip(
            "Downloads your full achievement progress from the cloud using your Player ID. "
            "Use this to restore your achievements on a new PC. "
            "Warning: This will overwrite your local achievement data."
        )
        self.btn_restore_cloud.setVisible(self.cfg.CLOUD_ENABLED)
        self.btn_restore_cloud.clicked.connect(self._restore_achievements_from_cloud)
        lay_cloud_btns.addWidget(self.btn_restore_cloud)

        lay_cloud.addLayout(lay_cloud_btns)
        layout.addWidget(grp_cloud)

        # --- ⚡ Performance & Animations ---
        grp_perf_anim = QGroupBox("⚡ Performance & Animations")
        lay_perf_anim = QVBoxLayout(grp_perf_anim)

        self.chk_low_perf_mode = QCheckBox("🔋 Low Performance Mode (disables all overlay animations)")
        self.chk_low_perf_mode.setChecked(bool(self.cfg.OVERLAY.get("low_performance_mode", False)))
        self.chk_low_perf_mode.stateChanged.connect(self._save_low_performance_mode)
        lay_perf_anim.addWidget(self.chk_low_perf_mode)

        lbl_anim_note = QLabel("Enable or disable individual animation groups. Low Performance Mode overrides all.")
        lbl_anim_note.setWordWrap(True)
        lbl_anim_note.setStyleSheet("color:#AAA; font-size:9pt; margin-top:6px; margin-bottom:4px;")
        lay_perf_anim.addWidget(lbl_anim_note)

        lbl_main_anim = QLabel("Main / Large Overlay:")
        lbl_main_anim.setStyleSheet("font-weight:bold; margin-top:4px;")
        lay_perf_anim.addWidget(lbl_main_anim)

        self.chk_anim_main_transitions = QCheckBox("  ↔  Page / content transitions (Main Overlay)")
        self.chk_anim_main_transitions.setChecked(bool(self.cfg.OVERLAY.get("anim_main_transitions", True)))
        self.chk_anim_main_transitions.stateChanged.connect(self._save_anim_settings)
        lay_perf_anim.addWidget(self.chk_anim_main_transitions)

        self.chk_anim_main_glow = QCheckBox("  ✨  Glow border & floating particles (Main Overlay)")
        self.chk_anim_main_glow.setChecked(bool(self.cfg.OVERLAY.get("anim_main_glow", True)))
        self.chk_anim_main_glow.stateChanged.connect(self._save_anim_settings)
        lay_perf_anim.addWidget(self.chk_anim_main_glow)

        self.chk_anim_main_score_progress = QCheckBox("  📊  Score counter & progress bar (Main Overlay)")
        self.chk_anim_main_score_progress.setChecked(bool(self.cfg.OVERLAY.get("anim_main_score_progress", True)))
        self.chk_anim_main_score_progress.stateChanged.connect(self._save_anim_settings)
        lay_perf_anim.addWidget(self.chk_anim_main_score_progress)

        self.chk_anim_main_highlights = QCheckBox("  💡  Value update highlights & shine sweep (Main Overlay)")
        self.chk_anim_main_highlights.setChecked(bool(self.cfg.OVERLAY.get("anim_main_highlights", True)))
        self.chk_anim_main_highlights.stateChanged.connect(self._save_anim_settings)
        lay_perf_anim.addWidget(self.chk_anim_main_highlights)

        lbl_other_anim = QLabel("Other Overlays:")
        lbl_other_anim.setStyleSheet("font-weight:bold; margin-top:6px;")
        lay_perf_anim.addWidget(lbl_other_anim)

        self.chk_anim_toast = QCheckBox("  🏆  Achievement toast (Toast Overlay)")
        self.chk_anim_toast.setChecked(bool(self.cfg.OVERLAY.get("anim_toast", True)))
        self.chk_anim_toast.stateChanged.connect(self._save_anim_settings)
        lay_perf_anim.addWidget(self.chk_anim_toast)

        self.chk_anim_status = QCheckBox("  🔵  Status overlay (Status Badge)")
        self.chk_anim_status.setChecked(bool(self.cfg.OVERLAY.get("anim_status", True)))
        self.chk_anim_status.stateChanged.connect(self._save_anim_settings)
        lay_perf_anim.addWidget(self.chk_anim_status)

        self.chk_anim_challenge = QCheckBox("  ⚡  Challenge overlays (Challenge Select / Timer / Flip Counter)")
        self.chk_anim_challenge.setChecked(bool(self.cfg.OVERLAY.get("anim_challenge", True)))
        self.chk_anim_challenge.stateChanged.connect(self._save_anim_settings)
        lay_perf_anim.addWidget(self.chk_anim_challenge)

        # Disable individual animation checkboxes if Low Performance Mode is already on
        if bool(self.cfg.OVERLAY.get("low_performance_mode", False)):
            for _chk in [
                self.chk_anim_main_transitions, self.chk_anim_main_glow,
                self.chk_anim_main_score_progress, self.chk_anim_main_highlights,
                self.chk_anim_toast, self.chk_anim_status, self.chk_anim_challenge,
            ]:
                _chk.setEnabled(False)

        layout.addWidget(grp_perf_anim)

        # --- 🐛 Feedback & Bug Reports ---
        grp_feedback = QGroupBox("🐛 Feedback & Bug Reports")
        lay_feedback = QVBoxLayout(grp_feedback)
        lbl_feedback = QLabel(
            "Found a bug or have a suggestion? Report it directly here!"
        )
        lbl_feedback.setWordWrap(True)
        lbl_feedback.setStyleSheet("color: #00E5FF; font-size: 9pt;")
        lay_feedback.addWidget(lbl_feedback)
        btn_feedback = QPushButton("🐛 Report Bug / Suggestion")
        btn_feedback.setStyleSheet(
            "QPushButton { background: #FF7F00; color: #fff; font-weight: bold;"
            "  border: none; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #e06d00; }"
        )
        btn_feedback.clicked.connect(lambda: FeedbackDialog(self).exec())
        lay_feedback.addWidget(btn_feedback)
        layout.addWidget(grp_feedback)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "system_general")
        system_subtabs.addTab(general_tab, "⚙️ General")

        # ── Maintenance sub-tab ────────────────────────────────────────────────
        maint_tab = QWidget()
        maint_layout = QVBoxLayout(maint_tab)

        # --- 📁 Directory Setup ---
        grp_paths = QGroupBox("📁 Directory Setup")
        lay_paths = QGridLayout(grp_paths)
        self.base_label = QLabel(f"BASE: {self.cfg.BASE}")
        self.btn_base = QPushButton("Browse..."); self.btn_base.clicked.connect(self.change_base)
        self.nvram_label = QLabel(f"NVRAM: {self.cfg.NVRAM_DIR}")
        self.btn_nvram = QPushButton("Browse..."); self.btn_nvram.clicked.connect(self.change_nvram)
        self.tables_label = QLabel(f"TABLES: {self.cfg.TABLES_DIR}")
        self.btn_tables = QPushButton("Browse..."); self.btn_tables.clicked.connect(self.change_tables)
        lay_paths.addWidget(self.btn_base, 0, 0); lay_paths.addWidget(self.base_label, 0, 1)
        lay_paths.addWidget(self.btn_nvram, 1, 0); lay_paths.addWidget(self.nvram_label, 1, 1)
        lay_paths.addWidget(self.btn_tables, 2, 0); lay_paths.addWidget(self.tables_label, 2, 1)
        lay_paths.setColumnStretch(1, 1); maint_layout.addWidget(grp_paths)

        # --- 🔧 Maintenance & Updates ---
        grp_maint = QGroupBox("🔧 Maintenance & Updates")
        lay_maint = QVBoxLayout(grp_maint)
        self.btn_repair = QPushButton("Repair Data Folders")
        self.btn_repair.clicked.connect(self._repair_data_folders)
        self.btn_prefetch = QPushButton("Force Cache NVRAM Maps")
        self.btn_prefetch.clicked.connect(self._prefetch_maps_now)
        lay_maint.addWidget(self.btn_repair)
        lay_maint.addWidget(self.btn_prefetch)

        self.btn_update_dbs = QPushButton("🔄 Update Databases (Index, NVRAM Maps, VPS DB, VPXTool)")
        self.btn_update_dbs.setToolTip("Force re-download of index.json, romnames.json, vpsdb.json and vpxtool, then reload.")
        self.btn_update_dbs.clicked.connect(self._update_databases_now)
        lay_maint.addWidget(self.btn_update_dbs)

        self.btn_self_update = QPushButton("⬆️ Watcher Update")
        self.btn_self_update.setToolTip("Checks GitHub for a newer release and downloads + installs it automatically.")
        self.btn_self_update.clicked.connect(self._check_for_app_update)
        lay_maint.addWidget(self.btn_self_update)

        maint_layout.addWidget(grp_maint)

        maint_layout.addStretch(1)
        self._add_tab_help_button(maint_layout, "system_maintenance")
        system_subtabs.addTab(maint_tab, "🔧 Maintenance")

        self.main_tabs.addTab(tab, "⚙️ System")

    # ==========================================
    # CLEAN SAVE METHODS
    # ==========================================
    def _save_cloud_settings(self):
        QTimer.singleShot(0, self._apply_cloud_settings)

    def _apply_cloud_settings(self):
        if self.chk_cloud_enabled.isChecked():
            pname = self.txt_player_name.text().strip().lower()
            if not pname or pname == "player":
                self._msgbox_topmost("warn", "Cloud Sync", "Please enter a valid player name in the profile first!")
                self.chk_cloud_enabled.blockSignals(True)
                self.chk_cloud_enabled.setChecked(False)
                self.chk_cloud_enabled.blockSignals(False)
                self.cfg.CLOUD_ENABLED = False
                if getattr(self, "btn_backup_cloud", None):
                    self.btn_backup_cloud.setVisible(False)
                if getattr(self, "btn_restore_cloud", None):
                    self.btn_restore_cloud.setVisible(False)
                if getattr(self, "chk_cloud_backup", None):
                    self.chk_cloud_backup.setVisible(False)
                    self.chk_cloud_backup.setChecked(False)
                    self.cfg.CLOUD_BACKUP_ENABLED = False
                self.cfg.save()
                return
        self.cfg.CLOUD_ENABLED = self.chk_cloud_enabled.isChecked()
        self.cfg.save()
        # Start/stop the highscore polling timer based on cloud state
        if hasattr(self, "_highscore_poll_timer"):
            if self.cfg.CLOUD_ENABLED:
                if not self._highscore_poll_timer.isActive():
                    self._highscore_poll_timer.start()
            else:
                self._highscore_poll_timer.stop()
        if getattr(self, "btn_backup_cloud", None):
            self.btn_backup_cloud.setVisible(self.cfg.CLOUD_ENABLED)
        if getattr(self, "btn_restore_cloud", None):
            self.btn_restore_cloud.setVisible(self.cfg.CLOUD_ENABLED)
        if getattr(self, "chk_cloud_backup", None):
            self.chk_cloud_backup.setVisible(self.cfg.CLOUD_ENABLED)
            if not self.cfg.CLOUD_ENABLED:
                self.chk_cloud_backup.setChecked(False)
                self.cfg.CLOUD_BACKUP_ENABLED = False
                self.cfg.save()

    def _save_cloud_backup_settings(self):
        self.cfg.CLOUD_BACKUP_ENABLED = self.chk_cloud_backup.isChecked()
        self.cfg.save()

    def _save_low_performance_mode(self, state: int):
        self.cfg.OVERLAY["low_performance_mode"] = bool(state)
        self.cfg.save()
        _anim_chks = [
            "chk_anim_main_transitions", "chk_anim_main_glow",
            "chk_anim_main_score_progress", "chk_anim_main_highlights",
            "chk_anim_toast", "chk_anim_status", "chk_anim_challenge",
        ]
        enabled = not bool(state)
        for name in _anim_chks:
            chk = getattr(self, name, None)
            if chk is not None:
                chk.setEnabled(enabled)

    def _save_anim_settings(self):
        self.cfg.OVERLAY["anim_main_transitions"] = bool(getattr(self, "chk_anim_main_transitions", None) and self.chk_anim_main_transitions.isChecked())
        self.cfg.OVERLAY["anim_main_glow"] = bool(getattr(self, "chk_anim_main_glow", None) and self.chk_anim_main_glow.isChecked())
        self.cfg.OVERLAY["anim_main_score_progress"] = bool(getattr(self, "chk_anim_main_score_progress", None) and self.chk_anim_main_score_progress.isChecked())
        self.cfg.OVERLAY["anim_main_highlights"] = bool(getattr(self, "chk_anim_main_highlights", None) and self.chk_anim_main_highlights.isChecked())
        self.cfg.OVERLAY["anim_toast"] = bool(getattr(self, "chk_anim_toast", None) and self.chk_anim_toast.isChecked())
        self.cfg.OVERLAY["anim_status"] = bool(getattr(self, "chk_anim_status", None) and self.chk_anim_status.isChecked())
        self.cfg.OVERLAY["anim_challenge"] = bool(getattr(self, "chk_anim_challenge", None) and self.chk_anim_challenge.isChecked())
        self.cfg.save()

    def _save_overlay_page_settings(self):
        self.cfg.OVERLAY["overlay_page2_enabled"] = self.chk_overlay_page2.isChecked()
        self.cfg.OVERLAY["overlay_page3_enabled"] = self.chk_overlay_page3.isChecked()
        self.cfg.OVERLAY["overlay_page4_enabled"] = self.chk_overlay_page4.isChecked()
        self.cfg.OVERLAY["overlay_page5_enabled"] = self.chk_overlay_page5.isChecked()
        self.cfg.save()

    def _save_player_name(self, name):
        self.cfg.OVERLAY["player_name"] = name.strip()
        self.cfg.save()
        if not name.strip() or name.strip().lower() == "player":
            if getattr(self, "chk_cloud_enabled", None) and self.chk_cloud_enabled.isChecked():
                self.chk_cloud_enabled.blockSignals(True)
                self.chk_cloud_enabled.setChecked(False)
                self.chk_cloud_enabled.blockSignals(False)
                self.cfg.CLOUD_ENABLED = False
                self.cfg.save()

    def _save_player_id(self, player_id):
        self.cfg.OVERLAY["player_id"] = player_id.strip()
        self.cfg.save()

    def _restore_achievements_from_cloud(self):
        if not self.cfg.CLOUD_ENABLED or not self.cfg.CLOUD_URL:
            self._msgbox_topmost("warn", "Restore from Cloud", "Cloud sync is not enabled.")
            return

        pid = str(self.cfg.OVERLAY.get("player_id", "")).strip()
        if not pid or pid == "unknown":
            self._msgbox_topmost("warn", "Restore from Cloud", "Please set a valid Player ID first.")
            return

        confirm = QMessageBox.question(
            self,
            "Restore from Cloud",
            "This will overwrite your local achievement data with the cloud version. Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            data = CloudSync.fetch_node(self.cfg, f"players/{pid}/achievements")
        except Exception as e:
            self._msgbox_topmost("warn", "Restore from Cloud", f"Failed to fetch data from cloud:\n{e}")
            return

        if not data or not isinstance(data, dict):
            self._msgbox_topmost("warn", "Restore from Cloud", "No achievement data found in the cloud for your Player ID.")
            return

        try:
            # Reconstruct the local state structure from the cloud payload
            state = {
                "global": {"__global__": data.get("global", [])},
                "session": data.get("session", {}),
                "roms_played": data.get("roms_played", []),
                "badges": data.get("badges", []),
                "selected_badge": data.get("selected_badge", ""),
            }
            self.watcher._ach_state_save(state)
        except Exception as e:
            self._msgbox_topmost("warn", "Restore from Cloud", f"Failed to save restored data locally:\n{e}")
            return

        # Restore Challenge Scores from Cloud
        scores_restored = False
        try:
            scores_data = CloudSync.fetch_node(self.cfg, f"players/{pid}/scores")
            if scores_data and isinstance(scores_data, dict):
                out_dir = os.path.join(self.cfg.BASE, "session_stats", "challenges", "history")
                ensure_dir(out_dir)
                for category, cat_entries in scores_data.items():
                    if not isinstance(cat_entries, dict):
                        continue
                    for rom_key, entry in cat_entries.items():
                        if not entry or not isinstance(entry, dict):
                            continue
                        try:
                            # Extract base ROM by stripping known suffixes added by upload_score
                            base_rom = rom_key
                            if "target_flips" in entry:
                                suffix = f"_f{entry['target_flips']}"
                                if base_rom.endswith(suffix):
                                    base_rom = base_rom[: -len(suffix)]
                            elif "difficulty" in entry:
                                clean_diff = str(entry["difficulty"]).replace(" ", "")
                                suffix = f"_{clean_diff}"
                                if base_rom.endswith(suffix):
                                    base_rom = base_rom[: -len(suffix)]

                            result = {
                                "kind": category,
                                "rom": base_rom,
                                "score": int(entry.get("score", 0)),
                                "ts": entry.get("ts", ""),
                            }
                            if "difficulty" in entry:
                                result["difficulty"] = entry["difficulty"]
                            if "target_flips" in entry:
                                result["target_flips"] = entry["target_flips"]
                            if "duration_sec" in entry:
                                result["duration_sec"] = entry["duration_sec"]

                            path = os.path.join(out_dir, f"{sanitize_filename(base_rom)}.json")
                            hist = secure_load_json(path, {"results": []}) or {"results": []}
                            hist.setdefault("results", [])
                            dup_key = f"{base_rom}|{category}|{result['ts']}"
                            existing_keys = {
                                f"{r.get('rom')}|{r.get('kind')}|{r.get('ts')}"
                                for r in hist["results"]
                            }
                            if dup_key not in existing_keys:
                                hist["results"].append(result)
                                secure_save_json(path, hist)
                                scores_restored = True
                        except Exception as _entry_err:
                            log(self.cfg, f"[CLOUD] Restore: failed to process score entry {rom_key}: {_entry_err}", "WARN")
                            continue
        except Exception as _scores_err:
            log(self.cfg, f"[CLOUD] Restore: challenge scores restore failed: {_scores_err}", "WARN")

        # Restore VPS ID Mapping from Cloud
        vps_mapping_restored = False
        try:
            vps_data = CloudSync.fetch_node(self.cfg, f"players/{pid}/vps_mapping")
            if vps_data and isinstance(vps_data, dict):
                from ui_vps import _save_vps_mapping
                _save_vps_mapping(self.cfg, vps_data)
                vps_mapping_restored = True
                log(self.cfg, f"[CLOUD] VPS mapping restored: {len(vps_data)} entries")
                # Refresh in-memory cache vps_id entries so the Available Maps tab updates immediately
                try:
                    for entry in self._all_maps_cache:
                        entry["vps_id"] = vps_data.get(entry["rom"], "")
                    self._filter_available_maps()
                except Exception as _refresh_err:
                    log(self.cfg, f"[CLOUD] VPS mapping cache refresh failed: {_refresh_err}", "WARN")
        except Exception as _vps_err:
            log(self.cfg, f"[CLOUD] VPS mapping restore failed: {_vps_err}", "WARN")

        # Refresh level display and notify listeners
        try:
            self._refresh_level_display()
        except Exception:
            pass
        try:
            self.bridge.achievements_updated.emit()
        except Exception:
            pass

        if scores_restored and vps_mapping_restored:
            msg = "Achievement data, challenge scores and VPS ID mapping successfully restored from the cloud!"
        elif scores_restored:
            msg = "Achievement data and challenge scores successfully restored from the cloud!"
        elif vps_mapping_restored:
            msg = "Achievement data and VPS ID mapping successfully restored from the cloud!"
        else:
            msg = "Achievement data successfully restored from the cloud!"
        self._msgbox_topmost("info", "Restore from Cloud", msg)

    def _manual_cloud_backup(self):
        """Perform a full manual backup of all local data to cloud."""
        if not self.cfg.CLOUD_ENABLED or not self.cfg.CLOUD_URL:
            self._msgbox_topmost("warn", "Backup to Cloud", "Cloud sync is not enabled.")
            return

        pid = str(self.cfg.OVERLAY.get("player_id", "")).strip()
        if not pid or pid == "unknown":
            self._msgbox_topmost("warn", "Backup to Cloud", "Please set a valid Player ID first.")
            return

        player_name = self.cfg.OVERLAY.get("player_name", "").strip()
        if not player_name or player_name.lower() == "player":
            self._msgbox_topmost("warn", "Backup to Cloud", "Please set a valid player name (not 'Player') first.")
            return

        confirm = QMessageBox.question(
            self,
            "Backup to Cloud",
            "This will upload your current data to the cloud. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.btn_backup_cloud.setEnabled(False)
        self.btn_backup_cloud.setText("⏳ Backing up...")

        def _worker():
            from datetime import datetime, timezone
            from watcher_core import compute_player_level, WATCHER_VERSION
            results = []
            errors = []

            state = self.watcher._ach_state_load()

            # 1. Upload full achievements state
            try:
                lv = compute_player_level(state)
                badges = list(state.get("badges") or [])
                selected_badge = state.get("selected_badge", "")
                payload = {
                    "name": player_name,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "watcher_version": WATCHER_VERSION,
                    "global": list(state.get("global", {}).get("__global__", []) or []),
                    "session": dict(state.get("session", {}) or {}),
                    "roms_played": list(state.get("roms_played", []) or []),
                    "player_level": lv["level"],
                    "player_level_name": lv["name"],
                    "player_prestige": lv["prestige"],
                    "player_prestige_display": lv["prestige_display"],
                    "player_fully_maxed": lv["fully_maxed"],
                    "badges": badges,
                    "badge_count": len(badges),
                    "selected_badge": selected_badge,
                }
                if CloudSync.set_node(self.cfg, f"players/{pid}/achievements", payload):
                    results.append("✅ Achievements")
                    log(self.cfg, "[CLOUD] Manual backup: full achievements uploaded")
                else:
                    errors.append("❌ Achievements: upload failed")
            except Exception as e:
                errors.append(f"❌ Achievements: {e}")
                log(self.cfg, f"[CLOUD] Manual backup: achievements upload failed: {e}", "WARN")

            # 2. Upload VPS mapping
            try:
                from ui_vps import _load_vps_mapping
                mapping = _load_vps_mapping(self.cfg)
                if CloudSync.set_node(self.cfg, f"players/{pid}/vps_mapping", mapping):
                    results.append(f"✅ VPS mapping ({len(mapping)} entries)")
                    log(self.cfg, f"[CLOUD] Manual backup: VPS mapping uploaded: {len(mapping)} entries")
                else:
                    errors.append("❌ VPS mapping: upload failed")
            except Exception as e:
                errors.append(f"❌ VPS mapping: {e}")
                log(self.cfg, f"[CLOUD] Manual backup: VPS mapping upload failed: {e}", "WARN")

            # 3. Upload progress for each ROM that has session data
            def _entry_title(e):
                return str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()

            progress_uploaded = 0
            progress_errors = 0
            try:
                session = state.get("session", {}) or {}
                for rom, entries in session.items():
                    if not entries:
                        continue
                    try:
                        rules = self.watcher._collect_player_rules_for_rom(rom)
                        total = len(rules)
                        if total == 0:
                            continue
                        unlocked_titles = {_entry_title(e) for e in entries}
                        unlocked = sum(
                            1 for r in rules
                            if str(r.get("title", "")).strip() in unlocked_titles
                        )
                        percentage = round((unlocked / total) * 100, 1)
                        progress_payload = {
                            "name": player_name,
                            "unlocked": unlocked,
                            "total": total,
                            "percentage": percentage,
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "watcher_version": WATCHER_VERSION,
                        }
                        if CloudSync.set_node(self.cfg, f"players/{pid}/progress/{rom}", progress_payload):
                            progress_uploaded += 1
                        else:
                            progress_errors += 1
                    except Exception as _rom_err:
                        progress_errors += 1
                        log(self.cfg, f"[CLOUD] Manual backup: progress upload failed for {rom}: {_rom_err}", "WARN")
                if progress_uploaded > 0:
                    results.append(f"✅ Progress for {progress_uploaded} ROM(s)")
                if progress_errors > 0:
                    errors.append(f"❌ Progress: {progress_errors} ROM(s) failed")
            except Exception as e:
                errors.append(f"❌ Progress: {e}")
                log(self.cfg, f"[CLOUD] Manual backup: progress iteration failed: {e}", "WARN")

            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            summary = "\n".join(results + errors)
            QMetaObject.invokeMethod(self, "_on_manual_cloud_backup_done",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, summary),
                Q_ARG(bool, len(errors) == 0))

        import threading
        threading.Thread(target=_worker, daemon=True, name="ManualCloudBackup").start()

    @pyqtSlot(str, bool)
    def _on_manual_cloud_backup_done(self, summary: str, success: bool):
        self.btn_backup_cloud.setEnabled(True)
        self.btn_backup_cloud.setText("☁️ Backup to Cloud")
        if success:
            self._msgbox_topmost("info", "Backup to Cloud", f"Backup completed successfully!\n\n{summary}")
        else:
            self._msgbox_topmost("warn", "Backup to Cloud", f"Backup completed with some issues:\n\n{summary}")

    def _cloud_upload_vps_mapping(self):
        """Upload vps_id_mapping.json to cloud under players/{pid}/vps_mapping."""
        if not self.cfg.CLOUD_ENABLED or not self.cfg.CLOUD_URL:
            return
        if not self.cfg.CLOUD_BACKUP_ENABLED:
            return
        pid = str(self.cfg.OVERLAY.get("player_id", "")).strip()
        if not pid or pid == "unknown":
            return
        try:
            from ui_vps import _load_vps_mapping
            mapping = _load_vps_mapping(self.cfg)
            CloudSync.set_node(self.cfg, f"players/{pid}/vps_mapping", mapping)
            log(self.cfg, f"[CLOUD] VPS mapping uploaded: {len(mapping)} entries")
        except Exception as e:
            log(self.cfg, f"[CLOUD] VPS mapping upload failed: {e}", "WARN")

    def _update_databases_now(self):
        import threading
        self.btn_update_dbs.setEnabled(False)
        self.btn_update_dbs.setText("⏳ Updating...")

        def _worker():
            try:
                from watcher_core import (
                    f_index, f_romnames, f_vpsdb_cache,
                    INDEX_URL, ROMNAMES_URL, _fetch_bytes_url, ensure_dir, load_json, log,
                    VPXTOOL_PATH, ensure_vpxtool
                )
                from ui_vps import VPSDB_URL
                import os

                cfg = self.cfg

                def _force_download(path, url):
                    try:
                        data = _fetch_bytes_url(url, timeout=30)
                        ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f:
                            f.write(data)
                        log(cfg, f"[UPDATE] Re-downloaded {url} -> {path}")
                        return True
                    except Exception as e:
                        log(cfg, f"[UPDATE] Failed to download {url}: {e}", "WARN")
                        return False

                _force_download(f_index(cfg), INDEX_URL)
                _force_download(f_romnames(cfg), ROMNAMES_URL)
                _force_download(f_vpsdb_cache(cfg), VPSDB_URL)

                try:
                    if os.path.isfile(VPXTOOL_PATH):
                        os.remove(VPXTOOL_PATH)
                    ensure_vpxtool(cfg)
                except Exception as e:
                    log(cfg, f"[UPDATE] vpxtool re-download failed: {e}", "WARN")

                self.watcher.INDEX = load_json(f_index(cfg), {}) or {}
                self.watcher.ROMNAMES = load_json(f_romnames(cfg), {}) or {}

            except Exception as e:
                log(self.cfg, f"[UPDATE] _update_databases_now worker failed: {e}", "WARN")
            finally:
                from PyQt6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(self, "_on_update_databases_done", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=_worker, daemon=True, name="UpdateDatabases").start()

    @pyqtSlot()
    def _on_update_databases_done(self):
        self.btn_update_dbs.setEnabled(True)
        self.btn_update_dbs.setText("🔄 Update Databases (Index, NVRAM Maps, VPS DB, VPXTool)")
        self._msgbox_topmost("info", "Update Databases", "Databases updated successfully!\n\nindex.json, romnames.json, vpsdb.json and vpxtool have been refreshed.")

    def _check_for_app_update(self):
        import threading
        self.btn_self_update.setEnabled(False)
        self.btn_self_update.setText("⏳ Checking...")

        def _worker():
            try:
                from watcher_core import _fetch_json_url, log

                RELEASES_API = "https://api.github.com/repos/Mizzlsolti/vpx-achievement-watcher/releases/latest"

                release = _fetch_json_url(RELEASES_API, timeout=15)
                tag = str(release.get("tag_name", "")).strip().lstrip("v")
                body = str(release.get("body", ""))

                if _parse_version(tag) <= _parse_version(self.CURRENT_VERSION):
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(self, "_on_update_check_result",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, "up_to_date"),
                        Q_ARG(str, tag),
                        Q_ARG(str, ""),
                        Q_ARG(str, ""))
                    return

                assets = release.get("assets") or []
                exe_asset = None
                # Prefer the Setup installer (e.g. VPX-Achievement-Watcher-Setup.exe)
                for a in assets:
                    name = str(a.get("name", "")).lower()
                    if "setup" in name and name.endswith(".exe"):
                        exe_asset = a
                        break
                # Fall back to any .exe asset if no Setup asset found
                if not exe_asset:
                    for a in assets:
                        name = str(a.get("name", "")).lower()
                        if name.endswith(".exe"):
                            exe_asset = a
                            break

                if not exe_asset:
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(self, "_on_update_check_result",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, "no_asset"),
                        Q_ARG(str, tag),
                        Q_ARG(str, ""),
                        Q_ARG(str, body))
                    return

                download_url = exe_asset.get("browser_download_url", "")

                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(self, "_on_update_check_result",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, "available"),
                    Q_ARG(str, tag),
                    Q_ARG(str, download_url),
                    Q_ARG(str, body))
            except Exception as e:
                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(self, "_on_update_check_result",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, f"error:{e}"),
                    Q_ARG(str, ""),
                    Q_ARG(str, ""),
                    Q_ARG(str, ""))

        threading.Thread(target=_worker, daemon=True, name="AppUpdateCheck").start()

    @pyqtSlot(str, str, str, str)
    def _on_update_check_result(self, status: str, tag: str, download_url: str, body: str):
        self.btn_self_update.setEnabled(True)
        self.btn_self_update.setText("⬆️ Watcher Update")

        if status == "up_to_date":
            self._msgbox_topmost("info", "Watcher Update", f"You are running the latest version (v{self.CURRENT_VERSION}).")
            return
        if status == "no_asset":
            self._msgbox_topmost("info", "Watcher Update", f"Latest release: v{tag}\nNo .exe asset found in this release.")
            return
        if status.startswith("error:"):
            self._msgbox_topmost("warn", "Watcher Update", f"Could not check for updates:\n{status[6:]}")
            return
        if status == "available":
            # Add update notification to Dashboard feed
            try:
                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self, "_add_update_notification",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, tag),
                )
            except Exception:
                pass
            from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                          QLabel, QTextBrowser, QDialogButtonBox)

            dlg = QDialog(self)
            dlg.setWindowTitle("Watcher Update Available")
            dlg.resize(600, 500)
            lay = QVBoxLayout(dlg)

            lbl_heading = QLabel(f"<b>New version available: v{tag}</b>")
            lbl_heading.setStyleSheet("font-size: 13pt;")
            lay.addWidget(lbl_heading)

            lbl_info = QLabel("Do you want to download and install it now?\nThe app will restart automatically after the update.")
            lbl_info.setWordWrap(True)
            lay.addWidget(lbl_info)

            notes_browser = QTextBrowser()
            notes_browser.setReadOnly(True)
            notes_browser.setOpenExternalLinks(True)
            if body:
                sb = notes_browser.verticalScrollBar()
                old_val = sb.value()
                old_max = max(1, sb.maximum())
                at_bottom = (old_val >= old_max - 2)
                ratio = old_val / old_max if old_max > 0 else 0.0
                notes_browser.setPlainText(body)
                new_max = max(1, sb.maximum())
                if at_bottom:
                    sb.setValue(sb.maximum())
                else:
                    sb.setValue(max(0, min(int(round(ratio * new_max)), new_max)))
            lay.addWidget(notes_browser, 1)

            btn_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
            btn_box.accepted.connect(dlg.accept)
            btn_box.rejected.connect(dlg.reject)
            lay.addWidget(btn_box)

            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            self._do_app_update(download_url)

    def _do_app_update(self, download_url: str):
        import threading
        from PyQt6.QtWidgets import QProgressDialog
        from PyQt6.QtCore import Qt

        self.btn_self_update.setEnabled(False)
        self.btn_self_update.setText("⏳ Downloading update...")

        progress_dlg = QProgressDialog("Downloading update…", None, 0, 0, self)
        progress_dlg.setWindowTitle("Watcher Update")
        progress_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setCancelButton(None)
        progress_dlg.setMinimum(0)
        progress_dlg.setMaximum(0)
        progress_dlg.show()
        self._update_progress_dlg = progress_dlg

        def _download_and_install():
            try:
                import os, tempfile, subprocess
                from watcher_core import _fetch_bytes_url, log

                log(self.cfg, f"[UPDATE] Downloading Setup from {download_url}")
                data = _fetch_bytes_url(download_url, timeout=120)

                tmp_dir = tempfile.mkdtemp(prefix="vpx_ach_update_")
                setup_exe = os.path.join(tmp_dir, "VPX-Achievement-Watcher-Setup.exe")

                with open(setup_exe, "wb") as f:
                    f.write(data)
                log(self.cfg, f"[UPDATE] Downloaded Setup to {setup_exe}")

                # Batch file runs the installer silently then cleans up the temp files.
                # The installer restarts Achievement_Watcher.exe via its silent [Run] entry.
                bat_path = os.path.join(tmp_dir, "vpx_ach_update.bat")
                bat = (
                    "@echo off\r\n"
                    "timeout /t 2 /nobreak >nul\r\n"
                    f'"{setup_exe}" /SILENT /NORESTART /SP-\r\n'
                    f'del /f /q "{setup_exe}"\r\n'
                    'del /f /q "%~f0"\r\n'
                )
                with open(bat_path, "w") as f:
                    f.write(bat)

                log(self.cfg, "[UPDATE] Launching silent installer and quitting")
                subprocess.Popen(
                    ["cmd.exe", "/c", bat_path],
                    creationflags=0x08000000 | 0x00000008,
                    close_fds=True,
                )

                from PyQt6.QtCore import QMetaObject, Qt as _Qt
                QMetaObject.invokeMethod(self, "_on_update_ready_quit", _Qt.ConnectionType.QueuedConnection)

            except Exception as e:
                from watcher_core import log
                log(self.cfg, f"[UPDATE] Download/install failed: {e}", "ERROR")
                from PyQt6.QtCore import QMetaObject, Qt as _Qt, Q_ARG
                QMetaObject.invokeMethod(self, "_on_update_download_failed",
                    _Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, str(e)))

        threading.Thread(target=_download_and_install, daemon=True, name="AppUpdateDownload").start()

    @pyqtSlot()
    def _on_update_ready_quit(self):
        if hasattr(self, "_update_progress_dlg"):
            self._update_progress_dlg.close()
        self.quit_all()

    @pyqtSlot(str)
    def _on_update_download_failed(self, error: str):
        if hasattr(self, "_update_progress_dlg"):
            self._update_progress_dlg.close()
        self.btn_self_update.setEnabled(True)
        self.btn_self_update.setText("⬆️ Watcher Update")
        self._msgbox_topmost("warn", "App Update Failed", f"Download or install failed:\n{error}")

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

        css = (
            "<style>"
            "table{width:100%;border-collapse:collapse;}"
            "td{font-size:0.9em;padding:4px 6px;border-bottom:1px solid #333;}"
            ".unlocked{color:#00E5FF;font-weight:bold;}"
            ".locked{color:#555;}"
            ".hdr{color:#FF7F00;font-size:1.15em;font-weight:bold;text-align:center;padding:6px 0;}"
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
            + (f"<div style='color:#FF7F00;font-size:0.9em;text-align:center;margin-bottom:2px;'>{esc(level_badge)}</div>" if level_badge else "")
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

        cloud_sync_msg = ""
        if not self.cfg.CLOUD_ENABLED:
            cloud_sync_msg = (
                "<div style='color:#FF7F00;font-weight:bold;font-size:1.05em;"
                "text-align:center;padding:8px 12px;border:1px solid #FF7F00;"
                "border-radius:6px;margin-bottom:10px;'>"
                "If you want to participate, enable cloud sync."
                "</div>"
            )

        header_html = (
            f"<div style='color:#FF7F00;font-size:1.15em;font-weight:bold;"
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

        # Zeige Ladebildschirm an
        loading_html = (
            f"<div style='color:#00E5FF;font-size:1.15em;font-weight:bold;text-align:center;padding:6px 0;'>"
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

    def _refresh_level_display(self):
        state = None
        try:
            state = self.watcher._ach_state_load()
            lv = compute_player_level(state)

            # Prestige stars label
            self.lbl_prestige_stars.setText(lv["prestige_display"])
            if lv["fully_maxed"]:
                self.lbl_prestige_stars.setStyleSheet(
                    "font-size: 22pt; font-weight: bold; color: #FFD700; "
                    "padding: 4px 10px; letter-spacing: 8px; "
                    "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, "
                    "stop:0 #FF7F00, stop:0.5 #FFD700, stop:1 #FF7F00); "
                    "border-radius: 6px;"
                )
            else:
                self.lbl_prestige_stars.setStyleSheet(
                    "font-size: 22pt; font-weight: bold; color: #FFD700; "
                    "padding: 4px 10px; letter-spacing: 8px;"
                )

            self.lbl_prestige_stars.setToolTip(
                f"Prestige {lv['prestige']} · {PRESTIGE_THRESHOLD} achievements per star"
            )

            prestige_txt = f"  •  Prestige {lv['prestige']}" if lv["prestige"] > 0 else ""
            self.lbl_level_icon_name.setText(
                f"{lv['icon']}  <b>{lv['label']}</b>   Level {lv['level']}{prestige_txt}"
            )
            if lv["max_level"]:
                self.lbl_level_next.setText("🌟 Max Level reached!")
                self.bar_level.setValue(100)
            else:
                self.lbl_level_next.setText(
                    f"Next: {LEVEL_TABLE[lv['level']][2]}  (Level {lv['level']+1}) — {lv['next_at'] - lv['effective']} more Achievements"
                )
                self.bar_level.setValue(int(lv["progress_pct"]))
            self.lbl_level_count.setText(f"{lv['total']} Achievements total")
            rows_html = ""
            for threshold, lvl, name in LEVEL_TABLE:
                cls = ' class="current"' if lvl == lv["level"] else ""
                marker = " ◄ YOU" if lvl == lv["level"] else ""
                rows_html += f"<tr{cls}><td>{lvl}</td><td>{name}{marker}</td><td>{threshold}</td></tr>"
            self.lv_table_browser.setHtml(
                "<style>table{border-collapse:collapse;width:100%}"
                "th{color:#FF7F00;font-weight:bold;padding:4px 8px;border-bottom:2px solid #555;background:#111;text-align:left}"
                "td{padding:3px 8px;border-bottom:1px solid #2a2a2a;color:#CCC}"
                ".current td{color:#00E5FF;font-weight:bold;background:#152015}"
                "</style>"
                + "<table><tr><th>Lvl</th><th>Name</th><th>Achievements</th></tr>"
                + rows_html + "</table>"
            )
        except Exception:
            pass

        # Refresh badge display
        try:
            self._refresh_badge_display(state)
        except Exception:
            pass

    def _refresh_badge_display(self, state: dict = None):
        """Rebuild the badge grid and update count/dropdown in the Dashboard tab."""
        try:
            from watcher_core import BADGE_DEFINITIONS
            if state is None:
                state = self.watcher._ach_state_load()
            earned_set = set(state.get("badges") or [])
            selected = state.get("selected_badge", "")

            # Clear existing grid
            while self._badge_grid_layout.count():
                item = self._badge_grid_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

            COLS = 8
            for idx, (bid, icon, name, desc) in enumerate(BADGE_DEFINITIONS):
                row, col = divmod(idx, COLS)
                is_earned = bid in earned_set
                lbl = QLabel(icon)
                lbl.setFixedSize(36, 36)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setToolTip(f"{'✅ ' if is_earned else '🔒 '}{name}: {desc}")
                if is_earned:
                    lbl.setStyleSheet(
                        "font-size: 18pt; background: #1a1a1a; border: 1px solid #FF7F00; "
                        "border-radius: 6px;"
                    )
                else:
                    lbl.setStyleSheet(
                        "font-size: 18pt; background: #111; border: 1px solid #333; "
                        "border-radius: 6px; color: rgba(200,200,200,40);"
                    )
                self._badge_grid_layout.addWidget(lbl, row, col)

            # Update count label
            total_badges = len(BADGE_DEFINITIONS)
            self.lbl_badge_count.setText(f"{len(earned_set)} / {total_badges} Badges")

            # Rebuild dropdown
            self.cmb_badge_select.blockSignals(True)
            self.cmb_badge_select.clear()
            self.cmb_badge_select.addItem("— None —", "")
            for bid, icon, name, _desc in BADGE_DEFINITIONS:
                if bid in earned_set:
                    self.cmb_badge_select.addItem(f"{icon} {name}", bid)
            # Restore selected value
            for i in range(self.cmb_badge_select.count()):
                if self.cmb_badge_select.itemData(i) == selected:
                    self.cmb_badge_select.setCurrentIndex(i)
                    break
            self.cmb_badge_select.blockSignals(False)
        except Exception:
            pass

    def _on_badge_select_changed(self, _index: int):
        """Save the selected badge to state and trigger a cloud re-upload."""
        try:
            badge_id = self.cmb_badge_select.currentData() or ""
            state = self.watcher._ach_state_load()
            state["selected_badge"] = badge_id
            self.watcher._ach_state_save(state)
            # Re-upload full achievements to cloud so the new badge appears on leaderboards
            if self.cfg.CLOUD_ENABLED and self.cfg.CLOUD_BACKUP_ENABLED:
                pname = self.cfg.OVERLAY.get("player_name", "Player").strip()
                if pname:
                    _state_copy = dict(state)
                    threading.Thread(
                        target=lambda: CloudSync.upload_full_achievements(self.cfg, _state_copy, pname),
                        daemon=True,
                    ).start()
                # Also re-upload progress for each ROM so the badge appears on progress leaderboards
                _cfg = self.cfg
                _watcher = self.watcher
                _state_copy2 = dict(state)

                def _reupload_progress():
                    try:
                        session = _state_copy2.get("session", {})
                        pid = str(_cfg.OVERLAY.get("player_id", "unknown")).strip()
                        for rom, entries in session.items():
                            if not rom or not entries:
                                continue
                            try:
                                rules = _watcher._collect_player_rules_for_rom(rom)
                            except Exception:
                                continue
                            if not rules:
                                continue
                            # Deduplicate rules by cleaned title
                            seen_titles = set()
                            unique_rules = []
                            for r in rules:
                                rt = str(r.get("title", "")).strip()
                                clean_rt = rt.replace(" (Session)", "").replace(" (Global)", "")
                                if clean_rt not in seen_titles:
                                    seen_titles.add(clean_rt)
                                    unique_rules.append(r)
                            total_achs = len(unique_rules)
                            if total_achs <= 0:
                                continue
                            unlocked_titles = set()
                            for e in (entries or []):
                                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                                if t:
                                    unlocked_titles.add(t)
                            unlocked_count = len(unlocked_titles)
                            # Clear dedup cache for this ROM so the re-upload is not skipped
                            if pid and pid != "unknown":
                                with CloudSync._recent_progress_uploads_lock:
                                    keys_to_remove = [
                                        k for k in CloudSync._recent_progress_uploads
                                        if k.startswith(f"{pid}|{rom}|")
                                    ]
                                    for k in keys_to_remove:
                                        del CloudSync._recent_progress_uploads[k]
                            CloudSync.upload_achievement_progress(_cfg, rom, unlocked_count, total_achs)
                    except Exception:
                        pass

                threading.Thread(target=_reupload_progress, daemon=True).start()
        except Exception:
            pass

    @staticmethod
    def _dot(color: str, label: str, value: str) -> str:
        """Return an HTML string with a colored dot indicator followed by label and value."""
        return (
            f"<span style='color:{color};'>&#9679;</span>"
            f"&nbsp;<span style='color:#CCC;'>{label}&nbsp;&nbsp;{value}</span>"
        )

    def _refresh_dashboard_cards(self):
        """Populate the Last Run and Run Status cards in the Dashboard tab."""
        import json as _json
        try:
            # ── Last Run card ────────────────────────────────────────────
            summary_path = os.path.join(
                self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json"
            )
            lr_table = "No previous run"
            lr_score = "—"
            lr_achievements = "—"
            lr_result = "—"
            try:
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as _f:
                        _data = _json.load(_f)
                    rom = str(_data.get("rom", "") or "")
                    romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
                    table_title = _strip_version_from_name(romnames.get(rom, rom.upper() if rom else ""))
                    lr_table = table_title or rom.upper() or "Unknown table"

                    # Score: try top-level "score" (added by newer exports),
                    # then best_ball.score, then P1 Score from players deltas.
                    raw_score = _data.get("score", _data.get("best_score", None))
                    if raw_score is None:
                        best_ball = _data.get("best_ball") or {}
                        raw_score = best_ball.get("score", None) if isinstance(best_ball, dict) else None
                    if raw_score is None:
                        try:
                            players = _data.get("players") or []
                            if players and isinstance(players[0], dict):
                                p1_deltas = players[0].get("deltas", {}) or {}
                                # Look for score-related field
                                for k, v in p1_deltas.items():
                                    if "score" in k.lower():
                                        raw_score = v
                                        break
                        except Exception:
                            pass
                    if raw_score is not None:
                        try:
                            lr_score = f"{int(raw_score):,}"
                        except Exception:
                            lr_score = str(raw_score)

                    # Achievements: try stored counts first, then live lookup from state
                    ach_count = _data.get("achievements_unlocked", _data.get("unlocked", None))
                    ach_total = _data.get("achievements_total", _data.get("total", None))
                    if ach_count is None and rom:
                        try:
                            state = self.watcher._ach_state_load()
                            unlocked_titles = set()
                            for e in state.get("session", {}).get(rom, []):
                                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                                if t:
                                    unlocked_titles.add(t)
                            ach_count = len(unlocked_titles)
                            try:
                                s_rules = self.watcher._collect_player_rules_for_rom(rom)
                                unique_titles = {str(r.get("title", "")).strip() for r in s_rules if isinstance(r, dict) and r.get("title")}
                                ach_total = len(unique_titles) if unique_titles else None
                            except Exception:
                                ach_total = None
                        except Exception:
                            pass
                    if ach_count is not None and ach_total is not None:
                        lr_achievements = f"{ach_count} / {ach_total}"
                    elif ach_count is not None:
                        lr_achievements = str(ach_count)

                    # Last run date: try end_timestamp → duration_sec → file mtime
                    result = str(_data.get("result", _data.get("outcome", "")) or "").strip()
                    if not result:
                        end_ts = str(_data.get("end_timestamp", "") or "").strip()
                        if end_ts:
                            try:
                                dt = datetime.fromisoformat(end_ts)
                                result = dt.astimezone().strftime("%Y-%m-%d %H:%M")
                            except Exception:
                                result = end_ts[:16]
                        if not result:
                            dur = _data.get("duration_sec")
                            if dur is not None:
                                try:
                                    mins, secs = divmod(int(dur), 60)
                                    result = f"{mins}m {secs}s"
                                except Exception:
                                    pass
                        if not result:
                            # Final fallback: use file modification time
                            try:
                                mtime = os.path.getmtime(summary_path)
                                result = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                            except Exception:
                                pass
                    lr_result = result if result else "—"
            except Exception:
                pass
            self.lbl_lr_table.setText(f"Table:  {lr_table}")
            self.lbl_lr_score.setText(f"Score:  {lr_score}")
            self.lbl_lr_achievements.setText(f"Achievements:  {lr_achievements}")
            self.lbl_lr_result.setText(f"Last run:  {lr_result}")
        except Exception:
            pass

        try:
            # ── Run Status card ──────────────────────────────────────────
            w = getattr(self, "watcher", None)
            game_active = bool(w and getattr(w, "game_active", False))
            current_rom = str(getattr(w, "current_rom", "") or "").strip() if w else ""
            romnames = getattr(w, "ROMNAMES", {}) or {}

            cloud_enabled = bool(getattr(self.cfg, "CLOUD_ENABLED", False))
            cloud_url = str(getattr(self.cfg, "CLOUD_URL", "") or "").strip()

            if game_active and current_rom:
                table_title = _strip_version_from_name(romnames.get(current_rom, current_rom.upper()))
                rs_table = table_title or current_rom.upper()
                try:
                    state = w._ach_state_load()
                    session_ach = state.get("session", {}).get(current_rom, [])
                    rs_session = f"{len(session_ach)} achievement{'s' if len(session_ach) != 1 else ''}"
                except Exception:
                    rs_session = "Active"
                if cloud_enabled and cloud_url:
                    pending_state = getattr(self, "_status_badge_state", None)
                    if pending_state == "pending":
                        rs_cloud = "Pending"
                    elif pending_state == "verified":
                        rs_cloud = "Verified"
                    else:
                        rs_cloud = "Online"
                else:
                    rs_cloud = "Disabled"
                rs_lb = "Ready" if (cloud_enabled and cloud_url) else "Local only"
            else:
                rs_table = "No active game"
                rs_session = "Idle"
                if cloud_enabled and cloud_url:
                    rs_cloud = "Online"
                    rs_lb = "Ready"
                elif cloud_enabled:
                    rs_cloud = "Offline"
                    rs_lb = "Pending"
                else:
                    rs_cloud = "Disabled"
                    rs_lb = "Local only"

            # Table: green when active, red when no game
            tbl_color = "#00C853" if (game_active and current_rom) else "#FF3B30"
            # Session: green when active/counting, yellow when idle
            ses_color = "#FFA500" if rs_session == "Idle" else "#00C853"
            # Cloud: green=online/verified, yellow=pending/offline, red=disabled
            cld_color = (
                "#00C853" if rs_cloud in ("Online", "Verified")
                else "#FF3B30" if rs_cloud == "Disabled"
                else "#FFA500"
            )
            # Leaderboard: green=ready, yellow=pending/local
            lb_color = "#00C853" if rs_lb == "Ready" else "#FFA500"

            self.lbl_rs_table.setText(self._dot(tbl_color, "Table:", rs_table))
            self.lbl_rs_session.setText(self._dot(ses_color, "Session:", rs_session))
            self.lbl_rs_cloud.setText(self._dot(cld_color, "Cloud:", rs_cloud))
            self.lbl_rs_leaderboard.setText(self._dot(lb_color, "Leaderboard:", rs_lb))
        except Exception:
            pass

        # Refresh notification feed + tab badge
        try:
            self._refresh_notification_feed()
        except Exception:
            pass

    # ── Notification feed ────────────────────────────────────────────────────

    def _refresh_notification_feed(self):
        """Rebuild the notification list widget and update the Dashboard tab title."""
        if not hasattr(self, "_notif_list_layout"):
            return

        items = _notif.load_notifications(self.cfg)
        display = items[:_notif._DISPLAY_LIMIT]

        lay = self._notif_list_layout
        # Remove all existing rows (keep the trailing stretch)
        while lay.count() > 1:
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Tab indices (order matches addTab calls in __init__:
        #   0=Dashboard, 1=Player, 2=Appearance, 3=Controls, 4=Records&Stats,
        #   5=Progress, 6=Available Maps, 7=Cloud, 8=System)
        # Only tabs used as notification action_tab destinations are listed here.
        _TAB_MAP = {
            "cloud": 7,
            "system": 8,
            "available_maps": 6,
        }

        if not display:
            lbl_empty = QLabel("No notifications")
            lbl_empty.setStyleSheet("color: #555; font-size: 9pt; padding: 6px;")
            lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.insertWidget(0, lbl_empty)
        else:
            for idx, notif in enumerate(display):
                row_widget = self._make_notif_row(notif, _TAB_MAP)
                lay.insertWidget(idx, row_widget)

        # Update Dashboard tab badge
        try:
            unread = _notif.unread_count(self.cfg)
            tab_idx = self.main_tabs.indexOf(
                self.main_tabs.widget(0)
            )
            if unread > 0:
                self.main_tabs.setTabText(0, f"🏠 Dashboard ({unread})")
            else:
                self.main_tabs.setTabText(0, "🏠 Dashboard")
        except Exception:
            pass

    def _make_notif_row(self, notif: dict, tab_map: dict) -> QWidget:
        """Create a single notification row widget."""
        is_read = bool(notif.get("read", False))
        bg_color = "#0e0e0e" if is_read else "#1a2a1a"
        border_color = "#2a2a2a" if is_read else "#2a4a2a"

        row = QWidget()
        row.setStyleSheet(
            f"QWidget {{ background: {bg_color}; border: 1px solid {border_color}; "
            "border-radius: 3px; }"
        )
        row.setFixedHeight(36)
        row.setCursor(Qt.CursorShape.PointingHandCursor)

        h = QHBoxLayout(row)
        h.setContentsMargins(6, 2, 6, 2)
        h.setSpacing(6)

        icon_text = notif.get("icon", "•")
        lbl_icon = QLabel(icon_text)
        lbl_icon.setFixedWidth(20)
        lbl_icon.setStyleSheet("background: transparent; border: none; font-size: 11pt;")
        h.addWidget(lbl_icon)

        title_text = notif.get("title", "")
        lbl_title = QLabel(title_text)
        lbl_title.setStyleSheet(
            "background: transparent; border: none; font-size: 9pt; "
            + ("font-weight: bold; color: #EEE;" if not is_read else "color: #888;")
        )
        lbl_title.setWordWrap(False)
        h.addWidget(lbl_title, 1)

        # Timestamp (short relative)
        ts_str = ""
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(notif.get("timestamp", ""))
            now = datetime.now(timezone.utc)
            delta = now - ts.astimezone(timezone.utc)
            secs = int(delta.total_seconds())
            if secs < 60:
                ts_str = "just now"
            elif secs < 3600:
                ts_str = f"{secs // 60}m ago"
            elif secs < 86400:
                ts_str = f"{secs // 3600}h ago"
            else:
                ts_str = f"{secs // 86400}d ago"
        except Exception:
            pass
        lbl_ts = QLabel(ts_str)
        lbl_ts.setStyleSheet("background: transparent; border: none; color: #555; font-size: 8pt;")
        lbl_ts.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(lbl_ts)

        notif_id = notif.get("id", "")
        action_tab = notif.get("action_tab")
        notif_type = notif.get("type", "")

        def _on_click(_event, _nid=notif_id, _tab=action_tab, _type=notif_type, _notif_data=notif):
            _notif.mark_read(self.cfg, _nid)
            try:
                self._on_notif_clicked(_tab, _type, _notif_data)
            except Exception:
                pass
            try:
                self._refresh_notification_feed()
            except Exception:
                pass

        row.mousePressEvent = _on_click
        return row

    def _on_notif_clicked(self, action_tab: str, notif_type: str, notif_data: dict):
        """Handle a notification click with enhanced navigation logic."""
        # ── system_maintenance → System tab + Maintenance sub-tab ────────────
        if action_tab == "system_maintenance":
            try:
                self.main_tabs.setCurrentIndex(8)  # System tab
            except Exception:
                pass
            try:
                if hasattr(self, "system_subtabs"):
                    # Find the Maintenance sub-tab (index 1)
                    for i in range(self.system_subtabs.count()):
                        if "Maintenance" in self.system_subtabs.tabText(i):
                            self.system_subtabs.setCurrentIndex(i)
                            break
            except Exception:
                pass
            return

        # ── achievement_beaten → open AchievementBeatenDialog ────────────────
        if notif_type == "achievement_beaten":
            try:
                dlg = AchievementBeatenDialog(self.cfg, notif_data, parent=self)
                dlg.exec()
            except Exception:
                pass
            return

        # ── leaderboard_rank → Cloud tab + auto-fetch ROM ────────────────────
        if notif_type == "leaderboard_rank" and action_tab == "cloud":
            try:
                self.main_tabs.setCurrentIndex(7)  # Cloud tab
            except Exception:
                pass
            try:
                rom = notif_data.get("rom", "")
                if rom and hasattr(self, "txt_cloud_rom"):
                    self.txt_cloud_rom.setText(rom)
                    self._fetch_cloud_leaderboard()
            except Exception:
                pass
            return

        # ── available_maps → switch tab + highlight missing ROMs ─────────────
        if action_tab == "available_maps":
            try:
                self.main_tabs.setCurrentIndex(6)  # Available Maps tab
            except Exception:
                pass
            try:
                missing_roms = notif_data.get("missing_roms", [])
                if missing_roms and hasattr(self, "maps_table") and self.maps_table.rowCount() > 0:
                    self._highlight_maps_table_rows(missing_roms)
            except Exception:
                pass
            return

        # ── generic tab switch ────────────────────────────────────────────────
        _TAB_MAP = {
            "cloud": 7,
            "system": 8,
            "available_maps": 6,
        }
        if action_tab and action_tab in _TAB_MAP:
            try:
                self.main_tabs.setCurrentIndex(_TAB_MAP[action_tab])
            except Exception:
                pass

    def _highlight_maps_table_rows(self, missing_roms: list):
        """Temporarily highlight maps table rows for the given ROM keys (amber tint, ~3 s)."""
        try:
            from PyQt6.QtGui import QColor, QBrush
            highlight_color = QColor("#3a2a00")
            normal_color = QColor("#1a1a1a")

            rows_to_highlight = []
            for row in range(self.maps_table.rowCount()):
                rom_item = self.maps_table.item(row, 1)
                if rom_item and rom_item.text() in missing_roms:
                    rows_to_highlight.append(row)

            # Apply highlight
            for row in rows_to_highlight:
                for col in range(self.maps_table.columnCount()):
                    item = self.maps_table.item(row, col)
                    if item:
                        item.setBackground(QBrush(highlight_color))

            # Reset after 3 seconds
            def _reset():
                try:
                    for r in rows_to_highlight:
                        for col in range(self.maps_table.columnCount()):
                            item = self.maps_table.item(r, col)
                            if item:
                                item.setBackground(QBrush(normal_color))
                except Exception:
                    pass

            QTimer.singleShot(3000, _reset)

            # Scroll to first highlighted row
            if rows_to_highlight:
                self.maps_table.scrollToItem(
                    self.maps_table.item(rows_to_highlight[0], 0)
                )
        except Exception:
            pass

    @pyqtSlot()
    def _on_notif_clear_all(self):
        """Clear all notifications and save dismissed keys so they won't reappear."""
        _notif.dismiss_all(self.cfg)
        self._refresh_notification_feed()

    @pyqtSlot(str)
    def _on_session_ended(self, rom: str):
        """Called when a game session ends; triggers leaderboard rank check."""
        if rom and self.cfg.CLOUD_ENABLED:
            self._check_leaderboard_rank_after_upload(rom)

    # ── Notification generation ───────────────────────────────────────────────

    @pyqtSlot(str)
    def _add_update_notification(self, tag: str):
        """Add an 'update available' notification (called from UI thread)."""
        title = f"New update available: v{tag}"
        _notif.add_notification(
            self.cfg,
            type="update_available",
            icon="🆕",
            title=title,
            detail="Click to open System → Maintenance",
            action_tab="system_maintenance",
            dedup_key=f"update_{tag}",
        )
        try:
            self._refresh_notification_feed()
        except Exception:
            pass

    @pyqtSlot(int)
    def _add_vps_missing_notification(self, count: int, missing_roms: list = None):
        """Add/update a 'vps_missing' notification (called from UI thread)."""
        if count <= 0:
            return
        title = f"{count} ROM{'s' if count != 1 else ''} without VPS ID — cloud upload not possible"
        extra = {}
        if missing_roms:
            extra["missing_roms"] = list(missing_roms)
        _notif.add_notification(
            self.cfg,
            type="vps_missing",
            icon="⚠️",
            title=title,
            detail="Open Available Maps to assign VPS IDs",
            action_tab="available_maps",
            dedup_key=f"vps_missing_{count}",
            extra=extra if extra else None,
        )
        try:
            self._refresh_notification_feed()
        except Exception:
            pass

    @pyqtSlot(str, int)
    def _add_leaderboard_rank_notification(self, rom: str, rank: int):
        """Add a 'leaderboard_rank' notification (called from UI thread)."""
        romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
        display_name = _strip_version_from_name(romnames.get(rom, rom.upper()))
        title = f"You are Top {rank} on {display_name} Leaderboard!"
        _notif.add_notification(
            self.cfg,
            type="leaderboard_rank",
            icon="📊",
            title=title,
            detail=f"ROM: {rom}",
            action_tab="cloud",
            dedup_key=f"lb_rank_{rom}_{rank}",
            extra={"rom": rom},
        )
        try:
            self._refresh_notification_feed()
        except Exception:
            pass

    @pyqtSlot(str, float, str, float)
    def _add_achievement_beaten_notification(self, rom: str, your_score: float = 0.0, new_leader_name: str = "", new_leader_score: float = 0.0):
        """Add an 'achievement_beaten' notification (called from UI thread)."""
        romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
        display_name = _strip_version_from_name(romnames.get(rom, rom.upper()))
        title = f"Your achievement progress on {display_name} has been beaten!"
        _notif.add_notification(
            self.cfg,
            type="achievement_beaten",
            icon="⚔️",
            title=title,
            detail=f"ROM: {rom}",
            action_tab=None,
            dedup_key=f"ach_beaten_{rom}_{new_leader_name}" if new_leader_name else f"ach_beaten_{rom}",
            extra={
                "rom": rom,
                "your_score": your_score,
                "new_leader_name": new_leader_name,
                "new_leader_score": new_leader_score,
            },
        )
        try:
            self._refresh_notification_feed()
        except Exception:
            pass

    def _check_leaderboard_rank_after_upload(self, rom: str):
        """Background: fetch cloud scores for *rom*, find own rank, notify if Top 5."""
        if not self.cfg.CLOUD_ENABLED or not self.cfg.CLOUD_URL:
            return
        pid = str(self.cfg.OVERLAY.get("player_id", "unknown")).strip()
        if not pid or pid == "unknown":
            return

        def _bg():
            try:
                player_ids = CloudSync.fetch_player_ids(self.cfg)
                if not player_ids:
                    return
                paths = [f"players/{p}/progress/{rom}" for p in player_ids]
                batch = CloudSync.fetch_parallel(self.cfg, paths)

                scores = []
                for path, entry in batch.items():
                    if entry and isinstance(entry, dict):
                        pct = float(entry.get("percentage", 0))
                        p_id = path.split("/")[1] if "/" in path else ""
                        scores.append((pct, p_id))
                scores.sort(reverse=True)

                rank = None
                for i, (_, p_id) in enumerate(scores, start=1):
                    if p_id == pid:
                        rank = i
                        break

                if rank is not None and rank <= 5:
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(
                        self, "_add_leaderboard_rank_notification",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, rom),
                        Q_ARG(int, rank),
                    )
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True, name="LeaderboardRankCheck").start()

    def _poll_highscore_beaten(self):
        """Periodic check (every 5 min): detect if own top scores have been beaten."""
        if not self.cfg.CLOUD_ENABLED or not self.cfg.CLOUD_URL:
            return
        pid = str(self.cfg.OVERLAY.get("player_id", "unknown")).strip()
        if not pid or pid == "unknown":
            return

        def _bg():
            try:
                # Load ROMs where this player has uploaded scores
                state = self.watcher._ach_state_load()
                roms_played = list((state.get("session") or {}).keys())
                if not roms_played:
                    return

                player_ids = CloudSync.fetch_player_ids(self.cfg)
                if not player_ids:
                    return

                # Check last-notified timestamps to avoid spam (24 h cooldown per ROM)
                notif_items = _notif.load_notifications(self.cfg)
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                recently_notified: set = set()
                for n in notif_items:
                    if n.get("type") in ("highscore_beaten", "achievement_beaten"):
                        try:
                            ts = datetime.fromisoformat(n.get("timestamp", ""))
                            if (now - ts.astimezone(timezone.utc)) < timedelta(hours=self._NOTIF_COOLDOWN_HOURS):
                                detail = n.get("detail", "")
                                if detail.startswith("ROM: "):
                                    recently_notified.add(detail[5:])
                        except Exception:
                            pass

                for rom in roms_played:
                    if rom in recently_notified:
                        continue
                    paths = [f"players/{p}/progress/{rom}" for p in player_ids]
                    batch = CloudSync.fetch_parallel(self.cfg, paths)

                    scores = []
                    for path, entry in batch.items():
                        if entry and isinstance(entry, dict):
                            pct = float(entry.get("percentage", 0))
                            p_id = path.split("/")[1] if "/" in path else ""
                            scores.append((pct, p_id))
                    scores.sort(reverse=True)

                    if not scores:
                        continue
                    top_pid = scores[0][1]
                    if top_pid and top_pid != pid:
                        # Check own score exists at all
                        own_in = any(p_id == pid for _, p_id in scores)
                        if own_in:
                            leader_score = float(scores[0][0])
                            your_score = next((pct for pct, p_id in scores if p_id == pid), 0.0)
                            leader_entry = batch.get(f"players/{top_pid}/progress/{rom}", {})
                            # player_name/name may be stored alongside the progress entry in Firebase;
                            # fall back to the player ID if no name field is present.
                            leader_name = str(leader_entry.get("player_name", "") or leader_entry.get("name", "") or top_pid)
                            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                            QMetaObject.invokeMethod(
                                self, "_add_achievement_beaten_notification",
                                Qt.ConnectionType.QueuedConnection,
                                Q_ARG(str, rom),
                                Q_ARG(float, float(your_score)),
                                Q_ARG(str, leader_name),
                                Q_ARG(float, leader_score),
                            )
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True, name="HighscorePolling").start()

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
     
    # ==========================================
    # PREFETCH STATUS ANIMATIONS
    # ==========================================
    def _on_prefetch_started(self):
        self._prefetch_msg = "Checking for missing files..."
        if hasattr(self, "_prefetch_blink_timer"):
            self._prefetch_blink_timer.start()
        self._update_prefetch_label()

    def _on_prefetch_progress(self, msg: str):
        self._prefetch_msg = str(msg)
        self._update_prefetch_label()

    def _on_prefetch_blink(self):
        self._prefetch_blink_state = not getattr(self, "_prefetch_blink_state", False)
        self._update_prefetch_label()

    def _update_prefetch_label(self):
        color = "#FF3B30" if getattr(self, "_prefetch_blink_state", False) else "#333333"
        html = (
            f"🔴 Watcher: PREFETCH IN PROGRESS - {self._prefetch_msg} "
            f"<span style='color:{color}; font-weight:bold;'>PLEASE WAIT</span>"
        )
        self.status_label.setText(html)
        self.status_label.setStyleSheet("font-size: 12pt; color: #FF7F00; padding: 10px;")

    def _on_prefetch_finished(self, msg: str):
        try:
            if hasattr(self, "_prefetch_blink_timer"):
                self._prefetch_blink_timer.stop()
        except Exception:
            pass
        self.status_label.setText(f"🟢 {msg}")
        self.status_label.setStyleSheet("font-size: 11pt; color: #00B050; padding: 10px;")
        QTimer.singleShot(10000, self._reset_status_label)
        # Kick off background ROM scan so the cache is warm before the first session ends
        try:
            if self.watcher:
                def _bg_prescan():
                    try:
                        self.watcher._scan_installed_roms_by_manufacturer("__any__")
                    except Exception as e:
                        log(self.cfg, f"[SCAN] Background pre-scan error: {e}", "WARN")
                threading.Thread(target=_bg_prescan, daemon=True).start()
        except Exception:
            pass

    def _reset_status_label(self):
        self.status_label.setText("🟢 Watcher: RUNNING...")
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00E5FF; padding: 10px;")

    def _restart_watcher(self):
        if getattr(self, "_restarting", False):
            return
        self._restarting = True
        self.btn_restart.setEnabled(False)
        self.status_label.setText("🔄 Watcher: RESTARTING...")
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #FFA500; padding: 10px;")

        old_watcher = self.watcher

        def _stop_old():
            try:
                if old_watcher:
                    try:
                        old_watcher.stop_timed_challenge()
                    except Exception:
                        pass
                    try:
                        old_watcher.stop_flip_challenge()
                    except Exception:
                        pass
                    try:
                        old_watcher.stop_heat_challenge()
                    except Exception:
                        pass
                    try:
                        old_watcher.stop()
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                from PyQt6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(self, "_finish_restart", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=_stop_old, daemon=True, name="WatcherRestartThread").start()

    @pyqtSlot()
    def _finish_restart(self):
        try:
            new_watcher = Watcher(self.cfg, self.bridge)
            new_watcher.start()
            self.watcher = new_watcher
            self._reset_status_label()
        except Exception as e:
            log(self.cfg, f"[RESTART] Failed to start new watcher: {e}", "WARN")
            self.status_label.setText("❌ Watcher: RESTART FAILED")
            self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #FF3B30; padding: 10px;")
        finally:
            self._restarting = False
            self.btn_restart.setEnabled(True)

    def _check_for_updates(self):
        """Startup update check: uses GitHub Releases API, adds Dashboard notification only (no popup)."""

        def _task():
            try:
                from watcher_core import _fetch_json_url

                RELEASES_API = "https://api.github.com/repos/Mizzlsolti/vpx-achievement-watcher/releases/latest"
                release = _fetch_json_url(RELEASES_API, timeout=5)

                if not release or not isinstance(release, dict):
                    return
                if release.get("draft"):
                    return

                tag = str(release.get("tag_name", "")).strip().lstrip("v")
                if not tag:
                    return

                if _parse_version(tag) > _parse_version(self.CURRENT_VERSION):
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(
                        self, "_add_update_notification",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, tag),
                    )
            except Exception as e:
                print(f"[UPDATE CHECK] failed: {e}")

        threading.Thread(target=_task, daemon=True).start()

    @pyqtSlot(str)
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
        os.path.join("Achievements", "custom_achievements"),
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
    win.hide()
    code = app.exec()
    cfg.save()
    sys.exit(code)

if __name__ == "__main__":

    main()

