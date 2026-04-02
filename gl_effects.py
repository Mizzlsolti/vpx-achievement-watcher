"""gl_effects.py – Centralized Animation Engine for all overlay animations.

All animation logic is collected here so that ``ui_overlay.py`` contains only
widget layout and state management, while this module owns *how* things animate.

Architecture is OpenGL-ready: the ``_HAS_OPENGL`` flag is set at import time
so any class can later be given a GPU-accelerated code path without changing
any calling code.

Public exports
--------------
Helper functions
    draw_glow_border, ease_out_bounce, ease_out_cubic

Overlay effect widgets
    EffectsWidget, ShineWidget, HighlightWidget

Animation primitive classes
    ParticleBurst, NeonRingExpansion, TypewriterReveal, IconBounce,
    SlideMotion, EnergyFlash, BreathingPulse, CarouselSlide,
    SnapScale, HeatPulse, ScanIn, GlowSweep, ColorMorph, GlitchFrame
"""
from __future__ import annotations

import math
import random

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient,
    QPainter, QPen, QPixmap,
)
from PyQt6.QtWidgets import QWidget

from theme import get_theme, get_theme_color, DEFAULT_THEME

# ---------------------------------------------------------------------------
# OpenGL detection – architecture ready; all implementations use QPainter
# for now since we are not yet adding GLSL shaders.
# ---------------------------------------------------------------------------
_HAS_OPENGL = False
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # noqa: F401
    from OpenGL.GL import *                           # noqa: F401, F403
    _HAS_OPENGL = True
except ImportError:
    pass


# ===========================================================================
# 1. Helper functions (public API; previously private in ui_overlay.py)
# ===========================================================================

def draw_glow_border(painter: QPainter, x: int, y: int, w: int, h: int,
                     radius: int = 18, color: QColor = None, layers: int = 3,
                     low_perf: bool = False):
    """Draw a multi-layer neon glow border for a modern sci-fi look.

    Used by ALL overlay widgets (main overlay, toast, flip counter,
    challenge select, heat barometer, countdown timer, etc.).
    """
    if color is None:
        color = QColor("#00E5FF")
    if not low_perf:
        for i in range(layers, 0, -1):
            alpha = int(30 * (layers + 1 - i))
            glow_pen = QPen(QColor(color.red(), color.green(), color.blue(), alpha))
            glow_pen.setWidth(i * 2)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(x + i, y + i, w - 2 * i, h - 2 * i, radius, radius)
    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(x + 1, y + 1, w - 2, h - 2, radius, radius)


def ease_out_bounce(t: float) -> float:
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


def ease_out_cubic(t: float) -> float:
    """Ease-out cubic curve used for slide transitions."""
    return 1.0 - (1.0 - t) ** 3


# ===========================================================================
# 2. Overlay Effect Widgets (moved from ui_overlay.py, public names)
# ===========================================================================

class EffectsWidget(QWidget):
    """Transparent overlay that draws the animated glow border and floating
    particles over the main overlay window.

    Replaces ``OverlayEffectsWidget`` in ``ui_overlay.py``; import with::

        from gl_effects import EffectsWidget as OverlayEffectsWidget
    """

    _PARTICLE_COUNT = 18

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Breathing glow state
        self._glow_t = 0.0

        # Floating particles
        self._particles: list = []

        # Per-page accent colour (smoothly lerped)
        try:
            _initial_accent = QColor(get_theme_color(parent.parent_gui.cfg, "primary"))
        except Exception:
            _initial_accent = QColor(get_theme(DEFAULT_THEME)["primary"])
        self._accent_color: QColor = _initial_accent
        self._target_accent: QColor = QColor(_initial_accent)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(50)
        self._tick_timer.timeout.connect(self._on_tick)
        self.hide()

    def _init_particles(self):
        W = max(200, self.width() if self.width() > 0 else 400)
        H = max(200, self.height() if self.height() > 0 else 600)
        self._particles = []
        for _ in range(self._PARTICLE_COUNT):
            self._particles.append(self._make_particle(W, H, spawn_anywhere=True))

    def _make_particle(self, W: int, H: int, spawn_anywhere: bool = False) -> dict:
        return {
            'x': random.uniform(0, W),
            'y': random.uniform(0, H) if spawn_anywhere else random.choice([
                random.uniform(-10, 0),
                random.uniform(H, H + 20),
            ]),
            'vx': random.uniform(-15, 15),
            'vy': random.uniform(-25, 25) if spawn_anywhere else random.uniform(-30, -10),
            'size': random.uniform(2, 6),
            'alpha': random.randint(30, 100),
            'alpha_dir': random.choice([-1, 1]),
        }

    def showEvent(self, event):
        super().showEvent(event)
        try:
            ov = self.parent().parent_gui.cfg.OVERLAY
            low_perf = bool(ov.get("low_performance_mode", False))
            anim_glow = bool(ov.get("fx_main_breathing_glow", ov.get("anim_main_glow", True)))
            anim_particles = bool(ov.get("fx_main_floating_particles", ov.get("anim_main_glow", True)))
        except Exception:
            low_perf = False
            anim_glow = True
            anim_particles = True
        if low_perf or (not anim_glow and not anim_particles):
            return
        if not self._particles:
            self._init_particles()
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._tick_timer.stop()

    def _on_tick(self):
        # Advance glow breath (~6.25 s period at 50 ms interval)
        self._glow_t = (self._glow_t + 0.008) % 1.0
        # Smoothly lerp accent color toward target (~1 s transition)
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
        dt = 0.05  # 50 ms in seconds
        for pt in self._particles:
            pt['x'] += pt['vx'] * dt
            pt['y'] += pt['vy'] * dt
            pt['alpha'] += pt['alpha_dir'] * 2
            if pt['alpha'] >= 100:
                pt['alpha'] = 100
                pt['alpha_dir'] = -1
            elif pt['alpha'] <= 20:
                pt['alpha'] = 20
                pt['alpha_dir'] = 1
            if pt['y'] < -10 or pt['y'] > H + 10 or pt['x'] < -10 or pt['x'] > W + 10:
                pt.update(self._make_particle(W, H, spawn_anywhere=True))
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
            fx_glow = bool(ov.get("fx_main_breathing_glow", ov.get("anim_main_glow", True)))
            fx_particles = bool(ov.get("fx_main_floating_particles", ov.get("anim_main_glow", True)))
            glow_intensity = max(0.0, min(1.0, float(ov.get("fx_main_breathing_glow_intensity", 80)) / 100.0))
            particles_intensity = max(0.0, min(1.0, float(ov.get("fx_main_floating_particles_intensity", 80)) / 100.0))
        except Exception:
            low_perf = False
            fx_glow = True
            fx_particles = True
            glow_intensity = 0.8
            particles_intensity = 0.8
        if low_perf:
            return
        draw_glow = fx_glow
        draw_particles = fx_particles
        if not draw_glow and not draw_particles:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            amp = 0.5 + 0.5 * math.sin(2 * math.pi * self._glow_t)
            ac = self._accent_color
            if draw_glow:
                alpha_base = int((120 + 135 * amp) * glow_intensity)  # scale by intensity
                layers = max(1, int((2 + 2 * amp) * glow_intensity))  # scale layers by intensity
                glow_color = QColor(ac.red(), ac.green(), ac.blue(), alpha_base)
                draw_glow_border(p, 0, 0, W, H, radius=18, color=glow_color, layers=layers)
            if draw_particles:
                # Scale particle count by intensity (fewer particles at lower intensity)
                particle_count = max(1, int(len(self._particles) * particles_intensity))
                p.setPen(Qt.PenStyle.NoPen)
                for pt in self._particles[:particle_count]:
                    alpha = int(pt['alpha'] * particles_intensity)
                    c = QColor(ac.red(), ac.green(), ac.blue(), alpha)
                    p.setBrush(c)
                    sz = int(pt['size'])
                    p.drawEllipse(int(pt['x']) - sz // 2, int(pt['y']) - sz // 2, sz, sz)
        finally:
            try:
                p.end()
            except Exception:
                pass


class ShineWidget(QWidget):
    """Transparent overlay that draws a horizontal shine/sweep stripe over
    the estimated progress bar area of the main overlay.

    Replaces ``_OverlayShineWidget`` in ``ui_overlay.py``; import with::

        from gl_effects import ShineWidget as _OverlayShineWidget
    """

    _BAR_TOP_FRAC  = 0.25   # fraction of widget height where bar area starts
    _BAR_H_FRAC    = 0.13   # fraction of widget height that covers bar area
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
        # Live check: skip drawing if fx_main_shine_sweep is disabled
        try:
            ov = self.parent().parent_gui.cfg.OVERLAY
            if bool(ov.get("low_performance_mode", False)) or not bool(ov.get("fx_main_shine_sweep", True)):
                return
        except Exception:
            pass
        portrait = False
        try:
            portrait = bool(self.parent().portrait_mode)
        except Exception:
            pass
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            if portrait:
                bar_top  = int(W * self._BAR_TOP_FRAC)
                bar_h    = int(W * self._BAR_H_FRAC)
                stripe_w = int(H * self._STRIPE_W_FRAC)
                y = int(-stripe_w + self._t * (H + stripe_w * 2))
                grad = QLinearGradient(float(bar_top), float(y),
                                       float(bar_top), float(y + stripe_w))
                grad.setColorAt(0.0,  QColor(255, 255, 255, 0))
                grad.setColorAt(0.35, QColor(255, 255, 255, 55))
                grad.setColorAt(0.65, QColor(255, 255, 255, 55))
                grad.setColorAt(1.0,  QColor(255, 255, 255, 0))
                p.fillRect(bar_top, y, bar_h, stripe_w, QBrush(grad))
            else:
                bar_top  = int(H * self._BAR_TOP_FRAC)
                bar_h    = int(H * self._BAR_H_FRAC)
                stripe_w = int(W * self._STRIPE_W_FRAC)
                x = int(-stripe_w + self._t * (W + stripe_w * 2))
                grad = QLinearGradient(float(x), float(bar_top),
                                       float(x + stripe_w), float(bar_top))
                grad.setColorAt(0.0,  QColor(255, 255, 255, 0))
                grad.setColorAt(0.35, QColor(255, 255, 255, 55))
                grad.setColorAt(0.65, QColor(255, 255, 255, 55))
                grad.setColorAt(1.0,  QColor(255, 255, 255, 0))
                p.fillRect(x, bar_top, stripe_w, bar_h, QBrush(grad))
        finally:
            try:
                p.end()
            except Exception:
                pass


class HighlightWidget(QWidget):
    """Briefly flashes a warm amber highlight over the overlay content area
    when score or progress values change.

    Replaces ``_OverlayHighlightWidget`` in ``ui_overlay.py``; import with::

        from gl_effects import HighlightWidget as _OverlayHighlightWidget
    """

    _FLASH_COLOR   = QColor(255, 200, 80)
    _INITIAL_ALPHA = 45
    _FADE_STEP     = 3

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
        # Live check: skip drawing if fx_main_highlight_flash is disabled
        try:
            ov = self.parent().parent_gui.cfg.OVERLAY
            if bool(ov.get("low_performance_mode", False)) or not bool(ov.get("fx_main_highlight_flash", True)):
                return
        except Exception:
            pass
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


# ===========================================================================
# 3. Reusable Animation Primitive Classes
#
# Consistent API pattern for every primitive:
#   __init__(self, ...config params...)
#   start(self)                  – reset and activate
#   tick(self, dt_ms: float)     – advance by dt milliseconds
#   draw(self, painter, ...)     – render onto painter
#   is_active(self) -> bool      – still animating?
# ===========================================================================

class ParticleBurst:
    """20 particles exploding outward from center with gravity and fade.

    Extracted from ``AchToastWindow`` burst particle logic.
    """

    def __init__(self, count: int = 20, color: QColor = None,
                 speed_range: tuple = (80, 200)):
        self._count = int(count)
        self._color = color if color is not None else QColor("#00E5FF")
        self._speed_range = speed_range
        self._particles: list = []
        self._elapsed: float = 0.0
        self._duration: float = 700.0
        self._active: bool = False

    def start(self):
        """Reset particles to center position and activate the burst."""
        self._particles = []
        for _ in range(self._count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(self._speed_range[0], self._speed_range[1])
            self._particles.append({
                'x': 0.0, 'y': 0.0,
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed,
                'size': random.uniform(3, 6),
                'alpha': 255,
                'color': QColor(self._color),
            })
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        """Advance particle positions and alpha fade."""
        dt = dt_ms / 1000.0
        self._elapsed += dt_ms
        for pt in self._particles:
            pt['x'] += pt['vx'] * dt
            pt['y'] += pt['vy'] * dt
            pt['vy'] += 60 * dt   # slight gravity
            fade = 1.0 - min(1.0, self._elapsed / self._duration)
            pt['alpha'] = int(255 * fade)
        if self._elapsed >= self._duration:
            self._active = False

    def draw(self, painter: QPainter, cx: int, cy: int):
        """Draw all particles centered at (cx, cy)."""
        painter.setPen(Qt.PenStyle.NoPen)
        for pt in self._particles:
            if pt['alpha'] > 0:
                c = QColor(pt['color'])
                c.setAlpha(int(max(0, min(255, pt['alpha']))))
                painter.setBrush(c)
                sz = max(1, int(pt['size']))
                painter.drawEllipse(cx + int(pt['x']) - sz // 2,
                                    cy + int(pt['y']) - sz // 2, sz, sz)

    def is_active(self) -> bool:
        return self._active


class NeonRingExpansion:
    """Multiple expanding neon rings for level-up celebration.

    Extracted from ``AchToastWindow`` ring expansion logic.
    """

    def __init__(self, ring_count: int = 4, delays: list = None,
                 duration: float = 550.0):
        if delays is None:
            delays = [0.0, 150.0, 300.0, 450.0]
        self._ring_count = int(ring_count)
        self._delays = list(delays)
        self._duration = float(duration)
        self._rings: list = []
        self._elapsed: float = 0.0
        self._active: bool = False

    def start(self):
        """Reset rings and activate the expansion."""
        default_alphas = [200, 200, 180, 150]
        self._rings = [
            {
                'r': 0.0,
                'elapsed': 0.0,
                'delay': self._delays[i] if i < len(self._delays) else 0.0,
                'alpha': default_alphas[i] if i < len(default_alphas) else 150,
            }
            for i in range(self._ring_count)
        ]
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float, max_r: float = 300.0):
        """Advance ring expansion. *max_r* is the maximum ring radius."""
        self._elapsed += dt_ms
        all_done = True
        for ring in self._rings:
            effective_elapsed = self._elapsed - ring['delay']
            if effective_elapsed < 0:
                all_done = False
                continue
            t = min(1.0, effective_elapsed / self._duration)
            ring['r'] = t * max_r
            ring['alpha'] = int(200 * (1.0 - t))
            if t < 1.0:
                all_done = False
        if all_done:
            self._active = False

    def draw(self, painter: QPainter, cx: int, cy: int, color: QColor):
        """Draw all rings centered at (cx, cy) using *color*."""
        for ring in self._rings:
            r = int(ring['r'])
            alp = int(max(0, min(255, ring['alpha'])))
            if r > 0 and alp > 0:
                c = QColor(color.red(), color.green(), color.blue(), alp)
                pen = QPen(c)
                pen.setWidth(3)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)

    def is_active(self) -> bool:
        return self._active


class TypewriterReveal:
    """Character-by-character text reveal with blinking cursor.

    Extracted from ``AchToastWindow`` typewriter logic.
    """

    def __init__(self, speed: int = 1):
        self._speed = max(1, int(speed))
        self._full_text: str = ""
        self._idx: int = 0
        self._active: bool = False
        self._cursor_visible: bool = True

    @property
    def full_text(self) -> str:
        return self._full_text

    def set_text(self, text: str):
        """Set the text to reveal. Call before :meth:`start`."""
        self._full_text = str(text or "")
        self._idx = 0

    def start(self):
        """Reset and activate the typewriter reveal."""
        self._idx = 0
        self._active = True
        self._cursor_visible = True

    def tick(self, dt_ms: float):
        """Advance typewriter index by *speed* characters."""
        if self._active and self._idx < len(self._full_text):
            self._idx = min(len(self._full_text), self._idx + self._speed)
            if self._idx >= len(self._full_text):
                self._active = False

    def toggle_cursor(self):
        """Toggle cursor visibility (call from blink timer)."""
        self._cursor_visible = not self._cursor_visible

    def current_text(self, show_cursor: bool = True) -> str:
        """Return the currently revealed text with optional blinking cursor."""
        text = self._full_text[:self._idx]
        if show_cursor and self._cursor_visible and self._active:
            text += "|"
        return text

    def draw(self, painter: QPainter, rect: QRect, font: QFont, color: QColor):
        """Draw the currently revealed text into *rect*."""
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self.current_text())

    def is_active(self) -> bool:
        return self._active


class IconBounce:
    """Scale 1.3→1.0 with ease-out-bounce and a Y offset of -30→0.

    Extracted from ``AchToastWindow`` icon bounce logic.
    """

    def __init__(self, duration: float = 400.0, start_scale: float = 1.3):
        self._duration = float(duration)
        self._start_scale = float(start_scale)
        self._elapsed: float = 0.0
        self._active: bool = False

    def start(self):
        """Reset and activate the bounce."""
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        """Advance bounce elapsed time."""
        if self._active:
            self._elapsed += dt_ms
            if self._elapsed >= self._duration:
                self._elapsed = self._duration
                self._active = False

    def get_scale_and_offset(self) -> tuple:
        """Return ``(scale, y_offset)`` for icon rendering.

        scale: *start_scale*→1.0, y_offset: -30→0.
        """
        t = min(1.0, self._elapsed / max(1.0, self._duration))
        eased = ease_out_bounce(t)
        scale = self._start_scale + (1.0 - self._start_scale) * eased
        y_offset = int(-30 * (1.0 - eased))
        return scale, y_offset

    def draw(self, painter: QPainter, *args, **kwargs):
        """IconBounce provides values via :meth:`get_scale_and_offset`."""
        pass

    def is_active(self) -> bool:
        return self._active


class SlideMotion:
    """Slide-in (entry) and slide-out (exit) with ease-out-cubic.

    Extracted from ``AchToastWindow`` slide motion logic.
    """

    def __init__(self, entry_duration: float = 250.0, exit_duration: float = 200.0,
                 distance: int = 60):
        self._entry_duration = float(entry_duration)
        self._exit_duration = float(exit_duration)
        self._distance = int(distance)
        self._entry_active: bool = False
        self._entry_elapsed: float = 0.0
        self._exit_active: bool = False
        self._exit_elapsed: float = 0.0

    def start_entry(self):
        """Start slide-in (entry) animation."""
        self._entry_active = True
        self._entry_elapsed = 0.0
        self._exit_active = False
        self._exit_elapsed = 0.0

    def start_exit(self):
        """Start slide-out (exit) animation."""
        self._exit_active = True
        self._exit_elapsed = 0.0
        self._entry_active = False

    def tick(self, dt_ms: float) -> bool:
        """Advance animation by *dt_ms*. Returns ``True`` while still active."""
        if self._entry_active:
            self._entry_elapsed += dt_ms
            if self._entry_elapsed >= self._entry_duration:
                self._entry_active = False
                self._entry_elapsed = self._entry_duration
        elif self._exit_active:
            self._exit_elapsed += dt_ms
            if self._exit_elapsed >= self._exit_duration:
                self._exit_active = False
                self._exit_elapsed = self._exit_duration
        return self.is_active()

    def get_offset_and_opacity(self) -> tuple:
        """Return ``(x_offset, opacity)`` for the current animation frame."""
        if self._entry_active:
            t = min(1.0, self._entry_elapsed / max(1.0, self._entry_duration))
            eased = ease_out_cubic(t)
            return int(self._distance * (1.0 - eased)), max(0.0, min(1.0, eased))
        if self._exit_active:
            t = min(1.0, self._exit_elapsed / max(1.0, self._exit_duration))
            return int(self._distance * t), max(0.0, min(1.0, 1.0 - t))
        return 0, 1.0

    def is_entry_active(self) -> bool:
        return self._entry_active

    def is_exit_active(self) -> bool:
        return self._exit_active

    def is_active(self) -> bool:
        return self._entry_active or self._exit_active

    def draw(self, painter: QPainter, *args, **kwargs):
        """SlideMotion provides values via :meth:`get_offset_and_opacity`."""
        pass


class EnergyFlash:
    """Full-widget color flash that fades out on level-up entry.

    Extracted from ``AchToastWindow`` energy flash logic.
    """

    def __init__(self, duration: float = 300.0, start_alpha: int = 180):
        self._duration = float(duration)
        self._start_alpha = int(start_alpha)
        self._elapsed: float = 0.0
        self._active: bool = False

    def start(self):
        """Reset and activate the flash."""
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        """Advance flash elapsed time."""
        if self._active:
            self._elapsed += dt_ms
            if self._elapsed >= self._duration:
                self._elapsed = self._duration
                self._active = False

    def draw(self, painter: QPainter, w: int, h: int, radius: int, color: QColor):
        """Draw the flash overlay if active."""
        if not self._active:
            return
        t = min(1.0, self._elapsed / max(1.0, self._duration))
        alpha = int(self._start_alpha * (1.0 - t))
        if alpha > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            flash_color = QColor(color.red(), color.green(), color.blue(), alpha)
            painter.setBrush(flash_color)
            painter.drawRoundedRect(0, 0, w, h, radius, radius)

    def is_active(self) -> bool:
        return self._active


class BreathingPulse:
    """Sine-wave based alpha/scale oscillation. Never stops.

    Used by FlipCounterOverlay, ChallengeSelectOverlay, FlipDifficultyOverlay,
    HeatBarometerOverlay, and EffectsWidget.
    """

    def __init__(self, speed: float = 0.05, min_alpha: int = 40,
                 max_alpha: int = 220):
        self._speed = float(speed)
        self._min_alpha = int(min_alpha)
        self._max_alpha = int(max_alpha)
        self._t: float = 0.0

    def start(self):
        """Reset pulse phase to zero."""
        self._t = 0.0

    def tick(self, dt_ms: float = 50.0):
        """Advance pulse phase by one step."""
        self._t = (self._t + self._speed) % 1.0

    def get_amp(self) -> float:
        """Return amplitude in the range 0.0–1.0."""
        return 0.5 + 0.5 * math.sin(2 * math.pi * self._t)

    def get_sin(self) -> float:
        """Return raw sine value in the range -1.0–1.0."""
        return math.sin(2 * math.pi * self._t)

    def get_alpha(self, min_alpha: int = None, max_alpha: int = None) -> int:
        """Return current alpha derived from the pulse amplitude."""
        lo = self._min_alpha if min_alpha is None else min_alpha
        hi = self._max_alpha if max_alpha is None else max_alpha
        return int(lo + (hi - lo) * self.get_amp())

    def draw(self, painter: QPainter, x: int, y: int, w: int, h: int,
             radius: int, color: QColor, width: int = 5):
        """Draw a pulsating glow ring at the given rectangle."""
        alpha = self.get_alpha()
        pen = QPen(QColor(color.red(), color.green(), color.blue(), alpha))
        pen.setWidth(width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(x, y, w, h, radius, radius)

    def is_active(self) -> bool:
        return True  # BreathingPulse never stops


class CarouselSlide:
    """Content slides left/right with fade for carousel navigation.

    Extracted from ``ChallengeSelectOverlay`` slide logic.
    """

    def __init__(self, duration: float = 180.0):
        self._duration = float(duration)
        self._elapsed: float = 0.0
        self._t: float = 0.0
        self._direction: int = 1   # 1 = right, -1 = left
        self._active: bool = False

    @property
    def direction(self) -> int:
        return self._direction

    def start(self, direction: int = 1):
        """Start slide in the given direction (1=right, -1=left)."""
        self._direction = int(direction)
        self._elapsed = 0.0
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        """Advance slide elapsed time."""
        if self._active:
            self._elapsed += dt_ms
            self._t = min(1.0, self._elapsed / max(1.0, self._duration))
            if self._t >= 1.0:
                self._active = False

    def get_t(self) -> float:
        """Return raw progress (0.0–1.0)."""
        return self._t

    def get_eased_t(self) -> float:
        """Return ease-out-cubic progress (0.0–1.0)."""
        return ease_out_cubic(self._t)

    def draw(self, painter: QPainter, *args, **kwargs):
        """CarouselSlide provides values via :meth:`get_eased_t`."""
        pass

    def is_active(self) -> bool:
        return self._active


class SnapScale:
    """Brief scale pulse (1.0→1.07→1.0) with flash on selection change.

    Extracted from ``FlipDifficultyOverlay`` snap pulse logic.
    """

    def __init__(self, duration: float = 160.0, scale_amount: float = 0.07):
        self._duration = float(duration)
        self._scale_amount = float(scale_amount)
        self._elapsed: float = 0.0
        self._active: bool = False
        self._prev_selected: int = -1

    def start(self, prev_selected: int = -1):
        """Reset and activate snap scale."""
        self._elapsed = 0.0
        self._active = True
        self._prev_selected = int(prev_selected)

    def tick(self, dt_ms: float):
        """Advance snap elapsed time."""
        if self._active:
            self._elapsed += dt_ms
            if self._elapsed >= self._duration:
                self._elapsed = self._duration
                self._active = False

    def get_scale(self, is_selected: bool) -> float:
        """Return scale factor for the selected item."""
        if not self._active or not is_selected:
            return 1.0
        t = min(1.0, self._elapsed / max(1.0, self._duration))
        return 1.0 + self._scale_amount * max(0.0, 1.0 - abs(t - 0.3) / 0.3)

    def get_flash_alpha(self, is_selected: bool) -> int:
        """Return flash overlay alpha for the selected item."""
        if not self._active or not is_selected:
            return 0
        t = min(1.0, self._elapsed / max(1.0, self._duration))
        return int(120 * max(0.0, 1.0 - t * 2.0))

    def get_prev_fade_alpha(self, item_idx: int) -> int:
        """Return fade alpha for the previously selected item."""
        if not self._active or item_idx != self._prev_selected:
            return 0
        t = min(1.0, self._elapsed / max(1.0, self._duration))
        return int(80 * max(0.0, 1.0 - t * 2.0))

    def draw(self, painter: QPainter, *args, **kwargs):
        """SnapScale provides values via getters."""
        pass

    def is_active(self) -> bool:
        return self._active


class HeatPulse:
    """Warning/critical pulsating border for the heat barometer.

    Extracted from ``HeatBarometerOverlay`` pulse logic.
    """

    def __init__(self, warning_color: QColor = None, critical_color: QColor = None,
                 threshold: int = 65):
        self._warning_color  = warning_color  if warning_color  is not None else QColor(255, 140, 0)
        self._critical_color = critical_color if critical_color is not None else QColor(255, 40,  0)
        self._threshold = int(threshold)
        self._t: float = 0.0
        self._active: bool = False

    def start(self):
        """Reset pulse phase and activate."""
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float = 40.0):
        """Advance pulse phase."""
        self._t = (self._t + 0.1) % 1.0

    def draw(self, painter: QPainter, x: int, y: int, w: int, h: int,
             heat: int, low_perf: bool = False):
        """Draw the pulsating border based on *heat* level.

        In low-performance mode a static red border is drawn only at critical
        heat (>85 %) to match the original behaviour.
        """
        if heat < self._threshold:
            return
        if low_perf:
            if heat > 85:
                pulse_pen = QPen(QColor(255, 60, 0, 200))
                pulse_pen.setWidth(3)
                painter.setPen(pulse_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(x, y, w, h, 10, 10)
            return
        amp = 0.5 + 0.5 * math.sin(2 * math.pi * self._t)
        if heat > 85:
            pulse_alpha = int(180 + 60 * amp)
            pulse_width = 2 + int(2 * amp)
            pulse_color = QColor(self._critical_color.red(),
                                 self._critical_color.green(),
                                 self._critical_color.blue(),
                                 min(255, pulse_alpha))
        else:
            pulse_alpha = int(120 + 40 * amp)
            pulse_width = 2
            pulse_color = QColor(self._warning_color.red(),
                                 self._warning_color.green(),
                                 self._warning_color.blue(),
                                 min(255, pulse_alpha))
        pulse_pen = QPen(pulse_color)
        pulse_pen.setWidth(pulse_width)
        painter.setPen(pulse_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(x, y, w, h, 10, 10)

    def is_active(self) -> bool:
        return self._active


class ScanIn:
    """Slide-in with opacity ramp using ease-out-cubic.

    Extracted from ``StatusOverlay`` scan-in logic.
    """

    def __init__(self, duration: float = 220.0, distance: int = 30):
        self._duration = float(duration)
        self._distance = int(distance)
        self._elapsed: float = 0.0
        self._active: bool = False

    def start(self):
        """Reset and activate scan-in."""
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        """Advance scan-in elapsed time."""
        if self._active:
            self._elapsed += dt_ms
            if self._elapsed >= self._duration:
                self._elapsed = self._duration
                self._active = False

    def get_offset_and_opacity(self) -> tuple:
        """Return ``(x_offset, opacity)`` for the current scan-in frame."""
        t = min(1.0, self._elapsed / max(1.0, self._duration))
        eased = ease_out_cubic(t)
        offset = int(self._distance * (1.0 - eased))
        opacity = max(0.0, min(1.0, eased))
        return offset, opacity

    def draw(self, painter: QPainter, *args, **kwargs):
        """ScanIn provides values via :meth:`get_offset_and_opacity`."""
        pass

    def is_active(self) -> bool:
        return self._active


class GlowSweep:
    """Horizontal glow line sweeping across a widget after scan-in.

    Extracted from ``StatusOverlay`` glow sweep logic.
    """

    def __init__(self, duration: float = 350.0):
        self._duration = float(duration)
        self._elapsed: float = 0.0
        self._active: bool = False

    def start(self):
        """Reset and activate sweep."""
        self._elapsed = 0.0
        self._active = True

    def stop(self):
        """Deactivate sweep without resetting elapsed."""
        self._active = False

    def tick(self, dt_ms: float):
        """Advance sweep elapsed time."""
        if self._active:
            self._elapsed += dt_ms
            if self._elapsed >= self._duration:
                self._elapsed = self._duration
                self._active = False

    def draw(self, painter: QPainter, w: int, h: int, radius: int, color: QColor):
        """Draw the sweeping glow line if active."""
        if not self._active:
            return
        sweep_t = min(1.0, self._elapsed / max(1.0, self._duration))
        sweep_x = int(sweep_t * (w + 60)) - 30
        sweep_alpha = int(160 * max(0.0, 1.0 - abs(sweep_t - 0.5) * 3.0))
        if sweep_alpha > 0:
            grad = QLinearGradient(float(sweep_x - 20), 0.0, float(sweep_x + 20), 0.0)
            grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 0))
            grad.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), sweep_alpha))
            grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setBrush(grad)
            painter.drawRoundedRect(0, 0, w, h, radius, radius)

    def is_active(self) -> bool:
        return self._active


class ColorMorph:
    """Smooth RGB interpolation between two colors over time.

    Extracted from ``StatusOverlay`` color morph logic.
    """

    def __init__(self, duration: float = 200.0):
        self._duration = float(duration)
        self._elapsed: float = 0.0
        self._from_color: str = "#00C853"
        self._target_color: str = "#00C853"
        self._from_text: str = ""
        self._target_text: str = ""
        self._current_color: str = "#00C853"
        self._active: bool = False

    def start(self, from_color: str, to_color: str,
              from_text: str = "", to_text: str = ""):
        """Start morphing from *from_color* to *to_color*."""
        self._from_color = str(from_color)
        self._target_color = str(to_color)
        self._from_text = str(from_text)
        self._target_text = str(to_text)
        self._current_color = str(from_color)
        self._elapsed = 0.0
        self._active = True

    def stop(self):
        """Deactivate morph without resetting the current color."""
        self._active = False

    def tick(self, dt_ms: float):
        """Advance morph and update the current interpolated color."""
        if not self._active:
            return
        self._elapsed += dt_ms
        t = min(1.0, self._elapsed / max(1.0, self._duration))
        fc = QColor(self._from_color)
        tc = QColor(self._target_color)
        r = int(fc.red()   + (tc.red()   - fc.red())   * t)
        g = int(fc.green() + (tc.green() - fc.green()) * t)
        b = int(fc.blue()  + (tc.blue()  - fc.blue())  * t)
        self._current_color = f"#{r:02X}{g:02X}{b:02X}"
        if t >= 1.0:
            self._active = False
            self._current_color = self._target_color

    def current_color(self) -> str:
        """Return the current interpolated color as a hex string."""
        return self._current_color

    def current_text(self) -> str:
        """Return the target text (shown immediately for readability)."""
        return self._target_text if self._target_text else self._from_text

    def draw(self, painter: QPainter, *args, **kwargs):
        """ColorMorph provides values via :meth:`current_color`."""
        pass

    def is_active(self) -> bool:
        return self._active


class GlitchFrame:
    """Slices an image into horizontal strips with random offsets.

    Extracted from ``OverlayWindow._draw_glitch_frame``.
    """

    def __init__(self, strip_count_range: tuple = (4, 6),
                 offset_range: tuple = (-15, 15)):
        self._strip_count_range = strip_count_range
        self._offset_range = offset_range

    def start(self):
        """No-op – GlitchFrame is stateless."""
        pass

    def tick(self, dt_ms: float):
        """No-op – GlitchFrame is stateless."""
        pass

    def draw(self, source_img: QImage, label) -> None:
        """Apply glitch effect to *source_img* and display the result on *label*."""
        W = source_img.width()
        H = source_img.height()
        glitched = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        glitched.fill(Qt.GlobalColor.transparent)
        p = QPainter(glitched)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        try:
            n_strips = random.randint(self._strip_count_range[0],
                                      self._strip_count_range[1])
            strip_h = max(1, H // n_strips)
            for i in range(n_strips):
                y0 = i * strip_h
                y1 = min(H, y0 + strip_h)
                sh = y1 - y0
                if sh <= 0:
                    continue
                offset_x = random.randint(self._offset_range[0],
                                          self._offset_range[1])
                strip = source_img.copy(0, y0, W, sh)
                p.drawImage(offset_x, y0, strip)
        finally:
            try:
                p.end()
            except Exception:
                pass
        label.setPixmap(QPixmap.fromImage(glitched))

    def is_active(self) -> bool:
        return False  # GlitchFrame is stateless
