"""Score-Duels-tab mixin: Score Duels tab, alert bar, active duels table,
start new duel, history table, and all duel event handlers."""
from __future__ import annotations

import os
import random
import threading
import time
from datetime import datetime
from html import escape as _html_escape

from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QCompleter, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, QStringListModel, pyqtSlot

from config import p_aweditor
from duel_engine import Duel, DuelEngine, DuelStatus
from watcher_core import _strip_version_from_name

# Delay (ms) before the first fast opponent-score re-check after our own score is submitted.
_DUEL_FAST_RECHECK_DELAY_MS = 12_000


# ---------------------------------------------------------------------------
# Floating duel invitation overlay (shown when GUI is minimized / in systray)
# ---------------------------------------------------------------------------

class DuelInviteOverlay(QWidget):
    """Floating always-on-top duel invitation overlay.

    Appears when the main GUI is minimized or hidden to the system tray.
    Shows the challenger name and table, and provides Accept/Decline buttons.
    Auto-hides (without declining) after 30 seconds; the invitation stays in
    the Duels tab inbox for the user to act on later.

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
        Called with ``(duel_id)`` when the user declines.
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
            f"You have been challenged by <b>{_html_escape(opponent)}</b><br>"
            f"Table: <b>{_html_escape(table_name)}</b><br>"
            f"<small><i>Check the Duels tab to accept or decline.</i></small>"
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

        # Focus tracking: 0 = Accept focused, 1 = Decline focused
        self._focused = 0

        btn_row.addWidget(self._btn_accept)
        btn_row.addWidget(self._btn_decline)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        # ── position on primary screen (top-right corner) ─────────────────
        self._place_on_screen()

        # ── auto-hide timer (30 seconds – does NOT decline) ───────────────
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self._auto_hide)
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

    def _auto_hide(self) -> None:
        """Auto-hide the overlay after 30 seconds without declining."""
        if not self._closed:
            self.hide()

    def _on_accept_clicked(self) -> None:
        if self._closed:
            return
        # Check VPX running — decline if so.
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
        self._closed = True
        self._timer.stop()
        try:
            self._on_decline(self._duel_id)
        except Exception:
            pass
        self.close()

    # ── hotkey-driven focus ───────────────────────────────────────────────

    @staticmethod
    def _focused_btn_style(bg: str, hover_bg: str, focused: bool) -> str:
        """Return a QPushButton stylesheet with or without focus border."""
        border = "border:2px solid #FFFF00;" if focused else "border:none;"
        return (
            f"QPushButton {{ background-color:{bg}; color:#FFFFFF; font-weight:bold;"
            f" {border} border-radius:5px; padding:7px 18px; font-size:9pt; }}"
            f"QPushButton:hover {{ background-color:{hover_bg}; }}"
        )

    def _apply_focus_styles(self) -> None:
        """Visually highlight the currently focused button."""
        accept_focused = self._focused == 0
        self._btn_accept.setStyleSheet(
            self._focused_btn_style("#006400", "#008000", accept_focused)
        )
        self._btn_decline.setStyleSheet(
            self._focused_btn_style("#8B0000", "#AA0000", not accept_focused)
        )

    def is_accept_focused(self) -> bool:
        """Return ``True`` when the Accept button is currently focused."""
        return self._focused == 0

    def focus_accept(self) -> None:
        """Switch keyboard focus to the Accept button."""
        self._focused = 0
        self._apply_focus_styles()

    def focus_decline(self) -> None:
        """Switch keyboard focus to the Decline button."""
        self._focused = 1
        self._apply_focus_styles()

    def confirm_focused(self) -> None:
        """Click whichever button is currently focused."""
        if self._focused == 0:
            self._on_accept_clicked()
        else:
            self._on_decline_clicked()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.confirm_focused()
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

        # ── a) Incoming Invitations Inbox ────────────────────────────────────
        grp_inbox = QGroupBox("📬 Incoming Invitations")
        lay_inbox = QVBoxLayout(grp_inbox)

        self._tbl_duel_inbox = QTableWidget(0, 5)
        self._tbl_duel_inbox.setHorizontalHeaderLabels(
            ["Challenger", "Table", "Received", "Expires", "Actions"]
        )
        self._tbl_duel_inbox.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._tbl_duel_inbox.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tbl_duel_inbox.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_duel_inbox.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_duel_inbox.setAlternatingRowColors(True)
        self._tbl_duel_inbox.setStyleSheet(
            "QTableWidget { background:#111; color:#DDD; gridline-color:#333; }"
            "QTableWidget::item:alternate { background:#1a1a1a; }"
            "QTableWidget::item:selected { background:#1a3a1a; }"
            "QHeaderView::section { background:#222; color:#FF7F00; font-weight:bold;"
            " border:1px solid #333; padding:4px; }"
        )
        self._tbl_duel_inbox.setMinimumHeight(80)
        lay_inbox.addWidget(self._tbl_duel_inbox)
        layout.addWidget(grp_inbox)

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

        self._duel_table_completer_model = QStringListModel([], self)
        self._duel_table_completer = QCompleter(self._duel_table_completer_model, self)
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
        layout.addWidget(grp_history)

        # ── e) Bottom ────────────────────────────────────────────────────────
        layout.addStretch(1)
        self._add_tab_duels_bottom_buttons(layout)
        self.main_tabs.addTab(tab, "⚔️ Score Duels")
        self._duels_tab_index = self.main_tabs.count() - 1

        # ── Populate table dropdown from maps cache ──────────────────────────
        self._populate_duel_table_combo()

        # ── Refresh table dropdown when this tab becomes active ──────────────
        self.main_tabs.currentChanged.connect(self._on_duels_tab_activated)

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

        # Write-amplification cooldown dict: duel_id → last_recheck_timestamp
        self._duel_recheck_cooldown: dict = {}

        # Initial populate.
        self._refresh_invitation_inbox()
        self._refresh_active_duels()
        self._refresh_duel_history()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _add_tab_duels_bottom_buttons(self, layout) -> None:
        """Add the Duel Rules and Help buttons anchored to the bottom-right."""
        row = QHBoxLayout()
        row.addStretch(1)

        btn_rules = QPushButton("📜 Duel Rules")
        btn_rules.setToolTip("Show the Score Duel rules")
        btn_rules.setStyleSheet(
            "QPushButton { background-color: #1a1a1a; color: #FF7F00; border: 1px solid #FF7F00;"
            " border-radius: 14px; font-size: 11pt; font-weight: bold; padding: 0 10px; }"
            "QPushButton:hover { background-color: #FF7F00; color: #000000; }"
        )
        btn_rules.setFixedHeight(28)
        btn_rules.clicked.connect(self._show_duel_rules)
        row.addWidget(btn_rules)

        btn_help = QPushButton("❓")
        btn_help.setFixedSize(28, 28)
        btn_help.setToolTip("Show help for this tab")
        btn_help.setStyleSheet(
            "QPushButton { background-color: #1a1a1a; color: #FF7F00; border: 1px solid #FF7F00; "
            "border-radius: 14px; font-size: 11pt; font-weight: bold; padding: 0; }"
            "QPushButton:hover { background-color: #FF7F00; color: #000000; }"
        )
        btn_help.clicked.connect(lambda: self._show_tab_help("duels"))
        row.addWidget(btn_help)
        layout.addLayout(row)

    def _show_duel_rules(self) -> None:
        """Show the Score Duel rules dialog."""
        from PyQt6.QtWidgets import QMessageBox
        rules = (
            "📜 Score Duel Rules\n\n"
            "⚔️ OVERVIEW\n"
            "Score Duels are asynchronous high-score battles. Challenge any\n"
            "cloud-connected player to compete on the same table.\n\n"
            "👥 OPPONENTS\n"
            "• Cloud Sync must be enabled for both players\n"
            "• Only players with a valid Player Name appear\n"
            "• Players using the default name \"Player\" are hidden\n\n"
            "🎰 TABLE SELECTION\n"
            "• Tables must have an NVRAM map AND be locally installed\n"
            "• Only approved custom tables (CAT Registry) are included\n\n"
            "🔗 MATCHING\n"
            "• Both players must have the same ROM name for the table\n"
            "• If the opponent does not have the table installed, the duel is automatically declined\n\n"
            "⏳ INVITATIONS\n"
            "• You have 7 days to accept or decline\n"
            "• Invitations are visible in the 📬 Incoming Invitations table\n"
            "• VPX must NOT be running when accepting\n"
            "• Unanswered invitations expire automatically\n\n"
            "🏆 SCORING\n"
            "• Both players play the table independently\n"
            "• Scores are submitted and compared via the cloud\n"
            "• Highest score wins the duel"
        )
        box = QMessageBox(self)
        box.setWindowTitle("📜 Score Duel Rules")
        box.setText(rules)
        box.setIcon(QMessageBox.Icon.Information)
        box.exec()

    def _populate_duel_table_combo(self) -> None:
        """Populate the table selection dropdown from the available maps cache.

        Filters the cache to entries that have an NVRAM map AND are locally
        installed, sorts them alphabetically by title, and adds them to the
        combo box.  Falls back to vps_id_mapping.json (ROMs the user has ever
        assigned a VPS-ID) when _all_maps_cache has no matching entries, e.g.
        on first launch before the map list has been loaded.

        Preserves the current selection if the same ROM is still available
        after repopulating.
        """
        # Preserve current selection before clearing.
        prev_rom = self._cmb_duel_table.currentData() or ""

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

        # Add CAT tables from AWEditor (.custom.json files) — only approved entries.
        try:
            from cat_registry import lookup_by_table_key
            aw_dir = p_aweditor(self.cfg)
            if os.path.isdir(aw_dir):
                existing_data = [self._cmb_duel_table.itemData(i) for i in range(self._cmb_duel_table.count())]
                for fname in sorted(os.listdir(aw_dir)):
                    if fname.endswith(".custom.json"):
                        table_key = fname[:-len(".custom.json")]
                        if lookup_by_table_key(table_key) is None:
                            continue  # Not approved → skip
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

        self._duel_table_completer_model.setStringList(suggestions)

        # Restore the previous selection if it is still available.
        if prev_rom:
            idx = self._cmb_duel_table.findData(prev_rom)
            if idx >= 0:
                self._cmb_duel_table.setCurrentIndex(idx)

        # Connect completer activation to select correct combo entry.
        try:
            self._duel_table_completer.activated.disconnect()
        except Exception:
            pass
        self._duel_table_completer.activated.connect(self._on_duel_table_completer_activated)

    def _on_duels_tab_activated(self, index: int) -> None:
        """Refresh the table dropdown whenever the Score Duels tab becomes active."""
        if index == getattr(self, "_duels_tab_index", -1):
            if hasattr(self, "_cmb_duel_table"):
                self._populate_duel_table_combo()

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

        duel_or_error = self._duel_engine.send_invitation(opponent_id, table_rom, table_name,
                                                           opponent_name=opponent_name)
        if isinstance(duel_or_error, Duel):
            self._lbl_duel_status.setText(
                f"✅ Invitation sent to '{opponent_name or opponent_id}' for '{table_name}'!"
            )
            self._lbl_duel_status.setStyleSheet("color:#00E500; font-style:italic;")
            self._refresh_active_duels()
        elif duel_or_error == "duplicate":
            self._lbl_duel_status.setText(
                "⚠️ A pending duel for this opponent and table already exists."
            )
            self._lbl_duel_status.setStyleSheet("color:#FFAA00; font-style:italic;")
        elif duel_or_error == "no_player_id":
            self._lbl_duel_status.setText(
                "⚠️ Player ID not configured. Please set your Player ID in Settings."
            )
            self._lbl_duel_status.setStyleSheet("color:#FFAA00; font-style:italic;")
        elif duel_or_error == "no_opponent":
            self._lbl_duel_status.setText("⚠️ Opponent ID is required.")
            self._lbl_duel_status.setStyleSheet("color:#FFAA00; font-style:italic;")
        else:
            self._lbl_duel_status.setText("❌ Failed to send invitation. Check Cloud Sync.")
            self._lbl_duel_status.setStyleSheet("color:#CC4444; font-style:italic;")

    # ── Slot: accept / decline invitation ────────────────────────────────────

    def _update_duels_tab_badge(self, count: int) -> None:
        """Update the Duels tab text to show a badge counter when ``count > 0``."""
        base = "⚔️ Score Duels"
        text = f"{base} ({count})" if count > 0 else base
        try:
            for i in range(self.main_tabs.count()):
                tab_text = self.main_tabs.tabText(i)
                if tab_text == base or (tab_text.startswith(base + " (") and tab_text.endswith(")")):
                    self.main_tabs.setTabText(i, text)
                    break
        except Exception:
            pass

    def _apply_duel_alert_focus_styles(self) -> None:
        """No-op: alert bar removed. Kept for backwards compatibility with hotkey handlers."""
        pass

    def _on_inbox_accept(self, duel_id: str) -> None:
        """Accept an incoming duel invitation from the inbox table.

        Checks VPX running state and table availability before accepting.
        """
        if not duel_id:
            return

        # Check VPX running — cannot accept while VPX is active.
        try:
            w = getattr(self, "watcher", None)
            if w and (w.game_active or w._vp_player_visible()):
                self._duel_engine.decline_duel(duel_id)
                self._refresh_invitation_inbox()
                self._refresh_active_duels()
                self._duel_notify(
                    "Cannot accept duel while VPX is running.",
                    "#CC5500",
                    seconds=5,
                )
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
                self._refresh_invitation_inbox()
                self._refresh_active_duels()
                self._duel_notify(
                    f"❌ Duel cancelled – Table '{tname}' is not available.",
                    "#CC2200",
                    seconds=6,
                )
                return
        except Exception:
            pass

        self._duel_engine.accept_duel(duel_id)
        self._refresh_invitation_inbox()
        self._refresh_active_duels()
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.on_duel_accepted()
            if getattr(self, "_trophie_overlay", None):
                self._trophie_overlay.on_duel_accepted()
        except Exception:
            pass

    def _on_inbox_decline(self, duel_id: str) -> None:
        """Decline an incoming duel invitation from the inbox table."""
        if not duel_id:
            return
        self._duel_engine.decline_duel(duel_id)
        self._refresh_invitation_inbox()
        self._refresh_active_duels()
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.on_duel_declined()
            if getattr(self, "_trophie_overlay", None):
                self._trophie_overlay.on_duel_declined()
        except Exception:
            pass

    def _on_duel_accept(self) -> None:
        """Legacy method: kept for backwards compatibility. Delegates to _on_inbox_accept."""
        pass

    def _on_duel_decline(self) -> None:
        """Legacy method: kept for backwards compatibility. No-op since alert bar is removed."""
        pass

    def _on_duel_cancel(self, duel_id: str) -> None:
        """Cancel a pending duel invitation that was sent by this player."""
        self._duel_engine.cancel_duel(duel_id)
        self._refresh_active_duels()
        self._refresh_duel_history()

    # ── Slot: incoming invitation ─────────────────────────────────────────────

    @pyqtSlot(str, str, str)
    def _on_duel_invitation_received(self, opponent: str, table_name: str, duel_id: str) -> None:
        """Handle an incoming duel invitation.

        Updates the inbox table to show the new invitation.  When the window is
        minimized or hidden (e.g. to the system tray) a floating
        :class:`DuelInviteOverlay` is shown as a notification; it auto-hides
        after 30 seconds without declining the invitation.

        Parameters
        ----------
        opponent : str
            Display name of the challenger.
        table_name : str
            Name of the table being challenged on.
        duel_id : str
            Unique ID of the incoming duel.
        """
        # Always refresh the inbox table so the new invitation is visible.
        self._refresh_invitation_inbox()

        gui_hidden = not self.isVisible() or self.isMinimized()

        if gui_hidden:
            # Close any previous invite overlay before showing a new one.
            try:
                prev = getattr(self, "_duel_invite_overlay", None)
                if prev is not None and not getattr(prev, "_closed", True):
                    prev.hide()
            except Exception:
                pass

            def _accept_cb(did: str) -> None:
                self._on_inbox_accept(did)

            def _decline_cb(did: str) -> None:
                self._on_inbox_decline(did)

            self._duel_invite_overlay = DuelInviteOverlay(
                self, opponent, table_name, duel_id, _accept_cb, _decline_cb
            )
            # Clear the reference when the overlay is destroyed (WA_DeleteOnClose)
            # to prevent RuntimeError from accessing a deleted C++ object.
            self._duel_invite_overlay.destroyed.connect(
                lambda: setattr(self, "_duel_invite_overlay", None)
            )
            self._duel_invite_overlay.show()
        else:
            # GUI is visible — switch to the Score Duels tab so the user notices.
            for i in range(self.main_tabs.count()):
                tab_text = self.main_tabs.tabText(i)
                if tab_text == "⚔️ Score Duels" or (tab_text.startswith("⚔️ Score Duels (") and tab_text.endswith(")")):
                    self.main_tabs.setCurrentIndex(i)
                    break

    def _on_duel_invitation_timeout(self) -> None:
        """Legacy no-op: countdown timer removed. Kept to avoid AttributeError."""
        pass

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
                msg = f"🏆 DUEL WON! You: {your_score:,} vs Opponent: {their_score:,}"
                color = "#00CC44"
            elif result == "lost":
                msg = f"💀 DUEL LOST. You: {your_score:,} vs Opponent: {their_score:,}"
                color = "#CC2200"
            else:
                msg = "⏰ Duel expired \u2014 no response received."
                color = "#888888"
            self._duel_notify(msg, color, seconds=8)
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

    def _duel_notify(self, msg: str, color_hex: str = "#888888", seconds: int = 6) -> None:
        """Show a duel notification — in-tab label if GUI visible, MiniOverlay if systray, nothing if VPX running."""
        try:
            w = getattr(self, "watcher", None)
            if w and (w.game_active or w._vp_player_visible()):
                return  # VPX is running → no notification
        except Exception:
            pass

        gui_visible = self.isVisible() and not self.isMinimized()
        if gui_visible:
            self._lbl_duel_status.setText(msg)
            self._lbl_duel_status.setStyleSheet(f"color:{color_hex}; font-style:italic;")
        else:
            try:
                self._get_mini_overlay().show_info(msg, seconds=seconds, color_hex=color_hex)
            except Exception:
                pass

    # ── Polling: invitation poll ───────────────────────────────────────────────

    def _poll_duel_invitations(self) -> None:
        """Poll the cloud for new incoming duel invitations in a background thread.

        Runs DuelEngine.receive_invitations() off the GUI thread so the UI
        stays responsive.  For each newly discovered invitation, triggers
        _on_duel_invitation_received() via QMetaObject.invokeMethod() on the
        GUI thread and refreshes the Active Duels table.  Also calls
        sync_active_duel_states() to detect when the challenger's pending duel
        has been accepted or declined by the opponent.  This method is
        called periodically by self._duel_poll_timer every 30 seconds when
        Cloud Sync is enabled.
        """
        import threading
        def _poll():
            new_duels = self._duel_engine.receive_invitations()
            changed_duels = self._duel_engine.sync_active_duel_states()
            from PyQt6.QtCore import QMetaObject, Q_ARG, Qt
            if new_duels:
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
            if new_duels or changed_duels:
                QMetaObject.invokeMethod(
                    self, "_refresh_invitation_inbox",
                    Qt.ConnectionType.QueuedConnection,
                )
            if changed_duels:
                from duel_engine import DuelStatus
                QMetaObject.invokeMethod(
                    self, "_refresh_active_duels",
                    Qt.ConnectionType.QueuedConnection,
                )
                has_history_change = any(
                    d.status in (DuelStatus.DECLINED, DuelStatus.EXPIRED, DuelStatus.CANCELLED,
                                 DuelStatus.WON, DuelStatus.LOST)
                    for d in changed_duels
                )
                if has_history_change:
                    QMetaObject.invokeMethod(
                        self, "_refresh_duel_history",
                        Qt.ConnectionType.QueuedConnection,
                    )
                for duel in changed_duels:
                    if duel.status == DuelStatus.ACCEPTED:
                        msg = f"✅ '{duel.opponent_name or 'Opponent'}' accepted your duel on {duel.table_name or duel.table_rom}!"
                        color = "#00E500"
                    elif duel.status == DuelStatus.DECLINED:
                        msg = f"❌ '{duel.opponent_name or 'Opponent'}' declined your duel on {duel.table_name or duel.table_rom}."
                        color = "#CC0000"
                    elif duel.status == DuelStatus.EXPIRED:
                        msg = f"⏰ Your duel invitation on {duel.table_name or duel.table_rom} expired (not accepted)."
                        color = "#888888"
                    elif duel.status == DuelStatus.CANCELLED:
                        # Reset duel-active flag on watcher regardless of game state so
                        # achievements and challenges are unblocked after a cancel.
                        try:
                            w = getattr(self, "watcher", None)
                            if w is not None and duel.table_rom.lower().strip() == (w.current_rom or "").lower().strip():
                                w.duel_active_for_current_table = False
                        except Exception:
                            pass
                        msg = f"🚫 Your duel on {duel.table_name or duel.table_rom} was cancelled."
                        color = "#888888"
                    else:
                        continue
                    QMetaObject.invokeMethod(
                        self, "_duel_notify",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, msg),
                        Q_ARG(str, color),
                        Q_ARG(int, 8),
                    )
        threading.Thread(target=_poll, daemon=True).start()

    # ── Polling: expiry check ──────────────────────────────────────────────────

    def _check_duel_expiry(self) -> None:
        """Check for expired duels via the engine and refresh both tables.

        Calls sync_active_duel_states() FIRST so any cloud state changes (e.g.
        PENDING→ACCEPTED) are applied before the expiry check runs, preventing
        the race condition where check_expiry() would expire a duel that was
        just accepted in the cloud.

        Delegates to DuelEngine.check_expiry() which moves any overdue
        PENDING/ACCEPTED/ACTIVE duels to history with DuelStatus.EXPIRED.
        If any duels were expired, both the Active Duels and Duel History
        tables are refreshed, bridge.duel_expired is emitted for mascot
        reactions, and a brief expiry overlay is shown per expired duel.
        Also re-checks ACTIVE duels for opponent score availability.
        Called every 60 seconds by self._duel_expiry_timer.
        """
        # Sync cloud states BEFORE expiry to avoid race conditions.
        try:
            self._duel_engine.sync_active_duel_states()
        except Exception:
            pass

        # Re-check ACTIVE duels for opponent score (mitigates race condition).
        try:
            self._recheck_active_duel_scores()
        except Exception:
            pass

        expired = self._duel_engine.check_expiry()
        if expired:
            # Reset duel-active flag on watcher if any expired duel matches the
            # current session ROM so achievements are unblocked after expiry.
            try:
                w = getattr(self, "watcher", None)
                if w is not None:
                    cur_rom = (w.current_rom or "").lower().strip()
                    if cur_rom and any(d.table_rom.lower().strip() == cur_rom for d in expired):
                        w.duel_active_for_current_table = False
            except Exception:
                pass
            self._refresh_invitation_inbox()
            self._refresh_active_duels()
            self._refresh_duel_history()
            for duel in expired:
                # Emit bridge signal so mascot dispatchers fire.
                try:
                    self.bridge.duel_expired.emit(duel.duel_id)
                except Exception:
                    pass
                self._duel_notify(
                    "⏰ Duel expired \u2014 no response received.",
                    "#888888",
                    seconds=6,
                )

    # ── Refresh: invitation inbox table ────────────────────────────────────────

    @pyqtSlot()
    def _refresh_invitation_inbox(self) -> None:
        """Reload the Incoming Invitations inbox table from the engine.

        Shows only PENDING duels where the local player is the opponent
        (i.e. incoming invitations they have not yet acted on).
        """
        if not hasattr(self, "_tbl_duel_inbox"):
            return
        duels = self._duel_engine.get_active_duels()
        my_id = self.cfg.OVERLAY.get("player_id", "").strip()
        now = time.time()
        tbl = self._tbl_duel_inbox
        tbl.setRowCount(0)
        for duel in duels:
            if duel.status != DuelStatus.PENDING:
                continue
            if duel.opponent != my_id:
                continue  # Only incoming invitations (we are the opponent)
            row = tbl.rowCount()
            tbl.insertRow(row)

            # Challenger column.
            tbl.setItem(row, 0, QTableWidgetItem(duel.challenger_name or duel.challenger))

            # Table column.
            tbl.setItem(row, 1, QTableWidgetItem(duel.table_name or duel.table_rom))

            # Received column (YYYY-MM-DD HH:MM).
            received = datetime.fromtimestamp(duel.created_at).strftime("%Y-%m-%d %H:%M") if duel.created_at else "—"
            tbl.setItem(row, 2, QTableWidgetItem(received))

            # Expires column (remaining time).
            if duel.expires_at > 0:
                remaining = max(0, duel.expires_at - now)
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                if days > 0:
                    expires_text = f"{days}d {hours}h"
                elif hours > 0:
                    mins = int((remaining % 3600) // 60)
                    expires_text = f"{hours}h {mins}m"
                else:
                    mins = int(remaining // 60)
                    expires_text = f"{mins}m"
            else:
                expires_text = "—"
            tbl.setItem(row, 3, QTableWidgetItem(expires_text))

            # Actions column: Accept and Decline buttons.
            actions_w = QWidget()
            actions_w.setStyleSheet("background: transparent;")
            actions_lay = QHBoxLayout(actions_w)
            actions_lay.setContentsMargins(2, 1, 2, 1)
            actions_lay.setSpacing(4)

            btn_accept = QPushButton("✅ Accept")
            btn_accept.setFixedHeight(22)
            btn_accept.setStyleSheet(
                "QPushButton { background:#003300; color:#00FF00; border:1px solid #00AA00;"
                " border-radius:4px; padding:0 6px; font-size:11px; }"
                "QPushButton:hover { background:#005500; }"
            )
            btn_accept.clicked.connect(
                lambda _checked=False, did=duel.duel_id: self._on_inbox_accept(did)
            )

            btn_decline = QPushButton("❌ Decline")
            btn_decline.setFixedHeight(22)
            btn_decline.setStyleSheet(
                "QPushButton { background:#2a0000; color:#FF4444; border:1px solid #FF4444;"
                " border-radius:4px; padding:0 6px; font-size:11px; }"
                "QPushButton:hover { background:#4a0000; }"
            )
            btn_decline.clicked.connect(
                lambda _checked=False, did=duel.duel_id: self._on_inbox_decline(did)
            )

            actions_lay.addWidget(btn_accept)
            actions_lay.addWidget(btn_decline)
            tbl.setCellWidget(row, 4, actions_w)

    # ── Refresh: active duels table ────────────────────────────────────────────

    @pyqtSlot()
    def _refresh_active_duels(self) -> None:
        """Reload the Active Duels table from the engine."""
        duels = self._duel_engine.get_active_duels()
        tbl = self._tbl_active_duels
        tbl.setRowCount(0)
        my_id = self.cfg.OVERLAY.get("player_id", "").strip()
        now = time.time()
        from duel_engine import ACTIVE_DUEL_TTL_SECONDS
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
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                if days > 0:
                    time_str = f"{days}d {hours}h"
                elif hours > 0:
                    mins = int((remaining % 3600) // 60)
                    time_str = f"{hours}h {mins}m"
                else:
                    mins = int(remaining // 60)
                    secs = int(remaining % 60)
                    time_str = f"{mins}m {secs:02d}s"
                tbl.setItem(row, 3, QTableWidgetItem(time_str))
            elif duel.status in (DuelStatus.ACCEPTED, DuelStatus.ACTIVE):
                ref_time = duel.accepted_at if duel.accepted_at > 0 else duel.created_at
                remaining = max(0, (ref_time + ACTIVE_DUEL_TTL_SECONDS) - now)
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                if days > 0:
                    time_str = f"{days}d {hours}h"
                elif hours > 0:
                    mins = int((remaining % 3600) // 60)
                    time_str = f"{hours}h {mins}m"
                else:
                    mins = int(remaining // 60)
                    time_str = f"{mins}m"
                tbl.setItem(row, 3, QTableWidgetItem(time_str))
            else:
                tbl.setItem(row, 3, QTableWidgetItem("—"))

            # Actions column: Cancel button for PENDING (challenger only) and ACCEPTED (either player).
            can_cancel = (
                (duel.status == DuelStatus.PENDING and is_challenger)
                or (duel.status == DuelStatus.ACCEPTED and (duel.challenger == my_id or duel.opponent == my_id))
            )
            if can_cancel:
                btn_cancel = QPushButton("❌ Cancel")
                btn_cancel.setFixedHeight(24)
                btn_cancel.setStyleSheet(
                    "QPushButton { background:#2a0000; color:#FF4444; border:1px solid #FF4444;"
                    " border-radius:4px; padding:0 6px; font-size:11px; }"
                    "QPushButton:hover { background:#4a0000; }"
                )
                btn_cancel.clicked.connect(
                    lambda _checked=False, did=duel.duel_id: self._on_duel_cancel(did)
                )
                tbl.setCellWidget(row, 4, btn_cancel)
            else:
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

            # Table name with optional ℹ️ info badge.
            table_display = duel.table_name or duel.table_rom
            try:
                from ui_vps import _load_vps_mapping, CloudProgressVpsInfoDialog
                vps_mapping = _load_vps_mapping(self.cfg)
                vps_id = vps_mapping.get(duel.table_rom, "")
            except Exception:
                vps_id = ""
            if vps_id:
                cell_w = QWidget()
                cell_w.setStyleSheet("background: transparent;")
                cell_lay = QHBoxLayout(cell_w)
                cell_lay.setContentsMargins(2, 0, 2, 0)
                cell_lay.setSpacing(4)
                lbl_table = QLabel(table_display)
                lbl_table.setStyleSheet("color:#DDD;")
                cell_lay.addWidget(lbl_table)
                btn_info = QPushButton("ℹ️")
                btn_info.setFixedSize(22, 22)
                btn_info.setFlat(True)
                btn_info.setToolTip(f"Table: {table_display}")
                btn_info.setStyleSheet(
                    "QPushButton { background: transparent; border: none;"
                    " font-size: 13px; padding: 0; }"
                    "QPushButton:hover { background: #1a2a2a; border-radius: 4px; }"
                )
                btn_info.clicked.connect(
                    lambda _checked=False, vps_id=vps_id, tname=table_display:
                        CloudProgressVpsInfoDialog(self.cfg, vps_id, table_name=tname, parent=self).exec()
                )
                cell_lay.addWidget(btn_info)
                cell_lay.addStretch(1)
                tbl.setCellWidget(row, 1, cell_w)
            else:
                tbl.setItem(row, 1, QTableWidgetItem(table_display))

            # Result with icon and color.
            result_map = {
                DuelStatus.WON:       ("🏆 Won",        "#00AA00"),
                DuelStatus.LOST:      ("💀 Lost",        "#AA0000"),
                DuelStatus.EXPIRED:   ("⏰ Expired",     "#666666"),
                DuelStatus.DECLINED:  ("❌ Declined",    "#666666"),
                DuelStatus.CANCELLED: ("🚫 Cancelled",   "#666666"),
            }
            result_text, result_color = result_map.get(duel.status, (duel.status.capitalize(), "#AAAAAA"))
            result_item = QTableWidgetItem(result_text)
            result_item.setForeground(QColor(result_color))
            tbl.setItem(row, 2, result_item)

            # Your score.
            my_score = duel.challenger_score if is_challenger else duel.opponent_score
            tbl.setItem(row, 3, QTableWidgetItem(f"{my_score:,}" if my_score >= 0 else "—"))

            # Their score.
            their_score = duel.opponent_score if is_challenger else duel.challenger_score
            tbl.setItem(row, 4, QTableWidgetItem(f"{their_score:,}" if their_score >= 0 else "—"))

            # Date.
            if duel.completed_at:
                dt = datetime.fromtimestamp(duel.completed_at).strftime("%Y-%m-%d %H:%M")
            else:
                dt = "—"
            tbl.setItem(row, 5, QTableWidgetItem(dt))

    # ── Session-started hook: detect active duel ──────────────────────────────

    @pyqtSlot(str, str)
    def _on_session_started_duels(self, rom: str, table_name: str) -> None:
        """Called when VPX starts a game session.

        Checks whether an ACCEPTED or ACTIVE duel exists for the current ROM.
        If so, sets ``watcher.duel_active_for_current_table = True`` to block
        achievements, challenges and the main overlay for this session, and
        shows a brief in-game notification via MiniInfoOverlay.
        """
        if not rom:
            return
        rom_lower = rom.lower().strip()
        try:
            active = self._duel_engine.get_active_duels()
        except Exception:
            return

        matching = [d for d in active
                    if d.table_rom.lower().strip() == rom_lower
                    and d.status in (DuelStatus.ACCEPTED, DuelStatus.ACTIVE)]
        if not matching:
            return

        # Flag the watcher so achievements/overlay are suppressed this session.
        try:
            w = getattr(self, "watcher", None)
            if w is not None:
                w.duel_active_for_current_table = True
        except Exception:
            pass

        # Show in-game notification directly via MiniInfoOverlay, bypassing
        # _duel_notify's VPX-running suppression — the point is to show it
        # exactly when the game starts.
        duel = matching[0]
        my_id = self.cfg.OVERLAY.get("player_id", "").strip()
        is_challenger = (duel.challenger == my_id)
        opponent_name = (duel.opponent_name if is_challenger else duel.challenger_name) or "Opponent"
        msg = f"⚔️ Duel aktiv gegen {opponent_name}!"
        try:
            self._get_mini_overlay().show_info(msg, seconds=6, color_hex="#FF7F00")
        except Exception:
            pass

    # ── Session-ended hook: submit duel scores ─────────────────────────────────

    def _on_session_ended_duels(self, rom: str) -> None:
        """Called when a game session ends. Submits scores for any ACCEPTED
        duels on the finished ROM.

        Looks up the latest high score from the watcher and calls
        ``DuelEngine.submit_result()`` for each matching duel.
        """
        if not rom:
            return
        rom_lower = rom.lower().strip()
        try:
            active = self._duel_engine.get_active_duels()
        except Exception:
            return

        matching = [d for d in active
                    if d.table_rom.lower().strip() == rom_lower
                    and d.status in (DuelStatus.ACCEPTED, DuelStatus.ACTIVE)]
        if not matching:
            return

        # Get the latest score from the watcher.
        score = 0
        try:
            w = getattr(self, "watcher", None)
            if w:
                score = int(getattr(w, "last_session_score", 0) or 0)
                if score <= 0:
                    # Fallback: try current high score from NVRAM state.
                    score = int(getattr(w, "current_highscore", 0) or 0)
        except Exception:
            pass

        for duel in matching:
            try:
                if score <= 0:
                    from watcher_core import log
                    log(self.cfg, f"[DUEL] Skipping score submission for {rom} — score is {score}", "WARN")
                    continue
                result = self._duel_engine.submit_result(duel.duel_id, score)
                if result:
                    my_id = self.cfg.OVERLAY.get("player_id", "").strip()
                    is_challenger = (duel.challenger == my_id)
                    my_score = duel.challenger_score if is_challenger else duel.opponent_score
                    their_score = duel.opponent_score if is_challenger else duel.challenger_score
                    try:
                        self.bridge.duel_result.emit(duel.duel_id, result, my_score, their_score)
                    except Exception:
                        pass
                    self._refresh_active_duels()
                    self._refresh_duel_history()
            except Exception:
                pass

        # If any duel is now ACTIVE (score submitted, waiting for opponent),
        # schedule a fast re-check so the result overlay appears promptly.
        try:
            active_after = self._duel_engine.get_active_duels()
            pending = [d for d in active_after
                       if d.table_rom.lower().strip() == rom_lower
                       and d.status == DuelStatus.ACTIVE]
            if pending:
                # Clear per-duel cooldown so the fast timer can proceed immediately.
                for d in pending:
                    self._duel_recheck_cooldown.pop(d.duel_id, None)
                QTimer.singleShot(_DUEL_FAST_RECHECK_DELAY_MS, self._recheck_active_duel_scores)
        except Exception:
            pass

    # ── Re-check ACTIVE duel scores (race condition mitigation) ────────────────

    def _recheck_active_duel_scores(self) -> None:
        """Re-check ACTIVE duels where we are waiting for the opponent's score.

        Called periodically by _check_duel_expiry to mitigate the race
        condition where both players submit at similar times and one does
        not see the other's score on the first attempt.

        Uses a per-duel cooldown of 5 minutes to avoid write amplification
        (excessive cloud reads/writes every 60 seconds).
        """
        from duel_engine import SCORE_NOT_SUBMITTED
        try:
            active = self._duel_engine.get_active_duels()
        except Exception:
            return

        now = time.time()
        if not hasattr(self, "_duel_recheck_cooldown"):
            self._duel_recheck_cooldown = {}

        for duel in active:
            if duel.status != DuelStatus.ACTIVE:
                continue
            my_id = self.cfg.OVERLAY.get("player_id", "").strip()
            is_challenger = (duel.challenger == my_id)
            my_score = duel.challenger_score if is_challenger else duel.opponent_score
            if my_score == SCORE_NOT_SUBMITTED:
                continue  # We haven't submitted yet; nothing to re-check.
            # Cooldown: only re-check every 5 minutes per duel.
            last = self._duel_recheck_cooldown.get(duel.duel_id, 0)
            if now - last < 300:  # 5 minutes
                continue
            self._duel_recheck_cooldown[duel.duel_id] = now
            result = self._duel_engine.submit_result(duel.duel_id, my_score)
            if result:
                opp_score = duel.opponent_score if is_challenger else duel.challenger_score
                try:
                    self.bridge.duel_result.emit(duel.duel_id, result, my_score, opp_score)
                except Exception:
                    pass
                self._refresh_active_duels()
                self._refresh_duel_history()
