"""
profile_card.py – Renders a Steam/Tekken-style showcase profile card using QPainter.

Public API:
    render_profile_card(data: dict) -> QImage
    save_profile_card(img: QImage, path: str) -> bool
"""

from __future__ import annotations

import math
from datetime import date

try:
    from PyQt6.QtGui import (
        QImage, QPainter, QColor, QFont, QFontMetrics,
        QPen, QBrush, QLinearGradient, QRadialGradient, QPixmap,
    )
    from PyQt6.QtCore import Qt, QRect, QPoint, QRectF
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CARD_W = 800
CARD_H = 450

HEADER_H = 80
STATS_H = 56
BADGES_H = 34
FOOTER_H = 26

# Rank emblem layout constants
RANK_EMBLEM_X = 12
RANK_EMBLEM_ICON_Y_OFFSET = -8   # relative to HEADER_H (overlaps banner bottom)
RANK_EMBLEM_W = 60
RANK_EMBLEM_ICON_H = 52
RANK_EMBLEM_LABEL_Y_OFFSET = 42  # relative to HEADER_H
RANK_EMBLEM_LABEL_W = 82
RANK_EMBLEM_LABEL_H = 14

# ---------------------------------------------------------------------------
# Rank system
# ---------------------------------------------------------------------------
_RANKS = [
    (0.0,  0.10, "🥉", "Rookie"),
    (0.10, 0.25, "🥈", "Regular"),
    (0.25, 0.50, "🥇", "Pro"),
    (0.50, 0.75, "💎", "Wizard"),
    (0.75, 1.01, "👑", "Grand Champion"),
]


def _get_rank(pct: float) -> tuple[str, str]:
    for lo, hi, icon, label in _RANKS:
        if lo <= pct < hi:
            return icon, label
    return "👑", "Grand Champion"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _draw_text(painter: "QPainter", x: int, y: int, w: int, h: int,
               text: str, font: "QFont", color: "QColor",
               align=None) -> None:
    if align is None:
        try:
            align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        except Exception:
            align = 0x0001 | 0x0080
    painter.setFont(font)
    painter.setPen(QPen(color))
    painter.drawText(QRect(x, y, w, h), align, text)


def _hex_to_qcolor(hex_str: str, alpha: int = 255) -> "QColor":
    try:
        c = QColor(hex_str)
        c.setAlpha(alpha)
        return c
    except Exception:
        return QColor(0, 229, 255, alpha)


def render_profile_card(data: dict) -> "QImage":
    """
    Render an 800×450 Steam/Tekken-style showcase profile card and return a QImage.

    Expected keys in *data* (all optional – missing values show placeholders):
        player_name, player_id, level, prestige_display,
        total_achievements (int), completion_pct (float 0-1),
        badges (list of dicts with 'icon'), total_playtime_sec (int),
        tables_played (int), top_tables (list of dicts with 'name', 'rom', 'pct'),
        challenge_records (dict with 'timed_best', 'flip_best', 'heat_best'),
        theme_colors (dict with 'primary', 'accent', 'border', 'bg'),
        version (str)
    """
    if not _QT_AVAILABLE:
        return QImage()

    img = QImage(CARD_W, CARD_H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    try:
        _render_card_contents(painter, data)
    except Exception:
        pass
    finally:
        painter.end()

    return img


def _render_card_contents(painter: "QPainter", data: dict) -> None:
    # ---- Theme colours ---------------------------------------------------
    tc = data.get("theme_colors") or {}
    primary_hex = tc.get("primary", "#00E5FF")
    accent_hex = tc.get("accent", "#FF7F00")
    border_hex = tc.get("border", "#00E5FF")
    bg_hex = tc.get("bg", "#080C16")

    primary_color = _hex_to_qcolor(primary_hex)
    accent_color = _hex_to_qcolor(accent_hex)
    border_color = _hex_to_qcolor(border_hex)

    try:
        bg_base = QColor(bg_hex)
    except Exception:
        bg_base = QColor(8, 12, 22)

    text_primary = QColor(230, 230, 230)
    text_dim = QColor(150, 150, 160)
    gold = QColor(255, 215, 0)

    # ---- 1. Background (dark gradient + DMD dot texture) -----------------
    bg_light = QColor(
        min(255, bg_base.red() + 20),
        min(255, bg_base.green() + 18),
        min(255, bg_base.blue() + 30),
    )
    grad_bg = QLinearGradient(0, 0, 0, CARD_H)
    grad_bg.setColorAt(0.0, bg_base)
    grad_bg.setColorAt(1.0, bg_light)
    painter.fillRect(0, 0, CARD_W, CARD_H, QBrush(grad_bg))

    # DMD dot-matrix texture
    dot_color = QColor(255, 255, 255, 8)
    painter.setPen(QPen(dot_color, 1.0))
    dot_step = 6
    for dy in range(0, CARD_H, dot_step):
        for dx in range(0, CARD_W, dot_step):
            painter.drawPoint(dx, dy)

    # ---- 2. Neon glow border (multi-layer) --------------------------------
    for thickness, alpha in [(6, 30), (4, 55), (2, 130), (1, 220)]:
        glow = _hex_to_qcolor(border_hex, alpha)
        painter.setPen(QPen(glow, thickness))
        offset = thickness // 2
        painter.drawRect(offset, offset, CARD_W - thickness, CARD_H - thickness)

    # ---- 3. Header banner (top HEADER_H px) --------------------------------
    banner_bg = QColor(
        border_color.red(), border_color.green(), border_color.blue(), 45
    )
    grad_hdr = QLinearGradient(0, 0, CARD_W, HEADER_H)
    grad_hdr.setColorAt(0.0, banner_bg)
    grad_hdr.setColorAt(0.60, QColor(border_color.red(), border_color.green(), border_color.blue(), 20))
    grad_hdr.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.fillRect(0, 0, CARD_W, HEADER_H, QBrush(grad_hdr))

    # Header top and bottom glow lines
    for alpha in (160, 80):
        line_pen = QPen(_hex_to_qcolor(border_hex, alpha), 1)
        painter.setPen(line_pen)
        painter.drawLine(0, HEADER_H - 1, CARD_W, HEADER_H - 1)

    # ---- 4. Player name (header left) ------------------------------------
    player_name = str(data.get("player_name") or "Player")
    f_name = QFont("Segoe UI", 20, QFont.Weight.Bold)
    _draw_text(painter, 14, 10, CARD_W // 2, 34, player_name,
               f_name, text_primary,
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # ---- 5. Level badge + prestige stars (header right) ------------------
    level = int(data.get("level") or 1)
    prestige_display = str(data.get("prestige_display") or "☆☆☆☆☆")
    f_level = QFont("Segoe UI", 11, QFont.Weight.Bold)
    _draw_text(painter, CARD_W // 2, 10, CARD_W // 2 - 14, 30,
               f"Level {level}",
               f_level, accent_color,
               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    f_stars = QFont("Segoe UI", 11)
    _draw_text(painter, CARD_W // 2, 40, CARD_W // 2 - 14, 28,
               prestige_display, f_stars, gold,
               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    # ---- 6. Rank emblem (overlapping header, left side) ------------------
    completion_pct = float(data.get("completion_pct") or 0.0)
    rank_icon, rank_label = _get_rank(completion_pct)
    f_rank_icon = QFont("Segoe UI", 28)
    _draw_text(painter,
               RANK_EMBLEM_X, HEADER_H + RANK_EMBLEM_ICON_Y_OFFSET,
               RANK_EMBLEM_W, RANK_EMBLEM_ICON_H,
               rank_icon, f_rank_icon, text_primary,
               Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    f_rank_label = QFont("Segoe UI", 7)
    _draw_text(painter,
               0, HEADER_H + RANK_EMBLEM_LABEL_Y_OFFSET,
               RANK_EMBLEM_LABEL_W, RANK_EMBLEM_LABEL_H,
               rank_label, f_rank_label, text_dim,
               Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

    # ---- 7. Featured Stats Row (below header) ----------------------------
    total_ach = int(data.get("total_achievements") or 0)
    tables_played = int(data.get("tables_played") or 0)
    playtime_sec = int(data.get("total_playtime_sec") or 0)
    hours = playtime_sec // 3600
    minutes = (playtime_sec % 3600) // 60
    playtime_str = f"{hours}h {minutes:02d}m"
    completion_str = f"{completion_pct * 100:.1f}%"

    stats = [
        ("🏆", "Achievements", str(total_ach)),
        ("🕐", "Playtime",     playtime_str),
        ("🎲", "Tables",       str(tables_played)),
        ("⭐", "Completion",   completion_str),
    ]

    stats_y = HEADER_H + 8
    stat_box_w = (CARD_W - 28) // 4
    f_stat_val = QFont("Segoe UI", 12, QFont.Weight.Bold)
    f_stat_lbl = QFont("Segoe UI", 7)

    for i, (icon, label, value) in enumerate(stats):
        bx = 14 + i * stat_box_w
        box_rect = QRect(bx, stats_y, stat_box_w - 4, STATS_H - 4)
        # subtle stat box background
        box_bg = QColor(border_color.red(), border_color.green(), border_color.blue(), 18)
        painter.fillRect(box_rect, QBrush(box_bg))
        box_border = _hex_to_qcolor(border_hex, 60)
        painter.setPen(QPen(box_border, 1))
        painter.drawRect(box_rect)
        # value
        _draw_text(painter, bx + 2, stats_y + 2, stat_box_w - 8, 24,
                   f"{icon} {value}", f_stat_val, accent_color,
                   Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        # label
        _draw_text(painter, bx + 2, stats_y + 26, stat_box_w - 8, 16, label,
                   f_stat_lbl, text_dim,
                   Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

    # ---- 8. Showcase Section divider ------------------------------------
    showcase_y = HEADER_H + STATS_H + 16
    painter.setPen(QPen(QColor(60, 60, 70), 1))
    painter.drawLine(14, showcase_y - 2, CARD_W - 14, showcase_y - 2)

    col_w = (CARD_W - 28) // 2
    left_x = 14
    right_x = left_x + col_w + 4

    f_sec = QFont("Segoe UI", 8, QFont.Weight.Bold)
    f_tbl = QFont("Segoe UI", 7)

    # ---- 9. Left column: Top Tables ------------------------------------
    tbl_y = showcase_y
    _draw_text(painter, left_x, tbl_y, col_w, 16, "🏅 Top Tables",
               f_sec, primary_color,
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    tbl_y += 18
    top_tables = data.get("top_tables") or []
    bar_w_max = col_w - 50

    for i, tbl in enumerate(top_tables[:3]):
        name = str(tbl.get("name") or f"Table {i+1}")
        rom = str(tbl.get("rom") or "")
        pct = float(tbl.get("pct") or 0)
        if rom and rom.lower() != name.lower():
            combined = f"{name} ({rom})"
        else:
            combined = name
        fm = QFontMetrics(f_tbl)
        combined = fm.elidedText(combined, Qt.TextElideMode.ElideRight, bar_w_max)
        _draw_text(painter, left_x, tbl_y, bar_w_max, 14, f"{i+1}. {combined}",
                   f_tbl, text_primary,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        _draw_text(painter, left_x + col_w - 44, tbl_y, 42, 14, f"{pct:.0f}%",
                   f_tbl, accent_color,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tbl_y += 14
        # progress bar
        bar_h = 5
        bar_bg = QColor(50, 50, 60)
        painter.fillRect(left_x, tbl_y, bar_w_max, bar_h, QBrush(bar_bg))
        filled_w = max(1, int(bar_w_max * min(1.0, pct / 100.0)))
        bar_grad = QLinearGradient(left_x, 0, left_x + bar_w_max, 0)
        bar_grad.setColorAt(0.0, primary_color)
        bar_grad.setColorAt(1.0, accent_color)
        painter.fillRect(left_x, tbl_y, filled_w, bar_h, QBrush(bar_grad))
        tbl_y += bar_h + 6

    # ---- 10. Right column: Challenge Records ----------------------------
    chal_y = showcase_y
    _draw_text(painter, right_x, chal_y, col_w, 16, "🎯 Challenge Records",
               f_sec, primary_color,
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    chal_y += 18
    records = data.get("challenge_records") or {}
    record_items = [
        ("⏱️", "Timed",  str(records.get("timed_best", "—"))),
        ("🔄", "Flip",   str(records.get("flip_best", "—"))),
        ("🌡️", "Heat",   str(records.get("heat_best", "—"))),
    ]
    for icon, label, value in record_items:
        _draw_text(painter, right_x, chal_y, 80, 14, f"{icon} {label}",
                   f_tbl, text_dim,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        _draw_text(painter, right_x + 80, chal_y, col_w - 84, 14, value,
                   f_tbl, accent_color,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        chal_y += 22

    # ---- 11. Badge Collection Row ----------------------------------------
    badges_y = CARD_H - BADGES_H - FOOTER_H - 6
    painter.setPen(QPen(QColor(50, 50, 60), 1))
    painter.drawLine(14, badges_y - 2, CARD_W - 14, badges_y - 2)

    badges = data.get("badges") or []
    f_badge = QFont("Segoe UI", 11)
    badge_x = 14
    max_badges = 10
    display_badges = badges[:max_badges]
    badge_slot_w = 28
    for badge in display_badges:
        icon = str(badge.get("icon") if isinstance(badge, dict) else badge or "🎖️")
        _draw_text(painter, badge_x, badges_y, badge_slot_w, BADGES_H - 4,
                   icon, f_badge, text_primary,
                   Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        badge_x += badge_slot_w

    if len(badges) > max_badges:
        extra = len(badges) - max_badges
        f_extra = QFont("Segoe UI", 7)
        _draw_text(painter, badge_x + 2, badges_y, 40, BADGES_H - 4,
                   f"+{extra}", f_extra, text_dim,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # ---- 12. Footer ------------------------------------------------------
    footer_y = CARD_H - FOOTER_H
    footer_line = _hex_to_qcolor(border_hex, 80)
    painter.setPen(QPen(footer_line, 1))
    painter.drawLine(14, footer_y, CARD_W - 14, footer_y)

    player_id = str(data.get("player_id") or "")
    today_str = date.today().strftime("%Y-%m-%d")
    version = str(data.get("version") or "")
    branding = f"VPX Achievement Watcher{('  ' + version) if version else ''}"

    f_footer = QFont("Segoe UI", 6)
    _draw_text(painter, 14, footer_y + 2, 180, FOOTER_H - 4, player_id,
               f_footer, text_dim,
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    _draw_text(painter, 0, footer_y + 2, CARD_W, FOOTER_H - 4, today_str,
               f_footer, text_dim,
               Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    _draw_text(painter, 14, footer_y + 2, CARD_W - 28, FOOTER_H - 4, branding,
               f_footer, text_dim,
               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


def save_profile_card(img: "QImage", path: str) -> bool:
    """Save *img* to *path* as PNG. Returns True on success."""
    if not _QT_AVAILABLE:
        return False
    try:
        return img.save(path, "PNG")
    except Exception:
        return False
