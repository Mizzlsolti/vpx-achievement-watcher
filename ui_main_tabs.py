from __future__ import annotations

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QCheckBox, QSlider, QComboBox, QGroupBox,
    QLineEdit, QFontComboBox, QSpinBox, QTabWidget, QTextBrowser,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from theme import pinball_arcade_style


class MainUITabsMixin:
    """
    Mixin for MainWindow that provides the GUI-building methods for the
    main tabs (Dashboard, Appearance, Controls, Progress, Available Maps,
    System) as well as the theme-application helpers.
    """

    def _style(self, widget, css: str):
        try:
            if widget:
                widget.setStyleSheet(css)
        except Exception:
            pass

    def _apply_theme(self):
        app = QApplication.instance()
        # Fusion ist die beste Basis für starke Custom-Themes
        app.setStyle("Fusion")

        app.setStyleSheet(pinball_arcade_style)

        self._style(getattr(self, "btn_minimize", None), "background:#005c99; color:white; border:none;")
        self._style(getattr(self, "btn_quit", None), "background:#8a2525; color:white; border:none;")
        self._style(getattr(self, "btn_restart", None), "background:#008040; color:white; border:none;")

    # ==========================================
    # TAB 1: DASHBOARD
    # ==========================================
    def _build_tab_dashboard(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_status = QGroupBox("System Status")
        lay_status = QVBoxLayout(grp_status)
        self.status_label = QLabel("🟢 Watcher: RUNNING...")
        self.status_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00E5FF; padding: 10px;")
        lay_status.addWidget(self.status_label)
        layout.addWidget(grp_status)

        grp_actions = QGroupBox("Quick Actions")
        lay_actions = QHBoxLayout(grp_actions)
        self.btn_restart = QPushButton("Restart Engine")
        self.btn_restart.setStyleSheet("background:#008040; border:none;")
        self.btn_restart.clicked.connect(self._restart_watcher)
        self.btn_minimize = QPushButton("Minimize to Tray")
        self.btn_minimize.setStyleSheet("background:#005c99; border:none;")
        self.btn_minimize.clicked.connect(self.hide)
        self.btn_quit = QPushButton("Quit GUI")
        self.btn_quit.setStyleSheet("background:#8a2525; border:none;")
        self.btn_quit.clicked.connect(self.quit_all)

        lay_actions.addWidget(self.btn_restart)
        lay_actions.addStretch(1)
        lay_actions.addWidget(self.btn_minimize)
        lay_actions.addWidget(self.btn_quit)
        layout.addWidget(grp_actions)

        lbl_info = QLabel("\n(Play a game of VPX to see stats and highlights...)")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setStyleSheet("color: #777;")
        layout.addWidget(lbl_info)
        layout.addStretch(1)

        self.main_tabs.addTab(tab, "🏠 Dashboard")

    # ==========================================
    # TAB 2: APPEARANCE (Grid Layout)
    # ==========================================
    def _build_tab_appearance(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

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

        lay_style.addWidget(QLabel("Font Family:"), 0, 0)
        lay_style.addWidget(self.cmb_font_family, 0, 1)
        lay_style.addWidget(QLabel("Base Size:"), 0, 2)
        lay_style.addWidget(self.spn_font_size, 0, 3)

        lay_style.addWidget(QLabel("Overlay Scale:"), 1, 0)
        lay_style.addWidget(self.sld_scale, 1, 1)
        lay_style.addWidget(self.lbl_scale, 1, 2)

        layout.addWidget(grp_style)

        grp_pos = QGroupBox("Widget Placement & Orientation")
        lay_pos = QGridLayout(grp_pos)

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

        # 3) Challenge Menu
        self.chk_ch_ov_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ch_ov_portrait.setChecked(bool(self.cfg.OVERLAY.get("ch_ov_portrait", True))); self.chk_ch_ov_portrait.stateChanged.connect(self._on_ch_ov_portrait_toggle)
        self.chk_ch_ov_ccw = QCheckBox("Rotate CCW"); self.chk_ch_ov_ccw.setChecked(bool(self.cfg.OVERLAY.get("ch_ov_rotate_ccw", True))); self.chk_ch_ov_ccw.stateChanged.connect(self._on_ch_ov_ccw_toggle)
        self.btn_ch_ov_place = QPushButton("Place"); self.btn_ch_ov_place.clicked.connect(self._on_ch_ov_place_clicked)
        self.btn_ch_ov_test = QPushButton("Test"); self.btn_ch_ov_test.clicked.connect(self._on_ch_ov_test)
        box_ch_sel = create_overlay_box("Challenge Menu", self.chk_ch_ov_portrait, self.chk_ch_ov_ccw, self.btn_ch_ov_place, self.btn_ch_ov_test)

        # 4) Timers & Counters
        self.chk_ch_timer_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_ch_timer_portrait.setChecked(bool(self.cfg.OVERLAY.get("ch_timer_portrait", True))); self.chk_ch_timer_portrait.stateChanged.connect(self._on_ch_timer_portrait_toggle)
        self.chk_ch_timer_ccw = QCheckBox("Rotate CCW"); self.chk_ch_timer_ccw.setChecked(bool(self.cfg.OVERLAY.get("ch_timer_rotate_ccw", True))); self.chk_ch_timer_ccw.stateChanged.connect(self._on_ch_timer_ccw_toggle)
        box_tc = QVBoxLayout(); box_tc.addWidget(QLabel("<b>Timers & Counters</b>")); box_tc.addWidget(self.chk_ch_timer_portrait); box_tc.addWidget(self.chk_ch_timer_ccw)
        btn_r1 = QHBoxLayout(); self.btn_ch_timer_place = QPushButton("Place Timer"); self.btn_ch_timer_place.clicked.connect(self._on_ch_timer_place_clicked); self.btn_ch_timer_test = QPushButton("Test Timer"); self.btn_ch_timer_test.clicked.connect(self._on_ch_timer_test); btn_r1.addWidget(self.btn_ch_timer_place); btn_r1.addWidget(self.btn_ch_timer_test)
        btn_r2 = QHBoxLayout(); self.btn_flip_counter_place = QPushButton("Place Counter"); self.btn_flip_counter_place.clicked.connect(self._on_flip_counter_place_clicked); self.btn_flip_counter_test = QPushButton("Test Counter"); self.btn_flip_counter_test.clicked.connect(self._on_flip_counter_test); btn_r2.addWidget(self.btn_flip_counter_place); btn_r2.addWidget(self.btn_flip_counter_test)
        box_tc.addLayout(btn_r1); box_tc.addLayout(btn_r2); box_tc.addStretch(1)

        self.chk_flip_counter_portrait = self.chk_ch_timer_portrait
        self.chk_flip_counter_ccw = self.chk_ch_timer_ccw

        # 5) NEU: Mini Info / Notifications Overlay
        self.chk_mini_info_portrait = QCheckBox("Portrait Mode (90°)"); self.chk_mini_info_portrait.setChecked(bool(self.cfg.OVERLAY.get("notifications_portrait", True))); self.chk_mini_info_portrait.stateChanged.connect(self._on_mini_info_portrait_toggle)
        self.chk_mini_info_ccw = QCheckBox("Rotate CCW"); self.chk_mini_info_ccw.setChecked(bool(self.cfg.OVERLAY.get("notifications_rotate_ccw", True))); self.chk_mini_info_ccw.stateChanged.connect(self._on_mini_info_ccw_toggle)
        self.btn_mini_info_place = QPushButton("Place"); self.btn_mini_info_place.clicked.connect(self._on_mini_info_place_clicked)
        self.btn_mini_info_test = QPushButton("Test"); self.btn_mini_info_test.clicked.connect(self._on_mini_info_test)
        box_mini_info = create_overlay_box("System Notifications", self.chk_mini_info_portrait, self.chk_mini_info_ccw, self.btn_mini_info_place, self.btn_mini_info_test)

        lay_pos.addLayout(box_main, 0, 0); lay_pos.addLayout(box_toast, 0, 1)
        lay_pos.addLayout(box_ch_sel, 1, 0); lay_pos.addLayout(box_tc, 1, 1)
        lay_pos.addLayout(box_mini_info, 2, 0) # Fügt die Box in die 3. Zeile ein

        layout.addWidget(grp_pos)
        layout.addStretch(1)
        self.main_tabs.addTab(tab, "🎨 Appearance")

    # ==========================================
    # TAB 3: CONTROLS
    # ==========================================
    def _build_tab_controls(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_inputs = QGroupBox("Input Bindings & Hotkeys")
        lay_inputs = QGridLayout(grp_inputs)

        self.cmb_toggle_src = QComboBox(); self.cmb_toggle_src.addItems(["keyboard", "joystick"]); self.cmb_toggle_src.setCurrentText(self.cfg.OVERLAY.get("toggle_input_source", "keyboard")); self.cmb_toggle_src.currentTextChanged.connect(self._on_toggle_source_changed)
        self.btn_bind_toggle = QPushButton("Bind..."); self.btn_bind_toggle.clicked.connect(self._on_bind_toggle_clicked)
        self.lbl_toggle_binding = QLabel(self._toggle_binding_label_text())

        self.cmb_ch_hotkey_src = QComboBox(); self.cmb_ch_hotkey_src.addItems(["keyboard", "joystick"]); self.cmb_ch_hotkey_src.setCurrentText(self.cfg.OVERLAY.get("challenge_hotkey_input_source", "keyboard")); self.cmb_ch_hotkey_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("hotkey", s))
        self.btn_ch_hotkey_bind = QPushButton("Bind..."); self.btn_ch_hotkey_bind.clicked.connect(lambda: self._on_bind_ch_clicked("hotkey"))
        self.lbl_ch_hotkey_binding = QLabel(self._challenge_binding_label_text("hotkey"))

        self.cmb_ch_left_src = QComboBox(); self.cmb_ch_left_src.addItems(["keyboard", "joystick"]); self.cmb_ch_left_src.setCurrentText(self.cfg.OVERLAY.get("challenge_left_input_source", "keyboard")); self.cmb_ch_left_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("left", s))
        self.btn_ch_left_bind = QPushButton("Bind..."); self.btn_ch_left_bind.clicked.connect(lambda: self._on_bind_ch_clicked("left"))
        self.lbl_ch_left_binding = QLabel(self._challenge_binding_label_text("left"))

        self.cmb_ch_right_src = QComboBox(); self.cmb_ch_right_src.addItems(["keyboard", "joystick"]); self.cmb_ch_right_src.setCurrentText(self.cfg.OVERLAY.get("challenge_right_input_source", "keyboard")); self.cmb_ch_right_src.currentTextChanged.connect(lambda s: self._on_ch_src_changed("right", s))
        self.btn_ch_right_bind = QPushButton("Bind..."); self.btn_ch_right_bind.clicked.connect(lambda: self._on_bind_ch_clicked("right"))
        self.lbl_ch_right_binding = QLabel(self._challenge_binding_label_text("right"))

        lay_inputs.addWidget(QLabel("<b>Show/Hide Stats Overlay:</b>"), 0, 0); lay_inputs.addWidget(self.cmb_toggle_src, 0, 1); lay_inputs.addWidget(self.btn_bind_toggle, 0, 2); lay_inputs.addWidget(self.lbl_toggle_binding, 0, 3)
        lay_inputs.addWidget(QLabel("<hr>"), 1, 0, 1, 4)
        lay_inputs.addWidget(QLabel("<b>Challenge Action / Start:</b>"), 2, 0); lay_inputs.addWidget(self.cmb_ch_hotkey_src, 2, 1); lay_inputs.addWidget(self.btn_ch_hotkey_bind, 2, 2); lay_inputs.addWidget(self.lbl_ch_hotkey_binding, 2, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Nav Left:</b>"), 3, 0); lay_inputs.addWidget(self.cmb_ch_left_src, 3, 1); lay_inputs.addWidget(self.btn_ch_left_bind, 3, 2); lay_inputs.addWidget(self.lbl_ch_left_binding, 3, 3)
        lay_inputs.addWidget(QLabel("<b>Challenge Nav Right:</b>"), 4, 0); lay_inputs.addWidget(self.cmb_ch_right_src, 4, 1); lay_inputs.addWidget(self.btn_ch_right_bind, 4, 2); lay_inputs.addWidget(self.lbl_ch_right_binding, 4, 3)
        lay_inputs.setColumnStretch(3, 1); layout.addWidget(grp_inputs)

        grp_voice = QGroupBox("Voice & Audio")
        lay_voice = QVBoxLayout(grp_voice)
        row_v1 = QHBoxLayout(); row_v1.addWidget(QLabel("AI Voice Volume (Challenges):"))
        self.sld_ch_volume = QSlider(Qt.Orientation.Horizontal); self.sld_ch_volume.setRange(0, 100); self.sld_ch_volume.setValue(int(self.cfg.OVERLAY.get("challenges_voice_volume", 80))); self.sld_ch_volume.valueChanged.connect(self._on_ch_volume_changed)
        row_v1.addWidget(self.sld_ch_volume); self.lbl_ch_volume = QLabel(f"{self.sld_ch_volume.value()}%"); row_v1.addWidget(self.lbl_ch_volume)
        self.chk_ch_voice_mute = QCheckBox("Mute all spoken announcements"); self.chk_ch_voice_mute.setChecked(bool(self.cfg.OVERLAY.get("challenges_voice_mute", False))); self.chk_ch_voice_mute.stateChanged.connect(self._on_ch_mute_toggled)
        lay_voice.addLayout(row_v1); lay_voice.addWidget(self.chk_ch_voice_mute); layout.addWidget(grp_voice)

        layout.addStretch(1)
        self.main_tabs.addTab(tab, "🕹️ Controls")

    def _build_tab_progress(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp = QGroupBox("Local Achievement Progress")
        lay = QVBoxLayout(grp)

        row = QHBoxLayout()
        row.addWidget(QLabel("Select ROM:"))
        self.cmb_progress_rom = QComboBox()
        self.cmb_progress_rom.currentIndexChanged.connect(self._on_progress_rom_changed)
        row.addWidget(self.cmb_progress_rom)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setStyleSheet("background:#00E5FF; color:black; font-weight:bold;")
        btn_refresh.clicked.connect(self._refresh_progress_roms)
        row.addWidget(btn_refresh)
        lay.addLayout(row)

        self.progress_view = QTextBrowser()
        lay.addWidget(self.progress_view)

        layout.addWidget(grp)
        self.main_tabs.addTab(tab, "📈 Progress")

        QTimer.singleShot(2000, self._refresh_progress_roms)

    def _build_tab_available_maps(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp = QGroupBox("Supported Tables (from Cloud/Index)")
        lay = QVBoxLayout(grp)

        row = QHBoxLayout()
        self.txt_map_search = QLineEdit()
        self.txt_map_search.setPlaceholderText("Search for Table or ROM...")
        self.txt_map_search.textChanged.connect(self._filter_available_maps)
        row.addWidget(self.txt_map_search)

        btn_refresh = QPushButton("🔄 Load List")
        btn_refresh.setStyleSheet("background:#FF7F00; color:black; font-weight:bold;")
        btn_refresh.clicked.connect(self._refresh_available_maps)
        row.addWidget(btn_refresh)
        lay.addLayout(row)

        self.maps_view = QTextBrowser()
        lay.addWidget(self.maps_view)

        layout.addWidget(grp)
        self.main_tabs.addTab(tab, "📚 Available Maps")
        self._all_maps_cache = []

    # ==========================================
    # TAB: SYSTEM
    # ==========================================
    def _build_tab_system(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grp_profile = QGroupBox("Player Profile & Cloud Setup")
        lay_profile = QGridLayout(grp_profile)

        self.txt_player_name = QLineEdit()
        self.txt_player_name.setText(self.cfg.OVERLAY.get("player_name", "Player"))
        self.txt_player_name.textChanged.connect(self._save_player_name)

        self.txt_player_id = QLineEdit()
        self.txt_player_id.setText(self.cfg.OVERLAY.get("player_id", "0000"))
        self.txt_player_id.setMaxLength(4)
        self.txt_player_id.setFixedWidth(60)
        self.txt_player_id.textChanged.connect(self._save_player_id)

        self.chk_cloud_enabled = QCheckBox("Enable Cloud Sync")
        self.chk_cloud_enabled.setChecked(self.cfg.CLOUD_ENABLED)
        self.chk_cloud_enabled.stateChanged.connect(self._save_cloud_settings)

        lay_profile.addWidget(QLabel("Display Name:"), 0, 0)
        lay_profile.addWidget(self.txt_player_name, 0, 1)
        lay_profile.addWidget(QLabel("Player ID (Restore):"), 0, 2)
        lay_profile.addWidget(self.txt_player_id, 0, 3)
        lay_profile.addWidget(self.chk_cloud_enabled, 1, 0, 1, 4)

        layout.addWidget(grp_profile)

        grp_paths = QGroupBox("Directory Setup")
        lay_paths = QGridLayout(grp_paths)
        self.base_label = QLabel(f"BASE: {self.cfg.BASE}")
        self.btn_base = QPushButton("Browse..."); self.btn_base.clicked.connect(self.change_base)
        self.nvram_label = QLabel(f"NVRAM: {self.cfg.NVRAM_DIR}")
        self.btn_nvram = QPushButton("Browse..."); self.btn_nvram.clicked.connect(self.change_nvram)
        self.tables_label = QLabel(f"TABLES: {self.cfg.TABLES_DIR}")
        self.btn_tables = QPushButton("Browse..."); self.btn_tables.clicked.connect(self.change_tables)
        lay_paths.addWidget(self.btn_base, 0, 0); lay_paths.addWidget(self.base_label, 0, 1)
        lay_paths.addWidget(self.btn_nvram, 1, 0); lay_paths.addWidget(self.nvram_label, 1, 1)
        lay_paths.addWidget(self.btn_tables, 2, 0); lay_paths.addWidget(self.tables_label, 2, 1)
        lay_paths.setColumnStretch(1, 1); layout.addWidget(grp_paths)

        grp_maint = QGroupBox("Maintenance Tools")
        lay_maint = QVBoxLayout(grp_maint)
        self.btn_repair = QPushButton("Repair Data Folders")
        self.btn_repair.clicked.connect(self._repair_data_folders)
        self.btn_prefetch = QPushButton("Force Cache NVRAM Maps")
        self.btn_prefetch.clicked.connect(self._prefetch_maps_now)
        lay_maint.addWidget(self.btn_repair)
        lay_maint.addWidget(self.btn_prefetch)

        lbl_id_warning = QLabel(
            "⚠️ <b>IMPORTANT: Keep your Player ID safe!</b><br>"
            "Do not share your 4-character Player ID with anyone. "
            "Please write it down or save it somewhere safe!"
        )
        lbl_id_warning.setWordWrap(True)
        lbl_id_warning.setStyleSheet("color: #FF7F00; margin-top: 15px; font-size: 10pt; background: #111; padding: 10px; border: 1px solid #FF7F00; border-radius: 5px;")
        lay_maint.addWidget(lbl_id_warning)

        layout.addWidget(grp_maint)
        layout.addStretch(1)
        self.main_tabs.addTab(tab, "⚙️ System")
