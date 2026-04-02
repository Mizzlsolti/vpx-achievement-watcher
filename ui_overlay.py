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

from watcher_core import APP_DIR, register_raw_input_for_window, p_aweditor, p_highlights, load_json, f_custom_achievements_progress
from theme import get_theme_color, get_theme, DEFAULT_THEME
from gl_effects import (
    draw_glow_border as _draw_glow_border,
    ease_out_bounce as _ease_out_bounce,
    ease_out_cubic as _ease_out_cubic,
    EffectsWidget as OverlayEffectsWidget,
    ShineWidget as _OverlayShineWidget,
    HighlightWidget as _OverlayHighlightWidget,
    ParticleBurst, NeonRingExpansion, TypewriterReveal, IconBounce,
    SlideMotion, EnergyFlash, BreathingPulse, CarouselSlide,
    SnapScale, HeatPulse, ScanIn, GlowSweep, ColorMorph, GlitchFrame,
)

try:
    import sound as _sound_mod
except Exception:
    _sound_mod = None


def _theme_bg_qcolor(cfg, alpha: int = 245) -> QColor:
    """Return the active theme bg colour as a QColor with *alpha* (0–255)."""
    h = get_theme_color(cfg, "bg").lstrip("#")
    return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _theme_bg_rgba_css(cfg, alpha: int = 245) -> str:
    """Return 'rgba(r,g,b,alpha)' for use in Qt stylesheets."""
    h = get_theme_color(cfg, "bg").lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _get_page_accents_list(cfg) -> list:
    """Return the page accent hex strings for the active theme.

    If the theme defines ``page_accents``, those are used directly.
    Otherwise a four-entry fallback is derived from the theme's
    primary/accent/border colours so the overlay always respects the
    current theme rather than falling back to hardcoded Neon-Blue values.
    """
    theme_id = (cfg.OVERLAY or {}).get("theme", DEFAULT_THEME)
    theme = get_theme(theme_id)
    accents = theme.get("page_accents", [])
    if accents:
        return accents
    # Dynamic fallback: build four entries from the theme's own colours.
    default = get_theme(DEFAULT_THEME)
    primary = theme.get("primary", default["primary"])
    accent  = theme.get("accent",  default["accent"])
    border  = theme.get("border",  primary)
    return [primary, accent, border, accent]


def _get_page_accent(cfg, idx: int) -> QColor:
    """Return the page accent QColor for page *idx* from the active theme."""
    accents = _get_page_accents_list(cfg)
    h = accents[idx % len(accents)].lstrip("#")
    return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))



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


class OverlayNavArrows(QWidget):
    """Pulsating ice-blue navigation arrows displayed over the main overlay to indicate page cycling."""

    def __init__(self, parent: "OverlayWindow"):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._breathing_pulse = BreathingPulse(speed=0.13)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(80)
        self._pulse_timer.timeout.connect(self._on_tick)
        self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent()
        low_perf = False
        try:
            low_perf = bool(parent.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
        except Exception:
            pass
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
        try:
            low_perf = bool(parent.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
        except Exception:
            pass

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
                alpha = 110 + int(120 * amp)
                scale = 0.9 + 0.2 * amp
                wobble = 2.0 * self._breathing_pulse.get_sin()
            base_h = 18
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

# Per-page accent colours for the main overlay – kept only as a last-resort
# emergency fallback.  All themes now define their own ``page_accents`` list
# and _get_page_accents_list() derives a dynamic fallback from the theme's
# primary/accent/border colours, so this static list should rarely (if ever)
# be reached in practice.
_OVERLAY_PAGE_ACCENTS = [
    QColor(0, 229, 255),    # page 0: cyan (default/highlights)
    QColor(255, 127, 0),    # page 1: orange (achievement progress)
    QColor(0, 200, 110),    # page 2: green (other views)
    QColor(180, 80, 255),   # page 3: purple (cloud/VPS)
]


class OverlayWindow(QWidget):
    TITLE_OFFSET_X = 0
    TITLE_OFFSET_Y = 0
    CLAMP_TITLE = True
    ROTATION_DEBOUNCE_MS = 1

    def _resolve_background_url(self, bg: str) -> str | None:
        def is_img(p: str) -> bool:
            return p.lower().endswith((".png", ".jpg", ".jpeg"))
        if isinstance(bg, str) and bg and bg.lower() != "auto":
            if os.path.isfile(bg) and is_img(bg):
                return bg.replace("\\", "/")
        for fn in ("overlay_bg.png", "overlay_bg.jpg", "overlay_bg.jpeg"):
            p = os.path.join(APP_DIR, fn)
            if os.path.isfile(p):
                return p.replace("\\", "/")
        return None

    def _show_live_unrotated(self):
        try:
            self.rotated_label.hide()
        except Exception:
            pass
        try:
            self.container.show()
            self.text_container.show()
            if not getattr(self, '_fullsize_mode', False):
                self.title.show()
            self.body.show()
        except Exception:
            pass
        if self._nav_arrows_active:
            self._nav_arrows.raise_()
        # Ensure all animation overlay widgets are raised above the live content in
        # landscape mode. In landscape the container/text_container are live widgets
        # stacked inside OverlayWindow; animation widgets must be on top of them.
        W, H = self.width(), self.height()
        if hasattr(self, '_effects_widget'):
            try:
                _ov = self.parent_gui.cfg.OVERLAY
                _low_perf = bool(_ov.get("low_performance_mode", False))
                _anim_glow = bool(_ov.get("fx_main_breathing_glow", _ov.get("anim_main_glow", True)))
                if not _low_perf and _anim_glow:
                    self._effects_widget.setGeometry(0, 0, W, H)
                    if not self._effects_widget.isVisible():
                        self._effects_widget.show()
                    self._effects_widget.raise_()
            except Exception:
                pass
        if hasattr(self, '_shine_widget') and self._shine_widget.isVisible():
            self._shine_widget.raise_()
        if hasattr(self, '_highlight_widget') and self._highlight_widget.isVisible():
            self._highlight_widget.raise_()
        if (getattr(self, '_transition_label', None) is not None
                and self._transition_label.isVisible()):
            self._transition_label.raise_()

    def _icon_local(self, key: str) -> str:
        use_emojis = not bool(self.parent_gui.cfg.OVERLAY.get("prefer_ascii_icons", False))
        if use_emojis:
            emoji_map = {
                "best_ball": "🔥",
                "extra_ball": "➕",
            }
            return emoji_map.get(key, "•")
        else:
            ascii_map = {
                "best_ball": "[BB]",
                "extra_ball": "[EB]",
            }
            return ascii_map.get(key, "[*]")

    def showEvent(self, e):
        super().showEvent(e)
        _force_topmost(self)
        if not self._ensuring:
            QTimer.singleShot(0, self._layout_positions)
            if self.portrait_mode:
                # Hide raw widgets immediately so the window never exposes
                # unrotated content while the rotation snapshot is being built.
                self.container.hide()
                self.text_container.hide()
                QTimer.singleShot(0, lambda: self.request_rotation(force=True))
            else:
                QTimer.singleShot(0, self._show_live_unrotated)
        W, H = self.width(), self.height()
        # Start effects overlay (glow border + floating particles).
        # In portrait mode when not in the controlled _ensuring path the rotation
        # snapshot is built asynchronously — starting the effects widget here would
        # show the glow animation on a blank/transparent window (dark background and
        # text not visible yet).  Defer to _apply_rotation_snapshot in that case; it
        # will raise the effects widget once the snapshot has been applied.
        _defer_effects = self.portrait_mode and not self._ensuring
        if hasattr(self, '_effects_widget') and not _defer_effects:
            low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
            anim_glow = bool(self.parent_gui.cfg.OVERLAY.get("fx_main_breathing_glow", self.parent_gui.cfg.OVERLAY.get("anim_main_glow", True)))
            if not low_perf and anim_glow:
                self._effects_widget.setGeometry(0, 0, W, H)
                self._effects_widget.show()
                self._effects_widget.raise_()
        # Size the shine and highlight overlay widgets
        if hasattr(self, '_shine_widget'):
            self._shine_widget.setGeometry(0, 0, W, H)
        if hasattr(self, '_highlight_widget'):
            self._highlight_widget.setGeometry(0, 0, W, H)
        # Resume animation timers that were interrupted by hideEvent
        if hasattr(self, '_score_spin_timer') and hasattr(self, '_score_display') and hasattr(self, '_score_target'):
            if self._score_display != self._score_target:
                if not self._score_spin_timer.isActive():
                    self._score_spin_timer.start()
        if hasattr(self, '_progress_bar_timer') and hasattr(self, '_progress_pct_current') and hasattr(self, '_progress_pct_target'):
            if abs(self._progress_pct_current - self._progress_pct_target) > 0.01:
                if not self._progress_bar_timer.isActive():
                    self._progress_bar_timer.start()
        if hasattr(self, '_transition_timer') and hasattr(self, '_transition_state'):
            if self._transition_state is not None:
                if not self._transition_timer.isActive():
                    self._transition_timer.start()
        # Restart the scrollable-list timer if there's more content than visible
        if hasattr(self, '_p2_timer') and hasattr(self, '_p2_rows') and self._p2_rows:
            visible = getattr(self, '_p2_visible', 10)
            if len(self._p2_rows) > visible and not self._p2_timer.isActive():
                self._p2_timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        if hasattr(self, '_effects_widget'):
            self._effects_widget.hide()
        if hasattr(self, '_score_spin_timer'):
            self._score_spin_timer.stop()
        if hasattr(self, '_progress_bar_timer'):
            self._progress_bar_timer.stop()
        if hasattr(self, '_transition_timer'):
            self._transition_timer.stop()
        if hasattr(self, '_shine_timer'):
            self._shine_timer.stop()
        if hasattr(self, '_highlight_timer'):
            self._highlight_timer.stop()
        if hasattr(self, '_p2_timer'):
            self._p2_timer.stop()


    def _alpha_bbox(self, img: QImage, min_alpha: int = 8) -> QRect:
        w, h = img.width(), img.height()
        if w == 0 or h == 0:
            return QRect(0, 0, 0, 0)
        top = None
        left = None
        right = -1
        bottom = -1
        for y in range(h):
            for x in range(w):
                if img.pixelColor(x, y).alpha() >= min_alpha:
                    if top is None:
                        top = y
                    bottom = y
                    if left is None or x < left:
                        left = x
                    if x > right:
                        right = x
        if top is None:
            return QRect(0, 0, 0, 0)
        return QRect(left, top, right - left + 1, bottom - top + 1)

    def _ref_screen_geometry(self) -> QRect:
        try:
            win = self.windowHandle()
            if win and win.screen():
                return win.screen().geometry()
            scr = QApplication.primaryScreen()
            if scr:
                return scr.geometry()
        except Exception:
            pass
        screens = QApplication.screens() or []
        return screens[0].geometry() if screens else QRect(0, 0, 1280, 720)

    def _register_raw_input(self):
        try:
            hwnd = int(self.winId())
            register_raw_input_for_window(hwnd)
        except Exception:
            pass

    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Watchtower Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ov = self.parent_gui.cfg.OVERLAY
        self.scale_pct = int(ov.get("scale_pct", 100))
        self.portrait_mode = bool(ov.get("portrait_mode", True))
        self.rotate_ccw = bool(ov.get("portrait_rotate_ccw", True))
        self.position = "center"
        self.lines_per_category = int(ov.get("lines_per_category", 5))
        
        self.font_family = ov.get("font_family", "Segoe UI")
        self._base_title_size = int(ov.get("base_title_size", 17))
        self._base_body_size = int(ov.get("base_body_size", 12))
        self._base_hint_size = int(ov.get("base_hint_size", 10))
        self._body_pt = self._base_body_size
        self._current_combined = None
        self._current_html = None
        self._p2_rows = None
        self._current_title = None
        self._rotation_pending = False
        self._apply_geometry()
        self.bg_url = self._resolve_background_url(ov.get("background", "auto"))
        self.container = QWidget(self)
        self.container.setObjectName("overlay_bg")
        self.container.setGeometry(0, 0, self.width(), self.height())
        _primary = get_theme_color(self.parent_gui.cfg, "primary")
        _bg_rgba = _theme_bg_rgba_css(self.parent_gui.cfg, 252)
        if self.bg_url:
            css = ("QWidget#overlay_bg {"
                   f"border-image: url('{self.bg_url}') 0 0 0 0 stretch stretch;"
                   f"background:{_bg_rgba};border:2px solid {_primary};border-radius:18px;}}")
        else:
            css = (f"QWidget#overlay_bg {{background:{_bg_rgba};"
                   f"border:2px solid {_primary};border-radius:18px;}}")
        self.container.setStyleSheet(css)
        self.text_container = QWidget(self)
        self.text_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.text_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.text_container.setGeometry(0, 0, self.width(), self.height())
        self.title = QLabel("Highlights", self.text_container)
        self.body = QLabel(self.text_container)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setWordWrap(True)
        for lab in (self.title, self.body):
            lab.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            lab.setAutoFillBackground(False)
            
        self.title.setStyleSheet("color:#FFFFFF;background:transparent;")
        self.body.setStyleSheet("color:#FFFFFF;background:transparent;")
        
        self._apply_scale(self.scale_pct)
        self.rotated_label = QLabel(self)
        self.rotated_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rotated_label.setStyleSheet("background:transparent;")
        self.rotated_label.hide()
        self._rot_in_progress = False
        self._rot_deferred = False
        self._ensuring = False
        self._font_update_in_progress = False
        self._nav_arrows = OverlayNavArrows(self)
        self._nav_arrows_active = False
        self._layout_positions()
        QTimer.singleShot(0, self._register_raw_input)
        _start_topmost_timer(self)
        # Page-2 (Achievement Progress) Python-level scroll support
        self._p2_timer = QTimer(self)
        self._p2_timer.setInterval(1500)
        self._p2_timer.timeout.connect(self._p2_tick)
        self._p2_rows: list = []
        self._p2_offset: int = 0
        self._p2_visible: int = 10
        self._p2_header: str = ""
        self._p2_css: str = ""
        # Score counter spin state
        self._score_display: int = 0
        self._score_target: int = 0
        self._score_spin_timer = QTimer(self)
        self._score_spin_timer.setInterval(50)
        self._score_spin_timer.timeout.connect(self._score_spin_tick)
        # Animated progress bar state
        self._progress_pct_current: float = 0.0
        self._progress_pct_target: float = 0.0
        self._progress_bar_timer = QTimer(self)
        self._progress_bar_timer.setInterval(50)
        self._progress_bar_timer.timeout.connect(self._progress_bar_tick)
        # Slide/glitch transition state
        self._transition_state: dict | None = None
        self._transition_label: QLabel | None = None
        self._transition_timer = QTimer(self)
        self._transition_timer.setInterval(16)
        self._transition_timer.timeout.connect(self._transition_tick)
        # Glitch frame effect primitive
        self._glitch_frame = GlitchFrame()
        # Effects widget (glow border + floating particles)
        self._effects_widget = OverlayEffectsWidget(self)
        # Per-page accent colour index
        self._page_index: int = 0
        # Shine/sweep effect for progress bar
        self._shine_widget = _OverlayShineWidget(self)
        self._shine_timer = QTimer(self)
        self._shine_timer.setInterval(16)
        self._shine_timer.timeout.connect(self._shine_tick)
        # Value highlight/pulse flash
        self._highlight_widget = _OverlayHighlightWidget(self)
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setInterval(16)
        self._highlight_timer.timeout.connect(self._highlight_tick)

    def request_rotation(self, force: bool = False):
        if not self.portrait_mode:
            return
        if self._rotation_pending and not force:
            return
        self._rotation_pending = True
        def _do():
            try:
                self._apply_rotation_snapshot(force=True)
            finally:
                self._rotation_pending = False
        QTimer.singleShot(self.ROTATION_DEBOUNCE_MS if not force else 0, _do)

    def set_nav_arrows(self, active: bool):
        """Show or hide the pulsating page-navigation arrows on the overlay."""
        self._nav_arrows_active = bool(active)
        if active:
            self._nav_arrows.setGeometry(0, 0, self.width(), self.height())
            self._nav_arrows.show()
            self._nav_arrows.raise_()
        else:
            self._nav_arrows.hide()

    def _apply_geometry(self):
        ref = self._ref_screen_geometry()
        if self.portrait_mode:
            base_h = int(ref.height() * 0.55)
            base_w = int(base_h * 9 / 16)
        else:
            base_w = int(ref.width() * 0.40)
            base_h = int(ref.height() * 0.30)
        w = max(120, int(base_w * self.scale_pct / 100))
        h = max(120, int(base_h * self.scale_pct / 100))
        screens = QApplication.screens() or []
        if screens:
            vgeo = screens[0].geometry()
            for s in screens[1:]:
                vgeo = vgeo.united(s.geometry())
        else:
            vgeo = QRect(0, 0, 1280, 720)
        ov = self.parent_gui.cfg.OVERLAY
        if ov.get("use_xy", False):
            x = int(ov.get("pos_x", 0))
            y = int(ov.get("pos_y", 0))
        else:
            pad = 20
            pos = (getattr(self, "position", "center") or "center").lower()
            mapping = {
                "top-left": (vgeo.left() + pad, vgeo.top() + pad),
                "top-right": (vgeo.right() - w - pad, vgeo.top() + pad),
                "bottom-left": (vgeo.left() + pad, vgeo.bottom() - h - pad),
                "bottom-right": (vgeo.right() - w - pad, vgeo.bottom() - h - pad),
                "center-top": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.top() + pad),
                "center-bottom": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.bottom() - h - pad),
                "center-left": (vgeo.left() + pad, vgeo.top() + (vgeo.height() - h) // 2),
                "center-right": (vgeo.right() - w - pad, vgeo.top() + (vgeo.height() - h) // 2),
                "center": (vgeo.left() + (vgeo.width() - w) // 2, vgeo.top() + (vgeo.height() - h) // 2)
            }
            x, y = mapping.get(pos, mapping["center"])
        self.setGeometry(x, y, w, h)
        if hasattr(self, "container"):
            self.container.setGeometry(0, 0, w, h)
        if hasattr(self, "text_container"):
            self.text_container.setGeometry(0, 0, w, h)
        if hasattr(self, '_shine_widget'):
            self._shine_widget.setGeometry(0, 0, w, h)
        if hasattr(self, '_highlight_widget'):
            self._highlight_widget.setGeometry(0, 0, w, h)

    def _layout_positions(self):
        if getattr(self, '_rot_in_progress', False):
            return
        self._layout_positions_for(self.width(), self.height())
        if self.portrait_mode:
            self.request_rotation(force=True)

    def _layout_positions_for(self, w: int, h: int, portrait_pre_render: bool = False):
        if hasattr(self, "text_container"):
            self.text_container.setGeometry(0, 0, w, h)
        if getattr(self, '_fullsize_mode', False):
            self.title.hide()
            self.body.setGeometry(0, 0, w, h)
            return
        pad = 24
        try:
            self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.title.setIndent(0)
            self.title.setMargin(0)
            self.title.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.title.adjustSize()
        t_h = self.title.sizeHint().height()
        if not self.portrait_mode:
            self.title.setGeometry(0, pad, w, t_h)
            body_top = self.title.y() + t_h + 10
            body_h = h - body_top - pad
            body_w = int(w * 0.9)
            body_x = (w - body_w) // 2
            try:
                self.body.setContentsMargins(0, 0, 0, 0)
            except Exception:
                pass
            self.body.setGeometry(body_x, body_top, body_w, max(80, body_h))
            return
        self.title.setGeometry(0, pad, w, t_h)
        body_w = int(w * 0.92)
        body_x = (w - body_w) // 2
        body_top = pad + t_h + 10
        body_h = h - body_top - pad
        try:
            self.body.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.body.setGeometry(body_x, body_top, body_w, max(80, body_h))

    def _apply_scale(self, scale_pct: int):
        r = scale_pct / 100.0
        body_pt = max(4, int(round(self._base_body_size * r)))
        title_pt = max(6, int(round(body_pt * 1.35)))
        
        self._body_pt = body_pt
        self.title.setFont(QFont(self.font_family, title_pt, QFont.Weight.Bold))
        self.body.setFont(QFont(self.font_family, body_pt))
        self.body.setStyleSheet(f"color:#FFFFFF;background:transparent;font-size:{body_pt}pt;font-family:'{self.font_family}';")

    def _composition_mode_source_over(self):
        try:
            return QPainter.CompositionMode.CompositionMode_SourceOver
        except Exception:
            try:
                return getattr(QPainter, "CompositionMode_SourceOver")
            except Exception:
                return None

    def _apply_rotation_snapshot(self, force: bool = False):
        if not self.portrait_mode:
            # Delegate to _show_live_unrotated which handles all z-ordering for
            # animation overlay widgets in landscape mode.
            self._show_live_unrotated()
            return
        if getattr(self, "_rot_in_progress", False):
            # Queue a deferred re-render so the final state is always correct
            if not getattr(self, "_rot_deferred", False):
                self._rot_deferred = True
                QTimer.singleShot(50, self._deferred_rotation)
            return
        self._rot_in_progress = True
        # NOTE: _effects_widget is a sibling of text_container (not its child), so
        # text_container.render() will never capture it. Do NOT hide/show it here —
        # that would stop/restart its animation timer on every portrait refresh cycle,
        # causing visible flicker and jitter. Instead, simply re-raise it after the
        # snapshot label is raised so z-order is preserved.
        try:
            W, H = self.width(), self.height()
            if W <= 0 or H <= 0:
                return
            angle = -90 if getattr(self, "rotate_ccw", True) else 90
            if self.bg_url and os.path.isfile(self.bg_url):
                pm = QPixmap(self.bg_url)
                if not pm.isNull():
                    rot_pm = pm.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
                    scaled = rot_pm.scaled(W, H, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                           Qt.TransformationMode.SmoothTransformation)
                    sw, sh = scaled.width(), scaled.height()
                    cx = max(0, (sw - W) // 2)
                    cy = max(0, (sh - H) // 2)
                    bg_img = scaled.copy(cx, cy, min(W, sw - cx), min(H, sh - cy)).toImage().convertToFormat(
                        QImage.Format.Format_ARGB32_Premultiplied)
                else:
                    bg_img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied); bg_img.fill(_theme_bg_qcolor(self.parent_gui.cfg, 245))
            else:
                bg_img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied); bg_img.fill(_theme_bg_qcolor(self.parent_gui.cfg, 245))
            pre_w, pre_h = H, W
            old_geom = self.text_container.geometry()
            old_title_vis = self.title.isVisible()
            old_body_vis = self.body.isVisible()
            self.text_container.setGeometry(0, 0, pre_w, pre_h)
            self.title.setVisible(not getattr(self, '_fullsize_mode', False))
            self.body.setVisible(True)
            self._layout_positions_for(pre_w, pre_h, portrait_pre_render=False)
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 5)
            content_pre = QImage(pre_w, pre_h, QImage.Format.Format_ARGB32_Premultiplied)
            content_pre.fill(Qt.GlobalColor.transparent)
            p_all = QPainter(content_pre)
            try:
                self.text_container.render(p_all)
            finally:
                p_all.end()
            content_rot = content_pre.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            self.container.hide()
            self.text_container.hide()
            final_img = QImage(bg_img)
            p_final = QPainter(final_img)
            try:
                mode = self._composition_mode_source_over()
                if mode is not None:
                    p_final.setCompositionMode(mode)
                dx = (W - content_rot.width()) // 2
                dy = (H - content_rot.height()) // 2
                p_final.drawImage(dx, dy, content_rot)

                _snap_low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
                _snap_anim_glow = bool(self.parent_gui.cfg.OVERLAY.get("fx_main_breathing_glow", self.parent_gui.cfg.OVERLAY.get("anim_main_glow", True)))
                # When the animated effects widget will be drawn on top, bake only the thin
                # sharp inner border into the snapshot so the two borders don't stack visually.
                # When animations are off, bake the full multi-layer glow into the snapshot.
                _draw_glow_border(p_final, 0, 0, W, H, radius=18,
                                   color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                                   low_perf=(_snap_low_perf or _snap_anim_glow))
            finally:
                p_final.end()
            self.text_container.setGeometry(old_geom)
            self.title.setVisible(old_title_vis)
            self.body.setVisible(old_body_vis)

            self.rotated_label.setGeometry(0, 0, W, H)
            self.rotated_label.setPixmap(QPixmap.fromImage(final_img))
            self.rotated_label.show()
            self.rotated_label.raise_()
            if self._nav_arrows_active:
                self._nav_arrows.setGeometry(0, 0, W, H)
                self._nav_arrows.show()
                self._nav_arrows.raise_()
            # Re-raise animation overlay widgets that must stay on top of the snapshot.
            # These widgets draw themselves transparently over the rotated content; if
            # rotated_label was just raised they would be buried underneath without this.
            # The geometry is reset to full-window size in case it changed since the last
            # render (e.g. a resize event occurred while the overlay was hidden).
            # Effects widget: re-raise without hide/show to avoid stopping its animation timer.
            if hasattr(self, '_effects_widget'):
                _ov = self.parent_gui.cfg.OVERLAY
                _low_perf = bool(_ov.get("low_performance_mode", False))
                _anim_glow = bool(_ov.get("fx_main_breathing_glow", _ov.get("anim_main_glow", True)))
                if not _low_perf and _anim_glow:
                    self._effects_widget.setGeometry(0, 0, W, H)
                    if not self._effects_widget.isVisible():
                        # Not yet visible — start it (showEvent will start the timer)
                        self._effects_widget.show()
                    self._effects_widget.raise_()
            if hasattr(self, '_shine_widget') and self._shine_widget.isVisible():
                self._shine_widget.setGeometry(0, 0, W, H)
                self._shine_widget.raise_()
            if hasattr(self, '_highlight_widget') and self._highlight_widget.isVisible():
                self._highlight_widget.setGeometry(0, 0, W, H)
                self._highlight_widget.raise_()
            if (self._transition_label is not None
                    and self._transition_label.isVisible()
                    and self._transition_state is not None):
                self._transition_label.setGeometry(0, 0, W, H)
                self._transition_label.raise_()
        except Exception as e:
            print("[overlay] portrait render failed:", e)
            self.rotated_label.hide()
            self.container.show()
            self.text_container.show()
        finally:
            self._rot_in_progress = False

    def _deferred_rotation(self):
        self._rot_deferred = False
        if self.portrait_mode and self.isVisible():
            self._apply_rotation_snapshot(force=True)

    def _refresh_current_content(self):
        """Re-render the currently displayed page using the current font settings.
        Handles all page types: fixed-columns (page 0), scrollable rows (page 1),
        plain HTML pages (pages 2/3), and fullsize pages (page 5 VPC leaderboard)."""
        if self._current_combined:
            self._render_fixed_columns()
        elif self._current_html is not None:
            if getattr(self, '_fullsize_mode', False):
                # In fullsize mode (e.g. VPC page 5), never call set_html() as that
                # resets _fullsize_mode. Prefer delegating to parent's _refresh_vpc_page5()
                # so image pixel dimensions are recalculated for the current overlay size.
                parent = getattr(self, 'parent_gui', None)
                if parent is not None and getattr(parent, '_vpc_page5_data', None):
                    parent._refresh_vpc_page5()
                else:
                    self.set_html_fullsize(self._current_html, self._current_title)
            else:
                self.set_html(self._current_html, self._current_title)
        elif self._p2_rows is not None:
            self._render_p2()
            self._layout_positions()
            self.request_rotation(force=True)
        else:
            self._layout_positions()
            self.request_rotation(force=True)

    def apply_font_from_cfg(self, ov: dict):
        if getattr(self, "_font_update_in_progress", False):
            return
        self._font_update_in_progress = True
        try:
            self.font_family = ov.get("font_family", self.font_family)
            self._base_body_size = int(ov.get("base_body_size", self._base_body_size))
            self._base_title_size = int(ov.get("base_title_size", self._base_title_size))
            self._base_hint_size = int(ov.get("base_hint_size", self._base_hint_size))
            self._apply_scale(self.scale_pct)
            def _finish():
                try:
                    self._refresh_current_content()
                finally:
                    self._font_update_in_progress = False
            QTimer.singleShot(0, _finish)
        except Exception:
            self._font_update_in_progress = False

    def apply_portrait_from_cfg(self, ov: dict):
        self.portrait_mode = bool(ov.get("portrait_mode", self.portrait_mode))
        self.rotate_ccw = bool(ov.get("portrait_rotate_ccw", self.rotate_ccw))
        self._apply_geometry()
        self._layout_positions()
        if self.portrait_mode:
            self.request_rotation(force=True)
        else:
            self._show_live_unrotated()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.container.setGeometry(0, 0, self.width(), self.height())
        self._layout_positions()
        if self.portrait_mode:
            self.request_rotation()
        else:
            self._show_live_unrotated()
        if self._nav_arrows_active:
            self._nav_arrows.setGeometry(0, 0, self.width(), self.height())
            self._nav_arrows.raise_()
        if hasattr(self, '_effects_widget') and self._effects_widget.isVisible():
            low_perf = bool(self.parent_gui.cfg.OVERLAY.get("low_performance_mode", False))
            if not low_perf:
                self._effects_widget.setGeometry(0, 0, self.width(), self.height())
                self._effects_widget.raise_()
        if hasattr(self, '_shine_widget') and self._shine_widget.isVisible():
            self._shine_widget.setGeometry(0, 0, self.width(), self.height())
            self._shine_widget.raise_()
        if hasattr(self, '_highlight_widget') and self._highlight_widget.isVisible():
            self._highlight_widget.setGeometry(0, 0, self.width(), self.height())
            self._highlight_widget.raise_()
        if (getattr(self, '_transition_label', None) is not None
                and self._transition_label.isVisible()):
            self._transition_label.setGeometry(0, 0, self.width(), self.height())
            self._transition_label.raise_()

    def set_placeholder(self, session_title: Optional[str] = None):
        self._fullsize_mode = False
        self._current_combined = None
        self._current_html = None
        self._p2_rows = None
        self._current_title = session_title or "Highlights"
        self.title.setText(self._current_title)
        self.body.setText("<div>Loading highlights …</div>")
        self._layout_positions()

    def set_html(self, html: str, session_title: Optional[str] = None):
        self._fullsize_mode = False
        if hasattr(self, "_p2_timer"):
            self._p2_timer.stop()
        self._current_combined = None
        self._current_html = html
        self._p2_rows = None
        self._current_title = "Highlights" if session_title is None else session_title
        self.title.setText(self._current_title)
        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self._layout_positions()

    def set_html_fullsize(self, html: str, session_title: Optional[str] = None):
        """Like set_html() but expands body to the full window — no title bar, no insets.

        Use this for pages that display a full-window image (e.g. Page 5 VPC leaderboard).
        Switching to any other page via set_html/set_combined/etc. automatically restores
        the normal title + body layout.
        """
        if hasattr(self, "_p2_timer"):
            self._p2_timer.stop()
        self._fullsize_mode = True
        self._current_combined = None
        self._current_html = html
        self._p2_rows = None
        self._current_title = "Highlights" if session_title is None else session_title
        self.title.hide()
        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self.body.setGeometry(0, 0, self.width(), self.height())
        self.request_rotation(force=True)

    def set_combined(self, combined: dict, session_title: Optional[str] = None):
        self._fullsize_mode = False
        if hasattr(self, "_p2_timer"):
            self._p2_timer.stop()
        self._current_combined = combined or {}
        self._current_html = None
        self._p2_rows = None
        self._current_title = "Highlights" if session_title is None else session_title
        self._render_fixed_columns()

    def set_html_scrollable(self, css: str, header_html: str, rows: list,
                            session_title: Optional[str] = None):
        """Display a list of table rows with Python QTimer-based scrolling."""
        self._fullsize_mode = False
        if hasattr(self, "_p2_timer"):
            self._p2_timer.stop()
        self._current_combined = None
        self._current_html = None
        self._current_title = session_title or "Achievement Progress"
        self.title.setText(self._current_title)
        self._p2_rows = list(rows)
        self._p2_offset = 0
        self._p2_header = header_html
        self._p2_css = css
        # Estimate how many rows fit in the body area.
        # In portrait mode the widget is taller than wide (e.g. 334×594 on 1080p),
        # but the content is rendered in the rotated orientation: the widget's
        # *width* (the short side) maps to the available content height.
        body_pt = getattr(self, "_body_pt", 20)
        row_h_px = max(16, int(body_pt * 1.8))
        if getattr(self, "portrait_mode", False):
            content_dim = self.width()
        else:
            content_dim = self.height()
        avail_h = max(80, content_dim - 80)
        # Subtract 2 row-heights to account for the header section
        # (ROM title div + progress bar div) that occupies the top of the body.
        self._p2_visible = max(3, avail_h // row_h_px - 2)
        self._render_p2()
        self._layout_positions()
        self.request_rotation(force=True)
        if len(self._p2_rows) > self._p2_visible:
            self._p2_timer.start()

    def _render_p2(self):
        """Render the current scroll window of achievement rows into the body label."""
        rows = self._p2_rows
        offset = self._p2_offset
        visible = getattr(self, "_p2_visible", 10)
        chunk = rows[offset:offset + visible]
        body_pt = getattr(self, "_body_pt", 20)
        css_base = (f"font-size:{body_pt}pt;"
                    f"font-family:'{self.font_family}';color:#FFFFFF;")
        table_html = ("<table width='100%' style='border-collapse:collapse;'>"
                      + "".join(chunk) + "</table>")
        full = getattr(self, "_p2_css", "") + getattr(self, "_p2_header", "") + table_html
        self.body.setText(f"<div style='{css_base}'>{full}</div>")

    def _p2_tick(self):
        """Advance scroll by one row and re-render; pause at end then loop."""
        total = len(self._p2_rows)
        visible = getattr(self, "_p2_visible", 10)
        if total <= visible:
            if hasattr(self, "_p2_timer"):
                self._p2_timer.stop()
            return
        max_offset = total - visible
        self._p2_offset += 1
        if self._p2_offset > max_offset:
            # Pause at end for 3 seconds before looping back to the top
            self._p2_timer.stop()
            self._p2_offset = 0
            self._render_p2()
            self.request_rotation(force=True)
            QTimer.singleShot(3000, lambda: self._p2_timer.start()
                              if self._p2_rows else None)
            return
        self._render_p2()
        self.request_rotation(force=True)

    def _render_fixed_columns(self):
        self.title.setText(self._current_title or "Highlights")
        players = list((self._current_combined or {}).get("players") or [])
        rom_name = str((self._current_combined or {}).get("rom_name") or getattr(self.parent_gui.watcher, "current_rom", None) or "Unknown ROM")
        limit = self.lines_per_category

        def esc(x) -> str:
            return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        table_title = ""
        try:
            romnames = getattr(self.parent_gui.watcher, "ROMNAMES", {}) or {}
            from watcher_core import _strip_version_from_name
            table_title = _strip_version_from_name(romnames.get(rom_name, ""))
        except Exception:
            pass

        # For custom (non-ROM) tables, check for a matching .custom.json and
        # read progress from custom_achievements_progress.json instead of
        # achievements_state.json so that custom achievements are shown
        # correctly without mixing them into the player level calculation.
        custom_table_name = ""
        custom_total_achs = 0
        custom_unlocked_total = 0
        custom_unlocked_titles: set[str] = set()
        custom_rules: list = []
        is_custom_table = False
        try:
            if not rom_name or rom_name == "Unknown ROM":
                current_table = getattr(self.parent_gui.watcher, "current_table", None) or ""
                # Fallback: read current_table from session_latest.summary.json when the
                # watcher has already cleared it after session end.
                if not current_table:
                    try:
                        _summary_path = os.path.join(
                            p_highlights(self.parent_gui.cfg), "session_latest.summary.json"
                        )
                        if os.path.isfile(_summary_path):
                            _sdata = load_json(_summary_path, {}) or {}
                            current_table = str(_sdata.get("table", "") or "")
                    except Exception:
                        pass
                if current_table:
                    _custom_json_path = os.path.join(
                        p_aweditor(self.parent_gui.cfg), f"{current_table}.custom.json"
                    )
                    if os.path.isfile(_custom_json_path):
                        is_custom_table = True
                        _cdata = load_json(_custom_json_path, {}) or {}
                        # Use the vpx filename (without .vpx) as the display title,
                        # stripping parenthetical content and version strings.
                        from watcher_core import _strip_version_from_name as _svfn
                        _tf = str(_cdata.get("table_file") or "").strip()
                        if _tf.lower().endswith(".vpx"):
                            custom_table_name = _svfn(_tf[:-4])
                        else:
                            custom_table_name = _svfn(_tf) if _tf else current_table
                        custom_rules = [r for r in (_cdata.get("rules") or []) if isinstance(r, dict)]
                        custom_total_achs = len(custom_rules)

                        # Read progress from custom_achievements_progress.json
                        _cap_data = load_json(f_custom_achievements_progress(self.parent_gui.cfg), {}) or {}
                        _unlocked_entries = (_cap_data.get(current_table, {}).get("unlocked") or [])
                        custom_unlocked_titles = {
                            str(e.get("title", "")).strip()
                            for e in _unlocked_entries
                            if isinstance(e, dict) and str(e.get("title", "")).strip()
                        }
                        custom_unlocked_total = len(custom_unlocked_titles)
        except Exception:
            pass

        total_achs = 0
        unlocked_total = 0
        pct = 0.0
        try:
            if is_custom_table:
                total_achs = custom_total_achs
                unlocked_total = custom_unlocked_total
                pct = round((unlocked_total / total_achs) * 100, 1) if total_achs > 0 else 0.0
            elif rom_name and rom_name != "Unknown ROM" and self.parent_gui.watcher._has_any_map(rom_name):
                g_rules = self.parent_gui.watcher._collect_global_rules_for_rom(rom_name)
                s_rules = self.parent_gui.watcher._collect_player_rules_for_rom(rom_name)
                total_achs = len(g_rules) + len(s_rules)

                if total_achs > 0:
                    state = self.parent_gui.watcher._ach_state_load()
                    unlocked_g = len(state.get("global", {}).get(rom_name, []))
                    unlocked_s = len(state.get("session", {}).get(rom_name, []))
                    unlocked_total = unlocked_g + unlocked_s
                    pct = round((unlocked_total / total_achs) * 100, 1)
        except Exception:
            pass

        # Animated progress bar: update target and start timer if changed
        new_pct_target = pct if total_achs > 0 else 0.0
        if abs(new_pct_target - getattr(self, '_progress_pct_target', -1)) > 0.05:
            old_pct_target = getattr(self, '_progress_pct_target', -1.0)
            self._progress_pct_target = new_pct_target
            if not self._anim_ok("fx_main_score_spin"):
                self._progress_pct_current = self._progress_pct_target
            else:
                if not hasattr(self, '_progress_bar_timer_started') or not getattr(self, '_progress_bar_timer_started', False):
                    # Fresh start: jump to 0 for a fill animation
                    self._progress_pct_current = 0.0
                if hasattr(self, '_progress_bar_timer'):
                    self._progress_bar_timer.start()
                # Trigger shine when progress actually changes (not first display)
                if old_pct_target >= 0:
                    self._trigger_shine()

        _tc_primary = get_theme_color(self.parent_gui.cfg, "primary")
        _tc_accent = get_theme_color(self.parent_gui.cfg, "accent")
        _tc_border = get_theme_color(self.parent_gui.cfg, "border")
        _tc_bg = get_theme_color(self.parent_gui.cfg, "bg")
        # Parse primary RGB for rgba() usage
        def _hex_to_rgb(h):
            h = h.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        _pr, _pg, _pb = _hex_to_rgb(_tc_primary)
        _br, _ab, _bb = _hex_to_rgb(_tc_accent)
        _bdr_r, _bdr_g, _bdr_b = _hex_to_rgb(_tc_border)

        style = f"""
        <style>
          table.hltable {{ border-collapse: collapse; margin: 0 auto; width: 100%; font-size: 1.1em; }}
          .hltable th, .hltable td {{ padding: 0.35em 0.65em; border-bottom: 1px solid rgba({_bdr_r},{_bdr_g},{_bdr_b},0.15); color: #E0E0E0; overflow-wrap: break-word; }}
          .hltable th {{ text-align: center; background: rgba({_pr}, {_pg}, {_pb}, 0.20); color: {_tc_primary}; font-weight: bold; font-size: 1.1em; border-bottom: 2px solid rgba({_pr}, {_pg}, {_pb}, 0.35); }}
          .hltable td.left {{ text-align: left; }}
          .hltable td.center {{ text-align: center; }}
          .hltable td.right {{ text-align: right; font-weight: bold; font-size: 1.15em; color: {_tc_accent}; }}
          .rom-title {{ text-align: center; font-size: 1.6em; font-weight: bold; color: {_tc_accent}; text-transform: uppercase; letter-spacing: 3px; margin-bottom: 0.2em; margin-top: 0.4em; border-bottom: 1px solid rgba({_pr}, {_pg}, {_pb}, 0.3); padding-bottom: 0.3em; }}
          .score-box {{ text-align: center; font-size: 2.2em; font-weight: bold; margin-bottom: 1.0em; color: {_tc_primary}; }}
          .divider {{ border-top: 1px solid rgba({_br}, {_ab}, {_bb}, 0.3); margin-top: 0.6em; padding-top: 0.6em; }}
        </style>
        """

        def block(entry: dict):
            hld = (entry.get("highlights") or {})
            deltas = (entry.get("deltas") or {})

            try:
                score_abs = int(entry.get("score", 0) or 0)
            except Exception:
                score_abs = 0

            # Score counter spin: update target and start spin if changed
            if score_abs != getattr(self, '_score_target', -1):
                old_score = getattr(self, '_score_target', 0)
                self._score_target = score_abs
                if getattr(self, '_score_display', 0) == 0:
                    self._score_display = 0
                if not self._anim_ok("fx_main_score_spin"):
                    self._score_display = self._score_target
                elif hasattr(self, '_score_spin_timer'):
                    self._score_spin_timer.start()
                # Flash highlight when score changes (not on initial 0→value)
                if old_score > 0 and score_abs != old_score:
                    self._trigger_highlight()

            lines = []

            display_title = custom_table_name or table_title or rom_name or "Unknown ROM"
            lines.append(f"<div class='rom-title'>{esc(display_title)}</div>")

            if total_achs > 0:
                # Use animated progress percentage
                anim_pct = getattr(self, '_progress_pct_current', pct)
                safe_pct = max(0.1, min(100.0, anim_pct))
                rem_pct = 100.0 - safe_pct

                bar_html = f"""
                <div style='text-align: center; color: #FFFFFF; font-weight: bold; font-size: 1.15em; margin-bottom: 0.3em;'>
                    {unlocked_total} / {total_achs} ({pct}%)
                </div>
                <table align='center' width='75%' style='border: 1px solid rgba({_bdr_r}, {_bdr_g}, {_bdr_b}, 0.25); background: {_tc_bg}; margin-bottom: 1.5em; border-radius: 6px; overflow: hidden;' cellpadding='0' cellspacing='0'>
                    <tr>
                        <td width='{safe_pct}%' style='background: {_tc_accent}; height: 12px; border-radius: 4px;'>&nbsp;</td>
                        <td width='{rem_pct}%' style='height: 12px;'>&nbsp;</td>
                    </tr>
                </table>
                """
                lines.append(bar_html)
            else:
                lines.append("<div style='margin-bottom: 1.2em;'></div>")

            if is_custom_table:
                # Clean summary layout for Custom Achievement Tables:
                # no score box, no achievement list (achievements are on page 1)
                remaining_achs = total_achs - unlocked_total
                lines.append(
                    f"<div style='text-align:center; margin-top:1.2em; font-size:1.25em; color:#E0E0E0;'>"
                    f"🏆 {unlocked_total} Achievements unlocked"
                    f"</div>"
                )
                lines.append(
                    f"<div style='text-align:center; margin-top:0.5em; font-size:1.1em; color:#aaa;'>"
                    f"⬜ {remaining_achs} remaining"
                    f"</div>"
                )
                lines.append(
                    "<div style='text-align:center; margin-top:2.5em; font-size:1.0em; color:#888;'>"
                    "► swipe for details"
                    "</div>"
                )
                return "".join(lines)

            if score_abs > 0:
                # Use animated score display value
                anim_score = getattr(self, '_score_display', score_abs)
                sc_txt = f"{anim_score:,d}".replace(",", ".")
                lines.append(f"<div class='score-box'>Score: {sc_txt}</div>")
            else:
                lines.append("<div style='margin-bottom: 1.8em;'></div>")

            lines.append("<table align='center' style='border-collapse: collapse; margin: 0 auto; width: 100%;'><tr>")

            lines.append(f"<td valign='top' style='padding-right: 20px; border-right: 1px solid rgba({_bdr_r}, {_bdr_g}, {_bdr_b}, 0.4);'>")
            lines.append("<table class='hltable'>")
            has_high = False

            if is_custom_table and custom_rules:
                # Show custom achievement list: unlocked first with ✅, then locked with ⬜
                has_high = True
                lines.append(f"<tr><th colspan='2'>Achievements</th></tr>")
                unlocked_rules = [r for r in custom_rules if str(r.get("title") or "").strip() in custom_unlocked_titles]
                locked_rules = [r for r in custom_rules if str(r.get("title") or "").strip() not in custom_unlocked_titles]
                for r in unlocked_rules[:max(1, limit)]:
                    t = esc(str(r.get("title") or "").strip())
                    lines.append(f"<tr><td class='center'>✅ {t}</td><td class='right'></td></tr>")
                for r in locked_rules[:max(1, limit)]:
                    t = esc(str(r.get("title") or "").strip())
                    lines.append(f"<tr><td class='center'>⬜ {t}</td><td class='right'></td></tr>")
            else:
                for cat in ["Power", "Precision", "Fun"]:
                    arr = hld.get(cat, [])
                    if arr:
                        has_high = True
                        lines.append(f"<tr><th colspan='2'>{esc(cat)}</th></tr>")
                        for x in arr[:max(1, limit)]:
                            parts = x.rsplit(" – ", 1)
                            if len(parts) == 2:
                                name, val = parts[0], parts[1]
                            else:
                                name, val = x, ""
                            lines.append(f"<tr><td class='left'>{esc(name)}</td><td class='right'>{esc(val)}</td></tr>")
            lines.append("</table>")
            if not has_high:
                lines.append("<div style='text-align:center; color:#888; margin-top:1em;'>(No Highlights yet)</div>")
            lines.append("</td>")

            lines.append("<td valign='top' style='padding-left: 20px; border:none;'>")
            lines.append("<table class='hltable'>")

            if not deltas:
                lines.append("<tr><td colspan='2' style='text-align:center; color:#888; border:none;'>(No actions yet)</td></tr>")
            else:
                items = sorted(list(deltas.items()), key=lambda x: int(x[1]), reverse=True)

                max_rows = 20
                cols = 2

                max_items = max_rows * cols
                display_items = items[:max_items]

                header_html = ""
                for c in range(cols):
                    border = f" style='border-left: 2px solid rgba({_bdr_r},{_bdr_g},{_bdr_b},0.2); padding-left: 0.55em;'" if c > 0 else ""
                    header_html += f"<th{border}>Action</th><th>Count</th>"
                lines.append(f"<tr>{header_html}</tr>")

                for i in range(0, len(display_items), cols):
                    row_html = ""
                    for c in range(cols):
                        idx = i + c
                        border = f" style='border-left: 2px solid rgba({_bdr_r},{_bdr_g},{_bdr_b},0.2); padding-left: 0.55em;'" if c > 0 else ""
                        if idx < len(display_items):
                            k, v = display_items[idx]
                            v_str = f"+{v:,}".replace(",", ".")
                            row_html += f"<td class='left'{border}>{esc(k)}</td><td class='right'>{esc(v_str)}</td>"
                        else:
                            row_html += f"<td class='left'{border}></td><td class='right'></td>"

                    lines.append(f"<tr>{row_html}</tr>")

                if len(items) > max_items:
                    lines.append(f"<tr><td colspan='{cols * 2}' style='text-align:center; color:#888; font-size:0.9em;'>(+ {len(items)-max_items} more actions)</td></tr>")

            lines.append("</table>")
            lines.append("</td>")

            lines.append("</tr></table>")
            return "".join(lines)

        if not players:
            if is_custom_table:
                # CAT tables have no NVRAM players entry — render from custom data directly.
                players = [{}]
            else:
                self.body.setText("<div>-</div>")
                self._layout_positions()
                return

        html = style + "<div align='center' style='width:100%;'>" + \
               "".join(f"{block(p)}" for p in players) + \
               "</div>"

        body_pt = getattr(self, "_body_pt", 20)
        css = f"font-size:{body_pt}pt;font-family:'{self.font_family}';color:#FFFFFF;"
        self.body.setText(f"<div style='{css}'>{html}</div>")
        self._layout_positions()
        
    def _score_spin_tick(self):
        """Animate score display value toward _score_target (slot-machine style)."""
        if self._score_display == self._score_target:
            self._score_spin_timer.stop()
            return
        diff = abs(self._score_target - self._score_display)
        # Cap animation to ~15 ticks (~750ms at 50ms interval) regardless of score magnitude.
        # Also enforce a minimum step of 1% of the target so huge values don't stall at the end.
        MAX_TICKS = 15
        step = max(1, diff // MAX_TICKS, abs(self._score_target) // 100)
        if self._score_display < self._score_target:
            self._score_display = min(self._score_target, self._score_display + step)
        else:
            self._score_display = max(self._score_target, self._score_display - step)
        self._render_fixed_columns()

    def _progress_bar_tick(self):
        """Animate progress bar fill toward _progress_pct_target (ease-out)."""
        target = getattr(self, '_progress_pct_target', 0.0)
        current = getattr(self, '_progress_pct_current', 0.0)
        if abs(current - target) < 0.5:
            self._progress_pct_current = target
            self._progress_bar_timer.stop()
            self._render_fixed_columns()
            return
        step = max(0.5, abs(target - current) * 0.12)
        if current < target:
            self._progress_pct_current = min(target, current + step)
        else:
            self._progress_pct_current = max(target, current - step)
        self._render_fixed_columns()

    def _snapshot_current(self):
        """Capture the current overlay content as a QImage for transition effects."""
        try:
            W, H = self.width(), self.height()
            if W <= 0 or H <= 0:
                return None
            if getattr(self, 'portrait_mode', False):
                pm = self.rotated_label.pixmap()
                if pm and not pm.isNull():
                    img = pm.toImage()
                    if img.width() == W and img.height() == H:
                        return img
            pm = self.grab()
            return pm.toImage()
        except Exception:
            return None

    def _draw_glitch_frame(self, source_img, label):
        """Draw a single glitch frame on the given label by slicing source_img into strips."""
        self._glitch_frame.draw(source_img, label)

    # ------------------------------------------------------------------
    # Animation helpers
    # ------------------------------------------------------------------

    def _anim_ok(self, key: str) -> bool:
        """Return True only when low_performance_mode is off AND *key* is enabled."""
        ov = self.parent_gui.cfg.OVERLAY
        if bool(ov.get("low_performance_mode", False)):
            return False
        return bool(ov.get(key, True))

    def _trigger_shine(self):
        """Start a shine/sweep over the estimated progress bar area."""
        if not self._anim_ok("fx_main_shine_sweep"):
            return
        W, H = self.width(), self.height()
        self._shine_widget.setGeometry(0, 0, W, H)
        self._shine_widget._t = 0.0
        self._shine_widget.show()
        self._shine_widget.raise_()
        if not self._shine_timer.isActive():
            self._shine_timer.start()

    def _shine_tick(self):
        """Advance the progress bar shine sweep (~800 ms full pass)."""
        self._shine_widget._t = min(1.0, self._shine_widget._t + 16.0 / 800.0)
        self._shine_widget.update()
        if self._shine_widget._t >= 1.0:
            self._shine_timer.stop()
            self._shine_widget.hide()

    def _trigger_highlight(self):
        """Flash a brief warm highlight to signal a value change."""
        if not self._anim_ok("fx_main_shine_sweep"):
            return
        W, H = self.width(), self.height()
        self._highlight_widget.setGeometry(0, 0, W, H)
        self._highlight_widget._alpha = _OverlayHighlightWidget._INITIAL_ALPHA
        self._highlight_widget.show()
        self._highlight_widget.raise_()
        if not self._highlight_timer.isActive():
            self._highlight_timer.start()

    def _highlight_tick(self):
        """Fade the highlight overlay out at the rate defined by _FADE_STEP."""
        self._highlight_widget._alpha = max(
            0, self._highlight_widget._alpha - _OverlayHighlightWidget._FADE_STEP
        )
        self._highlight_widget.update()
        if self._highlight_widget._alpha <= 0:
            self._highlight_timer.stop()
            self._highlight_widget.hide()

    def _restart_p2_timer_if_needed(self):
        """Restart the page-2 scroll timer after a transition completes, if applicable."""
        if not (hasattr(self, '_p2_rows') and self._p2_rows):
            return
        # _p2_visible is set dynamically in set_html_scrollable(); fall back to 10
        # (same default used throughout the overlay) if it hasn't been set yet.
        visible = getattr(self, '_p2_visible', 10)
        if len(self._p2_rows) > visible and hasattr(self, '_p2_timer') and not self._p2_timer.isActive():
            self._p2_timer.start()

    def transition_to(self, new_content_callback, direction: str = 'left'):
        """Perform a slide+fade page transition.

        Call this instead of set_html/set_combined when changing pages.  The method
        captures the current display, runs the callback to update content, then animates
        between old and new snapshots.
        """
        if not self._anim_ok("fx_main_page_transition"):
            new_content_callback()
            return

        old_img = self._snapshot_current()
        if old_img is None or old_img.isNull():
            new_content_callback()
            return

        # Advance page index for accent colour cycling
        n = len(_get_page_accents_list(self.parent_gui.cfg))
        if direction == 'left':
            self._page_index = (self._page_index + 1) % n
        else:
            self._page_index = (self._page_index - 1) % n
        if hasattr(self, '_effects_widget'):
            self._effects_widget.set_accent(_get_page_accent(self.parent_gui.cfg, self._page_index))

        # Pause the page-2 scroll timer for the duration of the transition so it
        # cannot update content mid-animation and cause flicker.
        if hasattr(self, '_p2_timer'):
            self._p2_timer.stop()

        # Stop any in-progress transition timer before entering the pending state so
        # _transition_tick cannot fire with an incomplete state dict during processEvents.
        self._transition_timer.stop()

        # Ensure transition label exists
        if self._transition_label is None:
            self._transition_label = QLabel(self)
            self._transition_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._transition_label.setStyleSheet("background:transparent;")
        W, H = self.width(), self.height()
        self._transition_label.setGeometry(0, 0, W, H)
        # Show old content as the starting frame — no blank flash, no glitch stripes.
        self._transition_label.setPixmap(QPixmap.fromImage(old_img))
        self._transition_label.show()
        self._transition_label.raise_()

        # Set a non-None sentinel state BEFORE calling new_content_callback().
        # In portrait mode, new_content_callback() triggers request_rotation() which
        # schedules _apply_rotation_snapshot via QTimer.singleShot(0,...).  That method
        # raises rotated_label and then, when _transition_state is not None, re-raises
        # _transition_label on top.  Without this sentinel the check in
        # _apply_rotation_snapshot fails and the animation plays invisibly behind
        # rotated_label.
        self._transition_state = {'phase': 'pending'}

        # Apply new content immediately.
        new_content_callback()

        # Flush pending events — in portrait mode this allows the QTimer.singleShot(0,...)
        # rotation snapshot to fire synchronously so new_img is fresh and _transition_label
        # has already been re-raised above rotated_label by _apply_rotation_snapshot.
        # singleShot(interval=0) fires on the first event-loop iteration so the 50ms
        # ceiling is a safe upper bound rather than a fixed delay; in landscape mode
        # there are no deferred snapshots so processEvents returns immediately.
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 50)

        new_img = self._snapshot_current()

        # Begin slide phase immediately — no glitch/stripe pre-effect.
        self._transition_state = {
            'phase': 'slide',
            'direction': direction,
            'old_img': old_img,
            'new_img': new_img,
            'elapsed': 0.0,
        }
        self._transition_timer.start()

    def _transition_tick(self):
        """Animate the current slide+fade transition frame."""
        state = self._transition_state
        if state is None:
            self._transition_timer.stop()
            if self._transition_label:
                self._transition_label.hide()
            return

        # 'pending' is a setup sentinel set in transition_to() before
        # new_content_callback() is called; the timer should not normally fire
        # while in this state, but guard here in case it does (e.g. a showEvent
        # restarts the timer during processEvents).
        if state.get('phase') == 'pending':
            return

        dt = 16.0

        if state['phase'] == 'zoom':
            # Zoom-settle phase: new content eases in from 0.97x → 1.0x
            state['zoom_elapsed'] += dt
            zoom_duration = 180.0
            zt = min(1.0, state['zoom_elapsed'] / zoom_duration)
            zoom_eased = _ease_out_cubic(zt)
            scale = 0.97 + 0.03 * zoom_eased
            new_img = state.get('new_img')
            if new_img and not new_img.isNull() and self._transition_label:
                W, H = new_img.width(), new_img.height()
                out = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
                out.fill(Qt.GlobalColor.transparent)
                pp = QPainter(out)
                pp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                try:
                    sw = int(W * scale)
                    sh = int(H * scale)
                    ox = (W - sw) // 2
                    oy = (H - sh) // 2
                    pp.drawImage(QRect(ox, oy, sw, sh), new_img)
                finally:
                    try:
                        pp.end()
                    except Exception:
                        pass
                self._transition_label.setPixmap(QPixmap.fromImage(out))
            if zt >= 1.0:
                self._transition_timer.stop()
                if self._transition_label:
                    self._transition_label.hide()
                self._transition_state = None
                self._restart_p2_timer_if_needed()
            return

        # Slide + fade phase
        state['elapsed'] += dt
        duration = 300.0
        t = min(1.0, state['elapsed'] / duration)
        eased = _ease_out_cubic(t)

        W, H = self.width(), self.height()
        composite = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        composite.fill(Qt.GlobalColor.transparent)
        p = QPainter(composite)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        direction = state['direction']
        try:
            old_img = state.get('old_img')
            new_img = state.get('new_img')
            if old_img and not old_img.isNull():
                dx_old = -int(W * eased) if direction == 'left' else int(W * eased)
                p.setOpacity(max(0.0, 1.0 - eased))
                p.drawImage(dx_old, 0, old_img)
            if new_img and not new_img.isNull():
                dx_new = int(W * (1.0 - eased)) if direction == 'left' else -int(W * (1.0 - eased))
                p.setOpacity(min(1.0, eased))
                p.drawImage(dx_new, 0, new_img)
        finally:
            try:
                p.end()
            except Exception:
                pass

        if self._transition_label:
            self._transition_label.setPixmap(QPixmap.fromImage(composite))

        if t >= 1.0:
            # Enter zoom-settle phase
            new_img = state.get('new_img')
            if new_img and not new_img.isNull():
                state['phase'] = 'zoom'
                state['zoom_elapsed'] = 0.0
            else:
                self._transition_timer.stop()
                if self._transition_label:
                    self._transition_label.hide()
                self._transition_state = None
                self._restart_p2_timer_if_needed()


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
            scr = QApplication.primaryScreen()
            geo = scr.geometry() if scr else QRect(0, 0, 1280, 720)
            return geo.left() + geo.width() // 2, geo.top() + geo.height() // 2
        except Exception:
            return 640, 360

    def _compose_html(self) -> str:
        pt = getattr(self, "_body_pt", 20)
        fam = str(getattr(self, "_font_family", "Segoe UI")).replace("'", "").replace('"', "").replace(";", "").replace("<", "").replace(">", "")
        return (
            f"<div style='font-size:{pt}pt;font-family:\"{fam}\";'>"
            f"<span style='color:{self._red};'>{self._base_msg}</span>"
            f"<br><span style='color:{self._hint};'>closing in {self._remaining}…</span>"
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
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
        
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
        self._remaining = max(1, int(seconds))
        if color_hex:
            try:
                self._red = color_hex
            except Exception:
                pass
        self._last_center = self._primary_center()
        self._timer.stop()
        self._refresh_view()
        self._timer.start()

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



class FlipCounterOverlay(QWidget):
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
        ov = parent.cfg.OVERLAY or {}
        _low_perf = bool(ov.get("low_performance_mode", False))
        _anim = bool(ov.get("fx_challenge_carousel", ov.get("anim_challenge", True)))
        self._low_perf = _low_perf or not _anim
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(50)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        if not self._check_low_perf():
            self._anim_timer.start()

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
        _start_topmost_timer(self)

    def _on_anim_tick(self):
        self._breathing_pulse.tick(50.0)
        self._render_and_place()

    def _check_low_perf(self) -> bool:
        """Read low-performance / anim-challenge config live so toggle takes effect immediately."""
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            return bool(ov.get("low_performance_mode", False)) or not bool(ov.get("fx_challenge_carousel", ov.get("anim_challenge", True)))
        except Exception:
            return self._low_perf

    def closeEvent(self, e):
        try:
            if getattr(self, "_anim_timer", None):
                self._anim_timer.stop()
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

        title = f"Total flips: {int(self._total)}/{int(self._goal)}"
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
        try:
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing, True)
            bg = _theme_bg_qcolor(self.parent_gui.cfg, 245)
            radius = 16
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(0, 0, content_w, content_h, radius, radius)

            _draw_glow_border(p, 0, 0, content_w, content_h, radius=radius,
                              color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                              low_perf=bool(ov.get("low_performance_mode", False)))

            # Breathing glow ring: pulsates when animation is enabled.
            # Drawn at 5px inset to avoid overlapping the fully-opaque inner border from
            # _draw_glow_border (which extends ~2px from the edge), ensuring the alpha
            # oscillation (40→220) is visible against the dark background.
            if not self._check_low_perf():
                _pc = QColor(get_theme_color(self.parent_gui.cfg, "primary"))
                self._breathing_pulse.draw(p, 5, 5, content_w - 10, content_h - 10,
                                           radius - 3, _pc, width=5)

            p.setPen(title_color); p.setFont(f_title)
            p.drawText(QRect(0, pad, content_w, fm_title.height()),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), title)

            p.setPen(hi_color); p.setFont(f_body)
            p.drawText(QRect(0, pad + fm_title.height() + vgap, content_w, fm_body.height()),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter), sub)
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
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
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

    def update_counts(self, total: int, remaining: int, goal: int):
        self._total = int(total)
        self._remaining = int(remaining)
        self._goal = int(goal)
        self._render_and_place()

    def update_font(self):
        if self.isVisible():
            self._render_and_place()

class FlipCounterPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 380, height_hint: int = 130):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Flip Counter")
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
        if bool(ov.get("flip_counter_saved", ov.get("flip_counter_custom", False))):
            if self._portrait:
                x0 = int(ov.get("flip_counter_x_portrait", 100))
                y0 = int(ov.get("flip_counter_y_portrait", 100))
            else:
                x0 = int(ov.get("flip_counter_x_landscape", 100))
                y0 = int(ov.get("flip_counter_y_landscape", 100))
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
        pad = max(12, int(body_pt * 0.9))
        vgap = max(4, int(body_pt * 0.25))
        # Use the configured goal so the picker matches the actual overlay size
        goal = int(ov.get("flip_counter_goal_total", 400))
        title = f"Total flips: {goal}/{goal}"
        sub = f"Remaining: {goal}"
        text_w = max(fm_title.horizontalAdvance(title), fm_body.horizontalAdvance(sub))
        text_h = fm_title.height() + vgap + fm_body.height()
        w = max(280, text_w + 2 * pad)
        h = max(96, text_h + 2 * pad)
        return w, h

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("flip_counter_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("flip_counter_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
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
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary"))); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Flip Counter\nDrag to position. Click the button again to save"
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
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary"))); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
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
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary"))); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
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

class ChallengeOVPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 520, height_hint: int = 200):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Challenge Overlay")
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
        if bool(ov.get("ch_ov_saved", ov.get("ch_ov_custom", False))):
            if self._portrait:
                x0 = int(ov.get("ch_ov_x_portrait", 100))
                y0 = int(ov.get("ch_ov_y_portrait", 100))
            else:
                x0 = int(ov.get("ch_ov_x_landscape", 100))
                y0 = int(ov.get("ch_ov_y_landscape", 100))
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
        return 520, 200

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ch_ov_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ch_ov_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
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
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary"))); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Challenge Overlay\nDrag to position. Click the button again to save"
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

class MiniInfoPositionPicker(QWidget):
    def __init__(self, parent: "MainWindow", width_hint: int = 420, height_hint: int = 100):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Mini Info Overlay")
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

        if bool(ov.get("notifications_saved", False)):
            if self._portrait:
                x0 = int(ov.get("notifications_x_portrait", 100))
                y0 = int(ov.get("notifications_y_portrait", 100))
            else:
                x0 = int(ov.get("notifications_x_landscape", 100))
                y0 = int(ov.get("notifications_y_landscape", 100))
        else:
            # Wenn noch nie gespeichert, starte in der Mitte
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
        body_pt = 20
        pad_w = 28
        pad_h = 22
        max_text_width = 520
        _accent = get_theme_color(self.parent_gui.cfg, "accent")
        html = (
            f"<div style='font-size:{body_pt}pt;font-family:\"{font_family}\";'>"
            f"<span style='color:{_accent};'>NVRAM file not found or not readable</span>"
            f"<br><span style='color:#DDDDDD;'>closing in 5…</span>"
            f"</div>"
        )
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet(f"color:{_accent};background:transparent;")
        tmp.setFont(QFont(font_family, body_pt))
        tmp.setWordWrap(True)
        tmp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tmp.setText(html)
        tmp.setFixedWidth(max_text_width)
        tmp.adjustSize()
        text_w = tmp.width()
        text_h = tmp.sizeHint().height()
        W = max(200, text_w + pad_w)
        H = max(60, text_h + pad_h)
        return W, H

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("notifications_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
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
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary"))); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Mini Info\nDrag to position. Click the button again to save"
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


class StatusOverlay(QWidget):
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
            scr = QApplication.primaryScreen()
            geo = scr.geometry() if scr else QRect(0, 0, 1280, 720)
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
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)

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


class StatusOverlayPositionPicker(QWidget):
    """Draggable position picker for StatusOverlay, uses ``status_overlay_*`` config keys."""

    def __init__(self, parent: "MainWindow", width_hint: int = 420, height_hint: int = 100):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Status Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = False
        self._sync_from_cfg()
        self._base_w, self._base_h = self._calc_overlay_size()
        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h

        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._screen_geo()

        if bool(ov.get("status_overlay_saved", False)):
            if self._portrait:
                x0 = int(ov.get("status_overlay_x_portrait", 100))
                y0 = int(ov.get("status_overlay_y_portrait", 100))
            else:
                x0 = int(ov.get("status_overlay_x_landscape", 100))
                y0 = int(ov.get("status_overlay_y_landscape", 100))
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
        badge_font_pt = 13
        pad_w = 22
        pad_h = 14
        max_text_width = 340
        status_text = "Online · Tracking"
        html = (
            f"<span style='font-size:{badge_font_pt}pt;font-family:\"{font_family}\";'>"
            f"<span style='color:#00C853;'>&#9679;</span>"
            f"&nbsp;<span style='color:#EEEEEE;'>{status_text}</span>"
            f"</span>"
        )
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet("color:#EEEEEE;background:transparent;")
        tmp.setFont(QFont(font_family, badge_font_pt))
        tmp.setWordWrap(False)
        tmp.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        tmp.setText(html)
        sh = tmp.sizeHint()
        text_w = max(60, min(sh.width(), max_text_width))
        text_h = max(1, sh.height())
        W = max(120, text_w + pad_w)
        H = max(36, text_h + pad_h)
        return W, H

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("status_overlay_portrait", False))
            self._ccw = bool(ov.get("status_overlay_rotate_ccw", False))
        except Exception:
            self._portrait = False
            self._ccw = False

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
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary"))); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        msg = "Status Overlay\nDrag to position. Click the button again to save"
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
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary"))); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
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

        low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))
        anim_toast = not low_perf and bool(parent.cfg.OVERLAY.get("fx_toast_slide_motion", parent.cfg.OVERLAY.get("anim_toast", True)))

        # --- Burst particle animation ---
        is_level_up = (self._rom == "__levelup__")
        self._burst = ParticleBurst(
            count=20,
            color=QColor(get_theme_color(self.parent_gui.cfg, "accent")),
        )
        self._burst_timer = QTimer(self)
        self._burst_timer.setInterval(30)
        self._burst_timer.timeout.connect(self._burst_tick)
        if not anim_toast:
            self._burst_img_margin = 0
        else:
            self._burst_img_margin = 80
            self._burst.start()
            self._burst_timer.start()

        # --- Neon ring pulse (level-up only) ---
        self._ring = NeonRingExpansion(
            ring_count=4,
            delays=[0.0, 150.0, 300.0, 450.0],
            duration=550.0,
        )
        if is_level_up and anim_toast:
            self._ring.start()
            self._ring_timer = QTimer(self)
            self._ring_timer.setInterval(20)
            self._ring_timer.timeout.connect(self._ring_tick)
            self._ring_timer.start()
        else:
            self._ring_timer = None

        # --- Energy flash for level-up ---
        self._flash = EnergyFlash(duration=300.0, start_alpha=180)
        if is_level_up and anim_toast:
            self._flash.start()

        # --- Typewriter reveal (title line1) ---
        self._typewriter = TypewriterReveal()
        self._tw_cursor_timer = QTimer(self)
        self._tw_cursor_timer.setInterval(500)
        self._tw_cursor_timer.timeout.connect(self._tw_cursor_blink)
        if anim_toast:
            self._typewriter.start()
            self._tw_cursor_timer.start()

        # --- Icon bounce animation ---
        self._bounce = IconBounce(duration=400.0, start_scale=1.3)
        if anim_toast:
            self._bounce.start()

        # --- Slide-in/slide-out entry/exit animation ---
        self._slide_motion = SlideMotion(entry_duration=250.0, exit_duration=200.0, distance=60)
        self._motion_timer = QTimer(self)
        self._motion_timer.setInterval(16)
        self._motion_timer.timeout.connect(self._motion_tick)
        if anim_toast:
            self._slide_motion.start_entry()
            self._motion_timer.start()

        # Combined fast animation timer (typewriter + bounce + flash)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._anim_tick)
        if anim_toast:
            self._anim_timer.start()

        self._render_and_place()
        self._timer.start()
        self.show()
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
            # Start exit animation if available, otherwise close immediately
            if not getattr(self, "_is_closing", False):
                if not self._slide_motion.is_exit_active() and hasattr(self, "_motion_timer"):
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
        for attr in ('_burst_timer', '_ring_timer', '_anim_timer',
                     '_tw_cursor_timer', '_timer', '_motion_timer'):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.stop()
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
        if self._typewriter.is_active() and self._typewriter.full_text:
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
        
        # Icon bounce animation: apply scale and Y-offset
        if self._bounce.is_active():
            icon_scale, icon_y_offset = self._bounce.get_scale_and_offset()
            actual_icon_sz = int(icon_sz * icon_scale)
        else:
            actual_icon_sz = icon_sz
            icon_y_offset = 0
        pm = self._icon_pixmap(actual_icon_sz)
        iy = int((H - actual_icon_sz) / 2) + icon_y_offset
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
        if is_level_up and self._flash.is_active():
            self._flash.draw(p, W, H, radius,
                             QColor(get_theme_color(self.parent_gui.cfg, "primary")))
        p.end()

        portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))

        # Draw burst particles and neon ring — works in both landscape and portrait.
        # The expanded image is built before rotation so particle positions remain
        # consistent; rotating the whole expanded image produces correct portrait output.
        burst_margin = self._burst_img_margin if (self._burst.is_active() or self._ring.is_active()) else 0
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
                self._burst.draw(ep, cx, cy)
                # Neon rings (level-up)
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
            burst_margin = self._burst_img_margin if (self._burst.is_active() or self._ring.is_active()) else 0
            W = EW - 2 * burst_margin
            H = EH - 2 * burst_margin
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

            # Apply slide-in/slide-out offset and opacity
            slide_offset, opacity = self._slide_motion.get_offset_and_opacity()

            # Expand window for burst/ring area
            x_win = x - burst_margin + slide_offset
            y_win = y - burst_margin
            self.setGeometry(x_win, y_win, EW, EH)
            self._label.setGeometry(0, 0, EW, EH)
            self._label.setPixmap(QPixmap.fromImage(img))
            self.setWindowOpacity(opacity)
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

    def _burst_tick(self):
        """Advance burst particle positions and fade out. Stops after ~700ms."""
        self._burst.tick(30.0)
        if not self._burst.is_active():
            self._burst_img_margin = 0
            self._burst_timer.stop()
        self._render_and_place()

    def _ring_tick(self):
        """Advance neon ring expansion for level-up toasts."""
        max_r = self.width() if self.width() > 0 else 300
        self._ring.tick(20.0, max_r=float(max_r))
        if not self._ring.is_active():
            if self._ring_timer:
                self._ring_timer.stop()
        self._render_and_place()

    def _anim_tick(self):
        """Advance typewriter index, icon bounce, and energy flash, then re-render."""
        dt = 30.0  # 30ms
        changed = False

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

        if changed:
            self._render_and_place()

        # Stop anim timer when typewriter, bounce, and flash are all done
        if (not self._typewriter.is_active() and
                not self._bounce.is_active() and
                not self._flash.is_active()):
            if hasattr(self, '_anim_timer'):
                self._anim_timer.stop()

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

        self._active = True
        title, rom, seconds = self._queue.pop(0)
        win = AchToastWindow(self.parent_gui, title, rom, seconds)
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
        QTimer.singleShot(250, self._show_next)

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
        _start_topmost_timer(self)

    def _tick(self):
        self._left -= 1
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
            QTimer.singleShot(200, self.close)
            return
        if _sound_mod is not None:
            try:
                _sound_mod.play_sound(self.parent_gui.cfg, "countdown_tick")
            except Exception:
                pass
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
        _draw_glow_border(p, 0, 0, w, h, radius=16,
                          color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                          low_perf=bool(ov.get("low_performance_mode", False)))
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

    def paintEvent(self, _evt):
        if hasattr(self, "_pix"):
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()
            
class ChallengeSelectOverlay(QWidget):
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
        low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))
        anim_challenge = bool(parent.cfg.OVERLAY.get("fx_challenge_carousel", parent.cfg.OVERLAY.get("anim_challenge", True)))
        self._low_perf = low_perf or not anim_challenge
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._slide_timer = QTimer(self)
        self._slide_timer.setInterval(16)
        self._slide_timer.timeout.connect(self._on_slide_tick)
        if not self._check_low_perf():
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
        super().closeEvent(e)

    def _check_low_perf(self) -> bool:
        """Read low-performance / anim-challenge config live so toggle takes effect immediately."""
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            return bool(ov.get("low_performance_mode", False)) or not bool(ov.get("fx_challenge_carousel", ov.get("anim_challenge", True)))
        except Exception:
            return self._low_perf

    def _on_pulse_tick(self):
        self._breathing_pulse.tick(50.0)
        self._render_and_place()

    def _on_slide_tick(self):
        self._carousel.tick(16.0)
        if not self._carousel.is_active():
            self._slide_timer.stop()
        self._render_and_place()

    def set_selected(self, idx: int):
        new_idx = int(idx) % 4
        if new_idx != self._selected and not self._check_low_perf():
            # Determine slide direction: going "right" in list = slide left
            direction = 1 if new_idx > self._selected else -1
            self._prev_selected = self._selected
            self._carousel.start(direction=direction)
            self._slide_timer.start()
        else:
            self._prev_selected = new_idx
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
                              low_perf=bool(ov.get("low_performance_mode", False)))

            title_pt = scaled_body_pt + 6
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
                t_h, d_h = measure_heights(title_pt, desc_pt, title_text, desc_text)
                total = t_h + 6 + d_h
                if total <= max_content_h:
                    break
                if title_pt > min_title: title_pt -= 1
                if desc_pt > min_desc: desc_pt -= 1
                if title_pt <= min_title and desc_pt <= min_desc: break

            t_h, d_h = measure_heights(title_pt, desc_pt, title_text, desc_text)
            block_h = t_h + 6 + d_h
            content_top = top_pad + max(0, (max_content_h - block_h) // 2)

            # Carousel slide: blend between previous and current content
            slide_active = not self._check_low_perf() and self._carousel.is_active()
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
                p.setFont(QFont(font_family, title_pt, QFont.Weight.Bold))
                p.drawText(QRect(pad_lr + prev_x_offset, content_top, avail_w, t_h), flags_wrap_center, prev_title)
                p.setPen(text_color)
                p.setFont(QFont(font_family, desc_pt))
                p.drawText(QRect(pad_lr + prev_x_offset, content_top + t_h + 6, avail_w, d_h), flags_wrap_center, prev_desc)

                # Draw current content (fading in, sliding in)
                p.setOpacity(max(0.0, min(1.0, cur_alpha / 255.0)))
                p.setPen(hi_color)
                p.setFont(QFont(font_family, title_pt, QFont.Weight.Bold))
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
                p.setFont(QFont(font_family, title_pt, QFont.Weight.Bold))
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
            amp = self._breathing_pulse.get_amp()
            alpha = 110 + int(120 * amp)
            anim_scale = 0.9 + 0.2 * amp
            wobble = 2.0 * self._breathing_pulse.get_sin()
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
        default_options = [("Easy", 400), ("Medium", 300), ("Difficult", 200), ("Pro", 100), ("← Back", -1)]
        self._options = list(options) if isinstance(options, list) and options else default_options

        # clamp selection to available options
        self._selected = max(0, min(int(selected_idx or 0), len(self._options) - 1))
        self._prev_selected = self._selected

        self._breathing_pulse = BreathingPulse(speed=0.08)
        self._snap = SnapScale(duration=160.0, scale_amount=0.07)
        low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))
        anim_challenge = bool(parent.cfg.OVERLAY.get("fx_challenge_carousel", parent.cfg.OVERLAY.get("anim_challenge", True)))
        self._low_perf = low_perf or not anim_challenge
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
        self._snap_timer = QTimer(self)
        self._snap_timer.setInterval(16)
        self._snap_timer.timeout.connect(self._on_snap_tick)
        if not self._low_perf:
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
        super().closeEvent(e)

    def _on_pulse_tick(self):
        self._breathing_pulse.tick(50.0)
        self._render_and_place()

    def _on_snap_tick(self):
        self._snap.tick(16.0)
        if not self._snap.is_active():
            self._snap_timer.stop()
        self._render_and_place()

    def set_selected(self, idx: int):
        new_idx = max(0, min(int(idx or 0), len(self._options) - 1))
        if new_idx != self._selected and not getattr(self, '_low_perf', False):
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
        base_body_pt = 20
        scaled_body_pt = 20  # Flip difficulty overlay is always fixed size (100%)
        hint_pt = max(8, int(round(scaled_body_pt * 0.8)))
        text_color = QColor("#FFFFFF")
        hi_color = QColor(get_theme_color(self.parent_gui.cfg, "accent"))

        factor = scaled_body_pt / 20.0
        pad_lr = max(12, int(round(24 * factor)))
        top_pad = max(13, int(round(26 * factor)))
        bottom_pad = max(9, int(round(18 * factor)))
        gap_title_desc = max(4, int(round(8 * factor)))
        spacing = max(10, int(round(18 * factor)))
        hint_line_h = max(10, int(round(18 * factor)))
        hint_gap = max(4, int(round(8 * factor)))
        inner_pad = max(6, int(round(12 * factor)))

        # Measure the actual text widths of every option (name + "N flips") so
        # box_w is guaranteed to be wide enough to show all labels without clipping.
        n = max(1, len(self._options))
        flips_pt = scaled_body_pt
        name_pt_check = scaled_body_pt + 2  # selected boxes use the +2 variant
        fm_name_check = QFontMetrics(QFont(font_family, name_pt_check, QFont.Weight.Bold))
        fm_flips_check = QFontMetrics(QFont(font_family, flips_pt))
        max_text_w = 60
        for _nm, _fl in self._options:
            _fl_int = int(_fl)
            max_text_w = max(max_text_w, fm_name_check.horizontalAdvance(_nm))
            if _fl_int != -1:
                max_text_w = max(max_text_w, fm_flips_check.horizontalAdvance(f"{_fl_int} flips"))
        box_w = max_text_w + 2 * inner_pad

        # Derive the canvas width from the measured box_w so every box fits.
        total_spacing = spacing * (n - 1)
        w = max(300, n * box_w + total_spacing + 2 * pad_lr)
        avail_w = w - 2 * pad_lr

        # Measure title height with word-wrap before creating the image so the
        # image can be sized to fit the content rather than using a fixed height.
        title = "Flip Challenge – Choose difficulty"
        title_font_pt = scaled_body_pt + 6
        flags_center_wrap = int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap)
        _fm_title_pre = QFontMetrics(QFont(font_family, title_font_pt, QFont.Weight.Bold))
        t_h = _fm_title_pre.boundingRect(QRect(0, 0, avail_w, 10000), flags_center_wrap, title).height()

        # box_h is also used when rendering the individual difficulty boxes below.
        box_h = max(50, int(round(100 * factor)))
        h_needed = top_pad + t_h + gap_title_desc + box_h + hint_gap + hint_line_h + bottom_pad
        h = max(130, max(int(round(240 * factor)), h_needed))

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
                              low_perf=bool(ov.get("low_performance_mode", False)))

            p.setPen(hi_color)
            p.setFont(QFont(font_family, title_font_pt, QFont.Weight.Bold))
            p.drawText(QRect(pad_lr, top_pad, avail_w, t_h), flags_center_wrap, title)

            y0 = top_pad + t_h + gap_title_desc

            def draw_option(ix: int, name: str, flips: int, selected: bool):
                x = pad_lr + ix * (box_w + spacing)
                rect = QRect(x, y0, box_w, box_h)

                # Snap pulse: brief scale + flash on selection change; fade-out on prev selection
                snap_scale = 1.0
                snap_flash_alpha = 0
                prev_fade_alpha = 0
                if not getattr(self, '_low_perf', False) and self._snap.is_active():
                    snap_scale = self._snap.get_scale(selected)
                    snap_flash_alpha = self._snap.get_flash_alpha(selected)
                    prev_fade_alpha = self._snap.get_prev_fade_alpha(ix)

                if snap_scale != 1.0:
                    expand = int((snap_scale - 1.0) * box_w / 2)
                    draw_rect = rect.adjusted(-expand, -expand, expand, expand)
                else:
                    draw_rect = rect

                if selected:
                    amp = self._breathing_pulse.get_amp()
                    alpha = 40 + int(60 * amp)
                    _ac = QColor(get_theme_color(self.parent_gui.cfg, "accent"))
                    p.fillRect(draw_rect.adjusted(-4, -4, 4, 4), QColor(_ac.red(), _ac.green(), _ac.blue(), alpha))
                    p.setPen(QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary")), 2))
                    if snap_flash_alpha > 0:
                        p.fillRect(draw_rect, QColor(255, 255, 255, snap_flash_alpha))
                else:
                    p.setPen(QPen(QColor(255, 255, 255, 80), 1))
                    _pc = QColor(get_theme_color(self.parent_gui.cfg, "primary"))
                    if prev_fade_alpha > 0:
                        p.fillRect(draw_rect.adjusted(-4, -4, 4, 4), QColor(_pc.red(), _pc.green(), _pc.blue(), prev_fade_alpha))

                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(draw_rect, 10, 10)

                # Shrink the name font until it fits within the box width.
                name_pt = scaled_body_pt + (2 if selected else 0)
                fm_n = QFontMetrics(QFont(font_family, name_pt, QFont.Weight.Bold))
                while fm_n.horizontalAdvance(name) > box_w - 4 and name_pt > 10:
                    name_pt -= 1
                    fm_n = QFontMetrics(QFont(font_family, name_pt, QFont.Weight.Bold))
                name_h = fm_n.height()
                p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")) if selected else QColor("#FFFFFF"))
                p.setFont(QFont(font_family, name_pt, QFont.Weight.Bold))
                if int(flips) == -1:
                    name_y = y0 + inner_pad + (box_h - name_h) // 2
                else:
                    name_y = y0 + inner_pad
                p.drawText(QRect(x, name_y, box_w, name_h),
                           int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), name)

                if int(flips) != -1:
                    flips_pt = scaled_body_pt
                    p.setFont(QFont(font_family, flips_pt))
                    fm_f = QFontMetrics(QFont(font_family, flips_pt))
                    p.drawText(QRect(x, y0 + inner_pad + name_h + max(4, int(round(6 * factor))), box_w, fm_f.height()),
                               int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), f"{int(flips)} flips")

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



class HeatBarometerOverlay(QWidget):
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
        ov = self.parent_gui.cfg.OVERLAY or {}
        low_perf = bool(ov.get("low_performance_mode", False))
        anim_challenge = bool(ov.get("fx_challenge_carousel", ov.get("anim_challenge", True)))
        self._low_perf = low_perf or not anim_challenge
        self._heat_pulse = HeatPulse(threshold=65)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)
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
        _start_topmost_timer(self)

    def _on_pulse_tick(self):
        self._heat_pulse.tick(40.0)
        self._render_and_place()

    def set_heat(self, heat: int):
        self._heat = max(0, min(100, int(heat)))
        # Start/stop pulse timer based on heat level and low_perf
        if not self._low_perf and self._heat >= 65:
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        else:
            if self._pulse_timer.isActive():
                self._pulse_timer.stop()
        self._render_and_place()

    def closeEvent(self, e):
        try:
            self._pulse_timer.stop()
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
                              low_perf=bool(ov.get("low_performance_mode", False)))

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
                p.setBrush(self._bar_color(self._heat))
                p.drawRoundedRect(bx, fill_y, bar_w, fill_h, 6, 6)

            # label
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            label_rect = QRect(0, pad + bar_h, w, label_h)
            p.drawText(label_rect, int(Qt.AlignmentFlag.AlignCenter), f"{self._heat}%")

            # Reactive warning/critical pulse border (no success effect for overheating)
            ov = self.parent_gui.cfg.OVERLAY or {}
            low_perf = bool(ov.get("low_performance_mode", False))
            self._heat_pulse.draw(p, 1, 1, w - 2, h - 2, self._heat, low_perf)
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
        scr = QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr else QRect(0, 0, 1280, 720)
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

    def paintEvent(self, _evt):
        if hasattr(self, "_pix") and self._pix:
            p = QPainter(self)
            p.drawPixmap(0, 0, self._pix)
            p.end()


class HeatBarPositionPicker(QWidget):
    """Draggable dummy widget to position the HeatBarometerOverlay."""

    def __init__(self, parent: "MainWindow", width_hint: int = 48, height_hint: int = 260):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Place Heat Bar")
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
        if bool(ov.get("heat_bar_saved", ov.get("heat_bar_custom", False))):
            if self._portrait:
                x0 = int(ov.get("heat_bar_x_portrait", 20))
                y0 = int(ov.get("heat_bar_y_portrait", 100))
            else:
                x0 = int(ov.get("heat_bar_x_landscape", 20))
                y0 = int(ov.get("heat_bar_y_landscape", 100))
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
        bar_w = 36
        bar_h = 220
        label_h = 28
        pad = 6
        w = bar_w + 2 * pad
        h = bar_h + label_h + 2 * pad
        return w, h

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("heat_bar_portrait", ov.get("portrait_mode", False)))
            self._ccw = bool(ov.get("heat_bar_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = False
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
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary")))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        msg = "Heat Bar\nDrag to position. Click the button again to save"
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


class ChallengeStartCountdown(QWidget):
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

        self._low_perf = False
        _primary = '#00E5FF'
        _accent = '#FF7F00'
        try:
            self._low_perf = bool(parent.cfg.OVERLAY.get("low_performance_mode", False))
            _primary = get_theme_color(parent.cfg, "primary")
            _accent = get_theme_color(parent.cfg, "accent")
        except Exception:
            pass

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
        self._timer.setInterval(50 if self._low_perf else 16)
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
            if self._low_perf:
                scale = 1.0
                p.setOpacity(1.0)
            elif is_go:
                # GO! fades out while scaling 1.0 → 1.5
                scale = 1.0 + 0.5 * eased
                opacity = max(0.0, 1.0 - eased)
                p.setOpacity(opacity)
            else:
                # Numbers scale 2.0 → 1.0
                scale = 2.0 - eased
                p.setOpacity(1.0)

            font_size = int(80 * scale)
            font = QFont("Segoe UI", max(12, font_size), QFont.Weight.Bold)
            p.setFont(font)

            if not self._low_perf:
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
        finally:
            try:
                p.end()
            except Exception:
                pass
