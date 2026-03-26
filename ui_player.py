from __future__ import annotations

import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QProgressBar, QTextBrowser, QVBoxLayout, QWidget,
)

from watcher_core import (
    BADGE_DEFINITIONS, CloudSync, LEVEL_TABLE, PRESTIGE_THRESHOLD,
    compute_player_level,
)


class PlayerMixin:
    """Mixin for MainWindow that provides the Player tab and all related helpers."""

    # ==========================================
    # TAB: PLAYER
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
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, self._refresh_level_display)

    # ==========================================
    # PLAYER HELPERS
    # ==========================================

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
