from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QTimer, Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel

from core.watcher_core import (
    JOYINFOEX, JOYERR_NOERROR, JOY_RETURNALL, _joyGetPosEx,
    WM_HOTKEY, WM_KEYDOWN, WM_SYSKEYDOWN,
    GlobalKeyHook, vk_to_name_en, log,
)


class HotkeysMixin:

    def _get_hotkey_mods_now(self) -> int:
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

    def _mods_for_vk(self, vk: int) -> int:
        return 0

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

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

        # Während Challenge keine Overlay-Toggle erlauben
        try:
            ch = getattr(self.watcher, "challenge", {}) or {}
            if ch.get("active") or ch.get("suppress_big_overlay_once"):
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
            if is_joy:
                lbl.setText(f"Press any joystick button to bind…\n(Timeout in {rem:.1f}s; ESC to cancel)")
            else:
                lbl.setText(f"Press any key to bind… (hold Shift, Ctrl, or Alt to add a modifier)\n(Timeout in {rem:.1f}s; ESC to cancel)")
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
                        if msg.message in (WM_KEYDOWN, WM_SYSKEYDOWN):
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
                                    
                                mods = self.parent._get_hotkey_mods_now()
                                self._done = True
                                self.parent.cfg.OVERLAY["toggle_vk"] = int(vk)
                                self.parent.cfg.OVERLAY["toggle_mods"] = int(mods)
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
            if is_joy:
                lbl.setText(f"Press any joystick button to bind…\n(Timeout in {rem:.1f}s; ESC to cancel)")
            else:
                lbl.setText(f"Press any key to bind… (hold Shift, Ctrl, or Alt to add a modifier)\n(Timeout in {rem:.1f}s; ESC to cancel)")
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
                        if msg.message in (WM_KEYDOWN, WM_SYSKEYDOWN):
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
            mods = int(self.cfg.OVERLAY.get("toggle_mods", 0))
            return f"Current: {self._fmt_hotkey_label(vk, mods)}"

    def _on_overlay_trigger(self):
        self._toggle_overlay()

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
                mods_overlay = int(self.cfg.OVERLAY.get("toggle_mods", 0))
                _reg_ch(ids["overlay_toggle"], vk_overlay, mods_overlay)
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
