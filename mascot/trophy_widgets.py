"""trophy_widgets.py — GUITrophie and OverlayTrophie mascot widgets.

GUITrophie lives in the bottom-left corner of the MainWindow central widget.
OverlayTrophie is a standalone always-on-top desktop widget (draggable).
Both share _TrophieMemory and _TROPHIE_SHARED for the zank bickering system.
"""
from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Optional

from mascot.trophy_data import (
    _TrophieMemory,
    _TROPHIE_SHARED,
    _ZANK_PAIRS,
    _ZANK_GUI_LINES,
    _ZANK_OVERLAY_LINES,
    _IDLE_BICKER_EXCHANGES,
    _GUI_TIPS,
    _GUI_EVENT_TIPS,
    _GUI_IDLE_TIPS,
    _GUI_RANDOM,
    _GUI_ZANK,
    _GUI_DUEL,
    _OV_ROM_START,
    _OV_SESSION_END,
    _OV_CHALLENGE,
    _OV_HEAT,
    _OV_FLIP,
    _OV_IDLE,
    _OV_DAYTIME,
    _OV_RANDOM,
    _OV_ZANK,
    _OV_DUEL,
    IDLE, TALKING, HAPPY, SAD, SLEEPY, SURPRISED, DISMISSING,
    _ZANK_COOLDOWN_MS,
    _IDLE_BICKER_MIN_COOLDOWN_MS,
    _IDLE_BICKER_MAX_COOLDOWN_MS,
    _IDLE_BICKER_MIN_COOLDOWN_GUI_MS,
    _IDLE_BICKER_MAX_COOLDOWN_GUI_MS,
)
from mascot.trophy_render import (
    _ActionToast,
    _SpeechBubble,
    _TrophieDrawWidget,
    _PinballDrawWidget,
)

from PyQt6.QtCore import (
    QPoint, QSize, Qt, QTimer,
)
from PyQt6.QtGui import (
    QImage, QPainter, QTransform,
)
from PyQt6.QtWidgets import (
    QApplication, QMenu, QWidget,
)

class GUITrophie(QWidget):
    """Trophie mascot that lives in the bottom-left corner of the main window."""

    _TROPHY_W = 60
    _TROPHY_H = 70
    _MARGIN = 8
    # Extra padding added around the logical drawing area on every side so that
    # animations (bounce, jump, wobble, squash) and tall skin accessories (hats,
    # rainbow arc) are never clipped by the widget boundary.
    _DRAW_PAD = 25

    _TROPHIE_GREETINGS = [
        "Hey! I am Trophie! Welcome back!",
        "Trophie reporting for duty! Let's chase some achievements!",
        "Hello there! Ready to track your progress today?",
        "Welcome back, champion! I have been keeping score!",
        "Trophie online! Your achievement journey continues!",
    ]

    def __init__(self, central_widget, cfg) -> None:
        """central_widget is the MainWindow's centralWidget() (the QTabWidget)."""
        super().__init__(central_widget)
        self._cfg = cfg
        # centralWidget is the QTabWidget — used for position/size reference
        self._central = central_widget
        self._memory: Optional[_TrophieMemory] = None  # set via set_memory()
        self._silenced_until = 0.0
        self._last_interaction = time.time()
        self._idle_notified_5m = False
        self._idle_notified_10m = False
        self._current_bubble: Optional[_SpeechBubble] = None
        self._current_tab = ""
        self._greeted = False

        # Draw widget — sized to _TROPHY_W/H + 2*_DRAW_PAD on every side so
        # animations and accessories are not clipped at the widget boundary.
        self._draw = _TrophieDrawWidget(self, self._TROPHY_W, self._TROPHY_H, pad=self._DRAW_PAD)
        self._draw.move(0, 0)
        self._draw.set_skin(cfg.OVERLAY.get("trophie_gui_skin", "classic"))

        self.setFixedSize(self._TROPHY_W + 2 * self._DRAW_PAD, self._TROPHY_H + 2 * self._DRAW_PAD)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.raise_()

        # Idle timer (checks every 30s)
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(30_000)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start()

        # Random personality timer
        self._rand_timer = QTimer(self)
        self._rand_timer.setSingleShot(True)
        self._rand_timer.timeout.connect(self._fire_random)
        self._schedule_random()

        # Zank cooldown tick
        self._zank_tick = QTimer(self)
        self._zank_tick.setInterval(1000)
        self._zank_tick.timeout.connect(self._zank_tick_fn)
        self._zank_tick.start()

        # Spontaneous idle bicker timer (checks every 30s whether the cooldown has elapsed)
        self._idle_bicker_timer = QTimer(self)
        self._idle_bicker_timer.setInterval(30_000)
        self._idle_bicker_timer.timeout.connect(self._try_idle_bicker)
        self._idle_bicker_timer.start()

    def set_memory(self, mem: _TrophieMemory) -> None:
        self._memory = mem

    def set_skin(self, skin_id: str) -> None:
        """Apply a visual skin to the GUI Trophie mascot."""
        self._draw.set_skin(skin_id)

    def greet(self) -> None:
        if self._greeted:
            return
        self._greeted = True
        self._draw.set_state(HAPPY)
        self._show_comment(random.choice(self._TROPHIE_GREETINGS), HAPPY)

    def re_greet(self) -> None:
        """Reset the greeted flag and show a fresh greeting (e.g. when restoring from tray)."""
        self._greeted = False
        self.greet()

    def on_tab_changed(self, idx: int) -> None:
        try:
            # self._central is the QTabWidget (centralWidget)
            tab_name = self._central.tabText(idx).lower()
            self._current_tab = tab_name
            if self._memory:
                self._memory.tab_visits[tab_name] = self._memory.tab_visits.get(tab_name, 0) + 1
        except Exception:
            return
        self._last_interaction = time.time()
        self._fire_tab_tip(tab_name)

    def on_subtab_changed(self, tab_name: str) -> None:
        """Called when the user switches to a sub-tab; tab_name is the sub-tab label text."""
        self._last_interaction = time.time()
        self._fire_tab_tip(tab_name.lower())

    def on_achievement(self) -> None:
        self._last_interaction = time.time()
        self._draw.set_state(HAPPY)
        # Decide: zank or event tip
        if self._try_zank("achievement"):
            return
        if self._memory:
            if self._memory.achievement_sessions == 0:
                self._show_comment_key("evt_first_ach", "Your first achievement! The hunt begins!", HAPPY)
                return
        self._show_comment_key("evt_ach_unlocked", "Achievement unlocked! You are on your way!", HAPPY)

    def on_level_up(self) -> None:
        self._last_interaction = time.time()
        self._try_zank("level_up")

    def on_low_perf_enabled(self) -> None:
        self._show_comment_key("evt_lowperf_on", "Good call! Low Performance Mode saves a lot of CPU.", HAPPY)

    def on_theme_changed(self) -> None:
        self._show_comment_key("evt_new_theme", "Nice theme choice! Try enabling Bloom for the full effect!", HAPPY)

    def on_postproc_enabled(self) -> None:
        self._show_comment_key("evt_postproc_on", "Post-Processing is on! Looks amazing, right?", HAPPY)

    def on_cloud_enabled(self) -> None:
        self._show_comment_key("evt_cloud_on", "Cloud Sync is on! Your achievements are safe now.", HAPPY)

    def on_duel_received(self) -> None:
        """React when a duel invitation arrives."""
        self._last_interaction = time.time()
        self._draw.set_state(SURPRISED)
        options = _GUI_DUEL.get("gui_duel_received", [])
        if options:
            self._show_comment_key("gui_duel_received", random.choice(options), SURPRISED)

    def on_duel_won(self) -> None:
        """React when a duel is won."""
        self._last_interaction = time.time()
        self._draw.set_state(HAPPY)
        options = _GUI_DUEL.get("gui_duel_won", [])
        if options:
            self._show_comment_key("gui_duel_won", random.choice(options), HAPPY)

    def on_duel_lost(self) -> None:
        """React when a duel is lost."""
        self._last_interaction = time.time()
        self._draw.set_state(SAD)
        options = _GUI_DUEL.get("gui_duel_lost", [])
        if options:
            self._show_comment_key("gui_duel_lost", random.choice(options), SAD)

    def on_duel_declined(self) -> None:
        """React when a duel invitation is declined."""
        options = _GUI_DUEL.get("gui_duel_declined", [])
        if options:
            self._show_comment_key("gui_duel_declined", random.choice(options), IDLE)

    def on_duel_accepted(self) -> None:
        """React when a duel invitation is accepted."""
        self._last_interaction = time.time()
        self._draw.set_state(HAPPY)
        options = _GUI_DUEL.get("gui_duel_accepted", [])
        if options:
            self._show_comment_key("gui_duel_accepted", random.choice(options), HAPPY)

    def on_duel_expired(self) -> None:
        """React when a duel invitation expires."""
        options = _GUI_DUEL.get("gui_duel_expired", [])
        if options:
            self._show_comment_key("gui_duel_expired", random.choice(options), IDLE)

    def on_automatch_started(self) -> None:
        """React when the player starts an Auto-Match search."""
        self._last_interaction = time.time()
        self._draw.set_state(SURPRISED)
        options = _GUI_DUEL.get("gui_automatch_started", [])
        if options:
            self._show_comment_key("gui_automatch_started", random.choice(options), SURPRISED)

    def on_automatch_found(self) -> None:
        """React when an Auto-Match opponent is found."""
        self._last_interaction = time.time()
        self._draw.set_state(HAPPY)
        options = _GUI_DUEL.get("gui_automatch_found", [])
        if options:
            self._show_comment_key("gui_automatch_found", random.choice(options), HAPPY)

    def on_automatch_timeout(self) -> None:
        """React when the Auto-Match search times out without finding an opponent."""
        self._draw.set_state(SAD)
        options = _GUI_DUEL.get("gui_automatch_timeout", [])
        if options:
            self._show_comment_key("gui_automatch_timeout", random.choice(options), SAD)

    def on_duel_aborted(self) -> None:
        """React when a duel is aborted due to an invalid session."""
        self._last_interaction = time.time()
        self._draw.set_state(SAD)
        options = _GUI_DUEL.get("gui_duel_aborted", [])
        if options:
            self._show_comment_key("gui_duel_aborted", random.choice(options), SAD)

    def _fire_tab_tip(self, tab_name: str) -> None:
        tab_map = {
            "dashboard":        "tab_dashboard",
            "effects":          "tab_effects",
            "overlay":          "tab_overlay",
            "theme":            "tab_theme",
            "sound":            "tab_sound",
            "appearance":       "tab_appearance",
            "mascots":          "tab_mascots",
            "controls":         "tab_controls",
            "progress":         "tab_progress",
            "cloud":            "tab_cloud",
            "general":          "tab_general",
            "maintenance":      "tab_maintenance",
            "system":           "tab_system",
            "player":           "tab_player",
            "records":          "tab_records",
            "stats":            "tab_records",
            "aweditor":         "tab_aweditor",
            "available maps":   "tab_maps",
            "maps":             "tab_maps",
            "score duels":      "tab_duels",
            "duels":            "tab_duels",
            "global feed":      "tab_duels_global",
            "challenges":       "tab_general",
        }
        for key_part, tip_cat in tab_map.items():
            if key_part in tab_name:
                tips = list(_GUI_TIPS.get(tip_cat, []))
                # Build dynamic controls tip if needed
                if tip_cat == "tab_controls":
                    dyn = self._build_controls_tip()
                    tips = [(k, t) if k != "ctrl_hotkey" else ("ctrl_hotkey", dyn) for k, t in tips]
                    tips = [(k, t) for k, t in tips if t]
                if tips and self._memory:
                    tip = self._memory.pick_unseen(tips)
                    if tip:
                        self._show_comment_key(tip[0], tip[1], TALKING)
                elif tips:
                    tip = random.choice(tips)
                    self._show_comment_key(tip[0], tip[1], TALKING)
                break

    def _build_controls_tip(self) -> Optional[str]:
        try:
            src = self._cfg.OVERLAY.get("toggle_input_source", "keyboard")
            vk = self._cfg.OVERLAY.get("toggle_vk", 120)
            if src == "keyboard":
                from core.input_hook import vk_to_name_en
                key_name = vk_to_name_en(int(vk))
            else:
                key_name = f"Joy btn {vk}"
            return f"Your current overlay toggle is: {key_name}. You can change it here!"
        except Exception:
            return None

    def _check_idle(self) -> None:
        elapsed = time.time() - self._last_interaction
        if elapsed >= 600 and not self._idle_notified_10m:
            self._idle_notified_10m = True
            self._draw.set_state(SLEEPY)
            self._show_comment_key("idle_10m", "ZZZ...", SLEEPY)
        elif elapsed >= 300 and not self._idle_notified_5m:
            self._idle_notified_5m = True
            self._show_comment_key("idle_5m", "Still there? I am here if you need help!", IDLE)
        if elapsed < 300:
            self._idle_notified_5m = False
            self._idle_notified_10m = False
            if self._draw._state == SLEEPY:
                self._draw.set_state(IDLE)

    def _schedule_random(self) -> None:
        base_ms = random.randint(3 * 60_000, 6 * 60_000)
        mult = self._memory.comment_frequency_multiplier() if self._memory else 1.0
        self._rand_timer.start(int(base_ms / max(0.1, mult)))

    def _fire_random(self) -> None:
        self._schedule_random()
        if self._is_silenced():
            return
        # Occasionally do a zank comment if overlay is visible
        if _TROPHIE_SHARED["gui_visible"] and random.random() < 0.2:
            self._fire_zank_comment()
            return
        if self._memory:
            tip = self._memory.pick_unseen(_GUI_RANDOM)
            if tip:
                self._show_comment_key(tip[0], tip[1], IDLE)
        else:
            tip = random.choice(_GUI_RANDOM)
            self._show_comment_key(tip[0], tip[1], IDLE)

    def _fire_zank_comment(self) -> None:
        if self._memory:
            tip = self._memory.pick_unseen(_GUI_ZANK)
        else:
            tip = random.choice(_GUI_ZANK)
        if tip:
            self._show_comment_key(tip[0], tip[1], TALKING)

    def _try_zank(self, trigger: str) -> bool:
        """Attempt to fire a synchronized zank pair. Returns True if zank fired."""
        if not _TROPHIE_SHARED["gui_visible"]:
            return False
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            return False
        for trig, gui_key, ov_key in _ZANK_PAIRS:
            if trig == trigger:
                gui_options = _ZANK_GUI_LINES.get(gui_key, [])
                if gui_options:
                    self._show_comment(random.choice(gui_options), TALKING)
                # Signal overlay to respond in 2 seconds
                _TROPHIE_SHARED["zank_pending_overlay"] = ov_key
                _TROPHIE_SHARED["zank_cooldown_ms"] = _ZANK_COOLDOWN_MS
                return True
        return False

    def _try_idle_bicker(self) -> None:
        """Fire a spontaneous bicker exchange when both trophies are visible."""
        if not _TROPHIE_SHARED["gui_visible"]:
            return
        if _TROPHIE_SHARED["idle_bicker_cooldown_ms"] > 0:
            return
        if self._is_silenced():
            return
        (gui_key, gui_text), (ov_key, ov_text) = random.choice(_IDLE_BICKER_EXCHANGES)
        self._show_comment_key(gui_key, gui_text, TALKING)
        _TROPHIE_SHARED["idle_bicker_ov_key"] = ov_key
        _TROPHIE_SHARED["idle_bicker_ov_text"] = ov_text
        _TROPHIE_SHARED["idle_bicker_cooldown_ms"] = random.randint(
            _IDLE_BICKER_MIN_COOLDOWN_GUI_MS, _IDLE_BICKER_MAX_COOLDOWN_GUI_MS
        )

    def _zank_tick_fn(self) -> None:
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            _TROPHIE_SHARED["zank_cooldown_ms"] = max(0, _TROPHIE_SHARED["zank_cooldown_ms"] - 1000)
        if _TROPHIE_SHARED["idle_bicker_cooldown_ms"] > 0:
            _TROPHIE_SHARED["idle_bicker_cooldown_ms"] = max(
                0, _TROPHIE_SHARED["idle_bicker_cooldown_ms"] - 1000
            )
        # Check if overlay posted a pending gui zank response
        pending = _TROPHIE_SHARED.get("zank_pending_gui")
        if pending:
            _TROPHIE_SHARED["zank_pending_gui"] = None
            options = _ZANK_GUI_LINES.get(pending, [])
            if options:
                self._show_comment(random.choice(options), TALKING)

    def _is_silenced(self) -> bool:
        return time.time() < self._silenced_until

    def _show_comment(self, text: str, state: str = TALKING) -> None:
        if not self.isVisible():
            return
        if self._is_silenced():
            return
        self._dismiss_bubble()
        self._draw.set_state(state)
        bubble = _SpeechBubble(self._central, text, self._memory or _TrophieMemory.__new__(_TrophieMemory))
        bubble._owner = self  # so _do_dismiss can reliably reset our state
        self._current_bubble = bubble
        self._position_bubble(bubble)
        bubble.show()

    def _show_comment_key(self, key: str, text: str, state: str = TALKING) -> None:
        if self._memory:
            self._memory.seen_tips.add(key)
        self._show_comment(text, state)

    def _position_bubble(self, bubble: _SpeechBubble) -> None:
        try:
            pad = self._DRAW_PAD
            bw = bubble.width()
            bh = bubble.height()
            # The drawing centre within the (padded) widget:
            draw_cx = self._TROPHY_W // 2 + pad
            draw_cy_base = self._TROPHY_H // 2 + int(self._TROPHY_H * 0.20) + pad
            # Cup top (widget-relative) and absolute visual positions
            cup_top_in_widget = draw_cy_base - int(self._TROPHY_H * 0.36)
            mascot_cx = self.x() + draw_cx
            cup_top_abs = self.y() + cup_top_in_widget
            base_bottom_abs = self.y() + draw_cy_base + int(self._TROPHY_H * 0.44)
            # Place bubble above the cup; flip below if not enough room
            bx = max(0, mascot_cx - bw // 2)
            by_raw = cup_top_abs - bh - 7
            if by_raw < 0:
                by = base_bottom_abs + 4  # flip below visual base
            else:
                by = by_raw
            # Clamp to central widget bounds
            if bx + bw > self._central.width():
                bx = self._central.width() - bw - 4
            if by + bh > self._central.height():
                by = self._central.height() - bh - 4
            bubble.set_pointer_offset(mascot_cx - bx)
            bubble.move(bx, by)
        except Exception:
            pass

    def _dismiss_bubble(self) -> None:
        if self._current_bubble:
            try:
                self._current_bubble._auto_timer.stop()
                self._current_bubble._begin_fade_out()
            except Exception:
                pass
            self._current_bubble = None
        self._draw.set_state(IDLE)

    def _schedule_quiet_msg(self, msg: str) -> None:
        QTimer.singleShot(500, lambda: self._show_comment(msg, TALKING))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())
        else:
            self._last_interaction = time.time()
            self._dismiss_bubble()
            self._draw.set_state(HAPPY)

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        gpos = self.mapToGlobal(pos)
        menu.addAction("Dismiss", lambda: (self._dismiss_bubble(), self._show_action_toast(gpos)))
        menu.addAction("Silence for 10 minutes", lambda: (self._silence_10m(), self._show_action_toast(gpos)))
        menu.exec(gpos)

    def _show_action_toast(self, global_pos: QPoint) -> None:
        toast = _ActionToast(self._central)
        # Position above the trophie visual area, centred horizontally
        pad = self._DRAW_PAD
        draw_cx = self._TROPHY_W // 2 + pad
        draw_cy_base = self._TROPHY_H // 2 + int(self._TROPHY_H * 0.20) + pad
        cup_top_abs = self.y() + draw_cy_base - int(self._TROPHY_H * 0.36)
        cx = self.x() + draw_cx
        ty = cup_top_abs - toast.height() - 4
        if ty < 0:
            ty = self.y() + draw_cy_base + int(self._TROPHY_H * 0.44) + 4
        toast.popup(self._central.mapToGlobal(QPoint(cx - toast.width() // 2, ty)))

    def _silence_10m(self) -> None:
        self._silenced_until = time.time() + 600
        self._dismiss_bubble()

    def update_position(self, parent_size: QSize) -> None:
        pad = self._DRAW_PAD
        widget_h = self._TROPHY_H + 2 * pad
        # Keep the widget's left edge at or to the right of the parent's left edge.
        # The visual trophy content (cx=55) remains visible even at x=0.
        x = max(0, self._MARGIN - pad)
        # Keep the widget bottom at _MARGIN pixels above the parent bottom so the
        # bottom padding absorbs downward animation without the widget overflowing.
        y = max(0, parent_size.height() - widget_h - self._MARGIN)
        self.move(x, y)
        self.raise_()


# ---------------------------------------------------------------------------
# Overlay Trophie
# ---------------------------------------------------------------------------
class OverlayTrophie(QWidget):
    """Standalone always-on-top desktop overlay Trophie widget."""

    _TROPHY_W = 80
    _TROPHY_H = 90
    _MARGIN = 20
    # Extra padding added around the logical drawing area on every side so that
    # passive animations (orbit, vibrate, bounce, zigzag, spin, wobble, squash)
    # and skin accessories (headphones, planet ring, scarf, flame, bow tie) are
    # never clipped by the widget boundary.
    _DRAW_PAD = 25

    _ROM_START_POLL_INTERVAL_MS = 250   # ms between VPX-visible checks on rom start
    _ROM_START_POLL_MAX_TRIES   = 60    # 60 × 250 ms ≈ 15 s fallback timeout

    _STEELY_GREETINGS = [
        "Hey! I am Steely! Ready to watch your games!",
        "Steely here! The flippers are calling!",
        "Yo! Your favourite pinball is back on duty!",
        "Steely reporting in! Let's roll some high scores!",
        "The ball is back! Time for some serious pinball action!",
    ]

    def __init__(self, parent_window, cfg) -> None:
        super().__init__(None)
        self._cfg = cfg
        self._parent = parent_window
        self._memory: Optional[_TrophieMemory] = None
        self._silenced_until = 0.0
        self._greeted = False
        self._current_bubble: Optional[_SpeechBubble] = None

        self.setWindowTitle("Trophie")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self._TROPHY_W + 2 * self._DRAW_PAD, self._TROPHY_H + 2 * self._DRAW_PAD)

        # Draw widget — sized to _TROPHY_W/H + 2*_DRAW_PAD on every side so
        # animations and skin accessories are not clipped at the widget boundary.
        self._draw = _PinballDrawWidget(self, self._TROPHY_W, self._TROPHY_H, pad=self._DRAW_PAD)
        self._draw.move(0, 0)
        self._draw.set_skin(cfg.OVERLAY.get("trophie_overlay_skin", "classic"))

        # Apply portrait mode on startup
        self.apply_portrait_from_cfg()

        # Connect draw tick to trigger our paintEvent update in portrait mode
        self._draw.add_tick_listener(self.update)

        # Drag support
        self._drag_start: Optional[QPoint] = None
        self._drag_pos_start: Optional[QPoint] = None

        self._restore_position()

        # Idle tracker
        self._last_game_ts = time.time()
        self._idle_shown: dict = {}

        # Session tracking
        self._session_start: Optional[float] = None
        self._session_rom: Optional[str] = None
        self._session_ach_count = 0
        self._today_ach_count = 0
        self._today_session_count = 0
        self._no_ach_sessions_streak = 0

        # Random personality timer
        self._rand_timer = QTimer(self)
        self._rand_timer.setSingleShot(True)
        self._rand_timer.timeout.connect(self._fire_random)
        self._schedule_random()

        # Idle check timer
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(60_000)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start()

        # Daytime comment timer (fires once per session at startup)
        QTimer.singleShot(5000, self._fire_daytime_comment)

        # Zank cooldown tick
        self._zank_tick = QTimer(self)
        self._zank_tick.setInterval(1000)
        self._zank_tick.timeout.connect(self._zank_tick_fn)
        self._zank_tick.start()

    def set_memory(self, mem: _TrophieMemory) -> None:
        self._memory = mem

    def set_skin(self, skin_id: str) -> None:
        """Apply a visual skin to the Steely overlay mascot."""
        self._draw.set_skin(skin_id)
        self.update()

    def _vp_visible(self) -> bool:
        """Return True when the Visual Pinball Player window is currently visible."""
        try:
            w = getattr(self._parent, "watcher", None)
            return bool(w and w._vp_player_visible())
        except Exception:
            return False

    def greet(self) -> None:
        if self._greeted:
            return
        self._greeted = True
        self._draw.set_state(HAPPY)
        self._show_comment(random.choice(self._STEELY_GREETINGS), HAPPY)

    def apply_portrait_from_cfg(self) -> None:
        """Apply portrait/landscape mode based on current config."""
        ov = self._cfg.OVERLAY or {}
        portrait = bool(ov.get("trophie_overlay_portrait", False))
        pad = self._DRAW_PAD
        if portrait:
            # Swap dimensions for portrait (rotated 90°); keep pad on each side
            self.setFixedSize(self._TROPHY_H + 2 * pad, self._TROPHY_W + 2 * pad)
            self._draw.setVisible(False)
        else:
            self.setFixedSize(self._TROPHY_W + 2 * pad, self._TROPHY_H + 2 * pad)
            self._draw.setVisible(True)
        self.update()

    def paintEvent(self, event) -> None:
        ov = self._cfg.OVERLAY or {}
        portrait = bool(ov.get("trophie_overlay_portrait", False))
        if not portrait:
            super().paintEvent(event)
            return
        # Portrait mode: render _draw widget to offscreen image, rotate, then paint
        pad = self._DRAW_PAD
        img = QImage(self._TROPHY_W + 2 * pad, self._TROPHY_H + 2 * pad, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        render_painter = QPainter(img)
        try:
            self._draw.render(render_painter, QPoint(0, 0))
        finally:
            render_painter.end()
        ccw = bool(ov.get("trophie_overlay_rotate_ccw", False))
        angle = -90 if ccw else 90
        img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        painter = QPainter(self)
        try:
            painter.drawImage(0, 0, img)
        finally:
            painter.end()


    def on_rom_start(self, rom: str, table_name: Optional[str] = None) -> None:
        self._session_start = time.time()
        self._session_rom = rom
        self._session_ach_count = 0
        self._today_session_count += 1
        self._last_game_ts = time.time()
        self._idle_shown.clear()
        # Reset idle rust and launch Steely into view
        self._draw._rust_amount = max(0.0, self._draw._rust_amount - 0.8)
        self._draw.start_event_anim("plunger_entry")

        if self._memory:
            self._memory.play_times.append(datetime.now().hour)
            prev_count = self._memory.rom_play_counts.get(rom, 0)
        else:
            prev_count = 0

        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()  # 0=Monday

        # Pick comment
        comment = None
        key = None

        if self._memory and prev_count == 0:
            key, comment = "ov_firsttime", "First time on this table! Good luck!"
        elif self._memory and prev_count > 0:
            fav = self._memory.favourite_rom()
            if fav and fav == rom:
                key, comment = "ov_fav", "Your favourite again? No complaints!"
            else:
                last_played_days = self._days_since_last_played(rom)
                if last_played_days is not None and last_played_days >= 30:
                    key, comment = "ov_dustoff", "Long time no see! Dust off those flippers!"
                elif last_played_days is not None and last_played_days >= 7:
                    key, comment = "ov_longago", "Haven't seen this one in a while!"
                elif table_name:
                    key, comment = "ov_classic", f"Oh! {table_name}! Classic!"

        if comment is None:
            # Time-based fallbacks
            if hour < 10:
                key, comment = "ov_morning", "Morning warm-up! Coffee + pinball!"
            elif 17 <= hour < 21:
                key, comment = "ov_evening", "Evening session! The best time to play!"
            elif hour >= 21:
                key, comment = "ov_nightowl", "Night owl mode activated!"
            elif weekday in (5, 6):
                key, comment = "ov_weekend", "Weekend pinball! No alarms tomorrow!"
            elif weekday == 0:
                key, comment = "ov_monday", "Monday motivation: pinball!"
            elif self._today_session_count == 1:
                key, comment = "ov_firstday", "First game of the day! Let's make it count!"
            elif self._today_session_count == 2:
                key, comment = "ov_onemore", "One more game? That is the spirit!"
            elif self._today_session_count >= 3:
                key, comment = "ov_thirdtoday", "Third table today! You are on a roll!"
            else:
                key, comment = "ov_go", "Let's go! Good luck!"

        if self._memory and rom:
            self._memory.rom_play_counts[rom] = prev_count + 1
            self._memory.save()

        if comment:
            _key = key or "ov_go"
            _comment = comment
            _tries = {"n": 0}

            def _poll():
                try:
                    if self._vp_visible():
                        self._show_comment_key(_key, _comment, HAPPY)
                        return
                    _tries["n"] += 1
                    if _tries["n"] < self._ROM_START_POLL_MAX_TRIES:
                        QTimer.singleShot(self._ROM_START_POLL_INTERVAL_MS, _poll)
                    else:
                        self._show_comment_key(_key, _comment, HAPPY)
                except Exception:
                    self._show_comment_key(_key, _comment, HAPPY)

            QTimer.singleShot(2000, _poll)

    def on_session_ended(self, rom: str) -> None:
        if self._session_start is None:
            return
        duration_s = time.time() - self._session_start
        duration_min = duration_s / 60.0
        ach_count = self._session_ach_count
        self._session_start = None

        if self._memory:
            self._memory.session_durations.append(int(duration_min))
            if ach_count > 0:
                self._memory.achievement_sessions += 1
                self._no_ach_sessions_streak = 0
            else:
                self._memory.no_achievement_sessions += 1
                self._no_ach_sessions_streak += 1
            self._memory.save()

        # Try zank on long session
        if duration_min >= 300:
            self._try_zank("session_5h")
            return

        # Pick end-of-session comment
        now = datetime.now()
        if now.hour == 0 or (now.hour == 23 and now.minute > 55):
            self._show_comment_key("ov_midnight", "Midnight finish! Legendary!", HAPPY)
        elif ach_count == 0 and duration_min < 2:
            self._show_comment_key("ov_tilt", "Tilt? Or just bad luck?", SAD)
        elif ach_count == 0 and duration_min < 5:
            self._show_comment_key("ov_shortsweet", "Short but sweet! Every game counts!", IDLE)
        elif ach_count == 0 and self._no_ach_sessions_streak >= 3:
            self._show_comment_key("ov_dry_spell", "Dry spell... but legends never quit!", SAD)
        elif ach_count == 0 and duration_min > 120:
            self._show_comment_key("ov_grind", "Long session, no achievements... The grind is real!", SAD)
        elif ach_count == 0:
            self._show_comment_key("ov_good_game", "Good game! See you next round", IDLE)
        elif ach_count == 1:
            self._show_comment_key("ov_got_one", "NICE! You got one!", HAPPY)
        elif ach_count == 2:
            self._show_comment_key("ov_double", "Double unlock! Efficient!", HAPPY)
        elif ach_count >= 5:
            self._show_comment_key("ov_avalanche", "Achievement AVALANCHE! How?!", SURPRISED)
        elif duration_min > 120:
            self._show_comment_key("ov_2h", "2 hours in... You okay?", IDLE)
        else:
            self._show_comment_key("ov_got_one", "NICE! You got one!", HAPPY)

    def on_achievement(self) -> None:
        self._session_ach_count += 1
        self._today_ach_count += 1
        self._last_game_ts = time.time()
        # Clear any rust accumulated during idle on new activity
        self._draw._rust_amount = max(0.0, self._draw._rust_amount - 0.5)
        self._draw.set_state(HAPPY)
        self._draw.start_event_anim("jackpot_glow")
        if self._try_zank("achievement"):
            return
        if self._today_ach_count == 1:
            self._show_comment_key("ov_first_blood", "First blood! The hunt is on!", HAPPY)
        elif self._today_ach_count >= 5:
            self._show_comment_key("ov_5today", "5 achievements today! Beast mode!", SURPRISED)
            self._draw.start_event_anim("proud")
        else:
            self._show_comment_key("ov_got_one", "NICE! You got one!", HAPPY)

    def on_level_up(self) -> None:
        self._draw.set_state(HAPPY)
        self._try_zank("level_up")

    def on_duel_received(self) -> None:
        """React when a duel invitation arrives."""
        self._draw.set_state(SURPRISED)
        options = _OV_DUEL.get("ov_duel_received", [])
        if options:
            self._show_comment_key("ov_duel_received", random.choice(options), SURPRISED)

    def on_duel_won(self) -> None:
        """React when a duel is won."""
        self._draw.set_state(HAPPY)
        self._draw.start_event_anim("victory_lap")
        options = _OV_DUEL.get("ov_duel_won", [])
        if options:
            self._show_comment_key("ov_duel_won", random.choice(options), HAPPY)

    def on_duel_lost(self) -> None:
        """React when a duel is lost."""
        self._draw.set_state(SAD)
        self._draw.start_event_anim("drain_fall")
        options = _OV_DUEL.get("ov_duel_lost", [])
        if options:
            self._show_comment_key("ov_duel_lost", random.choice(options), SAD)

    def on_duel_declined(self) -> None:
        """React when a duel invitation is declined."""
        options = _OV_DUEL.get("ov_duel_declined", [])
        if options:
            self._show_comment_key("ov_duel_declined", random.choice(options), IDLE)

    def on_duel_accepted(self) -> None:
        """React when a duel invitation is accepted."""
        self._draw.set_state(HAPPY)
        options = _OV_DUEL.get("ov_duel_accepted", [])
        if options:
            self._show_comment_key("ov_duel_accepted", random.choice(options), HAPPY)

    def on_duel_expired(self) -> None:
        """React when a duel invitation expires."""
        options = _OV_DUEL.get("ov_duel_expired", [])
        if options:
            self._show_comment_key("ov_duel_expired", random.choice(options), IDLE)

    def on_automatch_started(self) -> None:
        """React when the player starts an Auto-Match search."""
        self._draw.set_state(SURPRISED)
        options = _OV_DUEL.get("ov_automatch_started", [])
        if options:
            self._show_comment_key("ov_automatch_started", random.choice(options), SURPRISED)

    def on_automatch_found(self) -> None:
        """React when an Auto-Match opponent is found."""
        self._draw.set_state(HAPPY)
        options = _OV_DUEL.get("ov_automatch_found", [])
        if options:
            self._show_comment_key("ov_automatch_found", random.choice(options), HAPPY)

    def on_automatch_timeout(self) -> None:
        """React when the Auto-Match search times out without finding an opponent."""
        self._draw.set_state(SAD)
        options = _OV_DUEL.get("ov_automatch_timeout", [])
        if options:
            self._show_comment_key("ov_automatch_timeout", random.choice(options), SAD)

    def on_duel_aborted(self) -> None:
        """React when a duel is aborted due to an invalid session."""
        self._draw.set_state(SAD)
        options = _OV_DUEL.get("ov_duel_aborted", [])
        if options:
            self._show_comment_key("ov_duel_aborted", random.choice(options), SAD)

    # ── Idle handling ─────────────────────────────────────────────────────────

    def _check_idle(self) -> None:
        elapsed_min = (time.time() - self._last_game_ts) / 60.0
        now = datetime.now()

        idle_steps = [
            (5,    "ov_idle_5m",   "Still here... waiting...",                    IDLE),
            (10,   "ov_idle_10m",  "Psst. VPX won't start itself!",               IDLE),
            (15,   "ov_idle_15m",  "I could really go for a game right now...",   IDLE),
            (20,   "ov_idle_20m",  "The tables miss you. True story.",             IDLE),
            (30,   "ov_idle_zzz",  "ZZZ...",                                       SLEEPY),
            (45,   "ov_idle_45m",  "At this point I am basically furniture",       SLEEPY),
            (60,   "ov_idle_1h",   "One hour idle... Are you okay out there?",     SLEEPY),
        ]
        if now.hour >= 23 or now.hour < 5:
            idle_steps.append((20, "ov_idle_late", "Go to sleep. The achievements will be here tomorrow!", SLEEPY))
        if 6 <= now.hour < 10:
            idle_steps.append((5, "ov_idle_morn", "Good morning! Ready for some pinball?", HAPPY))
        if now.weekday() >= 5 and 10 <= now.hour < 20:
            idle_steps.append((10, "ov_idle_wknd", "It is the weekend and you are NOT playing?!", IDLE))

        for mins, key, text, state in sorted(idle_steps):
            if elapsed_min >= mins and key not in self._idle_shown:
                self._idle_shown[key] = True
                self._draw.set_state(state)
                self._show_comment_key(key, text, state)
                if mins == 30:
                    self._try_zank("idle_30m")
                    # Start rust accumulation after 30 min idle
                    if self._draw._event_anim != "rust":
                        self._draw.start_event_anim("rust")
                break

        if elapsed_min < 5:
            self._idle_shown.clear()
            if self._draw._state == SLEEPY:
                self._draw.set_state(IDLE)
            # Clear rust when activity resumes
            if self._draw._event_anim == "rust":
                self._draw._event_anim = ""
                self._draw._event_anim_t = 0.0

    def _fire_daytime_comment(self) -> None:
        now = datetime.now()
        weekday = now.weekday()
        hour = now.hour
        month = now.month
        day = now.day

        key = text = None
        if month == 1 and day == 1:
            key, text = "ov_day_ny",   "Happy New Year! First achievement of the year?"
        elif month == 12 and day == 25:
            key, text = "ov_day_xmas", "Playing on Christmas?! Dedicated!"
            self._try_zank("christmas")
            return
        elif month == 10 and day == 31:
            key, text = "ov_day_hal",  "Spooky session! BOO!"
        elif month == 12 and day == 31:
            key, text = "ov_day_nye",  "Last game of the year? Make it count!"
        elif day == 1:
            key, text = "ov_day_new_month", "New month, new achievements!"
        elif weekday == 0:
            key, text = "ov_day_mon",  "Monday? Best day for pinball!"
        elif weekday == 1:
            key, text = "ov_day_tue",  "Tuesday grind! Underrated pinball day!"
        elif weekday == 2:
            key, text = "ov_day_wed",  "Midweek energy! Keep it up!"
        elif weekday == 3:
            key, text = "ov_day_thu",  "Thursday already?! Time flies when you are flipping!"
        elif weekday == 4 and hour >= 17:
            key, text = "ov_day_fri",  "Friday night pinball! The best kind!"
        elif weekday == 5 and 12 <= hour < 18:
            key, text = "ov_day_sat",  "Perfect Saturday afternoon!"
        elif weekday == 6 and hour >= 18:
            key, text = "ov_day_sun",  "Sunday session! One more before Monday!"

        if key and text:
            QTimer.singleShot(8000, lambda: self._show_comment_key(key, text, IDLE))

    def _schedule_random(self) -> None:
        base_ms = random.randint(3 * 60_000, 6 * 60_000)
        mult = self._memory.comment_frequency_multiplier() if self._memory else 1.0
        self._rand_timer.start(int(base_ms / max(0.1, mult)))

    def _fire_random(self) -> None:
        self._schedule_random()
        if self._is_silenced():
            return
        if _TROPHIE_SHARED["gui_visible"] and random.random() < 0.2:
            self._fire_zank_comment()
            return
        if self._memory:
            tip = self._memory.pick_unseen(_OV_RANDOM)
        else:
            tip = random.choice(_OV_RANDOM)
        if tip:
            self._show_comment_key(tip[0], tip[1], IDLE)

    def _fire_zank_comment(self) -> None:
        if not _TROPHIE_SHARED["gui_visible"]:
            return
        if self._memory:
            tip = self._memory.pick_unseen(_OV_ZANK)
        else:
            tip = random.choice(_OV_ZANK)
        if tip:
            self._show_comment_key(tip[0], tip[1], TALKING)

    def _try_zank(self, trigger: str) -> bool:
        if not _TROPHIE_SHARED["gui_visible"]:
            return False
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            return False
        for trig, gui_key, ov_key in _ZANK_PAIRS:
            if trig == trigger:
                ov_options = _ZANK_OVERLAY_LINES.get(ov_key, [])
                if ov_options:
                    ov_text = random.choice(ov_options)
                    # Schedule overlay response 2 seconds after gui fires
                    QTimer.singleShot(2000, lambda t=ov_text, k=ov_key: self._show_comment_key(k, t, TALKING))
                # Signal GUI to show its line
                _TROPHIE_SHARED["zank_pending_gui"] = gui_key
                _TROPHIE_SHARED["zank_cooldown_ms"] = _ZANK_COOLDOWN_MS
                return True
        return False

    def _zank_tick_fn(self) -> None:
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            _TROPHIE_SHARED["zank_cooldown_ms"] = max(0, _TROPHIE_SHARED["zank_cooldown_ms"] - 1000)
        pending = _TROPHIE_SHARED.get("zank_pending_overlay")
        if pending:
            _TROPHIE_SHARED["zank_pending_overlay"] = None
            options = _ZANK_OVERLAY_LINES.get(pending, [])
            if options:
                ov_text = random.choice(options)
                QTimer.singleShot(2000, lambda t=ov_text, k=pending: self._show_comment_key(k, t, TALKING))
        # Handle spontaneous idle bicker response
        bicker_key = _TROPHIE_SHARED.get("idle_bicker_ov_key")
        bicker_text = _TROPHIE_SHARED.get("idle_bicker_ov_text")
        if bicker_key and bicker_text:
            _TROPHIE_SHARED["idle_bicker_ov_key"] = None
            _TROPHIE_SHARED["idle_bicker_ov_text"] = None
            if _TROPHIE_SHARED["gui_visible"]:
                QTimer.singleShot(2000, lambda t=bicker_text, k=bicker_key: self._show_comment_key(k, t, TALKING))

    def _days_since_last_played(self, rom: str) -> Optional[int]:
        # Simple: we don't track dates directly — use play_count heuristic
        return None  # Placeholder; extend with timestamp tracking if needed

    # ── UI ───────────────────────────────────────────────────────────────────

    def _is_silenced(self) -> bool:
        return time.time() < self._silenced_until

    def _show_comment(self, text: str, state: str = TALKING) -> None:
        if not self.isVisible():
            return
        if self._is_silenced():
            return
        self._dismiss_bubble()
        self._draw.set_state(state)
        # Create bubble as a top-level window so it is visible above the small
        # overlay widget (child widgets with negative Y coords get clipped).
        if self._memory is None:
            mem = _TrophieMemory.__new__(_TrophieMemory)
            mem.seen_tips = set()
            mem.dismiss_speed = []
            mem.comments_shown = 0
            mem.comments_dismissed_fast = 0
            mem._fast_dismiss_streak = 0
            mem._told_quiet = False
        else:
            mem = self._memory
        ov = self._cfg.OVERLAY or {}
        portrait = bool(ov.get("trophie_overlay_portrait", False))
        if portrait:
            ccw = bool(ov.get("trophie_overlay_rotate_ccw", False))
            rotation = -90 if ccw else 90
        else:
            rotation = 0
        bubble = _SpeechBubble(None, text, mem, rotation=rotation)
        bubble._owner = self  # so _do_dismiss can still call _schedule_quiet_msg
        bubble.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        bubble.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        bubble.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._current_bubble = bubble
        self._position_bubble(bubble)
        bubble.show()

    def _show_comment_key(self, key: str, text: str, state: str = TALKING) -> None:
        if self._memory:
            self._memory.seen_tips.add(key)
        self._show_comment(text, state)

    def _position_bubble(self, bubble: _SpeechBubble) -> None:
        try:
            bw = bubble.width()
            bh = bubble.height()
            screen_geom = QApplication.primaryScreen().geometry()
            origin = self.mapToGlobal(QPoint(0, 0))
            ov = self._cfg.OVERLAY or {}
            portrait = bool(ov.get("trophie_overlay_portrait", False))
            # Ball top offset in landscape widget coordinates:
            # ball center is at (pad+tw/2, pad+th/2), radius ≈ min(tw,th)*0.38
            pad = self._DRAW_PAD
            ball_top = pad + self._TROPHY_H // 2 - int(min(self._TROPHY_W, self._TROPHY_H) * 0.38)
            if not portrait:
                # Landscape: bubble centered above ball top
                abs_x = origin.x() + pad + self._TROPHY_W // 2 - bw // 2
                abs_y = origin.y() + ball_top - bh - 7
                # If no room above, flip below the ball
                if abs_y < screen_geom.y():
                    abs_y = origin.y() + pad + self._TROPHY_H + 4
                # Clamp to screen
                if abs_x < screen_geom.x():
                    abs_x = screen_geom.x()
                if abs_y < screen_geom.y():
                    abs_y = screen_geom.y()
                if abs_x + bw > screen_geom.right():
                    abs_x = screen_geom.right() - bw
                if abs_y + bh > screen_geom.bottom():
                    abs_y = screen_geom.bottom() - bh
                mascot_cx = origin.x() + pad + self._TROPHY_W // 2
                bubble.set_pointer_offset(mascot_cx - abs_x)
            else:
                # Portrait: widget is _TROPHY_H wide × _TROPHY_W tall.
                # Place bubble to the left or right of the mascot.
                # rotation=90 (CW)  → pointer points LEFT  → bubble to the RIGHT
                # rotation=-90 (CCW) → pointer points RIGHT → bubble to the LEFT
                ccw = bool(ov.get("trophie_overlay_rotate_ccw", False))
                mascot_center_y = origin.y() + self.height() // 2
                if not ccw:
                    # rotation=90: bubble to the right of mascot
                    abs_x = origin.x() + self.width() + 4
                    if abs_x + bw > screen_geom.right():
                        abs_x = origin.x() - bw - 4  # flip to left
                else:
                    # rotation=-90: bubble to the left of mascot
                    abs_x = origin.x() - bw - 4
                    if abs_x < screen_geom.x():
                        abs_x = origin.x() + self.width() + 4  # flip to right
                # Center bubble vertically with mascot
                abs_y = mascot_center_y - bh // 2
                # Clamp to screen
                if abs_x < screen_geom.x():
                    abs_x = screen_geom.x()
                if abs_y < screen_geom.y():
                    abs_y = screen_geom.y()
                if abs_x + bw > screen_geom.right():
                    abs_x = screen_geom.right() - bw
                if abs_y + bh > screen_geom.bottom():
                    abs_y = screen_geom.bottom() - bh
                # Map mascot Y distance to unrotated X (pointer offset).
                # rotation=90:  pointer Y in rotated widget == cx (unrotated X)
                # rotation=-90: pointer Y in rotated widget == bh - cx
                ptr_y = mascot_center_y - abs_y
                if not ccw:
                    bubble.set_pointer_offset(ptr_y)
                else:
                    bubble.set_pointer_offset(bh - ptr_y)
            bubble.move(abs_x, abs_y)
        except Exception:
            pass

    def _dismiss_bubble(self) -> None:
        if self._current_bubble:
            try:
                self._current_bubble._auto_timer.stop()
                self._current_bubble._begin_fade_out()
            except Exception:
                pass
            self._current_bubble = None
        self._draw.set_state(IDLE)

    def _schedule_quiet_msg(self, msg: str) -> None:
        QTimer.singleShot(500, lambda: self._show_comment(msg, TALKING))

    # ── Dragging ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_pos_start = self.pos()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._drag_pos_start + delta)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self._save_position()

    def _save_position(self) -> None:
        try:
            self._cfg.OVERLAY["trophie_overlay_x"] = self.x()
            self._cfg.OVERLAY["trophie_overlay_y"] = self.y()
            self._cfg.save()
        except Exception:
            pass

    def _restore_position(self) -> None:
        try:
            x = int(self._cfg.OVERLAY.get("trophie_overlay_x", -1))
            y = int(self._cfg.OVERLAY.get("trophie_overlay_y", -1))
            if x >= 0 and y >= 0:
                self.move(x, y)
                return
        except Exception:
            pass
        # Default: bottom-left of primary screen
        try:
            pad = self._DRAW_PAD
            screen = QApplication.primaryScreen().geometry()
            self.move(max(0, self._MARGIN - pad),
                      max(0, screen.height() - (self._TROPHY_H + 2 * pad) - self._MARGIN))
        except Exception:
            self.move(self._MARGIN, 600)

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        gpos = self.mapToGlobal(pos)
        menu.addAction("Dismiss comment", lambda: (self._dismiss_bubble(), self._show_action_toast(gpos)))
        menu.addAction("Silence for 10 minutes", lambda: (self._silence_10m(), self._show_action_toast(gpos)))
        move_menu = menu.addMenu("Move to corner...")
        move_menu.addAction("Bottom Left",  lambda: (self._move_to_corner("bl"), self._show_action_toast(gpos)))
        move_menu.addAction("Bottom Right", lambda: (self._move_to_corner("br"), self._show_action_toast(gpos)))
        move_menu.addAction("Top Left",     lambda: (self._move_to_corner("tl"), self._show_action_toast(gpos)))
        move_menu.addAction("Top Right",    lambda: (self._move_to_corner("tr"), self._show_action_toast(gpos)))
        menu.exec(gpos)

    def _show_action_toast(self, global_pos: QPoint) -> None:
        toast = _ActionToast(None)
        # Centre the toast above the mascot widget
        pad = self._DRAW_PAD
        tx = self.x() + pad + self._TROPHY_W // 2 - toast.width() // 2
        ty = self.y() - toast.height() - 4
        try:
            screen = QApplication.primaryScreen().geometry()
            if ty < screen.y():
                ty = self.y() + pad + self._TROPHY_H + 4
            tx = max(screen.x(), min(tx, screen.x() + screen.width()  - toast.width()))
            ty = max(screen.y(), min(ty, screen.y() + screen.height() - toast.height()))
        except Exception:
            pass
        toast.popup(QPoint(tx, ty))

    def _silence_10m(self) -> None:
        self._silenced_until = time.time() + 600
        self._dismiss_bubble()

    def _move_to_corner(self, corner: str) -> None:
        try:
            screen = QApplication.primaryScreen().geometry()
            sw, sh = screen.width(), screen.height()
            pad = self._DRAW_PAD
            ww = self._TROPHY_W + 2 * pad
            wh = self._TROPHY_H + 2 * pad
            m = self._MARGIN
            positions = {
                "bl": (max(0, m - pad), sh - wh - m),
                "br": (sw - ww - m, sh - wh - m),
                "tl": (max(0, m - pad), max(0, m - pad)),
                "tr": (sw - ww - m, max(0, m - pad)),
            }
            self.move(*positions.get(corner, (max(0, m - pad), sh - wh - m)))
            self._save_position()
        except Exception:
            pass
