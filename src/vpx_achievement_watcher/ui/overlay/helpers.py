from __future__ import annotations

import os
import re
import json
import sys
import math
import random

from typing import Optional

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QObject, QPoint, QEventLoop
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QTransform, QPixmap,
    QPainter, QImage, QPen, QLinearGradient, QBrush,
)

from watcher_core import APP_DIR, register_raw_input_for_window

def _draw_glow_border(painter: QPainter, x: int, y: int, w: int, h: int,
                      radius: int = 18, color: QColor = None, layers: int = 3,
                      low_perf: bool = False):
    """Draw a multi-layer neon glow border for a modern sci-fi look."""
    if color is None:
        color = QColor("#00E5FF")
    if not low_perf:
        # Outer glow layers
        for i in range(layers, 0, -1):
            alpha = int(30 * (layers + 1 - i))
            glow_pen = QPen(QColor(color.red(), color.green(), color.blue(), alpha))
            glow_pen.setWidth(i * 2)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(x + i, y + i, w - 2 * i, h - 2 * i, radius, radius)
    # Sharp inner border
    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(x + 1, y + 1, w - 2, h - 2, radius, radius)


def _ease_out_bounce(t: float) -> float:
    """Ease-out bounce curve used for icon stamp animation."""
    if t < 1 / 2.75:
        return 7.5625 * t * t
    elif t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    elif t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    else:
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375


def _ease_out_cubic(t: float) -> float:
    """Ease-out cubic curve used for slide transitions."""
    return 1.0 - (1.0 - t) ** 3


def _force_topmost(widget: QWidget):
    """Force a widget to the topmost z-order using Win32 API.
    Works even against fullscreen DirectX/OpenGL applications.
    No-ops silently when the widget is not visible or win32 is unavailable."""
    if not widget.isVisible():
        return
    try:
        import win32gui, win32con
        hwnd = int(widget.winId())
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
        )
    except Exception:
        pass


def _start_topmost_timer(widget: QWidget, interval_ms: int = 3000):
    """Start a periodic timer that re-applies HWND_TOPMOST to keep the widget above fullscreen apps.
    The timer is stored as widget._topmost_timer to prevent garbage collection."""
    timer = QTimer(widget)
    timer.setInterval(interval_ms)
    timer.timeout.connect(lambda: _force_topmost(widget))
    timer.start()
    widget._topmost_timer = timer

_OVERLAY_PAGE_ACCENTS = [
    QColor(0, 229, 255),    # page 0: cyan (default/highlights)
    QColor(255, 127, 0),    # page 1: orange (achievement progress)
    QColor(0, 200, 110),    # page 2: green (other views)
    QColor(180, 80, 255),   # page 3: purple (cloud/VPS)
]


def read_active_players(base_dir: str):
    ap_dir = os.path.join(base_dir, "session_stats", "Highlights", "activePlayers")
    if not os.path.isdir(ap_dir):
        return []

    # Nur P1 laden
    p1_files = []
    try:
        for fn in os.listdir(ap_dir):
            if re.search(r"_P1\.json$", fn, re.IGNORECASE):
                p1_files.append(os.path.join(ap_dir, fn))
    except Exception:
        return []

    if not p1_files:
        return []

    p1_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    fp = p1_files[0]

    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [{
            "id": 1,
            "highlights": data.get("highlights", {}),
            "playtime_sec": int(data.get("playtime_sec", 0) or 0),
            "score": int(data.get("score", 0) or 0),
            "title": data.get("title", "Player 1"),
            "player": 1,
            "rom": data.get("rom", ""),
        }]
    except Exception:
        return []

