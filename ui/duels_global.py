"""Global Duel Feed widget – shows the last 50 completed duels from all players."""
from __future__ import annotations

import threading
from datetime import datetime

from PyQt6.QtCore import QMetaObject, Qt, Q_ARG, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QVBoxLayout, QWidget,
)

from core.duel_engine import DuelStatus

_TABLE_STYLE = (
    "QTableWidget { background:#111; color:#DDD; gridline-color:#333; }"
    "QTableWidget::item:alternate { background:#1a1a1a; }"
    "QTableWidget::item:selected { background:#1a3a3a; }"
    "QHeaderView::section { background:#222; color:#FF7F00; font-weight:bold;"
    " border:1px solid #333; padding:4px; }"
)

_COMPLETED_STATUSES = {DuelStatus.WON, DuelStatus.LOST}
_MAX_ROWS = 50


class GlobalDuelFeedWidget(QWidget):
    """Widget that displays the last 50 completed duels from the cloud.

    Parameters
    ----------
    cfg : AppConfig
        Application configuration (must provide CLOUD_ENABLED / CLOUD_URL).
    parent : QWidget, optional
    """

    def __init__(self, cfg, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._fetching = False
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Player 1", "Player 2", "Table", "Result", "Score", "Date"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(_TABLE_STYLE)
        layout.addWidget(self._table)

        # Bottom row: Refresh button + status label
        bottom = QHBoxLayout()

        self._btn_refresh = QPushButton("🔄 Refresh")
        self._btn_refresh.setFixedHeight(28)
        self._btn_refresh.setStyleSheet(
            "QPushButton { background-color:#005c99; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:0 14px; }"
            "QPushButton:hover { background-color:#0070bb; }"
            "QPushButton:disabled { background-color:#333; color:#666; }"
        )
        self._btn_refresh.clicked.connect(self.refresh)
        bottom.addWidget(self._btn_refresh)
        bottom.addSpacing(12)

        self._lbl_status = QLabel("Not loaded yet.")
        self._lbl_status.setStyleSheet("color:#888; font-style:italic; font-size:10pt;")
        bottom.addWidget(self._lbl_status)
        bottom.addStretch(1)

        self._lbl_updated = QLabel("")
        self._lbl_updated.setStyleSheet("color:#666; font-size:10pt;")
        bottom.addWidget(self._lbl_updated)

        layout.addLayout(bottom)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Start a background fetch of the global duel feed."""
        if self._fetching:
            return
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            self._lbl_status.setText("Cloud Sync is disabled.")
            return
        self._fetching = True
        self._btn_refresh.setEnabled(False)
        self._lbl_status.setText("Loading…")
        t = threading.Thread(target=self._fetch_in_background, daemon=True)
        t.start()

    # ── Background fetch ──────────────────────────────────────────────────────

    def _fetch_in_background(self) -> None:
        try:
            from core.cloud_sync import CloudSync
            raw = CloudSync.fetch_node(self._cfg, "duels")
            if not isinstance(raw, dict):
                rows: list = []
                total = 0
            else:
                # Keep only completed duels (won / lost)
                completed = [
                    v for v in raw.values()
                    if isinstance(v, dict)
                    and v.get("status") in _COMPLETED_STATUSES
                ]
                # Sort newest first, limit to _MAX_ROWS
                completed.sort(key=lambda d: float(d.get("completed_at", 0)), reverse=True)
                rows = completed[:_MAX_ROWS]
                total = len(completed)
            QMetaObject.invokeMethod(
                self,
                "_on_fetch_done",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(object, (rows, total)),
            )
        except Exception as exc:
            QMetaObject.invokeMethod(
                self,
                "_on_fetch_error",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, str(exc)),
            )
        finally:
            self._fetching = False

    # ── Slots called on main thread ───────────────────────────────────────────

    @pyqtSlot(object)
    def _on_fetch_done(self, payload: object) -> None:
        """Populate the table widget from the fetched rows (called on main thread)."""
        rows, total = payload  # type: ignore[misc]
        self._table.setRowCount(0)
        for row_data in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)

            challenger_name = str(row_data.get("challenger_name", "?"))
            opponent_name   = str(row_data.get("opponent_name", "?"))
            table_name      = str(row_data.get("table_name", row_data.get("table_rom", "?")))
            ch_score        = int(row_data.get("challenger_score", -1))
            op_score        = int(row_data.get("opponent_score", -1))
            completed_at    = float(row_data.get("completed_at", 0))

            # Determine winner / result column by comparing scores directly.
            # The status field (WON/LOST) is relative to whoever last called
            # submit_result() and is therefore unreliable for a global view.
            # challenger_name, opponent_name, challenger_score and opponent_score
            # are always stored correctly in the cloud.
            if ch_score >= 0 and op_score >= 0:
                if ch_score == op_score:
                    winner_name = challenger_name
                    score_text = f"{ch_score:,} vs {op_score:,}"
                    result_text = "🤝 Tie (Challenger wins)"
                elif ch_score > op_score:
                    winner_name = challenger_name
                    score_text = f"{ch_score:,} vs {op_score:,}"
                    result_text = f"🏆 {winner_name}"
                else:
                    winner_name = opponent_name
                    score_text = f"{op_score:,} vs {ch_score:,}"
                    result_text = f"🏆 {winner_name}"
            else:
                winner_name = ""
                score_text = ""
                result_text = "—"

            # Date column
            if completed_at:
                try:
                    date_text = datetime.fromtimestamp(completed_at).strftime("%Y-%m-%d %H:%M")
                except (OSError, OverflowError, ValueError):
                    date_text = "—"
            else:
                date_text = "—"

            for col, text in enumerate(
                [challenger_name, opponent_name, table_name, result_text, score_text, date_text]
            ):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._table.setItem(row, col, item)

        now_str = datetime.now().strftime("%H:%M:%S")
        self._lbl_status.setText(f"Showing {len(rows)} of {total} duels")
        self._lbl_updated.setText(f"Last updated: {now_str}")
        self._btn_refresh.setEnabled(True)

    @pyqtSlot(str)
    def _on_fetch_error(self, msg: str) -> None:
        self._lbl_status.setText(f"Error: {msg}")
        self._btn_refresh.setEnabled(True)
