from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from .helpers import _draw_glow_border

class TimerPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 400, height_hint: int = 120):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Challenge Timer")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        self._base_w, self._base_h = self._calc_overlay_size()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._screen_geo()
        # fall back to legacy "custom" key for backward compatibility with older configs
        if bool(ov.get("ch_timer_saved", ov.get("ch_timer_custom", False))):
            if self._portrait:
                x0 = int(ov.get("ch_timer_x_portrait", 100))
                y0 = int(ov.get("ch_timer_y_portrait", 100))
            else:
                x0 = int(ov.get("ch_timer_x_landscape", 100))
                y0 = int(ov.get("ch_timer_y_landscape", 100))
        else:
            x0 = int(geo.left() + (geo.width() - self._w) // 2)
            y0 = int(geo.top() + (geo.height() - self._h) // 2)
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            scr = QApplication.primaryScreen()
            if scr:
                return scr.availableGeometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _calc_overlay_size(self) -> tuple[int, int]:
        return 400, 120

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ch_timer_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
            self._base_w, self._base_h = self._calc_overlay_size()
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h

            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            x = min(max(geo.left(), x), geo.right() - self._w)
            y = min(max(geo.top(),  y), geo.bottom() - self._h)
            self.setGeometry(x, y, self._w, self._h)
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(8, 12, 22, 245))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Challenge Timer\nDrag to position. Click the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            x = min(max(geo.left(), target.x()), geo.right() - self._w)
            y = min(max(geo.top(),  target.y()), geo.bottom() - self._h)
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())


class ToastPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 420, height_hint: int = 120):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Achievement Toast")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        self._base_w, self._base_h = self._calc_overlay_size()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h
        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._screen_geo()
        # fall back to legacy "custom" key for backward compatibility with older configs
        if bool(ov.get("ach_toast_saved", ov.get("ach_toast_custom", False))):
            if self._portrait:
                x0 = int(ov.get("ach_toast_x_portrait", 100))
                y0 = int(ov.get("ach_toast_y_portrait", 100))
            else:
                x0 = int(ov.get("ach_toast_x_landscape", 100))
                y0 = int(ov.get("ach_toast_y_landscape", 100))
        else:
            x0 = int(geo.left() + (geo.width() - self._w) // 2)
            y0 = int(geo.top() + (geo.height() - self._h) // 2)
        x = min(max(geo.left(), x0), geo.right() - self._w)
        y = min(max(geo.top(),  y0), geo.bottom() - self._h)
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _screen_geo(self) -> QRect:
        try:
            scr = QApplication.primaryScreen()
            if scr:
                return scr.availableGeometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = 15
        title_pt = max(body_pt + 2, int(round(body_pt * 1.35)))
        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)
        icon_sz = max(28, int(body_pt * 2.0))
        pad = max(12, int(body_pt * 0.8))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_text = "GREAT ACHIEVEMENT UNLOCKED!"
        sub_text = "Table Name"
        text_w = max(fm_title.horizontalAdvance(title_text), fm_body.horizontalAdvance(sub_text))
        text_h = fm_title.height() + vgap + fm_body.height()
        content_h = max(icon_sz, text_h)
        W = max(320, pad + icon_sz + gap + text_w + pad)
        H = max(96, pad + content_h + pad)
        return W, H

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        new_portrait = bool(self._portrait)
        if new_portrait != old_portrait:
            self._base_w, self._base_h = self._calc_overlay_size()
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h
            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            x = min(max(geo.left(), x), geo.right() - self._w)
            y = min(max(geo.top(),  y), geo.bottom() - self._h)
            self.setGeometry(x, y, self._w, self._h)
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(8, 12, 22, 245))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Achievement Toast\nDrag to position. Click the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            x = min(max(geo.left(), target.x()), geo.right() - self._w)
            y = min(max(geo.top(),  target.y()), geo.bottom() - self._h)
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())


class OverlayPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        self._w, self._h = self._calc_overlay_size()
        
        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._safe_screen_geo()
        
        if bool(ov.get("use_xy", False)):
            x0 = int(ov.get("pos_x", 100))
            y0 = int(ov.get("pos_y", 100))
        else:
            x0 = int(geo.left() + (geo.width() - self._w) // 2)
            y0 = int(geo.top() + (geo.height() - self._h) // 2)
            
        w_clamp = min(self._w, geo.width())
        h_clamp = min(self._h, geo.height())
        
        x = max(geo.left(), min(x0, geo.right() - w_clamp))
        y = max(geo.top(),  min(y0, geo.bottom() - h_clamp))
        
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _safe_screen_geo(self) -> QRect:
        try:
            scr = QApplication.primaryScreen()
            if scr:
                return scr.availableGeometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("portrait_mode", True))
            self._ccw = bool(ov.get("portrait_rotate_ccw", True))
        except Exception:
            self._portrait = True
            self._ccw = True

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        scale_pct = int(ov.get("scale_pct", 100))
        # Mirror OverlayWindow._ref_screen_geometry(): use the primary screen so
        # the picker dimensions exactly match the actual rendered overlay size.
        try:
            scr = QApplication.primaryScreen()
            ref = scr.geometry() if scr else self._safe_screen_geo()
        except Exception:
            ref = self._safe_screen_geo()
        if self._portrait:
            base_h = int(ref.height() * 0.55)
            base_w = int(base_h * 9 / 16)
        else:
            base_w = int(ref.width() * 0.40)
            base_h = int(ref.height() * 0.30)
        w = max(120, int(base_w * scale_pct / 100))
        h = max(120, int(base_h * scale_pct / 100))
        return w, h
        
    def apply_portrait_from_cfg(self):
        self._sync_from_cfg()
        self._w, self._h = self._calc_overlay_size()
        g = self.geometry()
        x, y = g.x(), g.y()
        geo = self._safe_screen_geo()
        w_clamp = min(self._w, geo.width())
        h_clamp = min(self._h, geo.height())
        x = max(geo.left(), min(x, geo.right() - w_clamp))
        y = max(geo.top(),  min(y, geo.bottom() - h_clamp))
        self.setGeometry(x, y, self._w, self._h)
        self.update()

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, QColor(8, 12, 22, 245))
        pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor("#FF7F00"))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Main Overlay\nDrag to position. Click the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._safe_screen_geo()
            w_clamp = min(self._w, geo.width())
            h_clamp = min(self._h, geo.height())
            x = max(geo.left(), min(target.x(), geo.right() - w_clamp))
            y = max(geo.top(),  min(target.y(), geo.bottom() - h_clamp))
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())

