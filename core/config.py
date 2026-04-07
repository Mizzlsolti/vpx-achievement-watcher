from __future__ import annotations
import os, sys, json, shutil
from dataclasses import dataclass, field
from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# Runtime paths
# ---------------------------------------------------------------------------

if getattr(sys, 'frozen', False):
    # Running as a PyInstaller-bundled .exe
    # sys.executable always points to the actual .exe regardless of working directory
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    # Running as a plain Python script (development)
    # __file__ is core/config.py, so go one level up to reach the project root
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_dir(path): os.makedirs(path, exist_ok=True)

# ---------------------------------------------------------------------------
# Overlay defaults
# ---------------------------------------------------------------------------

DEFAULT_OVERLAY = {
    "scale_pct": 50,
    "background": "auto",
    "portrait_mode": False,
    "portrait_rotate_ccw": False,
    "lines_per_category":12,
    "toggle_input_source": "keyboard",
    "toggle_vk": 120,
    "toggle_joy_button": 2,
    "font_family": "Segoe UI",
    "base_title_size": 17,
    "base_body_size": 12,
    "base_hint_size": 10,
    "use_xy": False,
    "pos_x": 100,
    "pos_y": 100,
    "prefer_ascii_icons": False,
    "auto_show_on_end": True,
    "live_updates": False,
    "ach_toast_custom": False,
    "ach_toast_x_landscape": 100,
    "ach_toast_y_landscape": 100,
    "ach_toast_x_portrait": 100,
    "ach_toast_y_portrait": 100,
    "ach_toast_portrait": False,
    "ach_toast_rotate_ccw": False,
    "overlay_auto_close": False,
    "automatic_creation": True,
}
DEFAULT_OVERLAY.setdefault("low_performance_mode", False)
DEFAULT_OVERLAY.setdefault("anim_main_transitions", True)
DEFAULT_OVERLAY.setdefault("anim_main_glow", True)
DEFAULT_OVERLAY.setdefault("anim_main_score_progress", True)
DEFAULT_OVERLAY.setdefault("anim_main_highlights", True)
DEFAULT_OVERLAY.setdefault("anim_toast", True)
DEFAULT_OVERLAY.setdefault("anim_status", True)

# ---------------------------------------------------------------------------
# Granular fx_* effect keys (replaces coarse anim_* toggles)
# Each overlay has 10 individual effects: fx_<group>_<effect> (bool)
# and fx_<group>_<effect>_intensity (int 0-100).
# ---------------------------------------------------------------------------
DEFAULT_OVERLAY.setdefault("_fx_migrated", False)

# Main Overlay
DEFAULT_OVERLAY.setdefault("fx_main_breathing_glow", True)
DEFAULT_OVERLAY.setdefault("fx_main_breathing_glow_intensity", 80)
DEFAULT_OVERLAY.setdefault("fx_main_floating_particles", True)
DEFAULT_OVERLAY.setdefault("fx_main_floating_particles_intensity", 80)
DEFAULT_OVERLAY.setdefault("fx_main_page_transition", True)
DEFAULT_OVERLAY.setdefault("fx_main_glitch_frame", True)
DEFAULT_OVERLAY.setdefault("fx_main_score_spin", True)
DEFAULT_OVERLAY.setdefault("fx_main_progress_fill", True)
DEFAULT_OVERLAY.setdefault("fx_main_shine_sweep", True)
DEFAULT_OVERLAY.setdefault("fx_main_highlight_flash", True)
DEFAULT_OVERLAY.setdefault("fx_main_nav_arrows_pulse", True)
DEFAULT_OVERLAY.setdefault("fx_main_accent_lerp", True)

# Achievement Toast
DEFAULT_OVERLAY.setdefault("fx_toast_burst_particles", True)
DEFAULT_OVERLAY.setdefault("fx_toast_burst_particles_intensity", 80)
DEFAULT_OVERLAY.setdefault("fx_toast_neon_rings", True)
DEFAULT_OVERLAY.setdefault("fx_toast_neon_rings_intensity", 80)
DEFAULT_OVERLAY.setdefault("fx_toast_typewriter", True)
DEFAULT_OVERLAY.setdefault("fx_toast_icon_bounce", True)
DEFAULT_OVERLAY.setdefault("fx_toast_slide_motion", True)
DEFAULT_OVERLAY.setdefault("fx_toast_energy_flash", True)
DEFAULT_OVERLAY.setdefault("fx_toast_god_rays", True)
DEFAULT_OVERLAY.setdefault("fx_toast_god_rays_intensity", 80)
DEFAULT_OVERLAY.setdefault("fx_toast_confetti", True)
DEFAULT_OVERLAY.setdefault("fx_toast_confetti_intensity", 80)
DEFAULT_OVERLAY.setdefault("fx_toast_hologram_flicker", True)
DEFAULT_OVERLAY.setdefault("fx_toast_shockwave", True)
DEFAULT_OVERLAY.setdefault("fx_toast_shockwave_intensity", 80)

DEFAULT_OVERLAY.setdefault("overlay_page2_enabled", True)
DEFAULT_OVERLAY.setdefault("overlay_page3_enabled", True)
DEFAULT_OVERLAY.setdefault("overlay_page4_enabled", True)
DEFAULT_OVERLAY.setdefault("overlay_page5_enabled", True)
DEFAULT_OVERLAY.setdefault("overlay_page6_enabled", True)
DEFAULT_OVERLAY.setdefault("status_overlay_enabled", True)
DEFAULT_OVERLAY.setdefault("status_overlay_rotate_ccw", False)
DEFAULT_OVERLAY.setdefault("status_overlay_x_portrait", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_y_portrait", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_x_landscape", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_y_landscape", 100)
DEFAULT_OVERLAY.setdefault("status_overlay_saved", False)
DEFAULT_OVERLAY.setdefault("sound_enabled", False)
DEFAULT_OVERLAY.setdefault("sound_volume", 20)
DEFAULT_OVERLAY.setdefault("sound_pack", "arcade")
DEFAULT_OVERLAY.setdefault("sound_events", {})
DEFAULT_OVERLAY.setdefault("trophie_gui_enabled", True)
DEFAULT_OVERLAY.setdefault("trophie_overlay_enabled", True)
DEFAULT_OVERLAY.setdefault("trophie_overlay_x", -1)
DEFAULT_OVERLAY.setdefault("trophie_overlay_y", -1)
DEFAULT_OVERLAY.setdefault("trophie_overlay_portrait", False)
DEFAULT_OVERLAY.setdefault("trophie_overlay_rotate_ccw", False)
DEFAULT_OVERLAY.setdefault("trophie_gui_skin", "classic")
DEFAULT_OVERLAY.setdefault("trophie_overlay_skin", "classic")

# Post-Processing
DEFAULT_OVERLAY.setdefault("fx_post_bloom", False)
DEFAULT_OVERLAY.setdefault("fx_post_bloom_intensity", 60)
DEFAULT_OVERLAY.setdefault("fx_post_motion_blur", False)
DEFAULT_OVERLAY.setdefault("fx_post_motion_blur_intensity", 60)
DEFAULT_OVERLAY.setdefault("fx_post_chromatic_aberration", False)
DEFAULT_OVERLAY.setdefault("fx_post_chromatic_aberration_intensity", 50)
DEFAULT_OVERLAY.setdefault("fx_post_vignette", False)
DEFAULT_OVERLAY.setdefault("fx_post_vignette_intensity", 60)
DEFAULT_OVERLAY.setdefault("fx_post_film_grain", False)
DEFAULT_OVERLAY.setdefault("fx_post_film_grain_intensity", 40)
DEFAULT_OVERLAY.setdefault("fx_post_scanlines", False)
DEFAULT_OVERLAY.setdefault("fx_post_scanlines_intensity", 50)
# Per-overlay post-processing toggles
DEFAULT_OVERLAY.setdefault("pp_overlay_main", True)
DEFAULT_OVERLAY.setdefault("pp_overlay_toast", True)
DEFAULT_OVERLAY.setdefault("duels_do_not_disturb", True)

_ALLOWED_OVERLAY_KEYS = [
    "theme",
    "scale_pct", "background", "portrait_mode", "portrait_rotate_ccw", 
    "lines_per_category", "font_family", "overlay_auto_close",
    "pos_x", "pos_y", "use_xy", "overlay_pos_saved",
    "base_body_size", "base_title_size", "base_hint_size",
    
    "toggle_input_source", "toggle_vk", "toggle_joy_button", "toggle_mods",
    "ach_toast_custom", "ach_toast_saved", "ach_toast_x_landscape", "ach_toast_y_landscape", 
    "ach_toast_x_portrait", "ach_toast_y_portrait", "ach_toast_portrait", "ach_toast_rotate_ccw",
    
    "notifications_portrait", "notifications_rotate_ccw", "notifications_saved",
    "notifications_x_landscape", "notifications_y_landscape", "notifications_x_portrait", "notifications_y_portrait",
    
    "status_overlay_enabled", "status_overlay_portrait", "status_overlay_rotate_ccw",
    "status_overlay_saved", "status_overlay_x_landscape", "status_overlay_y_landscape",
    "status_overlay_x_portrait", "status_overlay_y_portrait",
    
    "low_performance_mode",
    "anim_main_transitions", "anim_main_glow", "anim_main_score_progress",
    "overlay_page2_enabled", "overlay_page3_enabled",
    "overlay_page4_enabled", "overlay_page5_enabled", "overlay_page6_enabled",
    "sound_enabled", "sound_volume", "sound_pack", "sound_events",

    # Granular fx_* effect toggles and intensities
    "_fx_migrated",
    "fx_main_breathing_glow", "fx_main_breathing_glow_intensity",
    "fx_main_floating_particles", "fx_main_floating_particles_intensity",
    "fx_main_page_transition",
    "fx_main_glitch_frame",
    "fx_main_score_spin",
    "fx_main_progress_fill",
    "fx_main_shine_sweep",
    "fx_main_highlight_flash",
    "fx_main_nav_arrows_pulse",
    "fx_main_accent_lerp",
    "fx_toast_burst_particles", "fx_toast_burst_particles_intensity",
    "fx_toast_neon_rings", "fx_toast_neon_rings_intensity",
    "fx_toast_typewriter",
    "fx_toast_icon_bounce",
    "fx_toast_slide_motion",
    "fx_toast_energy_flash",
    "fx_toast_god_rays", "fx_toast_god_rays_intensity",
    "fx_toast_confetti", "fx_toast_confetti_intensity",
    "fx_toast_hologram_flicker",
    "fx_toast_shockwave", "fx_toast_shockwave_intensity",
    "trophie_gui_enabled", "trophie_overlay_enabled",
    "trophie_overlay_x", "trophie_overlay_y",
    "trophie_overlay_portrait", "trophie_overlay_rotate_ccw",
    "trophie_gui_skin", "trophie_overlay_skin",

    # Post-Processing effect toggles and intensities
    "fx_post_bloom", "fx_post_bloom_intensity",
    "fx_post_motion_blur", "fx_post_motion_blur_intensity",
    "fx_post_chromatic_aberration", "fx_post_chromatic_aberration_intensity",
    "fx_post_vignette", "fx_post_vignette_intensity",
    "fx_post_film_grain", "fx_post_film_grain_intensity",
    "fx_post_scanlines", "fx_post_scanlines_intensity",
    # Per-overlay post-processing toggles
    "duels_do_not_disturb",
]


def _migrate_anim_to_fx(ov: dict) -> None:
    """One-time migration: map legacy anim_* keys to granular fx_* keys.

    Called from AppConfig.load() on first load after upgrading.  Sets the
    ``_fx_migrated`` flag so the migration only runs once.
    """
    if ov.get("_fx_migrated"):
        return

    anim_main_transitions = bool(ov.get("anim_main_transitions", True))
    anim_main_glow = bool(ov.get("anim_main_glow", True))
    anim_main_score = bool(ov.get("anim_main_score_progress", True))
    anim_main_hi = bool(ov.get("anim_main_highlights", True))
    anim_toast = bool(ov.get("anim_toast", True))
    # Main Overlay
    ov.setdefault("fx_main_page_transition", anim_main_transitions)
    ov.setdefault("fx_main_glitch_frame", anim_main_transitions)
    ov.setdefault("fx_main_breathing_glow", anim_main_glow)
    ov.setdefault("fx_main_floating_particles", anim_main_glow)
    ov.setdefault("fx_main_score_spin", anim_main_score)
    ov.setdefault("fx_main_progress_fill", anim_main_score)
    ov.setdefault("fx_main_shine_sweep", anim_main_hi)
    ov.setdefault("fx_main_highlight_flash", anim_main_hi)
    ov.setdefault("fx_main_nav_arrows_pulse", anim_main_hi)
    ov.setdefault("fx_main_accent_lerp", anim_main_hi)

    # Achievement Toast
    for key in [
        "fx_toast_burst_particles", "fx_toast_neon_rings", "fx_toast_typewriter",
        "fx_toast_icon_bounce", "fx_toast_slide_motion", "fx_toast_energy_flash",
        "fx_toast_god_rays", "fx_toast_confetti", "fx_toast_hologram_flicker",
        "fx_toast_shockwave",
    ]:
        ov.setdefault(key, anim_toast)

    ov["_fx_migrated"] = True

EXCLUDED_FIELDS = {
    "Last Game Start", "Last Printout", "Last Replay", "Champion Reset", "Clock Last Set", "Coins Cleared",
    "Factory Setting", "Recent Paid Cred", "Recent Serv. Cred", "Burn-in Time", "Totals Cleared", "Audits Cleared",
     "Last Serv. Cred"
}
EXCLUDED_FIELDS_LC = {s.lower() for s in EXCLUDED_FIELDS}

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

DEFAULT_LOG_SUPPRESS = [
    "[HOOK] Global keyboard hook installed",
    "[HOOK] toggle fired",
    "[HOTKEY] Registered WM_HOTKEY",
    "[CTRL] map miss for candidate",         
    "[CTRL] base-map miss for candidate",    
]
 
@dataclass
class AppConfig:
    BASE: str = r"C:\vPinball\VPX Achievement Watcher"
    NVRAM_DIR: str = r"C:\vPinball\VisualPinball\VPinMAME\nvram"
    TABLES_DIR: str = r"C:\vPinball\VisualPinball\Tables"
    OVERLAY: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_OVERLAY))
    FIRST_RUN: bool = True
    TUTORIAL_COMPLETED: bool = False
    LOG_CTRL: bool = False
    LOG_SUPPRESS: List[str] = field(default_factory=lambda: list(DEFAULT_LOG_SUPPRESS))
    CLOUD_ENABLED: bool = False
    CLOUD_BACKUP_ENABLED: bool = False
    CLOUD_URL: str = "https://vpx-achievements-watcher-lb-default-rtdb.europe-west1.firebasedatabase.app/"
    POPPER_DB_PATH: str = ""
    _load_error: bool = field(default=False, repr=False, compare=False)

    @staticmethod
    def _parse_config(data: dict) -> "AppConfig":
        """Build an AppConfig from a parsed JSON dict."""
        ov = dict(DEFAULT_OVERLAY)
        loaded_ov = data.get("OVERLAY", {})

        allowed_keys = _ALLOWED_OVERLAY_KEYS

        for k in list(loaded_ov.keys()):
            if k not in allowed_keys:
                del loaded_ov[k]

        ov.update(loaded_ov)

        # One-time migration from legacy anim_* keys to granular fx_* keys
        _migrate_anim_to_fx(ov)

        cloud_enabled = bool(data.get("CLOUD_ENABLED", False))
        cloud_backup_enabled = bool(data.get("CLOUD_BACKUP_ENABLED", False))
        if not cloud_enabled:
            cloud_backup_enabled = False

        return AppConfig(
            BASE=data.get("BASE", AppConfig.BASE),
            NVRAM_DIR=data.get("NVRAM_DIR", AppConfig.NVRAM_DIR),
            TABLES_DIR=data.get("TABLES_DIR", AppConfig.TABLES_DIR),
            OVERLAY=ov,
            FIRST_RUN=bool(data.get("FIRST_RUN", False)),
            TUTORIAL_COMPLETED=bool(data.get("TUTORIAL_COMPLETED", False)),
            CLOUD_ENABLED=cloud_enabled,
            CLOUD_BACKUP_ENABLED=cloud_backup_enabled,
            POPPER_DB_PATH=str(data.get("POPPER_DB_PATH", "")),
        )

    @staticmethod
    def load(path: str = CONFIG_FILE) -> "AppConfig":
        bak_path = path + ".bak"
        primary_missing = not os.path.exists(path)

        if not primary_missing:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return AppConfig._parse_config(data)
            except Exception as e:
                print(f"[LOAD ERROR] Failed to load config from '{path}': {e}")

        # Primary file is missing or corrupt — try the backup.
        if os.path.exists(bak_path):
            try:
                with open(bak_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"[LOAD WARN] Falling back to backup config '{bak_path}'")
                return AppConfig._parse_config(data)
            except Exception as e:
                print(f"[LOAD ERROR] Failed to load backup config from '{bak_path}': {e}")

        if primary_missing and not os.path.exists(bak_path):
            # Neither file exists — genuine first run.
            return AppConfig(FIRST_RUN=True)

        # Both files exist but are corrupt (or one exists but is corrupt and the other is missing).
        return AppConfig(FIRST_RUN=False, _load_error=True)

    def save(self, path: str = CONFIG_FILE) -> None:
        try:
            clean_overlay = {}
            ov = getattr(self, "OVERLAY", {})
            allowed_keys = _ALLOWED_OVERLAY_KEYS

            for k in allowed_keys:
                if k in ov:
                    clean_overlay[k] = ov[k]

            cloud_enabled_val = getattr(self, "CLOUD_ENABLED", False)
            cloud_backup_val = getattr(self, "CLOUD_BACKUP_ENABLED", False)
            if not cloud_enabled_val:
                cloud_backup_val = False

            to_dump = {
                "BASE": getattr(self, "BASE", r"C:\vPinball\VPX Achievement Watcher"),
                "NVRAM_DIR": getattr(self, "NVRAM_DIR", r"C:\vPinball\VisualPinball\VPinMAME\nvram"),
                "TABLES_DIR": getattr(self, "TABLES_DIR", r"C:\vPinball\VisualPinball\Tables"),
                "CLOUD_ENABLED": cloud_enabled_val,
                "CLOUD_BACKUP_ENABLED": cloud_backup_val,
                "FIRST_RUN": getattr(self, "FIRST_RUN", False),
                "TUTORIAL_COMPLETED": getattr(self, "TUTORIAL_COMPLETED", False),
                "OVERLAY": clean_overlay,
                "POPPER_DB_PATH": getattr(self, "POPPER_DB_PATH", ""),
            }

            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)

            tmp_path = path + ".tmp"
            bak_path = path + ".bak"

            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(to_dump, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                if os.path.exists(path):
                    shutil.copy2(path, bak_path)

                os.replace(tmp_path, path)
            except Exception:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                raise
        except Exception as e:
            print(f"CRITICAL ERROR: Could not save config.json -> {e}")

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def p_maps(cfg):         return os.path.join(cfg.BASE, "tools", "NVRAM_Maps")
def p_local_maps(cfg):   return os.path.join(p_maps(cfg), "maps")
def p_session(cfg):      return os.path.join(cfg.BASE, "session_stats")
def p_highlights(cfg):   return os.path.join(p_session(cfg), "Highlights")
def p_achievements(cfg): return os.path.join(cfg.BASE, "Achievements")
def p_rom_spec(cfg):     return os.path.join(p_achievements(cfg), "rom_specific_achievements")
def f_global_ach(cfg):   return os.path.join(p_achievements(cfg), "global_achievements.json")
def f_achievements_state(cfg: "AppConfig") -> str:
    return os.path.join(p_achievements(cfg), "achievements_state.json")
def f_log(cfg):          return os.path.join(cfg.BASE, "watcher.log")
def f_index(cfg):        return os.path.join(p_maps(cfg), "index.json")
def f_romnames(cfg):     return os.path.join(p_maps(cfg), "romnames.json")
def p_vps(cfg):          return os.path.join(cfg.BASE, "tools", "vps")
def p_vps_img(cfg):      return os.path.join(p_vps(cfg), "img")
def f_vps_mapping(cfg):  return os.path.join(p_vps(cfg), "vps_id_mapping.json")
def f_vpsdb_cache(cfg):  return os.path.join(p_vps(cfg), "vpsdb.json")
def p_aweditor(cfg):     return os.path.join(cfg.BASE, "tools", "AWeditor")
def p_aweditor_data(cfg): return os.path.join(p_aweditor(cfg), "Data")
def p_custom_events(cfg): return os.path.join(p_aweditor(cfg), "custom_events")
def f_custom_achievements_progress(cfg): return os.path.join(p_aweditor_data(cfg), "custom_achievements_progress.json")
def f_legacy_cleanup_marker(cfg: "AppConfig") -> str:
    """Marker file indicating that the one-time legacy progress cleanup has already run."""
    return os.path.join(p_achievements(cfg), ".legacy_progress_cleaned")
def f_rom_keys_lowercased_marker(cfg: "AppConfig") -> str:
    """Marker file indicating that the one-time ROM-key lowercase migration has already run."""
    return os.path.join(p_achievements(cfg), ".rom_keys_lowercased")
def f_rom_keys_cloud_cleaned_marker(cfg: "AppConfig") -> str:
    """Marker file indicating that the one-time cloud uppercase ROM-key cleanup has already run."""
    return os.path.join(p_achievements(cfg), ".rom_keys_cloud_cleaned")
def f_progress_upload_log(cfg: "AppConfig") -> str:
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
    path = f_progress_upload_log(cfg)
    ensure_dir(os.path.dirname(path))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
    except Exception:
        pass


def _migrate_runtime_dirs(cfg):
    """One-time migration from old flat structure to new grouped structure."""

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

    # AWEditor data: AWeditor/ -> AWeditor/Data/
    try:
        ensure_dir(p_aweditor_data(cfg))
        old_cache = os.path.join(p_aweditor(cfg), "aweditor_scan_cache.json")
        new_cache = os.path.join(p_aweditor_data(cfg), "aweditor_scan_cache.json")
        if os.path.isfile(old_cache) and not os.path.isfile(new_cache):
            shutil.move(old_cache, new_cache)

        old_cap = os.path.join(p_aweditor(cfg), "custom_achievements_progress.json")
        new_cap = f_custom_achievements_progress(cfg)
        if os.path.isfile(old_cap) and not os.path.isfile(new_cap):
            shutil.move(old_cap, new_cap)
    except Exception:
        pass

    # Migrate notifications: merge old files into new unified store
    try:
        from . import notifications as _notif
        _notif.migrate_notifications(cfg)
    except Exception:
        pass
