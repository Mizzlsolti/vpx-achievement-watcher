"""steely_animations.py — Tick and draw helpers for Steely the pinball mascot
(_PinballDrawWidget / OverlayTrophie).

This module is imported by trophy_mascot.py to keep that file from growing
further.  It follows the same pattern as trophy_animations.py:
  - tick_* functions receive the widget instance and modify _passive_extra_x,
    _passive_extra_y, _passive_angle and particle lists.
  - draw_* functions receive an active QPainter and the widget instance and
    render overlays on top of the already-drawn ball.
  - tick_event_* / draw_event_* functions handle event-driven and personality
    animations (tracked via _event_anim / _event_anim_t on the widget).

All event animations have a fixed duration after which _event_anim is cleared
automatically by _PinballDrawWidget._tick().
"""
from __future__ import annotations

import math
import random

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient,
)

# ---------------------------------------------------------------------------
# Event animation durations (seconds).  0 means the animation persists until
# explicitly cleared (e.g. "rust" which fades over time).
# ---------------------------------------------------------------------------

EVENT_ANIM_DURATIONS: dict[str, float] = {
    "jackpot_glow":   3.5,
    "victory_lap":    4.0,
    "drain_fall":     3.0,
    "overheat":       5.0,
    "rust":           0.0,   # persistent — cleared on activity
    "plunger_entry":  2.0,
    "show_off":       3.0,
    "nervous":        4.0,
    "proud":          2.5,
    "offended":       3.5,
}

# ---------------------------------------------------------------------------
# Passive mode tick helpers — called from _PinballDrawWidget._tick()
# ---------------------------------------------------------------------------

def tick_roll_out(widget) -> None:
    """Steely rolls toward the widget edge and rolls back."""
    t = widget._passive_t
    max_x = widget._tw * 0.3
    cycle_t = t % 5.0
    if cycle_t < 1.5:
        eased = math.sin(cycle_t / 1.5 * math.pi / 2)
        widget._passive_extra_x = eased * max_x
        widget._passive_angle = eased * 160.0
    elif cycle_t < 2.5:
        widget._passive_extra_x = max_x
        widget._passive_angle = 160.0
    elif cycle_t < 4.0:
        eased = math.cos((cycle_t - 2.5) / 1.5 * math.pi / 2)
        widget._passive_extra_x = eased * max_x
        widget._passive_angle = eased * 160.0
    else:
        widget._passive_extra_x = 0.0
        widget._passive_angle = 0.0
    widget._passive_extra_y = 0.0


def tick_magnet(widget) -> None:
    """Steely is pulled upward as if attracted by a magnet, then drops."""
    t = widget._passive_t
    max_y = widget._th * 0.28
    cycle_t = t % 4.5
    if cycle_t < 1.0:
        eased = math.sin(cycle_t / 1.0 * math.pi / 2)
        widget._passive_extra_y = -eased * max_y
    elif cycle_t < 1.8:
        widget._passive_extra_y = -max_y
    elif cycle_t < 2.4:
        progress = (cycle_t - 1.8) / 0.6
        widget._passive_extra_y = -max_y * (1.0 - progress * progress)
    elif cycle_t < 2.9:
        # Small bounce at the bottom
        progress = (cycle_t - 2.4) / 0.5
        widget._passive_extra_y = math.sin(progress * math.pi) * max_y * 0.18
    else:
        widget._passive_extra_y = 0.0
    widget._passive_extra_x = 0.0
    widget._passive_angle = 0.0


def tick_bumper_hit(widget) -> None:
    """Quick direction-change jolts simulating pinball bumper impacts."""
    t = widget._passive_t
    cycle_t = t % 3.5
    hit_times = [0.0, 1.0, 1.9]
    widget._passive_extra_x = 0.0
    widget._passive_extra_y = 0.0
    widget._passive_angle = 0.0
    for hit_t in hit_times:
        elapsed = cycle_t - hit_t
        if 0.0 <= elapsed < 0.18:
            factor = 1.0 - elapsed / 0.18
            widget._passive_extra_x = math.sin(elapsed * 90) * 7.0 * factor
            widget._passive_extra_y = math.cos(elapsed * 90) * 4.5 * factor
            break


def tick_spin_out(widget) -> None:
    """Rapid spin followed by a ricochet glide to one side."""
    t = widget._passive_t
    cycle_t = t % 5.0
    if cycle_t < 0.5:
        # Rapid spin-up
        widget._passive_angle = (cycle_t / 0.5) * 720.0
        widget._passive_extra_x = 0.0
    elif cycle_t < 2.0:
        # Ricochet slide
        progress = (cycle_t - 0.5) / 1.5
        eased = math.sin(progress * math.pi)
        widget._passive_extra_x = eased * widget._tw * 0.32
        widget._passive_angle = 720.0 + progress * 360.0
    elif cycle_t < 3.5:
        # Return
        progress = (cycle_t - 2.0) / 1.5
        widget._passive_extra_x = widget._tw * 0.32 * (1.0 - progress)
        widget._passive_angle = 0.0
    else:
        widget._passive_extra_x = 0.0
        widget._passive_angle = 0.0
    widget._passive_extra_y = 0.0


def tick_drain(widget) -> None:
    """Steely drops to the bottom (drain), then pops back up (ball save)."""
    t = widget._passive_t
    max_y = widget._th * 0.35
    cycle_t = t % 4.5
    if cycle_t < 0.8:
        progress = cycle_t / 0.8
        widget._passive_extra_y = progress * progress * max_y
    elif cycle_t < 2.0:
        widget._passive_extra_y = max_y
    elif cycle_t < 2.5:
        progress = (cycle_t - 2.0) / 0.5
        eased = math.sin(progress * math.pi / 2)
        widget._passive_extra_y = max_y * (1.0 - eased)
    elif cycle_t < 3.0:
        # Small bounce
        progress = (cycle_t - 2.5) / 0.5
        widget._passive_extra_y = math.sin(progress * math.pi) * max_y * 0.15
    else:
        widget._passive_extra_y = 0.0
    widget._passive_extra_x = 0.0
    widget._passive_angle = 0.0


def tick_multiball(widget) -> None:
    """Initialise ghost-ball particles for the multiball overlay."""
    if not widget._ghost_particles:
        tw = float(widget._tw)
        th = float(widget._th)
        widget._ghost_particles = [
            {"x_off": -tw * 0.38, "y_off": -th * 0.28, "phase": 0.0,  "alpha": 0},
            {"x_off":  tw * 0.38, "y_off": -th * 0.18, "phase": 1.3,  "alpha": 0},
            {"x_off":  tw * 0.10, "y_off":  th * 0.32, "phase": 2.6,  "alpha": 0},
        ]
    cycle_t = widget._passive_t % 5.0
    for ghost in widget._ghost_particles:
        phase_t = (cycle_t + ghost["phase"]) % 5.0
        if phase_t < 1.5:
            ghost["alpha"] = int(phase_t / 1.5 * 110)
        elif phase_t < 3.5:
            ghost["alpha"] = 110
        else:
            ghost["alpha"] = int(max(0.0, (1.0 - (phase_t - 3.5) / 1.5) * 110))
    widget._passive_extra_x = 0.0
    widget._passive_extra_y = 0.0
    widget._passive_angle = 0.0


def tick_plunger_launch(widget) -> None:
    """Steely compresses briefly then launches upward like a plunger shot."""
    t = widget._passive_t
    max_y = widget._th * 0.45
    cycle_t = t % 4.5
    if cycle_t < 0.2:
        # Compress downward
        widget._passive_extra_y = (cycle_t / 0.2) * max_y * 0.22
    elif cycle_t < 0.55:
        # Launch upward
        progress = (cycle_t - 0.2) / 0.35
        eased = math.sin(progress * math.pi / 2)
        widget._passive_extra_y = max_y * 0.22 - eased * max_y
    elif cycle_t < 1.1:
        # Fall back
        progress = (cycle_t - 0.55) / 0.55
        widget._passive_extra_y = -max_y * (1.0 - progress * progress)
    elif cycle_t < 1.5:
        # Land bounce
        progress = (cycle_t - 1.1) / 0.4
        widget._passive_extra_y = math.sin(progress * math.pi) * max_y * 0.14
    else:
        widget._passive_extra_y = 0.0
    widget._passive_extra_x = 0.0
    widget._passive_angle = 0.0


def tick_ramp_jump(widget) -> None:
    """Short arc-jump like rolling up a ramp and landing."""
    t = widget._passive_t
    max_x = widget._tw * 0.32
    max_y = widget._th * 0.38
    cycle_t = t % 4.5
    if cycle_t < 1.6:
        progress = cycle_t / 1.6
        widget._passive_extra_x = progress * max_x
        widget._passive_extra_y = -max_y * math.sin(progress * math.pi)
        widget._passive_angle = progress * 200.0
    elif cycle_t < 2.8:
        progress = (cycle_t - 1.6) / 1.2
        widget._passive_extra_x = max_x * (1.0 - progress)
        widget._passive_extra_y = 0.0
        widget._passive_angle = 200.0 * (1.0 - progress)
    else:
        widget._passive_extra_x = 0.0
        widget._passive_extra_y = 0.0
        widget._passive_angle = 0.0


def tick_tilt_warning(widget) -> None:
    """Steely rolls to one side, vibrates with TILT flash, then recovers."""
    t = widget._passive_t
    max_x = widget._tw * 0.28
    cycle_t = t % 7.0
    if cycle_t < 1.0:
        eased = math.sin(cycle_t / 1.0 * math.pi / 2)
        widget._passive_extra_x = eased * max_x
        widget._passive_angle = eased * max_x * 0.9
    elif cycle_t < 3.5:
        # Hold with vibration
        widget._passive_extra_x = max_x + math.sin(cycle_t * 22) * 2.0
        widget._passive_angle = max_x * 0.9
    elif cycle_t < 5.0:
        eased = math.cos((cycle_t - 3.5) / 1.5 * math.pi / 2)
        widget._passive_extra_x = eased * max_x
        widget._passive_angle = eased * max_x * 0.9
    else:
        widget._passive_extra_x = 0.0
        widget._passive_angle = 0.0
    widget._passive_extra_y = 0.0


def tick_flipper_catch(widget) -> None:
    """Steely balances on a flipper then flips upward."""
    t = widget._passive_t
    max_y_up = widget._th * 0.38
    sink_y = widget._th * 0.18
    cycle_t = t % 5.5
    if cycle_t < 1.5:
        # Descend to flipper
        progress = cycle_t / 1.5
        widget._passive_extra_y = math.sin(progress * math.pi / 2) * sink_y
        widget._passive_angle = math.sin(progress * math.pi) * 8.0
    elif cycle_t < 2.5:
        # Balance on flipper — slight wobble
        widget._passive_extra_y = sink_y
        widget._passive_angle = 5.0 + math.sin(cycle_t * 4.0) * 3.0
    elif cycle_t < 3.1:
        # Flip up!
        progress = (cycle_t - 2.5) / 0.6
        eased = math.sin(progress * math.pi / 2)
        widget._passive_extra_y = sink_y - eased * (sink_y + max_y_up)
        widget._passive_angle = 0.0
    elif cycle_t < 4.2:
        # Come back down
        progress = (cycle_t - 3.1) / 1.1
        widget._passive_extra_y = -max_y_up * (1.0 - progress * progress)
        widget._passive_angle = 0.0
    else:
        widget._passive_extra_y = 0.0
        widget._passive_angle = 0.0
    widget._passive_extra_x = 0.0


# ---------------------------------------------------------------------------
# Shared centre helper (tracks the animated ball position incl. bob/jump)
# ---------------------------------------------------------------------------

def _steely_center(widget):
    """Return (cx, cy, tw, th, pad) tracking the animated ball centre.

    Mirrors the bob/jump/wiggle/passive-extra transforms from paintEvent so
    that overlay props drawn relative to (cx, cy) follow the ball.
    """
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    base_cx = tw // 2 + pad
    base_cy = th // 2 + int(th * 0.20) + pad

    state = getattr(widget, '_state', 'idle')
    passive_mode = getattr(widget, '_passive_mode', '')
    bob_t = getattr(widget, '_bob_t', 0.0)
    if state == 'idle' and passive_mode in ("rubber_bounce", "rubber_ring_bounce"):
        bob = -abs(math.sin(bob_t * 2.0)) * 10.0
    else:
        bob = math.sin(bob_t) * 3.0

    jump = getattr(widget, '_jump_offset', 0.0) if getattr(widget, '_jumping', False) else 0.0

    wiggle_t = getattr(widget, '_wiggle_t', 0.0)
    wiggle_x = math.sin(wiggle_t) * 4.0 if state == 'surprised' else 0.0

    extra_x = getattr(widget, '_passive_extra_x', 0.0)
    extra_y = getattr(widget, '_passive_extra_y', 0.0)

    cx = base_cx + int(wiggle_x + extra_x)
    cy = base_cy + int(bob + jump + extra_y)
    return cx, cy, tw, th, pad


# ---------------------------------------------------------------------------
# Passive mode draw (overlay) helpers — called from _PinballDrawWidget.paintEvent()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Passive mode draw (overlay) helpers — new pinball prop overlays
# ---------------------------------------------------------------------------

def draw_multiball(p: QPainter, widget) -> None:
    """Draw full 3D sphere-shaded ghost-ball copies around the main mascot."""
    particles = getattr(widget, "_ghost_particles", [])
    if not particles:
        return
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for ghost in particles:
        alpha = ghost["alpha"]
        if alpha <= 5:
            continue
        gx = cx + int(ghost["x_off"])
        gy = cy + int(ghost["y_off"])
        r = radius

        # 3. Drop shadow under each ghost ball
        p.setOpacity(0.25)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(gx - r + 2, gy - r + 3, r * 2, r * 2)
        p.setOpacity(1.0)

        # 1. Main sphere: 5-stop radial gradient (highlight upper-left → dark edge)
        grad = QRadialGradient(float(gx - r // 4), float(gy - r // 3), float(r * 1.2))
        grad.setColorAt(0.00, QColor(230, 232, 245, alpha))
        grad.setColorAt(0.25, QColor(195, 200, 218, int(alpha * 0.95)))
        grad.setColorAt(0.50, QColor(155, 163, 180, int(alpha * 0.85)))
        grad.setColorAt(0.75, QColor(95,  103, 122, int(alpha * 0.65)))
        grad.setColorAt(1.00, QColor(45,   55,  75, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(gx - r, gy - r, r * 2, r * 2)

        # 4. Specular highlight upper-left
        spec = QRadialGradient(float(gx - r // 3), float(gy - r // 3), float(r * 0.4))
        spec.setColorAt(0.0, QColor(255, 255, 255, int(180 * alpha / 255)))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(spec)
        p.drawEllipse(gx - r // 2, gy - r // 2, r, r)

        # 4. Rim light lower-right
        rim = QRadialGradient(float(gx + r // 3), float(gy + r // 3), float(r * 0.5))
        rim.setColorAt(0.0, QColor(120, 180, 255, int(alpha * 0.35)))
        rim.setColorAt(1.0, QColor(120, 180, 255, 0))
        p.setBrush(rim)
        p.drawEllipse(gx, gy, r, r)

        # 6. Environment reflection stripe
        env = QLinearGradient(float(gx - r), float(gy - r),
                              float(gx + r * 0.7), float(gy + r * 0.7))
        env.setColorAt(0.0, QColor(255, 255, 255, 0))
        env.setColorAt(0.4, QColor(255, 255, 255, int(38 * alpha / 255)))
        env.setColorAt(0.6, QColor(255, 255, 255, int(38 * alpha / 255)))
        env.setColorAt(1.0, QColor(255, 255, 255, 0))
        clip = QPainterPath()
        clip.addEllipse(QRectF(float(gx - r), float(gy - r), float(r * 2), float(r * 2)))
        p.save()
        p.setClipPath(clip)
        p.setBrush(env)
        p.drawEllipse(gx - r, gy - r, r * 2, r * 2)
        p.restore()

    p.restore()


def draw_tilt_warning(p: QPainter, widget) -> None:
    """Flash 'TILT' text with double-layer glow while in the tilt_warning phase."""
    t = widget._passive_t
    cycle_t = t % 7.0
    # Only flash during the hold/tilt phase (1.0–3.5 s)
    if not (1.0 <= cycle_t < 3.5):
        return
    flash_alpha = int(140 + 110 * abs(math.sin(cycle_t * 5.0)))
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    text = "TILT"

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    font_big = QFont("Arial Black", max(10, tw // 5), QFont.Weight.Black)
    font_sharp = QFont("Arial Black", max(8, tw // 6), QFont.Weight.Black)
    p.setFont(font_big)
    fm = p.fontMetrics()
    text_w = fm.horizontalAdvance(text)
    text_h = fm.height()
    ty = cy - int(th * 0.3) - text_h

    # 5. Glow layer via CompositionMode_Plus
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setPen(QColor(200, 40, 10, int(flash_alpha * 0.55)))
    p.drawText(cx - text_w // 2, ty, text)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # Sharp top layer
    p.setFont(font_sharp)
    fm2 = p.fontMetrics()
    text_w2 = fm2.horizontalAdvance(text)
    p.setPen(QColor(255, 60, 20, flash_alpha))
    p.drawText(cx - text_w2 // 2, ty, text)

    # 7. Bevel on text bounding box
    bx, bw, bh = cx - text_w2 // 2 - 2, text_w2 + 4, text_h + 4
    p.setPen(QPen(QColor(255, 255, 255, 50), 1))
    p.drawLine(bx, ty - bh + 2, bx + bw, ty - bh + 2)
    p.drawLine(bx, ty - bh + 2, bx, ty + 2)
    p.setPen(QPen(QColor(0, 0, 0, 50), 1))
    p.drawLine(bx, ty + 2, bx + bw, ty + 2)
    p.drawLine(bx + bw, ty - bh + 2, bx + bw, ty + 2)
    p.restore()


# ---------------------------------------------------------------------------
# Event animation draw (overlay) helpers — first-pass versions
# (kept for legacy call sites; updated section follows below)
# ---------------------------------------------------------------------------

def draw_event_jackpot_glow(p: QPainter, widget) -> None:
    """Gold glow ring and sparkles with CompositionMode_Plus glow."""
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["jackpot_glow"]
    fade = max(0.0, 1.0 - t / duration)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    glow_r = int(radius * (1.25 + 0.12 * math.sin(t * 6.0)))
    glow_alpha = int(130 * fade)
    if glow_alpha > 0:
        # 5. CompositionMode_Plus for glow ring
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        glow = QRadialGradient(float(cx), float(cy), float(glow_r * 1.5))
        glow.setColorAt(0.0, QColor(255, 230, 80, glow_alpha))
        glow.setColorAt(0.3, QColor(255, 220, 50, glow_alpha))
        glow.setColorAt(0.6, QColor(255, 180, 20, glow_alpha // 2))
        glow.setColorAt(0.8, QColor(200, 120, 0,  glow_alpha // 4))
        glow.setColorAt(1.0, QColor(255, 150, 0,  0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    for sp in getattr(widget, "_jackpot_particles", []):
        sp_x = cx + int(math.cos(sp["angle"]) * sp["dist"])
        sp_y = cy + int(math.sin(sp["angle"]) * sp["dist"])
        size = sp["size"] * fade
        alpha = int(sp["alpha"] * fade)
        if alpha <= 0 or size < 0.5:
            continue
        star = QPainterPath()
        star.moveTo(sp_x, sp_y - size)
        star.lineTo(sp_x + size * 0.35, sp_y - size * 0.35)
        star.lineTo(sp_x + size, sp_y)
        star.lineTo(sp_x + size * 0.35, sp_y + size * 0.35)
        star.lineTo(sp_x, sp_y + size)
        star.lineTo(sp_x - size * 0.35, sp_y + size * 0.35)
        star.lineTo(sp_x - size, sp_y)
        star.lineTo(sp_x - size * 0.35, sp_y - size * 0.35)
        star.closeSubpath()
        # 5. Sparkle glow
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.fillPath(star, QColor(255, 240, 80, alpha))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    p.restore()


def draw_event_victory_lap(p: QPainter, widget) -> None:
    """Draw a 3D tube-effect motion trail arc while Steely circles on victory lap."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["victory_lap"]
    if t > duration * 0.95:
        return
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    trail_alpha = int(80 * max(0.0, 1.0 - t / duration))
    if trail_alpha <= 0:
        return
    rx = int(tw * 0.30)
    ry = int(th * 0.22)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 3. Drop shadow for rail
    p.setOpacity(0.18)
    p.setPen(QPen(QColor(0, 0, 0, 60), max(4, radius // 4) + 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(cx - rx + 2, cy - ry + 3, rx * 2, ry * 2)
    p.setOpacity(1.0)

    # 7. Outer bevel (dark)
    p.setPen(QPen(QColor(0, 0, 0, 60), max(2, radius // 4) + 2))
    p.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)

    # 1. Tube rail: bright center stroke
    pen = QPen(QColor(180, 220, 255, trail_alpha), max(2, radius // 4))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)

    # 6. Environment reflection highlight on rail
    p.setPen(QPen(QColor(255, 255, 255, int(trail_alpha * 0.55)), max(1, radius // 8)))
    p.drawEllipse(cx - rx + 2, cy - ry + 2, (rx - 2) * 2, (ry - 2) * 2)

    p.restore()


def draw_event_drain_fall(p: QPainter, widget) -> None:
    """Sad expression overlay during drain_fall re-entry."""
    t = widget._event_anim_t
    if not (1.6 <= t < 2.4):
        return
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    p.save()
    font = QFont("Arial", max(7, tw // 9))
    p.setFont(font)
    alpha = int(180 * min(1.0, (t - 1.6) / 0.3))
    p.setPen(QColor(100, 160, 255, alpha))
    p.drawText(cx - 12, cy - int(th * 0.55), ":(")
    p.restore()


def draw_event_overheat(p: QPainter, widget) -> None:
    """Red heat tint and rising smoke puffs during overheat."""
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["overheat"]
    fade = max(0.0, 1.0 - t / duration)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    heat_alpha = int(90 * fade * (0.7 + 0.3 * math.sin(t * 8.0)))
    if heat_alpha > 0:
        # 5. CompositionMode_Plus for heat glow
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        heat = QRadialGradient(float(cx), float(cy), float(radius * 1.4))
        heat.setColorAt(0.0, QColor(255, 100, 30, heat_alpha))
        heat.setColorAt(0.4, QColor(255, 80,  20, heat_alpha))
        heat.setColorAt(0.7, QColor(200, 40,  0,  heat_alpha // 2))
        heat.setColorAt(1.0, QColor(255, 40,  0,  0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(heat)
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    for puff in getattr(widget, "_smoke_particles", []):
        if t < puff["delay"]:
            continue
        alpha = int(puff["alpha"] * fade)
        if alpha <= 0:
            continue
        sx = cx + int(puff["x_off"])
        sy = cy - radius + int(puff["y"])
        sz = int(puff["size"])
        smoke_grad = QRadialGradient(float(sx), float(sy), float(sz))
        smoke_grad.setColorAt(0.0, QColor(210, 140, 90, alpha))
        smoke_grad.setColorAt(0.5, QColor(180, 110, 70, alpha // 2))
        smoke_grad.setColorAt(1.0, QColor(180, 110, 70, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(smoke_grad)
        p.drawEllipse(sx - sz, sy - sz, sz * 2, sz * 2)

    p.restore()


def draw_event_rust(p: QPainter, widget) -> None:
    """Desaturation/rust overlay based on _rust_amount (0=fresh, 1=rusty)."""
    amount = getattr(widget, "_rust_amount", 0.0)
    if amount < 0.05:
        return
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    tint_alpha = int(min(120, amount * 130))
    p.setPen(Qt.PenStyle.NoPen)
    # 1. Multi-stop rust tint gradient
    rust_grad = QRadialGradient(float(cx), float(cy), float(radius))
    rust_grad.setColorAt(0.0, QColor(160, 80,  20, tint_alpha))
    rust_grad.setColorAt(0.4, QColor(150, 70,  15, tint_alpha))
    rust_grad.setColorAt(0.7, QColor(130, 55,  10, int(tint_alpha * 0.8)))
    rust_grad.setColorAt(1.0, QColor(100, 40,   5, int(tint_alpha * 0.5)))
    p.setBrush(rust_grad)
    p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

    random.seed(42)
    for _ in range(int(amount * 8)):
        rx_off = random.randint(-radius + 4, radius - 4)
        ry_off = random.randint(-radius + 4, radius - 4)
        if rx_off * rx_off + ry_off * ry_off > (radius - 3) ** 2:
            continue
        dot_alpha = int(amount * 160)
        sz = random.randint(2, 4)
        # 3. Small shadow under each rust dot
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawEllipse(cx + rx_off - sz + 1, cy + ry_off - sz + 1, sz * 2, sz * 2)
        p.setBrush(QColor(140, 55, 10, dot_alpha))
        p.drawEllipse(cx + rx_off - sz, cy + ry_off - sz, sz * 2, sz * 2)
    random.seed()
    p.restore()


def draw_event_show_off(p: QPainter, widget) -> None:
    """Polish sparkles on the ball body and mustache glow."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["show_off"]
    fade = max(0.0, 1.0 - t / duration)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    sheen_alpha = int(90 * fade * abs(math.sin(t * 4.0)))
    if sheen_alpha > 0:
        sheen = QLinearGradient(
            float(cx - radius), float(cy - radius),
            float(cx + radius), float(cy + radius),
        )
        sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.4, QColor(255, 255, 255, sheen_alpha))
        sheen.setColorAt(0.5, QColor(255, 255, 255, sheen_alpha))
        sheen.setColorAt(0.6, QColor(255, 255, 255, int(sheen_alpha * 0.6)))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        # 5. CompositionMode_Plus for sheen
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setBrush(sheen)
        clip = QPainterPath()
        clip.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        p.setClipPath(clip)
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        p.setClipping(False)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    eye_y = cy - radius // 5
    eye_r = max(3, radius // 4)
    moustache_y = eye_y + eye_r + 3
    for side in (-1, 1):
        for i in range(3):
            sx = cx + side * (radius // 3 + i * 4)
            sy = moustache_y - i * 2
            alpha = int(fade * (200 - i * 40) * abs(math.sin(t * 5.0 + i)))
            if alpha > 0:
                p.setPen(Qt.PenStyle.NoPen)
                # 5. Sparkle glow
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
                p.setBrush(QColor(255, 240, 80, alpha))
                p.drawEllipse(sx - 2, sy - 2, 4, 4)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    p.restore()


def draw_event_nervous(p: QPainter, widget) -> None:
    """Wide sweat drops during nervous personality animation."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["nervous"]
    if t > duration:
        return
    intensity = min(1.0, t / 2.0)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    sweat_alpha = int(intensity * 180)
    if sweat_alpha > 5:
        for side in (-1, 1):
            sx = cx + side * (radius // 2 - 2)
            sy = cy - radius + 3 + int(intensity * 5)
            # 3. Drop shadow under sweat drop
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 25))
            sweat_shad = QPainterPath()
            sweat_shad.moveTo(float(sx + 1), float(sy + 1))
            sweat_shad.lineTo(float(sx - 2), float(sy + 7))
            sweat_shad.lineTo(float(sx + 4), float(sy + 7))
            sweat_shad.closeSubpath()
            p.fillPath(sweat_shad, QColor(0, 0, 0, 25))
            # Sweat drop with gradient
            sweat = QPainterPath()
            sweat.moveTo(float(sx), float(sy))
            sweat.lineTo(float(sx - 3), float(sy + 6))
            sweat.lineTo(float(sx + 3), float(sy + 6))
            sweat.closeSubpath()
            sweat_grad = QLinearGradient(float(sx - 3), float(sy), float(sx + 3), float(sy + 6))
            sweat_grad.setColorAt(0.0, QColor(180, 220, 255, sweat_alpha))
            sweat_grad.setColorAt(0.5, QColor(100, 180, 255, sweat_alpha))
            sweat_grad.setColorAt(1.0, QColor(60,  140, 220, int(sweat_alpha * 0.7)))
            p.fillPath(sweat, sweat_grad)
            # 4. Specular highlight on sweat drop
            p.setBrush(QColor(255, 255, 255, int(sweat_alpha * 0.5)))
            p.drawEllipse(sx - 1, sy, 2, 2)

    p.restore()


def draw_event_plunger_entry(p: QPainter, widget) -> None:
    """Motion blur streak below Steely during the plunger-entry launch."""
    t = widget._event_anim_t
    if not (0.25 <= t < 1.1):
        return
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    progress = (t - 0.25) / 0.85
    streak_alpha = int(120 * (1.0 - progress))
    streak_len = int(radius * 2.5 * (1.0 - progress))
    if streak_alpha <= 0 or streak_len <= 0:
        return
    streak_w = max(4, radius // 2)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 1. 5-stop metallic streak gradient
    grad = QLinearGradient(float(cx), float(cy + radius),
                           float(cx), float(cy + radius + streak_len))
    grad.setColorAt(0.00, QColor(200, 215, 240, streak_alpha))
    grad.setColorAt(0.25, QColor(180, 200, 230, int(streak_alpha * 0.85)))
    grad.setColorAt(0.50, QColor(160, 185, 220, int(streak_alpha * 0.65)))
    grad.setColorAt(0.75, QColor(140, 165, 200, int(streak_alpha * 0.40)))
    grad.setColorAt(1.00, QColor(120, 150, 190, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRect(cx - streak_w // 2, cy + radius, streak_w, streak_len)

    # 6. Environment reflection centre line
    env = QLinearGradient(float(cx), float(cy + radius),
                          float(cx), float(cy + radius + streak_len))
    env.setColorAt(0.0, QColor(255, 255, 255, int(streak_alpha * 0.45)))
    env.setColorAt(0.5, QColor(255, 255, 255, int(streak_alpha * 0.20)))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(env)
    p.drawRect(cx - streak_w // 4, cy + radius, streak_w // 2, streak_len)

    p.restore()


# ---------------------------------------------------------------------------
# Passive mode draw (overlay) helpers — pinball prop overlays
# ---------------------------------------------------------------------------

def draw_plunger_launch(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    t = widget._passive_t
    extra_y = widget._passive_extra_y

    plunger_x = cx
    base_y = cy + int(th * 0.42)
    compress = max(0.0, extra_y / (th * 0.22)) if extra_y > 0 else 0.0
    rod_h = int(th * 0.30)
    rod_y = base_y - int(compress * th * 0.08)
    rod_w = 10

    # 3. Drop shadow under entire mechanism
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(plunger_x - rod_w // 2 + 3, rod_y + 3, rod_w, rod_h)
    p.setOpacity(1.0)

    # 1. Plunger rod: 5-stop metallic gradient (dark-mid-bright-mid-dark)
    grad = QLinearGradient(float(plunger_x - rod_w // 2), 0.0,
                           float(plunger_x + rod_w // 2), 0.0)
    grad.setColorAt(0.00, QColor(0x50, 0x58, 0x68))
    grad.setColorAt(0.25, QColor(0xA0, 0xA8, 0xB8))
    grad.setColorAt(0.50, QColor(0xFF, 0xFF, 0xFF))
    grad.setColorAt(0.75, QColor(0xA0, 0xA8, 0xB8))
    grad.setColorAt(1.00, QColor(0x50, 0x58, 0x68))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRect(plunger_x - rod_w // 2, rod_y, rod_w, rod_h)

    # 6. Environment reflection stripe on rod
    env = QLinearGradient(float(plunger_x - rod_w // 2), float(rod_y),
                          float(plunger_x + rod_w // 2), float(rod_y + rod_h * 0.7))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 38))
    env.setColorAt(0.6, QColor(255, 255, 255, 38))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(env)
    p.drawRect(plunger_x - rod_w // 2, rod_y, rod_w, rod_h)

    # 7. Bevel on rod
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(plunger_x - rod_w // 2, rod_y, plunger_x + rod_w // 2, rod_y)
    p.drawLine(plunger_x - rod_w // 2, rod_y, plunger_x - rod_w // 2, rod_y + rod_h)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(plunger_x - rod_w // 2, rod_y + rod_h, plunger_x + rod_w // 2, rod_y + rod_h)
    p.drawLine(plunger_x + rod_w // 2, rod_y, plunger_x + rod_w // 2, rod_y + rod_h)

    # Spring coils with 2. QConicalGradient shading
    spring_h = int(th * 0.12) - int(compress * th * 0.08)
    spring_h = max(4, spring_h)
    coil_count = 6
    for i in range(coil_count):
        y0 = rod_y + rod_h + int(i * spring_h / coil_count)
        y1 = y0 + int(spring_h / coil_count)
        mid_y = (y0 + y1) // 2
        coil_cx = float(plunger_x)
        coil_cy = float(mid_y)
        cg = QConicalGradient(coil_cx, coil_cy, 0.0)
        cg.setColorAt(0.0,  QColor(0xFF, 0xE8, 0x20))
        cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0x80))
        cg.setColorAt(0.5,  QColor(0xC0, 0xA0, 0x00))
        cg.setColorAt(0.75, QColor(0xFF, 0xE8, 0x20))
        cg.setColorAt(1.0,  QColor(0xFF, 0xE8, 0x20))
        ox = 5 if i % 2 == 0 else -5
        p.setPen(QPen(cg, 2))
        p.drawLine(plunger_x - 5, y0, plunger_x + ox, mid_y)
        p.drawLine(plunger_x + ox, mid_y, plunger_x - 5 + 10, y1)

    # 2+4. Rounded tip: QConicalGradient + specular highlight
    tip_cx = float(plunger_x)
    tip_cy = float(rod_y - 2)
    cg_tip = QConicalGradient(tip_cx, tip_cy, 0.0)
    cg_tip.setColorAt(0.0,  QColor(0xC0, 0xC8, 0xD8))
    cg_tip.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF))
    cg_tip.setColorAt(0.5,  QColor(0x80, 0x88, 0x98))
    cg_tip.setColorAt(0.75, QColor(0xE0, 0xE0, 0xE8))
    cg_tip.setColorAt(1.0,  QColor(0xC0, 0xC8, 0xD8))
    p.setPen(QPen(QColor(0x50, 0x58, 0x68), 1))
    p.setBrush(cg_tip)
    p.drawEllipse(plunger_x - 7, rod_y - 5, 14, 10)
    # Specular
    spec = QRadialGradient(float(plunger_x - 2), float(rod_y - 4), 4.0)
    spec.setColorAt(0.0, QColor(255, 255, 255, 180))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawEllipse(plunger_x - 5, rod_y - 6, 7, 5)

    p.restore()


def draw_bumper_hit(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    t = widget._passive_t
    cycle_t = t % 3.5
    active_idx = int(cycle_t / (3.5 / 3))

    bumper_positions = [
        (cx - int(tw * 0.35), cy - int(th * 0.30)),
        (cx + int(tw * 0.35), cy - int(th * 0.30)),
        (cx + int(tw * 0.40), cy + int(th * 0.05)),
    ]
    br = max(6, int(tw * 0.10))

    for i, (bx, by) in enumerate(bumper_positions):
        is_active = (i == active_idx)

        # 3. Drop shadow
        p.setOpacity(0.25)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(bx - br + 2, by - br + 3, br * 2, br * 2)
        p.setOpacity(1.0)

        # 5. Active glow via CompositionMode_Plus
        if is_active:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            glow = QRadialGradient(float(bx), float(by), float(br * 2.5))
            glow.setColorAt(0.0, QColor(255, 240, 0, 160))
            glow.setColorAt(0.4, QColor(255, 200, 0, 100))
            glow.setColorAt(0.7, QColor(255, 160, 0, 50))
            glow.setColorAt(1.0, QColor(255, 140, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(bx - br * 2, by - br * 2, br * 4, br * 4)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # 1. Dome: 5-stop radial gradient with highlight spot upper-left
        if is_active:
            dome_grad = QRadialGradient(float(bx - br // 3), float(by - br // 3), float(br * 1.3))
            dome_grad.setColorAt(0.00, QColor(255, 255, 200))
            dome_grad.setColorAt(0.25, QColor(255, 230, 140))
            dome_grad.setColorAt(0.50, QColor(240, 200,  80))
            dome_grad.setColorAt(0.75, QColor(200, 150,  40))
            dome_grad.setColorAt(1.00, QColor(140,  80,  10))
        else:
            dome_grad = QRadialGradient(float(bx - br // 3), float(by - br // 3), float(br * 1.3))
            dome_grad.setColorAt(0.00, QColor(255, 255, 255))
            dome_grad.setColorAt(0.25, QColor(220, 220, 228))
            dome_grad.setColorAt(0.50, QColor(180, 184, 196))
            dome_grad.setColorAt(0.75, QColor(130, 138, 155))
            dome_grad.setColorAt(1.00, QColor(80,  88, 108))
        p.setPen(QPen(QColor(0xCC, 0x18, 0x18), 3 if is_active else 2))
        p.setBrush(dome_grad)
        p.drawEllipse(bx - br, by - br, br * 2, br * 2)

        # 2. Ring base: QConicalGradient for metallic ring
        cg = QConicalGradient(float(bx), float(by), 30.0)
        cg.setColorAt(0.0,  QColor(0xC0, 0xC8, 0xD8))
        cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF))
        cg.setColorAt(0.5,  QColor(0x80, 0x88, 0x98))
        cg.setColorAt(0.75, QColor(0xE0, 0xE0, 0xE8))
        cg.setColorAt(1.0,  QColor(0xC0, 0xC8, 0xD8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(cg, 2))
        inner_r = br - 3
        p.drawEllipse(bx - inner_r, by - inner_r, inner_r * 2, inner_r * 2)

        # 4. Specular highlight
        spec = QRadialGradient(float(bx - br // 3), float(by - br // 3), float(br * 0.4))
        spec.setColorAt(0.0, QColor(255, 255, 255, 180))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(spec)
        p.drawEllipse(bx - br // 2, by - br // 2, br, br)

        # 6. Environment reflection
        env = QLinearGradient(float(bx - br), float(by - br),
                              float(bx + br * 0.7), float(by + br * 0.7))
        env.setColorAt(0.0, QColor(255, 255, 255, 0))
        env.setColorAt(0.4, QColor(255, 255, 255, 38))
        env.setColorAt(0.6, QColor(255, 255, 255, 38))
        env.setColorAt(1.0, QColor(255, 255, 255, 0))
        clip = QPainterPath()
        clip.addEllipse(QRectF(float(bx - br), float(by - br), float(br * 2), float(br * 2)))
        p.save()
        p.setClipPath(clip)
        p.setBrush(env)
        p.drawEllipse(bx - br, by - br, br * 2, br * 2)
        p.restore()

        # 7. Bevel on bumper skirt
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawArc(bx - br, by - br, br * 2, br * 2, 45 * 16, 180 * 16)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.drawArc(bx - br, by - br, br * 2, br * 2, 225 * 16, 180 * 16)

    p.restore()


def draw_flipper_catch(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    t = widget._passive_t
    cycle_t = t % 5.5
    extra_y = widget._passive_extra_y

    if 2.5 <= cycle_t < 3.1:
        flip_angle = -45.0 * ((cycle_t - 2.5) / 0.6)
    elif cycle_t < 2.5 and extra_y > 0:
        flip_angle = 10.0
    else:
        flip_angle = 0.0

    flipper_cx = cx
    flipper_cy = cy + int(th * 0.40)
    flipper_len = int(tw * 0.40)
    flipper_w = max(6, th // 12)

    # 3. Drop shadow under flipper
    p.save()
    p.translate(flipper_cx + 2, flipper_cy + 3)
    p.rotate(flip_angle)
    shad_path = QPainterPath()
    shad_path.moveTo(-flipper_len // 2, -flipper_w // 2)
    shad_path.lineTo(flipper_len // 2, -flipper_w // 4)
    shad_path.lineTo(flipper_len // 2, flipper_w // 4)
    shad_path.lineTo(-flipper_len // 2, flipper_w // 2)
    shad_path.closeSubpath()
    p.setOpacity(0.25)
    p.fillPath(shad_path, QColor(0, 0, 0, 60))
    p.setOpacity(1.0)
    p.restore()

    p.save()
    p.translate(flipper_cx, flipper_cy)
    p.rotate(flip_angle)

    path = QPainterPath()
    path.moveTo(-flipper_len // 2, -flipper_w // 2)
    path.lineTo(flipper_len // 2, -flipper_w // 4)
    path.lineTo(flipper_len // 2, flipper_w // 4)
    path.lineTo(-flipper_len // 2, flipper_w // 2)
    path.closeSubpath()

    # 1. 5-stop gradient for volume (bright top, dark bottom)
    grad = QLinearGradient(0.0, float(-flipper_w // 2), 0.0, float(flipper_w // 2))
    grad.setColorAt(0.00, QColor(140, 145, 160))
    grad.setColorAt(0.20, QColor(90,  95, 108))
    grad.setColorAt(0.50, QColor(55,  60,  72))
    grad.setColorAt(0.80, QColor(30,  35,  48))
    grad.setColorAt(1.00, QColor(15,  18,  28))
    p.fillPath(path, grad)

    # 6. Environment reflection stripe
    env = QLinearGradient(float(-flipper_len // 2), float(-flipper_w // 2),
                          float(flipper_len * 0.35), float(flipper_w * 0.35))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 38))
    env.setColorAt(0.6, QColor(255, 255, 255, 38))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.save()
    p.setClipPath(path)
    p.setBrush(env)
    p.setPen(Qt.PenStyle.NoPen)
    bnd = path.boundingRect()
    p.drawRect(bnd)
    p.restore()

    # 7. Bevel on flipper edges
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(-flipper_len // 2, -flipper_w // 2,
               flipper_len // 2,  -flipper_w // 4)
    p.drawLine(-flipper_len // 2, -flipper_w // 2,
               -flipper_len // 2,  flipper_w // 2)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(-flipper_len // 2, flipper_w // 2,
               flipper_len // 2,  flipper_w // 4)
    p.drawLine(flipper_len // 2, -flipper_w // 4,
               flipper_len // 2,  flipper_w // 4)

    # Chrome edge outline
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    # 2. Chrome pivot bolt: QConicalGradient + specular
    cg = QConicalGradient(0.0, 0.0, 0.0)
    cg.setColorAt(0.0,  QColor(0xC0, 0xC8, 0xD8))
    cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF))
    cg.setColorAt(0.5,  QColor(0x80, 0x88, 0x98))
    cg.setColorAt(0.75, QColor(0xE0, 0xE0, 0xE8))
    cg.setColorAt(1.0,  QColor(0xC0, 0xC8, 0xD8))
    p.setPen(QPen(QColor(0x50, 0x58, 0x68), 1))
    p.setBrush(cg)
    p.drawEllipse(-5, -5, 10, 10)
    # Specular on pivot
    spec = QRadialGradient(-2.0, -2.0, 3.0)
    spec.setColorAt(0.0, QColor(255, 255, 255, 180))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawEllipse(-4, -4, 5, 5)

    p.restore()
    p.restore()


def draw_ramp_jump(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad

    ramp_x0 = pad
    ramp_y0 = th + pad - int(th * 0.08)
    ramp_x1 = cx + int(tw * 0.25)
    ramp_y1 = th // 2 + pad
    ramp_w = max(3, th // 16)

    ramp_dx = ramp_x1 - ramp_x0
    ramp_dy = ramp_y1 - ramp_y0
    ramp_len = math.hypot(ramp_dx, ramp_dy)
    angle_rad = math.atan2(ramp_dy, ramp_dx)

    # 3. Drop shadow under ramp
    p.setOpacity(0.22)
    p.setPen(QPen(QColor(0, 0, 0, 60), ramp_w + 3))
    p.drawLine(ramp_x0 + 2, ramp_y0 + 3, ramp_x1 + 2, ramp_y1 + 3)
    p.setOpacity(1.0)

    # 1. Ramp walls: 5-stop metallic chrome gradient (using a linear pen along the ramp)
    perp_x = int(math.sin(angle_rad) * ramp_w * 2)
    perp_y = int(-math.cos(angle_rad) * ramp_w * 2)
    wall_grad = QLinearGradient(float(ramp_x0 - perp_x), float(ramp_y0 - perp_y),
                                float(ramp_x0 + perp_x), float(ramp_y0 + perp_y))
    wall_grad.setColorAt(0.00, QColor(0x50, 0x58, 0x68))
    wall_grad.setColorAt(0.25, QColor(0xA0, 0xA8, 0xB8))
    wall_grad.setColorAt(0.50, QColor(0xFF, 0x8C, 0x00))
    wall_grad.setColorAt(0.75, QColor(0xCC, 0x60, 0x00))
    wall_grad.setColorAt(1.00, QColor(0x80, 0x40, 0x00))
    p.setPen(QPen(wall_grad, ramp_w))
    p.drawLine(ramp_x0, ramp_y0, ramp_x1, ramp_y1)

    # Second parallel wall with bevel
    p.setPen(QPen(QColor(0xCC, 0x60, 0x00), ramp_w))
    p.drawLine(ramp_x0 + ramp_w + 2, ramp_y0, ramp_x1 + ramp_w + 2, ramp_y1)

    # 7. Bevel on ramp walls
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(ramp_x0, ramp_y0 - 1, ramp_x1, ramp_y1 - 1)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(ramp_x0 + ramp_w + 3, ramp_y0 + 1, ramp_x1 + ramp_w + 3, ramp_y1 + 1)

    # Lane arrows with 5. CompositionMode_Plus glow
    arrow_count = 3
    for i in range(arrow_count):
        t_pos = (i + 1) / (arrow_count + 1)
        ax = int(ramp_x0 + ramp_dx * t_pos)
        ay = int(ramp_y0 + ramp_dy * t_pos)
        arrow_len = max(5, int(ramp_len * 0.06))
        # Arrow glow
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(QPen(QColor(255, 255, 180, 120), 2))
        p.drawLine(ax, ay,
                   ax + int(math.cos(angle_rad) * arrow_len),
                   ay + int(math.sin(angle_rad) * arrow_len))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        # Arrow bright
        p.setPen(QPen(QColor(255, 255, 255, 200), 1))
        p.drawLine(ax, ay,
                   ax + int(math.cos(angle_rad) * arrow_len),
                   ay + int(math.sin(angle_rad) * arrow_len))
        p.drawLine(ax + int(math.cos(angle_rad) * arrow_len),
                   ay + int(math.sin(angle_rad) * arrow_len),
                   ax + int(math.cos(angle_rad - 0.5) * arrow_len // 2),
                   ay + int(math.sin(angle_rad - 0.5) * arrow_len // 2))

    p.restore()


def draw_drain(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    t = widget._passive_t
    extra_y = widget._passive_extra_y

    fall_fraction = min(1.0, extra_y / (th * 0.35)) if extra_y > 0 else 0.0
    drain_w = int((tw * 0.15) + fall_fraction * tw * 0.20)
    drain_h = int((th * 0.06) + fall_fraction * th * 0.08)
    drain_y = th + pad - drain_h // 2

    # 3. Drop shadow under drain
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawEllipse(cx - drain_w + 2, drain_y - drain_h // 2 + 3, drain_w * 2, drain_h)
    p.setOpacity(1.0)

    # Gutter channel: 1. 5-stop metallic gradient
    gutter_grad = QLinearGradient(float(cx - drain_w), float(drain_y),
                                  float(cx + drain_w), float(drain_y))
    gutter_grad.setColorAt(0.00, QColor(0x40, 0x44, 0x50))
    gutter_grad.setColorAt(0.25, QColor(0x70, 0x75, 0x85))
    gutter_grad.setColorAt(0.50, QColor(0x90, 0x98, 0xA8))
    gutter_grad.setColorAt(0.75, QColor(0x70, 0x75, 0x85))
    gutter_grad.setColorAt(1.00, QColor(0x40, 0x44, 0x50))
    p.setPen(QPen(gutter_grad, 2))
    p.drawLine(cx - drain_w, drain_y, cx + drain_w, drain_y)

    # 1. Drain hole: concentric QRadialGradient (dark center → lighter edge) for depth
    hole_grad = QRadialGradient(float(cx), float(drain_y), float(drain_w))
    hole_grad.setColorAt(0.00, QColor(5,   4,  10))
    hole_grad.setColorAt(0.25, QColor(10,  8,  18))
    hole_grad.setColorAt(0.50, QColor(18, 14,  28))
    hole_grad.setColorAt(0.75, QColor(28, 22,  40))
    hole_grad.setColorAt(1.00, QColor(38, 30,  50))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(hole_grad)
    p.drawEllipse(cx - drain_w, drain_y - drain_h // 2, drain_w * 2, drain_h)

    # 7. Metal rim bevel (bright top, dark bottom)
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawArc(cx - drain_w, drain_y - drain_h // 2, drain_w * 2, drain_h,
              0 * 16, 180 * 16)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawArc(cx - drain_w, drain_y - drain_h // 2, drain_w * 2, drain_h,
              180 * 16, 180 * 16)

    # Text
    cycle_t = t % 4.5
    if cycle_t >= 2.0:
        blink = int(t * 3) % 2 == 0
        text_color = QColor(0xFF, 0x20, 0x20, 220 if blink else 80)
        font = QFont("Arial Black", max(5, tw // 12), QFont.Weight.Black)
        p.setFont(font)
        p.setPen(text_color)
        label = "BALL SAVE" if cycle_t >= 2.0 else "DRAIN"
        fm = p.fontMetrics()
        p.drawText(cx - fm.horizontalAdvance(label) // 2, drain_y - drain_h - 2, label)

    p.restore()


def draw_spin_out(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    spin_angle = widget._passive_angle

    sp_cx = cx + int(tw * 0.38)
    sp_cy = cy - int(th * 0.05)
    sp_w = max(6, tw // 8)
    sp_h = max(3, th // 20)

    # 3. Drop shadow under spinner
    p.save()
    p.translate(sp_cx + 2, sp_cy + 3)
    p.rotate(spin_angle * 0.5)
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(-sp_w // 2, -sp_h // 2, sp_w, sp_h)
    p.setOpacity(1.0)
    p.restore()

    p.save()
    p.translate(sp_cx, sp_cy)
    p.rotate(spin_angle * 0.5)

    # 1. Paddle body: 5-stop metallic gradient
    pad_grad = QLinearGradient(float(-sp_w // 2), 0.0, float(sp_w // 2), 0.0)
    pad_grad.setColorAt(0.00, QColor(0x60, 0x68, 0x78))
    pad_grad.setColorAt(0.25, QColor(0xA8, 0xB0, 0xC0))
    pad_grad.setColorAt(0.50, QColor(0xFF, 0xFF, 0xFF))
    pad_grad.setColorAt(0.75, QColor(0xA8, 0xB0, 0xC0))
    pad_grad.setColorAt(1.00, QColor(0x60, 0x68, 0x78))
    p.setPen(QPen(QColor(0xB0, 0xB8, 0xC8), 1))
    p.setBrush(pad_grad)
    p.drawRect(-sp_w // 2, -sp_h // 2, sp_w, sp_h)

    # 4. Specular highlight stripe upper
    spec = QRadialGradient(float(-sp_w // 4), float(-sp_h // 4), float(sp_w * 0.35))
    spec.setColorAt(0.0, QColor(255, 255, 255, 180))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawRect(-sp_w // 2, -sp_h // 2, sp_w // 2, sp_h)

    # 6. Environment reflection
    env = QLinearGradient(float(-sp_w // 2), float(-sp_h // 2),
                          float(sp_w * 0.35), float(sp_h * 0.35))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 38))
    env.setColorAt(0.6, QColor(255, 255, 255, 38))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(env)
    p.drawRect(-sp_w // 2, -sp_h // 2, sp_w, sp_h)

    # Red center stripe
    p.setPen(QPen(QColor(0xFF, 0x20, 0x20), 1))
    p.drawLine(-sp_w // 2, 0, sp_w // 2, 0)

    # 7. Bevel on paddle edges
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(-sp_w // 2, -sp_h // 2, sp_w // 2, -sp_h // 2)
    p.drawLine(-sp_w // 2, -sp_h // 2, -sp_w // 2,  sp_h // 2)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(-sp_w // 2,  sp_h // 2, sp_w // 2,  sp_h // 2)
    p.drawLine( sp_w // 2, -sp_h // 2, sp_w // 2,  sp_h // 2)

    # 2. Pivot bolt: QConicalGradient + specular
    cg = QConicalGradient(0.0, 0.0, 0.0)
    cg.setColorAt(0.0,  QColor(0xC0, 0xC8, 0xD8))
    cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF))
    cg.setColorAt(0.5,  QColor(0x80, 0x88, 0x98))
    cg.setColorAt(0.75, QColor(0xE0, 0xE0, 0xE8))
    cg.setColorAt(1.0,  QColor(0xC0, 0xC8, 0xD8))
    p.setPen(QPen(QColor(0x50, 0x58, 0x68), 1))
    p.setBrush(cg)
    p.drawEllipse(-3, -3, 6, 6)
    spec2 = QRadialGradient(-1.0, -1.0, 2.0)
    spec2.setColorAt(0.0, QColor(255, 255, 255, 180))
    spec2.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec2)
    p.drawEllipse(-2, -2, 3, 3)

    p.restore()

    # Pivot rod: tube-effect
    rod_grad = QLinearGradient(float(sp_cx - 2), 0.0, float(sp_cx + 2), 0.0)
    rod_grad.setColorAt(0.0, QColor(60,  65,  75))
    rod_grad.setColorAt(0.5, QColor(140, 148, 162))
    rod_grad.setColorAt(1.0, QColor(60,  65,  75))
    p.setPen(QPen(rod_grad, 2))
    p.drawLine(sp_cx, sp_cy - 8, sp_cx, sp_cy + 8)

    p.restore()


def draw_roll_out(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad

    rail_rx = int(tw * 0.38)
    rail_ry = int(th * 0.25)
    inner_offset = max(3, tw // 20)
    track_w = max(3, tw // 16)

    # 3. Drop shadow arc
    p.setOpacity(0.20)
    p.setPen(QPen(QColor(0, 0, 0, 60), track_w + 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(float(cx - rail_rx + 2), float(cy - rail_ry + 3),
                     float(rail_rx * 2), float(rail_ry * 2)),
              180 * 16, -180 * 16)
    p.setOpacity(1.0)

    # 1. Outer rail tube: 5-stop gradient (bright centre, dark edges = 3D tube)
    outer_grad = QLinearGradient(float(cx - rail_rx), float(cy),
                                 float(cx - rail_rx + track_w * 2), float(cy))
    outer_grad.setColorAt(0.00, QColor(0x50, 0x58, 0x68, 180))
    outer_grad.setColorAt(0.25, QColor(0xA0, 0xA8, 0xB8, 200))
    outer_grad.setColorAt(0.50, QColor(0xFF, 0xFF, 0xFF, 220))
    outer_grad.setColorAt(0.75, QColor(0xA0, 0xA8, 0xB8, 200))
    outer_grad.setColorAt(1.00, QColor(0x50, 0x58, 0x68, 180))
    p.setPen(QPen(outer_grad, track_w))
    rect_outer = QRectF(float(cx - rail_rx), float(cy - rail_ry),
                        float(rail_rx * 2), float(rail_ry * 2))
    p.drawArc(rect_outer, 180 * 16, -180 * 16)

    # Inner rail: darker
    inner_grad = QLinearGradient(float(cx - rail_rx + inner_offset), float(cy),
                                 float(cx - rail_rx + inner_offset + track_w * 2), float(cy))
    inner_grad.setColorAt(0.00, QColor(0x40, 0x45, 0x55, 160))
    inner_grad.setColorAt(0.25, QColor(0x80, 0x88, 0x98, 180))
    inner_grad.setColorAt(0.50, QColor(0xC0, 0xC8, 0xD8, 200))
    inner_grad.setColorAt(0.75, QColor(0x80, 0x88, 0x98, 180))
    inner_grad.setColorAt(1.00, QColor(0x40, 0x45, 0x55, 160))
    p.setPen(QPen(inner_grad, max(2, track_w - 1)))
    rect_inner = QRectF(
        float(cx - rail_rx + inner_offset),
        float(cy - rail_ry + inner_offset),
        float((rail_rx - inner_offset) * 2),
        float((rail_ry - inner_offset) * 2),
    )
    p.drawArc(rect_inner, 180 * 16, -180 * 16)

    # 6. Environment highlight on top of rail
    p.setPen(QPen(QColor(255, 255, 255, 55), 1))
    p.drawArc(QRectF(float(cx - rail_rx + 1), float(cy - rail_ry + 1),
                     float(rail_rx * 2 - 2), float(rail_ry * 2 - 2)),
              180 * 16, -180 * 16)

    # 7. Support bracket bevel hints at ends
    for bx, by in ((cx - rail_rx, cy), (cx + rail_rx, cy)):
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawLine(bx - 2, by - 4, bx - 2, by + 4)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.drawLine(bx + 2, by - 4, bx + 2, by + 4)

    p.restore()


def draw_magnet(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    extra_y = widget._passive_extra_y

    pull = min(1.0, -extra_y / (th * 0.28)) if extra_y < 0 else 0.0

    mag_cx = cx
    mag_top = pad + int(th * 0.05)
    arm_w = max(5, tw // 12)
    arm_gap = max(12, tw // 5)
    arm_h = max(12, th // 6)

    # 3. Drop shadow under U-shape
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    shad_path = QPainterPath()
    shad_path.moveTo(float(mag_cx - arm_gap // 2 - arm_w + 3), float(mag_top + 3))
    shad_path.lineTo(float(mag_cx - arm_gap // 2 - arm_w + 3), float(mag_top + arm_h + 3))
    shad_path.lineTo(float(mag_cx - arm_gap // 2 + 3),         float(mag_top + arm_h + 3))
    shad_path.lineTo(float(mag_cx - arm_gap // 2 + 3),         float(mag_top + arm_w + 3))
    shad_path.lineTo(float(mag_cx + arm_gap // 2 + 3),         float(mag_top + arm_w + 3))
    shad_path.lineTo(float(mag_cx + arm_gap // 2 + 3),         float(mag_top + arm_h + 3))
    shad_path.lineTo(float(mag_cx + arm_gap // 2 + arm_w + 3), float(mag_top + arm_h + 3))
    shad_path.lineTo(float(mag_cx + arm_gap // 2 + arm_w + 3), float(mag_top + 3))
    shad_path.lineTo(float(mag_cx - arm_gap // 2 - arm_w + 3), float(mag_top + 3))
    p.fillPath(shad_path, QColor(0, 0, 0, 60))
    p.setOpacity(1.0)

    # Build proper QPainterPath U-shape for the magnet arms
    u_path = QPainterPath()
    u_path.moveTo(float(mag_cx - arm_gap // 2 - arm_w), float(mag_top))
    u_path.lineTo(float(mag_cx - arm_gap // 2 - arm_w), float(mag_top + arm_h))
    u_path.lineTo(float(mag_cx - arm_gap // 2),          float(mag_top + arm_h))
    u_path.lineTo(float(mag_cx - arm_gap // 2),          float(mag_top + arm_w))
    u_path.lineTo(float(mag_cx + arm_gap // 2),          float(mag_top + arm_w))
    u_path.lineTo(float(mag_cx + arm_gap // 2),          float(mag_top + arm_h))
    u_path.lineTo(float(mag_cx + arm_gap // 2 + arm_w),  float(mag_top + arm_h))
    u_path.lineTo(float(mag_cx + arm_gap // 2 + arm_w),  float(mag_top))
    u_path.lineTo(float(mag_cx - arm_gap // 2 - arm_w),  float(mag_top))

    # 1. 5-stop metallic gradient for U-shape body
    body_grad = QLinearGradient(float(mag_cx - arm_gap // 2 - arm_w), 0.0,
                                float(mag_cx + arm_gap // 2 + arm_w), 0.0)
    body_grad.setColorAt(0.00, QColor(0x50, 0x58, 0x68))
    body_grad.setColorAt(0.25, QColor(0x88, 0x90, 0xA0))
    body_grad.setColorAt(0.50, QColor(0xB0, 0xB8, 0xC8))
    body_grad.setColorAt(0.75, QColor(0x88, 0x90, 0xA0))
    body_grad.setColorAt(1.00, QColor(0x50, 0x58, 0x68))
    p.setPen(QPen(QColor(0x30, 0x35, 0x40), 1))
    p.setBrush(body_grad)
    p.drawPath(u_path)

    # 6. Environment reflection on arms
    env = QLinearGradient(float(mag_cx - arm_gap // 2 - arm_w), float(mag_top),
                          float(mag_cx + arm_gap // 2 + arm_w), float(mag_top + arm_h))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 35))
    env.setColorAt(0.6, QColor(255, 255, 255, 35))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.save()
    p.setClipPath(u_path)
    p.setBrush(env)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(u_path)
    p.restore()

    # 7. Bevel on U-shape
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(mag_cx - arm_gap // 2 - arm_w, mag_top,
               mag_cx + arm_gap // 2 + arm_w, mag_top)
    p.drawLine(mag_cx - arm_gap // 2 - arm_w, mag_top,
               mag_cx - arm_gap // 2 - arm_w, mag_top + arm_h)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(mag_cx - arm_gap // 2 - arm_w, mag_top + arm_h,
               mag_cx - arm_gap // 2,          mag_top + arm_h)
    p.drawLine(mag_cx + arm_gap // 2, mag_top + arm_h,
               mag_cx + arm_gap // 2 + arm_w, mag_top + arm_h)
    p.drawLine(mag_cx + arm_gap // 2 + arm_w, mag_top,
               mag_cx + arm_gap // 2 + arm_w, mag_top + arm_h)

    # Coil windings: red/blue gradient pole markings
    coil_turns = 5
    for i in range(coil_turns):
        fy = mag_top + arm_w + i * ((arm_h - arm_w) // coil_turns)
        coil_fade = int(180 - i * 20)
        # Left arm: red pole
        coil_l = QLinearGradient(float(mag_cx - arm_gap // 2 - arm_w), float(fy),
                                 float(mag_cx - arm_gap // 2), float(fy))
        coil_l.setColorAt(0.0, QColor(0xFF, 0x30, 0x20, coil_fade))
        coil_l.setColorAt(0.5, QColor(0xFF, 0x80, 0x40, coil_fade))
        coil_l.setColorAt(1.0, QColor(0xFF, 0x30, 0x20, coil_fade))
        p.setPen(QPen(coil_l, 1))
        p.drawLine(mag_cx - arm_gap // 2 - arm_w, fy, mag_cx - arm_gap // 2, fy)
        # Right arm: blue pole
        coil_r = QLinearGradient(float(mag_cx + arm_gap // 2), float(fy),
                                 float(mag_cx + arm_gap // 2 + arm_w), float(fy))
        coil_r.setColorAt(0.0, QColor(0x20, 0x50, 0xFF, coil_fade))
        coil_r.setColorAt(0.5, QColor(0x40, 0x80, 0xFF, coil_fade))
        coil_r.setColorAt(1.0, QColor(0x20, 0x50, 0xFF, coil_fade))
        p.setPen(QPen(coil_r, 1))
        p.drawLine(mag_cx + arm_gap // 2, fy, mag_cx + arm_gap // 2 + arm_w, fy)

    # Pole tips: glow when active
    if pull > 0.1:
        for px_off in (-arm_gap // 2 - arm_w // 2, arm_gap // 2 + arm_w // 2):
            # 5. CompositionMode_Plus for field glow
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            glow = QRadialGradient(float(mag_cx + px_off), float(mag_top + arm_h),
                                   float(arm_w * 2))
            glow.setColorAt(0.0, QColor(0x40, 0xA0, 0xFF, int(pull * 160)))
            glow.setColorAt(0.4, QColor(0x30, 0x80, 0xE0, int(pull * 80)))
            glow.setColorAt(1.0, QColor(0x40, 0xA0, 0xFF, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(mag_cx + px_off - arm_w * 2,
                          mag_top + arm_h - arm_w * 2,
                          arm_w * 4, arm_w * 4)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # Field lines with 5. glow
    field_count = 3 + int(pull * 4)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    field_pen_alpha = int(80 + pull * 120)
    p.setPen(QPen(QColor(0x40, 0xA0, 0xFF, field_pen_alpha), 1))
    for i in range(field_count):
        if field_count > 1:
            fx = mag_cx - arm_gap // 2 + i * (arm_gap // (field_count - 1))
        else:
            fx = mag_cx
        fy_start = mag_top + arm_h
        fy_end = fy_start + int((th * 0.12) * (0.5 + pull * 0.5))
        p.drawLine(fx, fy_start, fx + int(math.sin(i * 0.8) * 4), fy_end)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    p.restore()


def draw_orbit_loop(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad

    orbit_rx = int(tw * 0.36)
    orbit_ry = int(th * 0.22)
    track_w = max(3, tw // 20)

    # 3. Drop shadow
    p.setOpacity(0.20)
    p.setPen(QPen(QColor(0, 0, 0, 60), track_w + 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(float(cx - orbit_rx + 2), float(cy - orbit_ry + 3),
                         float(orbit_rx * 2), float(orbit_ry * 2)))
    p.setOpacity(1.0)

    # 1. Outer rail: double-layer 5-stop tube gradient (dark outer shadow)
    outer_grad = QLinearGradient(float(cx - orbit_rx), float(cy),
                                 float(cx - orbit_rx + track_w * 2), float(cy))
    outer_grad.setColorAt(0.00, QColor(0x20, 0x28, 0x30, 200))
    outer_grad.setColorAt(0.25, QColor(0x60, 0x70, 0x80, 210))
    outer_grad.setColorAt(0.50, QColor(0x00, 0xA0, 0x50, 220))
    outer_grad.setColorAt(0.75, QColor(0x60, 0x70, 0x80, 210))
    outer_grad.setColorAt(1.00, QColor(0x20, 0x28, 0x30, 200))
    p.setPen(QPen(outer_grad, track_w + 2))
    p.drawEllipse(QRectF(float(cx - orbit_rx - 2), float(cy - orbit_ry - 2),
                         float((orbit_rx + 2) * 2), float((orbit_ry + 2) * 2)))

    # Inner bright neon rail
    inner_grad = QLinearGradient(float(cx - orbit_rx), float(cy),
                                 float(cx - orbit_rx + track_w * 2), float(cy))
    inner_grad.setColorAt(0.00, QColor(0x00, 0x88, 0x44, 200))
    inner_grad.setColorAt(0.25, QColor(0x00, 0xCC, 0x66, 210))
    inner_grad.setColorAt(0.50, QColor(0x00, 0xFF, 0x80, 220))
    inner_grad.setColorAt(0.75, QColor(0x00, 0xCC, 0x66, 210))
    inner_grad.setColorAt(1.00, QColor(0x00, 0x88, 0x44, 200))
    p.setPen(QPen(inner_grad, track_w))
    p.drawEllipse(QRectF(float(cx - orbit_rx), float(cy - orbit_ry),
                         float(orbit_rx * 2), float(orbit_ry * 2)))

    # 5. Neon glow via CompositionMode_Plus
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setPen(QPen(QColor(0x00, 0xFF, 0x80, 80), track_w + 4))
    p.drawEllipse(QRectF(float(cx - orbit_rx), float(cy - orbit_ry),
                         float(orbit_rx * 2), float(orbit_ry * 2)))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # 6. Environment reflection highlight
    p.setPen(QPen(QColor(255, 255, 255, 50), 1))
    p.drawEllipse(QRectF(float(cx - orbit_rx + 1), float(cy - orbit_ry + 1),
                         float(orbit_rx * 2 - 2), float(orbit_ry * 2 - 2)))

    p.restore()


def draw_solenoid_buzz(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    t = widget._passive_t
    extra_x = widget._passive_extra_x
    extra_y = widget._passive_extra_y

    sol_x = cx + int(tw * 0.32) + int(extra_x)
    sol_y = cy + int(th * 0.10) + int(extra_y)
    sol_w = max(10, tw // 7)
    sol_h = max(8, th // 8)

    # 3. Drop shadow
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(sol_x - sol_w // 2 + 2, sol_y - sol_h // 2 + 3, sol_w, sol_h)
    p.setOpacity(1.0)

    # 1. Core: cylinder with 5-stop metallic gradient
    core_grad = QLinearGradient(float(sol_x - sol_w // 2), 0.0,
                                float(sol_x + sol_w // 2), 0.0)
    core_grad.setColorAt(0.00, QColor(0x50, 0x55, 0x60))
    core_grad.setColorAt(0.20, QColor(0x80, 0x88, 0x98))
    core_grad.setColorAt(0.50, QColor(0xB0, 0xB8, 0xC8))
    core_grad.setColorAt(0.80, QColor(0x80, 0x88, 0x98))
    core_grad.setColorAt(1.00, QColor(0x50, 0x55, 0x60))
    p.setPen(QPen(QColor(0x40, 0x42, 0x50), 1))
    p.setBrush(core_grad)
    p.drawRect(sol_x - sol_w // 2, sol_y - sol_h // 2, sol_w, sol_h)

    # 6. Environment reflection on core
    env = QLinearGradient(float(sol_x - sol_w // 2), float(sol_y - sol_h // 2),
                          float(sol_x + sol_w * 0.35), float(sol_y + sol_h * 0.35))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 38))
    env.setColorAt(0.6, QColor(255, 255, 255, 38))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(env)
    p.drawRect(sol_x - sol_w // 2, sol_y - sol_h // 2, sol_w, sol_h)

    # 7. Bevel on core
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(sol_x - sol_w // 2, sol_y - sol_h // 2,
               sol_x + sol_w // 2, sol_y - sol_h // 2)
    p.drawLine(sol_x - sol_w // 2, sol_y - sol_h // 2,
               sol_x - sol_w // 2, sol_y + sol_h // 2)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(sol_x - sol_w // 2, sol_y + sol_h // 2,
               sol_x + sol_w // 2, sol_y + sol_h // 2)
    p.drawLine(sol_x + sol_w // 2, sol_y - sol_h // 2,
               sol_x + sol_w // 2, sol_y + sol_h // 2)

    # Copper winding lines: each ring as individual gradient element
    turns = 8
    for i in range(turns):
        wy = sol_y - sol_h // 2 + i * (sol_h // turns)
        coil_grad = QLinearGradient(float(sol_x - sol_w // 2), float(wy),
                                    float(sol_x + sol_w // 2), float(wy))
        coil_grad.setColorAt(0.0, QColor(0x90, 0x55, 0x20))
        coil_grad.setColorAt(0.3, QColor(0xD8, 0x88, 0x38))
        coil_grad.setColorAt(0.5, QColor(0xFF, 0xAA, 0x55))
        coil_grad.setColorAt(0.7, QColor(0xD8, 0x88, 0x38))
        coil_grad.setColorAt(1.0, QColor(0x90, 0x55, 0x20))
        p.setPen(QPen(coil_grad, 1))
        p.drawLine(sol_x - sol_w // 2, wy, sol_x + sol_w // 2, wy)

    # 4. Specular highlight on top of core
    spec = QRadialGradient(float(sol_x - sol_w // 4), float(sol_y - sol_h // 4),
                           float(sol_w * 0.35))
    spec.setColorAt(0.0, QColor(255, 255, 255, 120))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawRect(sol_x - sol_w // 2, sol_y - sol_h // 2, sol_w // 2, sol_h // 2)

    # 5. Vibration lines: glow with CompositionMode_Plus
    vib_alpha = int(150 + 80 * abs(math.sin(t * 20.0)))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setPen(QPen(QColor(255, 255, 180, vib_alpha), 1))
    for vx_off, vy_off, vlen in ((-sol_w, 0, 6), (sol_w // 2 + 2, -4, 5),
                                  (-sol_w // 2 - 2, 4, 4)):
        vx = sol_x + vx_off
        vy = sol_y + vy_off
        p.drawLine(vx, vy, vx - vlen, vy)
        p.drawLine(vx - vlen, vy, vx - vlen + 3, vy - 3)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    p.restore()


def draw_lane_change(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    extra_x = widget._passive_extra_x

    lane_y = cy + int(th * 0.35)
    lane_len = int(tw * 0.28)
    arrow_size = max(5, tw // 12)

    def _draw_arrow(p: QPainter, ax: int, ay: int, direction: int,
                    is_active: bool) -> None:
        """Draw a dome-shaped insert-light style arrow."""
        # 3. Drop shadow
        p.setOpacity(0.22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        shad = QPainterPath()
        shad.moveTo(float(ax + direction * arrow_size + 2),
                    float(ay + 3))
        shad.lineTo(float(ax - direction * arrow_size + 2),
                    float(ay - arrow_size // 2 + 3))
        shad.lineTo(float(ax - direction * arrow_size + 2),
                    float(ay + arrow_size // 2 + 3))
        shad.closeSubpath()
        p.fillPath(shad, QColor(0, 0, 0, 60))
        p.setOpacity(1.0)

        # Arrow shape (dome-style insert light)
        arrow_path = QPainterPath()
        arrow_path.moveTo(float(ax + direction * arrow_size),  float(ay))
        arrow_path.lineTo(float(ax - direction * arrow_size),  float(ay - arrow_size // 2))
        arrow_path.lineTo(float(ax - direction * arrow_size),  float(ay + arrow_size // 2))
        arrow_path.closeSubpath()

        if is_active:
            # 1. Active: dome-shaped QRadialGradient (bright yellow)
            ar = QRadialGradient(float(ax), float(ay), float(arrow_size * 1.2))
            ar.setColorAt(0.00, QColor(255, 255, 200))
            ar.setColorAt(0.25, QColor(255, 240, 100))
            ar.setColorAt(0.50, QColor(255, 200,  30))
            ar.setColorAt(0.75, QColor(200, 140,   0))
            ar.setColorAt(1.00, QColor(140,  90,   0))
        else:
            ar = QRadialGradient(float(ax - direction * arrow_size // 3),
                                 float(ay - arrow_size // 4),
                                 float(arrow_size * 1.1))
            ar.setColorAt(0.00, QColor(0xFF, 0xCC, 0x60))
            ar.setColorAt(0.30, QColor(0xE0, 0x90, 0x10))
            ar.setColorAt(0.60, QColor(0xB0, 0x60, 0x00))
            ar.setColorAt(0.80, QColor(0x80, 0x40, 0x00))
            ar.setColorAt(1.00, QColor(0x50, 0x28, 0x00))
        p.setPen(QPen(QColor(0x80, 0x50, 0x00), 1))
        p.setBrush(ar)
        p.drawPath(arrow_path)

        # 4. Specular highlight
        spec = QRadialGradient(float(ax - direction * arrow_size // 3),
                               float(ay - arrow_size // 4),
                               float(arrow_size * 0.4))
        spec.setColorAt(0.0, QColor(255, 255, 255, 180))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(spec)
        p.drawPath(arrow_path)

        # 5. Active glow via CompositionMode_Plus
        if is_active:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            glow = QRadialGradient(float(ax), float(ay), float(arrow_size * 3))
            glow.setColorAt(0.0, QColor(255, 255, 80, 120))
            glow.setColorAt(0.5, QColor(255, 220, 40, 60))
            glow.setColorAt(1.0, QColor(255, 200, 0,  0))
            p.setBrush(glow)
            p.drawEllipse(ax - arrow_size * 3, ay - arrow_size * 3,
                          arrow_size * 6, arrow_size * 6)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # 7. Bevel on arrow base
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.drawLine(int(ax - direction * arrow_size),
                   int(ay - arrow_size // 2),
                   int(ax + direction * arrow_size),
                   int(ay))
        p.setPen(QPen(QColor(0, 0, 0, 80), 1))
        p.drawLine(int(ax - direction * arrow_size),
                   int(ay + arrow_size // 2),
                   int(ax + direction * arrow_size),
                   int(ay))

    # Left arrow
    left_active = extra_x < -3.0
    left_ax = cx - int(tw * 0.10) - lane_len // 2
    _draw_arrow(p, left_ax, lane_y, -1, left_active)

    # Connecting lane line for left
    line_grad_l = QLinearGradient(float(cx - int(tw * 0.10)), float(lane_y),
                                  float(left_ax + arrow_size), float(lane_y))
    line_grad_l.setColorAt(0.0, QColor(0xFF, 0x8C, 0x00, 80))
    line_grad_l.setColorAt(1.0, QColor(0xFF, 0x8C, 0x00,
                                       240 if left_active else 120))
    p.setPen(QPen(line_grad_l, 2))
    p.drawLine(cx - int(tw * 0.10), lane_y, left_ax + arrow_size, lane_y)

    # Right arrow
    right_active = extra_x > 3.0
    right_ax = cx + int(tw * 0.10) + lane_len // 2
    _draw_arrow(p, right_ax, lane_y, 1, right_active)

    # Connecting lane line for right
    line_grad_r = QLinearGradient(float(cx + int(tw * 0.10)), float(lane_y),
                                  float(right_ax - arrow_size), float(lane_y))
    line_grad_r.setColorAt(0.0, QColor(0xFF, 0x8C, 0x00, 80))
    line_grad_r.setColorAt(1.0, QColor(0xFF, 0x8C, 0x00,
                                       240 if right_active else 120))
    p.setPen(QPen(line_grad_r, 2))
    p.drawLine(cx + int(tw * 0.10), lane_y, right_ax - arrow_size, lane_y)

    p.restore()


# ---------------------------------------------------------------------------
# Updated event draw helpers — pinball-themed with full 3D rendering
# ---------------------------------------------------------------------------

def draw_event_jackpot_glow(p: QPainter, widget) -> None:
    """Gold glow ring, sparkles, and DMD-style JACKPOT display above Steely."""
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["jackpot_glow"]
    fade = max(0.0, 1.0 - t / duration)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    glow_r = int(radius * (1.25 + 0.12 * math.sin(t * 6.0)))
    glow_alpha = int(130 * fade)
    if glow_alpha > 0:
        # 5. CompositionMode_Plus for golden glow ring
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        # 1. 5-stop gradient for glow depth
        glow = QRadialGradient(float(cx), float(cy), float(glow_r * 1.5))
        glow.setColorAt(0.0, QColor(255, 240, 100, glow_alpha))
        glow.setColorAt(0.3, QColor(255, 220,  50, glow_alpha))
        glow.setColorAt(0.5, QColor(255, 200,  20, int(glow_alpha * 0.85)))
        glow.setColorAt(0.7, QColor(220, 160,   0, int(glow_alpha * 0.55)))
        glow.setColorAt(1.0, QColor(180, 110,   0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # Orbiting star sparkles with glow
    for sp in getattr(widget, "_jackpot_particles", []):
        sp_x = cx + int(math.cos(sp["angle"]) * sp["dist"])
        sp_y = cy + int(math.sin(sp["angle"]) * sp["dist"])
        size = sp["size"] * fade
        alpha = int(sp["alpha"] * fade)
        if alpha <= 0 or size < 0.5:
            continue
        star = QPainterPath()
        star.moveTo(sp_x, sp_y - size)
        star.lineTo(sp_x + size * 0.35, sp_y - size * 0.35)
        star.lineTo(sp_x + size, sp_y)
        star.lineTo(sp_x + size * 0.35, sp_y + size * 0.35)
        star.lineTo(sp_x, sp_y + size)
        star.lineTo(sp_x - size * 0.35, sp_y + size * 0.35)
        star.lineTo(sp_x - size, sp_y)
        star.lineTo(sp_x - size * 0.35, sp_y - size * 0.35)
        star.closeSubpath()
        # 5. Sparkle glow pass
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.fillPath(star, QColor(255, 240, 80, alpha))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        # Sharp sparkle on top
        p.fillPath(star, QColor(255, 255, 200, int(alpha * 0.7)))

    # DMD "JACKPOT" display
    dmd_alpha = int(220 * fade)
    if dmd_alpha > 10:
        dmd_w = min(tw - 4, max(40, int(tw * 0.80)))
        dmd_h = max(12, int(th * 0.14))
        dmd_x = cx - dmd_w // 2
        dmd_y = cy - radius - dmd_h - 8
        # 1. DMD frame: 5-stop gradient
        dmd_grad = QLinearGradient(float(dmd_x), float(dmd_y),
                                   float(dmd_x), float(dmd_y + dmd_h))
        dmd_grad.setColorAt(0.00, QColor(20, 20, 20, dmd_alpha))
        dmd_grad.setColorAt(0.25, QColor(15, 15, 15, dmd_alpha))
        dmd_grad.setColorAt(0.50, QColor(8,  8,  8,  dmd_alpha))
        dmd_grad.setColorAt(0.75, QColor(15, 15, 15, dmd_alpha))
        dmd_grad.setColorAt(1.00, QColor(20, 20, 20, dmd_alpha))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dmd_grad)
        p.drawRoundedRect(dmd_x, dmd_y, dmd_w, dmd_h, 2, 2)
        # 7. Bevel frame on DMD display
        p.setPen(QPen(QColor(255, 255, 255, int(dmd_alpha * 0.35)), 1))
        p.drawLine(dmd_x, dmd_y, dmd_x + dmd_w, dmd_y)
        p.drawLine(dmd_x, dmd_y, dmd_x, dmd_y + dmd_h)
        p.setPen(QPen(QColor(0, 0, 0, int(dmd_alpha * 0.55)), 1))
        p.drawLine(dmd_x, dmd_y + dmd_h, dmd_x + dmd_w, dmd_y + dmd_h)
        p.drawLine(dmd_x + dmd_w, dmd_y, dmd_x + dmd_w, dmd_y + dmd_h)
        # Pixel dot grid texture
        dot_spacing = max(2, dmd_h // 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0xFF, 0x88, 0x00, dmd_alpha // 3))
        for row in range(dmd_h // dot_spacing):
            for col in range(dmd_w // dot_spacing):
                p.drawEllipse(dmd_x + 1 + col * dot_spacing,
                              dmd_y + 1 + row * dot_spacing, 1, 1)
        # 5. Text with CompositionMode_Plus glow
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        font_glow = QFont("Courier", max(5, dmd_h - 4), QFont.Weight.Bold)
        p.setFont(font_glow)
        p.setPen(QColor(0xFF, 0x60, 0x00, int(dmd_alpha * 0.5)))
        p.drawText(dmd_x + 2, dmd_y + dmd_h - 3, "JACKPOT")
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QColor(0xFF, 0x99, 0x00, dmd_alpha))
        p.drawText(dmd_x + 2, dmd_y + dmd_h - 3, "JACKPOT")

    p.restore()


def draw_event_victory_lap(p: QPainter, widget) -> None:
    """Motion trail arc and 3D wireform rail while Steely circles on victory lap."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["victory_lap"]
    if t > duration * 0.95:
        return
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    fade = max(0.0, 1.0 - t / duration)
    rx = int(tw * 0.30)
    ry = int(th * 0.22)
    track_w = max(2, radius // 6)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 3. Drop shadow for wireform rail
    p.setOpacity(0.18)
    p.setPen(QPen(QColor(0, 0, 0, 60), track_w + 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(cx - rx + 2, cy - ry + 3, rx * 2, ry * 2)
    p.setOpacity(1.0)

    # 1. Chrome outer wireform rail: 5-stop tube gradient
    rail_grad = QLinearGradient(float(cx - rx), float(cy),
                                float(cx - rx + track_w * 3), float(cy))
    rail_grad.setColorAt(0.00, QColor(0x50, 0x58, 0x68, int(180 * fade)))
    rail_grad.setColorAt(0.25, QColor(0x90, 0x98, 0xA8, int(200 * fade)))
    rail_grad.setColorAt(0.50, QColor(0xC0, 0xC8, 0xD8, int(220 * fade)))
    rail_grad.setColorAt(0.75, QColor(0x90, 0x98, 0xA8, int(200 * fade)))
    rail_grad.setColorAt(1.00, QColor(0x50, 0x58, 0x68, int(180 * fade)))
    p.setPen(QPen(rail_grad, track_w))
    p.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)

    # Neon green inner rail
    p.setPen(QPen(QColor(0x00, 0xFF, 0x80, int(80 * fade)), 1))
    p.drawEllipse(cx - rx - 2, cy - ry - 2, (rx + 2) * 2, (ry + 2) * 2)

    # 5. Neon glow via CompositionMode_Plus
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setPen(QPen(QColor(0x00, 0xFF, 0x80, int(50 * fade)), track_w + 4))
    p.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # Motion trail
    trail_alpha = int(80 * fade)
    if trail_alpha > 0:
        pen = QPen(QColor(180, 220, 255, trail_alpha), max(2, radius // 4))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)

    # 6. Environment reflection highlight
    p.setPen(QPen(QColor(255, 255, 255, int(55 * fade)), 1))
    p.drawEllipse(cx - rx + 1, cy - ry + 1, (rx - 1) * 2, (ry - 1) * 2)

    p.restore()


def draw_event_drain_fall(p: QPainter, widget) -> None:
    """Drain hole and BALL SAVE text during drain_fall with 3D metallic rim."""
    t = widget._event_anim_t
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    drain_w = int(tw * 0.25)
    drain_h = max(6, int(th * 0.08))
    drain_y = th + pad - drain_h

    # 3. Drop shadow under drain
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawEllipse(cx - drain_w + 2, drain_y + 3, drain_w * 2, drain_h)
    p.setOpacity(1.0)

    # 1. Drain hole: concentric gradient (deep dark centre)
    hole_grad = QRadialGradient(float(cx), float(drain_y + drain_h // 2),
                                float(drain_w))
    hole_grad.setColorAt(0.00, QColor(4,   3,  10))
    hole_grad.setColorAt(0.25, QColor(8,   6,  18))
    hole_grad.setColorAt(0.50, QColor(15, 12,  28))
    hole_grad.setColorAt(0.75, QColor(25, 20,  38))
    hole_grad.setColorAt(1.00, QColor(35, 28,  48))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(hole_grad)
    p.drawEllipse(cx - drain_w, drain_y, drain_w * 2, drain_h)

    # 7. Metal rim bevel
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawArc(cx - drain_w, drain_y, drain_w * 2, drain_h, 0 * 16, 180 * 16)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawArc(cx - drain_w, drain_y, drain_w * 2, drain_h, 180 * 16, 180 * 16)

    # Gutter: 1. metallic gradient
    gutter_grad = QLinearGradient(float(cx - drain_w), float(drain_y + drain_h // 2),
                                  float(cx + drain_w), float(drain_y + drain_h // 2))
    gutter_grad.setColorAt(0.00, QColor(0x40, 0x44, 0x50))
    gutter_grad.setColorAt(0.25, QColor(0x70, 0x75, 0x85))
    gutter_grad.setColorAt(0.50, QColor(0x90, 0x98, 0xA8))
    gutter_grad.setColorAt(0.75, QColor(0x70, 0x75, 0x85))
    gutter_grad.setColorAt(1.00, QColor(0x40, 0x44, 0x50))
    p.setPen(QPen(gutter_grad, 2))
    p.drawLine(cx - drain_w, drain_y + drain_h // 2,
               cx + drain_w, drain_y + drain_h // 2)

    if 1.6 <= t < 2.4:
        alpha = int(180 * min(1.0, (t - 1.6) / 0.3))
        p.setPen(QColor(100, 160, 255, alpha))
        font = QFont("Arial", max(7, tw // 9))
        p.setFont(font)
        p.drawText(cx - 12, cy - int(th * 0.55), ":(")

        blink_alpha = 220 if int(t * 4) % 2 == 0 else 60
        # 5. BALL SAVE glow
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        font2 = QFont("Arial Black", max(5, tw // 11), QFont.Weight.Black)
        p.setFont(font2)
        p.setPen(QColor(0xFF, 0x10, 0x10, int(blink_alpha * 0.4)))
        label = "BALL SAVE"
        fm = p.fontMetrics()
        lx = cx - fm.horizontalAdvance(label) // 2
        p.drawText(lx, drain_y - 6, label)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QColor(0xFF, 0x20, 0x20, blink_alpha))
        p.drawText(lx, drain_y - 6, label)

    p.restore()


def draw_event_overheat(p: QPainter, widget) -> None:
    """Red heat tint, smoke, solenoid coils and sparks during overheat."""
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["overheat"]
    fade = max(0.0, 1.0 - t / duration)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    heat_alpha = int(90 * fade * (0.7 + 0.3 * math.sin(t * 8.0)))
    if heat_alpha > 0:
        # 5. CompositionMode_Plus for heat glow
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        # 1. 5-stop heat gradient
        heat = QRadialGradient(float(cx), float(cy), float(radius * 1.4))
        heat.setColorAt(0.0, QColor(255, 120, 40, heat_alpha))
        heat.setColorAt(0.3, QColor(255,  80, 20, heat_alpha))
        heat.setColorAt(0.5, QColor(220,  50, 10, int(heat_alpha * 0.85)))
        heat.setColorAt(0.7, QColor(180,  30,  0, int(heat_alpha * 0.6)))
        heat.setColorAt(1.0, QColor(120,  10,  0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(heat)
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    for puff in getattr(widget, "_smoke_particles", []):
        if t < puff["delay"]:
            continue
        alpha = int(puff["alpha"] * fade)
        if alpha <= 0:
            continue
        sx = cx + int(puff["x_off"])
        sy = cy - radius + int(puff["y"])
        sz = int(puff["size"])
        smoke_grad = QRadialGradient(float(sx), float(sy), float(sz))
        smoke_grad.setColorAt(0.0, QColor(210, 140, 90, alpha))
        smoke_grad.setColorAt(0.4, QColor(190, 120, 70, int(alpha * 0.7)))
        smoke_grad.setColorAt(0.7, QColor(170, 100, 55, int(alpha * 0.4)))
        smoke_grad.setColorAt(1.0, QColor(150,  90, 50, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(smoke_grad)
        p.drawEllipse(sx - sz, sy - sz, sz * 2, sz * 2)

    # Solenoid coils on each side: cylinder with 5-stop metallic gradient
    coil_w = max(8, tw // 8)
    coil_h = max(6, th // 10)
    for side_x in (cx - radius - coil_w - 4, cx + radius + 4):
        coil_y = cy - coil_h // 2
        # 3. Drop shadow under coil
        p.setOpacity(0.22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRect(side_x + 2, coil_y + 3, coil_w, coil_h)
        p.setOpacity(1.0)
        # 1. Cylinder gradient
        coil_body_grad = QLinearGradient(float(side_x), float(coil_y),
                                         float(side_x), float(coil_y + coil_h))
        coil_body_grad.setColorAt(0.00, QColor(255, 100, 10, int(fade * 220)))
        coil_body_grad.setColorAt(0.25, QColor(240,  70,  5, int(fade * 220)))
        coil_body_grad.setColorAt(0.50, QColor(200,  40,  0, int(fade * 220)))
        coil_body_grad.setColorAt(0.75, QColor(180,  25,  0, int(fade * 220)))
        coil_body_grad.setColorAt(1.00, QColor(140,  10,  0, int(fade * 220)))
        p.setPen(QPen(QColor(80, 20, 0), 1))
        p.setBrush(coil_body_grad)
        p.drawRect(side_x, coil_y, coil_w, coil_h)
        # 7. Bevel on coil
        p.setPen(QPen(QColor(255, 255, 255, int(80 * fade)), 1))
        p.drawLine(side_x, coil_y, side_x + coil_w, coil_y)
        p.drawLine(side_x, coil_y, side_x, coil_y + coil_h)
        p.setPen(QPen(QColor(0, 0, 0, int(80 * fade)), 1))
        p.drawLine(side_x, coil_y + coil_h, side_x + coil_w, coil_y + coil_h)
        p.drawLine(side_x + coil_w, coil_y, side_x + coil_w, coil_y + coil_h)
        # Winding lines
        turns = 5
        for i in range(turns):
            wy = coil_y + i * (coil_h // turns)
            winding_grad = QLinearGradient(float(side_x), float(wy),
                                           float(side_x + coil_w), float(wy))
            winding_grad.setColorAt(0.0, QColor(200, 60, 0, int(fade * 200)))
            winding_grad.setColorAt(0.5, QColor(255, 90, 0, int(fade * 200)))
            winding_grad.setColorAt(1.0, QColor(200, 60, 0, int(fade * 200)))
            p.setPen(QPen(winding_grad, 1))
            p.drawLine(side_x, wy, side_x + coil_w, wy)
        # 4. Specular on coil
        spec = QRadialGradient(float(side_x + coil_w // 4), float(coil_y + coil_h // 4),
                               float(coil_w * 0.4))
        spec.setColorAt(0.0, QColor(255, 255, 255, int(100 * fade)))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(spec)
        p.drawRect(side_x, coil_y, coil_w // 2, coil_h // 2)

    # Sparks with 5. CompositionMode_Plus
    spark_alpha = int(fade * 200 * abs(math.sin(t * 15.0)))
    if spark_alpha > 10:
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(QPen(QColor(255, 240, 80, spark_alpha), 1))
        for i in range(6):
            angle = i * math.pi / 3 + t * 5.0
            r0 = radius + 8
            r1 = r0 + 4 + int(3 * abs(math.sin(t * 7.0 + i * 1.3)))
            p.drawLine(cx + int(math.cos(angle) * r0),
                       cy + int(math.sin(angle) * r0),
                       cx + int(math.cos(angle) * r1),
                       cy + int(math.sin(angle) * r1))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    p.restore()


def draw_event_plunger_entry(p: QPainter, widget) -> None:
    """Motion blur streak and 3D plunger rod during plunger-entry launch."""
    t = widget._event_anim_t
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Motion blur streak (launch phase)
    if 0.25 <= t < 1.1:
        progress = (t - 0.25) / 0.85
        streak_alpha = int(120 * (1.0 - progress))
        streak_len = int(radius * 2.5 * (1.0 - progress))
        streak_w = max(4, radius // 2)
        if streak_alpha > 0 and streak_len > 0:
            # 1. 5-stop metallic streak
            grad = QLinearGradient(float(cx), float(cy + radius),
                                   float(cx), float(cy + radius + streak_len))
            grad.setColorAt(0.00, QColor(200, 215, 240, streak_alpha))
            grad.setColorAt(0.25, QColor(175, 195, 225, int(streak_alpha * 0.85)))
            grad.setColorAt(0.50, QColor(155, 180, 215, int(streak_alpha * 0.65)))
            grad.setColorAt(0.75, QColor(135, 160, 200, int(streak_alpha * 0.40)))
            grad.setColorAt(1.00, QColor(115, 145, 190, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRect(cx - streak_w // 2, cy + radius, streak_w, streak_len)
            # 6. Environment reflection centre line
            env = QLinearGradient(float(cx), float(cy + radius),
                                  float(cx), float(cy + radius + streak_len))
            env.setColorAt(0.0, QColor(255, 255, 255, int(streak_alpha * 0.45)))
            env.setColorAt(0.5, QColor(255, 255, 255, int(streak_alpha * 0.20)))
            env.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(env)
            p.drawRect(cx - streak_w // 4, cy + radius, streak_w // 2, streak_len)

    # Plunger rod visible when t < 0.7
    if t < 0.7:
        plunger_fade = max(0.0, 1.0 - t / 0.7)
        spring_extend = t / 0.7
        rod_y = cy + radius + 2
        rod_h = int(th * 0.18 * plunger_fade)
        rod_w = max(4, radius // 3)

        # 3. Drop shadow
        p.setOpacity(0.22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRect(cx - rod_w // 2 + 2, rod_y + 3, rod_w, rod_h)
        p.setOpacity(1.0)

        # Spring with 2. QConicalGradient on each coil
        spring_h = max(4, int(th * 0.08 * (0.4 + spring_extend * 0.6)))
        coil_count = 5
        for i in range(coil_count):
            sy0 = rod_y + rod_h + int(i * spring_h / coil_count)
            sy1 = sy0 + int(spring_h / coil_count)
            mid_sy = (sy0 + sy1) // 2
            cg = QConicalGradient(float(cx), float(mid_sy), 0.0)
            cg.setColorAt(0.0,  QColor(0xFF, 0xE8, 0x20, int(plunger_fade * 220)))
            cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0x80, int(plunger_fade * 220)))
            cg.setColorAt(0.5,  QColor(0xC0, 0xA0, 0x00, int(plunger_fade * 220)))
            cg.setColorAt(0.75, QColor(0xFF, 0xE8, 0x20, int(plunger_fade * 220)))
            cg.setColorAt(1.0,  QColor(0xFF, 0xE8, 0x20, int(plunger_fade * 220)))
            ox = 4 if i % 2 == 0 else -4
            p.setPen(QPen(cg, 2))
            p.drawLine(cx - 4, sy0, cx + ox, mid_sy)
            p.drawLine(cx + ox, mid_sy, cx + 4, sy1)

        if rod_h > 0:
            # 1. Rod: 5-stop metallic gradient
            rod_grad = QLinearGradient(float(cx - rod_w // 2), 0.0,
                                       float(cx + rod_w // 2), 0.0)
            rod_grad.setColorAt(0.00, QColor(0x50, 0x58, 0x68, int(plunger_fade * 220)))
            rod_grad.setColorAt(0.25, QColor(0xA0, 0xA8, 0xB8, int(plunger_fade * 220)))
            rod_grad.setColorAt(0.50, QColor(0xFF, 0xFF, 0xFF, int(plunger_fade * 220)))
            rod_grad.setColorAt(0.75, QColor(0xA0, 0xA8, 0xB8, int(plunger_fade * 220)))
            rod_grad.setColorAt(1.00, QColor(0x50, 0x58, 0x68, int(plunger_fade * 220)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rod_grad)
            p.drawRect(cx - rod_w // 2, rod_y, rod_w, rod_h)
            # 6. Env reflection
            env2 = QLinearGradient(float(cx - rod_w // 2), float(rod_y),
                                   float(cx + rod_w // 2), float(rod_y + rod_h))
            env2.setColorAt(0.0, QColor(255, 255, 255, 0))
            env2.setColorAt(0.4, QColor(255, 255, 255, int(38 * plunger_fade)))
            env2.setColorAt(0.6, QColor(255, 255, 255, int(38 * plunger_fade)))
            env2.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(env2)
            p.drawRect(cx - rod_w // 2, rod_y, rod_w, rod_h)
            # 7. Bevel
            p.setPen(QPen(QColor(255, 255, 255, int(80 * plunger_fade)), 1))
            p.drawLine(cx - rod_w // 2, rod_y, cx + rod_w // 2, rod_y)
            p.setPen(QPen(QColor(0, 0, 0, int(80 * plunger_fade)), 1))
            p.drawLine(cx - rod_w // 2, rod_y + rod_h, cx + rod_w // 2, rod_y + rod_h)

    p.restore()


def draw_event_show_off(p: QPainter, widget) -> None:
    """Polish sparkles, sheen, small ramp, and combo multiplier text."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["show_off"]
    fade = max(0.0, 1.0 - t / duration)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    sheen_alpha = int(90 * fade * abs(math.sin(t * 4.0)))
    if sheen_alpha > 0:
        sheen = QLinearGradient(
            float(cx - radius), float(cy - radius),
            float(cx + radius), float(cy + radius),
        )
        sheen.setColorAt(0.00, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.35, QColor(255, 255, 255, int(sheen_alpha * 0.5)))
        sheen.setColorAt(0.45, QColor(255, 255, 255, sheen_alpha))
        sheen.setColorAt(0.55, QColor(255, 255, 255, sheen_alpha))
        sheen.setColorAt(0.65, QColor(255, 255, 255, int(sheen_alpha * 0.5)))
        sheen.setColorAt(1.00, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        # 5. CompositionMode_Plus for sheen
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setBrush(sheen)
        clip = QPainterPath()
        clip.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        p.setClipPath(clip)
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        p.setClipping(False)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    eye_y = cy - radius // 5
    eye_r = max(3, radius // 4)
    moustache_y = eye_y + eye_r + 3
    for side in (-1, 1):
        for i in range(3):
            sx = cx + side * (radius // 3 + i * 4)
            sy = moustache_y - i * 2
            alpha = int(fade * (200 - i * 40) * abs(math.sin(t * 5.0 + i)))
            if alpha > 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
                p.setBrush(QColor(255, 240, 80, alpha))
                p.drawEllipse(sx - 2, sy - 2, 4, 4)
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # Small ramp: 1. metallic gradient
    ramp_x0 = pad + 2
    ramp_y0 = th + pad - 4
    ramp_x1 = cx - radius - 4
    ramp_y1 = cy + int(th * 0.10)
    ramp_dx = ramp_x1 - ramp_x0
    ramp_dy = ramp_y1 - ramp_y0
    ramp_grad = QLinearGradient(float(ramp_x0), float(ramp_y0),
                                float(ramp_x1), float(ramp_y1))
    ramp_grad.setColorAt(0.00, QColor(0x80, 0x50, 0x00, int(180 * fade)))
    ramp_grad.setColorAt(0.25, QColor(0xCC, 0x80, 0x10, int(180 * fade)))
    ramp_grad.setColorAt(0.50, QColor(0xFF, 0xA0, 0x20, int(180 * fade)))
    ramp_grad.setColorAt(0.75, QColor(0xCC, 0x70, 0x00, int(180 * fade)))
    ramp_grad.setColorAt(1.00, QColor(0x80, 0x45, 0x00, int(180 * fade)))
    p.setPen(QPen(ramp_grad, 2))
    p.drawLine(ramp_x0, ramp_y0, ramp_x1, ramp_y1)
    p.setPen(QPen(QColor(0xCC, 0x60, 0x00, int(140 * fade)), 2))
    p.drawLine(ramp_x0 + 3, ramp_y0, ramp_x1 + 3, ramp_y1)

    # Combo multiplier text
    combos = ["2x", "3x", "4x"]
    combo_idx = min(len(combos) - 1, int(t / (duration / 3)))
    combo_phase = (t % (duration / 3)) / (duration / 3)
    combo_alpha = int(fade * 220 *
                      min(1.0, combo_phase * 4.0) *
                      (1.0 - max(0.0, combo_phase - 0.7) / 0.3))
    if combo_alpha > 10:
        font = QFont("Arial Black", max(8, tw // 7), QFont.Weight.Black)
        p.setFont(font)
        label = combos[combo_idx]
        fm = p.fontMetrics()
        lx = cx - fm.horizontalAdvance(label) // 2
        ly = cy - radius - 8
        # 5. Glow pass
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(QColor(180, 140, 0, int(combo_alpha * 0.45)))
        p.drawText(lx, ly, label)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QColor(255, 220, 0, combo_alpha))
        p.drawText(lx, ly, label)

    p.restore()


def draw_event_nervous(p: QPainter, widget) -> None:
    """Sweat drops, tilt bob pendulum, and DANGER text."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["nervous"]
    if t > duration:
        return
    intensity = min(1.0, t / 2.0)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    sweat_alpha = int(intensity * 180)
    if sweat_alpha > 5:
        for side in (-1, 1):
            sx = cx + side * (radius // 2 - 2)
            sy = cy - radius + 3 + int(intensity * 5)
            # 3. Drop shadow
            p.setOpacity(0.25)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 40))
            shd = QPainterPath()
            shd.moveTo(float(sx + 1), float(sy + 1))
            shd.lineTo(float(sx - 2), float(sy + 7))
            shd.lineTo(float(sx + 4), float(sy + 7))
            shd.closeSubpath()
            p.fillPath(shd, QColor(0, 0, 0, 40))
            p.setOpacity(1.0)
            # 1. Sweat drop gradient
            sweat = QPainterPath()
            sweat.moveTo(float(sx), float(sy))
            sweat.lineTo(float(sx - 3), float(sy + 6))
            sweat.lineTo(float(sx + 3), float(sy + 6))
            sweat.closeSubpath()
            sweat_grad = QLinearGradient(float(sx - 3), float(sy),
                                         float(sx + 3), float(sy + 6))
            sweat_grad.setColorAt(0.0, QColor(200, 230, 255, sweat_alpha))
            sweat_grad.setColorAt(0.4, QColor(100, 180, 255, sweat_alpha))
            sweat_grad.setColorAt(0.7, QColor(60,  140, 220, int(sweat_alpha * 0.8)))
            sweat_grad.setColorAt(1.0, QColor(40,  110, 190, int(sweat_alpha * 0.5)))
            p.fillPath(sweat, sweat_grad)
            # 4. Specular on drop
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, int(sweat_alpha * 0.5)))
            p.drawEllipse(sx - 1, sy, 2, 2)

    # Tilt bob pendulum with metallic shading
    rod_len = int(th * 0.28)
    bob_r = max(4, tw // 10)
    swing = math.sin(t * 4.0) * 20.0
    p.save()
    p.translate(cx, cy - radius - 4)
    p.rotate(swing)
    # 1. Rod: metallic gradient
    rod_grad = QLinearGradient(-2.0, 0.0, 2.0, 0.0)
    rod_grad.setColorAt(0.0, QColor(55,  58,  72))
    rod_grad.setColorAt(0.5, QColor(120, 125, 140))
    rod_grad.setColorAt(1.0, QColor(55,  58,  72))
    p.setPen(QPen(rod_grad, 2))
    p.drawLine(0, 0, 0, rod_len)
    # 3. Bob drop shadow
    p.setOpacity(0.25)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    bob_shad = QPainterPath()
    bob_shad.moveTo(2.0, float(rod_len + 2))
    bob_shad.cubicTo(float(-bob_r + 2), float(rod_len + bob_r + 2),
                     float(-bob_r + 2), float(rod_len + bob_r * 2 + 2),
                     2.0, float(rod_len + bob_r * 2.5 + 2))
    bob_shad.cubicTo(float(bob_r + 2), float(rod_len + bob_r * 2 + 2),
                     float(bob_r + 2), float(rod_len + bob_r + 2),
                     2.0, float(rod_len + 2))
    p.fillPath(bob_shad, QColor(0, 0, 0, 60))
    p.setOpacity(1.0)
    # 1. Teardrop bob: gradient
    bob_path = QPainterPath()
    bob_path.moveTo(0.0, float(rod_len))
    bob_path.cubicTo(float(-bob_r), float(rod_len + bob_r),
                     float(-bob_r), float(rod_len + bob_r * 2),
                     0.0, float(rod_len + bob_r * 2.5))
    bob_path.cubicTo(float(bob_r), float(rod_len + bob_r * 2),
                     float(bob_r), float(rod_len + bob_r),
                     0.0, float(rod_len))
    bob_cg = QConicalGradient(0.0, float(rod_len + bob_r * 1.5), 30.0)
    bob_cg.setColorAt(0.0,  QColor(100, 105, 125, int(180 * intensity)))
    bob_cg.setColorAt(0.25, QColor(160, 165, 180, int(180 * intensity)))
    bob_cg.setColorAt(0.5,  QColor(80,  85, 100, int(180 * intensity)))
    bob_cg.setColorAt(0.75, QColor(140, 145, 160, int(180 * intensity)))
    bob_cg.setColorAt(1.0,  QColor(100, 105, 125, int(180 * intensity)))
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(bob_path, bob_cg)
    # 4. Specular on bob
    spec_bob = QRadialGradient(-float(bob_r // 3), float(rod_len + bob_r * 0.5),
                               float(bob_r * 0.4))
    spec_bob.setColorAt(0.0, QColor(255, 255, 255, int(140 * intensity)))
    spec_bob.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(spec_bob)
    p.drawPath(bob_path)
    p.restore()

    # DANGER text with 5. glow
    danger_alpha = int(180 * intensity * (0.5 + 0.5 * abs(math.sin(t * 5.0))))
    if danger_alpha > 10:
        font = QFont("Arial Black", max(6, tw // 9), QFont.Weight.Black)
        p.setFont(font)
        label = "DANGER"
        fm = p.fontMetrics()
        lx = cx - fm.horizontalAdvance(label) // 2
        ly = cy - radius - rod_len - bob_r * 3 - 4
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(QColor(200, 10, 10, int(danger_alpha * 0.4)))
        p.drawText(lx, ly, label)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QColor(255, 30, 30, danger_alpha))
        p.drawText(lx, ly, label)

    p.restore()


def draw_event_proud(p: QPainter, widget) -> None:
    """Insert lights in a ring around Steely lighting up sequentially."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["proud"]
    fade = max(0.0, 1.0 - t / duration)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    light_count = 8
    light_r = max(3, tw // 14)
    ring_r = int(radius * 1.55)
    colors = [
        QColor(255, 220, 0),
        QColor(255, 40,  40),
        QColor(255, 255, 255),
        QColor(40,  200, 60),
    ]

    for i in range(light_count):
        angle = 2 * math.pi * i / light_count - math.pi / 2
        lx = cx + int(math.cos(angle) * ring_r)
        ly = cy + int(math.sin(angle) * ring_r)
        phase = (t * 3.0 - i * 0.4) % light_count
        on = phase % 1.0 < 0.5
        color = colors[i % len(colors)]

        # 3. Drop shadow
        p.setOpacity(0.22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(lx - light_r + 1, ly - light_r + 2, light_r * 2, light_r * 2)
        p.setOpacity(1.0)

        if on:
            # 5. Glow via CompositionMode_Plus
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            glow = QRadialGradient(float(lx), float(ly), float(light_r * 2.5))
            glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(),
                                        int(fade * 150)))
            glow.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(),
                                        int(fade * 80)))
            glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(lx - light_r * 2, ly - light_r * 2,
                          light_r * 4, light_r * 4)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 1. Insert light dome: 5-stop QRadialGradient
            dome = QRadialGradient(float(lx - light_r // 3), float(ly - light_r // 3),
                                   float(light_r * 1.2))
            dome.setColorAt(0.00, QColor(min(255, color.red() + 100),
                                         min(255, color.green() + 100),
                                         min(255, color.blue() + 100),
                                         int(fade * 255)))
            dome.setColorAt(0.25, QColor(color.red(), color.green(), color.blue(),
                                         int(fade * 240)))
            dome.setColorAt(0.50, QColor(int(color.red() * 0.85),
                                         int(color.green() * 0.85),
                                         int(color.blue() * 0.85),
                                         int(fade * 220)))
            dome.setColorAt(0.75, QColor(int(color.red() * 0.65),
                                         int(color.green() * 0.65),
                                         int(color.blue() * 0.65),
                                         int(fade * 200)))
            dome.setColorAt(1.00, QColor(int(color.red() * 0.4),
                                         int(color.green() * 0.4),
                                         int(color.blue() * 0.4),
                                         int(fade * 180)))
            p.setBrush(dome)
        else:
            dim = QColor(color.red() // 4, color.green() // 4, color.blue() // 4)
            # Dim insert with slight 2. conical gradient
            cg_dim = QConicalGradient(float(lx), float(ly), 30.0)
            cg_dim.setColorAt(0.0, dim)
            cg_dim.setColorAt(0.5, QColor(dim.red() + 15, dim.green() + 15,
                                          dim.blue() + 15))
            cg_dim.setColorAt(1.0, dim)
            p.setBrush(cg_dim)

        p.setPen(QPen(QColor(40, 40, 40, int(fade * 180)), 1))
        p.drawEllipse(lx - light_r, ly - light_r, light_r * 2, light_r * 2)

        if on:
            # 4. Specular highlight
            spec = QRadialGradient(float(lx - light_r // 3), float(ly - light_r // 3),
                                   float(light_r * 0.4))
            spec.setColorAt(0.0, QColor(255, 255, 255, int(fade * 180)))
            spec.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(spec)
            p.drawEllipse(lx - light_r // 2, ly - light_r // 2, light_r, light_r)

        # 7. Bevel
        p.setPen(QPen(QColor(255, 255, 255, int(60 * fade)), 1))
        p.drawArc(lx - light_r, ly - light_r, light_r * 2, light_r * 2,
                  45 * 16, 180 * 16)
        p.setPen(QPen(QColor(0, 0, 0, int(60 * fade)), 1))
        p.drawArc(lx - light_r, ly - light_r, light_r * 2, light_r * 2,
                  225 * 16, 180 * 16)

    p.restore()


def draw_event_offended(p: QPainter, widget) -> None:
    """Outlane wall with metallic shading on the side Steely rolled toward."""
    t = widget._event_anim_t
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    extra_x = widget._passive_extra_x

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    wall_x = cx + int(tw * 0.42) if extra_x >= 0 else cx - int(tw * 0.42)
    wall_w = max(4, tw // 12)
    wall_h = int(th * 0.55)
    wall_y = cy - wall_h // 2

    duration = EVENT_ANIM_DURATIONS["offended"]
    fade = max(0.0, 1.0 - t / duration)

    # 3. Drop shadow
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(wall_x - wall_w // 2 + 2, wall_y + 3, wall_w, wall_h)
    p.setOpacity(1.0)

    # 1. Wall body: 5-stop metallic gradient
    wall_grad = QLinearGradient(float(wall_x - wall_w // 2), 0.0,
                                float(wall_x + wall_w // 2), 0.0)
    wall_grad.setColorAt(0.00, QColor(0x40, 0x44, 0x50, int(fade * 220)))
    wall_grad.setColorAt(0.25, QColor(0x60, 0x65, 0x72, int(fade * 220)))
    wall_grad.setColorAt(0.50, QColor(0x80, 0x88, 0x98, int(fade * 220)))
    wall_grad.setColorAt(0.75, QColor(0x60, 0x65, 0x72, int(fade * 220)))
    wall_grad.setColorAt(1.00, QColor(0x40, 0x44, 0x50, int(fade * 220)))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(wall_grad)
    p.drawRect(wall_x - wall_w // 2, wall_y, wall_w, wall_h)

    # 6. Environment reflection on wall
    env = QLinearGradient(float(wall_x - wall_w // 2), float(wall_y),
                          float(wall_x + wall_w // 2), float(wall_y + wall_h * 0.7))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, int(35 * fade)))
    env.setColorAt(0.6, QColor(255, 255, 255, int(35 * fade)))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(env)
    p.drawRect(wall_x - wall_w // 2, wall_y, wall_w, wall_h)

    # 7. Bevel on wall
    p.setPen(QPen(QColor(255, 255, 255, int(80 * fade)), 1))
    p.drawLine(wall_x - wall_w // 2, wall_y, wall_x + wall_w // 2, wall_y)
    p.drawLine(wall_x - wall_w // 2, wall_y, wall_x - wall_w // 2, wall_y + wall_h)
    p.setPen(QPen(QColor(0, 0, 0, int(80 * fade)), 1))
    p.drawLine(wall_x - wall_w // 2, wall_y + wall_h, wall_x + wall_w // 2, wall_y + wall_h)
    p.drawLine(wall_x + wall_w // 2, wall_y, wall_x + wall_w // 2, wall_y + wall_h)

    # 2. Rivets: QConicalGradient
    rivet_count = 4
    for i in range(rivet_count):
        ry = wall_y + (i + 1) * (wall_h // (rivet_count + 1))
        cg_riv = QConicalGradient(float(wall_x), float(ry), 45.0)
        cg_riv.setColorAt(0.0,  QColor(0xA0, 0xA8, 0xB8, int(fade * 200)))
        cg_riv.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF, int(fade * 200)))
        cg_riv.setColorAt(0.5,  QColor(0x70, 0x78, 0x88, int(fade * 200)))
        cg_riv.setColorAt(0.75, QColor(0xD0, 0xD8, 0xE8, int(fade * 200)))
        cg_riv.setColorAt(1.0,  QColor(0xA0, 0xA8, 0xB8, int(fade * 200)))
        p.setPen(QPen(QColor(0x50, 0x55, 0x60, int(fade * 180)), 1))
        p.setBrush(cg_riv)
        p.drawEllipse(wall_x - 3, ry - 3, 6, 6)
        # 4. Specular on rivet
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, int(140 * fade)))
        p.drawEllipse(wall_x - 2, ry - 2, 2, 2)

    # Chrome edge highlight
    edge_x = wall_x + (wall_w // 2 if extra_x >= 0 else -wall_w // 2)
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8, int(fade * 180)), 1))
    p.drawLine(edge_x, wall_y, edge_x, wall_y + wall_h)

    p.restore()


# ---------------------------------------------------------------------------
# Emotion-state pinball prop overlays for Steely
# ---------------------------------------------------------------------------

def draw_state_talking(p: QPainter, widget) -> None:
    """Pulsing bumper ring around Steely while talking — with QConicalGradient."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)
    t = widget._passive_t
    alpha = int(120 + 100 * abs(math.sin(t * 4.0)))
    ring_r = int(radius * 1.30)
    track_w = 3

    # 3. Drop shadow for ring
    p.setOpacity(0.18)
    p.setPen(QPen(QColor(0, 0, 0, 50), track_w + 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(cx - ring_r + 2, cy - ring_r + 3, ring_r * 2, ring_r * 2)
    p.setOpacity(1.0)

    # 2. Ring: QConicalGradient for metallic bumper ring
    cg = QConicalGradient(float(cx), float(cy), float(t * 60.0) % 360.0)
    cg.setColorAt(0.0,  QColor(0x00, 0xFF, 0x80, alpha))
    cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF, alpha))
    cg.setColorAt(0.5,  QColor(0x00, 0xCC, 0x60, alpha))
    cg.setColorAt(0.75, QColor(0x80, 0xFF, 0xC0, alpha))
    cg.setColorAt(1.0,  QColor(0x00, 0xFF, 0x80, alpha))
    p.setPen(QPen(cg, track_w))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)

    # 5. Neon glow via CompositionMode_Plus
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setPen(QPen(QColor(0x00, 0xFF, 0x80, alpha // 3), track_w + 4))
    p.drawEllipse(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # 6. Environment reflection
    p.setPen(QPen(QColor(255, 255, 255, alpha // 5), 1))
    p.drawEllipse(cx - ring_r + 1, cy - ring_r + 1,
                  ring_r * 2 - 2, ring_r * 2 - 2)

    p.restore()


def draw_state_happy(p: QPainter, widget) -> None:
    """Flipper at bottom in 'up' position while happy — 5-stop gradient + specular."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    flipper_cy = cy + int(th * 0.40)
    flipper_len = int(tw * 0.40)
    flipper_w = max(6, th // 12)

    # 3. Drop shadow
    p.save()
    p.translate(cx + 2, flipper_cy + 3)
    p.rotate(-40.0)
    shad_path = QPainterPath()
    shad_path.moveTo(-flipper_len // 2, -flipper_w // 2)
    shad_path.lineTo(flipper_len // 2, -flipper_w // 4)
    shad_path.lineTo(flipper_len // 2, flipper_w // 4)
    shad_path.lineTo(-flipper_len // 2, flipper_w // 2)
    shad_path.closeSubpath()
    p.setOpacity(0.25)
    p.fillPath(shad_path, QColor(0, 0, 0, 60))
    p.setOpacity(1.0)
    p.restore()

    p.save()
    p.translate(cx, flipper_cy)
    p.rotate(-40.0)

    path = QPainterPath()
    path.moveTo(-flipper_len // 2, -flipper_w // 2)
    path.lineTo(flipper_len // 2, -flipper_w // 4)
    path.lineTo(flipper_len // 2, flipper_w // 4)
    path.lineTo(-flipper_len // 2, flipper_w // 2)
    path.closeSubpath()

    # 1. 5-stop gradient for flipper volume
    grad = QLinearGradient(0.0, float(-flipper_w // 2), 0.0, float(flipper_w // 2))
    grad.setColorAt(0.00, QColor(145, 150, 165))
    grad.setColorAt(0.20, QColor(95,  100, 112))
    grad.setColorAt(0.50, QColor(58,   62,  75))
    grad.setColorAt(0.80, QColor(32,   36,  48))
    grad.setColorAt(1.00, QColor(15,   18,  28))
    p.fillPath(path, grad)

    # 6. Environment reflection stripe
    env = QLinearGradient(float(-flipper_len // 2), float(-flipper_w // 2),
                          float(flipper_len * 0.35), float(flipper_w * 0.35))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 38))
    env.setColorAt(0.6, QColor(255, 255, 255, 38))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.save()
    p.setClipPath(path)
    p.setBrush(env)
    p.setPen(Qt.PenStyle.NoPen)
    bnd = path.boundingRect()
    p.drawRect(bnd)
    p.restore()

    # 7. Bevel on flipper edges
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(-flipper_len // 2, -flipper_w // 2,
               flipper_len // 2,  -flipper_w // 4)
    p.drawLine(-flipper_len // 2, -flipper_w // 2,
               -flipper_len // 2,  flipper_w // 2)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(-flipper_len // 2, flipper_w // 2,
               flipper_len // 2,  flipper_w // 4)
    p.drawLine(flipper_len // 2, -flipper_w // 4,
               flipper_len // 2,  flipper_w // 4)

    # Chrome edge
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    # 2. Chrome pivot bolt: QConicalGradient
    cg = QConicalGradient(0.0, 0.0, 0.0)
    cg.setColorAt(0.0,  QColor(0xC0, 0xC8, 0xD8))
    cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF))
    cg.setColorAt(0.5,  QColor(0x80, 0x88, 0x98))
    cg.setColorAt(0.75, QColor(0xE0, 0xE0, 0xE8))
    cg.setColorAt(1.0,  QColor(0xC0, 0xC8, 0xD8))
    p.setPen(QPen(QColor(0x50, 0x58, 0x68), 1))
    p.setBrush(cg)
    p.drawEllipse(-5, -5, 10, 10)
    # 4. Specular on pivot
    spec = QRadialGradient(-2.0, -2.0, 3.0)
    spec.setColorAt(0.0, QColor(255, 255, 255, 180))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawEllipse(-4, -4, 5, 5)

    p.restore()
    p.restore()


def draw_state_sad(p: QPainter, widget) -> None:
    """Drain hole opening at bottom while sad — concentric QRadialGradient + rim."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    extra_y = widget._passive_extra_y
    fall_fraction = min(1.0, extra_y / (th * 0.35)) if extra_y > 0 else 0.3
    drain_w = int((tw * 0.15) + fall_fraction * tw * 0.15)
    drain_h = max(5, int((th * 0.05) + fall_fraction * th * 0.06))
    drain_y = th + pad - drain_h

    # 3. Drop shadow
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawEllipse(cx - drain_w + 2, drain_y + 3, drain_w * 2, drain_h)
    p.setOpacity(1.0)

    # 1. Drain hole: concentric radial gradient for depth
    hole_grad = QRadialGradient(float(cx), float(drain_y + drain_h // 2),
                                float(drain_w))
    hole_grad.setColorAt(0.00, QColor(4,   3,  10))
    hole_grad.setColorAt(0.25, QColor(8,   6,  18))
    hole_grad.setColorAt(0.50, QColor(15, 12,  28))
    hole_grad.setColorAt(0.75, QColor(25, 20,  38))
    hole_grad.setColorAt(1.00, QColor(35, 28,  48))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(hole_grad)
    p.drawEllipse(cx - drain_w, drain_y, drain_w * 2, drain_h)

    # 7. Metal rim bevel (bright top, dark bottom)
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawArc(cx - drain_w, drain_y, drain_w * 2, drain_h, 0 * 16, 180 * 16)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawArc(cx - drain_w, drain_y, drain_w * 2, drain_h, 180 * 16, 180 * 16)

    # Gutter: metallic gradient
    gutter_grad = QLinearGradient(float(cx - drain_w), float(drain_y + drain_h // 2),
                                  float(cx + drain_w), float(drain_y + drain_h // 2))
    gutter_grad.setColorAt(0.00, QColor(0x40, 0x44, 0x50))
    gutter_grad.setColorAt(0.25, QColor(0x70, 0x75, 0x85))
    gutter_grad.setColorAt(0.50, QColor(0x90, 0x98, 0xA8))
    gutter_grad.setColorAt(0.75, QColor(0x70, 0x75, 0x85))
    gutter_grad.setColorAt(1.00, QColor(0x40, 0x44, 0x50))
    p.setPen(QPen(gutter_grad, 1))
    p.drawLine(cx - drain_w, drain_y + drain_h // 2,
               cx + drain_w, drain_y + drain_h // 2)

    p.restore()


def draw_state_sleepy(p: QPainter, widget) -> None:
    """Trough gutter at bottom and floating ZZZ — 5-stop metallic gradient."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad

    trough_y = th + pad - max(6, th // 10)
    trough_w = int(tw * 0.55)
    trough_h = max(6, th // 10)

    # 3. Drop shadow
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(cx - trough_w // 2 + 2, trough_y + 3, trough_w, trough_h)
    p.setOpacity(1.0)

    # 1. U-shaped trough: 5-stop metallic gradient
    trough_grad = QLinearGradient(float(cx - trough_w // 2), 0.0,
                                  float(cx + trough_w // 2), 0.0)
    trough_grad.setColorAt(0.00, QColor(0x30, 0x33, 0x40))
    trough_grad.setColorAt(0.20, QColor(0x50, 0x55, 0x65))
    trough_grad.setColorAt(0.50, QColor(0x70, 0x78, 0x88))
    trough_grad.setColorAt(0.80, QColor(0x50, 0x55, 0x65))
    trough_grad.setColorAt(1.00, QColor(0x30, 0x33, 0x40))
    p.setPen(QPen(QColor(0x50, 0x55, 0x65), 2))
    p.setBrush(trough_grad)
    p.drawRect(cx - trough_w // 2, trough_y, trough_w, trough_h)

    # 6. Environment reflection on trough
    env = QLinearGradient(float(cx - trough_w // 2), float(trough_y),
                          float(cx + trough_w // 2), float(trough_y + trough_h))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 28))
    env.setColorAt(0.6, QColor(255, 255, 255, 28))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(env)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(cx - trough_w // 2, trough_y, trough_w, trough_h)

    # 7. Bevel on trough
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(cx - trough_w // 2, trough_y,
               cx + trough_w // 2 - 2, trough_y)
    p.drawLine(cx - trough_w // 2, trough_y,
               cx - trough_w // 2, trough_y + trough_h)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(cx - trough_w // 2, trough_y + trough_h,
               cx + trough_w // 2, trough_y + trough_h)
    p.drawLine(cx + trough_w // 2, trough_y,
               cx + trough_w // 2, trough_y + trough_h)

    # ZZZ snore particles
    particles = getattr(widget, "_snore_particles", [])
    cy_top = th // 2 + int(th * 0.20) + pad - int(th * 0.42)
    for part in particles:
        if part.get("alpha", 0) <= 10:
            continue
        font = QFont("Arial", part.get("size", 8), QFont.Weight.Bold)
        p.setFont(font)
        z_alpha = part["alpha"]
        # 5. ZZZ glow
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(QColor(140, 140, 200, z_alpha // 3))
        p.drawText(cx + int(part.get("x_off", 0)),
                   cy_top + int(part.get("y_off", 0)), "Z")
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QColor(210, 210, 255, z_alpha))
        p.drawText(cx + int(part.get("x_off", 0)),
                   cy_top + int(part.get("y_off", 0)), "Z")

    p.restore()


def draw_state_surprised(p: QPainter, widget) -> None:
    """TILT flash with double-layer glow and diagonal tilt indicator line."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    t = widget._passive_t
    flash_alpha = int(140 + 110 * abs(math.sin(t * 6.0)))
    text = "TILT"

    # Diagonal tilt line with gradient
    tilt_grad = QLinearGradient(float(pad), float(pad + int(th * 0.30)),
                                float(tw + pad), float(th + pad - int(th * 0.30)))
    tilt_grad.setColorAt(0.0, QColor(255, 60, 20, 0))
    tilt_grad.setColorAt(0.3, QColor(255, 60, 20, flash_alpha // 2))
    tilt_grad.setColorAt(0.7, QColor(255, 60, 20, flash_alpha // 2))
    tilt_grad.setColorAt(1.0, QColor(255, 60, 20, 0))
    p.setPen(QPen(tilt_grad, 2))
    p.drawLine(pad, pad + int(th * 0.30), tw + pad, th + pad - int(th * 0.30))

    # 5. TILT glow layer via CompositionMode_Plus
    font_big = QFont("Arial Black", max(10, tw // 5), QFont.Weight.Black)
    p.setFont(font_big)
    fm = p.fontMetrics()
    text_w = fm.horizontalAdvance(text)
    ty = cy - int(th * 0.35)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setPen(QColor(200, 40, 10, int(flash_alpha * 0.45)))
    p.drawText(cx - text_w // 2, ty, text)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # Sharp TILT text on top
    font_sharp = QFont("Arial Black", max(8, tw // 6), QFont.Weight.Black)
    p.setFont(font_sharp)
    fm2 = p.fontMetrics()
    text_w2 = fm2.horizontalAdvance(text)
    p.setPen(QColor(255, 60, 20, flash_alpha))
    p.drawText(cx - text_w2 // 2, ty, text)

    # 7. Bevel on TILT text bounding box
    bx = cx - text_w2 // 2 - 2
    bh = fm2.height() + 4
    p.setPen(QPen(QColor(255, 255, 255, 50), 1))
    p.drawLine(bx, ty - bh + 2, bx + text_w2 + 4, ty - bh + 2)
    p.drawLine(bx, ty - bh + 2, bx, ty + 2)
    p.setPen(QPen(QColor(0, 0, 0, 50), 1))
    p.drawLine(bx, ty + 2, bx + text_w2 + 4, ty + 2)
    p.drawLine(bx + text_w2 + 4, ty - bh + 2, bx + text_w2 + 4, ty + 2)

    p.restore()


def draw_state_dismissing(p: QPainter, widget) -> None:
    """Drain hole growing as Steely falls in during dismissal — 3D depth effect."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    scale = getattr(widget, '_scale', 1.0)
    open_fraction = 1.0 - scale
    drain_w = int((tw * 0.10) + open_fraction * tw * 0.25)
    drain_h = max(4, int((th * 0.04) + open_fraction * th * 0.10))
    drain_y = th + pad - drain_h

    # 3. Drop shadow
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawEllipse(cx - drain_w + 2, drain_y + 3, drain_w * 2, drain_h)
    p.setOpacity(1.0)

    # 1. Drain hole: concentric radial gradient for depth illusion
    hole_alpha = int(180 + open_fraction * 75)
    hole_grad = QRadialGradient(float(cx), float(drain_y + drain_h // 2),
                                float(drain_w))
    hole_grad.setColorAt(0.00, QColor(2,   1,   6,  hole_alpha))
    hole_grad.setColorAt(0.25, QColor(6,   4,  14,  hole_alpha))
    hole_grad.setColorAt(0.50, QColor(12, 10,  24,  hole_alpha))
    hole_grad.setColorAt(0.75, QColor(20, 16,  34,  hole_alpha))
    hole_grad.setColorAt(1.00, QColor(30, 24,  44,  hole_alpha))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(hole_grad)
    p.drawEllipse(cx - drain_w, drain_y, drain_w * 2, drain_h)

    # 7. Metal rim bevel
    p.setPen(QPen(QColor(255, 255, 255, int(80 * (0.3 + open_fraction * 0.7))), 1))
    p.drawArc(cx - drain_w, drain_y, drain_w * 2, drain_h, 0 * 16, 180 * 16)
    p.setPen(QPen(QColor(0, 0, 0, int(80 * (0.3 + open_fraction * 0.7))), 1))
    p.drawArc(cx - drain_w, drain_y, drain_w * 2, drain_h, 180 * 16, 180 * 16)

    # 4. Inner glow/depth spec
    if open_fraction > 0.1:
        spec = QRadialGradient(float(cx), float(drain_y + drain_h // 2),
                               float(drain_w * 0.4))
        spec.setColorAt(0.0, QColor(20, 30, 80, int(open_fraction * 60)))
        spec.setColorAt(1.0, QColor(10, 15, 40, 0))
        p.setBrush(spec)
        p.drawEllipse(cx - drain_w, drain_y, drain_w * 2, drain_h)

    p.restore()

