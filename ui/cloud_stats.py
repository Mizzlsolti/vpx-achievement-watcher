from __future__ import annotations

import html as _html
import os
import json
import threading
import urllib.parse as _urlparse
from datetime import datetime
from typing import Any, List, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QTabWidget, QGroupBox, QComboBox, QLineEdit, QPushButton,
    QMessageBox, QCompleter,
)
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG, QUrl, QStringListModel
from PyQt6.QtGui import QDesktopServices

from cloud_sync import CloudSync
from watcher_core import secure_load_json, _strip_version_from_name, f_achievements_state, p_aweditor, load_json, f_custom_achievements_progress, _is_valid_rom_name
from theme import get_theme_color


class _NoBrowseBrowser(QTextBrowser):
    """QTextBrowser subclass that never attempts to load external HTTP/HTTPS
    URLs as documents.  Without this override Qt prints a noisy warning:
    ``QTextBrowser: No document for https://…`` even when ``setOpenLinks``
    is False, because the base class still calls ``loadResource`` internally
    after emitting ``anchorClicked``.  Returning *None* here suppresses
    both the warning and any attempt to navigate away from the current HTML.
    """

    def loadResource(self, resource_type: int, url: QUrl):  # type: ignore[override]
        if url.scheme() in ("http", "https", "ftp"):
            return None
        return super().loadResource(resource_type, url)


class CloudStatsMixin:
    """
    Mixin for MainWindow that provides the Stats and Cloud-Leaderboard tabs,
    all related HTML-generation helpers, and the session/NVRAM read utilities.
    """

    # ==========================================
    # CHALLENGE RESULTS VIEW
    # ==========================================

    def _update_challenges_results_view(self):
        try:
            html = self._build_challenges_results_html()
            self.ch_results_view.setHtml(html)
        except Exception:
            self.ch_results_view.setHtml("<div style='color:#FF3B30; text-align:center;'>(error while loading results)</div>")

    def _build_challenges_results_html(self) -> str:
        """Build and return the challenge leaderboard HTML (used by both the GUI and the overlay)."""
        hist_dir = os.path.join(self.cfg.BASE, "session_stats", "challenges", "history")
        if not os.path.isdir(hist_dir):
            return "<div style='color:#888; text-align:center; margin-top:20px;'>(no results yet)</div>"

        timed_items = []
        flip_items = []
        heat_items = []
        for fn in os.listdir(hist_dir):
            if not fn.lower().endswith(".json"):
                continue
            fpath = os.path.join(hist_dir, fn)
            data = secure_load_json(fpath, {"results": []}) or {"results": []}
            for it in (data.get("results") or []):
                try:
                    kind = str(it.get("kind", "") or "").lower()
                    if kind not in ("timed", "flip", "heat"):
                        continue
                    rom = str(it.get("rom", "") or "")
                    score = int(it.get("score", 0) or 0)
                    dur_s = int(it.get("duration_sec", 0) or 0)
                    ts = str(it.get("ts", "") or "")
                    
                    diff_str = it.get("difficulty", "")
                    if not diff_str and kind == "flip":
                        tf = int(it.get("target_flips", 0) or 0)
                        if tf > 0:
                            if tf <= 100: diff_str = "Pro"
                            elif tf <= 200: diff_str = "Difficult"
                            elif tf <= 300: diff_str = "Medium"
                            elif tf <= 400: diff_str = "Easy"
                            else: diff_str = f"{tf} Flips"
                        else:
                            diff_str = "-"

                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if dt.tzinfo is not None:
                            dt = dt.astimezone().replace(tzinfo=None)
                    except Exception:
                        dt = datetime.min

                    item = {
                        "rom": rom, 
                        "score": score, 
                        "duration_sec": dur_s, 
                        "_dt": dt, 
                        "difficulty": diff_str,
                    }
                    
                    if kind == "timed":
                        timed_items.append(item)
                    elif kind == "flip":
                        flip_items.append(item)
                    else:
                        heat_items.append(item)
                except Exception:
                    continue

        timed_items.sort(key=lambda x: x.get("_dt") or datetime.min, reverse=True)
        flip_items.sort(key=lambda x: x.get("_dt") or datetime.min, reverse=True)
        heat_items.sort(key=lambda x: x.get("_dt") or datetime.min, reverse=True)

        LIMIT = 30
        timed_items = timed_items[:LIMIT]
        flip_items = flip_items[:LIMIT]
        heat_items = heat_items[:LIMIT]

        def fmt_score(n: int) -> str:
            try:
                return f"{int(n):,d}".replace(",", ".")
            except Exception:
                return str(n)

        _tc_primary = get_theme_color(self.cfg, "primary")
        _tc_accent = get_theme_color(self.cfg, "accent")
        _tc_border = get_theme_color(self.cfg, "border")
        css = f"""
        <style>
          table {{ border-collapse: collapse; margin-top: 5px; }}
          th, td {{ padding: 8px 10px; border-bottom: 1px solid {_tc_border}44; white-space: nowrap; }}
          th {{ background: #1A1A1A; font-weight: bold; color: {_tc_primary}; }}
          td.left {{ color: #FFFFFF; font-weight: bold; }} 
          td.val {{ color: {_tc_accent}; font-weight: bold; }} 
          td.diff {{ color: #AAAAAA; font-style: italic; }} 
          h4 {{ margin: 5px 0 10px 0; color: #FFFFFF; font-size: 1.4em; text-align: left; text-transform: uppercase; letter-spacing: 2px; }}
        </style>
        """

        def tbl(title: str, items: list[dict], is_flip: bool) -> str:
            if is_flip:
                head = "<tr><th align='left'>ROM</th><th align='right'>Difficulty</th><th align='right'>Score</th><th align='right'>Duration</th></tr>"
            else:
                head = "<tr><th align='left'>ROM</th><th align='right'>Score</th><th align='right'>Duration</th></tr>"
            
            if not items:
                cols = 4 if is_flip else 3
                body = f"<tr><td colspan='{cols}' align='center' style='color:#888; border:none; padding-top:20px;'>(no results)</td></tr>"
            else:
                rows = []
                romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
                for it in items:
                    rom = it.get("rom", "")
                    sc = fmt_score(it.get("score", 0))
                    dur = self._fmt_hms(int(it.get("duration_sec", 0)))
                    table_title = _html.escape(romnames.get(rom, ""))

                    if is_flip:
                        diff_label = it.get("difficulty", "-")
                        rows.append(f"<tr><td align='left' class='left' title='{table_title}'>{rom}</td><td align='right' class='diff'>{diff_label}</td><td align='right' class='val'>{sc}</td><td align='right' class='val'>{dur}</td></tr>")
                    else:
                        rows.append(f"<tr><td align='left' class='left' title='{table_title}'>{rom}</td><td align='right' class='val'>{sc}</td><td align='right' class='val'>{dur}</td></tr>")
                body = "".join(rows)
            
            return f"<h4>{title}</h4><table width='100%'>{head}{body}</table>"

        html_timed = tbl("⏳ Timed", timed_items, False)
        html_flip = tbl("🎯 Flip", flip_items, True)
        html_heat = tbl("🔥 Heat", heat_items, False)
        
        return (
            css +
            "<table width='100%' style='border:none; margin-top:5px;'><tr>"
            f"<td valign='top' style='padding-right:10px; width:33%; border:none;'>{html_timed}</td>"
            f"<td valign='top' style='padding:0 10px; width:34%; border:none; border-left:1px solid {_tc_border};'>{html_flip}</td>"
            f"<td valign='top' style='padding-left:10px; width:33%; border:none; border-left:1px solid {_tc_border};'>{html_heat}</td>"
            "</tr></table>"
        )

    # ==========================================
    # TAB 4: RECORDS & STATS
    # ==========================================

    def _build_tab_stats(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.stats_tabs = QTabWidget()

        self.stats_views = {}
        self.stats_views["global"] = QTextBrowser()
        self.stats_tabs.addTab(self.stats_views["global"], "🌍 Global NVRAM Dumps")
        self.stats_views[1] = QTextBrowser()
        self.stats_tabs.addTab(self.stats_views[1], "👤 Player Session Deltas")

        ch_tab = QWidget()
        ch_layout = QVBoxLayout(ch_tab)
        self.ch_results_view = QTextBrowser()
        ch_layout.addWidget(QLabel("<b>Latest Challenge Results</b>"))
        ch_layout.addWidget(self.ch_results_view)
        self.stats_tabs.addTab(ch_tab, "⚔️ Challenge Leaderboards")

        layout.addWidget(self.stats_tabs)
        self._add_tab_help_button(layout, "stats")
        self.main_tabs.addTab(tab, "📊 Records & Stats")
        
        try: self._update_challenges_results_view()
        except Exception: pass

    # ==========================================
    # TAB 5: CLOUD LEADERBOARD
    # ==========================================

    def _build_tab_cloud(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp_controls = QGroupBox("Global Cloud Leaderboard")
        lay_ctrl = QHBoxLayout(grp_controls)
        
        self.cmb_cloud_category = QComboBox()
        self.cmb_cloud_category.addItems(["Achievement Progress", "Timed Challenge", "Flip Challenge", "Heat Challenge"])        
        self.cmb_cloud_category.currentIndexChanged.connect(self._on_cloud_cat_changed)
        
        self.cmb_cloud_diff = QComboBox()
        self.cmb_cloud_diff.addItems(["All Difficulties", "Pro", "Difficult", "Medium", "Easy"])
        self.cmb_cloud_diff.hide() 
        
        self.txt_cloud_rom = QLineEdit()
        self.txt_cloud_rom.setPlaceholderText("Enter Table or ROM Name")
        self.txt_cloud_rom.returnPressed.connect(self._fetch_cloud_leaderboard)

        self._cloud_rom_completer_model = QStringListModel([], self)
        self._cloud_rom_completer = QCompleter(self._cloud_rom_completer_model, self)
        self._cloud_rom_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._cloud_rom_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._cloud_rom_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._cloud_rom_completer.setMaxVisibleItems(12)
        self._cloud_rom_completer.popup().setStyleSheet(
            "QListView {"
            "  background: #222; color: #e0e0e0;"
            f"  border: 1px solid {get_theme_color(self.cfg, 'accent')};"
            f"  selection-background-color: {get_theme_color(self.cfg, 'accent')};"
            "  selection-color: #000;"
            "  font-size: 10pt;"
            "}"
        )
        self.txt_cloud_rom.setCompleter(self._cloud_rom_completer)
        
        self.btn_cloud_fetch = QPushButton("Fetch Highscores ☁️")
        self.btn_cloud_fetch.setStyleSheet(
            f"QPushButton {{ background-color:{get_theme_color(self.cfg, 'primary')}; color:#000000;"
            " font-weight:bold; border:none; border-radius:5px; padding:7px 16px; }"
        )
        self.btn_cloud_fetch.clicked.connect(self._fetch_cloud_leaderboard)
        
        lay_ctrl.addWidget(QLabel("Category:"))
        lay_ctrl.addWidget(self.cmb_cloud_category)
        lay_ctrl.addWidget(self.cmb_cloud_diff)
        lay_ctrl.addWidget(QLabel("Table/ROM:"))
        lay_ctrl.addWidget(self.txt_cloud_rom)
        lay_ctrl.addWidget(self.btn_cloud_fetch)
        layout.addWidget(grp_controls)
        
        self.cloud_view = _NoBrowseBrowser()
        self.cloud_view.setOpenLinks(False)
        self.cloud_view.anchorClicked.connect(self._on_cloud_view_anchor_clicked)
        self.cloud_view.setHtml("<div style='text-align:center; color:#888; margin-top:20px;'>(Enter a ROM and click Fetch)</div>")
        layout.addWidget(self.cloud_view)
        
        self._add_tab_help_button(layout, "cloud")
        self.main_tabs.addTab(tab, "☁️ Cloud")
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, self._refresh_cloud_rom_completer)

    def _refresh_cloud_rom_completer(self):
        """Populate the ROM autocomplete model with all known ROM keys and table names."""
        try:
            romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
            items = sorted(set(list(romnames.keys()) + list(romnames.values())))
            self._cloud_rom_completer_model.setStringList(items)
        except Exception:
            pass

    def _on_cloud_cat_changed(self, idx: int):
        if idx == 2:
            self.cmb_cloud_diff.show()
        else:
            self.cmb_cloud_diff.hide()

    def _on_cloud_view_anchor_clicked(self, url: QUrl):
        """Handle info badge clicks: show VPS table info dialog instead of opening a browser."""
        url_str = url.toString() if isinstance(url, QUrl) else str(url)
        # Unescape HTML entities (e.g. &amp; -> &) that QTextBrowser retains for custom schemes
        url_str = _html.unescape(url_str)
        if url_str.startswith("vpsinfo://"):
            parsed = _urlparse.urlparse(url_str)
            params = _urlparse.parse_qs(parsed.query)
            vps_id = params.get("id", [""])[0]
            table_name = params.get("t", [""])[0]
            breakdown_raw = params.get("breakdown", [""])[0]
            breakdown = None
            if breakdown_raw:
                try:
                    breakdown = json.loads(breakdown_raw)
                except Exception:
                    pass
            try:
                from .vps import CloudProgressVpsInfoDialog
                dlg = CloudProgressVpsInfoDialog(
                    cfg=self.cfg,
                    vps_id=vps_id,
                    table_name=table_name,
                    breakdown=breakdown,
                    parent=self,
                )
                dlg.exec()
            except Exception:
                lines = []
                if table_name:
                    lines.append(f"Table: {table_name}")
                if vps_id:
                    lines.append(f"VPS ID: {vps_id}")
                msg = "\n".join(lines) if lines else "No VPS information available."
                QMessageBox.information(self, "Linked VPS Table", msg)
        elif url_str.startswith("http://") or url_str.startswith("https://"):
            QDesktopServices.openUrl(QUrl(url_str))

    def _fetch_cloud_leaderboard(self):
        cat_index = self.cmb_cloud_category.currentIndex()
        cat_map = {0: "progress", 1: "timed", 2: "flip", 3: "heat"}
        category = cat_map.get(cat_index, "progress")
        rom_input = self.txt_cloud_rom.text().strip().lower()
        selected_diff = self.cmb_cloud_diff.currentText() if category == "flip" else None

        if not rom_input:
            self.cloud_view.setHtml("<div style='color:#FF3B30;'>(Please enter a ROM or Title first)</div>")
            return

        # Resolve title input to ROM key if the input is not an exact ROM match
        rom = rom_input
        try:
            romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
            if rom_input not in romnames:
                for r_key, title in romnames.items():
                    if rom_input in title.lower():
                        rom = r_key
                        break
        except Exception:
            pass
            
        if not self.cfg.CLOUD_URL:
            self.cloud_view.setHtml("<div style='color:#FF3B30;'>(No Firebase URL configured in System Tab!)</div>")
            return

        if not _is_valid_rom_name(rom):
            self.cloud_view.setHtml("<div style='color:#FF3B30;'>(Invalid ROM name — custom achievement tables are not tracked in the cloud)</div>")
            return

        self.cloud_view.setHtml(f"<div style='color:{get_theme_color(self.cfg, 'primary')};'>Fetching data from cloud...</div>")
        
        def _bg_fetch():
            player_ids = CloudSync.fetch_player_ids(self.cfg)
            data = []
            if category == "flip":
                paths = [f"players/{pid}/scores/flip" for pid in player_ids]
                batch = CloudSync.fetch_parallel(self.cfg, paths)
                for path, flip_node in batch.items():
                    if flip_node and isinstance(flip_node, dict):
                        for rom_key, entry in flip_node.items():
                            if rom_key == rom or rom_key.startswith(f"{rom}_"):
                                if entry and isinstance(entry, dict):
                                    data.append(entry)
            elif category == "progress":
                paths = [f"players/{pid}/progress/{rom}" for pid in player_ids]
                batch = CloudSync.fetch_parallel(self.cfg, paths)
                for path in paths:
                    entry = batch.get(path)
                    if entry and isinstance(entry, dict):
                        data.append(entry)
            else:
                paths = [f"players/{pid}/scores/{category}/{rom}" for pid in player_ids]
                batch = CloudSync.fetch_parallel(self.cfg, paths)
                for path in paths:
                    entry = batch.get(path)
                    if entry and isinstance(entry, dict):
                        data.append(entry)

            if data:
                if category == "progress":
                    data.sort(key=lambda x: float(x.get("percentage", 0)), reverse=True)
                else:
                    if category == "flip" and selected_diff != "All Difficulties":
                        filtered_data = []
                        for row in data:
                            diff_str = str(row.get("difficulty", "")).strip()
                            if not diff_str:
                                tf = int(row.get("target_flips", 0) or 0)
                                if tf <= 100: diff_str = "Pro"
                                elif tf <= 200: diff_str = "Difficult"
                                elif tf <= 300: diff_str = "Medium"
                                elif tf <= 400: diff_str = "Easy"
                                else: diff_str = f"{tf} Flips"
                            
                            if diff_str.lower() == selected_diff.lower():
                                filtered_data.append(row)
                        data = filtered_data
                        
                    data.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
                    
            html = self._generate_cloud_html(data, category, rom, selected_diff)
            QMetaObject.invokeMethod(self.cloud_view, "setHtml", Qt.ConnectionType.QueuedConnection, Q_ARG(str, html))
            
        threading.Thread(target=_bg_fetch, daemon=True).start()

    def _generate_cloud_html(self, data: list, category: str, rom: str, selected_diff: str = None, include_info_badges: bool = True) -> str:
        _tc_primary = get_theme_color(self.cfg, "primary")
        _tc_accent = get_theme_color(self.cfg, "accent")
        _tc_border = get_theme_color(self.cfg, "border")
        css = f"""
        <style>
          table {{ border-collapse: collapse; width: 80%; margin: 10px auto; }}
          th, td {{ padding: 10px; border-bottom: 1px solid {_tc_border}44; color: #FFF; text-align: center; vertical-align: middle; }}
          th {{ background: #1A1A1A; color: {_tc_primary}; font-weight: bold; }}
          td.rank {{ font-weight: bold; color: {_tc_accent}; font-size: 1.2em; width: 50px; }}
          td.name {{ font-weight: bold; text-align: left; }}
          td.score {{ color: #00B050; font-weight: bold; font-size: 1.2em; }}
          .title {{ font-size: 1.5em; color: #FFF; text-transform: uppercase; font-weight: bold; text-align: center; margin-bottom: 10px; }}
          .bar-bg {{ background: #222; border-radius: 10px; width: 100%; height: 22px; position: relative; border: 1px solid {_tc_border}; }}
          .bar-text {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; text-align: center; color: #FFF; font-size: 12px; font-weight: bold; line-height: 22px; text-shadow: 1px 1px 2px #000; }}
        </style>
        """
        if not data:
            return f"<div style='text-align:center; color:#888; margin-top:20px;'>No cloud records found for {rom.upper()}</div>"
            
        if category == "progress":
            title_cat = "Achievement Progress"
        elif category == "flip" and selected_diff and selected_diff != "All Difficulties":
            title_cat = f"Flip Challenge ({selected_diff})"
        else:
            title_cat = f"{category.upper()} Challenge"
            
        html = [css, f"<div class='title'>Leaderboard: {rom.upper()} ({title_cat})</div>"]
        
        show_diff_col = (category == "flip" and (not selected_diff or selected_diff == "All Difficulties"))
        
        if category == "progress":
            html.append("<table><tr><th>Rank</th><th style='text-align:left;'>Player</th><th style='width: 50%;'>Progress</th><th>Date</th></tr>")
        elif show_diff_col:
            html.append("<table><tr><th>Rank</th><th style='text-align:left;'>Player</th><th>Difficulty</th><th>Score</th><th>Date</th></tr>")
        else:
            html.append("<table><tr><th>Rank</th><th style='text-align:left;'>Player</th><th>Score</th><th>Date</th></tr>")
        
        def _cloud_info_badge(r: dict) -> str:
            if not include_info_badges:
                return ""
            vps_id = (r.get("vps_id") or "").strip()
            table_name = (r.get("table_name") or "").strip()
            author = (r.get("author") or "").strip()
            version = (r.get("version") or "").strip()
            breakdown = r.get("vps_id_breakdown")
            parts = []
            if table_name:
                parts.append(f"Table: {_html.escape(table_name)}")
            if author:
                parts.append(f"Author: {_html.escape(author)}")
            if version:
                parts.append(f"Version: {_html.escape(version)}")
            if not parts and not vps_id:
                return ""
            tooltip = "&#10;".join(parts) if parts else _html.escape(vps_id)
            params: dict[str, str] = {}
            if table_name:
                params["t"] = table_name
            if author:
                params["a"] = author
            if version:
                params["v"] = version
            if vps_id:
                params["id"] = vps_id
            if breakdown and isinstance(breakdown, dict):
                params["breakdown"] = json.dumps(breakdown, separators=(",", ":"))
            if params:
                safe_url = _html.escape(
                    "vpsinfo://?" + _urlparse.urlencode(params, quote_via=_urlparse.quote),
                    quote=True,
                )
                return (
                    f" <a href='{safe_url}' title='{tooltip}'"
                    " style='text-decoration:none; cursor:pointer;'>ℹ️</a>"
                )
            return f" <span title='{tooltip}' style='cursor:help;'>ℹ️</span>"

        for i, row in enumerate(data):
            rank = i + 1
            name = _html.escape(str(row.get("name", "Unknown")))
            ts = row.get("ts", "")[:10]
            medal = "🏆" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"

            # Badge icon next to player name
            selected_badge_id = str(row.get("selected_badge") or "").strip()
            # For the current player's own row, override with the locally stored badge so
            # the display is immediately current after a badge change (before cloud sync).
            try:
                own_name = str(self.cfg.OVERLAY.get("player_name", "") or "").strip()
                if own_name and str(row.get("name") or "").strip() == own_name:
                    _local_state = secure_load_json(f_achievements_state(self.cfg), {}) or {}
                    _local_badge = str(_local_state.get("selected_badge") or "").strip()
                    if _local_badge:
                        selected_badge_id = _local_badge
            except Exception:
                pass
            badge_icon = ""
            if selected_badge_id:
                try:
                    from badges import BADGE_LOOKUP
                    bdef = BADGE_LOOKUP.get(selected_badge_id)
                    if bdef:
                        badge_icon = f" <span title='{_html.escape(bdef[2])}' style='font-size:1em;'>{bdef[1]}</span>"
                except Exception:
                    pass
            
            if category == "progress":
                badge = _cloud_info_badge(row)
                unlocked = int(row.get('unlocked', 0))
                total = int(row.get('total', 1))
                pct = float(row.get('percentage', 0))
                
                bar = f"""
                <div class='bar-bg'>
                    <div style='background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_tc_accent}, stop:1 #FFD700); width: {pct}%; height: 100%; border-radius: 9px;'></div>
                    <div class='bar-text'>{unlocked} / {total} ({pct}%)</div>
                </div>
                """
                html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}{badge_icon}{badge}</td><td>{bar}</td><td>{ts}</td></tr>")
            elif category == "flip":
                badge = _cloud_info_badge(row)
                score = f"{int(row.get('score', 0)):,d}".replace(",", ".")
                if show_diff_col:
                    diff_str = row.get("difficulty", "")
                    if not diff_str:
                        tf = int(row.get("target_flips", 0))
                        if tf > 0:
                            if tf <= 100: diff_str = "Pro"
                            elif tf <= 200: diff_str = "Difficult"
                            elif tf <= 300: diff_str = "Medium"
                            elif tf <= 400: diff_str = "Easy"
                            else: diff_str = f"{tf} Flips"
                        else:
                            diff_str = "-"
                    html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}{badge_icon}{badge}</td><td style='color:#AAAAAA; font-style:italic;'>{diff_str}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
                else:
                    html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}{badge_icon}{badge}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
            else:
                badge = _cloud_info_badge(row)
                score = f"{int(row.get('score', 0)):,d}".replace(",", ".")
                html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}{badge_icon}{badge}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
            
        html.append("</table>")
        return "".join(html)

    # ==========================================
    # STATS HTML HELPERS
    # ==========================================

    def update_stats(self):
        def _set_html_preserve_scroll(browser, html):
            try:
                sb = browser.verticalScrollBar()
                old_val = sb.value()
                old_max = max(1, sb.maximum())
                at_bottom_before = (old_val >= old_max - 2)
                ratio = old_val / old_max if old_max > 0 else 0.0
                browser.setHtml(html)
                new_max = max(1, sb.maximum())
                if at_bottom_before:
                    sb.setValue(sb.maximum())
                else:
                    new_val = int(round(ratio * new_max))
                    sb.setValue(max(0, min(new_val, new_max)))
            except Exception:
                try:
                    browser.setHtml(html)
                except Exception:
                    pass

        try:
            if "global" in self.stats_views:
                html_global = self._gui_stats_global_html()
                _set_html_preserve_scroll(self.stats_views["global"], html_global)
        except Exception:
            pass

        try:
            if 1 in self.stats_views:
                html_p1 = self._gui_stats_player1_html()
                _set_html_preserve_scroll(self.stats_views[1], html_p1)
        except Exception:
            pass

    def _resolve_custom_table_title(self, rom: str) -> str:
        """Return the display title for a custom (no-ROM) table.

        When ``rom`` is empty or "Unknown", checks whether the watcher's
        ``current_table`` has a matching ``.custom.json`` file and extracts
        the table name from ``table_file``.  Returns an empty string when no
        custom table can be identified.
        """
        if rom not in ("Unknown", ""):
            return ""
        try:
            current_table = str(getattr(self.watcher, "current_table", "") or "").strip()
            if not current_table:
                return ""
            _cjp = os.path.join(p_aweditor(self.cfg), f"{current_table}.custom.json")
            if not os.path.isfile(_cjp):
                return ""
            _cd = load_json(_cjp, {}) or {}
            _tf = str(_cd.get("table_file") or "").strip()
            if _tf.lower().endswith(".vpx"):
                return _tf[:-4]
            return _tf or current_table
        except Exception:
            return ""

    def _gui_stats_global_html(self) -> str:
        _tc_primary = get_theme_color(self.cfg, "primary")
        _tc_accent = get_theme_color(self.cfg, "accent")
        style = f"""
        <style>
          table {{ border-collapse: collapse; margin-top: 10px; }}
          th, td {{ padding: 0.2em 0.5em; border-bottom: 1px solid #444; white-space: nowrap; color: #E0E0E0; }}
          th {{ text-align: left; background: #1A1A1A; font-weight: bold; color: {_tc_primary}; }}
          th.right {{ text-align: right; }}
          td.val {{ text-align: right; font-weight: bold; color: {_tc_accent}; }}
          .meta {{ color: #888888; margin-bottom: 0.8em; font-size: 1.1em; font-weight: bold; text-align: center; }}
          .rom-title {{ font-size: 1.6em; font-weight: bold; color: #FFFFFF; text-align: center; margin-bottom: 5px; text-transform: uppercase; }}
        </style>
        """
        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            pass

        summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
        
        if not rom and os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rom = data.get("rom", "")
            except Exception:
                pass

        if not rom:
            rom = "Unknown"

        romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
        table_title = _strip_version_from_name(romnames.get(rom, ""))

        # For custom (no-ROM) tables, look up the display name from the .custom.json
        if not table_title:
            table_title = self._resolve_custom_table_title(rom)

        audits, _, _ = self.watcher.read_nvram_audits_with_autofix(rom)

        if not audits and os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("rom") == rom:
                        audits = data.get("end_audits", {})
            except Exception:
                pass

        html_lines = ["<div align='center'>"]
        html_lines.append(f"<div class='rom-title'>ROM: {rom}</div>")
        if table_title:
            html_lines.append(f"<div style='font-size:1.2em; color:{_tc_primary}; font-weight:bold; text-align:center; margin-bottom:5px;'>{_html.escape(table_title)}</div>")
        html_lines.append(f"<div class='meta'>All global values</div>")

        if not audits:
            html_lines.append(f"<div style='color:#888; margin-top: 15px;'>(No readable NVRAM data for {rom} found...)</div>")
        else:
            COLUMNS = 5
            html_lines.append("<table align='center'><tr>")
            for _ in range(COLUMNS):
                html_lines.append("<th>Field / Name</th><th class='right'>Value</th>")
            html_lines.append("</tr>")

            items = sorted(list(audits.items()), key=lambda x: str(x[0]).lower())

            for i in range(0, len(items), COLUMNS):
                html_lines.append("<tr>")
                for j in range(COLUMNS):
                    if i + j < len(items):
                        key, val = items[i + j]
                        if isinstance(val, int):
                            val_str = f"{val:,}".replace(",", ".")
                        else:
                            val_str = str(val)
                        html_lines.append(f"<td>{key}</td><td class='val'>{val_str}</td>")
                    else:
                        html_lines.append("<td></td><td></td>")
                html_lines.append("</tr>")

            html_lines.append("</table>")
            
        html_lines.append("</div>")
        return style + "".join(html_lines)

    def _gui_stats_player1_html(self) -> str:
        def esc(x) -> str:
            return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        _tc_primary = get_theme_color(self.cfg, "primary")
        _tc_accent = get_theme_color(self.cfg, "accent")
        style = f"""
        <style>
          table {{ border-collapse: collapse; margin-top: 10px; }}
          th, td {{ padding: 0.2em 0.5em; border-bottom: 1px solid #444; white-space: nowrap; color: #E0E0E0; }}
          th {{ text-align: left; background: #1A1A1A; font-weight: bold; color: {_tc_primary}; }}
          th.right {{ text-align: right; }}
          td.val {{ text-align: right; font-weight: bold; color: {_tc_accent}; }}
          .meta {{ color: #888888; margin-bottom: 0.8em; font-size: 1.1em; font-weight: bold; text-align: center; }}
          .rom-title {{ font-size: 1.6em; font-weight: bold; color: #FFFFFF; text-align: center; margin-bottom: 5px; text-transform: uppercase; }}
        </style>
        """

        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            pass

        summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
        if not rom and os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rom = data.get("rom", "")
            except Exception:
                pass
                
        if not rom:
            rom = "Unknown"

        romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
        table_title = _strip_version_from_name(romnames.get(rom, ""))

        # For custom (no-ROM) tables, look up the display name from the .custom.json
        if not table_title:
            table_title = self._resolve_custom_table_title(rom)

        active_deltas = {}
        playtime_str = ""

        try:
            if hasattr(self, "watcher") and getattr(self.watcher, "game_active", False):
                player_data = self.watcher.players.get(1, {})
                live_deltas = player_data.get("session_deltas", {})
                play_sec = int(player_data.get("active_play_seconds", 0.0))
                for k, v in live_deltas.items():
                    if int(v) > 0:
                        active_deltas[k] = int(v)
                if play_sec > 0:
                    m, s = divmod(play_sec, 60)
                    playtime_str = f"{m}m {s}s"
        except Exception:
            pass

        if not active_deltas:
            try:
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        p_list = data.get("players", [])
                        if p_list:
                            p1 = p_list[0]
                            saved_deltas = p1.get("deltas", {})
                            for k, v in saved_deltas.items():
                                if int(v) > 0:
                                    active_deltas[k] = int(v)
                            play_sec = int(p1.get("playtime_sec", 0))
                            if play_sec > 0:
                                m, s = divmod(play_sec, 60)
                                playtime_str = f"{m}m {s}s"
            except Exception:
                pass

        html_lines = ["<div align='center'>"]
        html_lines.append(f"<div class='rom-title'>ROM: {esc(rom)}</div>")
        if table_title:
            html_lines.append(f"<div style='font-size:1.2em; color:{_tc_primary}; font-weight:bold; text-align:center; margin-bottom:5px;'>{esc(table_title)}</div>")

        if playtime_str:
            html_lines.append(f"<div class='meta'>Playtime: {esc(playtime_str)} &nbsp;&nbsp;|&nbsp;&nbsp; Actions from session</div>")
        else:
            html_lines.append(f"<div class='meta'>Actions from session</div>")

        if not active_deltas:
            html_lines.append("<div style='color:#888; margin-top: 15px;'>(No actions registered in this/last session yet...)</div>")
        else:
            COLUMNS = 3
            html_lines.append("<table align='center'><tr>")
            for _ in range(COLUMNS):
                html_lines.append("<th>Action</th><th class='right'>Count</th>")
            html_lines.append("</tr>")

            items = sorted(list(active_deltas.items()), key=lambda x: str(x[0]).lower())

            for i in range(0, len(items), COLUMNS):
                html_lines.append("<tr>")
                for j in range(COLUMNS):
                    if i + j < len(items):
                        key, value = items[i + j]
                        val_str = f"{value:,}".replace(",", ".")
                        html_lines.append(f"<td>{esc(key)}</td><td class='val'>+{val_str}</td>")
                    else:
                        html_lines.append("<td></td><td></td>")
                html_lines.append("</tr>")

            html_lines.append("</table>")
            
        html_lines.append("</div>")

        return style + "".join(html_lines)

    # ==========================================
    # SESSION / NVRAM READ HELPERS
    # ==========================================

    def _extract_block(self, text: str, header: str) -> str:
        lines = text.splitlines()
        block = []
        capture = False
        for line in lines:
            s = line.strip()
            if s.startswith(f"=== {header} ==="):
                capture = True
                block = []
                continue
            if capture and s.startswith("===") and not s.startswith(f"=== {header} ==="):
                break
            if capture:
                block.append(line)

        if not block:
            return f"<p>No data found for {header}</p>"

        style = """
        <style>
        table { border-collapse: collapse; }
        .inner td { padding: 3px 6px; white-space:nowrap; }
        .inner td:first-child { text-align: left; }
        .inner td:last-child { text-align: right; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        h3 { margin-top: 12px; }
        h4 { margin-top: 10px; margin-bottom: 4px; border-bottom: 1px solid #ccc; }
        </style>
        """
        html = style + f"<h3>{header}</h3>"
        current_section = None
        rows: List[Tuple[str, str]] = []
        skip_section = False

        def flush():
            nonlocal html, rows, current_section
            if rows:
                sec_title = current_section or ""
                if sec_title:
                    html += f"<h4>{sec_title}</h4>"
                html += self._render_multi_columns(rows, 4)
                rows = []
        for raw in block:
            stripped = raw.rstrip()
            if not stripped:
                continue
            st = stripped.strip()
            if st.endswith(":"):
                tag = st[:-1].strip()
                flush()
                low = tag.lower()
                if low in ("achievements (unlocked)", "session achievements"):
                    current_section = None
                    skip_section = True
                else:
                    current_section = tag
                    skip_section = False
                continue
            if skip_section:
                continue
            parts = st.split()
            if len(parts) >= 2:
                key = " ".join(parts[:-1])
                val = parts[-1]
                rows.append((key, val))
            else:
                rows.append((st, ""))
        flush()
        return html

    def _read_latest_session_txt(self) -> str:
        return ""

    def _read_latest_session_txt_path(self) -> str:
        return ""

    def _read_raw_nvram_for_current_or_last_rom(self) -> tuple[str, bytes]:
        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            rom = ""

        if not rom:
            return "", b""

        nv_path = os.path.join(self.cfg.NVRAM_DIR, f"{rom}.nv")
        try:
            with open(nv_path, "rb") as f:
                return rom, f.read()
        except Exception:
            return rom, b""

    def _build_global_parsed_nvram_html(self) -> str:
        style = """
        <style>
          table { border-collapse: collapse; }
          th, td { padding: 0.2em 0.5em; border-bottom: 1px solid rgba(255,255,255,0.15); white-space: nowrap; }
          th { text-align: left; background: rgba(255,255,255,0.05); }
          th.right { text-align: right; }
          td.val { text-align: right; font-weight: bold; color: #FFFFFF; }
          .meta { color: rgba(255,255,255,0.6); margin-bottom: 0.5em; }
        </style>
        """
        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            pass

        if not rom:
            return style + "<div align='center'>(Global Snapshot: ROM unknown)</div>"

        romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
        table_title = _strip_version_from_name(romnames.get(rom, ""))

        audits, _, _ = self.watcher.read_nvram_audits_with_autofix(rom)

        if not audits:
            return style + f"<div align='center'>(Global Snapshot: No readable NVRAM data found for ROM <b>{rom}</b>)</div>"

        title_line = ""
        if table_title:
            title_line = (
                f"<div style='font-size:1.4em; font-weight:bold; color:#FFFFFF; "
                f"text-align:center; margin-bottom:3px; text-transform:uppercase;'>"
                f"{_html.escape(table_title)}</div>"
            )
        meta = (
            f"{title_line}"
            f"<div class='meta'><b>ROM:</b> {rom} &nbsp;&nbsp; <b>All NVRAM values</b></div>"
        )
        
        COLUMNS = 5
        
        rows = ["<tr>"]
        for _ in range(COLUMNS):
            rows.append("<th>Field / Name</th><th class='right'>Value</th>")
        rows.append("</tr>")
        
        items = []
        for key in sorted(audits.keys(), key=lambda x: str(x).lower()):
            val = audits[key]
            if isinstance(val, int):
                val_str = f"{val:,}".replace(",", ".")
            else:
                val_str = str(val)
            items.append((key, val_str))

        for i in range(0, len(items), COLUMNS):
            rows.append("<tr>")
            for j in range(COLUMNS):
                if i + j < len(items):
                    key, val_str = items[i + j]
                    rows.append(f"<td>{key}</td><td class='val'>{val_str}</td>")
                else:
                    rows.append("<td></td><td></td>")
            rows.append("</tr>")

        return style + f"<div align='center'>{meta}<table align='center'>" + "".join(rows) + "</table></div>"

    @staticmethod
    def _render_multi_columns(rows: List[Tuple[str, str]], columns: int) -> str:
        if columns <= 0:
            columns = 1
        per_col = (len(rows) + columns - 1) // columns
        html = "<table width='100%'><tr>"
        for c in range(columns):
            start = c * per_col
            end = start + per_col
            col_rows = rows[start:end]
            html += "<td valign='top'><table class='inner'>"
            for k, v in col_rows:
                html += f"<tr><td>{k}</td><td>{v}</td></tr>"
            html += "</table></td>"
        html += "</tr></table>"
        return html

    def _parse_player_snapshot(self, content: str, pid: int) -> dict:
        out = {"playtime": "", "achievements": [], "deltas": []}
        if not content:
            return out
        lines = content.splitlines()
        in_block = False
        in_achs = False
        in_deltas = False

        for raw in lines:
            s = raw.rstrip()  
            st = s.strip()
            if st.startswith(f"=== Player {pid} Snapshot ==="):
                in_block = True
                in_achs = False
                in_deltas = False
                continue
            if in_block and st.startswith("===") and not st.startswith(f"=== Player {pid} Snapshot ==="):
                break
            if not in_block:
                continue
            if st.lower().startswith("playtime:"):
                out["playtime"] = st.partition(":")[2].strip()
                continue
            if st.endswith(":"):
                t = st[:-1].strip().lower()
                in_achs = (t == "session achievements")
                in_deltas = (t == "session deltas")
                continue
            if in_achs and st:
                if (s.startswith("  ") or s.startswith("\t")):
                    out["achievements"].append(st)
                continue
            if in_deltas and st:
                if (s.startswith("  ") or s.startswith("\t")):
                    parts = st.split()
                    if len(parts) >= 2:
                        key = " ".join(parts[:-1])
                        val = parts[-1]
                        try:
                            ival = int(val)
                            if ival > 0:
                                out["deltas"].append((key, val))
                        except Exception:
                            pass
                continue
        return out

    def _build_player_snapshots_html(self, content: str = "") -> str:
        """
        SINGLE-PLAYER MODE:
        Shows Player 1 snapshot (only changes > 0). 
        Fetches live data or, if the game is closed, persistently loads from session_latest.summary.json.
        """
        def esc(x: Any) -> str:
            return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        style = """
        <style>
          table { border-collapse: collapse; margin-top: 10px; }
          th, td { padding: 0.2em 0.5em; border-bottom: 1px solid rgba(255,255,255,0.15); white-space: nowrap; }
          th { text-align: left; background: rgba(255,255,255,0.05); }
          th.right { text-align: right; }
          td.val { text-align: right; font-weight: bold; color: #00B050; }
          .meta { color: rgba(255,255,255,0.6); margin-bottom: 0.5em; font-size: 0.9em; }
        </style>
        """

        active_deltas = {}
        playtime_str = ""

        try:
            if hasattr(self, "watcher") and getattr(self.watcher, "game_active", False):
                player_data = self.watcher.players.get(1, {})
                live_deltas = player_data.get("session_deltas", {})
                play_sec = int(player_data.get("active_play_seconds", 0.0))
                for k, v in live_deltas.items():
                    if int(v) > 0:
                        active_deltas[k] = int(v)
                if play_sec > 0:
                    m, s = divmod(play_sec, 60)
                    playtime_str = f"{m}m {s}s"
        except Exception:
            pass

        if not active_deltas:
            try:
                summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        p_list = data.get("players", [])
                        if p_list:
                            p1 = p_list[0]
                            saved_deltas = p1.get("deltas", {})
                            for k, v in saved_deltas.items():
                                if int(v) > 0:
                                    active_deltas[k] = int(v)
                            
                            play_sec = int(p1.get("playtime_sec", 0))
                            if play_sec > 0:
                                m, s = divmod(play_sec, 60)
                                playtime_str = f"{m}m {s}s"
            except Exception:
                pass

        html_lines = []
        html_lines.append("<div align='center'>")
        
        if playtime_str:
            html_lines.append(f"<div class='meta'>Playtime: {esc(playtime_str)} &nbsp;&nbsp;|&nbsp;&nbsp; Actions from the (last) session</div>")

        if not active_deltas:
            html_lines.append("<div style='color:#888; margin-top: 15px;'>(No actions registered in this/last session yet...)</div>")
        else:
            COLUMNS = 3
            html_lines.append("<table align='center'><tr>")
            for _ in range(COLUMNS):
                html_lines.append("<th>Action</th><th class='right'>Count</th>")
            html_lines.append("</tr>")

            items = sorted(list(active_deltas.items()), key=lambda x: str(x[0]).lower())

            for i in range(0, len(items), COLUMNS):
                html_lines.append("<tr>")
                for j in range(COLUMNS):
                    if i + j < len(items):
                        key, value = items[i + j]
                        val_str = f"{value:,}".replace(",", ".")
                        html_lines.append(f"<td>{esc(key)}</td><td class='val'>+{val_str}</td>")
                    else:
                        html_lines.append("<td></td><td></td>")
                html_lines.append("</tr>")

            html_lines.append("</table>")
            
        html_lines.append("</div>")

        return style + "".join(html_lines)
