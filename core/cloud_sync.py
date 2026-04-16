from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .watcher_core import AppConfig, Bridge

from .watcher_core import (
    log,
    save_json,
    load_json,
    secure_load_json,
    secure_save_json,
    f_achievements_state,
    f_legacy_cleanup_marker,
    f_rom_keys_lowercased_marker,
    f_rom_keys_cloud_cleaned_marker,
    f_progress_upload_log,
    _load_progress_upload_log,
    _save_progress_upload_log,
    p_highlights,
    compute_player_level,
    _is_valid_rom_name,
    f_global_ach,
    compute_rarity,
    ensure_dir,
    is_excluded_field,
)

_FIREBASE_ILLEGAL_CHARS_RE = re.compile(r'[.$#\[\]/]')


def _urlopen_ssl_aware(cfg, req, timeout: int):
    """Open *req* with SSL verification; fall back to unverified on SSLError.

    Tries a fully-verified TLS connection first.  If the connection fails with
    an SSL error (e.g. outdated Windows root certificates), retries with
    certificate verification disabled and logs a warning so users are aware.
    """
    ctx = ssl.create_default_context()
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    except ssl.SSLError:
        ctx_fb = ssl.create_default_context()
        ctx_fb.check_hostname = False
        ctx_fb.verify_mode = ssl.CERT_NONE
        log(cfg, "[CLOUD] SSL verification failed, falling back to unverified", "WARN")
        return urllib.request.urlopen(req, timeout=timeout, context=ctx_fb)

def _sanitize_firebase_keys(d: dict) -> dict:
    """Return a copy of *d* with all Firebase-illegal characters (. $ # [ ] /)
    in the keys replaced by underscores."""
    return {_FIREBASE_ILLEGAL_CHARS_RE.sub("_", k): v for k, v in d.items()}

class CloudSync:
    _upload_skip_warned: bool = False
    _upload_skip_warned_lock = threading.Lock()

    # Client-side dedup: track (dedup_key -> timestamp) for recent competitive uploads.
    # Keys expire implicitly after _DEDUP_WINDOW_SEC seconds.
    _DEDUP_WINDOW_SEC: float = 60.0
    _recent_score_uploads: dict = {}
    _recent_score_uploads_lock = threading.Lock()
    _recent_progress_uploads: dict = {}
    _recent_progress_uploads_lock = threading.Lock()

    # Short-window dedup for full-achievements uploads to suppress burst duplicates that
    # arise when multiple callers (e.g. _ach_record_unlocks + _persist_and_toast) fire
    # upload_full_achievements for the same player within the same session-end cycle.
    _FULL_ACH_DEDUP_WINDOW_SEC: float = 5.0
    _recent_full_ach_uploads: dict = {}
    _recent_full_ach_uploads_lock = threading.Lock()

    # Notification message shown when a cloud upload is blocked due to missing VPS-ID.
    _BLOCKED_NO_VPS_MESSAGE: str = "Cloud Upload Blocked · No VPS-ID assigned\nGo to 'Available Maps' to assign this table"

    @staticmethod
    def _warn_missing_player_name(cfg: AppConfig) -> bool:
        """Returns True if player name is missing/default and upload should be skipped.
        Logs a once-only warning on the first occurrence."""
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not pname or pname.lower() == "player":
            with CloudSync._upload_skip_warned_lock:
                if not CloudSync._upload_skip_warned:
                    log(cfg, "[CLOUD] Upload skipped: Please set a player name (not 'Player') in System tab to enable cloud uploads.", "WARN")
                    CloudSync._upload_skip_warned = True
            return True
        return False

    @staticmethod
    def _emit_submission_state(cfg: "AppConfig", resp_body: str, bridge: Optional["Bridge"]) -> None:
        """Parse a server response body for submission_state and emit the status overlay signal.

        Handles structured responses: ``{"submission_state": "accepted"|"flagged"|"rejected"}``.
        Silently ignores empty bodies, plain-text, or legacy Firebase-style responses so that
        backwards compatibility with servers that do not return structured state is preserved.
        """
        if not bridge:
            return
        try:
            resp_data = json.loads(resp_body)
            if not isinstance(resp_data, dict):
                return
            state = str(resp_data.get("submission_state", "") or "").lower().strip()
            if state == "accepted":
                bridge.status_overlay_show.emit("Online · Verified", 0, "#00C853")
            elif state == "flagged":
                bridge.status_overlay_show.emit("Online · Flagged", 0, "#FFA500")
            elif state == "rejected":
                bridge.status_overlay_show.emit("Online · Rejected", 0, "#FF3B30")
        except Exception:
            pass

    @staticmethod
    def _notify_cloud_blocked(bridge: Optional["Bridge"], message: str) -> None:
        """Emit a status overlay badge when a cloud upload is locally blocked.

        Uses the same status_overlay_show signal as _emit_submission_state so the
        in-game badge reflects the blocked state with a consistent visual style.
        Silently no-ops when bridge is None (e.g. headless / test contexts).
        """
        if not bridge:
            return
        try:
            bridge.status_overlay_show.emit(message, 0, "#FFA500")
        except Exception:
            pass

    @staticmethod
    def validate_player_identity(cfg: AppConfig, player_id: str, player_name: str) -> dict:
        """Check whether player_id and player_name are valid and unique in the cloud.

        Returns ``{"ok": True}`` when the identity is valid, or
        ``{"ok": False, "reason": "name_reserved"|"id_conflict"|"name_conflict", "msg": "..."}``
        when validation fails.

        Scenarios:
        - Name is "Player" or "player" (case-insensitive) → name_reserved (always, even when cloud is off)
        - ID new + Name new → ok
        - ID exists + stored name matches entered name → ok (Cloud Restore)
        - ID exists + stored name does NOT match → id_conflict
        - Name already used by a different ID → name_conflict
        - Cloud URL missing or cloud disabled → server checks skipped (ok), but name_reserved still checked
        """
        player_id = (player_id or "").strip()
        player_name = (player_name or "").strip()

        # Always block the reserved default name, regardless of cloud state.
        if player_name.lower() == "player":
            return {
                "ok": False,
                "reason": "name_reserved",
                "msg": (
                    "⛔ Reserved Name — The name 'Player' cannot be used. "
                    "Please choose a different name."
                ),
            }

        if not player_id or not player_name:
            return {"ok": True}

        # Server-side checks require a reachable cloud and cloud sync enabled.
        if not cfg.CLOUD_URL or not cfg.CLOUD_ENABLED:
            return {"ok": True}

        existing_ids = CloudSync.fetch_player_ids(cfg)

        # Build a lowercase → actual-key mapping for case-insensitive lookup.
        existing_ids_lower = {pid.lower(): pid for pid in existing_ids}
        player_id_lower = player_id.lower()

        # Check 1: if this ID already exists (case-insensitive), verify the stored name matches.
        if player_id_lower in existing_ids_lower:
            cloud_key = existing_ids_lower[player_id_lower]
            stored_name = CloudSync.fetch_node(cfg, f"players/{cloud_key}/achievements/name")
            if not isinstance(stored_name, str) or not stored_name.strip():
                # Fall back to a progress entry for the stored name.
                try:
                    progress = CloudSync.fetch_node(cfg, f"players/{cloud_key}/progress")
                    if isinstance(progress, dict) and progress:
                        first_entry = next(iter(progress.values()), None)
                        if isinstance(first_entry, dict):
                            stored_name = first_entry.get("name", "")
                except Exception as _e:
                    log(cfg, f"[CLOUD] validate_player_identity: progress fallback error for {cloud_key}: {_e}", "WARN")
                    stored_name = ""

            if isinstance(stored_name, str) and stored_name.strip():
                if stored_name.strip().lower() != player_name.lower():
                    return {
                        "ok": False,
                        "reason": "id_conflict",
                        "msg": (
                            "⛔ Player ID Conflict — This Player ID is already registered to a "
                            "different player name. Please choose a different Player ID or enter "
                            "the correct name."
                        ),
                    }

        # Check 2: if the entered name is already used by a different player ID (case-insensitive).
        other_ids = [pid for pid in existing_ids if pid.lower() != player_id_lower]
        if other_ids:
            paths = [f"players/{pid}/achievements/name" for pid in other_ids]
            batch = CloudSync.fetch_parallel(cfg, paths, max_workers=20)
            for _path, name_data in batch.items():
                if isinstance(name_data, str) and name_data.strip().lower() == player_name.lower():
                    return {
                        "ok": False,
                        "reason": "name_conflict",
                        "msg": (
                            "⛔ Duplicate Player Name — This player name is already in use by "
                            "another player. Please choose a different name."
                        ),
                    }

        return {"ok": True}

    @staticmethod
    def cleanup_legacy_progress(cfg: AppConfig) -> None:
        """Delete cloud progress entries that lack a vps_id (legacy entries uploaded before
        VPS mapping was mandatory).  Runs only once per installation, guarded by a marker file.
        Executes in a background thread to avoid blocking the UI.
        """
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not cfg.CLOUD_BACKUP_ENABLED:
            return

        marker = f_legacy_cleanup_marker(cfg)
        if os.path.isfile(marker):
            return

        pid = str(cfg.OVERLAY.get("player_id", "")).strip().lower()
        if not pid or pid == "unknown":
            return

        def _task():
            try:
                # Write marker first so that a crash mid-cleanup doesn't re-run
                # on restart (partial cleanup is better than an infinite loop).
                try:
                    ensure_dir(os.path.dirname(marker))
                    with open(marker, "w", encoding="utf-8") as _f:
                        _f.write("1")
                except Exception as e:
                    log(cfg, f"[CLOUD] cleanup_legacy_progress: could not write marker: {e}", "WARN")

                progress_data = CloudSync.fetch_node(cfg, f"players/{pid}/progress")
                if not isinstance(progress_data, dict):
                    return

                _url = cfg.CLOUD_URL.strip().rstrip('/')

                for rom, entry in progress_data.items():
                    if not isinstance(entry, dict):
                        continue
                    vps_id = (entry.get("vps_id") or "").strip()
                    if vps_id:
                        continue
                    # Delete legacy entry
                    endpoint = f"{_url}/players/{pid}/progress/{rom}.json"
                    try:
                        del_req = urllib.request.Request(endpoint, method="DELETE")
                        with _urlopen_ssl_aware(cfg, del_req, 5):
                            pass
                        log(cfg, f"[CLOUD] Deleted legacy progress entry for {rom}: missing vps_id")
                    except Exception as e:
                        log(cfg, f"[CLOUD] Failed to delete legacy progress for {rom}: {e}", "WARN")
            except Exception as e:
                log(cfg, f"[CLOUD] cleanup_legacy_progress error: {e}", "WARN")

        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def cleanup_uppercase_rom_progress(cfg: AppConfig) -> None:
        """Delete cloud progress entries whose ROM key contains uppercase letters (pre-PR-#444
        entries).  Runs only once per installation, guarded by a marker file.
        Executes in a background thread to avoid blocking the UI.
        """
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not cfg.CLOUD_BACKUP_ENABLED:
            return

        marker = f_rom_keys_cloud_cleaned_marker(cfg)
        if os.path.isfile(marker):
            return

        pid = str(cfg.OVERLAY.get("player_id", "")).strip().lower()
        if not pid or pid == "unknown":
            return

        def _task():
            try:
                # Write marker first so that a crash mid-cleanup doesn't re-run
                # on restart (partial cleanup is better than an infinite loop).
                try:
                    ensure_dir(os.path.dirname(marker))
                    with open(marker, "w", encoding="utf-8") as _f:
                        _f.write("1")
                except Exception as e:
                    log(cfg, f"[CLOUD] cleanup_uppercase_rom_progress: could not write marker: {e}", "WARN")

                progress_data = CloudSync.fetch_node(cfg, f"players/{pid}/progress")
                if not isinstance(progress_data, dict):
                    return

                _url = cfg.CLOUD_URL.strip().rstrip('/')

                for rom in list(progress_data.keys()):
                    if rom == rom.lower():
                        continue  # already lowercase, skip
                    # Delete the uppercase ROM entry from cloud
                    endpoint = f"{_url}/players/{pid}/progress/{rom}.json"
                    try:
                        del_req = urllib.request.Request(endpoint, method="DELETE")
                        with _urlopen_ssl_aware(cfg, del_req, 5):
                            pass
                        log(cfg, f"[CLOUD] Deleted uppercase ROM progress entry: {rom}")
                    except Exception as e:
                        log(cfg, f"[CLOUD] Failed to delete uppercase ROM progress for {rom}: {e}", "WARN")
            except Exception as e:
                log(cfg, f"[CLOUD] cleanup_uppercase_rom_progress error: {e}", "WARN")

        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def upload_achievement_progress(cfg: AppConfig, rom: str, unlocked: int, total: int, bridge: Optional["Bridge"] = None):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or total <= 0:
            return
        if not cfg.CLOUD_BACKUP_ENABLED:
            return
        # Block upload for custom achievement tables (names with spaces/special chars are not
        # valid VPinMAME ROM names and must not be used as Firebase path segments).
        if not _is_valid_rom_name(rom):
            return
        if CloudSync._warn_missing_player_name(cfg):
            return
        # Block upload if no VPS-ID assigned for this ROM
        try:
            from ui.vps import _load_vps_mapping
            _vps_mapping = _load_vps_mapping(cfg)
            _vps_id = (_vps_mapping.get(rom) or "").strip()
            if not _vps_id:
                log(cfg, f"[CLOUD] upload_achievement_progress blocked for {rom}: no VPS-ID assigned", "WARN")
                CloudSync._notify_cloud_blocked(bridge, CloudSync._BLOCKED_NO_VPS_MESSAGE)
                return
            _extra_vps_id = _vps_id
        except Exception as e:
            log(cfg, f"[CLOUD] upload_achievement_progress blocked for {rom}: VPS mapping error: {e}", "WARN")
            return

        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip().lower()
        if not pid or pid == "unknown":
            log(cfg, f"[CLOUD] upload_achievement_progress blocked for {rom}: no valid player_id", "WARN")
            return

        # Client-side dedup: skip if the same (pid, rom, unlocked, total) was already submitted
        # within the dedup window to avoid redundant repeated progress writes.
        _dedup_key = f"{pid}|{rom}|{unlocked}|{total}"
        _now = time.time()
        with CloudSync._recent_progress_uploads_lock:
            # Prune expired entries to prevent unbounded growth over long sessions.
            _cutoff = _now - CloudSync._DEDUP_WINDOW_SEC
            CloudSync._recent_progress_uploads = {
                k: v for k, v in CloudSync._recent_progress_uploads.items() if v > _cutoff
            }
            _last_ts = CloudSync._recent_progress_uploads.get(_dedup_key, 0.0)
            if _now - _last_ts < CloudSync._DEDUP_WINDOW_SEC:
                return
            CloudSync._recent_progress_uploads[_dedup_key] = _now

        endpoint = f"{url}/players/{pid}/progress/{rom}.json"
        
        def _task():
            percentage = round((unlocked / total) * 100, 1)
            payload = {
                "name": pname,
                "unlocked": unlocked,
                "total": total,
                "percentage": percentage,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            # Include selected badge for leaderboard display
            try:
                _ach_state = secure_load_json(f_achievements_state(cfg), {})
                _sel_badge = str(_ach_state.get("selected_badge") or "").strip()
                payload["selected_badge"] = _sel_badge  # Always include, even if empty
            except Exception:
                pass
            if _extra_vps_id:
                payload["vps_id"] = _extra_vps_id
                try:
                    from ui.vps import _load_vpsdb
                    tables = _load_vpsdb(cfg)
                    if tables:
                        for t in tables:
                            vps_entry = None
                            tf_entry = None
                            if t.get("id") == _extra_vps_id:
                                vps_entry = t
                            else:
                                for tf in (t.get("tableFiles") or []):
                                    if tf.get("id") == _extra_vps_id:
                                        vps_entry = t
                                        tf_entry = tf
                                        break
                            if vps_entry:
                                table_name = vps_entry.get("name", "")
                                if table_name:
                                    payload["table_name"] = table_name
                                if tf_entry:
                                    version = tf_entry.get("version", "")
                                    authors = tf_entry.get("authors") or []
                                    if version:
                                        payload["version"] = version
                                    if authors:
                                        payload["author"] = ", ".join(authors)
                                break
                except Exception:
                    pass
            # Build vps_id_breakdown: count of unlocked achievements per vps_id
            try:
                ach_state = secure_load_json(f_achievements_state(cfg), {"global": {}, "session": {}})
                rom_achievements = ach_state.get("session", {}).get(rom, []) or []
                breakdown: dict = {}
                for ach in rom_achievements:
                    if isinstance(ach, dict):
                        vid = (ach.get("vps_id") or "").strip()
                        if vid:
                            breakdown[vid] = breakdown.get(vid, 0) + 1
                if breakdown:
                    payload["vps_id_breakdown"] = breakdown
            except Exception:
                pass
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=5) as resp:
                    resp_body = resp.read().decode()
                    log(cfg, f"[CLOUD] Uploaded Achievement Progress for {rom}: {unlocked}/{total} ({percentage}%)")
                    CloudSync._emit_submission_state(cfg, resp_body, bridge)
            except Exception as e:
                log(cfg, f"[CLOUD] Progress upload failed: {e}", "WARN")
        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def fetch_data(cfg: AppConfig, node_path: str) -> list:
        if not cfg.CLOUD_URL or not node_path: 
            return []
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        _MAX_RETRIES = 3
        for _attempt in range(_MAX_RETRIES):
            try:
                import urllib.request
                req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
                with _urlopen_ssl_aware(cfg, req, 7) as resp:
                    raw_data = resp.read().decode('utf-8')
                    data = json.loads(raw_data)
                if not data: return []
                if isinstance(data, dict): return list(data.values())
                elif isinstance(data, list): return [x for x in data if x is not None]
                return []
            except Exception as e:
                if "UNEXPECTED_EOF_WHILE_READING" in str(e) and _attempt < _MAX_RETRIES - 1:
                    time.sleep(1 * (_attempt + 1))
                    continue
                log(cfg, f"[CLOUD] Fetch error for {endpoint}: {e}", "ERROR")
                return []

    @staticmethod
    def fetch_player_ids(cfg: AppConfig) -> list:
        """Return the list of all player IDs stored under /players/ using a shallow fetch."""
        if not cfg.CLOUD_URL:
            return []
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/players.json?shallow=true"
        _MAX_RETRIES = 3
        for _attempt in range(_MAX_RETRIES):
            try:
                import urllib.request
                req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
                with _urlopen_ssl_aware(cfg, req, 7) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                if isinstance(data, dict):
                    return list(data.keys())
                return []
            except Exception as e:
                if "UNEXPECTED_EOF_WHILE_READING" in str(e) and _attempt < _MAX_RETRIES - 1:
                    time.sleep(1 * (_attempt + 1))
                    continue
                log(cfg, f"[CLOUD] fetch_player_ids error: {e}", "ERROR")
                return []

    @staticmethod
    def fetch_node(cfg: AppConfig, node_path: str):
        """Fetch a single Firebase node and return the raw parsed object (dict, list, or None)."""
        if not cfg.CLOUD_URL or not node_path:
            return None
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        _MAX_RETRIES = 3
        for _attempt in range(_MAX_RETRIES):
            try:
                import urllib.request
                req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
                with _urlopen_ssl_aware(cfg, req, 7) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                if "UNEXPECTED_EOF_WHILE_READING" in str(e) and _attempt < _MAX_RETRIES - 1:
                    time.sleep(1 * (_attempt + 1))
                    continue
                log(cfg, f"[CLOUD] fetch_node error for {endpoint}: {e}", "ERROR")
                return None

    @staticmethod
    def fetch_parallel(cfg: AppConfig, node_paths: list, max_workers: int = 10) -> dict:
        """Fetch multiple Firebase nodes in parallel using ThreadPoolExecutor.

        Returns a dict mapping each node_path to its fetched data (or None on error).
        Turns N sequential requests into ~1 round-trip of parallel requests.
        """
        import concurrent.futures
        if not node_paths:
            return {}
        results = {}

        def _fetch_one(node_path):
            return node_path, CloudSync.fetch_node(cfg, node_path)

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(node_paths))) as executor:
            futures = {executor.submit(_fetch_one, path): path for path in node_paths}
            for future in concurrent.futures.as_completed(futures):
                try:
                    path, data = future.result()
                    results[path] = data
                except Exception as e:
                    path = futures.get(future, "unknown")
                    log(cfg, f"[CLOUD] fetch_parallel error for {path}: {e}", "ERROR")
        return results

    @staticmethod
    def set_node(cfg: AppConfig, node_path: str, data) -> bool:
        """Write (PUT) arbitrary data to a Firebase node. Returns True on success.

        Retries up to 3 times on transient ``UNEXPECTED_EOF_WHILE_READING``
        errors, matching the retry pattern used in ``fetch_node()`` and
        ``fetch_data()``.
        """
        if not cfg.CLOUD_URL or not node_path:
            return False
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        payload = None
        _MAX_RETRIES = 3
        for _attempt in range(_MAX_RETRIES):
            try:
                payload = json.dumps(data).encode('utf-8')
                put_req = urllib.request.Request(endpoint, data=payload, method='PUT')
                put_req.add_header('Content-Type', 'application/json')
                with _urlopen_ssl_aware(cfg, put_req, 10):
                    pass
                return True
            except Exception as e:
                if "UNEXPECTED_EOF_WHILE_READING" in str(e) and _attempt < _MAX_RETRIES - 1:
                    time.sleep(1 * (_attempt + 1))
                    continue
                size_info = f"{len(payload)} bytes" if payload is not None else "serialization failed"
                log(cfg, f"[CLOUD] set_node error for {endpoint} (payload size: {size_info}): {e}", "WARN")
                return False
        return False

    @staticmethod
    def patch_node(cfg: AppConfig, node_path: str, data) -> bool:
        """Update (PATCH) fields on a Firebase node without deleting unmentioned children.

        Uses HTTP PATCH instead of PUT so that existing child nodes (e.g. ``session/``
        sub-nodes) are preserved when only metadata fields are updated.
        Retries up to 3 times on transient ``UNEXPECTED_EOF_WHILE_READING`` errors,
        matching the retry pattern used in ``set_node()``.
        Returns True on success.
        """
        if not cfg.CLOUD_URL or not node_path:
            return False
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        payload = None
        _MAX_RETRIES = 3
        for _attempt in range(_MAX_RETRIES):
            try:
                payload = json.dumps(data).encode('utf-8')
                patch_req = urllib.request.Request(endpoint, data=payload, method='PATCH')
                patch_req.add_header('Content-Type', 'application/json')
                with _urlopen_ssl_aware(cfg, patch_req, 10):
                    pass
                return True
            except Exception as e:
                if "UNEXPECTED_EOF_WHILE_READING" in str(e) and _attempt < _MAX_RETRIES - 1:
                    time.sleep(1 * (_attempt + 1))
                    continue
                size_info = f"{len(payload)} bytes" if payload is not None else "serialization failed"
                log(cfg, f"[CLOUD] patch_node error for {endpoint} (payload size: {size_info}): {e}", "WARN")
                return False
        return False

    @staticmethod
    def restore_from_cloud(cfg: AppConfig) -> bool:
        """Restore local achievement state from the cloud.

        Fetches ``players/{pid}/achievements`` and reconstructs the local
        ``achievements_state.json``.  Also fetches ``players/{pid}/progress``
        and merges ROM entries into ``roms_played`` and updates the local
        ``progress_upload_log.json`` so that already-uploaded progress entries
        are not re-sent after a restore.  After merging ``roms_played``, the
        method re-evaluates global achievement rules from ``global_achievements.json``
        that can be resolved without a running Watcher instance:

        * ``nvram_tally`` rules — sums the target field across all played ROMs
          by reading cached ``end_audits`` from each ROM's session summary file
          (``session_stats/Highlights/{rom}.summary.json``).
        * ``rom_count`` rules with ``manufacturer == "__any__"`` — checks whether
          enough distinct ROMs have been played (``min`` threshold only; rules that
          require per-manufacturer or per-brand counts are skipped because they
          need a running Watcher instance to resolve ROM → manufacturer mappings).

        Finally fetches ``players/{pid}/vps_mapping`` and saves it to the local
        ``vps_id_mapping.json``.

        Returns ``True`` on success, ``False`` when a critical step fails.
        """
        if not cfg.CLOUD_URL or not cfg.CLOUD_ENABLED:
            log(cfg, "[CLOUD] restore_from_cloud: cloud not enabled", "WARN")
            return False

        pid = str(cfg.OVERLAY.get("player_id", "")).strip().lower()
        if not pid or pid == "unknown":
            log(cfg, "[CLOUD] restore_from_cloud: no valid player_id set", "WARN")
            return False

        # ── 1. Fetch achievements node ────────────────────────────────────────
        data = CloudSync.fetch_node(cfg, f"players/{pid}/achievements")
        if not data or not isinstance(data, dict):
            log(cfg, f"[CLOUD] restore_from_cloud: no achievements data found for player {pid}", "WARN")
            return False

        # ── 2. Reconstruct local achievements state ───────────────────────────
        state = {
            "global": {"__global__": data.get("global", [])},
            "session": data.get("session", {}),
            "roms_played": data.get("roms_played", []),
            "badges": data.get("badges", []),
            "selected_badge": data.get("selected_badge", ""),
        }
        if not isinstance(state["session"], dict):
            state["session"] = {}
        if not isinstance(state["roms_played"], list):
            state["roms_played"] = []

        # Always fetch the session sub-node and merge it into state["session"].
        # Session data is stored per-ROM under achievements/session/{rom} (chunked
        # format) to avoid oversized single requests.  The inline metadata PUT/PATCH
        # never includes the session key, so sub-nodes are the canonical source.
        # Merging ensures ROMs present in the inline metadata but absent from the
        # sub-node are also preserved (backward-compat with old inline format).
        try:
            session_data = CloudSync.fetch_node(cfg, f"players/{pid}/achievements/session")
            if isinstance(session_data, dict) and session_data:
                # Merge: sub-node entries take precedence per ROM (they are the
                # authoritative chunked store), but keep any ROMs that came from
                # the inline metadata and are not present in the sub-node.
                for rom, entries in session_data.items():
                    if entries:  # Only overwrite if sub-node has actual data
                        state["session"][rom] = entries
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: session sub-node fetch failed (non-critical): {e}", "WARN")

        # ── 3. Fetch progress node, enrich state, update local upload log ─────
        try:
            progress_data = CloudSync.fetch_node(cfg, f"players/{pid}/progress")
            if isinstance(progress_data, dict) and progress_data:
                log_data = _load_progress_upload_log(cfg)
                for rom, entry in progress_data.items():
                    if not isinstance(entry, dict) or not rom:
                        continue
                    vps_id = str(entry.get("vps_id") or "").strip()
                    if vps_id:
                        log_data[rom] = vps_id
                    # Populate roms_played from progress data
                    if rom not in state["roms_played"]:
                        state["roms_played"].append(rom)
                    # Warn when a ROM has unlocked achievements but no session
                    # entries could be reconstructed (cloud achievements node
                    # was stale when the progress was last written).
                    unlocked = entry.get("unlocked", 0)
                    if unlocked > 0 and rom not in state["session"]:
                        log(
                            cfg,
                            f"[CLOUD] restore_from_cloud: ROM '{rom}' has {unlocked} unlocked "
                            f"achievement(s) in progress but no session details in cloud — "
                            f"session details could not be fully reconstructed",
                            "WARN",
                        )
                _save_progress_upload_log(cfg, log_data)
                log(
                    cfg,
                    f"[CLOUD] restore_from_cloud: progress log restored for {len(progress_data)} ROM(s)",
                )
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: progress restore failed (non-critical): {e}", "WARN")

        # ── 3.5. Re-evaluate global achievements from local NVRAM summary data ─
        try:
            _global_rules_raw = load_json(f_global_ach(cfg))
            if isinstance(_global_rules_raw, list):
                _global_rules_for_restore = _global_rules_raw
            elif isinstance(_global_rules_raw, dict):
                _global_rules_for_restore = _global_rules_raw.get("rules") or []
            else:
                _global_rules_for_restore = []

            if _global_rules_for_restore:
                _roms_played = list(state.get("roms_played") or [])
                _already_global = {
                    str(e.get("title", "")).strip()
                    for entries in state.get("global", {}).values()
                    for e in (entries if isinstance(entries, list) else [])
                    if isinstance(e, dict)
                }

                # Load end_audits from session summary files for each played ROM
                _rom_audits_lc: dict = {}  # rom -> {field_lowercase: value}
                for _r in _roms_played:
                    _summary_path = os.path.join(p_highlights(cfg), f"{_r}.summary.json")
                    if os.path.isfile(_summary_path):
                        try:
                            _summary_data = secure_load_json(_summary_path, {})
                            _audits = _summary_data.get("end_audits", {})
                            if isinstance(_audits, dict) and _audits:
                                _rom_audits_lc[_r] = {k.lower(): v for k, v in _audits.items()}
                        except Exception:
                            pass

                _newly_global: list = []
                _now_iso = datetime.now(timezone.utc).isoformat()

                for _rule in _global_rules_for_restore:
                    if not isinstance(_rule, dict):
                        continue
                    _title = (_rule.get("title") or "").strip()
                    if not _title or _title in _already_global:
                        continue
                    _cond = _rule.get("condition") or {}
                    if not isinstance(_cond, dict):
                        continue
                    _rtype = str(_cond.get("type") or "").lower()

                    if _rtype == "nvram_tally":
                        _field = str(_cond.get("field") or "").strip()
                        if not _field or is_excluded_field(_field):
                            continue
                        try:
                            _need = int(_cond.get("min", 1))
                        except (TypeError, ValueError):
                            continue
                        _field_lc = _field.lower()
                        _total = 0
                        for _r in _roms_played:
                            _aud = _rom_audits_lc.get(_r, {})
                            try:
                                _total += int(_aud.get(_field_lc, 0))
                            except (TypeError, ValueError):
                                pass
                        if _total >= _need:
                            _newly_global.append({"title": _title, "ts": _now_iso, "origin": "global_achievements"})
                            _already_global.add(_title)

                    elif _rtype == "rom_count":
                        _manufacturer = str(_cond.get("manufacturer") or "").strip()
                        if _manufacturer != "__any__":
                            # Cannot resolve manufacturer without a running Watcher instance – skip
                            continue
                        _min_brands = _cond.get("min_brands")
                        if _min_brands is not None:
                            # Cannot determine per-brand counts without a running Watcher instance – skip
                            continue
                        try:
                            _need = int(_cond.get("min", 1))
                        except (TypeError, ValueError):
                            continue
                        if len(set(_roms_played)) >= _need:
                            _newly_global.append({"title": _title, "ts": _now_iso, "origin": "global_achievements"})
                            _already_global.add(_title)

                if _newly_global:
                    _global_lst = state.setdefault("global", {}).setdefault("__global__", [])
                    if not isinstance(_global_lst, list):
                        state["global"]["__global__"] = []
                        _global_lst = state["global"]["__global__"]
                    _global_lst.extend(_newly_global)
                    log(
                        cfg,
                        f"[CLOUD] restore_from_cloud: {len(_newly_global)} global achievement(s) "
                        f"re-evaluated and restored from local NVRAM data",
                    )
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: global achievement re-evaluation failed (non-critical): {e}", "WARN")

        # ── 4. Save the enriched state and recompute level ────────────────────
        try:
            secure_save_json(f_achievements_state(cfg), state)
            lv = compute_player_level(state)
            log(
                cfg,
                f"[CLOUD] restore_from_cloud: achievements restored for player {pid} "
                f"(level {lv['level']}, {lv['total']} achievements)",
            )
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: failed to save achievements state: {e}", "WARN")
            return False

        # ── 5. Fetch vps_mapping node and save locally ────────────────────────
        try:
            vps_data = CloudSync.fetch_node(cfg, f"players/{pid}/vps_mapping")
            if vps_data and isinstance(vps_data, dict):
                from ui.vps import _save_vps_mapping
                _save_vps_mapping(cfg, vps_data)
                log(cfg, f"[CLOUD] restore_from_cloud: VPS mapping restored: {len(vps_data)} entries")
        except Exception as e:
            log(cfg, f"[CLOUD] restore_from_cloud: VPS mapping restore failed (non-critical): {e}", "WARN")

        return True

    @staticmethod
    def upload_full_achievements(cfg: AppConfig, state: dict, player_name: str):
        """Upload the full achievements state (global + session + roms_played) to Firebase
        under /players/{pid}/achievements.json. Called automatically after each session
        and each achievement unlock when cloud sync is enabled."""
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL:
            return
        if not cfg.CLOUD_BACKUP_ENABLED:
            return
        pname = player_name.strip() if player_name else cfg.OVERLAY.get("player_name", "Player").strip()
        if not pname or pname.lower() == "player":
            with CloudSync._upload_skip_warned_lock:
                if not CloudSync._upload_skip_warned:
                    log(cfg, "[CLOUD] Upload skipped: Please set a player name (not 'Player') in System tab to enable cloud uploads.", "WARN")
                    CloudSync._upload_skip_warned = True
            return
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip().lower()

        # Dedup: suppress burst duplicates when multiple callers fire within the same
        # session-end cycle (e.g. _ach_record_unlocks + _persist_and_toast).
        _now = time.time()
        with CloudSync._recent_full_ach_uploads_lock:
            _last_ts = CloudSync._recent_full_ach_uploads.get(pid, 0.0)
            if _now - _last_ts < CloudSync._FULL_ACH_DEDUP_WINDOW_SEC:
                return
            CloudSync._recent_full_ach_uploads[pid] = _now

        def _task():
            global_entries = []
            try:
                global_entries = list(state.get("global", {}).get("__global__", []) or [])
            except Exception:
                pass
            session_entries = {}
            try:
                session_entries = dict(state.get("session", {}) or {})
            except Exception:
                pass
            roms_played = []
            try:
                roms_played = list(state.get("roms_played", []) or [])
            except Exception:
                pass
            lv = compute_player_level(state)
            badges = list(state.get("badges") or [])
            selected_badge = state.get("selected_badge", "")
            # Upload metadata without session to avoid oversized single request.
            # custom_progress and global_tally are no longer uploaded to reduce traffic.
            metadata_payload = {
                "name": pname,
                "ts": datetime.now(timezone.utc).isoformat(),
                "global": global_entries,
                "roms_played": roms_played,
                "player_level": lv["level"],
                "player_level_name": lv["name"],
                "player_prestige": lv["prestige"],
                "player_prestige_display": lv["prestige_display"],
                "player_fully_maxed": lv["fully_maxed"],
                "badges": badges,
                "badge_count": len(badges),
                "selected_badge": selected_badge,
            }
            if CloudSync.patch_node(cfg, f"players/{pid}/achievements", metadata_payload):
                log(cfg, "[CLOUD] Full achievements metadata uploaded")
            else:
                log(cfg, "[CLOUD] upload_full_achievements: metadata upload failed", "WARN")
            # Batch all session ROM data into a single patch_node call to reduce HTTP requests.
            session_batch = {rom: entries for rom, entries in session_entries.items() if entries}
            if session_batch:
                if not CloudSync.patch_node(cfg, f"players/{pid}/achievements/session", session_batch):
                    log(cfg, "[CLOUD] upload_full_achievements: session batch upload failed", "WARN")

        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def fetch_rarity_for_rom(cfg: AppConfig, rom: str) -> tuple:
        """
        Fetch all players' achievement data from cloud and compute rarity for each
        achievement title of the given ROM.

        Returns: ({achievement_title: {tier, color, pct}, ...}, total_players)
        """
        player_ids = CloudSync.fetch_player_ids(cfg)
        if not player_ids:
            return {}, 0

        # Fetch only the per-ROM session node instead of the entire achievements node
        # to reduce download traffic (shallow per-ROM path).
        paths = [f"players/{pid}/achievements/session/{rom}" for pid in player_ids]
        batch = CloudSync.fetch_parallel(cfg, paths)

        total_players = 0
        title_counts: dict = {}

        for path, rom_entries in batch.items():
            if not rom_entries:
                continue
            # rom_entries is the direct list (or sparse object) for this ROM
            if isinstance(rom_entries, dict):
                rom_entries = list(rom_entries.values())
            if not isinstance(rom_entries, list):
                continue
            total_players += 1
            seen_titles: set = set()
            for e in rom_entries:
                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    title_counts[t] = title_counts.get(t, 0) + 1

        result: dict = {}
        for title, count in title_counts.items():
            result[title] = compute_rarity(count, total_players)

        # Cache rarity data back to cloud under players/{pid}/rarity_cache/{rom}.
        # Store as a list of {title, tier, color, pct} entries instead of a dict
        # keyed by achievement title: Firebase Realtime Database forbids certain
        # characters (. $ # [ ] /) in key names and achievement titles can contain
        # them (e.g. "Dr. Dude").  The in-memory `result` dict returned below is
        # always computed locally from player data and is never read back from this
        # Firebase node, so no reverse transformation is needed on the read path.
        try:
            if result and cfg.CLOUD_URL and cfg.CLOUD_ENABLED:
                overlay = cfg.OVERLAY if isinstance(cfg.OVERLAY, dict) else {}
                pid = str(overlay.get("player_id", "unknown")).strip().lower()
                safe_rom = rom.replace("/", "_").replace(".", "_")
                result_list = [{"title": t, **info} for t, info in result.items()]
                CloudSync.set_node(
                    cfg,
                    f"players/{pid}/rarity_cache/{safe_rom}",
                    {"data": result_list, "total_players": total_players,
                     "ts": datetime.now(timezone.utc).isoformat()},
                )
        except Exception:
            pass

        return result, total_players

    @staticmethod
    def fetch_rarity_for_cat(cfg: AppConfig, firebase_key: str) -> tuple:
        """Fetch all players' CAT progress from cloud and compute rarity for each
        achievement title of the given custom table.

        Returns: ({achievement_title: {tier, color, pct}, ...}, total_players)
        """
        player_ids = CloudSync.fetch_player_ids(cfg)
        if not player_ids:
            return {}, 0

        paths = [f"players/{pid}/progress_cat/{firebase_key}" for pid in player_ids]
        batch = CloudSync.fetch_parallel(cfg, paths)

        total_players = 0
        title_counts: dict = {}

        for path, data in batch.items():
            if not data or not isinstance(data, dict):
                continue
            unlocked_titles = data.get("unlocked_titles", [])
            if not unlocked_titles:
                continue
            total_players += 1
            seen_titles: set = set()
            for t in unlocked_titles:
                t = str(t).strip()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    title_counts[t] = title_counts.get(t, 0) + 1

        result: dict = {}
        for title, count in title_counts.items():
            result[title] = compute_rarity(count, total_players)

        return result, total_players

    # ── App signals polling ─────────────────────────────────────────────────

    @staticmethod
    def poll_app_signals(cfg: AppConfig) -> list:
        """Read and process app_signals from Firebase.
        Path: players/{pid}/app_signals/
        Returns list of signal dicts, then deletes processed signals.
        """
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL:
            return []
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip().lower()
        if pid == "unknown":
            return []
        try:
            data = CloudSync.fetch_node(cfg, f"players/{pid}/app_signals")
            if not data or not isinstance(data, dict):
                return []
            signals = []
            for signal_id, signal_data in data.items():
                if isinstance(signal_data, dict):
                    signal_data["_signal_id"] = signal_id
                    signals.append(signal_data)
                    # Delete processed signal
                    CloudSync.set_node(cfg, f"players/{pid}/app_signals/{signal_id}", None)
            return signals
        except Exception:
            return []


