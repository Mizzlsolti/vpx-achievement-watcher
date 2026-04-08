from __future__ import annotations

import copy
import os
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QCheckBox, QGroupBox, QLineEdit, QGridLayout, QMessageBox,
    QDialog, QDialogButtonBox, QTextBrowser, QProgressDialog,
    QTabWidget,
)
from PyQt6.QtCore import Qt, QTimer, QMetaObject, Q_ARG, pyqtSlot, QRegularExpression, QEvent, QPoint
from PyQt6.QtGui import QRegularExpressionValidator, QPainter, QColor, QFont, QFontMetrics, QPolygon
from core.cloud_sync import CloudSync, _sanitize_firebase_keys
from core.watcher_core import (
    ensure_dir, log, sanitize_filename,
    secure_load_json, secure_save_json,
    compute_player_level,
)
from .dialogs import FeedbackDialog
from .vps import _load_vps_mapping, _save_vps_mapping
from mascot.mascot import _TROPHIE_SHARED


def _parse_version(v_str):
    """Parse a version string like '2.5' or '2.5.1' into a comparable tuple of ints."""
    try:
        return tuple(map(int, str(v_str).split('.')))
    except Exception:
        return (0,)


class _PlayerNameLockOverlay(QWidget):
    """Hazard-stripe overlay drawn on top of txt_player_name when Cloud Sync is active.

    Paints alternating yellow/black diagonal stripes and centered white text
    indicating that the field is locked.  The overlay is a child of the target
    QLineEdit so it naturally follows the widget when the UI is resized.
    """

    _TEXT = "🔒 Locked – deactivate Cloud Sync to change"
    _STRIPE_W = 18       # pixel width of each colour band
    _YELLOW = QColor("#F5C518")
    _BLACK = QColor("#000000")
    _MIN_FONT_PX = 9
    _MAX_FONT_PX = 13
    _FONT_PADDING = 4

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()
        parent.installEventFilter(self)

    # ------------------------------------------------------------------
    # Keep overlay sized to cover the parent field at all times
    # ------------------------------------------------------------------
    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.resize(self.parent().size())
        return False

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.resize(self.parent().size())

    # ------------------------------------------------------------------
    # Custom painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        # Yellow base fill
        p.fillRect(0, 0, w, h, self._YELLOW)

        # Black diagonal stripes (45° – going from upper-left to lower-right)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._BLACK)
        sw = self._STRIPE_W
        i = -h
        while i < w:
            poly = QPolygon([
                QPoint(i,          0),
                QPoint(i + sw,     0),
                QPoint(i + sw + h, h),
                QPoint(i + h,      h),
            ])
            p.drawPolygon(poly)
            i += sw * 2

        # Centred text
        font = QFont()
        font.setPixelSize(max(self._MIN_FONT_PX, min(self._MAX_FONT_PX, h - self._FONT_PADDING)))
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        br = fm.boundingRect(self._TEXT)
        tx = (w - br.width()) // 2
        ty = (h + fm.ascent() - fm.descent()) // 2

        # Dark outline / shadow
        p.setPen(self._BLACK)
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1),
                       (0, -1),  (0, 1),  (-1, 0), (1, 0)):
            p.drawText(tx + dx, ty + dy, self._TEXT)

        # White text
        p.setPen(QColor("#FFFFFF"))
        p.drawText(tx, ty, self._TEXT)

        p.end()


class SystemMixin:
    """Mixin that provides the System tab and all related save/action methods.

    Expects the host class to provide:
        self.cfg            – AppConfig instance
        self.main_tabs      – QTabWidget (main tab bar)
        self.watcher        – Watcher instance
        self._add_tab_help_button(layout, key)  – adds the Help button to a tab layout
        self._msgbox_topmost(kind, title, msg)  – thread-safe top-most message box
    """

    def _repair_data_folders(self):
        try:
            ensure_dir(self.cfg.BASE)
            for sub in [
                os.path.join("tools", "NVRAM_Maps"),
                os.path.join("tools", "NVRAM_Maps", "maps"),
                "session_stats",
                os.path.join("Achievements", "rom_specific_achievements"),
            ]:
                ensure_dir(os.path.join(self.cfg.BASE, sub))
            try:
                self.watcher.bootstrap()
            except Exception as e:
                log(self.cfg, f"[REPAIR] bootstrap failed: {e}", "WARN")
            self._msgbox_topmost(
                "info", "Repair",
                "Base folders repaired.\n\nIf maps are still missing, please click 'Cache maps now (prefetch)'\n"
                "or simply start a ROM (maps will then be loaded on demand)."
            )
            log(self.cfg, "[REPAIR] base folders ensured and index/romnames fetched (if missing)")
        except Exception as e:
            log(self.cfg, f"[REPAIR] failed: {e}", "ERROR")
            self._msgbox_topmost("warn", "Repair", f"Repair failed:\n{e}")

    def _prefetch_maps_now(self):
        try:
            self.watcher.start_prefetch_background()
            maps_dir = os.path.join(self.cfg.BASE, "tools", "NVRAM_Maps", "maps")
            QMessageBox.information(
                self, "Prefetch",
                f"Prefetch started. Missing maps are being cached in the background at:\n"
                f"{maps_dir}\n"
                "See watcher.log for progress."
            )
            log(self.cfg, "[PREFETCH] started by user")
        except Exception as e:
            log(self.cfg, f"[PREFETCH] failed: {e}", "ERROR")
            QMessageBox.warning(self, "Prefetch", f"Prefetch failed:\n{e}")

    # ==========================================
    # TAB: SYSTEM
    # ==========================================
    def _build_tab_system(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        system_subtabs = QTabWidget()
        self.system_subtabs = system_subtabs
        tab_layout.addWidget(system_subtabs)

        # ── General sub-tab ────────────────────────────────────────────────────
        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)

        # --- 👤 Player Profile ---
        grp_profile = QGroupBox("👤 Player Profile")
        lay_profile = QGridLayout(grp_profile)

        self.txt_player_name = QLineEdit()
        self.txt_player_name.setText(self.cfg.OVERLAY.get("player_name", "Player"))
        _name_rx = QRegularExpression(r"[\p{L}\d /\\!\"§$%&()\-_,.:;]*")
        self.txt_player_name.setValidator(QRegularExpressionValidator(_name_rx, self.txt_player_name))
        self._player_name_lock_overlay = _PlayerNameLockOverlay(self.txt_player_name)

        self.txt_player_id = QLineEdit()
        self.txt_player_id.setText(self.cfg.OVERLAY.get("player_id", "0000"))
        self.txt_player_id.setMaxLength(4)
        self.txt_player_id.setFixedWidth(60)

        lay_profile.addWidget(QLabel("Display Name:"), 0, 0)
        lay_profile.addWidget(self.txt_player_name, 0, 1)
        lay_profile.addWidget(QLabel("Player ID (Restore):"), 0, 2)
        lay_profile.addWidget(self.txt_player_id, 0, 3)

        lbl_id_warning = QLabel(
            "⚠️ <b>IMPORTANT: Keep your Player ID safe!</b><br>"
            "Do not share your 4-character Player ID with anyone. "
            "Please write it down or save it somewhere safe!"
        )
        lbl_id_warning.setWordWrap(True)
        lbl_id_warning.setStyleSheet("color: #FF7F00; margin-top: 8px; font-size: 10pt; background: #111; padding: 10px; border: 1px solid #FF7F00; border-radius: 5px;")
        lay_profile.addWidget(lbl_id_warning, 1, 0, 1, 4)

        lbl_name_hint = QLabel(
            'ℹ️ Allowed characters: letters, numbers, spaces, and / \\ - _ ! " § $ % & ( ) , . ; :'
        )
        lbl_name_hint.setWordWrap(True)
        lbl_name_hint.setStyleSheet("color: #888888; margin-top: 4px; font-size: 9pt; padding: 4px 8px;")
        lay_profile.addWidget(lbl_name_hint, 2, 0, 1, 4)

        layout.addWidget(grp_profile)

        # --- ☁️ Cloud Sync & Backup ---
        grp_cloud = QGroupBox("☁️ Cloud Sync & Backup")
        lay_cloud = QVBoxLayout(grp_cloud)

        self.chk_cloud_enabled = QCheckBox("Enable Cloud Sync")
        self.chk_cloud_enabled.setChecked(self.cfg.CLOUD_ENABLED)
        self.chk_cloud_enabled.stateChanged.connect(self._save_cloud_settings)
        lay_cloud.addWidget(self.chk_cloud_enabled)

        self.chk_cloud_backup = QCheckBox("💾 Auto-Backup Progress to Cloud")
        self.chk_cloud_backup.setToolTip(
            "When enabled, your achievement progress and VPS mapping "
            "are automatically uploaded to the cloud for backup purposes. "
            "Use 'Restore from Cloud' to recover your data on a new PC."
        )
        self.chk_cloud_backup.setChecked(self.cfg.CLOUD_BACKUP_ENABLED)
        self.chk_cloud_backup.setVisible(self.cfg.CLOUD_ENABLED)
        self.chk_cloud_backup.stateChanged.connect(self._save_cloud_backup_settings)
        lay_cloud.addWidget(self.chk_cloud_backup)

        lay_cloud_btns = QHBoxLayout()

        self.btn_backup_cloud = QPushButton("☁️ Backup to Cloud")
        self.btn_backup_cloud.setToolTip(
            "Manually upload your full achievement data, VPS mapping, and ROM progress to the cloud. "
            "Use this to create an immediate backup of your current data."
        )
        self.btn_backup_cloud.setVisible(self.cfg.CLOUD_ENABLED)
        self.btn_backup_cloud.clicked.connect(self._manual_cloud_backup)
        lay_cloud_btns.addWidget(self.btn_backup_cloud)

        self.btn_restore_cloud = QPushButton("☁️ Restore from Cloud")
        self.btn_restore_cloud.setToolTip(
            "Downloads your full achievement progress from the cloud using your Player ID. "
            "Use this to restore your achievements on a new PC. "
            "Warning: This will overwrite your local achievement data."
        )
        self.btn_restore_cloud.setVisible(self.cfg.CLOUD_ENABLED)
        self.btn_restore_cloud.clicked.connect(self._restore_achievements_from_cloud)
        lay_cloud_btns.addWidget(self.btn_restore_cloud)

        lay_cloud.addLayout(lay_cloud_btns)
        layout.addWidget(grp_cloud)

        # Lock player identity fields on startup if Cloud Sync is already enabled
        if self.cfg.CLOUD_ENABLED:
            self._lock_player_identity_fields(True)

        # --- 🐛 Feedback & Bug Reports ---
        grp_feedback = QGroupBox("🐛 Feedback & Bug Reports")
        lay_feedback = QVBoxLayout(grp_feedback)
        lbl_feedback = QLabel(
            "Found a bug or have a suggestion? Report it directly here!"
        )
        lbl_feedback.setWordWrap(True)
        lbl_feedback.setStyleSheet("color: #00E5FF; font-size: 9pt;")
        lay_feedback.addWidget(lbl_feedback)
        btn_feedback = QPushButton("🐛 Report Bug / Suggestion")
        btn_feedback.setStyleSheet(
            "QPushButton { background-color: #FF7F00; color: #FFFFFF; font-weight: bold;"
            "  border: none; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e06d00; }"
        )
        btn_feedback.clicked.connect(lambda: FeedbackDialog(self).exec())
        lay_feedback.addWidget(btn_feedback)
        layout.addWidget(grp_feedback)

        layout.addStretch(1)
        self._add_tab_help_button(layout, "system_general")
        system_subtabs.addTab(general_tab, "⚙️ General")

        # ── Maintenance sub-tab ────────────────────────────────────────────────
        maint_tab = QWidget()
        maint_layout = QVBoxLayout(maint_tab)

        # --- 📁 Directory Setup ---
        grp_paths = QGroupBox("📁 Directory Setup")
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
        lay_paths.setColumnStretch(1, 1); maint_layout.addWidget(grp_paths)

        # --- 🔧 Maintenance & Updates ---
        grp_maint = QGroupBox("🔧 Maintenance & Updates")
        lay_maint = QVBoxLayout(grp_maint)
        self.btn_repair = QPushButton("Repair Data Folders")
        self.btn_repair.clicked.connect(self._repair_data_folders)
        self.btn_prefetch = QPushButton("Force Cache NVRAM Maps")
        self.btn_prefetch.clicked.connect(self._prefetch_maps_now)
        lay_maint.addWidget(self.btn_repair)
        lay_maint.addWidget(self.btn_prefetch)

        self.btn_update_dbs = QPushButton("🔄 Update Databases (Index, NVRAM Maps, VPS DB, VPXTool)")
        self.btn_update_dbs.setToolTip("Force re-download of index.json, romnames.json, vpsdb.json and vpxtool, then reload.")
        self.btn_update_dbs.clicked.connect(self._update_databases_now)
        lay_maint.addWidget(self.btn_update_dbs)

        self.btn_self_update = QPushButton("⬆️ Watcher Update")
        self.btn_self_update.setToolTip("Checks GitHub for a newer release and downloads + installs it automatically.")
        self.btn_self_update.clicked.connect(self._check_for_app_update)
        lay_maint.addWidget(self.btn_self_update)

        maint_layout.addWidget(grp_maint)

        maint_layout.addStretch(1)
        self._add_tab_help_button(maint_layout, "system_maintenance")
        system_subtabs.addTab(maint_tab, "🔧 Maintenance")

        self.main_tabs.addTab(tab, "⚙️ System")

    # ==========================================
    # CLEAN SAVE METHODS
    # ==========================================
    def _on_trophie_gui_toggled(self):
        enabled = self.chk_trophie_gui.isChecked()
        self.cfg.OVERLAY["trophie_gui_enabled"] = enabled
        self.cfg.save()
        try:
            if enabled:
                self._trophie_gui.show()
            else:
                self._trophie_gui._dismiss_bubble()
                self._trophie_gui.hide()
        except Exception:
            pass
        ov_enabled = bool(self.cfg.OVERLAY.get("trophie_overlay_enabled", True))
        _TROPHIE_SHARED["gui_visible"] = enabled and ov_enabled

    def _on_trophie_overlay_toggled(self):
        enabled = self.chk_trophie_overlay.isChecked()
        self.cfg.OVERLAY["trophie_overlay_enabled"] = enabled
        self.cfg.save()
        try:
            if enabled:
                self._trophie_overlay.show()
            else:
                self._trophie_overlay._dismiss_bubble()
                self._trophie_overlay.hide()
        except Exception:
            pass
        gui_enabled = bool(self.cfg.OVERLAY.get("trophie_gui_enabled", True))
        _TROPHIE_SHARED["gui_visible"] = enabled and gui_enabled

    def _on_trophie_overlay_portrait_toggled(self):
        enabled = self.chk_trophie_overlay_portrait.isChecked()
        self.cfg.OVERLAY["trophie_overlay_portrait"] = enabled
        self.cfg.save()
        try:
            self._trophie_overlay.apply_portrait_from_cfg()
        except Exception:
            pass

    def _on_trophie_overlay_ccw_toggled(self):
        enabled = self.chk_trophie_overlay_ccw.isChecked()
        self.cfg.OVERLAY["trophie_overlay_rotate_ccw"] = enabled
        self.cfg.save()
        try:
            self._trophie_overlay.apply_portrait_from_cfg()
        except Exception:
            pass

    def _save_cloud_settings(self):
        QTimer.singleShot(0, self._apply_cloud_settings)

    def _apply_cloud_settings(self):
        if self.chk_cloud_enabled.isChecked():
            pname = self.txt_player_name.text().strip()
            pid = self.txt_player_id.text().strip()
            name_invalid = not pname or pname.lower() == "player"
            id_invalid = not pid or len(pid) != 4
            if name_invalid or id_invalid:
                self.chk_cloud_enabled.blockSignals(True)
                self.chk_cloud_enabled.setChecked(False)
                self.chk_cloud_enabled.blockSignals(False)
                self.cfg.CLOUD_ENABLED = False
                if getattr(self, "btn_backup_cloud", None):
                    self.btn_backup_cloud.setVisible(False)
                if getattr(self, "btn_restore_cloud", None):
                    self.btn_restore_cloud.setVisible(False)
                if getattr(self, "chk_cloud_backup", None):
                    self.chk_cloud_backup.setVisible(False)
                    self.chk_cloud_backup.setChecked(False)
                    self.cfg.CLOUD_BACKUP_ENABLED = False
                self.cfg.save()
                if name_invalid and id_invalid:
                    self._msgbox_topmost(
                        "warn",
                        "⛔ Invalid Player Profile",
                        "Please enter a valid display name and a valid 4-character Player ID before enabling Cloud Sync.",
                    )
                elif name_invalid:
                    self._msgbox_topmost(
                        "warn",
                        "⛔ Invalid Player Name",
                        "Please enter a valid display name. The default name 'Player' is not allowed.",
                    )
                else:
                    self._msgbox_topmost(
                        "warn",
                        "⛔ Invalid Player ID",
                        "Please enter a valid 4-character Player ID.",
                    )
                return

            # Both locally valid — run cloud uniqueness check asynchronously.
            # Use QMetaObject.invokeMethod (QueuedConnection) to safely deliver the
            # result from the background thread back to the GUI thread.
            def _check():
                try:
                    cfg_snap = copy.copy(self.cfg)
                    cfg_snap.CLOUD_ENABLED = True
                    result = CloudSync.validate_player_identity(cfg_snap, pid, pname)
                except Exception as _exc:
                    result = {"ok": False, "reason": "error", "msg": f"⛔ Cloud check failed: {_exc}"}
                QMetaObject.invokeMethod(
                    self, "_on_cloud_validate_done",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(bool, bool(result.get("ok", False))),
                    Q_ARG(str, str(result.get("reason", ""))),
                    Q_ARG(str, str(result.get("msg", ""))),
                    Q_ARG(str, pname),
                    Q_ARG(str, pid),
                )

            threading.Thread(target=_check, daemon=True).start()
            return

        # Cloud Sync is being disabled
        self.cfg.CLOUD_ENABLED = False
        self.cfg.save()
        self._lock_player_identity_fields(False)
        if hasattr(self, "_highscore_poll_timer"):
            self._highscore_poll_timer.stop()
        if getattr(self, "btn_backup_cloud", None):
            self.btn_backup_cloud.setVisible(False)
        if getattr(self, "btn_restore_cloud", None):
            self.btn_restore_cloud.setVisible(False)
        if getattr(self, "chk_cloud_backup", None):
            self.chk_cloud_backup.setVisible(False)
            self.chk_cloud_backup.setChecked(False)
            self.cfg.CLOUD_BACKUP_ENABLED = False
            self.cfg.save()

    @pyqtSlot(bool, str, str, str, str)
    def _on_cloud_validate_done(self, ok: bool, reason: str, msg: str, new_name: str, new_id: str):
        """Slot invoked on the GUI thread after the background cloud-identity check finishes."""
        self._handle_cloud_sync_enable_result({"ok": ok, "reason": reason, "msg": msg}, new_name, new_id)

    def _handle_cloud_sync_enable_result(self, result: dict, new_name: str, new_id: str):
        """Called on the main thread after the async cloud identity validation completes.

        On success: persists both fields, enables Cloud Sync, locks the identity
        fields, and shows a confirmation popup.
        On conflict: unchecks the checkbox and shows a warning popup — fields stay
        unlocked so the user can correct them and try again.
        """
        if result.get("ok"):
            self._save_player_name(new_name)
            self._save_player_id(new_id)
            self.cfg.CLOUD_ENABLED = True
            self.cfg.save()
            # Immediately upload the player name so new players appear in opponent lists
            # before their first game session (which is when upload_full_achievements runs).
            if self.cfg.CLOUD_URL:
                import threading as _threading
                from core.cloud_sync import CloudSync as _CloudSync
                _pid = new_id.strip()
                _name = new_name.strip()
                if _pid and _name and _name.lower() != "player":
                    _threading.Thread(
                        target=lambda: _CloudSync.set_node(self.cfg, f"players/{_pid}/achievements/name", _name),
                        daemon=True,
                    ).start()
            if getattr(self, "btn_backup_cloud", None):
                self.btn_backup_cloud.setVisible(True)
            if getattr(self, "btn_restore_cloud", None):
                self.btn_restore_cloud.setVisible(True)
            if getattr(self, "chk_cloud_backup", None):
                self.chk_cloud_backup.setVisible(True)
            if hasattr(self, "_highscore_poll_timer"):
                if not self._highscore_poll_timer.isActive():
                    self._highscore_poll_timer.start()
            if self.cfg.CLOUD_URL:
                CloudSync.cleanup_legacy_progress(self.cfg)
            self._lock_player_identity_fields(True)
            self._msgbox_topmost(
                "info",
                "✅ Cloud Sync enabled!",
                "Your player profile has been saved and Cloud Sync is now active.",
            )
            try:
                if getattr(self, "_trophie_gui", None):
                    self._trophie_gui.on_cloud_enabled()
            except Exception:
                pass
            return

        # Validation failed — uncheck the checkbox and keep cloud disabled
        self.chk_cloud_enabled.blockSignals(True)
        self.chk_cloud_enabled.setChecked(False)
        self.chk_cloud_enabled.blockSignals(False)
        self.cfg.CLOUD_ENABLED = False
        self.cfg.save()
        reason = result.get("reason", "")
        if reason == "id_conflict":
            title = "⛔ Player ID already taken!"
            msg = "This Player ID is already registered to another player. Please choose a different 4-character ID."
        elif reason == "name_conflict":
            title = "⛔ Player Name already taken!"
            msg = "This display name is already in use by another player. Please choose a different name."
        else:
            title = "⛔ Identity Conflict"
            msg = result.get("msg", "Identity conflict detected.")
        self._msgbox_topmost("warn", title, msg)

    def _save_cloud_backup_settings(self):
        self.cfg.CLOUD_BACKUP_ENABLED = self.chk_cloud_backup.isChecked()
        self.cfg.save()

    def _save_overlay_page_settings(self):
        self.cfg.OVERLAY["overlay_page2_enabled"] = self.chk_overlay_page2.isChecked()
        self.cfg.OVERLAY["overlay_page3_enabled"] = self.chk_overlay_page3.isChecked()
        self.cfg.OVERLAY["overlay_page4_enabled"] = self.chk_overlay_page4.isChecked()
        self.cfg.OVERLAY["overlay_page5_enabled"] = self.chk_overlay_page5.isChecked()
        self.cfg.save()

    def _save_player_name(self, name):
        self.cfg.OVERLAY["player_name"] = name.strip()
        self.cfg.save()

    def _save_player_id(self, player_id):
        self.cfg.OVERLAY["player_id"] = player_id.strip()
        self.cfg.save()

    def _lock_player_identity_fields(self, locked: bool):
        """Disable or enable the Player Name and Player ID fields."""
        for widget in (
            getattr(self, "txt_player_name", None),
            getattr(self, "txt_player_id", None),
        ):
            if widget is not None:
                widget.setEnabled(not locked)

        overlay = getattr(self, "_player_name_lock_overlay", None)
        if overlay is not None:
            if locked:
                overlay.show()
                overlay.raise_()
            else:
                overlay.hide()

    def _restore_achievements_from_cloud(self):
        if not self.cfg.CLOUD_ENABLED or not self.cfg.CLOUD_URL:
            self._msgbox_topmost("warn", "Restore from Cloud", "Cloud sync is not enabled.")
            return

        pid = str(self.cfg.OVERLAY.get("player_id", "")).strip()
        if not pid or pid == "unknown":
            self._msgbox_topmost("warn", "Restore from Cloud", "Please set a valid Player ID first.")
            return

        confirm = QMessageBox.question(
            self,
            "Restore from Cloud",
            "This will overwrite your local achievement data with the cloud version. Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Restore achievements state and progress data via CloudSync
        ok = CloudSync.restore_from_cloud(self.cfg)
        if not ok:
            self._msgbox_topmost(
                "warn",
                "Restore from Cloud",
                "No achievement data found in the cloud for your Player ID, or the restore failed.",
            )
            return

        # Restore VPS ID Mapping from Cloud
        vps_mapping_restored = False
        try:
            vps_data = CloudSync.fetch_node(self.cfg, f"players/{pid}/vps_mapping")
            if vps_data and isinstance(vps_data, dict):
                from .vps import _save_vps_mapping
                _save_vps_mapping(self.cfg, vps_data)
                vps_mapping_restored = True
                log(self.cfg, f"[CLOUD] VPS mapping restored: {len(vps_data)} entries")
                # Refresh in-memory cache vps_id entries so the Available Maps tab updates immediately
                try:
                    for entry in self._all_maps_cache:
                        entry["vps_id"] = vps_data.get(entry["rom"], "")
                    self._filter_available_maps()
                except Exception as _refresh_err:
                    log(self.cfg, f"[CLOUD] VPS mapping cache refresh failed: {_refresh_err}", "WARN")
        except Exception as _vps_err:
            log(self.cfg, f"[CLOUD] VPS mapping restore failed: {_vps_err}", "WARN")

        # Restore CAT achievement progress from Cloud
        cat_progress_restored = False
        try:
            from core.cat_registry import CAT_REGISTRY
            from core.config import f_custom_achievements_progress
            from core.watcher_core import _strip_version_from_name

            cap_path = f_custom_achievements_progress(self.cfg)
            ensure_dir(os.path.dirname(cap_path))
            existing_cap = secure_load_json(cap_path, {}) or {}

            for firebase_key, registry_entry in CAT_REGISTRY.items():
                table_key = registry_entry.get("table_key", "")
                if not table_key:
                    continue
                try:
                    cat_data = CloudSync.fetch_node(self.cfg, f"players/{pid}/progress_cat/{firebase_key}")
                    if not cat_data or not isinstance(cat_data, dict):
                        continue

                    unlocked_titles = cat_data.get("unlocked_titles", [])
                    total = int(cat_data.get("total", 0))

                    if not unlocked_titles:
                        continue

                    unlocked_entries = []
                    for title in unlocked_titles:
                        if isinstance(title, str) and title.strip():
                            unlocked_entries.append({
                                "title": title.strip(),
                                "event": "",
                                "ts": cat_data.get("ts", ""),
                            })

                    if unlocked_entries:
                        stripped_table_key = _strip_version_from_name(table_key).strip()
                        local_key = table_key
                        for existing_key in existing_cap:
                            if _strip_version_from_name(existing_key).strip() == stripped_table_key:
                                local_key = existing_key
                                break

                        existing_cap[local_key] = {
                            "unlocked": unlocked_entries,
                            "total_rules": total if total > 0 else len(unlocked_entries),
                        }
                        cat_progress_restored = True
                        log(self.cfg, f"[CLOUD] CAT progress restored for '{local_key}': {len(unlocked_entries)} achievements")
                except Exception as _cat_err:
                    log(self.cfg, f"[CLOUD] CAT restore failed for '{firebase_key}': {_cat_err}", "WARN")

            if cat_progress_restored:
                secure_save_json(cap_path, existing_cap)
        except Exception as _cat_restore_err:
            log(self.cfg, f"[CLOUD] CAT progress restore failed: {_cat_restore_err}", "WARN")

        # Refresh level display and notify listeners
        try:
            self._refresh_level_display()
        except Exception:
            pass
        try:
            self.bridge.achievements_updated.emit()
        except Exception:
            pass

        parts = ["Achievement data"]
        if vps_mapping_restored:
            parts.append("VPS ID mapping")
        if cat_progress_restored:
            parts.append("CAT progress")
        if len(parts) == 1:
            msg = parts[0]
        elif len(parts) == 2:
            msg = f"{parts[0]} and {parts[1]}"
        else:
            msg = ", ".join(parts[:-1]) + " and " + parts[-1]
        msg += " successfully restored from the cloud!"
        self._msgbox_topmost("info", "Restore from Cloud", msg)

    def _manual_cloud_backup(self):
        """Perform a full manual backup of all local data to cloud."""
        if not self.cfg.CLOUD_ENABLED or not self.cfg.CLOUD_URL:
            self._msgbox_topmost("warn", "Backup to Cloud", "Cloud sync is not enabled.")
            return

        pid = str(self.cfg.OVERLAY.get("player_id", "")).strip()
        if not pid or pid == "unknown":
            self._msgbox_topmost("warn", "Backup to Cloud", "Please set a valid Player ID first.")
            return

        player_name = self.cfg.OVERLAY.get("player_name", "").strip()
        if not player_name or player_name.lower() == "player":
            self._msgbox_topmost("warn", "Backup to Cloud", "Please set a valid player name (not 'Player') first.")
            return

        confirm = QMessageBox.question(
            self,
            "Backup to Cloud",
            "This will upload your current data to the cloud. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.btn_backup_cloud.setEnabled(False)
        self.btn_backup_cloud.setText("⏳ Backing up...")

        def _worker():
            from datetime import datetime, timezone
            from core.watcher_core import compute_player_level
            from core.config import f_custom_achievements_progress
            from core.watcher_core import secure_load_json
            results = []
            errors = []

            state = self.watcher._ach_state_load()

            # Load CAT progress to include in the achievements payload
            custom_progress: dict = {}
            try:
                custom_progress = secure_load_json(f_custom_achievements_progress(self.cfg)) or {}
            except Exception:
                pass

            # 1. Upload achievements metadata (without session to avoid oversized request)
            try:
                lv = compute_player_level(state)
                badges = list(state.get("badges") or [])
                selected_badge = state.get("selected_badge", "")
                metadata_payload = {
                    "name": player_name,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "global": list(state.get("global", {}).get("__global__", []) or []),
                    "roms_played": list(state.get("roms_played", []) or []),
                    "player_level": lv["level"],
                    "player_level_name": lv["name"],
                    "player_prestige": lv["prestige"],
                    "player_prestige_display": lv["prestige_display"],
                    "player_fully_maxed": lv["fully_maxed"],
                    "badges": badges,
                    "badge_count": len(badges),
                    "selected_badge": selected_badge,
                }
                if custom_progress:
                    metadata_payload["custom_progress"] = _sanitize_firebase_keys(custom_progress)
                if CloudSync.set_node(self.cfg, f"players/{pid}/achievements", metadata_payload):
                    results.append("✅ Achievements metadata")
                    log(self.cfg, "[CLOUD] Manual backup: achievements metadata uploaded")
                else:
                    errors.append("❌ Achievements metadata: upload failed")
            except Exception as e:
                errors.append(f"❌ Achievements metadata: {e}")
                log(self.cfg, f"[CLOUD] Manual backup: achievements metadata upload failed: {e}", "WARN")

            # 1b. Upload session data per ROM to keep each request small
            session_uploaded = 0
            session_errors = 0
            try:
                session = dict(state.get("session", {}) or {})
                for rom, entries in session.items():
                    if entries:
                        if CloudSync.set_node(self.cfg, f"players/{pid}/achievements/session/{rom}", entries):
                            session_uploaded += 1
                        else:
                            session_errors += 1
                            log(self.cfg, f"[CLOUD] Manual backup: session upload failed for {rom}", "WARN")
                if session_uploaded > 0:
                    results.append(f"✅ Session for {session_uploaded} ROM(s)")
                if session_errors > 0:
                    errors.append(f"❌ Session: {session_errors} ROM(s) failed")
            except Exception as e:
                errors.append(f"❌ Session: {e}")
                log(self.cfg, f"[CLOUD] Manual backup: session upload failed: {e}", "WARN")

            # 2. Upload VPS mapping
            try:
                from .vps import _load_vps_mapping
                mapping = _load_vps_mapping(self.cfg)
                if CloudSync.set_node(self.cfg, f"players/{pid}/vps_mapping", mapping):
                    results.append(f"✅ VPS mapping ({len(mapping)} entries)")
                    log(self.cfg, f"[CLOUD] Manual backup: VPS mapping uploaded: {len(mapping)} entries")
                else:
                    errors.append("❌ VPS mapping: upload failed")
            except Exception as e:
                errors.append(f"❌ VPS mapping: {e}")
                log(self.cfg, f"[CLOUD] Manual backup: VPS mapping upload failed: {e}", "WARN")

            # 3. Upload progress for each ROM that has session data
            def _entry_title(e):
                return str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()

            progress_uploaded = 0
            progress_errors = 0
            try:
                session = state.get("session", {}) or {}
                for rom, entries in session.items():
                    if not entries:
                        continue
                    try:
                        rules = self.watcher._collect_player_rules_for_rom(rom)
                        total = len(rules)
                        if total == 0:
                            continue
                        unlocked_titles = {_entry_title(e) for e in entries}
                        unlocked = sum(
                            1 for r in rules
                            if str(r.get("title", "")).strip() in unlocked_titles
                        )
                        percentage = round((unlocked / total) * 100, 1)
                        progress_payload = {
                            "name": player_name,
                            "unlocked": unlocked,
                            "total": total,
                            "percentage": percentage,
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }
                        if CloudSync.set_node(self.cfg, f"players/{pid}/progress/{rom}", progress_payload):
                            progress_uploaded += 1
                        else:
                            progress_errors += 1
                    except Exception as _rom_err:
                        progress_errors += 1
                        log(self.cfg, f"[CLOUD] Manual backup: progress upload failed for {rom}: {_rom_err}", "WARN")
                if progress_uploaded > 0:
                    results.append(f"✅ Progress for {progress_uploaded} ROM(s)")
                if progress_errors > 0:
                    errors.append(f"❌ Progress: {progress_errors} ROM(s) failed")
            except Exception as e:
                errors.append(f"❌ Progress: {e}")
                log(self.cfg, f"[CLOUD] Manual backup: progress iteration failed: {e}", "WARN")

            # 4. Upload CAT progress via upload_cat_progress() (includes unlocked_titles)
            cat_uploaded = 0
            cat_errors = 0
            try:
                from core.cat_registry import upload_cat_progress
                from core.config import f_custom_achievements_progress
                all_cat_progress = secure_load_json(f_custom_achievements_progress(self.cfg)) or {}
                if isinstance(all_cat_progress, dict):
                    for table_key in all_cat_progress:
                        try:
                            if upload_cat_progress(self.cfg, table_key):
                                cat_uploaded += 1
                            else:
                                cat_errors += 1
                        except Exception as _cat_err:
                            cat_errors += 1
                            log(self.cfg, f"[CLOUD] Manual backup: CAT upload failed for '{table_key}': {_cat_err}", "WARN")
                if cat_uploaded > 0:
                    results.append(f"✅ CAT Progress for {cat_uploaded} table(s)")
                if cat_errors > 0:
                    errors.append(f"❌ CAT Progress: {cat_errors} table(s) failed")
            except Exception as e:
                errors.append(f"❌ CAT Progress: {e}")
                log(self.cfg, f"[CLOUD] Manual backup: CAT progress iteration failed: {e}", "WARN")

            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            summary = "\n".join(results + errors)
            QMetaObject.invokeMethod(self, "_on_manual_cloud_backup_done",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, summary),
                Q_ARG(bool, len(errors) == 0))

        import threading
        threading.Thread(target=_worker, daemon=True, name="ManualCloudBackup").start()

    @pyqtSlot(str, bool)
    def _on_manual_cloud_backup_done(self, summary: str, success: bool):
        self.btn_backup_cloud.setEnabled(True)
        self.btn_backup_cloud.setText("☁️ Backup to Cloud")
        if success:
            self._msgbox_topmost("info", "Backup to Cloud", f"Backup completed successfully!\n\n{summary}")
        else:
            self._msgbox_topmost("warn", "Backup to Cloud", f"Backup completed with some issues:\n\n{summary}")

    def _cloud_upload_vps_mapping(self):
        """Upload vps_id_mapping.json to cloud under players/{pid}/vps_mapping."""
        if not self.cfg.CLOUD_ENABLED or not self.cfg.CLOUD_URL:
            return
        if not self.cfg.CLOUD_BACKUP_ENABLED:
            return
        pid = str(self.cfg.OVERLAY.get("player_id", "")).strip()
        if not pid or pid == "unknown":
            return
        try:
            from .vps import _load_vps_mapping
            mapping = _load_vps_mapping(self.cfg)
            CloudSync.set_node(self.cfg, f"players/{pid}/vps_mapping", mapping)
            log(self.cfg, f"[CLOUD] VPS mapping uploaded: {len(mapping)} entries")
        except Exception as e:
            log(self.cfg, f"[CLOUD] VPS mapping upload failed: {e}", "WARN")

    def _update_databases_now(self):
        import threading
        self.btn_update_dbs.setEnabled(False)
        self.btn_update_dbs.setText("⏳ Updating...")

        def _worker():
            try:
                from core.watcher_core import (
                    f_index, f_romnames, f_vpsdb_cache,
                    INDEX_URL, ROMNAMES_URL, _fetch_bytes_url, ensure_dir, load_json, log,
                    VPXTOOL_PATH, ensure_vpxtool
                )
                from .vps import VPSDB_URL
                import os

                cfg = self.cfg

                def _force_download(path, url):
                    try:
                        data = _fetch_bytes_url(url, timeout=30)
                        ensure_dir(os.path.dirname(path))
                        with open(path, "wb") as f:
                            f.write(data)
                        log(cfg, f"[UPDATE] Re-downloaded {url} -> {path}")
                        return True
                    except Exception as e:
                        log(cfg, f"[UPDATE] Failed to download {url}: {e}", "WARN")
                        return False

                _force_download(f_index(cfg), INDEX_URL)
                _force_download(f_romnames(cfg), ROMNAMES_URL)
                _force_download(f_vpsdb_cache(cfg), VPSDB_URL)

                try:
                    if os.path.isfile(VPXTOOL_PATH):
                        os.remove(VPXTOOL_PATH)
                    ensure_vpxtool(cfg)
                except Exception as e:
                    log(cfg, f"[UPDATE] vpxtool re-download failed: {e}", "WARN")

                self.watcher.INDEX = load_json(f_index(cfg), {}) or {}
                self.watcher.ROMNAMES = load_json(f_romnames(cfg), {}) or {}

            except Exception as e:
                log(self.cfg, f"[UPDATE] _update_databases_now worker failed: {e}", "WARN")
            finally:
                from PyQt6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(self, "_on_update_databases_done", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=_worker, daemon=True, name="UpdateDatabases").start()

    @pyqtSlot()
    def _on_update_databases_done(self):
        self.btn_update_dbs.setEnabled(True)
        self.btn_update_dbs.setText("🔄 Update Databases (Index, NVRAM Maps, VPS DB, VPXTool)")
        self._msgbox_topmost("info", "Update Databases", "Databases updated successfully!\n\nindex.json, romnames.json, vpsdb.json and vpxtool have been refreshed.")

    def _check_for_app_update(self):
        import threading
        self.btn_self_update.setEnabled(False)
        self.btn_self_update.setText("⏳ Checking...")

        def _worker():
            try:
                from core.watcher_core import _fetch_json_url, log

                RELEASES_API = "https://api.github.com/repos/Mizzlsolti/vpx-achievement-watcher/releases/latest"

                release = _fetch_json_url(RELEASES_API, timeout=15)
                tag = str(release.get("tag_name", "")).strip().lstrip("v")
                body = str(release.get("body", ""))

                if _parse_version(tag) <= _parse_version(self.CURRENT_VERSION):
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(self, "_on_update_check_result",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, "up_to_date"),
                        Q_ARG(str, tag),
                        Q_ARG(str, ""),
                        Q_ARG(str, ""))
                    return

                assets = release.get("assets") or []
                exe_asset = None
                # Prefer the Setup installer (e.g. VPX-Achievement-Watcher-Setup.exe)
                for a in assets:
                    name = str(a.get("name", "")).lower()
                    if "setup" in name and name.endswith(".exe"):
                        exe_asset = a
                        break
                # Fall back to any .exe asset if no Setup asset found
                if not exe_asset:
                    for a in assets:
                        name = str(a.get("name", "")).lower()
                        if name.endswith(".exe"):
                            exe_asset = a
                            break

                if not exe_asset:
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(self, "_on_update_check_result",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, "no_asset"),
                        Q_ARG(str, tag),
                        Q_ARG(str, ""),
                        Q_ARG(str, body))
                    return

                download_url = exe_asset.get("browser_download_url", "")

                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(self, "_on_update_check_result",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, "available"),
                    Q_ARG(str, tag),
                    Q_ARG(str, download_url),
                    Q_ARG(str, body))
            except Exception as e:
                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(self, "_on_update_check_result",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, f"error:{e}"),
                    Q_ARG(str, ""),
                    Q_ARG(str, ""),
                    Q_ARG(str, ""))

        threading.Thread(target=_worker, daemon=True, name="AppUpdateCheck").start()

    @pyqtSlot(str, str, str, str)
    def _on_update_check_result(self, status: str, tag: str, download_url: str, body: str):
        self.btn_self_update.setEnabled(True)
        self.btn_self_update.setText("⬆️ Watcher Update")

        if status == "up_to_date":
            self._msgbox_topmost("info", "Watcher Update", f"You are running the latest version (v{self.CURRENT_VERSION}).")
            return
        if status == "no_asset":
            self._msgbox_topmost("info", "Watcher Update", f"Latest release: v{tag}\nNo .exe asset found in this release.")
            return
        if status.startswith("error:"):
            self._msgbox_topmost("warn", "Watcher Update", f"Could not check for updates:\n{status[6:]}")
            return
        if status == "available":
            # Add update notification to Dashboard feed
            try:
                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self, "_add_update_notification",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, tag),
                )
            except Exception:
                pass
            from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                          QLabel, QTextBrowser, QDialogButtonBox)

            dlg = QDialog(self)
            dlg.setWindowTitle("Watcher Update Available")
            dlg.resize(600, 500)
            lay = QVBoxLayout(dlg)

            lbl_heading = QLabel(f"<b>New version available: v{tag}</b>")
            lbl_heading.setStyleSheet("font-size: 13pt;")
            lay.addWidget(lbl_heading)

            lbl_info = QLabel("Do you want to download and install it now?\nThe app will restart automatically after the update.")
            lbl_info.setWordWrap(True)
            lay.addWidget(lbl_info)

            notes_browser = QTextBrowser()
            notes_browser.setReadOnly(True)
            notes_browser.setOpenExternalLinks(True)
            if body:
                sb = notes_browser.verticalScrollBar()
                old_val = sb.value()
                old_max = max(1, sb.maximum())
                at_bottom = (old_val >= old_max - 2)
                ratio = old_val / old_max if old_max > 0 else 0.0
                notes_browser.setPlainText(body)
                new_max = max(1, sb.maximum())
                if at_bottom:
                    sb.setValue(sb.maximum())
                else:
                    sb.setValue(max(0, min(int(round(ratio * new_max)), new_max)))
            lay.addWidget(notes_browser, 1)

            btn_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
            btn_box.accepted.connect(dlg.accept)
            btn_box.rejected.connect(dlg.reject)
            lay.addWidget(btn_box)

            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            self._do_app_update(download_url)

    def _do_app_update(self, download_url: str):
        import threading
        from PyQt6.QtWidgets import QProgressDialog
        from PyQt6.QtCore import Qt

        self.btn_self_update.setEnabled(False)
        self.btn_self_update.setText("⏳ Downloading update...")

        progress_dlg = QProgressDialog("Downloading update…", None, 0, 0, self)
        progress_dlg.setWindowTitle("Watcher Update")
        progress_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setCancelButton(None)
        progress_dlg.setMinimum(0)
        progress_dlg.setMaximum(0)
        progress_dlg.show()
        self._update_progress_dlg = progress_dlg

        def _download_and_install():
            try:
                import os, tempfile, subprocess
                from core.watcher_core import _fetch_bytes_url, log

                log(self.cfg, f"[UPDATE] Downloading Setup from {download_url}")
                data = _fetch_bytes_url(download_url, timeout=120)

                tmp_dir = tempfile.mkdtemp(prefix="vpx_ach_update_")
                setup_exe = os.path.join(tmp_dir, "VPX-Achievement-Watcher-Setup.exe")

                with open(setup_exe, "wb") as f:
                    f.write(data)
                log(self.cfg, f"[UPDATE] Downloaded Setup to {setup_exe}")

                # Batch file runs the installer silently then cleans up the temp files.
                # The installer restarts Achievement_Watcher.exe via its silent [Run] entry.
                bat_path = os.path.join(tmp_dir, "vpx_ach_update.bat")
                bat = (
                    "@echo off\r\n"
                    "timeout /t 2 /nobreak >nul\r\n"
                    f'"{setup_exe}" /SILENT /NORESTART /SP-\r\n'
                    f'del /f /q "{setup_exe}"\r\n'
                    'del /f /q "%~f0"\r\n'
                )
                with open(bat_path, "w") as f:
                    f.write(bat)

                log(self.cfg, "[UPDATE] Launching silent installer and quitting")
                subprocess.Popen(
                    ["cmd.exe", "/c", bat_path],
                    creationflags=0x08000000 | 0x00000008,
                    close_fds=True,
                )

                from PyQt6.QtCore import QMetaObject, Qt as _Qt
                QMetaObject.invokeMethod(self, "_on_update_ready_quit", _Qt.ConnectionType.QueuedConnection)

            except Exception as e:
                from core.watcher_core import log
                log(self.cfg, f"[UPDATE] Download/install failed: {e}", "ERROR")
                from PyQt6.QtCore import QMetaObject, Qt as _Qt, Q_ARG
                QMetaObject.invokeMethod(self, "_on_update_download_failed",
                    _Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, str(e)))

        threading.Thread(target=_download_and_install, daemon=True, name="AppUpdateDownload").start()

    @pyqtSlot()
    def _on_update_ready_quit(self):
        if hasattr(self, "_update_progress_dlg"):
            self._update_progress_dlg.close()
        self.quit_all()

    @pyqtSlot(str)
    def _on_update_download_failed(self, error: str):
        if hasattr(self, "_update_progress_dlg"):
            self._update_progress_dlg.close()
        self.btn_self_update.setEnabled(True)
        self.btn_self_update.setText("⬆️ Watcher Update")
        self._msgbox_topmost("warn", "App Update Failed", f"Download or install failed:\n{error}")
