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

from PyQt6.QtCore import Qt, QTimer
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

# Ordered list of (title, overlay_type, effects_list) for the 2×3 grid
_OVERLAY_GROUPS = [
    ("🖥️ Main Overlay",         "main",      _MAIN_EFFECTS),
    ("🏆 Achievement Toast",     "toast",     _TOAST_EFFECTS),
    ("⚡ Challenge Select",      "challenge", _CHALLENGE_EFFECTS),
    ("⏱️ Timer / Countdown",     "timer",     _TIMER_EFFECTS),
    ("🌡️ Heat Barometer",        "heat",      _HEAT_EFFECTS),
    ("🔢 Flip Counter",          "flip",      _FLIP_EFFECTS),
]

# Mapping overlay_type → effects list (for solo-preview logic)
_OVERLAY_EFFECTS_MAP = {otype: effects for _, otype, effects in _OVERLAY_GROUPS}

# All 60 fx_* boolean keys (for Enable All / Disable All / Reset)
_ALL_FX_KEYS = [key for _, _otype, effects in _OVERLAY_GROUPS for key, _ in effects]


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
        for idx, (title, overlay_type, effects) in enumerate(_OVERLAY_GROUPS):
            row, col = divmod(idx, 3)
            grp = self._build_fx_group(title, effects, overlay_type)
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

    def _build_fx_group(self, title: str, effects: list, overlay_type: str) -> QGroupBox:
        grp = QGroupBox(title)
        outer_lay = QVBoxLayout(grp)
        outer_lay.setSpacing(4)
        outer_lay.setContentsMargins(6, 6, 6, 6)

        # ── ▶ Preview button in the group header ──────────────────────
        hdr = QHBoxLayout()
        hdr.addStretch(1)
        btn_prev = QPushButton("▶ Preview")
        btn_prev.setToolTip(
            "Open overlay in demo mode with all currently enabled effects (6 s)"
        )
        btn_prev.setFixedHeight(22)
        btn_prev.setStyleSheet(
            "QPushButton { background-color: #1a1a1a; color: #FF7F00;"
            " border: 1px solid #FF7F00; padding: 2px 8px; border-radius: 3px; font-size: 9pt; }"
            "QPushButton:hover { background-color: #FF7F00; color: #000; }"
        )
        btn_prev.clicked.connect(
            lambda _=False, ot=overlay_type: self._preview_overlay(ot)
        )
        hdr.addWidget(btn_prev)
        outer_lay.addLayout(hdr)

        # ── 3×3 grid of effect cells ───────────────────────────────────
        fx_grid = QGridLayout()
        fx_grid.setSpacing(4)
        n = len(effects)
        cols = 3
        full_rows, leftover = divmod(n, cols)
        for i, (key, label) in enumerate(effects):
            if i < full_rows * cols:
                grid_row, grid_col = divmod(i, cols)
            else:
                # Remaining effects centred in the last row
                extra_idx = i - full_rows * cols
                start_col = (cols - leftover) // 2
                grid_row = full_rows
                grid_col = start_col + extra_idx
            cell = self._build_fx_cell(key, label, overlay_type)
            fx_grid.addWidget(cell, grid_row, grid_col)

        outer_lay.addLayout(fx_grid)
        return grp

    def _build_fx_cell(self, key: str, label: str, overlay_type: str) -> QWidget:
        """Build one 3×3-grid cell for a single effect (label + checkbox + slider + % + 👁)."""
        enabled = bool(self.cfg.OVERLAY.get(key, True))
        intensity = int(self.cfg.OVERLAY.get(key + "_intensity", 80))

        cell = QWidget()
        cell_lay = QVBoxLayout(cell)
        cell_lay.setContentsMargins(4, 2, 4, 2)
        cell_lay.setSpacing(2)

        # Effect name label
        lbl = QLabel(label)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 8pt; font-weight: bold;")
        cell_lay.addWidget(lbl)

        # Controls row: [✓] [slider] [pct] [👁]
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)
        ctrl_row.setContentsMargins(0, 0, 0, 0)

        chk = QCheckBox()
        chk.setChecked(enabled)
        chk.setFixedWidth(18)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(intensity)
        slider.setToolTip("Effect intensity (0 – 100 %)")

        pct_lbl = QLabel(f"{intensity}%")
        pct_lbl.setFixedWidth(32)
        pct_lbl.setStyleSheet("color: #AAA; font-size: 8pt;")

        eye_btn = QPushButton("👁")
        eye_btn.setFixedSize(22, 22)
        eye_btn.setToolTip(f"Preview {label} in isolation (3 s)")
        eye_btn.setStyleSheet(
            "QPushButton { background-color: #1a1a1a; color: #00BFFF;"
            " border: 1px solid #00BFFF; border-radius: 3px; font-size: 10pt; padding: 0; }"
            "QPushButton:hover { background-color: #00BFFF; color: #000; }"
        )
        eye_btn.clicked.connect(
            lambda _=False, ot=overlay_type, k=key: self._preview_single_effect(ot, k)
        )

        # Wire up save callbacks
        chk.stateChanged.connect(
            lambda state, k=key: self._fx_save_checkbox(k, state)
        )
        slider.valueChanged.connect(
            lambda val, k=key, pl=pct_lbl: self._fx_save_slider(k, val, pl)
        )

        ctrl_row.addWidget(chk)
        ctrl_row.addWidget(slider, 1)
        ctrl_row.addWidget(pct_lbl)
        ctrl_row.addWidget(eye_btn)
        cell_lay.addLayout(ctrl_row)

        self._fx_effect_rows[key] = (chk, slider, pct_lbl)
        return cell

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

    # ------------------------------------------------------------------
    # Preview helpers
    # ------------------------------------------------------------------

    def _preview_overlay(self, overlay_type: str):
        """▶ Preview — open overlay in demo mode, all currently enabled effects (6 s)."""
        self._open_demo_overlay(overlay_type, solo_effect=None, duration_ms=6000)

    def _preview_single_effect(self, overlay_type: str, effect_key: str):
        """👁 Preview — open overlay with ONLY this one effect for 3 s."""
        self._open_demo_overlay(overlay_type, solo_effect=effect_key, duration_ms=3000)

    def _open_demo_overlay(self, overlay_type: str, solo_effect: str | None = None,
                           duration_ms: int = 6000):
        """Open an overlay in demo mode with simulated triggers.

        If *solo_effect* is set, temporarily disable all other effects for this
        overlay group, show only that single effect, then restore previous states.
        """
        # Lazy import avoids module-level circular dependency
        from ui_overlay import (
            AchToastWindow, ChallengeSelectOverlay, ChallengeCountdownOverlay,
            HeatBarometerOverlay, FlipCounterOverlay,
        )

        effects = _OVERLAY_EFFECTS_MAP.get(overlay_type, [])

        # 1. Save and optionally isolate
        saved: dict[str, object] = {}
        if solo_effect is not None:
            for key, _ in effects:
                saved[key] = self.cfg.OVERLAY.get(key, True)
                self.cfg.OVERLAY[key] = (key == solo_effect)

        def _restore():
            for k, v in saved.items():
                self.cfg.OVERLAY[k] = v

        # 2. Open the appropriate overlay and wire simulated triggers
        win = None
        timers: list[QTimer] = []

        def _add_shot(delay_ms: int, fn):
            t = QTimer()
            t.setSingleShot(True)
            t.timeout.connect(fn)
            t.start(delay_ms)
            timers.append(t)

        try:
            if overlay_type == "toast":
                win = AchToastWindow(self, "🏆 Preview Effect", "demo", seconds=5)

            elif overlay_type == "challenge":
                win = ChallengeSelectOverlay(self, selected_idx=0)
                for i, delay in enumerate([1500, 3000, 4500], start=1):
                    _add_shot(delay, lambda _=False, idx=i % 4: (
                        win.set_selected(idx) if win and not win.isHidden() else None
                    ))

            elif overlay_type == "timer":
                win = ChallengeCountdownOverlay(self, total_seconds=5)

            elif overlay_type == "heat":
                win = HeatBarometerOverlay(self)
                win.set_heat(50)
                for heat, delay in [(65, 1500), (85, 3000), (95, 4500), (60, 5500)]:
                    _add_shot(delay, lambda _=False, h=heat: (
                        win.set_heat(h) if win and not win.isHidden() else None
                    ))

            elif overlay_type == "flip":
                win = FlipCounterOverlay(self, total=0, remaining=100, goal=100)
                for flips, delay in [(8, 500), (16, 1000), (25, 1500),
                                     (33, 2000), (50, 2500), (66, 3500),
                                     (75, 4000), (84, 4500), (100, 5500)]:
                    _add_shot(delay, lambda _=False, f=flips: (
                        win.update_counts(f, max(0, 100 - f), 100)
                        if win and not win.isHidden() else None
                    ))

            elif overlay_type == "main":
                # Main overlay: show the existing overlay window briefly
                try:
                    if getattr(self, "overlay", None) is None:
                        from ui_overlay import OverlayWindow
                        self.overlay = OverlayWindow(self)
                    self.overlay.show()
                    self.overlay.raise_()
                    win = self.overlay
                    # Auto-hide instead of close for the main overlay
                    _add_shot(duration_ms, lambda: (
                        self.overlay.hide() if getattr(self, "overlay", None) else None
                    ))
                    _restore()
                    return
                except Exception:
                    _restore()
                    return

        except Exception:
            _restore()
            return

        if win is None:
            _restore()
            return

        # 3. Auto-close after duration and restore states
        def _close_and_restore():
            try:
                if win and not win.isHidden():
                    win.close()
            except Exception:
                pass
            _restore()
            for t in timers:
                try:
                    t.stop()
                except Exception:
                    pass

        QTimer.singleShot(duration_ms, _close_and_restore)

