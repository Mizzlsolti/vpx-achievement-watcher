from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List

from vpx_achievement_watcher.core.constants import DEFAULT_OVERLAY, DEFAULT_LOG_SUPPRESS
from vpx_achievement_watcher.core.helpers import APP_DIR

CONFIG_FILE = os.path.join(APP_DIR, "config.json")


@dataclass
class AppConfig:
    BASE: str = r"C:\vPinball\VPX Achievement Watcher"
    NVRAM_DIR: str = r"C:\vPinball\VisualPinball\VPinMAME\nvram"
    TABLES_DIR: str = r"C:\vPinball\VisualPinball\Tables"
    OVERLAY: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_OVERLAY))
    FIRST_RUN: bool = True
    LOG_CTRL: bool = False
    LOG_SUPPRESS: List[str] = field(default_factory=lambda: list(DEFAULT_LOG_SUPPRESS))
    CLOUD_ENABLED: bool = False
    CLOUD_BACKUP_ENABLED: bool = False
    CLOUD_URL: str = "https://vpx-achievements-watcher-lb-default-rtdb.europe-west1.firebasedatabase.app/"

    ALLOWED_OVERLAY_KEYS = (
        "scale_pct", "background", "portrait_mode", "portrait_rotate_ccw",
        "lines_per_category", "font_family", "overlay_auto_close",
        "pos_x", "pos_y", "use_xy", "overlay_pos_saved",
        "base_body_size", "base_title_size", "base_hint_size",

        "toggle_input_source", "toggle_vk", "toggle_joy_button",
        "challenge_hotkey_input_source", "challenge_hotkey_vk", "challenge_hotkey_joy_button",
        "challenge_left_input_source", "challenge_left_vk", "challenge_left_joy_button",
        "challenge_right_input_source", "challenge_right_vk", "challenge_right_joy_button",

        "ach_toast_custom", "ach_toast_saved", "ach_toast_x_landscape", "ach_toast_y_landscape",
        "ach_toast_x_portrait", "ach_toast_y_portrait", "ach_toast_portrait", "ach_toast_rotate_ccw",

        "ch_timer_custom", "ch_timer_saved", "ch_timer_x_landscape", "ch_timer_y_landscape",
        "ch_timer_x_portrait", "ch_timer_y_portrait", "ch_timer_portrait", "ch_timer_rotate_ccw",

        "ch_ov_custom", "ch_ov_saved", "ch_ov_x_landscape", "ch_ov_y_landscape",
        "ch_ov_x_portrait", "ch_ov_y_portrait", "ch_ov_portrait", "ch_ov_rotate_ccw",

        "flip_counter_custom", "flip_counter_saved", "flip_counter_x_landscape", "flip_counter_y_landscape",
        "flip_counter_x_portrait", "flip_counter_y_portrait", "flip_counter_portrait", "flip_counter_rotate_ccw",

        "heat_bar_custom", "heat_bar_saved", "heat_bar_x_landscape", "heat_bar_y_landscape",
        "heat_bar_x_portrait", "heat_bar_y_portrait", "heat_bar_portrait", "heat_bar_rotate_ccw",

        "notifications_portrait", "notifications_rotate_ccw", "notifications_saved",
        "notifications_x_landscape", "notifications_y_landscape", "notifications_x_portrait", "notifications_y_portrait",

        "status_overlay_enabled", "status_overlay_portrait", "status_overlay_rotate_ccw",
        "status_overlay_saved", "status_overlay_x_landscape", "status_overlay_y_landscape",
        "status_overlay_x_portrait", "status_overlay_y_portrait",

        "player_name", "player_id", "flip_counter_goal_total",
        "challenges_voice_volume", "challenges_voice_mute",
        "low_performance_mode",
        "anim_main_transitions", "anim_main_glow", "anim_main_score_progress",
        "anim_main_highlights", "anim_toast", "anim_status", "anim_challenge",
    )

    @staticmethod
    def load(path: str = CONFIG_FILE) -> "AppConfig":
        if not os.path.exists(path):
            return AppConfig(FIRST_RUN=True)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            ov = dict(DEFAULT_OVERLAY)
            loaded_ov = data.get("OVERLAY", {})
            
            allowed_keys = AppConfig.ALLOWED_OVERLAY_KEYS
            
            for k in list(loaded_ov.keys()):
                if k not in allowed_keys:
                    del loaded_ov[k]
                    
            ov.update(loaded_ov)

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
                CLOUD_ENABLED=cloud_enabled,
                CLOUD_BACKUP_ENABLED=cloud_backup_enabled,
            )
        except Exception as e:
            print(f"[LOAD ERROR] {e}")
            return AppConfig(FIRST_RUN=True)

    def save(self, path: str = CONFIG_FILE) -> None:
        try:
            clean_overlay = {}
            ov = getattr(self, "OVERLAY", {})
            allowed_keys = AppConfig.ALLOWED_OVERLAY_KEYS
            
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
                "OVERLAY": clean_overlay
            }
            
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
                
            with open(path, "w", encoding="utf-8") as f:
                json.dump(to_dump, f, indent=2)
        except Exception as e:
            print(f"CRITICAL ERROR: Could not save config.json -> {e}")
