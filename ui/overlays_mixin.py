"""Overlays mixin: mini info, status overlay, close secondary overlays, and nav (duel) handlers."""
from __future__ import annotations
from PyQt6.QtCore import QTimer
from .overlay import MiniInfoOverlay, StatusOverlay
from .overlay_duel import DuelInfoOverlay
import core.sound as sound


class OverlaysMixin:
    """Mixin that provides mini info, status overlay, and nav (duel accept/decline) handler methods."""

    _MINI_TEST_MESSAGES = [
        ("NVRAM map not found for afm_113b.", "#FF3B30"),
        ("No VPS-ID set for afm_113b. Progress will NOT be uploaded to cloud. Go to 'Available Maps' tab to assign.", "#FF7F00"),
        ("No NVRAM map found for ROM 'afm_113b'.", "#FF7F00"),
        ("No NVRAM map for 'afm_113b'. Use AWEditor for custom achievements.", "#FF7F00"),
    ]

    _DUEL_TEST_MESSAGES = [
        ("⚔️ Duel active against xPinballWizard!\n🎰 Medieval Madness\n⚠️ One game only — restarting in-game will abort the duel!\n🔙 After the duel, close VPX or return to Popper.", "#FF7F00"),
        ("🏆 DUEL WON! You: 42,069,000 vs Opponent: 38,500,000", "#00CC44"),
        ("💀 DUEL LOST. You: 38,500,000 vs Opponent: 42,069,000", "#CC2200"),
        ("🤝 TIE! You: 42,069,000 vs Opponent: 42,069,000", "#FF7F00"),
        ("⏰ Duel expired — no response received.", "#888888"),
        ("⏳ Score submitted! Waiting for opponent's score...", "#FF7F00"),
        ("⚠️ Duel aborted: Session too short.", "#FFAA00"),
        ("✅ 'xPinballWizard' accepted your duel on Medieval Madness!", "#00E500"),
        ("❌ 'xPinballWizard' declined your duel on Medieval Madness.", "#CC0000"),
    ]

    _STATUS_TEST_MESSAGES = [
        ("Online · Tracking",  "#00C853"),
        ("Online · Pending",   "#FFA500"),
        ("Online · Verified",  "#00C853"),
        ("Offline · Local",    "#FFA500"),
        ("Cloud Off · Local",  "#FF3B30"),
    ]

    def _on_mini_info_show(self, rom: str, seconds: int = 10):
        msg = f"NVRAM map not found for {rom}."
        try:
            sound.play_sound(self.cfg, "toast_info")
        except Exception:
            pass

        def _player_visible() -> bool:
            try:
                w = getattr(self, "watcher", None)
                return bool(w and w._vp_player_visible())
            except Exception:
                return False

        def _show_now():
            try:
                if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                    self._mini_overlay = MiniInfoOverlay(self)
                self._mini_overlay.show_info(msg, seconds=max(1, int(seconds)))
            except Exception as e:
                try:
                    from core.watcher_core import log
                    log(self.cfg, f"[UI] Mini overlay show failed: {e}")
                except Exception:
                    pass

        if _player_visible():
            _show_now()
            return
        tries = {"n": 0}

        def _retry():
            if _player_visible():
                _show_now()
                return
            tries["n"] += 1
            if tries["n"] < 20:
                QTimer.singleShot(250, _retry)
            else:
                _show_now()

        QTimer.singleShot(250, _retry)

    def _on_mini_info_test(self):
        if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
            self._mini_overlay = MiniInfoOverlay(self)
        msg, color = self._MINI_TEST_MESSAGES[self._mini_test_idx % len(self._MINI_TEST_MESSAGES)]
        self._mini_test_idx = (self._mini_test_idx + 1) % len(self._MINI_TEST_MESSAGES)
        self._mini_overlay.show_info(msg, seconds=5, color_hex=color)

    def _get_duel_overlay(self):
        """Return the shared DuelInfoOverlay instance, creating it lazily on first access."""
        if not hasattr(self, "_duel_overlay") or self._duel_overlay is None:
            self._duel_overlay = DuelInfoOverlay(self)
        return self._duel_overlay

    def _on_duel_overlay_test(self):
        ov = self._get_duel_overlay()
        if not hasattr(self, "_duel_overlay_test_idx"):
            self._duel_overlay_test_idx = 0
        msg, color = self._DUEL_TEST_MESSAGES[self._duel_overlay_test_idx % len(self._DUEL_TEST_MESSAGES)]
        self._duel_overlay_test_idx = (self._duel_overlay_test_idx + 1) % len(self._DUEL_TEST_MESSAGES)
        ov.show_info(msg, seconds=5, color_hex=color)

    def _on_mini_info_message(self, message: str, seconds: int, color_hex: str = "#FFFFFF"):
        """Show a message in the mini info overlay with no duel-specific side-effects."""
        try:
            if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                self._mini_overlay = MiniInfoOverlay(self)
            self._mini_overlay.show_info(str(message), max(1, int(seconds)), color_hex=str(color_hex or "#FFFFFF"))
        except Exception:
            pass

    def _on_status_overlay_test(self):
        if not hasattr(self, "_status_overlay") or self._status_overlay is None:
            self._status_overlay = StatusOverlay(self)
        msg, color = self._STATUS_TEST_MESSAGES[self._status_overlay_test_idx % len(self._STATUS_TEST_MESSAGES)]
        self._status_overlay_test_idx = (self._status_overlay_test_idx + 1) % len(self._STATUS_TEST_MESSAGES)
        self._status_overlay.update_status(msg, color)

    def _determine_status_state(self) -> tuple[str, str]:
        cloud_enabled = bool(getattr(self.cfg, "CLOUD_ENABLED", False))
        if not cloud_enabled:
            return ("Cloud Off · Local", "#FF3B30")
        cloud_url = str(getattr(self.cfg, "CLOUD_URL", "") or "").strip()
        if not cloud_url:
            return ("Offline · Local", "#FFA500")
        w = getattr(self, "watcher", None)
        game_active = bool(w and getattr(w, "game_active", False))
        if not game_active:
            return ("Offline · Local", "#FFA500")
        pending_state = getattr(self, "_status_badge_state", None)
        if pending_state == "pending":
            return ("Online · Pending", "#FFA500")
        if pending_state == "verified":
            return ("Online · Verified", "#00C853")
        if pending_state == "flagged":
            return ("Online · Flagged", "#FFA500")
        if pending_state == "rejected":
            return ("Online · Rejected", "#FF3B30")
        return ("Online · Tracking", "#00C853")

    def _on_status_overlay_show(self, message: str, seconds: int = 5, color_hex: str = ""):
        if not bool(self.cfg.OVERLAY.get("status_overlay_enabled", True)):
            return
        lc = str(message or "").lower()
        if "pending" in lc:
            self._status_badge_state = "pending"
        elif "verified" in lc or "accepted" in lc:
            self._status_badge_state = "verified"
        elif "flagged" in lc:
            self._status_badge_state = "flagged"
        elif "rejected" in lc:
            self._status_badge_state = "rejected"
        else:
            self._status_badge_state = None
        if color_hex:
            txt = str(message or "").strip()
            self._status_badge_explicit = (txt, color_hex)
        else:
            self._status_badge_explicit = None
        self._poll_status_badge()

    def _poll_status_badge(self):
        try:
            if not bool(self.cfg.OVERLAY.get("status_overlay_enabled", True)):
                return
            in_game = self._in_game_now()
            if not in_game:
                self._status_badge_state = None
                self._status_badge_explicit = None
                return
            explicit = getattr(self, "_status_badge_explicit", None)
            if explicit:
                msg, color = explicit
            else:
                msg, color = self._determine_status_state()
            if not hasattr(self, "_status_overlay") or self._status_overlay is None:
                self._status_overlay = StatusOverlay(self)
            self._status_overlay.update_status(msg, color)
        except Exception:
            pass

    def _close_secondary_overlays(self):
        """Close all secondary overlay windows (NOT the main overlay) when VPX exits."""
        # NOTE: _ach_toast_mgr and _mini_overlay are intentionally NOT cleared here.
        try:
            if hasattr(self, "_status_overlay") and self._status_overlay is not None:
                self._status_overlay.hide()
        except Exception:
            pass

    def _nav_binding_label_text(self, kind: str) -> str:
        if kind == "left":
            src = str(self.cfg.OVERLAY.get("duel_left_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("duel_left_joy_button", 4))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("duel_left_vk", 0x25))
            mods = int(self.cfg.OVERLAY.get("duel_left_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        if kind == "right":
            src = str(self.cfg.OVERLAY.get("duel_right_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("duel_right_joy_button", 5))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("duel_right_vk", 0x27))
            mods = int(self.cfg.OVERLAY.get("duel_right_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        return "Current: (none)"

    def _on_nav_src_changed(self, kind: str, src: str):
        key = f"duel_{kind}_input_source"
        self.cfg.OVERLAY[key] = str(src)
        self.cfg.save()
        if kind == "left":
            self.lbl_ch_left_binding.setText(self._nav_binding_label_text("left"))
        elif kind == "right":
            self.lbl_ch_right_binding.setText(self._nav_binding_label_text("right"))
        self._refresh_input_bindings()

    def _on_nav_left(self):
        try:
            import time as _time
            now = _time.monotonic()
            if (now - float(getattr(self, "_last_ch_nav_ts", 0.0) or 0.0)) < 0.12:
                return
            self._last_ch_nav_ts = now
        except Exception:
            pass
        # If a duel invite notification is showing in the mini overlay, Left = Accept directly.
        try:
            state = getattr(self, "_duel_invite_notify_state", None)
            if state is not None:
                duel_id = state.get("duel_id")
                if not hasattr(self, "_duel_invite_handled_ids"):
                    self._duel_invite_handled_ids = set()
                self._duel_invite_handled_ids.add(duel_id)
                self._duel_invite_notify_cancel()
                try:
                    self._get_duel_overlay().hide()
                except Exception:
                    pass
                try:
                    self._on_inbox_accept(duel_id)
                except Exception as e:
                    try:
                        from core.watcher_core import log
                        log(self.cfg, f"[NAV] _on_nav_left inbox accept failed: {e}", "WARN")
                    except Exception:
                        pass
                return
        except Exception as e:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[NAV] _on_nav_left duel invite handling failed: {e}", "WARN")
            except Exception:
                pass
        # If a tournament notification is showing, Left = confirm/dismiss (read-only).
        try:
            t_state = getattr(self, "_tournament_notify_state", None)
            if t_state is not None:
                self._tournament_notify_state = None
                try:
                    self._get_mini_overlay().hide()
                except Exception:
                    pass
                # Let the TournamentWidget show the next deferred notification.
                try:
                    tw = getattr(self, "_tournament_widget", None)
                    if tw is not None:
                        QTimer.singleShot(300, tw._try_show_deferred_notification)
                except Exception:
                    pass
                return
        except Exception as e:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[NAV] _on_nav_left tournament notify handling failed: {e}", "WARN")
            except Exception:
                pass
        # Page 5 (Score Duels): intercept Left for duel actions.
        try:
            if (
                getattr(self, "_overlay_page", -1) == 4
                and getattr(self, "overlay", None) is not None
                and self.overlay.isVisible()
            ):
                p6_state = getattr(self, "_p6_state", "IDLE")
                if p6_state == "IDLE":
                    self._overlay_page6_start_search()
                elif p6_state == "MATCH_FOUND":
                    self._overlay_page6_accept()
                return
        except Exception as e:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[NAV] _on_nav_left page5 handling failed: {e}", "WARN")
            except Exception:
                pass

    def _on_nav_right(self):
        try:
            import time as _time
            now = _time.monotonic()
            if (now - float(getattr(self, "_last_ch_nav_ts", 0.0) or 0.0)) < 0.12:
                return
            self._last_ch_nav_ts = now
        except Exception:
            pass
        # If a duel invite notification is showing in the mini overlay, Right = Decline directly.
        try:
            state = getattr(self, "_duel_invite_notify_state", None)
            if state is not None:
                duel_id = state.get("duel_id")
                if not hasattr(self, "_duel_invite_handled_ids"):
                    self._duel_invite_handled_ids = set()
                self._duel_invite_handled_ids.add(duel_id)
                self._duel_invite_notify_cancel()
                try:
                    self._get_duel_overlay().hide()
                except Exception:
                    pass
                try:
                    self._on_inbox_decline(duel_id)
                except Exception as e:
                    try:
                        from core.watcher_core import log
                        log(self.cfg, f"[NAV] _on_nav_right inbox decline failed: {e}", "WARN")
                    except Exception:
                        pass
                return
        except Exception as e:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[NAV] _on_nav_right duel invite handling failed: {e}", "WARN")
            except Exception:
                pass
        # Page 5 (Score Duels): intercept Right for duel actions.
        try:
            if (
                getattr(self, "_overlay_page", -1) == 4
                and getattr(self, "overlay", None) is not None
                and self.overlay.isVisible()
            ):
                p6_state = getattr(self, "_p6_state", "IDLE")
                if p6_state == "SEARCHING":
                    self._overlay_page6_stop_search()
                    if self.overlay and self.overlay.isVisible():
                        self._overlay_page6_show()
                elif p6_state == "MATCH_FOUND":
                    self._overlay_page6_decline()
                return
        except Exception as e:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[NAV] _on_nav_right page5 handling failed: {e}", "WARN")
            except Exception:
                pass
