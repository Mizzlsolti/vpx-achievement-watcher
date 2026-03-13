from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor, QFont, QPixmap, QPainter, QImage
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

if TYPE_CHECKING:
    from gui import MainWindow

# ---------------------------------------------------------------------------
# Challenge overlays
# ---------------------------------------------------------------------------

class ChallengeCountdownOverlay(QWidget):
    def __init__(self, parent, total_seconds: int = 300):
        super().__init__(parent)
        self.parent_gui = parent
        self._left = max(1, int(total_seconds))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(400, 120)
        self.show()
        try:
            import win32gui, win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
        except Exception:
            pass
        self._render_and_place()

    def _tick(self):
        self._left -= 1
        if self._left <= 0:
            self._left = 0
            try:
                self._timer.stop()
                self._render_and_place()  
            except Exception:
                pass
            QTimer.singleShot(200, self.close)
            return
        self._render_and_place()

    def _render_and_place(self):
        img = self._compose_image()
        if img is None:
            return
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("ch_timer_saved", ov.get("ch_timer_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_timer_x_portrait", 100))
                y = int(ov.get("ch_timer_y_portrait", 100))
            else:
                x = int(ov.get("ch_timer_x_landscape", 100))
                y = int(ov.get("ch_timer_y_landscape", 100))
        else:
            pad = 40
            x = int(geo.left() + pad)
            y = int(geo.bottom() - H - pad)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def _compose_image(self):
        w, h = 400, 120
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(Qt.GlobalColor.white)
        p.fillRect(0, 0, w, h, QColor(0, 0, 0, 255))
        mins, secs = divmod(self._left, 60)
        txt = f"{mins:02d}:{secs:02d}"
        font = QFont("Segoe UI", 48, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, txt)
        p.end()
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_timer_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pass
        return img

    def paintEvent(self, _evt):
        if hasattr(self, "_pix"):
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()
            
class ChallengeSelectOverlay(QWidget):
    def __init__(self, parent: "MainWindow", selected_idx: int = 0):
        super().__init__(parent)
        self.parent_gui = parent
        self._selected = 0 if int(selected_idx) % 2 == 0 else 1
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pulse_t = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50) 
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._pulse_timer.start()
        self._pix = None
        self._render_and_place()
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

    def closeEvent(self, e):
        try:
            if getattr(self, "_pulse_timer", None):
                self._pulse_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.08) % 1.0
        self._render_and_place()

    def set_selected(self, idx: int):
        self._selected = 0 if int(idx) % 2 == 0 else 1
        self._render_and_place()

    def apply_portrait_from_cfg(self):
        self._render_and_place()

    def _compose_image(self) -> QImage:
        from math import sin, pi

        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        base_body_pt = int(ov.get("base_body_size", 20))
        hint_pt = int(ov.get("base_hint_size", max(12, base_body_pt * 0.8)))
        
        text_color = QColor("#FFFFFF")
        hi_color = QColor("#FF7F00")

        if int(getattr(self, "_selected", 0) or 0) % 2 == 0:
            title_text = "Timed Challenge"
            desc_text = "3:00 minutes playing time."
        else:
            title_text = "Flip Challenge"
            desc_text = "Count Left+Right flips until chosen target."

        w, h = 520, 200
        pad_lr = 20
        top_pad = 24
        bottom_pad = 18
        hint_gap = 10
        avail_w = w - 2 * pad_lr

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 255))
            radius = 16
            p.drawRoundedRect(0, 0, w, h, radius, radius)
            
            pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(1, 1, w - 2, h - 2, radius, radius)

            title_pt = base_body_pt + 6
            desc_pt = max(10, base_body_pt)
            min_title = 12
            min_desc = 10

            flags_wrap_center = int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap)

            def measure_heights(t_pt: int, d_pt: int) -> tuple[int, int]:
                fm_t = QFontMetrics(QFont(font_family, t_pt, QFont.Weight.Bold))
                fm_d = QFontMetrics(QFont(font_family, d_pt))
                rect = QRect(0, 0, avail_w, 10000)
                t_bbox = fm_t.boundingRect(rect, flags_wrap_center, title_text)
                d_bbox = fm_d.boundingRect(rect, flags_wrap_center, desc_text)
                return t_bbox.height(), d_bbox.height()

            fm_hint = QFontMetrics(QFont(font_family, hint_pt))
            hint_h = fm_hint.height()
            max_content_h = h - top_pad - bottom_pad - hint_gap - hint_h

            for _ in range(64):
                t_h, d_h = measure_heights(title_pt, desc_pt)
                total = t_h + 6 + d_h
                if total <= max_content_h:
                    break
                if title_pt > min_title: title_pt -= 1
                if desc_pt > min_desc: desc_pt -= 1
                if title_pt <= min_title and desc_pt <= min_desc: break

            t_h, d_h = measure_heights(title_pt, desc_pt)
            block_h = t_h + 6 + d_h
            content_top = top_pad + max(0, (max_content_h - block_h) // 2)

            p.setPen(hi_color)
            p.setFont(QFont(font_family, title_pt, QFont.Weight.Bold))
            title_rect = QRect(pad_lr, content_top, avail_w, t_h)
            p.drawText(title_rect, flags_wrap_center, title_text)

            p.setPen(text_color)
            p.setFont(QFont(font_family, desc_pt))
            desc_rect = QRect(pad_lr, title_rect.bottom() + 6, avail_w, d_h)
            p.drawText(desc_rect, flags_wrap_center, desc_text)

            p.setPen(QColor("#AAAAAA"))
            p.setFont(QFont(font_family, hint_pt))
            hint_rect = QRect(0, h - bottom_pad - hint_h, w, hint_h)
            p.drawText(hint_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), "Press Hotkey to start")

            # Eisblaue pulsierende Pfeile
            amp = 0.5 + 0.5 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
            alpha = 110 + int(120 * amp)
            scale = 0.9 + 0.2 * amp
            wobble = 2.0 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
            base_h = 18
            ah = int(base_h * scale)
            aw = max(8, int(ah * 0.6))
            cy = title_rect.center().y()
            left_cx = pad_lr + 24 + int(-wobble)
            right_cx = w - pad_lr - 24 + int(wobble)
            
            arrow_color = QColor("#00E5FF")
            arrow_color.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(arrow_color)

            p.drawPolygon(*[QPoint(left_cx - aw // 2, cy), QPoint(left_cx + aw // 2, cy - ah // 2), QPoint(left_cx + aw // 2, cy + ah // 2)])
            p.drawPolygon(*[QPoint(right_cx + aw // 2, cy), QPoint(right_cx - aw // 2, cy - ah // 2), QPoint(right_cx - aw // 2, cy + ah // 2)])

        finally:
            try: p.end()
            except Exception: pass

        try:
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception: pass

        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("ch_ov_saved", ov.get("ch_ov_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_ov_x_portrait", 100))
                y = int(ov.get("ch_ov_y_portrait", 100))
            else:
                x = int(ov.get("ch_ov_x_landscape", 100))
                y = int(ov.get("ch_ov_y_landscape", 100))
        else:
            x = int(geo.left() + (geo.width() - W) // 2)
            y = int(geo.top()  + (geo.height() - H) // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()

class FlipDifficultyOverlay(QWidget):
    def __init__(self, parent: "MainWindow", selected_idx: int = 1,
                 options: list[tuple[str, int]] = None):
        super().__init__(parent)
        self.parent_gui = parent

        # default options expanded/reordered
        default_options = [("Easy", 400), ("Medium", 300), ("Difficult", 200), ("Pro", 100)]
        self._options = list(options) if isinstance(options, list) and options else default_options

        # clamp selection to available options
        self._selected = max(0, min(int(selected_idx or 0), len(self._options) - 1))

        self._pulse_t = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._pulse_timer.start()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pix = None
        self._render_and_place()
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

    def closeEvent(self, e):
        try:
            if getattr(self, "_pulse_timer", None):
                self._pulse_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.08) % 1.0
        self._render_and_place()

    def set_selected(self, idx: int):
        self._selected = max(0, min(int(idx or 0), len(self._options) - 1))
        self._render_and_place()

    def selected_option(self) -> tuple[str, int]:
        return self._options[self._selected]

    def apply_portrait_from_cfg(self):
        self._render_and_place()

    def _compose_image(self) -> QImage:
        from math import sin, pi
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        base_body_pt = int(ov.get("base_body_size", 20))
        hint_pt = int(ov.get("base_hint_size", max(12, base_body_pt * 0.8)))
        text_color = QColor("#FFFFFF")
        hi_color = QColor("#FF7F00")

        w, h = 560, 240
        pad_lr = 24
        top_pad = 26
        bottom_pad = 18
        gap_title_desc = 8
        avail_w = w - 2 * pad_lr

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 255))
            radius = 16
            p.drawRoundedRect(0, 0, w, h, radius, radius)
            pen = QPen(QColor("#00E5FF")); pen.setWidth(2)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(1, 1, w - 2, h - 2, radius, radius)

            title = "Flip Challenge – Choose difficulty"
            p.setPen(hi_color)
            p.setFont(QFont(font_family, base_body_pt + 6, QFont.Weight.Bold))
            fm_t = QFontMetrics(QFont(font_family, base_body_pt + 6, QFont.Weight.Bold))
            t_h = fm_t.height()
            p.drawText(QRect(pad_lr, top_pad, avail_w, t_h),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), title)

            y0 = top_pad + t_h + gap_title_desc
            n = max(1, len(self._options))
            spacing = 15
            total_spacing = spacing * (n - 1)
            box_w = max(80, int((avail_w - total_spacing) / n))
            box_h = 100

            def draw_option(ix: int, name: str, flips: int, selected: bool):
                x = pad_lr + ix * (box_w + spacing)
                rect = QRect(x, y0, box_w, box_h)
                
                if selected:
                    amp = 0.5 + 0.5 * sin(2 * pi * getattr(self, "_pulse_t", 0.0))
                    alpha = 40 + int(60 * amp)
                    p.fillRect(rect.adjusted(-4, -4, 4, 4), QColor(255, 127, 0, alpha)) # Oranger Pulse
                    p.setPen(QPen(QColor("#00E5FF"), 2))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
                    
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, 10, 10)

                p.setPen(QColor("#FF7F00") if selected else QColor("#FFFFFF"))
                p.setFont(QFont(font_family, base_body_pt + (2 if selected else 0), QFont.Weight.Bold))
                fm_n = QFontMetrics(QFont(font_family, base_body_pt + (2 if selected else 0), QFont.Weight.Bold))
                name_h = fm_n.height()
                p.drawText(QRect(x, y0 + 10, box_w, name_h),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), name)
                
                p.setFont(QFont(font_family, base_body_pt))
                p.drawText(QRect(x, y0 + 10 + name_h + 6, box_w, base_body_pt + 8),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), f"{int(flips)} flips")

            for i, (nm, fl) in enumerate(self._options):
                draw_option(i, nm, fl, i == self._selected)

            p.setPen(QColor("#AAAAAA"))
            p.setFont(QFont(font_family, hint_pt))
            p.drawText(QRect(0, h - bottom_pad - 18, w, 18),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                       "Select with Left/Right, press Hotkey to start")
        finally:
            try: p.end()
            except Exception: pass

        try:
            portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception: pass
        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY or {}
        use_saved = bool(ov.get("ch_ov_saved", ov.get("ch_ov_custom", False)))
        portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
        if use_saved:
            if portrait:
                x = int(ov.get("ch_ov_x_portrait", 100)); y = int(ov.get("ch_ov_y_portrait", 100))
            else:
                x = int(ov.get("ch_ov_x_landscape", 100)); y = int(ov.get("ch_ov_y_landscape", 100))
        else:
            x = int(geo.left() + (geo.width() - W) // 2)
            y = int(geo.top()  + (geo.height() - H) // 2)
        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()

import threading, time, os

