
from __future__ import annotations

import configparser
import random
import subprocess
import hashlib
import os, sys, time, json, re, glob, threading, uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict, Counter
from PyQt6.QtGui import QFontMetrics

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QTextBrowser, QSystemTrayIcon, QMenu, QFileDialog, QMessageBox, QTabWidget,
    QCheckBox, QSlider, QComboBox, QDialog, QGroupBox, QColorDialog, QLineEdit,
    QFontComboBox, QSpinBox, QDoubleSpinBox, QGridLayout
)
from PyQt6.QtCore import (Qt, pyqtSignal, QEvent, QTimer, QRect,
                          QAbstractNativeEventFilter, QCoreApplication, QObject, QPoint, pyqtSlot)
from PyQt6.QtGui import (QIcon, QColor, QFont, QTransform, QPixmap,
                         QPainter, QImage, QPen)

try:
    import win32gui
except Exception:
    win32gui = None

import ctypes
from ctypes import wintypes
import ssl
from urllib.request import Request, urlopen

from watcher_core import (
    APP_DIR, AppConfig, CloudSync, Watcher,
    JOYINFOEX, JOYERR_NOERROR, JOY_RETURNALL, _joyGetPosEx,
    WM_HOTKEY, WM_KEYDOWN, WM_SYSKEYDOWN,
    KBDLLHOOKSTRUCT, GlobalKeyHook,
    ensure_dir, log, resource_path, sanitize_filename,
    apply_tooltips, f_achievements_state, f_global_ach,
    register_raw_input_for_window, secure_load_json, vk_to_name_en,
)

from ui_dialogs import SetupWizardDialog
from theme import pinball_arcade_style
from ui_cloud_stats import CloudStatsMixin

from ui_overlay import (
    OverlayWindow,
    MiniInfoOverlay,
    read_active_players,
    FlipCounterOverlay,
    FlipCounterPositionPicker,
    TimerPositionPicker,
    ToastPositionPicker,
    ChallengeOVPositionPicker,
    MiniInfoPositionPicker,
    OverlayPositionPicker,
    AchToastWindow,
    AchToastManager,
    ChallengeCountdownOverlay,
    ChallengeSelectOverlay,
    FlipDifficultyOverlay,
    HeatBarometerOverlay,
    HeatBarPositionPicker,
)

class Bridge(QObject):
    overlay_trigger = pyqtSignal()
    overlay_show = pyqtSignal()
    mini_info_show = pyqtSignal(str, int)
    ach_toast_show = pyqtSignal(str, str, int)
    challenge_timer_start = pyqtSignal(int)
    challenge_timer_stop = pyqtSignal()
    challenge_warmup_show = pyqtSignal(int, str)
    challenge_info_show = pyqtSignal(str, int, str)
    challenge_speak = pyqtSignal(str)
    achievements_updated = pyqtSignal()
    flip_counter_total_show = pyqtSignal(int, int, int)  
    flip_counter_total_update = pyqtSignal(int, int, int)
    flip_counter_total_hide = pyqtSignal()
    heat_bar_show = pyqtSignal()
    heat_bar_update = pyqtSignal(int)
    heat_bar_hide = pyqtSignal()
    
    prefetch_started = pyqtSignal()
    prefetch_progress = pyqtSignal(str)
    prefetch_finished = pyqtSignal(str)                     

class MainWindow(QMainWindow, CloudStatsMixin):
    def __init__(self, cfg: AppConfig, watcher: Watcher, bridge: Bridge):
        super().__init__()
        self.cfg = cfg
        self.watcher = watcher
        self.bridge = bridge
        self.setWindowTitle("VPX Achievement Watcher")
        self.resize(1350, 800)
        
        icon = self._get_icon()
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)
        
        if "player_id" not in self.cfg.OVERLAY:
            self.cfg.OVERLAY["player_id"] = str(uuid.uuid4())[:4]
            self.cfg.save()
            
        self.main_tabs = QTabWidget()
        self.setCentralWidget(self.main_tabs)

        self.bridge.overlay_trigger.connect(self._on_overlay_trigger)
        self.bridge.overlay_show.connect(self._show_overlay_latest)
        self.bridge.mini_info_show.connect(self._on_mini_info_show)
        self.bridge.ach_toast_show.connect(self._on_ach_toast_show)
        self._ach_toast_mgr = AchToastManager(self)
        self.bridge.achievements_updated.connect(self.update_achievements_tab)
        self.bridge.challenge_info_show.connect(self._on_challenge_info_show)
        self.bridge.challenge_timer_start.connect(self._on_challenge_timer_start)
        self.bridge.challenge_timer_stop.connect(self._on_challenge_timer_stop)
        self.bridge.challenge_warmup_show.connect(self._on_challenge_warmup_show)
        self.bridge.challenge_speak.connect(self._on_challenge_speak)
        
        self.bridge.prefetch_started.connect(self._on_prefetch_started)
        self.bridge.prefetch_progress.connect(self._on_prefetch_progress)
        self.bridge.prefetch_finished.connect(self._on_prefetch_finished)
        
        self._prefetch_blink_timer = QTimer(self)
        self._prefetch_blink_timer.setInterval(600)  # Blink-Intervall in ms
        self._prefetch_blink_timer.timeout.connect(self._on_prefetch_blink)
        self._prefetch_blink_state = False
        self._prefetch_msg = ""

        self._build_tab_dashboard()
        self._build_tab_appearance()
        self._build_tab_controls()
        self._build_tab_stats()
        self._build_tab_progress()        
        self._build_tab_available_maps()   
        self._build_tab_cloud() 
        self._build_tab_system()

        self.register_flip_counter_handlers()
        self.register_heat_bar_handlers()

        self.timer_stats = QTimer(self)
        self.timer_stats.timeout.connect(self.update_stats)
        self.timer_stats.start(4000)

        self.overlay_refresh_timer = QTimer(self)
        self.overlay_refresh_timer.setInterval(2000)
        self.overlay_refresh_timer.timeout.connect(self._refresh_overlay_live)
        if bool(self.cfg.OVERLAY.get("live_updates", False)):
            self.overlay_refresh_timer.start()

        self.overlay_auto_close_timer = QTimer(self)
        self.overlay_auto_close_timer.setSingleShot(True)
        self.overlay_auto_close_timer.timeout.connect(self._hide_overlay)

        self._joy_toggle_last_mask = 0
        self._joy_toggle_timer = QTimer(self)
        self._joy_toggle_timer.setInterval(50)
        self._joy_toggle_timer.timeout.connect(self._on_joy_toggle_poll)

        self._apply_toggle_source()
        self._last_toggle_ts = 0.0

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            menu = QMenu()
            menu.addAction("Open", self._show_from_tray)
            menu.addAction("Quit GUI", self.quit_all)
            self.tray.setContextMenu(menu)
            self.tray.show()
            
            QTimer.singleShot(1500, lambda: self.tray.showMessage(
                "VPX Achievement Watcher", 
                "Watcher is running in the background!", 
                QSystemTrayIcon.MessageIcon.Information, 
                3000
            ))
        else:
            self.tray = None

        self._overlay_cycle = {"sections": [], "idx": -1}
        self._overlay_busy = False
        self._overlay_last_action = 0.0
        self.overlay = None

        self._challenge_select = None
        self._ch_ov_selected_idx = 0
        self._ch_active_source = None
        self._last_ch_event_src = None
        self._ch_pick_flip_diff = False
        self._ch_flip_diff_idx = 1  
        self._flip_diff_options = [("Easy", 400), ("Medium", 300), ("Difficult", 200), ("Pro", 100)]
        self._flip_diff_select = None

        self.watcher.start()

        self._apply_theme()
        self._check_for_updates() 
        self._init_tooltips_main()
        self._init_overlay_tooltips()

        try:
            self.update_achievements_tab()
            self._init_achievements_timer()
        except Exception:
            pass

        self._refresh_input_bindings()

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
        
        body_pt = int(self.cfg.OVERLAY.get("base_body_size", 20))
        width_hint = 420 + max(0, (body_pt - 20) * 6)
        height_hint = 120 + max(0, (body_pt - 20) * 2)
        self._toast_picker = ToastPositionPicker(self, width_hint=width_hint, height_hint=height_hint)
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

    def _on_mini_info_test(self):
        # Ruft das Fenster direkt auf, ohne auf ein offenes Spiel zu warten!
        if not hasattr(self, "_mini_overlay") or self._mini_overlay is None:
            self._mini_overlay = MiniInfoOverlay(self)
        self._mini_overlay.show_info("TEST: System Notification Overlay", seconds=5, color_hex="#FF3B30")

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
        msg = f"NVRAM map not found for {rom}. It will be generated automatically after a full game."

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
                "NVRAM_Maps", "NVRAM_Maps/maps", "session_stats",
                "rom_specific_achievements", "custom_achievements",
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
            if getattr(self, "_challenge_select", None):
                try:
                    self._challenge_select.close()
                    self._challenge_select.deleteLater()
                except Exception:
                    pass
            self._challenge_select = ChallengeSelectOverlay(self, selected_idx=int(self._ch_ov_selected_idx))
            self._challenge_select.show()
            self._challenge_select.raise_()
            QTimer.singleShot(5000, self._close_challenge_select_overlay)
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
        return os.path.join(self.cfg.BASE, "challenges", "history", f"{sanitize_filename(rom)}.json")

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
               
    def quit_all(self):
        self.cfg.save()
        try:
            if self.tray:
                self.tray.hide()
        except Exception:
            pass
        try:
            if getattr(self, "watcher", None):
                self.watcher.stop()
        except Exception:
            pass
        try:
            self.close()
        except Exception:
            pass
        try:
            QApplication.instance().quit()
        except Exception:
            pass
           
    def _prefetch_maps_now(self):
        try:
            self.watcher.start_prefetch_background()
            maps_dir = os.path.join(self.cfg.BASE, "NVRAM_Maps", "maps")
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
        
        app.setStyleSheet(pinball_arcade_style)

        self._style(getattr(self, "btn_minimize", None), "background:#005c99; color:white; border:none;")
        self._style(getattr(self, "btn_quit", None), "background:#8a2525; color:white; border:none;")
        self._style(getattr(self, "btn_restart", None), "background:#008040; color:white; border:none;")

    # ==========================================
    # TAB 1: DASHBOARD
    # ==========================================
    def _build_tab_dashboard(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp_status = QGroupBox("System Status")
        lay_status = QVBoxLayout(grp_status)
        self.status_label = QLabel("🟢 Watcher: RUNNING...")
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00E5FF; padding: 10px;")
        lay_status.addWidget(self.status_label)
        layout.addWidget(grp_status)

        grp_actions = QGroupBox("Quick Actions")
        lay_actions = QHBoxLayout(grp_actions)
        self.btn_restart = QPushButton("Restart Engine")
        self.btn_restart.setStyleSheet("background:#008040; border:none;")
        self.btn_restart.clicked.connect(self._restart_watcher)
        self.btn_minimize = QPushButton("Minimize to Tray")
        self.btn_minimize.setStyleSheet("background:#005c99; border:none;")
        self.btn_minimize.clicked.connect(self.hide)
        self.btn_quit = QPushButton("Quit GUI")
        self.btn_quit.setStyleSheet("background:#8a2525; border:none;")
        self.btn_quit.clicked.connect(self.quit_all)
        
        lay_actions.addWidget(self.btn_restart)
        lay_actions.addStretch(1)
        lay_actions.addWidget(self.btn_minimize)
        lay_actions.addWidget(self.btn_quit)
        layout.addWidget(grp_actions)
        
        lbl_info = QLabel("\n(Play a game of VPX to see stats and highlights...)")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setStyleSheet("color: #777;")
        layout.addWidget(lbl_info)
        layout.addStretch(1)

        self.main_tabs.addTab(tab, "🏠 Dashboard")

    # ==========================================
    # TAB 2: APPEARANCE (Grid Layout)
    # ==========================================
    def _build_tab_appearance(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

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

        lay_style.addWidget(QLabel("Font Family:"), 0, 0)
        lay_style.addWidget(self.cmb_font_family, 0, 1)
        lay_style.addWidget(QLabel("Base Size:"), 0, 2)
        lay_style.addWidget(self.spn_font_size, 0, 3)
        
        lay_style.addWidget(QLabel("Overlay Scale:"), 1, 0)
        lay_style.addWidget(self.sld_scale, 1, 1)
        lay_style.addWidget(self.lbl_scale, 1, 2)

        layout.addWidget(grp_style)

        grp_pos = QGroupBox("Widget Placement & Orientation")
        lay_pos = QGridLayout(grp_pos)

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

        lay_pos.addLayout(box_main, 0, 0); lay_pos.addLayout(box_toast, 0, 1)
        lay_pos.addLayout(box_ch_sel, 1, 0); lay_pos.addLayout(box_tc, 1, 1)
        lay_pos.addLayout(box_mini_info, 2, 0); lay_pos.addLayout(box_heat_bar, 2, 1)

        layout.addWidget(grp_pos)
        layout.addStretch(1)
        self.main_tabs.addTab(tab, "🎨 Appearance")

    # ==========================================
    # TAB 3: CONTROLS
    # ==========================================
    def _build_tab_controls(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_inputs = QGroupBox("Input Bindings & Hotkeys")
        lay_inputs = QGridLayout(grp_inputs)
        
        self.cmb_toggle_src = QComboBox(); self.cmb_toggle_src.addItems(["keyboard", "joystick"]); self.cmb_toggle_src.setCurrentText(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")); self.cmb_toggle_src.currentTextChanged.connect(self._on_toggle_source_changed)
        self.btn_bind_toggle = QPushButton("Bind..."); self.btn_bind_toggle.clicked.connect(self._on_bind_toggle_clicked)
        self.lbl_toggle_binding = QLabel(self._toggle_binding_label_text())
        
        self.cmb_ch_hotkey_src = QComboBox(); self.cmb_ch_hotkey_src.addItems(["keyboard", "joystick"]); self.cmb_ch_hotkey_src.setCurrentText(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")); self.cmb_ch_hotkey_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("hotkey", s))
        self.btn_ch_hotkey_bind = QPushButton("Bind..."); self.btn_ch_hotkey_bind.clicked.connect(lambda: self._on_bind_ch_clicked("hotkey"))
        self.lbl_ch_hotkey_binding = QLabel(self._challenge_binding_label_text("hotkey"))

        self.cmb_ch_left_src = QComboBox(); self.cmb_ch_left_src.addItems(["keyboard", "joystick"]); self.cmb_ch_left_src.setCurrentText(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")); self.cmb_ch_left_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("left", s))
        self.btn_ch_left_bind = QPushButton("Bind..."); self.btn_ch_left_bind.clicked.connect(lambda: self._on_bind_ch_clicked("left"))
        self.lbl_ch_left_binding = QLabel(self._challenge_binding_label_text("left"))

        self.cmb_ch_right_src = QComboBox(); self.cmb_ch_right_src.addItems(["keyboard", "joystick"]); self.cmb_ch_right_src.setCurrentText(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")); self.cmb_ch_right_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("right", s))
        self.btn_ch_right_bind = QPushButton("Bind..."); self.btn_ch_right_bind.clicked.connect(lambda: self._on_bind_ch_clicked("right"))
        self.lbl_ch_right_binding = QLabel(self._challenge_binding_label_text("right"))

        lay_inputs.addWidget(QLabel("<b>Show/Hide Stats Overlay:</b>"), 0, 0); lay_inputs.addWidget(self.cmb_toggle_src, 0, 1); lay_inputs.addWidget(self.btn_bind_toggle, 0, 2); lay_inputs.addWidget(self.lbl_toggle_binding, 0, 3)
        lay_inputs.addWidget(QLabel("<hr>"), 1, 0, 1, 4)
        lay_inputs.addWidget(QLabel("<b>Challenge Action / Start:</b>"), 2, 0); lay_inputs.addWidget(self.cmb_ch_hotkey_src, 2, 1); lay_inputs.addWidget(self.btn_ch_hotkey_bind, 2, 2); lay_inputs.addWidget(self.lbl_ch_hotkey_binding, 2, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Nav Left:</b>"), 3, 0); lay_inputs.addWidget(self.cmb_ch_left_src, 3, 1); lay_inputs.addWidget(self.btn_ch_left_bind, 3, 2); lay_inputs.addWidget(self.lbl_ch_left_binding, 3, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Nav Right:</b>"), 4, 0); lay_inputs.addWidget(self.cmb_ch_right_src, 4, 1); lay_inputs.addWidget(self.btn_ch_right_bind, 4, 2); lay_inputs.addWidget(self.lbl_ch_right_binding, 4, 3)
        lay_inputs.setColumnStretch(3, 1); layout.addWidget(grp_inputs)

        grp_voice = QGroupBox("Voice & Audio")
        lay_voice = QVBoxLayout(grp_voice)
        row_v1 = QHBoxLayout(); row_v1.addWidget(QLabel("AI Voice Volume (Challenges):"))
        self.sld_ch_volume = QSlider(Qt.Orientation.Horizontal); self.sld_ch_volume.setRange(0, 100); self.sld_ch_volume.setValue(int(self.cfg.OVERLAY.get("challenges_voice_volume", 80))); self.sld_ch_volume.valueChanged.connect(self._on_ch_volume_changed)
        row_v1.addWidget(self.sld_ch_volume); self.lbl_ch_volume = QLabel(f"{self.sld_ch_volume.value()}%"); row_v1.addWidget(self.lbl_ch_volume)
        self.chk_ch_voice_mute = QCheckBox("Mute all spoken announcements"); self.chk_ch_voice_mute.setChecked(bool(self.cfg.OVERLAY.get("challenges_voice_mute", False))); self.chk_ch_voice_mute.stateChanged.connect(self._on_ch_mute_toggled)
        lay_voice.addLayout(row_v1); lay_voice.addWidget(self.chk_ch_voice_mute); layout.addWidget(grp_voice)

        layout.addStretch(1)
        self.main_tabs.addTab(tab, "🕹️ Controls")

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
        btn_refresh.setStyleSheet("background:#00E5FF; color:black; font-weight:bold;")
        btn_refresh.clicked.connect(self._refresh_progress_roms)
        row.addWidget(btn_refresh)
        lay.addLayout(row)
        
        self.progress_view = QTextBrowser()
        lay.addWidget(self.progress_view)
        
        layout.addWidget(grp)
        self.main_tabs.addTab(tab, "📈 Progress")
        
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, self._refresh_progress_roms)

    def _refresh_progress_roms(self):
        self.cmb_progress_rom.blockSignals(True)
        self.cmb_progress_rom.clear()
        
        roms = set()
        
        state = self.watcher._ach_state_load()
        roms.update(state.get("global", {}).keys())
        roms.update(state.get("session", {}).keys())
        
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
                title = romnames.get(r, r)
                self.cmb_progress_rom.addItem(title, r)
            
        self.cmb_progress_rom.blockSignals(False)
        self._on_progress_rom_changed()

    def _on_progress_rom_changed(self):
        rom = self.cmb_progress_rom.currentData()
        if not rom:
            rom = self.cmb_progress_rom.currentText()

        # Update colored ROM name label next to the dropdown
        self.lbl_progress_rom_name.setText(rom if (rom and rom != "Global") else "")

        if not rom:
            self.progress_view.setHtml("<div style='text-align:center; color:#888;'>(No data available)</div>")
            return
            
        state = self.watcher._ach_state_load()
        unlocked_titles = set()
        all_rules = []

        if rom == "Global":
            import json, os
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
            
        html = ["<style>table {width:100%; border-collapse:collapse;} td {padding:8px; border-bottom:1px solid #444;} .unlocked {color:#00E5FF; font-weight:bold;} .locked {color:#666;}</style>"]
        
        unlocked_count = 0
        cells = []
        for r in all_rules:
            title = str(r.get("title", "Unknown")).strip()
            clean_title = title.replace(" (Session)", "").replace(" (Global)", "")
            
            if title in unlocked_titles or clean_title in unlocked_titles:
                unlocked_count += 1
                cells.append(f"<td class='unlocked'>✅ {clean_title}</td>")
            else:
                cells.append(f"<td class='locked'>🔒 {clean_title}</td>")
                
        pct = round((unlocked_count / len(all_rules)) * 100, 1) if all_rules else 0
        
        rom_label = "Global Achievements" if rom == "Global" else f"ROM: {rom.upper()}"
        html.append(f"<div style='font-size:1.4em; color:#FFFFFF; text-align:center; margin-bottom:5px; font-weight:bold;'>{rom_label}</div>")
        html.append(f"<div style='font-size:1.2em; color:#FF7F00; text-align:center; margin-bottom:15px; font-weight:bold;'>Progress: {unlocked_count} / {len(all_rules)} ({pct}%)</div>")
        
        html.append("<table>")
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
            
    def _build_tab_available_maps(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        grp = QGroupBox("Supported Tables (from Cloud/Index)")
        lay = QVBoxLayout(grp)
        
        row = QHBoxLayout()
        self.txt_map_search = QLineEdit()
        self.txt_map_search.setPlaceholderText("Search for Table or ROM...")
        self.txt_map_search.textChanged.connect(self._filter_available_maps)
        row.addWidget(self.txt_map_search)
        
        btn_refresh = QPushButton("🔄 Load List")
        btn_refresh.setStyleSheet("background:#FF7F00; color:black; font-weight:bold;")
        btn_refresh.clicked.connect(self._refresh_available_maps)
        row.addWidget(btn_refresh)
        lay.addLayout(row)
        
        self.maps_view = QTextBrowser()
        lay.addWidget(self.maps_view)
        
        layout.addWidget(grp)
        self.main_tabs.addTab(tab, "📚 Available Maps")
        self._all_maps_cache = []

    def _refresh_available_maps(self):
        self.maps_view.setHtml("<div style='color:#00E5FF; text-align:center; font-size:1.2em; margin-top:20px;'>Loading maps from database... Please wait.</div>")
        QApplication.processEvents()
        
        index_roms = list(self.watcher.INDEX.keys())
        all_roms = sorted(list(set(index_roms)))
        
        self._all_maps_cache = []
        romnames = self.watcher.ROMNAMES or {}
        
        for rom in all_roms:
            if rom.startswith("_"): continue
            title = romnames.get(rom, "Unknown Table")
            self._all_maps_cache.append((rom, title))
            
        self._filter_available_maps()

    def _filter_available_maps(self):
        query = self.txt_map_search.text().lower()
        
        if not self._all_maps_cache:
            self.maps_view.setHtml("<div style='color:#888; text-align:center; margin-top:20px;'>(Click 'Load List' to see all supported tables)</div>")
            return
            
        html = ["<style>table {width:100%; border-collapse:collapse;} th {text-align:left; color:#FF7F00; padding:8px; border-bottom:2px solid #555; background:#111;} td {padding:6px 8px; border-bottom:1px solid #333; color:#DDD; font-weight:bold;}</style>"]
        html.append(f"<div style='margin-bottom:15px; color:#00E5FF; font-weight:bold;'>The online database currently contains NVRAM maps for {len(self._all_maps_cache)} tables.</div>")
        
        html.append("<table><tr><th>Table Name</th><th>ROM Identifier</th><th style='border-left: 2px solid #555; padding-left:15px;'>Table Name</th><th>ROM Identifier</th></tr>")
        
        filtered_items = []
        for rom, title in self._all_maps_cache:
            if query in rom.lower() or query in title.lower():
                filtered_items.append((title, rom))
                if len(filtered_items) > 800: # UI-Freeze Schutz
                    break
                    
        for i in range(0, len(filtered_items), 2):
            title1, rom1 = filtered_items[i]
            html.append("<tr>")
            
            html.append(f"<td>{title1}</td><td style='color:#888;'>{rom1}</td>")
            
            if i + 1 < len(filtered_items):
                title2, rom2 = filtered_items[i + 1]
                html.append(f"<td style='border-left: 2px solid #333; padding-left:15px;'>{title2}</td><td style='color:#888;'>{rom2}</td>")
            else:
                html.append("<td style='border-left: 2px solid #333; padding-left:15px;'></td><td></td>")
                
            html.append("</tr>")
                
        if len(filtered_items) > 800:
            html.append("<tr><td colspan='4' style='color:#FF3B30; text-align:center; padding-top:15px;'>(List truncated... Please refine your search)</td></tr>")
                    
        html.append("</table>")
        self.maps_view.setHtml("".join(html))

    # ==========================================
    # TAB: SYSTEM
    # ==========================================
    def _build_tab_system(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_profile = QGroupBox("Player Profile & Cloud Setup")
        lay_profile = QGridLayout(grp_profile)
        
        self.txt_player_name = QLineEdit()
        self.txt_player_name.setText(self.cfg.OVERLAY.get("player_name", "Player"))
        self.txt_player_name.textChanged.connect(self._save_player_name) 
        
        self.txt_player_id = QLineEdit()
        self.txt_player_id.setText(self.cfg.OVERLAY.get("player_id", "0000"))
        self.txt_player_id.setMaxLength(4)
        self.txt_player_id.setFixedWidth(60)
        self.txt_player_id.textChanged.connect(self._save_player_id)
        
        self.chk_cloud_enabled = QCheckBox("Enable Cloud Sync")
        self.chk_cloud_enabled.setChecked(self.cfg.CLOUD_ENABLED)
        self.chk_cloud_enabled.stateChanged.connect(self._save_cloud_settings)
        
        lay_profile.addWidget(QLabel("Display Name:"), 0, 0)
        lay_profile.addWidget(self.txt_player_name, 0, 1)
        lay_profile.addWidget(QLabel("Player ID (Restore):"), 0, 2)
        lay_profile.addWidget(self.txt_player_id, 0, 3)
        lay_profile.addWidget(self.chk_cloud_enabled, 1, 0, 1, 4)
        
        layout.addWidget(grp_profile)

        grp_paths = QGroupBox("Directory Setup")
        lay_paths = QGridLayout(grp_paths)
        self.base_label = QLabel(f"BASE: {self.cfg.BASE}")
        self.btn_base = QPushButton("Browse..."); self.btn_base.clicked.connect(self.change_base)
        self.nvram_label = QLabel(f"NVRAM: {self.cfg.NVRAM_DIR}")
        self.btn_nvram = QPushButton("Browse..."); self.btn_nvram.clicked.connect(self.change_nvram)
        self.tables_label = QLabel(f"TABLES: {self.cfg.TABLES_DIR}")
        self.btn_tables = QPushButton("Browse..."); self.btn_tables.clicked.connect(self.change_tables)
        lay_paths.addWidget(self.btn_base, 0, 0); lay_paths.addWidget(self.base_label, 0, 1)
        lay_paths.addWidget(self.btn_nvram, 1, 0); lay_paths.addWidget(self.nvram_label, 1, 1)
        lay_paths.addWidget(self.btn_tables, 2, 0); lay_paths.addWidget(self.tables_label, 2, 1)
        lay_paths.setColumnStretch(1, 1); layout.addWidget(grp_paths)

        grp_maint = QGroupBox("Maintenance Tools")
        lay_maint = QVBoxLayout(grp_maint)
        self.btn_repair = QPushButton("Repair Data Folders")
        self.btn_repair.clicked.connect(self._repair_data_folders)
        self.btn_prefetch = QPushButton("Force Cache NVRAM Maps")
        self.btn_prefetch.clicked.connect(self._prefetch_maps_now)
        lay_maint.addWidget(self.btn_repair)
        lay_maint.addWidget(self.btn_prefetch)
        
        lbl_id_warning = QLabel(
            "⚠️ <b>IMPORTANT: Keep your Player ID safe!</b><br>"
            "Do not share your 4-character Player ID with anyone. "
            "Please write it down or save it somewhere safe!"
        )
        lbl_id_warning.setWordWrap(True)
        lbl_id_warning.setStyleSheet("color: #FF7F00; margin-top: 15px; font-size: 10pt; background: #111; padding: 10px; border: 1px solid #FF7F00; border-radius: 5px;")
        lay_maint.addWidget(lbl_id_warning)
        
        layout.addWidget(grp_maint)
        layout.addStretch(1)
        self.main_tabs.addTab(tab, "⚙️ System")

    # ==========================================
    # CLEAN SAVE METHODS
    # ==========================================
    def _save_cloud_settings(self):
        if self.chk_cloud_enabled.isChecked():
            pname = self.txt_player_name.text().strip().lower()
            if not pname or pname == "player":
                self._msgbox_topmost("warn", "Cloud Sync", "Please enter a valid player name in the profile first!")
                self.chk_cloud_enabled.blockSignals(True)
                self.chk_cloud_enabled.setChecked(False)
                self.chk_cloud_enabled.blockSignals(False)
                return
        self.cfg.CLOUD_ENABLED = self.chk_cloud_enabled.isChecked()
        self.cfg.save()
        
    def _save_player_name(self, name):
        self.cfg.OVERLAY["player_name"] = name.strip()
        self.cfg.save()
        if not name.strip() or name.strip().lower() == "player":
            if getattr(self, "chk_cloud_enabled", None) and self.chk_cloud_enabled.isChecked():
                self.chk_cloud_enabled.blockSignals(True)
                self.chk_cloud_enabled.setChecked(False)
                self.chk_cloud_enabled.blockSignals(False)
                self.cfg.CLOUD_ENABLED = False
                self.cfg.save()

    def _save_player_id(self, player_id):
        self.cfg.OVERLAY["player_id"] = player_id.strip()
        self.cfg.save()

    def _init_tooltips_main(self):
        def _set_tip(attr: str, tip: str):
            try:
                w = getattr(self, attr, None)
                if w:
                    w.setToolTip(tip)
            except Exception:
                pass
                
        # Dashboard Tab
        _set_tip("btn_restart", "Restarts the background engine (useful if the tracker hangs).")
        _set_tip("btn_quit", "Completely closes the application and stops all background tracking.")
        _set_tip("btn_minimize", "Minimizes the window to the Windows system tray.")
        _set_tip("status_label", "Current status of the background watcher engine.")
        
        # Controls Tab
        _set_tip("cmb_toggle_src", "Choose whether to use a keyboard key or joystick button to show/hide the main overlay.")
        _set_tip("btn_bind_toggle", "Assign the hotkey used to show/hide the main stats overlay.")
        _set_tip("lbl_toggle_binding", "Currently assigned hotkey for the main overlay.")
        _set_tip("cmb_ch_hotkey_src", "Input source for the challenge 'Action/Start' button.")
        _set_tip("btn_ch_hotkey_bind", "Assign the hotkey used to start challenges or select options.")
        _set_tip("lbl_ch_hotkey_binding", "Currently assigned hotkey for challenge actions.")
        _set_tip("cmb_ch_left_src", "Input source for navigating left in challenge menus.")
        _set_tip("btn_ch_left_bind", "Assign the hotkey used to navigate left.")
        _set_tip("lbl_ch_left_binding", "Currently assigned left navigation hotkey.")
        _set_tip("cmb_ch_right_src", "Input source for navigating right in challenge menus.")
        _set_tip("btn_ch_right_bind", "Assign the hotkey used to navigate right.")
        _set_tip("lbl_ch_right_binding", "Currently assigned right navigation hotkey.")
        _set_tip("sld_ch_volume", "Adjust the volume of the AI voice announcements.")
        _set_tip("chk_ch_voice_mute", "Completely disable spoken voice announcements during challenges.")
        
        # Cloud Tab
        _set_tip("cmb_cloud_category", "Select the leaderboard category you want to view.")
        _set_tip("txt_cloud_rom", "Type the ROM name exactly as it appears in VPX (e.g. afm_113b).")
        _set_tip("btn_cloud_fetch", "Download and display the global highscores from the cloud.")
        
        # System Tab
        _set_tip("txt_player_name", "Enter your display name (used for local records and leaderboards).")
        _set_tip("txt_player_id", "Your unique 4-character ID. Keep this safe to restore your cloud progress after a reinstall!")
        _set_tip("chk_cloud_enabled", "Turn automatic cloud sync for scores and progress on or off.")
        _set_tip("btn_repair", "Recreates missing folders and downloads the base database if corrupted.")
        _set_tip("btn_prefetch", "Forces a background download of all missing NVRAM maps from the internet.")
        _set_tip("base_label", "Current base directory for achievements data.")
        _set_tip("btn_base", "Change the main folder where achievement data and history is saved.")
        _set_tip("nvram_label", "Current NVRAM folder path.")
        _set_tip("btn_nvram", "Change the folder where VPinMAME stores its .nv files.")
        _set_tip("tables_label", "Current VPX tables folder path (optional).")
        _set_tip("btn_tables", "Change the folder where Visual Pinball tables (.vpx) are located.")

    def _init_overlay_tooltips(self):
        tips = {
            # Appearance Tab - Global Styling
            "cmb_font_family": "Select the font style for all text in the overlays.",
            "spn_font_size": "Adjust the base font size (automatically scales headers and body text).",
            "sld_scale": "Scale the main overlay up or down in overall size (percentage).",
            "lbl_scale": "Current overlay scale in percent.",
            
            # Appearance Tab - Main Stats Overlay
            "chk_portrait": "Rotate the main overlay 90 degrees for portrait/cabinet screens.",
            "chk_portrait_ccw": "Rotate counter-clockwise (instead of clockwise) for portrait mode.",
            "btn_overlay_place": "Open a draggable window to set and save the position of the main overlay.",
            "btn_toggle_now": "Instantly show or hide the main overlay for testing.",
            "btn_hide": "Forcefully hide the main overlay if it's currently visible.",
            "chk_overlay_auto_close": "Automatically hide the main overlay after 60 seconds of inactivity.",
            
            # Appearance Tab - Achievement Toasts
            "chk_ach_toast_portrait": "Rotate achievement unlock popups for portrait screens.",
            "chk_ach_toast_ccw": "Rotate achievement popups counter-clockwise.",
            "btn_ach_toast_place": "Set and save the screen position for achievement popups.",
            "btn_test_toast": "Trigger a test achievement popup to check your placement.",
            
            # Appearance Tab - Challenge Menu
            "chk_ch_ov_portrait": "Rotate the challenge selection menu for portrait screens.",
            "chk_ch_ov_ccw": "Rotate the challenge selection menu counter-clockwise.",
            "btn_ch_ov_place": "Set and save the screen position for the challenge menu.",
            "btn_ch_ov_test": "Show the challenge selection menu for testing.",
            
            # Appearance Tab - Timers & Counters
            "chk_ch_timer_portrait": "Rotate timers and counters for portrait screens.",
            "chk_ch_timer_ccw": "Rotate timers and counters counter-clockwise.",
            "btn_ch_timer_place": "Set and save the screen position for the countdown timer.",
            "btn_ch_timer_test": "Show a test countdown timer to check your placement.",
            "btn_flip_counter_place": "Set and save the screen position for the flip challenge counter.",
            "btn_flip_counter_test": "Show a test flip counter to check your placement.",
            
            # Appearance Tab - System Notifications (Mini Info Overlay)
            "chk_mini_info_portrait": "Rotate system notifications (errors, warnings, info) for portrait screens.",
            "chk_mini_info_ccw": "Rotate system notifications counter-clockwise.",
            "btn_mini_info_place": "Set and save the screen position for system notifications.",
            "btn_mini_info_test": "Trigger a test notification to check your placement."
        }
        apply_tooltips(self, tips)
        
    def _init_settings_tooltips(self):
        pass
     
    def update_achievements_tab(self):
        state = secure_load_json(f_achievements_state(self.cfg), {}) or {}
        global_map = state.get("global", {}) or {}
        session_map = state.get("session", {}) or {}
        
        def build_columns_html(data_map: dict) -> str:
            roms = sorted(data_map.keys(), key=lambda s: str(s).lower())
            if not roms:
                return "<div>(no data)</div>"
            cols = []
            for rom in roms:
                entries = data_map.get(rom, []) or []
                items = []
                for e in entries:
                    if isinstance(e, dict):
                        title = str(e.get("title", "")).strip()
                    else:
                        title = str(e).strip()

                    title = title.replace(" (Session)", "").replace(" (Global)", "")

                    if title:
                        items.append(title)
                if not items:
                    continue
                lines = [f"<div style='font-weight:700;margin-bottom:4px;'>{rom}</div>"]
                for title in items:
                    lines.append(f"<div style='margin:2px 0;'>{title}</div>")
                cols.append("".join(lines))
            if not cols:
                return "<div>(no data)</div>"
            html = "<table width='100%'><tr>" + "".join(
                f"<td valign='top' style='padding:0 14px;'>{c}</td>" for c in cols
            ) + "</tr></table>"
            return html
            
        try:
            html_g = build_columns_html(global_map)
            self.ach_view_global.setHtml(html_g)
        except Exception:
            pass

        try:
            html_pl = build_columns_html(session_map)
            self.ach_view_pl.setHtml(html_pl)
        except Exception:
            pass 
        try:
            if hasattr(self, "cmb_progress_rom"):
                self._on_progress_rom_changed()
        except Exception:
            pass

    def _on_ach_toast_custom_toggled(self, state: int):
        use = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_custom"] = bool(use)
        if not use:
            self.cfg.OVERLAY["ach_toast_saved"] = False
        self.cfg.save()

    def _init_achievements_timer(self):
        try:
            self.timer_achievements = QTimer(self)
            self.timer_achievements.setInterval(5000)  # 5 seconds
            self.timer_achievements.timeout.connect(self.update_achievements_tab)
            self.timer_achievements.start()
        except Exception:
            pass 
 
    def _get_icon(self) -> QIcon:
        try:
            p = resource_path("watcher.ico")
            if os.path.isfile(p):
                ic = QIcon(p)
                if not ic.isNull():
                    return ic
        except Exception:
            pass
        try:
            p2 = os.path.join(APP_DIR, "watcher.ico")
            if os.path.isfile(p2):
                ic = QIcon(p2)
                if not ic.isNull():
                    return ic
        except Exception:
            pass

        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        try:
            painter = QPainter(pm)
            painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            painter.setBrush(QColor("#202020"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(1, 1, 30, 30, 6, 6)
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), "AW")
            painter.end()
        except Exception:
            pm.fill(QColor("#202020"))
        return QIcon(pm)

    def _on_portrait_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["portrait_rotate_ccw"] = is_ccw
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_portrait_from_cfg(self.cfg.OVERLAY)
            self.overlay.request_rotation(force=True)
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
            
    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        self.cfg.save()
        try:
            if getattr(self, "tray", None) and self.tray and self.tray.isVisible():
                self.hide()
                event.ignore()
                return
        except Exception:
            pass
        try:
            self._unregister_global_hotkeys()
        except Exception:
            pass
        try:
            self._uninstall_global_keyboard_hook()
        except Exception:
            pass
        try:
            if getattr(self, "watcher", None):
                self.watcher.stop()
        except Exception:
            pass
        event.accept()

    def change_base(self):
        d = QFileDialog.getExistingDirectory(self, "Select BASE directory", self.cfg.BASE)
        if d:
            self.cfg.BASE = d
            self.base_label.setText(f"BASE: {d}")
            self.cfg.save()

    def change_nvram(self):
        d = QFileDialog.getExistingDirectory(self, "Select NVRAM directory", self.cfg.NVRAM_DIR)
        if d:
            self.cfg.NVRAM_DIR = d
            self.nvram_label.setText(f"NVRAM: {d}")
            self.cfg.save()

    def change_tables(self):
        d = QFileDialog.getExistingDirectory(self, "Select TABLES directory", self.cfg.TABLES_DIR)
        if d:
            self.cfg.TABLES_DIR = d
            self.tables_label.setText(f"TABLES (optional): {d}")
            self.cfg.save()

    def _refresh_overlay_live(self):
        if not bool(self.cfg.OVERLAY.get("live_updates", False)):
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
            import time as _time
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
            
            # Neu bauen und rendern der einzigen Seite!
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

            if not active_deltas:
                try:
                    import json
                    summary_path = os.path.join(self.cfg.BASE, "session_stats", "Highlights", "session_latest.summary.json")
                    if os.path.isfile(summary_path):
                        with open(summary_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            saved_deltas = data.get("players", [])[0].get("deltas", {})
                            for k, v in saved_deltas.items():
                                if int(v) > 0:
                                    active_deltas[k] = int(v)
                except Exception:
                    pass

            for p in combined_players:
                p["deltas"] = active_deltas

            sections.append({
                "kind": "combined_players",
                "players": combined_players,
                "title": "Session Overview"
            })
            
        self._overlay_cycle = {"sections": sections, "idx": -1}
        
    def _show_overlay_section(self, payload: dict):
        self._ensure_overlay()
        kind = str(payload.get("kind", "")).lower()
        title = str(payload.get("title", "") or "").strip()
        if kind == "combined_players":
            combined = {"players": payload.get("players", [])}
            self.overlay.set_combined(combined, session_title=title or "Active Player Highlights")
            self.overlay.show(); self.overlay.raise_()
            self._start_overlay_auto_close_timer()
            return
        if kind == "html":
            html = payload.get("html", "") or "<div>-</div>"
            self.overlay.set_html(html, session_title=title)
            self.overlay.show(); self.overlay.raise_()
            self._start_overlay_auto_close_timer()
            return
        combined = {"players": [payload]}
        title2 = f"Highlights – {payload.get('title','')}".strip()
        self.overlay.set_combined(combined, session_title=title2)
        self.overlay.show(); self.overlay.raise_()
        self._start_overlay_auto_close_timer()

    def _cycle_overlay_button(self): 

        try:
            if self.watcher and self.watcher.game_active:
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
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
                if not secs:
                    self._msgbox_topmost("info", "Overlay", "No contents available (Global/Player).")
                    return
                self._overlay_cycle["idx"] = 0
                self._show_overlay_section(secs[0])
            else:
                secs = self._overlay_cycle.get("sections", [])
                if not secs:
                    self._prepare_overlay_sections()
                    secs = self._overlay_cycle.get("sections", [])
                    if not secs:
                        self._hide_overlay()
                        self._overlay_cycle = {"sections": [], "idx": -1}
                        return
                    self._overlay_cycle["idx"] = 0
                    self._show_overlay_section(secs[0])
                    return
                idx = int(self._overlay_cycle.get("idx", -1))
                idx = 0 if idx < 0 else idx + 1
                if idx >= len(secs):
                    self._hide_overlay()
                    self._overlay_cycle = {"sections": [], "idx": -1}
                else:
                    self._overlay_cycle["idx"] = idx
                    self._show_overlay_section(secs[idx])
        finally:
            import time as _time
            self._overlay_last_action = _time.monotonic()
            self._overlay_busy = False

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

    def _ensure_overlay(self):
        if self.overlay is None:
            self.overlay = OverlayWindow(self)
        self.overlay.portrait_mode = bool(self.cfg.OVERLAY.get("portrait_mode", True))
        self.overlay._apply_geometry()
        self.overlay._layout_positions()
        self.overlay.request_rotation(force=True)

    def _show_overlay_latest(self):
        from PyQt6.QtCore import QTimer
        import time as _time

        def _do_show():
            try:
                self._prepare_overlay_sections()
                secs = self._overlay_cycle.get("sections", [])
                if not secs:
                    return
                self._ensure_overlay()
                self._overlay_cycle["idx"] = 0
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
                    if tries["n"] < 32:
                        QTimer.singleShot(250, _poll)
                    else:
                        _do_show()
                QTimer.singleShot(250, _poll)
                return
        except Exception:
            pass
        _do_show()
        
    def _on_automap_sampler_started(self, rom: str):
        try:
            self._on_mini_info_show(rom, seconds=10)
        except Exception as e:
            try:
                log(self.cfg, f"[CTRL] mini overlay trigger failed on automap start: {e}")
            except Exception:
                pass

    def _maybe_start_automap(self, rom: str):
        log(self.cfg, f"[AUTOMAP] sampler started for {rom}")
        self._on_automap_sampler_started(rom)
           
    def _on_ach_toast_show(self, title: str, rom: str, seconds: int = 5):
        try:
            self._ach_toast_mgr.enqueue(title, rom, max(1, int(seconds)))
        except Exception:
            pass

    def _hide_overlay(self):
        if self.overlay and self.overlay.isVisible():
            self.overlay.hide()
        try:
            self.overlay_auto_close_timer.stop()
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

    def _on_overlay_test_clicked(self):
        self._ensure_overlay()
        
        dummy_data = {
            "players": [{
                "id": 1,
                "playtime_sec": 420,
                "score": 42069000,
                "deltas": {
                    "Ramps Made": 15,
                    "Jackpots": 4,
                    "Drop Targets": 22,
                    "Loops": 8,
                    "Spinner": 45
                },
                "highlights": {
                    "Power": ["🔥 Best Ball – 12.5M", "💥 Multiball Frenzy – 2", "➕ Extra Balls – 1"],
                    "Precision": ["🏹 Rampage – 15", "🎯 Combo King – 4", "🌀 Spinner Madness – 45"],
                    "Fun": ["💀 Tilted – 1"]
                }
            }]
        }
        
        old_rom = getattr(self.watcher, "current_rom", None)
        self.watcher.current_rom = "test_pinball_table"
        
        try:
            self.overlay.set_combined(dummy_data, session_title="Test Highlights")
            self.overlay.show()
            self.overlay.raise_()
            
            QTimer.singleShot(10000, self._hide_overlay)
        finally:
            self.watcher.current_rom = old_rom

    def _on_toggle_keyboard_event(self):
        now = time.monotonic()
        if now - getattr(self, "_last_toggle_ts", 0.0) < 0.40:
            return
        self._last_toggle_ts = now
        if getattr(self, "_overlay_busy", False):
            return
            
        try:
            if getattr(self, "_challenge_select", None) and self._challenge_select.isVisible():
                return
            if getattr(self, "_flip_diff_select", None) and self._flip_diff_select.isVisible():
                return
        except Exception:
            pass

        self._cycle_overlay_button()

    def _on_joy_toggle_poll(self):
        def _need_ch(kind: str) -> int | None:
            if str(self.cfg.OVERLAY.get(f"challenge_{kind}_input_source", "keyboard")).lower() != "joystick":
                return None
            try:
                return int(self.cfg.OVERLAY.get(f"challenge_{kind}_joy_button", 0) or 0)
            except Exception:
                return None
        overlay_src = str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower()
        overlay_btn = int(self.cfg.OVERLAY.get("toggle_joy_button", 0) or 0) if overlay_src == "joystick" else 0
        j_hotkey = _need_ch("hotkey")
        j_left   = _need_ch("left")
        j_right  = _need_ch("right")

        def _bit(btn: int | None) -> int:
            try:
                b = int(btn or 0)
                return (1 << (b - 1)) if b > 0 else 0
            except Exception:
                return 0
        overlay_bit = _bit(overlay_btn)
        hotkey_bit  = _bit(j_hotkey)
        left_bit    = _bit(j_left)
        right_bit   = _bit(j_right)
        interested_mask = overlay_bit | hotkey_bit | left_bit | right_bit
        if interested_mask == 0:
            self._joy_toggle_last_mask = 0
            return
        jix = JOYINFOEX()
        jix.dwSize = ctypes.sizeof(JOYINFOEX)
        jix.dwFlags = JOY_RETURNALL
        mask_all = 0
        for jid in range(16):
            try:
                if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                    mask_all |= int(jix.dwButtons)
            except Exception:
                continue

        newly = (mask_all & ~getattr(self, "_joy_toggle_last_mask", 0))
        self._joy_toggle_last_mask = mask_all
        if newly == 0:
            return
        if hotkey_bit and (newly & hotkey_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_hotkey()
            return
        if left_bit and (newly & left_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_left()
            return
        if right_bit and (newly & right_bit):
            self._last_ch_event_src = "joystick"
            self._on_challenge_right()
            return
        if overlay_bit and (newly & overlay_bit):
            try:
                ch_ov_visible = bool(getattr(self, "_challenge_select", None) and self._challenge_select.isVisible())
                diff_ov_visible = bool(getattr(self, "_flip_diff_select", None) and self._flip_diff_select.isVisible())
            except Exception:
                ch_ov_visible = False
                diff_ov_visible = False
            if ch_ov_visible or diff_ov_visible or self._challenge_is_active():
                return
            self._cycle_overlay_button()
            return
        
    def _on_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["portrait_mode"] = is_checked
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_portrait_from_cfg(self.cfg.OVERLAY)
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_lines_per_category_changed(self, val: int):
        self.cfg.OVERLAY["lines_per_category"] = int(val)
        self.cfg.save()
        try:
            if self.overlay and self.overlay.isVisible():
                self._refresh_overlay_live()
        except Exception:
            pass

    def _on_overlay_scale(self, val: int):
        self.lbl_scale.setText(f"{val}%")
        self.cfg.OVERLAY["scale_pct"] = int(val)
        self.cfg.save()
        if self.overlay:
            self.overlay.scale_pct = int(val)
            self.overlay._apply_scale(int(val))
            self.overlay._apply_geometry()
            self.overlay._layout_positions()
            self.overlay.request_rotation(force=True)
        try:
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_toggle_source_changed(self, src: str):
        self.cfg.OVERLAY["toggle_input_source"] = src
        self.cfg.save()
        self.lbl_toggle_binding.setText(self._toggle_binding_label_text())
        self._apply_toggle_source()
        self._refresh_input_bindings()
        
    def _apply_toggle_source(self):
        try:
            src_overlay = str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower()
            any_ch_joy = any(
                str(self.cfg.OVERLAY.get(f"challenge_{k}_input_source", "keyboard")).lower() == "joystick"
                for k in ("hotkey", "left", "right")
            )
            need_poll = (src_overlay == "joystick") or any_ch_joy
            if need_poll:
                self._joy_toggle_timer.start()
            else:
                self._joy_toggle_timer.stop()
                self._joy_toggle_last_mask = 0
        except Exception:
            try:
                self._joy_toggle_timer.stop()
            except Exception:
                pass
            self._joy_toggle_last_mask = 0
            
    def _refresh_input_bindings(self):
        try:
            self._install_global_keyboard_hook()  
        except Exception:
            pass
        try:
            self._register_global_hotkeys()       
        except Exception:
            pass
        try:
            self._install_challenge_key_handling()  
        except Exception:
            pass     

    def _on_bind_toggle_clicked(self):
        # 1. Globale Hotkeys deaktivieren
        self._unregister_global_hotkeys()
        self._uninstall_global_keyboard_hook()
        
        src = self.cfg.OVERLAY.get("toggle_input_source", "keyboard")
        is_joy = (src == "joystick")
        
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        dlg.setWindowTitle("Binding")
        dlg.resize(360, 140)
        
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        
        cancelled = {"flag": False}
        start_ts = time.time()
        
        def update_lbl():
            elapsed = time.time() - start_ts
            rem = max(0.0, 10.0 - elapsed)
            btn_txt = "joystick button" if is_joy else "key"
            lbl.setText(f"Press any {btn_txt} to bind…\n(Timeout in {rem:.1f}s; ESC to cancel)")
            return elapsed

        update_lbl()
        
        class _UnifiedFilter(QAbstractNativeEventFilter):
            def __init__(self, parent_ref):
                super().__init__()
                self.parent = parent_ref
                self._done = False
                
            def nativeEventFilter(self, eventType, message):
                if self._done:
                    return False, 0
                try:
                    if eventType == b"windows_generic_MSG":
                        msg = ctypes.wintypes.MSG.from_address(int(message))
                        if msg.message in (0x0100, 0x0104): # WM_KEYDOWN, WM_SYSKEYDOWN
                            vk = int(msg.wParam)
                            
                            if vk == 0x1B:
                                self._done = True
                                cancelled["flag"] = True
                                QTimer.singleShot(0, dlg.reject)
                                return True, 0
                                
                            if not is_joy:
                                if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                                    return False, 0 
                                    
                                lp = int(msg.lParam)
                                scancode = (lp >> 16) & 0xFF
                                extended = (lp >> 24) & 0x01

                                if vk == 0x10:
                                    if scancode == 42: vk = 0xA0
                                    elif scancode == 54: vk = 0xA1
                                elif vk == 0x11: 
                                    vk = 0xA3 if extended else 0xA2
                                    
                                self._done = True
                                self.parent.cfg.OVERLAY["toggle_vk"] = int(vk)
                                self.parent.cfg.save()
                                QTimer.singleShot(0, dlg.accept)
                                return True, 0
                except Exception:
                    pass
                return False, 0

        fil = _UnifiedFilter(self)
        QCoreApplication.instance().installNativeEventFilter(fil)

        def _read_buttons_mask() -> int:
            jix = JOYINFOEX()
            jix.dwSize = ctypes.sizeof(JOYINFOEX)
            jix.dwFlags = JOY_RETURNALL
            m_all = 0
            for jid in range(16):
                try:
                    if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                        m_all |= int(jix.dwButtons)
                except Exception:
                    continue
            return m_all
            
        baseline = _read_buttons_mask() if is_joy else 0
        timer = QTimer(dlg)
        
        def _poll():
            if cancelled["flag"]:
                timer.stop()
                return
                
            elapsed = update_lbl()
            
            if is_joy:
                try:
                    mask = _read_buttons_mask()
                    newly = mask & ~baseline
                    if newly:
                        lsb = newly & -newly
                        idx = lsb.bit_length() - 1
                        btn_num = idx + 1
                        self.cfg.OVERLAY["toggle_joy_button"] = int(btn_num)
                        self.cfg.save()
                        timer.stop()
                        dlg.accept()
                        return
                except Exception:
                    pass
                    
            if elapsed > 10.0:
                timer.stop()
                dlg.reject()

        timer.setInterval(35)
        timer.timeout.connect(_poll)
        timer.start()

        def cleanup():
            try:
                QCoreApplication.instance().removeNativeEventFilter(fil)
            except Exception:
                pass
            self.lbl_toggle_binding.setText(self._toggle_binding_label_text())
            self._refresh_input_bindings()
            
        dlg.finished.connect(cleanup)
        dlg.exec()


    def _on_bind_ch_clicked(self, kind: str):
        self._unregister_global_hotkeys()
        self._uninstall_global_keyboard_hook()
        
        src = self.cfg.OVERLAY.get(f"challenge_{kind}_input_source", "keyboard")
        is_joy = (src == "joystick")
        
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        dlg.setWindowTitle("Binding")
        dlg.resize(360, 140)
        
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        
        cancelled = {"flag": False}
        start_ts = time.time()
        
        def update_lbl():
            elapsed = time.time() - start_ts
            rem = max(0.0, 10.0 - elapsed)
            btn_txt = "joystick button" if is_joy else "key"
            lbl.setText(f"Press any {btn_txt} to bind…\n(Timeout in {rem:.1f}s; ESC to cancel)")
            return elapsed

        update_lbl()

        class _UnifiedFilter(QAbstractNativeEventFilter):
            def __init__(self, parent_ref):
                super().__init__()
                self.parent = parent_ref
                self._done = False
                
            def nativeEventFilter(self, eventType, message):
                if self._done:
                    return False, 0
                try:
                    if eventType == b"windows_generic_MSG":
                        msg = ctypes.wintypes.MSG.from_address(int(message))
                        if msg.message in (0x0100, 0x0104):
                            vk = int(msg.wParam)
                            
                            if vk == 0x1B:
                                self._done = True
                                cancelled["flag"] = True
                                QTimer.singleShot(0, dlg.reject)
                                return True, 0
                                
                            if not is_joy:
                                if vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                                    return False, 0
                                    
                                mods = self.parent._get_hotkey_mods_now()
                                self._done = True
                                self.parent.cfg.OVERLAY[f"challenge_{kind}_vk"] = int(vk)
                                self.parent.cfg.OVERLAY[f"challenge_{kind}_mods"] = int(mods)
                                self.parent.cfg.save()
                                QTimer.singleShot(0, dlg.accept)
                                return True, 0
                except Exception:
                    pass
                return False, 0

        fil = _UnifiedFilter(self)
        QCoreApplication.instance().installNativeEventFilter(fil)

        def _read_buttons_mask() -> int:
            jix = JOYINFOEX()
            jix.dwSize = ctypes.sizeof(JOYINFOEX)
            jix.dwFlags = JOY_RETURNALL
            m_all = 0
            for jid in range(16):
                try:
                    if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                        m_all |= int(jix.dwButtons)
                except Exception:
                    continue
            return m_all

        baseline = _read_buttons_mask() if is_joy else 0
        timer = QTimer(dlg)

        def _poll():
            if cancelled["flag"]:
                timer.stop()
                return
                
            elapsed = update_lbl()
            
            if is_joy:
                try:
                    mask = _read_buttons_mask()
                    newly = mask & ~baseline
                    if newly:
                        lsb = newly & -newly
                        idx = lsb.bit_length() - 1
                        btn_num = idx + 1
                        self.cfg.OVERLAY[f"challenge_{kind}_joy_button"] = int(btn_num)
                        self.cfg.save()
                        timer.stop()
                        dlg.accept()
                        return
                except Exception:
                    pass
                    
            if elapsed > 10.0:
                timer.stop()
                dlg.reject()

        timer.setInterval(35)
        timer.timeout.connect(_poll)
        timer.start()

        def cleanup():
            try:
                QCoreApplication.instance().removeNativeEventFilter(fil)
            except Exception:
                pass
                
            if kind == "hotkey":
                self.lbl_ch_hotkey_binding.setText(self._challenge_binding_label_text("hotkey"))
            elif kind == "left":
                self.lbl_ch_left_binding.setText(self._challenge_binding_label_text("left"))
            else:
                self.lbl_ch_right_binding.setText(self._challenge_binding_label_text("right"))
                
            self._refresh_input_bindings()

        dlg.finished.connect(cleanup)
        dlg.exec()

    def _toggle_binding_label_text(self) -> str:
        src = self.cfg.OVERLAY.get("toggle_input_source", "keyboard")
        if src == "joystick":
            btn = int(self.cfg.OVERLAY.get("toggle_joy_button", 2))
            return f"Current: joystick button {btn}"
        else:
            vk = int(self.cfg.OVERLAY.get("toggle_vk", 120))
            return f"Current: {vk_to_name_en(vk)}"

    def _on_overlay_trigger(self):
        self._toggle_overlay()

    def _on_font_family_changed(self, qfont: QFont):
        family = qfont.family()
        self.cfg.OVERLAY["font_family"] = family
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_font_from_cfg(self.cfg.OVERLAY)

    def _on_font_size_changed(self, val: int):
        body = int(val)
        self.cfg.OVERLAY["base_body_size"] = body
        self.cfg.OVERLAY["base_title_size"] = int(round(body * 1.4))
        self.cfg.OVERLAY["base_hint_size"] = int(round(body * 0.8))
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_font_from_cfg(self.cfg.OVERLAY)
            self.overlay._apply_geometry()
            self.overlay._layout_positions()
            self.overlay.request_rotation(force=True)

    def _install_global_keyboard_hook(self):
        try:
            if getattr(self, "_global_keyhook", None):
                try:
                    self._global_keyhook.uninstall()
                except Exception:
                    pass
            self._global_keyhook = None
        except Exception as e:
            log(self.cfg, f"[HOTKEY] disable hook failed: {e}", "WARN")

    def _register_global_hotkeys(self):
        try:
            try:
                self._unregister_global_hotkeys()
            except Exception:
                pass
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            MOD_NOREPEAT = 0x4000
            ids = {
                "overlay_toggle": 0xA11,
                "ch_hotkey":      0xA21,
                "ch_left":        0xA22,
                "ch_right":       0xA23,
            }

            def _reg(_id: int, vk: int):
                mods = (int(self._mods_for_vk(int(vk))) | MOD_NOREPEAT)
                user32.RegisterHotKey(wintypes.HWND(hwnd), _id, mods, int(vk))

            def _reg_ch(_id: int, vk: int, mods_cfg: int):
                mods = (int(mods_cfg) | MOD_NOREPEAT)
                user32.RegisterHotKey(wintypes.HWND(hwnd), _id, mods, int(vk))
            if str(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")).lower() == "keyboard":
                vk_overlay = int(self.cfg.OVERLAY.get("toggle_vk", 120))  # F9
                _reg(ids["overlay_toggle"], vk_overlay)
            if str(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_hotkey_vk", 0x7A))
                mods = int(self.cfg.OVERLAY.get("challenge_hotkey_mods", 0))
                _reg_ch(ids["ch_hotkey"], vk, mods)
            if str(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_left_vk", 0x25))
                mods = int(self.cfg.OVERLAY.get("challenge_left_mods", 0))
                _reg_ch(ids["ch_left"], vk, mods)
            if str(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")).lower() == "keyboard":
                vk = int(self.cfg.OVERLAY.get("challenge_right_vk", 0x27))
                mods = int(self.cfg.OVERLAY.get("challenge_right_mods", 0))
                _reg_ch(ids["ch_right"], vk, mods)
            class _HotkeyFilter(QAbstractNativeEventFilter):
                def __init__(self, parent_ref, ids_map):
                    super().__init__()
                    self.p = parent_ref
                    self.ids = ids_map
                def nativeEventFilter(self, eventType, message):
                    try:
                        if eventType == b"windows_generic_MSG":
                            msg = ctypes.wintypes.MSG.from_address(int(message))
                            if msg.message == WM_HOTKEY:
                                hid = int(msg.wParam)
                                if hid == self.ids["overlay_toggle"]:
                                    QTimer.singleShot(0, self.p._on_toggle_keyboard_event)
                                elif hid == self.ids["ch_hotkey"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_hotkey)
                                elif hid == self.ids["ch_left"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_left)
                                elif hid == self.ids["ch_right"]:
                                    self.p._last_ch_event_src = "keyboard"
                                    QTimer.singleShot(0, self.p._on_challenge_right)
                    except Exception:
                        pass
                    return False, 0
            self._hotkey_ids = ids
            self._hotkey_filter = _HotkeyFilter(self, ids)
            QCoreApplication.instance().installNativeEventFilter(self._hotkey_filter)
            if getattr(self.cfg, "LOG_CTRL", False):
                log(self.cfg, "[HOTKEY] Registered overlay + challenge hotkeys (keyboard)")
        except Exception as e:
            log(self.cfg, f"[HOTKEY] register failed: {e}", "WARN")
       
    def _uninstall_global_keyboard_hook(self):
        try:
            if getattr(self, "_global_keyhook", None):
                self._global_keyhook.uninstall()
                self._global_keyhook = None
                log(self.cfg, "[HOOK] Global keyboard hook uninstalled")
        except Exception as e:
            log(self.cfg, f"[HOOK] uninstall failed: {e}", "WARN")

    def _unregister_global_hotkeys(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            if getattr(self, "_hotkey_ids", None):
                for _name, _id in list(self._hotkey_ids.items()):
                    try:
                        user32.UnregisterHotKey(wintypes.HWND(hwnd), _id)
                    except Exception:
                        pass
            self._hotkey_ids = {}
        except Exception:
            pass
        try:
            if getattr(self, "_hotkey_filter", None):
                QCoreApplication.instance().removeNativeEventFilter(self._hotkey_filter)  # type: ignore
        except Exception:
            pass
        self._hotkey_filter = None
     
    # ==========================================
    # PREFETCH STATUS ANIMATIONS
    # ==========================================
    def _on_prefetch_started(self):
        self._prefetch_msg = "Checking for missing files..."
        if hasattr(self, "_prefetch_blink_timer"):
            self._prefetch_blink_timer.start()
        self._update_prefetch_label()

    def _on_prefetch_progress(self, msg: str):
        self._prefetch_msg = str(msg)
        self._update_prefetch_label()

    def _on_prefetch_blink(self):
        self._prefetch_blink_state = not getattr(self, "_prefetch_blink_state", False)
        self._update_prefetch_label()

    def _update_prefetch_label(self):
        color = "#FF3B30" if getattr(self, "_prefetch_blink_state", False) else "#333333"
        html = (
            f"🔴 Watcher: PREFETCH IN PROGRESS - {self._prefetch_msg} "
            f"<span style='color:{color}; font-weight:bold;'>PLEASE WAIT</span>"
        )
        self.status_label.setText(html)
        self.status_label.setStyleSheet("font-size: 12pt; color: #FF7F00; padding: 10px;")

    def _on_prefetch_finished(self, msg: str):
        try:
            if hasattr(self, "_prefetch_blink_timer"):
                self._prefetch_blink_timer.stop()
        except Exception:
            pass
        self.status_label.setText(f"🟢 {msg}")
        self.status_label.setStyleSheet("font-size: 11pt; color: #00B050; padding: 10px;")
        QTimer.singleShot(10000, self._reset_status_label)

    def _reset_status_label(self):
        self.status_label.setText("🟢 Watcher: RUNNING...")
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00E5FF; padding: 10px;")

    def _restart_watcher(self):
        try:
            if self.watcher:
                self.watcher.stop()
        except Exception:
            pass
        self.watcher = Watcher(self.cfg, self.bridge)
        self.watcher.start()
        self._reset_status_label()

    def _check_for_updates(self):
        CURRENT_VERSION = "2.3.1"
        
        def _task():
            try:
                import urllib.request
                import json
                import ssl
                
                url = f"{self.cfg.CLOUD_URL.rstrip('/')}/app_info.json"
                
                req = urllib.request.Request(url)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    
                if data and isinstance(data, dict):
                    latest = str(data.get("latest_version", CURRENT_VERSION))
                    
                    def parse_v(v_str):
                        try:
                            return tuple(map(int, str(v_str).split('.')))
                        except Exception:
                            return (0,)
                    
                    if parse_v(latest) > parse_v(CURRENT_VERSION):
                        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                        msg = f"An important update is available!\n\nCurrent version: {CURRENT_VERSION}\nNew version: {latest}\n\nPlease download the latest version to ensure that cloud sync and achievements work properly."
                        QMetaObject.invokeMethod(self, "_show_update_warning", Qt.ConnectionType.QueuedConnection, Q_ARG(str, msg))
            except Exception as e:
                pass 
                
        threading.Thread(target=_task, daemon=True).start()

    @pyqtSlot(str)
    def _show_update_warning(self, msg: str):
        QMessageBox.warning(self, "Update available!", msg)
     
def main():
    cfg = AppConfig.load()
    app = QApplication(sys.argv)
    need_wizard = cfg.FIRST_RUN or not os.path.isdir(cfg.BASE)
    if need_wizard:
        if not os.path.isdir(cfg.BASE):
            home_alt = os.path.join(os.path.expanduser("~"), "Achievements")
            if not os.path.exists(cfg.BASE) and not os.path.exists(home_alt):
                cfg.BASE = home_alt
        wiz = SetupWizardDialog(cfg)
        if wiz.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
    for sub in [
        "NVRAM_Maps/maps",
        "session_stats/Highlights",
        "rom_specific_achievements",
        "custom_achievements",
    ]:
        ensure_dir(os.path.join(cfg.BASE, sub))
    bridge = Bridge()
    watcher = Watcher(cfg, bridge)
    win = MainWindow(cfg, watcher, bridge)
    try:
        win._install_global_keyboard_hook()
    except Exception:
        pass
    try:
        win._register_global_hotkeys()
    except Exception:
        pass
    if cfg.FIRST_RUN:
        cfg.FIRST_RUN = False
        cfg.save()
    win.hide()
    code = app.exec()
    cfg.save()
    sys.exit(code)

if __name__ == "__main__":

    main()

