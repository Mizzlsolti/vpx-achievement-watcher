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
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient,
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
    """Return (cx, cy, tw, th, pad) for the trophy draw widget."""
    tw = widget._tw
    th = widget._th
    pad = widget._pad
    cx = tw // 2 + pad
    cy = th // 2 + int(th * 0.20) + pad
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

    # Left page
    p.setPen(QPen(QColor(80, 50, 20), 1))
    p.setBrush(_BEIGE)
    path_l = QPainterPath()
    path_l.moveTo(float(bx),           float(by))
    path_l.lineTo(float(bx - bw),      float(by + int(bh * 0.05)))
    path_l.lineTo(float(bx - bw),      float(by + bh))
    path_l.lineTo(float(bx),           float(by + bh))
    path_l.closeSubpath()
    p.fillPath(path_l, _BEIGE)
    p.drawPath(path_l)

    # Right page
    path_r = QPainterPath()
    path_r.moveTo(float(bx),           float(by))
    path_r.lineTo(float(bx + bw),      float(by + int(bh * 0.05)))
    path_r.lineTo(float(bx + bw),      float(by + bh))
    path_r.lineTo(float(bx),           float(by + bh))
    path_r.closeSubpath()
    p.fillPath(path_r, QColor(0xF0, 0xEB, 0xD5))
    p.drawPath(path_r)

    # Spine line
    p.setPen(QPen(QColor(80, 50, 20), 2))
    p.drawLine(bx, by, bx, by + bh)

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

    # Board
    p.setPen(QPen(_BROWN, 2))
    p.setBrush(_TAN)
    p.drawRoundedRect(bx, by, bw, bh, 3, 3)

    # Clip
    p.setBrush(QColor(0x80, 0x80, 0x80))
    p.setPen(QPen(QColor(0x50, 0x50, 0x50), 1))
    clip_w = max(4, bw // 3)
    clip_x = bx + (bw - clip_w) // 2
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
    p.restore()


def draw_thinking(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t

    # Small rising circles
    bubble_cx = cx + int(tw * 0.25)
    bubble_cy = cy - int(th * 0.30)
    p.setPen(QPen(QColor(180, 210, 240), 1))
    p.setBrush(QColor(240, 248, 255, 200))
    for i, (ox, oy, r) in enumerate([(0, 18, 4), (5, 10, 6), (12, 0, 10)]):
        p.drawEllipse(bubble_cx + ox - r, bubble_cy + oy - r, r * 2, r * 2)

    # Main oval cloud
    cw, ch = int(tw * 0.30), int(th * 0.18)
    cloud_x = bubble_cx - cw // 2 + 12
    cloud_y = bubble_cy - ch // 2
    p.setBrush(QColor(240, 248, 255, 220))
    p.setPen(QPen(QColor(160, 200, 240), 1))
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

    # Background
    p.setPen(QPen(QColor(180, 180, 190), 1))
    p.setBrush(QColor(240, 242, 248))
    p.drawRect(chart_x, chart_y, chart_w, chart_h)

    # Axes
    p.setPen(QPen(QColor(80, 80, 100), 1))
    p.drawLine(chart_x + 4, chart_y + chart_h - 4, chart_x + chart_w - 2, chart_y + chart_h - 4)
    p.drawLine(chart_x + 4, chart_y + 2, chart_x + 4, chart_y + chart_h - 4)

    # Bars
    bar_heights = [0.45, 0.70, 0.55, 0.85]
    bar_count = len(bar_heights)
    bar_w = max(3, (chart_w - 10) // (bar_count * 2))
    grow = min(1.0, t / 2.0)
    for i, bh_ratio in enumerate(bar_heights):
        target_h = int((chart_h - 8) * bh_ratio)
        actual_h = int(target_h * grow)
        bx = chart_x + 6 + i * (bar_w + 3)
        by = chart_y + chart_h - 4 - actual_h
        p.setBrush(_DARK_BLUE)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(bx, by, bar_w, actual_h)
    p.restore()


def draw_glasses_adjust(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t

    # Eye level approximate
    eye_y = cy - int(th * 0.26) + int(th * 0.12) + 4
    slide_down = 0
    if t % 4.0 < 0.8:
        slide_down = int((t % 4.0) / 0.8 * 6)

    lens_r = max(4, tw // 9)
    lens_sep = max(6, tw // 6)
    gy = eye_y + slide_down

    p.setPen(QPen(QColor(40, 40, 40), 2))
    p.setBrush(QColor(200, 230, 255, 60))
    p.drawEllipse(cx - lens_sep - lens_r, gy - lens_r, lens_r * 2, lens_r * 2)
    p.drawEllipse(cx + lens_sep - lens_r, gy - lens_r, lens_r * 2, lens_r * 2)
    # Bridge
    p.drawLine(cx - lens_sep + lens_r, gy, cx + lens_sep - lens_r, gy)
    # Temples
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

    # Mug body
    p.setPen(QPen(_COFFEE, 2))
    p.setBrush(QColor(0xFF, 0xFF, 0xFF))
    p.drawRoundedRect(mx, my, mw, mh, 4, 4)

    # Coffee surface
    p.setBrush(_COFFEE)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(mx + 2, my + 3, mw - 4, int(mh * 0.35))

    # Handle
    p.setPen(QPen(_COFFEE, 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(mx + mw - 2, my + mh // 4, 8, mh // 2, -90 * 16, 180 * 16)

    # Steam lines
    for i in range(3):
        sx = mx + 4 + i * (mw // 3)
        alpha = int(120 + 80 * math.sin(t * 2.5 + i))
        pen = QPen(QColor(200, 200, 200, max(0, alpha)), 1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for seg in range(3):
            y0 = my - 4 - seg * 5
            y1 = y0 - 5
            ox = int(2 * math.sin(t * 3.0 + i + seg))
            p.drawLine(sx + ox, y0, sx - ox, y1)
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

    # Keyboard base
    p.setPen(QPen(QColor(60, 60, 60), 1))
    p.setBrush(QColor(80, 80, 80))
    p.drawRoundedRect(kx, ky, kw, kh, 3, 3)

    # Keys grid
    cols, rows = 6, 2
    key_w = max(2, (kw - 6) // cols - 1)
    key_h = max(2, (kh - 6) // rows - 1)
    p.setBrush(QColor(160, 160, 160))
    p.setPen(Qt.PenStyle.NoPen)
    for row in range(rows):
        for col in range(cols):
            kx2 = kx + 3 + col * (key_w + 1)
            ky2 = ky + 3 + row * (key_h + 1)
            p.drawRoundedRect(kx2, ky2, key_w, key_h, 1, 1)

    # Animated "fingers"
    for fi in range(3):
        fx = kx + 4 + int((math.sin(t * 8.0 + fi * 1.5) * 0.5 + 0.5) * (kw - 8))
        fy = ky - 5
        p.setBrush(QColor(220, 190, 160, 180))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(fx - 3, fy, 6, 8, 2, 2)
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

    # Glow aura
    if glowing:
        glow_alpha = int(80 + 60 * math.sin(t * 4.0))
        grad = QRadialGradient(float(bx), float(by), float(br * 2.5))
        grad.setColorAt(0.0, QColor(255, 255, 100, glow_alpha))
        grad.setColorAt(1.0, QColor(255, 200, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(bx - br * 2, by - br * 2, br * 4, br * 4)

    # Bulb
    bulb_color = QColor(255, 255, 120) if glowing else QColor(200, 200, 200)
    p.setPen(QPen(QColor(80, 80, 80), 1))
    p.setBrush(bulb_color)
    p.drawEllipse(bx - br, by - br, br * 2, br * 2)

    # Base
    p.setBrush(QColor(100, 100, 100))
    p.drawRect(bx - br // 2, by + br - 2, br, br // 2)

    # Rays when glowing
    if glowing:
        p.setPen(QPen(QColor(255, 220, 0, 180), 1))
        for i in range(6):
            angle = i * math.pi / 3
            r0 = br + 2
            r1 = br + 7
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
    folder_colors = [_TAN, _BROWN, QColor(0xF5, 0xD8, 0xA8)]
    fx_base = cx + int(tw * 0.15)
    fy = cy - int(th * 0.05)
    fw = int(tw * 0.14)
    fh = int(th * 0.22)
    offsets = [int(math.sin(t * 1.2 + i * 1.2) * 6) for i in range(3)]

    for i, (fc, x_off) in enumerate(zip(folder_colors, offsets)):
        fx = fx_base + i * (fw + 2) + x_off
        # Tab
        p.setBrush(fc)
        p.setPen(QPen(QColor(80, 50, 20), 1))
        p.drawRoundedRect(fx, fy - 5, fw // 2, 6, 2, 2)
        # Body
        p.drawRect(fx, fy, fw, fh)
    p.restore()


def draw_stamp_approve(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = widget._passive_t
    cycle = t % 4.0
    stamp_x = cx + int(tw * 0.18)
    paper_y = cy + int(th * 0.15)

    # Paper
    p.setPen(QPen(QColor(200, 200, 180), 1))
    p.setBrush(QColor(250, 248, 240))
    p.drawRect(stamp_x - 4, paper_y, int(tw * 0.26), int(th * 0.16))

    # Stamp handle
    stamp_drop = min(1.0, cycle / 0.5) if cycle < 0.5 else max(0.0, 1.0 - (cycle - 0.5) / 0.3)
    sh = int(th * 0.22)
    sy = cy - int(th * 0.10) + int(stamp_drop * int(th * 0.20))
    sw = int(tw * 0.14)
    p.setPen(QPen(QColor(80, 20, 20), 1))
    p.setBrush(QColor(0x8B, 0x00, 0x00))
    p.drawRoundedRect(stamp_x, sy, sw, sh, 3, 3)

    # Ink face
    p.setBrush(QColor(0x00, 0xAA, 0x44))
    p.drawRect(stamp_x, sy + sh - 6, sw, 6)

    # "OK" text on paper after landing
    if cycle > 0.5:
        alpha = min(255, int((cycle - 0.5) / 0.3 * 255))
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

    # Body
    p.setPen(QPen(QColor(40, 40, 40), 1))
    p.setBrush(QColor(60, 60, 60))
    p.drawRoundedRect(calc_x, calc_y, cw, ch, 4, 4)

    # Display
    p.setBrush(QColor(40, 80, 40))
    disp_h = int(ch * 0.22)
    p.drawRect(calc_x + 3, calc_y + 3, cw - 6, disp_h)
    p.setPen(QColor(100, 255, 100))
    font = QFont("Courier", max(5, tw // 14), QFont.Weight.Bold)
    p.setFont(font)
    num = str(42 + int(t * 2) % 58)
    if int(t * 2) % 4 == 0:
        num = "   "
    p.drawText(calc_x + 4, calc_y + disp_h, num)

    # Buttons grid
    cols, rows = 3, 4
    btn_w = max(2, (cw - 8) // cols - 1)
    btn_h = max(2, (ch - disp_h - 12) // rows - 1)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(130, 130, 130))
    for row in range(rows):
        for col in range(cols):
            bx = calc_x + 4 + col * (btn_w + 1)
            by = calc_y + disp_h + 6 + row * (btn_h + 1)
            p.drawRoundedRect(bx, by, btn_w, btn_h, 1, 1)
    p.restore()


def draw_magnifying_glass(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    x_off = int(widget._passive_extra_x)
    mx = cx + x_off
    my = cy - int(th * 0.15)
    lr = max(7, int(tw * 0.12))

    # Lens
    p.setPen(QPen(QColor(0xC0, 0xC8, 0xD8), 3))
    p.setBrush(QColor(180, 210, 240, 80))
    p.drawEllipse(mx - lr, my - lr, lr * 2, lr * 2)

    # Handle
    p.setPen(QPen(QColor(0x80, 0x60, 0x40), 3))
    p.drawLine(mx + int(lr * 0.7), my + int(lr * 0.7),
               mx + lr + 8, my + lr + 8)

    # Inner crosshair
    p.setPen(QPen(QColor(60, 90, 130, 160), 1))
    p.drawLine(mx - lr + 3, my, mx + lr - 3, my)
    p.drawLine(mx, my - lr + 3, mx, my + lr - 3)
    p.restore()


def draw_presentation(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    board_x = cx + int(tw * 0.22)
    board_y = cy - int(th * 0.25)
    board_w = int(tw * 0.28)
    board_h = int(th * 0.28)

    # Easel legs
    p.setPen(QPen(QColor(100, 80, 60), 2))
    p.drawLine(board_x + board_w // 3, board_y + board_h,
               board_x + board_w // 4, board_y + board_h + 10)
    p.drawLine(board_x + board_w * 2 // 3, board_y + board_h,
               board_x + board_w * 3 // 4, board_y + board_h + 10)

    # Board
    p.setBrush(QColor(250, 252, 255))
    p.setPen(QPen(QColor(60, 80, 100), 2))
    p.drawRect(board_x, board_y, board_w, board_h)

    # Chart on board
    for i, bh_ratio in enumerate([0.5, 0.8, 0.6]):
        bh_px = int(board_h * 0.5 * bh_ratio)
        bw_px = max(3, board_w // 6)
        bxi = board_x + 4 + i * (bw_px + 3)
        byi = board_y + board_h - 6 - bh_px
        p.setBrush(_DARK_BLUE)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(bxi, byi, bw_px, bh_px)

    # Bullet lines
    p.setPen(QPen(QColor(80, 80, 100), 1))
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
        (cx - int(tw * 0.35), cy - int(th * 0.20), QColor(0xFF, 0xF0, 0x80, 220)),
        (cx + int(tw * 0.30), cy - int(th * 0.30), QColor(0xFF, 0xA0, 0xA0, 220)),
        (cx - int(tw * 0.25), cy + int(th * 0.15), QColor(0xA0, 0xFF, 0xA0, 220)),
        (cx + int(tw * 0.22), cy + int(th * 0.20), QColor(0xA0, 0xD0, 0xFF, 220)),
    ]
    ns = max(8, tw // 6)
    for i, (nx, ny, nc) in enumerate(note_data):
        rot = math.sin(t * 2.0 + i * 1.2) * 5.0
        p.save()
        p.translate(nx, ny)
        p.rotate(rot)
        p.setBrush(nc)
        p.setPen(QPen(QColor(160, 140, 100), 1))
        p.drawRect(-ns // 2, -ns // 2, ns, ns)
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

    # Trail
    p.setPen(QPen(QColor(160, 180, 200, 80), 1, Qt.PenStyle.DotLine))
    start_x = int(cx - tw * 0.5)
    step = max(1, int(tw * 1.0 * progress) // 8)
    for i in range(0, int(tw * 1.0 * progress), step):
        px = start_x + i
        py = cy - int(th * 0.25) - int(math.sin((i / (tw * 1.0)) * math.pi) * th * 0.18)
        p.drawPoint(px, py)

    # Airplane triangle
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(240, 240, 255))
    plane = QPainterPath()
    plane.moveTo(float(ax + 10), float(ay))
    plane.lineTo(float(ax - 4), float(ay - 5))
    plane.lineTo(float(ax - 4), float(ay + 5))
    plane.closeSubpath()
    p.fillPath(plane, QColor(240, 240, 255))
    p.setPen(QPen(QColor(100, 120, 180), 1))
    p.drawPath(plane)
    p.restore()


def draw_pencil_tap(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    tap_y = int(widget._passive_extra_y)
    px = cx + int(tw * 0.28)
    py = cy - int(th * 0.10) + tap_y
    pw = max(4, tw // 10)
    ph = int(th * 0.30)

    # Pencil body (rotated ~-20 deg)
    p.save()
    p.translate(px, py)
    p.rotate(-20)
    p.setBrush(QColor(0xFF, 0xD7, 0x00))
    p.setPen(QPen(QColor(80, 60, 20), 1))
    p.drawRect(-pw // 2, -ph // 2, pw, ph - 6)
    # Tip
    tip = QPainterPath()
    tip.moveTo(float(-pw // 2), float(ph // 2 - 6))
    tip.lineTo(float(pw // 2), float(ph // 2 - 6))
    tip.lineTo(float(0), float(ph // 2))
    tip.closeSubpath()
    p.fillPath(tip, QColor(220, 180, 120))
    # Eraser
    p.setBrush(QColor(0xF0, 0xA0, 0xA0))
    p.drawRect(-pw // 2, -ph // 2 - 5, pw, 5)
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
    p.setPen(QPen(_BROWN, 2))
    p.setBrush(_TAN)
    p.drawRoundedRect(bx, by, bw, bh, 3, 3)
    p.setBrush(QColor(0x80, 0x80, 0x80))
    p.setPen(QPen(QColor(0x50, 0x50, 0x50), 1))
    clip_w = max(4, bw // 3)
    p.drawRoundedRect(bx + (bw - clip_w) // 2, by - 4, clip_w, 7, 2, 2)
    p.setPen(QPen(QColor(0x00, 0xAA, 0x44), 2))
    for i in range(2):
        ly = by + 8 + i * 10
        p.drawLine(bx + 3, ly + 4, bx + 6, ly + 8)
        p.drawLine(bx + 6, ly + 8, bx + 11, ly)
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
    # Stamp
    sx = cx + int(tw * 0.18)
    sy = cy - int(th * 0.05)
    sw = int(tw * 0.26)
    sh = int(th * 0.08)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0x00, 0xAA, 0x44, 200))
    p.drawRoundedRect(sx, sy, sw, sh, 2, 2)
    p.setPen(QColor(255, 255, 255))
    font = QFont("Arial", max(5, tw // 14), QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(sx + 2, sy + sh - 2, "APPROVED ✓")
    # Confetti
    confetti_data = [
        (cx - int(tw * 0.25), cy - int(th * 0.20), QColor(255, 80, 80)),
        (cx + int(tw * 0.25), cy - int(th * 0.25), QColor(80, 200, 80)),
        (cx - int(tw * 0.10), cy - int(th * 0.30), QColor(80, 80, 255)),
        (cx + int(tw * 0.15), cy - int(th * 0.15), QColor(255, 200, 60)),
    ]
    for i, (confx, confy, col) in enumerate(confetti_data):
        rot = (t * 120 + i * 45) % 360
        p.save()
        p.translate(confx, confy)
        p.rotate(rot)
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(-3, -3, 6, 4)
        p.restore()
    p.restore()


def draw_state_sad(p: QPainter, widget) -> None:
    """Falling file folders while sad."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_passive_t', 0.0)
    folder_colors = [_TAN, _BROWN, QColor(0xF5, 0xD8, 0xA8)]
    for i, fc in enumerate(folder_colors):
        fall_y = int((t * 20 + i * 15) % (th * 0.6))
        rot = math.sin(t * 1.5 + i) * 15.0
        fx = cx - int(tw * 0.20) + i * int(tw * 0.15)
        fy = cy - int(th * 0.20) + fall_y
        fw = int(tw * 0.12)
        fh = int(th * 0.18)
        p.save()
        p.translate(fx + fw // 2, fy + fh // 2)
        p.rotate(rot)
        p.setBrush(fc)
        p.setPen(QPen(QColor(80, 50, 20), 1))
        p.drawRect(-fw // 2, -fh // 2, fw, fh)
        p.restore()
    p.restore()


def draw_state_sleepy(p: QPainter, widget) -> None:
    """Stack of books + ZZZ + coffee while sleepy."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_passive_t', 0.0)
    book_colors = [QColor(0x8B, 0x00, 0x00), QColor(0x00, 0x00, 0x8B), _DARK_GREEN]
    bx = cx + int(tw * 0.25)
    by = cy
    bw = int(tw * 0.20)
    bh = int(th * 0.08)
    for i, bc in enumerate(book_colors):
        p.setBrush(bc)
        p.setPen(QPen(QColor(20, 20, 20), 1))
        p.drawRect(bx, by - i * (bh + 1), bw, bh)

    # ZZZ
    zzz_data = [(bx + 4, by - int(th * 0.25) - j * 8, max(6, tw // 10) - j) for j in range(3)]
    for i, (zx, zy, zs) in enumerate(zzz_data):
        alpha = int(180 - i * 40)
        p.setPen(QColor(210, 210, 255, alpha))
        font = QFont("Arial", zs, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(zx + i * 4, zy, "Z")

    # Coffee cup
    mx = bx - int(tw * 0.28)
    my = by - int(th * 0.05)
    mw = int(tw * 0.14)
    mh = int(th * 0.16)
    p.setPen(QPen(_COFFEE, 1))
    p.setBrush(QColor(255, 255, 255))
    p.drawRoundedRect(mx, my, mw, mh, 3, 3)
    p.setBrush(_COFFEE)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(mx + 2, my + 2, mw - 4, int(mh * 0.3))
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
        p.setBrush(QColor(255, 255, 240))
        p.setPen(QPen(QColor(180, 180, 160), 1))
        p.drawRect(-6, -8, 12, 16)
        p.restore()
    # Exclamation
    p.setPen(QColor(255, 60, 20))
    font = QFont("Arial Black", max(8, tw // 7), QFont.Weight.Black)
    p.setFont(font)
    p.drawText(cx - 4, cy - int(th * 0.45), "!")
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
    # Left page
    p.save()
    p.translate(bx, by + bh // 2)
    p.rotate(-open_angle)
    p.setBrush(_BEIGE)
    p.setPen(QPen(QColor(80, 50, 20), 1))
    p.drawRect(0, -bh // 2, -bw, bh)
    p.restore()
    # Right page
    p.save()
    p.translate(bx, by + bh // 2)
    p.rotate(open_angle)
    p.setBrush(QColor(0xF0, 0xEB, 0xD5))
    p.setPen(QPen(QColor(80, 50, 20), 1))
    p.drawRect(0, -bh // 2, bw, bh)
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

    # Strong glow
    grad = QRadialGradient(float(bx), float(by), float(br * 3))
    grad.setColorAt(0.0, QColor(255, 255, 120, 180))
    grad.setColorAt(1.0, QColor(255, 200, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawEllipse(bx - br * 3, by - br * 3, br * 6, br * 6)

    # Bulb
    p.setPen(QPen(QColor(80, 80, 80), 2))
    p.setBrush(QColor(255, 255, 120))
    p.drawEllipse(bx - br, by - br, br * 2, br * 2)

    # Rays
    p.setPen(QPen(QColor(255, 220, 0, 200), 2))
    for i in range(8):
        angle = i * math.pi / 4 + t * 2.0
        p.drawLine(
            bx + int(math.cos(angle) * (br + 3)),
            by + int(math.sin(angle) * (br + 3)),
            bx + int(math.cos(angle) * (br + 10)),
            by + int(math.sin(angle) * (br + 10)),
        )

    # Floating note icons
    for i in range(3):
        nx = cx + int(math.cos(t * 1.5 + i * 2.1) * tw * 0.25)
        ny = by + int(math.sin(t * 1.5 + i * 2.1) * th * 0.12) - 8
        p.setBrush(QColor(255, 250, 200, 180))
        p.setPen(QPen(QColor(150, 130, 80), 1))
        p.drawRect(nx - 4, ny - 5, 8, 10)
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

    p.setBrush(QColor(240, 242, 248))
    p.setPen(QPen(QColor(180, 180, 190), 1))
    p.drawRect(chart_x, chart_y, chart_w, chart_h)

    bar_heights = [0.4, 0.6, 0.75, 0.9]
    bw = max(3, (chart_w - 10) // (len(bar_heights) * 2))
    grow = min(1.0, t / 1.5)
    for i, bh_r in enumerate(bar_heights):
        bh_px = int((chart_h - 8) * bh_r * grow)
        bxi = chart_x + 5 + i * (bw + 4)
        p.setBrush(_DARK_BLUE)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(bxi, chart_y + chart_h - 4 - bh_px, bw, bh_px)

    # Rising arrow
    if t > 1.0:
        arrow_x = chart_x + chart_w - 12
        arrow_y = chart_y + int(chart_h * (1.0 - min(1.0, (t - 1.0) / 1.0)))
        p.setPen(QPen(QColor(0, 200, 80), 2))
        p.drawLine(arrow_x, arrow_y + 10, arrow_x, chart_y + 4)
        p.drawLine(arrow_x - 4, chart_y + 8, arrow_x, chart_y + 4)
        p.drawLine(arrow_x + 4, chart_y + 8, arrow_x, chart_y + 4)

    # LEVEL UP text
    if t > 2.0:
        p.setPen(QColor(0, 180, 60))
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

    # Folder/paper
    p.setBrush(_TAN)
    p.setPen(QPen(_BROWN, 1))
    p.drawRect(sx, paper_y, sw, int(th * 0.16))

    # Stamp descending
    p.setBrush(QColor(0x22, 0x8B, 0x22))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(sx + sw // 4, stamp_y, sw // 2, stamp_h, 3, 3)

    if t > 0.5:
        alpha = min(255, int((t - 0.5) / 0.4 * 255))
        p.setPen(QColor(255, 255, 255, alpha))
        font = QFont("Arial", max(6, tw // 12), QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(sx + sw // 4 + 2, paper_y + int(th * 0.12), "COMPLETE ✓")

        # Impact lines
        if t < 1.0:
            p.setPen(QPen(QColor(0, 180, 60, 200), 1))
            for i in range(4):
                angle = i * math.pi / 2
                p.drawLine(
                    sx + sw // 2 + int(math.cos(angle) * 8),
                    paper_y + int(math.sin(angle) * 8),
                    sx + sw // 2 + int(math.cos(angle) * 16),
                    paper_y + int(math.sin(angle) * 16),
                )
    p.restore()


def draw_event_red_pen(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    # Paper
    px = cx - int(tw * 0.18)
    py = cy - int(th * 0.10)
    pw = int(tw * 0.36)
    ph = int(th * 0.24)
    p.setBrush(QColor(250, 248, 240))
    p.setPen(QPen(QColor(180, 180, 160), 1))
    p.drawRect(px, py, pw, ph)

    # X mark growing across document
    x_progress = min(1.0, t / 1.5)
    x_len = int(pw * x_progress)
    p.setPen(QPen(QColor(220, 20, 20), 3))
    p.drawLine(px + 4, py + 4, px + 4 + x_len, py + int(ph * x_progress * 0.8))
    if t > 1.0:
        x2_progress = min(1.0, (t - 1.0) / 1.0)
        x2_len = int(pw * x2_progress)
        p.drawLine(px + pw - 4, py + 4, px + pw - 4 - x2_len, py + int(ph * x2_progress * 0.8))

    # Pen
    pen_x = cx + int(tw * 0.22)
    pen_y = cy - int(th * 0.12)
    p.save()
    p.translate(pen_x, pen_y)
    p.rotate(-35)
    p.setBrush(QColor(220, 30, 30))
    p.setPen(QPen(QColor(120, 0, 0), 1))
    p.drawRect(-3, -12, 6, 22)
    tip = QPainterPath()
    tip.moveTo(-3.0, 10.0)
    tip.lineTo(3.0, 10.0)
    tip.lineTo(0.0, 15.0)
    tip.closeSubpath()
    p.fillPath(tip, QColor(200, 200, 160))
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

    # Large mug
    p.setPen(QPen(_COFFEE, 2))
    p.setBrush(QColor(255, 255, 255))
    p.drawRoundedRect(mx, my, mw, mh, 6, 6)
    p.setBrush(_COFFEE)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(mx + 3, my + 4, mw - 6, int(mh * 0.45))
    p.setPen(QPen(_COFFEE, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(mx + mw - 4, my + mh // 4, 12, mh // 2, -90 * 16, 180 * 16)

    # Exaggerated steam swirls
    for i in range(4):
        sx = mx + 4 + i * (mw // 4)
        alpha = int(150 + 80 * math.sin(t * 3.0 + i))
        p.setPen(QPen(QColor(220, 220, 220, max(0, alpha)), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for seg in range(4):
            y0 = my - 6 - seg * 7
            amp = 4 + seg
            ox = int(amp * math.sin(t * 2.5 + i + seg * 0.8))
            p.drawLine(sx + ox, y0, sx - ox, y0 - 7)
    p.restore()


def draw_event_deep_research(p: QPainter, widget) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy, tw, th, pad = _trophy_center(widget)
    t = getattr(widget, '_trophie_event_anim_t', 0.0)
    x_off = int(widget._passive_extra_x)

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
    mx = cx + x_off
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
