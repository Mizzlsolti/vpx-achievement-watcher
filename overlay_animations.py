"""
overlay_animations.py – Centralised animation classes for VPX Achievement Watcher overlays.

All classes follow the BaseEffect interface:
  tick(dt)          – advance state by dt milliseconds
  paint(painter, rect) – render into a QRect using a QPainter
  reset()           – reset to initial state
"""

import math
import random

try:
    from PyQt6.QtCore import Qt, QPointF, QRectF
    from PyQt6.QtGui import (
        QColor, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient,
        QFont, QFontMetrics,
    )
    from PyQt6.QtWidgets import QWidget
except ImportError:
    pass


# ---------------------------------------------------------------------------
# AnimConfig — reads animation enable flags from cfg
# ---------------------------------------------------------------------------

class AnimConfig:
    @staticmethod
    def is_low_perf(cfg) -> bool:
        try:
            return bool(cfg.OVERLAY.get("low_performance_mode", False))
        except Exception:
            return False

    @staticmethod
    def is_enabled(cfg, key: str, default: bool = True) -> bool:
        if AnimConfig.is_low_perf(cfg):
            return False
        try:
            return bool(cfg.OVERLAY.get(key, default))
        except Exception:
            return default


# ---------------------------------------------------------------------------
# BaseEffect
# ---------------------------------------------------------------------------

class BaseEffect:
    def tick(self, dt: float):
        """Advance animation state by dt milliseconds."""
        pass

    def paint(self, painter, rect):
        """Paint the effect using the given QPainter into the given QRect."""
        pass

    def reset(self):
        """Reset animation to initial state."""
        pass

    def is_portrait(self, cfg) -> bool:
        try:
            return bool(cfg.OVERLAY.get("portrait_mode", False))
        except Exception:
            return False


# ===========================================================================
# ── Main Overlay effects ────────────────────────────────────────────────────
# ===========================================================================

class GlowBorderEffect(BaseEffect):
    """Breathing glow border + particle system (extracted from OverlayEffectsWidget)."""

    def __init__(self, color="#00E5FF", portrait: bool = False):
        self._color = QColor(color)
        self._portrait = portrait
        self._phase = 0.0
        self._particles = []
        self._init_particles()

    def _init_particles(self):
        self._particles = [self._make_particle() for _ in range(18)]

    def _make_particle(self):
        return {
            "x": random.uniform(0.0, 1.0),
            "y": random.uniform(0.0, 1.0),
            "vx": random.uniform(-0.0003, 0.0003),
            "vy": random.uniform(-0.0003, 0.0003),
            "life": random.uniform(0.2, 1.0),
            "max_life": random.uniform(0.8, 2.0),
            "size": random.uniform(2.0, 5.0),
        }

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.002) % (2 * math.pi)
        new_particles = []
        for p in self._particles:
            p["life"] -= dt * 0.001
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            if p["life"] > 0:
                new_particles.append(p)
            else:
                new_particles.append(self._make_particle())
        self._particles = new_particles

    def paint(self, painter, rect):
        alpha = int(80 + 60 * math.sin(self._phase))
        c = QColor(self._color)
        c.setAlpha(alpha)
        pen = QPen(c, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 10, 10)

        w, h = rect.width(), rect.height()
        for p in self._particles:
            px = rect.x() + p["x"] * w
            py = rect.y() + p["y"] * h
            life_ratio = max(0.0, p["life"] / p["max_life"])
            pc = QColor(self._color)
            pc.setAlpha(int(life_ratio * 180))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(pc))
            r = p["size"] * life_ratio
            painter.drawEllipse(QPointF(px, py), r, r)

    def reset(self):
        self._phase = 0.0
        self._init_particles()


class SlideTransitionEffect(BaseEffect):
    """Slide+fade page transition (extracted from OverlayWindow)."""

    DURATION = 300.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False
        self._direction = 1  # +1 = slide left, -1 = slide right

    def start(self, direction: int = 1):
        self._elapsed = 0.0
        self._active = True
        self._direction = direction

    @property
    def active(self) -> bool:
        return self._active

    @property
    def progress(self) -> float:
        return min(1.0, self._elapsed / self.DURATION)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        t = self.progress
        alpha = int((1.0 - t) * 120)
        offset = int(self._direction * (1.0 - t) * rect.width() * 0.15)
        c = QColor(0, 0, 0, alpha)
        painter.fillRect(rect.translated(offset, 0), c)

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class ScoreSpinEffect(BaseEffect):
    """Score counter spin animation (extracted from OverlayWindow)."""

    DURATION = 600.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False
        self._display = 0
        self._target = 0

    def start(self, start_val: int, target_val: int):
        self._display = start_val
        self._target = target_val
        self._elapsed = 0.0
        self._active = True

    @property
    def value(self) -> int:
        return self._display

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        t = min(1.0, self._elapsed / self.DURATION)
        self._display = int(self._display + (self._target - self._display) * t * 0.15)
        if abs(self._display - self._target) < 1:
            self._display = self._target
            self._active = False

    def paint(self, painter, rect):
        pass  # Score rendering is done by the overlay widget itself

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class ProgressBarShimmerEffect(BaseEffect):
    """Shine sweep over progress bar (extracted from OverlayWindow._ShineWidget)."""

    DURATION = 600.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        t = min(1.0, self._elapsed / self.DURATION)
        cx = rect.x() + int(t * rect.width())
        grad = QLinearGradient(cx - 30, 0, cx + 30, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, QColor(255, 255, 255, 90))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(rect), grad)

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class HighlightsScrollEffect(BaseEffect):
    """Highlights auto-scroll (extracted from OverlayWindow p2_timer logic)."""

    INTERVAL = 3000.0

    def __init__(self):
        self._elapsed = 0.0
        self._tick_count = 0

    def tick(self, dt: float):
        self._elapsed += dt
        if self._elapsed >= self.INTERVAL:
            self._elapsed = 0.0
            self._tick_count += 1

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._elapsed = 0.0
        self._tick_count = 0


# ── Toast effects ────────────────────────────────────────────────────────────

class ToastBurstEffect(BaseEffect):
    """Burst particle animation on toast appear (extracted from AchToastWindow)."""

    DURATION = 800.0

    def __init__(self, color="#FF7F00"):
        self._color = QColor(color)
        self._active = False
        self._elapsed = 0.0
        self._particles = []

    def trigger(self, origin_x: float, origin_y: float):
        self._active = True
        self._elapsed = 0.0
        self._particles = []
        for _ in range(20):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(30, 120)
            self._particles.append({
                "x": origin_x,
                "y": origin_y,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "life": 1.0,
                "size": random.uniform(3, 7),
            })

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        decay = dt / self.DURATION
        for p in self._particles:
            p["life"] -= decay
            p["x"] += p["vx"] * dt * 0.001
            p["y"] += p["vy"] * dt * 0.001
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        for p in self._particles:
            if p["life"] <= 0:
                continue
            c = QColor(self._color)
            c.setAlpha(int(p["life"] * 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            px = rect.x() + p["x"] * rect.width()
            py = rect.y() + p["y"] * rect.height()
            r = p["size"] * p["life"]
            painter.drawEllipse(QPointF(px, py), r, r)

    def reset(self):
        self._active = False
        self._elapsed = 0.0
        self._particles = []


class ToastTypewriterEffect(BaseEffect):
    """Typewriter text animation (extracted from AchToastWindow)."""

    CHAR_DELAY = 40.0

    def __init__(self):
        self._text = ""
        self._display = ""
        self._elapsed = 0.0
        self._active = False

    def start(self, text: str):
        self._text = text
        self._display = ""
        self._elapsed = 0.0
        self._active = True

    @property
    def display_text(self) -> str:
        return self._display

    @property
    def active(self) -> bool:
        return self._active

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        n = min(len(self._text), int(self._elapsed / self.CHAR_DELAY))
        self._display = self._text[:n]
        if n >= len(self._text):
            self._active = False

    def paint(self, painter, rect):
        pass  # Rendered by the overlay widget

    def reset(self):
        self._active = False
        self._display = ""
        self._elapsed = 0.0


class ToastBounceEffect(BaseEffect):
    """Icon bounce animation (extracted from AchToastWindow)."""

    DURATION = 400.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def offset_y(self) -> float:
        if not self._active:
            return 0.0
        t = self._elapsed / self.DURATION
        return -abs(math.sin(t * math.pi * 2)) * 8.0

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class ToastEnergyFlashEffect(BaseEffect):
    """Energy flash animation (extracted from AchToastWindow)."""

    DURATION = 300.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def alpha(self) -> int:
        if not self._active:
            return 0
        t = self._elapsed / self.DURATION
        return int((1.0 - t) * 180)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        c = QColor(255, 220, 80, self.alpha)
        painter.fillRect(QRectF(rect), c)

    def reset(self):
        self._active = False
        self._elapsed = 0.0


# ── Status Overlay effects ───────────────────────────────────────────────────

class StatusScanInEffect(BaseEffect):
    """Scan-in slide from right (extracted from StatusOverlay)."""

    DURATION = 350.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def offset_x(self) -> float:
        if not self._active:
            return 0.0
        t = min(1.0, self._elapsed / self.DURATION)
        ease = 1.0 - (1.0 - t) ** 3
        return (1.0 - ease) * 40.0

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class StatusGlowSweepEffect(BaseEffect):
    """Horizontal glow sweep (extracted from StatusOverlay)."""

    DURATION = 700.0

    def __init__(self, color="#00E5FF"):
        self._color = QColor(color)
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        t = min(1.0, self._elapsed / self.DURATION)
        cx = rect.x() + int(t * rect.width())
        grad = QLinearGradient(cx - 20, 0, cx + 20, 0)
        c = QColor(self._color)
        c.setAlpha(0)
        c2 = QColor(self._color)
        c2.setAlpha(140)
        grad.setColorAt(0.0, c)
        grad.setColorAt(0.5, c2)
        grad.setColorAt(1.0, c)
        painter.fillRect(QRectF(rect), grad)

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class StatusColorMorphEffect(BaseEffect):
    """Color morph animation (extracted from StatusOverlay)."""

    DURATION = 1200.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False
        self._colors = [QColor("#00E5FF"), QColor("#FF7F00"), QColor("#00E5FF")]

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def current_color(self) -> "QColor":
        if not self._active:
            return self._colors[0]
        t = min(1.0, self._elapsed / self.DURATION)
        seg = t * (len(self._colors) - 1)
        idx = min(int(seg), len(self._colors) - 2)
        ft = seg - idx
        c1, c2 = self._colors[idx], self._colors[idx + 1]
        r = int(c1.red() + (c2.red() - c1.red()) * ft)
        g = int(c1.green() + (c2.green() - c1.green()) * ft)
        b = int(c1.blue() + (c2.blue() - c1.blue()) * ft)
        return QColor(r, g, b)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._elapsed = 0.0


# ── Flip Counter effects ─────────────────────────────────────────────────────

class FlipCounterPulseEffect(BaseEffect):
    """Breathing pulse glow ring (extracted from FlipCounterOverlay)."""

    def __init__(self, color="#FF7F00"):
        self._color = QColor(color)
        self._phase = 0.0

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.003) % (2 * math.pi)

    @property
    def alpha(self) -> int:
        return int(60 + 60 * math.sin(self._phase))

    def paint(self, painter, rect):
        c = QColor(self._color)
        c.setAlpha(self.alpha)
        pen = QPen(c, 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(rect).adjusted(2, 2, -2, -2))

    def reset(self):
        self._phase = 0.0


# ── Challenge Select effects ─────────────────────────────────────────────────

class ChallengePulseEffect(BaseEffect):
    """Pulse glow on active card (extracted from ChallengeSelectOverlay)."""

    def __init__(self, color="#00E5FF"):
        self._color = QColor(color)
        self._phase = 0.0

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.004) % (2 * math.pi)

    @property
    def alpha(self) -> int:
        return int(50 + 50 * math.sin(self._phase))

    def paint(self, painter, rect):
        c = QColor(self._color)
        c.setAlpha(self.alpha)
        pen = QPen(c, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 6, 6)

    def reset(self):
        self._phase = 0.0


class ChallengeCarouselEffect(BaseEffect):
    """Carousel slide animation (extracted from ChallengeSelectOverlay)."""

    DURATION = 200.0

    def __init__(self):
        self._offset = 0.0
        self._target = 0.0
        self._active = False
        self._elapsed = 0.0

    def slide_to(self, target_offset: float):
        self._offset = self._target
        self._target = target_offset
        self._elapsed = 0.0
        self._active = True

    @property
    def current_offset(self) -> float:
        return self._offset

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        t = min(1.0, self._elapsed / self.DURATION)
        ease = 1.0 - (1.0 - t) ** 2
        self._offset = self._offset + (self._target - self._offset) * ease
        if abs(self._offset - self._target) < 0.5:
            self._offset = self._target
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._offset = 0.0
        self._target = 0.0
        self._elapsed = 0.0


# ===========================================================================
# ── NEW animation classes ───────────────────────────────────────────────────
# ===========================================================================

# ── Main Overlay — new ──────────────────────────────────────────────────────

class SparkleEffect(BaseEffect):
    """Burst of small sparkle particles at overlay border on page change."""

    DURATION = 600.0

    def __init__(self, color="#00E5FF"):
        self._color = QColor(color)
        self._active = False
        self._elapsed = 0.0
        self._particles = []

    @property
    def active(self) -> bool:
        return self._active

    def trigger(self, portrait: bool = False):
        self._active = True
        self._elapsed = 0.0
        self._particles = []
        for _ in range(30):
            edge = random.randint(0, 3)
            if portrait:
                edge = (edge + 1) % 4
            if edge == 0:    # top
                x, y = random.uniform(0, 1), 0.0
            elif edge == 1:  # right
                x, y = 1.0, random.uniform(0, 1)
            elif edge == 2:  # bottom
                x, y = random.uniform(0, 1), 1.0
            else:            # left
                x, y = 0.0, random.uniform(0, 1)
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.05, 0.25)
            self._particles.append({
                "x": x, "y": y,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "life": 1.0,
                "size": random.uniform(2, 5),
            })

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        for p in self._particles:
            p["life"] -= dt / self.DURATION
            p["x"] += p["vx"] * dt * 0.01
            p["y"] += p["vy"] * dt * 0.01
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        w, h = rect.width(), rect.height()
        for p in self._particles:
            if p["life"] <= 0:
                continue
            c = QColor(self._color)
            c.setAlpha(int(p["life"] * 220))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            px = rect.x() + p["x"] * w
            py = rect.y() + p["y"] * h
            r = p["size"] * p["life"]
            painter.drawEllipse(QPointF(px, py), r, r)

    def reset(self):
        self._active = False
        self._elapsed = 0.0
        self._particles = []


class BackgroundRippleEffect(BaseEffect):
    """Subtle sine-wave ripple emanating from center of overlay."""

    def __init__(self, color="#00E5FF"):
        self._color = QColor(color)
        self._phase = 0.0
        self._rings = []
        self._elapsed_total = 0.0

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.002) % (2 * math.pi)
        self._elapsed_total += dt
        # Spawn a new ring every 600ms
        if not self._rings or self._elapsed_total - self._rings[-1]["born"] > 600:
            self._rings.append({"born": self._elapsed_total, "life": 1.0})
        new_rings = []
        for ring in self._rings:
            ring["life"] = max(0.0, 1.0 - (self._elapsed_total - ring["born"]) / 1800.0)
            if ring["life"] > 0:
                new_rings.append(ring)
        self._rings = new_rings

    def paint(self, painter, rect):
        cx = rect.x() + rect.width() / 2
        cy = rect.y() + rect.height() / 2
        max_r = math.sqrt((rect.width() / 2) ** 2 + (rect.height() / 2) ** 2)
        for ring in self._rings:
            t = 1.0 - ring["life"]
            r = t * max_r
            c = QColor(self._color)
            c.setAlpha(int(ring["life"] * 40))
            pen = QPen(c, 1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r, r)

    def reset(self):
        self._phase = 0.0
        self._rings = []
        self._elapsed_total = 0.0


class ConfettiEffect(BaseEffect):
    """Small colored rectangles fall from top of overlay on achievement unlock."""

    DURATION = 2500.0
    COLORS = ["#FF4444", "#44FF44", "#4444FF", "#FFFF44", "#FF44FF", "#44FFFF", "#FF7F00"]

    def __init__(self):
        self._active = False
        self._elapsed = 0.0
        self._pieces = []

    def trigger(self, portrait: bool = False):
        self._active = True
        self._elapsed = 0.0
        self._pieces = []
        for _ in range(40):
            if portrait:
                # Fall from left edge in portrait
                x = 0.0
                y = random.uniform(0, 1)
                vx = random.uniform(0.1, 0.4)
                vy = random.uniform(-0.05, 0.05)
            else:
                x = random.uniform(0, 1)
                y = 0.0
                vx = random.uniform(-0.02, 0.02)
                vy = random.uniform(0.1, 0.4)
            self._pieces.append({
                "x": x, "y": y, "vx": vx, "vy": vy,
                "color": QColor(random.choice(self.COLORS)),
                "w": random.uniform(5, 10),
                "h": random.uniform(3, 6),
                "rot": random.uniform(0, 360),
                "rot_speed": random.uniform(-180, 180),
                "life": 1.0,
            })

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        t_norm = self._elapsed / self.DURATION
        for p in self._pieces:
            p["x"] += p["vx"] * dt * 0.001
            p["y"] += p["vy"] * dt * 0.001
            p["rot"] = (p["rot"] + p["rot_speed"] * dt * 0.001) % 360
            p["life"] = max(0.0, 1.0 - t_norm)
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        w, h = rect.width(), rect.height()
        for p in self._pieces:
            if p["life"] <= 0:
                continue
            c = QColor(p["color"])
            c.setAlpha(int(p["life"] * 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            px = rect.x() + p["x"] * w
            py = rect.y() + p["y"] * h
            painter.save()
            painter.translate(px, py)
            painter.rotate(p["rot"])
            painter.drawRect(
                int(-p["w"] / 2), int(-p["h"] / 2),
                int(p["w"]), int(p["h"])
            )
            painter.restore()

    def reset(self):
        self._active = False
        self._elapsed = 0.0
        self._pieces = []


# ── Toast — new ──────────────────────────────────────────────────────────────

class ToastSlideInEffect(BaseEffect):
    """Toast slides in from bottom with cubic ease-out over 300ms."""

    DURATION = 300.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False
        self._portrait = False

    def trigger(self, portrait: bool = False):
        self._elapsed = 0.0
        self._active = True
        self._portrait = portrait

    @property
    def offset(self) -> float:
        if not self._active:
            return 0.0
        t = min(1.0, self._elapsed / self.DURATION)
        ease = 1.0 - (1.0 - t) ** 3
        return (1.0 - ease) * 60.0

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class ToastShineSweepEffect(BaseEffect):
    """Diagonal shine line sweeps across toast from left to right over 400ms."""

    DURATION = 400.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect, portrait: bool = False):
        if not self._active:
            return
        t = min(1.0, self._elapsed / self.DURATION)
        if portrait:
            cy = rect.y() + int(t * rect.height())
            grad = QLinearGradient(0, cy - 20, 0, cy + 20)
        else:
            cx = rect.x() + int(t * rect.width())
            grad = QLinearGradient(cx - 20, 0, cx + 20, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, QColor(255, 255, 255, 100))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(rect), grad)

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class ToastPulseRingEffect(BaseEffect):
    """Expanding semi-transparent ring around the toast icon, fades as it expands."""

    DURATION = 600.0

    def __init__(self, color="#FF7F00"):
        self._color = QColor(color)
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        t = min(1.0, self._elapsed / self.DURATION)
        cx = rect.x() + rect.width() / 2
        cy = rect.y() + rect.height() / 2
        base_r = min(rect.width(), rect.height()) * 0.3
        r = base_r + t * base_r * 2
        c = QColor(self._color)
        c.setAlpha(int((1.0 - t) * 150))
        pen = QPen(c, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r, r)

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class ToastGlowFadeEffect(BaseEffect):
    """Text area fades from white glow to normal over 500ms on appear."""

    DURATION = 500.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def alpha(self) -> int:
        if not self._active:
            return 0
        t = min(1.0, self._elapsed / self.DURATION)
        return int((1.0 - t) * 120)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active or self.alpha == 0:
            return
        c = QColor(255, 255, 255, self.alpha)
        painter.fillRect(QRectF(rect), c)

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class ToastSlideOutEffect(BaseEffect):
    """Toast slides up and fades out over 250ms on dismiss."""

    DURATION = 250.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False
        self._portrait = False

    def trigger(self, portrait: bool = False):
        self._elapsed = 0.0
        self._active = True
        self._portrait = portrait

    @property
    def offset(self) -> float:
        if not self._active:
            return 0.0
        t = min(1.0, self._elapsed / self.DURATION)
        return -t * 60.0

    @property
    def alpha(self) -> int:
        if not self._active:
            return 255
        t = min(1.0, self._elapsed / self.DURATION)
        return int((1.0 - t) * 255)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._elapsed = 0.0


# ── Flip Counter — new ───────────────────────────────────────────────────────

class FlipNumberEffect(BaseEffect):
    """Digit flip like a split-flap board: old digit slides up+fades, new slides in from below."""

    DURATION = 200.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False
        self._old_digit = ""
        self._new_digit = ""

    def trigger(self, old_digit: str, new_digit: str):
        self._old_digit = old_digit
        self._new_digit = new_digit
        self._elapsed = 0.0
        self._active = True

    @property
    def old_offset_y(self) -> float:
        if not self._active:
            return -100.0
        t = min(1.0, self._elapsed / self.DURATION)
        return -t * 100.0

    @property
    def new_offset_y(self) -> float:
        if not self._active:
            return 0.0
        t = min(1.0, self._elapsed / self.DURATION)
        return (1.0 - t) * 100.0

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass  # Caller renders using offset_y values

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class GoalFlashEffect(BaseEffect):
    """When goal is reached, the counter flashes bright with theme accent color 3 times."""

    FLASH_DURATION = 150.0
    FLASHES = 3

    def __init__(self, color="#FF7F00"):
        self._color = QColor(color)
        self._elapsed = 0.0
        self._active = False
        self._total_duration = self.FLASH_DURATION * self.FLASHES * 2

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self._total_duration:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        phase = (self._elapsed % (self.FLASH_DURATION * 2)) / (self.FLASH_DURATION * 2)
        alpha = int(math.sin(phase * math.pi) * 160)
        if alpha > 0:
            c = QColor(self._color)
            c.setAlpha(alpha)
            painter.fillRect(QRectF(rect), c)

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class GradientColorEffect(BaseEffect):
    """Counter background color smoothly shifts: green >50%, orange 20-50%, red <20%."""

    def __init__(self):
        self._ratio = 1.0  # 0.0–1.0 remaining fraction
        self._phase = 0.0

    def set_ratio(self, remaining: int, total: int):
        self._ratio = max(0.0, min(1.0, remaining / max(1, total)))

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.003) % (2 * math.pi)

    @property
    def color(self) -> "QColor":
        pulse = 0.15 * math.sin(self._phase)
        r = self._ratio + pulse
        if r > 0.5:
            return QColor(0, 180, 60)    # green
        elif r > 0.2:
            return QColor(255, 140, 0)   # orange
        else:
            return QColor(220, 40, 40)   # red

    def paint(self, painter, rect):
        c = QColor(self.color)
        c.setAlpha(60)
        painter.fillRect(QRectF(rect), c)

    def reset(self):
        self._ratio = 1.0
        self._phase = 0.0


class OrbitParticleEffect(BaseEffect):
    """6 small particles orbit the counter in a circular path."""

    NUM = 6

    def __init__(self, color="#00E5FF"):
        self._color = QColor(color)
        self._angle = 0.0
        self._speed = 0.002  # radians per ms, increases as remaining decreases

    def set_urgency(self, ratio: float):
        """ratio = remaining/total, 0..1. Lower → faster."""
        self._speed = 0.002 + (1.0 - ratio) * 0.006

    def tick(self, dt: float):
        self._angle = (self._angle + self._speed * dt) % (2 * math.pi)

    def paint(self, painter, rect):
        cx = rect.x() + rect.width() / 2
        cy = rect.y() + rect.height() / 2
        orbit_r = min(rect.width(), rect.height()) / 2 + 8
        for i in range(self.NUM):
            a = self._angle + (2 * math.pi * i / self.NUM)
            px = cx + math.cos(a) * orbit_r
            py = cy + math.sin(a) * orbit_r
            c = QColor(self._color)
            c.setAlpha(180)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(px, py), 3.0, 3.0)

    def reset(self):
        self._angle = 0.0
        self._speed = 0.002


class WarnShakeEffect(BaseEffect):
    """When remaining <10% of goal, the counter shakes horizontally ±4px, 3 cycles."""

    DURATION = 300.0
    CYCLES = 3

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def offset_x(self) -> float:
        if not self._active:
            return 0.0
        t = self._elapsed / self.DURATION
        return math.sin(t * math.pi * 2 * self.CYCLES) * 4.0

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class FlipFadeInEffect(BaseEffect):
    """Counter fades in with opacity 0→1 over 300ms on first show."""

    DURATION = 300.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def opacity(self) -> float:
        if not self._active:
            return 1.0
        return min(1.0, self._elapsed / self.DURATION)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        alpha = int((1.0 - self.opacity) * 255)
        if alpha > 0:
            painter.fillRect(QRectF(rect), QColor(0, 0, 0, alpha))

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class FlipZoomPulseEffect(BaseEffect):
    """Each time the count decrements, the counter briefly scales 1.0→1.08→1.0 over 150ms."""

    DURATION = 150.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def scale(self) -> float:
        if not self._active:
            return 1.0
        t = self._elapsed / self.DURATION
        return 1.0 + 0.08 * math.sin(t * math.pi)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass  # Caller applies transform from self.scale

    def reset(self):
        self._active = False
        self._elapsed = 0.0


# ── Challenge Select — new ───────────────────────────────────────────────────

class ChallengeCard3DFlipEffect(BaseEffect):
    """Selected card does a brief Y-axis pseudo-3D flip (squish width) over 200ms."""

    DURATION = 200.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False
        self._portrait = False

    def trigger(self, portrait: bool = False):
        self._elapsed = 0.0
        self._active = True
        self._portrait = portrait

    @property
    def scale(self) -> float:
        if not self._active:
            return 1.0
        t = self._elapsed / self.DURATION
        return abs(math.cos(t * math.pi))

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class ChallengeSpotlightEffect(BaseEffect):
    """Semi-transparent dark vignette with a bright circle cutout over the active card."""

    def __init__(self):
        self._cx = 0.5
        self._cy = 0.5
        self._radius = 0.25
        self._phase = 0.0

    def set_focus(self, cx: float, cy: float, radius: float):
        """cx, cy, radius as fractions of the widget size."""
        self._cx = cx
        self._cy = cy
        self._radius = radius

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.002) % (2 * math.pi)

    def paint(self, painter, rect):
        w, h = rect.width(), rect.height()
        cx = rect.x() + self._cx * w
        cy = rect.y() + self._cy * h
        r = self._radius * min(w, h)
        pulse = 0.05 * math.sin(self._phase)
        r *= (1.0 + pulse)
        grad = QRadialGradient(QPointF(cx, cy), r)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.7, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(0, 0, 0, 140))
        painter.fillRect(QRectF(rect), grad)

    def reset(self):
        self._phase = 0.0


class ChallengeGlitterEffect(BaseEffect):
    """Tiny sparkle dots trail behind the selection indicator as it moves."""

    DURATION = 500.0

    def __init__(self, color="#FFFF80"):
        self._color = QColor(color)
        self._trail = []
        self._elapsed_total = 0.0

    def add_trail(self, x: float, y: float):
        """x, y as fractions of widget size."""
        self._trail.append({"x": x, "y": y, "born": self._elapsed_total, "life": 1.0})

    def tick(self, dt: float):
        self._elapsed_total += dt
        for p in self._trail:
            age = self._elapsed_total - p["born"]
            p["life"] = max(0.0, 1.0 - age / self.DURATION)
        self._trail = [p for p in self._trail if p["life"] > 0]

    def paint(self, painter, rect):
        w, h = rect.width(), rect.height()
        for p in self._trail:
            c = QColor(self._color)
            c.setAlpha(int(p["life"] * 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            px = rect.x() + p["x"] * w
            py = rect.y() + p["y"] * h
            r = 3.0 * p["life"]
            painter.drawEllipse(QPointF(px, py), r, r)

    def reset(self):
        self._trail = []
        self._elapsed_total = 0.0


class ChallengeZoomPulseEffect(BaseEffect):
    """Active card scale pulses 1.0→1.04→1.0 continuously at 1.5s interval."""

    PERIOD = 1500.0

    def __init__(self):
        self._elapsed = 0.0

    @property
    def scale(self) -> float:
        t = (self._elapsed % self.PERIOD) / self.PERIOD
        return 1.0 + 0.04 * math.sin(t * 2 * math.pi)

    def tick(self, dt: float):
        self._elapsed += dt

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._elapsed = 0.0


class ChallengeHaloEffect(BaseEffect):
    """Colored halo ring around the active card, color follows theme accent, pulses in/out."""

    def __init__(self, color="#00E5FF"):
        self._color = QColor(color)
        self._phase = 0.0

    def set_color(self, color: str):
        self._color = QColor(color)

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.003) % (2 * math.pi)

    def paint(self, painter, rect):
        alpha = int(80 + 60 * math.sin(self._phase))
        c = QColor(self._color)
        c.setAlpha(alpha)
        pen = QPen(c, 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(rect).adjusted(2, 2, -2, -2), 8, 8)

    def reset(self):
        self._phase = 0.0


class ChallengeFadeInEffect(BaseEffect):
    """Entire overlay fades in opacity 0→1 over 350ms on open."""

    DURATION = 350.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def opacity(self) -> float:
        if not self._active:
            return 1.0
        return min(1.0, self._elapsed / self.DURATION)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        alpha = int((1.0 - self.opacity) * 255)
        if alpha > 0:
            painter.fillRect(QRectF(rect), QColor(0, 0, 0, alpha))

    def reset(self):
        self._active = False
        self._elapsed = 0.0


# ===========================================================================
# ── Heat Bar effects ────────────────────────────────────────────────────────
# ===========================================================================

class HeatPulseGlowEffect(BaseEffect):
    """Breathing glow border that intensifies with heat level."""

    def __init__(self):
        self._phase = 0.0
        self._heat = 0

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))

    def tick(self, dt: float):
        speed = 0.002 + 0.004 * (self._heat / 100.0)
        self._phase = (self._phase + dt * speed) % (2 * math.pi)

    def paint(self, painter, rect):
        if self._heat < 30:
            return
        amp = 0.5 + 0.5 * math.sin(self._phase)
        if self._heat > 85:
            color = QColor(255, 40, 0, int(120 + 80 * amp))
            width = 2 + int(2 * amp)
        elif self._heat > 65:
            color = QColor(255, 140, 0, int(80 + 60 * amp))
            width = 2
        else:
            color = QColor(0, 200, 100, int(40 + 40 * amp))
            width = 1
        pen = QPen(color, width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 8, 8)

    def reset(self):
        self._phase = 0.0


class HeatFillShimmerEffect(BaseEffect):
    """Shimmer sweep over the filled portion of the bar."""

    PERIOD = 1200.0

    def __init__(self):
        self._elapsed = 0.0

    def tick(self, dt: float):
        self._elapsed = (self._elapsed + dt) % self.PERIOD

    def paint(self, painter, rect):
        t = self._elapsed / self.PERIOD
        x = rect.x() + t * rect.width()
        grad = QLinearGradient(x - 10, 0, x + 10, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.5, QColor(255, 255, 255, 60))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(QRectF(rect), grad)

    def reset(self):
        self._elapsed = 0.0


class HeatColorMorphEffect(BaseEffect):
    """Smooth color transition overlay as heat changes (green->orange->red)."""

    def __init__(self):
        self._phase = 0.0
        self._heat = 0

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.001) % (2 * math.pi)

    def paint(self, painter, rect):
        if self._heat < 50:
            return
        pulse = 0.5 + 0.5 * math.sin(self._phase)
        frac = (self._heat - 50) / 50.0
        r = int(200 * frac)
        g = int(80 * (1.0 - frac))
        alpha = int(20 + 15 * pulse)
        painter.fillRect(QRectF(rect), QColor(r, g, 0, alpha))

    def reset(self):
        self._phase = 0.0


class HeatWarningFlashEffect(BaseEffect):
    """Flash effect when heat exceeds 85%."""

    FLASH_INTERVAL = 400.0

    def __init__(self):
        self._elapsed = 0.0
        self._heat = 0

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))

    def tick(self, dt: float):
        self._elapsed = (self._elapsed + dt) % (self.FLASH_INTERVAL * 2)

    def paint(self, painter, rect):
        if self._heat <= 85:
            return
        t = self._elapsed / self.FLASH_INTERVAL
        alpha = int(60 * math.sin(t * math.pi))
        if alpha > 0:
            painter.fillRect(QRectF(rect), QColor(255, 30, 0, alpha))

    def reset(self):
        self._elapsed = 0.0


class HeatParticleRiseEffect(BaseEffect):
    """Small particles rising from the bar (like heat/steam)."""

    MAX_PARTICLES = 12

    def __init__(self):
        self._particles = []
        self._spawn_timer = 0.0
        self._heat = 0

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))

    def tick(self, dt: float):
        if self._heat < 40:
            self._particles.clear()
            return
        interval = max(80.0, 300.0 - 2.0 * self._heat)
        self._spawn_timer += dt
        if self._spawn_timer >= interval and len(self._particles) < self.MAX_PARTICLES:
            self._spawn_timer = 0.0
            self._particles.append({
                "x": random.uniform(0.1, 0.9),
                "y": random.uniform(0.7, 1.0),
                "vy": random.uniform(0.0003, 0.0007),
                "life": 1.0,
                "r": random.randint(2, 4),
            })
        for p in self._particles:
            p["y"] -= p["vy"] * dt
            p["life"] -= dt / 1200.0
        self._particles = [p for p in self._particles if p["life"] > 0 and p["y"] > -0.1]

    def paint(self, painter, rect):
        w, h = rect.width(), rect.height()
        for p in self._particles:
            alpha = int(p["life"] * 180)
            c = QColor(255, 200, 80, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            px = rect.x() + p["x"] * w
            py = rect.y() + p["y"] * h
            painter.drawEllipse(QPointF(px, py), p["r"], p["r"])

    def reset(self):
        self._particles.clear()
        self._spawn_timer = 0.0


class HeatShakeEffect(BaseEffect):
    """Horizontal shake when heat is critical (>90%)."""

    def __init__(self):
        self._phase = 0.0
        self._heat = 0

    @property
    def offset_x(self):
        if self._heat <= 90:
            return 0.0
        return 2.0 * math.sin(self._phase)

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.04) % (2 * math.pi)

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._phase = 0.0


class HeatFadeInEffect(BaseEffect):
    """Opacity fade-in when bar first appears."""

    DURATION = 400.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def opacity(self):
        if not self._active:
            return 1.0
        return min(1.0, self._elapsed / self.DURATION)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        alpha = int((1.0 - self.opacity) * 255)
        if alpha > 0:
            painter.fillRect(QRectF(rect), QColor(0, 0, 0, alpha))

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class HeatBarScaleEffect(BaseEffect):
    """Subtle scale pulse on heat level change."""

    PERIOD = 600.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    @property
    def scale(self):
        if not self._active:
            return 1.0
        t = self._elapsed / self.PERIOD
        return 1.0 + 0.03 * math.sin(t * math.pi)

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.PERIOD:
            self._active = False

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._active = False
        self._elapsed = 0.0


# ===========================================================================
# ── Timer effects ───────────────────────────────────────────────────────────
# ===========================================================================

class TimerPulseEffect(BaseEffect):
    """Breathing pulse that speeds up as time runs out."""

    def __init__(self):
        self._phase = 0.0
        self._seconds_left = 300

    def set_time(self, seconds_left: int):
        self._seconds_left = max(0, int(seconds_left))

    @property
    def scale(self):
        return 1.0 + 0.02 * math.sin(self._phase)

    def tick(self, dt: float):
        speed = 0.002 + 0.006 * max(0.0, 1.0 - self._seconds_left / 30.0)
        self._phase = (self._phase + dt * speed) % (2 * math.pi)

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._phase = 0.0


class TimerTickFlashEffect(BaseEffect):
    """Brief flash on each second tick."""

    FLASH_DURATION = 120.0

    def __init__(self):
        self._elapsed = self.FLASH_DURATION  # start inactive

    def trigger(self):
        self._elapsed = 0.0

    def tick(self, dt: float):
        self._elapsed = min(self._elapsed + dt, self.FLASH_DURATION)

    def paint(self, painter, rect):
        if self._elapsed >= self.FLASH_DURATION:
            return
        t = self._elapsed / self.FLASH_DURATION
        alpha = int(80 * (1.0 - t))
        if alpha > 0:
            painter.fillRect(QRectF(rect), QColor(255, 255, 255, alpha))

    def reset(self):
        self._elapsed = self.FLASH_DURATION


class TimerColorShiftEffect(BaseEffect):
    """Color shifts from calm to urgent as time decreases."""

    def __init__(self):
        self._phase = 0.0
        self._seconds_left = 300

    def set_time(self, seconds_left: int):
        self._seconds_left = max(0, int(seconds_left))

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.001) % (2 * math.pi)

    def paint(self, painter, rect):
        if self._seconds_left > 30:
            return
        frac = max(0.0, 1.0 - self._seconds_left / 30.0)
        pulse = 0.5 + 0.5 * math.sin(self._phase)
        r = int(200 * frac)
        alpha = int((10 + 20 * pulse) * frac)
        if alpha > 0:
            painter.fillRect(QRectF(rect), QColor(r, 0, 0, alpha))

    def reset(self):
        self._phase = 0.0


class TimerShakeEffect(BaseEffect):
    """Shake when time is critically low (<10 seconds)."""

    def __init__(self):
        self._phase = 0.0
        self._seconds_left = 300

    @property
    def offset_x(self):
        if self._seconds_left >= 10:
            return 0.0
        return 3.0 * math.sin(self._phase)

    def set_time(self, seconds_left: int):
        self._seconds_left = max(0, int(seconds_left))

    def tick(self, dt: float):
        self._phase = (self._phase + dt * 0.05) % (2 * math.pi)

    def paint(self, painter, rect):
        pass

    def reset(self):
        self._phase = 0.0


class TimerGlowBorderEffect(BaseEffect):
    """Glowing border that intensifies near timeout."""

    def __init__(self):
        self._phase = 0.0
        self._seconds_left = 300

    def set_time(self, seconds_left: int):
        self._seconds_left = max(0, int(seconds_left))

    def tick(self, dt: float):
        speed = 0.002 + 0.005 * max(0.0, 1.0 - self._seconds_left / 60.0)
        self._phase = (self._phase + dt * speed) % (2 * math.pi)

    def paint(self, painter, rect):
        if self._seconds_left > 60:
            return
        frac = max(0.0, 1.0 - self._seconds_left / 60.0)
        amp = 0.5 + 0.5 * math.sin(self._phase)
        if self._seconds_left <= 10:
            color = QColor(255, 40, 0, int((80 + 80 * amp) * frac))
            width = 2 + int(2 * amp)
        else:
            color = QColor(255, 140, 0, int((50 + 50 * amp) * frac))
            width = 2
        pen = QPen(color, width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(rect).adjusted(2, 2, -2, -2), 10, 10)

    def reset(self):
        self._phase = 0.0


class TimerFadeInEffect(BaseEffect):
    """Opacity fade-in when timer first appears."""

    DURATION = 350.0

    def __init__(self):
        self._elapsed = 0.0
        self._active = False

    def trigger(self):
        self._elapsed = 0.0
        self._active = True

    @property
    def opacity(self):
        if not self._active:
            return 1.0
        return min(1.0, self._elapsed / self.DURATION)

    def tick(self, dt: float):
        if not self._active:
            return
        self._elapsed += dt
        if self._elapsed >= self.DURATION:
            self._active = False

    def paint(self, painter, rect):
        if not self._active:
            return
        alpha = int((1.0 - self.opacity) * 255)
        if alpha > 0:
            painter.fillRect(QRectF(rect), QColor(0, 0, 0, alpha))

    def reset(self):
        self._active = False
        self._elapsed = 0.0


class TimerDigitFlipEffect(BaseEffect):
    """Split-flap digit animation on second change."""

    FLIP_DURATION = 150.0

    def __init__(self):
        self._elapsed = self.FLIP_DURATION  # start inactive

    def trigger(self):
        self._elapsed = 0.0

    @property
    def flip_progress(self):
        return min(1.0, self._elapsed / self.FLIP_DURATION)

    def tick(self, dt: float):
        self._elapsed = min(self._elapsed + dt, self.FLIP_DURATION)

    def paint(self, painter, rect):
        if self._elapsed >= self.FLIP_DURATION:
            return
        t = self._elapsed / self.FLIP_DURATION
        # Draw a horizontal sweep bar to simulate the flip
        y = rect.y() + t * rect.height()
        alpha = int(100 * (1.0 - t))
        if alpha > 0:
            painter.fillRect(
                QRectF(rect.x(), y - 4, rect.width(), 4),
                QColor(255, 255, 255, alpha),
            )

    def reset(self):
        self._elapsed = self.FLIP_DURATION


class TimerUrgencyParticleEffect(BaseEffect):
    """Orbiting particles that speed up as time runs out."""

    MAX_PARTICLES = 8

    def __init__(self):
        self._angles = []
        self._seconds_left = 300
        self._elapsed = 0.0

    def set_time(self, seconds_left: int):
        self._seconds_left = max(0, int(seconds_left))

    def tick(self, dt: float):
        if self._seconds_left > 60:
            self._angles.clear()
            return
        self._elapsed += dt
        speed = 0.002 + 0.006 * max(0.0, 1.0 - self._seconds_left / 60.0)
        count = max(2, int(self.MAX_PARTICLES * (1.0 - self._seconds_left / 60.0)))
        while len(self._angles) < count:
            self._angles.append(random.uniform(0, 2 * math.pi))
        while len(self._angles) > count:
            self._angles.pop()
        self._angles = [(a + dt * speed) % (2 * math.pi) for a in self._angles]

    def paint(self, painter, rect):
        if self._seconds_left > 60 or not self._angles:
            return
        cx = rect.x() + rect.width() / 2
        cy = rect.y() + rect.height() / 2
        rx = rect.width() / 2 + 6
        ry = rect.height() / 2 + 6
        frac = max(0.0, 1.0 - self._seconds_left / 60.0)
        alpha = int(160 * frac)
        for angle in self._angles:
            px = cx + rx * math.cos(angle)
            py = cy + ry * math.sin(angle)
            c = QColor(255, 200, 50, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(px, py), 3.0, 3.0)

    def reset(self):
        self._angles.clear()
        self._elapsed = 0.0
