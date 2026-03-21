from __future__ import annotations

import json
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from vpx_achievement_watcher.core.config import AppConfig
from vpx_achievement_watcher.core.helpers import log, compute_player_level
from vpx_achievement_watcher.core.paths import f_achievements_state
from vpx_achievement_watcher.utils.json_io import secure_load_json
from vpx_achievement_watcher.utils.version import WATCHER_VERSION

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
    def upload_score(cfg: AppConfig, category: str, rom: str, score: int, extra_data: dict = None, bridge: Optional["Bridge"] = None):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or score <= 0:
            return
        if not cfg.CLOUD_BACKUP_ENABLED:
            return
        if CloudSync._warn_missing_player_name(cfg):
            return
        # Block upload if no VPS-ID assigned for this ROM
        try:
            from ui_vps import _load_vps_mapping
            _vps_mapping = _load_vps_mapping(cfg)
            _vps_id = (_vps_mapping.get(rom) or "").strip()
            if not _vps_id:
                log(cfg, f"[CLOUD] upload_score blocked for {rom}: no VPS-ID assigned", "WARN")
                return
            # Inject vps_id into extra_data so it gets included in the payload
            if extra_data is None:
                extra_data = {}
            extra_data = dict(extra_data)
            extra_data.setdefault("vps_id", _vps_id)
            # Enrich extra_data with VPS table metadata (table_name, author, version)
            try:
                from ui_vps import _load_vpsdb
                tables = _load_vpsdb(cfg)
                if tables:
                    for t in tables:
                        vps_entry = None
                        tf_entry = None
                        if t.get("id") == _vps_id:
                            vps_entry = t
                        else:
                            for tf in (t.get("tableFiles") or []):
                                if tf.get("id") == _vps_id:
                                    vps_entry = t
                                    tf_entry = tf
                                    break
                        if vps_entry:
                            table_name = vps_entry.get("name", "")
                            if table_name:
                                extra_data["table_name"] = table_name
                            if tf_entry:
                                version = tf_entry.get("version", "")
                                authors = tf_entry.get("authors") or []
                                if version:
                                    extra_data["version"] = version
                                if authors:
                                    extra_data["author"] = ", ".join(authors)
                            break
            except Exception:
                pass
        except Exception as e:
            log(cfg, f"[CLOUD] upload_score blocked for {rom}: VPS mapping error: {e}", "WARN")
            return
        
        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip()
        if not pid or pid == "unknown":
            log(cfg, f"[CLOUD] upload_score blocked for {rom}: no valid player_id", "WARN")
            return

        rom_key = rom
        if extra_data:
            if category == "flip" and "target_flips" in extra_data:
                rom_key = f"{rom}_f{extra_data['target_flips']}"
            elif category == "time" and "target_time" in extra_data:
                rom_key = f"{rom}_t{extra_data['target_time']}"
            elif "difficulty" in extra_data:
                clean_diff = str(extra_data["difficulty"]).replace(" ", "")
                rom_key = f"{rom}_{clean_diff}"

        # Client-side dedup: skip if an identical (pid, category, rom_key, score) was already
        # submitted within the dedup window to reduce accidental replay uploads.
        _dedup_key = f"{pid}|{category}|{rom_key}|{score}"
        _now = time.time()
        with CloudSync._recent_score_uploads_lock:
            # Prune expired entries to prevent unbounded growth over long sessions.
            _cutoff = _now - CloudSync._DEDUP_WINDOW_SEC
            CloudSync._recent_score_uploads = {
                k: v for k, v in CloudSync._recent_score_uploads.items() if v > _cutoff
            }
            _last_ts = CloudSync._recent_score_uploads.get(_dedup_key, 0.0)
            if _now - _last_ts < CloudSync._DEDUP_WINDOW_SEC:
                log(cfg, f"[CLOUD] upload_score skipped: identical score {score} for {rom_key} "
                         f"(duplicate within {CloudSync._DEDUP_WINDOW_SEC:.0f}s window)")
                return
            CloudSync._recent_score_uploads[_dedup_key] = _now

        endpoint = f"{url}/players/{pid}/scores/{category}/{rom_key}.json"
        
        def _task():
            try:
                req = urllib.request.Request(endpoint)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                if data and isinstance(data, dict):
                    if score <= int(data.get("score", 0)):
                        return
            except Exception:
                pass 
            
            payload = {"name": pname, "score": score, "ts": datetime.now(timezone.utc).isoformat(), "watcher_version": WATCHER_VERSION}
            if extra_data: payload.update(extra_data)
                
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=5) as resp:
                    resp_body = resp.read().decode()
                    log(cfg, f"[CLOUD] Uploaded {category.upper()} Score for {rom}: {score}")
                    CloudSync._emit_submission_state(cfg, resp_body, bridge)
            except Exception as e:
                log(cfg, f"[CLOUD] Upload failed: {e}", "WARN")
                
        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def upload_achievement_progress(cfg: AppConfig, rom: str, unlocked: int, total: int, bridge: Optional["Bridge"] = None):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or total <= 0:
            return
        if not cfg.CLOUD_BACKUP_ENABLED:
            return
        if CloudSync._warn_missing_player_name(cfg):
            return
        # Block upload if no VPS-ID assigned for this ROM
        try:
            from ui_vps import _load_vps_mapping
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
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip()
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
                log(cfg, f"[CLOUD] upload_achievement_progress skipped: same payload for {rom} "
                         f"({unlocked}/{total}) (duplicate within {CloudSync._DEDUP_WINDOW_SEC:.0f}s window)")
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
                "watcher_version": WATCHER_VERSION,
            }
            if _extra_vps_id:
                payload["vps_id"] = _extra_vps_id
                try:
                    from ui_vps import _load_vpsdb
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
        try:
            import urllib.request
            import ssl
            req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
                raw_data = resp.read().decode('utf-8')
                data = json.loads(raw_data)
            if not data: return []
            if isinstance(data, dict): return list(data.values())
            elif isinstance(data, list): return [x for x in data if x is not None]
            return []
        except Exception as e:
            log(cfg, f"[CLOUD] Fetch error for {endpoint}: {e}", "ERROR")
            return []

    @staticmethod
    def fetch_player_ids(cfg: AppConfig) -> list:
        """Return the list of all player IDs stored under /players/ using a shallow fetch."""
        if not cfg.CLOUD_URL:
            return []
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/players.json?shallow=true"
        try:
            import urllib.request
            import ssl
            req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if isinstance(data, dict):
                return list(data.keys())
            return []
        except Exception as e:
            log(cfg, f"[CLOUD] fetch_player_ids error: {e}", "ERROR")
            return []

    @staticmethod
    def fetch_node(cfg: AppConfig, node_path: str):
        """Fetch a single Firebase node and return the raw parsed object (dict, list, or None)."""
        if not cfg.CLOUD_URL or not node_path:
            return None
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        try:
            import urllib.request
            import ssl
            req = urllib.request.Request(endpoint, headers={"User-Agent": "AchievementWatcher/2.0"})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
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
        """Write (PUT) arbitrary data to a Firebase node. Returns True on success."""
        if not cfg.CLOUD_URL or not node_path:
            return False
        url = cfg.CLOUD_URL.strip().rstrip('/')
        endpoint = f"{url}/{node_path}.json"
        try:
            import ssl
            payload = json.dumps(data).encode('utf-8')
            put_req = urllib.request.Request(endpoint, data=payload, method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(put_req, timeout=10, context=ctx) as resp:
                pass
            return True
        except Exception as e:
            log(cfg, f"[CLOUD] set_node error for {endpoint}: {e}", "WARN")
            return False

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
        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip()
        endpoint = f"{url}/players/{pid}/achievements.json"

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
            payload = {
                "name": pname,
                "ts": datetime.now(timezone.utc).isoformat(),
                "watcher_version": WATCHER_VERSION,
                "global": global_entries,
                "session": session_entries,
                "roms_played": roms_played,
                "player_level": lv["level"],
                "player_level_name": lv["name"],
            }
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=10) as resp:
                    log(cfg, f"[CLOUD] Uploaded full achievements for player {pid}")
            except Exception as e:
                log(cfg, f"[CLOUD] upload_full_achievements failed: {e}", "WARN")

        threading.Thread(target=_task, daemon=True).start()


