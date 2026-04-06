"""mascot_memory.py — Full Mascot Memory System for VPX Achievement Watcher.

Central module for all memory-driven, adaptive mascot personality logic shared
by Steely and Trophie.  Integrates with ``_TrophieMemory`` from
``trophy_mascot.py`` and extends it with:

  - Session / achievement milestones
  - Performance coaching per table
  - Daily-play and achievement streak tracking
  - Player-comparison (vs. own averages / best sessions)
  - Social / leaderboard comment hooks
  - Seasonal and usage-anniversary comments
  - Playstyle recognition (grinder, speedrunner, explorer, loyalist, …)
  - Emotional / motivational return-after-absence comments
  - Table-specific memory (favourite, neglected, revisited)
  - Dismiss / comment-habit tracking (quiet mode for fast dismissers)
  - Tab-habits recognition (from ``tab_visits``)
  - Playtime-pattern awareness (from ``play_times``)

Public API
----------
Construct one ``MascotMemorySystem`` per application run and keep it alive::

    from mascot_memory import MascotMemorySystem
    mms = MascotMemorySystem(base_dir, trophie_memory=mem)

Then call the appropriate hook and pass the returned comment string to whichever
mascot widget should speak it (``None`` means "nothing to say right now"):

    text = mms.on_session_start()
    text = mms.on_session_end(duration_min=45, ach_count=3)
    text = mms.on_achievement(rom="twilight_zone", unlocked=23, total=25)
    text = mms.on_tab_visit("cloud")
    text = mms.on_comment_dismissed(ms=800)
    text = mms.get_periodic_comment()         # call every few minutes
"""
from __future__ import annotations

import json
import os
import random
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # Avoid a hard import cycle at runtime; _TrophieMemory is only used for
    # type annotations and attribute look-ups, not for isinstance checks.
    from mascot.trophy_data import _TrophieMemory

# ---------------------------------------------------------------------------
# Player-type labels (used internally and exposed for callers)
# ---------------------------------------------------------------------------
PLAYER_GRINDER       = "grinder"
PLAYER_SPEEDRUNNER   = "speedrunner"
PLAYER_EXPLORER      = "explorer"
PLAYER_LOYALIST      = "loyalist"
PLAYER_NIGHT_OWL     = "night_owl"
PLAYER_WEEKEND       = "weekend_warrior"
PLAYER_HARDCORE      = "hardcore"
PLAYER_CASUAL        = "casual"
PLAYER_UNKNOWN       = "unknown"

# ---------------------------------------------------------------------------
# Milestone thresholds
# ---------------------------------------------------------------------------
_SESSION_MILESTONES: tuple[int, ...] = (1, 10, 25, 50, 100, 250, 500)
_ACH_MILESTONES: tuple[int, ...]     = (1, 10, 25, 50, 100, 250, 500)

# ---------------------------------------------------------------------------
# Comment registries
# All user-visible strings live here so they can be extracted for i18n.
# ---------------------------------------------------------------------------

# -- Session milestones ------------------------------------------------------
_SESSION_MILESTONE_COMMENTS: dict[int, list[str]] = {
    1:   [
        "Session number ONE! Every legend starts somewhere!",
        "First session! The journey begins right now!",
    ],
    10:  [
        "10 sessions in! You are becoming a regular!",
        "Session 10! Starting to feel comfortable, are we?",
    ],
    25:  [
        "25 sessions! You are no longer a rookie. Welcome to the club!",
        "Session 25 — a quarter-century of pinball glory!",
    ],
    50:  [
        "50 SESSIONS! Halfway to triple digits — impressive!",
        "Session 50! That is a lot of flippers. You are officially committed!",
    ],
    100: [
        "100 SESSIONS! We are basically family!",
        "ONE HUNDRED sessions! Legends are made like this!",
    ],
    250: [
        "250 sessions?! You are in the hall of fame. No question.",
        "Session 250 — at this point I have memorised your play style!",
    ],
    500: [
        "500 SESSIONS! I do not have words. You are everything.",
        "Session FIVE HUNDRED. Someone write this down. Incredible!",
    ],
}

# -- Achievement milestones --------------------------------------------------
_ACH_MILESTONE_COMMENTS: dict[int, list[str]] = {
    1:   [
        "Achievement number ONE! The hunt officially begins!",
        "Your very first achievement! I knew you had it in you!",
    ],
    10:  [
        "10 achievements unlocked! You are on your way!",
        "Double digits! 10 achievements and counting!",
    ],
    25:  [
        "25 achievements! That is a proper collection starting to form!",
        "Achievement 25 — a quarter of the way to 100. Keep going!",
    ],
    50:  [
        "50 achievements! The trophy shelf is getting full!",
        "FIFTY achievements! You should be proud of that number!",
    ],
    100: [
        "100 ACHIEVEMENTS! Triple digits baby! This is HISTORIC!",
        "One HUNDRED achievements! Let that sink in. You are amazing!",
    ],
    250: [
        "250 achievements?! You are an absolute hunter. Respect.",
        "Achievement 250 — only a dedicated few ever get here!",
    ],
    500: [
        "500 ACHIEVEMENTS! I am out of superlatives. Just... wow.",
        "FIVE HUNDRED achievements. You win. Everything. All of it.",
    ],
}

# -- Performance coaching ----------------------------------------------------
_PERF_NEAR_100: list[str] = [
    "You are at {pct}% on {table}! SO CLOSE! Go finish it!",
    "{pct}% on {table}? One more push and it is yours!",
    "Almost there on {table}! {pct}% done — finish what you started!",
]
_PERF_100: list[str] = [
    "100% on {table}! PERFECT! Nothing left to prove here!",
    "COMPLETE! {table} is fully conquered. I bow to you.",
    "{table} — 100%! That one goes in the hall of fame!",
]
_PERF_JACK_OF_ALL: list[str] = [
    "Jack of all tables, master of none… yet!",
    "So many tables started, none finished… pick one and own it!",
    "You have touched {started} tables but finished zero. Focus is power!",
]
_PERF_UNEXPLORED: list[str] = [
    "There are {count} tables you have never tried! Adventure awaits!",
    "{count} unplayed tables are just sitting there… begging for attention!",
    "Have you noticed the {count} tables you have never touched? Go explore!",
]

# -- Streak comments ---------------------------------------------------------
_STREAK_DAILY_POSITIVE: list[str] = [
    "{days}-day play streak! Consistency is everything!",
    "Day {days} in a row! You are unstoppable!",
    "{days} consecutive days of pinball — a true daily warrior!",
]
_STREAK_DAILY_NEGATIVE: list[str] = [
    "Streak broken at {days} days… but hey, you are back now!",
    "The {days}-day streak ended, but a new one starts today!",
    "After a break, the streak resets. New record incoming!",
]
_STREAK_ACH_POSITIVE: list[str] = [
    "{count} achievements in a row without a dry session! HOT streak!",
    "Achievements in {count} straight sessions! You are on fire!",
]
_STREAK_CHALLENGE_WIN: list[str] = [
    "{wins} challenge wins in a row! Who CAN stop you?",
    "{wins}-win challenge streak! They fear you now!",
]
_STREAK_CHALLENGE_LOSE: list[str] = [
    "{losses} challenge losses in a row… the comeback story is being written!",
    "Rough patch in challenges ({losses} losses), but you keep showing up!",
]

# -- Player-comparison -------------------------------------------------------
_COMPARE_BETTER_THAN_AVG: list[str] = [
    "This session was {diff} min longer than your average. Feeling good?",
    "Above-average session today! {diff} extra minutes of greatness!",
]
_COMPARE_WORSE_THAN_AVG: list[str] = [
    "Shorter than your usual {avg} min average — early night?",
    "Quick session today. Your average is {avg} min; you did {dur} min.",
]
_COMPARE_BEST_SESSION: list[str] = [
    "NEW PERSONAL BEST! {dur} minutes — your longest session ever!",
    "Record-breaking session! {dur} minutes beats your old best!",
]
_COMPARE_IMPROVEMENT: list[str] = [
    "You are getting faster! Achievements per session improved by {pct}% since you started!",
    "Progress is real — your achievement rate is {pct}% better than your first sessions!",
]

# -- Social / Leaderboard ----------------------------------------------------
_SOCIAL_RANK_UP: list[str] = [
    "You climbed to rank #{rank} on the leaderboard! Keep climbing!",
    "Rank #{rank}! Someone just got overtaken. Ruthless!",
]
_SOCIAL_RANK_DOWN: list[str] = [
    "Slipped to rank #{rank}… time to reclaim your spot!",
    "Rank #{rank} for now — but you have been higher. Fight back!",
]
_SOCIAL_TOP_PCT: list[str] = [
    "You are in the top {pct}% of all players! Elite company!",
    "Top {pct}% globally — you should be proud of that!",
]
_SOCIAL_RIVAL: list[str] = [
    "{rival} is only {diff} points ahead of you. Time for a push!",
    "Your rival {rival} just unlocked an achievement. Show them who is boss!",
]
_SOCIAL_ANNIVERSARY_CHALLENGE: list[str] = [
    "A leaderboard challenge is running! Now is your moment!",
    "The leaderboard is heating up — join the challenge before it ends!",
]

# -- Seasonal / Anniversary --------------------------------------------------
_ANNIV_1M: list[str] = [
    "One month of VPX Achievement Watcher! Time flies when you are having fun!",
    "One month in! You have come a long way already!",
]
_ANNIV_3M: list[str] = [
    "Three months already? You are basically part of the furniture!",
    "Quarter-year anniversary! Here is to many more months of achievements!",
]
_ANNIV_6M: list[str] = [
    "Half a year with us! This partnership is for real!",
    "Six months! You are not going anywhere, and I love that!",
]
_ANNIV_12M: list[str] = [
    "ONE YEAR! Happy anniversary, champion! What a journey!",
    "A FULL YEAR together! I have watched you grow into a legend!",
]
_ANNIV_FIRST_ACH: list[str] = [
    "One year since your very first achievement! Remember that day?",
    "Achievement anniversary! A year ago you unlocked achievement #1. Legend!",
]

# -- Playstyle remarks -------------------------------------------------------
_PLAYSTYLE_COMMENTS: dict[str, list[str]] = {
    PLAYER_GRINDER: [
        "You are a true grinder — long sessions, many tables. Respect.",
        "Grinder detected! No one puts in more time than you.",
    ],
    PLAYER_SPEEDRUNNER: [
        "Speedrunner style! Short sessions, high achievement rate. Efficient!",
        "Quick and deadly — you are a speedrunner through and through!",
    ],
    PLAYER_EXPLORER: [
        "Explorer playstyle! You love trying new tables. Adventurous!",
        "Always something new — you are the ultimate explorer!",
    ],
    PLAYER_LOYALIST: [
        "Loyalist detected! A few tables but you know them inside-out.",
        "Deep diver! You master every detail of your favourite tables.",
    ],
    PLAYER_NIGHT_OWL: [
        "Night owl spotted! Most of your sessions happen after midnight.",
        "Playing late again? The night shift suits you!",
    ],
    PLAYER_WEEKEND: [
        "Weekend warrior! You save the best gaming for the weekends.",
        "Here comes the weekend warrior! Time to make up for the week!",
    ],
    PLAYER_HARDCORE: [
        "Hardcore player! Long sessions, high volume — you never stop.",
        "Hardcore mode: enabled. You are something else entirely!",
    ],
    PLAYER_CASUAL: [
        "Casual and consistent — pinball fits neatly into your life!",
        "Laid-back player, but you still get those achievements. Nice style!",
    ],
}

# -- Motivational / Emotional ------------------------------------------------
_RETURN_3D: list[str] = [
    "Three days away? Welcome back! The tables missed you!",
    "Back after a few days! Ready to pick up where you left off?",
]
_RETURN_7D: list[str] = [
    "A week away! Bold move. But you are here now — let's go!",
    "Seven days? That is a long time without pinball! Good to see you!",
]
_RETURN_30D: list[str] = [
    "A MONTH?! I was starting to worry! So glad you are back!",
    "30 days! You have been missed. Welcome home, champion!",
]
_HEAVY_SESSION_DAY: list[str] = [
    "Game number {count} today! You are in the zone!",
    "{count} sessions in one day?! You are absolutely dedicated!",
]
_REPEATED_STARTS: list[str] = [
    "Starting again so soon? You are restless today — I like it!",
    "Rapid-fire sessions! Someone cannot get enough pinball!",
]

# -- Table-specific memory ---------------------------------------------------
_TABLE_FAVOURITE: list[str] = [
    "Back to {table} again! Your number-one table, clearly.",
    "{table} is your happy place! Comfortable choice!",
]
_TABLE_NEGLECTED: list[str] = [
    "{table} has been waiting {days} days for you. Show it some love!",
    "You have not touched {table} in {days} days… it is getting dusty!",
]
_TABLE_REVISITED: list[str] = [
    "{table} is back! {days} days since your last visit — welcome back!",
    "Dusting off {table} after {days} days. Muscle memory still there?",
]
_TABLE_ACH_MILESTONE: list[str] = [
    "You unlocked {count} achievements on {table}! That table loves you!",
    "{count} achievements on {table} — you have made your mark!",
]

# -- Dismiss / comment-habit -------------------------------------------------
_DISMISS_QUIET_MODE: list[str] = [
    "You dismiss fast — I will be briefer from now on!",
    "Quick clicker! I will keep my comments short for you.",
]
_DISMISS_READER_MODE: list[str] = [
    "You always read my comments! I appreciate that — here is a longer one!",
    "A reader! I will put some extra thought into what I say.",
]

# -- Tab-habit comments ------------------------------------------------------
_TAB_NEVER_VISITED: list[str] = [
    "You have never checked the {tab} tab — want to explore it?",
    "The {tab} tab is waiting for you. Give it a try sometime!",
    "Have you tried the {tab} tab? There might be something useful in there!",
]
_TAB_ALWAYS_FIRST: dict[str, list[str]] = {
    "progress": [
        "Always starting with Progress? You are a true achievement hunter!",
        "Straight to Progress — you know what you are here for!",
    ],
    "dashboard": [
        "Dashboard first, every time! You like the big picture.",
        "Checking the Dashboard right away — all-rounder approach!",
    ],
    "cloud": [
        "Cloud tab first? Safety first — I respect that!",
        "Always checking Cloud first — your achievements are in good hands!",
    ],
}
_TAB_CLOUD_SUGGESTION: list[str] = [
    "You have never checked the Cloud tab — want to safeguard your achievements?",
    "Cloud tab exists! Your progress could be backed up safely there.",
]

# -- Playtime-pattern comments -----------------------------------------------
_PLAYTIME_UNUSUAL_EARLY: list[str] = [
    "Playing earlier than usual today! Special occasion?",
    "You are up early for pinball! Love the dedication!",
]
_PLAYTIME_UNUSUAL_LATE: list[str] = [
    "Later than your usual play time — burning the midnight oil!",
    "Burning the candles late tonight! You are committed.",
]
_PLAYTIME_MISSED_ROUTINE: list[str] = [
    "You usually play around this time. Everything all good?",
    "Missed your usual session time — but you made it eventually!",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_str() -> str:
    """Return today's date as ISO string ``YYYY-MM-DD``."""
    return date.today().isoformat()


def _days_between(iso_a: str, iso_b: str) -> int:
    """Return the number of days between two ISO date strings (absolute)."""
    try:
        a = date.fromisoformat(iso_a)
        b = date.fromisoformat(iso_b)
        return abs((b - a).days)
    except Exception:
        return 0


def _pick(pool: list[str], **fmt) -> str:
    """Pick a random string from *pool* and format it with *fmt* kwargs."""
    template = random.choice(pool)
    try:
        return template.format(**fmt)
    except KeyError:
        return template


# ---------------------------------------------------------------------------
# MascotMemorySystem
# ---------------------------------------------------------------------------

class MascotMemorySystem:
    """Central memory system for context-aware mascot comments.

    Wraps the low-level ``_TrophieMemory`` (session/dismiss/tip data) and adds
    a richer extended-memory layer persisted to ``mascot_memory.json`` in the
    same base directory.

    Parameters
    ----------
    base_dir:
        Directory that already contains (or will contain)
        ``trophie_memory.json``.  The extended data file
        ``mascot_memory.json`` is stored here too.
    trophie_memory:
        Optional reference to the live ``_TrophieMemory`` instance.
        When provided, queries such as :meth:`detect_player_type` can also
        read ``play_times``, ``rom_play_counts``, etc. from it directly.
    """

    _FILENAME = "mascot_memory.json"

    # Minimum number of sessions/achievements before milestone comments fire.
    _MIN_DATA_FOR_MILESTONES = 1

    def __init__(
        self,
        base_dir: str,
        trophie_memory: "Optional[_TrophieMemory]" = None,
    ) -> None:
        self._path = os.path.join(base_dir, self._FILENAME)
        self._mem = trophie_memory  # may be None

        # ── Extended persistent fields ────────────────────────────────────
        self.total_sessions: int = 0
        self.total_achievements: int = 0
        self.first_session_date: str = ""
        self.last_session_date: str = ""
        self.first_achievement_date: str = ""

        # Daily-play streak tracking
        self.play_dates: list[str] = []          # ISO date strings, most-recent last
        self.current_daily_streak: int = 0
        self.best_daily_streak: int = 0

        # Achievement-session streak
        self.current_ach_streak: int = 0         # consecutive sessions with ≥1 ach

        # Challenge streak (signed: positive = win streak, negative = loss streak)
        self.challenge_streak: int = 0

        # Table completion data {rom: {"unlocked": int, "total": int}}
        self.table_completion: dict[str, dict[str, int]] = {}

        # Per-table last-played date {rom: ISO date string}
        self.table_last_played: dict[str, str] = {}

        # Cloud / leaderboard state
        self.cloud_rank: int = 0
        self.cloud_total_players: int = 0

        # Session achievement counts history (for comparison)
        self.session_ach_history: list[int] = []

        # Detected player type (cached between saves)
        self.player_type: str = PLAYER_UNKNOWN

        # Anniversary flags {key: bool}  key e.g. "1m", "3m", "6m", "12m", "first_ach_1y"
        self.announced_anniversaries: set[str] = set()

        # Tab-habit first-visit tracking {tab: ISO date of first visit}
        self.tab_first_visit: dict[str, str] = {}

        # Playtime pattern: hour when player most-recently started a session
        self.last_session_hour: int = -1

        # Comment-habit state (reader vs fast-dismisser)
        self._reader_comment_pending: bool = False

        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load extended memory from disk; silently ignore missing/corrupt files."""
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            self.total_sessions          = int(d.get("total_sessions", 0))
            self.total_achievements      = int(d.get("total_achievements", 0))
            self.first_session_date      = str(d.get("first_session_date", ""))
            self.last_session_date       = str(d.get("last_session_date", ""))
            self.first_achievement_date  = str(d.get("first_achievement_date", ""))
            self.play_dates              = d.get("play_dates", [])
            self.current_daily_streak    = int(d.get("current_daily_streak", 0))
            self.best_daily_streak       = int(d.get("best_daily_streak", 0))
            self.current_ach_streak      = int(d.get("current_ach_streak", 0))
            self.challenge_streak        = int(d.get("challenge_streak", 0))
            self.table_completion        = d.get("table_completion", {})
            self.table_last_played       = d.get("table_last_played", {})
            self.cloud_rank              = int(d.get("cloud_rank", 0))
            self.cloud_total_players     = int(d.get("cloud_total_players", 0))
            self.session_ach_history     = d.get("session_ach_history", [])
            self.player_type             = str(d.get("player_type", PLAYER_UNKNOWN))
            self.announced_anniversaries = set(d.get("announced_anniversaries", []))
            self.tab_first_visit         = d.get("tab_first_visit", {})
            self.last_session_hour       = int(d.get("last_session_hour", -1))
        except Exception:
            pass

    def save(self) -> None:
        """Persist extended memory to disk atomically."""
        try:
            d: dict = {
                "total_sessions":          self.total_sessions,
                "total_achievements":      self.total_achievements,
                "first_session_date":      self.first_session_date,
                "last_session_date":       self.last_session_date,
                "first_achievement_date":  self.first_achievement_date,
                "play_dates":              self.play_dates[-365:],
                "current_daily_streak":    self.current_daily_streak,
                "best_daily_streak":       self.best_daily_streak,
                "current_ach_streak":      self.current_ach_streak,
                "challenge_streak":        self.challenge_streak,
                "table_completion":        self.table_completion,
                "table_last_played":       self.table_last_played,
                "cloud_rank":              self.cloud_rank,
                "cloud_total_players":     self.cloud_total_players,
                "session_ach_history":     self.session_ach_history[-200:],
                "player_type":             self.player_type,
                "announced_anniversaries": list(self.announced_anniversaries),
                "tab_first_visit":         self.tab_first_visit,
                "last_session_hour":       self.last_session_hour,
            }
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(d, fh, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            pass

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _update_daily_streak(self, today: str) -> tuple[bool, int]:
        """Update daily streak; returns (streak_broken, new_streak_length)."""
        if not self.play_dates:
            self.play_dates.append(today)
            self.current_daily_streak = 1
            self.best_daily_streak = max(self.best_daily_streak, 1)
            return False, 1

        last = self.play_dates[-1]
        if last == today:
            # Already recorded today
            return False, self.current_daily_streak

        days_gap = _days_between(last, today)
        if days_gap == 1:
            # Consecutive day
            self.current_daily_streak += 1
            self.best_daily_streak = max(self.best_daily_streak, self.current_daily_streak)
            self.play_dates.append(today)
            return False, self.current_daily_streak
        else:
            # Streak broken
            old_streak = self.current_daily_streak
            self.current_daily_streak = 1
            self.play_dates.append(today)
            return True, old_streak

    def _avg_session_minutes(self) -> float:
        """Return average session duration in minutes using _TrophieMemory if available."""
        if self._mem and self._mem.session_durations:
            durations = self._mem.session_durations
        else:
            return 30.0
        return sum(durations) / len(durations)

    def _total_rom_count(self) -> int:
        """Return total number of distinct ROMs ever played."""
        if self._mem:
            return len(self._mem.rom_play_counts)
        return len(self.table_last_played)

    def _play_times(self) -> list[int]:
        """Return play-hour list from _TrophieMemory if available."""
        if self._mem:
            return self._mem.play_times
        return []

    def _rom_play_counts(self) -> dict[str, int]:
        """Return ROM play counts from _TrophieMemory if available."""
        if self._mem:
            return self._mem.rom_play_counts
        return {}

    # ── 1. Session milestones ─────────────────────────────────────────────────

    def on_session_start(self) -> Optional[str]:
        """Call when a new play session begins.

        Returns a milestone comment when the session count crosses a threshold,
        an absence-return comment, or ``None``.
        """
        today = _today_str()
        now_hour = datetime.now().hour

        # -- Absence detection (before updating last_session_date) -----------
        absence_comment = None
        if self.last_session_date:
            days_away = _days_between(self.last_session_date, today)
            if days_away >= 30:
                absence_comment = _pick(_RETURN_30D)
            elif days_away >= 7:
                absence_comment = _pick(_RETURN_7D)
            elif days_away >= 3:
                absence_comment = _pick(_RETURN_3D)

        # -- Update counters -------------------------------------------------
        self.total_sessions += 1
        self.last_session_date = today
        if not self.first_session_date:
            self.first_session_date = today
        self.last_session_hour = now_hour

        # -- Daily streak ---------------------------------------------------
        streak_broken, streak_val = self._update_daily_streak(today)

        # -- Update player type --------------------------------------------
        self.player_type = self.detect_player_type()

        self.save()

        # -- Choose comment priority ----------------------------------------
        # 1. Absence comment takes top priority
        if absence_comment:
            return absence_comment

        # 2. Session milestone
        if self.total_sessions in _SESSION_MILESTONES:
            pool = _SESSION_MILESTONE_COMMENTS.get(self.total_sessions, [])
            if pool:
                return _pick(pool)

        # 3. Streak update
        if streak_broken and streak_val >= 3:
            return _pick(_STREAK_DAILY_NEGATIVE, days=streak_val)
        if not streak_broken and self.current_daily_streak in (3, 7, 14, 30, 60, 100):
            return _pick(_STREAK_DAILY_POSITIVE, days=self.current_daily_streak)

        # 4. Anniversary
        anniv = self._check_usage_anniversary(today)
        if anniv:
            return anniv

        # 5. Playtime pattern
        return self._check_playtime_pattern(now_hour)

    # ── 2. Session end ────────────────────────────────────────────────────────

    def on_session_end(self, duration_min: float, ach_count: int) -> Optional[str]:
        """Call when a play session ends.

        Parameters
        ----------
        duration_min:
            Duration of the session in minutes.
        ach_count:
            Number of achievements unlocked during this session.

        Returns a comparison or coaching comment, or ``None``.
        """
        avg = self._avg_session_minutes()
        self.session_ach_history.append(ach_count)

        # -- Achievement streak update ------------------------------------
        if ach_count > 0:
            self.current_ach_streak += 1
        else:
            self.current_ach_streak = 0

        self.save()

        # -- Best session check -------------------------------------------
        if self._mem and self._mem.session_durations:
            all_durations = self._mem.session_durations
            if duration_min > 0 and len(all_durations) > 1 and duration_min > max(all_durations):
                return _pick(_COMPARE_BEST_SESSION, dur=int(duration_min))

        # -- Achievement streak comment -----------------------------------
        if self.current_ach_streak in (3, 5, 10):
            return _pick(_STREAK_ACH_POSITIVE, count=self.current_ach_streak)

        # -- Comparison with average ------------------------------------
        if avg > 0 and len(getattr(self._mem, "session_durations", [])) >= 5:
            diff = duration_min - avg
            if diff > 30:
                return _pick(_COMPARE_BETTER_THAN_AVG, diff=int(diff))
            if diff < -20 and avg > 10:
                return _pick(_COMPARE_WORSE_THAN_AVG, avg=int(avg), dur=int(duration_min))

        # -- Improvement check (need at least 10 sessions) ---------------
        history = self.session_ach_history
        if len(history) >= 10:
            early_avg = sum(history[:5]) / 5
            recent_avg = sum(history[-5:]) / 5
            if early_avg > 0 and recent_avg > early_avg * 1.2:
                pct = int((recent_avg - early_avg) / early_avg * 100)
                return _pick(_COMPARE_IMPROVEMENT, pct=pct)

        return None

    # ── 3. Achievement milestone ───────────────────────────────────────────────

    def on_achievement(
        self,
        rom: str = "",
        unlocked: int = 0,
        total: int = 0,
    ) -> Optional[str]:
        """Call when an achievement is unlocked.

        Parameters
        ----------
        rom:
            ROM identifier of the table.
        unlocked:
            Total achievements unlocked on *rom* after this unlock.
        total:
            Total possible achievements on *rom* (0 if unknown).

        Returns a milestone/coaching comment or ``None``.
        """
        today = _today_str()
        self.total_achievements += 1
        if not self.first_achievement_date:
            self.first_achievement_date = today

        # -- Update table completion ---------------------------------------
        if rom:
            entry = self.table_completion.setdefault(rom, {"unlocked": 0, "total": 0})
            if unlocked > 0:
                entry["unlocked"] = unlocked
            if total > 0:
                entry["total"] = total

        self.save()

        # -- Achievement milestone comment ---------------------------------
        if self.total_achievements in _ACH_MILESTONES:
            pool = _ACH_MILESTONE_COMMENTS.get(self.total_achievements, [])
            if pool:
                return _pick(pool)

        # -- Table performance coaching ------------------------------------
        if rom and total > 0 and unlocked > 0:
            pct = int(unlocked / total * 100)
            table_label = rom
            if pct == 100:
                return _pick(_PERF_100, table=table_label)
            if pct >= 90:
                return _pick(_PERF_NEAR_100, pct=pct, table=table_label)

        return None

    # ── 4. Performance coaching (on-demand) ────────────────────────────────────

    def get_performance_comment(
        self,
        all_tables: Optional[list[str]] = None,
    ) -> Optional[str]:
        """Return a performance-coaching comment based on table-completion data.

        Parameters
        ----------
        all_tables:
            Optional list of all known ROM identifiers; used to detect
            unexplored tables.
        """
        completion = self.table_completion
        if not completion:
            return None

        # -- Near-100% coaching ------------------------------------------
        near_100 = [
            (rom, e)
            for rom, e in completion.items()
            if e.get("total", 0) > 0
            and e.get("unlocked", 0) > 0
            and 90 <= int(e["unlocked"] / e["total"] * 100) < 100
        ]
        if near_100:
            rom, entry = random.choice(near_100)
            pct = int(entry["unlocked"] / entry["total"] * 100)
            return _pick(_PERF_NEAR_100, pct=pct, table=rom)

        # -- Jack of all tables (many started, none finished) -------------
        started = [
            rom for rom, e in completion.items()
            if e.get("unlocked", 0) > 0 and e.get("total", 0) > 0
            and e["unlocked"] < e["total"]
        ]
        if len(started) >= 5:
            return _pick(_PERF_JACK_OF_ALL, started=len(started))

        # -- Unexplored tables --------------------------------------------
        if all_tables:
            played = set(self._rom_play_counts().keys()) | set(completion.keys())
            unplayed = [t for t in all_tables if t not in played]
            if len(unplayed) >= 3:
                return _pick(_PERF_UNEXPLORED, count=len(unplayed))

        return None

    # ── 5. Streak comments (on-demand) ─────────────────────────────────────────

    def get_streak_comment(self) -> Optional[str]:
        """Return a streak-related comment, or ``None`` if nothing notable."""
        # Challenge streaks
        if self._mem:
            wins_total  = self._mem.challenge_wins
            losses_total = self._mem.challenge_losses
        else:
            wins_total = losses_total = 0

        if self.challenge_streak >= 3:
            return _pick(_STREAK_CHALLENGE_WIN, wins=self.challenge_streak)
        if self.challenge_streak <= -3:
            return _pick(_STREAK_CHALLENGE_LOSE, losses=abs(self.challenge_streak))

        # Daily streak milestone
        streak = self.current_daily_streak
        if streak in (3, 7, 14, 30, 60, 100):
            return _pick(_STREAK_DAILY_POSITIVE, days=streak)

        return None

    def on_challenge_result(self, won: bool) -> Optional[str]:
        """Update challenge streak and return a comment if notable."""
        if won:
            self.challenge_streak = max(0, self.challenge_streak) + 1
        else:
            self.challenge_streak = min(0, self.challenge_streak) - 1
        self.save()

        if won and self.challenge_streak in (3, 5, 10):
            return _pick(_STREAK_CHALLENGE_WIN, wins=self.challenge_streak)
        if not won and self.challenge_streak in (-3, -5, -10):
            return _pick(_STREAK_CHALLENGE_LOSE, losses=abs(self.challenge_streak))
        return None

    # ── 6. Social / Leaderboard ────────────────────────────────────────────────

    def on_rank_changed(
        self,
        new_rank: int,
        old_rank: int = 0,
        total_players: int = 0,
    ) -> Optional[str]:
        """Return a comment when the player's leaderboard rank changes.

        Parameters
        ----------
        new_rank:
            New rank (1 = first place).
        old_rank:
            Previous rank; 0 means unknown / first observation.
        total_players:
            Total players on the leaderboard; used for top-X% comments.
        """
        self.cloud_rank = new_rank
        if total_players > 0:
            self.cloud_total_players = total_players
        self.save()

        if total_players > 0:
            pct = max(1, int(new_rank / total_players * 100))
            if pct <= 10:
                return _pick(_SOCIAL_TOP_PCT, pct=pct)

        if old_rank > 0 and new_rank < old_rank:
            return _pick(_SOCIAL_RANK_UP, rank=new_rank)
        if old_rank > 0 and new_rank > old_rank:
            return _pick(_SOCIAL_RANK_DOWN, rank=new_rank)
        return None

    def on_rival_activity(
        self,
        rival_name: str,
        point_diff: int = 0,
    ) -> Optional[str]:
        """Return a comment when a rival has recent activity."""
        if point_diff > 0:
            return _pick(_SOCIAL_RIVAL, rival=rival_name, diff=point_diff)
        return _pick(_SOCIAL_RIVAL, rival=rival_name, diff="?")

    # ── 7. Seasonal / Anniversary ──────────────────────────────────────────────

    def _check_usage_anniversary(self, today: str) -> Optional[str]:
        """Return an anniversary comment if a threshold is crossed today."""
        if not self.first_session_date:
            return None

        months = {
            "1m":  30,
            "3m":  91,
            "6m":  182,
            "12m": 365,
        }
        for key, days_threshold in months.items():
            if key in self.announced_anniversaries:
                continue
            elapsed = _days_between(self.first_session_date, today)
            if elapsed >= days_threshold:
                self.announced_anniversaries.add(key)
                pools = {
                    "1m":  _ANNIV_1M,
                    "3m":  _ANNIV_3M,
                    "6m":  _ANNIV_6M,
                    "12m": _ANNIV_12M,
                }
                pool = pools.get(key, [])
                if pool:
                    return _pick(pool)

        # First-achievement anniversary
        if (
            self.first_achievement_date
            and "first_ach_1y" not in self.announced_anniversaries
        ):
            elapsed = _days_between(self.first_achievement_date, today)
            if elapsed >= 365:
                self.announced_anniversaries.add("first_ach_1y")
                return _pick(_ANNIV_FIRST_ACH)

        return None

    def get_anniversary_comment(self) -> Optional[str]:
        """Check and return any pending anniversary comment for today."""
        return self._check_usage_anniversary(_today_str())

    # ── 8. Playstyle recognition ──────────────────────────────────────────────

    def detect_player_type(self) -> str:
        """Infer player personality from session and achievement data.

        Returns one of the ``PLAYER_*`` constants.  The detection requires at
        least 5 sessions worth of data; returns :data:`PLAYER_UNKNOWN` when
        there is not enough information yet.
        """
        durations = list(getattr(self._mem, "session_durations", []))
        play_times_h = self._play_times()
        rom_counts   = self._rom_play_counts()
        sessions     = self.total_sessions

        if sessions < 5 or not durations:
            return PLAYER_UNKNOWN

        avg_dur   = sum(durations) / len(durations)
        n_roms    = len(rom_counts)
        ach_hist  = self.session_ach_history or [0]
        avg_ach   = sum(ach_hist) / len(ach_hist)

        # Night-owl: >40% of sessions after 21h or before 5h
        if len(play_times_h) >= 5:
            night_ratio = sum(1 for h in play_times_h if h >= 21 or h < 5) / len(play_times_h)
            if night_ratio > 0.4:
                return PLAYER_NIGHT_OWL

        # Weekend warrior: >60% of sessions on Sat/Sun
        # (approximate from play_dates weekday distribution)
        if len(self.play_dates) >= 5:
            weekend = sum(
                1 for d in self.play_dates
                if date.fromisoformat(d).weekday() >= 5
            )
            if weekend / len(self.play_dates) > 0.6:
                return PLAYER_WEEKEND

        # Hardcore: very long sessions (avg > 120 min) AND high achievement rate
        if avg_dur > 120 and avg_ach > 3:
            return PLAYER_HARDCORE

        # Grinder: long sessions (avg > 60 min), many tables, few ach/session
        if avg_dur > 60 and n_roms >= 5 and avg_ach < 2:
            return PLAYER_GRINDER

        # Speedrunner: short sessions (avg < 30 min), high achievement rate (>3/session)
        if avg_dur < 30 and avg_ach > 3:
            return PLAYER_SPEEDRUNNER

        # Explorer: many different ROMs, short-to-medium sessions
        if n_roms >= 8 and avg_dur < 60:
            return PLAYER_EXPLORER

        # Loyalist: few ROMs but very high play counts
        if n_roms <= 3 and sessions >= 10:
            return PLAYER_LOYALIST

        # Casual: relatively short sessions, moderate achievement rate
        if avg_dur < 30 and avg_ach <= 2:
            return PLAYER_CASUAL

        return PLAYER_UNKNOWN

    def get_playstyle_comment(self) -> Optional[str]:
        """Return a comment tailored to the detected player type."""
        ptype = self.detect_player_type()
        self.player_type = ptype
        pool = _PLAYSTYLE_COMMENTS.get(ptype)
        if pool:
            return _pick(pool)
        return None

    # ── 9. Emotional / Motivational ───────────────────────────────────────────

    def get_return_comment(self, days_absent: int) -> Optional[str]:
        """Return a motivational comment based on how many days the player was away."""
        if days_absent >= 30:
            return _pick(_RETURN_30D)
        if days_absent >= 7:
            return _pick(_RETURN_7D)
        if days_absent >= 3:
            return _pick(_RETURN_3D)
        return None

    def on_heavy_session_day(self, session_count_today: int) -> Optional[str]:
        """Return a comment when the player has many sessions in a single day."""
        if session_count_today >= 3:
            return _pick(_HEAVY_SESSION_DAY, count=session_count_today)
        return None

    # ── 10. Table-specific memory ─────────────────────────────────────────────

    def on_rom_start(self, rom: str, table_name: Optional[str] = None) -> Optional[str]:
        """Call when a ROM/table session starts.  Returns a table-specific comment or ``None``."""
        today = _today_str()
        label = table_name or rom
        last  = self.table_last_played.get(rom, "")
        counts = self._rom_play_counts()
        fav    = (
            max(counts, key=lambda r: counts[r])
            if counts else None
        )

        # Determine days since last played this ROM
        days_ago: Optional[int] = None
        if last:
            days_ago = _days_between(last, today)

        # Update last-played
        self.table_last_played[rom] = today
        self.save()

        # Favourite table comment
        if fav and fav == rom and (counts.get(rom, 0) >= 5):
            return _pick(_TABLE_FAVOURITE, table=label)

        # Long-not-played revisit
        if days_ago is not None and days_ago >= 30:
            return _pick(_TABLE_REVISITED, table=label, days=days_ago)
        if days_ago is not None and days_ago >= 7:
            return _pick(_TABLE_NEGLECTED, table=label, days=days_ago)

        return None

    def get_neglected_table_comment(self) -> Optional[str]:
        """Return a comment about a table that has not been played for a long time."""
        today = _today_str()
        candidates = [
            (rom, _days_between(last, today))
            for rom, last in self.table_last_played.items()
            if _days_between(last, today) >= 14
        ]
        if not candidates:
            return None
        rom, days = max(candidates, key=lambda x: x[1])
        return _pick(_TABLE_NEGLECTED, table=rom, days=days)

    def on_table_achievement_milestone(
        self, rom: str, count: int, table_name: Optional[str] = None
    ) -> Optional[str]:
        """Return a comment when a per-table achievement count milestone is reached."""
        label = table_name or rom
        if count in (5, 10, 25, 50):
            return _pick(_TABLE_ACH_MILESTONE, count=count, table=label)
        return None

    # ── 11. Dismiss / Comment habits ─────────────────────────────────────────

    def on_comment_dismissed(self, ms: int) -> Optional[str]:
        """Record a comment dismissal and return a habit-acknowledgement comment if appropriate.

        Parameters
        ----------
        ms:
            Time in milliseconds between the comment appearing and being dismissed.
        """
        if self._mem:
            msg = self._mem.record_dismiss(ms)
            if msg:
                return msg

        # Reader mode: consistently long reading time triggers a special comment
        if self._mem and len(self._mem.dismiss_speed) >= 10:
            recent = self._mem.dismiss_speed[-10:]
            slow_reads = sum(1 for t in recent if t >= 4000)
            if slow_reads >= 7 and not self._reader_comment_pending:
                self._reader_comment_pending = True
                self.save()
                return _pick(_DISMISS_READER_MODE)

        return None

    def comment_frequency_multiplier(self) -> float:
        """Return a multiplier for comment frequency (lower = fewer comments).

        Delegates to ``_TrophieMemory`` when available; otherwise returns 1.0.
        """
        if self._mem:
            return self._mem.comment_frequency_multiplier()
        return 1.0

    # ── 12. Tab habits ────────────────────────────────────────────────────────

    def on_tab_visit(self, tab_name: str) -> Optional[str]:
        """Call when the user visits a tab.  Returns a habit comment or ``None``.

        Parameters
        ----------
        tab_name:
            Normalised (lower-case) tab label text.
        """
        today = _today_str()
        is_first_ever = tab_name not in self.tab_first_visit
        if is_first_ever:
            self.tab_first_visit[tab_name] = today
            self.save()

        # Always-first-tab check: if this tab has the most visits by far
        if self._mem and self._mem.tab_visits:
            visits = self._mem.tab_visits
            total_visits = sum(visits.values()) or 1
            tab_share = visits.get(tab_name, 0) / total_visits
            if tab_share > 0.5 and visits.get(tab_name, 0) >= 10:
                pool = _TAB_ALWAYS_FIRST.get(tab_name)
                if pool:
                    return _pick(pool)

        # Cloud-tab nudge: cloud tab never visited after 7+ sessions
        if tab_name != "cloud" and self.total_sessions >= 7:
            if "cloud" not in self.tab_first_visit:
                return _pick(_TAB_CLOUD_SUGGESTION)

        return None

    def get_unvisited_tab_comment(
        self, known_tabs: list[str], days_threshold: int = 14
    ) -> Optional[str]:
        """Return a comment encouraging the user to visit a tab they have never used.

        Parameters
        ----------
        known_tabs:
            All tab names available in the application.
        days_threshold:
            Minimum days since first session before nudging about an unvisited tab.
        """
        if not self.first_session_date:
            return None
        today = _today_str()
        days_since_start = _days_between(self.first_session_date, today)
        if days_since_start < days_threshold:
            return None

        visited = set(self.tab_first_visit.keys())
        if self._mem:
            visited |= set(self._mem.tab_visits.keys())

        unvisited = [t for t in known_tabs if t not in visited]
        if unvisited:
            tab = random.choice(unvisited)
            return _pick(_TAB_NEVER_VISITED, tab=tab)
        return None

    # ── 13. Playtime-pattern awareness ────────────────────────────────────────

    def _check_playtime_pattern(self, current_hour: int) -> Optional[str]:
        """Return a comment if the current session hour deviates from the routine."""
        play_times_h = self._play_times()
        if len(play_times_h) < 10:
            return None

        # Compute modal play-hour window (±2 h)
        from collections import Counter
        hour_counts = Counter(play_times_h)
        modal_hour = hour_counts.most_common(1)[0][0]

        diff = abs(current_hour - modal_hour)
        # Wrap-around midnight
        diff = min(diff, 24 - diff)

        if diff >= 5:
            if current_hour < modal_hour:
                return _pick(_PLAYTIME_UNUSUAL_EARLY)
            return _pick(_PLAYTIME_UNUSUAL_LATE)
        return None

    def get_playtime_pattern_comment(self) -> Optional[str]:
        """Return a playtime-pattern comment based on the current hour."""
        return self._check_playtime_pattern(datetime.now().hour)

    # ── Unified entry-point ───────────────────────────────────────────────────

    def get_periodic_comment(self) -> Optional[str]:
        """Return a context-aware periodic comment (call every few minutes).

        Cycles through: playstyle → anniversary → streak → performance → neglected table.
        Returns the first non-``None`` result.
        """
        checks = [
            self.get_playstyle_comment,
            self.get_anniversary_comment,
            self.get_streak_comment,
            self.get_performance_comment,
            self.get_neglected_table_comment,
            self.get_playtime_pattern_comment,
        ]
        random.shuffle(checks)
        for fn in checks:
            try:
                result = fn()
                if result:
                    return result
            except Exception:
                continue
        return None
