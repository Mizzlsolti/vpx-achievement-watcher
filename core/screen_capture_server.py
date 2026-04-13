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
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List, Dict, Any

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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UDP_DISCOVERY_PORT = 9875
UDP_BROADCAST_INTERVAL = 2.0   # seconds between UDP broadcasts
MJPEG_FPS = 30
JPEG_QUALITY = 95
BOUNDARY = b"frame"

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


def _capture_monitor(monitor_id: int) -> bytes | None:
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
            img.save(buf, format="JPEG", quality=JPEG_QUALITY, subsampling=0)
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
        """Stream MJPEG frames for the given monitor id until the client disconnects."""
        self.send_response(200)
        self.send_header(
            "Content-Type",
            f"multipart/x-mixed-replace; boundary={BOUNDARY.decode()}",
        )
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        frame_interval = 1.0 / MJPEG_FPS
        while True:
            t0 = time.monotonic()
            jpeg = _capture_monitor(monitor_id)
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


# ---------------------------------------------------------------------------
# Public server class
# ---------------------------------------------------------------------------


class ScreenCaptureServer:
    """Manages the MJPEG HTTP server and the UDP discovery broadcaster.

    Usage::

        server = ScreenCaptureServer(http_port=9876)
        server.start()
        ...
        server.stop()
    """

    def __init__(self, http_port: int = 9876) -> None:
        self.http_port = http_port
        self._http_server: HTTPServer | None = None
        self._stop_event = threading.Event()
        self._http_thread: threading.Thread | None = None
        self._udp_thread: threading.Thread | None = None

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
            self._http_server = HTTPServer(("", self.http_port), _CaptureHandler)
        except OSError:
            return False

        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            daemon=True,
            name="ScreenCaptureHTTP",
        )
        self._http_thread.start()

        local_ip = _get_local_ip()
        self._udp_thread = threading.Thread(
            target=_udp_broadcaster,
            args=(local_ip, self.http_port, self._stop_event),
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
