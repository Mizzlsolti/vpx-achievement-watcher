"""
Sound engine for VPX Achievement Watcher.
Generates WAV audio in memory (no external files, no pip dependencies).
Playback via winsound on Windows; silent fallback on other platforms.
"""
from __future__ import annotations

import io
import math
import struct
import threading
import wave

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22050   # Hz – good enough for short SFX, lower CPU cost
DEFAULT_VOLUME = 70   # 0-100

SOUND_PACKS = {
    "arcade":          "Arcade",
    "subtle":          "Subtle",
    "sci_fi":          "Sci-Fi",
    "retro_8bit":      "Retro 8-Bit",
    "pinball_classic": "Pinball Classic",
    "galactic_battle": "Galactic Battle",
    "stage_magic":     "Stage Magic",
    "neon_grid":       "Neon Grid",
    "martian_assault": "Martian Assault",
    "carnival_show":   "Carnival Show",
    "medieval_quest":  "Medieval Quest",
    "haunted_manor":   "Haunted Manor",
    "deep_ocean":      "Deep Ocean",
    "jukebox":         "Jukebox",
    "showtime":        "Showtime",
    "chrome_steel":    "Chrome Steel",
    "treasure_hunt":   "Treasure Hunt",
    "turbo_racer":     "Turbo Racer",
    "neon_lounge":     "Neon Lounge",
    "voltage":         "Voltage",
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


# ---------------------------------------------------------------------------
# Additional effect helpers for new sound packs
# ---------------------------------------------------------------------------

def _tremolo(samples: list[float], rate: float = 5.0, depth: float = 0.5) -> list[float]:
    """Amplitude modulation (tremolo): varies volume at *rate* Hz by *depth* factor."""
    n = len(samples)
    return [
        s * (1.0 - depth * 0.5 + depth * 0.5 * math.sin(2 * math.pi * rate * i / SAMPLE_RATE))
        for i, s in enumerate(samples)
    ]


def _vibrato(freq: float, duration: float, depth: float = 10.0,
             rate: float = 6.0, amplitude: float = 0.7) -> list[float]:
    """Frequency modulation (vibrato): sine wave with oscillating pitch."""
    n = int(SAMPLE_RATE * duration)
    result = []
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        f = freq + depth * math.sin(2 * math.pi * rate * t)
        phase += 2 * math.pi * f / SAMPLE_RATE
        result.append(amplitude * math.sin(phase))
    return result


def _noise(duration: float, amplitude: float = 0.5) -> list[float]:
    """White noise burst."""
    import random
    n = int(SAMPLE_RATE * duration)
    return [amplitude * (random.random() * 2.0 - 1.0) for _ in range(n)]


def _ring(freq: float, duration: float, decay: float = 5.0,
          amplitude: float = 0.75) -> list[float]:
    """Bell/metallic ring: sine with exponential decay (more controllable than _bell)."""
    n = int(SAMPLE_RATE * duration)
    return [
        amplitude * math.sin(2 * math.pi * freq * i / SAMPLE_RATE) *
        math.exp(-decay * i / n)
        for i in range(n)
    ]


def _crackle(duration: float, density: float = 0.05) -> list[float]:
    """Random pop/crackle texture: sparse noise impulses."""
    import random
    n = int(SAMPLE_RATE * duration)
    out = [0.0] * n
    for i in range(n):
        if random.random() < density:
            out[i] = (random.random() * 2.0 - 1.0) * 0.8
    return out


# ---------------------------------------------------------------------------
# New sound pack definitions (packs 6-20)
# ---------------------------------------------------------------------------

def _build_galactic_battle(event: str) -> list[float]:
    """Star Wars VPX – Imperial fanfares, laser zaps, epic sweeps."""
    def _laser(f_start: float, f_end: float, dur: float) -> list[float]:
        return _envelope(_sweep(f_start, f_end, dur, amplitude=0.65, wave_fn="sine"),
                         attack=0.005, release=0.04)

    def _fanfare_note(freq: float, dur: float) -> list[float]:
        return _envelope(_mix(_square(freq, dur, 0.45), _sine(freq * 2, dur, 0.25)),
                         attack=0.01, release=0.05)

    if event == "achievement_unlock":
        return _concat(
            _fanfare_note(392, 0.10), _fanfare_note(523, 0.10),
            _fanfare_note(659, 0.10), _fanfare_note(784, 0.20),
        )
    if event == "achievement_rare":
        return _envelope(_concat(
            _fanfare_note(262, 0.07), _fanfare_note(330, 0.07),
            _fanfare_note(392, 0.07), _fanfare_note(523, 0.07),
            _fanfare_note(659, 0.07), _fanfare_note(784, 0.07), _fanfare_note(1047, 0.20),
        ), release=0.10)
    if event == "challenge_start":
        return _concat(
            _laser(600, 200, 0.10), _silence(0.03), _laser(200, 800, 0.12),
        )
    if event == "challenge_complete":
        return _concat(
            _fanfare_note(392, 0.08), _fanfare_note(494, 0.08),
            _fanfare_note(587, 0.08), _fanfare_note(784, 0.18),
        )
    if event == "challenge_fail":
        return _envelope(_concat(
            _sine(440, 0.08), _sine(392, 0.08), _sine(330, 0.08),
            _sine(262, 0.12), _sine(220, 0.16),
        ), release=0.08)
    if event == "level_up":
        bass = _sweep(80, 200, 0.30, amplitude=0.55)
        fanfare = _concat(
            _silence(0.05), _fanfare_note(523, 0.07),
            _fanfare_note(659, 0.07), _fanfare_note(784, 0.14),
        )
        return _mix(bass, fanfare)
    if event == "toast_info":
        return _laser(800, 1200, 0.08)
    if event == "toast_warning":
        return _concat(_laser(1000, 500, 0.07), _silence(0.03), _laser(1000, 500, 0.07))
    if event == "countdown_tick":
        return _envelope(_sine(600, 0.05, 0.6), attack=0.002, release=0.02)
    if event == "countdown_final":
        return _concat(
            _laser(400, 700, 0.06), _silence(0.02),
            _laser(500, 800, 0.06), _silence(0.02),
            _laser(600, 1000, 0.06), _silence(0.02),
            _fanfare_note(784, 0.16),
        )
    if event == "personal_best":
        bass = _sweep(60, 160, 0.25, amplitude=0.50)
        top = _concat(
            _fanfare_note(523, 0.07), _fanfare_note(659, 0.07),
            _fanfare_note(784, 0.07), _fanfare_note(1047, 0.18),
        )
        return _mix(bass, top)
    if event == "combo":
        return _laser(800, 1400, 0.07)
    return []


def _build_stage_magic(event: str) -> list[float]:
    """Theatre of Magic VPX – Mysterious bells, magic glissandos, shimmer."""
    def _bell_tone(freq: float, dur: float) -> list[float]:
        return _ring(freq, dur, decay=4.0, amplitude=0.70)

    def _shimmer(freq: float, dur: float) -> list[float]:
        return _envelope(_vibrato(freq, dur, depth=20.0, rate=12.0, amplitude=0.60),
                         attack=0.02, release=0.06)

    if event == "achievement_unlock":
        return _concat(_bell_tone(523, 0.25), _bell_tone(659, 0.25), _bell_tone(784, 0.35))
    if event == "achievement_rare":
        return _concat(
            _bell_tone(392, 0.18), _bell_tone(523, 0.18), _bell_tone(659, 0.18),
            _bell_tone(784, 0.22), _bell_tone(1047, 0.35),
        )
    if event == "challenge_start":
        return _concat(_shimmer(400, 0.15), _silence(0.03), _shimmer(600, 0.15))
    if event == "challenge_complete":
        return _concat(
            _bell_tone(523, 0.15), _bell_tone(659, 0.15),
            _bell_tone(784, 0.15), _bell_tone(1047, 0.30),
        )
    if event == "challenge_fail":
        return _envelope(_concat(
            _bell_tone(440, 0.20), _bell_tone(330, 0.25),
        ), release=0.10)
    if event == "level_up":
        gliss = _sweep(300, 1200, 0.35, amplitude=0.55, wave_fn="sine")
        return _envelope(_mix(gliss, _shimmer(600, 0.35)), release=0.10)
    if event == "toast_info":
        return _bell_tone(1047, 0.18)
    if event == "toast_warning":
        return _concat(_bell_tone(740, 0.14), _silence(0.04), _bell_tone(740, 0.14))
    if event == "countdown_tick":
        return _envelope(_sine(1200, 0.05, 0.5), attack=0.002, release=0.025)
    if event == "countdown_final":
        return _concat(
            _bell_tone(659, 0.10), _silence(0.02), _bell_tone(784, 0.10),
            _silence(0.02), _bell_tone(988, 0.10), _silence(0.02), _bell_tone(1319, 0.28),
        )
    if event == "personal_best":
        return _concat(
            _bell_tone(523, 0.15), _bell_tone(659, 0.15), _bell_tone(784, 0.15),
            _bell_tone(988, 0.18), _bell_tone(1319, 0.35),
        )
    if event == "combo":
        return _bell_tone(1319, 0.14)
    return []


def _build_neon_grid(event: str) -> list[float]:
    """Tron VPX – Digital pulses, grid hum, synthetic arpeggios."""
    def _pulse(freq: float, dur: float) -> list[float]:
        n = int(SAMPLE_RATE * dur)
        result = []
        for i in range(n):
            phase = (freq * i / SAMPLE_RATE) % 1.0
            result.append(0.55 if phase < 0.25 else -0.55)
        return _envelope(result, attack=0.002, release=0.015)

    if event == "achievement_unlock":
        return _concat(
            _pulse(440, 0.06), _pulse(554, 0.06), _pulse(659, 0.06), _pulse(880, 0.12),
        )
    if event == "achievement_rare":
        freqs = [330, 392, 494, 587, 740, 880, 1109]
        return _concat(*[_pulse(f, 0.05) for f in freqs], _pulse(1318, 0.14))
    if event == "challenge_start":
        return _concat(
            _pulse(220, 0.06), _silence(0.03), _pulse(220, 0.06), _silence(0.03), _pulse(330, 0.10),
        )
    if event == "challenge_complete":
        freqs = [330, 440, 554, 659]
        return _concat(*[_pulse(f, 0.07) for f in freqs], _pulse(880, 0.14))
    if event == "challenge_fail":
        return _concat(_pulse(440, 0.09), _pulse(330, 0.09), _pulse(220, 0.14))
    if event == "level_up":
        freqs = [220, 262, 330, 392, 494, 587, 740, 880]
        return _concat(*[_pulse(f, 0.05) for f in freqs])
    if event == "toast_info":
        return _pulse(880, 0.07)
    if event == "toast_warning":
        return _concat(_pulse(659, 0.06), _silence(0.03), _pulse(659, 0.06))
    if event == "countdown_tick":
        return _pulse(440, 0.04)
    if event == "countdown_final":
        return _concat(
            _pulse(494, 0.05), _silence(0.02), _pulse(587, 0.05),
            _silence(0.02), _pulse(659, 0.05), _silence(0.02), _pulse(880, 0.12),
        )
    if event == "personal_best":
        freqs = [494, 587, 740, 880, 1109]
        return _concat(*[_pulse(f, 0.06) for f in freqs], _pulse(1318, 0.14))
    if event == "combo":
        return _pulse(740, 0.05)
    return []


def _build_martian_assault(event: str) -> list[float]:
    """Attack from Mars VPX – Alien warble, explosion bursts, sirens."""
    def _alien_warble(f_base: float, f_mod: float, rate: float, dur: float) -> list[float]:
        n = int(SAMPLE_RATE * dur)
        result = []
        for i in range(n):
            t = i / SAMPLE_RATE
            freq = f_base + f_mod * math.sin(2 * math.pi * rate * t)
            result.append(0.65 * math.sin(2 * math.pi * freq * t))
        return _envelope(result, attack=0.01, release=0.05)

    def _explosion(dur: float = 0.12) -> list[float]:
        noise = _noise(dur, amplitude=0.7)
        sweep = _sweep(200, 40, dur, amplitude=0.5)
        return _envelope(_mix(noise, sweep), attack=0.002, release=0.06)

    def _siren(f_low: float, f_high: float, dur: float) -> list[float]:
        return _envelope(_sweep(f_low, f_high, dur / 2, amplitude=0.60) +
                         _sweep(f_high, f_low, dur / 2, amplitude=0.60),
                         attack=0.01, release=0.04)

    if event == "achievement_unlock":
        return _concat(_alien_warble(400, 150, 8, 0.15), _explosion(0.08), _alien_warble(600, 200, 10, 0.18))
    if event == "achievement_rare":
        return _concat(
            _siren(300, 900, 0.20), _explosion(0.10), _alien_warble(600, 250, 12, 0.20),
        )
    if event == "challenge_start":
        return _concat(_siren(400, 800, 0.16), _silence(0.03), _siren(400, 800, 0.16))
    if event == "challenge_complete":
        return _concat(_explosion(0.07), _alien_warble(500, 200, 8, 0.18))
    if event == "challenge_fail":
        return _concat(_explosion(0.14), _sweep(600, 80, 0.20, amplitude=0.55))
    if event == "level_up":
        return _concat(_siren(200, 1000, 0.30), _alien_warble(500, 200, 10, 0.18))
    if event == "toast_info":
        return _alien_warble(500, 80, 12, 0.10)
    if event == "toast_warning":
        return _concat(_siren(600, 1000, 0.12), _silence(0.03), _siren(600, 1000, 0.12))
    if event == "countdown_tick":
        return _envelope(_noise(0.04, 0.5), attack=0.001, release=0.02)
    if event == "countdown_final":
        return _concat(_siren(300, 900, 0.08), _silence(0.02),
                       _siren(300, 900, 0.08), _silence(0.02), _explosion(0.12))
    if event == "personal_best":
        return _concat(_alien_warble(400, 200, 10, 0.15), _siren(400, 1200, 0.25),
                       _explosion(0.10))
    if event == "combo":
        return _envelope(_noise(0.06, 0.6), attack=0.002, release=0.025)
    return []


def _build_carnival_show(event: str) -> list[float]:
    """Cirqus Voltaire/Funhouse VPX – Circus organ, fairground jingles."""
    def _organ(freq: float, dur: float) -> list[float]:
        sq = _square(freq, dur, amplitude=0.40)
        sq2 = _square(freq * 2, dur, amplitude=0.20)
        sq3 = _square(freq * 3, dur, amplitude=0.10)
        return _envelope(_mix(_mix(sq, sq2), sq3), attack=0.01, release=0.04)

    if event == "achievement_unlock":
        return _concat(
            _organ(523, 0.08), _organ(659, 0.08), _organ(784, 0.08), _organ(1047, 0.16),
        )
    if event == "achievement_rare":
        melody = [523, 587, 659, 698, 784, 880, 988, 1047]
        return _concat(*[_organ(f, 0.07) for f in melody])
    if event == "challenge_start":
        return _concat(_organ(523, 0.07), _organ(523, 0.07), _organ(659, 0.12))
    if event == "challenge_complete":
        return _concat(
            _organ(523, 0.07), _organ(659, 0.07), _organ(784, 0.07), _organ(1047, 0.16),
        )
    if event == "challenge_fail":
        return _concat(_organ(440, 0.08), _organ(392, 0.08), _organ(330, 0.12))
    if event == "level_up":
        melody = [262, 294, 330, 349, 392, 440, 494, 523]
        return _concat(*[_organ(f, 0.06) for f in melody])
    if event == "toast_info":
        return _organ(880, 0.09)
    if event == "toast_warning":
        return _concat(_organ(659, 0.07), _silence(0.03), _organ(659, 0.07))
    if event == "countdown_tick":
        return _organ(523, 0.05)
    if event == "countdown_final":
        return _concat(
            _organ(523, 0.06), _silence(0.02), _organ(659, 0.06),
            _silence(0.02), _organ(784, 0.06), _silence(0.02), _organ(1047, 0.14),
        )
    if event == "personal_best":
        melody = [523, 659, 784, 988, 1047]
        return _concat(*[_organ(f, 0.08) for f in melody])
    if event == "combo":
        return _organ(784, 0.06)
    return []


def _build_medieval_quest(event: str) -> list[float]:
    """Medieval Madness VPX – Trumpet fanfares, sword clang, castle bells."""
    def _trumpet(freq: float, dur: float) -> list[float]:
        sq = _square(freq, dur, amplitude=0.50)
        sq2 = _square(freq * 2, dur, amplitude=0.15)
        return _envelope(_mix(sq, sq2), attack=0.02, release=0.05)

    def _clang(dur: float = 0.15) -> list[float]:
        n = _noise(dur * 0.02, 0.7)
        r = _ring(1200, dur, decay=6.0, amplitude=0.65)
        return _mix(n, r)

    def _castle_bell(freq: float, dur: float) -> list[float]:
        return _ring(freq, dur, decay=3.5, amplitude=0.70)

    if event == "achievement_unlock":
        return _concat(
            _trumpet(392, 0.10), _trumpet(494, 0.10),
            _trumpet(587, 0.10), _trumpet(784, 0.20),
        )
    if event == "achievement_rare":
        return _concat(
            _trumpet(330, 0.08), _trumpet(392, 0.08), _trumpet(494, 0.08),
            _trumpet(587, 0.08), _trumpet(784, 0.08), _clang(0.10), _castle_bell(880, 0.30),
        )
    if event == "challenge_start":
        return _concat(_trumpet(330, 0.10), _silence(0.04), _trumpet(330, 0.10),
                       _silence(0.04), _trumpet(494, 0.14))
    if event == "challenge_complete":
        return _concat(
            _trumpet(392, 0.09), _trumpet(494, 0.09),
            _trumpet(587, 0.09), _castle_bell(784, 0.28),
        )
    if event == "challenge_fail":
        return _concat(_clang(0.12), _trumpet(330, 0.10), _trumpet(262, 0.14))
    if event == "level_up":
        return _concat(
            _trumpet(262, 0.07), _trumpet(330, 0.07), _trumpet(392, 0.07),
            _trumpet(494, 0.07), _castle_bell(784, 0.20), _castle_bell(988, 0.25),
        )
    if event == "toast_info":
        return _castle_bell(1047, 0.18)
    if event == "toast_warning":
        return _concat(_castle_bell(659, 0.14), _silence(0.05), _castle_bell(659, 0.14))
    if event == "countdown_tick":
        return _envelope(_sine(880, 0.05, 0.55), attack=0.002, release=0.02)
    if event == "countdown_final":
        return _concat(
            _trumpet(494, 0.06), _silence(0.02), _trumpet(587, 0.06),
            _silence(0.02), _trumpet(659, 0.06), _silence(0.02), _castle_bell(880, 0.22),
        )
    if event == "personal_best":
        return _concat(
            _trumpet(392, 0.08), _trumpet(494, 0.08), _trumpet(587, 0.08),
            _clang(0.08), _castle_bell(784, 0.22), _castle_bell(1047, 0.28),
        )
    if event == "combo":
        return _clang(0.10)
    return []


def _build_haunted_manor(event: str) -> list[float]:
    """Scared Stiff/Creature VPX – Spooky organ, deep drones, theremin."""
    def _drone(freq: float, dur: float) -> list[float]:
        sq = _square(freq, dur, amplitude=0.35)
        sq2 = _square(freq * 1.5, dur, amplitude=0.15)
        return _envelope(_mix(sq, sq2), attack=0.08, release=0.10)

    def _theremin(freq: float, dur: float) -> list[float]:
        return _envelope(_vibrato(freq, dur, depth=15.0, rate=4.0, amplitude=0.55),
                         attack=0.08, release=0.12)

    def _spooky_bell(freq: float, dur: float) -> list[float]:
        return _ring(freq, dur, decay=2.5, amplitude=0.60)

    if event == "achievement_unlock":
        drone = _drone(80, 0.50)
        melody = _concat(_spooky_bell(440, 0.20), _silence(0.05), _spooky_bell(554, 0.25))
        return _mix(drone, _concat(_silence(0.05), melody))
    if event == "achievement_rare":
        return _concat(
            _theremin(200, 0.20), _spooky_bell(330, 0.18),
            _theremin(300, 0.20), _spooky_bell(440, 0.22), _theremin(440, 0.25),
        )
    if event == "challenge_start":
        return _concat(_drone(60, 0.25), _silence(0.05), _theremin(300, 0.20))
    if event == "challenge_complete":
        return _concat(
            _spooky_bell(330, 0.18), _spooky_bell(415, 0.18),
            _spooky_bell(554, 0.20), _theremin(440, 0.28),
        )
    if event == "challenge_fail":
        return _concat(_drone(55, 0.35), _theremin(150, 0.30))
    if event == "level_up":
        base = _drone(70, 0.45)
        bells = _concat(
            _silence(0.10), _spooky_bell(330, 0.15), _spooky_bell(415, 0.15),
            _spooky_bell(554, 0.18),
        )
        return _mix(base, bells)
    if event == "toast_info":
        return _spooky_bell(659, 0.20)
    if event == "toast_warning":
        return _envelope(_theremin(300, 0.20), release=0.08)
    if event == "countdown_tick":
        return _envelope(_sine(220, 0.06, 0.45), attack=0.003, release=0.03)
    if event == "countdown_final":
        return _concat(
            _spooky_bell(330, 0.10), _silence(0.03), _spooky_bell(415, 0.10),
            _silence(0.03), _spooky_bell(554, 0.10), _silence(0.03), _theremin(440, 0.28),
        )
    if event == "personal_best":
        return _concat(
            _drone(80, 0.30), _theremin(400, 0.22), _spooky_bell(659, 0.28),
        )
    if event == "combo":
        return _spooky_bell(440, 0.14)
    return []


def _build_deep_ocean(event: str) -> list[float]:
    """Fish Tales VPX – Underwater bubbles, wave sweeps, sonar pings."""
    import random

    def _bubble() -> list[float]:
        dur = 0.04
        f = 600 + 400 * random.random()
        return _envelope(_sine(f, dur, 0.40), attack=0.001, release=0.025)

    def _bubbles(count: int, gap: float = 0.02) -> list[float]:
        result: list[float] = []
        for _ in range(count):
            result.extend(_bubble())
            result.extend(_silence(gap))
        return result

    def _sonar(freq: float = 900) -> list[float]:
        return _ring(freq, 0.30, decay=3.0, amplitude=0.60)

    def _wave_sweep(dur: float) -> list[float]:
        return _envelope(_sweep(80, 300, dur, amplitude=0.45, wave_fn="sine"),
                         attack=0.10, release=0.10)

    if event == "achievement_unlock":
        return _concat(_sonar(880), _silence(0.06), _bubbles(4, 0.03), _sonar(1100))
    if event == "achievement_rare":
        return _concat(_wave_sweep(0.20), _bubbles(6, 0.025), _sonar(880), _sonar(1100))
    if event == "challenge_start":
        return _concat(_wave_sweep(0.15), _silence(0.04), _sonar(700))
    if event == "challenge_complete":
        return _concat(_sonar(659), _silence(0.05), _sonar(784), _silence(0.05), _sonar(988))
    if event == "challenge_fail":
        return _envelope(_sweep(400, 80, 0.30, amplitude=0.50), attack=0.02, release=0.10)
    if event == "level_up":
        return _concat(_wave_sweep(0.25), _bubbles(5, 0.025), _sonar(880))
    if event == "toast_info":
        return _sonar(1047)
    if event == "toast_warning":
        return _concat(_sonar(659), _silence(0.06), _sonar(659))
    if event == "countdown_tick":
        return _envelope(_sine(600, 0.05, 0.45), attack=0.002, release=0.025)
    if event == "countdown_final":
        return _concat(
            _sonar(523), _silence(0.03), _sonar(659),
            _silence(0.03), _sonar(784), _silence(0.03), _sonar(1047),
        )
    if event == "personal_best":
        return _concat(_wave_sweep(0.20), _bubbles(4, 0.02), _sonar(880), _sonar(1319))
    if event == "combo":
        return _bubbles(3, 0.025)
    return []


def _build_jukebox(event: str) -> list[float]:
    """PinUP Popper – Vinyl crackle feel, jukebox coin-drop, retro radio jingles."""
    def _warm_note(freq: float, dur: float) -> list[float]:
        s = _sine(freq, dur, amplitude=0.60)
        s2 = _sine(freq * 1.01, dur, amplitude=0.15)
        return _envelope(_mix(s, s2), attack=0.02, release=0.06)

    def _coin_click() -> list[float]:
        return _envelope(_mix(_noise(0.015, 0.6), _sine(800, 0.015, 0.4)),
                         attack=0.001, release=0.010)

    if event == "achievement_unlock":
        return _concat(_coin_click(), _silence(0.04),
                       _warm_note(523, 0.10), _warm_note(659, 0.10), _warm_note(784, 0.20))
    if event == "achievement_rare":
        return _concat(
            _coin_click(), _silence(0.03),
            _warm_note(392, 0.09), _warm_note(523, 0.09), _warm_note(659, 0.09),
            _warm_note(784, 0.09), _warm_note(1047, 0.22),
        )
    if event == "challenge_start":
        return _concat(_coin_click(), _silence(0.05),
                       _warm_note(330, 0.10), _silence(0.04), _warm_note(440, 0.12))
    if event == "challenge_complete":
        return _concat(
            _warm_note(440, 0.09), _warm_note(523, 0.09),
            _warm_note(659, 0.09), _warm_note(784, 0.20),
        )
    if event == "challenge_fail":
        return _envelope(_concat(
            _warm_note(330, 0.12), _warm_note(262, 0.14),
        ), release=0.08)
    if event == "level_up":
        return _concat(_coin_click(), _silence(0.02),
                       *[_warm_note(f, 0.06) for f in [262, 330, 392, 494, 523, 659]])
    if event == "toast_info":
        return _warm_note(880, 0.10)
    if event == "toast_warning":
        return _concat(_warm_note(659, 0.08), _silence(0.03), _warm_note(659, 0.08))
    if event == "countdown_tick":
        return _coin_click()
    if event == "countdown_final":
        return _concat(
            _coin_click(), _silence(0.02), _coin_click(), _silence(0.02),
            _coin_click(), _silence(0.03), _warm_note(784, 0.16),
        )
    if event == "personal_best":
        return _concat(
            _coin_click(), _silence(0.02),
            _warm_note(523, 0.08), _warm_note(659, 0.08),
            _warm_note(784, 0.08), _warm_note(1047, 0.22),
        )
    if event == "combo":
        return _warm_note(784, 0.07)
    return []


def _build_showtime(event: str) -> list[float]:
    """PinUP Popper – Applause-like bursts, drumrolls, spotlight dings."""
    def _drumroll(dur: float, density: float = 0.20) -> list[float]:
        return _envelope(_noise(dur, amplitude=0.55), attack=0.01, release=0.06)

    def _snare() -> list[float]:
        return _envelope(_mix(_noise(0.04, 0.65), _sine(200, 0.04, 0.30)),
                         attack=0.001, release=0.025)

    def _ding(freq: float, dur: float = 0.22) -> list[float]:
        return _ring(freq, dur, decay=4.0, amplitude=0.70)

    if event == "achievement_unlock":
        roll = _drumroll(0.12)
        return _concat(roll, _silence(0.03), _ding(880), _ding(1047))
    if event == "achievement_rare":
        return _concat(_drumroll(0.18), _silence(0.03),
                       _ding(659), _ding(784), _ding(988), _ding(1319))
    if event == "challenge_start":
        return _concat(_snare(), _silence(0.04), _snare(), _silence(0.04),
                       _snare(), _silence(0.02), _ding(659))
    if event == "challenge_complete":
        return _concat(_drumroll(0.14), _silence(0.03), _ding(784), _ding(1047))
    if event == "challenge_fail":
        return _concat(_snare(), _silence(0.05), _sweep(600, 100, 0.20, amplitude=0.45))
    if event == "level_up":
        return _concat(_drumroll(0.20), _silence(0.03),
                       _ding(523), _ding(659), _ding(784), _ding(1047))
    if event == "toast_info":
        return _ding(1047)
    if event == "toast_warning":
        return _concat(_snare(), _silence(0.04), _snare())
    if event == "countdown_tick":
        return _snare()
    if event == "countdown_final":
        return _concat(
            _snare(), _silence(0.02), _snare(), _silence(0.02),
            _snare(), _silence(0.02), _snare(), _silence(0.02), _ding(1047),
        )
    if event == "personal_best":
        return _concat(_drumroll(0.16), _silence(0.02),
                       _ding(659), _ding(784), _ding(988), _ding(1319))
    if event == "combo":
        return _snare()
    return []


def _build_chrome_steel(event: str) -> list[float]:
    """Terminator/Demolition Man VPX – Metallic impacts, industrial bass."""
    def _metal_hit(dur: float = 0.10) -> list[float]:
        noise_part = _noise(dur * 0.05, 0.70)
        ring_part = _ring(1800, dur, decay=8.0, amplitude=0.55)
        return _mix(noise_part + _silence(dur - dur * 0.05), ring_part)

    def _bass_thud(dur: float = 0.12) -> list[float]:
        return _envelope(
            _mix(_square(60, dur, amplitude=0.65), _noise(dur * 0.03, 0.50)),
            attack=0.002, release=0.06,
        )

    if event == "achievement_unlock":
        return _concat(_bass_thud(), _metal_hit(), _silence(0.03), _metal_hit(0.15))
    if event == "achievement_rare":
        return _concat(
            _bass_thud(), _metal_hit(), _silence(0.02),
            _bass_thud(), _metal_hit(), _silence(0.02),
            _ring(1600, 0.28, decay=5.0, amplitude=0.65),
        )
    if event == "challenge_start":
        return _concat(_bass_thud(0.10), _silence(0.04), _bass_thud(0.10),
                       _silence(0.04), _metal_hit(0.12))
    if event == "challenge_complete":
        return _concat(_bass_thud(), _metal_hit(), _bass_thud(), _ring(1400, 0.25, decay=4.0))
    if event == "challenge_fail":
        return _concat(_bass_thud(0.16), _sweep(300, 50, 0.20, amplitude=0.55))
    if event == "level_up":
        return _concat(
            _bass_thud(0.08), _bass_thud(0.08), _bass_thud(0.08), _metal_hit(),
            _ring(1600, 0.25, decay=4.5, amplitude=0.65),
        )
    if event == "toast_info":
        return _metal_hit(0.08)
    if event == "toast_warning":
        return _concat(_metal_hit(0.07), _silence(0.04), _metal_hit(0.07))
    if event == "countdown_tick":
        return _envelope(_mix(_noise(0.02, 0.50), _sine(400, 0.02, 0.30)),
                         attack=0.001, release=0.01)
    if event == "countdown_final":
        return _concat(
            _metal_hit(0.05), _silence(0.02), _metal_hit(0.05), _silence(0.02),
            _metal_hit(0.05), _silence(0.02), _bass_thud(0.14),
        )
    if event == "personal_best":
        return _concat(
            _bass_thud(), _metal_hit(), _bass_thud(), _metal_hit(),
            _ring(1800, 0.30, decay=5.0, amplitude=0.70),
        )
    if event == "combo":
        return _metal_hit(0.07)
    return []


def _build_treasure_hunt(event: str) -> list[float]:
    """Pirates of the Caribbean VPX – Adventure fanfares, ship bell, compass tick."""
    def _adventure_note(freq: float, dur: float) -> list[float]:
        sq = _square(freq, dur, amplitude=0.45)
        sn = _sine(freq * 1.5, dur, amplitude=0.20)
        return _envelope(_mix(sq, sn), attack=0.015, release=0.05)

    def _ship_bell(freq: float, dur: float) -> list[float]:
        return _ring(freq, dur, decay=2.5, amplitude=0.72)

    def _compass_tick() -> list[float]:
        return _envelope(_mix(_noise(0.012, 0.55), _sine(1200, 0.012, 0.40)),
                         attack=0.001, release=0.008)

    if event == "achievement_unlock":
        return _concat(
            _adventure_note(392, 0.09), _adventure_note(494, 0.09),
            _adventure_note(587, 0.09), _ship_bell(784, 0.32),
        )
    if event == "achievement_rare":
        return _concat(
            _adventure_note(330, 0.08), _adventure_note(392, 0.08),
            _adventure_note(494, 0.08), _adventure_note(587, 0.08),
            _ship_bell(784, 0.25), _ship_bell(988, 0.30),
        )
    if event == "challenge_start":
        return _concat(_adventure_note(330, 0.10), _silence(0.04),
                       _adventure_note(330, 0.10), _silence(0.04),
                       _adventure_note(494, 0.14))
    if event == "challenge_complete":
        return _concat(
            _adventure_note(392, 0.09), _adventure_note(494, 0.09),
            _adventure_note(587, 0.09), _ship_bell(784, 0.28),
        )
    if event == "challenge_fail":
        return _concat(_ship_bell(330, 0.25), _ship_bell(220, 0.30))
    if event == "level_up":
        return _concat(
            _adventure_note(262, 0.07), _adventure_note(330, 0.07),
            _adventure_note(392, 0.07), _adventure_note(494, 0.07),
            _ship_bell(659, 0.22), _ship_bell(784, 0.28),
        )
    if event == "toast_info":
        return _ship_bell(1047, 0.22)
    if event == "toast_warning":
        return _concat(_ship_bell(659, 0.16), _silence(0.05), _ship_bell(659, 0.16))
    if event == "countdown_tick":
        return _compass_tick()
    if event == "countdown_final":
        return _concat(
            _compass_tick(), _silence(0.03), _compass_tick(), _silence(0.03),
            _compass_tick(), _silence(0.03), _ship_bell(880, 0.24),
        )
    if event == "personal_best":
        return _concat(
            _adventure_note(392, 0.08), _adventure_note(494, 0.08),
            _adventure_note(587, 0.08), _ship_bell(784, 0.22), _ship_bell(988, 0.28),
        )
    if event == "combo":
        return _ship_bell(880, 0.14)
    return []


def _build_turbo_racer(event: str) -> list[float]:
    """Indianapolis 500/Getaway VPX – Motor sweep, starting lights beeps."""
    def _engine_rev(f_start: float, f_end: float, dur: float) -> list[float]:
        sq = _sweep(f_start, f_end, dur, amplitude=0.55, wave_fn="square")
        sn = _sweep(f_start * 2, f_end * 2, dur, amplitude=0.20, wave_fn="sine")
        return _envelope(_mix(sq, sn), attack=0.02, release=0.05)

    def _start_beep(freq: float = 1000) -> list[float]:
        return _envelope(_sine(freq, 0.06, 0.65), attack=0.003, release=0.02)

    if event == "achievement_unlock":
        return _concat(_engine_rev(200, 1200, 0.20), _start_beep(1200), _start_beep(1400))
    if event == "achievement_rare":
        return _concat(
            _engine_rev(150, 1600, 0.28),
            _start_beep(1000), _start_beep(1200),
            _start_beep(1400), _start_beep(1600),
        )
    if event == "challenge_start":
        return _concat(
            _start_beep(800), _silence(0.08), _start_beep(800), _silence(0.08),
            _start_beep(800), _silence(0.08), _engine_rev(300, 1000, 0.14),
        )
    if event == "challenge_complete":
        return _concat(_engine_rev(400, 1800, 0.22), _start_beep(1600), _start_beep(1800))
    if event == "challenge_fail":
        return _concat(_engine_rev(1000, 100, 0.25), _envelope(_noise(0.06, 0.35), release=0.04))
    if event == "level_up":
        return _concat(_engine_rev(100, 2000, 0.30), _start_beep(1200),
                       _start_beep(1400), _start_beep(1600))
    if event == "toast_info":
        return _start_beep(1000)
    if event == "toast_warning":
        return _concat(_start_beep(900), _silence(0.04), _start_beep(900))
    if event == "countdown_tick":
        return _start_beep(800)
    if event == "countdown_final":
        return _concat(
            _start_beep(800), _silence(0.07), _start_beep(800), _silence(0.07),
            _start_beep(800), _silence(0.07), _engine_rev(500, 2000, 0.16),
        )
    if event == "personal_best":
        return _concat(_engine_rev(200, 2200, 0.28), _start_beep(1400),
                       _start_beep(1600), _start_beep(1800))
    if event == "combo":
        return _start_beep(1200)
    return []


def _build_neon_lounge(event: str) -> list[float]:
    """Pinball FX style – Smooth jazz chords, soft pads, elegant notifications."""
    def _pad_note(freq: float, dur: float) -> list[float]:
        s1 = _sine(freq, dur, amplitude=0.35)
        s2 = _sine(freq * 1.25, dur, amplitude=0.20)
        s3 = _sine(freq * 1.5, dur, amplitude=0.12)
        return _envelope(_mix(_mix(s1, s2), s3), attack=0.05, release=0.10)

    def _soft_ding(freq: float) -> list[float]:
        return _ring(freq, 0.28, decay=3.5, amplitude=0.55)

    if event == "achievement_unlock":
        return _concat(
            _pad_note(523, 0.15), _pad_note(659, 0.15), _pad_note(784, 0.25),
        )
    if event == "achievement_rare":
        return _concat(
            _pad_note(392, 0.14), _pad_note(494, 0.14), _pad_note(587, 0.14),
            _pad_note(740, 0.14), _pad_note(880, 0.28),
        )
    if event == "challenge_start":
        return _concat(_pad_note(330, 0.14), _silence(0.04), _pad_note(440, 0.18))
    if event == "challenge_complete":
        return _concat(
            _pad_note(440, 0.14), _pad_note(523, 0.14), _pad_note(659, 0.22),
        )
    if event == "challenge_fail":
        return _envelope(_concat(
            _pad_note(330, 0.16), _pad_note(262, 0.20),
        ), release=0.10)
    if event == "level_up":
        return _envelope(_concat(
            _pad_note(262, 0.10), _pad_note(330, 0.10), _pad_note(392, 0.10),
            _pad_note(494, 0.10), _pad_note(659, 0.22),
        ), attack=0.03, release=0.10)
    if event == "toast_info":
        return _soft_ding(1047)
    if event == "toast_warning":
        return _concat(_soft_ding(740), _silence(0.05), _soft_ding(740))
    if event == "countdown_tick":
        return _envelope(_sine(880, 0.07, 0.40), attack=0.008, release=0.04)
    if event == "countdown_final":
        return _concat(
            _soft_ding(659), _silence(0.03), _soft_ding(784),
            _silence(0.03), _soft_ding(988), _silence(0.03), _soft_ding(1319),
        )
    if event == "personal_best":
        return _concat(
            _pad_note(392, 0.12), _pad_note(494, 0.12), _pad_note(587, 0.12),
            _pad_note(740, 0.14), _pad_note(988, 0.28),
        )
    if event == "combo":
        return _soft_ding(880)
    return []


def _build_voltage(event: str) -> list[float]:
    """Pinball Arcade style – Electric zaps, high-voltage crackle, transformer hum."""
    def _zap(f_start: float, f_end: float, dur: float = 0.10) -> list[float]:
        noise_layer = _noise(dur, amplitude=0.40)
        sweep_layer = _sweep(f_start, f_end, dur, amplitude=0.55, wave_fn="sine")
        return _envelope(_mix(noise_layer, sweep_layer), attack=0.002, release=0.04)

    def _hum(freq: float = 60, dur: float = 0.15) -> list[float]:
        h1 = _sine(freq, dur, amplitude=0.35)
        h2 = _sine(freq * 2, dur, amplitude=0.20)
        h3 = _sine(freq * 3, dur, amplitude=0.12)
        h4 = _sine(freq * 5, dur, amplitude=0.06)
        return _envelope(_mix(_mix(_mix(h1, h2), h3), h4), attack=0.03, release=0.06)

    def _spark() -> list[float]:
        return _envelope(_crackle(0.04, density=0.15), attack=0.001, release=0.015)

    if event == "achievement_unlock":
        return _concat(_spark(), _zap(200, 1500, 0.12), _hum(60, 0.18))
    if event == "achievement_rare":
        return _concat(
            _spark(), _zap(150, 2000, 0.14), _spark(), _hum(60, 0.12),
            _zap(300, 1800, 0.12), _hum(120, 0.18),
        )
    if event == "challenge_start":
        return _concat(_zap(600, 200, 0.10), _silence(0.03), _zap(200, 800, 0.12))
    if event == "challenge_complete":
        return _concat(_zap(200, 1600, 0.14), _spark(), _hum(60, 0.20))
    if event == "challenge_fail":
        return _concat(_spark(), _sweep(800, 60, 0.22, amplitude=0.55),
                       _crackle(0.06, density=0.12))
    if event == "level_up":
        return _concat(
            _hum(60, 0.08), _zap(100, 1800, 0.18),
            _spark(), _hum(120, 0.12), _zap(200, 2000, 0.12),
        )
    if event == "toast_info":
        return _zap(600, 1000, 0.07)
    if event == "toast_warning":
        return _concat(_zap(800, 400, 0.07), _silence(0.03), _zap(800, 400, 0.07))
    if event == "countdown_tick":
        return _spark()
    if event == "countdown_final":
        return _concat(
            _spark(), _silence(0.02), _spark(), _silence(0.02),
            _spark(), _silence(0.02), _zap(200, 1600, 0.14),
        )
    if event == "personal_best":
        return _concat(
            _hum(60, 0.08), _zap(100, 2000, 0.18), _spark(),
            _hum(120, 0.10), _zap(300, 2200, 0.14), _spark(), _hum(60, 0.18),
        )
    if event == "combo":
        return _zap(800, 1400, 0.07)
    return []


_PACK_BUILDERS = {
    "arcade":          _build_arcade,
    "subtle":          _build_subtle,
    "sci_fi":          _build_sci_fi,
    "retro_8bit":      _build_retro_8bit,
    "pinball_classic": _build_pinball_classic,
    "galactic_battle": _build_galactic_battle,
    "stage_magic":     _build_stage_magic,
    "neon_grid":       _build_neon_grid,
    "martian_assault": _build_martian_assault,
    "carnival_show":   _build_carnival_show,
    "medieval_quest":  _build_medieval_quest,
    "haunted_manor":   _build_haunted_manor,
    "deep_ocean":      _build_deep_ocean,
    "jukebox":         _build_jukebox,
    "showtime":        _build_showtime,
    "chrome_steel":    _build_chrome_steel,
    "treasure_hunt":   _build_treasure_hunt,
    "turbo_racer":     _build_turbo_racer,
    "neon_lounge":     _build_neon_lounge,
    "voltage":         _build_voltage,
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
