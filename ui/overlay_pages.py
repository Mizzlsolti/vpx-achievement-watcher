"""Overlay-pages mixin: navigation, HTML generation, and page-switching logic for overlay pages 1–5."""
from __future__ import annotations

import os
import json
import threading
import base64
import html as _html_mod
import ssl
import time
import urllib.request

from PyQt6.QtCore import Qt, pyqtSlot, Q_ARG, QMetaObject, QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication

from core.config import p_aweditor, f_custom_achievements_progress
from core.watcher_core import log, _strip_version_from_name, secure_load_json
from core.badges import compute_player_level
from core.theme import get_theme_color


class OverlayPagesMixin:
    """Mixin that provides overlay page navigation, HTML generation, and page-switching for overlay pages 0–4 (5 pages total).

    Expects the host class to provide:
        self.cfg            – AppConfig instance
        self.watcher        – Watcher instance
        self.overlay        – OverlayWindow instance
        self._overlay_page  – int: current page index
        self._overlay_cycle – dict with 'sections' key
        self._rarity_cache  – dict: per-ROM rarity data
        self._vpc_page5_data – dict or None: cached VPC page5 data
        self._vpc_cache     – dict or None: TTL cache for VPC data
        self._ensure_overlay()
        self._prepare_overlay_sections()
        self._show_overlay_section(section)
        self._start_overlay_auto_close_timer()
        self._build_challenges_results_html()
        self._generate_cloud_html(...)
    """

    # ── CAT helper ────────────────────────────────────────────────────────────

    def _is_active_cat_table(self) -> bool:
        """Return True if the currently active table is a Custom Achievement Table (no NVRAM map)."""
        try:
            watcher = getattr(self, "watcher", None)
            if not watcher:
                return False
            current_table = getattr(watcher, "current_table", "") or ""
            if not current_table:
                return False
            current_rom = getattr(watcher, "current_rom", "") or ""
            if current_rom:
                return False  # Has ROM → not a CAT table
            custom_json = os.path.join(p_aweditor(self.cfg), f"{current_table}.custom.json")
            return os.path.isfile(custom_json)
        except Exception:
            return False

    # ── Overlay page navigation core ─────────────────────────────────────────

    def _navigate_overlay_page(self, direction: int):
        """Cycle to the next/previous overlay page, skipping disabled pages."""
        ov = self.cfg.OVERLAY or {}
        enabled_pages = [0]
        if ov.get("overlay_page2_enabled", True):
            enabled_pages.append(1)
        if ov.get("overlay_page3_enabled", True):
            enabled_pages.append(2)
        if ov.get("overlay_page4_enabled", True):
            enabled_pages.append(3)
        if ov.get("overlay_page5_enabled", True):
            enabled_pages.append(4)
        if ov.get("overlay_page6_enabled", True):
            enabled_pages.append(5)

        if not enabled_pages:
            enabled_pages = [0]

        current = int(getattr(self, "_overlay_page", 0))
        if current in enabled_pages:
            current_idx = enabled_pages.index(current)
        else:
            current_idx = 0

        new_idx = (current_idx + direction) % len(enabled_pages)
        self._overlay_page = enabled_pages[new_idx]

        try:
            self._show_overlay_page(self._overlay_page)
        except Exception as e:
            try:
                log(self.cfg, f"[OVERLAY] page navigation failed: {e}", "WARN")
            except Exception:
                pass

    def _show_page_with_transition(self, content_cb):
        """Show/update the overlay using *content_cb*.

        When the overlay is already visible a slide+fade transition is used so
        the page change is animated without flickering.  On the first open the
        normal full-show sequence is used (layout, rotation, show/raise).
        Always restarts the auto-close timer and shows navigation arrows.
        """
        if self.overlay.isVisible():
            self.overlay.transition_to(content_cb)
        else:
            content_cb()
            QApplication.processEvents()
            if self.overlay.portrait_mode:
                self.overlay._apply_rotation_snapshot(force=True)
            else:
                self.overlay._show_live_unrotated()
            self.overlay._ensuring = True
            try:
                self.overlay.show()
                self.overlay.raise_()
            finally:
                self.overlay._ensuring = False
        self._start_overlay_auto_close_timer()
        try:
            self.overlay.set_nav_arrows(True)
        except Exception:
            pass

    def _show_overlay_page(self, page_idx: int):
        """Show one of the 5 overlay pages."""
        self._ensure_overlay()
        if page_idx == 0:
            self._vpc_page5_data = None
            # Page 1: Main Stats (existing combined-players view)
            secs = self._overlay_cycle.get("sections", [])
            if not secs:
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
            if secs:
                self._show_overlay_section(secs[0])
            else:
                self._show_page_with_transition(
                    lambda: self.overlay.set_html(
                        "<div style='text-align:center; color:#888; padding:20px;'>(No session data available)</div>",
                        "Session Overview",
                    )
                )
        elif page_idx == 1:
            self._vpc_page5_data = None
            # Page 2: Local Achievement Progress for last played ROM
            css, header_html, rows = self._overlay_page2_html()
            self._show_page_with_transition(
                lambda: self.overlay.set_html_scrollable(css, header_html, rows, "Achievement Progress")
            )
        elif page_idx == 2:
            self._vpc_page5_data = None
            # Page 3: Local Challenge Leaderboard (1:1 mirror of GUI)
            html = self._overlay_page3_html()
            self._show_page_with_transition(
                lambda: self.overlay.set_html(html, "Challenge Leaderboard")
            )
        elif page_idx == 3:
            self._vpc_page5_data = None
            # Page 4: Cloud Leaderboard (dynamic)
            self._overlay_page4_show()
        elif page_idx == 4:
            # Page 5: VPC Weekly Challenge Leaderboard
            self._overlay_page5_show()
        elif page_idx == 5:
            # Page 6: Score Duels Auto-Match
            self._overlay_page6_show()

    # ── Last-played helpers ───────────────────────────────────────────────────

    def _get_last_played_rom(self) -> str:
        """Return the ROM key of the last played session (non-challenge or challenge)."""
        try:
            summary_path = os.path.join(
                self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json"
            )
            if os.path.isfile(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                rom = str(data.get("rom", "") or "")
                if rom:
                    return rom
        except Exception:
            pass
        try:
            rom = (
                getattr(self.watcher, "current_rom", None)
                or getattr(self.watcher, "_last_logged_rom", None)
            )
            if rom:
                return str(rom)
        except Exception:
            pass
        return ""

    def _get_last_session_context(self) -> dict:
        """Determine what was last played: non-challenge session or a challenge, and return metadata."""
        from datetime import datetime

        ctx = {"rom": "", "table_name": "", "is_challenge": False, "kind": "", "difficulty": ""}

        # Last non-challenge session from summary
        summary_path = os.path.join(
            self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json"
        )
        last_normal_ts = None
        normal_rom = ""
        normal_table = ""
        try:
            if os.path.isfile(summary_path):
                last_normal_ts = os.path.getmtime(summary_path)
                with open(summary_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                normal_rom = str(data.get("rom", "") or "")
                normal_table = str(data.get("table", "") or "")
        except Exception:
            pass

        # Last challenge session from challenge history files
        last_challenge_ts = None
        challenge_rom = ""
        challenge_kind = ""
        challenge_difficulty = ""
        hist_dir = os.path.join(self.cfg.BASE, "session_stats", "challenges", "history")
        try:
            if os.path.isdir(hist_dir):
                latest_item = None
                latest_dt = None
                for fn in os.listdir(hist_dir):
                    if not fn.lower().endswith(".json"):
                        continue
                    fpath = os.path.join(hist_dir, fn)
                    data = secure_load_json(fpath, {"results": []}) or {"results": []}
                    for it in (data.get("results") or []):
                        try:
                            ts = str(it.get("ts", "") or "")
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if dt.tzinfo is not None:
                                dt = dt.astimezone().replace(tzinfo=None)
                            if latest_dt is None or dt > latest_dt:
                                latest_dt = dt
                                latest_item = it
                        except Exception:
                            continue
                if latest_item and latest_dt:
                    last_challenge_ts = latest_dt.timestamp()
                    challenge_rom = str(latest_item.get("rom", "") or "")
                    challenge_kind = str(latest_item.get("kind", "") or "").lower()
                    challenge_difficulty = str(latest_item.get("difficulty", "") or "")
        except Exception:
            pass

        # Pick the more recent context
        if last_challenge_ts is not None and last_normal_ts is not None:
            if last_challenge_ts >= last_normal_ts:
                ctx.update({"rom": challenge_rom, "is_challenge": True,
                            "kind": challenge_kind, "difficulty": challenge_difficulty})
            else:
                ctx.update({"rom": normal_rom, "table_name": normal_table})
        elif last_challenge_ts is not None:
            ctx.update({"rom": challenge_rom, "is_challenge": True,
                        "kind": challenge_kind, "difficulty": challenge_difficulty})
        elif last_normal_ts is not None:
            ctx.update({"rom": normal_rom, "table_name": normal_table})

        # Resolve table name from ROMNAMES if not already set
        if ctx["rom"] and not ctx["table_name"]:
            try:
                romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
                ctx["table_name"] = romnames.get(ctx["rom"], "")
            except Exception:
                pass

        return ctx

    # ── Page renderers ────────────────────────────────────────────────────────

    def _overlay_page2_html(self) -> tuple:
        """Return (css, header_html, rows) for Page 2: Achievement Progress.

        ``rows`` is a list of ``<tr>`` HTML strings for use with
        ``OverlayWindow.set_html_scrollable()``.  The Python-level QTimer scroll
        in OverlayWindow replaces the old CSS-animation approach (which is not
        supported by Qt's QLabel RichText renderer).
        """
        import html as _html_mod
        import json as _json_mod

        def esc(s):
            return _html_mod.escape(str(s))

        rom = self._get_last_played_rom()
        table_name = ""
        if rom:
            try:
                romnames = getattr(self.watcher, "ROMNAMES", {}) or {}
                table_name = _strip_version_from_name(romnames.get(rom, ""))
            except Exception:
                pass

        if rom:
            header = f"Last Played: {table_name}" if table_name else f"Last Played: {rom}"
        else:
            header = "No recent play data available"

        _tc_primary = get_theme_color(self.cfg, "primary")
        _tc_accent = get_theme_color(self.cfg, "accent")
        css = (
            "<style>"
            "table{width:100%;border-collapse:collapse;}"
            "td{font-size:0.9em;padding:4px 6px;border-bottom:1px solid #333;}"
            f".unlocked{{color:{_tc_primary};font-weight:bold;}}"
            ".locked{color:#555;}"
            f".hdr{{color:{_tc_accent};font-size:1.15em;font-weight:bold;text-align:center;padding:6px 0;}}"
            ".prog{color:#FFFFFF;font-size:0.95em;text-align:center;margin-bottom:6px;}"
            "</style>"
        )

        if not rom or not self.watcher._has_any_map(rom):
            # No NVRAM map – check if there are custom achievements for the last table
            last_table = ""
            try:
                summary_path = os.path.join(
                    self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json"
                )
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as _f:
                        _sdata = _json_mod.load(_f)
                    last_table = str(_sdata.get("table", "") or "")
            except Exception:
                pass
            if not last_table:
                last_table = getattr(self.watcher, "current_table", "") or ""

            _cat_reg_result = None
            if last_table:
                header = f"Last Played: {_strip_version_from_name(last_table)}"
                # Check for custom.json in AWEditor dir
                custom_json_path = os.path.join(p_aweditor(self.cfg), f"{last_table}.custom.json")
                # Check CAT registry once so we can suppress the "no NVRAM map"
                # messages for officially registered custom tables.
                try:
                    from core.cat_registry import lookup_by_table_key as _lookup_cat
                    _cat_reg_result = _lookup_cat(last_table)
                except Exception:
                    pass
                if os.path.isfile(custom_json_path):
                    try:
                        with open(custom_json_path, "r", encoding="utf-8") as _cf:
                            custom_data = _json_mod.load(_cf)
                        all_rules = [r for r in (custom_data.get("rules") or []) if isinstance(r, dict)]
                        # Read unlocked achievements from custom_achievements_progress.json
                        _cap_data = {}
                        try:
                            _cap_path = f_custom_achievements_progress(self.cfg)
                            if os.path.isfile(_cap_path):
                                with open(_cap_path, "r", encoding="utf-8") as _capf:
                                    _cap_data = _json_mod.load(_capf)
                        except Exception:
                            pass
                        unlocked_titles = {
                            str(e.get("title", "")).strip()
                            for e in (_cap_data.get(last_table, {}).get("unlocked") or [])
                            if isinstance(e, dict) and str(e.get("title", "")).strip()
                        }
                        if all_rules:
                            unlocked_count = 0
                            cells = []
                            # Pull rarity data from cache for this CAT table
                            # (TTL-based re-fetch mirrors the progress-tab behaviour)
                            _cat_rarity: dict = {}
                            _CAT_RARITY_TTL = 300
                            try:
                                _cat_result = _cat_reg_result
                                if _cat_result:
                                    _cat_firebase_key = _cat_result[0]
                                    _cat_cached = self._rarity_cache.get(f"cat:{_cat_firebase_key}")
                                    if getattr(self.cfg, "CLOUD_ENABLED", False) and (
                                        _cat_cached is None
                                        or (time.time() - _cat_cached.get("ts", 0)) > _CAT_RARITY_TTL
                                    ):
                                        from core.cloud_sync import CloudSync as _CS
                                        def _cat_rarity_worker(_fk=_cat_firebase_key):
                                            try:
                                                rarity_data, total = _CS.fetch_rarity_for_cat(self.cfg, _fk)
                                                self._rarity_cache[f"cat:{_fk}"] = {"data": rarity_data, "ts": time.time(), "total_players": total}
                                                QMetaObject.invokeMethod(
                                                    self, "_overlay_refresh_page2",
                                                    Qt.ConnectionType.QueuedConnection,
                                                )
                                            except Exception:
                                                pass
                                        import threading as _threading
                                        _threading.Thread(target=_cat_rarity_worker, daemon=True).start()
                                    if _cat_cached:
                                        _cat_rarity = _cat_cached.get("data", {})
                            except Exception:
                                pass
                            for r in all_rules:
                                title = str(r.get("title", "Unknown")).strip()
                                ri = _cat_rarity.get(title)
                                rarity_suffix = (
                                    f"<br><span style='font-size:0.65em;color:{esc(ri['color'])};'>"
                                    f"{esc(ri['tier'])} ({esc(str(ri['pct']))}%)</span>"
                                    if ri else ""
                                )
                                if title in unlocked_titles:
                                    unlocked_count += 1
                                    cells.append(f"<td class='unlocked'>✅ {esc(title)}{rarity_suffix}</td>")
                                else:
                                    cells.append(f"<td class='locked'>🔒 {esc(title)}{rarity_suffix}</td>")
                            pct = round((unlocked_count / len(all_rules)) * 100, 1) if all_rules else 0.0
                            _cat_subtitle = (
                                "" if _cat_reg_result else
                                "<div style='text-align:center;color:#FF7F00;font-size:0.85em;"
                                "padding:2px 0 4px;'>Custom Achievements (no NVRAM map)</div>"
                            )
                            header_html = (
                                f"<div class='hdr'>{esc(header)}</div>"
                                + _cat_subtitle
                                + f"<div class='prog'>Progress: {unlocked_count} / {len(all_rules)} ({pct}%)</div>"
                            )
                            COLS = 4
                            rows = []
                            for i in range(0, len(cells), COLS):
                                row = "<tr>"
                                for j in range(COLS):
                                    if i + j < len(cells):
                                        row += cells[i + j]
                                    else:
                                        row += "<td></td>"
                                row += "</tr>"
                                rows.append(row)
                            return css, header_html, rows
                    except Exception:
                        pass
                    # custom.json exists but couldn't load rules
                    _no_nvram_div = (
                        "" if _cat_reg_result else
                        "<div style='text-align:center;color:#888;padding:18px;'>"
                        "No NVRAM data / map available for this table. "
                        "Custom achievements are active.</div>"
                    )
                    header_html = f"<div class='hdr'>{esc(header)}</div>" + _no_nvram_div
                    return css, header_html, []

            # Generic no-map / no custom events fallback
            _no_nvram_div2 = (
                "" if _cat_reg_result else
                "<div style='text-align:center;color:#888;padding:18px;'>"
                "No NVRAM data / map available for this table. "
                "Custom achievements are active.</div>"
            )
            header_html = f"<div class='hdr'>{esc(header)}</div>" + _no_nvram_div2
            return css, header_html, []

        try:
            state = self.watcher._ach_state_load()
        except Exception:
            state = {"global": {}, "session": {}}

        all_rules = []
        unlocked_titles = set()
        try:
            s_rules = self.watcher._collect_player_rules_for_rom(rom)
            seen = set()
            for r in s_rules:
                if isinstance(r, dict) and r.get("title"):
                    t = str(r["title"]).strip()
                    if t not in seen:
                        seen.add(t)
                        all_rules.append(r)
        except Exception:
            pass
        for e in state.get("session", {}).get(rom, []):
            t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
            unlocked_titles.add(t)

        if not all_rules:
            header_html = (
                f"<div class='hdr'>{esc(header)}</div>"
                "<div style='text-align:center;color:#888;padding:18px;'>"
                "No specific achievements defined for this ROM.</div>"
            )
            return css, header_html, []

        unlocked_count = 0
        cells = []
        # Pull rarity data from cache for this ROM
        _overlay_rarity: dict = {}
        _ROM_RARITY_TTL = 300
        _cached_r = self._rarity_cache.get(rom)
        if getattr(self.cfg, "CLOUD_ENABLED", False) and (
            _cached_r is None
            or (time.time() - _cached_r.get("ts", 0)) > _ROM_RARITY_TTL
        ):
            from core.cloud_sync import CloudSync as _CS
            def _rom_rarity_worker(_r=rom):
                try:
                    _rarity_data, _total = _CS.fetch_rarity_for_rom(self.cfg, _r)
                    self._rarity_cache[_r] = {"data": _rarity_data, "ts": time.time(), "total_players": _total}
                    QMetaObject.invokeMethod(
                        self, "_overlay_refresh_page2",
                        Qt.ConnectionType.QueuedConnection,
                    )
                except Exception:
                    pass
            import threading as _threading
            _threading.Thread(target=_rom_rarity_worker, daemon=True).start()
        if _cached_r:
            _overlay_rarity = _cached_r.get("data", {})
        for r in all_rules:
            title = str(r.get("title", "Unknown")).strip()
            clean = title.replace(" (Session)", "").replace(" (Global)", "")
            ri = _overlay_rarity.get(title) or _overlay_rarity.get(clean)
            rarity_suffix = (
                f"<br><span style='font-size:0.65em;color:{esc(ri['color'])};'>"
                f"{esc(ri['tier'])} ({esc(str(ri['pct']))}%)</span>"
                if ri else ""
            )
            if title in unlocked_titles or clean in unlocked_titles:
                unlocked_count += 1
                cells.append(f"<td class='unlocked'>✅ {esc(clean)}{rarity_suffix}</td>")
            else:
                cells.append(f"<td class='locked'>🔒 {esc(clean)}{rarity_suffix}</td>")

        pct = round((unlocked_count / len(all_rules)) * 100, 1) if all_rules else 0.0
        try:
            _state_for_lv = self.watcher._ach_state_load()
            _lv = compute_player_level(_state_for_lv)
            level_badge = f"{_lv['icon']} {_lv['label']} • Level {_lv['level']} • {_lv['total']} Achievements"
        except Exception:
            level_badge = ""

        header_html = (
            f"<div class='hdr'>{esc(header)}</div>"
            + (f"<div style='color:{_tc_accent};font-size:0.9em;text-align:center;margin-bottom:2px;'>{esc(level_badge)}</div>" if level_badge else "")
            + f"<div class='prog'>Progress: {unlocked_count} / {len(all_rules)} ({pct}%)</div>"
        )

        # Always use 4 columns so the table is compact and consistent at any scale
        COLS = 4
        rows = []
        for i in range(0, len(cells), COLS):
            row = "<tr>"
            for j in range(COLS):
                if i + j < len(cells):
                    row += cells[i + j]
                else:
                    row += "<td></td>"
            row += "</tr>"
            rows.append(row)

        return css, header_html, rows

    def _overlay_page3_html(self) -> str:
        """Generate HTML for Page 3: Local Challenge Leaderboard (mirrors the GUI view)."""
        try:
            return self._build_challenges_results_html()
        except Exception:
            return "<div style='color:#FF3B30;text-align:center;'>(Error loading challenge leaderboard)</div>"

    def _overlay_page4_show(self):
        """Show Page 4: Cloud Leaderboard. Fetches data in the background."""
        from core.cloud_sync import CloudSync

        self._ensure_overlay()
        ctx = self._get_last_session_context()

        # Build dynamic header
        is_challenge = ctx.get("is_challenge", False)
        kind = ctx.get("kind", "")
        difficulty = ctx.get("difficulty", "")
        table_name = ctx.get("table_name", "")
        rom = ctx.get("rom", "")

        kind_labels = {"timed": "Timed Challenge", "flip": "Flip Challenge", "heat": "Heat Challenge"}
        if is_challenge:
            ch_label = kind_labels.get(kind, "Challenge")
            header_title = f"{ch_label} – {difficulty}" if difficulty else ch_label
        else:
            header_title = table_name if table_name else (rom.upper() if rom else "Cloud Leaderboard")

        _tc_accent = get_theme_color(self.cfg, "accent")
        cloud_sync_msg = ""
        if not self.cfg.CLOUD_ENABLED:
            cloud_sync_msg = (
                f"<div style='color:{_tc_accent};font-weight:bold;font-size:1.05em;"
                f"text-align:center;padding:8px 12px;border:1px solid {_tc_accent};"
                "border-radius:6px;margin-bottom:10px;'>"
                "If you want to participate, enable cloud sync."
                "</div>"
            )

        header_html = (
            f"<div style='color:{_tc_accent};font-size:1.15em;font-weight:bold;"
            f"text-align:center;padding:6px 0;margin-bottom:4px;'>"
            f"{_html_mod.escape(header_title)}</div>"
            + cloud_sync_msg
        )

        if self.cfg.CLOUD_ENABLED and rom:
            loading_html = header_html + (
                "<div style='color:#888;text-align:center;padding:16px;'>Fetching cloud data…</div>"
            )
        else:
            loading_html = header_html + (
                "<div style='color:#888;text-align:center;padding:16px;'>(No ROM data available)</div>"
                if not rom else ""
            )

        self._show_page_with_transition(lambda: self.overlay.set_html(loading_html, "Cloud Leaderboard"))

        if not (self.cfg.CLOUD_ENABLED and rom):
            return

        # Fetch cloud data in background
        def _do_fetch():
            try:
                player_ids = CloudSync.fetch_player_ids(self.cfg)
                data = []
                if is_challenge:
                    cat = kind if kind in ("timed", "flip", "heat") else "timed"
                    if cat == "flip":
                        paths = [f"players/{pid}/scores/flip" for pid in player_ids]
                        batch = CloudSync.fetch_parallel(self.cfg, paths)
                        for path, flip_node in batch.items():
                            if flip_node and isinstance(flip_node, dict):
                                for rom_key, entry in flip_node.items():
                                    if rom_key == rom or rom_key.startswith(f"{rom}_"):
                                        if entry and isinstance(entry, dict):
                                            data.append(entry)
                    else:
                        paths = [f"players/{pid}/scores/{cat}/{rom}" for pid in player_ids]
                        batch = CloudSync.fetch_parallel(self.cfg, paths)
                        for path in paths:
                            entry = batch.get(path)
                            if entry and isinstance(entry, dict):
                                data.append(entry)
                    if data:
                        if cat == "flip" and difficulty and difficulty != "All Difficulties":
                            data = [
                                r for r in data
                                if str(r.get("difficulty", "")).strip().lower() == difficulty.lower()
                            ]
                        data.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
                    selected_diff = difficulty if (is_challenge and kind == "flip") else None
                    cat_for_html = cat
                else:
                    paths = [f"players/{pid}/progress/{rom}" for pid in player_ids]
                    batch = CloudSync.fetch_parallel(self.cfg, paths)
                    for path in paths:
                        entry = batch.get(path)
                        if entry and isinstance(entry, dict):
                            data.append(entry)
                    if data:
                        data.sort(key=lambda x: float(x.get("percentage", 0)), reverse=True)
                    selected_diff = None
                    cat_for_html = "progress"

                if not data:
                    final_html = header_html + (
                        "<div style='color:#FF3B30;text-align:center;padding:16px;'>Failed to fetch cloud data.</div>"
                    )
                else:
                    cloud_body = self._generate_cloud_html(data, cat_for_html, rom, selected_diff, include_info_badges=False)
                    final_html = header_html + cloud_body

                QMetaObject.invokeMethod(
                    self, "_overlay_set_cloud_html",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, final_html)
                )
            except Exception as e:
                print(f"[CLOUD OVERLAY] fetch failed: {e}")
                error_html = header_html + (
                    "<div style='color:#FF3B30;text-align:center;padding:16px;'>Failed to fetch cloud data.</div>"
                )
                QMetaObject.invokeMethod(
                    self, "_overlay_set_cloud_html",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, error_html)
                )

        threading.Thread(target=_do_fetch, daemon=True).start()

    def _generate_vpc_html_landscape(self, b64_img, week_text, table_name, overlay_w, overlay_h):
        # Use full overlay dimensions — image already contains all branding/week info.
        avail_w = overlay_w
        avail_h = overlay_h

        # The API returns 1920x1080 landscape images (16:9 aspect ratio).
        aspect = 16.0 / 9.0

        # Fit image within available bounds while preserving aspect ratio.
        img_w = avail_w
        img_h = int(img_w / aspect)

        if img_h > avail_h:
            img_h = avail_h
            img_w = int(img_h * aspect)

        img_w = max(100, img_w)
        img_h = max(56, img_h)

        # Use <table> centering — the only reliable method in Qt's RichText engine.
        # Fixed pixel width/height prevent Qt from misaligning percentage-based images.
        return (
            f"<table width='100%' height='100%'><tr><td align='center' valign='middle'>"
            f"<img src='data:image/png;base64,{b64_img}' width='{img_w}' height='{img_h}' />"
            f"</td></tr></table>"
        )

    def _refresh_vpc_page5(self):
        """Recalculate and redisplay the VPC image for the current overlay size."""
        data = getattr(self, '_vpc_page5_data', None)
        if not data:
            return
        b64_img = data['b64_img']
        week_text = data['week_text']
        table_name = data['table_name']
        is_portrait = data['is_portrait']

        if is_portrait:
            # Portrait overlay renders content in a landscape pre-canvas (H×W).
            # Use pre-canvas dimensions so the image fills it edge-to-edge.
            pre_w = self.overlay.height() if self.overlay else 1920
            pre_h = self.overlay.width() if self.overlay else 1080
            final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, pre_w, pre_h)
        else:
            overlay_w = self.overlay.width() if self.overlay else 1920
            overlay_h = self.overlay.height() if self.overlay else 1080
            final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, overlay_w, overlay_h)

        self.overlay.set_html_fullsize(final_html, "VPC Weekly")

    def _overlay_page5_show(self):
        """Show Page 5: VPC Weekly Competition (Live Data + Official Image)."""
        self._ensure_overlay()

        # Check TTL-based memory cache (~5 minutes)
        _VPC_CACHE_TTL_SECONDS = 300
        vpc_cache = getattr(self, '_vpc_cache', None)
        if vpc_cache and (time.time() - vpc_cache.get('ts', 0)) < _VPC_CACHE_TTL_SECONDS:
            cached = vpc_cache
            is_portrait = getattr(self.overlay, 'portrait_mode', False) if self.overlay else False
            b64_img = cached['b64_img']
            week_text = cached['week_text']
            table_name = cached['table_name']
            if is_portrait:
                pre_w = self.overlay.height() if self.overlay else 1920
                pre_h = self.overlay.width() if self.overlay else 1080
                final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, pre_w, pre_h)
            else:
                overlay_w = self.overlay.width() if self.overlay else 1920
                overlay_h = self.overlay.height() if self.overlay else 1080
                final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, overlay_w, overlay_h)
            self._vpc_page5_data = {
                'b64_img': b64_img,
                'week_text': week_text,
                'table_name': table_name,
                'is_portrait': is_portrait,
            }
            self._show_page_with_transition(lambda: self.overlay.set_html_fullsize(final_html, "VPC Weekly"))
            return

        # Recommended PyQt6 pattern for cross-thread UI updates
        class VpcWorkerSignals(QObject):
            update_ui = pyqtSignal(str, str)

        signals = VpcWorkerSignals()
        signals.update_ui.connect(self.overlay.set_html_fullsize)

        # Show loading screen
        _tc_primary = get_theme_color(self.cfg, "primary")
        loading_html = (
            f"<div style='color:{_tc_primary};font-size:1.15em;font-weight:bold;text-align:center;padding:6px 0;'>"
            f"VPC Weekly Challenge</div>"
            f"<div style='color:#888;text-align:center;padding:16px;'>Fetching live Challenge data & image...</div>"
        )
        self._show_page_with_transition(lambda: self.overlay.set_html_fullsize(loading_html, "VPC Weekly"))

        def _fetch_vpc_challenge():
            try:
                # SSL workaround for Windows systems with missing/outdated CA certificates
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                # 1. Challenge-Daten (Text/Infos) über die GET API abrufen
                req_api = urllib.request.Request(
                    "https://virtualpinballchat.com/vpc/api/v1/currentWeek?channelName=competition-corner",
                    headers={'User-Agent': 'VPX-Achievement-Watcher'}
                )
                with urllib.request.urlopen(req_api, timeout=10, context=ctx) as response:
                    api_data = json.loads(response.read().decode('utf-8'))

                if isinstance(api_data, list) and len(api_data) > 0:
                    week_data = api_data[0]
                else:
                    week_data = api_data

                table_name = week_data.get("tableName", week_data.get("table", "Unknown Table"))
                week_number = week_data.get("weekNumber", "")

                week_text = f"Week {week_number} - " if week_number else ""

                # 2. Ausrichtung erkennen (Portrait oder Landscape) – komplett getrennte Pfade
                is_portrait = getattr(self.overlay, 'portrait_mode', False) if self.overlay else False

                if is_portrait:
                    # Portrait overlay: content is rendered in a landscape pre-canvas
                    # (H×W = overlay height × overlay width) before being rotated 90°.
                    # Request the landscape VPC image so it fills the pre-canvas perfectly.
                    vpc_payload = json.dumps({
                        "layout": "landscape"
                    }).encode('utf-8')

                    req_img = urllib.request.Request(
                        "https://virtualpinballchat.com/vpc/api/v1/generateWeeklyLeaderboard",
                        data=vpc_payload,
                        headers={
                            'Content-Type': 'application/json',
                            'User-Agent': 'VPX-Achievement-Watcher'
                        },
                        method='POST'
                    )

                    with urllib.request.urlopen(req_img, timeout=45, context=ctx) as img_response:
                        img_data = img_response.read()

                    b64_img = base64.b64encode(img_data).decode('utf-8')
                    # Use pre-canvas dimensions (H×W) so the image fills the canvas edge-to-edge.
                    pre_w = self.overlay.height() if self.overlay else 1920
                    pre_h = self.overlay.width() if self.overlay else 1080
                    final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, pre_w, pre_h)

                else:
                    # Landscape: eigener API-Aufruf mit layout="landscape"
                    landscape_payload = json.dumps({
                        "layout": "landscape"
                    }).encode('utf-8')

                    req_img_landscape = urllib.request.Request(
                        "https://virtualpinballchat.com/vpc/api/v1/generateWeeklyLeaderboard",
                        data=landscape_payload,
                        headers={
                            'Content-Type': 'application/json',
                            'User-Agent': 'VPX-Achievement-Watcher'
                        },
                        method='POST'
                    )

                    with urllib.request.urlopen(req_img_landscape, timeout=45, context=ctx) as img_response:
                        img_data = img_response.read()

                    b64_img = base64.b64encode(img_data).decode('utf-8')
                    overlay_w = self.overlay.width() if self.overlay else 1920
                    overlay_h = self.overlay.height() if self.overlay else 1080
                    final_html = self._generate_vpc_html_landscape(b64_img, week_text, table_name, overlay_w, overlay_h)

                # Cache raw data so the slider can recalculate the image
                self._vpc_page5_data = {
                    'b64_img': b64_img,
                    'week_text': week_text,
                    'table_name': table_name,
                    'is_portrait': is_portrait,
                }

                # Store TTL cache for fast re-open (~5 min TTL)
                self._vpc_cache = {
                    'b64_img': b64_img,
                    'week_text': week_text,
                    'table_name': table_name,
                    'ts': time.time(),
                }

                # Slider hook: When overlay scale changes, recalculate the image
                try:
                    self.overlay.resizeEvent_original  # check if already hooked
                except AttributeError:
                    _orig = self.overlay.resizeEvent
                    self.overlay.resizeEvent_original = _orig
                    _self = self  # Reference to Achievement_watcher instance

                    def _hooked_resize(event, _orig=_orig, _aw=_self):
                        _orig(event)
                        if getattr(_aw, '_vpc_page5_data', None):
                            _aw._refresh_vpc_page5()

                    self.overlay.resizeEvent = _hooked_resize

                # Über das definierte Signal emitten, damit PyQt6 es sicher in den Main-Thread schiebt!
                signals.update_ui.emit(final_html, "VPC Weekly")

            except Exception as e:
                import traceback
                traceback.print_exc()
                error_html = (
                    f"<div style='color:#FF5555;text-align:center;padding:16px;'>"
                    f"Error loading VPC Challenge:<br><span style='font-size:0.8em;'>{str(e)}</span></div>"
                )
                signals.update_ui.emit(error_html, "VPC Weekly")

        threading.Thread(target=_fetch_vpc_challenge, daemon=True).start()

    # ── Page 6: Score Duels Auto-Match ───────────────────────────────────────

    _P6_POLL_INTERVAL_MS = 5_000   # poll matchmaking every 5 seconds
    _P6_TICK_INTERVAL_MS = 1_000   # elapsed timer tick every 1 second

    def _overlay_page6_show(self):
        """Show Page 6: Score Duels Auto-Match (IDLE / SEARCHING / MATCH_FOUND)."""
        self._ensure_overlay()
        state = getattr(self, "_p6_state", "IDLE")

        _tc_primary = get_theme_color(self.cfg, "primary")
        _tc_accent  = get_theme_color(self.cfg, "accent")
        _tc_border  = get_theme_color(self.cfg, "border")
        _tc_bg      = get_theme_color(self.cfg, "bg")

        fs_title = int(self.cfg.OVERLAY.get("base_title_size", 17))
        fs_body  = int(self.cfg.OVERLAY.get("base_body_size", 12))
        fs_hint  = int(self.cfg.OVERLAY.get("base_hint_size", 10))

        # Common header
        header = (
            f"<div style='text-align:center; color:{_tc_primary}; font-size:{fs_title}pt;"
            f" font-weight:bold; padding:4px 0 2px 0;'>⚔️ Score Duels</div>"
            f"<div style='border-top:1px solid {_tc_border}; margin:4px 8px;'></div>"
        )

        if state == "IDLE":
            body = (
                f"<div style='text-align:center; color:{_tc_accent}; font-size:{fs_body + 2}pt;"
                f" font-weight:bold; padding:10px 0 6px 0;'>🔍 Auto-Match</div>"
                f"<div style='display:flex; justify-content:space-between; padding:4px 16px;"
                f" font-size:{fs_body}pt;'>"
                f"<span style='color:{_tc_accent};'>◀ Start Search</span>"
                f"<span style='color:#888;'>Cancel ▶</span>"
                f"</div>"
                f"<div style='color:#888; font-size:{fs_hint}pt; padding:10px 16px 4px 16px;"
                f" font-style:italic;'>"
                f"Use ◀ Left to start searching for an opponent. Keep the overlay open until a match is found."
                f"</div>"
            )
        elif state == "SEARCHING":
            elapsed = int(getattr(self, "_p6_elapsed_sec", 0))
            mins, secs = divmod(elapsed, 60)
            queue  = int(getattr(self, "_p6_queue_count", 0))
            shared = int(getattr(self, "_p6_shared_tables", 0))
            body = (
                f"<div style='text-align:center; color:{_tc_accent}; font-size:{fs_body + 1}pt;"
                f" font-weight:bold; padding:8px 0 4px 0;'>🔍 Searching for opponent...</div>"
                f"<div style='color:{_tc_primary}; font-size:{fs_body}pt; padding:2px 16px;'>"
                f"Queue: {queue} player{'s' if queue != 1 else ''}</div>"
                f"<div style='color:{_tc_primary}; font-size:{fs_body}pt; padding:2px 16px;'>"
                f"Shared Tables: {shared}</div>"
                f"<div style='color:{_tc_primary}; font-size:{fs_body}pt; padding:2px 16px 8px 16px;'>"
                f"Search Time: {mins}:{secs:02d}</div>"
                f"<div style='text-align:right; padding:4px 16px; font-size:{fs_body}pt;'>"
                f"<span style='color:{_tc_accent};'>Cancel ▶</span>"
                f"</div>"
                f"<div style='color:#888; font-size:{fs_hint}pt; padding:4px 16px;"
                f" font-style:italic;'>"
                f"Press ▶ Right to cancel the search. Keep the overlay open until a match is found."
                f"</div>"
            )
        else:  # MATCH_FOUND
            opponent = _html_mod.escape(str(getattr(self, "_p6_opponent_name", "")))
            table    = _html_mod.escape(str(getattr(self, "_p6_table_name", "")))
            body = (
                f"<div style='text-align:center; color:{_tc_accent}; font-size:{fs_body + 2}pt;"
                f" font-weight:bold; padding:8px 0 6px 0;'>⚔️ MATCH FOUND!</div>"
                f"<div style='color:{_tc_primary}; font-size:{fs_body}pt; padding:2px 16px;'>"
                f"Opponent: {opponent}</div>"
                f"<div style='color:{_tc_primary}; font-size:{fs_body}pt; padding:2px 16px 8px 16px;'>"
                f"Table: {table}</div>"
                f"<div style='display:flex; justify-content:space-between; padding:4px 16px;"
                f" font-size:{fs_body}pt;'>"
                f"<span style='color:{_tc_accent};'>◀ Accept</span>"
                f"<span style='color:#888;'>Decline ▶</span>"
                f"</div>"
                f"<div style='color:#888; font-size:{fs_hint}pt; padding:10px 16px 4px 16px;"
                f" font-style:italic;'>"
                f"Press ◀ Left to accept or ▶ Right to decline. Launch the table yourself to begin."
                f"</div>"
            )

        html = (
            f"<div style='background:{_tc_bg}; padding:8px; border-radius:8px;"
            f" border:1px solid {_tc_border};'>"
            f"{header}{body}"
            f"</div>"
        )

        self._show_page_with_transition(lambda: self.overlay.set_html(html, "Score Duels"))

        # During SEARCHING, disable auto-close so the overlay stays open.
        if state == "SEARCHING":
            try:
                self.overlay_auto_close_timer.stop()
            except Exception:
                pass

    def _overlay_page6_init_timers(self):
        """Lazily initialise the poll and tick timers for page 6."""
        if getattr(self, "_p6_poll_timer", None) is None:
            self._p6_poll_timer = QTimer(self)
            self._p6_poll_timer.setInterval(self._P6_POLL_INTERVAL_MS)
            self._p6_poll_timer.timeout.connect(self._overlay_page6_do_poll)
        if getattr(self, "_p6_tick_timer", None) is None:
            self._p6_tick_timer = QTimer(self)
            self._p6_tick_timer.setInterval(self._P6_TICK_INTERVAL_MS)
            self._p6_tick_timer.timeout.connect(self._overlay_page6_tick)

    def _overlay_page6_start_search(self):
        """Join matchmaking queue and enter SEARCHING state."""
        # Validate prerequisites
        if not getattr(self.cfg, "CLOUD_ENABLED", False):
            return
        duel_engine = getattr(self, "_duel_engine", None)
        if duel_engine is None:
            return

        def _join():
            ok = duel_engine.join_matchmaking()
            QMetaObject.invokeMethod(
                self, "_overlay_page6_on_joined",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(bool, ok),
            )

        import threading as _threading
        _threading.Thread(target=_join, daemon=True).start()

    @pyqtSlot(bool)
    def _overlay_page6_on_joined(self, ok: bool):
        if not ok:
            return
        self._p6_state         = "SEARCHING"
        self._p6_elapsed_sec   = 0
        self._p6_queue_count   = 0
        self._p6_shared_tables = 0
        self._overlay_page6_init_timers()
        self._p6_poll_timer.start()
        self._p6_tick_timer.start()
        # Notify mascot
        try:
            trophie = getattr(self, "_trophie_overlay", None)
            if trophie is not None:
                trophie.on_automatch_started()
        except Exception:
            pass
        # Refresh display and disable auto-close
        if getattr(self, "_overlay_page", -1) == 5:
            self._overlay_page6_show()
        # Immediate first poll
        self._overlay_page6_do_poll()

    @pyqtSlot()
    def _overlay_page6_tick(self):
        """Increment elapsed counter and refresh the SEARCHING display."""
        if getattr(self, "_p6_state", "IDLE") != "SEARCHING":
            return
        self._p6_elapsed_sec = int(getattr(self, "_p6_elapsed_sec", 0)) + 1
        if getattr(self, "_overlay_page", -1) == 5 and self.overlay and self.overlay.isVisible():
            self._overlay_page6_show()

    def _overlay_page6_do_poll(self):
        """Run poll_matchmaking() in a background thread."""
        if getattr(self, "_p6_state", "IDLE") != "SEARCHING":
            return
        duel_engine = getattr(self, "_duel_engine", None)
        if duel_engine is None:
            return

        def _poll():
            result = duel_engine.poll_matchmaking()
            QMetaObject.invokeMethod(
                self, "_overlay_page6_on_poll_result",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(object, result),
            )

        import threading as _threading
        _threading.Thread(target=_poll, daemon=True).start()

    @pyqtSlot(object)
    def _overlay_page6_on_poll_result(self, result):
        if getattr(self, "_p6_state", "IDLE") != "SEARCHING":
            return
        if result is None:
            return  # network error – keep searching
        if "opponent_name" in result:
            # Match found → enter MATCH_FOUND state
            self._overlay_page6_stop_timers()
            self._p6_state         = "MATCH_FOUND"
            self._p6_opponent_name = result.get("opponent_name", "")
            raw_table              = result.get("table_name", "")
            self._p6_table_name    = _strip_version_from_name(raw_table)
            self._p6_duel_id       = result.get("duel_id", "")
            # Play match-found sound (reuse duel_received)
            try:
                from core.sound import play_sound
                play_sound(self.cfg, "duel_received")
            except Exception:
                pass
            # Notify mascot
            try:
                trophie = getattr(self, "_trophie_overlay", None)
                if trophie is not None:
                    trophie.on_automatch_found()
            except Exception:
                pass
            if getattr(self, "_overlay_page", -1) == 5 and self.overlay and self.overlay.isVisible():
                self._overlay_page6_show()
        else:
            self._p6_queue_count   = result.get("queue_count", 0)
            self._p6_shared_tables = result.get("shared_tables", 0)

    def _overlay_page6_stop_timers(self):
        """Stop poll and tick timers without leaving the queue."""
        try:
            if getattr(self, "_p6_poll_timer", None):
                self._p6_poll_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "_p6_tick_timer", None):
                self._p6_tick_timer.stop()
        except Exception:
            pass

    def _overlay_page6_stop_search(self):
        """Cancel search: stop timers, leave queue, reset to IDLE."""
        self._overlay_page6_stop_timers()
        self._p6_state = "IDLE"
        duel_engine = getattr(self, "_duel_engine", None)
        if duel_engine is not None:
            import threading as _threading
            _threading.Thread(target=duel_engine.leave_matchmaking, daemon=True).start()

    def _overlay_page6_accept(self):
        """Accept the matched duel (MATCH_FOUND state → Left hotkey)."""
        if getattr(self, "_p6_state", "IDLE") != "MATCH_FOUND":
            return
        duel_id    = getattr(self, "_p6_duel_id", "")
        self._p6_state = "IDLE"
        if duel_id:
            try:
                self._on_inbox_accept(duel_id)
            except Exception:
                try:
                    duel_engine = getattr(self, "_duel_engine", None)
                    if duel_engine:
                        duel_engine.accept_duel(duel_id)
                except Exception:
                    pass
            try:
                from core.sound import play_sound
                play_sound(self.cfg, "duel_accepted")
            except Exception:
                pass
        if getattr(self, "_overlay_page", -1) == 5 and self.overlay and self.overlay.isVisible():
            self._overlay_page6_show()

    def _overlay_page6_decline(self):
        """Decline the matched duel (MATCH_FOUND state → Right hotkey)."""
        if getattr(self, "_p6_state", "IDLE") != "MATCH_FOUND":
            return
        duel_id    = getattr(self, "_p6_duel_id", "")
        self._p6_state = "IDLE"
        if duel_id:
            try:
                self._on_inbox_decline(duel_id)
            except Exception:
                try:
                    duel_engine = getattr(self, "_duel_engine", None)
                    if duel_engine:
                        duel_engine.decline_duel(duel_id)
                except Exception:
                    pass
        if getattr(self, "_overlay_page", -1) == 5 and self.overlay and self.overlay.isVisible():
            self._overlay_page6_show()

    # ── Cloud overlay slot ────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _overlay_set_cloud_html(self, html: str):
        """Thread-safe slot to update the cloud leaderboard overlay HTML."""
        try:
            if (
                getattr(self, "_overlay_page", -1) == 3
                and self.overlay
                and self.overlay.isVisible()
            ):
                self.overlay.set_html(html, "Cloud Leaderboard")
                try:
                    self.overlay.set_nav_arrows(True)
                except Exception:
                    pass
        except Exception:
            pass

    @pyqtSlot()
    def _overlay_refresh_page2(self):
        """Thread-safe slot to refresh the Achievement Progress page after rarity data arrives."""
        try:
            if (
                getattr(self, "_overlay_page", -1) == 1
                and getattr(self, "overlay", None) is not None
                and self.overlay.isVisible()
            ):
                self._show_overlay_page(1)
        except Exception:
            pass
