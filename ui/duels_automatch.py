"""ui_duels_automatch.py – Auto-Match widget for the Score Duels tab.

Provides :class:`AutoMatchWidget`, a self-contained QWidget that lets the
player join the cloud matchmaking queue and automatically find an opponent
with at least one shared VPS-ID table.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt, QTimer, QMetaObject, Q_ARG, pyqtSlot
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton,
)

# Total search timeout in seconds (5 minutes).
_TIMEOUT_SECONDS = 300
# Polling interval in milliseconds (15 seconds).
_POLL_INTERVAL_MS = 15_000
# Countdown refresh interval in milliseconds (1 second).
_COUNTDOWN_INTERVAL_MS = 1_000


class AutoMatchWidget(QWidget):
    """Auto-Match UI widget.

    Parameters
    ----------
    main_window : QWidget
        The main application window.  Used to reach the Trophie mascot.
    cfg : AppConfig
        Application configuration.
    duel_engine : DuelEngine
        The shared :class:`~duel_engine.DuelEngine` instance.
    """

    def __init__(self, main_window, cfg, duel_engine) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._cfg = cfg
        self._engine = duel_engine

        self._searching = False
        self._elapsed = 0  # seconds elapsed since search started

        self._build_ui()

        # 15-second polling timer.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._do_poll)

        # 1-second countdown timer.
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(_COUNTDOWN_INTERVAL_MS)
        self._countdown_timer.timeout.connect(self._tick_countdown)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Auto-Match button ──────────────────────────────────────────────
        row_btn = QHBoxLayout()
        row_btn.setContentsMargins(0, 0, 0, 0)

        self._btn_automatch = QPushButton("🔀 Auto-Match")
        self._btn_automatch.setToolTip(
            "Automatically find an opponent with at least one shared table (VPS-ID)."
        )
        self._btn_automatch.setStyleSheet(
            "QPushButton { background-color:#1a3a5c; color:#FFFFFF; font-weight:bold;"
            " border:1px solid #336699; border-radius:5px; padding:6px 18px; }"
            "QPushButton:hover { background-color:#1e4a78; }"
            "QPushButton:disabled { background-color:#222222; color:#555555;"
            " border-color:#333333; }"
        )
        self._btn_automatch.clicked.connect(self._on_automatch_clicked)
        row_btn.addWidget(self._btn_automatch)
        row_btn.addStretch(1)
        layout.addLayout(row_btn)

        # ── Status row (visible only while searching) ──────────────────────
        self._row_status = QWidget()
        row_status_layout = QHBoxLayout(self._row_status)
        row_status_layout.setContentsMargins(0, 0, 0, 0)
        row_status_layout.setSpacing(8)

        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color:#00BFFF; font-style:italic;")
        row_status_layout.addWidget(self._lbl_status, 1)

        self._btn_stop = QPushButton("❌ Stop")
        self._btn_stop.setStyleSheet(
            "QPushButton { background-color:#3a1a1a; color:#FF6666; font-weight:bold;"
            " border:1px solid #993333; border-radius:5px; padding:4px 10px; }"
            "QPushButton:hover { background-color:#5a2020; }"
        )
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        row_status_layout.addWidget(self._btn_stop)

        self._row_status.setVisible(False)
        layout.addWidget(self._row_status)

        # ── Info label (queue count / shared tables) ───────────────────────
        self._lbl_info = QLabel("")
        self._lbl_info.setStyleSheet("color:#888888; font-style:italic; font-size:10pt;")
        self._lbl_info.setVisible(False)
        layout.addWidget(self._lbl_info)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_automatch_clicked(self) -> None:
        """Validate preconditions and start the matchmaking search."""
        if self._searching:
            return
        # Validate: Cloud Sync must be enabled.
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            self._show_result("⚠️ Cloud Sync is disabled.", "#FFAA00")
            return
        # Validate: player must have at least one VPS-ID.
        try:
            from .vps import _load_vps_mapping
            vps_mapping = _load_vps_mapping(self._cfg)
        except Exception:
            vps_mapping = {}
        if not vps_mapping:
            self._show_result("⚠️ No tables with VPS-ID found.", "#FFAA00")
            return
        self._start_search()

    def _on_stop_clicked(self) -> None:
        """Cancel the ongoing search."""
        self._stop_search()
        self._show_result("", "")  # clear status
        self._btn_automatch.setEnabled(True)

    # ── Search lifecycle ──────────────────────────────────────────────────────

    def _start_search(self) -> None:
        """Join the queue, start timers, update UI."""
        def _join():
            ok = self._engine.join_matchmaking()
            QMetaObject.invokeMethod(
                self, "_on_joined",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(bool, ok),
            )
        threading.Thread(target=_join, daemon=True).start()

    @pyqtSlot(bool)
    def _on_joined(self, ok: bool) -> None:
        if not ok:
            self._show_result("❌ Failed to join queue. Check Cloud Sync.", "#CC4444")
            return
        self._searching = True
        self._elapsed = 0
        self._btn_automatch.setEnabled(False)
        self._row_status.setVisible(True)
        self._lbl_info.setText("0 players in queue • 0 shared tables")
        self._lbl_info.setVisible(True)
        self._update_countdown_label()
        self._poll_timer.start()
        self._countdown_timer.start()
        # Notify Trophie.
        try:
            trophie = getattr(self._mw, "_trophie_gui", None)
            if trophie is not None:
                trophie.on_automatch_started()
        except Exception:
            pass
        # First poll immediately.
        self._do_poll()

    def _stop_search(self) -> None:
        """Stop timers and leave the queue (non-blocking)."""
        self._searching = False
        self._poll_timer.stop()
        self._countdown_timer.stop()
        self._row_status.setVisible(False)
        self._lbl_info.setVisible(False)
        threading.Thread(target=self._engine.leave_matchmaking, daemon=True).start()

    # ── Timers ────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _tick_countdown(self) -> None:
        if not self._searching:
            return
        self._elapsed += 1
        if self._elapsed >= _TIMEOUT_SECONDS:
            self._stop_search()
            self._show_result("⏰ No match found. Try again later.", "#FFAA00")
            self._btn_automatch.setEnabled(True)
            # Notify Trophie.
            try:
                trophie = getattr(self._mw, "_trophie_gui", None)
                if trophie is not None:
                    trophie.on_automatch_timeout()
            except Exception:
                pass
            return
        self._update_countdown_label()

    def _update_countdown_label(self) -> None:
        remaining = max(0, _TIMEOUT_SECONDS - self._elapsed)
        mins, secs = divmod(remaining, 60)
        self._lbl_status.setText(
            f"🔍 Searching for opponent... ({mins}:{secs:02d})"
        )
        self._lbl_status.setStyleSheet("color:#00BFFF; font-style:italic;")

    # ── Polling ───────────────────────────────────────────────────────────────

    def _do_poll(self) -> None:
        """Run poll_matchmaking() in a background thread."""
        if not self._searching:
            return
        def _poll():
            result = self._engine.poll_matchmaking()
            QMetaObject.invokeMethod(
                self, "_on_poll_result",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(object, result),
            )
        threading.Thread(target=_poll, daemon=True).start()

    @pyqtSlot(object)
    def _on_poll_result(self, result) -> None:
        if not self._searching:
            return
        if result is None:
            return  # error – keep searching, keep last info visible
        if "opponent_name" in result:
            # Match found!
            self._stop_search()
            opponent = result.get("opponent_name", "")
            table    = result.get("table_name", "")
            self._show_result(
                f"✅ Match found! Duel invitation sent to {opponent} on {table}",
                "#00E500",
            )
            self._btn_automatch.setEnabled(True)
            # Notify Trophie.
            try:
                trophie = getattr(self._mw, "_trophie_gui", None)
                if trophie is not None:
                    trophie.on_automatch_found()
            except Exception:
                pass
            # Refresh active duels table.
            try:
                QMetaObject.invokeMethod(
                    self._mw, "_refresh_active_duels",
                    Qt.ConnectionType.QueuedConnection,
                )
            except Exception:
                pass
        else:
            queue_count   = result.get("queue_count", 0)
            shared_tables = result.get("shared_tables", 0)
            self._lbl_info.setText(
                f"{queue_count} player{'s' if queue_count != 1 else ''} in queue"
                f" • {shared_tables} shared table{'s' if shared_tables != 1 else ''}"
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _show_result(self, text: str, color: str) -> None:
        """Display a result/status message below the button row."""
        if text:
            self._lbl_status.setText(text)
            self._lbl_status.setStyleSheet(
                f"color:{color}; font-style:italic;" if color else "color:#888888; font-style:italic;"
            )
            self._row_status.setVisible(True)
            self._btn_stop.setVisible(False)  # hide Stop when showing final result
        else:
            self._lbl_status.setText("")
            self._row_status.setVisible(False)
        self._lbl_info.setVisible(False)
