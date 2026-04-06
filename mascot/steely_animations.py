"""steely_animations.py — Tick and draw helpers for Steely the pinball mascot
(_PinballDrawWidget / OverlayTrophie).

This module is imported by mascot.py to keep that file from growing
further.  It follows the same pattern as trophie_animations.py:
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
