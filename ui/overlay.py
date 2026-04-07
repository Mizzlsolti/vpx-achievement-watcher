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

from core.watcher_core import APP_DIR, register_raw_input_for_window, p_aweditor, p_highlights, load_json, f_custom_achievements_progress
from core.theme import get_theme_color, get_theme, DEFAULT_THEME
from effects.gl_effects_opengl import (
    draw_glow_border as _draw_glow_border,
    ease_out_bounce as _ease_out_bounce,
    ease_out_cubic as _ease_out_cubic,
    EffectsWidget as OverlayEffectsWidget,
    ShineWidget as _OverlayShineWidget,
    HighlightWidget as _OverlayHighlightWidget,
    ParticleBurst, NeonRingExpansion, TypewriterReveal, IconBounce,
    SlideMotion, EnergyFlash, BreathingPulse, CarouselSlide,
    SnapScale, HeatPulse, ScanIn, GlowSweep, ColorMorph, GlitchFrame,
    GodRayBurst, ConfettiShower, HologramFlicker, ShockwaveRipple,
    ElectricArc, HoverShimmer, PlasmaNoise, HoloSweep, DifficultyColorPulse,
    # Timer / Countdown effects
    CountdownScaleGlow, RadialPulseBackground, UrgencyShake, TimeWarpDistortion,
    TrailAfterimage, FinalExplosion, PulseRingCountdown, GlitchNumbers,
    # Heat Barometer effects
    FlameParticles, HeatShimmer, SmokeWisps, LavaGlowEdge, NumberThrob, MeltdownShake,
    # Flip Counter effects
    FlipImpactPulse, MilestoneBurst, ElectricSpark,
    GoalProximityGlow, CompletionFirework,
)

try:
    from core import sound as _sound_mod
except Exception:
    _sound_mod = None

from effects.post_processing import (
    PostBloom, PostMotionBlur, PostChromaticAberration,
    PostVignette, PostFilmGrain, PostScanlines,
)


from ui.overlay_base import (
    _theme_bg_qcolor,
    _theme_bg_rgba_css,
    _get_page_accents_list,
    _get_page_accent,
    _force_topmost,
    _start_topmost_timer,
    _OverlayFxMixin,
)
from ui.overlay_pickers import (
    FlipCounterPositionPicker,
    TimerPositionPicker,
    ToastPositionPicker,
    ChallengeOVPositionPicker,
    MiniInfoPositionPicker,
    StatusOverlayPositionPicker,
    OverlayPositionPicker,
    HeatBarPositionPicker,
)
from ui.overlay_toast import AchToastWindow, AchToastManager, read_active_players



from ui.overlay_info import MiniInfoOverlay, StatusOverlay, OverlayNavArrows, FlipCounterOverlay

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


class PostProcessingWidget(QWidget):
    """Transparent overlay widget that renders post-processing screen-space
    effects (bloom, motion blur, chromatic aberration, vignette, film grain,
    scanlines) on top of all overlay content.

    Must be a child of a widget whose parent chain includes a ``parent_gui``
    attribute that exposes ``parent_gui.cfg.OVERLAY``.

    All 6 effects default to *disabled* in config — users must opt in.
    The widget respects ``low_performance_mode`` and stops its timer when
    no effects are enabled, keeping CPU usage at zero in the common case.
    """

    _TICK_MS = 33  # ~30 fps

    def __init__(self, parent, overlay_type: str = "main"):
        super().__init__(parent)
        self._overlay_type = overlay_type
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._fx_bloom        = PostBloom()
        self._fx_motion_blur  = PostMotionBlur()
        self._fx_chromatic    = PostChromaticAberration()
        self._fx_vignette     = PostVignette()
        self._fx_film_grain   = PostFilmGrain()
        self._fx_scanlines    = PostScanlines()

        self._all_fx = [
            ("fx_post_bloom",                self._fx_bloom),
            ("fx_post_motion_blur",          self._fx_motion_blur),
            ("fx_post_chromatic_aberration", self._fx_chromatic),
            ("fx_post_vignette",             self._fx_vignette),
            ("fx_post_film_grain",           self._fx_film_grain),
            ("fx_post_scanlines",            self._fx_scanlines),
        ]

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(self._TICK_MS)
        self._tick_timer.timeout.connect(self._on_tick)
        self.hide()

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _cfg_ov(self) -> dict:
        try:
            return self.parent().parent_gui.cfg.OVERLAY or {}
        except Exception:
            return {}

    def _is_pp_enabled(self, key: str) -> bool:
        ov = self._cfg_ov()
        if bool(ov.get("low_performance_mode", False)):
            return False
        if not bool(ov.get(f"pp_overlay_{self._overlay_type}", True)):
            return False
        return bool(ov.get(key, False))

    def _pp_intensity(self, key: str) -> float:
        ov = self._cfg_ov()
        return max(0.0, min(1.0, float(ov.get(key + "_intensity", 70)) / 100.0))

    def _any_pp_enabled(self) -> bool:
        ov = self._cfg_ov()
        if bool(ov.get("low_performance_mode", False)):
            return False
        if not bool(ov.get(f"pp_overlay_{self._overlay_type}", True)):
            return False
        return any(bool(ov.get(key, False)) for key, _ in self._all_fx)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._any_pp_enabled():
            return
        for key, fx in self._all_fx:
            if self._is_pp_enabled(key):
                fx.set_intensity(self._pp_intensity(key))
                if not fx.is_active():
                    fx.start()
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._tick_timer.stop()
        for _, fx in self._all_fx:
            fx.stop()

    def stop_timer(self):
        """Explicitly stop the tick timer (e.g. when parent closes)."""
        self._tick_timer.stop()

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def _on_tick(self):
        dt = float(self._TICK_MS)
        any_active = False
        for key, fx in self._all_fx:
            if self._is_pp_enabled(key):
                fx.set_intensity(self._pp_intensity(key))
                if not fx.is_active():
                    fx.start()
                fx.tick(dt)
                any_active = True
            else:
                if fx.is_active():
                    fx.stop()
        if any_active:
            self.update()
        else:
            self._tick_timer.stop()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return
        if not self._any_pp_enabled():
            return
        rect = self.rect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        try:
            for key, fx in self._all_fx:
                if self._is_pp_enabled(key) and fx.is_active():
                    fx.draw(p, rect)
        finally:
            try:
                p.end()
            except Exception:
                pass


class OverlayWindow(_OverlayFxMixin, QWidget):
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
                _anim_particles = bool(_ov.get("fx_main_floating_particles", _ov.get("anim_main_glow", True)))
                if not _low_perf and (_anim_glow or _anim_particles):
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
        if hasattr(self, '_pp_widget') and self._pp_widget._any_pp_enabled():
            self._pp_widget.setGeometry(0, 0, W, H)
            if not self._pp_widget.isVisible():
                self._pp_widget.show()
            self._pp_widget.raise_()

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
            anim_particles = bool(self.parent_gui.cfg.OVERLAY.get("fx_main_floating_particles", self.parent_gui.cfg.OVERLAY.get("anim_main_glow", True)))
            if not low_perf and (anim_glow or anim_particles):
                self._effects_widget.setGeometry(0, 0, W, H)
                self._effects_widget.show()
                self._effects_widget.raise_()
        # Size the shine and highlight overlay widgets
        if hasattr(self, '_shine_widget'):
            self._shine_widget.setGeometry(0, 0, W, H)
        if hasattr(self, '_highlight_widget'):
            self._highlight_widget.setGeometry(0, 0, W, H)
        # Start post-processing widget (shown above all other widgets)
        if hasattr(self, '_pp_widget') and not _defer_effects:
            if self._pp_widget._any_pp_enabled():
                self._pp_widget.setGeometry(0, 0, W, H)
                self._pp_widget.show()
                self._pp_widget.raise_()
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
        if hasattr(self, '_pp_widget'):
            self._pp_widget.hide()
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
        # Post-processing effects widget (bloom, vignette, scanlines, etc.)
        self._pp_widget = PostProcessingWidget(self, overlay_type="main")
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
            try:
                fx_nav = bool(self.parent_gui.cfg.OVERLAY.get("fx_main_nav_arrows_pulse", True))
            except Exception:
                fx_nav = True
            if not fx_nav:
                self._nav_arrows.hide()
                return
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
        if hasattr(self, '_pp_widget'):
            self._pp_widget.setGeometry(0, 0, w, h)

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
                _snap_anim_particles = bool(self.parent_gui.cfg.OVERLAY.get("fx_main_floating_particles", self.parent_gui.cfg.OVERLAY.get("anim_main_glow", True)))
                # When the animated effects widget will be drawn on top, bake only the thin
                # sharp inner border into the snapshot so the two borders don't stack visually.
                # When animations are off, bake the full multi-layer glow into the snapshot.
                _effects_active = not _snap_low_perf and (_snap_anim_glow or _snap_anim_particles)
                _draw_glow_border(p_final, 0, 0, W, H, radius=18,
                                   color=QColor(get_theme_color(self.parent_gui.cfg, "border")),
                                   low_perf=(_snap_low_perf or _effects_active))
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
                _anim_particles = bool(_ov.get("fx_main_floating_particles", _ov.get("anim_main_glow", True)))
                if not _low_perf and (_anim_glow or _anim_particles):
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
            # Post-processing widget must be topmost at all times
            if hasattr(self, '_pp_widget') and self._pp_widget._any_pp_enabled():
                self._pp_widget.setGeometry(0, 0, W, H)
                if not self._pp_widget.isVisible():
                    self._pp_widget.show()
                self._pp_widget.raise_()
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
        if hasattr(self, '_pp_widget') and self._pp_widget.isVisible():
            self._pp_widget.setGeometry(0, 0, self.width(), self.height())
            self._pp_widget.raise_()

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
            from core.watcher_core import _strip_version_from_name
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
                        from core.watcher_core import _strip_version_from_name as _svfn
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

        # In preview/demo mode the combined dict carries synthetic achievement counts
        # so the progress bar is always rendered even without real ROM data.
        if total_achs == 0 and "_demo_total_achs" in (self._current_combined or {}):
            total_achs = int(self._current_combined["_demo_total_achs"])
            unlocked_total = int(self._current_combined.get("_demo_unlocked", 0))
            pct = round((unlocked_total / total_achs) * 100, 1) if total_achs > 0 else 0.0

        # Animated progress bar: update target and start timer if changed
        new_pct_target = pct if total_achs > 0 else 0.0
        if abs(new_pct_target - getattr(self, '_progress_pct_target', -1)) > 0.05:
            old_pct_target = getattr(self, '_progress_pct_target', -1.0)
            self._progress_pct_target = new_pct_target
            if not self._anim_ok("fx_main_progress_fill"):
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
        if not self._anim_ok("fx_main_highlight_flash"):
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
            # Even without a full page slide, still show the glitch-frame flash
            # if that effect is enabled so it works independently of page transitions.
            if self._anim_ok("fx_main_glitch_frame"):
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 50)
                _gf_img = self._snapshot_current()
                if _gf_img and not _gf_img.isNull():
                    _gf_lbl = QLabel(self)
                    _gf_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    _gf_lbl.setStyleSheet("background:transparent;")
                    _gf_lbl.setGeometry(0, 0, self.width(), self.height())
                    _gf_lbl.setPixmap(QPixmap.fromImage(_gf_img))
                    self._draw_glitch_frame(_gf_img, _gf_lbl)
                    _gf_lbl.show()
                    _gf_lbl.raise_()
                    new_content_callback()
                    QTimer.singleShot(300, _gf_lbl.deleteLater)
                    return
            new_content_callback()
            return

        # Ensure overlay content is fully rendered before taking the initial snapshot.
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 50)
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
        # Show old content as the starting frame; apply a brief glitch-strip
        # distortion on the first displayed frame when the effect is enabled.
        self._transition_label.setPixmap(QPixmap.fromImage(old_img))
        if self._anim_ok("fx_main_glitch_frame"):
            self._draw_glitch_frame(old_img, self._transition_label)
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



from ui.overlay_challenges import (
    ChallengeCountdownOverlay,
    ChallengeSelectOverlay,
    FlipDifficultyOverlay,
    HeatBarometerOverlay,
)
