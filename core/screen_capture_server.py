"""core/screen_capture_server.py – MJPEG screen-capture server for VPX Watcher.

Provides a ThreadingHTTPServer that streams desktop monitors as MJPEG over HTTP
and broadcasts its address via UDP so local clients can auto-discover it.

Endpoints
---------
GET /api/monitors   → JSON list of monitor descriptors
GET /stream/{id}    → MJPEG stream for monitor *id* (1-based)

Dependencies: mss, Pillow.
If either is missing the ``available`` property returns False and all other
methods are no-ops so the rest of the application keeps running normally.
"""

from __future__ import annotations

import io
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

# MJPEG boundary — must match the constant in ui/overlay_pip.py
_MJPEG_BOUNDARY = b"--vpxframe"

# ---------------------------------------------------------------------------
# Optional dependency guard
# ---------------------------------------------------------------------------

try:
    import mss
    import mss.tools  # noqa: F401 — ensure tools module loads OK
    from PIL import Image
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

# ---------------------------------------------------------------------------
# Adaptive-quality look-up table
# cpu_pct_threshold → (fps, jpeg_quality)
# Entries are checked in ascending order; first match wins.
# ---------------------------------------------------------------------------

_ADAPTIVE_QUALITY_TABLE = [
    (70,  30, 95),
    (80,  30, 80),
    (90,  20, 70),
    (101, 10, 50),
]


def _get_lan_ip() -> str:
    """Return the machine's LAN IP address (best-effort, cached by caller)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _set_low_priority():
    """Lower the current thread's scheduling priority (best-effort)."""
    try:
        import ctypes
        THREAD_PRIORITY_BELOW_NORMAL = -1
        ctypes.windll.kernel32.SetThreadPriority(
            ctypes.windll.kernel32.GetCurrentThread(),
            THREAD_PRIORITY_BELOW_NORMAL,
        )
    except Exception:
        try:
            os.nice(5)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class _MjpegHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for /api/monitors and /stream/{id}."""

    # Silence default request logging to avoid spamming the watcher log.
    def log_message(self, fmt, *args):  # noqa: ANN001
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/api/monitors":
            self._serve_monitors()
        elif self.path.startswith("/stream/"):
            try:
                monitor_id = int(self.path.split("/stream/")[1].split("?")[0])
            except (ValueError, IndexError):
                self.send_error(400, "Bad monitor id")
                return
            self._serve_stream(monitor_id)
        else:
            self.send_error(404, "Not found")

    # ------------------------------------------------------------------
    # /api/monitors
    # ------------------------------------------------------------------

    def _serve_monitors(self):
        server: ScreenCaptureServer = self.server.scs  # type: ignore[attr-defined]
        try:
            with mss.mss() as sct:
                monitors = [
                    {
                        "id":  i + 1,
                        "x":   m["left"],
                        "y":   m["top"],
                        "w":   m["width"],
                        "h":   m["height"],
                    }
                    for i, m in enumerate(sct.monitors[1:])  # skip "all" monitor at index 0
                ]
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = json.dumps(monitors).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------
    # /stream/{id}
    # ------------------------------------------------------------------

    def _serve_stream(self, monitor_id: int):
        server: ScreenCaptureServer = self.server.scs  # type: ignore[attr-defined]
        server._client_connected()
        try:
            self.send_response(200)
            self.send_header(
                "Content-Type",
                f"multipart/x-mixed-replace; boundary={_MJPEG_BOUNDARY.decode()}",
            )
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            _set_low_priority()

            with mss.mss() as sct:
                mons = sct.monitors
                # mons[0] is the virtual "all screens" monitor; 1-based ids map to mons[1:]
                if monitor_id < 1 or monitor_id >= len(mons):
                    return

                mon = mons[monitor_id]

                while True:
                    fps, quality = server._current_fps_quality()
                    interval = 1.0 / max(1, fps)

                    t0 = time.monotonic()

                    raw = sct.grab(mon)
                    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=quality, optimize=False)
                    frame = buf.getvalue()

                    header = (
                        _MJPEG_BOUNDARY + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                        b"\r\n"
                    )
                    try:
                        self.wfile.write(header + frame + b"\r\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        break

                    elapsed = time.monotonic() - t0
                    sleep = interval - elapsed
                    if sleep > 0:
                        time.sleep(sleep)
        finally:
            server._client_disconnected()


# ---------------------------------------------------------------------------
# Main server class
# ---------------------------------------------------------------------------

class ScreenCaptureServer:
    """Manages the MJPEG HTTP server and UDP discovery broadcast."""

    def __init__(self, port: int = 9876, fps_cfg: str = "auto", quality_cfg: str = "auto"):
        self._port = port
        self._fps_cfg = fps_cfg
        self._quality_cfg = quality_cfg

        self._http_thread: Optional[threading.Thread] = None
        self._udp_thread: Optional[threading.Thread] = None
        self._server: Optional[ThreadingHTTPServer] = None
        self._stop_event = threading.Event()

        self._client_count = 0
        self._client_lock = threading.Lock()

        # CPU cache (updated every ~1-2 s by _cpu_monitor_thread)
        self._cached_cpu: float = 0.0
        self._cpu_thread: Optional[threading.Thread] = None

        self._local_ip_cache: Optional[str] = None

    # ------------------------------------------------------------------
    # Public setters so UI changes apply live to running streams
    # ------------------------------------------------------------------

    def set_fps_cfg(self, value: str):
        self._fps_cfg = str(value)

    def set_quality_cfg(self, value: str):
        self._quality_cfg = str(value)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return _DEPS_OK

    @property
    def is_running(self) -> bool:
        return (
            self._http_thread is not None
            and self._http_thread.is_alive()
        )

    @property
    def local_ip(self) -> str:
        if self._local_ip_cache is None:
            self._local_ip_cache = _get_lan_ip()
        return self._local_ip_cache

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the HTTP server and UDP discovery. Returns True on success."""
        if not _DEPS_OK:
            return False
        if self.is_running:
            return True

        self._stop_event.clear()
        try:
            server = ThreadingHTTPServer(("", self._port), _MjpegHandler)
            server.scs = self  # type: ignore[attr-defined]
            server.daemon_threads = True
            self._server = server
        except OSError:
            return False

        self._http_thread = threading.Thread(
            target=self._http_worker,
            daemon=True,
            name="ScreenCaptureHTTP",
        )
        self._http_thread.start()

        self._udp_thread = threading.Thread(
            target=self._udp_worker,
            daemon=True,
            name="ScreenCaptureUDP",
        )
        self._udp_thread.start()

        self._cpu_thread = threading.Thread(
            target=self._cpu_monitor_worker,
            daemon=True,
            name="ScreenCaptureCPU",
        )
        self._cpu_thread.start()

        return True

    def stop(self):
        """Stop the HTTP server and all background threads."""
        self._stop_event.set()
        try:
            if self._server is not None:
                self._server.shutdown()
                self._server = None
        except Exception:
            pass
        self._http_thread = None
        self._udp_thread = None
        self._cpu_thread = None

    # ------------------------------------------------------------------
    # Client tracking (zero CPU when no client connected)
    # ------------------------------------------------------------------

    def _client_connected(self):
        with self._client_lock:
            self._client_count += 1

    def _client_disconnected(self):
        with self._client_lock:
            self._client_count = max(0, self._client_count - 1)

    # ------------------------------------------------------------------
    # Adaptive quality
    # ------------------------------------------------------------------

    def _current_fps_quality(self) -> tuple[int, int]:
        """Return (fps, jpeg_quality) based on current config and CPU load."""
        fps_raw = str(self._fps_cfg).strip().lower()
        qual_raw = str(self._quality_cfg).strip().lower()

        if fps_raw == "auto" or qual_raw == "auto":
            cpu = self._cached_cpu
            for threshold, fps_a, qual_a in _ADAPTIVE_QUALITY_TABLE:
                if cpu < threshold:
                    fps_final = fps_a if fps_raw == "auto" else int(fps_raw)
                    qual_final = qual_a if qual_raw == "auto" else int(qual_raw)
                    return fps_final, qual_final
            fps_final = 10 if fps_raw == "auto" else int(fps_raw)
            qual_final = 50 if qual_raw == "auto" else int(qual_raw)
            return fps_final, qual_final

        try:
            return int(fps_raw), int(qual_raw)
        except ValueError:
            return 30, 80

    # ------------------------------------------------------------------
    # Background workers
    # ------------------------------------------------------------------

    def _http_worker(self):
        _set_low_priority()
        try:
            self._server.serve_forever()
        except Exception:
            pass

    def _udp_worker(self):
        _set_low_priority()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            msg = f"VPX-WATCHER:{self.local_ip}:{self._port}".encode()
            while not self._stop_event.is_set():
                try:
                    sock.sendto(msg, ("<broadcast>", 9875))
                except Exception:
                    pass
                self._stop_event.wait(2.0)
            sock.close()
        except Exception:
            pass

    def _cpu_monitor_worker(self):
        """Periodically sample CPU usage and cache the result."""
        _set_low_priority()
        try:
            import psutil
            # Use interval=None so the call returns immediately (uses the
            # value calculated since the last call, or 0.0 on first call).
            # We sleep ~1.5 s between samples to keep the overhead low.
            psutil.cpu_percent(interval=None)  # prime the counter
            while not self._stop_event.is_set():
                self._stop_event.wait(1.5)  # sleep 1.5 s between samples
                if self._stop_event.is_set():
                    break
                self._cached_cpu = psutil.cpu_percent(interval=None)
        except ImportError:
            # psutil not available — leave CPU at 0 (best-quality always)
            pass
        except Exception:
            pass
