"""
nvram_map_generator.py — Standalone NVRAM Map Auto-Generator
=============================================================
Automatically discovers and creates NVRAM map files (.map.json) for ROMs
that don't have an existing map, by analysing byte-level diffs between
periodic snapshots taken during gameplay.

Architecture
------------
NvramDiffCollector   – snapshot collection and byte-level diff analysis
FieldGrouper         – multi-byte grouping and encoding detection
NvramMapGenerator    – orchestrator with on_game_tick() / on_game_end()

This module is **100% optional**.  Import guard in watcher_core.py:
    try:
        from nvram_map_generator import NvramMapGenerator
    except ImportError:
        NvramMapGenerator = None

If the file is deleted or the flag AUTO_MAP_GENERATOR is False the watcher
works exactly as before with zero side effects.
"""

from __future__ import annotations

import os
import json
import time
from datetime import datetime, timezone
from typing import Optional, Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GENERATOR_MARKER = "nvram-auto-map-v1"
SNAPSHOT_INTERVAL_SEC = 5.0          # minimum gap between snapshots
MIN_SNAPSHOTS_TO_ANALYSE = 3         # need at least this many snapshots
# Maximum allowed ratio between two adjacent bytes' change counts before they
# are split into separate fields (0 = always group, 1 = always split).
MAX_CHANGE_COUNT_DIFF_RATIO = 0.6


def detect_platform(nv_size: int) -> str:
    """Return a platform hint string based on .nv file size."""
    if nv_size <= 8 * 1024:
        return "wpc"          # Williams / Bally WPC or Whitestar
    if nv_size <= 32 * 1024:
        return "sam"          # Stern SAM (32 KB typical)
    return "unknown"


def _decode_bcd(raw: bytes) -> Optional[int]:
    """Decode a BCD-encoded byte sequence.  Returns None if any nibble > 9."""
    digits = []
    for byte in raw:
        hi = (byte >> 4) & 0x0F
        lo = byte & 0x0F
        if hi > 9 or lo > 9:
            return None
        digits.append(hi)
        digits.append(lo)
    s = "".join(str(d) for d in digits).lstrip("0")
    return int(s) if s else 0


def _is_bcd(raw: bytes) -> bool:
    return _decode_bcd(raw) is not None


def _is_printable_ascii(raw: bytes) -> bool:
    return all(0x20 <= b <= 0x7E for b in raw)


def auto_label_field(offset: int, size: int, encoding: Optional[str],
                     max_val: int, change_count: int) -> str:
    """
    Assign a heuristic human-readable label to a discovered field.

    Heuristics
    ----------
    * BCD field of ≥ 3 bytes that changed frequently → likely a score
    * 1-byte field with small max value (≤ 4) → Ball / Player counter
    * Medium counters → generic Counter_XXXX fallback
    """
    if encoding == "bcd" and size >= 3 and change_count >= 3:
        return "P1 Score"
    if size == 1:
        if max_val <= 4 and change_count >= 2:
            return "Ball Number"
        if max_val <= 8 and change_count >= 2:
            return "Current Player"
    return f"Counter_{offset:04X}"


# ---------------------------------------------------------------------------
# NvramDiffCollector
# ---------------------------------------------------------------------------

class NvramDiffCollector:
    """
    Periodically reads the raw .nv file and stores byte snapshots.
    After MIN_SNAPSHOTS_TO_ANALYSE snapshots have been taken the analyse()
    method identifies which offsets changed and how.
    """

    def __init__(self, nv_path: str) -> None:
        self.nv_path = nv_path
        self._snapshots: list[tuple[float, bytes]] = []   # (timestamp, data)
        self._last_snapshot_ts: float = 0.0

    # ------------------------------------------------------------------
    def take_snapshot(self) -> bool:
        """
        Read the .nv file and store a snapshot.
        Returns True if a new snapshot was stored, False otherwise.
        Enforces a minimum gap of SNAPSHOT_INTERVAL_SEC between captures.
        """
        now = time.time()
        if now - self._last_snapshot_ts < SNAPSHOT_INTERVAL_SEC:
            return False
        try:
            with open(self.nv_path, "rb") as fh:
                data = fh.read()
        except OSError:
            return False
        if not data:
            return False
        self._snapshots.append((now, data))
        self._last_snapshot_ts = now
        return True

    # ------------------------------------------------------------------
    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    @property
    def ready(self) -> bool:
        return len(self._snapshots) >= MIN_SNAPSHOTS_TO_ANALYSE

    # ------------------------------------------------------------------
    def analyse(self) -> list[dict]:
        """
        Compare all stored snapshots byte-by-byte.

        Returns a list of dicts, one per offset that changed at least once:
            {
                "offset":       int,
                "change_count": int,       # how many snapshots showed a change
                "values":       list[int], # all observed byte values
                "monotonic":    bool,      # True if bytes only ever increased
            }
        """
        if not self.ready:
            return []

        # Use the length of the smallest snapshot so we never overflow
        min_len = min(len(snap) for _, snap in self._snapshots)
        if min_len == 0:
            return []

        # Flatten to list of byte arrays, trimmed to min_len
        arrays = [snap[:min_len] for _, snap in self._snapshots]

        results: list[dict] = []
        for offset in range(min_len):
            vals = [arr[offset] for arr in arrays]
            unique = set(vals)
            if len(unique) <= 1:
                continue   # this byte never changed

            # Check monotonic increase
            monotonic = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))

            change_count = sum(
                1 for i in range(1, len(vals)) if vals[i] != vals[i - 1]
            )

            results.append({
                "offset":       offset,
                "change_count": change_count,
                "values":       vals,
                "monotonic":    monotonic,
                "min_val":      min(vals),
                "max_val":      max(vals),
            })

        return results


# ---------------------------------------------------------------------------
# FieldGrouper
# ---------------------------------------------------------------------------

class FieldGrouper:
    """
    Takes the per-byte change info produced by NvramDiffCollector.analyse()
    and groups adjacent changing bytes into multi-byte fields, then attempts
    to detect the most likely encoding for each group.
    """

    MAX_FIELD_BYTES = 8   # do not form fields wider than this

    # ------------------------------------------------------------------
    @staticmethod
    def group(byte_changes: list[dict], all_snapshots: list[tuple[float, bytes]]) -> list[dict]:
        """
        Group adjacent changing offsets that behave similarly into fields.

        A group is formed by a run of consecutive offsets that all changed.
        Adjacent offsets whose change counts differ by more than 50 % of the
        larger value are split into separate fields.

        Returns a list of field candidate dicts:
            {
                "offset": int,
                "size":   int,
                "raw_samples": list[bytes],  # one bytes object per snapshot
                "change_count": int,
                "max_val": int,
            }
        """
        if not byte_changes:
            return []

        offset_map = {r["offset"]: r for r in byte_changes}
        if not offset_map:
            return []

        sorted_offsets = sorted(offset_map)
        groups: list[list[int]] = []
        current_group: list[int] = [sorted_offsets[0]]

        for prev, curr in zip(sorted_offsets, sorted_offsets[1:]):
            if curr - prev > 1:
                # Gap in offsets → start a new group
                groups.append(current_group)
                current_group = [curr]
                continue
            # Adjacent: check if change counts are "compatible"
            cnt_prev = offset_map[prev]["change_count"]
            cnt_curr = offset_map[curr]["change_count"]
            max_cnt = max(cnt_prev, cnt_curr, 1)
            if abs(cnt_prev - cnt_curr) / max_cnt > MAX_CHANGE_COUNT_DIFF_RATIO:
                groups.append(current_group)
                current_group = [curr]
            else:
                current_group.append(curr)

        groups.append(current_group)

        # Split any group that exceeds MAX_FIELD_BYTES
        final_groups: list[list[int]] = []
        for g in groups:
            while len(g) > FieldGrouper.MAX_FIELD_BYTES:
                final_groups.append(g[:FieldGrouper.MAX_FIELD_BYTES])
                g = g[FieldGrouper.MAX_FIELD_BYTES:]
            if g:
                final_groups.append(g)

        # Build output structures
        fields: list[dict] = []
        min_len = min(len(snap) for _, snap in all_snapshots) if all_snapshots else 0
        for g in final_groups:
            start = g[0]
            size = len(g)
            max_offset = start + size
            if max_offset > min_len:
                size = min_len - start
            if size <= 0:
                continue
            change_count = max(
                offset_map.get(off, {}).get("change_count", 0) for off in g
            )
            max_val_combined = max(
                offset_map.get(off, {}).get("max_val", 0) for off in g
            )
            raw_samples = [snap[start:start + size] for _, snap in all_snapshots]
            fields.append({
                "offset":       start,
                "size":         size,
                "raw_samples":  raw_samples,
                "change_count": change_count,
                "max_val":      max_val_combined,
            })

        return fields

    # ------------------------------------------------------------------
    @staticmethod
    def detect_encoding(field_candidate: dict) -> tuple[Optional[str], Optional[str]]:
        """
        Try to detect encoding and endian for a field candidate.

        Tries in order:
          1. BCD        — all nibbles 0–9
          2. ASCII      — all bytes in printable ASCII range
          3. big-endian integer
          4. little-endian integer (only for size > 1)

        Returns (encoding, endian) where endian is "be"/"le" or None.
        """
        samples: list[bytes] = field_candidate["raw_samples"]
        size = field_candidate["size"]

        if not samples:
            return None, "be"

        # --- BCD ---
        if all(_is_bcd(s) for s in samples):
            return "bcd", None

        # --- ASCII / string ---
        if size >= 2 and all(_is_printable_ascii(s) for s in samples):
            return "ch", None

        # --- Integer (be / le) ---
        if size > 1:
            be_vals = [int.from_bytes(s, "big") for s in samples]
            le_vals = [int.from_bytes(s, "little") for s in samples]
            # Pick whichever produces a larger value spread (more likely to
            # represent a meaningful counter).  When spreads are equal we
            # default to big-endian, which is the most common byte order in
            # classic pinball NVRAM (Williams WPC, Stern, etc.).
            be_spread = max(be_vals) - min(be_vals)
            le_spread = max(le_vals) - min(le_vals)
            endian = "be" if be_spread >= le_spread else "le"
            return None, endian   # encoding=None → raw unsigned int

        # Single byte – no multi-byte endian concern
        return None, "be"


# ---------------------------------------------------------------------------
# NvramMapGenerator (orchestrator)
# ---------------------------------------------------------------------------

class NvramMapGenerator:
    """
    Orchestrates snapshot collection and map generation for a single ROM session.

    Usage (from watcher_core.py):
        gen = NvramMapGenerator(cfg, rom, nv_path, maps_dir)
        # each watcher tick:
        gen.on_game_tick()
        # when session ends:
        gen.on_game_end()
    """

    def __init__(self, cfg: Any, rom: str, nv_path: str, maps_dir: str) -> None:
        self.cfg = cfg
        self.rom = rom
        self.nv_path = nv_path
        self.maps_dir = maps_dir
        self._collector = NvramDiffCollector(nv_path)
        self._active = True

    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = "INFO") -> None:
        """Emit a log message via watcher_core.log() if available."""
        try:
            from watcher_core import log as _log_fn
            _log_fn(self.cfg, f"[MAP-GEN] {msg}", level)
        except Exception:
            # Fallback when running standalone / in tests
            print(f"[MAP-GEN] [{level}] {msg}")

    # ------------------------------------------------------------------
    def on_game_tick(self) -> None:
        """
        Should be called on every watcher tick (~every 1 s while a game is
        active).  Takes a new NVRAM snapshot respecting the internal cooldown.
        """
        if not self._active:
            return
        try:
            stored = self._collector.take_snapshot()
            if stored:
                self._log(
                    f"snapshot #{self._collector.snapshot_count} taken for {self.rom}",
                    "DEBUG",
                )
        except Exception as exc:
            self._log(f"snapshot failed: {exc}", "WARN")

    # ------------------------------------------------------------------
    def on_game_end(self) -> Optional[str]:
        """
        Analyses collected snapshots, generates (or refines) the .map.json
        file and returns the path to the saved file, or None on failure/
        insufficient data.
        """
        self._active = False

        n = self._collector.snapshot_count
        self._log(f"game ended for {self.rom} — {n} snapshot(s) collected")

        if n < MIN_SNAPSHOTS_TO_ANALYSE:
            self._log(
                f"not enough snapshots ({n} < {MIN_SNAPSHOTS_TO_ANALYSE}), skipping analysis",
                "WARN",
            )
            return None

        try:
            return self._analyse_and_save()
        except Exception as exc:
            self._log(f"analysis failed: {exc}", "WARN")
            return None

    # ------------------------------------------------------------------
    def _analyse_and_save(self) -> Optional[str]:
        byte_changes = self._collector.analyse()
        if not byte_changes:
            self._log("no changing bytes found — map not generated", "WARN")
            return None

        snapshots = self._collector._snapshots
        nv_size = len(snapshots[0][1]) if snapshots else 0
        platform = detect_platform(nv_size)

        self._log(
            f"analysis: {len(byte_changes)} changing byte(s) across {len(snapshots)} "
            f"snapshots, platform hint={platform}"
        )

        candidates = FieldGrouper.group(byte_changes, snapshots)
        if not candidates:
            self._log("field grouper produced no candidates", "WARN")
            return None

        fields: list[dict] = []
        for cand in candidates:
            encoding, endian = FieldGrouper.detect_encoding(cand)
            label = auto_label_field(
                offset=cand["offset"],
                size=cand["size"],
                encoding=encoding,
                max_val=cand["max_val"],
                change_count=cand["change_count"],
            )
            fields.append({
                "label":    label,
                "offset":   cand["offset"],
                "size":     cand["size"],
                "encoding": encoding,
                "endian":   endian,
            })

        self._log(f"generated {len(fields)} field(s) for {self.rom}")

        out_path = os.path.join(self.maps_dir, f"{self.rom}.map.json")

        # --- Self-improvement: load existing auto-generated map if present ---
        existing_snapshots_used = 0
        existing_fields: list[dict] = []
        if os.path.exists(out_path):
            try:
                with open(out_path, "r", encoding="utf-8") as fh:
                    existing = json.load(fh)
                if existing.get("_generator") == GENERATOR_MARKER:
                    existing_snapshots_used = int(existing.get("_snapshots_used", 0))
                    existing_fields = existing.get("fields", [])
                    self._log(
                        f"refining existing auto-map ({existing_snapshots_used} prior "
                        f"snapshots) for {self.rom}"
                    )
                else:
                    # Manually-created map — never overwrite
                    self._log(
                        f"manually-created map already exists for {self.rom} — skipping",
                        "WARN",
                    )
                    return None
            except Exception as exc:
                self._log(f"could not read existing map: {exc}", "WARN")

        # Merge new fields with existing ones (add new offsets, keep existing labels)
        merged = self._merge_fields(existing_fields, fields)
        total_snapshots = existing_snapshots_used + len(snapshots)

        # Build the map JSON
        mj: dict = {
            "_generator":      GENERATOR_MARKER,
            "_rom":            self.rom,
            "_platform":       platform,
            "_confidence":     "auto-generated",
            "_snapshots_used": total_snapshots,
            "_generated_at":   datetime.now(timezone.utc).isoformat(),
            "fields":          merged,
        }

        os.makedirs(self.maps_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(mj, fh, indent=2)

        self._log(
            f"map saved → {out_path} "
            f"({len(merged)} fields, {total_snapshots} total snapshots)"
        )
        return out_path

    # ------------------------------------------------------------------
    @staticmethod
    def _merge_fields(existing: list[dict], new: list[dict]) -> list[dict]:
        """
        Merge new field candidates with existing ones.
        Existing entries take precedence for the same offset; new offsets are
        appended.
        """
        existing_offsets = {f["offset"]: f for f in existing}
        merged = list(existing)
        for nf in new:
            if nf["offset"] not in existing_offsets:
                merged.append(nf)
        return sorted(merged, key=lambda f: f["offset"])
