"""trophy_render.py — Drawing widgets for the Trophie mascot companion.

Contains _ActionToast, _SpeechBubble, _TrophieDrawWidget and _PinballDrawWidget.
All rendering is pure QPainter; no application-level logic lives here.
"""
from __future__ import annotations

import math
import random
import time

from mascot.trophy_data import (
    _TrophieMemory,
    IDLE, TALKING, HAPPY, SAD, SLEEPY, SURPRISED, DISMISSING,
)
from mascot import trophie_animations as trophy_animations
from mascot import steely_animations

from PyQt6.QtCore import (
    QPoint, QRect, QRectF, QSize, Qt, QTimer,
)
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient, QTransform,
)
from PyQt6.QtWidgets import (
    QWidget,
)

class _ActionToast(QWidget):
    """Small ✅ toast that fades in, stays ~1 s, then fades out."""

    _BG     = QColor("#1A1A1A")
    _BORDER = QColor("#FF7F00")
    _TEXT   = QColor("#FFFFFF")
    _RADIUS = 8
    _PAD    = 8
    _FADE_MS      = 200
    _VISIBLE_MS   = 1000

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if parent is None:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool,
            )
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        else:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)

        font = QFont("Segoe UI", 11)
        self.setFont(font)
        fm = QFontMetrics(font)
        r  = fm.boundingRect("✅")
        w  = r.width()  + self._PAD * 2
        h  = r.height() + self._PAD * 2
        self.setFixedSize(max(w, 44), max(h, 36))

        self._opacity    = 0.0
        self._fading_out = False

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._on_fade)

        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._begin_fade_out)

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(rect.height()),
            self._RADIUS, self._RADIUS,
        )
        p.fillPath(path, self._BG)
        pen = QPen(self._BORDER, 1.5)
        p.setPen(pen)
        p.drawPath(path)
        p.setPen(self._TEXT)
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "✅")

    # ── animation ─────────────────────────────────────────────────────────────

    def _on_fade(self) -> None:
        step = 16.0 / self._FADE_MS
        if not self._fading_out:
            self._opacity = min(1.0, self._opacity + step)
            if self._opacity >= 1.0:
                self._fade_timer.stop()
                self._hold_timer.start(self._VISIBLE_MS)
        else:
            self._opacity = max(0.0, self._opacity - step)
            if self._opacity <= 0.0:
                self._fade_timer.stop()
                self.hide()
                self.deleteLater()
        self.update()

    def _begin_fade_out(self) -> None:
        self._fading_out = True
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    # ── public show helper ────────────────────────────────────────────────────

    def popup(self, global_pos: QPoint) -> None:
        """Position the toast at global_pos and start the fade-in."""
        if self.parent() is not None:
            local = self.parent().mapFromGlobal(global_pos)
            self.move(local)
        else:
            self.move(global_pos)
        self.raise_()
        self.show()
        self._fade_timer.start()


# ---------------------------------------------------------------------------
# Speech Bubble widget
# ---------------------------------------------------------------------------
class _SpeechBubble(QWidget):
    """Floating speech bubble that auto-dismisses after 4 seconds."""

    _AUTO_DISMISS_MS = 5000
    _FADE_MS = 300
    _BG = QColor("#1A1A1A")
    _BORDER = QColor("#FF7F00")
    _TEXT_COLOR = QColor("#FFFFFF")
    _MAX_W = 240
    _PAD = 12
    _RADIUS = 10
    _PTR_H = 10

    def __init__(self, parent: QWidget, text: str, memory: _TrophieMemory, rotation: int = 0) -> None:
        super().__init__(parent)
        self._memory = memory
        self._text = text
        self._opacity = 0.0
        self._shown_at_ms = int(time.time() * 1000)
        self._rotation = rotation  # 0, 90 or -90 degrees
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)

        # Measure required size
        font = QFont("Segoe UI", 9)
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(
            QRect(0, 0, self._MAX_W - self._PAD * 2, 10000),
            Qt.TextFlag.TextWordWrap,
            text,
        )
        bw = max(120, text_rect.width() + self._PAD * 2 + 30)  # +30 for close button
        bh = text_rect.height() + self._PAD * 2 + self._PTR_H
        # Swap dimensions when rotated so the widget occupies the right layout space
        if self._rotation != 0:
            bw, bh = bh, bw
        self.setFixedSize(bw, bh)

        # Fade-in timer
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._on_fade)
        self._fade_timer.start()

        # Auto-dismiss timer
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._begin_fade_out)
        self._auto_timer.start(self._AUTO_DISMISS_MS)

        self._fading_out = False
        self._ptr_offset = -1
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def set_pointer_offset(self, offset: int) -> None:
        self._ptr_offset = offset
        self.update()

    def _on_fade(self) -> None:
        step = 16.0 / self._FADE_MS
        if not self._fading_out:
            self._opacity = min(1.0, self._opacity + step)
            if self._opacity >= 1.0:
                self._fade_timer.stop()
        else:
            self._opacity = max(0.0, self._opacity - step)
            if self._opacity <= 0.0:
                self._fade_timer.stop()
                self._do_dismiss()
        self.update()

    def _begin_fade_out(self) -> None:
        self._fading_out = True
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    def _do_dismiss(self) -> None:
        elapsed = int(time.time() * 1000) - self._shown_at_ms
        msg = self._memory.record_dismiss(elapsed)
        self._memory.save()
        owner = getattr(self, '_owner', None) or self.parent()
        if msg:
            # Schedule a brief "quiet" message on parent Trophie after dismissal.
            # _owner is set when the bubble is a top-level window with no Qt parent.
            try:
                owner._schedule_quiet_msg(msg)
            except Exception:
                pass
        # Reset owner animation state to IDLE and clear the stale bubble reference
        if owner:
            try:
                owner._current_bubble = None
                owner._draw.set_state(IDLE)
                # Trigger offended personality animation on quick dismiss (Steely only)
                if elapsed < 1500 and hasattr(owner._draw, "start_event_anim"):
                    owner._draw.start_event_anim("offended")
            except Exception:
                pass
        self.hide()
        self.deleteLater()

    def mousePressEvent(self, event) -> None:
        self._auto_timer.stop()
        self._begin_fade_out()

    def paintEvent(self, event) -> None:
        if self._rotation != 0:
            self._paint_rotated()
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        w = self.width()
        h = self.height() - self._PTR_H

        # Background rounded rect
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, self._RADIUS, self._RADIUS)
        p.fillPath(path, self._BG)

        # Border
        pen = QPen(self._BORDER, 2)
        p.setPen(pen)
        p.drawPath(path)

        # Pointer triangle (pointing down, centered)
        tri = QPainterPath()
        cx = self._ptr_offset if self._ptr_offset >= 0 else w // 2
        cx = max(self._RADIUS + 8, min(w - self._RADIUS - 8, cx))
        tri.moveTo(cx - 8, h)
        tri.lineTo(cx + 8, h)
        tri.lineTo(cx, h + self._PTR_H)
        tri.closeSubpath()
        p.fillPath(tri, self._BG)
        p.setPen(QPen(self._BORDER, 1))
        p.drawLine(cx - 8, h, cx, h + self._PTR_H)
        p.drawLine(cx + 8, h, cx, h + self._PTR_H)

        # Close button "x"
        p.setPen(QPen(self._BORDER, 1))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(w - self._PAD - 8, self._PAD + 8, "x")

        # Text
        p.setPen(QPen(self._TEXT_COLOR))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(
            QRect(self._PAD, self._PAD, w - self._PAD * 2 - 14, h - self._PAD * 2),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        p.end()

    def _paint_rotated(self) -> None:
        """Render the bubble content at normal orientation then rotate to paint."""
        # Compute the unrotated dimensions (swap back)
        uw = self.height()
        uh = self.width()
        img = QImage(uw, uh, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        ip = QPainter(img)
        ip.setRenderHint(QPainter.RenderHint.Antialiasing)
        ip.setOpacity(self._opacity)

        bh_content = uh - self._PTR_H
        path = QPainterPath()
        path.addRoundedRect(0, 0, uw, bh_content, self._RADIUS, self._RADIUS)
        ip.fillPath(path, self._BG)
        pen = QPen(self._BORDER, 2)
        ip.setPen(pen)
        ip.drawPath(path)

        tri = QPainterPath()
        cx = self._ptr_offset if self._ptr_offset >= 0 else uw // 2
        cx = max(self._RADIUS + 8, min(uw - self._RADIUS - 8, cx))
        tri.moveTo(cx - 8, bh_content)
        tri.lineTo(cx + 8, bh_content)
        tri.lineTo(cx, bh_content + self._PTR_H)
        tri.closeSubpath()
        ip.fillPath(tri, self._BG)
        ip.setPen(QPen(self._BORDER, 1))
        ip.drawLine(cx - 8, bh_content, cx, bh_content + self._PTR_H)
        ip.drawLine(cx + 8, bh_content, cx, bh_content + self._PTR_H)

        ip.setPen(QPen(self._BORDER, 1))
        ip.setFont(QFont("Segoe UI", 8))
        ip.drawText(uw - self._PAD - 8, self._PAD + 8, "x")

        ip.setPen(QPen(self._TEXT_COLOR))
        ip.setFont(QFont("Segoe UI", 9))
        ip.drawText(
            QRect(self._PAD, self._PAD, uw - self._PAD * 2 - 14, bh_content - self._PAD * 2),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        ip.end()

        rotated = img.transformed(QTransform().rotate(self._rotation), Qt.TransformationMode.SmoothTransformation)
        p = QPainter(self)
        try:
            p.drawImage(0, 0, rotated)
        finally:
            p.end()


# ---------------------------------------------------------------------------
# Trophy drawing widget (shared base)
# ---------------------------------------------------------------------------
class _TrophieDrawWidget(QWidget):
    """Draws the animated trophy mascot using QPainter."""

    # Expression pupil offsets (dy relative to eye center)
    _EXPR_PUPIL: dict = {
        IDLE:      (0, 0),
        TALKING:   (0, 0),
        HAPPY:     (0, -3),
        SAD:       (0, 3),
        SLEEPY:    (0, 1),
        SURPRISED: (0, 0),
        DISMISSING:(0, 0),
    }

    # Passive animation modes — cycle through these to keep the trophy lively
    _PASSIVE_MODES = [
        "bumper_float", "spinner_target", "insert_light_pulse", "chrome_ball_shimmer",
        "slingshot_wobble", "bonus_multiplier_fade", "rubber_bounce", "orbit_shot",
        "pop_bumper_stretch", "plunger_nod", "jackpot_sparkle", "ball_lock_yawn",
        "drop_target_dance", "flipper_wave", "trough_snore", "tilt_shiver",
        "multiball_confetti", "ball_save_peek", "loop_dizzy",
    ]
    _PASSIVE_MODE_MIN_MS = 8000
    _PASSIVE_MODE_MAX_MS = 20000
    _PASSIVE_MODE_OFFSET_MS = 5000  # max extra random offset so two instances desynchronize
    # Yawn threshold: above this value the mouth is drawn wide open (surprised shape)
    _YAWN_FULL_OPEN_THRESHOLD = 0.7

    def __init__(self, parent: QWidget, trophy_w: int, trophy_h: int, pad: int = 0) -> None:
        super().__init__(parent)
        self._tw = trophy_w
        self._th = trophy_h
        self._pad = pad
        self.setFixedSize(trophy_w + 2 * pad, trophy_h + 2 * pad)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Skin
        self._skin: str = "classic"

        # Animation state
        self._state = IDLE
        self._bob_t = 0.0          # time for sine bob (radians)
        self._bob_y = 0.0          # current vertical offset from bob
        self._scale = 1.0          # for grow/shrink animations (dismiss)
        self._opacity_val = 1.0    # for fade-out

        # Blink state
        self._blink = False
        self._blink_timer = QTimer(self)
        self._blink_timer.setSingleShot(True)
        self._blink_timer.timeout.connect(self._do_blink)
        self._schedule_blink()

        # Pupil override
        self._pupil_dx = 0
        self._pupil_dy = 0

        # Eye half-close for sleepy
        self._eye_half = False

        # Jump animation
        self._jump_offset = 0.0
        self._jump_vel = 0.0
        self._jumping = False

        # Dismiss animation
        self._dismiss_cb = None

        # Extended animations
        self._tilt_t = 0.0          # wobble/tilt phase for TALKING state
        self._wiggle_t = 0.0        # rapid horizontal wiggle phase for SURPRISED
        self._squash_t = 0.0        # squash-and-stretch phase (post-jump landing)
        self._squash_active = False  # True while squash/stretch is playing

        # Extra animation state for new passive modes
        self._eye_roll_phase: float = 0.0  # for eye_roll passive mode
        self._yawn_amount: float = 0.0     # 0.0=closed, 1.0=full yawn

        # Particle lists for trophy_animations passive modes
        self._snore_particles: list = []       # for snore mode and SLEEPY state
        self._confetti_particles: list = []    # for celebrate mode

        # Subclass-settable passive offsets (used for Steely-specific modes)
        self._passive_extra_x: float = 0.0
        self._passive_extra_y: float = 0.0
        self._passive_angle: float = 0.0

        # Passive animation mode — cycles through variety animations independently
        # of the emotion state to keep the trophy visually interesting.
        self._passive_mode: str = random.choice(self._PASSIVE_MODES)
        self._passive_t: float = 0.0      # phase timer within current passive mode
        self._passive_mode_timer = QTimer(self)
        self._passive_mode_timer.timeout.connect(self._cycle_passive_mode)
        # Add random initial offset so two instances don't sync up
        initial_delay = random.randint(self._PASSIVE_MODE_MIN_MS, self._PASSIVE_MODE_MAX_MS) + random.randint(0, self._PASSIVE_MODE_OFFSET_MS)
        self._passive_mode_timer.start(initial_delay)

        # Main animation tick
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(16)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    def add_tick_listener(self, callback) -> None:
        """Register an additional callback to fire on every animation tick."""
        self._tick_timer.timeout.connect(callback)

    def set_skin(self, skin_id: str) -> None:
        """Apply a visual skin to the mascot drawing widget."""
        self._skin = skin_id
        self.update()

    def _schedule_blink(self) -> None:
        delay_ms = random.randint(3000, 6000)
        self._blink_timer.start(delay_ms)

    def _do_blink(self) -> None:
        self._blink = True
        self.update()
        QTimer.singleShot(120, self._end_blink)

    def _end_blink(self) -> None:
        self._blink = False
        self.update()
        self._schedule_blink()

    def _cycle_passive_mode(self) -> None:
        current = self._passive_mode
        choices = [m for m in self._PASSIVE_MODES if m != current]
        self._passive_mode = random.choice(choices)
        self._passive_t = 0.0
        self._eye_roll_phase = 0.0
        self._passive_extra_x = 0.0
        self._passive_extra_y = 0.0
        self._passive_angle = 0.0
        self._snore_particles = []
        self._confetti_particles = []
        # Restore normal pupil position only when leaving eye_roll mode
        if current in ("orbit_shot", "spinner_eye_roll"):
            dx, dy = self._EXPR_PUPIL.get(self._state, (0, 0))
            self._pupil_dx = dx
            self._pupil_dy = dy
        # Schedule next mode change at a random interval
        self._passive_mode_timer.start(random.randint(self._PASSIVE_MODE_MIN_MS, self._PASSIVE_MODE_MAX_MS))

    def _tick(self) -> None:
        dt = 0.016  # ~16ms
        speed = 0.4 if self._state == SLEEPY else 1.2
        self._bob_t += dt * speed
        self._passive_t += dt

        if self._state == DISMISSING:
            self._scale = max(0.0, self._scale - 0.04)
            self._opacity_val = max(0.0, self._opacity_val - 0.04)
            if self._scale <= 0.0 or self._opacity_val <= 0.0:
                self._tick_timer.stop()
                if self._dismiss_cb:
                    self._dismiss_cb()
                return
        else:
            # Not dismissing — run all motion physics.
            # Jump physics (runs for any jumping state)
            if self._jumping:
                self._jump_offset += self._jump_vel * dt * 60
                self._jump_vel += 0.5  # gravity
                if self._jump_offset >= 0.0:
                    self._jump_offset = 0.0
                    self._jumping = False
                    # Trigger squash-and-stretch on landing
                    self._squash_active = True
                    self._squash_t = 0.0

            # Squash-and-stretch countdown
            if self._squash_active:
                self._squash_t += dt * 5.0
                if self._squash_t >= 1.0:
                    self._squash_t = 0.0
                    self._squash_active = False

            # Wobble/tilt phase for TALKING
            if self._state == TALKING:
                self._tilt_t += dt * 3.0
            else:
                self._tilt_t = 0.0

            # Rapid horizontal wiggle for SURPRISED
            if self._state == SURPRISED:
                self._wiggle_t += dt * 8.0
            else:
                self._wiggle_t = 0.0

            # Eye roll passive mode
            if self._state == IDLE and self._passive_mode in ("orbit_shot", "spinner_eye_roll"):
                self._eye_roll_phase += dt * 1.5
                roll_r = 3
                self._pupil_dx = int(roll_r * math.cos(self._eye_roll_phase))
                self._pupil_dy = int(roll_r * math.sin(self._eye_roll_phase))

            # Yawn passive mode
            if self._state == IDLE and self._passive_mode == "ball_lock_yawn":
                if self._passive_t < 1.5:
                    self._yawn_amount = min(1.0, self._passive_t / 1.0)
                else:
                    self._yawn_amount = max(0.0, 1.0 - (self._passive_t - 1.5) / 1.0)
            else:
                self._yawn_amount = max(0.0, self._yawn_amount - dt * 2.0)

            # New passive animations — delegate to trophy_animations
            if self._state == IDLE:
                _mode = self._passive_mode
                if _mode == "drop_target_dance":
                    trophy_animations.tick_drop_target_dance(self)
                elif _mode == "flipper_wave":
                    trophy_animations.tick_flipper_wave(self)
                elif _mode == "trough_snore":
                    trophy_animations.tick_trough_snore(self)
                elif _mode == "tilt_shiver":
                    trophy_animations.tick_tilt_shiver(self)
                elif _mode == "multiball_confetti":
                    trophy_animations.tick_multiball_confetti(self)
                elif _mode == "ball_save_peek":
                    trophy_animations.tick_ball_save_peek(self)
                elif _mode == "loop_dizzy":
                    trophy_animations.tick_loop_dizzy(self)
            elif self._state == SLEEPY:
                trophy_animations.tick_trough_snore(self)

        self.update()

    def set_state(self, state: str) -> None:
        self._state = state
        dx, dy = self._EXPR_PUPIL.get(state, (0, 0))
        self._pupil_dx = dx
        self._pupil_dy = dy
        self._eye_half = (state == SLEEPY)
        if state in (HAPPY, SURPRISED, TALKING):
            self._jump_offset = -8.0
            self._jump_vel = 0.0
            self._jumping = True
        if state == DISMISSING:
            self._scale = 1.0
            self._opacity_val = 1.0
        # Reset secondary animations on state change for clean transitions
        if state != TALKING:
            self._tilt_t = 0.0
        if state != SURPRISED:
            self._wiggle_t = 0.0

    def start_dismiss(self, callback=None) -> None:
        self._dismiss_cb = callback
        self.set_state(DISMISSING)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Passive fade mode modulates opacity independently of dismiss fade-out
        if self._state != DISMISSING and self._passive_mode == "bonus_multiplier_fade":
            fade_opacity = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._passive_t * 1.5))
            p.setOpacity(self._opacity_val * fade_opacity)
        else:
            p.setOpacity(self._opacity_val)

        if self._state == IDLE and self._passive_mode in ("rubber_bounce", "rubber_ring_bounce"):
            bob = -abs(math.sin(self._bob_t * 2.0)) * 10.0
        else:
            bob = math.sin(self._bob_t) * 3.0
        jump = self._jump_offset if self._jumping else 0.0
        total_offset = bob + jump

        cx = self._tw // 2 + self._pad
        cy_base = self._th // 2 + int(self._th * 0.20) + self._pad

        # ── Tilt / rotation angle (degrees) ──────────────────────────────────
        if self._state == TALKING:
            # Gentle side-to-side wobble while speaking
            angle = math.sin(self._tilt_t) * 8.0
        elif self._state == SAD:
            # Slight downward droop
            angle = -5.0
        elif self._state == SLEEPY:
            # Slow exaggerated sway
            angle = math.sin(self._bob_t * 0.25) * 12.0
        elif self._state == IDLE and self._passive_mode == "spinner_target":
            # Slow continuous spin in idle mode
            angle = (self._passive_t * 45.0) % 360.0
        elif self._state == IDLE and self._passive_mode in ("slingshot_wobble", "slingshot_hit"):
            # Pronounced side-to-side wobble in idle mode
            angle = math.sin(self._passive_t * 2.5) * 18.0
        elif self._state == IDLE and self._passive_mode in ("plunger_nod", "plunger_pull"):
            angle = math.sin(self._passive_t * 2.5) * 10.0
        elif self._state == IDLE and self._passive_angle != 0.0:
            # Subclass-provided angle for passive modes like "roll"
            angle = self._passive_angle
        else:
            angle = 0.0

        # ── Horizontal wiggle offset (SURPRISED) ─────────────────────────────
        wiggle_x = math.sin(self._wiggle_t) * 4.0 if self._state == SURPRISED else 0.0

        # ── Scale components ──────────────────────────────────────────────────
        if self._squash_active:
            # Squash-and-stretch on jump landing: briefly squash then snap back
            sq = math.sin(self._squash_t * math.pi)
            sx = 1.0 + sq * 0.25   # momentarily wider
            sy = 1.0 - sq * 0.20   # momentarily shorter
        elif self._state == IDLE and self._passive_mode in ("insert_light_pulse", "kickback_pulse"):
            # Stronger breathing pulse in pulse mode
            s = 1.0 + math.sin(self._passive_t * 2.0) * 0.12
            sx = s
            sy = s
        elif self._state == IDLE and self._passive_mode == "pop_bumper_stretch":
            sx = 1.0 - abs(math.sin(self._passive_t * 1.5)) * 0.08
            sy = 1.0 + abs(math.sin(self._passive_t * 1.5)) * 0.18
        elif self._state == IDLE:
            # Subtle breathe / pulse while idle
            s = 1.0 + math.sin(self._bob_t * 0.7) * 0.025
            sx = s
            sy = s
        else:
            sx = 1.0
            sy = 1.0

        # Apply dismiss shrink on top of any other scale
        sx *= self._scale
        sy *= self._scale

        p.save()
        # Translate origin to the draw center (incorporating vertical bob/jump,
        # horizontal wiggle, and subclass passive extra offsets), then apply
        # rotation and scale around that center before drawing.
        p.translate(cx + wiggle_x + int(self._passive_extra_x),
                    cy_base + int(total_offset + self._passive_extra_y))
        if angle != 0.0:
            p.rotate(angle)
        if sx != 1.0 or sy != 1.0:
            p.scale(sx, sy)
        self._draw_trophy(p, 0, 0)
        self._draw_skin_accessory(p, 0, 0)
        p.restore()

        # ── Sparkle overlay ───────────────────────────────────────────────────
        if self._state == IDLE and self._passive_mode in ("jackpot_sparkle", "insert_lamp_sparkle"):
            self._draw_sparkles(p, cx, int(cy_base + total_offset))

        # ── Shimmer/shine sweep overlay ───────────────────────────────────────
        if self._state == IDLE and self._passive_mode in ("chrome_ball_shimmer", "playfield_glass_shimmer"):
            self._draw_shimmer(p)

        # ── New passive animation overlays (trophy_animations) ────────────────
        if self._state == IDLE and self._passive_mode == "flipper_wave":
            trophy_animations.draw_flipper_wave(p, self)
        if self._passive_mode == "trough_snore" or self._state == SLEEPY:
            trophy_animations.draw_trough_snore(p, self)
        if self._state == IDLE and self._passive_mode == "multiball_confetti":
            trophy_animations.draw_multiball_confetti(p, self)
        if self._state == IDLE and self._passive_mode == "loop_dizzy":
            trophy_animations.draw_loop_dizzy(p, self)

        p.end()

    def _draw_shimmer(self, p: QPainter) -> None:
        """Draw a golden shimmer sweep across the trophy."""
        sweep_speed = 1.2
        # Normalized sweep position cycles 0→1 over ~2s
        sweep_pos = (self._passive_t * sweep_speed) % 2.0
        if sweep_pos > 1.0:
            # Return sweep — invisible
            return
        tw = self._tw
        th = self._th
        pad = self._pad
        # Map sweep_pos 0→1 to x position across the visual trophy area
        sweep_x = int((sweep_pos - 0.2) * (tw + 40)) - 20 + pad
        sweep_w = max(12, int(tw * 0.25))
        widget_h = th + 2 * pad
        grad = QLinearGradient(float(sweep_x), 0.0, float(sweep_x + sweep_w), float(widget_h))
        grad.setColorAt(0.0, QColor(255, 220, 80, 0))
        grad.setColorAt(0.3, QColor(255, 220, 80, 80))
        grad.setColorAt(0.5, QColor(255, 240, 120, 120))
        grad.setColorAt(0.7, QColor(255, 220, 80, 80))
        grad.setColorAt(1.0, QColor(255, 220, 80, 0))
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRect(sweep_x, 0, sweep_w, widget_h)
        p.restore()

    def _draw_sparkles(self, p: QPainter, cx: int, cy: int) -> None:
        """Draw animated star sparkles around the character."""
        t = self._passive_t
        offsets = [(-30, -38), (28, -35), (-26, 28), (30, 26), (0, -48), (34, -10), (-34, -8)]
        for i, (ox, oy) in enumerate(offsets):
            phase = (t * 2.5 + i * 0.9) % (math.pi * 2)
            alpha = int(200 * abs(math.sin(phase)))
            if alpha < 20:
                continue
            size = 2.5 + 1.5 * abs(math.sin(phase))
            sx = cx + ox
            sy = cy + oy
            color = QColor(255, 240, 80, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            # 4-pointed star shape
            star = QPainterPath()
            star.moveTo(sx, sy - size)
            star.lineTo(sx + size * 0.3, sy - size * 0.3)
            star.lineTo(sx + size, sy)
            star.lineTo(sx + size * 0.3, sy + size * 0.3)
            star.lineTo(sx, sy + size)
            star.lineTo(sx - size * 0.3, sy + size * 0.3)
            star.lineTo(sx - size, sy)
            star.lineTo(sx - size * 0.3, sy - size * 0.3)
            star.closeSubpath()
            p.fillPath(star, color)

    def _draw_trophy(self, p: QPainter, cx: int, cy: int) -> None:
        tw = self._tw
        th = self._th

        # ── Base / Pedestal ──────────────────────────────────────────────────
        base_w = int(tw * 0.55)
        base_h = int(th * 0.12)
        base_x = cx - base_w // 2
        base_y = cy + int(th * 0.32)

        grad_base = QLinearGradient(float(base_x), float(base_y), float(base_x), float(base_y + base_h))
        grad_base.setColorAt(0.0, QColor("#DAA520"))
        grad_base.setColorAt(1.0, QColor("#8B6914"))
        p.setBrush(grad_base)
        p.setPen(QPen(QColor("#704214"), 1))
        p.drawRoundedRect(base_x, base_y, base_w, base_h, 3, 3)

        # Stem
        stem_w = int(tw * 0.16)
        stem_h = int(th * 0.16)
        stem_x = cx - stem_w // 2
        stem_y = base_y - stem_h
        grad_stem = QLinearGradient(float(stem_x), 0.0, float(stem_x + stem_w), 0.0)
        grad_stem.setColorAt(0.0, QColor("#8B6914"))
        grad_stem.setColorAt(0.5, QColor("#FFD700"))
        grad_stem.setColorAt(1.0, QColor("#8B6914"))
        p.setBrush(grad_stem)
        p.setPen(QPen(QColor("#704214"), 1))
        p.drawRect(stem_x, stem_y, stem_w, stem_h)

        # ── Cup body ─────────────────────────────────────────────────────────
        cup_w = int(tw * 0.62)
        cup_h = int(th * 0.52)
        cup_x = cx - cup_w // 2
        cup_y = cy - int(th * 0.36)

        grad_cup = QLinearGradient(float(cup_x), 0.0, float(cup_x + cup_w), 0.0)
        grad_cup.setColorAt(0.0, QColor("#B8860B"))
        grad_cup.setColorAt(0.3, QColor("#FFD700"))
        grad_cup.setColorAt(0.7, QColor("#FFC200"))
        grad_cup.setColorAt(1.0, QColor("#B8860B"))
        p.setBrush(grad_cup)
        p.setPen(QPen(QColor("#704214"), 1))

        # Trapezoid-ish cup: wider at top, narrower at bottom
        cup_path = QPainterPath()
        top_extra = int(cup_w * 0.1)
        cup_path.moveTo(cup_x - top_extra, cup_y)
        cup_path.lineTo(cup_x + cup_w + top_extra, cup_y)
        cup_path.lineTo(cup_x + cup_w, cup_y + cup_h)
        cup_path.lineTo(cup_x, cup_y + cup_h)
        cup_path.closeSubpath()
        p.fillPath(cup_path, grad_cup)
        p.strokePath(cup_path, QPen(QColor("#704214"), 1))

        # Cup rim highlight
        p.setPen(QPen(QColor("#FFFACD"), 2))
        p.drawLine(cup_x - top_extra + 4, cup_y + 3, cup_x + cup_w + top_extra - 4, cup_y + 3)

        # ── Handles ──────────────────────────────────────────────────────────
        handle_y = cup_y + cup_h // 3
        handle_h = int(cup_h * 0.5)
        handle_w = int(tw * 0.12)

        for side in (-1, 1):
            if side == -1:
                hx = cup_x - top_extra - handle_w
            else:
                hx = cup_x + cup_w + top_extra
            p.setBrush(QColor("#DAA520"))
            p.setPen(QPen(QColor("#704214"), 1))
            p.drawRoundedRect(hx, handle_y, handle_w, handle_h, handle_w // 2, handle_w // 2)

        # ── Eyes ─────────────────────────────────────────────────────────────
        eye_y = cup_y + cup_h // 2 - 4
        eye_r = max(4, int(tw * 0.09))
        left_eye_x = cx - int(tw * 0.14)
        right_eye_x = cx + int(tw * 0.14)

        for ex in (left_eye_x, right_eye_x):
            # White sclera
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor("#333333"), 1))
            if self._blink or self._state == SLEEPY:
                # Blink: half-closed line
                blink_h = eye_r if self._eye_half else 2
                p.drawEllipse(ex - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2)
                # Draw eyelid overlay
                p.setBrush(QColor("#DAA520"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(ex - eye_r - 1, eye_y - eye_r - 1, eye_r * 2 + 2, blink_h + 2)
            else:
                p.drawEllipse(ex - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2)

            if not self._blink:
                # Pupil
                pr = max(2, int(eye_r * 0.55))
                if self._state == SURPRISED:
                    pr = eye_r - 1
                px = ex + self._pupil_dx
                py = eye_y + self._pupil_dy
                p.setBrush(QColor("#111111"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(px - pr, py - pr, pr * 2, pr * 2)

                # Eye shine
                p.setBrush(QColor("#FFFFFF"))
                shine_r = max(1, pr // 3)
                p.drawEllipse(px - pr // 3, py - pr // 3, shine_r, shine_r)

        # ── Mouth ────────────────────────────────────────────────────────────
        mouth_cx = cx
        mouth_y = eye_y + eye_r + 6
        mouth_w = int(tw * 0.28)
        mouth_h = int(tw * 0.14)
        talk_pulse = (math.sin(self._tilt_t * 3.0) > 0) if self._state == TALKING else False
        yawn_open = self._yawn_amount > 0.1 if self._state == IDLE and self._passive_mode == "ball_lock_yawn" else False

        p.setPen(QPen(QColor("#333333"), 1))
        p.setBrush(QColor("#333333"))
        if self._state == SURPRISED or (yawn_open and self._yawn_amount > self._YAWN_FULL_OPEN_THRESHOLD):
            ow = int(mouth_w * 0.7)
            oh = int(mouth_h * (1.0 + self._yawn_amount * 0.5))
            p.setBrush(QColor("#111111"))
            p.drawEllipse(mouth_cx - ow // 2, mouth_y - oh // 4, ow, oh)
        elif self._state == HAPPY:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#333333"), 2))
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w // 2, mouth_y)
            path.quadTo(mouth_cx, mouth_y + mouth_h, mouth_cx + mouth_w // 2, mouth_y)
            p.drawPath(path)
        elif self._state == SAD:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#333333"), 2))
            frown_y = mouth_y + mouth_h
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w // 2, frown_y)
            path.quadTo(mouth_cx, mouth_y, mouth_cx + mouth_w // 2, frown_y)
            p.drawPath(path)
        elif self._state == TALKING and talk_pulse:
            tw2 = int(mouth_w * 0.5)
            th2 = int(mouth_h * 0.6)
            p.setBrush(QColor("#111111"))
            p.drawEllipse(mouth_cx - tw2 // 2, mouth_y - th2 // 4, tw2, th2)
        elif self._state == SLEEPY or (yawn_open and self._yawn_amount <= self._YAWN_FULL_OPEN_THRESHOLD):
            ow = int(mouth_w * 0.3 + self._yawn_amount * mouth_w * 0.4)
            oh = int(mouth_h * 0.4 + self._yawn_amount * mouth_h * 0.5)
            p.setBrush(QColor("#333333"))
            p.drawEllipse(mouth_cx - ow // 2, mouth_y - oh // 4, ow, oh)
        elif self._state == DISMISSING:
            p.setPen(QPen(QColor("#333333"), 2))
            p.drawLine(mouth_cx - mouth_w // 3, mouth_y + mouth_h // 2,
                       mouth_cx + mouth_w // 3, mouth_y + mouth_h // 2)
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#333333"), 2))
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w // 3, mouth_y)
            path.quadTo(mouth_cx, mouth_y + mouth_h // 2, mouth_cx + mouth_w // 3, mouth_y)
            p.drawPath(path)

    def _cup_safe_clip(self, cx: int, cy: int) -> QPainterPath:
        """Return the cup trapezoid path minus the face exclusion zone.

        Used by clothing skins so decorations don't paint over the face.
        """
        tw = self._tw
        th = self._th
        cup_w = int(tw * 0.62)
        cup_h = int(th * 0.52)
        cup_x = cx - cup_w // 2
        cup_y = cy - int(th * 0.36)
        top_extra = int(cup_w * 0.1)
        eye_y = cup_y + cup_h // 2 - 4
        eye_r = max(4, int(tw * 0.09))
        mouth_y = eye_y + eye_r + 6
        mouth_h = int(tw * 0.14)
        mouth_w = int(tw * 0.28)
        fm = eye_r + 4
        cup_path = QPainterPath()
        cup_path.moveTo(float(cup_x - top_extra), float(cup_y))
        cup_path.lineTo(float(cup_x + cup_w + top_extra), float(cup_y))
        cup_path.lineTo(float(cup_x + cup_w), float(cup_y + cup_h))
        cup_path.lineTo(float(cup_x), float(cup_y + cup_h))
        cup_path.closeSubpath()
        face_path = QPainterPath()
        face_path.addRect(QRectF(
            cx - mouth_w // 2 - fm,
            eye_y - eye_r - fm,
            mouth_w + fm * 2,
            mouth_y + mouth_h + fm - (eye_y - eye_r - fm),
        ))
        return cup_path.subtracted(face_path)

    def _draw_skin_accessory(self, p: QPainter, cx: int, cy: int) -> None:
        """Draw the skin-specific accessory on top of the trophy."""
        skin = getattr(self, "_skin", "classic")
        if skin == "classic" or not skin:
            return
        tw = self._tw
        th = self._th
        # Cup top position (reference for accessories placed on top)
        cup_y_top = cy - int(th * 0.36)

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if skin == "top_hat":
            hw = int(tw * 0.35)
            hh = int(th * 0.22)
            brim_w = int(tw * 0.50)
            brim_h = int(th * 0.05)
            hx = cx - hw // 2
            hy = cup_y_top - hh - brim_h
            p.setBrush(QColor("#111111"))
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawRect(hx, hy, hw, hh)
            # Brim
            p.drawRect(cx - brim_w // 2, cup_y_top - brim_h, brim_w, brim_h)
            # Hat band
            p.setBrush(QColor("#FF7F00"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(hx, hy + hh - int(hh * 0.2), hw, int(hh * 0.2))

        elif skin == "sunglasses":
            eye_y = cy - int(th * 0.36) + int(th * 0.26)
            g_r = int(tw * 0.11)
            lx = cx - int(tw * 0.14)
            rx = cx + int(tw * 0.14)
            p.setBrush(QColor(0, 0, 0, 180))
            p.setPen(QPen(QColor("#222222"), 1))
            p.drawEllipse(lx - g_r, eye_y - g_r, g_r * 2, g_r * 2)
            p.drawEllipse(rx - g_r, eye_y - g_r, g_r * 2, g_r * 2)
            # Bridge
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawLine(lx + g_r, eye_y, rx - g_r, eye_y)

        elif skin == "party_hat":
            hw = int(tw * 0.30)
            hh = int(th * 0.28)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            path = QPainterPath()
            path.moveTo(cx, hy)
            path.lineTo(hx, cup_y_top)
            path.lineTo(hx + hw, cup_y_top)
            path.closeSubpath()
            p.setBrush(QColor("#FF3399"))
            p.setPen(QPen(QColor("#CC1177"), 1))
            p.fillPath(path, QColor("#FF3399"))
            p.strokePath(path, QPen(QColor("#CC1177"), 1))
            # Dots
            p.setBrush(QColor("#FFFF00"))
            p.setPen(Qt.PenStyle.NoPen)
            for dx, dy in [(-4, hh // 2), (4, hh // 3), (0, hh * 2 // 3)]:
                p.drawEllipse(cx + dx - 2, hy + dy - 2, 4, 4)
            # Pom-pom
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - 4, hy - 4, 8, 8)

        elif skin == "pirate":
            hw = int(tw * 0.42)
            hh = int(th * 0.16)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            p.setBrush(QColor("#111111"))
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawRect(hx, hy, hw, hh)
            # Brim
            brim_w = int(tw * 0.55)
            p.drawRect(cx - brim_w // 2, hy + hh - 3, brim_w, 6)
            # Skull & crossbones (simple)
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            sr = int(tw * 0.06)
            p.drawEllipse(cx - sr, hy + hh // 4 - sr, sr * 2, sr * 2)
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            cross_y = hy + hh * 3 // 4
            p.drawLine(cx - sr, cross_y, cx + sr, cross_y)
            p.drawLine(cx - sr + 2, cross_y - 2, cx + sr - 2, cross_y + 2)

        elif skin == "headband":
            # Ninja headband
            hb_y = cup_y_top + int(th * 0.06)
            hb_h = int(th * 0.07)
            hb_w = int(tw * 0.70)
            p.setBrush(QColor("#222222"))
            p.setPen(QPen(QColor("#111111"), 1))
            p.drawRect(cx - hb_w // 2, hb_y, hb_w, hb_h)
            # Forehead plate
            p.setBrush(QColor("#555577"))
            p.setPen(QPen(QColor("#333355"), 1))
            plate_w = int(tw * 0.28)
            plate_h = int(th * 0.09)
            p.drawRect(cx - plate_w // 2, hb_y - 2, plate_w, plate_h)

        elif skin == "wizard_hat":
            hw = int(tw * 0.32)
            hh = int(th * 0.35)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            path = QPainterPath()
            path.moveTo(cx, hy)
            path.lineTo(hx, cup_y_top)
            path.lineTo(hx + hw, cup_y_top)
            path.closeSubpath()
            p.setBrush(QColor("#4400AA"))
            p.setPen(QPen(QColor("#220088"), 1))
            p.fillPath(path, QColor("#4400AA"))
            p.strokePath(path, QPen(QColor("#220088"), 1))
            # Stars on hat
            p.setBrush(QColor("#FFD700"))
            p.setPen(Qt.PenStyle.NoPen)
            for dx, dy in [(-3, hh // 3), (5, hh // 2), (1, hh * 2 // 3)]:
                p.drawEllipse(cx + dx - 2, hy + dy - 2, 4, 4)
            # Brim
            brim_w = int(tw * 0.50)
            p.setBrush(QColor("#330099"))
            p.setPen(QPen(QColor("#220088"), 1))
            p.drawRect(cx - brim_w // 2, cup_y_top - 4, brim_w, 8)

        elif skin == "santa_hat":
            hw = int(tw * 0.32)
            hh = int(th * 0.28)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            path = QPainterPath()
            path.moveTo(cx, hy)
            path.lineTo(hx, cup_y_top)
            path.lineTo(hx + hw, cup_y_top)
            path.closeSubpath()
            p.setBrush(QColor("#CC0000"))
            p.setPen(QPen(QColor("#AA0000"), 1))
            p.fillPath(path, QColor("#CC0000"))
            p.strokePath(path, QPen(QColor("#AA0000"), 1))
            # White trim at base
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            trim_w = int(tw * 0.50)
            p.drawRect(cx - trim_w // 2, cup_y_top - 5, trim_w, 8)
            # Pom-pom
            p.drawEllipse(cx - 4, hy - 4, 8, 8)

        elif skin == "ice":
            # Icicles hanging from cup rim
            rim_y = cup_y_top
            for i in range(5):
                ix = cx - int(tw * 0.22) + i * int(tw * 0.11)
                ice_h = int(th * 0.08) + (i % 2) * int(th * 0.05)
                path = QPainterPath()
                path.moveTo(ix - 3, rim_y)
                path.lineTo(ix + 3, rim_y)
                path.lineTo(ix, rim_y + ice_h)
                path.closeSubpath()
                p.fillPath(path, QColor(180, 230, 255, 200))
                p.strokePath(path, QPen(QColor(100, 180, 255), 1))

        elif skin == "flame":
            # Flames around cup base
            base_y = cy + int(th * 0.32)
            for i in range(5):
                fx = cx - int(tw * 0.22) + i * int(tw * 0.11)
                fl_h = int(th * 0.14) + (i % 2) * int(th * 0.05)
                path = QPainterPath()
                path.moveTo(fx - 4, base_y)
                path.quadTo(fx - 2, base_y - fl_h * 0.6, fx, base_y - fl_h)
                path.quadTo(fx + 2, base_y - fl_h * 0.6, fx + 4, base_y)
                path.closeSubpath()
                p.fillPath(path, QColor(255, int(120 + i * 20), 0, 200))

        elif skin == "sparks":
            # Electric sparks around cup
            p.setPen(QPen(QColor("#FFFF00"), 2))
            for i in range(4):
                angle_rad = (i / 4.0) * 6.28
                sx2 = cx + int(math.cos(angle_rad) * tw * 0.38)
                sy2 = cy - int(th * 0.08) + int(math.sin(angle_rad) * th * 0.28)
                ex2 = cx + int(math.cos(angle_rad) * tw * 0.48)
                ey2 = cy - int(th * 0.08) + int(math.sin(angle_rad) * th * 0.35)
                p.drawLine(sx2, sy2, ex2, ey2)

        elif skin == "rainbow":
            # Rainbow arc above cup
            arc_r = int(tw * 0.42)
            colors = [QColor("#FF0000"), QColor("#FF7F00"), QColor("#FFFF00"),
                      QColor("#00BB00"), QColor("#0000FF"), QColor("#8B00FF")]
            for i, color in enumerate(colors):
                r = arc_r - i * 3
                p.setPen(QPen(color, 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(cx - r, cup_y_top - r, r * 2, r * 2, 0, 180 * 16)

        elif skin == "detective":
            # Detective hat (fedora style)
            hw = int(tw * 0.38)
            hh = int(th * 0.14)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            p.setBrush(QColor("#5C4000"))
            p.setPen(QPen(QColor("#3A2800"), 1))
            p.drawRect(hx, hy, hw, hh)
            # Wide brim
            brim_w = int(tw * 0.56)
            p.drawRect(cx - brim_w // 2, cup_y_top - 5, brim_w, 8)
            # Hat band
            p.setBrush(QColor("#222222"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(hx, hy + hh - 5, hw, 5)

        elif skin == "chef_hat":
            # Tall white chef hat
            hw = int(tw * 0.30)
            hh = int(th * 0.28)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor("#CCCCCC"), 1))
            p.drawRoundedRect(hx, hy, hw, hh, 4, 4)
            # Band
            p.setBrush(QColor("#DDDDDD"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(hx, cup_y_top - 6, hw, 6)

        elif skin == "antenna":
            # Robot antenna
            ax = cx
            ay = cup_y_top
            p.setPen(QPen(QColor("#AAAAAA"), 2))
            p.drawLine(ax, ay, ax, ay - int(th * 0.20))
            p.setBrush(QColor("#FF4444"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(ax - 4, ay - int(th * 0.20) - 4, 8, 8)

        elif skin == "crystal":
            # Diamond crystal on top
            dc = int(tw * 0.10)
            dx2 = cx
            dy2 = cup_y_top - int(th * 0.10)
            path = QPainterPath()
            path.moveTo(dx2, dy2 - dc * 2)
            path.lineTo(dx2 + dc, dy2)
            path.lineTo(dx2, dy2 + dc)
            path.lineTo(dx2 - dc, dy2)
            path.closeSubpath()
            p.fillPath(path, QColor(100, 220, 255, 200))
            p.strokePath(path, QPen(QColor("#AAEEFF"), 1))

        elif skin == "neon_glow":
            # Neon glow ring centered at the cup top rim
            glow_r = min(int(tw * 0.32), int(th * 0.22))
            glow_cx = cx
            glow_cy = cup_y_top + glow_r // 2
            # Clamp radius so all ring layers stay within widget bounds
            max_r = min(glow_cx, tw - glow_cx, glow_cy, th - glow_cy) - 6
            if max_r > 4:
                glow_r = min(glow_r, max_r)
                for alpha, width in [(30, 10), (60, 6), (120, 3)]:
                    p.setPen(QPen(QColor(0, 229, 255, alpha), width))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(glow_cx - glow_r, glow_cy - glow_r,
                                  glow_r * 2, glow_r * 2)

        elif skin == "medal":
            # Champion medal hanging from cup handle
            mx = cx + int(tw * 0.36)
            my = cy
            p.setPen(QPen(QColor("#DAA520"), 2))
            p.drawLine(mx, cup_y_top + int(th * 0.10), mx, my - int(th * 0.08))
            p.setBrush(QColor("#FFD700"))
            p.setPen(QPen(QColor("#B8860B"), 1))
            mr = int(tw * 0.09)
            p.drawEllipse(mx - mr, my - mr, mr * 2, mr * 2)
            p.setPen(QPen(QColor("#333333"), 1))
            p.setFont(QFont("Arial", max(5, int(tw * 0.10)), QFont.Weight.Bold))
            p.drawText(mx - mr, my - mr, mr * 2, mr * 2,
                       Qt.AlignmentFlag.AlignCenter, "1")

        elif skin == "suit":
            # Tuxedo: black jacket sides + white shirt front + red bow tie
            cup_w_s = int(tw * 0.62)
            cup_h_s = int(th * 0.52)
            cup_x_s = cx - cup_w_s // 2
            top_ex = int(cup_w_s * 0.1)
            shirt_hw = max(5, int(cup_w_s * 0.18))
            p.save()
            p.setClipPath(self._cup_safe_clip(cx, cy))
            p.setBrush(QColor("#1A1A1A"))
            p.setPen(Qt.PenStyle.NoPen)
            # Left jacket panel
            p.drawRect(cup_x_s - top_ex, cup_y_top,
                       cx - shirt_hw - (cup_x_s - top_ex), cup_h_s)
            # Right jacket panel
            p.drawRect(cx + shirt_hw, cup_y_top,
                       cup_x_s + cup_w_s + top_ex - cx - shirt_hw, cup_h_s)
            # White shirt front
            p.setBrush(QColor("#F5F5F5"))
            p.drawRect(cx - shirt_hw, cup_y_top, shirt_hw * 2, cup_h_s)
            # Shirt buttons
            p.setBrush(QColor("#999999"))
            for bi in range(3):
                btn_y = cup_y_top + cup_h_s * (bi + 1) // 4
                p.drawEllipse(cx - 2, btn_y - 2, 4, 4)
            p.restore()
            # Bow tie at collar top (above face zone)
            bt_y = cup_y_top + max(3, int(cup_h_s * 0.05))
            bt_w = max(5, int(tw * 0.09))
            bt_h = max(3, int(th * 0.04))
            bow_l = QPainterPath()
            bow_l.moveTo(float(cx - bt_w), float(bt_y - bt_h))
            bow_l.lineTo(float(cx), float(bt_y))
            bow_l.lineTo(float(cx - bt_w), float(bt_y + bt_h))
            bow_l.closeSubpath()
            p.fillPath(bow_l, QColor("#CC0000"))
            bow_r = QPainterPath()
            bow_r.moveTo(float(cx + bt_w), float(bt_y - bt_h))
            bow_r.lineTo(float(cx), float(bt_y))
            bow_r.lineTo(float(cx + bt_w), float(bt_y + bt_h))
            bow_r.closeSubpath()
            p.fillPath(bow_r, QColor("#CC0000"))
            p.setBrush(QColor("#990000"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - 3, bt_y - 3, 6, 6)

        elif skin == "superhero":
            # Red cape strips on cup sides + gold star emblem at collar
            cup_w_sp = int(tw * 0.62)
            cup_h_sp = int(th * 0.52)
            cup_x_sp = cx - cup_w_sp // 2
            top_ex = int(cup_w_sp * 0.1)
            cape_strip_w = max(5, int(cup_w_sp * 0.20))
            # Left cape strip (outer edge of cup)
            p.setBrush(QColor("#CC0000"))
            p.setPen(Qt.PenStyle.NoPen)
            cap_l = QPainterPath()
            cap_l.moveTo(float(cup_x_sp - top_ex), float(cup_y_top))
            cap_l.lineTo(float(cup_x_sp - top_ex + cape_strip_w), float(cup_y_top))
            cap_l.lineTo(float(cup_x_sp), float(cup_y_top + cup_h_sp))
            cap_l.lineTo(float(cup_x_sp - top_ex), float(cup_y_top + cup_h_sp))
            cap_l.closeSubpath()
            p.fillPath(cap_l, QColor("#CC0000"))
            # Right cape strip
            cap_r = QPainterPath()
            cap_r.moveTo(float(cup_x_sp + cup_w_sp + top_ex - cape_strip_w), float(cup_y_top))
            cap_r.lineTo(float(cup_x_sp + cup_w_sp + top_ex), float(cup_y_top))
            cap_r.lineTo(float(cup_x_sp + cup_w_sp + top_ex), float(cup_y_top + cup_h_sp))
            cap_r.lineTo(float(cup_x_sp + cup_w_sp), float(cup_y_top + cup_h_sp))
            cap_r.closeSubpath()
            p.fillPath(cap_r, QColor("#CC0000"))
            # Gold star emblem at collar (top of cup — always above face zone)
            emb_cx = cx
            emb_cy = cup_y_top + max(4, int(cup_h_sp * 0.07))
            emb_r = max(4, int(tw * 0.09))
            star_path = QPainterPath()
            for k in range(5):
                oa = math.radians(-90 + k * 72)
                ia = math.radians(-90 + k * 72 + 36)
                op = (emb_cx + math.cos(oa) * emb_r, emb_cy + math.sin(oa) * emb_r)
                ip = (emb_cx + math.cos(ia) * emb_r * 0.4, emb_cy + math.sin(ia) * emb_r * 0.4)
                if k == 0:
                    star_path.moveTo(float(op[0]), float(op[1]))
                else:
                    star_path.lineTo(float(op[0]), float(op[1]))
                star_path.lineTo(float(ip[0]), float(ip[1]))
            star_path.closeSubpath()
            p.fillPath(star_path, QColor("#FFD700"))
            p.strokePath(star_path, QPen(QColor("#CC8800"), 1))

        elif skin == "armor":
            # Silver armor plates on cup sides + shoulder pauldrons + gorget
            cup_w_a = int(tw * 0.62)
            cup_h_a = int(th * 0.52)
            cup_x_a = cx - cup_w_a // 2
            top_ex = int(cup_w_a * 0.1)
            # Shoulder pauldrons outside the cup (over handles area)
            pld_w = int(tw * 0.14)
            pld_h = int(th * 0.16)
            pld_y = cup_y_top + int(cup_h_a * 0.05)
            for hx_off in (cup_x_a - top_ex - pld_w - 2,
                           cup_x_a + cup_w_a + top_ex + 2):
                p.setBrush(QColor("#8888AA"))
                p.setPen(QPen(QColor("#555566"), 1))
                p.drawRoundedRect(hx_off, pld_y, pld_w, pld_h, 3, 3)
                p.setPen(QPen(QColor("#666677"), 1))
                for lv in range(3):
                    ly = pld_y + lv * pld_h // 3
                    p.drawLine(hx_off + 2, ly, hx_off + pld_w - 2, ly)
            # Armor side plates on cup (clipped)
            plate_w = max(5, int(cup_w_a * 0.22))
            p.save()
            p.setClipPath(self._cup_safe_clip(cx, cy))
            p.setBrush(QColor("#7777AA"))
            p.setPen(QPen(QColor("#555577"), 1))
            p.drawRoundedRect(cup_x_a - top_ex, cup_y_top, plate_w, cup_h_a, 2, 2)
            p.drawRoundedRect(cup_x_a + cup_w_a + top_ex - plate_w, cup_y_top, plate_w, cup_h_a, 2, 2)
            p.setPen(QPen(QColor("#444455"), 1))
            for seg in range(1, 4):
                seg_y = cup_y_top + seg * cup_h_a // 4
                p.drawLine(cup_x_a - top_ex, seg_y, cup_x_a - top_ex + plate_w, seg_y)
                r_s = cup_x_a + cup_w_a + top_ex - plate_w
                p.drawLine(r_s, seg_y, r_s + plate_w, seg_y)
            p.restore()
            # Gorget (neck guard) at top of cup — above face zone
            gorg_w = int(cup_w_a * 0.55)
            gorg_h = max(4, int(cup_h_a * 0.07))
            p.setBrush(QColor("#8888AA"))
            p.setPen(QPen(QColor("#555566"), 1))
            p.drawRoundedRect(cx - gorg_w // 2, cup_y_top - gorg_h // 2, gorg_w, gorg_h, 2, 2)

        p.restore()


# ---------------------------------------------------------------------------
# Pinball (Steely) drawing widget
# ---------------------------------------------------------------------------
class _PinballDrawWidget(_TrophieDrawWidget):
    """Draws Steely the pinball mascot — a metallic chrome sphere."""

    # Steely-specific passive modes — distinct from Trophie's list
    _PASSIVE_MODES = [
        "wireform_glide", "kickback_pulse", "playfield_glass_shimmer",
        "slingshot_hit", "rubber_ring_bounce", "spinner_eye_roll",
        "roll", "solenoid_buzz", "lane_change", "orbit_loop", "insert_lamp_sparkle", "plunger_pull",
        "roll_out", "magnet", "bumper_hit", "spin_out", "drain",
        "multiball", "plunger_launch", "ramp_jump", "tilt_warning", "flipper_catch",
    ]

    # Use different timer ranges from base class so the two mascots desynchronize
    _PASSIVE_MODE_MIN_MS = 6000
    _PASSIVE_MODE_MAX_MS = 15000

    def __init__(self, parent: QWidget, trophy_w: int, trophy_h: int, pad: int = 0) -> None:
        super().__init__(parent, trophy_w, trophy_h, pad)
        # Steely-specific particle/state for steely_animations
        self._smoke_particles: list = []
        self._ghost_particles: list = []
        self._jackpot_particles: list = []
        self._rust_amount: float = 0.0
        # Event-driven / personality animation state
        self._event_anim: str = ""
        self._event_anim_t: float = 0.0

    def _cycle_passive_mode(self) -> None:
        super()._cycle_passive_mode()
        self._smoke_particles = []
        self._ghost_particles = []
        self._jackpot_particles = []

    def start_event_anim(self, name: str) -> None:
        """Trigger a named event or personality animation on Steely."""
        self._event_anim = name
        self._event_anim_t = 0.0
        # Reset associated particle lists for a clean start
        if name == "jackpot_glow":
            self._jackpot_particles = []
        elif name == "overheat":
            self._smoke_particles = []
        elif name == "multiball":
            self._ghost_particles = []

    def _tick(self) -> None:
        super()._tick()
        dt = 0.016
        # Advance event animation timer and auto-expire when duration is reached
        if self._event_anim:
            self._event_anim_t += dt
            duration = steely_animations.EVENT_ANIM_DURATIONS.get(self._event_anim, 0.0)
            if duration > 0.0 and self._event_anim_t >= duration:
                self._event_anim = ""
                self._event_anim_t = 0.0
                self._passive_extra_x = 0.0
                self._passive_extra_y = 0.0
                self._passive_angle = 0.0
        # Dispatch event/personality animation tick (always, while active)
        if self._event_anim:
            tick_fn = getattr(steely_animations, f"tick_event_{self._event_anim}", None)
            if tick_fn:
                tick_fn(self)
            # Position-controlling event animations set _passive_extra_* themselves;
            # skip the passive position logic so they don't conflict.
            if self._event_anim in {"victory_lap", "drain_fall", "plunger_entry",
                                    "proud", "offended"}:
                return
        # Passive mode position updates
        if self._state == IDLE:
            mode = self._passive_mode
            if mode == "roll":
                # Gentle continuous roll — updates angle used in paintEvent
                self._passive_angle = (self._passive_angle + dt * 30.0) % 360.0
                self._passive_extra_x = 0.0
                self._passive_extra_y = 0.0
            elif mode == "solenoid_buzz":
                # Rapid small jitter in both X and Y
                self._passive_extra_x = random.uniform(-3.0, 3.0)
                self._passive_extra_y = random.uniform(-2.0, 2.0)
                self._passive_angle = 0.0
            elif mode == "lane_change":
                # Horizontal zigzag/wave pattern
                cycle = (self._passive_t * 0.8) % 1.0
                self._passive_extra_x = ((cycle / 0.5) * 12.0 - 6.0) if cycle < 0.5 \
                    else (((1.0 - cycle) / 0.5) * 12.0 - 6.0)
                self._passive_extra_y = 0.0
                self._passive_angle = 0.0
            elif mode == "orbit_loop":
                # Small elliptical orbit around the rest position
                self._passive_extra_x = math.cos(self._passive_t * 1.2) * 8.0
                self._passive_extra_y = math.sin(self._passive_t * 1.2) * 5.0
                self._passive_angle = 0.0
            elif mode == "roll_out":
                steely_animations.tick_roll_out(self)
            elif mode == "magnet":
                steely_animations.tick_magnet(self)
            elif mode == "bumper_hit":
                steely_animations.tick_bumper_hit(self)
            elif mode == "spin_out":
                steely_animations.tick_spin_out(self)
            elif mode == "drain":
                steely_animations.tick_drain(self)
            elif mode == "multiball":
                steely_animations.tick_multiball(self)
            elif mode == "plunger_launch":
                steely_animations.tick_plunger_launch(self)
            elif mode == "ramp_jump":
                steely_animations.tick_ramp_jump(self)
            elif mode == "tilt_warning":
                steely_animations.tick_tilt_warning(self)
            elif mode == "flipper_catch":
                steely_animations.tick_flipper_catch(self)
            else:
                self._passive_extra_x = 0.0
                self._passive_extra_y = 0.0
                self._passive_angle = 0.0
        else:
            self._passive_extra_x = 0.0
            self._passive_extra_y = 0.0
            self._passive_angle = 0.0

    def _draw_shimmer(self, p: QPainter) -> None:
        """Silver shimmer sweep across the pinball."""
        sweep_speed = 1.2
        sweep_pos = (self._passive_t * sweep_speed) % 2.0
        if sweep_pos > 1.0:
            return
        tw = self._tw
        th = self._th
        pad = self._pad
        sweep_x = int((sweep_pos - 0.2) * (tw + 40)) - 20 + pad
        sweep_w = max(12, int(tw * 0.25))
        widget_h = th + 2 * pad
        grad = QLinearGradient(float(sweep_x), 0.0, float(sweep_x + sweep_w), float(widget_h))
        grad.setColorAt(0.0, QColor(220, 220, 240, 0))
        grad.setColorAt(0.3, QColor(220, 220, 240, 70))
        grad.setColorAt(0.5, QColor(240, 240, 255, 110))
        grad.setColorAt(0.7, QColor(220, 220, 240, 70))
        grad.setColorAt(1.0, QColor(220, 220, 240, 0))
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRect(sweep_x, 0, sweep_w, widget_h)
        p.restore()

    def paintEvent(self, event) -> None:
        """Extend base paintEvent with Steely-specific overlay draws."""
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # ── Passive mode overlays ────────────────────────────────────────────
        if self._state == IDLE and self._passive_mode == "multiball":
            steely_animations.draw_multiball(p, self)
        if self._state == IDLE and self._passive_mode == "tilt_warning":
            steely_animations.draw_tilt_warning(p, self)
        # ── Rust overlay (persistent, driven by _rust_amount) ────────────────
        if self._rust_amount > 0.05:
            steely_animations.draw_event_rust(p, self)
        # ── Event / personality animation overlays ───────────────────────────
        if self._event_anim == "jackpot_glow":
            steely_animations.draw_event_jackpot_glow(p, self)
        elif self._event_anim == "victory_lap":
            steely_animations.draw_event_victory_lap(p, self)
        elif self._event_anim == "drain_fall":
            steely_animations.draw_event_drain_fall(p, self)
        elif self._event_anim == "overheat":
            steely_animations.draw_event_overheat(p, self)
        elif self._event_anim == "plunger_entry":
            steely_animations.draw_event_plunger_entry(p, self)
        elif self._event_anim == "show_off":
            steely_animations.draw_event_show_off(p, self)
        elif self._event_anim == "nervous":
            steely_animations.draw_event_nervous(p, self)
        p.end()

    def _draw_trophy(self, p: QPainter, cx: int, cy: int) -> None:
        """Draw Steely as a metallic chrome pinball with eyes and handlebar mustache."""
        # Apply skin-based gradient overrides
        skin = getattr(self, "_skin", "classic")
        self._draw_trophy_pinball(p, cx, cy, skin)

    def _draw_trophy_pinball(self, p: QPainter, cx: int, cy: int, skin: str) -> None:
        """Core Steely drawing with optional skin-based gradient."""
        tw = self._tw
        th = self._th

        radius = int(min(tw, th) * 0.38)

        # ── Metallic sphere body ─────────────────────────────────────────────
        # Choose colors based on skin
        if skin in ("gold", "gold_ball"):
            c0, c1, c2, c3, c4 = "#FFFACD", "#FFD700", "#DAA520", "#B8860B", "#705000"
            pen_color = "#8B6914"
        elif skin == "chrome":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#F0F8FF", "#88AACC", "#204870", "#071828"
            pen_color = "#305880"
        elif skin == "fireball":
            c0, c1, c2, c3, c4 = "#FFFF80", "#FF8800", "#CC3300", "#880000", "#330000"
            pen_color = "#660000"
        elif skin == "iceball":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#D0F0FF", "#80C8FF", "#4090D0", "#1050A0"
            pen_color = "#2060B0"
        elif skin == "marble":
            c0, c1, c2, c3, c4 = "#EE88FF", "#AA44CC", "#7711AA", "#440088", "#220044"
            pen_color = "#330066"
        elif skin == "rubber":
            c0, c1, c2, c3, c4 = "#555555", "#333333", "#222222", "#111111", "#000000"
            pen_color = "#444444"
        elif skin == "spotted":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#F8F8F8", "#EBEBEB", "#D0D0D0", "#B0B0B0"
            pen_color = "#888888"
        elif skin == "basketball":
            c0, c1, c2, c3, c4 = "#FF9944", "#FF6600", "#CC4400", "#882200", "#441100"
            pen_color = "#662200"
        elif skin == "tennis":
            c0, c1, c2, c3, c4 = "#FFFF88", "#CCDD00", "#AACC00", "#669900", "#446600"
            pen_color = "#557700"
        elif skin == "bowling":
            c0, c1, c2, c3, c4 = "#6080C0", "#304090", "#182060", "#0C1040", "#060818"
            pen_color = "#101828"
        elif skin == "beach":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#FFFFC0", "#FFE880", "#EEC860", "#CCA040"
            pen_color = "#AA8030"
        elif skin == "camo":
            c0, c1, c2, c3, c4 = "#8B9B5B", "#6B7B3B", "#4B5B2B", "#2B3B1B", "#1B2B0B"
            pen_color = "#384820"
        elif skin == "pixel":
            c0, c1, c2, c3, c4 = "#FF80FF", "#CC00CC", "#880088", "#440044", "#220022"
            pen_color = "#660066"
        elif skin == "galaxy":
            c0, c1, c2, c3, c4 = "#8040C0", "#4820A0", "#281070", "#180840", "#0C0420"
            pen_color = "#301060"
        elif skin == "disco":
            c0, c1, c2, c3, c4 = "#FF80FF", "#CC44CC", "#883399", "#441166", "#180828"
            pen_color = "#662288"
        elif skin == "moon":
            c0, c1, c2, c3, c4 = "#C0C0C0", "#909090", "#606060", "#363636", "#1C1C1C"
            pen_color = "#404040"
        elif skin == "planet":
            c0, c1, c2, c3, c4 = "#F0E080", "#D4A840", "#B08020", "#785010", "#3C2808"
            pen_color = "#604018"
        elif skin == "skull":
            c0, c1, c2, c3, c4 = "#484848", "#282828", "#181818", "#0C0C0C", "#040404"
            pen_color = "#303030"
        elif skin == "eyeball":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#FAFAFA", "#F0F0F0", "#E0E0E0", "#C8C8C8"
            pen_color = "#B0B0B0"
        elif skin == "8ball":
            c0, c1, c2, c3, c4 = "#404040", "#202020", "#101010", "#080808", "#020202"
            pen_color = "#303030"
        else:
            c0, c1, c2, c3, c4 = "#FFFFFF", "#E8E8F0", "#A0A8B8", "#606880", "#303040"
            pen_color = "#404050"

        # ── Planet skin: draw ring back-half before ball so it appears behind ────
        if skin == "planet":
            ring_rx = int(radius * 1.4)
            ring_ry = int(radius * 0.35)
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor("#DAA520"), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            # Upper semicircle (0° → 180° CCW) appears behind the ball
            p.drawArc(cx - ring_rx, cy - ring_ry, ring_rx * 2, ring_ry * 2, 0, 180 * 16)
            p.restore()

        grad = QRadialGradient(float(cx - radius // 4), float(cy - radius // 3), float(radius * 1.4))
        grad.setColorAt(0.0,  QColor(c0))
        grad.setColorAt(0.15, QColor(c1))
        grad.setColorAt(0.45, QColor(c2))
        grad.setColorAt(0.75, QColor(c3))
        grad.setColorAt(1.0,  QColor(c4))
        p.setBrush(grad)
        p.setPen(QPen(QColor(pen_color), 2))
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # ── Specular highlight (small bright spot top-left) ──────────────────
        hl_r = max(3, radius // 4)
        hl_x = cx - radius // 3
        hl_y = cy - radius // 2
        hl_grad = QRadialGradient(float(hl_x), float(hl_y), float(hl_r * 1.5))
        hl_grad.setColorAt(0.0, QColor(255, 255, 255, 220))
        hl_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hl_grad)
        p.drawEllipse(hl_x - hl_r, hl_y - hl_r, hl_r * 2, hl_r * 2)

        # Secondary soft highlight (lower right)
        hl2_r = max(2, radius // 5)
        hl2_x = cx + radius // 3
        hl2_y = cy + radius // 3
        hl2_grad = QRadialGradient(float(hl2_x), float(hl2_y), float(hl2_r * 2))
        hl2_grad.setColorAt(0.0, QColor(180, 200, 255, 80))
        hl2_grad.setColorAt(1.0, QColor(180, 200, 255, 0))
        p.setBrush(hl2_grad)
        p.drawEllipse(hl2_x - hl2_r, hl2_y - hl2_r, hl2_r * 2, hl2_r * 2)

        # ── Spotted ball patches (drawn before face so face renders on top) ─────
        if skin == "spotted":
            ball_path = QPainterPath()
            ball_path.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            p.save()
            p.setClipPath(ball_path)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor("#111111"))
            p.setPen(Qt.PenStyle.NoPen)
            patch_r = int(radius * 0.18)
            dist = int(radius * 0.62)
            for angle_deg in [0, 72, 144, 216, 288]:
                a = math.radians(angle_deg)
                px2 = cx + int(math.cos(a) * dist)
                py2 = cy + int(math.sin(a) * dist)
                p.drawEllipse(px2 - patch_r, py2 - patch_r, patch_r * 2, patch_r * 2)
            p.restore()

        # ── Disco ball tiles (drawn before face so face renders on top) ──────────
        elif skin == "disco":
            ball_path = QPainterPath()
            ball_path.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            p.save()
            p.setClipPath(ball_path)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            sq = max(8, int(radius * 0.35))
            step = sq + 2
            colors_disco = [QColor("#FF44FF"), QColor("#44FFFF"), QColor("#FFFF44"),
                            QColor("#FF4488"), QColor("#44FF88"), QColor("#8844FF"),
                            QColor("#FF8844"), QColor("#44FF44")]
            ci = 0
            p.setPen(QPen(QColor(0, 0, 0, 60), 1))
            for row in range(-6, 7):
                for col in range(-6, 7):
                    tx = cx + col * step - sq // 2
                    ty = cy + row * step - sq // 2
                    tile_cx = tx + sq // 2
                    tile_cy = ty + sq // 2
                    d = math.sqrt((tile_cx - cx) ** 2 + (tile_cy - cy) ** 2)
                    if d < radius * 0.92:
                        p.setBrush(colors_disco[ci % len(colors_disco)])
                        p.drawRect(tx, ty, sq, sq)
                        ci += 1
            p.restore()

        # ── Pixel ball grid (drawn before face so face renders on top) ───────────
        elif skin == "pixel":
            ball_path = QPainterPath()
            ball_path.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            p.save()
            p.setClipPath(ball_path)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            pix = max(6, int(radius * 0.28))
            pixel_colors = [QColor("#FF00FF"), QColor("#00FFFF"), QColor("#FFFF00"),
                            QColor("#FF8800"), QColor("#00FF88"), QColor("#8800FF")]
            p.setPen(Qt.PenStyle.NoPen)
            for row in range(-6, 7):
                for col in range(-6, 7):
                    tile_x = cx + col * pix
                    tile_y = cy + row * pix
                    tile_cx = tile_x + pix // 2
                    tile_cy = tile_y + pix // 2
                    d = math.sqrt((tile_cx - cx) ** 2 + (tile_cy - cy) ** 2)
                    if d < radius * 0.90:
                        p.setBrush(pixel_colors[(row + col) % len(pixel_colors)])
                        p.drawRect(tile_x, tile_y, pix - 1, pix - 1)
            p.restore()

        # ── Eyes ─────────────────────────────────────────────────────────────
        eye_y = cy - radius // 5
        eye_r = max(4, int(tw * 0.08))
        left_eye_x = cx - int(tw * 0.12)
        right_eye_x = cx + int(tw * 0.12)

        for ex in (left_eye_x, right_eye_x):
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor("#333333"), 1))
            if self._blink or self._state == SLEEPY:
                blink_h = eye_r if self._eye_half else 2
                p.drawEllipse(ex - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2)
                p.setBrush(QColor("#8090A8"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(ex - eye_r - 1, eye_y - eye_r - 1, eye_r * 2 + 2, blink_h + 2)
            else:
                p.drawEllipse(ex - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2)

            if not self._blink:
                pr = max(2, int(eye_r * 0.55))
                if self._state == SURPRISED:
                    pr = eye_r - 1
                px = ex + self._pupil_dx
                py = eye_y + self._pupil_dy
                p.setBrush(QColor("#111111"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(px - pr, py - pr, pr * 2, pr * 2)
                # Eye shine
                p.setBrush(QColor("#FFFFFF"))
                shine_r = max(1, pr // 3)
                p.drawEllipse(px - pr // 3, py - pr // 3, shine_r, shine_r)

        # ── Handlebar mustache ────────────────────────────────────────────────
        mst_y = eye_y + eye_r + 3
        mst_cx = cx
        mst_w = int(tw * 0.34)
        mst_h = int(tw * 0.12)

        p.setPen(QPen(QColor("#1A1A1A"), 2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor("#1A1A1A"))

        # Left side of mustache (curls left and up)
        left_mst = QPainterPath()
        left_mst.moveTo(mst_cx, mst_y)
        left_mst.cubicTo(
            mst_cx - mst_w * 0.3, mst_y + mst_h * 0.8,
            mst_cx - mst_w * 0.7, mst_y + mst_h * 1.0,
            mst_cx - mst_w * 0.5, mst_y - mst_h * 0.3
        )
        left_mst.cubicTo(
            mst_cx - mst_w * 0.4, mst_y - mst_h * 0.7,
            mst_cx - mst_w * 0.1, mst_y + mst_h * 0.1,
            mst_cx, mst_y
        )
        p.fillPath(left_mst, QColor("#1A1A1A"))
        p.drawPath(left_mst)

        # Right side of mustache (mirror)
        right_mst = QPainterPath()
        right_mst.moveTo(mst_cx, mst_y)
        right_mst.cubicTo(
            mst_cx + mst_w * 0.3, mst_y + mst_h * 0.8,
            mst_cx + mst_w * 0.7, mst_y + mst_h * 1.0,
            mst_cx + mst_w * 0.5, mst_y - mst_h * 0.3
        )
        right_mst.cubicTo(
            mst_cx + mst_w * 0.4, mst_y - mst_h * 0.7,
            mst_cx + mst_w * 0.1, mst_y + mst_h * 0.1,
            mst_cx, mst_y
        )
        p.fillPath(right_mst, QColor("#1A1A1A"))
        p.drawPath(right_mst)

    def _steely_safe_clip(self, cx: int, cy: int) -> QPainterPath:
        """Return the ball circle path minus the face exclusion zone.

        Used by surface overlay skins so they don't paint over Steely's
        eyes and mustache.
        """
        tw = self._tw
        th = self._th
        radius = int(min(tw, th) * 0.38)
        eye_y = cy - radius // 5
        eye_r = max(4, int(tw * 0.08))
        mst_w = int(tw * 0.34)
        mst_h = int(tw * 0.12)
        mst_y = eye_y + eye_r + 3
        fm = eye_r + 4
        ball = QPainterPath()
        ball.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        face = QPainterPath()
        face.addRect(QRectF(
            cx - mst_w // 2 - fm,
            eye_y - eye_r - fm,
            mst_w + fm * 2,
            mst_y + mst_h + fm - (eye_y - eye_r - fm),
        ))
        return ball.subtracted(face)

    def _draw_skin_accessory(self, p: QPainter, cx: int, cy: int) -> None:
        """Draw Steely skin-specific surface decorations."""
        skin = getattr(self, "_skin", "classic")
        if skin in ("classic", "chrome", "gold", "gold_ball", "fireball",
                    "iceball", "marble", "rubber", "disco", "pixel"):
            # These are handled purely by gradient — no extra overlay needed
            return
        tw = self._tw
        th = self._th
        radius = int(min(tw, th) * 0.38)
        # Face zone coordinates — shared by multiple skins for exclusion logic
        eye_y = cy - radius // 5
        eye_r = max(4, int(tw * 0.08))
        mst_w = int(tw * 0.34)
        mst_h = int(tw * 0.12)
        mst_y = eye_y + eye_r + 3

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if skin == "8ball":
            # White circle with "8" — shifted to lower half so it doesn't cover the eyes
            cr = int(radius * 0.38)
            cy_8 = cy + int(radius * 0.18)
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - cr, cy_8 - cr, cr * 2, cr * 2)
            p.setPen(QPen(QColor("#111111"), 1))
            p.setFont(QFont("Arial", max(6, cr - 2), QFont.Weight.Bold))
            p.drawText(cx - cr, cy_8 - cr, cr * 2, cr * 2,
                       Qt.AlignmentFlag.AlignCenter, "8")

        elif skin == "spotted":
            # Outer ring patches — ball circle clip, no face exclusion
            # (inner ring patches were drawn before the face in _draw_trophy_pinball)
            ball_clip = QPainterPath()
            ball_clip.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            p.save()
            p.setClipPath(ball_clip)
            p.setBrush(QColor("#111111"))
            p.setPen(Qt.PenStyle.NoPen)
            outer_r = int(radius * 0.15)
            dist_out = int(radius * 0.80)
            for angle_deg in [36, 108, 180, 252, 324]:
                a = math.radians(angle_deg)
                px2 = cx + int(math.cos(a) * dist_out)
                py2 = cy + int(math.sin(a) * dist_out)
                p.drawEllipse(px2 - outer_r, py2 - outer_r, outer_r * 2, outer_r * 2)
            p.restore()

        elif skin == "basketball":
            # Seam lines — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setPen(QPen(QColor(60, 20, 0, 220), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(cx, cy - radius, cx, cy + radius)
            p.drawArc(cx - radius, cy - radius // 2, radius * 2, radius, 0, 180 * 16)
            p.drawArc(cx - radius, cy - radius // 2, radius * 2, radius, 180 * 16, 180 * 16)
            p.restore()

        elif skin == "tennis":
            # White seam curves — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setPen(QPen(QColor("#FFFFFF"), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(cx - radius, cy - radius, radius * 2, radius * 2,
                      45 * 16, 90 * 16)
            p.drawArc(cx - radius, cy - radius, radius * 2, radius * 2,
                      225 * 16, 90 * 16)
            p.restore()

        elif skin == "bowling":
            # Three finger holes — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setBrush(QColor("#333333"))
            p.setPen(Qt.PenStyle.NoPen)
            hr = max(3, int(radius * 0.15))
            for hx2, hy2 in [(cx, cy - int(radius * 0.3)),
                             (cx - int(radius * 0.25), cy + int(radius * 0.1)),
                             (cx + int(radius * 0.25), cy + int(radius * 0.1))]:
                p.drawEllipse(hx2 - hr, hy2 - hr, hr * 2, hr * 2)
            p.restore()

        elif skin == "eyeball":
            # Big iris centred in the lower half of the ball so it clears the eyes
            iris_cy = cy + int(radius * 0.20)
            iris_r = int(radius * 0.50)
            p.setBrush(QColor("#44AAFF"))
            p.setPen(QPen(QColor("#2277CC"), 1))
            p.drawEllipse(cx - iris_r, iris_cy - iris_r, iris_r * 2, iris_r * 2)
            p.setBrush(QColor("#111111"))
            p.setPen(Qt.PenStyle.NoPen)
            pr = int(iris_r * 0.55)
            p.drawEllipse(cx - pr, iris_cy - pr, pr * 2, pr * 2)
            p.setBrush(QColor("#FFFFFF"))
            shine_r = max(2, pr // 3)
            p.drawEllipse(cx - pr // 3, iris_cy - pr // 3, shine_r, shine_r)

        elif skin == "planet":
            # Front half of Saturn ring — lower arc drawn in front of ball
            ring_rx = int(radius * 1.4)
            ring_ry = int(radius * 0.35)
            p.setPen(QPen(QColor("#DAA520"), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            # Lower semicircle (180° → 360° CCW) appears in front of the ball
            p.drawArc(cx - ring_rx, cy - ring_ry, ring_rx * 2, ring_ry * 2, 180 * 16, 180 * 16)

        elif skin == "moon":
            # Smooth crescent via path subtraction — no rectangular face-clip artifacts
            off = int(radius * 0.35)
            ball_path = QPainterPath()
            ball_path.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            inner_path = QPainterPath()
            inner_path.addEllipse(QRectF(cx + off - radius, cy - radius, radius * 2, radius * 2))
            crescent = ball_path.subtracted(inner_path)
            p.save()
            p.setBrush(QColor(30, 30, 60, 160))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(crescent)
            p.restore()

        elif skin == "skull":
            # Skull shifted to lower half of ball so it clears Steely's face
            skull_cy = cy + int(radius * 0.18)
            sr = int(radius * 0.35)
            p.setBrush(QColor(255, 255, 255, 200))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - sr, skull_cy - sr, sr * 2, sr * 2)
            p.setBrush(QColor("#111111"))
            eye_off = int(sr * 0.38)
            er = max(2, int(sr * 0.25))
            p.drawEllipse(cx - eye_off - er, skull_cy - er, er * 2, er * 2)
            p.drawEllipse(cx + eye_off - er, skull_cy - er, er * 2, er * 2)
            p.setPen(QPen(QColor("#111111"), 1))
            for i in range(4):
                tx2 = cx - int(sr * 0.4) + i * int(sr * 0.28)
                p.drawLine(tx2, skull_cy + int(sr * 0.35), tx2, skull_cy + int(sr * 0.6))

        elif skin == "beach":
            # Colored vertical stripes — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            colors_b = [QColor("#FF4444"), QColor("#FFFF44"), QColor("#4444FF")]
            stripe_w = int(radius * 0.35)
            for i, col in enumerate(colors_b):
                x2 = cx - stripe_w * len(colors_b) // 2 + i * stripe_w
                p.setBrush(col)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(x2, cy - radius, stripe_w, radius * 2)
            p.restore()

        elif skin == "camo":
            # Camo blobs — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            camo_colors = [QColor(60, 80, 40, 160), QColor(40, 60, 20, 140),
                           QColor(80, 70, 30, 120)]
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(6):
                bx2 = cx + int((i - 3) * radius * 0.3)
                by2 = cy + int(((i % 3) - 1) * radius * 0.3)
                br = int(radius * 0.22)
                p.setBrush(camo_colors[i % len(camo_colors)])
                p.drawEllipse(bx2 - br, by2 - br, br * 2, br * 2)
            p.restore()

        elif skin == "galaxy":
            # Star dots — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(8):
                a2 = math.radians(i * 45 + 22)
                sx3 = cx + int(math.cos(a2) * radius * 0.6)
                sy3 = cy + int(math.sin(a2) * radius * 0.6)
                p.drawEllipse(sx3 - 2, sy3 - 2, 4, 4)
            p.restore()

        # ── Clothing / wearable skins ─────────────────────────────────────────
        elif skin == "scarf":
            # Knitted scarf wrapped below the mustache
            scarf_top = mst_y + mst_h + 6
            scarf_colors = [QColor("#CC3300"), QColor("#FF6600"), QColor("#FFCC00"),
                            QColor("#CC3300"), QColor("#FF6600")]
            band_h = max(3, int(radius * 0.13))
            p.setPen(Qt.PenStyle.NoPen)
            for i, col in enumerate(scarf_colors):
                by2 = scarf_top + i * band_h
                mid_y2 = by2 + band_h // 2
                dy2 = abs(mid_y2 - cy)
                if dy2 >= radius:
                    break
                hw2 = int(math.sqrt(max(0, radius * radius - dy2 * dy2)))
                p.setBrush(col)
                p.drawRect(cx - hw2, by2, hw2 * 2, band_h)
            # Dangling scarf tail on the right
            tail_start_y = scarf_top + band_h
            tail_x = cx + int(radius * 0.60)
            if abs(tail_start_y - cy) < radius:
                tail_w = max(4, int(radius * 0.18))
                tail_h = int(radius * 0.50)
                p.setBrush(QColor("#CC3300"))
                p.drawRect(tail_x, tail_start_y, tail_w, tail_h)
                # Tassel fringe
                p.setBrush(QColor("#FFD700"))
                for ti in range(3):
                    tx3 = tail_x + ti * max(1, tail_w // 3)
                    p.drawRect(tx3, tail_start_y + tail_h,
                               max(2, tail_w // 3 - 1), int(radius * 0.10))

        elif skin == "bow_tie":
            # Small bow tie just below the mustache
            bt_cx = cx
            bt_cy = mst_y + mst_h + max(6, int(radius * 0.14))
            bt_w = max(7, int(tw * 0.14))
            bt_h = max(3, int(tw * 0.07))
            bow_l = QPainterPath()
            bow_l.moveTo(float(bt_cx - bt_w), float(bt_cy - bt_h))
            bow_l.lineTo(float(bt_cx), float(bt_cy))
            bow_l.lineTo(float(bt_cx - bt_w), float(bt_cy + bt_h))
            bow_l.closeSubpath()
            p.fillPath(bow_l, QColor("#CC0044"))
            p.strokePath(bow_l, QPen(QColor("#880033"), 1))
            bow_r = QPainterPath()
            bow_r.moveTo(float(bt_cx + bt_w), float(bt_cy - bt_h))
            bow_r.lineTo(float(bt_cx), float(bt_cy))
            bow_r.lineTo(float(bt_cx + bt_w), float(bt_cy + bt_h))
            bow_r.closeSubpath()
            p.fillPath(bow_r, QColor("#CC0044"))
            p.strokePath(bow_r, QPen(QColor("#880033"), 1))
            # Center knot
            p.setBrush(QColor("#990033"))
            p.setPen(Qt.PenStyle.NoPen)
            knot_r = max(2, bt_h // 2)
            p.drawEllipse(bt_cx - knot_r, bt_cy - knot_r, knot_r * 2, knot_r * 2)

        elif skin == "bandana":
            # Red bandana capping the very top of the ball (above face zone)
            ban_h = int(radius * 0.30)
            ban_bot = cy - radius + ban_h
            # Clip to the top cap of the ball
            ban_path = QPainterPath()
            ban_path.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            cut_path = QPainterPath()
            cut_path.addRect(QRectF(float(cx - radius - 2), float(ban_bot),
                                    float(radius * 2 + 4), float(radius * 2)))
            top_cap = ban_path.subtracted(cut_path)
            p.setBrush(QColor("#CC2200"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(top_cap)
            # White polka dots on bandana
            p.setBrush(QColor(255, 255, 255, 140))
            dr = radius - ban_h // 2
            for angle_deg in [200, 240, 270, 300, 340]:
                a3 = math.radians(angle_deg)
                dx3 = cx + int(math.cos(a3) * dr * 0.55)
                dy3 = cy + int(math.sin(a3) * dr * 0.65)
                if dy3 <= ban_bot:
                    p.drawEllipse(dx3 - 2, dy3 - 2, 4, 4)
            # Knot at upper-left with short tails
            kx = cx - int(radius * 0.62)
            ky = cy - int(radius * 0.78)
            p.setBrush(QColor("#991100"))
            p.setPen(QPen(QColor("#661100"), 1))
            p.drawEllipse(kx - 5, ky - 4, 10, 8)
            p.setPen(QPen(QColor("#CC2200"), 2))
            p.drawLine(kx, ky - 4, kx - 7, ky - 11)
            p.drawLine(kx, ky + 4, kx - 9, ky + 9)

        elif skin == "monocle":
            # Gold monocle ring on the right eye with a chain hanging down.
            # Intentionally overlaps that eye — the glass is part of the look.
            r_eye_x = cx + int(tw * 0.12)
            mono_r = eye_r + 4
            # Subtle glass tint
            p.setBrush(QColor(200, 230, 255, 50))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(r_eye_x - mono_r + 2, eye_y - mono_r + 2,
                          mono_r * 2 - 4, mono_r * 2 - 4)
            # Gold frame
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#DAA520"), 2))
            p.drawEllipse(r_eye_x - mono_r, eye_y - mono_r, mono_r * 2, mono_r * 2)
            # Chain from bottom-right of monocle to lower-right of ball
            chain_x1 = r_eye_x + int(mono_r * 0.7)
            chain_y1 = eye_y + int(mono_r * 0.7)
            chain_x2 = cx + int(radius * 0.60)
            chain_y2 = cy + int(radius * 0.45)
            p.setPen(QPen(QColor("#DAA520"), 1, Qt.PenStyle.DotLine))
            p.drawLine(chain_x1, chain_y1, chain_x2, chain_y2)

        elif skin == "headphones":
            # Headphones arching over the top with ear cups on the sides
            arc_r = int(radius * 1.05)
            band_w = max(3, int(radius * 0.10))
            # Headband arc (upper semicircle)
            p.setPen(QPen(QColor("#2A2A2A"), band_w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2,
                      10 * 16, 160 * 16)
            # Left ear cup
            ec_r = max(5, int(radius * 0.26))
            lec_x = cx - arc_r
            lec_y = cy - int(radius * 0.08)
            p.setBrush(QColor("#1A1A1A"))
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawEllipse(lec_x - ec_r, lec_y - ec_r, ec_r * 2, ec_r * 2)
            p.setBrush(QColor("#444444"))
            p.setPen(Qt.PenStyle.NoPen)
            pad_r = max(3, int(ec_r * 0.65))
            p.drawEllipse(lec_x - pad_r, lec_y - pad_r, pad_r * 2, pad_r * 2)
            # Right ear cup
            rec_x = cx + arc_r
            rec_y = lec_y
            p.setBrush(QColor("#1A1A1A"))
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawEllipse(rec_x - ec_r, rec_y - ec_r, ec_r * 2, ec_r * 2)
            p.setBrush(QColor("#444444"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(rec_x - pad_r, rec_y - pad_r, pad_r * 2, pad_r * 2)

        p.restore()


