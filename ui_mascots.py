"""ui_mascots.py – 🏆 Mascots sub-tab mixin for the Appearance tab.

Provides the MascotsMixin class which builds the Mascots sub-tab containing
skin galleries and live previews for Trophie (GUI mascot) and Steely (desktop
overlay mascot), as well as visibility/orientation controls that were previously
in the System > General sub-tab.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QCheckBox, QGroupBox, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt

from trophy_mascot import _TrophieDrawWidget, _PinballDrawWidget

# ---------------------------------------------------------------------------
# Skin definitions
# ---------------------------------------------------------------------------
TROPHIE_SKINS = [
    {"id": "classic",     "name": "Classic",      "icon": "🏆",    "accessory": None},
    {"id": "crown",       "name": "Golden King",  "icon": "🏆👑",  "accessory": "crown"},
    {"id": "top_hat",     "name": "Top Hat",      "icon": "🏆🎩",  "accessory": "top_hat"},
    {"id": "sunglasses",  "name": "Cool Shades",  "icon": "🏆🕶️", "accessory": "sunglasses"},
    {"id": "party_hat",   "name": "Party Time",   "icon": "🏆🎉",  "accessory": "party_hat"},
    {"id": "pirate",      "name": "Pirate",       "icon": "🏆🏴‍☠️", "accessory": "pirate"},
    {"id": "headband",    "name": "Ninja",        "icon": "🏆🥷",  "accessory": "headband"},
    {"id": "wizard_hat",  "name": "Wizard",       "icon": "🏆🧙",  "accessory": "wizard_hat"},
    {"id": "santa_hat",   "name": "Santa",        "icon": "🏆🎅",  "accessory": "santa_hat"},
    {"id": "ice",         "name": "Frosty",       "icon": "🏆❄️",  "accessory": "ice"},
    {"id": "flame",       "name": "Inferno",      "icon": "🏆🔥",  "accessory": "flame"},
    {"id": "sparks",      "name": "Electric",     "icon": "🏆⚡",  "accessory": "sparks"},
    {"id": "rainbow",     "name": "Rainbow",      "icon": "🏆🌈",  "accessory": "rainbow"},
    {"id": "gears",       "name": "Steampunk",    "icon": "🏆⚙️",  "accessory": "gears"},
    {"id": "helmet",      "name": "Astronaut",    "icon": "🏆🚀",  "accessory": "helmet"},
    {"id": "detective",   "name": "Detective",    "icon": "🏆🔍",  "accessory": "detective"},
    {"id": "chef_hat",    "name": "Chef",         "icon": "🏆👨‍🍳", "accessory": "chef_hat"},
    {"id": "cape",        "name": "Vampire",      "icon": "🏆🧛",  "accessory": "cape"},
    {"id": "antenna",     "name": "Robot",        "icon": "🏆🤖",  "accessory": "antenna"},
    {"id": "crystal",     "name": "Diamond",      "icon": "🏆💎",  "accessory": "crystal"},
    {"id": "neon_glow",   "name": "Neon",         "icon": "🏆✨",  "accessory": "neon_glow"},
    {"id": "medal",       "name": "Champion",     "icon": "🏆🏅",  "accessory": "medal"},
]

STEELY_SKINS = [
    {"id": "classic",    "name": "Classic",      "icon": "🎱",  "accessory": None},
    {"id": "chrome",     "name": "Chrome",       "icon": "🪩",  "accessory": "chrome"},
    {"id": "gold_ball",  "name": "Gold Ball",    "icon": "🥇",  "accessory": "gold"},
    {"id": "8ball",      "name": "8-Ball",       "icon": "🎱",  "accessory": "8ball"},
    {"id": "soccer",     "name": "Soccer Ball",  "icon": "⚽",  "accessory": "soccer"},
    {"id": "basketball", "name": "Basketball",   "icon": "🏀",  "accessory": "basketball"},
    {"id": "baseball",   "name": "Baseball",     "icon": "⚾",  "accessory": "baseball"},
    {"id": "tennis",     "name": "Tennis Ball",  "icon": "🎾",  "accessory": "tennis"},
    {"id": "bowling",    "name": "Bowling Ball",  "icon": "🎳", "accessory": "bowling"},
    {"id": "eyeball",    "name": "Eyeball",      "icon": "👁️", "accessory": "eyeball"},
    {"id": "disco",      "name": "Disco Ball",   "icon": "🪩",  "accessory": "disco"},
    {"id": "planet",     "name": "Planet",       "icon": "🪐",  "accessory": "planet"},
    {"id": "moon",       "name": "Moon",         "icon": "🌙",  "accessory": "moon"},
    {"id": "fireball",   "name": "Fireball",     "icon": "🔥",  "accessory": "fireball"},
    {"id": "iceball",    "name": "Ice Ball",     "icon": "❄️",  "accessory": "iceball"},
    {"id": "marble",     "name": "Marble",       "icon": "🔮",  "accessory": "marble"},
    {"id": "camo",       "name": "Camouflage",   "icon": "🎖️", "accessory": "camo"},
    {"id": "pixel",      "name": "Pixel Ball",   "icon": "👾",  "accessory": "pixel"},
    {"id": "galaxy",     "name": "Galaxy",       "icon": "🌌",  "accessory": "galaxy"},
    {"id": "rubber",     "name": "Rubber",       "icon": "⚫",  "accessory": "rubber"},
    {"id": "beach",      "name": "Beach Ball",   "icon": "🏖️", "accessory": "beach"},
    {"id": "skull",      "name": "Skull Ball",   "icon": "💀",  "accessory": "skull"},
]

# ---------------------------------------------------------------------------
# Styling constants
# ---------------------------------------------------------------------------
_CARD_NORMAL = (
    "QWidget#skinCard {"
    "  background-color: #1a1a1a;"
    "  border: 1px solid #333;"
    "  border-radius: 6px;"
    "}"
    "QWidget#skinCard:hover {"
    "  border: 1px solid #FF7F00;"
    "}"
)
_CARD_PREVIEW = (
    "QWidget#skinCard {"
    "  background-color: #1a1a1a;"
    "  border: 2px solid #00E5FF;"
    "  border-radius: 6px;"
    "}"
)
_CARD_APPLIED = (
    "QWidget#skinCard {"
    "  background-color: #3D2600;"
    "  border: 2px solid #FF7F00;"
    "  border-radius: 6px;"
    "}"
)

_BTN_APPLY_CSS = (
    "QPushButton { background-color: #FF7F00; color: #000000; font-weight: bold;"
    "  border: none; padding: 6px 16px; border-radius: 4px; font-size: 9pt; }"
    "QPushButton:hover { background-color: #FF9933; }"
    "QPushButton:pressed { background-color: #CC6600; }"
)

_GRP_CSS = (
    "QGroupBox { color: #E0E0E0; font-size: 10pt; font-weight: bold;"
    "  border: 1px solid #444; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
)

_SCROLL_CSS = (
    "QScrollArea { background: transparent; border: none; }"
    "QScrollBar:vertical { background: #1a1a1a; width: 8px; border-radius: 4px; }"
    "QScrollBar::handle:vertical { background: #444; border-radius: 4px; min-height: 20px; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
    "QScrollBar:horizontal { background: #1a1a1a; height: 8px; border-radius: 4px; }"
    "QScrollBar::handle:horizontal { background: #444; border-radius: 4px; min-width: 20px; }"
    "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
)


class MascotsMixin:
    """Mixin that provides the 🏆 Mascots sub-tab inside the Appearance tab.

    Expects the host class to provide:
        self.cfg                        – AppConfig instance
        self.appearance_subtabs         – QTabWidget (appearance sub-tabs)
        self._add_tab_help_button(layout, key)
        self._on_trophie_gui_toggled    – handler (from SystemMixin)
        self._on_trophie_overlay_toggled
        self._on_trophie_overlay_portrait_toggled
        self._on_trophie_overlay_ccw_toggled
        self._trophie_gui               – GUITrophie instance (optional, may not exist yet)
        self._trophie_overlay           – OverlayTrophie instance (optional)
    """

    # ── Public entry-point ────────────────────────────────────────────────────
    def _build_mascots_subtab(self) -> None:
        """Build and register the 🏆 Mascots sub-tab."""
        tab = QWidget()
        tab_outer = QVBoxLayout(tab)
        tab_outer.setContentsMargins(0, 0, 0, 0)
        tab_outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(_SCROLL_CSS)

        inner = QWidget()
        inner.setStyleSheet("background-color: #111;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)

        scroll.setWidget(inner)
        tab_outer.addWidget(scroll)

        # ── Trophie section ───────────────────────────────────────────────────
        layout.addWidget(self._build_trophie_group())

        # ── Steely section ────────────────────────────────────────────────────
        layout.addWidget(self._build_steely_group())

        layout.addStretch(1)
        self._add_tab_help_button(layout, "appearance_mascots")

        self.appearance_subtabs.addTab(tab, "🏆 Mascots")

    # ── Trophie group ─────────────────────────────────────────────────────────
    def _build_trophie_group(self) -> QGroupBox:
        grp = QGroupBox("🏆 Trophie (GUI Mascot)")
        grp.setStyleSheet(_GRP_CSS)
        grp_layout = QVBoxLayout(grp)
        grp_layout.setSpacing(10)

        # Settings row
        self.chk_trophie_gui = QCheckBox("Show Trophie in the main window (GUI)")
        self.chk_trophie_gui.setChecked(bool(self.cfg.OVERLAY.get("trophie_gui_enabled", True)))
        self.chk_trophie_gui.setToolTip(
            "Shows the animated Trophie mascot in the bottom-left corner of the main window."
        )
        self.chk_trophie_gui.setStyleSheet("color: #E0E0E0;")
        self.chk_trophie_gui.stateChanged.connect(self._on_trophie_gui_toggled)
        grp_layout.addWidget(self.chk_trophie_gui)

        # Gallery + preview split
        current_skin = self.cfg.OVERLAY.get("trophie_gui_skin", "classic")
        split = self._build_skin_gallery_split(
            skins=TROPHIE_SKINS,
            current_skin=current_skin,
            draw_widget_factory=lambda parent: _TrophieDrawWidget(parent, 120, 140),
            on_apply=self._apply_trophie_skin,
            attr_prefix="trophie",
        )
        grp_layout.addWidget(split)
        return grp

    # ── Steely group ──────────────────────────────────────────────────────────
    def _build_steely_group(self) -> QGroupBox:
        grp = QGroupBox("🎱 Steely (Desktop Overlay Mascot)")
        grp.setStyleSheet(_GRP_CSS)
        grp_layout = QVBoxLayout(grp)
        grp_layout.setSpacing(8)

        # Settings checkboxes
        self.chk_trophie_overlay = QCheckBox("Show Steely on the desktop (Overlay)")
        self.chk_trophie_overlay.setChecked(bool(self.cfg.OVERLAY.get("trophie_overlay_enabled", True)))
        self.chk_trophie_overlay.setToolTip(
            "Shows the Steely mascot as a desktop overlay — always visible, reacts to game events."
        )
        self.chk_trophie_overlay.setStyleSheet("color: #E0E0E0;")
        self.chk_trophie_overlay.stateChanged.connect(self._on_trophie_overlay_toggled)
        grp_layout.addWidget(self.chk_trophie_overlay)

        self.chk_trophie_overlay_portrait = QCheckBox("Portrait Mode (90°) — for cabinet screens")
        self.chk_trophie_overlay_portrait.setChecked(
            bool(self.cfg.OVERLAY.get("trophie_overlay_portrait", False))
        )
        self.chk_trophie_overlay_portrait.setToolTip(
            "Rotates Steely 90° — use on vertical/portrait arcade cabinet displays."
        )
        self.chk_trophie_overlay_portrait.setStyleSheet("color: #E0E0E0;")
        self.chk_trophie_overlay_portrait.stateChanged.connect(
            self._on_trophie_overlay_portrait_toggled
        )
        grp_layout.addWidget(self.chk_trophie_overlay_portrait)

        self.chk_trophie_overlay_ccw = QCheckBox(
            "Rotate Counter-Clockwise (default: clockwise)"
        )
        self.chk_trophie_overlay_ccw.setChecked(
            bool(self.cfg.OVERLAY.get("trophie_overlay_rotate_ccw", False))
        )
        self.chk_trophie_overlay_ccw.setToolTip(
            "When Portrait Mode is on, rotate counter-clockwise (CCW) instead of clockwise."
        )
        self.chk_trophie_overlay_ccw.setStyleSheet("color: #E0E0E0;")
        self.chk_trophie_overlay_ccw.stateChanged.connect(
            self._on_trophie_overlay_ccw_toggled
        )
        grp_layout.addWidget(self.chk_trophie_overlay_ccw)

        # Gallery + preview split
        current_skin = self.cfg.OVERLAY.get("trophie_overlay_skin", "classic")
        split = self._build_skin_gallery_split(
            skins=STEELY_SKINS,
            current_skin=current_skin,
            draw_widget_factory=lambda parent: _PinballDrawWidget(parent, 120, 120),
            on_apply=self._apply_steely_skin,
            attr_prefix="steely",
        )
        grp_layout.addWidget(split)
        return grp

    # ── Gallery + preview panel builder ──────────────────────────────────────
    def _build_skin_gallery_split(
        self,
        skins: list,
        current_skin: str,
        draw_widget_factory,
        on_apply,
        attr_prefix: str,
    ) -> QWidget:
        """Return a horizontal widget: skin gallery (left ~65%) + live preview (right ~35%)."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(0, 4, 0, 4)
        h_layout.setSpacing(10)

        # ── Left: scrollable skin grid ────────────────────────────────────────
        gallery_scroll = QScrollArea()
        gallery_scroll.setWidgetResizable(True)
        gallery_scroll.setFrameShape(QFrame.Shape.NoFrame)
        gallery_scroll.setStyleSheet(_SCROLL_CSS)
        gallery_scroll.setMaximumHeight(260)

        gallery_inner = QWidget()
        gallery_inner.setStyleSheet("background-color: #161616;")
        grid = QGridLayout(gallery_inner)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(6)

        gallery_scroll.setWidget(gallery_inner)

        # ── Right: live preview ───────────────────────────────────────────────
        preview_panel = QWidget()
        preview_panel.setFixedWidth(160)
        preview_panel.setStyleSheet("background-color: #161616; border-radius: 6px;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(6)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        preview_lbl_title = QLabel("Live Preview")
        preview_lbl_title.setStyleSheet("color: #888; font-size: 8pt;")
        preview_lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(preview_lbl_title)

        # Container to centre the draw widget
        draw_container = QWidget()
        draw_container.setStyleSheet("background: transparent;")
        draw_h = QHBoxLayout(draw_container)
        draw_h.setContentsMargins(0, 0, 0, 0)
        draw_h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_widget = draw_widget_factory(draw_container)
        preview_widget.set_skin(current_skin)
        draw_h.addWidget(preview_widget)
        preview_layout.addWidget(draw_container)

        preview_skin_lbl = QLabel(_skin_name(skins, current_skin))
        preview_skin_lbl.setStyleSheet("color: #CCC; font-size: 8pt;")
        preview_skin_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(preview_skin_lbl)

        btn_apply = QPushButton("✓ Apply Skin")
        btn_apply.setStyleSheet(_BTN_APPLY_CSS)
        btn_apply.setEnabled(False)  # disabled until user selects a different skin
        preview_layout.addWidget(btn_apply)
        preview_layout.addStretch(1)

        # ── State bag for this gallery ─────────────────────────────────────────
        state = {
            "previewed": current_skin,
            "applied": current_skin,
            "cards": {},        # skin_id -> card QWidget
        }

        def _select_card(skin_id: str) -> None:
            state["previewed"] = skin_id
            preview_widget.set_skin(skin_id)
            preview_skin_lbl.setText(_skin_name(skins, skin_id))
            btn_apply.setEnabled(skin_id != state["applied"])
            _refresh_card_borders()

        def _refresh_card_borders() -> None:
            for sid, card in state["cards"].items():
                if sid == state["applied"]:
                    card.setStyleSheet(_CARD_APPLIED)
                elif sid == state["previewed"]:
                    card.setStyleSheet(_CARD_PREVIEW)
                else:
                    card.setStyleSheet(_CARD_NORMAL)

        def _apply() -> None:
            skin_id = state["previewed"]
            state["applied"] = skin_id
            on_apply(skin_id)
            btn_apply.setEnabled(False)
            _refresh_card_borders()

        btn_apply.clicked.connect(_apply)

        # Build skin cards
        COLS = 4
        for idx, skin in enumerate(skins):
            sid = skin["id"]
            card = _make_skin_card(skin, applied=(sid == current_skin))
            state["cards"][sid] = card

            def _make_handler(s=sid):
                def handler(_=None):
                    _select_card(s)
                return handler

            card.mousePressEvent = _make_handler()
            grid.addWidget(card, idx // COLS, idx % COLS)

        # Store refs for external use (e.g. after apply, update the live mascot)
        setattr(self, f"_{attr_prefix}_preview_widget", preview_widget)
        setattr(self, f"_{attr_prefix}_skin_state", state)

        h_layout.addWidget(gallery_scroll, 65)
        h_layout.addWidget(preview_panel, 35)
        return container

    # ── Apply handlers ─────────────────────────────────────────────────────────
    def _apply_trophie_skin(self, skin_id: str) -> None:
        self.cfg.OVERLAY["trophie_gui_skin"] = skin_id
        self.cfg.save()
        try:
            self._trophie_gui.set_skin(skin_id)
        except Exception:
            pass

    def _apply_steely_skin(self, skin_id: str) -> None:
        self.cfg.OVERLAY["trophie_overlay_skin"] = skin_id
        self.cfg.save()
        try:
            self._trophie_overlay.set_skin(skin_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _skin_name(skins: list, skin_id: str) -> str:
    for s in skins:
        if s["id"] == skin_id:
            return s["name"]
    return skin_id


def _make_skin_card(skin: dict, applied: bool = False) -> QWidget:
    """Build a single skin selection card (~80×90 px)."""
    card = QWidget()
    card.setObjectName("skinCard")
    card.setFixedSize(82, 92)
    if applied:
        card.setStyleSheet(_CARD_APPLIED)
    else:
        card.setStyleSheet(_CARD_NORMAL)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(2)

    icon_lbl = QLabel(skin["icon"])
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_lbl.setStyleSheet("font-size: 20pt; background: transparent; color: #E0E0E0;")
    layout.addWidget(icon_lbl)

    name_lbl = QLabel(skin["name"])
    name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    name_lbl.setStyleSheet("font-size: 7pt; color: #CCC; background: transparent;")
    name_lbl.setWordWrap(True)
    layout.addWidget(name_lbl)

    if applied:
        applied_lbl = QLabel("✅")
        applied_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        applied_lbl.setStyleSheet("font-size: 8pt; background: transparent;")
        layout.addWidget(applied_lbl)

    return card
