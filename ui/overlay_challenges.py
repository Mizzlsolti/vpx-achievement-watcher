"""Challenge-related overlay widgets: countdown timer, challenge select, flip difficulty, heat barometer, start countdown."""
from __future__ import annotations

import math

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QPoint
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QTransform, QPixmap,
    QPainter, QImage, QPen, QLinearGradient, QBrush,
)

from ui.overlay_base import (
    _OverlayFxMixin,
    _theme_bg_qcolor,
    _start_topmost_timer,
)
from core.theme import get_theme_color
from effects.gl_effects_opengl import (
    draw_glow_border as _draw_glow_border,
    ease_out_cubic as _ease_out_cubic,
    BreathingPulse, CarouselSlide, SnapScale, HeatPulse,
    # Timer / Countdown effects
    CountdownScaleGlow, RadialPulseBackground, UrgencyShake, TimeWarpDistortion,
    TrailAfterimage, FinalExplosion, PulseRingCountdown, GlitchNumbers,
    # Challenge select effects
    ElectricArc, HoverShimmer, PlasmaNoise, HoloSweep, DifficultyColorPulse,
    # Heat Barometer effects
    FlameParticles, HeatShimmer, SmokeWisps, LavaGlowEdge, NumberThrob, MeltdownShake,
)

try:
    from core import sound as _sound_mod
except Exception:
    _sound_mod = None


class ChallengeCountdownOverlay(_OverlayFxMixin, QWidget):
    def __init__(self, parent, total_seconds: int = 300):
        super().__init__(parent)
        self.parent_gui = parent
        self._left = max(1, int(total_seconds))
        self._tick_callback = None
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
        # --- Timer effects (instantiated before first render) ---
        self._fx_scale_glow = CountdownScaleGlow(intensity=self._get_fx_intensity("fx_timer_321go"))
        self._fx_radial_pulse = RadialPulseBackground(intensity=self._get_fx_intensity("fx_timer_radial_pulse"))
        self._fx_urgency_shake = UrgencyShake(intensity=self._get_fx_intensity("fx_timer_urgency_shake"))
        self._fx_warp = TimeWarpDistortion(intensity=self._get_fx_intensity("fx_timer_warp_distortion"))
        self._fx_trail = TrailAfterimage(intensity=self._get_fx_intensity("fx_timer_trail_afterimage"))
        self._fx_explosion = FinalExplosion(intensity=self._get_fx_intensity("fx_timer_final_explosion"))
        self._fx_pulse_ring = PulseRingCountdown(intensity=self._get_fx_intensity("fx_timer_pulse_ring"))
        self._fx_glitch = GlitchNumbers(intensity=self._get_fx_intensity("fx_timer_glitch_numbers"))
        if self._is_fx_enabled("fx_timer_radial_pulse"):
            self._fx_radial_pulse.start()
        if self._is_fx_enabled("fx_timer_warp_distortion") and self._left <= 10:
            self._fx_warp.start()
        if self._is_fx_enabled("fx_timer_urgency_shake") and self._left <= 5:
            self._fx_urgency_shake.start()
        self._fx_timer = QTimer(self)
        self._fx_timer.setInterval(50)
        self._fx_timer.timeout.connect(self._on_fx_tick)
        self._fx_timer.start()
        # Post-processing widget (drawn on top of timer content)
        from .overlay import PostProcessingWidget
        self._pp_widget = PostProcessingWidget(self, overlay_type="timer")
        self.show()
        try:
            import win32gui, win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
            )
        except Exception:
            pass
        self._render_and_place()
        _start_topmost_timer(self)

    def _tick(self):
        self._left -= 1
        try:
            if self._tick_callback is not None:
                self._tick_callback(self._left * 1000)
        except Exception:
            pass
        if self._left <= 0:
            self._left = 0
            if _sound_mod is not None:
                try:
                    _sound_mod.play_sound(self.parent_gui.cfg, "countdown_final")
                except Exception:
                    pass
            try:
                self._timer.stop()
                self._render_and_place()
            except Exception:
                pass
            if self._is_fx_enabled("fx_timer_final_explosion"):
                self._fx_explosion.start()
            QTimer.singleShot(2000, self.close)
            return
        if self._is_fx_enabled("fx_timer_321go"):
            self._fx_scale_glow.trigger()
        if self._is_fx_enabled("fx_timer_pulse_ring"):
            self._fx_pulse_ring.trigger()
        if self._is_fx_enabled("fx_timer_trail_afterimage"):
            self._fx_trail.start()
        if self._is_fx_enabled("fx_timer_glitch_numbers"):
            self._fx_glitch.start()
        if self._is_fx_enabled("fx_timer_warp_distortion") and self._left <= 10:
            if not self._fx_warp.is_active():
                self._fx_warp.start()
        if self._is_fx_enabled("fx_timer_urgency_shake") and self._left <= 5:
            if not self._fx_urgency_shake.is_active():
                self._fx_urgency_shake.start()
        if _sound_mod is not None:
            try:
                _sound_mod.play_sound(self.parent_gui.cfg, "countdown_tick")
            except Exception:
                pass
        self._render_and_place()

    def _on_fx_tick(self):
        self._fx_scale_glow.tick(50.0)
        self._fx_radial_pulse.tick(50.0)
        self._fx_urgency_shake.tick(50.0)
        self._fx_warp.tick(50.0)
        self._fx_trail.tick(50.0)
        self._fx_explosion.tick(50.0)
        self._fx_pulse_ring.tick(50.0)
        self._fx_glitch.tick(50.0)
        self._render_and_place()

    def _render_and_place(self):
        img = self._compose_image()
        if img is None:
            return
        W, H = img.width(), img.height()
        self.setFixedSize(W, H)
        screens = QApplication.screens() or []
        geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
        for s in screens[1:]:
            geo = geo.united(s.availableGeometry())
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
        if hasattr(self, '_pp_widget') and self._pp_widget._any_pp_enabled():
            self._pp_widget.setGeometry(0, 0, W, H)
            if not self._pp_widget.isVisible():
                self._pp_widget.show()
            self._pp_widget.raise_()

    def _compose_image(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        factor = 1.0  # Challenge timer is always fixed size (100%)
        w = max(200, int(round(400 * factor)))
        h = max(60, int(round(120 * factor)))
        timer_font_pt = max(20, int(round(48 * factor)))
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_theme_bg_qcolor(self.parent_gui.cfg, 245))
        p.drawRoundedRect(0, 0, w, h, 16, 16)
        if self._is_fx_enabled("fx_timer_glow_border") and not bool(ov.get("low_performance_mode", False)):
            _draw_glow_border(p, 0, 0, w, h, radius=16,
                              color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                              low_perf=False)
        draw_rect = QRect(0, 0, w, h)
        # Background effects (drawn behind text)
        if self._is_fx_enabled("fx_timer_radial_pulse"):
            self._fx_radial_pulse.draw(p, draw_rect)
        if self._is_fx_enabled("fx_timer_321go"):
            self._fx_scale_glow.draw(p, draw_rect)
        if self._is_fx_enabled("fx_timer_warp_distortion"):
            self._fx_warp.draw(p, draw_rect)
        # Turn accent colour when 10 seconds or fewer remain
        if self._left <= 10:
            p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
        else:
            p.setPen(Qt.GlobalColor.white)
        mins, secs = divmod(self._left, 60)
        txt = f"{mins:02d}:{secs:02d}"
        font = QFont(font_family, timer_font_pt, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, txt)
        # Foreground effects (drawn over text)
        if self._is_fx_enabled("fx_timer_trail_afterimage"):
            self._fx_trail.draw(p, draw_rect)
        if self._is_fx_enabled("fx_timer_pulse_ring"):
            self._fx_pulse_ring.draw(p, draw_rect)
        if self._is_fx_enabled("fx_timer_final_explosion"):
            self._fx_explosion.draw(p, draw_rect)
        if self._is_fx_enabled("fx_timer_glitch_numbers"):
            self._fx_glitch.draw(p, draw_rect)
        if self._is_fx_enabled("fx_timer_urgency_shake"):
            self._fx_urgency_shake.draw(p, draw_rect)
        p.end()
        try:
            portrait = bool(ov.get("ch_timer_portrait", ov.get("portrait_mode", True)))
            if portrait:
                angle = -90 if bool(ov.get("ch_timer_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pass
        return img

    def update_font(self):
        if self.isVisible():
            self._render_and_place()

    def closeEvent(self, e):
        try:
            self._fx_timer.stop()
        except Exception:
            pass
        pp = getattr(self, '_pp_widget', None)
        if pp is not None:
            try:
                pp.stop_timer()
            except Exception:
                pass
        super().closeEvent(e)

    def paintEvent(self, _evt):
        if hasattr(self, "_pix"):
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()

class ChallengeSelectOverlay(_OverlayFxMixin, QWidget):
    def __init__(self, parent: "MainWindow", selected_idx: int = 0):
        super().__init__(parent)
        self.parent_gui = parent
        self._selected = int(selected_idx) % 4
        self._prev_selected = self._selected
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._breathing_pulse = BreathingPulse(speed=0.08)
        self._carousel = CarouselSlide(duration=180.0)
        self._exit_slide = CarouselSlide(duration=180.0)
        self._exit_callback = None
        self._exiting = False
        self._electric_arc = ElectricArc(intensity=self._get_fx_intensity("fx_challenge_electric_arc"))
        self._hover_shimmer = HoverShimmer(intensity=self._get_fx_intensity("fx_challenge_hover_shimmer"))
        self._plasma_noise = PlasmaNoise(intensity=self._get_fx_intensity("fx_challenge_plasma_noise"))
        self._holo_sweep = HoloSweep(intensity=self._get_fx_intensity("fx_challenge_holo_sweep"))
        self._color_pulse = DifficultyColorPulse(intensity=self._get_fx_intensity("fx_challenge_color_pulse"))
        # Snap scale state
        self._snap_scale = 1.0
        self._snap_elapsed = 0.0
        self._snap_active = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._slide_timer = QTimer(self)
        self._slide_timer.setInterval(16)
        self._slide_timer.timeout.connect(self._on_slide_tick)
        if self._is_fx_enabled("fx_challenge_electric_arc"):
            self._electric_arc.start()
        if self._is_fx_enabled("fx_challenge_hover_shimmer"):
            self._hover_shimmer.start()
        if self._is_fx_enabled("fx_challenge_plasma_noise"):
            self._plasma_noise.start()
        if self._is_fx_enabled("fx_challenge_holo_sweep"):
            self._holo_sweep.start()
        if self._is_fx_enabled("fx_challenge_color_pulse"):
            self._color_pulse.start()
        self._pulse_timer.start()  # always run; live fx checks in _compose_image
        self._pix = None
        # Post-processing widget (drawn on top of challenge select content)
        from .overlay import PostProcessingWidget
        self._pp_widget = PostProcessingWidget(self, overlay_type="challenge")
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

    def closeEvent(self, e):
        try:
            if getattr(self, "_pulse_timer", None):
                self._pulse_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "_slide_timer", None):
                self._slide_timer.stop()
        except Exception:
            pass
        pp = getattr(self, '_pp_widget', None)
        if pp is not None:
            try:
                pp.stop_timer()
            except Exception:
                pass
        super().closeEvent(e)

    def _check_low_perf(self) -> bool:
        """Live-read low_performance_mode master switch."""
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            return bool(ov.get("low_performance_mode", False))
        except Exception:
            return False

    def _on_pulse_tick(self):
        self._breathing_pulse.tick(50.0)
        if self._is_fx_enabled("fx_challenge_electric_arc"):
            self._electric_arc.tick(50.0)
        if self._is_fx_enabled("fx_challenge_hover_shimmer"):
            self._hover_shimmer.tick(50.0)
        if self._is_fx_enabled("fx_challenge_plasma_noise"):
            self._plasma_noise.tick(50.0)
        if self._is_fx_enabled("fx_challenge_holo_sweep"):
            self._holo_sweep.tick(50.0)
        if self._is_fx_enabled("fx_challenge_color_pulse"):
            self._color_pulse.tick(50.0)
        if self._snap_active:
            self._snap_elapsed += 50.0
            t = min(1.0, self._snap_elapsed / 200.0)  # 200ms duration
            self._snap_scale = 0.92 + 0.08 * t  # lerp back to 1.0
            if t >= 1.0:
                self._snap_scale = 1.0
                self._snap_active = False
        self._render_and_place()

    def _on_slide_tick(self):
        if self._exiting:
            self._exit_slide.tick(16.0)
            self._render_and_place()
            if not self._exit_slide.is_active():
                self._slide_timer.stop()
                cb = self._exit_callback
                self._exit_callback = None
                if cb:
                    cb()
        else:
            self._carousel.tick(16.0)
            if not self._carousel.is_active():
                self._slide_timer.stop()
            self._render_and_place()

    def start_slide_out(self, callback=None):
        """Trigger a slide-out animation then call callback when done."""
        if self._is_fx_enabled("fx_challenge_carousel"):
            self._exit_callback = callback
            self._exiting = True
            self._exit_slide.start(direction=1)
            self._slide_timer.start()
        else:
            if callback:
                callback()

    def set_selected(self, idx: int):
        new_idx = int(idx) % 4
        if new_idx != self._selected and self._is_fx_enabled("fx_challenge_carousel"):
            # Determine slide direction: going "right" in list = slide left
            direction = 1 if new_idx > self._selected else -1
            self._prev_selected = self._selected
            self._carousel.start(direction=direction)
            self._slide_timer.start()
        else:
            self._prev_selected = new_idx
        if new_idx != self._selected and self._is_fx_enabled("fx_challenge_snap_scale"):
            self._snap_scale = 0.92  # start slightly shrunk
            self._snap_elapsed = 0.0
            self._snap_active = True
        self._selected = new_idx
        self._render_and_place()

    def apply_portrait_from_cfg(self):
        self._render_and_place()

    def update_font(self):
        if self.isVisible():
            self._render_and_place()

    def _compose_image(self) -> QImage:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        base_body_pt = 20
        scaled_body_pt = 20  # Challenge select is always fixed size (100%)
        hint_pt = max(8, int(round(scaled_body_pt * 0.8)))

        text_color = QColor("#FFFFFF")
        hi_color = QColor(get_theme_color(self.parent_gui.cfg, "accent"))

        _CHALLENGE_LABELS = [
            ("⌛ Timed Challenge", "3:00 minutes playing time."),
            ("🎯 Flip Challenge", "Count Left+Right flips until chosen target."),
            ("🔥 Heat Challenge", "Keep heat below 100%. Don't spam or hold flippers!"),
            ("❌ Exit", "Close the challenge menu."),
        ]

        def _label_for(idx: int):
            return _CHALLENGE_LABELS[idx % 4]

        title_text, desc_text = _label_for(int(getattr(self, "_selected", 0) or 0))

        factor = scaled_body_pt / 20.0
        w = max(280, int(round(520 * factor)))
        h = max(110, int(round(200 * factor)))
        pad_lr = max(10, int(round(20 * factor)))
        top_pad = max(12, int(round(24 * factor)))
        bottom_pad = max(9, int(round(18 * factor)))
        hint_gap = max(5, int(round(10 * factor)))
        avail_w = w - 2 * pad_lr

        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_theme_bg_qcolor(self.parent_gui.cfg, 245))
            radius = 16
            p.drawRoundedRect(0, 0, w, h, radius, radius)

            _draw_glow_border(p, 0, 0, w, h, radius=radius,
                              color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                              low_perf=not self._is_fx_enabled("fx_challenge_glow_border"))

            # Selection glow (gated by fx)
            if self._is_fx_enabled("fx_challenge_selection_glow"):
                amp = self._breathing_pulse.get_amp()
                glow_alpha = int(30 * amp)
                glow_color = QColor(hi_color)
                glow_color.setAlpha(glow_alpha)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow_color)
                p.drawRoundedRect(0, 0, w, h, radius, radius)

            # Apply snap scale transform when active
            if self._snap_active or self._snap_scale != 1.0:
                cx_center, cy_center = w / 2.0, h / 2.0
                t = QTransform()
                t.translate(cx_center, cy_center)
                t.scale(self._snap_scale, self._snap_scale)
                t.translate(-cx_center, -cy_center)
                p.setTransform(t)

            draw_rect = QRect(0, 0, w, h)
            if self._is_fx_enabled("fx_challenge_plasma_noise"):
                self._plasma_noise.draw(p, draw_rect)
            if self._is_fx_enabled("fx_challenge_electric_arc"):
                self._electric_arc.draw(p, draw_rect)
            if self._is_fx_enabled("fx_challenge_hover_shimmer"):
                self._hover_shimmer.draw(p, draw_rect)
            if self._is_fx_enabled("fx_challenge_holo_sweep"):
                self._holo_sweep.draw(p, draw_rect)
            if self._is_fx_enabled("fx_challenge_color_pulse"):
                self._color_pulse.draw(p, draw_rect)

            title_font_pt = scaled_body_pt + 6
            desc_pt = max(10, scaled_body_pt)
            min_title = 12
            min_desc = 10

            flags_wrap_center = int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap)

            def measure_heights(t_pt: int, d_pt: int, title_text: str, desc_text: str) -> tuple[int, int]:
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
                t_h, d_h = measure_heights(title_font_pt, desc_pt, title_text, desc_text)
                total = t_h + 6 + d_h
                if total <= max_content_h:
                    break
                if title_font_pt > min_title: title_font_pt -= 1
                if desc_pt > min_desc: desc_pt -= 1
                if title_font_pt <= min_title and desc_pt <= min_desc: break

            t_h, d_h = measure_heights(title_font_pt, desc_pt, title_text, desc_text)
            block_h = t_h + 6 + d_h
            content_top = top_pad + max(0, (max_content_h - block_h) // 2)

            # Carousel slide: blend between previous and current content
            slide_active = self._is_fx_enabled("fx_challenge_carousel") and self._carousel.is_active()
            if slide_active:
                eased = self._carousel.get_eased_t()
                slide_dir = self._carousel.direction
                # Current item: slides in from direction
                cur_x_offset = int((1.0 - eased) * slide_dir * (avail_w // 2))
                cur_alpha = int(255 * eased)
                # Previous item: slides out in opposite direction
                prev_title, prev_desc = _label_for(int(getattr(self, '_prev_selected', self._selected)))
                prev_x_offset = int(-eased * slide_dir * (avail_w // 2))
                prev_alpha = int(255 * (1.0 - eased))

                # Set clip region to content area
                p.setClipRect(pad_lr, content_top, avail_w, block_h + 10)

                # Draw previous content (fading out, sliding away)
                p.setOpacity(max(0.0, min(1.0, prev_alpha / 255.0)))
                p.setPen(hi_color)
                p.setFont(QFont(font_family, title_font_pt, QFont.Weight.Bold))
                p.drawText(QRect(pad_lr + prev_x_offset, content_top, avail_w, t_h), flags_wrap_center, prev_title)
                p.setPen(text_color)
                p.setFont(QFont(font_family, desc_pt))
                p.drawText(QRect(pad_lr + prev_x_offset, content_top + t_h + 6, avail_w, d_h), flags_wrap_center, prev_desc)

                # Draw current content (fading in, sliding in)
                p.setOpacity(max(0.0, min(1.0, cur_alpha / 255.0)))
                p.setPen(hi_color)
                p.setFont(QFont(font_family, title_font_pt, QFont.Weight.Bold))
                title_rect = QRect(pad_lr + cur_x_offset, content_top, avail_w, t_h)
                p.drawText(title_rect, flags_wrap_center, title_text)
                p.setPen(text_color)
                p.setFont(QFont(font_family, desc_pt))
                desc_rect = QRect(pad_lr + cur_x_offset, content_top + t_h + 6, avail_w, d_h)
                p.drawText(desc_rect, flags_wrap_center, desc_text)

                p.setOpacity(1.0)
                p.setClipping(False)
            else:
                # Static (no slide) — clip content area so text can never overflow the
                # overlay bounds if the shrink loop exhausted both minimum font sizes.
                p.setClipRect(pad_lr, content_top, avail_w, max_content_h)
                p.setPen(hi_color)
                p.setFont(QFont(font_family, title_font_pt, QFont.Weight.Bold))
                title_rect = QRect(pad_lr, content_top, avail_w, t_h)
                p.drawText(title_rect, flags_wrap_center, title_text)

                p.setPen(text_color)
                p.setFont(QFont(font_family, desc_pt))
                desc_rect = QRect(pad_lr, title_rect.bottom() + 1 + 6, avail_w, d_h)
                p.drawText(desc_rect, flags_wrap_center, desc_text)
                p.setClipping(False)

            p.setPen(QColor("#AAAAAA"))
            p.setFont(QFont(font_family, hint_pt))
            hint_rect = QRect(0, h - bottom_pad - hint_h, w, hint_h)
            if int(getattr(self, "_selected", 0) or 0) % 4 == 3:
                hint_label = "Press Hotkey to close"
            else:
                hint_label = "Press Hotkey to start"
            p.drawText(hint_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), hint_label)

            # Pulsating ice-blue arrows (always at static content position for stability)
            arrow_cy_rect = QRect(pad_lr, content_top, avail_w, t_h)
            if self._is_fx_enabled("fx_challenge_arrow_wobble"):
                amp = self._breathing_pulse.get_amp()
                alpha = 110 + int(120 * amp)
                anim_scale = 0.9 + 0.2 * amp
                wobble = 2.0 * self._breathing_pulse.get_sin()
            else:
                amp = 0.5
                alpha = 170
                anim_scale = 1.0
                wobble = 0.0
            base_arr_h = max(10, int(round(18 * factor)))
            ah = int(base_arr_h * anim_scale)
            aw = max(6, int(ah * 0.6))
            cy = arrow_cy_rect.center().y()
            left_cx = pad_lr + max(12, int(round(24 * factor))) + int(-wobble)
            right_cx = w - pad_lr - max(12, int(round(24 * factor))) + int(wobble)

            arrow_color = QColor(get_theme_color(self.parent_gui.cfg, "primary"))
            arrow_color.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(arrow_color)

            p.drawPolygon([QPoint(left_cx - aw // 2, cy), QPoint(left_cx + aw // 2, cy - ah // 2), QPoint(left_cx + aw // 2, cy + ah // 2)])
            p.drawPolygon([QPoint(right_cx + aw // 2, cy), QPoint(right_cx - aw // 2, cy - ah // 2), QPoint(right_cx - aw // 2, cy + ah // 2)])

        finally:
            try: p.end()
            except Exception: pass

        # Exit slide: shift content to the left (sliding out)
        if getattr(self, '_exiting', False) and self._exit_slide.is_active():
            eased = self._exit_slide.get_eased_t()
            x_shift = int(eased * w)
            shifted = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            shifted.fill(Qt.GlobalColor.transparent)
            sp = QPainter(shifted)
            sp.setOpacity(1.0 - eased)
            sp.drawImage(-x_shift, 0, img)
            sp.end()
            img = shifted

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
        screens = QApplication.screens() or []
        geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
        for s in screens[1:]:
            geo = geo.united(s.availableGeometry())
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
        if hasattr(self, '_pp_widget') and self._pp_widget._any_pp_enabled():
            self._pp_widget.setGeometry(0, 0, W, H)
            if not self._pp_widget.isVisible():
                self._pp_widget.show()
            self._pp_widget.raise_()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()

class FlipDifficultyOverlay(_OverlayFxMixin, QWidget):
    def __init__(self, parent: "MainWindow", selected_idx: int = 1,
                 options: list[tuple[str, int]] = None):
        super().__init__(parent)
        self.parent_gui = parent

        # default options expanded/reordered
        default_options = [("Easy", 400), ("Medium", 300), ("Difficult", 200), ("Pro", 100), ("← Back", -1)]
        self._options = list(options) if isinstance(options, list) and options else default_options

        # clamp selection to available options
        self._selected = max(0, min(int(selected_idx or 0), len(self._options) - 1))
        self._prev_selected = self._selected

        self._breathing_pulse = BreathingPulse(speed=0.08)
        self._snap = SnapScale(duration=160.0, scale_amount=0.07)
        self._entry_slide = CarouselSlide(duration=180.0)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._snap_timer = QTimer(self)
        self._snap_timer.setInterval(16)
        self._snap_timer.timeout.connect(self._on_snap_tick)
        self._entry_timer = QTimer(self)
        self._entry_timer.setInterval(16)
        self._entry_timer.timeout.connect(self._on_entry_tick)
        self._pulse_timer.start()  # always run; live fx checks in _compose_image

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
        # Start entry slide-in from the right when fx is enabled
        if self._is_fx_enabled("fx_challenge_carousel"):
            self._entry_slide.start(direction=1)
            self._entry_timer.start()
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

    def closeEvent(self, e):
        try:
            if getattr(self, "_pulse_timer", None):
                self._pulse_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "_snap_timer", None):
                self._snap_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "_entry_timer", None):
                self._entry_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._breathing_pulse.tick(50.0)
        self._render_and_place()

    def _on_snap_tick(self):
        self._snap.tick(16.0)
        if not self._snap.is_active():
            self._snap_timer.stop()
        self._render_and_place()

    def _on_entry_tick(self):
        self._entry_slide.tick(16.0)
        if not self._entry_slide.is_active():
            self._entry_timer.stop()
        self._render_and_place()

    def set_selected(self, idx: int):
        new_idx = max(0, min(int(idx or 0), len(self._options) - 1))
        if new_idx != self._selected and self._is_fx_enabled("fx_challenge_snap_scale"):
            self._snap.start(prev_selected=self._selected)
            self._snap_timer.start()
        self._selected = new_idx
        self._render_and_place()

    def selected_option(self) -> tuple[str, int]:
        return self._options[self._selected]

    def apply_portrait_from_cfg(self):
        self._render_and_place()

    def update_font(self):
        if self.isVisible():
            self._render_and_place()

    def _compose_image(self) -> QImage:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        scaled_body_pt = 20
        hint_pt = max(8, int(round(scaled_body_pt * 0.8)))
        hi_color = QColor(get_theme_color(self.parent_gui.cfg, "accent"))

        factor = scaled_body_pt / 20.0
        # Match ChallengeSelectOverlay canvas size and padding exactly
        w = max(280, int(round(520 * factor)))
        pad_lr = max(10, int(round(20 * factor)))
        top_pad = max(12, int(round(24 * factor)))
        bottom_pad = max(9, int(round(18 * factor)))
        hint_gap = max(5, int(round(10 * factor)))
        gap_title_desc = max(4, int(round(8 * factor)))
        avail_w = w - 2 * pad_lr

        # Title — same font sizing as ChallengeSelectOverlay title
        title = "Flip Challenge – Choose difficulty"
        title_font_pt = scaled_body_pt + 6
        flags_center_wrap = int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap)
        fm_title = QFontMetrics(QFont(font_family, title_font_pt, QFont.Weight.Bold))
        t_h = fm_title.boundingRect(QRect(0, 0, avail_w, 10000), flags_center_wrap, title).height()

        # Hint line height
        fm_hint_pre = QFontMetrics(QFont(font_family, hint_pt))
        hint_line_h = fm_hint_pre.height()

        # Horizontal layout: 5 boxes side by side
        n = max(1, len(self._options))
        box_gap = max(4, int(round(8 * factor)))
        total_spacing = box_gap * (n - 1)
        box_w = max(40, (w - 2 * pad_lr - total_spacing) // n)

        # Boxes are equal squares: height equals width
        box_h = box_w
        boxes_y = top_pad + t_h + gap_title_desc
        # Height is determined dynamically to fit title + squares + hint
        h = top_pad + t_h + gap_title_desc + box_h + hint_gap + hint_line_h + bottom_pad

        # Font for names: constrained by box_w (longest label is "Difficult"/"← Back")
        inner_margin = max(2, int(round(3 * factor)))
        box_name_pt = max(7, int(round(box_w / 9)))
        flip_pt = max(6, box_name_pt - 2)  # flip count rendered 2pt smaller than the name

        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_theme_bg_qcolor(self.parent_gui.cfg, 245))
            radius = 16
            p.drawRoundedRect(0, 0, w, h, radius, radius)
            _draw_glow_border(p, 0, 0, w, h, radius=radius,
                              color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                              low_perf=not self._is_fx_enabled("fx_challenge_glow_border"))

            p.setPen(hi_color)
            p.setFont(QFont(font_family, title_font_pt, QFont.Weight.Bold))
            p.drawText(QRect(pad_lr, top_pad, avail_w, t_h), flags_center_wrap, title)

            def draw_option(ix: int, name: str, flips: int, selected: bool):
                box_x = pad_lr + ix * (box_w + box_gap)
                rect = QRect(box_x, boxes_y, box_w, box_h)

                # Snap pulse: brief flash on selection change; fade-out on prev selection
                snap_flash_alpha = 0
                prev_fade_alpha = 0
                if self._is_fx_enabled("fx_challenge_snap_scale") and self._snap.is_active():
                    snap_flash_alpha = self._snap.get_flash_alpha(selected)
                    prev_fade_alpha = self._snap.get_prev_fade_alpha(ix)

                if selected:
                    amp = self._breathing_pulse.get_amp()
                    alpha = 40 + int(60 * amp)
                    _ac = QColor(get_theme_color(self.parent_gui.cfg, "accent"))
                    p.fillRect(rect.adjusted(-2, -1, 2, 1), QColor(_ac.red(), _ac.green(), _ac.blue(), alpha))
                    p.setPen(QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary")), 2))
                    if snap_flash_alpha > 0:
                        p.fillRect(rect, QColor(255, 255, 255, snap_flash_alpha))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
                    _pc = QColor(get_theme_color(self.parent_gui.cfg, "primary"))
                    if prev_fade_alpha > 0:
                        p.fillRect(rect.adjusted(-2, -1, 2, 1), QColor(_pc.red(), _pc.green(), _pc.blue(), prev_fade_alpha))

                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, 6, 6)

                name_color = QColor(get_theme_color(self.parent_gui.cfg, "accent")) if selected else QColor("#FFFFFF")
                p.setPen(name_color)

                if int(flips) == -1:
                    # Back option: name centered in full box
                    p.setFont(QFont(font_family, box_name_pt, QFont.Weight.Bold))
                    p.drawText(rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), name)
                else:
                    # Name in top half, flip count in bottom half
                    half_h = box_h // 2
                    name_rect = QRect(box_x + inner_margin, boxes_y + inner_margin,
                                      box_w - 2 * inner_margin, half_h - inner_margin)
                    flip_rect = QRect(box_x + inner_margin, boxes_y + half_h,
                                      box_w - 2 * inner_margin, half_h - inner_margin)
                    p.setFont(QFont(font_family, box_name_pt, QFont.Weight.Bold))
                    p.drawText(name_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), name)
                    p.setPen(QColor("#CCCCCC") if not selected else name_color)
                    p.setFont(QFont(font_family, flip_pt))
                    p.drawText(flip_rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                               f"{int(flips)}")

            for i, (nm, fl) in enumerate(self._options):
                draw_option(i, nm, fl, i == self._selected)

            sel_flips = self._options[self._selected][1] if 0 <= self._selected < len(self._options) else 0
            hint_label = "Press Hotkey to go back" if int(sel_flips) == -1 else "Select with Left/Right, press Hotkey to start"
            p.setPen(QColor("#AAAAAA"))
            p.setFont(QFont(font_family, hint_pt))
            p.drawText(QRect(0, h - bottom_pad - hint_line_h, w, hint_line_h),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                       hint_label)
        finally:
            try: p.end()
            except Exception: pass

        # Entry slide: shift content in from the right (sliding in)
        if self._is_fx_enabled("fx_challenge_carousel") and self._entry_slide.is_active():
            eased = self._entry_slide.get_eased_t()
            x_shift = int((1.0 - eased) * w)
            shifted = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            shifted.fill(Qt.GlobalColor.transparent)
            sp = QPainter(shifted)
            sp.setOpacity(eased)
            sp.drawImage(x_shift, 0, img)
            sp.end()
            img = shifted

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
        screens = QApplication.screens() or []
        geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
        for s in screens[1:]:
            geo = geo.united(s.availableGeometry())
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
        if hasattr(self, '_pp_widget') and self._pp_widget._any_pp_enabled():
            self._pp_widget.setGeometry(0, 0, W, H)
            if not self._pp_widget.isVisible():
                self._pp_widget.show()
            self._pp_widget.raise_()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()


class HeatBarometerOverlay(_OverlayFxMixin, QWidget):
    """Vertical heat barometer overlay for Heat Challenge. Fills bottom-to-top,
    colour transitions from green (0-50%) to orange (50-85%) to red (>85%)."""

    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self._heat = 0
        self.setWindowTitle("Heat Barometer")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Reactive pulse animation timer (warning/critical)
        self._heat_pulse = HeatPulse(threshold=65)
        self._critical_pulse = HeatPulse(threshold=85)
        # --- Heat Barometer effects ---
        self._fx_flame = FlameParticles(intensity=self._get_fx_intensity("fx_heat_flame_particles"))
        self._fx_shimmer = HeatShimmer(intensity=self._get_fx_intensity("fx_heat_shimmer"))
        self._fx_smoke = SmokeWisps(intensity=self._get_fx_intensity("fx_heat_smoke_wisps"))
        self._fx_lava = LavaGlowEdge(intensity=self._get_fx_intensity("fx_heat_lava_glow"))
        self._fx_throb = NumberThrob(intensity=self._get_fx_intensity("fx_heat_number_throb"))
        self._fx_meltdown = MeltdownShake(intensity=self._get_fx_intensity("fx_heat_meltdown_shake"))
        if self._is_fx_enabled("fx_heat_flame_particles"):
            self._fx_flame.start()
        if self._is_fx_enabled("fx_heat_shimmer"):
            self._fx_shimmer.start()
        if self._is_fx_enabled("fx_heat_smoke_wisps"):
            self._fx_smoke.start()
        if self._is_fx_enabled("fx_heat_lava_glow"):
            self._fx_lava.start()
        if self._is_fx_enabled("fx_heat_number_throb"):
            self._fx_throb.start()
        if self._is_fx_enabled("fx_heat_warning_pulse"):
            self._heat_pulse.start()
        if self._is_fx_enabled("fx_heat_critical_pulse"):
            self._critical_pulse.start()
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._pulse_timer.start()
        self._anim_t = 0.0
        # Post-processing widget (drawn on top of heat barometer content)
        from .overlay import PostProcessingWidget
        self._pp_widget = PostProcessingWidget(self, overlay_type="heat")
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

    def _on_pulse_tick(self):
        self._anim_t += 0.04
        self._heat_pulse.tick(40.0)
        self._critical_pulse.tick(40.0)
        self._fx_flame.tick(40.0)
        self._fx_shimmer.tick(40.0)
        self._fx_smoke.tick(40.0)
        self._fx_lava.tick(40.0)
        self._fx_throb.tick(40.0)
        self._fx_meltdown.tick(40.0)
        self._render_and_place()

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))
        # Start meltdown shake at 90%+, stop below
        if self._is_fx_enabled("fx_heat_meltdown_shake") and self._heat >= 90:
            if not self._fx_meltdown.is_active():
                self._fx_meltdown.start()
        elif self._heat < 90 and self._fx_meltdown.is_active():
            self._fx_meltdown.stop()
        self._render_and_place()

    def closeEvent(self, e):
        try:
            self._pulse_timer.stop()
        except Exception:
            pass
        try:
            self._fx_flame.stop()
            self._fx_shimmer.stop()
            self._fx_smoke.stop()
            self._fx_lava.stop()
            self._fx_throb.stop()
            self._fx_meltdown.stop()
        except Exception:
            pass
        pp = getattr(self, '_pp_widget', None)
        if pp is not None:
            try:
                pp.stop_timer()
            except Exception:
                pass
        super().closeEvent(e)

    def _bar_color(self, heat: int) -> QColor:
        if heat <= 50:
            # 0-50%: blend from green (0,200,0) toward yellow (255,200,0)
            r = int(heat * 255 / 50)
            return QColor(r, 200, 0)
        elif heat <= 85:
            # 50-85%: blend from yellow toward deep orange/red
            frac = (heat - 50) / 35.0
            r = 255
            g = int(200 * (1.0 - frac))
            return QColor(r, g, 0)
        else:
            # >85%: solid danger red
            return QColor(220, 30, 0)

    def _compose_image(self) -> QImage:
        bar_w = 36
        bar_h = 220
        label_h = 28
        pad = 6
        w = bar_w + 2 * pad
        h = bar_h + label_h + 2 * pad

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        draw_rect = QRect(0, 0, w, h)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # background
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_theme_bg_qcolor(self.parent_gui.cfg, 245))
            p.drawRoundedRect(0, 0, w, h, 10, 10)

            # border with glow
            ov = self.parent_gui.cfg.OVERLAY or {}
            _draw_glow_border(p, 0, 0, w, h, radius=10,
                              color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                              low_perf=not self._is_fx_enabled("fx_heat_glow_border"))

            # Background effects (behind bar fill)
            if self._is_fx_enabled("fx_heat_shimmer"):
                self._fx_shimmer.draw(p, draw_rect)
            if self._is_fx_enabled("fx_heat_lava_glow"):
                self._fx_lava.draw(p, draw_rect)

            # bar background (track)
            bx = pad
            by = pad
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(40, 40, 40, 255))
            p.drawRoundedRect(bx, by, bar_w, bar_h, 6, 6)

            # fill from bottom upward
            fill_h = int(bar_h * self._heat / 100)
            if fill_h > 0:
                fill_y = by + bar_h - fill_h
                if self._is_fx_enabled("fx_heat_gradient_anim"):
                    # Animated gradient: green→yellow→orange→red based on heat
                    # with a phase offset to create shimmer motion
                    grad = QLinearGradient(float(bx), float(fill_y + fill_h),
                                           float(bx), float(fill_y))
                    phase = math.sin(self._anim_t * 2.0) * 0.08
                    # Color stops clamped to [0.0, 1.0] and kept in ascending order
                    s0 = max(0.0, min(1.0, 0.00 + phase))
                    s1 = max(0.0, min(1.0, 0.35 + phase))
                    s2 = max(0.0, min(1.0, 0.65 + phase))
                    s3 = max(0.0, min(1.0, 1.00 + phase))
                    grad.setColorAt(s0, QColor(0,   200, 0))
                    grad.setColorAt(s1, QColor(200, 200, 0))
                    grad.setColorAt(s2, QColor(255, 120, 0))
                    grad.setColorAt(s3, QColor(220,  30, 0))
                    p.setBrush(QBrush(grad))
                else:
                    p.setBrush(self._bar_color(self._heat))
                p.drawRoundedRect(bx, fill_y, bar_w, fill_h, 6, 6)

            # label
            p.setPen(QColor("#FFFFFF"))
            label_font_pt = 9
            if self._is_fx_enabled("fx_heat_number_throb"):
                scale = self._fx_throb.scale
                label_font_pt = max(7, int(round(9 * scale)))
            p.setFont(QFont("Segoe UI", label_font_pt, QFont.Weight.Bold))
            label_rect = QRect(0, pad + bar_h, w, label_h)
            p.drawText(label_rect, int(Qt.AlignmentFlag.AlignCenter), f"{self._heat}%")

            # Foreground effects (over bar fill and label)
            if self._is_fx_enabled("fx_heat_flame_particles"):
                self._fx_flame.draw(p, draw_rect)
            if self._is_fx_enabled("fx_heat_smoke_wisps"):
                self._fx_smoke.draw(p, draw_rect)

            # Reactive warning/critical pulse borders
            self._heat_pulse.draw(p, 1, 1, w - 2, h - 2, self._heat,
                                  not self._is_fx_enabled("fx_heat_warning_pulse"))
            self._critical_pulse.draw(p, 1, 1, w - 2, h - 2, self._heat,
                                      not self._is_fx_enabled("fx_heat_critical_pulse"))

            # Meltdown shake overlay
            if self._is_fx_enabled("fx_heat_meltdown_shake"):
                self._fx_meltdown.draw(p, draw_rect)
        finally:
            p.end()

        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            portrait = bool(ov.get("heat_bar_portrait", ov.get("portrait_mode", False)))
            if portrait:
                angle = -90 if bool(ov.get("heat_bar_rotate_ccw", ov.get("portrait_rotate_ccw", True))) else 90
                img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pass

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
        portrait = bool(ov.get("heat_bar_portrait", ov.get("portrait_mode", False)))
        use_saved = bool(ov.get("heat_bar_saved", ov.get("heat_bar_custom", False)))
        if use_saved:
            if portrait:
                x = int(ov.get("heat_bar_x_portrait", 20))
                y = int(ov.get("heat_bar_y_portrait", 100))
            else:
                x = int(ov.get("heat_bar_x_landscape", 20))
                y = int(ov.get("heat_bar_y_landscape", 100))
        else:
            x = int(geo.left() + 20)
            y = int(geo.top() + (geo.height() - H) // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(),  min(y,  geo.bottom() - H))
        self.move(x, y)
        self._pix = QPixmap.fromImage(img)
        self.update()
        if hasattr(self, '_pp_widget') and self._pp_widget._any_pp_enabled():
            self._pp_widget.setGeometry(0, 0, W, H)
            if not self._pp_widget.isVisible():
                self._pp_widget.show()
            self._pp_widget.raise_()

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()


class ChallengeStartCountdown(_OverlayFxMixin, QWidget):
    """Full-screen transparent countdown overlay: 3…2…1…GO!

    Each number scales from 2.0x → 1.0x with Ease-Out over 800ms.
    After '1', a brief 'GO!' text appears in orange with scale 1.0 → 1.5 + fade-out.
    Total duration: ~3.5 s.  Emits `finished` when the animation ends and auto-closes.
    """

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Cover the primary screen
        screen = QApplication.primaryScreen()
        geo = screen.geometry() if screen else QRect(0, 0, 1280, 720)
        self.setGeometry(geo)

        _primary = '#00E5FF'
        _accent = '#FF7F00'
        try:
            self.parent_gui = parent
            _primary = get_theme_color(parent.cfg, "primary")
            _accent = get_theme_color(parent.cfg, "accent")
        except Exception:
            self.parent_gui = None

        # Countdown sequence: ('3', primary), ('2', primary), ('1', primary), ('GO!', accent)
        self._steps = [
            ('3',   QColor(_primary), 800, False),
            ('2',   QColor(_primary), 800, False),
            ('1',   QColor(_primary), 800, False),
            ('GO!', QColor(_accent), 500, True),   # last step fades out
        ]
        self._step_idx = 0
        self._step_elapsed = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

        _start_topmost_timer(self)

    def start(self):
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self):
        if self._step_idx >= len(self._steps):
            self._timer.stop()
            self.finished.emit()
            self.close()
            return
        self._step_elapsed += float(self._timer.interval())
        _, _, duration, _ = self._steps[self._step_idx]
        if self._step_elapsed >= duration:
            self._step_elapsed = 0.0
            self._step_idx += 1
            if self._step_idx >= len(self._steps):
                self._timer.stop()
                self.finished.emit()
                self.close()
                return
        self.update()

    def paintEvent(self, event):
        if self._step_idx >= len(self._steps):
            return
        label, color, duration, is_go = self._steps[self._step_idx]
        t = min(1.0, self._step_elapsed / max(1.0, duration))
        eased = _ease_out_cubic(t)

        W, H = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            fx_enabled = self._is_fx_enabled("fx_timer_321go")
            if not fx_enabled:
                scale = 1.0
                p.setOpacity(1.0)
            elif is_go:
                # GO! fades out while scaling 1.0 → 1.5
                scale = 1.0 + 0.5 * eased
                opacity = max(0.0, 1.0 - eased)
                p.setOpacity(opacity)
            else:
                # Numbers scale 2.0 → 1.0 and spin 360° → 0°
                scale = 2.0 - eased
                p.setOpacity(1.0)

            font_size = int(80 * scale)
            font = QFont("Segoe UI", max(12, font_size), QFont.Weight.Bold)
            p.setFont(font)

            if fx_enabled and not is_go:
                # Spin animation: rotate from 360° → 0° as eased goes 0→1
                angle = 360.0 * (1.0 - eased)
                p.save()
                p.translate(W / 2, H / 2)
                p.rotate(angle)
                p.translate(-W / 2, -H / 2)

            if fx_enabled:
                # Glow effect
                glow_col = QColor(color.red(), color.green(), color.blue(), 60)
                for r in range(4, 0, -1):
                    gp = QPen(glow_col)
                    gp.setWidth(r * 3)
                    p.setPen(gp)
                    p.drawText(QRect(0, 0, W, H),
                               Qt.AlignmentFlag.AlignCenter, label)

            # Main text
            p.setPen(QPen(color))
            p.drawText(QRect(0, 0, W, H),
                       Qt.AlignmentFlag.AlignCenter, label)

            if fx_enabled and not is_go:
                p.restore()
        finally:
            try:
                p.end()
            except Exception:
                pass
