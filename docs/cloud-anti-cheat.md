# Cloud Anti-Cheat Rules

This document describes both the **watcher-side responsibilities** and the
**server-side validation approach** used for cloud uploads (scores, achievement
progress) in the VPX Achievement Watcher.

---

## Watcher-Side Responsibilities

The watcher (this repository) is responsible for collecting and forwarding
reliable metadata to the server.  It is **not** responsible for being the
final arbiter of fair play — that role belongs to the server.

### What the watcher must do

1. **Include all required metadata fields** in every upload payload (see
   [Required Fields](#required-fields) below).
2. **Block uploads** when the player name is missing or set to the default
   `"Player"`.
3. **Block uploads** when no VPS-ID has been assigned to the ROM.  The ROM
   must be linked to a known VPS table entry before any cloud submission is
   allowed.
4. **Normalise the ROM name** using the VPinMAME ROM identifier so the server
   can cross-check it against the VPS entry.
5. **Enrich payloads with VPS context** where available: `vps_id`,
   `table_name`, `author`, `version` are added from the local VPS database
   cache when the ROM is linked.
6. **Surface the submission state** (`accepted` / `flagged` / `rejected`)
   returned by the server via the **Status Overlay** so the player receives
   immediate feedback.
7. **Apply local integrity protection** as a supporting signal (see
   [Local Integrity Protection](#local-integrity-protection) below).

### What the watcher must NOT claim

- The watcher must **not** make final `accepted` / `flagged` / `rejected`
  decisions.  Those decisions belong to the server.
- Local integrity checks (hash signatures, file validation) are **supporting
  signals only** — they help detect casual tampering or file corruption, but
  they are not proof that a submission is clean.
- Rate limiting, duplicate detection, event-window enforcement, and all
  cross-player comparisons are **server-side responsibilities**.

---

## Philosophy

The backend must **never blindly trust client uploads**.  
All data submitted by the client is treated as untrusted input and must be
validated server-side before being accepted, stored, or displayed on
leaderboards.

Client-side checks (e.g. local hash signatures) are useful as *indicators*
to the server and for transparency, but they are
**not sufficient proof** of a clean submission.  The definitive verdict always
comes from the server.

---

## Local Integrity Protection

In addition to server-side validation, the Watcher also uses local integrity
protection for saved data and score-related files.

This local protection is intended to:
- detect casual file tampering
- detect broken or corrupted local save/state files
- provide additional trust signals for cloud uploads

Examples include:
- hash-based protection of local save/state data
- integrity checks for locally stored score-related data before upload

**Important:**  
Local integrity protection is still entirely client-side.  
A modified client may bypass or recreate local integrity markers.

Because of that, local integrity checks must be treated as **supporting
signals**, not as final proof that a submission is legitimate.

Server-side validation always remains the authoritative anti-cheat layer.

---

## Required Fields

Every upload payload must contain all of the following fields.  Submissions
that are missing any required field should be **rejected** immediately.

| Field | Description |
|---|---|
| `name` | Player display name (non-empty, not the default `"Player"`) |
| `ts` | ISO-8601 UTC timestamp of the submission |
| `vps_id` | VPS database table ID (links the ROM to a known pinball table) |

Score-specific uploads additionally require:

| Field | Description |
|---|---|
| `score` | Positive integer score value |
| `rom` | ROM name as used by VPinMAME |

Achievement-progress uploads additionally require:

| Field | Description |
|---|---|
| `unlocked` | Number of unlocked achievements (≥ 0) |
| `total` | Total achievements for this ROM (> 0) |

---

## Validation Rules

### 1. Valid Player ID
- The player ID (`pid`) must exist as a known entity in the database.
- It must not be `"unknown"` or empty.
- The ID must match the authenticated session / API key used to submit.

### 2. Valid ROM
- The ROM name must not be empty or contain path-traversal characters.
- Optionally, it should be cross-checked against the VPS entry (`vps_id`)
  to ensure the combination is plausible.

### 3. Timestamp Sanity
- The `ts` field must be a parseable ISO-8601 UTC timestamp.
- Submissions with timestamps more than **5 minutes in the future** relative
  to the server clock should be **rejected** (clock skew tolerance).
- Submissions with timestamps **older than 30 days** should be **rejected**
  or at minimum flagged for review.

### 4. Duplicate Detection
- If a submission is identical (same player, ROM, category, score) within a
  short window (e.g. 60 seconds), the later submission should be deduplicated
  or rejected to prevent replay attacks.
- Challenge-specific key variants (e.g. `rom_f100` for a 100-flip run) should
  be considered separately.

### 5. Rate Limiting
- Uploads from a single player ID must be rate-limited per endpoint.
- Suggested limits: no more than **30 score uploads** and **60 achievement
  uploads** per hour per player.
- Exceeding the limit should result in a `429 Too Many Requests` response
  and the submission status being set to `"flagged"`.

### 6. Challenge-Specific Plausibility Checks
- For **Timed Challenges**, verify that the `target_time` value is a positive
  integer within the allowed range for that challenge type.
- For **Flip Challenges**, verify that `target_flips` is a positive integer
  and corresponds to a known difficulty tier.
- Scores that are mathematically impossible for the reported challenge
  parameters (e.g. a score of `999_999_999` with only 10 flips allowed)
  should be **flagged** for manual review.

### 7. Strict Weekly / Event Validation
- Weekly challenge submissions must include the correct `event_id` or
  `week_key` that was active at the time of the submission (within the
  event window).
- Submissions referencing an expired or future event window should be
  **rejected**.
- Only one winning submission per player per event period should be counted.

---

## Explicit Exception: Achievement / Progress Jumps

> **Large jumps in achievement count or progress percentage in a short time
> must NOT be treated as cheating by default.**

The VPX Achievement Watcher uses an NVRAM-trigger approach: when a game ends
(or when an NVRAM file changes), the system may legitimately unlock or sync
many achievements at once.  This is normal behaviour and is not an indicator
of tampering.

Therefore, **server-side rules must not flag or reject submissions solely
because the number of newly unlocked achievements is large**.  This exception
must be explicitly encoded in the validation logic so that it is not silently
re-introduced in future versions.

---

## Submission States

Each upload is assigned one of three states after server-side validation:

| State | Meaning |
|---|---|
| `accepted` | The submission passed all checks and is counted on the leaderboard. |
| `flagged` | The submission passed basic checks but triggered a plausibility heuristic and is held for manual review.  It is **not** displayed on the public leaderboard until reviewed. |
| `rejected` | The submission failed a hard validation rule (missing field, invalid ROM, duplicate, rate-limited, incompatible version, etc.) and is discarded. |

The server communicates the result back to the client.  The client surfaces
the state via the **Status Overlay** so the player receives immediate
feedback.

### Status Overlay Colours
- `accepted` → green (`#00C853`)
- `flagged` → orange (`#FFA500`)
- `rejected` → red (`#FF3B30`)

---

## Leaderboard Rendering

Leaderboard rendering code must respect the submission state:

- Only `accepted` entries should appear on the public leaderboard.
- `flagged` entries should be hidden or shown with a clear visual indicator
  (e.g. a warning badge) until reviewed.
- `rejected` entries should not be displayed at all.

Suspicious data must never be implicitly treated the same as normal data.

---

## Client-Side Responsibilities

See the [Watcher-Side Responsibilities](#watcher-side-responsibilities) section
at the top of this document for the full list of what the watcher does and does
not do.

In summary, the watcher is responsible for **collecting, enriching, and
forwarding** reliable metadata.  It surfaces the server's verdict via the
**Status Overlay**.  It is **not** responsible for being the final arbiter of
fair play — server-side validation is always authoritative.

---

## Minimum Client Version Enforcement

### Overview

The Firebase Realtime Database stores a **minimum required client version** at
the read-only node `meta/min_client_version` (e.g. `"3.1"`).  The watcher
reads this value once at startup on a background thread and compares it against
its own `WATCHER_VERSION`.  If the local version is below the minimum, the
watcher:

1. Disables all cloud **write** operations for the lifetime of the process
   (`cfg._cloud_blocked_by_version = True`).
2. Shows a **red, non-dismissable banner** at the top of the main window.
3. Shows a **modal "⛔ Update Required" dialog** once on startup.
4. Persists a Dashboard notification of type `update_required`.

**Read operations** (`fetch_*`) remain fully functional so users can still
browse leaderboards in read-only mode.

The server is the authoritative source of truth.  The client-side enforcement
above is the primary defence; the Firebase rules below are a backstop.

### Firebase Rules Snippet

```json
{
  "rules": {
    "meta": {
      "min_client_version": { ".read": true, ".write": false }
    },
    "players": {
      "$pid": {
        ".write": "query.client_version != null && root.child('meta/min_client_version').val() != null"
      }
    },
    "duels": {
      ".write": "query.client_version != null && root.child('meta/min_client_version').val() != null"
    }
  }
}
```

> **Limitation:** Firebase Realtime Database rules do not expose a built-in
> semantic version-comparison function.  The snippet above only validates that
> the `client_version` query parameter is *present* — it does not enforce a
> minimum value server-side.  Two practical options for full server enforcement:
>
> (a) **String-equality for major versions** — if you only ever block an entire
>     major release, a simple `query.client_version != "3.0"` rule suffices.
>
> (b) **Cloud Function write proxy** — replace direct Firebase REST writes with
>     an HTTPS Cloud Function that parses and compares the version string before
>     forwarding the write to the Realtime Database.
>
> The client-side guard (version-check at startup + write-blocking in all upload
> methods) is the primary defence; the Firebase rules are an additional backstop.

### Client version query parameter

Every write request from the watcher appends
`?client_version=<WATCHER_VERSION>` to the Firebase REST URL so that Firebase
rules (and any future Cloud Function proxy) can inspect the version without
parsing the request body.

### How to set the minimum version (maintainer steps)

1. Open the [Firebase Console](https://console.firebase.google.com/) and select
   the project used by the watcher.
2. Navigate to **Realtime Database → Data**.
3. Locate (or create) the `meta` node at the root of the database.
4. Add a child key `min_client_version` with the string value of the minimum
   version you want to enforce, e.g. `"3.1"`.
5. Save.  All watcher instances will pick up the new value within the same
   session (the value is fetched once per process start).

> **Example:** To block all clients older than v3.1, set
> `meta/min_client_version` to `"3.1"`.  Clients running v3.0, v2.x, etc.
> will immediately lose cloud write access after their next restart.
