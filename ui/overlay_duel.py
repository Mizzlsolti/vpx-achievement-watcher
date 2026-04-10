"""ui/overlay_duel.py – DuelInfoOverlay: dedicated overlay for all duel/tournament messages."""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui import (
    QColor, QFont, QTransform, QPixmap,
    QPainter, QImage, QPen,
)

from ui.overlay_base import (
    _theme_bg_qcolor,
    _force_topmost,
    _start_topmost_timer,
    _OverlayFxMixin,
)
from core.theme import get_theme_color
from effects.gl_effects_opengl import (
    BreathingPulse, SlideMotion, EnergyFlash, ColorMorph, GlowSweep,
)

# ---------------------------------------------------------------------------
# Fixed-size helper (mirrors DuelOverlayPositionPicker._calc_overlay_size)
# ---------------------------------------------------------------------------

_DUEL_BODY_PT = 20
_DUEL_PAD_W = 28
_DUEL_PAD_H = 22
_DUEL_MAX_TEXT_W = 520

# Candidate messages used for size computation — kept in sync with the picker.
_DUEL_CANDIDATE_MESSAGES = [
    "⚔️ Duel active against xPinballWizard!<br>🎰 Medieval Madness<br>⚠️ One game only — restarting in-game will abort the duel!<br>🔙 After the duel, close VPX or return to Popper.<br><span style='color:#DDDDDD;'>closing in 20…</span>",
    "⚔️ Duel from xPinballWizard<br>🎰 Medieval Madness<br>⚠️ One game only — restarting in-game will abort the duel!<br>🔙 After the duel, close VPX or return to Popper.<br>[✅ Accept] / Decline<br><small>Use your Duel Accept / Decline keys bound in the Controls tab.</small>",
    "🏆 DUEL WON! You: 42,069,000 vs Opponent: 38,500,000<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "💀 DUEL LOST. You: 38,500,000 vs Opponent: 42,069,000<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "🤝 TIE! You: 42,069,000 vs Opponent: 42,069,000<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "⏰ Duel expired — no response received.<br><span style='color:#DDDDDD;'>closing in 6…</span>",
    "⏳ Score submitted! Waiting for opponent's score...<br><span style='color:#DDDDDD;'>closing in 10…</span>",
    "⚠️ Duel aborted: Session too short.<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "⚠️ Duel aborted: VPX restarted during active duel. Only one attempt allowed!<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "⚠️ Duel aborted: Multiple games detected in single VPX session. Only one game per duel allowed!<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "✅ 'xPinballWizard' accepted your duel on Medieval Madness!<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "❌ 'xPinballWizard' declined your duel on Medieval Madness.<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "⏰ Your duel invitation on Medieval Madness expired (not accepted).<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "🚫 Your duel on Medieval Madness was cancelled.<br><span style='color:#DDDDDD;'>closing in 8…</span>",
    "Cannot accept duel while VPX is running.<br><span style='color:#DDDDDD;'>closing in 5…</span>",
    "❌ Duel cancelled – Table 'Medieval Madness' is not available.<br><span style='color:#DDDDDD;'>closing in 6…</span>",
]


def _calc_duel_overlay_fixed_size(cfg) -> tuple[int, int]:
    """Compute the fixed overlay size by measuring all candidate messages.

    Mirrors ``DuelOverlayPositionPicker._calc_overlay_size()`` exactly so that
    the live overlay window matches the picker rectangle.
    """
    ov = getattr(cfg, "OVERLAY", None) or {}
    font_family = str(ov.get("font_family", "Segoe UI"))
    accent = get_theme_color(cfg, "accent")
    max_w, max_h = 200, 60
    for inner_html in _DUEL_CANDIDATE_MESSAGES:
        html = (
            f"<div style='font-size:{_DUEL_BODY_PT}pt;"
            f"font-family:\"{font_family}\";'>"
            f"<span style='color:{accent};'>{inner_html}</span>"
            f"</div>"
        )
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet(f"color:{accent};background:transparent;")
        tmp.setFont(QFont(font_family, _DUEL_BODY_PT))
        tmp.setWordWrap(True)
        tmp.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        tmp.setText(html)
        tmp.setFixedWidth(_DUEL_MAX_TEXT_W)
        tmp.adjustSize()
        max_w = max(max_w, tmp.width() + _DUEL_PAD_W)
        max_h = max(max_h, tmp.sizeHint().height() + _DUEL_PAD_H)
    return max_w, max_h


class DuelInfoOverlay(_OverlayFxMixin, QWidget):
    """Standalone overlay for duel and tournament notification messages.

    Architecturally identical to MiniInfoOverlay but uses its own
    ``duel_overlay_*`` config keys so it can be positioned, rotated, and
    themed independently from the System Notifications overlay.

    Supports five visual effects controlled by the ``fx_duel_*`` config keys:
    - ``fx_duel_breathing_glow``  – pulsating glow border
    - ``fx_duel_slide_motion``    – slide-in / slide-out
    - ``fx_duel_energy_flash``    – brief flash on show
    - ``fx_duel_color_morph``     – smooth color transition on message change
    - ``fx_duel_glow_sweep``      – horizontal glow sweep on show
    """

    def __init__(self, parent: "MainWindow"):
        super().__init__(None)
        self.parent_gui = parent
        self.setWindowTitle("Duel")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._radius = 16
        self._portrait_mode = True
        self._rotate_ccw = True
        self._remaining = 0
        self._base_msg = ""
        self._last_center = (960, 540)
        # Per-message accent colour override (None → use theme accent dynamically)
        self._accent_override: str | None = None
        self._is_closing = False

        # Compute fixed window size once (recomputed on font change)
        self._fixed_W, self._fixed_H = _calc_duel_overlay_fixed_size(self.parent_gui.cfg)

        # ── Effect objects ────────────────────────────────────────────────────
        self._breathing = BreathingPulse(speed=0.04, min_alpha=60, max_alpha=200)
        self._flash = EnergyFlash(duration=350.0, start_alpha=160)
        self._glow_sweep = GlowSweep(duration=450.0)
        self._color_morph = ColorMorph(duration=260.0)
        self._slide_motion = SlideMotion(entry_duration=260.0, exit_duration=200.0, distance=60)

        # ── Widgets ───────────────────────────────────────────────────────────
        self._snap_label = QLabel(self)
        self._snap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snap_label.setStyleSheet("background:transparent;")

        # ── Timers ────────────────────────────────────────────────────────────
        self._timer = QTimer(self)          # 1 s countdown
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._fx_timer = QTimer(self)       # 16 ms animation (~60 fps)
        self._fx_timer.setInterval(16)
        self._fx_timer.timeout.connect(self._fx_tick)

        # ── Post-processing widget ────────────────────────────────────────────
        # Deferred import to avoid circular dependency (overlay.py → overlay_pickers.py)
        try:
            from ui.overlay import PostProcessingWidget
            self._pp_widget = PostProcessingWidget(self, overlay_type="duel")
        except ImportError:
            self._pp_widget = None
        except Exception as e:
            print(f"[DuelInfoOverlay] PostProcessingWidget init failed: {e}")
            self._pp_widget = None

        self.hide()
        _start_topmost_timer(self)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _primary_center(self) -> tuple[int, int]:
        try:
            scr = QApplication.primaryScreen()
            if scr:
                geo = scr.availableGeometry()
                return geo.left() + geo.width() // 2, geo.top() + geo.height() // 2
        except Exception:
            pass
        return 640, 360

    def _accent_color(self) -> str:
        """Return the current accent colour: per-message override or fresh from theme."""
        if self._accent_override:
            return self._accent_override
        return get_theme_color(self.parent_gui.cfg, "accent")

    # ------------------------------------------------------------------
    # HTML composition
    # ------------------------------------------------------------------

    def _compose_html(self) -> str:
        """Build the HTML rendered by _render_message_image, reading all colours fresh."""
        ov = self.parent_gui.cfg.OVERLAY or {}
        pt = _DUEL_BODY_PT
        fam = (
            str(ov.get("font_family", "Segoe UI"))
            .replace("'", "").replace('"', "")
            .replace(";", "").replace("<", "").replace(">", "")
        )

        # Determine message colour (may animate via ColorMorph)
        if self._is_fx_enabled("fx_duel_color_morph") and self._color_morph.is_active():
            msg_color = self._color_morph.current_color()
        else:
            msg_color = self._accent_color()

        # Countdown line (smaller, hint-coloured)
        if self._remaining > 0:
            countdown = (
                f"<br><span style='font-size:{max(pt - 4, 12)}pt;"
                f"color:#DDDDDD;'>closing in {self._remaining}…</span>"
            )
        else:
            countdown = ""

        # Detect whether the message is already rich HTML (from _duel_invite_notify_text).
        # We recognise pre-formatted HTML by the presence of a recognised HTML opening tag
        # at the start of the string, combined with a closing tag or <br> somewhere inside.
        msg = str(self._base_msg or "")
        _stripped = msg.lstrip()
        _is_html = (
            _stripped.startswith("<div") or _stripped.startswith("<p") or _stripped.startswith("<span")
        ) and ("</" in msg or "<br" in msg)
        if _is_html:
            # Already HTML – use as-is; apply font/size via the outer div only
            inner = msg
        else:
            # Plain text – convert newlines and apply colour
            safe = msg.replace("\n", "<br>")
            inner = f"<span style='color:{msg_color};'>{safe}</span>"

        return (
            f"<div style='font-size:{pt}pt;font-family:\"{fam}\";text-align:center;'>"
            f"{inner}"
            f"{countdown}"
            f"</div>"
        )

    # ------------------------------------------------------------------
    # Image rendering
    # ------------------------------------------------------------------

    def _render_message_image(self, html: str) -> QImage:
        """Render the HTML onto a fixed-size image and draw active effects."""
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        accent_color = QColor(self._accent_color())
        bg_color = _theme_bg_qcolor(self.parent_gui.cfg, 245)
        border_color = QColor(get_theme_color(self.parent_gui.cfg, "border"))

        W, H = self._fixed_W, self._fixed_H
        text_area_w = max(100, W - _DUEL_PAD_W)

        # Measure the rendered text height for vertical centering
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet(f"color:{self._accent_color()};background:transparent;")
        tmp.setFont(QFont(font_family, _DUEL_BODY_PT))
        tmp.setWordWrap(True)
        tmp.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        tmp.setText(html)
        tmp.setFixedWidth(text_area_w)
        tmp.adjustSize()
        text_h = min(tmp.sizeHint().height(), H - _DUEL_PAD_H)

        img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHints(
                QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing,
                True,
            )

            # ── Background ────────────────────────────────────────────────
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg_color)
            p.drawRoundedRect(0, 0, W, H, self._radius, self._radius)

            # ── Border ────────────────────────────────────────────────────
            pen = QPen(border_color)
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(1, 1, W - 2, H - 2, self._radius, self._radius)

            # ── Text content (vertically centered within fixed rect) ──────
            margin_left = _DUEL_PAD_W // 2
            margin_top = max(0, (H - text_h) // 2)
            tmp.render(p, QPoint(margin_left, margin_top))

            # ── Effect: Breathing Glow Border ────────────────────────────
            if self._is_fx_enabled("fx_duel_breathing_glow"):
                self._breathing.draw(p, 1, 1, W - 2, H - 2, self._radius, accent_color, width=4)

            # ── Effect: Energy Flash ──────────────────────────────────────
            if self._is_fx_enabled("fx_duel_energy_flash") and self._flash.is_active():
                self._flash.draw(p, W, H, self._radius, accent_color)

            # ── Effect: Glow Sweep ────────────────────────────────────────
            if self._is_fx_enabled("fx_duel_glow_sweep") and self._glow_sweep.is_active():
                self._glow_sweep.draw(p, W, H, self._radius, accent_color)

        finally:
            p.end()
        return img

    # ------------------------------------------------------------------
    # View refresh (positions window, applies slide offset / opacity)
    # ------------------------------------------------------------------

    def _refresh_view(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        self._portrait_mode = bool(ov.get("duel_overlay_portrait", True))
        self._rotate_ccw = bool(ov.get("duel_overlay_rotate_ccw", True))

        html = self._compose_html()
        img = self._render_message_image(html)

        # Determine slide offset and window opacity
        if self._is_fx_enabled("fx_duel_slide_motion"):
            slide_offset, opacity = self._slide_motion.get_offset_and_opacity()
        else:
            slide_offset, opacity = 0, 1.0

        if self._portrait_mode:
            angle = -90 if self._rotate_ccw else 90
            img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)

        W, H = img.width(), img.height()

        use_saved = bool(ov.get("duel_overlay_saved", False))
        screens = QApplication.screens() or []
        geo = screens[0].availableGeometry() if screens else QRect(0, 0, 1280, 720)
        for s in screens[1:]:
            geo = geo.united(s.availableGeometry())

        if use_saved:
            if self._portrait_mode:
                x = int(ov.get("duel_overlay_x_portrait", 100))
                y = int(ov.get("duel_overlay_y_portrait", 100))
            else:
                x = int(ov.get("duel_overlay_x_landscape", 100))
                y = int(ov.get("duel_overlay_y_landscape", 100))
        else:
            cx, cy = self._last_center
            x = int(cx - W // 2)
            y = int(cy - H // 2)

        x = max(geo.left(), min(x, geo.right() - W))
        y = max(geo.top(), min(y, geo.bottom() - H))

        # Apply slide offset along the appropriate axis
        if self._is_fx_enabled("fx_duel_slide_motion"):
            if self._portrait_mode:
                # In portrait mode the image is rotated 90°; the logical slide direction
                # maps to the X axis.  CCW rotation (-90°) means the "bottom" edge of the
                # overlay is on the right side of the screen, so the overlay slides in from
                # the right (positive offset = starts further right, decreases to 0).
                # CW rotation (+90°) is the mirror: slide in from the left.
                if self._rotate_ccw:
                    x += slide_offset
                else:
                    x -= slide_offset
            else:
                # Landscape: slide along Y axis (bottom → up, positive offset starts lower).
                y += slide_offset

        self.setGeometry(x, y, W, H)
        self._snap_label.setGeometry(0, 0, W, H)
        self._snap_label.setPixmap(QPixmap.fromImage(img))
        self.setWindowOpacity(opacity)
        self.show()
        self.raise_()
        _force_topmost(self)

        # Post-processing widget
        if self._pp_widget is not None:
            if self._pp_widget._any_pp_enabled():
                self._pp_widget.setGeometry(0, 0, W, H)
                if not self._pp_widget.isVisible():
                    self._pp_widget.show()
                self._pp_widget.raise_()
            elif self._pp_widget.isVisible():
                self._pp_widget.hide()

    # ------------------------------------------------------------------
    # Animation ticks
    # ------------------------------------------------------------------

    def _fx_tick(self):
        """Unified 16 ms animation tick: advance all visual effects and re-render."""
        dt = 16.0
        changed = False

        # Breathing glow (continuous – only ticks when effect is enabled)
        if self._is_fx_enabled("fx_duel_breathing_glow"):
            self._breathing.tick(dt)
            changed = True

        # Energy flash (one-shot)
        if self._flash.is_active():
            self._flash.tick(dt)
            changed = True

        # Glow sweep (one-shot)
        if self._glow_sweep.is_active():
            self._glow_sweep.tick(dt)
            changed = True

        # Color morph (one-shot)
        if self._color_morph.is_active():
            self._color_morph.tick(dt)
            changed = True

        # Slide motion (entry / exit)
        if self._slide_motion.is_active():
            was_exit = self._slide_motion.is_exit_active()
            self._slide_motion.tick(dt)
            changed = True
            if was_exit and not self._slide_motion.is_active():
                # Exit animation completed → hide
                self._fx_timer.stop()
                if not self._is_closing:
                    self._is_closing = True
                    QTimer.singleShot(50, self.hide)
                return

        if changed:
            self._refresh_view()

        # Stop the timer once all one-shot effects have finished and breathing glow is off
        breathing_on = self._is_fx_enabled("fx_duel_breathing_glow")
        if (not breathing_on
                and not self._flash.is_active()
                and not self._glow_sweep.is_active()
                and not self._color_morph.is_active()
                and not self._slide_motion.is_active()):
            self._fx_timer.stop()

    # ------------------------------------------------------------------
    # Countdown timer
    # ------------------------------------------------------------------

    def _on_tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._remaining = 0
            self._timer.stop()
            if not self._is_closing:
                if self._is_fx_enabled("fx_duel_slide_motion"):
                    # Snap entry to completion if still running, then start exit
                    if self._slide_motion.is_entry_active():
                        self._slide_motion.complete_entry()
                    if not self._slide_motion.is_exit_active():
                        self._slide_motion.start_exit()
                    if not self._fx_timer.isActive():
                        self._fx_timer.start()
                else:
                    self._is_closing = True
                    QTimer.singleShot(200, self.hide)
            return
        # Only re-render directly when the animation timer isn't already doing it
        if not self._fx_timer.isActive():
            self._refresh_view()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_font(self):
        ov = self.parent_gui.cfg.OVERLAY or {}
        # Recompute fixed size since font change affects text measurements
        self._fixed_W, self._fixed_H = _calc_duel_overlay_fixed_size(self.parent_gui.cfg)
        if self.isVisible():
            self._refresh_view()

    def show_info(self, message: str, seconds: int = 5, center: tuple[int, int] | None = None, color_hex: str | None = None):
        """Show the overlay with *message* for *seconds* (0 = persistent)."""
        self._base_msg = str(message or "").strip()
        self._remaining = max(1, int(seconds)) if int(seconds) > 0 else 0
        self._is_closing = False

        # Handle color morph on accent change (only when overlay is already visible)
        old_color = self._accent_color()
        self._accent_override = color_hex if color_hex else None
        new_color = self._accent_color()
        if (self._is_fx_enabled("fx_duel_color_morph")
                and self.isVisible()
                and old_color.lower() != new_color.lower()):
            self._color_morph.start(old_color, new_color)

        self._last_center = center if center is not None else self._primary_center()
        self._timer.stop()

        # Start entry animation and one-shot effects
        if self._is_fx_enabled("fx_duel_slide_motion"):
            self._slide_motion.start_entry()
            self.setWindowOpacity(0.0)
        else:
            self.setWindowOpacity(1.0)
        if self._is_fx_enabled("fx_duel_energy_flash"):
            self._flash.start()
        if self._is_fx_enabled("fx_duel_glow_sweep"):
            self._glow_sweep.start()

        self._refresh_view()

        if not self._fx_timer.isActive():
            self._fx_timer.start()

        if self._remaining > 0:
            self._timer.start()

    def update_message(self, message: str, color_hex: str | None = None) -> None:
        """Update the displayed message without resetting the countdown timer.

        Useful when the message content changes mid-display (e.g. toggling the
        focused option in a duel invite) but the remaining time must not change.
        Has no effect if the overlay is not currently visible.
        """
        old_color = self._accent_color()
        self._base_msg = str(message or "").strip()
        if color_hex:
            self._accent_override = color_hex
        new_color = self._accent_color()
        # Trigger colour morph when the accent changes
        if (self._is_fx_enabled("fx_duel_color_morph")
                and old_color.lower() != new_color.lower()):
            self._color_morph.start(old_color, new_color)
            if not self._fx_timer.isActive():
                self._fx_timer.start()
        if self.isVisible():
            self._refresh_view()
