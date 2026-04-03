"""post_processing.py – Screen-space post-processing effect classes.

All effect primitives share a common public API:

    start()              – (re-)initialise and begin the effect
    tick(dt_ms: float)   – advance state by *dt_ms* milliseconds
    draw(painter, rect)  – render onto *painter* inside *rect* (QRect)
    is_active() -> bool  – True while the effect is running

All classes accept an ``intensity`` parameter (0.0 – 1.0) that scales the
visual output (alpha, line count, grain density, etc.).

Effects gracefully fall back to a QPainter-based implementation when
PyOpenGL is not available.
"""
from __future__ import annotations

import math
import random

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QPainter, QPen, QRadialGradient,
)

_HAS_OPENGL = False
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # noqa: F401
    from OpenGL.GL import (
        GL_LINES, GL_POINTS, GL_TRIANGLE_FAN,
        GL_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA, GL_BLEND,
        GL_DEPTH_TEST,
        glBegin, glEnd, glVertex2f, glColor4f, glPointSize, glLineWidth,
        glEnable, glDisable, glBlendFunc,
        glViewport, glMatrixMode, glLoadIdentity, glOrtho,
        GL_PROJECTION, GL_MODELVIEW,
    )
    _HAS_OPENGL = True
except ImportError:
    pass


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ===========================================================================
# 1. PostBloom – light bleed around bright/neon areas
# ===========================================================================

class PostBloom:
    """Simulates light bleed around bright/neon areas.

    QPainter fallback: draws multiple semi-transparent expanding rounded
    rectangles over the widget area in an additive-style blend.

    GL path: uses additive blending (GL_ONE) to paint a blurred glow layer
    over the widget rect.
    """

    def __init__(self, intensity: float = 0.6):
        self._intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False
        self._time_ms = 0.0

    def set_intensity(self, intensity: float):
        self._intensity = _clamp(intensity, 0.0, 1.0)

    def start(self):
        self._time_ms = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._time_ms += dt_ms

    def is_active(self) -> bool:
        return self._active

    def stop(self):
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
        self._draw_qpainter(painter, rect)

    def _draw_qpainter(self, painter: QPainter, rect: QRect):
        alpha_base = int(self._intensity * 120)
        pulse = math.sin(self._time_ms * 0.002) * 0.3 + 0.7
        layers = max(2, int(self._intensity * 5))
        old_mode = painter.compositionMode()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        for i in range(layers):
            expand = (i + 1) * int(self._intensity * 12)
            alpha = max(0, int(alpha_base * pulse * (1.0 - i / layers)))
            color = QColor(180, 140, 255, alpha)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                rect.adjusted(-expand, -expand, expand, expand),
                12 + expand, 12 + expand,
            )
        painter.setCompositionMode(old_mode)

    def _draw_gl(self, rect: QRect):
        w, h = rect.width(), rect.height()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_ONE, GL_ONE)
        glDisable(GL_DEPTH_TEST)

        pulse = math.sin(self._time_ms * 0.002) * 0.3 + 0.7
        alpha = float(self._intensity * 0.25 * pulse)
        glColor4f(0.7, 0.55, 1.0, alpha)

        layers = max(2, int(self._intensity * 4))
        for i in range(layers):
            expand = (i + 1) * self._intensity * 15
            x0 = -expand
            y0 = -expand
            x1 = w + expand
            y1 = h + expand
            glBegin(GL_TRIANGLE_FAN)
            glVertex2f(w / 2, h / 2)
            for seg in range(33):
                angle = seg * 2 * math.pi / 32
                cx = (w / 2) + (w / 2 + expand) * math.cos(angle)
                cy = (h / 2) + (h / 2 + expand) * math.sin(angle)
                glVertex2f(cx, cy)
            glEnd()

        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


# ===========================================================================
# 2. PostMotionBlur – directional blur/trail to simulate motion
# ===========================================================================

class PostMotionBlur:
    """Applies a directional blur/trail to simulate motion.

    QPainter fallback: draws 3–5 semi-transparent copies of the rect offset
    in the velocity direction, fading out.

    GL path: renders offset quads with decreasing alpha using standard
    alpha blending.
    """

    def __init__(self, intensity: float = 0.6):
        self._intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False
        self._vx = 1.0
        self._vy = 0.0

    def set_intensity(self, intensity: float):
        self._intensity = _clamp(intensity, 0.0, 1.0)

    def set_velocity(self, vx: float, vy: float):
        """Set blur direction and magnitude."""
        self._vx = vx
        self._vy = vy

    def start(self):
        self._active = True

    def tick(self, dt_ms: float):
        pass  # Stateless — redraws based on current velocity each frame

    def is_active(self) -> bool:
        return self._active

    def stop(self):
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
        self._draw_qpainter(painter, rect)

    def _draw_qpainter(self, painter: QPainter, rect: QRect):
        steps = max(3, int(self._intensity * 5))
        step_dist = self._intensity * 10
        old_mode = painter.compositionMode()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        for i in range(steps, 0, -1):
            offset_x = int(-self._vx * step_dist * i / steps)
            offset_y = int(-self._vy * step_dist * i / steps)
            alpha = int(self._intensity * 90 * (1.0 - i / (steps + 1)))
            color = QColor(200, 200, 255, alpha)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect.adjusted(offset_x, offset_y, offset_x, offset_y))
        painter.setCompositionMode(old_mode)

    def _draw_gl(self, rect: QRect):
        w, h = rect.width(), rect.height()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)

        steps = max(3, int(self._intensity * 5))
        step_dist = self._intensity * 10
        for i in range(steps, 0, -1):
            ox = -self._vx * step_dist * i / steps
            oy = -self._vy * step_dist * i / steps
            alpha = float(self._intensity * 0.35 * (1.0 - i / (steps + 1)))
            glColor4f(0.8, 0.8, 1.0, alpha)
            glBegin(GL_TRIANGLE_FAN)
            glVertex2f(ox, oy)
            glVertex2f(w + ox, oy)
            glVertex2f(w + ox, h + oy)
            glVertex2f(ox, h + oy)
            glEnd()


# ===========================================================================
# 3. PostChromaticAberration – offset R/G/B channels for lens/glitch look
# ===========================================================================

class PostChromaticAberration:
    """Offsets the R/G/B channels slightly to simulate lens distortion/glitch.

    QPainter fallback: draws 3 colored semi-transparent rects offset by a
    few pixels (red left, blue right, green centered).

    GL path: draws three colored quads with channel offsets.
    """

    def __init__(self, intensity: float = 0.5):
        self._intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False
        self._time_ms = 0.0

    def set_intensity(self, intensity: float):
        self._intensity = _clamp(intensity, 0.0, 1.0)

    def start(self):
        self._time_ms = 0.0
        self._active = True

    def tick(self, dt_ms: float):
        if not self._active:
            return
        self._time_ms += dt_ms

    def is_active(self) -> bool:
        return self._active

    def stop(self):
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
        self._draw_qpainter(painter, rect)

    def _draw_qpainter(self, painter: QPainter, rect: QRect):
        offset = max(1, int(self._intensity * 6))
        alpha = int(self._intensity * 100)
        old_mode = painter.compositionMode()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        painter.setPen(Qt.PenStyle.NoPen)
        # Red channel – shifted left
        painter.setBrush(QBrush(QColor(255, 0, 0, alpha)))
        painter.drawRect(rect.adjusted(-offset, 0, -offset, 0))
        # Blue channel – shifted right
        painter.setBrush(QBrush(QColor(0, 0, 255, alpha)))
        painter.drawRect(rect.adjusted(offset, 0, offset, 0))
        # Green channel – centered (subtle)
        painter.setBrush(QBrush(QColor(0, 255, 0, alpha // 2)))
        painter.drawRect(rect)
        painter.setCompositionMode(old_mode)

    def _draw_gl(self, rect: QRect):
        w, h = rect.width(), rect.height()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)

        offset = self._intensity * 6.0
        alpha = float(self._intensity * 0.4)

        # Red quad – shifted left
        glColor4f(1.0, 0.0, 0.0, alpha)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(-offset, 0)
        glVertex2f(w - offset, 0)
        glVertex2f(w - offset, h)
        glVertex2f(-offset, h)
        glEnd()

        # Blue quad – shifted right
        glColor4f(0.0, 0.0, 1.0, alpha)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(offset, 0)
        glVertex2f(w + offset, 0)
        glVertex2f(w + offset, h)
        glVertex2f(offset, h)
        glEnd()

        # Green quad – centered, half alpha
        glColor4f(0.0, 1.0, 0.0, alpha * 0.5)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(0, 0)
        glVertex2f(w, 0)
        glVertex2f(w, h)
        glVertex2f(0, h)
        glEnd()


# ===========================================================================
# 4. PostVignette – darkens edges of the widget
# ===========================================================================

class PostVignette:
    """Darkens the edges of the widget, drawing focus to the center.

    QPainter fallback: uses a QRadialGradient from transparent center to
    dark semi-transparent edges.

    GL path: renders a dark GL_TRIANGLE_FAN that is transparent at center
    and opaque at edges.
    """

    def __init__(self, intensity: float = 0.6):
        self._intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False

    def set_intensity(self, intensity: float):
        self._intensity = _clamp(intensity, 0.0, 1.0)

    def start(self):
        self._active = True

    def tick(self, dt_ms: float):
        pass  # Static effect — no animation needed

    def is_active(self) -> bool:
        return self._active

    def stop(self):
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
        self._draw_qpainter(painter, rect)

    def _draw_qpainter(self, painter: QPainter, rect: QRect):
        cx = rect.x() + rect.width() / 2
        cy = rect.y() + rect.height() / 2
        radius = max(rect.width(), rect.height()) * 0.75

        gradient = QRadialGradient(cx, cy, radius)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        edge_alpha = int(self._intensity * 180)
        gradient.setColorAt(1.0, QColor(0, 0, 0, edge_alpha))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRect(rect)

    def _draw_gl(self, rect: QRect):
        w, h = rect.width(), rect.height()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)

        cx, cy = w / 2, h / 2
        edge_alpha = float(self._intensity * 0.7)
        segments = 48

        glBegin(GL_TRIANGLE_FAN)
        glColor4f(0.0, 0.0, 0.0, 0.0)  # Center: transparent
        glVertex2f(cx, cy)
        radius_x = w * 0.75
        radius_y = h * 0.75
        for i in range(segments + 1):
            angle = i * 2 * math.pi / segments
            x = cx + radius_x * math.cos(angle)
            y = cy + radius_y * math.sin(angle)
            glColor4f(0.0, 0.0, 0.0, edge_alpha)
            glVertex2f(x, y)
        glEnd()


# ===========================================================================
# 5. PostFilmGrain – random noise/grain for analog film or CRT look
# ===========================================================================

class PostFilmGrain:
    """Adds random noise/grain to simulate analog film or old CRT monitors.

    QPainter fallback: draws many small semi-transparent random-colored dots
    scattered across the rect.

    GL path: uses GL_POINTS with random positions each frame.
    """

    def __init__(self, intensity: float = 0.4):
        self._intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False
        self._points: list[tuple[float, float, int]] = []  # (x_frac, y_frac, alpha 0-255)

    def set_intensity(self, intensity: float):
        self._intensity = _clamp(intensity, 0.0, 1.0)

    def start(self):
        self._active = True
        self._regenerate_points()

    def tick(self, dt_ms: float):
        """Regenerate grain positions each tick for animated noise."""
        if not self._active:
            return
        self._regenerate_points()

    def _regenerate_points(self):
        """Generate random grain point positions as (x_frac, y_frac, alpha) tuples.

        Positions are stored as fractions (0.0–1.0) so they scale correctly
        to any widget rect size at draw time.
        """
        count = max(50, int(self._intensity * 1200))
        self._points = [
            (random.random(), random.random(), random.randint(40, 140))
            for _ in range(count)
        ]

    def is_active(self) -> bool:
        return self._active

    def stop(self):
        self._active = False

    def draw(self, painter: QPainter, rect: QRect):
        if not self._active:
            return
        # Regenerate each frame for animated noise
        self._regenerate_points()
        if _HAS_OPENGL:
            try:
                self._draw_gl(rect)
                return
            except Exception:
                pass
        self._draw_qpainter(painter, rect)

    def _draw_qpainter(self, painter: QPainter, rect: QRect):
        x0, y0, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        painter.setPen(Qt.PenStyle.NoPen)
        for xf, yf, a in self._points:
            brightness = random.randint(180, 255)
            c = QColor(brightness, brightness, brightness, int(a * self._intensity))
            painter.setBrush(QBrush(c))
            px = x0 + int(xf * w)
            py = y0 + int(yf * h)
            painter.drawRect(px, py, 1, 1)

    def _draw_gl(self, rect: QRect):
        w, h = rect.width(), rect.height()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glPointSize(1.0)

        glBegin(GL_POINTS)
        for xf, yf, a in self._points:
            brightness = random.uniform(0.7, 1.0)
            alpha = float(a / 255.0 * self._intensity)
            glColor4f(brightness, brightness, brightness, alpha)
            glVertex2f(xf * w, yf * h)
        glEnd()


# ===========================================================================
# 6. PostScanlines – horizontal CRT scanlines
# ===========================================================================

class PostScanlines:
    """Draws horizontal semi-transparent lines across the widget to simulate
    a CRT monitor.

    QPainter fallback: draws horizontal lines every N pixels using QPen.

    GL path: uses GL_LINES to draw horizontal lines across the rect.

    Line spacing scales inversely with intensity (more lines = higher
    intensity).
    """

    def __init__(self, intensity: float = 0.5):
        self._intensity = _clamp(intensity, 0.0, 1.0)
        self._active = False

    def set_intensity(self, intensity: float):
        self._intensity = _clamp(intensity, 0.0, 1.0)

    def start(self):
        self._active = True

    def tick(self, dt_ms: float):
        pass  # Static pattern — no animation needed

    def is_active(self) -> bool:
        return self._active

    def stop(self):
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
        self._draw_qpainter(painter, rect)

    def _line_spacing(self) -> int:
        """Return pixel spacing between scanlines (fewer pixels = more lines)."""
        # intensity 0→1 maps to spacing 8→2
        return max(2, int(8 - self._intensity * 6))

    def _draw_qpainter(self, painter: QPainter, rect: QRect):
        alpha = int(self._intensity * 90)
        spacing = self._line_spacing()
        pen = QPen(QColor(0, 0, 0, alpha))
        pen.setWidth(1)
        painter.setPen(pen)
        x0, y0 = rect.x(), rect.y()
        x1 = rect.x() + rect.width()
        y_max = rect.y() + rect.height()
        y = y0
        while y < y_max:
            painter.drawLine(x0, y, x1, y)
            y += spacing

    def _draw_gl(self, rect: QRect):
        w, h = rect.width(), rect.height()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)
        glLineWidth(1.0)

        alpha = float(self._intensity * 0.35)
        spacing = self._line_spacing()
        glColor4f(0.0, 0.0, 0.0, alpha)
        glBegin(GL_LINES)
        y = 0
        while y < h:
            glVertex2f(0, y)
            glVertex2f(w, y)
            y += spacing
        glEnd()
