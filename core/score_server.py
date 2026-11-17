"""core/score_server.py – Client for superhac's VPX *score-server* plugin.

The plugin (VPX 10.8.1+) broadcasts JSON messages on ``ws://127.0.0.1:3131``:

* ``game_start`` / ``game_end``            – a pinball game begins / ends
* ``current_scores``                       – players, current player, ball, scores
* ``high_scores`` / ``table_loaded`` / ``badge`` – ignored here

This module keeps a lightweight background connection and records, per
VPX session, every game with its player count, final scores and the points
each player scored on each ball.  The Watcher only *reads* this data: it is
used to decide single- vs. multiplayer and to fill the multiplayer page.

Standard library only (no extra dependency): a minimal RFC 6455 client is
enough because the server is local and only sends unmasked text frames.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import threading
import time
from typing import Any, Dict, List, Optional

HOST = "127.0.0.1"
PORT = 3131
RECONNECT_SEC = 3.0


def _to_int(v: Any) -> int:
    try:
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v or "").strip().replace(",", "").replace(".", "").replace(" ", "")
        return int(s) if s.lstrip("-").isdigit() else 0
    except Exception:
        return 0


def _player_index(entry: dict, fallback: int) -> int:
    """'Player 2' -> 2 (1-based)."""
    try:
        txt = str(entry.get("player") or "")
        digits = "".join(ch for ch in txt if ch.isdigit())
        if digits:
            return int(digits)
    except Exception:
        pass
    return fallback


class _Game:
    """Live tracking of one pinball game."""

    def __init__(self, rom: str, started: float):
        self.rom = rom
        self.started = started
        self.ended: Optional[float] = None
        self.players = 1
        self.scores: Dict[int, int] = {}
        # (player, ball) -> points scored on that ball
        self.ball_points: Dict[tuple, int] = {}
        self._cur: Optional[tuple] = None          # (player, ball) currently in play
        self._cur_start_score = 0
        # Raw NVRAM snapshots from the plugin, taken on every player/ball change:
        # [{"ts", "player", "ball", "players", "data": bytes}]
        self.snapshots: List[dict] = []

    def update(self, players: int, cur_player: int, cur_ball: int, scores: Dict[int, int]) -> None:
        if players > self.players:
            self.players = players
        for p, sc in scores.items():
            self.scores[p] = sc
        key = (cur_player, cur_ball) if cur_player > 0 and cur_ball > 0 else None
        if key != self._cur:
            self._close_ball()
            self._cur = key
            if key is not None:
                self._cur_start_score = int(self.scores.get(cur_player, 0))

    def _close_ball(self) -> None:
        if self._cur is None:
            return
        p, _b = self._cur
        pts = int(self.scores.get(p, 0)) - int(self._cur_start_score)
        if pts < 0:
            pts = 0
        self.ball_points[self._cur] = self.ball_points.get(self._cur, 0) + pts
        self._cur = None

    def finish(self, ts: float, final_scores: Optional[Dict[int, int]] = None) -> None:
        if final_scores:
            for p, sc in final_scores.items():
                if sc > 0 or p not in self.scores:
                    self.scores[p] = sc
        self._close_ball()
        self.ended = ts

    def summary(self, include_snapshots: bool = False) -> dict:
        players = max(1, int(self.players or 1), max(self.scores.keys(), default=1))
        out_players = []
        for p in range(1, players + 1):
            balls = sorted((b, pts) for (pp, b), pts in self.ball_points.items() if pp == p)
            ball_vals = [pts for _b, pts in balls]
            out_players.append({
                "player": p,
                "score": int(self.scores.get(p, 0)),
                "balls": [{"ball": b, "points": pts} for b, pts in balls],
                "best_ball": max(ball_vals) if ball_vals else 0,
                "best_ball_no": (max(balls, key=lambda x: x[1])[0] if balls else 0),
                "avg_ball": int(sum(ball_vals) / len(ball_vals)) if ball_vals else 0,
            })
        winner = 0
        if players > 1 and out_players:
            top = max(out_players, key=lambda x: x["score"])
            if top["score"] > 0 and sum(1 for x in out_players if x["score"] == top["score"]) == 1:
                winner = top["player"]
        return {
            "rom": self.rom,
            "started": self.started,
            "ended": self.ended,
            "players": players,
            "player_stats": out_players,
            "winner": winner,
            **({"snapshots": list(self.snapshots)} if include_snapshots else {}),
        }


class ScoreServerClient:
    """Background WebSocket client; thread-safe accessors for the Watcher."""

    def __init__(self, log_fn=None):
        self._log = log_fn or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._pending = b""
        self.connected = False
        self.last_rom = ""
        self._games: List[_Game] = []
        self._current: Optional[_Game] = None
        self._session_start = 0.0
        self._last_snapshot: Optional[dict] = None

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ScoreServerClient")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    # ── session API used by the Watcher ─────────────────────────────────
    def begin_session(self, ts: Optional[float] = None) -> None:
        """Mark the start of a VPX table session (keeps a game already running)."""
        with self._lock:
            self._session_start = float(ts or time.time()) - 90.0  # plugin queues ~60 s
            self._games = [g for g in self._games if (g.ended is None) or (g.ended >= self._session_start)]

    def session_summary(self, include_snapshots: bool = False) -> dict:
        """Games recorded since :meth:`begin_session` (running game included).

        ``include_snapshots`` adds the raw NVRAM snapshots (bytes, not JSON
        serialisable) per game for the per-player action breakdown.
        """
        with self._lock:
            games = [g for g in self._games if g.started >= self._session_start or g.ended is None
                     or (g.ended or 0) >= self._session_start]
            if self._current is not None and self._current.ended is None and self._current not in games:
                games.append(self._current)
            summaries = []
            for g in games:
                if g.ended is None:
                    g._close_ball()
                summaries.append(g.summary(include_snapshots))
        max_players = max((s["players"] for s in summaries), default=0)
        return {
            "connected": self.connected,
            "games": summaries,
            "max_players": max_players,
            "multiplayer": max_players > 1,
        }

    def end_session(self) -> None:
        with self._lock:
            self._games = []
            if self._current is not None and self._current.ended is not None:
                self._current = None

    # ── networking ───────────────────────────────────────────────────────
    def _run(self) -> None:
        was_connected = False
        while not self._stop.is_set():
            try:
                self._connect()
                if not was_connected:
                    self._log("[SCORE_SERVER] connected to score-server plugin")
                was_connected = True
                self.connected = True
                self._read_loop()
            except (ConnectionRefusedError, TimeoutError, socket.timeout, OSError):
                pass
            except Exception as e:
                self._log(f"[SCORE_SERVER] client error: {e}", "WARN")
            finally:
                if self.connected:
                    self._log("[SCORE_SERVER] connection closed")
                self.connected = False
                was_connected = False
                try:
                    if self._sock:
                        self._sock.close()
                except Exception:
                    pass
                self._sock = None
            self._stop.wait(RECONNECT_SEC)

    def _connect(self) -> None:
        s = socket.create_connection((HOST, PORT), timeout=2.0)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET / HTTP/1.1\r\nHost: {HOST}:{PORT}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        s.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = s.recv(1024)
            if not chunk:
                raise ConnectionError("handshake closed")
            buf += chunk
            if len(buf) > 8192:
                raise ConnectionError("handshake too long")
        head, rest = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError("handshake rejected")
        s.settimeout(1.0)
        self._sock = s
        self._pending = rest

    def _recv_exact(self, n: int) -> bytes:
        out = bytearray()
        if self._pending:
            take = self._pending[:n]
            out += take
            self._pending = self._pending[len(take):]
        while len(out) < n:
            if self._stop.is_set():
                raise ConnectionError("stopping")
            try:
                chunk = self._sock.recv(n - len(out))
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError("closed")
            out += chunk
        return bytes(out)

    def _send_frame(self, opcode: int, payload: bytes = b"") -> None:
        # Client frames must be masked.
        mask = os.urandom(4)
        hdr = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        try:
            self._sock.sendall(bytes(hdr) + mask + masked)
        except Exception:
            pass

    def _read_loop(self) -> None:
        fragments = bytearray()
        while not self._stop.is_set():
            b1, b2 = self._recv_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv_exact(8))[0]
            if n > 8 * 1024 * 1024:
                raise ConnectionError("frame too large")
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(n) if n else b""
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:      # close
                raise ConnectionError("server closed")
            if opcode == 0x9:      # ping
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:      # pong
                continue
            if opcode in (0x1, 0x0):
                fragments += payload
                if fin:
                    text = fragments.decode("utf-8", errors="replace")
                    fragments = bytearray()
                    self._handle(text)

    # ── message handling ─────────────────────────────────────────────────
    def _handle(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except Exception:
            return
        if not isinstance(msg, dict):
            return
        mtype = str(msg.get("type") or "")
        rom = str(msg.get("rom") or "")
        now = time.time()
        with self._lock:
            if rom:
                self.last_rom = rom
            if mtype == "game_start":
                if self._current is not None and self._current.ended is None:
                    self._current.finish(now)
                self._current = _Game(rom, now)
                if self._last_snapshot is not None:
                    self._current.snapshots.append(dict(self._last_snapshot))  # baseline
                self._games.append(self._current)
            elif mtype == "nvram_snapshot":
                try:
                    data = base64.b64decode(str(msg.get("data") or ""), validate=False)
                except Exception:
                    data = b""
                if data:
                    snap = {
                        "ts": now,
                        "player": _to_int(msg.get("current_player")),
                        "ball": _to_int(msg.get("current_ball")),
                        "players": _to_int(msg.get("players")),
                        "data": data,
                    }
                    self._last_snapshot = snap
                    g = self._current
                    # Also accept the final snapshot that may arrive just after game_end.
                    if g is not None and (g.ended is None or now - g.ended < 5.0):
                        g.snapshots.append(snap)
                        if len(g.snapshots) > 400:   # safety cap
                            del g.snapshots[1:101]
            elif mtype == "current_scores":
                if self._current is None or self._current.ended is not None:
                    # Joined mid-game (or game_start missed): start tracking now.
                    self._current = _Game(rom, now)
                    self._games.append(self._current)
                scores = {}
                for i, e in enumerate(msg.get("scores") or []):
                    if isinstance(e, dict):
                        scores[_player_index(e, i + 1)] = _to_int(e.get("score"))
                self._current.update(
                    _to_int(msg.get("players")) or 1,
                    _to_int(msg.get("current_player")),
                    _to_int(msg.get("current_ball")),
                    scores,
                )
            elif mtype == "game_end":
                if self._current is not None and self._current.ended is None:
                    final = {}
                    for i, e in enumerate(msg.get("scores") or []):
                        if isinstance(e, dict):
                            final[_player_index(e, i + 1)] = _to_int(e.get("score"))
                    self._current.finish(now, final)


_client: Optional[ScoreServerClient] = None
_client_lock = threading.Lock()


def get_client(log_fn=None) -> ScoreServerClient:
    """Process-wide client singleton (started on first use)."""
    global _client
    with _client_lock:
        if _client is None:
            _client = ScoreServerClient(log_fn=log_fn)
        _client.start()
        return _client


def peek_client() -> Optional[ScoreServerClient]:
    return _client
