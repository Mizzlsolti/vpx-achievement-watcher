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
    QTextEdit, QTextBrowser, QFileDialog, QMessageBox, QTabWidget,
    QCheckBox, QSlider, QComboBox, QDialog, QGroupBox, QColorDialog, QLineEdit,
    QFontComboBox, QSpinBox, QDoubleSpinBox, QGridLayout, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressDialog, QScrollArea, QCompleter,
    QFrame,
)
from PyQt6.QtCore import (Qt, QEvent, QTimer, QRect,
                          QPoint, pyqtSlot,
                          QThread, QUrl, QStringListModel, QMetaObject, Q_ARG)
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

from core.config import (
    AppConfig, f_achievements_state, f_global_ach,
    f_vps_mapping, f_vpsdb_cache,
    f_custom_achievements_progress, p_aweditor,
)
from core.cloud_sync import CloudSync
from core.watcher_core import (
    APP_DIR, Watcher,
    ensure_dir, log, resource_path,
    run_vpxtool_get_script_authors,
    run_vpxtool_info_show,
    _strip_version_from_name,
    WATCHER_VERSION,
)
from core.badges import (
    compute_player_level, LEVEL_TABLE, PRESTIGE_THRESHOLD, compute_rarity, RARITY_TIERS,
    BADGE_DEFINITIONS,
)

from ui.dialogs import FeedbackDialog, AchievementBeatenDialog
from core.tutorial import TutorialWizardDialog
from core.theme import pinball_arcade_style, generate_stylesheet, list_themes, get_theme, DEFAULT_THEME, get_theme_color
from ui.cloud_stats import CloudStatsMixin
from aweditor import AWEditorMixin
from ui.system import SystemMixin
from ui.appearance import AppearanceMixin
from ui.challenges import ChallengesMixin
from ui.progress import ProgressMixin
from ui.dashboard import DashboardMixin
from ui.overlay_pages import OverlayPagesMixin
from ui.duels import DuelsMixin

from ui.vps import (
    VpsPickerDialog, VpsAchievementInfoDialog, CloudProgressVpsInfoDialog,
    _load_vpsdb, _load_vps_mapping, _save_vps_mapping, _vps_find, _table_has_rom,
    _normalize_term, _find_table_file_by_filename_and_authors,
)
from ui.available_maps import _AvailableMapsWorker

import core.notifications as _notif
import core.sound as sound

from mascot.mascot import GUITrophie, OverlayTrophie, _TROPHIE_SHARED, _TrophieMemory

from ui.overlay import (
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
)

from app.bootstrap import Bridge, main, _authors_match, _parse_version
from app.tray import TrayMixin
from app.overlay_ctrl import OverlayCtrlMixin
from app.hotkeys import HotkeysMixin


class MainWindow(QMainWindow, HotkeysMixin, OverlayCtrlMixin, TrayMixin, CloudStatsMixin, AWEditorMixin, SystemMixin, AppearanceMixin, ChallengesMixin, ProgressMixin,
                 DashboardMixin, OverlayPagesMixin, DuelsMixin):
    CURRENT_VERSION = WATCHER_VERSION
    _HIGHSCORE_POLL_INTERVAL_MS = 300_000   # 5 minutes
    _NOTIF_COOLDOWN_HOURS = 24              # dedup window for highscore_beaten per ROM

    def __init__(self, cfg: AppConfig, watcher: Watcher, bridge: Bridge):
        super().__init__()
        self.cfg = cfg
        self.watcher = watcher
        self.bridge = bridge
        self.setWindowTitle("VPX Achievement Watcher")
        self.resize(1640, 1224)
        
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
        self.bridge.session_ended.connect(self._on_session_ended_duels)
        self.bridge.session_started.connect(self._on_session_started_duels)
        self.bridge.duel_result.connect(self._on_duel_result)
        
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
        self._build_tab_duels()
        self._build_tab_available_maps()   
        self._build_tab_cloud() 
        self._build_tab_system()
        self._build_tab_aweditor()

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

        self._setup_tray(icon)

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
            CloudSync.cleanup_uppercase_rom_progress(self.cfg)

        self._apply_theme()
        self._check_for_updates()
        self._init_tooltips_main()
        self._init_overlay_tooltips()

        self._refresh_input_bindings()

        # ── Trophie mascot ──────────────────────────────────────────────────
        try:
            _trophie_memory = _TrophieMemory(self.cfg.BASE)
            self._trophie_gui = GUITrophie(self.centralWidget(), self.cfg)
            self._trophie_gui.set_memory(_trophie_memory)
            self._trophie_overlay = OverlayTrophie(self, self.cfg)
            self._trophie_overlay.set_memory(_trophie_memory)

            self.main_tabs.currentChanged.connect(self._trophie_gui.on_tab_changed)

            # Connect sub-tab signals so Trophie also reacts to sub-tab changes
            if hasattr(self, 'appearance_subtabs'):
                self.appearance_subtabs.currentChanged.connect(self._on_subtab_changed_appearance)
            if hasattr(self, 'system_subtabs'):
                self.system_subtabs.currentChanged.connect(self._on_subtab_changed_system)
            if hasattr(self, '_aw_inner_tabs'):
                self._aw_inner_tabs.currentChanged.connect(self._on_subtab_changed_aweditor)

            self.bridge.session_ended.connect(self._trophie_overlay.on_session_ended)
            self.bridge.session_started.connect(
                lambda rom, table: self._trophie_overlay.on_rom_start(rom, table or None)
            )
            self.bridge.challenge_timer_start.connect(
                lambda *a: self._trophie_overlay.on_challenge_start()
            )
            self.bridge.challenge_timer_stop.connect(
                lambda *a: self._trophie_overlay.on_challenge_stop()
            )
            self.bridge.challenge_timer_tick.connect(
                lambda ms: self._trophie_overlay.on_challenge_timer_tick(ms)
            )
            self.bridge.challenge_won.connect(
                lambda margin: self._trophie_overlay.on_challenge_won(margin)
            )
            self.bridge.challenge_lost.connect(
                lambda attempts, margin: self._trophie_overlay.on_challenge_lost(attempts, margin)
            )

            # Duel mascot reactions
            self.bridge.duel_received.connect(self._on_duel_received_mascot)
            self.bridge.duel_result.connect(self._on_duel_result_mascot)
            self.bridge.duel_expired.connect(self._on_duel_expired_mascot)

            if self.cfg.OVERLAY.get("trophie_gui_enabled", True):
                self._trophie_gui.show()
                QTimer.singleShot(800, self._trophie_gui.greet)
            else:
                self._trophie_gui.hide()
            if self.cfg.OVERLAY.get("trophie_overlay_enabled", True):
                self._trophie_overlay.show()
                QTimer.singleShot(1200, self._trophie_overlay.greet)
            else:
                self._trophie_overlay.hide()
            # Enable zank/bicker system when both trophies are visible
            _TROPHIE_SHARED["gui_visible"] = (
                bool(self.cfg.OVERLAY.get("trophie_gui_enabled", True)) and
                bool(self.cfg.OVERLAY.get("trophie_overlay_enabled", True))
            )
        except Exception:
            self._trophie_gui = None
            self._trophie_overlay = None

    # ── Duel mascot dispatchers ───────────────────────────────────────────────

    def _msgbox_topmost(self, kind: str, title: str, msg: str):
        """Show a top-most message box. *kind* is 'info' or 'warn'."""
        if kind == "warn":
            box = QMessageBox(QMessageBox.Icon.Warning, title, msg, QMessageBox.StandardButton.Ok, self)
        else:
            box = QMessageBox(QMessageBox.Icon.Information, title, msg, QMessageBox.StandardButton.Ok, self)
        box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        box.exec()

    def _on_duel_received_mascot(self, opponent: str, table_name: str, duel_id: str) -> None:
        """Trigger mascot duel-received reactions."""
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.on_duel_received()
        except Exception:
            pass
        try:
            if getattr(self, "_trophie_overlay", None):
                self._trophie_overlay.on_duel_received()
        except Exception:
            pass

    def _on_duel_result_mascot(self, duel_id: str, result: str, your_score: int, their_score: int) -> None:
        """Trigger mascot reactions based on duel result."""
        try:
            trophie_gui = getattr(self, "_trophie_gui", None)
            trophie_ov  = getattr(self, "_trophie_overlay", None)
            if result == "won":
                if trophie_gui:
                    trophie_gui.on_duel_won()
                if trophie_ov:
                    trophie_ov.on_duel_won()
            elif result == "lost":
                if trophie_gui:
                    trophie_gui.on_duel_lost()
                if trophie_ov:
                    trophie_ov.on_duel_lost()
            elif result == "expired":
                if trophie_gui:
                    trophie_gui.on_duel_expired()
                if trophie_ov:
                    trophie_ov.on_duel_expired()
            elif result == "declined":
                if trophie_gui:
                    trophie_gui.on_duel_declined()
                if trophie_ov:
                    trophie_ov.on_duel_declined()
        except Exception:
            pass

    def _on_duel_expired_mascot(self, duel_id: str) -> None:
        """Trigger mascot duel-expired reactions (bridge.duel_expired signal)."""
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.on_duel_expired()
        except Exception:
            pass
        try:
            if getattr(self, "_trophie_overlay", None):
                self._trophie_overlay.on_duel_expired()
        except Exception:
            pass

    def _in_game_now(self) -> bool:
        try:
            w = getattr(self, "watcher", None)
            return bool(w and (w.game_active or w._vp_player_visible()))
        except Exception:
            return False

    def _player_is_visible(self) -> bool:
        """Strict check: True only when the VPX Player window is visible (not just the editor)."""
        try:
            w = getattr(self, "watcher", None)
            return bool(w and w._vp_player_visible())
        except Exception:
            return False

    def _on_subtab_changed_appearance(self, idx: int) -> None:
        self._notify_trophie_subtab(self.appearance_subtabs.tabText(idx))

    def _on_subtab_changed_system(self, idx: int) -> None:
        self._notify_trophie_subtab(self.system_subtabs.tabText(idx))

    def _on_subtab_changed_aweditor(self, _idx: int) -> None:
        self._notify_trophie_subtab("aweditor")

    def _notify_trophie_subtab(self, tab_name: str) -> None:
        if not getattr(self, '_trophie_gui', None):
            return
        try:
            self._trophie_gui.on_subtab_changed(tab_name)
        except Exception:
            pass


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
           
    def _style(self, widget, css: str):
        try:
            if widget:
                widget.setStyleSheet(css)
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
        "duels": (
            "<b>⚔️ Score Duels</b><br><br>"
            "Challenge other players to asynchronous high-score battles!<br><br>"
            "<b>🎯 My Duels</b><br>"
            "• <b>Start New Duel</b>: Search for a player by Name and select a table to challenge them.<br>"
            "• <b>Incoming Invitations</b>: When someone challenges you, the Score Duels tab switches automatically "
            "(if the GUI is open). If the GUI is minimized, a notification overlay appears — "
            "press <b>Left</b> to accept or <b>Right</b> to decline directly.<br>"
            "• Invitations stay visible until you accept or decline — they do not auto-hide.<br>"
            "• <b>Active Duels</b>: Shows all pending and in-progress duels with status indicators.<br>"
            "• <b>Duel History</b>: Browse your completed duels with results and scores.<br><br>"
            "<b>🌍 Global Feed</b><br>"
            "• Shows the last 50 completed duels from all cloud-connected players.<br>"
            "• Only finished duels (won/lost) are displayed — no cancelled or expired ones.<br>"
            "• Use the Refresh button to update the feed.<br><br>"
            "<b>Rules:</b><br>"
            "• VPX must <b>NOT</b> be running when accepting a duel invitation.<br>"
            "• Both players play the same table independently; highest score wins.<br>"
            "• Tables must have a <b>VPS-ID</b> assigned for duels to work.<br>"
            "• Duels expire if not accepted or completed within the time limit.<br>"
            "• Cloud Sync must be enabled for duels to work."
            "<br><br>"
            "<b>⚠️ Table Requirements:</b><br>"
            "• Table must have an NVRAM map (or be an enabled CAT table).<br>"
            "• Table must be locally installed (.vpx file found).<br>"
            "• Table must have a VPS-ID assigned.<br>"
            "• All three conditions must be met — no exceptions.<br><br>"
            "<b>⚠️ Session Rules:</b><br>"
            "• You must play for at least 60 seconds.<br>"
            "• Your score must improve from the baseline.<br>"
            "• Quitting VPX early or not improving your score will abort the duel.<br>"
            "<br>"
            "<b>🔀 Auto-Match</b><br>"
            "• Press Auto-Match to join the matchmaking queue.<br>"
            "• The system automatically finds an opponent with matching tables (shared VPS-IDs).<br>"
            "• A random shared table is selected and a duel invitation is sent.<br>"
            "• The opponent still needs to accept or decline the invitation.<br>"
            "• Search times out after 5 minutes if no match is found.<br>"
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
        "appearance_effects": (
            "<b>✨ Visual Effects</b><br><br>"
            "Control every animation and visual effect across all overlays.<br><br>"
            "• <b>Low Performance Mode</b>: Master switch — disables all effects at once.<br>"
            "• <b>Checkbox</b>: Enable or disable individual effects.<br>"
            "• <b>Slider</b>: Adjust effect intensity (particle count, glow strength, "
            "shake amplitude, flash brightness, etc.).<br><br>"
            "<b>Preview buttons:</b><br>"
            "• <b>▶ Preview</b> (per group): Opens the overlay in demo mode with all currently "
            "enabled effects running for 6 seconds, then auto-closes.<br><br>"
            "<b>Effects are grouped by overlay:</b><br>"
            "• 🖥️ Main Overlay — glow border, particles, transitions, score spin, shine sweep…<br>"
            "• 🏆 Achievement Toast — burst particles, neon rings, typewriter, god rays, confetti…<br>"
            "• ⚡ Challenge Select — carousel, selection glow, electric arc, plasma noise…<br>"
            "• ⏱️ Timer / Countdown — 3-2-1-GO, radial pulse, urgency shake, glitch numbers…<br>"
            "• 🌡️ Heat Barometer — warning pulse, flame particles, heat shimmer, lava glow…<br>"
            "• 🔢 Flip Counter — breathing glow, counter spin, milestone burst, firework…<br><br>"
            "• <b>Enable All / Disable All</b>: Quick toggle for all 60 effects at once.<br><br>"
            "<b>🎬 Post-Processing</b><br>"
            "Screen-space effects applied on top of overlay windows. Require OpenGL. "
            "Disabled automatically in Low Performance Mode. Use the toggle buttons below "
            "the effect controls to choose which overlays receive post-processing "
            "(Main, Toast, Challenge, Timer, Heat, Flip).<br>"
            "• <b>Bloom</b>: Makes bright and neon elements glow and bleed light into surrounding areas.<br>"
            "• <b>Motion Blur</b>: Adds a directional blur trail to animated elements to simulate motion speed.<br>"
            "• <b>Chromatic Aberration</b>: Slightly offsets the red and blue color channels for a lens distortion or glitch effect.<br>"
            "• <b>Vignette</b>: Darkens the edges of the overlay, drawing focus toward the center.<br>"
            "• <b>Film Grain</b>: Adds subtle random noise over the overlay for a retro analog film or CRT look.<br>"
            "• <b>Scanlines</b>: Overlays horizontal lines to simulate a classic CRT monitor screen.<br>"
            "• <b>Overlay Toggles</b>: Use the buttons below the post-processing effects to enable or disable "
            "post-processing per overlay (Main, Toast, Challenge, Timer, Heat Bar, Flip Counter). "
            "By default, only Main and Toast are enabled.<br><br>"
            "All settings are saved to config.json and persist across restarts.<br>"
            "Effects use OpenGL GPU acceleration when available, with automatic "
            "QPainter CPU fallback on systems without GPU drivers."
        ),
        "available_maps": (
            "<b>📚 Available Maps</b><br><br>"
            "This tab lists all known tables from the cloud index and your local VPX installation.<br><br>"
            "• <b>Search</b>: Filter by table name or ROM name.<br>"
            "• <b>🎯 Local tables with nvram map</b>: Show only locally installed tables that have an NVRAM mapping.<br>"
            "• <b>⚡ Auto-Match All</b>: Automatically assign VPS-IDs to all local ROMs by matching table names, authors and ROM files against the VPS database.<br>"
            "• <b>🔄 Load List</b>: Scan your tables directory and refresh the list.<br>"
            "• <b>📥 Import from Popper</b>: Import VPS-IDs from PinUP Popper's PUPDatabase.db. Reads the CUSTOM3 field (where VPinStudio stores VPS-IDs) and matches tables by filename and name.<br>"
            "• <b>🗑️ Clear VPS Mapping</b>: Deletes all VPS-ID assignments (vps_id_mapping.json) and resets the Popper DB path cache. Use this to start fresh if mappings are incorrect.<br><br>"
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
            "• <b>Challenge Action</b>: Bind a key or button to start or trigger a challenge.<br>"
            "• <b>Challenge Left / Duel Accept</b> and <b>Challenge Right / Duel Decline</b>: Bind keys or buttons for left/right challenge navigation and duel accept/decline (Left = Accept, Right = Decline).<br>"
            "• Select <b>keyboard</b> or <b>joystick</b> as the input source for each binding, then click <b>Bind…</b> and press your desired key or button.<br>"
            "• <b>AI Voice Volume</b>: Adjust the volume of spoken announcements during challenges.<br>"
            "• <b>Mute</b>: Silence all voice announcements.<br><br>"
            "💡 Tip: You can combine keys with Shift, Ctrl, or Alt — just hold the modifier while pressing your key."
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
            "The General sub-tab is where you manage your player profile, cloud sync, "
            "and feedback.<br><br>"
            "• <b>Player Profile</b>: Set your display name and 4-character player ID. "
            "The player ID is required for cloud sync and data recovery — keep it safe!<br>"
            "• <b>Cloud Sync</b>: Enable cloud synchronisation and automatic progress backup.<br>"
            "• <b>Visual Effects</b>: Use the ✨ Effects sub-tab in the Appearance tab to "
            "control individual overlay effects and Low Performance Mode.<br>"
            "• <b>Mascots</b>: Trophie &amp; Steely settings have moved to the "
            "🎨 Appearance → 🏆 Mascots sub-tab.<br>"
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
        "aweditor": (
            "<b>🎯 AWEditor – Custom Achievement System for Non-ROM Tables</b><br><br>"
            "<b>OVERVIEW</b><br>"
            "The AWEditor lets you create custom achievements for tables that don't use VPinMAME ROMs "
            "(Non-ROM or Original tables). Since these tables have no NVRAM data, achievements are "
            "triggered via a file-drop mechanism: the table's VBScript writes a small trigger file, "
            "and the Achievement Watcher detects it instantly.<br><br>"

            "<b>Step 1 – SELECT A TABLE</b><br>"
            "Use the dropdown to select a .vpx table. Only tables WITHOUT an NVRAM map are shown. "
            "Click 🔄 to re-scan your Tables directory.<br><br>"

            "<b>Step 2 – ANALYZE THE TABLE SCRIPT</b><br>"
            "Click '🔍 Analyze Script' to read the table's VBScript. The editor uses vpxtool to "
            "extract the script and scans for common game events: Multiball, Jackpot, Wizard Mode, "
            "Extra Ball, Mission, Ramp/Loop combos, and more. Detected events appear with their "
            "Sub name and line number.<br><br>"

            "<b>Step 3 – SELECT EVENTS AS ACHIEVEMENTS</b><br>"
            "Check the box next to any detected event you want to turn into an achievement. "
            "Each checked event becomes an achievement with an auto-generated title.<br><br>"

            "<b>Step 4 – ADD CUSTOM ACHIEVEMENTS (OPTIONAL)</b><br>"
            "Click [+ Add Achievement] to create your own. Fill in:<br>"
            "• <b>Title</b>: The name shown in the toast notification (e.g. 'Ramp Combo King')<br>"
            "• <b>Description</b>: A short text explaining what to do<br>"
            "• <b>Event Name</b>: A unique identifier, no spaces, lowercase only (e.g. 'ramp_combo_5x')<br><br>"

            "<b>Step 5 – EXPORT</b><br>"
            "Click [💾 Export VBS + JSON] to generate two files in tools/AWeditor/:<br>"
            "• <b>aw_{TableName}.vbs</b> – VBScript with the FireAchievement Sub<br>"
            "• <b>{TableName}.custom.json</b> – Achievement rule definitions<br><br>"

            "<b>INSTALLATION</b><br>"
            "1. Copy aw_{TableName}.vbs next to your .vpx file.<br>"
            "2. Open the table in VPX Editor (File → Open).<br>"
            "3. Open Script Editor (View → Script or F12).<br>"
            "4. Add near the top: <code>LoadScript \"aw_YourTableName.vbs\"</code><br>"
            "5. Find the Subs for each event and add: <code>FireAchievement \"your_event_name\"</code><br><br>"

            "<b>⚠️ IMPORTANT – DO NOT name the .vbs file the same as the table!</b><br>"
            "If 'MyTable.vbs' exists next to 'MyTable.vpx', VPX REPLACES the entire table script "
            "and breaks the table. The 'aw_' prefix prevents this conflict.<br><br>"

            "<b>HOW THE TRIGGER MECHANISM WORKS</b><br>"
            "1. During gameplay, FireAchievement \"multiball\" is called.<br>"
            "2. It writes 'multiball.trigger' into the AWEditor/custom_events/ folder using "
            "the standard Windows Scripting.FileSystemObject (no external DLLs needed).<br>"
            "3. The Achievement Watcher detects the file, matches it against your .custom.json rules, "
            "shows a toast 🏆, and deletes the trigger file automatically.<br><br>"

            "<b>FILE LOCATIONS</b><br>"
            "• Generated scripts &amp; JSON: {BASE}/tools/AWeditor/<br>"
            "• Trigger files: {BASE}/tools/AWeditor/custom_events/<br>"
            "• Copy the aw_*.vbs to: Your Tables directory (next to .vpx)"
        ),
        "appearance_mascots": (
            "<b>🏆 Mascots</b><br><br>"
            "Customize your Trophie and Steely mascots.<br><br>"
            "<b>🏆 Trophie (GUI Mascot)</b><br>"
            "• <b>Show/Hide</b>: Toggle Trophie visibility in the main window.<br>"
            "• <b>Skin Gallery</b>: Browse 22 unique skins. Click a skin card to preview it live. "
            "Click <b>✓ Apply Skin</b> to make it permanent.<br>"
            "• <b>Live Preview</b>: See the selected skin animated in real-time before applying.<br><br>"
            "<b>🎱 Steely (Desktop Overlay Mascot)</b><br>"
            "• <b>Show/Hide</b>: Toggle the desktop overlay widget.<br>"
            "• <b>Portrait Mode</b>: Rotate Steely 90° for vertical cabinet screens.<br>"
            "• <b>Skin Gallery</b>: Browse 22 unique skins with accessories. Click a card to preview, "
            "then <b>✓ Apply Skin</b>.<br>"
            "• <b>Live Preview</b>: See Steely animated with the selected skin before committing."
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
            "QPushButton { background-color: #1a1a1a; color: #FF7F00; border: 1px solid #FF7F00; "
            "border-radius: 14px; font-size: 11pt; font-weight: bold; padding: 0; }"
            "QPushButton:hover { background-color: #FF7F00; color: #000000; }"
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
        lay_inputs.addWidget(QLabel("<b>Challenge Action:</b>"), 2, 0); lay_inputs.addWidget(self.cmb_ch_hotkey_src, 2, 1); lay_inputs.addWidget(self.btn_ch_hotkey_bind, 2, 2); lay_inputs.addWidget(self.lbl_ch_hotkey_binding, 2, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Left / Duel Accept:</b>"), 3, 0); lay_inputs.addWidget(self.cmb_ch_left_src, 3, 1); lay_inputs.addWidget(self.btn_ch_left_bind, 3, 2); lay_inputs.addWidget(self.lbl_ch_left_binding, 3, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Right / Duel Decline:</b>"), 4, 0); lay_inputs.addWidget(self.cmb_ch_right_src, 4, 1); lay_inputs.addWidget(self.btn_ch_right_bind, 4, 2); lay_inputs.addWidget(self.lbl_ch_right_binding, 4, 3)
        lay_inputs.setColumnStretch(3, 1); layout.addWidget(grp_inputs)

        lbl_flipper_hint = QLabel(
            '💡 <b>Tip:</b> For the best experience, bind <b>Challenge Left</b> and <b>Challenge Right</b> '
            'to your flipper buttons (left and right flipper keys). '
            'This way you can navigate challenges and duels without taking your hands off the machine!'
        )
        lbl_flipper_hint.setWordWrap(True)
        lbl_flipper_hint.setStyleSheet(
            "color: #888888; margin-top: 4px; font-size: 9pt; padding: 6px 10px; "
            "background: #1a1a1a; border: 1px solid #333; border-radius: 5px;"
        )
        layout.addWidget(lbl_flipper_hint)

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
        btn_refresh.setStyleSheet(
            "QPushButton { background-color:#FF7F00; color:#000000; font-weight:bold;"
            " border:none; border-radius:5px; padding:7px 16px; }"
        )
        btn_refresh.clicked.connect(self._refresh_available_maps)
        row.addWidget(btn_refresh)

        self.btn_nvram_filter = QPushButton("🎯 Local tables with nvram map")
        self.btn_nvram_filter.setCheckable(True)
        self.btn_nvram_filter.setChecked(False)
        self.btn_nvram_filter.setStyleSheet(
            "QPushButton { background-color:#222222; color:#FF7F00; border:1px solid #FF7F00; font-weight:bold; border-radius:5px; padding:7px 16px; } "
            "QPushButton:checked { background-color:#3D2600; color:#FF7F00; border:1px solid #FF7F00; font-weight:bold; border-radius:5px; padding:7px 16px; }"
        )
        self.btn_nvram_filter.toggled.connect(self._filter_available_maps)
        row.addWidget(self.btn_nvram_filter)

        btn_auto = QPushButton("⚡ Auto-Match All")
        btn_auto.setStyleSheet(
            "QPushButton { background-color:#003333; color:#00E5FF; font-weight:bold;"
            " border:1px solid #00E5FF; border-radius:5px; padding:7px 16px; }"
        )
        btn_auto.clicked.connect(self._on_vps_auto_match_all)
        row.addWidget(btn_auto)

        btn_popper = QPushButton("📥 Import from Popper")
        btn_popper.setStyleSheet(
            "QPushButton { background-color:#1A0A00; color:#FFAA44; font-weight:bold;"
            " border:1px solid #BB6600; border-radius:5px; padding:7px 16px; }"
            "QPushButton:hover { background-color:#2A1400; border-color:#FFAA44; }"
        )
        btn_popper.setToolTip("Import VPS-IDs from PinUP Popper (PUPDatabase.db, reads CUSTOM2 & CUSTOM3)")
        btn_popper.clicked.connect(self._on_import_from_popper)
        row.addWidget(btn_popper)

        btn_clear_vps = QPushButton("🗑️ Clear VPS Mapping")
        btn_clear_vps.setStyleSheet(
            "QPushButton { background-color:#1A0000; color:#FF4444; font-weight:bold;"
            " border:1px solid #AA0000; border-radius:5px; padding:7px 16px; }"
            "QPushButton:hover { background-color:#2A0000; border-color:#FF4444; }"
        )
        btn_clear_vps.setToolTip("Delete vps_id_mapping.json and clear all VPS-ID assignments")
        btn_clear_vps.clicked.connect(self._on_clear_vps_mapping)
        row.addWidget(btn_clear_vps)

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
            "QPushButton { background-color: #FF3B30; color: #FFFFFF; border: 1px solid #FF3B30; "
            "border-radius: 14px; font-size: 10pt; font-weight: bold; padding: 0 8px; }"
            "QPushButton:hover { background-color: #CC2F27; color: #FFFFFF; }"
        )
        btn_rules.clicked.connect(self._show_cloud_rules)
        row.addWidget(btn_rules)

        btn_help = QPushButton("❓")
        btn_help.setFixedSize(28, 28)
        btn_help.setToolTip("Show help for this tab")
        btn_help.setStyleSheet(
            "QPushButton { background-color: #1a1a1a; color: #FF7F00; border: 1px solid #FF7F00; "
            "border-radius: 14px; font-size: 11pt; font-weight: bold; padding: 0; }"
            "QPushButton:hover { background-color: #FF7F00; color: #000000; }"
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
                    if hasattr(self, '_cmb_duel_table'):
                        self._populate_duel_table_combo()
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
            if hasattr(self, '_cmb_duel_table'):
                self._populate_duel_table_combo()
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
                    "QPushButton { background-color:#2a1800; color:#FF7F00; border:1px solid #FF7F00; font-weight:bold; font-size:16px; border-radius:4px; padding:0; } "
                    "QPushButton:hover { background-color:#4a2e00; color:#FF7F00; border:1px solid #FF7F00; font-weight:bold; font-size:16px; border-radius:4px; padding:0; }"
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

    # ------------------------------------------------------------------
    # PinUP Popper VPS-ID Import
    # ------------------------------------------------------------------

    @staticmethod
    def _popper_db_candidates(base: str) -> list:
        """Return ordered list of candidate PUPDatabase.db paths to probe."""
        return [
            os.path.normpath(os.path.join(base, "..", "PinUPSystem", "PUPDatabase.db")),
            r"C:\vPinball\PinUPSystem\PUPDatabase.db",
            r"C:\PinUPSystem\PUPDatabase.db",
            r"D:\vPinball\PinUPSystem\PUPDatabase.db",
            r"D:\PinUPSystem\PUPDatabase.db",
        ]

    @staticmethod
    def _is_valid_popper_db(p: str) -> bool:
        """Return True if *p* is an accessible SQLite file with a Games table."""
        import sqlite3
        if not os.path.isfile(p):
            return False
        try:
            con = sqlite3.connect(p)
            con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Games'")
            con.close()
            return True
        except Exception:
            return False

    def _find_popper_db(self, cancel_event: threading.Event | None = None) -> str | None:
        """
        Locate PUPDatabase.db using three phases:
          1. Cached path from config
          2. Known common install locations
          3. Shallow scan (first 3 directory levels) of all drive letters
        Returns the found path, or None if not found.
        cancel_event: optional threading.Event; scan stops early when set.
        """
        # Phase 1 — cached path
        cached = getattr(self.cfg, "POPPER_DB_PATH", "").strip()
        if cached and self._is_valid_popper_db(cached):
            return cached

        # Phase 2 — known paths
        base = getattr(self.cfg, "BASE", "")
        for p in self._popper_db_candidates(base):
            if self._is_valid_popper_db(p):
                return p

        # Phase 3 — shallow scan (up to 3 levels deep on each drive)
        drives: list[str] = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            if os.path.isdir(root):
                drives.append(root)

        TARGET = "PUPDatabase.db"
        MAX_DEPTH = 3

        for drive in drives:
            for dirpath, dirnames, filenames in os.walk(drive):
                if cancel_event and cancel_event.is_set():
                    return None
                depth = dirpath.replace(drive, "").count(os.sep)
                if depth >= MAX_DEPTH:
                    dirnames.clear()
                    continue
                if TARGET in filenames:
                    candidate = os.path.join(dirpath, TARGET)
                    if self._is_valid_popper_db(candidate):
                        return candidate

        return None

    def _on_import_from_popper(self):
        """Handler for the '📥 Import from Popper' button."""
        import sqlite3

        # ----------------------------------------------------------------
        # Phase 1+2: try fast discovery (no UI blocking)
        # ----------------------------------------------------------------
        db_path: str | None = None

        cached = getattr(self.cfg, "POPPER_DB_PATH", "").strip()
        if cached and os.path.isfile(cached):
            db_path = cached
        else:
            base = getattr(self.cfg, "BASE", "")
            for p in self._popper_db_candidates(base):
                if os.path.isfile(p):
                    db_path = p
                    break

        if db_path is None:
            # Phase 3 — shallow scan in background with progress indicator
            cancel_event = threading.Event()
            found_path: list[str] = []

            def _do_scan():
                result = self._find_popper_db(cancel_event=cancel_event)
                if result and not cancel_event.is_set():
                    found_path.append(result)

            scan_thread = threading.Thread(target=_do_scan, daemon=True)
            scan_thread.start()

            progress = QProgressDialog("Searching for PUPDatabase.db…", "Cancel", 0, 0, self)
            progress.setWindowTitle("📥 Import from Popper")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()

            while scan_thread.is_alive():
                QApplication.processEvents()
                if progress.wasCanceled():
                    cancel_event.set()
                    progress.close()
                    scan_thread.join(timeout=2)
                    return
                scan_thread.join(timeout=0.1)

            progress.close()
            db_path = found_path[0] if found_path else None

        if db_path is None:
            # Fallback — manual path entry
            dlg = QDialog(self)
            dlg.setWindowTitle("📥 Import from Popper — Enter Path")
            dlg.setMinimumWidth(500)
            dlg_layout = QVBoxLayout(dlg)
            lbl = QLabel("PUPDatabase.db not found. Enter path manually:")
            lbl.setStyleSheet("color:#FFAA44;")
            dlg_layout.addWidget(lbl)
            path_edit = QLineEdit()
            path_edit.setPlaceholderText(r"e.g. C:\vPinball\PinUPSystem\PUPDatabase.db")
            path_edit.setStyleSheet(
                "QLineEdit { background:#1A1A1A; color:#EEE; border:1px solid #BB6600;"
                " border-radius:4px; padding:4px 8px; }"
            )
            dlg_layout.addWidget(path_edit)
            btn_row = QHBoxLayout()
            btn_ok = QPushButton("Import")
            btn_ok.setStyleSheet(
                "QPushButton { background-color:#1A0A00; color:#FFAA44; font-weight:bold;"
                " border:1px solid #BB6600; border-radius:4px; padding:5px 14px; }"
            )
            btn_cancel = QPushButton("Cancel")
            btn_cancel.setStyleSheet(
                "QPushButton { background-color:#222; color:#AAA; border:1px solid #555;"
                " border-radius:4px; padding:5px 14px; }"
            )
            btn_row.addStretch(1)
            btn_row.addWidget(btn_ok)
            btn_row.addWidget(btn_cancel)
            dlg_layout.addLayout(btn_row)
            btn_ok.clicked.connect(dlg.accept)
            btn_cancel.clicked.connect(dlg.reject)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            db_path = path_edit.text().strip()
            if not db_path:
                return
            if not os.path.isfile(db_path):
                QMessageBox.warning(self, "Import from Popper",
                                    f"File not found:\n{db_path}")
                return

        # ----------------------------------------------------------------
        # Cache the discovered path
        # ----------------------------------------------------------------
        self.cfg.POPPER_DB_PATH = db_path
        self.cfg.save()

        # ----------------------------------------------------------------
        # Load existing mapping
        # ----------------------------------------------------------------
        mapping: dict = _load_vps_mapping(self.cfg)

        # ----------------------------------------------------------------
        # Build a set of all valid VPS IDs for validation
        # ----------------------------------------------------------------
        vpsdb_tables = _load_vpsdb(self.cfg) or []
        valid_vps_ids: set = set()
        for _t in vpsdb_tables:
            tid = _t.get("id", "")
            if tid:
                valid_vps_ids.add(tid)
            for _tf in _t.get("tableFiles", []):
                tfid = _tf.get("id", "")
                if tfid:
                    valid_vps_ids.add(tfid)

        # ----------------------------------------------------------------
        # Run import
        # ----------------------------------------------------------------
        _query_mode = None  # "both", "c3only", "c2only"
        rows: list = []
        try:
            conn = sqlite3.connect(db_path)
            try:
                cursor = conn.execute(
                    "SELECT GameFileName, GameName, CUSTOM2, CUSTOM3 FROM Games"
                )
                rows = cursor.fetchall()
                _query_mode = "both"
            except sqlite3.OperationalError as exc:
                err = str(exc).lower()
                if "no such column" in err:
                    # CUSTOM2 or CUSTOM3 missing — try CUSTOM3 only
                    try:
                        cursor = conn.execute(
                            "SELECT GameFileName, GameName, CUSTOM3 FROM Games"
                        )
                        rows = cursor.fetchall()
                        _query_mode = "c3only"
                    except sqlite3.OperationalError:
                        # Try CUSTOM2 only as last resort
                        try:
                            cursor = conn.execute(
                                "SELECT GameFileName, GameName, CUSTOM2 FROM Games"
                            )
                            rows = cursor.fetchall()
                            _query_mode = "c2only"
                        except sqlite3.OperationalError as exc3:
                            conn.close()
                            err3 = str(exc3).lower()
                            if "no such table" in err3 or "no such column" in err3:
                                QMessageBox.warning(
                                    self, "Import from Popper",
                                    "No VPS-ID data found in this database.\n"
                                    "Make sure your Popper version supports VPS-IDs."
                                )
                            else:
                                QMessageBox.warning(
                                    self, "Import from Popper",
                                    f"Could not read from PUPDatabase.db.\n{exc3}\n\n"
                                    "If Popper is running, try closing it first."
                                )
                            return
                elif "no such table" in err:
                    conn.close()
                    QMessageBox.warning(
                        self, "Import from Popper",
                        "No VPS-ID data found in this database.\n"
                        "Make sure your Popper version supports VPS-IDs."
                    )
                    return
                else:
                    conn.close()
                    QMessageBox.warning(
                        self, "Import from Popper",
                        f"Could not read from PUPDatabase.db.\n{exc}\n\n"
                        "If Popper is running, try closing it first."
                    )
                    return
            conn.close()
        except sqlite3.OperationalError as exc:
            QMessageBox.warning(
                self, "Import from Popper",
                f"Could not open PUPDatabase.db.\n{exc}\n\n"
                "The file may be corrupted, locked, or currently in use by Popper."
            )
            return
        except Exception as exc:
            QMessageBox.warning(
                self, "Import from Popper",
                f"Unexpected error opening PUPDatabase.db:\n{exc}"
            )
            return

        # ----------------------------------------------------------------
        # Build lookup structures from the in-memory cache for fast matching
        # ----------------------------------------------------------------
        # Map: lowercase vpx basename → cache entry  (for exact filename match)
        cache_by_vpx: dict[str, dict] = {}
        # Map: normalized title → cache entry  (for fuzzy name match)
        cache_by_title: dict[str, dict] = {}
        for entry in self._all_maps_cache:
            vpx_path = entry.get("vpx_path", "")
            if vpx_path:
                cache_by_vpx[os.path.basename(vpx_path).lower()] = entry
            title = entry.get("title", "")
            if title:
                norm = _normalize_term(_strip_version_from_name(title))
                if norm and norm not in cache_by_title:
                    cache_by_title[norm] = entry

        # ----------------------------------------------------------------
        # Match each Popper row against the cache
        # ----------------------------------------------------------------
        imported = 0
        skipped = 0
        matched_by_file = 0
        matched_by_name = 0
        unmatched = 0
        from_custom3 = 0
        from_custom2 = 0
        invalid_id = 0
        for row in rows:
            try:
                game_filename = str(row[0] or "").strip()
                game_name = str(row[1] or "").strip()

                # Extract CUSTOM2/CUSTOM3 based on which query succeeded
                if _query_mode == "both":
                    custom2 = str(row[2] or "").strip()
                    custom3 = str(row[3] or "").strip()
                elif _query_mode == "c3only":
                    custom2 = ""
                    custom3 = str(row[2] or "").strip()
                else:  # c2only
                    custom2 = str(row[2] or "").strip()
                    custom3 = ""

                # Priority: CUSTOM3 first, then CUSTOM2; validate against VPS-DB
                vps_id = ""
                id_source = ""
                for candidate, src in [(custom3, "custom3"), (custom2, "custom2")]:
                    if candidate and candidate in valid_vps_ids:
                        vps_id = candidate
                        id_source = src
                        break

                if not vps_id:
                    if custom3 or custom2:
                        invalid_id += 1
                    continue

                if id_source == "custom3":
                    from_custom3 += 1
                else:
                    from_custom2 += 1

                matched_entry = None

                # Strategy 1: exact VPX filename match
                if game_filename:
                    matched_entry = cache_by_vpx.get(game_filename.lower())
                    if matched_entry:
                        matched_by_file += 1

                # Strategy 2: normalized name match
                # Note: when multiple cache entries share the same normalized title
                # (rare collision), the first entry encountered in cache order is used.
                if matched_entry is None and game_name:
                    norm_game = _normalize_term(_strip_version_from_name(game_name))
                    matched_entry = cache_by_title.get(norm_game)
                    if matched_entry:
                        matched_by_name += 1

                if matched_entry is None:
                    unmatched += 1
                    continue

                rom = matched_entry.get("rom", "")
                if not rom:
                    # Matched a cache entry but it has no ROM identifier — skip silently
                    continue

                if mapping.get(rom):
                    skipped += 1
                else:
                    mapping[rom] = vps_id
                    imported += 1
            except Exception:
                continue

        # ----------------------------------------------------------------
        # Persist and refresh
        # ----------------------------------------------------------------
        _save_vps_mapping(self.cfg, mapping)
        self._cloud_upload_vps_mapping()

        for entry in self._all_maps_cache:
            rom = entry.get("rom", "")
            if rom and mapping.get(rom):
                entry["vps_id"] = mapping[rom]

        self._filter_available_maps()

        QMessageBox.information(
            self, "Import Complete",
            f"Import complete.\n"
            f"{imported} VPS-ID(s) imported from PinUP Popper.\n"
            f"{skipped} already mapped (skipped).\n\n"
            f"From CUSTOM3: {from_custom3}\n"
            f"From CUSTOM2: {from_custom2}\n"
            f"Invalid/non-VPS IDs skipped: {invalid_id}\n\n"
            f"Matched by filename: {matched_by_file}\n"
            f"Matched by name: {matched_by_name}\n"
            f"No local table found: {unmatched}"
        )

    def _on_clear_vps_mapping(self):
        """Handler for the '🗑️ Clear VPS Mapping' button."""
        reply = QMessageBox.question(
            self,
            "Clear VPS Mapping",
            "This will delete vps_id_mapping.json and clear all VPS-ID assignments.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Delete the mapping file
        mapping_path = f_vps_mapping(self.cfg)
        if os.path.isfile(mapping_path):
            os.remove(mapping_path)

        # Clear all vps_id entries in cache
        for entry in self._all_maps_cache:
            entry["vps_id"] = ""

        # Reset the cached Popper DB path
        self.cfg.POPPER_DB_PATH = ""
        self.cfg.save()

        # Upload empty mapping to cloud
        self._cloud_upload_vps_mapping()

        # Refresh the table
        self._filter_available_maps()

        QMessageBox.information(
            self,
            "Clear VPS Mapping",
            "VPS-ID mapping cleared successfully.\n"
            "All VPS-ID assignments have been removed and vps_id_mapping.json has been deleted.",
        )

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
        _set_tip("btn_bind_toggle", "Assign the hotkey used to show/hide the main stats overlay. Hold Shift, Ctrl, or Alt while pressing a key to bind a modifier combination (e.g. Ctrl+F9).")
        _set_tip("lbl_toggle_binding", "Currently assigned hotkey for the main overlay.")
        _set_tip("cmb_ch_hotkey_src", "Input source for the Challenge Action button.")
        _set_tip("btn_ch_hotkey_bind", "Assign the hotkey used to start challenges. Hold Shift, Ctrl, or Alt while pressing a key to bind a modifier combination.")
        _set_tip("lbl_ch_hotkey_binding", "Currently assigned hotkey for challenge actions.")
        _set_tip("cmb_ch_left_src", "Input source for navigating left in Challenge and Duel menus.")
        _set_tip("btn_ch_left_bind", "Assign the hotkey used to navigate left in Challenge and Duel menus. Hold Shift, Ctrl, or Alt while pressing a key to bind a modifier combination.")
        _set_tip("lbl_ch_left_binding", "Currently assigned left navigation hotkey (used to navigate Challenge and Duel menus).")
        _set_tip("cmb_ch_right_src", "Input source for navigating right in Challenge and Duel menus.")
        _set_tip("btn_ch_right_bind", "Assign the hotkey used to navigate right in Challenge and Duel menus. Hold Shift, Ctrl, or Alt while pressing a key to bind a modifier combination.")
        _set_tip("lbl_ch_right_binding", "Currently assigned right navigation hotkey (used to navigate Challenge and Duel menus).")
        _set_tip("sld_ch_volume", "Adjust the volume of the AI voice announcements.")
        _set_tip("chk_ch_voice_mute", "Completely disable spoken voice announcements during challenges.")
        
        # Cloud Tab
        _set_tip("cmb_cloud_category", "Select the leaderboard category you want to view.")
        _set_tip("txt_cloud_rom", "Type the ROM name exactly as it appears in VPX (e.g. afm_113b).")
        _set_tip("btn_cloud_fetch", "Download and display the global highscores from the cloud.")
        
        # System Tab
        _set_tip("txt_player_name", "Enter your display name (used for local records and leaderboards).")
        _set_tip("txt_player_id", "Your unique 4-character ID. Keep this safe to restore your cloud progress after a reinstall!")
        _set_tip("chk_cloud_enabled", "Enable Cloud Sync: validates your Player Name and Player ID, then activates cloud sync. Fields are locked while Cloud Sync is active.")
        _set_tip("chk_cloud_backup", "Enable automatic backup of your achievement progress, scores, and VPS mapping to the cloud.")
        _set_tip("btn_repair", "Recreates missing folders and downloads the base database if corrupted.")
        _set_tip("btn_prefetch", "Forces a background download of all missing NVRAM maps from the internet.")
        _set_tip("base_label", "Current base directory for achievements data.")
        _set_tip("btn_base", "Change the main folder where achievement data and history is saved.")
        _set_tip("nvram_label", "Current NVRAM folder path.")
        _set_tip("btn_nvram", "Change the folder where VPinMAME stores its .nv files.")
        _set_tip("tables_label", "Current VPX tables folder path (optional).")
        _set_tip("btn_tables", "Change the folder where Visual Pinball tables (.vpx) are located.")

    def _init_settings_tooltips(self):
        pass
     
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

    def showEvent(self, event):
        super().showEvent(event)
        _TROPHIE_SHARED["gui_visible"] = (
            bool(self.cfg.OVERLAY.get("trophie_gui_enabled", True)) and
            bool(self.cfg.OVERLAY.get("trophie_overlay_enabled", True))
        )
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.update_position(self.centralWidget().size())
        except Exception:
            pass

    def hideEvent(self, event):
        super().hideEvent(event)
        _TROPHIE_SHARED["gui_visible"] = self.isVisible()

    def changeEvent(self, event):
        super().changeEvent(event)
        _TROPHIE_SHARED["gui_visible"] = self.isVisible()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.update_position(self.centralWidget().size())
        except Exception:
            pass

    def closeEvent(self, event):
        _TROPHIE_SHARED["gui_visible"] = False
        self.cfg.save()
        try:
            if getattr(self, "tray", None) and self.tray and self.tray.isVisible():
                self.hide()
                event.ignore()
                return
        except Exception:
            pass
        # Stop duel timers only on actual quit (not when minimizing to systray).
        try:
            if getattr(self, "_duel_poll_timer", None):
                self._duel_poll_timer.stop()
            if getattr(self, "_duel_expiry_timer", None):
                self._duel_expiry_timer.stop()
            if getattr(self, "_duel_accept_timer", None):
                self._duel_accept_timer.stop()
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
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.on_achievement()
        except Exception:
            pass
        try:
            if getattr(self, "_trophie_overlay", None):
                self._trophie_overlay.on_achievement()
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
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.on_level_up()
        except Exception:
            pass
        try:
            if getattr(self, "_trophie_overlay", None):
                self._trophie_overlay.on_level_up()
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
        # Schedule a cloud leaderboard refresh so the updated badge icon appears immediately
        try:
            QTimer.singleShot(3000, self._fetch_cloud_leaderboard)
        except Exception:
            pass

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


if __name__ == "__main__":
    main()

