"""trophy_mascot.py — Trophie mascot companion for VPX Achievement Watcher.

Two instances:
  - GUITrophie  : bottom-left corner of the MainWindow central widget
  - OverlayTrophie : standalone always-on-top desktop widget (draggable)

Both share _TrophieMemory (persisted to <BASE>/trophie_memory.json) and the
_TROPHIE_SHARED coordination dict used for the "zank" (bickering) system.
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import (
    QPoint, QRect, QSize, Qt, QTimer,
)
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMenu, QSizePolicy,
    QVBoxLayout, QWidget,
)

# ---------------------------------------------------------------------------
# Shared state — used for zank (bickering) coordination
# ---------------------------------------------------------------------------
_TROPHIE_SHARED: dict = {
    "gui_visible": False,
    "zank_cooldown_ms": 0,
    "last_gui_comment_key": None,
    "last_overlay_comment_key": None,
    "zank_pending_overlay": None,
    "zank_pending_gui": None,
}

# ---------------------------------------------------------------------------
# Animation state constants
# ---------------------------------------------------------------------------
IDLE = "idle"
TALKING = "talking"
HAPPY = "happy"
SAD = "sad"
SLEEPY = "sleepy"
SURPRISED = "surprised"
DISMISSING = "dismissing"

# ---------------------------------------------------------------------------
# Zank pair table  (trigger -> (gui_line_key, overlay_line_key))
# ---------------------------------------------------------------------------
_ZANK_PAIRS: list[tuple[str, str, str]] = [
    # (trigger_key, gui_key, overlay_key)
    ("achievement", "zank_gui_predicted",    "zank_ov_saw_it"),
    ("game_over",   "zank_gui_no_talk",      "zank_ov_happens"),
    ("challenge_win", "zank_gui_training",   "zank_ov_cheering"),
    ("challenge_lose", "zank_gui_stats",     "zank_ov_not_my_fault"),
    ("idle_30m",    "zank_gui_come_back",    "zank_ov_left_us"),
    ("heat_100",    "zank_gui_calculated",   "zank_ov_told_them"),
    ("level_up",    "zank_gui_guidance",     "zank_ov_witnessed"),
    ("session_5h",  "zank_gui_hydration",    "zank_ov_legend"),
    ("christmas",   "zank_gui_family",       "zank_ov_xmas"),
]

_ZANK_GUI_LINES: dict[str, str] = {
    "zank_gui_predicted":  "I predicted that!",
    "zank_gui_no_talk":    "We do not talk about this...",
    "zank_gui_training":   "I knew you could do it! My training worked!",
    "zank_gui_stats":      "Statistically this was likely...",
    "zank_gui_come_back":  "Where did you go? Come back!",
    "zank_gui_calculated": "I calculated this would happen!",
    "zank_gui_guidance":   "My guidance paid off!",
    "zank_gui_hydration":  "Hydration reminder #47...",
    "zank_gui_family":     "Statistically you should be with family...",
}

_ZANK_OVERLAY_LINES: dict[str, str] = {
    "zank_ov_saw_it":      "I SAW IT HAPPEN! I was there!",
    "zank_ov_happens":     "It happens to everyone! ...right?",
    "zank_ov_cheering":    "MY cheering definitely helped!",
    "zank_ov_not_my_fault": "NOT MY FAULT!",
    "zank_ov_left_us":     "...they left us both!",
    "zank_ov_told_them":   "I TOLD THEM! Nobody listens!",
    "zank_ov_witnessed":   "I WITNESSED HISTORY!",
    "zank_ov_legend":      "LEGEND STATUS ACHIEVED!",
    "zank_ov_xmas":        "CHRISTMAS PINBALL! NO REGRETS!",
}

# ---------------------------------------------------------------------------
# GUI Trophie tips
# ---------------------------------------------------------------------------
_GUI_TIPS: dict[str, list[tuple[str, str]]] = {
    # (key, text)
    "tab_dashboard": [
        ("dash_notif",  "Check the notification feed — it shows everything that happened last game!"),
        ("dash_restart","You can restart the watcher engine here if something seems stuck."),
    ],
    "tab_effects": [
        ("eff_lowperf",  "Too many effects active? Enable Low Performance Mode to save CPU!"),
        ("eff_bloom_scan","Bloom + Scanlines together = perfect arcade look!"),
        ("eff_opengl",   "Post-Processing effects require OpenGL to look their best!"),
        ("eff_grain",    "Film Grain + Scanlines = retro CRT monitor feeling!"),
    ],
    "tab_appearance": [
        ("app_synthwave","Try the Synthwave theme — it looks amazing with Bloom enabled!"),
        ("app_place",    "You can position each overlay independently — try the Place buttons!"),
        ("app_portrait", "Portrait mode rotates the overlay for cabinet screens!"),
    ],
    "tab_controls": [
        ("ctrl_joy",     "You can bind a joystick button instead of keyboard to toggle the overlay!"),
        ("ctrl_hotkey",  None),  # dynamic tip — built at runtime
    ],
    "tab_progress": [
        ("prog_tab",     "The Progress tab shows how close you are to every achievement!"),
        ("prog_click",   "Click any achievement to see its unlock rules!"),
    ],
    "tab_cloud": [
        ("cloud_backup", "Back up your achievements to the cloud — do not lose your progress!"),
        ("cloud_id",     "Your Player ID is your identity. Write it down somewhere safe!"),
    ],
    "tab_system": [
        ("sys_nvram",    "Use Force Cache NVRAM Maps if a new table is not being tracked!"),
        ("sys_name",     "You can change your display name here — it shows on the cloud leaderboard!"),
    ],
}

_GUI_EVENT_TIPS: list[tuple[str, str]] = [
    ("evt_first_ach",    "Your first achievement! The hunt begins!"),
    ("evt_ach_unlocked", "Achievement unlocked! You are on your way!"),
    ("evt_lowperf_on",   "Good call! Low Performance Mode saves a lot of CPU."),
    ("evt_new_theme",    "Nice theme choice! Try enabling Bloom for the full effect!"),
    ("evt_postproc_on",  "Post-Processing is on! Looks amazing, right?"),
    ("evt_bloom_grain",  "Careful — Bloom + Film Grain together can be heavy on older PCs!"),
    ("evt_cloud_on",     "Cloud Sync is on! Your achievements are safe now."),
]

_GUI_IDLE_TIPS: list[tuple[str, str]] = [
    ("idle_5m",  "Still there? I am here if you need help!"),
    ("idle_10m", "ZZZ..."),  # enters SLEEPY
]

_GUI_RANDOM: list[tuple[str, str]] = [
    ("rnd_track",    "Did you know? I track everything you do... in a good way!"),
    ("rnd_believe",  "I believe in you. Just saying."),
    ("rnd_art",      "Achievement hunting is an art form. You are an artist!"),
    ("rnd_great",    "Between us? You are doing great!"),
    ("rnd_pixels",   "Fun fact: I am made of pixels but I feel real emotions!"),
    ("rnd_watch",    "I do not sleep. I just watch. Always watching."),
    ("rnd_luck",     "Some say pinball is luck. Those people have not seen you!"),
]

_GUI_ZANK: list[tuple[str, str]] = [
    ("z_gui_weird",   "My outdoor colleague just said something weird again..."),
    ("z_gui_smart",   "Do not listen to the other me. I am the smart one!"),
    ("z_gui_filter",  "The overlay version of me has NO filter. Sorry about that!"),
    ("z_gui_toomuch", "Between us? The other Trophie talks WAY too much!"),
    ("z_gui_unprof",  "My outside version just said something unprofessional. Embarrassing!"),
    ("z_gui_moving",  "We do not talk about the other Trophie. Moving on!"),
    ("z_gui_real",    "I do the REAL work here. The other one just watches!"),
    ("z_gui_twin",    "My twin thinks it is funny. It is not. I am the serious one!"),
    ("z_gui_first",   "I told you before the other one did. Just saying!"),
]

# ---------------------------------------------------------------------------
# Overlay Trophie comments
# ---------------------------------------------------------------------------
_OV_ROM_START: list[tuple[str, str]] = [
    ("ov_go",          "Let's go! Good luck!"),
    ("ov_classic",     None),  # dynamic: "Oh! {table_name}! Classic!"
    ("ov_firsttime",   "First time on this table! Good luck!"),
    ("ov_longago",     "Haven't seen this one in a while!"),
    ("ov_fav",         "Your favourite again? No complaints!"),
    ("ov_revenge",     "Back for more revenge? I respect that!"),
    ("ov_dustoff",     "Long time no see! Dust off those flippers!"),
    ("ov_thirdtoday",  "Third table today! You are on a roll!"),
    ("ov_firstday",    "First game of the day! Let's make it count!"),
    ("ov_onemore",     "One more game? That is the spirit!"),
    ("ov_morning",     "Morning warm-up! Coffee + pinball!"),
    ("ov_evening",     "Evening session! The best time to play!"),
    ("ov_nightowl",    "Night owl mode activated!"),
    ("ov_monday",      "Monday motivation: pinball!"),
    ("ov_weekend",     "Weekend pinball! No alarms tomorrow!"),
]

_OV_SESSION_END: list[tuple[str, str]] = [
    ("ov_good_game",   "Good game! See you next round"),
    ("ov_got_one",     "NICE! You got one!"),
    ("ov_double",      "Double unlock! Efficient!"),
    ("ov_avalanche",   "Achievement AVALANCHE! How?!"),
    ("ov_levelup",     "LEVEL UP! You are on fire!"),
    ("ov_almostach",   "Not every game needs a trophy. Almost!"),
    ("ov_shortsweet",  "Short but sweet! Every game counts!"),
    ("ov_2h",          "2 hours in... You okay?"),
    ("ov_3h",          "3 hours?! You are a machine!"),
    ("ov_5h",          "5 hours... Please drink some water!"),
    ("ov_drought_over","FINALLY! The drought is over!"),
    ("ov_rare_ach",    "That one is RARE! Show it off!"),
    ("ov_grind",       "Long session, no achievements... The grind is real!"),
    ("ov_tilt",        "Tilt? Or just bad luck?"),
    ("ov_first_blood", "First blood! The hunt is on!"),
    ("ov_5today",      "5 achievements today! Beast mode!"),
    ("ov_dry_spell",   "Dry spell... but legends never quit!"),
    ("ov_midnight",    "Midnight finish! Legendary!"),
]

_OV_CHALLENGE: list[tuple[str, str]] = [
    ("ov_ch_accepted",   "Challenge accepted! Do not choke!"),
    ("ov_ch_clock",      "Clock is ticking! FOCUS!"),
    ("ov_ch_10s",        "10 SECONDS! GIVE IT EVERYTHING!"),
    ("ov_ch_win",        "YOU WIN! I knew you could do it!"),
    ("ov_ch_close",      "So close... Try again!"),
    ("ov_ch_heartattack","THAT WAS CLOSE! Heart attack!"),
    ("ov_ch_dominant",   "Dominant performance!"),
    ("ov_ch_third",      "Third time is the charm... right?"),
    ("ov_ch_notmyfault", "NOT MY FAULT!"),
    ("ov_ch_record",     "NEW CHALLENGE RECORD! History made!"),
    ("ov_ch_back",       "Back in the challenge ring!"),
    ("ov_ch_5today",     "5 challenges today! Competitor of the year!"),
    ("ov_ch_morning",    "Morning challenge! Warm those fingers up!"),
    ("ov_ch_1sec",       "1 second away... I felt that"),
]

_OV_HEAT: list[tuple[str, str]] = [
    ("ov_heat_65",    "Getting warm! Ease up a little!"),
    ("ov_heat_85",    "CRITICAL HEAT! Your flippers are burning!"),
    ("ov_heat_100",   "TOO HOT! Give those flippers a rest!"),
    ("ov_heat_cool",  "Cooling down... smart move!"),
    ("ov_heat_zone",  "Steady pace! You are in the zone!"),
]

_OV_FLIP: list[tuple[str, str]] = [
    ("ov_flip_start",  "Flip counter active! Every flip counts!"),
    ("ov_flip_25",     "Quarter way there! Warm up done!"),
    ("ov_flip_50",     "Halfway there! Keep flipping!"),
    ("ov_flip_75",     "75%! Almost there! Do not slow down!"),
    ("ov_flip_90",     "Almost at your goal! Do not stop now!"),
    ("ov_flip_over",   "You SMASHED your goal! Overachiever!"),
    ("ov_flip_goal",   "GOAL! You hit your flip target!"),
]

_OV_IDLE: list[tuple[str, str]] = [
    ("ov_idle_5m",   "Still here... waiting..."),
    ("ov_idle_10m",  "Psst. VPX won't start itself!"),
    ("ov_idle_15m",  "I could really go for a game right now..."),
    ("ov_idle_20m",  "The tables miss you. True story."),
    ("ov_idle_45m",  "At this point I am basically furniture"),
    ("ov_idle_1h",   "One hour idle... Are you okay out there?"),
    ("ov_idle_zzz",  "ZZZ..."),  # SLEEPY state
    ("ov_idle_late", "Go to sleep. The achievements will be here tomorrow!"),
    ("ov_idle_morn", "Good morning! Ready for some pinball?"),
    ("ov_idle_wknd", "It is the weekend and you are NOT playing?!"),
]

_OV_DAYTIME: list[tuple[str, str]] = [
    ("ov_day_mon",  "Monday? Best day for pinball!"),
    ("ov_day_tue",  "Tuesday grind! Underrated pinball day!"),
    ("ov_day_wed",  "Midweek energy! Keep it up!"),
    ("ov_day_thu",  "Thursday already?! Time flies when you are flipping!"),
    ("ov_day_fri",  "Friday night pinball! The best kind!"),
    ("ov_day_sat",  "Perfect Saturday afternoon!"),
    ("ov_day_sun",  "Sunday session! One more before Monday!"),
    ("ov_day_ny",   "Happy New Year! First achievement of the year?"),
    ("ov_day_xmas", "Playing on Christmas?! Dedicated!"),
    ("ov_day_hal",  "Spooky session! BOO!"),
    ("ov_day_3am",  "3am pinball?! Legendary dedication!"),
    ("ov_day_hist", "This session is going in the history books!"),
    ("ov_day_new_month", "New month, new achievements!"),
    ("ov_day_nye",  "Last game of the year? Make it count!"),
]

_OV_RANDOM: list[tuple[str, str]] = [
    ("ov_rnd_pixels",  "Fun fact: I am made of pixels but I feel real emotions!"),
    ("ov_rnd_art",     "Achievement hunting is an art form. You are an artist!"),
    ("ov_rnd_count",   "I have been counting your achievements. Impressive!"),
    ("ov_rnd_best",    "Between us? You are one of the best I have seen!"),
    ("ov_rnd_1000",    "Did you know VPX has over 1000 tables? Try them all!"),
    ("ov_rnd_watch",   "I do not sleep. I just watch. Always watching."),
    ("ov_rnd_luck",    "Some say pinball is luck. Those people have not seen you!"),
    ("ov_rnd_mascot",  "Achievement unlocked: Having an awesome mascot!"),
    ("ov_rnd_boo",     "...boo. Did I scare you?"),
    ("ov_rnd_flippers","If I had flippers I would be amazing at this game. Just saying!"),
    ("ov_rnd_silence", "I am still here by the way"),
    ("ov_rnd_cheat",   "Are you cheating? ...I am not judging"),
    ("ov_rnd_1871",    "Fun fact: The first pinball machine was built in 1871!"),
    ("ov_rnd_believe", "I believe in you. Just saying."),
    ("ov_rnd_combo",   "VPX + achievements = perfect combo"),
    ("ov_rnd_score",   "You know I can see your score right?"),
]

_OV_ZANK: list[tuple[str, str]] = [
    ("z_ov_indoor",    "The indoor me is giving you tips again huh? Classic!"),
    ("z_ov_twin",      "My GUI twin thinks it knows everything. Adorable!"),
    ("z_ov_funone",    "I am the fun one. The other Trophie is just... there!"),
    ("z_ov_better",    "Do not tell my indoor clone but... I am the better looking one!"),
    ("z_ov_lecture",   "The other me is probably lecturing you about settings right now!"),
    ("z_ov_boring",    "My twin is SO boring. Tips tips tips! I do the real action!"),
    ("z_ov_novideo",   "Between us? GUI Trophie has never seen a real game!"),
    ("z_ov_famous",    "I live on the DESKTOP. I am basically famous!"),
    ("z_ov_woke",      "My indoor version just woke up to say hello. Took long enough!"),
    ("z_ov_congrat",   "Did the indoor Trophie congratulate you? I did it first!"),
]


# ---------------------------------------------------------------------------
# _TrophieMemory — KI learning, persisted to trophie_memory.json
# ---------------------------------------------------------------------------
class _TrophieMemory:
    """Persistent learning memory shared by both Trophie instances."""

    _FILENAME = "trophie_memory.json"

    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, self._FILENAME)
        self.seen_tips: set = set()
        self.tab_visits: dict = {}
        self.play_times: list = []
        self.session_durations: list = []
        self.achievement_sessions: int = 0
        self.no_achievement_sessions: int = 0
        self.challenge_wins: int = 0
        self.challenge_losses: int = 0
        self.heat_100_count: int = 0
        self.rom_play_counts: dict = {}
        self.dismiss_speed: list = []
        self.comments_shown: int = 0
        self.comments_dismissed_fast: int = 0
        self._fast_dismiss_streak: int = 0
        self._told_quiet: bool = False
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.seen_tips = set(d.get("seen_tips", []))
            self.tab_visits = d.get("tab_visits", {})
            self.play_times = d.get("play_times", [])
            self.session_durations = d.get("session_durations", [])
            self.achievement_sessions = int(d.get("achievement_sessions", 0))
            self.no_achievement_sessions = int(d.get("no_achievement_sessions", 0))
            self.challenge_wins = int(d.get("challenge_wins", 0))
            self.challenge_losses = int(d.get("challenge_losses", 0))
            self.heat_100_count = int(d.get("heat_100_count", 0))
            self.rom_play_counts = d.get("rom_play_counts", {})
            self.dismiss_speed = d.get("dismiss_speed", [])
            self.comments_shown = int(d.get("comments_shown", 0))
            self.comments_dismissed_fast = int(d.get("comments_dismissed_fast", 0))
            self._told_quiet = bool(d.get("_told_quiet", False))
        except Exception:
            pass

    def save(self) -> None:
        try:
            d = {
                "seen_tips": list(self.seen_tips),
                "tab_visits": self.tab_visits,
                "play_times": self.play_times[-200:],
                "session_durations": self.session_durations[-200:],
                "achievement_sessions": self.achievement_sessions,
                "no_achievement_sessions": self.no_achievement_sessions,
                "challenge_wins": self.challenge_wins,
                "challenge_losses": self.challenge_losses,
                "heat_100_count": self.heat_100_count,
                "rom_play_counts": self.rom_play_counts,
                "dismiss_speed": self.dismiss_speed[-200:],
                "comments_shown": self.comments_shown,
                "comments_dismissed_fast": self.comments_dismissed_fast,
                "_told_quiet": self._told_quiet,
            }
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            pass

    # ── KI queries ───────────────────────────────────────────────────────────

    def prefers_night(self) -> bool:
        if len(self.play_times) < 5:
            return False
        night = sum(1 for h in self.play_times if h >= 21 or h < 5)
        return night / len(self.play_times) > 0.4

    def avg_session_minutes(self) -> float:
        if not self.session_durations:
            return 30.0
        return sum(self.session_durations) / len(self.session_durations)

    def is_challenge_fan(self) -> bool:
        return (self.challenge_wins + self.challenge_losses) > 10

    def dismisses_quickly(self) -> bool:
        if len(self.dismiss_speed) < 5:
            return False
        fast = sum(1 for ms in self.dismiss_speed[-10:] if ms < 1500)
        return fast >= 5

    def favourite_rom(self) -> Optional[str]:
        if not self.rom_play_counts:
            return None
        return max(self.rom_play_counts, key=lambda r: self.rom_play_counts[r])

    # ── Tip rotation ─────────────────────────────────────────────────────────

    def pick_unseen(self, tips: list[tuple[str, str]]) -> Optional[tuple[str, str]]:
        """Return an unseen tip from the list; resets rotation when all seen."""
        keys = [k for k, _ in tips]
        unseen = [t for t in tips if t[0] not in self.seen_tips]
        if not unseen:
            # All seen — reset and start over
            for k in keys:
                self.seen_tips.discard(k)
            unseen = list(tips)
        if not unseen:
            return None
        chosen = random.choice(unseen)
        self.seen_tips.add(chosen[0])
        return chosen

    # ── Dismiss tracking ─────────────────────────────────────────────────────

    def record_dismiss(self, ms: int) -> Optional[str]:
        """Record a dismissal; returns special message if 3 fast in a row."""
        self.dismiss_speed.append(ms)
        self.comments_shown += 1
        if ms < 1500:
            self.comments_dismissed_fast += 1
            self._fast_dismiss_streak += 1
        else:
            self._fast_dismiss_streak = 0
        if self._fast_dismiss_streak >= 3 and not self._told_quiet:
            self._told_quiet = True
            return "I will be quieter!"
        return None

    def comment_frequency_multiplier(self) -> float:
        if self.dismisses_quickly():
            return 0.5
        return 1.0


# ---------------------------------------------------------------------------
# Speech Bubble widget
# ---------------------------------------------------------------------------
class _SpeechBubble(QWidget):
    """Floating speech bubble that auto-dismisses after 4 seconds."""

    _AUTO_DISMISS_MS = 4000
    _FADE_MS = 300
    _BG = QColor("#1A1A1A")
    _BORDER = QColor("#FF7F00")
    _TEXT_COLOR = QColor("#FFFFFF")
    _MAX_W = 240
    _PAD = 12
    _RADIUS = 10
    _PTR_H = 10

    def __init__(self, parent: QWidget, text: str, memory: _TrophieMemory) -> None:
        super().__init__(parent)
        self._memory = memory
        self._text = text
        self._opacity = 0.0
        self._shown_at_ms = int(time.time() * 1000)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)

        # Measure required size
        font = QFont("Segoe UI", 9)
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(
            QRect(0, 0, self._MAX_W - self._PAD * 2, 10000),
            Qt.TextFlag.TextWordWrap,
            text,
        )
        bw = max(120, text_rect.width() + self._PAD * 2 + 30)  # +30 for close button
        bh = text_rect.height() + self._PAD * 2 + self._PTR_H
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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show()

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
        if msg:
            # Schedule a brief "quiet" message on parent Trophie after dismissal
            try:
                self.parent()._schedule_quiet_msg(msg)
            except Exception:
                pass
        self.hide()
        self.deleteLater()

    def mousePressEvent(self, event) -> None:
        self._auto_timer.stop()
        self._begin_fade_out()

    def paintEvent(self, event) -> None:
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
        cx = w // 2
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

    def __init__(self, parent: QWidget, trophy_w: int, trophy_h: int) -> None:
        super().__init__(parent)
        self._tw = trophy_w
        self._th = trophy_h
        self.setFixedSize(trophy_w, trophy_h)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Animation state
        self._state = IDLE
        self._bob_t = 0.0          # time for sine bob (radians)
        self._bob_y = 0.0          # current vertical offset from bob
        self._scale = 1.0          # for grow/shrink animations
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

        # Main animation tick
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(16)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

        # Jump animation
        self._jump_offset = 0.0
        self._jump_vel = 0.0
        self._jumping = False

        # Dismiss animation
        self._dismiss_cb = None

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

    def _tick(self) -> None:
        dt = 0.016  # ~16ms
        speed = 0.4 if self._state == SLEEPY else 1.2
        self._bob_t += dt * speed

        if self._state == DISMISSING:
            self._scale = max(0.0, self._scale - 0.04)
            self._opacity_val = max(0.0, self._opacity_val - 0.04)
            if self._scale <= 0.0 or self._opacity_val <= 0.0:
                self._tick_timer.stop()
                if self._dismiss_cb:
                    self._dismiss_cb()
                return
        elif self._state in (HAPPY, SURPRISED):
            if self._jumping:
                self._jump_offset += self._jump_vel * dt * 60
                self._jump_vel += 0.5  # gravity
                if self._jump_offset >= 0.0:
                    self._jump_offset = 0.0
                    self._jumping = False
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

    def start_dismiss(self, callback=None) -> None:
        self._dismiss_cb = callback
        self.set_state(DISMISSING)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity_val)

        bob = math.sin(self._bob_t) * 3.0
        jump = self._jump_offset if self._jumping else 0.0
        total_offset = bob + jump

        cx = self._tw // 2
        cy = self._th // 2 + int(total_offset)

        p.save()
        # Scale around center for dismiss shrink
        if self._scale != 1.0:
            p.translate(cx, cy)
            p.scale(self._scale, self._scale)
            p.translate(-cx, -cy)

        self._draw_trophy(p, cx, cy)
        p.restore()
        p.end()

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


# ---------------------------------------------------------------------------
# GUI Trophie
# ---------------------------------------------------------------------------
class GUITrophie(QWidget):
    """Trophie mascot that lives in the bottom-left corner of the main window."""

    _TROPHY_W = 60
    _TROPHY_H = 70
    _MARGIN = 8

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

        # Draw widget
        self._draw = _TrophieDrawWidget(self, self._TROPHY_W, self._TROPHY_H)
        self._draw.move(0, 0)

        self.setFixedSize(self._TROPHY_W, self._TROPHY_H)
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

    def set_memory(self, mem: _TrophieMemory) -> None:
        self._memory = mem

    def greet(self) -> None:
        if self._greeted:
            return
        self._greeted = True
        self._draw.set_state(HAPPY)
        self._show_comment("Hey! I am Trophie! Welcome back!", HAPPY)

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

    def _fire_tab_tip(self, tab_name: str) -> None:
        tab_map = {
            "dashboard": "tab_dashboard",
            "effects":   "tab_effects",
            "appearance":"tab_appearance",
            "controls":  "tab_controls",
            "progress":  "tab_progress",
            "cloud":     "tab_cloud",
            "system":    "tab_system",
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
                from input_hook import vk_to_name_en
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
        base_ms = random.randint(8 * 60_000, 15 * 60_000)
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
                gui_text = _ZANK_GUI_LINES.get(gui_key, "")
                ov_text = _ZANK_OVERLAY_LINES.get(ov_key, "")
                if gui_text:
                    self._show_comment(gui_text, TALKING)
                # Signal overlay to respond in 2 seconds
                _TROPHIE_SHARED["zank_pending_overlay"] = ov_key
                _TROPHIE_SHARED["zank_cooldown_ms"] = 15 * 60 * 1000
                return True
        return False

    def _zank_tick_fn(self) -> None:
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            _TROPHIE_SHARED["zank_cooldown_ms"] = max(0, _TROPHIE_SHARED["zank_cooldown_ms"] - 1000)
        # Check if overlay posted a pending gui zank response
        pending = _TROPHIE_SHARED.get("zank_pending_gui")
        if pending:
            _TROPHIE_SHARED["zank_pending_gui"] = None
            text = _ZANK_GUI_LINES.get(pending, "")
            if text:
                self._show_comment(text, TALKING)

    def _is_silenced(self) -> bool:
        return time.time() < self._silenced_until

    def _show_comment(self, text: str, state: str = TALKING) -> None:
        if self._is_silenced():
            return
        self._dismiss_bubble()
        self._draw.set_state(state)
        bubble = _SpeechBubble(self._central, text, self._memory or _TrophieMemory.__new__(_TrophieMemory))
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
            # Place bubble above the trophy
            bx = max(0, self.x() + self._TROPHY_W // 2 - bw // 2)
            by = max(0, self.y() - bh - 4)
            # Clamp to central widget
            if bx + bw > self._central.width():
                bx = self._central.width() - bw - 4
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
        menu.addAction("Dismiss", self._dismiss_bubble)
        menu.addAction("Silence for 10 minutes", self._silence_10m)
        menu.exec(self.mapToGlobal(pos))

    def _silence_10m(self) -> None:
        self._silenced_until = time.time() + 600
        self._dismiss_bubble()

    def update_position(self, parent_size: QSize) -> None:
        x = self._MARGIN
        y = parent_size.height() - self._TROPHY_H - self._MARGIN
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
        self.setFixedSize(self._TROPHY_W, self._TROPHY_H)

        self._draw = _TrophieDrawWidget(self, self._TROPHY_W, self._TROPHY_H)
        self._draw.move(0, 0)

        # Drag support
        self._drag_start: Optional[QPoint] = None
        self._drag_pos_start: Optional[QPoint] = None

        self._restore_position()

        # Idle tracker
        self._last_game_ts = time.time()
        self._idle_shown: dict = {}

        # Heat tracking
        self._last_heat = 0
        self._heat_notified_65 = False
        self._heat_notified_85 = False
        self._heat_notified_100 = False
        self._heat_zone_timer_ms = 0

        # Flip tracking
        self._flip_prev_pct = 0.0
        self._flip_notified: dict = {}

        # Session tracking
        self._session_start: Optional[float] = None
        self._session_rom: Optional[str] = None
        self._session_ach_count = 0
        self._today_ach_count = 0
        self._today_session_count = 0
        self._challenge_count_today = 0
        self._challenge_losses_streak = 0
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

    def greet(self) -> None:
        if self._greeted:
            return
        self._greeted = True
        self._draw.set_state(HAPPY)
        self._show_comment("Hey! I am Trophie! Ready to watch your games!", HAPPY)

    # ── Session event handlers ────────────────────────────────────────────────

    def on_rom_start(self, rom: str, table_name: Optional[str] = None) -> None:
        self._session_start = time.time()
        self._session_rom = rom
        self._session_ach_count = 0
        self._today_session_count += 1
        self._last_game_ts = time.time()
        self._idle_shown.clear()

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
            self._show_comment_key(key or "ov_go", comment, HAPPY)

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
        self._draw.set_state(HAPPY)
        if self._try_zank("achievement"):
            return
        if self._today_ach_count == 1:
            self._show_comment_key("ov_first_blood", "First blood! The hunt is on!", HAPPY)
        elif self._today_ach_count >= 5:
            self._show_comment_key("ov_5today", "5 achievements today! Beast mode!", SURPRISED)
        else:
            self._show_comment_key("ov_got_one", "NICE! You got one!", HAPPY)

    def on_level_up(self) -> None:
        self._draw.set_state(HAPPY)
        self._try_zank("level_up")

    def on_challenge_start(self) -> None:
        self._challenge_count_today += 1
        self._last_game_ts = time.time()
        self._draw.set_state(HAPPY)
        now = datetime.now()
        if now.hour < 10:
            self._show_comment_key("ov_ch_morning", "Morning challenge! Warm those fingers up!", HAPPY)
        elif self._challenge_count_today >= 5:
            self._show_comment_key("ov_ch_5today", "5 challenges today! Competitor of the year!", SURPRISED)
        else:
            self._show_comment_key("ov_ch_accepted", "Challenge accepted! Do not choke!", HAPPY)

    def on_challenge_timer_tick(self, remaining_ms: int) -> None:
        if remaining_ms <= 3000 and remaining_ms > 2500:
            self._show_comment_key("ov_ch_clock", "Clock is ticking! FOCUS!", SURPRISED)
        elif remaining_ms <= 10000 and remaining_ms > 9500:
            self._show_comment_key("ov_ch_10s", "10 SECONDS! GIVE IT EVERYTHING!", SURPRISED)

    def on_challenge_stop(self) -> None:
        pass  # Session end will handle the result

    def on_challenge_won(self, margin_pct: float = 50.0) -> None:
        self._last_game_ts = time.time()
        self._challenge_losses_streak = 0
        if self._try_zank("challenge_win"):
            return
        if margin_pct < 5.0:
            self._show_comment_key("ov_ch_heartattack", "THAT WAS CLOSE! Heart attack!", SURPRISED)
        elif margin_pct > 50.0:
            self._show_comment_key("ov_ch_dominant", "Dominant performance!", HAPPY)
        else:
            self._show_comment_key("ov_ch_win", "YOU WIN! I knew you could do it!", HAPPY)

    def on_challenge_lost(self, attempts: int = 1, margin_pct: float = 10.0) -> None:
        self._last_game_ts = time.time()
        self._challenge_losses_streak += 1
        if self._try_zank("challenge_lose"):
            return
        if margin_pct < 2.0:
            self._show_comment_key("ov_ch_1sec", "1 second away... I felt that", SAD)
        elif attempts >= 3:
            self._show_comment_key("ov_ch_third", "Third time is the charm... right?", SAD)
        elif margin_pct < 10.0:
            self._show_comment_key("ov_ch_close", "So close... Try again!", SAD)
        else:
            self._show_comment_key("ov_ch_notmyfault", "NOT MY FAULT!", SAD)

    def on_heat_changed(self, heat_pct: int) -> None:
        self._last_game_ts = time.time()
        if heat_pct >= 100 and not self._heat_notified_100:
            self._heat_notified_100 = True
            self._try_zank("heat_100") or self._show_comment_key("ov_heat_100", "TOO HOT! Give those flippers a rest!", SURPRISED)
        elif heat_pct >= 85 and not self._heat_notified_85:
            self._heat_notified_85 = True
            self._show_comment_key("ov_heat_85", "CRITICAL HEAT! Your flippers are burning!", SURPRISED)
        elif heat_pct >= 65 and not self._heat_notified_65:
            self._heat_notified_65 = True
            self._show_comment_key("ov_heat_65", "Getting warm! Ease up a little!", IDLE)
        elif heat_pct < 80 and self._heat_notified_100:
            self._heat_notified_100 = False
            self._heat_notified_85 = False
            self._show_comment_key("ov_heat_cool", "Cooling down... smart move!", HAPPY)
        if heat_pct < 50:
            self._heat_notified_65 = False

    def on_flip_progress(self, current: int, goal: int) -> None:
        if goal <= 0:
            return
        pct = current / goal
        prev = self._flip_prev_pct
        self._flip_prev_pct = pct

        milestones = [(0.01, "ov_flip_start", "Flip counter active! Every flip counts!", IDLE),
                      (0.25,  "ov_flip_25",    "Quarter way there! Warm up done!", IDLE),
                      (0.50,  "ov_flip_50",    "Halfway there! Keep flipping!", IDLE),
                      (0.75,  "ov_flip_75",    "75%! Almost there! Do not slow down!", HAPPY),
                      (0.90,  "ov_flip_90",    "Almost at your goal! Do not stop now!", HAPPY),
                      (1.00,  "ov_flip_goal",  "GOAL! You hit your flip target!", HAPPY),
                      (1.01,  "ov_flip_over",  "You SMASHED your goal! Overachiever!", SURPRISED)]
        for threshold, key, text, state in milestones:
            if prev < threshold <= pct and key not in self._flip_notified:
                self._flip_notified[key] = True
                self._show_comment_key(key, text, state)
                break

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
                break

        if elapsed_min < 5:
            self._idle_shown.clear()
            if self._draw._state == SLEEPY:
                self._draw.set_state(IDLE)

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
        base_ms = random.randint(8 * 60_000, 15 * 60_000)
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
                ov_text = _ZANK_OVERLAY_LINES.get(ov_key, "")
                # Schedule overlay response 2 seconds after gui fires
                QTimer.singleShot(2000, lambda t=ov_text, k=ov_key: self._show_comment_key(k, t, TALKING))
                # Signal GUI to show its line
                _TROPHIE_SHARED["zank_pending_gui"] = gui_key
                _TROPHIE_SHARED["zank_cooldown_ms"] = 15 * 60 * 1000
                return True
        return False

    def _zank_tick_fn(self) -> None:
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            _TROPHIE_SHARED["zank_cooldown_ms"] = max(0, _TROPHIE_SHARED["zank_cooldown_ms"] - 1000)
        pending = _TROPHIE_SHARED.get("zank_pending_overlay")
        if pending:
            _TROPHIE_SHARED["zank_pending_overlay"] = None
            text = _ZANK_OVERLAY_LINES.get(pending, "")
            if text:
                QTimer.singleShot(2000, lambda t=text, k=pending: self._show_comment_key(k, t, TALKING))

    def _days_since_last_played(self, rom: str) -> Optional[int]:
        # Simple: we don't track dates directly — use play_count heuristic
        return None  # Placeholder; extend with timestamp tracking if needed

    # ── UI ───────────────────────────────────────────────────────────────────

    def _is_silenced(self) -> bool:
        return time.time() < self._silenced_until

    def _show_comment(self, text: str, state: str = TALKING) -> None:
        if self._is_silenced():
            return
        self._dismiss_bubble()
        self._draw.set_state(state)
        # Bubble is a child of THIS widget so it floats above it
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
        bubble = _SpeechBubble(self, text, mem)
        self._current_bubble = bubble
        self._position_bubble(bubble)

    def _show_comment_key(self, key: str, text: str, state: str = TALKING) -> None:
        if self._memory:
            self._memory.seen_tips.add(key)
        self._show_comment(text, state)

    def _position_bubble(self, bubble: _SpeechBubble) -> None:
        try:
            bw = bubble.width()
            bh = bubble.height()
            # Place bubble above the trophy widget
            bx = self._TROPHY_W // 2 - bw // 2
            by = -bh - 4
            # Clamp to screen
            screen_geom = QApplication.primaryScreen().geometry()
            abs_x = self.x() + bx
            abs_y = self.y() + by
            if abs_x < 0:
                bx -= abs_x
            if abs_y < 0:
                by = self._TROPHY_H + 4  # flip below
            if abs_x + bw > screen_geom.width():
                bx -= (abs_x + bw - screen_geom.width())
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
            screen = QApplication.primaryScreen().geometry()
            self.move(self._MARGIN, screen.height() - self._TROPHY_H - self._MARGIN)
        except Exception:
            self.move(self._MARGIN, 600)

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("Dismiss comment", self._dismiss_bubble)
        menu.addAction("Silence for 10 minutes", self._silence_10m)
        move_menu = menu.addMenu("Move to corner...")
        move_menu.addAction("Bottom Left",  lambda: self._move_to_corner("bl"))
        move_menu.addAction("Bottom Right", lambda: self._move_to_corner("br"))
        move_menu.addAction("Top Left",     lambda: self._move_to_corner("tl"))
        move_menu.addAction("Top Right",    lambda: self._move_to_corner("tr"))
        menu.exec(self.mapToGlobal(pos))

    def _silence_10m(self) -> None:
        self._silenced_until = time.time() + 600
        self._dismiss_bubble()

    def _move_to_corner(self, corner: str) -> None:
        try:
            screen = QApplication.primaryScreen().geometry()
            sw, sh = screen.width(), screen.height()
            m = self._MARGIN
            positions = {
                "bl": (m, sh - self._TROPHY_H - m),
                "br": (sw - self._TROPHY_W - m, sh - self._TROPHY_H - m),
                "tl": (m, m),
                "tr": (sw - self._TROPHY_W - m, m),
            }
            self.move(*positions.get(corner, (m, sh - self._TROPHY_H - m)))
            self._save_position()
        except Exception:
            pass
