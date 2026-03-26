from __future__ import annotations

import os
import re
import json
import glob
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from config import (
    AppConfig, log, load_json, save_json, secure_load_json, secure_save_json,
    p_rom_spec, f_global_ach, f_achievements_state, p_session, p_highlights,
    p_local_maps, p_maps, p_achievements, ensure_dir,
    is_excluded_field, MANUFACTURER_EMOJI, TABLE_EMOJI_KEYWORDS,
    BADGE_LOOKUP, evaluate_badges, compute_rarity,
    RARITY_TIERS, sanitize_filename, write_text, run_vpxtool_get_rom,
)
from cloud_sync import CloudSync


class AchievementsMixin:
    """Achievement-related methods, extracted as a mixin for Watcher."""

    def _generate_default_global_rules(self) -> list[dict]:
        rules: list[dict] = []
        seen: set[str] = set()
        candidate_fields = [
            "Games Started", "Balls Played", "Ramps Made", "Jackpots",
            "Total Multiballs", "Loops",
            "Combos", "Extra Balls", "Ball Saves",
        ]

        total_target = 150
        ci = 0
        while len(rules) < total_target and candidate_fields:
            fld = candidate_fields[ci % len(candidate_fields)]
            for m in self._overall_milestones_for_field(fld):
                if len(rules) >= total_target:
                    break
                title = self._unique_title(f"Global – {fld}: {m} Total", seen)
                rules.append({
                    "title": title,
                    "scope": "global",
                    "condition": {"type": "nvram_tally", "field": fld, "min": int(m)}
                })
            ci += 1

        # --- Manufacturer-based global achievements ---
        MANUFACTURER_ACHIEVEMENTS = [
            # Rookie: play 3 different tables of a manufacturer
            {"title": "Bally Rookie",      "type": "rom_count", "manufacturer": "Bally",     "min": 3},
            {"title": "Williams Rookie",   "type": "rom_count", "manufacturer": "Williams",  "min": 3},
            {"title": "Stern Rookie",      "type": "rom_count", "manufacturer": "Stern",     "min": 3},
            {"title": "Data East Rookie",  "type": "rom_count", "manufacturer": "Data East", "min": 3},
            {"title": "Gottlieb Rookie",   "type": "rom_count", "manufacturer": "Gottlieb",  "min": 3},
            {"title": "Sega Rookie",       "type": "rom_count", "manufacturer": "Sega",      "min": 3},
            {"title": "Capcom Rookie",     "type": "rom_count", "manufacturer": "Capcom",    "min": 3},
            # Veteran: play 5 different tables of a manufacturer
            {"title": "Bally Veteran",     "type": "rom_count", "manufacturer": "Bally",     "min": 5},
            {"title": "Williams Veteran",  "type": "rom_count", "manufacturer": "Williams",  "min": 5},
            {"title": "Stern Veteran",     "type": "rom_count", "manufacturer": "Stern",     "min": 5},
            {"title": "Data East Veteran", "type": "rom_count", "manufacturer": "Data East", "min": 5},
            {"title": "Gottlieb Veteran",  "type": "rom_count", "manufacturer": "Gottlieb",  "min": 5},
            # Master: play all installed tables of a manufacturer
            {"title": "Bally Master",      "type": "rom_complete_set", "manufacturer": "Bally"},
            {"title": "Williams Master",   "type": "rom_complete_set", "manufacturer": "Williams"},
            {"title": "Stern Master",      "type": "rom_complete_set", "manufacturer": "Stern"},
            {"title": "Data East Master",  "type": "rom_complete_set", "manufacturer": "Data East"},
            {"title": "Gottlieb Master",   "type": "rom_complete_set", "manufacturer": "Gottlieb"},
            {"title": "Sega Master",       "type": "rom_complete_set", "manufacturer": "Sega"},
            {"title": "Capcom Master",     "type": "rom_complete_set", "manufacturer": "Capcom"},
            # Cross-brand
            {"title": "Brand Explorer",    "type": "rom_count", "manufacturer": "__any__",   "min_brands": 3},
            {"title": "Brand Connoisseur", "type": "rom_count", "manufacturer": "__any__",   "min_brands": 5},
            {"title": "Brand Master",      "type": "rom_count", "manufacturer": "__any__",   "min_brands": 7},
            # Combo / Era
            {"title": "Golden Age",        "type": "rom_multi_brand", "manufacturers": ["Bally", "Williams", "Gottlieb"]},
            {"title": "Modern Era",        "type": "rom_multi_brand", "manufacturers": ["Stern", "Data East", "Sega"]},
            # Collector milestones (any manufacturer)
            {"title": "Table Tourist",     "type": "rom_count", "manufacturer": "__any__",   "min": 10},
            {"title": "Table Explorer",    "type": "rom_count", "manufacturer": "__any__",   "min": 20},
            {"title": "Complete Collector", "type": "rom_complete_set", "manufacturer": "__any__"},
            # Extra
            {"title": "Midway Rookie",     "type": "rom_count", "manufacturer": "Midway",    "min": 3},
            {"title": "Midway Master",     "type": "rom_complete_set", "manufacturer": "Midway"},
            {"title": "Premier Rookie",    "type": "rom_count", "manufacturer": "Premier",   "min": 3},
        ]
        for ach in MANUFACTURER_ACHIEVEMENTS:
            t = ach["title"]
            atype = ach["type"]
            if atype == "rom_multi_brand":
                rules.append({
                    "title": t,
                    "scope": "global",
                    "condition": {
                        "type": "rom_multi_brand",
                        "manufacturers": ach["manufacturers"],
                    },
                })
            elif atype == "rom_complete_set":
                rules.append({
                    "title": t,
                    "scope": "global",
                    "condition": {
                        "type": "rom_complete_set",
                        "manufacturer": ach["manufacturer"],
                    },
                })
            else:
                cond: dict = {"type": "rom_count", "manufacturer": ach["manufacturer"]}
                if "min" in ach:
                    cond["min"] = ach["min"]
                if "min_brands" in ach:
                    cond["min_brands"] = ach["min_brands"]
                rules.append({
                    "title": t,
                    "scope": "global",
                    "condition": cond,
                })

        # --- Challenge-based global achievements ---
        CHALLENGE_ACHIEVEMENTS = [
            # Timed challenges
            {"title": "Complete Your First Timed Challenge",  "challenge_type": "timed", "min": 1},
            {"title": "Complete 5 Timed Challenges",          "challenge_type": "timed", "min": 5},
            {"title": "Complete 10 Timed Challenges",         "challenge_type": "timed", "min": 10},
            {"title": "Complete 25 Timed Challenges",         "challenge_type": "timed", "min": 25},
            {"title": "Complete 50 Timed Challenges",         "challenge_type": "timed", "min": 50},
            # Flip challenges
            {"title": "Complete Your First Flip Challenge",   "challenge_type": "flip",  "min": 1},
            {"title": "Complete 5 Flip Challenges",           "challenge_type": "flip",  "min": 5},
            {"title": "Complete 10 Flip Challenges",          "challenge_type": "flip",  "min": 10},
            {"title": "Complete 25 Flip Challenges",          "challenge_type": "flip",  "min": 25},
            {"title": "Complete 50 Flip Challenges",          "challenge_type": "flip",  "min": 50},
            # Heat challenges
            {"title": "Complete Your First Heat Challenge",   "challenge_type": "heat",  "min": 1},
            {"title": "Complete 5 Heat Challenges",           "challenge_type": "heat",  "min": 5},
            {"title": "Complete 10 Heat Challenges",          "challenge_type": "heat",  "min": 10},
            {"title": "Complete 25 Heat Challenges",          "challenge_type": "heat",  "min": 25},
            {"title": "Complete 50 Heat Challenges",          "challenge_type": "heat",  "min": 50},
        ]
        for ach in CHALLENGE_ACHIEVEMENTS:
            rules.append({
                "title": ach["title"],
                "scope": "global",
                "condition": {
                    "type": "challenge_count",
                    "challenge_type": ach["challenge_type"],
                    "min": ach["min"],
                },
            })

        return rules        
            
    def _ensure_rom_specific(self, rom: str, audits: dict):
        if not rom or not audits:
            return
        path = os.path.join(p_rom_spec(self.cfg), f"{rom}.ach.json")
        if os.path.exists(path):
            return

        priority_set = set()
        
        fields_meta, _ = self.load_map_for_rom(rom)
        priority_fields = []
        if fields_meta:
            for f in fields_meta:
                sec = str(f.get("section", "")).lower()
                if "feature" in sec or "champion" in sec or "mode" in sec:
                    lbl = str(f.get("label") or f.get("name") or "")
                    if lbl and lbl in audits:
                        priority_fields.append(lbl)
                        priority_set.add(lbl) # Direkt ins Set schreiben

        target_session_total = max(36, len(priority_fields) * 2 + 15)
        session_time_minutes = [5, 10, 15, 20, 30, 45]
        max_session_milestones_per_field = 2
        max_session_uses_per_field = 2

        def ok_label(lbl: str) -> bool:
            if not isinstance(lbl, str) or not lbl.strip():
                return False
            ll = lbl.lower()
            if lbl not in priority_set and "score" in ll:
                return False
            if lbl not in priority_set and (is_excluded_field(lbl) or self.NOISE_REGEX.search(lbl)):
                return False
            if ll in {"current_player", "player_count", "current_ball", "balls played", "credits", "tilted", "game over", "tilt warnings"}:
                return False
            return True

        def category(lbl: str) -> str:
            ll = (lbl or "").lower()
            if any(k in ll for k in ["extra ball", "ball save", "multiball", "jackpot", "wizard"]):
                return "power"
            if any(k in ll for k in ["ramp", "loop", "orbit", "spinner", "target", "combo"]):
                return "precision"
            if any(k in ll for k in ["mode", "lock", "locks lit", "balls locked"]):
                return "progress"
            if any(k in ll for k in ["games started", "balls played"]):
                return "meta"
            return "other"

        def uniq(seq):
            seen = set()
            out = []
            for x in seq:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        def session_cap_for(lbl: str) -> int:
            l = (lbl or "").lower()
            if "extra ball" in l: return 5
            if "ball save" in l:  return 10
            if "jackpot" in l:    return 10
            if "multiball" in l:  return 3
            if "ramp" in l:       return 20
            if "loop" in l or "orbit" in l: return 10
            if "spinner" in l:    return 30
            if "target" in l:     return 30
            if "mode" in l:       return 5
            return 15

        def pick_session_milestones(lbl: str) -> list[int]:
            if lbl in priority_set and ("score" in lbl.lower() or "champion" in lbl.lower()):
                return [1]
            mils = self._session_milestones_for_field(lbl) or []
            cap = session_cap_for(lbl)
            mils = [m for m in mils if m <= cap]
            if not mils:
                return [1] if lbl in priority_set else []
            if len(mils) == 1:
                return [mils[0]]
            low = mils[0]
            mid = mils[max(1, len(mils)//2 - 1)]
            return uniq([low, mid])[:max_session_milestones_per_field]

        int_fields = [k for k, v in audits.items() if isinstance(v, int)]
        plausible = [k for k in int_fields if self._plausible_counter(k) and ok_label(k)]

        map_fields = self._map_fields_for_rom(rom)
        ordered = uniq([*priority_fields, *map_fields, *plausible]) or map_fields or plausible or int_fields
        ordered = [f for f in ordered if ok_label(f)]

        cats = {"power": [], "precision": [], "progress": [], "meta": [], "other": []}
        for f in ordered:
            cats[category(f)].append(f)

        rr = [
            ("power", cats["power"]),
            ("precision", cats["precision"]),
            ("progress", cats["progress"]),
            ("meta", cats["meta"]),
            ("other", cats["other"]),
        ]

        session_fields = []
        for f in priority_fields:
            if f in ordered and f not in session_fields:
                session_fields.append(f)

        target_session_unique_fields = max(15, len(session_fields) + 10)
        idxs = {k: 0 for k, _ in rr}
        while len(session_fields) < target_session_unique_fields:
            progressed = False
            for key, arr in rr:
                i = idxs[key]
                while i < len(arr) and arr[i] in session_fields:
                    i += 1
                idxs[key] = i
                if i < len(arr):
                    session_fields.append(arr[i])
                    idxs[key] = i + 1
                    progressed = True
            if not progressed:
                break

        if not session_fields:
            session_fields = ordered[:target_session_unique_fields]

        rules: list[dict] = []
        seen_titles: set[str] = set()

        for mins in session_time_minutes:
            secs = int(mins * 60)
            title = self._unique_title(f"{rom} – Play {mins} Minutes", seen_titles)
            rules.append({
                "title": title,
                "condition": {"type": "session_time", "min_seconds": secs},
                "scope": "session"
            })

        remaining_session = max(0, target_session_total - len(rules))
        used_session_per_field: dict[str, int] = {}

        for fld in session_fields:
            if remaining_session <= 0:
                break
            fl = (fld or "").lower()
            if "games started" in fl:
                continue
            picks = pick_session_milestones(fld)
            if not picks:
                continue
            for m in picks:
                if remaining_session <= 0:
                    break
                cnt = used_session_per_field.get(fld, 0)
                if cnt >= max_session_uses_per_field:
                    break
                title = self._unique_title(f"{rom} – {fld}: {int(m)}", seen_titles)
                rules.append({
                    "title": title,
                    "condition": {"type": "nvram_delta", "field": fld, "min": int(m)},
                    "scope": "session"
                })
                used_session_per_field[fld] = cnt + 1
                remaining_session -= 1

        if save_json(path, {"rules": rules}):
            batch = getattr(self, "_rom_spec_batch", None)
            if isinstance(batch, list):
                batch.append((rom, len(rules)))
            else:
                log(self.cfg, f"[ROM_SPEC] created {path} with {len(rules)} session-only rules (included priority fields)")

    def _unique_title(self, title: str, seen: set[str]) -> str:
        base = title.strip()
        if base not in seen:
            seen.add(base)
            return base
        i = 2
        while True:
            cand = f"{base} #{i}"
            if cand not in seen:
                seen.add(cand)
                return cand
            i += 1

    def _milestones(self, kind: str) -> list[int]:
        if kind == "session":
            return [1, 3, 5, 7, 10, 12, 15, 20, 25, 30, 40, 50]
        if kind == "overall":
            return [25, 50, 75, 100, 150, 200, 300, 400, 500, 750, 1000]
        if kind == "time":
            return [180, 300, 480, 600, 720, 900, 1200, 1500, 1800, 2400, 3000]
        return []

    def _collect_player_rules_for_rom(self, rom: str) -> list:
        rules = []
        rpath = os.path.join(p_rom_spec(self.cfg), f"{rom}.ach.json")
        if os.path.exists(rpath):
            data = load_json(rpath, {}) or {}
            if isinstance(data.get("rules"), list):
                rules.extend(data["rules"])

        out, seen = [], set()
        for r in rules:
            t = r.get("title") or "Achievement"
            if t in seen:
                continue
            seen.add(t)
            out.append(r)
        return out

    def _evaluate_player_session_achievements(self, pid: int, rom: str) -> tuple[list, list]:
        if pid not in self.players:
            return [], []
        player = self.players[pid]
        deltas = player.get("session_deltas", {}) or {}
        play_sec = int(player.get("active_play_seconds", 0.0))
        rules = self._collect_player_rules_for_rom(rom)

        state = self._ach_state_load()
        unlocked_session = state.get("session", {}).get(rom, [])
        def _get_title(e):
            if isinstance(e, dict): return str(e.get("title")).strip()
            return str(e).strip()
        already_unlocked = { _get_title(e) for e in unlocked_session if _get_title(e) }

        awarded = []
        retriggered = []
        for rule in rules:
            title = rule.get("title") or "Achievement"

            cond = rule.get("condition", {}) or {}
            rtype = cond.get("type")
            field = cond.get("field")
            is_met = False
            try:
                if rtype == "nvram_delta":
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 0))
                    if deltas.get(field, 0) >= need:
                        is_met = True

                elif rtype == "session_time":
                    min_s = int(cond.get("min_seconds", cond.get("min", 0)))
                    if play_sec >= min_s:
                        is_met = True
            except Exception:
                continue

            if is_met:
                if title.strip() in already_unlocked:
                    retriggered.append(title)
                else:
                    awarded.append(title)

        best_per_field = {}
        non_field_titles = []

        for title in awarded:
            parts = title.split("–", 1)
            if len(parts) > 1:
                right = parts[1].strip()
                m = re.match(r'^(.+?):\s*(\d+)$', right)
                if m:
                    field_name = m.group(1).strip()
                    tier_value = int(m.group(2))
                    if field_name not in best_per_field or tier_value > best_per_field[field_name][0]:
                        best_per_field[field_name] = (tier_value, title)
                    continue
            non_field_titles.append(title)

        out = non_field_titles + [t for _, t in sorted(best_per_field.values())]
        return out, retriggered

    def _augment_player_events_with_flags(self, score_abs: int, end_audits: dict, events: dict) -> dict:
        out = dict(events or {})
        try:
            if "666" in str(score_abs):
                out["devils_number"] = True
        except Exception:
            pass
        try:
            ini_key = None
            for k in (end_audits or {}).keys():
                if "initial" in str(k).lower():
                    ini_key = k
                    break
            if ini_key:
                val = str(end_audits.get(ini_key) or "").strip()
                if val:
                    out["initials"] = val
        except Exception:
            pass
        return out

    def _persist_and_toast_achievements(self, end_audits: dict, duration_sec: int):
        if not self.current_rom or not self._has_any_map(self.current_rom):
            log(self.cfg, f"[ACH] Evaluation skipped: No NVRAM map found for '{self.current_rom}'")
            return

        log(self.cfg, f"[ACH] Starting achievement evaluation for '{self.current_rom}'")

        # Track roms_played in achievements_state (Anti-Cheat protected)
        try:
            rom_state = self._ach_state_load()
            roms_played = list(rom_state.get("roms_played") or [])
            if self.current_rom not in roms_played:
                roms_played.append(self.current_rom)
                rom_state["roms_played"] = roms_played
                self._ach_state_save(rom_state)
                mfr = self._get_manufacturer_from_rom(self.current_rom)
                log(self.cfg, f"[GLOBAL_ACH] roms_played updated: {self.current_rom} (manufacturer: {mfr})")
        except Exception as e:
            log(self.cfg, f"[ACH] roms_played update failed: {e}", "WARN")

        try:
            _awarded, _all_global, awarded_meta, retriggered_meta = self._evaluate_achievements(
                self.current_rom, self.start_audits, end_audits, duration_sec
            )
        except Exception as e:
            log(self.cfg, f"[ACH] eval failed: {e}", "WARN")
            awarded_meta = []
            retriggered_meta = []

        log(self.cfg, f"[ACH] Evaluation result: {len(awarded_meta) if awarded_meta else 0} awarded, {len(retriggered_meta) if retriggered_meta else 0} retriggered")

        try:
            global_hits = [m for m in (awarded_meta or []) if (m.get("origin") == "global_achievements")]
            global_rt = [m for m in (retriggered_meta or []) if (m.get("origin") == "global_achievements")]
            if global_hits or global_rt:
                self._ach_record_unlocks("global", self.current_rom, global_hits, retriggered=global_rt)
            if global_hits:
                self._emit_achievement_toasts(global_hits, seconds=5, rom_override="")
        except Exception as e:
            log(self.cfg, f"[ACH] persist global failed: {e}", "WARN")

        try:
            session_hits, session_rt = self._evaluate_player_session_achievements(1, self.current_rom)
            if session_hits or session_rt:
                self._ach_record_unlocks("session", self.current_rom, list(session_hits), retriggered=list(session_rt))
            if session_hits:
                self._emit_achievement_toasts(session_hits, seconds=5)
        except Exception as e:
            log(self.cfg, f"[ACH] persist session failed: {e}", "WARN")

        try:
            if self.cfg.CLOUD_ENABLED:
                state = self._ach_state_load()
                player_name = self.cfg.OVERLAY.get("player_name", "Player")
                # Mark cloud upload done for cloud_pioneer badge
                state["cloud_upload_done"] = True
                self._ach_state_save(state)
                CloudSync.upload_full_achievements(self.cfg, state, player_name)
        except Exception as e:
            log(self.cfg, f"[ACH] full achievements upload failed: {e}", "WARN")

        # Evaluate badges
        try:
            state = self._ach_state_load()
            all_earned, newly_earned = evaluate_badges(state, self.cfg, watcher=self)
            if newly_earned:
                state["badges"] = all_earned
                self._ach_state_save(state)
                for badge_id in newly_earned:
                    try:
                        bdef = BADGE_LOOKUP.get(badge_id)
                        if bdef:
                            badge_title = f"{bdef[1]} {bdef[2]}"
                            self.bridge.ach_toast_show.emit(badge_title, "🏅 Badge Unlocked!", 6)
                    except Exception:
                        pass
                log(self.cfg, f"[BADGES] Newly earned: {newly_earned}")
        except Exception as e:
            log(self.cfg, f"[BADGES] evaluate_badges failed: {e}", "WARN")

    def _evaluate_achievements(self, rom: str, start_audits: dict, end_audits: dict, duration_sec: int) -> tuple[list[str], list[str], list[dict], list[dict]]:
        global_rules = self._collect_global_rules_for_rom(rom)

        deltas_ci = {}
        for k, _ve in (end_audits or {}).items():
            try:
                ve_i = int(self._nv_get_int_ci(end_audits, str(k), 0))
                vs_i = int(self._nv_get_int_ci(start_audits, str(k), 0))
                d = ve_i - vs_i
            except Exception:
                d = 0
            if d < 0:
                d = 0
            deltas_ci[str(k)] = d
        awarded = []
        awarded_meta = []
        retriggered_meta = []
        all_titles = []
        seen_all = set()
        seen_aw = set()
        seen_rt = set()

        # Pre-load state for rom_count / rom_complete_set / rom_multi_brand evaluation
        _rom_state_cache: dict | None = None
        _installed_roms_cache: dict = {}  # manufacturer -> set of ROM names
        _mfr_cache: dict = {}  # rom -> manufacturer (cached to avoid repeated regex)
        _rom_audits_cache: dict = {}  # rom -> audits dict (for nvram_tally cross-ROM reads)

        def _rom_state() -> dict:
            nonlocal _rom_state_cache
            if _rom_state_cache is None:
                _rom_state_cache = self._ach_state_load()
            return _rom_state_cache

        def _installed_roms(manufacturer: str) -> set:
            if manufacturer not in _installed_roms_cache:
                _installed_roms_cache[manufacturer] = self._scan_installed_roms_by_manufacturer(manufacturer)
            return _installed_roms_cache[manufacturer]

        def _mfr_for(r: str) -> str | None:
            if r not in _mfr_cache:
                _mfr_cache[r] = self._get_manufacturer_from_rom(r)
            return _mfr_cache[r]

        # Check for rom_complete_set revocations before evaluating rules
        try:
            state_pre = _rom_state()
            already_global = {
                str(e.get("title", "")).strip()
                for entries in state_pre.get("global", {}).values()
                for e in entries
            }
            roms_played_pre = set(state_pre.get("roms_played") or [])
            revoked = False
            for rule in global_rules:
                cond_pre = (rule.get("condition") or {}) if isinstance(rule, dict) else {}
                if str(cond_pre.get("type") or "").lower() != "rom_complete_set":
                    continue
                t_pre = (rule.get("title") or "Achievement").strip()
                if t_pre not in already_global:
                    continue
                mfr_pre = cond_pre.get("manufacturer", "")
                installed_pre = _installed_roms(mfr_pre)
                if not installed_pre:
                    continue
                new_tables = installed_pre - roms_played_pre
                if new_tables:
                    # Revoke: remove from global unlocks and reset tally
                    for r_key, entries in list(state_pre.get("global", {}).items()):
                        state_pre["global"][r_key] = [
                            e for e in entries
                            if str(e.get("title", "")).strip() != t_pre
                        ]
                    tally_bucket = state_pre.setdefault("global_tally", {})
                    if t_pre in tally_bucket:
                        del tally_bucket[t_pre]
                    revoked = True
                    log(self.cfg, f"[GLOBAL_ACH] rom_complete_set revoked for '{t_pre}': {len(new_tables)} new table(s) found ({', '.join(sorted(new_tables))})")
            if revoked:
                self._ach_state_save(state_pre)
                _rom_state_cache = state_pre
        except Exception:
            pass

        # Track whether the rom_state was modified by new-type rules so we save once at end
        _rom_state_dirty = False

        for rule in global_rules:
            title = (rule.get("title") or "Achievement").strip()
            if title not in seen_all:
                seen_all.add(title)
                all_titles.append(title)
            cond = (rule.get("condition") or {}) if isinstance(rule, dict) else {}
            rtype = str(cond.get("type") or "").lower()
            origin = rule.get("_origin") or ""
            try:
                if rtype == "nvram_overall":
                    field = cond.get("field")
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 1))
                    sv = int(self._nv_get_int_ci(start_audits, field, 0))
                    ev = int(self._nv_get_int_ci(end_audits, field, 0))
                    if sv < need <= ev:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title); seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                elif rtype == "nvram_delta":
                    field = cond.get("field")
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 1))
                    de = int(self._nv_get_int_ci(end_audits, field, 0))
                    ds = int(self._nv_get_int_ci(start_audits, field, 0))
                    d = de - ds
                    if d < 0:
                        d = 0
                    if d >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title); seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                elif rtype == "nvram_tally":
                    field = cond.get("field")
                    if not field or is_excluded_field(field):
                        continue
                    need = int(cond.get("min", 1))

                    state = self._ach_state_load()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }

                    delta = self._fuzzy_sum_deltas(deltas_ci, field)
                    roms_played = list(state.get("roms_played") or [])
                    abs_val = self._sum_field_across_all_roms(field, roms_played, _rom_audits_cache)

                    tally_bucket = state.setdefault("global_tally", {})
                    tally = tally_bucket.setdefault(title, {"progress": 0, "entries": []})

                    if not (title in already_global) and delta > 0:
                        now_iso = datetime.now(timezone.utc).isoformat()
                        tally["entries"].append({"rom": rom, "delta": delta, "ts": now_iso})
                        tally["progress"] += delta

                    effective_progress = max(int(tally["progress"]), abs_val)
                    tally["progress"] = effective_progress
                    self._ach_state_save(state)

                    if effective_progress >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})

                elif rtype == "rom_count":
                    state = _rom_state()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }
                    roms_played = list(state.get("roms_played") or [])
                    manufacturer = cond.get("manufacturer", "")
                    if manufacturer == "__any__":
                        min_brands = cond.get("min_brands")
                        if min_brands is not None:
                            # Count distinct brands represented in roms_played
                            brands = {_mfr_for(r) for r in roms_played}
                            brands.discard(None)
                            progress = len(brands)
                            need = int(min_brands)
                        else:
                            # Count total distinct ROMs
                            progress = len(set(roms_played))
                            need = int(cond.get("min", 1))
                    else:
                        played_for_mfr = {r for r in roms_played if _mfr_for(r) == manufacturer}
                        progress = len(played_for_mfr)
                        need = int(cond.get("min", 1))
                        if progress < need:
                            if self.cfg.LOG_CTRL:
                                log(self.cfg, f"[GLOBAL_ACH] rom_count '{title}': {progress}/{need} ({manufacturer}) – played={list(played_for_mfr)}, roms_played={roms_played}")
                    # Update tally for progress display (batched save at end)
                    state.setdefault("global_tally", {})[title] = {"progress": progress}
                    _rom_state_dirty = True
                    if progress >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                            log(self.cfg, f"[GLOBAL_ACH] rom_count triggered: '{title}' ({progress}/{need} tables played)")

                elif rtype == "rom_complete_set":
                    state = _rom_state()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }
                    manufacturer = cond.get("manufacturer", "")
                    roms_played = set(state.get("roms_played") or [])
                    installed = _installed_roms(manufacturer)
                    if not installed:
                        continue
                    installed_count = len(installed)
                    played_count = len(installed & roms_played)
                    # Store installed_count in global_tally for progress display (batched save at end)
                    state.setdefault("global_tally", {})[title] = {"progress": played_count, "installed_count": installed_count}
                    _rom_state_dirty = True
                    if played_count >= installed_count:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                            log(self.cfg, f"[GLOBAL_ACH] rom_complete_set triggered: '{title}' ({played_count}/{installed_count} tables played)")

                elif rtype == "rom_multi_brand":
                    state = _rom_state()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }
                    manufacturers = cond.get("manufacturers") or []
                    roms_played = list(state.get("roms_played") or [])
                    # Pre-compute set of manufacturers represented in roms_played
                    played_brands = {_mfr_for(r) for r in roms_played}
                    played_brands.discard(None)
                    brands_with_roms = {mfr for mfr in manufacturers if mfr in played_brands}
                    progress = len(brands_with_roms)
                    need = len(manufacturers)
                    # Update tally for progress display (batched save at end)
                    state.setdefault("global_tally", {})[title] = {"progress": progress, "installed_count": need}
                    _rom_state_dirty = True
                    if progress >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                            log(self.cfg, f"[GLOBAL_ACH] rom_multi_brand triggered: '{title}' ({progress}/{need} brands played)")

                elif rtype == "challenge_count":
                    state = _rom_state()
                    already_global = {
                        str(e.get("title", "")).strip()
                        for entries in state.get("global", {}).values()
                        for e in entries
                    }
                    challenge_type = str(cond.get("challenge_type") or "").lower()
                    need = int(cond.get("min", 1))
                    count = self._count_completed_challenges(challenge_type)
                    # Update tally for progress display (batched save at end)
                    state.setdefault("global_tally", {})[title] = {"progress": count}
                    _rom_state_dirty = True
                    if count >= need:
                        if title in already_global:
                            if title not in seen_rt:
                                retriggered_meta.append({"title": title, "origin": origin})
                                seen_rt.add(title)
                        elif title not in seen_aw:
                            awarded.append(title)
                            seen_aw.add(title)
                            awarded_meta.append({"title": title, "origin": origin})
                            log(self.cfg, f"[GLOBAL_ACH] challenge_count triggered: '{title}' ({count}/{need} {challenge_type} challenges)")

            except Exception:
                continue

        # Batch-save the rom_state if any new-type rules updated it
        if _rom_state_dirty and _rom_state_cache is not None:
            try:
                self._ach_state_save(_rom_state_cache)
            except Exception:
                pass

        return awarded, all_titles, awarded_meta, retriggered_meta
        
    def _count_completed_challenges(self, challenge_type: str) -> int:
        """Count completed challenges of a given type from the challenge history folder."""
        count = 0
        history_dir = os.path.join(self.cfg.BASE, "session_stats", "challenges", "history")
        if not os.path.isdir(history_dir):
            return 0
        try:
            for fname in os.listdir(history_dir):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(history_dir, fname)
                try:
                    hist = secure_load_json(fpath, {}) or {}
                    for entry in (hist.get("results") or []):
                        if str(entry.get("kind") or "").lower() == challenge_type:
                            count += 1
                except Exception:
                    continue
        except Exception:
            pass
        return count

    def _evaluate_challenge_count_achievements(self):
        """Evaluate challenge_count global achievements and award any newly reached ones."""
        try:
            gp = f_global_ach(self.cfg)
            if not os.path.exists(gp):
                return
            data = load_json(gp, {}) or {}
            rules = [r for r in (data.get("rules") or []) if isinstance(r, dict)]
            state = self._ach_state_load()
            already_global = {
                str(e.get("title", "")).strip()
                for entries in state.get("global", {}).values()
                for e in entries
            }
            awarded_meta = []
            for rule in rules:
                cond = (rule.get("condition") or {}) if isinstance(rule, dict) else {}
                if str(cond.get("type") or "").lower() != "challenge_count":
                    continue
                title = (rule.get("title") or "").strip()
                if not title or title in already_global:
                    continue
                challenge_type = str(cond.get("challenge_type") or "").lower()
                need = int(cond.get("min", 1))
                count = self._count_completed_challenges(challenge_type)
                # Update tally for progress display
                state.setdefault("global_tally", {})[title] = {"progress": count}
                if count >= need:
                    awarded_meta.append({"title": title, "origin": "global_achievements"})
                    log(self.cfg, f"[GLOBAL_ACH] challenge_count triggered: '{title}' ({count}/{need} {challenge_type} challenges)")
            if awarded_meta:
                self._ach_record_unlocks("global", self.current_rom or "__challenge__", awarded_meta)
                self._ach_state_save(state)
                try:
                    self._emit_achievement_toasts(awarded_meta, seconds=5)
                except Exception:
                    pass
            else:
                self._ach_state_save(state)
        except Exception as e:
            log(self.cfg, f"[GLOBAL_ACH] challenge_count eval failed: {e}", "WARN")

    def _collect_global_rules_for_rom(self, rom: str) -> list[dict]:
        rules_out = []
        seen_titles = set()

        gp = f_global_ach(self.cfg)
        if os.path.exists(gp):
            data = load_json(gp, {}) or {}
            for r in (data.get("rules") or []):
                if not isinstance(r, dict):
                    continue
                if self._is_rule_global(r, origin="global_achievements"):
                    t = (r.get("title") or "Achievement").strip()
                    if t not in seen_titles:
                        seen_titles.add(t)
                        r2 = dict(r)
                        r2["_origin"] = "global_achievements"
                        rules_out.append(r2)
        rpath = os.path.join(p_rom_spec(self.cfg), f"{rom}.ach.json")
        if os.path.exists(rpath):
            data = load_json(rpath, {}) or {}
            for r in (data.get("rules") or []):
                if not isinstance(r, dict):
                    continue
                if self._is_rule_global(r, origin="rom_specific"):
                    t = (r.get("title") or "Achievement").strip()
                    if t not in seen_titles:
                        seen_titles.add(t)
                        r2 = dict(r)
                        r2["_origin"] = "rom_specific"
                        rules_out.append(r2)
        return rules_out     
        
    def _is_rule_global(self, rule: dict, origin: str) -> bool:
        scope = str(rule.get("scope") or "").strip().lower()
        return scope == "global"
 
    def _ensure_global_ach(self):
        path = f_global_ach(self.cfg)
        if os.path.exists(path):
            try:
                data = load_json(path, {}) or {}
                cur = data.get("rules") or []
                if isinstance(cur, list) and len(cur) >= 136:  # 150 nvram_tally + manufacturer + challenge rules (19 session_time rules removed)
                    # Force regeneration if any removed categories are still present
                    REMOVED_FIELDS = {"Drop Targets", "Spinner", "Orbits", "Modes Started", "Modes Completed"}
                    has_removed = any(
                        cond.get("field") in REMOVED_FIELDS
                        for r in cur
                        if isinstance(r, dict)
                        for cond in [r.get("condition", {})]
                        if isinstance(cond, dict) and cond.get("type") == "nvram_tally"
                    )
                    has_global_session_time = any(
                        isinstance(r, dict)
                        and isinstance(r.get("condition"), dict)
                        and r["condition"].get("type") == "session_time"
                        and str(r.get("scope", "")).lower() == "global"
                        for r in cur
                    )
                    if not has_removed and not has_global_session_time:
                        return
            except Exception:
                pass
        try:
            rules = self._generate_default_global_rules()
            save_json(path, {"rules": rules})
            log(self.cfg, f"global_achievements.json created/refreshed with {len(rules)} rules")
        except Exception as e:
            log(self.cfg, f"[GLOBAL_ACH] generation failed: {e}", "WARN")

    def _export_summary(self, end_audits: dict, duration_sec: int):
        from datetime import timezone
        summary_path = os.path.join(p_highlights(self.cfg), self.SUMMARY_FILENAME)
        try:
            best_ball = None
            try:
                balls = self.ball_track.get("balls", [])
                if balls:
                    best_ball = max(balls, key=lambda b: (int(b.get("score", 0)), int(b.get("duration", 0))))
            except Exception:
                best_ball = None

            try:
                global_deltas = self._compute_session_deltas(self.start_audits, end_audits)
            except Exception:
                global_deltas = {}

            p1 = self.players.get(1, {}) or {}
            players_out = [{
                "player": 1,
                "playtime_sec": int(p1.get("active_play_seconds", 0.0) or 0),
                "deltas": {k: v for k, v in (p1.get("session_deltas", {}) or {}).items() if "score" not in k.lower()},
                "events": p1.get("event_counts", {}) or {},
            }]

            payload = {
                "rom": self.current_rom,
                "table": self.current_table,
                "duration_sec": int(duration_sec or 0),
                "best_ball": best_ball,
                "players": players_out,
                "end_audits": end_audits,
                "global_deltas": global_deltas,
                "end_timestamp": datetime.now(timezone.utc).isoformat(),
                # Convenience fields for dashboard display
                "score": int(best_ball.get("score", 0)) if isinstance(best_ball, dict) else None,
            }

            save_json(summary_path, payload)

        except Exception as e:
            log(self.cfg, f"[SUMMARY] export failed: {e}", "WARN")


    def _ach_state_load(self) -> dict:
        p = f_achievements_state(self.cfg)
        return secure_load_json(p, {"global": {}, "session": {}})

    def _ach_state_save(self, state: dict):
        p = f_achievements_state(self.cfg)
        secure_save_json(p, state)

    # Maps known ROM prefixes to their manufacturer names.
    # Prefix matching is used: exact ROM name, then progressively shorter underscore-split segments,
    # then just the leading alphabetic characters.
    MANUFACTURER_MAP: dict[str, str] = {
        # Bally
        "afm": "Bally", "tom": "Bally", "mm": "Bally", "cv": "Bally",
        "cp": "Bally", "cftbl": "Bally", "pz": "Bally", "fh": "Bally", "bbb": "Bally",
        "trucksp": "Bally", "theatre": "Bally", "scared": "Bally", "eatpm": "Bally",
        "centaur": "Bally", "paragon": "Bally", "eightball": "Bally", "medusa": "Bally",
        "xenon": "Bally", "vector": "Bally", "embryon": "Bally", "speakesy": "Bally",
        "hotdoggin": "Bally", "mystic": "Bally", "fireball": "Bally", "frontier": "Bally",
        "harlem": "Bally", "ngndshkr": "Bally", "goldball": "Bally", "grandslm": "Bally",
        "kosteel": "Bally", "xsandos": "Bally", "blackblt": "Bally", "cybrnaut": "Bally",
        "beatclck": "Bally", "atlantis": "Bally", "spy_hunter": "Bally",
        "flashgdn": "Bally", "smman": "Bally",
        # Williams
        "ts": "Williams", "t2": "Williams", "ij": "Williams", "wcs": "Williams",
        "dw": "Williams", "br": "Williams", "rs": "Williams", "ft": "Williams",
        "gi": "Williams", "hurr": "Williams", "dm": "Williams",
        "tz": "Williams", "ww": "Williams", "taf": "Williams", "nf": "Williams",
        "bop": "Williams", "whirl": "Williams", "rollr": "Williams",
        "ss": "Williams", "taxi": "Williams", "pool": "Williams", "diner": "Williams",
        "jy": "Williams", "poto": "Williams", "esha": "Williams", "fire": "Williams",
        "sttng": "Williams", "jd": "Williams", "afv": "Williams", "cc": "Williams",
        "corv": "Williams", "dh": "Williams", "i500": "Williams", "jb": "Williams",
        "jm": "Williams", "ngg": "Williams", "pop": "Williams", "sc": "Williams",
        "sf2": "Williams", "tod": "Williams", "totan": "Williams", "wd": "Williams",
        "congo": "Williams", "dracula": "Williams", "mb": "Williams",
        "nbaf": "Williams", "cactjack": "Williams", "strik": "Williams",
        # Stern (modern)
        "godzilla": "Stern", "deadpool": "Stern", "got": "Stern", "munsters": "Stern",
        "aerosmith": "Stern", "lotr": "Stern", "sopranos": "Stern", "simpsons": "Stern",
        "metallica": "Stern", "twd": "Stern", "mustang": "Stern", "starwars": "Stern",
        "ghostbusters": "Stern", "batman66": "Stern", "kiss": "Stern", "wpt": "Stern",
        "elvis": "Stern", "ironman": "Stern", "xmen": "Stern", "transformers": "Stern",
        "avatar": "Stern", "tron": "Stern", "acdc": "Stern", "spider": "Stern",
        "avengers": "Stern", "nbafastbreak": "Stern",
        # Data East
        "lw3": "Data East", "tftc": "Data East", "hook": "Data East", "btmn": "Data East",
        "rab": "Data East", "gnr": "Data East", "stwr": "Data East", "tmnt": "Data East",
        "trek": "Data East", "simp": "Data East", "wwfr": "Data East", "mn_180": "Data East",
        "rctycn": "Data East", "aar": "Data East",
        # Gottlieb / Premier
        "cue": "Gottlieb", "teed": "Gottlieb", "sprbrk": "Gottlieb", "gladiatr": "Gottlieb",
        "shaq": "Gottlieb", "freddy": "Gottlieb", "wipe": "Gottlieb", "sfight2": "Gottlieb",
        "silvslug": "Gottlieb", "waterwld": "Gottlieb",
        # Sega
        "baywatch": "Sega", "mav": "Sega", "frankenstein": "Sega", "id4": "Sega",
        "twister": "Sega", "apollo": "Sega", "gw": "Sega", "jpark": "Sega",
        "swtril": "Sega", "spacejam": "Sega", "viprsega": "Sega", "ctcheese": "Sega",
        "goldeneye": "Sega", "xfiles": "Sega", "starship": "Sega", "harley": "Sega",
        "godzilla_sega": "Sega", "lostspc": "Sega",
        # Capcom
        "kp": "Capcom", "bbb_capcom": "Capcom", "pm": "Capcom", "flip": "Capcom",
        "bsv": "Capcom", "kingspin": "Capcom",
    }

    def _get_manufacturer_from_rom(self, rom: str) -> str | None:
        """Return the manufacturer for a given ROM name, e.g. 'Bally' for 'afm_113b'.

        Lookup order:
        1. MANUFACTURER_MAP — exact match on the lowercased ROM name.
        2. MANUFACTURER_MAP — progressively shorter underscore-delimited prefixes
           (e.g. 'afm_113b' → tries 'afm_113b', then 'afm').
        3. MANUFACTURER_MAP — leading alphabetic characters only
           (e.g. 'afm113' → 'afm').
        4. ROMNAMES regex fallback (legacy behaviour, skips bare version strings).
        """
        rom_lower = rom.lower()
        # 1. Exact match
        if rom_lower in self.MANUFACTURER_MAP:
            return self.MANUFACTURER_MAP[rom_lower]
        # 2. Progressively shorter underscore-split prefixes
        parts = rom_lower.split("_")
        for i in range(len(parts) - 1, 0, -1):
            prefix = "_".join(parts[:i])
            if prefix in self.MANUFACTURER_MAP:
                return self.MANUFACTURER_MAP[prefix]
        # 3. Leading alphabetic characters (strips trailing digits / underscores)
        base_m = re.match(r'^([a-z]+)(?=\d|_|$)', rom_lower)
        if base_m and base_m.group(1) in self.MANUFACTURER_MAP:
            return self.MANUFACTURER_MAP[base_m.group(1)]
        # 4. Fallback: parse ROMNAMES entry (e.g. "Table Name (Manufacturer)")
        name = self.ROMNAMES.get(rom) if hasattr(self, "ROMNAMES") else None
        if not name:
            return None
        m = re.search(r'\(([^)]+)\)$', str(name).strip())
        if m:
            val = m.group(1)
            # Ignore version strings like "1.13b / S1.1" — manufacturer names never start with a digit
            if re.match(r'^\d', val):
                return None
            return val
        return None

    def _resolve_emoji_for_rom(self, rom: str) -> str:
        """Automatically resolve a fitting emoji for a ROM based on table name keywords."""
        romnames = getattr(self, "ROMNAMES", {}) or {}
        table_name = romnames.get(rom, "").lower()

        # 1. Keyword match on table name (longest keywords first to prefer specific matches)
        for keyword, emoji in sorted(TABLE_EMOJI_KEYWORDS.items(),
                                     key=lambda x: len(x[0]), reverse=True):
            if keyword in table_name:
                return emoji

        # 2. Manufacturer fallback
        mfr = self._get_manufacturer_from_rom(rom)
        if mfr and mfr in MANUFACTURER_EMOJI:
            return MANUFACTURER_EMOJI[mfr]

        # 3. Generic pinball fallback
        return "🎯"

    # Keyword patterns for fuzzy matching of canonical global field names to ROM-specific NVRAM labels.
    # Each entry maps a canonical name to a list of keyword-tuples; ALL keywords in a tuple must be
    # present (case-insensitive) in an NVRAM field name for it to match.
    _NVRAM_TALLY_PATTERNS: dict[str, list[tuple[str, ...]]] = {
        "Ball Saves":       [("ball save",), ("ball saver",)],
        "Ramps Made":       [("ramp",)],
        # "jckpot" covers abbreviated spellings like "TROPICAL JCKPOTS"
        "Jackpots":         [("jackpot",), ("jckpot",)],
        "Total Multiballs": [("multiball",), ("multi-ball",)],
        "Loops":            [("loop",)],
        "Combos":           [("combo",)],
        "Extra Balls":      [("extra ball",)],
        "Games Started":    [("games started",), ("games played",)],
        "Balls Played":     [("balls played",), ("ball count",), ("total balls",)],
        # "MINUTES ON" is the standard WPC/Williams NVRAM field for cumulative play time in minutes.
        # "minute" covers abbreviated variants like "MINUTES ON" or "Minutes On".
        "MINUTES ON":       [("minutes on",), ("minute",)],
    }

    def _fuzzy_sum_deltas(self, deltas_ci: dict, canonical_field: str) -> int:
        """Return the sum of all deltas from fields in deltas_ci that match canonical_field.

        First tries an exact key lookup (current behaviour).  If that yields 0, falls back to
        keyword-based fuzzy matching so that ROM-specific labels like "Ball Saver Cnt" are
        matched by the canonical name "Ball Saves".
        """
        exact = int(deltas_ci.get(canonical_field, 0) or 0)
        if exact > 0:
            return exact

        patterns = self._NVRAM_TALLY_PATTERNS.get(canonical_field)
        if not patterns:
            return 0

        total = 0
        counted: set[str] = set()
        for k, v in deltas_ci.items():
            kl = k.lower()
            for kws in patterns:
                if all(kw in kl for kw in kws):
                    if k not in counted:
                        total += int(v or 0)
                        counted.add(k)
                    break
        return total

    def _fuzzy_sum_field(self, audits: dict, canonical_field: str) -> int:
        """Return the sum of all values in *audits* that fuzzy-match *canonical_field*.

        Uses the same _NVRAM_TALLY_PATTERNS as _fuzzy_sum_deltas so that
        ROM-specific labels like "MAIN M.B. JACKPOTS" are matched by "Jackpots".
        Falls back to exact case-insensitive lookup when no pattern entry exists.
        """
        patterns = self._NVRAM_TALLY_PATTERNS.get(canonical_field)
        if not patterns:
            return int(self._nv_get_int_ci(audits, canonical_field, 0))

        total = 0
        counted: set[str] = set()
        for k, v in audits.items():
            kl = k.lower()
            for kws in patterns:
                if all(kw in kl for kw in kws):
                    if k not in counted:
                        try:
                            total += int(v or 0)
                        except (ValueError, TypeError):
                            pass
                        counted.add(k)
                    break
        return total

    def _sum_field_across_all_roms(self, field: str, roms_played: list,
                                    _audits_cache: dict | None = None) -> int:
        """Sum *field* across all played ROMs using fuzzy NVRAM label matching.

        *roms_played* is the list of ROM names from the achievements state.
        *_audits_cache* is an optional dict keyed by ROM name that is populated on
        first use so repeated calls during one evaluation pass avoid re-reading files.
        """
        # Activate batch-logging mode so _ensure_rom_specific collects ROM_SPEC
        # creation events instead of logging them individually.
        batch_not_active = not isinstance(getattr(self, "_rom_spec_batch", None), list)
        if batch_not_active:
            self._rom_spec_batch = []
        total = 0
        try:
            for r in roms_played:
                try:
                    if _audits_cache is not None:
                        if r not in _audits_cache:
                            audits, _, _ = self.read_nvram_audits_with_autofix(r)
                            _audits_cache[r] = audits
                        audits = _audits_cache[r]
                    else:
                        audits, _, _ = self.read_nvram_audits_with_autofix(r)
                    if audits:
                        total += self._fuzzy_sum_field(audits, field)
                except Exception:
                    continue
        finally:
            if batch_not_active:
                collected = self._rom_spec_batch or []
                self._rom_spec_batch = None
                if collected:
                    seen: set[str] = set()
                    unique = []
                    for r, n in collected:
                        if r not in seen:
                            seen.add(r)
                            unique.append((r, n))
                    if unique:
                        summary = ", ".join(f"{r} ({n})" for r, n in unique)
                        log(self.cfg, f"[ROM_SPEC] Batch-generated achievement rules for {len(unique)} ROM(s): {summary}")
        return total

    def _scan_installed_roms_by_manufacturer(self, manufacturer: str) -> set:
        """Scan TABLES_DIR for .vpx files and return ROM names matching the given manufacturer.
        Only includes ROMs that have an available NVRAM map (consistent with roms_played tracking).
        If manufacturer is '__any__', return all map-having ROMs found regardless of manufacturer.
        Results are cached after the first scan to avoid repeated blocking filesystem walks."""
        # Return from cache if available
        if self._installed_roms_scan_done:
            if manufacturer == "__any__":
                return set(self._installed_roms_scan_cache.get("__all_with_map__", set()))
            return set(self._installed_roms_scan_cache.get(manufacturer, set()))

        # First call: do the full scan ONCE and cache ALL results
        result_all: set = set()  # all ROMs with maps
        result_by_mfr: dict = {}
        tables_dir = getattr(self.cfg, "TABLES_DIR", None)
        if tables_dir and os.path.isdir(tables_dir):
            skipped = 0
            vpxtool_warn = 0
            for root, _dirs, files in os.walk(tables_dir):
                for fname in files:
                    if not fname.lower().endswith(".vpx"):
                        continue
                    vpx_path = os.path.join(root, fname)
                    try:
                        rom = run_vpxtool_get_rom(self.cfg, vpx_path, suppress_warn=True)
                    except Exception:
                        rom = None
                    if not rom:
                        vpxtool_warn += 1
                        continue
                    # Only include ROMs that have an NVRAM map — consistent with roms_played tracking
                    # (roms_played is only updated when _has_any_map() is True)
                    if not self._has_any_map(rom):
                        skipped += 1
                        continue
                    result_all.add(rom)
                    mfr = self._get_manufacturer_from_rom(rom)
                    if mfr:
                        result_by_mfr.setdefault(mfr, set()).add(rom)
                    self._rom_emoji_cache[rom] = self._resolve_emoji_for_rom(rom)
            if skipped > 0 or vpxtool_warn > 0:
                log(self.cfg, f"[SCAN] Table scan complete: {len(result_all)} ROMs with maps, {skipped} skipped (no map), {vpxtool_warn} vpxtool warnings", "INFO")

        self._installed_roms_scan_cache = dict(result_by_mfr)
        self._installed_roms_scan_cache["__all_with_map__"] = result_all
        self._installed_roms_scan_done = True

        if manufacturer == "__any__":
            return set(result_all)
        return set(result_by_mfr.get(manufacturer, set()))

    def _append_nvram_dump_block(self, lines: list[str], audits: dict):
        if not isinstance(audits, dict) or not audits:
            lines.append("(none)")
            return

        for k in sorted(audits.keys(), key=lambda x: str(x).lower()):
            try:
                label = str(k)
            except Exception:
                label = repr(k)

            try:
                value = audits.get(k, "")
            except Exception:
                value = ""

            try:
                value_txt = str(value)
            except Exception:
                value_txt = repr(value)

            lines.append(f"{label:<30} {value_txt}")

    def _ach_record_unlocks(self, kind: str, rom: str, titles: list, retriggered: list = None):
        if not rom or (not titles and not retriggered):
            return
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        state = self._ach_state_load()
        old_level_info = compute_player_level(state)
        bucket = state.setdefault(kind, {})
        storage_key = "__global__" if kind == "global" else rom
        lst = bucket.setdefault(storage_key, [])

        def _entry_title(e):
            try:
                return str(e.get("title")).strip()
            except Exception:
                return str(e).strip()

        # Build a mapping of existing entries by title to easily find and update them
        existing_by_title = {}
        for e in lst:
            if isinstance(e, dict):
                t_val = _entry_title(e)
                if t_val:
                    existing_by_title[t_val] = e

        _current_vps_id = ""
        try:
            from ui_vps import _load_vps_mapping
            _vps_mapping = _load_vps_mapping(self.cfg)
            _current_vps_id = (_vps_mapping.get(rom) or "").strip()
        except Exception:
            pass

        added = 0
        updated = 0
        for t in titles:
            if isinstance(t, dict):
                title = str(t.get("title", "")).strip()
                origin = t.get("origin")
            else:
                title = str(t).strip()
                origin = None

            if not title:
                continue

            if title in existing_by_title:
                # Already unlocked – skip; backfill only happens on re-trigger (see below)
                continue

            # New achievement
            entry = {"title": title, "ts": now_iso}
            if origin:
                entry["origin"] = str(origin)
            if _current_vps_id:
                entry["vps_id"] = _current_vps_id
            lst.append(entry)
            existing_by_title[title] = entry
            added += 1

        # Process retriggered achievements: backfill vps_id only if the entry has none (freeze semantics)
        for t in (retriggered or []):
            if isinstance(t, dict):
                title = str(t.get("title", "")).strip()
            else:
                title = str(t).strip()
            if not title:
                continue
            if title in existing_by_title:
                existing_entry = existing_by_title[title]
                stored_vps = (existing_entry.get("vps_id") or "").strip()
                if _current_vps_id and not stored_vps:
                    existing_entry["vps_id"] = _current_vps_id
                    updated += 1
                    try:
                        toast_title = f"{title}\n{rom}\nVPS-ID linked"
                        self.bridge.ach_toast_show.emit(toast_title, rom, 5)
                    except Exception:
                        pass

        if added or updated:
            self._ach_state_save(state)
            if added:
                new_level_info = compute_player_level(state)
                if new_level_info["level"] > old_level_info["level"]:
                    try:
                        self.bridge.level_up_show.emit(new_level_info["name"], new_level_info["level"])
                    except Exception:
                        pass
            try:
                if getattr(self, "bridge", None) and hasattr(self.bridge, "achievements_updated"):
                    self.bridge.achievements_updated.emit()
            except Exception:
                pass
            try:
                if self.cfg.CLOUD_ENABLED:
                    player_name = self.cfg.OVERLAY.get("player_name", "Player")
                    CloudSync.upload_full_achievements(self.cfg, state, player_name)
            except Exception:
                pass
  
    def _emit_achievement_toasts(self, titles, seconds: int = 5, rom_override: str | None = None):
        try:
            already_shown = getattr(self, "_toasted_titles", set())
            for t in titles or []:
                if isinstance(t, dict):
                    title = str(t.get("title", "")).strip()
                else:
                    title = str(t).strip()

                title = title.replace(" (Session)", "").replace(" (Global)", "")

                if title and title not in already_shown:
                    already_shown.add(title)
                    rom_value = rom_override if rom_override is not None else (self.current_rom or "")
                    log(self.cfg, f"[ACH] Emitting toast: '{title}' rom='{rom_value}'")
                    try:
                        self.bridge.ach_toast_show.emit(title, rom_value, int(seconds))
                    except Exception as e:
                        log(self.cfg, f"[ACH] Toast emit failed: {e}", "WARN")
            self._toasted_titles = already_shown
        except Exception as e:
            log(self.cfg, f"[ACH] _emit_achievement_toasts error: {e}", "WARN")
  
    def _on_session_end_record_achievements(self, rom: str, session_titles: list, global_titles: list):
        try:
            session_titles = session_titles or []
            global_titles = global_titles or []
            self._ach_record_unlocks("session", rom, session_titles)
            self._ach_record_unlocks("global", rom, global_titles)
            out = []
            for t in session_titles:
                if isinstance(t, dict):
                    out.append(t)
                else:
                    out.append({"title": str(t), "origin": "session"})
            for t in global_titles:
                if isinstance(t, dict):
                    out.append(t)
                else:
                    out.append({"title": str(t), "origin": "global"})
            self.last_unlocked_achievements = out
        except Exception:
            pass
  
