from __future__ import annotations
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .watcher_core import AppConfig

# Runtime-Import um Circular Imports zu vermeiden:
# AppConfig wird nur als Type-Hint verwendet
# Actual imports von watcher_core erfolgen lazy in den Funktionen

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

PRESTIGE_THRESHOLD = 2000   # Achievements per prestige round
MAX_PRESTIGE = 5            # Maximum prestige stars

# ─── Achievement Rarity ───────────────────────────────────────────────
RARITY_TIERS = [
    (50.0, "Common",    "#FFFFFF"),
    (25.0, "Uncommon",  "#4CAF50"),
    (10.0, "Rare",      "#2196F3"),
    (5.0,  "Epic",      "#9C27B0"),
    (0.0,  "Legendary", "#FF9800"),
]

def compute_rarity(unlocked_by: int, total_players: int) -> dict:
    """Compute rarity tier for an achievement based on how many players unlocked it."""
    if total_players <= 0:
        return {"tier": "Unknown", "color": "#888888", "pct": 0.0}
    pct = (unlocked_by / total_players) * 100
    for threshold, name, color in RARITY_TIERS:
        if pct >= threshold:
            return {"tier": name, "color": color, "pct": round(pct, 1)}
    return {"tier": "Legendary", "color": "#FF9800", "pct": round(pct, 1)}

def compute_player_level(state: dict) -> dict:
    """
    Compute the player level from the achievements state.
    Counts all unique unlocked achievement titles across global + all session ROMs (deduped).
    Returns dict with keys: level (int), name (str), icon (str), label (str), total (int),
    next_at (int), progress_pct (float), prev_at (int), max_level (bool),
    effective (int), prestige (int), prestige_display (str), fully_maxed (bool)
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

    # Prestige calculation
    prestige = min(total // PRESTIGE_THRESHOLD, MAX_PRESTIGE)
    prestige_display = "★" * prestige + "☆" * (MAX_PRESTIGE - prestige)
    effective = total - (prestige * PRESTIGE_THRESHOLD)

    current_level = 1
    current_name = LEVEL_TABLE[0][2]
    prev_at = 0
    next_at = LEVEL_TABLE[1][0] if len(LEVEL_TABLE) > 1 else effective + 1

    for threshold, lvl, name in LEVEL_TABLE:
        if effective >= threshold:
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
        progress_pct = round((effective - prev_at) / (next_at - prev_at) * 100, 1)
    else:
        progress_pct = 100.0  # max level

    max_level = current_level == LEVEL_TABLE[-1][1]
    fully_maxed = prestige >= MAX_PRESTIGE and max_level

    return {
        "level": current_level,
        "name": current_name,
        "icon": icon,
        "label": label,
        "total": total,
        "next_at": next_at,
        "prev_at": prev_at,
        "progress_pct": progress_pct,
        "max_level": max_level,
        "effective": effective,
        "prestige": prestige,
        "prestige_display": prestige_display,
        "fully_maxed": fully_maxed,
    }


# ──────────────────────────────────────────────────────────────────────────────
# BADGES
# ──────────────────────────────────────────────────────────────────────────────

BADGE_DEFINITIONS = [
    # (id, icon, name, description)
    # Milestones
    ("first_steps",       "🐣", "First Steps",        "Unlock your very first achievement"),
    ("getting_started",   "🎯", "Getting Started",     "Unlock 5 unique achievements"),
    ("deca",              "🔟", "Deca",                "Unlock 10 unique achievements"),
    ("half_century",      "5️⃣",  "Half Century",        "Unlock 50 unique achievements"),
    ("century",           "💯", "Century",             "Unlock 100 unique achievements"),
    ("hoarder",           "🏗️", "Hoarder",             "Unlock 500 unique achievements"),
    ("thousandaire",      "🏛️", "Thousandaire",        "Unlock 1000 unique achievements"),
    # Prestige
    ("first_star",        "⭐", "First Star",          "Reach Prestige 1"),
    ("two_stars",         "⭐", "Rising Star",         "Reach Prestige 2"),
    ("three_stars",       "⭐", "Superstar",           "Reach Prestige 3"),
    ("four_stars",        "🌟", "Elite Star",          "Reach Prestige 4"),
    ("five_stars",        "👑", "Maximum Prestige",    "Reach Prestige 5 — Fully Maxed"),
    # Exploration
    ("explorer",          "🗺️", "Explorer",            "Play 10 different tables"),
    ("globetrotter",      "🌍", "Globetrotter",        "Play tables from 5 different manufacturers"),
    ("bally_fan",         "🅱️", "Bally Fan",           "Play 5 different Bally tables"),
    ("williams_fan",      "🔷", "Williams Fan",        "Play 5 different Williams tables"),
    ("stern_fan",         "⚡", "Stern Fan",           "Play 5 different Stern tables"),
    ("gottlieb_fan",      "🔶", "Gottlieb Fan",        "Play 5 different Gottlieb tables"),
    # Playtime
    ("dedicated",         "⏰", "Dedicated",           "Accumulate 10 hours of total playtime"),
    ("marathon",          "🏃", "Marathon",            "Accumulate 50 hours of total playtime"),
    ("addict",            "🕹️", "Addict",              "Accumulate 100 hours of total playtime"),
    ("long_session",      "🌙", "Endurance",           "Play a single session for 60+ minutes"),
    # Special
    ("hot_streak",        "🔥", "Hot Streak",          "Unlock 5 achievements in a single session"),
    ("night_owl",         "🦉", "Night Owl",           "Start a session after midnight (00:00–05:00)"),
    ("speed_demon",       "⚡", "Speed Demon",         "Unlock 3 achievements within 5 minutes"),
    # Rarity
    ("rare_finder",       "🔵", "Rare Finder",         "Unlock a Rare achievement"),
    ("epic_hunter",       "🟣", "Epic Hunter",         "Unlock an Epic achievement"),
    ("legendary_hunter",  "🟠", "Legendary Hunter",    "Unlock a Legendary achievement"),
    # Cloud / Level
    ("cloud_pioneer",     "☁️", "Cloud Pioneer",       "Complete your first cloud upload"),
    ("level_5",           "🏅", "Level 5",             "Reach Player Level 5"),
    ("level_10",          "🎖️", "Level 10",            "Reach Player Level 10"),
]

BADGE_LOOKUP = {b[0]: b for b in BADGE_DEFINITIONS}


def _gather_badge_stats(cfg: "AppConfig", state: dict, watcher=None, rarity_cache: dict = None) -> dict:
    """Collect all statistics needed for badge evaluation."""
    from .watcher_core import secure_load_json
    stats = {}
    try:
        # Total unique achievements
        seen = set()
        for entries in (state.get("global") or {}).values():
            for e in (entries or []):
                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                if t:
                    seen.add(t)
        for entries in (state.get("session") or {}).values():
            for e in (entries or []):
                t = str(e.get("title", "")).strip() if isinstance(e, dict) else str(e).strip()
                if t:
                    seen.add(t)
        stats["total_achievements"] = len(seen)
    except Exception:
        stats["total_achievements"] = 0

    try:
        lv = compute_player_level(state)
        stats["level"] = lv["level"]
        stats["prestige"] = lv["prestige"]
        stats["fully_maxed"] = lv["fully_maxed"]
    except Exception:
        stats["level"] = 1
        stats["prestige"] = 0
        stats["fully_maxed"] = False

    try:
        stats["roms_played"] = list(state.get("roms_played") or [])
    except Exception:
        stats["roms_played"] = []

    # Manufacturer counts from roms_played using watcher INDEX
    mfr_roms: dict = {}  # manufacturer -> set of roms
    try:
        if watcher is not None:
            for rom in stats["roms_played"]:
                mfr = watcher._get_manufacturer_from_rom(rom) if hasattr(watcher, "_get_manufacturer_from_rom") else None
                if mfr:
                    mfr_roms.setdefault(mfr, set()).add(rom)
    except Exception:
        pass
    stats["mfr_roms"] = mfr_roms
    stats["num_manufacturers"] = len(mfr_roms)

    # Playtime from session stats txt/json files
    try:
        playtime_sec = 0
        max_session_sec = 0
        stats_dir = os.path.join(cfg.BASE, "session_stats")
        if os.path.isdir(stats_dir):
            highlights_dir = os.path.join(stats_dir, "Highlights")
            if os.path.isdir(highlights_dir):
                for fname in os.listdir(highlights_dir):
                    if fname.endswith(".summary.json"):
                        fpath = os.path.join(highlights_dir, fname)
                        try:
                            data = secure_load_json(fpath, {}) or {}
                            dur = int(data.get("duration_sec") or data.get("playtime_sec") or 0)
                            playtime_sec += dur
                            if dur > max_session_sec:
                                max_session_sec = dur
                        except Exception:
                            continue
        stats["total_playtime_sec"] = playtime_sec
        stats["max_session_sec"] = max_session_sec
    except Exception:
        stats["total_playtime_sec"] = 0
        stats["max_session_sec"] = 0

    # Max session unlocks (hot_streak): check from session state
    try:
        max_session_unlocks = 0
        for entries in (state.get("session") or {}).values():
            if entries:
                max_session_unlocks = max(max_session_unlocks, len(entries))
        stats["max_session_unlocks"] = max_session_unlocks
    except Exception:
        stats["max_session_unlocks"] = 0

    # Speed demon: 3 achievements within 5 minutes
    # Check session entries for timestamps
    try:
        speed_demon = False
        for entries in (state.get("session") or {}).values():
            if not entries or len(entries) < 3:
                continue
            ts_list = []
            for e in entries:
                if isinstance(e, dict) and e.get("ts"):
                    try:
                        t = datetime.fromisoformat(str(e["ts"]).replace("Z", "+00:00"))
                        ts_list.append(t.timestamp())
                    except Exception:
                        pass
            if len(ts_list) >= 3:
                ts_list.sort()
                for i in range(len(ts_list) - 2):
                    if ts_list[i + 2] - ts_list[i] <= 300:
                        speed_demon = True
                        break
        stats["speed_demon"] = speed_demon
    except Exception:
        stats["speed_demon"] = False

    # Night owl: check recent session start times from summary files
    try:
        night_owl = False
        highlights_dir = os.path.join(cfg.BASE, "session_stats", "Highlights")
        if os.path.isdir(highlights_dir):
            for fname in os.listdir(highlights_dir):
                if fname.endswith(".summary.json"):
                    fpath = os.path.join(highlights_dir, fname)
                    try:
                        data = secure_load_json(fpath, {}) or {}
                        ts_str = str(data.get("ts") or data.get("start_ts") or "")
                        if ts_str:
                            try:
                                t = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            except Exception:
                                continue
                            hour = t.hour
                            if 0 <= hour < 5:
                                night_owl = True
                                break
                    except Exception:
                        continue
        stats["night_owl"] = night_owl
    except Exception:
        stats["night_owl"] = False

    # Rarity checks
    try:
        has_rare = False
        has_epic = False
        has_legendary = False
        if rarity_cache and isinstance(rarity_cache, dict):
            for rom_cache in rarity_cache.values():
                if isinstance(rom_cache, dict):
                    for title, info in rom_cache.items():
                        if isinstance(info, dict):
                            tier = str(info.get("tier") or info.get("rarity") or "").lower()
                        else:
                            tier = str(info).lower()
                        if tier == "rare":
                            has_rare = True
                        elif tier == "epic":
                            has_epic = True
                        elif tier == "legendary":
                            has_legendary = True
        stats["has_rare"] = has_rare
        stats["has_epic"] = has_epic
        stats["has_legendary"] = has_legendary
    except Exception:
        stats["has_rare"] = False
        stats["has_epic"] = False
        stats["has_legendary"] = False

    # Cloud pioneer: check if any cloud upload has been done
    try:
        cloud_upload_done = bool(state.get("cloud_upload_done", False))
        stats["cloud_upload_done"] = cloud_upload_done
    except Exception:
        stats["cloud_upload_done"] = False

    return stats


BADGE_CHECKS = {
    "first_steps":      lambda s: s["total_achievements"] >= 1,
    "getting_started":  lambda s: s["total_achievements"] >= 5,
    "deca":             lambda s: s["total_achievements"] >= 10,
    "half_century":     lambda s: s["total_achievements"] >= 50,
    "century":          lambda s: s["total_achievements"] >= 100,
    "hoarder":          lambda s: s["total_achievements"] >= 500,
    "thousandaire":     lambda s: s["total_achievements"] >= 1000,
    "first_star":       lambda s: s["prestige"] >= 1,
    "two_stars":        lambda s: s["prestige"] >= 2,
    "three_stars":      lambda s: s["prestige"] >= 3,
    "four_stars":       lambda s: s["prestige"] >= 4,
    "five_stars":       lambda s: s["fully_maxed"],
    "explorer":         lambda s: len(s["roms_played"]) >= 10,
    "globetrotter":     lambda s: s["num_manufacturers"] >= 5,
    "bally_fan":        lambda s: len(s["mfr_roms"].get("Bally", set())) >= 5,
    "williams_fan":     lambda s: len(s["mfr_roms"].get("Williams", set())) >= 5,
    "stern_fan":        lambda s: len(s["mfr_roms"].get("Stern", set())) >= 5,
    "gottlieb_fan":     lambda s: len(s["mfr_roms"].get("Gottlieb", set())) >= 5,
    "dedicated":        lambda s: s["total_playtime_sec"] >= 36000,   # 10 hours
    "marathon":         lambda s: s["total_playtime_sec"] >= 180000,  # 50 hours
    "addict":           lambda s: s["total_playtime_sec"] >= 360000,  # 100 hours
    "long_session":     lambda s: s["max_session_sec"] >= 3600,       # 60 minutes
    "hot_streak":       lambda s: s["max_session_unlocks"] >= 5,
    "night_owl":        lambda s: s["night_owl"],
    "speed_demon":      lambda s: s["speed_demon"],
    "rare_finder":      lambda s: s["has_rare"],
    "epic_hunter":      lambda s: s["has_epic"],
    "legendary_hunter": lambda s: s["has_legendary"],
    "cloud_pioneer":    lambda s: s["cloud_upload_done"],
    "level_5":          lambda s: s["level"] >= 5,
    "level_10":         lambda s: s["level"] >= 10,
}


def evaluate_badges(state: dict, cfg: "AppConfig", watcher=None, rarity_cache: dict = None) -> tuple:
    """Evaluate all badges and return (all_earned_ids, newly_earned_ids).

    Non-blocking: catches all exceptions internally.
    """
    try:
        already_earned = set(state.get("badges") or [])
        stats = _gather_badge_stats(cfg, state, watcher=watcher, rarity_cache=rarity_cache)
        newly_earned = []
        all_earned = list(already_earned)
        for badge_id, check_fn in BADGE_CHECKS.items():
            if badge_id in already_earned:
                continue
            try:
                if check_fn(stats):
                    newly_earned.append(badge_id)
                    all_earned.append(badge_id)
            except Exception:
                pass
        return all_earned, newly_earned
    except Exception:
        return list(state.get("badges") or []), []
