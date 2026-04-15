"""core/webrtc_stream.py – WebRTC screen-capture streaming for Duel PiP.

Provides a peer-to-peer video stream between two duel players using WebRTC
(via the ``aiortc`` library).  Signaling is done through the existing Firebase
real-time database so no extra infrastructure is required.

Architecture
------------
Both players create a ``WebRTCSession``.  The player whose sanitised Firebase
key sorts first alphabetically becomes the *offerer*; the other is the
*answerer*.  Each side adds its own ``ScreenCaptureTrack`` to the connection,
so the resulting single RTCPeerConnection carries video in both directions.

Signaling path (Firebase ``duels/{duel_id}/webrtc/``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``participants/{player_key}``   → registration timestamp (written on start)
``{player_key}/offer``          → full SDP offer  (written by offerer after ICE)
``{offerer_key}/answer``        → full SDP answer (written by answerer after ICE)

ICE candidates are embedded in the SDP (non-trickle / "complete offer") by
waiting for ``iceGatheringState == "complete"`` before publishing, which
avoids the need for a separate ICE-candidate signaling round-trip.

Graceful degradation
--------------------
If ``aiortc`` or ``mss`` are not installed the module still imports cleanly.
``WebRTCSession.available`` returns ``False`` and ``start()`` logs a warning
without raising.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------

try:
    import av as _av
    from aiortc import (
        RTCConfiguration,
        RTCIceServer,
        RTCPeerConnection,
        RTCSessionDescription,
    )
    from aiortc.mediastreams import VideoStreamTrack
    _AIORTC_OK = True
except ImportError:
    _AIORTC_OK = False
    VideoStreamTrack = object  # placeholder so class body below stays importable

try:
    import mss as _mss_module
    _MSS_OK = True
except ImportError:
    _MSS_OK = False

# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------

_POLL_INTERVAL_S: float = 2.0    # seconds between Firebase polls
_ICE_TIMEOUT_S: float = 15.0     # max wait for ICE gathering
_EXCHANGE_TIMEOUT_S: float = 60.0  # max wait for signaling exchange

# ---------------------------------------------------------------------------
# Screen capture track (only defined when deps are available)
# ---------------------------------------------------------------------------

if _AIORTC_OK and _MSS_OK:
    class ScreenCaptureTrack(VideoStreamTrack):
        """``aiortc`` ``VideoStreamTrack`` that streams a desktop monitor via ``mss``."""

        kind = "video"

        def __init__(self, monitor: int = 1) -> None:
            super().__init__()
            self._monitor_idx = monitor
            self._sct: Optional[object] = None

        async def recv(self):  # type: ignore[override]
            pts, time_base = await self.next_timestamp()

            loop = asyncio.get_event_loop()
            frame = await loop.run_in_executor(None, self._capture_frame)

            frame.pts = pts
            frame.time_base = time_base
            return frame

        def _capture_frame(self):
            """Capture one screen frame (called in executor thread)."""
            from PIL import Image

            if self._sct is None:
                self._sct = _mss_module.mss()

            monitors = self._sct.monitors  # type: ignore[union-attr]
            # monitors[0] is the "all screens" composite; real monitors start at 1.
            idx = max(1, min(self._monitor_idx, len(monitors) - 1))
            mon = monitors[idx]

            raw = self._sct.grab(mon)  # type: ignore[union-attr]
            # frombytes with "BGRX" raw decoder converts the mss BGRA buffer to RGB.
            pil_img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

            return _av.VideoFrame.from_image(pil_img)

else:
    # Stub so imports of ScreenCaptureTrack from outside still work.
    class ScreenCaptureTrack:  # type: ignore[no-redef]
        """Unavailable: aiortc/mss not installed."""


# ---------------------------------------------------------------------------
# Qt signal carrier
# ---------------------------------------------------------------------------

class _FrameEmitter(QObject):
    """Carries received video frames as PyQt signals (thread-safe emission)."""

    frame_ready = pyqtSignal(QImage)


# ---------------------------------------------------------------------------
# Helper: build ICE server list from config
# ---------------------------------------------------------------------------

def _ice_servers_from_cfg(cfg) -> list:
    """Return a list of ``RTCIceServer`` instances based on app config."""
    ov = cfg.OVERLAY or {}
    stun_urls = ov.get(
        "webrtc_stun_servers",
        ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"],
    )
    servers = [RTCIceServer(urls=u) for u in stun_urls]

    turn_url = ov.get("webrtc_turn_server", "").strip()
    if turn_url:
        servers.append(
            RTCIceServer(
                urls=turn_url,
                username=ov.get("webrtc_turn_username", ""),
                credential=ov.get("webrtc_turn_credential", ""),
            )
        )

    return servers


# ---------------------------------------------------------------------------
# Main session class
# ---------------------------------------------------------------------------

class WebRTCSession:
    """Manages a bidirectional WebRTC video session for a Duel PiP stream.

    Parameters
    ----------
    cfg:
        The ``AppConfig`` instance (needed for Firebase URL and STUN/TURN config).
    duel_id:
        The Firebase duel identifier.
    player_key:
        The local player's sanitised Firebase key (used as signaling node name).
    log_fn:
        Optional callable ``(msg: str, level: str) -> None`` for logging.
        When omitted a no-op is used.

    Usage::

        session = WebRTCSession(cfg, duel_id, player_key, log_fn=log)
        session.frame_emitter.frame_ready.connect(pip_overlay._on_frame)
        session.start()
        # …
        session.stop()          # stops stream and cleans up Firebase
    """

    def __init__(
        self,
        cfg,
        duel_id: str,
        player_key: str,
        log_fn=None,
    ) -> None:
        self._cfg = cfg
        self._duel_id = duel_id
        self._player_key = player_key
        self._log = log_fn if log_fn is not None else (lambda msg, level="INFO": None)

        self.frame_emitter = _FrameEmitter()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._pc: Optional[object] = None  # RTCPeerConnection when available
        self._screen_track: Optional[object] = None
        self._cancel_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """True when aiortc and mss are installed."""
        return _AIORTC_OK and _MSS_OK

    def start(self) -> None:
        """Start the WebRTC session in a dedicated asyncio background thread."""
        if not _AIORTC_OK:
            self._log(
                "[WebRTC] aiortc is not installed — Duel PiP disabled. "
                "Install with: pip install aiortc",
                "WARN",
            )
            return
        if not _MSS_OK:
            self._log(
                "[WebRTC] mss is not installed — Duel PiP disabled.",
                "WARN",
            )
            return

        self._cancel_event.clear()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="WebRTCSession",
        )
        self._thread.start()
        self._log("[WebRTC] Session thread started", "INFO")

    def stop(self) -> None:
        """Stop the WebRTC session and remove Firebase signaling data."""
        self._cancel_event.set()

        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._cleanup_async(), loop)
                fut.result(timeout=5.0)
            except Exception as e:
                self._log(f"[WebRTC] Cleanup error: {e}", "WARN")
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass

        thread = self._thread
        if thread is not None:
            thread.join(timeout=3.0)

        self._loop = None
        self._thread = None
        self._log("[WebRTC] Session stopped", "INFO")

    # ------------------------------------------------------------------
    # Internal: asyncio event loop runner
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session_main())
        except Exception as e:
            self._log(f"[WebRTC] Session main error: {e}", "WARN")
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self._loop.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal: async cleanup
    # ------------------------------------------------------------------

    async def _cleanup_async(self) -> None:
        """Close the peer connection and remove Firebase signaling data."""
        if self._pc is not None:
            try:
                await self._pc.close()
            except Exception as e:
                self._log(f"[WebRTC] PC close error: {e}", "WARN")
            self._pc = None

        try:
            base = f"duels/{self._duel_id}/webrtc"
            # Remove participant registration
            await self._fb_set(f"{base}/participants/{self._player_key}", None)
            # Remove our offer/answer node
            await self._fb_set(f"{base}/{self._player_key}", None)
        except Exception as e:
            self._log(f"[WebRTC] Firebase cleanup error: {e}", "WARN")

    # ------------------------------------------------------------------
    # Internal: Firebase helpers (run in executor thread)
    # ------------------------------------------------------------------

    async def _fb_set(self, path: str, data) -> bool:
        from core.cloud_sync import CloudSync
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: CloudSync.set_node(self._cfg, path, data)
        )

    async def _fb_get(self, path: str):
        from core.cloud_sync import CloudSync
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: CloudSync.fetch_node(self._cfg, path)
        )

    # ------------------------------------------------------------------
    # Internal: ICE gathering wait
    # ------------------------------------------------------------------

    async def _wait_for_ice(self, timeout: float = _ICE_TIMEOUT_S) -> None:
        """Block until ICE gathering is complete or timeout/cancel occurs."""
        start = time.monotonic()
        while self._pc.iceGatheringState != "complete":
            if self._cancel_event.is_set():
                return
            if time.monotonic() - start > timeout:
                self._log("[WebRTC] ICE gathering timed out — using partial candidates", "WARN")
                return
            await asyncio.sleep(0.1)

    # ------------------------------------------------------------------
    # Internal: receive video from remote track
    # ------------------------------------------------------------------

    async def _receive_video(self, track) -> None:
        """Receive frames from a remote video track and emit as ``QImage``."""
        self._log("[WebRTC] Remote video track attached — receiving frames", "INFO")
        while not self._cancel_event.is_set():
            try:
                frame = await asyncio.wait_for(track.recv(), timeout=5.0)
                # Convert av.VideoFrame → PIL Image → QImage
                pil_img = frame.to_image()
                pil_rgb = pil_img.convert("RGB")
                w, h = pil_rgb.size
                raw = pil_rgb.tobytes("raw", "RGB")
                qimg = QImage(raw, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                self.frame_emitter.frame_ready.emit(qimg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if not self._cancel_event.is_set():
                    self._log(f"[WebRTC] Frame receive error: {e}", "WARN")
                break
        self._log("[WebRTC] Video receive loop ended", "INFO")

    # ------------------------------------------------------------------
    # Internal: main session coroutine
    # ------------------------------------------------------------------

    async def _session_main(self) -> None:
        """Orchestrate signaling, peer connection setup, and streaming."""
        base = f"duels/{self._duel_id}/webrtc"
        self._log(
            f"[WebRTC] Joining duel {self._duel_id} as player '{self._player_key}'",
            "INFO",
        )

        # --- Step 1: Register as participant ---
        await self._fb_set(f"{base}/participants/{self._player_key}", int(time.time()))

        # --- Step 2: Wait for the opponent to register ---
        opponent_key: Optional[str] = None
        deadline = time.monotonic() + _EXCHANGE_TIMEOUT_S

        while not self._cancel_event.is_set() and time.monotonic() < deadline:
            participants = await self._fb_get(f"{base}/participants") or {}
            others = [k for k in participants.keys() if k != self._player_key]
            if others:
                opponent_key = others[0]
                break
            await asyncio.sleep(_POLL_INTERVAL_S)

        if not opponent_key or self._cancel_event.is_set():
            self._log(
                "[WebRTC] No opponent registered within timeout — PiP unavailable",
                "WARN",
            )
            return

        self._log(f"[WebRTC] Opponent registered: '{opponent_key}'", "INFO")

        # --- Step 3: Determine offerer vs answerer (alphabetical order) ---
        is_offerer = self._player_key < opponent_key
        role = "OFFERER" if is_offerer else "ANSWERER"
        self._log(f"[WebRTC] Role: {role}", "INFO")

        # --- Step 4: Build RTCPeerConnection ---
        ice_servers = _ice_servers_from_cfg(self._cfg)
        cfg_rtc = RTCConfiguration(iceServers=ice_servers)
        self._pc = RTCPeerConnection(configuration=cfg_rtc)

        # Add local screen capture track
        self._screen_track = ScreenCaptureTrack()
        self._pc.addTrack(self._screen_track)

        # Handle incoming video track (opponent's screen)
        @self._pc.on("track")
        def on_track(track):
            if track.kind == "video":
                asyncio.get_event_loop().create_task(self._receive_video(track))

        @self._pc.on("connectionstatechange")
        async def on_connection_state():
            self._log(
                f"[WebRTC] Connection state → {self._pc.connectionState}", "INFO"
            )

        # --- Step 5: Run role-specific signaling ---
        if is_offerer:
            await self._run_as_offerer(base)
        else:
            await self._run_as_answerer(base, opponent_key)

        # --- Step 6: Keep session alive until cancelled or connection drops ---
        while not self._cancel_event.is_set():
            if self._pc and self._pc.connectionState in ("failed", "closed"):
                self._log("[WebRTC] Connection closed/failed", "WARN")
                break
            await asyncio.sleep(1.0)

        await self._cleanup_async()

    # ------------------------------------------------------------------
    # Internal: offerer flow
    # ------------------------------------------------------------------

    async def _run_as_offerer(self, base: str) -> None:
        """Create an SDP offer, wait for ICE, publish to Firebase, wait for answer."""
        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)

        await self._wait_for_ice()
        if self._cancel_event.is_set():
            return

        sdp = self._pc.localDescription.sdp
        ok = await self._fb_set(f"{base}/{self._player_key}/offer", sdp)
        if not ok:
            self._log("[WebRTC] Failed to publish offer to Firebase", "WARN")
            return
        self._log("[WebRTC] Offer published to Firebase", "INFO")

        # Poll for the answerer's SDP answer
        deadline = time.monotonic() + _EXCHANGE_TIMEOUT_S
        while not self._cancel_event.is_set() and time.monotonic() < deadline:
            answer_sdp = await self._fb_get(f"{base}/{self._player_key}/answer")
            if answer_sdp and isinstance(answer_sdp, str):
                try:
                    await self._pc.setRemoteDescription(
                        RTCSessionDescription(sdp=answer_sdp, type="answer")
                    )
                    self._log("[WebRTC] Answer set — connection establishing", "INFO")
                    return
                except Exception as e:
                    self._log(f"[WebRTC] Failed to set remote answer: {e}", "WARN")
                    return
            await asyncio.sleep(_POLL_INTERVAL_S)

        self._log("[WebRTC] Timed out waiting for SDP answer", "WARN")

    # ------------------------------------------------------------------
    # Internal: answerer flow
    # ------------------------------------------------------------------

    async def _run_as_answerer(self, base: str, offerer_key: str) -> None:
        """Wait for the offerer's SDP, create an answer, publish to Firebase."""
        # Poll for the offerer's SDP offer
        deadline = time.monotonic() + _EXCHANGE_TIMEOUT_S
        offer_sdp: Optional[str] = None

        while not self._cancel_event.is_set() and time.monotonic() < deadline:
            offer_sdp = await self._fb_get(f"{base}/{offerer_key}/offer")
            if offer_sdp and isinstance(offer_sdp, str):
                break
            await asyncio.sleep(_POLL_INTERVAL_S)

        if not offer_sdp or self._cancel_event.is_set():
            self._log("[WebRTC] Timed out waiting for SDP offer", "WARN")
            return

        self._log("[WebRTC] Offer received — creating answer", "INFO")

        try:
            await self._pc.setRemoteDescription(
                RTCSessionDescription(sdp=offer_sdp, type="offer")
            )
            answer = await self._pc.createAnswer()
            await self._pc.setLocalDescription(answer)

            await self._wait_for_ice()
            if self._cancel_event.is_set():
                return

            answer_sdp = self._pc.localDescription.sdp
            ok = await self._fb_set(f"{base}/{offerer_key}/answer", answer_sdp)
            if not ok:
                self._log("[WebRTC] Failed to publish answer to Firebase", "WARN")
                return
            self._log("[WebRTC] Answer published to Firebase — connection establishing", "INFO")
        except Exception as e:
            self._log(f"[WebRTC] Answer creation/publish failed: {e}", "WARN")
