"""
Profile Card renderer for VPX Achievement Watcher.
Generates a shareable PNG image with player stats.
"""

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QImage, QColor, QFont, QPen, QLinearGradient
import os


def render_profile_card(
    player_name: str,
    level: int,
    level_name: str,
    prestige: int,
    prestige_display: str,
    total_achievements: int,
    badge_count: int,
    total_badges: int,
    total_playtime_sec: int,
    tables_played: int,
    top_tables: list,  # list of dicts: [{"name": "...", "pct": 92, "score": "156M"}, ...]
    challenge_records: dict,  # {"timed": "45.2M", "flip": "12.8M", "heat": "8"}
    theme_colors: dict,  # {"primary": "#00E5FF", "accent": "#FF7F00", "border": "#00E5FF", "bg": "#080C16"}
    watcher_version: str = "",
) -> QImage:
    """Render a profile card as QImage (800x600)."""

    W, H = 800, 600
    img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(theme_colors.get("bg", "#080C16")))

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    primary = QColor(theme_colors.get("primary", "#00E5FF"))
    accent = QColor(theme_colors.get("accent", "#FF7F00"))
    border = QColor(theme_colors.get("border", "#00E5FF"))
    white = QColor("#FFFFFF")
    gray = QColor("#888888")

    # Border
    pen = QPen(border, 3)
    p.setPen(pen)
    p.drawRoundedRect(2, 2, W - 4, H - 4, 16, 16)

    # Header: Player name + level
    p.setPen(accent)
    p.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
    p.drawText(QRect(30, 20, W - 60, 40), Qt.AlignmentFlag.AlignLeft, f"🎮 {player_name}")

    p.setPen(primary)
    p.setFont(QFont("Segoe UI", 14))
    p.drawText(QRect(30, 65, W - 60, 25), Qt.AlignmentFlag.AlignLeft,
               f"Level {level} – {level_name}  {prestige_display}")

    # Divider
    p.setPen(QPen(border, 1))
    p.drawLine(30, 100, W - 30, 100)

    # Stats section
    p.setPen(white)
    p.setFont(QFont("Segoe UI", 12))
    h_total = total_playtime_sec // 3600
    m_total = (total_playtime_sec % 3600) // 60
    playtime_str = f"{h_total}h {m_total:02d}m"

    stats_y = 115
    stats = [
        f"Playtime: {playtime_str}",
        f"Achievements: {total_achievements}",
        f"Badges: {badge_count}/{total_badges}",
        f"Tables Played: {tables_played}",
    ]
    for i, s in enumerate(stats):
        col = 0 if i < 2 else 1
        row = i % 2
        x = 30 + col * 380
        y = stats_y + row * 28
        p.drawText(QRect(x, y, 360, 25), Qt.AlignmentFlag.AlignLeft, s)

    # Divider
    p.setPen(QPen(border, 1))
    p.drawLine(30, 180, W - 30, 180)

    # Top 3 tables
    p.setPen(accent)
    p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
    p.drawText(QRect(30, 190, W - 60, 25), Qt.AlignmentFlag.AlignLeft, "🏅 TOP 3 TABLES")

    medals = ["🥇", "🥈", "🥉"]
    p.setPen(white)
    p.setFont(QFont("Segoe UI", 11))
    for i, t in enumerate(top_tables[:3]):
        y = 220 + i * 28
        name = t.get("name", "—")
        pct = t.get("pct", 0)
        score = t.get("score", "—")
        p.drawText(QRect(30, y, W - 60, 25), Qt.AlignmentFlag.AlignLeft,
                   f"  {medals[i]}  {name}    {pct}%  |  {score}")

    # Divider
    p.setPen(QPen(border, 1))
    p.drawLine(30, 310, W - 30, 310)

    # Challenge records
    p.setPen(accent)
    p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
    p.drawText(QRect(30, 320, W - 60, 25), Qt.AlignmentFlag.AlignLeft, "⚔️ CHALLENGE RECORDS")

    p.setPen(white)
    p.setFont(QFont("Segoe UI", 11))
    ch_text = (
        f"  Timed: {challenge_records.get('timed', '—')}  |  "
        f"Flip: {challenge_records.get('flip', '—')}  |  "
        f"Heat: {challenge_records.get('heat', '—')}"
    )
    p.drawText(QRect(30, 350, W - 60, 25), Qt.AlignmentFlag.AlignLeft, ch_text)

    # Footer
    p.setPen(gray)
    p.setFont(QFont("Segoe UI", 9))
    footer = f"VPX Achievement Watcher {watcher_version}"
    p.drawText(QRect(30, H - 40, W - 60, 25), Qt.AlignmentFlag.AlignCenter, footer)

    p.end()
    return img


def save_profile_card(img: QImage, path: str) -> bool:
    """Save QImage to PNG file. Returns True on success."""
    try:
        return img.save(path, "PNG")
    except Exception:
        return False
