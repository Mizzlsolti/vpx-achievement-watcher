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

class FlipCounterOverlay(QWidget):
    def __init__(self, parent: "MainWindow", total: int, remaining: int, goal: int):
        super().__init__(None)
        self.parent_gui = parent
        self._total = int(total)
        self._remaining = int(remaining)
        self._goal = int(goal)
        self.setWindowTitle("Flip Counter")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background:transparent;")

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

    def _compose_image(self) -> QImage:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = 15
        title_pt = max(body_pt + 2, int(round(body_pt * 1.35)))

        title_color = QColor("#FF7F00")
        hi_color = QColor("#FFFFFF")

        title = f"Total flips: {int(self._total)}/{int(self._goal)}"
        sub = f"Remaining: {int(max(0, self._remaining))}"

        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)

        pad = max(12, int(body_pt * 0.9))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_w = fm_title.horizontalAdvance(title)
        sub_w = fm_body.horizontalAdvance(sub)
        text_w = max(title_w, sub_w)
        text_h = fm_title.height() + vgap + fm_body.height()
        content_w = max(280, text_w + 2 * pad)
        content_h = max(96, text_h + 2 * pad)

        img = QImage(content_w, content_h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            bg = QColor(8, 12, 22, 245)
            radius = 16
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(0, 0, content_w, content_h, radius, radius)

            _draw_glow_border(p, 0, 0, content_w, content_h, radius=radius,
                              low_perf=bool(ov.get("low_performance_mode", False)))

            p.setPen(title_color); p.setFont(f_title)
            p.drawText(QRect(0, pad, content_w, fm_title.height()),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), title)

            p.setPen(hi_color); p.setFont(f_body)
            p.drawText(QRect(0, pad + fm_title.height() + vgap, content_w, fm_body.height()),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), sub)
        finally:
            p.end()

        portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
        if portrait:
            ccw = bool(ov.get("flip_counter_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        ov = self.parent_gui.cfg.OVERLAY or {}
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("flip_counter_saved", ov.get("flip_counter_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("flip_counter_x_portrait", 100))
                y = int(ov.get("flip_counter_y_portrait", 100))
            else:
                x = int(ov.get("flip_counter_x_landscape", 100))
                y = int(ov.get("flip_counter_y_landscape", 100))
        else:
            pad = 40
            x = int(geo.left() + pad)
            y = int(geo.top() + pad)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.setGeometry(x, y, W, H)
        self._label.setGeometry(0, 0, W, H)
        self._label.setPixmap(QPixmap.fromImage(img))
        self.show()
        self.raise_()

    def update_counts(self, total: int, remaining: int, goal: int):
        self._total = int(total)
        self._remaining = int(remaining)
        self._goal = int(goal)
        self._render_and_place()

    def update_font(self):
        if self.isVisible():
            self._render_and_place()


class FlipCounterPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 380, height_hint: int = 130):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Flip Counter")
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
        if bool(ov.get("flip_counter_saved", ov.get("flip_counter_custom", False))):
            if self._portrait:
                x0 = int(ov.get("flip_counter_x_portrait", 100))
                y0 = int(ov.get("flip_counter_y_portrait", 100))
            else:
                x0 = int(ov.get("flip_counter_x_landscape", 100))
                y0 = int(ov.get("flip_counter_y_landscape", 100))
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
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = 15
        title_pt = max(body_pt + 2, int(round(body_pt * 1.35)))
        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)
        pad = max(12, int(body_pt * 0.9))
        vgap = max(4, int(body_pt * 0.25))
        # Use the configured goal so the picker matches the actual overlay size
        goal = int(ov.get("flip_counter_goal_total", 400))
        title = f"Total flips: {goal}/{goal}"
        sub = f"Remaining: {goal}"
        text_w = max(fm_title.horizontalAdvance(title), fm_body.horizontalAdvance(sub))
        text_h = fm_title.height() + vgap + fm_body.height()
        w = max(280, text_w + 2 * pad)
        h = max(96, text_h + 2 * pad)
        return w, h

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("flip_counter_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
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
        msg = "Flip Counter\nDrag to position. Click the button again to save"
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

