"""Info, status, and navigation overlay widgets."""
from __future__ import annotations

import random

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QTransform, QPixmap,
    QPainter, QImage, QPen,
)

from ui.overlay_base import (
    _OverlayFxMixin,
    _theme_bg_qcolor,
    _force_topmost,
    _start_topmost_timer,
)
from core.theme import get_theme_color
from effects.gl_effects_opengl import (
    draw_glow_border as _draw_glow_border,
    BreathingPulse,
    ScanIn, GlowSweep, ColorMorph,
)


class OverlayNavArrows(QWidget):
    """Pulsating ice-blue navigation arrows displayed over the main overlay to indicate page cycling."""

    def __init__(self, parent: "OverlayWindow"):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._breathing_pulse = BreathingPulse(speed=0.08)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(80)
        self._pulse_timer.timeout.connect(self._on_tick)
        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent()
        low_perf = False
        fx_nav = True
        try:
            cfg_ov = parent.parent_gui.cfg.OVERLAY
            low_perf = bool(cfg_ov.get("low_performance_mode", False))
            fx_nav = bool(cfg_ov.get("fx_main_nav_arrows_pulse", True))
        except Exception:
            pass
        if not fx_nav:
            self.hide()
            return
        if not low_perf and not self._pulse_timer.isActive():
            self._pulse_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._pulse_timer.stop()

    def _on_tick(self):
        self._breathing_pulse.tick(80.0)
        self.update()

    def paintEvent(self, event):
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return

        parent = self.parent()
        portrait = getattr(parent, "portrait_mode", False)
        ccw = getattr(parent, "rotate_ccw", True)

        low_perf = False
        fx_nav = True
        try:
            cfg_ov = parent.parent_gui.cfg.OVERLAY
            low_perf = bool(cfg_ov.get("low_performance_mode", False))
            fx_nav = bool(cfg_ov.get("fx_main_nav_arrows_pulse", True))
        except Exception:
            pass

        if not fx_nav:
            return

        if portrait:
            draw_w, draw_h = H, W
        else:
            draw_w, draw_h = W, H

        img = QImage(draw_w, draw_h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            if low_perf:
                alpha = 180
                scale = 1.0
                wobble = 0
            else:
                amp = self._breathing_pulse.get_amp()
                alpha = 120 + int(135 * amp)
                scale = 0.88 + 0.25 * amp
                wobble = 5.0 * self._breathing_pulse.get_sin()
            base_h = 28
            ah = int(base_h * scale)
            aw = max(6, int(ah * 0.6))
            cy = draw_h // 2
            pad = 16
            right_cx = draw_w - pad + int(wobble)
            try:
                arrow_color = QColor(get_theme_color(parent.parent_gui.cfg, "primary"))
            except Exception:
                arrow_color = QColor("#00E5FF")
            arrow_color.setAlpha(alpha)
            # Glow/shadow behind the arrow for better visibility
            if not low_perf:
                glow_color = QColor(arrow_color)
                glow_color.setAlpha(max(0, alpha // 3))
                for glow_r in (ah // 2 + 6, ah // 2 + 3):
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(glow_color)
                    p.drawPolygon([
                        QPoint(right_cx + aw // 2 + glow_r // 3, cy),
                        QPoint(right_cx - aw // 2 - glow_r // 3, cy - ah // 2 - glow_r // 3),
                        QPoint(right_cx - aw // 2 - glow_r // 3, cy + ah // 2 + glow_r // 3),
                    ])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(arrow_color)
            # Right-pointing arrow
            p.drawPolygon([
                QPoint(right_cx + aw // 2, cy),
                QPoint(right_cx - aw // 2, cy - ah // 2),
                QPoint(right_cx - aw // 2, cy + ah // 2),
            ])
        finally:
            try:
                p.end()
            except Exception:
                pass

        if portrait:
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        p_main = QPainter(self)
        p_main.drawImage(0, 0, img)
        p_main.end()


class MiniInfoOverlay(QWidget):
    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Info")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._body_pt = 20
        self._font_family = ov.get("font_family", "Segoe UI")
        self._red = get_theme_color(self.parent_gui.cfg, "accent")
        self._hint = "#DDDDDD"
        self._bg_color = _theme_bg_qcolor(self.parent_gui.cfg, 245)
        self._radius = 16
        self._pad_w = 28
        self._pad_h = 22
        self._max_text_width = 520
        self._portrait_mode = bool(ov.get("portrait_mode", True))
        self._rotate_ccw = bool(ov.get("portrait_rotate_ccw", True))
        self._remaining = 0
        self._base_msg = ""
        self._last_center = (960, 540)
        self._snap_label = QLabel(self)
        self._snap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snap_label.setStyleSheet("background:transparent;")
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        self.hide()
        _start_topmost_timer(self)

    def _primary_center(self) -> tuple[int, int]:
        try:
            screens = QApplication.screens() or []
            geo = screens[0].geometry() if screens else QRect(0, 0, 1280, 720)
            for s in screens[1:]:
                geo = geo.united(s.geometry())
            return geo.left() + geo.width() // 2, geo.top() + geo.height() // 2
        except Exception:
            return 640, 360

    def _compose_html(self) -> str:
        pt = getattr(self, "_body_pt", 20)
        fam = str(getattr(self, "_font_family", "Segoe UI")).replace("'", "").replace('"', "").replace(";", "").replace("<", "").replace(">", "")
        if self._remaining > 0:
            countdown = f"<br><span style='color:{self._hint};'>closing in {self._remaining}…</span>"
        else:
            countdown = ""
        return (
            f"<div style='font-size:{pt}pt;font-family:\"{fam}\";'>"
            f"<span style='color:{self._red};'>{self._base_msg}</span>"
            f"{countdown}"
            f"</div>"
        )

    def _render_message_image(self, html: str) -> QImage:
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet(f"color:{self._red};background:transparent;")
        tmp.setFont(QFont(self._font_family, self._body_pt))
        tmp.setWordWrap(True)
        tmp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tmp.setText(html)
        tmp.setFixedWidth(self._max_text_width)
        tmp.adjustSize()
        text_w = tmp.width()
        text_h = tmp.sizeHint().height()
        W = max(200, text_w + self._pad_w)
        H = max(60,  text_h + self._pad_h)
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._bg_color)
            p.drawRoundedRect(0, 0, W, H, self._radius, self._radius)
            margin_left = (W - text_w) // 2
            margin_top = (H - text_h) // 2
            tmp.render(p, QPoint(margin_left, margin_top))
        finally:
            p.end()
        return img

    def _refresh_view(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._portrait_mode = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
        self._rotate_ccw = bool(ov.get("notifications_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        self._bg_color = _theme_bg_qcolor(self.parent_gui.cfg, 245)

        html = self._compose_html()
        img = self._render_message_image(html)

        if self._portrait_mode:
            angle = -90 if self._rotate_ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        W, H = img.width(), img.height()
        
        use_saved = bool(ov.get("notifications_saved", False))
        screens = QApplication.screens() or []
        geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
        for s in screens[1:]:
            geo = geo.united(s.availableGeometry())
        
        if use_saved:
            if self._portrait_mode:
                x = int(ov.get("notifications_x_portrait", 100))
                y = int(ov.get("notifications_y_portrait", 100))
            else:
                x = int(ov.get("notifications_x_landscape", 100))
                y = int(ov.get("notifications_y_landscape", 100))
        else:
            cx, cy = self._last_center
            x = int(cx - W // 2)
            y = int(cy - H // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(), min(y, geo.bottom() - H))

        self.setGeometry(x, y, W, H)
        self._snap_label.setGeometry(0, 0, W, H)
        self._snap_label.setPixmap(QPixmap.fromImage(img))
        self.show()
        self.raise_()
        _force_topmost(self)

    def _on_tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self.hide()
            return
        self._refresh_view()

    def update_font(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._body_pt = 20
        self._font_family = str(ov.get("font_family", "Segoe UI"))
        if self.isVisible():
            self._refresh_view()

    def show_info(self, message: str, seconds: int = 5, center: tuple[int, int] | None = None, color_hex: str | None = None):
        self._base_msg = str(message or "").strip()
        # seconds=0 means persistent (no auto-hide); positive values auto-hide after N seconds
        self._remaining = max(1, int(seconds)) if int(seconds) > 0 else 0
        if color_hex:
            try:
                self._red = color_hex
            except Exception:
                pass
        self._last_center = self._primary_center()
        self._timer.stop()
        self._refresh_view()
        if self._remaining > 0:
            self._timer.start()

    def update_message(self, message: str, color_hex: str | None = None) -> None:
        """Update the displayed message without resetting the countdown timer.

        Useful when the message content changes mid-display (e.g. toggling the
        focused option in a duel invite) but the remaining time must not change.
        Has no effect if the overlay is not currently visible.
        """
        self._base_msg = str(message or "").strip()
        if color_hex:
            try:
                self._red = color_hex
            except Exception:
                pass
        if self.isVisible():
            self._refresh_view()


class StatusOverlay(QWidget):
    """Small frameless status badge overlay for persistent cloud/tracking status display."""

    _AUTO_HIDE_SECS = 8

    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Status")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._font_family = str(ov.get("font_family", "Segoe UI"))
        self._badge_font_pt = 13
        self._pad_w = 22
        self._pad_h = 14
        self._radius = 10
        self._message = "Online · Tracking"
        self._color_hex = "#00C853"
        self._snap_label = QLabel(self)
        self._snap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snap_label.setStyleSheet("background:transparent;")
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        # Entry-animation effects
        self._scan_in = ScanIn()
        self._glow_sweep = GlowSweep()
        self._color_morph = ColorMorph()
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_alpha = 0.0
        self._anim_done = False
        self.hide()
        _start_topmost_timer(self)

    def _get_portrait(self) -> bool:
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            return bool(ov.get("status_overlay_portrait", False))
        except Exception:
            return False

    def _get_ccw(self) -> bool:
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            return bool(ov.get("status_overlay_rotate_ccw", False))
        except Exception:
            return False

    def _render_badge_image(self) -> QImage:
        fam = str(self._font_family).replace("'", "").replace('"', "").replace(";", "").replace("<", "").replace(">", "")
        pt = self._badge_font_pt
        color = str(self._color_hex or "#00C853")
        text = str(self._message or "").strip()
        html = (
            f"<span style='font-size:{pt}pt;font-family:\"{fam}\";'>"
            f"<span style='color:{color};'>&#9679;</span>"
            f"&nbsp;<span style='color:#EEEEEE;'>{text}</span>"
            f"</span>"
        )
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet("color:#EEEEEE;background:transparent;")
        tmp.setFont(QFont(fam, pt))
        tmp.setWordWrap(False)
        tmp.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        tmp.setText(html)
        sh = tmp.sizeHint()
        text_w = max(60, min(sh.width(), 340))
        text_h = max(1, sh.height())
        W = max(120, text_w + self._pad_w)
        H = max(36, text_h + self._pad_h)

        bg_color = _theme_bg_qcolor(self.parent_gui.cfg, 220)
        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg_color)
            p.drawRoundedRect(0, 0, W, H, self._radius, self._radius)
            try:
                glow_col = QColor(self._color_hex)
                _draw_glow_border(p, 0, 0, W, H, self._radius, glow_col, alpha=120, width=2)
            except Exception:
                pass
            margin_left = self._pad_w // 2
            margin_top = (H - text_h) // 2
            tmp.render(p, QPoint(margin_left, margin_top))
        finally:
            p.end()
        return img

    def _compute_position(self, W: int, H: int) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        portrait = self._get_portrait()
        use_saved = bool(ov.get("status_overlay_saved", False))
        screens = QApplication.screens() or []
        geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
        for s in screens[1:]:
            geo = geo.united(s.availableGeometry())
        if use_saved:
            if portrait:
                x = int(ov.get("status_overlay_x_portrait", 100))
                y = int(ov.get("status_overlay_y_portrait", 100))
            else:
                x = int(ov.get("status_overlay_x_landscape", 100))
                y = int(ov.get("status_overlay_y_landscape", 100))
        else:
            x = geo.right() - W - 20
            y = geo.top() + 20
        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(), min(y, geo.bottom() - H))
        return x, y

    def _refresh_view(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._font_family = str(ov.get("font_family", self._font_family))
        portrait = self._get_portrait()
        ccw = self._get_ccw()

        img = self._render_badge_image()
        if portrait:
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        # Apply animation alpha fade-in
        if not self._anim_done and self._anim_alpha < 1.0:
            faded = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
            faded.fill(Qt.GlobalColor.transparent)
            p = QPainter(faded)
            p.setOpacity(max(0.0, min(1.0, self._anim_alpha)))
            p.drawImage(0, 0, img)
            p.end()
            img = faded

        W, H = img.width(), img.height()
        x, y = self._compute_position(W, H)
        self.setGeometry(x, y, W, H)
        self._snap_label.setGeometry(0, 0, W, H)
        self._snap_label.setPixmap(QPixmap.fromImage(img))
        self.show()
        self.raise_()
        _force_topmost(self)

    def _on_anim_tick(self):
        self._anim_alpha = min(1.0, self._anim_alpha + 0.12)
        self._refresh_view()
        if self._anim_alpha >= 1.0:
            self._anim_done = True
            self._anim_timer.stop()

    def update_font(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._font_family = str(ov.get("font_family", "Segoe UI"))
        if self.isVisible():
            self._refresh_view()

    def update_status(self, message: str, color_hex: str):
        """Update the displayed status message and color, then show (or refresh) the overlay."""
        self._message = str(message or "").strip()
        self._color_hex = str(color_hex or "#00C853")
        ov = self.parent_gui.cfg.OVERLAY or {}
        auto_hide_secs = int(ov.get("status_overlay_auto_hide_secs", self._AUTO_HIDE_SECS))
        # Start fade-in animation if newly shown
        if not self.isVisible():
            self._anim_alpha = 0.0
            self._anim_done = False
            try:
                self._scan_in.reset()
                self._glow_sweep.reset()
                self._color_morph.reset()
            except Exception:
                pass
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        self._refresh_view()
        # Reset auto-hide timer
        self._hide_timer.stop()
        if auto_hide_secs > 0:
            self._hide_timer.start(auto_hide_secs * 1000)

