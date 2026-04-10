"""Tournament sub-tab widget for the Score Duels tab.

Provides:
- Queue section (join / leave, player list, progress bar)
- Bracket visualization for the player's active tournament
- Tournament history table
- Tournament Rules dialog
- Notification overlay integration (deferred when VPX is running)
- Real-time Tournament Chat (backed by Firebase Realtime Database)
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from html import escape as _esc

from PyQt6.QtCore import QMetaObject, Qt, Q_ARG, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QVBoxLayout, QWidget,
)

from core.tournament_engine import TournamentEngine, TOURNAMENT_SIZE, _clean_table_name
from .chat import ChatWidget

_TABLE_STYLE = (
    "QTableWidget { background:#111; color:#DDD; gridline-color:#333; }"
    "QTableWidget::item:alternate { background:#1a1a1a; }"
    "QTableWidget::item:selected { background:#1a3a3a; }"
    "QHeaderView::section { background:#222; color:#FF7F00; font-weight:bold;"
    " border:1px solid #333; padding:4px; }"
)

_BTN_BLUE = (
    "QPushButton { background-color:#005c99; color:#FFFFFF; font-weight:bold;"
    " border:none; border-radius:5px; padding:0 14px; }"
    "QPushButton:hover { background-color:#0070bb; }"
    "QPushButton:disabled { background-color:#333; color:#666; }"
)
_BTN_ORANGE = (
    "QPushButton { background-color:#7a3c00; color:#FF7F00; font-weight:bold;"
    " border:1px solid #FF7F00; border-radius:5px; padding:0 14px; }"
    "QPushButton:hover { background-color:#FF7F00; color:#000; }"
    "QPushButton:disabled { background-color:#333; color:#666; }"
)
_BTN_RED = (
    "QPushButton { background-color:#2a0000; color:#FF4444; font-weight:bold;"
    " border:1px solid #FF4444; border-radius:5px; padding:0 14px; }"
    "QPushButton:hover { background-color:#4a0000; }"
    "QPushButton:disabled { background-color:#333; color:#666; }"
)

_POLL_INTERVAL_IDLE_MS   = 30_000  # 30 seconds – queue / no tournament
_POLL_INTERVAL_ACTIVE_MS = 10_000  # 10 seconds – active tournament (SF or final in progress)
_COMPLETED_BRACKET_DISPLAY_MS = 300_000  # 5 minutes to keep completed bracket visible


class TournamentWidget(QWidget):
    """Sub-tab widget for the Tournament mode.

    Parameters
    ----------
    main_window :
        The application main window (provides ``watcher``, ``cfg`` and the
        overlay helpers ``_get_duel_overlay`` / ``_tournament_notify_state``).
    cfg : AppConfig
        Application configuration instance.
    duel_engine : DuelEngine
        The shared DuelEngine used for 1v1 match management.
    parent : QWidget, optional
    """

    def __init__(self, main_window, cfg, duel_engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._main_window  = main_window
        self._cfg          = cfg
        self._engine       = TournamentEngine(cfg, duel_engine)
        self._fetching     = False
        self._in_queue     = False
        self._active_tournament: dict | None = None
        # Notifications queued for display (not yet shown because VPX was running).
        self._deferred_notifications: list = []
        self._completed_bracket_timer_started: bool = False
        self._queue_expires_at: float = 0.0
        self._build_ui()
        # Periodic poll timer.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_IDLE_MS)
        self._poll_timer.timeout.connect(self._on_poll_timer)
        if getattr(cfg, "CLOUD_ENABLED", False):
            self._poll_timer.start()
        # 1-second countdown timer for queue expiry display.
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._update_countdown)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # Left column holds all existing tournament widgets
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        # ── Queue section ──────────────────────────────────────────────────
        self._grp_queue = QGroupBox("📝 Tournament Queue")
        self._grp_queue.setStyleSheet(
            "QGroupBox { color:#FF7F00; font-weight:bold; border:1px solid #333;"
            " border-radius:5px; margin-top:6px; padding-top:6px; }"
            "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
        )
        lay_q = QVBoxLayout(self._grp_queue)

        row_btns = QHBoxLayout()
        self._btn_join = QPushButton("📝 Join Queue")
        self._btn_join.setFixedHeight(28)
        self._btn_join.setStyleSheet(_BTN_ORANGE)
        self._btn_join.clicked.connect(self._on_join_queue)
        row_btns.addWidget(self._btn_join)

        self._btn_leave = QPushButton("❌ Leave Queue")
        self._btn_leave.setFixedHeight(28)
        self._btn_leave.setStyleSheet(_BTN_RED)
        self._btn_leave.setEnabled(False)
        self._btn_leave.clicked.connect(self._on_leave_queue)
        row_btns.addWidget(self._btn_leave)
        row_btns.addStretch(1)
        lay_q.addLayout(row_btns)

        self._lbl_queue_status = QLabel("Not in queue.")
        self._lbl_queue_status.setStyleSheet("color:#888; font-style:italic;")
        lay_q.addWidget(self._lbl_queue_status)

        self._lbl_countdown = QLabel("")
        self._lbl_countdown.setStyleSheet("color:#FF7F00; font-style:italic;")
        self._lbl_countdown.hide()
        lay_q.addWidget(self._lbl_countdown)

        self._progress_queue = QProgressBar()
        self._progress_queue.setRange(0, TOURNAMENT_SIZE)
        self._progress_queue.setValue(0)
        self._progress_queue.setFormat(f"0/{TOURNAMENT_SIZE} Players")
        self._progress_queue.setFixedHeight(18)
        self._progress_queue.setStyleSheet(
            "QProgressBar { background:#222; border:1px solid #444; border-radius:4px;"
            " color:#DDD; text-align:center; font-size:9pt; }"
            "QProgressBar::chunk { background:#FF7F00; border-radius:3px; }"
        )
        self._progress_queue.hide()
        lay_q.addWidget(self._progress_queue)

        left_col.addWidget(self._grp_queue)

        # ── Bracket section ────────────────────────────────────────────────
        self._grp_bracket = QGroupBox("🏆 My Tournament")
        self._grp_bracket.setStyleSheet(
            "QGroupBox { color:#FF7F00; font-weight:bold; border:1px solid #333;"
            " border-radius:5px; margin-top:6px; padding-top:6px; }"
            "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
        )
        lay_b = QVBoxLayout(self._grp_bracket)
        lay_b.setSpacing(4)

        self._lbl_table = QLabel("")
        self._lbl_table.setStyleSheet("color:#FF7F00; font-weight:bold; font-size:11pt;")
        self._lbl_table.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_b.addWidget(self._lbl_table)

        # Semifinal rows
        self._sf_labels: list[QLabel] = []
        for i in range(2):
            lbl = QLabel(f"Semifinal {i + 1}: —")
            lbl.setStyleSheet("color:#DDD; font-size:10pt; padding:2px 6px;")
            lbl.setWordWrap(True)
            lay_b.addWidget(lbl)
            self._sf_labels.append(lbl)

        sep = QLabel("──────────────────────────────────────────")
        sep.setStyleSheet("color:#444;")
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_b.addWidget(sep)

        self._lbl_final = QLabel("Final: —")
        self._lbl_final.setStyleSheet("color:#DDD; font-size:10pt; font-weight:bold; padding:2px 6px;")
        self._lbl_final.setWordWrap(True)
        lay_b.addWidget(self._lbl_final)

        self._lbl_bracket_status = QLabel("")
        self._lbl_bracket_status.setStyleSheet("color:#888; font-style:italic; font-size:9pt;")
        self._lbl_bracket_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_b.addWidget(self._lbl_bracket_status)

        self._lbl_tournament_vpx_hint = QLabel(
            "ℹ️ Scores are submitted when VPX is closed — remind opponents to close VPX after playing!"
        )
        self._lbl_tournament_vpx_hint.setStyleSheet("color:#888; font-style:italic; font-size:9pt;")
        self._lbl_tournament_vpx_hint.setWordWrap(True)
        lay_b.addWidget(self._lbl_tournament_vpx_hint)

        self._grp_bracket.hide()
        left_col.addWidget(self._grp_bracket)

        # ── History section ────────────────────────────────────────────────
        grp_hist = QGroupBox("📜 Tournament History")
        grp_hist.setStyleSheet(
            "QGroupBox { color:#FF7F00; font-weight:bold; border:1px solid #333;"
            " border-radius:5px; margin-top:6px; padding-top:6px; }"
            "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
        )
        lay_h = QVBoxLayout(grp_hist)

        self._tbl_history = QTableWidget(0, 3)
        self._tbl_history.setHorizontalHeaderLabels(["Date", "Table", "Placement"])
        self._tbl_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl_history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl_history.setAlternatingRowColors(True)
        self._tbl_history.setStyleSheet(_TABLE_STYLE)
        lay_h.addWidget(self._tbl_history)

        left_col.addWidget(grp_hist)
        left_col.addStretch(1)

        # ── Chat panel (below tournament content) ─────────────────────────
        self._chat_widget = ChatWidget(self._cfg)
        self._chat_widget.setMaximumHeight(660)

        # Compose the vertical layout: tournament content on top, chat below
        root.addLayout(left_col, 1)
        root.addWidget(self._chat_widget)

        # ── Bottom bar ─────────────────────────────────────────────────────
        bottom = QHBoxLayout()

        btn_rules = QPushButton("📜 Tournament Rules")
        btn_rules.setFixedHeight(28)
        btn_rules.setStyleSheet(
            "QPushButton { background-color:#1a1a1a; color:#FF7F00; border:1px solid #FF7F00;"
            " border-radius:5px; font-weight:bold; padding:0 14px; }"
            "QPushButton:hover { background-color:#FF7F00; color:#000; }"
        )
        btn_rules.clicked.connect(self._show_rules)
        bottom.addWidget(btn_rules)

        bottom.addSpacing(12)

        self._btn_refresh = QPushButton("🔄 Refresh")
        self._btn_refresh.setFixedHeight(28)
        self._btn_refresh.setStyleSheet(_BTN_BLUE)
        self._btn_refresh.clicked.connect(self.refresh)
        bottom.addWidget(self._btn_refresh)

        bottom.addSpacing(8)
        self._lbl_status = QLabel("Not loaded yet.")
        self._lbl_status.setStyleSheet("color:#888; font-style:italic; font-size:10pt;")
        bottom.addWidget(self._lbl_status)
        bottom.addStretch(1)

        self._lbl_updated = QLabel("")
        self._lbl_updated.setStyleSheet("color:#666; font-size:10pt;")
        bottom.addWidget(self._lbl_updated)

        root.addLayout(bottom)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Trigger a background poll and UI refresh."""
        if self._fetching:
            return
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            self._lbl_status.setText("Cloud Sync is disabled.")
            return
        self._fetching = True
        self._btn_refresh.setEnabled(False)
        self._lbl_status.setText("Loading…")
        t = threading.Thread(target=self._poll_in_background, daemon=True)
        t.start()

    # ── Poll timer ────────────────────────────────────────────────────────────

    def _on_poll_timer(self) -> None:
        """Periodic background poll (called by QTimer every 30 s)."""
        # Try to deliver any deferred notifications when VPX is not running.
        self._try_show_deferred_notification()
        if not self._fetching:
            self.refresh()

    # ── Background poll ───────────────────────────────────────────────────────

    def _poll_in_background(self) -> None:
        """Run queue + active-tournament polls in a worker thread.

        Always calls ``poll_queue()`` regardless of the local ``_in_queue``
        flag so that the UI correctly detects existing cloud queue entries
        after an app restart (fixes _in_queue drift on restart).
        """
        try:
            result: dict = {}

            # Always poll the queue to detect current cloud membership and to
            # handle app-restart drift where _in_queue=False but a cloud entry
            # exists.  Tournament creation is guarded by the deterministic
            # creator-election inside poll_queue() so this is safe to call
            # even when the local flag says we are not queued.
            q = self._engine.poll_queue()
            result["queue"] = q
            if q.get("tournament_started") and q.get("tournament"):
                result["active"] = q["tournament"]
            else:
                # Also check if another player started a tournament for us.
                t = self._engine.poll_active_tournament()
                if t:
                    result["active"] = t

            # Always load local history.
            result["history"] = self._engine.get_history()

            QMetaObject.invokeMethod(
                self,
                "_on_poll_done",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(object, result),
            )
        except Exception as exc:
            QMetaObject.invokeMethod(
                self,
                "_on_poll_error",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, str(exc)),
            )
        finally:
            self._fetching = False

    # ── Slots (main thread) ───────────────────────────────────────────────────

    @pyqtSlot(object)
    def _on_poll_done(self, result: object) -> None:
        data: dict = result  # type: ignore[assignment]

        q_data = data.get("queue")
        if q_data:
            self._in_queue = q_data.get("in_queue", self._in_queue)
            if q_data.get("tournament_started"):
                self._in_queue = False
                # Force an immediate re-poll to show the bracket quickly
                QTimer.singleShot(500, self.refresh)
            self._update_queue_ui(q_data)

        active = data.get("active")
        if active:
            self._active_tournament = active
            self._update_bracket_ui(active)
            self._queue_pending_notifications(active)
        elif self._active_tournament and self._active_tournament.get("status") == "completed":
            # The cloud entry is gone (coordinator deleted it after completion)
            # but we still have it cached.  Keep showing the completed bracket so
            # the player can see the final result.  Also make sure this player's
            # local history contains the entry (safety net for non-coordinators).
            self._engine.ensure_in_history(self._active_tournament)
            self._update_bracket_ui(self._active_tournament)
            # Schedule cleanup: hide the bracket after 5 minutes so it doesn't
            # linger forever in case the player never explicitly dismisses it.
            if not self._completed_bracket_timer_started:
                self._completed_bracket_timer_started = True
                QTimer.singleShot(_COMPLETED_BRACKET_DISPLAY_MS, self._clear_completed_tournament)
        elif not self._in_queue:
            self._active_tournament = None
            self._grp_bracket.hide()

        history = data.get("history", [])
        self._update_history_ui(history)

        now_str = datetime.now().strftime("%H:%M:%S")
        self._lbl_status.setText("Ready.")
        self._lbl_updated.setText(f"Last updated: {now_str}")
        self._btn_refresh.setEnabled(True)

        # Try to show deferred notifications now that UI is refreshed.
        self._try_show_deferred_notification()
        self._adjust_poll_interval()

    @pyqtSlot(str)
    def _on_poll_error(self, msg: str) -> None:
        self._lbl_status.setText(f"Error: {msg}")
        self._btn_refresh.setEnabled(True)

    def _adjust_poll_interval(self) -> None:
        """Switch to fast polling during active tournaments, slow polling otherwise."""
        if (self._active_tournament
                and self._active_tournament.get("status") in ("semifinal", "final")):
            desired = _POLL_INTERVAL_ACTIVE_MS
        else:
            desired = _POLL_INTERVAL_IDLE_MS
        if self._poll_timer.interval() != desired:
            self._poll_timer.setInterval(desired)

    def _clear_completed_tournament(self) -> None:
        """Hide the bracket and clear the cached completed tournament.

        Called by a 5-minute QTimer so that a completed bracket does not
        linger on screen indefinitely after the tournament has ended.
        """
        self._active_tournament = None
        self._completed_bracket_timer_started = False
        if not self._in_queue:
            self._grp_bracket.hide()

    # ── Queue button handlers ─────────────────────────────────────────────────

    def _on_join_queue(self) -> None:
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            self._lbl_queue_status.setText("Cloud Sync is disabled.")
            return
        self._btn_join.setEnabled(False)
        self._lbl_queue_status.setText("Joining queue…")

        def _do():
            ok = self._engine.join_queue()
            QMetaObject.invokeMethod(
                self, "_on_join_done",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(bool, ok),
            )

        threading.Thread(target=_do, daemon=True).start()

    @pyqtSlot(bool)
    def _on_join_done(self, ok: bool) -> None:
        if ok:
            self._in_queue = True
            self._btn_join.setEnabled(False)
            self._btn_leave.setEnabled(True)
            self._progress_queue.show()
            self._progress_queue.setValue(1)
            self._progress_queue.setFormat(f"1/{TOURNAMENT_SIZE} Players")
            self._lbl_queue_status.setText("In queue – waiting for players…")
        else:
            self._btn_join.setEnabled(True)
            self._lbl_queue_status.setText("Failed to join queue. Check Cloud Sync and VPS-IDs.")

    def _on_leave_queue(self) -> None:
        self._btn_leave.setEnabled(False)
        self._lbl_queue_status.setText("Leaving queue…")

        def _do():
            ok = self._engine.leave_queue()
            QMetaObject.invokeMethod(
                self, "_on_leave_done",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(bool, ok),
            )

        threading.Thread(target=_do, daemon=True).start()

    @pyqtSlot(bool)
    def _on_leave_done(self, ok: bool) -> None:
        self._in_queue = False
        self._queue_expires_at = 0.0
        self._countdown_timer.stop()
        self._lbl_countdown.hide()
        self._btn_join.setEnabled(True)
        self._btn_leave.setEnabled(False)
        self._progress_queue.hide()
        self._progress_queue.setValue(0)
        self._lbl_queue_status.setText("Left queue." if ok else "Left queue (cloud error).")

    # ── UI updaters ───────────────────────────────────────────────────────────

    def _update_queue_ui(self, q_data: dict) -> None:
        """Refresh the queue section with the latest poll data."""
        in_queue    = q_data.get("in_queue", False)
        q_count     = q_data.get("queue_count", 0)
        q_players   = q_data.get("queue_players", [])
        started     = q_data.get("tournament_started", False)

        # Sync button states.
        self._btn_join.setEnabled(not in_queue and not started)
        self._btn_leave.setEnabled(in_queue)

        if started:
            self._progress_queue.hide()
            self._lbl_countdown.hide()
            self._countdown_timer.stop()
            self._lbl_queue_status.setText("🏆 Tournament started!")
            return

        if in_queue:
            self._progress_queue.show()
            self._progress_queue.setValue(q_count)
            self._progress_queue.setFormat(f"{q_count}/{TOURNAMENT_SIZE} Players")
            names = [p.get("player_name", "?") for p in q_players]
            if names:
                status = "Players in queue: " + ", ".join(names)
            else:
                status = "In queue – waiting for more players…"
            self._lbl_queue_status.setText(status)
            # Update countdown timer.
            expires_at = q_data.get("my_expires_at", 0.0)
            if expires_at > 0:
                self._queue_expires_at = expires_at
                self._lbl_countdown.show()
                self._update_countdown()
                if not self._countdown_timer.isActive():
                    self._countdown_timer.start()
        else:
            self._progress_queue.hide()
            self._lbl_countdown.hide()
            self._countdown_timer.stop()
            self._lbl_queue_status.setText("Not in queue.")

    @pyqtSlot()
    def _update_countdown(self) -> None:
        """Update the countdown label with the remaining queue time."""
        if self._queue_expires_at <= 0:
            self._lbl_countdown.hide()
            return
        remaining = self._queue_expires_at - time.time()
        if remaining <= 0:
            self._lbl_countdown.setText("⏱ Queue expired")
            self._countdown_timer.stop()
            return
        mins = int(remaining) // 60
        secs = int(remaining) % 60
        self._lbl_countdown.setText(f"⏱ {mins:02d}:{secs:02d} remaining")

    def _update_bracket_ui(self, tournament: dict) -> None:
        """Refresh the bracket visualisation with the current tournament state."""
        my_id      = self._cfg.OVERLAY.get("player_id", "")
        bracket    = tournament.get("bracket") or {}
        semifinals = bracket.get("semifinal") or []
        final      = bracket.get("final") or {}
        status     = tournament.get("status", "semifinal")
        table_name = _clean_table_name(tournament.get("table_name") or tournament.get("table_rom") or "")

        self._grp_bracket.show()
        self._lbl_table.setText(f"🎰 {table_name}")

        for i, sf in enumerate(semifinals[:2]):
            pa   = sf.get("player_a_name", "?")
            pb   = sf.get("player_b_name", "?")
            w    = sf.get("winner", "")
            wn   = sf.get("winner_name", "")
            sa   = sf.get("score_a", -1)
            sb   = sf.get("score_b", -1)
            a_id = sf.get("player_a", "")
            b_id = sf.get("player_b", "")

            is_mine = (a_id == my_id or b_id == my_id)
            prefix  = "★ " if is_mine else ""

            if w:
                score_txt = ""
                if sa >= 0 and sb >= 0:
                    score_txt = f"  ({sa:,} – {sb:,})"
                text = f"{prefix}SF{i + 1}: {_esc(pa)} vs {_esc(pb)}{score_txt}  →  🏆 {_esc(wn)}"
            else:
                text = f"{prefix}SF{i + 1}: {_esc(pa)} vs {_esc(pb)}  ⏳"

            lbl = self._sf_labels[i]
            lbl.setText(text)
            color = "#FF7F00" if is_mine else "#DDD"
            lbl.setStyleSheet(f"color:{color}; font-size:10pt; padding:2px 6px;")

        # Final row.
        if status in ("final", "completed") and final:
            pa   = final.get("player_a_name", "?")
            pb   = final.get("player_b_name", "?")
            w    = final.get("winner", "")
            wn   = final.get("winner_name", "")
            sa   = final.get("score_a", -1)
            sb   = final.get("score_b", -1)
            a_id = final.get("player_a", "")
            b_id = final.get("player_b", "")

            is_mine = (a_id == my_id or b_id == my_id)
            prefix  = "★ " if is_mine else ""

            if w:
                score_txt = ""
                if sa >= 0 and sb >= 0:
                    score_txt = f"  ({sa:,} – {sb:,})"
                text = f"{prefix}🏆 FINAL: {_esc(pa)} vs {_esc(pb)}{score_txt}  →  🏆 {_esc(wn)}"
            else:
                text = f"{prefix}🏆 FINAL: {_esc(pa)} vs {_esc(pb)}  ⏳"

            color = "#FF7F00" if is_mine else "#DDD"
            self._lbl_final.setText(text)
            self._lbl_final.setStyleSheet(
                f"color:{color}; font-size:10pt; font-weight:bold; padding:2px 6px;"
            )
        else:
            self._lbl_final.setText("🏆 FINAL: — (waiting for semifinals)")
            self._lbl_final.setStyleSheet("color:#666; font-size:10pt; font-weight:bold; padding:2px 6px;")

        if status == "completed":
            winner_name = tournament.get("winner_name", "?")
            self._lbl_bracket_status.setText(f"Tournament completed – 🏆 {_esc(winner_name)}")
        elif status == "final":
            self._lbl_bracket_status.setText("⚔️ Final is live!")
        else:
            self._lbl_bracket_status.setText("⚔️ Semifinals in progress…")

    def _update_history_ui(self, history: list) -> None:
        """Populate the history table."""
        self._tbl_history.setRowCount(0)
        for t in history:
            row = self._tbl_history.rowCount()
            self._tbl_history.insertRow(row)

            created_at = float(t.get("created_at", 0))
            try:
                date_text = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d")
            except Exception:
                date_text = "—"

            table_name = _clean_table_name(t.get("table_name", "") or t.get("table_rom", "") or "?")
            placement  = self._engine.get_my_placement(t)

            for col, text in enumerate([date_text, table_name, placement]):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._tbl_history.setItem(row, col, item)

    # ── Notifications ─────────────────────────────────────────────────────────

    def _queue_pending_notifications(self, tournament: dict) -> None:
        """Check for unseen notifications and add them to the deferred queue."""
        pending = self._engine.get_pending_notifications(tournament)
        tid = tournament.get("tournament_id", "")
        for event, msg in pending:
            # Mark as shown immediately so it won't be regenerated on the next poll.
            self._engine.mark_notification_shown(tid, event)
            self._deferred_notifications.append({"event": event, "msg": msg, "tid": tid})

    def _is_vpx_running(self) -> bool:
        """Return True when VPX (or VPX Player) is currently running."""
        try:
            w = getattr(self._main_window, "watcher", None)
            if w:
                return bool(w.game_active or w._vp_player_visible())
        except Exception:
            pass
        return False

    def _try_show_deferred_notification(self) -> None:
        """Show the next deferred notification if VPX is not running."""
        if not self._deferred_notifications:
            return
        if self._is_vpx_running():
            return  # Defer until VPX exits.
        # Check if another tournament notification is already on screen.
        if getattr(self._main_window, "_tournament_notify_state", None) is not None:
            return  # Wait for user to dismiss current one.
        notification = self._deferred_notifications.pop(0)
        self._display_notification(notification)

    def _display_notification(self, notification: dict) -> None:
        """Display a tournament notification using the duel overlay."""
        msg = notification.get("msg", "")
        try:
            from ui.overlay_base import _force_topmost
            ov = self._main_window._get_duel_overlay()
            ov.show_info(msg, seconds=0, color_hex="#FF7F00")
            _force_topmost(ov)
            QTimer.singleShot(200, lambda: _force_topmost(ov))
        except Exception:
            pass
        # Store state on main window so _on_nav_left can dismiss it.
        self._main_window._tournament_notify_state = {
            "event": notification.get("event", ""),
            "tid":   notification.get("tid", ""),
        }

    # ── Tournament Rules dialog ───────────────────────────────────────────────

    def _show_rules(self) -> None:
        dlg = QMessageBox(self)
        dlg.setWindowTitle("📜 Tournament Rules")
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.setText(
            "📜 Tournament Rules\n\n"
            "🏆 OVERVIEW\n"
            "Tournaments are automatic 4-player single-elimination brackets.\n"
            "All matches are played on the same table.\n\n"
            "📝 JOINING\n"
            "• Join the queue to enter the next tournament\n"
            "• Once 4 players with a shared table are found, the tournament starts\n"
            "• A random shared table is selected automatically\n"
            "• You can leave the queue anytime before the tournament starts\n"
            "• Queue entries expire after 30 minutes\n\n"
            "⚔️ MATCHES\n"
            "• All matches are auto-accepted – no declining once the tournament starts\n"
            "• You have 2 hours to play each match\n"
            "• Each match runs independently – every player has the full time\n"
            "• Cloud Sync must be enabled\n"
            "• Tables must have a VPS-ID assigned\n\n"
            "🏅 BRACKET\n"
            "• Semifinal: 2 matches\n"
            "• Final starts when both semifinals are complete\n"
            "• Same table for all rounds\n\n"
            "⚠️ FORFEIT\n"
            "• Not playing within 2 hours = forfeit (opponent advances)\n"
            "• Quitting VPX early = forfeit\n"
            "• Only ONE game per match — restarting in-game (F3) or\n"
            "  starting at ball 1 new will abort the match! (NVRAM tracking)\n\n"
            "🏆 RESULTS\n"
            "• Highest score wins each match\n"
            "• Tie = challenger wins\n"
            "• Final placements: 🏆 Winner, #2, #3-4"
        )
        dlg.exec()
