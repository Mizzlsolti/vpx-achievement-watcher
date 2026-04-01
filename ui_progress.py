"""Progress-tab mixin: local achievement progress view, rarity fetch, and custom-table progress."""
from __future__ import annotations

import os
import json
import time
import threading
import urllib.parse as _urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QTextBrowser,
)
from PyQt6.QtCore import QTimer, QUrl

from config import f_custom_achievements_progress, f_global_ach, p_aweditor
from cloud_sync import CloudSync
from watcher_core import _strip_version_from_name
from badges import RARITY_TIERS
from ui_vps import VpsAchievementInfoDialog


class ProgressMixin:
    """Mixin that provides the Progress tab (local achievement progress, rarity) and all
    related build, refresh, and render methods.

    Expects the host class to provide:
        self.cfg            – AppConfig instance
        self.watcher        – Watcher instance
        self.main_tabs      – QTabWidget (main tab bar)
        self._add_tab_help_button(layout, key)  – adds the Help button to a tab layout
        self._rarity_cache  – dict, initialised in __init__
    """

    def _build_tab_progress(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp = QGroupBox("Local Achievement Progress")
        lay = QVBoxLayout(grp)
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Select Table:"))
        self.cmb_progress_rom = QComboBox()
        self.cmb_progress_rom.currentIndexChanged.connect(self._on_progress_rom_changed)
        row.addWidget(self.cmb_progress_rom)

        self.lbl_progress_rom_name = QLabel("")
        self.lbl_progress_rom_name.setStyleSheet("color:#00E5FF; font-weight:bold; margin-left: 10px;")
        row.addWidget(self.lbl_progress_rom_name)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color:#00E5FF; color:#000000; font-weight:bold;"
            " border:none; border-radius:5px; padding:7px 16px; }"
        )
        btn_refresh.clicked.connect(self._refresh_progress_roms)
        row.addWidget(btn_refresh)
        lay.addLayout(row)
        
        self.progress_view = QTextBrowser()
        self.progress_view.setOpenLinks(False)
        self.progress_view.anchorClicked.connect(self._on_progress_anchor_clicked)
        lay.addWidget(self.progress_view)
        
        layout.addWidget(grp)
        self._add_tab_help_button(layout, "progress")
        self.main_tabs.addTab(tab, "📈 Progress")
        
        QTimer.singleShot(2000, self._refresh_progress_roms)

    def _refresh_progress_roms(self):
        self.cmb_progress_rom.blockSignals(True)
        self.cmb_progress_rom.clear()
        
        roms = set()
        
        state = self.watcher._ach_state_load()
        roms.update(state.get("global", {}).keys())
        roms.update(state.get("session", {}).keys())

        # Include ROMs from roms_played (populated after cloud restore)
        roms_played = state.get("roms_played") or []
        roms.update(roms_played)

        # Include ROMs that have a .ach.json file (generated after cloud restore)
        ach_dir = os.path.join(self.cfg.BASE, "Achievements", "rom_specific_achievements")
        if os.path.isdir(ach_dir):
            for fn in os.listdir(ach_dir):
                if fn.lower().endswith(".ach.json"):
                    roms.add(fn[:-len(".ach.json")])

        stats_dir = os.path.join(self.cfg.BASE, "session_stats")
        if os.path.isdir(stats_dir):
            for fn in os.listdir(stats_dir):
                if fn.lower().endswith(".txt"):
                    parts = fn.split("__")
                    if len(parts) >= 2:
                        roms.add(parts[0])
                        
        valid_roms = sorted([r for r in roms if self.watcher._has_any_map(r)])
        
        self.cmb_progress_rom.addItem("Global", "Global")
        
        if valid_roms:
            romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
            for r in valid_roms:
                title = _strip_version_from_name(romnames.get(r, r))
                self.cmb_progress_rom.addItem(title, r)

        # Add custom achievement tables from custom_achievements_progress.json
        try:
            cap_path = f_custom_achievements_progress(self.cfg)
            if os.path.isfile(cap_path):
                with open(cap_path, "r", encoding="utf-8") as _f:
                    cap_data = json.load(_f)
                if isinstance(cap_data, dict):
                    for table_key in sorted(cap_data.keys()):
                        display_name = _strip_version_from_name(table_key)
                        self.cmb_progress_rom.addItem(display_name, f"__custom__:{table_key}")
        except Exception:
            pass
            
        self.cmb_progress_rom.blockSignals(False)
        self._on_progress_rom_changed()

    def _get_manufacturer_progress_for_display(self, cond: dict, global_tally: dict, title: str) -> tuple:
        """Return (progress, need) for display in the progress bar for manufacturer-based conditions.
        Reads roms_played from global_tally cache stored by _evaluate_achievements."""
        rtype = str(cond.get("type") or "").lower()
        tally = global_tally.get(title, {})
        progress = int(tally.get("progress", 0))
        if rtype == "rom_count":
            manufacturer = cond.get("manufacturer", "")
            if manufacturer == "__any__":
                min_brands = cond.get("min_brands")
                if min_brands is not None:
                    return progress, int(min_brands)
                else:
                    return progress, int(cond.get("min", 1))
            else:
                return progress, int(cond.get("min", 1))
        elif rtype == "rom_complete_set":
            installed_count = int(tally.get("installed_count", 0))
            if installed_count > 0:
                return progress, installed_count
            # installed_count not yet cached (no session evaluated); show progress/progress
            # to avoid division-by-zero, use max(progress, 1) as the denominator
            return progress, max(progress, 1)
        elif rtype == "rom_multi_brand":
            manufacturers = cond.get("manufacturers") or []
            installed_count = int(tally.get("installed_count", len(manufacturers)))
            return progress, installed_count
        return 0, 1

    def _fetch_rarity_bg(self, rom):
        """Fetch rarity data in background and refresh progress tab when done."""
        def _worker():
            try:
                rarity_data, total = CloudSync.fetch_rarity_for_rom(self.cfg, rom)
                self._rarity_cache[rom] = {"data": rarity_data, "ts": time.time(), "total_players": total}
                QTimer.singleShot(0, self._on_progress_rom_changed)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _fetch_cat_rarity_bg(self, firebase_key: str):
        """Fetch CAT rarity data in background and refresh progress tab when done."""
        def _worker():
            try:
                rarity_data, total = CloudSync.fetch_rarity_for_cat(self.cfg, firebase_key)
                self._rarity_cache[f"cat:{firebase_key}"] = {"data": rarity_data, "ts": time.time(), "total_players": total}
                QTimer.singleShot(0, self._on_progress_rom_changed)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _render_custom_progress(self, table_key: str):
        """Render the progress view for a custom achievement table."""
        try:
            cap_path = f_custom_achievements_progress(self.cfg)
            cap_data = {}
            if os.path.isfile(cap_path):
                with open(cap_path, "r", encoding="utf-8") as _f:
                    cap_data = json.load(_f)
            entry = cap_data.get(table_key, {}) if isinstance(cap_data, dict) else {}
            unlocked_list = entry.get("unlocked") or []
            unlocked_titles = {str(e.get("title", "")).strip() for e in unlocked_list if isinstance(e, dict)}

            # Load all defined rules from the matching .custom.json
            aw_dir = p_aweditor(self.cfg)
            all_rules = []
            json_name = f"{table_key}.custom.json"
            json_path = os.path.join(aw_dir, json_name)
            if os.path.isfile(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as _f:
                        custom_data = json.load(_f)
                    all_rules = custom_data.get("rules") or []
                except Exception:
                    pass

            # Rarity: trigger background fetch if cloud enabled
            rarity_map: dict = {}
            if self.cfg.CLOUD_ENABLED:
                try:
                    from cat_registry import lookup_by_table_key
                    result = lookup_by_table_key(table_key)
                    if result:
                        firebase_key = result[0]
                        _RARITY_TTL = 300
                        cached = self._rarity_cache.get(f"cat:{firebase_key}")
                        if cached is None or (time.time() - cached.get("ts", 0)) > _RARITY_TTL:
                            self._fetch_cat_rarity_bg(firebase_key)
                        cached = self._rarity_cache.get(f"cat:{firebase_key}")
                        if cached:
                            rarity_map = cached.get("data", {})
                except Exception:
                    pass

            display_name = _strip_version_from_name(table_key)
            unlocked_count = len(unlocked_titles)
            total = len(all_rules) if all_rules else entry.get("total_rules", 0)

            cells = []
            for r in all_rules:
                title = str(r.get("title", "Unknown")).strip()
                rarity_label = ""
                if rarity_map:
                    ri = rarity_map.get(title)
                    if ri:
                        rarity_label = (
                            f"<br><span style='font-size:0.7em;color:{ri['color']};'>"
                            f"{ri['tier']} ({ri['pct']}%)</span>"
                        )
                if title in unlocked_titles:
                    cells.append(f"<td class='unlocked'>✅ {title}{rarity_label}</td>")
                else:
                    cells.append(f"<td class='locked'>🔒 {title}{rarity_label}</td>")
            # Also show any unlocked achievements that are no longer in the rules file
            for e in unlocked_list:
                t = str(e.get("title", "")).strip()
                if t and t not in {str(r.get("title", "")).strip() for r in all_rules}:
                    cells.append(f"<td class='unlocked'>✅ {t}</td>")

            COLUMNS = 4
            rows = []
            for i in range(0, len(cells), COLUMNS):
                row_cells = cells[i:i + COLUMNS]
                while len(row_cells) < COLUMNS:
                    row_cells.append("<td></td>")
                rows.append("<tr>" + "".join(row_cells) + "</tr>")

            pct = int(unlocked_count * 100 / total) if total > 0 else 0
            html = (
                "<style>table {border-collapse:collapse;} "
                "td {width:25%; padding:3px 4px; border-bottom:1px solid #444; text-align:center;} "
                ".unlocked {color:#00E5FF; font-weight:bold;} "
                ".locked {color:#666; font-size:0.85em;}</style>"
                f"<h3 style='color:#00E5FF; text-align:center;'>{display_name}</h3>"
                f"<p style='color:#aaa; text-align:center;'>Progress: {unlocked_count} / {total} ({pct}%)</p>"
            )

            rarity_tooltips = {
                "Common": "Unlocked by more than 50% of players",
                "Uncommon": "Unlocked by 20–50% of players",
                "Rare": "Unlocked by 5–20% of players",
                "Epic": "Unlocked by 1–5% of players",
                "Legendary": "Unlocked by less than 1% of players",
            }
            legend_parts = "".join(
                f"<span style='color:{color}; margin:0 6px; cursor:help;' "
                f"title='{rarity_tooltips.get(name, '')}'>"
                f"■ {name}</span>"
                for _, name, color in RARITY_TIERS
            )
            html += (
                f"<div style='text-align:center; font-size:0.78em; margin-bottom:18px;'>"
                f"Rarity: {legend_parts}</div>"
            )

            if rows:
                html += "<table align='center' width='100%'>" + "".join(rows) + "</table>"
            else:
                html += "<p style='color:#888;'>(No achievements defined yet)</p>"
            self.progress_view.setHtml(html)
        except Exception as e:
            self.progress_view.setHtml(f"<div style='color:#FF3B30;'>Error loading custom progress: {e}</div>")

    def _on_progress_rom_changed(self):
        rom = self.cmb_progress_rom.currentData()
        if not rom:
            rom = self.cmb_progress_rom.currentText()

        # Update colored ROM name label next to the dropdown
        if rom and rom != "Global":
            if isinstance(rom, str) and rom.startswith("__custom__:"):
                _label = _strip_version_from_name(rom[len("__custom__:"):])
            else:
                _label = rom
            self.lbl_progress_rom_name.setText(_label)
        else:
            self.lbl_progress_rom_name.setText("")

        if not rom:
            self.progress_view.setHtml("<div style='text-align:center; color:#888;'>(No data available)</div>")
            return

        # ── Custom achievement table (no NVRAM map) ──────────────────────────
        if isinstance(rom, str) and rom.startswith("__custom__:"):
            table_key = rom[len("__custom__:"):]
            self._render_custom_progress(table_key)
            return

        # ── Rarity: trigger background fetch when cloud is enabled ──────────
        _RARITY_TTL = 300  # 5 minutes
        if self.cfg.CLOUD_ENABLED and rom != "Global":
            cached = self._rarity_cache.get(rom)
            if cached is None or (time.time() - cached.get("ts", 0)) > _RARITY_TTL:
                self._fetch_rarity_bg(rom)
        rarity_map: dict = {}
        if rom != "Global":
            cached = self._rarity_cache.get(rom)
            if cached:
                rarity_map = cached.get("data", {})

        state = self.watcher._ach_state_load()
        unlocked_titles = set()
        all_rules = []

        if rom == "Global":
            gp = f_global_ach(self.cfg)
            if os.path.exists(gp):
                try:
                    with open(gp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        all_rules = data.get("rules", [])
                except Exception:
                    pass
            for r_key, entries in state.get("global", {}).items():
                for e in entries:
                    t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                    unlocked_titles.add(t)
        else:
            s_rules = self.watcher._collect_player_rules_for_rom(rom)
            
            seen_rule_titles = set()
            for r in s_rules:
                if isinstance(r, dict) and r.get("title"):
                    t = str(r.get("title")).strip()
                    if t not in seen_rule_titles:
                        seen_rule_titles.add(t)
                        all_rules.append(r)
            
            for e in state.get("session", {}).get(rom, []):
                t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                unlocked_titles.add(t)
        
        if not all_rules:
            if rom == "Global":
                self.progress_view.setHtml("<div style='color:#FF7F00; text-align:center;'>No global achievements defined.</div>")
            else:
                self.progress_view.setHtml("<div style='color:#FF7F00; text-align:center;'>No specific achievements defined for this ROM.</div>")
            return
            
        global_tally = state.get("global_tally", {}) if rom == "Global" else {}

        # Pre-compute live NVRAM totals for nvram_tally so that the progress
        # bars reflect actual NVRAM data even without a recent session evaluation.
        _live_nvram_cache: dict = {}  # field -> live total across all played ROMs
        _live_nvram_audits: dict = {}  # rom -> audits (shared across field lookups)
        _roms_played_for_live: list = list(state.get("roms_played") or []) if rom == "Global" else []

        def _live_nvram_total(field: str) -> int:
            if not _roms_played_for_live:
                return 0
            if field not in _live_nvram_cache:
                try:
                    val = self.watcher._sum_field_across_all_roms(
                        field, _roms_played_for_live, _live_nvram_audits
                    )
                except Exception:
                    val = 0
                _live_nvram_cache[field] = val
            return _live_nvram_cache[field]

        html = ["<style>table {border-collapse:collapse;} td {width:25%; padding:3px 4px; border-bottom:1px solid #444; text-align:center;} .unlocked {color:#00E5FF; font-weight:bold;} .locked {color:#666; font-size:0.85em;}</style>"]

        def _tooltip_for_rule(rule, unlocked=False):
            cond = rule.get("condition", {}) or {}
            rtype = str(cond.get("type", "")).lower()
            prefix = "✅ Unlocked! " if unlocked else ""
            if rtype == "session_time":
                seconds = cond.get("min_seconds", cond.get("min", 0))
                mins = round(int(seconds) / 60)
                return f"{prefix}Accumulate {mins} minutes of total play time across all sessions"
            elif rtype == "nvram_tally":
                field = cond.get("field", "")
                need = int(cond.get("min", 1))
                return f"{prefix}Reach {need} total {field} across all played tables"
            elif rtype == "rom_count":
                mfr = cond.get("manufacturer", "")
                if mfr == "__any__":
                    min_brands = cond.get("min_brands")
                    if min_brands:
                        return f"{prefix}Play tables from {int(min_brands)} different manufacturers"
                    else:
                        return f"{prefix}Play {int(cond.get('min', 1))} different tables"
                return f"{prefix}Play {int(cond.get('min', 1))} different {mfr} tables"
            elif rtype == "rom_complete_set":
                mfr = cond.get("manufacturer", "")
                if mfr == "__any__":
                    return f"{prefix}Play every installed table"
                return f"{prefix}Play every installed {mfr} table"
            elif rtype == "rom_multi_brand":
                mfrs = cond.get("manufacturers", [])
                return f"{prefix}Play at least one table from each: {', '.join(mfrs)}"
            elif rtype == "challenge_count":
                ct = cond.get("challenge_type", "")
                need = int(cond.get("min", 1))
                return f"{prefix}Complete {need} {ct} challenge{'s' if need != 1 else ''}"
            return prefix + "Achievement"

        unlocked_count = 0
        cells = []
        for r in all_rules:
            title = str(r.get("title", "Unknown")).strip()
            clean_title = title.replace(" (Session)", "").replace(" (Global)", "")

            # Build ℹ️ info link for ROM-specific achievements only
            if rom != "Global":
                encoded = _urlparse.quote(title, safe="")
                info_link = f" <a href='achinfo://{rom}/{encoded}' style='color:#00E5FF; text-decoration:none;'>ℹ️</a>"
            else:
                info_link = ""

            # Rarity label (ROM-specific only, when cloud data is available)
            rarity_label = ""
            if rarity_map:
                ri = rarity_map.get(title) or rarity_map.get(clean_title)
                if ri:
                    rarity_label = (
                        f"<br><span style='font-size:0.7em;color:{ri['color']};'>"
                        f"{ri['tier']} ({ri['pct']}%)</span>"
                    )

            if title in unlocked_titles or clean_title in unlocked_titles:
                unlocked_count += 1
                tooltip = _tooltip_for_rule(r, unlocked=True).replace("'", "&#39;")
                cells.append(f"<td class='unlocked' title='{tooltip}'>✅ {clean_title}{info_link}{rarity_label}</td>")
            else:
                cond = r.get("condition", {}) or {}
                rtype_display = str(cond.get("type", "")).lower()
                tooltip = _tooltip_for_rule(r, unlocked=False).replace("'", "&#39;")
                if rom == "Global" and rtype_display in ("nvram_tally", "rom_count", "rom_complete_set", "rom_multi_brand", "challenge_count"):
                    if rtype_display in ("nvram_tally", "challenge_count"):
                        need = int(cond.get("min", 1))
                        tally = global_tally.get(title, {})
                        cached_progress = int(tally.get("progress", 0))
                        field = cond.get("field") or ""
                        live_progress = _live_nvram_total(field) if field else 0
                        progress = max(cached_progress, live_progress)
                        cells.append(
                            f"<td class='locked' title='{tooltip}'>🔒 {clean_title}<br>"
                            f"<span style='font-size:0.75em;color:#FF7F00;'>{progress}/{need}</span>{rarity_label}</td>"
                        )
                    else:
                        progress, need = self._get_manufacturer_progress_for_display(cond, global_tally, title)
                        cells.append(
                            f"<td class='locked' title='{tooltip}'>🔒 {clean_title}<br>"
                            f"<span style='font-size:0.75em;color:#FF7F00;'>{progress}/{need}</span>{rarity_label}</td>"
                        )
                else:
                    cells.append(f"<td class='locked' title='{tooltip}'>🔒 {clean_title}{rarity_label}</td>")
                
        pct = round((unlocked_count / len(all_rules)) * 100, 1) if all_rules else 0
        
        if rom == "Global":
            rom_label = "Global Achievements"
        else:
            romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
            clean_rom = _strip_version_from_name(romnames.get(rom, "")) or romnames.get(rom, "") or rom
            rom_label = clean_rom
        html.append(f"<div style='font-size:1.1em; color:#FFFFFF; text-align:center; margin-bottom:5px; font-weight:bold;'>{rom_label}</div>")

        html.append(f"<div style='font-size:1.0em; color:#FF7F00; text-align:center; margin-bottom:8px; font-weight:bold;'>Progress: {unlocked_count} / {len(all_rules)} ({pct}%)</div>")

        # ── Rarity legend (ROM-specific only; not shown for Global) ───────────
        if rom != "Global":
            rarity_tooltips = {
                "Common": "Unlocked by more than 50% of players",
                "Uncommon": "Unlocked by 20–50% of players",
                "Rare": "Unlocked by 5–20% of players",
                "Epic": "Unlocked by 1–5% of players",
                "Legendary": "Unlocked by less than 1% of players",
            }
            legend_parts = "".join(
                f"<span style='color:{color}; margin:0 6px; cursor:help;' "
                f"title='{rarity_tooltips.get(name, '')}'>"
                f"■ {name}</span>"
                for _, name, color in RARITY_TIERS
            )
            html.append(
                f"<div style='text-align:center; font-size:0.78em; margin-bottom:18px;'>"
                f"Rarity: {legend_parts}</div>"
            )

        html.append("<table align='center' width='100%'>")
        COLUMNS = 4
        for i in range(0, len(cells), COLUMNS):
            html.append("<tr>")
            for j in range(COLUMNS):
                if i + j < len(cells):
                    html.append(cells[i + j])
                else:
                    html.append("<td></td>")
            html.append("</tr>")
        html.append("</table>")
        
        final_html = "".join(html)

        try:
            sb = self.progress_view.verticalScrollBar()
            old_val = sb.value()
            self.progress_view.setHtml(final_html)
            sb.setValue(old_val)
        except Exception:
            self.progress_view.setHtml(final_html)

    def _on_progress_anchor_clicked(self, url):
        """Handle ℹ️ anchor clicks in the progress view."""
        url_str = url.toString() if isinstance(url, QUrl) else str(url)
        if not url_str.startswith("achinfo://"):
            return
        # Parse achinfo://ROM/ENCODED_TITLE
        rest = url_str[len("achinfo://"):]
        parts = rest.split("/", 1)
        if len(parts) < 2:
            return
        rom = parts[0]
        title = _urlparse.unquote(parts[1])

        # Find the rule for this achievement
        rule = None
        try:
            s_rules = self.watcher._collect_player_rules_for_rom(rom)
            for r in s_rules:
                if isinstance(r, dict):
                    t = str(r.get("title", "")).strip()
                    clean = t.replace(" (Session)", "").replace(" (Global)", "")
                    if t == title or clean == title:
                        rule = r
                        break
        except Exception:
            pass

        # Find unlock entry (with timestamp if available)
        # Search both session and global achievement buckets to handle
        # all achievement types (session-specific and global).
        unlock_entry = None
        try:
            state = self.watcher._ach_state_load()
            # 1. Search session achievements for this ROM
            for e in state.get("session", {}).get(rom, []):
                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                clean = t.replace(" (Session)", "").replace(" (Global)", "")
                if t == title or clean == title:
                    unlock_entry = e if isinstance(e, dict) else {"title": e}
                    break
            # 2. If not found, also search the global "__global__" bucket
            if unlock_entry is None:
                for e in state.get("global", {}).get("__global__", []):
                    t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                    clean = t.replace(" (Session)", "").replace(" (Global)", "")
                    if t == title or clean == title:
                        unlock_entry = e if isinstance(e, dict) else {"title": e}
                        break
        except Exception:
            pass

        dlg = VpsAchievementInfoDialog(self.cfg, rom, title, rule, unlock_entry, parent=self)
        dlg.navigate_to_available_maps.connect(lambda: setattr(dlg, "_navigate_requested", True))
        dlg.exec()
        if getattr(dlg, "_navigate_requested", False):
            for i in range(self.main_tabs.count()):
                if "Available Maps" in self.main_tabs.tabText(i):
                    self.main_tabs.setCurrentIndex(i)
                    break
