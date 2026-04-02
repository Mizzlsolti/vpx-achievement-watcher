"""ui_effects.py – ✨ Effects sub-tab mixin for the Appearance tab.

Provides the EffectsMixin class which builds the Effects sub-tab containing
granular enable/disable controls and intensity sliders for every visual effect
on every overlay (60 effects total: 10 per overlay × 6 overlays).

The mixin expects the host class to provide:
    self.cfg            – AppConfig instance
    self.main_tabs      – QTabWidget (main tab bar)
    self._add_tab_help_button(layout, key)  – adds the Help button to a tab layout
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget, QGridLayout,
)

# ---------------------------------------------------------------------------
# Effect definitions: (config_key, display_label)
# ---------------------------------------------------------------------------
_MAIN_EFFECTS = [
    ("fx_main_breathing_glow",      "Breathing Glow Border"),
    ("fx_main_floating_particles",  "Floating Particles"),
    ("fx_main_page_transition",     "Page Slide+Fade Transition"),
    ("fx_main_glitch_frame",        "Glitch Frame Transition"),
    ("fx_main_score_spin",          "Score Counter Spin"),
    ("fx_main_progress_fill",       "Progress Bar Smooth Fill"),
    ("fx_main_shine_sweep",         "Shine / Sweep Effect"),
    ("fx_main_highlight_flash",     "Value Highlight Flash"),
    ("fx_main_nav_arrows_pulse",    "Nav Arrows Pulse"),
    ("fx_main_accent_lerp",         "Page Accent Color Lerp"),
]

_TOAST_EFFECTS = [
    ("fx_toast_burst_particles",    "Burst Particles"),
    ("fx_toast_neon_rings",         "Neon Ring Expansion"),
    ("fx_toast_typewriter",         "Typewriter Title Reveal"),
    ("fx_toast_icon_bounce",        "Icon Bounce"),
    ("fx_toast_slide_motion",       "Slide-In / Slide-Out Motion"),
    ("fx_toast_energy_flash",       "Energy Flash (Level-Up)"),
    ("fx_toast_god_rays",           "Radial God-Ray Burst ✨"),
    ("fx_toast_confetti",           "Confetti Shower ✨"),
    ("fx_toast_hologram_flicker",   "Icon Hologram Flicker ✨"),
    ("fx_toast_shockwave",          "Shockwave Ripple ✨"),
]

_CHALLENGE_EFFECTS = [
    ("fx_challenge_carousel",       "Carousel Slide Animation"),
    ("fx_challenge_selection_glow", "Pulsating Selection Glow"),
    ("fx_challenge_arrow_wobble",   "Arrow Wobble Pulse"),
    ("fx_challenge_glow_border",    "Glow Border Breathing"),
    ("fx_challenge_snap_scale",     "Selection Snap Scale"),
    ("fx_challenge_electric_arc",   "Electric Arc Between Options ✨"),
    ("fx_challenge_hover_shimmer",  "Option Hover Shimmer ✨"),
    ("fx_challenge_plasma_noise",   "Background Plasma Noise ✨"),
    ("fx_challenge_holo_sweep",     "Title Holographic Sweep ✨"),
    ("fx_challenge_color_pulse",    "Difficulty Color Pulse ✨"),
]

_TIMER_EFFECTS = [
    ("fx_timer_321go",              "3-2-1-GO Scale + Glow"),
    ("fx_timer_number_spin",        "Countdown Number Spin"),
    ("fx_timer_radial_pulse",       "Background Radial Pulse"),
    ("fx_timer_glow_border",        "Timer Glow Border"),
    ("fx_timer_urgency_shake",      "Urgency Shake (last 5 s) ✨"),
    ("fx_timer_warp_distortion",    "Time Warp Distortion ✨"),
    ("fx_timer_trail_afterimage",   "Countdown Trail Afterimage ✨"),
    ("fx_timer_final_explosion",    "Final Second Explosion ✨"),
    ("fx_timer_pulse_ring",         "Pulse Ring Countdown ✨"),
    ("fx_timer_glitch_numbers",     "Digital Glitch Numbers ✨"),
]

_HEAT_EFFECTS = [
    ("fx_heat_warning_pulse",       "Warning Pulse (65 %+)"),
    ("fx_heat_critical_pulse",      "Critical Pulse (85 %+)"),
    ("fx_heat_glow_border",         "Glow Border Breathing"),
    ("fx_heat_gradient_anim",       "Heat Bar Gradient Animation"),
    ("fx_heat_flame_particles",     "Flame Particle Emission ✨"),
    ("fx_heat_shimmer",             "Heat Shimmer / Distortion ✨"),
    ("fx_heat_smoke_wisps",         "Smoke Wisp Particles ✨"),
    ("fx_heat_lava_glow",           "Lava Glow Edge ✨"),
    ("fx_heat_number_throb",        "Temperature Number Throb ✨"),
    ("fx_heat_meltdown_shake",      "Meltdown Screen Shake ✨"),
]

_FLIP_EFFECTS = [
    ("fx_flip_breathing_glow",      "Breathing Glow Ring"),
    ("fx_flip_counter_spin",        "Counter Spin Animation"),
    ("fx_flip_glow_border",         "Glow Border"),
    ("fx_flip_progress_arc",        "Progress Arc Animation"),
    ("fx_flip_impact_pulse",        "Flip Impact Pulse ✨"),
    ("fx_flip_number_cascade",      "Number Cascade Roll ✨"),
    ("fx_flip_milestone_burst",     "Milestone Burst ✨"),
    ("fx_flip_electric_spark",      "Electric Counter Spark ✨"),
    ("fx_flip_goal_glow",           "Goal Proximity Glow Intensify ✨"),
    ("fx_flip_completion_firework", "Completion Firework ✨"),
]

# Ordered list of (title, effects_list) for the 2×3 grid
_OVERLAY_GROUPS = [
    ("🖥️ Main Overlay",             _MAIN_EFFECTS),
    ("🏆 Achievement Toast",         _TOAST_EFFECTS),
    ("⚡ Challenge Select",          _CHALLENGE_EFFECTS),
    ("⏱️ Timer / Countdown",         _TIMER_EFFECTS),
    ("🌡️ Heat Barometer",            _HEAT_EFFECTS),
    ("🔢 Flip Counter",              _FLIP_EFFECTS),
]

# All 60 fx_* boolean keys (for Enable All / Disable All / Reset)
_ALL_FX_KEYS = [key for _, effects in _OVERLAY_GROUPS for key, _ in effects]


class EffectsMixin:
    """Mixin that provides the ✨ Effects sub-tab for the Appearance tab.

    Expects the host class to provide:
        self.cfg                        – AppConfig instance
        self.appearance_subtabs         – QTabWidget (Appearance sub-tab bar)
        self._add_tab_help_button(layout, key)
    """

    def _build_effects_subtab(self):
        """Build and register the ✨ Effects sub-tab."""
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(8)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # --- Master: Low Performance Mode ---
        grp_master = QGroupBox()
        lay_master = QHBoxLayout(grp_master)
        self._fx_chk_low_perf = QCheckBox(
            "🔋 Low Performance Mode — disables ALL effects (overrides all individual toggles below)"
        )
        self._fx_chk_low_perf.setChecked(bool(self.cfg.OVERLAY.get("low_performance_mode", False)))
        self._fx_chk_low_perf.stateChanged.connect(self._fx_save_low_perf)
        lay_master.addWidget(self._fx_chk_low_perf)
        layout.addWidget(grp_master)

        # --- 2×3 grid of overlay group-boxes ---
        self._fx_effect_rows: dict = {}  # key → (checkbox, slider, pct_label)

        grid = QGridLayout()
        grid.setSpacing(8)
        for idx, (title, effects) in enumerate(_OVERLAY_GROUPS):
            row, col = divmod(idx, 3)
            grp = self._build_fx_group(title, effects)
            grid.addWidget(grp, row, col)
        layout.addLayout(grid)

        # --- Bottom buttons: Enable All / Disable All / Reset ---
        btn_row = QHBoxLayout()
        btn_enable = QPushButton("Enable All")
        btn_enable.setToolTip("Enable all 60 individual effects")
        btn_enable.clicked.connect(lambda: self._fx_set_all(True))
        btn_disable = QPushButton("Disable All")
        btn_disable.setToolTip("Disable all 60 individual effects")
        btn_disable.clicked.connect(lambda: self._fx_set_all(False))
        btn_reset = QPushButton("Reset to Defaults")
        btn_reset.setToolTip("Restore all effects to enabled state at 80 % intensity")
        btn_reset.clicked.connect(self._fx_reset_defaults)
        for b in (btn_enable, btn_disable, btn_reset):
            b.setStyleSheet(
                "QPushButton { background-color: #1a1a1a; color: #FF7F00; border: 1px solid #FF7F00;"
                " padding: 4px 14px; border-radius: 4px; }"
                "QPushButton:hover { background-color: #FF7F00; color: #000; }"
            )
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "appearance_effects")

        # Initial enabled-state of all controls based on low_performance_mode
        self._fx_apply_low_perf_state(bool(self.cfg.OVERLAY.get("low_performance_mode", False)))

        self.appearance_subtabs.addTab(tab, "✨ Effects")

    # ------------------------------------------------------------------
    # Group-box builder
    # ------------------------------------------------------------------

    def _build_fx_group(self, title: str, effects: list) -> QGroupBox:
        grp = QGroupBox(title)
        lay = QVBoxLayout(grp)
        lay.setSpacing(2)

        for key, label in effects:
            enabled = bool(self.cfg.OVERLAY.get(key, True))
            intensity = int(self.cfg.OVERLAY.get(key + "_intensity", 80))

            row_widget = QWidget()
            row_lay = QHBoxLayout(row_widget)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(6)

            chk = QCheckBox()
            chk.setChecked(enabled)
            chk.setFixedWidth(20)

            lbl = QLabel(label)
            lbl.setMinimumWidth(200)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(intensity)
            slider.setFixedWidth(100)
            slider.setToolTip("Effect intensity (0 – 100 %)")

            pct_lbl = QLabel(f"{intensity}%")
            pct_lbl.setFixedWidth(36)
            pct_lbl.setStyleSheet("color: #AAA; font-size: 9pt;")

            # Wire up
            chk.stateChanged.connect(
                lambda state, k=key: self._fx_save_checkbox(k, state)
            )
            slider.valueChanged.connect(
                lambda val, k=key, pl=pct_lbl: self._fx_save_slider(k, val, pl)
            )

            row_lay.addWidget(chk)
            row_lay.addWidget(lbl, 1)
            row_lay.addWidget(slider)
            row_lay.addWidget(pct_lbl)

            lay.addWidget(row_widget)
            self._fx_effect_rows[key] = (chk, slider, pct_lbl)

        return grp

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def _fx_save_checkbox(self, key: str, state: int):
        self.cfg.OVERLAY[key] = bool(Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.save()

    def _fx_save_slider(self, key: str, value: int, pct_lbl: QLabel):
        pct_lbl.setText(f"{value}%")
        self.cfg.OVERLAY[key + "_intensity"] = int(value)
        self.cfg.save()

    def _fx_save_low_perf(self, state: int):
        enabled = bool(Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["low_performance_mode"] = enabled
        self.cfg.save()
        self._fx_apply_low_perf_state(enabled)

    # ------------------------------------------------------------------
    # Bulk actions
    # ------------------------------------------------------------------

    def _fx_set_all(self, value: bool):
        for key in _ALL_FX_KEYS:
            self.cfg.OVERLAY[key] = value
            row = self._fx_effect_rows.get(key)
            if row:
                chk, _, _ = row
                chk.blockSignals(True)
                chk.setChecked(value)
                chk.blockSignals(False)
        self.cfg.save()

    def _fx_reset_defaults(self):
        for key in _ALL_FX_KEYS:
            self.cfg.OVERLAY[key] = True
            self.cfg.OVERLAY[key + "_intensity"] = 80
            row = self._fx_effect_rows.get(key)
            if row:
                chk, slider, pct_lbl = row
                chk.blockSignals(True)
                slider.blockSignals(True)
                chk.setChecked(True)
                slider.setValue(80)
                pct_lbl.setText("80%")
                chk.blockSignals(False)
                slider.blockSignals(False)
        self.cfg.save()

    def _fx_apply_low_perf_state(self, low_perf: bool):
        """Enable or disable all individual effect controls based on low_perf flag."""
        for key, (chk, slider, pct_lbl) in self._fx_effect_rows.items():
            chk.setEnabled(not low_perf)
            slider.setEnabled(not low_perf)
            pct_lbl.setEnabled(not low_perf)
