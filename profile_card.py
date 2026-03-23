"""
profile_card.py – Renders a compact business-card-style profile card image using QPainter.

Public API:
    render_profile_card(data: dict) -> QImage
    save_profile_card(img: QImage, path: str) -> bool
"""

from __future__ import annotations

try:
    from PyQt6.QtGui import (
        QImage, QPainter, QColor, QFont, QFontMetrics,
        QPen, QBrush, QLinearGradient, QPixmap,
    )
    from PyQt6.QtCore import Qt, QRect, QPoint
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CARD_W = 600
CARD_H = 360


def _draw_text(painter: "QPainter", x: int, y: int, w: int, h: int,
               text: str, font: "QFont", color: "QColor",
               align=None) -> None:
    if align is None:
        try:
            align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        except Exception:
            align = 0x0001 | 0x0080  # AlignLeft | AlignVCenter fallback
    painter.setFont(font)
    painter.setPen(QPen(color))
    painter.drawText(QRect(x, y, w, h), align, text)


def render_profile_card(data: dict) -> "QImage":
    """
    Render a compact 600×360 business-card-style profile card and return a QImage.

    Expected keys in *data* (all optional – missing values show placeholders):
        player_name, level, prestige_display, total_achievements (int),
        badges (list), total_playtime_sec (int), tables_played (int),
        top_tables (list of dicts with 'name', 'rom' and 'pct'),
        challenge_records (dict), theme_colors (dict with 'border', 'accent'),
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
    # ---- Colours --------------------------------------------------------
    tc = data.get("theme_colors") or {}
    border_hex = tc.get("border", "#00E5FF")
    accent_hex = tc.get("accent", "#FF7F00")
    try:
        border_color = QColor(border_hex)
        accent_color = QColor(accent_hex)
    except Exception:
        border_color = QColor("#00E5FF")
        accent_color = QColor("#FF7F00")

    bg_dark = QColor(15, 15, 20)
    bg_mid = QColor(25, 25, 35)
    text_primary = QColor(230, 230, 230)
    text_dim = QColor(150, 150, 160)
    gold = QColor(255, 215, 0)

    # ---- Background -----------------------------------------------------
    grad = QLinearGradient(0, 0, 0, CARD_H)
    grad.setColorAt(0.0, bg_dark)
    grad.setColorAt(1.0, bg_mid)
    painter.fillRect(0, 0, CARD_W, CARD_H, QBrush(grad))

    # ---- Border ---------------------------------------------------------
    border_pen = QPen(border_color, 2)
    painter.setPen(border_pen)
    painter.drawRect(1, 1, CARD_W - 2, CARD_H - 2)

    # ---- Header band ----------------------------------------------------
    header_h = 62
    header_grad = QLinearGradient(0, 0, CARD_W, 0)
    header_grad.setColorAt(0.0, QColor(border_color.red(), border_color.green(), border_color.blue(), 40))
    header_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.fillRect(0, 0, CARD_W, header_h, QBrush(header_grad))

    # ---- Player name ----------------------------------------------------
    player_name = str(data.get("player_name") or "Player")
    f_name = QFont("Segoe UI", 18, QFont.Weight.Bold)
    _draw_text(painter, 12, 8, CARD_W - 24, 32, player_name,
               f_name, text_primary,
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # ---- Level ----------------------------------------------------------
    level = int(data.get("level") or 1)
    prestige_display = str(data.get("prestige_display") or "☆☆☆☆☆")
    level_text = f"Level {level}"
    f_level = QFont("Segoe UI", 10)
    _draw_text(painter, 12, 40, 200, 20, level_text,
               f_level, accent_color,
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # ---- Prestige stars -------------------------------------------------
    f_stars = QFont("Segoe UI", 10)
    _draw_text(painter, 12, 40, CARD_W - 24, 20, prestige_display,
               f_stars, gold,
               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    # ---- Divider --------------------------------------------------------
    painter.setPen(QPen(border_color, 1))
    painter.drawLine(12, header_h, CARD_W - 12, header_h)

    # ---- Stats row ------------------------------------------------------
    total_ach = int(data.get("total_achievements") or 0)
    badge_count = len(data.get("badges") or [])
    tables_played = int(data.get("tables_played") or 0)
    playtime_sec = int(data.get("total_playtime_sec") or 0)
    hours = playtime_sec // 3600
    minutes = (playtime_sec % 3600) // 60
    playtime_str = f"{hours}h {minutes:02d}m"

    stats = [
        ("🏆", "Achievements", str(total_ach)),
        ("🎖️", "Badges", str(badge_count)),
        ("🎲", "Played Tables", str(tables_played)),
        ("⏱️", "Playtime", playtime_str),
    ]
    stat_y = header_h + 8
    stat_w = (CARD_W - 24) // len(stats)
    f_stat_val = QFont("Segoe UI", 12, QFont.Weight.Bold)
    f_stat_lbl = QFont("Segoe UI", 7)
    for i, (icon, label, value) in enumerate(stats):
        sx = 12 + i * stat_w
        _draw_text(painter, sx, stat_y, stat_w, 20, f"{icon} {value}",
                   f_stat_val, text_primary,
                   Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        _draw_text(painter, sx, stat_y + 20, stat_w, 14, label,
                   f_stat_lbl, text_dim,
                   Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

    # ---- Divider --------------------------------------------------------
    section_y = header_h + 48
    painter.setPen(QPen(QColor(60, 60, 70), 1))
    painter.drawLine(12, section_y, CARD_W - 12, section_y)

    # ---- Top 3 tables ---------------------------------------------------
    top_tables = data.get("top_tables") or []
    col_left = 12
    col_w = (CARD_W // 2) - 18

    f_sec = QFont("Segoe UI", 8, QFont.Weight.Bold)
    f_tbl = QFont("Segoe UI", 7)

    tbl_y = section_y + 8
    _draw_text(painter, col_left, tbl_y, col_w, 16, "🏅 Top Tables",
               f_sec, border_color,
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    tbl_y += 18
    for i, tbl in enumerate(top_tables[:3]):
        name = str(tbl.get("name") or f"Table {i+1}")
        rom = str(tbl.get("rom") or "")
        pct = float(tbl.get("pct") or 0)
        # Build combined label: "Table Name (rom)" or just the name if no rom
        if rom and rom.lower() != name.lower():
            combined = f"{name} ({rom})"
        else:
            combined = name
        # truncate long combined labels
        fm = QFontMetrics(f_tbl)
        max_w = col_w - 42
        combined = fm.elidedText(combined, Qt.TextElideMode.ElideRight, max_w)
        row_text = f"{i+1}. {combined}"
        _draw_text(painter, col_left, tbl_y, col_w - 42, 15, row_text,
                   f_tbl, text_primary,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        pct_text = f"{pct:.0f}%"
        _draw_text(painter, col_left + col_w - 42, tbl_y, 38, 15, pct_text,
                   f_tbl, accent_color,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tbl_y += 16

    # ---- Challenge records ----------------------------------------------
    chal_x = CARD_W // 2 + 6
    chal_w = CARD_W // 2 - 18
    chal_y = section_y + 8
    _draw_text(painter, chal_x, chal_y, chal_w, 16, "🎯 Challenge Records",
               f_sec, border_color,
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    chal_y += 18
    records = data.get("challenge_records") or {}
    record_items = [
        ("⏱️ Timed", records.get("timed_best", "—")),
        ("🔄 Flip", records.get("flip_best", "—")),
        ("🌡️ Heat", records.get("heat_best", "—")),
    ]
    for label, value in record_items:
        _draw_text(painter, chal_x, chal_y, chal_w - 60, 15, label,
                   f_tbl, text_dim,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        _draw_text(painter, chal_x + chal_w - 60, chal_y, 58, 15, str(value),
                   f_tbl, text_primary,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        chal_y += 16

    # ---- Bottom divider -------------------------------------------------
    footer_y = CARD_H - 22
    painter.setPen(QPen(QColor(50, 50, 60), 1))
    painter.drawLine(12, footer_y, CARD_W - 12, footer_y)

    # ---- Version footer -------------------------------------------------
    version = str(data.get("version") or "")
    f_footer = QFont("Segoe UI", 6)
    footer_text = f"VPX Achievement Watcher  {version}"
    _draw_text(painter, 12, footer_y + 3, CARD_W - 24, 16, footer_text,
               f_footer, text_dim,
               Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)


def save_profile_card(img: "QImage", path: str) -> bool:
    """Save *img* to *path* as PNG. Returns True on success."""
    if not _QT_AVAILABLE:
        return False
    try:
        return img.save(path, "PNG")
    except Exception:
        return False
