from __future__ import annotations
import subprocess
import os
import sys
import re
import ssl
import time
import json
import zipfile
import io
from datetime import datetime
from typing import Optional

try:
    import requests
except Exception:
    requests = None

from urllib.request import Request, urlopen

from vpx_achievement_watcher.core.constants import (
    EXCLUDED_FIELDS_LC, DEFAULT_LOG_SUPPRESS,
    VPXTOOL_EXE, VPXTOOL_DIRNAME, VPXTOOL_URL,
    INDEX_URL, ROMNAMES_URL,
)
from vpx_achievement_watcher.utils.version import WATCHER_VERSION

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
VPXTOOL_PATH = os.path.join(APP_DIR, VPXTOOL_DIRNAME, VPXTOOL_EXE)

def ensure_dir(path): os.makedirs(path, exist_ok=True)
def _ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

quiet_prefixes: tuple[str, ...] = ()

def log(cfg, msg: str, level: str = "INFO"):
    from vpx_achievement_watcher.core.paths import f_log
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

def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.isdir(base):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    return os.path.join(APP_DIR, rel)

def sanitize_filename(s):
    s = re.sub(r"[^\w\-. ]+", "_", str(s))
    return s.strip().replace(" ", "_")

def apply_tooltips(owner, tips: dict):
    for name, text in (tips or {}).items():
        try:
            w = getattr(owner, name, None)
            if w:
                w.setToolTip(text)
        except Exception:
            pass

def is_excluded_field(label: str) -> bool:
    ll = str(label or "").strip().lower()
    return (
        ll in EXCLUDED_FIELDS_LC or
        "reset" in ll or
        "cleared" in ll or
        "factory" in ll or
        "timestamp" in ll or
        "game time" in ll or
        ("last" in ll and ("printout" in ll or "replay" in ll)) or
        ("last" in ll and "game" in ll)
    )

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

def ensure_vpxtool(cfg) -> str | None:
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

def run_vpxtool_get_rom(cfg, vpx_path: str, suppress_warn: bool = False) -> str | None:

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
                return rom

        m = re.search(r"\b([A-Za-z0-9_]{2,})\b", out)
        if m:
            if key in warned:
                warned.discard(key)
            return m.group(1)

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


def run_vpxtool_get_script_authors(cfg, vpx_path: str) -> list:
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


def run_vpxtool_info_show(cfg, vpx_path: str) -> dict:
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


LEVEL_TABLE = [
    (0,    1,  "🪙 Rookie"),
    (10,   2,  "🥉 Apprentice"),
    (25,   3,  "🥈 Veteran"),
    (50,   4,  "🥇 Expert"),
    (100,  5,  "🏆 Master"),
    (200,  6,  "💎 Grand Master"),
    (400,  7,  "👑 Pinball Legend"),
    (750,  8,  "🔥 Pinball God"),
    (1200, 9,  "⚡ Multiball King"),
    (2000, 10, "🌟 VPX Elite"),
]

def compute_player_level(state: dict) -> dict:
    """
    Compute the player level from the achievements state.
    Counts all unique unlocked achievement titles across global + all session ROMs (deduped).
    Returns dict with keys: level (int), name (str), icon (str), label (str), total (int),
    next_at (int), progress_pct (float), prev_at (int), max_level (bool)
    """
    seen = set()
    # global
    for entries in (state.get("global") or {}).values():
        for e in (entries or []):
            t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
            if t:
                seen.add(t)
    # session (all ROMs)
    for entries in (state.get("session") or {}).values():
        for e in (entries or []):
            t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
            if t:
                seen.add(t)
    total = len(seen)

    current_level = 1
    current_name = LEVEL_TABLE[0][2]
    prev_at = 0
    next_at = LEVEL_TABLE[1][0] if len(LEVEL_TABLE) > 1 else total + 1

    for threshold, lvl, name in LEVEL_TABLE:
        if total >= threshold:
            current_level = lvl
            current_name = name
            prev_at = threshold
        else:
            next_at = threshold
            break
    else:
        next_at = prev_at  # max level reached

    icon = current_name.split(" ")[0]  # the emoji
    label = " ".join(current_name.split(" ")[1:])  # the name without emoji

    if next_at > prev_at:
        progress_pct = round((total - prev_at) / (next_at - prev_at) * 100, 1)
    else:
        progress_pct = 100.0  # max level

    return {
        "level": current_level,
        "name": current_name,
        "icon": icon,
        "label": label,
        "total": total,
        "next_at": next_at,
        "prev_at": prev_at,
        "progress_pct": progress_pct,
        "max_level": current_level == LEVEL_TABLE[-1][1],
    }
