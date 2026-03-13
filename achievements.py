from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import (QColor, QFont, QPixmap, QPainter, QImage, QFontMetrics)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal, QObject

if TYPE_CHECKING:
    from gui import MainWindow

# ---------------------------------------------------------------------------
# Achievement toast notifications
# ---------------------------------------------------------------------------

class AchToastWindow(QWidget):
    finished = pyqtSignal()
    def __init__(self, parent: "MainWindow", title: str, rom: str, seconds: int = 5):
        super().__init__(None)
        self.parent_gui = parent
        self._title = str(title or "").strip()
        self._rom = str(rom or "").strip()
        self._seconds = max(1, int(seconds))
        self._is_closing = False  
        self.setWindowTitle("Achievement")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background:transparent;")
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._remaining = self._seconds
        self._render_and_place()
        self._timer.start()
        self.show()
        self.raise_()

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._remaining = 0
            try:
                self._timer.stop()
            except Exception:
                pass
            
            if not getattr(self, "_is_closing", False):
                self._is_closing = True
                try:
                    self.finished.emit()
                except Exception:
                    pass
                QTimer.singleShot(200, self.close)
            return
        self._render_and_place()

    def closeEvent(self, e):
        if not getattr(self, "_is_closing", False):
            self._is_closing = True
            try:
                self.finished.emit()
            except Exception:
                pass
        super().closeEvent(e)

    def _icon_pixmap(self, size: int = 40) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setBrush(QColor("#FFD700"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, size, size)
            p.setBrush(QColor("#FFFFFF"))
            cx = int(size * 0.25)
            cs = int(size * 0.5)
            p.drawEllipse(cx, cx, cs, cs)
        finally:
            p.end()
        return pm
        
    def _compose_image(self) -> QImage:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = int(ov.get("base_body_size", 20))
        title_pt = max(body_pt + 2, int(ov.get("base_title_size", int(body_pt * 1.35))))
        
        # Feste Theme-Farben
        title_color = QColor("#FF7F00") # Orange
        text_color = QColor("#FFFFFF")  # Weiß
        
        title = self._title or "Achievement unlocked"
        sub = self._rom or ""
        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)
        icon_sz = max(28, int(body_pt * 2.0))
        pad = max(12, int(body_pt * 0.8))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_w = fm_title.horizontalAdvance(title)
        sub_w = fm_body.horizontalAdvance(sub) if sub else 0
        text_w = max(title_w, sub_w)
        text_h = fm_title.height() + (vgap + fm_body.height() if sub else 0)
        content_h = max(icon_sz, text_h)
        W = pad + icon_sz + gap + text_w + pad
        H = pad + content_h + pad
        W = max(W, 320)
        H = max(H, max(96, int(body_pt * 4.8)))
        
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        
        bg = QColor(0, 0, 0, 200)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        radius = 16
        p.drawRoundedRect(0, 0, W, H, radius, radius)
        
        # Eisblauer Rahmen
        pen = QPen(QColor("#00E5FF"))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, W - 2, H - 2, radius, radius)
        
        pm = self._icon_pixmap(icon_sz)
        iy = int((H - icon_sz) / 2)
        p.drawPixmap(pad, iy, pm)
        x_text = pad + icon_sz + gap
        text_top = int((H - text_h) / 2)
        
        p.setPen(title_color)
        p.setFont(f_title)
        p.drawText(QRect(x_text, text_top, W - x_text - pad, fm_title.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        if sub:
            p.setPen(text_color)
            p.setFont(f_body)
            p.drawText(QRect(x_text, text_top + fm_title.height() + vgap,
                             W - x_text - pad, fm_body.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)
        p.end()
        
        portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
        if portrait:
            ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        return img

    def _render_and_place(self):
        try:
            img = self._compose_image()
            W, H = img.width(), img.height()
            ov = self.parent_gui.cfg.OVERLAY or {}
            portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            use_saved = bool(ov.get("ach_toast_saved", ov.get("ach_toast_custom", False)))
            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)
            if use_saved:
                if portrait:
                    x = int(ov.get("ach_toast_x_portrait", 100))
                    y = int(ov.get("ach_toast_y_portrait", 100))
                else:
                    x = int(ov.get("ach_toast_x_landscape", 100))
                    y = int(ov.get("ach_toast_y_landscape", 100))
            else:
                pad = 40
                x = int(geo.right() - W - pad)
                y = int(geo.bottom() - H - pad)

            x = max(geo.left(), min(x, geo.right() - W))
            y = max(geo.top(),  min(y,  geo.bottom() - H))
            self.setGeometry(x, y, W, H)
            self._label.setGeometry(0, 0, W, H)
            self._label.setPixmap(QPixmap.fromImage(img))
            self.show()
            self.raise_()
            try:
                import win32gui, win32con 
                hwnd = int(self.winId())
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
                )
            except Exception:
                pass
        except Exception as e:
            print(f"[TOAST] render_and_place failed: {e}")

class AchToastManager(QObject):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.parent_gui = parent
        self._queue: list[tuple[str, str, int]] = []
        self._active = False
        self._active_window: Optional[AchToastWindow] = None

    def enqueue(self, title: str, rom: str, seconds: int = 5):
        """Fügt einen Toast in die Warteschlange ein."""
        self._queue.append((title, rom, seconds))
        if not self._active:
            self._show_next()

    def _show_next(self):
        if not self._queue:
            self._active = False
            self._active_window = None
            return
        
        self._active = True
        title, rom, seconds = self._queue.pop(0)
        win = AchToastWindow(self.parent_gui, title, rom, seconds)
        win.finished.connect(self._on_finished)
        self._active_window = win

    def _on_finished(self):
        self._active_window = None
        QTimer.singleShot(250, self._show_next)

