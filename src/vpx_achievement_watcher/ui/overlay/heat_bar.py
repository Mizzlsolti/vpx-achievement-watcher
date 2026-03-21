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

from .helpers import _draw_glow_border, _start_topmost_timer

class HeatBarometerOverlay(QWidget):
    """Vertical heat barometer overlay for Heat Challenge. Fills bottom-to-top,
    colour transitions from green (0-50%) to orange (50-85%) to red (>85%)."""

    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self._heat = 0
        self.setWindowTitle("Heat Barometer")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Reactive pulse animation timer (warning/critical)
        ov = self.parent_gui.cfg.OVERLAY or {}
        low_perf = bool(ov.get("low_performance_mode", False))
        anim_challenge = bool(ov.get("anim_challenge", True))
        self._low_perf = low_perf or not anim_challenge
        self._pulse_t: float = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
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

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.1) % 1.0
        self._render_and_place()

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))
        # Start/stop pulse timer based on heat level and low_perf
        if not self._low_perf and self._heat >= 65:
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        else:
            if self._pulse_timer.isActive():
                self._pulse_timer.stop()
        self._render_and_place()

    def closeEvent(self, e):
        try:
            self._pulse_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _bar_color(self, heat: int) -> QColor:
        if heat <= 50:
            # 0-50%: blend from green (0,200,0) toward yellow (255,200,0)
            r = int(heat * 255 / 50)
            return QColor(r, 200, 0)
        elif heat <= 85:
            # 50-85%: blend from yellow toward deep orange/red
            frac = (heat - 50) / 35.0
            r = 255
            g = int(200 * (1.0 - frac))
            return QColor(r, g, 0)
        else:
            # >85%: solid danger red
            return QColor(220, 30, 0)

    def _compose_image(self) -> QImage:
        bar_w = 36
        bar_h = 220
        label_h = 28
        pad = 6
        w = bar_w + 2 * pad
        h = bar_h + label_h + 2 * pad

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # background
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(8, 12, 22, 245))
            p.drawRoundedRect(0, 0, w, h, 10, 10)

            # border with glow
            ov = self.parent_gui.cfg.OVERLAY or {}
            _draw_glow_border(p, 0, 0, w, h, radius=10,
                              low_perf=bool(ov.get("low_performance_mode", False)))

            # bar background (track)
            bx = pad
            by = pad
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(40, 40, 40, 255))
            p.drawRoundedRect(bx, by, bar_w, bar_h, 6, 6)

            # fill from bottom upward
            fill_h = int(bar_h * self._heat / 100)
            if fill_h > 0:
                fill_y = by + bar_h - fill_h
                p.setBrush(self._bar_color(self._heat))
                p.drawRoundedRect(bx, fill_y, bar_w, fill_h, 6, 6)

            # label
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            label_rect = QRect(0, pad + bar_h, w, label_h)
            p.drawText(label_rect, int(Qt.AlignmentFlag.AlignCenter), f"{self._heat}%")

            # Reactive warning/critical pulse border (no success effect for overheating)
            ov = self.parent_gui.cfg.OVERLAY or {}
            low_perf = bool(ov.get("low_performance_mode", False))
            if self._heat >= 65:
                if not low_perf:
                    from math import sin, pi as _pi
                    pulse_t = getattr(self, '_pulse_t', 0.0)
                    amp = 0.5 + 0.5 * sin(2 * _pi * pulse_t)
                    if self._heat > 85:
                        # Critical zone: red, intense animated pulse
                        pulse_alpha = int(180 + 60 * amp)
                        pulse_width = 2 + int(2 * amp)
                        pulse_color = QColor(255, 40, 0, min(255, pulse_alpha))
                    else:
                        # Warning zone (65-85%): orange, moderate animated pulse
                        pulse_alpha = int(120 + 40 * amp)
                        pulse_width = 2
                        pulse_color = QColor(255, 140, 0, min(255, pulse_alpha))
                    pulse_pen = QPen(pulse_color)
                    pulse_pen.setWidth(pulse_width)
                    p.setPen(pulse_pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(1, 1, w - 2, h - 2, 10, 10)
                elif self._heat > 85:
                    # Low performance mode: static red border at critical heat only
                    pulse_pen = QPen(QColor(255, 60, 0, 200))
                    pulse_pen.setWidth(3)
                    p.setPen(pulse_pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(1, 1, w - 2, h - 2, 10, 10)
        finally:
            p.end()

        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            portrait = bool(ov.get("heat_bar_portrait", ov.get("portrait_mode", False)))
            if portrait:
                angle = -90 if bool(ov.get("heat_bar_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pass

        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        ov = self.parent_gui.cfg.OVERLAY or {}
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        portrait = bool(ov.get("heat_bar_portrait", ov.get("portrait_mode", False)))
        use_saved = bool(ov.get("heat_bar_saved", ov.get("heat_bar_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("heat_bar_x_portrait", 20))
                y = int(ov.get("heat_bar_y_portrait", 100))
            else:
                x = int(ov.get("heat_bar_x_landscape", 20))
                y = int(ov.get("heat_bar_y_landscape", 100))
        else:
            x = int(geo.left() + 20)
            y = int(geo.top() + (geo.height() - H) // 2)

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



class HeatBarPositionPicker(QWidget):
    """Draggable dummy widget to position the HeatBarometerOverlay."""

    def __init__(self, parent: "MainWindow", width_hint: int = 48, height_hint: int = 260):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Heat Bar")
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
        if bool(ov.get("heat_bar_saved", ov.get("heat_bar_custom", False))):
            if self._portrait:
                x0 = int(ov.get("heat_bar_x_portrait", 20))
                y0 = int(ov.get("heat_bar_y_portrait", 100))
            else:
                x0 = int(ov.get("heat_bar_x_landscape", 20))
                y0 = int(ov.get("heat_bar_y_landscape", 100))
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
        bar_w = 36
        bar_h = 220
        label_h = 28
        pad = 6
        w = bar_w + 2 * pad
        h = bar_h + label_h + 2 * pad
        return w, h

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("heat_bar_portrait", ov.get("portrait_mode", False)))
            self._ccw = bool(ov.get("heat_bar_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = False
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
        pen = QPen(QColor("#00E5FF"))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        msg = "Heat Bar\nDrag to position. Click the button again to save"
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

