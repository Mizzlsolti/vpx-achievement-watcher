"""ui/overlay_pip.py – Duel Picture-in-Picture overlay.

Shows the opponent's MJPEG live stream as a resizable, always-on-top overlay
window.  The user can drag it to any monitor and resize it at the edges; the
video scales dynamically.  Position and size are auto-saved to config with a
300 ms debounce so rapid drags don't hammer the config file.
"""

from __future__ import annotations

import threading
from typing import Optional

from PyQt6.QtCore import (
    QObject,
    QPoint,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from ui.overlay_base import _force_topmost, _start_topmost_timer

# MJPEG boundary used by the screen capture server
_MJPEG_BOUNDARY = b"--vpxframe"


# ---------------------------------------------------------------------------
# MJPEG reader (runs in a background thread)
# ---------------------------------------------------------------------------

class _MjpegReader(QObject):
    """Reads MJPEG frames from *url* and emits ``frame_ready`` for each frame."""

    frame_ready = pyqtSignal(QImage)

    def __init__(self, url: str, stop_event: threading.Event):
        super().__init__()
        self._url = url
        self._stop = stop_event

    @staticmethod
    def _validate_stream_url(url: str) -> bool:
        """Validate that the URL is a safe http/https URL pointing to a private IP."""
        try:
            from urllib.parse import urlparse
            import ipaddress
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            host = parsed.hostname or ""
            # Reject empty or obviously unsafe hosts
            if not host or host.lower() in ("localhost",):
                return True  # localhost is fine
            try:
                addr = ipaddress.ip_address(host)
                # Only allow private/loopback/link-local ranges
                if not (addr.is_private or addr.is_loopback or addr.is_link_local):
                    return False
            except ValueError:
                # hostname (not IP) — only allow localhost
                if host.lower() != "localhost":
                    return False
            return True
        except Exception:
            return False

    def run(self):  # called from background thread
        try:
            import urllib.request
            from urllib.parse import urlparse

            if not self._validate_stream_url(self._url):
                return

            req = urllib.request.Request(self._url)
            resp = urllib.request.urlopen(req, timeout=10)  # noqa: S310

            buf = b""
            header_done = False
            content_length = 0

            while not self._stop.is_set():
                chunk = resp.read(4096)
                if not chunk:
                    break
                buf += chunk

                while True:
                    if not header_done:
                        # Look for the end of the MJPEG part header
                        header_end = buf.find(b"\r\n\r\n")
                        if header_end == -1:
                            break
                        header = buf[:header_end].decode("latin-1", errors="replace")
                        buf = buf[header_end + 4:]
                        header_done = True
                        content_length = 0
                        for line in header.splitlines():
                            if line.lower().startswith("content-length:"):
                                try:
                                    content_length = int(line.split(":", 1)[1].strip())
                                except ValueError:
                                    pass

                    if content_length > 0:
                        if len(buf) < content_length:
                            break
                        jpeg = buf[:content_length]
                        buf = buf[content_length:]
                        # Skip trailing \r\n after frame body
                        if buf.startswith(b"\r\n"):
                            buf = buf[2:]
                        header_done = False

                        img = QImage()
                        img.loadFromData(jpeg, "JPEG")
                        if not img.isNull():
                            self.frame_ready.emit(img)
                    else:
                        # No content-length — scan for next boundary
                        boundary_pos = buf.find(_MJPEG_BOUNDARY)
                        if boundary_pos == -1:
                            break
                        buf = buf[boundary_pos:]
                        header_done = False
                        content_length = 0

        except Exception:
            pass


# ---------------------------------------------------------------------------
# DuelPiPOverlay
# ---------------------------------------------------------------------------

class DuelPiPOverlay(QWidget):
    """Always-on-top, resizable PiP overlay for the opponent's live stream.

    In *placement mode* (no URL) it shows a placeholder so the user can
    drag and resize it to the desired position before a duel starts.
    In *stream mode* it shows the live MJPEG video.
    """

    def __init__(self, parent_gui, stream_url: str = ""):
        super().__init__(None)
        self._parent_gui = parent_gui
        self._stream_url = stream_url
        self._current_frame: Optional[QPixmap] = None
        self._stop_event = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._reader: Optional[_MjpegReader] = None
        self._video_aspect: Optional[float] = None  # kept for backwards compat; unused
        self._remote_orientation: Optional[str] = None  # diagnostics only; see set_remote_orientation

        # Debounce timer for saving geometry to config
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._save_geometry_to_cfg)

        # Resize state
        self._resize_margin = 8
        self._resize_dir: Optional[str] = None
        self._resize_origin = QPoint()
        self._resize_start_geo = QRect()

        # Drag state
        self._drag_offset = QPoint()
        self._dragging = False

        self._setup_window()
        self._restore_geometry()

        if stream_url:
            self._start_stream()

        _start_topmost_timer(self, interval_ms=3000)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMinimumSize(160, 90)

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def _restore_geometry(self):
        ov = self._parent_gui.cfg.OVERLAY or {}
        portrait = bool(ov.get("duel_pip_portrait", True))
        x = int(ov.get("duel_pip_x", -1))
        y = int(ov.get("duel_pip_y", -1))
        # Default window shape matches the expected content orientation so the
        # placeholder and the stream both look correct out of the box.
        default_w = 270 if portrait else 480
        default_h = 480 if portrait else 270
        w = int(ov.get("duel_pip_w", default_w))
        h = int(ov.get("duel_pip_h", default_h))
        w = max(160, w)
        h = max(90, h)

        if x == -1 or y == -1:
            # Centre on primary screen
            primary = QApplication.primaryScreen()
            if primary:
                geo = primary.availableGeometry()
                x = geo.left() + (geo.width() - w) // 2
                y = geo.top() + (geo.height() - h) // 2
            else:
                x, y = 100, 100

        self.setGeometry(x, y, w, h)

    def _save_geometry_to_cfg(self):
        try:
            g = self.geometry()
            self._parent_gui.cfg.OVERLAY["duel_pip_x"] = g.x()
            self._parent_gui.cfg.OVERLAY["duel_pip_y"] = g.y()
            self._parent_gui.cfg.OVERLAY["duel_pip_w"] = g.width()
            self._parent_gui.cfg.OVERLAY["duel_pip_h"] = g.height()
            self._parent_gui.cfg.save()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Stream
    # ------------------------------------------------------------------

    def _start_stream(self):
        self._stop_event.clear()
        reader = _MjpegReader(self._stream_url, self._stop_event)
        reader.frame_ready.connect(self._on_frame)
        self._reader = reader

        t = threading.Thread(target=reader.run, daemon=True, name="PiPMjpegReader")
        self._reader_thread = t
        t.start()

    def _on_frame(self, img: QImage):
        # The window shape is driven by the local user's orientation (set via
        # _restore_geometry / user drag), NOT by the incoming frame.  The frame
        # is simply drawn inside the window preserving its native aspect ratio,
        # with letterbox / pillarbox bars absorbing any mismatch.
        self._current_frame = QPixmap.fromImage(img)
        self.update()

    def _local_portrait(self) -> bool:
        """Return True when the local user's setup is portrait (Cabinet)."""
        ov = self._parent_gui.cfg.OVERLAY or {}
        return bool(ov.get("duel_pip_portrait", True))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self):
        """Show the overlay and (re-)start the stream if a URL is set."""
        self.show()
        self.raise_()
        _force_topmost(self)
        if self._stream_url and (
            self._reader_thread is None or not self._reader_thread.is_alive()
        ):
            self._start_stream()

    def set_remote_orientation(self, orientation: str) -> None:
        """Record the opponent's advertised orientation (diagnostics only).

        The opponent's orientation does NOT affect the local window shape or
        frame rotation — the sender transmits frames in their native orientation
        and the receiver draws them with ``KeepAspectRatio``, producing
        letterbox/pillarbox bars when the ratios differ.  This setter is kept
        so future diagnostics / logging can access the value.
        """
        if orientation not in ("portrait", "landscape"):
            return
        self._remote_orientation = orientation

    def close_pip(self):
        """Stop the stream and hide the overlay."""
        self._stop_event.set()
        self.hide()
        self._current_frame = None

    # ------------------------------------------------------------------
    # Qt event handlers
    # ------------------------------------------------------------------

    def paintEvent(self, _evt):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))

        # Window shape is driven by the LOCAL orientation; the stream is drawn
        # at its native aspect ratio with letterbox/pillarbox bars absorbing any
        # mismatch between local window and remote stream.
        local_portrait = self._local_portrait()
        ov = self._parent_gui.cfg.OVERLAY or {}
        rotate_ccw = bool(ov.get("duel_pip_rotate_ccw", True))

        if self._current_frame is not None:
            # Draw the incoming frame at its native aspect ratio, centered.
            # No rotation: the sender transmits in its own orientation; the
            # receiver only scales + letterboxes/pillarboxes.
            scaled = self._current_frame.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        else:
            # Placeholder — orientation of the placeholder text follows the
            # local window shape so the "Drag to position" hint reads correctly
            # for both Cabinet (portrait) and Desktop (landscape) users.
            pen = QPen(QColor(80, 80, 80))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawRect(1, 1, self.width() - 2, self.height() - 2)
            p.setPen(QColor(160, 160, 160))
            p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            if local_portrait:
                # Rotate painter for placeholder text
                angle = -90 if rotate_ccw else 90
                p.translate(self.width() / 2, self.height() / 2)
                p.rotate(angle)
                text_rect = p.boundingRect(
                    0, 0, 0, 0,
                    int(Qt.AlignmentFlag.AlignCenter),
                    "📺 Drag to position – Resize at edges",
                )
                p.drawText(
                    -text_rect.width() // 2, -text_rect.height() // 2,
                    text_rect.width(), text_rect.height(),
                    int(Qt.AlignmentFlag.AlignCenter),
                    "📺 Drag to position – Resize at edges",
                )
            else:
                p.drawText(
                    self.rect(),
                    int(Qt.AlignmentFlag.AlignCenter),
                    "📺 Drag to position – Resize at edges",
                )
        p.end()

    def mousePressEvent(self, evt):  # noqa: N802
        if evt.button() == Qt.MouseButton.LeftButton:
            pos = evt.position().toPoint()
            direction = self._resize_direction(pos)
            if direction:
                self._resize_dir = direction
                self._resize_origin = evt.globalPosition().toPoint()
                self._resize_start_geo = self.geometry()
                self._dragging = False
            else:
                self._resize_dir = None
                self._drag_offset = evt.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self._dragging = True

    def mouseMoveEvent(self, evt):  # noqa: N802
        pos = evt.position().toPoint()
        if evt.buttons() & Qt.MouseButton.LeftButton:
            if self._resize_dir:
                self._do_resize(evt.globalPosition().toPoint())
            elif self._dragging:
                target = evt.globalPosition().toPoint() - self._drag_offset
                self.move(target)
                self._save_timer.start()
        else:
            # Update cursor shape for resize handles
            direction = self._resize_direction(pos)
            if direction in ("left", "right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif direction in ("top", "bottom"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif direction in ("top-left", "bottom-right"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif direction in ("top-right", "bottom-left"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, evt):  # noqa: N802
        if evt.button() == Qt.MouseButton.LeftButton:
            self._resize_dir = None
            self._dragging = False
            # No aspect snap: the window shape follows the local user's
            # orientation, not the stream's aspect ratio.  Any mismatch is
            # absorbed by letterbox/pillarbox bars in paintEvent.
            self._save_timer.start()

    def resizeEvent(self, evt):  # noqa: N802
        self._save_timer.start()
        super().resizeEvent(evt)

    def moveEvent(self, evt):  # noqa: N802
        self._save_timer.start()
        super().moveEvent(evt)

    # ------------------------------------------------------------------
    # Resize helpers
    # ------------------------------------------------------------------

    def _resize_direction(self, pos: QPoint) -> Optional[str]:
        """Return the resize edge/corner for mouse position *pos*, or None."""
        m = self._resize_margin
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        left = x < m
        right = x > w - m
        top = y < m
        bottom = y > h - m

        if top and left:
            return "top-left"
        if top and right:
            return "top-right"
        if bottom and left:
            return "bottom-left"
        if bottom and right:
            return "bottom-right"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None

    def _do_resize(self, global_pos: QPoint):
        delta = global_pos - self._resize_origin
        dx, dy = delta.x(), delta.y()
        geo = QRect(self._resize_start_geo)
        d = self._resize_dir

        if "right" in d:
            geo.setRight(geo.right() + dx)
        if "bottom" in d:
            geo.setBottom(geo.bottom() + dy)
        if "left" in d:
            geo.setLeft(geo.left() + dx)
        if "top" in d:
            geo.setTop(geo.top() + dy)

        min_w, min_h = 160, 90
        if geo.width() < min_w:
            if "left" in d:
                geo.setLeft(geo.right() - min_w)
            else:
                geo.setRight(geo.left() + min_w)
        if geo.height() < min_h:
            if "top" in d:
                geo.setTop(geo.bottom() - min_h)
            else:
                geo.setBottom(geo.top() + min_h)

        self.setGeometry(geo)
