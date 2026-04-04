"""duel_engine.py – Backend engine for Score Duel lifecycle management.

Handles sending/receiving duel invitations, timer management,
table validation, result evaluation, and status transitions.
Duels are stored locally as JSON files and synced via the cloud.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union

import sound
from config import p_session
from cloud_sync import CloudSync
from watcher_core import log


class DuelStatus:
    """Possible states for a Score Duel."""
    PENDING   = "pending"
    ACCEPTED  = "accepted"
    ACTIVE    = "active"
    WON       = "won"
    LOST      = "lost"
    DRAW      = "draw"
    EXPIRED   = "expired"
    DECLINED  = "declined"
    CANCELLED = "cancelled"


# Invitation expires after 15 minutes if not accepted.
INVITATION_TTL_SECONDS = 900

# Accepted/active duels expire after 24 hours if no score is submitted.
ACTIVE_DUEL_TTL_SECONDS = 86_400

# Sentinel value indicating a score has not yet been submitted.
SCORE_NOT_SUBMITTED = -1


@dataclass
class Duel:
    """Data model for a single Score Duel."""
    duel_id:          str   # unique UUID
    challenger:       str   # player_id of challenger
    challenger_name:  str   # display name of challenger
    opponent:         str   # player_id of opponent
    opponent_name:    str   # display name of opponent
    table_rom:        str   # ROM name of the table
    table_name:       str   # display name of the table
    status:           str   # DuelStatus value
    created_at:       float # Unix timestamp of creation
    accepted_at:      float = 0.0   # Unix timestamp when accepted (0 = not yet)
    completed_at:     float = 0.0   # Unix timestamp when completed (0 = not yet)
    challenger_score: int   = -1    # final score of challenger (-1 = not yet submitted)
    opponent_score:   int   = -1    # final score of opponent (-1 = not yet submitted)
    expires_at:       float = 0.0   # Unix timestamp when invitation expires


def _duel_from_dict(d: dict) -> Duel:
    """Reconstruct a Duel dataclass from a plain dict (e.g. loaded from JSON)."""
    return Duel(
        duel_id=d.get("duel_id", ""),
        challenger=d.get("challenger", ""),
        challenger_name=d.get("challenger_name", ""),
        opponent=d.get("opponent", ""),
        opponent_name=d.get("opponent_name", ""),
        table_rom=d.get("table_rom", ""),
        table_name=d.get("table_name", ""),
        status=d.get("status", DuelStatus.PENDING),
        created_at=float(d.get("created_at", 0)),
        accepted_at=float(d.get("accepted_at", 0)),
        completed_at=float(d.get("completed_at", 0)),
        challenger_score=int(d.get("challenger_score", SCORE_NOT_SUBMITTED)),
        opponent_score=int(d.get("opponent_score", SCORE_NOT_SUBMITTED)),
        expires_at=float(d.get("expires_at", 0)),
    )


class DuelEngine:
    """Backend engine for Score Duel lifecycle management.

    Handles sending/receiving duel invitations, timer management,
    table validation, result evaluation, and status transitions.

    Parameters
    ----------
    cfg : AppConfig
        Application configuration instance (provides BASE, CLOUD_*, OVERLAY keys).
    """

    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._active: List[Duel] = []
        self._history: List[Duel] = []
        self._load_local()

    # ── Paths ────────────────────────────────────────────────────────────────

    def _p_duels(self) -> str:
        return os.path.join(p_session(self._cfg), "duels")

    def _f_active(self) -> str:
        return os.path.join(self._p_duels(), "active_duels.json")

    def _f_history(self) -> str:
        return os.path.join(self._p_duels(), "duel_history.json")

    # ── Local persistence ────────────────────────────────────────────────────

    def _load_local(self) -> None:
        """Load active duels and history from local JSON files."""
        try:
            if os.path.isfile(self._f_active()):
                with open(self._f_active(), encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._active = [_duel_from_dict(d) for d in raw if isinstance(d, dict)]
        except Exception as exc:
            log(self._cfg, f"[DUEL] Could not load active_duels.json: {exc}", "WARN")
            self._active = []

        try:
            if os.path.isfile(self._f_history()):
                with open(self._f_history(), encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._history = [_duel_from_dict(d) for d in raw if isinstance(d, dict)]
        except Exception as exc:
            log(self._cfg, f"[DUEL] Could not load duel_history.json: {exc}", "WARN")
            self._history = []

    def _save_active(self) -> None:
        """Persist the current active duels list to disk."""
        try:
            os.makedirs(self._p_duels(), exist_ok=True)
            with open(self._f_active(), "w", encoding="utf-8") as fh:
                json.dump([asdict(d) for d in self._active], fh, indent=2)
        except Exception as exc:
            log(self._cfg, f"[DUEL] Could not save active_duels.json: {exc}", "WARN")

    def _save_history(self) -> None:
        """Persist the duel history list to disk."""
        try:
            os.makedirs(self._p_duels(), exist_ok=True)
            with open(self._f_history(), "w", encoding="utf-8") as fh:
                json.dump([asdict(d) for d in self._history], fh, indent=2)
        except Exception as exc:
            log(self._cfg, f"[DUEL] Could not save duel_history.json: {exc}", "WARN")

    # ── Player helpers ───────────────────────────────────────────────────────

    def _my_player_id(self) -> str:
        return str(self._cfg.OVERLAY.get("player_id", "")).strip()

    def _my_player_name(self) -> str:
        return str(self._cfg.OVERLAY.get("player_name", "Player")).strip()

    # ── Cloud helpers ────────────────────────────────────────────────────────

    def _cloud_node_for_duel(self, duel_id: str) -> str:
        return f"duels/{duel_id}"

    def _upload_duel(self, duel: Duel) -> bool:
        """Upload a duel record to the cloud. Returns True on success."""
        if not self._cfg.CLOUD_ENABLED:
            return False
        node = self._cloud_node_for_duel(duel.duel_id)
        ok = CloudSync.set_node(self._cfg, node, asdict(duel))
        if not ok:
            log(self._cfg, f"[DUEL] Cloud upload failed for duel {duel.duel_id}.", "WARN")
        return ok

    # ── Public API ───────────────────────────────────────────────────────────

    def send_invitation(self, opponent_id: str, table_rom: str, table_name: str = "",
                        opponent_name: str = "") -> Union[Duel, str]:
        """Create a new duel invitation and upload it to the cloud.

        Parameters
        ----------
        opponent_id : str
            The player_id of the challenged opponent.
        table_rom : str
            The ROM name of the table to play.
        table_name : str, optional
            Human-readable display name for the table.
        opponent_name : str, optional
            Display name of the opponent player.

        Returns
        -------
        Duel
            The newly created Duel on success.
        str
            An error-reason string on failure: ``"no_player_id"``,
            ``"no_opponent"``, ``"duplicate"``, or ``"cloud_error"``.
        """
        my_id = self._my_player_id()
        if not my_id:
            log(self._cfg, "[DUEL] send_invitation: player_id not configured.", "WARN")
            return "no_player_id"
        if not opponent_id:
            log(self._cfg, "[DUEL] send_invitation: opponent_id is empty.", "WARN")
            return "no_opponent"

        # Prevent duplicate invitation for the same opponent + table while one is still pending.
        for existing in self._active:
            if (existing.opponent == opponent_id
                    and existing.table_rom == table_rom.lower().strip()
                    and existing.status == DuelStatus.PENDING):
                log(self._cfg, "[DUEL] send_invitation: duplicate – a pending duel for this opponent/table already exists.", "WARN")
                return "duplicate"

        now = time.time()
        duel = Duel(
            duel_id=str(uuid.uuid4()),
            challenger=my_id,
            challenger_name=self._my_player_name(),
            opponent=opponent_id,
            opponent_name=opponent_name,
            table_rom=table_rom.lower().strip(),
            table_name=table_name or table_rom,
            status=DuelStatus.PENDING,
            created_at=now,
            expires_at=now + INVITATION_TTL_SECONDS,
        )
        self._active.append(duel)
        self._save_active()
        self._upload_duel(duel)
        log(self._cfg, f"[DUEL] Invitation sent: {duel.duel_id} → {opponent_id} ({table_rom})")
        return duel

    def receive_invitations(self) -> List[Duel]:
        """Poll the cloud for pending duel invitations addressed to this player.

        Returns a list of newly discovered Duel objects (not yet in active list).
        Also plays the duel_received sound for each new invitation.
        """
        my_id = self._my_player_id()
        if not my_id or not self._cfg.CLOUD_ENABLED:
            return []

        try:
            all_duels = CloudSync.fetch_node(self._cfg, "duels")
        except Exception as exc:
            log(self._cfg, f"[DUEL] receive_invitations fetch error: {exc}", "WARN")
            return []

        if not isinstance(all_duels, dict):
            return []

        known_ids = {d.duel_id for d in self._active}
        new_duels: List[Duel] = []
        for duel_id, data in all_duels.items():
            if not isinstance(data, dict):
                continue
            if data.get("opponent") != my_id:
                continue
            if data.get("status") != DuelStatus.PENDING:
                continue
            if duel_id in known_ids:
                continue
            duel = _duel_from_dict(data)
            duel.duel_id = duel_id
            self._active.append(duel)
            known_ids.add(duel_id)
            new_duels.append(duel)
            log(self._cfg, f"[DUEL] New invitation received: {duel_id} from {duel.challenger_name}")
            try:
                sound.play("duel_received")
            except Exception:
                pass

        if new_duels:
            self._save_active()
        return new_duels

    def accept_duel(self, duel_id: str) -> bool:
        """Accept a pending duel invitation.

        Returns True if the duel was found and successfully accepted.
        """
        duel = self._find_active(duel_id)
        if duel is None:
            log(self._cfg, f"[DUEL] accept_duel: duel {duel_id} not found.", "WARN")
            return False
        duel.status = DuelStatus.ACCEPTED
        duel.accepted_at = time.time()
        self._save_active()
        self._upload_duel(duel)
        log(self._cfg, f"[DUEL] Duel {duel_id} accepted.")
        try:
            sound.play("duel_accepted")
        except Exception:
            pass
        return True

    def decline_duel(self, duel_id: str) -> bool:
        """Decline a pending duel invitation.

        Returns True if the duel was found and declined.
        """
        duel = self._find_active(duel_id)
        if duel is None:
            log(self._cfg, f"[DUEL] decline_duel: duel {duel_id} not found.", "WARN")
            return False
        duel.status = DuelStatus.DECLINED
        duel.completed_at = time.time()
        self._active.remove(duel)
        self._history.append(duel)
        self._save_active()
        self._save_history()
        self._upload_duel(duel)
        log(self._cfg, f"[DUEL] Duel {duel_id} declined.")
        try:
            sound.play("duel_declined")
        except Exception:
            pass
        return True

    def cancel_duel(self, duel_id: str) -> bool:
        """Cancel a pending duel invitation that was sent by this player.

        Only PENDING duels where this player is the challenger can be cancelled.
        The duel is marked as CANCELLED, moved to history, and the updated
        status is uploaded to the cloud.

        Returns True if the duel was found and cancelled.
        """
        duel = self._find_active(duel_id)
        if duel is None:
            log(self._cfg, f"[DUEL] cancel_duel: duel {duel_id} not found.", "WARN")
            return False
        my_id = self._my_player_id()
        if duel.challenger != my_id:
            log(self._cfg, f"[DUEL] cancel_duel: duel {duel_id} – not the challenger.", "WARN")
            return False
        if duel.status != DuelStatus.PENDING:
            log(self._cfg, f"[DUEL] cancel_duel: duel {duel_id} is not pending (status={duel.status}).", "WARN")
            return False
        duel.status = DuelStatus.CANCELLED
        duel.completed_at = time.time()
        self._active.remove(duel)
        self._history.append(duel)
        self._save_active()
        self._save_history()
        self._upload_duel(duel)
        log(self._cfg, f"[DUEL] Duel {duel_id} cancelled by challenger.")
        return True

    def submit_result(self, duel_id: str, score: int) -> Optional[str]:
        """Submit the local player's score for a duel and evaluate the result.

        Fetches the opponent's score from the cloud, determines the winner,
        plays the appropriate sound, and moves the duel to history.

        Parameters
        ----------
        duel_id : str
            The duel to submit a score for.
        score : int
            The score achieved by the local player.

        Returns
        -------
        str or None
            The DuelStatus result ('won', 'lost', or 'expired'), or None on error.
        """
        duel = self._find_active(duel_id)
        if duel is None:
            log(self._cfg, f"[DUEL] submit_result: duel {duel_id} not found.", "WARN")
            return None

        my_id = self._my_player_id()
        is_challenger = (duel.challenger == my_id)

        if is_challenger:
            duel.challenger_score = score
        else:
            duel.opponent_score = score

        # Try to fetch the opponent's score from the cloud.
        cloud_data = None
        if self._cfg.CLOUD_ENABLED:
            cloud_data = CloudSync.fetch_node(self._cfg, self._cloud_node_for_duel(duel_id))

        if isinstance(cloud_data, dict):
            if is_challenger:
                opp_val = int(cloud_data.get("opponent_score", SCORE_NOT_SUBMITTED))
                duel.opponent_score = opp_val if opp_val != SCORE_NOT_SUBMITTED else SCORE_NOT_SUBMITTED
            else:
                chall_val = int(cloud_data.get("challenger_score", SCORE_NOT_SUBMITTED))
                duel.challenger_score = chall_val if chall_val != SCORE_NOT_SUBMITTED else SCORE_NOT_SUBMITTED

        # Only determine winner if both scores have been submitted.
        both_submitted = (duel.challenger_score != SCORE_NOT_SUBMITTED
                          and duel.opponent_score != SCORE_NOT_SUBMITTED)
        if both_submitted:
            # Challenger advantage on tie: challenger wins if scores are equal.
            if duel.challenger_score > duel.opponent_score:
                result = DuelStatus.WON if is_challenger else DuelStatus.LOST
            elif duel.challenger_score < duel.opponent_score:
                result = DuelStatus.LOST if is_challenger else DuelStatus.WON
            else:
                # Tie: challenger gets the edge (home-field advantage rule).
                result = DuelStatus.WON if is_challenger else DuelStatus.LOST
        else:
            # Score not yet available from the other side – mark ACTIVE and wait.
            duel.status = DuelStatus.ACTIVE
            self._save_active()
            self._upload_duel(duel)
            log(self._cfg, f"[DUEL] Score submitted for {duel_id}; waiting for opponent score.")
            return None

        duel.status = result
        duel.completed_at = time.time()
        self._active.remove(duel)
        self._history.append(duel)
        self._save_active()
        self._save_history()
        self._upload_duel(duel)
        log(self._cfg, f"[DUEL] Duel {duel_id} result: {result} (challenger={duel.challenger_score}, opponent={duel.opponent_score})")

        try:
            sound.play("duel_won" if result == DuelStatus.WON else "duel_lost")
        except Exception:
            pass

        return result

    def check_expiry(self) -> List[Duel]:
        """Check all active duels for expiry and move expired ones to history.

        PENDING duels expire when their ``expires_at`` timestamp passes.
        ACCEPTED and ACTIVE duels expire after ``ACTIVE_DUEL_TTL_SECONDS``
        (24 hours) from acceptance to prevent them from staying forever.

        Returns a list of duels that were expired in this call.
        """
        now = time.time()
        expired: List[Duel] = []
        for duel in list(self._active):
            should_expire = False
            if duel.status == DuelStatus.PENDING and duel.expires_at > 0 and now > duel.expires_at:
                should_expire = True
            elif duel.status in (DuelStatus.ACCEPTED, DuelStatus.ACTIVE):
                # Accepted/active duels expire after 24 hours from acceptance.
                ref_time = duel.accepted_at if duel.accepted_at > 0 else duel.created_at
                if ref_time > 0 and now > ref_time + ACTIVE_DUEL_TTL_SECONDS:
                    should_expire = True

            if should_expire:
                duel.status = DuelStatus.EXPIRED
                duel.completed_at = now
                self._active.remove(duel)
                self._history.append(duel)
                expired.append(duel)
                log(self._cfg, f"[DUEL] Duel {duel.duel_id} expired.")
                try:
                    sound.play("duel_expired")
                except Exception:
                    pass

        if expired:
            self._save_active()
            self._save_history()

        return expired

    def get_active_duels(self) -> List[Duel]:
        """Return a copy of the current active/pending duels list."""
        return list(self._active)

    def get_duel_history(self) -> List[Duel]:
        """Return a copy of the completed duel history list (newest first)."""
        return list(reversed(self._history))

    def validate_table(self, table_rom: str, maps_cache: list = None) -> bool:
        """Check whether a table ROM is available in the local maps cache.

        Parameters
        ----------
        table_rom : str
            The ROM name to look up (case-insensitive).
        maps_cache : list, optional
            The ``_all_maps_cache`` from the main window. If omitted, returns True.

        Returns
        -------
        bool
            True if the table is found (or no cache is provided), False otherwise.
        """
        if not maps_cache:
            return True
        rom_lower = table_rom.lower().strip()
        for entry in maps_cache:
            if isinstance(entry, dict) and entry.get("rom", "").lower() == rom_lower:
                return True
        return False

    # ── Private helpers ──────────────────────────────────────────────────────

    def _find_active(self, duel_id: str) -> Optional[Duel]:
        """Return the active Duel with the given ID, or None."""
        for d in self._active:
            if d.duel_id == duel_id:
                return d
        return None
