"""Shared reusable Qt widgets for the VPX Achievement Watcher UI."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QEvent, QPoint
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPolygon


class HazardStripeOverlay(QWidget):
    """Hazard-stripe overlay widget that can be placed over any parent widget.

    Paints alternating yellow/black diagonal stripes and centred white text.
    The overlay is transparent for mouse events so it does not block the
    underlying widget's interactions — it is a purely visual indicator.

    Usage::

        overlay = HazardStripeOverlay(parent_widget, "🔒 Some lock message")
        overlay.show()
        overlay.raise_()
    """

    _STRIPE_W = 18       # pixel width of each colour band
    _YELLOW = QColor("#F5C518")
    _BLACK = QColor("#000000")
    _MIN_FONT_PX = 9
    _MAX_FONT_PX = 13
    _FONT_PADDING = 4

    def __init__(self, parent: QWidget, text: str = "") -> None:
        super().__init__(parent)
        self._text = text
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()
        parent.installEventFilter(self)

    # ------------------------------------------------------------------
    # Keep overlay sized to cover the parent widget at all times
    # ------------------------------------------------------------------
    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.resize(self.parent().size())
        return False

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.resize(self.parent().size())

    # ------------------------------------------------------------------
    # Custom painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        # Yellow base fill
        p.fillRect(0, 0, w, h, self._YELLOW)

        # Black diagonal stripes (45° – going from upper-left to lower-right)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._BLACK)
        sw = self._STRIPE_W
        i = -h
        while i < w:
            poly = QPolygon([
                QPoint(i,          0),
                QPoint(i + sw,     0),
                QPoint(i + sw + h, h),
                QPoint(i + h,      h),
            ])
            p.drawPolygon(poly)
            i += sw * 2

        if not self._text:
            p.end()
            return

        # Centred text
        font = QFont()
        font.setPixelSize(max(self._MIN_FONT_PX, min(self._MAX_FONT_PX, h - self._FONT_PADDING)))
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        br = fm.boundingRect(self._text)
        tx = (w - br.width()) // 2
        ty = (h + fm.ascent() - fm.descent()) // 2

        # Dark outline / shadow
        p.setPen(self._BLACK)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1),
                       (0, -1),  (0, 1),  (-1, 0), (1, 0)):
            p.drawText(tx + dx, ty + dy, self._text)

        # White text
        p.setPen(QColor("#FFFFFF"))
        p.drawText(tx, ty, self._text)

        p.end()
