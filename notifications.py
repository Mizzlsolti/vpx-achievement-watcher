"""
notifications.py – CRUD helpers for the Dashboard notification feed.

Storage: {cfg.BASE}/notifications.json
Format:  JSON array (plain, no signature) – notifications are not scored data.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

_MAX_ENTRIES = 50
_DISPLAY_LIMIT = 10


# ── file path ────────────────────────────────────────────────────────────────

def _notifications_path(cfg) -> str:
    return os.path.join(cfg.BASE, "notifications.json")


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
    - ``dedup_key`` dismissed:  skip creation if the key is in the dismissed-keys file.
    """
    # Check dismissed keys first
    if dedup_key:
        dismissed = load_dismissed_keys(cfg)
        if dedup_key in dismissed:
            return None

    items = load_notifications(cfg)

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

    save_notifications(cfg, items)
    return entry


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
    """Delete all notifications."""
    save_notifications(cfg, [])


def unread_count(cfg) -> int:
    """Return the number of unread notifications."""
    items = load_notifications(cfg)
    return sum(1 for n in items if not n.get("read", False))


# ── Dismissed-key helpers ─────────────────────────────────────────────────────

def _dismissed_path(cfg) -> str:
    return os.path.join(cfg.BASE, "dismissed_keys.json")


def load_dismissed_keys(cfg) -> set:
    """Load the set of dismissed notification dedup keys."""
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
    """Persist dismissed keys to disk."""
    path = _dismissed_path(cfg)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(keys), f, ensure_ascii=False)
    except Exception:
        pass


def dismiss_all(cfg):
    """Add all current notification dedup_keys to the dismissed set, then clear."""
    items = load_notifications(cfg)
    dismissed = load_dismissed_keys(cfg)
    for n in items:
        dk = n.get("dedup_key")
        if dk:
            dismissed.add(dk)
    save_dismissed_keys(cfg, dismissed)
    clear_all(cfg)
