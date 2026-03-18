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
    QPainter, QImage, QPen,
)

from watcher_core import APP_DIR, register_raw_input_for_window


def _draw_glow_border(painter: QPainter, x: int, y: int, w: int, h: int,
                      radius: int = 18, color: QColor = None, layers: int = 3,
                      low_perf: bool = False):
    """Draw a multi-layer neon glow border for a modern sci-fi look."""
    if color is None:
        color = QColor("#00E5FF")
    if not low_perf:
        # Outer glow layers
        for i in range(layers, 0, -1):
            alpha = int(30 * (layers + 1 - i))
            glow_pen = QPen(QColor(color.red(), color.green(), color.blue(), alpha))
            glow_pen.setWidth(i * 2)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(x + i, y + i, w - 2 * i, h - 2 * i, radius, radius)
    # Sharp inner border
    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(x + 1, y + 1, w - 2, h - 2, radius, radius)


def _ease_out_bounce(t: float) -> float:
    """Ease-out bounce curve used for icon stamp animation."""
    if t < 1 / 2.75:
        return 7.5625 * t * t
    elif t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    elif t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    else:
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375


def _ease_out_cubic(t: float) -> float:
    """Ease-out cubic curve used for slide transitions."""
    return 1.0 - (1.0 - t) ** 3


def _force_topmost(widget: QWidget):
    """Force a widget to the topmost z-order using Win32 API.
    Works even against fullscreen DirectX/OpenGL applications.
    No-ops silently when the widget is not visible or win32 is unavailable."""
    if not widget.isVisible():
        return
    try:
        import win32gui, win32con
        hwnd = int(widget.winId())
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
        )
    except Exception:
        pass


def _start_topmost_timer(widget: QWidget, interval_ms: int = 3000):
    """Start a periodic timer that re-applies HWND_TOPMOST to keep the widget above fullscreen apps.
    The timer is stored as widget._topmost_timer to prevent garbage collection."""
    timer = QTimer(widget)
    timer.setInterval(interval_ms)
    timer.timeout.connect(lambda: _force_topmost(widget))
    timer.start()
    widget._topmost_timer = timer


class OverlayNavArrows(QWidget):
    """Pulsating ice-blue navigation arrows displayed over the main overlay to indicate page cycling."""

    def __init__(self, parent: "OverlayWindow"):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pulse_t = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(80)
        self._pulse_timer.timeout.connect(self._on_tick)
        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent()
        low_perf = False
        try:
            low_perf = bool(parent.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
        except Exception:
            pass
        if not low_perf and not self._pulse_timer.isActive():
            self._pulse_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._pulse_timer.stop()

    def _on_tick(self):
        self._pulse_t = (self._pulse_t + 0.13) % 1.0
        self.update()

    def paintEvent(self, event):
        from math import sin, pi
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return

        parent = self.parent()
        portrait = getattr(parent, "portrait_mode", False)
        ccw = getattr(parent, "rotate_ccw", True)

        low_perf = False
        try:
            low_perf = bool(parent.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
        except Exception:
            pass

        if portrait:
            draw_w, draw_h = H, W
        else:
            draw_w, draw_h = W, H

        img = QImage(draw_w, draw_h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            if low_perf:
                alpha = 180
                scale = 1.0
                wobble = 0
            else:
                amp = 0.5 + 0.5 * sin(2 * pi * self._pulse_t)
                alpha = 110 + int(120 * amp)
                scale = 0.9 + 0.2 * amp
                wobble = 2.0 * sin(2 * pi * self._pulse_t)
            base_h = 18
            ah = int(base_h * scale)
            aw = max(6, int(ah * 0.6))
            cy = draw_h // 2
            pad = 16
            left_cx = pad + int(-wobble)
            right_cx = draw_w - pad + int(wobble)
            arrow_color = QColor("#00E5FF")
            arrow_color.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(arrow_color)
            # Left-pointing arrow
            p.drawPolygon([
                QPoint(left_cx - aw // 2, cy),
                QPoint(left_cx + aw // 2, cy - ah // 2),
                QPoint(left_cx + aw // 2, cy + ah // 2),
            ])
            # Right-pointing arrow
            p.drawPolygon([
                QPoint(right_cx + aw // 2, cy),
                QPoint(right_cx - aw // 2, cy - ah // 2),
                QPoint(right_cx - aw // 2, cy + ah // 2),
            ])
        finally:
            try:
                p.end()
            except Exception:
                pass

        if portrait:
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        p_main = QPainter(self)
        p_main.drawImage(0, 0, img)
        p_main.end()



class OverlayEffectsWidget(QWidget):
    """Transparent overlay that draws the animated glow border and floating particles
    over the main overlay window. Works for both portrait and landscape modes since it
    paints in physical screen coordinates."""

    _PARTICLE_COUNT = 12

    def __init__(self, parent: "OverlayWindow"):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Breathing glow state
        self._glow_t = 0.0

        # Floating particles
        self._particles: list = []

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(50)
        self._tick_timer.timeout.connect(self._on_tick)
        self.hide()

    def _init_particles(self):
        W = max(200, self.width() if self.width() > 0 else 400)
        H = max(200, self.height() if self.height() > 0 else 600)
        count = self._PARTICLE_COUNT
        self._particles = []
        for _ in range(count):
            self._particles.append(self._make_particle(W, H, spawn_anywhere=True))

    def _make_particle(self, W: int, H: int, spawn_anywhere: bool = False) -> dict:
        return {
            'x': random.uniform(0, W),
            'y': random.uniform(0, H) if spawn_anywhere else H + random.uniform(0, 20),
            'vx': random.uniform(-8, 8),
            'vy': random.uniform(-30, -10),
            'size': random.uniform(2, 4),
            'alpha': random.randint(30, 80),
        }

    def showEvent(self, event):
        super().showEvent(event)
        low_perf = False
        try:
            low_perf = bool(self.parent().parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
        except Exception:
            pass
        if low_perf:
            return
        if not self._particles:
            self._init_particles()
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._tick_timer.stop()

    def _on_tick(self):
        # Advance glow breath (increment ~0.008 per 50ms => ~6.25s period)
        self._glow_t = (self._glow_t + 0.008) % 1.0
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return
        dt = 0.05  # 50ms in seconds
        for pt in self._particles:
            pt['x'] += pt['vx'] * dt
            pt['y'] += pt['vy'] * dt
            # Respawn at bottom if out of bounds
            if pt['y'] < -10 or pt['x'] < -10 or pt['x'] > W + 10:
                pt.update(self._make_particle(W, H, spawn_anywhere=False))
        self.update()

    def paintEvent(self, event):
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return
        low_perf = False
        try:
            low_perf = bool(self.parent().parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
        except Exception:
            pass
        if low_perf:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            # Breathing glow border
            amp = 0.5 + 0.5 * math.sin(2 * math.pi * self._glow_t)
            alpha_base = int(120 + 135 * amp)  # 120..255
            layers = int(2 + 2 * amp)          # 2..4
            glow_color = QColor(0, 229, 255, alpha_base)
            _draw_glow_border(p, 0, 0, W, H, radius=18, color=glow_color, layers=layers)

            # Floating particles
            p.setPen(Qt.PenStyle.NoPen)
            for pt in self._particles:
                c = QColor(0, 229, 255, int(pt['alpha']))
                p.setBrush(c)
                sz = int(pt['size'])
                p.drawEllipse(int(pt['x']) - sz // 2, int(pt['y']) - sz // 2, sz, sz)
        finally:
            try:
                p.end()
            except Exception:
                pass


class OverlayWindow(QWidget):
    TITLE_OFFSET_X = 0
    TITLE_OFFSET_Y = 0
    CLAMP_TITLE = True
    ROTATION_DEBOUNCE_MS = 1

    def _resolve_background_url(self, bg: str) -> str | None:
        def is_img(p: str) -> bool:
            return p.lower().endswith((".png", ".jpg", ".jpeg"))
        if isinstance(bg, str) and bg and bg.lower() != "auto":
            if os.path.isfile(bg) and is_img(bg):
                return bg.replace("\\", "/")
        for fn in ("overlay_bg.png", "overlay_bg.jpg", "overlay_bg.jpeg"):
            p = os.path.join(APP_DIR, fn)
            if os.path.isfile(p):
                return p.replace("\\", "/")
        return None

    def _show_live_unrotated(self):
        try:
            self.rotated_label.hide()
        except Exception:
            pass
        try:
            self.container.show()
            self.text_container.show()
            if not getattr(self, '_fullsize_mode', False):
                self.title.show()
            self.body.show()
        except Exception:
            pass
        if self._nav_arrows_active:
            self._nav_arrows.raise_()

    def _icon_local(self, key: str) -> str:
        use_emojis = not bool(self.parent_gui.cfg.OVERLAY.get("prefer_ascii_icons", False))
        if use_emojis:
            emoji_map = {
                "best_ball": "🔥",
                "extra_ball": "➕",
            }
            return emoji_map.get(key, "•")
        else:
            ascii_map = {
                "best_ball": "[BB]",
                "extra_ball": "[EB]",
            }
            return ascii_map.get(key, "[*]")

    def showEvent(self, e):
        super().showEvent(e)
        _force_topmost(self)
        if not self._ensuring:
            QTimer.singleShot(0, self._layout_positions)
            if self.portrait_mode:
                QTimer.singleShot(0, lambda: self.request_rotation(force=True))
            else:
                QTimer.singleShot(0, self._show_live_unrotated)
        # Start effects overlay (glow border + floating particles)
        if hasattr(self, '_effects_widget'):
            low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
            if not low_perf:
                self._effects_widget.setGeometry(0, 0, self.width(), self.height())
                self._effects_widget.show()
                self._effects_widget.raise_()

    def hideEvent(self, e):
        super().hideEvent(e)
        if hasattr(self, '_effects_widget'):
            self._effects_widget.hide()
        if hasattr(self, '_score_spin_timer'):
            self._score_spin_timer.stop()
        if hasattr(self, '_progress_bar_timer'):
            self._progress_bar_timer.stop()
        if hasattr(self, '_transition_timer'):
            self._transition_timer.stop()


    def _alpha_bbox(self, img: QImage, min_alpha: int = 8) -> QRect:
        w, h = img.width(), img.height()
        if w == 0 or h == 0:
            return QRect(0, 0, 0, 0)
        top = None
        left = None
        right = -1
        bottom = -1
        for y in range(h):
            for x in range(w):
                if img.pixelColor(x, y).alpha() >= min_alpha:
                    if top is None:
                        top = y
                    bottom = y
                    if left is None or x < left:
                        left = x
                    if x > right:
                        right = x
        if top is None:
            return QRect(0, 0, 0, 0)
        return QRect(left, top, right - left + 1, bottom - top + 1)

    def _ref_screen_geometry(self) -> QRect:
        try:
            win = self.windowHandle()
            if win and win.screen():
                return win.screen().geometry()
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        screens = QApplication.screens() or []
        return screens[0].geometry() if screens else QRect(0, 0, 1280, 720)

    def _register_raw_input(self):
        try:
            hwnd = int(self.winId())
            register_raw_input_for_window(hwnd)
        except Exception:
            pass

    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Watchtower Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ov = self.parent_gui.cfg.OVERLAY
        self.scale_pct = int(ov.get("scale_pct", 100))
        self.portrait_mode = bool(ov.get("portrait_mode", True))
        self.rotate_ccw = bool(ov.get("portrait_rotate_ccw", True))
        self.position = "center"
        self.lines_per_category = int(ov.get("lines_per_category", 5))
        
        self.font_family = ov.get("font_family", "Segoe UI")
        self._base_title_size = int(ov.get("base_title_size", 17))
        self._base_body_size = int(ov.get("base_body_size", 12))
        self._base_hint_size = int(ov.get("base_hint_size", 10))
        self._body_pt = self._base_body_size
        self._current_combined = None
        self._current_html = None
        self._p2_rows = None
        self._current_title = None
        self._rotation_pending = False
        self._apply_geometry()
        self.bg_url = self._resolve_background_url(ov.get("background", "auto"))
        self.container = QWidget(self)
        self.container.setObjectName("overlay_bg")
        self.container.setGeometry(0, 0, self.width(), self.height())
        if self.bg_url:
            css = ("QWidget#overlay_bg {"
                   f"border-image: url('{self.bg_url}') 0 0 0 0 stretch stretch;"
                   "background:rgba(8,12,22,245);border:2px solid #00E5FF;border-radius:18px;}")
        else:
            css = ("QWidget#overlay_bg {background:rgba(8,12,22,245);"
                   "border:2px solid #00E5FF;border-radius:18px;}")
        self.container.setStyleSheet(css)
        self.text_container = QWidget(self)
        self.text_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.text_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.text_container.setGeometry(0, 0, self.width(), self.height())
        self.title = QLabel("Highlights", self.text_container)
        self.body = QLabel(self.text_container)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setWordWrap(True)
        for lab in (self.title, self.body):
            lab.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            lab.setAutoFillBackground(False)
            
        self.title.setStyleSheet("color:#FFFFFF;background:transparent;")
        self.body.setStyleSheet("color:#FFFFFF;background:transparent;")
        
        self._apply_scale(self.scale_pct)
        self.rotated_label = QLabel(self)
        self.rotated_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rotated_label.setStyleSheet("background:transparent;")
        self.rotated_label.hide()
        self._rot_in_progress = False
        self._rot_deferred = False
        self._ensuring = False
        self._font_update_in_progress = False
        self._nav_arrows = OverlayNavArrows(self)
        self._nav_arrows_active = False
        self._layout_positions()
        QTimer.singleShot(0, self._register_raw_input)
        _start_topmost_timer(self)
        # Page-2 (Achievement Progress) Python-level scroll support
        self._p2_timer = QTimer(self)
        self._p2_timer.setInterval(1500)
        self._p2_timer.timeout.connect(self._p2_tick)
        self._p2_rows: list = []
        self._p2_offset: int = 0
        self._p2_visible: int = 10
        self._p2_header: str = ""
        self._p2_css: str = ""
        # Score counter spin state
        self._score_display: int = 0
        self._score_target: int = 0
        self._score_spin_timer = QTimer(self)
        self._score_spin_timer.setInterval(50)
        self._score_spin_timer.timeout.connect(self._score_spin_tick)
        # Animated progress bar state
        self._progress_pct_current: float = 0.0
        self._progress_pct_target: float = 0.0
        self._progress_bar_timer = QTimer(self)
        self._progress_bar_timer.setInterval(50)
        self._progress_bar_timer.timeout.connect(self._progress_bar_tick)
        # Slide/glitch transition state
        self._transition_state: dict | None = None
        self._transition_label: QLabel | None = None
        self._transition_timer = QTimer(self)
        self._transition_timer.setInterval(16)
        self._transition_timer.timeout.connect(self._transition_tick)
        # Effects widget (glow border + floating particles)
        self._effects_widget = OverlayEffectsWidget(self)

    def request_rotation(self, force: bool = False):
        if not self.portrait_mode:
            return
        if self._rotation_pending and not force:
            return
        self._rotation_pending = True
        def _do():
            try:
                self._apply_rotation_snapshot(force=True)
            finally:
                self._rotation_pending = False
        QTimer.singleShot(self.ROTATION_DEBOUNCE_MS if not force else 0, _do)

    def set_nav_arrows(self, active: bool):
        """Show or hide the pulsating page-navigation arrows on the overlay."""
        self._nav_arrows_active = bool(active)
        if active:
            self._nav_arrows.setGeometry(0, 0, self.width(), self.height())
            self._nav_arrows.show()
            self._nav_arrows.raise_()
        else:
            self._nav_arrows.hide()

    def _apply_geometry(self):
        ref = self._ref_screen_geometry()
        if self.portrait_mode:
            base_h = int(ref.height() * 0.55)
            base_w = int(base_h * 9 / 16)
        else:
            base_w = int(ref.width() * 0.40)
            base_h = int(ref.height() * 0.30)
        w = max(120, int(base_w * self.scale_pct / 100))
        h = max(120, int(base_h * self.scale_pct / 100))
        screens = QApplication.screens() or []
        if screens:
            vgeo = screens[0].geometry()
            for s in screens[1:]:
                vgeo = vgeo.united(s.geometry())
        else:
            vgeo = QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY
        if ov.get("use_xy", False):
            x = int(ov.get("pos_x", 0))
            y = int(ov.get("pos_y", 0))
        else:
            pad = 20
            pos = (getattr(self, "position", "center") or "center").lower()
            mapping = {
                "top-left": (vgeo.left() + pad, vgeo.top() + pad),
                "top-right": (vgeo.right() - w - pad, vgeo.top() + pad),
                "bottom-left": (vgeo.left() + pad, vgeo.bottom() - h - pad),
                "bottom-right": (vgeo.right() - w - pad, vgeo.bottom() - h - pad),
                "center-top": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.top() + pad),
                "center-bottom": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.bottom() - h - pad),
                "center-left": (vgeo.left() + pad, vgeo.top() + (vgeo.height() - h) // 2),
                "center-right": (vgeo.right() - w - pad, vgeo.top() + (vgeo.height() - h) // 2),
                "center": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.top() + (vgeo.height() - h) // 2)
            }
            x, y = mapping.get(pos, mapping["center"])
        self.setGeometry(x, y, w, h)
        if hasattr(self, "container"):
            self.container.setGeometry(0, 0, w, h)
        if hasattr(self, "text_container"):
            self.text_container.setGeometry(0, 0, w, h)

    def _layout_positions(self):
        self._layout_positions_for(self.width(), self.height())
        if self.portrait_mode:
            self.request_rotation()

    def _layout_positions_for(self, w: int, h: int, portrait_pre_render: bool = False):
        if hasattr(self, "text_container"):
            self.text_container.setGeometry(0, 0, w, h)
        if getattr(self, '_fullsize_mode', False):
            self.title.hide()
            self.body.setGeometry(0, 0, w, h)
            return
        pad = 24
        try:
            self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.title.setIndent(0)
            self.title.setMargin(0)
            self.title.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.title.adjustSize()
        t_h = self.title.sizeHint().height()
        if not self.portrait_mode:
            self.title.setGeometry(0, pad, w, t_h)
            body_top = self.title.y() + t_h + 10
            body_h = h - body_top - pad
            body_w = int(w * 0.9)
            body_x = (w - body_w) // 2
            try:
                self.body.setContentsMargins(0, 0, 0, 0)
            except Exception:
                pass
            self.body.setGeometry(body_x, body_top, body_w, max(80, body_h))
            return
        self.title.setGeometry(0, pad, w, t_h)
        body_w = int(w * 0.92)
        body_x = (w - body_w) // 2
        body_top = pad + t_h + 10
        body_h = h - body_top - pad
        try:
            self.body.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.body.setGeometry(body_x, body_top, body_w, max(80, body_h))

    def _apply_scale(self, scale_pct: int):
        r = scale_pct / 100.0
        body_pt = max(4, int(round(self._base_body_size * r)))
        title_pt = max(6, int(round(body_pt * 1.35)))
        
        self._body_pt = body_pt
        self.title.setFont(QFont(self.font_family, title_pt, QFont.Weight.Bold))
        self.body.setFont(QFont(self.font_family, body_pt))
        self.body.setStyleSheet(f"color:#FFFFFF;background:transparent;font-size:{body_pt}pt;font-family:'{self.font_family}';")

    def _composition_mode_source_over(self):
        try:
            return QPainter.CompositionMode.CompositionMode_SourceOver
        except Exception:
            try:
                return getattr(QPainter, "CompositionMode_SourceOver")
            except Exception:
                return None

    def _apply_rotation_snapshot(self, force: bool = False):
        if not self.portrait_mode:
            self.rotated_label.hide()
            self.container.show()
            self.text_container.show()
            if not getattr(self, '_fullsize_mode', False):
                self.title.show()
            self.body.show()
            return
        if getattr(self, "_rot_in_progress", False):
            # Queue a deferred re-render so the final state is always correct
            if not getattr(self, "_rot_deferred", False):
                self._rot_deferred = True
                QTimer.singleShot(50, self._deferred_rotation)
            return
        self._rot_in_progress = True
        try:
            W, H = self.width(), self.height()
            if W <= 0 or H <= 0:
                return
            angle = -90 if getattr(self, "rotate_ccw", True) else 90
            if self.bg_url and os.path.isfile(self.bg_url):
                pm = QPixmap(self.bg_url)
                if not pm.isNull():
                    rot_pm = pm.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
                    scaled = rot_pm.scaled(W, H, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                           Qt.TransformationMode.SmoothTransformation)
                    sw, sh = scaled.width(), scaled.height()
                    cx = max(0, (sw - W) // 2)
                    cy = max(0, (sh - H) // 2)
                    bg_img = scaled.copy(cx, cy, min(W, sw - cx), min(H, sh - cy)).toImage().convertToFormat(
                        QImage.Format.Format_ARGB32_Premultiplied)
                else:
                    bg_img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied); bg_img.fill(QColor(8, 12, 22, 245))
            else:
                bg_img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied); bg_img.fill(QColor(8, 12, 22, 245))
            pre_w, pre_h = H, W
            old_geom = self.text_container.geometry()
            old_title_vis = self.title.isVisible()
            old_body_vis = self.body.isVisible()
            self.text_container.setGeometry(0, 0, pre_w, pre_h)
            self.title.setVisible(not getattr(self, '_fullsize_mode', False))
            self.body.setVisible(True)
            self._layout_positions_for(pre_w, pre_h, portrait_pre_render=False)
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 5)
            content_pre = QImage(pre_w, pre_h, QImage.Format.Format_ARGB32_Premultiplied)
            content_pre.fill(Qt.GlobalColor.transparent)
            p_all = QPainter(content_pre)
            try:
                self.text_container.render(p_all)
            finally:
                p_all.end()
            content_rot = content_pre.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            self.container.hide()
            self.text_container.hide()
            final_img = QImage(bg_img)
            p_final = QPainter(final_img)
            try:
                mode = self._composition_mode_source_over()
                if mode is not None:
                    p_final.setCompositionMode(mode)
                dx = (W - content_rot.width()) // 2
                dy = (H - content_rot.height()) // 2
                p_final.drawImage(dx, dy, content_rot)

                _draw_glow_border(p_final, 0, 0, W, H, radius=18,
                                   low_perf=bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False)))
            finally:
                p_final.end()
            self.text_container.setGeometry(old_geom)
            self.title.setVisible(old_title_vis)
            self.body.setVisible(old_body_vis)

            self.rotated_label.setGeometry(0, 0, W, H)
            self.rotated_label.setPixmap(QPixmap.fromImage(final_img))
            self.rotated_label.show()
            self.rotated_label.raise_()
            if self._nav_arrows_active:
                self._nav_arrows.setGeometry(0, 0, W, H)
                self._nav_arrows.show()
                self._nav_arrows.raise_()
            # Keep effects widget (glow + particles) on top
            if hasattr(self, '_effects_widget') and self._effects_widget.isVisible():
                low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
                if not low_perf:
                    self._effects_widget.setGeometry(0, 0, W, H)
                    self._effects_widget.raise_()
        except Exception as e:
            print("[overlay] portrait render failed:", e)
            self.rotated_label.hide()
            self.container.show()
            self.text_container.show()
        finally:
            self._rot_in_progress = False

    def _deferred_rotation(self):
        self._rot_deferred = False
        if self.portrait_mode and self.isVisible():
            self._apply_rotation_snapshot(force=True)

    def _refresh_current_content(self):
        """Re-render the currently displayed page using the current font settings.
        Handles all page types: fixed-columns (page 0), scrollable rows (page 1),
        plain HTML pages (pages 2/3), and fullsize pages (page 5 VPC leaderboard)."""
        if self._current_combined:
            self._render_fixed_columns()
        elif self._current_html is not None:
            if getattr(self, '_fullsize_mode', False):
                # In fullsize mode (e.g. VPC page 5), never call set_html() as that
                # resets _fullsize_mode. Prefer delegating to parent's _refresh_vpc_page5()
                # so image pixel dimensions are recalculated for the current overlay size.
                parent = getattr(self, 'parent_gui', None)
                if parent is not None and getattr(parent, '_vpc_page5_data', None):
                    parent._refresh_vpc_page5()
                else:
                    self.set_html_fullsize(self._current_html, self._current_title)
            else:
                self.set_html(self._current_html, self._current_title)
        elif self._p2_rows is not None:
            self._render_p2()
            self._layout_positions()
            self.request_rotation(force=True)
        else:
            self._layout_positions()
            self.request_rotation(force=True)

    def apply_font_from_cfg(self, ov: dict):
        if getattr(self, "_font_update_in_progress", False):
            return
        self._font_update_in_progress = True
        try:
            self.font_family = ov.get("font_family", self.font_family)
            self._base_body_size = int(ov.get("base_body_size", self._base_body_size))
            self._base_title_size = int(ov.get("base_title_size", self._base_title_size))
            self._base_hint_size = int(ov.get("base_hint_size", self._base_hint_size))
            self._apply_scale(self.scale_pct)
            def _finish():
                try:
                    self._refresh_current_content()
                finally:
                    self._font_update_in_progress = False
            QTimer.singleShot(0, _finish)
        except Exception:
            self._font_update_in_progress = False

    def apply_portrait_from_cfg(self, ov: dict):
        self.portrait_mode = bool(ov.get("portrait_mode", self.portrait_mode))
        self.rotate_ccw = bool(ov.get("portrait_rotate_ccw", self.rotate_ccw))
        self._apply_geometry()
        self._layout_positions()
        if self.portrait_mode:
            self.request_rotation(force=True)
        else:
            self._show_live_unrotated()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.container.setGeometry(0, 0, self.width(), self.height())
        self._layout_positions()
        if self.portrait_mode:
            self.request_rotation()
        else:
            self._show_live_unrotated()
        if self._nav_arrows_active:
            self._nav_arrows.setGeometry(0, 0, self.width(), self.height())
            self._nav_arrows.raise_()
        if hasattr(self, '_effects_widget') and self._effects_widget.isVisible():
            low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
            if not low_perf:
                self._effects_widget.setGeometry(0, 0, self.width(), self.height())
                self._effects_widget.raise_()

    def set_placeholder(self, session_title: Optional[str] = None):
        self._fullsize_mode = False
        self._current_combined = None
        self._current_html = None
        self._p2_rows = None
        self._current_title = session_title or "Highlights"
        self.title.setText(self._current_title)
        self.body.setText("<div>Loading highlights …</div>")
        self._layout_positions()
        self.request_rotation(force=True)

    def set_html(self, html: str, session_title: Optional[str] = None):
        self._fullsize_mode = False
        if hasattr(self, "_p2_timer"):
            self._p2_timer.stop()
        self._current_combined = None
        self._current_html = html
        self._p2_rows = None
        self._current_title = "Highlights" if session_title is None else session_title
        self.title.setText(self._current_title)
        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self._layout_positions()
        self.request_rotation(force=True)

    def set_html_fullsize(self, html: str, session_title: Optional[str] = None):
        """Like set_html() but expands body to the full window — no title bar, no insets.

        Use this for pages that display a full-window image (e.g. Page 5 VPC leaderboard).
        Switching to any other page via set_html/set_combined/etc. automatically restores
        the normal title + body layout.
        """
        if hasattr(self, "_p2_timer"):
            self._p2_timer.stop()
        self._fullsize_mode = True
        self._current_combined = None
        self._current_html = html
        self._p2_rows = None
        self._current_title = "Highlights" if session_title is None else session_title
        self.title.hide()
        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self.body.setGeometry(0, 0, self.width(), self.height())
        self.request_rotation(force=True)

    def set_combined(self, combined: dict, session_title: Optional[str] = None):
        self._fullsize_mode = False
        if hasattr(self, "_p2_timer"):
            self._p2_timer.stop()
        self._current_combined = combined or {}
        self._current_html = None
        self._p2_rows = None
        self._current_title = "Highlights" if session_title is None else session_title
        self._render_fixed_columns()

    def set_html_scrollable(self, css: str, header_html: str, rows: list,
                            session_title: Optional[str] = None):
        """Display a list of table rows with Python QTimer-based scrolling."""
        self._fullsize_mode = False
        if hasattr(self, "_p2_timer"):
            self._p2_timer.stop()
        self._current_combined = None
        self._current_html = None
        self._current_title = session_title or "Achievement Progress"
        self.title.setText(self._current_title)
        self._p2_rows = list(rows)
        self._p2_offset = 0
        self._p2_header = header_html
        self._p2_css = css
        # Estimate how many rows fit in the body area.
        # In portrait mode the widget is taller than wide (e.g. 334×594 on 1080p),
        # but the content is rendered in the rotated orientation: the widget's
        # *width* (the short side) maps to the available content height.
        body_pt = getattr(self, "_body_pt", 20)
        row_h_px = max(16, int(body_pt * 1.8))
        if getattr(self, "portrait_mode", False):
            content_dim = self.width()
        else:
            content_dim = self.height()
        avail_h = max(80, content_dim - 80)
        # Subtract 2 row-heights to account for the header section
        # (ROM title div + progress bar div) that occupies the top of the body.
        self._p2_visible = max(3, avail_h // row_h_px - 2)
        self._render_p2()
        self._layout_positions()
        self.request_rotation(force=True)
        if len(self._p2_rows) > self._p2_visible:
            self._p2_timer.start()

    def _render_p2(self):
        """Render the current scroll window of achievement rows into the body label."""
        rows = self._p2_rows
        offset = self._p2_offset
        visible = getattr(self, "_p2_visible", 10)
        chunk = rows[offset:offset + visible]
        body_pt = getattr(self, "_body_pt", 20)
        css_base = (f"font-size:{body_pt}pt;"
                    f"font-family:'{self.font_family}';color:#FFFFFF;")
        table_html = ("<table width='100%' style='border-collapse:collapse;'>"
                      + "".join(chunk) + "</table>")
        full = getattr(self, "_p2_css", "") + getattr(self, "_p2_header", "") + table_html
        self.body.setText(f"<div style='{css_base}'>{full}</div>")

    def _p2_tick(self):
        """Advance scroll by one row and re-render; pause at end then loop."""
        total = len(self._p2_rows)
        visible = getattr(self, "_p2_visible", 10)
        if total <= visible:
            if hasattr(self, "_p2_timer"):
                self._p2_timer.stop()
            return
        max_offset = total - visible
        self._p2_offset += 1
        if self._p2_offset > max_offset:
            # Pause at end for 3 seconds before looping back to the top
            self._p2_timer.stop()
            self._p2_offset = 0
            self._render_p2()
            self.request_rotation(force=True)
            QTimer.singleShot(3000, lambda: self._p2_timer.start()
                              if self._p2_rows else None)
            return
        self._render_p2()
        self.request_rotation(force=True)

    def _render_fixed_columns(self):
        self.title.setText(self._current_title or "Highlights")
        players = list((self._current_combined or {}).get("players") or [])
        rom_name = str((self._current_combined or {}).get("rom_name") or getattr(self.parent_gui.watcher, "current_rom", None) or "Unknown ROM")
        limit = self.lines_per_category

        def esc(x) -> str:
            return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        table_title = ""
        try:
            romnames = getattr(self.parent_gui.watcher, "ROMNAMES", {}) or {}
            table_title = romnames.get(rom_name, "")
        except Exception:
            pass

        total_achs = 0
        unlocked_total = 0
        pct = 0.0
        try:
            if rom_name and rom_name != "Unknown ROM" and self.parent_gui.watcher._has_any_map(rom_name):
                g_rules = self.parent_gui.watcher._collect_global_rules_for_rom(rom_name)
                s_rules = self.parent_gui.watcher._collect_player_rules_for_rom(rom_name)
                total_achs = len(g_rules) + len(s_rules)

                if total_achs > 0:
                    state = self.parent_gui.watcher._ach_state_load()
                    unlocked_g = len(state.get("global", {}).get(rom_name, []))
                    unlocked_s = len(state.get("session", {}).get(rom_name, []))
                    unlocked_total = unlocked_g + unlocked_s
                    pct = round((unlocked_total / total_achs) * 100, 1)
        except Exception:
            pass

        # Animated progress bar: update target and start timer if changed
        new_pct_target = pct if total_achs > 0 else 0.0
        if abs(new_pct_target - getattr(self, '_progress_pct_target', -1)) > 0.05:
            self._progress_pct_target = new_pct_target
            low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
            if low_perf:
                self._progress_pct_current = self._progress_pct_target
            else:
                if not hasattr(self, '_progress_bar_timer_started') or not getattr(self, '_progress_bar_timer_started', False):
                    # Fresh start: jump to 0 for a fill animation
                    self._progress_pct_current = 0.0
                if hasattr(self, '_progress_bar_timer'):
                    self._progress_bar_timer.start()

        style = """
        <style>
          table.hltable { border-collapse: collapse; margin: 0 auto; width: 100%; font-size: 1.1em; }
          .hltable th, .hltable td { padding: 0.35em 0.65em; border-bottom: 1px solid rgba(255,255,255,0.15); color: #E0E0E0; overflow-wrap: break-word; }
          .hltable th { text-align: center; background: rgba(0, 229, 255, 0.20); color: #00E5FF; font-weight: bold; font-size: 1.1em; border-bottom: 2px solid rgba(0, 229, 255, 0.35); }
          .hltable td.left { text-align: left; }
          .hltable td.right { text-align: right; font-weight: bold; font-size: 1.15em; color: #FF7F00; }
          .rom-title { text-align: center; font-size: 1.6em; font-weight: bold; color: #FF7F00; text-transform: uppercase; letter-spacing: 3px; margin-bottom: 0.2em; margin-top: 0.4em; border-bottom: 1px solid rgba(0, 229, 255, 0.3); padding-bottom: 0.3em; }
          .score-box { text-align: center; font-size: 2.2em; font-weight: bold; margin-bottom: 1.0em; color: #00E5FF; }
          .divider { border-top: 1px solid rgba(255, 127, 0, 0.3); margin-top: 0.6em; padding-top: 0.6em; }
        </style>
        """

        def block(entry: dict):
            hld = (entry.get("highlights") or {})
            deltas = (entry.get("deltas") or {})

            try:
                score_abs = int(entry.get("score", 0) or 0)
            except Exception:
                score_abs = 0

            # Score counter spin: update target and start spin if changed
            if score_abs != getattr(self, '_score_target', -1):
                self._score_target = score_abs
                if getattr(self, '_score_display', 0) == 0:
                    self._score_display = 0
                low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
                if low_perf:
                    self._score_display = self._score_target
                elif hasattr(self, '_score_spin_timer'):
                    self._score_spin_timer.start()

            lines = []

            display_title = table_title or rom_name or "Unknown ROM"
            lines.append(f"<div class='rom-title'>{esc(display_title)}</div>")

            if total_achs > 0:
                # Use animated progress percentage
                anim_pct = getattr(self, '_progress_pct_current', pct)
                safe_pct = max(0.1, min(100.0, anim_pct))
                rem_pct = 100.0 - safe_pct

                bar_html = f"""
                <div style='text-align: center; color: #FFFFFF; font-weight: bold; font-size: 1.15em; margin-bottom: 0.3em;'>
                    {unlocked_total} / {total_achs} ({pct}%)
                </div>
                <table align='center' width='75%' style='border: 1px solid rgba(0, 229, 255, 0.25); background: #0D1117; margin-bottom: 1.5em; border-radius: 6px; overflow: hidden;' cellpadding='0' cellspacing='0'>
                    <tr>
                        <td width='{safe_pct}%' style='background: #FF9020; height: 12px; border-radius: 4px;'>&nbsp;</td>
                        <td width='{rem_pct}%' style='height: 12px;'>&nbsp;</td>
                    </tr>
                </table>
                """
                lines.append(bar_html)
            else:
                lines.append("<div style='margin-bottom: 1.2em;'></div>")

            if score_abs > 0:
                # Use animated score display value
                anim_score = getattr(self, '_score_display', score_abs)
                sc_txt = f"{anim_score:,d}".replace(",", ".")
                lines.append(f"<div class='score-box'>Score: {sc_txt}</div>")
            else:
                lines.append("<div style='margin-bottom: 1.8em;'></div>")

            lines.append("<table align='center' style='border-collapse: collapse; margin: 0 auto; width: 100%;'><tr>")

            lines.append("<td valign='top' style='padding-right: 20px; border-right: 1px solid rgba(255, 255, 255, 0.4);'>")
            lines.append("<table class='hltable'>")
            has_high = False
            for cat in ["Power", "Precision", "Fun"]:
                arr = hld.get(cat, [])
                if arr:
                    has_high = True
                    lines.append(f"<tr><th colspan='2'>{esc(cat)}</th></tr>")
                    for x in arr[:max(1, limit)]:
                        parts = x.rsplit(" – ", 1)
                        if len(parts) == 2:
                            name, val = parts[0], parts[1]
                        else:
                            name, val = x, ""
                        lines.append(f"<tr><td class='left'>{esc(name)}</td><td class='right'>{esc(val)}</td></tr>")
            lines.append("</table>")
            if not has_high:
                lines.append("<div style='text-align:center; color:#888; margin-top:1em;'>(No Highlights yet)</div>")
            lines.append("</td>")

            lines.append("<td valign='top' style='padding-left: 20px; border:none;'>")
            lines.append("<table class='hltable'>")

            if not deltas:
                lines.append("<tr><td colspan='2' style='text-align:center; color:#888; border:none;'>(No actions yet)</td></tr>")
            else:
                items = sorted(list(deltas.items()), key=lambda x: int(x[1]), reverse=True)

                max_rows = 20
                cols = 2

                max_items = max_rows * cols
                display_items = items[:max_items]

                header_html = ""
                for c in range(cols):
                    border = " style='border-left: 2px solid rgba(255,255,255,0.2); padding-left: 0.55em;'" if c > 0 else ""
                    header_html += f"<th{border}>Action</th><th>Count</th>"
                lines.append(f"<tr>{header_html}</tr>")

                for i in range(0, len(display_items), cols):
                    row_html = ""
                    for c in range(cols):
                        idx = i + c
                        border = " style='border-left: 2px solid rgba(255,255,255,0.2); padding-left: 0.55em;'" if c > 0 else ""
                        if idx < len(display_items):
                            k, v = display_items[idx]
                            v_str = f"+{v:,}".replace(",", ".")
                            row_html += f"<td class='left'{border}>{esc(k)}</td><td class='right'>{esc(v_str)}</td>"
                        else:
                            row_html += f"<td class='left'{border}></td><td class='right'></td>"

                    lines.append(f"<tr>{row_html}</tr>")

                if len(items) > max_items:
                    lines.append(f"<tr><td colspan='{cols * 2}' style='text-align:center; color:#888; font-size:0.9em;'>(+ {len(items)-max_items} more actions)</td></tr>")

            lines.append("</table>")
            lines.append("</td>")

            lines.append("</tr></table>")
            return "".join(lines)

        if not players:
            self.body.setText("<div>-</div>")
            self._layout_positions()
            self.request_rotation(force=True)
            return

        html = style + "<div align='center' style='width:100%;'>" + \
               "".join(f"{block(p)}" for p in players) + \
               "</div>"

        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self._layout_positions()
        self.request_rotation(force=True)
        
    def _score_spin_tick(self):
        """Animate score display value toward _score_target (slot-machine style)."""
        if self._score_display == self._score_target:
            self._score_spin_timer.stop()
            return
        diff = abs(self._score_target - self._score_display)
        # Cap animation to ~15 ticks (~750ms at 50ms interval) regardless of score magnitude.
        # Also enforce a minimum step of 1% of the target so huge values don't stall at the end.
        MAX_TICKS = 15
        step = max(1, diff // MAX_TICKS, abs(self._score_target) // 100)
        if self._score_display < self._score_target:
            self._score_display = min(self._score_target, self._score_display + step)
        else:
            self._score_display = max(self._score_target, self._score_display - step)
        self._render_fixed_columns()

    def _progress_bar_tick(self):
        """Animate progress bar fill toward _progress_pct_target (ease-out)."""
        target = getattr(self, '_progress_pct_target', 0.0)
        current = getattr(self, '_progress_pct_current', 0.0)
        if abs(current - target) < 0.5:
            self._progress_pct_current = target
            self._progress_bar_timer.stop()
            self._render_fixed_columns()
            return
        step = max(0.5, abs(target - current) * 0.12)
        if current < target:
            self._progress_pct_current = min(target, current + step)
        else:
            self._progress_pct_current = max(target, current - step)
        self._render_fixed_columns()

    def _snapshot_current(self):
        """Capture the current overlay content as a QImage for transition effects."""
        try:
            W, H = self.width(), self.height()
            if W <= 0 or H <= 0:
                return None
            if getattr(self, 'portrait_mode', False):
                pm = self.rotated_label.pixmap()
                if pm and not pm.isNull():
                    img = pm.toImage()
                    if img.width() == W and img.height() == H:
                        return img
            pm = self.grab()
            return pm.toImage()
        except Exception:
            return None

    def _draw_glitch_frame(self, source_img, label):
        """Draw a single glitch frame on the given label by slicing source_img into strips."""
        W = source_img.width()
        H = source_img.height()
        glitched = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        glitched.fill(Qt.GlobalColor.transparent)
        p = QPainter(glitched)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        try:
            n_strips = random.randint(4, 6)
            strip_h = max(1, H // n_strips)
            for i in range(n_strips):
                y0 = i * strip_h
                y1 = min(H, y0 + strip_h)
                sh = y1 - y0
                if sh <= 0:
                    continue
                offset_x = random.randint(-15, 15)
                strip = source_img.copy(0, y0, W, sh)
                p.drawImage(offset_x, y0, strip)
        finally:
            try:
                p.end()
            except Exception:
                pass
        label.setPixmap(QPixmap.fromImage(glitched))

    def transition_to(self, new_content_callback, direction: str = 'left'):
        """Perform a slide+fade page transition (with a brief glitch pre-effect).

        Call this instead of set_html/set_combined when changing pages.  The method
        captures the current display, runs the callback to update content, then animates
        between old and new snapshots.
        """
        low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
        if low_perf:
            new_content_callback()
            return

        old_img = self._snapshot_current()
        if old_img is None or old_img.isNull():
            new_content_callback()
            return

        # Ensure transition label exists
        if self._transition_label is None:
            self._transition_label = QLabel(self)
            self._transition_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._transition_label.setStyleSheet("background:transparent;")
        W, H = self.width(), self.height()
        self._transition_label.setGeometry(0, 0, W, H)
        self._transition_label.show()
        self._transition_label.raise_()

        # Initialise state in glitch phase
        self._transition_state = {
            'phase': 'glitch',
            'direction': direction,
            'old_img': old_img,
            'new_img': None,
            'elapsed': 0.0,
            'glitch_elapsed': 0.0,
        }

        # Draw first glitch frame immediately
        self._draw_glitch_frame(old_img, self._transition_label)

        # After 120 ms of glitch frames, apply callback and switch to slide
        def _switch_to_slide():
            new_content_callback()
            QApplication.processEvents()
            new_img = self._snapshot_current()
            if self._transition_state:
                self._transition_state['new_img'] = new_img
                self._transition_state['phase'] = 'slide'
                self._transition_state['elapsed'] = 0.0

        QTimer.singleShot(120, _switch_to_slide)
        self._transition_timer.start()

    def _transition_tick(self):
        """Animate the current slide/glitch transition frame."""
        state = self._transition_state
        if state is None:
            self._transition_timer.stop()
            if self._transition_label:
                self._transition_label.hide()
            return

        dt = 16.0
        if state['phase'] == 'glitch':
            state['glitch_elapsed'] += dt
            old_img = state['old_img']
            if old_img and self._transition_label:
                self._draw_glitch_frame(old_img, self._transition_label)
            return

        # Slide + fade phase
        state['elapsed'] += dt
        duration = 300.0
        t = min(1.0, state['elapsed'] / duration)
        eased = _ease_out_cubic(t)

        W, H = self.width(), self.height()
        composite = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        composite.fill(Qt.GlobalColor.transparent)
        p = QPainter(composite)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        direction = state['direction']
        try:
            old_img = state.get('old_img')
            new_img = state.get('new_img')
            if old_img and not old_img.isNull():
                dx_old = -int(W * eased) if direction == 'left' else int(W * eased)
                p.setOpacity(max(0.0, 1.0 - eased))
                p.drawImage(dx_old, 0, old_img)
            if new_img and not new_img.isNull():
                dx_new = int(W * (1.0 - eased)) if direction == 'left' else -int(W * (1.0 - eased))
                p.setOpacity(min(1.0, eased))
                p.drawImage(dx_new, 0, new_img)
        finally:
            try:
                p.end()
            except Exception:
                pass

        if self._transition_label:
            self._transition_label.setPixmap(QPixmap.fromImage(composite))

        if t >= 1.0:
            self._transition_timer.stop()
            if self._transition_label:
                self._transition_label.hide()
            self._transition_state = None


class MiniInfoOverlay(QWidget):
    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Info")
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
        self._body_pt = 20
        self._font_family = ov.get("font_family", "Segoe UI")
        self._red = "#FF3B30"                          
        self._hint = "#DDDDDD"                         
        self._bg_color = QColor(8, 12, 22, 245)
        self._radius = 16
        self._pad_w = 28
        self._pad_h = 22
        self._max_text_width = 520
        self._portrait_mode = bool(ov.get("portrait_mode", True))
        self._rotate_ccw = bool(ov.get("portrait_rotate_ccw", True))
        self._remaining = 0
        self._base_msg = ""
        self._last_center = (960, 540)
        self._snap_label = QLabel(self)
        self._snap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snap_label.setStyleSheet("background:transparent;")
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
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
        pt = getattr(self, "_body_pt", 20)
        fam = str(getattr(self, "_font_family", "Segoe UI")).replace("'", "").replace('"', "").replace(";", "").replace("<", "").replace(">", "")
        return (
            f"<div style='font-size:{pt}pt;font-family:\"{fam}\";'>"
            f"<span style='color:{self._red};'>{self._base_msg}</span>"
            f"<br><span style='color:{self._hint};'>closing in {self._remaining}…</span>"
            f"</div>"
        )

    def _render_message_image(self, html: str) -> QImage:
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet(f"color:{self._red};background:transparent;")
        tmp.setFont(QFont(self._font_family, self._body_pt))
        tmp.setWordWrap(True)
        tmp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tmp.setText(html)
        tmp.setFixedWidth(self._max_text_width)
        tmp.adjustSize()
        text_w = tmp.width()
        text_h = tmp.sizeHint().height()
        W = max(200, text_w + self._pad_w)
        H = max(60,  text_h + self._pad_h)
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._bg_color)
            p.drawRoundedRect(0, 0, W, H, self._radius, self._radius)
            margin_left = (W - text_w) // 2
            margin_top = (H - text_h) // 2
            tmp.render(p, QPoint(margin_left, margin_top))
        finally:
            p.end()
        return img

    def _refresh_view(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._portrait_mode = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
        self._rotate_ccw = bool(ov.get("notifications_rotate_ccw", ov.get("portrait_rotate_ccw", True)))

        html = self._compose_html()
        img = self._render_message_image(html)

        if self._portrait_mode:
            angle = -90 if self._rotate_ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        W, H = img.width(), img.height()
        
        use_saved = bool(ov.get("notifications_saved", False))
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        
        if use_saved:
            if self._portrait_mode:
                x = int(ov.get("notifications_x_portrait", 100))
                y = int(ov.get("notifications_y_portrait", 100))
            else:
                x = int(ov.get("notifications_x_landscape", 100))
                y = int(ov.get("notifications_y_landscape", 100))
        else:
            cx, cy = self._last_center
            x = int(cx - W // 2)
            y = int(cy - H // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(), min(y, geo.bottom() - H))

        self.setGeometry(x, y, W, H)
        self._snap_label.setGeometry(0, 0, W, H)
        self._snap_label.setPixmap(QPixmap.fromImage(img))
        self.show()
        self.raise_()
        _force_topmost(self)

    def _on_tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self.hide()
            return
        self._refresh_view()

    def update_font(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._body_pt = 20
        self._font_family = str(ov.get("font_family", "Segoe UI"))
        if self.isVisible():
            self._refresh_view()

    def show_info(self, message: str, seconds: int = 5, center: tuple[int, int] | None = None, color_hex: str | None = None):
        self._base_msg = str(message or "").strip()
        self._remaining = max(1, int(seconds))
        if color_hex:
            try:
                self._red = color_hex
            except Exception:
                pass
        self._last_center = self._primary_center()
        self._timer.stop()
        self._refresh_view()
        self._timer.start()

def read_active_players(base_dir: str):
    ap_dir = os.path.join(base_dir, "session_stats", "Highlights", "activePlayers")
    if not os.path.isdir(ap_dir):
        return []

    # Nur P1 laden
    p1_files = []
    try:
        for fn in os.listdir(ap_dir):
            if re.search(r"_P1\.json$", fn, re.IGNORECASE):
                p1_files.append(os.path.join(ap_dir, fn))
    except Exception:
        return []

    if not p1_files:
        return []

    p1_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    fp = p1_files[0]

    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [{
            "id": 1,
            "highlights": data.get("highlights", {}),
            "playtime_sec": int(data.get("playtime_sec", 0) or 0),
            "score": int(data.get("score", 0) or 0),
            "title": data.get("title", "Player 1"),
            "player": 1,
            "rom": data.get("rom", ""),
        }]
    except Exception:
        return []



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

        self._base_w = max(220, int(width_hint))
        self._base_h = max(90, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()

        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h

        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("flip_counter_x_portrait", 100))
            y0 = int(ov.get("flip_counter_y_portrait", 100))
        else:
            x0 = int(ov.get("flip_counter_x_landscape", 100))
            y0 = int(ov.get("flip_counter_y_landscape", 100))

        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

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
        msg = "Drag to position.\nClick the button again to save"
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

class TimerPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 400, height_hint: int = 120):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Challenge Timer")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._base_w = max(200, int(width_hint))
        self._base_h = max(80, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("ch_timer_x_portrait", 100))
            y0 = int(ov.get("ch_timer_y_portrait", 100))
        else:
            x0 = int(ov.get("ch_timer_x_landscape", 100))
            y0 = int(ov.get("ch_timer_y_landscape", 100))
        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ch_timer_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
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
        msg = "Drag to position.\nClick the button again to save"
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

class ToastPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 420, height_hint: int = 120):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Achievement Toast")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._base_w = max(200, int(width_hint))
        self._base_h = max(80, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("ach_toast_x_portrait", 100))
            y0 = int(ov.get("ach_toast_y_portrait", 100))
        else:
            x0 = int(ov.get("ach_toast_x_landscape", 100))
            y0 = int(ov.get("ach_toast_y_landscape", 100))
        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        new_portrait = bool(self._portrait)
        if new_portrait != old_portrait:
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
        msg = "Drag to position.\nClick the button again to save"
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

class ChallengeOVPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 500, height_hint: int = 200):
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
        self._base_w = max(260, int(width_hint))
        self._base_h = max(120, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("ch_ov_x_portrait", 100))
            y0 = int(ov.get("ch_ov_y_portrait", 100))
        else:
            x0 = int(ov.get("ch_ov_x_landscape", 100))
            y0 = int(ov.get("ch_ov_y_landscape", 100))
        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

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
        msg = "Drag to position.\nClick the button again to save"
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

class MiniInfoPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 420, height_hint: int = 100):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Mini Info Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._base_w = max(200, int(width_hint))
        self._base_h = max(80, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
            
        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._screen_geo()
        
        if bool(ov.get("notifications_saved", False)):
            if self._portrait:
                x0 = int(ov.get("notifications_x_portrait", 100))
                y0 = int(ov.get("notifications_y_portrait", 100))
            else:
                x0 = int(ov.get("notifications_x_landscape", 100))
                y0 = int(ov.get("notifications_y_landscape", 100))
        else:
            # Wenn noch nie gespeichert, starte in der Mitte
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

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("notifications_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
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
        msg = "Drag to position.\nClick the button again to save"
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
        
class OverlayPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Overlay")
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
        self._w, self._h = self._calc_overlay_size()
        
        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._safe_screen_geo()
        
        if bool(ov.get("use_xy", False)):
            x0 = int(ov.get("pos_x", 100))
            y0 = int(ov.get("pos_y", 100))
        else:
            x0 = int(geo.left() + (geo.width() - self._w) // 2)
            y0 = int(geo.top() + (geo.height() - self._h) // 2)
            
        w_clamp = min(self._w, geo.width())
        h_clamp = min(self._h, geo.height())
        
        x = max(geo.left(), min(x0, geo.right() - w_clamp))
        y = max(geo.top(),  min(y0, geo.bottom() - h_clamp))
        
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _safe_screen_geo(self) -> QRect:
        try:
            scr = QApplication.primaryScreen()
            if scr:
                return scr.availableGeometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("portrait_mode", True))
            self._ccw = bool(ov.get("portrait_rotate_ccw", True))
        except Exception:
            self._portrait = True
            self._ccw = True

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        scale_pct = int(ov.get("scale_pct", 100))
        ref = self._safe_screen_geo()
        if self._portrait:
            base_h = int(ref.height() * 0.55)
            base_w = int(base_h * 9 / 16)
        else:
            base_w = int(ref.width() * 0.40)
            base_h = int(ref.height() * 0.30)
        w = max(120, int(base_w * scale_pct / 100))
        h = max(120, int(base_h * scale_pct / 100))
        return w, h
        
    def apply_portrait_from_cfg(self):
        self._sync_from_cfg()
        self._w, self._h = self._calc_overlay_size()
        g = self.geometry()
        x, y = g.x(), g.y()
        geo = self._safe_screen_geo()
        w_clamp = min(self._w, geo.width())
        h_clamp = min(self._h, geo.height())
        x = max(geo.left(), min(x, geo.right() - w_clamp))
        y = max(geo.top(),  min(y, geo.bottom() - h_clamp))
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
        msg = "Drag to position.\nClick the button again to save"
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
            geo = self._safe_screen_geo()
            w_clamp = min(self._w, geo.width())
            h_clamp = min(self._h, geo.height())
            x = max(geo.left(), min(target.x(), geo.right() - w_clamp))
            y = max(geo.top(),  min(target.y(), geo.bottom() - h_clamp))
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())

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

        # --- Burst particle animation ---
        is_level_up = (self._rom == "__levelup__")
        if low_perf:
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
        if is_level_up and not low_perf:
            self._ring_rings = [
                {'r': 0.0, 'elapsed': 0.0, 'delay': 0.0, 'alpha': 200},
                {'r': 0.0, 'elapsed': 0.0, 'delay': 200.0, 'alpha': 200},
            ]
            self._ring_elapsed = 0.0
            self._ring_duration = 600.0
            self._ring_active = True
            self._ring_timer = QTimer(self)
            self._ring_timer.setInterval(20)
            self._ring_timer.timeout.connect(self._ring_tick)
            self._ring_timer.start()

        # --- Typewriter reveal (subtitle line2) ---
        self._tw_full: str = ""
        self._tw_idx: int = 0
        self._tw_active: bool = not low_perf
        self._tw_cursor_visible: bool = True
        self._tw_cursor_timer = QTimer(self)
        self._tw_cursor_timer.setInterval(500)
        self._tw_cursor_timer.timeout.connect(self._tw_cursor_blink)
        if not low_perf:
            self._tw_cursor_timer.start()

        # --- Icon bounce animation ---
        self._bounce_elapsed: float = 0.0
        self._bounce_duration: float = 400.0
        self._bounce_active: bool = not low_perf

        # Combined fast animation timer (typewriter + bounce)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._anim_tick)
        if not low_perf:
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
            
            if not getattr(self, "_is_closing", False):
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
                     '_tw_cursor_timer', '_timer'):
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
            line1 = "⬆️  LEVEL UP!"
            line2 = self._title.replace("⬆️ LEVEL UP!  ", "").strip()
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

        # Set typewriter full text on first call
        if getattr(self, '_tw_active', False) and not getattr(self, '_tw_full', ''):
            self._tw_full = line2

        # Feste Theme-Farben
        title_color = QColor("#FF7F00") # Orange
        text_color = QColor("#FFFFFF")  # Weiß
        levelup_color = QColor("#00E5FF")  # Cyan for level-up line1

        title = line1
        # Apply typewriter reveal to subtitle (use full text for sizing, partial for display)
        sub_for_size = line2  # always use full text for width calculation
        if getattr(self, '_tw_active', False) and getattr(self, '_tw_full', ''):
            tw_text = self._tw_full[:self._tw_idx]
            if self._tw_cursor_visible and self._tw_idx < len(self._tw_full):
                tw_text += '|'
            sub = tw_text
        else:
            sub = line2
        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt, QFont.Weight.Bold if is_level_up else QFont.Weight.Normal)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)
        icon_sz = max(28, int(body_pt * 2.0))
        pad = max(12, int(body_pt * 0.8))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_w = fm_title.horizontalAdvance(title)
        sub_w = fm_body.horizontalAdvance(sub_for_size) if sub_for_size else 0
        text_w = max(title_w, sub_w)
        # Use sub_for_size for height calculation to keep window stable during typewriter
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
            # Expand window for burst/ring area
            x_win = x - burst_margin
            y_win = y - burst_margin
            self.setGeometry(x_win, y_win, EW, EH)
            self._label.setGeometry(0, 0, EW, EH)
            self._label.setPixmap(QPixmap.fromImage(img))
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
        """Advance typewriter index and icon bounce, then re-render."""
        dt = 30.0  # 30ms
        changed = False

        # Typewriter
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

        if changed:
            self._render_and_place()

        # Stop anim timer when both typewriter and bounce are done
        if not getattr(self, '_tw_active', False) and not getattr(self, '_bounce_active', False):
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
        if not low_perf:
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
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.08) % 1.0
        self._render_and_place()

    def set_selected(self, idx: int):
        self._selected = int(idx) % 4
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

        if int(getattr(self, "_selected", 0) or 0) % 4 == 0:
            title_text = "⌛ Timed Challenge"
            desc_text = "3:00 minutes playing time."
        elif int(getattr(self, "_selected", 0) or 0) % 4 == 1:
            title_text = "🎯 Flip Challenge"
            desc_text = "Count Left+Right flips until chosen target."
        elif int(getattr(self, "_selected", 0) or 0) % 4 == 2:
            title_text = "🔥 Heat Challenge"
            desc_text = "Keep heat below 100%. Don't spam or hold flippers!"
        else:
            title_text = "❌ Exit"
            desc_text = "Close the challenge menu."

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

            def measure_heights(t_pt: int, d_pt: int) -> tuple[int, int]:
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
                t_h, d_h = measure_heights(title_pt, desc_pt)
                total = t_h + 6 + d_h
                if total <= max_content_h:
                    break
                if title_pt > min_title: title_pt -= 1
                if desc_pt > min_desc: desc_pt -= 1
                if title_pt <= min_title and desc_pt <= min_desc: break

            t_h, d_h = measure_heights(title_pt, desc_pt)
            block_h = t_h + 6 + d_h
            content_top = top_pad + max(0, (max_content_h - block_h) // 2)

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

            # Eisblaue pulsierende Pfeile
            amp = 0.5 + 0.5 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
            alpha = 110 + int(120 * amp)
            anim_scale = 0.9 + 0.2 * amp
            wobble = 2.0 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
            base_arr_h = max(10, int(round(18 * factor)))
            ah = int(base_arr_h * anim_scale)
            aw = max(6, int(ah * 0.6))
            cy = title_rect.center().y()
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
        if not low_perf:
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
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.08) % 1.0
        self._render_and_place()

    def set_selected(self, idx: int):
        self._selected = max(0, min(int(idx or 0), len(self._options) - 1))
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
                
                if selected:
                    amp = 0.5 + 0.5 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
                    alpha = 40 + int(60 * amp)
                    p.fillRect(rect.adjusted(-4, -4, 4, 4), QColor(255, 127, 0, alpha)) # Oranger Pulse
                    p.setPen(QPen(QColor("#00E5FF"), 2))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
                    
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, 10, 10)

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

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))
        self._render_and_place()

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

            # pulsing red border when > 85%
            if self._heat > 85:
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

        self._base_w = max(36, int(width_hint))
        self._base_h = max(120, int(height_hint))
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()

        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h

        ov = self.parent_gui.cfg.OVERLAY or {}
        if self._portrait:
            x0 = int(ov.get("heat_bar_x_portrait", 20))
            y0 = int(ov.get("heat_bar_y_portrait", 100))
        else:
            x0 = int(ov.get("heat_bar_x_landscape", 20))
            y0 = int(ov.get("heat_bar_y_landscape", 100))

        geo = self._screen_geo()
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            screens = QApplication.screens() or []
            if screens:
                vgeo = screens[0].geometry()
                for s in screens[1:]:
                    vgeo = vgeo.united(s.geometry())
                return vgeo
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

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
        pen = QPen(QColor("#FF7F00"))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 8, 8)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        msg = "Drag to position.\nClick button again to save"
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
