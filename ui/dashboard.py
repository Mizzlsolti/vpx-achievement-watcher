"""Dashboard-tab mixin: Dashboard build, notification feed, notification generation,
session-end hook, cloud rank/beaten polling, and update check."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QScrollArea,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, Q_ARG, QMetaObject

import core.notifications as _notif
from core.cloud_sync import CloudSync
from core.watcher_core import _strip_version_from_name, _is_valid_rom_name
from .dialogs import AchievementBeatenDialog


def _parse_version(v_str):
    """Parse a version string like '2.5' or '2.5.1' into a comparable tuple of ints."""
    try:
        return tuple(map(int, str(v_str).split('.')))
    except Exception:
        return (0,)


class DashboardMixin:
    """Mixin that provides the Dashboard tab, notification feed UI, notification
    generation, session-end hook, cloud rank/beaten polling, and update check.

    Expects the host class to provide:
        self.cfg                – AppConfig instance
        self.watcher            – Watcher instance
        self.main_tabs          – QTabWidget (main tab bar)
        self._add_tab_help_button(layout, key)
        self._restart_watcher() – slot
        self.quit_all()         – slot
        self.CURRENT_VERSION    – str
        self._HIGHSCORE_POLL_INTERVAL_MS – int
        self._NOTIF_COOLDOWN_HOURS       – int
        self.maps_table         – QTableWidget (Available Maps tab)
        self.txt_cloud_rom      – QLineEdit (Cloud tab)
        self._fetch_cloud_leaderboard()  – method
        self.system_subtabs     – QTabWidget (System sub-tabs, optional)
    """

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
            "QPushButton { background-color: #3a1a1a; color: #CC4444; border: 1px solid #5a2a2a; "
            "border-radius: 3px; font-size: 8pt; padding: 0 6px; }"
            "QPushButton:hover { background-color: #5a2a2a; }"
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

        # ── 📋 Setup Status ────────────────────────────────────────────────────
        grp_setup = QGroupBox("📋 Setup Status")
        lay_setup = QVBoxLayout(grp_setup)
        lay_setup.setContentsMargins(8, 8, 8, 8)
        lay_setup.setSpacing(4)

        # Row helper: (check_label, link_button_or_None)
        self._setup_check_rows: list[tuple[QLabel, QPushButton | None]] = []

        for _ in range(5):
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel("")
            lbl.setStyleSheet("font-size: 9pt; padding: 1px 0;")
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            row.addWidget(lbl)
            row.addStretch(1)
            btn = QPushButton("")
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { color: #FF7F00; font-size: 9pt; border: none; padding: 0 2px;"
                " text-decoration: none; background: transparent; }"
                "QPushButton:hover { text-decoration: underline; }"
            )
            btn.hide()
            row.addWidget(btn)
            lay_setup.addLayout(row)
            self._setup_check_rows.append((lbl, btn))

        self._lbl_setup_all_good = QLabel("✅ All set! You're ready to play.")
        self._lbl_setup_all_good.setStyleSheet(
            "color: #00C853; font-size: 9pt; font-weight: bold; padding: 2px 0;"
        )
        self._lbl_setup_all_good.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_setup_all_good.hide()
        lay_setup.addWidget(self._lbl_setup_all_good)

        self._lbl_setup_info = QLabel(
            "ℹ️ All checks must pass for Duels, Tournaments and Leaderboards to work."
        )
        self._lbl_setup_info.setStyleSheet(
            "color: #888; font-size: 8pt; font-style: italic; padding: 2px 0;"
        )
        self._lbl_setup_info.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_setup_info.setWordWrap(True)
        lay_setup.addWidget(self._lbl_setup_info)

        layout.addWidget(grp_setup)

        grp_actions = QGroupBox("Quick Actions")
        lay_actions = QHBoxLayout(grp_actions)
        self.btn_restart = QPushButton("Restart Engine")
        self.btn_restart.setStyleSheet(
            "QPushButton { background-color:#008040; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:7px 16px; }"
        )
        self.btn_restart.clicked.connect(self._restart_watcher)
        self.btn_minimize = QPushButton("Minimize to Tray")
        self.btn_minimize.setStyleSheet(
            "QPushButton { background-color:#005c99; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:7px 16px; }"
        )
        self.btn_minimize.clicked.connect(self.hide)
        self.btn_quit = QPushButton("Quit GUI")
        self.btn_quit.setStyleSheet(
            "QPushButton { background-color:#8a2525; color:#FFFFFF; font-weight:bold;"
            " border:none; border-radius:5px; padding:7px 16px; }"
        )
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

        # Refresh setup checklist
        try:
            self._refresh_setup_checklist()
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
        #   5=Progress, 6=Score Duels, 7=Available Maps, 8=Cloud, 9=System)
        # Only tabs used as notification action_tab destinations are listed here.
        _TAB_MAP = {
            "cloud": 8,
            "system": 9,
            "available_maps": 7,
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

    # ── Setup checklist ──────────────────────────────────────────────────────

    def _refresh_setup_checklist(self) -> None:
        """Update the Setup Status GroupBox to reflect current configuration state."""
        if not hasattr(self, "_setup_check_rows"):
            return

        # Tab indices matching addTab call order in the main window.
        _IDX_SYSTEM = 9
        _IDX_MAPS = 7

        # ── Check 1: Player Name ──────────────────────────────────────────────
        pname = str(self.cfg.OVERLAY.get("player_name", "Player") or "").strip()
        check1_ok = bool(pname and pname.lower() != "player")

        # ── Check 2: Cloud Sync ───────────────────────────────────────────────
        cloud_ok = bool(
            getattr(self.cfg, "CLOUD_ENABLED", False)
            and str(getattr(self.cfg, "CLOUD_URL", "") or "").strip()
        )

        # ── Check 3: VPS-ID assignments ───────────────────────────────────────
        try:
            from ui.vps import _load_vps_mapping
            mapping = _load_vps_mapping(self.cfg)
            vps_count = len(mapping)
        except Exception:
            vps_count = 0
        check3_ok = vps_count > 0

        # ── Check 4: Available Maps loaded ────────────────────────────────────
        maps_cache = getattr(self, "_all_maps_cache", None)
        maps_ok = isinstance(maps_cache, list) and len(maps_cache) > 0
        maps_count = len(maps_cache) if maps_ok else 0

        # ── Check 5: Overlay positions saved ─────────────────────────────────
        _OVERLAY_CHECKS = [
            ("overlay_pos_saved",    None),
            ("ach_toast_saved",      None),
            ("notifications_saved",  None),
            ("duel_overlay_saved",   None),
            ("status_overlay_saved", "status_overlay_enabled"),
        ]
        total_relevant = 0
        total_configured = 0
        for saved_key, enabled_key in _OVERLAY_CHECKS:
            if enabled_key and not bool(self.cfg.OVERLAY.get(enabled_key, True)):
                continue
            total_relevant += 1
            if bool(self.cfg.OVERLAY.get(saved_key, False)):
                total_configured += 1
        overlay_all_ok = (total_configured == total_relevant)

        all_ok = check1_ok and cloud_ok and check3_ok and maps_ok and overlay_all_ok

        # Hide individual rows and show "all good" label when everything passes.
        for lbl, btn in self._setup_check_rows:
            lbl.setVisible(not all_ok)
            if btn is not None:
                btn.setVisible(False)

        self._lbl_setup_all_good.setVisible(all_ok)
        self._lbl_setup_info.setVisible(not all_ok)

        if all_ok:
            return

        _GREEN = "color: #00C853; font-size: 9pt; padding: 1px 0;"
        _RED   = "color: #FF3B30; font-size: 9pt; padding: 1px 0;"

        def _apply_row(idx: int, ok: bool, ok_text: str, fail_text: str,
                       link_text: str | None, link_target: int | None) -> None:
            lbl, btn = self._setup_check_rows[idx]
            if ok:
                lbl.setText(f"✅ {ok_text}")
                lbl.setStyleSheet(_GREEN)
                if btn is not None:
                    btn.hide()
            else:
                lbl.setText(f"❌ {fail_text}")
                lbl.setStyleSheet(_RED)
                if btn is not None and link_text and link_target is not None:
                    btn.setText(f"[→ {link_text}]")
                    try:
                        btn.clicked.disconnect()
                    except Exception:
                        pass
                    _target = link_target
                    btn.clicked.connect(lambda _=False, t=_target: self.main_tabs.setCurrentIndex(t))
                    btn.show()
                elif btn is not None:
                    btn.hide()

        _apply_row(
            0, check1_ok,
            f'Player Name set: "{pname}"',
            "Player Name not set",
            "Set Name", _IDX_SYSTEM,
        )
        _apply_row(
            1, cloud_ok,
            "Cloud Sync enabled",
            "Cloud Sync disabled",
            "Enable", _IDX_SYSTEM,
        )
        _apply_row(
            2, check3_ok,
            f"{vps_count} table{'s' if vps_count != 1 else ''} with VPS-ID assigned",
            "No VPS-IDs assigned",
            None, None,
        )
        _apply_row(
            3, maps_ok,
            f"{maps_count} map{'s' if maps_count != 1 else ''} loaded",
            "Available Maps not loaded",
            "Load Maps", _IDX_MAPS,
        )

        # ── Row 5: Overlays ───────────────────────────────────────────────
        _IDX_APPEARANCE = 2
        lbl5, btn5 = self._setup_check_rows[4]
        if overlay_all_ok:
            lbl5.setText("✅ All overlays configured")
            lbl5.setStyleSheet(_GREEN)
            if btn5 is not None:
                btn5.hide()
        else:
            _YELLOW = "color: #FFA500; font-size: 9pt; padding: 1px 0;"
            if total_configured > 0:
                lbl5.setText(f"⚠️ {total_configured}/{total_relevant} overlays configured")
                lbl5.setStyleSheet(_YELLOW)
            else:
                lbl5.setText("❌ Overlays not configured")
                lbl5.setStyleSheet(_RED)
            if btn5 is not None:
                btn5.setText("[→ Configure]")
                try:
                    btn5.clicked.disconnect()
                except Exception:
                    pass
                btn5.clicked.connect(
                    lambda _=False, t=_IDX_APPEARANCE: self.main_tabs.setCurrentIndex(t)
                )
                btn5.show()

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
                self.main_tabs.setCurrentIndex(9)  # System tab
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
                self.main_tabs.setCurrentIndex(8)  # Cloud tab
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
                self.main_tabs.setCurrentIndex(7)  # Available Maps tab
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
            "cloud": 8,
            "system": 9,
            "available_maps": 7,
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
        """Clear all notifications."""
        _notif.clear_all(self.cfg)
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
        # Custom achievement tables have non-standard ROM names; skip cloud fetch.
        if not _is_valid_rom_name(rom):
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
                    # Custom achievement tables have non-standard names; skip cloud fetch.
                    if not _is_valid_rom_name(rom):
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

    def _check_for_updates(self):
        """Startup update check: uses GitHub Releases API, adds Dashboard notification only (no popup)."""

        def _task():
            try:
                from core.watcher_core import _fetch_json_url

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
