"""gl_effects_opengl.py – GPU-ready visual effect classes.

All effect primitives share a common public API:

    start()              – (re-)initialise and begin the effect
    tick(dt_ms: float)   – advance state by *dt_ms* milliseconds
    draw(painter, rect)  – render onto *painter* inside *rect* (QRect)
    is_active() -> bool  – True while the effect has frames remaining

All classes accept an ``intensity`` parameter (0.0 – 1.0) that scales the
visual output (particle count, alpha, amplitude, etc.).
"""
from __future__ import annotations

import math
import random

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient,
    QPainter, QPen, QPixmap,
)
from PyQt6.QtWidgets import QWidget

from theme import get_theme, get_theme_color, DEFAULT_THEME

_HAS_OPENGL = False
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # noqa: F401
    from OpenGL.GL import (
        GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, GL_COMPILE_STATUS, GL_LINK_STATUS,
        GL_POINTS, GL_LINES, GL_LINE_STRIP, GL_TRIANGLES, GL_TRIANGLE_FAN,
        GL_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA, GL_BLEND,
        GL_DEPTH_TEST,
        glCreateShader, glShaderSource, glCompileShader, glGetShaderiv,
        glGetShaderInfoLog, glCreateProgram, glAttachShader, glLinkProgram,
        glDeleteShader, glGetProgramiv, glGetProgramInfoLog,
        glUseProgram, glGetUniformLocation, glUniform1f, glUniform2f,
        glUniform4f, glUniform1i,
        glBegin, glEnd, glVertex2f, glColor4f, glPointSize, glLineWidth,
        glEnable, glDisable, glBlendFunc, glClearColor,
        glViewport, glMatrixMode, glLoadIdentity, glOrtho,
        GL_PROJECTION, GL_MODELVIEW,
        glEnableClientState, glDisableClientState, GL_VERTEX_ARRAY,
        glVertexPointer, glDrawArrays, GL_FLOAT,
    )
    _HAS_OPENGL = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ---------------------------------------------------------------------------
# OpenGL shader infrastructure (only used when _HAS_OPENGL = True)
# ---------------------------------------------------------------------------

def _compile_shader(source: str, shader_type):
    shader = glCreateShader(shader_type)
    glShaderSource(shader, source)
    glCompileShader(shader)
    if not glGetShaderiv(shader, GL_COMPILE_STATUS):
        raise RuntimeError(glGetShaderInfoLog(shader).decode())
    return shader


def _link_program(vertex_src: str, fragment_src: str):
    vs = _compile_shader(vertex_src, GL_VERTEX_SHADER)
    fs = _compile_shader(fragment_src, GL_FRAGMENT_SHADER)
    prog = glCreateProgram()
    glAttachShader(prog, vs)
    glAttachShader(prog, fs)
    glLinkProgram(prog)
    glDeleteShader(vs)
    glDeleteShader(fs)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        raise RuntimeError(glGetProgramInfoLog(prog).decode())
    return prog


# Number of line segments used to approximate a circle in GL ring effects.
_GL_CIRCLE_SEGMENTS = 64

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

        from gl_effects_opengl import EffectsWidget as OverlayEffectsWidget
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

        from gl_effects_opengl import ShineWidget as _OverlayShineWidget
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

        from gl_effects_opengl import HighlightWidget as _OverlayHighlightWidget
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
# ===========================================================================
# Achievement Toast – 4 new effects
# ===========================================================================

class GodRayBurst:
    """Radial light rays emanating from the centre of the widget on unlock."""

    _DURATION_MS = 800

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._rays: list[dict] = []

    def start(self):
        n = max(4, int(10 * self.intensity))
        self._rays = [
            {
                "angle": random.uniform(0, 2 * math.pi),
                "length": random.uniform(0.3, 0.9),
                "width": random.uniform(4, 12) * self.intensity,
                "alpha": random.randint(80, 180),
            }
            for _ in range(n)
        ]
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = rect.center().x(), rect.center().y()
        max_r = max(rect.width(), rect.height()) * 0.7
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for ray in self._rays:
            length = ray["length"] * t * max_r
            dx = math.cos(ray["angle"]) * length
            dy = math.sin(ray["angle"]) * length
            alpha = int(ray["alpha"] * fade * self.intensity)
            color = QColor(255, 220, 100, _clamp(alpha, 0, 255))
            pen = QPen(color)
            pen.setWidthF(ray["width"] * fade)
            painter.setPen(pen)
            painter.drawLine(cx, cy, int(cx + dx), int(cy + dy))
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = rect.center().x(), rect.center().y()
        max_r = max(rect.width(), rect.height()) * 0.7
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glPointSize(4.0)
        glBegin(GL_POINTS)
        for ray in self._rays:
            length = ray["length"] * t * max_r
            dx = math.cos(ray["angle"]) * length
            dy = math.sin(ray["angle"]) * length
            alpha = ray["alpha"] * fade * self.intensity / 255.0
            glColor4f(1.0, 0.86, 0.39, _clamp(alpha, 0.0, 1.0))
            glVertex2f(cx + dx, cy + dy)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)



class ConfettiShower:
    """Colorful falling confetti particles."""

    _DURATION_MS = 2500
    _COLORS = [
        QColor("#FF4444"), QColor("#FFD700"), QColor("#00E5FF"),
        QColor("#FF7F00"), QColor("#00FF88"), QColor("#FF69B4"),
        QColor("#AA44FF"),
    ]

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._pieces: list[dict] = []

    def start(self):
        n = max(5, int(30 * self.intensity))
        self._pieces = [
            {
                "x": random.uniform(0.05, 0.95),
                "y": random.uniform(-0.2, 0.0),
                "vx": random.uniform(-0.05, 0.05),
                "vy": random.uniform(0.1, 0.35),
                "rot": random.uniform(0, 360),
                "vrot": random.uniform(-180, 180),
                "w": random.uniform(6, 14) * self.intensity,
                "h": random.uniform(4, 8) * self.intensity,
                "color": random.choice(self._COLORS),
            }
            for _ in range(n)
        ]
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        dt_s = dt_ms / 1000.0
        for p in self._pieces:
            p["x"] += p["vx"] * dt_s
            p["y"] += p["vy"] * dt_s
            p["rot"] += p["vrot"] * dt_s
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - max(0.0, (t - 0.7) / 0.3)
        W, H = rect.width(), rect.height()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for p in self._pieces:
            if p["y"] > 1.1:
                continue
            alpha = _clamp(int(200 * fade), 0, 255)
            color = QColor(p["color"].red(), p["color"].green(), p["color"].blue(), alpha)
            cx = rect.left() + int(p["x"] * W)
            cy = rect.top() + int(p["y"] * H)
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(p["rot"])
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(-p["w"] / 2), int(-p["h"] / 2), int(p["w"]), int(p["h"]))
            painter.restore()
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - max(0.0, (t - 0.7) / 0.3)
        W, H = rect.width(), rect.height()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glPointSize(5.0)
        glBegin(GL_POINTS)
        for p in self._pieces:
            if p["y"] > 1.1:
                continue
            alpha = _clamp(200 * fade * self.intensity, 0.0, 255.0) / 255.0
            c = p["color"]
            glColor4f(c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0,
                      _clamp(alpha, 0.0, 1.0))
            px = rect.left() + p["x"] * W
            py = rect.top() + p["y"] * H
            glVertex2f(float(px), float(py))
        glEnd()



class HologramFlicker:
    """Rapid opacity flicker with horizontal scan lines on the toast icon area."""

    _DURATION_MS = 1200

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._next_flip = 0.0
        self._on = True

    def start(self):
        self._elapsed = 0.0
        self._on = True
        self._next_flip = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        self._next_flip -= dt_ms
        if self._next_flip <= 0:
            self._on = not self._on
            interval_ms = random.uniform(40, 120) / max(0.1, self.intensity)
            self._next_flip = interval_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        if not self._on:
            return
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(int(80 * fade * self.intensity), 0, 255)
        scan_color = QColor(0, 229, 255, alpha)
        painter.save()
        painter.setPen(QPen(scan_color, 1))
        step = max(2, int(6 / max(0.1, self.intensity)))
        y = rect.top()
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += step
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        if not self._on:
            return
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(fade * self.intensity * 0.31, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glLineWidth(1.0)
        step = max(2, int(6 / max(0.1, self.intensity)))
        glBegin(GL_LINES)
        y = float(rect.top())
        while y < rect.bottom():
            glColor4f(0.0, 0.9, 1.0, alpha)
            glVertex2f(float(rect.left()), y)
            glVertex2f(float(rect.right()), y)
            y += step
        glEnd()



class ShockwaveRipple:
    """Expanding distortion ring from the centre of the widget."""

    _DURATION_MS = 700

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False

    def start(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = rect.center().x(), rect.center().y()
        max_r = max(rect.width(), rect.height()) * 0.6 * self.intensity
        radius = int(t * max_r)
        thickness = max(1, int(8 * fade * self.intensity))
        alpha = _clamp(int(220 * fade), 0, 255)
        color = QColor(0, 229, 255, alpha)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color, thickness)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = float(rect.center().x()), float(rect.center().y())
        max_r = max(rect.width(), rect.height()) * 0.6 * self.intensity
        radius = t * max_r
        alpha = _clamp(fade, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glLineWidth(max(1.0, 8.0 * fade * self.intensity))
        N = _GL_CIRCLE_SEGMENTS
        glBegin(GL_LINE_STRIP)
        for i in range(N + 1):
            angle = 2 * math.pi * i / N
            glColor4f(0.0, 0.9, 1.0, alpha)
            glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)



# ===========================================================================
# Challenge Select – 6 effects (5 GPU-tier + 1 base)
# ===========================================================================

class ElectricArc:
    """Animated lightning bolt between two points."""

    _DURATION_MS = 600

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._segments: list[tuple[int, int]] = []
        self._next_regen = 0.0

    def start(self):
        self._elapsed = 0.0
        self._active = True
        self._next_regen = 0.0
        self._segments = []

    def _regen(self, rect: QRect):
        n = max(3, int(8 * self.intensity))
        x0, y0 = rect.left() + 10, rect.top() + rect.height() // 3
        x1, y1 = rect.right() - 10, rect.bottom() - rect.height() // 3
        pts = [(x0, y0)]
        for i in range(1, n):
            frac = i / n
            mx = int(x0 + (x1 - x0) * frac)
            my = int(y0 + (y1 - y0) * frac + random.randint(-20, 20))
            pts.append((mx, my))
        pts.append((x1, y1))
        self._segments = pts

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        self._next_regen -= dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        if self._next_regen <= 0:
            self._regen(rect)
            self._next_regen = 60.0
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(int(200 * fade * self.intensity), 0, 255)
        color = QColor(160, 120, 255, alpha)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color, max(1, int(2 * self.intensity)))
        painter.setPen(pen)
        for i in range(len(self._segments) - 1):
            x0, y0 = self._segments[i]
            x1, y1 = self._segments[i + 1]
            painter.drawLine(x0, y0, x1, y1)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        if not self._segments:
            return
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(fade * self.intensity, 0.0, 1.0)
        glLineWidth(max(1.0, 2.0 * self.intensity))
        glBegin(GL_LINES)
        for i in range(len(self._segments) - 1):
            x0, y0 = self._segments[i]
            x1, y1 = self._segments[i + 1]
            glColor4f(0.63, 0.47, 1.0, alpha)
            glVertex2f(float(x0), float(y0))
            glVertex2f(float(x1), float(y1))
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)



class HoverShimmer:
    """Subtle horizontal shimmer on a highlighted region."""

    _DURATION_MS = 500

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False

    def start(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        # Shimmer sweeps left to right
        sweep_x = rect.left() + int(t * rect.width())
        fade = 1.0 - t
        alpha = _clamp(int(120 * fade * self.intensity), 0, 255)
        grad = QLinearGradient(sweep_x - 30, 0, sweep_x + 30, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, QColor(255, 255, 255, alpha))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.save()
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(fade * self.intensity * 0.47, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(1.0, 1.0, 1.0, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()



class PlasmaNoise:
    """Animated plasma-like background that cycles over time."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms / 1000.0

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        alpha = _clamp(int(40 * self.intensity), 0, 60)
        val = 0.5 + 0.5 * math.sin(self._t * 2.0)
        r = int(20 + 60 * val)
        g = int(0 + 40 * (1 - val))
        b = int(60 + 120 * val)
        painter.save()
        painter.setBrush(QBrush(QColor(r, g, b, alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        val = 0.5 + 0.5 * math.sin(self._t * 2.0)
        r = (20 + 60 * val) / 255.0
        g = (0 + 40 * (1 - val)) / 255.0
        b = (60 + 120 * val) / 255.0
        alpha = _clamp(40 * self.intensity / 255.0, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(r, g, b, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()


    def stop(self):
        self._active = False


class HoloSweep:
    """Holographic colour sweep across title text area."""

    _DURATION_MS = 900

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False

    def start(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        sweep_x = rect.left() + int(t * rect.width())
        alpha = _clamp(int(160 * fade * self.intensity), 0, 255)
        painter.save()
        painter.setClipRect(rect)
        grad = QLinearGradient(sweep_x - 20, 0, sweep_x + 20, 0)
        grad.setColorAt(0.0, QColor(0, 229, 255, 0))
        grad.setColorAt(0.5, QColor(180, 100, 255, alpha))
        grad.setColorAt(1.0, QColor(0, 229, 255, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(fade * self.intensity * 0.63, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(0.71, 0.39, 1.0, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()



class DifficultyColorPulse:
    """Colour pulse that matches the challenge difficulty level."""

    def __init__(self, intensity: float = 1.0, color: QColor = None):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._color = color or QColor("#FF7F00")
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms / 1000.0

    def set_color(self, color: QColor):
        self._color = color

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        amp = 0.5 + 0.5 * math.sin(self._t * 4.0)
        alpha = _clamp(int(60 * amp * self.intensity), 0, 80)
        c = self._color
        painter.save()
        painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        amp = 0.5 + 0.5 * math.sin(self._t * 4.0)
        alpha = _clamp(60 * amp * self.intensity / 255.0, 0.0, 1.0)
        c = self._color
        r, g, b = c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(r, g, b, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()


    def stop(self):
        self._active = False


class ArrowWobblePulse:
    """Sinusoidal wobble applied to navigation arrows, emphasising the
    current selection direction."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms * 0.003

    @property
    def offset_x(self) -> float:
        """Horizontal displacement in pixels for the arrow widget."""
        if not self._active:
            return 0.0
        return math.sin(self._t * math.pi * 2.0) * 4.0 * self.intensity

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        # Draw a faint direction hint using a translucent chevron tint
        alpha = int(18 * abs(math.sin(self._t * math.pi * 2.0)) * self.intensity)
        alpha = _clamp(alpha, 0, 40)
        painter.save()
        painter.setBrush(QBrush(QColor(255, 200, 50, alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        alpha = _clamp(
            18 * abs(math.sin(self._t * math.pi * 2.0)) * self.intensity / 255.0,
            0.0, 1.0,
        )
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(1.0, 0.78, 0.2, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()


    def stop(self):
        self._active = False


# ===========================================================================
# Timer / Countdown – 8 effects (6 GPU-tier + 2 base)
# ===========================================================================

class CountdownScaleGlow:
    """3-2-1-GO scale-up + glow burst for each countdown digit."""

    _DURATION_MS = 500

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        """Call once per countdown digit change."""
        self._elapsed = 0.0
        self._active = True

    def start(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    @property
    def scale(self) -> float:
        """Scale factor to apply to the digit widget (1.0 = normal)."""
        if not self._active:
            return 1.0
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        # Quick grow then settle
        if t < 0.3:
            return 1.0 + 0.35 * (t / 0.3) * self.intensity
        return 1.0 + 0.35 * (1.0 - (t - 0.3) / 0.7) * self.intensity

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = max(0.0, 1.0 - t)
        alpha = int(80 * fade * self.intensity)
        alpha = _clamp(alpha, 0, 120)
        painter.save()
        painter.setBrush(QBrush(QColor(255, 255, 150, alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = max(0.0, 1.0 - t)
        alpha = _clamp(80 * fade * self.intensity / 255.0, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(1.0, 1.0, 0.59, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()



class RadialPulseBackground:
    """Expanding translucent ring drawn over the timer background,
    reinforcing the countdown urgency with a slow radial pulse."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms * 0.0015

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        cx = rect.left() + rect.width() // 2
        cy = rect.top() + rect.height() // 2
        # Two offset rings for depth
        for phase in (0.0, 0.5):
            t = (self._t + phase) % 1.0
            radius = int((min(rect.width(), rect.height()) * 0.5) * t)
            alpha = int(40 * (1.0 - t) * self.intensity)
            alpha = _clamp(alpha, 0, 60)
            if radius > 0 and alpha > 0:
                pen = QPen(QColor(200, 100, 255, alpha))
                pen.setWidth(2)
                painter.save()
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
                painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        cx, cy = float(rect.center().x()), float(rect.center().y())
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        N = _GL_CIRCLE_SEGMENTS
        for phase in (0.0, 0.5):
            t = (self._t + phase) % 1.0
            max_r = min(rect.width(), rect.height()) * 0.5 * self.intensity
            radius = t * max_r
            alpha = _clamp((1.0 - t) * self.intensity * 0.24, 0.0, 1.0)
            glLineWidth(2.0)
            glBegin(GL_LINE_STRIP)
            for i in range(N + 1):
                angle = 2 * math.pi * i / N
                glColor4f(0.78, 0.39, 1.0, alpha)
                glVertex2f(cx + radius * math.cos(angle),
                           cy + radius * math.sin(angle))
            glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


    def stop(self):
        self._active = False


class UrgencyShake:
    """Screen shake effect that activates in the last few seconds."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._t = 0.0
        self._active = False
        self._offset_x = 0
        self._offset_y = 0
        self._next_shake = 0.0

    def start(self):
        self._t = 0.0
        self._offset_x = 0
        self._offset_y = 0
        self._next_shake = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms
        self._next_shake -= dt_ms
        if self._next_shake <= 0:
            amp = int(6 * self.intensity)
            self._offset_x = random.randint(-amp, amp)
            self._offset_y = random.randint(-amp, amp)
            self._next_shake = 80.0

    @property
    def shake_offset(self) -> tuple[int, int]:
        return (self._offset_x, self._offset_y)

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        alpha = _clamp(int(30 * self.intensity), 0, 50)
        painter.save()
        painter.setBrush(QBrush(QColor(255, 50, 50, alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        alpha = _clamp(30 * self.intensity, 0.0, 50.0) / 255.0
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(1.0, 0.2, 0.2, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()


    def stop(self):
        self._active = False


class TimeWarpDistortion:
    """Wavy distortion overlay representing time running low."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms / 1000.0

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        W, H = rect.width(), rect.height()
        alpha = _clamp(int(50 * self.intensity), 0, 80)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(0, 200, 255, alpha), 1)
        painter.setPen(pen)
        num_lines = max(3, int(8 * self.intensity))
        for i in range(num_lines):
            y_base = rect.top() + int((i + 0.5) * H / num_lines)
            pts = []
            for x in range(rect.left(), rect.right(), 4):
                phase = (x / W) * 2 * math.pi + self._t * 3 + i
                y_off = int(math.sin(phase) * 4 * self.intensity)
                pts.append((x, y_base + y_off))
            for j in range(len(pts) - 1):
                painter.drawLine(pts[j][0], pts[j][1], pts[j + 1][0], pts[j + 1][1])
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        alpha = _clamp(50 * self.intensity / 255.0, 0.0, 1.0)
        W, H = rect.width(), rect.height()
        num_lines = max(3, int(8 * self.intensity))
        glLineWidth(1.0)
        for i in range(num_lines):
            y_base = rect.top() + (i + 0.5) * H / num_lines
            glColor4f(0.0, 0.78, 1.0, alpha)
            glBegin(GL_LINE_STRIP)
            x = rect.left()
            while x < rect.right():
                phase = (x / max(1, W)) * 2 * math.pi + self._t * 3 + i
                y_off = math.sin(phase) * 4 * self.intensity
                glVertex2f(float(x), float(y_base + y_off))
                x += 4
            glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


    def stop(self):
        self._active = False


class TrailAfterimage:
    """Fading afterimage that trails behind a changing number."""

    _DURATION_MS = 400

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._center_x = 0
        self._center_y = 0

    def trigger(self, cx: int, cy: int):
        self._center_x = cx
        self._center_y = cy
        self._elapsed = 0.0
        self._active = True

    def start(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx = self._center_x or rect.center().x()
        cy = self._center_y or rect.center().y()
        for i in range(3):
            scale = 1.0 + i * 0.15
            offset_y = int(i * 8 * t * self.intensity)
            r = int(30 * scale * self.intensity)
            alpha = _clamp(int(80 * fade / (i + 1)), 0, 100)
            painter.save()
            painter.setBrush(QBrush(QColor(0, 229, 255, alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - r, cy - r + offset_y, r * 2, r * 2)
            painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx = float(self._center_x or rect.center().x())
        cy = float(self._center_y or rect.center().y())
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        N = 32
        for i in range(3):
            scale = 1.0 + i * 0.15
            offset_y = i * 8 * t * self.intensity
            radius = 30 * scale * self.intensity
            alpha = _clamp(80 * fade / (i + 1) / 255.0, 0.0, 1.0)
            glBegin(GL_LINE_STRIP)
            for k in range(N + 1):
                angle = 2 * math.pi * k / N
                glColor4f(0.0, 0.9, 1.0, alpha)
                glVertex2f(cx + radius * math.cos(angle),
                           cy + offset_y + radius * math.sin(angle))
            glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)



class FinalExplosion:
    """Particle burst at the moment the countdown hits zero."""

    _DURATION_MS = 1000

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._particles: list[dict] = []

    def start(self):
        n = max(8, int(25 * self.intensity))
        self._particles = [
            {
                "angle": random.uniform(0, 2 * math.pi),
                "speed": random.uniform(0.05, 0.3) * self.intensity,
                "size": random.uniform(4, 10) * self.intensity,
                "color": random.choice([
                    QColor("#FF4444"), QColor("#FFD700"),
                    QColor("#00E5FF"), QColor("#FF7F00"),
                ]),
                "alpha": random.randint(150, 255),
            }
            for _ in range(n)
        ]
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = rect.center().x(), rect.center().y()
        max_r = max(rect.width(), rect.height()) * 0.5
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for p in self._particles:
            dist = t * max_r * p["speed"] / 0.15
            px = cx + int(math.cos(p["angle"]) * dist)
            py = cy + int(math.sin(p["angle"]) * dist)
            alpha = _clamp(int(p["alpha"] * fade), 0, 255)
            c = p["color"]
            painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            sz = int(p["size"] * (1.0 - t * 0.5))
            painter.drawEllipse(px - sz // 2, py - sz // 2, sz, sz)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = float(rect.center().x()), float(rect.center().y())
        max_r = max(rect.width(), rect.height()) * 0.5
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glPointSize(4.0)
        glBegin(GL_POINTS)
        for p in self._particles:
            dist = t * max_r * p["speed"] / 0.15
            px = cx + math.cos(p["angle"]) * dist
            py = cy + math.sin(p["angle"]) * dist
            alpha = _clamp(p["alpha"] * fade / 255.0, 0.0, 1.0)
            c = p["color"]
            glColor4f(c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0, alpha)
            glVertex2f(px, py)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)



class PulseRingCountdown:
    """A ring that contracts once per second in sync with the countdown."""

    _DURATION_MS = 800

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    def start(self):
        self.trigger()

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        # Ring starts large and contracts
        max_r = max(rect.width(), rect.height()) // 2
        radius = int(max_r * (1.0 - t * 0.8))
        cx, cy = rect.center().x(), rect.center().y()
        alpha = _clamp(int(200 * fade * self.intensity), 0, 255)
        thickness = max(1, int(4 * fade * self.intensity))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(0, 229, 255, alpha), thickness))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        max_r = max(rect.width(), rect.height()) // 2
        radius = float(max_r * (1.0 - t * 0.8))
        cx, cy = float(rect.center().x()), float(rect.center().y())
        alpha = _clamp(fade * self.intensity, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glLineWidth(max(1.0, 8.0 * fade * self.intensity))
        N = _GL_CIRCLE_SEGMENTS
        glBegin(GL_LINE_STRIP)
        for i in range(N + 1):
            angle = 2 * math.pi * i / N
            glColor4f(0.0, 0.9, 1.0, alpha)
            glVertex2f(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)



class GlitchNumbers:
    """Digital glitch effect on number transitions."""

    _DURATION_MS = 300

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._strips: list[dict] = []
        self._next_regen = 0.0

    def start(self):
        self._elapsed = 0.0
        self._active = True
        self._next_regen = 0.0

    def _regen(self, rect: QRect):
        n = max(2, int(5 * self.intensity))
        H = rect.height()
        self._strips = [
            {
                "y": random.randint(rect.top(), rect.bottom() - 4),
                "h": random.randint(2, max(2, int(10 * self.intensity))),
                "offset": random.randint(-10, 10),
                "alpha": random.randint(100, 200),
            }
            for _ in range(n)
        ]

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        self._next_regen -= dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        if self._next_regen <= 0:
            self._regen(rect)
            self._next_regen = 50.0
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        painter.save()
        painter.setClipRect(rect)
        for s in self._strips:
            alpha = _clamp(int(s["alpha"] * fade * self.intensity), 0, 255)
            painter.setBrush(QBrush(QColor(0, 229, 255, alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(
                rect.left() + s["offset"], s["y"],
                rect.width(), s["h"]
            )
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        if not self._strips:
            return
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        for s in self._strips:
            alpha = _clamp(s["alpha"] * fade * self.intensity / 255.0, 0.0, 1.0)
            y0 = float(s["y"])
            y1 = float(s["y"] + s["h"])
            x0 = float(rect.left() + s["offset"])
            x1 = float(rect.right() + s["offset"])
            glBegin(GL_TRIANGLE_FAN)
            glColor4f(0.0, 0.9, 1.0, alpha)
            glVertex2f(x0, y0)
            glVertex2f(x1, y0)
            glVertex2f(x1, y1)
            glVertex2f(x0, y1)
            glEnd()



# ===========================================================================
# Heat Barometer – 6 new effects
# ===========================================================================

class FlameParticles:
    """Rising flame particles from the bottom of the heat bar."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False
        self._particles: list[dict] = []
        self._t = 0.0
        self._spawn_acc = 0.0

    def start(self):
        self._particles = []
        self._t = 0.0
        self._spawn_acc = 0.0
        self._active = True

    def _spawn(self, rect: QRect):
        return {
            "x": random.uniform(rect.left(), rect.right()),
            "y": float(rect.bottom()),
            "vx": random.uniform(-8, 8) * self.intensity,
            "vy": random.uniform(-40, -20) * self.intensity,
            "life": 1.0,
            "size": random.uniform(4, 10) * self.intensity,
        }

    def tick(self, dt_ms: float):
        if not self._active:
            return
        dt_s = dt_ms / 1000.0
        self._t += dt_s
        self._spawn_acc += dt_ms
        spawn_interval = max(50, int(150 / max(0.1, self.intensity)))
        for p in self._particles:
            p["x"] += p["vx"] * dt_s
            p["y"] += p["vy"] * dt_s
            p["life"] -= dt_s * 1.5
        self._particles = [p for p in self._particles if p["life"] > 0]
        if self._spawn_acc >= spawn_interval:
            self._spawn_acc = 0
            # Stored rect not available here; spawn deferred to draw()
            self._do_spawn = True

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        if getattr(self, "_do_spawn", False):
            self._particles.append(self._spawn(rect))
            self._do_spawn = False
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for p in self._particles:
            life = p["life"]
            r = _clamp(int(255), 0, 255)
            g = _clamp(int(100 * life), 0, 255)
            b = 0
            alpha = _clamp(int(200 * life * self.intensity), 0, 255)
            painter.setBrush(QBrush(QColor(r, g, b, alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            sz = int(p["size"] * life)
            painter.drawEllipse(int(p["x"]) - sz // 2, int(p["y"]) - sz // 2, sz, sz)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glPointSize(5.0)
        glBegin(GL_POINTS)
        for p in self._particles:
            life = p["life"]
            g = _clamp(100 * life / 255.0, 0.0, 1.0)
            alpha = _clamp(200 * life * self.intensity / 255.0, 0.0, 1.0)
            glColor4f(1.0, g, 0.0, alpha)
            glVertex2f(float(p["x"]), float(p["y"]))
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


    def stop(self):
        self._active = False


class HeatShimmer:
    """Wavy heat distortion overlay."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms / 1000.0

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        alpha = _clamp(int(25 * self.intensity), 0, 40)
        W, H = rect.width(), rect.height()
        painter.save()
        pen = QPen(QColor(255, 180, 60, alpha), 1)
        painter.setPen(pen)
        num_lines = max(2, int(5 * self.intensity))
        for i in range(num_lines):
            y_base = rect.top() + int((i + 0.5) * H / num_lines)
            prev = None
            for x in range(rect.left(), rect.right(), 3):
                phase = (x / max(1, W)) * 3 * math.pi + self._t * 5 + i * 1.2
                y_off = int(math.sin(phase) * 3 * self.intensity)
                pt = (x, y_base + y_off)
                if prev:
                    painter.drawLine(prev[0], prev[1], pt[0], pt[1])
                prev = pt
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        alpha = _clamp(25 * self.intensity / 255.0, 0.0, 1.0)
        W, H = rect.width(), rect.height()
        num_lines = max(2, int(5 * self.intensity))
        glLineWidth(1.0)
        for i in range(num_lines):
            y_base = rect.top() + (i + 0.5) * H / num_lines
            glColor4f(1.0, 0.71, 0.24, alpha)
            glBegin(GL_LINE_STRIP)
            x = rect.left()
            while x < rect.right():
                phase = (x / max(1, W)) * 3 * math.pi + self._t * 5 + i * 1.2
                y_off = math.sin(phase) * 3 * self.intensity
                glVertex2f(float(x), float(y_base + y_off))
                x += 3
            glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


    def stop(self):
        self._active = False


class SmokeWisps:
    """Wispy smoke particles drifting upward at the edges."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False
        self._particles: list[dict] = []
        self._spawn_acc = 0.0

    def start(self):
        self._particles = []
        self._spawn_acc = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        dt_s = dt_ms / 1000.0
        self._spawn_acc += dt_ms
        for p in self._particles:
            p["x"] += p["vx"] * dt_s
            p["y"] += p["vy"] * dt_s
            p["life"] -= dt_s * 0.8
            p["size"] *= 1.01
        self._particles = [p for p in self._particles if p["life"] > 0]
        spawn_interval = max(120, int(300 / max(0.1, self.intensity)))
        self._do_spawn = self._spawn_acc >= spawn_interval
        if self._do_spawn:
            self._spawn_acc = 0

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        if getattr(self, "_do_spawn", False):
            side = random.choice([rect.left() + 5, rect.right() - 5])
            self._particles.append({
                "x": float(side),
                "y": float(rect.bottom() - 5),
                "vx": random.uniform(-5, 5),
                "vy": random.uniform(-20, -10) * self.intensity,
                "life": 1.0,
                "size": random.uniform(6, 14) * self.intensity,
            })
            self._do_spawn = False
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for p in self._particles:
            alpha = _clamp(int(80 * p["life"] * self.intensity), 0, 100)
            painter.setBrush(QBrush(QColor(180, 180, 180, alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            sz = int(p["size"])
            painter.drawEllipse(int(p["x"]) - sz // 2, int(p["y"]) - sz // 2, sz, sz)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glPointSize(8.0)
        glBegin(GL_POINTS)
        for p in self._particles:
            alpha = _clamp(80 * p["life"] * self.intensity / 255.0, 0.0, 1.0)
            glColor4f(0.71, 0.71, 0.71, alpha)
            glVertex2f(float(p["x"]), float(p["y"]))
        glEnd()


    def stop(self):
        self._active = False


class LavaGlowEdge:
    """Glowing lava-like edge effect around the heat bar widget."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms / 1000.0

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        amp = 0.5 + 0.5 * math.sin(self._t * 3.0)
        alpha = _clamp(int((80 + 100 * amp) * self.intensity), 0, 200)
        r = _clamp(int(255), 0, 255)
        g = _clamp(int(60 + 80 * amp), 0, 255)
        b = 0
        color = QColor(r, g, b, alpha)
        layers = max(1, int(3 * self.intensity))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i in range(layers, 0, -1):
            a = alpha // i
            pen = QPen(QColor(r, g, b, _clamp(a, 0, 255)), i * 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                rect.left() + i, rect.top() + i,
                rect.width() - 2 * i, rect.height() - 2 * i,
                8, 8
            )
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        amp = 0.5 + 0.5 * math.sin(self._t * 3.0)
        alpha = _clamp((80 + 100 * amp) * self.intensity / 255.0, 0.0, 1.0)
        g_val = (60 + 80 * amp) / 255.0
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glLineWidth(4.0)
        x = float(rect.left())
        y = float(rect.top())
        w = float(rect.width())
        h = float(rect.height())
        N = _GL_CIRCLE_SEGMENTS
        glBegin(GL_LINE_STRIP)
        for i in range(N + 1):
            angle = 2 * math.pi * i / N
            cx = x + w / 2 + (w / 2) * math.cos(angle)
            cy = y + h / 2 + (h / 2) * math.sin(angle)
            glColor4f(1.0, _clamp(g_val, 0.0, 1.0), 0.0, alpha)
            glVertex2f(cx, cy)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


    def stop(self):
        self._active = False


class NumberThrob:
    """Temperature number scale pulse matching the heat level."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms / 1000.0

    @property
    def scale(self) -> float:
        """Returns a scale factor (0.97–1.06) for the number display."""
        if not self._active:
            return 1.0
        pulse = 0.5 + 0.5 * math.sin(self._t * 6.0)
        return 1.0 + 0.06 * pulse * self.intensity

    def draw(self, painter: QPainter, rect: QRect):
        pass  # Effect applied externally via .scale property

    def is_active(self) -> bool:
        return self._active

    def stop(self):
        self._active = False


class MeltdownShake:
    """Violent shake at 90 %+ heat."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False
        self._ox = 0
        self._oy = 0
        self._next_shake = 0.0

    def start(self):
        self._ox = 0
        self._oy = 0
        self._next_shake = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._next_shake -= dt_ms
        if self._next_shake <= 0:
            amp = int(8 * self.intensity)
            self._ox = random.randint(-amp, amp)
            self._oy = random.randint(-amp, amp)
            self._next_shake = 50.0

    @property
    def shake_offset(self) -> tuple[int, int]:
        return (self._ox, self._oy)

    def draw(self, painter: QPainter, rect: QRect):
        alpha = _clamp(int(20 * self.intensity), 0, 40)
        painter.save()
        painter.setBrush(QBrush(QColor(255, 30, 30, alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        alpha = _clamp(20 * self.intensity, 0.0, 35.0) / 255.0
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(1.0, 0.12, 0.12, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()


    def stop(self):
        self._active = False


# ===========================================================================
# Flip Counter – 6 new effects
# ===========================================================================

class FlipImpactPulse:
    """Brief flash / shake on each flip event."""

    _DURATION_MS = 250

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    def start(self):
        self.trigger()

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(int(120 * fade * self.intensity), 0, 180)
        painter.save()
        painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(120 * fade * self.intensity / 255.0, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(1.0, 1.0, 1.0, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()



class NumberCascade:
    """Digits rolling like a slot machine on counter change."""

    _DURATION_MS = 400
    _DIGITS = "0123456789"

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    def start(self):
        self.trigger()

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    @property
    def cascade_char(self) -> str:
        """Returns a random digit to display during the cascade."""
        return random.choice(self._DIGITS)

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(int(100 * fade * self.intensity), 0, 150)
        painter.save()
        painter.setOpacity(alpha / 255.0)
        painter.setPen(QPen(QColor(0, 229, 255)))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.cascade_char)
        painter.setOpacity(1.0)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        alpha = _clamp(100 * fade * self.intensity / 255.0, 0.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(0.0, 0.9, 1.0, alpha)
        glVertex2f(float(rect.left()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.top()))
        glVertex2f(float(rect.right()), float(rect.bottom()))
        glVertex2f(float(rect.left()), float(rect.bottom()))
        glEnd()



class MilestoneBurst:
    """Particle burst at 25 %, 50 %, 75 % milestones."""

    _DURATION_MS = 800

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._particles: list[dict] = []

    def trigger(self, rect: QRect = None):
        n = max(6, int(20 * self.intensity))
        self._particles = [
            {
                "angle": random.uniform(0, 2 * math.pi),
                "speed": random.uniform(0.1, 0.5) * self.intensity,
                "size": random.uniform(3, 8) * self.intensity,
                "color": random.choice([
                    QColor("#FFD700"), QColor("#FF7F00"), QColor("#00E5FF"),
                ]),
            }
            for _ in range(n)
        ]
        self._elapsed = 0.0
        self._active = True

    def start(self):
        self.trigger()

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = rect.center().x(), rect.center().y()
        max_r = max(rect.width(), rect.height()) * 0.4
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for p in self._particles:
            dist = t * max_r * p["speed"] / 0.2
            px = cx + int(math.cos(p["angle"]) * dist)
            py = cy + int(math.sin(p["angle"]) * dist)
            alpha = _clamp(int(200 * fade), 0, 255)
            c = p["color"]
            painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            sz = int(p["size"])
            painter.drawEllipse(px - sz // 2, py - sz // 2, sz, sz)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = float(rect.center().x()), float(rect.center().y())
        max_r = max(rect.width(), rect.height()) * 0.4
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glPointSize(4.0)
        glBegin(GL_POINTS)
        for p in self._particles:
            dist = t * max_r * p["speed"] / 0.2
            px = cx + math.cos(p["angle"]) * dist
            py = cy + math.sin(p["angle"]) * dist
            alpha = _clamp(200 * fade / 255.0, 0.0, 1.0)
            c = p["color"]
            glColor4f(c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0, alpha)
            glVertex2f(px, py)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)



class ElectricSpark:
    """Spark effect on counter increment."""

    _DURATION_MS = 300

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._sparks: list[dict] = []

    def trigger(self):
        n = max(3, int(8 * self.intensity))
        self._sparks = [
            {
                "angle": random.uniform(0, 2 * math.pi),
                "speed": random.uniform(0.05, 0.25) * self.intensity,
                "alpha": random.randint(150, 255),
            }
            for _ in range(n)
        ]
        self._elapsed = 0.0
        self._active = True

    def start(self):
        self.trigger()

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = rect.center().x(), rect.center().y()
        max_r = max(rect.width(), rect.height()) * 0.3
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for s in self._sparks:
            dist = t * max_r * s["speed"] / 0.12
            ex = cx + int(math.cos(s["angle"]) * dist)
            ey = cy + int(math.sin(s["angle"]) * dist)
            alpha = _clamp(int(s["alpha"] * fade), 0, 255)
            painter.setPen(QPen(QColor(200, 180, 255, alpha), max(1, int(2 * self.intensity))))
            painter.drawLine(cx, cy, ex, ey)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        t = _clamp(self._elapsed / self._DURATION_MS, 0.0, 1.0)
        fade = 1.0 - t
        cx, cy = float(rect.center().x()), float(rect.center().y())
        max_r = max(rect.width(), rect.height()) * 0.3
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glLineWidth(max(1.0, 2.0 * self.intensity))
        glBegin(GL_LINES)
        for s in self._sparks:
            dist = t * max_r * s["speed"] / 0.12
            ex = cx + math.cos(s["angle"]) * dist
            ey = cy + math.sin(s["angle"]) * dist
            alpha = _clamp(s["alpha"] * fade / 255.0, 0.0, 1.0)
            glColor4f(0.78, 0.71, 1.0, alpha)
            glVertex2f(cx, cy)
            glVertex2f(ex, ey)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)



class GoalProximityGlow:
    """Glow that intensifies as the flip count approaches the goal."""

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._proximity = 0.0  # 0.0 = far, 1.0 = at goal
        self._t = 0.0
        self._active = False

    def start(self):
        self._t = 0.0
        self._active = True

    def set_proximity(self, value: float):
        """Set how close count is to goal (0.0–1.0)."""
        self._proximity = _clamp(value, 0.0, 1.0)

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._t += dt_ms / 1000.0

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        pulse = 0.5 + 0.5 * math.sin(self._t * (2 + self._proximity * 6))
        alpha = _clamp(int(80 * pulse * self._proximity * self.intensity), 0, 120)
        r = int(255)
        g = int(200 * (1 - self._proximity))
        b = int(50 * (1 - self._proximity))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        layers = max(1, int(3 * self.intensity))
        for i in range(layers, 0, -1):
            layer_alpha = alpha // i
            pen = QPen(QColor(r, g, b, _clamp(layer_alpha, 0, 255)), i * 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                rect.left() + i, rect.top() + i,
                rect.width() - 2 * i, rect.height() - 2 * i,
                10, 10
            )
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        pulse = 0.5 + 0.5 * math.sin(self._t * (2 + self._proximity * 6))
        alpha = _clamp(80 * pulse * self._proximity * self.intensity / 255.0, 0.0, 1.0)
        r = 1.0
        g = (200 * (1 - self._proximity)) / 255.0
        b = (50 * (1 - self._proximity)) / 255.0
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glLineWidth(4.0)
        x = float(rect.left())
        y = float(rect.top())
        w = float(rect.width())
        h = float(rect.height())
        N = _GL_CIRCLE_SEGMENTS
        glBegin(GL_LINE_STRIP)
        for i in range(N + 1):
            angle = 2 * math.pi * i / N
            cx = x + w / 2 + (w / 2) * math.cos(angle)
            cy = y + h / 2 + (h / 2) * math.sin(angle)
            glColor4f(r, _clamp(g, 0.0, 1.0), _clamp(b, 0.0, 1.0), alpha)
            glVertex2f(cx, cy)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


    def stop(self):
        self._active = False


class CompletionFirework:
    """Firework particles when goal is reached."""

    _DURATION_MS = 1500

    def __init__(self, intensity: float = 1.0):
        self.intensity = _clamp(intensity, 0.0, 1.0)
        self._elapsed = 0.0
        self._active = False
        self._bursts: list[dict] = []

    def start(self):
        self._elapsed = 0.0
        self._bursts = []
        n_bursts = max(2, int(4 * self.intensity))
        for _ in range(n_bursts):
            n_p = max(8, int(20 * self.intensity))
            color = random.choice([
                QColor("#FFD700"), QColor("#FF4444"), QColor("#00E5FF"),
                QColor("#FF7F00"), QColor("#FF69B4"),
            ])
            self._bursts.append({
                "cx_frac": random.uniform(0.2, 0.8),
                "cy_frac": random.uniform(0.2, 0.8),
                "delay_ms": random.uniform(0, 600),
                "color": color,
                "particles": [
                    {
                        "angle": random.uniform(0, 2 * math.pi),
                        "speed": random.uniform(0.15, 0.5) * self.intensity,
                    }
                    for _ in range(n_p)
                ],
            })
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._elapsed += dt_ms
        if self._elapsed >= self._DURATION_MS:
            self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        W, H = rect.width(), rect.height()
        max_r = max(W, H) * 0.4
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for burst in self._bursts:
            burst_t = self._elapsed - burst["delay_ms"]
            if burst_t <= 0:
                continue
            t = _clamp(burst_t / (self._DURATION_MS - burst["delay_ms"]), 0.0, 1.0)
            fade = 1.0 - t
            cx = rect.left() + int(burst["cx_frac"] * W)
            cy = rect.top() + int(burst["cy_frac"] * H)
            c = burst["color"]
            for p in burst["particles"]:
                dist = t * max_r * p["speed"] / 0.3
                px = cx + int(math.cos(p["angle"]) * dist)
                py = cy + int(math.sin(p["angle"]) * dist)
                alpha = _clamp(int(220 * fade), 0, 255)
                painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), alpha)))
                painter.setPen(Qt.PenStyle.NoPen)
                sz = max(2, int(5 * fade * self.intensity))
                painter.drawEllipse(px - sz // 2, py - sz // 2, sz, sz)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

    def _draw_gl(self, rect: QRect):
        W, H = rect.width(), rect.height()
        max_r = max(W, H) * 0.4
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_DEPTH_TEST)
        glPointSize(4.0)
        glBegin(GL_POINTS)
        for burst in self._bursts:
            burst_t = self._elapsed - burst["delay_ms"]
            if burst_t <= 0:
                continue
            t = _clamp(burst_t / (self._DURATION_MS - burst["delay_ms"]), 0.0, 1.0)
            fade = 1.0 - t
            cx = float(rect.left() + burst["cx_frac"] * W)
            cy = float(rect.top() + burst["cy_frac"] * H)
            c = burst["color"]
            for p in burst["particles"]:
                dist = t * max_r * p["speed"] / 0.3
                px = cx + math.cos(p["angle"]) * dist
                py = cy + math.sin(p["angle"]) * dist
                alpha = _clamp(220 * fade / 255.0, 0.0, 1.0)
                glColor4f(c.red() / 255.0, c.green() / 255.0, c.blue() / 255.0, alpha)
                glVertex2f(px, py)
        glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

