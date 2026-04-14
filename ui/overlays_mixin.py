"""Overlays mixin: mini info, status overlay, close secondary overlays, and nav (duel) handlers."""
from __future__ import annotations
import threading
from PyQt6.QtCore import QTimer
from .overlay import MiniInfoOverlay, StatusOverlay
from .overlay_duel import DuelInfoOverlay
import core.sound as sound


class OverlaysMixin:
    """Mixin that provides mini info, status overlay, and nav (duel accept/decline) handler methods."""

    _PIP_EXCHANGE_TIMEOUT_SECONDS = 60
    _PIP_POLL_INTERVAL_SECONDS = 2
    CPU_MONITOR_INTERVAL_MS = 2000

    _MINI_TEST_MESSAGES = [
        ("NVRAM map not found for afm_113b.", "#FF3B30"),
        ("No VPS-ID set for afm_113b. Progress will NOT be uploaded to cloud. Go to 'Available Maps' tab to assign.", "#FF7F00"),
        ("No NVRAM map found for ROM 'afm_113b'.", "#FF7F00"),
        ("No NVRAM map for 'afm_113b'. Use AWEditor for custom achievements.", "#FF7F00"),
    ]

    _DUEL_TEST_MESSAGES = [
        (
            "<div style='text-align:center'>"
            "⚔️ Duel invite from <b>xPinballWizard</b><br>"
            "🎰 <b>Medieval Madness</b><br>"
            "←  <b>[✅ Accept]</b>  /  ❌ Decline  →"
            "</div>",
            None
        ),
        (
            "<div style='text-align:center'>"
            "⚔️ Duel against <b>xPinballWizard</b><br>"
            "🎰 <b>Medieval Madness</b><br>"
            "⚠️ One game only — restarting in-game will abort the duel!<br>"
            "🔙 After the duel, close VPX or return to your Frontend.<br>"
            "←  <b>[✅ Accept]</b>  /  ⏰ Later  →"
            "</div>",
            None
        ),
        (
            "<div style='text-align:center'>"
            "⚔️ Auto-Match found!<br>"
            "🎰 <b>Medieval Madness</b><br>"
            "⚔️ Opponent: <b>xPinballWizard</b><br>"
            "⚠️ One game only — restarting in-game will abort the duel!<br>"
            "🔙 After the duel, close VPX or return to your Frontend.<br><br>"
            "<small>Press left ← to confirm</small>"
            "</div>",
            None
        ),
        ("🏆 DUEL WON!\nYou: 42,069,000 vs Opponent: 38,500,000", "#00CC44"),
        ("💀 DUEL LOST.\nYou: 38,500,000 vs Opponent: 42,069,000", "#CC2200"),
        ("🤝 TIE!\nYou: 42,069,000 vs Opponent: 42,069,000", "#FF7F00"),
        ("⏰ Duel expired — no response received.", "#888888"),
        ("⏳ Score submitted!\nWaiting for opponent's score...", None),
        ("⚠️ Duel aborted:\nSession too short.", "#FFAA00"),
        ("✅ 'xPinballWizard' accepted your duel\non Medieval Madness!", "#00E500"),
        ("❌ 'xPinballWizard' declined your duel\non Medieval Madness.", "#CC0000"),
        ("⏰ Your duel invitation on Medieval Madness expired (not accepted).", "#888888"),
        ("🚫 Your duel on Medieval Madness was cancelled.", "#888888"),
        ("⚠️ Duel aborted:\nVPX restarted during active duel. Only one attempt allowed!", "#FF3B30"),
        ("⚠️ Duel aborted:\nMultiple games detected in single VPX session. Only one game per duel allowed!", "#FF3B30"),
        (
            "<div style='text-align:center'>"
            "🏆 Tournament started!<br>"
            "🎰 <b>Medieval Madness</b><br><br>"
            "⚔️ Your first match: against <b>xPinballWizard</b><br>"
            "⏳ You have 2 hours to play<br><br>"
            "<small>Press left ← to confirm</small>"
            "</div>",
            None
        ),
        (
            "<div style='text-align:center'>"
            "💀 Eliminated in the semifinal<br>"
            "🎰 <b>Medieval Madness</b><br><br>"
            "<b>xPinballWizard</b> wins with 42,069,000<br>"
            "Your score: 38,500,000<br><br>"
            "<small>Press left ← to confirm</small>"
            "</div>",
            None
        ),
        (
            "<div style='text-align:center'>"
            "🏆 FINAL!<br>"
            "🎰 <b>Medieval Madness</b><br><br>"
            "⚔️ Your opponent: <b>xPinballWizard</b><br>"
            "⏳ You have 2 hours to play<br><br>"
            "<small>Press left ← to confirm</small>"
            "</div>",
            None
        ),
        (
            "<div style='text-align:center'>"
            "🏆 TOURNAMENT CHAMPION!<br>"
            "🎰 <b>Medieval Madness</b><br><br>"
            "You won the tournament!<br><br>"
            "<small>Press left ← to confirm</small>"
            "</div>",
            None
        ),
        (
            "<div style='text-align:center'>"
            "💀 Final lost – Place #2<br>"
            "🎰 <b>Medieval Madness</b><br><br>"
            "<b>xPinballWizard</b> wins with 42,069,000<br>"
            "Your score: 38,500,000<br><br>"
            "<small>Press left ← to confirm</small>"
            "</div>",
            None
        ),
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
        # Clear any pending in-game duel Accept/Later overlay so the duel stays
        # ACCEPTED and the overlay reappears on the next VPX start.
        if getattr(self, "_duel_ingame_notify_state", None) is not None:
            self._duel_ingame_notify_state = None
            try:
                self._get_duel_overlay().hide()
            except Exception:
                pass

    def _nav_binding_label_text(self, kind: str) -> str:
        if kind == "left":
            src = str(self.cfg.OVERLAY.get("duel_left_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("duel_left_joy_button", 4))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("duel_left_vk", 0))
            if vk == 0:
                return "Current: (none)"
            mods = int(self.cfg.OVERLAY.get("duel_left_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        if kind == "right":
            src = str(self.cfg.OVERLAY.get("duel_right_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("duel_right_joy_button", 5))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("duel_right_vk", 0))
            if vk == 0:
                return "Current: (none)"
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
        # If an in-game duel Accept/Later overlay is showing, Left = Accept.
        try:
            ig_state = getattr(self, "_duel_ingame_notify_state", None)
            if ig_state is not None:
                rom = ig_state.get("rom", "")
                # Activate the duel session.
                w = getattr(self, "watcher", None)
                try:
                    if w is not None:
                        w.duel_active_for_current_table = True
                except Exception:
                    pass
                # Capture NVRAM "Games Started" baseline.
                try:
                    if w and rom:
                        baseline_gs = -1
                        _ba, _, _ = w.read_nvram_audits_with_autofix(rom)
                        for _k in self._DUEL_GAMES_STARTED_KEYS:
                            _v = w._nv_get_int_ci(_ba, _k, -1)
                            if _v >= 0:
                                baseline_gs = _v
                                break
                        self._duel_baseline_games_started = baseline_gs
                        self._duel_baseline_rom = rom
                except Exception:
                    self._duel_baseline_games_started = -1
                    self._duel_baseline_rom = rom
                # Record session start timestamp.
                import time as _t
                self._duel_session_start_ts = _t.time()
                # Mark the duel as started for restart detection.
                if not hasattr(self, "_duel_games_played"):
                    self._duel_games_played = {}
                duel_id = ig_state.get("duel_id", "")
                self._duel_games_played[duel_id] = 1
                # Clear state and hide overlay.
                self._duel_ingame_notify_state = None
                try:
                    self._get_duel_overlay().hide()
                except Exception:
                    pass
                return
        except Exception as e:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[NAV] _on_nav_left ingame duel accept failed: {e}", "WARN")
            except Exception:
                pass
        # If a duel invite notification is showing in the duel overlay, Left = Accept directly.
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
                    self._get_duel_overlay().hide()
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
        # If an automatch notification is showing, Left = confirm/dismiss (info-only).
        try:
            am_state = getattr(self, "_automatch_notify_state", None)
            if am_state is not None:
                self._automatch_notify_state = None
                try:
                    self._get_duel_overlay().hide()
                except Exception:
                    pass
                return
        except Exception as e:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[NAV] _on_nav_left automatch notify handling failed: {e}", "WARN")
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
        # If an in-game duel Accept/Later overlay is showing, Right = Later (dismiss).
        try:
            ig_state = getattr(self, "_duel_ingame_notify_state", None)
            if ig_state is not None:
                self._duel_ingame_notify_state = None
                try:
                    self._get_duel_overlay().hide()
                except Exception:
                    pass
                return
        except Exception as e:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[NAV] _on_nav_right ingame duel later failed: {e}", "WARN")
            except Exception:
                pass
        # If a duel invite notification is showing in the duel overlay, Right = "Decline" (actually decline the duel).
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

    # ── Duel PiP helpers ──────────────────────────────────────────────────────

    def _get_scs(self):
        """Return the running ScreenCaptureServer or None."""
        try:
            w = getattr(self, "watcher", None)
            if w is None:
                return None
            return getattr(w, "_screen_capture_server", None)
        except Exception:
            return None

    @staticmethod
    def _sanitize_pip_key(player_id: str) -> str:
        """Sanitize player_id for use as a Firebase key (same chars as cloud_sync)."""
        for ch in (".", "#", "$", "[", "]", "/"):
            player_id = player_id.replace(ch, "_")
        return player_id

    def _pip_start_exchange(self, ig_state: dict):
        """Publish own IP to Firebase and poll for opponent IP, then open PiP."""
        scs = self._get_scs()
        if scs is None or not scs.is_running:
            return

        duel_id = ig_state.get("duel_id", "")
        if not duel_id:
            return

        try:
            player_id = str(self.cfg.OVERLAY.get("player_id", "")).strip().lower()
        except Exception:
            return

        port = getattr(self.cfg, "SCREEN_CAPTURE_PORT", 9876)
        own_ip = scs.local_ip
        own_url = f"http://{own_ip}:{port}/stream/1"

        cancel_event = threading.Event()
        self._pip_cancel_event = cancel_event

        # Publish own IP to Firebase
        try:
            w = getattr(self, "watcher", None)
            if w is not None:
                sync = getattr(w, "_cloud_sync", None)
                if sync is None:
                    sync = getattr(w, "cloud_sync", None)
                if sync is not None:
                    _safe_key = self._sanitize_pip_key(player_id)
                    pip_path = f"duels/{duel_id}/pip_ips/{_safe_key}"
                    sync.set_value(pip_path, own_url)
        except Exception:
            pass

        own_safe_key = self._sanitize_pip_key(player_id)

        def _poll_worker():
            deadline = self._PIP_EXCHANGE_TIMEOUT_SECONDS
            elapsed = 0
            opponent_url = None

            while not cancel_event.is_set() and elapsed < deadline:
                # Check if game is still active
                try:
                    w2 = getattr(self, "watcher", None)
                    if w2 is not None and not getattr(w2, "game_active", False):
                        return
                except Exception:
                    pass

                # Try to read opponent IP from Firebase
                try:
                    w2 = getattr(self, "watcher", None)
                    sync = getattr(w2, "_cloud_sync", None) if w2 else None
                    if sync is None and w2 is not None:
                        sync = getattr(w2, "cloud_sync", None)
                    if sync is not None:
                        all_ips = sync.get_value(f"duels/{duel_id}/pip_ips") or {}
                        for key, url in all_ips.items():
                            if key != own_safe_key and url:
                                opponent_url = str(url)
                                break
                except Exception:
                    pass

                if opponent_url:
                    break

                cancel_event.wait(self._PIP_POLL_INTERVAL_SECONDS)
                elapsed += self._PIP_POLL_INTERVAL_SECONDS

            if opponent_url and not cancel_event.is_set():
                _url = opponent_url
                _did = duel_id
                QTimer.singleShot(0, lambda u=_url, d=_did: self._pip_open(u, d))

        t = threading.Thread(target=_poll_worker, daemon=True, name="PiPExchange")
        t.start()

    def _pip_open(self, stream_url: str, duel_id: str = ""):
        """Create and show the DuelPiPOverlay."""
        try:
            from ui.overlay_pip import DuelPiPOverlay
            if not hasattr(self, "_pip_overlay") or self._pip_overlay is None:
                self._pip_overlay = DuelPiPOverlay(self, stream_url=stream_url)
            else:
                self._pip_overlay._stream_url = stream_url
            self._pip_overlay.open()
        except Exception as exc:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[PiP] open failed: {exc}", "WARN")
            except Exception:
                pass

    def _pip_close(self):
        """Cancel any pending exchange, close PiP, clean up Firebase IP node."""
        try:
            cancel = getattr(self, "_pip_cancel_event", None)
            if cancel is not None:
                cancel.set()
                self._pip_cancel_event = None
        except Exception:
            pass

        try:
            pip = getattr(self, "_pip_overlay", None)
            if pip is not None:
                pip.close_pip()
                self._pip_overlay = None
        except Exception:
            pass

        # Clean up own IP from Firebase in a daemon thread
        def _cleanup():
            try:
                player_id = str(self.cfg.OVERLAY.get("player_id", "")).strip().lower()
                w = getattr(self, "watcher", None)
                sync = getattr(w, "_cloud_sync", None) if w else None
                if sync is None and w is not None:
                    sync = getattr(w, "cloud_sync", None)
                if sync is None or not player_id:
                    return
                _safe_key = self._sanitize_pip_key(player_id)
                # Find any active duel to get the duel_id
                try:
                    engine = getattr(self, "_duel_engine", None)
                    if engine is None:
                        return
                    active = engine.get_active_duels()
                    for duel in active:
                        duel_id = getattr(duel, "duel_id", "")
                        if duel_id:
                            sync.delete_value(f"duels/{duel_id}/pip_ips/{_safe_key}")
                except Exception:
                    pass
            except Exception:
                pass

        t = threading.Thread(target=_cleanup, daemon=True, name="PiPCleanup")
        t.start()

