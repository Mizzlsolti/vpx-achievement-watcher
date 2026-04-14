"""MJPEG HTTP Screen-Capture Server + UDP Auto-Discovery broadcaster.

Desktop side of the "Live View" feature.

HTTP server  — port configurable (default 9876):
  GET /api/monitors   → JSON list of all monitors with their real x/y/w/h
  GET /stream/{id}    → MJPEG stream for monitor <id> (1-based index matching
                        the /api/monitors list, independent of Windows numbers)

UDP broadcaster — port 9875:
  Sends  "VPX-WATCHER:<local_ip>:<http_port>"  as a broadcast every 2 seconds
  so the Android app can find the server automatically without manual IP entry.
"""

from __future__ import annotations

import io
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from typing import List, Dict, Any, Optional

# mss is the cross-platform (Windows/Linux/macOS) screen-capture library.
# It is listed as an optional dependency; if missing the server will refuse
# to start and log a clear error.
try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# psutil for CPU monitoring (optional — graceful fallback when unavailable)
try:
    import psutil as _psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _psutil = None  # type: ignore[assignment]
    _PSUTIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UDP_DISCOVERY_PORT = 9875
UDP_BROADCAST_INTERVAL = 2.0   # seconds between UDP broadcasts
MJPEG_FPS = 30
JPEG_QUALITY = 95
BOUNDARY = b"frame"

# ---------------------------------------------------------------------------
# Adaptive quality helpers
# ---------------------------------------------------------------------------

def _get_cpu_percent() -> float:
    """Return current CPU usage (0-100).  Falls back to 0.0 when psutil is absent."""
    if _PSUTIL_AVAILABLE:
        try:
            return float(_psutil.cpu_percent(interval=None))
        except Exception:
            pass
    return 0.0


def _resolve_fps_quality(fps_cfg: str, quality_cfg: str) -> tuple[int, int]:
    """Resolve the effective FPS and JPEG quality from config values + CPU state.

    When either setting is ``"auto"`` the value is chosen adaptively based on
    the current CPU load so that VPX always gets scheduling priority.

    Adaptive thresholds (auto mode only):
        CPU ≤ 70%  → 30 FPS, quality 95
        CPU 70-80% → 30 FPS, quality 80
        CPU 80-90% → 20 FPS, quality 70
        CPU > 90%  → 10 FPS, quality 50
    """
    auto_fps = (fps_cfg == "auto")
    auto_quality = (quality_cfg == "auto")

    if auto_fps or auto_quality:
        cpu = _get_cpu_percent()
        if cpu > 90:
            a_fps, a_quality = 10, 50
        elif cpu > 80:
            a_fps, a_quality = 20, 70
        elif cpu > 70:
            a_fps, a_quality = 30, 80
        else:
            a_fps, a_quality = 30, 95
    else:
        a_fps, a_quality = MJPEG_FPS, JPEG_QUALITY

    try:
        fps = a_fps if auto_fps else int(fps_cfg)
    except (ValueError, TypeError):
        fps = a_fps

    try:
        quality = a_quality if auto_quality else int(quality_cfg)
    except (ValueError, TypeError):
        quality = a_quality

    fps = max(1, min(fps, 60))
    quality = max(1, min(quality, 100))
    return fps, quality


# ---------------------------------------------------------------------------
# Monitor helpers
# ---------------------------------------------------------------------------


def _get_monitors() -> List[Dict[str, Any]]:
    """Return all connected monitors with their real screen coordinates.

    Uses ``mss`` to read positions exactly as Windows reports them (x, y can
    be negative for monitors to the left/above the primary monitor).  The
    first ``mss`` entry is always the "all monitors combined" virtual screen;
    we skip it and only return the real physical monitors.

    The returned ``id`` is a 1-based index into this list — it is NOT the
    Windows monitor number, which is meaningless for our purposes.
    """
    if not _MSS_AVAILABLE:
        return []
    with mss.mss() as sct:
        result = []
        for idx, mon in enumerate(sct.monitors[1:], start=1):   # skip index 0 (virtual all-in-one)
            result.append({
                "id": idx,
                "x": mon["left"],
                "y": mon["top"],
                "w": mon["width"],
                "h": mon["height"],
                "name": f"Monitor {idx}",
            })
        return result


def _capture_monitor(monitor_id: int, jpeg_quality: int = JPEG_QUALITY) -> Optional[bytes]:
    """Capture a single monitor and return JPEG bytes, or None on failure."""
    if not _MSS_AVAILABLE:
        return None
    try:
        with mss.mss() as sct:
            monitors = sct.monitors[1:]   # skip virtual combined screen
            if monitor_id < 1 or monitor_id > len(monitors):
                return None
            mon = monitors[monitor_id - 1]
            screenshot = sct.grab(mon)
            # mss returns BGRA; convert to RGB via PIL if available,
            # otherwise use mss's own PNG → PIL fallback path.
            if _PIL_AVAILABLE:
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            else:
                # Fallback: encode via mss to PNG bytes then re-open with PIL stub
                png_bytes = mss.tools.to_png(screenshot.bgra, screenshot.size)
                img = Image.open(io.BytesIO(png_bytes))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=jpeg_quality, subsampling=0)
            return buf.getvalue()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------


class _CaptureHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for /api/monitors and /stream/<id>."""

    # Silence the default request-per-line access log so the watcher's own
    # log file isn't flooded with per-frame HTTP entries.
    def log_message(self, fmt, *args):  # noqa: ANN001
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_404(self) -> None:
        self._send_json({"error": "not found"}, 404)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")

        if path == "/api/monitors":
            monitors = _get_monitors()
            try:
                hostname = socket.gethostname()
            except Exception:
                hostname = "unknown"
            self._send_json({"monitors": monitors, "hostname": hostname})

        elif path.startswith("/stream/"):
            parts = path.split("/")
            try:
                monitor_id = int(parts[-1])
            except (ValueError, IndexError):
                self._send_404()
                return
            self._stream_monitor(monitor_id)

        else:
            self._send_404()

    def _stream_monitor(self, monitor_id: int) -> None:
        """Stream MJPEG frames for the given monitor id until the client disconnects.

        Capture only runs while a client is actively connected — no background
        capturing when nobody is watching.
        """
        # Notify the owning server that a client has connected.
        server: ScreenCaptureServer = getattr(self.server, "_capture_server_ref", None)
        if server is not None:
            server._on_client_connect()

        fps_cfg = "auto"
        quality_cfg = "auto"
        if server is not None:
            fps_cfg = server._fps_cfg
            quality_cfg = server._quality_cfg

        try:
            self.send_response(200)
            self.send_header(
                "Content-Type",
                f"multipart/x-mixed-replace; boundary={BOUNDARY.decode()}",
            )
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            while True:
                t0 = time.monotonic()
                effective_fps, effective_quality = _resolve_fps_quality(fps_cfg, quality_cfg)
                frame_interval = 1.0 / effective_fps

                jpeg = _capture_monitor(monitor_id, effective_quality)
                if jpeg is None:
                    break
                try:
                    header = (
                        f"--{BOUNDARY.decode()}\r\n"
                        f"Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(jpeg)}\r\n\r\n"
                    ).encode()
                    self.wfile.write(header)
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
                elapsed = time.monotonic() - t0
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        finally:
            if server is not None:
                server._on_client_disconnect()


# ---------------------------------------------------------------------------
# UDP broadcaster
# ---------------------------------------------------------------------------


def _get_local_ip() -> str:
    """Return the local LAN IP address (WLAN or Ethernet)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Connecting to an external address does NOT actually send a packet;
            # it just selects the correct outbound interface.
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _udp_broadcaster(local_ip: str, http_port: int, stop_event: threading.Event) -> None:
    """Send UDP broadcasts every 2 s until *stop_event* is set."""
    payload = f"VPX-WATCHER:{local_ip}:{http_port}".encode("ascii")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
    except Exception:
        return

    while not stop_event.is_set():
        try:
            sock.sendto(payload, ("255.255.255.255", UDP_DISCOVERY_PORT))
        except Exception:
            pass
        stop_event.wait(UDP_BROADCAST_INTERVAL)

    try:
        sock.close()
    except Exception:
        pass


def _set_low_thread_priority() -> None:
    """Lower the current thread's scheduling priority so VPX gets CPU first.

    On Windows we use ``BELOW_NORMAL_PRIORITY_CLASS``; on other platforms we
    try ``os.nice()`` and silently ignore permission errors.
    """
    try:
        import sys
        if sys.platform == "win32":
            import ctypes
            THREAD_PRIORITY_BELOW_NORMAL = -1
            ctypes.windll.kernel32.SetThreadPriority(  # type: ignore[attr-defined]
                ctypes.windll.kernel32.GetCurrentThread(),  # type: ignore[attr-defined]
                THREAD_PRIORITY_BELOW_NORMAL,
            )
        else:
            import os
            os.nice(5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public server class
# ---------------------------------------------------------------------------


class ScreenCaptureServer:
    """Manages the MJPEG HTTP server and the UDP discovery broadcaster.

    Performance safeguards
    ----------------------
    * HTTP-server and capture threads run at **below-normal priority** so that
      VPX always gets CPU first.
    * Frames are only captured while at least one streaming client is
      connected — there is no background capturing when nobody is watching.
    * When ``fps_cfg`` / ``quality_cfg`` are ``"auto"`` the server adapts
      JPEG quality and frame-rate based on ``psutil.cpu_percent()``.

    Usage::

        server = ScreenCaptureServer(http_port=9876)
        server.start()
        ...
        server.stop()
    """

    def __init__(
        self,
        http_port: int = 9876,
        fps_cfg: str = "auto",
        quality_cfg: str = "auto",
    ) -> None:
        self.http_port = http_port
        self._fps_cfg = fps_cfg
        self._quality_cfg = quality_cfg
        self._http_server: Optional[ThreadingHTTPServer] = None
        self._stop_event = threading.Event()
        self._http_thread: Optional[threading.Thread] = None
        self._udp_thread: Optional[threading.Thread] = None

        # Track connected streaming clients so we can report to UI.
        self._client_lock = threading.Lock()
        self._active_client_count: int = 0

        # Cache the local IP so it doesn't have to be resolved on every broadcast.
        self._local_ip: str = "127.0.0.1"

    def _on_client_connect(self) -> None:
        with self._client_lock:
            self._active_client_count += 1

    def _on_client_disconnect(self) -> None:
        with self._client_lock:
            self._active_client_count = max(0, self._active_client_count - 1)

    @property
    def active_clients(self) -> int:
        """Number of currently connected streaming clients."""
        with self._client_lock:
            return self._active_client_count

    @property
    def local_ip(self) -> str:
        """Local LAN IP the server is reachable on."""
        return self._local_ip

    @property
    def is_running(self) -> bool:
        """True when the HTTP server thread is alive and accepting connections."""
        return self._http_thread is not None and self._http_thread.is_alive()

    @property
    def available(self) -> bool:
        """True when the required libraries (mss, PIL) are installed."""
        return _MSS_AVAILABLE and _PIL_AVAILABLE

    def start(self) -> bool:
        """Start the HTTP server and UDP broadcaster.

        Returns True on success, False if dependencies are missing or the
        server is already running.
        """
        if not self.available:
            return False
        if self._http_thread and self._http_thread.is_alive():
            return True   # already running

        self._stop_event.clear()

        try:
            self._http_server = ThreadingHTTPServer(("", self.http_port), _CaptureHandler)
            # Store a back-reference so the request handler can reach us.
            self._http_server._capture_server_ref = self  # type: ignore[attr-defined]
        except OSError:
            return False

        def _serve_with_low_priority():
            _set_low_thread_priority()
            self._http_server.serve_forever()

        self._http_thread = threading.Thread(
            target=_serve_with_low_priority,
            daemon=True,
            name="ScreenCaptureHTTP",
        )
        self._http_thread.start()

        self._local_ip = _get_local_ip()

        def _udp_with_low_priority():
            _set_low_thread_priority()
            _udp_broadcaster(self._local_ip, self.http_port, self._stop_event)

        self._udp_thread = threading.Thread(
            target=_udp_with_low_priority,
            daemon=True,
            name="ScreenCaptureUDP",
        )
        self._udp_thread.start()

        return True

    def stop(self) -> None:
        """Stop the HTTP server and UDP broadcaster."""
        self._stop_event.set()
        if self._http_server:
            try:
                self._http_server.shutdown()
            except Exception:
                pass
            self._http_server = None
        if self._http_thread:
            self._http_thread.join(timeout=3)
            self._http_thread = None
        if self._udp_thread:
            self._udp_thread.join(timeout=3)
            self._udp_thread = None

