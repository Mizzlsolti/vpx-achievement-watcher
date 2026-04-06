"""Info, status, navigation and flip counter overlay widgets."""
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
    FlipImpactPulse, MilestoneBurst, ElectricSpark,
    GoalProximityGlow, CompletionFirework,
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


class FlipCounterOverlay(_OverlayFxMixin, QWidget):
    def __init__(self, parent: "MainWindow", total: int, remaining: int, goal: int):
        super().__init__(None)
        self.parent_gui = parent
        self._total = int(total)
        self._remaining = int(remaining)
        self._goal = int(goal)
        self.setWindowTitle("Flip Counter")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background:transparent;")

        # Breathing glow animation (same cadence as ChallengeSelectOverlay pulse)
        self._breathing_pulse = BreathingPulse(speed=0.05)

        # --- Flip Counter effects ---
        self._fx_impact = FlipImpactPulse(intensity=self._get_fx_intensity("fx_flip_impact_pulse"))
        self._fx_milestone = MilestoneBurst(intensity=self._get_fx_intensity("fx_flip_milestone_burst"))
        self._fx_spark = ElectricSpark(intensity=self._get_fx_intensity("fx_flip_electric_spark"))
        self._fx_goal_glow = GoalProximityGlow(intensity=self._get_fx_intensity("fx_flip_goal_glow"))
        self._fx_firework = CompletionFirework(intensity=self._get_fx_intensity("fx_flip_completion_firework"))
        if self._is_fx_enabled("fx_flip_goal_glow"):
            self._fx_goal_glow.start()
            if self._goal > 0:
                self._fx_goal_glow.set_proximity(min(1.0, self._total / self._goal))
        # Counter spin state (inline effect)
        self._spin_elapsed = 0.0
        self._spin_from = self._total

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(50)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()  # always run; live fx checks in _compose_image

        # Post-processing widget (drawn on top of flip counter content)
        from .overlay import PostProcessingWidget
        self._pp_widget = PostProcessingWidget(self, overlay_type="flip")

        self._render_and_place()
        self.show()
        self.raise_()
        try:
            import win32gui, win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
            )
        except Exception:
            pass
        _start_topmost_timer(self)

    def _on_anim_tick(self):
        self._breathing_pulse.tick(50.0)
        self._fx_impact.tick(50.0)
        self._fx_milestone.tick(50.0)
        self._fx_spark.tick(50.0)
        self._fx_goal_glow.tick(50.0)
        self._fx_firework.tick(50.0)
        if self._spin_elapsed > 0:
            self._spin_elapsed += 50.0
            if self._spin_elapsed >= 400.0:
                self._spin_elapsed = 0.0
        self._render_and_place()

    def _check_low_perf(self) -> bool:
        """Live-read low_performance_mode master switch."""
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            return bool(ov.get("low_performance_mode", False))
        except Exception:
            return False

    def closeEvent(self, e):
        try:
            if getattr(self, "_anim_timer", None):
                self._anim_timer.stop()
        except Exception:
            pass
        try:
            self._fx_goal_glow.stop()
        except Exception:
            pass
        pp = getattr(self, '_pp_widget', None)
        if pp is not None:
            try:
                pp.stop_timer()
            except Exception:
                pass
        super().closeEvent(e)

    def _compose_image(self) -> QImage:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = 15
        title_pt = max(body_pt + 2, int(round(body_pt * 1.35)))

        title_color = QColor(get_theme_color(self.parent_gui.cfg, "accent"))
        hi_color = QColor("#FFFFFF")

        # Counter spin: show animated intermediate value during spin
        if self._is_fx_enabled("fx_flip_counter_spin") and self._spin_elapsed > 0:
            t = min(1.0, self._spin_elapsed / 400.0)
            spin_value = int(self._spin_from + (self._total - self._spin_from) * t)
            noise = random.randint(-2, 2) if t < 0.75 else 0
            display_total = max(0, spin_value + noise)
        else:
            display_total = self._total

        title = f"Total flips: {int(display_total)}/{int(self._goal)}"
        sub = f"Remaining: {int(max(0, self._remaining))}"

        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)

        pad = max(12, int(body_pt * 0.9))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_w = fm_title.horizontalAdvance(title)
        sub_w = fm_body.horizontalAdvance(sub)
        text_w = max(title_w, sub_w)
        text_h = fm_title.height() + vgap + fm_body.height()
        content_w = max(280, text_w + 2 * pad)
        content_h = max(96, text_h + 2 * pad)

        img = QImage(content_w, content_h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        draw_rect = QRect(0, 0, content_w, content_h)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            bg = _theme_bg_qcolor(self.parent_gui.cfg, 245)
            radius = 16
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(0, 0, content_w, content_h, radius, radius)

            _draw_glow_border(p, 0, 0, content_w, content_h, radius=radius,
                              color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                              low_perf=not self._is_fx_enabled("fx_flip_glow_border"))

            # Breathing glow ring: pulsates when animation is enabled.
            # Drawn at 5px inset to avoid overlapping the fully-opaque inner border from
            # _draw_glow_border (which extends ~2px from the edge), ensuring the alpha
            # oscillation (40→220) is visible against the dark background.
            if self._is_fx_enabled("fx_flip_breathing_glow"):
                _pc = QColor(get_theme_color(self.parent_gui.cfg, "primary"))
                self._breathing_pulse.draw(p, 5, 5, content_w - 10, content_h - 10,
                                           radius - 3, _pc, width=5)

            # Progress arc (inline effect): arc around the widget showing progress toward goal
            if self._is_fx_enabled("fx_flip_progress_arc") and self._goal > 0:
                progress = min(1.0, self._total / self._goal)
                arc_margin = 4
                arc_rect = QRect(arc_margin, arc_margin,
                                 content_w - 2 * arc_margin, content_h - 2 * arc_margin)
                span_angle = int(progress * 360 * 16)
                start_angle = 90 * 16  # start from top (12 o'clock)
                accent_c = QColor(get_theme_color(self.parent_gui.cfg, "accent"))
                accent_c.setAlpha(180)
                p.save()
                p.setPen(QPen(accent_c, 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(arc_rect, start_angle, -span_angle)
                p.restore()

            # Goal proximity glow
            if self._is_fx_enabled("fx_flip_goal_glow"):
                self._fx_goal_glow.draw(p, draw_rect)

            p.setPen(title_color); p.setFont(f_title)
            p.drawText(QRect(0, pad, content_w, fm_title.height()),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), title)

            p.setPen(hi_color); p.setFont(f_body)
            body_rect = QRect(0, pad + fm_title.height() + vgap, content_w, fm_body.height())
            p.drawText(body_rect,
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), sub)

            # Foreground effects (over text)
            if self._is_fx_enabled("fx_flip_impact_pulse"):
                self._fx_impact.draw(p, draw_rect)
            if self._is_fx_enabled("fx_flip_milestone_burst"):
                self._fx_milestone.draw(p, draw_rect)
            if self._is_fx_enabled("fx_flip_electric_spark"):
                self._fx_spark.draw(p, draw_rect)
            if self._is_fx_enabled("fx_flip_completion_firework"):
                self._fx_firework.draw(p, draw_rect)
        finally:
            p.end()

        portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
        if portrait:
            ccw = bool(ov.get("flip_counter_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        return img

    def _render_and_place(self):
        img = self._compose_image()
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        ov = self.parent_gui.cfg.OVERLAY or {}
        screens = QApplication.screens() or []
        geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
        for s in screens[1:]:
            geo = geo.united(s.availableGeometry())
        portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
        use_saved = bool(ov.get("flip_counter_saved", ov.get("flip_counter_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("flip_counter_x_portrait", 100))
                y = int(ov.get("flip_counter_y_portrait", 100))
            else:
                x = int(ov.get("flip_counter_x_landscape", 100))
                y = int(ov.get("flip_counter_y_landscape", 100))
        else:
            pad = 40
            x = int(geo.left() + pad)
            y = int(geo.top() + pad)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.setGeometry(x, y, W, H)
        self._label.setGeometry(0, 0, W, H)
        self._label.setPixmap(QPixmap.fromImage(img))
        self.show()
        self.raise_()
        if hasattr(self, '_pp_widget') and self._pp_widget._any_pp_enabled():
            self._pp_widget.setGeometry(0, 0, W, H)
            if not self._pp_widget.isVisible():
                self._pp_widget.show()
            self._pp_widget.raise_()

    def update_counts(self, total: int, remaining: int, goal: int):
        old_total = self._total
        self._total = int(total)
        self._remaining = int(remaining)
        self._goal = int(goal)
        if self._total != old_total:
            # Trigger one-shot effects on count change
            if self._is_fx_enabled("fx_flip_impact_pulse"):
                self._fx_impact.trigger()
            if self._is_fx_enabled("fx_flip_electric_spark"):
                self._fx_spark.trigger()
            # Counter spin (inline)
            if self._is_fx_enabled("fx_flip_counter_spin"):
                self._spin_from = old_total
                self._spin_elapsed = 0.001  # non-zero to start spin
            # Milestone burst at 25%, 50%, 75% of goal
            if self._goal > 0 and self._is_fx_enabled("fx_flip_milestone_burst"):
                for pct in (25, 50, 75):
                    threshold = int(self._goal * pct / 100)
                    if old_total < threshold <= self._total:
                        self._fx_milestone.trigger()
                        break
            # Completion firework when goal first reached
            if self._goal > 0 and self._total >= self._goal > old_total:
                if self._is_fx_enabled("fx_flip_completion_firework"):
                    self._fx_firework.start()
            # Update goal proximity glow
            if self._is_fx_enabled("fx_flip_goal_glow") and self._goal > 0:
                self._fx_goal_glow.set_proximity(min(1.0, self._total / self._goal))
        self._render_and_place()

    def update_font(self):
        if self.isVisible():
            self._render_and_place()


class StatusOverlay(_OverlayFxMixin, QWidget):
    """Compact persistent status badge reflecting tracking/cloud state.

    Displays one of the agreed status states using traffic-light semantics:
      - Green:  ``Online · Tracking``, ``Online · Verified``
      - Yellow: ``Online · Pending``, ``Offline · Local``
      - Red:    ``Cloud Off · Local``

    Unlike MiniInfoOverlay (System Notifications), this overlay is a
    persistent mini-badge that stays visible while in-game.  It has no
    countdown timer and does not auto-dismiss; callers are responsible for
    calling :meth:`show_badge` / :meth:`hide_badge` based on game state.

    Uses its own config keys (``status_overlay_*``) and is completely
    independent from MiniInfoOverlay / System Notifications.
    """

    # Compact badge dimensions
    _BADGE_FONT_PT = 13
    _PAD_W = 22
    _PAD_H = 14
    _RADIUS = 12
    _MAX_TEXT_WIDTH = 340

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
        self._font_family = ov.get("font_family", "Segoe UI")
        # Traffic-light color for the dot indicator
        self._color = "#00C853"
        # Status text (one of the 5 agreed states)
        self._status_text = ""
        self._bg_color = _theme_bg_qcolor(self.parent_gui.cfg, 230)
        self._portrait_mode = bool(ov.get("status_overlay_portrait", False))
        self._rotate_ccw = bool(ov.get("status_overlay_rotate_ccw", False))
        self._last_center = (960, 540)
        self._snap_label = QLabel(self)
        self._snap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snap_label.setStyleSheet("background:transparent;")

        # Animation state
        low_perf = bool(ov.get("low_performance_mode", False))
        anim_status = bool(ov.get("anim_status", True))
        self._low_perf = low_perf or not anim_status
        # Scan-in, glow sweep, and color morph animation primitives
        self._scan_in = ScanIn(duration=220.0, distance=30)
        self._sweep = GlowSweep(duration=350.0)
        self._morph = ColorMorph(duration=200.0)
        # Combined animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_tick)

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

    def _check_low_perf(self) -> bool:
        """Read low-performance / anim-status config live so toggle takes effect immediately."""
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            return bool(ov.get("low_performance_mode", False)) or not bool(ov.get("anim_status", True))
        except Exception:
            return self._low_perf

    def _compose_html(self) -> str:
        """Build compact badge HTML: colored dot + status text."""
        fam = str(getattr(self, "_font_family", "Segoe UI")).replace("'", "").replace('"', "").replace(";", "").replace("<", "").replace(">", "")
        pt = self._BADGE_FONT_PT
        dot_color = self._color
        text = str(self._status_text or "").strip()
        return (
            f"<span style='font-size:{pt}pt;font-family:\"{fam}\";'>"
            f"<span style='color:{dot_color};'>&#9679;</span>"
            f"&nbsp;<span style='color:#EEEEEE;'>{text}</span>"
            f"</span>"
        )

    def _render_badge_image(self, html: str) -> QImage:
        # Measure the actual rendered text size using a QLabel sizeHint so the
        # badge is sized to fit the content tightly (no excess right padding).
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet("color:#EEEEEE;background:transparent;")
        tmp.setFont(QFont(self._font_family, self._BADGE_FONT_PT))
        tmp.setWordWrap(False)
        tmp.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        tmp.setText(html)
        # sizeHint() gives the natural (unwrapped) dimensions of the label.
        sh = tmp.sizeHint()
        text_w = max(60, min(sh.width(), self._MAX_TEXT_WIDTH))
        text_h = max(1, sh.height())

        W = max(120, text_w + self._PAD_W)
        H = max(36, text_h + self._PAD_H)

        tmp.setFixedWidth(text_w)
        tmp.resize(text_w, text_h)

        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._bg_color)
            p.drawRoundedRect(0, 0, W, H, self._RADIUS, self._RADIUS)
            # Left-align content with equal horizontal padding on both sides
            margin_left = self._PAD_W // 2
            margin_top = (H - text_h) // 2
            tmp.render(p, QPoint(margin_left, margin_top))
            # Glow sweep animation (horizontal sweep line)
            if not self._check_low_perf() and self._sweep.is_active():
                _sc = QColor(get_theme_color(self.parent_gui.cfg, "primary"))
                self._sweep.draw(p, W, H, self._RADIUS, _sc)
        finally:
            p.end()
        return img

    def _refresh_view(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._portrait_mode = bool(ov.get("status_overlay_portrait", False))
        self._rotate_ccw = bool(ov.get("status_overlay_rotate_ccw", False))
        self._bg_color = _theme_bg_qcolor(self.parent_gui.cfg, 230)

        html = self._compose_html()
        img = self._render_badge_image(html)

        if self._portrait_mode:
            angle = -90 if self._rotate_ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        W, H = img.width(), img.height()

        use_saved = bool(ov.get("status_overlay_saved", False))
        screens = QApplication.screens() or []
        geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
        for s in screens[1:]:
            geo = geo.united(s.availableGeometry())

        if use_saved:
            if self._portrait_mode:
                x = int(ov.get("status_overlay_x_portrait", 100))
                y = int(ov.get("status_overlay_y_portrait", 100))
            else:
                x = int(ov.get("status_overlay_x_landscape", 100))
                y = int(ov.get("status_overlay_y_landscape", 100))
        else:
            cx, cy = self._last_center
            x = int(cx - W // 2)
            y = int(cy - H // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(), min(y, geo.bottom() - H))

        # Apply scan-in x offset
        scan_offset = 0
        opacity = 1.0
        if not self._check_low_perf() and self._scan_in.is_active():
            scan_offset, opacity = self._scan_in.get_offset_and_opacity()

        self.setGeometry(x + scan_offset, y, W, H)
        self._snap_label.setGeometry(0, 0, W, H)
        self._snap_label.setPixmap(QPixmap.fromImage(img))
        self.setWindowOpacity(opacity)
        self.show()
        self.raise_()
        _force_topmost(self)

    def _anim_tick(self):
        """Advance scan-in, sweep, and morph animations."""
        dt = 16.0
        needs_render = False

        # Scan-in
        if self._scan_in.is_active():
            self._scan_in.tick(dt)
            if not self._scan_in.is_active():
                # Trigger glow sweep after scan-in
                if not self._check_low_perf():
                    self._sweep.start()
            needs_render = True

        # Glow sweep
        if self._sweep.is_active():
            self._sweep.tick(dt)
            needs_render = True

        # Color morph
        if self._morph.is_active():
            self._morph.tick(dt)
            self._color = self._morph.current_color()
            if not self._morph.is_active():
                self._status_text = self._morph.current_text()
            needs_render = True

        if needs_render:
            self._refresh_view()

        # Stop timer if nothing active
        if (not self._scan_in.is_active() and
                not self._sweep.is_active() and
                not self._morph.is_active()):
            self._anim_timer.stop()

    def closeEvent(self, e):
        try:
            self._anim_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def update_font(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._font_family = str(ov.get("font_family", "Segoe UI"))
        if self.isVisible():
            self._refresh_view()

    def update_status(self, status_text: str, color_hex: str = "#00C853"):
        """Update the displayed status state and refresh the badge.

        This is the primary method for changing the badge content.  The badge
        remains visible after this call; use :meth:`hide_badge` to hide it.
        """
        new_text = str(status_text or "").strip()
        new_color = str(color_hex or "#00C853").strip()
        self._last_center = self._primary_center()

        if self._check_low_perf():
            # Low performance: instant switch, no animation
            self._status_text = new_text
            self._color = new_color
            self._refresh_view()
            return

        was_visible = self.isVisible()
        text_changed = (new_text != self._status_text)
        color_changed = (new_color != self._color)

        if not was_visible or (not self._status_text and new_text):
            # Badge newly appearing: trigger scan-in
            self._status_text = new_text
            self._color = new_color
            self._scan_in.start()
            self._sweep.stop()
            self._morph.stop()
            self._anim_timer.start()
        elif text_changed or color_changed:
            # Status changing: morph color, pop text
            self._morph.start(self._color, new_color, self._status_text, new_text)
            # Show new text immediately for readability; color morphs smoothly
            self._status_text = new_text
            self._anim_timer.start()
        else:
            self._status_text = new_text
            self._color = new_color

        self._refresh_view()

    def show_badge(self):
        """Make the badge visible (typically called on game start)."""
        if self._status_text:
            self._refresh_view()

    def hide_badge(self):
        """Hide the badge (typically called on game end)."""
        self.hide()

    def show_status(self, message: str, seconds: int = 5, color_hex: str | None = None):
        """Compatibility shim: update the status badge persistently.

        The ``seconds`` parameter is ignored; this overlay is persistent and
        does not auto-dismiss.  Use :meth:`hide_badge` to hide it explicitly.
        """
        self.update_status(message, color_hex or "#00C853")
