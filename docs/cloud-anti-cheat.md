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
