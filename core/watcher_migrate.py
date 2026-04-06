from __future__ import annotations

import os

from .config import (
    AppConfig,
    f_achievements_state,
    f_rom_keys_lowercased_marker,
    p_rom_spec,
    _load_progress_upload_log,
    _save_progress_upload_log,
)
from .watcher_io import (
    ensure_dir,
    log,
    secure_load_json,
    secure_save_json,
)


def _is_weird_value(x: int) -> bool:
    try:
        return abs(int(x)) >= 400_000_000
    except Exception:
        return False


def _migrate_rom_keys_to_lowercase(cfg: "AppConfig") -> None:
    """One-time migration: normalize all ROM keys to lowercase in state/log files and rename
    .ach.json files.  Runs only once per installation, guarded by a marker file.
    """
    marker = f_rom_keys_lowercased_marker(cfg)
    if os.path.isfile(marker):
        return

    migrated = False

    # 1. Migrate achievements_state.json
    state_path = f_achievements_state(cfg)
    if os.path.isfile(state_path):
        try:
            state = secure_load_json(state_path, {}) or {}
            changed = False

            # Migrate state["session"] — dict keyed by ROM name
            session = state.get("session", {})
            if isinstance(session, dict) and any(k != k.lower() for k in session):
                new_session: dict = {}
                for rom_key, ach_list in session.items():
                    lc_key = rom_key.lower()
                    if lc_key not in new_session:
                        new_session[lc_key] = []
                    # Merge achievement lists, deduplicate by title (keep earlier timestamp)
                    existing: dict = {
                        e["title"]: e
                        for e in new_session[lc_key]
                        if isinstance(e, dict) and "title" in e
                    }
                    for entry in (ach_list if isinstance(ach_list, list) else []):
                        if not isinstance(entry, dict) or "title" not in entry:
                            continue
                        title = entry["title"]
                        if title not in existing:
                            existing[title] = entry
                        elif entry.get("ts", "") < existing[title].get("ts", ""):
                            existing[title] = entry  # keep earlier timestamp
                    new_session[lc_key] = list(existing.values())
                state["session"] = new_session
                changed = True

            # Migrate state["roms_played"] — list of ROM names
            roms_played = state.get("roms_played", [])
            if isinstance(roms_played, list) and any(
                r != r.lower() for r in roms_played if isinstance(r, str)
            ):
                state["roms_played"] = list(
                    dict.fromkeys(r.lower() for r in roms_played if isinstance(r, str))
                )
                changed = True

            if changed:
                secure_save_json(state_path, state)
                log(cfg, "[MIGRATE] Lowercased ROM keys in achievements_state.json")
                migrated = True
        except Exception as e:
            log(cfg, f"[MIGRATE] rom_keys_lowercase: achievements_state error: {e}", "WARN")

    # 2. Migrate progress_upload_log.json
    try:
        log_data = _load_progress_upload_log(cfg)
        if log_data and any(k != k.lower() for k in log_data):
            new_log: dict = {}
            for rom_key, vps_id in log_data.items():
                lc_key = rom_key.lower()
                if lc_key not in new_log:
                    new_log[lc_key] = vps_id
            _save_progress_upload_log(cfg, new_log)
            log(cfg, "[MIGRATE] Lowercased ROM keys in progress_upload_log.json")
            migrated = True
    except Exception as e:
        log(cfg, f"[MIGRATE] rom_keys_lowercase: progress_upload_log error: {e}", "WARN")

    # 3. Rename uppercase .ach.json files in the rom-specific achievements directory
    rom_spec_dir = p_rom_spec(cfg)
    if os.path.isdir(rom_spec_dir):
        try:
            for fn in os.listdir(rom_spec_dir):
                if not fn.lower().endswith(".ach.json"):
                    continue
                stem = fn[: -len(".ach.json")]
                if stem == stem.lower():
                    continue  # already lowercase, nothing to do
                lc_fn = stem.lower() + ".ach.json"
                old_path = os.path.join(rom_spec_dir, fn)
                new_path = os.path.join(rom_spec_dir, lc_fn)
                if os.path.isfile(new_path):
                    # Lowercase file already exists — remove the uppercase duplicate
                    os.remove(old_path)
                    log(cfg, f"[MIGRATE] Removed uppercase ROM spec: {fn} (lowercase exists)")
                else:
                    os.rename(old_path, new_path)
                    log(cfg, f"[MIGRATE] Renamed ROM spec: {fn} → {lc_fn}")
                migrated = True
        except Exception as e:
            log(cfg, f"[MIGRATE] rom_keys_lowercase: .ach.json error: {e}", "WARN")

    # Write marker file so this migration only runs once
    try:
        ensure_dir(os.path.dirname(marker))
        with open(marker, "w", encoding="utf-8") as _f:
            _f.write("1")
    except Exception as e:
        log(cfg, f"[MIGRATE] rom_keys_lowercase: could not write marker: {e}", "WARN")

    if migrated:
        log(cfg, "[MIGRATE] ROM keys lowercase migration complete")
