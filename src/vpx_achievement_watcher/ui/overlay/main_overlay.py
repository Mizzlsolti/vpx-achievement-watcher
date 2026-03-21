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

from .helpers import _draw_glow_border, _ease_out_bounce, _ease_out_cubic, _force_topmost, _start_topmost_timer, _OVERLAY_PAGE_ACCENTS

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
            right_cx = draw_w - pad + int(wobble)
            arrow_color = QColor("#00E5FF")
            arrow_color.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(arrow_color)
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

        # Per-page accent colour (smoothly lerped)
        self._accent_color: QColor = QColor(0, 229, 255)
        self._target_accent: QColor = QColor(0, 229, 255)

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
        try:
            ov = self.parent().parent_gui.cfg.OVERLAY
            low_perf = bool(ov.get("low_performance_mode", False))
            anim_glow = bool(ov.get("anim_main_glow", True))
        except Exception:
            low_perf = False
            anim_glow = True
        if low_perf or not anim_glow:
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
        # Smoothly lerp accent color toward target (~1s transition)
        tgt = self._target_accent
        cur = self._accent_color
        lerp = 0.06
        r = int(cur.red()   + (tgt.red()   - cur.red())   * lerp)
        g = int(cur.green() + (tgt.green() - cur.green()) * lerp)
        b = int(cur.blue()  + (tgt.blue()  - cur.blue())  * lerp)
        self._accent_color = QColor(max(0, min(255, r)),
                                    max(0, min(255, g)),
                                    max(0, min(255, b)))
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

    def set_accent(self, color: QColor):
        """Set the target accent color; the glow will smoothly lerp to it."""
        self._target_accent = QColor(color)

    def paintEvent(self, event):
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return
        try:
            ov = self.parent().parent_gui.cfg.OVERLAY
            low_perf = bool(ov.get("low_performance_mode", False))
            anim_glow = bool(ov.get("anim_main_glow", True))
        except Exception:
            low_perf = False
            anim_glow = True
        if low_perf or not anim_glow:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            # Breathing glow border — use smoothly lerped accent colour
            amp = 0.5 + 0.5 * math.sin(2 * math.pi * self._glow_t)
            alpha_base = int(120 + 135 * amp)  # 120..255
            layers = int(2 + 2 * amp)          # 2..4
            ac = self._accent_color
            glow_color = QColor(ac.red(), ac.green(), ac.blue(), alpha_base)
            _draw_glow_border(p, 0, 0, W, H, radius=18, color=glow_color, layers=layers)

            # Floating particles — tinted to accent colour
            p.setPen(Qt.PenStyle.NoPen)
            for pt in self._particles:
                c = QColor(ac.red(), ac.green(), ac.blue(), int(pt['alpha']))
                p.setBrush(c)
                sz = int(pt['size'])
                p.drawEllipse(int(pt['x']) - sz // 2, int(pt['y']) - sz // 2, sz, sz)
        finally:
            try:
                p.end()
            except Exception:
                pass



class _OverlayShineWidget(QWidget):
    """Transparent overlay that draws a horizontal shine/sweep stripe
    over the estimated progress bar area of the main overlay."""

    # Progress bar is placed roughly in the upper-middle of the body content:
    # ~25-38% down from the widget top, spanning the centred 75%-width bar.
    _BAR_TOP_FRAC = 0.25    # fraction of widget height where bar area starts
    _BAR_H_FRAC   = 0.13    # fraction of widget height that covers bar area
    _STRIPE_W_FRAC = 0.22   # width of the shine stripe relative to widget width

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._t: float = 0.0  # 0.0..1.0 sweep position
        self.hide()

    def paintEvent(self, _ev):
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return
        bar_top  = int(H * self._BAR_TOP_FRAC)
        bar_h    = int(H * self._BAR_H_FRAC)
        stripe_w = int(W * self._STRIPE_W_FRAC)
        x = int(-stripe_w + self._t * (W + stripe_w * 2))
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            grad = QLinearGradient(float(x), float(bar_top),
                                   float(x + stripe_w), float(bar_top))
            grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            grad.setColorAt(0.35, QColor(255, 255, 255, 55))
            grad.setColorAt(0.65, QColor(255, 255, 255, 55))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(x, bar_top, stripe_w, bar_h, QBrush(grad))
        finally:
            try:
                p.end()
            except Exception:
                pass



class _OverlayHighlightWidget(QWidget):
    """Briefly flashes a warm amber highlight over the overlay content area
    when score or progress values change."""

    # Warm amber tint used for the value-change highlight flash
    _FLASH_COLOR = QColor(255, 200, 80)
    # Starting alpha (0-255) for the highlight; fades to 0 over ~240 ms
    _INITIAL_ALPHA = 45
    # Alpha step subtracted each 16 ms tick → fade duration ≈ alpha/step*16 ms
    _FADE_STEP = 3

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._alpha: int = 0
        self.hide()

    def paintEvent(self, _ev):
        if self._alpha <= 0:
            return
        p = QPainter(self)
        try:
            c = QColor(self._FLASH_COLOR)
            c.setAlpha(self._alpha)
            p.fillRect(self.rect(), c)
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
                # Hide raw widgets immediately so the window never exposes
                # unrotated content while the rotation snapshot is being built.
                self.container.hide()
                self.text_container.hide()
                QTimer.singleShot(0, lambda: self.request_rotation(force=True))
            else:
                QTimer.singleShot(0, self._show_live_unrotated)
        W, H = self.width(), self.height()
        # Start effects overlay (glow border + floating particles)
        if hasattr(self, '_effects_widget'):
            low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
            anim_glow = bool(self.parent_gui.cfg.OVERLAY.get("anim_main_glow", True))
            if not low_perf and anim_glow:
                self._effects_widget.setGeometry(0, 0, W, H)
                self._effects_widget.show()
                self._effects_widget.raise_()
        # Size the shine and highlight overlay widgets
        if hasattr(self, '_shine_widget'):
            self._shine_widget.setGeometry(0, 0, W, H)
        if hasattr(self, '_highlight_widget'):
            self._highlight_widget.setGeometry(0, 0, W, H)

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
        if hasattr(self, '_shine_timer'):
            self._shine_timer.stop()
        if hasattr(self, '_highlight_timer'):
            self._highlight_timer.stop()


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
                   "background:rgba(8,12,22,252);border:2px solid #00E5FF;border-radius:18px;}")
        else:
            css = ("QWidget#overlay_bg {background:rgba(8,12,22,252);"
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
        # Per-page accent colour index
        self._page_index: int = 0
        # Shine/sweep effect for progress bar
        self._shine_widget = _OverlayShineWidget(self)
        self._shine_timer = QTimer(self)
        self._shine_timer.setInterval(16)
        self._shine_timer.timeout.connect(self._shine_tick)
        # Value highlight/pulse flash
        self._highlight_widget = _OverlayHighlightWidget(self)
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setInterval(16)
        self._highlight_timer.timeout.connect(self._highlight_tick)

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
        if hasattr(self, '_shine_widget'):
            self._shine_widget.setGeometry(0, 0, w, h)
        if hasattr(self, '_highlight_widget'):
            self._highlight_widget.setGeometry(0, 0, w, h)

    def _layout_positions(self):
        if getattr(self, '_rot_in_progress', False):
            return
        self._layout_positions_for(self.width(), self.height())
        if self.portrait_mode:
            self.request_rotation(force=True)

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
            old_pct_target = getattr(self, '_progress_pct_target', -1.0)
            self._progress_pct_target = new_pct_target
            if not self._anim_ok("anim_main_score_progress"):
                self._progress_pct_current = self._progress_pct_target
            else:
                if not hasattr(self, '_progress_bar_timer_started') or not getattr(self, '_progress_bar_timer_started', False):
                    # Fresh start: jump to 0 for a fill animation
                    self._progress_pct_current = 0.0
                if hasattr(self, '_progress_bar_timer'):
                    self._progress_bar_timer.start()
                # Trigger shine when progress actually changes (not first display)
                if old_pct_target >= 0:
                    self._trigger_shine()

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
                old_score = getattr(self, '_score_target', 0)
                self._score_target = score_abs
                if getattr(self, '_score_display', 0) == 0:
                    self._score_display = 0
                if not self._anim_ok("anim_main_score_progress"):
                    self._score_display = self._score_target
                elif hasattr(self, '_score_spin_timer'):
                    self._score_spin_timer.start()
                # Flash highlight when score changes (not on initial 0→value)
                if old_score > 0 and score_abs != old_score:
                    self._trigger_highlight()

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
            return

        html = style + "<div align='center' style='width:100%;'>" + \
               "".join(f"{block(p)}" for p in players) + \
               "</div>"

        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self._layout_positions()
        
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

    # ------------------------------------------------------------------
    # Animation helpers
    # ------------------------------------------------------------------

    def _anim_ok(self, key: str) -> bool:
        """Return True only when low_performance_mode is off AND *key* is enabled."""
        ov = self.parent_gui.cfg.OVERLAY
        if bool(ov.get("low_performance_mode", False)):
            return False
        return bool(ov.get(key, True))

    def _trigger_shine(self):
        """Start a shine/sweep over the estimated progress bar area."""
        if not self._anim_ok("anim_main_highlights"):
            return
        W, H = self.width(), self.height()
        self._shine_widget.setGeometry(0, 0, W, H)
        self._shine_widget._t = 0.0
        self._shine_widget.show()
        self._shine_widget.raise_()
        if not self._shine_timer.isActive():
            self._shine_timer.start()

    def _shine_tick(self):
        """Advance the progress bar shine sweep (~800 ms full pass)."""
        self._shine_widget._t = min(1.0, self._shine_widget._t + 16.0 / 800.0)
        self._shine_widget.update()
        if self._shine_widget._t >= 1.0:
            self._shine_timer.stop()
            self._shine_widget.hide()

    def _trigger_highlight(self):
        """Flash a brief warm highlight to signal a value change."""
        if not self._anim_ok("anim_main_highlights"):
            return
        W, H = self.width(), self.height()
        self._highlight_widget.setGeometry(0, 0, W, H)
        self._highlight_widget._alpha = _OverlayHighlightWidget._INITIAL_ALPHA
        self._highlight_widget.show()
        self._highlight_widget.raise_()
        if not self._highlight_timer.isActive():
            self._highlight_timer.start()

    def _highlight_tick(self):
        """Fade the highlight overlay out at the rate defined by _FADE_STEP."""
        self._highlight_widget._alpha = max(
            0, self._highlight_widget._alpha - _OverlayHighlightWidget._FADE_STEP
        )
        self._highlight_widget.update()
        if self._highlight_widget._alpha <= 0:
            self._highlight_timer.stop()
            self._highlight_widget.hide()

    def transition_to(self, new_content_callback, direction: str = 'left'):
        """Perform a slide+fade page transition (with a brief glitch pre-effect).

        Call this instead of set_html/set_combined when changing pages.  The method
        captures the current display, runs the callback to update content, then animates
        between old and new snapshots.
        """
        if not self._anim_ok("anim_main_transitions"):
            new_content_callback()
            return

        old_img = self._snapshot_current()
        if old_img is None or old_img.isNull():
            new_content_callback()
            return

        # Advance page index for accent colour cycling
        n = len(_OVERLAY_PAGE_ACCENTS)
        if direction == 'left':
            self._page_index = (self._page_index + 1) % n
        else:
            self._page_index = (self._page_index - 1) % n
        if hasattr(self, '_effects_widget'):
            self._effects_widget.set_accent(_OVERLAY_PAGE_ACCENTS[self._page_index])

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

        if state['phase'] == 'zoom':
            # Zoom-settle phase: new content eases in from 0.97x → 1.0x
            state['zoom_elapsed'] += dt
            zoom_duration = 180.0
            zt = min(1.0, state['zoom_elapsed'] / zoom_duration)
            zoom_eased = _ease_out_cubic(zt)
            scale = 0.97 + 0.03 * zoom_eased
            new_img = state.get('new_img')
            if new_img and not new_img.isNull() and self._transition_label:
                W, H = new_img.width(), new_img.height()
                out = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
                out.fill(Qt.GlobalColor.transparent)
                pp = QPainter(out)
                pp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                try:
                    sw = int(W * scale)
                    sh = int(H * scale)
                    ox = (W - sw) // 2
                    oy = (H - sh) // 2
                    pp.drawImage(QRect(ox, oy, sw, sh), new_img)
                finally:
                    try:
                        pp.end()
                    except Exception:
                        pass
                self._transition_label.setPixmap(QPixmap.fromImage(out))
            if zt >= 1.0:
                self._transition_timer.stop()
                if self._transition_label:
                    self._transition_label.hide()
                self._transition_state = None
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
            # Enter zoom-settle phase
            new_img = state.get('new_img')
            if new_img and not new_img.isNull():
                state['phase'] = 'zoom'
                state['zoom_elapsed'] = 0.0
            else:
                self._transition_timer.stop()
                if self._transition_label:
                    self._transition_label.hide()
                self._transition_state = None


