from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class Bridge(QObject):
    overlay_trigger = pyqtSignal()
    overlay_show = pyqtSignal()
    mini_info_show = pyqtSignal(str, int)
    ach_toast_show = pyqtSignal(str, str, int)
    challenge_timer_start = pyqtSignal(int)
    challenge_timer_stop = pyqtSignal()
    challenge_warmup_show = pyqtSignal(int, str)
    challenge_info_show = pyqtSignal(str, int, str)
    challenge_speak = pyqtSignal(str)
    achievements_updated = pyqtSignal()
    flip_counter_total_show = pyqtSignal(int, int, int)  
    flip_counter_total_update = pyqtSignal(int, int, int)
    flip_counter_total_hide = pyqtSignal()
    heat_bar_show = pyqtSignal()
    heat_bar_update = pyqtSignal(int)
    heat_bar_hide = pyqtSignal()
    
    prefetch_started = pyqtSignal()
    prefetch_progress = pyqtSignal(str)
    prefetch_finished = pyqtSignal(str)
    level_up_show = pyqtSignal(str, int)   # (level_name, level_number)
    status_overlay_show = pyqtSignal(str, int, str)  # (message, seconds, color_hex)
