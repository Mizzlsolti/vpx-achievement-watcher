"""Score-Duels-tab mixin: Score Duels tab, alert bar, active duels table,
start new duel, history table, and all duel event handlers."""
from __future__ import annotations

import os
import random
import threading
import time
from datetime import datetime

from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QCompleter, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, QStringListModel, pyqtSlot

from config import p_aweditor
from duel_engine import DuelEngine, DuelStatus
from watcher_core import _strip_version_from_name


# ---------------------------------------------------------------------------
# Floating duel invitation overlay (shown when GUI is minimized / in systray)
# ---------------------------------------------------------------------------

class DuelInviteOverlay(QWidget):
    """Floating always-on-top duel invitation overlay.

    Appears when the main GUI is minimized or hidden to the system tray.
    Shows the challenger name and table, and provides Accept/Decline buttons
    with a visible 15-second countdown.  Auto-declines on timeout.

    Parameters
    ----------
    parent_gui : MainWindow
        The main application window (used for VPX-running check).
    opponent : str
        Display name of the challenging player.
    table_name : str
        Display name of the table being challenged on.
    duel_id : str
        Unique ID of the duel invitation.
    on_accept : callable
        Called with ``(duel_id)`` when the user accepts (after all checks pass).
    on_decline : callable
        Called with ``(duel_id)`` when the user declines or the timer expires.
    """

    _WIDTH  = 460
    _HEIGHT = 185

    def __init__(
        self,
        parent_gui,
        opponent: str,
        table_name: str,
        duel_id: str,
        on_accept,
        on_decline,
    ) -> None:
        super().__init__(None)
        self._parent_gui = parent_gui
        self._opponent   = opponent
        self._table_name = table_name
        self._duel_id    = duel_id
        self._on_accept  = on_accept
        self._on_decline = on_decline
        self._countdown  = 15
        self._closed     = False

        self.setWindowTitle("⚔️ Score Duel Invitation")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setFixedSize(self._WIDTH, self._HEIGHT)

        # ── layout ────────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)

        lbl_title = QLabel("⚔️  Score Duel Invitation")
        lbl_title.setStyleSheet(
            "color:#FF7F00; font-size:12pt; font-weight:bold; background:transparent;"
        )
        root.addWidget(lbl_title)

        self._lbl_msg = QLabel(
            f"You have been challenged by <b>{opponent}</b><br>"
            f"Table: <b>{table_name}</b>"
        )
        self._lbl_msg.setWordWrap(True)
        self._lbl_msg.setStyleSheet(
            "color:#EEEEEE; font-size:10pt; background:transparent;"
        )
        root.addWidget(self._lbl_msg)

        btn_row = QHBoxLayout()
        self._btn_accept = QPushButton("✅  Accept  [Enter]")
        self._btn_accept.setStyleSheet(
            "QPushButton { background-color:#006400; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:7px 18px; font-size:9pt; }"
            "QPushButton:hover { background-color:#008000; }"
        )
        self._btn_accept.clicked.connect(self._on_accept_clicked)

        self._btn_decline = QPushButton("❌  Decline  [Esc]")
        self._btn_decline.setStyleSheet(
            "QPushButton { background-color:#8B0000; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:7px 18px; font-size:9pt; }"
            "QPushButton:hover { background-color:#AA0000; }"
        )
        self._btn_decline.clicked.connect(self._on_decline_clicked)

        self._lbl_cd = QLabel(f"⏳ {self._countdown}s")
        self._lbl_cd.setStyleSheet(
            "color:#FFAA00; font-size:10pt; font-weight:bold; background:transparent;"
        )

        btn_row.addWidget(self._btn_accept)
        btn_row.addWidget(self._btn_decline)
        btn_row.addStretch(1)
        btn_row.addWidget(self._lbl_cd)
        root.addLayout(btn_row)

        # ── position on primary screen (top-right corner) ─────────────────
        self._place_on_screen()

        # ── countdown timer ───────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ── painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor("#2a1000"))
        p.setPen(QPen(QColor("#FF7F00"), 2))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

    # ── helpers ───────────────────────────────────────────────────────────

    def _place_on_screen(self) -> None:
        try:
            scr = QApplication.primaryScreen()
            geo = scr.availableGeometry() if scr else None
            if geo:
                x = geo.right() - self._WIDTH - 20
                y = geo.top() + 80
                self.move(x, y)
        except Exception:
            pass

    def _tick(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self._auto_decline()
        else:
            self._lbl_cd.setText(f"⏳ {self._countdown}s")

    def _auto_decline(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        try:
            self._on_decline(self._duel_id)
        except Exception:
            pass
        self.close()

    def _on_accept_clicked(self) -> None:
        if self._closed:
            return
        # Check VPX running — auto-decline if so.
        try:
            w = getattr(self._parent_gui, "watcher", None)
            if w and (w.game_active or w._vp_player_visible()):
                self._closed = True
                self._timer.stop()
                self._lbl_msg.setText(
                    "⚠️ Cannot accept duel while VPX is running.<br>"
                    "The invitation has been declined."
                )
                self._btn_accept.setEnabled(False)
                self._btn_decline.setEnabled(False)
                QTimer.singleShot(2500, self.close)
                try:
                    self._on_decline(self._duel_id)
                except Exception:
                    pass
                return
        except Exception:
            pass
        self._closed = True
        self._timer.stop()
        try:
            self._on_accept(self._duel_id)
        except Exception:
            pass
        self.close()

    def _on_decline_clicked(self) -> None:
        if self._closed:
            return
        self._auto_decline()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_accept_clicked()
        elif key == Qt.Key.Key_Escape:
            self._on_decline_clicked()
        else:
            super().keyPressEvent(event)


class DuelsMixin:
    """Mixin that provides the Score Duels tab and all related UI methods.

    Expects the host class to provide:
        self.cfg            – AppConfig instance
        self.watcher        – Watcher instance
        self.main_tabs      – QTabWidget (main tab bar)
        self._add_tab_help_button(layout, key)  – adds the Help button to a tab layout
    """

    # ==========================================
    # TAB: SCORE DUELS
    # ==========================================

    def _build_tab_duels(self):
        """Build the '⚔️ Score Duels' tab and wire up all timers."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Instantiate the duel engine.
        self._duel_engine = DuelEngine(self.cfg)

        # ── a) Incoming Invitation Alert Bar ────────────────────────────────
        self._duel_alert_frame = QFrame()
        self._duel_alert_frame.setStyleSheet(
            "QFrame { background-color:#3a1a00; border:2px solid #FF7F00;"
            " border-radius:8px; padding:6px; }"
        )
        alert_layout = QVBoxLayout(self._duel_alert_frame)
        alert_layout.setContentsMargins(10, 6, 10, 6)
        alert_layout.setSpacing(4)

        self._duel_alert_label = QLabel("")
        self._duel_alert_label.setStyleSheet(
            "color:#FF7F00; font-size:11pt; font-weight:bold;"
        )
        self._duel_alert_label.setWordWrap(True)
        alert_layout.addWidget(self._duel_alert_label)

        alert_btn_row = QHBoxLayout()
        self._btn_duel_accept = QPushButton("✅ Accept")
        self._btn_duel_accept.setStyleSheet(
            "QPushButton { background-color:#006400; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:6px 18px; }"
            "QPushButton:hover { background-color:#008000; }"
        )
        self._btn_duel_accept.clicked.connect(self._on_duel_accept)

        self._btn_duel_decline = QPushButton("❌ Decline")
        self._btn_duel_decline.setStyleSheet(
            "QPushButton { background-color:#8B0000; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:6px 18px; }"
            "QPushButton:hover { background-color:#AA0000; }"
        )
        self._btn_duel_decline.clicked.connect(self._on_duel_decline)

        self._lbl_duel_countdown = QLabel("")
        self._lbl_duel_countdown.setStyleSheet(
            "color:#FFAA00; font-size:10pt; font-weight:bold; margin-left:12px;"
        )

        alert_btn_row.addWidget(self._btn_duel_accept)
        alert_btn_row.addWidget(self._btn_duel_decline)
        alert_btn_row.addWidget(self._lbl_duel_countdown)
        alert_btn_row.addStretch(1)
        alert_layout.addLayout(alert_btn_row)

        layout.addWidget(self._duel_alert_frame)
        self._duel_alert_frame.setVisible(False)

        # Countdown timer for incoming invitation (15 seconds).
        self._duel_accept_timer = QTimer(self)
        self._duel_accept_timer.setInterval(1000)
        self._duel_accept_timer.timeout.connect(self._on_duel_invitation_timeout)
        self._duel_accept_countdown = 0
        self._pending_invitation_duel_id: str = ""

        # ── b) Start New Duel ────────────────────────────────────────────────
        grp_new = QGroupBox("⚔️ Start New Duel")
        lay_new = QVBoxLayout(grp_new)

        row_opponent = QHBoxLayout()
        row_opponent.addWidget(QLabel("Opponent:"))
        self._cmb_duel_opponent = QComboBox()
        self._cmb_duel_opponent.setEditable(True)
        self._cmb_duel_opponent.setMinimumWidth(220)
        self._cmb_duel_opponent.addItem("Loading players…", "")
        self._cmb_duel_opponent.lineEdit().setPlaceholderText("Type to filter players…")
        self._duel_opponent_completer = QCompleter(self._cmb_duel_opponent.model(), self)
        self._duel_opponent_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._duel_opponent_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._cmb_duel_opponent.setCompleter(self._duel_opponent_completer)
        row_opponent.addWidget(self._cmb_duel_opponent, 1)

        self._btn_duel_refresh_players = QPushButton("🔄 Refresh Players")
        self._btn_duel_refresh_players.setStyleSheet(
            "QPushButton { background-color:#005c99; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:6px 14px; }"
            "QPushButton:hover { background-color:#0070bb; }"
        )
        self._btn_duel_refresh_players.clicked.connect(self._fetch_duel_opponents)
        row_opponent.addWidget(self._btn_duel_refresh_players)
        lay_new.addLayout(row_opponent)

        self._cmb_duel_opponent.setMaxVisibleItems(20)

        row_table = QHBoxLayout()
        row_table.addWidget(QLabel("Table:"))
        self._cmb_duel_table = QComboBox()
        self._cmb_duel_table.setEditable(True)
        self._cmb_duel_table.setMinimumWidth(250)
        self._cmb_duel_table.lineEdit().setPlaceholderText("Type to filter tables...")
        self._cmb_duel_table.setMaxVisibleItems(20)

        self._duel_table_completer = QCompleter(self._cmb_duel_table.model(), self)
        self._duel_table_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._duel_table_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._cmb_duel_table.setCompleter(self._duel_table_completer)
        row_table.addWidget(self._cmb_duel_table, 1)

        self._btn_duel_start = QPushButton("⚔️ Start Duel")
        self._btn_duel_start.setStyleSheet(
            "QPushButton { background-color:#FF7F00; color:#000000; font-weight:bold;"
            " border:none; border-radius:5px; padding:6px 18px; }"
            "QPushButton:hover { background-color:#FFA040; }"
        )
        self._btn_duel_start.clicked.connect(self._on_duel_start_clicked)
        row_table.addWidget(self._btn_duel_start)
        lay_new.addLayout(row_table)

        self._lbl_duel_status = QLabel("")
        self._lbl_duel_status.setStyleSheet("color:#00E5FF; font-style:italic;")
        lay_new.addWidget(self._lbl_duel_status)

        layout.addWidget(grp_new)

        # ── c) Active Duels ──────────────────────────────────────────────────
        grp_active = QGroupBox("🔵 Active Duels")
        lay_active = QVBoxLayout(grp_active)

        self._tbl_active_duels = QTableWidget(0, 5)
        self._tbl_active_duels.setHorizontalHeaderLabels(
            ["Opponent", "Table", "Status", "Time Remaining", "Actions"]
        )
        self._tbl_active_duels.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._tbl_active_duels.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tbl_active_duels.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_active_duels.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_active_duels.setAlternatingRowColors(True)
        self._tbl_active_duels.setStyleSheet(
            "QTableWidget { background:#111; color:#DDD; gridline-color:#333; }"
            "QTableWidget::item:alternate { background:#1a1a1a; }"
            "QTableWidget::item:selected { background:#1a3a1a; }"
            "QHeaderView::section { background:#222; color:#FF7F00; font-weight:bold;"
            " border:1px solid #333; padding:4px; }"
        )
        self._tbl_active_duels.setMinimumHeight(120)
        lay_active.addWidget(self._tbl_active_duels)

        btn_row_active = QHBoxLayout()
        btn_refresh_active = QPushButton("🔄 Refresh")
        btn_refresh_active.setStyleSheet(
            "QPushButton { background-color:#00E5FF; color:#000000; font-weight:bold;"
            " border:none; border-radius:5px; padding:6px 14px; }"
        )
        btn_refresh_active.clicked.connect(self._refresh_active_duels)
        btn_row_active.addWidget(btn_refresh_active)
        btn_row_active.addStretch(1)
        lay_active.addLayout(btn_row_active)
        layout.addWidget(grp_active)

        # ── d) Duel History ──────────────────────────────────────────────────
        grp_history = QGroupBox("📜 Duel History")
        lay_history = QVBoxLayout(grp_history)

        self._tbl_duel_history = QTableWidget(0, 6)
        self._tbl_duel_history.setHorizontalHeaderLabels(
            ["Opponent", "Table", "Result", "Your Score", "Their Score", "Date"]
        )
        self._tbl_duel_history.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._tbl_duel_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_duel_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_duel_history.setAlternatingRowColors(True)
        self._tbl_duel_history.setStyleSheet(
            "QTableWidget { background:#111; color:#DDD; gridline-color:#333; }"
            "QTableWidget::item:alternate { background:#1a1a1a; }"
            "QTableWidget::item:selected { background:#1a3a3a; }"
            "QHeaderView::section { background:#222; color:#FF7F00; font-weight:bold;"
            " border:1px solid #333; padding:4px; }"
        )
        self._tbl_duel_history.setMinimumHeight(120)
        lay_history.addWidget(self._tbl_duel_history)

        btn_row_hist = QHBoxLayout()
        btn_refresh_hist = QPushButton("🔄 Refresh History")
        btn_refresh_hist.setStyleSheet(
            "QPushButton { background-color:#00E5FF; color:#000000; font-weight:bold;"
            " border:none; border-radius:5px; padding:6px 14px; }"
        )
        btn_refresh_hist.clicked.connect(self._refresh_duel_history)
        btn_row_hist.addWidget(btn_refresh_hist)
        btn_row_hist.addStretch(1)
        lay_history.addLayout(btn_row_hist)
        layout.addWidget(grp_history)

        # ── e) Bottom ────────────────────────────────────────────────────────
        layout.addStretch(1)
        self._add_tab_help_button(layout, "duels")
        self.main_tabs.addTab(tab, "⚔️ Score Duels")

        # ── Populate table dropdown from maps cache ──────────────────────────
        self._populate_duel_table_combo()

        # ── Fetch opponent players from cloud in background ──────────────────
        if getattr(self.cfg, "CLOUD_ENABLED", False):
            self._fetch_duel_opponents()

        # ── Polling timers ───────────────────────────────────────────────────
        # Poll for incoming invitations every 30 seconds (cloud only).
        self._duel_poll_timer = QTimer(self)
        self._duel_poll_timer.setInterval(30_000)
        self._duel_poll_timer.timeout.connect(self._poll_duel_invitations)
        if getattr(self.cfg, "CLOUD_ENABLED", False):
            self._duel_poll_timer.start()

        # Check duel expiry every 60 seconds.
        self._duel_expiry_timer = QTimer(self)
        self._duel_expiry_timer.setInterval(60_000)
        self._duel_expiry_timer.timeout.connect(self._check_duel_expiry)
        self._duel_expiry_timer.start()

        # Initial populate.
        self._refresh_active_duels()
        self._refresh_duel_history()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _populate_duel_table_combo(self) -> None:
        """Populate the table selection dropdown from the available maps cache.

        Filters the cache to entries that have an NVRAM map AND are locally
        installed, sorts them alphabetically by title, and adds them to the
        combo box.  Falls back to vps_id_mapping.json (ROMs the user has ever
        assigned a VPS-ID) when _all_maps_cache has no matching entries, e.g.
        on first launch before the map list has been loaded.
        """
        self._cmb_duel_table.clear()
        self._cmb_duel_table.addItem("— Select Table —", "")
        cache = getattr(self, "_all_maps_cache", None) or []
        entries = sorted(
            (e for e in cache if isinstance(e, dict) and e.get("has_map") and e.get("is_local")),
            key=lambda e: e.get("title", e.get("rom", "")).lower(),
        )
        for entry in entries:
            title = entry.get("title") or entry.get("rom", "")
            rom = entry.get("rom", "")
            clean_title = _strip_version_from_name(title)
            display = clean_title
            self._cmb_duel_table.addItem(display, rom)
        if not entries:
            # Fallback: use vps_id_mapping.json (always present if the user has
            # ever assigned a VPS-ID to a table, even before the map list loads).
            try:
                from ui_vps import _load_vps_mapping
                mapping = _load_vps_mapping(self.cfg)
            except Exception:
                mapping = {}
            if mapping:
                romnames = getattr(getattr(self, "watcher", None), "ROMNAMES", {})
                fallback_entries = sorted(mapping.keys(), key=lambda r: (romnames.get(r) or r).lower())
                for rom in fallback_entries:
                    title = romnames.get(rom) or rom
                    clean_title = _strip_version_from_name(title)
                    display = clean_title
                    self._cmb_duel_table.addItem(display, rom)
            else:
                self._cmb_duel_table.addItem("(No tables found – load the map list first)", "")

        # Add CAT tables from AWEditor (.custom.json files).
        try:
            aw_dir = p_aweditor(self.cfg)
            if os.path.isdir(aw_dir):
                existing_data = [self._cmb_duel_table.itemData(i) for i in range(self._cmb_duel_table.count())]
                for fname in sorted(os.listdir(aw_dir)):
                    if fname.endswith(".custom.json"):
                        table_key = fname[:-len(".custom.json")]
                        clean_name = _strip_version_from_name(table_key)
                        display = clean_name
                        if table_key not in existing_data:
                            self._cmb_duel_table.addItem(display, table_key)
        except Exception:
            pass

        # Build autocomplete suggestions: both display names and ROM names.
        suggestions: list[str] = []
        seen: set[str] = set()
        for i in range(self._cmb_duel_table.count()):
            display = self._cmb_duel_table.itemText(i)
            rom = self._cmb_duel_table.itemData(i) or ""
            if display and display not in seen:
                seen.add(display)
                suggestions.append(display)
            if rom and rom not in seen:
                seen.add(rom)
                suggestions.append(rom)

        # Also add all known ROM names and table titles from ROMNAMES for broader autocomplete.
        try:
            romnames = getattr(getattr(self, "watcher", None), "ROMNAMES", {}) or {}
            for rom_key, table_title in romnames.items():
                if rom_key and rom_key not in seen:
                    seen.add(rom_key)
                    suggestions.append(rom_key)
                if table_title and table_title not in seen:
                    seen.add(table_title)
                    suggestions.append(table_title)
        except Exception:
            pass

        suggestions.sort(key=str.lower)

        if not hasattr(self, '_duel_table_completer_model'):
            self._duel_table_completer_model = QStringListModel(suggestions, self)
        else:
            self._duel_table_completer_model.setStringList(suggestions)
        self._duel_table_completer.setModel(self._duel_table_completer_model)

        # Connect completer activation to select correct combo entry.
        try:
            self._duel_table_completer.activated.disconnect()
        except Exception:
            pass
        self._duel_table_completer.activated.connect(self._on_duel_table_completer_activated)

    # ── Slot: fetch opponent players from cloud ───────────────────────────────

    def _on_duel_table_completer_activated(self, text: str) -> None:
        """When autocomplete selects something, find the matching combo entry.

        Supports both table name and ROM name matching.
        """
        cmb = self._cmb_duel_table
        # First try exact display text match.
        idx = cmb.findText(text, Qt.MatchFlag.MatchExactly)
        if idx >= 0:
            cmb.setCurrentIndex(idx)
            return
        # Then try matching by ROM (itemData).
        for i in range(cmb.count()):
            if (cmb.itemData(i) or "").lower() == text.lower():
                cmb.setCurrentIndex(i)
                return
        # Try reverse lookup via ROMNAMES (table title → ROM).
        try:
            romnames = getattr(getattr(self, "watcher", None), "ROMNAMES", {}) or {}
            for rk, rv in romnames.items():
                if rv and rv.lower() == text.lower():
                    for i in range(cmb.count()):
                        if (cmb.itemData(i) or "").lower() == rk.lower():
                            cmb.setCurrentIndex(i)
                            return
        except Exception:
            pass
        # Fallback: partial match on display text.
        idx = cmb.findText(text, Qt.MatchFlag.MatchContains)
        if idx >= 0:
            cmb.setCurrentIndex(idx)

    def _fetch_duel_opponents(self) -> None:
        """Fetch all player names from the cloud and populate the opponent combo box.

        Runs in a background thread to avoid blocking the UI.  Shows a
        "Loading players…" placeholder while fetching.
        """
        if not getattr(self.cfg, "CLOUD_ENABLED", False):
            self._cmb_duel_opponent.clear()
            self._cmb_duel_opponent.addItem("(Cloud Sync disabled)", "")
            return
        self._cmb_duel_opponent.clear()
        self._cmb_duel_opponent.addItem("Loading players…", "")
        self._btn_duel_refresh_players.setEnabled(False)

        def _load():
            from cloud_sync import CloudSync
            try:
                player_ids = CloudSync.fetch_player_ids(self.cfg) or []
                my_id = self.cfg.OVERLAY.get("player_id", "").strip()
                other_ids = [pid for pid in player_ids if pid != my_id]
                name_nodes = [f"players/{pid}/achievements/name" for pid in other_ids]
                names_map: dict[str, str] = {}
                if name_nodes:
                    results = CloudSync.fetch_parallel(self.cfg, name_nodes) or {}
                    for pid in other_ids:
                        node = f"players/{pid}/achievements/name"
                        raw = results.get(node)
                        if isinstance(raw, str):
                            names_map[pid] = raw
                        elif isinstance(raw, dict):
                            names_map[pid] = raw.get("name", "")
                        else:
                            names_map[pid] = ""
                players = []
                for pid in other_ids:
                    name = names_map.get(pid, "").strip()
                    if name and name != "Player":
                        players.append((name, pid))
                players.sort(key=lambda x: x[0].lower())
            except Exception:
                players = []
            from PyQt6.QtCore import QMetaObject, Q_ARG, Qt
            QMetaObject.invokeMethod(
                self, "_on_duel_players_loaded",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(object, players),
            )

        threading.Thread(target=_load, daemon=True).start()

    @pyqtSlot(object)
    def _on_duel_players_loaded(self, players) -> None:
        """Populate the opponent combo box with the fetched player list."""
        self._btn_duel_refresh_players.setEnabled(True)
        self._cmb_duel_opponent.clear()
        if not players:
            self._cmb_duel_opponent.addItem("(No players found)", "")
            return
        self._cmb_duel_opponent.addItem("— Select Player —", "")
        for display_name, player_id in players:
            self._cmb_duel_opponent.addItem(display_name, player_id)
        self._cmb_duel_opponent.setCurrentIndex(0)

    # ── Slot: start duel ─────────────────────────────────────────────────────

    def _on_duel_start_clicked(self) -> None:
        """Send a duel invitation to the selected opponent for the chosen table.

        Validates that an opponent has been selected and a valid table ROM has
        been chosen, that Cloud Sync is enabled, and then delegates to
        DuelEngine.send_invitation().  Updates the status label with success
        or failure feedback and refreshes the Active Duels table on success.
        """
        opponent_id = self._cmb_duel_opponent.currentData() or ""
        opponent_name = self._cmb_duel_opponent.currentText().strip()
        if not opponent_id:
            self._lbl_duel_status.setText("⚠️ Select an opponent first.")
            self._lbl_duel_status.setStyleSheet("color:#FFAA00; font-style:italic;")
            return
        idx = self._cmb_duel_table.currentIndex()
        table_rom = self._cmb_duel_table.itemData(idx) or ""
        table_name = self._cmb_duel_table.currentText()
        if not table_rom:
            self._lbl_duel_status.setText("⚠️ Select a valid table first.")
            self._lbl_duel_status.setStyleSheet("color:#FFAA00; font-style:italic;")
            return
        if not getattr(self.cfg, "CLOUD_ENABLED", False):
            self._lbl_duel_status.setText("⚠️ Cloud Sync is disabled. Enable it in System → General.")
            self._lbl_duel_status.setStyleSheet("color:#FFAA00; font-style:italic;")
            return

        duel = self._duel_engine.send_invitation(opponent_id, table_rom, table_name,
                                                  opponent_name=opponent_name)
        if duel:
            self._lbl_duel_status.setText(
                f"✅ Invitation sent to '{opponent_name or opponent_id}' for '{table_name}'!"
            )
            self._lbl_duel_status.setStyleSheet("color:#00E500; font-style:italic;")
            self._refresh_active_duels()
        else:
            self._lbl_duel_status.setText("❌ Failed to send invitation. Check Cloud Sync.")
            self._lbl_duel_status.setStyleSheet("color:#CC4444; font-style:italic;")

    # ── Slot: accept / decline invitation ────────────────────────────────────

    def _on_duel_accept(self) -> None:
        """Accept the currently displayed incoming duel invitation.

        Checks VPX running state and table availability before accepting.
        Stops the 15-second countdown timer, hides the alert bar, and either
        declines with an error message or delegates to DuelEngine.accept_duel().
        """
        duel_id = self._pending_invitation_duel_id
        self._duel_accept_timer.stop()
        self._duel_alert_frame.setVisible(False)
        if not duel_id:
            return

        # Check VPX running — cannot accept while VPX is active.
        try:
            w = getattr(self, "watcher", None)
            if w and (w.game_active or w._vp_player_visible()):
                self._duel_engine.decline_duel(duel_id)
                self._refresh_active_duels()
                try:
                    self._get_mini_overlay().show_info(
                        "Cannot accept duel while VPX is running.",
                        seconds=5,
                        color_hex="#CC5500",
                    )
                except Exception:
                    pass
                try:
                    if getattr(self, "_trophie_gui", None):
                        self._trophie_gui.on_duel_declined()
                    if getattr(self, "_trophie_overlay", None):
                        self._trophie_overlay.on_duel_declined()
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Check table availability.
        try:
            duel = next(
                (d for d in self._duel_engine.get_active_duels() if d.duel_id == duel_id),
                None,
            )
            if duel and not self._duel_engine.validate_table(
                duel.table_rom, getattr(self, "_all_maps_cache", [])
            ):
                tname = duel.table_name or duel.table_rom
                self._duel_engine.decline_duel(duel_id)
                self._refresh_active_duels()
                try:
                    self._get_mini_overlay().show_info(
                        f"Duel cancelled \u2013 Table \u2018{tname}\u2019 is not available.",
                        seconds=6,
                        color_hex="#CC2200",
                    )
                except Exception:
                    pass
                return
        except Exception:
            pass

        self._duel_engine.accept_duel(duel_id)
        self._refresh_active_duels()

    def _on_duel_decline(self) -> None:
        """Decline the currently displayed incoming duel invitation.

        Stops the 15-second countdown timer, hides the alert bar, delegates
        to DuelEngine.decline_duel(), and refreshes the Active Duels table.
        """
        duel_id = self._pending_invitation_duel_id
        self._duel_accept_timer.stop()
        self._duel_alert_frame.setVisible(False)
        if duel_id:
            self._duel_engine.decline_duel(duel_id)
            self._refresh_active_duels()
            try:
                if getattr(self, "_trophie_gui", None):
                    self._trophie_gui.on_duel_declined()
                if getattr(self, "_trophie_overlay", None):
                    self._trophie_overlay.on_duel_declined()
            except Exception:
                pass

    # ── Slot: incoming invitation ─────────────────────────────────────────────

    @pyqtSlot(str, str, str)
    def _on_duel_invitation_received(self, opponent: str, table_name: str, duel_id: str) -> None:
        """Handle an incoming duel invitation.

        If the main GUI is visible the in-tab alert bar is shown.  When the
        window is minimized or hidden (e.g. to the system tray) a floating
        :class:`DuelInviteOverlay` is used instead so the user still sees the
        invitation.

        Parameters
        ----------
        opponent : str
            Display name of the challenger.
        table_name : str
            Name of the table being challenged on.
        duel_id : str
            Unique ID of the incoming duel.
        """
        self._pending_invitation_duel_id = duel_id

        gui_hidden = not self.isVisible() or self.isMinimized()

        if gui_hidden:
            # Close any previous invite overlay before showing a new one.
            try:
                prev = getattr(self, "_duel_invite_overlay", None)
                if prev is not None:
                    prev._auto_decline()
            except Exception:
                pass

            def _accept_cb(did: str) -> None:
                # Table availability check is handled here; VPX check is in overlay.
                try:
                    duel = next(
                        (d for d in self._duel_engine.get_active_duels() if d.duel_id == did),
                        None,
                    )
                    if duel and not self._duel_engine.validate_table(
                        duel.table_rom, getattr(self, "_all_maps_cache", [])
                    ):
                        tname = duel.table_name or duel.table_rom
                        self._duel_engine.decline_duel(did)
                        self._refresh_active_duels()
                        try:
                            self._get_mini_overlay().show_info(
                                f"Duel cancelled \u2013 Table \u2018{tname}\u2019 is not available.",
                                seconds=6,
                                color_hex="#CC2200",
                            )
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
                self._duel_engine.accept_duel(did)
                self._refresh_active_duels()

            def _decline_cb(did: str) -> None:
                self._duel_engine.decline_duel(did)
                self._refresh_active_duels()
                try:
                    if getattr(self, "_trophie_gui", None):
                        self._trophie_gui.on_duel_declined()
                    if getattr(self, "_trophie_overlay", None):
                        self._trophie_overlay.on_duel_declined()
                except Exception:
                    pass

            self._duel_invite_overlay = DuelInviteOverlay(
                self, opponent, table_name, duel_id, _accept_cb, _decline_cb
            )
            self._duel_invite_overlay.show()
        else:
            # GUI is visible — use the in-tab alert bar.
            self._duel_alert_label.setText(
                f"⚔️ You have been challenged to a Score Duel by {opponent} "
                f"(Table: {table_name}). Accept?"
            )
            self._duel_accept_countdown = 15
            self._lbl_duel_countdown.setText(f"⏳ {self._duel_accept_countdown}s")
            self._duel_alert_frame.setVisible(True)
            self._duel_accept_timer.start()

            # Switch to the Score Duels tab so the user notices the alert.
            for i in range(self.main_tabs.count()):
                if self.main_tabs.tabText(i) == "⚔️ Score Duels":
                    self.main_tabs.setCurrentIndex(i)
                    break

    # ── Slot: countdown tick ──────────────────────────────────────────────────

    def _on_duel_invitation_timeout(self) -> None:
        """Called every second during the 15-second accept window.
        Auto-declines when the counter reaches zero.
        """
        self._duel_accept_countdown -= 1
        if self._duel_accept_countdown <= 0:
            self._duel_accept_timer.stop()
            self._duel_alert_frame.setVisible(False)
            if self._pending_invitation_duel_id:
                self._duel_engine.decline_duel(self._pending_invitation_duel_id)
                self._pending_invitation_duel_id = ""
            self._refresh_active_duels()
        else:
            self._lbl_duel_countdown.setText(f"⏳ {self._duel_accept_countdown}s")

    # ── Slot: duel result ─────────────────────────────────────────────────────

    def _on_duel_result(self, duel_id: str, result: str, your_score: int, their_score: int) -> None:
        """Handle a completed duel result update from the bridge.

        Parameters
        ----------
        duel_id : str
            The duel that was completed.
        result : str
            'won', 'lost', or 'expired'.
        your_score : int
            Your final score.
        their_score : int
            Opponent's final score.
        """
        self._refresh_active_duels()
        self._refresh_duel_history()
        self._show_duel_result_overlay(result, your_score, their_score)

    # ── Helper: result overlay ────────────────────────────────────────────────

    def _show_duel_result_overlay(self, result: str, your_score: int, their_score: int) -> None:
        """Display a brief result overlay after a duel completes.

        Uses :class:`~ui_overlay.MiniInfoOverlay` (the System Notifications
        widget) to show a win, loss, or expiry message with the final scores.

        Parameters
        ----------
        result : str
            One of ``'won'``, ``'lost'``, or ``'expired'``.
        your_score : int
            Local player's final score (0 for expired).
        their_score : int
            Opponent's final score (0 for expired).
        """
        try:
            if result == "won":
                msg = f"🏆 DUEL WON!\nYou: {your_score:,} vs Opponent: {their_score:,}"
                color = "#00CC44"
            elif result == "lost":
                msg = f"💀 DUEL LOST.\nYou: {your_score:,} vs Opponent: {their_score:,}"
                color = "#CC2200"
            else:
                msg = "⏰ Duel expired \u2014 no response received."
                color = "#888888"
            self._get_mini_overlay().show_info(msg, seconds=8, color_hex=color)
        except Exception:
            pass

    # ── Helper: mini overlay accessor ────────────────────────────────────────

    def _get_mini_overlay(self):
        """Return the shared :class:`~ui_overlay.MiniInfoOverlay` instance.

        Creates it lazily on first access so that the import is deferred and
        circular-import issues are avoided.
        """
        if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
            from ui_overlay import MiniInfoOverlay  # deferred import
            self._mini_overlay = MiniInfoOverlay(self)
        return self._mini_overlay

    # ── Polling: invitation poll ───────────────────────────────────────────────

    def _poll_duel_invitations(self) -> None:
        """Poll the cloud for new incoming duel invitations in a background thread.

        Runs DuelEngine.receive_invitations() off the GUI thread so the UI
        stays responsive.  For each newly discovered invitation, triggers
        _on_duel_invitation_received() via QMetaObject.invokeMethod() on the
        GUI thread and refreshes the Active Duels table.  This method is
        called periodically by self._duel_poll_timer every 30 seconds when
        Cloud Sync is enabled.
        """
        import threading
        def _poll():
            new_duels = self._duel_engine.receive_invitations()
            if new_duels:
                from PyQt6.QtCore import QMetaObject, Q_ARG, Qt
                for duel in new_duels:
                    QMetaObject.invokeMethod(
                        self, "_on_duel_invitation_received",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, duel.challenger_name or duel.challenger),
                        Q_ARG(str, duel.table_name or duel.table_rom),
                        Q_ARG(str, duel.duel_id),
                    )
                QMetaObject.invokeMethod(
                    self, "_refresh_active_duels",
                    Qt.ConnectionType.QueuedConnection,
                )
        threading.Thread(target=_poll, daemon=True).start()

    # ── Polling: expiry check ──────────────────────────────────────────────────

    def _check_duel_expiry(self) -> None:
        """Check for expired duels via the engine and refresh both tables.

        Delegates to DuelEngine.check_expiry() which moves any overdue
        PENDING duels to history with DuelStatus.EXPIRED.  If any duels
        were expired, both the Active Duels and Duel History tables are
        refreshed and a brief expiry overlay is shown per expired duel.
        Called every 60 seconds by self._duel_expiry_timer.
        """
        expired = self._duel_engine.check_expiry()
        if expired:
            self._refresh_active_duels()
            self._refresh_duel_history()
            for duel in expired:
                try:
                    self._get_mini_overlay().show_info(
                        "⏰ Duel expired \u2014 no response received.",
                        seconds=6,
                        color_hex="#888888",
                    )
                except Exception:
                    pass

    # ── Refresh: active duels table ────────────────────────────────────────────

    @pyqtSlot()
    def _refresh_active_duels(self) -> None:
        """Reload the Active Duels table from the engine."""
        duels = self._duel_engine.get_active_duels()
        tbl = self._tbl_active_duels
        tbl.setRowCount(0)
        my_id = self.cfg.OVERLAY.get("player_id", "").strip()
        now = time.time()
        for duel in duels:
            row = tbl.rowCount()
            tbl.insertRow(row)

            # Opponent name column.
            is_challenger = (duel.challenger == my_id)
            opp_name = duel.opponent_name or duel.opponent if is_challenger else duel.challenger_name or duel.challenger
            tbl.setItem(row, 0, QTableWidgetItem(opp_name))

            # Table name column.
            tbl.setItem(row, 1, QTableWidgetItem(duel.table_name or duel.table_rom))

            # Status with colored indicator.
            status_map = {
                DuelStatus.PENDING:  "🟡 Pending",
                DuelStatus.ACCEPTED: "🟢 Accepted",
                DuelStatus.ACTIVE:   "🔵 In Progress",
            }
            status_text = status_map.get(duel.status, duel.status.capitalize())
            tbl.setItem(row, 2, QTableWidgetItem(status_text))

            # Time remaining column.
            if duel.status == DuelStatus.PENDING and duel.expires_at > 0:
                remaining = max(0, duel.expires_at - now)
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                tbl.setItem(row, 3, QTableWidgetItem(f"{mins}m {secs:02d}s"))
            else:
                tbl.setItem(row, 3, QTableWidgetItem("—"))

            # Actions column placeholder.
            tbl.setItem(row, 4, QTableWidgetItem(""))

    # ── Refresh: history table ─────────────────────────────────────────────────

    def _refresh_duel_history(self) -> None:
        """Reload the Duel History table from the engine.

        Fetches the completed-duel list (newest first) from DuelEngine and
        repopulates self._tbl_duel_history.  Each row shows opponent name,
        table name, result with color coding (green for wins, red for losses,
        gray for expired/declined), local player score, opponent score, and
        the completion date formatted as YYYY-MM-DD HH:MM.
        """
        history = self._duel_engine.get_duel_history()
        tbl = self._tbl_duel_history
        tbl.setRowCount(0)
        my_id = self.cfg.OVERLAY.get("player_id", "").strip()
        for duel in history:
            row = tbl.rowCount()
            tbl.insertRow(row)

            # Opponent name.
            is_challenger = (duel.challenger == my_id)
            opp_name = duel.opponent_name or duel.opponent if is_challenger else duel.challenger_name or duel.challenger
            tbl.setItem(row, 0, QTableWidgetItem(opp_name))

            # Table name.
            tbl.setItem(row, 1, QTableWidgetItem(duel.table_name or duel.table_rom))

            # Result with icon and color.
            result_map = {
                DuelStatus.WON:      ("🏆 Won",     "#00AA00"),
                DuelStatus.LOST:     ("💀 Lost",    "#AA0000"),
                DuelStatus.EXPIRED:  ("⏰ Expired", "#666666"),
                DuelStatus.DECLINED: ("❌ Declined","#666666"),
            }
            result_text, result_color = result_map.get(duel.status, (duel.status.capitalize(), "#AAAAAA"))
            result_item = QTableWidgetItem(result_text)
            result_item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(result_color))
            tbl.setItem(row, 2, result_item)

            # Your score.
            my_score = duel.challenger_score if is_challenger else duel.opponent_score
            tbl.setItem(row, 3, QTableWidgetItem(f"{my_score:,}"))

            # Their score.
            their_score = duel.opponent_score if is_challenger else duel.challenger_score
            tbl.setItem(row, 4, QTableWidgetItem(f"{their_score:,}"))

            # Date.
            if duel.completed_at:
                dt = datetime.fromtimestamp(duel.completed_at).strftime("%Y-%m-%d %H:%M")
            else:
                dt = "—"
            tbl.setItem(row, 5, QTableWidgetItem(dt))
