# Cloud Anti-Cheat and Data Layout (Watcher 3.2+)

The cloud is a Firebase Realtime Database on the free Spark plan (no Cloud
Functions). All server-side protection lives in the database rules:
[`firebase/database.rules.json`](../firebase/database.rules.json).

## Identity

* Every Watcher signs in **anonymously** (Firebase Authentication, no user input).
* `owners/<pid>` = `{uid, key}` binds a Player ID to one sign-in. Only that
  sign-in may write `players/<pid>/…` and the index entries of `<pid>`.
  `owners` cannot be read by anyone.
* The first sign-in that claims a free ID owns it. Existing players claim their
  ID automatically on the first start of 3.2.
* The **recovery key** (`key`) moves an ID to another installation: a new
  sign-in may take over the ID only with the same key. It is shown in
  System → General and stored in *Backup to ZIP* (`cloud_identity.json`).
* `uids/<uid>` = `<pid>` (readable only by that sign-in) lets the rules map a
  sign-in to its ID.
* `names/<lowercase name>` = `<pid>` makes player names unique.
* An ID claimed by the wrong person can be freed by the admin by deleting
  `owners/<pid>` (and the matching `uids/<uid>`) in the console.

## What is stored

| Node | Content | Read | Write |
|---|---|---|---|
| `meta` | `min_client_version` | everyone | console only |
| `players/<pid>/achievements` | name, level, badges, global + per-ROM unlocks | everyone (single player) | owner |
| `players/<pid>/progress/<rom>` | unlocked / total / % per ROM | everyone (single player) | owner |
| `players/<pid>/progress_cat/<key>` | custom tables | everyone (single player) | owner |
| `players/<pid>/vps_mapping` | ROM → VPS-ID (restore) | everyone (single player) | owner |
| `lb/<rom>/<pid>` | leaderboard index (top-N query on `p`) | everyone | owner |
| `lb_cat/<key>/<pid>` | custom-table leaderboard index | everyone | owner |
| `lb_global/<pid>` | number of different achievements (top-N on `t`) | everyone | owner |
| `rarity/<rom>` | `players` + `c/<hash>` counters | everyone | +1 once per player |
| `rarity_claims/<rom>/<pid>` | what a player already counted | that player | that player |

The player list (`players`) and the database root cannot be read as a whole.
Everything else (duels, tournaments, scores, records, session stats,
preferences, rarity caches, app signals) is rejected by the rules.

## Validation in the rules

* Field whitelist and type/length limits for every node.
* `unlocked ≤ total`, `total ≤ 5000`, percentage must match `unlocked/total`.
* The leaderboard entry must equal the progress written in the same request.
* Rate limit: progress and index entries at most every 5 s (server time).
* Rarity counters only grow by exactly 1, only together with the player's
  claim, and only once per achievement and player.

## Watcher side

* All requests carry the sign-in token; writes go through one helper.
* Uploads are skipped when values are implausible (e.g. `unlocked > total`).
* **Local integrity:** protected files (`achievements_state.json`, session
  summaries) are signed. An unsigned or modified file is still loaded – nothing
  is thrown away – but cloud uploads stay blocked until the player restores from
  the cloud or from a valid ZIP backup. A damaged file falls back to its `.bak`
  copy. The local signature only detects casual edits; the rules are the real
  protection.
* Old Watcher versions cannot write any more (no sign-in). Set
  `meta/min_client_version` to the new version at release.

## Traffic

* Leaderboards: top 25 per ROM / top 50 overall + own entry – constant size,
  independent of the number of players.
* Rarity: one small counter node per ROM, cached for 24 h.
* No periodic polling (the Android-app polling and the hidden duel polling are
  gone).
