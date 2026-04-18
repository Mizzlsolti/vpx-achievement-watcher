"""Duel Leaderboard widget – shows the top 50 players ranked by wins."""
from __future__ import annotations

import threading
import time
from datetime import datetime

from PyQt6.QtCore import QMetaObject, Qt, Q_ARG, pyqtSlot
from PyQt6.QtGui import QColor
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
_MAX_PLAYERS = 50
_MIN_DUELS = 1
_CACHE_TTL_SECONDS = 300  # 5 minutes
_ACCENT_COLOR = "#FF7F00"

_RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
_NUM_COLUMNS = 5


def _build_leaderboard(raw: dict, own_name: str) -> tuple[list[dict], int]:
    """Aggregate duel records into per-player stats and return sorted rows.

    Parameters
    ----------
    raw:
        The raw dict fetched from the ``duels/`` cloud node.
    own_name:
        The local player's name (used to mark the own row).

    Returns
    -------
    rows : list[dict]
        Up to ``_MAX_PLAYERS`` player-stat dicts, already sorted.
    total_ranked : int
        Total number of players that met the minimum-duel threshold.
    """
    stats: dict[str, dict] = {}

    for entry in raw.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("status") not in _COMPLETED_STATUSES:
            continue

        ch_name = str(entry.get("challenger_name", "")).strip()
        op_name = str(entry.get("opponent_name", "")).strip()
        ch_score = entry.get("challenger_score", -1)
        op_score = entry.get("opponent_score", -1)

        try:
            ch_score = int(ch_score)
            op_score = int(op_score)
        except (TypeError, ValueError):
            continue

        # Both scores must be non-negative and must NOT be equal (no ties)
        if ch_score < 0 or op_score < 0 or ch_score == op_score:
            continue

        if not ch_name or not op_name:
            continue

        # Initialise stat buckets on first encounter
        for name in (ch_name, op_name):
            if name not in stats:
                stats[name] = {"wins": 0, "losses": 0}

        if ch_score > op_score:
            stats[ch_name]["wins"] += 1
            stats[op_name]["losses"] += 1
        else:
            stats[op_name]["wins"] += 1
            stats[ch_name]["losses"] += 1

    # Include every player with at least one completed duel
    qualified = [
        {"name": name, "wins": s["wins"], "losses": s["losses"]}
        for name, s in stats.items()
        if s["wins"] + s["losses"] >= _MIN_DUELS
    ]

    total_ranked = len(qualified)

    # Sort: primary wins desc, secondary win-rate desc
    def _sort_key(p: dict) -> tuple:
        total = p["wins"] + p["losses"]
        rate = p["wins"] / total
        return (-p["wins"], -rate)

    qualified.sort(key=_sort_key)
    rows = qualified[:_MAX_PLAYERS]

    own_lower = own_name.strip().lower() if own_name else ""
    for rank_idx, row in enumerate(rows, start=1):
        row["rank"] = rank_idx
        total = row["wins"] + row["losses"]
        row["win_rate"] = row["wins"] / total * 100 if total else 0.0
        row["is_own"] = (row["name"].strip().lower() == own_lower) if own_lower else False

    return rows, total_ranked


class DuelLeaderboardWidget(QWidget):
    """Widget that displays the top 50 duel players ranked by wins.

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
        # TTL cache: {"rows": [...], "total": int, "ts": float}
        self._cache: dict | None = None
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Table – 5 columns: Rank, Player, Wins, Losses, Win Rate
        self._table = QTableWidget(0, _NUM_COLUMNS)
        self._table.setHorizontalHeaderLabels(
            ["Rank", "Player", "Wins", "Losses", "Win Rate"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(_TABLE_STYLE)
        layout.addWidget(self._table)

        # Bottom row: Refresh button + status label + last-updated label
        bottom = QHBoxLayout()

        self._btn_refresh = QPushButton("🔄 Refresh")
        self._btn_refresh.setFixedHeight(28)
        self._btn_refresh.setStyleSheet(
            "QPushButton { background-color:#005c99; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:0 14px; }"
            "QPushButton:hover { background-color:#0070bb; }"
            "QPushButton:disabled { background-color:#333; color:#666; }"
        )
        self._btn_refresh.clicked.connect(self._on_refresh_clicked)
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
        """Show cached data if still fresh, otherwise start a background fetch."""
        if self._fetching:
            return
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            self._lbl_status.setText("Cloud Sync is disabled.")
            return

        # Serve from cache when TTL has not expired
        if self._cache is not None:
            age = time.time() - self._cache.get("ts", 0)
            if age < _CACHE_TTL_SECONDS:
                self._populate_table(self._cache["rows"], self._cache["total"])
                return

        self._start_fetch()

    def _on_refresh_clicked(self) -> None:
        """Force a fresh fetch, bypassing the cache."""
        self._cache = None
        self.refresh()

    # ── Background fetch ──────────────────────────────────────────────────────

    def _start_fetch(self) -> None:
        self._fetching = True
        self._btn_refresh.setEnabled(False)
        self._lbl_status.setText("Loading…")
        t = threading.Thread(target=self._fetch_in_background, daemon=True)
        t.start()

    def _fetch_in_background(self) -> None:
        try:
            from core.cloud_sync import CloudSync
            raw = CloudSync.fetch_node(self._cfg, "duels")
            if not isinstance(raw, dict):
                rows: list = []
                total = 0
            else:
                own_name = self._cfg.OVERLAY.get("player_name", "")
                rows, total = _build_leaderboard(raw, own_name)
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
        rows, total = payload  # type: ignore[misc]
        # Store in cache
        self._cache = {"rows": rows, "total": total, "ts": time.time()}
        self._populate_table(rows, total)

    @pyqtSlot(str)
    def _on_fetch_error(self, msg: str) -> None:
        self._lbl_status.setText(f"Error: {msg}")
        self._btn_refresh.setEnabled(True)

    # ── Table population ──────────────────────────────────────────────────────

    def _populate_table(self, rows: list, total: int) -> None:
        """Fill the table widget with the provided player-stat rows."""
        self._table.setRowCount(0)

        for row_data in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)

            rank = row_data["rank"]
            medal = _RANK_MEDALS.get(rank, "")
            rank_text = f"{medal} {rank}" if medal else str(rank)

            player_name = row_data["name"]
            is_own = row_data.get("is_own", False)
            if is_own:
                player_name = f"★ {player_name}"

            wins_text = str(row_data["wins"])
            losses_text = str(row_data["losses"])
            win_rate_text = f"{row_data['win_rate']:.1f}%"

            for col, text in enumerate(
                [rank_text, player_name, wins_text, losses_text, win_rate_text]
            ):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                if is_own:
                    item.setForeground(QColor(_ACCENT_COLOR))
                self._table.setItem(row, col, item)

        now_str = datetime.now().strftime("%H:%M:%S")
        self._lbl_status.setText(f"Showing top {len(rows)} of {total} players")
        self._lbl_updated.setText(f"Last updated: {now_str}")
        self._btn_refresh.setEnabled(True)
