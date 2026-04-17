"""
cat_registry.py — Manually-maintained registry of Custom Achievement Tables (CAT)
approved for cloud progress uploads.

Only tables explicitly listed in CAT_REGISTRY are allowed to upload their
achievement progress to Firebase.  The repo maintainer decides which tables
are listed; no automatic discovery or user-configurable whitelist is involved.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .watcher_core import AppConfig, Bridge

from .watcher_core import (
    log,
    load_json,
    ensure_dir,
    f_custom_achievements_progress,
    p_aweditor,
    _strip_version_from_name,
)
from .cloud_sync import CloudSync

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# CAT_REGISTRY is the single source of truth for which custom tables may push
# progress to the cloud.
#
# Dict key        — Firebase path segment (alphanumeric + underscores only),
#                   manually chosen by the maintainer.
# "table_key"     — Must match exactly the key used in
#                   custom_achievements_progress.json (i.e. the value of
#                   current_table set by the watcher during a session).
# "display_name"  — Human-readable name for cloud leaderboard display.
CAT_REGISTRY: dict[str, dict] = {
    "shovel_knight": {
        "table_key": "Shovel Knight (Original 2017)",
        "display_name": "Shovel Knight",
    },
}

# ---------------------------------------------------------------------------
# Client-side dedup (mirrors CloudSync._recent_progress_uploads pattern)
# ---------------------------------------------------------------------------

_recent_cat_uploads: dict = {}
_recent_cat_uploads_lock = threading.Lock()
_DEDUP_WINDOW_SEC: float = 60.0

# ---------------------------------------------------------------------------
# Helper: reverse lookup
# ---------------------------------------------------------------------------

def lookup_by_table_key(table_key: str) -> Optional[Tuple[str, dict]]:
    """Return (firebase_key, registry_entry) for a given table_key, or None.

    Tries exact match first, then falls back to matching with version
    suffixes stripped (e.g. 'Table Name v1.2.1' matches 'Table Name').
    """
    # Exact match first
    for firebase_key, entry in CAT_REGISTRY.items():
        if entry.get("table_key") == table_key:
            return firebase_key, entry
    # Fuzzy match: strip version suffixes and compare
    stripped_input = _strip_version_from_name(table_key).strip()
    for firebase_key, entry in CAT_REGISTRY.items():
        reg_key = entry.get("table_key", "")
        if _strip_version_from_name(reg_key).strip() == stripped_input:
            return firebase_key, entry
    return None

# ---------------------------------------------------------------------------
# Upload function
# ---------------------------------------------------------------------------

def upload_cat_progress(
    cfg: "AppConfig",
    table_key: str,
    bridge: Optional["Bridge"] = None,
) -> bool:
    """Upload CAT achievement progress to Firebase if the table is approved.

    Returns True if the background upload thread was dispatched successfully.
    Returns False at every early-return point (table not in registry,
    cloud disabled, player name not set, dedup skip, etc.).
    """
    # 1. Registry check — table must be explicitly approved
    result = lookup_by_table_key(table_key)
    if result is None:
        return False
    firebase_key, registry_entry = result

    # Validate firebase_key is a safe path segment (alphanumeric + underscores only)
    if not re.fullmatch(r"[A-Za-z0-9_]+", firebase_key):
        log(cfg, f"[CAT] upload_cat_progress blocked: invalid firebase_key '{firebase_key}'", "WARN")
        return False

    # 2. Cloud feature flags
    if not cfg.CLOUD_ENABLED:
        return False
    if not cfg.CLOUD_URL:
        return False

    # 3. Player name check (reuse existing helper)
    if CloudSync._warn_missing_player_name(cfg):
        return False

    # 4. Player ID check
    pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip().lower()
    if not pid or pid == "unknown":
        log(cfg, f"[CAT] upload_cat_progress blocked for '{table_key}': no valid player_id", "WARN")
        return False

    # 5. Read progress data
    progress_path = f_custom_achievements_progress(cfg)
    all_progress: dict = load_json(progress_path, {}) or {}
    table_progress: dict = all_progress.get(table_key, {})

    unlocked_list = table_progress.get("unlocked", [])
    unlocked_count = len(unlocked_list) if isinstance(unlocked_list, list) else 0

    # Determine total: prefer the actual rule file if available, fall back to stored value
    total_count: int = int(table_progress.get("total_rules", 0) or 0)
    try:
        custom_json_path = os.path.join(p_aweditor(cfg), f"{table_key}.custom.json")
        if os.path.isfile(custom_json_path):
            rules_data = load_json(custom_json_path, {}) or {}
            rules_list = rules_data.get("rules", [])
            if isinstance(rules_list, list) and rules_list:
                total_count = len(rules_list)
    except Exception:
        pass  # Fall through to stored total_rules value

    if total_count <= 0:
        log(cfg, f"[CAT] upload_cat_progress skipped for '{table_key}': total_count is 0", "WARN")
        return False

    # 6. Client-side dedup
    pname = cfg.OVERLAY.get("player_name", "Player").strip()
    _dedup_key = f"{pid}|{firebase_key}|{unlocked_count}|{total_count}"
    _now = time.time()
    with _recent_cat_uploads_lock:
        _cutoff = _now - _DEDUP_WINDOW_SEC
        _pruned = {k: v for k, v in _recent_cat_uploads.items() if v > _cutoff}
        _recent_cat_uploads.clear()
        _recent_cat_uploads.update(_pruned)
        _last_ts = _recent_cat_uploads.get(_dedup_key, 0.0)
        if _now - _last_ts < _DEDUP_WINDOW_SEC:
            return False
        _recent_cat_uploads[_dedup_key] = _now

    # 7. Fire HTTP request in background thread
    url = cfg.CLOUD_URL.strip().rstrip("/")
    endpoint = f"{url}/players/{pid}/progress_cat/{firebase_key}.json"

    _cfg = cfg
    _pid = pid
    _pname = pname
    _unlocked = unlocked_count
    _total = total_count
    _unlocked_list = list(unlocked_list) if isinstance(unlocked_list, list) else []
    _display_name = registry_entry["display_name"]
    _table_key = table_key
    _firebase_key = firebase_key

    def _task() -> None:
        percentage = round((_unlocked / _total) * 100, 1) if _total > 0 else 0.0
        payload = {
            "name": _pname,
            "display_name": _display_name,
            "unlocked": _unlocked,
            "total": _total,
            "percentage": percentage,
            "unlocked_titles": [str(e.get("title", "")).strip() for e in _unlocked_list if isinstance(e, dict)],
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        put_req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode(),
            method="PUT",
        )
        put_req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(put_req, timeout=5) as resp:
                resp.read()
            log(
                _cfg,
                f"[CAT] Uploaded progress for '{_table_key}' ({_firebase_key}): "
                f"{_unlocked}/{_total} ({percentage}%)",
            )
        except Exception as e:
            log(_cfg, f"[CAT] Progress upload failed for '{_table_key}': {e}", "WARN")

    threading.Thread(target=_task, daemon=True).start()
    return True
