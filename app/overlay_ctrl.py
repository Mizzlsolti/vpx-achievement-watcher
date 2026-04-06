from __future__ import annotations

import json
import os
import time as _time

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from ui.overlay import OverlayWindow, MiniInfoOverlay
from ui.overlay import read_active_players


class OverlayCtrlMixin:

    def _refresh_overlay_live(self):
        if not bool(self.cfg.OVERLAY.get("live_updates", False)):
            return
        # Only refresh page 0 (Main Stats); other pages have static content
        if getattr(self, "_overlay_page", 0) != 0:
            return
        try:
            if self.watcher and (self.watcher.game_active or self.watcher._vp_player_visible()):
                try:
                    if self.overlay and self.overlay.isVisible():
                        self.overlay.hide()
                except Exception:
                    pass
                return
        except Exception:
            pass
        if not self.overlay or not self.overlay.isVisible():
            return
        if not self.watcher:
            return
        try:
            if (_time.monotonic() - getattr(self, "_overlay_last_action", 0.0)) < 0.35:
                return
        except Exception:
            pass
        if getattr(self, "_overlay_busy", False):
            return
        try:
            self._overlay_busy = True

            try:
                self.watcher.force_flush()
            except Exception:
                pass
            
            self._prepare_overlay_sections()
            secs = self._overlay_cycle.get("sections", [])
            if not secs:
                self._hide_overlay()
                self._overlay_cycle = {"sections": [], "idx": -1}
                return
            
            self._show_overlay_section(secs[0])
            
        finally:
            self._overlay_busy = False

    def _has_highlights(self, entry: dict) -> bool:
        h = entry.get("highlights", {}) or {}
        for cat in ("Power", "Precision", "Fun"):
            if h.get(cat):
                return True
        return False

    def _prepare_overlay_sections(self):
        def _played_entry(p: dict) -> bool:
            try:
                if int(p.get("playtime_sec", 0) or 0) > 0:
                    return True
            except Exception:
                pass
            try:
                if int(p.get("score", 0) or 0) > 0:
                    return True
            except Exception:
                pass
            h = p.get("highlights", {}) or {}
            return any(h.get(cat) for cat in ("Power", "Precision", "Fun"))

        sections = []

        # Prefer the in-memory snapshot cache (avoids a disk read race where the
        # file hasn't been flushed yet but the overlay signal has already arrived).
        players_raw = []
        try:
            cached = getattr(self.watcher, "_overlay_snapshot_cache", None)
            if cached and isinstance(cached, dict):
                players_raw = [{
                    "id": 1,
                    "highlights": cached.get("highlights", {}),
                    "playtime_sec": int(cached.get("playtime_sec", 0) or 0),
                    "score": int(cached.get("score", 0) or 0),
                    "title": "Player 1",
                    "player": 1,
                    "rom": cached.get("rom", ""),
                }]
        except Exception:
            pass

        if not players_raw:
            players_raw = read_active_players(self.cfg.BASE)

        combined_players = []
        if players_raw:
            for p in players_raw:
                if not _played_entry(p):
                    continue
                combined_players.append({
                    "id": int(p.get("id", 0)),
                    "highlights": p.get("highlights", {}),
                    "playtime_sec": p.get("playtime_sec", 0),
                    "score": int(p.get("score", 0) or 0),
                    "rom": p.get("rom", ""),
                })
        
        active_ids = [e for e in combined_players if 1 <= int(e.get("id", 0)) <= 4]
        is_single_player = (len(active_ids) <= 1)
        if is_single_player and combined_players:
            p1 = next((e for e in combined_players if int(e.get("id", 0)) == 1), None)
            combined_players = [p1] if p1 else [combined_players[0]]

        if combined_players:
            # --- Hole die Deltas für unsere einzige Seite ---
            active_deltas = {}
            try:
                live_deltas = self.watcher.players.get(1, {}).get("session_deltas", {})
                for k, v in live_deltas.items():
                    if int(v) > 0:
                        active_deltas[k] = int(v)
            except Exception:
                pass

            summary_rom = ""
            try:
                summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
                if os.path.isfile(summary_path):
                    with open(summary_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        summary_rom = data.get("rom", "")
                        if not active_deltas:
                            saved_deltas = data.get("players", [])[0].get("deltas", {})
                            for k, v in saved_deltas.items():
                                if int(v) > 0:
                                    active_deltas[k] = int(v)
            except Exception:
                pass

            for p in combined_players:
                p["deltas"] = active_deltas

            resolved_rom = (
                getattr(self.watcher, "current_rom", "")
                or next(iter(combined_players), {}).get("rom", "")
                or summary_rom
            )
            sections.append({
                "kind": "combined_players",
                "players": combined_players,
                "title": "Session Overview",
                "rom_name": resolved_rom,
            })
            
        self._overlay_cycle = {"sections": sections, "idx": -1}
        
    def _show_overlay_section(self, payload: dict):
        self._ensure_overlay()
        already_visible = self.overlay.isVisible()
        kind = str(payload.get("kind", "")).lower()
        title = str(payload.get("title", "") or "").strip()

        def _update_and_show(update_cb):
            """Apply content update and show/raise the overlay as needed."""
            if already_visible:
                # Overlay is already on screen: use a smooth transition instead
                # of a hard content swap, which would cause a visible flash.
                self.overlay.transition_to(update_cb)
            else:
                update_cb()
                # Allow Qt to process any pending layout/paint events so that
                # font metrics are fully initialized before we measure geometry.
                QApplication.processEvents()
                # Re-run layout positions after processEvents() so title height
                # and body positions are computed with now-correct font metrics.
                # Using _layout_positions_for() directly avoids scheduling an
                # extra rotation timer (which _layout_positions() would do for
                # portrait mode).  This prevents the first-open blink/distortion
                # where sizeHint() returned stale values before the first paint.
                self.overlay._layout_positions_for(
                    self.overlay.width(), self.overlay.height()
                )
                if self.overlay.portrait_mode:
                    self.overlay._apply_rotation_snapshot(force=True)
                else:
                    # Ensure live (unrotated) widgets are explicitly visible
                    # before show() so no blank flash occurs on first open.
                    self.overlay._show_live_unrotated()
                # Prevent showEvent from re-triggering layout/rotation and
                # causing additional blink frames.
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

        if kind == "combined_players":
            combined = {"players": payload.get("players", []), "rom_name": payload.get("rom_name", "")}
            _update_and_show(lambda: self.overlay.set_combined(
                combined, session_title=title or "Active Player Highlights"))
            return
        if kind == "html":
            html = payload.get("html", "") or "<div>-</div>"
            _update_and_show(lambda: self.overlay.set_html(html, session_title=title))
            return
        combined = {"players": [payload]}
        title2 = f"Highlights – {payload.get('title','')}".strip()
        _update_and_show(lambda: self.overlay.set_combined(combined, session_title=title2))

    def _cycle_overlay_button(self):
        # ── cooldown: ignore rapid re-triggers within 500 ms ──
        _now = _time.monotonic()
        if _now - getattr(self, "_overlay_last_action", 0.0) < 0.50:
            return
        # Record this attempt immediately so all exit paths respect the cooldown
        self._overlay_last_action = _now

        try:
            if self.watcher and self.watcher.game_active:
                # Wenn eine Challenge aktiv ist oder gestartet wird → nichts tun
                ch = getattr(self.watcher, "challenge", {}) or {}
                if ch.get("active") or ch.get("suppress_big_overlay_once"):
                    return
                try:
                    if self.overlay and self.overlay.isVisible():
                        self.overlay.hide()
                except Exception:
                    pass
                try:
                    if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                        self._mini_overlay = MiniInfoOverlay(self)
                    self._mini_overlay.show_info("Overlay only available after VPX end", seconds=3, color_hex="#FF3B30")
                except Exception:
                    pass
                return
        except Exception:
            pass
        try:
            if self._is_active_cat_table():
                try:
                    if self.overlay and self.overlay.isVisible():
                        self.overlay.hide()
                except Exception:
                    pass
                try:
                    if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                        self._mini_overlay = MiniInfoOverlay(self)
                    self._mini_overlay.show_info("Overlay only available after VPX end", seconds=3, color_hex="#FF3B30")
                except Exception:
                    pass
                return
        except Exception:
            pass
        if getattr(self, "_overlay_busy", False):
            return
        self._overlay_busy = True
        try:
            ov = getattr(self, "overlay", None)
            if not ov or not ov.isVisible():
                # Open overlay. For CAT tables, start at page 1 (Achievement Progress)
                # because page 0 (Highlights/Session Overview) shows "UNKNOWN ROM".
                if self._is_active_cat_table():
                    self._overlay_page = 1
                    self._show_overlay_page(1)
                else:
                    self._overlay_page = 0
                    self._prepare_overlay_sections()
                    secs = self._overlay_cycle.get("sections", [])
                    if not secs:
                        self._msgbox_topmost("info", "Overlay", "No contents available (Global/Player).")
                        return
                    self._overlay_cycle["idx"] = 0
                    self._show_overlay_section(secs[0])
            else:
                # Overlay already visible – cycle to next enabled page, close after last.
                # Page 0 is skipped for CAT tables.
                ov = self.cfg.OVERLAY or {}
                if not self._is_active_cat_table():
                    enabled_pages = [0]
                else:
                    enabled_pages = []
                if ov.get("overlay_page2_enabled", True):
                    enabled_pages.append(1)
                if ov.get("overlay_page3_enabled", True):
                    enabled_pages.append(2)
                if ov.get("overlay_page4_enabled", True):
                    enabled_pages.append(3)
                if ov.get("overlay_page5_enabled", True):
                    enabled_pages.append(4)
                if not enabled_pages:
                    enabled_pages = [1] if self._is_active_cat_table() else [0]
                current = int(getattr(self, "_overlay_page", 0))
                if current in enabled_pages:
                    current_idx = enabled_pages.index(current)
                else:
                    current_idx = 0
                next_idx = current_idx + 1
                if next_idx >= len(enabled_pages):
                    # After last enabled page → close overlay
                    self._hide_overlay()
                else:
                    next_page = enabled_pages[next_idx]
                    self._overlay_page = next_page
                    self._show_overlay_page(next_page)
        finally:
            self._overlay_last_action = _time.monotonic()
            self._overlay_busy = False

    def _ensure_overlay(self):
        if self.overlay is None:
            self.overlay = OverlayWindow(self)
        self.overlay.portrait_mode = bool(self.cfg.OVERLAY.get("portrait_mode", True))
        self.overlay._ensuring = True          # suppress showEvent double-work
        self.overlay._apply_geometry()
        self.overlay._layout_positions()
        self.overlay.request_rotation(force=True)
        # 50ms > QTimer.singleShot(0) delay in request_rotation, so the rotation
        # pipeline has started before we release the flag.
        QTimer.singleShot(50, lambda: setattr(self.overlay, '_ensuring', False))

    def _show_overlay_latest(self):
        import time as _time

        def _do_show():
            try:
                # Don't auto-open the main overlay when a challenge is active or
                # being started (suppress_big_overlay_once is set at challenge start
                # before the first challenge notification fires).
                # Also suppress when a duel is active for the current table.
                try:
                    _w = getattr(self, "watcher", None)
                    ch = getattr(_w, "challenge", {}) if _w is not None else {}
                    if ((ch or {}).get("active") or (ch or {}).get("suppress_big_overlay_once")
                            or getattr(_w, "duel_active_for_current_table", False)):
                        return
                except Exception:
                    pass
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
                self._ensure_overlay()
                self._overlay_cycle["idx"] = 0
                if self._is_active_cat_table():
                    # For custom tables (no NVRAM map) skip the Highlights page
                    # (page 0) which shows "(No Highlights yet)" and start
                    # directly at Achievement Progress (page 1).
                    self._overlay_page = 1
                    self._show_overlay_page(1)
                else:
                    if not secs:
                        return
                    self._overlay_page = 0
                    self._show_overlay_section(secs[0])
                try:
                    self._overlay_last_action = _time.monotonic()
                except Exception:
                    pass
            except Exception:
                pass
        try:
            w = getattr(self, "watcher", None)
            if w and w._vp_player_visible():
                tries = {"n": 0}
                def _poll():
                    try:
                        if not w._vp_player_visible():
                            _do_show()
                            return
                    except Exception:
                        _do_show()
                        return
                    tries["n"] += 1
                    if tries["n"] < 16:
                        QTimer.singleShot(150, _poll)
                    else:
                        _do_show()
                QTimer.singleShot(150, _poll)
                return
        except Exception:
            pass
        _do_show()

    def _hide_overlay(self):
        if self.overlay and self.overlay.isVisible():
            self.overlay.hide()
        try:
            self.overlay_auto_close_timer.stop()
        except Exception:
            pass
        try:
            if self.overlay:
                self.overlay.set_nav_arrows(False)
        except Exception:
            pass
        if self.overlay and self.overlay.isVisible():
            self.overlay.hide()

    def _toggle_overlay(self):
        if self.watcher and self.watcher.game_active and self.watcher.current_rom:
            if bool(self.cfg.OVERLAY.get("live_updates", False)):
                try:
                    self.watcher.force_flush()
                except Exception:
                    pass
        self._cycle_overlay_button()
