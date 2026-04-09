"""sound.py – Procedural sound engine for VPX Achievement Watcher.

Generates all audio in memory via WAV – no external files needed.
Playback via winsound on Windows; silent on other platforms.
"""

from __future__ import annotations

import io
import math
import random
import struct
import threading
from functools import lru_cache
from typing import List

SAMPLE_RATE = 22050
DEFAULT_VOLUME = 20

# ── Public metadata ───────────────────────────────────────────────────────────

SOUND_PACKS = {
    "zaptron":          "Zaptron",
    "iron_basilisk":    "Iron Basilisk",
    "voodoo_swamp":     "Voodoo Swamp",
    "pixel_ghost":      "Pixel Ghost",
    "solar_drift":      "Solar Drift",
    "rokos_lair":       "Roko's Lair",
    "thunderclap_rex":  "Thunderclap Rex",
    "frostbite_hollow": "Frostbite Hollow",
    "ratchet_circus":   "Ratchet Circus",
    "lucky_stardust":   "Lucky Stardust",
    "boneshaker":       "Boneshaker",
    "vex_machina":      "Vex Machina",
    "stormfront_jake":  "Stormfront Jake",
    "nebula_drift":     "Nebula Drift",
    "gideons_clock":    "Gideon's Clock",
    "sapphire_specter": "Sapphire Specter",
    "molten_core":      "Molten Core",
    "zigzag_bandit":    "Zigzag Bandit",
    "wildcat_hollow":   "Wildcat Hollow",
    "crimson_flare":    "Crimson Flare",
}

SOUND_EVENTS = [
    ("achievement_unlock", "🏆 Achievement Unlock"),
    ("level_up",           "⬆️ Level Up"),
    ("duel_received",      "⚔️ Automatch Found"),
    ("duel_accepted",      "🤝 Duel Accepted"),
    ("duel_won",           "🏆 Duel Won"),
    ("duel_lost",          "💀 Duel Lost"),
    ("duel_expired",       "⏰ Duel Expired"),
    ("duel_declined",      "❌ Duel Declined"),
]

# ── Low-level helpers ─────────────────────────────────────────────────────────

def _to_bytes(samples: List[float]) -> bytes:
    out = bytearray(len(samples) * 2)
    for i, s in enumerate(samples):
        v = max(-1.0, min(1.0, s))
        struct.pack_into("<h", out, i * 2, int(v * 32767))
    return bytes(out)


def _make_wav(samples: List[float], sr: int = SAMPLE_RATE) -> bytes:
    data = _to_bytes(samples)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(data)))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    byte_rate = sr * 2
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sr, byte_rate, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(data)))
    buf.write(data)
    return buf.getvalue()


def _sine(freq: float, dur: float, sr: int = SAMPLE_RATE) -> List[float]:
    n = int(dur * sr)
    return [math.sin(2 * math.pi * freq * i / sr) for i in range(n)]


def _square(freq: float, dur: float, sr: int = SAMPLE_RATE) -> List[float]:
    n = int(dur * sr)
    return [1.0 if math.sin(2 * math.pi * freq * i / sr) >= 0 else -1.0 for i in range(n)]


def _sweep(freq0: float, freq1: float, dur: float, sr: int = SAMPLE_RATE) -> List[float]:
    n = int(dur * sr)
    result: List[float] = []
    phase = 0.0
    for i in range(n):
        result.append(math.sin(phase))
        f = freq0 + (freq1 - freq0) * i / max(1, n - 1)
        phase += 2 * math.pi * f / sr
    return result


def _envelope(samples: List[float], attack: float, decay: float,
              sustain_lvl: float, release: float,
              sr: int = SAMPLE_RATE) -> List[float]:
    n = len(samples)
    a = int(attack * sr)
    d = int(decay * sr)
    r = int(release * sr)
    s_len = max(0, n - a - d - r)
    out: List[float] = []
    for i, x in enumerate(samples):
        if i < a:
            gain = (i + 1) / max(1, a)
        elif i < a + d:
            gain = 1.0 - (1.0 - sustain_lvl) * (i - a) / max(1, d)
        elif i < a + d + s_len:
            gain = sustain_lvl
        else:
            prog = (i - a - d - s_len) / max(1, r)
            gain = sustain_lvl * (1.0 - prog)
        out.append(x * max(0.0, gain))
    return out


def _concat(*args: List[float]) -> List[float]:
    result: List[float] = []
    for a in args:
        result.extend(a)
    return result


def _silence(dur: float, sr: int = SAMPLE_RATE) -> List[float]:
    return [0.0] * int(dur * sr)


def _mix(*args: List[float]) -> List[float]:
    if not args:
        return []
    n = max(len(a) for a in args)
    out = [0.0] * n
    for a in args:
        for i, v in enumerate(a):
            out[i] += v
    return [max(-1.0, min(1.0, x * 0.75)) for x in out]


def _tremolo(samples: List[float], rate: float, depth: float,
             sr: int = SAMPLE_RATE) -> List[float]:
    return [
        s * (1.0 - depth + depth * (0.5 + 0.5 * math.sin(2 * math.pi * rate * i / sr)))
        for i, s in enumerate(samples)
    ]


def _vibrato(samples: List[float], rate: float, depth: float,
             sr: int = SAMPLE_RATE) -> List[float]:
    out: List[float] = []
    n = len(samples)
    for i in range(n):
        offset = depth * math.sin(2 * math.pi * rate * i / sr)
        j = i + offset
        j0 = int(j)
        j1 = j0 + 1
        frac = j - j0
        if 0 <= j0 < n and 0 <= j1 < n:
            out.append(samples[j0] * (1.0 - frac) + samples[j1] * frac)
        elif 0 <= j0 < n:
            out.append(samples[j0])
        else:
            out.append(0.0)
    return out


def _noise(dur: float, sr: int = SAMPLE_RATE) -> List[float]:
    n = int(dur * sr)
    return [random.uniform(-1.0, 1.0) for _ in range(n)]


def _ring(samples: List[float], freq: float, sr: int = SAMPLE_RATE) -> List[float]:
    return [s * math.sin(2 * math.pi * freq * i / sr)
            for i, s in enumerate(samples)]


def _crackle(dur: float, sr: int = SAMPLE_RATE) -> List[float]:
    n = int(dur * sr)
    out: List[float] = []
    for _ in range(n):
        if random.random() < 0.015:
            out.append(random.uniform(-0.6, 0.6))
        else:
            out.append(0.0)
    return out


# ── Pack builders ──────────────────────────────────────────────────────────────

# Zaptron – pure square wave, fast staccato, mid-high pitch, sharp attack
def _build_zaptron(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(*[_square(f, 0.06, SR) for f in [523, 659, 784, 1046, 1319]])
        return _envelope(s, 0.002, 0.02, 0.75, 0.08, SR)
        return _envelope(s, 0.002, 0.02, 0.68, 0.08, SR)
        return _envelope(s, 0.002, 0.018, 0.78, 0.1, SR)
        return _envelope(s, 0.002, 0.02, 0.6, 0.12, SR)
    elif event == "level_up":
        s = _concat(*[_square(f, 0.05, SR) for f in [262, 330, 392, 494, 587, 659, 784, 988, 1175, 1319]])
        return _envelope(s, 0.002, 0.015, 0.82, 0.15, SR)
    elif event == "countdown_tick":
        return _envelope(_square(880, 0.035, SR), 0.001, 0.01, 0.5, 0.02, SR)
    elif event == "countdown_final":
        s = _concat(_square(1108, 0.07, SR), _square(1319, 0.12, SR))
        return _envelope(s, 0.001, 0.015, 0.78, 0.1, SR)
    elif event == "duel_received":
        s = _concat(
            _square(330, 0.04, SR), _silence(0.02, SR),
            _square(440, 0.04, SR), _silence(0.02, SR),
            _square(554, 0.04, SR), _silence(0.04, SR),
            _square(330, 0.04, SR), _silence(0.02, SR),
            _square(440, 0.04, SR), _silence(0.02, SR),
            _square(659, 0.08, SR),
        )
        return _envelope(s, 0.002, 0.02, 0.72, 0.1, SR)
    elif event == "duel_accepted":
        s = _concat(*[_square(f, 0.055, SR) for f in [440, 554, 659, 880]])
        return _envelope(s, 0.002, 0.018, 0.7, 0.1, SR)
    elif event == "duel_won":
        s = _concat(*[_square(f, 0.06, SR) for f in [523, 659, 784, 1046, 1319, 1568]])
        return _envelope(s, 0.002, 0.015, 0.82, 0.15, SR)
    elif event == "duel_lost":
        s = _concat(*[_square(f, 0.08, SR) for f in [554, 440, 370, 294, 220]])
        return _envelope(s, 0.002, 0.025, 0.5, 0.15, SR)
    elif event == "duel_expired":
        s = _concat(_square(440, 0.06, SR), _silence(0.04, SR), _square(330, 0.12, SR))
        return _envelope(s, 0.002, 0.02, 0.45, 0.15, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Iron Basilisk – heavy low square + noise, slow, bassy, deep
def _build_iron_basilisk(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        hit = _mix(_square(55, 0.12, SR), _noise(0.12, SR))
        hit = [s * 0.45 for s in hit]
        tone = _envelope(_square(110, 0.3, SR), 0.02, 0.08, 0.55, 0.25, SR)
        return _concat(_envelope(hit, 0.002, 0.04, 0.4, 0.1, SR), _silence(0.03, SR), tone)
        return s
        return s
        return _envelope([x * 0.5 for x in s], 0.005, 0.06, 0.45, 0.28, SR)
    elif event == "level_up":
        s = _concat(*[_envelope(_mix(_square(f, 0.1, SR), _noise(0.1, SR)),
                                0.005, 0.04, 0.55, 0.12, SR)
                      for f in [55, 73, 88, 110, 138, 165, 220]])
        return s
    elif event == "countdown_tick":
        s = _mix(_square(80, 0.055, SR), _noise(0.055, SR))
        return _envelope([x * 0.4 for x in s], 0.001, 0.02, 0.45, 0.03, SR)
    elif event == "countdown_final":
        s = _mix(_sweep(120, 55, 0.15, SR), _noise(0.15, SR))
        return _envelope([x * 0.55 for x in s], 0.003, 0.05, 0.6, 0.12, SR)
    elif event == "duel_received":
        hit1 = _mix(_square(55, 0.08, SR), _noise(0.08, SR))
        hit1 = [s * 0.45 for s in hit1]
        hit2 = _mix(_square(65, 0.08, SR), _noise(0.08, SR))
        hit2 = [s * 0.45 for s in hit2]
        sting = _envelope(_square(110, 0.32, SR), 0.02, 0.07, 0.62, 0.26, SR)
        return _concat(
            _envelope(hit1, 0.002, 0.03, 0.5, 0.07, SR),
            _silence(0.04, SR),
            _envelope(hit2, 0.002, 0.03, 0.5, 0.07, SR),
            _silence(0.05, SR),
            sting,
        )
    elif event == "duel_accepted":
        s = _concat(*[_envelope(_square(f, 0.1, SR), 0.01, 0.04, 0.6, 0.1, SR)
                      for f in [73, 88, 110, 138]])
        return s
    elif event == "duel_won":
        s = _concat(*[_envelope(_mix(_square(f, 0.1, SR), _noise(0.1, SR)),
                                0.01, 0.04, 0.62, 0.12, SR)
                      for f in [55, 73, 88, 110, 138, 165, 220]])
        return s
    elif event == "duel_lost":
        s = _mix(_sweep(220, 40, 0.42, SR), _noise(0.42, SR))
        return _envelope([x * 0.5 for x in s], 0.005, 0.07, 0.42, 0.35, SR)
    elif event == "duel_expired":
        s = _mix(_square(80, 0.12, SR), _noise(0.12, SR))
        return _envelope([x * 0.35 for x in s], 0.005, 0.04, 0.38, 0.14, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Voodoo Swamp – low crackle + tremolo sine, murky, atmospheric
def _build_voodoo_swamp(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        base = _tremolo(_sine(220, 0.3, SR), 4, 0.55, SR)
        cr = _crackle(0.3, SR)
        s = _mix(base, cr)
        tone = _envelope(_tremolo(_sine(440, 0.2, SR), 3, 0.45, SR), 0.02, 0.08, 0.55, 0.22, SR)
        return _concat(_envelope(s, 0.03, 0.1, 0.52, 0.25, SR), tone)
        return _concat(_envelope(s, 0.01, 0.06, 0.48, 0.18, SR),
                       _silence(0.04, SR),
                       _envelope(sting, 0.02, 0.07, 0.55, 0.22, SR))
        return _envelope(s, 0.02, 0.08, 0.58, 0.25, SR)
        return _envelope(s, 0.005, 0.06, 0.42, 0.3, SR)
    elif event == "level_up":
        s = _mix(
            _tremolo(_sine(110, 0.4, SR), 3, 0.5, SR),
            _tremolo(_sine(220, 0.4, SR), 4, 0.4, SR),
            _crackle(0.4, SR),
        )
        return _envelope(s, 0.04, 0.1, 0.6, 0.3, SR)
    elif event == "countdown_tick":
        s = _mix(_sine(200, 0.06, SR), _crackle(0.06, SR))
        return _envelope([x * 0.45 for x in s], 0.002, 0.02, 0.4, 0.04, SR)
    elif event == "countdown_final":
        s = _mix(_sweep(150, 500, 0.14, SR), _tremolo(_sine(330, 0.18, SR), 5, 0.45, SR))
        return _envelope(s, 0.01, 0.06, 0.62, 0.2, SR)
    elif event == "duel_received":
        alert = _mix(_sweep(80, 330, 0.18, SR), _crackle(0.18, SR))
        sting1 = _tremolo(_sine(330, 0.14, SR), 5, 0.5, SR)
        sting2 = _tremolo(_sine(440, 0.18, SR), 5, 0.5, SR)
        return _concat(
            _envelope(alert, 0.01, 0.06, 0.48, 0.15, SR),
            _silence(0.04, SR),
            _envelope(sting1, 0.02, 0.07, 0.52, 0.18, SR),
            _envelope(sting2, 0.02, 0.07, 0.58, 0.22, SR),
        )
    elif event == "duel_accepted":
        s = _mix(_sweep(150, 440, 0.18, SR), _crackle(0.18, SR))
        tone = _envelope(_tremolo(_sine(440, 0.2, SR), 4, 0.45, SR), 0.02, 0.07, 0.55, 0.22, SR)
        return _concat(_envelope(s, 0.01, 0.06, 0.5, 0.15, SR), _silence(0.03, SR), tone)
    elif event == "duel_won":
        s = _mix(
            _sweep(200, 660, 0.28, SR),
            _tremolo(_sine(440, 0.28, SR), 3, 0.4, SR),
            _crackle(0.28, SR),
        )
        return _envelope(s, 0.02, 0.1, 0.62, 0.28, SR)
    elif event == "duel_lost":
        s = _mix(_sweep(330, 55, 0.42, SR), _crackle(0.42, SR))
        return _envelope(s, 0.005, 0.07, 0.4, 0.35, SR)
    elif event == "duel_expired":
        s = _mix(_tremolo(_sine(220, 0.2, SR), 3, 0.5, SR), _crackle(0.2, SR))
        return _envelope(s, 0.01, 0.06, 0.35, 0.2, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Pixel Ghost – square + ring mod, retro ghostly, mid-range
def _build_pixel_ghost(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _ring(_concat(*[_square(f, 0.07, SR) for f in [370, 466, 554, 740]]), 180, SR)
        return _envelope(s, 0.005, 0.03, 0.68, 0.15, SR)
        return _envelope(s, 0.005, 0.03, 0.62, 0.15, SR)
        return _envelope(s, 0.005, 0.025, 0.72, 0.15, SR)
        return _envelope(s, 0.003, 0.03, 0.55, 0.18, SR)
    elif event == "level_up":
        s = _ring(_concat(*[_square(f, 0.058, SR)
                            for f in [247, 294, 370, 440, 554, 659, 740, 932, 1108]]), 160, SR)
        return _envelope(s, 0.003, 0.02, 0.75, 0.2, SR)
    elif event == "countdown_tick":
        s = _ring(_square(440, 0.04, SR), 160, SR)
        return _envelope(s, 0.001, 0.015, 0.45, 0.025, SR)
    elif event == "countdown_final":
        s = _ring(_concat(_square(740, 0.08, SR), _square(932, 0.14, SR)), 200, SR)
        return _envelope(s, 0.002, 0.03, 0.72, 0.12, SR)
    elif event == "duel_received":
        s = _ring(_concat(
            _square(220, 0.05, SR), _silence(0.02, SR),
            _square(294, 0.05, SR), _silence(0.02, SR),
            _square(370, 0.05, SR), _silence(0.04, SR),
            _square(220, 0.05, SR), _silence(0.02, SR),
            _square(294, 0.05, SR), _silence(0.02, SR),
            _square(440, 0.1, SR),
        ), 130, SR)
        return _envelope(s, 0.005, 0.03, 0.68, 0.12, SR)
    elif event == "duel_accepted":
        s = _ring(_concat(*[_square(f, 0.065, SR) for f in [294, 370, 440, 554]]), 150, SR)
        return _envelope(s, 0.005, 0.025, 0.68, 0.12, SR)
    elif event == "duel_won":
        s = _ring(_concat(*[_square(f, 0.065, SR) for f in [294, 370, 440, 554, 659, 880, 1108]]), 180, SR)
        return _envelope(s, 0.005, 0.025, 0.75, 0.15, SR)
    elif event == "duel_lost":
        s = _ring(_concat(*[_square(f, 0.08, SR) for f in [440, 370, 311, 247, 185]]), 100, SR)
        return _envelope(s, 0.003, 0.03, 0.52, 0.18, SR)
    elif event == "duel_expired":
        s = _ring(_concat(_square(370, 0.07, SR), _silence(0.04, SR), _square(247, 0.14, SR)), 110, SR)
        return _envelope(s, 0.003, 0.025, 0.42, 0.18, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Solar Drift – smooth pure sine + slow sweeps, gentle fade-in, ethereal
def _build_solar_drift(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        rise = _sweep(300, 900, 0.2, SR)
        tone = _sine(900, 0.3, SR)
        return _envelope(_concat(rise, tone), 0.06, 0.12, 0.6, 0.3, SR)
        return _envelope(s, 0.05, 0.1, 0.62, 0.28, SR)
        return _envelope(s, 0.06, 0.1, 0.68, 0.3, SR)
        return _envelope(s, 0.04, 0.1, 0.48, 0.3, SR)
    elif event == "level_up":
        s = _concat(
            _sweep(220, 660, 0.18, SR),
            _sweep(660, 1100, 0.15, SR),
            _sweep(1100, 1760, 0.12, SR),
            _sine(1760, 0.25, SR),
        )
        return _envelope(s, 0.06, 0.1, 0.72, 0.3, SR)
    elif event == "countdown_tick":
        return _envelope(_sine(660, 0.07, SR), 0.01, 0.03, 0.42, 0.04, SR)
    elif event == "countdown_final":
        s = _concat(_sweep(440, 1320, 0.14, SR), _sine(1320, 0.22, SR))
        return _envelope(s, 0.04, 0.08, 0.72, 0.25, SR)
    elif event == "duel_received":
        s = _concat(
            _sweep(300, 600, 0.14, SR), _sine(600, 0.06, SR),
            _silence(0.04, SR),
            _sweep(300, 880, 0.16, SR), _sine(880, 0.22, SR),
        )
        return _envelope(s, 0.06, 0.12, 0.65, 0.3, SR)
    elif event == "duel_accepted":
        s = _concat(_sweep(392, 784, 0.16, SR), _sine(784, 0.24, SR))
        return _envelope(s, 0.05, 0.1, 0.62, 0.26, SR)
    elif event == "duel_won":
        s = _concat(_sweep(440, 1320, 0.22, SR), _sine(1320, 0.35, SR))
        return _envelope(s, 0.06, 0.12, 0.72, 0.32, SR)
    elif event == "duel_lost":
        s = _concat(_sine(660, 0.14, SR), _sweep(660, 180, 0.38, SR))
        return _envelope(s, 0.04, 0.1, 0.45, 0.32, SR)
    elif event == "duel_expired":
        s = _concat(_sine(440, 0.1, SR), _sweep(440, 220, 0.22, SR))
        return _envelope(s, 0.04, 0.08, 0.38, 0.28, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Roko's Lair – deep low sine, very long sustain, ominous dungeon
def _build_rokos_lair(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        bass = _envelope(_sine(80, 0.4, SR), 0.05, 0.1, 0.5, 0.3, SR)
        mid = _envelope(_sine(160, 0.35, SR), 0.04, 0.1, 0.45, 0.28, SR)
        bright = _envelope(_sine(640, 0.25, SR), 0.02, 0.08, 0.6, 0.22, SR)
        return _mix(bass, mid, bright)
        return _concat(pulse, _silence(0.04, SR), sting)
        return s
        return _envelope(s, 0.04, 0.1, 0.45, 0.35, SR)
    elif event == "level_up":
        layers = [_envelope(_sine(f, 0.5, SR), 0.04, 0.1, 0.5, 0.38, SR)
                  for f in [55, 110, 220, 440]]
        return _mix(*layers)
    elif event == "countdown_tick":
        return _envelope(_sine(160, 0.08, SR), 0.005, 0.03, 0.45, 0.05, SR)
    elif event == "countdown_final":
        s = _mix(
            _envelope(_sine(80, 0.35, SR), 0.04, 0.1, 0.55, 0.3, SR),
            _envelope(_sine(320, 0.28, SR), 0.03, 0.09, 0.62, 0.25, SR),
        )
        return s
    elif event == "duel_received":
        pulse1 = _envelope(_sine(80, 0.12, SR), 0.005, 0.04, 0.5, 0.1, SR)
        pulse2 = _envelope(_sine(80, 0.12, SR), 0.005, 0.04, 0.5, 0.1, SR)
        sting = _envelope(_sine(320, 0.4, SR), 0.04, 0.12, 0.58, 0.32, SR)
        return _concat(pulse1, _silence(0.05, SR), pulse2, _silence(0.06, SR), sting)
    elif event == "duel_accepted":
        s = _mix(
            _envelope(_sine(80, 0.4, SR), 0.04, 0.1, 0.45, 0.32, SR),
            _envelope(_sine(480, 0.32, SR), 0.03, 0.09, 0.58, 0.28, SR),
        )
        return s
    elif event == "duel_won":
        layers = [_envelope(_sine(f, 0.55, SR), 0.05, 0.12, 0.55, 0.4, SR)
                  for f in [80, 160, 480, 640]]
        return _mix(*layers)
    elif event == "duel_lost":
        s = _concat(_sine(160, 0.14, SR), _sweep(160, 40, 0.5, SR))
        return _envelope(s, 0.04, 0.12, 0.42, 0.4, SR)
    elif event == "duel_expired":
        s = _mix(
            _envelope(_sine(80, 0.35, SR), 0.04, 0.1, 0.38, 0.3, SR),
            _envelope(_sine(160, 0.28, SR), 0.03, 0.08, 0.35, 0.25, SR),
        )
        return s
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Thunderclap Rex – noise transients + short sweeps, percussive, powerful
def _build_thunderclap_rex(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        crack = _mix(_noise(0.05, SR), _sweep(600, 200, 0.05, SR))
        crack = [s * 0.6 for s in crack]
        boom = _mix(_sweep(400, 60, 0.22, SR), _noise(0.22, SR))
        boom = [s * 0.5 for s in boom]
        high = _envelope(_sine(1200, 0.2, SR), 0.005, 0.05, 0.6, 0.18, SR)
        return _concat(_envelope(crack, 0.001, 0.02, 0.5, 0.04, SR),
                       _envelope(boom, 0.003, 0.06, 0.48, 0.2, SR), high)
        return s
        return s
        return _envelope([x * 0.55 for x in s], 0.003, 0.06, 0.45, 0.3, SR)
    elif event == "level_up":
        beats = _concat(*[
            _concat(_envelope(_mix(_noise(0.05, SR), _sweep(200 + i * 80, 60, 0.05, SR)),
                              0.001, 0.02, 0.52, 0.04, SR), _silence(0.03, SR))
            for i in range(4)
        ])
        finale = _envelope(_mix(_sweep(200, 1600, 0.25, SR), _noise(0.25, SR)),
                           0.003, 0.06, 0.6, 0.22, SR)
        return _concat(beats, finale)
    elif event == "countdown_tick":
        s = _mix(_noise(0.04, SR), _sweep(400, 200, 0.04, SR))
        return _envelope([x * 0.45 for x in s], 0.001, 0.012, 0.42, 0.025, SR)
    elif event == "countdown_final":
        s = _mix(_noise(0.06, SR), _sweep(600, 1400, 0.06, SR))
        boom = _mix(_sweep(300, 80, 0.18, SR), _noise(0.18, SR))
        return _concat(_envelope([x * 0.55 for x in s], 0.001, 0.02, 0.55, 0.05, SR),
                       _envelope([x * 0.55 for x in boom], 0.003, 0.06, 0.55, 0.15, SR))
    elif event == "duel_received":
        crack1 = _mix(_noise(0.05, SR), _sweep(500, 150, 0.05, SR))
        crack1 = [x * 0.6 for x in crack1]
        crack2 = _mix(_noise(0.05, SR), _sweep(600, 200, 0.05, SR))
        crack2 = [x * 0.6 for x in crack2]
        boom = _mix(_sweep(300, 1200, 0.22, SR), _noise(0.22, SR))
        boom = [x * 0.5 for x in boom]
        return _concat(
            _envelope(crack1, 0.001, 0.02, 0.5, 0.04, SR),
            _silence(0.04, SR),
            _envelope(crack2, 0.001, 0.02, 0.5, 0.04, SR),
            _silence(0.04, SR),
            _envelope(boom, 0.003, 0.06, 0.6, 0.2, SR),
        )
    elif event == "duel_accepted":
        s = _concat(
            _envelope(_mix(_noise(0.06, SR), _sweep(400, 1000, 0.06, SR)),
                      0.001, 0.02, 0.55, 0.05, SR),
            _envelope(_mix(_sweep(200, 1000, 0.18, SR), _noise(0.18, SR)),
                      0.003, 0.05, 0.58, 0.16, SR),
        )
        return s
    elif event == "duel_won":
        beats = _concat(*[
            _concat(_envelope(_mix(_noise(0.05, SR), _sweep(200 + i * 100, 80, 0.05, SR)),
                              0.001, 0.02, 0.52, 0.04, SR), _silence(0.03, SR))
            for i in range(3)
        ])
        finale = _envelope(_mix(_sweep(200, 1800, 0.28, SR), _noise(0.28, SR)),
                           0.003, 0.06, 0.65, 0.25, SR)
        return _concat(beats, finale)
    elif event == "duel_lost":
        s = _mix(_sweep(1000, 40, 0.42, SR), _noise(0.42, SR))
        return _envelope([x * 0.55 for x in s], 0.003, 0.07, 0.42, 0.35, SR)
    elif event == "duel_expired":
        crack = _mix(_noise(0.06, SR), _sweep(500, 200, 0.06, SR))
        crack = [x * 0.45 for x in crack]
        tail = _mix(_sweep(200, 80, 0.18, SR), _noise(0.18, SR))
        tail = [x * 0.35 for x in tail]
        return _concat(
            _envelope(crack, 0.001, 0.02, 0.45, 0.05, SR),
            _envelope(tail, 0.003, 0.05, 0.35, 0.18, SR),
        )
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Frostbite Hollow – very high frequency tremolo sine, crystalline pings
def _build_frostbite_hollow(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        pings = _concat(*[
            _envelope(_tremolo(_sine(f, 0.1, SR), 8, 0.35, SR), 0.005, 0.03, 0.65, 0.12, SR)
            for f in [1319, 1568, 1760, 2093, 2637]
        ])
        return pings
        return s
        return pings
        return s
    elif event == "level_up":
        pings = _concat(*[
            _envelope(_tremolo(_sine(f, 0.08, SR), 10, 0.28, SR), 0.003, 0.02, 0.7, 0.1, SR)
            for f in [784, 988, 1175, 1319, 1568, 1760, 2093, 2349, 2637, 3136]
        ])
        return pings
    elif event == "countdown_tick":
        return _envelope(_tremolo(_sine(2093, 0.05, SR), 10, 0.25, SR), 0.002, 0.015, 0.45, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_tremolo(_sine(f, 0.08, SR), 8, 0.3, SR), 0.003, 0.025, 0.68, 0.1, SR)
            for f in [1568, 1760, 2093]
        ])
        return s
    elif event == "duel_received":
        pings1 = _concat(*[
            _envelope(_tremolo(_sine(f, 0.09, SR), 8, 0.3, SR), 0.004, 0.028, 0.62, 0.1, SR)
            for f in [1319, 1568, 1760]
        ])
        pings2 = _concat(*[
            _envelope(_tremolo(_sine(f, 0.09, SR), 8, 0.3, SR), 0.004, 0.028, 0.68, 0.12, SR)
            for f in [1047, 1319, 1568, 2093]
        ])
        return _concat(pings1, _silence(0.03, SR), pings2)
    elif event == "duel_accepted":
        pings = _concat(*[
            _envelope(_tremolo(_sine(f, 0.1, SR), 7, 0.3, SR), 0.004, 0.03, 0.65, 0.1, SR)
            for f in [1175, 1568, 1760, 2093]
        ])
        return pings
    elif event == "duel_won":
        pings = _concat(*[
            _envelope(_tremolo(_sine(f, 0.085, SR), 9, 0.28, SR), 0.004, 0.025, 0.72, 0.12, SR)
            for f in [784, 988, 1175, 1319, 1568, 1760, 2093, 2637]
        ])
        return pings
    elif event == "duel_lost":
        s = _concat(
            _envelope(_tremolo(_sine(2093, 0.1, SR), 7, 0.4, SR), 0.005, 0.03, 0.62, 0.1, SR),
            _envelope(_tremolo(_sweep(2093, 500, 0.35, SR), 6, 0.38, SR), 0.01, 0.06, 0.45, 0.3, SR),
        )
        return s
    elif event == "duel_expired":
        s = _concat(
            _envelope(_tremolo(_sine(1760, 0.07, SR), 8, 0.3, SR), 0.003, 0.025, 0.5, 0.07, SR),
            _silence(0.04, SR),
            _envelope(_tremolo(_sine(1047, 0.16, SR), 7, 0.32, SR), 0.005, 0.04, 0.38, 0.18, SR),
        )
        return s
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Ratchet Circus – mechanical staccato noise + square bursts, carnival machine
def _build_ratchet_circus(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        mech = _concat(*[
            _concat(_envelope(_mix(_noise(0.025, SR), _square(f, 0.025, SR)),
                              0.001, 0.008, 0.5, 0.02, SR), _silence(0.015, SR))
            for f in [440, 554, 659, 880, 1108]
        ])
        return mech
        return _concat(ratchet, _silence(0.03, SR), call)
        return mech
        return wind_down
    elif event == "level_up":
        mech = _concat(*[
            _concat(_envelope(_mix(_noise(0.02, SR), _square(f, 0.02, SR)),
                              0.001, 0.007, 0.55, 0.015, SR), _silence(0.01, SR))
            for f in [262, 330, 392, 494, 587, 659, 784, 880, 988, 1175, 1319, 1568]
        ])
        return mech
    elif event == "countdown_tick":
        s = _mix(_noise(0.03, SR), _square(440, 0.03, SR))
        return _envelope([x * 0.45 for x in s], 0.001, 0.01, 0.42, 0.02, SR)
    elif event == "countdown_final":
        mech = _concat(*[
            _concat(_envelope(_mix(_noise(0.025, SR), _square(f, 0.025, SR)),
                              0.001, 0.008, 0.55, 0.02, SR), _silence(0.01, SR))
            for f in [659, 784, 988]
        ])
        return mech
    elif event == "duel_received":
        ratchet = _concat(*[
            _concat(_envelope(_mix(_noise(0.025, SR), _square(f, 0.025, SR)),
                              0.001, 0.008, 0.5, 0.02, SR), _silence(0.015, SR))
            for f in [330, 440, 554]
        ])
        fanfare = _concat(
            _envelope(_mix(_square(523, 0.05, SR), _noise(0.05, SR)), 0.001, 0.015, 0.55, 0.04, SR),
            _silence(0.02, SR),
            _envelope(_mix(_square(659, 0.05, SR), _noise(0.05, SR)), 0.001, 0.015, 0.58, 0.04, SR),
            _silence(0.02, SR),
            _envelope(_mix(_square(880, 0.12, SR), _noise(0.12, SR)), 0.002, 0.03, 0.65, 0.1, SR),
        )
        return _concat(ratchet, _silence(0.02, SR), fanfare)
    elif event == "duel_accepted":
        mech = _concat(*[
            _concat(_envelope(_mix(_noise(0.025, SR), _square(f, 0.025, SR)),
                              0.001, 0.008, 0.52, 0.02, SR), _silence(0.012, SR))
            for f in [440, 554, 659, 880]
        ])
        return mech
    elif event == "duel_won":
        mech = _concat(*[
            _concat(_envelope(_mix(_noise(0.022, SR), _square(f, 0.022, SR)),
                              0.001, 0.008, 0.55, 0.018, SR), _silence(0.01, SR))
            for f in [392, 494, 587, 784, 988, 1175, 1319, 1568]
        ])
        return mech
    elif event == "duel_lost":
        wind_down = _concat(*[
            _envelope(_mix(_noise(0.04, SR), _square(f, 0.04, SR)),
                      0.001, 0.015, 0.5, 0.035, SR)
            for f in [554, 494, 440, 370, 294, 220]
        ])
        return wind_down
    elif event == "duel_expired":
        s = _concat(
            _envelope(_mix(_noise(0.03, SR), _square(440, 0.03, SR)), 0.001, 0.01, 0.45, 0.025, SR),
            _silence(0.04, SR),
            _envelope(_mix(_noise(0.04, SR), _square(330, 0.04, SR)), 0.001, 0.015, 0.38, 0.04, SR),
        )
        return s
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Lucky Stardust – fast bright high sine arpeggios, glittery, sparkly
def _build_lucky_stardust(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(*[_envelope(_sine(f, 0.045, SR), 0.002, 0.015, 0.7, 0.045, SR)
                      for f in [1047, 1319, 1568, 1760, 2093, 2349, 2793, 3136]])
        return s
        return _concat(s, _silence(0.03, SR),
                       _envelope(_sine(1760, 0.22, SR), 0.01, 0.06, 0.68, 0.2, SR))
        return s
        return s
    elif event == "level_up":
        s = _concat(*[_envelope(_sine(f, 0.038, SR), 0.001, 0.01, 0.75, 0.038, SR)
                      for f in [523, 659, 784, 988, 1175, 1319, 1568, 1760, 2093, 2349,
                                 2637, 3136]])
        return s
    elif event == "countdown_tick":
        return _envelope(_sine(2093, 0.03, SR), 0.001, 0.008, 0.55, 0.022, SR)
    elif event == "countdown_final":
        s = _concat(*[_envelope(_sine(f, 0.045, SR), 0.002, 0.015, 0.72, 0.045, SR)
                      for f in [1568, 1760, 2093]])
        return s
    elif event == "duel_received":
        arp1 = _concat(*[_envelope(_sine(f, 0.045, SR), 0.002, 0.015, 0.68, 0.045, SR)
                         for f in [784, 988, 1175, 1568]])
        arp2 = _concat(*[_envelope(_sine(f, 0.042, SR), 0.002, 0.013, 0.72, 0.042, SR)
                         for f in [784, 988, 1319, 1760, 2093]])
        return _concat(arp1, _silence(0.03, SR), arp2)
    elif event == "duel_accepted":
        s = _concat(*[_envelope(_sine(f, 0.05, SR), 0.002, 0.015, 0.7, 0.05, SR)
                      for f in [988, 1175, 1568, 2093]])
        return s
    elif event == "duel_won":
        s = _concat(*[_envelope(_sine(f, 0.04, SR), 0.002, 0.012, 0.75, 0.04, SR)
                      for f in [784, 988, 1175, 1319, 1568, 1760, 2093, 2793, 3136]])
        return s
    elif event == "duel_lost":
        s = _concat(*[_envelope(_sine(f, 0.06, SR), 0.003, 0.02, 0.55, 0.06, SR)
                      for f in [1568, 1319, 1047, 784, 523]])
        return s
    elif event == "duel_expired":
        s = _concat(
            _envelope(_sine(1175, 0.06, SR), 0.002, 0.018, 0.52, 0.06, SR),
            _silence(0.04, SR),
            _envelope(_sine(784, 0.14, SR), 0.003, 0.025, 0.38, 0.14, SR),
        )
        return s
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Boneshaker – short rattling noise + low square bursts, percussive skeleton
def _build_boneshaker(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        rattle = _concat(*[
            _concat(_envelope(_noise(0.03, SR), 0.001, 0.01, 0.5, 0.025, SR),
                    _silence(0.02, SR))
            for _ in range(4)
        ])
        bone = _concat(*[_envelope(_mix(_noise(0.04, SR), _square(f, 0.04, SR)),
                                   0.001, 0.015, 0.55, 0.04, SR)
                         for f in [196, 247, 294, 392]])
        return _concat(rattle, bone)
        return _concat(march, _silence(0.03, SR), crack)
        return s
        return s
    elif event == "level_up":
        s = _concat(*[
            _concat(_envelope(_mix(_noise(0.028, SR), _square(f, 0.028, SR)),
                              0.001, 0.01, 0.55, 0.025, SR), _silence(0.015, SR))
            for f in [110, 138, 165, 196, 247, 294, 370, 440, 554, 659]
        ])
        return s
    elif event == "countdown_tick":
        s = _mix(_noise(0.035, SR), _square(196, 0.035, SR))
        return _envelope([x * 0.45 for x in s], 0.001, 0.012, 0.42, 0.022, SR)
    elif event == "countdown_final":
        rattle = _concat(*[
            _concat(_envelope(_noise(0.025, SR), 0.001, 0.008, 0.5, 0.02, SR),
                    _silence(0.015, SR))
            for _ in range(3)
        ])
        boom = _envelope(_mix(_noise(0.1, SR), _square(110, 0.1, SR)),
                         0.001, 0.03, 0.55, 0.09, SR)
        return _concat(rattle, boom)
    elif event == "duel_received":
        rattle = _concat(*[
            _concat(_envelope(_noise(0.03, SR), 0.001, 0.01, 0.5, 0.025, SR), _silence(0.02, SR))
            for _ in range(3)
        ])
        bone = _concat(*[_envelope(_mix(_noise(0.04, SR), _square(f, 0.04, SR)),
                                   0.001, 0.015, 0.58, 0.04, SR)
                         for f in [147, 196, 247, 294, 370]])
        return _concat(rattle, _silence(0.02, SR), bone)
    elif event == "duel_accepted":
        s = _concat(*[_envelope(_mix(_noise(0.035, SR), _square(f, 0.035, SR)),
                                0.001, 0.012, 0.55, 0.03, SR)
                      for f in [196, 247, 294, 370]])
        return s
    elif event == "duel_won":
        s = _concat(*[_envelope(_mix(_noise(0.035, SR), _square(f, 0.035, SR)),
                                0.001, 0.012, 0.58, 0.03, SR)
                      for f in [147, 196, 247, 294, 370, 440, 554]])
        return s
    elif event == "duel_lost":
        s = _concat(*[_envelope(_mix(_noise(0.05, SR), _square(f, 0.05, SR)),
                                0.001, 0.018, 0.48, 0.045, SR)
                      for f in [370, 294, 247, 196, 147, 110]])
        return s
    elif event == "duel_expired":
        rattle = _concat(*[
            _concat(_envelope(_noise(0.02, SR), 0.001, 0.007, 0.42, 0.018, SR), _silence(0.015, SR))
            for _ in range(2)
        ])
        tail = _envelope(_mix(_noise(0.07, SR), _square(147, 0.07, SR)),
                         0.001, 0.02, 0.38, 0.07, SR)
        return _concat(rattle, tail)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Vex Machina – ring mod + metallic sweeps, steampunk gears
def _build_vex_machina(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _ring(_concat(_sweep(200, 800, 0.12, SR), _sine(800, 0.22, SR)), 320, SR)
        return _envelope(s, 0.005, 0.04, 0.68, 0.2, SR)
        return _envelope(s, 0.005, 0.04, 0.65, 0.18, SR)
        return _envelope(_concat(s, _ring(_sine(1600, 0.15, SR), 400, SR)),
                         0.008, 0.05, 0.7, 0.2, SR)
        return _envelope([x * 0.52 for x in s], 0.004, 0.05, 0.42, 0.26, SR)
    elif event == "level_up":
        s = _concat(
            _ring(_sweep(100, 600, 0.14, SR), 160, SR),
            _ring(_sweep(600, 1200, 0.12, SR), 240, SR),
            _ring(_sweep(1200, 2000, 0.1, SR), 320, SR),
            _mix(_ring(_sine(2000, 0.22, SR), 400, SR), _sine(1000, 0.22, SR)),
        )
        return _envelope(s, 0.008, 0.05, 0.72, 0.22, SR)
    elif event == "countdown_tick":
        s = _ring(_sine(440, 0.05, SR), 220, SR)
        return _envelope(s, 0.002, 0.018, 0.42, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(
            _ring(_sweep(300, 1400, 0.1, SR), 200, SR),
            _mix(_ring(_sine(1400, 0.2, SR), 350, SR), _sine(700, 0.2, SR)),
        )
        return _envelope(s, 0.004, 0.04, 0.72, 0.18, SR)
    elif event == "duel_received":
        gears = _concat(*[
            _ring(_sine(200 + i * 80, 0.065, SR), 100 + i * 40, SR)
            for i in range(3)
        ])
        flare1 = _ring(_sweep(200, 800, 0.1, SR), 200, SR)
        flare2 = _ring(_sweep(300, 1400, 0.18, SR), 260, SR)
        return _envelope(
            _concat(gears, _silence(0.04, SR), flare1, _silence(0.03, SR), flare2),
            0.005, 0.04, 0.68, 0.2, SR,
        )
    elif event == "duel_accepted":
        s = _concat(
            _ring(_sweep(300, 1000, 0.12, SR), 200, SR),
            _mix(_ring(_sine(1000, 0.18, SR), 280, SR), _sine(500, 0.18, SR)),
        )
        return _envelope(s, 0.005, 0.04, 0.65, 0.18, SR)
    elif event == "duel_won":
        s = _mix(
            _ring(_sweep(300, 1800, 0.25, SR), 240, SR),
            _ring(_sine(900, 0.25, SR), 320, SR),
        )
        return _envelope(_concat(s, _ring(_sine(1800, 0.2, SR), 420, SR)),
                         0.008, 0.05, 0.74, 0.22, SR)
    elif event == "duel_lost":
        s = _mix(_ring(_sweep(800, 60, 0.35, SR), 160, SR),
                 _ring(_noise(0.35, SR), 90, SR))
        return _envelope([x * 0.52 for x in s], 0.004, 0.05, 0.42, 0.3, SR)
    elif event == "duel_expired":
        s = _concat(
            _ring(_sine(600, 0.07, SR), 200, SR),
            _silence(0.04, SR),
            _ring(_sweep(600, 200, 0.2, SR), 140, SR),
        )
        return _envelope(s, 0.004, 0.04, 0.4, 0.22, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Stormfront Jake – wide dramatic sweeps + noise gusts, stormy western
def _build_stormfront_jake(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        gust = [s * 0.3 for s in _noise(0.12, SR)]
        s = _concat(
            _envelope(gust, 0.04, 0.08, 0.35, 0.08, SR),
            _envelope(_sweep(200, 1400, 0.22, SR), 0.01, 0.06, 0.65, 0.2, SR),
        )
        return s
        return s
        return _envelope(s, 0.01, 0.07, 0.65, 0.22, SR)
        return _envelope(s, 0.01, 0.07, 0.45, 0.3, SR)
    elif event == "level_up":
        gusts = _concat(
            _envelope([s * 0.3 for s in _noise(0.1, SR)], 0.04, 0.06, 0.3, 0.08, SR),
            _silence(0.03, SR),
            _envelope([s * 0.3 for s in _noise(0.1, SR)], 0.04, 0.06, 0.32, 0.08, SR),
            _silence(0.03, SR),
        )
        finale = _envelope(_mix(_sweep(200, 2000, 0.3, SR),
                                [x * 0.3 for x in _noise(0.3, SR)]),
                           0.01, 0.07, 0.68, 0.28, SR)
        return _concat(gusts, finale)
    elif event == "countdown_tick":
        s = _mix(_sweep(400, 200, 0.055, SR), [x * 0.2 for x in _noise(0.055, SR)])
        return _envelope(s, 0.002, 0.02, 0.42, 0.03, SR)
    elif event == "countdown_final":
        s = _mix(_sweep(200, 1400, 0.14, SR), [x * 0.3 for x in _noise(0.14, SR)])
        return _envelope(s, 0.01, 0.06, 0.7, 0.18, SR)
    elif event == "duel_received":
        gust1 = [s * 0.28 for s in _noise(0.1, SR)]
        gust2 = [s * 0.28 for s in _noise(0.1, SR)]
        s = _concat(
            _envelope(gust1, 0.04, 0.07, 0.3, 0.08, SR),
            _silence(0.03, SR),
            _envelope(gust2, 0.04, 0.07, 0.32, 0.08, SR),
            _silence(0.04, SR),
            _envelope(_mix(_sweep(150, 1200, 0.28, SR), [x * 0.25 for x in _noise(0.28, SR)]),
                      0.01, 0.07, 0.68, 0.24, SR),
        )
        return s
    elif event == "duel_accepted":
        wind = [s * 0.28 for s in _noise(0.14, SR)]
        s = _concat(
            _envelope(wind, 0.04, 0.08, 0.3, 0.1, SR),
            _silence(0.03, SR),
            _envelope(_sweep(200, 1000, 0.22, SR), 0.01, 0.06, 0.62, 0.2, SR),
        )
        return s
    elif event == "duel_won":
        s = _mix(
            _sweep(300, 1800, 0.28, SR),
            [x * 0.28 for x in _noise(0.28, SR)],
        )
        return _envelope(s, 0.01, 0.07, 0.68, 0.25, SR)
    elif event == "duel_lost":
        s = _mix(_sweep(1400, 80, 0.42, SR), [x * 0.38 for x in _noise(0.42, SR)])
        return _envelope(s, 0.01, 0.07, 0.42, 0.35, SR)
    elif event == "duel_expired":
        s = _mix(_sweep(500, 150, 0.22, SR), [x * 0.2 for x in _noise(0.22, SR)])
        return _envelope(s, 0.01, 0.06, 0.38, 0.22, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Nebula Drift – very long, slow tremolo/vibrato sine waves, deep ambient space
def _build_nebula_drift(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        low = _tremolo(_sine(110, 0.5, SR), 1.2, 0.55, SR)
        mid = _tremolo(_sine(220, 0.45, SR), 1.8, 0.45, SR)
        bright = _vibrato(_sine(880, 0.3, SR), 2, 8, SR)
        return _mix(
            _envelope(low, 0.08, 0.15, 0.5, 0.35, SR),
            _envelope(mid, 0.06, 0.12, 0.45, 0.3, SR),
            _envelope(bright, 0.04, 0.1, 0.6, 0.25, SR),
        )
        return _mix(
            _envelope(low, 0.07, 0.12, 0.48, 0.3, SR),
            _envelope(rise, 0.05, 0.1, 0.55, 0.28, SR),
        )
        return s
        return _envelope(s, 0.06, 0.12, 0.42, 0.38, SR)
    elif event == "level_up":
        layers = [
            _envelope(_tremolo(_sine(f, 0.55, SR), 1.0 + i * 0.3, 0.45, SR),
                      0.06 + i * 0.01, 0.12, 0.5, 0.4, SR)
            for i, f in enumerate([55, 110, 220, 440, 880])
        ]
        return _mix(*layers)
    elif event == "countdown_tick":
        return _envelope(_tremolo(_sine(440, 0.1, SR), 2, 0.35, SR), 0.008, 0.03, 0.42, 0.06, SR)
    elif event == "countdown_final":
        s = _mix(
            _envelope(_tremolo(_sine(220, 0.4, SR), 1.5, 0.5, SR), 0.05, 0.1, 0.55, 0.32, SR),
            _envelope(_vibrato(_sine(880, 0.32, SR), 2, 7, SR), 0.03, 0.08, 0.65, 0.28, SR),
        )
        return s
    elif event == "duel_received":
        low = _tremolo(_sine(130, 0.35, SR), 1.2, 0.5, SR)
        mid = _tremolo(_sine(260, 0.32, SR), 1.8, 0.45, SR)
        call = _vibrato(_sine(880, 0.22, SR), 2, 7, SR)
        call2 = _vibrato(_sine(1320, 0.2, SR), 2.2, 6, SR)
        return _mix(
            _envelope(low, 0.07, 0.12, 0.48, 0.28, SR),
            _envelope(mid, 0.06, 0.1, 0.45, 0.26, SR),
            _envelope(_concat(call, call2), 0.04, 0.1, 0.6, 0.25, SR),
        )
    elif event == "duel_accepted":
        low = _tremolo(_sine(130, 0.35, SR), 1.5, 0.48, SR)
        rise = _sweep(220, 700, 0.28, SR)
        return _mix(
            _envelope(low, 0.06, 0.12, 0.45, 0.28, SR),
            _envelope(rise, 0.04, 0.1, 0.55, 0.25, SR),
        )
    elif event == "duel_won":
        s = _mix(
            _envelope(_tremolo(_sine(110, 0.55, SR), 1.5, 0.5, SR), 0.07, 0.14, 0.55, 0.42, SR),
            _envelope(_vibrato(_sine(660, 0.45, SR), 2.5, 6, SR), 0.05, 0.12, 0.68, 0.36, SR),
            _envelope(_vibrato(_sine(1320, 0.35, SR), 3, 5, SR), 0.04, 0.1, 0.6, 0.28, SR),
        )
        return s
    elif event == "duel_lost":
        s = _mix(
            _tremolo(_sweep(440, 55, 0.55, SR), 1.2, 0.55, SR),
            _envelope(_sine(220, 0.5, SR), 0.05, 0.12, 0.4, 0.42, SR),
        )
        return _envelope(s, 0.06, 0.12, 0.4, 0.42, SR)
    elif event == "duel_expired":
        s = _mix(
            _envelope(_tremolo(_sine(220, 0.38, SR), 1.2, 0.45, SR), 0.05, 0.1, 0.38, 0.32, SR),
            _envelope(_vibrato(_sine(440, 0.3, SR), 2, 6, SR), 0.04, 0.08, 0.35, 0.28, SR),
        )
        return s
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Gideon's Clock – precise staccato square bursts, clockwork timing
def _build_gideons_clock(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        chime = _concat(*[
            _concat(_envelope(_square(f, 0.055, SR), 0.002, 0.02, 0.65, 0.06, SR),
                    _silence(0.03, SR))
            for f in [659, 784, 880, 988, 1175, 1319]
        ])
        return chime
        return _concat(ticks, _silence(0.03, SR), alarm)
        return chime
        return s
    elif event == "level_up":
        chime = _concat(*[
            _concat(_envelope(_square(f, 0.045, SR), 0.001, 0.015, 0.72, 0.05, SR),
                    _silence(0.02, SR))
            for f in [392, 440, 494, 523, 587, 659, 698, 784, 880, 988, 1047, 1175]
        ])
        return chime
    elif event == "countdown_tick":
        return _envelope(_square(784, 0.032, SR), 0.001, 0.01, 0.52, 0.022, SR)
    elif event == "countdown_final":
        chime = _concat(*[
            _concat(_envelope(_square(f, 0.05, SR), 0.001, 0.018, 0.72, 0.055, SR),
                    _silence(0.02, SR))
            for f in [880, 1047, 1319]
        ])
        return chime
    elif event == "duel_received":
        alarm = _concat(*[
            _concat(_envelope(_square(784, 0.04, SR), 0.001, 0.014, 0.6, 0.035, SR),
                    _silence(0.04, SR))
            for _ in range(3)
        ])
        chime = _concat(*[
            _concat(_envelope(_square(f, 0.05, SR), 0.001, 0.018, 0.68, 0.055, SR),
                    _silence(0.025, SR))
            for f in [523, 659, 784, 988]
        ])
        return _concat(alarm, _silence(0.03, SR), chime)
    elif event == "duel_accepted":
        chime = _concat(*[
            _concat(_envelope(_square(f, 0.05, SR), 0.001, 0.018, 0.65, 0.055, SR),
                    _silence(0.025, SR))
            for f in [659, 784, 880, 1047]
        ])
        return chime
    elif event == "duel_won":
        chime = _concat(*[
            _concat(_envelope(_square(f, 0.05, SR), 0.001, 0.018, 0.72, 0.055, SR),
                    _silence(0.022, SR))
            for f in [523, 659, 784, 880, 988, 1175, 1319, 1568]
        ])
        return chime
    elif event == "duel_lost":
        s = _concat(*[
            _concat(_envelope(_square(f, 0.06, SR), 0.001, 0.022, 0.52, 0.06, SR),
                    _silence(0.038, SR))
            for f in [659, 587, 523, 466, 392, 330]
        ])
        return s
    elif event == "duel_expired":
        s = _concat(
            _envelope(_square(523, 0.06, SR), 0.001, 0.022, 0.52, 0.06, SR),
            _silence(0.05, SR),
            _envelope(_square(392, 0.14, SR), 0.001, 0.03, 0.4, 0.14, SR),
        )
        return s
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Sapphire Specter – soft vibrato sine, high harmonic shimmer, spectral beauty
def _build_sapphire_specter(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        shimmer = _concat(*[
            _envelope(_vibrato(_mix(_sine(f, 0.1, SR), _sine(f * 2, 0.1, SR)), 4, 5, SR),
                      0.01, 0.04, 0.62, 0.12, SR)
            for f in [784, 988, 1175, 1568, 1975]
        ])
        return shimmer
        return _concat(s, _silence(0.03, SR), sustain)
        return s
        return s
    elif event == "level_up":
        s = _concat(*[
            _envelope(_vibrato(_mix(_sine(f, 0.08, SR), _sine(f * 2, 0.08, SR)), 4, 4, SR),
                      0.007, 0.03, 0.68, 0.1, SR)
            for f in [330, 415, 494, 659, 784, 988, 1175, 1319, 1568, 1975]
        ])
        return s
    elif event == "countdown_tick":
        s = _vibrato(_mix(_sine(1047, 0.048, SR), _sine(2093, 0.048, SR)), 5, 3, SR)
        return _envelope(s, 0.002, 0.018, 0.45, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_vibrato(_mix(_sine(f, 0.09, SR), _sine(f * 2, 0.09, SR)), 4, 5, SR),
                      0.006, 0.03, 0.68, 0.1, SR)
            for f in [880, 1108, 1319]
        ])
        return s
    elif event == "duel_received":
        call = _concat(*[
            _envelope(_vibrato(_sine(f, 0.1, SR), 3, 4, SR), 0.01, 0.04, 0.6, 0.12, SR)
            for f in [494, 659, 784]
        ])
        call2 = _concat(*[
            _envelope(_vibrato(_mix(_sine(f, 0.1, SR), _sine(f * 2, 0.1, SR)), 3.5, 5, SR),
                      0.01, 0.04, 0.65, 0.12, SR)
            for f in [494, 659, 784, 988]
        ])
        return _concat(call, _silence(0.04, SR), call2)
    elif event == "duel_accepted":
        s = _concat(*[
            _envelope(_vibrato(_mix(_sine(f, 0.1, SR), _sine(f * 2, 0.1, SR)), 3.5, 4, SR),
                      0.01, 0.04, 0.62, 0.12, SR)
            for f in [659, 784, 988, 1175]
        ])
        return s
    elif event == "duel_won":
        s = _concat(*[
            _envelope(_vibrato(_mix(_sine(f, 0.09, SR), _sine(f * 2, 0.09, SR)), 4, 4, SR),
                      0.008, 0.035, 0.7, 0.1, SR)
            for f in [523, 659, 784, 988, 1175, 1319, 1568, 1975]
        ])
        return s
    elif event == "duel_lost":
        s = _concat(*[
            _envelope(_vibrato(_sine(f, 0.12, SR), 3, 5, SR), 0.01, 0.04, 0.48, 0.12, SR)
            for f in [988, 784, 659, 523, 415, 330]
        ])
        return s
    elif event == "duel_expired":
        s = _concat(
            _envelope(_vibrato(_mix(_sine(784, 0.08, SR), _sine(1568, 0.08, SR)), 4, 4, SR),
                      0.008, 0.03, 0.48, 0.1, SR),
            _silence(0.04, SR),
            _envelope(_vibrato(_sine(494, 0.18, SR), 3, 4, SR), 0.01, 0.05, 0.35, 0.18, SR),
        )
        return s
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Molten Core – deep low rumbling sweeps, industrial, heavy
def _build_molten_core(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        rumble = _tremolo(_mix(_sine(55, 0.35, SR), _sine(110, 0.35, SR)), 2.5, 0.6, SR)
        rise = _sweep(80, 600, 0.25, SR)
        return _mix(
            _envelope(rumble, 0.06, 0.12, 0.48, 0.3, SR),
            _envelope(rise, 0.02, 0.08, 0.6, 0.22, SR),
        )
        return _concat(
            _envelope(rumble, 0.05, 0.1, 0.45, 0.25, SR),
            _silence(0.04, SR),
            _envelope(slam, 0.01, 0.06, 0.6, 0.18, SR),
        )
        return _envelope(s, 0.05, 0.12, 0.55, 0.32, SR)
        return _envelope(s, 0.04, 0.1, 0.42, 0.38, SR)
    elif event == "level_up":
        layers = [
            _envelope(_tremolo(_sine(f, 0.5, SR), 2.0 + i * 0.2, 0.55, SR),
                      0.05, 0.12, 0.5, 0.38, SR)
            for i, f in enumerate([40, 55, 80, 110, 220])
        ]
        sweep_layer = _envelope(_sweep(80, 1200, 0.4, SR), 0.03, 0.1, 0.58, 0.32, SR)
        return _mix(*layers, sweep_layer)
    elif event == "countdown_tick":
        s = _mix(_sine(80, 0.06, SR), [x * 0.2 for x in _noise(0.06, SR)])
        return _envelope(s, 0.002, 0.02, 0.48, 0.04, SR)
    elif event == "countdown_final":
        s = _mix(
            _tremolo(_sine(55, 0.38, SR), 2, 0.55, SR),
            _sweep(100, 700, 0.28, SR),
        )
        return _envelope(s, 0.04, 0.1, 0.58, 0.3, SR)
    elif event == "duel_received":
        rumble1 = _tremolo(_mix(_sine(55, 0.22, SR), _sine(110, 0.22, SR)), 2.5, 0.55, SR)
        rumble2 = _tremolo(_mix(_sine(55, 0.22, SR), _sine(110, 0.22, SR)), 2.5, 0.55, SR)
        rise = _sweep(80, 700, 0.28, SR)
        return _concat(
            _envelope(rumble1, 0.05, 0.1, 0.45, 0.2, SR),
            _silence(0.04, SR),
            _envelope(rumble2, 0.05, 0.1, 0.45, 0.2, SR),
            _silence(0.04, SR),
            _envelope(rise, 0.02, 0.08, 0.65, 0.25, SR),
        )
    elif event == "duel_accepted":
        rumble = _tremolo(_sine(60, 0.3, SR), 2, 0.5, SR)
        slam = _mix(_sweep(100, 500, 0.2, SR), [x * 0.28 for x in _noise(0.2, SR)])
        return _concat(
            _envelope(rumble, 0.05, 0.1, 0.42, 0.24, SR),
            _silence(0.03, SR),
            _envelope(slam, 0.01, 0.06, 0.6, 0.18, SR),
        )
    elif event == "duel_won":
        s = _mix(
            _tremolo(_sine(55, 0.5, SR), 2, 0.55, SR),
            _sweep(100, 1000, 0.35, SR),
            _envelope(_sine(400, 0.32, SR), 0.02, 0.08, 0.58, 0.26, SR),
        )
        return _envelope(s, 0.05, 0.12, 0.58, 0.36, SR)
    elif event == "duel_lost":
        s = _mix(
            _tremolo(_sweep(350, 40, 0.5, SR), 2, 0.6, SR),
            [x * 0.3 for x in _noise(0.5, SR)],
        )
        return _envelope(s, 0.04, 0.1, 0.42, 0.42, SR)
    elif event == "duel_expired":
        s = _mix(
            _tremolo(_sine(55, 0.3, SR), 2, 0.5, SR),
            _sweep(100, 50, 0.22, SR),
        )
        return _envelope(s, 0.04, 0.1, 0.38, 0.28, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Zigzag Bandit – rapidly alternating high/low square notes, erratic and fun
def _build_zigzag_bandit(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        zz = _concat(*[_square(880 if i % 2 == 0 else 440, 0.04, SR) for i in range(8)])
        s = _concat(zz, _square(1760, 0.18, SR))
        return _envelope(s, 0.002, 0.02, 0.72, 0.12, SR)
        return _envelope(s, 0.002, 0.02, 0.68, 0.15, SR)
        return _envelope(s, 0.002, 0.018, 0.75, 0.12, SR)
        return _envelope(zz, 0.002, 0.02, 0.62, 0.15, SR)
    elif event == "level_up":
        pairs = [(330, 660), (392, 784), (440, 880), (494, 988),
                 (523, 1046), (587, 1175), (659, 1319), (784, 1568)]
        zz = _concat(*[_square(hi if i % 2 == 0 else lo, 0.035, SR)
                       for lo, hi in pairs for i in range(2)])
        return _envelope(zz, 0.002, 0.015, 0.8, 0.18, SR)
    elif event == "countdown_tick":
        s = _concat(_square(880, 0.02, SR), _square(440, 0.02, SR))
        return _envelope(s, 0.001, 0.008, 0.55, 0.02, SR)
    elif event == "countdown_final":
        zz = _concat(*[_square(1319 if i % 2 == 0 else 659, 0.04, SR) for i in range(4)])
        s = _concat(zz, _square(2637, 0.14, SR))
        return _envelope(s, 0.001, 0.015, 0.78, 0.12, SR)
    elif event == "duel_received":
        zz1 = _concat(*[_square(880 if i % 2 == 0 else 330, 0.035, SR) for i in range(6)])
        zz2 = _concat(*[_square(1046 if i % 2 == 0 else 440, 0.032, SR) for i in range(8)])
        s = _concat(zz1, _silence(0.03, SR), zz2, _square(1760, 0.12, SR))
        return _envelope(s, 0.002, 0.02, 0.75, 0.12, SR)
    elif event == "duel_accepted":
        zz = _concat(*[_square(880 if i % 2 == 0 else 440, 0.042, SR) for i in range(6)])
        s = _concat(zz, _square(1760, 0.14, SR))
        return _envelope(s, 0.002, 0.02, 0.7, 0.12, SR)
    elif event == "duel_won":
        zz = _concat(*[_square(1319 if i % 2 == 0 else 659, 0.035, SR) for i in range(12)])
        s = _concat(zz, _square(2637, 0.18, SR))
        return _envelope(s, 0.002, 0.018, 0.8, 0.15, SR)
    elif event == "duel_lost":
        zz = _concat(*[_square(440 if i % 2 == 0 else 220, 0.06, SR) for i in range(8)])
        return _envelope(zz, 0.002, 0.022, 0.58, 0.18, SR)
    elif event == "duel_expired":
        s = _concat(_square(660, 0.05, SR), _square(330, 0.05, SR),
                    _silence(0.04, SR), _square(440, 0.14, SR))
        return _envelope(s, 0.002, 0.02, 0.42, 0.18, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Wildcat Hollow – warm sine + mild crackle, rustic country charm
def _build_wildcat_hollow(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        twang = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.5, 0.09, SR)), 0.005, 0.03, 0.62, 0.12, SR)
            for f in [392, 494, 587, 784, 988]
        ])
        total_dur = 5 * (0.09 + 0.12)
        cr_n = int(total_dur * SR)
        cr = [s * 0.12 for s in _crackle(total_dur, SR)]
        tw_n = len(twang)
        cr = (cr + [0.0] * tw_n)[:tw_n]
        return _mix(twang, cr)
        return _concat(drum, _silence(0.04, SR), call)
        return s
        return s
    elif event == "level_up":
        notes = [262, 330, 392, 494, 587, 659, 784, 880, 1046, 1319]
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.07, SR), _sine(f * 1.25, 0.07, SR),
                           _sine(f * 1.5, 0.07, SR)), 0.004, 0.025, 0.7, 0.09, SR)
            for f in notes
        ])
        return s
    elif event == "countdown_tick":
        return _envelope(_sine(440, 0.045, SR), 0.002, 0.016, 0.42, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.25, 0.08, SR)),
                      0.004, 0.028, 0.68, 0.1, SR)
            for f in [659, 784, 988]
        ])
        return s
    elif event == "duel_received":
        call1 = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.25, 0.09, SR)),
                      0.005, 0.03, 0.6, 0.1, SR)
            for f in [330, 440, 523]
        ])
        call2 = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.5, 0.09, SR)),
                      0.005, 0.03, 0.65, 0.1, SR)
            for f in [330, 440, 523, 659]
        ])
        cr = [s * 0.1 for s in _crackle(len(call1) / SR, SR)]
        cr = (cr + [0.0] * len(call1))[:len(call1)]
        return _concat(_mix(call1, cr), _silence(0.03, SR), call2)
    elif event == "duel_accepted":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.25, 0.09, SR)),
                      0.005, 0.03, 0.62, 0.1, SR)
            for f in [392, 523, 659, 784]
        ])
        return s
    elif event == "duel_won":
        notes = [330, 440, 523, 659, 784, 988, 1175]
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.5, 0.08, SR),
                           _sine(f * 1.25, 0.08, SR)), 0.005, 0.025, 0.68, 0.1, SR)
            for f in notes
        ])
        return s
    elif event == "duel_lost":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.1, SR), _sine(f * 0.5, 0.1, SR)),
                      0.006, 0.04, 0.46, 0.12, SR)
            for f in [392, 330, 277, 220, 165]
        ])
        return s
    elif event == "duel_expired":
        s = _concat(
            _envelope(_mix(_sine(440, 0.08, SR), _sine(550, 0.08, SR)),
                      0.005, 0.03, 0.48, 0.1, SR),
            _silence(0.04, SR),
            _envelope(_mix(_sine(330, 0.16, SR), _sine(247, 0.16, SR)),
                      0.005, 0.04, 0.35, 0.18, SR),
        )
        return s
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# Crimson Flare – ring mod dramatic rises, intense cinematic build-up
def _build_crimson_flare(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(
            _ring(_sweep(200, 1200, 0.14, SR), 130, SR),
            _mix(_ring(_sine(1200, 0.25, SR), 260, SR), _sine(600, 0.25, SR)),
        )
        return _envelope(s, 0.01, 0.05, 0.7, 0.22, SR)
        return _envelope(_concat(build, _silence(0.04, SR), flare),
                         0.008, 0.05, 0.67, 0.18, SR)
        return _envelope(_concat(s, _ring(_sine(1800, 0.18, SR), 400, SR)),
                         0.01, 0.05, 0.72, 0.2, SR)
        return _envelope([x * 0.52 for x in s], 0.005, 0.05, 0.42, 0.28, SR)
    elif event == "level_up":
        s = _concat(
            _ring(_sweep(100, 600, 0.13, SR), 110, SR),
            _ring(_sweep(600, 1200, 0.11, SR), 180, SR),
            _ring(_sweep(1200, 2000, 0.09, SR), 260, SR),
            _mix(_ring(_sine(2000, 0.25, SR), 360, SR), _sine(1000, 0.25, SR)),
        )
        return _envelope(s, 0.01, 0.05, 0.75, 0.22, SR)
    elif event == "countdown_tick":
        s = _ring(_sine(550, 0.052, SR), 180, SR)
        return _envelope(s, 0.002, 0.018, 0.42, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(
            _ring(_sweep(250, 1600, 0.12, SR), 160, SR),
            _mix(_ring(_sine(1600, 0.22, SR), 320, SR), _sine(800, 0.22, SR)),
        )
        return _envelope(s, 0.006, 0.05, 0.74, 0.2, SR)
    elif event == "duel_received":
        build1 = _concat(*[
            _ring(_sine(200 + i * 100, 0.065, SR), 80 + i * 45, SR)
            for i in range(3)
        ])
        build2 = _concat(*[
            _ring(_sine(200 + i * 100, 0.065, SR), 90 + i * 50, SR)
            for i in range(4)
        ])
        flare = _ring(_sweep(400, 1600, 0.22, SR), 200, SR)
        return _envelope(
            _concat(build1, _silence(0.03, SR), build2, _silence(0.04, SR), flare),
            0.008, 0.05, 0.72, 0.2, SR,
        )
    elif event == "duel_accepted":
        s = _concat(
            _ring(_sweep(250, 1000, 0.13, SR), 140, SR),
            _mix(_ring(_sine(1000, 0.2, SR), 230, SR), _sine(500, 0.2, SR)),
        )
        return _envelope(s, 0.008, 0.05, 0.67, 0.2, SR)
    elif event == "duel_won":
        s = _mix(
            _ring(_sweep(300, 2000, 0.26, SR), 240, SR),
            _ring(_sine(1000, 0.26, SR), 320, SR),
        )
        return _envelope(_concat(s, _ring(_sine(2000, 0.22, SR), 450, SR)),
                         0.01, 0.05, 0.76, 0.22, SR)
    elif event == "duel_lost":
        s = _mix(
            _ring(_sweep(1400, 80, 0.38, SR), 170, SR),
            _ring(_noise(0.38, SR), 90, SR),
        )
        return _envelope([x * 0.52 for x in s], 0.005, 0.05, 0.42, 0.32, SR)
    elif event == "duel_expired":
        s = _concat(
            _ring(_sine(700, 0.07, SR), 200, SR),
            _silence(0.04, SR),
            _ring(_sweep(700, 220, 0.22, SR), 140, SR),
        )
        return _envelope(s, 0.006, 0.04, 0.4, 0.24, SR)
    elif event == "duel_declined":
        s = _concat(_square(370, 0.06, SR), _silence(0.03, SR), _square(277, 0.1, SR))
        return _envelope(s, 0.002, 0.02, 0.35, 0.12, SR)


# ── Pack registry ─────────────────────────────────────────────────────────────

_PACK_BUILDERS = {
    "zaptron":          _build_zaptron,
    "iron_basilisk":    _build_iron_basilisk,
    "voodoo_swamp":     _build_voodoo_swamp,
    "pixel_ghost":      _build_pixel_ghost,
    "solar_drift":      _build_solar_drift,
    "rokos_lair":       _build_rokos_lair,
    "thunderclap_rex":  _build_thunderclap_rex,
    "frostbite_hollow": _build_frostbite_hollow,
    "ratchet_circus":   _build_ratchet_circus,
    "lucky_stardust":   _build_lucky_stardust,
    "boneshaker":       _build_boneshaker,
    "vex_machina":      _build_vex_machina,
    "stormfront_jake":  _build_stormfront_jake,
    "nebula_drift":     _build_nebula_drift,
    "gideons_clock":    _build_gideons_clock,
    "sapphire_specter": _build_sapphire_specter,
    "molten_core":      _build_molten_core,
    "zigzag_bandit":    _build_zigzag_bandit,
    "wildcat_hollow":   _build_wildcat_hollow,
    "crimson_flare":    _build_crimson_flare,
}


# ── Volume / cache / playback ─────────────────────────────────────────────────

def _volume_scale(cfg_volume) -> float:
    try:
        v = int(cfg_volume)
    except (TypeError, ValueError):
        v = DEFAULT_VOLUME
    return max(0.0, min(1.0, v / 100.0))


@lru_cache(maxsize=256)
def _get_wav(pack_id: str, event: str, volume: int) -> bytes:
    builder = _PACK_BUILDERS.get(pack_id) or _PACK_BUILDERS["zaptron"]
    samples = builder(event)
    scale = _volume_scale(volume)
    if scale != 1.0:
        samples = [s * scale for s in samples]
    return _make_wav(samples)


def _play_raw(wav_bytes: bytes) -> None:
    try:
        import winsound

        def _play():
            try:
                winsound.PlaySound(
                    wav_bytes,
                    winsound.SND_MEMORY | winsound.SND_NODEFAULT,
                )
            except Exception:
                pass

        t = threading.Thread(target=_play, daemon=True)
        t.start()
    except ImportError:
        pass


def _resolve_pack_id(ov: dict) -> str:
    pack_id = str(ov.get("sound_pack", "zaptron")).strip()
    if pack_id not in _PACK_BUILDERS:
        pack_id = "zaptron"
    return pack_id


def play_sound(cfg, event_name: str) -> None:
    """Play a sound if the feature is enabled and the event is not muted."""
    try:
        ov = getattr(cfg, "OVERLAY", {}) or {}
        if not bool(ov.get("sound_enabled", False)):
            return
        events = ov.get("sound_events") or {}
        if isinstance(events, dict) and not bool(events.get(event_name, False)):
            return
        pack_id = _resolve_pack_id(ov)
        volume = int(ov.get("sound_volume", DEFAULT_VOLUME))
        wav = _get_wav(pack_id, event_name, volume)
        _play_raw(wav)
    except Exception:
        pass


def play_sound_preview(cfg, event_name: str) -> None:
    """Play a sound preview regardless of enabled/muted state (for Test buttons)."""
    try:
        ov = getattr(cfg, "OVERLAY", {}) or {}
        pack_id = _resolve_pack_id(ov)
        volume = int(ov.get("sound_volume", DEFAULT_VOLUME))
        wav = _get_wav(pack_id, event_name, volume)
        _play_raw(wav)
    except Exception:
        pass
