"""Overlays mixin: mini info, status overlay, close secondary overlays, and nav (duel) handlers."""
from __future__ import annotations
from PyQt6.QtCore import QTimer
from .overlay import MiniInfoOverlay, StatusOverlay
from .overlay_duel import DuelInfoOverlay
import core.sound as sound


class OverlaysMixin:
    """Mixin that provides mini info, status overlay, and nav (duel accept/decline) handler methods."""

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
                # Register the duel for presence tracking — the PiP window will
                # appear automatically once both players are simultaneously playing.
                try:
                    self._pip_register_presence(ig_state)
                except Exception:
                    pass
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

    @staticmethod
    def _sanitize_pip_key(player_id: str) -> str:
        """Sanitize player_id for use as a Firebase key (same chars as cloud_sync)."""
        for ch in (".", "#", "$", "[", "]", "/"):
            player_id = player_id.replace(ch, "_")
        return player_id

    def _pip_start_exchange(self, ig_state: dict, remote_orientation=None):
        """Start a WebRTC session for the Duel PiP stream.

        Each player registers in Firebase, determines their role (offerer /
        answerer) by alphabetical key order, exchanges SDP via Firebase, and
        once connected, streams their screen while receiving the opponent's
        screen in the PiP overlay.

        Parameters
        ----------
        ig_state:
            In-game duel state dict (must contain ``duel_id``).
        remote_orientation:
            The opponent's advertised orientation ("portrait" | "landscape" |
            None).  When provided it is forwarded to the PiP overlay so that
            incoming frames are rotated correctly.
        """
        try:
            from core.watcher_core import log
        except ImportError:
            log = None  # type: ignore[assignment]

        def _log(msg: str, level: str = "INFO"):
            try:
                if log is not None:
                    log(self.cfg, msg, level)
            except Exception:
                pass

        duel_id = ig_state.get("duel_id", "")
        if not duel_id:
            _log("[WebRTC] _pip_start_exchange: missing duel_id", "WARN")
            return

        try:
            player_id = str(self.cfg.OVERLAY.get("player_id", "")).strip().lower()
        except Exception as exc:
            _log(f"[WebRTC] _pip_start_exchange: could not read player_id: {exc}", "WARN")
            return

        if not player_id:
            _log("[WebRTC] _pip_start_exchange: player_id is empty", "WARN")
            return

        player_key = self._sanitize_pip_key(player_id)

        try:
            from core.webrtc_stream import WebRTCSession
        except ImportError as exc:
            _log(f"[WebRTC] Could not import webrtc_stream: {exc}", "WARN")
            return

        # Stop only the WebRTC session / overlay — presence timers stay alive.
        session = getattr(self, "_pip_webrtc_session", None)
        if session is not None:
            try:
                session.stop()
            except Exception:
                pass
            self._pip_webrtc_session = None
        try:
            pip_old = getattr(self, "_pip_overlay", None)
            if pip_old is not None:
                pip_old.close_pip()
                self._pip_overlay = None
        except Exception:
            pass

        # Create the PiP overlay in placement mode (no stream URL needed)
        self._pip_open(duel_id=duel_id)

        # Apply the opponent's orientation so frames are rotated correctly.
        if remote_orientation in ("portrait", "landscape"):
            try:
                pip = getattr(self, "_pip_overlay", None)
                if pip is not None:
                    pip.set_remote_orientation(remote_orientation)
            except Exception as exc:
                _log(f"[WebRTC] Could not set remote orientation: {exc}", "WARN")

        # Create and start the WebRTC session
        session = WebRTCSession(
            cfg=self.cfg,
            duel_id=duel_id,
            player_key=player_key,
            log_fn=_log,
        )

        # Connect received frames to the overlay
        try:
            pip = getattr(self, "_pip_overlay", None)
            if pip is not None:
                session.frame_emitter.frame_ready.connect(pip._on_frame)
        except Exception as exc:
            _log(f"[WebRTC] Could not connect frame signal: {exc}", "WARN")

        self._pip_webrtc_session = session
        session.start()

    def _pip_open(self, duel_id: str = ""):
        """Create and show the DuelPiPOverlay (WebRTC pushes frames directly)."""
        try:
            from ui.overlay_pip import DuelPiPOverlay
            if not hasattr(self, "_pip_overlay") or self._pip_overlay is None:
                self._pip_overlay = DuelPiPOverlay(self)
            self._pip_overlay.open()
        except Exception as exc:
            try:
                from core.watcher_core import log
                log(self.cfg, f"[WebRTC] PiP open failed: {exc}", "WARN")
            except Exception:
                pass

    def _pip_close(self):
        """Stop the WebRTC session, close the PiP overlay, and clean up Firebase."""
        # Stop WebRTC session (also cleans up Firebase signaling data)
        session = getattr(self, "_pip_webrtc_session", None)
        if session is not None:
            try:
                session.stop()
            except Exception as exc:
                try:
                    from core.watcher_core import log
                    log(self.cfg, f"[WebRTC] Session stop error: {exc}", "WARN")
                except Exception:
                    pass
            self._pip_webrtc_session = None

        # Also cancel any legacy exchange event (kept for safety)
        try:
            cancel = getattr(self, "_pip_cancel_event", None)
            if cancel is not None:
                cancel.set()
                self._pip_cancel_event = None
        except Exception:
            pass

        # Close and discard the overlay
        try:
            pip = getattr(self, "_pip_overlay", None)
            if pip is not None:
                pip.close_pip()
                self._pip_overlay = None
        except Exception:
            pass

        # Clean up presence (remove local node, stop timers)
        try:
            self._pip_deregister_presence()
        except Exception:
            pass

    # ── Presence-based PiP trigger ────────────────────────────────────────────

    # Heartbeat interval (ms) for publishing local playing state.
    _PIP_HEARTBEAT_MS: int = 10_000   # 10 s
    # Polling interval (ms) for checking the opponent's playing state.
    _PIP_POLL_MS: int = 5_000         # 5 s

    def _local_orientation(self) -> str:
        """Return 'portrait' or 'landscape' for the local player's setup.

        Derives the orientation from the primary screen geometry first, then
        falls back to the ``duel_overlay_portrait`` / ``duel_pip_portrait``
        config flags so the Cabinet (Portrait) vs Desktop (Landscape) distinction
        is detected automatically.
        """
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.geometry()
                if geo.height() > geo.width():
                    return "portrait"
                return "landscape"
        except Exception:
            pass
        try:
            ov = self.cfg.OVERLAY or {}
            if bool(ov.get("duel_overlay_portrait", ov.get("duel_pip_portrait", False))):
                return "portrait"
        except Exception:
            pass
        return "landscape"

    def _pip_register_presence(self, ig_state: dict) -> None:
        """Start presence tracking for an accepted duel.

        Stores the duel context and starts two QTimers:
        - a heartbeat that publishes the local ``playing`` flag every
          ``_PIP_HEARTBEAT_MS`` ms, and
        - a poll that checks the opponent's presence every ``_PIP_POLL_MS`` ms
          and opens / closes the PiP window accordingly.

        The PiP window is **not** opened here — it only opens once both sides
        report ``playing=true`` simultaneously.
        """
        try:
            from core.watcher_core import log
        except ImportError:
            log = None  # type: ignore[assignment]

        def _log(msg: str, level: str = "INFO"):
            try:
                if log is not None:
                    log(self.cfg, msg, level)
            except Exception:
                pass

        if not getattr(self.cfg, "CLOUD_ENABLED", False):
            _log("[PiP Presence] Cloud disabled — skipping presence registration", "INFO")
            return

        duel_id = ig_state.get("duel_id", "")
        if not duel_id:
            _log("[PiP Presence] _pip_register_presence: missing duel_id", "WARN")
            return

        try:
            player_id = str(self.cfg.OVERLAY.get("player_id", "")).strip().lower()
        except Exception as exc:
            _log(f"[PiP Presence] could not read player_id: {exc}", "WARN")
            return

        if not player_id:
            _log("[PiP Presence] player_id is empty — skipping presence", "WARN")
            return

        player_key = self._sanitize_pip_key(player_id)

        # Stop any previous presence tracking before starting a new one.
        self._pip_stop_presence_timers()

        self._pip_presence_duel_id = duel_id
        self._pip_presence_player_key = player_key
        self._pip_presence_ig_state = ig_state
        self._pip_session_open = False

        _log(f"[PiP Presence] Registered for duel={duel_id} player={player_key}", "INFO")

        # Publish an initial heartbeat immediately (before the first timer tick).
        self._pip_presence_heartbeat()

        # Heartbeat timer — keeps local presence fresh while playing.
        htimer = QTimer(self)
        htimer.setInterval(self._PIP_HEARTBEAT_MS)
        htimer.timeout.connect(self._pip_presence_heartbeat)
        htimer.start()
        self._pip_heartbeat_timer = htimer

        # Poll timer — checks opponent and triggers PiP open/close.
        ptimer = QTimer(self)
        ptimer.setInterval(self._PIP_POLL_MS)
        ptimer.timeout.connect(self._pip_presence_poll)
        ptimer.start()
        self._pip_poll_timer = ptimer

    def _pip_stop_presence_timers(self) -> None:
        """Stop and discard the heartbeat and poll QTimers (if running)."""
        try:
            ht = getattr(self, "_pip_heartbeat_timer", None)
            if ht is not None:
                ht.stop()
                self._pip_heartbeat_timer = None
        except Exception:
            pass
        try:
            pt = getattr(self, "_pip_poll_timer", None)
            if pt is not None:
                pt.stop()
                self._pip_poll_timer = None
        except Exception:
            pass

    def _pip_presence_heartbeat(self) -> None:
        """Publish the local player's current playing state to Firebase.

        Called every ``_PIP_HEARTBEAT_MS`` ms by the heartbeat timer.
        """
        duel_id = getattr(self, "_pip_presence_duel_id", "")
        player_key = getattr(self, "_pip_presence_player_key", "")
        if not duel_id or not player_key:
            return
        try:
            w = getattr(self, "watcher", None)
            playing = bool(w and getattr(w, "game_active", False))
            orientation = self._local_orientation()
            import threading as _threading
            _threading.Thread(
                target=self._pip_presence_heartbeat_bg,
                args=(duel_id, player_key, playing, orientation),
                daemon=True,
                name="PiPPresenceHB",
            ).start()
        except Exception:
            pass

    def _pip_presence_heartbeat_bg(
        self,
        duel_id: str,
        player_key: str,
        playing: bool,
        orientation: str,
    ) -> None:
        """Background worker for the heartbeat (avoids blocking the UI thread)."""
        try:
            from core.duel_presence import publish_presence
            publish_presence(self.cfg, duel_id, player_key, playing, orientation)
        except Exception:
            pass

    def _pip_presence_poll(self) -> None:
        """Check opponent's presence and open / close PiP accordingly.

        Called every ``_PIP_POLL_MS`` ms by the poll timer (UI thread).
        First applies any pending action from the previous background poll,
        then starts a new background poll.
        """
        # Apply any result that was computed by the previous background poll.
        try:
            result = getattr(self, "_pip_poll_result", None)
            if result is not None:
                self._pip_poll_result = None
                action = result.get("action")
                opp_orientation = result.get("opp_orientation")
                ig_state = result.get("ig_state", {})
                reason = result.get("reason", "opponent")
                if action == "open":
                    self._pip_presence_open(ig_state, opp_orientation)
                elif action == "close":
                    self._pip_presence_close(reason=reason)
        except Exception:
            pass

        duel_id = getattr(self, "_pip_presence_duel_id", "")
        player_key = getattr(self, "_pip_presence_player_key", "")
        ig_state = getattr(self, "_pip_presence_ig_state", {})
        if not duel_id or not player_key:
            return
        try:
            import threading as _threading
            _threading.Thread(
                target=self._pip_presence_poll_bg,
                args=(duel_id, player_key, ig_state),
                daemon=True,
                name="PiPPresencePoll",
            ).start()
        except Exception:
            pass

    def _pip_presence_poll_bg(
        self,
        duel_id: str,
        player_key: str,
        ig_state: dict,
    ) -> None:
        """Background worker: fetch opponent presence, store pending action.

        The result is stored in ``self._pip_poll_result`` and consumed by the
        next call to ``_pip_presence_poll()`` on the UI thread.
        """
        try:
            from core.duel_presence import fetch_presence, is_playing, get_orientation

            # Determine opponent key from duel state.
            opponent_key = self._resolve_opponent_key(ig_state, player_key)
            if not opponent_key:
                return

            opponent_presence = fetch_presence(self.cfg, duel_id, opponent_key)
            opp_playing = is_playing(opponent_presence)
            opp_orientation = get_orientation(opponent_presence, fallback=None)

            # Local playing state (GIL-safe read).
            w = getattr(self, "watcher", None)
            local_playing = bool(w and getattr(w, "game_active", False))

            both_playing = local_playing and opp_playing
            session_open = getattr(self, "_pip_session_open", False)

            if both_playing and not session_open:
                self._pip_poll_result = {
                    "action": "open",
                    "ig_state": ig_state,
                    "opp_orientation": opp_orientation,
                }
            elif not both_playing and session_open:
                reason = "local" if not local_playing else "opponent"
                self._pip_poll_result = {
                    "action": "close",
                    "ig_state": ig_state,
                    "reason": reason,
                }
        except Exception:
            pass

    def _resolve_opponent_key(self, ig_state: dict, player_key: str) -> str:
        """Return the Firebase presence key for the opponent in *ig_state*."""
        try:
            # ig_state contains a 'duel' Duel object with challenger / opponent fields.
            duel = ig_state.get("duel")
            candidates = []
            if duel is not None:
                try:
                    candidates.append(str(getattr(duel, "challenger", "") or "").strip().lower())
                except Exception:
                    pass
                try:
                    candidates.append(str(getattr(duel, "opponent", "") or "").strip().lower())
                except Exception:
                    pass
            # Fallback: direct string fields (future-proofing)
            for field in ("challenger", "opponent"):
                val = str(ig_state.get(field, "") or "").strip().lower()
                if val:
                    candidates.append(val)
            for candidate_id in candidates:
                if not candidate_id:
                    continue
                candidate_key = self._sanitize_pip_key(candidate_id)
                if candidate_key != player_key:
                    return candidate_key
        except Exception:
            pass
        return ""

    def _pip_presence_open(self, ig_state: dict, opp_orientation) -> None:
        """Open the PiP window because both players are now playing.

        Must be called from the UI thread.
        """
        try:
            from core.watcher_core import log
            log(self.cfg, "[PiP Presence] Both players playing — opening PiP", "INFO")
        except Exception:
            pass
        self._pip_session_open = True
        # Pass the opponent's orientation to the overlay before/after opening.
        self._pip_start_exchange(ig_state, remote_orientation=opp_orientation)

    def _pip_presence_close(self, reason: str = "opponent") -> None:
        """Close the PiP window but keep presence tracking running.

        Must be called from the UI thread.
        """
        try:
            from core.watcher_core import log
            log(self.cfg, f"[PiP Presence] {reason.capitalize()} stopped playing — closing PiP", "INFO")
        except Exception:
            pass
        self._pip_session_open = False

        # Stop the WebRTC session and hide the overlay without touching the
        # presence timers (they continue running so we can re-open later).
        session = getattr(self, "_pip_webrtc_session", None)
        if session is not None:
            try:
                session.stop()
            except Exception:
                pass
            self._pip_webrtc_session = None
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

    def _pip_deregister_presence(self) -> None:
        """Stop presence timers and remove the local presence node from Firebase."""
        self._pip_stop_presence_timers()
        self._pip_session_open = False

        duel_id = getattr(self, "_pip_presence_duel_id", "")
        player_key = getattr(self, "_pip_presence_player_key", "")

        self._pip_presence_duel_id = ""
        self._pip_presence_player_key = ""
        self._pip_presence_ig_state = {}

        if duel_id and player_key:
            try:
                import threading as _threading
                _threading.Thread(
                    target=self._pip_presence_remove_bg,
                    args=(duel_id, player_key),
                    daemon=True,
                    name="PiPPresenceRM",
                ).start()
            except Exception:
                pass

    def _pip_presence_remove_bg(self, duel_id: str, player_key: str) -> None:
        """Background worker: remove local presence node from Firebase."""
        try:
            from core.duel_presence import remove_presence
            remove_presence(self.cfg, duel_id, player_key)
        except Exception:
            pass

