"""trophy_animations.py — Office/intellectual passive animation tick and draw
helpers for _TrophieDrawWidget (GUITrophie).

Each tick_* function receives the draw-widget instance and updates its state
fields (_passive_t, _passive_extra_x, _passive_extra_y, _passive_angle,
_snore_particles, _confetti_particles).  Each draw_* function receives the
active QPainter and the widget instance and renders an overlay on top of the
already-drawn trophy.
"""
from __future__ import annotations

import math
import random

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient,
)

# ---------------------------------------------------------------------------
# Event animation durations (seconds)
# ---------------------------------------------------------------------------

EVENT_ANIM_DURATIONS: dict[str, float] = {
    "eureka":        3.0,
    "chart_update":  3.5,
    "file_complete": 3.0,
    "red_pen":       3.0,
    "coffee_break":  4.0,
    "deep_research": 3.5,
}

# ---------------------------------------------------------------------------
# Shared helper colors
# ---------------------------------------------------------------------------
_BROWN      = QColor(0x6B, 0x42, 0x26)
_TAN        = QColor(0xD2, 0xB4, 0x8C)
_COFFEE     = QColor(0x4A, 0x2C, 0x0A)
_GRAY       = QColor(0x88, 0x88, 0x88)
_DARK_GREEN = QColor(0x2D, 0x5A, 0x27)
_BEIGE      = QColor(0xF5, 0xF0, 0xDC)
_DARK_BLUE  = QColor(0x1A, 0x3A, 0x5C)


def _trophy_center(widget):
    """Return (cx, cy, tw, th, pad) tracking the animated character centre.

    Replicates the same bob/jump/wiggle/passive-extra transforms that
    paintEvent applies via p.translate(), so every overlay prop drawn
    relative to (cx, cy) automatically follows the mascot body.
    """
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    base_cx = tw // 2 + pad
    base_cy = th // 2 + int(th * 0.20) + pad

    # ── Bob ──────────────────────────────────────────────────────────────────
    state = getattr(widget, '_state', 'idle')
    passive_mode = getattr(widget, '_passive_mode', '')
    bob_t = getattr(widget, '_bob_t', 0.0)
    if state == 'idle' and passive_mode in ("rubber_bounce", "rubber_ring_bounce"):
        bob = -abs(math.sin(bob_t * 2.0)) * 10.0
    else:
        bob = math.sin(bob_t) * 3.0

    # ── Jump ─────────────────────────────────────────────────────────────────
    jump = getattr(widget, '_jump_offset', 0.0) if getattr(widget, '_jumping', False) else 0.0

    # ── Horizontal wiggle (SURPRISED only) ───────────────────────────────────
    wiggle_t = getattr(widget, '_wiggle_t', 0.0)
    wiggle_x = math.sin(wiggle_t) * 4.0 if state == 'surprised' else 0.0

    # ── Passive-extra offsets ─────────────────────────────────────────────────
    extra_x = getattr(widget, '_passive_extra_x', 0.0)
    extra_y = getattr(widget, '_passive_extra_y', 0.0)

    cx = base_cx + int(wiggle_x + extra_x)
    cy = base_cy + int(bob + jump + extra_y)
    return cx, cy, tw, th, pad


# ---------------------------------------------------------------------------
# Passive tick helpers
# ---------------------------------------------------------------------------

def tick_reading(widget) -> None:
    t = widget._passive_t
    widget._passive_extra_x = math.sin(t * 0.8) * 2.0
    widget._passive_angle   = math.sin(t * 0.8) * 3.0


def tick_clipboard_check(widget) -> None:
    pass  # no body movement


def tick_thinking(widget) -> None:
    t = widget._passive_t
    widget._passive_extra_y = -math.sin(min(1.0, t / 0.8) * math.pi / 2) * 4.0


def tick_chart_analysis(widget) -> None:
    t = widget._passive_t
    widget._passive_extra_x = math.sin(t * 1.0) * 2.0


def tick_glasses_adjust(widget) -> None:
    t = widget._passive_t
    widget._passive_angle = math.sin(t * 1.5) * 4.0


def tick_coffee_sip(widget) -> None:
    t = widget._passive_t
    widget._passive_extra_y = math.sin(t * 0.8) * 3.0


def tick_typing(widget) -> None:
    pass  # no body movement


def tick_eureka_moment(widget) -> None:
    t = widget._passive_t
    cycle = t % 5.0
    if cycle < 0.3:
        widget._passive_extra_y = -8.0
    else:
        widget._passive_extra_y = max(0.0, widget._passive_extra_y + 0.8)


def tick_filing(widget) -> None:
    t = widget._passive_t
    widget._passive_extra_x = math.sin(t * 1.2) * 5.0


def tick_stamp_approve(widget) -> None:
    pass  # no body movement


def tick_calculator(widget) -> None:
    t = widget._passive_t
    widget._passive_angle = math.sin(t * 1.0) * 3.0


def tick_magnifying_glass(widget) -> None:
    t = widget._passive_t
    widget._passive_extra_x = math.sin(t * 1.0) * 8.0


def tick_presentation(widget) -> None:
    pass  # no body movement


def tick_sticky_notes(widget) -> None:
    t = widget._passive_t
    widget._passive_extra_y = math.sin(t * 2.0) * 3.0


def tick_paper_airplane(widget) -> None:
    pass  # airplane position driven by draw function via _passive_t


def tick_pencil_tap(widget) -> None:
    t = widget._passive_t
    widget._passive_extra_y = abs(math.sin(t * 4.0)) * 2.0


# ---------------------------------------------------------------------------
# Passive draw helpers
# ---------------------------------------------------------------------------

def draw_reading(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    bx = cx + int(tw * 0.30)
    by = cy + int(th * 0.10)
    bw = int(tw * 0.28)
    bh = int(th * 0.22)

    # Drop shadow under whole book
    p.setOpacity(0.28)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(bx - bw + 3, by + 3, bw * 2 + 2, bh + 2, 3, 3)
    p.setOpacity(1.0)

    # Spine gradient (leather look)
    spine_w = max(3, bw // 8)
    spine_grad = QLinearGradient(float(bx - spine_w), 0.0, float(bx + spine_w), 0.0)
    spine_grad.setColorAt(0.00, QColor(0x40, 0x22, 0x08))
    spine_grad.setColorAt(0.25, QColor(0x70, 0x42, 0x18))
    spine_grad.setColorAt(0.50, QColor(0x90, 0x5A, 0x28))
    spine_grad.setColorAt(0.75, QColor(0x60, 0x38, 0x14))
    spine_grad.setColorAt(1.00, QColor(0x38, 0x1C, 0x06))
    p.setPen(QPen(QColor(40, 20, 5), 1))
    p.setBrush(spine_grad)
    p.drawRect(bx - spine_w, by, spine_w * 2, bh)

    # Left page — warm paper gradient
    l_grad = QLinearGradient(float(bx - bw), 0.0, float(bx), 0.0)
    l_grad.setColorAt(0.00, QColor(0xD8, 0xD0, 0xB8))
    l_grad.setColorAt(0.20, QColor(0xE8, 0xE2, 0xCC))
    l_grad.setColorAt(0.50, QColor(0xF5, 0xF0, 0xDC))
    l_grad.setColorAt(0.80, QColor(0xF0, 0xEB, 0xD5))
    l_grad.setColorAt(1.00, QColor(0xE0, 0xD8, 0xC0))
    path_l = QPainterPath()
    path_l.moveTo(float(bx), float(by))
    path_l.lineTo(float(bx - bw), float(by + int(bh * 0.05)))
    path_l.lineTo(float(bx - bw), float(by + bh))
    path_l.lineTo(float(bx), float(by + bh))
    path_l.closeSubpath()
    p.setPen(QPen(QColor(80, 50, 20), 1))
    p.fillPath(path_l, l_grad)
    p.drawPath(path_l)

    # Right page — slightly cooler paper
    r_grad = QLinearGradient(float(bx), 0.0, float(bx + bw), 0.0)
    r_grad.setColorAt(0.00, QColor(0xE0, 0xD8, 0xC0))
    r_grad.setColorAt(0.20, QColor(0xEE, 0xE8, 0xD2))
    r_grad.setColorAt(0.50, QColor(0xF5, 0xF2, 0xE0))
    r_grad.setColorAt(0.80, QColor(0xE8, 0xE2, 0xCC))
    r_grad.setColorAt(1.00, QColor(0xD8, 0xD0, 0xB8))
    path_r = QPainterPath()
    path_r.moveTo(float(bx), float(by))
    path_r.lineTo(float(bx + bw), float(by + int(bh * 0.05)))
    path_r.lineTo(float(bx + bw), float(by + bh))
    path_r.lineTo(float(bx), float(by + bh))
    path_r.closeSubpath()
    p.fillPath(path_r, r_grad)
    p.drawPath(path_r)

    # Environment reflection on pages
    env = QLinearGradient(float(bx - bw), float(by), float(bx + bw * 0.6), float(by + bh * 0.6))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 30))
    env.setColorAt(0.6, QColor(255, 255, 255, 30))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(env)
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(path_r, env)

    # Page lines on left
    p.setPen(QPen(QColor(180, 160, 120, 120), 1))
    for i in range(4):
        ly = by + int(bh * 0.20) + i * int(bh * 0.17)
        p.drawLine(bx - bw + 6, ly, bx - 6, ly)
    # Page lines on right
    for i in range(4):
        ly = by + int(bh * 0.20) + i * int(bh * 0.17)
        p.drawLine(bx + 6, ly, bx + bw - 6, ly)

    # Bevel on book edges
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.drawLine(bx - bw, by + int(bh * 0.05), bx - bw, by + bh)
    p.drawLine(bx - bw, by + int(bh * 0.05), bx, by)
    p.setPen(QPen(QColor(0, 0, 0, 60), 1))
    p.drawLine(bx - bw, by + bh, bx + bw, by + bh)
    p.drawLine(bx + bw, by + int(bh * 0.05), bx + bw, by + bh)

    # Page-turn animation
    if t % 3.0 < 0.2:
        arc_alpha = int(180 * (1.0 - (t % 3.0) / 0.2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0xF5, 0xF0, 0xDC, arc_alpha))
        p.drawEllipse(QRectF(float(bx), float(by), float(bw * 0.5), float(bh * 0.7)))
    p.restore()


def draw_clipboard_check(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    bx = cx + int(tw * 0.28)
    by = cy - int(th * 0.15)
    bw = int(tw * 0.24)
    bh = int(th * 0.35)

    # Drop shadow
    p.setOpacity(0.25)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(bx + 3, by + 3, bw, bh, 3, 3)
    p.setOpacity(1.0)

    # Board with wood-grain gradient (5 stops)
    board_grad = QLinearGradient(float(bx), 0.0, float(bx + bw), 0.0)
    board_grad.setColorAt(0.00, QColor(0xA0, 0x70, 0x38))
    board_grad.setColorAt(0.25, QColor(0xC8, 0x96, 0x50))
    board_grad.setColorAt(0.50, QColor(0xD8, 0xAA, 0x64))
    board_grad.setColorAt(0.75, QColor(0xC0, 0x8A, 0x48))
    board_grad.setColorAt(1.00, QColor(0x98, 0x68, 0x30))
    p.setPen(QPen(_BROWN, 2))
    p.setBrush(board_grad)
    p.drawRoundedRect(bx, by, bw, bh, 3, 3)

    # Bevel on board
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.drawLine(bx, by, bx + bw, by)
    p.drawLine(bx, by, bx, by + bh)
    p.setPen(QPen(QColor(0, 0, 0, 70), 1))
    p.drawLine(bx, by + bh, bx + bw, by + bh)
    p.drawLine(bx + bw, by, bx + bw, by + bh)

    # Metal clip with QConicalGradient + specular
    clip_w = max(4, bw // 3)
    clip_x = bx + (bw - clip_w) // 2
    clip_cx = clip_x + clip_w // 2
    clip_cy = by - 1
    cg = QConicalGradient(float(clip_cx), float(clip_cy), 0.0)
    cg.setColorAt(0.00, QColor(0xC0, 0xC8, 0xD8))
    cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF))
    cg.setColorAt(0.50, QColor(0x80, 0x88, 0x98))
    cg.setColorAt(0.75, QColor(0xE0, 0xE0, 0xE8))
    cg.setColorAt(1.00, QColor(0xC0, 0xC8, 0xD8))
    p.setPen(QPen(QColor(0x50, 0x50, 0x50), 1))
    p.setBrush(cg)
    p.drawRoundedRect(clip_x, by - 4, clip_w, 8, 2, 2)
    # Specular highlight on clip
    spec = QRadialGradient(float(clip_x + clip_w // 4), float(by - 3), float(clip_w * 0.3))
    spec.setColorAt(0.0, QColor(255, 255, 255, 160))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawRoundedRect(clip_x, by - 4, clip_w, 8, 2, 2)

    # Lines and checkmarks
    line_x = bx + 4
    check_color = QColor(0x00, 0xAA, 0x44)
    for i in range(3):
        ly = by + 10 + i * (bh // 4)
        p.setPen(QPen(QColor(180, 160, 130), 1))
        p.drawLine(line_x + 10, ly + 6, bx + bw - 4, ly + 6)
        if t % 3.0 > (i + 1) * 0.6:
            p.setPen(QPen(check_color, 2))
            p.drawLine(line_x, ly + 4, line_x + 3, ly + 8)
            p.drawLine(line_x + 3, ly + 8, line_x + 8, ly)

    # Environment reflection stripe
    env = QLinearGradient(float(bx), float(by), float(bx + bw * 0.7), float(by + bh * 0.7))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 28))
    env.setColorAt(0.6, QColor(255, 255, 255, 28))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(env)
    p.drawRoundedRect(bx, by, bw, bh, 3, 3)
    p.restore()


def draw_thinking(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t

    bubble_cx = cx + int(tw * 0.25)
    bubble_cy = cy - int(th * 0.30)

    # Shadow under thought cloud
    p.setOpacity(0.20)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 50))
    cw, ch = int(tw * 0.30), int(th * 0.18)
    cloud_x = bubble_cx - cw // 2 + 12
    cloud_y = bubble_cy - ch // 2
    p.drawEllipse(cloud_x + 3, cloud_y + 4, cw, ch)
    p.setOpacity(1.0)

    # Small rising circles with QRadialGradient shading
    for i, (ox, oy, r) in enumerate([(0, 18, 4), (5, 10, 6), (12, 0, 10)]):
        bcx = bubble_cx + ox
        bcy = bubble_cy + oy
        bg = QRadialGradient(float(bcx - r // 3), float(bcy - r // 3), float(r * 1.0))
        bg.setColorAt(0.0, QColor(255, 255, 255, 220))
        bg.setColorAt(0.5, QColor(220, 238, 255, 190))
        bg.setColorAt(1.0, QColor(180, 210, 240, 100))
        p.setPen(QPen(QColor(160, 200, 240), 1))
        p.setBrush(bg)
        p.drawEllipse(bcx - r, bcy - r, r * 2, r * 2)

    # Main oval cloud with gradient
    cloud_grad = QRadialGradient(float(cloud_x + cw // 3), float(cloud_y + ch // 3), float(max(cw, ch) * 0.7))
    cloud_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
    cloud_grad.setColorAt(0.5, QColor(235, 246, 255, 210))
    cloud_grad.setColorAt(1.0, QColor(190, 220, 248, 150))
    p.setBrush(cloud_grad)
    p.setPen(QPen(QColor(160, 200, 240), 1))
    p.drawEllipse(cloud_x, cloud_y, cw, ch)

    # Inner glow
    inner_glow = QRadialGradient(float(cloud_x + cw // 3), float(cloud_y + ch // 3), float(cw * 0.3))
    inner_glow.setColorAt(0.0, QColor(200, 230, 255, 60))
    inner_glow.setColorAt(1.0, QColor(200, 230, 255, 0))
    p.setBrush(inner_glow)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(cloud_x, cloud_y, cw, ch)

    # Content inside cloud
    p.setPen(QPen(QColor(60, 90, 130), 2))
    font = QFont("Arial", max(6, tw // 10), QFont.Weight.Bold)
    p.setFont(font)
    if t > 2.0:
        p.drawText(cloud_x + cw // 2 - 4, cloud_y + ch // 2 + 4, "?")
    else:
        dots = "." * (1 + int(t * 2.5) % 3)
        p.drawText(cloud_x + cw // 4, cloud_y + ch // 2 + 4, dots)
    p.restore()


def draw_chart_analysis(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    chart_x = cx + int(tw * 0.22)
    chart_y = cy - int(th * 0.10)
    chart_w = int(tw * 0.30)
    chart_h = int(th * 0.28)

    # Drop shadow
    p.setOpacity(0.25)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(chart_x + 3, chart_y + 3, chart_w, chart_h)
    p.setOpacity(1.0)

    # Background with subtle gradient
    bg_grad = QLinearGradient(float(chart_x), float(chart_y), float(chart_x), float(chart_y + chart_h))
    bg_grad.setColorAt(0.0, QColor(248, 250, 255))
    bg_grad.setColorAt(0.5, QColor(240, 242, 250))
    bg_grad.setColorAt(1.0, QColor(228, 232, 244))
    p.setPen(QPen(QColor(180, 180, 190), 1))
    p.setBrush(bg_grad)
    p.drawRect(chart_x, chart_y, chart_w, chart_h)

    # Bevel frame
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(chart_x, chart_y, chart_x + chart_w, chart_y)
    p.drawLine(chart_x, chart_y, chart_x, chart_y + chart_h)
    p.setPen(QPen(QColor(0, 0, 0, 60), 1))
    p.drawLine(chart_x, chart_y + chart_h, chart_x + chart_w, chart_y + chart_h)
    p.drawLine(chart_x + chart_w, chart_y, chart_x + chart_w, chart_y + chart_h)

    # Axes
    p.setPen(QPen(QColor(80, 80, 100), 1))
    p.drawLine(chart_x + 4, chart_y + chart_h - 4, chart_x + chart_w - 2, chart_y + chart_h - 4)
    p.drawLine(chart_x + 4, chart_y + 2, chart_x + 4, chart_y + chart_h - 4)

    # Bars with glossy gradient (highlight on top)
    bar_heights = [0.45, 0.70, 0.55, 0.85]
    bar_colors = [
        (0x1A, 0x3A, 0x5C),
        (0x22, 0x4A, 0x70),
        (0x18, 0x38, 0x58),
        (0x20, 0x48, 0x6C),
    ]
    bar_count = len(bar_heights)
    bar_w = max(3, (chart_w - 10) // (bar_count * 2))
    grow = min(1.0, t / 2.0)
    for i, (bh_ratio, (r, g, b)) in enumerate(zip(bar_heights, bar_colors)):
        target_h = int((chart_h - 8) * bh_ratio)
        actual_h = int(target_h * grow)
        if actual_h <= 0:
            continue
        bxi = chart_x + 6 + i * (bar_w + 3)
        byi = chart_y + chart_h - 4 - actual_h
        bar_grad = QLinearGradient(float(bxi), float(byi), float(bxi), float(byi + actual_h))
        bar_grad.setColorAt(0.0, QColor(min(255, r + 60), min(255, g + 60), min(255, b + 80)))
        bar_grad.setColorAt(0.3, QColor(r + 20, g + 20, b + 30))
        bar_grad.setColorAt(1.0, QColor(r, g, b))
        p.setBrush(bar_grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(bxi, byi, bar_w, actual_h)
        # Glossy highlight on top portion
        gloss = QLinearGradient(float(bxi), float(byi), float(bxi + bar_w), float(byi))
        gloss.setColorAt(0.0, QColor(255, 255, 255, 50))
        gloss.setColorAt(0.5, QColor(255, 255, 255, 90))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 20))
        p.setBrush(gloss)
        p.drawRect(bxi, byi, bar_w, max(2, actual_h // 3))
    p.restore()


def draw_glasses_adjust(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t

    eye_y = cy - int(th * 0.26) + int(th * 0.12) + 4
    slide_down = 0
    if t % 4.0 < 0.8:
        slide_down = int((t % 4.0) / 0.8 * 6)

    lens_r = max(4, tw // 9)
    lens_sep = max(6, tw // 6)
    gy = eye_y + slide_down

    # Drop shadow under glasses
    p.setOpacity(0.20)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 50))
    p.drawEllipse(cx - lens_sep - lens_r + 2, gy - lens_r + 3, lens_r * 2, lens_r * 2)
    p.drawEllipse(cx + lens_sep - lens_r + 2, gy - lens_r + 3, lens_r * 2, lens_r * 2)
    p.setOpacity(1.0)

    # Frame (dark acetate gradient)
    p.setPen(QPen(QColor(30, 30, 30), 2))
    for lx in (cx - lens_sep, cx + lens_sep):
        frame_grad = QRadialGradient(float(lx - lens_r // 3), float(gy - lens_r // 3), float(lens_r * 1.2))
        frame_grad.setColorAt(0.0, QColor(60, 60, 65))
        frame_grad.setColorAt(0.7, QColor(35, 35, 40))
        frame_grad.setColorAt(1.0, QColor(20, 20, 25))
        p.setBrush(frame_grad)
        p.drawEllipse(lx - lens_r, gy - lens_r, lens_r * 2, lens_r * 2)

    # Lens glass gradient (convex look)
    for lx in (cx - lens_sep, cx + lens_sep):
        lens_grad = QRadialGradient(float(lx - lens_r // 3), float(gy - lens_r // 3), float(lens_r))
        lens_grad.setColorAt(0.0, QColor(220, 240, 255, 120))
        lens_grad.setColorAt(0.4, QColor(180, 215, 248, 70))
        lens_grad.setColorAt(1.0, QColor(140, 190, 230, 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(lens_grad)
        p.drawEllipse(lx - lens_r + 1, gy - lens_r + 1, lens_r * 2 - 2, lens_r * 2 - 2)
        # Specular highlight
        spec = QRadialGradient(float(lx - lens_r // 2), float(gy - lens_r // 2), float(lens_r * 0.4))
        spec.setColorAt(0.0, QColor(255, 255, 255, 160))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(spec)
        p.drawEllipse(lx - lens_r + 1, gy - lens_r + 1, lens_r, lens_r)

    # Bridge and temples
    p.setPen(QPen(QColor(30, 30, 30), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(cx - lens_sep + lens_r, gy, cx + lens_sep - lens_r, gy)
    p.drawLine(cx - lens_sep - lens_r, gy, cx - lens_sep - lens_r - 6, gy - 2)
    p.drawLine(cx + lens_sep + lens_r, gy, cx + lens_sep + lens_r + 6, gy - 2)
    p.restore()


def draw_coffee_sip(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    mx = cx + int(tw * 0.30)
    my = cy + int(th * 0.10)
    mw = int(tw * 0.20)
    mh = int(th * 0.22)

    # Drop shadow under mug
    p.setOpacity(0.25)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(mx + 3, my + 3, mw, mh, 4, 4)
    p.setOpacity(1.0)

    # Ceramic mug body with radial gradient (white highlight upper-left)
    mug_grad = QRadialGradient(float(mx + mw * 0.25), float(my + mh * 0.20), float(mw * 0.9))
    mug_grad.setColorAt(0.0, QColor(0xFF, 0xFF, 0xFF))
    mug_grad.setColorAt(0.35, QColor(0xF4, 0xF4, 0xF2))
    mug_grad.setColorAt(0.70, QColor(0xE0, 0xDE, 0xDA))
    mug_grad.setColorAt(1.0, QColor(0xC8, 0xC4, 0xBE))
    p.setPen(QPen(_COFFEE, 2))
    p.setBrush(mug_grad)
    p.drawRoundedRect(mx, my, mw, mh, 4, 4)

    # Bevel on mug
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(mx + 1, my + 1, mx + mw - 1, my + 1)
    p.drawLine(mx + 1, my + 1, mx + 1, my + mh - 1)
    p.setPen(QPen(QColor(0, 0, 0, 50), 1))
    p.drawLine(mx + 1, my + mh - 1, mx + mw - 1, my + mh - 1)
    p.drawLine(mx + mw - 1, my + 1, mx + mw - 1, my + mh - 1)

    # Coffee surface with dark gradient + subtle lighter reflection
    coffee_h = int(mh * 0.35)
    coffee_grad = QLinearGradient(float(mx + 2), float(my + 3), float(mx + mw - 2), float(my + 3 + coffee_h))
    coffee_grad.setColorAt(0.0, QColor(0x6A, 0x3C, 0x14))
    coffee_grad.setColorAt(0.30, QColor(0x4A, 0x28, 0x0A))
    coffee_grad.setColorAt(0.70, QColor(0x38, 0x1E, 0x06))
    coffee_grad.setColorAt(1.0, QColor(0x2C, 0x14, 0x02))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(coffee_grad)
    p.drawRoundedRect(mx + 2, my + 3, mw - 4, coffee_h, 2, 2)
    # Surface reflection shimmer
    shimmer_alpha = int(40 + 20 * math.sin(t * 2.0))
    surf_refl = QLinearGradient(float(mx + 2), float(my + 3), float(mx + mw * 0.6), float(my + 3))
    surf_refl.setColorAt(0.0, QColor(255, 220, 160, shimmer_alpha))
    surf_refl.setColorAt(1.0, QColor(255, 220, 160, 0))
    p.setBrush(surf_refl)
    p.drawRoundedRect(mx + 2, my + 3, mw - 4, max(2, coffee_h // 3), 2, 2)

    # Handle with gradient (ceramic look)
    handle_x = mx + mw - 2
    handle_y = my + mh // 4
    handle_w = max(6, mw // 3)
    handle_h = mh // 2
    handle_path = QPainterPath()
    handle_path.moveTo(float(handle_x), float(handle_y))
    handle_path.cubicTo(
        float(handle_x + handle_w + 2), float(handle_y - 2),
        float(handle_x + handle_w + 2), float(handle_y + handle_h + 2),
        float(handle_x), float(handle_y + handle_h)
    )
    handle_path.cubicTo(
        float(handle_x + handle_w - 2), float(handle_y + handle_h),
        float(handle_x + handle_w - 2), float(handle_y),
        float(handle_x), float(handle_y)
    )
    handle_grad = QLinearGradient(float(handle_x), 0.0, float(handle_x + handle_w), 0.0)
    handle_grad.setColorAt(0.0, QColor(0xD8, 0xD4, 0xCE))
    handle_grad.setColorAt(0.4, QColor(0xF0, 0xEE, 0xEA))
    handle_grad.setColorAt(1.0, QColor(0xB0, 0xAC, 0xA6))
    p.setPen(QPen(_COFFEE, 2))
    p.setBrush(handle_grad)
    p.drawPath(handle_path)

    # Animated wavy steam wisps with alpha fade
    for i in range(3):
        base_sx = mx + 4 + i * (mw // 3)
        wisp_alpha_base = int(100 + 80 * math.sin(t * 2.5 + i * 1.1))
        wisp_path = QPainterPath()
        start_y = my - 3
        wisp_path.moveTo(float(base_sx), float(start_y))
        for seg in range(5):
            seg_y = start_y - (seg + 1) * 5
            ox = int(3 * math.sin(t * 3.0 + i * 1.3 + seg * 0.9))
            wisp_path.lineTo(float(base_sx + ox), float(seg_y))
        top_alpha = max(0, wisp_alpha_base - 80)
        steam_pen = QPen(QColor(200, 200, 210, max(0, wisp_alpha_base)), 1)
        steam_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(steam_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(wisp_path)

    # Specular dot on mug upper-left
    spec = QRadialGradient(float(mx + mw * 0.18), float(my + mh * 0.12), float(mw * 0.18))
    spec.setColorAt(0.0, QColor(255, 255, 255, 140))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawRoundedRect(mx, my, mw, mh, 4, 4)
    p.restore()


def draw_typing(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    kx = cx - int(tw * 0.20)
    ky = cy + int(th * 0.25)
    kw = int(tw * 0.40)
    kh = int(th * 0.14)

    # Drop shadow under keyboard
    p.setOpacity(0.25)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(kx + 3, ky + 3, kw, kh, 3, 3)
    p.setOpacity(1.0)

    # Dark plastic body with gradient (lighter top, darker bottom)
    body_grad = QLinearGradient(float(kx), float(ky), float(kx), float(ky + kh))
    body_grad.setColorAt(0.0, QColor(95, 95, 100))
    body_grad.setColorAt(0.3, QColor(72, 72, 78))
    body_grad.setColorAt(1.0, QColor(45, 45, 50))
    p.setPen(QPen(QColor(30, 30, 35), 1))
    p.setBrush(body_grad)
    p.drawRoundedRect(kx, ky, kw, kh, 3, 3)

    # Bevel on keyboard body
    p.setPen(QPen(QColor(255, 255, 255, 50), 1))
    p.drawLine(kx + 1, ky + 1, kx + kw - 1, ky + 1)
    p.drawLine(kx + 1, ky + 1, kx + 1, ky + kh - 1)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(kx + 1, ky + kh - 1, kx + kw - 1, ky + kh - 1)
    p.drawLine(kx + kw - 1, ky + 1, kx + kw - 1, ky + kh - 1)

    # Individual keys with raised look
    cols, rows = 6, 2
    key_w = max(2, (kw - 6) // cols - 1)
    key_h = max(2, (kh - 6) // rows - 1)
    for row in range(rows):
        for col in range(cols):
            kx2 = kx + 3 + col * (key_w + 1)
            ky2 = ky + 3 + row * (key_h + 1)
            # Key base gradient (lighter top, darker bottom)
            key_grad = QLinearGradient(float(kx2), float(ky2), float(kx2), float(ky2 + key_h))
            key_grad.setColorAt(0.0, QColor(175, 175, 182))
            key_grad.setColorAt(0.5, QColor(155, 155, 162))
            key_grad.setColorAt(1.0, QColor(120, 120, 126))
            p.setBrush(key_grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(kx2, ky2, key_w, key_h, 1, 1)
            # Top highlight edge (lighter)
            p.setPen(QPen(QColor(210, 210, 218, 160), 1))
            p.drawLine(kx2, ky2, kx2 + key_w - 1, ky2)
            p.drawLine(kx2, ky2, kx2, ky2 + key_h - 1)
            # Bottom/right edge (darker)
            p.setPen(QPen(QColor(80, 80, 88, 180), 1))
            p.drawLine(kx2, ky2 + key_h - 1, kx2 + key_w - 1, ky2 + key_h - 1)
            p.drawLine(kx2 + key_w - 1, ky2, kx2 + key_w - 1, ky2 + key_h - 1)
            # Specular dot upper-left
            spec = QRadialGradient(float(kx2 + 1), float(ky2 + 1), float(max(1, key_w // 3)))
            spec.setColorAt(0.0, QColor(255, 255, 255, 80))
            spec.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(spec)
            p.drawRoundedRect(kx2, ky2, key_w, key_h, 1, 1)

    # Animated fingers with skin-tone gradient
    for fi in range(3):
        fx = kx + 4 + int((math.sin(t * 8.0 + fi * 1.5) * 0.5 + 0.5) * (kw - 8))
        fy = ky - 5
        pressed = math.sin(t * 8.0 + fi * 1.5) > 0.6
        finger_grad = QLinearGradient(float(fx - 3), float(fy), float(fx + 3), float(fy + 8))
        finger_grad.setColorAt(0.0, QColor(240, 210, 180))
        finger_grad.setColorAt(0.5, QColor(220, 185, 155))
        finger_grad.setColorAt(1.0, QColor(190, 155, 125))
        p.setBrush(finger_grad)
        p.setPen(QPen(QColor(170, 130, 100), 1))
        p.drawRoundedRect(fx - 3, fy + (2 if pressed else 0), 6, 7, 2, 2)
        # Nail highlight
        nail_spec = QRadialGradient(float(fx - 1), float(fy + 1), 2.0)
        nail_spec.setColorAt(0.0, QColor(255, 240, 220, 100))
        nail_spec.setColorAt(1.0, QColor(255, 240, 220, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(nail_spec)
        p.drawRoundedRect(fx - 3, fy, 6, 4, 1, 1)
    p.restore()


def draw_eureka_moment(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    cycle = t % 5.0
    glowing = cycle < 2.5

    bx = cx - int(tw * 0.08)
    by = cy - int(th * 0.50)
    br = max(6, int(tw * 0.10))

    # Outer glow aura with radial gradient
    if glowing:
        glow_alpha = int(80 + 60 * math.sin(t * 4.0))
        aura = QRadialGradient(float(bx), float(by), float(br * 3.0))
        aura.setColorAt(0.0, QColor(255, 255, 80, glow_alpha))
        aura.setColorAt(0.4, QColor(255, 220, 0, glow_alpha // 2))
        aura.setColorAt(1.0, QColor(255, 200, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(aura)
        p.drawEllipse(bx - br * 3, by - br * 3, br * 6, br * 6)

    # Glass bulb — radial gradient with bright inner and semi-transparent glass look
    if glowing:
        bulb_grad = QRadialGradient(float(bx - br * 0.3), float(by - br * 0.3), float(br * 1.2))
        bulb_grad.setColorAt(0.0, QColor(255, 255, 200, 240))
        bulb_grad.setColorAt(0.4, QColor(255, 240, 120, 220))
        bulb_grad.setColorAt(0.8, QColor(240, 200, 60, 180))
        bulb_grad.setColorAt(1.0, QColor(200, 160, 20, 140))
    else:
        bulb_grad = QRadialGradient(float(bx - br * 0.3), float(by - br * 0.3), float(br * 1.2))
        bulb_grad.setColorAt(0.0, QColor(220, 220, 228))
        bulb_grad.setColorAt(0.5, QColor(185, 185, 195))
        bulb_grad.setColorAt(1.0, QColor(150, 150, 162))
    p.setPen(QPen(QColor(80, 80, 80), 1))
    p.setBrush(bulb_grad)
    p.drawEllipse(bx - br, by - br, br * 2, br * 2)

    # Glass sheen — crescent highlight upper-left
    sheen = QRadialGradient(float(bx - br * 0.4), float(by - br * 0.4), float(br * 0.55))
    sheen.setColorAt(0.0, QColor(255, 255, 255, 160 if glowing else 80))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(sheen)
    p.drawEllipse(bx - br, by - br, br * 2, br * 2)

    # Metallic base/socket with conical gradient
    socket_w = br
    socket_h = max(3, br // 2)
    socket_x = bx - socket_w // 2
    socket_y = by + br - 2
    cg = QConicalGradient(float(bx), float(socket_y + socket_h // 2), 0.0)
    cg.setColorAt(0.00, QColor(0xB0, 0xB8, 0xC8))
    cg.setColorAt(0.25, QColor(0xF0, 0xF4, 0xFF))
    cg.setColorAt(0.50, QColor(0x78, 0x80, 0x90))
    cg.setColorAt(0.75, QColor(0xD0, 0xD4, 0xE0))
    cg.setColorAt(1.00, QColor(0xB0, 0xB8, 0xC8))
    p.setPen(QPen(QColor(70, 70, 80), 1))
    p.setBrush(cg)
    p.drawRect(socket_x, socket_y, socket_w, socket_h)
    # Socket contact lines
    p.setPen(QPen(QColor(90, 90, 100), 1))
    for li in range(2):
        lx = socket_x + socket_w // 3 * (li + 1)
        p.drawLine(lx, socket_y, lx, socket_y + socket_h)

    # Rays with varying width and alpha fade
    if glowing:
        for i in range(8):
            angle = i * math.pi / 4 + math.sin(t * 0.8) * 0.1
            ray_alpha = int(180 - 60 * ((i % 3) / 2.0))
            ray_w = 2 if i % 2 == 0 else 1
            r0 = br + 3
            r1 = br + 7 + (i % 3) * 2
            pen = QPen(QColor(255, 220, 0, ray_alpha), ray_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(
                bx + int(math.cos(angle) * r0),
                by + int(math.sin(angle) * r0),
                bx + int(math.cos(angle) * r1),
                by + int(math.sin(angle) * r1),
            )
    p.restore()


def draw_filing(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    folder_data = [
        (QColor(0xD2, 0xB4, 0x8C), QColor(0xA0, 0x78, 0x40), QColor(0xF0, 0xD4, 0xA0)),
        (QColor(0x8B, 0x5E, 0x3C), QColor(0x5A, 0x34, 0x14), QColor(0xAA, 0x7A, 0x52)),
        (QColor(0xF5, 0xD8, 0xA8), QColor(0xC8, 0xA0, 0x68), QColor(0xFF, 0xF0, 0xC8)),
    ]
    fx_base = cx + int(tw * 0.15)
    fy = cy - int(th * 0.05)
    fw = int(tw * 0.14)
    fh = int(th * 0.22)
    offsets = [int(math.sin(t * 1.2 + i * 1.2) * 6) for i in range(3)]

    for i, ((fc_mid, fc_dark, fc_light), x_off) in enumerate(zip(folder_data, offsets)):
        fx = fx_base + i * (fw + 2) + x_off

        # Drop shadow
        p.setOpacity(0.20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRoundedRect(fx + 2, fy + 2, fw, fh, 2, 2)
        p.setOpacity(1.0)

        # Tab (lighter at top) with metallic clip hint
        tab_w = fw // 2
        tab_grad = QLinearGradient(float(fx), float(fy - 5), float(fx), float(fy))
        tab_grad.setColorAt(0.0, fc_light)
        tab_grad.setColorAt(1.0, fc_mid)
        p.setBrush(tab_grad)
        p.setPen(QPen(QColor(80, 50, 20), 1))
        p.drawRoundedRect(fx, fy - 5, tab_w, 6, 2, 2)
        # Small metallic clip on tab
        clip_cg = QConicalGradient(float(fx + tab_w // 2), float(fy - 3), 0.0)
        clip_cg.setColorAt(0.0, QColor(0xD0, 0xD4, 0xE0))
        clip_cg.setColorAt(0.5, QColor(0xFF, 0xFF, 0xFF))
        clip_cg.setColorAt(1.0, QColor(0xA0, 0xA4, 0xB0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(clip_cg)
        p.drawRect(fx + tab_w // 4, fy - 4, tab_w // 2, 3)

        # Folder body with depth gradient
        body_grad = QLinearGradient(float(fx), float(fy), float(fx), float(fy + fh))
        body_grad.setColorAt(0.0, fc_light)
        body_grad.setColorAt(0.15, fc_mid)
        body_grad.setColorAt(0.85, fc_mid)
        body_grad.setColorAt(1.0, fc_dark)
        p.setPen(QPen(QColor(80, 50, 20), 1))
        p.setBrush(body_grad)
        p.drawRect(fx, fy, fw, fh)

        # Paper edge visible at top (white paper peeking)
        paper_grad = QLinearGradient(float(fx + 2), float(fy + 2), float(fx + fw - 2), float(fy + 2))
        paper_grad.setColorAt(0.0, QColor(240, 238, 230))
        paper_grad.setColorAt(0.5, QColor(255, 253, 245))
        paper_grad.setColorAt(1.0, QColor(235, 232, 224))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(paper_grad)
        p.drawRect(fx + 2, fy + 2, fw - 4, max(3, fh // 8))

        # Bevel on folder body
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawLine(fx, fy, fx + fw, fy)
        p.drawLine(fx, fy, fx, fy + fh)
        p.setPen(QPen(QColor(0, 0, 0, 50), 1))
        p.drawLine(fx, fy + fh, fx + fw, fy + fh)
        p.drawLine(fx + fw, fy, fx + fw, fy + fh)
    p.restore()


def draw_stamp_approve(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    cycle = t % 4.0
    stamp_x = cx + int(tw * 0.18)
    paper_y = cy + int(th * 0.15)
    sw = int(tw * 0.14)
    sh = int(th * 0.22)

    # Paper with subtle texture gradient
    paper_w = int(tw * 0.26)
    paper_h = int(th * 0.16)
    paper_grad = QLinearGradient(float(stamp_x - 4), float(paper_y), float(stamp_x - 4 + paper_w), float(paper_y + paper_h))
    paper_grad.setColorAt(0.0, QColor(252, 250, 242))
    paper_grad.setColorAt(0.4, QColor(248, 246, 236))
    paper_grad.setColorAt(1.0, QColor(238, 235, 222))
    p.setPen(QPen(QColor(180, 175, 160), 1))
    p.setBrush(paper_grad)
    p.drawRect(stamp_x - 4, paper_y, paper_w, paper_h)
    # Paper bevel
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.drawLine(stamp_x - 4, paper_y, stamp_x - 4 + paper_w, paper_y)
    p.drawLine(stamp_x - 4, paper_y, stamp_x - 4, paper_y + paper_h)
    p.setPen(QPen(QColor(0, 0, 0, 40), 1))
    p.drawLine(stamp_x - 4, paper_y + paper_h, stamp_x - 4 + paper_w, paper_y + paper_h)
    p.drawLine(stamp_x - 4 + paper_w, paper_y, stamp_x - 4 + paper_w, paper_y + paper_h)

    # Stamp handle (cylindrical metallic gradient)
    stamp_drop = min(1.0, cycle / 0.5) if cycle < 0.5 else max(0.0, 1.0 - (cycle - 0.5) / 0.3)
    sy = cy - int(th * 0.10) + int(stamp_drop * int(th * 0.20))
    handle_grad = QLinearGradient(float(stamp_x), 0.0, float(stamp_x + sw), 0.0)
    handle_grad.setColorAt(0.00, QColor(0x60, 0x00, 0x00))
    handle_grad.setColorAt(0.20, QColor(0xA0, 0x20, 0x20))
    handle_grad.setColorAt(0.45, QColor(0xCC, 0x40, 0x40))
    handle_grad.setColorAt(0.65, QColor(0x9B, 0x10, 0x10))
    handle_grad.setColorAt(1.00, QColor(0x50, 0x00, 0x00))
    p.setPen(QPen(QColor(60, 0, 0), 1))
    p.setBrush(handle_grad)
    p.drawRoundedRect(stamp_x, sy, sw, sh, 3, 3)

    # Handle specular highlight
    h_spec = QRadialGradient(float(stamp_x + sw * 0.2), float(sy + sh * 0.15), float(sw * 0.35))
    h_spec.setColorAt(0.0, QColor(255, 180, 180, 100))
    h_spec.setColorAt(1.0, QColor(255, 180, 180, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(h_spec)
    p.drawRoundedRect(stamp_x, sy, sw, sh, 3, 3)

    # Rubber face with gradient at bottom of stamp
    face_h = max(5, sh // 5)
    face_grad = QLinearGradient(float(stamp_x), float(sy + sh - face_h), float(stamp_x + sw), float(sy + sh))
    face_grad.setColorAt(0.0, QColor(0x40, 0xCC, 0x60))
    face_grad.setColorAt(0.4, QColor(0x20, 0xAA, 0x44))
    face_grad.setColorAt(1.0, QColor(0x10, 0x80, 0x30))
    p.setPen(QPen(QColor(0, 80, 20), 1))
    p.setBrush(face_grad)
    p.drawRect(stamp_x, sy + sh - face_h, sw, face_h)

    # "OK" text on paper after landing
    if cycle > 0.5:
        alpha = min(255, int((cycle - 0.5) / 0.3 * 255))
        # Ink glow under text
        glow = QRadialGradient(float(stamp_x + sw // 2), float(paper_y + int(th * 0.08)), float(sw * 0.7))
        glow.setColorAt(0.0, QColor(0, 180, 60, min(80, alpha // 2)))
        glow.setColorAt(1.0, QColor(0, 180, 60, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(stamp_x - 4, paper_y + 2, sw + 8, int(th * 0.12))
        p.setPen(QColor(0x00, 0x88, 0x33, alpha))
        font = QFont("Arial", max(5, tw // 12), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(stamp_x + 2, paper_y + int(th * 0.12), "OK ✓")
    p.restore()


def draw_calculator(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    calc_x = cx + int(tw * 0.24)
    calc_y = cy - int(th * 0.08)
    cw = int(tw * 0.26)
    ch = int(th * 0.36)

    # Drop shadow
    p.setOpacity(0.25)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(calc_x + 3, calc_y + 3, cw, ch, 4, 4)
    p.setOpacity(1.0)

    # Plastic body with gradient (slightly lighter top-left corner)
    body_grad = QLinearGradient(float(calc_x), float(calc_y), float(calc_x + cw), float(calc_y + ch))
    body_grad.setColorAt(0.0, QColor(82, 82, 88))
    body_grad.setColorAt(0.25, QColor(68, 68, 74))
    body_grad.setColorAt(0.75, QColor(50, 50, 56))
    body_grad.setColorAt(1.0, QColor(38, 38, 44))
    p.setPen(QPen(QColor(25, 25, 30), 1))
    p.setBrush(body_grad)
    p.drawRoundedRect(calc_x, calc_y, cw, ch, 4, 4)

    # Bevel on body
    p.setPen(QPen(QColor(255, 255, 255, 50), 1))
    p.drawLine(calc_x + 1, calc_y + 1, calc_x + cw - 1, calc_y + 1)
    p.drawLine(calc_x + 1, calc_y + 1, calc_x + 1, calc_y + ch - 1)
    p.setPen(QPen(QColor(0, 0, 0, 80), 1))
    p.drawLine(calc_x + 1, calc_y + ch - 1, calc_x + cw - 1, calc_y + ch - 1)
    p.drawLine(calc_x + cw - 1, calc_y + 1, calc_x + cw - 1, calc_y + ch - 1)

    # Display screen with green glow gradient
    disp_h = int(ch * 0.22)
    disp_grad = QLinearGradient(float(calc_x + 3), float(calc_y + 3), float(calc_x + 3), float(calc_y + 3 + disp_h))
    disp_grad.setColorAt(0.0, QColor(60, 100, 60))
    disp_grad.setColorAt(0.4, QColor(40, 85, 45))
    disp_grad.setColorAt(1.0, QColor(25, 60, 30))
    p.setPen(QPen(QColor(20, 50, 25), 1))
    p.setBrush(disp_grad)
    p.drawRoundedRect(calc_x + 3, calc_y + 3, cw - 6, disp_h, 2, 2)
    # Green glow overlay
    disp_glow = QRadialGradient(float(calc_x + cw * 0.5), float(calc_y + 3 + disp_h * 0.4), float(cw * 0.4))
    disp_glow.setColorAt(0.0, QColor(80, 255, 100, 40))
    disp_glow.setColorAt(1.0, QColor(80, 255, 100, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(disp_glow)
    p.drawRoundedRect(calc_x + 3, calc_y + 3, cw - 6, disp_h, 2, 2)
    p.setPen(QColor(100, 255, 100))
    font = QFont("Courier", max(5, tw // 14), QFont.Weight.Bold)
    p.setFont(font)
    num = str(42 + int(t * 2) % 58)
    if int(t * 2) % 4 == 0:
        num = "   "
    p.drawText(calc_x + 4, calc_y + disp_h, num)

    # Buttons grid with raised look
    cols, rows = 3, 4
    btn_w = max(2, (cw - 8) // cols - 1)
    btn_h = max(2, (ch - disp_h - 12) // rows - 1)
    for row in range(rows):
        for col in range(cols):
            bx = calc_x + 4 + col * (btn_w + 1)
            by = calc_y + disp_h + 6 + row * (btn_h + 1)
            btn_grad = QLinearGradient(float(bx), float(by), float(bx), float(by + btn_h))
            btn_grad.setColorAt(0.0, QColor(148, 148, 156))
            btn_grad.setColorAt(0.5, QColor(132, 132, 138))
            btn_grad.setColorAt(1.0, QColor(105, 105, 112))
            p.setBrush(btn_grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bx, by, btn_w, btn_h, 1, 1)
            # Top highlight edge
            p.setPen(QPen(QColor(200, 200, 208, 150), 1))
            p.drawLine(bx, by, bx + btn_w - 1, by)
            p.drawLine(bx, by, bx, by + btn_h - 1)
            # Bottom/right edge darker
            p.setPen(QPen(QColor(70, 70, 78, 180), 1))
            p.drawLine(bx, by + btn_h - 1, bx + btn_w - 1, by + btn_h - 1)
            p.drawLine(bx + btn_w - 1, by, bx + btn_w - 1, by + btn_h - 1)
            # Specular corner dot
            b_spec = QRadialGradient(float(bx + 1), float(by + 1), float(max(1, btn_w // 3)))
            b_spec.setColorAt(0.0, QColor(255, 255, 255, 60))
            b_spec.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(b_spec)
            p.drawRoundedRect(bx, by, btn_w, btn_h, 1, 1)

    # Glossy body reflection stripe (diagonal)
    env = QLinearGradient(float(calc_x), float(calc_y), float(calc_x + cw * 0.6), float(calc_y + ch * 0.6))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.3, QColor(255, 255, 255, 22))
    env.setColorAt(0.6, QColor(255, 255, 255, 22))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(env)
    p.drawRoundedRect(calc_x, calc_y, cw, ch, 4, 4)
    p.restore()


def draw_magnifying_glass(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    # cx already incorporates passive_extra_x — no additional offset needed
    mx = cx
    my = cy - int(th * 0.15)
    lr = max(7, int(tw * 0.12))

    # Drop shadow under lens
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawEllipse(mx - lr + 3, my - lr + 3, lr * 2, lr * 2)
    p.setOpacity(1.0)

    # Metal frame ring with conical gradient
    ring_cg = QConicalGradient(float(mx), float(my), 45.0)
    ring_cg.setColorAt(0.00, QColor(0xA0, 0xAC, 0xC0))
    ring_cg.setColorAt(0.20, QColor(0xE0, 0xEC, 0xFF))
    ring_cg.setColorAt(0.40, QColor(0xC8, 0xD4, 0xE8))
    ring_cg.setColorAt(0.60, QColor(0x70, 0x7C, 0x90))
    ring_cg.setColorAt(0.80, QColor(0xB8, 0xC4, 0xD8))
    ring_cg.setColorAt(1.00, QColor(0xA0, 0xAC, 0xC0))
    p.setPen(QPen(QColor(60, 70, 90), 3))
    p.setBrush(ring_cg)
    p.drawEllipse(mx - lr, my - lr, lr * 2, lr * 2)

    # Glass lens with radial gradient (blue-white center with transparency)
    lens_grad = QRadialGradient(float(mx - lr * 0.25), float(my - lr * 0.25), float(lr * 1.0))
    lens_grad.setColorAt(0.0, QColor(220, 240, 255, 100))
    lens_grad.setColorAt(0.4, QColor(180, 215, 248, 75))
    lens_grad.setColorAt(0.8, QColor(140, 190, 238, 50))
    lens_grad.setColorAt(1.0, QColor(100, 160, 220, 30))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(lens_grad)
    p.drawEllipse(mx - lr + 2, my - lr + 2, lr * 2 - 4, lr * 2 - 4)

    # Internal reflection arc (white crescent upper-left)
    crescent_path = QPainterPath()
    crescent_path.moveTo(float(mx - lr * 0.55), float(my - lr * 0.25))
    crescent_path.arcTo(
        float(mx - lr * 0.70), float(my - lr * 0.70),
        float(lr * 1.0), float(lr * 1.0),
        140.0, -80.0
    )
    crescent_pen = QPen(QColor(255, 255, 255, 120), 2)
    crescent_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(crescent_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(crescent_path)

    # Specular highlight dot
    spec = QRadialGradient(float(mx - lr * 0.40), float(my - lr * 0.40), float(lr * 0.30))
    spec.setColorAt(0.0, QColor(255, 255, 255, 160))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawEllipse(mx - lr + 2, my - lr + 2, lr * 2 - 4, lr * 2 - 4)

    # Handle with wood/metal gradient
    hx0 = mx + int(lr * 0.7)
    hy0 = my + int(lr * 0.7)
    hx1 = mx + lr + 8
    hy1 = my + lr + 8
    handle_grad = QLinearGradient(float(hx0), float(hy0), float(hx1), float(hy1))
    handle_grad.setColorAt(0.0, QColor(0xA0, 0x78, 0x40))
    handle_grad.setColorAt(0.35, QColor(0xC8, 0xA0, 0x60))
    handle_grad.setColorAt(0.65, QColor(0x90, 0x68, 0x30))
    handle_grad.setColorAt(1.0, QColor(0x68, 0x48, 0x18))
    handle_pen = QPen(handle_grad, 4)
    handle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(handle_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(hx0, hy0, hx1, hy1)
    p.restore()


def draw_presentation(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    board_x = cx + int(tw * 0.22)
    board_y = cy - int(th * 0.25)
    board_w = int(tw * 0.28)
    board_h = int(th * 0.28)

    # Drop shadow under board
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(board_x + 3, board_y + 3, board_w, board_h)
    p.setOpacity(1.0)

    # Easel legs with wood gradient
    for lx_frac, lx_end_frac in ((1 / 3, 1 / 4), (2 / 3, 3 / 4)):
        lx0 = board_x + int(board_w * lx_frac)
        lx1 = board_x + int(board_w * lx_end_frac)
        ly0 = board_y + board_h
        ly1 = board_y + board_h + 10
        leg_grad = QLinearGradient(float(lx0), float(ly0), float(lx1), float(ly1))
        leg_grad.setColorAt(0.0, QColor(0xA8, 0x80, 0x50))
        leg_grad.setColorAt(0.5, QColor(0xC8, 0xA0, 0x68))
        leg_grad.setColorAt(1.0, QColor(0x80, 0x58, 0x28))
        leg_pen = QPen(leg_grad, 2)
        p.setPen(leg_pen)
        p.drawLine(lx0, ly0, lx1, ly1)

    # Whiteboard with subtle gradient (ivory white, slight blue tint)
    board_grad = QLinearGradient(float(board_x), float(board_y), float(board_x + board_w), float(board_y + board_h))
    board_grad.setColorAt(0.0, QColor(255, 255, 252))
    board_grad.setColorAt(0.3, QColor(252, 253, 255))
    board_grad.setColorAt(0.7, QColor(246, 248, 254))
    board_grad.setColorAt(1.0, QColor(238, 240, 248))
    p.setPen(QPen(QColor(60, 80, 100), 2))
    p.setBrush(board_grad)
    p.drawRect(board_x, board_y, board_w, board_h)

    # Neat border with bevel
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(board_x, board_y, board_x + board_w, board_y)
    p.drawLine(board_x, board_y, board_x, board_y + board_h)
    p.setPen(QPen(QColor(0, 0, 0, 50), 1))
    p.drawLine(board_x, board_y + board_h, board_x + board_w, board_y + board_h)
    p.drawLine(board_x + board_w, board_y, board_x + board_w, board_y + board_h)

    # Gradient chart bars on board
    bar_data = [(0.5, 0x1A, 0x3A, 0x5C), (0.8, 0x22, 0x4A, 0x70), (0.6, 0x18, 0x38, 0x58)]
    for i, (bh_ratio, r, g, b) in enumerate(bar_data):
        bh_px = int(board_h * 0.5 * bh_ratio)
        bw_px = max(3, board_w // 6)
        bxi = board_x + 4 + i * (bw_px + 3)
        byi = board_y + board_h - 6 - bh_px
        bar_grad = QLinearGradient(float(bxi), float(byi), float(bxi), float(byi + bh_px))
        bar_grad.setColorAt(0.0, QColor(min(255, r + 70), min(255, g + 70), min(255, b + 90)))
        bar_grad.setColorAt(0.4, QColor(r + 20, g + 20, b + 30))
        bar_grad.setColorAt(1.0, QColor(r, g, b))
        p.setBrush(bar_grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(bxi, byi, bw_px, bh_px)
        # Bar gloss
        gloss = QLinearGradient(float(bxi), float(byi), float(bxi + bw_px), float(byi))
        gloss.setColorAt(0.0, QColor(255, 255, 255, 60))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 10))
        p.setBrush(gloss)
        p.drawRect(bxi, byi, bw_px, max(2, bh_px // 3))

    # Bullet lines at top of board
    p.setPen(QPen(QColor(120, 130, 160, 160), 1))
    for i in range(3):
        ly = board_y + 4 + i * 5
        p.drawLine(board_x + 3, ly, board_x + board_w - 3, ly)
    p.restore()


def draw_sticky_notes(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    note_data = [
        (cx - int(tw * 0.35), cy - int(th * 0.20), QColor(0xFF, 0xF0, 0x80, 220), QColor(0xFF, 0xD8, 0x40, 220)),
        (cx + int(tw * 0.30), cy - int(th * 0.30), QColor(0xFF, 0xA0, 0xA0, 220), QColor(0xFF, 0x70, 0x70, 220)),
        (cx - int(tw * 0.25), cy + int(th * 0.15), QColor(0xA0, 0xFF, 0xA0, 220), QColor(0x60, 0xE0, 0x60, 220)),
        (cx + int(tw * 0.22), cy + int(th * 0.20), QColor(0xA0, 0xD0, 0xFF, 220), QColor(0x60, 0xA8, 0xFF, 220)),
    ]
    ns = max(8, tw // 6)
    for i, (nx, ny, nc_light, nc_dark) in enumerate(note_data):
        rot = math.sin(t * 2.0 + i * 1.2) * 5.0
        p.save()
        p.translate(nx, ny)
        p.rotate(rot)

        # Drop shadow (offset dark ellipse)
        p.setOpacity(0.20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRect(-ns // 2 + 2, -ns // 2 + 3, ns, ns)
        p.setOpacity(1.0)

        # Note body with gradient (lighter top to main color bottom)
        note_grad = QLinearGradient(0.0, float(-ns // 2), 0.0, float(ns // 2))
        note_grad.setColorAt(0.0, nc_light)
        note_grad.setColorAt(0.5, QColor(nc_light.red(), nc_light.green(), nc_light.blue(), 210))
        note_grad.setColorAt(1.0, nc_dark)
        p.setPen(QPen(QColor(nc_dark.red() - 20, nc_dark.green() - 20, max(0, nc_dark.blue() - 20), 180), 1))
        p.setBrush(note_grad)
        p.drawRect(-ns // 2, -ns // 2, ns, ns)

        # Folded bottom-right corner (small triangle)
        fold_size = max(3, ns // 5)
        fold = QPainterPath()
        fold.moveTo(float(ns // 2 - fold_size), float(ns // 2))
        fold.lineTo(float(ns // 2), float(ns // 2 - fold_size))
        fold.lineTo(float(ns // 2), float(ns // 2))
        fold.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(nc_dark.red() - 30, nc_dark.green() - 30, max(0, nc_dark.blue() - 30), 180))
        p.fillPath(fold, p.brush())
        p.setPen(QPen(QColor(nc_dark.red() - 40, nc_dark.green() - 40, max(0, nc_dark.blue() - 40), 140), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(fold)

        # Faint ruled lines inside
        p.setPen(QPen(QColor(nc_dark.red() - 10, nc_dark.green() - 10, nc_dark.blue(), 80), 1))
        for li in range(3):
            ly = -ns // 2 + ns // 5 + li * (ns // 4)
            p.drawLine(-ns // 2 + 2, ly, ns // 2 - fold_size - 1 if li == 2 else ns // 2 - 2, ly)

        # Top adhesive strip (slightly darker)
        strip_grad = QLinearGradient(0.0, float(-ns // 2), 0.0, float(-ns // 2 + ns // 5))
        strip_grad.setColorAt(0.0, nc_dark)
        strip_grad.setColorAt(1.0, nc_light)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(strip_grad)
        p.drawRect(-ns // 2, -ns // 2, ns, ns // 5)

        p.restore()
    p.restore()


def draw_paper_airplane(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    cycle = t % 3.5
    progress = cycle / 3.0
    # Arc: start left, arc to right
    ax = int((cx - tw * 0.5) + progress * (tw * 1.0))
    ay = cy - int(th * 0.25) - int(math.sin(progress * math.pi) * th * 0.18)

    # Trail (dotted)
    p.setPen(QPen(QColor(160, 180, 200, 80), 1, Qt.PenStyle.DotLine))
    start_x = int(cx - tw * 0.5)
    step = max(1, int(tw * 1.0 * progress) // 8)
    for i in range(0, int(tw * 1.0 * progress), step):
        trail_x = start_x + i
        trail_y = cy - int(th * 0.25) - int(math.sin((i / (tw * 1.0)) * math.pi) * th * 0.18)
        p.drawPoint(trail_x, trail_y)

    # Subtle shadow underneath airplane
    p.setOpacity(0.18)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 50))
    shadow_path = QPainterPath()
    shadow_path.moveTo(float(ax + 11), float(ay + 2))
    shadow_path.lineTo(float(ax - 3), float(ay - 3))
    shadow_path.lineTo(float(ax - 3), float(ay + 7))
    shadow_path.closeSubpath()
    p.fillPath(shadow_path, QColor(0, 0, 0, 50))
    p.setOpacity(1.0)

    # Folded paper look — upper wing slightly lighter
    upper_wing = QPainterPath()
    upper_wing.moveTo(float(ax + 10), float(ay))
    upper_wing.lineTo(float(ax - 4), float(ay - 5))
    upper_wing.lineTo(float(ax), float(ay))
    upper_wing.closeSubpath()
    upper_grad = QLinearGradient(float(ax - 4), float(ay - 5), float(ax + 10), float(ay + 5))
    upper_grad.setColorAt(0.0, QColor(245, 248, 255))
    upper_grad.setColorAt(0.5, QColor(235, 240, 252))
    upper_grad.setColorAt(1.0, QColor(210, 220, 240))
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(upper_wing, upper_grad)

    # Lower wing (slightly darker)
    lower_wing = QPainterPath()
    lower_wing.moveTo(float(ax + 10), float(ay))
    lower_wing.lineTo(float(ax), float(ay))
    lower_wing.lineTo(float(ax - 4), float(ay + 5))
    lower_wing.closeSubpath()
    lower_grad = QLinearGradient(float(ax - 4), float(ay), float(ax + 10), float(ay + 5))
    lower_grad.setColorAt(0.0, QColor(210, 218, 238))
    lower_grad.setColorAt(1.0, QColor(190, 200, 225))
    p.fillPath(lower_wing, lower_grad)

    # Fold line (centre crease)
    fold_pen = QPen(QColor(160, 175, 210, 180), 1)
    fold_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(fold_pen)
    p.drawLine(ax - 4, ay, ax + 10, ay)

    # Outline
    full_plane = QPainterPath()
    full_plane.moveTo(float(ax + 10), float(ay))
    full_plane.lineTo(float(ax - 4), float(ay - 5))
    full_plane.lineTo(float(ax - 4), float(ay + 5))
    full_plane.closeSubpath()
    p.setPen(QPen(QColor(100, 120, 180), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(full_plane)
    p.restore()


def draw_pencil_tap(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    # cy already incorporates passive_extra_y (tap bounce) — no double-offset
    px = cx + int(tw * 0.28)
    py = cy - int(th * 0.10)
    pw = max(4, tw // 10)
    ph = int(th * 0.30)

    p.save()
    p.translate(px, py)
    p.rotate(-20)

    # Drop shadow behind pencil
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(-pw // 2 + 2, -ph // 2 + 2, pw, ph - 6, 2, 2)
    p.setOpacity(1.0)

    # Pencil body — cylindrical gradient (yellow-orange-yellow for roundness)
    body_grad = QLinearGradient(float(-pw // 2), 0.0, float(pw // 2), 0.0)
    body_grad.setColorAt(0.00, QColor(0xD4, 0xA0, 0x00))
    body_grad.setColorAt(0.20, QColor(0xFF, 0xE0, 0x40))
    body_grad.setColorAt(0.45, QColor(0xFF, 0xF0, 0x80))
    body_grad.setColorAt(0.65, QColor(0xFF, 0xD7, 0x00))
    body_grad.setColorAt(1.00, QColor(0xB8, 0x88, 0x00))
    p.setPen(QPen(QColor(80, 60, 20), 1))
    p.setBrush(body_grad)
    p.drawRect(-pw // 2, -ph // 2, pw, ph - 6)

    # Grain stripes
    p.setPen(QPen(QColor(180, 140, 10, 60), 1))
    for gi in range(2):
        gx = -pw // 2 + pw // 3 * (gi + 1)
        p.drawLine(gx, -ph // 2, gx, ph // 2 - 6)

    # Eraser band — metallic ferrule (conical gradient)
    ferrule_h = max(3, ph // 12)
    ferrule_y = -ph // 2 - ferrule_h
    fcx = 0.0
    fcy = float(ferrule_y + ferrule_h // 2)
    cg = QConicalGradient(fcx, fcy, 0.0)
    cg.setColorAt(0.00, QColor(0xC0, 0xC8, 0xD8))
    cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF))
    cg.setColorAt(0.50, QColor(0x80, 0x88, 0x98))
    cg.setColorAt(0.75, QColor(0xE0, 0xE0, 0xE8))
    cg.setColorAt(1.00, QColor(0xC0, 0xC8, 0xD8))
    p.setPen(QPen(QColor(90, 90, 100), 1))
    p.setBrush(cg)
    p.drawRect(-pw // 2, ferrule_y, pw, ferrule_h)

    # Pink eraser
    eraser_h = max(3, ph // 10)
    eraser_y = ferrule_y - eraser_h
    eraser_grad = QLinearGradient(float(-pw // 2), 0.0, float(pw // 2), 0.0)
    eraser_grad.setColorAt(0.0, QColor(0xE0, 0x80, 0x90))
    eraser_grad.setColorAt(0.4, QColor(0xF8, 0xC0, 0xC8))
    eraser_grad.setColorAt(1.0, QColor(0xC0, 0x60, 0x78))
    p.setPen(QPen(QColor(180, 80, 100), 1))
    p.setBrush(eraser_grad)
    p.drawRoundedRect(-pw // 2, eraser_y, pw, eraser_h, 1, 1)

    # Wood-colored tip with gradient
    tip_h = max(4, ph // 8)
    tip_y = ph // 2 - 6
    tip_grad = QLinearGradient(float(-pw // 2), 0.0, float(pw // 2), 0.0)
    tip_grad.setColorAt(0.0, QColor(0xA0, 0x70, 0x30))
    tip_grad.setColorAt(0.4, QColor(0xD4, 0xA8, 0x60))
    tip_grad.setColorAt(1.0, QColor(0x88, 0x58, 0x20))
    tip_path = QPainterPath()
    tip_path.moveTo(float(-pw // 2), float(tip_y))
    tip_path.lineTo(float(pw // 2), float(tip_y))
    tip_path.lineTo(0.0, float(tip_y + tip_h))
    tip_path.closeSubpath()
    p.setPen(QPen(QColor(80, 50, 10), 1))
    p.fillPath(tip_path, tip_grad)
    p.drawPath(tip_path)

    # Graphite point
    p.setBrush(QColor(40, 40, 50))
    p.setPen(Qt.PenStyle.NoPen)
    point = QPainterPath()
    point.moveTo(-1.0, float(tip_y + tip_h - 2))
    point.lineTo(1.0, float(tip_y + tip_h - 2))
    point.lineTo(0.0, float(tip_y + tip_h))
    point.closeSubpath()
    p.fillPath(point, QColor(40, 40, 50))

    # Specular highlight on body (upper-left light source)
    spec = QRadialGradient(float(-pw // 2 + 1), float(-ph // 4), float(pw * 0.6))
    spec.setColorAt(0.0, QColor(255, 255, 255, 120))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawRect(-pw // 2, -ph // 2, pw // 2, ph - 6)

    p.restore()
    p.restore()


# ---------------------------------------------------------------------------
# Emotion-state prop overlays for Trophie
# ---------------------------------------------------------------------------

def draw_state_talking(p: QPainter, widget) -> None:
    """Clipboard with animated checkmarks beside Trophie while talking."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_passive_t', 0.0)
    bx = cx + int(tw * 0.32)
    by = cy - int(th * 0.10)
    bw = int(tw * 0.22)
    bh = int(th * 0.30)

    # Drop shadow
    p.setOpacity(0.25)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(bx + 3, by + 3, bw, bh, 3, 3)
    p.setOpacity(1.0)

    # Board with wood-grain gradient (5 stops)
    board_grad = QLinearGradient(float(bx), 0.0, float(bx + bw), 0.0)
    board_grad.setColorAt(0.00, QColor(0xA0, 0x70, 0x38))
    board_grad.setColorAt(0.25, QColor(0xC8, 0x96, 0x50))
    board_grad.setColorAt(0.50, QColor(0xD8, 0xAA, 0x64))
    board_grad.setColorAt(0.75, QColor(0xC0, 0x8A, 0x48))
    board_grad.setColorAt(1.00, QColor(0x98, 0x68, 0x30))
    p.setPen(QPen(_BROWN, 2))
    p.setBrush(board_grad)
    p.drawRoundedRect(bx, by, bw, bh, 3, 3)

    # Bevel on board
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.drawLine(bx, by, bx + bw, by)
    p.drawLine(bx, by, bx, by + bh)
    p.setPen(QPen(QColor(0, 0, 0, 70), 1))
    p.drawLine(bx, by + bh, bx + bw, by + bh)
    p.drawLine(bx + bw, by, bx + bw, by + bh)

    # Metal clip with QConicalGradient + specular
    clip_w = max(4, bw // 3)
    clip_x = bx + (bw - clip_w) // 2
    clip_cx = clip_x + clip_w // 2
    clip_cy = by - 1
    cg = QConicalGradient(float(clip_cx), float(clip_cy), 0.0)
    cg.setColorAt(0.00, QColor(0xC0, 0xC8, 0xD8))
    cg.setColorAt(0.25, QColor(0xFF, 0xFF, 0xFF))
    cg.setColorAt(0.50, QColor(0x80, 0x88, 0x98))
    cg.setColorAt(0.75, QColor(0xE0, 0xE0, 0xE8))
    cg.setColorAt(1.00, QColor(0xC0, 0xC8, 0xD8))
    p.setPen(QPen(QColor(0x50, 0x50, 0x50), 1))
    p.setBrush(cg)
    p.drawRoundedRect(clip_x, by - 4, clip_w, 8, 2, 2)
    spec = QRadialGradient(float(clip_x + clip_w // 4), float(by - 3), float(clip_w * 0.3))
    spec.setColorAt(0.0, QColor(255, 255, 255, 160))
    spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawRoundedRect(clip_x, by - 4, clip_w, 8, 2, 2)

    # Lines and checkmarks
    line_x = bx + 4
    check_color = QColor(0x00, 0xAA, 0x44)
    for i in range(3):
        ly = by + 10 + i * (bh // 4)
        p.setPen(QPen(QColor(180, 160, 130), 1))
        p.drawLine(line_x + 10, ly + 6, bx + bw - 4, ly + 6)
        if t % 3.0 > (i + 1) * 0.6:
            p.setPen(QPen(check_color, 2))
            p.drawLine(line_x, ly + 4, line_x + 3, ly + 8)
            p.drawLine(line_x + 3, ly + 8, line_x + 8, ly)

    # Environment reflection stripe
    env = QLinearGradient(float(bx), float(by), float(bx + bw * 0.7), float(by + bh * 0.7))
    env.setColorAt(0.0, QColor(255, 255, 255, 0))
    env.setColorAt(0.4, QColor(255, 255, 255, 28))
    env.setColorAt(0.6, QColor(255, 255, 255, 28))
    env.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(env)
    p.drawRoundedRect(bx, by, bw, bh, 3, 3)

    # Pointing finger indicator
    p.setPen(QPen(QColor(220, 190, 150), 2))
    p.drawLine(cx + int(tw * 0.28), cy, bx - 2, by + bh // 2)
    p.restore()


def draw_state_happy(p: QPainter, widget) -> None:
    """Stamp slamming down 'APPROVED' with confetti."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_passive_t', 0.0)

    # Stamp handle — cylindrical red gradient
    sx = cx + int(tw * 0.18)
    sh_body = int(th * 0.14)
    sy_body = cy - int(th * 0.10)
    sw = int(tw * 0.26)
    handle_grad = QLinearGradient(float(sx), 0.0, float(sx + sw), 0.0)
    handle_grad.setColorAt(0.00, QColor(0x7A, 0x00, 0x00))
    handle_grad.setColorAt(0.20, QColor(0xCC, 0x20, 0x20))
    handle_grad.setColorAt(0.45, QColor(0xF0, 0x50, 0x50))
    handle_grad.setColorAt(0.70, QColor(0xBB, 0x10, 0x10))
    handle_grad.setColorAt(1.00, QColor(0x66, 0x00, 0x00))
    p.setPen(QPen(QColor(60, 0, 0), 1))
    p.setBrush(handle_grad)
    p.drawRoundedRect(sx, sy_body, sw, sh_body, 3, 3)
    # Handle specular
    h_spec = QRadialGradient(float(sx + sw * 0.2), float(sy_body + sh_body * 0.2), float(sw * 0.3))
    h_spec.setColorAt(0.0, QColor(255, 200, 200, 100))
    h_spec.setColorAt(1.0, QColor(255, 200, 200, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(h_spec)
    p.drawRoundedRect(sx, sy_body, sw, sh_body, 3, 3)

    # Rubber face — green with specular
    sy_rubber = sy_body + sh_body
    sh_rubber = int(th * 0.06)
    rubber_grad = QLinearGradient(float(sx), 0.0, float(sx + sw), 0.0)
    rubber_grad.setColorAt(0.0, QColor(0x10, 0x88, 0x30))
    rubber_grad.setColorAt(0.3, QColor(0x30, 0xCC, 0x60))
    rubber_grad.setColorAt(0.65, QColor(0x18, 0xAA, 0x44))
    rubber_grad.setColorAt(1.0, QColor(0x08, 0x70, 0x28))
    p.setPen(QPen(QColor(0, 60, 20), 1))
    p.setBrush(rubber_grad)
    p.drawRoundedRect(sx, sy_rubber, sw, sh_rubber, 1, 1)
    # Rubber specular
    r_spec = QRadialGradient(float(sx + sw * 0.25), float(sy_rubber + sh_rubber * 0.25), float(sw * 0.2))
    r_spec.setColorAt(0.0, QColor(255, 255, 255, 80))
    r_spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(r_spec)
    p.drawRoundedRect(sx, sy_rubber, sw, sh_rubber, 1, 1)

    # Ink impression "APPROVED" with glow
    stamp_y = cy - int(th * 0.05)
    glow = QRadialGradient(float(sx + sw // 2), float(stamp_y), float(sw * 0.8))
    glow.setColorAt(0.0, QColor(0, 200, 80, 60))
    glow.setColorAt(1.0, QColor(0, 200, 80, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(sx - 6, stamp_y - 4, sw + 12, int(th * 0.10))
    p.setPen(QColor(255, 255, 255))
    font = QFont("Arial", max(5, tw // 14), QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0x00, 0xAA, 0x44, 200))
    p.drawRoundedRect(sx, stamp_y, sw, int(th * 0.08), 2, 2)
    p.setPen(QColor(255, 255, 255))
    p.drawText(sx + 2, stamp_y + int(th * 0.06), "APPROVED ✓")

    # Confetti with varied shapes in different colors
    confetti_params = [
        (cx - int(tw * 0.25), cy - int(th * 0.20), QColor(255, 80, 80),  'rect'),
        (cx + int(tw * 0.25), cy - int(th * 0.25), QColor(80, 200, 80),  'circle'),
        (cx - int(tw * 0.10), cy - int(th * 0.30), QColor(80, 80, 255),  'tri'),
        (cx + int(tw * 0.15), cy - int(th * 0.15), QColor(255, 200, 60), 'rect'),
        (cx - int(tw * 0.18), cy - int(th * 0.38), QColor(255, 100, 200), 'circle'),
        (cx + int(tw * 0.08), cy - int(th * 0.42), QColor(0, 220, 220),  'tri'),
    ]
    for i, (confx, confy, col, shape) in enumerate(confetti_params):
        rot = (t * 120 + i * 60) % 360
        alpha = int(180 + 60 * math.sin(t * 3.0 + i))
        c = QColor(col.red(), col.green(), col.blue(), max(60, alpha))
        p.save()
        p.translate(confx, confy)
        p.rotate(rot)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        if shape == 'rect':
            p.drawRect(-3, -3, 6, 4)
        elif shape == 'circle':
            p.drawEllipse(-3, -3, 6, 6)
        else:
            tri = QPainterPath()
            tri.moveTo(0.0, -4.0)
            tri.lineTo(-3.5, 3.0)
            tri.lineTo(3.5, 3.0)
            tri.closeSubpath()
            p.fillPath(tri, c)
        p.restore()
    p.restore()


def draw_state_sad(p: QPainter, widget) -> None:
    """Falling file folders while sad."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_passive_t', 0.0)
    folder_data = [
        (QColor(0xD2, 0xB4, 0x8C), QColor(0xA0, 0x78, 0x40), QColor(0xF0, 0xD4, 0xA0)),
        (QColor(0x8B, 0x5E, 0x3C), QColor(0x5A, 0x34, 0x14), QColor(0xAA, 0x7A, 0x52)),
        (QColor(0xF5, 0xD8, 0xA8), QColor(0xC8, 0xA0, 0x68), QColor(0xFF, 0xF0, 0xC8)),
    ]
    for i, (fc_mid, fc_dark, fc_light) in enumerate(folder_data):
        fall_y = int((t * 20 + i * 15) % (th * 0.6))
        rot = math.sin(t * 1.5 + i) * 15.0
        fx = cx - int(tw * 0.20) + i * int(tw * 0.15)
        fy = cy - int(th * 0.20) + fall_y
        fw = int(tw * 0.12)
        fh = int(th * 0.18)
        p.save()
        p.translate(fx + fw // 2, fy + fh // 2)
        p.rotate(rot)

        # Drop shadow
        p.setOpacity(0.18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawRoundedRect(-fw // 2 + 2, -fh // 2 + 2, fw, fh, 2, 2)
        p.setOpacity(1.0)

        # Tab
        tab_w = fw // 2
        tab_grad = QLinearGradient(float(-fw // 2), float(-fh // 2 - 5), float(-fw // 2), float(-fh // 2))
        tab_grad.setColorAt(0.0, fc_light)
        tab_grad.setColorAt(1.0, fc_mid)
        p.setPen(QPen(QColor(80, 50, 20), 1))
        p.setBrush(tab_grad)
        p.drawRoundedRect(-fw // 2, -fh // 2 - 5, tab_w, 6, 2, 2)

        # Folder body with depth gradient
        body_grad = QLinearGradient(float(-fw // 2), float(-fh // 2), float(-fw // 2), float(fh // 2))
        body_grad.setColorAt(0.0, fc_light)
        body_grad.setColorAt(0.2, fc_mid)
        body_grad.setColorAt(1.0, fc_dark)
        p.setBrush(body_grad)
        p.drawRect(-fw // 2, -fh // 2, fw, fh)

        # Paper edge at top
        paper_grad = QLinearGradient(float(-fw // 2 + 2), 0.0, float(fw // 2 - 2), 0.0)
        paper_grad.setColorAt(0.0, QColor(238, 234, 225))
        paper_grad.setColorAt(0.5, QColor(255, 252, 244))
        paper_grad.setColorAt(1.0, QColor(235, 231, 222))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(paper_grad)
        p.drawRect(-fw // 2 + 2, -fh // 2 + 2, fw - 4, max(3, fh // 8))

        # Bevel
        p.setPen(QPen(QColor(255, 255, 255, 55), 1))
        p.drawLine(-fw // 2, -fh // 2, fw // 2, -fh // 2)
        p.drawLine(-fw // 2, -fh // 2, -fw // 2, fh // 2)
        p.setPen(QPen(QColor(0, 0, 0, 45), 1))
        p.drawLine(-fw // 2, fh // 2, fw // 2, fh // 2)
        p.drawLine(fw // 2, -fh // 2, fw // 2, fh // 2)
        p.restore()
    p.restore()


def draw_state_sleepy(p: QPainter, widget) -> None:
    """Stack of books + ZZZ + coffee while sleepy."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_passive_t', 0.0)

    # Book stack
    book_data = [
        (QColor(0x8B, 0x00, 0x00), QColor(0xC0, 0x20, 0x20), QColor(0x60, 0x00, 0x00)),
        (QColor(0x00, 0x00, 0x8B), QColor(0x20, 0x20, 0xC0), QColor(0x00, 0x00, 0x60)),
        (_DARK_GREEN,               QColor(0x40, 0x88, 0x38), QColor(0x18, 0x3E, 0x14)),
    ]
    bx = cx + int(tw * 0.25)
    by = cy
    bw = int(tw * 0.20)
    bh = int(th * 0.08)
    for i, (bc_mid, bc_light, bc_dark) in enumerate(book_data):
        book_y = by - i * (bh + 1)

        # Drop shadow under bottom book
        if i == 0:
            p.setOpacity(0.20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 50))
            p.drawRect(bx + 2, book_y + 2, bw, bh)
            p.setOpacity(1.0)

        # Book cover gradient (spine gradient effect)
        cover_grad = QLinearGradient(float(bx), 0.0, float(bx + bw), 0.0)
        cover_grad.setColorAt(0.00, bc_dark)
        cover_grad.setColorAt(0.08, bc_mid)
        cover_grad.setColorAt(0.30, bc_light)
        cover_grad.setColorAt(0.70, bc_mid)
        cover_grad.setColorAt(1.00, bc_dark)
        p.setPen(QPen(QColor(10, 10, 10), 1))
        p.setBrush(cover_grad)
        p.drawRect(bx, book_y, bw, bh)

        # Leather-look top edge
        leather = QLinearGradient(float(bx), float(book_y), float(bx + bw), float(book_y + 2))
        leather.setColorAt(0.0, bc_light)
        leather.setColorAt(1.0, bc_mid)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(leather)
        p.drawRect(bx, book_y, bw, 2)

        # Bevel
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        p.drawLine(bx, book_y, bx + bw, book_y)
        p.drawLine(bx, book_y, bx, book_y + bh)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.drawLine(bx, book_y + bh, bx + bw, book_y + bh)
        p.drawLine(bx + bw, book_y, bx + bw, book_y + bh)

    # ZZZ letters with glow
    zzz_data = [(bx + 4, by - int(th * 0.25) - j * 8, max(6, tw // 10) - j) for j in range(3)]
    for i, (zx, zy, zs) in enumerate(zzz_data):
        alpha = int(180 - i * 40)
        glow_r = QRadialGradient(float(zx + zs // 2), float(zy - zs // 2), float(zs))
        glow_r.setColorAt(0.0, QColor(160, 160, 255, min(80, alpha // 2)))
        glow_r.setColorAt(1.0, QColor(160, 160, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow_r)
        p.drawEllipse(zx - zs // 2, zy - zs, zs * 2, zs * 2)
        p.setPen(QColor(210, 210, 255, alpha))
        font = QFont("Arial", zs, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(zx + i * 4, zy, "Z")

    # Coffee cup with ceramic gradient
    mx = bx - int(tw * 0.28)
    my = by - int(th * 0.05)
    mw = int(tw * 0.14)
    mh = int(th * 0.16)

    # Cup drop shadow
    p.setOpacity(0.20)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 50))
    p.drawRoundedRect(mx + 2, my + 2, mw, mh, 3, 3)
    p.setOpacity(1.0)

    # Ceramic mug gradient
    mug_grad = QRadialGradient(float(mx + mw * 0.25), float(my + mh * 0.20), float(mw * 0.85))
    mug_grad.setColorAt(0.0, QColor(0xFF, 0xFF, 0xFF))
    mug_grad.setColorAt(0.4, QColor(0xF0, 0xEE, 0xEA))
    mug_grad.setColorAt(1.0, QColor(0xC8, 0xC4, 0xBE))
    p.setPen(QPen(_COFFEE, 1))
    p.setBrush(mug_grad)
    p.drawRoundedRect(mx, my, mw, mh, 3, 3)

    # Coffee surface
    coffee_h = int(mh * 0.3)
    coffee_grad = QLinearGradient(float(mx + 2), float(my + 2), float(mx + 2), float(my + 2 + coffee_h))
    coffee_grad.setColorAt(0.0, QColor(0x60, 0x38, 0x12))
    coffee_grad.setColorAt(1.0, QColor(0x2C, 0x14, 0x02))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(coffee_grad)
    p.drawRoundedRect(mx + 2, my + 2, mw - 4, coffee_h, 2, 2)

    # Handle
    p.setPen(QPen(_COFFEE, 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(mx + mw - 2, my + mh // 4, 6, mh // 2, -90 * 16, 180 * 16)
    p.restore()


def draw_state_surprised(p: QPainter, widget) -> None:
    """Flying paper sheets + exclamation mark."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_passive_t', 0.0)
    for i in range(4):
        rot = (t * 90 + i * 70) % 360
        px = cx + int(math.cos(t * 2.0 + i) * tw * 0.30)
        py = cy + int(math.sin(t * 2.0 + i) * th * 0.20) - int(th * 0.10)
        p.save()
        p.translate(px, py)
        p.rotate(rot)

        # Paper with slight crumple gradient (cream-white)
        paper_grad = QLinearGradient(-6.0, -8.0, 6.0, 8.0)
        paper_grad.setColorAt(0.0, QColor(255, 255, 248))
        paper_grad.setColorAt(0.35, QColor(248, 246, 236))
        paper_grad.setColorAt(0.65, QColor(242, 240, 228))
        paper_grad.setColorAt(1.0, QColor(230, 228, 215))
        p.setBrush(paper_grad)
        p.setPen(QPen(QColor(170, 165, 148), 1))
        # Trapezoidal shape for slight curl/bend look
        paper_path = QPainterPath()
        paper_path.moveTo(-6.0, -8.0)
        paper_path.lineTo(7.0, -7.0)
        paper_path.lineTo(6.0, 8.0)
        paper_path.lineTo(-7.0, 7.0)
        paper_path.closeSubpath()
        p.fillPath(paper_path, paper_grad)
        p.setPen(QPen(QColor(160, 155, 138), 1))
        p.drawPath(paper_path)

        # Drop shadow
        p.setOpacity(0.15)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawRect(-5, -7, 13, 16)
        p.setOpacity(1.0)

        # Ruled line suggestion
        p.setPen(QPen(QColor(160, 170, 200, 80), 1))
        for li in range(3):
            p.drawLine(-4, -4 + li * 4, 4, -4 + li * 4)

        p.restore()

    # Exclamation mark with glow and shadow
    ex = cx - 4
    ey = cy - int(th * 0.45)
    font = QFont("Arial Black", max(8, tw // 7), QFont.Weight.Black)
    p.setFont(font)
    # Shadow
    p.setPen(QColor(180, 20, 0, 100))
    p.drawText(ex + 2, ey + 2, "!")
    # Glow behind text
    glow = QRadialGradient(float(ex + 6), float(ey - 2), float(tw // 6))
    glow.setColorAt(0.0, QColor(255, 100, 40, 80))
    glow.setColorAt(1.0, QColor(255, 100, 40, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(ex - tw // 8, ey - tw // 5, tw // 4, tw // 4)
    # Main text
    p.setPen(QColor(255, 60, 20))
    p.drawText(ex, ey, "!")
    p.restore()


def draw_state_dismissing(p: QPainter, widget) -> None:
    """Closing book as Trophie dismisses."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    scale = getattr(widget, '_scale', 1.0)
    open_angle = scale * 60.0  # degrees each page opens from spine
    bx = cx + int(tw * 0.20)
    by = cy - int(th * 0.10)
    bw = int(tw * 0.22)
    bh = int(th * 0.22)

    # Drop shadow
    p.setOpacity(0.20)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 50))
    p.drawRoundedRect(bx + 2, by + 2, bw * 2, bh, 2, 2)
    p.setOpacity(1.0)

    # Left page with paper texture gradient
    p.save()
    p.translate(bx, by + bh // 2)
    p.rotate(-open_angle)
    left_grad = QLinearGradient(float(-bw), float(-bh // 2), 0.0, float(bh // 2))
    left_grad.setColorAt(0.0, QColor(0xD8, 0xD2, 0xBC))
    left_grad.setColorAt(0.25, QColor(0xE8, 0xE4, 0xD0))
    left_grad.setColorAt(0.60, QColor(0xF5, 0xF2, 0xE2))
    left_grad.setColorAt(1.0, QColor(0xE0, 0xDC, 0xC8))
    p.setBrush(left_grad)
    p.setPen(QPen(QColor(80, 50, 20), 1))
    p.drawRect(0, -bh // 2, -bw, bh)
    # Bevel
    p.setPen(QPen(QColor(255, 255, 255, 55), 1))
    p.drawLine(-bw, -bh // 2, 0, -bh // 2)
    p.drawLine(-bw, -bh // 2, -bw, bh // 2)
    p.setPen(QPen(QColor(0, 0, 0, 45), 1))
    p.drawLine(-bw, bh // 2, 0, bh // 2)
    # Page lines
    p.setPen(QPen(QColor(160, 145, 115, 100), 1))
    for li in range(4):
        line_y = -bh // 2 + int(bh * 0.15) + li * int(bh * 0.18)
        p.drawLine(-bw + 4, line_y, -4, line_y)
    p.restore()

    # Right page with paper texture gradient
    p.save()
    p.translate(bx, by + bh // 2)
    p.rotate(open_angle)
    right_grad = QLinearGradient(0.0, float(-bh // 2), float(bw), float(bh // 2))
    right_grad.setColorAt(0.0, QColor(0xE0, 0xDC, 0xC8))
    right_grad.setColorAt(0.40, QColor(0xF0, 0xEC, 0xDC))
    right_grad.setColorAt(0.75, QColor(0xEC, 0xE8, 0xD5))
    right_grad.setColorAt(1.0, QColor(0xD5, 0xD0, 0xBC))
    p.setBrush(right_grad)
    p.setPen(QPen(QColor(80, 50, 20), 1))
    p.drawRect(0, -bh // 2, bw, bh)
    # Bevel
    p.setPen(QPen(QColor(255, 255, 255, 55), 1))
    p.drawLine(0, -bh // 2, bw, -bh // 2)
    p.drawLine(0, -bh // 2, 0, bh // 2)
    p.setPen(QPen(QColor(0, 0, 0, 45), 1))
    p.drawLine(0, bh // 2, bw, bh // 2)
    p.drawLine(bw, -bh // 2, bw, bh // 2)
    # Page lines
    p.setPen(QPen(QColor(160, 145, 115, 100), 1))
    for li in range(4):
        line_y = -bh // 2 + int(bh * 0.15) + li * int(bh * 0.18)
        p.drawLine(4, line_y, bw - 4, line_y)
    p.restore()

    # Spine (dark gradient at centre)
    spine_w = max(3, bw // 8)
    p.save()
    p.translate(bx, by + bh // 2)
    spine_grad = QLinearGradient(float(-spine_w), 0.0, float(spine_w), 0.0)
    spine_grad.setColorAt(0.0, QColor(0x40, 0x22, 0x08))
    spine_grad.setColorAt(0.4, QColor(0x70, 0x42, 0x18))
    spine_grad.setColorAt(0.6, QColor(0x58, 0x30, 0x10))
    spine_grad.setColorAt(1.0, QColor(0x38, 0x1C, 0x06))
    p.setPen(QPen(QColor(30, 12, 2), 1))
    p.setBrush(spine_grad)
    p.drawRect(-spine_w, -bh // 2, spine_w * 2, bh)
    p.restore()
    p.restore()


# ---------------------------------------------------------------------------
# Trophie event animation tick helpers
# ---------------------------------------------------------------------------

def tick_event_eureka(widget) -> None:
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    widget._passive_extra_y = -abs(math.sin(t * 6.0)) * 5.0


def tick_event_chart_update(widget) -> None:
    pass


def tick_event_file_complete(widget) -> None:
    pass


def tick_event_red_pen(widget) -> None:
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    widget._passive_extra_x = math.sin(t * 12.0) * 2.0


def tick_event_coffee_break(widget) -> None:
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    widget._passive_extra_y = math.sin(t * 1.5) * 3.0


def tick_event_deep_research(widget) -> None:
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    widget._passive_extra_x = math.sin(t * 1.5) * 6.0


# ---------------------------------------------------------------------------
# Trophie event animation draw helpers
# ---------------------------------------------------------------------------

def draw_event_eureka(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    br = max(8, int(tw * 0.12))
    bx = cx
    by = cy - int(th * 0.52)

    # Strong outer glow with radial gradient
    outer_glow = QRadialGradient(float(bx), float(by), float(br * 3.5))
    outer_glow.setColorAt(0.0, QColor(255, 255, 100, 160))
    outer_glow.setColorAt(0.4, QColor(255, 230, 40, 80))
    outer_glow.setColorAt(1.0, QColor(255, 200, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(outer_glow)
    p.drawEllipse(bx - br * 3, by - br * 3, br * 6, br * 6)

    # Bright inner glow
    inner_glow = QRadialGradient(float(bx), float(by), float(br * 1.8))
    inner_glow.setColorAt(0.0, QColor(255, 255, 220, 200))
    inner_glow.setColorAt(0.5, QColor(255, 240, 100, 100))
    inner_glow.setColorAt(1.0, QColor(255, 200, 0, 0))
    p.setBrush(inner_glow)
    p.drawEllipse(bx - br * 2, by - br * 2, br * 4, br * 4)

    # Glass bulb with radial gradient (bright inner, semi-transparent glass)
    bulb_grad = QRadialGradient(float(bx - br * 0.3), float(by - br * 0.3), float(br * 1.2))
    bulb_grad.setColorAt(0.0, QColor(255, 255, 240, 250))
    bulb_grad.setColorAt(0.35, QColor(255, 245, 150, 230))
    bulb_grad.setColorAt(0.70, QColor(240, 210, 60, 200))
    bulb_grad.setColorAt(1.0, QColor(200, 160, 20, 160))
    p.setPen(QPen(QColor(80, 80, 80), 2))
    p.setBrush(bulb_grad)
    p.drawEllipse(bx - br, by - br, br * 2, br * 2)

    # Crescent glass sheen
    sheen = QRadialGradient(float(bx - br * 0.4), float(by - br * 0.4), float(br * 0.5))
    sheen.setColorAt(0.0, QColor(255, 255, 255, 180))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(sheen)
    p.drawEllipse(bx - br, by - br, br * 2, br * 2)

    # Metallic socket
    socket_w = br
    socket_h = max(3, br // 2)
    socket_x = bx - socket_w // 2
    socket_y = by + br - 2
    s_cg = QConicalGradient(float(bx), float(socket_y + socket_h // 2), 0.0)
    s_cg.setColorAt(0.00, QColor(0xB0, 0xB8, 0xC8))
    s_cg.setColorAt(0.25, QColor(0xF0, 0xF4, 0xFF))
    s_cg.setColorAt(0.50, QColor(0x78, 0x80, 0x90))
    s_cg.setColorAt(0.75, QColor(0xD0, 0xD4, 0xE0))
    s_cg.setColorAt(1.00, QColor(0xB0, 0xB8, 0xC8))
    p.setPen(QPen(QColor(70, 70, 80), 1))
    p.setBrush(s_cg)
    p.drawRect(socket_x, socket_y, socket_w, socket_h)

    # Rays with varying alpha (rotating)
    for i in range(10):
        angle = i * math.pi / 5 + t * 1.5
        ray_alpha = int(200 - 80 * ((i % 3) / 2.0))
        ray_w = 2 if i % 2 == 0 else 1
        r0 = br + 3
        r1 = br + 9 + (i % 4) * 2
        ray_pen = QPen(QColor(255, 220, 0, ray_alpha), ray_w)
        ray_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(ray_pen)
        p.drawLine(
            bx + int(math.cos(angle) * r0),
            by + int(math.sin(angle) * r0),
            bx + int(math.cos(angle) * r1),
            by + int(math.sin(angle) * r1),
        )

    # Floating note icons with paper texture
    for i in range(3):
        nx = cx + int(math.cos(t * 1.5 + i * 2.1) * tw * 0.25)
        ny = by + int(math.sin(t * 1.5 + i * 2.1) * th * 0.12) - 8
        note_grad = QLinearGradient(float(nx - 4), float(ny - 5), float(nx + 4), float(ny + 5))
        note_grad.setColorAt(0.0, QColor(255, 252, 210))
        note_grad.setColorAt(1.0, QColor(240, 235, 185))
        p.setBrush(note_grad)
        p.setPen(QPen(QColor(150, 130, 80), 1))
        p.drawRect(nx - 4, ny - 5, 8, 10)
        # Note line
        p.setPen(QPen(QColor(160, 140, 90, 100), 1))
        p.drawLine(nx - 2, ny, nx + 2, ny)
    p.restore()


def draw_event_chart_update(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    chart_x = cx - int(tw * 0.20)
    chart_y = cy - int(th * 0.40)
    chart_w = int(tw * 0.40)
    chart_h = int(th * 0.30)

    # Drop shadow
    p.setOpacity(0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRect(chart_x + 3, chart_y + 3, chart_w, chart_h)
    p.setOpacity(1.0)

    # Background with gradient
    bg_grad = QLinearGradient(float(chart_x), float(chart_y), float(chart_x), float(chart_y + chart_h))
    bg_grad.setColorAt(0.0, QColor(250, 252, 255))
    bg_grad.setColorAt(0.5, QColor(242, 245, 252))
    bg_grad.setColorAt(1.0, QColor(228, 232, 245))
    p.setPen(QPen(QColor(160, 165, 180), 1))
    p.setBrush(bg_grad)
    p.drawRect(chart_x, chart_y, chart_w, chart_h)

    # Bevel
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(chart_x, chart_y, chart_x + chart_w, chart_y)
    p.drawLine(chart_x, chart_y, chart_x, chart_y + chart_h)
    p.setPen(QPen(QColor(0, 0, 0, 50), 1))
    p.drawLine(chart_x, chart_y + chart_h, chart_x + chart_w, chart_y + chart_h)
    p.drawLine(chart_x + chart_w, chart_y, chart_x + chart_w, chart_y + chart_h)

    # Gradient bars
    bar_heights = [0.4, 0.6, 0.75, 0.9]
    bar_colors = [
        (0x1A, 0x3A, 0x5C),
        (0x22, 0x4A, 0x70),
        (0x18, 0x38, 0x58),
        (0x20, 0x48, 0x6C),
    ]
    bw_bar = max(3, (chart_w - 10) // (len(bar_heights) * 2))
    grow = min(1.0, t / 1.5)
    for i, (bh_r, (r, g, b)) in enumerate(zip(bar_heights, bar_colors)):
        bh_px = int((chart_h - 8) * bh_r * grow)
        if bh_px <= 0:
            continue
        bxi = chart_x + 5 + i * (bw_bar + 4)
        byi = chart_y + chart_h - 4 - bh_px
        bar_grad = QLinearGradient(float(bxi), float(byi), float(bxi), float(byi + bh_px))
        bar_grad.setColorAt(0.0, QColor(min(255, r + 70), min(255, g + 70), min(255, b + 90)))
        bar_grad.setColorAt(0.35, QColor(r + 20, g + 20, b + 30))
        bar_grad.setColorAt(1.0, QColor(r, g, b))
        p.setBrush(bar_grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(bxi, byi, bw_bar, bh_px)
        # Glossy highlight
        gloss = QLinearGradient(float(bxi), float(byi), float(bxi + bw_bar), float(byi))
        gloss.setColorAt(0.0, QColor(255, 255, 255, 70))
        gloss.setColorAt(0.5, QColor(255, 255, 255, 120))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 20))
        p.setBrush(gloss)
        p.drawRect(bxi, byi, bw_bar, max(2, bh_px // 3))

    # Rising arrow with glow
    if t > 1.0:
        arrow_x = chart_x + chart_w - 12
        arrow_y = chart_y + int(chart_h * (1.0 - min(1.0, (t - 1.0) / 1.0)))
        # Arrow glow
        arrow_glow = QRadialGradient(float(arrow_x), float(arrow_y), float(chart_w * 0.15))
        arrow_glow.setColorAt(0.0, QColor(0, 220, 80, 80))
        arrow_glow.setColorAt(1.0, QColor(0, 220, 80, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(arrow_glow)
        p.drawEllipse(arrow_x - 8, arrow_y - 8, 16, 16)
        p.setPen(QPen(QColor(0, 200, 80), 2))
        p.drawLine(arrow_x, arrow_y + 10, arrow_x, chart_y + 4)
        p.drawLine(arrow_x - 4, chart_y + 8, arrow_x, chart_y + 4)
        p.drawLine(arrow_x + 4, chart_y + 8, arrow_x, chart_y + 4)

    # LEVEL UP text with glowing effect
    if t > 2.0:
        text_alpha = min(255, int((t - 2.0) * 255))
        # Text glow
        text_glow = QRadialGradient(float(chart_x + chart_w * 0.4), float(chart_y - 5), float(chart_w * 0.4))
        text_glow.setColorAt(0.0, QColor(0, 200, 80, min(60, text_alpha // 3)))
        text_glow.setColorAt(1.0, QColor(0, 200, 80, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(text_glow)
        p.drawEllipse(chart_x, chart_y - 12, chart_w, 14)
        p.setPen(QColor(0, 180, 60, text_alpha))
        font = QFont("Arial", max(6, tw // 10), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(chart_x + 2, chart_y - 3, "LEVEL UP!")
    p.restore()


def draw_event_file_complete(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    drop = min(1.0, t / 0.5)
    sx = cx - int(tw * 0.15)
    paper_y = cy + int(th * 0.05)
    stamp_h = int(th * 0.14)
    stamp_y = cy - int(th * 0.25) + int(drop * int(th * 0.22))
    sw = int(tw * 0.30)

    # Folder/paper with gradient texture
    folder_grad = QLinearGradient(float(sx), float(paper_y), float(sx + sw), float(paper_y + int(th * 0.16)))
    folder_grad.setColorAt(0.0, QColor(0xF0, 0xD8, 0xA8))
    folder_grad.setColorAt(0.3, QColor(0xD8, 0xBC, 0x88))
    folder_grad.setColorAt(0.7, QColor(0xC8, 0xA8, 0x70))
    folder_grad.setColorAt(1.0, QColor(0xB0, 0x90, 0x58))
    p.setPen(QPen(_BROWN, 1))
    p.setBrush(folder_grad)
    p.drawRect(sx, paper_y, sw, int(th * 0.16))
    # Paper bevel
    p.setPen(QPen(QColor(255, 255, 255, 60), 1))
    p.drawLine(sx, paper_y, sx + sw, paper_y)
    p.drawLine(sx, paper_y, sx, paper_y + int(th * 0.16))
    p.setPen(QPen(QColor(0, 0, 0, 40), 1))
    p.drawLine(sx, paper_y + int(th * 0.16), sx + sw, paper_y + int(th * 0.16))
    p.drawLine(sx + sw, paper_y, sx + sw, paper_y + int(th * 0.16))
    # Paper lines on folder
    p.setPen(QPen(QColor(160, 135, 90, 100), 1))
    for li in range(3):
        ly = paper_y + int(th * 0.04) + li * int(th * 0.035)
        p.drawLine(sx + 4, ly, sx + sw - 4, ly)

    # Stamp descending — 3D cylindrical gradient
    stamp_w = sw // 2
    stamp_x = sx + sw // 4
    handle_grad = QLinearGradient(float(stamp_x), 0.0, float(stamp_x + stamp_w), 0.0)
    handle_grad.setColorAt(0.00, QColor(0x10, 0x60, 0x10))
    handle_grad.setColorAt(0.20, QColor(0x28, 0xAA, 0x30))
    handle_grad.setColorAt(0.45, QColor(0x40, 0xCC, 0x50))
    handle_grad.setColorAt(0.70, QColor(0x20, 0x96, 0x28))
    handle_grad.setColorAt(1.00, QColor(0x08, 0x50, 0x10))
    p.setPen(QPen(QColor(0, 60, 10), 1))
    p.setBrush(handle_grad)
    p.drawRoundedRect(stamp_x, stamp_y, stamp_w, stamp_h, 3, 3)

    # Handle specular
    h_spec = QRadialGradient(float(stamp_x + stamp_w * 0.22), float(stamp_y + stamp_h * 0.18), float(stamp_w * 0.3))
    h_spec.setColorAt(0.0, QColor(255, 255, 255, 90))
    h_spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(h_spec)
    p.drawRoundedRect(stamp_x, stamp_y, stamp_w, stamp_h, 3, 3)

    # Rubber face (darker green)
    rubber_h = max(4, stamp_h // 5)
    rubber_grad = QLinearGradient(float(stamp_x), 0.0, float(stamp_x + stamp_w), 0.0)
    rubber_grad.setColorAt(0.0, QColor(0x08, 0x70, 0x18))
    rubber_grad.setColorAt(0.35, QColor(0x18, 0xA0, 0x28))
    rubber_grad.setColorAt(0.70, QColor(0x10, 0x88, 0x20))
    rubber_grad.setColorAt(1.0, QColor(0x04, 0x58, 0x10))
    p.setPen(QPen(QColor(0, 50, 10), 1))
    p.setBrush(rubber_grad)
    p.drawRect(stamp_x, stamp_y + stamp_h - rubber_h, stamp_w, rubber_h)

    if t > 0.5:
        alpha = min(255, int((t - 0.5) / 0.4 * 255))
        # "COMPLETE ✓" glow
        glow = QRadialGradient(float(sx + sw // 2), float(paper_y + int(th * 0.08)), float(sw * 0.6))
        glow.setColorAt(0.0, QColor(0, 220, 80, min(80, alpha // 2)))
        glow.setColorAt(1.0, QColor(0, 220, 80, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(sx - 4, paper_y + 2, sw + 8, int(th * 0.12))
        p.setPen(QColor(255, 255, 255, alpha))
        font = QFont("Arial", max(6, tw // 12), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(sx + sw // 4 + 2, paper_y + int(th * 0.12), "COMPLETE ✓")

        # Impact starburst lines
        if t < 1.0:
            burst_alpha = int((1.0 - t) * 200)
            for i in range(8):
                angle = i * math.pi / 4
                burst_pen = QPen(QColor(0, 200, 60, burst_alpha), 1)
                burst_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(burst_pen)
                p.drawLine(
                    sx + sw // 2 + int(math.cos(angle) * 6),
                    paper_y + int(math.sin(angle) * 6),
                    sx + sw // 2 + int(math.cos(angle) * 14),
                    paper_y + int(math.sin(angle) * 14),
                )
    p.restore()


def draw_event_red_pen(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_trophie_event_anim_t', 0.0)

    # Paper with subtle gradient
    px = cx - int(tw * 0.18)
    py = cy - int(th * 0.10)
    pw = int(tw * 0.36)
    ph = int(th * 0.24)
    paper_grad = QLinearGradient(float(px), float(py), float(px + pw), float(py + ph))
    paper_grad.setColorAt(0.0, QColor(253, 251, 244))
    paper_grad.setColorAt(0.3, QColor(250, 248, 240))
    paper_grad.setColorAt(0.7, QColor(245, 242, 232))
    paper_grad.setColorAt(1.0, QColor(238, 234, 222))
    p.setPen(QPen(QColor(175, 172, 158), 1))
    p.setBrush(paper_grad)
    p.drawRect(px, py, pw, ph)
    # Paper bevel
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.drawLine(px, py, px + pw, py)
    p.drawLine(px, py, px, py + ph)
    p.setPen(QPen(QColor(0, 0, 0, 40), 1))
    p.drawLine(px, py + ph, px + pw, py + ph)
    p.drawLine(px + pw, py, px + pw, py + ph)
    # Paper lines
    p.setPen(QPen(QColor(180, 175, 158, 100), 1))
    for li in range(4):
        ly = py + int(ph * 0.15) + li * int(ph * 0.20)
        p.drawLine(px + 4, ly, px + pw - 4, ly)

    # X mark growing across document (thick bold red lines)
    x_progress = min(1.0, t / 1.5)
    x_len = int(pw * x_progress)
    x_pen = QPen(QColor(220, 20, 20), 3)
    x_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(x_pen)
    p.drawLine(px + 4, py + 4, px + 4 + x_len, py + int(ph * x_progress * 0.8))
    if t > 1.0:
        x2_progress = min(1.0, (t - 1.0) / 1.0)
        x2_len = int(pw * x2_progress)
        p.drawLine(px + pw - 4, py + 4, px + pw - 4 - x2_len, py + int(ph * x2_progress * 0.8))

    # Cylindrical red pen with gradient
    pen_x = cx + int(tw * 0.22)
    pen_y = cy - int(th * 0.12)
    p.save()
    p.translate(pen_x, pen_y)
    p.rotate(-35)
    pen_body_w = 6
    pen_body_h = 22
    body_grad = QLinearGradient(float(-pen_body_w // 2), 0.0, float(pen_body_w // 2), 0.0)
    body_grad.setColorAt(0.00, QColor(0x80, 0x00, 0x00))
    body_grad.setColorAt(0.25, QColor(0xCC, 0x10, 0x10))
    body_grad.setColorAt(0.45, QColor(0xEE, 0x40, 0x40))
    body_grad.setColorAt(0.70, QColor(0xC0, 0x10, 0x10))
    body_grad.setColorAt(1.00, QColor(0x70, 0x00, 0x00))
    p.setPen(QPen(QColor(100, 0, 0), 1))
    p.setBrush(body_grad)
    p.drawRect(-pen_body_w // 2, -pen_body_h // 2, pen_body_w, pen_body_h)
    # Pen body specular
    spec = QRadialGradient(float(-pen_body_w // 2 + 1), float(-pen_body_h // 4), float(pen_body_w * 0.5))
    spec.setColorAt(0.0, QColor(255, 200, 200, 100))
    spec.setColorAt(1.0, QColor(255, 200, 200, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spec)
    p.drawRect(-pen_body_w // 2, -pen_body_h // 2, pen_body_w, pen_body_h)
    # Pen tip
    tip_path = QPainterPath()
    tip_path.moveTo(float(-pen_body_w // 2), float(pen_body_h // 2))
    tip_path.lineTo(float(pen_body_w // 2), float(pen_body_h // 2))
    tip_path.lineTo(0.0, float(pen_body_h // 2 + 5))
    tip_path.closeSubpath()
    p.setPen(QPen(QColor(80, 60, 20), 1))
    p.fillPath(tip_path, QColor(200, 195, 160))
    p.restore()
    p.restore()


def draw_event_coffee_break(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    mx = cx + int(tw * 0.15)
    my = cy - int(th * 0.05)
    mw = int(tw * 0.22)
    mh = int(th * 0.26)

    # Drop shadow
    p.setOpacity(0.25)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(mx + 3, my + 3, mw, mh, 6, 6)
    p.setOpacity(1.0)

    # Ceramic mug body with radial gradient (white highlight upper-left)
    mug_grad = QRadialGradient(float(mx + mw * 0.22), float(my + mh * 0.18), float(mw * 1.0))
    mug_grad.setColorAt(0.0, QColor(0xFF, 0xFF, 0xFF))
    mug_grad.setColorAt(0.3, QColor(0xF5, 0xF4, 0xF0))
    mug_grad.setColorAt(0.65, QColor(0xE2, 0xE0, 0xDA))
    mug_grad.setColorAt(1.0, QColor(0xC4, 0xC0, 0xB8))
    p.setPen(QPen(_COFFEE, 2))
    p.setBrush(mug_grad)
    p.drawRoundedRect(mx, my, mw, mh, 6, 6)

    # Bevel on mug
    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
    p.drawLine(mx + 2, my + 2, mx + mw - 2, my + 2)
    p.drawLine(mx + 2, my + 2, mx + 2, my + mh - 2)
    p.setPen(QPen(QColor(0, 0, 0, 50), 1))
    p.drawLine(mx + 2, my + mh - 2, mx + mw - 2, my + mh - 2)
    p.drawLine(mx + mw - 2, my + 2, mx + mw - 2, my + mh - 2)

    # Coffee surface with dark gradient
    coffee_h = int(mh * 0.45)
    coffee_grad = QLinearGradient(float(mx + 3), float(my + 4), float(mx + 3), float(my + 4 + coffee_h))
    coffee_grad.setColorAt(0.0, QColor(0x72, 0x42, 0x16))
    coffee_grad.setColorAt(0.3, QColor(0x50, 0x2A, 0x0C))
    coffee_grad.setColorAt(0.7, QColor(0x3A, 0x1E, 0x06))
    coffee_grad.setColorAt(1.0, QColor(0x28, 0x12, 0x02))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(coffee_grad)
    p.drawRoundedRect(mx + 3, my + 4, mw - 6, coffee_h, 3, 3)
    # Surface shimmer reflection
    shimmer_a = int(50 + 30 * math.sin(t * 2.0))
    surf_refl = QLinearGradient(float(mx + 3), float(my + 4), float(mx + mw * 0.65), float(my + 4))
    surf_refl.setColorAt(0.0, QColor(255, 230, 170, shimmer_a))
    surf_refl.setColorAt(1.0, QColor(255, 230, 170, 0))
    p.setBrush(surf_refl)
    p.drawRoundedRect(mx + 3, my + 4, mw - 6, max(3, coffee_h // 4), 2, 2)

    # Handle with ceramic gradient
    handle_x = mx + mw - 3
    handle_y = my + mh // 4
    handle_w = max(8, mw // 3)
    handle_h = mh // 2
    handle_path = QPainterPath()
    handle_path.moveTo(float(handle_x), float(handle_y))
    handle_path.cubicTo(
        float(handle_x + handle_w + 3), float(handle_y - 3),
        float(handle_x + handle_w + 3), float(handle_y + handle_h + 3),
        float(handle_x), float(handle_y + handle_h)
    )
    handle_path.cubicTo(
        float(handle_x + handle_w - 3), float(handle_y + handle_h),
        float(handle_x + handle_w - 3), float(handle_y),
        float(handle_x), float(handle_y)
    )
    handle_grad = QLinearGradient(float(handle_x), 0.0, float(handle_x + handle_w), 0.0)
    handle_grad.setColorAt(0.0, QColor(0xD5, 0xD0, 0xC8))
    handle_grad.setColorAt(0.4, QColor(0xEE, 0xEC, 0xE8))
    handle_grad.setColorAt(1.0, QColor(0xAC, 0xA8, 0xA0))
    p.setPen(QPen(_COFFEE, 2))
    p.setBrush(handle_grad)
    p.drawPath(handle_path)

    # Exaggerated swirling steam wisps
    for i in range(4):
        base_sx = mx + 4 + i * (mw // 4)
        wisp_alpha = int(140 + 80 * math.sin(t * 3.0 + i * 0.9))
        wisp_path = QPainterPath()
        start_wy = my - 6
        wisp_path.moveTo(float(base_sx), float(start_wy))
        for seg in range(5):
            amp = 5 + seg * 1.5
            ox = int(amp * math.sin(t * 2.5 + i * 1.1 + seg * 0.8))
            wy = start_wy - (seg + 1) * 7
            wisp_path.cubicTo(
                float(base_sx + ox * 1.5), float(wy + 3),
                float(base_sx + ox * 0.5), float(wy + 1),
                float(base_sx - ox // 2), float(wy),
            )
            base_sx = base_sx - ox // 2
        wisp_pen = QPen(QColor(220, 220, 225, max(0, wisp_alpha)), 2)
        wisp_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(wisp_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(wisp_path)

    # Specular on mug upper-left
    mug_spec = QRadialGradient(float(mx + mw * 0.18), float(my + mh * 0.12), float(mw * 0.22))
    mug_spec.setColorAt(0.0, QColor(255, 255, 255, 140))
    mug_spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(mug_spec)
    p.drawRoundedRect(mx, my, mw, mh, 6, 6)
    p.restore()


def draw_event_deep_research(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    # cx already incorporates passive_extra_x — use cx directly for magnifier

    # Document
    doc_x = cx - int(tw * 0.20)
    doc_y = cy - int(th * 0.10)
    doc_w = int(tw * 0.40)
    doc_h = int(th * 0.28)
    p.setBrush(QColor(250, 248, 240))
    p.setPen(QPen(QColor(180, 180, 160), 1))
    p.drawRect(doc_x, doc_y, doc_w, doc_h)
    p.setPen(QPen(QColor(160, 160, 150), 1))
    for i in range(5):
        ly = doc_y + 6 + i * 8
        p.drawLine(doc_x + 4, ly, doc_x + doc_w - 4, ly)

    # Magnifying glass over document, scanning
    lr = max(8, int(tw * 0.12))
    mx = cx          # passive_extra_x already encoded in cx
    my = cy - int(th * 0.08)
    # Spotlight glow
    grad = QRadialGradient(float(mx), float(my), float(lr))
    grad.setColorAt(0.0, QColor(255, 255, 180, 120))
    grad.setColorAt(1.0, QColor(255, 255, 180, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawEllipse(mx - lr, my - lr, lr * 2, lr * 2)
    # Lens
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8), 3))
    p.setBrush(QColor(180, 210, 240, 80))
    p.drawEllipse(mx - lr, my - lr, lr * 2, lr * 2)
    p.setPen(QPen(QColor(0x80, 0x60, 0x40), 3))
    p.drawLine(mx + int(lr * 0.7), my + int(lr * 0.7), mx + lr + 8, my + lr + 8)
    p.restore()
