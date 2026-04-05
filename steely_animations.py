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
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient,
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
# Passive mode draw (overlay) helpers — called from _PinballDrawWidget.paintEvent()
# ---------------------------------------------------------------------------

def draw_multiball(p: QPainter, widget) -> None:
    """Draw faint ghost-ball copies around the main mascot."""
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
        grad = QRadialGradient(float(gx - radius // 4), float(gy - radius // 3),
                               float(radius * 1.2))
        grad.setColorAt(0.0, QColor(230, 230, 240, alpha))
        grad.setColorAt(0.6, QColor(160, 168, 180, alpha // 2))
        grad.setColorAt(1.0, QColor(80,  90, 110, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(gx - radius, gy - radius, radius * 2, radius * 2)
    p.restore()


def draw_tilt_warning(p: QPainter, widget) -> None:
    """Flash 'TILT' text while in the tilt_warning passive mode phase."""
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
    p.save()
    font = QFont("Arial Black", max(8, tw // 6), QFont.Weight.Black)
    p.setFont(font)
    p.setPen(QColor(255, 60, 20, flash_alpha))
    text = "TILT"
    fm = p.fontMetrics()
    text_w = fm.horizontalAdvance(text)
    text_h = fm.height()
    p.drawText(cx - text_w // 2, cy - int(th * 0.3) - text_h, text)
    p.restore()


# ---------------------------------------------------------------------------
# Event animation tick helpers — called from _PinballDrawWidget._tick()
# when _event_anim matches the name.  Each function updates _passive_extra_x,
# _passive_extra_y, _passive_angle and/or particle lists.
# ---------------------------------------------------------------------------

def tick_event_jackpot_glow(widget) -> None:
    """Initialise sparkle particles for the jackpot glow draw overlay."""
    if not widget._jackpot_particles:
        tw = float(widget._tw)
        th = float(widget._th)
        r = min(tw, th) * 0.38
        widget._jackpot_particles = [
            {
                "angle": random.uniform(0, 2 * math.pi),
                "dist":  random.uniform(r * 0.9, r * 1.4),
                "size":  random.uniform(2.5, 5.0),
                "speed": random.uniform(1.0, 2.5),
                "alpha": random.randint(160, 255),
            }
            for _ in range(14)
        ]
    dt = 0.016
    for sp in widget._jackpot_particles:
        sp["angle"] = (sp["angle"] + sp["speed"] * dt) % (2 * math.pi)
        sp["alpha"] = max(60, sp["alpha"] - 1)
    widget._passive_extra_x = 0.0
    widget._passive_extra_y = 0.0
    widget._passive_angle = 0.0


def tick_event_victory_lap(widget) -> None:
    """Steely circles the widget area once to celebrate a challenge win."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["victory_lap"]
    progress = min(1.0, t / duration)
    angle = progress * 2.0 * math.pi
    rx = widget._tw * 0.30
    ry = widget._th * 0.22
    widget._passive_extra_x = math.cos(angle - math.pi / 2) * rx
    widget._passive_extra_y = math.sin(angle - math.pi / 2) * ry
    widget._passive_angle = math.degrees(angle) % 360.0


def tick_event_drain_fall(widget) -> None:
    """Steely falls downward on a challenge loss, then re-enters from top."""
    t = widget._event_anim_t
    th = float(widget._th)
    pad = float(widget._pad)
    fall_dist = th + pad * 1.5
    if t < 0.8:
        # Fall
        widget._passive_extra_y = (t / 0.8) ** 2 * fall_dist
    elif t < 1.6:
        # Off-screen — wait briefly
        widget._passive_extra_y = fall_dist
    elif t < 2.4:
        # Re-enter from top
        progress = (t - 1.6) / 0.8
        widget._passive_extra_y = -(1.0 - progress) * fall_dist
    else:
        widget._passive_extra_y = 0.0
    widget._passive_extra_x = 0.0
    widget._passive_angle = 0.0


def tick_event_overheat(widget) -> None:
    """Initialise and advance smoke particles for the overheat overlay."""
    dt = 0.016
    if not widget._smoke_particles:
        widget._smoke_particles = [
            {
                "x_off": random.uniform(-10, 10),
                "y":     0.0,
                "vy":    random.uniform(20.0, 45.0),
                "vx":    random.uniform(-8.0, 8.0),
                "size":  random.uniform(4.0, 8.0),
                "alpha": random.randint(140, 210),
                "delay": random.uniform(0.0, 1.2),
            }
            for _ in range(8)
        ]
    for puff in widget._smoke_particles:
        if widget._event_anim_t < puff["delay"]:
            continue
        puff["y"]    -= puff["vy"] * dt
        puff["x_off"] += puff["vx"] * dt
        puff["alpha"]  = max(0, puff["alpha"] - 2)
        puff["size"]   = min(puff["size"] + 0.1, 14.0)
        if puff["alpha"] <= 0:
            puff["y"]     = 0.0
            puff["x_off"] = random.uniform(-10, 10)
            puff["alpha"] = random.randint(140, 210)
            puff["size"]  = random.uniform(4.0, 8.0)
    widget._passive_extra_x = 0.0
    widget._passive_extra_y = 0.0
    widget._passive_angle = 0.0


def tick_event_rust(widget) -> None:
    """Gradually increase the rust desaturation amount."""
    dt = 0.016
    widget._rust_amount = min(1.0, widget._rust_amount + dt * 0.04)
    widget._passive_extra_x = 0.0
    widget._passive_extra_y = 0.0
    widget._passive_angle = 0.0


def tick_event_plunger_entry(widget) -> None:
    """Steely enters from below like a plunger launch at session start."""
    t = widget._event_anim_t
    th = float(widget._th)
    pad = float(widget._pad)
    launch_dist = th + pad * 1.5
    if t < 0.25:
        # Compress down slightly
        widget._passive_extra_y = (t / 0.25) * launch_dist * 0.2
    elif t < 0.7:
        # Shoot up
        progress = (t - 0.25) / 0.45
        eased = math.sin(progress * math.pi / 2)
        widget._passive_extra_y = launch_dist * 0.2 - eased * (launch_dist + launch_dist * 0.2)
    elif t < 1.1:
        # Fall back to rest
        progress = (t - 0.7) / 0.4
        widget._passive_extra_y = -launch_dist * (1.0 - progress * progress)
    elif t < 1.5:
        # Landing bounce
        progress = (t - 1.1) / 0.4
        widget._passive_extra_y = math.sin(progress * math.pi) * launch_dist * 0.12
    else:
        widget._passive_extra_y = 0.0
    widget._passive_extra_x = 0.0
    widget._passive_angle = 0.0


# ---------------------------------------------------------------------------
# Personality animation tick helpers
# ---------------------------------------------------------------------------

def tick_event_show_off(widget) -> None:
    """Steely shows off with a quick spin and chest-puff."""
    t = widget._event_anim_t
    if t < 0.6:
        widget._passive_angle = (t / 0.6) * 360.0
        widget._passive_extra_x = 0.0
    elif t < 1.2:
        widget._passive_angle = 360.0 + ((t - 0.6) / 0.6) * 360.0
        widget._passive_extra_x = 0.0
    else:
        widget._passive_angle = 0.0
        widget._passive_extra_x = 0.0
    widget._passive_extra_y = 0.0


def tick_event_nervous(widget) -> None:
    """Extra vibration before a challenge — rapid jitter + wide eyes."""
    t = widget._event_anim_t
    intensity = min(1.0, t / 2.0)  # ramp up over 2 s
    jitter = intensity * 3.5
    widget._passive_extra_x = random.uniform(-jitter, jitter)
    widget._passive_extra_y = random.uniform(-jitter * 0.6, jitter * 0.6)
    widget._passive_angle = 0.0


def tick_event_proud(widget) -> None:
    """Brief inflate and mustache twitch on a achievement milestone."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["proud"]
    # Scale is handled by modifying extra offsets to simulate a slight puff
    inflate = math.sin(min(1.0, t / (duration * 0.4)) * math.pi) * 3.0
    widget._passive_extra_y = -inflate
    widget._passive_extra_x = 0.0
    widget._passive_angle = 0.0


def tick_event_offended(widget) -> None:
    """Steely turns away if a speech bubble is dismissed too quickly."""
    t = widget._event_anim_t
    duration = EVENT_ANIM_DURATIONS["offended"]
    if t < duration * 0.3:
        # Turn away
        progress = t / (duration * 0.3)
        widget._passive_angle = -progress * 30.0
    elif t < duration * 0.7:
        # Hold turned away
        widget._passive_angle = -30.0
        widget._passive_extra_x = math.sin(t * 3.0) * 1.5
    else:
        # Slowly return
        progress = (t - duration * 0.7) / (duration * 0.3)
        widget._passive_angle = -30.0 * (1.0 - progress)
        widget._passive_extra_x = 0.0
    widget._passive_extra_y = 0.0


# ---------------------------------------------------------------------------
# Event animation draw (overlay) helpers — called from paintEvent()
# ---------------------------------------------------------------------------

def draw_event_jackpot_glow(p: QPainter, widget) -> None:
    """Gold glow ring and sparkles around Steely on achievement unlock."""
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

    # Pulsing golden glow ring
    glow_r = int(radius * (1.25 + 0.12 * math.sin(t * 6.0)))
    glow_alpha = int(130 * fade)
    if glow_alpha > 0:
        glow = QRadialGradient(float(cx), float(cy), float(glow_r * 1.5))
        glow.setColorAt(0.4, QColor(255, 220, 50, glow_alpha))
        glow.setColorAt(0.7, QColor(255, 180, 20, glow_alpha // 2))
        glow.setColorAt(1.0, QColor(255, 150,  0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2)

    # Orbiting star sparkles
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
        p.fillPath(star, QColor(255, 240, 80, alpha))

    p.restore()


def draw_event_victory_lap(p: QPainter, widget) -> None:
    """Draw a motion trail arc while Steely circles on victory lap."""
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
    p.save()
    pen = QPen(QColor(180, 220, 255, trail_alpha), max(2, radius // 4))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    rx = int(tw * 0.30)
    ry = int(th * 0.22)
    p.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)
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

    # Red heat glow
    heat_alpha = int(90 * fade * (0.7 + 0.3 * math.sin(t * 8.0)))
    if heat_alpha > 0:
        heat = QRadialGradient(float(cx), float(cy), float(radius * 1.4))
        heat.setColorAt(0.5, QColor(255, 80, 20, heat_alpha))
        heat.setColorAt(1.0, QColor(255, 40,  0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(heat)
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

    # Smoke puffs
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
        smoke_grad.setColorAt(0.0, QColor(200, 130, 80, alpha))
        smoke_grad.setColorAt(1.0, QColor(200, 130, 80, 0))
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
    # Sepia/rust tint overlay
    tint_alpha = int(min(120, amount * 130))
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(160, 80, 20, tint_alpha))
    p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
    # Random rust spot dots
    random.seed(42)
    for _ in range(int(amount * 8)):
        rx_off = random.randint(-radius + 4, radius - 4)
        ry_off = random.randint(-radius + 4, radius - 4)
        if rx_off * rx_off + ry_off * ry_off > (radius - 3) ** 2:
            continue
        dot_alpha = int(amount * 160)
        sz = random.randint(2, 4)
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

    # Rotating sheen
    sheen_alpha = int(90 * fade * abs(math.sin(t * 4.0)))
    if sheen_alpha > 0:
        sheen = QLinearGradient(
            float(cx - radius), float(cy - radius),
            float(cx + radius), float(cy + radius),
        )
        sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.45, QColor(255, 255, 255, sheen_alpha))
        sheen.setColorAt(0.55, QColor(255, 255, 255, sheen_alpha))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sheen)
        clip = QPainterPath()
        clip.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        p.setClipPath(clip)
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        p.setClipping(False)

    # Mustache sparkle dots
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
                p.setBrush(QColor(255, 240, 80, alpha))
                p.drawEllipse(sx - 2, sy - 2, 4, 4)

    p.restore()


def draw_event_nervous(p: QPainter, widget) -> None:
    """Wide, slightly offset eyes during nervous personality animation."""
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
    eye_y = cy - radius // 5
    eye_r = max(3, radius // 4)
    eye_sep = radius // 2

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Sweat drop(s) on forehead
    sweat_alpha = int(intensity * 180)
    if sweat_alpha > 5:
        for side in (-1, 1):
            sx = cx + side * (radius // 2 - 2)
            sy = cy - radius + 3 + int(intensity * 5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(100, 180, 255, sweat_alpha))
            sweat = QPainterPath()
            sweat.moveTo(float(sx), float(sy))
            sweat.lineTo(float(sx - 3), float(sy + 6))
            sweat.lineTo(float(sx + 3), float(sy + 6))
            sweat.closeSubpath()
            p.fillPath(sweat, QColor(100, 180, 255, sweat_alpha))

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
    p.save()
    grad = QLinearGradient(float(cx), float(cy + radius), float(cx), float(cy + radius + streak_len))
    grad.setColorAt(0.0, QColor(180, 200, 230, streak_alpha))
    grad.setColorAt(1.0, QColor(180, 200, 230, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    streak_w = max(4, radius // 2)
    p.drawRect(cx - streak_w // 2, cy + radius, streak_w, streak_len)
    p.restore()


# ---------------------------------------------------------------------------
# Passive mode draw (overlay) helpers — new pinball prop overlays
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

    # Plunger position: at bottom of widget
    plunger_x = cx
    base_y = cy + int(th * 0.42)
    compress = max(0.0, extra_y / (th * 0.22)) if extra_y > 0 else 0.0
    rod_h = int(th * 0.30)
    rod_y = base_y - int(compress * th * 0.08)

    # Spring coils
    spring_h = int(th * 0.12) - int(compress * th * 0.08)
    spring_h = max(4, spring_h)
    coil_count = 6
    p.setPen(QPen(QColor(0xFF, 0xE8, 0x20), 2))
    for i in range(coil_count):
        y0 = rod_y + rod_h + int(i * spring_h / coil_count)
        y1 = y0 + int(spring_h / coil_count)
        ox = 5 if i % 2 == 0 else -5
        p.drawLine(plunger_x - 5, y0, plunger_x + ox, (y0 + y1) // 2)
        p.drawLine(plunger_x + ox, (y0 + y1) // 2, plunger_x - 5 + 10, y1)

    # Plunger rod
    grad = QLinearGradient(float(plunger_x - 5), 0.0, float(plunger_x + 5), 0.0)
    grad.setColorAt(0.0, QColor(0xC0, 0xC8, 0xD8))
    grad.setColorAt(0.5, QColor(0xFF, 0xFF, 0xFF))
    grad.setColorAt(1.0, QColor(0x80, 0x88, 0x98))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRect(plunger_x - 5, rod_y, 10, rod_h)

    # Rounded tip
    p.setBrush(QColor(0xC0, 0xC8, 0xD8))
    p.setPen(QPen(QColor(0x60, 0x68, 0x78), 1))
    p.drawEllipse(plunger_x - 7, rod_y - 5, 14, 10)
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
        if is_active:
            # Glow
            glow = QRadialGradient(float(bx), float(by), float(br * 2.5))
            glow.setColorAt(0.0, QColor(255, 230, 0, 160))
            glow.setColorAt(1.0, QColor(255, 230, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(bx - br * 2, by - br * 2, br * 4, br * 4)
            # Active bumper
            p.setPen(QPen(QColor(0xFF, 0x20, 0x20), 3))
            p.setBrush(QColor(255, 255, 180))
        else:
            p.setPen(QPen(QColor(0xFF, 0x20, 0x20), 2))
            p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(bx - br, by - br, br * 2, br * 2)
        # Inner ring
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(200, 30, 30), 1))
        p.drawEllipse(bx - br + 3, by - br + 3, (br - 3) * 2, (br - 3) * 2)
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

    # Flipper angle: neutral or flipped up
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

    p.save()
    p.translate(flipper_cx, flipper_cy)
    p.rotate(flip_angle)
    # Tapering flipper shape
    path = QPainterPath()
    path.moveTo(-flipper_len // 2, -flipper_w // 2)
    path.lineTo(flipper_len // 2, -flipper_w // 4)
    path.lineTo(flipper_len // 2, flipper_w // 4)
    path.lineTo(-flipper_len // 2, flipper_w // 2)
    path.closeSubpath()
    # Glossy dark gradient
    grad = QLinearGradient(0.0, float(-flipper_w // 2), 0.0, float(flipper_w // 2))
    grad.setColorAt(0.0, QColor(80, 80, 90))
    grad.setColorAt(0.3, QColor(50, 50, 60))
    grad.setColorAt(1.0, QColor(20, 20, 30))
    p.fillPath(path, grad)
    # Chrome edge
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    # Pivot dot
    p.setBrush(QColor(0xC0, 0xC8, 0xD8))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(-5, -5, 10, 10)
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
    # Ramp walls (two parallel lines)
    p.setPen(QPen(QColor(0xFF, 0x8C, 0x00), ramp_w))
    p.drawLine(ramp_x0, ramp_y0, ramp_x1, ramp_y1)
    p.setPen(QPen(QColor(0xCC, 0x60, 0x00), ramp_w))
    p.drawLine(ramp_x0 + ramp_w + 2, ramp_y0, ramp_x1 + ramp_w + 2, ramp_y1)

    # Lane arrows along ramp
    ramp_dx = ramp_x1 - ramp_x0
    ramp_dy = ramp_y1 - ramp_y0
    ramp_len = math.hypot(ramp_dx, ramp_dy)
    arrow_count = 3
    p.setPen(QPen(QColor(255, 255, 255), 1))
    for i in range(arrow_count):
        t_pos = (i + 1) / (arrow_count + 1)
        ax = int(ramp_x0 + ramp_dx * t_pos)
        ay = int(ramp_y0 + ramp_dy * t_pos)
        angle = math.atan2(ramp_dy, ramp_dx)
        arrow_len = max(5, int(ramp_len * 0.06))
        p.drawLine(
            ax, ay,
            ax + int(math.cos(angle) * arrow_len),
            ay + int(math.sin(angle) * arrow_len),
        )
        p.drawLine(
            ax + int(math.cos(angle) * arrow_len),
            ay + int(math.sin(angle) * arrow_len),
            ax + int(math.cos(angle - 0.5) * arrow_len // 2),
            ay + int(math.sin(angle - 0.5) * arrow_len // 2),
        )
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

    # Drain mouth grows as Steely falls
    fall_fraction = min(1.0, extra_y / (th * 0.35)) if extra_y > 0 else 0.0
    drain_w = int((tw * 0.15) + fall_fraction * tw * 0.20)
    drain_h = int((th * 0.06) + fall_fraction * th * 0.08)
    drain_y = th + pad - drain_h // 2

    # Gutter channel
    p.setPen(QPen(QColor(50, 50, 60), 2))
    p.drawLine(cx - drain_w, drain_y, cx + drain_w, drain_y)

    # Drain hole
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(20, 15, 25))
    p.drawEllipse(cx - drain_w, drain_y - drain_h // 2, drain_w * 2, drain_h)

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
    t = widget._passive_t
    spin_angle = widget._passive_angle

    # Spinner: rectangular paddle on pivot
    sp_cx = cx + int(tw * 0.38)
    sp_cy = cy - int(th * 0.05)
    sp_w = max(6, tw // 8)
    sp_h = max(3, th // 20)

    p.save()
    p.translate(sp_cx, sp_cy)
    p.rotate(spin_angle * 0.5)  # spinner rotates at half Steely's rate

    # Paddle body
    p.setPen(QPen(QColor(180, 180, 200), 1))
    p.setBrush(QColor(240, 240, 255))
    p.drawRect(-sp_w // 2, -sp_h // 2, sp_w, sp_h)

    # Red center line
    p.setPen(QPen(QColor(0xFF, 0x20, 0x20), 1))
    p.drawLine(-sp_w // 2, 0, sp_w // 2, 0)

    # Pivot
    p.setBrush(QColor(100, 100, 120))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(-3, -3, 6, 6)
    p.restore()

    # Pivot rod
    p.setPen(QPen(QColor(100, 100, 120), 1))
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

    # Wireform rail: two parallel arcs
    rail_rx = int(tw * 0.38)
    rail_ry = int(th * 0.25)
    inner_offset = max(3, tw // 20)

    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8, 180), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    rect_outer = QRectF(float(cx - rail_rx), float(cy - rail_ry), float(rail_rx * 2), float(rail_ry * 2))
    p.drawArc(rect_outer, 180 * 16, -180 * 16)  # top half arc

    p.setPen(QPen(QColor(0x80, 0x88, 0x98, 180), 2))
    rect_inner = QRectF(
        float(cx - rail_rx + inner_offset),
        float(cy - rail_ry + inner_offset),
        float((rail_rx - inner_offset) * 2),
        float((rail_ry - inner_offset) * 2),
    )
    p.drawArc(rect_inner, 180 * 16, -180 * 16)
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

    # Intensity based on how far Steely is pulled up
    pull = min(1.0, -extra_y / (th * 0.28)) if extra_y < 0 else 0.0

    mag_cx = cx
    mag_top = pad + int(th * 0.05)
    arm_w = max(5, tw // 12)
    arm_gap = max(12, tw // 5)
    arm_h = max(12, th // 6)

    # U-shape magnet
    # Left arm
    p.setPen(QPen(QColor(40, 40, 50), 1))
    p.setBrush(QColor(60, 60, 70))
    p.drawRect(mag_cx - arm_gap // 2 - arm_w, mag_top, arm_w, arm_h)
    # Right arm
    p.drawRect(mag_cx + arm_gap // 2, mag_top, arm_w, arm_h)
    # Bridge/top
    p.drawRect(mag_cx - arm_gap // 2 - arm_w, mag_top, arm_gap + arm_w * 2, arm_w)

    # Coil windings (red/chrome thin lines)
    coil_turns = 5
    for i in range(coil_turns):
        fy = mag_top + arm_w + i * ((arm_h - arm_w) // coil_turns)
        # Left arm coil
        p.setPen(QPen(QColor(0xFF, 0x40, 0x40, 180), 1))
        p.drawLine(mag_cx - arm_gap // 2 - arm_w - 1, fy,
                   mag_cx - arm_gap // 2 + 1, fy)
        # Right arm coil
        p.drawLine(mag_cx + arm_gap // 2 - 1, fy,
                   mag_cx + arm_gap // 2 + arm_w + 1, fy)

    # Pole tips glow when active
    if pull > 0.1:
        for px_off in (-arm_gap // 2 - arm_w // 2, arm_gap // 2 + arm_w // 2):
            glow = QRadialGradient(float(mag_cx + px_off), float(mag_top + arm_h), float(arm_w * 2))
            glow.setColorAt(0.0, QColor(0x40, 0xA0, 0xFF, int(pull * 160)))
            glow.setColorAt(1.0, QColor(0x40, 0xA0, 0xFF, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(
                mag_cx + px_off - arm_w * 2,
                mag_top + arm_h - arm_w * 2,
                arm_w * 4, arm_w * 4,
            )

    # Field lines
    field_count = 3 + int(pull * 4)
    p.setPen(QPen(QColor(0x40, 0xA0, 0xFF, int(80 + pull * 120)), 1))
    for i in range(field_count):
        fx = mag_cx - arm_gap // 2 + i * (arm_gap // (field_count - 1)) if field_count > 1 else mag_cx
        fy_start = mag_top + arm_h
        fy_end = fy_start + int((th * 0.12) * (0.5 + pull * 0.5))
        p.drawLine(fx, fy_start, fx + int(math.sin(i * 0.8) * 4), fy_end)
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

    # Outer ellipse (neon green glow)
    p.setPen(QPen(QColor(0x00, 0xFF, 0x80, 120), track_w + 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(float(cx - orbit_rx - 2), float(cy - orbit_ry - 2),
                         float((orbit_rx + 2) * 2), float((orbit_ry + 2) * 2)))
    # Inner neon rail
    p.setPen(QPen(QColor(0x00, 0xFF, 0x80, 200), track_w))
    p.drawEllipse(QRectF(float(cx - orbit_rx), float(cy - orbit_ry),
                         float(orbit_rx * 2), float(orbit_ry * 2)))
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

    # Solenoid core
    p.setPen(QPen(QColor(80, 80, 80), 1))
    p.setBrush(QColor(100, 100, 110))
    p.drawRect(sol_x - sol_w // 2, sol_y - sol_h // 2, sol_w, sol_h)

    # Copper winding lines
    turns = 8
    p.setPen(QPen(QColor(0xB8, 0x73, 0x33, 180), 1))
    for i in range(turns):
        wy = sol_y - sol_h // 2 + i * (sol_h // turns)
        p.drawLine(sol_x - sol_w // 2, wy, sol_x + sol_w // 2, wy)

    # Vibration lines (comic jitter marks)
    vib_alpha = int(150 + 80 * abs(math.sin(t * 20.0)))
    p.setPen(QPen(QColor(255, 255, 180, vib_alpha), 1))
    for i, (vx_off, vy_off, vlen) in enumerate([(-sol_w, 0, 6), (sol_w // 2 + 2, -4, 5), (-sol_w // 2 - 2, 4, 4)]):
        vx = sol_x + vx_off
        vy = sol_y + vy_off
        p.drawLine(vx, vy, vx - vlen, vy)
        p.drawLine(vx - vlen, vy, vx - vlen + 3, vy - 3)
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

    # Left lane arrow
    left_active = extra_x < -3.0
    left_color = QColor(255, 255, 120, 240) if left_active else QColor(0xFF, 0x8C, 0x00, 120)
    if left_active:
        glow = QRadialGradient(float(cx - int(tw * 0.28)), float(lane_y), float(arrow_size * 3))
        glow.setColorAt(0.0, QColor(255, 255, 80, 120))
        glow.setColorAt(1.0, QColor(255, 255, 80, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(cx - int(tw * 0.28) - arrow_size * 3, lane_y - arrow_size * 3,
                      arrow_size * 6, arrow_size * 6)
    p.setPen(QPen(left_color, 2))
    p.drawLine(cx - int(tw * 0.10), lane_y, cx - int(tw * 0.10) - lane_len, lane_y)
    # Arrow head
    p.drawLine(cx - int(tw * 0.10) - lane_len, lane_y,
               cx - int(tw * 0.10) - lane_len + arrow_size, lane_y - arrow_size // 2)
    p.drawLine(cx - int(tw * 0.10) - lane_len, lane_y,
               cx - int(tw * 0.10) - lane_len + arrow_size, lane_y + arrow_size // 2)

    # Right lane arrow
    right_active = extra_x > 3.0
    right_color = QColor(255, 255, 120, 240) if right_active else QColor(0xFF, 0x8C, 0x00, 120)
    if right_active:
        glow = QRadialGradient(float(cx + int(tw * 0.28)), float(lane_y), float(arrow_size * 3))
        glow.setColorAt(0.0, QColor(255, 255, 80, 120))
        glow.setColorAt(1.0, QColor(255, 255, 80, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(cx + int(tw * 0.28) - arrow_size * 3, lane_y - arrow_size * 3,
                      arrow_size * 6, arrow_size * 6)
    p.setPen(QPen(right_color, 2))
    p.drawLine(cx + int(tw * 0.10), lane_y, cx + int(tw * 0.10) + lane_len, lane_y)
    p.drawLine(cx + int(tw * 0.10) + lane_len, lane_y,
               cx + int(tw * 0.10) + lane_len - arrow_size, lane_y - arrow_size // 2)
    p.drawLine(cx + int(tw * 0.10) + lane_len, lane_y,
               cx + int(tw * 0.10) + lane_len - arrow_size, lane_y + arrow_size // 2)
    p.restore()


# ---------------------------------------------------------------------------
# Updated event draw helpers — pinball-themed additions
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

    # Pulsing golden glow ring
    glow_r = int(radius * (1.25 + 0.12 * math.sin(t * 6.0)))
    glow_alpha = int(130 * fade)
    if glow_alpha > 0:
        glow = QRadialGradient(float(cx), float(cy), float(glow_r * 1.5))
        glow.setColorAt(0.4, QColor(255, 220, 50, glow_alpha))
        glow.setColorAt(0.7, QColor(255, 180, 20, glow_alpha // 2))
        glow.setColorAt(1.0, QColor(255, 150, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2)

    # Orbiting star sparkles
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
        p.fillPath(star, QColor(255, 240, 80, alpha))

    # DMD "JACKPOT" display
    dmd_alpha = int(220 * fade)
    if dmd_alpha > 10:
        dmd_w = min(tw - 4, max(40, int(tw * 0.80)))
        dmd_h = max(12, int(th * 0.14))
        dmd_x = cx - dmd_w // 2
        dmd_y = cy - radius - dmd_h - 8
        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(10, 10, 10, dmd_alpha))
        p.drawRoundedRect(dmd_x, dmd_y, dmd_w, dmd_h, 2, 2)
        # Pixel dot grid texture
        dot_spacing = max(2, dmd_h // 4)
        p.setBrush(QColor(0xFF, 0x88, 0x00, dmd_alpha // 3))
        for row in range(dmd_h // dot_spacing):
            for col in range(dmd_w // dot_spacing):
                p.drawEllipse(dmd_x + 1 + col * dot_spacing, dmd_y + 1 + row * dot_spacing, 1, 1)
        # Text
        p.setPen(QColor(0xFF, 0x99, 0x00, dmd_alpha))
        font = QFont("Courier", max(5, dmd_h - 4), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(dmd_x + 2, dmd_y + dmd_h - 3, "JACKPOT")

    p.restore()


def draw_event_victory_lap(p: QPainter, widget) -> None:
    """Motion trail arc and wireform rail while Steely circles on victory lap."""
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

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Wireform rail (chrome + neon, behind Steely)
    rx = int(tw * 0.30)
    ry = int(th * 0.22)
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8, int(160 * fade)), max(2, radius // 6)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)
    p.setPen(QPen(QColor(0x00, 0xFF, 0x80, int(80 * fade)), 1))
    p.drawEllipse(cx - rx - 2, cy - ry - 2, (rx + 2) * 2, (ry + 2) * 2)

    # Motion trail
    trail_alpha = int(80 * fade)
    if trail_alpha > 0:
        pen = QPen(QColor(180, 220, 255, trail_alpha), max(2, radius // 4))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)

    p.restore()


def draw_event_drain_fall(p: QPainter, widget) -> None:
    """Drain hole and BALL SAVE text during drain_fall."""
    t = widget._event_anim_t
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Drain hole at bottom
    drain_w = int(tw * 0.25)
    drain_h = max(6, int(th * 0.08))
    drain_y = th + pad - drain_h
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(15, 10, 20))
    p.drawEllipse(cx - drain_w, drain_y, drain_w * 2, drain_h)

    # Gutter
    p.setPen(QPen(QColor(50, 50, 60), 2))
    p.drawLine(cx - drain_w, drain_y + drain_h // 2, cx + drain_w, drain_y + drain_h // 2)

    # Sad text + BALL SAVE
    if 1.6 <= t < 2.4:
        alpha = int(180 * min(1.0, (t - 1.6) / 0.3))
        p.setPen(QColor(100, 160, 255, alpha))
        font = QFont("Arial", max(7, tw // 9))
        p.setFont(font)
        p.drawText(cx - 12, cy - int(th * 0.55), ":(")

        # BALL SAVE blink
        blink_alpha = 220 if int(t * 4) % 2 == 0 else 60
        p.setPen(QColor(0xFF, 0x20, 0x20, blink_alpha))
        font2 = QFont("Arial Black", max(5, tw // 11), QFont.Weight.Black)
        p.setFont(font2)
        label = "BALL SAVE"
        fm = p.fontMetrics()
        p.drawText(cx - fm.horizontalAdvance(label) // 2, drain_y - 6, label)

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

    # Red heat glow
    heat_alpha = int(90 * fade * (0.7 + 0.3 * math.sin(t * 8.0)))
    if heat_alpha > 0:
        heat = QRadialGradient(float(cx), float(cy), float(radius * 1.4))
        heat.setColorAt(0.5, QColor(255, 80, 20, heat_alpha))
        heat.setColorAt(1.0, QColor(255, 40, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(heat)
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

    # Smoke puffs
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
        smoke_grad.setColorAt(0.0, QColor(200, 130, 80, alpha))
        smoke_grad.setColorAt(1.0, QColor(200, 130, 80, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(smoke_grad)
        p.drawEllipse(sx - sz, sy - sz, sz * 2, sz * 2)

    # Solenoid coils on each side
    coil_w = max(8, tw // 8)
    coil_h = max(6, th // 10)
    for side_x in (cx - radius - coil_w - 4, cx + radius + 4):
        coil_y = cy - coil_h // 2
        # Gradient from red-hot to orange
        grad = QLinearGradient(float(side_x), float(coil_y), float(side_x), float(coil_y + coil_h))
        grad.setColorAt(0.0, QColor(255, 80, 0, int(fade * 220)))
        grad.setColorAt(1.0, QColor(220, 30, 0, int(fade * 220)))
        p.setPen(QPen(QColor(80, 20, 0), 1))
        p.setBrush(grad)
        p.drawRect(side_x, coil_y, coil_w, coil_h)
        # Winding lines
        turns = 5
        p.setPen(QPen(QColor(200, 60, 0, int(fade * 200)), 1))
        for i in range(turns):
            wy = coil_y + i * (coil_h // turns)
            p.drawLine(side_x, wy, side_x + coil_w, wy)

    # Sparks
    spark_alpha = int(fade * 200 * abs(math.sin(t * 15.0)))
    if spark_alpha > 10:
        p.setPen(QPen(QColor(255, 240, 80, spark_alpha), 1))
        for i in range(6):
            angle = i * math.pi / 3 + t * 5.0
            r0 = radius + 8
            r1 = r0 + random.randint(4, 10)
            p.drawLine(
                cx + int(math.cos(angle) * r0),
                cy + int(math.sin(angle) * r0),
                cx + int(math.cos(angle) * r1),
                cy + int(math.sin(angle) * r1),
            )

    p.restore()


def draw_event_plunger_entry(p: QPainter, widget) -> None:
    """Motion blur streak and plunger rod during plunger-entry launch."""
    t = widget._event_anim_t
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    radius = int(min(tw, th) * 0.38)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Motion blur streak (during launch phase)
    if 0.25 <= t < 1.1:
        progress = (t - 0.25) / 0.85
        streak_alpha = int(120 * (1.0 - progress))
        streak_len = int(radius * 2.5 * (1.0 - progress))
        if streak_alpha > 0 and streak_len > 0:
            grad = QLinearGradient(float(cx), float(cy + radius),
                                   float(cx), float(cy + radius + streak_len))
            grad.setColorAt(0.0, QColor(180, 200, 230, streak_alpha))
            grad.setColorAt(1.0, QColor(180, 200, 230, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            streak_w = max(4, radius // 2)
            p.drawRect(cx - streak_w // 2, cy + radius, streak_w, streak_len)

    # Plunger rod visible when t < 0.7
    if t < 0.7:
        plunger_fade = max(0.0, 1.0 - t / 0.7)
        spring_extend = t / 0.7  # 0 = compressed, 1 = extended
        rod_y = cy + radius + 2
        rod_h = int(th * 0.18 * plunger_fade)
        rod_w = max(4, radius // 3)

        # Spring
        spring_h = max(4, int(th * 0.08 * (0.4 + spring_extend * 0.6)))
        p.setPen(QPen(QColor(0xFF, 0xE8, 0x20, int(plunger_fade * 220)), 2))
        coil_count = 5
        for i in range(coil_count):
            sy0 = rod_y + rod_h + int(i * spring_h / coil_count)
            sy1 = sy0 + int(spring_h / coil_count)
            ox = 4 if i % 2 == 0 else -4
            p.drawLine(cx - 4, sy0, cx + ox, (sy0 + sy1) // 2)
            p.drawLine(cx + ox, (sy0 + sy1) // 2, cx + 4, sy1)

        # Rod
        grad = QLinearGradient(float(cx - rod_w // 2), 0.0, float(cx + rod_w // 2), 0.0)
        grad.setColorAt(0.0, QColor(0xC0, 0xC8, 0xD8, int(plunger_fade * 220)))
        grad.setColorAt(0.5, QColor(0xFF, 0xFF, 0xFF, int(plunger_fade * 220)))
        grad.setColorAt(1.0, QColor(0x80, 0x88, 0x98, int(plunger_fade * 220)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        if rod_h > 0:
            p.drawRect(cx - rod_w // 2, rod_y, rod_w, rod_h)

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

    # Rotating sheen
    sheen_alpha = int(90 * fade * abs(math.sin(t * 4.0)))
    if sheen_alpha > 0:
        sheen = QLinearGradient(
            float(cx - radius), float(cy - radius),
            float(cx + radius), float(cy + radius),
        )
        sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.45, QColor(255, 255, 255, sheen_alpha))
        sheen.setColorAt(0.55, QColor(255, 255, 255, sheen_alpha))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sheen)
        clip = QPainterPath()
        clip.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        p.setClipPath(clip)
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        p.setClipping(False)

    # Mustache sparkle dots
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
                p.setBrush(QColor(255, 240, 80, alpha))
                p.drawEllipse(sx - 2, sy - 2, 4, 4)

    # Small ramp in bottom-left
    ramp_x0 = pad + 2
    ramp_y0 = th + pad - 4
    ramp_x1 = cx - radius - 4
    ramp_y1 = cy + int(th * 0.10)
    p.setPen(QPen(QColor(0xFF, 0x8C, 0x00, int(180 * fade)), 2))
    p.drawLine(ramp_x0, ramp_y0, ramp_x1, ramp_y1)
    p.setPen(QPen(QColor(0xCC, 0x60, 0x00, int(140 * fade)), 2))
    p.drawLine(ramp_x0 + 3, ramp_y0, ramp_x1 + 3, ramp_y1)

    # Combo multiplier text sequence
    combos = ["2x", "3x", "4x"]
    combo_idx = min(len(combos) - 1, int(t / (duration / 3)))
    combo_phase = (t % (duration / 3)) / (duration / 3)
    combo_alpha = int(fade * 220 * min(1.0, combo_phase * 4.0) * (1.0 - max(0.0, combo_phase - 0.7) / 0.3))
    if combo_alpha > 10:
        font = QFont("Arial Black", max(8, tw // 7), QFont.Weight.Black)
        p.setFont(font)
        p.setPen(QColor(255, 220, 0, combo_alpha))
        label = combos[combo_idx]
        fm = p.fontMetrics()
        p.drawText(cx - fm.horizontalAdvance(label) // 2, cy - radius - 8, label)

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

    # Sweat drops
    sweat_alpha = int(intensity * 180)
    if sweat_alpha > 5:
        for side in (-1, 1):
            sx = cx + side * (radius // 2 - 2)
            sy = cy - radius + 3 + int(intensity * 5)
            p.setPen(Qt.PenStyle.NoPen)
            sweat = QPainterPath()
            sweat.moveTo(float(sx), float(sy))
            sweat.lineTo(float(sx - 3), float(sy + 6))
            sweat.lineTo(float(sx + 3), float(sy + 6))
            sweat.closeSubpath()
            p.fillPath(sweat, QColor(100, 180, 255, sweat_alpha))

    # Tilt bob: teardrop pendulum hanging from top-center
    rod_len = int(th * 0.28)
    bob_r = max(4, tw // 10)
    swing = math.sin(t * 4.0) * 20.0  # degrees
    p.save()
    p.translate(cx, cy - radius - 4)
    p.rotate(swing)
    # Rod
    p.setPen(QPen(QColor(80, 80, 100), 1))
    p.drawLine(0, 0, 0, rod_len)
    # Teardrop bob
    bob_path = QPainterPath()
    bob_path.moveTo(0.0, float(rod_len))
    bob_path.cubicTo(float(-bob_r), float(rod_len + bob_r),
                     float(-bob_r), float(rod_len + bob_r * 2),
                     0.0, float(rod_len + bob_r * 2.5))
    bob_path.cubicTo(float(bob_r), float(rod_len + bob_r * 2),
                     float(bob_r), float(rod_len + bob_r),
                     0.0, float(rod_len))
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(bob_path, QColor(80, 80, 100, int(180 * intensity)))
    p.restore()

    # DANGER text
    danger_alpha = int(180 * intensity * (0.5 + 0.5 * abs(math.sin(t * 5.0))))
    if danger_alpha > 10:
        font = QFont("Arial Black", max(6, tw // 9), QFont.Weight.Black)
        p.setFont(font)
        p.setPen(QColor(255, 30, 30, danger_alpha))
        label = "DANGER"
        fm = p.fontMetrics()
        p.drawText(cx - fm.horizontalAdvance(label) // 2,
                   cy - radius - rod_len - bob_r * 3 - 4, label)

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
        QColor(255, 220, 0),  # yellow
        QColor(255, 40, 40),  # red
        QColor(255, 255, 255), # white
        QColor(40, 200, 60),  # green
    ]

    for i in range(light_count):
        angle = 2 * math.pi * i / light_count - math.pi / 2
        lx = cx + int(math.cos(angle) * ring_r)
        ly = cy + int(math.sin(angle) * ring_r)
        phase = (t * 3.0 - i * 0.4) % light_count
        on = phase % 1.0 < 0.5
        color = colors[i % len(colors)]
        if on:
            # Glow
            glow = QRadialGradient(float(lx), float(ly), float(light_r * 2.5))
            glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), int(fade * 150)))
            glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(lx - light_r * 2, ly - light_r * 2, light_r * 4, light_r * 4)
            p.setBrush(color)
        else:
            dim = QColor(color.red() // 4, color.green() // 4, color.blue() // 4)
            p.setBrush(dim)
        p.setPen(QPen(QColor(40, 40, 40, int(fade * 180)), 1))
        p.drawEllipse(lx - light_r, ly - light_r, light_r * 2, light_r * 2)

    p.restore()


def draw_event_offended(p: QPainter, widget) -> None:
    """Outlane wall on the side Steely rolled toward."""
    t = widget._event_anim_t
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    extra_x = widget._passive_extra_x

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Determine wall side
    wall_x = cx + int(tw * 0.42) if extra_x >= 0 else cx - int(tw * 0.42)
    wall_w = max(4, tw // 12)
    wall_h = int(th * 0.55)
    wall_y = cy - wall_h // 2

    duration = EVENT_ANIM_DURATIONS["offended"]
    fade = max(0.0, 1.0 - t / duration)

    # Wall body
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(60, 65, 70, int(fade * 220)))
    p.drawRect(wall_x - wall_w // 2, wall_y, wall_w, wall_h)

    # Rivets
    p.setBrush(QColor(90, 95, 100, int(fade * 200)))
    rivet_count = 4
    for i in range(rivet_count):
        ry = wall_y + (i + 1) * (wall_h // (rivet_count + 1))
        p.drawEllipse(wall_x - 3, ry - 3, 6, 6)

    # Chrome edge highlight
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8, int(fade * 180)), 1))
    edge_x = wall_x + (wall_w // 2 if extra_x >= 0 else -wall_w // 2)
    p.drawLine(edge_x, wall_y, edge_x, wall_y + wall_h)

    p.restore()


# ---------------------------------------------------------------------------
# Emotion-state pinball prop overlays for Steely
# ---------------------------------------------------------------------------

def draw_state_talking(p: QPainter, widget) -> None:
    """Pulsing bumper ring around Steely while talking."""
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
    p.setPen(QPen(QColor(0x00, 0xFF, 0x80, alpha), 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
    p.restore()


def draw_state_happy(p: QPainter, widget) -> None:
    """Flipper at bottom in 'up' position while happy."""
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

    p.save()
    p.translate(cx, flipper_cy)
    p.rotate(-40.0)  # up position
    path = QPainterPath()
    path.moveTo(-flipper_len // 2, -flipper_w // 2)
    path.lineTo(flipper_len // 2, -flipper_w // 4)
    path.lineTo(flipper_len // 2, flipper_w // 4)
    path.lineTo(-flipper_len // 2, flipper_w // 2)
    path.closeSubpath()
    grad = QLinearGradient(0.0, float(-flipper_w // 2), 0.0, float(flipper_w // 2))
    grad.setColorAt(0.0, QColor(80, 80, 90))
    grad.setColorAt(0.3, QColor(50, 50, 60))
    grad.setColorAt(1.0, QColor(20, 20, 30))
    p.fillPath(path, grad)
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.restore()
    p.restore()


def draw_state_sad(p: QPainter, widget) -> None:
    """Drain hole opening at bottom while sad."""
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

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(15, 10, 20))
    p.drawEllipse(cx - drain_w, drain_y, drain_w * 2, drain_h)
    p.setPen(QPen(QColor(50, 50, 60), 1))
    p.drawLine(cx - drain_w, drain_y + drain_h // 2, cx + drain_w, drain_y + drain_h // 2)
    p.restore()


def draw_state_sleepy(p: QPainter, widget) -> None:
    """Trough gutter at bottom and floating ZZZ while sleepy."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad

    # U-shaped trough
    trough_y = th + pad - max(6, th // 10)
    trough_w = int(tw * 0.55)
    trough_h = max(6, th // 10)
    p.setPen(QPen(QColor(60, 65, 75), 2))
    p.setBrush(QColor(30, 30, 40))
    p.drawRect(cx - trough_w // 2, trough_y, trough_w, trough_h)
    p.setPen(QPen(QColor(80, 85, 95), 1))
    p.drawLine(cx - trough_w // 2 + 2, trough_y + 2, cx + trough_w // 2 - 2, trough_y + 2)

    # ZZZ from snore particles
    particles = getattr(widget, "_snore_particles", [])
    cy_top = th // 2 + int(th * 0.20) + pad - int(th * 0.42)
    for part in particles:
        if part.get("alpha", 0) <= 10:
            continue
        font = QFont("Arial", part.get("size", 8), QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(210, 210, 255, part["alpha"]))
        p.drawText(cx + int(part.get("x_off", 0)), cy_top + int(part.get("y_off", 0)), "Z")
    p.restore()


def draw_state_surprised(p: QPainter, widget) -> None:
    """TILT flash and diagonal tilt indicator line."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
    t = widget._passive_t
    flash_alpha = int(140 + 110 * abs(math.sin(t * 6.0)))

    # Diagonal tilt line
    p.setPen(QPen(QColor(255, 60, 20, flash_alpha // 2), 2))
    p.drawLine(pad, pad + int(th * 0.30), tw + pad, th + pad - int(th * 0.30))

    # TILT text
    font = QFont("Arial Black", max(8, tw // 6), QFont.Weight.Black)
    p.setFont(font)
    p.setPen(QColor(255, 60, 20, flash_alpha))
    text = "TILT"
    fm = p.fontMetrics()
    text_w = fm.horizontalAdvance(text)
    p.drawText(cx - text_w // 2, cy - int(th * 0.35), text)
    p.restore()


def draw_state_dismissing(p: QPainter, widget) -> None:
    """Drain hole growing as Steely falls in during dismissal."""
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

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(15, 10, 20, int(180 + open_fraction * 75)))
    p.drawEllipse(cx - drain_w, drain_y, drain_w * 2, drain_h)
    p.restore()
