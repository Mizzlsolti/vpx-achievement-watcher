"""
notifications.py – CRUD helpers for the Dashboard notification feed.

Storage: {cfg.BASE}/Achievements/notifications.json  (Windows Hidden attribute set)
Format:  JSON object – {"notifications": [...], "dismissed_keys": {"key": "iso-timestamp", ...}}
         notifications are not scored data.
"""

from __future__ import annotations

import ctypes
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

_MAX_ENTRIES = 50
_DISPLAY_LIMIT = 10
_DISMISSED_TTL_HOURS = 24


# ── Windows hidden-attribute helper ──────────────────────────────────────────

def _set_hidden(path: str):
    """Set Windows FILE_ATTRIBUTE_HIDDEN on *path*. No-op on non-Windows."""
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x02
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


# ── file path ────────────────────────────────────────────────────────────────

def _notifications_path(cfg) -> str:
    return os.path.join(cfg.BASE, "Achievements", "notifications.json")


# ── low-level I/O ─────────────────────────────────────────────────────────────

def _load_store(cfg) -> dict:
    """Return the raw store dict {"notifications": [...], "dismissed_keys": {...}}."""
    path = _notifications_path(cfg)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                notifs = data.get("notifications", [])
                dismissed = data.get("dismissed_keys", {})
                return {
                    "notifications": notifs if isinstance(notifs, list) else [],
                    "dismissed_keys": dismissed if isinstance(dismissed, dict) else {},
                }
            # Legacy: plain list (old notifications.json format)
            if isinstance(data, list):
                return {"notifications": data, "dismissed_keys": {}}
    except Exception:
        pass
    return {"notifications": [], "dismissed_keys": {}}


def _save_store(cfg, store: dict):
    """Persist *store* to disk (atomic write via temp file) and set Hidden attribute."""
    path = _notifications_path(cfg)
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
            f.flush()
        try:
            os.replace(tmp, path)
        except Exception:
            os.rename(tmp, path)
        _set_hidden(path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def load_notifications(cfg) -> list:
    """Return the current list of notification dicts (newest-first order)."""
    return _load_store(cfg)["notifications"]


def save_notifications(cfg, items: list):
    """Persist *items* to disk."""
    store = _load_store(cfg)
    store["notifications"] = items
    _save_store(cfg, store)


# ── migration ─────────────────────────────────────────────────────────────────

def migrate_notifications(cfg):
    """
    One-time migration:
    - Move old notifications.json content (at cfg.BASE) into the new store.
    - Remove old notifications.json and dismissed_keys.json.
    """
    old_notif = os.path.join(cfg.BASE, "notifications.json")
    old_dismissed = os.path.join(cfg.BASE, "dismissed_keys.json")

    if not os.path.isfile(old_notif) and not os.path.isfile(old_dismissed):
        return

    store = _load_store(cfg)

    # Merge old notifications if new store is empty
    if not store["notifications"] and os.path.isfile(old_notif):
        try:
            with open(old_notif, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                store["notifications"] = data
        except Exception:
            pass

    _save_store(cfg, store)

    # Remove old files
    for p in (old_notif, old_dismissed):
        try:
            if os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_notification(
    cfg,
    type: str,
    icon: str,
    title: str,
    detail: str = "",
    action_tab: Optional[str] = None,
    dedup_key: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Optional[dict]:
    """
    Create a new notification, deduplicate, trim to _MAX_ENTRIES and save.

    Deduplication rules
    -------------------
    - ``vps_missing``:          replace any existing ``vps_missing`` entry (title may change).
    - ``update_available``:     skip if an entry with same type *and* same title already exists.
    - ``leaderboard_rank`` / ``achievement_beaten``:  deduplicated by the caller (per ROM).

    Dismissal
    ---------
    If a notification was recently dismissed (via ``clear_all``), it is suppressed for
    ``_DISMISSED_TTL_HOURS`` hours so it does not immediately reappear.
    """
    store = _load_store(cfg)
    items = store["notifications"]

    # ── Prune expired dismissed keys and check dismissal ──────────────────────
    now = datetime.now(timezone.utc)
    dismissed = store.get("dismissed_keys", {})
    pruned: dict = {}
    for dk, ts_str in dismissed.items():
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if (now - ts).total_seconds() < _DISMISSED_TTL_HOURS * 3600:
                pruned[dk] = ts_str
        except Exception:
            pass
    dismissed = pruned
    store["dismissed_keys"] = dismissed

    # Check dedup_key dismissal
    if dedup_key and dedup_key in dismissed:
        _save_store(cfg, store)  # persist pruned keys
        return None

    # ── Existing deduplication logic ──────────────────────────────────────────
    if type == "vps_missing":
        items = [n for n in items if n.get("type") != "vps_missing"]

    elif type == "update_available":
        for n in items:
            if n.get("type") == "update_available" and n.get("title") == title:
                return n

    entry: dict = {
        "id": str(uuid.uuid4()),
        "type": type,
        "icon": icon,
        "title": title,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read": False,
        "action_tab": action_tab,
    }
    if dedup_key:
        entry["dedup_key"] = dedup_key
    if extra:
        entry.update(extra)

    items.insert(0, entry)

    if len(items) > _MAX_ENTRIES:
        items = items[:_MAX_ENTRIES]

    store["notifications"] = items
    _save_store(cfg, store)
    return entry


def mark_read(cfg, notification_id: str):
    """Mark a single notification as read."""
    store = _load_store(cfg)
    items = store["notifications"]
    changed = False
    for n in items:
        if n.get("id") == notification_id and not n.get("read", False):
            n["read"] = True
            changed = True
    if changed:
        store["notifications"] = items
        _save_store(cfg, store)


def mark_all_read(cfg):
    """Mark all notifications as read."""
    store = _load_store(cfg)
    items = store["notifications"]
    changed = False
    for n in items:
        if not n.get("read", False):
            n["read"] = True
            changed = True
    if changed:
        store["notifications"] = items
        _save_store(cfg, store)


def clear_all(cfg):
    """Delete all notifications and remember their dedup_keys to prevent re-creation."""
    store = _load_store(cfg)
    items = store["notifications"]

    # Collect dedup_keys from cleared notifications
    dismissed = store.get("dismissed_keys", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    for n in items:
        dk = n.get("dedup_key")
        if dk:
            dismissed[dk] = now_iso

    store["notifications"] = []
    store["dismissed_keys"] = dismissed
    _save_store(cfg, store)


def unread_count(cfg) -> int:
    """Return the number of unread notifications."""
    items = load_notifications(cfg)
    return sum(1 for n in items if not n.get("read", False))


def dismiss_all(cfg):
    """Clear all notifications. Kept for backward compatibility; delegates to clear_all()."""
    clear_all(cfg)
