"""
tutorial.py – First-Run Tutorial Wizard (14 steps)

A non-modal QDialog that walks the user through every tab of the app on
their very first launch.  It floats on top of the main window so the user
can see which tab is highlighted as the wizard advances.

Usage (called from Achievement_watcher.main()):
    tutorial = TutorialWizardDialog(cfg, main_window)
    tutorial.show()
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)

# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------
# Each entry is a dict with:
#   title   – icon + heading shown in large text
#   body    – multi-line description (plain text, shown in a QLabel)
#   tab     – main-tab index to switch to on Next, or None
#   subtab  – Appearance sub-tab index (0=Overlay, 1=Theme, 2=Sound), or None

_STEPS = [
    {
        "title": "👋 Welcome!",
        "body": (
            "This wizard walks you through the essential steps to get\n"
            "achievement tracking working with your VPX tables.\n\n"
            "You'll need:\n"
            "  • Visual Pinball X installed and working\n"
            "  • VPinMAME with ROM files for your tables\n"
            "  • NVRAM files (created automatically by VPinMAME\n"
            "    when you play a table)\n\n"
            "Don't worry — we'll explain each step."
        ),
        "tab": None,
        "subtab": None,
    },
    {
        "title": "👤 Player Identity",
        "body": (
            "Your Player Name and Player ID are shown in the System\n"
            "tab behind this window.\n\n"
            "  • Player Name: Displayed on overlays and leaderboards.\n"
            "    Change it anytime in the System tab.\n\n"
            "  • Player ID: Your unique 4-character identifier.\n"
            "    ⚠️ Keep your Player ID safe!\n"
            "    It links all your stats, achievements, and cloud data.\n"
            "    If you lose it, your progress cannot be recovered.\n"
            "    Do not share it with others."
        ),
        "tab": 8,   # System
        "subtab": None,
    },
    {
        "title": "🏠 Dashboard",
        "body": (
            "The Dashboard is your control center — it shows the\n"
            "current state of the watcher at a glance.\n\n"
            "  • System Status: Is the watcher running?\n"
            "  • Session Summary: Last table played, score, achievements\n"
            "  • Run Status: Table detection, session, cloud and\n"
            "    leaderboard connection (green/yellow/red indicators)\n"
            "  • Notifications: Clickable alerts for leaderboard ranks,\n"
            "    beaten records, missing VPS-IDs, and available updates\n"
            "  • Quick Actions: Restart Engine, Minimize to Tray, Quit\n\n"
            "The Dashboard updates automatically. No setup needed."
        ),
        "tab": 0,   # Dashboard
        "subtab": None,
    },
    {
        "title": "🗺️ Loading Your Tables",
        "body": (
            "The Available Maps tab is now open behind this window.\n\n"
            "Click \"🔄 Load List\" in the top right corner and wait\n"
            "while your tables directory is scanned. This may take\n"
            "a minute depending on how many tables you have.\n\n"
            "Once loaded you'll see:\n"
            "  • ✅ NVRAM Map = achievement tracking supported\n"
            "  • ❌ No NVRAM Map = not supported yet\n"
            "  • 🟠 Local = .vpx file found in your tables folder\n\n"
            "Each table needs an NVRAM Map to track achievements.\n"
            "Maps are downloaded automatically from the cloud index."
        ),
        "tab": 6,   # Available Maps
        "subtab": None,
    },
    {
        "title": "🔑 VPS-ID — Linking Tables to the Database",
        "body": (
            "For cloud leaderboards and table info, each table needs\n"
            "a VPS-ID (Virtual Pinball Spreadsheet ID).\n\n"
            "How to assign VPS-IDs:\n"
            "  1. Click \"⚡ Auto-Match All\" in the top right corner\n"
            "  2. Wait for the matching to complete\n"
            "  3. ⚠️ Review the results! Auto-match is not always\n"
            "     correct — scroll through the list and check each\n"
            "     table's VPS-ID. Click the [+] button to correct\n"
            "     any wrong matches manually.\n\n"
            "VPS-IDs are optional for local tracking but required for:\n"
            "  • ☁️ Cloud leaderboard uploads\n"
            "  • 🖼️ Table images and metadata\n"
            "  • 📊 Cross-player stat comparison"
        ),
        "tab": None,  # Stay on Available Maps
        "subtab": None,
    },
    {
        "title": "📐 Overlay Settings",
        "body": (
            "Overlays appear on top of your pinball table while you\n"
            "play. Configure them in the Overlay tab behind this window.\n\n"
            "Position — Each overlay has a \"Set Position\" button.\n"
            "Click it to drag the overlay where you want it on screen.\n"
            "Examples: Stats Overlay, Achievement Toast, Challenge\n"
            "Menu, Flip Counter, Heat Bar, and more.\n\n"
            "Page Controls — Enable or disable overlay pages (2–5)\n"
            "to choose which information is shown during gameplay.\n\n"
            "💡 Set positions now so overlays don't cover important\n"
            "   parts of your playfield. You can always adjust later."
        ),
        "tab": 2,   # Appearance
        "subtab": 0,  # Overlay sub-tab
    },
    {
        "title": "⌨️ Controls & Hotkeys",
        "body": (
            "The Controls tab lets you configure keyboard hotkeys\n"
            "for use during gameplay.\n\n"
            "  • Toggle overlay on/off while playing\n"
            "  • Cycle through overlay pages\n"
            "  • Start/stop challenges\n"
            "  • Quick actions without leaving the table"
        ),
        "tab": 3,   # Controls
        "subtab": None,
    },
    {
        "title": "🎨 Theme (optional)",
        "body": (
            "Choose a visual theme for the app and all overlays.\n"
            "The default is \"Neon Blue\" (cyan + orange).\n\n"
            "15 themes available — pick one that fits your style:\n\n"
            "  💙 Neon Blue    💜 Synthwave    ⚡ Cyberpunk\n"
            "  🟢 Retro Arcade 🔴 Lava        🔵 Arctic\n"
            "  🟡 Classic      ⚫ Stealth      👑 Royal Purple\n"
            "  ☢️ Toxic Green  🌊 Ocean       🌙 Midnight Gold\n"
            "  🌸 Cherry       🌲 Forest      🌅 Sunset\n\n"
            "Select a theme in the Theme tab and click \"Apply Theme\".\n"
            "You can always change it later."
        ),
        "tab": 2,   # Appearance
        "subtab": 1,  # Theme sub-tab
    },
    {
        "title": "🔊 Sound Effects (optional)",
        "body": (
            "Enable sound effects for achievement unlocks, challenges,\n"
            "and other events.\n\n"
            "  • Toggle \"Enable Sound Effects\" to turn sounds on\n"
            "  • Adjust volume with the slider\n"
            "  • Choose a sound pack (Vex Machina, Zaptron, etc.)\n"
            "  • Enable/disable sounds per event\n"
            "  • Use the ▶ buttons to preview each sound\n\n"
            "Sounds are disabled by default. Enable them here if you\n"
            "want audio feedback during gameplay."
        ),
        "tab": 2,   # Appearance
        "subtab": 2,  # Sound sub-tab
    },
    {
        "title": "✨ Effects (optional)",
        "body": (
            "Fine-tune which animations are shown on each overlay.\n\n"
            "  • Toggle individual effects on or off per overlay\n"
            "  • Use [All On] / [All Off] for quick control\n"
            "  • Preview animations live in the preview window\n"
            "  • Low Performance Mode (Overlay tab) disables all effects\n\n"
            "All effects are enabled by default."
        ),
        "tab": 2,   # Appearance
        "subtab": 3,  # Effects sub-tab
    },
    {
        "title": "📊 Records & Stats",
        "body": (
            "This tab tracks your personal records across all tables:\n\n"
            "  • High scores per table\n"
            "  • Achievement completion rates\n"
            "  • Session history and play time\n"
            "  • Personal bests and milestones\n\n"
            "Everything is tracked automatically — just play and your\n"
            "stats will appear here. No setup needed."
        ),
        "tab": 4,   # Records & Stats
        "subtab": None,
    },
    {
        "title": "📈 Progress",
        "body": (
            "Track your overall achievement progress per table:\n\n"
            "  • Completion percentage for each table\n"
            "  • Which achievements are still locked\n"
            "  • Overall progress across all tables\n"
            "  • Level progression and XP\n\n"
            "Use this tab to see what you still need to unlock.\n"
            "Everything updates automatically after each session."
        ),
        "tab": 5,   # Progress
        "subtab": None,
    },
    {
        "title": "☁️ Cloud Sync & Leaderboards (optional)",
        "body": (
            "Upload your scores and achievements to compete on the\n"
            "global cloud leaderboard!\n\n"
            "  • Enable \"Cloud Sync\" to automatically upload after\n"
            "    each session\n"
            "  • Your Player Name and Player ID are used for the board\n\n"
            "📜 Cloud Leaderboard Rules:\n"
            "  • One player per installation — no shared accounts\n"
            "  • Scores must come from real gameplay (NVRAM-verified)\n"
            "  • Manipulated scores will be flagged and removed\n"
            "  • VPS-ID must be correctly assigned for each table\n"
            "  • Rankings update after each sync\n\n"
            "Click \"📜 Cloud Rules\" in the Cloud tab for full details."
        ),
        "tab": 7,   # Cloud
        "subtab": None,
    },
    {
        "title": "🧑 Player Tab",
        "body": (
            "Your personal player profile and summary:\n\n"
            "  • Current level and XP progress\n"
            "  • Total achievements unlocked\n"
            "  • Badges earned for milestones\n\n"
            "This is your profile page — everything fills in\n"
            "automatically as you play more tables."
        ),
        "tab": 1,   # Player
        "subtab": None,
    },
    {
        "title": "🎮 How to Play",
        "body": (
            "1. Keep VPX Achievement Watcher running in the background\n"
            "2. Launch a table in Visual Pinball X\n"
            "3. The watcher detects the game automatically\n"
            "4. Play! Achievements pop up as toast notifications\n"
            "5. Press your hotkey to toggle the stats overlay\n\n"
            "💡 The watcher monitors your NVRAM folder.\n"
            "   Just keep it open and play!\n\n"
            "Quick Reference:\n"
            "  • 📚 Available Maps → supported tables & VPS-IDs\n"
            "  • ⚙️ System → paths, updates, maintenance\n"
            "  • ❓ Help button on every tab for detailed info"
        ),
        "tab": None,
        "subtab": None,
    },
]

_TOTAL_STEPS = len(_STEPS)

# ---------------------------------------------------------------------------
# Stylesheet helpers
# ---------------------------------------------------------------------------
_DIALOG_STYLE = """
QDialog {
    background: #141414;
    color: #e0e0e0;
}
QLabel {
    color: #e0e0e0;
    background: transparent;
}
QPushButton {
    background: #1e2d2d;
    color: #00d4d4;
    border: 1px solid #00d4d4;
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 9pt;
    font-weight: bold;
}
QPushButton:hover {
    background: #00d4d4;
    color: #141414;
}
QPushButton:disabled {
    background: #1a1a1a;
    color: #444;
    border-color: #333;
}
QPushButton#btn_skip {
    background: transparent;
    color: #666;
    border: 1px solid #333;
    font-weight: normal;
}
QPushButton#btn_skip:hover {
    background: #1a1a1a;
    color: #999;
    border-color: #555;
}
QPushButton#btn_finish {
    background: #e07000;
    color: #141414;
    border: 1px solid #e07000;
}
QPushButton#btn_finish:hover {
    background: #ff8800;
    border-color: #ff8800;
    color: #141414;
}
"""


# ---------------------------------------------------------------------------
# Wizard dialog
# ---------------------------------------------------------------------------
class TutorialWizardDialog(QDialog):
    """
    Non-modal 14-step first-run tutorial wizard.

    Parameters
    ----------
    cfg : AppConfig
        Live config object; ``TUTORIAL_COMPLETED`` is set to True and saved
        when the user finishes or skips the wizard.
    parent : MainWindow
        The main application window.  The wizard uses it to switch tabs.
    """

    def __init__(self, cfg, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint,
        )
        self.cfg = cfg
        self._step = 0

        self.setWindowTitle("VPX Achievement Watcher – First-Time Setup")
        self.resize(520, 440)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── step counter row ──────────────────────────────────────────────
        self._lbl_counter = QLabel()
        self._lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_counter.setStyleSheet(
            "color: #888; font-size: 8pt; letter-spacing: 1px;"
        )
        root.addWidget(self._lbl_counter)

        # ── dot indicator row ─────────────────────────────────────────────
        self._dot_row = QHBoxLayout()
        self._dot_row.setSpacing(6)
        self._dot_row.addStretch(1)
        self._dot_labels: list = []
        for _ in range(_TOTAL_STEPS):
            dot = QLabel("○")
            dot.setFixedWidth(14)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("font-size: 10pt;")
            self._dot_labels.append(dot)
            self._dot_row.addWidget(dot)
        self._dot_row.addStretch(1)
        root.addLayout(self._dot_row)

        # ── title label ───────────────────────────────────────────────────
        self._lbl_title = QLabel()
        self._lbl_title.setStyleSheet(
            "font-size: 14pt; font-weight: bold; color: #00d4d4; padding-top: 4px;"
        )
        self._lbl_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self._lbl_title)

        # ── body label ────────────────────────────────────────────────────
        self._lbl_body = QLabel()
        self._lbl_body.setWordWrap(True)
        self._lbl_body.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._lbl_body.setStyleSheet(
            "font-size: 9pt; color: #cccccc; line-height: 150%; padding: 4px 0px;"
        )
        root.addWidget(self._lbl_body, 1)

        # ── button row ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_skip = QPushButton("[Skip Setup]")
        self._btn_skip.setObjectName("btn_skip")
        self._btn_skip.clicked.connect(self._on_skip)

        self._btn_back = QPushButton("← Back")
        self._btn_back.clicked.connect(self._on_back)

        self._btn_next = QPushButton("Next →")
        self._btn_next.clicked.connect(self._on_next)

        self._btn_finish = QPushButton("🚀  Let's Go!")
        self._btn_finish.setObjectName("btn_finish")
        self._btn_finish.clicked.connect(self._on_finish)

        btn_row.addWidget(self._btn_skip)
        btn_row.addStretch(1)
        btn_row.addWidget(self._btn_back)
        btn_row.addWidget(self._btn_next)
        btn_row.addWidget(self._btn_finish)

        root.addLayout(btn_row)

        self._refresh()

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def _refresh(self):
        step = _STEPS[self._step]
        n = self._step + 1
        total = _TOTAL_STEPS
        is_last = self._step == total - 1

        self._lbl_counter.setText(f"Step {n} of {total}")

        for i, dot in enumerate(self._dot_labels):
            if i < n:
                dot.setText("●")
                dot.setStyleSheet(
                    "font-size: 10pt; color: #00d4d4;"
                    if i == self._step
                    else "font-size: 10pt; color: #007a7a;"
                )
            else:
                dot.setText("○")
                dot.setStyleSheet("font-size: 10pt; color: #444;")

        self._lbl_title.setText(step["title"])
        self._lbl_body.setText(step["body"])

        self._btn_skip.setVisible(not is_last)
        self._btn_back.setEnabled(self._step > 0)
        self._btn_next.setVisible(not is_last)
        self._btn_finish.setVisible(is_last)

    def _switch_tab(self, step_idx: int):
        """Switch the main window to the tab specified for the given step."""
        parent = self.parent()
        if parent is None:
            return
        step = _STEPS[step_idx]
        tab_idx = step.get("tab")
        subtab_idx = step.get("subtab")
        try:
            if tab_idx is not None:
                parent.main_tabs.setCurrentIndex(tab_idx)
            if subtab_idx is not None and hasattr(parent, "appearance_subtabs"):
                parent.appearance_subtabs.setCurrentIndex(subtab_idx)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Button slots
    # ------------------------------------------------------------------

    def _on_next(self):
        if self._step < _TOTAL_STEPS - 1:
            self._step += 1
            self._switch_tab(self._step)
            self._refresh()

    def _on_back(self):
        if self._step > 0:
            self._step -= 1
            self._switch_tab(self._step)
            self._refresh()

    def _on_skip(self):
        self._complete()

    def _on_finish(self):
        self._complete()

    def _complete(self):
        self._mark_done()
        self.close()

    def _mark_done(self):
        try:
            self.cfg.TUTORIAL_COMPLETED = True
            self.cfg.save()
        except Exception:
            pass

    def closeEvent(self, event):
        # Ensure completion flag is set even if user closes via the X button.
        self._mark_done()
        super().closeEvent(event)
