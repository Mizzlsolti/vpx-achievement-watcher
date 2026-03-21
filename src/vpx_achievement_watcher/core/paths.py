from __future__ import annotations
import os
import shutil
import json


def p_maps(cfg):         return os.path.join(cfg.BASE, "tools", "NVRAM_Maps")
def p_local_maps(cfg):   return os.path.join(p_maps(cfg), "maps")
def p_session(cfg):      return os.path.join(cfg.BASE, "session_stats")
def p_highlights(cfg):   return os.path.join(p_session(cfg), "Highlights")
def p_achievements(cfg): return os.path.join(cfg.BASE, "Achievements")
def p_rom_spec(cfg):     return os.path.join(p_achievements(cfg), "rom_specific_achievements")
def p_custom(cfg):       return os.path.join(p_achievements(cfg), "custom_achievements")
def f_global_ach(cfg):   return os.path.join(p_achievements(cfg), "global_achievements.json")
def f_achievements_state(cfg) -> str:
    return os.path.join(p_achievements(cfg), "achievements_state.json")
def f_log(cfg):          return os.path.join(cfg.BASE, "watcher.log")
def f_index(cfg):        return os.path.join(p_maps(cfg), "index.json")
def f_romnames(cfg):     return os.path.join(p_maps(cfg), "romnames.json")
def p_vps(cfg):          return os.path.join(cfg.BASE, "tools", "vps")
def p_vps_img(cfg):      return os.path.join(p_vps(cfg), "img")
def f_vps_mapping(cfg):  return os.path.join(p_vps(cfg), "vps_id_mapping.json")
def f_vpsdb_cache(cfg):  return os.path.join(p_vps(cfg), "vpsdb.json")
def f_progress_upload_log(cfg) -> str:
    """Tracks which (rom, vps_id) combos have already had progress uploaded."""
    return os.path.join(p_achievements(cfg), "progress_upload_log.json")


def _load_progress_upload_log(cfg) -> dict:
    """Load the progress upload log dict {rom: vps_id}."""
    path = f_progress_upload_log(cfg)
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_progress_upload_log(cfg, log_data: dict):
    """Save the progress upload log dict {rom: vps_id}."""
    from vpx_achievement_watcher.core.helpers import ensure_dir
    path = f_progress_upload_log(cfg)
    ensure_dir(os.path.dirname(path))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
    except Exception:
        pass


def _migrate_runtime_dirs(cfg):
    """One-time migration from old flat structure to new grouped structure."""
    from vpx_achievement_watcher.core.helpers import ensure_dir

    # NVRAM_Maps: root → tools/NVRAM_Maps
    old_maps = os.path.join(cfg.BASE, "NVRAM_Maps")
    new_maps = p_maps(cfg)
    if os.path.isdir(old_maps) and not os.path.isdir(new_maps):
        ensure_dir(os.path.dirname(new_maps))
        shutil.move(old_maps, new_maps)

    # achievements_state.json: root → Achievements/
    old_state = os.path.join(cfg.BASE, "achievements_state.json")
    new_state = f_achievements_state(cfg)
    if os.path.isfile(old_state) and not os.path.isfile(new_state):
        ensure_dir(os.path.dirname(new_state))
        shutil.move(old_state, new_state)

    # global_achievements.json: root → Achievements/
    old_global = os.path.join(cfg.BASE, "global_achievements.json")
    new_global = f_global_ach(cfg)
    if os.path.isfile(old_global) and not os.path.isfile(new_global):
        ensure_dir(os.path.dirname(new_global))
        shutil.move(old_global, new_global)

    # rom_specific_achievements: root → Achievements/
    old_rom_spec = os.path.join(cfg.BASE, "rom_specific_achievements")
    new_rom_spec = p_rom_spec(cfg)
    if os.path.isdir(old_rom_spec) and not os.path.isdir(new_rom_spec):
        ensure_dir(os.path.dirname(new_rom_spec))
        shutil.move(old_rom_spec, new_rom_spec)

    # custom_achievements: root → Achievements/
    old_custom = os.path.join(cfg.BASE, "custom_achievements")
    new_custom = p_custom(cfg)
    if os.path.isdir(old_custom) and not os.path.isdir(new_custom):
        ensure_dir(os.path.dirname(new_custom))
        shutil.move(old_custom, new_custom)

    # challenges: root → session_stats/challenges
    old_challenges = os.path.join(cfg.BASE, "challenges")
    new_challenges = os.path.join(p_session(cfg), "challenges")
    if os.path.isdir(old_challenges) and not os.path.isdir(new_challenges):
        ensure_dir(os.path.dirname(new_challenges))
        shutil.move(old_challenges, new_challenges)

    # vps_id_mapping.json: root → tools/vps/
    old_vps_mapping = os.path.join(cfg.BASE, "vps_id_mapping.json")
    new_vps_mapping = f_vps_mapping(cfg)
    if os.path.isfile(old_vps_mapping) and not os.path.isfile(new_vps_mapping):
        ensure_dir(os.path.dirname(new_vps_mapping))
        shutil.move(old_vps_mapping, new_vps_mapping)

    # vpsdb.json: tools/ → tools/vps/
    old_vpsdb = os.path.join(cfg.BASE, "tools", "vpsdb.json")
    new_vpsdb = f_vpsdb_cache(cfg)
    if os.path.isfile(old_vpsdb) and not os.path.isfile(new_vpsdb):
        ensure_dir(os.path.dirname(new_vpsdb))
        shutil.move(old_vpsdb, new_vpsdb)

    # Clean up old .txt session dumps
    if os.path.isdir(p_session(cfg)):
        for fn in os.listdir(p_session(cfg)):
            if fn.lower().endswith(".txt"):
                try:
                    os.remove(os.path.join(p_session(cfg), fn))
                except Exception:
                    pass

    # Clean up old .session.json history files in Highlights
    if os.path.isdir(p_highlights(cfg)):
        for fn in os.listdir(p_highlights(cfg)):
            if fn.lower().endswith(".session.json"):
                try:
                    os.remove(os.path.join(p_highlights(cfg), fn))
                except Exception:
                    pass
