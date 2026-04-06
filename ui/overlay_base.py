"""ui/overlay_base.py – Theme helpers, mixins, and the shared _BasePositionPicker.

All position picker classes inherit from _BasePositionPicker and only need to
implement a small set of abstract hooks.  The heavy lifting (window setup,
dragging, clamping, portrait handling) lives here once.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen

from core.theme import get_theme_color, get_theme, DEFAULT_THEME


# ---------------------------------------------------------------------------
# Module-level theme helpers
# ---------------------------------------------------------------------------

def _theme_bg_qcolor(cfg, alpha: int = 245) -> QColor:
    """Return the active theme bg colour as a QColor with *alpha* (0–255)."""
    h = get_theme_color(cfg, "bg").lstrip("#")
    return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _theme_bg_rgba_css(cfg, alpha: int = 245) -> str:
    """Return 'rgba(r,g,b,alpha)' for use in Qt stylesheets."""
    h = get_theme_color(cfg, "bg").lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _get_page_accents_list(cfg) -> list:
    """Return the page accent hex strings for the active theme.

    If the theme defines ``page_accents``, those are used directly.
    Otherwise a four-entry fallback is derived from the theme's
    primary/accent/border colours so the overlay always respects the
    current theme rather than falling back to hardcoded Neon-Blue values.
    """
    theme_id = (cfg.OVERLAY or {}).get("theme", DEFAULT_THEME)
    theme = get_theme(theme_id)
    accents = theme.get("page_accents", [])
    if accents:
        return accents
    # Dynamic fallback: build four entries from the theme's own colours.
    default = get_theme(DEFAULT_THEME)
    primary = theme.get("primary", default["primary"])
    accent  = theme.get("accent",  default["accent"])
    border  = theme.get("border",  primary)
    return [primary, accent, border, accent]


def _get_page_accent(cfg, idx: int) -> QColor:
    """Return the page accent QColor for page *idx* from the active theme."""
    accents = _get_page_accents_list(cfg)
    h = accents[idx % len(accents)].lstrip("#")
    return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _force_topmost(widget: QWidget):
    """Force a widget to the topmost z-order using Win32 API.
    Works even against fullscreen DirectX/OpenGL applications.
    No-ops silently when the widget is not visible or win32 is unavailable."""
    if not widget.isVisible():
        return
    try:
        import win32gui, win32con
        hwnd = int(widget.winId())
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE
        )
    except Exception:
        pass


def _start_topmost_timer(widget: QWidget, interval_ms: int = 3000):
    """Start a periodic timer that re-applies HWND_TOPMOST to keep the widget above fullscreen apps.
    The timer is stored as widget._topmost_timer to prevent garbage collection."""
    timer = QTimer(widget)
    timer.setInterval(interval_ms)
    timer.timeout.connect(lambda: _force_topmost(widget))
    timer.start()
    widget._topmost_timer = timer


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------

class _OverlayFxMixin:
    """Mixin that provides live fx_* config read helpers for all overlay classes.

    Requires the host class to have a ``parent_gui`` attribute that exposes
    ``parent_gui.cfg.OVERLAY`` (a dict-like config object).
    """

    def _is_fx_enabled(self, fx_key: str) -> bool:
        """Live-read whether a specific effect is enabled, respecting low_performance_mode."""
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            if bool(ov.get("low_performance_mode", False)):
                return False
            return bool(ov.get(fx_key, True))
        except Exception:
            return False  # fail-safe: disable effects on config error

    def _get_fx_intensity(self, fx_key: str) -> float:
        """Live-read the intensity (0.0–1.0) for a specific effect."""
        try:
            ov = self.parent_gui.cfg.OVERLAY or {}
            return max(0.0, min(1.0, float(ov.get(fx_key + "_intensity", 80)) / 100.0))
        except Exception:
            return 0.8


# ---------------------------------------------------------------------------
# Base position picker
# ---------------------------------------------------------------------------

class _BasePositionPicker(QWidget):
    """Gemeinsame Basis für alle Overlay-Position-Picker.

    Subklassen müssen implementieren:
    - _picker_label() -> str
    - _config_saved_key() -> str
    - _config_fallback_saved_key() -> str | None   (default: None)
    - _config_x_portrait_key() -> str
    - _config_y_portrait_key() -> str
    - _config_x_landscape_key() -> str
    - _config_y_landscape_key() -> str
    - _calc_overlay_size() -> tuple[int, int]
    - _sync_from_cfg()
    """

    def __init__(self, parent, *, width_hint=None, height_hint=None):
        super().__init__(None)
        self.parent_gui = parent
        self._width_hint = width_hint
        self._height_hint = height_hint
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
        self._base_w, self._base_h = self._calc_overlay_size()
        if self._width_hint is not None:
            self._base_w = self._width_hint
        if self._height_hint is not None:
            self._base_h = self._height_hint

        if self._portrait:
            self._w, self._h = self._base_h, self._base_w
        else:
            self._w, self._h = self._base_w, self._base_h

        ov = self.parent_gui.cfg.OVERLAY or {}
        primary_geo = self._primary_screen_geo()
        virt_geo = self._screen_geo()

        saved_key = self._config_saved_key()
        fallback_key = self._config_fallback_saved_key()
        is_saved = bool(ov.get(saved_key, False)) if saved_key else False
        if not is_saved and fallback_key:
            is_saved = bool(ov.get(fallback_key, False))

        if is_saved:
            if self._portrait:
                x0 = int(ov.get(self._config_x_portrait_key(), 100))
                y0 = int(ov.get(self._config_y_portrait_key(), 100))
            else:
                x0 = int(ov.get(self._config_x_landscape_key(), 100))
                y0 = int(ov.get(self._config_y_landscape_key(), 100))
        else:
            x0 = int(primary_geo.left() + (primary_geo.width() - self._w) // 2)
            y0 = int(primary_geo.top() + (primary_geo.height() - self._h) // 2)

        w_clamp = min(self._w, virt_geo.width())
        h_clamp = min(self._h, virt_geo.height())
        x = max(virt_geo.left(), min(x0, virt_geo.right() - w_clamp))
        y = max(virt_geo.top(), min(y0, virt_geo.bottom() - h_clamp))
        self.setGeometry(x, y, self._w, self._h)
        self.show()
        self.raise_()

    # ------------------------------------------------------------------
    # Screen geometry helpers
    # ------------------------------------------------------------------

    def _primary_screen_geo(self) -> QRect:
        """Primary screen geometry for default centering."""
        try:
            scr = QApplication.primaryScreen()
            if scr:
                return scr.availableGeometry()
        except Exception:
            pass
        return QRect(0, 0, 1280, 720)

    def _screen_geo(self) -> QRect:
        """Virtual desktop geometry (union of all screens) for clamping/dragging."""
        screens = QApplication.screens() or []
        if screens:
            vgeo = screens[0].availableGeometry()
            for s in screens[1:]:
                vgeo = vgeo.united(s.availableGeometry())
            return vgeo
        return QRect(0, 0, 1280, 720)

    # ------------------------------------------------------------------
    # Abstract hooks – subclasses must implement these
    # ------------------------------------------------------------------

    def _picker_label(self) -> str:
        raise NotImplementedError

    def _config_saved_key(self) -> str:
        raise NotImplementedError

    def _config_fallback_saved_key(self) -> str | None:
        """Override for legacy config fallback key. Default: None."""
        return None

    def _config_x_portrait_key(self) -> str:
        raise NotImplementedError

    def _config_y_portrait_key(self) -> str:
        raise NotImplementedError

    def _config_x_landscape_key(self) -> str:
        raise NotImplementedError

    def _config_y_landscape_key(self) -> str:
        raise NotImplementedError

    def _calc_overlay_size(self) -> tuple[int, int]:
        raise NotImplementedError

    def _sync_from_cfg(self):
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared picker font size (override in subclass to change)
    # ------------------------------------------------------------------

    def _picker_font_size(self) -> int:
        return 10

    # ------------------------------------------------------------------
    # Portrait update
    # ------------------------------------------------------------------

    def apply_portrait_from_cfg(self):
        old_portrait = bool(self._portrait)
        self._sync_from_cfg()
        if bool(self._portrait) != old_portrait:
            self._base_w, self._base_h = self._calc_overlay_size()
            if self._width_hint is not None:
                self._base_w = self._width_hint
            if self._height_hint is not None:
                self._base_h = self._height_hint
            if self._portrait:
                self._w, self._h = self._base_h, self._base_w
            else:
                self._w, self._h = self._base_w, self._base_h
            g = self.geometry()
            x, y = g.x(), g.y()
            geo = self._screen_geo()
            w_clamp = min(self._w, geo.width())
            h_clamp = min(self._h, geo.height())
            x = max(geo.left(), min(x, geo.right() - w_clamp))
            y = max(geo.top(), min(y, geo.bottom() - h_clamp))
            self.setGeometry(x, y, self._w, self._h)
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _evt):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(0, 0, self._w, self._h, _theme_bg_qcolor(self.parent_gui.cfg, 245))
        pen = QPen(QColor(get_theme_color(self.parent_gui.cfg, "primary")))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(1, 1, self._w - 2, self._h - 2, 18, 18)
        p.setPen(QColor(get_theme_color(self.parent_gui.cfg, "accent")))
        p.setFont(QFont("Segoe UI", self._picker_font_size(), QFont.Weight.Bold))
        msg = f"{self._picker_label()}\nDrag to position. Click the button again to save"
        if self._portrait:
            p.save()
            angle = -90 if self._ccw else 90
            center = self.rect().center()
            p.translate(center)
            p.rotate(angle)
            p.translate(-center)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
            p.restore()
        else:
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), msg)
        p.end()

    # ------------------------------------------------------------------
    # Mouse drag
    # ------------------------------------------------------------------

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self._drag_off = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evt):
        if evt.buttons() & Qt.MouseButton.LeftButton:
            target = evt.globalPosition().toPoint() - self._drag_off
            geo = self._screen_geo()
            w_clamp = min(self._w, geo.width())
            h_clamp = min(self._h, geo.height())
            x = max(geo.left(), min(target.x(), geo.right() - w_clamp))
            y = max(geo.top(), min(target.y(), geo.bottom() - h_clamp))
            self.move(x, y)

    def current_top_left(self) -> tuple[int, int]:
        g = self.geometry()
        return int(g.x()), int(g.y())
