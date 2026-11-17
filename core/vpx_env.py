"""core/vpx_env.py – Visual Pinball X environment detection (10.8.1+ aware).

Responsibilities
----------------
* Find the VPX installation folder.  Users run different executables
  (``VPinballX.exe``, ``VPinballX64.exe``, ``VPinballX_GL64.exe``,
  ``VPinballX_BGFX64.exe`` …) from different install paths, so every
  executable whose name starts with ``VPinballX`` is accepted.
* Read the VPX version from the executable's file version resource.
* Locate ``VPinballX.ini``.  VPX 10.8.1 stores it per minor version in
  ``%APPDATA%\\VPinballX\\10.8\\`` (or next to the executable when the
  "ini along exe" layout is enabled); 10.8.0 used ``%APPDATA%\\VPinballX\\``.
* Install / enable superhac's *score-server* plugin (10.8.1+ only).

Everything here is best-effort: any failure is logged and the Watcher keeps
running exactly as before (single-player, NVRAM only).
"""

from __future__ import annotations

import glob
import io
import json
import os
import re
import threading
import zipfile
from typing import Optional, Tuple

from .watcher_io import log, _fetch_bytes_url

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil is a hard requirement in builds
    psutil = None  # type: ignore

try:
    import win32api  # type: ignore
except Exception:
    win32api = None  # type: ignore


VPX_EXE_PATTERN = re.compile(r"^vpinballx.*\.exe$", re.IGNORECASE)
MIN_PLUGIN_VERSION: Tuple[int, int, int] = (10, 8, 1)

SCORE_SERVER_ID = "ScoreServer"
PINMAME_ID = "PinMAME"
SCORE_SERVER_FOLDER = "score-server"
SCORE_SERVER_DLL = "plugin-score-server64.dll"
PINMAME_FOLDER = "pinmame"
PINMAME_DLL = "plugin-pinmame64.dll"
PINMAME_BACKUP_SUFFIX = ".watcher-original"

# Plugins are built by .github/workflows/build-vpx-plugins.yml in the Watcher
# repo and published as pre-releases tagged "vpx-plugins-*".
PLUGIN_RELEASES_API = "https://api.github.com/repos/Mizzlsolti/vpx-achievement-watcher/releases?per_page=30"
PLUGIN_TAG_PREFIX = "vpx-plugins-"
PLUGIN_ZIP_ASSET = "vpx-plugins-win64.zip"
PLUGIN_MANIFEST_ASSET = "vpx-plugins-manifest.json"

_ensure_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Executable / folder detection
# ---------------------------------------------------------------------------

def _is_vpx_exe_name(name: str) -> bool:
    return bool(name) and bool(VPX_EXE_PATTERN.match(os.path.basename(name)))


def find_vpx_exes(folder: str) -> list[str]:
    """Return all VPinballX*.exe files directly inside *folder*."""
    out: list[str] = []
    try:
        if folder and os.path.isdir(folder):
            for fn in os.listdir(folder):
                if _is_vpx_exe_name(fn) and os.path.isfile(os.path.join(folder, fn)):
                    out.append(os.path.join(folder, fn))
    except Exception:
        pass
    return sorted(out)


def find_running_vpx_exe() -> Optional[str]:
    """Return the full path of a running VPinballX*.exe process, if any."""
    if psutil is None:
        return None
    try:
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                name = proc.info.get("name") or ""
                if not _is_vpx_exe_name(name):
                    continue
                exe = proc.info.get("exe") or ""
                if exe and os.path.isfile(exe):
                    return exe
            except Exception:
                continue
    except Exception:
        pass
    return None


def is_vpx_running() -> bool:
    if psutil is None:
        return False
    try:
        for proc in psutil.process_iter(["name"]):
            if _is_vpx_exe_name(proc.info.get("name") or ""):
                return True
    except Exception:
        pass
    return False


def _candidate_dirs_from_cfg(cfg) -> list[str]:
    cands: list[str] = []
    tables = str(getattr(cfg, "TABLES_DIR", "") or "")
    nvram = str(getattr(cfg, "NVRAM_DIR", "") or "")
    if tables:
        cands.append(os.path.dirname(os.path.normpath(tables)))       # ...\VisualPinball\Tables
    if nvram:
        cands.append(os.path.dirname(os.path.dirname(os.path.normpath(nvram))))  # ...\VPinMAME\nvram
    return cands


def resolve_vpx_dir(cfg, save: bool = True) -> str:
    """Return the VPX install folder ('' when unknown).

    Order: running process → stored ``cfg.VPX_DIR`` → folders derived from the
    configured Tables/NVRAM paths.  The result is persisted in ``cfg.VPX_DIR``.
    """
    found = ""
    running = find_running_vpx_exe()
    if running:
        found = os.path.dirname(running)
    if not found:
        stored = str(getattr(cfg, "VPX_DIR", "") or "")
        if stored and find_vpx_exes(stored):
            found = stored
    if not found:
        for d in _candidate_dirs_from_cfg(cfg):
            if find_vpx_exes(d):
                found = d
                break
    if found and save and os.path.normcase(found) != os.path.normcase(str(getattr(cfg, "VPX_DIR", "") or "")):
        try:
            cfg.VPX_DIR = found
            cfg.save()
            log(cfg, f"[VPX] Install folder detected: {found}")
        except Exception:
            pass
    return found


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def get_exe_version(exe_path: str) -> Optional[Tuple[int, int, int]]:
    """Return (major, minor, revision) from the exe's version resource."""
    if not exe_path or not os.path.isfile(exe_path) or win32api is None:
        return None
    try:
        info = win32api.GetFileVersionInfo(exe_path, "\\")
        ms = int(info["FileVersionMS"])
        ls = int(info["FileVersionLS"])
        return (ms >> 16) & 0xFFFF, ms & 0xFFFF, (ls >> 16) & 0xFFFF
    except Exception:
        return None


def get_vpx_version(cfg, vpx_dir: str = "") -> Optional[Tuple[int, int, int]]:
    """Version of the running VPX exe, else the newest exe in *vpx_dir*."""
    running = find_running_vpx_exe()
    if running:
        v = get_exe_version(running)
        if v:
            return v
    best: Optional[Tuple[int, int, int]] = None
    for exe in find_vpx_exes(vpx_dir or resolve_vpx_dir(cfg, save=False)):
        v = get_exe_version(exe)
        if v and (best is None or v > best):
            best = v
    return best


def supports_score_server(version: Optional[Tuple[int, int, int]]) -> bool:
    return bool(version) and tuple(version) >= MIN_PLUGIN_VERSION


def _fmt_ver(v) -> str:
    return ".".join(str(x) for x in v) if v else "unknown"


# ---------------------------------------------------------------------------
# VPinballX.ini
# ---------------------------------------------------------------------------

def find_vpx_ini(cfg=None, vpx_dir: str = "", version: Optional[Tuple[int, int, int]] = None) -> Optional[str]:
    """Locate the VPinballX.ini VPX actually uses.

    Mirrors VPX's own lookup (FileLocator / VPApp):
      1. %APPDATA%\\VPinballX\\<major>.<minor>\\VPinballX.ini   (10.8.1+)
      2. <vpx folder>\\VPinballX.ini                           (ini-along-exe layout)
      3. %APPDATA%\\VPinballX\\VPinballX.ini                   (10.8.0)
    """
    appdata = os.environ.get("APPDATA") or ""
    base = os.path.join(appdata, "VPinballX") if appdata else ""
    if cfg is not None and not vpx_dir:
        vpx_dir = resolve_vpx_dir(cfg, save=False)
    if cfg is not None and version is None:
        version = get_vpx_version(cfg, vpx_dir)

    cands: list[str] = []
    if base:
        if version:
            cands.append(os.path.join(base, f"{version[0]}.{version[1]}", "VPinballX.ini"))
        else:
            # Unknown version: newest per-version folder first.
            try:
                subs = [d for d in glob.glob(os.path.join(base, "*.*")) if os.path.isdir(d)]

                def _key(p):
                    try:
                        return tuple(int(x) for x in os.path.basename(p).split("."))
                    except Exception:
                        return (0,)
                for d in sorted(subs, key=_key, reverse=True):
                    cands.append(os.path.join(d, "VPinballX.ini"))
            except Exception:
                pass
    if vpx_dir:
        cands.append(os.path.join(vpx_dir, "VPinballX.ini"))
    if base:
        cands.append(os.path.join(base, "VPinballX.ini"))

    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def _read_text(path: str) -> Tuple[str, str]:
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("latin-1"), "latin-1"


def ini_enable_plugin(ini_path: str, plugin_id: str) -> bool:
    """Set ``Enable = 1`` in ``[Plugin.<plugin_id>]`` with a minimal text edit.

    Returns True when the file now enables the plugin.  The rest of the file
    (comments, ordering, line endings) is left untouched.  A one-time backup
    ``VPinballX.ini.watcher.bak`` is written before the first change.
    """
    text, enc = _read_text(ini_path)
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    header = f"[plugin.{plugin_id}]".lower()

    sec_start = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == header:
            sec_start = i
            break

    changed = False
    if sec_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [f"[Plugin.{plugin_id}]", "Enable = 1"]
        changed = True
    else:
        sec_end = len(lines)
        for j in range(sec_start + 1, len(lines)):
            if lines[j].strip().startswith("["):
                sec_end = j
                break
        key_idx = None
        for j in range(sec_start + 1, sec_end):
            m = re.match(r"^\s*enable\s*=\s*(.*)$", lines[j], re.IGNORECASE)
            if m:
                key_idx = j
                if m.group(1).strip() != "1":
                    lines[j] = "Enable = 1"
                    changed = True
                break
        if key_idx is None:
            lines.insert(sec_start + 1, "Enable = 1")
            changed = True

    if not changed:
        return True

    bak = ini_path + ".watcher.bak"
    try:
        if not os.path.exists(bak):
            with open(ini_path, "rb") as src, open(bak, "wb") as dst:
                dst.write(src.read())
    except Exception:
        pass
    out = nl.join(lines) + nl
    tmp = ini_path + ".watcher.tmp"
    with open(tmp, "w", encoding=("utf-8" if enc == "utf-8-sig" else enc), newline="") as f:
        if enc == "utf-8-sig":
            f.write("﻿")
        f.write(out)
    os.replace(tmp, ini_path)
    return True


def ini_plugin_enabled(ini_path: str, plugin_id: str) -> bool:
    try:
        text, _ = _read_text(ini_path)
    except Exception:
        return False
    header = f"[plugin.{plugin_id}]".lower()
    in_sec = False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("["):
            in_sec = (s.lower() == header)
            continue
        if in_sec:
            m = re.match(r"^enable\s*=\s*(.*)$", s, re.IGNORECASE)
            if m:
                return m.group(1).strip() == "1"
    return False


# ---------------------------------------------------------------------------
# Multiplayer plugins (score-server + patched PinMAME)
# ---------------------------------------------------------------------------

def _sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _state_path(cfg) -> str:
    return os.path.join(cfg.BASE, "tools", "vpx_plugins", "state.json")


def _load_state(cfg) -> dict:
    try:
        with open(_state_path(cfg), "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(cfg, st: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_state_path(cfg)), exist_ok=True)
        with open(_state_path(cfg), "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
    except Exception:
        pass


def find_score_server_plugin(vpx_dir: str) -> Optional[str]:
    """Return the plugin folder if the score-server plugin is installed."""
    if not vpx_dir:
        return None
    plugins = os.path.join(vpx_dir, "plugins")
    if not os.path.isdir(plugins):
        return None
    default = os.path.join(plugins, SCORE_SERVER_FOLDER)
    try:
        others = [os.path.join(plugins, d) for d in os.listdir(plugins)]
    except Exception:
        others = []
    for d in [default] + [o for o in others if o != default]:
        try:
            if not os.path.isdir(d):
                continue
            if os.path.isfile(os.path.join(d, SCORE_SERVER_DLL)):
                return d
            cfg_file = os.path.join(d, "plugin.cfg")
            if os.path.isfile(cfg_file):
                txt, _ = _read_text(cfg_file)
                if re.search(r'^\s*id\s*=\s*"?ScoreServer"?\s*$', txt, re.IGNORECASE | re.MULTILINE) \
                        and os.path.isfile(os.path.join(d, SCORE_SERVER_DLL)):
                    return d
        except Exception:
            continue
    return None


def _latest_plugin_release() -> Optional[dict]:
    """Newest 'vpx-plugins-*' release of the Watcher repo (pre-releases included)."""
    try:
        data = _fetch_bytes_url(PLUGIN_RELEASES_API, timeout=20)
        rels = json.loads(data.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(rels, list):
        return None
    cands = [r for r in rels if isinstance(r, dict) and str(r.get("tag_name", "")).startswith(PLUGIN_TAG_PREFIX)
             and not r.get("draft")]
    if not cands:
        return None
    cands.sort(key=lambda r: str(r.get("published_at") or r.get("created_at") or ""), reverse=True)
    return cands[0]


def _asset_url(release: dict, name: str) -> str:
    for a in release.get("assets") or []:
        if isinstance(a, dict) and a.get("name") == name:
            return str(a.get("browser_download_url") or "")
    return ""


def _download_package(cfg, release: dict) -> Optional[Tuple[dict, str]]:
    """Download + unpack the plugin package into BASE/tools/vpx_plugins/<tag>/."""
    tag = str(release.get("tag_name") or "")
    cache = os.path.join(cfg.BASE, "tools", "vpx_plugins", tag)
    manifest_path = os.path.join(cache, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f), cache
        except Exception:
            pass
    zurl = _asset_url(release, PLUGIN_ZIP_ASSET)
    if not zurl:
        log(cfg, f"[VPX_PLUGINS] Release {tag} has no {PLUGIN_ZIP_ASSET}", "WARN")
        return None
    log(cfg, f"[VPX_PLUGINS] Downloading plugin package {tag} …")
    data = _fetch_bytes_url(zurl, timeout=120)
    tmp = cache + ".tmp"
    if os.path.isdir(tmp):
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    root = os.path.realpath(tmp)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            dest = os.path.realpath(os.path.join(tmp, *name.split("/")))
            if not (dest == root or dest.startswith(root + os.sep)):
                continue  # path traversal guard
            if info.is_dir():
                os.makedirs(dest, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as dst:
                dst.write(src.read())
    if not os.path.isfile(os.path.join(tmp, "manifest.json")):
        raise RuntimeError("package has no manifest.json")
    if os.path.isdir(cache):
        import shutil
        shutil.rmtree(cache, ignore_errors=True)
    os.replace(tmp, cache)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    # Verify hashes from the manifest.
    for rel, sha in (manifest.get("files") or {}).items():
        fp = os.path.join(cache, *rel.split("/"))
        if not os.path.isfile(fp) or _sha256(fp).lower() != str(sha).lower():
            raise RuntimeError(f"hash mismatch for {rel}")
    return manifest, cache


def _copy_tree(src: str, dst: str) -> None:
    import shutil
    os.makedirs(dst, exist_ok=True)
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for fn in files:
            shutil.copy2(os.path.join(root, fn), os.path.join(target, fn))


def _version_compatible(version, manifest: dict) -> bool:
    """Plugins are built per VPX major.minor.rev (e.g. 10.8.1)."""
    try:
        want = tuple(int(x) for x in str(manifest.get("vpx_version", "")).split(".")[:3])
        return bool(version) and tuple(version[:3]) == want
    except Exception:
        return False


def ensure_vpx_plugins(cfg) -> dict:
    """Install/repair the multiplayer plugins for VPX 10.8.1+.

    Returns {"ready": bool, "event": str, "detail": str, "version": str}.
    ``event`` is one of: "", "installed", "reapplied", "rebuild_needed",
    "no_build", "failed", "vpx_not_found", "vpx_old", "busy".
    The Watcher only enables multiplayer when ``ready`` is True; in every
    other case it keeps working exactly as before (single player).
    """
    res = {"ready": False, "event": "", "detail": "", "version": ""}
    if not _ensure_lock.acquire(blocking=False):
        res["event"] = "busy"
        return res
    try:
        vpx_dir = resolve_vpx_dir(cfg)
        if not vpx_dir:
            res["event"] = "vpx_not_found"
            log(cfg, "[VPX_PLUGINS] VPX folder not found – multiplayer disabled")
            return res
        version = get_vpx_version(cfg, vpx_dir)
        res["version"] = _fmt_ver(version)
        if not supports_score_server(version):
            res["event"] = "vpx_old"
            log(cfg, f"[VPX_PLUGINS] VPX {_fmt_ver(version)} – multiplayer needs 10.8.1+, running single player")
            return res
        if not find_vpx_exes(vpx_dir) or not any(os.path.basename(e).lower().endswith("64.exe") for e in find_vpx_exes(vpx_dir)):
            res["event"] = "failed"
            res["detail"] = "Only 64-bit VPX is supported for multiplayer."
            return res

        state = _load_state(cfg)
        release = _latest_plugin_release()
        pkg = None
        if release:
            try:
                pkg = _download_package(cfg, release)
            except Exception as e:
                log(cfg, f"[VPX_PLUGINS] package download failed: {e}", "WARN")
        if pkg is None and state.get("cache") and os.path.isdir(state.get("cache")):
            try:
                with open(os.path.join(state["cache"], "manifest.json"), "r", encoding="utf-8") as f:
                    pkg = (json.load(f), state["cache"])
            except Exception:
                pkg = None
        if pkg is None:
            res["event"] = "no_build"
            log(cfg, "[VPX_PLUGINS] No plugin build available yet – running single player")
            return res
        manifest, cache = pkg
        tag = str(manifest.get("tag") or (release or {}).get("tag_name") or "")
        patched_sha = str((manifest.get("files") or {}).get(f"{PINMAME_FOLDER}/{PINMAME_DLL}", "")).lower()

        if not _version_compatible(version, manifest):
            res["event"] = "rebuild_needed"
            res["detail"] = (f"VPX {_fmt_ver(version)} is installed, the plugin build is for "
                             f"VPX {manifest.get('vpx_version')}. Multiplayer is off until a new build is released.")
            log(cfg, f"[VPX_PLUGINS] {res['detail']}", "WARN")
            return res

        pm_dir = os.path.join(vpx_dir, "plugins", PINMAME_FOLDER)
        pm_dll = os.path.join(pm_dir, PINMAME_DLL)
        ss_dir = os.path.join(vpx_dir, "plugins", SCORE_SERVER_FOLDER)
        running = is_vpx_running()

        # ── PinMAME plugin: our patched build vs. whatever is installed ──
        cur_sha = _sha256(pm_dll).lower() if os.path.isfile(pm_dll) else ""
        need_pm = cur_sha != patched_sha
        new_build = tag and tag != state.get("installed_tag")
        own_builds = [str(x).lower() for x in state.get("patched_shas", [])]
        if need_pm and cur_sha and not new_build and state.get("original_sha") \
                and cur_sha != str(state.get("original_sha")).lower() and cur_sha not in own_builds:
            # Same build as before, but a *different* official PinMAME plugin is
            # installed now -> VPX/PinMAME was updated with a new plugin version.
            res["event"] = "rebuild_needed"
            res["detail"] = ("A new PinMAME plugin was installed by a VPX update. "
                             "Multiplayer is off until a new plugin build is released.")
            log(cfg, f"[VPX_PLUGINS] {res['detail']}", "WARN")
            return res

        ss_need = (not find_score_server_plugin(vpx_dir)) or new_build or (
            os.path.isfile(os.path.join(ss_dir, SCORE_SERVER_DLL))
            and _sha256(os.path.join(ss_dir, SCORE_SERVER_DLL)).lower()
            != str((manifest.get("files") or {}).get(f"{SCORE_SERVER_FOLDER}/{SCORE_SERVER_DLL}", "")).lower())

        if (need_pm or ss_need) and running:
            res["event"] = "busy"
            log(cfg, "[VPX_PLUGINS] VPX is running – plugin install postponed until VPX exits")
            return res

        first_install = not state.get("installed_tag")
        try:
            if ss_need:
                _copy_tree(os.path.join(cache, SCORE_SERVER_FOLDER), ss_dir)
            if need_pm:
                os.makedirs(pm_dir, exist_ok=True)
                # Back up the official plugin (never one of our own patched builds).
                if cur_sha and cur_sha not in [str(x).lower() for x in state.get("patched_shas", [])]:
                    import shutil
                    shutil.copy2(pm_dll, pm_dll + PINMAME_BACKUP_SUFFIX)
                    state["original_sha"] = cur_sha
                import shutil
                shutil.copy2(os.path.join(cache, PINMAME_FOLDER, PINMAME_DLL), pm_dll)
                if _sha256(pm_dll).lower() != patched_sha:
                    raise RuntimeError("patched PinMAME plugin did not verify after copy")
        except PermissionError as e:
            res["event"] = "failed"
            res["detail"] = f"No write access to the VPX plugins folder ({e}). Start the Watcher once as administrator."
            log(cfg, f"[VPX_PLUGINS] {res['detail']}", "WARN")
            return res
        except Exception as e:
            res["event"] = "failed"
            res["detail"] = f"Plugin install failed: {e}"
            log(cfg, f"[VPX_PLUGINS] {res['detail']}", "WARN")
            return res

        if need_pm or ss_need:
            if first_install:
                res["event"] = "installed"
            elif new_build:
                res["event"] = "installed"
            else:
                res["event"] = "reapplied"
            known = [str(x).lower() for x in state.get("patched_shas", [])]
            if patched_sha and patched_sha not in known:
                known.append(patched_sha)
            state.update({"installed_tag": tag, "cache": cache, "vpx_dir": vpx_dir,
                          "vpx_version": _fmt_ver(version), "patched_shas": known[-10:]})
            _save_state(cfg, state)
            log(cfg, f"[VPX_PLUGINS] {res['event']}: {tag} -> {vpx_dir}")

        # ── VPinballX.ini: enable both plugins ──
        ini = find_vpx_ini(cfg, vpx_dir, version)
        if not ini:
            res["event"] = res["event"] or "failed"
            res["detail"] = "VPinballX.ini not found – start VPX once so it creates its settings file."
            log(cfg, f"[VPX_PLUGINS] {res['detail']}", "WARN")
            return res
        need_ini = not (ini_plugin_enabled(ini, SCORE_SERVER_ID) and ini_plugin_enabled(ini, PINMAME_ID))
        if need_ini:
            if running:
                if not res["event"]:
                    res["event"] = "busy"
                return res
            try:
                ini_enable_plugin(ini, SCORE_SERVER_ID)
                ini_enable_plugin(ini, PINMAME_ID)
                log(cfg, f"[VPX_PLUGINS] score-server + PinMAME plugins enabled in {ini}")
            except Exception as e:
                res["event"] = "failed"
                res["detail"] = f"Could not edit {ini}: {e}"
                log(cfg, f"[VPX_PLUGINS] {res['detail']}", "WARN")
                return res
        res["ready"] = True
        return res
    except Exception as e:
        res["event"] = "failed"
        res["detail"] = str(e)
        log(cfg, f"[VPX_PLUGINS] ensure failed: {e}", "WARN")
        return res
    finally:
        _ensure_lock.release()


def ensure_vpx_plugins_async(cfg, on_done=None) -> None:
    def _run():
        st = ensure_vpx_plugins(cfg)
        if on_done:
            try:
                on_done(st)
            except Exception:
                pass
    threading.Thread(target=_run, daemon=True, name="VpxPluginsEnsure").start()
