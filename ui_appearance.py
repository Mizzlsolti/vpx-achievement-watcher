from __future__ import annotations

import ctypes
import os
import threading

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFontComboBox, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSlider, QSpinBox, QTabWidget, QTableWidget, QVBoxLayout,
    QWidget,
)

try:
    import win32gui
except Exception:
    win32gui = None

from ui_overlay import (
    ChallengeCountdownOverlay, ChallengeOVPositionPicker,
    ChallengeSelectOverlay, ChallengeStartCountdown,
    FlipCounterOverlay, FlipCounterPositionPicker, FlipDifficultyOverlay,
    HeatBarometerOverlay, HeatBarPositionPicker,
    MiniInfoOverlay, MiniInfoPositionPicker, OverlayPositionPicker,
    StatusOverlay, TimerPositionPicker, ToastPositionPicker,
)
from theme import DEFAULT_THEME, generate_stylesheet, get_theme, get_theme_color, list_themes
from watcher_core import ensure_dir, log, vk_to_name_en
import sound


class AppearanceMixin:
    """Mixin for MainWindow that provides the Appearance tab (Overlay/Theme/Sound sub-tabs)
    and all related overlay placement, theme, and sound helpers."""

    # ==========================================
    # OVERLAY REGISTRATION & HANDLERS
    # ==========================================

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

    def _on_heat_bar_hide(self):
        try:
            if self._heat_bar_win:
                self._heat_bar_win.close()
                self._heat_bar_win.deleteLater()
        except Exception:
            pass
        self._heat_bar_win = None

    def _on_heat_bar_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["heat_bar_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if isinstance(self._heat_bar_picker, HeatBarPositionPicker):
                self._heat_bar_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_heat_bar_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["heat_bar_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if isinstance(self._heat_bar_picker, HeatBarPositionPicker):
                self._heat_bar_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_heat_bar_place_clicked(self):
        picker = getattr(self, "_heat_bar_picker", None)
        if picker:
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()

            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("heat_bar_portrait", ov.get("portrait_mode", False)))
            if portrait:
                self.cfg.OVERLAY["heat_bar_x_portrait"] = int(x)
                self.cfg.OVERLAY["heat_bar_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["heat_bar_x_landscape"] = int(x)
                self.cfg.OVERLAY["heat_bar_y_landscape"] = int(y)
            self.cfg.OVERLAY["heat_bar_saved"] = True
            self.cfg.OVERLAY["heat_bar_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._heat_bar_picker = None
            self.btn_heat_bar_place.setText("Place / Save Heat Bar position")
            return
        self._heat_bar_picker = HeatBarPositionPicker(self, width_hint=48, height_hint=260)
        self.btn_heat_bar_place.setText("Save Heat Bar position")

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

    def _on_flip_total_hide(self):
        try:
            if self._flip_total_win:
                self._flip_total_win.close()
                self._flip_total_win.deleteLater()
        except Exception:
            pass
        self._flip_total_win = None
        
    def _in_game_now(self) -> bool:
        try:
            w = getattr(self, "watcher", None)
            return bool(w and (w.game_active or w._vp_player_visible()))
        except Exception:
            return False
  
    def _on_flip_counter_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["flip_counter_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass
            
    def _on_flip_counter_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["flip_counter_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass            
            
    def _on_flip_counter_place_clicked(self):
        picker = getattr(self, "_flip_counter_picker", None)
        if picker:
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()

            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["flip_counter_x_portrait"] = int(x)
                self.cfg.OVERLAY["flip_counter_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["flip_counter_x_landscape"] = int(x)
                self.cfg.OVERLAY["flip_counter_y_landscape"] = int(y)
            self.cfg.OVERLAY["flip_counter_saved"] = True
            self.cfg.OVERLAY["flip_counter_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._flip_counter_picker = None
            self.btn_flip_counter_place.setText("Place / Save Flip-Counter position")
            return
        self._flip_counter_picker = FlipCounterPositionPicker(self, width_hint=380, height_hint=130)
        self.btn_flip_counter_place.setText("Save Flip-Counter position")

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
 
    def _get_hotkey_mods_now(self) -> int:
        import ctypes
        user32 = ctypes.windll.user32

        def pressed(vk: int) -> bool:
            state = user32.GetKeyState(vk)
            return (state & 0x8000) != 0

        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_WIN = 0x0008

        mods = 0
        if pressed(0x10) or pressed(0xA0) or pressed(0xA1):  # Shift / LShift / RShift
            mods |= MOD_SHIFT
        if pressed(0x11) or pressed(0xA2) or pressed(0xA3):  # Ctrl / LCtrl / RCtrl
            mods |= MOD_CONTROL
        if pressed(0x12) or pressed(0xA4) or pressed(0xA5):  # Alt / LAlt / RAlt
            mods |= MOD_ALT
        if pressed(0x5B) or pressed(0x5C):                   # Win links/rechts
            mods |= MOD_WIN

        return mods

    def _fmt_hotkey_label(self, vk: int, mods: int) -> str:
        parts = []
        if mods & 0x0002: parts.append("Ctrl")
        if mods & 0x0004: parts.append("Shift")
        if mods & 0x0001: parts.append("Alt")
        if mods & 0x0008: parts.append("Win")
        parts.append(vk_to_name_en(int(vk)))
        return "+".join(parts)
 
    def _on_overlay_auto_close_toggle(self, state: int):
        enabled = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["overlay_auto_close"] = bool(enabled)
        self.cfg.save()
        try:
            if enabled and self.overlay and self.overlay.isVisible():
                self._start_overlay_auto_close_timer()
            else:
                self.overlay_auto_close_timer.stop()
        except Exception:
            pass

    def _start_overlay_auto_close_timer(self):
        try:
            if bool(self.cfg.OVERLAY.get("overlay_auto_close", False)):
                self.overlay_auto_close_timer.stop()
                self.overlay_auto_close_timer.start(60 * 1000)
        except Exception:
            pass
            
    def _on_ch_ov_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_ov_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_ov_picker") and isinstance(self._ch_ov_picker, ChallengeOVPositionPicker):
                self._ch_ov_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._refresh_challenge_select_overlay()
        self._update_switch_all_button_label()

    def _on_ch_ov_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_ov_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_ov_picker") and isinstance(self._ch_ov_picker, ChallengeOVPositionPicker):
                self._ch_ov_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._refresh_challenge_select_overlay()

    def _on_ch_ov_place_clicked(self):
        picker = getattr(self, "_ch_ov_picker", None)
        if picker and isinstance(picker, ChallengeOVPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ch_ov_x_portrait"] = int(x)
                self.cfg.OVERLAY["ch_ov_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ch_ov_x_landscape"] = int(x)
                self.cfg.OVERLAY["ch_ov_y_landscape"] = int(y)
            self.cfg.OVERLAY["ch_ov_saved"] = True
            self.cfg.OVERLAY["ch_ov_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._ch_ov_picker = None
            self.btn_ch_ov_place.setText("Place / Save ChallengeOV position")
            self._refresh_challenge_select_overlay()
            return
        self._ch_ov_picker = ChallengeOVPositionPicker(self, width_hint=520, height_hint=200)
        self.btn_ch_ov_place.setText("Save ChallengeOV position")
        
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

    def _on_ach_toast_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_ach_toast_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ach_toast_place_clicked(self):
        picker = getattr(self, "_toast_picker", None)
        if picker and isinstance(picker, ToastPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ach_toast_x_portrait"] = int(x)
                self.cfg.OVERLAY["ach_toast_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ach_toast_x_landscape"] = int(x)
                self.cfg.OVERLAY["ach_toast_y_landscape"] = int(y)
            self.cfg.OVERLAY["ach_toast_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._toast_picker = None
            self.btn_ach_toast_place.setText("Place / Save position")
            return

        self._toast_picker = ToastPositionPicker(self)
        self.btn_ach_toast_place.setText("Save position")

    def _on_mini_info_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["notifications_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_mini_info_picker") and isinstance(self._mini_info_picker, MiniInfoPositionPicker):
                self._mini_info_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_mini_info_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["notifications_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_mini_info_picker") and isinstance(self._mini_info_picker, MiniInfoPositionPicker):
                self._mini_info_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_mini_info_place_clicked(self):
        picker = getattr(self, "_mini_info_picker", None)
        if picker and isinstance(picker, MiniInfoPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["notifications_x_portrait"] = int(x)
                self.cfg.OVERLAY["notifications_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["notifications_x_landscape"] = int(x)
                self.cfg.OVERLAY["notifications_y_landscape"] = int(y)
            self.cfg.OVERLAY["notifications_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._mini_info_picker = None
            self.btn_mini_info_place.setText("Place / Save position")
            return
        
        self._mini_info_picker = MiniInfoPositionPicker(self, width_hint=420, height_hint=100)
        self.btn_mini_info_place.setText("Save position")

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

    def _on_status_overlay_enabled_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_enabled"] = bool(is_checked)
        self.cfg.save()

    def _on_status_overlay_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_status_overlay_picker") and isinstance(self._status_overlay_picker, StatusOverlayPositionPicker):
                self._status_overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_status_overlay_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_status_overlay_picker") and isinstance(self._status_overlay_picker, StatusOverlayPositionPicker):
                self._status_overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_status_overlay_place_clicked(self):
        picker = getattr(self, "_status_overlay_picker", None)
        if picker and isinstance(picker, StatusOverlayPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("status_overlay_portrait", False))
            if portrait:
                self.cfg.OVERLAY["status_overlay_x_portrait"] = int(x)
                self.cfg.OVERLAY["status_overlay_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["status_overlay_x_landscape"] = int(x)
                self.cfg.OVERLAY["status_overlay_y_landscape"] = int(y)
            self.cfg.OVERLAY["status_overlay_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._status_overlay_picker = None
            self.btn_status_overlay_place.setText("Place / Save position")
            return

        self._status_overlay_picker = StatusOverlayPositionPicker(self)
        self.btn_status_overlay_place.setText("Save position")

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
        cloud_url = str(getattr(self.cfg, "CLOUD_URL", "") or "").strip()
        if not cloud_enabled or not cloud_url:
            return ("Cloud Off · Local", "#FF3B30")
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
        if getattr(self, '_mini_overlay', None) is not None:
            try:
                self._mini_overlay.close()
                self._mini_overlay.deleteLater()
            except Exception:
                pass
            self._mini_overlay = None
        # NOTE: _ach_toast_mgr is intentionally NOT cleared here.
        # Achievement toasts are post-game notifications that must survive VPX exit,
        # because _persist_and_toast_achievements() runs AFTER the session ends.

    def _refresh_challenge_select_overlay(self):
        ovw = getattr(self, "_challenge_select", None)
        if ovw:
            try:
                ovw.apply_portrait_from_cfg()
            except Exception:
                pass
                
    def _on_ch_timer_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_timer_portrait"] = bool(is_checked)
        self.cfg.OVERLAY["flip_counter_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_timer_picker") and isinstance(self._ch_timer_picker, TimerPositionPicker):
                self._ch_timer_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        try:
            if hasattr(self, "_flip_counter_picker") and isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_ch_timer_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ch_timer_rotate_ccw"] = bool(is_ccw)
        self.cfg.OVERLAY["flip_counter_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_ch_timer_picker") and isinstance(self._ch_timer_picker, TimerPositionPicker):
                self._ch_timer_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        try:
            if hasattr(self, "_flip_counter_picker") and isinstance(self._flip_counter_picker, FlipCounterPositionPicker):
                self._flip_counter_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ch_timer_place_clicked(self):
        picker = getattr(self, "_ch_timer_picker", None)
        if picker and isinstance(picker, TimerPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ch_timer_x_portrait"] = int(x)
                self.cfg.OVERLAY["ch_timer_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ch_timer_x_landscape"] = int(x)
                self.cfg.OVERLAY["ch_timer_y_landscape"] = int(y)
            self.cfg.OVERLAY["ch_timer_saved"] = True
            self.cfg.OVERLAY["ch_timer_custom"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._ch_timer_picker = None
            self.btn_ch_timer_place.setText("Place / Save timer position")
            return
        self._ch_timer_picker = TimerPositionPicker(self, width_hint=400, height_hint=120)
        self.btn_ch_timer_place.setText("Save timer position")

    def _on_overlay_place_clicked(self):
        picker = getattr(self, "_overlay_picker", None)
        if picker and isinstance(picker, OverlayPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            self.cfg.OVERLAY["pos_x"] = int(x)
            self.cfg.OVERLAY["pos_y"] = int(y)
            self.cfg.OVERLAY["use_xy"] = True
            self.cfg.OVERLAY["overlay_pos_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._overlay_picker = None
            self.btn_overlay_place.setText("Place / Save overlay position")

            if self.overlay:
                self.overlay._apply_geometry()
                self.overlay._layout_positions()
                self.overlay.request_rotation(force=True)
            return
        self._overlay_picker = OverlayPositionPicker(self)
        self.btn_overlay_place.setText("Save position")

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

    def _first_screen_geometry(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                return screens[0].geometry()
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _msgbox_topmost(self, kind: str, title: str, text: str):
        box = QMessageBox(self)
        box.setWindowTitle(str(title))
        box.setText(str(text))
        box.setIcon(QMessageBox.Icon.Information if kind == "info" else QMessageBox.Icon.Warning)
        box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        box.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        box.setModal(True)
        box.show()
        box.raise_()
        return box.exec()

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
                except Exception:
                    self._challenge_timer = None

            self._challenge_timer_delay.timeout.connect(lambda: QTimer.singleShot(0, _spawn))
            self._challenge_timer_delay.start(warmup_sec * 1000)
        except Exception:
            pass

    def _repair_data_folders(self):
        try:
            ensure_dir(self.cfg.BASE)
            for sub in [
                os.path.join("tools", "NVRAM_Maps"),
                os.path.join("tools", "NVRAM_Maps", "maps"),
                "session_stats",
                os.path.join("Achievements", "rom_specific_achievements"),
            ]:
                ensure_dir(os.path.join(self.cfg.BASE, sub))
            try:
                self.watcher.bootstrap()
            except Exception as e:
                log(self.cfg, f"[REPAIR] bootstrap failed: {e}", "WARN")
            self._msgbox_topmost(
                "info", "Repair",
                "Base folders repaired.\n\nIf maps are still missing, please click 'Cache maps now (prefetch)'\n"
                "or simply start a ROM (maps will then be loaded on demand)."
            )
            log(self.cfg, "[REPAIR] base folders ensured and index/romnames fetched (if missing)")
        except Exception as e:
            log(self.cfg, f"[REPAIR] failed: {e}", "ERROR")
            self._msgbox_topmost("warn", "Repair", f"Repair failed:\n{e}")

    def _mods_for_vk(self, vk: int) -> int:
        return 0
            
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

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

    def _open_flip_difficulty_overlay(self):
        try:
            if getattr(self, "_challenge_select", None):
                try:
                    self._challenge_select.hide()
                except Exception:
                    pass
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
                    
    def _fmt_hms(self, seconds: int) -> str:
        try:
            seconds = int(seconds or 0)
        except Exception:
            seconds = 0
        d = seconds // 86400
        h = (seconds % 86400) // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if d > 0:
            return f"{d}d {h:02d}:{m:02d}:{s:02d}"
        return f"{h:02d}:{m:02d}:{s:02d}"
               

    # ==========================================
    # PREFETCH / THEME HELPERS
    # ==========================================

    def _prefetch_maps_now(self):
        try:
            self.watcher.start_prefetch_background()
            maps_dir = os.path.join(self.cfg.BASE, "tools", "NVRAM_Maps", "maps")
            QMessageBox.information(
                self, "Prefetch",
                f"Prefetch started. Missing maps are being cached in the background at:\n"
                f"{maps_dir}\n"
                "See watcher.log for progress."
            )
            log(self.cfg, "[PREFETCH] started by user")
        except Exception as e:
            log(self.cfg, f"[PREFETCH] failed: {e}", "ERROR")
            QMessageBox.warning(self, "Prefetch", f"Prefetch failed:\n{e}")
    def _style(self, widget, css: str):
        try:
            if widget:
                widget.setStyleSheet(css)
        except Exception:
            pass

    def _apply_theme(self):
        app = QApplication.instance()
        # Fusion ist die beste Basis für starke Custom-Themes
        app.setStyle("Fusion")

        theme_id = (self.cfg.OVERLAY or {}).get("theme", DEFAULT_THEME)
        app.setStyleSheet(generate_stylesheet(theme_id))

        self._style(getattr(self, "btn_minimize", None), "background:#005c99; color:white; border:none;")
        self._style(getattr(self, "btn_quit", None), "background:#8a2525; color:white; border:none;")
        self._style(getattr(self, "btn_restart", None), "background:#008040; color:white; border:none;")

    def _on_apply_theme(self):
        theme_id = self.cmb_theme.currentData()
        if not theme_id:
            theme_id = DEFAULT_THEME
        self.cfg.OVERLAY["theme"] = theme_id
        self.cfg.save()
        app = QApplication.instance()
        app.setStyleSheet(generate_stylesheet(theme_id))
        self._style(getattr(self, "btn_minimize", None), "background:#005c99; color:white; border:none;")
        self._style(getattr(self, "btn_quit", None), "background:#8a2525; color:white; border:none;")
        self._style(getattr(self, "btn_restart", None), "background:#008040; color:white; border:none;")
        self._update_theme_preview(theme_id)

    def _on_theme_combo_changed(self, _index: int):
        theme_id = self.cmb_theme.currentData()
        if theme_id:
            self._update_theme_preview(theme_id)

    def _update_theme_preview(self, theme_id: str):
        t = get_theme(theme_id)
        primary = t.get("primary", "#00E5FF")
        for key, swatch in getattr(self, "_theme_color_boxes", {}).items():
            color = t.get(key, "#000000")
            swatch.setStyleSheet(
                f"background-color: {color}; border: 1px solid #555; border-radius: 4px;"
            )
        desc = t.get("description", "")
        lbl_desc = getattr(self, "lbl_theme_description", None)
        if lbl_desc is not None:
            lbl_desc.setText(desc)
            lbl_desc.setStyleSheet(f"color: {primary}; font-size: 9pt; font-style: italic;")
        lbl_active = getattr(self, "lbl_active_theme", None)
        if lbl_active is not None:
            lbl_active.setStyleSheet(f"color: {primary}; font-weight: bold; font-size: 10pt;")
        for dot in getattr(self, "_theme_dot_labels", []):
            dot.setStyleSheet(f"color: {primary}; font-size: 14pt;")

    def _on_theme_toast_test(self):
        try:
            sound.play_sound(self.cfg, "achievement_unlock")
        except Exception:
            pass
        try:
            self._ach_toast_mgr.enqueue("TEST – Achievement Unlock", "test_rom", 5)
        except Exception:
            pass

    def _on_theme_timer_test(self):
        try:
            sound.play_sound(self.cfg, "challenge_start")
        except Exception:
            pass
        self._on_ch_timer_test()


    # ==========================================
    # TAB: APPEARANCE
    # ==========================================

    def _build_tab_appearance(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        self.appearance_subtabs = QTabWidget()
        tab_layout.addWidget(self.appearance_subtabs)

        # ── Overlay sub-tab ────────────────────────────────────────────────────
        overlay_tab = QWidget()
        overlay_tab_layout = QVBoxLayout(overlay_tab)
        overlay_tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        scroll.setWidget(inner)
        overlay_tab_layout.addWidget(scroll)

        grp_style = QGroupBox("Global Styling")
        lay_style = QGridLayout(grp_style)
        
        self.cmb_font_family = QFontComboBox()
        self.cmb_font_family.setCurrentFont(QFont(self.cfg.OVERLAY.get("font_family", "Segoe UI")))
        self.cmb_font_family.currentFontChanged.connect(self._on_font_family_changed)
        
        self.spn_font_size = QSpinBox()
        self.spn_font_size.setRange(8, 64)
        self.spn_font_size.setValue(int(self.cfg.OVERLAY.get("base_body_size", 20)))
        self.spn_font_size.valueChanged.connect(self._on_font_size_changed)

        self.sld_scale = QSlider(Qt.Orientation.Horizontal)
        self.sld_scale.setMinimum(30); self.sld_scale.setMaximum(300)
        self.sld_scale.setValue(int(self.cfg.OVERLAY.get("scale_pct", 100)))
        self.sld_scale.valueChanged.connect(self._on_overlay_scale)
        self.lbl_scale = QLabel(f"{self.sld_scale.value()}%")
        self.btn_scale_reset = QPushButton("100%")
        self.btn_scale_reset.setToolTip("Reset Overlay Scale to 100%")
        self.btn_scale_reset.clicked.connect(lambda: self.sld_scale.setValue(100))

        lay_style.addWidget(QLabel("Overlay Scale:"), 0, 0)
        lay_style.addWidget(self.sld_scale, 0, 1)
        lay_style.addWidget(self.lbl_scale, 0, 2)
        lay_style.addWidget(self.btn_scale_reset, 0, 3)

        lay_style.addWidget(QLabel("Font Family:"), 1, 0)
        lay_style.addWidget(self.cmb_font_family, 1, 1)
        lay_style.addWidget(QLabel("Base Size:"), 1, 2)
        lay_style.addWidget(self.spn_font_size, 1, 3)

        layout.addWidget(grp_style)

        grp_pos = QGroupBox("Widget Placement & Orientation")
        lay_pos = QGridLayout(grp_pos)

        self.btn_switch_all_orientation = QPushButton("🔄 Switch All → Portrait")
        self.btn_switch_all_orientation.setStyleSheet(
            "QPushButton { background: #FF7F00; color: #000; font-weight: bold; padding: 6px 16px; border-radius: 6px; font-size: 10pt; }"
            "QPushButton:hover { background: #FFA040; }"
        )
        self.btn_switch_all_orientation.clicked.connect(self._on_switch_all_portrait_landscape)
        _row_switch = QHBoxLayout()
        _row_switch.addWidget(self.btn_switch_all_orientation)
        _row_switch.addStretch(1)
        lay_pos.addLayout(_row_switch, 0, 0, 1, 2)

        def create_overlay_box(title, chk_port, chk_ccw, btn_place, btn_test=None, btn_hide=None, extra=None):
            box = QVBoxLayout()
            box.addWidget(QLabel(f"<b>{title}</b>"))
            box.addWidget(chk_port); box.addWidget(chk_ccw)
            btns = QHBoxLayout(); btns.addWidget(btn_place)
            if btn_test: btns.addWidget(btn_test)
            if btn_hide: btns.addWidget(btn_hide)
            box.addLayout(btns)
            if extra: box.addWidget(extra)
            box.addStretch(1)
            return box

        # 1) Main Overlay
        self.chk_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_portrait.setChecked(bool(self.cfg.OVERLAY.get("portrait_mode", True))); self.chk_portrait.stateChanged.connect(self._on_portrait_toggle)
        self.chk_portrait_ccw = QCheckBox("Rotate CCW"); self.chk_portrait_ccw.setChecked(bool(self.cfg.OVERLAY.get("portrait_rotate_ccw", True))); self.chk_portrait_ccw.stateChanged.connect(self._on_portrait_ccw_toggle)
        self.btn_overlay_place = QPushButton("Place"); self.btn_overlay_place.clicked.connect(self._on_overlay_place_clicked)
        self.btn_toggle_now = QPushButton("Test"); self.btn_toggle_now.clicked.connect(self._on_overlay_test_clicked)
        self.btn_hide = QPushButton("Hide"); self.btn_hide.clicked.connect(self._hide_overlay)
        self.chk_overlay_auto_close = QCheckBox("Auto-Close 1 min"); self.chk_overlay_auto_close.setChecked(bool(self.cfg.OVERLAY.get("overlay_auto_close", False))); self.chk_overlay_auto_close.stateChanged.connect(self._on_overlay_auto_close_toggle)
        box_main = create_overlay_box("Main Stats Overlay", self.chk_portrait, self.chk_portrait_ccw, self.btn_overlay_place, self.btn_toggle_now, self.btn_hide, self.chk_overlay_auto_close)

        # 2) Toasts
        self.chk_ach_toast_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ach_toast_portrait.setChecked(bool(self.cfg.OVERLAY.get("ach_toast_portrait", True))); self.chk_ach_toast_portrait.stateChanged.connect(self._on_ach_toast_portrait_toggle)
        self.chk_ach_toast_ccw = QCheckBox("Rotate CCW"); self.chk_ach_toast_ccw.setChecked(bool(self.cfg.OVERLAY.get("ach_toast_rotate_ccw", True))); self.chk_ach_toast_ccw.stateChanged.connect(self._on_ach_toast_ccw_toggle)
        self.btn_ach_toast_place = QPushButton("Place"); self.btn_ach_toast_place.clicked.connect(self._on_ach_toast_place_clicked)
        self.btn_test_toast = QPushButton("Test"); self.btn_test_toast.clicked.connect(lambda: self._ach_toast_mgr.enqueue("TEST – Achievement", "test_rom", 5))
        box_toast = create_overlay_box("Achievement Toasts", self.chk_ach_toast_portrait, self.chk_ach_toast_ccw, self.btn_ach_toast_place, self.btn_test_toast)

        # 3) Challenge Menu
        self.chk_ch_ov_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ch_ov_portrait.setChecked(bool(self.cfg.OVERLAY.get("ch_ov_portrait", True))); self.chk_ch_ov_portrait.stateChanged.connect(self._on_ch_ov_portrait_toggle)
        self.chk_ch_ov_ccw = QCheckBox("Rotate CCW"); self.chk_ch_ov_ccw.setChecked(bool(self.cfg.OVERLAY.get("ch_ov_rotate_ccw", True))); self.chk_ch_ov_ccw.stateChanged.connect(self._on_ch_ov_ccw_toggle)
        self.btn_ch_ov_place = QPushButton("Place"); self.btn_ch_ov_place.clicked.connect(self._on_ch_ov_place_clicked)
        self.btn_ch_ov_test = QPushButton("Test"); self.btn_ch_ov_test.clicked.connect(self._on_ch_ov_test)
        box_ch_sel = create_overlay_box("Challenge Menu", self.chk_ch_ov_portrait, self.chk_ch_ov_ccw, self.btn_ch_ov_place, self.btn_ch_ov_test)

        # 4) Timers & Counters
        self.chk_ch_timer_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ch_timer_portrait.setChecked(bool(self.cfg.OVERLAY.get("ch_timer_portrait", True))); self.chk_ch_timer_portrait.stateChanged.connect(self._on_ch_timer_portrait_toggle)
        self.chk_ch_timer_ccw = QCheckBox("Rotate CCW"); self.chk_ch_timer_ccw.setChecked(bool(self.cfg.OVERLAY.get("ch_timer_rotate_ccw", True))); self.chk_ch_timer_ccw.stateChanged.connect(self._on_ch_timer_ccw_toggle)
        box_tc = QVBoxLayout(); box_tc.addWidget(QLabel("<b>Timers & Counters</b>")); box_tc.addWidget(self.chk_ch_timer_portrait); box_tc.addWidget(self.chk_ch_timer_ccw)
        btn_r1 = QHBoxLayout(); self.btn_ch_timer_place = QPushButton("Place Timer"); self.btn_ch_timer_place.clicked.connect(self._on_ch_timer_place_clicked); self.btn_ch_timer_test = QPushButton("Test Timer"); self.btn_ch_timer_test.clicked.connect(self._on_ch_timer_test); btn_r1.addWidget(self.btn_ch_timer_place); btn_r1.addWidget(self.btn_ch_timer_test)
        btn_r2 = QHBoxLayout(); self.btn_flip_counter_place = QPushButton("Place Counter"); self.btn_flip_counter_place.clicked.connect(self._on_flip_counter_place_clicked); self.btn_flip_counter_test = QPushButton("Test Counter"); self.btn_flip_counter_test.clicked.connect(self._on_flip_counter_test); btn_r2.addWidget(self.btn_flip_counter_place); btn_r2.addWidget(self.btn_flip_counter_test)
        box_tc.addLayout(btn_r1); box_tc.addLayout(btn_r2); box_tc.addStretch(1)

        self.chk_flip_counter_portrait = self.chk_ch_timer_portrait
        self.chk_flip_counter_ccw = self.chk_ch_timer_ccw

        # 5) NEU: Mini Info / Notifications Overlay
        self.chk_mini_info_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_mini_info_portrait.setChecked(bool(self.cfg.OVERLAY.get("notifications_portrait", True))); self.chk_mini_info_portrait.stateChanged.connect(self._on_mini_info_portrait_toggle)
        self.chk_mini_info_ccw = QCheckBox("Rotate CCW"); self.chk_mini_info_ccw.setChecked(bool(self.cfg.OVERLAY.get("notifications_rotate_ccw", True))); self.chk_mini_info_ccw.stateChanged.connect(self._on_mini_info_ccw_toggle)
        self.btn_mini_info_place = QPushButton("Place"); self.btn_mini_info_place.clicked.connect(self._on_mini_info_place_clicked)
        self.btn_mini_info_test = QPushButton("Test"); self.btn_mini_info_test.clicked.connect(self._on_mini_info_test)
        box_mini_info = create_overlay_box("System Notifications", self.chk_mini_info_portrait, self.chk_mini_info_ccw, self.btn_mini_info_place, self.btn_mini_info_test)

        # 6) Heat Bar
        self.chk_heat_bar_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_heat_bar_portrait.setChecked(bool(self.cfg.OVERLAY.get("heat_bar_portrait", False))); self.chk_heat_bar_portrait.stateChanged.connect(self._on_heat_bar_portrait_toggle)
        self.chk_heat_bar_ccw = QCheckBox("Rotate CCW"); self.chk_heat_bar_ccw.setChecked(bool(self.cfg.OVERLAY.get("heat_bar_rotate_ccw", True))); self.chk_heat_bar_ccw.stateChanged.connect(self._on_heat_bar_ccw_toggle)
        self.btn_heat_bar_place = QPushButton("Place"); self.btn_heat_bar_place.clicked.connect(self._on_heat_bar_place_clicked)
        self.btn_heat_bar_test = QPushButton("Test"); self.btn_heat_bar_test.clicked.connect(self._on_heat_bar_test)
        box_heat_bar = create_overlay_box("Heat Bar (Heat Challenge)", self.chk_heat_bar_portrait, self.chk_heat_bar_ccw, self.btn_heat_bar_place, self.btn_heat_bar_test)

        # 7) Status Overlay (cloud / leaderboard status messages)
        self.chk_status_overlay_enabled = QCheckBox("Enabled"); self.chk_status_overlay_enabled.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_enabled", True))); self.chk_status_overlay_enabled.stateChanged.connect(self._on_status_overlay_enabled_toggle)
        self.chk_status_overlay_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_status_overlay_portrait.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_portrait", False))); self.chk_status_overlay_portrait.stateChanged.connect(self._on_status_overlay_portrait_toggle)
        self.chk_status_overlay_ccw = QCheckBox("Rotate CCW"); self.chk_status_overlay_ccw.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_rotate_ccw", False))); self.chk_status_overlay_ccw.stateChanged.connect(self._on_status_overlay_ccw_toggle)
        self.btn_status_overlay_place = QPushButton("Place"); self.btn_status_overlay_place.clicked.connect(self._on_status_overlay_place_clicked)
        self.btn_status_overlay_test = QPushButton("Test"); self.btn_status_overlay_test.clicked.connect(self._on_status_overlay_test)
        box_status_overlay = QVBoxLayout()
        box_status_overlay.addWidget(QLabel("<b>Status Overlay</b>"))
        box_status_overlay.addWidget(self.chk_status_overlay_enabled)
        box_status_overlay.addWidget(self.chk_status_overlay_portrait)
        box_status_overlay.addWidget(self.chk_status_overlay_ccw)
        _btns_status = QHBoxLayout(); _btns_status.addWidget(self.btn_status_overlay_place); _btns_status.addWidget(self.btn_status_overlay_test)
        box_status_overlay.addLayout(_btns_status)
        box_status_overlay.addStretch(1)

        lay_pos.addLayout(box_main, 1, 0); lay_pos.addLayout(box_toast, 1, 1)
        lay_pos.addLayout(box_ch_sel, 2, 0); lay_pos.addLayout(box_tc, 2, 1)
        lay_pos.addLayout(box_mini_info, 3, 0); lay_pos.addLayout(box_heat_bar, 3, 1)
        lay_pos.addLayout(box_status_overlay, 4, 0)

        layout.addWidget(grp_pos)

        # ── Overlay Pages toggle ────────────────────────────────────────────────
        grp_pages = QGroupBox("📄 Overlay Pages")
        lay_pages = QVBoxLayout(grp_pages)

        lbl_page1 = QLabel("Page 1 (Highlights & Score) is always active.")
        lbl_page1.setStyleSheet("color: #FF7F00; font-size: 9pt;")
        lay_pages.addWidget(lbl_page1)

        lbl_hint = QLabel("Disable pages you don't need — they will be skipped when cycling through the overlay.")
        lbl_hint.setStyleSheet("color: #AAA; font-size: 9pt; font-style: italic;")
        lbl_hint.setWordWrap(True)
        lay_pages.addWidget(lbl_hint)

        self.chk_overlay_page2 = QCheckBox("Page 2: Achievement Progress")
        self.chk_overlay_page2.setChecked(bool(self.cfg.OVERLAY.get("overlay_page2_enabled", True)))
        self.chk_overlay_page2.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page2)

        self.chk_overlay_page3 = QCheckBox("Page 3: Challenge Leaderboard")
        self.chk_overlay_page3.setChecked(bool(self.cfg.OVERLAY.get("overlay_page3_enabled", True)))
        self.chk_overlay_page3.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page3)

        self.chk_overlay_page4 = QCheckBox("Page 4: Cloud Leaderboard")
        self.chk_overlay_page4.setChecked(bool(self.cfg.OVERLAY.get("overlay_page4_enabled", True)))
        self.chk_overlay_page4.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page4)

        self.chk_overlay_page5 = QCheckBox("Page 5: VPC Leaderboard")
        self.chk_overlay_page5.setChecked(bool(self.cfg.OVERLAY.get("overlay_page5_enabled", True)))
        self.chk_overlay_page5.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page5)

        layout.addWidget(grp_pages)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "appearance_overlay")
        self._update_switch_all_button_label()
        self.appearance_subtabs.addTab(overlay_tab, "🖼 Overlay")

        # ── Theme sub-tab ──────────────────────────────────────────────────────
        theme_tab = QWidget()
        theme_tab_outer = QVBoxLayout(theme_tab)

        theme_scroll = QScrollArea()
        theme_scroll.setWidgetResizable(True)
        theme_scroll.setFrameShape(QFrame.Shape.NoFrame)
        theme_inner = QWidget()
        theme_layout = QVBoxLayout(theme_inner)
        theme_layout.setContentsMargins(8, 8, 8, 8)
        theme_layout.setSpacing(10)
        theme_scroll.setWidget(theme_inner)
        theme_tab_outer.addWidget(theme_scroll)

        # ── 1. Active Theme row ────────────────────────────────────────────────
        row_active = QHBoxLayout()
        self.lbl_active_theme = QLabel("Active theme:")
        self.lbl_active_theme.setStyleSheet("color: #00E5FF; font-weight: bold; font-size: 10pt;")
        row_active.addWidget(self.lbl_active_theme)

        self.cmb_theme = QComboBox()
        current_theme_id = (self.cfg.OVERLAY or {}).get("theme", DEFAULT_THEME)
        for tid, tdata in list_themes():
            self.cmb_theme.addItem(f"{tdata['icon']} {tdata['name']}", tid)
        idx = next((i for i in range(self.cmb_theme.count())
                    if self.cmb_theme.itemData(i) == current_theme_id), 0)
        self.cmb_theme.setCurrentIndex(idx)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_combo_changed)
        row_active.addWidget(self.cmb_theme, 1)

        self.btn_apply_theme = QPushButton("Apply Theme")
        self.btn_apply_theme.setStyleSheet(
            "QPushButton { background: #FF7F00; color: #000; font-weight: bold;"
            " padding: 6px 16px; border-radius: 6px; }"
            "QPushButton:hover { background: #FFA040; }"
            "QPushButton:pressed { background: #CC6600; }"
        )
        self.btn_apply_theme.clicked.connect(self._on_apply_theme)
        row_active.addWidget(self.btn_apply_theme)
        theme_layout.addLayout(row_active)

        # ── 2. Color Preview ───────────────────────────────────────────────────
        grp_preview = QGroupBox("Color Preview")
        lay_preview = QVBoxLayout(grp_preview)

        row_colors = QHBoxLayout()
        row_colors.setSpacing(12)
        self._theme_color_boxes: dict[str, QLabel] = {}
        for key, label_text in [("primary", "Primary"), ("accent", "Accent"),
                                 ("border", "Border"), ("bg", "BG")]:
            col = QVBoxLayout()
            col.setSpacing(2)
            swatch = QLabel()
            swatch.setFixedSize(60, 36)
            swatch.setStyleSheet("border: 1px solid #555; border-radius: 4px;")
            self._theme_color_boxes[key] = swatch
            col.addWidget(swatch)
            lbl_key = QLabel(label_text)
            lbl_key.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl_key.setStyleSheet("color: #AAA; font-size: 8pt;")
            col.addWidget(lbl_key)
            row_colors.addLayout(col)
        row_colors.addStretch(1)
        lay_preview.addLayout(row_colors)

        self.lbl_theme_description = QLabel()
        self.lbl_theme_description.setStyleSheet("color: #00E5FF; font-size: 9pt; font-style: italic;")
        lay_preview.addWidget(self.lbl_theme_description)
        theme_layout.addWidget(grp_preview)

        # ── 3. Overlay Preview / Test ──────────────────────────────────────────
        grp_ov_test = QGroupBox("Overlay Preview / Test")
        lay_ov_test = QVBoxLayout(grp_ov_test)

        lbl_ov_hint = QLabel(
            "Preview how overlays look with the current theme."
        )
        lbl_ov_hint.setWordWrap(True)
        lbl_ov_hint.setStyleSheet("color: #AAA; font-size: 9pt; font-style: italic;")
        lay_ov_test.addWidget(lbl_ov_hint)

        _btn_css = (
            "QPushButton { background: #333; color: #CCC; border: 1px solid #555;"
            " border-radius: 4px; padding: 3px 10px; font-size: 9pt; }"
            "QPushButton:hover { border-color: #AAA; color: #FFF; }"
        )
        self._theme_dot_labels: list[QLabel] = []

        def _make_ov_row(dot_color: str, name: str, desc: str,
                         test_fn=None, track_dot: bool = False) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl_name = QLabel(f"<b>{name}</b>")
            lbl_name.setStyleSheet("color: #E0E0E0;")
            row.addWidget(lbl_name)
            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet("color: #888; font-size: 9pt;")
            row.addWidget(lbl_desc, 1)
            if test_fn is not None:
                btn = QPushButton("Test")
                btn.setStyleSheet(_btn_css)
                btn.setFixedWidth(52)
                btn.clicked.connect(test_fn)
                row.addWidget(btn)
            return row

        # theme-affected overlays (primary-color dot)
        lay_ov_test.addLayout(_make_ov_row(
            "#00E5FF", "Main Stats Overlay", "Full achievement list & stats",
            self._on_overlay_test_clicked, track_dot=True))
        lay_ov_test.addLayout(_make_ov_row(
            "#00E5FF", "Achievement Toast", "Pops up on each unlock",
            self._on_theme_toast_test, track_dot=True))
        lay_ov_test.addLayout(_make_ov_row(
            "#00E5FF", "Challenge Menu", "Choose Timed/Flip/Heat",
            self._on_ch_ov_test, track_dot=True))
        lay_ov_test.addLayout(_make_ov_row(
            "#00E5FF", "Challenge Timer", "Countdown during timed challenge",
            self._on_theme_timer_test, track_dot=True))
        lay_ov_test.addLayout(_make_ov_row(
            "#00E5FF", "Flip Counter", "Flip tally for flip challenge",
            self._on_flip_counter_test, track_dot=True))
        lay_ov_test.addLayout(_make_ov_row(
            "#00E5FF", "Heat Bar", "Heat barometer for heat challenge",
            self._on_heat_bar_test, track_dot=True))
        theme_layout.addWidget(grp_ov_test)

        # ── 4. Available Themes ────────────────────────────────────────────────
        grp_themes = QGroupBox("Available Themes")
        lay_themes = QVBoxLayout(grp_themes)

        for tid, tdata in list_themes():
            row = QHBoxLayout()
            row.setSpacing(10)
            lbl_icon = QLabel(tdata["icon"])
            lbl_icon.setFixedWidth(28)
            lbl_icon.setStyleSheet("font-size: 16pt;")
            row.addWidget(lbl_icon)
            lbl_tname = QLabel(f"<b>{tdata['name']}</b>")
            lbl_tname.setStyleSheet("color: #FFFFFF; font-size: 10pt;")
            lbl_tname.setFixedWidth(150)
            row.addWidget(lbl_tname)
            lbl_tdesc = QLabel(tdata.get("description", ""))
            lbl_tdesc.setStyleSheet("color: #888888; font-size: 9pt;")
            row.addWidget(lbl_tdesc, 1)
            lay_themes.addLayout(row)
        theme_layout.addWidget(grp_themes)

        theme_layout.addStretch(1)
        self._add_tab_help_button(theme_tab_outer, "appearance_theme")
        self.appearance_subtabs.addTab(theme_tab, "🎨 Theme")

        # Populate color preview for the initial theme
        self._update_theme_preview(current_theme_id)

        # ── Sound sub-tab ──────────────────────────────────────────────────────
        sound_tab = QWidget()
        sound_outer = QVBoxLayout(sound_tab)
        sound_scroll = QScrollArea()
        sound_scroll.setWidgetResizable(True)
        sound_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sound_inner = QWidget()
        sound_layout = QVBoxLayout(sound_inner)
        sound_layout.setContentsMargins(8, 8, 8, 8)

        # Title
        lbl_sound_title = QLabel("🔊 Sound Effects")
        lbl_sound_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #FF7F00; padding: 4px 0;")
        sound_layout.addWidget(lbl_sound_title)

        # Enable + Volume row
        row_enable = QHBoxLayout()
        self.chk_sound_enabled = QCheckBox("Enable Sound Effects")
        self.chk_sound_enabled.setChecked(bool(self.cfg.OVERLAY.get("sound_enabled", False)))
        def _on_sound_enabled(state):
            self.cfg.OVERLAY["sound_enabled"] = bool(state)
            self.cfg.save()
        self.chk_sound_enabled.stateChanged.connect(_on_sound_enabled)
        row_enable.addWidget(self.chk_sound_enabled)
        row_enable.addSpacing(20)

        lbl_vol = QLabel("Volume:")
        row_enable.addWidget(lbl_vol)
        self.sld_sound_volume = QSlider(Qt.Orientation.Horizontal)
        self.sld_sound_volume.setRange(0, 100)
        self.sld_sound_volume.setValue(int(self.cfg.OVERLAY.get("sound_volume", sound.DEFAULT_VOLUME)))
        self.sld_sound_volume.setFixedWidth(180)
        self.sld_sound_volume.setStyleSheet(
            "QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #FF7F00; width: 14px; margin: -4px 0; border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #FF7F00; border-radius: 3px; }"
        )
        self.lbl_sound_vol_pct = QLabel(f"{self.sld_sound_volume.value()}%")
        self.lbl_sound_vol_pct.setMinimumWidth(36)
        def _on_sound_volume(val):
            self.lbl_sound_vol_pct.setText(f"{val}%")
            self.cfg.OVERLAY["sound_volume"] = val
            self.cfg.save()
        self.sld_sound_volume.valueChanged.connect(_on_sound_volume)
        row_enable.addWidget(self.sld_sound_volume)
        row_enable.addWidget(self.lbl_sound_vol_pct)
        row_enable.addStretch(1)
        sound_layout.addLayout(row_enable)

        # Sound Pack
        row_pack = QHBoxLayout()
        lbl_pack = QLabel("Sound Pack:")
        lbl_pack.setStyleSheet("font-weight: bold;")
        row_pack.addWidget(lbl_pack)
        self.cmb_sound_pack = QComboBox()
        self.cmb_sound_pack.setFixedWidth(160)
        for pack_id, pack_name in sound.SOUND_PACKS.items():
            self.cmb_sound_pack.addItem(pack_name, pack_id)
        cur_pack = str(self.cfg.OVERLAY.get("sound_pack", "zaptron"))
        idx = self.cmb_sound_pack.findData(cur_pack)
        if idx >= 0:
            self.cmb_sound_pack.setCurrentIndex(idx)
        def _on_sound_pack(idx):
            self.cfg.OVERLAY["sound_pack"] = self.cmb_sound_pack.itemData(idx)
            self.cfg.save()
        self.cmb_sound_pack.currentIndexChanged.connect(_on_sound_pack)
        row_pack.addWidget(self.cmb_sound_pack)
        row_pack.addStretch(1)
        sound_layout.addLayout(row_pack)

        # Events group
        lbl_events = QLabel("Events")
        lbl_events.setStyleSheet("font-size: 11pt; font-weight: bold; color: #00E5FF; margin-top: 6px;")
        sound_layout.addWidget(lbl_events)

        tbl_sound = QTableWidget(len(sound.SOUND_EVENTS), 3)
        tbl_sound.setHorizontalHeaderLabels(["Event", "Enabled", "Test"])
        tbl_sound.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tbl_sound.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tbl_sound.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tbl_sound.horizontalHeader().setStretchLastSection(False)
        tbl_sound.verticalHeader().setDefaultSectionSize(32)
        tbl_sound.verticalHeader().setVisible(False)
        tbl_sound.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl_sound.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl_sound.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl_sound.setShowGrid(False)
        tbl_sound.setAlternatingRowColors(False)
        tbl_sound.setStyleSheet(
            "QTableWidget { background: #111; alternate-background-color: #111; border: 1px solid #333; gridline-color: transparent; }"
            "QTableWidget::item { padding: 4px 6px; border: none; }"
        )

        cur_events = self.cfg.OVERLAY.get("sound_events") or {}

        for row, (event_id, event_label) in enumerate(sound.SOUND_EVENTS):
            lbl_item = QTableWidgetItem(event_label)
            lbl_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tbl_sound.setItem(row, 0, lbl_item)

            chk_event = QCheckBox()
            chk_event.setChecked(bool(cur_events.get(event_id, False)))
            chk_event.setFixedSize(20, 20)
            chk_event.setToolTip(f"Enable/disable sound for {event_label}")
            chk_event.setStyleSheet(
                "QCheckBox::indicator { width: 16px; height: 16px; }"
                "QCheckBox::indicator:checked { background: #00E5FF; border: 1px solid #00E5FF; border-radius: 2px; }"
                "QCheckBox::indicator:unchecked { background: #333; border: 1px solid #555; border-radius: 2px; }"
            )

            def _make_event_handler(eid):
                def _handler(state):
                    ev = self.cfg.OVERLAY.setdefault("sound_events", {})
                    ev[eid] = bool(state)
                    self.cfg.save()
                return _handler

            chk_event.stateChanged.connect(_make_event_handler(event_id))
            cell_chk = QWidget()
            cell_lay = QHBoxLayout(cell_chk)
            cell_lay.setContentsMargins(0, 0, 0, 0)
            cell_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_lay.addWidget(chk_event)
            tbl_sound.setCellWidget(row, 1, cell_chk)

            btn_test = QPushButton("▶")
            btn_test.setFixedSize(28, 22)
            btn_test.setToolTip(f"Preview sound for {event_label}")
            btn_test.setStyleSheet(
                "QPushButton { background: #00E5FF; color: #000; border: none; "
                "border-radius: 3px; font-size: 10pt; font-weight: bold; "
                "padding: 0px; text-align: center; }"
                "QPushButton:hover { background: #33EEFF; }"
            )

            def _make_preview(eid):
                def _preview():
                    sound.play_sound_preview(self.cfg, eid)
                return _preview

            btn_test.clicked.connect(_make_preview(event_id))
            cell_btn = QWidget()
            cell_btn_lay = QHBoxLayout(cell_btn)
            cell_btn_lay.setContentsMargins(2, 1, 2, 1)
            cell_btn_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_btn_lay.addWidget(btn_test)
            tbl_sound.setCellWidget(row, 2, cell_btn)

        tbl_sound.resizeRowsToContents()
        tbl_sound.resizeColumnsToContents()
        _total_w = (sum(tbl_sound.columnWidth(c) for c in range(3))
                    + tbl_sound.frameWidth() * 2 + 20)
        tbl_sound.setMaximumWidth(_total_w)
        tbl_sound.setMinimumHeight(len(sound.SOUND_EVENTS) * 32 + 30)
        sound_layout.addWidget(tbl_sound)

        sound_layout.addStretch(1)
        self._add_tab_help_button(sound_layout, "appearance_sound")
        sound_scroll.setWidget(sound_inner)
        sound_outer.addWidget(sound_scroll)
        self.appearance_subtabs.addTab(sound_tab, "🔊 Sound")

        self.main_tabs.addTab(tab, "🎨 Appearance")

    def _portrait_checkboxes(self):
        """Returns the list of all overlay portrait-mode checkboxes."""
        return [
            self.chk_portrait,
            self.chk_ach_toast_portrait,
            self.chk_ch_ov_portrait,
            self.chk_ch_timer_portrait,
            self.chk_mini_info_portrait,
            self.chk_heat_bar_portrait,
            self.chk_status_overlay_portrait,
        ]

    def _ccw_checkboxes(self):
        """Returns the list of all overlay CCW-rotation checkboxes."""
        return [
            self.chk_portrait_ccw,
            self.chk_ach_toast_ccw,
            self.chk_ch_ov_ccw,
            self.chk_ch_timer_ccw,
            self.chk_mini_info_ccw,
            self.chk_heat_bar_ccw,
            self.chk_status_overlay_ccw,
        ]

    def _update_switch_all_button_label(self):
        """Updates the Switch All button label to reflect current portrait checkbox state."""
        try:
            if any(chk.isChecked() for chk in self._portrait_checkboxes()):
                self.btn_switch_all_orientation.setText("🔄 Switch All → Landscape")
            else:
                self.btn_switch_all_orientation.setText("🔄 Switch All → Portrait")
        except AttributeError:
            # During _build_tab_appearance() the checkboxes are created one by one;
            # stateChanged may fire before all 7 checkboxes or the button exist yet.
            pass

    def _on_switch_all_portrait_landscape(self):
        """Toggles all overlay portrait + CCW checkboxes between Portrait and Landscape at once."""
        should_be_portrait = not any(chk.isChecked() for chk in self._portrait_checkboxes())
        for chk in self._portrait_checkboxes():
            chk.setChecked(should_be_portrait)
        for chk in self._ccw_checkboxes():
            chk.setChecked(should_be_portrait)
        self.cfg.save()
        self._update_switch_all_button_label()

    # ==========================================
    # TAB 3: CONTROLS
    # ==========================================
