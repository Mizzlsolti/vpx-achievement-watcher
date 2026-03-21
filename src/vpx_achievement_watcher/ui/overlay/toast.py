from __future__ import annotations

import os
import re
import json
import sys
import math
import random

from typing import Optional

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QObject, QPoint, QEventLoop
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QTransform, QPixmap,
    QPainter, QImage, QPen, QLinearGradient, QBrush,
)

from watcher_core import APP_DIR, register_raw_input_for_window

from .helpers import _ease_out_bounce, _ease_out_cubic, _start_topmost_timer

class AchToastWindow(QWidget):
    finished = pyqtSignal()
    def __init__(self, parent: "MainWindow", title: str, rom: str, seconds: int = 5):
        super().__init__(None)
        self.parent_gui = parent
        self._title = str(title or "").strip()
        self._rom = str(rom or "").strip()
        self._seconds = max(1, int(seconds))
        self._is_closing = False  
        self.setWindowTitle("Achievement")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background:transparent;")
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._remaining = self._seconds

        low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))
        anim_toast = not low_perf and bool(parent.cfg.OVERLAY.get("anim_toast", True))

        # --- Burst particle animation ---
        is_level_up = (self._rom == "__levelup__")
        if not anim_toast:
            self._burst_img_margin = 0
            self._burst_particles = []
            self._burst_elapsed = 0.0
            self._burst_active = False
            self._burst_timer = QTimer(self)
            self._burst_timer.setInterval(30)
            self._burst_timer.timeout.connect(self._burst_tick)
        else:
            self._burst_img_margin = 80
            self._burst_particles = []
            for _ in range(20):
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(80, 200)
                self._burst_particles.append({
                    'x': 0.0, 'y': 0.0,
                    'vx': math.cos(angle) * speed,
                    'vy': math.sin(angle) * speed,
                    'size': random.uniform(3, 6),
                    'alpha': 255,
                    'color': QColor(random.choice([0xFFD700, 0xFF7F00, 0xFFA500])),
                })
            self._burst_elapsed = 0.0
            self._burst_active = True
            self._burst_timer = QTimer(self)
            self._burst_timer.setInterval(30)
            self._burst_timer.timeout.connect(self._burst_tick)
            self._burst_timer.start()

        # --- Neon ring pulse (level-up only) ---
        self._ring_rings = []
        self._ring_active = False
        if is_level_up and anim_toast:
            self._ring_rings = [
                {'r': 0.0, 'elapsed': 0.0, 'delay': 0.0, 'alpha': 200},
                {'r': 0.0, 'elapsed': 0.0, 'delay': 150.0, 'alpha': 200},
                {'r': 0.0, 'elapsed': 0.0, 'delay': 300.0, 'alpha': 180},
                {'r': 0.0, 'elapsed': 0.0, 'delay': 450.0, 'alpha': 150},
            ]
            self._ring_elapsed = 0.0
            self._ring_duration = 550.0
            self._ring_active = True
            self._ring_timer = QTimer(self)
            self._ring_timer.setInterval(20)
            self._ring_timer.timeout.connect(self._ring_tick)
            self._ring_timer.start()

        # --- Energy flash for level-up ---
        self._flash_active: bool = is_level_up and anim_toast
        self._flash_elapsed: float = 0.0
        self._flash_duration: float = 300.0

        # --- Typewriter reveal (title line1) ---
        self._tw_full: str = ""
        self._tw_idx: int = 0
        self._tw_active: bool = anim_toast
        self._tw_cursor_visible: bool = True
        self._tw_cursor_timer = QTimer(self)
        self._tw_cursor_timer.setInterval(500)
        self._tw_cursor_timer.timeout.connect(self._tw_cursor_blink)
        if anim_toast:
            self._tw_cursor_timer.start()

        # --- Icon bounce animation ---
        self._bounce_elapsed: float = 0.0
        self._bounce_duration: float = 400.0
        self._bounce_active: bool = anim_toast

        # --- Slide-in/slide-out entry/exit animation ---
        self._entry_active: bool = anim_toast
        self._entry_elapsed: float = 0.0
        self._entry_duration: float = 250.0
        self._exit_active: bool = False
        self._exit_elapsed: float = 0.0
        self._exit_duration: float = 200.0
        self._motion_timer = QTimer(self)
        self._motion_timer.setInterval(16)
        self._motion_timer.timeout.connect(self._motion_tick)
        if anim_toast:
            self._motion_timer.start()

        # Combined fast animation timer (typewriter + bounce + flash)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._anim_tick)
        if anim_toast:
            self._anim_timer.start()

        self._render_and_place()
        self._timer.start()
        self.show()
        self.raise_()
        _start_topmost_timer(self)

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._remaining = 0
            try:
                self._timer.stop()
            except Exception:
                pass
            # Start exit animation if available, otherwise close immediately
            if not getattr(self, "_is_closing", False):
                if getattr(self, "_exit_active", False) is False and hasattr(self, "_motion_timer"):
                    # Trigger exit animation
                    self._exit_active = True
                    self._exit_elapsed = 0.0
                    self._motion_timer.start()
                else:
                    self._is_closing = True
                    try:
                        self.finished.emit()
                    except Exception:
                        pass
                    QTimer.singleShot(200, self.close)
            return
        self._render_and_place()

    def closeEvent(self, e):
        if not getattr(self, "_is_closing", False):
            self._is_closing = True
            try:
                self.finished.emit()
            except Exception:
                pass
        # Stop all animation timers
        for attr in ('_burst_timer', '_ring_timer', '_anim_timer',
                     '_tw_cursor_timer', '_timer', '_motion_timer'):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
        super().closeEvent(e)

    def _icon_pixmap(self, size: int = 40) -> QPixmap:
        emoji = ""
        try:
            if self._rom == "__levelup__":
                emoji = "⬆️"
            else:
                watcher = getattr(self.parent_gui, "watcher", None)
                if watcher:
                    cache = getattr(watcher, "_rom_emoji_cache", {})
                    emoji = cache.get(self._rom, "")
                    if not emoji and hasattr(watcher, "_resolve_emoji_for_rom"):
                        emoji = watcher._resolve_emoji_for_rom(self._rom)
        except Exception:
            emoji = ""

        if emoji:
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                if sys.platform == "win32":
                    font_name = "Segoe UI Emoji"
                elif sys.platform == "darwin":
                    font_name = "Apple Color Emoji"
                else:
                    font_name = "Noto Color Emoji"
                font = QFont(font_name, int(size * 0.75))
                p.setFont(font)
                p.drawText(QRect(0, 0, size, size),
                           Qt.AlignmentFlag.AlignCenter, emoji)
            finally:
                p.end()
            return pm

        # Fallback: original gold/white circles
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setBrush(QColor("#FFD700"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, size, size)
            p.setBrush(QColor("#FFFFFF"))
            cx = int(size * 0.25)
            cs = int(size * 0.5)
            p.drawEllipse(cx, cx, cs, cs)
        finally:
            p.end()
        return pm
        
    def _compose_image(self) -> QImage:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = 15
        title_pt = max(body_pt + 2, int(round(body_pt * 1.35)))

        is_level_up = (self._rom == "__levelup__")
        if is_level_up:
            border_color = QColor("#00E5FF")
            line1 = "LEVEL UP!"
            line2 = self._title.replace("LEVEL UP!  ", "").strip()
        else:
            border_color = QColor("#555555")
            raw_title = self._title or "Achievement unlocked"
            rom = self._rom or ""

            # Strip ROM prefix from title (e.g. "cc_13 – GOLD MINE MB: 1" → "GOLD MINE MB: 1")
            prefix = f"{rom} \u2013 "
            if rom and raw_title.startswith(prefix):
                line1 = raw_title[len(prefix):]
            else:
                prefix2 = f"{rom} - "
                if rom and raw_title.startswith(prefix2):
                    line1 = raw_title[len(prefix2):]
                else:
                    line1 = raw_title

            # Resolve ROM to clean table name (without version number)
            table_name = ""
            try:
                watcher = getattr(self.parent_gui, "watcher", None)
                if watcher:
                    romnames = getattr(watcher, "ROMNAMES", {}) or {}
                    table_name = romnames.get(rom, "")
            except Exception:
                pass

            if table_name:
                # Strip everything from the first " (" onwards, e.g. "AC/DC Limited Edition (V1.5)" → "AC/DC Limited Edition"
                table_name = table_name.split(" (")[0].strip()

            line2 = table_name if table_name else rom

        # Set typewriter full text on first call (now applies to title/line1)
        if getattr(self, '_tw_active', False) and not getattr(self, '_tw_full', ''):
            self._tw_full = line1

        # Feste Theme-Farben
        title_color = QColor("#FF7F00") # Orange
        text_color = QColor("#FFFFFF")  # Weiß
        levelup_color = QColor("#00E5FF")  # Cyan for level-up line1

        # Apply typewriter reveal to title (line1); use full text for sizing, partial for display
        title_for_size = line1  # always use full text for width calculation
        if getattr(self, '_tw_active', False) and getattr(self, '_tw_full', ''):
            tw_text = self._tw_full[:self._tw_idx]
            if self._tw_cursor_visible and self._tw_idx < len(self._tw_full):
                tw_text += '|'
            title = tw_text
        else:
            title = line1
        # Second line is always static (no typewriter)
        sub = line2
        sub_for_size = line2  # always use full text for width calculation
        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt, QFont.Weight.Bold if is_level_up else QFont.Weight.Normal)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)
        icon_sz = max(28, int(body_pt * 2.0))
        pad = max(12, int(body_pt * 0.8))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_w = fm_title.horizontalAdvance(title_for_size)
        sub_w = fm_body.horizontalAdvance(sub_for_size) if sub_for_size else 0
        text_w = max(title_w, sub_w)
        # Use full text sizes for height calculation to keep window stable during typewriter
        text_h = fm_title.height() + (vgap + fm_body.height() if sub_for_size else 0)
        content_h = max(icon_sz, text_h)
        W = pad + icon_sz + gap + text_w + pad
        H = pad + content_h + pad
        W = max(W, 320)
        H = max(H, max(96, int(body_pt * 4.8)))
        
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        
        bg = QColor(8, 12, 22, 245)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        radius = 16
        p.drawRoundedRect(0, 0, W, H, radius, radius)

        # Outer glow for toast
        glow_pen = QPen(QColor(border_color.red(), border_color.green(), border_color.blue(), 50))
        glow_pen.setWidth(4)
        p.setPen(glow_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(3, 3, W - 6, H - 6, radius - 2, radius - 2)

        pen = QPen(border_color)
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, W - 2, H - 2, radius, radius)
        
        # Icon bounce animation: apply scale and Y-offset
        if getattr(self, '_bounce_active', False):
            bounce_t = min(1.0, getattr(self, '_bounce_elapsed', 0.0) / max(1.0, getattr(self, '_bounce_duration', 400.0)))
            eased = _ease_out_bounce(bounce_t)
            icon_scale = 1.3 + (1.0 - 1.3) * eased   # 1.3 -> 1.0
            icon_y_offset = int(-30 * (1.0 - eased))  # -30 -> 0
            actual_icon_sz = int(icon_sz * icon_scale)
        else:
            actual_icon_sz = icon_sz
            icon_y_offset = 0
        pm = self._icon_pixmap(actual_icon_sz)
        iy = int((H - actual_icon_sz) / 2) + icon_y_offset
        p.drawPixmap(pad, iy, pm)
        x_text = pad + icon_sz + gap
        text_top = int((H - text_h) / 2)
        
        p.setPen(levelup_color if is_level_up else title_color)
        p.setFont(f_title)
        p.drawText(QRect(x_text, text_top, W - x_text - pad, fm_title.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        if sub:
            p.setPen(title_color if is_level_up else text_color)
            p.setFont(f_body)
            p.drawText(QRect(x_text, text_top + fm_title.height() + vgap,
                             W - x_text - pad, fm_body.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)
        # Energy flash overlay for level-up entry
        if is_level_up and getattr(self, '_flash_active', False):
            flash_t = min(1.0, getattr(self, '_flash_elapsed', 0.0) / max(1.0, self._flash_duration))
            flash_alpha = int(180 * (1.0 - flash_t))
            if flash_alpha > 0:
                p.setPen(Qt.PenStyle.NoPen)
                flash_color = QColor(0, 229, 255, flash_alpha)
                p.setBrush(flash_color)
                p.drawRoundedRect(0, 0, W, H, radius, radius)
        p.end()

        portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))

        # Draw burst particles and neon ring in landscape only (portrait adds complexity)
        if not portrait:
            burst_active = getattr(self, '_burst_active', False)
            ring_active = getattr(self, '_ring_active', False)
            burst_margin = getattr(self, '_burst_img_margin', 0) if (burst_active or ring_active) else 0
            if burst_margin > 0:
                EW = W + 2 * burst_margin
                EH = H + 2 * burst_margin
                expanded = QImage(EW, EH, QImage.Format.Format_ARGB32_Premultiplied)
                expanded.fill(Qt.GlobalColor.transparent)
                ep = QPainter(expanded)
                ep.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                try:
                    ep.drawImage(burst_margin, burst_margin, img)
                    cx = EW // 2
                    cy = EH // 2
                    # Burst particles
                    ep.setPen(Qt.PenStyle.NoPen)
                    for pt in getattr(self, '_burst_particles', []):
                        if pt['alpha'] > 0:
                            c = QColor(pt['color'])
                            c.setAlpha(int(max(0, min(255, pt['alpha']))))
                            ep.setBrush(c)
                            sz = max(1, int(pt['size']))
                            ep.drawEllipse(cx + int(pt['x']) - sz // 2,
                                           cy + int(pt['y']) - sz // 2, sz, sz)
                    # Neon rings (level-up)
                    for ring in getattr(self, '_ring_rings', []):
                        r = int(ring['r'])
                        alp = int(max(0, min(255, ring['alpha'])))
                        if r > 0 and alp > 0:
                            rc = QColor(0, 229, 255, alp)
                            pen = QPen(rc)
                            pen.setWidth(3)
                            ep.setPen(pen)
                            ep.setBrush(Qt.BrushStyle.NoBrush)
                            ep.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
                finally:
                    try:
                        ep.end()
                    except Exception:
                        pass
                img = expanded

        if portrait:
            ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        return img

    def _render_and_place(self):
        try:
            img = self._compose_image()
            EW, EH = img.width(), img.height()
            ov = self.parent_gui.cfg.OVERLAY or {}
            portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            # Determine the burst margin embedded in the image (landscape only)
            burst_active = getattr(self, '_burst_active', False)
            ring_active = getattr(self, '_ring_active', False)
            burst_margin = getattr(self, '_burst_img_margin', 0) if (not portrait and (burst_active or ring_active)) else 0
            W = EW - 2 * burst_margin
            H = EH - 2 * burst_margin
            use_saved = bool(ov.get("ach_toast_saved", ov.get("ach_toast_custom", False)))
            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)
            if use_saved:
                if portrait:
                    x = int(ov.get("ach_toast_x_portrait", 100))
                    y = int(ov.get("ach_toast_y_portrait", 100))
                else:
                    x = int(ov.get("ach_toast_x_landscape", 100))
                    y = int(ov.get("ach_toast_y_landscape", 100))
            else:
                pad = 40
                x = int(geo.right() - W - pad)
                y = int(geo.bottom() - H - pad)

            x = max(geo.left(), min(x, geo.right() - W))
            y = max(geo.top(),  min(y,  geo.bottom() - H))

            # Apply slide-in/slide-out offset and opacity
            slide_offset = 0
            opacity = 1.0
            if getattr(self, '_entry_active', False):
                entry_t = min(1.0, getattr(self, '_entry_elapsed', 0.0) / max(1.0, self._entry_duration))
                eased = _ease_out_cubic(entry_t)
                slide_offset = int(60 * (1.0 - eased))
                opacity = max(0.0, min(1.0, eased))
            elif getattr(self, '_exit_active', False):
                exit_t = min(1.0, getattr(self, '_exit_elapsed', 0.0) / max(1.0, self._exit_duration))
                slide_offset = int(60 * exit_t)
                opacity = max(0.0, min(1.0, 1.0 - exit_t))

            # Expand window for burst/ring area
            x_win = x - burst_margin + slide_offset
            y_win = y - burst_margin
            self.setGeometry(x_win, y_win, EW, EH)
            self._label.setGeometry(0, 0, EW, EH)
            self._label.setPixmap(QPixmap.fromImage(img))
            self.setWindowOpacity(opacity)
            self.show()
            self.raise_()
            try:
                import win32gui, win32con 
                hwnd = int(self.winId())
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
                )
            except Exception:
                pass
        except Exception as e:
            print(f"[TOAST] render_and_place failed: {e}")

    def _motion_tick(self):
        """Advance slide-in (entry) or slide-out (exit) animation."""
        dt = 16.0
        if getattr(self, '_entry_active', False):
            self._entry_elapsed += dt
            if self._entry_elapsed >= self._entry_duration:
                self._entry_active = False
                self._entry_elapsed = self._entry_duration
                self._motion_timer.stop()
            self._render_and_place()
        elif getattr(self, '_exit_active', False):
            self._exit_elapsed += dt
            if self._exit_elapsed >= self._exit_duration:
                self._exit_active = False
                self._motion_timer.stop()
                if not getattr(self, "_is_closing", False):
                    self._is_closing = True
                    try:
                        self.finished.emit()
                    except Exception:
                        pass
                    QTimer.singleShot(50, self.close)
                return
            self._render_and_place()

    def _burst_tick(self):
        """Advance burst particle positions and fade out. Stops after ~700ms."""
        dt = 0.030  # 30ms in seconds
        self._burst_elapsed += dt * 1000
        duration = 700.0
        for pt in self._burst_particles:
            pt['x'] += pt['vx'] * dt
            pt['y'] += pt['vy'] * dt
            pt['vy'] += 60 * dt   # slight gravity
            fade = 1.0 - min(1.0, self._burst_elapsed / duration)
            pt['alpha'] = int(255 * fade)
        if self._burst_elapsed >= duration:
            self._burst_active = False
            self._burst_img_margin = 0
            self._burst_timer.stop()
        self._render_and_place()

    def _ring_tick(self):
        """Advance neon ring expansion for level-up toasts."""
        dt = 20.0  # 20ms
        self._ring_elapsed += dt
        max_r = self.width() if self.width() > 0 else 300
        all_done = True
        for ring in self._ring_rings:
            effective_elapsed = self._ring_elapsed - ring['delay']
            if effective_elapsed < 0:
                all_done = False
                continue
            t = min(1.0, effective_elapsed / self._ring_duration)
            ring['r'] = t * max_r
            ring['alpha'] = int(200 * (1.0 - t))
            if t < 1.0:
                all_done = False
        if all_done:
            self._ring_active = False
            self._ring_timer.stop()
        self._render_and_place()

    def _anim_tick(self):
        """Advance typewriter index, icon bounce, and energy flash, then re-render."""
        dt = 30.0  # 30ms
        changed = False

        # Typewriter (applies to title/line1)
        if getattr(self, '_tw_active', False) and getattr(self, '_tw_full', ''):
            if self._tw_idx < len(self._tw_full):
                self._tw_idx += 1
                changed = True
            else:
                self._tw_active = False
                if hasattr(self, '_tw_cursor_timer'):
                    self._tw_cursor_timer.stop()
                changed = True

        # Icon bounce
        if getattr(self, '_bounce_active', False):
            self._bounce_elapsed += dt
            if self._bounce_elapsed >= self._bounce_duration:
                self._bounce_active = False
                self._bounce_elapsed = self._bounce_duration
            changed = True

        # Energy flash (level-up only)
        if getattr(self, '_flash_active', False):
            self._flash_elapsed += dt
            if self._flash_elapsed >= self._flash_duration:
                self._flash_active = False
                self._flash_elapsed = self._flash_duration
            changed = True

        if changed:
            self._render_and_place()

        # Stop anim timer when typewriter, bounce, and flash are all done
        if (not getattr(self, '_tw_active', False) and
                not getattr(self, '_bounce_active', False) and
                not getattr(self, '_flash_active', False)):
            if hasattr(self, '_anim_timer'):
                self._anim_timer.stop()

    def _tw_cursor_blink(self):
        """Toggle cursor visibility for typewriter effect."""
        self._tw_cursor_visible = not getattr(self, '_tw_cursor_visible', True)
        if getattr(self, '_tw_active', False):
            self._render_and_place()



class AchToastManager(QObject):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.parent_gui = parent
        self._queue: list[tuple[str, str, int]] = []
        self._active = False
        self._active_window: Optional[AchToastWindow] = None

    def enqueue(self, title: str, rom: str, seconds: int = 5):
        """Fügt einen Toast in die Warteschlange ein."""
        self._queue.append((title, rom, seconds))
        if not self._active:
            self._show_next()

    def enqueue_level_up(self, title: str, level_number: int, seconds: int = 6):
        """Enqueue a special level-up toast."""
        self._queue.append((title, "__levelup__", seconds))
        if not self._active:
            self._show_next()

    def _show_next(self):
        if not self._queue:
            self._active = False
            self._active_window = None
            return
        
        self._active = True
        title, rom, seconds = self._queue.pop(0)
        win = AchToastWindow(self.parent_gui, title, rom, seconds)
        win.finished.connect(self._on_finished)
        self._active_window = win

    def _on_finished(self):
        self._active_window = None
        QTimer.singleShot(250, self._show_next)

