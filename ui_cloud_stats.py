from __future__ import annotations

import html as _html
import os
import json
import threading
from datetime import datetime
from typing import Any, List, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QTabWidget, QGroupBox, QComboBox, QLineEdit, QPushButton,
)
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG

from watcher_core import CloudSync, secure_load_json


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
        hist_dir = os.path.join(self.cfg.BASE, "challenges", "history")
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

        css = """
        <style>
          table { border-collapse: collapse; margin-top: 5px; }
          th, td { padding: 8px 10px; border-bottom: 1px solid #444; white-space: nowrap; }
          th { background: #1A1A1A; font-weight: bold; color: #00E5FF; }
          td.left { color: #FFFFFF; font-weight: bold; } 
          td.val { color: #FF7F00; font-weight: bold; } 
          td.diff { color: #AAAAAA; font-style: italic; } 
          h4 { margin: 5px 0 10px 0; color: #FFFFFF; font-size: 1.4em; text-align: left; text-transform: uppercase; letter-spacing: 2px; }
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
            f"<td valign='top' style='padding:0 10px; width:34%; border:none; border-left:1px solid #555;'>{html_flip}</td>"
            f"<td valign='top' style='padding-left:10px; width:33%; border:none; border-left:1px solid #555;'>{html_heat}</td>"
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
        self.txt_cloud_rom.setPlaceholderText("Enter ROM Name (e.g. afm_113b)")
        
        self.btn_cloud_fetch = QPushButton("Fetch Highscores ☁️")
        self.btn_cloud_fetch.setStyleSheet("background:#00E5FF; color:black; font-weight:bold;")
        self.btn_cloud_fetch.clicked.connect(self._fetch_cloud_leaderboard)
        
        lay_ctrl.addWidget(QLabel("Category:"))
        lay_ctrl.addWidget(self.cmb_cloud_category)
        lay_ctrl.addWidget(self.cmb_cloud_diff)
        lay_ctrl.addWidget(QLabel("ROM:"))
        lay_ctrl.addWidget(self.txt_cloud_rom)
        lay_ctrl.addWidget(self.btn_cloud_fetch)
        layout.addWidget(grp_controls)
        
        self.cloud_view = QTextBrowser()
        self.cloud_view.setHtml("<div style='text-align:center; color:#888; margin-top:20px;'>(Enter a ROM and click Fetch)</div>")
        layout.addWidget(self.cloud_view)
        
        self.main_tabs.addTab(tab, "☁️ Cloud")

    def _on_cloud_cat_changed(self, idx: int):
        if idx == 2:
            self.cmb_cloud_diff.show()
        else:
            self.cmb_cloud_diff.hide()

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

        self.cloud_view.setHtml("<div style='color:#00E5FF;'>Fetching data from cloud...</div>")
        
        def _bg_fetch():
            if category == "progress":
                data = CloudSync.fetch_data(self.cfg, f"progress/{rom}")
                if data:
                    data.sort(key=lambda x: float(x.get("percentage", 0)), reverse=True)
            else:
                data = CloudSync.fetch_data(self.cfg, f"scores/{category}/{rom}")
                if data:
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

    def _generate_cloud_html(self, data: list, category: str, rom: str, selected_diff: str = None) -> str:
        css = """
        <style>
          table { border-collapse: collapse; width: 80%; margin: 10px auto; }
          th, td { padding: 10px; border-bottom: 1px solid #444; color: #FFF; text-align: center; vertical-align: middle; }
          th { background: #1A1A1A; color: #00E5FF; font-weight: bold; }
          td.rank { font-weight: bold; color: #FF7F00; font-size: 1.2em; width: 50px; }
          td.name { font-weight: bold; text-align: left; }
          td.score { color: #00B050; font-weight: bold; font-size: 1.2em; }
          .title { font-size: 1.5em; color: #FFF; text-transform: uppercase; font-weight: bold; text-align: center; margin-bottom: 10px; }
          .bar-bg { background: #222; border-radius: 10px; width: 100%; height: 22px; position: relative; border: 1px solid #555; }
          .bar-text { position: absolute; top: 0; left: 0; width: 100%; height: 100%; text-align: center; color: #FFF; font-size: 12px; font-weight: bold; line-height: 22px; text-shadow: 1px 1px 2px #000; }
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
        
        vps_base = "https://virtualpinballspreadsheet.github.io/vps-db/vps/"

        def _cloud_info_badge(r: dict) -> str:
            vps_id = (r.get("vps_id") or "").strip()
            table_name = (r.get("table_name") or "").strip()
            author = (r.get("author") or "").strip()
            version = (r.get("version") or "").strip()
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
            safe_vps_id = _html.escape(vps_id, quote=True)
            if vps_id:
                return (
                    f" <a href='{vps_base}{safe_vps_id}' title='{tooltip}'"
                    " style='text-decoration:none;'>ℹ️</a>"
                )
            return f" <span title='{tooltip}' style='cursor:help;'>ℹ️</span>"

        for i, row in enumerate(data):
            rank = i + 1
            name = row.get("name", "Unknown")
            ts = row.get("ts", "")[:10]
            medal = "🏆" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
            
            if category == "progress":
                unlocked = int(row.get('unlocked', 0))
                total = int(row.get('total', 1))
                pct = float(row.get('percentage', 0))
                
                bar = f"""
                <div class='bar-bg'>
                    <div style='background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF7F00, stop:1 #FFD700); width: {pct}%; height: 100%; border-radius: 9px;'></div>
                    <div class='bar-text'>{unlocked} / {total} ({pct}%)</div>
                </div>
                """
                html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}</td><td>{bar}</td><td>{ts}</td></tr>")
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
                    html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}{badge}</td><td style='color:#AAAAAA; font-style:italic;'>{diff_str}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
                else:
                    html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}{badge}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
            else:
                badge = _cloud_info_badge(row)
                score = f"{int(row.get('score', 0)):,d}".replace(",", ".")
                html.append(f"<tr><td class='rank'>{medal}</td><td class='name'>{name}{badge}</td><td class='score'>{score}</td><td>{ts}</td></tr>")
            
        html.append("</table>")
        return "".join(html)

    # ==========================================
    # STATS HTML HELPERS
    # ==========================================

    def update_stats(self):
        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        content = ""
        if os.path.isdir(stats_dir):
            try:
                txt_files = [os.path.join(stats_dir, fn) for fn in os.listdir(stats_dir)
                             if fn.lower().endswith(".txt")]
                if txt_files:
                    latest = max(txt_files, key=lambda p: os.path.getmtime(p))
                    with open(latest, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
            except Exception:
                pass

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
                html_p1 = self._gui_stats_player1_html(content)
                _set_html_preserve_scroll(self.stats_views[1], html_p1)
        except Exception:
            pass

    def _gui_stats_global_html(self) -> str:
        style = """
        <style>
          table { border-collapse: collapse; margin-top: 10px; }
          th, td { padding: 0.2em 0.5em; border-bottom: 1px solid #444; white-space: nowrap; color: #E0E0E0; }
          th { text-align: left; background: #1A1A1A; font-weight: bold; color: #00E5FF; }
          th.right { text-align: right; }
          td.val { text-align: right; font-weight: bold; color: #FF7F00; }
          .meta { color: #888888; margin-bottom: 0.8em; font-size: 1.1em; font-weight: bold; text-align: center; }
          .rom-title { font-size: 1.6em; font-weight: bold; color: #FFFFFF; text-align: center; margin-bottom: 5px; text-transform: uppercase; }
        </style>
        """
        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            pass

        summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
        
        if not rom:
            p = self._read_latest_session_txt_path()
            if p and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if line.lower().startswith("rom:"):
                                rom = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass

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
        table_title = romnames.get(rom, "")

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
            html_lines.append(f"<div style='font-size:1.2em; color:#00E5FF; font-weight:bold; text-align:center; margin-bottom:5px;'>{_html.escape(table_title)}</div>")
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

    def _gui_stats_player1_html(self, content: str = "") -> str:
        def esc(x) -> str:
            return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        style = """
        <style>
          table { border-collapse: collapse; margin-top: 10px; }
          th, td { padding: 0.2em 0.5em; border-bottom: 1px solid #444; white-space: nowrap; color: #E0E0E0; }
          th { text-align: left; background: #1A1A1A; font-weight: bold; color: #00E5FF; }
          th.right { text-align: right; }
          td.val { text-align: right; font-weight: bold; color: #FF7F00; }
          .meta { color: #888888; margin-bottom: 0.8em; font-size: 1.1em; font-weight: bold; text-align: center; }
          .rom-title { font-size: 1.6em; font-weight: bold; color: #FFFFFF; text-align: center; margin-bottom: 5px; text-transform: uppercase; }
        </style>
        """

        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            pass
        if not rom and content:
            for line in content.splitlines():
                if line.lower().startswith("rom:"):
                    rom = line.split(":", 1)[1].strip()
                    break
                    
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
        table_title = romnames.get(rom, "")

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
            html_lines.append(f"<div style='font-size:1.2em; color:#00E5FF; font-weight:bold; text-align:center; margin-bottom:5px;'>{esc(table_title)}</div>")

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
        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        if not os.path.isdir(stats_dir):
            return ""
        try:
            txt_files = [os.path.join(stats_dir, fn) for fn in os.listdir(stats_dir)
                         if fn.lower().endswith(".txt")]
            if not txt_files:
                return ""
            latest = max(txt_files, key=lambda p: os.path.getmtime(p))
            with open(latest, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return ""

    def _read_latest_session_txt_path(self) -> str:
        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        if not os.path.isdir(stats_dir):
            return ""
        try:
            txt_files = [
                os.path.join(stats_dir, fn)
                for fn in os.listdir(stats_dir)
                if fn.lower().endswith(".txt")
            ]
            if not txt_files:
                return ""
            return max(txt_files, key=lambda p: os.path.getmtime(p))
        except Exception:
            return ""

    def _read_raw_nvram_for_current_or_last_rom(self) -> tuple[str, bytes]:
        rom = ""
        try:
            rom = str(getattr(self.watcher, "current_rom", "") or "").strip()
        except Exception:
            rom = ""

        if not rom:
            p = self._read_latest_session_txt_path()
            if p and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if line.lower().startswith("rom:"):
                                rom = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass

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
            p = self._read_latest_session_txt_path()
            if p and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if line.lower().startswith("rom:"):
                                rom = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass

        if not rom:
            return style + "<div align='center'>(Global Snapshot: ROM unknown)</div>"

        audits, _, _ = self.watcher.read_nvram_audits_with_autofix(rom)

        if not audits:
            return style + f"<div align='center'>(Global Snapshot: No readable NVRAM data found for ROM <b>{rom}</b>)</div>"

        meta = f"<div class='meta'><b>ROM:</b> {rom} &nbsp;&nbsp; <b>All NVRAM values</b></div>"
        
        COLUMNS = 5
        
        rows = ["<tr>"]
        for _ in range(COLUMNS):
            rows.append("<th>Feld / Name</th><th class='right'>Wert</th>")
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
