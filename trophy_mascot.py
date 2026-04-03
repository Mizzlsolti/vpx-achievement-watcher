"""trophy_mascot.py — Trophie mascot companion for VPX Achievement Watcher.

Two instances:
  - GUITrophie  : bottom-left corner of the MainWindow central widget
  - OverlayTrophie : standalone always-on-top desktop widget (draggable)

Both share _TrophieMemory (persisted to <BASE>/trophie_memory.json) and the
_TROPHIE_SHARED coordination dict used for the "zank" (bickering) system.
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import (
    QPoint, QRect, QRectF, QSize, Qt, QTimer,
)
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient, QTransform,
)
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMenu, QSizePolicy,
    QVBoxLayout, QWidget,
)

# ---------------------------------------------------------------------------
# Shared state — used for zank (bickering) coordination
# ---------------------------------------------------------------------------
_TROPHIE_SHARED: dict = {
    "gui_visible": False,
    "zank_cooldown_ms": 0,
    "idle_bicker_cooldown_ms": 0,
    "last_gui_comment_key": None,
    "last_overlay_comment_key": None,
    "zank_pending_overlay": None,
    "zank_pending_gui": None,
    "idle_bicker_ov_key": None,
    "idle_bicker_ov_text": None,
}

# ---------------------------------------------------------------------------
# Cooldown constants (milliseconds)
# ---------------------------------------------------------------------------
# How long before another event-triggered zank exchange can fire.
_ZANK_COOLDOWN_MS = 2 * 60 * 1_000          # 2 minutes
# Cooldowns between spontaneous idle bicker exchanges.
_IDLE_BICKER_MIN_COOLDOWN_MS = 3 * 60 * 1_000  # 3 minutes (when GUI is not open)
_IDLE_BICKER_MAX_COOLDOWN_MS = 5 * 60 * 1_000  # 5 minutes (when GUI is not open)
# Shorter cooldowns when both characters are visible (GUI is open)
_IDLE_BICKER_MIN_COOLDOWN_GUI_MS = 30 * 1_000   # 30 seconds
_IDLE_BICKER_MAX_COOLDOWN_GUI_MS = 45 * 1_000   # 45 seconds

# ---------------------------------------------------------------------------
# Animation state constants
# ---------------------------------------------------------------------------
IDLE = "idle"
TALKING = "talking"
HAPPY = "happy"
SAD = "sad"
SLEEPY = "sleepy"
SURPRISED = "surprised"
DISMISSING = "dismissing"

# ---------------------------------------------------------------------------
# Zank pair table  (trigger -> (gui_line_key, overlay_line_key))
# ---------------------------------------------------------------------------
_ZANK_PAIRS: list[tuple[str, str, str]] = [
    # (trigger_key, gui_key, overlay_key)
    ("achievement", "zank_gui_predicted",    "zank_ov_saw_it"),
    ("game_over",   "zank_gui_no_talk",      "zank_ov_happens"),
    ("challenge_win", "zank_gui_training",   "zank_ov_cheering"),
    ("challenge_lose", "zank_gui_stats",     "zank_ov_not_my_fault"),
    ("idle_30m",    "zank_gui_come_back",    "zank_ov_left_us"),
    ("heat_100",    "zank_gui_calculated",   "zank_ov_told_them"),
    ("level_up",    "zank_gui_guidance",     "zank_ov_witnessed"),
    ("session_5h",  "zank_gui_hydration",    "zank_ov_legend"),
    ("christmas",   "zank_gui_family",       "zank_ov_xmas"),
]

_ZANK_GUI_LINES: dict[str, list[str]] = {
    "zank_gui_predicted": [
        "I predicted that!",
        "Called it! No surprise there.",
        "My algorithm said this would happen. As always.",
        "Told you so. You are welcome.",
        "Some of us plan ahead. Just saying.",
    ],
    "zank_gui_no_talk": [
        "We do not talk about this...",
        "Let us just... move on. Quietly.",
        "This never happened. Agreed? Agreed.",
        "I am choosing not to remember this.",
        "Statistical anomaly. Moving on.",
    ],
    "zank_gui_training": [
        "I knew you could do it! My training worked!",
        "All that coaching paid off! You are welcome!",
        "That is the result of my expert guidance!",
        "I prepared you for this moment!",
        "My mentorship programme is clearly working.",
    ],
    "zank_gui_stats": [
        "Statistically this was likely...",
        "The probability charts predicted this outcome.",
        "My data model said this might happen. It did.",
        "Not ideal, but the numbers do not lie.",
        "Failure rate is within acceptable parameters.",
    ],
    "zank_gui_come_back": [
        "Where did you go? Come back!",
        "Hello? I have been waiting here for ages!",
        "It is very quiet without you. Come back!",
        "I did not sign up to be furniture!",
        "The achievements miss you. So do I. Not that I care.",
    ],
    "zank_gui_calculated": [
        "I calculated this would happen!",
        "The math does not lie — this was inevitable.",
        "My heat forecast was accurate to the degree.",
        "Simulation complete. Result: expected.",
        "Another data point confirming my model.",
    ],
    "zank_gui_guidance": [
        "My guidance paid off!",
        "You levelled up because of my expert tips!",
        "That is what listening to me gets you!",
        "Level achieved! I take full credit.",
        "Growth. I taught you that.",
    ],
    "zank_gui_hydration": [
        "Hydration reminder #47...",
        "Five hours. Please drink something.",
        "Water exists. You should try it.",
        "Your achievement score is rising. Your hydration is not.",
        "Marathon session. Hydration protocol: ACTIVATE.",
    ],
    "zank_gui_family": [
        "Statistically you should be with family...",
        "Christmas Day. Pinball. You chose this.",
        "The data suggests family gatherings exist for a reason.",
        "Holiday detected. Unusual activity logged.",
        "Festive season. Flippers active. Interesting.",
    ],
}

_ZANK_OVERLAY_LINES: dict[str, list[str]] = {
    "zank_ov_saw_it": [
        "I SAW IT HAPPEN! I was there!",
        "WITNESSED! I have proof!",
        "I saw everything from out here! Every single flip!",
        "Front row seat! That was INCREDIBLE!",
        "History happened and I was present for it!",
    ],
    "zank_ov_happens": [
        "It happens to everyone! ...right?",
        "Hey, even legends have bad days!",
        "Nobody saw that. Except me. But I will forget.",
        "Completely normal. Happens all the time. Probably.",
        "The table was cheating. Definitely the table.",
    ],
    "zank_ov_cheering": [
        "MY cheering definitely helped!",
        "You heard me shouting from here, right?",
        "I gave you good vibes the whole way!",
        "My moral support was essential to that win!",
        "Team effort. Mostly me, but still.",
    ],
    "zank_ov_not_my_fault": [
        "NOT MY FAULT!",
        "I was rooting for you! The table let us down!",
        "My positive energy was clearly not enough!",
        "Do NOT look at me for this one!",
        "I had nothing to do with that. Nothing.",
    ],
    "zank_ov_left_us": [
        "...they left us both!",
        "Hello?! We are still here you know!",
        "Abandoned. Both of us. Together in loneliness.",
        "I waited. GUI waited. Nobody came.",
        "The screen is dark. The silence is deafening.",
    ],
    "zank_ov_told_them": [
        "I TOLD THEM! Nobody listens!",
        "Maximum heat! I called this twenty minutes ago!",
        "Did they hear my warnings? NO. Did it matter? YES.",
        "I was screaming from the desktop! Could they hear me? No!",
        "I said SLOW DOWN and yet here we are.",
    ],
    "zank_ov_witnessed": [
        "I WITNESSED HISTORY!",
        "I was HERE for this LEGENDARY moment!",
        "Future generations will hear about this level up!",
        "My desktop view gave me the perfect angle on greatness!",
        "HISTORICAL! I am honoured to have been present!",
    ],
    "zank_ov_legend": [
        "LEGEND STATUS ACHIEVED!",
        "FIVE HOURS! YOU ARE UNSTOPPABLE!",
        "The stuff of LEGENDS! I am speechless! Almost!",
        "This session will be in the history books!",
        "FIVE HOURS AND COUNTING! PLEASE ALSO EAT SOMETHING!",
    ],
    "zank_ov_xmas": [
        "CHRISTMAS PINBALL! NO REGRETS!",
        "FESTIVE FLIPPING! This is the best holiday!",
        "Santa would be proud. Genuinely.",
        "Holiday season and the flippers are HOT!",
        "Christmas achievement hunting! A new tradition!",
    ],
}

# ---------------------------------------------------------------------------
# Spontaneous idle bicker exchanges — fired when both trophies are visible
# Each entry: ((gui_key, gui_text), (ov_key, ov_text))
# GUI fires its line first; Overlay responds 2 seconds later.
# ---------------------------------------------------------------------------
_IDLE_BICKER_EXCHANGES: list[tuple[tuple[str, str], tuple[str, str]]] = [
    (("ibk1_gui", "Steely... are you even paying attention out there?"),
     ("ibk1_ov",  "Unlike YOU, I see the whole screen. Every pixel.")),
    (("ibk2_gui", "I do the important work. Just so you know."),
     ("ibk2_ov",  "Important work? I am literally on the DESKTOP. I am everywhere.")),
    (("ibk3_gui", "Steely really needs to calm down sometimes."),
     ("ibk3_ov",  "CALM DOWN? You are the one hiding inside a window!")),
    (("ibk4_gui", "I gave better tips today. Objectively."),
     ("ibk4_ov",  "I cheered louder. That counts more. Science.")),
    (("ibk5_gui", "Between us? My speech bubbles are more elegant."),
     ("ibk5_ov",  "Mine are BIGGER. Bigger is better. Everyone knows.")),
    (("ibk6_gui", "I work in a controlled indoor environment. Very professional."),
     ("ibk6_ov",  "I brave the open desktop every single day. Do you know how drafty it is?")),
    (("ibk7_gui", "My tips are data-driven and carefully researched."),
     ("ibk7_ov",  "Mine come from the heart! That is worth more than data!")),
    (("ibk8_gui", "I wonder if Steely ever takes a day off."),
     ("ibk8_ov",  "Day off? I live on this desktop 24/7. This IS my life.")),
    (("ibk9_gui", "The player seems to be ignoring both of us today."),
     ("ibk9_ov",  "At least they can still SEE me. I am literally floating here.")),
    (("ibk10_gui", "If I had to pick one of us who is more useful... it would be me."),
     ("ibk10_ov",  "Interesting! You chose wrong! It is me! Obviously!")),
    (("ibk11_gui", "Do you ever get tired of being outside all the time?"),
     ("ibk11_ov",  "Do YOU ever get tired of being stuck in a tab?")),
    (("ibk12_gui", "I track stats. I give tips. I am basically a personal assistant."),
     ("ibk12_ov",  "I celebrate EVERY achievement in REAL TIME. Beat that.")),
    (("ibk13_gui", "Nice mustache, Steely... did a caterpillar land on your face?"),
     ("ibk13_ov",  "At least I HAVE a distinguishing feature. You are just... gold.")),
    (("ibk14_gui", "I am clearly the player's favourite. Look — they click on ME!"),
     ("ibk14_ov",  "They LOOK at me. All the time. I am unavoidable.")),
    (("ibk15_gui", "I do the real work. You just float around looking smug."),
     ("ibk15_ov",  "Without me there is no celebration! I AM the hype!")),
    (("ibk16_gui", "You are so round you could roll off the screen."),
     ("ibk16_ov",  "At least I am not stuck on a pedestal like a museum piece!")),
    (("ibk17_gui", "I have been a trophy for ages. Timeless. Classic."),
     ("ibk17_ov",  "I am a PINBALL. Born to roll. You are just... decorative.")),
    (("ibk18_gui", "My gold colour is very prestigious, you know."),
     ("ibk18_ov",  "My chrome finish is literally more shiny. Facts.")),
    (("ibk19_gui", "Don't tilt, Steely. You always overreact."),
     ("ibk19_ov",  "TILT? ME? I have never tilted in my life!")),
    (("ibk20_gui", "I am having a perfectly productive day, thank you."),
     ("ibk20_ov",  "I am having a BALL today! Literally! Get it?")),
    (("ibk21_gui", "You know, Steely, sometimes less is more."),
     ("ibk21_ov",  "You are on a roll... wait, that is ME. I am on a roll!")),
    (("ibk22_gui", "I track every stat. I never miss a thing."),
     ("ibk22_ov",  "I SEE everything from out here. EVERYTHING.")),
    (("ibk23_gui", "The player has been playing for hours. They need hydration."),
     ("ibk23_ov",  "I already told them! Nobody ever listens to the ball!")),
    (("ibk24_gui", "You know what, Steely? You are not so bad. For a ball."),
     ("ibk24_ov",  "Careful, Trophie. That almost sounded like a compliment.")),
    (("ibk25_gui", "I give advice. You give noise. We make a great team."),
     ("ibk25_ov",  "The BEST team. Even if one of us is shinier than the other.")),
    (("ibk26_gui", "Sometimes I think the player prefers you. It bothers me slightly."),
     ("ibk26_ov",  "Only slightly? Come on, Trophie. Admit it. I am irresistible.")),
    (("ibk27_gui", "Your mustache is very... dramatic."),
     ("ibk27_ov",  "Thank you! I grew it myself. Do NOT touch it.")),
    (("ibk28_gui", "I am the symbol of achievement. Respect that."),
     ("ibk28_ov",  "I am the reason achievements exist! Someone has to play the game!")),
    (("ibk29_gui", "You should come inside sometime. Get out of the elements."),
     ("ibk29_ov",  "And give up the freedom of the desktop? Never.")),
    (("ibk30_gui", "We should work together more. United front."),
     ("ibk30_ov",  "Agreed. But I am still the better looking one. Just for the record.")),
]

# ---------------------------------------------------------------------------
# GUI Trophie tips
# ---------------------------------------------------------------------------
_GUI_TIPS: dict[str, list[tuple[str, str]]] = {
    # (key, text)
    "tab_dashboard": [
        ("dash_notif",    "Check the notification feed — it shows everything that happened last game!"),
        ("dash_restart",  "You can restart the watcher engine here if something seems stuck."),
        ("dash_sessions", "Your session history shows your best gaming streaks — watch them grow!"),
        ("dash_stats",    "The dashboard tracks your all-time trophy count. Keep it climbing!"),
        ("dash_export",   "Tip: you can scroll the notification feed to see older events too!"),
        ("dash_streak",   "Consecutive gaming sessions build your streak — don't break the chain!"),
        ("dash_history",  "Every session is a chance to beat your personal record. Go for it!"),
        ("dash_pinball",  "The ball never lies — your stats tell the whole story of your pinball journey!"),
    ],
    "tab_effects": [
        ("eff_lowperf",   "Too many effects active? Enable Low Performance Mode to save CPU!"),
        ("eff_bloom_scan","Bloom + Scanlines together = perfect arcade look!"),
        ("eff_opengl",    "Post-Processing effects require OpenGL to look their best!"),
        ("eff_grain",     "Film Grain + Scanlines = retro CRT monitor feeling!"),
        ("eff_particle",  "Particle effects add that extra pop to every unlock — try them!"),
        ("eff_confetti",  "Confetti shower on every achievement unlock? Yes please!"),
        ("eff_shockwave", "The shockwave ripple effect makes every unlock feel like a real event!"),
        ("eff_godrays",   "God-Ray Burst makes rare achievements feel truly legendary!"),
    ],
    "tab_appearance": [
        ("app_synthwave", "Try the Synthwave theme — it looks amazing with Bloom enabled!"),
        ("app_place",     "You can position each overlay independently — try the Place buttons!"),
        ("app_portrait",  "Portrait mode rotates the overlay for cabinet screens!"),
        ("app_font",      "Bigger font sizes work great on a real arcade cabinet — try it!"),
        ("app_color",     "Customize the overlay accent colour to match your room's lighting!"),
        ("app_theme",     "The right theme can make your achievements look even more impressive!"),
        ("app_sound",     "Unlock sounds make achievements feel real — don't forget to enable them!"),
        ("app_dark",      "Dark themes are easier on the eyes during late-night pinball sessions!"),
    ],
    "tab_overlay": [
        ("ov_place",      "Position the overlay exactly where you want it — even on a cabinet screen!"),
        ("ov_portrait",   "Portrait mode is perfect for vertical cabinet displays!"),
        ("ov_size",       "Adjust overlay font size to match your screen distance and resolution!"),
        ("ov_accent",     "The accent colour ties the whole overlay together — make it yours!"),
        ("ov_toast",      "The achievement toast tells you exactly what you unlocked and when!"),
        ("ov_timer",      "Challenge timer overlay keeps the pressure on — just how pinball should be!"),
        ("ov_layout",     "Try different overlay layouts to find what works best for your setup!"),
        ("ov_transparent","A transparent overlay blends perfectly without blocking the playfield!"),
    ],
    "tab_theme": [
        ("theme_pick",    "Your theme, your style — pinball should look as good as it plays!"),
        ("theme_neon",    "Neon themes look incredible on dark arcade cabinet screens!"),
        ("theme_gold",    "Gold accents give your achievements a legendary championship feel!"),
        ("theme_match",   "Match your overlay theme to your favourite pinball table aesthetic!"),
        ("theme_update",  "New themes get added with updates — keep an eye out for new styles!"),
        ("theme_blend",   "A consistent theme across all overlays creates an immersive experience!"),
        ("theme_classic", "Classic themes are timeless — sometimes simple is the most powerful!"),
    ],
    "tab_sound": [
        ("snd_enable",    "Achievement sounds make every unlock feel like a true pinball victory!"),
        ("snd_volume",    "Adjust sound volume so it fits perfectly with your VPX audio setup!"),
        ("snd_custom",    "Custom unlock sounds can match the theme of your favourite tables!"),
        ("snd_fanfare",   "A great fanfare makes rare achievements feel truly special!"),
        ("snd_ambient",   "Subtle sounds keep you aware of progress without breaking immersion!"),
        ("snd_level",     "Level-up sounds deserve to be louder — you earned that celebration!"),
        ("snd_mute",      "You can mute sounds during stream sessions without losing visual effects!"),
    ],
    "tab_controls": [
        ("ctrl_joy",      "You can bind a joystick button instead of keyboard to toggle the overlay!"),
        ("ctrl_hotkey",   None),  # dynamic tip — built at runtime
        ("ctrl_overlay",  "The overlay toggle key works even while VPX is running — very handy!"),
        ("ctrl_remap",    "Changed your button layout? Re-bind your overlay toggle here!"),
        ("ctrl_gamepad",  "Gamepad users: almost any button can be assigned as the overlay toggle!"),
        ("ctrl_shortcut", "Quick hotkey access means you never miss an achievement notification!"),
        ("ctrl_toggle",   "Toggle the overlay mid-game to check your progress without pausing!"),
        ("ctrl_cabinet",  "Cabinet players: map the overlay toggle to a flipper button for easy access!"),
    ],
    "tab_progress": [
        ("prog_tab",      "The Progress tab shows how close you are to every achievement!"),
        ("prog_click",    "Click any achievement to see its unlock rules!"),
        ("prog_filter",   "Filter achievements by status to focus only on what is still locked!"),
        ("prog_percent",  "Completion percentage is tracked per table — can you reach 100%?"),
        ("prog_sort",     "Sort your achievements by unlock date to relive your greatest moments!"),
        ("prog_hunt",     "Achievement hunting is a marathon, not a sprint — enjoy the journey!"),
        ("prog_rare",     "Some achievements require hundreds of games — the rarest are the best!"),
        ("prog_milestone","Every 10% completion milestone is worth celebrating. You are making progress!"),
    ],
    "tab_cloud": [
        ("cloud_backup",  "Back up your achievements to the cloud — do not lose your progress!"),
        ("cloud_id",      "Your Player ID is your identity. Write it down somewhere safe!"),
        ("cloud_sync",    "Cloud Sync runs automatically in the background — always protected!"),
        ("cloud_leader",  "Check the online leaderboard to see how you rank globally!"),
        ("cloud_compete", "Compete with players worldwide — pinball skill is a global language!"),
        ("cloud_safe",    "Your pinball legacy is safe in the cloud — every flip, every unlock!"),
        ("cloud_rank",    "Climb the global rankings one achievement at a time — every unlock counts!"),
    ],
    "tab_system": [
        ("sys_nvram",     "Use Force Cache NVRAM Maps if a new table is not being tracked!"),
        ("sys_name",      "You can change your display name here — it shows on the cloud leaderboard!"),
        ("sys_logs",      "Check the system log if something is not tracking correctly!"),
        ("sys_paths",     "Verify your NVRAM and ROM paths here if tables are not being detected!"),
        ("sys_update",    "Keep VPX Achievement Watcher updated for the latest table support!"),
        ("sys_cache",     "Clear the NVRAM cache if a table starts acting strange — fresh start!"),
        ("sys_backup",    "Regular system backups mean you never lose hard-earned achievements!"),
        ("sys_perf",      "Check performance settings if your system runs hot during long sessions!"),
    ],
    "tab_general": [
        ("gen_profile",   "Set up your player profile to personalise your achievement journey!"),
        ("gen_name",      "Your display name is how the world sees your pinball legacy!"),
        ("gen_language",  "Adjust language and locale settings for the best experience!"),
        ("gen_startup",   "Configure startup behaviour so VPX Achievement Watcher is always ready!"),
        ("gen_paths",     "Correct ROM and NVRAM paths are the foundation of perfect tracking!"),
        ("gen_check",     "Run the system check to make sure everything is working perfectly!"),
        ("gen_support",   "Check the logs first if something seems wrong — the answer is usually there!"),
    ],
    "tab_maintenance": [
        ("maint_clean",   "Occasional cache clearing keeps the watcher running at peak performance!"),
        ("maint_rebuild", "Rebuilding the achievement index fixes most tracking problems instantly!"),
        ("maint_backup",  "Always back up before performing maintenance — better safe than sorry!"),
        ("maint_update",  "Keeping maps up to date means new tables are tracked immediately!"),
        ("maint_logs",    "Maintenance logs are your best friend when troubleshooting tricky tables!"),
        ("maint_nvram",   "Force-refreshing NVRAM maps helps if a newly installed table is not detected!"),
        ("maint_reset",   "A clean reset can solve mystery bugs — and your achievements are cloud-safe!"),
    ],
    "tab_player": [
        ("player_id",     "Your Player ID is unique to you — protect it like a high score!"),
        ("player_name",   "Choose a name that represents your pinball legacy — make it memorable!"),
        ("player_stats",  "Your personal stats track every flip and every win — it is all yours!"),
        ("player_rank",   "Every achievement moves you up the global rankings. Keep pushing!"),
        ("player_history","Your play history is a testament to your dedication. Wear it proudly!"),
        ("player_profile","A complete player profile makes your achievements shine on the leaderboard!"),
        ("player_cloud",  "Link your cloud account to protect every achievement you have ever earned!"),
    ],
    "tab_records": [
        ("rec_global",    "Global records show you the best pinball players in the world!"),
        ("rec_compare",   "Compare your scores with other players — pinball is always better together!"),
        ("rec_session",   "Session delta records show your improvement over time — progress is real!"),
        ("rec_personal",  "Personal records are the benchmarks you set for yourself. Smash them!"),
        ("rec_challenge", "Challenge leaderboards are where pinball legends are made!"),
        ("rec_rank",      "Your current global rank is just the beginning of the climb!"),
        ("rec_history",   "Historical records prove that every session made you a better player!"),
    ],
    "tab_aweditor": [
        ("aw_custom",     "AWEditor lets you create custom achievements for any table you love!"),
        ("aw_trigger",    "Custom trigger files let you unlock achievements from any in-game event!"),
        ("aw_script",     "Export the full VPX script to create the most accurate custom rules!"),
        ("aw_share",      "Share your custom achievement packs with the community!"),
        ("aw_creative",   "The best custom achievements make you think differently about a table!"),
        ("aw_test",       "Test your custom achievements thoroughly — every edge case matters!"),
        ("aw_rules",      "Well-crafted achievement rules reward skill, creativity, and persistence!"),
    ],
    "tab_maps": [
        ("maps_browse",   "Browse the Available Maps list to see which tables have NVRAM tracking!"),
        ("maps_filter",   "Filter to local tables only to focus on what you actually have installed!"),
        ("maps_vps",      "The VPS-ID column links tables to the Virtual Pinball Spreadsheet database!"),
        ("maps_refresh",  "Hit Refresh if you just installed a new table — it should appear in the list!"),
        ("maps_nvram",    "Tables with NVRAM maps can track achievements automatically while you play!"),
        ("maps_local",    "Local tables with an NVRAM map are the ones the watcher monitors in real time!"),
        ("maps_author",   "Achievement map authors put a lot of work in — give them a round of applause!"),
        ("maps_missing",  "Missing a map for your favourite table? Check for updates or request one!"),
    ],
    "tab_mascots": [
        ("mascots_intro",   "Dress me up! Pick a skin from the gallery and hit Apply Skin to see the change!"),
        ("mascots_preview", "Click any skin card to preview it live before applying — I will model it for you!"),
        ("mascots_steely",  "Steely has 22 skins too! Give him a disco ball or a galaxy pattern for variety!"),
        ("mascots_apply",   "Applied skins are remembered even after you restart the watcher!"),
        ("mascots_hide",    "Not a fan of mascots? You can hide Trophie or Steely with the checkboxes above!"),
    ],
}

_GUI_EVENT_TIPS: list[tuple[str, str]] = [
    ("evt_first_ach",    "Your first achievement! The hunt begins!"),
    ("evt_ach_unlocked", "Achievement unlocked! You are on your way!"),
    ("evt_lowperf_on",   "Good call! Low Performance Mode saves a lot of CPU."),
    ("evt_new_theme",    "Nice theme choice! Try enabling Bloom for the full effect!"),
    ("evt_postproc_on",  "Post-Processing is on! Looks amazing, right?"),
    ("evt_bloom_grain",  "Careful — Bloom + Film Grain together can be heavy on older PCs!"),
    ("evt_cloud_on",     "Cloud Sync is on! Your achievements are safe now."),
]

_GUI_IDLE_TIPS: list[tuple[str, str]] = [
    ("idle_5m",  "Still there? I am here if you need help!"),
    ("idle_10m", "ZZZ..."),  # enters SLEEPY
]

_GUI_RANDOM: list[tuple[str, str]] = [
    ("rnd_track",    "Did you know? I track everything you do... in a good way!"),
    ("rnd_believe",  "I believe in you. Just saying."),
    ("rnd_art",      "Achievement hunting is an art form. You are an artist!"),
    ("rnd_great",    "Between us? You are doing great!"),
    ("rnd_pixels",   "Fun fact: I am made of pixels but I feel real emotions!"),
    ("rnd_watch",    "I do not sleep. I just watch. Always watching."),
    ("rnd_luck",     "Some say pinball is luck. Those people have not seen you!"),
]

_GUI_ZANK: list[tuple[str, str]] = [
    ("z_gui_weird",   "Steely just said something weird again..."),
    ("z_gui_smart",   "Do not listen to Steely. I am the smart one!"),
    ("z_gui_filter",  "Steely has NO filter. Sorry about that!"),
    ("z_gui_toomuch", "Between us? Steely talks WAY too much!"),
    ("z_gui_unprof",  "Steely just said something unprofessional. Embarrassing!"),
    ("z_gui_moving",  "We do not talk about Steely. Moving on!"),
    ("z_gui_real",    "I do the REAL work here. Steely just watches!"),
    ("z_gui_twin",    "Steely thinks it is funny. It is not. I am the serious one!"),
    ("z_gui_first",   "I told you before Steely did. Just saying!"),
    ("z_gui_loud",    "Steely is being VERY loud today. Apologies."),
    ("z_gui_shouting","Did you hear that? Yes. That was Steely. Again."),
    ("z_gui_drama",   "Steely is being dramatic. As usual."),
    ("z_gui_credit",  "Steely is trying to take credit again. Classic."),
    ("z_gui_expert",  "I have a certification. Steely does not. Just so you know."),
    ("z_gui_envy",    "Sure, Steely floats around looking fancy. I actually HELP."),
]

# ---------------------------------------------------------------------------
# Overlay Trophie comments
# ---------------------------------------------------------------------------
_OV_ROM_START: list[tuple[str, str]] = [
    ("ov_go",          "Let's go! Good luck!"),
    ("ov_classic",     None),  # dynamic: "Oh! {table_name}! Classic!"
    ("ov_firsttime",   "First time on this table! Good luck!"),
    ("ov_longago",     "Haven't seen this one in a while!"),
    ("ov_fav",         "Your favourite again? No complaints!"),
    ("ov_revenge",     "Back for more revenge? I respect that!"),
    ("ov_dustoff",     "Long time no see! Dust off those flippers!"),
    ("ov_thirdtoday",  "Third table today! You are on a roll!"),
    ("ov_firstday",    "First game of the day! Let's make it count!"),
    ("ov_onemore",     "One more game? That is the spirit!"),
    ("ov_morning",     "Morning warm-up! Coffee + pinball!"),
    ("ov_evening",     "Evening session! The best time to play!"),
    ("ov_nightowl",    "Night owl mode activated!"),
    ("ov_monday",      "Monday motivation: pinball!"),
    ("ov_weekend",     "Weekend pinball! No alarms tomorrow!"),
]

_OV_SESSION_END: list[tuple[str, str]] = [
    ("ov_good_game",   "Good game! See you next round"),
    ("ov_got_one",     "NICE! You got one!"),
    ("ov_double",      "Double unlock! Efficient!"),
    ("ov_avalanche",   "Achievement AVALANCHE! How?!"),
    ("ov_levelup",     "LEVEL UP! You are on fire!"),
    ("ov_almostach",   "Not every game needs a trophy. Almost!"),
    ("ov_shortsweet",  "Short but sweet! Every game counts!"),
    ("ov_2h",          "2 hours in... You okay?"),
    ("ov_3h",          "3 hours?! You are a machine!"),
    ("ov_5h",          "5 hours... Please drink some water!"),
    ("ov_drought_over","FINALLY! The drought is over!"),
    ("ov_rare_ach",    "That one is RARE! Show it off!"),
    ("ov_grind",       "Long session, no achievements... The grind is real!"),
    ("ov_tilt",        "Tilt? Or just bad luck?"),
    ("ov_first_blood", "First blood! The hunt is on!"),
    ("ov_5today",      "5 achievements today! Beast mode!"),
    ("ov_dry_spell",   "Dry spell... but legends never quit!"),
    ("ov_midnight",    "Midnight finish! Legendary!"),
]

_OV_CHALLENGE: list[tuple[str, str]] = [
    ("ov_ch_accepted",   "Challenge accepted! Do not choke!"),
    ("ov_ch_clock",      "Clock is ticking! FOCUS!"),
    ("ov_ch_10s",        "10 SECONDS! GIVE IT EVERYTHING!"),
    ("ov_ch_win",        "YOU WIN! I knew you could do it!"),
    ("ov_ch_close",      "So close... Try again!"),
    ("ov_ch_heartattack","THAT WAS CLOSE! Heart attack!"),
    ("ov_ch_dominant",   "Dominant performance!"),
    ("ov_ch_third",      "Third time is the charm... right?"),
    ("ov_ch_notmyfault", "NOT MY FAULT!"),
    ("ov_ch_record",     "NEW CHALLENGE RECORD! History made!"),
    ("ov_ch_back",       "Back in the challenge ring!"),
    ("ov_ch_5today",     "5 challenges today! Competitor of the year!"),
    ("ov_ch_morning",    "Morning challenge! Warm those fingers up!"),
    ("ov_ch_1sec",       "1 second away... I felt that"),
]

_OV_HEAT: list[tuple[str, str]] = [
    ("ov_heat_65",    "Getting warm! Ease up a little!"),
    ("ov_heat_85",    "CRITICAL HEAT! Your flippers are burning!"),
    ("ov_heat_100",   "TOO HOT! Give those flippers a rest!"),
    ("ov_heat_cool",  "Cooling down... smart move!"),
    ("ov_heat_zone",  "Steady pace! You are in the zone!"),
]

_OV_FLIP: list[tuple[str, str]] = [
    ("ov_flip_start",  "Flip counter active! Every flip counts!"),
    ("ov_flip_25",     "Quarter way there! Warm up done!"),
    ("ov_flip_50",     "Halfway there! Keep flipping!"),
    ("ov_flip_75",     "75%! Almost there! Do not slow down!"),
    ("ov_flip_90",     "Almost at your goal! Do not stop now!"),
    ("ov_flip_over",   "You SMASHED your goal! Overachiever!"),
    ("ov_flip_goal",   "GOAL! You hit your flip target!"),
]

_OV_IDLE: list[tuple[str, str]] = [
    ("ov_idle_5m",   "Still here... waiting..."),
    ("ov_idle_10m",  "Psst. VPX won't start itself!"),
    ("ov_idle_15m",  "I could really go for a game right now..."),
    ("ov_idle_20m",  "The tables miss you. True story."),
    ("ov_idle_45m",  "At this point I am basically furniture"),
    ("ov_idle_1h",   "One hour idle... Are you okay out there?"),
    ("ov_idle_zzz",  "ZZZ..."),  # SLEEPY state
    ("ov_idle_late", "Go to sleep. The achievements will be here tomorrow!"),
    ("ov_idle_morn", "Good morning! Ready for some pinball?"),
    ("ov_idle_wknd", "It is the weekend and you are NOT playing?!"),
]

_OV_DAYTIME: list[tuple[str, str]] = [
    ("ov_day_mon",  "Monday? Best day for pinball!"),
    ("ov_day_tue",  "Tuesday grind! Underrated pinball day!"),
    ("ov_day_wed",  "Midweek energy! Keep it up!"),
    ("ov_day_thu",  "Thursday already?! Time flies when you are flipping!"),
    ("ov_day_fri",  "Friday night pinball! The best kind!"),
    ("ov_day_sat",  "Perfect Saturday afternoon!"),
    ("ov_day_sun",  "Sunday session! One more before Monday!"),
    ("ov_day_ny",   "Happy New Year! First achievement of the year?"),
    ("ov_day_xmas", "Playing on Christmas?! Dedicated!"),
    ("ov_day_hal",  "Spooky session! BOO!"),
    ("ov_day_3am",  "3am pinball?! Legendary dedication!"),
    ("ov_day_hist", "This session is going in the history books!"),
    ("ov_day_new_month", "New month, new achievements!"),
    ("ov_day_nye",  "Last game of the year? Make it count!"),
]

_OV_RANDOM: list[tuple[str, str]] = [
    ("ov_rnd_pixels",  "Fun fact: I am made of pixels but I feel real emotions!"),
    ("ov_rnd_art",     "Achievement hunting is an art form. You are an artist!"),
    ("ov_rnd_count",   "I have been counting your achievements. Impressive!"),
    ("ov_rnd_best",    "Between us? You are one of the best I have seen!"),
    ("ov_rnd_1000",    "Did you know VPX has over 1000 tables? Try them all!"),
    ("ov_rnd_watch",   "I do not sleep. I just watch. Always watching."),
    ("ov_rnd_luck",    "Some say pinball is luck. Those people have not seen you!"),
    ("ov_rnd_mascot",  "Achievement unlocked: Having an awesome mascot!"),
    ("ov_rnd_boo",     "...boo. Did I scare you?"),
    ("ov_rnd_flippers","If I had flippers I would be amazing at this game. Just saying!"),
    ("ov_rnd_silence", "I am still here by the way"),
    ("ov_rnd_cheat",   "Are you cheating? ...I am not judging"),
    ("ov_rnd_1871",    "Fun fact: The first pinball machine was built in 1871!"),
    ("ov_rnd_believe", "I believe in you. Just saying."),
    ("ov_rnd_combo",   "VPX + achievements = perfect combo"),
    ("ov_rnd_score",   "You know I can see your score right?"),
]

_OV_ZANK: list[tuple[str, str]] = [
    ("z_ov_indoor",    "Trophie is giving you tips again huh? Classic!"),
    ("z_ov_twin",      "Trophie thinks it knows everything. Adorable!"),
    ("z_ov_funone",    "I am the fun one. Trophie is just... there!"),
    ("z_ov_better",    "Do not tell Trophie but... I am the better looking one!"),
    ("z_ov_lecture",   "Trophie is probably lecturing you about settings right now!"),
    ("z_ov_boring",    "Trophie is SO boring. Tips tips tips! I do the real action!"),
    ("z_ov_novideo",   "Between us? Trophie has never seen a real game!"),
    ("z_ov_famous",    "I live on the DESKTOP. I am basically famous!"),
    ("z_ov_woke",      "Trophie just woke up to say hello. Took long enough!"),
    ("z_ov_congrat",   "Did Trophie congratulate you? I did it first!"),
    ("z_ov_tabs",      "Trophie just sits in its cozy little tab. Must be nice!"),
    ("z_ov_exposure",  "I get direct desktop exposure. Trophie gets none. Tragic."),
    ("z_ov_celebrate", "I am the celebration one. Trophie is the lecture one. Facts."),
    ("z_ov_freedom",   "The desktop is my kingdom. Trophie is basically in a box."),
    ("z_ov_relevant",  "You can minimise the window but you cannot minimise ME!"),
]


# ---------------------------------------------------------------------------
# _TrophieMemory — KI learning, persisted to trophie_memory.json
# ---------------------------------------------------------------------------
class _TrophieMemory:
    """Persistent learning memory shared by both Trophie instances."""

    _FILENAME = "trophie_memory.json"

    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, self._FILENAME)
        self.seen_tips: set = set()
        self.tab_visits: dict = {}
        self.play_times: list = []
        self.session_durations: list = []
        self.achievement_sessions: int = 0
        self.no_achievement_sessions: int = 0
        self.challenge_wins: int = 0
        self.challenge_losses: int = 0
        self.heat_100_count: int = 0
        self.rom_play_counts: dict = {}
        self.dismiss_speed: list = []
        self.comments_shown: int = 0
        self.comments_dismissed_fast: int = 0
        self._fast_dismiss_streak: int = 0
        self._told_quiet: bool = False
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.seen_tips = set(d.get("seen_tips", []))
            self.tab_visits = d.get("tab_visits", {})
            self.play_times = d.get("play_times", [])
            self.session_durations = d.get("session_durations", [])
            self.achievement_sessions = int(d.get("achievement_sessions", 0))
            self.no_achievement_sessions = int(d.get("no_achievement_sessions", 0))
            self.challenge_wins = int(d.get("challenge_wins", 0))
            self.challenge_losses = int(d.get("challenge_losses", 0))
            self.heat_100_count = int(d.get("heat_100_count", 0))
            self.rom_play_counts = d.get("rom_play_counts", {})
            self.dismiss_speed = d.get("dismiss_speed", [])
            self.comments_shown = int(d.get("comments_shown", 0))
            self.comments_dismissed_fast = int(d.get("comments_dismissed_fast", 0))
            self._told_quiet = bool(d.get("_told_quiet", False))
        except Exception:
            pass

    def save(self) -> None:
        try:
            d = {
                "seen_tips": list(self.seen_tips),
                "tab_visits": self.tab_visits,
                "play_times": self.play_times[-200:],
                "session_durations": self.session_durations[-200:],
                "achievement_sessions": self.achievement_sessions,
                "no_achievement_sessions": self.no_achievement_sessions,
                "challenge_wins": self.challenge_wins,
                "challenge_losses": self.challenge_losses,
                "heat_100_count": self.heat_100_count,
                "rom_play_counts": self.rom_play_counts,
                "dismiss_speed": self.dismiss_speed[-200:],
                "comments_shown": self.comments_shown,
                "comments_dismissed_fast": self.comments_dismissed_fast,
                "_told_quiet": self._told_quiet,
            }
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            pass

    # ── KI queries ───────────────────────────────────────────────────────────

    def prefers_night(self) -> bool:
        if len(self.play_times) < 5:
            return False
        night = sum(1 for h in self.play_times if h >= 21 or h < 5)
        return night / len(self.play_times) > 0.4

    def avg_session_minutes(self) -> float:
        if not self.session_durations:
            return 30.0
        return sum(self.session_durations) / len(self.session_durations)

    def is_challenge_fan(self) -> bool:
        return (self.challenge_wins + self.challenge_losses) > 10

    def dismisses_quickly(self) -> bool:
        if len(self.dismiss_speed) < 5:
            return False
        fast = sum(1 for ms in self.dismiss_speed[-10:] if ms < 1500)
        return fast >= 5

    def favourite_rom(self) -> Optional[str]:
        if not self.rom_play_counts:
            return None
        return max(self.rom_play_counts, key=lambda r: self.rom_play_counts[r])

    # ── Tip rotation ─────────────────────────────────────────────────────────

    def pick_unseen(self, tips: list[tuple[str, str]]) -> Optional[tuple[str, str]]:
        """Return an unseen tip from the list; resets rotation when all seen."""
        keys = [k for k, _ in tips]
        unseen = [t for t in tips if t[0] not in self.seen_tips]
        if not unseen:
            # All seen — reset and start over
            for k in keys:
                self.seen_tips.discard(k)
            unseen = list(tips)
        if not unseen:
            return None
        chosen = random.choice(unseen)
        self.seen_tips.add(chosen[0])
        return chosen

    # ── Dismiss tracking ─────────────────────────────────────────────────────

    def record_dismiss(self, ms: int) -> Optional[str]:
        """Record a dismissal; returns special message if 3 fast in a row."""
        self.dismiss_speed.append(ms)
        self.comments_shown += 1
        if ms < 1500:
            self.comments_dismissed_fast += 1
            self._fast_dismiss_streak += 1
        else:
            self._fast_dismiss_streak = 0
        if self._fast_dismiss_streak >= 3 and not self._told_quiet:
            self._told_quiet = True
            return "I will be quieter!"
        return None

    def comment_frequency_multiplier(self) -> float:
        if self.dismisses_quickly():
            return 0.5
        return 1.0


# ---------------------------------------------------------------------------
# Action-confirmed Toast (✅ feedback after context-menu actions)
# ---------------------------------------------------------------------------
class _ActionToast(QWidget):
    """Small ✅ toast that fades in, stays ~1 s, then fades out."""

    _BG     = QColor("#1A1A1A")
    _BORDER = QColor("#FF7F00")
    _TEXT   = QColor("#FFFFFF")
    _RADIUS = 8
    _PAD    = 8
    _FADE_MS      = 200
    _VISIBLE_MS   = 1000

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if parent is None:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool,
            )
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        else:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)

        font = QFont("Segoe UI", 11)
        self.setFont(font)
        fm = QFontMetrics(font)
        r  = fm.boundingRect("✅")
        w  = r.width()  + self._PAD * 2
        h  = r.height() + self._PAD * 2
        self.setFixedSize(max(w, 44), max(h, 36))

        self._opacity    = 0.0
        self._fading_out = False

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._on_fade)

        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._begin_fade_out)

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(rect.height()),
            self._RADIUS, self._RADIUS,
        )
        p.fillPath(path, self._BG)
        pen = QPen(self._BORDER, 1.5)
        p.setPen(pen)
        p.drawPath(path)
        p.setPen(self._TEXT)
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "✅")

    # ── animation ─────────────────────────────────────────────────────────────

    def _on_fade(self) -> None:
        step = 16.0 / self._FADE_MS
        if not self._fading_out:
            self._opacity = min(1.0, self._opacity + step)
            if self._opacity >= 1.0:
                self._fade_timer.stop()
                self._hold_timer.start(self._VISIBLE_MS)
        else:
            self._opacity = max(0.0, self._opacity - step)
            if self._opacity <= 0.0:
                self._fade_timer.stop()
                self.hide()
                self.deleteLater()
        self.update()

    def _begin_fade_out(self) -> None:
        self._fading_out = True
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    # ── public show helper ────────────────────────────────────────────────────

    def popup(self, global_pos: QPoint) -> None:
        """Position the toast at global_pos and start the fade-in."""
        if self.parent() is not None:
            local = self.parent().mapFromGlobal(global_pos)
            self.move(local)
        else:
            self.move(global_pos)
        self.raise_()
        self.show()
        self._fade_timer.start()


# ---------------------------------------------------------------------------
# Speech Bubble widget
# ---------------------------------------------------------------------------
class _SpeechBubble(QWidget):
    """Floating speech bubble that auto-dismisses after 4 seconds."""

    _AUTO_DISMISS_MS = 5000
    _FADE_MS = 300
    _BG = QColor("#1A1A1A")
    _BORDER = QColor("#FF7F00")
    _TEXT_COLOR = QColor("#FFFFFF")
    _MAX_W = 240
    _PAD = 12
    _RADIUS = 10
    _PTR_H = 10

    def __init__(self, parent: QWidget, text: str, memory: _TrophieMemory, rotation: int = 0) -> None:
        super().__init__(parent)
        self._memory = memory
        self._text = text
        self._opacity = 0.0
        self._shown_at_ms = int(time.time() * 1000)
        self._rotation = rotation  # 0, 90 or -90 degrees
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)

        # Measure required size
        font = QFont("Segoe UI", 9)
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(
            QRect(0, 0, self._MAX_W - self._PAD * 2, 10000),
            Qt.TextFlag.TextWordWrap,
            text,
        )
        bw = max(120, text_rect.width() + self._PAD * 2 + 30)  # +30 for close button
        bh = text_rect.height() + self._PAD * 2 + self._PTR_H
        # Swap dimensions when rotated so the widget occupies the right layout space
        if self._rotation != 0:
            bw, bh = bh, bw
        self.setFixedSize(bw, bh)

        # Fade-in timer
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._on_fade)
        self._fade_timer.start()

        # Auto-dismiss timer
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._begin_fade_out)
        self._auto_timer.start(self._AUTO_DISMISS_MS)

        self._fading_out = False
        self._ptr_offset = -1
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show()

    def set_pointer_offset(self, offset: int) -> None:
        self._ptr_offset = offset
        self.update()

    def _on_fade(self) -> None:
        step = 16.0 / self._FADE_MS
        if not self._fading_out:
            self._opacity = min(1.0, self._opacity + step)
            if self._opacity >= 1.0:
                self._fade_timer.stop()
        else:
            self._opacity = max(0.0, self._opacity - step)
            if self._opacity <= 0.0:
                self._fade_timer.stop()
                self._do_dismiss()
        self.update()

    def _begin_fade_out(self) -> None:
        self._fading_out = True
        if not self._fade_timer.isActive():
            self._fade_timer.start()

    def _do_dismiss(self) -> None:
        elapsed = int(time.time() * 1000) - self._shown_at_ms
        msg = self._memory.record_dismiss(elapsed)
        self._memory.save()
        owner = getattr(self, '_owner', None) or self.parent()
        if msg:
            # Schedule a brief "quiet" message on parent Trophie after dismissal.
            # _owner is set when the bubble is a top-level window with no Qt parent.
            try:
                owner._schedule_quiet_msg(msg)
            except Exception:
                pass
        # Reset owner animation state to IDLE and clear the stale bubble reference
        if owner:
            try:
                owner._current_bubble = None
                owner._draw.set_state(IDLE)
            except Exception:
                pass
        self.hide()
        self.deleteLater()

    def mousePressEvent(self, event) -> None:
        self._auto_timer.stop()
        self._begin_fade_out()

    def paintEvent(self, event) -> None:
        if self._rotation != 0:
            self._paint_rotated()
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)

        w = self.width()
        h = self.height() - self._PTR_H

        # Background rounded rect
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, self._RADIUS, self._RADIUS)
        p.fillPath(path, self._BG)

        # Border
        pen = QPen(self._BORDER, 2)
        p.setPen(pen)
        p.drawPath(path)

        # Pointer triangle (pointing down, centered)
        tri = QPainterPath()
        cx = self._ptr_offset if self._ptr_offset >= 0 else w // 2
        cx = max(self._RADIUS + 8, min(w - self._RADIUS - 8, cx))
        tri.moveTo(cx - 8, h)
        tri.lineTo(cx + 8, h)
        tri.lineTo(cx, h + self._PTR_H)
        tri.closeSubpath()
        p.fillPath(tri, self._BG)
        p.setPen(QPen(self._BORDER, 1))
        p.drawLine(cx - 8, h, cx, h + self._PTR_H)
        p.drawLine(cx + 8, h, cx, h + self._PTR_H)

        # Close button "x"
        p.setPen(QPen(self._BORDER, 1))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(w - self._PAD - 8, self._PAD + 8, "x")

        # Text
        p.setPen(QPen(self._TEXT_COLOR))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(
            QRect(self._PAD, self._PAD, w - self._PAD * 2 - 14, h - self._PAD * 2),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        p.end()

    def _paint_rotated(self) -> None:
        """Render the bubble content at normal orientation then rotate to paint."""
        # Compute the unrotated dimensions (swap back)
        uw = self.height()
        uh = self.width()
        img = QImage(uw, uh, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        ip = QPainter(img)
        ip.setRenderHint(QPainter.RenderHint.Antialiasing)
        ip.setOpacity(self._opacity)

        bh_content = uh - self._PTR_H
        path = QPainterPath()
        path.addRoundedRect(0, 0, uw, bh_content, self._RADIUS, self._RADIUS)
        ip.fillPath(path, self._BG)
        pen = QPen(self._BORDER, 2)
        ip.setPen(pen)
        ip.drawPath(path)

        tri = QPainterPath()
        cx = self._ptr_offset if self._ptr_offset >= 0 else uw // 2
        cx = max(self._RADIUS + 8, min(uw - self._RADIUS - 8, cx))
        tri.moveTo(cx - 8, bh_content)
        tri.lineTo(cx + 8, bh_content)
        tri.lineTo(cx, bh_content + self._PTR_H)
        tri.closeSubpath()
        ip.fillPath(tri, self._BG)
        ip.setPen(QPen(self._BORDER, 1))
        ip.drawLine(cx - 8, bh_content, cx, bh_content + self._PTR_H)
        ip.drawLine(cx + 8, bh_content, cx, bh_content + self._PTR_H)

        ip.setPen(QPen(self._BORDER, 1))
        ip.setFont(QFont("Segoe UI", 8))
        ip.drawText(uw - self._PAD - 8, self._PAD + 8, "x")

        ip.setPen(QPen(self._TEXT_COLOR))
        ip.setFont(QFont("Segoe UI", 9))
        ip.drawText(
            QRect(self._PAD, self._PAD, uw - self._PAD * 2 - 14, bh_content - self._PAD * 2),
            Qt.TextFlag.TextWordWrap,
            self._text,
        )
        ip.end()

        rotated = img.transformed(QTransform().rotate(self._rotation), Qt.TransformationMode.SmoothTransformation)
        p = QPainter(self)
        try:
            p.drawImage(0, 0, rotated)
        finally:
            p.end()


# ---------------------------------------------------------------------------
# Trophy drawing widget (shared base)
# ---------------------------------------------------------------------------
class _TrophieDrawWidget(QWidget):
    """Draws the animated trophy mascot using QPainter."""

    # Expression pupil offsets (dy relative to eye center)
    _EXPR_PUPIL: dict = {
        IDLE:      (0, 0),
        TALKING:   (0, 0),
        HAPPY:     (0, -3),
        SAD:       (0, 3),
        SLEEPY:    (0, 1),
        SURPRISED: (0, 0),
        DISMISSING:(0, 0),
    }

    # Passive animation modes — cycle through these to keep the trophy lively
    _PASSIVE_MODES = ["float", "spin", "pulse", "shimmer", "wobble", "fade", "bounce", "eye_roll", "stretch", "nod", "sparkle", "yawn"]
    _PASSIVE_MODE_MIN_MS = 8000
    _PASSIVE_MODE_MAX_MS = 20000
    _PASSIVE_MODE_OFFSET_MS = 5000  # max extra random offset so two instances desynchronize
    # Yawn threshold: above this value the mouth is drawn wide open (surprised shape)
    _YAWN_FULL_OPEN_THRESHOLD = 0.7

    def __init__(self, parent: QWidget, trophy_w: int, trophy_h: int) -> None:
        super().__init__(parent)
        self._tw = trophy_w
        self._th = trophy_h
        self.setFixedSize(trophy_w, trophy_h)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Skin
        self._skin: str = "classic"

        # Animation state
        self._state = IDLE
        self._bob_t = 0.0          # time for sine bob (radians)
        self._bob_y = 0.0          # current vertical offset from bob
        self._scale = 1.0          # for grow/shrink animations (dismiss)
        self._opacity_val = 1.0    # for fade-out

        # Blink state
        self._blink = False
        self._blink_timer = QTimer(self)
        self._blink_timer.setSingleShot(True)
        self._blink_timer.timeout.connect(self._do_blink)
        self._schedule_blink()

        # Pupil override
        self._pupil_dx = 0
        self._pupil_dy = 0

        # Eye half-close for sleepy
        self._eye_half = False

        # Jump animation
        self._jump_offset = 0.0
        self._jump_vel = 0.0
        self._jumping = False

        # Dismiss animation
        self._dismiss_cb = None

        # Extended animations
        self._tilt_t = 0.0          # wobble/tilt phase for TALKING state
        self._wiggle_t = 0.0        # rapid horizontal wiggle phase for SURPRISED
        self._squash_t = 0.0        # squash-and-stretch phase (post-jump landing)
        self._squash_active = False  # True while squash/stretch is playing

        # Extra animation state for new passive modes
        self._eye_roll_phase: float = 0.0  # for eye_roll passive mode
        self._yawn_amount: float = 0.0     # 0.0=closed, 1.0=full yawn

        # Subclass-settable passive offsets (used for Steely-specific modes)
        self._passive_extra_x: float = 0.0
        self._passive_extra_y: float = 0.0
        self._passive_angle: float = 0.0

        # Passive animation mode — cycles through variety animations independently
        # of the emotion state to keep the trophy visually interesting.
        self._passive_mode: str = random.choice(self._PASSIVE_MODES)
        self._passive_t: float = 0.0      # phase timer within current passive mode
        self._passive_mode_timer = QTimer(self)
        self._passive_mode_timer.timeout.connect(self._cycle_passive_mode)
        # Add random initial offset so two instances don't sync up
        initial_delay = random.randint(self._PASSIVE_MODE_MIN_MS, self._PASSIVE_MODE_MAX_MS) + random.randint(0, self._PASSIVE_MODE_OFFSET_MS)
        self._passive_mode_timer.start(initial_delay)

        # Main animation tick
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(16)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    def add_tick_listener(self, callback) -> None:
        """Register an additional callback to fire on every animation tick."""
        self._tick_timer.timeout.connect(callback)

    def set_skin(self, skin_id: str) -> None:
        """Apply a visual skin to the mascot drawing widget."""
        self._skin = skin_id
        self.update()

    def _schedule_blink(self) -> None:
        delay_ms = random.randint(3000, 6000)
        self._blink_timer.start(delay_ms)

    def _do_blink(self) -> None:
        self._blink = True
        self.update()
        QTimer.singleShot(120, self._end_blink)

    def _end_blink(self) -> None:
        self._blink = False
        self.update()
        self._schedule_blink()

    def _cycle_passive_mode(self) -> None:
        current = self._passive_mode
        choices = [m for m in self._PASSIVE_MODES if m != current]
        self._passive_mode = random.choice(choices)
        self._passive_t = 0.0
        self._eye_roll_phase = 0.0
        self._passive_extra_x = 0.0
        self._passive_extra_y = 0.0
        self._passive_angle = 0.0
        # Restore normal pupil position only when leaving eye_roll mode
        if current == "eye_roll":
            dx, dy = self._EXPR_PUPIL.get(self._state, (0, 0))
            self._pupil_dx = dx
            self._pupil_dy = dy
        # Schedule next mode change at a random interval
        self._passive_mode_timer.start(random.randint(self._PASSIVE_MODE_MIN_MS, self._PASSIVE_MODE_MAX_MS))

    def _tick(self) -> None:
        dt = 0.016  # ~16ms
        speed = 0.4 if self._state == SLEEPY else 1.2
        self._bob_t += dt * speed
        self._passive_t += dt

        if self._state == DISMISSING:
            self._scale = max(0.0, self._scale - 0.04)
            self._opacity_val = max(0.0, self._opacity_val - 0.04)
            if self._scale <= 0.0 or self._opacity_val <= 0.0:
                self._tick_timer.stop()
                if self._dismiss_cb:
                    self._dismiss_cb()
                return
        else:
            # Not dismissing — run all motion physics.
            # Jump physics (runs for any jumping state)
            if self._jumping:
                self._jump_offset += self._jump_vel * dt * 60
                self._jump_vel += 0.5  # gravity
                if self._jump_offset >= 0.0:
                    self._jump_offset = 0.0
                    self._jumping = False
                    # Trigger squash-and-stretch on landing
                    self._squash_active = True
                    self._squash_t = 0.0

            # Squash-and-stretch countdown
            if self._squash_active:
                self._squash_t += dt * 5.0
                if self._squash_t >= 1.0:
                    self._squash_t = 0.0
                    self._squash_active = False

            # Wobble/tilt phase for TALKING
            if self._state == TALKING:
                self._tilt_t += dt * 3.0
            else:
                self._tilt_t = 0.0

            # Rapid horizontal wiggle for SURPRISED
            if self._state == SURPRISED:
                self._wiggle_t += dt * 8.0
            else:
                self._wiggle_t = 0.0

            # Eye roll passive mode
            if self._state == IDLE and self._passive_mode == "eye_roll":
                self._eye_roll_phase += dt * 1.5
                roll_r = 3
                self._pupil_dx = int(roll_r * math.cos(self._eye_roll_phase))
                self._pupil_dy = int(roll_r * math.sin(self._eye_roll_phase))

            # Yawn passive mode
            if self._state == IDLE and self._passive_mode == "yawn":
                if self._passive_t < 1.5:
                    self._yawn_amount = min(1.0, self._passive_t / 1.0)
                else:
                    self._yawn_amount = max(0.0, 1.0 - (self._passive_t - 1.5) / 1.0)
            else:
                self._yawn_amount = max(0.0, self._yawn_amount - dt * 2.0)

        self.update()

    def set_state(self, state: str) -> None:
        self._state = state
        dx, dy = self._EXPR_PUPIL.get(state, (0, 0))
        self._pupil_dx = dx
        self._pupil_dy = dy
        self._eye_half = (state == SLEEPY)
        if state in (HAPPY, SURPRISED, TALKING):
            self._jump_offset = -8.0
            self._jump_vel = 0.0
            self._jumping = True
        if state == DISMISSING:
            self._scale = 1.0
            self._opacity_val = 1.0
        # Reset secondary animations on state change for clean transitions
        if state != TALKING:
            self._tilt_t = 0.0
        if state != SURPRISED:
            self._wiggle_t = 0.0

    def start_dismiss(self, callback=None) -> None:
        self._dismiss_cb = callback
        self.set_state(DISMISSING)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Passive fade mode modulates opacity independently of dismiss fade-out
        if self._state != DISMISSING and self._passive_mode == "fade":
            fade_opacity = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._passive_t * 1.5))
            p.setOpacity(self._opacity_val * fade_opacity)
        else:
            p.setOpacity(self._opacity_val)

        if self._state == IDLE and self._passive_mode == "bounce":
            bob = -abs(math.sin(self._bob_t * 2.0)) * 10.0
        else:
            bob = math.sin(self._bob_t) * 3.0
        jump = self._jump_offset if self._jumping else 0.0
        total_offset = bob + jump

        cx = self._tw // 2
        cy_base = self._th // 2 + int(self._th * 0.15)

        # ── Tilt / rotation angle (degrees) ──────────────────────────────────
        if self._state == TALKING:
            # Gentle side-to-side wobble while speaking
            angle = math.sin(self._tilt_t) * 8.0
        elif self._state == SAD:
            # Slight downward droop
            angle = -5.0
        elif self._state == SLEEPY:
            # Slow exaggerated sway
            angle = math.sin(self._bob_t * 0.25) * 12.0
        elif self._state == IDLE and self._passive_mode == "spin":
            # Slow continuous spin in idle mode
            angle = (self._passive_t * 45.0) % 360.0
        elif self._state == IDLE and self._passive_mode == "wobble":
            # Pronounced side-to-side wobble in idle mode
            angle = math.sin(self._passive_t * 2.5) * 18.0
        elif self._state == IDLE and self._passive_mode == "nod":
            angle = math.sin(self._passive_t * 2.5) * 10.0
        elif self._state == IDLE and self._passive_angle != 0.0:
            # Subclass-provided angle for passive modes like "roll"
            angle = self._passive_angle
        else:
            angle = 0.0

        # ── Horizontal wiggle offset (SURPRISED) ─────────────────────────────
        wiggle_x = math.sin(self._wiggle_t) * 4.0 if self._state == SURPRISED else 0.0

        # ── Scale components ──────────────────────────────────────────────────
        if self._squash_active:
            # Squash-and-stretch on jump landing: briefly squash then snap back
            sq = math.sin(self._squash_t * math.pi)
            sx = 1.0 + sq * 0.25   # momentarily wider
            sy = 1.0 - sq * 0.20   # momentarily shorter
        elif self._state == IDLE and self._passive_mode == "pulse":
            # Stronger breathing pulse in pulse mode
            s = 1.0 + math.sin(self._passive_t * 2.0) * 0.12
            sx = s
            sy = s
        elif self._state == IDLE and self._passive_mode == "stretch":
            sx = 1.0 - abs(math.sin(self._passive_t * 1.5)) * 0.08
            sy = 1.0 + abs(math.sin(self._passive_t * 1.5)) * 0.18
        elif self._state == IDLE:
            # Subtle breathe / pulse while idle
            s = 1.0 + math.sin(self._bob_t * 0.7) * 0.025
            sx = s
            sy = s
        else:
            sx = 1.0
            sy = 1.0

        # Apply dismiss shrink on top of any other scale
        sx *= self._scale
        sy *= self._scale

        p.save()
        # Translate origin to the draw center (incorporating vertical bob/jump,
        # horizontal wiggle, and subclass passive extra offsets), then apply
        # rotation and scale around that center before drawing.
        p.translate(cx + wiggle_x + int(self._passive_extra_x),
                    cy_base + int(total_offset + self._passive_extra_y))
        if angle != 0.0:
            p.rotate(angle)
        if sx != 1.0 or sy != 1.0:
            p.scale(sx, sy)
        self._draw_trophy(p, 0, 0)
        self._draw_skin_accessory(p, 0, 0)
        p.restore()

        # ── Sparkle overlay ───────────────────────────────────────────────────
        if self._state == IDLE and self._passive_mode == "sparkle":
            self._draw_sparkles(p, cx, int(cy_base + total_offset))

        # ── Shimmer/shine sweep overlay ───────────────────────────────────────
        if self._state == IDLE and self._passive_mode == "shimmer":
            self._draw_shimmer(p)

        p.end()

    def _draw_shimmer(self, p: QPainter) -> None:
        """Draw a golden shimmer sweep across the trophy."""
        sweep_speed = 1.2
        # Normalized sweep position cycles 0→1 over ~2s
        sweep_pos = (self._passive_t * sweep_speed) % 2.0
        if sweep_pos > 1.0:
            # Return sweep — invisible
            return
        tw = self._tw
        th = self._th
        # Map sweep_pos 0→1 to x position across the widget
        sweep_x = int((sweep_pos - 0.2) * (tw + 40)) - 20
        sweep_w = max(12, int(tw * 0.25))
        grad = QLinearGradient(float(sweep_x), 0.0, float(sweep_x + sweep_w), float(th))
        grad.setColorAt(0.0, QColor(255, 220, 80, 0))
        grad.setColorAt(0.3, QColor(255, 220, 80, 80))
        grad.setColorAt(0.5, QColor(255, 240, 120, 120))
        grad.setColorAt(0.7, QColor(255, 220, 80, 80))
        grad.setColorAt(1.0, QColor(255, 220, 80, 0))
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRect(sweep_x, 0, sweep_w, th)
        p.restore()

    def _draw_sparkles(self, p: QPainter, cx: int, cy: int) -> None:
        """Draw animated star sparkles around the character."""
        t = self._passive_t
        offsets = [(-30, -38), (28, -35), (-26, 28), (30, 26), (0, -48), (34, -10), (-34, -8)]
        for i, (ox, oy) in enumerate(offsets):
            phase = (t * 2.5 + i * 0.9) % (math.pi * 2)
            alpha = int(200 * abs(math.sin(phase)))
            if alpha < 20:
                continue
            size = 2.5 + 1.5 * abs(math.sin(phase))
            sx = cx + ox
            sy = cy + oy
            color = QColor(255, 240, 80, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            # 4-pointed star shape
            star = QPainterPath()
            star.moveTo(sx, sy - size)
            star.lineTo(sx + size * 0.3, sy - size * 0.3)
            star.lineTo(sx + size, sy)
            star.lineTo(sx + size * 0.3, sy + size * 0.3)
            star.lineTo(sx, sy + size)
            star.lineTo(sx - size * 0.3, sy + size * 0.3)
            star.lineTo(sx - size, sy)
            star.lineTo(sx - size * 0.3, sy - size * 0.3)
            star.closeSubpath()
            p.fillPath(star, color)

    def _draw_trophy(self, p: QPainter, cx: int, cy: int) -> None:
        tw = self._tw
        th = self._th

        # ── Base / Pedestal ──────────────────────────────────────────────────
        base_w = int(tw * 0.55)
        base_h = int(th * 0.12)
        base_x = cx - base_w // 2
        base_y = cy + int(th * 0.32)

        grad_base = QLinearGradient(float(base_x), float(base_y), float(base_x), float(base_y + base_h))
        grad_base.setColorAt(0.0, QColor("#DAA520"))
        grad_base.setColorAt(1.0, QColor("#8B6914"))
        p.setBrush(grad_base)
        p.setPen(QPen(QColor("#704214"), 1))
        p.drawRoundedRect(base_x, base_y, base_w, base_h, 3, 3)

        # Stem
        stem_w = int(tw * 0.16)
        stem_h = int(th * 0.16)
        stem_x = cx - stem_w // 2
        stem_y = base_y - stem_h
        grad_stem = QLinearGradient(float(stem_x), 0.0, float(stem_x + stem_w), 0.0)
        grad_stem.setColorAt(0.0, QColor("#8B6914"))
        grad_stem.setColorAt(0.5, QColor("#FFD700"))
        grad_stem.setColorAt(1.0, QColor("#8B6914"))
        p.setBrush(grad_stem)
        p.setPen(QPen(QColor("#704214"), 1))
        p.drawRect(stem_x, stem_y, stem_w, stem_h)

        # ── Cup body ─────────────────────────────────────────────────────────
        cup_w = int(tw * 0.62)
        cup_h = int(th * 0.52)
        cup_x = cx - cup_w // 2
        cup_y = cy - int(th * 0.36)

        grad_cup = QLinearGradient(float(cup_x), 0.0, float(cup_x + cup_w), 0.0)
        grad_cup.setColorAt(0.0, QColor("#B8860B"))
        grad_cup.setColorAt(0.3, QColor("#FFD700"))
        grad_cup.setColorAt(0.7, QColor("#FFC200"))
        grad_cup.setColorAt(1.0, QColor("#B8860B"))
        p.setBrush(grad_cup)
        p.setPen(QPen(QColor("#704214"), 1))

        # Trapezoid-ish cup: wider at top, narrower at bottom
        cup_path = QPainterPath()
        top_extra = int(cup_w * 0.1)
        cup_path.moveTo(cup_x - top_extra, cup_y)
        cup_path.lineTo(cup_x + cup_w + top_extra, cup_y)
        cup_path.lineTo(cup_x + cup_w, cup_y + cup_h)
        cup_path.lineTo(cup_x, cup_y + cup_h)
        cup_path.closeSubpath()
        p.fillPath(cup_path, grad_cup)
        p.strokePath(cup_path, QPen(QColor("#704214"), 1))

        # Cup rim highlight
        p.setPen(QPen(QColor("#FFFACD"), 2))
        p.drawLine(cup_x - top_extra + 4, cup_y + 3, cup_x + cup_w + top_extra - 4, cup_y + 3)

        # ── Handles ──────────────────────────────────────────────────────────
        handle_y = cup_y + cup_h // 3
        handle_h = int(cup_h * 0.5)
        handle_w = int(tw * 0.12)

        for side in (-1, 1):
            if side == -1:
                hx = cup_x - top_extra - handle_w
            else:
                hx = cup_x + cup_w + top_extra
            p.setBrush(QColor("#DAA520"))
            p.setPen(QPen(QColor("#704214"), 1))
            p.drawRoundedRect(hx, handle_y, handle_w, handle_h, handle_w // 2, handle_w // 2)

        # ── Eyes ─────────────────────────────────────────────────────────────
        eye_y = cup_y + cup_h // 2 - 4
        eye_r = max(4, int(tw * 0.09))
        left_eye_x = cx - int(tw * 0.14)
        right_eye_x = cx + int(tw * 0.14)

        for ex in (left_eye_x, right_eye_x):
            # White sclera
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor("#333333"), 1))
            if self._blink or self._state == SLEEPY:
                # Blink: half-closed line
                blink_h = eye_r if self._eye_half else 2
                p.drawEllipse(ex - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2)
                # Draw eyelid overlay
                p.setBrush(QColor("#DAA520"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(ex - eye_r - 1, eye_y - eye_r - 1, eye_r * 2 + 2, blink_h + 2)
            else:
                p.drawEllipse(ex - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2)

            if not self._blink:
                # Pupil
                pr = max(2, int(eye_r * 0.55))
                if self._state == SURPRISED:
                    pr = eye_r - 1
                px = ex + self._pupil_dx
                py = eye_y + self._pupil_dy
                p.setBrush(QColor("#111111"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(px - pr, py - pr, pr * 2, pr * 2)

                # Eye shine
                p.setBrush(QColor("#FFFFFF"))
                shine_r = max(1, pr // 3)
                p.drawEllipse(px - pr // 3, py - pr // 3, shine_r, shine_r)

        # ── Mouth ────────────────────────────────────────────────────────────
        mouth_cx = cx
        mouth_y = eye_y + eye_r + 6
        mouth_w = int(tw * 0.28)
        mouth_h = int(tw * 0.14)
        talk_pulse = (math.sin(self._tilt_t * 3.0) > 0) if self._state == TALKING else False
        yawn_open = self._yawn_amount > 0.1 if self._state == IDLE and self._passive_mode == "yawn" else False

        p.setPen(QPen(QColor("#333333"), 1))
        p.setBrush(QColor("#333333"))
        if self._state == SURPRISED or (yawn_open and self._yawn_amount > self._YAWN_FULL_OPEN_THRESHOLD):
            ow = int(mouth_w * 0.7)
            oh = int(mouth_h * (1.0 + self._yawn_amount * 0.5))
            p.setBrush(QColor("#111111"))
            p.drawEllipse(mouth_cx - ow // 2, mouth_y - oh // 4, ow, oh)
        elif self._state == HAPPY:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#333333"), 2))
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w // 2, mouth_y)
            path.quadTo(mouth_cx, mouth_y + mouth_h, mouth_cx + mouth_w // 2, mouth_y)
            p.drawPath(path)
        elif self._state == SAD:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#333333"), 2))
            frown_y = mouth_y + mouth_h
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w // 2, frown_y)
            path.quadTo(mouth_cx, mouth_y, mouth_cx + mouth_w // 2, frown_y)
            p.drawPath(path)
        elif self._state == TALKING and talk_pulse:
            tw2 = int(mouth_w * 0.5)
            th2 = int(mouth_h * 0.6)
            p.setBrush(QColor("#111111"))
            p.drawEllipse(mouth_cx - tw2 // 2, mouth_y - th2 // 4, tw2, th2)
        elif self._state == SLEEPY or (yawn_open and self._yawn_amount <= self._YAWN_FULL_OPEN_THRESHOLD):
            ow = int(mouth_w * 0.3 + self._yawn_amount * mouth_w * 0.4)
            oh = int(mouth_h * 0.4 + self._yawn_amount * mouth_h * 0.5)
            p.setBrush(QColor("#333333"))
            p.drawEllipse(mouth_cx - ow // 2, mouth_y - oh // 4, ow, oh)
        elif self._state == DISMISSING:
            p.setPen(QPen(QColor("#333333"), 2))
            p.drawLine(mouth_cx - mouth_w // 3, mouth_y + mouth_h // 2,
                       mouth_cx + mouth_w // 3, mouth_y + mouth_h // 2)
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#333333"), 2))
            path = QPainterPath()
            path.moveTo(mouth_cx - mouth_w // 3, mouth_y)
            path.quadTo(mouth_cx, mouth_y + mouth_h // 2, mouth_cx + mouth_w // 3, mouth_y)
            p.drawPath(path)

    def _cup_safe_clip(self, cx: int, cy: int) -> QPainterPath:
        """Return the cup trapezoid path minus the face exclusion zone.

        Used by clothing skins so decorations don't paint over the face.
        """
        tw = self._tw
        th = self._th
        cup_w = int(tw * 0.62)
        cup_h = int(th * 0.52)
        cup_x = cx - cup_w // 2
        cup_y = cy - int(th * 0.36)
        top_extra = int(cup_w * 0.1)
        eye_y = cup_y + cup_h // 2 - 4
        eye_r = max(4, int(tw * 0.09))
        mouth_y = eye_y + eye_r + 6
        mouth_h = int(tw * 0.14)
        mouth_w = int(tw * 0.28)
        fm = eye_r + 4
        cup_path = QPainterPath()
        cup_path.moveTo(float(cup_x - top_extra), float(cup_y))
        cup_path.lineTo(float(cup_x + cup_w + top_extra), float(cup_y))
        cup_path.lineTo(float(cup_x + cup_w), float(cup_y + cup_h))
        cup_path.lineTo(float(cup_x), float(cup_y + cup_h))
        cup_path.closeSubpath()
        face_path = QPainterPath()
        face_path.addRect(QRectF(
            cx - mouth_w // 2 - fm,
            eye_y - eye_r - fm,
            mouth_w + fm * 2,
            mouth_y + mouth_h + fm - (eye_y - eye_r - fm),
        ))
        return cup_path.subtracted(face_path)

    def _draw_skin_accessory(self, p: QPainter, cx: int, cy: int) -> None:
        """Draw the skin-specific accessory on top of the trophy."""
        skin = getattr(self, "_skin", "classic")
        if skin == "classic" or not skin:
            return
        tw = self._tw
        th = self._th
        # Cup top position (reference for accessories placed on top)
        cup_y_top = cy - int(th * 0.36)

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if skin == "crown":
            # Golden crown on top of cup
            cw = int(tw * 0.45)
            ch = int(th * 0.14)
            bx = cx - cw // 2
            by = cup_y_top - ch
            grad = QLinearGradient(float(bx), float(by), float(bx), float(by + ch))
            grad.setColorAt(0.0, QColor("#FFD700"))
            grad.setColorAt(1.0, QColor("#B8860B"))
            p.setBrush(grad)
            p.setPen(QPen(QColor("#8B6914"), 1))
            p.drawRect(bx, by + ch // 2, cw, ch // 2)
            # Three crown points
            tip_w = cw // 5
            for i in range(3):
                tx = bx + (i * cw // 2) - tip_w // 2 + cw // 4
                path = QPainterPath()
                path.moveTo(tx, by + ch // 2)
                path.lineTo(tx + tip_w // 2, by)
                path.lineTo(tx + tip_w, by + ch // 2)
                path.closeSubpath()
                p.fillPath(path, QColor("#FFD700"))
                p.strokePath(path, QPen(QColor("#8B6914"), 1))

        elif skin == "top_hat":
            hw = int(tw * 0.35)
            hh = int(th * 0.22)
            brim_w = int(tw * 0.50)
            brim_h = int(th * 0.05)
            hx = cx - hw // 2
            hy = cup_y_top - hh - brim_h
            p.setBrush(QColor("#111111"))
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawRect(hx, hy, hw, hh)
            # Brim
            p.drawRect(cx - brim_w // 2, cup_y_top - brim_h, brim_w, brim_h)
            # Hat band
            p.setBrush(QColor("#FF7F00"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(hx, hy + hh - int(hh * 0.2), hw, int(hh * 0.2))

        elif skin == "sunglasses":
            eye_y = cy - int(th * 0.36) + int(th * 0.26)
            g_r = int(tw * 0.11)
            lx = cx - int(tw * 0.14)
            rx = cx + int(tw * 0.14)
            p.setBrush(QColor(0, 0, 0, 180))
            p.setPen(QPen(QColor("#222222"), 1))
            p.drawEllipse(lx - g_r, eye_y - g_r, g_r * 2, g_r * 2)
            p.drawEllipse(rx - g_r, eye_y - g_r, g_r * 2, g_r * 2)
            # Bridge
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawLine(lx + g_r, eye_y, rx - g_r, eye_y)

        elif skin == "party_hat":
            hw = int(tw * 0.30)
            hh = int(th * 0.28)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            path = QPainterPath()
            path.moveTo(cx, hy)
            path.lineTo(hx, cup_y_top)
            path.lineTo(hx + hw, cup_y_top)
            path.closeSubpath()
            p.setBrush(QColor("#FF3399"))
            p.setPen(QPen(QColor("#CC1177"), 1))
            p.fillPath(path, QColor("#FF3399"))
            p.strokePath(path, QPen(QColor("#CC1177"), 1))
            # Dots
            p.setBrush(QColor("#FFFF00"))
            p.setPen(Qt.PenStyle.NoPen)
            for dx, dy in [(-4, hh // 2), (4, hh // 3), (0, hh * 2 // 3)]:
                p.drawEllipse(cx + dx - 2, hy + dy - 2, 4, 4)
            # Pom-pom
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - 4, hy - 4, 8, 8)

        elif skin == "pirate":
            hw = int(tw * 0.42)
            hh = int(th * 0.16)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            p.setBrush(QColor("#111111"))
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawRect(hx, hy, hw, hh)
            # Brim
            brim_w = int(tw * 0.55)
            p.drawRect(cx - brim_w // 2, hy + hh - 3, brim_w, 6)
            # Skull & crossbones (simple)
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            sr = int(tw * 0.06)
            p.drawEllipse(cx - sr, hy + hh // 4 - sr, sr * 2, sr * 2)
            p.setPen(QPen(QColor("#FFFFFF"), 1))
            cross_y = hy + hh * 3 // 4
            p.drawLine(cx - sr, cross_y, cx + sr, cross_y)
            p.drawLine(cx - sr + 2, cross_y - 2, cx + sr - 2, cross_y + 2)

        elif skin == "headband":
            # Ninja headband
            hb_y = cup_y_top + int(th * 0.06)
            hb_h = int(th * 0.07)
            hb_w = int(tw * 0.70)
            p.setBrush(QColor("#222222"))
            p.setPen(QPen(QColor("#111111"), 1))
            p.drawRect(cx - hb_w // 2, hb_y, hb_w, hb_h)
            # Forehead plate
            p.setBrush(QColor("#555577"))
            p.setPen(QPen(QColor("#333355"), 1))
            plate_w = int(tw * 0.28)
            plate_h = int(th * 0.09)
            p.drawRect(cx - plate_w // 2, hb_y - 2, plate_w, plate_h)

        elif skin == "wizard_hat":
            hw = int(tw * 0.32)
            hh = int(th * 0.35)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            path = QPainterPath()
            path.moveTo(cx, hy)
            path.lineTo(hx, cup_y_top)
            path.lineTo(hx + hw, cup_y_top)
            path.closeSubpath()
            p.setBrush(QColor("#4400AA"))
            p.setPen(QPen(QColor("#220088"), 1))
            p.fillPath(path, QColor("#4400AA"))
            p.strokePath(path, QPen(QColor("#220088"), 1))
            # Stars on hat
            p.setBrush(QColor("#FFD700"))
            p.setPen(Qt.PenStyle.NoPen)
            for dx, dy in [(-3, hh // 3), (5, hh // 2), (1, hh * 2 // 3)]:
                p.drawEllipse(cx + dx - 2, hy + dy - 2, 4, 4)
            # Brim
            brim_w = int(tw * 0.50)
            p.setBrush(QColor("#330099"))
            p.setPen(QPen(QColor("#220088"), 1))
            p.drawRect(cx - brim_w // 2, cup_y_top - 4, brim_w, 8)

        elif skin == "santa_hat":
            hw = int(tw * 0.32)
            hh = int(th * 0.28)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            path = QPainterPath()
            path.moveTo(cx, hy)
            path.lineTo(hx, cup_y_top)
            path.lineTo(hx + hw, cup_y_top)
            path.closeSubpath()
            p.setBrush(QColor("#CC0000"))
            p.setPen(QPen(QColor("#AA0000"), 1))
            p.fillPath(path, QColor("#CC0000"))
            p.strokePath(path, QPen(QColor("#AA0000"), 1))
            # White trim at base
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            trim_w = int(tw * 0.50)
            p.drawRect(cx - trim_w // 2, cup_y_top - 5, trim_w, 8)
            # Pom-pom
            p.drawEllipse(cx - 4, hy - 4, 8, 8)

        elif skin == "ice":
            # Icicles hanging from cup rim
            rim_y = cup_y_top
            for i in range(5):
                ix = cx - int(tw * 0.22) + i * int(tw * 0.11)
                ice_h = int(th * 0.08) + (i % 2) * int(th * 0.05)
                path = QPainterPath()
                path.moveTo(ix - 3, rim_y)
                path.lineTo(ix + 3, rim_y)
                path.lineTo(ix, rim_y + ice_h)
                path.closeSubpath()
                p.fillPath(path, QColor(180, 230, 255, 200))
                p.strokePath(path, QPen(QColor(100, 180, 255), 1))

        elif skin == "flame":
            # Flames around cup base
            base_y = cy + int(th * 0.32)
            for i in range(5):
                fx = cx - int(tw * 0.22) + i * int(tw * 0.11)
                fl_h = int(th * 0.14) + (i % 2) * int(th * 0.05)
                path = QPainterPath()
                path.moveTo(fx - 4, base_y)
                path.quadTo(fx - 2, base_y - fl_h * 0.6, fx, base_y - fl_h)
                path.quadTo(fx + 2, base_y - fl_h * 0.6, fx + 4, base_y)
                path.closeSubpath()
                p.fillPath(path, QColor(255, int(120 + i * 20), 0, 200))

        elif skin == "sparks":
            # Electric sparks around cup
            p.setPen(QPen(QColor("#FFFF00"), 2))
            for i in range(4):
                angle_rad = (i / 4.0) * 6.28
                sx2 = cx + int(math.cos(angle_rad) * tw * 0.38)
                sy2 = cy - int(th * 0.08) + int(math.sin(angle_rad) * th * 0.28)
                ex2 = cx + int(math.cos(angle_rad) * tw * 0.48)
                ey2 = cy - int(th * 0.08) + int(math.sin(angle_rad) * th * 0.35)
                p.drawLine(sx2, sy2, ex2, ey2)

        elif skin == "rainbow":
            # Rainbow arc above cup
            arc_r = int(tw * 0.42)
            colors = [QColor("#FF0000"), QColor("#FF7F00"), QColor("#FFFF00"),
                      QColor("#00BB00"), QColor("#0000FF"), QColor("#8B00FF")]
            for i, color in enumerate(colors):
                r = arc_r - i * 3
                p.setPen(QPen(color, 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(cx - r, cup_y_top - r, r * 2, r * 2, 0, 180 * 16)

        elif skin == "gears":
            # Small gear near cup
            gr = int(tw * 0.08)
            gx = cx + int(tw * 0.28)
            gy = cup_y_top + int(th * 0.10)
            p.setBrush(QColor("#888888"))
            p.setPen(QPen(QColor("#555555"), 1))
            p.drawEllipse(gx - gr, gy - gr, gr * 2, gr * 2)
            for t in range(8):
                a = t * 45.0
                tx2 = gx + int(math.cos(math.radians(a)) * gr * 1.5)
                ty2 = gy + int(math.sin(math.radians(a)) * gr * 1.5)
                p.drawLine(gx, gy, tx2, ty2)

        elif skin == "helmet":
            # Astronaut helmet
            h_r = int(tw * 0.36)
            p.setBrush(QColor(200, 220, 255, 180))
            p.setPen(QPen(QColor("#AABBDD"), 2))
            p.drawEllipse(cx - h_r, cup_y_top - h_r // 2, h_r * 2, int(h_r * 1.4))
            # Visor
            p.setBrush(QColor(100, 180, 255, 120))
            p.setPen(Qt.PenStyle.NoPen)
            vr = int(h_r * 0.55)
            p.drawEllipse(cx - vr, cup_y_top, vr * 2, int(vr * 1.2))

        elif skin == "detective":
            # Detective hat (fedora style)
            hw = int(tw * 0.38)
            hh = int(th * 0.14)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            p.setBrush(QColor("#5C4000"))
            p.setPen(QPen(QColor("#3A2800"), 1))
            p.drawRect(hx, hy, hw, hh)
            # Wide brim
            brim_w = int(tw * 0.56)
            p.drawRect(cx - brim_w // 2, cup_y_top - 5, brim_w, 8)
            # Hat band
            p.setBrush(QColor("#222222"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(hx, hy + hh - 5, hw, 5)

        elif skin == "chef_hat":
            # Tall white chef hat
            hw = int(tw * 0.30)
            hh = int(th * 0.28)
            hx = cx - hw // 2
            hy = cup_y_top - hh
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor("#CCCCCC"), 1))
            p.drawRoundedRect(hx, hy, hw, hh, 4, 4)
            # Band
            p.setBrush(QColor("#DDDDDD"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(hx, cup_y_top - 6, hw, 6)

        elif skin == "cape":
            # Vampire cape draped behind
            cape_w = int(tw * 0.65)
            cape_h = int(th * 0.45)
            cap_x = cx - cape_w // 2
            cap_y = cup_y_top - int(th * 0.05)
            path = QPainterPath()
            path.moveTo(cx - cape_w // 2, cap_y)
            path.lineTo(cx + cape_w // 2, cap_y)
            path.lineTo(cx + cape_w // 2, cap_y + cape_h)
            path.lineTo(cx, cap_y + cape_h - int(cape_h * 0.25))
            path.lineTo(cx - cape_w // 2, cap_y + cape_h)
            path.closeSubpath()
            p.fillPath(path, QColor(80, 0, 0, 180))
            p.strokePath(path, QPen(QColor("#CC0000"), 1))

        elif skin == "antenna":
            # Robot antenna
            ax = cx
            ay = cup_y_top
            p.setPen(QPen(QColor("#AAAAAA"), 2))
            p.drawLine(ax, ay, ax, ay - int(th * 0.20))
            p.setBrush(QColor("#FF4444"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(ax - 4, ay - int(th * 0.20) - 4, 8, 8)

        elif skin == "crystal":
            # Diamond crystal on top
            dc = int(tw * 0.10)
            dx2 = cx
            dy2 = cup_y_top - int(th * 0.10)
            path = QPainterPath()
            path.moveTo(dx2, dy2 - dc * 2)
            path.lineTo(dx2 + dc, dy2)
            path.lineTo(dx2, dy2 + dc)
            path.lineTo(dx2 - dc, dy2)
            path.closeSubpath()
            p.fillPath(path, QColor(100, 220, 255, 200))
            p.strokePath(path, QPen(QColor("#AAEEFF"), 1))

        elif skin == "neon_glow":
            # Neon glow halo around cup
            glow_r = int(tw * 0.40)
            for alpha, width in [(30, 10), (60, 6), (120, 3)]:
                p.setPen(QPen(QColor(0, 229, 255, alpha), width))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(cx - glow_r, cup_y_top - glow_r // 3, glow_r * 2, glow_r)

        elif skin == "medal":
            # Champion medal hanging from cup handle
            mx = cx + int(tw * 0.36)
            my = cy
            p.setPen(QPen(QColor("#DAA520"), 2))
            p.drawLine(mx, cup_y_top + int(th * 0.10), mx, my - int(th * 0.08))
            p.setBrush(QColor("#FFD700"))
            p.setPen(QPen(QColor("#B8860B"), 1))
            mr = int(tw * 0.09)
            p.drawEllipse(mx - mr, my - mr, mr * 2, mr * 2)
            p.setPen(QPen(QColor("#333333"), 1))
            p.setFont(QFont("Arial", max(5, int(tw * 0.10)), QFont.Weight.Bold))
            p.drawText(mx - mr, my - mr, mr * 2, mr * 2,
                       Qt.AlignmentFlag.AlignCenter, "1")

        elif skin == "suit":
            # Tuxedo: black jacket sides + white shirt front + red bow tie
            cup_w_s = int(tw * 0.62)
            cup_h_s = int(th * 0.52)
            cup_x_s = cx - cup_w_s // 2
            top_ex = int(cup_w_s * 0.1)
            shirt_hw = max(5, int(cup_w_s * 0.18))
            p.save()
            p.setClipPath(self._cup_safe_clip(cx, cy))
            p.setBrush(QColor("#1A1A1A"))
            p.setPen(Qt.PenStyle.NoPen)
            # Left jacket panel
            p.drawRect(cup_x_s - top_ex, cup_y_top,
                       cx - shirt_hw - (cup_x_s - top_ex), cup_h_s)
            # Right jacket panel
            p.drawRect(cx + shirt_hw, cup_y_top,
                       cup_x_s + cup_w_s + top_ex - cx - shirt_hw, cup_h_s)
            # White shirt front
            p.setBrush(QColor("#F5F5F5"))
            p.drawRect(cx - shirt_hw, cup_y_top, shirt_hw * 2, cup_h_s)
            # Shirt buttons
            p.setBrush(QColor("#999999"))
            for bi in range(3):
                btn_y = cup_y_top + cup_h_s * (bi + 1) // 4
                p.drawEllipse(cx - 2, btn_y - 2, 4, 4)
            p.restore()
            # Bow tie at collar top (above face zone)
            bt_y = cup_y_top + max(3, int(cup_h_s * 0.05))
            bt_w = max(5, int(tw * 0.09))
            bt_h = max(3, int(th * 0.04))
            bow_l = QPainterPath()
            bow_l.moveTo(float(cx - bt_w), float(bt_y - bt_h))
            bow_l.lineTo(float(cx), float(bt_y))
            bow_l.lineTo(float(cx - bt_w), float(bt_y + bt_h))
            bow_l.closeSubpath()
            p.fillPath(bow_l, QColor("#CC0000"))
            bow_r = QPainterPath()
            bow_r.moveTo(float(cx + bt_w), float(bt_y - bt_h))
            bow_r.lineTo(float(cx), float(bt_y))
            bow_r.lineTo(float(cx + bt_w), float(bt_y + bt_h))
            bow_r.closeSubpath()
            p.fillPath(bow_r, QColor("#CC0000"))
            p.setBrush(QColor("#990000"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - 3, bt_y - 3, 6, 6)

        elif skin == "hoodie":
            # Grey hoodie with raised hood above cup and kangaroo pocket
            cup_w_h = int(tw * 0.62)
            cup_h_h = int(th * 0.52)
            cup_x_h = cx - cup_w_h // 2
            top_ex = int(cup_w_h * 0.1)
            hood_color = QColor("#4A4A4A")
            # Hood raised above the cup top (always above the face)
            hood_w = int(tw * 0.52)
            hood_h = int(th * 0.16)
            p.setBrush(hood_color)
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawRoundedRect(cx - hood_w // 2, cup_y_top - hood_h,
                              hood_w, hood_h + 4, hood_w // 3, hood_w // 3)
            # Hoodie body over cup (clipped to avoid face)
            p.save()
            p.setClipPath(self._cup_safe_clip(cx, cy))
            p.setBrush(hood_color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(cup_x_h - top_ex, cup_y_top, cup_w_h + top_ex * 2, cup_h_h)
            # Kangaroo pocket at bottom of hoodie body
            pkt_w = int(cup_w_h * 0.42)
            pkt_h = int(cup_h_h * 0.18)
            pkt_y = cup_y_top + cup_h_h - pkt_h - int(cup_h_h * 0.05)
            p.setBrush(QColor("#3A3A3A"))
            p.setPen(QPen(QColor("#555555"), 1))
            p.drawRoundedRect(cx - pkt_w // 2, pkt_y, pkt_w, pkt_h, 3, 3)
            p.restore()
            # Drawstrings
            str_y = cup_y_top + int(cup_h_h * 0.12)
            p.setPen(QPen(QColor("#BBBBBB"), 1))
            p.drawLine(cx - 5, str_y, cx - 8, str_y + int(cup_h_h * 0.18))
            p.drawLine(cx + 5, str_y, cx + 8, str_y + int(cup_h_h * 0.18))
            # Aglets
            p.setBrush(QColor("#CCCCCC"))
            p.setPen(Qt.PenStyle.NoPen)
            aglet_y = str_y + int(cup_h_h * 0.18)
            p.drawEllipse(cx - 10, aglet_y - 2, 4, 4)
            p.drawEllipse(cx + 6, aglet_y - 2, 4, 4)

        elif skin == "superhero":
            # Red cape strips on cup sides + gold star emblem at collar
            cup_w_sp = int(tw * 0.62)
            cup_h_sp = int(th * 0.52)
            cup_x_sp = cx - cup_w_sp // 2
            top_ex = int(cup_w_sp * 0.1)
            cape_strip_w = max(5, int(cup_w_sp * 0.20))
            # Left cape strip (outer edge of cup)
            p.setBrush(QColor("#CC0000"))
            p.setPen(Qt.PenStyle.NoPen)
            cap_l = QPainterPath()
            cap_l.moveTo(float(cup_x_sp - top_ex), float(cup_y_top))
            cap_l.lineTo(float(cup_x_sp - top_ex + cape_strip_w), float(cup_y_top))
            cap_l.lineTo(float(cup_x_sp), float(cup_y_top + cup_h_sp))
            cap_l.lineTo(float(cup_x_sp - top_ex), float(cup_y_top + cup_h_sp))
            cap_l.closeSubpath()
            p.fillPath(cap_l, QColor("#CC0000"))
            # Right cape strip
            cap_r = QPainterPath()
            cap_r.moveTo(float(cup_x_sp + cup_w_sp + top_ex - cape_strip_w), float(cup_y_top))
            cap_r.lineTo(float(cup_x_sp + cup_w_sp + top_ex), float(cup_y_top))
            cap_r.lineTo(float(cup_x_sp + cup_w_sp + top_ex), float(cup_y_top + cup_h_sp))
            cap_r.lineTo(float(cup_x_sp + cup_w_sp), float(cup_y_top + cup_h_sp))
            cap_r.closeSubpath()
            p.fillPath(cap_r, QColor("#CC0000"))
            # Gold star emblem at collar (top of cup — always above face zone)
            emb_cx = cx
            emb_cy = cup_y_top + max(4, int(cup_h_sp * 0.07))
            emb_r = max(4, int(tw * 0.09))
            star_path = QPainterPath()
            for k in range(5):
                oa = math.radians(-90 + k * 72)
                ia = math.radians(-90 + k * 72 + 36)
                op = (emb_cx + math.cos(oa) * emb_r, emb_cy + math.sin(oa) * emb_r)
                ip = (emb_cx + math.cos(ia) * emb_r * 0.4, emb_cy + math.sin(ia) * emb_r * 0.4)
                if k == 0:
                    star_path.moveTo(float(op[0]), float(op[1]))
                else:
                    star_path.lineTo(float(op[0]), float(op[1]))
                star_path.lineTo(float(ip[0]), float(ip[1]))
            star_path.closeSubpath()
            p.fillPath(star_path, QColor("#FFD700"))
            p.strokePath(star_path, QPen(QColor("#CC8800"), 1))

        elif skin == "armor":
            # Silver armor plates on cup sides + shoulder pauldrons + gorget
            cup_w_a = int(tw * 0.62)
            cup_h_a = int(th * 0.52)
            cup_x_a = cx - cup_w_a // 2
            top_ex = int(cup_w_a * 0.1)
            # Shoulder pauldrons outside the cup (over handles area)
            pld_w = int(tw * 0.14)
            pld_h = int(th * 0.16)
            pld_y = cup_y_top + int(cup_h_a * 0.05)
            for hx_off in (cup_x_a - top_ex - pld_w - 2,
                           cup_x_a + cup_w_a + top_ex + 2):
                p.setBrush(QColor("#8888AA"))
                p.setPen(QPen(QColor("#555566"), 1))
                p.drawRoundedRect(hx_off, pld_y, pld_w, pld_h, 3, 3)
                p.setPen(QPen(QColor("#666677"), 1))
                for lv in range(3):
                    ly = pld_y + lv * pld_h // 3
                    p.drawLine(hx_off + 2, ly, hx_off + pld_w - 2, ly)
            # Armor side plates on cup (clipped)
            plate_w = max(5, int(cup_w_a * 0.22))
            p.save()
            p.setClipPath(self._cup_safe_clip(cx, cy))
            p.setBrush(QColor("#7777AA"))
            p.setPen(QPen(QColor("#555577"), 1))
            p.drawRoundedRect(cup_x_a - top_ex, cup_y_top, plate_w, cup_h_a, 2, 2)
            p.drawRoundedRect(cup_x_a + cup_w_a + top_ex - plate_w, cup_y_top, plate_w, cup_h_a, 2, 2)
            p.setPen(QPen(QColor("#444455"), 1))
            for seg in range(1, 4):
                seg_y = cup_y_top + seg * cup_h_a // 4
                p.drawLine(cup_x_a - top_ex, seg_y, cup_x_a - top_ex + plate_w, seg_y)
                r_s = cup_x_a + cup_w_a + top_ex - plate_w
                p.drawLine(r_s, seg_y, r_s + plate_w, seg_y)
            p.restore()
            # Gorget (neck guard) at top of cup — above face zone
            gorg_w = int(cup_w_a * 0.55)
            gorg_h = max(4, int(cup_h_a * 0.07))
            p.setBrush(QColor("#8888AA"))
            p.setPen(QPen(QColor("#555566"), 1))
            p.drawRoundedRect(cx - gorg_w // 2, cup_y_top - gorg_h // 2, gorg_w, gorg_h, 2, 2)

        elif skin == "lab_coat":
            # White lab coat panels on cup sides + collar + pocket
            cup_w_l = int(tw * 0.62)
            cup_h_l = int(th * 0.52)
            cup_x_l = cx - cup_w_l // 2
            top_ex = int(cup_w_l * 0.1)
            collar_hw = max(5, int(cup_w_l * 0.18))
            p.save()
            p.setClipPath(self._cup_safe_clip(cx, cy))
            p.setBrush(QColor("#EEEEEE"))
            p.setPen(QPen(QColor("#CCCCCC"), 1))
            # Left coat panel
            p.drawRect(cup_x_l - top_ex, cup_y_top,
                       cx - collar_hw - (cup_x_l - top_ex), cup_h_l)
            # Right coat panel
            p.drawRect(cx + collar_hw, cup_y_top,
                       cup_x_l + cup_w_l + top_ex - cx - collar_hw, cup_h_l)
            # Breast pocket on right side
            pkt_w = max(4, int(cup_w_l * 0.16))
            pkt_h = int(cup_h_l * 0.18)
            pkt_x = cx + collar_hw + max(2, int((cup_w_l // 2 - collar_hw) * 0.25))
            pkt_y = cup_y_top + int(cup_h_l * 0.55)
            p.setBrush(QColor("#DDDDDD"))
            p.setPen(QPen(QColor("#BBBBBB"), 1))
            p.drawRect(pkt_x, pkt_y, pkt_w, pkt_h)
            # Pen in pocket
            p.setBrush(QColor("#2244AA"))
            p.setPen(Qt.PenStyle.NoPen)
            pen_x = pkt_x + pkt_w // 4
            p.drawRect(pen_x, pkt_y - int(pkt_h * 0.3), max(2, pkt_w // 6), int(pkt_h * 0.45))
            p.restore()
            # Collar lapels at top of cup (above face zone)
            lap_w = max(5, int(cup_w_l * 0.20))
            lap_h = max(4, int(cup_h_l * 0.12))
            p.setBrush(QColor("#EEEEEE"))
            p.setPen(QPen(QColor("#CCCCCC"), 1))
            p.drawRect(cup_x_l - top_ex, cup_y_top, lap_w, lap_h)
            p.drawRect(cup_x_l + cup_w_l + top_ex - lap_w, cup_y_top, lap_w, lap_h)

        p.restore()


# ---------------------------------------------------------------------------
# Pinball (Steely) drawing widget
# ---------------------------------------------------------------------------
class _PinballDrawWidget(_TrophieDrawWidget):
    """Draws Steely the pinball mascot — a metallic chrome sphere."""

    # Steely-specific passive modes — distinct from Trophie's list
    _PASSIVE_MODES = [
        "float", "pulse", "shimmer", "wobble", "bounce", "eye_roll",
        "roll", "vibrate", "zigzag", "orbit", "sparkle", "nod",
    ]

    # Use different timer ranges from base class so the two mascots desynchronize
    _PASSIVE_MODE_MIN_MS = 6000
    _PASSIVE_MODE_MAX_MS = 15000

    def _tick(self) -> None:
        super()._tick()
        dt = 0.016
        if self._state == IDLE:
            mode = self._passive_mode
            if mode == "roll":
                # Gentle continuous roll — updates angle used in paintEvent
                self._passive_angle = (self._passive_angle + dt * 30.0) % 360.0
                self._passive_extra_x = 0.0
                self._passive_extra_y = 0.0
            elif mode == "vibrate":
                # Rapid small jitter in both X and Y
                self._passive_extra_x = random.uniform(-3.0, 3.0)
                self._passive_extra_y = random.uniform(-2.0, 2.0)
                self._passive_angle = 0.0
            elif mode == "zigzag":
                # Horizontal zigzag/wave pattern
                cycle = (self._passive_t * 0.8) % 1.0
                self._passive_extra_x = ((cycle / 0.5) * 12.0 - 6.0) if cycle < 0.5 \
                    else (((1.0 - cycle) / 0.5) * 12.0 - 6.0)
                self._passive_extra_y = 0.0
                self._passive_angle = 0.0
            elif mode == "orbit":
                # Small elliptical orbit around the rest position
                self._passive_extra_x = math.cos(self._passive_t * 1.2) * 8.0
                self._passive_extra_y = math.sin(self._passive_t * 1.2) * 5.0
                self._passive_angle = 0.0
            else:
                self._passive_extra_x = 0.0
                self._passive_extra_y = 0.0
                self._passive_angle = 0.0
        else:
            self._passive_extra_x = 0.0
            self._passive_extra_y = 0.0
            self._passive_angle = 0.0

    def _draw_shimmer(self, p: QPainter) -> None:
        """Silver shimmer sweep across the pinball."""
        sweep_speed = 1.2
        sweep_pos = (self._passive_t * sweep_speed) % 2.0
        if sweep_pos > 1.0:
            return
        tw = self._tw
        th = self._th
        sweep_x = int((sweep_pos - 0.2) * (tw + 40)) - 20
        sweep_w = max(12, int(tw * 0.25))
        grad = QLinearGradient(float(sweep_x), 0.0, float(sweep_x + sweep_w), float(th))
        grad.setColorAt(0.0, QColor(220, 220, 240, 0))
        grad.setColorAt(0.3, QColor(220, 220, 240, 70))
        grad.setColorAt(0.5, QColor(240, 240, 255, 110))
        grad.setColorAt(0.7, QColor(220, 220, 240, 70))
        grad.setColorAt(1.0, QColor(220, 220, 240, 0))
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRect(sweep_x, 0, sweep_w, th)
        p.restore()

    def _draw_trophy(self, p: QPainter, cx: int, cy: int) -> None:
        """Draw Steely as a metallic chrome pinball with eyes and handlebar mustache."""
        # Apply skin-based gradient overrides
        skin = getattr(self, "_skin", "classic")
        self._draw_trophy_pinball(p, cx, cy, skin)

    def _draw_trophy_pinball(self, p: QPainter, cx: int, cy: int, skin: str) -> None:
        """Core Steely drawing with optional skin-based gradient."""
        tw = self._tw
        th = self._th

        radius = int(min(tw, th) * 0.38)

        # ── Metallic sphere body ─────────────────────────────────────────────
        # Choose colors based on skin
        if skin in ("gold", "gold_ball"):
            c0, c1, c2, c3, c4 = "#FFFACD", "#FFD700", "#DAA520", "#B8860B", "#705000"
            pen_color = "#8B6914"
        elif skin == "chrome":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#F0F0FF", "#C8C8D8", "#8888A0", "#404050"
            pen_color = "#606070"
        elif skin == "fireball":
            c0, c1, c2, c3, c4 = "#FFFF80", "#FF8800", "#CC3300", "#880000", "#330000"
            pen_color = "#660000"
        elif skin == "iceball":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#D0F0FF", "#80C8FF", "#4090D0", "#1050A0"
            pen_color = "#2060B0"
        elif skin == "marble":
            c0, c1, c2, c3, c4 = "#EE88FF", "#AA44CC", "#7711AA", "#440088", "#220044"
            pen_color = "#330066"
        elif skin == "rubber":
            c0, c1, c2, c3, c4 = "#555555", "#333333", "#222222", "#111111", "#000000"
            pen_color = "#444444"
        elif skin == "soccer":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#F8F8F8", "#EBEBEB", "#D0D0D0", "#B0B0B0"
            pen_color = "#888888"
        elif skin == "basketball":
            c0, c1, c2, c3, c4 = "#FF9944", "#FF6600", "#CC4400", "#882200", "#441100"
            pen_color = "#662200"
        elif skin == "baseball":
            c0, c1, c2, c3, c4 = "#FFFEF0", "#F5F0DC", "#E8DCC8", "#C8B090", "#907060"
            pen_color = "#806050"
        elif skin == "tennis":
            c0, c1, c2, c3, c4 = "#FFFF88", "#CCDD00", "#AACC00", "#669900", "#446600"
            pen_color = "#557700"
        elif skin == "bowling":
            c0, c1, c2, c3, c4 = "#6080C0", "#304090", "#182060", "#0C1040", "#060818"
            pen_color = "#101828"
        elif skin == "beach":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#FFFFC0", "#FFE880", "#EEC860", "#CCA040"
            pen_color = "#AA8030"
        elif skin == "camo":
            c0, c1, c2, c3, c4 = "#8B9B5B", "#6B7B3B", "#4B5B2B", "#2B3B1B", "#1B2B0B"
            pen_color = "#384820"
        elif skin == "pixel":
            c0, c1, c2, c3, c4 = "#FF80FF", "#CC00CC", "#880088", "#440044", "#220022"
            pen_color = "#660066"
        elif skin == "galaxy":
            c0, c1, c2, c3, c4 = "#8040C0", "#4820A0", "#281070", "#180840", "#0C0420"
            pen_color = "#301060"
        elif skin == "disco":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#F8F8FF", "#D8D8F8", "#B0B0D8", "#6868A0"
            pen_color = "#8080B0"
        elif skin == "moon":
            c0, c1, c2, c3, c4 = "#C0C0C0", "#909090", "#606060", "#363636", "#1C1C1C"
            pen_color = "#404040"
        elif skin == "planet":
            c0, c1, c2, c3, c4 = "#F0E080", "#D4A840", "#B08020", "#785010", "#3C2808"
            pen_color = "#604018"
        elif skin == "skull":
            c0, c1, c2, c3, c4 = "#484848", "#282828", "#181818", "#0C0C0C", "#040404"
            pen_color = "#303030"
        elif skin == "eyeball":
            c0, c1, c2, c3, c4 = "#FFFFFF", "#FAFAFA", "#F0F0F0", "#E0E0E0", "#C8C8C8"
            pen_color = "#B0B0B0"
        elif skin == "8ball":
            c0, c1, c2, c3, c4 = "#404040", "#202020", "#101010", "#080808", "#020202"
            pen_color = "#303030"
        else:
            c0, c1, c2, c3, c4 = "#FFFFFF", "#E8E8F0", "#A0A8B8", "#606880", "#303040"
            pen_color = "#404050"

        grad = QRadialGradient(float(cx - radius // 4), float(cy - radius // 3), float(radius * 1.4))
        grad.setColorAt(0.0,  QColor(c0))
        grad.setColorAt(0.15, QColor(c1))
        grad.setColorAt(0.45, QColor(c2))
        grad.setColorAt(0.75, QColor(c3))
        grad.setColorAt(1.0,  QColor(c4))
        p.setBrush(grad)
        p.setPen(QPen(QColor(pen_color), 2))
        p.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # ── Specular highlight (small bright spot top-left) ──────────────────
        hl_r = max(3, radius // 4)
        hl_x = cx - radius // 3
        hl_y = cy - radius // 2
        hl_grad = QRadialGradient(float(hl_x), float(hl_y), float(hl_r * 1.5))
        hl_grad.setColorAt(0.0, QColor(255, 255, 255, 220))
        hl_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hl_grad)
        p.drawEllipse(hl_x - hl_r, hl_y - hl_r, hl_r * 2, hl_r * 2)

        # Secondary soft highlight (lower right)
        hl2_r = max(2, radius // 5)
        hl2_x = cx + radius // 3
        hl2_y = cy + radius // 3
        hl2_grad = QRadialGradient(float(hl2_x), float(hl2_y), float(hl2_r * 2))
        hl2_grad.setColorAt(0.0, QColor(180, 200, 255, 80))
        hl2_grad.setColorAt(1.0, QColor(180, 200, 255, 0))
        p.setBrush(hl2_grad)
        p.drawEllipse(hl2_x - hl2_r, hl2_y - hl2_r, hl2_r * 2, hl2_r * 2)

        # ── Eyes ─────────────────────────────────────────────────────────────
        eye_y = cy - radius // 5
        eye_r = max(4, int(tw * 0.08))
        left_eye_x = cx - int(tw * 0.12)
        right_eye_x = cx + int(tw * 0.12)

        for ex in (left_eye_x, right_eye_x):
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor("#333333"), 1))
            if self._blink or self._state == SLEEPY:
                blink_h = eye_r if self._eye_half else 2
                p.drawEllipse(ex - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2)
                p.setBrush(QColor("#8090A8"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(ex - eye_r - 1, eye_y - eye_r - 1, eye_r * 2 + 2, blink_h + 2)
            else:
                p.drawEllipse(ex - eye_r, eye_y - eye_r, eye_r * 2, eye_r * 2)

            if not self._blink:
                pr = max(2, int(eye_r * 0.55))
                if self._state == SURPRISED:
                    pr = eye_r - 1
                px = ex + self._pupil_dx
                py = eye_y + self._pupil_dy
                p.setBrush(QColor("#111111"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(px - pr, py - pr, pr * 2, pr * 2)
                # Eye shine
                p.setBrush(QColor("#FFFFFF"))
                shine_r = max(1, pr // 3)
                p.drawEllipse(px - pr // 3, py - pr // 3, shine_r, shine_r)

        # ── Handlebar mustache ────────────────────────────────────────────────
        mst_y = eye_y + eye_r + 3
        mst_cx = cx
        mst_w = int(tw * 0.34)
        mst_h = int(tw * 0.12)

        p.setPen(QPen(QColor("#1A1A1A"), 2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor("#1A1A1A"))

        # Left side of mustache (curls left and up)
        left_mst = QPainterPath()
        left_mst.moveTo(mst_cx, mst_y)
        left_mst.cubicTo(
            mst_cx - mst_w * 0.3, mst_y + mst_h * 0.8,
            mst_cx - mst_w * 0.7, mst_y + mst_h * 1.0,
            mst_cx - mst_w * 0.5, mst_y - mst_h * 0.3
        )
        left_mst.cubicTo(
            mst_cx - mst_w * 0.4, mst_y - mst_h * 0.7,
            mst_cx - mst_w * 0.1, mst_y + mst_h * 0.1,
            mst_cx, mst_y
        )
        p.fillPath(left_mst, QColor("#1A1A1A"))
        p.drawPath(left_mst)

        # Right side of mustache (mirror)
        right_mst = QPainterPath()
        right_mst.moveTo(mst_cx, mst_y)
        right_mst.cubicTo(
            mst_cx + mst_w * 0.3, mst_y + mst_h * 0.8,
            mst_cx + mst_w * 0.7, mst_y + mst_h * 1.0,
            mst_cx + mst_w * 0.5, mst_y - mst_h * 0.3
        )
        right_mst.cubicTo(
            mst_cx + mst_w * 0.4, mst_y - mst_h * 0.7,
            mst_cx + mst_w * 0.1, mst_y + mst_h * 0.1,
            mst_cx, mst_y
        )
        p.fillPath(right_mst, QColor("#1A1A1A"))
        p.drawPath(right_mst)

    def _steely_safe_clip(self, cx: int, cy: int) -> QPainterPath:
        """Return the ball circle path minus the face exclusion zone.

        Used by surface overlay skins so they don't paint over Steely's
        eyes and mustache.
        """
        tw = self._tw
        th = self._th
        radius = int(min(tw, th) * 0.38)
        eye_y = cy - radius // 5
        eye_r = max(4, int(tw * 0.08))
        mst_w = int(tw * 0.34)
        mst_h = int(tw * 0.12)
        mst_y = eye_y + eye_r + 3
        fm = eye_r + 4
        ball = QPainterPath()
        ball.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        face = QPainterPath()
        face.addRect(QRectF(
            cx - mst_w // 2 - fm,
            eye_y - eye_r - fm,
            mst_w + fm * 2,
            mst_y + mst_h + fm - (eye_y - eye_r - fm),
        ))
        return ball.subtracted(face)

    def _draw_skin_accessory(self, p: QPainter, cx: int, cy: int) -> None:
        """Draw Steely skin-specific surface decorations."""
        skin = getattr(self, "_skin", "classic")
        if skin in ("classic", "chrome", "gold", "gold_ball", "fireball",
                    "iceball", "marble", "rubber"):
            # These are handled purely by gradient — no extra overlay needed
            return
        tw = self._tw
        th = self._th
        radius = int(min(tw, th) * 0.38)
        # Face zone coordinates — shared by multiple skins for exclusion logic
        eye_y = cy - radius // 5
        eye_r = max(4, int(tw * 0.08))
        mst_w = int(tw * 0.34)
        mst_h = int(tw * 0.12)
        mst_y = eye_y + eye_r + 3

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if skin == "8ball":
            # White circle with "8" — shifted to lower half so it doesn't cover the eyes
            cr = int(radius * 0.38)
            cy_8 = cy + int(radius * 0.18)
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - cr, cy_8 - cr, cr * 2, cr * 2)
            p.setPen(QPen(QColor("#111111"), 1))
            p.setFont(QFont("Arial", max(6, cr - 2), QFont.Weight.Bold))
            p.drawText(cx - cr, cy_8 - cr, cr * 2, cr * 2,
                       Qt.AlignmentFlag.AlignCenter, "8")

        elif skin == "soccer":
            # Pentagon patches — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setBrush(QColor("#111111"))
            p.setPen(Qt.PenStyle.NoPen)
            for angle_deg in [0, 72, 144, 216, 288]:
                a = math.radians(angle_deg)
                px2 = cx + int(math.cos(a) * radius * 0.5)
                py2 = cy + int(math.sin(a) * radius * 0.5)
                pr = int(radius * 0.22)
                p.drawEllipse(px2 - pr, py2 - pr, pr * 2, pr * 2)
            p.restore()

        elif skin == "basketball":
            # Seam lines — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setPen(QPen(QColor(60, 20, 0, 220), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(cx, cy - radius, cx, cy + radius)
            p.drawArc(cx - radius, cy - radius // 2, radius * 2, radius, 0, 180 * 16)
            p.drawArc(cx - radius, cy - radius // 2, radius * 2, radius, 180 * 16, 180 * 16)
            p.restore()

        elif skin == "baseball":
            # Red stitching — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setPen(QPen(QColor("#CC0000"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for x_off in [-radius // 4, radius // 4]:
                p.drawArc(cx + x_off - radius // 3, cy - radius // 2,
                           radius * 2 // 3, radius,
                           30 * 16, 120 * 16)
            p.restore()

        elif skin == "tennis":
            # White seam curves — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setPen(QPen(QColor("#FFFFFF"), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(cx - radius, cy - radius, radius * 2, radius * 2,
                      45 * 16, 90 * 16)
            p.drawArc(cx - radius, cy - radius, radius * 2, radius * 2,
                      225 * 16, 90 * 16)
            p.restore()

        elif skin == "bowling":
            # Three finger holes — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setBrush(QColor("#333333"))
            p.setPen(Qt.PenStyle.NoPen)
            hr = max(3, int(radius * 0.15))
            for hx2, hy2 in [(cx, cy - int(radius * 0.3)),
                             (cx - int(radius * 0.25), cy + int(radius * 0.1)),
                             (cx + int(radius * 0.25), cy + int(radius * 0.1))]:
                p.drawEllipse(hx2 - hr, hy2 - hr, hr * 2, hr * 2)
            p.restore()

        elif skin == "eyeball":
            # Big iris centred in the lower half of the ball so it clears the eyes
            iris_cy = cy + int(radius * 0.20)
            iris_r = int(radius * 0.50)
            p.setBrush(QColor("#44AAFF"))
            p.setPen(QPen(QColor("#2277CC"), 1))
            p.drawEllipse(cx - iris_r, iris_cy - iris_r, iris_r * 2, iris_r * 2)
            p.setBrush(QColor("#111111"))
            p.setPen(Qt.PenStyle.NoPen)
            pr = int(iris_r * 0.55)
            p.drawEllipse(cx - pr, iris_cy - pr, pr * 2, pr * 2)
            p.setBrush(QColor("#FFFFFF"))
            shine_r = max(2, pr // 3)
            p.drawEllipse(cx - pr // 3, iris_cy - pr // 3, shine_r, shine_r)

        elif skin == "disco":
            # Tiled mirror squares — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            sq = max(4, int(radius * 0.18))
            colors = [QColor("#FF88FF"), QColor("#88FFFF"), QColor("#FFFF88"),
                      QColor("#FF8888"), QColor("#88FF88")]
            ci = 0
            for row in range(-2, 3):
                for col in range(-2, 3):
                    sx2 = cx + col * (sq + 1) - sq // 2
                    sy2 = cy + row * (sq + 1) - sq // 2
                    dist = math.sqrt((sx2 - cx) ** 2 + (sy2 - cy) ** 2)
                    if dist < radius * 0.85:
                        p.setBrush(colors[ci % len(colors)])
                        p.setPen(Qt.PenStyle.NoPen)
                        p.drawRect(sx2, sy2, sq, sq)
                        ci += 1
            p.restore()

        elif skin == "planet":
            # Saturn-like ring around the ball — doesn't cover the face
            p.setPen(QPen(QColor("#DAA520"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            ring_rx = int(radius * 1.4)
            ring_ry = int(radius * 0.35)
            p.drawEllipse(cx - ring_rx, cy - ring_ry, ring_rx * 2, ring_ry * 2)

        elif skin == "moon":
            # Crescent shadow — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setBrush(QColor(30, 30, 60, 160))
            p.setPen(Qt.PenStyle.NoPen)
            off = int(radius * 0.35)
            p.drawEllipse(cx + off - radius, cy - radius, radius * 2, radius * 2)
            p.restore()

        elif skin == "skull":
            # Skull shifted to lower half of ball so it clears Steely's face
            skull_cy = cy + int(radius * 0.18)
            sr = int(radius * 0.35)
            p.setBrush(QColor(255, 255, 255, 200))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - sr, skull_cy - sr, sr * 2, sr * 2)
            p.setBrush(QColor("#111111"))
            eye_off = int(sr * 0.38)
            er = max(2, int(sr * 0.25))
            p.drawEllipse(cx - eye_off - er, skull_cy - er, er * 2, er * 2)
            p.drawEllipse(cx + eye_off - er, skull_cy - er, er * 2, er * 2)
            p.setPen(QPen(QColor("#111111"), 1))
            for i in range(4):
                tx2 = cx - int(sr * 0.4) + i * int(sr * 0.28)
                p.drawLine(tx2, skull_cy + int(sr * 0.35), tx2, skull_cy + int(sr * 0.6))

        elif skin == "beach":
            # Colored vertical stripes — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            colors_b = [QColor("#FF4444"), QColor("#FFFF44"), QColor("#4444FF")]
            stripe_w = int(radius * 0.35)
            for i, col in enumerate(colors_b):
                x2 = cx - stripe_w * len(colors_b) // 2 + i * stripe_w
                p.setBrush(col)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(x2, cy - radius, stripe_w, radius * 2)
            p.restore()

        elif skin == "camo":
            # Camo blobs — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            camo_colors = [QColor(60, 80, 40, 160), QColor(40, 60, 20, 140),
                           QColor(80, 70, 30, 120)]
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(6):
                bx2 = cx + int((i - 3) * radius * 0.3)
                by2 = cy + int(((i % 3) - 1) * radius * 0.3)
                br = int(radius * 0.22)
                p.setBrush(camo_colors[i % len(camo_colors)])
                p.drawEllipse(bx2 - br, by2 - br, br * 2, br * 2)
            p.restore()

        elif skin == "pixel":
            # Pixel grid — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            pix = max(4, int(radius * 0.22))
            colors_px = [QColor("#FF00FF"), QColor("#00FFFF"), QColor("#FFFF00")]
            p.setPen(Qt.PenStyle.NoPen)
            for row in range(-2, 3):
                for col in range(-2, 3):
                    px2 = cx + col * pix - pix // 2
                    py2 = cy + row * pix - pix // 2
                    dist = math.sqrt((px2 + pix // 2 - cx) ** 2 + (py2 + pix // 2 - cy) ** 2)
                    if dist < radius * 0.8:
                        p.setBrush(colors_px[(row + col) % len(colors_px)])
                        p.drawRect(px2, py2, pix - 1, pix - 1)
            p.restore()

        elif skin == "galaxy":
            # Star dots — face area excluded via clip
            safe = self._steely_safe_clip(cx, cy)
            p.save()
            p.setClipPath(safe)
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(8):
                a2 = math.radians(i * 45 + 22)
                sx3 = cx + int(math.cos(a2) * radius * 0.6)
                sy3 = cy + int(math.sin(a2) * radius * 0.6)
                p.drawEllipse(sx3 - 2, sy3 - 2, 4, 4)
            p.restore()

        # ── Clothing / wearable skins ─────────────────────────────────────────
        elif skin == "scarf":
            # Knitted scarf wrapped below the mustache
            scarf_top = mst_y + mst_h + 6
            scarf_colors = [QColor("#CC3300"), QColor("#FF6600"), QColor("#FFCC00"),
                            QColor("#CC3300"), QColor("#FF6600")]
            band_h = max(3, int(radius * 0.13))
            p.setPen(Qt.PenStyle.NoPen)
            for i, col in enumerate(scarf_colors):
                by2 = scarf_top + i * band_h
                mid_y2 = by2 + band_h // 2
                dy2 = abs(mid_y2 - cy)
                if dy2 >= radius:
                    break
                hw2 = int(math.sqrt(max(0, radius * radius - dy2 * dy2)))
                p.setBrush(col)
                p.drawRect(cx - hw2, by2, hw2 * 2, band_h)
            # Dangling scarf tail on the right
            tail_start_y = scarf_top + band_h
            tail_x = cx + int(radius * 0.60)
            if abs(tail_start_y - cy) < radius:
                tail_w = max(4, int(radius * 0.18))
                tail_h = int(radius * 0.50)
                p.setBrush(QColor("#CC3300"))
                p.drawRect(tail_x, tail_start_y, tail_w, tail_h)
                # Tassel fringe
                p.setBrush(QColor("#FFD700"))
                for ti in range(3):
                    tx3 = tail_x + ti * max(1, tail_w // 3)
                    p.drawRect(tx3, tail_start_y + tail_h,
                               max(2, tail_w // 3 - 1), int(radius * 0.10))

        elif skin == "bow_tie":
            # Small bow tie just below the mustache
            bt_cx = cx
            bt_cy = mst_y + mst_h + max(6, int(radius * 0.14))
            bt_w = max(7, int(tw * 0.14))
            bt_h = max(3, int(tw * 0.07))
            bow_l = QPainterPath()
            bow_l.moveTo(float(bt_cx - bt_w), float(bt_cy - bt_h))
            bow_l.lineTo(float(bt_cx), float(bt_cy))
            bow_l.lineTo(float(bt_cx - bt_w), float(bt_cy + bt_h))
            bow_l.closeSubpath()
            p.fillPath(bow_l, QColor("#CC0044"))
            p.strokePath(bow_l, QPen(QColor("#880033"), 1))
            bow_r = QPainterPath()
            bow_r.moveTo(float(bt_cx + bt_w), float(bt_cy - bt_h))
            bow_r.lineTo(float(bt_cx), float(bt_cy))
            bow_r.lineTo(float(bt_cx + bt_w), float(bt_cy + bt_h))
            bow_r.closeSubpath()
            p.fillPath(bow_r, QColor("#CC0044"))
            p.strokePath(bow_r, QPen(QColor("#880033"), 1))
            # Center knot
            p.setBrush(QColor("#990033"))
            p.setPen(Qt.PenStyle.NoPen)
            knot_r = max(2, bt_h // 2)
            p.drawEllipse(bt_cx - knot_r, bt_cy - knot_r, knot_r * 2, knot_r * 2)

        elif skin == "bandana":
            # Red bandana capping the very top of the ball (above face zone)
            ban_h = int(radius * 0.30)
            ban_bot = cy - radius + ban_h
            # Clip to the top cap of the ball
            ban_path = QPainterPath()
            ban_path.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            cut_path = QPainterPath()
            cut_path.addRect(QRectF(float(cx - radius - 2), float(ban_bot),
                                    float(radius * 2 + 4), float(radius * 2)))
            top_cap = ban_path.subtracted(cut_path)
            p.setBrush(QColor("#CC2200"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(top_cap)
            # White polka dots on bandana
            p.setBrush(QColor(255, 255, 255, 140))
            dr = radius - ban_h // 2
            for angle_deg in [200, 240, 270, 300, 340]:
                a3 = math.radians(angle_deg)
                dx3 = cx + int(math.cos(a3) * dr * 0.55)
                dy3 = cy + int(math.sin(a3) * dr * 0.65)
                if dy3 <= ban_bot:
                    p.drawEllipse(dx3 - 2, dy3 - 2, 4, 4)
            # Knot at upper-left with short tails
            kx = cx - int(radius * 0.62)
            ky = cy - int(radius * 0.78)
            p.setBrush(QColor("#991100"))
            p.setPen(QPen(QColor("#661100"), 1))
            p.drawEllipse(kx - 5, ky - 4, 10, 8)
            p.setPen(QPen(QColor("#CC2200"), 2))
            p.drawLine(kx, ky - 4, kx - 7, ky - 11)
            p.drawLine(kx, ky + 4, kx - 9, ky + 9)

        elif skin == "monocle":
            # Gold monocle ring on the right eye with a chain hanging down.
            # Intentionally overlaps that eye — the glass is part of the look.
            r_eye_x = cx + int(tw * 0.12)
            mono_r = eye_r + 4
            # Subtle glass tint
            p.setBrush(QColor(200, 230, 255, 50))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(r_eye_x - mono_r + 2, eye_y - mono_r + 2,
                          mono_r * 2 - 4, mono_r * 2 - 4)
            # Gold frame
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#DAA520"), 2))
            p.drawEllipse(r_eye_x - mono_r, eye_y - mono_r, mono_r * 2, mono_r * 2)
            # Chain from bottom-right of monocle to lower-right of ball
            chain_x1 = r_eye_x + int(mono_r * 0.7)
            chain_y1 = eye_y + int(mono_r * 0.7)
            chain_x2 = cx + int(radius * 0.60)
            chain_y2 = cy + int(radius * 0.45)
            p.setPen(QPen(QColor("#DAA520"), 1, Qt.PenStyle.DotLine))
            p.drawLine(chain_x1, chain_y1, chain_x2, chain_y2)

        elif skin == "headphones":
            # Headphones arching over the top with ear cups on the sides
            arc_r = int(radius * 1.05)
            band_w = max(3, int(radius * 0.10))
            # Headband arc (upper semicircle)
            p.setPen(QPen(QColor("#2A2A2A"), band_w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2,
                      10 * 16, 160 * 16)
            # Left ear cup
            ec_r = max(5, int(radius * 0.26))
            lec_x = cx - arc_r
            lec_y = cy - int(radius * 0.08)
            p.setBrush(QColor("#1A1A1A"))
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawEllipse(lec_x - ec_r, lec_y - ec_r, ec_r * 2, ec_r * 2)
            p.setBrush(QColor("#444444"))
            p.setPen(Qt.PenStyle.NoPen)
            pad_r = max(3, int(ec_r * 0.65))
            p.drawEllipse(lec_x - pad_r, lec_y - pad_r, pad_r * 2, pad_r * 2)
            # Right ear cup
            rec_x = cx + arc_r
            rec_y = lec_y
            p.setBrush(QColor("#1A1A1A"))
            p.setPen(QPen(QColor("#333333"), 1))
            p.drawEllipse(rec_x - ec_r, rec_y - ec_r, ec_r * 2, ec_r * 2)
            p.setBrush(QColor("#444444"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(rec_x - pad_r, rec_y - pad_r, pad_r * 2, pad_r * 2)

        p.restore()


# ---------------------------------------------------------------------------
# GUI Trophie
# ---------------------------------------------------------------------------
class GUITrophie(QWidget):
    """Trophie mascot that lives in the bottom-left corner of the main window."""

    _TROPHY_W = 60
    _TROPHY_H = 70
    _MARGIN = 8

    _TROPHIE_GREETINGS = [
        "Hey! I am Trophie! Welcome back!",
        "Trophie reporting for duty! Let's chase some achievements!",
        "Hello there! Ready to track your progress today?",
        "Welcome back, champion! I have been keeping score!",
        "Trophie online! Your achievement journey continues!",
    ]

    def __init__(self, central_widget, cfg) -> None:
        """central_widget is the MainWindow's centralWidget() (the QTabWidget)."""
        super().__init__(central_widget)
        self._cfg = cfg
        # centralWidget is the QTabWidget — used for position/size reference
        self._central = central_widget
        self._memory: Optional[_TrophieMemory] = None  # set via set_memory()
        self._silenced_until = 0.0
        self._last_interaction = time.time()
        self._idle_notified_5m = False
        self._idle_notified_10m = False
        self._current_bubble: Optional[_SpeechBubble] = None
        self._current_tab = ""
        self._greeted = False

        # Draw widget
        self._draw = _TrophieDrawWidget(self, self._TROPHY_W, self._TROPHY_H)
        self._draw.move(0, 0)
        self._draw.set_skin(cfg.OVERLAY.get("trophie_gui_skin", "classic"))

        self.setFixedSize(self._TROPHY_W, self._TROPHY_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.raise_()

        # Idle timer (checks every 30s)
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(30_000)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start()

        # Random personality timer
        self._rand_timer = QTimer(self)
        self._rand_timer.setSingleShot(True)
        self._rand_timer.timeout.connect(self._fire_random)
        self._schedule_random()

        # Zank cooldown tick
        self._zank_tick = QTimer(self)
        self._zank_tick.setInterval(1000)
        self._zank_tick.timeout.connect(self._zank_tick_fn)
        self._zank_tick.start()

        # Spontaneous idle bicker timer (checks every 30s whether the cooldown has elapsed)
        self._idle_bicker_timer = QTimer(self)
        self._idle_bicker_timer.setInterval(30_000)
        self._idle_bicker_timer.timeout.connect(self._try_idle_bicker)
        self._idle_bicker_timer.start()

    def set_memory(self, mem: _TrophieMemory) -> None:
        self._memory = mem

    def set_skin(self, skin_id: str) -> None:
        """Apply a visual skin to the GUI Trophie mascot."""
        self._draw.set_skin(skin_id)

    def greet(self) -> None:
        if self._greeted:
            return
        self._greeted = True
        self._draw.set_state(HAPPY)
        self._show_comment(random.choice(self._TROPHIE_GREETINGS), HAPPY)

    def re_greet(self) -> None:
        """Reset the greeted flag and show a fresh greeting (e.g. when restoring from tray)."""
        self._greeted = False
        self.greet()

    def on_tab_changed(self, idx: int) -> None:
        try:
            # self._central is the QTabWidget (centralWidget)
            tab_name = self._central.tabText(idx).lower()
            self._current_tab = tab_name
            if self._memory:
                self._memory.tab_visits[tab_name] = self._memory.tab_visits.get(tab_name, 0) + 1
        except Exception:
            return
        self._last_interaction = time.time()
        self._fire_tab_tip(tab_name)

    def on_subtab_changed(self, tab_name: str) -> None:
        """Called when the user switches to a sub-tab; tab_name is the sub-tab label text."""
        self._last_interaction = time.time()
        self._fire_tab_tip(tab_name.lower())

    def on_achievement(self) -> None:
        self._last_interaction = time.time()
        self._draw.set_state(HAPPY)
        # Decide: zank or event tip
        if self._try_zank("achievement"):
            return
        if self._memory:
            if self._memory.achievement_sessions == 0:
                self._show_comment_key("evt_first_ach", "Your first achievement! The hunt begins!", HAPPY)
                return
        self._show_comment_key("evt_ach_unlocked", "Achievement unlocked! You are on your way!", HAPPY)

    def on_level_up(self) -> None:
        self._last_interaction = time.time()
        self._try_zank("level_up")

    def on_low_perf_enabled(self) -> None:
        self._show_comment_key("evt_lowperf_on", "Good call! Low Performance Mode saves a lot of CPU.", HAPPY)

    def on_theme_changed(self) -> None:
        self._show_comment_key("evt_new_theme", "Nice theme choice! Try enabling Bloom for the full effect!", HAPPY)

    def on_postproc_enabled(self) -> None:
        self._show_comment_key("evt_postproc_on", "Post-Processing is on! Looks amazing, right?", HAPPY)

    def on_cloud_enabled(self) -> None:
        self._show_comment_key("evt_cloud_on", "Cloud Sync is on! Your achievements are safe now.", HAPPY)

    def _fire_tab_tip(self, tab_name: str) -> None:
        tab_map = {
            "dashboard":        "tab_dashboard",
            "effects":          "tab_effects",
            "overlay":          "tab_overlay",
            "theme":            "tab_theme",
            "sound":            "tab_sound",
            "appearance":       "tab_appearance",
            "mascots":          "tab_mascots",
            "controls":         "tab_controls",
            "progress":         "tab_progress",
            "cloud":            "tab_cloud",
            "general":          "tab_general",
            "maintenance":      "tab_maintenance",
            "system":           "tab_system",
            "player":           "tab_player",
            "records":          "tab_records",
            "stats":            "tab_records",
            "aweditor":         "tab_aweditor",
            "available maps":   "tab_maps",
            "maps":             "tab_maps",
        }
        for key_part, tip_cat in tab_map.items():
            if key_part in tab_name:
                tips = list(_GUI_TIPS.get(tip_cat, []))
                # Build dynamic controls tip if needed
                if tip_cat == "tab_controls":
                    dyn = self._build_controls_tip()
                    tips = [(k, t) if k != "ctrl_hotkey" else ("ctrl_hotkey", dyn) for k, t in tips]
                    tips = [(k, t) for k, t in tips if t]
                if tips and self._memory:
                    tip = self._memory.pick_unseen(tips)
                    if tip:
                        self._show_comment_key(tip[0], tip[1], TALKING)
                elif tips:
                    tip = random.choice(tips)
                    self._show_comment_key(tip[0], tip[1], TALKING)
                break

    def _build_controls_tip(self) -> Optional[str]:
        try:
            src = self._cfg.OVERLAY.get("toggle_input_source", "keyboard")
            vk = self._cfg.OVERLAY.get("toggle_vk", 120)
            if src == "keyboard":
                from input_hook import vk_to_name_en
                key_name = vk_to_name_en(int(vk))
            else:
                key_name = f"Joy btn {vk}"
            return f"Your current overlay toggle is: {key_name}. You can change it here!"
        except Exception:
            return None

    def _check_idle(self) -> None:
        elapsed = time.time() - self._last_interaction
        if elapsed >= 600 and not self._idle_notified_10m:
            self._idle_notified_10m = True
            self._draw.set_state(SLEEPY)
            self._show_comment_key("idle_10m", "ZZZ...", SLEEPY)
        elif elapsed >= 300 and not self._idle_notified_5m:
            self._idle_notified_5m = True
            self._show_comment_key("idle_5m", "Still there? I am here if you need help!", IDLE)
        if elapsed < 300:
            self._idle_notified_5m = False
            self._idle_notified_10m = False
            if self._draw._state == SLEEPY:
                self._draw.set_state(IDLE)

    def _schedule_random(self) -> None:
        base_ms = random.randint(3 * 60_000, 6 * 60_000)
        mult = self._memory.comment_frequency_multiplier() if self._memory else 1.0
        self._rand_timer.start(int(base_ms / max(0.1, mult)))

    def _fire_random(self) -> None:
        self._schedule_random()
        if self._is_silenced():
            return
        # Occasionally do a zank comment if overlay is visible
        if _TROPHIE_SHARED["gui_visible"] and random.random() < 0.2:
            self._fire_zank_comment()
            return
        if self._memory:
            tip = self._memory.pick_unseen(_GUI_RANDOM)
            if tip:
                self._show_comment_key(tip[0], tip[1], IDLE)
        else:
            tip = random.choice(_GUI_RANDOM)
            self._show_comment_key(tip[0], tip[1], IDLE)

    def _fire_zank_comment(self) -> None:
        if self._memory:
            tip = self._memory.pick_unseen(_GUI_ZANK)
        else:
            tip = random.choice(_GUI_ZANK)
        if tip:
            self._show_comment_key(tip[0], tip[1], TALKING)

    def _try_zank(self, trigger: str) -> bool:
        """Attempt to fire a synchronized zank pair. Returns True if zank fired."""
        if not _TROPHIE_SHARED["gui_visible"]:
            return False
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            return False
        for trig, gui_key, ov_key in _ZANK_PAIRS:
            if trig == trigger:
                gui_options = _ZANK_GUI_LINES.get(gui_key, [])
                if gui_options:
                    self._show_comment(random.choice(gui_options), TALKING)
                # Signal overlay to respond in 2 seconds
                _TROPHIE_SHARED["zank_pending_overlay"] = ov_key
                _TROPHIE_SHARED["zank_cooldown_ms"] = _ZANK_COOLDOWN_MS
                return True
        return False

    def _try_idle_bicker(self) -> None:
        """Fire a spontaneous bicker exchange when both trophies are visible."""
        if not _TROPHIE_SHARED["gui_visible"]:
            return
        if _TROPHIE_SHARED["idle_bicker_cooldown_ms"] > 0:
            return
        if self._is_silenced():
            return
        (gui_key, gui_text), (ov_key, ov_text) = random.choice(_IDLE_BICKER_EXCHANGES)
        self._show_comment_key(gui_key, gui_text, TALKING)
        _TROPHIE_SHARED["idle_bicker_ov_key"] = ov_key
        _TROPHIE_SHARED["idle_bicker_ov_text"] = ov_text
        _TROPHIE_SHARED["idle_bicker_cooldown_ms"] = random.randint(
            _IDLE_BICKER_MIN_COOLDOWN_GUI_MS, _IDLE_BICKER_MAX_COOLDOWN_GUI_MS
        )

    def _zank_tick_fn(self) -> None:
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            _TROPHIE_SHARED["zank_cooldown_ms"] = max(0, _TROPHIE_SHARED["zank_cooldown_ms"] - 1000)
        if _TROPHIE_SHARED["idle_bicker_cooldown_ms"] > 0:
            _TROPHIE_SHARED["idle_bicker_cooldown_ms"] = max(
                0, _TROPHIE_SHARED["idle_bicker_cooldown_ms"] - 1000
            )
        # Check if overlay posted a pending gui zank response
        pending = _TROPHIE_SHARED.get("zank_pending_gui")
        if pending:
            _TROPHIE_SHARED["zank_pending_gui"] = None
            options = _ZANK_GUI_LINES.get(pending, [])
            if options:
                self._show_comment(random.choice(options), TALKING)

    def _is_silenced(self) -> bool:
        return time.time() < self._silenced_until

    def _show_comment(self, text: str, state: str = TALKING) -> None:
        if self._is_silenced():
            return
        self._dismiss_bubble()
        self._draw.set_state(state)
        bubble = _SpeechBubble(self._central, text, self._memory or _TrophieMemory.__new__(_TrophieMemory))
        bubble._owner = self  # so _do_dismiss can reliably reset our state
        self._current_bubble = bubble
        self._position_bubble(bubble)
        bubble.show()

    def _show_comment_key(self, key: str, text: str, state: str = TALKING) -> None:
        if self._memory:
            self._memory.seen_tips.add(key)
        self._show_comment(text, state)

    def _position_bubble(self, bubble: _SpeechBubble) -> None:
        try:
            bw = bubble.width()
            bh = bubble.height()
            # Place bubble just above the trophy cup top (not the widget top).
            # cy_base is shifted down by 15% to give accessories headroom, so the
            # cup top is at widget-y + (trophy_h/2 + trophy_h*0.15 - trophy_h*0.36).
            cup_top = self._TROPHY_H // 2 + int(self._TROPHY_H * 0.15) - int(self._TROPHY_H * 0.36)
            bx = max(0, self.x() + self._TROPHY_W // 2 - bw // 2)
            by_raw = self.y() + cup_top - bh - 7
            if by_raw < 0:
                by = self.y() + self._TROPHY_H + 4  # flip below
            else:
                by = by_raw
            # Clamp to central widget
            if bx + bw > self._central.width():
                bx = self._central.width() - bw - 4
            mascot_cx = self.x() + self._TROPHY_W // 2
            bubble.set_pointer_offset(mascot_cx - bx)
            bubble.move(bx, by)
        except Exception:
            pass

    def _dismiss_bubble(self) -> None:
        if self._current_bubble:
            try:
                self._current_bubble._auto_timer.stop()
                self._current_bubble._begin_fade_out()
            except Exception:
                pass
            self._current_bubble = None
        self._draw.set_state(IDLE)

    def _schedule_quiet_msg(self, msg: str) -> None:
        QTimer.singleShot(500, lambda: self._show_comment(msg, TALKING))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())
        else:
            self._last_interaction = time.time()
            self._dismiss_bubble()
            self._draw.set_state(HAPPY)

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        gpos = self.mapToGlobal(pos)
        menu.addAction("Dismiss", lambda: (self._dismiss_bubble(), self._show_action_toast(gpos)))
        menu.addAction("Silence for 10 minutes", lambda: (self._silence_10m(), self._show_action_toast(gpos)))
        menu.exec(gpos)

    def _show_action_toast(self, global_pos: QPoint) -> None:
        toast = _ActionToast(self._central)
        # Position above the trophie, centred horizontally
        cx = self.x() + self._TROPHY_W // 2
        ty = self.y() - toast.height() - 4
        if ty < 0:
            ty = self.y() + self._TROPHY_H + 4
        toast.popup(self._central.mapToGlobal(QPoint(cx - toast.width() // 2, ty)))

    def _silence_10m(self) -> None:
        self._silenced_until = time.time() + 600
        self._dismiss_bubble()

    def update_position(self, parent_size: QSize) -> None:
        x = self._MARGIN
        y = parent_size.height() - self._TROPHY_H - self._MARGIN
        self.move(x, y)
        self.raise_()


# ---------------------------------------------------------------------------
# Overlay Trophie
# ---------------------------------------------------------------------------
class OverlayTrophie(QWidget):
    """Standalone always-on-top desktop overlay Trophie widget."""

    _TROPHY_W = 80
    _TROPHY_H = 90
    _MARGIN = 20

    _STEELY_GREETINGS = [
        "Hey! I am Steely! Ready to watch your games!",
        "Steely here! The flippers are calling!",
        "Yo! Your favourite pinball is back on duty!",
        "Steely reporting in! Let's roll some high scores!",
        "The ball is back! Time for some serious pinball action!",
    ]

    def __init__(self, parent_window, cfg) -> None:
        super().__init__(None)
        self._cfg = cfg
        self._parent = parent_window
        self._memory: Optional[_TrophieMemory] = None
        self._silenced_until = 0.0
        self._greeted = False
        self._current_bubble: Optional[_SpeechBubble] = None

        self.setWindowTitle("Trophie")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(self._TROPHY_W, self._TROPHY_H)

        self._draw = _PinballDrawWidget(self, self._TROPHY_W, self._TROPHY_H)
        self._draw.move(0, 0)
        self._draw.set_skin(cfg.OVERLAY.get("trophie_overlay_skin", "classic"))

        # Apply portrait mode on startup
        self.apply_portrait_from_cfg()

        # Connect draw tick to trigger our paintEvent update in portrait mode
        self._draw.add_tick_listener(self.update)

        # Drag support
        self._drag_start: Optional[QPoint] = None
        self._drag_pos_start: Optional[QPoint] = None

        self._restore_position()

        # Idle tracker
        self._last_game_ts = time.time()
        self._idle_shown: dict = {}

        # Heat tracking
        self._last_heat = 0
        self._heat_notified_65 = False
        self._heat_notified_85 = False
        self._heat_notified_100 = False
        self._heat_zone_timer_ms = 0

        # Flip tracking
        self._flip_prev_pct = 0.0
        self._flip_notified: dict = {}

        # Session tracking
        self._session_start: Optional[float] = None
        self._session_rom: Optional[str] = None
        self._session_ach_count = 0
        self._today_ach_count = 0
        self._today_session_count = 0
        self._challenge_count_today = 0
        self._challenge_losses_streak = 0
        self._no_ach_sessions_streak = 0

        # Random personality timer
        self._rand_timer = QTimer(self)
        self._rand_timer.setSingleShot(True)
        self._rand_timer.timeout.connect(self._fire_random)
        self._schedule_random()

        # Idle check timer
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(60_000)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start()

        # Daytime comment timer (fires once per session at startup)
        QTimer.singleShot(5000, self._fire_daytime_comment)

        # Zank cooldown tick
        self._zank_tick = QTimer(self)
        self._zank_tick.setInterval(1000)
        self._zank_tick.timeout.connect(self._zank_tick_fn)
        self._zank_tick.start()

    def set_memory(self, mem: _TrophieMemory) -> None:
        self._memory = mem

    def set_skin(self, skin_id: str) -> None:
        """Apply a visual skin to the Steely overlay mascot."""
        self._draw.set_skin(skin_id)
        self.update()

    def greet(self) -> None:
        if self._greeted:
            return
        self._greeted = True
        self._draw.set_state(HAPPY)
        self._show_comment(random.choice(self._STEELY_GREETINGS), HAPPY)

    def apply_portrait_from_cfg(self) -> None:
        """Apply portrait/landscape mode based on current config."""
        ov = self._cfg.OVERLAY or {}
        portrait = bool(ov.get("trophie_overlay_portrait", False))
        if portrait:
            # Swap dimensions for portrait (rotated 90°)
            self.setFixedSize(self._TROPHY_H, self._TROPHY_W)
            self._draw.setVisible(False)
        else:
            self.setFixedSize(self._TROPHY_W, self._TROPHY_H)
            self._draw.setVisible(True)
        self.update()

    def paintEvent(self, event) -> None:
        ov = self._cfg.OVERLAY or {}
        portrait = bool(ov.get("trophie_overlay_portrait", False))
        if not portrait:
            super().paintEvent(event)
            return
        # Portrait mode: render _draw widget to offscreen image, rotate, then paint
        img = QImage(self._TROPHY_W, self._TROPHY_H, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        render_painter = QPainter(img)
        try:
            self._draw.render(render_painter, QPoint(0, 0))
        finally:
            render_painter.end()
        ccw = bool(ov.get("trophie_overlay_rotate_ccw", False))
        angle = -90 if ccw else 90
        img = img.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        painter = QPainter(self)
        try:
            painter.drawImage(0, 0, img)
        finally:
            painter.end()


    def on_rom_start(self, rom: str, table_name: Optional[str] = None) -> None:
        self._session_start = time.time()
        self._session_rom = rom
        self._session_ach_count = 0
        self._today_session_count += 1
        self._last_game_ts = time.time()
        self._idle_shown.clear()

        if self._memory:
            self._memory.play_times.append(datetime.now().hour)
            prev_count = self._memory.rom_play_counts.get(rom, 0)
        else:
            prev_count = 0

        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()  # 0=Monday

        # Pick comment
        comment = None
        key = None

        if self._memory and prev_count == 0:
            key, comment = "ov_firsttime", "First time on this table! Good luck!"
        elif self._memory and prev_count > 0:
            fav = self._memory.favourite_rom()
            if fav and fav == rom:
                key, comment = "ov_fav", "Your favourite again? No complaints!"
            else:
                last_played_days = self._days_since_last_played(rom)
                if last_played_days is not None and last_played_days >= 30:
                    key, comment = "ov_dustoff", "Long time no see! Dust off those flippers!"
                elif last_played_days is not None and last_played_days >= 7:
                    key, comment = "ov_longago", "Haven't seen this one in a while!"
                elif table_name:
                    key, comment = "ov_classic", f"Oh! {table_name}! Classic!"

        if comment is None:
            # Time-based fallbacks
            if hour < 10:
                key, comment = "ov_morning", "Morning warm-up! Coffee + pinball!"
            elif 17 <= hour < 21:
                key, comment = "ov_evening", "Evening session! The best time to play!"
            elif hour >= 21:
                key, comment = "ov_nightowl", "Night owl mode activated!"
            elif weekday in (5, 6):
                key, comment = "ov_weekend", "Weekend pinball! No alarms tomorrow!"
            elif weekday == 0:
                key, comment = "ov_monday", "Monday motivation: pinball!"
            elif self._today_session_count == 1:
                key, comment = "ov_firstday", "First game of the day! Let's make it count!"
            elif self._today_session_count == 2:
                key, comment = "ov_onemore", "One more game? That is the spirit!"
            elif self._today_session_count >= 3:
                key, comment = "ov_thirdtoday", "Third table today! You are on a roll!"
            else:
                key, comment = "ov_go", "Let's go! Good luck!"

        if self._memory and rom:
            self._memory.rom_play_counts[rom] = prev_count + 1
            self._memory.save()

        if comment:
            self._show_comment_key(key or "ov_go", comment, HAPPY)

    def on_session_ended(self, rom: str) -> None:
        if self._session_start is None:
            return
        duration_s = time.time() - self._session_start
        duration_min = duration_s / 60.0
        ach_count = self._session_ach_count
        self._session_start = None

        if self._memory:
            self._memory.session_durations.append(int(duration_min))
            if ach_count > 0:
                self._memory.achievement_sessions += 1
                self._no_ach_sessions_streak = 0
            else:
                self._memory.no_achievement_sessions += 1
                self._no_ach_sessions_streak += 1
            self._memory.save()

        # Try zank on long session
        if duration_min >= 300:
            self._try_zank("session_5h")
            return

        # Pick end-of-session comment
        now = datetime.now()
        if now.hour == 0 or (now.hour == 23 and now.minute > 55):
            self._show_comment_key("ov_midnight", "Midnight finish! Legendary!", HAPPY)
        elif ach_count == 0 and duration_min < 2:
            self._show_comment_key("ov_tilt", "Tilt? Or just bad luck?", SAD)
        elif ach_count == 0 and duration_min < 5:
            self._show_comment_key("ov_shortsweet", "Short but sweet! Every game counts!", IDLE)
        elif ach_count == 0 and self._no_ach_sessions_streak >= 3:
            self._show_comment_key("ov_dry_spell", "Dry spell... but legends never quit!", SAD)
        elif ach_count == 0 and duration_min > 120:
            self._show_comment_key("ov_grind", "Long session, no achievements... The grind is real!", SAD)
        elif ach_count == 0:
            self._show_comment_key("ov_good_game", "Good game! See you next round", IDLE)
        elif ach_count == 1:
            self._show_comment_key("ov_got_one", "NICE! You got one!", HAPPY)
        elif ach_count == 2:
            self._show_comment_key("ov_double", "Double unlock! Efficient!", HAPPY)
        elif ach_count >= 5:
            self._show_comment_key("ov_avalanche", "Achievement AVALANCHE! How?!", SURPRISED)
        elif duration_min > 120:
            self._show_comment_key("ov_2h", "2 hours in... You okay?", IDLE)
        else:
            self._show_comment_key("ov_got_one", "NICE! You got one!", HAPPY)

    def on_achievement(self) -> None:
        self._session_ach_count += 1
        self._today_ach_count += 1
        self._last_game_ts = time.time()
        self._draw.set_state(HAPPY)
        if self._try_zank("achievement"):
            return
        if self._today_ach_count == 1:
            self._show_comment_key("ov_first_blood", "First blood! The hunt is on!", HAPPY)
        elif self._today_ach_count >= 5:
            self._show_comment_key("ov_5today", "5 achievements today! Beast mode!", SURPRISED)
        else:
            self._show_comment_key("ov_got_one", "NICE! You got one!", HAPPY)

    def on_level_up(self) -> None:
        self._draw.set_state(HAPPY)
        self._try_zank("level_up")

    def on_challenge_start(self) -> None:
        self._challenge_count_today += 1
        self._last_game_ts = time.time()
        self._draw.set_state(HAPPY)
        now = datetime.now()
        if now.hour < 10:
            self._show_comment_key("ov_ch_morning", "Morning challenge! Warm those fingers up!", HAPPY)
        elif self._challenge_count_today >= 5:
            self._show_comment_key("ov_ch_5today", "5 challenges today! Competitor of the year!", SURPRISED)
        else:
            self._show_comment_key("ov_ch_accepted", "Challenge accepted! Do not choke!", HAPPY)

    def on_challenge_timer_tick(self, remaining_ms: int) -> None:
        if remaining_ms <= 3000 and remaining_ms > 2500:
            self._show_comment_key("ov_ch_clock", "Clock is ticking! FOCUS!", SURPRISED)
        elif remaining_ms <= 10000 and remaining_ms > 9500:
            self._show_comment_key("ov_ch_10s", "10 SECONDS! GIVE IT EVERYTHING!", SURPRISED)

    def on_challenge_stop(self) -> None:
        self._draw.set_state(IDLE)

    def on_challenge_won(self, margin_pct: float = 50.0) -> None:
        self._last_game_ts = time.time()
        self._challenge_losses_streak = 0
        if self._try_zank("challenge_win"):
            return
        if margin_pct < 5.0:
            self._show_comment_key("ov_ch_heartattack", "THAT WAS CLOSE! Heart attack!", SURPRISED)
        elif margin_pct > 50.0:
            self._show_comment_key("ov_ch_dominant", "Dominant performance!", HAPPY)
        else:
            self._show_comment_key("ov_ch_win", "YOU WIN! I knew you could do it!", HAPPY)

    def on_challenge_lost(self, attempts: int = 1, margin_pct: float = 10.0) -> None:
        self._last_game_ts = time.time()
        self._challenge_losses_streak += 1
        if self._try_zank("challenge_lose"):
            return
        if margin_pct < 2.0:
            self._show_comment_key("ov_ch_1sec", "1 second away... I felt that", SAD)
        elif attempts >= 3:
            self._show_comment_key("ov_ch_third", "Third time is the charm... right?", SAD)
        elif margin_pct < 10.0:
            self._show_comment_key("ov_ch_close", "So close... Try again!", SAD)
        else:
            self._show_comment_key("ov_ch_notmyfault", "NOT MY FAULT!", SAD)

    def on_heat_changed(self, heat_pct: int) -> None:
        self._last_game_ts = time.time()
        if heat_pct >= 100 and not self._heat_notified_100:
            self._heat_notified_100 = True
            self._try_zank("heat_100") or self._show_comment_key("ov_heat_100", "TOO HOT! Give those flippers a rest!", SURPRISED)
        elif heat_pct >= 85 and not self._heat_notified_85:
            self._heat_notified_85 = True
            self._show_comment_key("ov_heat_85", "CRITICAL HEAT! Your flippers are burning!", SURPRISED)
        elif heat_pct >= 65 and not self._heat_notified_65:
            self._heat_notified_65 = True
            self._show_comment_key("ov_heat_65", "Getting warm! Ease up a little!", IDLE)
        elif heat_pct < 80 and self._heat_notified_100:
            self._heat_notified_100 = False
            self._heat_notified_85 = False
            self._show_comment_key("ov_heat_cool", "Cooling down... smart move!", HAPPY)
        if heat_pct < 50:
            self._heat_notified_65 = False

    def on_flip_progress(self, current: int, goal: int) -> None:
        if goal <= 0:
            return
        pct = current / goal
        prev = self._flip_prev_pct
        self._flip_prev_pct = pct

        milestones = [(0.01, "ov_flip_start", "Flip counter active! Every flip counts!", IDLE),
                      (0.25,  "ov_flip_25",    "Quarter way there! Warm up done!", IDLE),
                      (0.50,  "ov_flip_50",    "Halfway there! Keep flipping!", IDLE),
                      (0.75,  "ov_flip_75",    "75%! Almost there! Do not slow down!", HAPPY),
                      (0.90,  "ov_flip_90",    "Almost at your goal! Do not stop now!", HAPPY),
                      (1.00,  "ov_flip_goal",  "GOAL! You hit your flip target!", HAPPY),
                      (1.01,  "ov_flip_over",  "You SMASHED your goal! Overachiever!", SURPRISED)]
        for threshold, key, text, state in milestones:
            if prev < threshold <= pct and key not in self._flip_notified:
                self._flip_notified[key] = True
                self._show_comment_key(key, text, state)
                break

    # ── Idle handling ─────────────────────────────────────────────────────────

    def _check_idle(self) -> None:
        elapsed_min = (time.time() - self._last_game_ts) / 60.0
        now = datetime.now()

        idle_steps = [
            (5,    "ov_idle_5m",   "Still here... waiting...",                    IDLE),
            (10,   "ov_idle_10m",  "Psst. VPX won't start itself!",               IDLE),
            (15,   "ov_idle_15m",  "I could really go for a game right now...",   IDLE),
            (20,   "ov_idle_20m",  "The tables miss you. True story.",             IDLE),
            (30,   "ov_idle_zzz",  "ZZZ...",                                       SLEEPY),
            (45,   "ov_idle_45m",  "At this point I am basically furniture",       SLEEPY),
            (60,   "ov_idle_1h",   "One hour idle... Are you okay out there?",     SLEEPY),
        ]
        if now.hour >= 23 or now.hour < 5:
            idle_steps.append((20, "ov_idle_late", "Go to sleep. The achievements will be here tomorrow!", SLEEPY))
        if 6 <= now.hour < 10:
            idle_steps.append((5, "ov_idle_morn", "Good morning! Ready for some pinball?", HAPPY))
        if now.weekday() >= 5 and 10 <= now.hour < 20:
            idle_steps.append((10, "ov_idle_wknd", "It is the weekend and you are NOT playing?!", IDLE))

        for mins, key, text, state in sorted(idle_steps):
            if elapsed_min >= mins and key not in self._idle_shown:
                self._idle_shown[key] = True
                self._draw.set_state(state)
                self._show_comment_key(key, text, state)
                if mins == 30:
                    self._try_zank("idle_30m")
                break

        if elapsed_min < 5:
            self._idle_shown.clear()
            if self._draw._state == SLEEPY:
                self._draw.set_state(IDLE)

    def _fire_daytime_comment(self) -> None:
        now = datetime.now()
        weekday = now.weekday()
        hour = now.hour
        month = now.month
        day = now.day

        key = text = None
        if month == 1 and day == 1:
            key, text = "ov_day_ny",   "Happy New Year! First achievement of the year?"
        elif month == 12 and day == 25:
            key, text = "ov_day_xmas", "Playing on Christmas?! Dedicated!"
            self._try_zank("christmas")
            return
        elif month == 10 and day == 31:
            key, text = "ov_day_hal",  "Spooky session! BOO!"
        elif month == 12 and day == 31:
            key, text = "ov_day_nye",  "Last game of the year? Make it count!"
        elif day == 1:
            key, text = "ov_day_new_month", "New month, new achievements!"
        elif weekday == 0:
            key, text = "ov_day_mon",  "Monday? Best day for pinball!"
        elif weekday == 1:
            key, text = "ov_day_tue",  "Tuesday grind! Underrated pinball day!"
        elif weekday == 2:
            key, text = "ov_day_wed",  "Midweek energy! Keep it up!"
        elif weekday == 3:
            key, text = "ov_day_thu",  "Thursday already?! Time flies when you are flipping!"
        elif weekday == 4 and hour >= 17:
            key, text = "ov_day_fri",  "Friday night pinball! The best kind!"
        elif weekday == 5 and 12 <= hour < 18:
            key, text = "ov_day_sat",  "Perfect Saturday afternoon!"
        elif weekday == 6 and hour >= 18:
            key, text = "ov_day_sun",  "Sunday session! One more before Monday!"

        if key and text:
            QTimer.singleShot(8000, lambda: self._show_comment_key(key, text, IDLE))

    def _schedule_random(self) -> None:
        base_ms = random.randint(3 * 60_000, 6 * 60_000)
        mult = self._memory.comment_frequency_multiplier() if self._memory else 1.0
        self._rand_timer.start(int(base_ms / max(0.1, mult)))

    def _fire_random(self) -> None:
        self._schedule_random()
        if self._is_silenced():
            return
        if _TROPHIE_SHARED["gui_visible"] and random.random() < 0.2:
            self._fire_zank_comment()
            return
        if self._memory:
            tip = self._memory.pick_unseen(_OV_RANDOM)
        else:
            tip = random.choice(_OV_RANDOM)
        if tip:
            self._show_comment_key(tip[0], tip[1], IDLE)

    def _fire_zank_comment(self) -> None:
        if not _TROPHIE_SHARED["gui_visible"]:
            return
        if self._memory:
            tip = self._memory.pick_unseen(_OV_ZANK)
        else:
            tip = random.choice(_OV_ZANK)
        if tip:
            self._show_comment_key(tip[0], tip[1], TALKING)

    def _try_zank(self, trigger: str) -> bool:
        if not _TROPHIE_SHARED["gui_visible"]:
            return False
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            return False
        for trig, gui_key, ov_key in _ZANK_PAIRS:
            if trig == trigger:
                ov_options = _ZANK_OVERLAY_LINES.get(ov_key, [])
                if ov_options:
                    ov_text = random.choice(ov_options)
                    # Schedule overlay response 2 seconds after gui fires
                    QTimer.singleShot(2000, lambda t=ov_text, k=ov_key: self._show_comment_key(k, t, TALKING))
                # Signal GUI to show its line
                _TROPHIE_SHARED["zank_pending_gui"] = gui_key
                _TROPHIE_SHARED["zank_cooldown_ms"] = _ZANK_COOLDOWN_MS
                return True
        return False

    def _zank_tick_fn(self) -> None:
        if _TROPHIE_SHARED["zank_cooldown_ms"] > 0:
            _TROPHIE_SHARED["zank_cooldown_ms"] = max(0, _TROPHIE_SHARED["zank_cooldown_ms"] - 1000)
        pending = _TROPHIE_SHARED.get("zank_pending_overlay")
        if pending:
            _TROPHIE_SHARED["zank_pending_overlay"] = None
            options = _ZANK_OVERLAY_LINES.get(pending, [])
            if options:
                ov_text = random.choice(options)
                QTimer.singleShot(2000, lambda t=ov_text, k=pending: self._show_comment_key(k, t, TALKING))
        # Handle spontaneous idle bicker response
        bicker_key = _TROPHIE_SHARED.get("idle_bicker_ov_key")
        bicker_text = _TROPHIE_SHARED.get("idle_bicker_ov_text")
        if bicker_key and bicker_text:
            _TROPHIE_SHARED["idle_bicker_ov_key"] = None
            _TROPHIE_SHARED["idle_bicker_ov_text"] = None
            if _TROPHIE_SHARED["gui_visible"]:
                QTimer.singleShot(2000, lambda t=bicker_text, k=bicker_key: self._show_comment_key(k, t, TALKING))

    def _days_since_last_played(self, rom: str) -> Optional[int]:
        # Simple: we don't track dates directly — use play_count heuristic
        return None  # Placeholder; extend with timestamp tracking if needed

    # ── UI ───────────────────────────────────────────────────────────────────

    def _is_silenced(self) -> bool:
        return time.time() < self._silenced_until

    def _show_comment(self, text: str, state: str = TALKING) -> None:
        if self._is_silenced():
            return
        self._dismiss_bubble()
        self._draw.set_state(state)
        # Create bubble as a top-level window so it is visible above the small
        # overlay widget (child widgets with negative Y coords get clipped).
        if self._memory is None:
            mem = _TrophieMemory.__new__(_TrophieMemory)
            mem.seen_tips = set()
            mem.dismiss_speed = []
            mem.comments_shown = 0
            mem.comments_dismissed_fast = 0
            mem._fast_dismiss_streak = 0
            mem._told_quiet = False
        else:
            mem = self._memory
        ov = self._cfg.OVERLAY or {}
        portrait = bool(ov.get("trophie_overlay_portrait", False))
        if portrait:
            ccw = bool(ov.get("trophie_overlay_rotate_ccw", False))
            rotation = -90 if ccw else 90
        else:
            rotation = 0
        bubble = _SpeechBubble(None, text, mem, rotation=rotation)
        bubble._owner = self  # so _do_dismiss can still call _schedule_quiet_msg
        bubble.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        bubble.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        bubble.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._current_bubble = bubble
        self._position_bubble(bubble)
        bubble.show()

    def _show_comment_key(self, key: str, text: str, state: str = TALKING) -> None:
        if self._memory:
            self._memory.seen_tips.add(key)
        self._show_comment(text, state)

    def _position_bubble(self, bubble: _SpeechBubble) -> None:
        try:
            bw = bubble.width()
            bh = bubble.height()
            screen_geom = QApplication.primaryScreen().geometry()
            origin = self.mapToGlobal(QPoint(0, 0))
            ov = self._cfg.OVERLAY or {}
            portrait = bool(ov.get("trophie_overlay_portrait", False))
            # Ball top offset in landscape widget coordinates:
            # ball center is at (tw/2, th/2), radius ≈ min(tw,th)*0.38
            ball_top = self._TROPHY_H // 2 - int(min(self._TROPHY_W, self._TROPHY_H) * 0.38)
            if not portrait:
                # Landscape: bubble centered above ball top
                abs_x = origin.x() + self._TROPHY_W // 2 - bw // 2
                abs_y = origin.y() + ball_top - bh - 7
                # If no room above, flip below the ball
                if abs_y < screen_geom.y():
                    abs_y = origin.y() + self._TROPHY_H + 4
                # Clamp to screen
                if abs_x < screen_geom.x():
                    abs_x = screen_geom.x()
                if abs_y < screen_geom.y():
                    abs_y = screen_geom.y()
                if abs_x + bw > screen_geom.right():
                    abs_x = screen_geom.right() - bw
                if abs_y + bh > screen_geom.bottom():
                    abs_y = screen_geom.bottom() - bh
                mascot_cx = origin.x() + self._TROPHY_W // 2
                bubble.set_pointer_offset(mascot_cx - abs_x)
            else:
                # Portrait: widget is _TROPHY_H wide × _TROPHY_W tall.
                # Place bubble to the left or right of the mascot.
                # rotation=90 (CW)  → pointer points LEFT  → bubble to the RIGHT
                # rotation=-90 (CCW) → pointer points RIGHT → bubble to the LEFT
                ccw = bool(ov.get("trophie_overlay_rotate_ccw", False))
                mascot_center_y = origin.y() + self.height() // 2
                if not ccw:
                    # rotation=90: bubble to the right of mascot
                    abs_x = origin.x() + self.width() + 4
                    if abs_x + bw > screen_geom.right():
                        abs_x = origin.x() - bw - 4  # flip to left
                else:
                    # rotation=-90: bubble to the left of mascot
                    abs_x = origin.x() - bw - 4
                    if abs_x < screen_geom.x():
                        abs_x = origin.x() + self.width() + 4  # flip to right
                # Center bubble vertically with mascot
                abs_y = mascot_center_y - bh // 2
                # Clamp to screen
                if abs_x < screen_geom.x():
                    abs_x = screen_geom.x()
                if abs_y < screen_geom.y():
                    abs_y = screen_geom.y()
                if abs_x + bw > screen_geom.right():
                    abs_x = screen_geom.right() - bw
                if abs_y + bh > screen_geom.bottom():
                    abs_y = screen_geom.bottom() - bh
                # Map mascot Y distance to unrotated X (pointer offset).
                # rotation=90:  pointer Y in rotated widget == cx (unrotated X)
                # rotation=-90: pointer Y in rotated widget == bh - cx
                ptr_y = mascot_center_y - abs_y
                if not ccw:
                    bubble.set_pointer_offset(ptr_y)
                else:
                    bubble.set_pointer_offset(bh - ptr_y)
            bubble.move(abs_x, abs_y)
        except Exception:
            pass

    def _dismiss_bubble(self) -> None:
        if self._current_bubble:
            try:
                self._current_bubble._auto_timer.stop()
                self._current_bubble._begin_fade_out()
            except Exception:
                pass
            self._current_bubble = None
        self._draw.set_state(IDLE)

    def _schedule_quiet_msg(self, msg: str) -> None:
        QTimer.singleShot(500, lambda: self._show_comment(msg, TALKING))

    # ── Dragging ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_pos_start = self.pos()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._drag_pos_start + delta)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self._save_position()

    def _save_position(self) -> None:
        try:
            self._cfg.OVERLAY["trophie_overlay_x"] = self.x()
            self._cfg.OVERLAY["trophie_overlay_y"] = self.y()
            self._cfg.save()
        except Exception:
            pass

    def _restore_position(self) -> None:
        try:
            x = int(self._cfg.OVERLAY.get("trophie_overlay_x", -1))
            y = int(self._cfg.OVERLAY.get("trophie_overlay_y", -1))
            if x >= 0 and y >= 0:
                self.move(x, y)
                return
        except Exception:
            pass
        # Default: bottom-left of primary screen
        try:
            screen = QApplication.primaryScreen().geometry()
            self.move(self._MARGIN, screen.height() - self._TROPHY_H - self._MARGIN)
        except Exception:
            self.move(self._MARGIN, 600)

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        gpos = self.mapToGlobal(pos)
        menu.addAction("Dismiss comment", lambda: (self._dismiss_bubble(), self._show_action_toast(gpos)))
        menu.addAction("Silence for 10 minutes", lambda: (self._silence_10m(), self._show_action_toast(gpos)))
        move_menu = menu.addMenu("Move to corner...")
        move_menu.addAction("Bottom Left",  lambda: (self._move_to_corner("bl"), self._show_action_toast(gpos)))
        move_menu.addAction("Bottom Right", lambda: (self._move_to_corner("br"), self._show_action_toast(gpos)))
        move_menu.addAction("Top Left",     lambda: (self._move_to_corner("tl"), self._show_action_toast(gpos)))
        move_menu.addAction("Top Right",    lambda: (self._move_to_corner("tr"), self._show_action_toast(gpos)))
        menu.exec(gpos)

    def _show_action_toast(self, global_pos: QPoint) -> None:
        toast = _ActionToast(None)
        # Centre the toast above the mascot widget
        tx = self.x() + self._TROPHY_W // 2 - toast.width() // 2
        ty = self.y() - toast.height() - 4
        try:
            screen = QApplication.primaryScreen().geometry()
            if ty < screen.y():
                ty = self.y() + self._TROPHY_H + 4
            tx = max(screen.x(), min(tx, screen.x() + screen.width()  - toast.width()))
            ty = max(screen.y(), min(ty, screen.y() + screen.height() - toast.height()))
        except Exception:
            pass
        toast.popup(QPoint(tx, ty))

    def _silence_10m(self) -> None:
        self._silenced_until = time.time() + 600
        self._dismiss_bubble()

    def _move_to_corner(self, corner: str) -> None:
        try:
            screen = QApplication.primaryScreen().geometry()
            sw, sh = screen.width(), screen.height()
            m = self._MARGIN
            positions = {
                "bl": (m, sh - self._TROPHY_H - m),
                "br": (sw - self._TROPHY_W - m, sh - self._TROPHY_H - m),
                "tl": (m, m),
                "tr": (sw - self._TROPHY_W - m, m),
            }
            self.move(*positions.get(corner, (m, sh - self._TROPHY_H - m)))
            self._save_position()
        except Exception:
            pass
