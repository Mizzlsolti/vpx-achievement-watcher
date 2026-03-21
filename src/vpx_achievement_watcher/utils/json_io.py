from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime


def _raw_load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _raw_save_json(path, obj):
    from vpx_achievement_watcher.core.helpers import ensure_dir
    tmp = None
    try:
        ensure_dir(os.path.dirname(path))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.flush()
        try:
            os.replace(tmp, path)
        except Exception:
            os.rename(tmp, path)
        return True
    except Exception:
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False

# ==========================================
# ANTI-CHEAT SECURITY
# ==========================================
LEGACY_SALT = "VPX_S3cr3t_H4sh_9921!"
BASE_SALT = "VpX_W@tcher_2024!"

def _generate_legacy_signature(data: dict) -> str:
    d = dict(data)
    d.pop("_signature", None)
    s = json.dumps(d, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256((s + LEGACY_SALT).encode('utf-8')).hexdigest()

def _generate_signature(data: dict) -> str:
    d = dict(data)
    d.pop("_signature", None)
    
    score_val = str(d.get("score", "0"))
    duration_val = str(d.get("duration", "0"))
    session_val = str(d.get("session_id", "none"))
    
    dynamic_salt = f"{score_val}_{duration_val}_{session_val}_{BASE_SALT}"
    s = json.dumps(d, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256((s + dynamic_salt).encode('utf-8')).hexdigest()

def _is_secure_path(path: str) -> bool:
    """Prüft, ob eine Datei durch Anti-Cheat geschützt werden soll."""
    if not path: return False
    p = path.lower().replace("\\", "/")

    if p.endswith("config.json"): return False
    if "nvram_maps" in p: return False
    if "custom_achievements" in p: return False
    if p.endswith("index.json") or p.endswith("romnames.json"): return False
    
    if not p.endswith(".json"): return False
    
    return True

def load_json(path, default=None):
    data = _raw_load_json(path, None)
    if data is None:
        return default
        
    if _is_secure_path(path) and isinstance(data, dict):
        sig = data.pop("_signature", None)
        if not sig:
            print(f"\n[SECURITY] NO SIGNATURE FOUND IN: {path}")
            print("[SECURITY] The file has been blocked and will not be loaded!\n")
            return default
            
        expected_new = _generate_signature(data)
        expected_legacy = _generate_legacy_signature(data)
        
        if sig == expected_new:
            # File is already on the new security standard
            data["_signature"] = sig
        elif sig == expected_legacy:
            # File is using the old security standard - allow it to load
            print(f"[SECURITY] Legacy save file detected: {path}. Access granted. Upgrading immediately.")
            data["_signature"] = sig
            save_json(path, data)
        else:
            print(f"\n[SECURITY] TAMPERING DETECTED IN: {path}")
            print("[SECURITY] The file has been blocked and will not be loaded!\n")
            return default
            
    return data

def save_json(path, obj):
    if _is_secure_path(path) and isinstance(obj, dict):
        try:
            obj["_signature"] = _generate_signature(obj)
        except Exception:
            pass
    return _raw_save_json(path, obj)

secure_save_json = save_json
secure_load_json = load_json

def write_text(path, text):
    from vpx_achievement_watcher.core.helpers import ensure_dir
    tmp = None
    try:
        ensure_dir(os.path.dirname(path))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass
        try:
            os.replace(tmp, path)
        except Exception:
            os.rename(tmp, path)
        return True
    except Exception:
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False

def _is_weird_value(x: int) -> bool:
    try:
        return abs(int(x)) >= 400_000_000
    except Exception:
        return False
