"""Duel Picture-in-Picture (PiP) Overlay.

Shows the opponent's playfield as a live MJPEG stream inside a resizable,
draggable overlay window that stays on top of fullscreen VPX.  The window is
automatically opened when both duel players have accepted the in-game prompt
and screen-capture IPs have been exchanged via Firebase.  It closes as soon as
the duel ends or VPX is closed.

When no stream URL is provided (placement mode) the window shows a placeholder
so the user can drag it to the desired position and resize it before a real
duel starts.

Position and size are persisted in ``cfg.DUEL_PIP_X/Y/W/H`` so the window
reopens at the same spot next duel.
"""

from __future__ import annotations

import threading
import time
import urllib.request
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QImage, QPixmap, QResizeEvent, QCloseEvent, QMoveEvent
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QSizePolicy

from ui.overlay_base import _start_topmost_timer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MJPEG_STREAM_TIMEOUT_SECONDS = 10   # HTTP connect/read timeout for the MJPEG stream
MJPEG_READ_CHUNK_SIZE = 8192        # Bytes per read() call from the MJPEG response
JPEG_MARKER_SAFETY_BYTES = 4        # Bytes retained in buffer to avoid split JPEG markers


# ---------------------------------------------------------------------------
# MJPEG frame reader (runs in a background thread)
# ---------------------------------------------------------------------------


class _MjpegReader(QObject):
    """Fetches MJPEG frames from a URL and emits them as QImage signals."""

    frame_ready = pyqtSignal(QImage)
    error = pyqtSignal(str)

    def __init__(self, url: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._url = url
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="PiPMjpegReader")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        BOUNDARY_MARKER = b"--"
        CONTENT_LENGTH_HEADER = b"content-length:"

        try:
            req = urllib.request.Request(
                self._url,
                headers={"User-Agent": "VPXWatcher-PiP/1.0"},
            )
            with urllib.request.urlopen(req, timeout=MJPEG_STREAM_TIMEOUT_SECONDS) as resp:  # noqa: S310
                buf = b""
                while not self._stop_event.is_set():
                    chunk = resp.read(MJPEG_READ_CHUNK_SIZE)
                    if not chunk:
                        break
                    buf += chunk

                    # Parse MJPEG multipart stream.
                    while True:
                        # Find the JPEG SOI marker.
                        soi = buf.find(b"\xff\xd8")
                        if soi == -1:
                            # No JPEG start yet — keep the last few bytes in case
                            # the marker is split across chunks.
                            buf = buf[-JPEG_MARKER_SAFETY_BYTES:]
                            break

                        # Find the JPEG EOI marker after SOI.
                        eoi = buf.find(b"\xff\xd9", soi + 2)
                        if eoi == -1:
                            # Incomplete frame — wait for more data.
                            buf = buf[soi:]
                            break

                        jpeg_data = buf[soi:eoi + 2]
                        buf = buf[eoi + 2:]

                        img = QImage()
                        if img.loadFromData(jpeg_data, "JPEG"):
                            self.frame_ready.emit(img)

        except Exception as exc:
            if not self._stop_event.is_set():
                self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# PiP window
# ---------------------------------------------------------------------------


class DuelPiPOverlay(QWidget):
    """Resizable, draggable PiP overlay that streams the opponent's playfield.

    The window uses ``WindowStaysOnTopHint`` and a periodic Win32
    ``HWND_TOPMOST`` timer so it remains visible over fullscreen VPX.

    Lifecycle
    ---------
    1. Create with ``cfg`` and opponent stream URL (or empty string for
       placement mode).
    2. Call ``open()`` to show the window and start the MJPEG reader.
    3. Call ``close_pip()`` to stop the stream and hide the window.

    The window saves its position and size to ``cfg`` on every move/resize so
    the placement is remembered across duel sessions.
    """

    def __init__(self, cfg, stream_url: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._cfg = cfg
        self._stream_url = stream_url
        self._reader: Optional[_MjpegReader] = None
        self._save_pending = False
        self._placement_mode = not bool(stream_url)

        self.setWindowTitle("⚔️ Duel Live – Opponent's Playfield")
        self.setMinimumSize(160, 90)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        placeholder = (
            "📺 Drag to position  •  Resize at edges\n\nDuel PiP – Placement Mode"
            if self._placement_mode else "Connecting…"
        )
        self._lbl_frame = QLabel(placeholder)
        self._lbl_frame.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._lbl_frame.setStyleSheet(
            "QLabel { background: #000; color: #AAA; font-size: 10pt; }"
        )
        layout.addWidget(self._lbl_frame)

        # Save-position debounce timer (300 ms after last move/resize).
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._save_geometry)

        self._apply_saved_geometry()

    # ── Geometry persistence ──────────────────────────────────────────────

    def _apply_saved_geometry(self) -> None:
        x = int(getattr(self._cfg, "DUEL_PIP_X", -1))
        y = int(getattr(self._cfg, "DUEL_PIP_Y", -1))
        w = int(getattr(self._cfg, "DUEL_PIP_W", 480))
        h = int(getattr(self._cfg, "DUEL_PIP_H", 270))
        self.resize(max(160, w), max(90, h))
        if x >= 0 and y >= 0:
            self.move(x, y)

    def _save_geometry(self) -> None:
        try:
            pos = self.pos()
            sz = self.size()
            self._cfg.DUEL_PIP_X = pos.x()
            self._cfg.DUEL_PIP_Y = pos.y()
            self._cfg.DUEL_PIP_W = sz.width()
            self._cfg.DUEL_PIP_H = sz.height()
            self._cfg.save()
        except Exception:
            pass

    # ── Qt event overrides ────────────────────────────────────────────────

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._save_timer.start()
        # Scale the current pixmap to the new size if one is showing.
        pm = self._lbl_frame.pixmap()
        if pm and not pm.isNull():
            self._lbl_frame.setPixmap(
                pm.scaled(
                    self._lbl_frame.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._save_timer.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.close_pip()
        event.accept()

    # ── Stream control ────────────────────────────────────────────────────

    def open(self) -> None:
        """Show the window and start streaming (or show placement placeholder)."""
        self._apply_saved_geometry()
        self.show()
        self.raise_()
        _start_topmost_timer(self)
        if not self._placement_mode:
            self._start_stream()

    def close_pip(self) -> None:
        """Stop the MJPEG stream and hide the window."""
        self._stop_stream()
        self.hide()

    def _start_stream(self) -> None:
        self._stop_stream()
        self._reader = _MjpegReader(self._stream_url)
        self._reader.frame_ready.connect(self._on_frame)
        self._reader.error.connect(self._on_error)
        self._reader.start()

    def _stop_stream(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None

    def _on_frame(self, img: QImage) -> None:
        pm = QPixmap.fromImage(img)
        scaled = pm.scaled(
            self._lbl_frame.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._lbl_frame.setPixmap(scaled)

    def _on_error(self, msg: str) -> None:
        self._lbl_frame.setText(f"⚠️ Stream error:\n{msg}")
