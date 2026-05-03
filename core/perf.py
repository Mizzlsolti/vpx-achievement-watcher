"""core/perf.py – Shared performance / FPS-quality resolution helper.

Both the WebRTC sender (``core/webrtc_stream.ScreenCaptureTrack``) and the
MJPEG receiver (``ui/overlay_pip._MjpegReader``) need to resolve the same
``(fps, quality)`` pair from the user's ``SCREEN_CAPTURE_FPS`` and
``SCREEN_CAPTURE_QUALITY`` config values.  This module centralises that logic
so the two sides stay in lock-step.
"""

from __future__ import annotations

import time

# ---------------------------------------------------------------------------
# Adaptive table: (cpu_threshold_pct, fps, quality)
# Mirrors the table in core/webrtc_stream.py::ScreenCaptureTrack._ADAPTIVE_TABLE
# ---------------------------------------------------------------------------

_ADAPTIVE_TABLE = [
    (50,  10, 60),
    (70,   8, 55),
    (85,   6, 50),
    (101,  4, 40),
]

# ---------------------------------------------------------------------------
# CPU cache (global, shared between sender and receiver)
# ---------------------------------------------------------------------------

_cpu_cache: dict = {"ts": 0.0, "value": 0.0}


def _cached_cpu(refresh_s: float = 5.0) -> float:
    """Return a cached CPU-usage percentage, refreshed every *refresh_s* seconds."""
    now = time.monotonic()
    if now - _cpu_cache["ts"] >= refresh_s:
        try:
            import psutil
            _cpu_cache["value"] = psutil.cpu_percent(interval=None)
        except Exception:
            _cpu_cache["value"] = 0.0
        _cpu_cache["ts"] = now
    return _cpu_cache["value"]


def resolve_capture_fps_quality(cfg) -> tuple:
    """Return ``(fps: int, quality: int)`` for the current config and CPU load.

    Reads ``cfg.SCREEN_CAPTURE_FPS`` and ``cfg.SCREEN_CAPTURE_QUALITY``.
    When either value is ``"auto"`` the adaptive table is consulted.
    ``cfg.OVERLAY.low_performance_mode`` clamps fps ≤ 5 and quality ≤ 40.

    Parameters
    ----------
    cfg:
        An ``AppConfig`` instance (or any object that exposes
        ``SCREEN_CAPTURE_FPS``, ``SCREEN_CAPTURE_QUALITY``, and ``OVERLAY``).

    Returns
    -------
    tuple
        ``(fps, quality)`` where both values are positive integers.
    """
    fps_raw = str(getattr(cfg, "SCREEN_CAPTURE_FPS", "auto")).strip().lower()
    qual_raw = str(getattr(cfg, "SCREEN_CAPTURE_QUALITY", "auto")).strip().lower()

    if fps_raw == "auto" or qual_raw == "auto":
        cpu = _cached_cpu()
        fps = None
        qual = None
        for threshold, fps_a, qual_a in _ADAPTIVE_TABLE:
            if cpu < threshold:
                fps = fps_a if fps_raw == "auto" else _safe_int(fps_raw, 10)
                qual = qual_a if qual_raw == "auto" else _safe_int(qual_raw, 60)
                break
        if fps is None:
            fps = 4 if fps_raw == "auto" else _safe_int(fps_raw, 4)
            qual = 40 if qual_raw == "auto" else _safe_int(qual_raw, 40)
    else:
        fps = _safe_int(fps_raw, 10)
        qual = _safe_int(qual_raw, 60)

    # Low-performance mode clamp
    try:
        ov = getattr(cfg, "OVERLAY", {}) or {}
        if bool(ov.get("low_performance_mode", False)):
            fps = min(fps, 5)
            qual = min(qual, 40)
    except Exception:
        pass

    return fps, qual


def _safe_int(value: str, default: int) -> int:
    """Parse *value* as int, returning *default* on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
