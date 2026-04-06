"""trophie_animations.py — New passive animation tick and draw helpers for
_TrophieDrawWidget (GUITrophie).

This module is imported by mascot.py to keep that file from growing
further.  Each tick_* function receives the draw-widget instance and updates
its state fields (_passive_t, _passive_extra_x, _passive_extra_y,
_passive_angle, _snore_particles, _confetti_particles).  Each draw_* function
receives the active QPainter and the widget instance and renders an overlay
effect on top of the already-drawn trophy.
"""
from __future__ import annotations

import math
import random

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

# ---------------------------------------------------------------------------
# Tick helpers — called from _TrophieDrawWidget._tick()
# ---------------------------------------------------------------------------

def tick_drop_target_dance(widget) -> None:
    """Rhythmic sinusoidal side-to-side sway with matching tilt angle."""
    t = widget._passive_t
    widget._passive_extra_x = math.sin(t * 1.5) * 6.0
    widget._passive_angle = math.sin(t * 1.5) * 8.0


def tick_flipper_wave(widget) -> None:
    """Flipper-wave: no body transform needed; overlay drawn by draw_flipper_wave()."""


def tick_trough_snore(widget) -> None:
    """Animated 'Z' letters drifting upward; particles initialised on first call."""
    if not widget._snore_particles:
        widget._snore_particles = [
            {"x_off": 10, "y_off":  0.0, "size": 11, "alpha": 220, "delay": 0.0,  "speed": 18.0},
            {"x_off": 20, "y_off":  0.0, "size":  8, "alpha": 180, "delay": 1.2,  "speed": 15.0},
            {"x_off":  4, "y_off":  0.0, "size":  6, "alpha": 140, "delay": 2.4,  "speed": 12.0},
        ]
    dt = 0.016
    for part in widget._snore_particles:
        if widget._passive_t < part["delay"]:
            continue
        part["y_off"] -= part["speed"] * dt
        part["alpha"] = max(0, part["alpha"] - 1)
        if part["alpha"] <= 0:
            part["y_off"] = 0.0
            part["alpha"] = 220


def tick_tilt_shiver(widget) -> None:
    """Rapid high-frequency horizontal micro-jitter (±2 px)."""
    widget._passive_extra_x = random.uniform(-2.0, 2.0)


_CONFETTI_COLORS = [
    QColor(255, 80,  80),
    QColor(80,  200, 80),
    QColor(80,  80,  255),
    QColor(255, 200, 60),
    QColor(255, 80,  200),
    QColor(80,  220, 220),
]


def tick_multiball_confetti(widget) -> None:
    """Confetti rain: particles initialised on first call and loop when off-screen."""
    tw = widget._tw
    th = widget._th
    if not widget._confetti_particles:
        widget._confetti_particles = [
            {
                "x":         random.uniform(0.0, float(tw)),
                "y":         random.uniform(-float(th) * 0.5, 0.0),
                "vy":        random.uniform(30.0, 70.0),
                "vx":        random.uniform(-15.0, 15.0),
                "color":     random.choice(_CONFETTI_COLORS),
                "w":         random.randint(4, 8),
                "h":         random.randint(3, 6),
                "rot":       random.uniform(0.0, 360.0),
                "rot_speed": random.uniform(-90.0, 90.0),
            }
            for _ in range(10)
        ]
    dt = 0.016
    bottom = float(th + widget._pad)
    for cp in widget._confetti_particles:
        cp["y"] += cp["vy"] * dt
        cp["x"] += cp["vx"] * dt
        cp["rot"] = (cp["rot"] + cp["rot_speed"] * dt) % 360.0
        if cp["y"] > bottom:
            cp["y"] = random.uniform(-float(th) * 0.5, 0.0)
            cp["x"] = random.uniform(0.0, float(tw))


def tick_ball_save_peek(widget) -> None:
    """Single duck → hold → rise cycle using _passive_extra_y."""
    t = widget._passive_t
    peek_depth = widget._th * 0.35
    if t < 0.8:
        widget._passive_extra_y = (t / 0.8) * peek_depth
    elif t < 2.0:
        widget._passive_extra_y = peek_depth
    elif t < 2.8:
        widget._passive_extra_y = (1.0 - (t - 2.0) / 0.8) * peek_depth
    else:
        widget._passive_extra_y = 0.0


def tick_loop_dizzy(widget) -> None:
    """Dizzy star orbit: phase is driven by _passive_t; no extra state required."""


# ---------------------------------------------------------------------------
# Draw (overlay) helpers — called from _TrophieDrawWidget.paintEvent()
# ---------------------------------------------------------------------------

def draw_flipper_wave(p: QPainter, widget) -> None:
    """Oscillating golden arc near the right handle of the trophy cup."""
    t = widget._passive_t
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy_base = th // 2 + int(th * 0.20) + pad
    # Place the arc beside the right handle (~37 % of tw to the right of center)
    arc_cx = cx + int(tw * 0.37)
    arc_cy = cy_base - int(th * 0.08) + int(math.sin(t * 3.5) * 6.0)
    arc_r = max(5, int(tw * 0.10))
    alpha = int(180 + 60 * abs(math.sin(t * 3.5)))
    p.save()
    pen = QPen(QColor(255, 210, 60, alpha), 3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    rect = QRect(arc_cx - arc_r, arc_cy - arc_r, arc_r * 2, arc_r * 2)
    start_angle = int((-60 + math.sin(t * 3.5) * 20) * 16)
    span_angle = int(120 * 16)
    p.drawArc(rect, start_angle, span_angle)
    p.restore()


def draw_trough_snore(p: QPainter, widget) -> None:
    """Draw floating 'Z' characters rising above the trophy cup."""
    particles = getattr(widget, "_snore_particles", [])
    if not particles:
        return
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    # Anchor just above the cup rim
    cy_top = th // 2 + int(th * 0.20) + pad - int(th * 0.42)
    p.save()
    for part in particles:
        if part["alpha"] <= 10:
            continue
        font = QFont("Arial", part["size"], QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(210, 210, 255, part["alpha"]))
        p.drawText(cx + int(part["x_off"]), cy_top + int(part["y_off"]), "Z")
    p.restore()


def draw_multiball_confetti(p: QPainter, widget) -> None:
    """Draw confetti particles raining around the trophy."""
    particles = getattr(widget, "_confetti_particles", [])
    if not particles:
        return
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    for cp in particles:
        p.save()
        p.translate(cp["x"], cp["y"])
        p.rotate(cp["rot"])
        p.setBrush(cp["color"])
        p.drawRect(-cp["w"] // 2, -cp["h"] // 2, cp["w"], cp["h"])
        p.restore()
    p.restore()


def draw_loop_dizzy(p: QPainter, widget) -> None:
    """Draw small 4-pointed stars orbiting above the trophy cup."""
    t = widget._passive_t
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy_top = th // 2 + int(th * 0.20) + pad - int(th * 0.44)
    orbit_rx = max(8, int(tw * 0.24))
    orbit_ry = max(4, int(th * 0.07))
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(4):
        phase = t * 2.0 + (2.0 * math.pi * i / 4)
        sx = cx + int(math.cos(phase) * orbit_rx)
        sy = cy_top + int(math.sin(phase) * orbit_ry)
        size = 3.0 + 1.0 * math.sin(phase * 2)
        alpha = int(180 + 60 * abs(math.sin(phase)))
        star = QPainterPath()
        star.moveTo(sx, sy - size)
        star.lineTo(sx + size * 0.3, sy - size * 0.3)
        star.lineTo(sx + size, sy)
        star.lineTo(sx + size * 0.3, sy + size * 0.3)
        star.lineTo(sx, sy + size)
        star.lineTo(sx - size * 0.3, sy + size * 0.3)
        star.lineTo(sx - size, sy)
        star.lineTo(sx - size * 0.3, sy - size * 0.3)
        star.closeSubpath()
        p.fillPath(star, QColor(255, 240, 100, alpha))
    p.restore()
