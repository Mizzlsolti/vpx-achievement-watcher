"""tournament_engine.py – Tournament mode backend for Score Duels.

Manages a 4-player single-elimination tournament queue and bracket
orchestration.  Uses the existing DuelEngine for individual 1v1 matches.

Cloud structure
---------------
tournaments/queue/{player_id}
    { player_name, vps_ids[], queued_at, expires_at }

tournaments/active/{tournament_id}
    {
        tournament_id,
        participants: [{player_id, player_name}, ...],  // always 4
        table_rom,
        table_name,
        bracket: {
            semifinal: [
                { duel_id, player_a, player_a_name, player_b, player_b_name,
                  winner, winner_name, score_a, score_b },
                { ... }
            ],
            final: { duel_id, player_a, player_a_name, player_b, player_b_name,
                     winner, winner_name, score_a, score_b }
        },
        status: "semifinal" | "final" | "completed",
        winner, winner_name,
        created_at, completed_at
    }
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from itertools import combinations
from typing import List, Optional

from .config import p_session, f_romnames
from .cloud_sync import CloudSync
from .duel_engine import DuelEngine, DuelStatus
from .watcher_core import log
from .watcher_io import load_json

# ── Constants ─────────────────────────────────────────────────────────────────

TOURNAMENT_QUEUE_TTL = 600    # 10 minutes – queue entry lifetime
TOURNAMENT_MATCH_TTL = 7200   # 2 hours  – per-match duel lifetime
TOURNAMENT_SIZE      = 4      # fixed 4-player bracket
TOURNAMENT_TTL       = 14400  # 4 hours  – active tournament lifetime (2h SF + 2h final)

_CONFIRM_HINT = "<small>Press left [← Duel Accept] to confirm</small>"


def _clean_table_name(raw: str) -> str:
    """Return a clean table name without version, manufacturer, or year suffixes."""
    try:
        from .watcher_core import _strip_version_from_name
        name = _strip_version_from_name(raw)
    except Exception:
        name = raw
    if "(" in name:
        name = name[: name.index("(")].strip()
    return name or raw


class TournamentEngine:
    """Backend engine for Tournament mode.

    Parameters
    ----------
    cfg : AppConfig
        Application configuration instance.
    duel_engine : DuelEngine
        The active DuelEngine used for 1v1 match management.
    """

    def __init__(self, cfg, duel_engine: DuelEngine) -> None:
        self._cfg = cfg
        self._duel_engine = duel_engine
        self._lock = threading.RLock()
        self._history: list = []
        self._shown_notifications: set = set()
        self._load_local()

    # ── Paths ─────────────────────────────────────────────────────────────────

    def _p_tournaments(self) -> str:
        return os.path.join(p_session(self._cfg), "tournaments")

    def _f_history(self) -> str:
        return os.path.join(self._p_tournaments(), "tournament_history.json")

    def _f_notifications(self) -> str:
        return os.path.join(self._p_tournaments(), "shown_notifications.json")

    # ── Local persistence ─────────────────────────────────────────────────────

    def _load_local(self) -> None:
        try:
            if os.path.isfile(self._f_history()):
                with open(self._f_history(), encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._history = raw if isinstance(raw, list) else []
        except Exception:
            self._history = []
        try:
            if os.path.isfile(self._f_notifications()):
                with open(self._f_notifications(), encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._shown_notifications = set(raw) if isinstance(raw, list) else set()
        except Exception:
            self._shown_notifications = set()

    def _save_history(self) -> None:
        try:
            os.makedirs(self._p_tournaments(), exist_ok=True)
            with open(self._f_history(), "w", encoding="utf-8") as fh:
                json.dump(self._history, fh, indent=2)
        except Exception:
            pass

    def _save_notifications(self) -> None:
        try:
            os.makedirs(self._p_tournaments(), exist_ok=True)
            with open(self._f_notifications(), "w", encoding="utf-8") as fh:
                json.dump(list(self._shown_notifications), fh)
        except Exception:
            pass

    # ── Player helpers ────────────────────────────────────────────────────────

    def _my_player_id(self) -> str:
        return str(self._cfg.OVERLAY.get("player_id", "")).strip()

    def _my_player_name(self) -> str:
        return str(self._cfg.OVERLAY.get("player_name", "Player")).strip()

    # ── Notification tracking ─────────────────────────────────────────────────

    def is_notification_shown(self, tournament_id: str, event: str) -> bool:
        """Return True if this (tournament_id, event) notification was already shown."""
        return f"{tournament_id}:{event}" in self._shown_notifications

    def mark_notification_shown(self, tournament_id: str, event: str) -> None:
        """Mark a notification as shown so it is not displayed again."""
        self._shown_notifications.add(f"{tournament_id}:{event}")
        self._save_notifications()

    # ── Queue management ──────────────────────────────────────────────────────

    def join_queue(self) -> bool:
        """Write this player's entry to the tournament queue cloud node.

        Returns True on success.
        """
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            log(self._cfg, "[TOURNAMENT] join_queue: Cloud Sync is disabled.", "WARN")
            return False
        my_id = self._my_player_id()
        if not my_id:
            log(self._cfg, "[TOURNAMENT] join_queue: player_id not configured.", "WARN")
            return False
        try:
            from ui.vps import _load_vps_mapping
            vps_mapping = _load_vps_mapping(self._cfg)
        except Exception as exc:
            log(self._cfg, f"[TOURNAMENT] join_queue: could not load VPS mapping: {exc}", "WARN")
            vps_mapping = {}
        # vps_ids intentionally stores VPS-ID values (not ROM keys) so that the
        # intersection logic in poll_queue() can compare sets of VPS-ID strings.
        vps_ids = list(vps_mapping.values())
        if not vps_ids:
            log(self._cfg, "[TOURNAMENT] join_queue: no VPS-IDs found.", "WARN")
            return False
        now = time.time()
        entry = {
            "player_id":   my_id,
            "player_name": self._my_player_name(),
            "vps_ids":     vps_ids,
            "queued_at":   now,
            "expires_at":  now + TOURNAMENT_QUEUE_TTL,
        }
        ok = CloudSync.set_node(self._cfg, f"tournaments/queue/{my_id}", entry)
        if ok:
            log(self._cfg, f"[TOURNAMENT] Joined queue with {len(vps_ids)} VPS-IDs.")
        else:
            log(self._cfg, "[TOURNAMENT] join_queue: cloud write failed.", "WARN")
        return ok

    def leave_queue(self) -> bool:
        """Remove this player's entry from the tournament queue.

        Returns True on success (including when no entry existed).
        """
        my_id = self._my_player_id()
        if not my_id:
            return True
        ok = CloudSync.set_node(self._cfg, f"tournaments/queue/{my_id}", None)
        if ok:
            log(self._cfg, "[TOURNAMENT] Left queue.")
        else:
            log(self._cfg, "[TOURNAMENT] leave_queue: cloud delete failed.", "WARN")
        return ok

    # ── Tournament duel creation ──────────────────────────────────────────────

    def _create_tournament_duel(
        self,
        player_a_id: str, player_a_name: str,
        player_b_id: str, player_b_name: str,
        table_rom: str, table_name: str,
    ) -> Optional[str]:
        """Write a tournament duel record directly to cloud with ACCEPTED status.

        Returns the duel_id on success, None on failure.
        """
        duel_id = str(uuid.uuid4())
        now = time.time()
        duel_data = {
            "duel_id":          duel_id,
            "challenger":       player_a_id,
            "challenger_name":  player_a_name,
            "opponent":         player_b_id,
            "opponent_name":    player_b_name,
            "table_rom":        table_rom.lower().strip(),
            "table_name":       table_name,
            "status":           DuelStatus.ACCEPTED,
            "created_at":       now,
            "accepted_at":      now,
            "expires_at":       now + TOURNAMENT_MATCH_TTL,
            "completed_at":     0.0,
            "challenger_score": -1,
            "opponent_score":   -1,
            "cancel_reason":    "",
        }
        ok = CloudSync.set_node(self._cfg, f"duels/{duel_id}", duel_data)
        if not ok:
            log(self._cfg, "[TOURNAMENT] _create_tournament_duel: cloud write failed.", "WARN")
            return None
        # Register locally if the current player is one of the participants.
        my_id = self._my_player_id()
        if my_id in (player_a_id, player_b_id):
            self._duel_engine.register_cloud_duel(duel_id)
        return duel_id

    # ── Tournament creation ───────────────────────────────────────────────────

    def _create_tournament(self, players: list, shared_vps_ids: set) -> Optional[dict]:
        """Create a new tournament record in the cloud.

        Parameters
        ----------
        players : list
            Exactly TOURNAMENT_SIZE player dicts, each containing
            ``player_id``, ``player_name``, ``vps_ids``, ``queued_at``.
        shared_vps_ids : set
            VPS-IDs held by all players (used to pick the table).

        Returns
        -------
        dict
            The tournament record on success.
        None
            On failure.
        """
        # Load the VPS-ID → ROM mapping to resolve a table_rom from the chosen VPS-ID.
        try:
            from ui.vps import _load_vps_mapping
            vps_mapping = _load_vps_mapping(self._cfg)
        except Exception:
            vps_mapping = {}

        chosen_vps_id = random.choice(list(shared_vps_ids))
        table_rom = next(
            (rom for rom, vid in vps_mapping.items() if vid == chosen_vps_id),
            "",
        )
        if not table_rom:
            log(self._cfg, f"[TOURNAMENT] _create_tournament: no ROM for VPS-ID {chosen_vps_id}.", "WARN")
            return None

        # Resolve a clean human-readable table name from romnames.json.
        try:
            romnames: dict = load_json(f_romnames(self._cfg), {}) or {}
            table_name = _clean_table_name(romnames.get(table_rom) or table_rom)
        except Exception:
            table_name = _clean_table_name(table_rom)

        # Random bracket pairings.
        shuffled = list(players)
        random.shuffle(shuffled)
        participants = [
            {"player_id": p["player_id"], "player_name": p["player_name"]}
            for p in shuffled
        ]

        # Semifinal 1: participants[0] vs participants[1]
        sf1_id = self._create_tournament_duel(
            participants[0]["player_id"], participants[0]["player_name"],
            participants[1]["player_id"], participants[1]["player_name"],
            table_rom, table_name,
        )
        if not sf1_id:
            return None

        # Semifinal 2: participants[2] vs participants[3]
        sf2_id = self._create_tournament_duel(
            participants[2]["player_id"], participants[2]["player_name"],
            participants[3]["player_id"], participants[3]["player_name"],
            table_rom, table_name,
        )
        if not sf2_id:
            return None

        tournament_id = str(uuid.uuid4())
        now = time.time()
        tournament = {
            "tournament_id": tournament_id,
            "participants":  participants,
            "table_rom":     table_rom.lower().strip(),
            "table_name":    table_name,
            "bracket": {
                "semifinal": [
                    {
                        "duel_id":      sf1_id,
                        "player_a":     participants[0]["player_id"],
                        "player_a_name": participants[0]["player_name"],
                        "player_b":     participants[1]["player_id"],
                        "player_b_name": participants[1]["player_name"],
                        "winner":       "",
                        "winner_name":  "",
                        "score_a":      -1,
                        "score_b":      -1,
                    },
                    {
                        "duel_id":      sf2_id,
                        "player_a":     participants[2]["player_id"],
                        "player_a_name": participants[2]["player_name"],
                        "player_b":     participants[3]["player_id"],
                        "player_b_name": participants[3]["player_name"],
                        "winner":       "",
                        "winner_name":  "",
                        "score_a":      -1,
                        "score_b":      -1,
                    },
                ],
                "final": {},
            },
            "status":       "semifinal",
            "winner":       "",
            "winner_name":  "",
            "created_at":   now,
            "completed_at": 0.0,
        }

        ok = CloudSync.set_node(self._cfg, f"tournaments/active/{tournament_id}", tournament)
        if not ok:
            log(self._cfg, f"[TOURNAMENT] _create_tournament: cloud write failed for {tournament_id}.", "WARN")
            return None

        log(self._cfg, f"[TOURNAMENT] Created tournament {tournament_id} on '{table_name}'.")
        return tournament

    # ── Queue polling ─────────────────────────────────────────────────────────

    def poll_queue(self) -> dict:
        """Poll the tournament queue and possibly start a tournament.

        When exactly TOURNAMENT_SIZE players sharing at least one table are
        found in the queue, the designated creator (player with the
        lex-smallest player_id, consistent with ``_maybe_advance_to_final()``)
        creates the tournament and removes all queue entries.

        Returns
        -------
        dict
            Keys:

            ``in_queue`` : bool
                Whether the local player is currently queued.
            ``queue_players`` : list[dict]
                Other players in queue (``{player_id, player_name}``).
            ``queue_count`` : int
                Total number of valid queue entries including self.
            ``tournament_started`` : bool
                True when a tournament was just created by this call.
            ``tournament`` : dict or None
                The new tournament record if ``tournament_started`` is True.
            ``error`` : str
                Non-empty string on failure.
        """
        _empty = {
            "in_queue": False, "queue_players": [], "queue_count": 0,
            "tournament_started": False, "tournament": None, "error": "",
        }

        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            return {**_empty, "error": "cloud_disabled"}

        my_id = self._my_player_id()
        if not my_id:
            return {**_empty, "error": "no_player_id"}

        try:
            all_entries = CloudSync.fetch_node(self._cfg, "tournaments/queue")
        except Exception as exc:
            return {**_empty, "error": str(exc)}

        if not isinstance(all_entries, dict):
            all_entries = {}

        now = time.time()
        valid: dict = {
            pid: e
            for pid, e in all_entries.items()
            if isinstance(e, dict) and float(e.get("expires_at", 0)) >= now
        }

        in_queue = my_id in valid
        queue_players = [
            {"player_id": pid, "player_name": e.get("player_name", pid)}
            for pid, e in valid.items()
            if pid != my_id
        ]

        if not in_queue or len(valid) < TOURNAMENT_SIZE:
            return {
                "in_queue": in_queue,
                "queue_players": queue_players,
                "queue_count": len(valid),
                "tournament_started": False,
                "tournament": None,
                "error": "",
            }

        # Try every combination of TOURNAMENT_SIZE players with a shared table.
        all_valid_list = list(valid.items())
        group: Optional[tuple] = None
        shared: Optional[set] = None

        for combo in combinations(all_valid_list, TOURNAMENT_SIZE):
            sets = [set(e.get("vps_ids") or []) for _, e in combo]
            common = sets[0]
            for s in sets[1:]:
                common = common & s
            if common:
                group = combo
                shared = common
                break

        if group is None or not shared:
            return {
                "in_queue": in_queue,
                "queue_players": queue_players,
                "queue_count": len(valid),
                "tournament_started": False,
                "tournament": None,
                "error": "",
            }

        group_ids = {pid for pid, _ in group}

        # Only proceed if the local player is part of the matched group.
        if my_id not in group_ids:
            return {
                "in_queue": in_queue,
                "queue_players": queue_players,
                "queue_count": len(valid),
                "tournament_started": False,
                "tournament": None,
                "error": "",
            }

        # Deterministic creator selection: lex-smallest player_id (consistent with
        # _maybe_advance_to_final() which also uses min(player_id) as coordinator).
        creator_id = min(group_ids)
        if creator_id != my_id:
            return {
                "in_queue": in_queue,
                "queue_players": queue_players,
                "queue_count": len(valid),
                "tournament_started": False,
                "tournament": None,
                "error": "",
            }

        result_base = {
            "in_queue": in_queue,
            "queue_players": queue_players,
            "queue_count": len(valid),
        }

        # Duplicate-tournament guard: skip creation if an active tournament
        # already contains all players from the matched group.
        try:
            all_tournaments = CloudSync.fetch_node(self._cfg, "tournaments/active")
            if isinstance(all_tournaments, dict):
                for _tid, _t in all_tournaments.items():
                    if not isinstance(_t, dict):
                        continue
                    t_pids = {p.get("player_id") for p in (_t.get("participants") or [])}
                    if group_ids <= t_pids:
                        log(self._cfg,
                            f"[TOURNAMENT] poll_queue: skipping creation — tournament {_tid} "
                            f"already exists for this group.")
                        # Clean up queue entries anyway so the queue stays tidy.
                        for pid in group_ids:
                            CloudSync.set_node(self._cfg, f"tournaments/queue/{pid}", None)
                        return {**result_base, "in_queue": False, "tournament_started": False,
                                "tournament": None, "error": ""}
        except Exception:
            pass

        # Delete-first, then create: removes the race-condition window where
        # other players' poll_queue() calls could still see the same 4 entries
        # after this player starts creating the tournament.
        deleted_entries: dict = {}  # pid -> entry (for rollback)
        failed_deletions: list = []
        for pid in group_ids:
            ok = CloudSync.set_node(self._cfg, f"tournaments/queue/{pid}", None)
            if ok:
                deleted_entries[pid] = valid[pid]
            else:
                # Retry once.
                ok = CloudSync.set_node(self._cfg, f"tournaments/queue/{pid}", None)
                if ok:
                    deleted_entries[pid] = valid[pid]
                else:
                    failed_deletions.append(pid)

        if failed_deletions:
            log(self._cfg,
                f"[TOURNAMENT] poll_queue: queue deletion failed for {failed_deletions}; "
                f"rolling back {list(deleted_entries.keys())}.", "WARN")
            # Rollback: re-add entries that were successfully deleted.
            for pid, entry in deleted_entries.items():
                CloudSync.set_node(self._cfg, f"tournaments/queue/{pid}", entry)
            return {**result_base, "tournament_started": False, "tournament": None,
                    "error": "create_failed"}

        # I am the creator – build the tournament.
        players = [
            {
                "player_id":   pid,
                "player_name": valid[pid].get("player_name", pid),
                "vps_ids":     valid[pid].get("vps_ids", []),
                "queued_at":   float(valid[pid].get("queued_at", 0)),
            }
            for pid, _ in group
        ]

        tournament = self._create_tournament(players, shared)
        if not tournament:
            return {**result_base, "tournament_started": False, "tournament": None,
                    "error": "create_failed"}

        return {
            "in_queue":           False,
            "queue_players":      [],
            "queue_count":        0,
            "tournament_started": True,
            "tournament":         tournament,
            "error":              "",
        }

    # ── Active-tournament polling ─────────────────────────────────────────────

    def poll_active_tournament(self) -> Optional[dict]:
        """Fetch and advance the active tournament for this player.

        Ensures tournament duels are registered in the DuelEngine, advances the
        bracket from semifinal → final when both SFs are complete, and marks
        the tournament as completed when the final is done.

        Returns
        -------
        dict
            The (possibly updated) tournament record.
        None
            When no active tournament exists for the local player.
        """
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            return None
        my_id = self._my_player_id()
        if not my_id:
            return None

        try:
            all_tournaments = CloudSync.fetch_node(self._cfg, "tournaments/active")
        except Exception:
            return None

        if not isinstance(all_tournaments, dict):
            return None

        now = time.time()
        my_id_str = my_id  # already resolved above

        # ── TTL-based cleanup of expired tournaments ──────────────────────────
        # Run BEFORE the "find my tournament" loop so that an expired tournament
        # for this player is removed before it could be picked up as active.
        for tid, t in list(all_tournaments.items()):
            if not isinstance(t, dict):
                continue
            created_at = float(t.get("created_at") or 0)
            if created_at <= 0 or (now - created_at) < TOURNAMENT_TTL:
                continue
            age_hours = (now - created_at) / 3600.0
            participants = t.get("participants") or []
            participant_ids = [p.get("player_id") for p in participants]
            is_participant = my_id_str in participant_ids
            if not is_participant:
                continue
            # Only the coordinator (lex-smallest player_id) performs the deletion.
            coordinator_id = min((p for p in participant_ids if p), default="")
            if my_id_str != coordinator_id:
                continue
            # If this was our own active tournament, save it to history first.
            if t.get("status") != "completed":
                expired_record = dict(t)
                expired_record["tournament_id"] = tid
                expired_record["status"] = "expired"
                with self._lock:
                    if not any(h.get("tournament_id") == tid for h in self._history):
                        self._history.append(expired_record)
                        self._save_history()
            CloudSync.set_node(self._cfg, f"tournaments/active/{tid}", None)
            log(self._cfg,
                f"[TOURNAMENT] Cleaned up expired tournament {tid} (age: {age_hours:.1f}h)",
                "WARN")
            # Remove it from the local snapshot so it is not picked up below.
            all_tournaments.pop(tid, None)
        # ─────────────────────────────────────────────────────────────────────

        # Find the tournament this player is participating in.
        my_tournament: Optional[dict] = None
        for tid, t in all_tournaments.items():
            if not isinstance(t, dict):
                continue
            if any(p.get("player_id") == my_id for p in (t.get("participants") or [])):
                my_tournament = t
                my_tournament.setdefault("tournament_id", tid)
                break

        if my_tournament is None:
            return None

        # Ensure all related duels are in the local DuelEngine.
        self._sync_tournament_duels(my_tournament)

        status = my_tournament.get("status", "semifinal")
        if status == "semifinal":
            my_tournament = self._maybe_advance_to_final(my_tournament)
        elif status == "final":
            my_tournament = self._maybe_complete_tournament(my_tournament)

        return my_tournament

    # ── Bracket advancement helpers ───────────────────────────────────────────

    def _sync_tournament_duels(self, tournament: dict) -> None:
        """Register any tournament duel IDs not yet in the local DuelEngine."""
        bracket = tournament.get("bracket") or {}
        duel_ids: List[str] = [
            sf.get("duel_id", "")
            for sf in (bracket.get("semifinal") or [])
        ]
        final = bracket.get("final") or {}
        if final.get("duel_id"):
            duel_ids.append(final["duel_id"])
        for duel_id in duel_ids:
            if duel_id:
                self._duel_engine.register_cloud_duel(duel_id)

    def _fetch_duel_from_cloud(self, duel_id: str) -> Optional[dict]:
        """Fetch a duel record from the cloud and return it as a dict, or None."""
        if not duel_id:
            return None
        try:
            data = CloudSync.fetch_node(self._cfg, f"duels/{duel_id}")
            return data if isinstance(data, dict) else None
        except Exception as exc:
            log(self._cfg, f"[TOURNAMENT] _fetch_duel_from_cloud error for {duel_id}: {exc}", "WARN")
            return None

    def _resolve_match_winner(
        self,
        duel_data: dict,
        player_a_id: str,
        player_b_id: str,
    ) -> Optional[tuple]:
        """Determine the winner of a completed duel.

        Returns
        -------
        tuple ``(winner_id, winner_name, score_a, score_b, forfeit)``
            Where score_a / score_b correspond to player_a / player_b, and
            ``forfeit`` is True when neither player submitted a score (e.g.
            EXPIRED or CANCELLED match where both raw scores were -1).
        None
            When the duel is not yet complete.
        """
        _terminal = {
            DuelStatus.WON, DuelStatus.LOST, DuelStatus.TIE,
            DuelStatus.EXPIRED, DuelStatus.CANCELLED,
        }
        status = duel_data.get("status")
        if status not in _terminal:
            return None

        ch_id   = duel_data.get("challenger", "")
        ch_name = duel_data.get("challenger_name", "")
        op_id   = duel_data.get("opponent", "")
        op_name = duel_data.get("opponent_name", "")

        raw_ch_score = int(duel_data.get("challenger_score", 0) or 0)
        raw_op_score = int(duel_data.get("opponent_score", 0) or 0)

        # Detect forfeit: expired/cancelled match where neither player played.
        forfeit = (
            status in (DuelStatus.EXPIRED, DuelStatus.CANCELLED)
            and raw_ch_score <= 0
            and raw_op_score <= 0
        )
        if forfeit:
            log(self._cfg,
                f"[TOURNAMENT] _resolve_match_winner: duel {duel_data.get('duel_id', '?')} "
                f"was {status} with no scores submitted – advancing bracket as forfeit "
                f"(challenger {ch_id} wins by default).",
                "WARN")

        ch_score = max(0, raw_ch_score)
        op_score = max(0, raw_op_score)

        # Map challenger/opponent scores to player_a/player_b.
        if ch_id == player_a_id:
            score_a, score_b = ch_score, op_score
        else:
            score_a, score_b = op_score, ch_score

        # Challenger wins on tie (per tournament rules).
        if ch_score >= op_score:
            winner_id, winner_name = ch_id, ch_name
        else:
            winner_id, winner_name = op_id, op_name

        return winner_id, winner_name, score_a, score_b, forfeit

    def _maybe_advance_to_final(self, tournament: dict) -> dict:
        """Advance the tournament from 'semifinal' → 'final' if both SFs are done."""
        bracket     = tournament.get("bracket") or {}
        semifinals  = bracket.get("semifinal") or []
        if len(semifinals) < 2:
            return tournament

        # Check both SF duels from the cloud.
        sf_results = []
        for sf in semifinals:
            data = self._fetch_duel_from_cloud(sf.get("duel_id", ""))
            if data is None:
                return tournament
            result = self._resolve_match_winner(
                data, sf.get("player_a", ""), sf.get("player_b", "")
            )
            if result is None:
                return tournament  # Not done yet.
            sf_results.append(result)

        # Update SF slots with results.
        for i, (wid, wname, sa, sb, _forfeit) in enumerate(sf_results):
            semifinals[i].update(winner=wid, winner_name=wname, score_a=sa, score_b=sb)

        # Guard: final may have been created concurrently by another participant.
        if bracket.get("final", {}).get("duel_id"):
            tournament["bracket"] = bracket
            return tournament

        # Only the coordinator (lex-smallest player_id) creates the final.
        my_id = self._my_player_id()
        participants = tournament.get("participants") or []
        coordinator_id = min(
            (p["player_id"] for p in participants), default=""
        )
        if my_id != coordinator_id:
            tournament["bracket"] = bracket
            return tournament

        finalist_a_id,   finalist_a_name, *_ = sf_results[0]
        finalist_b_id,   finalist_b_name, *_ = sf_results[1]
        table_rom  = tournament.get("table_rom", "")
        table_name = tournament.get("table_name", "")

        final_duel_id = self._create_tournament_duel(
            finalist_a_id, finalist_a_name,
            finalist_b_id, finalist_b_name,
            table_rom, table_name,
        )
        if not final_duel_id:
            return tournament

        bracket["final"] = {
            "duel_id":      final_duel_id,
            "player_a":     finalist_a_id,
            "player_a_name": finalist_a_name,
            "player_b":     finalist_b_id,
            "player_b_name": finalist_b_name,
            "winner":       "",
            "winner_name":  "",
            "score_a":      -1,
            "score_b":      -1,
        }
        tournament["status"]  = "final"
        tournament["bracket"] = bracket

        tid = tournament.get("tournament_id", "")
        CloudSync.set_node(self._cfg, f"tournaments/active/{tid}", tournament)
        log(self._cfg, f"[TOURNAMENT] Advanced to final. Duel: {final_duel_id}")
        return tournament

    def _maybe_complete_tournament(self, tournament: dict) -> dict:
        """Mark the tournament as 'completed' when the final duel is done."""
        bracket  = tournament.get("bracket") or {}
        final    = bracket.get("final") or {}
        duel_id  = final.get("duel_id", "")
        if not duel_id:
            return tournament

        data = self._fetch_duel_from_cloud(duel_id)
        if data is None:
            return tournament
        result = self._resolve_match_winner(
            data, final.get("player_a", ""), final.get("player_b", "")
        )
        if result is None:
            return tournament  # Final not done yet.

        winner_id, winner_name, score_a, score_b, _forfeit = result
        final.update(winner=winner_id, winner_name=winner_name, score_a=score_a, score_b=score_b)
        bracket["final"] = final

        tournament["status"]       = "completed"
        tournament["winner"]       = winner_id
        tournament["winner_name"]  = winner_name
        tournament["completed_at"] = time.time()
        tournament["bracket"]      = bracket

        tid = tournament.get("tournament_id", "")
        CloudSync.set_node(self._cfg, f"tournaments/active/{tid}", tournament)

        # Save to local history (dedup by tournament_id).
        with self._lock:
            if not any(h.get("tournament_id") == tid for h in self._history):
                self._history.append(dict(tournament))
                self._save_history()

        # Remove the completed tournament from the cloud to prevent unbounded growth
        # of tournaments/active (poll_active_tournament fetches ALL entries every 30 s).
        if tid:
            CloudSync.set_node(self._cfg, f"tournaments/active/{tid}", None)

        log(self._cfg, f"[TOURNAMENT] Completed. Winner: {winner_name}")
        return tournament

    # ── Pending-notification generation ──────────────────────────────────────

    @staticmethod
    def _match_scores_for_player(match: dict, my_id: str) -> tuple:
        """Return ``(my_score, their_score)`` from a bracket match slot.

        Works for both semifinal and final dicts that carry
        ``player_a``, ``player_b``, ``score_a``, ``score_b``.
        Negative sentinel values (-1) are normalised to 0.
        """
        raw_a = int(match.get("score_a", 0) or 0)
        raw_b = int(match.get("score_b", 0) or 0)
        score_a = max(0, raw_a)
        score_b = max(0, raw_b)
        if match.get("player_a") == my_id:
            return score_a, score_b
        return score_b, score_a

    def get_pending_notifications(self, tournament: dict) -> list:
        """Return a list of ``(event, html_msg)`` tuples for unseen notifications.

        At most one notification is returned per call.  The caller should call
        :meth:`mark_notification_shown` once the notification has been queued
        for display.

        Notification order
        ------------------
        1. ``"started"``      – tournament just started (SF opponent announced)
        2. ``"eliminated"``   – lost in semifinal
        3. ``"final_reached"`` – reached the final
        4. ``"outcome"``      – won or lost the final
        """
        my_id = self._my_player_id()
        tid   = tournament.get("tournament_id", "")
        if not tid or not my_id:
            return []

        bracket    = tournament.get("bracket") or {}
        semifinals = bracket.get("semifinal") or []
        final      = bracket.get("final") or {}
        status     = tournament.get("status", "")
        table_name = tournament.get("table_name", "")

        # 1. Tournament started.
        if not self.is_notification_shown(tid, "started"):
            opponent_name = ""
            for sf in semifinals:
                if sf.get("player_a") == my_id:
                    opponent_name = sf.get("player_b_name", "?")
                    break
                if sf.get("player_b") == my_id:
                    opponent_name = sf.get("player_a_name", "?")
                    break
            msg = (
                "<div style='text-align:center'>"
                "🏆 Tournament started!<br>"
                f"🎰 <b>{table_name}</b><br><br>"
                f"⚔️ Your first match: against <b>{opponent_name}</b><br>"
                "⏳ You have 2 hours to play<br><br>"
                f"{_CONFIRM_HINT}"
                "</div>"
            )
            return [("started", msg)]

        # 2. Eliminated in semifinal.
        if not self.is_notification_shown(tid, "eliminated"):
            my_sf = next(
                (sf for sf in semifinals
                 if sf.get("player_a") == my_id or sf.get("player_b") == my_id),
                None,
            )
            if my_sf and my_sf.get("winner") and my_sf["winner"] != my_id:
                opp_name = my_sf.get("winner_name", "?")
                my_score, their_score = self._match_scores_for_player(my_sf, my_id)
                msg = (
                    "<div style='text-align:center'>"
                    "💀 Eliminated in the semifinal<br>"
                    f"🎰 <b>{table_name}</b><br><br>"
                    f"<b>{opp_name}</b> wins with {their_score:,}<br>"
                    f"Your score: {my_score:,}<br><br>"
                    f"{_CONFIRM_HINT}"
                    "</div>"
                )
                return [("eliminated", msg)]

        # 3. Reached the final.
        if not self.is_notification_shown(tid, "final_reached") and status in ("final", "completed"):
            final_players = {final.get("player_a"), final.get("player_b")}
            if my_id in final_players:
                opp_name = (
                    final.get("player_b_name", "?")
                    if my_id == final.get("player_a")
                    else final.get("player_a_name", "?")
                )
                msg = (
                    "<div style='text-align:center'>"
                    "🏆 FINAL!<br>"
                    f"🎰 <b>{table_name}</b><br><br>"
                    f"⚔️ Your opponent: <b>{opp_name}</b><br>"
                    "⏳ You have 2 hours to play<br><br>"
                    f"{_CONFIRM_HINT}"
                    "</div>"
                )
                return [("final_reached", msg)]

        # 4. Final outcome (only once tournament is completed).
        if status == "completed" and not self.is_notification_shown(tid, "outcome"):
            final_players = {final.get("player_a"), final.get("player_b")}
            if my_id in final_players:
                if tournament.get("winner") == my_id:
                    msg = (
                        "<div style='text-align:center'>"
                        "🏆 TOURNAMENT CHAMPION!<br>"
                        f"🎰 <b>{table_name}</b><br><br>"
                        "You won the tournament!<br><br>"
                        f"{_CONFIRM_HINT}"
                        "</div>"
                    )
                else:
                    opp_name = final.get("winner_name", "?")
                    my_score, their_score = self._match_scores_for_player(final, my_id)
                    msg = (
                        "<div style='text-align:center'>"
                        "💀 Final lost – Place #2<br>"
                        f"🎰 <b>{table_name}</b><br><br>"
                        f"<b>{opp_name}</b> wins with {their_score:,}<br>"
                        f"Your score: {my_score:,}<br><br>"
                        f"{_CONFIRM_HINT}"
                        "</div>"
                    )
                return [("outcome", msg)]

        return []

    # ── History ───────────────────────────────────────────────────────────────

    def get_history(self) -> list:
        """Return completed tournament records (newest first)."""
        with self._lock:
            return list(reversed(self._history))

    def get_my_placement(self, tournament: dict) -> str:
        """Return the placement string for the local player in a completed tournament."""
        my_id  = self._my_player_id()
        bracket = tournament.get("bracket") or {}
        final   = bracket.get("final") or {}
        final_players = {final.get("player_a"), final.get("player_b")}
        if tournament.get("winner") == my_id:
            return "🏆 Winner"
        if my_id in final_players:
            return "#2"
        return "#3-4"
