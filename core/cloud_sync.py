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
    WATCHER_VERSION,
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

# Cloud areas the Watcher no longer uses (score duels / tournaments are hidden).
_BLOCKED_PREFIXES = ("duels", "tournaments", "tournament_chat")


def _is_blocked_path(node_path: str) -> bool:
    p = str(node_path or "").strip("/").split("/", 1)[0]
    return p in _BLOCKED_PREFIXES


def _db_url(cfg, node_path: str, params: Optional[dict] = None, auth: bool = True) -> str:
    """Full REST URL for *node_path* (auth token, emulator namespace, extra params)."""
    import urllib.parse as _up
    base = cfg.CLOUD_URL.strip().rstrip('/')
    path = str(node_path or "").strip("/")
    url = f"{base}/{path}.json" if path else f"{base}/.json"
    q = dict(params or {})
    ns = os.environ.get("VPXAW_DB_NS", "").strip()
    if ns:
        q["ns"] = ns
    if auth:
        try:
            from . import cloud_auth
            tok = cloud_auth.get_token(cfg)
            if tok:
                q["auth"] = tok
        except Exception:
            pass
    if q:
        url += "?" + _up.urlencode(q)
    return url


def _db_request(cfg, method: str, node_path: str, data=None, params: Optional[dict] = None,
                timeout: int = 10, retries: int = 3):
    """Perform one REST request. Returns (status, parsed_body_or_None).

    status 0 means a network error. Retries transient TLS EOF errors.
    """
    import urllib.error
    if not cfg.CLOUD_URL:
        return 0, None
    if _is_blocked_path(node_path):
        return 403, None
    body = None if method in ("GET", "DELETE") else json.dumps(data).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(_db_url(cfg, node_path, params), data=body, method=method,
                                         headers={"User-Agent": f"AchievementWatcher/{WATCHER_VERSION}"})
            if body is not None:
                req.add_header("Content-Type", "application/json")
            with _urlopen_ssl_aware(cfg, req, timeout) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            return e.code, None
        except Exception as e:
            if "UNEXPECTED_EOF_WHILE_READING" in str(e) and attempt < retries - 1:
                time.sleep(1 * (attempt + 1))
                continue
            log(cfg, f"[CLOUD] {method} {node_path} failed: {e}", "WARN")
            return 0, None
    return 0, None


SERVER_TS = {".sv": "timestamp"}


class RarityMap(dict):
    """Rarity info keyed by achievement-title hash; look-ups take the title."""

    def get(self, title, default=None):
        if not title:
            return default
        from_hash = dict.get(self, CloudSync.rarity_key(title))
        return from_hash if from_hash is not None else dict.get(self, title, default)

    def __contains__(self, title):
        return self.get(title) is not None

    def __getitem__(self, title):
        v = self.get(title)
        if v is None:
            raise KeyError(title)
        return v


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

    # Local disk cache TTL for rarity data (seconds). Rarity changes slowly; 1 hour
    # is sufficient to keep comparisons reasonably fresh while drastically reducing
    # cloud read traffic.

    # Notification message shown when a cloud upload is blocked due to missing VPS-ID.

    # Minimum client version enforcement.
    # Cached once per process after the first fetch; None means not yet fetched or fetch failed.
    _min_client_version: Optional[str] = None
    _min_client_version_fetched: bool = False
    _min_client_version_lock = threading.Lock()

    # Once-per-session warning flag for version-blocked write attempts.
    _blocked_warned: bool = False
    _blocked_warned_lock = threading.Lock()

    # Once-per-session warning flag for uploads blocked by a failed integrity check.
    _integrity_warned: bool = False
    _integrity_warned_lock = threading.Lock()

    _claims_lock = threading.Lock()

    @staticmethod
    def fetch_min_client_version(cfg: "AppConfig") -> Optional[str]:
        """Read the minimum required client version from Firebase ``meta/min_client_version``.

        Returns the version string (e.g. ``"3.1"``) or ``None`` when the node
        is absent, the request fails, or the result cannot be parsed.

        The result is cached on the class for the lifetime of the process so
        that the network round-trip is performed at most once per session.
        """
        with CloudSync._min_client_version_lock:
            if CloudSync._min_client_version_fetched:
                return CloudSync._min_client_version
            CloudSync._min_client_version_fetched = True  # mark even on failure

        try:
            if not cfg.CLOUD_URL:
                return None
            status, value = _db_request(cfg, "GET", "meta/min_client_version", timeout=5, retries=1)
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            if value is None:
                CloudSync._min_client_version = None
                return None
            result = str(value).strip().strip('"')
            CloudSync._min_client_version = result if result else None
            return CloudSync._min_client_version
        except Exception as e:
            log(cfg, f"[CLOUD] fetch_min_client_version failed: {e}", "WARN")
            CloudSync._min_client_version = None
            return None

    @staticmethod
    def _is_write_blocked(cfg: "AppConfig") -> bool:
        """Return True (and log once) when writes are blocked due to version enforcement."""
        if getattr(cfg, "_cloud_blocked_by_version", False):
            with CloudSync._blocked_warned_lock:
                if not CloudSync._blocked_warned:
                    log(cfg, "[CLOUD] Upload blocked: client version too old — update the watcher to re-enable cloud writes.", "WARN")
                    CloudSync._blocked_warned = True
            return True
        return False

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

        player_id_lower = player_id.lower()

        # Check 1: the name an existing ID is registered with must match.
        stored_name = CloudSync.fetch_node(cfg, f"players/{player_id_lower}/achievements/name")
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

        # Check 2: the name must not belong to another ID (one read of the name index).
        owner = CloudSync.fetch_node(cfg, f"names/{CloudSync.name_key(player_name)}")
        if isinstance(owner, str) and owner and owner.lower() != player_id_lower:
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
    def name_key(name: str) -> str:
        """Key of a player name in the 'names' index (case-insensitive, unique)."""
        return _FIREBASE_ILLEGAL_CHARS_RE.sub("_", str(name or "").strip().lower())[:32]

    @staticmethod
    def claim_name(cfg: AppConfig, name: str, old_name: str = "") -> bool:
        """Reserve *name* for the own Player ID (and release *old_name*)."""
        pid = str(cfg.OVERLAY.get("player_id", "")).strip().lower()
        key = CloudSync.name_key(name)
        if not pid or not key or key == "player":
            return False
        if not CloudSync._can_write(cfg) or not CloudSync._ensure_owner(cfg):
            return False
        status = CloudSync.write_paths(cfg, {f"names/{key}": pid})
        if status != 200:
            log(cfg, f"[CLOUD] name '{name}' could not be reserved (HTTP {status})", "WARN")
            return False
        old_key = CloudSync.name_key(old_name)
        if old_key and old_key != key:
            if CloudSync.fetch_node(cfg, f"names/{old_key}") == pid:
                CloudSync.write_paths(cfg, {f"names/{old_key}": None})
        return True

    @staticmethod
    def cleanup_legacy_progress(cfg: AppConfig) -> None:
        """Delete cloud progress entries that lack a vps_id (legacy entries uploaded before
        VPS mapping was mandatory).  Runs only once per installation, guarded by a marker file.
        Executes in a background thread to avoid blocking the UI.
        """
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL:
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
                    try:
                        if not CloudSync.set_node(cfg, f"players/{pid}/progress/{rom}", None):
                            raise RuntimeError("rejected")
                        CloudSync.set_node(cfg, f"lb/{rom}/{pid}", None)
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
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL:
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
                    try:
                        if not CloudSync.set_node(cfg, f"players/{pid}/progress/{rom}", None):
                            raise RuntimeError("rejected")
                        log(cfg, f"[CLOUD] Deleted uppercase ROM progress entry: {rom}")
                    except Exception as e:
                        log(cfg, f"[CLOUD] Failed to delete uppercase ROM progress for {rom}: {e}", "WARN")
            except Exception as e:
                log(cfg, f"[CLOUD] cleanup_uppercase_rom_progress error: {e}", "WARN")

        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def upload_achievement_progress(cfg: AppConfig, rom: str, unlocked: int, total: int, bridge: Optional["Bridge"] = None):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not CloudSync._can_write(cfg):
            return
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or total <= 0:
            return
        if unlocked < 0 or unlocked > total:
            log(cfg, f"[CLOUD] upload_achievement_progress blocked for {rom}: implausible {unlocked}/{total}", "WARN")
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
            if not CloudSync._ensure_owner(cfg):
                return
            payload["sts"] = SERVER_TS
            lb_entry = {"n": pname, "u": unlocked, "t": total, "p": percentage, "ts": payload["ts"], "sts": SERVER_TS}
            for src, dst in (("selected_badge", "b"), ("vps_id", "vid"), ("table_name", "tn"),
                             ("version", "ver"), ("author", "au"), ("vps_id_breakdown", "bd")):
                if payload.get(src):
                    lb_entry[dst] = payload[src]
            status = CloudSync.write_paths(cfg, {f"players/{pid}/progress/{rom}": payload,
                                                 f"lb/{rom}/{pid}": lb_entry})
            if status == 200:
                log(cfg, f"[CLOUD] Uploaded Achievement Progress for {rom}: {unlocked}/{total} ({percentage}%)")
            else:
                log(cfg, f"[CLOUD] Progress upload for {rom} rejected (HTTP {status})", "WARN")
        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def fetch_data(cfg: AppConfig, node_path: str) -> list:
        if not cfg.CLOUD_URL or not node_path:
            return []
        status, data = _db_request(cfg, "GET", node_path)
        if status != 200 or not data:
            return []
        if isinstance(data, dict):
            return list(data.values())
        if isinstance(data, list):
            return [x for x in data if x is not None]
        return []

    @staticmethod
    def fetch_node(cfg: AppConfig, node_path: str):
        """Fetch a single Firebase node and return the raw parsed object (dict, list, or None)."""
        if not cfg.CLOUD_URL or not node_path:
            return None
        status, data = _db_request(cfg, "GET", node_path)
        return data if status == 200 else None

    @staticmethod
    def query(cfg: AppConfig, node_path: str, order_by: str, limit_to_last: int = 0,
              limit_to_first: int = 0, start_at=None) -> dict:
        """Ordered query on an indexed node (leaderboards). Returns {key: value}."""
        params = {"orderBy": json.dumps(order_by)}
        if limit_to_last:
            params["limitToLast"] = int(limit_to_last)
        if limit_to_first:
            params["limitToFirst"] = int(limit_to_first)
        if start_at is not None:
            params["startAt"] = json.dumps(start_at)
        status, data = _db_request(cfg, "GET", node_path, params=params)
        return data if (status == 200 and isinstance(data, dict)) else {}

    @staticmethod
    def fetch_parallel(cfg: AppConfig, node_paths: list, max_workers: int = 10) -> dict:
        """Fetch multiple Firebase nodes in parallel. Returns {node_path: data_or_None}."""
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
    def _can_write(cfg: AppConfig, node_path: str = "") -> bool:
        if CloudSync._is_write_blocked(cfg):
            return False
        if not cfg.CLOUD_URL:
            return False
        if node_path and _is_blocked_path(node_path):
            return False
        try:
            from .watcher_io import integrity_upload_blocked
            if integrity_upload_blocked():
                with CloudSync._integrity_warned_lock:
                    if not CloudSync._integrity_warned:
                        log(cfg, "[CLOUD] Upload blocked: a local save file failed its integrity check "
                                 "(restore from cloud or from a backup to re-enable uploads).", "WARN")
                        CloudSync._integrity_warned = True
                return False
        except Exception:
            pass
        return True

    @staticmethod
    def _ensure_owner(cfg: AppConfig) -> bool:
        """Make sure this installation owns the configured Player ID (claims it once)."""
        try:
            from . import cloud_auth
            if not cloud_auth.available():
                return True          # sign-in not configured: legacy behaviour
            pid = str(cfg.OVERLAY.get("player_id", "")).strip().lower()
            if cloud_auth.is_owner(cfg, pid):
                return True
            if getattr(cfg, "_cloud_claim_failed", False):
                return False          # waiting for the recovery key (System → General)
            ok, reason = cloud_auth.claim(cfg, pid)
            if not ok and reason == "owned":
                try:
                    cfg._cloud_claim_failed = True
                except Exception:
                    pass
            return ok
        except Exception as e:
            log(cfg, f"[CLOUD] ownership check failed: {e}", "WARN")
            return False

    @staticmethod
    def write_paths(cfg: AppConfig, updates: dict) -> int:
        """Atomic multi-path update at the database root. Returns the HTTP status (0 = offline)."""
        if not updates:
            return 200
        if any(_is_blocked_path(k) for k in updates):
            return 403
        status, _ = _db_request(cfg, "PATCH", "", updates, retries=2)
        return status

    @staticmethod
    def set_node(cfg: AppConfig, node_path: str, data) -> bool:
        """Write (PUT) data to a node of the own player (or delete with None)."""
        if not CloudSync._can_write(cfg, node_path) or not node_path:
            return False
        if not CloudSync._ensure_owner(cfg):
            return False
        status, _ = _db_request(cfg, "DELETE" if data is None else "PUT", node_path, data)
        if status != 200:
            log(cfg, f"[CLOUD] set_node {node_path} rejected (HTTP {status})", "WARN")
        return status == 200

    @staticmethod
    def patch_node(cfg: AppConfig, node_path: str, data) -> bool:
        """Update (PATCH) fields of a node without deleting unmentioned children."""
        if not CloudSync._can_write(cfg, node_path) or not node_path:
            return False
        if not CloudSync._ensure_owner(cfg):
            return False
        status, _ = _db_request(cfg, "PATCH", node_path, data)
        if status != 200:
            log(cfg, f"[CLOUD] patch_node {node_path} rejected (HTTP {status})", "WARN")
        return status == 200

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
            try:
                from .watcher_io import clear_integrity_failure
                clear_integrity_failure(cfg.BASE)
            except Exception:
                pass
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
    def upload_full_achievements(cfg: AppConfig, state: dict, player_name: str, changed_rom: str = None):
        """Upload the full achievements state (global + session + roms_played) to Firebase
        under /players/{pid}/achievements.json. Called automatically after each session
        and each achievement unlock when cloud sync is enabled.

        When *changed_rom* is provided (achievement unlock): only that ROM's session data
        is uploaded instead of the full session batch, reducing payload from ~150 KB to
        ~5 KB.  The metadata (name, level, badges, etc.) is always uploaded.
        When *changed_rom* is None (session end): the full session batch is uploaded as a
        safety net to ensure all ROMs are in sync.
        """
        if not CloudSync._can_write(cfg):
            return
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL:
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
            metadata_payload["sts"] = SERVER_TS
            if CloudSync.patch_node(cfg, f"players/{pid}/achievements", metadata_payload):
                log(cfg, "[CLOUD] Full achievements metadata uploaded")
            else:
                log(cfg, "[CLOUD] upload_full_achievements: metadata upload failed", "WARN")
            if changed_rom:
                # Single-ROM upload on achievement unlock: only send the changed ROM's
                # session data to keep the payload small (~5 KB instead of ~150 KB).
                rom_entries = session_entries.get(changed_rom)
                if rom_entries:
                    if not CloudSync.set_node(cfg, f"players/{pid}/achievements/session/{changed_rom}", rom_entries):
                        log(cfg, f"[CLOUD] upload_full_achievements: session upload failed for {changed_rom}", "WARN")
            else:
                # Full batch upload on session end (safety net to keep all ROMs in sync).
                session_batch = {rom: entries for rom, entries in session_entries.items() if entries}
                if session_batch:
                    if not CloudSync.patch_node(cfg, f"players/{pid}/achievements/session", session_batch):
                        log(cfg, "[CLOUD] upload_full_achievements: session batch upload failed", "WARN")

            # Global overview entry: number of different achievements unlocked.
            try:
                seen = set()
                for e in global_entries:
                    t = str(e.get("title", "") if isinstance(e, dict) else e).strip()
                    if t:
                        seen.add(t)
                for entries in session_entries.values():
                    for e in entries or []:
                        t = str(e.get("title", "") if isinstance(e, dict) else e).strip()
                        if t:
                            seen.add(t)
                CloudSync.write_paths(cfg, {f"lb_global/{pid}": {
                    "n": pname, "t": len(seen), "b": str(selected_badge or ""),
                    "ts": metadata_payload["ts"], "sts": SERVER_TS}})
            except Exception as e:
                log(cfg, f"[CLOUD] global overview entry failed: {e}", "WARN")

            # Shared rarity counters (each achievement counts once per player).
            roms = [changed_rom] if changed_rom else list(session_entries.keys())
            for rom in roms:
                titles = [str(e.get("title", "") if isinstance(e, dict) else e) for e in (session_entries.get(rom) or [])]
                if titles:
                    CloudSync.contribute_rarity(cfg, rom, titles)

        threading.Thread(target=_task, daemon=True).start()

    # ── Rarity (shared counters, VPX Achievement Watcher 3.2+) ─────────────
    #
    # rarity/<key>/players      – players with at least one achievement there
    # rarity/<key>/c/<hash>     – players that unlocked the achievement <hash>
    # rarity_claims/<key>/<pid>/<hash|_p> – what this player already counted
    #
    # <key> is the ROM name, or "cat_<firebase_key>" for custom tables.
    # Each player adds +1 once per achievement; the database rules enforce it.

    _RARITY_DISK_CACHE_TTL_SEC: int = 24 * 3600

    @staticmethod
    def rarity_key(title: str) -> str:
        import hashlib
        return hashlib.sha1(str(title or "").strip().encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _rarity_from_counts(node) -> tuple:
        node = node if isinstance(node, dict) else {}
        total = int(node.get("players") or 0)
        result = RarityMap()
        for k, n in (node.get("c") or {}).items():
            try:
                dict.__setitem__(result, k, compute_rarity(int(n), total))
            except Exception:
                continue
        return result, total

    @staticmethod
    def _fetch_rarity(cfg: AppConfig, key: str) -> tuple:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
        cache_dir = os.path.join(cfg.BASE, "tools", "rarity_cache")
        cache_file = os.path.join(cache_dir, f"{safe}.json")
        try:
            if os.path.isfile(cache_file) and time.time() - os.path.getmtime(cache_file) < CloudSync._RARITY_DISK_CACHE_TTL_SEC:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if isinstance(cached, dict) and "c" in cached:
                    return CloudSync._rarity_from_counts(cached)
        except Exception:
            pass
        status, node = _db_request(cfg, "GET", f"rarity/{key}")
        if status != 200:
            return RarityMap(), 0
        node = node if isinstance(node, dict) else {"players": 0, "c": {}}
        try:
            ensure_dir(cache_dir)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"players": node.get("players") or 0, "c": node.get("c") or {}}, f)
        except Exception:
            pass
        return CloudSync._rarity_from_counts(node)

    @staticmethod
    def fetch_rarity_for_rom(cfg: AppConfig, rom: str) -> tuple:
        """({title: {tier, color, pct}}, total_players) for a ROM – one small read per day."""
        if not rom:
            return RarityMap(), 0
        return CloudSync._fetch_rarity(cfg, rom)

    @staticmethod
    def fetch_rarity_for_cat(cfg: AppConfig, firebase_key: str) -> tuple:
        """Same as fetch_rarity_for_rom for a custom achievement table."""
        if not firebase_key:
            return RarityMap(), 0
        return CloudSync._fetch_rarity(cfg, f"cat_{firebase_key}")

    @staticmethod
    def _claims_cache_file(cfg: AppConfig) -> str:
        return os.path.join(cfg.BASE, "tools", "rarity_claims.json")

    @staticmethod
    def contribute_rarity(cfg: AppConfig, key: str, titles) -> None:
        """Count this player's unlocked *titles* once in the shared rarity counters."""
        try:
            from . import cloud_auth
            if not cloud_auth.available() or not key:
                return
            pid = str(cfg.OVERLAY.get("player_id", "")).strip().lower()
            if not pid or not CloudSync._can_write(cfg) or not CloudSync._ensure_owner(cfg):
                return
            hashes = sorted({CloudSync.rarity_key(t) for t in (titles or []) if str(t or "").strip()})
            if not hashes:
                return
            with CloudSync._claims_lock:
                cache_path = CloudSync._claims_cache_file(cfg)
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cache = json.load(f)
                except Exception:
                    cache = {}
                mine = cache.get(pid) if isinstance(cache.get(pid), dict) else {}
                done = set(mine.get(key) or [])
                if key not in mine:
                    status, claimed = _db_request(cfg, "GET", f"rarity_claims/{key}/{pid}", params={"shallow": "true"})
                    if status != 200:
                        return
                    done = set((claimed or {}).keys()) if isinstance(claimed, dict) else set()
                todo = [h for h in hashes if h not in done]
                need_player = "_p" not in done
                if not todo and not need_player:
                    mine[key] = sorted(done); cache[pid] = mine
                    save_json(cache_path, cache)
                    return
                ok = False
                for _attempt in range(4):
                    status, node = _db_request(cfg, "GET", f"rarity/{key}")
                    if status != 200:
                        break
                    node = node if isinstance(node, dict) else {}
                    counts = node.get("c") or {}
                    upd = {}
                    for h in todo:
                        upd[f"rarity/{key}/c/{h}"] = int(counts.get(h) or 0) + 1
                        upd[f"rarity_claims/{key}/{pid}/{h}"] = True
                    if need_player:
                        upd[f"rarity/{key}/players"] = int(node.get("players") or 0) + 1
                        upd[f"rarity_claims/{key}/{pid}/_p"] = True
                    if CloudSync.write_paths(cfg, upd) == 200:
                        ok = True
                        break
                    time.sleep(0.5 + _attempt)   # another player counted at the same time
                if ok:
                    done.update(todo)
                    done.add("_p")
                    mine[key] = sorted(done); cache[pid] = mine
                    save_json(cache_path, cache)
                    log(cfg, f"[CLOUD] rarity: counted {len(todo)} achievement(s) for {key}")
        except Exception as e:
            log(cfg, f"[CLOUD] rarity contribution failed for {key}: {e}", "WARN")

    # ── Leaderboards (small index, read with a top-N query) ────────────────

    LB_TOP_ROM = 25
    LB_TOP_GLOBAL = 50

    @staticmethod
    def fetch_lb_top(cfg: AppConfig, node: str, order_by: str, top: int) -> list:
        """[(pid, entry)] best first."""
        data = CloudSync.query(cfg, node, order_by, limit_to_last=top)
        rows = [(k, v) for k, v in data.items() if isinstance(v, dict)]
        rows.sort(key=lambda kv: float(kv[1].get(order_by) or 0), reverse=True)
        return rows

    @staticmethod
    def fetch_lb_rank(cfg: AppConfig, node: str, order_by: str, pid: str, cap: int = 100) -> tuple:
        """(rank or None, own entry or None). Rank is None when it is worse than *cap*."""
        pid = (pid or "").strip().lower()
        own = CloudSync.fetch_node(cfg, f"{node}/{pid}") if pid else None
        if not isinstance(own, dict):
            return None, None
        mine = float(own.get(order_by) or 0)
        better = CloudSync.query(cfg, node, order_by, start_at=mine, limit_to_first=cap + 1)
        above = sum(1 for k, v in better.items()
                    if k != pid and isinstance(v, dict) and float(v.get(order_by) or 0) > mine)
        if len(better) > cap and above >= cap:
            return None, own
        return above + 1, own

    @staticmethod
    def lb_to_progress(entry: dict) -> dict:
        """Leaderboard index entry -> the progress-entry format the views use."""
        e = entry or {}
        out = {"name": e.get("n", ""), "unlocked": e.get("u", 0), "total": e.get("t", 0),
               "percentage": e.get("p", 0), "ts": e.get("ts", ""), "selected_badge": e.get("b", "")}
        for src, dst in (("vid", "vps_id"), ("tn", "table_name"), ("ver", "version"),
                         ("au", "author"), ("bd", "vps_id_breakdown"), ("dn", "display_name")):
            if e.get(src):
                out[dst] = e[src]
        return out

    @staticmethod
    def _top_with_own(cfg: AppConfig, node: str, order_by: str, top: int) -> list:
        rows = CloudSync.fetch_lb_top(cfg, node, order_by, top)
        pid = str(cfg.OVERLAY.get("player_id", "")).strip().lower()
        out = [dict(v, _pid=k) for k, v in rows]
        if pid and pid not in {k for k, _ in rows}:
            rank, own = CloudSync.fetch_lb_rank(cfg, node, order_by, pid, cap=1000)
            if isinstance(own, dict):
                out.append(dict(own, _pid=pid, _rank=rank or 0))
        return out

    @staticmethod
    def fetch_rom_leaderboard(cfg: AppConfig, rom: str) -> list:
        """Top 25 of a ROM (+ own entry), in the progress-entry format."""
        out = []
        for e in CloudSync._top_with_own(cfg, f"lb/{rom}", "p", CloudSync.LB_TOP_ROM):
            row = CloudSync.lb_to_progress(e)
            if e.get("_rank") is not None and "_rank" in e:
                row["_rank"] = e["_rank"] or ">1000"
            out.append(row)
        return out

    @staticmethod
    def fetch_cat_leaderboard(cfg: AppConfig, firebase_key: str) -> list:
        out = []
        for e in CloudSync._top_with_own(cfg, f"lb_cat/{firebase_key}", "p", CloudSync.LB_TOP_ROM):
            row = CloudSync.lb_to_progress(e)
            if "_rank" in e:
                row["_rank"] = e["_rank"] or ">1000"
            out.append(row)
        return out

    @staticmethod
    def fetch_global_leaderboard(cfg: AppConfig) -> list:
        """Top 50 by number of different achievements (+ own entry)."""
        out = []
        for e in CloudSync._top_with_own(cfg, "lb_global", "t", CloudSync.LB_TOP_GLOBAL):
            row = {"name": e.get("n", ""), "badge_id": e.get("b", ""), "total": int(e.get("t") or 0)}
            if "_rank" in e:
                row["_rank"] = e["_rank"] or ">1000"
            if row["total"] > 0:
                out.append(row)
        return out

    @staticmethod
    def fetch_player_ids(cfg: AppConfig) -> list:
        """No longer available (the player list is not readable any more)."""
        return []




