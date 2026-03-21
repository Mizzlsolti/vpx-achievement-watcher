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

from .helpers import _ease_out_cubic, _force_topmost, _start_topmost_timer

class StatusOverlay(QWidget):
    """Compact persistent status badge reflecting tracking/cloud state.

    Displays one of the agreed status states using traffic-light semantics:
      - Green:  ``Online · Tracking``, ``Online · Verified``
      - Yellow: ``Online · Pending``, ``Offline · Local``
      - Red:    ``Cloud Off · Local``

    Unlike MiniInfoOverlay (System Notifications), this overlay is a
    persistent mini-badge that stays visible while in-game.  It has no
    countdown timer and does not auto-dismiss; callers are responsible for
    calling :meth:`show_badge` / :meth:`hide_badge` based on game state.

    Uses its own config keys (``status_overlay_*``) and is completely
    independent from MiniInfoOverlay / System Notifications.
    """

    # Compact badge dimensions
    _BADGE_FONT_PT = 13
    _PAD_W = 22
    _PAD_H = 14
    _RADIUS = 12
    _MAX_TEXT_WIDTH = 340

    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Status")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._font_family = ov.get("font_family", "Segoe UI")
        # Traffic-light color for the dot indicator
        self._color = "#00C853"
        # Status text (one of the 5 agreed states)
        self._status_text = ""
        self._bg_color = QColor(8, 12, 22, 230)
        self._portrait_mode = bool(ov.get("status_overlay_portrait", False))
        self._rotate_ccw = bool(ov.get("status_overlay_rotate_ccw", False))
        self._last_center = (960, 540)
        self._snap_label = QLabel(self)
        self._snap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snap_label.setStyleSheet("background:transparent;")

        # Animation state
        low_perf = bool(ov.get("low_performance_mode", False))
        anim_status = bool(ov.get("anim_status", True))
        self._low_perf = low_perf or not anim_status
        # Scan-in animation
        self._scan_active: bool = False
        self._scan_elapsed: float = 0.0
        self._scan_duration: float = 220.0
        # Glow sweep animation (starts after scan-in)
        self._sweep_active: bool = False
        self._sweep_elapsed: float = 0.0
        self._sweep_duration: float = 350.0
        # Color morph animation
        self._morph_active: bool = False
        self._morph_elapsed: float = 0.0
        self._morph_duration: float = 200.0
        self._morph_from_color: str = "#00C853"
        self._morph_target_color: str = "#00C853"
        self._morph_from_text: str = ""
        self._morph_target_text: str = ""
        # Combined animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_tick)

        self.hide()
        _start_topmost_timer(self)

    def _primary_center(self) -> tuple[int, int]:
        try:
            scr = QApplication.primaryScreen()
            geo = scr.geometry() if scr else QRect(0, 0, 1280, 720)
            return geo.left() + geo.width() // 2, geo.top() + geo.height() // 2
        except Exception:
            return 640, 360

    def _compose_html(self) -> str:
        """Build compact badge HTML: colored dot + status text."""
        fam = str(getattr(self, "_font_family", "Segoe UI")).replace("'", "").replace('"', "").replace(";", "").replace("<", "").replace(">", "")
        pt = self._BADGE_FONT_PT
        dot_color = self._color
        text = str(self._status_text or "").strip()
        return (
            f"<span style='font-size:{pt}pt;font-family:\"{fam}\";'>"
            f"<span style='color:{dot_color};'>&#9679;</span>"
            f"&nbsp;<span style='color:#EEEEEE;'>{text}</span>"
            f"</span>"
        )

    def _render_badge_image(self, html: str) -> QImage:
        # Measure the actual rendered text size using a QLabel sizeHint so the
        # badge is sized to fit the content tightly (no excess right padding).
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet("color:#EEEEEE;background:transparent;")
        tmp.setFont(QFont(self._font_family, self._BADGE_FONT_PT))
        tmp.setWordWrap(False)
        tmp.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        tmp.setText(html)
        # sizeHint() gives the natural (unwrapped) dimensions of the label.
        sh = tmp.sizeHint()
        text_w = max(60, min(sh.width(), self._MAX_TEXT_WIDTH))
        text_h = max(1, sh.height())

        W = max(120, text_w + self._PAD_W)
        H = max(36, text_h + self._PAD_H)

        tmp.setFixedWidth(text_w)
        tmp.resize(text_w, text_h)

        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._bg_color)
            p.drawRoundedRect(0, 0, W, H, self._RADIUS, self._RADIUS)
            # Left-align content with equal horizontal padding on both sides
            margin_left = self._PAD_W // 2
            margin_top = (H - text_h) // 2
            tmp.render(p, QPoint(margin_left, margin_top))
            # Glow sweep animation (horizontal sweep line)
            if not getattr(self, '_low_perf', False) and getattr(self, '_sweep_active', False):
                sweep_t = min(1.0, getattr(self, '_sweep_elapsed', 0.0) / max(1.0, getattr(self, '_sweep_duration', 350.0)))
                sweep_x = int(sweep_t * (W + 60)) - 30
                sweep_alpha = int(160 * max(0.0, 1.0 - abs(sweep_t - 0.5) * 3.0))
                if sweep_alpha > 0:
                    from PyQt6.QtGui import QLinearGradient
                    grad = QLinearGradient(float(sweep_x - 20), 0.0, float(sweep_x + 20), 0.0)
                    grad.setColorAt(0.0, QColor(0, 229, 255, 0))
                    grad.setColorAt(0.5, QColor(0, 229, 255, sweep_alpha))
                    grad.setColorAt(1.0, QColor(0, 229, 255, 0))
                    p.setBrush(grad)
                    p.drawRoundedRect(0, 0, W, H, self._RADIUS, self._RADIUS)
        finally:
            p.end()
        return img

    def _refresh_view(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._portrait_mode = bool(ov.get("status_overlay_portrait", False))
        self._rotate_ccw = bool(ov.get("status_overlay_rotate_ccw", False))

        html = self._compose_html()
        img = self._render_badge_image(html)

        if self._portrait_mode:
            angle = -90 if self._rotate_ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        W, H = img.width(), img.height()

        use_saved = bool(ov.get("status_overlay_saved", False))
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)

        if use_saved:
            if self._portrait_mode:
                x = int(ov.get("status_overlay_x_portrait", 100))
                y = int(ov.get("status_overlay_y_portrait", 100))
            else:
                x = int(ov.get("status_overlay_x_landscape", 100))
                y = int(ov.get("status_overlay_y_landscape", 100))
        else:
            cx, cy = self._last_center
            x = int(cx - W // 2)
            y = int(cy - H // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(), min(y, geo.bottom() - H))

        # Apply scan-in x offset
        scan_offset = 0
        opacity = 1.0
        if not self._low_perf and getattr(self, '_scan_active', False):
            scan_t = min(1.0, getattr(self, '_scan_elapsed', 0.0) / max(1.0, self._scan_duration))
            eased = _ease_out_cubic(scan_t)
            scan_offset = int(30 * (1.0 - eased))
            opacity = max(0.0, min(1.0, eased))

        self.setGeometry(x + scan_offset, y, W, H)
        self._snap_label.setGeometry(0, 0, W, H)
        self._snap_label.setPixmap(QPixmap.fromImage(img))
        self.setWindowOpacity(opacity)
        self.show()
        self.raise_()
        _force_topmost(self)

    def _anim_tick(self):
        """Advance scan-in, sweep, and morph animations."""
        dt = 16.0
        needs_render = False

        # Scan-in
        if getattr(self, '_scan_active', False):
            self._scan_elapsed += dt
            if self._scan_elapsed >= self._scan_duration:
                self._scan_active = False
                self._scan_elapsed = self._scan_duration
                # Trigger glow sweep after scan-in
                if not self._low_perf:
                    self._sweep_active = True
                    self._sweep_elapsed = 0.0
            needs_render = True

        # Glow sweep
        if getattr(self, '_sweep_active', False):
            self._sweep_elapsed += dt
            if self._sweep_elapsed >= self._sweep_duration:
                self._sweep_active = False
                self._sweep_elapsed = self._sweep_duration
            needs_render = True

        # Color morph
        if getattr(self, '_morph_active', False):
            self._morph_elapsed += dt
            t = min(1.0, self._morph_elapsed / max(1.0, self._morph_duration))
            # Interpolate color
            fc = QColor(self._morph_from_color)
            tc = QColor(self._morph_target_color)
            r = int(fc.red() + (tc.red() - fc.red()) * t)
            g = int(fc.green() + (tc.green() - fc.green()) * t)
            b = int(fc.blue() + (tc.blue() - fc.blue()) * t)
            self._color = f"#{r:02X}{g:02X}{b:02X}"
            if t >= 1.0:
                self._morph_active = False
                self._color = self._morph_target_color
                self._status_text = self._morph_target_text
            needs_render = True

        if needs_render:
            self._refresh_view()

        # Stop timer if nothing active
        if (not getattr(self, '_scan_active', False) and
                not getattr(self, '_sweep_active', False) and
                not getattr(self, '_morph_active', False)):
            self._anim_timer.stop()

    def closeEvent(self, e):
        try:
            self._anim_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def update_font(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._font_family = str(ov.get("font_family", "Segoe UI"))
        if self.isVisible():
            self._refresh_view()

    def update_status(self, status_text: str, color_hex: str = "#00C853"):
        """Update the displayed status state and refresh the badge.

        This is the primary method for changing the badge content.  The badge
        remains visible after this call; use :meth:`hide_badge` to hide it.
        """
        new_text = str(status_text or "").strip()
        new_color = str(color_hex or "#00C853").strip()
        self._last_center = self._primary_center()

        if self._low_perf:
            # Low performance: instant switch, no animation
            self._status_text = new_text
            self._color = new_color
            self._refresh_view()
            return

        was_visible = self.isVisible()
        text_changed = (new_text != self._status_text)
        color_changed = (new_color != self._color)

        if not was_visible or (not self._status_text and new_text):
            # Badge newly appearing: trigger scan-in
            self._status_text = new_text
            self._color = new_color
            self._scan_active = True
            self._scan_elapsed = 0.0
            self._sweep_active = False
            self._morph_active = False
            self._anim_timer.start()
        elif text_changed or color_changed:
            # Status changing: morph color, pop text
            self._morph_from_color = self._color
            self._morph_target_color = new_color
            self._morph_from_text = self._status_text
            self._morph_target_text = new_text
            self._morph_active = True
            self._morph_elapsed = 0.0
            # Show new text immediately for readability; color morphs smoothly
            self._status_text = new_text
            self._anim_timer.start()
        else:
            self._status_text = new_text
            self._color = new_color

        self._refresh_view()

    def show_badge(self):
        """Make the badge visible (typically called on game start)."""
        if self._status_text:
            self._refresh_view()

    def hide_badge(self):
        """Hide the badge (typically called on game end)."""
        self.hide()

    def show_status(self, message: str, seconds: int = 5, color_hex: str | None = None):
        """Compatibility shim: update the status badge persistently.

        The ``seconds`` parameter is ignored; this overlay is persistent and
        does not auto-dismiss.  Use :meth:`hide_badge` to hide it explicitly.
        """
        self.update_status(message, color_hex or "#00C853")



class StatusOverlayPositionPicker(QWidget):
    """Draggable position picker for StatusOverlay, uses ``status_overlay_*`` config keys."""

    def __init__(self, parent: "MainWindow", width_hint: int = 420, height_hint: int = 100):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Status Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = False
        self._sync_from_cfg()
        self._base_w, self._base_h = self._calc_overlay_size()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h

        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._screen_geo()

        if bool(ov.get("status_overlay_saved", False)):
            if self._portrait:
                x0 = int(ov.get("status_overlay_x_portrait", 100))
                y0 = int(ov.get("status_overlay_y_portrait", 100))
            else:
                x0 = int(ov.get("status_overlay_x_landscape", 100))
                y0 = int(ov.get("status_overlay_y_landscape", 100))
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
        badge_font_pt = 13
        pad_w = 22
        pad_h = 14
        max_text_width = 340
        status_text = "Online · Tracking"
        html = (
            f"<span style='font-size:{badge_font_pt}pt;font-family:\"{font_family}\";'>"
            f"<span style='color:#00C853;'>&#9679;</span>"
            f"&nbsp;<span style='color:#EEEEEE;'>{status_text}</span>"
            f"</span>"
        )
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet("color:#EEEEEE;background:transparent;")
        tmp.setFont(QFont(font_family, badge_font_pt))
        tmp.setWordWrap(False)
        tmp.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        tmp.setText(html)
        sh = tmp.sizeHint()
        text_w = max(60, min(sh.width(), max_text_width))
        text_h = max(1, sh.height())
        W = max(120, text_w + pad_w)
        H = max(36, text_h + pad_h)
        return W, H

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("status_overlay_portrait", False))
            self._ccw = bool(ov.get("status_overlay_rotate_ccw", False))
        except Exception:
            self._portrait = False
            self._ccw = False

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
        msg = "Status Overlay\nDrag to position. Click the button again to save"
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


