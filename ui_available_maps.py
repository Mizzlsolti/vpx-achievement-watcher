from __future__ import annotations

import os

from PyQt6.QtCore import QThread, pyqtSignal

from watcher_core import (
    AppConfig,
    log,
    run_vpxtool_get_rom,
    run_vpxtool_info_show,
)
from ui_vps import _load_vps_mapping


class _AvailableMapsWorker(QThread):
    """Background worker that scans TABLES_DIR and builds the available-maps list."""
    progress = pyqtSignal(int, int, str)   # (current_index, total, filename)
    finished = pyqtSignal(list)            # sorted list of entry dicts

    def __init__(self, cfg, watcher, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.watcher = watcher
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        romnames = self.watcher.ROMNAMES or {}

        # Build base list from cloud index
        index_roms = set(k for k in (self.watcher.INDEX or {}).keys() if not k.startswith("_"))
        entries: dict = {}
        for rom in index_roms:
            title = romnames.get(rom, "Unknown Table")
            entries[rom] = {"rom": rom, "title": title, "has_map": False, "is_local": False, "vps_id": "", "vpx_path": ""}

        # Collect all .vpx files first so we can report total count
        tables_dir = getattr(self.cfg, "TABLES_DIR", None)
        vpx_files = []
        if tables_dir and os.path.isdir(tables_dir):
            for root, _dirs, files in os.walk(tables_dir):
                for fname in files:
                    if fname.lower().endswith(".vpx"):
                        vpx_files.append((root, fname))

        # Build a lowercase-to-original-key map once for O(1) case-insensitive lookups
        entries_lower: dict = {k.lower(): k for k in entries}

        total = len(vpx_files)
        for i, (root, fname) in enumerate(vpx_files):
            if self._cancel:
                break
            self.progress.emit(i, total, fname)
            vpx_path = os.path.join(root, fname)
            try:
                rom = run_vpxtool_get_rom(self.cfg, vpx_path, suppress_warn=True)
            except Exception:
                rom = None
            if not rom:
                continue
            # Normalize ROM to lowercase for case-insensitive matching against cloud index
            rom_lower = rom.lower()
            matched_key = entries_lower.get(rom_lower)
            if matched_key:
                rom = matched_key
            elif rom not in entries:
                title = romnames.get(rom) or romnames.get(rom_lower) or fname.rsplit(".", 1)[0]
                entries[rom] = {"rom": rom, "title": title, "has_map": False, "is_local": False, "vps_id": "", "vpx_path": ""}
                entries_lower[rom_lower] = rom
            entries[rom]["is_local"] = True
            entries[rom]["vpx_path"] = vpx_path   # store path for later author extraction

            # Store vpx_info metadata for richer table display
            try:
                vpx_info = run_vpxtool_info_show(self.cfg, vpx_path)
                if vpx_info:
                    entries[rom]["vpx_info"] = vpx_info
                    # Use table_name from info if the current title is just the filename
                    info_name = (vpx_info.get("table_name") or "").strip()
                    if info_name and entries[rom]["title"] == fname.rsplit(".", 1)[0]:
                        entries[rom]["title"] = info_name
            except Exception:
                pass

        # Check NVRAM-Map availability (with family fallback, same as during gameplay)
        for rom, entry in entries.items():
            if self._cancel:
                break
            try:
                if self.watcher._has_any_map(rom):
                    entry["has_map"] = True
                else:
                    fields, src, matched = self.watcher._resolve_map_from_index_then_family(rom)
                    entry["has_map"] = bool(fields)
            except Exception:
                entry["has_map"] = False

        # Load current VPS mappings
        mapping = _load_vps_mapping(self.cfg)
        for rom, entry in entries.items():
            entry["vps_id"] = mapping.get(rom, mapping.get(rom.lower(), ""))

        result = sorted(entries.values(), key=lambda e: e["title"].lower())
        self.finished.emit(result)
