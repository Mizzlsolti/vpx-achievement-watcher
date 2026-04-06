# 🎯 VPX Achievement Watcher

A companion app for Visual Pinball X (VPX) that adds modern achievements, live overlays, and challenges by reading VPinMAME NVRAM data.

---

## Features

### 🏠 Dashboard

Your control center at a glance:
- **System Status**: Is the watcher running? Is VPX active?
- **Session Summary**: Last table played, score, and achievements
- **Run Status**: Table detection, session, cloud, and leaderboard connection (green/yellow/red indicators)
- **Notifications**: Clickable alerts for leaderboard ranks, beaten records, missing VPS-IDs, and available updates
- **Quick Actions**: Restart Engine, Minimize to Tray, Quit

---

### 👤 Player Tab

Your personal player profile and summary:
- **Player Level**: Current level and XP progress bar based on unlocked achievements
- **Prestige System**: Reach Prestige 1–5 by unlocking 2000 achievements per star (☆ → ★)
- **Level Table**: All levels from Rookie to VPX Elite with their achievement thresholds
- **🏅 Badges**: 37 collectible badges earned through gameplay milestones — unlock achievements, complete challenges, reach levels, accumulate playtime, and more
- **Display Badge**: Choose which badge icon appears next to your name on cloud leaderboards

---

### 🏆 Achievement Progress & System

The tool recognizes game actions (e.g., ramps hit, multiballs activated, jackpots) and automatically unlocks achievements — either for the current game session or globally as long-term motivation.

---

### 📊 Highlights & Overlays

After a game (or at the touch of a button on the keyboard/controller), transparent info windows appear directly above the pinball machine. These show the best actions of the game and statistics. Supports portrait mode specifically for pinball cabinets.

---

### ⚔️ Challenge Modes (like Pinball FX)

- **Timed Challenge**: Achieve the maximum score in 3 or 5 minutes.
- **Flip Challenge**: How many points can you score with a limited number of flips? Select your difficulty level (e.g., Pro = Only 100 flips!).
- **Heat Challenge**: When the barometer reaches 100%, it's over. The heat rises if you hold down the button or press it too quickly. But it cools down when you let go.

---

### ⚔️ Score Duels

Challenge other players to direct score duels on the same table! Compete head-to-head with Auto-Match or invite friends. Includes a global feed of active duels.

---

### 📈 Progress

Track your overall achievement progress per table:
- Completion percentage for each table
- Which achievements are still locked / unlocked (✅ / 🔒)
- Overall progress across all tables

---

### 🔔 Feedback

Displays small pop-up notifications (toasts) directly after the game when you achieve a success and offers optional voice output for challenge events.

---

### 💾 Statistics & Records

Records every round played, the duration of the game, and the points scored in the background. These can be conveniently evaluated in the user interface (GUI):
- **Global NVRAM Dumps**: Full data overview per table
- **Player Session Deltas**: Actions and changes from your sessions
- **Challenge Leaderboards**: Latest challenge results and rankings

---

### ☁️ Leaderboards

Compete with the community! The tool uploads your challenge scores and achievement progress (in %) to the cloud (if desired).

> 💡 **Tip**: You can find your personal 4-digit player ID in the "System" tab. Make a note of it! If you ever install Watcher on a new PC, you can use it to restore your cloud progress.

---

### 🛡️ Fair Play & Anti-Cheat

To keep the leaderboards fair, local saves and scores are protected by hash signatures.

---

### 🗺️ Available Maps

Browse all supported tables and their NVRAM map status:
- ✅ **NVRAM Map** = achievement tracking supported
- ❌ **No NVRAM Map** = not supported yet
- 🟠 **Local** = .vpx file found in your tables folder
- Filter by local tables with NVRAM maps, search by name or ROM
- Assign **VPS-IDs** to link tables to the Virtual Pinball Spreadsheet database
- View table author extracted from .vpx file metadata

---

### 🎯 AWEditor — Custom Achievement Editor

Create custom achievements for tables that don't use VPinMAME ROMs (Non-ROM / Original tables):
- **📋 Tables**: Scan your tables directory for tables without NVRAM maps
- **✏️ Codes**: Analyze table scripts, detect events, and create custom achievement rules
- **Export**: Generates VBScript + JSON files — the table writes trigger files that the watcher detects instantly
- **Full Script Export**: Zero manual work — AWEditor inserts all FireAchievement calls automatically

---

### 🏆 Mascots — Trophie & Steely

Two animated companion mascots that react to your gameplay:

- **🏆 Trophie** (GUI Mascot): Lives in the bottom-left corner of the main window. An intellectual office-themed character — reads books, checks clipboards, analyzes charts, and celebrates your achievements with a scholarly flair.
- **🎱 Steely** (Desktop Overlay Mascot): A metallic chrome pinball that lives on your desktop as an always-on-top overlay. Reacts to game events with pinball-themed animations — gets launched by plungers, bounces off bumpers, rides wireforms, and celebrates jackpots.
- **Skins**: Multiple visual skins for both mascots (configurable in the Appearance tab)
- **Personality**: Both mascots have unique speech bubbles, reactions, memory, and even a "bickering" system between them
- **Portrait Mode**: Steely supports 90° rotation for cabinet screens

---

### 🎨 Appearance — Themes, Sound & Effects

Customize the look and feel of the entire application:

- **🎨 Themes**: Multiple color themes (Neon Blue, Retro, etc.) affecting all windows, overlays, toasts, and challenge UI
- **🔊 Sound Effects**: Configurable sound effects for achievement unlocks, challenges, and events — with multiple sound packs (Zaptron, Vex Machina, Retro, etc.), per-event enable/disable, volume control, and preview buttons
- **✨ Visual Effects**: GPU-accelerated visual effects with automatic CPU fallback
- **Overlay Placement**: Position every overlay element (stats, toasts, challenge menu, timer, flip counter, heat bar, mini info, status) independently on screen

---

### 📺 VPC Weekly Challenge

View Discord's Weekly Challenge directly on the overlay (view only).

---

### 🕹️ Controls

Configure hotkeys and input bindings for the overlay and challenges. Supports keyboard keys and joystick buttons.

---

### ⚙️ System

- **Player Profile**: Set your player name and view your 4-digit player ID
- **Directory Setup**: Configure BASE, NVRAM, and Tables directories
- **Maintenance & Updates**: Repair data folders, force cache NVRAM maps, check for updates
- **Cloud Settings**: Enable/disable cloud sync, restore progress with player ID

---

## Data Sources

The Achievement Watcher uses the following open-source projects and data sources:

Thanks to this people:

| Source | Repository |
|--------|-----------|
| **NVRAM Maps** by tomlogic | [pinmame-nvram-maps](https://github.com/tomlogic/pinmame-nvram-maps) |
| **vpxtool** by francisdb | [vpxtool](https://github.com/francisdb/vpxtool) |
| **VPC Data** by emb417 | [vpc-data](https://github.com/emb417/vpc-data) |
| **VPS Database** by VPS Team | [vps-db](https://github.com/VirtualPinballSpreadsheet/vps-db) |
| **Visual Pinball & PinMAME** | [vpinball](https://github.com/vpinball) — The official Visual Pinball and PinMAME hub |

