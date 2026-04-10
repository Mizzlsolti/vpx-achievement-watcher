"""duel_engine.py – Backend engine for Score Duel lifecycle management.

Handles sending/receiving duel invitations, timer management,
table validation, result evaluation, and status transitions.
Duels are stored locally as JSON files and synced via the cloud.
"""
from __future__ import annotations

import json
import os
import random
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union

from . import sound
from .config import p_session
from .cloud_sync import CloudSync
from .watcher_core import log


class DuelStatus:
    """Possible states for a Score Duel."""
    PENDING   = "pending"
    ACCEPTED  = "accepted"
    ACTIVE    = "active"
    WON       = "won"
    LOST      = "lost"
    TIE       = "tie"  # canonical equal-score terminal status
    EXPIRED   = "expired"
    DECLINED  = "declined"
    CANCELLED = "cancelled"


# Invitation expires after 7 days if not accepted.
INVITATION_TTL_SECONDS = 604_800

# Accepted/active duels expire after 2 days if no score is submitted.
ACTIVE_DUEL_TTL_SECONDS = 172_800

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
    cancel_reason:    str   = ""    # reason for cancellation (set by abort_duel)


def _duel_from_dict(d: dict) -> Duel:
    """Reconstruct a Duel dataclass from a plain dict (e.g. loaded from JSON)."""
    return Duel(
        duel_id=d.get("duel_id", ""),
        challenger=d.get("challenger", "").lower(),
        challenger_name=d.get("challenger_name", ""),
        opponent=d.get("opponent", "").lower(),
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
        cancel_reason=str(d.get("cancel_reason", "")),
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
        self._lock = threading.RLock()
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
        return str(self._cfg.OVERLAY.get("player_id", "")).strip().lower()

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
        terminal = (DuelStatus.WON, DuelStatus.LOST, DuelStatus.TIE,
                    DuelStatus.EXPIRED, DuelStatus.DECLINED, DuelStatus.CANCELLED)
        if duel.status in terminal:
            # Terminal states: delete from cloud to keep duels/ node small.
            # The duel is already saved in local duel_history.json.
            ok = CloudSync.set_node(self._cfg, node, None)
        else:
            ok = CloudSync.set_node(self._cfg, node, asdict(duel))
        if not ok:
            log(self._cfg, f"[DUEL] Cloud upload failed for duel {duel.duel_id}.", "WARN")
        return ok

    # ── Public API ───────────────────────────────────────────────────────────

    def send_invitation(self, opponent_id: str, table_rom: str, table_name: str = "",
                        opponent_name: str = "",
                        maps_cache: Optional[list] = None) -> Union[Duel, str]:
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
        maps_cache : list, optional
            Available maps cache entries.  When provided, the table is
            validated against the triple-condition rules before the
            invitation is sent.  Omit (or pass ``None``) to skip the
            cache-based validation (e.g. auto-match flow already
            guarantees a valid VPS-ID intersection).

        Returns
        -------
        Duel
            The newly created Duel on success.
        str
            An error-reason string on failure: ``"no_player_id"``,
            ``"no_cloud"``, ``"no_opponent"``, ``"duplicate"``,
            ``"cloud_error"``, ``"table_not_found"``, ``"no_nvram_map"``,
            ``"cat_not_enabled"``, ``"not_local"``, or ``"no_vps_id"``.
        """
        my_id = self._my_player_id()
        if not my_id:
            log(self._cfg, "[DUEL] send_invitation: player_id not configured.", "WARN")
            return "no_player_id"
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            log(self._cfg, "[DUEL] send_invitation: Cloud Sync is disabled.", "WARN")
            return "no_cloud"
        if not opponent_id:
            log(self._cfg, "[DUEL] send_invitation: opponent_id is empty.", "WARN")
            return "no_opponent"

        # Triple-condition validation when maps_cache is provided.
        if maps_cache is not None:
            ok, err = self.validate_table_for_duel(table_rom, maps_cache)
            if not ok:
                log(self._cfg, f"[DUEL] send_invitation blocked: {err} for {table_rom}", "WARN")
                return err

        # Prevent duplicate invitation for the same opponent + table while one is PENDING/ACCEPTED/ACTIVE.
        norm_rom = table_rom.lower().strip()
        with self._lock:
            for existing in self._active:
                if (existing.table_rom == norm_rom
                        and existing.status in (DuelStatus.PENDING, DuelStatus.ACCEPTED, DuelStatus.ACTIVE)):
                    # Block if same opponent (either direction).
                    if existing.opponent.lower() == opponent_id.lower() or existing.challenger.lower() == opponent_id.lower():
                        log(self._cfg, "[DUEL] send_invitation: duplicate – an active duel for this opponent/table already exists.", "WARN")
                        return "duplicate"

            now = time.time()
            duel = Duel(
                duel_id=str(uuid.uuid4()),
                challenger=my_id,
                challenger_name=self._my_player_name(),
                opponent=opponent_id.lower().strip(),
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
        log(self._cfg, f"[DUEL] Invitation sent: {duel.duel_id} → '{opponent_name or 'opponent'}' ({table_rom})")
        return duel

    def validate_table_for_duel(self, table_rom: str, maps_cache: list = None) -> tuple:
        """Validate that a table meets all 3 requirements for duels.

        Requirements
        ------------
        1. NVRAM map exists (``has_map == True``) **or** CAT table is enabled
           (``is_cat == True`` and ``cat_enabled == True``).
        2. Table is locally installed (``is_local == True``).
        3. ROM has a VPS-ID assigned in ``vps_id_mapping.json``.

        Parameters
        ----------
        table_rom : str
            ROM name of the table to validate.
        maps_cache : list, optional
            Available maps cache entries (list of dicts).  Defaults to ``[]``.

        Returns
        -------
        tuple[bool, str]
            ``(True, "")`` on success.
            ``(False, error_code)`` on failure.  Error codes:
            ``"table_not_found"``, ``"no_nvram_map"``, ``"cat_not_enabled"``,
            ``"not_local"``, ``"no_vps_id"``.
        """
        if maps_cache is None:
            maps_cache = []

        norm = table_rom.lower().strip()
        entry = next(
            (e for e in maps_cache
             if isinstance(e, dict) and e.get("rom", "").lower().strip() == norm),
            None,
        )

        if not entry:
            return False, "table_not_found"

        is_cat = entry.get("is_cat", False)

        if is_cat:
            if not entry.get("cat_enabled"):
                return False, "cat_not_enabled"
        else:
            if not entry.get("has_map"):
                return False, "no_nvram_map"

        if not entry.get("is_local"):
            return False, "not_local"

        try:
            from ui.vps import _load_vps_mapping
            vps_mapping = _load_vps_mapping(self._cfg)
        except Exception:
            vps_mapping = {}
        if norm not in {k.lower().strip() for k in vps_mapping}:
            return False, "no_vps_id"

        return True, ""

    def abort_duel(self, duel_id: str, reason: str = "aborted") -> bool:
        """Abort a duel and report to cloud.

        Used when a VPX game session is deemed invalid (too short or no score
        improvement).  Transitions the duel to ``CANCELLED``, moves it to
        history, persists the ``cancel_reason``, and pushes the update to the
        cloud.

        Parameters
        ----------
        duel_id : str
            ID of the duel to abort.
        reason : str, optional
            Human-readable reason string stored on the duel record.
            Defaults to ``"aborted"``.

        Returns
        -------
        bool
            ``True`` if the duel was found and aborted; ``False`` otherwise.
        """
        with self._lock:
            duel = self._find_active(duel_id)
            if not duel:
                log(self._cfg, f"[DUEL] abort_duel: duel {duel_id} not found.", "WARN")
                return False
            duel.status = DuelStatus.CANCELLED
            duel.cancel_reason = reason
            duel.completed_at = time.time()
            self._active.remove(duel)
            self._history.append(duel)
            self._save_active()
            self._save_history()
        self._upload_duel(duel)
        log(self._cfg, f"[DUEL] Duel {duel_id} aborted. Reason: {reason}")
        return True

    def receive_invitations(self) -> List[Duel]:
        """Poll the cloud for pending duel invitations addressed to this player.

        Returns a list of newly discovered Duel objects (not yet in active list).
        Also plays the duel_received sound for each new invitation.
        """
        my_id = self._my_player_id()
        if not my_id or not self._cfg.CLOUD_ENABLED:
            return []
        if bool(self._cfg.OVERLAY.get("duels_do_not_disturb", False)):
            return []

        try:
            all_duels = CloudSync.fetch_node(self._cfg, "duels")
        except Exception as exc:
            log(self._cfg, f"[DUEL] receive_invitations fetch error: {exc}", "WARN")
            return []

        if not isinstance(all_duels, dict):
            return []

        new_duels: List[Duel] = []
        with self._lock:
            known_ids = {d.duel_id for d in self._active}
            for duel_id, data in all_duels.items():
                if not isinstance(data, dict):
                    continue
                if data.get("opponent", "").lower() != my_id:
                    continue
                if data.get("status") != DuelStatus.PENDING:
                    continue
                if duel_id in known_ids:
                    continue
                # Receiver-side dedup: skip if a duel for the same challenger + table_rom
                # already exists in active with status PENDING/ACCEPTED/ACTIVE.
                challenger_id = data.get("challenger", "").lower().strip()
                table_rom_norm = data.get("table_rom", "").lower().strip()
                duplicate = any(
                    d.table_rom == table_rom_norm
                    and d.status in (DuelStatus.PENDING, DuelStatus.ACCEPTED, DuelStatus.ACTIVE)
                    and (d.challenger.lower() == challenger_id or d.opponent.lower() == challenger_id)
                    for d in self._active
                )
                if duplicate:
                    log(self._cfg, f"[DUEL] receive_invitations: skipping duplicate invite {duel_id} from {challenger_id}.", "WARN")
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
        with self._lock:
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
        with self._lock:
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
        """Cancel a duel that was sent by or involves this player.

        PENDING duels: either the challenger or the opponent can cancel.
        ACCEPTED duels: either the challenger or opponent can cancel.

        The duel is marked as CANCELLED, moved to history, and the updated
        status is uploaded to the cloud.

        Returns True if the duel was found and cancelled.
        """
        with self._lock:
            duel = self._find_active(duel_id)
            if duel is None:
                log(self._cfg, f"[DUEL] cancel_duel: duel {duel_id} not found.", "WARN")
                return False
            my_id = self._my_player_id()
            if duel.status == DuelStatus.PENDING:
                if duel.challenger.lower() != my_id and duel.opponent.lower() != my_id:
                    log(self._cfg, f"[DUEL] cancel_duel: duel {duel_id} – not a participant.", "WARN")
                    return False
            elif duel.status == DuelStatus.ACCEPTED:
                if duel.challenger.lower() != my_id and duel.opponent.lower() != my_id:
                    log(self._cfg, f"[DUEL] cancel_duel: duel {duel_id} – not a participant.", "WARN")
                    return False
            else:
                log(self._cfg, f"[DUEL] cancel_duel: duel {duel_id} cannot be cancelled (status={duel.status}).", "WARN")
                return False
            duel.status = DuelStatus.CANCELLED
            duel.completed_at = time.time()
            self._active.remove(duel)
            self._history.append(duel)
            self._save_active()
            self._save_history()
        self._upload_duel(duel)
        log(self._cfg, f"[DUEL] Duel {duel_id} cancelled.")
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
        str
            ``DuelStatus.WON``, ``DuelStatus.LOST``, or ``DuelStatus.TIE``
            when both scores are available and a winner has been determined.
        None
            When the duel is not found (``duel_id`` is unknown) or when the
            opponent's score is not yet available (waiting for opponent to play).
        """
        with self._lock:
            duel = self._find_active(duel_id)
            if duel is None:
                log(self._cfg, f"[DUEL] submit_result: duel {duel_id} not found.", "WARN")
                return None

            my_id = self._my_player_id()
            is_challenger = (duel.challenger.lower() == my_id)

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
                if duel.challenger_score > duel.opponent_score:
                    result = DuelStatus.WON if is_challenger else DuelStatus.LOST
                elif duel.challenger_score < duel.opponent_score:
                    result = DuelStatus.LOST if is_challenger else DuelStatus.WON
                else:
                    result = DuelStatus.TIE
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
            if result == DuelStatus.WON:
                sound.play("duel_won")
            elif result == DuelStatus.LOST:
                sound.play("duel_lost")
            # TIE: no specific sound
        except Exception:
            pass

        return result

    def check_expiry(self) -> List[Duel]:
        """Check all active duels for expiry and move expired ones to history.

        PENDING duels expire when their ``expires_at`` timestamp passes.
        Before expiring a PENDING duel the cloud state is fetched to verify it
        was not accepted in the meantime (race condition guard).
        ACCEPTED and ACTIVE duels expire after ``ACTIVE_DUEL_TTL_SECONDS``
        (2 days) from acceptance to prevent them from staying forever.

        Returns a list of duels that were expired in this call.
        """
        now = time.time()
        expired: List[Duel] = []
        with self._lock:
            for duel in list(self._active):
                should_expire = False
                if duel.status == DuelStatus.PENDING and duel.expires_at > 0 and now > duel.expires_at:
                    # Before expiring, check cloud state – the opponent may have accepted
                    # just before we run expiry (race condition guard).
                    if self._cfg.CLOUD_ENABLED:
                        try:
                            cloud_data = CloudSync.fetch_node(self._cfg, f"duels/{duel.duel_id}")
                            if isinstance(cloud_data, dict):
                                cloud_status = cloud_data.get("status")
                                if cloud_status == DuelStatus.ACCEPTED:
                                    # Opponent accepted in the cloud – update local state.
                                    duel.status = DuelStatus.ACCEPTED
                                    duel.accepted_at = float(cloud_data.get("accepted_at", now))
                                    self._save_active()
                                    log(self._cfg, f"[DUEL] check_expiry: duel {duel.duel_id} was accepted in cloud – skipping expiry.")
                                    continue
                        except Exception:
                            pass
                    should_expire = True
                elif duel.status in (DuelStatus.ACCEPTED, DuelStatus.ACTIVE):
                    # Accepted/active duels expire after 2 days from acceptance.
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

        # Upload each expired duel to the cloud outside the lock (mirrors abort_duel).
        if self._cfg.CLOUD_ENABLED:
            for duel in expired:
                self._upload_duel(duel)

        return expired

    def sync_active_duel_states(self) -> List[Duel]:
        """Sync cloud state for duels where this player is the challenger or opponent.

        Fetches the cloud record for each locally-PENDING, ACCEPTED, or ACTIVE
        duel where the local player is the challenger or opponent and updates the
        local state accordingly.  This ensures missed transitions (e.g. after an
        app restart) are recovered on the next sync cycle.

        Handled transitions:
        - Cloud ACCEPTED  → update local to ACCEPTED
        - Cloud DECLINED/EXPIRED/CANCELLED → move to history
        - Cloud WON/LOST  → move to history with scores (result computed from
          scores, not the perspective-relative cloud status field)
        - For ACTIVE duels: check if the other player's score is now available

        Returns a list of Duel objects whose status changed during this call.
        """
        my_id = self._my_player_id()
        if not my_id or not self._cfg.CLOUD_ENABLED:
            return []

        # Phase 1: Snapshot active duels under lock so the cloud fetches below
        # do not race with list mutations on the GUI thread.
        with self._lock:
            snapshot = [
                d for d in self._active
                if (d.challenger.lower() == my_id or d.opponent.lower() == my_id)
                and d.status in (DuelStatus.PENDING, DuelStatus.ACCEPTED, DuelStatus.ACTIVE)
            ]

        # Phase 2: Fetch cloud state for each duel (outside lock – network I/O).
        cloud_results: dict = {}
        for duel in snapshot:
            try:
                cloud_data = CloudSync.fetch_node(self._cfg, f"duels/{duel.duel_id}")
                cloud_results[duel.duel_id] = cloud_data
            except Exception as exc:
                log(self._cfg, f"[DUEL] sync_active_duel_states fetch error for {duel.duel_id}: {exc}", "WARN")

        # Phase 3: Apply mutations under lock.
        changed: List[Duel] = []
        to_remove: List[Duel] = []
        with self._lock:
            for duel in snapshot:
                cloud_data = cloud_results.get(duel.duel_id)
                if not isinstance(cloud_data, dict):
                    continue
                # Skip if the duel was already removed from _active by another thread.
                if duel not in self._active:
                    continue

                cloud_status = cloud_data.get("status")
                if cloud_status == duel.status:
                    # For ACTIVE duels, still check if the other player's score arrived.
                    if duel.status == DuelStatus.ACTIVE:
                        is_challenger = (duel.challenger.lower() == my_id)
                        if is_challenger:
                            other_score = int(cloud_data.get("opponent_score", SCORE_NOT_SUBMITTED))
                            if other_score != SCORE_NOT_SUBMITTED and duel.opponent_score == SCORE_NOT_SUBMITTED:
                                duel.opponent_score = other_score
                                self._save_active()
                                log(self._cfg, f"[DUEL] sync: opponent score arrived for {duel.duel_id}.")
                                changed.append(duel)
                        else:
                            other_score = int(cloud_data.get("challenger_score", SCORE_NOT_SUBMITTED))
                            if other_score != SCORE_NOT_SUBMITTED and duel.challenger_score == SCORE_NOT_SUBMITTED:
                                duel.challenger_score = other_score
                                self._save_active()
                                log(self._cfg, f"[DUEL] sync: challenger score arrived for {duel.duel_id}.")
                                changed.append(duel)
                    continue

                if cloud_status == DuelStatus.ACCEPTED:
                    duel.status = DuelStatus.ACCEPTED
                    duel.accepted_at = float(cloud_data.get("accepted_at", time.time()))
                    self._save_active()
                    log(self._cfg, f"[DUEL] Duel {duel.duel_id} accepted by '{duel.opponent_name or 'opponent'}'.")
                    changed.append(duel)

                elif cloud_status in (DuelStatus.DECLINED, DuelStatus.EXPIRED, DuelStatus.CANCELLED):
                    duel.status = cloud_status
                    duel.completed_at = float(cloud_data.get("completed_at", time.time()))
                    if duel not in to_remove:
                        to_remove.append(duel)
                    self._history.append(duel)
                    changed.append(duel)
                    log(self._cfg, f"[DUEL] Duel {duel.duel_id} {cloud_status} by '{duel.opponent_name or 'opponent'}'.")

                elif cloud_status in (DuelStatus.WON, DuelStatus.LOST, DuelStatus.TIE):
                    ch_score = int(cloud_data.get("challenger_score", SCORE_NOT_SUBMITTED))
                    op_score = int(cloud_data.get("opponent_score", SCORE_NOT_SUBMITTED))
                    is_challenger = (duel.challenger.lower() == my_id)
                    if ch_score == op_score:
                        correct_status = DuelStatus.TIE
                    elif ch_score > op_score:
                        correct_status = DuelStatus.WON if is_challenger else DuelStatus.LOST
                    else:
                        correct_status = DuelStatus.LOST if is_challenger else DuelStatus.WON
                    duel.status = correct_status
                    duel.completed_at = float(cloud_data.get("completed_at", time.time()))
                    duel.challenger_score = ch_score
                    duel.opponent_score = op_score
                    if duel not in to_remove:
                        to_remove.append(duel)
                    self._history.append(duel)
                    changed.append(duel)
                    log(self._cfg, f"[DUEL] Duel {duel.duel_id} completed with status {correct_status}.")

            if to_remove:
                for d in to_remove:
                    if d in self._active:
                        self._active.remove(d)
                self._save_active()
                self._save_history()

        return changed

    def get_active_duels(self) -> List[Duel]:
        """Return a copy of the current active/pending duels list."""
        with self._lock:
            return list(self._active)

    def get_duel_history(self) -> List[Duel]:
        """Return a copy of the completed duel history list (newest first)."""
        with self._lock:
            return list(reversed(self._history))

    def clear_history(self) -> None:
        """Remove all entries from the duel history."""
        with self._lock:
            self._history.clear()
            self._save_history()
        log(self._cfg, "[DUEL] Duel history cleared.")

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

    # ── Matchmaking ──────────────────────────────────────────────────────────

    # TTL for matchmaking queue entries (5 minutes).
    _MATCHMAKING_TTL = 300

    def join_matchmaking(self) -> bool:
        """Add the local player to the cloud matchmaking queue.

        Collects all VPS-IDs from ``vps_id_mapping.json``, writes an entry to
        ``duels/matchmaking/{player_id}`` in the cloud, and returns True on
        success.  Returns False when Cloud Sync is disabled, the player has no
        VPS-IDs, or the upload fails.
        """
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            log(self._cfg, "[DUEL] join_matchmaking: Cloud Sync is disabled.", "WARN")
            return False
        my_id = self._my_player_id()
        if not my_id:
            log(self._cfg, "[DUEL] join_matchmaking: player_id not configured.", "WARN")
            return False
        try:
            from ui.vps import _load_vps_mapping
            vps_mapping = _load_vps_mapping(self._cfg)
        except Exception as exc:
            log(self._cfg, f"[DUEL] join_matchmaking: could not load VPS mapping: {exc}", "WARN")
            vps_mapping = {}
        vps_ids = list(vps_mapping.values())
        if not vps_ids:
            log(self._cfg, "[DUEL] join_matchmaking: no VPS-IDs found.", "WARN")
            return False
        now = time.time()
        entry = {
            "player_id":   my_id,
            "player_name": self._my_player_name(),
            "vps_ids":     vps_ids,
            "queued_at":   now,
            "expires_at":  now + self._MATCHMAKING_TTL,
        }
        node = f"duels/matchmaking/{my_id}"
        ok = CloudSync.set_node(self._cfg, node, entry)
        if not ok:
            log(self._cfg, "[DUEL] join_matchmaking: cloud write failed.", "WARN")
        else:
            log(self._cfg, f"[DUEL] Joined matchmaking queue with {len(vps_ids)} VPS-IDs.")
        return ok

    def poll_matchmaking(self) -> Optional[dict]:
        """Poll the matchmaking queue for a compatible opponent.

        Fetches all entries from ``duels/matchmaking/``, filters out own entry,
        expired entries, and players with whom an active duel already exists.
        For remaining candidates the VPS-ID intersection is computed.  If a
        match is found the newer player (higher ``queued_at``) creates the duel
        via :meth:`send_invitation` and removes both queue entries.

        Returns
        -------
        dict
            ``{"opponent_name": ..., "table_name": ..., "duel_id": ...}`` when
            a match is found and this player creates the duel.
            ``{"queue_count": N, "shared_tables": M}`` when the queue was read
            but no match was created (either no candidates or we are the older
            player waiting for the other side to create the duel).
        None
            On error.
        """
        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            return None
        my_id = self._my_player_id()
        if not my_id:
            return None
        try:
            all_entries = CloudSync.fetch_node(self._cfg, "duels/matchmaking")
        except Exception as exc:
            log(self._cfg, f"[DUEL] poll_matchmaking: fetch error: {exc}", "WARN")
            return None
        if not isinstance(all_entries, dict):
            return {"queue_count": 0, "shared_tables": 0}
        now = time.time()
        # Load own VPS-IDs.
        try:
            from ui.vps import _load_vps_mapping
            vps_mapping = _load_vps_mapping(self._cfg)
        except Exception:
            vps_mapping = {}
        my_vps_ids = set(vps_mapping.values())
        # Determine own queued_at (for first-come principle).
        my_entry = next((v for k, v in all_entries.items() if k.lower() == my_id), None)
        my_queued_at = float(my_entry.get("queued_at", 0)) if isinstance(my_entry, dict) else 0.0
        # Active opponent IDs (skip if we already have a duel against them).
        active_opponents = set()
        with self._lock:
            for d in self._active:
                if d.status in (DuelStatus.PENDING, DuelStatus.ACCEPTED, DuelStatus.ACTIVE):
                    active_opponents.add(d.challenger.lower())
                    active_opponents.add(d.opponent.lower())
        active_opponents.discard(my_id)
        max_shared = 0
        queue_count = 0
        for pid, entry in all_entries.items():
            if pid.lower() == my_id:
                continue
            if not isinstance(entry, dict):
                continue
            if float(entry.get("expires_at", 0)) < now:
                continue
            if pid.lower() in active_opponents:
                continue
            queue_count += 1
            their_vps_ids = set(entry.get("vps_ids") or [])
            shared = my_vps_ids & their_vps_ids
            if len(shared) > max_shared:
                max_shared = len(shared)
            if not shared:
                continue
            their_queued_at = float(entry.get("queued_at", 0))
            # First-come principle: only the NEWER player (higher queued_at) creates
            # the duel; the older player waits to receive the invitation.
            if my_queued_at <= their_queued_at:
                continue  # We arrived first – wait for the other side to create
            # We are the newer player – create the duel now.
            chosen_vps_id = random.choice(list(shared))
            # Reverse-lookup: find the ROM that owns this VPS-ID.
            table_rom = ""
            for rom, vid in vps_mapping.items():
                if vid == chosen_vps_id:
                    table_rom = rom
                    break
            if not table_rom:
                continue
            # Resolve display name.
            try:
                from .watcher_core import _strip_version_from_name
                romnames = {}
                for obj in list(sys.modules.values()):
                    if hasattr(obj, "ROMNAMES") and isinstance(getattr(obj, "ROMNAMES"), dict):
                        romnames = obj.ROMNAMES
                        break
                raw_name = romnames.get(table_rom) or table_rom
                table_name = _strip_version_from_name(raw_name)
                if "(" in table_name:
                    table_name = table_name[:table_name.index("(")].strip()
            except Exception:
                table_name = table_rom
            opponent_id   = entry.get("player_id", pid)
            opponent_name = entry.get("player_name", pid)
            result = self.send_invitation(opponent_id, table_rom, table_name,
                                          opponent_name=opponent_name)
            if isinstance(result, Duel):
                duel_id = result.duel_id
                # Remove both queue entries.
                CloudSync.set_node(self._cfg, f"duels/matchmaking/{my_id}", None)
                CloudSync.set_node(self._cfg, f"duels/matchmaking/{pid}", None)
                log(self._cfg, f"[DUEL] Auto-Match: duel created against {opponent_name} on {table_name}.")
                return {"opponent_name": opponent_name, "table_name": table_name, "duel_id": duel_id}
        return {"queue_count": queue_count, "shared_tables": max_shared}

    def leave_matchmaking(self) -> bool:
        """Remove the local player's entry from the matchmaking queue.

        Returns True on success (including when no entry existed), False on
        network error.
        """
        my_id = self._my_player_id()
        if not my_id:
            return True
        node = f"duels/matchmaking/{my_id}"
        ok = CloudSync.set_node(self._cfg, node, None)
        if ok:
            log(self._cfg, "[DUEL] Left matchmaking queue.")
        else:
            log(self._cfg, "[DUEL] leave_matchmaking: cloud delete failed.", "WARN")
        return ok

    def register_cloud_duel(self, duel_id: str) -> Optional["Duel"]:
        """Fetch a duel from the cloud and add it to the local active list if unknown.

        Used by the tournament engine so that all participants discover their
        tournament duels without going through the normal invitation flow.

        Parameters
        ----------
        duel_id : str
            Cloud duel ID to fetch.

        Returns
        -------
        Duel
            The registered (or already-known) Duel on success.
        None
            When the duel could not be fetched or parsed.
        """
        with self._lock:
            existing = self._find_active(duel_id)
            if existing is not None:
                return existing

        if not getattr(self._cfg, "CLOUD_ENABLED", False):
            return None
        try:
            cloud_data = CloudSync.fetch_node(self._cfg, f"duels/{duel_id}")
        except Exception as exc:
            log(self._cfg, f"[DUEL] register_cloud_duel fetch error for {duel_id}: {exc}", "WARN")
            return None
        if not isinstance(cloud_data, dict):
            return None

        duel = _duel_from_dict(cloud_data)
        duel.duel_id = duel_id

        with self._lock:
            # Double-check under lock to avoid race condition.
            if not any(d.duel_id == duel_id for d in self._active):
                # Only add if the duel is still in an active state (not completed).
                if duel.status in (DuelStatus.PENDING, DuelStatus.ACCEPTED, DuelStatus.ACTIVE):
                    self._active.append(duel)
                    self._save_active()
                    log(self._cfg, f"[DUEL] register_cloud_duel: registered {duel_id} (status={duel.status}).")
        return duel

    # ── Private helpers ──────────────────────────────────────────────────────

    def _find_active(self, duel_id: str) -> Optional[Duel]:
        """Return the active Duel with the given ID, or None."""
        for d in self._active:
            if d.duel_id == duel_id:
                return d
        return None
