"""
notifications.py – CRUD helpers for the Dashboard notification feed.

Storage: {cfg.BASE}/notifications.json
Format:  JSON array (plain, no signature) – notifications are not scored data.

Dismissed keys for highscore_beaten / leaderboard_rank are stored in
{cfg.BASE}/notifications_dismissed.json so the same event is never
re-created after the user clears it.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

_MAX_ENTRIES = 50
_DISPLAY_LIMIT = 10

# Notification types that support persistent dismiss deduplication
_DISMISSABLE_TYPES = {"highscore_beaten", "leaderboard_rank"}


# ── file paths ───────────────────────────────────────────────────────────────

def _notifications_path(cfg) -> str:
    return os.path.join(cfg.BASE, "notifications.json")


def _dismissed_path(cfg) -> str:
    return os.path.join(cfg.BASE, "notifications_dismissed.json")


# ── dismissed keys helpers ───────────────────────────────────────────────────

def _make_dismissed_key(notif: dict) -> Optional[str]:
    """
    Build a canonical dismissed key from a notification dict.

    The key encodes ``type``, ``rom`` and ``other_player`` (if present) so
    that the exact same event is never re-created after the user clears it.
    A genuinely new event (e.g. a different player overtakes, or the same
    player with a changed score) will produce a different key and will be
    allowed through.
    """
    ntype = notif.get("type", "")
    if ntype not in _DISMISSABLE_TYPES:
        return None
    rom = str(notif.get("rom", "")).strip().lower()
    other_player = str(notif.get("other_player", "")).strip().lower()
    return f"{ntype}|{rom}|{other_player}"


def load_dismissed_keys(cfg) -> set:
    """Return the set of dismissed notification keys."""
    path = _dismissed_path(cfg)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data)
    except Exception:
        pass
    return set()


def save_dismissed_keys(cfg, keys: set):
    """Persist dismissed keys to disk (atomic write via temp file)."""
    path = _dismissed_path(cfg)
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(keys), f, indent=2, ensure_ascii=False)
            f.flush()
        try:
            os.replace(tmp, path)
        except Exception:
            os.rename(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


# ── low-level I/O ─────────────────────────────────────────────────────────────

def load_notifications(cfg) -> list:
    """Return the current list of notification dicts (newest-first order)."""
    path = _notifications_path(cfg)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def save_notifications(cfg, items: list):
    """Persist *items* to disk (atomic write via temp file)."""
    path = _notifications_path(cfg)
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
            f.flush()
        try:
            os.replace(tmp, path)
        except Exception:
            os.rename(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
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
    **extra,
) -> dict:
    """
    Create a new notification, deduplicate, trim to _MAX_ENTRIES and save.

    Deduplication rules
    -------------------
    - ``vps_missing``:       replace any existing ``vps_missing`` entry (title may change).
    - ``update_available``:  skip if an entry with same type *and* same title already exists.
    - ``leaderboard_rank`` / ``highscore_beaten``:  skipped if a matching dismissed key exists
      (type + rom + other_player).  A new notification is only created when the situation
      genuinely changes (e.g. a different player overtakes).

    Any additional keyword arguments (e.g. ``rom``, ``vps_id``, ``other_player``) are
    merged into the entry dict so click-handlers can access them.
    """
    items = load_notifications(cfg)

    if type == "vps_missing":
        items = [n for n in items if n.get("type") != "vps_missing"]

    elif type == "update_available":
        for n in items:
            if n.get("type") == "update_available" and n.get("title") == title:
                return n

    elif type in _DISMISSABLE_TYPES:
        # Check against persistent dismissed keys
        notif_for_key = {"type": type, **extra}
        key = _make_dismissed_key(notif_for_key)
        if key is not None:
            dismissed = load_dismissed_keys(cfg)
            if key in dismissed:
                # Same event already seen and dismissed — return a dummy sentinel
                return {"id": "", "type": type, "_skipped": True}

    entry = {
        "id": str(uuid.uuid4()),
        "type": type,
        "icon": icon,
        "title": title,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read": False,
        "action_tab": action_tab,
    }
    entry.update(extra)

    items.insert(0, entry)

    if len(items) > _MAX_ENTRIES:
        items = items[:_MAX_ENTRIES]

    save_notifications(cfg, items)
    return entry


def dismiss_notification(cfg, notification_id: str):
    """
    Remove a single notification and, for dismissable types, record its key
    so the same event is never re-created.
    """
    items = load_notifications(cfg)
    target = next((n for n in items if n.get("id") == notification_id), None)
    if target is None:
        return
    key = _make_dismissed_key(target)
    if key is not None:
        dismissed = load_dismissed_keys(cfg)
        dismissed.add(key)
        save_dismissed_keys(cfg, dismissed)
    items = [n for n in items if n.get("id") != notification_id]
    save_notifications(cfg, items)


def mark_read(cfg, notification_id: str):
    """Mark a single notification as read."""
    items = load_notifications(cfg)
    changed = False
    for n in items:
        if n.get("id") == notification_id and not n.get("read", False):
            n["read"] = True
            changed = True
    if changed:
        save_notifications(cfg, items)


def mark_all_read(cfg):
    """Mark all notifications as read."""
    items = load_notifications(cfg)
    changed = False
    for n in items:
        if not n.get("read", False):
            n["read"] = True
            changed = True
    if changed:
        save_notifications(cfg, items)


def clear_all(cfg):
    """Delete all notifications and record dismissed keys for dismissable types."""
    items = load_notifications(cfg)
    new_keys = set()
    for n in items:
        key = _make_dismissed_key(n)
        if key is not None:
            new_keys.add(key)
    if new_keys:
        dismissed = load_dismissed_keys(cfg)
        dismissed.update(new_keys)
        save_dismissed_keys(cfg, dismissed)
    save_notifications(cfg, [])


def unread_count(cfg) -> int:
    """Return the number of unread notifications."""
    items = load_notifications(cfg)
    return sum(1 for n in items if not n.get("read", False))
