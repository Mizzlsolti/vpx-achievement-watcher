# 🎯 VPX Achievement Watcher

A companion app for Visual Pinball X (VPX) that adds achievements, live overlays, multiplayer results and cloud leaderboards by reading VPinMAME NVRAM data.

---

## Highlights

- **Achievements** for every table with an NVRAM map – per table and across all tables, with levels, prestige and badges
- **In-game overlay** at the end of every game: highlights, score, Best Ball, NVRAM actions, achievement progress and the cloud leaderboard
- **Multiplayer (VPX 10.8.1+)**: up to 4 players per game, one column per player
- **Cloud leaderboards** and achievement rarity, protected against cheating
- **AWEditor** to create achievements for tables without a ROM

---

## Main window

The window is split into 6 tabs: **Dashboard, Player, Tables, Stats, Appearance, System**. A setup wizard guides you through the first start. Every tab has a ❓ button with help for that page.

### 🏠 Dashboard

- **Status**: Is the Watcher running? Quick actions: Restart, Minimize to Tray, Quit
- **Last Run**: last table played, score, achievements unlocked, date
- **📋 Setup Status**: checklist (player name, Cloud Sync, VPS-IDs, NVRAM maps, overlays, controls) with direct links to fix missing items
- **📬 Notifications**: leaderboard ranks, beaten records, missing VPS-IDs, available updates and plugin notices

### 👤 Player

- **Level & Badges**
  - Player level from Rookie to VPX Elite, based on unlocked achievements
  - Prestige 1–5: one star per 2000 achievements (☆ → ★)
  - 31 collectible badges; choose the badge shown next to your name on the leaderboards
- **Achievements**
  - Per table: every achievement with ✅ unlocked / 🔒 locked and an ℹ️ info (condition, VPS table, unlock time)
  - Global achievements across all tables (playtime, tables played, manufacturers …) with progress bars
  - Rarity tiers (Common → Legendary), based on how many cloud players unlocked an achievement
  - Custom tables (AWEditor) have their own progress view

### 📚 Tables

- **NVRAM Maps**: all supported tables and their map status
  - ✅ NVRAM map = achievement tracking supported, ❌ = not supported yet, 🟠 = `.vpx` found in your tables folder
  - Filter and search by name or ROM
  - Assign **VPS-IDs** (Virtual Pinball Spreadsheet) – needed for cloud uploads
- **🎯 AWEditor**: create achievements for tables without a VPinMAME ROM
  - Scans your tables folder for tables without NVRAM maps
  - Analyzes the table script, detects events and creates achievement rules
  - Exports VBScript + JSON; the full script export inserts all `FireAchievement` calls automatically

### 📊 Stats

- **🌍 Global NVRAM Dumps**: all NVRAM fields and values per table
- **👤 Player Session Deltas**: what changed during your last session (actions, score, playtime)
- **☁️ Cloud Leaderboard**
  - Global overview: top 50 players by number of different achievements, plus your own place
  - Per table: enter a table or ROM name (autocomplete) – top 25 with progress, medals, badges and ℹ️ VPS info, plus your own place

### 🎨 Appearance

- **🖼 Overlay**
  - Font, base size and overlay scale (30–300 %)
  - Per overlay (Main Stats Overlay, Achievement Toasts, System Notifications): Portrait mode, Rotate CCW, **Place** / **Save** position, Test
  - Switch all overlays to portrait or landscape at once
  - Overlay pages: page 1 (Highlights & Score) is always on; page 2 (Achievement Progress) and page 3 (Cloud Leaderboard) can be switched off
  - Custom background: place `overlay_bg.jpg/png` next to the executable
- **🎨 Theme**: 15 themes as clickable color tiles, color preview, overlay test
- **✨ Sound & Effects**
  - Sound: on/off, volume, 20 sound packs, every event can be switched off and previewed
  - Animations and visual effects for all overlays, low-performance mode
- **🕹️ Controls**: hotkeys for the overlay and the tray; keyboard keys and joystick buttons (flipper or MagnaSave buttons work best)

### ⚙️ System

- **General**
  - **Player Profile**: display name, 4-character Player ID and your **Recovery Key** (see *Cloud & Fair Play*). Name and ID are locked while Cloud Sync is on
  - **Cloud Sync**: enable/disable, Restore from Cloud (achievements, VPS mapping, custom-table progress)
  - **Local Backup & Restore**: everything in one ZIP file (signed), including your Recovery Key
  - **Feedback & Bug Reports** directly from the app
- **Maintenance**
  - Folders (Watcher, NVRAM, Tables), Repair Data Folders
  - Force Cache NVRAM Maps, Update Databases (index, ROM names, VPS DB, vpxtool)
  - Watcher Update: checks GitHub for a new release, shows the release notes and installs the setup

---

## 🖥️ In-game overlay

Opens automatically at the end of a game (or with your hotkey) and has up to 3 pages:

1. **Highlights & Score** – score, Best Ball, highlights and the NVRAM actions of the game. Content that does not fit scrolls automatically, the text size stays the same.
2. **Achievement Progress** – all achievements of the table with rarity
3. **Cloud Leaderboard** – top 25 of the table

Achievement toasts pop up when an achievement is unlocked; system notifications show short notices (e.g. a table without NVRAM map).

---

## 👥 Multiplayer & live tracking (VPX 10.8.1+)

With Visual Pinball X **10.8.1** the Watcher tracks every game on its own, with **up to 4 players**:

- The Watcher installs and enables the required plugins automatically: superhac's **score-server** plugin and the **PinMAME plugin** with his `GetController` patch (built by this repo's *Build VPX Plugins* workflow).
- The overlay opens at the end of each game – not again when the table is closed. A game still running when you close the table is shown then, if it lasted 60 s or longer. Games shorter than 60 s are ignored.
- **1 player**: achievements unlock live during the game (from ball 2 on – what you reached on ball 1 follows then). Every stage reached in a game is unlocked.
- **2–4 players**: no achievements. Page 1 shows one column per player – score, Best Ball, highlights and that player's table actions – and the winner.
- ROMs whose game status the plugin cannot read: a short notice at table start, then everything works like 10.8.0.
- If a VPX update replaces the PinMAME plugin, the multiplayer version is restored automatically (same plugin version). A new PinMAME version is reported in the Dashboard.
- **VPX older than 10.8.1** or plugins not available: single player, results after closing the table – exactly as before.

---

## ☁️ Cloud & Fair Play

- Every Watcher signs in to the cloud automatically – no account or password needed.
- Your **Player ID belongs to your PC**: nobody else can upload for it. To use it on another PC, enter your **Recovery Key** (System → General, also stored in *Backup to ZIP*). Keep it safe and never share it.
- The cloud checks every upload (valid values, matching leaderboard entry, upload rate), and player names are unique.
- Save files changed outside the Watcher still load, but cloud uploads pause until you restore from the cloud or from a backup. A damaged save file falls back to its last good copy.
- Uploads need a player name (not "Player"), Cloud Sync switched on and a VPS-ID for the table.
- Older Watcher versions cannot upload – keep the Watcher up to date.

---

## Credits

The Achievement Watcher builds on these open-source projects – thanks to everyone involved:

| Project | Repository |
|--------|-----------|
| **NVRAM Maps** by tomlogic | [pinmame-nvram-maps](https://github.com/tomlogic/pinmame-nvram-maps) – the base of all achievements and table statistics |
| **Score Server** by superhac | [score-server](https://github.com/superhac/score-server) – live scores, players and balls for multiplayer, incl. his PinMAME `GetController` patch |
| **vpxtool** by francisdb | [vpxtool](https://github.com/francisdb/vpxtool) – reads table scripts and metadata from `.vpx` files |
| **VPS Database** by the VPS team | [vps-db](https://github.com/VirtualPinballSpreadsheet/vps-db) – table names, authors and versions |
| **Visual Pinball & PinMAME** | [vpinball](https://github.com/vpinball) – the official Visual Pinball and PinMAME hub |
