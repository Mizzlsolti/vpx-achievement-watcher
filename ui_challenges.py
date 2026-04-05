"""Challenge-tab mixin: challenge select/hotkey/navigation, flip counter, heat bar, mini info, status overlay, timer, warmup, speak, and volume handlers."""
from __future__ import annotations
import os
import time
from PyQt6.QtCore import Qt, QTimer
from watcher_core import log, sanitize_filename
from ui_overlay import (
    FlipCounterOverlay,
    HeatBarometerOverlay,
    MiniInfoOverlay,
    StatusOverlay,
    ChallengeSelectOverlay,
    FlipDifficultyOverlay,
    ChallengeCountdownOverlay,
    ChallengeStartCountdown,
)
import sound


class ChallengesMixin:
    """Mixin that provides challenge select/hotkey/navigation, flip counter, heat bar,
    mini info, status overlay, timer, warmup, speak, and volume handler methods.

    Expects the host class to provide:
      - self.cfg
      - self.bridge
      - self.watcher
      - self._in_game_now()
    """

    def register_flip_counter_handlers(self):
        try:
            self.bridge.flip_counter_total_show.connect(self._on_flip_total_show)
            self.bridge.flip_counter_total_update.connect(self._on_flip_total_update)
            self.bridge.flip_counter_total_hide.connect(self._on_flip_total_hide)
        except Exception:
            pass
        self._flip_total_win = None
        self._flip_counter_picker = None

    def register_heat_bar_handlers(self):
        try:
            self.bridge.heat_bar_show.connect(self._on_heat_bar_show)
            self.bridge.heat_bar_update.connect(self._on_heat_bar_update)
            self.bridge.heat_bar_hide.connect(self._on_heat_bar_hide)
        except Exception:
            pass
        self._heat_bar_win = None
        self._heat_bar_picker = None

    def _on_heat_bar_show(self):
        try:
            if self._heat_bar_win:
                try:
                    self._heat_bar_win.close()
                    self._heat_bar_win.deleteLater()
                except Exception:
                    pass
            self._heat_bar_win = HeatBarometerOverlay(self)
        except Exception:
            self._heat_bar_win = None

    def _on_heat_bar_update(self, heat: int):
        try:
            if not self._heat_bar_win:
                self._on_heat_bar_show()
            else:
                self._heat_bar_win.set_heat(heat)
        except Exception:
            pass
        try:
            if getattr(self, "_trophie_overlay", None):
                self._trophie_overlay.on_heat_changed(int(heat))
        except Exception:
            pass

    def _on_heat_bar_hide(self):
        try:
            if self._heat_bar_win:
                self._heat_bar_win.close()
                self._heat_bar_win.deleteLater()
        except Exception:
            pass
        self._heat_bar_win = None


    def _on_heat_bar_test(self):
        try:
            if getattr(self, "_heat_bar_test_win", None):
                try:
                    self._heat_bar_test_win.close()
                except Exception:
                    pass
            self._heat_bar_test_win = HeatBarometerOverlay(self)
            self._heat_bar_test_win.set_heat(70)
            QTimer.singleShot(6000, lambda: (self._heat_bar_test_win.close() if self._heat_bar_test_win else None))
        except Exception:
            pass

    def _on_flip_total_show(self, total: int, remaining: int, goal: int):
        try:
            if self._flip_total_win:
                try:
                    self._flip_total_win.close()
                    self._flip_total_win.deleteLater()
                except Exception:
                    pass
            self._flip_total_win = FlipCounterOverlay(self, total, remaining, goal)
        except Exception:
            self._flip_total_win = None

    def _on_flip_total_update(self, total: int, remaining: int, goal: int):
        try:
            if not self._flip_total_win:
                self._on_flip_total_show(total, remaining, goal)
            else:
                self._flip_total_win.update_counts(total, remaining, goal)
        except Exception:
            pass
        try:
            if getattr(self, "_trophie_overlay", None):
                self._trophie_overlay.on_flip_progress(int(total), int(goal))
        except Exception:
            pass

    def _on_flip_total_hide(self):
        try:
            if self._flip_total_win:
                self._flip_total_win.close()
                self._flip_total_win.deleteLater()
        except Exception:
            pass
        self._flip_total_win = None
        

    def _on_flip_counter_test(self):
        try:
            goal = int(self.cfg.OVERLAY.get("flip_counter_goal_total", 400))
            
            if getattr(self, "_flip_total_test_win", None):
                try: 
                    self._flip_total_test_win.close()
                except Exception: 
                    pass
                    
            self._flip_total_test_win = FlipCounterOverlay(self, total=123, remaining=max(0, goal - 123), goal=goal)
            
            QTimer.singleShot(6000, lambda: (self._flip_total_test_win.close() if self._flip_total_test_win else None))
        except Exception:
            pass
       
    def _challenge_is_active(self) -> bool:
        try:
            ch = getattr(self.watcher, "challenge", {}) or {}
            if not ch.get("active"):
                return False
            if not self._in_game_now():
                ch["active"] = False
                ch["pending_kill_at"] = None
                self.watcher.challenge = ch
                return False
            cur_rom = getattr(self.watcher, "current_rom", None)
            ch_rom = ch.get("rom")
            if cur_rom and ch_rom and str(cur_rom) != str(ch_rom):
                ch["active"] = False
                ch["pending_kill_at"] = None
                self.watcher.challenge = ch
                return False
            return True
        except Exception:
            return False
 
    def _on_ch_src_changed(self, kind: str, src: str):
        key = f"challenge_{kind}_input_source"
        self.cfg.OVERLAY[key] = str(src)
        self.cfg.save()
        if kind == "hotkey":
            self.lbl_ch_hotkey_binding.setText(self._challenge_binding_label_text("hotkey"))
        elif kind == "left":
            self.lbl_ch_left_binding.setText(self._challenge_binding_label_text("left"))
        else:
            self.lbl_ch_right_binding.setText(self._challenge_binding_label_text("right"))
        self._refresh_input_bindings()

    _MINI_TEST_MESSAGES = [
        ("CHALLENGE COMPLETE!<br>Score: 42.069.000", "#00C853"),
        ("TIME'S UP!<br>Score: 42.069.000", "#00C853"),
        (
            "NVRAM map not found for afm_113b.",
            "#FF3B30",
        ),
        ("Challenge Aborted!", "#FF3B30"),
        ("Challenge can only be started in-game.", "#FF3B30"),
    ]

    def _on_mini_info_test(self):
        # Ruft das Fenster direkt auf, ohne auf ein offenes Spiel zu warten!
        if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
            self._mini_overlay = MiniInfoOverlay(self)
        msg, color = self._MINI_TEST_MESSAGES[self._mini_test_idx % len(self._MINI_TEST_MESSAGES)]
        self._mini_test_idx = (self._mini_test_idx + 1) % len(self._MINI_TEST_MESSAGES)
        self._mini_overlay.show_info(msg, seconds=5, color_hex=color)

    # ------------------------------------------------------------------
    # Status Overlay handlers
    # ------------------------------------------------------------------

    # Agreed status states for the persistent status badge (traffic-light semantics)
    _STATUS_TEST_MESSAGES = [
        ("Online · Tracking",  "#00C853"),   # Green
        ("Online · Pending",   "#FFA500"),   # Yellow
        ("Online · Verified",  "#00C853"),   # Green
        ("Offline · Local",    "#FFA500"),   # Yellow
        ("Cloud Off · Local",  "#FF3B30"),   # Red
    ]

    def _on_status_overlay_test(self):
        """Cycle through the agreed status states for visual testing."""
        if not hasattr(self, "_status_overlay") or self._status_overlay is None:
            self._status_overlay = StatusOverlay(self)
        msg, color = self._STATUS_TEST_MESSAGES[self._status_overlay_test_idx % len(self._STATUS_TEST_MESSAGES)]
        self._status_overlay_test_idx = (self._status_overlay_test_idx + 1) % len(self._STATUS_TEST_MESSAGES)
        self._status_overlay.update_status(msg, color)

    def _determine_status_state(self) -> tuple[str, str]:
        """Return (status_text, color_hex) that reflects the current tracking state.

        Traffic-light semantics:
          Green:  Online · Tracking / Online · Verified
          Yellow: Online · Pending  / Offline · Local
          Red:    Cloud Off · Local
        """
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
        # Check for an externally set pending/verified flag (set by _on_status_overlay_show)
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
        """Handle an externally-triggered status update.

        The message is expected to be one of the agreed status texts.  When
        cloud/leaderboard code submits a score it can emit status_overlay_show
        with the relevant state.  The badge is kept persistent; callers must
        not rely on auto-dismiss behavior.
        """
        if not bool(self.cfg.OVERLAY.get("status_overlay_enabled", True)):
            return
        # Map message/color to our known state flags so _determine_status_state
        # can pick them up during the next poll cycle.
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
        # Also pass the explicit color if provided
        if color_hex:
            txt = str(message or "").strip()
            self._status_badge_explicit = (txt, color_hex)
        else:
            self._status_badge_explicit = None
        # Force an immediate badge refresh via the poll timer mechanism
        self._poll_status_badge()

    def _poll_status_badge(self):
        """Poll game state and show/update/hide the status badge accordingly.

        Called every ~2 seconds by ``_status_badge_timer``.  Also called
        directly from ``_on_status_overlay_show`` for immediate feedback.
        """
        try:
            if not bool(self.cfg.OVERLAY.get("status_overlay_enabled", True)):
                if hasattr(self, "_status_overlay") and self._status_overlay:
                    self._status_overlay.hide_badge()
                return
            in_game = self._in_game_now()
            if not in_game:
                if hasattr(self, "_status_overlay") and self._status_overlay:
                    self._status_overlay.hide_badge()
                # Reset transient state flags when leaving a game
                self._status_badge_state = None
                self._status_badge_explicit = None
                return
            # Determine what to show
            explicit = getattr(self, "_status_badge_explicit", None)
            if explicit:
                txt, color = explicit
            else:
                txt, color = self._determine_status_state()
            if not hasattr(self, "_status_overlay") or self._status_overlay is None:
                self._status_overlay = StatusOverlay(self)
            self._status_overlay.update_status(txt, color)
        except Exception:
            pass

    def _open_challenge_select_overlay(self):
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self.bridge.challenge_info_show.emit(
                    "Challenge can only be started in-game.",
                    3,
                    "#FF3B30"
                )
            except Exception:
                pass
            return

        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            if not current_rom or not self.watcher._has_any_map(current_rom):
                try:
                    self.bridge.challenge_info_show.emit(
                        "Challenges disabled: No NVRAM map found for this table.",
                        4,
                        "#FF3B30"
                    )
                    self.bridge.challenge_speak.emit("Challenge disabled. Map missing.")
                except Exception:
                    pass
                return
        except Exception:
            pass

        try:
            if getattr(self, "_challenge_select", None):
                try:
                    self._challenge_select.close()
                    self._challenge_select.deleteLater()
                except Exception:
                    pass
            self._challenge_select = ChallengeSelectOverlay(self, selected_idx=int(self._ch_ov_selected_idx))
            self._challenge_select.show()
            self._challenge_select.raise_()
            if self._ch_active_source is None and self._last_ch_event_src:
                self._ch_active_source = self._last_ch_event_src
            try:
                import time as _time
                self._ch_ov_opened_at = _time.monotonic()
            except Exception:
                self._ch_ov_opened_at = 0.0
        except Exception as e:
            try:
                log(self.cfg, f"[UI] open ChallengeSelectOverlay failed: {e}", "WARN")
            except Exception:
                pass

    def _close_challenge_select_overlay(self):
        try:
            if getattr(self, "_challenge_select", None):
                self._challenge_select.hide()
                self._challenge_select.close()
                self._challenge_select.deleteLater()
        except Exception:
            pass
        self._challenge_select = None
        self._ch_active_source = None
        try:
            self._ch_ov_opened_at = 0.0
        except Exception:
            pass

    def _close_secondary_overlays(self):
        """Close all secondary overlay windows (NOT the main overlay) when VPX exits."""
        for attr in ('_challenge_timer', '_challenge_select', '_flip_diff_select',
                     '_flip_total_win', '_heat_bar_win'):
            win = getattr(self, attr, None)
            if win is not None:
                try:
                    win.close()
                    win.deleteLater()
                except Exception:
                    pass
                setattr(self, attr, None)
        if getattr(self, '_status_overlay', None) is not None:
            try:
                self._status_overlay.close()
                self._status_overlay.deleteLater()
            except Exception:
                pass
            self._status_overlay = None
        # NOTE: _ach_toast_mgr and _mini_overlay are intentionally NOT cleared here.
        # Both are post-game notifications that must survive VPX exit:
        # - _ach_toast_mgr: achievement toasts fired by _persist_and_toast_achievements()
        # - _mini_overlay: challenge score overlay emitted by _challenge_record_result()

    def _refresh_challenge_select_overlay(self):
        ovw = getattr(self, "_challenge_select", None)
        if ovw:
            try:
                ovw.apply_portrait_from_cfg()
            except Exception:
                pass
                
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
            if tries["n"] < 8:
                QTimer.singleShot(250, _retry)
        QTimer.singleShot(250, _retry)

    def _on_challenge_timer_start(self, total_seconds: int):
        try:
            sound.play_sound(self.cfg, "challenge_start")
        except Exception:
            pass
        try:
            try:
                if hasattr(self, "_challenge_timer_delay") and self._challenge_timer_delay:
                    self._challenge_timer_delay.stop()
                    self._challenge_timer_delay.deleteLater()
            except Exception:
                pass
            self._challenge_timer_delay = None

            try:
                if hasattr(self, "_challenge_timer") and self._challenge_timer:
                    self._challenge_timer.close()
                    self._challenge_timer.deleteLater()
            except Exception:
                pass
            self._challenge_timer = None
            warmup_sec = int(getattr(self, "_ch_warmup_sec", 10))
            play_sec = max(1, int(total_seconds or 0) - warmup_sec)

            self._challenge_timer_delay = QTimer(self)
            self._challenge_timer_delay.setSingleShot(True)

            def _spawn():
                try:
                    if hasattr(self, "_challenge_timer") and self._challenge_timer:
                        self._challenge_timer.close()
                        self._challenge_timer.deleteLater()
                except Exception:
                    pass
                self._challenge_timer = None
                try:
                    log(self.cfg, f"[CHALLENGE] countdown spawn – seconds={play_sec}")
                except Exception:
                    pass
                try:
                    # Show 3…2…1…GO! countdown before the actual challenge timer
                    csd = ChallengeStartCountdown(None)
                    csd.finished.connect(lambda: _launch_timer(csd))
                    csd.start()
                except Exception:
                    _launch_timer(None)

            def _launch_timer(csd_widget=None):
                try:
                    if csd_widget is not None:
                        csd_widget.close()
                except Exception:
                    pass
                try:
                    self._challenge_timer = ChallengeCountdownOverlay(self, play_sec)
                    try:
                        if getattr(self, "_trophie_overlay", None):
                            _ov = self._trophie_overlay
                            self._challenge_timer._tick_callback = lambda ms: _ov.on_challenge_timer_tick(ms)
                    except Exception:
                        pass
                except Exception:
                    self._challenge_timer = None

            self._challenge_timer_delay.timeout.connect(lambda: QTimer.singleShot(0, _spawn))
            self._challenge_timer_delay.start(warmup_sec * 1000)
        except Exception:
            pass

    def _on_ch_timer_test(self):
        try:
            win = ChallengeCountdownOverlay(self, total_seconds=10)
            try:
                win._kill_vpx = lambda: (win.close())
            except Exception:
                pass
            QTimer.singleShot(12000, lambda: (win.close() if hasattr(win, "close") else None))
        except Exception:
            pass
            
    def _on_ch_ov_test(self):
        try:
            if getattr(self, "_challenge_select_test", None):
                try:
                    self._challenge_select_test.close()
                    self._challenge_select_test.deleteLater()
                except Exception:
                    pass
            self._challenge_select_test = ChallengeSelectOverlay(self, selected_idx=int(self._ch_ov_selected_idx))
            self._challenge_select_test.show()
            self._challenge_select_test.raise_()

            def _close_test():
                try:
                    w = getattr(self, "_challenge_select_test", None)
                    if w:
                        w.close()
                        w.deleteLater()
                except Exception:
                    pass
                self._challenge_select_test = None

            QTimer.singleShot(5000, _close_test)
        except Exception:
            pass

    def _start_selected_challenge(self):
        idx = int(getattr(self, "_ch_ov_selected_idx", 0) or 0) % 4
        try:
            has_map = False
            try:
                current_rom = getattr(self.watcher, "current_rom", None)
                has_map = bool(current_rom and self.watcher._has_any_map(current_rom))
            except Exception:
                has_map = True
            if not has_map:
                return
            if idx == 0:
                self.watcher.start_timed_challenge()
            elif idx == 2:
                self.watcher.start_heat_challenge()
            elif idx == 1:
                self.watcher.start_flip_challenge(500)
        except Exception:
            pass

    def _challenge_binding_label_text(self, kind: str) -> str:
        if kind == "hotkey":
            src = str(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_hotkey_joy_button", 3))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_hotkey_vk", 0x7A))
            mods = int(self.cfg.OVERLAY.get("challenge_hotkey_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        if kind == "left":
            src = str(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_left_joy_button", 4))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_left_vk", 0x25))
            mods = int(self.cfg.OVERLAY.get("challenge_left_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        if kind == "right":
            src = str(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")).lower()
            if src == "joystick":
                btn = int(self.cfg.OVERLAY.get("challenge_right_joy_button", 5))
                return f"Current: joystick button {btn}"
            vk = int(self.cfg.OVERLAY.get("challenge_right_vk", 0x27))
            mods = int(self.cfg.OVERLAY.get("challenge_right_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"
        return "Current: (none)"
        
    def _on_ch_volume_changed(self, val: int):
        self.lbl_ch_volume.setText(f"{val}%")
        self.cfg.OVERLAY["challenges_voice_volume"] = int(val)
        self.cfg.save()

    def _on_ch_mute_toggled(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["challenges_voice_mute"] = bool(is_checked)
        self.cfg.save()
    
    def _ch_results_path(self, rom: str) -> str:
        return os.path.join(self.cfg.BASE, "session_stats", "challenges", "history", f"{sanitize_filename(rom)}.json")

    def _open_flip_difficulty_overlay(self):
        def _do_open():
            # Hide challenge select after slide-out completes
            try:
                ovw = getattr(self, "_challenge_select", None)
                if ovw:
                    ovw.hide()
            except Exception:
                pass
            try:
                if getattr(self, "_flip_diff_select", None):
                    try:
                        self._flip_diff_select.close()
                        self._flip_diff_select.deleteLater()
                    except Exception:
                        pass
                self._flip_diff_select = FlipDifficultyOverlay(self, selected_idx=int(self._ch_flip_diff_idx),
                                                               options=list(self._flip_diff_options))
                self._flip_diff_select.show()
                self._flip_diff_select.raise_()
                self._ch_pick_flip_diff = True
            except Exception:
                self._flip_diff_select = None
                self._ch_pick_flip_diff = False

        try:
            ovw = getattr(self, "_challenge_select", None)
            if ovw:
                try:
                    ovw.start_slide_out(callback=_do_open)
                    return
                except Exception:
                    try:
                        ovw.hide()
                    except Exception:
                        pass
        except Exception:
            pass
        _do_open()

    def _close_flip_difficulty_overlay(self):
        try:
            if getattr(self, "_flip_diff_select", None):
                self._flip_diff_select.hide()
                self._flip_diff_select.close()
                self._flip_diff_select.deleteLater()
        except Exception:
            pass
        self._flip_diff_select = None
        self._ch_pick_flip_diff = False

    def _on_challenge_hotkey(self):
        try:
            import time as _time
            debounce_ms_cfg = int(self.cfg.OVERLAY.get("ch_hotkey_debounce_ms", 120))
            debounce_ms = max(120, debounce_ms_cfg)
            now = _time.monotonic()
            last = float(getattr(self, "_last_ch_hotkey_ts", 0.0) or 0.0)
            if debounce_ms > 0 and (now - last) < (debounce_ms / 1000.0):
                return
            self._last_ch_hotkey_ts = now
        except Exception:
            pass

        if not self._in_game_now():
            # If a duel invite notification is showing in the mini overlay, ignore
            # the hotkey — Left/Right handle accept/decline directly.
            try:
                if getattr(self, "_duel_invite_notify_state", None) is not None:
                    return  # ignore hotkey while duel invite notification is showing
            except Exception:
                pass
            # Legacy DuelInviteOverlay fallback (no longer shown for GUI-hidden case).
            try:
                overlay = getattr(self, "_duel_invite_overlay", None)
                if overlay is not None and overlay.isVisible():
                    overlay.confirm_focused()
                    return
            except Exception:
                pass
            # If the in-tab duel alert bar is visible, click the focused button.
            # (alert bar removed — this block is kept as no-op for compatibility)
            try:
                pass
            except Exception:
                pass
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            try:
                self.bridge.challenge_info_show.emit(
                    "Challenge can only be started in-game.",
                    3,
                    "#FF3B30"
                )
            except Exception:
                pass
            return

        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            _has_map = bool(current_rom and self.watcher._has_any_map(current_rom))
        except Exception:
            _has_map = True

        if not _has_map:
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            try:
                self.bridge.challenge_info_show.emit(
                    "No NVRAM map available. Challenges require a map for score.",
                    3,
                    "#FF3B30"
                )
            except Exception:
                pass
            return

        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                name, flips = self._flip_diff_select.selected_option()
            except Exception:
                name, flips = ("Medium", 400)
            if int(flips) == -1:
                # Back/cancel: close flip difficulty overlay and re-show challenge select
                self._close_flip_difficulty_overlay()
                try:
                    ovw = getattr(self, "_challenge_select", None)
                    if ovw:
                        ovw.show()
                        ovw.raise_()
                    else:
                        self._open_challenge_select_overlay()
                except Exception:
                    pass
                return
            self._close_flip_difficulty_overlay()
            self._close_challenge_select_overlay()
            try:
                self.watcher.start_flip_challenge(int(flips))
            except Exception:
                pass
            return

        ovw = getattr(self, "_challenge_select", None)
        if ovw and ovw.isVisible():
            sel = int(getattr(self, "_ch_ov_selected_idx", 0) or 0) % 4
            if sel == 3:
                self._close_challenge_select_overlay()
                return
            elif sel == 0:
                self._close_challenge_select_overlay()
                try:
                    self.watcher.start_timed_challenge()
                except Exception:
                    pass
                return
            elif sel == 2:
                self._close_challenge_select_overlay()
                try:
                    self.watcher.start_heat_challenge()
                except Exception:
                    pass
                return
            else:
                self._open_flip_difficulty_overlay()
                return
        self._open_challenge_select_overlay()

    def _on_challenge_left(self):
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
                # Mark as handled to prevent double notification (Fix 4)
                if not hasattr(self, "_duel_invite_handled_ids"):
                    self._duel_invite_handled_ids = set()
                self._duel_invite_handled_ids.add(duel_id)
                self._duel_invite_notify_cancel()
                try:
                    self._get_mini_overlay().hide()
                except Exception:
                    pass
                try:
                    self._on_inbox_accept(duel_id)
                except Exception:
                    pass
                return
        except Exception:
            pass
        # Legacy DuelInviteOverlay fallback (no longer shown for GUI-hidden case).
        try:
            overlay = getattr(self, "_duel_invite_overlay", None)
            if overlay is not None and overlay.isVisible():
                if overlay.is_accept_focused():
                    overlay.focus_decline()
                else:
                    overlay.focus_accept()
                return
        except Exception:
            pass
        # Alert bar removed — skip duel alert frame focus toggle
        # Challenge left/right no longer navigates overlay pages
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            return
        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            if not (current_rom and self.watcher._has_any_map(current_rom)):
                # No NVRAM map – only allow navigating between Heat (2) and Exit (3)
                current = int(self._ch_ov_selected_idx) % 4
                if current == 3:
                    self._ch_ov_selected_idx = 2
                    ovw = getattr(self, "_challenge_select", None)
                    if ovw and ovw.isVisible():
                        try:
                            ovw.set_selected(2)
                        except Exception:
                            pass
                return
        except Exception:
            pass
        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                n = len(self._flip_diff_options)
                self._ch_flip_diff_idx = (int(self._ch_flip_diff_idx) - 1) % n
                self._flip_diff_select.set_selected(self._ch_flip_diff_idx)
            except Exception:
                pass
            return
        ovw = getattr(self, "_challenge_select", None)
        if not (ovw and ovw.isVisible()):
            return
        src = getattr(self, "_last_ch_event_src", None)
        if self._ch_active_source and src and self._ch_active_source != src:
            self._ch_active_source = src
        self._ch_ov_selected_idx = (int(self._ch_ov_selected_idx) - 1) % 4
        try:
            ovw.set_selected(self._ch_ov_selected_idx)
        except Exception:
            pass

    def _on_challenge_right(self):
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
                # Mark as handled to prevent double notification (Fix 4)
                if not hasattr(self, "_duel_invite_handled_ids"):
                    self._duel_invite_handled_ids = set()
                self._duel_invite_handled_ids.add(duel_id)
                self._duel_invite_notify_cancel()
                try:
                    self._get_mini_overlay().hide()
                except Exception:
                    pass
                try:
                    self._on_inbox_decline(duel_id)
                except Exception:
                    pass
                return
        except Exception:
            pass
        # Legacy DuelInviteOverlay fallback (no longer shown for GUI-hidden case).
        try:
            overlay = getattr(self, "_duel_invite_overlay", None)
            if overlay is not None and overlay.isVisible():
                if overlay.is_accept_focused():
                    overlay.focus_decline()
                else:
                    overlay.focus_accept()
                return
        except Exception:
            pass
        # Alert bar removed — skip duel alert frame focus toggle
        # Challenge left/right no longer navigates overlay pages
        if self._challenge_is_active():
            return
        if not self._in_game_now():
            try:
                self._close_challenge_select_overlay()
                self._close_flip_difficulty_overlay()
            except Exception:
                pass
            return
        try:
            current_rom = getattr(self.watcher, "current_rom", None)
            if not (current_rom and self.watcher._has_any_map(current_rom)):
                # No NVRAM map – only allow navigating between Heat (2) and Exit (3)
                current = int(self._ch_ov_selected_idx) % 4
                if current == 2:
                    self._ch_ov_selected_idx = 3
                    ovw = getattr(self, "_challenge_select", None)
                    if ovw and ovw.isVisible():
                        try:
                            ovw.set_selected(3)
                        except Exception:
                            pass
                return
        except Exception:
            pass
        if getattr(self, "_ch_pick_flip_diff", False) and getattr(self, "_flip_diff_select", None):
            try:
                n = len(self._flip_diff_options)
                self._ch_flip_diff_idx = (int(self._ch_flip_diff_idx) + 1) % n
                self._flip_diff_select.set_selected(self._ch_flip_diff_idx)
            except Exception:
                pass
            return
        ovw = getattr(self, "_challenge_select", None)
        if not (ovw and ovw.isVisible()):
            return
        src = getattr(self, "_last_ch_event_src", None)
        if self._ch_active_source and src and self._ch_active_source != src:
            self._ch_active_source = src
        self._ch_ov_selected_idx = (int(self._ch_ov_selected_idx) + 1) % 4
        try:
            ovw.set_selected(self._ch_ov_selected_idx)
        except Exception:
            pass

    def _install_challenge_key_handling(self):
        try:
            if getattr(self, "_challenge_keyhook", None):
                try:
                    self._challenge_keyhook.uninstall()
                except Exception:
                    pass
        except Exception:
            pass
        self._challenge_keyhook = None
        if getattr(self.cfg, "LOG_CTRL", False):
            log(self.cfg, "[HOTKEY] challenge low-level hook disabled (using WM_HOTKEY)")

    def _speak_en(self, text: str):
        try:
            if bool(self.cfg.OVERLAY.get("challenges_voice_mute", False)):
                return

            vol = int(self.cfg.OVERLAY.get("challenges_voice_volume", 80))
            vol = max(0, min(100, vol))
            try:
                import win32com.client 
                sp = win32com.client.Dispatch("SAPI.SpVoice")
                sp.Volume = vol
                sp.Speak(str(text))
                return
            except Exception:
                pass
        except Exception:
            pass

    def _on_challenge_warmup_show(self, seconds: int, message: str):
        try:
            try:
                self._ch_warmup_sec = int(seconds)
            except Exception:
                self._ch_warmup_sec = 10

            if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                self._mini_overlay = MiniInfoOverlay(self)
            self._mini_overlay.show_info(str(message), max(1, int(seconds)), color_hex="#FF3B30")
            if not hasattr(self, "_ch_last_spoken"):
                self._ch_last_spoken = {}
            now = time.time()
            last = float(self._ch_last_spoken.get("timed", 0.0) or 0.0)
            if now - last > 2.0:
                QTimer.singleShot(0, lambda: self._speak_en("Timed challenge started"))
                self._ch_last_spoken["timed"] = now
        except Exception:
            pass

    def _on_challenge_timer_stop(self):
        try:
            if hasattr(self, "_challenge_timer_delay") and self._challenge_timer_delay:
                self._challenge_timer_delay.stop()
                self._challenge_timer_delay.deleteLater()
        except Exception:
            pass
        self._challenge_timer_delay = None

        try:
            if hasattr(self, "_challenge_timer") and self._challenge_timer:
                self._challenge_timer.close()
                self._challenge_timer.deleteLater()
        except Exception:
            pass
        self._challenge_timer = None

    def _on_challenge_info_show(self, message: str, seconds: int, color_hex: str = "#FFFFFF"):
        try:
            msg_lower = str(message or "").lower()
            col = str(color_hex or "").upper()
            if "challenge complete" in msg_lower or "time's up" in msg_lower:
                sound.play_sound(self.cfg, "challenge_complete")
            elif col == "#FF3B30" or "aborted" in msg_lower or "fail" in msg_lower:
                sound.play_sound(self.cfg, "challenge_fail")
        except Exception:
            pass
        try:
            if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
                self._mini_overlay = MiniInfoOverlay(self)
            self._mini_overlay.show_info(str(message), max(1, int(seconds)), color_hex=str(color_hex or "#FFFFFF"))
        except Exception:
            pass
        try:
            self._update_challenges_results_view()
        except Exception:
            pass

    def _on_challenge_speak(self, phrase: str):
        self._speak_en(str(phrase or ""))
