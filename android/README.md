# VPX Achievement Watcher — Android Companion App

📱 Android companion app for the [VPX Achievement Watcher](https://github.com/Mizzlsolti/vpx-achievement-watcher) desktop application. Manage Score Duels, join Tournaments — all synced via Firebase Realtime Database.

## Screenshots

*(Coming soon — screenshots placeholder)*

## Features

- **🏠 Dashboard** — Quick status overview of pending duels, active tournaments, and queue status
- **⚔️ Score Duels** — Accept/decline duel invitations, send new duels, auto-match, view history and leaderboard
- **🏆 Tournaments** — Join the 4-player tournament queue, view live brackets, tournament history
- **👤 Profile** — View player info, level, badges, duel statistics
- **🔗 Overlay Sync** — Actions in the app (accept/decline duel) automatically dismiss the desktop Watcher's overlay

## Prerequisites

- **Android 8.0+** (API 26)
- **Player ID** and **Player Name** from your desktop Watcher setup

## Setup

1. **Get your Player ID and Name**:
   - These are set during the Watcher's first-run setup wizard
   - Player ID is a 4-character code (e.g., `AB23`)
   - If you don't have one, the app can generate a new one

2. **Install the app** and enter your Player Name and Player ID on the login screen

## Build Instructions

### Prerequisites
- [Java Development Kit (JDK) 17](https://adoptium.net/)
- [Android SDK](https://developer.android.com/studio) (or Android Studio)

### Build Debug APK

```bash
cd android
./gradlew assembleDebug
```

The APK will be at `app/build/outputs/apk/debug/app-debug.apk`.

### Build Release APK

```bash
cd android
./gradlew assembleRelease
```

> **Note**: Release builds require signing configuration in `app/build.gradle.kts`.

## Architecture

| Layer | Technology |
|-------|-----------|
| UI | Jetpack Compose + Material 3 |
| Navigation | Navigation Compose (Bottom Nav) |
| State | ViewModel + Compose State |
| Network | OkHttp (REST + SSE) |
| Serialization | kotlinx.serialization |
| Data | Firebase REST API (no SDK) |
| Storage | SharedPreferences |

### Key Design Decisions

- **No Firebase SDK** — Uses plain HTTP REST calls matching the desktop Watcher's `CloudSync` approach
- **Same Validation** — Login validation matches `CloudSync.validate_player_identity()` exactly
- **App Signals** — Writes to `players/{pid}/app_signals/` so the desktop Watcher can auto-dismiss overlays

## Firebase Rules

See [FIREBASE_RULES.md](FIREBASE_RULES.md) for the Firebase Realtime Database rules that need to be applied.

## Limitations

- **Cannot submit scores** — Only the desktop Watcher can read VPinMAME NVRAM to capture scores
- **Limited auto-match** — The app sends an empty `vps_ids` list since it has no local NVRAM maps
- **Limited tournament table matching** — Same reason as auto-match
- **No achievement tracking** — Achievements are tracked by the desktop Watcher via NVRAM analysis
- **No push notifications** — Currently uses polling (5s for duels, 30s for tournaments)

## Polling Intervals

| Feature | Interval | Method |
|---------|----------|--------|
| Duels | 5 seconds | Polling |
| Tournaments | 30 seconds | Polling |
| Duel expiry | 30 seconds | Polling |

## License

Same license as the main VPX Achievement Watcher project.
