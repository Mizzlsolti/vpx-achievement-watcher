"""trophy_data.py — Constants, data structures, and _TrophieMemory for the Trophie mascot.

Shared by both GUITrophie and OverlayTrophie instances.  Contains all static
dialogue data (tips, zank lines, idle bicker exchanges, overlay comments) and
the lightweight JSON-backed _TrophieMemory learning model.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime
from typing import Optional

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
    "tab_duels": [
        ("duels_intro",    "Score Duels let you challenge other players head-to-head!"),
        ("duels_invite",   "Send a duel invitation and see who scores higher on the same table!"),
        ("duels_accept",   "You have 15 seconds to accept an incoming duel — stay alert!"),
        ("duels_history",  "Check your duel history to see your win rate against rivals!"),
        ("duels_cloud",    "Duels require Cloud Sync to communicate with other players!"),
        ("duels_table",    "Pick a table you know well for duels — home advantage matters!"),
        ("duels_rematch",  "Lost a duel? Challenge them again — revenge is sweet!"),
        ("duels_hotkey",   "Use your hotkeys to navigate duel invitations!"),
    ],
    "tab_duels_global": [
        ("tab_global_1",   "Let's see who's been dueling!"),
        ("tab_global_2",   "The arena never sleeps!"),
        ("tab_global_3",   "Scouting the competition, smart move!"),
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

_GUI_DUEL: dict[str, list[str]] = {
    "gui_duel_received": [
        "A challenger approaches! Check your Score Duels tab!",
        "You have been challenged! Open the Score Duels tab to respond!",
        "Incoming duel invitation! Will you accept the challenge?",
        "Someone wants to duel you! 15 seconds to decide!",
    ],
    "gui_duel_won": [
        "DUEL CHAMPION! You crushed that duel!",
        "Victory in the duel! That is what I am talking about!",
        "Duel won! The high score speaks for itself!",
        "DUEL WINNER! Absolutely dominant performance!",
    ],
    "gui_duel_lost": [
        "The table was rigged! Next time for sure...",
        "Tough duel. Rematch incoming?",
        "Duel lost... but you gave it everything!",
        "They got lucky. That is all I am saying.",
    ],
    "gui_duel_declined": [
        "Maybe next time...",
        "No shame in saying no. There will be other duels!",
        "Declined. The duels tab is always open for new challenges!",
    ],
    "gui_duel_accepted": [
        "Challenge accepted! Time to show them what you got!",
        "The duel is ON! Go crush that score!",
        "Accepted! May the best player win!",
    ],
    "gui_duel_expired": [
        "That duel timed out... They were probably scared!",
        "Duel expired. Onwards to the next challenge!",
        "Too slow! The invite window closed.",
    ],
    "gui_automatch_started": [
        "Looking for trouble, huh?",
        "Let's find you a worthy opponent!",
        "The arena awaits!",
    ],
    "gui_automatch_found": [
        "Found one! Game on!",
        "A challenger appears!",
        "Match made! Time to duel!",
    ],
    "gui_automatch_timeout": [
        "Nobody home... try again later!",
        "The arena is empty...",
        "Patience... they'll come.",
    ],
    "gui_duel_aborted": [
        "That doesn't count! Play the full game!",
        "No quitting early in a duel!",
        "Rage quit? The duel is void!",
        "You gotta earn it! No shortcuts!",
    ],
}

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

_OV_DUEL: dict[str, list[str]] = {
    "ov_duel_received": [
        "A challenger approaches! Open the app to respond!",
        "Incoming duel invitation! Check your Score Duels tab!",
        "Someone wants to duel you! You have 15 seconds!",
        "DUEL ALERT! Will you answer the challenge?",
    ],
    "ov_duel_won": [
        "DUEL CHAMPION! I knew you had it in you!",
        "Victory! The high score dominates again!",
        "DUEL WON! Nobody beats you on this table!",
        "That is how you duel! Absolutely crushing!",
    ],
    "ov_duel_lost": [
        "Next time for sure... The table was clearly rigged!",
        "Tough loss. Challenge them to a rematch!",
        "Duel lost... but what a battle!",
        "They got lucky. I was watching. It was luck.",
    ],
    "ov_duel_declined": [
        "Maybe next time...",
        "No problem. The duels will keep coming!",
        "Declined. Save your energy for the right opponent!",
    ],
    "ov_duel_accepted": [
        "Challenge accepted! Time to dominate!",
        "The duel is ON! Show them your skills!",
        "Accepted! Let the battle begin!",
    ],
    "ov_duel_expired": [
        "Too slow! That duel just expired!",
        "Duel expired. The clock waits for nobody!",
        "That invite timed out. Watch for the next one!",
    ],
    "ov_automatch_started": [
        "Looking for trouble, huh?",
        "Let's find you a worthy opponent!",
        "The arena awaits!",
    ],
    "ov_automatch_found": [
        "Found one! Game on!",
        "A challenger appears!",
        "Match made! Time to duel!",
    ],
    "ov_automatch_timeout": [
        "Nobody home... try again later!",
        "The arena is empty...",
        "Patience... they'll come.",
    ],
    "ov_duel_aborted": [
        "That doesn't count! Play the full game!",
        "No quitting early in a duel!",
        "Rage quit? The duel is void!",
        "You gotta earn it! No shortcuts!",
    ],
}


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
        return False

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


