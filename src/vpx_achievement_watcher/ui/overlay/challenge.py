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

from vpx_achievement_watcher.core.helpers import APP_DIR
from vpx_achievement_watcher.input.hooks import register_raw_input_for_window

from .helpers import _draw_glow_border, _ease_out_cubic, _start_topmost_timer

class ChallengeOVPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 520, height_hint: int = 200):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Challenge Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        self._base_w, self._base_h = self._calc_overlay_size()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._screen_geo()
        # fall back to legacy "custom" key for backward compatibility with older configs
        if bool(ov.get("ch_ov_saved", ov.get("ch_ov_custom", False))):
            if self._portrait:
                x0 = int(ov.get("ch_ov_x_portrait", 100))
                y0 = int(ov.get("ch_ov_y_portrait", 100))
            else:
                x0 = int(ov.get("ch_ov_x_landscape", 100))
                y0 = int(ov.get("ch_ov_y_landscape", 100))
        else:
            x0 = int(geo.left() + (geo.width() - self._w) // 2)
            y0 = int(geo.top() + (geo.height() - self._h) // 2)
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            scr = QApplication.primaryScreen()
            if scr:
                return scr.availableGeometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _calc_overlay_size(self) -> tuple[int, int]:
        return 520, 200

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
            self._base_w, self._base_h = self._calc_overlay_size()
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h
            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            x = min(max(geo.left(), x), geo.right() - self._w)
            y = min(max(geo.top(),  y), geo.bottom() - self._h)
            self.setGeometry(x, y, self._w, self._h)
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(8, 12, 22, 245))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Challenge Overlay\nDrag to position. Click the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            x = min(max(geo.left(), target.x()), geo.right() - self._w)
            y = min(max(geo.top(),  target.y()), geo.bottom() - self._h)
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())


class ChallengeCountdownOverlay(QWidget):
    def __init__(self, parent, total_seconds: int = 300):
        super().__init__(parent)
        self.parent_gui = parent
        self._left = max(1, int(total_seconds))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(400, 120)
        self.show()
        try:
            import win32gui, win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
        except Exception:
            pass
        self._render_and_place()
        _start_topmost_timer(self)

    def _tick(self):
        self._left -= 1
        if self._left <= 0:
            self._left = 0
            try:
                self._timer.stop()
                self._render_and_place()  
            except Exception:
                pass
            QTimer.singleShot(200, self.close)
            return
        self._render_and_place()

    def _render_and_place(self):
        img = self._compose_image()
        if img is None:
            return
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("ch_timer_saved", ov.get("ch_timer_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_timer_x_portrait", 100))
                y = int(ov.get("ch_timer_y_portrait", 100))
            else:
                x = int(ov.get("ch_timer_x_landscape", 100))
                y = int(ov.get("ch_timer_y_landscape", 100))
        else:
            pad = 40
            x = int(geo.left() + pad)
            y = int(geo.bottom() - H - pad)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def _compose_image(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        factor = 1.0  # Challenge timer is always fixed size (100%)
        w = max(200, int(round(400 * factor)))
        h = max(60, int(round(120 * factor)))
        timer_font_pt = max(20, int(round(48 * factor)))
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(8, 12, 22, 245))
        p.drawRoundedRect(0, 0, w, h, 16, 16)
        _draw_glow_border(p, 0, 0, w, h, radius=16,
                          low_perf=bool(ov.get("low_performance_mode", False)))
        # Turn red when 10 seconds or fewer remain
        if self._left <= 10:
            p.setPen(QColor("#FF2020"))
        else:
            p.setPen(Qt.GlobalColor.white)
        mins, secs = divmod(self._left, 60)
        txt = f"{mins:02d}:{secs:02d}"
        font = QFont(font_family, timer_font_pt, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, txt)
        p.end()
        try:
            portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_timer_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pass
        return img

    def update_font(self):
        if self.isVisible():
            self._render_and_place()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix"):
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()
            

class ChallengeSelectOverlay(QWidget):
    def __init__(self, parent: "MainWindow", selected_idx: int = 0):
        super().__init__(parent)
        self.parent_gui = parent
        self._selected = int(selected_idx) % 4
        self._prev_selected = self._selected
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pulse_t = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50) 
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))
        anim_challenge = bool(parent.cfg.OVERLAY.get("anim_challenge", True))
        self._low_perf = low_perf or not anim_challenge
        # Carousel slide animation
        self._slide_active: bool = False
        self._slide_t: float = 0.0
        self._slide_duration: float = 180.0
        self._slide_elapsed: float = 0.0
        self._slide_dir: int = 1  # 1 = right, -1 = left
        self._slide_timer = QTimer(self)
        self._slide_timer.setInterval(16)
        self._slide_timer.timeout.connect(self._on_slide_tick)
        if not self._low_perf:
            self._pulse_timer.start()
        self._pix = None
        self._render_and_place()
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
        _start_topmost_timer(self)

    def closeEvent(self, e):
        try:
            if getattr(self, "_pulse_timer", None):
                self._pulse_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "_slide_timer", None):
                self._slide_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.08) % 1.0
        self._render_and_place()

    def _on_slide_tick(self):
        self._slide_elapsed += 16.0
        self._slide_t = min(1.0, self._slide_elapsed / max(1.0, self._slide_duration))
        if self._slide_t >= 1.0:
            self._slide_active = False
            self._slide_timer.stop()
        self._render_and_place()

    def set_selected(self, idx: int):
        new_idx = int(idx) % 4
        if new_idx != self._selected and not getattr(self, '_low_perf', False):
            # Determine slide direction: going "right" in list = slide left
            self._slide_dir = 1 if new_idx > self._selected else -1
            self._prev_selected = self._selected
            self._slide_active = True
            self._slide_t = 0.0
            self._slide_elapsed = 0.0
            self._slide_timer.start()
        else:
            self._prev_selected = new_idx
        self._selected = new_idx
        self._render_and_place()

    def apply_portrait_from_cfg(self):
        self._render_and_place()

    def update_font(self):
        if self.isVisible():
            self._render_and_place()

    def _compose_image(self) -> QImage:
        from math import sin, pi

        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        base_body_pt = 20
        scaled_body_pt = 20  # Challenge select is always fixed size (100%)
        hint_pt = max(8, int(round(scaled_body_pt * 0.8)))

        text_color = QColor("#FFFFFF")
        hi_color = QColor("#FF7F00")

        _CHALLENGE_LABELS = [
            ("⌛ Timed Challenge", "3:00 minutes playing time."),
            ("🎯 Flip Challenge", "Count Left+Right flips until chosen target."),
            ("🔥 Heat Challenge", "Keep heat below 100%. Don't spam or hold flippers!"),
            ("❌ Exit", "Close the challenge menu."),
        ]

        def _label_for(idx: int):
            return _CHALLENGE_LABELS[idx % 4]

        title_text, desc_text = _label_for(int(getattr(self, "_selected", 0) or 0))

        factor = scaled_body_pt / 20.0
        w = max(280, int(round(520 * factor)))
        h = max(110, int(round(200 * factor)))
        pad_lr = max(10, int(round(20 * factor)))
        top_pad = max(12, int(round(24 * factor)))
        bottom_pad = max(9, int(round(18 * factor)))
        hint_gap = max(5, int(round(10 * factor)))
        avail_w = w - 2 * pad_lr

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(8, 12, 22, 245))
            radius = 16
            p.drawRoundedRect(0, 0, w, h, radius, radius)

            _draw_glow_border(p, 0, 0, w, h, radius=radius,
                              low_perf=bool(ov.get("low_performance_mode", False)))

            title_pt = scaled_body_pt + 6
            desc_pt = max(10, scaled_body_pt)
            min_title = 12
            min_desc = 10

            flags_wrap_center = int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap)

            def measure_heights(t_pt: int, d_pt: int, title_text: str, desc_text: str) -> tuple[int, int]:
                fm_t = QFontMetrics(QFont(font_family, t_pt, QFont.Weight.Bold))
                fm_d = QFontMetrics(QFont(font_family, d_pt))
                rect = QRect(0, 0, avail_w, 10000)
                t_bbox = fm_t.boundingRect(rect, flags_wrap_center, title_text)
                d_bbox = fm_d.boundingRect(rect, flags_wrap_center, desc_text)
                return t_bbox.height(), d_bbox.height()

            fm_hint = QFontMetrics(QFont(font_family, hint_pt))
            hint_h = fm_hint.height()
            max_content_h = h - top_pad - bottom_pad - hint_gap - hint_h

            for _ in range(64):
                t_h, d_h = measure_heights(title_pt, desc_pt, title_text, desc_text)
                total = t_h + 6 + d_h
                if total <= max_content_h:
                    break
                if title_pt > min_title: title_pt -= 1
                if desc_pt > min_desc: desc_pt -= 1
                if title_pt <= min_title and desc_pt <= min_desc: break

            t_h, d_h = measure_heights(title_pt, desc_pt, title_text, desc_text)
            block_h = t_h + 6 + d_h
            content_top = top_pad + max(0, (max_content_h - block_h) // 2)

            # Carousel slide: blend between previous and current content
            slide_active = not getattr(self, '_low_perf', False) and getattr(self, '_slide_active', False)
            if slide_active:
                slide_t = getattr(self, '_slide_t', 0.0)
                eased = _ease_out_cubic(slide_t)
                slide_dir = getattr(self, '_slide_dir', 1)
                # Current item: slides in from direction
                cur_x_offset = int((1.0 - eased) * slide_dir * (avail_w // 2))
                cur_alpha = int(255 * eased)
                # Previous item: slides out in opposite direction
                prev_title, prev_desc = _label_for(int(getattr(self, '_prev_selected', self._selected)))
                prev_x_offset = int(-eased * slide_dir * (avail_w // 2))
                prev_alpha = int(255 * (1.0 - eased))

                # Set clip region to content area
                p.setClipRect(pad_lr, content_top, avail_w, block_h + 10)

                # Draw previous content (fading out, sliding away)
                p.setOpacity(max(0.0, min(1.0, prev_alpha / 255.0)))
                p.setPen(hi_color)
                p.setFont(QFont(font_family, title_pt, QFont.Weight.Bold))
                p.drawText(QRect(pad_lr + prev_x_offset, content_top, avail_w, t_h), flags_wrap_center, prev_title)
                p.setPen(text_color)
                p.setFont(QFont(font_family, desc_pt))
                p.drawText(QRect(pad_lr + prev_x_offset, content_top + t_h + 6, avail_w, d_h), flags_wrap_center, prev_desc)

                # Draw current content (fading in, sliding in)
                p.setOpacity(max(0.0, min(1.0, cur_alpha / 255.0)))
                p.setPen(hi_color)
                p.setFont(QFont(font_family, title_pt, QFont.Weight.Bold))
                title_rect = QRect(pad_lr + cur_x_offset, content_top, avail_w, t_h)
                p.drawText(title_rect, flags_wrap_center, title_text)
                p.setPen(text_color)
                p.setFont(QFont(font_family, desc_pt))
                desc_rect = QRect(pad_lr + cur_x_offset, content_top + t_h + 6, avail_w, d_h)
                p.drawText(desc_rect, flags_wrap_center, desc_text)

                p.setOpacity(1.0)
                p.setClipping(False)
            else:
                # Static (no slide)
                p.setPen(hi_color)
                p.setFont(QFont(font_family, title_pt, QFont.Weight.Bold))
                title_rect = QRect(pad_lr, content_top, avail_w, t_h)
                p.drawText(title_rect, flags_wrap_center, title_text)

                p.setPen(text_color)
                p.setFont(QFont(font_family, desc_pt))
                desc_rect = QRect(pad_lr, title_rect.bottom() + 6, avail_w, d_h)
                p.drawText(desc_rect, flags_wrap_center, desc_text)

            p.setPen(QColor("#AAAAAA"))
            p.setFont(QFont(font_family, hint_pt))
            hint_rect = QRect(0, h - bottom_pad - hint_h, w, hint_h)
            if int(getattr(self, "_selected", 0) or 0) % 4 == 3:
                hint_label = "Press Hotkey to close"
            else:
                hint_label = "Press Hotkey to start"
            p.drawText(hint_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), hint_label)

            # Pulsating ice-blue arrows (always at static content position for stability)
            arrow_cy_rect = QRect(pad_lr, content_top, avail_w, t_h)
            amp = 0.5 + 0.5 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
            alpha = 110 + int(120 * amp)
            anim_scale = 0.9 + 0.2 * amp
            wobble = 2.0 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
            base_arr_h = max(10, int(round(18 * factor)))
            ah = int(base_arr_h * anim_scale)
            aw = max(6, int(ah * 0.6))
            cy = arrow_cy_rect.center().y()
            left_cx = pad_lr + max(12, int(round(24 * factor))) + int(-wobble)
            right_cx = w - pad_lr - max(12, int(round(24 * factor))) + int(wobble)
            
            arrow_color = QColor("#00E5FF")
            arrow_color.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(arrow_color)

            p.drawPolygon(*[QPoint(left_cx - aw // 2, cy), QPoint(left_cx + aw // 2, cy - ah // 2), QPoint(left_cx + aw // 2, cy + ah // 2)])
            p.drawPolygon(*[QPoint(right_cx + aw // 2, cy), QPoint(right_cx - aw // 2, cy - ah // 2), QPoint(right_cx - aw // 2, cy + ah // 2)])

        finally:
            try: p.end()
            except Exception: pass

        try:
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception: pass

        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("ch_ov_saved", ov.get("ch_ov_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_ov_x_portrait", 100))
                y = int(ov.get("ch_ov_y_portrait", 100))
            else:
                x = int(ov.get("ch_ov_x_landscape", 100))
                y = int(ov.get("ch_ov_y_landscape", 100))
        else:
            x = int(geo.left() + (geo.width() - W) // 2)
            y = int(geo.top()  + (geo.height() - H) // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()


class FlipDifficultyOverlay(QWidget):
    def __init__(self, parent: "MainWindow", selected_idx: int = 1,
                 options: list[tuple[str, int]] = None):
        super().__init__(parent)
        self.parent_gui = parent

        # default options expanded/reordered
        default_options = [("Easy", 400), ("Medium", 300), ("Difficult", 200), ("Pro", 100)]
        self._options = list(options) if isinstance(options, list) and options else default_options

        # clamp selection to available options
        self._selected = max(0, min(int(selected_idx or 0), len(self._options) - 1))

        self._pulse_t = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))
        anim_challenge = bool(parent.cfg.OVERLAY.get("anim_challenge", True))
        self._low_perf = low_perf or not anim_challenge
        # Slot-machine snap animation
        self._snap_active: bool = False
        self._snap_elapsed: float = 0.0
        self._snap_duration: float = 160.0
        self._snap_timer = QTimer(self)
        self._snap_timer.setInterval(16)
        self._snap_timer.timeout.connect(self._on_snap_tick)
        if not self._low_perf:
            self._pulse_timer.start()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pix = None
        self._render_and_place()
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
        _start_topmost_timer(self)

    def closeEvent(self, e):
        try:
            if getattr(self, "_pulse_timer", None):
                self._pulse_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "_snap_timer", None):
                self._snap_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.08) % 1.0
        self._render_and_place()

    def _on_snap_tick(self):
        self._snap_elapsed += 16.0
        if self._snap_elapsed >= self._snap_duration:
            self._snap_active = False
            self._snap_elapsed = self._snap_duration
            self._snap_timer.stop()
        self._render_and_place()

    def set_selected(self, idx: int):
        new_idx = max(0, min(int(idx or 0), len(self._options) - 1))
        if new_idx != self._selected and not getattr(self, '_low_perf', False):
            self._snap_active = True
            self._snap_elapsed = 0.0
            self._snap_timer.start()
        self._selected = new_idx
        self._render_and_place()

    def selected_option(self) -> tuple[str, int]:
        return self._options[self._selected]

    def apply_portrait_from_cfg(self):
        self._render_and_place()

    def update_font(self):
        if self.isVisible():
            self._render_and_place()

    def _compose_image(self) -> QImage:
        from math import sin, pi
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        base_body_pt = 20
        scaled_body_pt = 20  # Flip difficulty overlay is always fixed size (100%)
        hint_pt = max(8, int(round(scaled_body_pt * 0.8)))
        text_color = QColor("#FFFFFF")
        hi_color = QColor("#FF7F00")

        factor = scaled_body_pt / 20.0
        w = max(300, int(round(560 * factor)))
        h = max(130, int(round(240 * factor)))
        pad_lr = max(12, int(round(24 * factor)))
        top_pad = max(13, int(round(26 * factor)))
        bottom_pad = max(9, int(round(18 * factor)))
        gap_title_desc = max(4, int(round(8 * factor)))
        spacing = max(8, int(round(15 * factor)))
        hint_line_h = max(10, int(round(18 * factor)))
        avail_w = w - 2 * pad_lr

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(8, 12, 22, 245))
            radius = 16
            p.drawRoundedRect(0, 0, w, h, radius, radius)
            _draw_glow_border(p, 0, 0, w, h, radius=radius,
                              low_perf=bool(ov.get("low_performance_mode", False)))

            title = "Flip Challenge – Choose difficulty"
            title_font_pt = scaled_body_pt + 6
            p.setPen(hi_color)
            p.setFont(QFont(font_family, title_font_pt, QFont.Weight.Bold))
            fm_t = QFontMetrics(QFont(font_family, title_font_pt, QFont.Weight.Bold))
            t_h = fm_t.height()
            p.drawText(QRect(pad_lr, top_pad, avail_w, t_h),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), title)

            y0 = top_pad + t_h + gap_title_desc
            n = max(1, len(self._options))
            total_spacing = spacing * (n - 1)
            box_w = max(60, int((avail_w - total_spacing) / n))
            box_h = max(50, int(round(100 * factor)))
            inner_pad = max(5, int(round(10 * factor)))

            def draw_option(ix: int, name: str, flips: int, selected: bool):
                x = pad_lr + ix * (box_w + spacing)
                rect = QRect(x, y0, box_w, box_h)

                # Snap pulse: brief scale + flash on selection change
                snap_scale = 1.0
                snap_flash_alpha = 0
                if selected and not getattr(self, '_low_perf', False) and getattr(self, '_snap_active', False):
                    snap_t = min(1.0, getattr(self, '_snap_elapsed', 0.0) / max(1.0, self._snap_duration))
                    # Scale: 1.0 → 1.07 → 1.0 (peak at t=0.3)
                    snap_scale = 1.0 + 0.07 * max(0.0, 1.0 - abs(snap_t - 0.3) / 0.3)
                    snap_flash_alpha = int(120 * max(0.0, 1.0 - snap_t * 2.0))

                if snap_scale != 1.0:
                    expand = int((snap_scale - 1.0) * box_w / 2)
                    draw_rect = rect.adjusted(-expand, -expand, expand, expand)
                else:
                    draw_rect = rect

                if selected:
                    amp = 0.5 + 0.5 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
                    alpha = 40 + int(60 * amp)
                    p.fillRect(draw_rect.adjusted(-4, -4, 4, 4), QColor(255, 127, 0, alpha))
                    p.setPen(QPen(QColor("#00E5FF"), 2))
                    if snap_flash_alpha > 0:
                        p.fillRect(draw_rect, QColor(255, 255, 255, snap_flash_alpha))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 80), 1))

                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(draw_rect, 10, 10)

                name_pt = scaled_body_pt + (2 if selected else 0)
                p.setPen(QColor("#FF7F00") if selected else QColor("#FFFFFF"))
                p.setFont(QFont(font_family, name_pt, QFont.Weight.Bold))
                fm_n = QFontMetrics(QFont(font_family, name_pt, QFont.Weight.Bold))
                name_h = fm_n.height()
                p.drawText(QRect(x, y0 + inner_pad, box_w, name_h),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), name)
                
                flips_pt = scaled_body_pt
                p.setFont(QFont(font_family, flips_pt))
                fm_f = QFontMetrics(QFont(font_family, flips_pt))
                p.drawText(QRect(x, y0 + inner_pad + name_h + max(4, int(round(6 * factor))), box_w, fm_f.height()),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), f"{int(flips)} flips")

            for i, (nm, fl) in enumerate(self._options):
                draw_option(i, nm, fl, i == self._selected)

            p.setPen(QColor("#AAAAAA"))
            p.setFont(QFont(font_family, hint_pt))
            p.drawText(QRect(0, h - bottom_pad - hint_line_h, w, hint_line_h),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                       "Select with Left/Right, press Hotkey to start")
        finally:
            try: p.end()
            except Exception: pass

        try:
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception: pass
        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        use_saved = bool(ov.get("ch_ov_saved", ov.get("ch_ov_custom", False)))
        portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_ov_x_portrait", 100)); y = int(ov.get("ch_ov_y_portrait", 100))
            else:
                x = int(ov.get("ch_ov_x_landscape", 100)); y = int(ov.get("ch_ov_y_landscape", 100))
        else:
            x = int(geo.left() + (geo.width() - W) // 2)
            y = int(geo.top()  + (geo.height() - H) // 2)
        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()




class ChallengeStartCountdown(QWidget):
    """Full-screen transparent countdown overlay: 3…2…1…GO!

    Each number scales from 2.0x → 1.0x with Ease-Out over 800ms.
    After '1', a brief 'GO!' text appears in orange with scale 1.0 → 1.5 + fade-out.
    Total duration: ~3.5 s.  Emits `finished` when the animation ends and auto-closes.
    """

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Cover the primary screen
        screen = QApplication.primaryScreen()
        geo = screen.geometry() if screen else QRect(0, 0, 1280, 720)
        self.setGeometry(geo)

        self._low_perf = False
        try:
            self._low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))
        except Exception:
            pass

        # Countdown sequence: ('3', cyan), ('2', cyan), ('1', cyan), ('GO!', orange)
        self._steps = [
            ('3',   QColor('#00E5FF'), 800, False),
            ('2',   QColor('#00E5FF'), 800, False),
            ('1',   QColor('#00E5FF'), 800, False),
            ('GO!', QColor('#FF7F00'), 500, True),   # last step fades out
        ]
        self._step_idx = 0
        self._step_elapsed = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(50 if self._low_perf else 16)
        self._timer.timeout.connect(self._tick)

        _start_topmost_timer(self)

    def start(self):
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self):
        if self._step_idx >= len(self._steps):
            self._timer.stop()
            self.finished.emit()
            self.close()
            return
        self._step_elapsed += float(self._timer.interval())
        _, _, duration, _ = self._steps[self._step_idx]
        if self._step_elapsed >= duration:
            self._step_elapsed = 0.0
            self._step_idx += 1
            if self._step_idx >= len(self._steps):
                self._timer.stop()
                self.finished.emit()
                self.close()
                return
        self.update()

    def paintEvent(self, event):
        if self._step_idx >= len(self._steps):
            return
        label, color, duration, is_go = self._steps[self._step_idx]
        t = min(1.0, self._step_elapsed / max(1.0, duration))
        eased = _ease_out_cubic(t)

        W, H = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            if self._low_perf:
                scale = 1.0
                p.setOpacity(1.0)
            elif is_go:
                # GO! fades out while scaling 1.0 → 1.5
                scale = 1.0 + 0.5 * eased
                opacity = max(0.0, 1.0 - eased)
                p.setOpacity(opacity)
            else:
                # Numbers scale 2.0 → 1.0
                scale = 2.0 - eased
                p.setOpacity(1.0)

            font_size = int(80 * scale)
            font = QFont("Segoe UI", max(12, font_size), QFont.Weight.Bold)
            p.setFont(font)

            if not self._low_perf:
                # Glow effect
                glow_col = QColor(color.red(), color.green(), color.blue(), 60)
                for r in range(4, 0, -1):
                    gp = QPen(glow_col)
                    gp.setWidth(r * 3)
                    p.setPen(gp)
                    p.drawText(QRect(0, 0, W, H),
                               Qt.AlignmentFlag.AlignCenter, label)

            # Main text
            p.setPen(QPen(color))
            p.drawText(QRect(0, 0, W, H),
                       Qt.AlignmentFlag.AlignCenter, label)
        finally:
            try:
                p.end()
            except Exception:
                pass

