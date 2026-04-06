"""Achievement toast overlay and queue manager."""
from __future__ import annotations

import os
import re
import json
import sys

from typing import Optional

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QObject
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QTransform, QPixmap,
    QPainter, QImage, QPen,
)

from ui.overlay_base import (
    _OverlayFxMixin,
    _theme_bg_qcolor,
    _get_page_accent,
    _get_page_accents_list,
    _force_topmost,
    _start_topmost_timer,
)
from theme import get_theme_color
from gl_effects_opengl import (
    ParticleBurst, NeonRingExpansion, TypewriterReveal, IconBounce,
    SlideMotion, EnergyFlash,
    GodRayBurst, ConfettiShower, HologramFlicker, ShockwaveRipple,
)

try:
    import sound as _sound_mod
except Exception:
    _sound_mod = None


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


class AchToastWindow(_OverlayFxMixin, QWidget):
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
            Qt.WindowType.Tool
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

        low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))

        # --- Burst particle animation ---
        is_level_up = (self._rom == "__levelup__")
        self._burst = ParticleBurst(
            count=max(5, int(20 * self._get_fx_intensity("fx_toast_burst_particles"))),
            color=QColor(get_theme_color(self.parent_gui.cfg, "accent")),
        )
        self._burst_img_margin = 80
        if self._is_fx_enabled("fx_toast_burst_particles"):
            self._burst.start()

        # --- Neon ring pulse (level-up only) ---
        _neon_intensity = self._get_fx_intensity("fx_toast_neon_rings")
        self._ring = NeonRingExpansion(
            ring_count=max(1, int(4 * _neon_intensity)),
            delays=[0.0, 150.0, 300.0, 450.0],
            duration=max(200.0, 550.0 * _neon_intensity),
        )
        if is_level_up and self._is_fx_enabled("fx_toast_neon_rings"):
            self._ring.start()

        # --- Energy flash for level-up ---
        self._flash = EnergyFlash(duration=300.0, start_alpha=180)
        if is_level_up and self._is_fx_enabled("fx_toast_energy_flash"):
            self._flash.start()

        # --- Typewriter reveal (title line1) ---
        self._typewriter = TypewriterReveal()
        self._tw_cursor_timer = QTimer(self)
        self._tw_cursor_timer.setInterval(500)
        self._tw_cursor_timer.timeout.connect(self._tw_cursor_blink)
        if self._is_fx_enabled("fx_toast_typewriter"):
            self._typewriter.start()
            self._tw_cursor_timer.start()

        # --- Icon bounce animation ---
        self._bounce = IconBounce(duration=400.0, start_scale=1.3)
        if self._is_fx_enabled("fx_toast_icon_bounce"):
            self._bounce.start()

        # --- Slide-in/slide-out entry/exit animation ---
        self._slide_motion = SlideMotion(entry_duration=250.0, exit_duration=200.0, distance=60)
        self._motion_timer = QTimer(self)
        self._motion_timer.setInterval(16)
        self._motion_timer.timeout.connect(self._motion_tick)
        if self._is_fx_enabled("fx_toast_slide_motion"):
            self._slide_motion.start_entry()
            self._motion_timer.start()

        # --- God-Ray Burst ---
        self._god_rays = GodRayBurst(intensity=self._get_fx_intensity("fx_toast_god_rays"))
        if self._is_fx_enabled("fx_toast_god_rays"):
            self._god_rays.start()

        # --- Confetti Shower ---
        self._confetti = ConfettiShower(intensity=self._get_fx_intensity("fx_toast_confetti"))
        if self._is_fx_enabled("fx_toast_confetti"):
            self._confetti.start()

        # --- Hologram Flicker ---
        self._hologram = HologramFlicker()
        if self._is_fx_enabled("fx_toast_hologram_flicker"):
            self._hologram.start()

        # --- Shockwave Ripple ---
        self._shockwave = ShockwaveRipple(intensity=self._get_fx_intensity("fx_toast_shockwave"))
        if self._is_fx_enabled("fx_toast_shockwave"):
            self._shockwave.start()

        # Unified animation timer — advances all visual effects at 16ms and renders once
        self._fx_timer = QTimer(self)
        self._fx_timer.setInterval(16)
        self._fx_timer.timeout.connect(self._fx_tick)
        self._fx_timer.start()

        # Post-processing widget (drawn on top of toast content)
        from .overlay import PostProcessingWidget
        self._pp_widget = PostProcessingWidget(self, overlay_type="toast")

        # Hide before first render to prevent a single-frame flash at the wrong
        # position: on frame 0 slide_offset is at its maximum value and burst_margin
        # may be non-zero, which shifts the window far from its intended position.
        # The slide animation fades opacity 0→1 naturally; when slide motion is
        # disabled, _render_and_place sets opacity=1.0 on the first render.
        self.setWindowOpacity(0)
        self._render_and_place()
        self._timer.start()
        self.raise_()
        _start_topmost_timer(self)

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._remaining = 0
            try:
                self._timer.stop()
            except Exception:
                pass
            # Start exit animation if available and enabled, otherwise close immediately
            if not getattr(self, "_is_closing", False):
                if self._is_fx_enabled("fx_toast_slide_motion") and hasattr(self, "_motion_timer"):
                    # If entry animation is still running, snap it to completion first
                    if self._slide_motion.is_entry_active():
                        self._slide_motion.complete_entry()
                    if not self._slide_motion.is_exit_active():
                        # Trigger exit animation
                        self._slide_motion.start_exit()
                        self._motion_timer.start()
                else:
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
        # Stop all animation timers
        for attr in ('_fx_timer', '_tw_cursor_timer', '_timer', '_motion_timer'):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
        # Stop post-processing timer
        pp = getattr(self, '_pp_widget', None)
        if pp is not None:
            try:
                pp.stop_timer()
            except Exception:
                pass
        super().closeEvent(e)

    def _icon_pixmap(self, size: int = 40) -> QPixmap:
        emoji = ""
        try:
            if self._rom == "__levelup__":
                emoji = "⬆️"
            else:
                watcher = getattr(self.parent_gui, "watcher", None)
                if watcher:
                    cache = getattr(watcher, "_rom_emoji_cache", {})
                    emoji = cache.get(self._rom, "")
                    if not emoji and hasattr(watcher, "_resolve_emoji_for_rom"):
                        emoji = watcher._resolve_emoji_for_rom(self._rom)
        except Exception:
            emoji = ""

        if emoji:
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                if sys.platform == "win32":
                    font_name = "Segoe UI Emoji"
                elif sys.platform == "darwin":
                    font_name = "Apple Color Emoji"
                else:
                    font_name = "Noto Color Emoji"
                font = QFont(font_name, int(size * 0.75))
                p.setFont(font)
                p.drawText(QRect(0, 0, size, size),
                           Qt.AlignmentFlag.AlignCenter, emoji)
            finally:
                p.end()
            return pm

        # Fallback: original gold/white circles
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
        body_pt = 15
        title_pt = max(body_pt + 2, int(round(body_pt * 1.35)))

        is_level_up = (self._rom == "__levelup__")
        if is_level_up:
            border_color = QColor(get_theme_color(self.parent_gui.cfg, "primary"))
            line1 = "LEVEL UP!"
            line2 = self._title.replace("LEVEL UP!  ", "").strip()
            line3 = ""
        else:
            border_color = QColor(get_theme_color(self.parent_gui.cfg, "border"))
            raw_title = self._title or "Achievement unlocked"
            rom = self._rom or ""
            line3 = ""

            if '\n' in raw_title:
                # Multi-line toast format (e.g. VPS-ID backfill): "title\nrom\nline3"
                parts = raw_title.split('\n', 2)
                line1 = parts[0].strip()
                line2 = parts[1].strip() if len(parts) > 1 else (rom or "")
                line3 = parts[2].strip() if len(parts) > 2 else ""
            else:
                # Strip ROM prefix from title (e.g. "cc_13 – GOLD MINE MB: 1" → "GOLD MINE MB: 1")
                prefix = f"{rom} \u2013 "
                if rom and raw_title.startswith(prefix):
                    line1 = raw_title[len(prefix):]
                else:
                    prefix2 = f"{rom} - "
                    if rom and raw_title.startswith(prefix2):
                        line1 = raw_title[len(prefix2):]
                    else:
                        line1 = raw_title

                if not rom:
                    # Global achievement – no table name in toast
                    line2 = ""
                else:
                    # Resolve ROM to clean table name (without version number)
                    table_name = ""
                    try:
                        watcher = getattr(self.parent_gui, "watcher", None)
                        if watcher:
                            romnames = getattr(watcher, "ROMNAMES", {}) or {}
                            from watcher_core import _strip_version_from_name
                            table_name = _strip_version_from_name(romnames.get(rom, ""))
                    except Exception:
                        pass

                    line2 = table_name if table_name else _strip_version_from_name(rom)

        # Set typewriter full text on first call (now applies to title/line1)
        if self._typewriter.is_active() and not self._typewriter.full_text:
            self._typewriter.set_text(line1)

        # Theme-dynamic colors
        title_color = QColor(get_theme_color(self.parent_gui.cfg, "accent"))
        text_color = QColor("#FFFFFF")  # White
        levelup_color = QColor(get_theme_color(self.parent_gui.cfg, "primary"))  # primary for level-up line1

        # Apply typewriter reveal to title (line1); use full text for sizing, partial for display
        title_for_size = line1  # always use full text for width calculation
        if self._is_fx_enabled("fx_toast_typewriter") and self._typewriter.is_active() and self._typewriter.full_text:
            title = self._typewriter.current_text(show_cursor=True)
        else:
            title = line1
        # Second line is always static (no typewriter)
        sub = line2
        sub_for_size = line2  # always use full text for width calculation
        line3_pt = max(body_pt - 3, 10)
        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt, QFont.Weight.Bold if is_level_up else QFont.Weight.Normal)
        f_line3 = QFont(font_family, line3_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)
        fm_line3 = QFontMetrics(f_line3)
        icon_sz = max(28, int(body_pt * 2.0))
        pad = max(12, int(body_pt * 0.8))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_w = fm_title.horizontalAdvance(title_for_size)
        sub_w = fm_body.horizontalAdvance(sub_for_size) if sub_for_size else 0
        line3_w = fm_line3.horizontalAdvance(line3) if line3 else 0
        text_w = max(title_w, sub_w, line3_w)
        # Use full text sizes for height calculation to keep window stable during typewriter
        text_h = fm_title.height() + (vgap + fm_body.height() if sub_for_size else 0) + (vgap + fm_line3.height() if line3 else 0)
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
        
        bg = _theme_bg_qcolor(self.parent_gui.cfg, 245)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        radius = 16
        p.drawRoundedRect(0, 0, W, H, radius, radius)

        # Outer glow for toast
        glow_pen = QPen(QColor(border_color.red(), border_color.green(), border_color.blue(), 50))
        glow_pen.setWidth(4)
        p.setPen(glow_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(3, 3, W - 6, H - 6, radius - 2, radius - 2)

        pen = QPen(border_color)
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, W - 2, H - 2, radius, radius)
        
        # Icon bounce animation: apply scale and Y-offset when effect is enabled
        if self._is_fx_enabled("fx_toast_icon_bounce") and self._bounce.is_active():
            icon_scale, icon_y_offset = self._bounce.get_scale_and_offset()
            actual_icon_sz = int(icon_sz * icon_scale)
        else:
            actual_icon_sz = icon_sz
            icon_y_offset = 0
        pm = self._icon_pixmap(actual_icon_sz)
        iy = max(0, int((H - actual_icon_sz) / 2) + icon_y_offset)
        p.drawPixmap(pad, iy, pm)
        x_text = pad + icon_sz + gap
        text_top = int((H - text_h) / 2)
        
        p.setPen(levelup_color if is_level_up else title_color)
        p.setFont(f_title)
        p.drawText(QRect(x_text, text_top, W - x_text - pad, fm_title.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        if sub:
            p.setPen(title_color if is_level_up else text_color)
            p.setFont(f_body)
            p.drawText(QRect(x_text, text_top + fm_title.height() + vgap,
                             W - x_text - pad, fm_body.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)
        if line3:
            p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "primary")))
            p.setFont(f_line3)
            line3_y = text_top + fm_title.height() + vgap + (fm_body.height() + vgap if sub_for_size else 0)
            p.drawText(QRect(x_text, line3_y, W - x_text - pad, fm_line3.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line3)
        # Energy flash overlay for level-up entry
        if is_level_up and self._is_fx_enabled("fx_toast_energy_flash") and self._flash.is_active():
            self._flash.draw(p, W, H, radius,
                             QColor(get_theme_color(self.parent_gui.cfg, "primary")))
        # God-Ray Burst
        if self._is_fx_enabled("fx_toast_god_rays") and self._god_rays.is_active():
            self._god_rays.draw(p, QRect(0, 0, W, H))
        # Confetti Shower
        if self._is_fx_enabled("fx_toast_confetti") and self._confetti.is_active():
            self._confetti.draw(p, QRect(0, 0, W, H))
        # Hologram Flicker (icon area)
        if self._is_fx_enabled("fx_toast_hologram_flicker") and self._hologram.is_active():
            self._hologram.draw(p, QRect(pad, iy, actual_icon_sz, actual_icon_sz))
        # Shockwave Ripple
        if self._is_fx_enabled("fx_toast_shockwave") and self._shockwave.is_active():
            self._shockwave.draw(p, QRect(0, 0, W, H))
        p.end()

        portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))

        # Draw burst particles and neon ring — works in both landscape and portrait.
        # The expanded image is built before rotation so particle positions remain
        # consistent; rotating the whole expanded image produces correct portrait output.
        # Only expand if the relevant fx effects are enabled (live check).
        _burst_active = self._is_fx_enabled("fx_toast_burst_particles") and self._burst.is_active()
        _ring_active = self._is_fx_enabled("fx_toast_neon_rings") and self._ring.is_active()
        burst_margin = self._burst_img_margin if (_burst_active or _ring_active) else 0
        if burst_margin > 0:
            EW = W + 2 * burst_margin
            EH = H + 2 * burst_margin
            expanded = QImage(EW, EH, QImage.Format.Format_ARGB32_Premultiplied)
            expanded.fill(Qt.GlobalColor.transparent)
            ep = QPainter(expanded)
            ep.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                ep.drawImage(burst_margin, burst_margin, img)
                cx = EW // 2
                cy = EH // 2
                # Burst particles
                if _burst_active:
                    self._burst.draw(ep, cx, cy)
                # Neon rings (level-up)
                if _ring_active:
                    self._ring.draw(ep, cx, cy,
                                    QColor(get_theme_color(self.parent_gui.cfg, "primary")))
            finally:
                try:
                    ep.end()
                except Exception:
                    pass
            img = expanded

        if portrait:
            ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
            angle = -90 if ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        return img

    def _render_and_place(self):
        try:
            img = self._compose_image()
            EW, EH = img.width(), img.height()
            ov = self.parent_gui.cfg.OVERLAY or {}
            portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            # Determine the burst margin embedded in the image (both landscape and portrait)
            burst_margin = self._burst_img_margin if (
                (self._is_fx_enabled("fx_toast_burst_particles") and self._burst.is_active()) or
                (self._is_fx_enabled("fx_toast_neon_rings") and self._ring.is_active())
            ) else 0
            W = EW - 2 * burst_margin
            H = EH - 2 * burst_margin
            use_saved = bool(ov.get("ach_toast_saved", ov.get("ach_toast_custom", False)))
            screens = QApplication.screens() or []
            geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
            for s in screens[1:]:
                geo = geo.united(s.availableGeometry())
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

            # Apply slide-in/slide-out offset and opacity (only when effect is enabled)
            if self._is_fx_enabled("fx_toast_slide_motion"):
                slide_offset, opacity = self._slide_motion.get_offset_and_opacity()
            else:
                slide_offset, opacity = 0, 1.0

            if portrait:
                # In portrait mode the image is rotated 90°, so the logical "bottom"
                # maps to the left or right side of the screen.  Apply slide offset to
                # the X axis; direction depends on the rotation direction.
                ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
                if ccw:
                    # CCW (-90°): logical bottom = right side of the screen
                    # → slide in from the right (positive offset, decreases to 0).
                    x_win = x - burst_margin + slide_offset
                else:
                    # CW (+90°): logical bottom = left side of the screen
                    # → slide in from the left (negative offset, increases to 0).
                    x_win = x - burst_margin - slide_offset
                y_win = y - burst_margin
            else:
                # Landscape: slide along Y axis (bottom-to-top) as before.
                x_win = x - burst_margin
                y_win = y - burst_margin + slide_offset
            self.setGeometry(x_win, y_win, EW, EH)
            self._label.setGeometry(0, 0, EW, EH)
            self._label.setPixmap(QPixmap.fromImage(img))
            self.setWindowOpacity(opacity)
            self.show()
            self.raise_()
            # Size and raise the post-processing widget above the label
            if hasattr(self, '_pp_widget') and self._pp_widget._any_pp_enabled():
                if burst_margin > 0:
                    self._pp_widget.setGeometry(burst_margin, burst_margin, W, H)
                else:
                    self._pp_widget.setGeometry(0, 0, EW, EH)
                if not self._pp_widget.isVisible():
                    self._pp_widget.show()
                self._pp_widget.raise_()
            elif hasattr(self, '_pp_widget') and self._pp_widget.isVisible():
                # PP was disabled mid-toast — hide the widget
                self._pp_widget.hide()
            try:
                import win32gui, win32con 
                hwnd = int(self.winId())
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
                )
            except Exception:
                pass
        except Exception as e:
            print(f"[TOAST] render_and_place failed: {e}")

    def _motion_tick(self):
        """Advance slide-in (entry) or slide-out (exit) animation."""
        dt = 16.0
        was_exit = self._slide_motion.is_exit_active()
        still_active = self._slide_motion.tick(dt)
        if not still_active and was_exit:
            self._motion_timer.stop()
            if not getattr(self, "_is_closing", False):
                self._is_closing = True
                try:
                    self.finished.emit()
                except Exception:
                    pass
                QTimer.singleShot(50, self.close)
            return
        if not still_active:
            self._motion_timer.stop()
        self._render_and_place()

    def _fx_tick(self):
        """Unified animation tick: advances all visual effects once at 16ms and re-renders."""
        dt = 16.0
        changed = False

        # Burst particles
        if self._burst.is_active():
            self._burst.tick(dt)
            if not self._burst.is_active():
                self._burst_img_margin = 0
            changed = True

        # Neon ring expansion (level-up)
        if self._ring.is_active():
            max_r = self.width() if self.width() > 0 else 300
            self._ring.tick(dt, max_r=float(max_r))
            changed = True

        # Typewriter (applies to title/line1)
        if self._typewriter.is_active() and self._typewriter.full_text:
            self._typewriter.tick(dt)
            changed = True
            if not self._typewriter.is_active():
                if hasattr(self, '_tw_cursor_timer'):
                    self._tw_cursor_timer.stop()

        # Icon bounce
        if self._bounce.is_active():
            self._bounce.tick(dt)
            changed = True

        # Energy flash (level-up only)
        if self._flash.is_active():
            self._flash.tick(dt)
            changed = True

        # God-Ray Burst
        if self._god_rays.is_active():
            self._god_rays.tick(dt)
            changed = True

        # Confetti Shower
        if self._confetti.is_active():
            self._confetti.tick(dt)
            changed = True

        # Hologram Flicker
        if self._hologram.is_active():
            self._hologram.tick(dt)
            changed = True

        # Shockwave Ripple
        if self._shockwave.is_active():
            self._shockwave.tick(dt)
            changed = True

        if changed:
            self._render_and_place()

        # Stop unified timer when all visual effects have completed
        if (not self._burst.is_active() and
                not self._ring.is_active() and
                not self._typewriter.is_active() and
                not self._bounce.is_active() and
                not self._flash.is_active() and
                not self._god_rays.is_active() and
                not self._confetti.is_active() and
                not self._hologram.is_active() and
                not self._shockwave.is_active()):
            if hasattr(self, '_fx_timer'):
                self._fx_timer.stop()

    def _tw_cursor_blink(self):
        """Toggle cursor visibility for typewriter effect."""
        self._typewriter.toggle_cursor()
        if self._typewriter.is_active():
            self._render_and_place()

class AchToastManager(QObject):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.parent_gui = parent
        self._queue: list[tuple[str, str, int]] = []
        self._active = False
        self._active_window: Optional[AchToastWindow] = None
        self._sound_played = False
        self._levelup_sound_played = False

    def enqueue(self, title: str, rom: str, seconds: int = 5):
        """Add a toast to the queue."""
        self._queue.append((title, rom, seconds))
        if not self._active:
            self._show_next()

    def enqueue_level_up(self, title: str, level_number: int, seconds: int = 6):
        """Enqueue a special level-up toast."""
        self._queue.append((title, "__levelup__", seconds))
        if not self._active:
            self._show_next()

    def _show_next(self):
        if not self._queue:
            self._active = False
            self._active_window = None
            self._sound_played = False
            self._levelup_sound_played = False
            return

        # Immediately hide and close any lingering previous window so it is never
        # visible at the same time as the incoming toast (the old window may still
        # be on-screen waiting for its QTimer.singleShot close callback).
        old = self._active_window
        self._active_window = None
        if old is not None:
            try:
                old.hide()
                old.close()
            except Exception:
                pass

        self._active = True
        title, rom, seconds = self._queue.pop(0)
        try:
            win = AchToastWindow(self.parent_gui, title, rom, seconds)
        except Exception:
            self._active = False
            QTimer.singleShot(100, self._show_next)
            return
        win.finished.connect(self._on_finished)
        self._active_window = win

        if _sound_mod is not None:
            try:
                if rom == "__levelup__":
                    if not self._levelup_sound_played:
                        _sound_mod.play_sound(self.parent_gui.cfg, "level_up")
                        self._levelup_sound_played = True
                else:
                    if not self._sound_played:
                        _sound_mod.play_sound(self.parent_gui.cfg, "achievement_unlock")
                        self._sound_played = True
            except Exception:
                pass

    def _on_finished(self):
        self._active_window = None
        self._active = False
        QTimer.singleShot(250, self._show_next)
