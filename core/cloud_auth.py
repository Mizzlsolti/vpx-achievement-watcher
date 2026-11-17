"""Cloud identity: anonymous Firebase sign-in and Player-ID ownership.

Every Watcher signs in anonymously (no user input). The first sign-in that
claims a Player ID owns it; the database rules only let that sign-in write
under ``players/<id>`` and the leaderboard/rarity entries of that ID.

A random *recovery key* is created with the claim. It is stored locally (and
in the ZIP backup) and moves the Player ID to another installation, e.g. a
new PC: a new sign-in may take over an ID only with the same key.

Files: ``<BASE>/cloud_identity.json`` – {uid, refresh_token, pid, key}
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional, Tuple

# Web API key of the Firebase project (not a secret – it only names the project).
FIREBASE_API_KEY = "AIzaSyAZ9SeiU90dSS0rHK1tETOkA07YvcqAMK8"

_AUTH_HOST = "https://identitytoolkit.googleapis.com"
_TOKEN_HOST = "https://securetoken.googleapis.com"

_lock = threading.RLock()
_state: dict = {}          # cached identity file contents
_id_token: str = ""
_id_token_exp: float = 0.0
_state_base: str = ""


def _api_key() -> str:
    return os.environ.get("VPXAW_FIREBASE_API_KEY") or FIREBASE_API_KEY


def _hosts() -> Tuple[str, str]:
    emu = os.environ.get("VPXAW_AUTH_EMULATOR", "").strip()
    if emu:
        return (f"http://{emu}/identitytoolkit.googleapis.com", f"http://{emu}/securetoken.googleapis.com")
    return (_AUTH_HOST, _TOKEN_HOST)


def available() -> bool:
    """True when cloud sign-in is configured (API key known)."""
    return bool(_api_key())


def _identity_path(cfg) -> str:
    return os.path.join(cfg.BASE, "cloud_identity.json")


def _load(cfg) -> dict:
    global _state, _state_base
    with _lock:
        if _state_base == cfg.BASE and _state:
            return _state
        try:
            with open(_identity_path(cfg), "r", encoding="utf-8") as f:
                data = json.load(f)
            _state = data if isinstance(data, dict) else {}
        except Exception:
            _state = {}
        _state_base = cfg.BASE
        return _state


def _save(cfg) -> None:
    with _lock:
        path = _identity_path(cfg)
        tmp = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_state, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass


def _http_json(cfg, url: str, body: bytes, content_type: str, timeout: int = 10) -> dict:
    from .cloud_sync import _urlopen_ssl_aware
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    with _urlopen_ssl_aware(cfg, req, timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _sign_up(cfg) -> None:
    global _id_token, _id_token_exp
    auth_host, _ = _hosts()
    data = _http_json(cfg, f"{auth_host}/v1/accounts:signUp?key={_api_key()}",
                      b'{"returnSecureToken":true}', "application/json")
    _state["uid"] = data["localId"]
    _state["refresh_token"] = data["refreshToken"]
    _id_token = data["idToken"]
    _id_token_exp = time.time() + int(data.get("expiresIn", 3600)) - 120
    _save(cfg)


def _refresh(cfg) -> None:
    global _id_token, _id_token_exp
    _, token_host = _hosts()
    body = urllib.parse.urlencode({"grant_type": "refresh_token",
                                   "refresh_token": _state.get("refresh_token", "")}).encode()
    data = _http_json(cfg, f"{token_host}/v1/token?key={_api_key()}", body,
                      "application/x-www-form-urlencoded")
    _state["uid"] = data.get("user_id") or _state.get("uid")
    if data.get("refresh_token"):
        _state["refresh_token"] = data["refresh_token"]
    _id_token = data["id_token"]
    _id_token_exp = time.time() + int(data.get("expires_in", 3600)) - 120
    _save(cfg)


def get_token(cfg) -> str:
    """A valid ID token for database requests ('' when sign-in is unavailable)."""
    from .watcher_core import log
    if not available():
        return ""
    with _lock:
        _load(cfg)
        if _id_token and time.time() < _id_token_exp:
            return _id_token
        try:
            if _state.get("refresh_token"):
                try:
                    _refresh(cfg)
                    return _id_token
                except Exception as e:
                    log(cfg, f"[CLOUD-AUTH] token refresh failed, signing in again: {e}", "WARN")
            _sign_up(cfg)
            return _id_token
        except Exception as e:
            log(cfg, f"[CLOUD-AUTH] sign-in failed: {e}", "WARN")
            return ""


def uid(cfg) -> str:
    return str(_load(cfg).get("uid") or "")


def recovery_key(cfg) -> str:
    return str(_load(cfg).get("key") or "")


def claimed_pid(cfg) -> str:
    return str(_load(cfg).get("pid") or "")


def set_recovery_key(cfg, key: str) -> None:
    with _lock:
        _load(cfg)
        _state["key"] = (key or "").strip()
        _save(cfg)


def claim(cfg, pid: str, key: Optional[str] = None) -> Tuple[bool, str]:
    """Bind *pid* to this installation.

    Returns (ok, reason). reason: 'ok' | 'owned' (another installation owns
    the ID – the recovery key is needed) | 'offline' | 'unavailable'.
    """
    from .cloud_sync import CloudSync
    from .watcher_core import log
    pid = (pid or "").strip().lower()
    if not pid or pid == "unknown":
        return False, "unavailable"
    tok = get_token(cfg)
    if not tok:
        return False, "unavailable" if not available() else "offline"
    with _lock:
        st = _load(cfg)
        my_uid = st.get("uid") or ""
        if st.get("pid") == pid and st.get("claimed_uid") == my_uid and st.get("key"):
            return True, "ok"
        use_key = (key or st.get("key") or "").strip()
        new_key = use_key or secrets.token_urlsafe(24)
        status = CloudSync.write_paths(cfg, {
            f"owners/{pid}": {"uid": my_uid, "key": new_key},
            f"uids/{my_uid}": pid,
        })
        if status == 200:
            st["pid"] = pid
            st["key"] = new_key
            st["claimed_uid"] = my_uid
            _save(cfg)
            log(cfg, f"[CLOUD-AUTH] Player ID '{pid}' is linked to this installation")
            return True, "ok"
        if status in (401, 403):
            log(cfg, f"[CLOUD-AUTH] Player ID '{pid}' belongs to another installation – recovery key needed", "WARN")
            return False, "owned"
        return False, "offline"


def is_owner(cfg, pid: str) -> bool:
    st = _load(cfg)
    return bool(st.get("pid") == (pid or "").strip().lower() and st.get("claimed_uid")
                and st.get("claimed_uid") == st.get("uid"))
