from __future__ import annotations

import json
import threading
import urllib.request
from datetime import datetime, timezone

from config import AppConfig, log

# ---------------------------------------------------------------------------
# Cloud synchronisation
# ---------------------------------------------------------------------------

class CloudSync:
    @staticmethod
    def upload_score(cfg: AppConfig, category: str, rom: str, score: int, extra_data: dict = None):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or score <= 0 or not pname or pname.lower() == "player":
            return

        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = str(cfg.OVERLAY.get("player_id", "unknown")).strip()

        pid_key = f"p_{pid}"
        if extra_data:
            if category == "flip" and "target_flips" in extra_data:
                pid_key = f"p_{pid}_f{extra_data['target_flips']}"
            elif category == "time" and "target_time" in extra_data:
                pid_key = f"p_{pid}_t{extra_data['target_time']}"
            elif "difficulty" in extra_data:
                clean_diff = str(extra_data["difficulty"]).replace(" ", "")
                pid_key = f"p_{pid}_{clean_diff}"

        endpoint = f"{url}/scores/{category}/{rom}/{pid_key}.json"

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

            payload = {"name": pname, "score": score, "ts": datetime.now(timezone.utc).isoformat()}
            if extra_data: payload.update(extra_data)

            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=5) as resp:
                    log(cfg, f"[CLOUD] Uploaded {category.upper()} Score for {rom}: {score}")
            except Exception as e:
                log(cfg, f"[CLOUD] Upload failed: {e}", "WARN")

        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def upload_achievement_progress(cfg: AppConfig, rom: str, unlocked: int, total: int):
        pname = cfg.OVERLAY.get("player_name", "Player").strip()
        if not cfg.CLOUD_ENABLED or not cfg.CLOUD_URL or not rom or total <= 0 or not pname or pname.lower() == "player":
            return

        url = cfg.CLOUD_URL.strip().rstrip('/')
        pid = cfg.OVERLAY.get("player_id", "unknown")
        endpoint = f"{url}/progress/{rom}/{pid}.json"

        def _task():
            percentage = round((unlocked / total) * 100, 1)
            payload = {
                "name": pname,
                "unlocked": unlocked,
                "total": total,
                "percentage": percentage,
                "ts": datetime.now(timezone.utc).isoformat()
            }
            put_req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), method='PUT')
            put_req.add_header('Content-Type', 'application/json')
            try:
                with urllib.request.urlopen(put_req, timeout=5) as resp:
                    log(cfg, f"[CLOUD] Uploaded Achievement Progress for {rom}: {unlocked}/{total} ({percentage}%)")
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
