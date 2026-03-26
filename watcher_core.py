from __future__ import annotations

# Re-export everything from config for backward compatibility
from config import *
from config import (
    APP_DIR, AppConfig, WATCHER_VERSION, DEFAULT_OVERLAY, CONFIG_FILE,
    EXCLUDED_FIELDS, EXCLUDED_FIELDS_LC, DEFAULT_LOG_SUPPRESS, CHALLENGES_ENABLED,
    VK_LSHIFT, VK_RSHIFT, HEAT_HOLD_RATE, HEAT_PRESS_BURST, HEAT_COOLDOWN_RATE,
    TABLE_EMOJI_KEYWORDS, MANUFACTURER_EMOJI,
    is_excluded_field, log, load_json, save_json, secure_load_json, secure_save_json,
    write_text, ensure_dir, sanitize_filename, apply_tooltips, resource_path,
    compute_player_level, compute_rarity, LEVEL_TABLE, PRESTIGE_THRESHOLD, MAX_PRESTIGE,
    RARITY_TIERS, BADGE_DEFINITIONS, BADGE_LOOKUP, BADGE_CHECKS, evaluate_badges,
    p_maps, p_local_maps, p_session, p_highlights, p_achievements, p_rom_spec,
    f_global_ach, f_achievements_state, f_log, f_index, f_romnames,
    p_vps, p_vps_img, f_vps_mapping, f_vpsdb_cache,
    _strip_version_from_name, _clean_table_name, _fetch_json_url, _fetch_bytes_url,
    run_vpxtool_get_rom, run_vpxtool_get_script_authors, run_vpxtool_info_show,
    JOYINFOEX, JOY_RETURNALL, JOYERR_NOERROR, _joyGetPosEx,
    WM_HOTKEY, WM_KEYDOWN, WM_SYSKEYDOWN, WH_KEYBOARD_LL,
    KBDLLHOOKSTRUCT, GlobalKeyHook, RAWINPUTDEVICE, _RegisterRawInputDevices,
    _MapVirtualKeyW, _GetKeyNameTextW, vk_to_name, vk_to_name_en, vsc_to_vk,
    get_vpx_ini_path_for_current_user, parse_vpx_flipper_bindings,
    register_raw_input_for_window, RIDEV_INPUTSINK,
)
from cloud_sync import CloudSync
from achievements import AchievementsMixin

import os, sys, json, re, glob, threading, uuid, time, random
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict, Counter
import ctypes
from ctypes import wintypes

class Watcher(AchievementsMixin):
    MIN_SEGMENTS_FOR_CLASSIFICATION = 1
    SUMMARY_FILENAME = "session_latest.summary.json"
    
    def __init__(self, cfg: AppConfig, bridge: "Bridge"):
        self.cfg = cfg
        self.bridge = bridge
        self._stop = threading.Event()
        self._flush_lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self._last_logged_rom = None
        self._map_found_logged_roms: set = set()
        self._rom_spec_batch: Optional[list] = None

        self.current_table: Optional[str] = None
        self.current_rom: Optional[str] = None
        self.start_time: Optional[float] = None
        self.game_active: bool = False
        self.start_audits: Dict[str, Any] = {}
        self.current_player = 1
        self.players: Dict[int, Dict[str, Any]] = {}
        self.ball_track = {
            "active": False, "index": 0, "start_time": None,
            "score_base": 0, "last_balls_played": None, "balls": []
        }
        self._last_audits_global: Dict[str, Any] = {}
        self._nvram_cache_rom: str = ""
        self._nvram_cache_mtime: float = 0.0
        self._nvram_cache_result: Tuple[Dict[str, Any], List[str], bool] = ({}, [], False)
        self.INDEX: Dict[str, Any] = {}
        self.ROMNAMES: Dict[str, Any] = {}
        
        self._field_layout_cache: Dict[str, Dict[str, Any]] = {}
        self.current_segment_provisional_diff: Dict[str, int] = {}
        self.include_current_segment_in_overlay = True
        self._control_fields_cache: Dict[str, List[dict]] = {}

        self._installed_roms_scan_cache: dict = {}   # manufacturer -> set of ROM names; '__all_with_map__' -> all ROMs with maps
        self._installed_roms_scan_done: bool = False
        self._rom_emoji_cache: dict = {}  # rom -> emoji string
        
        self.snapshot_mode = True
        self.snap_initialized = False
        self.field_stats = {}
        self.bootstrap_phase = False

        # In-memory cache of the last overlay snapshot payload (avoids disk read race)
        self._overlay_snapshot_cache: Optional[dict] = None

        self._flip_init_state()
        self._toasted_titles: set = set()

    def _map_fields_for_rom(self, rom: str) -> list[str]:
        out = []
        try:
            fields, _src = self.load_map_for_rom(rom)
            for f in (fields or []):
                lbl = str(f.get("label") or f.get("name") or "").strip()
                if not lbl:
                    continue
                ll = lbl.lower()
                if "score" in ll:
                    continue
                if is_excluded_field(lbl) or self.NOISE_REGEX.search(lbl):
                    continue
                out.append(lbl)
        except Exception:
            pass
        # unique preserve order
        seen = set()
        uniq = []
        for x in out:
            k = x.lower()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(x)
        return uniq

    def _flip_init_state(self):
        self._flip = {
            "active": False,
            "threshold": 500,
            "left": 0,
            "right": 0,
            "vk_left": 0,
            "vk_right": 0,
            "joy_left": 0,
            "joy_right": 0,
            "started_at": 0.0,
        }
        self._flip_inputs = {
            "kbd": None,
            "joy_running": False,
            "joy_thread": None,
            "joy_prev_masks": {},
        }
        self._heat_inputs = {
            "joy_running": False,
            "joy_thread": None,
        }

    def start_challenge_input_bindings(self) -> None:

        if getattr(self, "_ch_inputs", None) and self._ch_inputs.get("running"):
            return
        debounce_ms = int((self.cfg.OVERLAY or {}).get("ch_hotkey_debounce_ms", 120))
        self._ch_inputs = {
            "running": True,
            "active_source": None, 
            "nav_enabled": False,
            "last_press_ts": 0.0,
            "debounce_s": max(0.01, debounce_ms / 1000.0),
            "joy_running": False,
            "joy_last": 0,
            "kbd": None,
            "joy_thread": None,
        }
        try:
            hot_vk = int((self.cfg.OVERLAY or {}).get("challenge_hotkey_vk", 0x7A))
            left_vk = int((self.cfg.OVERLAY or {}).get("challenge_left_vk", 0x25))
            right_vk = int((self.cfg.OVERLAY or {}).get("challenge_right_vk", 0x27))
            kb_bindings = [
                {"get_vk": lambda hv=hot_vk: hv, "on_press": lambda: self._on_challenge_hotkey_press("keyboard")},
                {"get_vk": lambda lv=left_vk: lv, "on_press": lambda: self._on_challenge_nav_left("keyboard")},
                {"get_vk": lambda rv=right_vk: rv, "on_press": lambda: self._on_challenge_nav_right("keyboard")},
            ]
            self._ch_inputs["kbd"] = GlobalKeyHook(kb_bindings)
            self._ch_inputs["kbd"].install()
            log(self.cfg, "[CH-INPUT] Global keyboard hook installed for challenge controls")
        except Exception as e:
            log(self.cfg, f"[CH-INPUT] Keyboard hook install failed: {e}", "WARN")
        try:
            self._ch_inputs["joy_running"] = True
            t = threading.Thread(target=self._joystick_poll_loop, daemon=True, name="ChallengeJoyPoll")
            self._ch_inputs["joy_thread"] = t
            t.start()
            log(self.cfg, "[CH-INPUT] Joystick polling started for challenge controls")
        except Exception as e:
            log(self.cfg, f"[CH-INPUT] Joystick thread start failed: {e}", "WARN")
 
    def _player_balls_count(self, pid: int) -> int:
        try:
            balls = self.ball_track.get("balls", []) or []
            return sum(1 for b in balls if int(b.get("pid", 1)) == 1)
        except Exception:
            return 0
            
    def _alt_f4_visual_pinball_player(self, wait_ms: int = 3000) -> bool:
        try:
            import ctypes, time
            from ctypes import wintypes
            import win32gui, win32con, win32api
            pids = set()
            hwnds = []
            def _cb(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    title = (win32gui.GetWindowText(hwnd) or "").strip()
                    if title.startswith("Visual Pinball Player"):
                        hwnds.append(hwnd)
                        pid = wintypes.DWORD(0)
                        ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
                        if pid.value:
                            pids.add(int(pid.value))
                except Exception:
                    pass
                return True
            win32gui.EnumWindows(_cb, None)
            if not hwnds:
                return True  
            VK_MENU = 0x12   
            VK_F4 = 0x73
            KEYEVENTF_KEYUP = 0x0002
            for hwnd in hwnds:
                try:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    time.sleep(0.05)
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                    except Exception:
                        try:
                            fg = win32gui.GetForegroundWindow()
                            tid1 = ctypes.windll.user32.GetWindowThreadProcessId(fg, None)
                            tid2 = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                            ctypes.windll.user32.AttachThreadInput(tid1, tid2, True)
                            win32gui.SetForegroundWindow(hwnd)
                            ctypes.windll.user32.AttachThreadInput(tid1, tid2, False)
                        except Exception:
                            pass
                    time.sleep(0.05)
                    win32api.keybd_event(VK_MENU, 0, 0, 0)
                    time.sleep(0.01)
                    win32api.keybd_event(VK_F4, 0, 0, 0)
                    time.sleep(0.02)
                    win32api.keybd_event(VK_F4, 0, KEYEVENTF_KEYUP, 0)
                    time.sleep(0.01)
                    win32api.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
                    time.sleep(0.05)
                except Exception:
                    continue
            k32 = ctypes.windll.kernel32
            SYNCHRONIZE = 0x00100000
            handles = []
            for pid in pids:
                try:
                    h = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
                    if h:
                        handles.append(h)
                except Exception:
                    pass
            if handles:
                arr_type = wintypes.HANDLE * len(handles)
                arr = arr_type(*handles)
                k32.WaitForMultipleObjects(len(handles), arr, True, int(wait_ms))
                for h in handles:
                    try:
                        k32.CloseHandle(h)
                    except Exception:
                        pass
            else:
                time.sleep(min(1.0, wait_ms / 1000.0))
            still = []
            try:
                out = subprocess.check_output(["tasklist"], creationflags=0x08000000).decode(errors="ignore").lower()
                for pid in pids:
                    if str(pid) in out:
                        still.append(pid)
            except Exception:
                pass

            return len(still) == 0
        except Exception:
            return False
 
    def _base_map_exists(self, rom: str) -> bool:

        if not rom:
            return False
        maps_dir = p_local_maps(self.cfg)
        return (
            os.path.isfile(os.path.join(maps_dir, f"{rom}.json")) or
            os.path.isfile(os.path.join(maps_dir, f"{rom}.map.json"))
        )
 
    def _has_any_map(self, rom: str) -> bool:
        if not rom:
            return False
        try:
            m1 = os.path.join(p_local_maps(self.cfg), f"{rom}.json")
            m2 = os.path.join(p_local_maps(self.cfg), f"{rom}.map.json")
            if os.path.isfile(m1) or os.path.isfile(m2):
                return True
            fields, _ = self._try_load_map_for(rom)
            return bool(fields)
        except Exception:
            return False
 
    def _emit_mini_info_if_missing_map(self, rom: str, seconds: int = 5):
        """Non-blocking: spawns a background thread to wait for VPX window and show info."""
        import threading
        def _worker():
            import time
            try:
                import win32gui
            except ImportError:
                return
            try:
                if not rom:
                    return
                if self._has_any_map(rom):
                    return
                log(self.cfg, f"[OVERLAY] no-map worker start: rom={rom!r}")

                shown = getattr(self, "_mini_info_shown_for_rom", None)
                if not isinstance(shown, set):
                    shown = set()
                if rom in shown:
                    return

                def _vpx_window_visible() -> bool:
                    found = False
                    def _cb(hwnd, _):
                        nonlocal found
                        try:
                            title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
                            if "visual pinball player" in title and win32gui.IsWindowVisible(hwnd):
                                found = True
                                return False
                        except Exception:
                            pass
                        return True
                    try:
                        win32gui.EnumWindows(_cb, None)
                    except Exception:
                        return False
                    return found

                for _ in range(40):  # max 20s warten statt endlos
                    if self._stop.is_set():
                        return
                    try:
                        if not self.game_active:
                            return
                    except Exception:
                        return
                    if _vpx_window_visible():
                        msg = f"NVRAM map not found for {rom}."
                        dur = max(3, int(seconds))
                        try:
                            self.bridge.challenge_info_show.emit(msg, dur, "#FF3B30")
                            shown.add(rom)
                            self._mini_info_shown_for_rom = shown
                            log(self.cfg, f"[INFO] Mini overlay (no map) shown for {rom}")
                        except Exception as e:
                            log(self.cfg, f"[OVERLAY] mini info emit failed: {e}", "WARN")
                        return
                    time.sleep(0.5)
            except Exception as e:
                log(self.cfg, f"[OVERLAY] mini info worker failed: {e}", "WARN")

        try:
            t = threading.Thread(target=_worker, daemon=True, name="MiniInfoMissingMap")
            t.start()
        except Exception:
            pass

    def _emit_mini_info_if_missing_vps_id(self, rom: str, seconds: int = 8):
        """Non-blocking: spawns a background thread to warn if cloud sync is enabled but no VPS-ID is set for the ROM."""
        import threading
        def _worker():
            import time
            try:
                import win32gui
            except ImportError:
                return
            try:
                if not rom:
                    return
                if not self.cfg.CLOUD_ENABLED:
                    return
                if not self._has_any_map(rom):
                    return

                shown = getattr(self, "_mini_info_vps_shown_for_rom", None)
                if not isinstance(shown, set):
                    shown = set()
                if rom in shown:
                    return

                try:
                    from ui_vps import _load_vps_mapping
                    mapping = _load_vps_mapping(self.cfg)
                    if mapping.get(rom):
                        return
                except Exception:
                    return

                def _vpx_window_visible() -> bool:
                    found = False
                    def _cb(hwnd, _):
                        nonlocal found
                        try:
                            title = (win32gui.GetWindowText(hwnd) or "").strip().lower()
                            if "visual pinball player" in title and win32gui.IsWindowVisible(hwnd):
                                found = True
                                return False
                        except Exception:
                            pass
                        return True
                    try:
                        win32gui.EnumWindows(_cb, None)
                    except Exception:
                        return False
                    return found

                for _ in range(40):  # max 20s warten
                    if self._stop.is_set():
                        return
                    # Don't abort on game_active=False – short sessions would never see the
                    # notification because game_active can become False before the VPX window
                    # is detected by the poll.  Only _stop (watcher shutdown) should abort.
                    # Don't show while a challenge is active; the challenge start
                    # message would appear before this notification otherwise.
                    try:
                        if getattr(self, "challenge", {}).get("active", False):
                            return
                    except Exception:
                        pass
                    if _vpx_window_visible():
                        msg = f"No VPS-ID set for {rom}. Progress will NOT be uploaded to cloud.\nGo to 'Available Maps' tab to assign."
                        dur = max(5, int(seconds))
                        try:
                            self.bridge.challenge_info_show.emit(msg, dur, "#FF7F00")
                            shown.add(rom)
                            self._mini_info_vps_shown_for_rom = shown
                            log(self.cfg, f"[INFO] Mini overlay (no VPS-ID) shown for {rom}")
                        except Exception as e:
                            log(self.cfg, f"[OVERLAY] mini info vps emit failed: {e}", "WARN")
                        return
                    time.sleep(0.5)
            except Exception as e:
                log(self.cfg, f"[OVERLAY] mini info vps worker failed: {e}", "WARN")

        try:
            t = threading.Thread(target=_worker, daemon=True, name="MiniInfoMissingVpsId")
            t.start()
        except Exception:
            pass

    def _plausible_counter(self, label: str) -> bool:
        if not label:
            return False
        l = label.lower()
        keys = [
            "games", "balls", "ramp", "bumper", "spinner", "extra",
            "bonus", "hits", "made", "served", "targets", "loops",
            "lane", "kicks", "multiball", "jackpot", "mode"
        ]
        return any(k in l for k in keys)

    def _session_milestones_for_field(self, field_label: str) -> list[int]:
        f = (field_label or "").lower()
        if "extra ball" in f:
            return [3, 5]
        if "ball save" in f:
            return [3, 5, 10]
        if "jackpot" in f:
            return [1, 3, 5, 10, 15]
        if "multiball" in f:
            return [1, 3, 5]
        if "ramp" in f:
            return [5, 10, 15, 20, 25]
        if "loop" in f or "orbit" in f:
            return [3, 5, 10, 15]
        if "spinner" in f:
            return [10, 20, 30, 50]
        if "target" in f:
            return [10, 20, 30, 50]
        if "mode" in f:
            return [1, 3, 5, 10]
        return [1, 3, 5, 10, 15, 20, 25, 30]
        
    def _overall_milestones_for_field(self, field_label: str) -> list[int]:
        f = (field_label or "").lower()
        if "games started" in f:
            return [50, 100, 250, 500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 25000, 30000, 50000]
        if "balls played" in f:
            return [100, 250, 500, 1000, 2500, 5000, 10000, 15000, 25000, 50000, 75000, 100000]
        if "extra ball" in f:
            return [10, 20, 30, 50, 100, 250, 500, 1000, 2500, 5000]
        if "ball save" in f:
            return [20, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        if "jackpot" in f:
            return [25, 50, 100, 150, 300, 500, 1000, 2500, 5000, 10000]
        if "multiball" in f:
            return [10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
        if "ramp" in f:
            return [100, 200, 300, 500, 1000, 2500, 5000, 10000, 25000, 50000]
        if "loop" in f or "orbit" in f:
            return [100, 200, 500, 1000, 2500, 5000, 10000, 25000]
        if "modes completed" in f or ("mode" in f and "complete" in f):
            return [10, 25, 50, 100, 250, 500, 1000, 2500]
        if "modes started" in f or ("mode" in f and "start" in f):
            return [25, 50, 100, 250, 500, 1000, 2500, 5000]
        return [50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000]

    def bootstrap(self):
        for d in [
            self.cfg.BASE,
            p_maps(self.cfg),
            p_local_maps(self.cfg),
            p_session(self.cfg),
            p_highlights(self.cfg),
            p_achievements(self.cfg),
            p_rom_spec(self.cfg),
        ]:
            ensure_dir(d)

        _set_folder_hidden(p_session(self.cfg))
        _set_folder_hidden(p_achievements(self.cfg))

        def ensure_file(path, url):
            if os.path.exists(path):
                return
            try:
                data = _fetch_bytes_url(url, timeout=25)
                ensure_dir(os.path.dirname(path))
                with open(path, "wb") as f:
                    f.write(data)
                log(self.cfg, f"Downloaded {url} -> {path}")
            except Exception as e:
                log(self.cfg, f"Could not download {url}: {e}", "ERROR")

        ensure_file(f_index(self.cfg), INDEX_URL)
        ensure_file(f_romnames(self.cfg), ROMNAMES_URL)
        from ui_vps import VPSDB_URL as _VPSDB_URL
        ensure_file(f_vpsdb_cache(self.cfg), _VPSDB_URL)
        try:
            ensure_vpxtool(self.cfg)
        except Exception as e:
            log(self.cfg, f"[VPXTOOL] ensure failed: {e}", "WARN")

        self.INDEX = load_json(f_index(self.cfg), {}) or {}
        self.ROMNAMES = load_json(f_romnames(self.cfg), {}) or {}
            
    def _prefetch_worker(self):
        try:
            if hasattr(self, "bridge") and hasattr(self.bridge, "prefetch_started"):
                self.bridge.prefetch_started.emit()
        except Exception:
            pass

        if not self.INDEX:
            log(self.cfg, "Prefetch: INDEX empty, attempting reload...", "WARN")
            try:
                self.INDEX = load_json(f_index(self.cfg), {}) or {}
                if not self.INDEX:
                    mj = _fetch_json_url(INDEX_URL, timeout=25)
                    save_json(f_index(self.cfg), mj)
                    self.INDEX = mj or {}
            except Exception as e:
                msg = f"Prefetch aborted: cannot load INDEX: {e}"
                log(self.cfg, msg, "ERROR")
                try:
                    if hasattr(self, "bridge") and hasattr(self.bridge, "prefetch_finished"):
                        self.bridge.prefetch_finished.emit(msg)
                except Exception:
                    pass
                return
                
        unique_rels = set()
        total_roms = 0
        for rom, entry in self.INDEX.items():
            if str(rom).startswith("_"):
                continue
            total_roms += 1
            rel = entry if isinstance(entry, str) else (entry.get("path") or entry.get("file"))
            if not rel:
                continue
            if rel.startswith("maps/"):
                rel = rel[len("maps/"):]
            unique_rels.add(rel)
            
        downloaded = 0
        for rel in sorted(unique_rels):
            local = os.path.join(p_local_maps(self.cfg), rel.replace("/", os.sep))
            if os.path.exists(local):
                continue
            try:
                url = f"{GITHUB_BASE}/maps/{rel.lstrip('/')}"
                mj = _fetch_json_url(url, timeout=25)
                if save_json(local, mj):
                    downloaded += 1
                    if downloaded % PREFETCH_LOG_EVERY == 0:
                        prog_msg = f"downloaded {downloaded} unique maps..."
                        log(self.cfg, f"Prefetch progress: {prog_msg}")
                        try:
                            if hasattr(self, "bridge") and hasattr(self.bridge, "prefetch_progress"):
                                self.bridge.prefetch_progress.emit(prog_msg)
                        except Exception:
                            pass
            except Exception as e:
                log(self.cfg, f"Prefetch miss {rel}: {e}", "WARN")
                
        fin_msg = f"Prefetch finished. ROMs in index: {total_roms}, unique map files: {len(unique_rels)}, newly downloaded: {downloaded}"
        log(self.cfg, fin_msg)
        try:
            if hasattr(self, "bridge") and hasattr(self.bridge, "prefetch_finished"):
                self.bridge.prefetch_finished.emit(fin_msg)
        except Exception:
            pass

    def start_prefetch_background(self):
        if PREFETCH_MODE != "background":
            log(self.cfg, "Prefetch disabled (mode != background)")
            return
        threading.Thread(target=self._prefetch_worker, daemon=True).start()

    @staticmethod
    def _to_int(v, default=2):
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            try:
                if s.startswith("0x"):
                    return int(s, 16)
                return int(s)
            except Exception:
                return default
        return default

    def parse_map(self, mj):
        fields: List[Dict[str, Any]] = []
        if not isinstance(mj, dict):
            return fields

        if isinstance(mj.get("fields"), list):
            for f in mj["fields"]:
                if not isinstance(f, dict):
                    continue
                label = str(f.get("label") or f.get("name") or "field")
                ll = label.strip().lower()
                if ll in {"current_player", "player_count", "p2 score", "p3 score", "p4 score"}:
                    continue
                fields.append({
                    "name": f.get("name") or f.get("label") or "field",
                    "label": f.get("label") or f.get("name") or "field",
                    "offset": self._to_int(f.get("offset", f.get("start", 0)), 0),
                    "size": self._to_int(f.get("size", f.get("length", 2)), 2),
                    "encoding": f.get("encoding") or None,
                    "endian": f.get("endian") or None,
                    "scale": float(f.get("scale") or 1.0),
                    "signed": bool(f.get("signed", False)),
                    "mask": self._to_int(f.get("mask", 0), 0),
                    "value_offset": self._to_int(f.get("value_offset", f.get("offset_adjust", f.get("valueoffset", 0))), 0)
                })
            return fields

        if isinstance(mj.get("game_state"), dict):
            gs = mj["game_state"]
            scores = gs.get("scores")
            if isinstance(scores, list) and scores:
                sc = scores[0]  # nur P1
                if isinstance(sc, dict) and "start" in sc:
                    fields.append({
                        "name": "P1 Score",
                        "label": "P1 Score",
                        "offset": self._to_int(sc.get("start", 0), 0),
                        "size": self._to_int(sc.get("length", 2), 2),
                        "encoding": sc.get("encoding") or "bcd",
                        "endian": sc.get("endian") or None,
                        "scale": float(sc.get("scale") or 1.0),
                        "signed": bool(sc.get("signed", False)),
                        "mask": self._to_int(sc.get("mask", 0), 0),
                        "value_offset": self._to_int(sc.get("value_offset", sc.get("offset", 0)), 0)
                    })

            def add_gs(name_in: str, label_out: str | None = None):
                ent = gs.get(name_in)
                if not isinstance(ent, dict) or "start" not in ent:
                    return
                lab = label_out or str(ent.get("label") or name_in)
                ll = lab.strip().lower()
                if ll in {"current_player", "player_count"}:
                    return
                fields.append({
                    "name": label_out or name_in,
                    "label": lab,
                    "offset": self._to_int(ent.get("start", 0), 0),
                    "size": self._to_int(ent.get("length", ent.get("size", 1)), 1),
                    "encoding": ent.get("encoding") or None,
                    "endian": ent.get("endian") or None,
                    "scale": float(ent.get("scale") or 1.0),
                    "signed": bool(ent.get("signed", False)),
                    "mask": self._to_int(ent.get("mask", 0), 0),
                    "value_offset": self._to_int(ent.get("value_offset", ent.get("offset", 0)), 0)
                })

            add_gs("credits", "Credits")
            add_gs("current_ball", "current_ball")
            if "ball_count" in gs:
                add_gs("ball_count", "Balls Played")
            add_gs("tilted", "Tilted")
            add_gs("game_over", "Game Over")
            add_gs("extra_balls", "Extra Balls")
            add_gs("tilt_warnings", "Tilt Warnings")

        def _extract_nested(node, parent_label="", top_key=""):
            if isinstance(node, dict):
                if ("start" in node or "offset" in node):
                    label = str(node.get("label") or node.get("name") or parent_label)
                    if label and label.lower() not in {"current_player", "player_count"}:
                        if not any(f["label"] == label for f in fields):
                            fields.append({
                                "name": label,
                                "label": label,
                                "offset": self._to_int(node.get("offset", node.get("start", 0)), 0),
                                "size": self._to_int(node.get("size", node.get("length", 1)), 1),
                                "encoding": node.get("encoding") or None,
                                "endian": node.get("endian") or None,
                                "scale": float(node.get("scale") or 1.0),
                                "signed": bool(node.get("signed", False)),
                                "mask": self._to_int(node.get("mask", 0), 0),
                                "value_offset": self._to_int(node.get("value_offset", node.get("offset_adjust", 0)), 0),
                                "section": top_key
                            })
                else:
                    current_label = str(node.get("label") or node.get("name") or parent_label)
                    for k, v in node.items():
                        if isinstance(v, (dict, list)):
                            child_label = current_label
                            if current_label and k in {"score", "initials", "timestamp"}:
                                child_label = f"{current_label} {k.title()}"
                            _extract_nested(v, child_label, top_key if top_key else str(k))
            elif isinstance(node, list):
                for item in node:
                    _extract_nested(item, parent_label, top_key)

        _extract_nested(mj.get("audits", {}))
        _extract_nested(mj.get("adjustments", {}), top_key="adjustments")
        _extract_nested(mj.get("high_scores", []), top_key="high_scores")
        _extract_nested(mj.get("mode_champions", []), top_key="mode_champions")

        return fields
        
    def _try_load_map_for(self, rom: str) -> tuple[Optional[list[dict]], Optional[str]]:
        try:
            local1 = os.path.join(p_local_maps(self.cfg), rom + ".json")
            if os.path.exists(local1):
                fields = self.parse_map(load_json(local1, {}) or {})
                if fields:
                    return fields, local1

            local2 = os.path.join(p_local_maps(self.cfg), rom + ".map.json")
            if os.path.exists(local2):
                fields = self.parse_map(load_json(local2, {}) or {})
                if fields:
                    return fields, local2

            entry = (self.INDEX or {}).get(rom) or (self.INDEX or {}).get(rom.lower())
            if entry:
                rel = entry if isinstance(entry, str) else (entry.get("path") or entry.get("file"))
                if rel:
                    fields, p = self._load_map_from_local_rel(rel)
                    if fields:
                        return fields, p
        except Exception:
            pass
        return None, None

    def _resolve_map_from_index_then_family(self, rom: str) -> tuple[Optional[list[dict]], Optional[str], Optional[str]]:
        if not rom:
            return None, None, None

        fields, src = self._try_load_map_for(rom)
        if fields:
            return fields, src, rom

        for cand in self._all_rom_candidates(rom):
            if cand.lower() == rom.lower():
                continue
            try:
                f2, s2 = self._try_load_map_for(cand)
            except Exception:
                f2, s2 = None, None
            if f2:
                return f2, s2, cand

        return None, None, None

    def load_map_for_rom(self, rom: str):
        fields, src, matched = self._resolve_map_from_index_then_family(rom)

        try:
            if fields and matched and matched.lower() != (rom or "").lower():
                log(self.cfg, f"[MAP] family fallback: {rom} -> {matched}")
                no_map_set = getattr(self, "_no_map_logged_for_roms", None)
                if isinstance(no_map_set, set):
                    no_map_set.discard(str(rom).lower())
            elif not fields:
                key = str(rom or "").lower()
                no_map_set = getattr(self, "_no_map_logged_for_roms", None)
                if not isinstance(no_map_set, set):
                    no_map_set = set()
                    self._no_map_logged_for_roms = no_map_set
                if key and key not in no_map_set:
                    log(self.cfg, f"[MAP] no nvram map found for ROM '{rom}' (after family fallback)", "WARN")
                    no_map_set.add(key)
            else:
                no_map_set = getattr(self, "_no_map_logged_for_roms", None)
                if isinstance(no_map_set, set):
                    no_map_set.discard(str(rom).lower())
                logged = getattr(self, "_map_found_logged_roms", None)
                if not isinstance(logged, set):
                    logged = set()
                    self._map_found_logged_roms = logged
                if rom not in logged and self.current_rom and rom == self.current_rom:
                    log(self.cfg, f"[MAP] direct map found for ROM '{rom}' (source: {src})")
                    logged.add(rom)
        except Exception:
            pass

        return fields, src

    def _all_rom_candidates(self, rom: str) -> list[str]:
        name = (rom or "").strip()
        out: list[str] = []
        seen = set()
        def add(x: str):
            x = (x or "").strip()
            if not x:
                return
            xl = x.lower()
            if xl not in seen:
                seen.add(xl)
                out.append(x)
        add(name)
        rn = self.ROMNAMES or {}
        base_rom = rn.get(name) or rn.get(name.lower())
        if base_rom and base_rom != name:
            add(base_rom)
        for c in self._family_rom_candidates(name):
            add(c)
        return out
          
    def _load_map_from_local_rel(self, rel) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        if rel.startswith("maps/"):
            rel = rel[len("maps/"):]
        local = os.path.join(p_local_maps(self.cfg), rel.replace("/", os.sep))
        if not os.path.exists(local):
            try:
                url = f"{GITHUB_BASE}/maps/{rel.lstrip('/')}"
                mj = _fetch_json_url(url, timeout=25)
                save_json(local, mj)
            except Exception as e:
                log(self.cfg, f"Map fetch failed {rel}: {e}", "WARN")
                return None, None
        mj = load_json(local, {}) or {}
        return self.parse_map(mj), local

    def _family_rom_candidates(self, rom: str) -> list[str]:
        name = (rom or "").strip()
        nlow = name.lower()
        out: list[str] = []
        def add(x: str):
            x = (x or "").strip()
            if x and x.lower() != nlow and x not in out:
                out.append(x)
        m = re.match(r"^([a-z0-9]+?)[a-z]+$", nlow)
        if m:
            add(m.group(1))
        pre_us = nlow.split("_")[0]
        if pre_us and pre_us != nlow:
            add(pre_us)
        m2 = re.match(r"^([a-z]+[0-9]+)", nlow)
        if m2:
            add(m2.group(1))
        if pre_us and pre_us != nlow:
            m3 = re.match(r"^([a-z]+)_([0-9]+)", nlow)
            if m3:
                add(m3.group(1) + m3.group(2))
        family_prefixes = []
        if m2:
            family_prefixes.append(m2.group(1))  # afm113
        if pre_us:
            family_prefixes.append(pre_us)       # afm
        seen_fp = set()
        family_prefixes = [fp for fp in family_prefixes if not (fp in seen_fp or seen_fp.add(fp))]
        for fp in family_prefixes:
            for key in sorted(self.INDEX.keys()):
                kl = key.lower()
                if kl.startswith(fp) and kl != nlow:
                    add(key)
        return out

    @staticmethod
    def decode_bcd(raw: bytes) -> Optional[int]:
        digits = []
        for b in raw:
            hi, lo = (b >> 4) & 0xF, b & 0xF
            if hi > 9 or lo > 9:
                return None
            digits.append(str(hi))
            digits.append(str(lo))
        s = "".join(digits).lstrip("0")
        return int(s) if s else 0

    @staticmethod
    def decode_uint(raw: bytes, endian: Optional[str], signed: bool) -> int:
        e = "big" if (endian or "be") in ("be", "big") else "little"
        return int.from_bytes(raw, e, signed=bool(signed))

    @staticmethod
    def _plausibility_score(label, value):
        if value is None:
            return 1e12
        if value < 0:
            return 1e9
        caps = {"bumper": 200000, "spinner": 500000, "ramp": 200000, "ball": 100000, "extra": 10000}
        v = str(label).lower()
        cap = 500000
        for k, c in caps.items():
            if k in v:
                cap = c
                break
        penalty = (value - cap) * 10 if value > cap else 0
        return value + penalty

    def _decode_field_value(self, raw: bytes, fld: dict):
        offset = int(fld["offset"])
        size = int(fld["size"])
        enc = (fld.get("encoding") or "").lower() or None
        endian = fld.get("endian") or "be"
        signed = bool(fld.get("signed", False))
        scale = float(fld.get("scale", 1.0))
        if offset < 0 or offset + size > len(raw):
            return None
        window = raw[offset: offset + size]
        
        if enc in ("ch", "ascii", "string"):
            return "".join(chr(b) for b in window if 32 <= b <= 126).strip()

        if enc == "bcd":
            val = self.decode_bcd(window)
        elif enc in ("int", "uint", "sint"):
            val = self.decode_uint(window, endian, signed)
        elif enc == "bool":
            val = self.decode_uint(window, endian, False)
            val = 1 if int(val or 0) != 0 else 0
        else:
            val = self.decode_uint(window, endian, signed)
            
        if val is None:
            return None
        try:
            mask = int(fld.get("mask", 0) or 0)
            if mask:
                val = int(val) & mask
        except Exception:
            pass
        if scale != 1.0:
            try:
                val = int(int(val) * scale)
            except Exception:
                val = int(val)
        try:
            vo = int(fld.get("value_offset", 0) or 0)
            if vo:
                val = int(val) + vo
        except Exception:
            pass
        return int(val)

    def auto_fix_field(self, raw: bytes, base_enc, base_end, base_size, signed, label):
        sizes = sorted({int(base_size or 2), int(base_size or 2) + 1, int(base_size or 2) + 2})
        candidates = []
        for sz in sizes:
            if sz > len(raw):
                continue
            chunk = raw[:sz]
            encs = [base_enc] if base_enc else [None, "bcd"]
            if "bcd" not in encs:
                encs.append("bcd")
            for enc in encs:
                if enc == "bcd":
                    val = self.decode_bcd(chunk)
                    if val is not None:
                        candidates.append((val, {"encoding": "bcd", "endian": None, "size": sz}))
                else:
                    for e in ("be", "le"):
                        val = self.decode_uint(chunk, e, signed)
                        candidates.append((val, {"encoding": None, "endian": e, "size": sz}))
        best, cfg, best_score = None, None, 1e18
        for val, c in candidates:
            sc = self._plausibility_score(label, int(val))
            if sc < best_score:
                best, cfg, best_score = int(val), c, sc
        return best, cfg

    def _load_cached_layout(self, rom: str):
        return self._field_layout_cache.get(rom)

    def _store_cached_layout(self, rom: str, layout_fields: List[dict]):
        self._field_layout_cache[rom] = {
            "fields": layout_fields,
            "cache_time": time.time()
        }

    def read_nvram_audits_with_autofix(self, rom: str) -> Tuple[Dict[str, Any], List[str], bool]:
        if not rom:
            return {}, [], False
        # mtime-based NVRAM read cache – skip re-read if file unchanged
        nv_path = os.path.join(self.cfg.NVRAM_DIR, rom + ".nv")
        try:
            mt = os.path.getmtime(nv_path)
            if rom == self._nvram_cache_rom and mt == self._nvram_cache_mtime:
                return self._nvram_cache_result
        except Exception:
            pass
        if not os.path.exists(nv_path):
            return {}, [], False
        try:
            with open(nv_path, "rb") as f:
                raw = f.read()
        except Exception:
            return {}, [], False

        cached = self._load_cached_layout(rom)
        if cached:
            audits = {}
            notes: List[str] = []
            for fld in cached["fields"]:
                try:
                    label = fld["label"]
                    val = self._decode_field_value(raw, fld)
                    if val is None:
                        continue
                    audits[label] = val
                except Exception:
                    continue
            try:
                self._ensure_rom_specific(rom, audits)
            except Exception as e:
                log(self.cfg, f"[ROM_SPEC] ensure failed (cached path): {e}", "WARN")
            self._nvram_cache_rom = rom
            try:
                self._nvram_cache_mtime = os.path.getmtime(nv_path)
            except Exception:
                self._nvram_cache_mtime = 0.0
            self._nvram_cache_result = (audits, notes, False)
            return audits, notes, False

        fields, _ = self.load_map_for_rom(rom)
        if not fields:
            return {}, [], False

        audits, notes, fixed_fields = {}, [], []
        for fld in fields:
            try:
                label = (fld.get("label") or fld.get("name") or "field")
                offset = int(fld.get("offset", 0))
                size = int(fld.get("size", 2))
                enc = (fld.get("encoding") or "").lower() or None
                endian = (fld.get("endian") or "").lower() or None
                scale = float(fld.get("scale") or 1.0)
                signed = bool(fld.get("signed", False))
                if offset < 0 or offset + size > len(raw):
                    continue

                if enc in ("ch", "ascii", "string", "wpc_rtc"):
                    val = self._decode_field_value(raw, fld)
                    if val is not None:
                        audits[label] = val
                    fixed_fields.append(fld)
                    continue

                win_len = max(4, min(6, size + 2))
                window = raw[offset: min(len(raw), offset + win_len)]
                best, cfg = self.auto_fix_field(window, enc, endian, size, signed, label)
                val = int(best or 0)
                if scale != 1.0:
                    val = int(val * scale)
                audits[label] = val

                enc_new = (cfg or {}).get("encoding")
                end_new = (cfg or {}).get("endian")
                size_new = int((cfg or {}).get("size") or size)
                spec = {
                    "name": fld.get("name") or label,
                    "label": label,
                    "offset": offset,
                    "size": size_new,
                    "encoding": enc_new,
                    "endian": end_new,
                    "scale": scale,
                    "signed": signed,
                    "mask": self._to_int(fld.get("mask", 0), 0),
                    "value_offset": self._to_int(fld.get("value_offset", 0), 0),
                    "section": fld.get("section", ""),
                }
                fixed_fields.append(spec)

                if (enc_new or None) != (enc or None) or (end_new or None) != (endian or None) or size_new != size:
                    notes.append(f"[AUTO-FIX] {label}: enc {enc}->{enc_new}, endian {endian}->{end_new}, size {size}->{size_new}")
            except Exception as e:
                notes.append(f"[READ-WARN] {fld} -> {e}")

        self._store_cached_layout(rom, fixed_fields)
        try:
            self._ensure_rom_specific(rom, audits)
        except Exception as e:
            log(self.cfg, f"[ROM_SPEC] ensure failed: {e}", "WARN")

        self._nvram_cache_rom = rom
        try:
            self._nvram_cache_mtime = os.path.getmtime(nv_path)
        except Exception:
            self._nvram_cache_mtime = 0.0
        self._nvram_cache_result = (audits, notes, False)
        return audits, notes, False

    HIGHLIGHT_RULES = {
        "multiball": {"cat": "Power", "emoji": "💥", "label": "Multiball Frenzy", "type": "count"},
        "jackpot": {"cat": "Power", "emoji": "🎯", "label": "Jackpot Hunter", "type": "count"},
        "super_jackpot": {"cat": "Power", "emoji": "💎", "label": "Super Jackpot", "type": "count"},
        "triple_jackpot": {"cat": "Power", "emoji": "👑", "label": "Triple Jackpot", "type": "count"},
        "ball_save": {"cat": "Power", "emoji": "🛡️", "label": "Ball Saves", "type": "count"},
        "extra_ball": {"cat": "Power", "emoji": "➕", "label": "Extra Balls", "type": "count"},
        "special_award": {"cat": "Power", "emoji": "🎁", "label": "Special Awards", "type": "count"},
        "mode_completed": {"cat": "Power", "emoji": "🏆", "label": "Modes Completed", "type": "count"},
        "best_ball": {"cat": "Power", "emoji": "🔥", "label": "Best Ball", "type": "always"},
        "wizard_mode": {"cat": "Power", "emoji": "🧙", "label": "Wizard Mode", "type": "flag"},
        "loops": {"cat": "Precision", "emoji": "🔁", "label": "Loop Machine", "type": "count"},
        "spinner": {"cat": "Precision", "emoji": "🌀", "label": "Spinner Madness", "type": "count"},
        "combo": {"cat": "Precision", "emoji": "🎯", "label": "Combo King", "type": "count"},
        "drop_targets": {"cat": "Precision", "emoji": "🎯", "label": "Target Slayer", "type": "count"},
        "ramps": {"cat": "Precision", "emoji": "🏹", "label": "Rampage", "type": "count"},
        "orbit": {"cat": "Precision", "emoji": "🌌", "label": "Orbit Runner", "type": "count"},
        "skillshot": {"cat": "Precision", "emoji": "🎯", "label": "Skill Shot", "type": "count"},
        "super_skillshot": {"cat": "Precision", "emoji": "💥", "label": "Super Skill Shot", "type": "count"},
        "mode_starts": {"cat": "Precision", "emoji": "🎬", "label": "Modes Started", "type": "count"},
        "tilt_warnings": {"cat": "Fun", "emoji": "🛡️", "label": "Tilt Warnings", "type": "count"},
        "tilt": {"cat": "Fun", "emoji": "💀", "label": "Tilted", "type": "count"},
        "devils_number": {"cat": "Fun", "emoji": "👹", "label": "Devil’s Number", "type": "flag"},
        "match": {"cat": "Fun", "emoji": "🎲", "label": "Match Lucky", "type": "count"},
    }
    EVENT_KEYWORDS = {
        "super_jackpot": ["super jackpot", "super-jackpot", "super jp", "super jp."],
        "triple_jackpot": ["triple jackpot", "triple-jackpot", "triple jp", "triple jp."],
        "jackpot": ["jackpot", " jp", " jp.", "jackpots"],
        "multiball": ["multiball", "multi-ball", "multi ball", "multiballs", "m.b.", "mb start"],
        "ball_save": ["ball save", "ball saves"],
        "extra_ball": ["extra ball", "extra balls", "e.b.", "ex. ball"],
        "special_award": ["special"],
        "loops": ["loop", "loops"],
        "spinner": ["spinner"],
        "combo": ["combo", "combos"],
        "drop_targets": ["drop target", "targets"],
        "ramps": ["ramp", "ramps"],
        "orbit": ["orbit", "orbits"],
        "super_skillshot": ["super skill", "super skillshot"],
        "skillshot": ["skill shot", "skillshot"],
        "mode_completed": ["mode complete", "modes completed", "wave compl", "mission compl"],
        "mode_starts": ["mode start", "modes started", "wave start", "mission start", "atk. start"],
        "tilt_warnings": ["tilt warn", "tilt warning", "tilt warnings"],
        "tilt": [" tilt ", "tilted"],
        "match": ["match awards", "match lucky"],
        "wizard_mode": ["wizard mode", "wizard", "universe start", "universe won", "ruler of the universe"],
    }
    NOISE_REGEX = re.compile(r"(minutes on|play time|recent|total .*slot|paid cred|serv|factory|reset|cleared|burn|clock|coins|h\.s\.t\.d)", re.I)
    KEYWORD_FALLBACK = [
        "jackpot", "multiball", "skill", "mode", "lock", "locks", "extra", "ball save", "save", "wave",
        "combo", "martian", "video", "hurry", "random", "tilt", "wizard",
        "games started", "balls locked", "locks lit", "extra balls", "ball saves", "bonus", "mode start",
        "mode compl", "annihil", "martn.", "strobe"
    ]

    def _find_vpx_pid(self) -> Optional[int]:
        if not win32gui:
            return None
        hwnd = {"h": None}
        def _cb(h, _):
            if win32gui.IsWindowVisible(h):
                title = win32gui.GetWindowText(h)
                if title.startswith("Visual Pinball - ["):
                    hwnd["h"] = h
                    return False
            return True
        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            return None
        if not hwnd["h"]:
            return None
        pid = wintypes.DWORD(0)
        try:
            ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd["h"]), ctypes.byref(pid))
            return int(pid.value or 0) or None
        except Exception:
            return None

    def _vp_player_visible(self) -> bool:
        if not win32gui:
            return False
        now = time.time()
        cache = getattr(self, "_vp_visible_cache", None)
        if cache and (now - cache[0]) < 0.3:
            return cache[1]
        visible = {"flag": False}
        def _cb(hwnd, _):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    title = (win32gui.GetWindowText(hwnd) or "").strip()
                    if title.startswith("Visual Pinball Player"):
                        visible["flag"] = True
                        return False
            except Exception:
                pass
            return True
        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            return False
        result = bool(visible["flag"])
        self._vp_visible_cache = (now, result)
        return result

    def _get_vp_player_rect(self) -> tuple[int, int, int, int] | None:
        if not win32gui:
            return None
        rect = {"ok": False, "x": 0, "y": 0, "w": 0, "h": 0}
        def _cb(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                title = (win32gui.GetWindowText(hwnd) or "").strip()
                if title.startswith("Visual Pinball Player"):
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    rect["ok"] = True
                    rect["x"], rect["y"] = int(left), int(top)
                    rect["w"], rect["h"] = int(right - left), int(bottom - top)
                    return False
            except Exception:
                pass
            return True
        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            return None
        if rect["ok"] and rect["w"] > 0 and rect["h"] > 0:
            return rect["x"], rect["y"], rect["w"], rect["h"]
        return None

    def _graceful_close_visual_pinball_player(self, wait_ms: int = 2500) -> bool:   
        try:
            import ctypes
            from ctypes import wintypes
            WM_CLOSE = 0x0010
            try:
                import win32gui
            except Exception:
                win32gui = None

            if not win32gui:
                return False
            pids = set()

            def _cb(hwnd, _):
                try:
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    title = win32gui.GetWindowText(hwnd) or ""
                    if title.startswith("Visual Pinball Player"):
                        try:
                            ctypes.windll.user32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0)
                        except Exception:
                            pass
                        pid = wintypes.DWORD(0)
                        ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
                        if pid.value:
                            pids.add(int(pid.value))
                except Exception:
                    pass
                return True
            win32gui.EnumWindows(_cb, None)
            if not pids:
                return True 
            k32 = ctypes.windll.kernel32
            SYNCHRONIZE = 0x00100000
            handles = []
            for pid in pids:
                try:
                    h = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
                    if h:
                        handles.append(h)
                except Exception:
                    pass
            if not handles:
                import time as _time
                _time.sleep(min(1.0, wait_ms / 1000.0))
            else:
                arr_type = wintypes.HANDLE * len(handles)
                arr = arr_type(*handles)
                k32.WaitForMultipleObjects(len(handles), arr, True, int(wait_ms))
                for h in handles:
                    try:
                        k32.CloseHandle(h)
                    except Exception:
                        pass
            try:
                still = []
                out = subprocess.check_output(
                    ["tasklist"], creationflags=0x08000000
                ).decode(errors="ignore").lower()
                for pid in pids:
                    if str(pid) in out:
                        still.append(pid)
                return len(still) == 0
            except Exception:
                return False
        except Exception:
            return False
            
    def _kill_vpx_process(self):
        try:
            import ctypes, subprocess, time
            from ctypes import wintypes
            try:
                self._alt_f4_visual_pinball_player(wait_ms=800)
            except Exception as e:
                log(self.cfg, f"[CHALLENGE] Alt+F4 path failed: {e}", "WARN")

            try:
                import win32gui, win32con
                def _cb(hwnd, _):
                    try:
                        if not win32gui.IsWindowVisible(hwnd):
                            return True
                        title = (win32gui.GetWindowText(hwnd) or "").strip()
                        if title.startswith("Visual Pinball Player") or title.startswith("Visual Pinball - ["):
                            try:
                                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    return True
                win32gui.EnumWindows(_cb, None)
            except Exception:
                pass

            try:
                deadline = time.time() + 1.8
                while time.time() < deadline:
                    out = subprocess.check_output(["tasklist"], creationflags=0x08000000).decode(errors="ignore").lower()
                    if "vpinball" not in out:
                        log(self.cfg, "[CHALLENGE] VPX closed via Alt+F4 + WM_CLOSE")
                        return
                    time.sleep(0.15)
            except Exception:
                pass

            try:
                for img in ("VPinballX64.exe", "VPinballX.exe", "VPinballX_GL.exe", "VPinball.exe"):
                    try:
                        subprocess.run(
                            ["taskkill", "/IM", img, "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x08000000
                        )
                    except Exception:
                        continue
            except Exception:
                pass
            log(self.cfg, "[CHALLENGE] WARNING: fallback hard kill executed", "WARN")
        except Exception as e:
            log(self.cfg, f"[CHALLENGE] _kill_vpx_process failed: {e}", "WARN")


    def start_timed_challenge(self, total_seconds: int = 190):
        try:
            if not self.game_active or not self.current_rom:
                log(self.cfg, "[CHALLENGE] timed: ignored (no active game)", "WARN")
                return
            ch = getattr(self, "challenge", {}) or {}
            if ch.get("active") and ch.get("kind") == "timed":
                log(self.cfg, "[CHALLENGE] timed already active – ignored duplicate")
                return
            warmup = 10
            total = max(1, int(total_seconds))
            countdown = max(1, total - warmup)
            ch.clear()
            ch.update({
                "active": True,
                "kind": "timed",
                "rom": self.current_rom,
                "table": self.current_table,
                "started_at": time.time(),
                "end_at": time.time() + total,
                "pending_kill_at": None,
                "suppress_big_overlay_once": True,
            })
            self.challenge = ch
            try:
                self.bridge.challenge_warmup_show.emit(warmup, "Timed challenge – warm-up")
                self.bridge.challenge_timer_start.emit(total)
            except Exception:
                pass
            log(self.cfg, f"[CHALLENGE] timed armed – warmup={warmup}s, countdown={countdown}s (total={total}s)")
        except Exception as e:
            log(self.cfg, f"[CHALLENGE] timed start failed: {e}", "WARN")

    def stop_timed_challenge(self):      
        ch = getattr(self, "challenge", {})
        if ch.get("kind") == "timed":
            ch["active"] = False
            self.challenge = ch
            try:
                self.bridge.challenge_timer_stop.emit()
            except Exception:
                pass
            log(self.cfg, "[CHALLENGE] timed stopped")

    def _flip_start_inputs(self):
        ini = get_vpx_ini_path_for_current_user()
        binds = parse_vpx_flipper_bindings(ini or "")
        self._flip["vk_left"] = int(binds.get("vk_left", 0) or 0)
        self._flip["vk_right"] = int(binds.get("vk_right", 0) or 0)
        self._flip["joy_left"] = int(binds.get("joy_left", 0) or 0)
        self._flip["joy_right"] = int(binds.get("joy_right", 0) or 0)
        try:
            kbs = []
            if self._flip["vk_left"]:
                kbs.append({"get_vk": lambda: self._flip["vk_left"], "on_press": lambda: self._flip_on_kbd_press("L")})
            if self._flip["vk_right"]:
                kbs.append({"get_vk": lambda: self._flip["vk_right"], "on_press": lambda: self._flip_on_kbd_press("R")})
            if kbs:
                self._flip_inputs["kbd"] = GlobalKeyHook(kbs)
                self._flip_inputs["kbd"].install()
                log(self.cfg, "[FLIP] Keyboard hook installed for flipper keys")
        except Exception as e:
            log(self.cfg, f"[FLIP] Keyboard hook failed: {e}", "WARN")
        try:
            self._flip_inputs["joy_running"] = True
            t = threading.Thread(target=self._flip_joy_poll_loop, daemon=True, name="FlipJoyPoll")
            self._flip_inputs["joy_thread"] = t
            t.start()
            log(self.cfg, "[FLIP] Joystick polling started for flipper buttons")
        except Exception as e:
            log(self.cfg, f"[FLIP] Joystick thread start failed: {e}", "WARN")

    def _flip_stop_inputs(self):
        try:
            self._flip_inputs["joy_running"] = False
        except Exception:
            pass
        try:
            if self._flip_inputs.get("kbd"):
                self._flip_inputs["kbd"].uninstall()
        except Exception:
            pass
        self._flip_inputs["kbd"] = None
        self._flip_inputs["joy_thread"] = None
        self._flip_inputs["joy_prev_masks"] = {}

    def _flip_on_kbd_press(self, side: str):
        try:
            self._flip_inc(side)
        except Exception:
            pass

    def _flip_joy_poll_loop(self):
        want_left = int(self._flip.get("joy_left", 0) or 0)
        want_right = int(self._flip.get("joy_right", 0) or 0)

        def bit_for(btn: int) -> int:
            return (1 << (int(btn) - 1)) if int(btn) > 0 else 0

        bit_left = bit_for(want_left)
        bit_right = bit_for(want_right)
        jix = JOYINFOEX()
        jix.dwSize = ctypes.sizeof(JOYINFOEX)
        jix.dwFlags = JOY_RETURNALL
        prev = self._flip_inputs.get("joy_prev_masks", {}) or {}
        while bool(self._flip_inputs.get("joy_running", False)):
            mask_all = 0
            for jid in range(16):
                try:
                    if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                        cur = int(jix.dwButtons)
                        old = int(prev.get(jid, 0))
                        newly = cur & ~old
                        prev[jid] = cur
                        if newly:
                            if bit_left and (newly & bit_left):
                                self._flip_inc("L")
                            if bit_right and (newly & bit_right):
                                self._flip_inc("R")
                except Exception:
                    continue
            self._flip_inputs["joy_prev_masks"] = prev
            time.sleep(0.04)
            
    def _flip_inc(self, side: str):
        if not self._flip.get("active"):
            return

        if side == "L":
            self._flip["left"] = int(self._flip.get("left", 0)) + 1
        elif side == "R":
            self._flip["right"] = int(self._flip.get("right", 0)) + 1
        left = int(self._flip.get("left", 0))
        right = int(self._flip.get("right", 0))
        total = left + right
        goal_total = int(self._flip.get("threshold", (self.cfg.OVERLAY or {}).get("flip_counter_goal_total", 400)))
        remaining = max(0, int(goal_total) - int(total))
        try:
            self.bridge.flip_counter_total_update.emit(int(total), int(remaining), int(goal_total))
        except Exception:
            try:
                self.bridge.flip_counter_update.emit(int(left), int(right), int(goal_total), 0)
            except Exception:
                pass
        if total >= int(goal_total):
            self._flip_check()

    def _flip_check(self):
        if not self._flip.get("active"):
            return
        try:
            audits_now = None
            try:
                audits_now, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
            except Exception:
                audits_now = None
            if audits_now:
                try:
                    self._last_audits_global = dict(audits_now)
                except Exception:
                    pass
                try:
                    duration_now = int(time.time() - (self.start_time or time.time()))
                    self.export_overlay_snapshot(audits_now, duration_now, on_demand=True)
                except Exception:
                    pass
                ch = getattr(self, "challenge", {}) or {}
                ch["prekill_end"] = dict(audits_now)
                self.challenge = ch
            try:
                self._kill_vpx_process()
            except Exception:
                pass

            ch = getattr(self, "challenge", {}) or {}
            ch["active"] = False
            ch["pending_kill_at"] = None
            ch["completed"] = True 
            self.challenge = ch
            log(self.cfg, "[CHALLENGE] flip finished – Alt+F4 + WM_CLOSE executed")
        except Exception as e:
            log(self.cfg, f"[FLIP] finalize failed: {e}", "WARN")
        finally:
            try:
                self.bridge.flip_counter_total_hide.emit()
            except Exception:
                try:
                    self.bridge.flip_counter_hide.emit()
                except Exception:
                    pass
            self._flip_stop_inputs()

    def start_flip_challenge(self, threshold: int = 500):
        try:
            if not self.game_active or not self.current_rom:
                log(self.cfg, "[CHALLENGE] flip: ignored (no active game)", "WARN")
                return

            ch = getattr(self, "challenge", {}) or {}
            if ch.get("active"):
                log(self.cfg, "[CHALLENGE] flip: another challenge already active – ignored", "WARN")
                return

            goal_total = int(threshold or (self.cfg.OVERLAY or {}).get("flip_counter_goal_total", 400))
            self._flip["active"] = True
            self._flip["threshold"] = max(1, int(goal_total))
            self._flip["left"] = 0
            self._flip["right"] = 0
            self._flip["started_at"] = time.time()

            # Single-player enforced
            try:
                if self.snapshot_mode:
                    self.snap_players_in_game = 1
                    self.snap_players_locked = True
                    self.current_player = 1
                    self._cp_rotate_lock_until = time.time() + 36000.0
            except Exception:
                pass

            ch.clear()
            ch.update({
                "active": True,
                "kind": "flip",
                "rom": self.current_rom,
                "table": self.current_table,
                "started_at": time.time(),
                "end_at": None,
                "pending_kill_at": None,
                "suppress_big_overlay_once": True,
                "threshold": int(goal_total), 
            })
            self.challenge = ch

            try:
                self.bridge.challenge_info_show.emit(
                    f"Flip Challenge – Total Goal: {int(goal_total)}", 4, "#FFFFFF"
                )
                self.bridge.challenge_speak.emit("Flip challenge armed")
            except Exception:
                pass

            try:
                self.bridge.flip_counter_total_show.emit(0, int(goal_total), int(goal_total))
            except Exception:
                try:
                    self.bridge.flip_counter_show.emit(0, 0, int(goal_total), 0)
                except Exception:
                    pass

            self._flip_start_inputs()
            log(self.cfg, f"[CHALLENGE] flip armed – total goal={int(goal_total)} (single-player enforced)")
        except Exception as e:
            log(self.cfg, f"[CHALLENGE] flip start failed: {e}", "WARN")

    def stop_flip_challenge(self):
        try:
            self._flip_stop_inputs()
        except Exception:
            pass
        try:
            self._flip["active"] = False
        except Exception:
            pass
        try:
            self.bridge.flip_counter_total_hide.emit()
        except Exception:
            try:
                self.bridge.flip_counter_hide.emit()
            except Exception:
                pass

        ch = getattr(self, "challenge", {}) or {}
        if ch.get("kind") == "flip":
            ch["active"] = False
            ch["pending_kill_at"] = None
            self.challenge = ch
            log(self.cfg, "[CHALLENGE] flip stopped")

    def start_heat_challenge(self):
        try:
            if not self.game_active or not self.current_rom:
                log(self.cfg, "[CHALLENGE] heat: ignored (no active game)", "WARN")
                return

            ch = getattr(self, "challenge", {}) or {}
            if ch.get("active"):
                log(self.cfg, "[CHALLENGE] heat: another challenge already active – ignored", "WARN")
                return

            # Single-player enforced
            try:
                if self.snapshot_mode:
                    self.snap_players_in_game = 1
                    self.snap_players_locked = True
                    self.current_player = 1
                    self._cp_rotate_lock_until = time.time() + 36000.0
            except Exception:
                pass

            ini = get_vpx_ini_path_for_current_user()
            binds = parse_vpx_flipper_bindings(ini or "")
            vk_left = int(binds.get("vk_left", 0) or 0) or VK_LSHIFT
            vk_right = int(binds.get("vk_right", 0) or 0) or VK_RSHIFT
            joy_left = int(binds.get("joy_left", 0) or 0)
            joy_right = int(binds.get("joy_right", 0) or 0)

            ch.clear()
            ch.update({
                "active": True,
                "kind": "heat",
                "rom": self.current_rom,
                "table": self.current_table,
                "started_at": time.time(),
                "end_at": None,
                "pending_kill_at": None,
                "suppress_big_overlay_once": True,
                "heat": 0.0,
                "heat_last_time": time.time(),
                "heat_prev_pressed": False,
                "vk_left": vk_left,
                "vk_right": vk_right,
                "joy_left": joy_left,
                "joy_right": joy_right,
                "joy_pressed": False,
            })
            self.challenge = ch

            try:
                self._heat_inputs["joy_running"] = True
                t = threading.Thread(target=self._heat_joy_poll_loop, daemon=True, name="HeatJoyPoll")
                self._heat_inputs["joy_thread"] = t
                t.start()
                log(self.cfg, "[HEAT] Joystick polling started for flipper held-state")
            except Exception as e:
                log(self.cfg, f"[HEAT] Joystick thread start failed: {e}", "WARN")

            try:
                self.bridge.challenge_info_show.emit("Heat Challenge – Don't overheat!", 4, "#FF7F00")
                self.bridge.challenge_speak.emit("Heat challenge armed")
            except Exception:
                pass

            try:
                self.bridge.heat_bar_show.emit()
            except Exception:
                pass

            log(self.cfg, "[CHALLENGE] heat armed – keep flippers cool!")
        except Exception as e:
            log(self.cfg, f"[CHALLENGE] heat start failed: {e}", "WARN")

    def stop_heat_challenge(self):
        try:
            self._heat_inputs["joy_running"] = False
        except Exception:
            pass
        try:
            t = self._heat_inputs.get("joy_thread")
            if t and t.is_alive():
                t.join(timeout=0.5)
        except Exception:
            pass
        self._heat_inputs["joy_thread"] = None
        ch = getattr(self, "challenge", {})
        if ch.get("kind") == "heat":
            ch["active"] = False
            self.challenge = ch
            try:
                self.bridge.heat_bar_hide.emit()
            except Exception:
                pass
            log(self.cfg, "[CHALLENGE] heat stopped")

    def _heat_joy_poll_loop(self):
        """Background thread: poll joystick held-state for the Heat Challenge."""
        try:
            ch = getattr(self, "challenge", {}) or {}
            want_left = int(ch.get("joy_left", 0) or 0)
            want_right = int(ch.get("joy_right", 0) or 0)

            def bit_for(btn: int) -> int:
                return (1 << (int(btn) - 1)) if int(btn) > 0 else 0

            bit_left = bit_for(want_left)
            bit_right = bit_for(want_right)

            if not bit_left and not bit_right:
                return  # no joystick bindings – nothing to poll

            jix = JOYINFOEX()
            jix.dwSize = ctypes.sizeof(JOYINFOEX)
            jix.dwFlags = JOY_RETURNALL

            while bool(self._heat_inputs.get("joy_running", False)):
                held = False
                for jid in range(16):
                    try:
                        if _joyGetPosEx(jid, ctypes.byref(jix)) == JOYERR_NOERROR:
                            cur = int(jix.dwButtons)
                            if (bit_left and (cur & bit_left)) or (bit_right and (cur & bit_right)):
                                held = True
                                break
                    except Exception:
                        continue
                ch = getattr(self, "challenge", {}) or {}
                if ch.get("kind") == "heat" and ch.get("active"):
                    ch["joy_pressed"] = held
                    self.challenge = ch
                else:
                    break
                time.sleep(0.1)
        except Exception as e:
            log(self.cfg, f"[HEAT] joy poll loop failed: {e}", "WARN")

    def _clear_challenge_state(self):
        try:
            self.bridge.flip_counter_total_hide.emit()
        except Exception:
            pass
        try:
            self.bridge.challenge_timer_stop.emit()
        except Exception:
            pass
        try:
            self.bridge.heat_bar_hide.emit()
        except Exception:
            pass
        try:
            self._flip_stop_inputs()
        except Exception:
            pass
        try:
            self._heat_inputs["joy_running"] = False
        except Exception:
            pass
            
        try:
            ch = getattr(self, "challenge", {})
            if isinstance(ch, dict):
                ch["active"] = False
                ch["pending_kill_at"] = None
        except Exception:
            pass
        try:
            self.challenge = {}
        except Exception:
            pass

    def _challenge_tick(self, audits: dict):
        try:
            ch = getattr(self, "challenge", {}) or {}
            if not ch or not ch.get("active"):
                return
            now = time.time()

            if not self._vp_player_visible():
                # Grace Period: erst nach 3s Unsichtbarkeit abbrechen
                grace_start = float(ch.get("_vpx_gone_since", 0.0))
                if grace_start == 0.0:
                    ch["_vpx_gone_since"] = now
                    self.challenge = ch
                    return  # noch NICHT abbrechen
                elif (now - grace_start) < 3.0:
                    return  # noch innerhalb Grace Period
                # Ab hier: VPX war > 3s nicht sichtbar → jetzt abbrechen
                log(self.cfg, "[CHALLENGE] VPX Player window gone for >3s. Aborting challenge.")
                kind = str(ch.get("kind", "")).lower()
                
                if kind == "timed":
                    self.stop_timed_challenge()
                elif kind == "flip":
                    self.stop_flip_challenge()
                elif kind == "heat":
                    self.stop_heat_challenge()
                else:
                    try:
                        self.bridge.challenge_timer_stop.emit()
                        self.bridge.flip_counter_total_hide.emit()
                    except Exception:
                        pass
                    
                ch["active"] = False
                ch["pending_kill_at"] = None
                ch.pop("_vpx_gone_since", None)
                self.challenge = ch
                return
            else:
                # VPX ist sichtbar → Grace-Timer zurücksetzen
                if ch.get("_vpx_gone_since"):
                    ch.pop("_vpx_gone_since", None)
                    self.challenge = ch

            if ch.get("kind") == "timed":
                end_at = float(ch.get("end_at", 0.0) or 0.0)
                if now >= end_at:
                    try:
                        time.sleep(0.15)
                    except Exception:
                        pass
                    audits_now = audits
                    try:
                        audits_now2, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                        if audits_now2:
                            audits_now = audits_now2
                    except Exception:
                        pass
                    if audits_now:
                        try:
                            self._last_audits_global = dict(audits_now)
                        except Exception:
                            pass
                        try:
                            duration_now = int(now - (self.start_time or now))
                            self.export_overlay_snapshot(audits_now, duration_now, on_demand=True)
                        except Exception:
                            pass
                        ch["prekill_end"] = dict(audits_now)
                        self.challenge = ch

                    # 3) VPX schließen
                    try:
                        self._kill_vpx_process()
                    except Exception:
                        pass

                    ch["active"] = False
                    ch["pending_kill_at"] = None
                    ch["completed"] = True 
                    self.challenge = ch
                    log(self.cfg, "[CHALLENGE] timed finished – Alt+F4 + WM_CLOSE executed")
                    return

            if ch.get("kind") == "heat":
                try:
                    now_t = time.time()
                    last_t = float(ch.get("heat_last_time", now_t) or now_t)
                    delta = min(now_t - last_t, 1.5)
                    ch["heat_last_time"] = now_t

                    vk_l = int(ch.get("vk_left", 0) or 0) or VK_LSHIFT
                    vk_r = int(ch.get("vk_right", 0) or 0) or VK_RSHIFT
                    try:
                        import ctypes as _ctypes
                        lshift = bool(_ctypes.windll.user32.GetAsyncKeyState(vk_l) & 0x8000)
                        rshift = bool(_ctypes.windll.user32.GetAsyncKeyState(vk_r) & 0x8000)
                    except Exception:
                        lshift = False
                        rshift = False

                    joy_held = bool(ch.get("joy_pressed", False))
                    pressed = lshift or rshift or joy_held
                    prev_pressed = bool(ch.get("heat_prev_pressed", False))
                    heat = float(ch.get("heat", 0.0) or 0.0)

                    if pressed:
                        heat += HEAT_HOLD_RATE * delta
                        if pressed and not prev_pressed:
                            heat += HEAT_PRESS_BURST
                    else:
                        heat -= HEAT_COOLDOWN_RATE * delta

                    heat = max(0.0, min(100.0, heat))
                    ch["heat"] = heat
                    ch["heat_prev_pressed"] = pressed
                    self.challenge = ch

                    try:
                        self.bridge.heat_bar_update.emit(int(heat))
                    except Exception:
                        pass

                    if heat >= 100.0:
                        log(self.cfg, "[CHALLENGE] heat reached 100% – killing VPX")
                        audits_now = audits
                        try:
                            audits_now2, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                            if audits_now2:
                                audits_now = audits_now2
                        except Exception:
                            pass
                        if audits_now:
                            try:
                                self._last_audits_global = dict(audits_now)
                            except Exception:
                                pass
                            try:
                                duration_now = int(now - (self.start_time or now))
                                self.export_overlay_snapshot(audits_now, duration_now, on_demand=True)
                            except Exception:
                                pass
                            ch["prekill_end"] = dict(audits_now)

                        try:
                            self._kill_vpx_process()
                        except Exception:
                            pass

                        ch["active"] = False
                        ch["pending_kill_at"] = None
                        ch["completed"] = True
                        self.challenge = ch

                        try:
                            self._heat_inputs["joy_running"] = False
                        except Exception:
                            pass
                        try:
                            self.bridge.heat_bar_hide.emit()
                        except Exception:
                            pass
                        log(self.cfg, "[CHALLENGE] heat finished – VPX killed")
                        return
                except Exception as e:
                    log(self.cfg, f"[CHALLENGE] heat tick failed: {e}", "WARN")

        except Exception as e:
            log(self.cfg, f"[CHALLENGE] tick failed: {e}", "WARN")
 
    def _challenge_best_final_score(self, end_audits: dict, pid: int = 1) -> int:
        # Single-player only
        try:
            v = int((end_audits or {}).get("P1 Score", 0) or 0)
            if v > 0:
                return v

            cache = getattr(self, "_last_audits_global", {}) or {}
            cv = int(cache.get("P1 Score", 0) or 0)
            if cv > 0:
                return cv

            balls = (self.ball_track or {}).get("balls", []) or []
            if balls:
                best_ball = max(balls, key=lambda b: (int(b.get("score", 0)), int(b.get("duration", 0))))
                bv = int(best_ball.get("score", 0) or 0)
                if bv > 0:
                    return bv
        except Exception:
            pass
        return 0

    def _inject_best_score_for_timed(self, end_audits: dict) -> dict:
        try:
            ch = getattr(self, "challenge", {}) or {}
            if str(ch.get("kind", "")).lower() != "timed":
                return dict(end_audits or {})

            ea = dict(end_audits or {})
            best = self._challenge_best_final_score(ea, pid=1)
            if best > 0:
                ea["P1 Score"] = best
                log(self.cfg, f"[CHALLENGE] timed: injected best P1 Score={best}")
            return ea
        except Exception:
            return dict(end_audits or {})
            
    def _challenge_record_result(self, kind: str, end_audits: dict, duration_sec: int):
        try:
            ch = getattr(self, "challenge", {}) or {}

            if not ch.get("completed", False):
                log(self.cfg, f"[CHALLENGE] Aborted early by player. Score NOT recorded/uploaded.")
                return

            now = time.time()
            started_at = float(ch.get("started_at", now))
            if (now - started_at) < 2.0:
                return

            if ch.get("result_recorded"):
                return

            rom = ch.get("rom") or self.current_rom or ""
            key = f"{rom}|{str(kind or '').lower()}"

            last = getattr(self, "_ch_result_recent", {"k": "", "ts": 0.0})
            if last.get("k") == key and (now - float(last.get("ts", 0.0))) < 5.0:
                return
            self._ch_result_recent = {"k": key, "ts": now}

            if not rom:
                return

            table = ch.get("table") or self.current_table or ""
            try:
                score = int(self._challenge_best_final_score(end_audits, pid=1) or 0)
            except Exception:
                score = 0

            payload = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": str(kind or ""),
                "rom": rom,
                "table": table,
                "duration_sec": int(duration_sec or 0),
                "score": int(score)
            }

            extra = {}
            if str(kind or "").lower() == "flip":
                tf = int(ch.get("threshold", 0))
                payload["target_flips"] = tf
                
                if tf <= 100: diff_name = "Pro"
                elif tf <= 200: diff_name = "Difficult"
                elif tf <= 300: diff_name = "Medium"
                elif tf <= 400: diff_name = "Easy"
                else: diff_name = f"{tf} Flips"
                
                payload["difficulty"] = diff_name
                extra = {"target_flips": tf, "difficulty": diff_name}

            out_dir = os.path.join(self.cfg.BASE, "session_stats", "challenges", "history")
            ensure_dir(out_dir)
            path = os.path.join(out_dir, f"{sanitize_filename(rom)}.json")
            hist = secure_load_json(path, {"results": []}) or {"results": []}
            hist.setdefault("results", []).append(payload)
            secure_save_json(path, hist)

            # Re-evaluate challenge_count achievements immediately after recording
            try:
                self._evaluate_challenge_count_achievements()
            except Exception:
                pass

            CloudSync.upload_score(self.cfg, kind, rom, int(score), extra, bridge=self.bridge)
            
            ch["result_recorded"] = True
            self.challenge = ch

            try:
                phrase = f"{str(kind or '').capitalize()} challenge finished."
                self.bridge.challenge_speak.emit(phrase)
            except Exception:
                pass
            try:
                score_txt = f"{int(score):,d}".replace(",", ".")
                if str(kind or "").lower() == "timed":
                    title = "TIME'S UP!"
                else:
                    title = "CHALLENGE COMPLETE!"
                self.bridge.challenge_info_show.emit(f"{title}<br>Score: {score_txt}", 8, "#FFFFFF")
            except Exception:
                pass

            try:
                deadline = time.time() + 3.0
                while self._vp_player_visible() and time.time() < deadline:
                    time.sleep(0.1)
            except Exception:
                pass

        except Exception as e:
            log(self.cfg, f"[CHALLENGE] record result failed: {e}", "WARN")
                
    @staticmethod
    def _is_number(x):
        try:
            int(x)
            return True
        except Exception:
            return False

    @staticmethod
    def _extract_numeric(value):
        try:
            return int(value)
        except Exception:
            try:
                return int(float(value))
            except Exception:
                return 0

    @staticmethod
    def _player_field_filter(audits: dict, pid: int) -> dict:
        prefix = f"P{pid} "
        return {k: v for k, v in audits.items() if isinstance(k, str) and k.startswith(prefix)}

    def _find_score_from_audits(self, audits: dict, pid: Optional[int] = None) -> int:
        """
        SINGLE-PLAYER MODE: nur P1.
        """
        def _is_num(x):
            try:
                int(x)
                return True
            except Exception:
                return False

        val = (audits or {}).get("P1 Score")
        if _is_num(val):
            return int(val)

        val = (audits or {}).get("Score")
        return int(val) if _is_num(val) else 0

    def _build_events_from_deltas(self, deltas: dict) -> dict:
        events = {k: 0 for k in self.HIGHLIGHT_RULES.keys()}
        for label, val in deltas.items():
            if not isinstance(val, int) or val <= 0:
                continue
                
            l = str(label).lower()
            
            if any(noise in l for noise in ["max ", "count", "system", "percent", "boost", "allow", "level"]):
                continue

            # 2. Treffer sammeln
            matched_keys = []
            for key, words in self.EVENT_KEYWORDS.items():
                if any(w in l for w in words):
                    matched_keys.append(key)
            
            if "super_jackpot" in matched_keys and "jackpot" in matched_keys:
                matched_keys.remove("jackpot")
            if "triple_jackpot" in matched_keys and "jackpot" in matched_keys:
                matched_keys.remove("jackpot")
            if "super_skillshot" in matched_keys and "skillshot" in matched_keys:
                matched_keys.remove("skillshot")
            if "mode_completed" in matched_keys and "mode_starts" in matched_keys:
                matched_keys.remove("mode_starts")
                
            if "jackpot" in matched_keys and "multiball" in matched_keys:
                matched_keys.remove("multiball")
            if "super_jackpot" in matched_keys and "multiball" in matched_keys:
                matched_keys.remove("multiball")
                
            for key in matched_keys:
                events[key] = events.get(key, 0) + int(val)
                
        return events

    def _attribute_events(self, audits: dict) -> bool:
        if not audits or not getattr(self, "current_player", None) or (self.current_player not in self.players):
            try:
                self._last_global_for_player_attr = {
                    k: v for k, v in audits.items() if isinstance(k, str) and not k.startswith("P")
                }
            except Exception:
                pass
            return False
        try:
            prev = getattr(self, "_last_global_for_player_attr", {}) or {}
            cur_player = int(self.current_player or 1)
            player_rec = self.players.setdefault(cur_player, {
                "start_audits": self._player_field_filter(self.start_audits, cur_player) or {f"P{cur_player} Score": 0},
                "last_audits": self._player_field_filter(self.start_audits, cur_player) or {f"P{cur_player} Score": 0},
                "active_play_seconds": 0.0,
                "start_time": time.time(),
                "session_deltas": {},
                "event_counts": {},
            })
        except Exception:
            return False
            
        changed = False
        ignore_list = {"current_ball", "game over", "tilted", "credits", "player_count", "total plays", "1 player games", "2 player games", "3 player games", "4 player games"}
        
        for label, val_now in (audits or {}).items():
            if not isinstance(label, str):
                continue
            if label.startswith("P"):
                continue
            
            if is_excluded_field(label) or label.lower() in ignore_list:
                continue
                
            ll = label.lower()
            if "score" in ll:
                continue
            try:
                now_i = int(val_now or 0)
            except Exception:
                continue
            try:
                old_i = int(prev.get(label, 0) or 0)
            except Exception:
                old_i = 0
            diff = now_i - old_i
            if diff <= 0:
                continue
            try:
                sd = player_rec.setdefault("session_deltas", {})
                sd[label] = sd.get(label, 0) + int(diff)
            except Exception:
                pass
            for ev_key, words in (self.EVENT_KEYWORDS or {}).items():
                if any(w in ll for w in words):
                    try:
                        ec = player_rec.setdefault("event_counts", {})
                        ec[ev_key] = ec.get(ev_key, 0) + int(diff)
                        changed = True
                    except Exception:
                        pass
                    break
        try:
            self._last_global_for_player_attr = {
                k: v for k, v in audits.items() if isinstance(k, str) and not k.startswith("P")
            }
        except Exception:
            pass
        return bool(changed)

    def _icon(self, key: str, prefer_ascii: bool | None = None) -> str:
        ov = getattr(self.cfg, "OVERLAY", {}) or {}
        use_ascii = ov.get("prefer_ascii_icons", True) if prefer_ascii is None else bool(prefer_ascii)
        if use_ascii:
            ascii_map = {
                "best_ball": "[BB]",
                "wizard_mode": "[WZ]",
                "multiball": "[MB]",
                "jackpot": "[JP]",
                "super_jackpot": "[SJP]",
                "triple_jackpot": "[TJP]",
                "ball_save": "[BS]",
                "extra_ball": "[EB]",
                "special_award": "[SPC]",
                "mode_completed": "[MODE✓]",
                "loops": "[LOOP]",
                "spinner": "[SPIN]",
                "combo": "[COMBO]",
                "drop_targets": "[DT]",
                "ramps": "[RAMP]",
                "orbit": "[ORBIT]",
                "skillshot": "[SS]",
                "super_skillshot": "[SS+]",
                "mode_starts": "[MODE]",
                "tilt_warnings": "[TILT!]",
                "tilt": "[TILT]",
                "devils_number": "[666]",
                "match": "[MATCH]",
                "initials": "[INIT]",
            }
            return ascii_map.get(key, "[*]")
        else:
            emoji_map = {
                "best_ball": "🔥",
                "wizard_mode": "🧙",
                "multiball": "💥",
                "jackpot": "🎯",
                "super_jackpot": "💎",
                "triple_jackpot": "👑",
                "ball_save": "🛡️",
                "extra_ball": "➕",
                "special_award": "🎁",
                "mode_completed": "🏆",
                "loops": "🔁",
                "spinner": "🌀",
                "combo": "🎯",
                "drop_targets": "🎯",
                "ramps": "🏹",
                "orbit": "🌌",
                "skillshot": "🎯",
                "super_skillshot": "💥",
                "mode_starts": "🎬",
                "tilt_warnings": "🛡️",
                "tilt": "💀",
                "devils_number": "👹",
                "match": "🎲",
                "initials": "✍️",
            }
            return emoji_map.get(key, "•")
            
    def analyze_session(self, stats: dict) -> dict:
        events = stats.get("events", {}) or {}
        duration_sec = int(stats.get("duration_sec", 0) or 0)
        lines_per_cat = int((self.cfg.OVERLAY or {}).get("lines_per_category", 5))
        out = {"Power": [], "Precision": [], "Fun": []}
        buckets = {"Power": [], "Precision": [], "Fun": []}
        for key, rule in (self.HIGHLIGHT_RULES or {}).items():
            if key == "best_ball":
                continue
            cat = rule.get("cat", "Fun")
            typ = rule.get("type", "count")
            icon = self._icon(key)
            if typ == "count":
                val = int(events.get(key, 0) or 0)
                if val > 0:
                    base_w = 100
                    weight = base_w + val
                    label = f"{icon} {rule.get('label','')}".strip()
                    buckets[cat].append((weight, f"{label} – {val}"))
            elif typ == "flag":
                v = events.get(key, False)
                if isinstance(v, str):
                    v = v.strip()
                    if v:
                        buckets[cat].append((150, f"{icon} {rule.get('label','')} – {v}"))
                elif bool(v):
                    buckets[cat].append((150, f"{icon} {rule.get('label','')} – Yes"))
        for cat in ["Power", "Precision", "Fun"]:
            arr = sorted(buckets[cat], key=lambda x: x[0], reverse=True)[:max(1, lines_per_cat)]
            out[cat] = [s for _, s in arr]
        return out

    def _get_balls_played(self, audits: dict) -> Optional[int]:
        kl = {str(k).lower(): k for k in audits.keys()}
        for key in ["balls played", "games balls played", "total balls played"]:
            if key in kl:
                try:
                    return int(audits[kl[key]])
                except Exception:
                    pass
        for lk, orig in kl.items():
            if lk == "ball count" or ("ball" in lk and "count" in lk):
                try:
                    return int(audits[orig])
                except Exception:
                    continue
        for lk, orig in kl.items():
            if "balls" in lk and "played" in lk:
                try:
                    return int(audits[orig])
                except Exception:
                    continue
        return None

    def _nv_get_int_ci(self, audits: dict, label: str, default: int = 0) -> int:
        try:
            kl = {str(k).lower(): k for k in audits.keys()}
            key = kl.get(label.lower())
            if key is None:
                return int(default)
            return int(audits.get(key, default) or default)
        except Exception:
            return int(default)

    def _ball_reset(self, start_audits: dict):
        self.ball_track.update({
            "active": True,
            "index": 1,
            "start_time": time.time(),
            "current_pid": int(getattr(self, "current_player", 1) or 1),
            "score_base": self._find_score_from_audits(start_audits, pid=int(getattr(self, "current_player", 1) or 1)),
            "last_balls_played": self._get_balls_played(start_audits),
            "balls": []
        })

    def _ball_finalize_current(self, current_audits: dict, force: bool = False):
        if not self.ball_track.get("active"):
            return
        now = time.time()
        pid = int(self.ball_track.get("current_pid") or getattr(self, "current_player", 1) or 1)
        cur_score = self._find_score_from_audits(current_audits, pid=pid)
        base_score = int(self.ball_track.get("score_base", 0))
        ball_score = max(0, int(cur_score) - base_score)
        if ball_score == 0 and cur_score > 0 and base_score == 0:
            ball_score = cur_score
        duration = int(now - (self.ball_track.get("start_time") or now))
        if force or ball_score > 0 or duration > 0:
            entry = {
                "pid": pid,
                "num": self.ball_track.get("index", 1),
                "score": int(ball_score),
                "score_abs": int(cur_score),
                "duration": duration
            }
            self.ball_track["balls"].append(entry)
            self.ball_track["index"] = int(self.ball_track.get("index", 1)) + 1
            self.ball_track["start_time"] = now
            self.ball_track["score_base"] = cur_score

    def _ball_update(self, current_audits: dict):
        if not self.ball_track.get("active"):
            return
        cp = int(getattr(self, "current_player", 1) or 1)
        if cp != int(self.ball_track.get("current_pid") or cp):
            self._ball_finalize_current(current_audits, force=False)
            self.ball_track["current_pid"] = cp
            self.ball_track["start_time"] = time.time()
            self.ball_track["score_base"] = self._find_score_from_audits(current_audits, pid=cp)
        bp = self._get_balls_played(current_audits)
        if bp is None:
            return
        if self.ball_track.get("last_balls_played") is None:
            self.ball_track["last_balls_played"] = bp
            return
        if bp > int(self.ball_track.get("last_balls_played", 0)):
            self._ball_finalize_current(current_audits, force=False)
            self.ball_track["last_balls_played"] = bp
            cp = int(getattr(self, "current_player", 1) or 1)
            self.ball_track["current_pid"] = cp
            self.ball_track["start_time"] = time.time()
            self.ball_track["score_base"] = self._find_score_from_audits(current_audits, pid=cp)
  
    def _best_ball_for_player(self, pid: int):
        try:
            balls = [b for b in self.ball_track.get("balls", []) if int(b.get("pid", 0)) == pid]
            if not balls:
                return None
            return max(balls, key=lambda b: (int(b.get("score", 0)), int(b.get("duration", 0))))
        except Exception:
            return None

    def _init_player_snaps(self, start_audits: dict):
        self.players.clear()
        now = time.time()
        for pid in range(1, 5):
            snap = self._player_field_filter(start_audits, pid)
            if not snap:
                snap = {f"P{pid} Score": 0}
            self.players[pid] = {
                "start_audits": dict(snap),
                "last_audits": dict(snap),
                "active_play_seconds": 0.0,
                "start_time": now,
                "session_deltas": {},
                "event_counts": {},
            }
        self._last_tick_time = time.time()
        self._last_global_for_player_attr = {
            k: v for k, v in start_audits.items() if isinstance(k, str) and not k.startswith("P")
        }

    def _compute_session_deltas(self, start: dict, end: dict) -> dict:
        out = {}
        if not isinstance(end, dict):
            return out
        start = start or {}
        
        ignore_list = {"current_ball", "game over", "tilted", "credits", "player_count", "1 player games", "2 player games", "3 player games", "4 player games"}
        
        for k, ve in end.items():
            if not isinstance(k, str) or k.startswith("P"):
                continue
                
            if is_excluded_field(k) or k.lower() in ignore_list:
                continue
                
            try:
                s = int(start.get(k, 0) or 0)
                e = int(ve or 0)
            except Exception:
                continue
            d = e - s
            if d < 0:
                d = 0
            if d > 0:
                out[k] = d
        return out
        
    def _build_session_stats(self, start_audits: dict, end_audits: dict, duration_sec: int) -> dict:
        deltas = self._compute_session_deltas(start_audits, end_audits)
        events = self._build_events_from_deltas(deltas)
        score_final = self._find_score_from_audits(end_audits)
        events["devils_number"] = ("666" in str(score_final))
        initials = ""
        for k in end_audits.keys():
            if "initial" in str(k).lower():
                initials = str(end_audits.get(k) or "").strip()
                break
        events["initials"] = initials
        return {"score": score_final, "duration_sec": duration_sec, "events": events}

    def export_overlay_snapshot(self, end_audits: dict, duration_sec: int, on_demand: bool = False) -> str:
        """
        SINGLE-PLAYER MODE:
        Exportiert nur Player-1-Highlightdatei.
        """
        try:
            if on_demand and (self.game_active or self._vp_player_visible()):
                return os.path.join(p_highlights(self.cfg), "activePlayers")
        except Exception:
            pass

        self._latest_end_audits_cache = dict(end_audits)
        try:
            self._ball_finalize_current(end_audits, force=True)
        except Exception as e:
            log(self.cfg, f"[BALL] finalize current failed: {e}", "WARN")

        active_dir = os.path.join(p_highlights(self.cfg), "activePlayers")
        ensure_dir(active_dir)

        pid = 1
        rec = self.players.get(pid, {})
        play_sec = int(rec.get("active_play_seconds", 0.0) or 0)
        deltas_for_player = rec.get("session_deltas", {}) or {}
        events_from_deltas = self._build_events_from_deltas(deltas_for_player)

        events_from_counts = {}
        try:
            for k, v in (rec.get("event_counts", {}) or {}).items():
                events_from_counts[k] = int(v or 0)
        except Exception:
            events_from_counts = {}

        merged_events = dict(events_from_deltas)
        for k, v in events_from_counts.items():
            merged_events[k] = max(int(merged_events.get(k, 0) or 0), int(v or 0))

        analysis_sec = play_sec if play_sec > 0 else int(duration_sec or 0)
        try:
            score_abs = int(self._find_score_from_audits(end_audits, pid=1) or 0)
        except Exception:
            score_abs = 0

        try:
            n_balls = self._player_balls_count(1)
            if isinstance(n_balls, int) and n_balls >= 0:
                if merged_events.get("skillshot", 0) > n_balls:
                    merged_events["skillshot"] = n_balls
        except Exception:
            pass

        events_aug = self._augment_player_events_with_flags(score_abs, end_audits, merged_events)
        pseudo_stats = {
            "score": score_abs,
            "duration_sec": analysis_sec,
            "events": events_aug,
        }

        try:
            highlights = self.analyze_session(pseudo_stats)
        except Exception as e:
            log(self.cfg, f"[HIGHLIGHTS] analyze_session failed for P1: {e}", "WARN")
            highlights = {"Power": [], "Precision": [], "Fun": []}

        payload = {
            "player": 1,
            "rom": self.current_rom,
            "playtime_sec": play_sec,
            "score": score_abs,
            "highlights": highlights,
        }

        # Cache the payload in memory so the overlay can read it without waiting for disk I/O
        self._overlay_snapshot_cache = payload

        save_json(os.path.join(active_dir, f"{self.current_rom}_P1.json"), payload)

        try:
            for pid_old in (2, 3, 4):
                fp = os.path.join(active_dir, f"{self.current_rom}_P{pid_old}.json")
                if os.path.isfile(fp):
                    os.remove(fp)
        except Exception:
            pass

        if not on_demand:
            log(self.cfg, "[EXPORT] session-only activePlayers written (P1 only)")
        return active_dir

    def on_session_start(self, table_or_rom: str, is_rom: bool = False):
        if is_rom:
            self.current_rom = table_or_rom
            self.current_table = f"(ROM only: {self.current_rom})"
            self._table_load_ts = time.time()
        else:
            self.current_table = table_or_rom

        try:
            cands = self._all_rom_candidates(self.current_rom or "")
            log(self.cfg, f"[ROM] candidates for {self.current_rom}: {cands[:12]}")
        except Exception:
            pass

        self.start_time = time.time()
        self.game_active = True
        self.players.clear()
        self._toasted_titles = set()

        self.start_audits, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)

        try:
            self._ensure_rom_specific(self.current_rom, self.start_audits)
        except Exception as e:
            log(self.cfg, f"[ROM_SPEC] generation failed: {e}", "WARN")

        self._last_audits_global = dict(self.start_audits)

        try:
            self._ball_reset(self.start_audits)
        except Exception as e:
            log(self.cfg, f"[BALL] reset failed: {e}", "WARN")

    def _ensure_singleplayer_min_playtime(self, nplayers: int, duration_sec: int) -> None:
        try:
            if int(nplayers) == 1:
                cur = int(self.players.get(1, {}).get("active_play_seconds") or 0)
                if cur < int(duration_sec):
                    self.players.setdefault(1, {})["active_play_seconds"] = int(duration_sec)
        except Exception:
            pass
           
    def on_session_end(self):
        if not self.game_active:
            return

        ch = getattr(self, "challenge", {}) or {}
        is_challenge = str(ch.get("kind", "")).lower() in ("timed", "oneball", "flip", "heat")
        ch_aborted = is_challenge and not ch.get("completed", False)

        if is_challenge:
            try:
                if hasattr(self.bridge, "flip_counter_total_hide"):
                    self.bridge.flip_counter_total_hide.emit()
            except Exception: pass
            
            try:
                if hasattr(self.bridge, "challenge_timer_stop"):
                    self.bridge.challenge_timer_stop.emit() 
            except Exception: pass
            
            try:
                if hasattr(self, "_flip_stop_inputs"):
                    self._flip_stop_inputs()
            except Exception: pass

            try:
                self._heat_inputs["joy_running"] = False
            except Exception: pass

            try:
                if hasattr(self.bridge, "heat_bar_hide"):
                    self.bridge.heat_bar_hide.emit()
            except Exception: pass
            
            if ch_aborted:
                try:
                    self.bridge.challenge_info_show.emit("Challenge Aborted!", 3, "#FF3B30")
                except Exception: pass

        # 2. DELAY NUR BEI ERFOLG (Verhindert langes Warten beim manuellen Abbruch)
        if is_challenge and not ch_aborted:
            try:
                delay_ms = int((self.cfg.OVERLAY or {}).get("ch_finalize_delay_ms", 2000))
                if delay_ms > 0:
                    time.sleep(max(0.0, delay_ms / 1000.0))
            except Exception:
                pass

        try:
            end_ts = time.time()
            duration_sec = int(end_ts - (self.start_time or end_ts))
            duration_str = str(timedelta(seconds=duration_sec))
            pre = ch.get("prekill_end") if isinstance(ch.get("prekill_end", None), dict) else None
            self._session_rom_for_notif = self.current_rom

            if is_challenge:
                try:
                    end_audits, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                except Exception as e:
                    log(self.cfg, f"[END] read end audits (challenge) failed: {e}", "WARN")
                    end_audits = {}
                if not end_audits:
                    end_audits = dict(pre) if pre else dict(self._last_audits_global)
            else:
                if pre:
                    end_audits = dict(pre)
                else:
                    try:
                        end_audits, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                        if not end_audits:
                            raise RuntimeError("Empty end_audits")
                    except Exception as e:
                        log(self.cfg, f"[END] read end audits failed, using last known: {e}", "WARN")
                        end_audits = dict(self._last_audits_global)

            nplayers = 1
            seg_deltas = {1: self._compute_session_deltas(self.start_audits, end_audits)}
            self.players.setdefault(1, {
                "start_audits": self._player_field_filter(self.start_audits, 1) or {"P1 Score": 0},
                "last_audits": self._player_field_filter(end_audits, 1) or {"P1 Score": 0},
                "active_play_seconds": float(self.players.get(1, {}).get("active_play_seconds", 0.0)),
                "start_time": self.players.get(1, {}).get("start_time", time.time()),
                "session_deltas": {},
                "event_counts": self.players.get(1, {}).get("event_counts", {}),
            })
            self.players[1]["session_deltas"] = dict(seg_deltas.get(1, {}) or {})
            self.players[1]["active_play_seconds"] = max(
                int(self.players[1].get("active_play_seconds", 0) or 0),
                int(duration_sec)
            )

            if is_challenge:
                log(self.cfg, f"[SESSION END] Challenge finished: rom={self.current_rom}, duration={duration_str}. Skipping NVRAM dumps and regular achievements.")
                try:
                    if str(ch.get("kind", "")).lower() == "timed":
                        end_audits = self._inject_best_score_for_timed(end_audits)
                    if not ch.get("result_recorded", False):
                        self._challenge_record_result(str(ch.get("kind")), end_audits, duration_sec)
                except Exception as e:
                    log(self.cfg, f"[CHALLENGE] result finalize failed: {e}", "WARN")
            else:
                log(self.cfg, f"[SESSION END] Normal session finished: rom={self.current_rom}, duration={duration_str}")
                try:
                    self._export_summary(end_audits, duration_sec)
                except Exception as e:
                    log(self.cfg, f"[SUMMARY] export failed: {e}", "WARN")

                try:
                    self.export_overlay_snapshot(end_audits, duration_sec)
                except Exception as e:
                    log(self.cfg, f"[OVERLAY] export snapshot failed: {e}", "WARN")

                # Fire the overlay signal immediately after the snapshot data is ready,
                # before slow achievement persistence and cloud uploads.
                try:
                    if (self.cfg.OVERLAY or {}).get("auto_show_on_end", True):
                        if self.current_rom and self._has_any_map(self.current_rom):
                            self.bridge.overlay_show.emit()
                        else:
                            log(self.cfg, f"[OVERLAY] Skipped auto-show because no NVRAM map exists for {self.current_rom}")
                except Exception as e:
                    log(self.cfg, f"[OVERLAY] auto-show emit failed: {e}", "WARN")

                try:
                    self._persist_and_toast_achievements(end_audits, duration_sec)
                except Exception as e:
                    log(self.cfg, f"[ACHIEVEMENTS] persist/toast failed: {e}", "WARN")

                if self.current_rom and self._has_any_map(self.current_rom):
                    try:
                        s_rules = self._collect_player_rules_for_rom(self.current_rom)
                        
                        unique_achs = set()
                        for r in s_rules:
                            if isinstance(r, dict) and r.get("title"):
                                unique_achs.add(str(r.get("title")).strip())
                        total_achs = len(unique_achs)
                        
                        if total_achs > 0:
                            state = self._ach_state_load()
                            
                            unlocked_titles = set()
                            for e in state.get("session", {}).get(self.current_rom, []):
                                t = str(e.get("title")).strip() if isinstance(e, dict) else str(e).strip()
                                if t: unlocked_titles.add(t)
                                
                            unlocked_total = len(unlocked_titles)
                            _rom = self.current_rom
                            _cfg = self.cfg
                            _br = self.bridge
                            threading.Thread(
                                target=lambda _c=_cfg, _r=_rom, _ut=unlocked_total, _ta=total_achs, _b=_br:
                                    CloudSync.upload_achievement_progress(_c, _r, _ut, _ta, bridge=_b),
                                daemon=True,
                            ).start()
                            # Retroactive upload: if this ROM now has a VPS-ID but was previously
                            # blocked (progress_upload_log has no entry or a different vps_id),
                            # the upload above will succeed this time. Record the vps_id used.
                            try:
                                from ui_vps import _load_vps_mapping
                                _vps_mapping = _load_vps_mapping(self.cfg)
                                _vps_id = (_vps_mapping.get(self.current_rom) or "").strip()
                                if _vps_id:
                                    _upload_log = _load_progress_upload_log(self.cfg)
                                    _prev_vps_id = _upload_log.get(self.current_rom, "")
                                    if _prev_vps_id != _vps_id:
                                        _upload_log[self.current_rom] = _vps_id
                                        _save_progress_upload_log(self.cfg, _upload_log)
                                        log(self.cfg, f"[CLOUD] Progress upload log updated for {self.current_rom} -> vps_id={_vps_id}")
                            except Exception as e:
                                log(self.cfg, f"[CLOUD] Progress upload log update failed: {e}", "WARN")
                    except Exception as e:
                        log(self.cfg, f"[CLOUD] Progress upload failed: {e}", "WARN")

        finally:
            self.current_table = None
            self.current_rom = None
            self.start_time = None
            self.game_active = False
            self.start_audits = {}
            self.challenge = {} 
            self.players.clear()
            self.ball_track.update({"active": False, "index": 0, "start_time": None, "score_base": 0, "last_balls_played": None, "balls": []})
            self._last_audits_global = {}
            self.snap_initialized = False
            self.field_stats.clear()
            self.bootstrap_phase = False
            self.current_segment_provisional_diff = {}
            try:
                if hasattr(self.bridge, 'close_secondary_overlays'):
                    self.bridge.close_secondary_overlays.emit()
            except Exception:
                pass
            try:
                _ended_rom = getattr(self, "_session_rom_for_notif", None)
                if _ended_rom and hasattr(self.bridge, "session_ended"):
                    self.bridge.session_ended.emit(_ended_rom)
            except Exception:
                pass
            self._session_rom_for_notif = None
                
    def monitor_table(self) -> Optional[Dict[str, str]]:
        if not win32gui:
            return None

        def _cb(hwnd, acc):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.startswith("Visual Pinball - ["):
                    acc.append(title)

        wins = []
        try:
            win32gui.EnumWindows(_cb, wins)
        except Exception:
            return None

        if not wins:
            return None

        title = wins[0]
        if not (title.startswith("Visual Pinball - [") and title.endswith("]")):
            return None

        table_fragment = title[len("Visual Pinball - ["):-1]
        vpx_filename = table_fragment if table_fragment.lower().endswith(".vpx") else table_fragment + ".vpx"

        vpx_path = os.path.join(self.cfg.TABLES_DIR, vpx_filename)
        if not os.path.isfile(vpx_path):
            alt = os.path.join(self.cfg.TABLES_DIR, table_fragment)
            vpx_path = alt if os.path.isfile(alt) else None

        cache = getattr(self, "_rom_detect_cache", None)
        if not isinstance(cache, dict):
            cache = {"vpx_path": None, "rom": None, "ts": 0.0}
            self._rom_detect_cache = cache

        rom = None
        if vpx_path and os.path.isfile(vpx_path):
            now = time.time()
            cache_path = cache.get("vpx_path")
            cache_rom = cache.get("rom")
            cache_ts = float(cache.get("ts") or 0.0)

            if cache_path == vpx_path and cache_rom and (now - cache_ts) < 120:
                rom = cache_rom
            else:
                rom = run_vpxtool_get_rom(self.cfg, vpx_path)
                if rom:
                    self._rom_detect_cache = {"vpx_path": vpx_path, "rom": rom, "ts": now}
                    try:
                        if rom != self._last_logged_rom:
                            log(self.cfg, f"[ROM] VPXTOOL: {rom}")
                            self._last_logged_rom = rom
                    except Exception:
                        pass

        clean_table = table_fragment[:-4] if table_fragment.lower().endswith(".vpx") else table_fragment

        if not rom:
            try:
                log(self.cfg, f"[ROM] vpxtool failed for table '{vpx_filename}'", "WARN")
            except Exception:
                pass
            return None

        return {"table": clean_table, "rom": rom, "vpx_file": vpx_path or ""}
    
    def _thread_main(self):
        log(self.cfg, ">>> watcher thread running")
        # Lower thread priority so VPX always gets CPU scheduler priority
        try:
            THREAD_PRIORITY_BELOW_NORMAL = -1
            handle = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadPriority(handle, THREAD_PRIORITY_BELOW_NORMAL)
            log(self.cfg, "[WATCHER] thread priority set to BELOW_NORMAL")
        except Exception as e:
            log(self.cfg, f"[WATCHER] could not set thread priority: {e}", "WARN")
        active_rom = None
        if not hasattr(self, "_last_live_export_ts"):
            self._last_live_export_ts = 0.0
        self._missing_table_ticks = 0  
        while not self._stop.is_set():
            now_loop = time.time()
            dt = now_loop - getattr(self, "_last_tick_time", now_loop)
            if dt < 0 or dt > 5:
                dt = 0.5
            self._last_tick_time = now_loop

            try:
                upd = self.monitor_table()
            except Exception as e:
                log(self.cfg, f"[WATCHER] monitor error: {e}", "WARN")
                upd = None

            if upd:
                self._missing_table_ticks = 0  
                rom = (upd.get("rom") or "").strip()

                if active_rom is None and rom:
                    self.on_session_start(rom, is_rom=True)
                    active_rom = rom
                    self._emit_mini_info_if_missing_map(rom, 5)
                    self._emit_mini_info_if_missing_vps_id(rom, 8)

                elif active_rom and rom and rom != active_rom:
                    self.on_session_end()
                    active_rom = None
                    self.on_session_start(rom, is_rom=True)
                    active_rom = rom
                    self._emit_mini_info_if_missing_map(rom, 5)
                    self._emit_mini_info_if_missing_vps_id(rom, 8)

                if active_rom:
                    audits, _, _ = self.read_nvram_audits_with_autofix(self.current_rom)
                    audits_ctl = audits 

                    ch = getattr(self, "challenge", {}) or {}
                    is_chal_active = ch.get("active", False)

                    try:
                        now2 = time.time()
                        if self.current_rom and self.cfg.OVERLAY.get("live_updates", False) and (now2 - self._last_live_export_ts >= 2.0):
                            if not is_chal_active:
                                duration_sec = int(now2 - (self.start_time or now2))
                                self.export_overlay_snapshot(audits, duration_sec, on_demand=True)
                            self._last_live_export_ts = now2
                    except Exception as e:
                        log(self.cfg, f"[EXPORT] live export failed: {e}", "WARN")

                    self.current_segment_provisional_diff = {}

                    self.current_player = 1
                    try:
                        if 1 in self.players:
                            self.players[1]["active_play_seconds"] = float(self.players[1].get("active_play_seconds", 0.0)) + dt
                    except Exception:
                        pass

                    try:
                        changed = bool(self._attribute_events(audits_ctl))
                        if changed and self.cfg.OVERLAY.get("live_updates", False) and not is_chal_active:
                            duration_now = int(time.time() - (self.start_time or time.time()))
                            self.export_overlay_snapshot(audits, duration_now, on_demand=True)
                            self._last_live_export_ts = time.time()
                    except Exception as e:
                        log(self.cfg, f"[HIGHLIGHTS] live attribute failed: {e}", "WARN")

                    self.players.setdefault(1, {
                        "start_audits": self._player_field_filter(self.start_audits, 1) or {"P1 Score": 0},
                        "last_audits": self._player_field_filter(self.start_audits, 1) or {"P1 Score": 0},
                        "active_play_seconds": 0.0,
                        "start_time": time.time(),
                        "session_deltas": {},
                        "event_counts": {},
                    })
                    p1_audits = self._player_field_filter(audits, 1)
                    if p1_audits:
                        self.players[1]["last_audits"].update(p1_audits)

                    try:
                        self._challenge_tick(audits_ctl)
                    except Exception as e:
                        log(self.cfg, f"[CHALLENGE] tick failed in loop: {e}", "WARN")

                    if self.snapshot_mode:
                        try:
                            self._ball_update(audits_ctl)
                        except Exception as e:
                            log(self.cfg, f"[BALL] update failed: {e}", "WARN")
            else:
                if active_rom is not None:

                    self._missing_table_ticks += 1
                    if self._missing_table_ticks >= 4: 
                        self.on_session_end()
                        active_rom = None
                        self._missing_table_ticks = 0

            # Sleep longer while game is active to reduce CPU/IO pressure on VPX
            if active_rom is not None:
                time.sleep(1.0)
            else:
                time.sleep(2.0)

    def start(self):
        if getattr(self, "thread", None) and self.thread.is_alive():
            return
        try:
            _migrate_runtime_dirs(self.cfg)
        except Exception as e:
            log(self.cfg, f"[MIGRATE] failed: {e}", "WARN")
        try:
            self.bootstrap()
        except Exception as e:
            log(self.cfg, f"[BOOTSTRAP] failed: {e}", "WARN")
        try:
            self._ensure_global_ach()
        except Exception as e:
            log(self.cfg, f"[GLOBAL_ACH] ensure failed: {e}", "WARN")
        try:
            self.start_prefetch_background()
        except Exception as e:
            log(self.cfg, f"[PREFETCH] auto-start failed: {e}", "WARN")
        self._stop.clear()
        self.thread = threading.Thread(target=self._thread_main, daemon=True, name="WatcherThread")
        self.thread.start()

    def stop(self):
        try:
            self._stop.set()
            if getattr(self, "thread", None):
                self.thread.join(timeout=3)
        except Exception:
            pass

        if self.game_active:
            try:
                self.on_session_end()
            except Exception as e:
                log(self.cfg, f"[WATCHER] on_session_end during stop failed: {e}", "WARN")

        log(self.cfg, "[WATCHER] stopped")
            
