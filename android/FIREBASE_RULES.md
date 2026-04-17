# Firebase Rules for VPX Achievement Watcher Android App

The Android companion app requires the following Firebase Realtime Database rules to be applied in addition to the existing rules used by the desktop Watcher.

## App Signals Node

The `app_signals` node allows the Android app to communicate actions (e.g. accepting a duel) back to the desktop Watcher, causing the overlay to dismiss automatically.

```json
{
  "rules": {
    "players": {
      "$playerId": {
        "app_signals": {
          ".read": true,
          ".write": true,
          "$signalId": {
            ".validate": "newData.hasChildren(['action', 'duel_id', 'ts'])"
          }
        }
      }
    }
  }
}
```

## Important Notes

1. **No Firebase Authentication**: The existing desktop Watcher uses **unauthenticated** Firebase access — all `CloudSync` methods use plain HTTP GET/PUT/PATCH without any Firebase auth tokens. The Android app follows the same pattern using plain REST calls.

2. **Existing Rules**: The rules above should be **merged** with the existing rules for `players/`, `duels/`, and `tournaments/` nodes. Do not replace existing rules.

3. **Signal Structure**: Each signal under `players/{playerId}/app_signals/{signalId}` has:
   - `action` (string): `"duel_accepted"`, `"duel_declined"`, `"duel_cancelled"`, or `"overlay_dismiss"`
   - `duel_id` (string): The UUID of the duel that was acted upon
   - `ts` (number): Unix timestamp in milliseconds when the action was taken

4. **Signal Lifecycle**: The desktop Watcher reads and then **deletes** processed signals by setting the `app_signals` node to `null` after processing. This prevents duplicate processing.

5. **Security Considerations**: Since the Watcher ecosystem uses unauthenticated access, the Firebase rules use `.read: true` and `.write: true` to match the existing pattern. If you want to add authentication in the future, update both the Watcher's `CloudSync` and the Android app's `FirebaseClient` to include auth tokens.
