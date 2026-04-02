"""gl_effects_opengl.py – New GPU-ready visual effect classes.

30 new effect primitives added by the ✨ Effects tab feature.  Each class
follows the same public API as the primitives in ``gl_effects.py``:

    start()              – (re-)initialise and begin the effect
    tick(dt_ms: float)   – advance state by *dt_ms* milliseconds
    draw(painter, rect)  – render onto *painter* inside *rect* (QRect)
    is_active() -> bool  – True while the effect has frames remaining

All classes accept an ``intensity`` parameter (0.0 – 1.0) that scales the
visual output (particle count, alpha, amplitude, etc.).

Architecture note
-----------------
The ``_HAS_OPENGL`` flag mirrors the one in ``gl_effects.py``.  When
PyOpenGL and PyQt6.QtOpenGLWidgets are available, classes may switch to a
GPU code-path.  The current implementations use QPainter (CPU fallback)
that is correct on all platforms without additional dependencies.
"""
from __future__ import annotations

import math
import random

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen, QBrush

_HAS_OPENGL = False
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget  # noqa: F401
    from OpenGL.GL import *                           # noqa: F401, F403
    _HAS_OPENGL = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


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


# ===========================================================================
# Challenge Select – 5 new effects
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

    def stop(self):
        self._active = False


# ===========================================================================
# Timer / Countdown – 6 new effects
# ===========================================================================

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
        alpha = _clamp(int(30 * self.intensity), 0, 50)
        painter.save()
        painter.setBrush(QBrush(QColor(255, 50, 50, alpha)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)
        painter.restore()

    def is_active(self) -> bool:
        return self._active

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
