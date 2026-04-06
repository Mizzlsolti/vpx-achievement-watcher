from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import ctypes
import ssl
from datetime import datetime
from urllib.request import Request, urlopen

try:
    import requests
except Exception:
    requests = None

from .config import (
    APP_DIR,
    AppConfig,
    DEFAULT_LOG_SUPPRESS,
    f_log,
)

# ---------------------------------------------------------------------------
# PyInstaller path helper
# ---------------------------------------------------------------------------

def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.isdir(base):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    return os.path.join(APP_DIR, rel)


# ---------------------------------------------------------------------------
# ROM-name helpers
# ---------------------------------------------------------------------------

def _strip_version_from_name(name: str) -> str:
    """Remove all trailing parenthesised/bracketed suffixes and bare version numbers.

    Examples:
        "Medieval Madness (Williams)"             -> "Medieval Madness"
        "AC/DC (Premium) (V1.13b)"                -> "AC/DC"
        "Theatre of Magic [VPX]"                  -> "Theatre of Magic"
        "Attack from Mars (Remake) (2.0)"         -> "Attack from Mars"
        "Shovel Knight (Original 2017) v1.2.1"    -> "Shovel Knight"
    """
    result = name
    while True:
        # Use separate patterns for each delimiter type to avoid matching
        # unbalanced pairs such as "(Name]".
        stripped = re.sub(r"\s*\([^\)]*\)\s*$", "", result, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"\s*\[[^\]]*\]\s*$", "", stripped, flags=re.IGNORECASE).strip()
        # Also strip trailing bare version numbers such as "v1.2.1", "v2.0", "v1.2.1-beta"
        stripped = re.sub(r"\s+v\d+(?:\.\d+)*(?:[.-]\S+)?$", "", stripped, flags=re.IGNORECASE).strip()
        if stripped == result:
            break
        result = stripped
    return result


# Alias used by callers that want to strip all parenthesised/bracketed suffixes.
_clean_table_name = _strip_version_from_name


def _is_valid_rom_name(rom: str) -> bool:
    """Return True if *rom* is a valid VPinMAME ROM name (only [A-Za-z0-9_]).

    Custom achievement table names (e.g. "Blood Machines (Original 2022)") contain
    spaces and special characters and must never be used as Firebase path segments.
    """
    return bool(rom and re.fullmatch(r"[A-Za-z0-9_]+", rom))


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch_json_url(url: str, timeout: int = 25) -> dict:
    ua = "AchievementWatcher/1.0 (+https://github.com/Mizzlsolti)"
    if requests:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": ua})
        r.raise_for_status()
        return r.json()
    req = Request(url, headers={"User-Agent": ua})
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        raw = resp.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return json.loads(raw)


def _fetch_bytes_url(url: str, timeout: int = 25) -> bytes:
    ua = "AchievementWatcher/1.0 (+https://github.com/Mizzlsolti)"
    if requests:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": ua})
        r.raise_for_status()
        return r.content
    req = Request(url, headers={"User-Agent": ua})
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        return resp.read()


# ---------------------------------------------------------------------------
# VPXTool helpers
# ---------------------------------------------------------------------------

VPXTOOL_EXE = "vpxtool.exe"
VPXTOOL_DIRNAME = "tools"
VPXTOOL_PATH = os.path.join(APP_DIR, VPXTOOL_DIRNAME, VPXTOOL_EXE)
VPXTOOL_URL = "https://github.com/francisdb/vpxtool/releases/download/v0.26.0/vpxtool-Windows-x86_64-v0.26.0.zip"


def ensure_vpxtool(cfg: AppConfig) -> str | None:
    import zipfile
    import io
    try:
        if os.path.isfile(VPXTOOL_PATH):
            return VPXTOOL_PATH

        log(cfg, f"[VPXTOOL] Download from {VPXTOOL_URL}...")
        data = _fetch_bytes_url(VPXTOOL_URL, timeout=30)
        ensure_dir(os.path.dirname(VPXTOOL_PATH))

        with zipfile.ZipFile(io.BytesIO(data)) as z:
            with open(VPXTOOL_PATH, "wb") as f:
                f.write(z.read("vpxtool.exe"))

        try:
            os.chmod(VPXTOOL_PATH, 0o755)
        except Exception:
            pass

        log(cfg, f"[VPXTOOL] Successfully downloaded and unzipped -> {VPXTOOL_PATH}")
        return VPXTOOL_PATH
    except Exception as e:
        log(cfg, f"[VPXTOOL] download failed: {e}", "ERROR")
        return None


def run_vpxtool_get_rom(cfg: AppConfig, vpx_path: str, suppress_warn: bool = False) -> str | None:

    if not vpx_path or not os.path.isfile(vpx_path):
        return None

    exe = ensure_vpxtool(cfg)
    if not exe:
        return None
    try:
        key = os.path.abspath(vpx_path).lower()
    except Exception:
        key = str(vpx_path)
    if not hasattr(run_vpxtool_get_rom, "_warned_keys"):
        run_vpxtool_get_rom._warned_keys = set()
    warned = run_vpxtool_get_rom._warned_keys

    cmd = [exe, "romname", vpx_path]
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=0x08000000
        )
        out = ((cp.stdout or "") + "\n" + (cp.stderr or "")).strip()

        if cp.returncode != 0:
            if key not in warned:
                if not suppress_warn:
                    log(cfg, f"[VPXTOOL] romname failed rc={cp.returncode}: {out}", "WARN")
                warned.add(key)
            return None

        lines = (cp.stdout or "").strip().splitlines()
        if lines:
            rom = lines[-1].strip().strip('"').strip("'")
            if re.fullmatch(r"[A-Za-z0-9_]+", rom or ""):
                if key in warned:
                    warned.discard(key)
                return rom.lower()

        m = re.search(r"\b([A-Za-z0-9_]{2,})\b", out)
        if m:
            if key in warned:
                warned.discard(key)
            return m.group(1).lower()

        if key not in warned:
            if not suppress_warn:
                log(cfg, f"[VPXTOOL] romname returned no parsable output: {out}", "WARN")
            warned.add(key)
        return None

    except Exception as e:
        if key not in warned:
            if not suppress_warn:
                log(cfg, f"[VPXTOOL] romname exception: {e}", "WARN")
            warned.add(key)
        return None


def run_vpxtool_get_script_authors(cfg: "AppConfig", vpx_path: str) -> list:
    """
    Runs: vpxtool script show "<vpx_path>"
    Parses the VBS script output for author names from comment lines.
    Returns a list of author name strings (possibly empty).
    No logging — silent failure is OK.
    """
    if not vpx_path or not os.path.isfile(vpx_path):
        return []

    exe = ensure_vpxtool(cfg)
    if not exe:
        return []

    cmd = [exe, "script", "show", vpx_path]
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=0x08000000,
            encoding="utf-8",
            errors="replace",
        )
        script = cp.stdout or ""
        return _parse_authors_from_script(script)
    except Exception:
        return []


def run_vpxtool_info_show(cfg: "AppConfig", vpx_path: str) -> dict:
    """
    Runs: vpxtool info show "<vpx_path>"
    Parses the human-readable key: value output into a dict.
    Returns a dict with keys like 'table_name', 'version', 'author', 'release_date',
    'description', 'blurb', 'rules', 'save_revision', 'save_date', 'vpx_version'.
    Returns {} on any failure (silent).
    """
    if not vpx_path or not os.path.isfile(vpx_path):
        return {}

    exe = ensure_vpxtool(cfg)
    if not exe:
        return {}

    cmd = [exe, "info", "show", vpx_path]
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=0x08000000,
            encoding="utf-8",
            errors="replace",
        )
        output = cp.stdout or ""
        result = {}
        for line in output.splitlines():
            m = re.match(r"^\s*(.+?):\s+(.*)$", line)
            if m:
                raw_key = m.group(1).strip()
                value = m.group(2).strip()
                key = re.sub(r"\s+", "_", raw_key).lower()
                result[key] = value
        return result
    except Exception:
        return {}


def _parse_authors_from_script(script: str) -> list:
    """
    Parse author names from a VBS script.
    Looks for comment lines containing author indicators.
    Returns a deduplicated list of primary author name tokens.

    Primary author patterns searched (case-insensitive):
      ' Table by JPSalas
      ' Author: nFozzy, Fleep
      ' Authors: Brad1X, Sixtoe
      ' Created by Tom Tower
      ' VPX by Dozer
      ' VPX recreation by g5k
      ' Original by George H
      ' Adapted by Flukemaster

    Lines after a '  Thanks to:' / '  Credits:' marker are treated as
    contributor credits and excluded from the primary author list.
    """
    authors = []
    seen = set()
    in_credits_section = False

    # Detect entry into a thanks/credits block
    _credits_re = re.compile(r"^\s*'[^']*(?:thanks?\s+to|credits?)\s*:", re.IGNORECASE)

    # Match comment lines with primary author-like patterns.
    # vpx(?:\s+\w+)*\s+by handles "VPX by", "VPX recreation by", "VPX conversion by", etc.
    _primary_re = re.compile(
        r"^\s*'[^']*(?:author(?:s)?|created\s+by|table\s+by|vpx(?:\s+\w+)*\s+by"
        r"|original\s+by|adapted\s+by|remake\s+by|mod\s+by|script\s+by"
        r"|recreation\s+by|conversion\s+by|made\s+by)\s*:?\s*(.+)",
        re.IGNORECASE,
    )

    for line in script.splitlines():
        # Entering a thanks/credits section — stop collecting primary authors
        if _credits_re.match(line):
            in_credits_section = True
            continue
        if in_credits_section:
            continue

        m = _primary_re.match(line)
        if m:
            raw = m.group(1).strip().strip("'").strip()
            # Split on common separators: comma, ampersand, " and ", " & "
            tokens = re.split(r"\s*[,&]\s*|\s+and\s+", raw, flags=re.IGNORECASE)
            for tok in tokens:
                tok = tok.strip().strip("'\"").strip()
                # Remove trailing version/year info like "(v1.0)" or "2024"
                tok = re.sub(r"\s*[\(\[].*", "", tok).strip()
                if tok and len(tok) >= 2:
                    key = tok.lower()
                    if key not in seen:
                        seen.add(key)
                        authors.append(tok)
    return authors


# ---------------------------------------------------------------------------
# Prefetch constants
# ---------------------------------------------------------------------------

PREFETCH_MODE = "background"
PREFETCH_LOG_EVERY = 50
ROLLING_HISTORY_PER_ROM = 10


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def ensure_dir(path): os.makedirs(path, exist_ok=True)
def _ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _set_folder_hidden(path: str):
    """Set Windows FILE_ATTRIBUTE_HIDDEN on *path*. No-op on non-Windows."""
    try:
        FILE_ATTRIBUTE_HIDDEN = 0x02
        ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

quiet_prefixes: tuple[str, ...] = ()

def log(cfg: AppConfig, msg: str, level: str = "INFO"):
    try:
        suppress_list = (getattr(cfg, "LOG_SUPPRESS", None) or DEFAULT_LOG_SUPPRESS) if cfg else DEFAULT_LOG_SUPPRESS
        for pat in suppress_list:
            if pat and pat in str(msg):
                return
    except Exception:
        pass
    line = f"[{_ts()}] [{level}] {msg}"
    suppress_console = any(str(msg).startswith(p) for p in quiet_prefixes) if quiet_prefixes else False
    try:
        ensure_dir(os.path.dirname(f_log(cfg)))
        with open(f_log(cfg), "a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except Exception:
        pass
    if not suppress_console:
        print(line)


# ---------------------------------------------------------------------------
# JSON helpers (raw, unsigned)
# ---------------------------------------------------------------------------

def _raw_load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _raw_save_json(path, obj):
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


# ---------------------------------------------------------------------------
# Anti-cheat / signature helpers
# ---------------------------------------------------------------------------

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
    """Determines whether a file should be protected by anti-tamper signature.

    Uses a whitelist approach: only gameplay-relevant local state files that
    can directly affect achievements, scores, or progress are protected.
    Non-critical files (config, caches, tool data, reference/definition files)
    are intentionally left unsigned.

    Protected categories:
    - Achievement state (achievements_state.json)
    - Challenge result history (session_stats/challenges/history/*.json)
    - Session summary data (session_stats/Highlights/*.summary.json)
    - Active player session state (session_stats/Highlights/activePlayers/*.json)
    """
    if not path:
        return False
    p = path.lower().replace("\\", "/")

    if not p.endswith(".json"):
        return False

    # Achievement state – the main persisted achievement/progress store
    if p.endswith("achievements_state.json"):
        return True

    # Challenge result history – local score/result records per ROM
    if "/session_stats/challenges/history/" in p:
        return True

    # Session summary files – per-session result snapshots used for display and uploads
    if "/session_stats/highlights/" in p and p.endswith(".summary.json"):
        return True

    # Active player session state – in-progress session data
    if "/session_stats/highlights/activeplayers/" in p:
        return True

    return False


# ---------------------------------------------------------------------------
# JSON helpers (with signature support)
# ---------------------------------------------------------------------------

def load_json(path, default=None):
    data = _raw_load_json(path, None)
    if data is None:
        return default

    if _is_secure_path(path) and isinstance(data, dict):
        sig = data.pop("_signature", None)
        if not sig:
            # Unsigned legacy file (e.g. from v2.5) – do not block; migrate to v2.6 protection now.
            print(f"[SECURITY] Unsigned legacy file detected: {path}. Upgrading to v2.6 protection now.")
            save_json(path, data)
            return data

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


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def apply_tooltips(owner, tips: dict):
    for name, text in (tips or {}).items():
        try:
            w = getattr(owner, name, None)
            if w:
                w.setToolTip(text)
        except Exception:
            pass


def sanitize_filename(s):
    s = re.sub(r"[^\w\-. ]+", "_", str(s))
    return s.strip().replace(" ", "_")
