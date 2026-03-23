"""
Sound engine for VPX Achievement Watcher.
Generates WAV audio in memory (no external files, no pip dependencies).
Playback via winsound on Windows; silent fallback on other platforms.
"""
from __future__ import annotations

import io
import math
import struct
import wave

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22050   # Hz – good enough for short SFX, lower CPU cost
DEFAULT_VOLUME = 70   # 0-100

SOUND_PACKS = {
    "arcade":         "Arcade",
    "subtle":         "Subtle",
    "sci_fi":         "Sci-Fi",
    "retro_8bit":     "Retro 8-Bit",
    "pinball_classic": "Pinball Classic",
}

SOUND_EVENTS = [
    ("achievement_unlock", "🏆 Achievement Unlock"),
    ("achievement_rare",   "✨ Rare Achievement"),
    ("challenge_start",    "⚔️ Challenge Start"),
    ("challenge_complete", "🏁 Challenge Complete"),
    ("challenge_fail",     "❌ Challenge Fail"),
    ("level_up",           "⬆️ Level Up"),
    ("toast_info",         "ℹ️ Info Notification"),
    ("toast_warning",      "⚠️ Warning"),
    ("countdown_tick",     "⏱️ Countdown Tick"),
    ("countdown_final",    "🔔 Countdown Final"),
    ("personal_best",      "🏅 Personal Best"),
    ("combo",              "💥 Combo"),
]

# Cache: (pack_id, event_name) -> bytes (WAV data)
_cache: dict[tuple[str, str], bytes] = {}

# ---------------------------------------------------------------------------
# Low-level WAV helpers
# ---------------------------------------------------------------------------

def _to_bytes(samples: list[float], volume: float = 1.0) -> bytes:
    """Convert a list of float samples [-1.0, 1.0] to 16-bit PCM bytes."""
    clamp = max(-1.0, min(1.0, volume))
    out = bytearray()
    for s in samples:
        val = int(max(-32768, min(32767, s * clamp * 32767)))
        out += struct.pack("<h", val)
    return bytes(out)


def _make_wav(samples: list[float], volume: float = 1.0) -> bytes:
    """Wrap PCM samples in a proper WAV container and return raw bytes."""
    pcm = _to_bytes(samples, volume)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


def _sine(freq: float, duration: float, amplitude: float = 0.8) -> list[float]:
    n = int(SAMPLE_RATE * duration)
    return [amplitude * math.sin(2 * math.pi * freq * i / SAMPLE_RATE) for i in range(n)]


def _square(freq: float, duration: float, amplitude: float = 0.6) -> list[float]:
    n = int(SAMPLE_RATE * duration)
    result = []
    for i in range(n):
        phase = (freq * i / SAMPLE_RATE) % 1.0
        result.append(amplitude if phase < 0.5 else -amplitude)
    return result


def _sweep(f_start: float, f_end: float, duration: float,
           amplitude: float = 0.7, wave_fn: str = "sine") -> list[float]:
    """Linear frequency sweep."""
    n = int(SAMPLE_RATE * duration)
    result = []
    phase = 0.0
    for i in range(n):
        t = i / n
        freq = f_start + (f_end - f_start) * t
        phase += 2 * math.pi * freq / SAMPLE_RATE
        if wave_fn == "sine":
            result.append(amplitude * math.sin(phase))
        else:
            result.append(amplitude if (phase % (2 * math.pi)) < math.pi else -amplitude)
    return result


def _envelope(samples: list[float], attack: float = 0.01,
              release: float = 0.05) -> list[float]:
    """Apply simple linear attack/release envelope."""
    n = len(samples)
    atk_n = int(SAMPLE_RATE * attack)
    rel_n = int(SAMPLE_RATE * release)
    out = list(samples)
    for i in range(min(atk_n, n)):
        out[i] *= i / atk_n
    for i in range(min(rel_n, n)):
        idx = n - 1 - i
        out[idx] *= i / rel_n
    return out


def _concat(*sample_lists: list[float]) -> list[float]:
    result: list[float] = []
    for sl in sample_lists:
        result.extend(sl)
    return result


def _silence(duration: float) -> list[float]:
    return [0.0] * int(SAMPLE_RATE * duration)


def _mix(a: list[float], b: list[float]) -> list[float]:
    n = max(len(a), len(b))
    a = a + [0.0] * (n - len(a))
    b = b + [0.0] * (n - len(b))
    return [max(-1.0, min(1.0, a[i] + b[i])) for i in range(n)]


# ---------------------------------------------------------------------------
# Sound pack definitions
# ---------------------------------------------------------------------------

def _build_arcade(event: str) -> list[float]:
    if event == "achievement_unlock":
        return _envelope(_concat(
            _square(440, 0.08), _square(523, 0.08), _square(659, 0.12),
        ), attack=0.005, release=0.04)
    if event == "achievement_rare":
        s = _concat(
            _square(330, 0.06), _square(392, 0.06),
            _square(494, 0.06), _square(659, 0.10), _square(988, 0.15),
        )
        return _envelope(s, attack=0.005, release=0.06)
    if event == "challenge_start":
        return _envelope(_concat(
            _square(220, 0.08), _silence(0.04), _square(220, 0.08), _silence(0.04), _square(330, 0.12),
        ), release=0.05)
    if event == "challenge_complete":
        return _envelope(_concat(
            _square(330, 0.08), _square(440, 0.08), _square(523, 0.08), _square(659, 0.15),
        ), attack=0.005, release=0.06)
    if event == "challenge_fail":
        return _envelope(_concat(
            _square(330, 0.10), _square(262, 0.10), _square(196, 0.14),
        ), release=0.06)
    if event == "level_up":
        return _envelope(_sweep(262, 1047, 0.35, amplitude=0.6, wave_fn="square"), release=0.08)
    if event == "toast_info":
        return _envelope(_square(880, 0.07), attack=0.003, release=0.03)
    if event == "toast_warning":
        return _envelope(_concat(
            _square(659, 0.07), _silence(0.04), _square(659, 0.07),
        ), release=0.03)
    if event == "countdown_tick":
        return _envelope(_square(440, 0.05), attack=0.002, release=0.02)
    if event == "countdown_final":
        return _envelope(_concat(
            _square(523, 0.06), _silence(0.02), _square(587, 0.06),
            _silence(0.02), _square(659, 0.06), _silence(0.02), _square(880, 0.12),
        ), release=0.04)
    if event == "personal_best":
        return _envelope(_concat(
            _square(523, 0.07), _square(659, 0.07), _square(784, 0.07), _square(1047, 0.15),
        ), attack=0.005, release=0.06)
    if event == "combo":
        return _envelope(_square(659, 0.06), attack=0.002, release=0.02)
    return []


def _build_subtle(event: str) -> list[float]:
    if event == "achievement_unlock":
        return _envelope(_concat(
            _sine(523, 0.10), _sine(659, 0.10), _sine(784, 0.18),
        ), attack=0.02, release=0.08)
    if event == "achievement_rare":
        s = _concat(
            _sine(392, 0.10), _sine(523, 0.10),
            _sine(659, 0.10), _sine(784, 0.20),
        )
        return _envelope(s, attack=0.02, release=0.10)
    if event == "challenge_start":
        return _envelope(_concat(
            _sine(330, 0.10), _silence(0.05), _sine(440, 0.12),
        ), attack=0.01, release=0.06)
    if event == "challenge_complete":
        return _envelope(_concat(
            _sine(440, 0.10), _sine(523, 0.10), _sine(659, 0.18),
        ), attack=0.01, release=0.08)
    if event == "challenge_fail":
        return _envelope(_concat(
            _sine(330, 0.12), _sine(262, 0.14),
        ), attack=0.01, release=0.07)
    if event == "level_up":
        return _envelope(_sweep(330, 1047, 0.40, amplitude=0.55, wave_fn="sine"), attack=0.02, release=0.10)
    if event == "toast_info":
        return _envelope(_sine(880, 0.09), attack=0.01, release=0.05)
    if event == "toast_warning":
        return _envelope(_concat(
            _sine(660, 0.08), _silence(0.03), _sine(660, 0.08),
        ), attack=0.01, release=0.04)
    if event == "countdown_tick":
        return _envelope(_sine(440, 0.06), attack=0.005, release=0.03)
    if event == "countdown_final":
        return _envelope(_concat(
            _sine(523, 0.07), _silence(0.02), _sine(587, 0.07),
            _silence(0.02), _sine(659, 0.07), _silence(0.02), _sine(880, 0.14),
        ), attack=0.01, release=0.06)
    if event == "personal_best":
        return _envelope(_concat(
            _sine(523, 0.09), _sine(659, 0.09), _sine(784, 0.09), _sine(1047, 0.20),
        ), attack=0.02, release=0.08)
    if event == "combo":
        return _envelope(_sine(784, 0.07), attack=0.005, release=0.03)
    return []


def _build_sci_fi(event: str) -> list[float]:
    def _warble(f_base: float, f_mod: float, rate: float, duration: float, amp: float = 0.7) -> list[float]:
        n = int(SAMPLE_RATE * duration)
        result = []
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = f_base + f_mod * math.sin(2 * math.pi * rate * t)
            result.append(amp * math.sin(2 * math.pi * freq * t))
        return result

    if event == "achievement_unlock":
        return _envelope(_sweep(300, 1200, 0.28, amplitude=0.65, wave_fn="sine"), attack=0.01, release=0.08)
    if event == "achievement_rare":
        s = _concat(_warble(800, 200, 6, 0.20), _sweep(400, 1600, 0.20))
        return _envelope(s, attack=0.02, release=0.08)
    if event == "challenge_start":
        return _envelope(_concat(
            _sweep(600, 200, 0.12), _silence(0.03), _sweep(200, 600, 0.12),
        ), attack=0.01, release=0.06)
    if event == "challenge_complete":
        return _envelope(_concat(
            _sweep(200, 1200, 0.20), _sweep(1200, 800, 0.12),
        ), attack=0.01, release=0.07)
    if event == "challenge_fail":
        return _envelope(_sweep(800, 100, 0.30, amplitude=0.6), attack=0.01, release=0.08)
    if event == "level_up":
        return _envelope(_concat(
            _sweep(200, 800, 0.18), _warble(800, 100, 8, 0.18),
        ), attack=0.01, release=0.08)
    if event == "toast_info":
        return _envelope(_warble(600, 50, 10, 0.10), attack=0.01, release=0.04)
    if event == "toast_warning":
        return _envelope(_concat(
            _warble(700, 100, 12, 0.09), _silence(0.03), _warble(700, 100, 12, 0.09),
        ), attack=0.01, release=0.04)
    if event == "countdown_tick":
        return _envelope(_sweep(500, 600, 0.05, amplitude=0.6), attack=0.002, release=0.02)
    if event == "countdown_final":
        return _envelope(_concat(
            _sweep(400, 600, 0.07), _silence(0.02),
            _sweep(500, 700, 0.07), _silence(0.02),
            _sweep(600, 900, 0.07), _silence(0.02),
            _sweep(700, 1200, 0.12),
        ), attack=0.005, release=0.06)
    if event == "personal_best":
        return _envelope(_concat(
            _sweep(300, 1200, 0.18), _warble(1200, 100, 10, 0.15),
        ), attack=0.01, release=0.08)
    if event == "combo":
        return _envelope(_sweep(600, 900, 0.07, amplitude=0.6), attack=0.003, release=0.03)
    return []


def _build_retro_8bit(event: str) -> list[float]:
    """NES/Gameboy style: pure square wave melodies."""
    def _sq_note(freq: float, dur: float) -> list[float]:
        return _envelope(_square(freq, dur, amplitude=0.55), attack=0.003, release=0.03)

    if event == "achievement_unlock":
        return _concat(_sq_note(523, 0.07), _sq_note(659, 0.07), _sq_note(784, 0.12))
    if event == "achievement_rare":
        return _concat(
            _sq_note(330, 0.06), _sq_note(392, 0.06), _sq_note(523, 0.06),
            _sq_note(659, 0.06), _sq_note(784, 0.06), _sq_note(1047, 0.15),
        )
    if event == "challenge_start":
        return _concat(
            _sq_note(262, 0.07), _silence(0.03), _sq_note(262, 0.07),
            _silence(0.03), _sq_note(392, 0.12),
        )
    if event == "challenge_complete":
        return _concat(
            _sq_note(392, 0.06), _sq_note(523, 0.06), _sq_note(659, 0.06), _sq_note(784, 0.14),
        )
    if event == "challenge_fail":
        return _concat(
            _sq_note(330, 0.09), _sq_note(294, 0.09), _sq_note(247, 0.13),
        )
    if event == "level_up":
        notes = [262, 294, 330, 349, 392, 440, 494, 523]
        return _concat(*[_sq_note(f, 0.05) for f in notes])
    if event == "toast_info":
        return _sq_note(880, 0.07)
    if event == "toast_warning":
        return _concat(_sq_note(740, 0.07), _silence(0.04), _sq_note(740, 0.07))
    if event == "countdown_tick":
        return _sq_note(523, 0.05)
    if event == "countdown_final":
        return _concat(
            _sq_note(523, 0.06), _silence(0.02), _sq_note(587, 0.06),
            _silence(0.02), _sq_note(659, 0.06), _silence(0.02), _sq_note(784, 0.12),
        )
    if event == "personal_best":
        return _concat(
            _sq_note(523, 0.06), _sq_note(659, 0.06),
            _sq_note(784, 0.06), _sq_note(1047, 0.06), _sq_note(1319, 0.14),
        )
    if event == "combo":
        return _sq_note(740, 0.05)
    return []


def _build_pinball_classic(event: str) -> list[float]:
    """Real pinball feel: bell dings, bumper pops."""
    def _bell(freq: float, duration: float, amp: float = 0.75) -> list[float]:
        """Bell-like tone: sine with exponential decay."""
        n = int(SAMPLE_RATE * duration)
        return [amp * math.sin(2 * math.pi * freq * i / SAMPLE_RATE) *
                math.exp(-4.0 * i / n) for i in range(n)]

    def _pop(freq: float = 300, amp: float = 0.7) -> list[float]:
        """Short bumper pop: quick burst."""
        return _envelope(_square(freq, 0.04, amp), attack=0.002, release=0.015)

    if event == "achievement_unlock":
        return _concat(_bell(880, 0.30), _bell(1108, 0.25), _bell(1320, 0.30))
    if event == "achievement_rare":
        return _concat(
            _bell(660, 0.20), _bell(784, 0.20), _bell(988, 0.20),
            _bell(1320, 0.35), _bell(1760, 0.35),
        )
    if event == "challenge_start":
        return _concat(_pop(440), _silence(0.05), _pop(440), _silence(0.05), _bell(660, 0.20))
    if event == "challenge_complete":
        return _concat(
            _bell(660, 0.18), _bell(784, 0.18), _bell(988, 0.18), _bell(1320, 0.30),
        )
    if event == "challenge_fail":
        return _concat(_bell(330, 0.25), _bell(220, 0.30))
    if event == "level_up":
        return _concat(
            _pop(330), _pop(392), _pop(494),
            _bell(784, 0.25), _bell(988, 0.30), _bell(1320, 0.35),
        )
    if event == "toast_info":
        return _bell(1047, 0.18)
    if event == "toast_warning":
        return _concat(_bell(659, 0.14), _silence(0.05), _bell(659, 0.14))
    if event == "countdown_tick":
        return _pop(880, 0.5)
    if event == "countdown_final":
        return _concat(
            _pop(523), _silence(0.03), _pop(587), _silence(0.03),
            _pop(659), _silence(0.03), _bell(880, 0.20),
        )
    if event == "personal_best":
        return _concat(
            _pop(392), _pop(494), _pop(587),
            _bell(784, 0.22), _bell(988, 0.22), _bell(1320, 0.30), _bell(1760, 0.35),
        )
    if event == "combo":
        return _pop(659)
    return []


_PACK_BUILDERS = {
    "arcade":          _build_arcade,
    "subtle":          _build_subtle,
    "sci_fi":          _build_sci_fi,
    "retro_8bit":      _build_retro_8bit,
    "pinball_classic": _build_pinball_classic,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _volume_scale(cfg_volume: int) -> float:
    """Convert 0-100 integer volume to 0.0-1.0 amplitude scale."""
    return max(0.0, min(1.0, int(cfg_volume or DEFAULT_VOLUME) / 100.0))


def _get_wav(pack_id: str, event: str, volume: float = 1.0) -> bytes | None:
    """Return cached WAV bytes for (pack, event), building if needed."""
    key = (pack_id, event)
    if key not in _cache:
        builder = _PACK_BUILDERS.get(pack_id)
        if builder is None:
            return None
        samples = builder(event)
        if not samples:
            return None
        _cache[key] = _make_wav(samples, volume=1.0)  # cache at full volume
    raw_wav = _cache.get(key)
    if raw_wav is None:
        return None
    if volume >= 0.99:
        return raw_wav
    # Re-scale volume on the fly (cheap decode/re-encode of just the PCM chunk)
    return _rescale_wav(raw_wav, volume)


def _rescale_wav(wav_bytes: bytes, scale: float) -> bytes:
    """Return a new WAV with all PCM samples multiplied by scale."""
    try:
        buf_in = io.BytesIO(wav_bytes)
        with wave.open(buf_in, "rb") as wf:
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            fr = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())
        if sw != 2:
            return wav_bytes
        n = len(pcm) // 2
        samples = struct.unpack(f"<{n}h", pcm)
        scaled = bytes(struct.pack(f"<{n}h", *[int(max(-32768, min(32767, s * scale))) for s in samples]))
        buf_out = io.BytesIO()
        with wave.open(buf_out, "wb") as wf:
            wf.setnchannels(nch)
            wf.setsampwidth(sw)
            wf.setframerate(fr)
            wf.writeframes(scaled)
        return buf_out.getvalue()
    except Exception:
        return wav_bytes


def _play_raw(wav_bytes: bytes) -> None:
    """Play WAV bytes asynchronously via a daemon thread using winsound (Windows) or silent fallback."""
    import threading

    def _worker(data: bytes) -> None:
        try:
            import winsound
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            pass

    threading.Thread(target=_worker, args=(wav_bytes,), daemon=True).start()


def _resolve_pack_id(ov: dict) -> str:
    """Normalize and resolve a pack ID from OVERLAY config, falling back to 'arcade'."""
    pack_id = str(ov.get("sound_pack", "arcade") or "arcade").lower().replace(" ", "_").replace("-", "_")
    return pack_id if pack_id in _PACK_BUILDERS else "arcade"


def play_sound(cfg, event_name: str) -> None:
    """Play sound for event if sound is enabled and event is enabled in config."""
    try:
        ov = getattr(cfg, "OVERLAY", {}) or {}
        if not ov.get("sound_enabled", True):
            return
        events_cfg = ov.get("sound_events") or {}
        if not events_cfg.get(event_name, True):
            return
        pack_id = _resolve_pack_id(ov)
        vol = _volume_scale(ov.get("sound_volume", DEFAULT_VOLUME))
        wav = _get_wav(pack_id, event_name, vol)
        if wav:
            _play_raw(wav)
    except Exception:
        pass


def play_sound_preview(cfg, event_name: str) -> None:
    """Play sound preview regardless of enabled state (for Test buttons)."""
    try:
        ov = getattr(cfg, "OVERLAY", {}) or {}
        pack_id = _resolve_pack_id(ov)
        vol = _volume_scale(ov.get("sound_volume", DEFAULT_VOLUME))
        wav = _get_wav(pack_id, event_name, vol)
        if wav:
            _play_raw(wav)
    except Exception:
        pass
