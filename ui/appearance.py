"""Appearance-tab mixin: overlay placement, orientation, font, sound, and theme handlers."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QCheckBox, QGroupBox, QScrollArea, QFrame, QFontComboBox, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QSlider, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.theme import generate_stylesheet, list_themes, get_theme, DEFAULT_THEME
from core.watcher_core import apply_tooltips
import core.sound as sound
from .overlay import (
    ToastPositionPicker,
    OverlayPositionPicker,
    MiniInfoPositionPicker,
    StatusOverlayPositionPicker,
    DuelOverlayPositionPicker,
)
from .effects import EffectsMixin
from .mascots import MascotsMixin


class AppearanceMixin(MascotsMixin, EffectsMixin):
    """Mixin that provides the Appearance tab (Overlay, Theme, Sound sub-tabs) and all
    related placement, orientation, font, and theme handler methods.

    Expects the host class to provide:
        self.cfg            – AppConfig instance
        self.main_tabs      – QTabWidget (main tab bar)
        self._add_tab_help_button(layout, key)  – adds the Help button to a tab layout
        self._style(widget, css)  – applies inline CSS to a widget
    """

    def _on_overlay_auto_close_toggle(self, state: int):
        enabled = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["overlay_auto_close"] = bool(enabled)
        self.cfg.save()
        try:
            if enabled and self.overlay and self.overlay.isVisible():
                self._start_overlay_auto_close_timer()
            else:
                self.overlay_auto_close_timer.stop()
        except Exception:
            pass

    def _start_overlay_auto_close_timer(self):
        try:
            if bool(self.cfg.OVERLAY.get("overlay_auto_close", False)):
                self.overlay_auto_close_timer.stop()
                self.overlay_auto_close_timer.start(60 * 1000)
        except Exception:
            pass
            
    def _on_ach_toast_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_ach_toast_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_ach_toast_place_clicked(self):
        picker = getattr(self, "_toast_picker", None)
        if picker and isinstance(picker, ToastPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["ach_toast_x_portrait"] = int(x)
                self.cfg.OVERLAY["ach_toast_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["ach_toast_x_landscape"] = int(x)
                self.cfg.OVERLAY["ach_toast_y_landscape"] = int(y)
            self.cfg.OVERLAY["ach_toast_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._toast_picker = None
            self.btn_ach_toast_place.setText("Place / Save position")
            return

        self._toast_picker = ToastPositionPicker(self)
        self.btn_ach_toast_place.setText("Save position")

    def _on_mini_info_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["notifications_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_mini_info_picker") and isinstance(self._mini_info_picker, MiniInfoPositionPicker):
                self._mini_info_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_mini_info_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["notifications_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_mini_info_picker") and isinstance(self._mini_info_picker, MiniInfoPositionPicker):
                self._mini_info_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_mini_info_place_clicked(self):
        picker = getattr(self, "_mini_info_picker", None)
        if picker and isinstance(picker, MiniInfoPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
            if portrait:
                self.cfg.OVERLAY["notifications_x_portrait"] = int(x)
                self.cfg.OVERLAY["notifications_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["notifications_x_landscape"] = int(x)
                self.cfg.OVERLAY["notifications_y_landscape"] = int(y)
            self.cfg.OVERLAY["notifications_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._mini_info_picker = None
            self.btn_mini_info_place.setText("Place / Save position")
            return
        
        self._mini_info_picker = MiniInfoPositionPicker(self)
        self.btn_mini_info_place.setText("Save position")

    def _on_status_overlay_enabled_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_enabled"] = bool(is_checked)
        self.cfg.save()

    def _on_status_overlay_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_status_overlay_picker") and isinstance(self._status_overlay_picker, StatusOverlayPositionPicker):
                self._status_overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_status_overlay_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["status_overlay_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_status_overlay_picker") and isinstance(self._status_overlay_picker, StatusOverlayPositionPicker):
                self._status_overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_status_overlay_place_clicked(self):
        picker = getattr(self, "_status_overlay_picker", None)
        if picker and isinstance(picker, StatusOverlayPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("status_overlay_portrait", False))
            if portrait:
                self.cfg.OVERLAY["status_overlay_x_portrait"] = int(x)
                self.cfg.OVERLAY["status_overlay_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["status_overlay_x_landscape"] = int(x)
                self.cfg.OVERLAY["status_overlay_y_landscape"] = int(y)
            self.cfg.OVERLAY["status_overlay_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._status_overlay_picker = None
            self.btn_status_overlay_place.setText("Place / Save position")
            return

        self._status_overlay_picker = StatusOverlayPositionPicker(self)
        self.btn_status_overlay_place.setText("Save position")

    def _on_duel_overlay_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["duel_overlay_portrait"] = bool(is_checked)
        self.cfg.save()
        try:
            if hasattr(self, "_duel_overlay_picker") and isinstance(self._duel_overlay_picker, DuelOverlayPositionPicker):
                self._duel_overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_duel_overlay_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["duel_overlay_rotate_ccw"] = bool(is_ccw)
        self.cfg.save()
        try:
            if hasattr(self, "_duel_overlay_picker") and isinstance(self._duel_overlay_picker, DuelOverlayPositionPicker):
                self._duel_overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_duel_overlay_place_clicked(self):
        picker = getattr(self, "_duel_overlay_picker", None)
        if picker and isinstance(picker, DuelOverlayPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            portrait = bool(ov.get("duel_overlay_portrait", True))
            if portrait:
                self.cfg.OVERLAY["duel_overlay_x_portrait"] = int(x)
                self.cfg.OVERLAY["duel_overlay_y_portrait"] = int(y)
            else:
                self.cfg.OVERLAY["duel_overlay_x_landscape"] = int(x)
                self.cfg.OVERLAY["duel_overlay_y_landscape"] = int(y)
            self.cfg.OVERLAY["duel_overlay_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._duel_overlay_picker = None
            self.btn_duel_overlay_place.setText("Place / Save position")
            return

        self._duel_overlay_picker = DuelOverlayPositionPicker(self)
        self.btn_duel_overlay_place.setText("Save position")

    def _on_overlay_place_clicked(self):
        picker = getattr(self, "_overlay_picker", None)
        if picker and isinstance(picker, OverlayPositionPicker):
            try:
                x, y = picker.current_top_left()
            except Exception:
                g = picker.geometry()
                x, y = g.x(), g.y()
            ov = self.cfg.OVERLAY or {}
            self.cfg.OVERLAY["pos_x"] = int(x)
            self.cfg.OVERLAY["pos_y"] = int(y)
            self.cfg.OVERLAY["use_xy"] = True
            self.cfg.OVERLAY["overlay_pos_saved"] = True
            self.cfg.save()
            try:
                picker.close()
                picker.deleteLater()
            except Exception:
                pass
            self._overlay_picker = None
            self.btn_overlay_place.setText("Place / Save overlay position")

            if self.overlay:
                self.overlay._apply_geometry()
                self.overlay._layout_positions()
                self.overlay.request_rotation(force=True)
            return
        self._overlay_picker = OverlayPositionPicker(self)
        self.btn_overlay_place.setText("Save position")

    def _apply_theme(self):
        app = QApplication.instance()
        # Fusion is the best base for strong custom themes
        app.setStyle("Fusion")

        theme_id = (self.cfg.OVERLAY or {}).get("theme", DEFAULT_THEME)
        app.setStyleSheet(generate_stylesheet(theme_id))

        self._style(getattr(self, "btn_minimize", None), "QPushButton { background-color:#005c99; color:#FFFFFF; font-weight:bold; border:none; border-radius:5px; padding:7px 16px; }")
        self._style(getattr(self, "btn_quit", None), "QPushButton { background-color:#8a2525; color:#FFFFFF; font-weight:bold; border:none; border-radius:5px; padding:7px 16px; }")
        self._style(getattr(self, "btn_restart", None), "QPushButton { background-color:#008040; color:#FFFFFF; font-weight:bold; border:none; border-radius:5px; padding:7px 16px; }")

    def _on_apply_theme(self):
        theme_id = self.cmb_theme.currentData()
        if not theme_id:
            theme_id = DEFAULT_THEME
        self.cfg.OVERLAY["theme"] = theme_id
        self.cfg.save()
        app = QApplication.instance()
        app.setStyleSheet(generate_stylesheet(theme_id))
        self._style(getattr(self, "btn_minimize", None), "QPushButton { background-color:#005c99; color:#FFFFFF; font-weight:bold; border:none; border-radius:5px; padding:7px 16px; }")
        self._style(getattr(self, "btn_quit", None), "QPushButton { background-color:#8a2525; color:#FFFFFF; font-weight:bold; border:none; border-radius:5px; padding:7px 16px; }")
        self._style(getattr(self, "btn_restart", None), "QPushButton { background-color:#008040; color:#FFFFFF; font-weight:bold; border:none; border-radius:5px; padding:7px 16px; }")
        self._update_theme_preview(theme_id)
        try:
            if getattr(self, "_trophie_gui", None):
                self._trophie_gui.on_theme_changed()
        except Exception:
            pass
        # Sync theme to cloud for app bidirectional sync
        try:
            from core.cloud_sync import CloudSync
            CloudSync.upload_preferences(self.cfg, {"theme": theme_id})
        except Exception:
            pass

    def _on_theme_combo_changed(self, _index: int):
        theme_id = self.cmb_theme.currentData()
        if theme_id:
            self._update_theme_preview(theme_id)

    def _update_theme_preview(self, theme_id: str):
        t = get_theme(theme_id)
        primary = t.get("primary", "#00E5FF")
        for key, swatch in getattr(self, "_theme_color_boxes", {}).items():
            color = t.get(key, "#000000")
            swatch.setStyleSheet(
                f"background-color: {color}; border: 1px solid #555; border-radius: 4px;"
            )
        desc = t.get("description", "")
        lbl_desc = getattr(self, "lbl_theme_description", None)
        if lbl_desc is not None:
            lbl_desc.setText(desc)
            lbl_desc.setStyleSheet(f"color: {primary}; font-size: 9pt; font-style: italic;")
        lbl_active = getattr(self, "lbl_active_theme", None)
        if lbl_active is not None:
            lbl_active.setStyleSheet(f"color: {primary}; font-weight: bold; font-size: 10pt;")
        for dot in getattr(self, "_theme_dot_labels", []):
            dot.setStyleSheet(f"color: {primary}; font-size: 14pt;")

    def _on_theme_toast_test(self):
        try:
            sound.play_sound(self.cfg, "achievement_unlock")
        except Exception:
            pass
        try:
            self._ach_toast_mgr.enqueue("TEST – Achievement Unlock", "test_rom", 5)
        except Exception:
            pass

    def _on_theme_timer_test(self):
        pass

    def _build_tab_appearance(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        self.appearance_subtabs = QTabWidget()
        tab_layout.addWidget(self.appearance_subtabs)

        # ── Overlay sub-tab ────────────────────────────────────────────────────
        overlay_tab = QWidget()
        overlay_tab_layout = QVBoxLayout(overlay_tab)
        overlay_tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        scroll.setWidget(inner)
        overlay_tab_layout.addWidget(scroll)

        grp_style = QGroupBox("Global Styling")
        lay_style = QGridLayout(grp_style)
        
        self.cmb_font_family = QFontComboBox()
        self.cmb_font_family.setCurrentFont(QFont(self.cfg.OVERLAY.get("font_family", "Segoe UI")))
        self.cmb_font_family.currentFontChanged.connect(self._on_font_family_changed)
        
        self.spn_font_size = QSpinBox()
        self.spn_font_size.setRange(8, 64)
        self.spn_font_size.setValue(int(self.cfg.OVERLAY.get("base_body_size", 20)))
        self.spn_font_size.valueChanged.connect(self._on_font_size_changed)

        self.sld_scale = QSlider(Qt.Orientation.Horizontal)
        self.sld_scale.setMinimum(30); self.sld_scale.setMaximum(300)
        self.sld_scale.setValue(int(self.cfg.OVERLAY.get("scale_pct", 100)))
        self.sld_scale.valueChanged.connect(self._on_overlay_scale)
        self.lbl_scale = QLabel(f"{self.sld_scale.value()}%")
        self.btn_scale_reset = QPushButton("100%")
        self.btn_scale_reset.setToolTip("Reset Overlay Scale to 100%")
        self.btn_scale_reset.clicked.connect(lambda: self.sld_scale.setValue(100))

        lay_style.addWidget(QLabel("Overlay Scale:"), 0, 0)
        lay_style.addWidget(self.sld_scale, 0, 1)
        lay_style.addWidget(self.lbl_scale, 0, 2)
        lay_style.addWidget(self.btn_scale_reset, 0, 3)

        lay_style.addWidget(QLabel("Font Family:"), 1, 0)
        lay_style.addWidget(self.cmb_font_family, 1, 1)
        lay_style.addWidget(QLabel("Base Size:"), 1, 2)
        lay_style.addWidget(self.spn_font_size, 1, 3)

        layout.addWidget(grp_style)

        grp_pos = QGroupBox("Widget Placement & Orientation")
        lay_pos = QGridLayout(grp_pos)

        self.btn_switch_all_orientation = QPushButton("🔄 Switch All → Portrait")
        self.btn_switch_all_orientation.setStyleSheet(
            "QPushButton { background-color: #FF7F00; color: #000000; font-weight: bold; padding: 6px 16px; border-radius: 6px; font-size: 10pt; border:none; }"
            "QPushButton:hover { background-color: #FFA040; }"
        )
        self.btn_switch_all_orientation.clicked.connect(self._on_switch_all_portrait_landscape)
        _row_switch = QHBoxLayout()
        _row_switch.addWidget(self.btn_switch_all_orientation)
        _row_switch.addStretch(1)
        lay_pos.addLayout(_row_switch, 0, 0, 1, 2)

        def create_overlay_box(title, chk_port, chk_ccw, btn_place, btn_test=None, btn_hide=None, extra=None):
            box = QVBoxLayout()
            box.addWidget(QLabel(f"<b>{title}</b>"))
            box.addWidget(chk_port); box.addWidget(chk_ccw)
            btns = QHBoxLayout(); btns.addWidget(btn_place)
            if btn_test: btns.addWidget(btn_test)
            if btn_hide: btns.addWidget(btn_hide)
            box.addLayout(btns)
            if extra: box.addWidget(extra)
            box.addStretch(1)
            return box

        # 1) Main Overlay
        self.chk_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_portrait.setChecked(bool(self.cfg.OVERLAY.get("portrait_mode", True))); self.chk_portrait.stateChanged.connect(self._on_portrait_toggle)
        self.chk_portrait_ccw = QCheckBox("Rotate CCW"); self.chk_portrait_ccw.setChecked(bool(self.cfg.OVERLAY.get("portrait_rotate_ccw", True))); self.chk_portrait_ccw.stateChanged.connect(self._on_portrait_ccw_toggle)
        self.btn_overlay_place = QPushButton("Place"); self.btn_overlay_place.clicked.connect(self._on_overlay_place_clicked)
        self.btn_toggle_now = QPushButton("Test"); self.btn_toggle_now.clicked.connect(self._on_overlay_test_clicked)
        self.btn_hide = QPushButton("Hide"); self.btn_hide.clicked.connect(self._hide_overlay)
        self.chk_overlay_auto_close = QCheckBox("Auto-Close 1 min"); self.chk_overlay_auto_close.setChecked(bool(self.cfg.OVERLAY.get("overlay_auto_close", False))); self.chk_overlay_auto_close.stateChanged.connect(self._on_overlay_auto_close_toggle)
        box_main = create_overlay_box("Main Stats Overlay", self.chk_portrait, self.chk_portrait_ccw, self.btn_overlay_place, self.btn_toggle_now, self.btn_hide, self.chk_overlay_auto_close)

        # 2) Toasts
        self.chk_ach_toast_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ach_toast_portrait.setChecked(bool(self.cfg.OVERLAY.get("ach_toast_portrait", True))); self.chk_ach_toast_portrait.stateChanged.connect(self._on_ach_toast_portrait_toggle)
        self.chk_ach_toast_ccw = QCheckBox("Rotate CCW"); self.chk_ach_toast_ccw.setChecked(bool(self.cfg.OVERLAY.get("ach_toast_rotate_ccw", True))); self.chk_ach_toast_ccw.stateChanged.connect(self._on_ach_toast_ccw_toggle)
        self.btn_ach_toast_place = QPushButton("Place"); self.btn_ach_toast_place.clicked.connect(self._on_ach_toast_place_clicked)
        self.btn_test_toast = QPushButton("Test"); self.btn_test_toast.clicked.connect(lambda: self._ach_toast_mgr.enqueue("TEST – Achievement", "test_rom", 5))
        box_toast = create_overlay_box("Achievement Toasts", self.chk_ach_toast_portrait, self.chk_ach_toast_ccw, self.btn_ach_toast_place, self.btn_test_toast)

        # 4) Mini Info / Notifications Overlay
        self.chk_mini_info_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_mini_info_portrait.setChecked(bool(self.cfg.OVERLAY.get("notifications_portrait", True))); self.chk_mini_info_portrait.stateChanged.connect(self._on_mini_info_portrait_toggle)
        self.chk_mini_info_ccw = QCheckBox("Rotate CCW"); self.chk_mini_info_ccw.setChecked(bool(self.cfg.OVERLAY.get("notifications_rotate_ccw", True))); self.chk_mini_info_ccw.stateChanged.connect(self._on_mini_info_ccw_toggle)
        self.btn_mini_info_place = QPushButton("Place"); self.btn_mini_info_place.clicked.connect(self._on_mini_info_place_clicked)
        self.btn_mini_info_test = QPushButton("Test"); self.btn_mini_info_test.clicked.connect(self._on_mini_info_test)
        box_mini_info = create_overlay_box("System Notifications", self.chk_mini_info_portrait, self.chk_mini_info_ccw, self.btn_mini_info_place, self.btn_mini_info_test)

        # 5) Status Overlay (cloud / leaderboard status messages)
        self.chk_status_overlay_enabled = QCheckBox("Enabled"); self.chk_status_overlay_enabled.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_enabled", True))); self.chk_status_overlay_enabled.stateChanged.connect(self._on_status_overlay_enabled_toggle)
        self.chk_status_overlay_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_status_overlay_portrait.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_portrait", False))); self.chk_status_overlay_portrait.stateChanged.connect(self._on_status_overlay_portrait_toggle)
        self.chk_status_overlay_ccw = QCheckBox("Rotate CCW"); self.chk_status_overlay_ccw.setChecked(bool(self.cfg.OVERLAY.get("status_overlay_rotate_ccw", False))); self.chk_status_overlay_ccw.stateChanged.connect(self._on_status_overlay_ccw_toggle)
        self.btn_status_overlay_place = QPushButton("Place"); self.btn_status_overlay_place.clicked.connect(self._on_status_overlay_place_clicked)
        self.btn_status_overlay_test = QPushButton("Test"); self.btn_status_overlay_test.clicked.connect(self._on_status_overlay_test)
        box_status_overlay = QVBoxLayout()
        box_status_overlay.addWidget(QLabel("<b>Status Overlay</b>"))
        box_status_overlay.addWidget(self.chk_status_overlay_enabled)
        box_status_overlay.addWidget(self.chk_status_overlay_portrait)
        box_status_overlay.addWidget(self.chk_status_overlay_ccw)
        _btns_status = QHBoxLayout(); _btns_status.addWidget(self.btn_status_overlay_place); _btns_status.addWidget(self.btn_status_overlay_test)
        box_status_overlay.addLayout(_btns_status)
        box_status_overlay.addStretch(1)

        # 6) Duel Overlay (dedicated overlay for all duel/tournament messages)
        self.chk_duel_overlay_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_duel_overlay_portrait.setChecked(bool(self.cfg.OVERLAY.get("duel_overlay_portrait", True))); self.chk_duel_overlay_portrait.stateChanged.connect(self._on_duel_overlay_portrait_toggle)
        self.chk_duel_overlay_ccw = QCheckBox("Rotate CCW"); self.chk_duel_overlay_ccw.setChecked(bool(self.cfg.OVERLAY.get("duel_overlay_rotate_ccw", True))); self.chk_duel_overlay_ccw.stateChanged.connect(self._on_duel_overlay_ccw_toggle)
        self.btn_duel_overlay_place = QPushButton("Place"); self.btn_duel_overlay_place.clicked.connect(self._on_duel_overlay_place_clicked)
        self.btn_duel_overlay_test = QPushButton("Test"); self.btn_duel_overlay_test.clicked.connect(self._on_duel_overlay_test)
        box_duel_overlay = create_overlay_box("⚔️ Duel Notifications", self.chk_duel_overlay_portrait, self.chk_duel_overlay_ccw, self.btn_duel_overlay_place, self.btn_duel_overlay_test)

        lay_pos.addLayout(box_main, 1, 0); lay_pos.addLayout(box_toast, 1, 1)
        lay_pos.addLayout(box_mini_info, 2, 0); lay_pos.addLayout(box_status_overlay, 2, 1)
        lay_pos.addLayout(box_duel_overlay, 3, 0)

        layout.addWidget(grp_pos)

        lbl_overlay_bg_tip = QLabel(
            "💡 Tip: To use a custom background for the main overlay, "
            "place an image named overlay_bg.jpg/png next to the executable."
        )
        lbl_overlay_bg_tip.setWordWrap(True)
        lbl_overlay_bg_tip.setStyleSheet("color: #888; font-size: 9pt; font-style: italic; padding: 2px 4px;")
        layout.addWidget(lbl_overlay_bg_tip)

        # ── Overlay Pages toggle ────────────────────────────────────────────────
        grp_pages = QGroupBox("📄 Overlay Pages")
        lay_pages = QVBoxLayout(grp_pages)

        lbl_page1 = QLabel("Page 1 (Highlights & Score) is always active.")
        lbl_page1.setStyleSheet("color: #FF7F00; font-size: 9pt;")
        lay_pages.addWidget(lbl_page1)

        lbl_hint = QLabel("Disable pages you don't need — they will be skipped when cycling through the overlay.")
        lbl_hint.setStyleSheet("color: #AAA; font-size: 9pt; font-style: italic;")
        lbl_hint.setWordWrap(True)
        lay_pages.addWidget(lbl_hint)

        self.chk_overlay_page2 = QCheckBox("Page 2: Achievement Progress")
        self.chk_overlay_page2.setChecked(bool(self.cfg.OVERLAY.get("overlay_page2_enabled", True)))
        self.chk_overlay_page2.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page2)

        self.chk_overlay_page3 = QCheckBox("Page 3: Cloud Leaderboard")
        self.chk_overlay_page3.setChecked(bool(self.cfg.OVERLAY.get("overlay_page3_enabled", True)))
        self.chk_overlay_page3.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page3)

        self.chk_overlay_page4 = QCheckBox("Page 4: VPC Leaderboard")
        self.chk_overlay_page4.setChecked(bool(self.cfg.OVERLAY.get("overlay_page4_enabled", True)))
        self.chk_overlay_page4.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page4)

        self.chk_overlay_page5 = QCheckBox("Page 5: Score Duels")
        self.chk_overlay_page5.setChecked(bool(self.cfg.OVERLAY.get("overlay_page5_enabled", True)))
        self.chk_overlay_page5.stateChanged.connect(self._save_overlay_page_settings)
        lay_pages.addWidget(self.chk_overlay_page5)

        layout.addWidget(grp_pages)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "appearance_overlay")
        self._update_switch_all_button_label()
        self.appearance_subtabs.addTab(overlay_tab, "🖼 Overlay")

        # ── Theme sub-tab ──────────────────────────────────────────────────────
        theme_tab = QWidget()
        theme_tab_outer = QVBoxLayout(theme_tab)

        theme_scroll = QScrollArea()
        theme_scroll.setWidgetResizable(True)
        theme_scroll.setFrameShape(QFrame.Shape.NoFrame)
        theme_inner = QWidget()
        theme_layout = QVBoxLayout(theme_inner)
        theme_layout.setContentsMargins(8, 8, 8, 8)
        theme_layout.setSpacing(10)
        theme_scroll.setWidget(theme_inner)
        theme_tab_outer.addWidget(theme_scroll)

        # ── 1. Active Theme row ────────────────────────────────────────────────
        row_active = QHBoxLayout()
        self.lbl_active_theme = QLabel("Active theme:")
        self.lbl_active_theme.setStyleSheet("color: #00E5FF; font-weight: bold; font-size: 10pt;")
        row_active.addWidget(self.lbl_active_theme)

        self.cmb_theme = QComboBox()
        current_theme_id = (self.cfg.OVERLAY or {}).get("theme", DEFAULT_THEME)
        for tid, tdata in list_themes():
            self.cmb_theme.addItem(f"{tdata['icon']} {tdata['name']}", tid)
        idx = next((i for i in range(self.cmb_theme.count())
                    if self.cmb_theme.itemData(i) == current_theme_id), 0)
        self.cmb_theme.setCurrentIndex(idx)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_combo_changed)
        row_active.addWidget(self.cmb_theme, 1)

        self.btn_apply_theme = QPushButton("Apply Theme")
        self.btn_apply_theme.setStyleSheet(
            "QPushButton { background-color: #FF7F00; color: #000000; font-weight: bold;"
            " padding: 6px 16px; border-radius: 6px; border:none; }"
            "QPushButton:hover { background-color: #FFA040; }"
            "QPushButton:pressed { background-color: #CC6600; }"
        )
        self.btn_apply_theme.clicked.connect(self._on_apply_theme)
        row_active.addWidget(self.btn_apply_theme)
        theme_layout.addLayout(row_active)

        # ── 2. Color Preview ───────────────────────────────────────────────────
        grp_preview = QGroupBox("Color Preview")
        lay_preview = QVBoxLayout(grp_preview)

        row_colors = QHBoxLayout()
        row_colors.setSpacing(12)
        self._theme_color_boxes: dict[str, QLabel] = {}
        for key, label_text in [("primary", "Primary"), ("accent", "Accent"),
                                 ("border", "Border"), ("bg", "BG")]:
            col = QVBoxLayout()
            col.setSpacing(2)
            swatch = QLabel()
            swatch.setFixedSize(60, 36)
            swatch.setStyleSheet("border: 1px solid #555; border-radius: 4px;")
            self._theme_color_boxes[key] = swatch
            col.addWidget(swatch)
            lbl_key = QLabel(label_text)
            lbl_key.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl_key.setStyleSheet("color: #AAA; font-size: 8pt;")
            col.addWidget(lbl_key)
            row_colors.addLayout(col)
        row_colors.addStretch(1)
        lay_preview.addLayout(row_colors)

        self.lbl_theme_description = QLabel()
        self.lbl_theme_description.setStyleSheet("color: #00E5FF; font-size: 9pt; font-style: italic;")
        lay_preview.addWidget(self.lbl_theme_description)
        theme_layout.addWidget(grp_preview)

        # ── 3. Overlay Preview / Test ──────────────────────────────────────────
        grp_ov_test = QGroupBox("Overlay Preview / Test")
        lay_ov_test = QVBoxLayout(grp_ov_test)

        lbl_ov_hint = QLabel(
            "Preview how overlays look with the current theme."
        )
        lbl_ov_hint.setWordWrap(True)
        lbl_ov_hint.setStyleSheet("color: #AAA; font-size: 9pt; font-style: italic;")
        lay_ov_test.addWidget(lbl_ov_hint)

        _btn_css = (
            "QPushButton { background-color: #333333; color: #CCCCCC; border: 1px solid #555555;"
            " border-radius: 4px; padding: 3px 10px; font-size: 9pt; font-weight: bold; }"
            "QPushButton:hover { border-color: #AAAAAA; color: #FFFFFF; }"
        )
        self._theme_dot_labels: list[QLabel] = []

        def _make_ov_row(dot_color: str, name: str, desc: str,
                         test_fn=None, track_dot: bool = False) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl_name = QLabel(f"<b>{name}</b>")
            lbl_name.setStyleSheet("color: #E0E0E0;")
            row.addWidget(lbl_name)
            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet("color: #888; font-size: 9pt;")
            row.addWidget(lbl_desc, 1)
            if test_fn is not None:
                btn = QPushButton("Test")
                btn.setStyleSheet(_btn_css)
                btn.setFixedWidth(52)
                btn.clicked.connect(test_fn)
                row.addWidget(btn)
            return row

        # theme-affected overlays (primary-color dot)
        lay_ov_test.addLayout(_make_ov_row(
            "#00E5FF", "Main Stats Overlay", "Full achievement list & stats",
            self._on_overlay_test_clicked, track_dot=True))
        lay_ov_test.addLayout(_make_ov_row(
            "#00E5FF", "Achievement Toast", "Pops up on each unlock",
            self._on_theme_toast_test, track_dot=True))
        theme_layout.addWidget(grp_ov_test)

        # ── 4. Available Themes ────────────────────────────────────────────────
        grp_themes = QGroupBox("Available Themes")
        lay_themes = QVBoxLayout(grp_themes)

        for tid, tdata in list_themes():
            row = QHBoxLayout()
            row.setSpacing(10)
            lbl_icon = QLabel(tdata["icon"])
            lbl_icon.setFixedWidth(28)
            lbl_icon.setStyleSheet("font-size: 16pt;")
            row.addWidget(lbl_icon)
            lbl_tname = QLabel(f"<b>{tdata['name']}</b>")
            lbl_tname.setStyleSheet("color: #FFFFFF; font-size: 10pt;")
            lbl_tname.setFixedWidth(150)
            row.addWidget(lbl_tname)
            lbl_tdesc = QLabel(tdata.get("description", ""))
            lbl_tdesc.setStyleSheet("color: #888888; font-size: 9pt;")
            row.addWidget(lbl_tdesc, 1)
            lay_themes.addLayout(row)
        theme_layout.addWidget(grp_themes)

        theme_layout.addStretch(1)
        self._add_tab_help_button(theme_tab_outer, "appearance_theme")
        self.appearance_subtabs.addTab(theme_tab, "🎨 Theme")

        # Populate color preview for the initial theme
        self._update_theme_preview(current_theme_id)

        # ── Sound sub-tab ──────────────────────────────────────────────────────
        sound_tab = QWidget()
        sound_outer = QVBoxLayout(sound_tab)
        sound_scroll = QScrollArea()
        sound_scroll.setWidgetResizable(True)
        sound_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sound_inner = QWidget()
        sound_layout = QVBoxLayout(sound_inner)
        sound_layout.setContentsMargins(8, 8, 8, 8)

        # Title
        lbl_sound_title = QLabel("🔊 Sound Effects")
        lbl_sound_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #FF7F00; padding: 4px 0;")
        sound_layout.addWidget(lbl_sound_title)

        # Enable + Volume row
        row_enable = QHBoxLayout()
        self.chk_sound_enabled = QCheckBox("Enable Sound Effects")
        self.chk_sound_enabled.setChecked(bool(self.cfg.OVERLAY.get("sound_enabled", False)))
        def _on_sound_enabled(state):
            self.cfg.OVERLAY["sound_enabled"] = bool(state)
            self.cfg.save()
            self._sync_sound_preferences()
        self.chk_sound_enabled.stateChanged.connect(_on_sound_enabled)
        row_enable.addWidget(self.chk_sound_enabled)
        row_enable.addSpacing(20)

        lbl_vol = QLabel("Volume:")
        row_enable.addWidget(lbl_vol)
        self.sld_sound_volume = QSlider(Qt.Orientation.Horizontal)
        self.sld_sound_volume.setRange(0, 100)
        self.sld_sound_volume.setValue(int(self.cfg.OVERLAY.get("sound_volume", sound.DEFAULT_VOLUME)))
        self.sld_sound_volume.setFixedWidth(180)
        self.sld_sound_volume.setStyleSheet(
            "QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #FF7F00; width: 14px; margin: -4px 0; border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #FF7F00; border-radius: 3px; }"
        )
        self.lbl_sound_vol_pct = QLabel(f"{self.sld_sound_volume.value()}%")
        self.lbl_sound_vol_pct.setMinimumWidth(36)
        def _on_sound_volume(val):
            self.lbl_sound_vol_pct.setText(f"{val}%")
            self.cfg.OVERLAY["sound_volume"] = val
            self.cfg.save()
            self._sync_sound_preferences()
        self.sld_sound_volume.valueChanged.connect(_on_sound_volume)
        row_enable.addWidget(self.sld_sound_volume)
        row_enable.addWidget(self.lbl_sound_vol_pct)
        row_enable.addStretch(1)
        sound_layout.addLayout(row_enable)

        # Sound Pack
        row_pack = QHBoxLayout()
        lbl_pack = QLabel("Sound Pack:")
        lbl_pack.setStyleSheet("font-weight: bold;")
        row_pack.addWidget(lbl_pack)
        self.cmb_sound_pack = QComboBox()
        self.cmb_sound_pack.setFixedWidth(160)
        for pack_id, pack_name in sound.SOUND_PACKS.items():
            self.cmb_sound_pack.addItem(pack_name, pack_id)
        cur_pack = str(self.cfg.OVERLAY.get("sound_pack", "zaptron"))
        idx = self.cmb_sound_pack.findData(cur_pack)
        if idx >= 0:
            self.cmb_sound_pack.setCurrentIndex(idx)
        def _on_sound_pack(idx):
            self.cfg.OVERLAY["sound_pack"] = self.cmb_sound_pack.itemData(idx)
            self.cfg.save()
            self._sync_sound_preferences()
        self.cmb_sound_pack.currentIndexChanged.connect(_on_sound_pack)
        row_pack.addWidget(self.cmb_sound_pack)
        row_pack.addStretch(1)
        sound_layout.addLayout(row_pack)

        # Events group
        lbl_events = QLabel("Events")
        lbl_events.setStyleSheet("font-size: 11pt; font-weight: bold; color: #00E5FF; margin-top: 6px;")
        sound_layout.addWidget(lbl_events)

        tbl_sound = QTableWidget(len(sound.SOUND_EVENTS), 3)
        tbl_sound.setHorizontalHeaderLabels(["Event", "Enabled", "Test"])
        tbl_sound.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tbl_sound.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tbl_sound.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tbl_sound.horizontalHeader().setStretchLastSection(False)
        tbl_sound.verticalHeader().setDefaultSectionSize(32)
        tbl_sound.verticalHeader().setVisible(False)
        tbl_sound.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl_sound.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl_sound.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl_sound.setShowGrid(False)
        tbl_sound.setAlternatingRowColors(False)
        tbl_sound.setStyleSheet(
            "QTableWidget { background: #111; alternate-background-color: #111; border: 1px solid #333; gridline-color: transparent; }"
            "QTableWidget::item { padding: 4px 6px; border: none; }"
        )

        cur_events = self.cfg.OVERLAY.get("sound_events") or {}

        for row, (event_id, event_label) in enumerate(sound.SOUND_EVENTS):
            lbl_item = QTableWidgetItem(event_label)
            lbl_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tbl_sound.setItem(row, 0, lbl_item)

            chk_event = QCheckBox()
            chk_event.setChecked(bool(cur_events.get(event_id, False)))
            chk_event.setFixedSize(20, 20)
            chk_event.setToolTip(f"Enable/disable sound for {event_label}")
            chk_event.setStyleSheet(
                "QCheckBox::indicator { width: 16px; height: 16px; }"
                "QCheckBox::indicator:checked { background: #00E5FF; border: 1px solid #00E5FF; border-radius: 2px; }"
                "QCheckBox::indicator:unchecked { background: #333; border: 1px solid #555; border-radius: 2px; }"
            )

            def _make_event_handler(eid):
                def _handler(state):
                    ev = self.cfg.OVERLAY.setdefault("sound_events", {})
                    ev[eid] = bool(state)
                    self.cfg.save()
                    self._sync_sound_preferences()
                return _handler

            chk_event.stateChanged.connect(_make_event_handler(event_id))
            cell_chk = QWidget()
            cell_lay = QHBoxLayout(cell_chk)
            cell_lay.setContentsMargins(0, 0, 0, 0)
            cell_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_lay.addWidget(chk_event)
            tbl_sound.setCellWidget(row, 1, cell_chk)

            btn_test = QPushButton("▶")
            btn_test.setFixedSize(28, 22)
            btn_test.setToolTip(f"Preview sound for {event_label}")
            btn_test.setStyleSheet(
                "QPushButton { background-color: #00E5FF; color: #000000; border: none; "
                "border-radius: 3px; font-size: 10pt; font-weight: bold; "
                "padding: 0px; text-align: center; }"
                "QPushButton:hover { background-color: #33EEFF; }"
            )

            def _make_preview(eid):
                def _preview():
                    sound.play_sound_preview(self.cfg, eid)
                return _preview

            btn_test.clicked.connect(_make_preview(event_id))
            cell_btn = QWidget()
            cell_btn_lay = QHBoxLayout(cell_btn)
            cell_btn_lay.setContentsMargins(2, 1, 2, 1)
            cell_btn_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_btn_lay.addWidget(btn_test)
            tbl_sound.setCellWidget(row, 2, cell_btn)

        tbl_sound.resizeRowsToContents()
        tbl_sound.resizeColumnsToContents()
        _total_w = (sum(tbl_sound.columnWidth(c) for c in range(3))
                    + tbl_sound.frameWidth() * 2 + 20)
        tbl_sound.setMaximumWidth(_total_w)
        tbl_sound.setMinimumHeight(len(sound.SOUND_EVENTS) * 32 + 30)
        sound_layout.addWidget(tbl_sound)

        sound_layout.addStretch(1)
        self._add_tab_help_button(sound_layout, "appearance_sound")
        sound_scroll.setWidget(sound_inner)
        sound_outer.addWidget(sound_scroll)
        self.appearance_subtabs.addTab(sound_tab, "🔊 Sound")

        # ── Effects sub-tab ────────────────────────────────────────────────────
        self._build_effects_subtab()

        # ── Mascots sub-tab ────────────────────────────────────────────────────
        self._build_mascots_subtab()

        self.main_tabs.addTab(tab, "🎨 Appearance")

    def _portrait_checkboxes(self):
        """Returns the list of all overlay portrait-mode checkboxes."""
        return [
            self.chk_portrait,
            self.chk_ach_toast_portrait,
            self.chk_mini_info_portrait,
            self.chk_status_overlay_portrait,
            self.chk_duel_overlay_portrait,
        ]

    def _sync_sound_preferences(self):
        """Upload current sound preferences to cloud for bidirectional sync with the app."""
        try:
            from core.cloud_sync import CloudSync
            sounds_data = {
                "enabled": bool(self.cfg.OVERLAY.get("sound_enabled", False)),
                "volume": int(self.cfg.OVERLAY.get("sound_volume", 20)),
                "pack": str(self.cfg.OVERLAY.get("sound_pack", "zaptron")),
                "events": dict(self.cfg.OVERLAY.get("sound_events", {})),
            }
            CloudSync.upload_preferences(self.cfg, {"sounds": sounds_data})
        except Exception:
            pass

    def _ccw_checkboxes(self):
        """Returns the list of all overlay CCW-rotation checkboxes."""
        return [
            self.chk_portrait_ccw,
            self.chk_ach_toast_ccw,
            self.chk_mini_info_ccw,
            self.chk_status_overlay_ccw,
            self.chk_duel_overlay_ccw,
        ]

    def _update_switch_all_button_label(self):
        """Updates the Switch All button label to reflect current portrait checkbox state."""
        try:
            if any(chk.isChecked() for chk in self._portrait_checkboxes()):
                self.btn_switch_all_orientation.setText("🔄 Switch All → Landscape")
            else:
                self.btn_switch_all_orientation.setText("🔄 Switch All → Portrait")
        except AttributeError:
            # During _build_tab_appearance() the checkboxes are created one by one;
            # stateChanged may fire before all 7 checkboxes or the button exist yet.
            pass

    def _on_switch_all_portrait_landscape(self):
        """Toggles all overlay portrait + CCW checkboxes between Portrait and Landscape at once."""
        should_be_portrait = not any(chk.isChecked() for chk in self._portrait_checkboxes())
        for chk in self._portrait_checkboxes():
            chk.setChecked(should_be_portrait)
        for chk in self._ccw_checkboxes():
            chk.setChecked(should_be_portrait)
        self.cfg.save()
        self._update_switch_all_button_label()

    def _init_overlay_tooltips(self):
        tips = {
            # Appearance Tab - Global Styling
            "cmb_font_family": "Select the font style for all text in the overlays.",
            "spn_font_size": "Adjust the base font size (automatically scales headers and body text).",
            "sld_scale": "Scale the main overlay up or down in overall size (percentage).",
            "lbl_scale": "Current overlay scale in percent.",
            
            # Appearance Tab - Main Stats Overlay
            "chk_portrait": "Rotate the main overlay 90 degrees for portrait/cabinet screens.",
            "chk_portrait_ccw": "Rotate counter-clockwise (instead of clockwise) for portrait mode.",
            "btn_overlay_place": "Open a draggable window to set and save the position of the main overlay.",
            "btn_toggle_now": "Instantly show or hide the main overlay for testing.",
            "btn_hide": "Forcefully hide the main overlay if it's currently visible.",
            "chk_overlay_auto_close": "Automatically hide the main overlay after 60 seconds of inactivity.",
            
            # Appearance Tab - Achievement Toasts
            "chk_ach_toast_portrait": "Rotate achievement unlock popups for portrait screens.",
            "chk_ach_toast_ccw": "Rotate achievement popups counter-clockwise.",
            "btn_ach_toast_place": "Set and save the screen position for achievement popups.",
            "btn_test_toast": "Trigger a test achievement popup to check your placement.",
            
            # Appearance Tab - System Notifications (Mini Info Overlay)
            "chk_mini_info_portrait": "Rotate system notifications (errors, warnings, info) for portrait screens.",
            "chk_mini_info_ccw": "Rotate system notifications counter-clockwise.",
            "btn_mini_info_place": "Set and save the screen position for system notifications.",
            "btn_mini_info_test": "Trigger a test notification to check your placement.",
            
            # Appearance Tab - Status Overlay (cloud / leaderboard status)
            "chk_status_overlay_enabled": "Show or hide the Status Overlay for cloud and leaderboard submission feedback.",
            "chk_status_overlay_portrait": "Rotate the Status Overlay 90 degrees for portrait/cabinet screens.",
            "chk_status_overlay_ccw": "Rotate the Status Overlay counter-clockwise.",
            "btn_status_overlay_place": "Set and save the screen position for the Status Overlay.",
            "btn_status_overlay_test": "Trigger a test Status Overlay message to check your placement.",

            # Appearance Tab - Duel Overlay
            "chk_duel_overlay_portrait": "Rotate duel/tournament notifications for portrait/cabinet screens.",
            "chk_duel_overlay_ccw": "Rotate duel/tournament notifications counter-clockwise.",
            "btn_duel_overlay_place": "Set and save the screen position for duel notifications.",
            "btn_duel_overlay_test": "Trigger a test duel notification to check your placement.",

            # Appearance Tab - Switch All button
            "btn_switch_all_orientation": "Toggle all overlay widgets between Portrait and Landscape mode at once.",
        }
        apply_tooltips(self, tips)

    def _on_ach_toast_custom_toggled(self, state: int):
        use = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["ach_toast_custom"] = bool(use)
        if not use:
            self.cfg.OVERLAY["ach_toast_saved"] = False
        self.cfg.save()

    def _on_portrait_ccw_toggle(self, state: int):
        is_ccw = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["portrait_rotate_ccw"] = is_ccw
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_portrait_from_cfg(self.cfg.OVERLAY)
            self.overlay.request_rotation(force=True)
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_portrait_toggle(self, state: int):
        is_checked = (Qt.CheckState(state) == Qt.CheckState.Checked)
        self.cfg.OVERLAY["portrait_mode"] = is_checked
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_portrait_from_cfg(self.cfg.OVERLAY)
        try:
            if hasattr(self, "_toast_picker") and isinstance(self._toast_picker, ToastPositionPicker):
                self._toast_picker.apply_portrait_from_cfg()
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_switch_all_button_label()

    def _on_lines_per_category_changed(self, val: int):
        self.cfg.OVERLAY["lines_per_category"] = int(val)
        self.cfg.save()
        try:
            if self.overlay and self.overlay.isVisible():
                self._refresh_overlay_live()
        except Exception:
            pass

    def _on_overlay_scale(self, val: int):
        self.lbl_scale.setText(f"{val}%")
        self.cfg.OVERLAY["scale_pct"] = int(val)
        self.cfg.save()
        if self.overlay:
            self.overlay.scale_pct = int(val)
            self.overlay._apply_scale(int(val))
            self.overlay._apply_geometry()
            if getattr(self, '_vpc_page5_data', None):
                # VPC page 5 is active — recalculate image dimensions for new overlay size
                self._refresh_vpc_page5()
            else:
                self.overlay._refresh_current_content()
        try:
            if hasattr(self, "_overlay_picker") and isinstance(self._overlay_picker, OverlayPositionPicker):
                self._overlay_picker.apply_portrait_from_cfg()
        except Exception:
            pass
        self._update_secondary_overlay_fonts()

    def _on_font_family_changed(self, qfont: QFont):
        family = qfont.family()
        self.cfg.OVERLAY["font_family"] = family
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_font_from_cfg(self.cfg.OVERLAY)
        self._update_secondary_overlay_fonts()

    def _on_font_size_changed(self, val: int):
        body = int(val)
        self.cfg.OVERLAY["base_body_size"] = body
        self.cfg.OVERLAY["base_title_size"] = int(round(body * 1.4))
        self.cfg.OVERLAY["base_hint_size"] = int(round(body * 0.8))
        self.cfg.save()
        if self.overlay:
            self.overlay.apply_font_from_cfg(self.cfg.OVERLAY)
            self.overlay._apply_geometry()
        self._update_secondary_overlay_fonts()

    def _update_secondary_overlay_fonts(self):
        mini = getattr(self, "_mini_overlay", None)
        if mini is not None:
            mini.update_font()
        status = getattr(self, "_status_overlay", None)
        if status is not None:
            status.update_font()
        for attr in ("_flip_total_win", "_flip_total_test_win"):
            flip = getattr(self, attr, None)
            if flip is not None:
                flip.update_font()
