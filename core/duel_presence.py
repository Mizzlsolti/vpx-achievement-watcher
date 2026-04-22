"""core/duel_presence.py – Lightweight presence layer for the Duel PiP system.

Each player publishes a small JSON blob to
``duels/{duel_id}/pip_presence/{player_key}`` while they are inside an active
VPX session.  The PiP window is opened only when **both** peers carry
``playing=true`` at the same time, and closed as soon as one side stops.

Schema of each presence node::

    {
        "playing": true | false,
        "orientation": "portrait" | "landscape",
        "ts": <unix milliseconds>
    }

Design notes
------------
* All Firebase I/O goes through the existing ``CloudSync.set_node`` /
  ``CloudSync.fetch_node`` helpers so the retry / SSL logic is inherited for
  free.
* A presence entry is considered *stale* (= peer not playing) when its ``ts``
  is older than ``STALE_MS`` milliseconds.  This guards against a peer that
  crashes without cleaning up.
* When ``cfg.CLOUD_ENABLED`` is ``False`` every function is a no-op so no
  traffic is generated and no PiP window ever opens through this path.
"""

from __future__ import annotations

import time
from typing import Optional

# Peer entries older than this are treated as "not playing".
STALE_MS: int = 30_000  # 30 seconds

_BASE = "duels/{duel_id}/pip_presence"


def _path(duel_id: str, player_key: str) -> str:
    return f"{_BASE.format(duel_id=duel_id)}/{player_key}"


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def publish_presence(
    cfg,
    duel_id: str,
    player_key: str,
    playing: bool,
    orientation: str,
) -> bool:
    """Write the local player's presence to Firebase.

    Returns ``True`` on success, ``False`` on any error.
    """
    if not getattr(cfg, "CLOUD_ENABLED", False):
        return False
    try:
        from core.cloud_sync import CloudSync
        data = {
            "playing": bool(playing),
            "orientation": str(orientation),
            "ts": int(time.time() * 1000),
        }
        ok = CloudSync.set_node(cfg, _path(duel_id, player_key), data)
        return ok
    except Exception as exc:
        try:
            from core.watcher_core import log
            log(cfg, f"[PiP Presence] publish_presence error: {exc}", "WARN")
        except Exception:
            pass
        return False


def remove_presence(cfg, duel_id: str, player_key: str) -> bool:
    """Remove the local player's presence node from Firebase.

    Returns ``True`` on success, ``False`` on any error.
    """
    if not getattr(cfg, "CLOUD_ENABLED", False):
        return False
    try:
        from core.cloud_sync import CloudSync
        from core.watcher_core import log
        ok = CloudSync.set_node(cfg, _path(duel_id, player_key), None)
        log(cfg, f"[PiP Presence] Removed: duel={duel_id} player={player_key}", "INFO")
        return ok
    except Exception as exc:
        try:
            from core.watcher_core import log
            log(cfg, f"[PiP Presence] remove_presence error: {exc}", "WARN")
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def fetch_presence(cfg, duel_id: str, player_key: str) -> Optional[dict]:
    """Fetch the opponent's presence node from Firebase.

    Returns the raw dict (``{playing, orientation, ts}``) or ``None`` when the
    node is absent or a network error occurs.
    """
    if not getattr(cfg, "CLOUD_ENABLED", False):
        return None
    try:
        from core.cloud_sync import CloudSync
        data = CloudSync.fetch_node(cfg, _path(duel_id, player_key))
        if isinstance(data, dict):
            return data
        return None
    except Exception as exc:
        try:
            from core.watcher_core import log
            log(cfg, f"[PiP Presence] fetch_presence error: {exc}", "WARN")
        except Exception:
            pass
        return None


def is_playing(presence: Optional[dict]) -> bool:
    """Return ``True`` when *presence* is fresh and ``playing`` is ``True``."""
    if not isinstance(presence, dict):
        return False
    if not bool(presence.get("playing", False)):
        return False
    ts = presence.get("ts")
    if ts is None:
        return False
    age_ms = int(time.time() * 1000) - int(ts)
    return age_ms < STALE_MS


def get_orientation(presence: Optional[dict], fallback: Optional[str] = "portrait") -> Optional[str]:
    """Return the orientation advertised in *presence*, or *fallback*.

    *fallback* may be ``None`` to signal "no information available".
    """
    if isinstance(presence, dict):
        val = presence.get("orientation", "")
        if val in ("portrait", "landscape"):
            return val
    return fallback
