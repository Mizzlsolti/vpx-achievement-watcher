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


_DUEL_EFFECTS = [
    ("fx_duel_breathing_glow",  "Breathing Glow Border"),
    ("fx_duel_slide_motion",    "Slide-In / Slide-Out Motion"),
    ("fx_duel_energy_flash",    "Energy Flash"),
    ("fx_duel_color_morph",     "Color Morph"),
    ("fx_duel_glow_sweep",      "Glow Sweep"),
]


# Ordered list of (title, overlay_type, effects_list) for the 2×3 grid
_OVERLAY_GROUPS = [
    ("🖥️ Main Overlay",         "main",      _MAIN_EFFECTS),
    ("🏆 Achievement Toast",     "toast",     _TOAST_EFFECTS),
    ("⚔️ Duel Overlay",          "duel",      _DUEL_EFFECTS),
]

# All 60 fx_* boolean keys (for Enable All / Disable All / Reset)
_ALL_FX_KEYS = [key for _, _otype, effects in _OVERLAY_GROUPS for key, _ in effects]

# Effects where the intensity slider has no visible impact — show only Checkbox
_NO_SLIDER_EFFECTS: frozenset[str] = frozenset({
    # Main Overlay — non-particle/shake effects
    "fx_main_page_transition",
    "fx_main_glitch_frame",
    "fx_main_score_spin",
    "fx_main_progress_fill",
    "fx_main_shine_sweep",
    "fx_main_highlight_flash",
    "fx_main_nav_arrows_pulse",
    "fx_main_accent_lerp",
    # Achievement Toast — fixed speed/distance/alpha effects
    "fx_toast_typewriter",
    "fx_toast_icon_bounce",
    "fx_toast_slide_motion",
    "fx_toast_energy_flash",
    "fx_toast_hologram_flicker",
    # Duel Overlay — easing/alpha-only effects
    "fx_duel_slide_motion",
    "fx_duel_energy_flash",
    "fx_duel_color_morph",
    "fx_duel_glow_sweep",
    # Score Duel result — easing/alpha-only effects
    # Timer — subtle/alpha-only effects
    # Heat Barometer — threshold-based or alpha-only
    # Flip Counter — fixed speed/alpha/non-OpenGL effects
})


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
        self._fx_post_rows: dict = {}    # key → (checkbox, slider, pct_label)
        self._fx_pp_overlay_btns: dict = {}  # overlay_type → QPushButton
        self._fx_group_widgets: dict = {}  # overlay_type → QGroupBox
        self._fx_scroll = scroll

        grid = QGridLayout()
        grid.setSpacing(8)
        for idx, (title, overlay_type, effects) in enumerate(_OVERLAY_GROUPS):
            row, col = divmod(idx, 3)
            grp = self._build_fx_group(title, effects, overlay_type)
            self._fx_group_widgets[overlay_type] = grp
            grid.addWidget(grp, row, col)
        layout.addLayout(grid)

        # --- Post-Processing section ---
        layout.addWidget(self._build_fx_post_group())

        # --- Bottom buttons: Enable All / Disable All / Preview All ---
        btn_row = QHBoxLayout()
        self._fx_btn_enable = QPushButton("Enable All")
        self._fx_btn_enable.setToolTip("Enable all 60 individual effects")
        self._fx_btn_enable.clicked.connect(lambda: self._fx_set_all(True))
        self._fx_btn_disable = QPushButton("Disable All")
        self._fx_btn_disable.setToolTip("Disable all 60 individual effects")
        self._fx_btn_disable.clicked.connect(lambda: self._fx_set_all(False))
        for b in (self._fx_btn_enable, self._fx_btn_disable):
            b.setStyleSheet(
                "QPushButton { background-color: #1a1a1a; color: #FF7F00; border: 1px solid #FF7F00;"
                " padding: 4px 14px; border-radius: 4px; }"
                "QPushButton:hover { background-color: #FF7F00; color: #000; }"
            )
            btn_row.addWidget(b)
        self._fx_btn_preview_all = QPushButton("▶ Preview All")
        self._fx_btn_preview_all.setToolTip("Open all overlay windows (including Main Overlay) simultaneously to preview all effects")
        self._fx_btn_preview_all.clicked.connect(self._preview_all_overlays)
        self._fx_btn_preview_all.setStyleSheet(
            "QPushButton { background-color: #1a1a1a; color: #00E5FF; border: 1px solid #00E5FF;"
            " padding: 4px 14px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #00E5FF; color: #000; }"
        )
        btn_row.addWidget(self._fx_btn_preview_all)
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
        """Build one 3×3-grid cell for a single effect.

        Effects in ``_NO_SLIDER_EFFECTS`` get only ``[✓] Label``.
        All other effects get the full ``[✓] Label ──●── 80%`` row.
        """
        enabled = bool(self.cfg.OVERLAY.get(key, True))
        has_slider = key not in _NO_SLIDER_EFFECTS

        cell = QWidget()
        cell_lay = QVBoxLayout(cell)
        cell_lay.setContentsMargins(4, 2, 4, 2)
        cell_lay.setSpacing(2)

        # Effect name label
        lbl = QLabel(label)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 8pt; font-weight: bold;")
        cell_lay.addWidget(lbl)

        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)
        ctrl_row.setContentsMargins(0, 0, 0, 0)

        chk = QCheckBox()
        chk.setChecked(enabled)
        chk.setFixedWidth(18)
        chk.stateChanged.connect(
            lambda state, k=key: self._fx_save_checkbox(k, state)
        )

        ctrl_row.addWidget(chk)

        if has_slider:
            intensity = int(self.cfg.OVERLAY.get(key + "_intensity", 80))

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(intensity)
            slider.setToolTip("Effect intensity (0 – 100 %)")

            pct_lbl = QLabel(f"{intensity}%")
            pct_lbl.setFixedWidth(32)
            pct_lbl.setStyleSheet("color: #AAA; font-size: 8pt;")

            slider.valueChanged.connect(
                lambda val, k=key, pl=pct_lbl: self._fx_save_slider(k, val, pl)
            )

            ctrl_row.addWidget(slider, 1)
            ctrl_row.addWidget(pct_lbl)
        else:
            ctrl_row.addStretch(1)
            slider = None
            pct_lbl = None

        cell_lay.addLayout(ctrl_row)

        self._fx_effect_rows[key] = (chk, slider, pct_lbl)
        return cell

    # ------------------------------------------------------------------
    # Post-Processing group builder
    # ------------------------------------------------------------------

    # Post-processing effect definitions: (config_key, display_label, default_intensity)
    _POST_EFFECTS = [
        ("fx_post_bloom",                "Bloom",                60),
        ("fx_post_motion_blur",          "Motion Blur",          60),
        ("fx_post_chromatic_aberration", "Chromatic Aberration", 50),
        ("fx_post_vignette",             "Vignette",             60),
        ("fx_post_film_grain",           "Film Grain",           40),
        ("fx_post_scanlines",            "Scanlines",            50),
    ]

    def _build_fx_post_group(self) -> QGroupBox:
        """Build the 🎬 Post-Processing QGroupBox with a 2×3 grid of effect cells."""
        grp = QGroupBox("🎬 Post-Processing")
        outer_lay = QVBoxLayout(grp)
        outer_lay.setSpacing(6)
        outer_lay.setContentsMargins(8, 8, 8, 8)

        desc = QLabel(
            "Screen-space effects applied on top of overlay windows. "
            "Requires OpenGL. Disabled automatically in Low Performance Mode."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #AAA; font-size: 8pt;")
        outer_lay.addWidget(desc)

        post_grid = QGridLayout()
        post_grid.setSpacing(4)
        for idx, (key, label, default_intensity) in enumerate(self._POST_EFFECTS):
            row, col = divmod(idx, 3)
            cell = self._build_fx_post_cell(key, label, default_intensity)
            post_grid.addWidget(cell, row, col)
        outer_lay.addLayout(post_grid)

        # --- Per-overlay toggle buttons ---
        apply_lbl = QLabel("Apply Post-Processing to:")
        apply_lbl.setStyleSheet("color: #CCC; font-size: 8pt; font-weight: bold;")
        outer_lay.addWidget(apply_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        _OVERLAY_TOGGLES = [
            ("pp_overlay_main",      "🖥️ Main",      True),
            ("pp_overlay_toast",     "🏆 Toast",     True),
            ("pp_overlay_duel",      "⚔️ Duel",      True),
        ]
        _style_on = (
            "QPushButton { background-color: #1a1a1a; color: #FF7F00;"
            " border: 2px solid #FF7F00; padding: 2px 6px; border-radius: 3px;"
            " font-size: 8pt; }"
            "QPushButton:hover { background-color: #FF7F00; color: #000; }"
        )
        _style_off = (
            "QPushButton { background-color: #1a1a1a; color: #555;"
            " border: 1px solid #333; padding: 2px 6px; border-radius: 3px;"
            " font-size: 8pt; }"
            "QPushButton:hover { background-color: #2a2a2a; color: #888; }"
        )
        for cfg_key, btn_label, _default in _OVERLAY_TOGGLES:
            active = bool(self.cfg.OVERLAY.get(cfg_key, _default))
            btn = QPushButton(btn_label)
            btn.setCheckable(True)
            btn.setChecked(active)
            btn.setFixedHeight(26)
            btn.setStyleSheet(_style_on if active else _style_off)
            btn.toggled.connect(
                lambda checked, k=cfg_key, b=btn, son=_style_on, soff=_style_off:
                    self._fx_save_pp_overlay_toggle(k, checked, b, son, soff)
            )
            btn_row.addWidget(btn)
            self._fx_pp_overlay_btns[cfg_key] = btn
        btn_row.addStretch(1)
        outer_lay.addLayout(btn_row)
        return grp

    def _build_fx_post_cell(self, key: str, label: str, default_intensity: int) -> QWidget:
        """Build one post-processing effect cell with checkbox + slider."""
        enabled = bool(self.cfg.OVERLAY.get(key, False))
        intensity = int(self.cfg.OVERLAY.get(key + "_intensity", default_intensity))

        cell = QWidget()
        cell_lay = QVBoxLayout(cell)
        cell_lay.setContentsMargins(4, 2, 4, 2)
        cell_lay.setSpacing(2)

        lbl = QLabel(label)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 8pt; font-weight: bold;")
        cell_lay.addWidget(lbl)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)
        ctrl_row.setContentsMargins(0, 0, 0, 0)

        chk = QCheckBox()
        chk.setChecked(enabled)
        chk.setFixedWidth(18)
        chk.stateChanged.connect(
            lambda state, k=key: self._fx_save_checkbox(k, state)
        )
        ctrl_row.addWidget(chk)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(intensity)
        slider.setToolTip("Effect intensity (0 – 100 %)")

        pct_lbl = QLabel(f"{intensity}%")
        pct_lbl.setFixedWidth(32)
        pct_lbl.setStyleSheet("color: #AAA; font-size: 8pt;")

        slider.valueChanged.connect(
            lambda val, k=key, pl=pct_lbl: self._fx_save_slider(k, val, pl)
        )

        ctrl_row.addWidget(slider, 1)
        ctrl_row.addWidget(pct_lbl)
        cell_lay.addLayout(ctrl_row)

        self._fx_post_rows[key] = (chk, slider, pct_lbl)
        return cell

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def _fx_save_checkbox(self, key: str, state: int):
        enabled = bool(Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY[key] = enabled
        self.cfg.save()
        if enabled and key.startswith("fx_post_"):
            try:
                if getattr(self, "_trophie_gui", None):
                    self._trophie_gui.on_postproc_enabled()
            except Exception:
                pass

    def _fx_save_slider(self, key: str, value: int, pct_lbl: QLabel):
        pct_lbl.setText(f"{value}%")
        self.cfg.OVERLAY[key + "_intensity"] = int(value)
        self.cfg.save()

    def _fx_save_low_perf(self, state: int):
        enabled = bool(Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["low_performance_mode"] = enabled
        self.cfg.save()
        self._fx_apply_low_perf_state(enabled)
        if enabled:
            try:
                if getattr(self, "_trophie_gui", None):
                    self._trophie_gui.on_low_perf_enabled()
            except Exception:
                pass

    def _fx_save_pp_overlay_toggle(self, key: str, checked: bool, btn, style_on: str, style_off: str):
        self.cfg.OVERLAY[key] = checked
        self.cfg.save()
        btn.setStyleSheet(style_on if checked else style_off)

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

    def _fx_apply_low_perf_state(self, low_perf: bool):
        """Enable or disable all individual effect controls based on low_perf flag."""
        self._fx_apply_row_enabled(self._fx_effect_rows, not low_perf)
        self._fx_apply_row_enabled(self._fx_post_rows, not low_perf)
        self._fx_btn_enable.setEnabled(not low_perf)
        self._fx_btn_disable.setEnabled(not low_perf)
        for btn in getattr(self, '_fx_pp_overlay_btns', {}).values():
            btn.setEnabled(not low_perf)

    def _fx_apply_row_enabled(self, rows: dict, enabled: bool):
        """Enable or disable all controls in a row dict (key → (chk, slider, pct_lbl))."""
        for _key, (chk, slider, pct_lbl) in rows.items():
            chk.setEnabled(enabled)
            if slider is not None:
                slider.setEnabled(enabled)
            if pct_lbl is not None:
                pct_lbl.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Preview helpers
    # ------------------------------------------------------------------

    def _preview_overlay(self, overlay_type: str):
        """▶ Preview — open overlay in demo mode, all currently enabled effects (6 s)."""
        self._open_demo_overlay(overlay_type, duration_ms=6000)

    def _preview_all_overlays(self):
        """▶ Preview All — open all overlay windows simultaneously for 6 seconds."""
        for overlay_type in ("main", "toast", "duel"):
            self._open_demo_overlay(overlay_type, duration_ms=6000)

    def _open_demo_overlay(self, overlay_type: str, duration_ms: int = 6000):
        """Open an overlay in demo mode with simulated triggers."""
        # Lazy import avoids module-level circular dependency
        from .overlay import (
            AchToastWindow,
        )

        # Open the appropriate overlay and wire simulated triggers
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
                win = AchToastWindow(self, "🏆 Preview Effect", "__levelup__", seconds=5)

            elif overlay_type == "duel":
                from .overlay_duel import DuelInfoOverlay
                if not hasattr(self, "_duel_overlay") or self._duel_overlay is None:
                    self._duel_overlay = DuelInfoOverlay(self)
                win = self._duel_overlay
                win.show_info("⚔️ Duel active against xPinballWizard!\n🎰 Medieval Madness\n⚠️ One game only — restarting in-game will abort the duel!\n🔙 After the duel, close VPX or return to Popper.", seconds=6)

            elif overlay_type == "main":
                # Main overlay: show the existing overlay window with demo triggers
                try:
                    if getattr(self, "overlay", None) is None:
                        from .overlay import OverlayWindow
                        self.overlay = OverlayWindow(self)
                    win = self.overlay

                    # Demo data for page 1 and page 2 (used in the transition)
                    _demo_p1 = {
                        "players": [{
                            "id": 1, "playtime_sec": 300, "score": 10000,
                            "deltas": {"Ramps": 5, "Jackpots": 2},
                            "highlights": {
                                "Power": ["🔥 Top Shot – 5k"],
                                "Precision": ["🎯 Combo – 2"],
                            },
                        }],
                        "_demo_total_achs": 10,
                        "_demo_unlocked": 3,
                    }
                    _demo_p2 = {
                        "players": [{
                            "id": 1, "playtime_sec": 300, "score": 10000,
                            "deltas": {"Ramps": 8, "Jackpots": 4},
                            "highlights": {
                                "Power": ["🔥 Multiball – 8k"],
                                "Precision": ["🎯 Skill Shot – 4"],
                            },
                        }],
                        "_demo_total_achs": 10,
                        "_demo_unlocked": 6,
                    }
                    _demo_scored = {
                        "players": [{
                            "id": 1, "playtime_sec": 300, "score": 10500,
                            "deltas": {"Ramps": 8, "Jackpots": 4},
                            "highlights": {
                                "Power": ["🔥 Multiball – 8k"],
                                "Precision": ["🎯 Skill Shot – 4"],
                            },
                        }],
                        "_demo_total_achs": 10,
                        "_demo_unlocked": 8,
                    }

                    # Reset animation counters for a clean demo start
                    try:
                        win._score_display = 0
                        win._score_target = 0
                        win._progress_pct_current = 0.0
                        win._progress_pct_target = -1.0
                    except Exception:
                        pass

                    win.set_combined(_demo_p1, "Demo Preview")
                    win.show()
                    win.raise_()

                    # Force-start the effects widget animation timer so the
                    # breathing glow and floating particles are visible immediately.
                    try:
                        ew = win._effects_widget
                        if not ew.isVisible():
                            ew.setGeometry(0, 0, win.width(), win.height())
                            ew.show()
                            ew.raise_()
                        if not ew._particles:
                            ew._init_particles()
                        if not ew._tick_timer.isActive():
                            ew._tick_timer.start()
                    except Exception:
                        pass

                    # Show nav arrows immediately so the pulsing animation is
                    # visible throughout the first half of the demo.
                    try:
                        win._nav_arrows.setGeometry(0, 0, win.width(), win.height())
                        win._nav_arrows.show()
                        win._nav_arrows.raise_()
                    except Exception:
                        pass

                    # Helper: animate the progress bar to a specific target percentage.
                    # (triggers Progress Bar Fill + Shine/Sweep each call)
                    def _demo_progress_step(target_pct: float):
                        if not win or win.isHidden():
                            return
                        try:
                            win._progress_pct_current = max(0.0, getattr(win, "_progress_pct_target", 0.0))
                            win._progress_pct_target = target_pct
                            if self.cfg.OVERLAY.get("fx_main_progress_fill", True):
                                if hasattr(win, "_progress_bar_timer"):
                                    win._progress_bar_timer.start()
                            else:
                                win._progress_pct_current = target_pct
                            if self.cfg.OVERLAY.get("fx_main_shine_sweep", True):
                                win._trigger_shine()
                        except Exception:
                            pass

                    # 1s: progress 0 → 20%
                    _add_shot(1000, lambda: _demo_progress_step(20.0))

                    # 2s: simulate page transition
                    # (triggers Page Slide+Fade, Glitch Frame, Accent Color Lerp)
                    _add_shot(2000, lambda: (
                        win.transition_to(
                            lambda: win.set_combined(_demo_p2, "Demo — Page 2")
                        )
                        if win and not win.isHidden() else None
                    ))

                    # 2.5s: progress 20 → 50%
                    _add_shot(2500, lambda: _demo_progress_step(50.0))

                    # 3s: simulate score change +500
                    # (triggers Score Counter Spin, Value Highlight Flash)
                    _add_shot(3000, lambda: (
                        win.set_combined(_demo_scored, "Demo — Score")
                        if win and not win.isHidden() else None
                    ))

                    # 3s: hide nav arrows after ~3s of visible pulsing
                    _add_shot(3000, lambda: (
                        win._nav_arrows.hide()
                        if win and not win.isHidden() else None
                    ))

                    # 4s: progress 50 → 80%
                    _add_shot(4000, lambda: _demo_progress_step(80.0))

                    # 4.5s: second page transition (direction='right')
                    # Triggers Glitch Frame + Accent Color Lerp a second time so
                    # both effects are clearly demonstrated during the preview.
                    _add_shot(4500, lambda: (
                        win.transition_to(
                            lambda: win.set_combined(_demo_p1, "Demo — Page 1"),
                            direction='right',
                        )
                        if win and not win.isHidden() else None
                    ))

                    # 5s: progress 80 → 100%
                    _add_shot(5000, lambda: _demo_progress_step(100.0))

                    # Auto-hide (not close) at duration_ms
                    def _hide_overlay():
                        try:
                            if win and not win.isHidden():
                                win.hide()
                        except Exception:
                            pass
                        for t in timers:
                            try:
                                t.stop()
                            except Exception:
                                pass

                    QTimer.singleShot(duration_ms, _hide_overlay)
                    return  # Bypass generic auto-close below
                except Exception:
                    return

        except Exception:
            return

        if win is None:
            return

        # Auto-close after duration
        def _close_overlay():
            try:
                if win and not win.isHidden():
                    win.close()
            except Exception:
                pass
            for t in timers:
                try:
                    t.stop()
                except Exception:
                    pass

        QTimer.singleShot(duration_ms, _close_overlay)

