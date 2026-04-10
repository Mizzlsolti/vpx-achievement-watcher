"""ui/overlay_pickers.py – All 8 overlay position picker classes.

Each class inherits from _BasePositionPicker and only overrides the parts
that are specific to that overlay (size, config keys, label, etc.).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QLabel, QWidget
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QFont, QFontMetrics

from core.theme import get_theme_color
from ui.overlay_base import _BasePositionPicker


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

class ToastPositionPicker(_BasePositionPicker):
    def _picker_label(self) -> str:
        return "Achievement Toast"

    def _config_saved_key(self) -> str:
        return "ach_toast_saved"

    def _config_fallback_saved_key(self) -> str | None:
        return "ach_toast_custom"

    def _config_x_portrait_key(self) -> str:
        return "ach_toast_x_portrait"

    def _config_y_portrait_key(self) -> str:
        return "ach_toast_y_portrait"

    def _config_x_landscape_key(self) -> str:
        return "ach_toast_x_landscape"

    def _config_y_landscape_key(self) -> str:
        return "ach_toast_y_landscape"

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("ach_toast_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("ach_toast_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = 15
        title_pt = max(body_pt + 2, int(round(body_pt * 1.35)))
        f_title = QFont(font_family, title_pt, QFont.Weight.Bold)
        f_body = QFont(font_family, body_pt)
        fm_title = QFontMetrics(f_title)
        fm_body = QFontMetrics(f_body)
        icon_sz = max(28, int(body_pt * 2.0))
        pad = max(12, int(body_pt * 0.8))
        gap = max(10, int(body_pt * 0.5))
        vgap = max(4, int(body_pt * 0.25))
        title_text = "GREAT ACHIEVEMENT UNLOCKED!"
        sub_text = "Table Name"
        text_w = max(fm_title.horizontalAdvance(title_text), fm_body.horizontalAdvance(sub_text))
        text_h = fm_title.height() + vgap + fm_body.height()
        content_h = max(icon_sz, text_h)
        W = max(320, pad + icon_sz + gap + text_w + pad)
        H = max(96, pad + content_h + pad)
        return W, H


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

class MiniInfoPositionPicker(_BasePositionPicker):
    def _picker_label(self) -> str:
        return "Mini Info"

    def _config_saved_key(self) -> str:
        return "notifications_saved"

    def _config_fallback_saved_key(self) -> str | None:
        return None

    def _config_x_portrait_key(self) -> str:
        return "notifications_x_portrait"

    def _config_y_portrait_key(self) -> str:
        return "notifications_y_portrait"

    def _config_x_landscape_key(self) -> str:
        return "notifications_x_landscape"

    def _config_y_landscape_key(self) -> str:
        return "notifications_y_landscape"

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("notifications_portrait", ov.get("portrait_mode", True)))
            self._ccw = bool(ov.get("notifications_rotate_ccw", ov.get("portrait_rotate_ccw", True)))
        except Exception:
            self._portrait = True
            self._ccw = True

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = 20
        pad_w = 28
        pad_h = 22
        max_text_width = 520
        _accent = get_theme_color(self.parent_gui.cfg, "accent")
        candidate_messages = [
            f"<span style='color:{_accent};'>SCORE DUEL COMPLETE!</span><br><span style='color:#DDDDDD;'>Score: 42.069.000</span><br><span style='color:#DDDDDD;'>closing in 5…</span>",
            f"<span style='color:{_accent};'>SCORE DUEL FINISHED!</span><br><span style='color:#DDDDDD;'>Score: 42.069.000</span><br><span style='color:#DDDDDD;'>closing in 5…</span>",
            f"<span style='color:{_accent};'>No VPS-ID set for afm_113b. Progress will NOT be uploaded to cloud.\nGo to 'Available Maps' tab to assign.</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>No NVRAM map for 'afm_113b'. Use AWEditor for custom achievements.</span><br><span style='color:#DDDDDD;'>closing in 5…</span>",
            f"<span style='color:{_accent};'>NVRAM file not found or not readable</span><br><span style='color:#DDDDDD;'>closing in 5…</span>",
            f"<span style='color:{_accent};'>💀 DUEL LOST. You: 42,069,000 vs Opponent: 42,069,000</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>Overlay only available after VPX end</span><br><span style='color:#DDDDDD;'>closing in 5…</span>",
        ]
        max_w, max_h = 200, 60
        for msg_html in candidate_messages:
            html = f"<div style='font-size:{body_pt}pt;font-family:\"{font_family}\";'>{msg_html}</div>"
            tmp = QLabel()
            tmp.setTextFormat(Qt.TextFormat.RichText)
            tmp.setStyleSheet(f"color:{_accent};background:transparent;")
            tmp.setFont(QFont(font_family, body_pt))
            tmp.setWordWrap(True)
            tmp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tmp.setText(html)
            tmp.setFixedWidth(max_text_width)
            tmp.adjustSize()
            text_w = tmp.width()
            text_h = tmp.sizeHint().height()
            max_w = max(max_w, text_w + pad_w)
            max_h = max(max_h, text_h + pad_h)
        return max_w, max_h


# ---------------------------------------------------------------------------
# 6. StatusOverlayPositionPicker
# ---------------------------------------------------------------------------

class StatusOverlayPositionPicker(_BasePositionPicker):
    """Draggable position picker for StatusOverlay, uses ``status_overlay_*`` config keys."""

    def _picker_label(self) -> str:
        return "Status Overlay"

    def _config_saved_key(self) -> str:
        return "status_overlay_saved"

    def _config_fallback_saved_key(self) -> str | None:
        return None

    def _config_x_portrait_key(self) -> str:
        return "status_overlay_x_portrait"

    def _config_y_portrait_key(self) -> str:
        return "status_overlay_y_portrait"

    def _config_x_landscape_key(self) -> str:
        return "status_overlay_x_landscape"

    def _config_y_landscape_key(self) -> str:
        return "status_overlay_y_landscape"

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("status_overlay_portrait", False))
            self._ccw = bool(ov.get("status_overlay_rotate_ccw", False))
        except Exception:
            self._portrait = False
            self._ccw = False

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        badge_font_pt = 13
        pad_w = 22
        pad_h = 14
        max_text_width = 340
        status_text = "Online · Tracking"
        html = (
            f"<span style='font-size:{badge_font_pt}pt;font-family:\"{font_family}\";'>"
            f"<span style='color:#00C853;'>&#9679;</span>"
            f"&nbsp;<span style='color:#EEEEEE;'>{status_text}</span>"
            f"</span>"
        )
        tmp = QLabel()
        tmp.setTextFormat(Qt.TextFormat.RichText)
        tmp.setStyleSheet("color:#EEEEEE;background:transparent;")
        tmp.setFont(QFont(font_family, badge_font_pt))
        tmp.setWordWrap(False)
        tmp.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        tmp.setText(html)
        sh = tmp.sizeHint()
        text_w = max(60, min(sh.width(), max_text_width))
        text_h = max(1, sh.height())
        W = max(120, text_w + pad_w)
        H = max(36, text_h + pad_h)
        return W, H


# ---------------------------------------------------------------------------
# 7. OverlayPositionPicker  (special case – uses use_xy / pos_x / pos_y)
# ---------------------------------------------------------------------------

class OverlayPositionPicker(_BasePositionPicker):
    """Draggable picker for the main overlay.

    Special case: uses ``use_xy`` / ``pos_x`` / ``pos_y`` rather than
    portrait/landscape split config keys.  The ``__init__`` is therefore
    overridden to implement the different position-loading logic.
    """

    def __init__(self, parent):
        # Perform only the common window setup, then handle position ourselves.
        QWidget.__init__(self, None)
        self.parent_gui = parent
        self.setWindowTitle(f"Place {self._picker_label()}")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._drag_off = QPoint(0, 0)
        self._portrait = False
        self._ccw = True
        self._sync_from_cfg()
        self._w, self._h = self._calc_overlay_size()

        ov = self.parent_gui.cfg.OVERLAY or {}
        geo = self._screen_geo()

        if bool(ov.get("use_xy", False)):
            x0 = int(ov.get("pos_x", 100))
            y0 = int(ov.get("pos_y", 100))
        else:
            _pscr = self._primary_screen_geo()
            x0 = int(_pscr.left() + (_pscr.width() - self._w) // 2)
            y0 = int(_pscr.top() + (_pscr.height() - self._h) // 2)

        w_clamp = min(self._w, geo.width())
        h_clamp = min(self._h, geo.height())
        x = max(geo.left(), min(x0, geo.right() - w_clamp))
        y = max(geo.top(), min(y0, geo.bottom() - h_clamp))
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    def _picker_label(self) -> str:
        return "Main Overlay"

    def _config_saved_key(self) -> str:
        return "use_xy"

    def _config_x_portrait_key(self) -> str:
        return "pos_x"

    def _config_y_portrait_key(self) -> str:
        return "pos_y"

    def _config_x_landscape_key(self) -> str:
        return "pos_x"

    def _config_y_landscape_key(self) -> str:
        return "pos_y"

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("portrait_mode", True))
            self._ccw = bool(ov.get("portrait_rotate_ccw", True))
        except Exception:
            self._portrait = True
            self._ccw = True

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        scale_pct = int(ov.get("scale_pct", 100))
        try:
            scr = QApplication.primaryScreen()
            ref = scr.geometry() if scr else self._screen_geo()
        except Exception:
            ref = self._screen_geo()
        if self._portrait:
            base_h = int(ref.height() * 0.55)
            base_w = int(base_h * 9 / 16)
        else:
            base_w = int(ref.width() * 0.40)
            base_h = int(ref.height() * 0.30)
        w = max(120, int(base_w * scale_pct / 100))
        h = max(120, int(base_h * scale_pct / 100))
        return w, h

    def apply_portrait_from_cfg(self):
        self._sync_from_cfg()
        self._w, self._h = self._calc_overlay_size()
        g = self.geometry()
        x, y = g.x(), g.y()
        geo = self._screen_geo()
        w_clamp = min(self._w, geo.width())
        h_clamp = min(self._h, geo.height())
        x = max(geo.left(), min(x, geo.right() - w_clamp))
        y = max(geo.top(), min(y, geo.bottom() - h_clamp))
        self.setGeometry(x, y, self._w, self._h)
        self.update()


# ---------------------------------------------------------------------------
# DuelOverlayPositionPicker
# ---------------------------------------------------------------------------

class DuelOverlayPositionPicker(_BasePositionPicker):
    """Draggable position picker for DuelInfoOverlay, uses ``duel_overlay_*`` config keys."""

    def _picker_label(self) -> str:
        return "Duel Overlay"

    def _config_saved_key(self) -> str:
        return "duel_overlay_saved"

    def _config_fallback_saved_key(self) -> str | None:
        return None

    def _config_x_portrait_key(self) -> str:
        return "duel_overlay_x_portrait"

    def _config_y_portrait_key(self) -> str:
        return "duel_overlay_y_portrait"

    def _config_x_landscape_key(self) -> str:
        return "duel_overlay_x_landscape"

    def _config_y_landscape_key(self) -> str:
        return "duel_overlay_y_landscape"

    def _sync_from_cfg(self):
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            self._portrait = bool(ov.get("duel_overlay_portrait", True))
            self._ccw = bool(ov.get("duel_overlay_rotate_ccw", True))
        except Exception:
            self._portrait = True
            self._ccw = True

    def _calc_overlay_size(self) -> tuple[int, int]:
        ov = self.parent_gui.cfg.OVERLAY or {}
        font_family = str(ov.get("font_family", "Segoe UI"))
        body_pt = 20
        pad_w = 28
        pad_h = 22
        max_text_width = 520
        _accent = get_theme_color(self.parent_gui.cfg, "accent")
        candidate_messages = [
            f"<span style='color:{_accent};'>⚔️ Duel active against xPinballWizard!<br>🎰 Medieval Madness<br>⚠️ One game only — restarting in-game will abort the duel!<br>🔙 After the duel, close VPX or return to Popper.</span><br><span style='color:#DDDDDD;'>closing in 20…</span>",
            f"<span style='color:{_accent};'>⚔️ Duel from xPinballWizard<br>🎰 Medieval Madness<br>⚠️ One game only — restarting in-game will abort the duel!<br>🔙 After the duel, close VPX or return to Popper.<br>[✅ Accept] / Decline</span>",
            f"<span style='color:{_accent};'>🏆 DUEL WON! You: 42,069,000 vs Opponent: 38,500,000</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>💀 DUEL LOST. You: 38,500,000 vs Opponent: 42,069,000</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>🤝 TIE! You: 42,069,000 vs Opponent: 42,069,000</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>⏰ Duel expired — no response received.</span><br><span style='color:#DDDDDD;'>closing in 6…</span>",
            f"<span style='color:{_accent};'>⏳ Score submitted! Waiting for opponent's score...</span><br><span style='color:#DDDDDD;'>closing in 10…</span>",
            f"<span style='color:{_accent};'>⚠️ Duel aborted: Session too short.</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>⚠️ Duel aborted: VPX restarted during active duel. Only one attempt allowed!</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>⚠️ Duel aborted: Multiple games detected in single VPX session. Only one game per duel allowed!</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>✅ 'xPinballWizard' accepted your duel on Medieval Madness!</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>❌ 'xPinballWizard' declined your duel on Medieval Madness.</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>⏰ Your duel invitation on Medieval Madness expired (not accepted).</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
            f"<span style='color:{_accent};'>🚫 Your duel on Medieval Madness was cancelled.</span><br><span style='color:#DDDDDD;'>closing in 8…</span>",
        ]
        max_w, max_h = 200, 60
        for msg_html in candidate_messages:
            html = f"<div style='font-size:{body_pt}pt;font-family:\"{font_family}\";'>{msg_html}</div>"
            tmp = QLabel()
            tmp.setTextFormat(Qt.TextFormat.RichText)
            tmp.setStyleSheet(f"color:{_accent};background:transparent;")
            tmp.setFont(QFont(font_family, body_pt))
            tmp.setWordWrap(True)
            tmp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tmp.setText(html)
            tmp.setFixedWidth(max_text_width)
            tmp.adjustSize()
            text_w = tmp.width()
            text_h = tmp.sizeHint().height()
            max_w = max(max_w, text_w + pad_w)
            max_h = max(max_h, text_h + pad_h)
        return max_w, max_h


# ---------------------------------------------------------------------------
