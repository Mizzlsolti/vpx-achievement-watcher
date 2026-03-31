"""
aweditor.py – AWEditor: Custom Achievement Editor for Non-ROM Tables
=====================================================================
Provides the AWEditorMixin class, which adds the "🎯 AWEditor" tab to the
main window.  The tab lets users create custom achievements for tables that
have no VPinMAME ROM / NVRAM map and therefore cannot use the normal
achievement-detection pipeline.

Trigger mechanism overview
--------------------------
1. AWEditor generates three files:
     • aw_{TableName}.vbs   – VBScript with a FireAchievement() Sub
     • {TableName}.custom.json – Achievement rule definitions
     • README_aw_{TableName}.txt – Installation instructions
2. The user copies the .vbs next to the .vpx and adds an ExecuteGlobal GetTextFile(...) call.
3. During gameplay the VBScript writes a <event>.trigger file into the
   custom_events/ folder.
4. The watcher's ``_poll_custom_events()`` method (called every loop iteration
   while a table session is active) detects the file, resolves it against the
   matching ``*.custom.json`` rule, emits an achievement toast, and removes the
   trigger file so it can fire again on the next occurrence.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading  # noqa: F401 – available for subclasses
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from theme import get_theme_color
from watcher_core import (
    CONFIG_FILE,
    ensure_dir,
    ensure_vpxtool,
    f_index,
    f_vps_mapping,
    load_json,
    p_aweditor,
    p_custom_events,
    p_local_maps,
    run_vpxtool_get_rom,
)

# ---------------------------------------------------------------------------
# Event pattern catalogue
# ---------------------------------------------------------------------------

# Each entry: (regex_pattern, title, event_name, default_checked)
# ORDER MATTERS – more specific patterns must appear before generic ones so they
# are matched first (the loop breaks on the first match per line).
_EVENT_PATTERNS: list[tuple[str, str, str, bool]] = [
    # ── Multiball ──────────────────────────────────────────────────────────
    (r"Sub.*Multi[_]?[Bb]all",        "Multiball",          "multiball",          False),
    # ── Jackpot (specific before generic) ─────────────────────────────────
    (r"Sub.*SuperJackpot|Sub.*Super_Jackpot", "Super Jackpot", "super_jackpot",   False),
    (r"Sub.*Triple[_]?Jackpot",        "Triple Jackpot",     "triple_jackpot",     False),
    (r"Sub.*Jackpot",                  "Jackpot",            "jackpot",            False),
    # ── Wizard ─────────────────────────────────────────────────────────────
    (r"Sub.*Wizard[_]?Mode|Sub.*Wizard", "Wizard Mode",      "wizard_mode",        False),
    # ── Mission (specific before generic) ─────────────────────────────────
    (r"Sub.*Mission.*Start|Sub.*StartMission|Sub.*MissionStart", "Mission Start", "mission_start", False),
    (r"Sub.*Mission.*Complete|Sub.*CompleteMission|Sub.*MissionComplete|Sub.*Mission.*End|Sub.*EndMission", "Mission Complete", "mission_complete", False),
    (r"Sub.*Mission",                  "Mission",            "mission",            False),
    # ── Quest (specific before generic) ────────────────────────────────────
    (r"Sub.*Quest.*Start|Sub.*StartQuest|Sub.*QuestStart", "Quest Start",         "quest_start",        False),
    (r"Sub.*Quest.*Complete|Sub.*CompleteQuest|Sub.*QuestComplete|Sub.*Quest.*End", "Quest Complete", "quest_complete", False),
    (r"Sub.*Quest",                    "Quest",              "quest",              False),
    # ── Mode (specific before generic) ────────────────────────────────────
    (r"Sub.*Mode.*Start|Sub.*ModeStart|Sub.*StartMode|Sub.*ModeActive|Sub.*ActivateMode", "Mode Start", "mode_start", False),
    (r"Sub.*Mode.*Complete|Sub.*ModeComplete|Sub.*Mode.*End|Sub.*EndMode|Sub.*Mode.*Win", "Mode Complete", "mode_complete", False),
    # ── Game Modes / Features (table-specific) ────────────────────────────
    (r"Sub.*Start[A-Z]\w+Mode",        "Game Mode Start",    "game_mode_start",    False),
    (r"Sub.*Activate[A-Z]\w+",         "Feature Activated",  "feature_activate",   False),
    (r"Sub.*Begin[A-Z]\w+",            "Feature Begin",      "feature_begin",      False),
    (r"Sub.*Complete[A-Z]\w+",         "Feature Complete",   "feature_complete",   False),
    (r"Sub.*Collect[A-Z]\w+",          "Collect",            "collect",            False),
    (r"Sub.*Award[A-Z]\w+",            "Award",              "award",              False),
    (r"Sub.*Unlock[A-Z]\w+",           "Unlock",             "unlock",             False),
    # ── Boss / Final ───────────────────────────────────────────────────────
    (r"Sub.*Boss",                     "Boss Fight",         "boss_fight",         False),
    (r"Sub.*Final[A-Z]\w+",            "Final Challenge",    "final_challenge",    False),
    # ── Scoring milestones ─────────────────────────────────────────────────
    (r"Sub.*Super[A-Z]\w+",            "Super Feature",      "super_feature",      False),
    (r"Sub.*Mega[A-Z]\w+",             "Mega Feature",       "mega_feature",       False),
    (r"Sub.*Ultra[A-Z]\w+",            "Ultra Feature",      "ultra_feature",      False),
    # ── Extra Ball ─────────────────────────────────────────────────────────
    (r"Sub.*Extra[_]?Ball",            "Extra Ball",         "extra_ball",         False),
    # ── Skillshot (specific before generic) ───────────────────────────────
    (r"Sub.*Super[_]?Skill",           "Super Skillshot",    "super_skillshot",    False),
    (r"Sub.*Skill[_]?[Ss]hot",         "Skillshot",          "skillshot",          False),
    # ── Ball events ────────────────────────────────────────────────────────
    (r"Sub.*Ball[_]?Save",             "Ball Save",          "ball_save",          False),
    (r"Sub.*Ball[_]?Lock|Sub.*Lock[_]?Ball", "Ball Lock",    "ball_lock",          False),
    (r"Sub.*Launch[_]?Ball|Sub.*PlungeBall", "Ball Launch",  "ball_launch",        False),
    # ── Combo / Ramp / Loop / Spinner ──────────────────────────────────────
    (r"Sub.*Combo",                    "Combo",              "combo",              False),
    (r"Sub.*Ramp.*Hit",                "Ramp Hit",           "ramp_hit",           False),
    (r"Sub.*Loop",                     "Loop Shot",          "loop_shot",          False),
    (r"Sub.*Orbit",                    "Orbit Shot",         "orbit_shot",         False),
    (r"Sub.*Spinner",                  "Spinner",            "spinner",            False),
    # ── Bumpers / Slings / Targets ─────────────────────────────────────────
    (r"Sub.*Bumper.*Hit",              "Bumper Hit",         "bumper_hit",         False),
    (r"Sub.*Slingshot|Sub.*Sling\b",   "Slingshot",          "slingshot",          False),
    (r"Sub.*Target.*Hit|Sub.*DropTarget", "Target Hit",      "target_hit",         False),
    # ── Saves / Outlane ────────────────────────────────────────────────────
    (r"Sub.*Kickback",                 "Kickback",           "kickback",           False),
    (r"Sub.*Outlane",                  "Outlane Save",       "outlane_save",       False),
    (r"Sub.*Magna[_]?Save",            "Magna Save",         "magna_save",         False),
    # ── Hurry Up / Frenzy / Bonus ──────────────────────────────────────────
    (r"Sub.*Hurry[_]?Up",              "Hurry Up",           "hurry_up",           False),
    (r"Sub.*Frenzy",                   "Frenzy",             "frenzy",             False),
    (r"Sub.*Bonus.*Collect|Sub.*CollectBonus|Sub.*BonusCollect", "Bonus Collect", "bonus_collect", False),
    # ── Mini Game / Mystery / Scoop ────────────────────────────────────────
    (r"Sub.*Mini[_]?Game|Sub.*MiniWizard", "Mini Game",      "mini_game",          False),
    (r"Sub.*Mystery",                  "Mystery Award",      "mystery",            False),
    (r"Sub.*Scoop",                    "Scoop Hit",          "scoop_hit",          False),
    # ── Multiplier / Video Mode / Captive Ball ─────────────────────────────
    (r"Sub.*Multiplier|Sub.*Playfield[_]?X", "Playfield Multiplier", "multiplier", False),
    (r"Sub.*Video[_]?Mode",            "Video Mode",         "video_mode",         False),
    (r"Sub.*Captive[_]?Ball",          "Captive Ball",       "captive_ball",       False),
    # ── Drain / Tilt ───────────────────────────────────────────────────────
    (r"Sub.*Drain",                    "Drain",              "drain",              False),
    (r"Sub.*Tilt",                     "Tilt",               "tilt",               False),
]

# Compiled regex to identify a VBScript Sub definition line (strict)
_SUB_DEF_RE = re.compile(
    r"^(?:Public\s+|Private\s+)?Sub\s+([a-zA-Z0-9_]+)",
    re.IGNORECASE,
)

# Sub names that look like implementation helpers (animations, sounds, timers, etc.)
# are filtered out to reduce noise in the Detected Events list.
# Rules:
#   - Filter if name STARTS WITH one of the noise prefixes (case-insensitive).
#   - Filter if name ENDS WITH "timer" (case-insensitive).
# Using a prefix/suffix check avoids false positives like Sub LeftRampSoundJackpot
# or Sub SauceTimerExpired which are real game-logic events.
_NOISE_PREFIXES = ("animate", "sound", "update", "light", "flash", "init")


def _is_noise_sub(sub_name: str) -> bool:
    """Return True if this sub name looks like an implementation helper, not a game-logic event."""
    name_lower = sub_name.lower()
    if any(name_lower.startswith(p) for p in _NOISE_PREFIXES):
        return True
    if name_lower.endswith("timer"):
        return True
    return False

# Subs that VPX calls automatically on table load or on key events – these fire
# before the player starts playing, so achievements attached to them would
# trigger immediately at startup.  They are marked with ⚠️ in the UI so users
# know to uncheck them before exporting.
_STARTUP_SUB_RE = re.compile(
    r"AttractMode|_Init\b|Table_Init|Table_KeyDown|Table_KeyUp|KeyDown|KeyUp|_Timer\b",
    re.IGNORECASE,
)

# Event types that are too generic or frequent to be useful as achievements.
# Used by _aw_auto_select_for_option_c to skip noise events.
_AUTO_SELECT_SKIP_EVENTS: frozenset[str] = frozenset({
    "drain", "tilt", "slingshot", "bumper_hit", "spinner",
})

# Stop words excluded when deriving a thematic keyword from a table filename.
_KEYWORD_STOP_WORDS: frozenset[str] = frozenset({
    "the", "of", "a", "an", "and", "from", "in", "on", "at", "to", "for",
})


def _extract_table_keyword(fname: str) -> str:
    """
    Extracts a short thematic keyword from a .vpx filename for use in achievement titles.

    Examples:
        "AFM_AttackFromMars_VPW.vpx"  -> "Mars"
        "JP_JurassicPark_VPW.vpx"     -> "Park"
        "MM_MedievalMadness.vpx"       -> "Madness"
        "Theatre_of_Magic_VPX.vpx"     -> "Magic"
        "PinballWizard.vpx"            -> "Wizard"
    """
    stem = os.path.splitext(fname)[0]

    # Remove known suffixes first (case-insensitive)
    stem = re.sub(r"[_\s](?:VPW|VPX|MOD|v\d[\w.]*|\d+)$", "", stem, flags=re.IGNORECASE)

    # Remove short prefix (2-4 uppercase chars followed by underscore, e.g. "AFM_", "JP_")
    stem = re.sub(r"^[A-Z]{2,4}_", "", stem)

    # Replace underscores with spaces, then split CamelCase
    stem = stem.replace("_", " ")
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", stem)
    words = spaced.strip().split()

    # Prefer words longer than 3 chars that are not stop words
    meaningful = [w for w in words if len(w) > 3 and w.lower() not in _KEYWORD_STOP_WORDS]
    if not meaningful:
        # Fall back to any non-stop word
        meaningful = [w for w in words if w.lower() not in _KEYWORD_STOP_WORDS]

    # Return last meaningful word (most specific / thematic)
    if meaningful:
        return meaningful[-1]
    if words:
        return words[-1]
    return ""


# Body indicators: patterns that suggest a Sub contains real game logic even if
# its name did not match any entry in _EVENT_PATTERNS.
# Each entry: (regex_pattern, human_readable_type)
_BODY_INDICATORS: list[tuple[str, str]] = [
    (r"\bAddScore\b|\.Score\s*=|\bCurrentPlayer\b",  "Scoring Logic"),
    (r"\bModeIsRunning\b|\bModeActive\b|\bbMode\b",   "Mode State"),
    (r"\bDMD\b|\bDispDMD\b|\bShowText\b|\bDisplayText\b", "Display Event"),
]

# Maps event_name values to display categories used for grouping in the UI.
_MISSIONS_MODES_EVENTS: frozenset[str] = frozenset({
    "multiball", "wizard_mode",
    "mission_start", "mission_complete", "mission",
    "quest_start", "quest_complete", "quest",
    "mode_start", "mode_complete",
    "game_mode_start", "feature_activate", "feature_begin", "feature_complete",
    "collect", "award", "unlock",
    "boss_fight", "final_challenge",
})

_MECHANICS_EVENTS: frozenset[str] = frozenset({
    "super_jackpot", "triple_jackpot", "jackpot",
    "extra_ball", "super_skillshot", "skillshot",
    "ball_save", "ball_lock", "ball_launch",
    "combo", "ramp_hit", "loop_shot", "orbit_shot",
    "super_feature", "mega_feature", "ultra_feature",
    "hurry_up", "frenzy", "bonus_collect",
    "mini_game", "mystery", "scoop_hit",
    "multiplier", "video_mode", "captive_ball",
})


def _event_category(event_name: str) -> str:
    """Return a category string for a given event_name."""
    if event_name in _MISSIONS_MODES_EVENTS:
        return "missions_modes"
    if event_name in _MECHANICS_EVENTS:
        return "mechanics"
    return "basics"

# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class _ScanTablesWorker(QThread):
    """Scans TABLES_DIR for .vpx files that have no ROM or no NVRAM map."""

    # Each entry: {"filename": str, "rom": str, "has_map": bool, "is_local": bool}
    finished = pyqtSignal(list)
    progress = pyqtSignal(int, int)  # (current, total)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg

    def run(self):
        results: list[dict] = []
        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        if not tables_dir or not os.path.isdir(tables_dir):
            self.finished.emit(results)
            return

        # Load the cloud index (ROM → map path) and VPS-ID mapping once
        # Normalize keys to lowercase for case-insensitive lookups
        try:
            cloud_index: set = {
                k.lower() for k in (load_json(f_index(self.cfg), {}) or {})
            }
        except Exception:
            cloud_index = set()
        try:
            raw_mapping: dict = load_json(f_vps_mapping(self.cfg), {}) or {}
            vps_mapping: set = {k.lower() for k, v in raw_mapping.items() if v}
        except Exception:
            vps_mapping = set()

        # Collect all .vpx files first so we can report total count
        vpx_files = sorted(
            fname for fname in os.listdir(tables_dir)
            if fname.lower().endswith(".vpx")
        )
        total = len(vpx_files)

        for idx, fname in enumerate(vpx_files):
            self.progress.emit(idx + 1, total)
            vpx_path = os.path.join(tables_dir, fname)
            try:
                rom = run_vpxtool_get_rom(self.cfg, vpx_path, suppress_warn=True) or ""
                if rom:
                    # Check local map files (but NOT .custom.json – those are AWEditor output)
                    m1 = os.path.join(p_local_maps(self.cfg), f"{rom}.json")
                    m2 = os.path.join(p_local_maps(self.cfg), f"{rom}.map.json")
                    if os.path.isfile(m1) or os.path.isfile(m2):
                        # Verify it is a real NVRAM map and not a custom achievements file.
                        # A real map has "fields"; a custom achievements file has "rules" but
                        # no "fields".  If we cannot read it, err on the side of skipping.
                        map_path = m1 if os.path.isfile(m1) else m2
                        try:
                            with open(map_path, "r", encoding="utf-8") as _f:
                                _map_data = json.load(_f)
                            if (
                                isinstance(_map_data, dict)
                                and "rules" in _map_data
                                and "fields" not in _map_data
                            ):
                                pass  # custom achievements file – do NOT skip
                            else:
                                continue  # real NVRAM map – skip
                        except Exception:
                            continue  # unreadable – assume real map and skip
                    # Check cloud index – if the ROM is listed there it has a map
                    if rom.lower() in cloud_index:
                        continue
                    # Check VPS-ID mapping – already assigned means it's managed
                    if rom.lower() in vps_mapping:
                        continue
                results.append({"filename": fname, "rom": rom, "has_map": False, "is_local": True})
            except Exception:
                results.append({"filename": fname, "rom": "", "has_map": False, "is_local": True})

        self.finished.emit(results)


class _AnalyzeScriptWorker(QThread):
    """Reads the VBScript of a .vpx file and finds matching event Subs."""

    finished = pyqtSignal(list)  # list of (title, sub_name, line_no, event_name, default_checked, category)

    def __init__(self, cfg, vpx_path: str, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.vpx_path = vpx_path

    @staticmethod
    def _prettify_sub_name(name: str) -> str:
        """Convert a CamelCase sub name to a human-readable title string."""
        # Insert spaces before uppercase letters that follow lowercase letters,
        # or before uppercase letters that start a new word in an all-caps run.
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
        # Re-merge sequences of spaced single uppercase letters back into
        # abbreviations, e.g. "D M D" -> "DMD", "V I P" -> "VIP".
        merged = re.sub(r"\b([A-Z])(?: ([A-Z]))+\b", lambda m: m.group(0).replace(" ", ""), spaced)
        return merged.strip()

    def run(self):
        findings: list[tuple[str, str, int, str, bool, str]] = []
        exe = ensure_vpxtool(self.cfg)
        if not exe:
            self.finished.emit(findings)
            return
        try:
            cp = subprocess.run(
                [exe, "script", "show", self.vpx_path],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=0x08000000,  # CREATE_NO_WINDOW – suppress console popup on Windows
                encoding="utf-8",
                errors="replace",
            )
            script = cp.stdout or ""
        except Exception:
            self.finished.emit(findings)
            return

        lines = script.splitlines()
        # Pre-compile body indicator patterns
        body_indicator_res = [
            (re.compile(pat, re.IGNORECASE), label)
            for pat, label in _BODY_INDICATORS
        ]
        # End-Sub pattern used to delimit sub bodies
        end_sub_re = re.compile(r"^\s*End\s+Sub\b", re.IGNORECASE)

        seen_events: set[str] = set()
        # Track sub names already covered by body analysis to avoid duplicates
        seen_sub_names: set[str] = set()
        i = 0
        while i < len(lines):
            lineno = i + 1
            stripped = lines[i].strip()
            # Only consider actual Sub definition lines (not variable declarations
            # or comments that happen to contain "Sub" as a substring).
            m_def = _SUB_DEF_RE.match(stripped)
            if not m_def:
                i += 1
                continue
            sub_name = m_def.group(1)
            # Skip implementation-helper subs (animations, sounds, timers, etc.)
            # that are not meaningful game-logic events.
            if _is_noise_sub(sub_name):
                i += 1
                continue
            # Build a clean, canonical test string so patterns work correctly
            # regardless of modifiers like "Public" / "Private".
            test_line = f"Sub {sub_name}"
            matched = False
            for pattern, title, event_name, default_checked in _EVENT_PATTERNS:
                if re.search(pattern, test_line, re.IGNORECASE):
                    # Determine display category from event name
                    category = _event_category(event_name)
                    # Make event_name unique if already used by a previous sub
                    unique_event = event_name
                    suffix = 2
                    while unique_event in seen_events:
                        unique_event = f"{event_name}_{suffix}"
                        suffix += 1
                    findings.append((title, sub_name, lineno, unique_event, default_checked, category))
                    seen_events.add(unique_event)
                    seen_sub_names.add(sub_name)
                    matched = True
                    break  # only first pattern match per sub

            # Body analysis: only for subs that had no pattern match and are not duplicates
            if not matched and sub_name not in seen_sub_names:
                # Collect the body of this sub up to the matching End Sub
                body_lines: list[str] = []
                j = i + 1
                while j < len(lines):
                    if end_sub_re.match(lines[j]):
                        break
                    body_lines.append(lines[j])
                    j += 1

                body_text = "\n".join(body_lines)
                for body_re, indicator_label in body_indicator_res:
                    if body_re.search(body_text):
                        pretty_title = self._prettify_sub_name(sub_name)
                        # Generate an event name from the sub name (lowercase + underscores)
                        base_event = re.sub(r"[^a-z0-9]+", "_", sub_name.lower()).strip("_")
                        # Make event_name unique if already used by a previous sub
                        unique_event = base_event
                        suffix = 2
                        while unique_event in seen_events:
                            unique_event = f"{base_event}_{suffix}"
                            suffix += 1
                        findings.append((
                            pretty_title,
                            sub_name,
                            lineno,
                            unique_event,
                            False,       # body-analysed findings are always unchecked
                            "body",
                        ))
                        seen_events.add(unique_event)
                        seen_sub_names.add(sub_name)
                        break  # one indicator match per sub is enough

            i += 1

        self.finished.emit(findings)


# ---------------------------------------------------------------------------
# AWEditorMixin
# ---------------------------------------------------------------------------

class AWEditorMixin:
    """
    Mixin that adds the '🎯 AWEditor' tab to the MainWindow.

    Expects the host class to provide:
        self.cfg          – AppConfig instance
        self.main_tabs    – QTabWidget
        self._add_tab_help_button(layout, key) – bottom-right help button helper
        self._show_tab_help(key) – help dialog helper
    """

    def _build_tab_aweditor(self):
        """Build the 🎯 AWEditor tab and add it to main_tabs."""
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(10, 10, 10, 6)
        outer.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QLabel(
            "<span style='font-size:15px; font-weight:bold; color:#E0E0E0;'>"
            "🎯 AWEditor – Custom Achievements for Non-ROM Tables and without NVRAM-Map</span>"
        )
        hdr.setWordWrap(True)
        outer.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#333;")
        outer.addWidget(sep)

        # ── Inner sub-tabs ─────────────────────────────────────────────────
        self._aw_inner_tabs = QTabWidget()
        self._aw_inner_tabs.setStyleSheet(
            "QTabWidget::pane { border:1px solid #333; background:#111; }"
            "QTabBar::tab { background:#1a1a1a; color:#aaa; padding:5px 14px;"
            " border:1px solid #333; border-bottom:none; }"
            "QTabBar::tab:selected { background:#222; color:#E0E0E0;"
            " border-bottom:2px solid #FF7F00; }"
            "QTabBar::tab:hover { background:#222; color:#E0E0E0; }"
        )
        outer.addWidget(self._aw_inner_tabs, stretch=1)

        # Sub-tab 1 – Tables list
        tables_tab = QWidget()
        self._build_aw_subtab_tables(tables_tab)
        self._aw_inner_tabs.addTab(tables_tab, "📋 Tables")

        # Sub-tab 2 – Codes (analyze / export)
        codes_tab = QWidget()
        self._build_aw_subtab_codes(codes_tab)
        self._aw_inner_tabs.addTab(codes_tab, "✏️ Codes")

        # ── Bottom help-button row (red ❓ + blue 💡) ─────────────────────
        help_row = QHBoxLayout()
        help_row.addStretch(1)

        btn_guide = QPushButton("💡 Custom Guide")
        btn_guide.setFixedHeight(28)
        btn_guide.setToolTip("How to create Custom Achievements step-by-step")
        btn_guide.setStyleSheet(
            "QPushButton { background-color: #1a1a1a; color: #4FC3F7;"
            " border: 1px solid #4FC3F7; border-radius: 5px;"
            " font-size: 9pt; font-weight: bold; padding: 0 10px; }"
            "QPushButton:hover { background-color: #4FC3F7; color: #000000; }"
        )
        btn_guide.clicked.connect(self._aw_show_custom_guide)
        help_row.addWidget(btn_guide)

        btn_help = QPushButton("❓")
        btn_help.setFixedSize(28, 28)
        btn_help.setToolTip("Show help for this tab")
        btn_help.setStyleSheet(
            "QPushButton { background-color: #1a1a1a; color: #FF7F00;"
            " border: 1px solid #FF7F00; border-radius: 14px;"
            " font-size: 11pt; font-weight: bold; padding: 0; }"
            "QPushButton:hover { background-color: #FF7F00; color: #000000; }"
        )
        btn_help.clicked.connect(self._aw_show_help_dialog)
        help_row.addWidget(btn_help)

        outer.addLayout(help_row)

        self.main_tabs.addTab(tab, "🎯 AWEditor")

        # Shared state
        self._aw_selected_table: str = ""    # .vpx filename selected in the Tables sub-tab
        self._aw_all_tables: list[dict] = [] # full (unfiltered) scan result

        # Load from cache or kick off initial scan
        self._aw_init_tables()

    # ------------------------------------------------------------------
    # Sub-tab 1 – Tables list
    # ------------------------------------------------------------------

    def _build_aw_subtab_tables(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Toolbar row ────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        self._aw_search = QLineEdit()
        self._aw_search.setPlaceholderText("🔍 Search Table or ROM…")
        self._aw_search.setStyleSheet(
            "QLineEdit { background:#222; color:#E0E0E0; border:1px solid #444;"
            " border-radius:4px; padding:4px 8px; }"
        )
        self._aw_search.textChanged.connect(self._aw_filter_tables)
        toolbar.addWidget(self._aw_search, stretch=1)

        self._aw_btn_scan = QPushButton("🔄 Scan")
        self._aw_btn_scan.setFixedWidth(90)
        self._aw_btn_scan.setStyleSheet(self._aw_btn_style())
        self._aw_btn_scan.setToolTip(
            "Rescan the Tables directory for .vpx files without a ROM or NVRAM map (refreshes cache)"
        )
        self._aw_btn_scan.clicked.connect(self._aw_scan_tables)
        toolbar.addWidget(self._aw_btn_scan)

        self._aw_btn_refresh = QPushButton("🔃 Refresh")
        self._aw_btn_refresh.setFixedWidth(90)
        self._aw_btn_refresh.setStyleSheet(self._aw_btn_style())
        self._aw_btn_refresh.setToolTip(
            "Refresh the Custom status column (checks for .custom.json files without rescanning)"
        )
        self._aw_btn_refresh.clicked.connect(self._aw_refresh_custom_status)
        toolbar.addWidget(self._aw_btn_refresh)

        layout.addLayout(toolbar)

        # ── Legend ─────────────────────────────────────────────────────
        lbl_legend = QLabel("Legend:  ❌ = No NVRAM Map  |  🟠 = Local .vpx found  |  ✅ = Custom Achievements configured")
        lbl_legend.setStyleSheet("color:#777; font-size:10px; padding:2px 4px;")
        layout.addWidget(lbl_legend)

        # ── Table widget ───────────────────────────────────────────────
        self._aw_tables_widget = QTableWidget(0, 7)
        self._aw_tables_widget.setHorizontalHeaderLabels(
            ["#", "Table Name", "ROM", "NVRAM Map", "Local", "Custom", "+"]
        )
        hh = self._aw_tables_widget.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self._aw_tables_widget.setColumnWidth(6, 36)
        self._aw_tables_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._aw_tables_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._aw_tables_widget.setStyleSheet(
            "QTableWidget { background:#111; color:#DDD; gridline-color:#333; }"
            "QHeaderView::section { background:#1a1a1a; color:#FF7F00; padding:4px;"
            " border-bottom:2px solid #555; }"
            "QTableWidget::item:selected { background:#3D2600; }"
        )
        self._aw_tables_widget.itemSelectionChanged.connect(self._aw_on_table_selected)
        layout.addWidget(self._aw_tables_widget, stretch=1)

        # ── Progress bar (hidden when not scanning) ────────────────────
        self._aw_progress_bar = QProgressBar()
        self._aw_progress_bar.setTextVisible(True)
        self._aw_progress_bar.setFixedHeight(14)
        self._aw_progress_bar.setStyleSheet(
            "QProgressBar { border:1px solid #444; border-radius:3px; background:#222;"
            " font-size:8pt; color:#E0E0E0; }"
            "QProgressBar::chunk { background:#FF7F00; border-radius:2px; }"
        )
        self._aw_progress_bar.hide()
        layout.addWidget(self._aw_progress_bar)

        # ── Scan status label ──────────────────────────────────────────
        self._aw_scan_status_lbl = QLabel("")
        self._aw_scan_status_lbl.setStyleSheet("color:#aaa; font-size:9pt;")
        layout.addWidget(self._aw_scan_status_lbl)

    def _aw_on_table_selected(self):
        """Store the selected .vpx filename when user clicks a row."""
        rows = self._aw_tables_widget.selectedItems()
        if not rows:
            self._aw_selected_table = ""
            return
        row = self._aw_tables_widget.currentRow()
        item = self._aw_tables_widget.item(row, 1)  # Table Name column
        if item:
            fname = item.data(Qt.ItemDataRole.UserRole) or ""
            self._aw_selected_table = fname
            self._aw_status_lbl.setText(f"Selected: {fname}")
            stem = os.path.splitext(fname)[0]
            self._aw_codes_table_lbl.setText(f"📌 Selected Table: {stem}")

    # ------------------------------------------------------------------
    # Sub-tab 2 – Codes
    # ------------------------------------------------------------------

    def _build_aw_subtab_codes(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Selected table label ──────────────────────────────────────
        self._aw_codes_table_lbl = QLabel(
            "📌 No table selected – go to Tables tab and click +"
        )
        self._aw_codes_table_lbl.setStyleSheet(
            "QLabel { color:#FF7F00; font-size:11pt; font-weight:bold;"
            " background:#1a1a1a; border:1px solid #333; border-radius:4px;"
            " padding:5px 10px; }"
        )
        self._aw_codes_table_lbl.setWordWrap(True)
        layout.addWidget(self._aw_codes_table_lbl)

        # ── Analyze button ────────────────────────────────────────────
        self._aw_btn_analyze = QPushButton("🔍 Analyze Script")
        self._aw_btn_analyze.setStyleSheet(self._aw_btn_style())
        self._aw_btn_analyze.setToolTip(
            "Extract the VBScript from the selected table and detect common event Subs"
        )
        self._aw_btn_analyze.clicked.connect(self._aw_analyze_script)
        layout.addWidget(self._aw_btn_analyze)

        # ── Auto-Select button ────────────────────────────────────────
        self._aw_btn_auto_select = QPushButton("⚡ Auto-Select for Option C")
        self._aw_btn_auto_select.setStyleSheet(
            "QPushButton { background-color:#1a2a1a; color:#88CC88;"
            " font-weight:bold; border-radius:5px; padding:4px 12px; border:1px solid #88CC88; }"
            "QPushButton:hover { background-color:#88CC88; color:#000000; }"
        )
        self._aw_btn_auto_select.setToolTip(
            "Automatically check all meaningful events and fill in context-aware achievement titles"
            " based on the table name.\n"
            "Skips: drain, tilt, slingshot, bumper hits, spinners and startup-firing subs.\n"
            "Run '🔍 Analyze Script' first."
        )
        self._aw_btn_auto_select.clicked.connect(self._aw_auto_select_for_option_c)
        layout.addWidget(self._aw_btn_auto_select)

        # ── Detected events group ─────────────────────────────────────
        grp_detected = QGroupBox("📋 Detected Events in Table Script")
        grp_detected.setStyleSheet(self._aw_groupbox_style())
        detected_layout = QVBoxLayout(grp_detected)

        scroll_det = QScrollArea()
        scroll_det.setWidgetResizable(True)
        scroll_det.setMinimumHeight(140)
        scroll_det.setStyleSheet("QScrollArea { border: none; background: #181818; }")

        self._aw_detected_container = QWidget()
        self._aw_detected_container.setStyleSheet("background:#181818;")
        self._aw_detected_vbox = QVBoxLayout(self._aw_detected_container)
        self._aw_detected_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._aw_detected_vbox.setSpacing(3)

        self._aw_no_events_lbl = QLabel(
            "<i style='color:#666;'>Select a table in the Tables tab, then click '🔍 Analyze Script'.</i>"
        )
        self._aw_detected_vbox.addWidget(self._aw_no_events_lbl)

        scroll_det.setWidget(self._aw_detected_container)
        detected_layout.addWidget(scroll_det)
        layout.addWidget(grp_detected, stretch=1)

        # ── Custom achievements group ──────────────────────────────────
        grp_custom = QGroupBox("✏️ Custom Achievements")
        grp_custom.setStyleSheet(self._aw_groupbox_style())
        custom_outer = QVBoxLayout(grp_custom)

        self._aw_btn_add = QPushButton("+ Add Achievement")
        self._aw_btn_add.setStyleSheet(self._aw_btn_style())
        self._aw_btn_add.setToolTip(
            "Add a new custom achievement row with title, description and event name"
        )
        self._aw_btn_add.clicked.connect(lambda: self._aw_add_row())
        custom_outer.addWidget(self._aw_btn_add)

        scroll_cust = QScrollArea()
        scroll_cust.setWidgetResizable(True)
        scroll_cust.setMinimumHeight(120)
        scroll_cust.setMaximumHeight(240)
        scroll_cust.setStyleSheet("QScrollArea { border: none; background: #181818; }")

        self._aw_rows_container = QWidget()
        self._aw_rows_container.setStyleSheet("background:#181818;")
        self._aw_rows_vbox = QVBoxLayout(self._aw_rows_container)
        self._aw_rows_vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._aw_rows_vbox.setSpacing(5)

        scroll_cust.setWidget(self._aw_rows_container)
        custom_outer.addWidget(scroll_cust)
        layout.addWidget(grp_custom)

        # Internal state for row lists
        self._aw_custom_rows: list[dict] = []
        self._aw_detected_rows: list[dict] = []

        # ── Bottom row: Export + Status ───────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#333;")
        layout.addWidget(sep2)

        btn_row = QHBoxLayout()
        self._aw_btn_export = QPushButton("💾 Export VBS + JSON")
        self._aw_btn_export.setStyleSheet(
            f"QPushButton {{ background-color:{get_theme_color(self.cfg, 'primary')}; color:#000000;"
            " font-weight:bold; border-radius:5px; padding:5px 12px; border:none; }"
            f"QPushButton:hover {{ background-color:{get_theme_color(self.cfg, 'accent')}; }}"
        )
        self._aw_btn_export.setToolTip(
            "Export the VBS trigger script and JSON achievement definitions to the AWEditor folder"
        )
        self._aw_btn_export.clicked.connect(self._aw_export)
        btn_row.addWidget(self._aw_btn_export)

        self._aw_btn_export_full = QPushButton("⚡ Export Full Script")
        self._aw_btn_export_full.setStyleSheet(
            "QPushButton { background-color: #1a3a1a; color: #88CC88;"
            " font-weight:bold; border-radius:5px; padding:5px 12px; border: 1px solid #88CC88; }"
            "QPushButton:hover { background-color: #88CC88; color: #000000; }"
        )
        self._aw_btn_export_full.setToolTip(
            "Export the complete table script with FireAchievement calls inserted automatically. "
            "Saves as {TableName}.vbs – VPX loads it instead of the built-in script. "
            "⚠ Does NOT support Custom Achievements."
        )
        self._aw_btn_export_full.clicked.connect(self._aw_export_full_script)
        btn_row.addWidget(self._aw_btn_export_full)

        btn_row.addStretch(1)

        self._aw_status_lbl = QLabel("")
        self._aw_status_lbl.setStyleSheet("color:#aaa; font-size:9pt;")
        btn_row.addWidget(self._aw_status_lbl)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Styling helpers
    # ------------------------------------------------------------------

    def _aw_btn_style(self) -> str:
        primary = get_theme_color(self.cfg, "primary")
        accent  = get_theme_color(self.cfg, "accent")
        return (
            f"QPushButton {{ background-color:{primary}; color:#000000;"
            " font-weight:bold; border-radius:4px; padding:4px 10px; border:none; }"
            f"QPushButton:hover {{ background-color:{accent}; }}"
        )

    def _aw_groupbox_style(self) -> str:
        accent = get_theme_color(self.cfg, "accent")
        return (
            "QGroupBox { background:#141414; border:1px solid #333; border-radius:6px;"
            " margin-top:8px; font-weight:bold; color:#E0E0E0; }"
            f"QGroupBox::title {{ subcontrol-origin:margin; left:10px; color:{accent}; }}"
        )

    def _aw_lineedit_style(self, invalid: bool = False) -> str:
        border = "#cc3333" if invalid else "#444"
        return (
            f"QLineEdit {{ background:#2a2a2a; color:#E0E0E0; border:1px solid {border};"
            " border-radius:3px; padding:2px 5px; }"
        )

    # ------------------------------------------------------------------
    # Table scan
    # ------------------------------------------------------------------

    def _aw_scan_tables(self):
        self._aw_scan_manual = True
        self._aw_btn_scan.setEnabled(False)
        self._aw_btn_scan.setText("⏳")
        self._aw_scan_status_lbl.setText("Scanning tables…")
        self._aw_progress_bar.setValue(0)
        self._aw_progress_bar.setMaximum(0)  # indeterminate until we know the total
        self._aw_progress_bar.show()
        worker = _ScanTablesWorker(self.cfg, parent=self)
        worker.progress.connect(self._aw_on_scan_progress)
        worker.finished.connect(self._aw_on_scan_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        # Keep a reference so the thread is not garbage-collected
        self._aw_scan_worker = worker

    def _aw_refresh_custom_status(self):
        """Refresh the Custom column by re-checking .custom.json files without rescanning."""
        self._aw_filter_tables()
        self._aw_scan_status_lbl.setText("✅ Custom status refreshed.")

    def _aw_on_scan_progress(self, current: int, total: int):
        """Update the progress bar and status label during a scan."""
        if total > 0:
            self._aw_progress_bar.setMaximum(total)
            self._aw_progress_bar.setValue(current)
        self._aw_scan_status_lbl.setText(f"Scanning tables… ({current}/{total})")

    def _aw_on_scan_done(self, tables: list[dict]):
        self._aw_progress_bar.hide()

        # Detect tables that were cached before but now have a map (disappeared)
        old_filenames = {entry.get("filename", "") for entry in self._aw_all_tables}
        new_filenames = {entry.get("filename", "") for entry in tables}
        removed = old_filenames - new_filenames

        is_manual = getattr(self, "_aw_scan_manual", False)
        if is_manual:
            # Popup will convey the result — clear the status label instead of duplicating
            self._aw_scan_status_lbl.setText("")
        elif removed and old_filenames:
            # Show names without extension for readability
            removed_names = ", ".join(
                sorted(os.path.splitext(f)[0] for f in removed)
            )
            count = len(removed)
            self._aw_scan_status_lbl.setText(
                f"ℹ️ {count} table(s) now have NVRAM maps and were removed: {removed_names}"
            )
        elif tables:
            self._aw_scan_status_lbl.setText(f"Found {len(tables)} table(s).")
        else:
            self._aw_scan_status_lbl.setText(
                "No Non-ROM tables found. Check Tables directory in System tab."
            )

        self._aw_all_tables = tables
        self._aw_filter_tables()
        self._aw_btn_scan.setEnabled(True)
        self._aw_btn_scan.setText("🔄 Scan")
        self._aw_save_cache(tables)

        # Show a popup only for manual scans (not for startup/cache loads)
        if getattr(self, "_aw_scan_manual", False):
            self._aw_scan_manual = False
            from PyQt6.QtWidgets import QMessageBox
            lines = []
            if tables:
                lines.append(f"✅ {len(tables)} table(s) found without NVRAM map.")
            else:
                lines.append("No non-ROM tables found without NVRAM map.")
            if removed and old_filenames:
                removed_names = ", ".join(
                    sorted(os.path.splitext(f)[0] for f in removed)
                )
                lines.append(
                    f"ℹ️ {len(removed)} table(s) now have NVRAM maps and were removed: {removed_names}"
                )
            QMessageBox.information(self, "Scan Results", "\n".join(lines))

    def _aw_filter_tables(self):
        """Filter the table list by the current search text and repopulate the widget."""
        query = self._aw_search.text().lower()

        filtered = []
        for entry in self._aw_all_tables:
            fname = entry.get("filename", "")
            rom = entry.get("rom", "")
            stem = os.path.splitext(fname)[0].lower()
            if query and query not in stem and query not in rom.lower():
                continue
            filtered.append(entry)

        self._aw_tables_widget.setRowCount(0)
        self._aw_tables_widget.setRowCount(len(filtered))

        for row, entry in enumerate(filtered):
            fname = entry.get("filename", "")
            stem = os.path.splitext(fname)[0]
            rom = entry.get("rom", "")
            is_local = entry.get("is_local", False)

            def _make_item(text, color=None, align=None):
                it = QTableWidgetItem(text)
                if color:
                    it.setForeground(QColor(color))
                if align:
                    it.setTextAlignment(align)
                return it

            num_item = _make_item(str(row + 1), "#888", Qt.AlignmentFlag.AlignCenter)
            self._aw_tables_widget.setItem(row, 0, num_item)

            name_item = _make_item(stem)
            name_item.setData(Qt.ItemDataRole.UserRole, fname)
            self._aw_tables_widget.setItem(row, 1, name_item)

            self._aw_tables_widget.setItem(row, 2, _make_item(rom, "#888" if rom else "#555"))
            self._aw_tables_widget.setItem(
                row, 3,
                _make_item("❌", "#555", Qt.AlignmentFlag.AlignCenter),
            )
            self._aw_tables_widget.setItem(
                row, 4,
                _make_item("🟠" if is_local else "", align=Qt.AlignmentFlag.AlignCenter),
            )

            # Check if a .custom.json exists for this table
            custom_json_path = os.path.join(p_aweditor(self.cfg), f"{stem}.custom.json")
            has_custom = os.path.isfile(custom_json_path)
            self._aw_tables_widget.setItem(
                row, 5,
                _make_item("✅" if has_custom else "", align=Qt.AlignmentFlag.AlignCenter),
            )

            # "+" button – click to select table and switch to Codes sub-tab
            btn_plus = QPushButton("+")
            btn_plus.setFixedSize(28, 24)
            btn_plus.setToolTip("Select this table and open the Codes tab")
            btn_plus.setStyleSheet(
                "QPushButton { background-color:#1a1a1a; color:#FF7F00; border:1px solid #FF7F00;"
                " border-radius:3px; font-size:11pt; font-weight:bold; padding:0; }"
                "QPushButton:hover { background-color:#FF7F00; color:#000000; }"
            )

            def _make_plus_handler(filename: str, table_stem: str):
                def _handler():
                    self._aw_selected_table = filename
                    self._aw_status_lbl.setText(f"Selected: {filename}")
                    self._aw_codes_table_lbl.setText(f"📌 Selected Table: {table_stem}")
                    self._aw_inner_tabs.setCurrentIndex(1)
                return _handler

            btn_plus.clicked.connect(_make_plus_handler(fname, stem))
            self._aw_tables_widget.setCellWidget(row, 6, btn_plus)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _aw_cache_path(self) -> str:
        return os.path.join(p_aweditor(self.cfg), "aweditor_scan_cache.json")

    def _aw_load_cache(self) -> list[dict] | None:
        """Return the cached table list if it matches the current tables_dir, else None."""
        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        try:
            with open(self._aw_cache_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("tables_dir") == tables_dir and isinstance(data.get("results"), list):
                results = data["results"]
                # Normalize: accept both old format (list of str) and new format (list of dict),
                # including mixed caches from partial migrations or corruption.
                normalized: list[dict] = []
                for r in results:
                    if isinstance(r, str):
                        normalized.append(
                            {"filename": r, "rom": "", "has_map": False, "is_local": True}
                        )
                    elif isinstance(r, dict):
                        normalized.append(r)
                return normalized
        except Exception:
            pass
        return None

    def _aw_save_cache(self, tables: list[dict]) -> None:
        """Persist scan results to the cache file."""
        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        path = self._aw_cache_path()
        try:
            ensure_dir(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "tables_dir": tables_dir,
                        "results": tables,
                        "cached_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception:
            pass

    def _aw_init_tables(self) -> None:
        """On startup: populate the table list from cache if available, else wait for manual scan."""
        cached = self._aw_load_cache()
        if cached is not None:
            self._aw_all_tables = cached
            self._aw_filter_tables()
            if cached:
                self._aw_scan_status_lbl.setText(f"Found {len(cached)} table(s) (cached).")
            else:
                self._aw_scan_status_lbl.setText(
                    "No tables found in cache. Click '🔄 Scan' to search for tables without NVRAM map."
                )
        else:
            self._aw_scan_status_lbl.setText(
                "Click '🔄 Scan' to search for tables without NVRAM map."
            )

    # ------------------------------------------------------------------
    # Script analysis
    # ------------------------------------------------------------------

    def _aw_analyze_script(self):
        fname = self._aw_selected_table
        if not fname:
            self._aw_status_lbl.setText("⚠ Please select a table in the Tables tab first.")
            return

        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        if not tables_dir:
            self._aw_status_lbl.setText("⚠ Tables directory not configured.")
            return

        vpx_path = os.path.join(tables_dir, fname)
        if not os.path.isfile(vpx_path):
            self._aw_status_lbl.setText(f"⚠ File not found: {vpx_path}")
            return

        self._aw_btn_analyze.setEnabled(False)
        self._aw_status_lbl.setText("Analyzing script…")

        worker = _AnalyzeScriptWorker(self.cfg, vpx_path, parent=self)
        worker.finished.connect(self._aw_on_analyze_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self._aw_analyze_worker = worker

    def _aw_on_analyze_done(self, findings: list):
        # Clear previous
        while self._aw_detected_vbox.count():
            item = self._aw_detected_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._aw_detected_rows.clear()

        if not findings:
            lbl = QLabel("<i style='color:#666;'>No common events detected in the script.</i>")
            self._aw_detected_vbox.addWidget(lbl)
            self._aw_status_lbl.setText("Analysis complete. No known events found.")
        else:
            # Group findings by category
            _CATEGORY_ORDER = [
                ("missions_modes", "🎯 Missions & Modes"),
                ("mechanics",      "🎮 Game Mechanics"),
                ("basics",         "⚙️ Basic Events"),
                ("body",           "🔍 Body Analysis"),
            ]
            grouped: dict[str, list] = {cat: [] for cat, _ in _CATEGORY_ORDER}
            for finding in findings:
                # Support both 5-element (legacy) and 6-element tuples
                if len(finding) == 6:
                    title, sub_name, lineno, event_name, default_checked, category = finding
                else:
                    title, sub_name, lineno, event_name, default_checked = finding
                    category = _event_category(event_name)
                grouped[category].append((title, sub_name, lineno, event_name, default_checked))

            for cat_key, cat_label in _CATEGORY_ORDER:
                items = grouped.get(cat_key, [])
                if not items:
                    continue

                # Category header label
                hdr = QLabel(f"<b style='color:#FF7F00;'>{cat_label}</b>")
                hdr.setStyleSheet("background:transparent; padding:4px 2px 1px 2px;")
                self._aw_detected_vbox.addWidget(hdr)

                for title, sub_name, lineno, event_name, default_checked in items:
                    fires_on_load = bool(_STARTUP_SUB_RE.search(sub_name))

                    row_w = QWidget()
                    row_w.setStyleSheet("background:transparent;")
                    row_h = QHBoxLayout(row_w)
                    row_h.setContentsMargins(4, 2, 4, 2)

                    chk = QCheckBox()
                    # Uncheck by default if this sub is known to fire on table load
                    chk.setChecked(default_checked and not fires_on_load)
                    chk.setStyleSheet("QCheckBox { color:#E0E0E0; }")
                    chk.setToolTip("Check to include this event as an achievement trigger")
                    row_h.addWidget(chk)

                    if fires_on_load:
                        warn_suffix = (
                            f"<span style='color:#FF8800; font-size:0.9em;'>"
                            f" ⚠️ fires on table load</span>"
                        )
                    else:
                        warn_suffix = ""

                    lbl = QLabel(
                        f"<span style='color:#E0E0E0; font-weight:bold;'>{title}</span>"
                        f"<span style='color:#888;'> → Sub {sub_name}()</span>"
                        f"<span style='color:#555;'>  Ln {lineno}</span>"
                        f"{warn_suffix}"
                    )
                    lbl.setStyleSheet("background:transparent;")
                    row_h.addWidget(lbl, stretch=1)

                    title_edit = QLineEdit(title)
                    title_edit.setPlaceholderText("Achievement title for toast")
                    title_edit.setStyleSheet(self._aw_lineedit_style())
                    title_edit.setToolTip(
                        "Customize the achievement title shown in the toast notification (line 1)"
                    )
                    title_edit.setMaximumWidth(200)
                    row_h.addWidget(title_edit)

                    self._aw_detected_vbox.addWidget(row_w)
                    self._aw_detected_rows.append({
                        "chk":        chk,
                        "title":      title,
                        "title_edit": title_edit,
                        "sub":        sub_name,
                        "lineno":     lineno,
                        "event":      event_name,
                    })

            self._aw_status_lbl.setText(f"Found {len(findings)} event(s).")

        self._aw_btn_analyze.setEnabled(True)

    # ------------------------------------------------------------------
    # Custom achievement rows
    # ------------------------------------------------------------------

    def _aw_auto_select_for_option_c(self):
        """Check all meaningful detected events and fill in context-aware achievement titles."""
        if not self._aw_detected_rows:
            self._aw_status_lbl.setText("⚠ No detected events. Run 'Analyze Script' first.")
            return

        keyword = _extract_table_keyword(self._aw_selected_table or "")

        checked_count = 0
        for row in self._aw_detected_rows:
            event_name = row["event"]
            sub_name = row["sub"]

            # Never check startup-firing subs
            if _STARTUP_SUB_RE.search(sub_name):
                row["chk"].setChecked(False)
                continue

            # Skip noise events
            if event_name in _AUTO_SELECT_SKIP_EVENTS:
                row["chk"].setChecked(False)
                continue

            # Check it
            row["chk"].setChecked(True)
            checked_count += 1

            # Build context-aware title
            base_title = row["title"]
            if keyword and keyword.lower() not in base_title.lower():
                new_title = f"{keyword} {base_title}"
            else:
                new_title = base_title

            row["title_edit"].setText(new_title)

        self._aw_status_lbl.setText(
            f"✅ Auto-selected {checked_count} event(s) for Option C."
        )

    def _aw_add_row(self, title: str = "", desc: str = "", event: str = ""):
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background:#1e1e1e; border:1px solid #333; border-radius:4px; }"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(6)

        lbl_t = QLabel("🏆 Title:")
        lbl_t.setStyleSheet("color:#aaa; background:transparent; border:none;")
        h.addWidget(lbl_t)

        ed_title = QLineEdit(title)
        ed_title.setPlaceholderText("e.g. Ramp Combo King")
        ed_title.setStyleSheet(self._aw_lineedit_style())
        ed_title.setToolTip("Achievement title shown in the toast notification")
        h.addWidget(ed_title, stretch=2)

        lbl_d = QLabel("📝 Desc:")
        lbl_d.setStyleSheet("color:#aaa; background:transparent; border:none;")
        h.addWidget(lbl_d)

        ed_desc = QLineEdit(desc)
        ed_desc.setPlaceholderText("e.g. Hit 5 ramps in a row")
        ed_desc.setStyleSheet(self._aw_lineedit_style())
        ed_desc.setToolTip("Short description of how to unlock this achievement")
        h.addWidget(ed_desc, stretch=2)

        lbl_e = QLabel("🎯 Event:")
        lbl_e.setStyleSheet("color:#aaa; background:transparent; border:none;")
        h.addWidget(lbl_e)

        ed_event = QLineEdit(event)
        ed_event.setPlaceholderText("e.g. ramp_combo_5x")
        ed_event.setStyleSheet(self._aw_lineedit_style())
        ed_event.setToolTip("Unique event identifier (lowercase, a-z, 0-9, underscores only)")
        ed_event.setMaximumWidth(160)
        h.addWidget(ed_event)

        # Validate event name on text change
        def _validate():
            txt = ed_event.text()
            invalid = bool(txt) and not re.fullmatch(r"[a-z0-9_]+", txt)
            ed_event.setStyleSheet(self._aw_lineedit_style(invalid))

        ed_event.textChanged.connect(_validate)

        btn_rm = QPushButton("🗑️")
        btn_rm.setFixedSize(30, 26)
        btn_rm.setToolTip("Remove this achievement")
        btn_rm.setStyleSheet(
            "QPushButton { background-color:#3a1a1a; color:#cc3333; border:1px solid #cc3333;"
            " border-radius:4px; font-size:10pt; font-weight:bold; padding:0; }"
            "QPushButton:hover { background-color:#cc3333; color:#ffffff; }"
        )

        row_dict = {"title": ed_title, "desc": ed_desc, "event": ed_event, "frame": frame}
        self._aw_custom_rows.append(row_dict)

        def _remove():
            self._aw_rows_vbox.removeWidget(frame)
            frame.deleteLater()
            if row_dict in self._aw_custom_rows:
                self._aw_custom_rows.remove(row_dict)

        btn_rm.clicked.connect(_remove)
        h.addWidget(btn_rm)

        self._aw_rows_vbox.addWidget(frame)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _aw_export(self):
        fname = self._aw_selected_table
        if not fname:
            self._aw_status_lbl.setText("⚠ No table selected. Pick one in the Tables tab.")
            return

        table_stem = os.path.splitext(fname)[0]  # e.g. "JP_JurassicPark_VPW"

        # Collect detected events that are checked
        rules: list[dict] = []
        for row in self._aw_detected_rows:
            if row["chk"].isChecked():
                custom_title = row["title_edit"].text().strip()
                if not custom_title:
                    custom_title = row["title"]
                rules.append({
                    "title":       custom_title + "!",
                    "description": f"Trigger: {row['sub']}()",
                    "condition":   {"type": "event", "event": row["event"]},
                })

        # Collect custom achievement rows
        for row in self._aw_custom_rows:
            t  = row["title"].text().strip()
            d  = row["desc"].text().strip()
            ev = row["event"].text().strip()
            if not t or not ev:
                continue
            if not re.fullmatch(r"[a-z0-9_]+", ev):
                self._aw_status_lbl.setText(f"⚠ Invalid event name: '{ev}' – use only a-z, 0-9, _")
                return
            rules.append({
                "title":       t,
                "description": d,
                "condition":   {"type": "event", "event": ev},
            })

        if not rules:
            self._aw_status_lbl.setText("⚠ No achievements selected. Add or check some first.")
            return

        out_dir = p_aweditor(self.cfg)
        ensure_dir(out_dir)
        ensure_dir(p_custom_events(self.cfg))

        # ── Write JSON ────────────────────────────────────────────────
        json_name = f"{table_stem}.custom.json"
        json_path = os.path.join(out_dir, json_name)
        payload = {
            "table_file": fname,
            "rules": rules,
        }
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not write JSON: {e}")
            return

        # ── Write VBS ─────────────────────────────────────────────────
        vbs_name = f"aw_{table_stem}.vbs"
        vbs_path = os.path.join(out_dir, vbs_name)

        # VBScript paths need backslashes; events_path_vbs is the fallback if config read fails
        events_path_vbs = p_custom_events(self.cfg).replace("/", "\\").rstrip("\\") + "\\"
        config_path_vbs = CONFIG_FILE.replace("/", "\\")

        # Build comment lines for detected events
        detected_lines: list[str] = []
        for row in self._aw_detected_rows:
            if row["chk"].isChecked():
                detected_lines.append(
                    f'\'   FireAchievement "{row["event"]}"'
                    f'        → Add to Sub {row["sub"]}()'
                    f'    Line {row["lineno"]}'
                )

        # Build comment lines for custom events
        custom_lines: list[str] = []
        for row in self._aw_custom_rows:
            ev = row["event"].text().strip()
            t  = row["title"].text().strip()
            if ev and re.fullmatch(r"[a-z0-9_]+", ev):
                custom_lines.append(
                    f'\'   FireAchievement "{ev}"'
                    f'    → Your custom event ({t})'
                )

        detected_block = "\n".join(detected_lines) if detected_lines else "\'   (none selected)"
        custom_block   = "\n".join(custom_lines)   if custom_lines   else "\'   (none defined)"

        vbs_content = f"""\
' ═══════════════════════════════════════════════════════════════════
'   VPX Achievement Watcher – Custom Achievement Triggers
'   Table: {fname}
'   Generated by AWEditor
'
'   INSTALLATION:
'   1. Copy this file next to your .vpx table file
'   2. Open the table in VPX Editor (File > Open)
'   3. Open Script Editor (View > Script or F12)
'   4. Add these lines near the top of your table script:
'        On Error Resume Next
'        ExecuteGlobal GetTextFile("aw_{table_stem}.vbs")
'        On Error GoTo 0
'   5. For custom achievements, add FireAchievement calls
'      at the appropriate places (see comments below)
'
'   ⚠️  IMPORTANT: Do NOT rename this file to {table_stem}.vbs !
'   If the .vbs has the same base name as the .vpx, VPX will
'   REPLACE the entire table script and completely break the table.
'   The "aw_" prefix keeps this file additive (loaded via ExecuteGlobal GetTextFile).
' ═══════════════════════════════════════════════════════════════════

Dim AW_EventPath, AW_Installed

' Locates the custom_events folder at runtime.
' Priority: 1. Registry  2. config.json  3. Hardcoded fallback (path at export time)
Sub AW_InitEventPath()
    On Error Resume Next
    AW_Installed = False
    AW_EventPath = ""

    ' --- 1. Registry ---
    Dim sh
    Set sh = CreateObject("WScript.Shell")
    Dim regVal
    regVal = sh.RegRead("HKCU\\Software\\VPX Achievement Watcher\\EventsPath")
    Set sh = Nothing
    If Err.Number = 0 And regVal <> "" Then
        AW_EventPath = regVal
        AW_Installed = True
        On Error GoTo 0
        Exit Sub
    End If
    Err.Clear

    ' --- 2. config.json ---
    Dim fso, f, txt, p1, p2, base
    Dim q : q = Chr(34)
    Set fso = CreateObject("Scripting.FileSystemObject")
    If fso.FileExists("{config_path_vbs}") Then
        Set f = fso.OpenTextFile("{config_path_vbs}", 1)
        txt = f.ReadAll
        f.Close
        Set f = Nothing
        p1 = InStr(txt, q & "BASE" & q & ": " & q)
        If p1 > 0 Then
            p1 = p1 + Len(q & "BASE" & q & ": " & q)
            p2 = InStr(p1, txt, q)
            If p2 > 0 Then
                base = Mid(txt, p1, p2 - p1)
                base = Replace(base, "\\\\", "\\")
                AW_EventPath = base & "\\tools\\AWeditor\\custom_events\\"
                AW_Installed = True
                Set fso = Nothing
                On Error GoTo 0
                Exit Sub
            End If
        End If
    End If
    Set fso = Nothing

    ' --- 3. Hardcoded fallback (path at export time) ---
    AW_EventPath = "{events_path_vbs}"
    On Error GoTo 0
End Sub

AW_InitEventPath

Sub FireAchievement(eventName)
    ' If Achievement Watcher is not installed, do nothing silently
    If Not AW_Installed Then Exit Sub
    On Error Resume Next
    Dim fso, f
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set f = fso.CreateTextFile(AW_EventPath & eventName & ".trigger", True)
    f.WriteLine eventName
    f.WriteLine Now
    f.Close
    Set f = Nothing
    Set fso = Nothing
    On Error GoTo 0
End Sub

' ── Auto-Detected Events ─────────────────────────────────────────
' These are called when specific Subs in your table execute.
' The FireAchievement calls below need to be placed inside the
' corresponding Subs in your table script.
'
{detected_block}

' ── Custom Events ─────────────────────────────────────────────────
' Place these calls where the event happens in your table script:
'
{custom_block}
"""

        try:
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(vbs_content)
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not write VBS: {e}")
            return

        # ── Write README ──────────────────────────────────────────────
        readme_name = f"README_aw_{table_stem}.txt"
        readme_path = os.path.join(out_dir, readme_name)

        # Build detected-event trigger examples for the README
        readme_detected_lines: list[str] = []
        for row in self._aw_detected_rows:
            if row["chk"].isChecked():
                readme_detected_lines.append(
                    f'  Sub {row["sub"]}()    \' Line {row["lineno"]}\n'
                    f'      \' ... existing code ...\n'
                    f'      FireAchievement "{row["event"]}"    \' <-- Add this line\n'
                    f'  End Sub'
                )

        # Build custom-event list for the README
        readme_custom_lines: list[str] = []
        for row in self._aw_custom_rows:
            ev = row["event"].text().strip()
            t  = row["title"].text().strip()
            if ev and re.fullmatch(r"[a-z0-9_]+", ev):
                readme_custom_lines.append(
                    f'  FireAchievement "{ev}"'
                    + (f'    \' {t}' if t else "")
                )

        sep = "═" * 67

        if readme_detected_lines:
            detected_section = "\n\n".join(readme_detected_lines)
        else:
            detected_section = "  (no detected events were selected)"

        if readme_custom_lines:
            custom_section = "\n".join(readme_custom_lines)
        else:
            custom_section = "  (none defined)"

        readme_content = (
            f"{sep}\n"
            f"  VPX Achievement Watcher \u2013 Custom Achievement Setup\n"
            f"  Table: {fname}\n"
            f"  Generated by AWEditor\n"
            f"{sep}\n"
            f"\n"
            f"INSTALLATION \u2013 TWO OPTIONS:\n"
            f"{'─' * 74}\n"
            f"\n"
            f"OPTION A \u2013 With separate .vbs file (standard):\n"
            f"  1. Copy \"{vbs_name}\" next to your .vpx file (into your Tables folder)\n"
            f"  2. Open the table in VPX Editor \u2192 F12 (Script Editor)\n"
            f"  3. Paste these 3 lines at the very TOP of your table script:\n"
            f"\n"
            f"     On Error Resume Next\n"
            f"     ExecuteGlobal GetTextFile(\"{vbs_name}\")\n"
            f"     On Error GoTo 0\n"
            f"\n"
            f"  4. Add FireAchievement calls at the appropriate places (see below)\n"
            f"\n"
            f"{'─' * 74}\n"
            f"\n"
            f"OPTION B \u2013 Inline (no extra file needed):\n"
            f"  Instead of the .vbs file, paste this block at the very TOP of your table script:\n"
            f"\n"
            f"  Dim AW_EventPath, AW_Installed\n"
            f"  Sub AW_Init()\n"
            f"      On Error Resume Next\n"
            f"      AW_Installed = False\n"
            f"      Dim sh : Set sh = CreateObject(\"WScript.Shell\")\n"
            f"      AW_EventPath = sh.RegRead(\"HKCU\\Software\\VPX Achievement Watcher\\EventsPath\")\n"
            f"      Set sh = Nothing\n"
            f"      AW_Installed = (Err.Number = 0 And AW_EventPath <> \"\")\n"
            f"      Err.Clear : On Error GoTo 0\n"
            f"  End Sub\n"
            f"  AW_Init\n"
            f"\n"
            f"  Sub FireAchievement(eventName)\n"
            f"      If Not AW_Installed Then Exit Sub\n"
            f"      On Error Resume Next\n"
            f"      Dim fso, f\n"
            f"      Set fso = CreateObject(\"Scripting.FileSystemObject\")\n"
            f"      Set f = fso.CreateTextFile(AW_EventPath & eventName & \".trigger\", True)\n"
            f"      f.WriteLine eventName : f.WriteLine Now\n"
            f"      f.Close\n"
            f"      Set f = Nothing : Set fso = Nothing\n"
            f"      On Error GoTo 0\n"
            f"  End Sub\n"
            f"\n"
            f"  Then add FireAchievement calls at the appropriate places (see below).\n"
            f"  \u2705 No extra .vbs file needed\n"
            f"  \u2705 No error if Achievement Watcher is not installed\n"
            f"\n"
            f"{'─' * 74}\n"
            f"\n"
            f"OPTION C \u2013 Full Script Export (zero manual work):\n"
            f"  Use the \u26a1 Export Full Script button in AWEditor.\n"
            f"  AWEditor inserts all FireAchievement calls automatically.\n"
            f"  See README_aw_{table_stem}_optionC.txt for details.\n"
            f"\n"
            f"  \u26a0\ufe0f  CUSTOM ACHIEVEMENTS NOT SUPPORTED in Option C.\n"
            f"      \u2192 Use Option A or B if you need custom achievements.\n"
            f"\n"
            f"{'═' * 74}\n"
            f"\n"
            f"\u26a0\ufe0f  IMPORTANT: Do NOT rename the .vbs file to \"{table_stem}.vbs\"!\n"
            f"   If the .vbs has the same base name as the .vpx, VPX will REPLACE the entire\n"
            f"   table script and completely break the table.\n"
            f"   The \"aw_\" prefix keeps this file additive.\n"
            f"\n"
            f"\n"
            f"ACHIEVEMENT TRIGGERS TO ADD:\n"
            f"{'─' * 28}\n"
            f"{detected_section}\n"
            f"\n"
            f"\n"
            f"CUSTOM ACHIEVEMENTS:\n"
            f"{'─' * 20}\n"
            f"{custom_section}\n"
            f"\n"
            f"  Place these calls where the event happens in your table script:\n"
            f"    FireAchievement \"your_custom_event\"\n"
            f"\n"
            f"\n"
            f"FILES GENERATED:\n"
            f"{'─' * 16}\n"
            f"  \u2022 {vbs_name}    \u2192 Copy to Tables folder\n"
            f"  \u2022 {json_name} \u2192 Stays in AWEditor folder\n"
            f"  \u2022 {readme_name} \u2192 This file (instructions)\n"
            f"{sep}\n"
        )

        try:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(readme_content)
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not write README: {e}")
            return

        rel_out = os.path.relpath(out_dir, self.cfg.BASE) if hasattr(self.cfg, "BASE") else out_dir
        self._aw_status_lbl.setText(
            f"✅ Exported {vbs_name} + {json_name} + README \u2192 {rel_out}\n"
            "ℹ️ Custom achievements ≠ NVRAM map. Table stays in AWEditor list."
        )

    # ------------------------------------------------------------------
    # Option C – Full Script Export
    # ------------------------------------------------------------------

    def _aw_export_full_script(self):
        """Export the complete table script with FireAchievement calls inserted (Option C)."""
        fname = self._aw_selected_table
        if not fname:
            self._aw_status_lbl.setText("⚠ No table selected. Pick one in the Tables tab.")
            return

        # Guard: no detected events checked
        checked_detected = [r for r in self._aw_detected_rows if r["chk"].isChecked()]
        if not checked_detected:
            self._aw_status_lbl.setText(
                "⚠ No detected events selected. Use '🔍 Analyze Script' first and check at least one event."
            )
            return

        # Guard: custom achievements present
        if self._aw_custom_rows:
            mb = QMessageBox(self)
            mb.setWindowTitle("Option C \u2013 Custom Achievements Not Supported")
            mb.setText(
                "Option C (Full Script Export) does not support Custom Achievements.\n\n"
                "Custom achievements cannot be placed automatically because AWEditor does not know "
                "where in the script they should fire.\n\n"
                "Please use Option A or B if you need custom achievements.\n\n"
                "Do you want to continue with detected events only?"
            )
            mb.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            mb.setDefaultButton(QMessageBox.StandardButton.No)
            if mb.exec() != QMessageBox.StandardButton.Yes:
                return

        # Extract full script via vpxtool
        exe = ensure_vpxtool(self.cfg)
        if not exe:
            self._aw_status_lbl.setText("⚠ vpxtool not available.")
            return
        tables_dir = getattr(self.cfg, "TABLES_DIR", "") or ""
        vpx_path = os.path.join(tables_dir, fname)
        try:
            cp = subprocess.run(
                [exe, "script", "show", vpx_path],
                capture_output=True, text=True, timeout=30,
                creationflags=0x08000000,  # CREATE_NO_WINDOW – suppress console popup on Windows
                encoding="utf-8", errors="replace",
            )
            original_script = cp.stdout or ""
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not extract script: {e}")
            return
        if not original_script.strip():
            self._aw_status_lbl.setText("⚠ Could not extract script from table.")
            return

        # Insert FireAchievement calls into the script
        lines = original_script.splitlines()
        inject_map: dict[str, str] = {}
        for row in self._aw_detected_rows:
            if row["chk"].isChecked():
                inject_map[row["sub"].lower()] = row["event"]

        modified_lines: list[str] = []
        sub_def_re = re.compile(r'^(?:Public\s+|Private\s+)?Sub\s+([a-zA-Z0-9_]+)', re.IGNORECASE)
        for line in lines:
            modified_lines.append(line)
            m = sub_def_re.match(line.strip())
            if m and m.group(1).lower() in inject_map:
                event = inject_map[m.group(1).lower()]
                modified_lines.append(f'    FireAchievement "{event}"')

        modified_script = "\n".join(modified_lines)

        # VBScript-friendly paths for fallback path discovery (same as Option A)
        events_path_vbs = p_custom_events(self.cfg).replace("/", "\\").rstrip("\\") + "\\"
        config_path_vbs = CONFIG_FILE.replace("/", "\\")

        # Build AW-Init inline block (full 3-step path discovery, same as Option A)
        aw_init_block = (
            "' \u2500\u2500 VPX Achievement Watcher \u2013 Inline Integration "
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            "Dim AW_EventPath, AW_Installed\n"
            "\n"
            "' Locates the custom_events folder at runtime.\n"
            "' Priority: 1. Registry  2. config.json  3. Hardcoded fallback (path at export time)\n"
            "Sub AW_InitEventPath()\n"
            "    On Error Resume Next\n"
            "    AW_Installed = False\n"
            "    AW_EventPath = \"\"\n"
            "\n"
            "    ' --- 1. Registry ---\n"
            "    Dim sh\n"
            "    Set sh = CreateObject(\"WScript.Shell\")\n"
            "    Dim regVal\n"
            "    regVal = sh.RegRead(\"HKCU\\Software\\VPX Achievement Watcher\\EventsPath\")\n"
            "    Set sh = Nothing\n"
            "    If Err.Number = 0 And regVal <> \"\" Then\n"
            "        AW_EventPath = regVal\n"
            "        AW_Installed = True\n"
            "        On Error GoTo 0\n"
            "        Exit Sub\n"
            "    End If\n"
            "    Err.Clear\n"
            "\n"
            "    ' --- 2. config.json ---\n"
            "    Dim fso, f, txt, p1, p2, base\n"
            "    Dim q : q = Chr(34)\n"
            "    Set fso = CreateObject(\"Scripting.FileSystemObject\")\n"
            f"    If fso.FileExists(\"{config_path_vbs}\") Then\n"
            f"        Set f = fso.OpenTextFile(\"{config_path_vbs}\", 1)\n"
            "        txt = f.ReadAll\n"
            "        f.Close\n"
            "        Set f = Nothing\n"
            "        p1 = InStr(txt, q & \"BASE\" & q & \": \" & q)\n"
            "        If p1 > 0 Then\n"
            "            p1 = p1 + Len(q & \"BASE\" & q & \": \" & q)\n"
            "            p2 = InStr(p1, txt, q)\n"
            "            If p2 > 0 Then\n"
            "                base = Mid(txt, p1, p2 - p1)\n"
            "                ' Convert JSON-escaped backslashes (\\\\) to single backslashes for VBScript paths\n"
            "                base = Replace(base, \"\\\\\", \"\\\")\n"
            "                AW_EventPath = base & \"\\tools\\AWeditor\\custom_events\\\"\n"
            "                AW_Installed = True\n"
            "                Set fso = Nothing\n"
            "                On Error GoTo 0\n"
            "                Exit Sub\n"
            "            End If\n"
            "        End If\n"
            "    End If\n"
            "    Set fso = Nothing\n"
            "\n"
            "    ' --- 3. Hardcoded fallback (path at export time) ---\n"
            f"    AW_EventPath = \"{events_path_vbs}\"\n"
            "    On Error GoTo 0\n"
            "End Sub\n"
            "\n"
            "AW_InitEventPath\n"
            "\n"
            "Sub FireAchievement(eventName)\n"
            "    ' If Achievement Watcher is not installed, do nothing silently\n"
            "    If Not AW_Installed Then Exit Sub\n"
            "    On Error Resume Next\n"
            "    Dim fso, f\n"
            "    Set fso = CreateObject(\"Scripting.FileSystemObject\")\n"
            "    Set f = fso.CreateTextFile(AW_EventPath & eventName & \".trigger\", True)\n"
            "    f.WriteLine eventName\n"
            "    f.WriteLine Now\n"
            "    f.Close\n"
            "    Set f = Nothing\n"
            "    Set fso = Nothing\n"
            "    On Error GoTo 0\n"
            "End Sub\n"
            "' \u2500\u2500 End Achievement Watcher \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
        )

        # Smart insertion: place AW-Init block AFTER leading Option Explicit / Randomize /
        # blank lines / comments so that VBScript's Option Explicit remains first.
        ms_lines = modified_script.splitlines()
        insert_pos = 0
        for i, ln in enumerate(ms_lines):
            stripped = ln.strip()
            if (
                stripped == ""
                or stripped.lower().startswith("option explicit")
                or stripped.lower().startswith("randomize")
                or stripped.startswith("'")
            ):
                insert_pos = i + 1
            else:
                break

        leading = "\n".join(ms_lines[:insert_pos])
        remaining = "\n".join(ms_lines[insert_pos:])
        if leading:
            full_script = leading + "\n\n" + aw_init_block + "\n\n" + remaining
        else:
            full_script = aw_init_block + "\n\n" + remaining

        table_stem = os.path.splitext(fname)[0]
        out_dir = p_aweditor(self.cfg)
        ensure_dir(out_dir)

        # Write {table_stem}.vbs into the Tables folder (next to the .vpx)
        vbs_name = f"{table_stem}.vbs"
        vbs_path = os.path.join(tables_dir, vbs_name)
        try:
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(full_script)
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not write VBS: {e}")
            return

        # Write {table_stem}.custom.json (detected events only)
        json_name = f"{table_stem}.custom.json"
        json_path = os.path.join(out_dir, json_name)
        rules: list[dict] = []
        for row in self._aw_detected_rows:
            if row["chk"].isChecked():
                custom_title = row["title_edit"].text().strip()
                if not custom_title:
                    custom_title = row["title"]
                rules.append({
                    "title":       custom_title + "!",
                    "description": f"Trigger: {row['sub']}()",
                    "condition":   {"type": "event", "event": row["event"]},
                })
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"table_file": fname, "rules": rules}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not write JSON: {e}")
            return

        # Write Option C README
        readme_name = f"README_aw_{table_stem}_optionC.txt"
        readme_path = os.path.join(out_dir, readme_name)
        readme_detected_lines: list[str] = []
        for row in self._aw_detected_rows:
            if row["chk"].isChecked():
                readme_detected_lines.append(
                    f'  Sub {row["sub"]}()    \' Line {row["lineno"]}\n'
                    f'      \' ... existing code ...\n'
                    f'      FireAchievement "{row["event"]}"    \' inserted automatically\n'
                    f'  End Sub'
                )
        detected_section = (
            "\n\n".join(readme_detected_lines)
            if readme_detected_lines
            else "  (none selected)"
        )
        sep = "\u2550" * 75
        readme_content = (
            f"{sep}\n"
            f"  VPX Achievement Watcher \u2013 Full Script Export (Option C)\n"
            f"  Table: {fname}\n"
            f"  Generated by AWEditor\n"
            f"{sep}\n"
            f"\n"
            f"OPTION C \u2013 Full Script Export (zero manual work):\n"
            f"{'─' * 76}\n"
            f"\n"
            f"  1. \"{vbs_name}\" has been automatically saved to your Tables folder.\n"
            f"  2. Done. VPX loads this file automatically instead of the built-in script.\n"
            f"\n"
            f"  \u26a0\ufe0f  IMPORTANT \u2013 RE-EXPORT AFTER EVERY SCRIPT CHANGE:\n"
            f"      This file contains a FULL COPY of your table script at the time of export.\n"
            f"      If you edit the table script in VPX Editor afterwards, those changes will\n"
            f"      be IGNORED because VPX loads this .vbs file instead.\n"
            f"      \u2192 Re-export from AWEditor every time you change the script in VPX Editor.\n"
            f"\n"
            f"  \u26a0\ufe0f  CUSTOM ACHIEVEMENTS NOT SUPPORTED:\n"
            f"      Option C only works with auto-detected events from Analyze Script.\n"
            f"      Custom achievements cannot be placed automatically because AWEditor\n"
            f"      does not know where in the script they should fire.\n"
            f"      \u2192 Use Option A or B if you need custom achievements.\n"
            f"\n"
            f"{'═' * 76}\n"
            f"\n"
            f"FIREACHIEVEMENT CALLS INSERTED:\n"
            f"{'─' * 32}\n"
            f"{detected_section}\n"
            f"\n"
            f"\n"
            f"FILES GENERATED:\n"
            f"{'─' * 16}\n"
            f"  \u2022 {vbs_name}        \u2192 Already in Tables folder (saved automatically)\n"
            f"  \u2022 {json_name} \u2192 Stays in AWEditor folder\n"
            f"  \u2022 {readme_name}   \u2192 Stays in AWEditor folder\n"
            f"{sep}\n"
        )
        try:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(readme_content)
        except Exception as e:
            self._aw_status_lbl.setText(f"❌ Could not write README: {e}")
            return

        self._aw_status_lbl.setText(
            f"✅ Option C exported: {vbs_name} automatically saved to Tables folder"
            " | Re-export after every script change in VPX Editor!"
        )

    # ------------------------------------------------------------------
    # AWEditor help dialog (red ❓)
    # ------------------------------------------------------------------

    def _aw_show_help_dialog(self):
        """Show the AWEditor help as a custom QDialog with a copyable inline code block."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Help – 🎯 AWEditor")
        dlg.setMinimumWidth(640)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #111; }")

        container = QWidget()
        container.setStyleSheet("background: #111;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # ── Existing help content ─────────────────────────────────────────
        lbl_main = QLabel(
            "<b>🎯 AWEditor – Custom Achievement System for Non-ROM Tables</b><br><br>"
            "<b>OVERVIEW</b><br>"
            "The AWEditor lets you create custom achievements for tables that don't use VPinMAME ROMs "
            "(Non-ROM or Original tables). Since these tables have no NVRAM data, achievements are "
            "triggered via a file-drop mechanism: the table's VBScript writes a small trigger file, "
            "and the Achievement Watcher detects it instantly.<br><br>"

            "<b>Step 1 – SELECT A TABLE</b><br>"
            "Use the dropdown to select a .vpx table. Only tables WITHOUT an NVRAM map are shown. "
            "Click 🔄 to re-scan your Tables directory.<br><br>"

            "<b>Step 2 – ANALYZE THE TABLE SCRIPT</b><br>"
            "Click '🔍 Analyze Script' to read the table's VBScript. The editor uses vpxtool to "
            "extract the script and scans for common game events: Multiball, Jackpot, Wizard Mode, "
            "Extra Ball, Mission, Ramp/Loop combos, and more. Detected events appear with their "
            "Sub name and line number.<br><br>"

            "<b>Step 3 – SELECT EVENTS AS ACHIEVEMENTS</b><br>"
            "Check the box next to any detected event you want to turn into an achievement. "
            "Each checked event becomes an achievement with an auto-generated title.<br><br>"

            "<b>Step 4 – ADD CUSTOM ACHIEVEMENTS (OPTIONAL)</b><br>"
            "Click [+ Add Achievement] to create your own. Fill in:<br>"
            "• <b>Title</b>: The name shown in the toast notification (e.g. 'Ramp Combo King')<br>"
            "• <b>Description</b>: A short text explaining what to do<br>"
            "• <b>Event Name</b>: A unique identifier, no spaces, lowercase only (e.g. 'ramp_combo_5x')<br><br>"

            "<b>Step 5 – EXPORT</b><br>"
            "Click [💾 Export VBS + JSON] to generate two files in tools/AWeditor/:<br>"
            "• <b>aw_{TableName}.vbs</b> – VBScript with the FireAchievement Sub<br>"
            "• <b>{TableName}.custom.json</b> – Achievement rule definitions<br><br>"

            "<b>INSTALLATION</b><br>"
            "1. Copy aw_{TableName}.vbs next to your .vpx file.<br>"
            "2. Open the table in VPX Editor (File → Open).<br>"
            "3. Open Script Editor (View → Script or F12).<br>"
            "4. Add near the top: <code>On Error Resume Next / ExecuteGlobal GetTextFile(\"aw_YourTable.vbs\") / On Error GoTo 0</code><br>"
            "5. Find the Subs for each event and add: <code>FireAchievement \"your_event_name\"</code><br><br>"

            "<b>⚠️ IMPORTANT – DO NOT name the .vbs file the same as the table!</b><br>"
            "If 'MyTable.vbs' exists next to 'MyTable.vpx', VPX REPLACES the entire table script "
            "and breaks the table. The 'aw_' prefix prevents this conflict.<br><br>"

            "<b>HOW THE TRIGGER MECHANISM WORKS</b><br>"
            "1. During gameplay, FireAchievement \"multiball\" is called.<br>"
            "2. It writes 'multiball.trigger' into the AWEditor/custom_events/ folder using "
            "the standard Windows Scripting.FileSystemObject (no external DLLs needed).<br>"
            "3. The Achievement Watcher detects the file, matches it against your .custom.json rules, "
            "shows a toast 🏆, and deletes the trigger file automatically.<br><br>"

            "<b>FILE LOCATIONS</b><br>"
            "• Generated scripts &amp; JSON: {BASE}/tools/AWeditor/<br>"
            "• Trigger files: {BASE}/tools/AWeditor/custom_events/<br>"
            "• Copy the aw_*.vbs to: Your Tables directory (next to .vpx)"
        )
        lbl_main.setWordWrap(True)
        lbl_main.setTextFormat(Qt.TextFormat.RichText)
        lbl_main.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        lay.addWidget(lbl_main)

        # ── Inline Integration tip ────────────────────────────────────────
        lbl_tip = QLabel(
            "<br><b>💡 Tip: Inline Integration (no extra file needed)</b><br><br>"
            "Instead of using a separate .vbs file, you can embed the Achievement Watcher "
            "integration directly into your table script. This means the table script is "
            "completely self-contained — no extra file to copy or manage.<br><br>"
            "<b>How it works:</b><br>"
            "&nbsp;&nbsp;• The script reads the installation path from the Windows Registry.<br>"
            "&nbsp;&nbsp;• If the Achievement Watcher is installed → FireAchievement works normally.<br>"
            "&nbsp;&nbsp;• If it is NOT installed → FireAchievement does nothing silently (no error!).<br><br>"
            "Copy the block below and paste it at the very TOP of your table script "
            "(before everything else):"
        )
        lbl_tip.setWordWrap(True)
        lbl_tip.setTextFormat(Qt.TextFormat.RichText)
        lbl_tip.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        lay.addWidget(lbl_tip)

        # ── Copyable inline code block ────────────────────────────────────
        inline_code = (
            "' \u2500\u2500 VPX Achievement Watcher \u2013 Inline Integration \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            "Dim AW_EventPath, AW_Installed\n"
            "Sub AW_Init()\n"
            "    On Error Resume Next\n"
            "    AW_Installed = False\n"
            "    Dim sh : Set sh = CreateObject(\"WScript.Shell\")\n"
            "    AW_EventPath = sh.RegRead(\"HKCU\\Software\\VPX Achievement Watcher\\EventsPath\")\n"
            "    Set sh = Nothing\n"
            "    AW_Installed = (Err.Number = 0 And AW_EventPath <> \"\")\n"
            "    Err.Clear : On Error GoTo 0\n"
            "End Sub\n"
            "AW_Init\n"
            "\n"
            "Sub FireAchievement(eventName)\n"
            "    If Not AW_Installed Then Exit Sub\n"
            "    On Error Resume Next\n"
            "    Dim fso, f\n"
            "    Set fso = CreateObject(\"Scripting.FileSystemObject\")\n"
            "    Set f = fso.CreateTextFile(AW_EventPath & eventName & \".trigger\", True)\n"
            "    f.WriteLine eventName : f.WriteLine Now\n"
            "    f.Close\n"
            "    Set f = Nothing : Set fso = Nothing\n"
            "    On Error GoTo 0\n"
            "End Sub\n"
            "' \u2500\u2500 End Achievement Watcher \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
        )
        code_edit = QPlainTextEdit()
        code_edit.setReadOnly(True)
        code_edit.setPlainText(inline_code)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        code_edit.setFont(mono)
        code_edit.setFixedHeight(220)
        code_edit.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #E0E0E0;"
            " border: 1px solid #FF7F00; font-family: 'Courier New', monospace; }"
        )
        lay.addWidget(code_edit)

        lbl_note = QLabel(
            "Then call <code>FireAchievement \"your_event_id\"</code> wherever the action happens "
            "in your script."
        )
        lbl_note.setWordWrap(True)
        lbl_note.setTextFormat(Qt.TextFormat.RichText)
        lbl_note.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        lay.addWidget(lbl_note)

        lbl_option_c = QLabel(
            "<br><b>\u26a1 Option C \u2013 Full Script Export (zero manual work)</b><br><br>"
            "AWEditor extracts the complete table script from the .vpx file, automatically "
            "inserts <code>FireAchievement</code> calls into the correct Subs, prepends the "
            "AW-Init block, and saves the result as <b>{TableName}.vbs</b> \u2014 the same name "
            "as your .vpx file. VPX loads this file automatically instead of the built-in script.<br><br>"
            "<b>How to use:</b><br>"
            "&nbsp;&nbsp;1. Select a table in the \U0001f4cb Tables tab<br>"
            "&nbsp;&nbsp;2. Click \U0001f50d Analyze Script and check the events you want<br>"
            "&nbsp;&nbsp;3. Click <b>\u26a1 Export Full Script</b><br>"
            "&nbsp;&nbsp;4. Done \u2014 no manual script editing needed<br><br>"
            "\u2705 No manual editing needed<br>"
            "\u2705 FireAchievement calls are inserted automatically<br>"
            "\u2705 Works silently if Achievement Watcher is not installed<br><br>"
            "<b>\u26a0\ufe0f Re-export every time you edit the table script in VPX Editor.</b> "
            "This file is a full copy of the script \u2014 VPX edits made afterwards will be ignored "
            "until you re-export.<br><br>"
            "<b>\u26a0\ufe0f Custom Achievements are NOT supported in Option C.</b><br>"
            "Option C only inserts FireAchievement calls for auto-detected events. "
            "Custom achievements require you to manually decide where in the script they fire \u2014 "
            "use Option A or B for those."
        )
        lbl_option_c.setWordWrap(True)
        lbl_option_c.setTextFormat(Qt.TextFormat.RichText)
        lbl_option_c.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        lay.addWidget(lbl_option_c)

        lay.addStretch(1)
        scroll.setWidget(container)

        outer_lay = QVBoxLayout(dlg)
        outer_lay.setContentsMargins(0, 0, 0, 8)
        outer_lay.addWidget(scroll, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(30)
        btn_close.setStyleSheet(
            "QPushButton { background: #222; color: #E0E0E0; border: 1px solid #555;"
            " border-radius: 4px; padding: 0 16px; }"
            "QPushButton:hover { background: #333; }"
        )
        btn_close.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        btn_row.setContentsMargins(8, 0, 8, 0)
        outer_lay.addLayout(btn_row)

        dlg.resize(660, 620)
        dlg.exec()

    # ------------------------------------------------------------------
    # Custom Guide dialog
    # ------------------------------------------------------------------

    def _aw_show_custom_guide(self):
        """Show a step-by-step guide for creating Custom Achievements."""
        # Determine .vbs filename for the placeholder in the code snippet
        if self._aw_selected_table:
            vbs_name_guide = "aw_" + os.path.splitext(os.path.basename(self._aw_selected_table))[0] + ".vbs"
        else:
            vbs_name_guide = "aw_YourTable.vbs"

        dlg = QDialog(self)
        dlg.setWindowTitle("How to create Custom Achievements")
        dlg.setMinimumWidth(620)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #111; }")

        container = QWidget()
        container.setStyleSheet("background: #111;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        lbl_intro = QLabel(
            "<b style='font-size:12pt;'>How to create Custom Achievements</b><br><br>"
            "Creating your own achievements via the <b>✏️ Codes</b> tab is perfect when "
            "<i>Analyze Script</i> doesn't find an event, or when you want to create "
            "entirely unique goals.<br><br>"
            "Here is a step-by-step example (e.g. for hitting a secret scoop):<br><br>"

            "<b>1. Select a Table</b><br>"
            "Go to the <b>📋 Tables</b> sub-tab and click the <b>+</b> button on your "
            "table to select it.<br><br>"

            "<b>2. Define the Achievement</b><br>"
            "Switch to the <b>✏️ Codes</b> sub-tab. Scroll down to "
            "<i>✏️ Custom Achievements</i> and click <b>+ Add Achievement</b>.<br>"
            "Fill in the three fields:<br>"
            "&nbsp;&nbsp;• <b>Title:</b> The name of your achievement "
            "(e.g. <code>Secret Chamber!</code>)<br>"
            "&nbsp;&nbsp;• <b>Description:</b> A short info text "
            "(e.g. <code>You found the hidden hole</code>)<br>"
            "&nbsp;&nbsp;• <b>Event-ID (far right):</b> A short code word you invent yourself. "
            "<b>Important:</b> Use only lowercase letters, numbers, and underscores – "
            "no spaces! (e.g. <code>secret_hole</code>)<br><br>"

            "<b>3. Export Files</b><br>"
            "Click <b>💾 Export VBS + JSON</b> at the bottom.<br><br>"

            "<b>4. Add the integration code to the VPX table script</b><br>"
            "Open your table in VPX and press <b>F12</b> to open the Script Editor.<br><br>"

            "<b>\u2500\u2500\u2500 OPTION A \u2013 With separate .vbs file (generated by Export) "
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500</b><br>"
            "Copy these 3 lines and paste them at the very TOP of your table script "
            "(above everything else):"
        )
        lbl_intro.setWordWrap(True)
        lbl_intro.setTextFormat(Qt.TextFormat.RichText)
        lbl_intro.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        lay.addWidget(lbl_intro)

        # Option A copyable 3-liner
        option_a_code = (
            f"On Error Resume Next\n"
            f"ExecuteGlobal GetTextFile(\"{vbs_name_guide}\")\n"
            f"On Error GoTo 0"
        )
        code_a = QPlainTextEdit()
        code_a.setReadOnly(True)
        code_a.setPlainText(option_a_code)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        code_a.setFont(mono)
        code_a.setFixedHeight(68)
        code_a.setStyleSheet(
            "QPlainTextEdit { background: #1a1a1a; color: #E0E0E0;"
            " border: 1px solid #FF7F00; font-family: 'Courier New', monospace; }"
        )
        lay.addWidget(code_a)

        lbl_option_a_note = QLabel(
            "The .vbs file must be placed next to your .vpx file in the Tables folder.<br><br>"

            "<b>\u2500\u2500\u2500 OPTION B \u2013 Inline (no extra file needed) "
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500</b><br>"
            "Instead of the .vbs file, copy the full inline block at the very TOP of your "
            "table script. Find the block in the <b>\u2753 Help</b> button on this tab.<br><br>"
            "\u2705 No extra file needed<br>"
            "\u2705 Works automatically when Achievement Watcher is installed<br>"
            "\u2705 Does nothing silently when Achievement Watcher is NOT installed<br><br>"
        )
        lbl_option_a_note.setWordWrap(True)
        lbl_option_a_note.setTextFormat(Qt.TextFormat.RichText)
        lbl_option_a_note.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        lay.addWidget(lbl_option_a_note)

        lbl_option_c_guide = QLabel(
            "<b>\u2500\u2500\u2500 OPTION C \u2013 Full Script Export (zero manual work) "
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500</b><br>"
            "Click <b>\u26a1 Export Full Script</b>. AWEditor extracts the complete table script, "
            "inserts all <code>FireAchievement</code> calls automatically, and saves "
            "<b>{TableName}.vbs</b> directly into your Tables folder.<br><br>"
            "\u2705 No manual script editing needed<br>"
            "\u2705 FireAchievement calls inserted automatically<br><br>"
            "<b>\u26a0\ufe0f Re-export after every script change in VPX Editor.</b> "
            "This file replaces the built-in script entirely \u2014 VPX changes made afterwards "
            "are ignored until you re-export.<br><br>"
            "<b>\u26a0\ufe0f Custom Achievements are NOT supported in Option C.</b> "
            "If you have defined custom achievements in the \u270f\ufe0f Codes tab, use Option A or B instead.<br><br>"
            "<hr>"
            "<b>Summary:</b> You invent a unique Event-ID, register it in the AWEditor, "
            "and then paste <code>FireAchievement \"your_event_id\"</code> directly into "
            "the table's script where the action happens."
        )
        lbl_option_c_guide.setWordWrap(True)
        lbl_option_c_guide.setTextFormat(Qt.TextFormat.RichText)
        lbl_option_c_guide.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        lay.addWidget(lbl_option_c_guide)

        lay.addStretch(1)
        scroll.setWidget(container)

        outer_lay = QVBoxLayout(dlg)
        outer_lay.setContentsMargins(0, 0, 0, 8)
        outer_lay.addWidget(scroll, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(30)
        btn_close.setStyleSheet(
            "QPushButton { background: #222; color: #E0E0E0; border: 1px solid #555;"
            " border-radius: 4px; padding: 0 16px; }"
            "QPushButton:hover { background: #333; }"
        )
        btn_close.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        btn_row.setContentsMargins(8, 0, 8, 0)
        outer_lay.addLayout(btn_row)

        dlg.resize(640, 580)
        dlg.exec()
