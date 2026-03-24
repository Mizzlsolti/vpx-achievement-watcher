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
DEFAULT_VOLUME = 70

# ── Public metadata ───────────────────────────────────────────────────────────

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
    ("achievement_rare",   "💎 Rare Achievement"),
    ("challenge_start",    "⚔️ Challenge Start"),
    ("challenge_complete", "✅ Challenge Complete"),
    ("challenge_fail",     "❌ Challenge Fail"),
    ("level_up",           "⬆️ Level Up"),
    ("toast_info",         "ℹ️ Toast Info"),
    ("toast_warning",      "⚠️ Toast Warning"),
    ("countdown_tick",     "🕐 Countdown Tick"),
    ("countdown_final",    "🔔 Countdown Final"),
    ("personal_best",      "🌟 Personal Best"),
    ("combo",              "🔥 Combo"),
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

def _build_arcade(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        return _envelope(_concat(
            _square(440, 0.08, SR), _square(554, 0.08, SR),
            _square(659, 0.08, SR), _square(880, 0.18, SR),
        ), 0.01, 0.05, 0.7, 0.12, SR)
    elif event == "achievement_rare":
        s = _concat(*[_square(f, 0.06, SR)
                      for f in [440, 494, 554, 622, 659, 740, 880, 988]])
        return _envelope(s, 0.01, 0.04, 0.7, 0.18, SR)
    elif event == "challenge_start":
        return _envelope(_concat(
            _square(220, 0.09, SR), _square(330, 0.09, SR),
            _silence(0.04, SR), _square(440, 0.22, SR),
        ), 0.01, 0.07, 0.6, 0.12, SR)
    elif event == "challenge_complete":
        return _envelope(_concat(
            _square(523, 0.09, SR), _square(659, 0.09, SR),
            _square(784, 0.09, SR), _square(1046, 0.22, SR),
        ), 0.01, 0.05, 0.7, 0.15, SR)
    elif event == "challenge_fail":
        return _envelope(_concat(
            _square(440, 0.1, SR), _square(330, 0.1, SR),
            _square(220, 0.18, SR),
        ), 0.01, 0.05, 0.5, 0.18, SR)
    elif event == "level_up":
        freqs = [262, 294, 330, 349, 392, 440, 494, 523]
        s = _concat(*[_square(f, 0.07, SR) for f in freqs])
        return _envelope(s, 0.01, 0.04, 0.8, 0.2, SR)
    elif event == "toast_info":
        return _envelope(_square(880, 0.1, SR), 0.01, 0.05, 0.5, 0.1, SR)
    elif event == "toast_warning":
        return _envelope(_concat(
            _square(660, 0.09, SR), _silence(0.04, SR),
            _square(660, 0.09, SR),
        ), 0.01, 0.03, 0.6, 0.1, SR)
    elif event == "countdown_tick":
        return _envelope(_square(440, 0.05, SR), 0.005, 0.02, 0.4, 0.03, SR)
    elif event == "countdown_final":
        return _envelope(_concat(
            _square(880, 0.1, SR), _square(1100, 0.18, SR),
        ), 0.005, 0.04, 0.7, 0.12, SR)
    elif event == "personal_best":
        s = _concat(
            _square(523, 0.08, SR), _square(659, 0.08, SR),
            _square(784, 0.08, SR), _silence(0.04, SR),
            _square(784, 0.08, SR), _square(1046, 0.22, SR),
        )
        return _envelope(s, 0.01, 0.05, 0.8, 0.18, SR)
    else:  # combo
        s = _concat(*[_square(f, 0.05, SR) for f in [330, 415, 523, 622, 784]])
        return _envelope(s, 0.005, 0.03, 0.7, 0.08, SR)


def _build_subtle(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        return _envelope(_concat(
            _sine(523, 0.1, SR), _sine(659, 0.1, SR), _sine(784, 0.2, SR),
        ), 0.02, 0.08, 0.6, 0.2, SR)
    elif event == "achievement_rare":
        base = _sine(880, 0.35, SR)
        mod = _tremolo(base, 8.0, 0.3, SR)
        return _envelope(mod, 0.03, 0.1, 0.6, 0.2, SR)
    elif event == "challenge_start":
        return _envelope(_concat(
            _sine(392, 0.12, SR), _sine(523, 0.18, SR),
        ), 0.02, 0.07, 0.6, 0.15, SR)
    elif event == "challenge_complete":
        return _envelope(_concat(
            _sine(523, 0.1, SR), _sine(659, 0.1, SR), _sine(784, 0.2, SR),
        ), 0.02, 0.07, 0.65, 0.2, SR)
    elif event == "challenge_fail":
        return _envelope(_concat(
            _sine(392, 0.12, SR), _sine(294, 0.2, SR),
        ), 0.02, 0.08, 0.5, 0.2, SR)
    elif event == "level_up":
        s = _concat(*[_sine(f, 0.08, SR) for f in [262, 330, 392, 523, 659, 784]])
        return _envelope(s, 0.02, 0.06, 0.7, 0.25, SR)
    elif event == "toast_info":
        return _envelope(_sine(784, 0.12, SR), 0.02, 0.06, 0.5, 0.12, SR)
    elif event == "toast_warning":
        return _envelope(_concat(
            _sine(523, 0.1, SR), _silence(0.05, SR), _sine(523, 0.1, SR),
        ), 0.01, 0.04, 0.6, 0.1, SR)
    elif event == "countdown_tick":
        return _envelope(_sine(660, 0.06, SR), 0.005, 0.025, 0.4, 0.03, SR)
    elif event == "countdown_final":
        return _envelope(_sine(880, 0.22, SR), 0.01, 0.06, 0.7, 0.15, SR)
    elif event == "personal_best":
        s = _concat(
            _sine(523, 0.08, SR), _sine(659, 0.08, SR),
            _sine(784, 0.08, SR), _sine(1046, 0.25, SR),
        )
        return _envelope(s, 0.02, 0.07, 0.75, 0.25, SR)
    else:  # combo
        s = _concat(*[_sine(f, 0.06, SR) for f in [392, 494, 587, 740]])
        return _envelope(s, 0.01, 0.04, 0.65, 0.1, SR)


def _build_sci_fi(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _sweep(300, 1200, 0.18, SR)
        s2 = _sine(880, 0.2, SR)
        return _envelope(_concat(s, s2), 0.01, 0.06, 0.65, 0.15, SR)
    elif event == "achievement_rare":
        s = _mix(_sweep(200, 2000, 0.4, SR), _sine(440, 0.4, SR))
        return _envelope(_tremolo(s, 12, 0.25, SR), 0.02, 0.08, 0.65, 0.2, SR)
    elif event == "challenge_start":
        s = _concat(_sweep(100, 600, 0.15, SR), _silence(0.04, SR), _sine(600, 0.2, SR))
        return _envelope(s, 0.01, 0.06, 0.6, 0.15, SR)
    elif event == "challenge_complete":
        s = _concat(_sweep(400, 1200, 0.15, SR), _sine(1200, 0.2, SR))
        return _envelope(s, 0.01, 0.05, 0.7, 0.18, SR)
    elif event == "challenge_fail":
        s = _sweep(800, 100, 0.3, SR)
        return _envelope(s, 0.01, 0.05, 0.55, 0.2, SR)
    elif event == "level_up":
        s = _concat(_sweep(200, 800, 0.2, SR), _sweep(800, 1600, 0.15, SR), _sine(1200, 0.2, SR))
        return _envelope(s, 0.01, 0.06, 0.75, 0.2, SR)
    elif event == "toast_info":
        s = _sweep(600, 900, 0.12, SR)
        return _envelope(s, 0.01, 0.05, 0.5, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(_sweep(400, 700, 0.1, SR), _silence(0.04, SR), _sweep(400, 700, 0.1, SR))
        return _envelope(s, 0.01, 0.04, 0.6, 0.12, SR)
    elif event == "countdown_tick":
        return _envelope(_sweep(600, 400, 0.06, SR), 0.005, 0.02, 0.4, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(_sweep(300, 1200, 0.1, SR), _sine(1200, 0.18, SR))
        return _envelope(s, 0.01, 0.04, 0.7, 0.15, SR)
    elif event == "personal_best":
        s = _concat(
            _sweep(200, 1000, 0.15, SR), _silence(0.03, SR),
            _sweep(500, 1500, 0.12, SR), _sine(1200, 0.22, SR),
        )
        return _envelope(s, 0.01, 0.05, 0.75, 0.2, SR)
    else:  # combo
        s = _concat(*[_sweep(f, f * 1.5, 0.05, SR) for f in [300, 400, 500, 600, 700]])
        return _envelope(s, 0.005, 0.03, 0.65, 0.1, SR)


def _build_retro_8bit(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(*[_square(f, 0.07, SR) for f in [523, 659, 784, 1046]])
        n = _mix(_envelope(s, 0.005, 0.04, 0.7, 0.12, SR),
                 _envelope(_concat(*[_square(f * 2, 0.07, SR) for f in [523, 659, 784, 1046]]),
                            0.005, 0.04, 0.3, 0.12, SR))
        return n
    elif event == "achievement_rare":
        s = _concat(*[_square(f, 0.055, SR) for f in [440, 494, 554, 622, 698, 784, 880, 988, 1108]])
        return _envelope(s, 0.005, 0.03, 0.75, 0.18, SR)
    elif event == "challenge_start":
        s = _concat(_square(220, 0.07, SR), _silence(0.03, SR),
                    _square(294, 0.07, SR), _silence(0.03, SR),
                    _square(440, 0.18, SR))
        return _envelope(s, 0.005, 0.04, 0.65, 0.12, SR)
    elif event == "challenge_complete":
        s = _concat(*[_square(f, 0.07, SR) for f in [392, 523, 659, 784, 1046]])
        return _envelope(s, 0.005, 0.04, 0.72, 0.15, SR)
    elif event == "challenge_fail":
        s = _concat(*[_square(f, 0.09, SR) for f in [440, 370, 311, 220]])
        return _envelope(s, 0.005, 0.04, 0.55, 0.18, SR)
    elif event == "level_up":
        freqs = [262, 294, 330, 392, 440, 494, 523, 587, 659, 784]
        s = _concat(*[_square(f, 0.06, SR) for f in freqs])
        return _envelope(s, 0.005, 0.03, 0.8, 0.2, SR)
    elif event == "toast_info":
        return _envelope(_square(880, 0.08, SR), 0.005, 0.03, 0.5, 0.08, SR)
    elif event == "toast_warning":
        s = _concat(_square(660, 0.07, SR), _silence(0.04, SR), _square(880, 0.07, SR))
        return _envelope(s, 0.005, 0.03, 0.6, 0.1, SR)
    elif event == "countdown_tick":
        return _envelope(_square(440, 0.04, SR), 0.002, 0.015, 0.45, 0.025, SR)
    elif event == "countdown_final":
        s = _concat(_square(880, 0.08, SR), _square(1108, 0.15, SR))
        return _envelope(s, 0.002, 0.03, 0.72, 0.12, SR)
    elif event == "personal_best":
        s = _concat(
            *[_square(f, 0.06, SR) for f in [523, 659, 784, 880, 1046]],
            _silence(0.04, SR),
            *[_square(f, 0.06, SR) for f in [523, 659, 784, 880, 1046]],
        )
        return _envelope(s, 0.005, 0.03, 0.8, 0.2, SR)
    else:  # combo
        s = _concat(*[_square(f, 0.045, SR) for f in [330, 440, 523, 660, 784, 880]])
        return _envelope(s, 0.002, 0.025, 0.68, 0.08, SR)


def _build_pinball_classic(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        bump = _mix(_sine(220, 0.06, SR), _noise(0.06, SR))
        bump = [s * 0.4 for s in bump]
        s = _concat(
            _envelope(bump, 0.002, 0.03, 0.4, 0.05, SR),
            _silence(0.02, SR),
            _envelope(_sine(880, 0.18, SR), 0.01, 0.06, 0.6, 0.18, SR),
        )
        return s
    elif event == "achievement_rare":
        chime = _concat(*[
            _envelope(_sine(f, 0.12, SR), 0.005, 0.05, 0.6, 0.1, SR)
            for f in [784, 988, 1175, 1568]
        ])
        return chime
    elif event == "challenge_start":
        flipper = _mix(_sine(80, 0.1, SR), _noise(0.1, SR))
        flipper = [s * 0.5 for s in flipper]
        s = _concat(
            _envelope(flipper, 0.005, 0.04, 0.5, 0.08, SR),
            _silence(0.03, SR),
            _envelope(_sine(660, 0.2, SR), 0.01, 0.06, 0.65, 0.15, SR),
        )
        return s
    elif event == "challenge_complete":
        s = _concat(*[
            _envelope(_sine(f, 0.1, SR), 0.005, 0.05, 0.65, 0.1, SR)
            for f in [523, 659, 784, 1046]
        ])
        return s
    elif event == "challenge_fail":
        drain = _mix(_sweep(300, 60, 0.25, SR), _noise(0.25, SR))
        drain = [s * 0.4 for s in drain]
        return _envelope(drain, 0.005, 0.05, 0.4, 0.2, SR)
    elif event == "level_up":
        s = _concat(*[
            _envelope(_sine(f, 0.09, SR), 0.005, 0.04, 0.7, 0.1, SR)
            for f in [392, 494, 587, 698, 784, 988]
        ])
        return s
    elif event == "toast_info":
        return _envelope(_sine(1046, 0.1, SR), 0.01, 0.04, 0.55, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_sine(660, 0.09, SR), 0.01, 0.04, 0.6, 0.07, SR),
            _silence(0.04, SR),
            _envelope(_sine(660, 0.09, SR), 0.01, 0.04, 0.6, 0.07, SR),
        )
        return s
    elif event == "countdown_tick":
        click = _mix(_sine(300, 0.04, SR), _noise(0.04, SR))
        click = [s * 0.3 for s in click]
        return _envelope(click, 0.002, 0.015, 0.4, 0.025, SR)
    elif event == "countdown_final":
        s = _concat(
            _envelope(_sine(880, 0.12, SR), 0.005, 0.04, 0.7, 0.1, SR),
            _envelope(_sine(1100, 0.18, SR), 0.005, 0.05, 0.72, 0.15, SR),
        )
        return s
    elif event == "personal_best":
        s = _concat(*[
            _envelope(_sine(f, 0.09, SR), 0.005, 0.04, 0.72, 0.1, SR)
            for f in [523, 659, 784, 880, 988, 1175]
        ])
        return s
    else:  # combo
        bumps = _concat(*[
            _envelope(_mix(_sine(220, 0.05, SR), _noise(0.05, SR)),
                      0.002, 0.02, 0.4, 0.04, SR)
            for _ in range(4)
        ])
        return [s * 0.5 for s in bumps]


def _build_galactic_battle(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(_sweep(200, 1000, 0.15, SR), _silence(0.03, SR), _sine(1000, 0.22, SR))
        laser = _ring(s[:int(0.1 * SR)], 180, SR)
        return _envelope(_concat(laser, s[int(0.1 * SR):]), 0.01, 0.05, 0.68, 0.18, SR)
    elif event == "achievement_rare":
        s = _mix(_sweep(150, 2000, 0.4, SR), _sine(800, 0.4, SR), _sine(1200, 0.4, SR))
        return _envelope(_tremolo(s, 10, 0.2, SR), 0.01, 0.07, 0.68, 0.22, SR)
    elif event == "challenge_start":
        alarm = _concat(*[_sine(440 if i % 2 == 0 else 550, 0.07, SR) for i in range(4)])
        s = _concat(alarm, _silence(0.04, SR), _sweep(300, 900, 0.15, SR))
        return _envelope(s, 0.005, 0.04, 0.65, 0.15, SR)
    elif event == "challenge_complete":
        s = _concat(_sweep(400, 1400, 0.18, SR), _sine(1400, 0.22, SR))
        return _envelope(s, 0.01, 0.05, 0.72, 0.18, SR)
    elif event == "challenge_fail":
        s = _mix(_sweep(600, 60, 0.28, SR), _noise(0.28, SR))
        return _envelope(s, 0.005, 0.04, 0.5, 0.22, SR)
    elif event == "level_up":
        s = _concat(
            _sweep(100, 600, 0.15, SR), _sweep(600, 1200, 0.12, SR),
            _sweep(1200, 1800, 0.1, SR), _sine(1800, 0.2, SR),
        )
        return _envelope(s, 0.01, 0.05, 0.75, 0.2, SR)
    elif event == "toast_info":
        s = _sweep(500, 800, 0.1, SR)
        return _envelope(s, 0.005, 0.04, 0.52, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(_sweep(300, 600, 0.09, SR), _silence(0.04, SR), _sweep(300, 600, 0.09, SR))
        return _envelope(s, 0.005, 0.03, 0.6, 0.12, SR)
    elif event == "countdown_tick":
        return _envelope(_sweep(500, 300, 0.06, SR), 0.002, 0.02, 0.4, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(_sweep(200, 1200, 0.1, SR), _sine(1200, 0.2, SR))
        return _envelope(s, 0.005, 0.04, 0.72, 0.15, SR)
    elif event == "personal_best":
        s = _concat(
            _sweep(200, 900, 0.12, SR), _silence(0.03, SR),
            _sweep(400, 1200, 0.1, SR), _silence(0.03, SR),
            _sine(1200, 0.25, SR),
        )
        return _envelope(s, 0.01, 0.05, 0.75, 0.2, SR)
    else:  # combo
        s = _concat(*[_sweep(f, f * 1.4, 0.055, SR) for f in [250, 350, 450, 550, 650]])
        return _envelope(s, 0.004, 0.025, 0.65, 0.1, SR)


def _build_stage_magic(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        shimmer = _concat(*[
            _envelope(_sine(f, 0.07, SR), 0.005, 0.03, 0.6, 0.07, SR)
            for f in [784, 988, 1175, 1568, 1975]
        ])
        return shimmer
    elif event == "achievement_rare":
        s = _concat(*[
            _envelope(_sine(f, 0.065, SR), 0.005, 0.025, 0.65, 0.065, SR)
            for f in [523, 659, 784, 880, 988, 1175, 1319, 1568, 1760]
        ])
        return s
    elif event == "challenge_start":
        drum = _mix(_sine(80, 0.15, SR), _noise(0.15, SR))
        drum = [s * 0.45 for s in drum]
        s = _concat(
            _envelope(drum, 0.002, 0.04, 0.4, 0.1, SR),
            _silence(0.04, SR),
            _envelope(_sine(660, 0.22, SR), 0.01, 0.06, 0.65, 0.15, SR),
        )
        return s
    elif event == "challenge_complete":
        s = _concat(*[
            _envelope(_sine(f, 0.09, SR), 0.005, 0.04, 0.68, 0.1, SR)
            for f in [523, 659, 784, 988, 1175]
        ])
        return s
    elif event == "challenge_fail":
        return _envelope(_concat(_sine(440, 0.12, SR), _sine(330, 0.2, SR)), 0.01, 0.06, 0.5, 0.2, SR)
    elif event == "level_up":
        s = _concat(*[
            _envelope(_sine(f, 0.08, SR), 0.005, 0.035, 0.72, 0.1, SR)
            for f in [262, 330, 392, 523, 659, 784, 1046, 1319]
        ])
        return s
    elif event == "toast_info":
        return _envelope(_sine(1175, 0.1, SR), 0.01, 0.04, 0.52, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_sine(660, 0.09, SR), 0.01, 0.04, 0.6, 0.07, SR),
            _silence(0.04, SR),
            _envelope(_sine(880, 0.09, SR), 0.01, 0.04, 0.65, 0.07, SR),
        )
        return s
    elif event == "countdown_tick":
        return _envelope(_sine(1046, 0.06, SR), 0.003, 0.02, 0.45, 0.04, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_sine(f, 0.09, SR), 0.003, 0.035, 0.65, 0.09, SR)
            for f in [880, 1108, 1319]
        ])
        return s
    elif event == "personal_best":
        s = _concat(*[
            _envelope(_sine(f, 0.075, SR), 0.004, 0.03, 0.72, 0.09, SR)
            for f in [523, 659, 784, 880, 988, 1175, 1319, 1568]
        ])
        return s
    else:  # combo
        s = _concat(*[
            _envelope(_sine(f, 0.055, SR), 0.003, 0.025, 0.65, 0.06, SR)
            for f in [440, 554, 659, 784, 880]
        ])
        return s


def _build_neon_grid(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _mix(_sweep(220, 880, 0.18, SR), _sine(440, 0.18, SR))
        return _envelope(_ring(s, 80, SR), 0.01, 0.05, 0.65, 0.18, SR)
    elif event == "achievement_rare":
        s = _mix(_sweep(110, 1760, 0.38, SR), _sine(880, 0.38, SR), _sine(440, 0.38, SR))
        return _envelope(_tremolo(_ring(s, 60, SR), 8, 0.2, SR), 0.01, 0.07, 0.65, 0.22, SR)
    elif event == "challenge_start":
        s = _concat(_sweep(80, 440, 0.12, SR), _silence(0.04, SR), _sine(440, 0.2, SR))
        return _envelope(_ring(s, 55, SR), 0.005, 0.04, 0.62, 0.15, SR)
    elif event == "challenge_complete":
        s = _mix(_sweep(440, 1320, 0.18, SR), _sine(660, 0.18, SR))
        return _envelope(s, 0.01, 0.05, 0.68, 0.18, SR)
    elif event == "challenge_fail":
        s = _mix(_sweep(440, 55, 0.28, SR), _noise(0.28, SR))
        return _envelope([x * 0.6 for x in s], 0.005, 0.05, 0.45, 0.22, SR)
    elif event == "level_up":
        s = _mix(
            _sweep(110, 880, 0.3, SR),
            _sweep(220, 1760, 0.3, SR),
            _sine(440, 0.3, SR),
        )
        return _envelope(s, 0.01, 0.07, 0.72, 0.22, SR)
    elif event == "toast_info":
        s = _ring(_sine(660, 0.1, SR), 110, SR)
        return _envelope(s, 0.005, 0.04, 0.5, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _ring(_sine(440, 0.08, SR), 80, SR),
            _silence(0.04, SR),
            _ring(_sine(440, 0.08, SR), 80, SR),
        )
        return _envelope(s, 0.005, 0.03, 0.58, 0.1, SR)
    elif event == "countdown_tick":
        s = _ring(_sine(440, 0.055, SR), 120, SR)
        return _envelope(s, 0.002, 0.02, 0.4, 0.03, SR)
    elif event == "countdown_final":
        s = _mix(_sine(880, 0.2, SR), _ring(_sine(880, 0.2, SR), 110, SR))
        return _envelope(s, 0.005, 0.04, 0.7, 0.15, SR)
    elif event == "personal_best":
        s = _mix(_sweep(220, 1320, 0.32, SR), _sweep(440, 1760, 0.32, SR))
        return _envelope(_tremolo(s, 6, 0.15, SR), 0.01, 0.06, 0.72, 0.22, SR)
    else:  # combo
        s = _concat(*[_ring(_sine(f, 0.055, SR), 80, SR) for f in [330, 440, 550, 660, 770]])
        return _envelope(s, 0.003, 0.025, 0.62, 0.1, SR)


def _build_martian_assault(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        alien = _ring(_sweep(150, 900, 0.2, SR), 220, SR)
        s = _concat(alien, _sine(900, 0.18, SR))
        return _envelope(s, 0.01, 0.05, 0.65, 0.18, SR)
    elif event == "achievement_rare":
        s = _mix(
            _ring(_sweep(80, 1200, 0.4, SR), 180, SR),
            _sine(600, 0.4, SR),
        )
        return _envelope(_tremolo(s, 9, 0.22, SR), 0.01, 0.07, 0.65, 0.22, SR)
    elif event == "challenge_start":
        blaster = _concat(*[_ring(_sine(220 + i * 40, 0.06, SR), 140, SR) for i in range(3)])
        s = _concat(blaster, _silence(0.04, SR), _sweep(300, 700, 0.18, SR))
        return _envelope(s, 0.005, 0.04, 0.62, 0.15, SR)
    elif event == "challenge_complete":
        s = _concat(_sweep(300, 1200, 0.15, SR), _ring(_sine(1200, 0.22, SR), 200, SR))
        return _envelope(s, 0.01, 0.05, 0.68, 0.18, SR)
    elif event == "challenge_fail":
        s = _mix(_sweep(500, 50, 0.28, SR), _ring(_noise(0.28, SR), 80, SR))
        return _envelope([x * 0.55 for x in s], 0.005, 0.04, 0.45, 0.22, SR)
    elif event == "level_up":
        s = _concat(
            _ring(_sweep(100, 600, 0.12, SR), 160, SR),
            _ring(_sweep(600, 1400, 0.12, SR), 200, SR),
            _ring(_sine(1400, 0.22, SR), 220, SR),
        )
        return _envelope(s, 0.01, 0.05, 0.72, 0.2, SR)
    elif event == "toast_info":
        s = _ring(_sine(660, 0.1, SR), 120, SR)
        return _envelope(s, 0.005, 0.04, 0.5, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _ring(_sine(400, 0.08, SR), 100, SR),
            _silence(0.04, SR),
            _ring(_sine(500, 0.08, SR), 100, SR),
        )
        return _envelope(s, 0.005, 0.03, 0.58, 0.1, SR)
    elif event == "countdown_tick":
        s = _ring(_sine(400, 0.055, SR), 140, SR)
        return _envelope(s, 0.002, 0.02, 0.38, 0.03, SR)
    elif event == "countdown_final":
        s = _ring(_concat(_sweep(200, 1100, 0.1, SR), _sine(1100, 0.18, SR)), 180, SR)
        return _envelope(s, 0.005, 0.04, 0.7, 0.15, SR)
    elif event == "personal_best":
        s = _mix(
            _ring(_sweep(150, 1200, 0.3, SR), 200, SR),
            _sweep(300, 1800, 0.3, SR),
        )
        return _envelope(s, 0.01, 0.06, 0.72, 0.22, SR)
    else:  # combo
        s = _concat(*[_ring(_sine(f, 0.055, SR), 120, SR) for f in [280, 370, 460, 550, 640]])
        return _envelope(s, 0.003, 0.025, 0.62, 0.1, SR)


def _build_carnival_show(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(*[
            _envelope(_sine(f, 0.075, SR), 0.005, 0.025, 0.65, 0.08, SR)
            for f in [523, 659, 784, 880, 1046, 1319]
        ])
        return s
    elif event == "achievement_rare":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.07, SR), _sine(f * 1.5, 0.07, SR)), 0.005, 0.025, 0.65, 0.08, SR)
            for f in [440, 554, 659, 784, 880, 1046, 1175, 1319]
        ])
        return s
    elif event == "challenge_start":
        roll = _concat(*[_envelope(_noise(0.04, SR), 0.001, 0.01, 0.4, 0.03, SR) for _ in range(3)])
        fanfare = _envelope(_sine(784, 0.22, SR), 0.01, 0.06, 0.68, 0.15, SR)
        return _concat(roll, _silence(0.04, SR), fanfare)
    elif event == "challenge_complete":
        s = _concat(*[
            _envelope(_sine(f, 0.08, SR), 0.004, 0.03, 0.68, 0.09, SR)
            for f in [523, 659, 784, 659, 784, 1046]
        ])
        return s
    elif event == "challenge_fail":
        s = _concat(*[
            _envelope(_sine(f, 0.1, SR), 0.005, 0.04, 0.5, 0.1, SR)
            for f in [440, 392, 349, 294]
        ])
        return s
    elif event == "level_up":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.07, SR), _sine(f * 1.25, 0.07, SR)), 0.004, 0.03, 0.72, 0.09, SR)
            for f in [262, 330, 392, 523, 659, 784, 880, 1046]
        ])
        return s
    elif event == "toast_info":
        return _envelope(_sine(1046, 0.09, SR), 0.008, 0.04, 0.52, 0.09, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_sine(660, 0.09, SR), 0.005, 0.035, 0.62, 0.07, SR),
            _silence(0.04, SR),
            _envelope(_sine(880, 0.09, SR), 0.005, 0.035, 0.65, 0.07, SR),
        )
        return s
    elif event == "countdown_tick":
        return _envelope(_mix(_sine(880, 0.04, SR), _noise(0.04, SR)), 0.001, 0.015, 0.4, 0.025, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_sine(f, 0.07, SR), 0.003, 0.03, 0.68, 0.08, SR)
            for f in [784, 988, 1175]
        ])
        return s
    elif event == "personal_best":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.07, SR), _sine(f * 1.5, 0.07, SR)), 0.004, 0.028, 0.72, 0.08, SR)
            for f in [523, 659, 784, 880, 1046, 1175, 1319, 1568]
        ])
        return s
    else:  # combo
        s = _concat(*[
            _envelope(_sine(f, 0.055, SR), 0.003, 0.022, 0.62, 0.06, SR)
            for f in [440, 554, 659, 784, 880]
        ])
        return s


def _build_medieval_quest(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        horn = _concat(*[
            _envelope(_mix(_sine(f, 0.1, SR), _sine(f * 1.5, 0.1, SR)), 0.01, 0.04, 0.65, 0.1, SR)
            for f in [392, 523, 659, 784]
        ])
        return horn
    elif event == "achievement_rare":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.25, 0.09, SR), _sine(f * 1.5, 0.09, SR)),
                      0.008, 0.035, 0.65, 0.1, SR)
            for f in [330, 392, 494, 587, 659, 784, 880, 988]
        ])
        return s
    elif event == "challenge_start":
        drums = _concat(*[_envelope(_mix(_sine(60, 0.08, SR), _noise(0.08, SR)),
                                    0.001, 0.03, 0.45, 0.06, SR) for _ in range(2)])
        fanfare = _concat(*[
            _envelope(_mix(_sine(f, 0.1, SR), _sine(f * 1.5, 0.1, SR)), 0.01, 0.04, 0.65, 0.1, SR)
            for f in [330, 440, 523]
        ])
        return _concat(drums, _silence(0.04, SR), fanfare)
    elif event == "challenge_complete":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.25, 0.09, SR)), 0.008, 0.035, 0.68, 0.1, SR)
            for f in [392, 494, 587, 784, 988]
        ])
        return s
    elif event == "challenge_fail":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.1, SR), _sine(f * 1.25, 0.1, SR)), 0.008, 0.04, 0.5, 0.12, SR)
            for f in [330, 262, 220, 196]
        ])
        return s
    elif event == "level_up":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.5, 0.08, SR)), 0.008, 0.032, 0.72, 0.1, SR)
            for f in [262, 330, 392, 494, 587, 659, 784, 988, 1175]
        ])
        return s
    elif event == "toast_info":
        return _envelope(_mix(_sine(659, 0.1, SR), _sine(988, 0.1, SR)), 0.01, 0.04, 0.55, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_mix(_sine(440, 0.09, SR), _sine(550, 0.09, SR)), 0.008, 0.035, 0.62, 0.08, SR),
            _silence(0.04, SR),
            _envelope(_mix(_sine(440, 0.09, SR), _sine(550, 0.09, SR)), 0.008, 0.035, 0.62, 0.08, SR),
        )
        return s
    elif event == "countdown_tick":
        s = _mix(_sine(330, 0.05, SR), _sine(495, 0.05, SR))
        return _envelope(s, 0.002, 0.018, 0.42, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.5, 0.09, SR)), 0.005, 0.035, 0.68, 0.1, SR)
            for f in [523, 659, 784]
        ])
        return s
    elif event == "personal_best":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.25, 0.08, SR), _sine(f * 1.5, 0.08, SR)),
                      0.006, 0.03, 0.72, 0.1, SR)
            for f in [392, 494, 587, 659, 784, 880, 988, 1175]
        ])
        return s
    else:  # combo
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.055, SR), _sine(f * 1.5, 0.055, SR)), 0.003, 0.022, 0.62, 0.07, SR)
            for f in [330, 415, 523, 622, 784]
        ])
        return s


def _build_haunted_manor(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _mix(_sweep(300, 600, 0.22, SR), _crackle(0.22, SR))
        tone = _tremolo(_sine(600, 0.18, SR), 5, 0.4, SR)
        return _envelope(_concat(s, tone), 0.02, 0.08, 0.55, 0.22, SR)
    elif event == "achievement_rare":
        s = _mix(
            _tremolo(_sine(300, 0.45, SR), 4, 0.5, SR),
            _sweep(200, 800, 0.45, SR),
            _crackle(0.45, SR),
        )
        return _envelope(s, 0.03, 0.1, 0.55, 0.28, SR)
    elif event == "challenge_start":
        creak = _mix(_sweep(100, 200, 0.18, SR), _crackle(0.18, SR))
        sting = _tremolo(_sine(440, 0.22, SR), 6, 0.45, SR)
        return _envelope(_concat(creak, _silence(0.04, SR), sting), 0.01, 0.06, 0.55, 0.2, SR)
    elif event == "challenge_complete":
        s = _mix(_sweep(300, 900, 0.22, SR), _tremolo(_sine(600, 0.22, SR), 5, 0.3, SR))
        return _envelope(s, 0.02, 0.07, 0.58, 0.22, SR)
    elif event == "challenge_fail":
        s = _mix(_sweep(500, 80, 0.32, SR), _crackle(0.32, SR))
        return _envelope(s, 0.005, 0.05, 0.42, 0.28, SR)
    elif event == "level_up":
        s = _mix(
            _sweep(150, 600, 0.35, SR),
            _tremolo(_sine(300, 0.35, SR), 4, 0.45, SR),
            _crackle(0.35, SR),
        )
        return _envelope(s, 0.02, 0.08, 0.62, 0.25, SR)
    elif event == "toast_info":
        s = _tremolo(_sine(440, 0.12, SR), 6, 0.35, SR)
        return _envelope(s, 0.01, 0.05, 0.48, 0.12, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_mix(_sine(330, 0.1, SR), _crackle(0.1, SR)), 0.005, 0.04, 0.5, 0.08, SR),
            _silence(0.05, SR),
            _envelope(_mix(_sine(440, 0.1, SR), _crackle(0.1, SR)), 0.005, 0.04, 0.55, 0.08, SR),
        )
        return s
    elif event == "countdown_tick":
        s = _mix(_sine(220, 0.06, SR), _crackle(0.06, SR))
        return _envelope(s, 0.002, 0.02, 0.38, 0.04, SR)
    elif event == "countdown_final":
        s = _mix(_sweep(180, 600, 0.12, SR), _tremolo(_sine(400, 0.2, SR), 5, 0.4, SR))
        return _envelope(s, 0.008, 0.05, 0.62, 0.2, SR)
    elif event == "personal_best":
        s = _mix(
            _sweep(200, 800, 0.32, SR),
            _tremolo(_sine(400, 0.32, SR), 4, 0.4, SR),
            _crackle(0.32, SR),
        )
        return _envelope(s, 0.02, 0.08, 0.62, 0.25, SR)
    else:  # combo
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.06, SR), _crackle(0.06, SR)), 0.002, 0.025, 0.42, 0.06, SR)
            for f in [220, 277, 330, 415, 494]
        ])
        return s


def _build_deep_ocean(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _tremolo(_sine(220, 0.35, SR), 3, 0.4, SR)
        ping = _envelope(_sine(880, 0.18, SR), 0.01, 0.08, 0.6, 0.18, SR)
        return _concat(_envelope(s, 0.04, 0.1, 0.55, 0.25, SR), _silence(0.02, SR), ping)
    elif event == "achievement_rare":
        s = _mix(
            _tremolo(_sine(110, 0.5, SR), 2, 0.5, SR),
            _tremolo(_sine(220, 0.5, SR), 3, 0.35, SR),
        )
        ping = _concat(
            _envelope(_sine(880, 0.12, SR), 0.01, 0.06, 0.65, 0.15, SR),
            _silence(0.04, SR),
            _envelope(_sine(1100, 0.12, SR), 0.01, 0.06, 0.65, 0.15, SR),
        )
        return _concat(_envelope(s, 0.05, 0.12, 0.55, 0.3, SR), ping)
    elif event == "challenge_start":
        s = _tremolo(_sine(180, 0.28, SR), 2.5, 0.45, SR)
        ping = _envelope(_sine(660, 0.22, SR), 0.01, 0.07, 0.62, 0.2, SR)
        return _concat(_envelope(s, 0.03, 0.08, 0.52, 0.2, SR), ping)
    elif event == "challenge_complete":
        s = _concat(
            _envelope(_tremolo(_sine(220, 0.2, SR), 3, 0.38, SR), 0.03, 0.08, 0.55, 0.18, SR),
            _envelope(_sine(880, 0.22, SR), 0.01, 0.07, 0.65, 0.2, SR),
        )
        return s
    elif event == "challenge_fail":
        s = _tremolo(_sweep(300, 60, 0.35, SR), 2, 0.4, SR)
        return _envelope(s, 0.02, 0.07, 0.42, 0.28, SR)
    elif event == "level_up":
        s = _mix(
            _tremolo(_sine(110, 0.4, SR), 2, 0.45, SR),
            _tremolo(_sine(220, 0.4, SR), 3, 0.35, SR),
        )
        pings = _concat(*[
            _envelope(_sine(f, 0.1, SR), 0.008, 0.04, 0.65, 0.12, SR)
            for f in [440, 550, 660, 880]
        ])
        return _concat(_envelope(s, 0.04, 0.1, 0.58, 0.28, SR), pings)
    elif event == "toast_info":
        return _envelope(_tremolo(_sine(440, 0.12, SR), 3, 0.3, SR), 0.02, 0.05, 0.5, 0.12, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_tremolo(_sine(330, 0.1, SR), 4, 0.35, SR), 0.01, 0.04, 0.52, 0.09, SR),
            _silence(0.05, SR),
            _envelope(_tremolo(_sine(440, 0.1, SR), 4, 0.38, SR), 0.01, 0.04, 0.55, 0.09, SR),
        )
        return s
    elif event == "countdown_tick":
        s = _tremolo(_sine(660, 0.07, SR), 4, 0.2, SR)
        return _envelope(s, 0.005, 0.025, 0.42, 0.04, SR)
    elif event == "countdown_final":
        s = _concat(
            _envelope(_sine(660, 0.1, SR), 0.008, 0.04, 0.68, 0.1, SR),
            _envelope(_tremolo(_sine(880, 0.22, SR), 3, 0.3, SR), 0.01, 0.07, 0.7, 0.2, SR),
        )
        return s
    elif event == "personal_best":
        s = _mix(
            _tremolo(_sine(110, 0.42, SR), 2, 0.45, SR),
            _tremolo(_sine(220, 0.42, SR), 2.8, 0.38, SR),
        )
        pings = _concat(*[
            _envelope(_sine(f, 0.1, SR), 0.008, 0.04, 0.68, 0.12, SR)
            for f in [440, 550, 660, 784, 880]
        ])
        return _concat(_envelope(s, 0.04, 0.1, 0.6, 0.3, SR), pings)
    else:  # combo
        s = _concat(*[
            _envelope(_tremolo(_sine(f, 0.065, SR), 4, 0.22, SR), 0.005, 0.025, 0.52, 0.07, SR)
            for f in [330, 415, 523, 622, 784]
        ])
        return s


def _build_jukebox(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.25, 0.09, SR)), 0.008, 0.035, 0.68, 0.1, SR)
            for f in [392, 494, 587, 784, 988]
        ])
        return s
    elif event == "achievement_rare":
        notes = [330, 415, 494, 587, 698, 784, 880, 988, 1175]
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.07, SR), _sine(f * 1.25, 0.07, SR),
                           _sine(f * 1.5, 0.07, SR)), 0.006, 0.028, 0.65, 0.09, SR)
            for f in notes
        ])
        return s
    elif event == "challenge_start":
        roll = _concat(*[_envelope(_mix(_noise(0.03, SR), _sine(100, 0.03, SR)),
                                   0.001, 0.012, 0.4, 0.025, SR) for _ in range(4)])
        call = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.5, 0.09, SR)), 0.008, 0.035, 0.65, 0.1, SR)
            for f in [330, 440, 523]
        ])
        return _concat(roll, _silence(0.04, SR), call)
    elif event == "challenge_complete":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.25, 0.08, SR)), 0.007, 0.03, 0.68, 0.1, SR)
            for f in [392, 494, 587, 698, 784]
        ])
        return s
    elif event == "challenge_fail":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.1, SR), _sine(f * 1.25, 0.1, SR)), 0.007, 0.04, 0.5, 0.12, SR)
            for f in [440, 392, 330, 277]
        ])
        return s
    elif event == "level_up":
        notes = [262, 294, 330, 370, 392, 440, 494, 523, 587, 659]
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.07, SR), _sine(f * 1.25, 0.07, SR),
                           _sine(f * 1.5, 0.07, SR)), 0.005, 0.028, 0.72, 0.09, SR)
            for f in notes
        ])
        return s
    elif event == "toast_info":
        return _envelope(_mix(_sine(784, 0.1, SR), _sine(988, 0.1, SR)), 0.008, 0.04, 0.55, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_mix(_sine(523, 0.09, SR), _sine(659, 0.09, SR)), 0.007, 0.035, 0.62, 0.09, SR),
            _silence(0.04, SR),
            _envelope(_mix(_sine(659, 0.09, SR), _sine(784, 0.09, SR)), 0.007, 0.035, 0.65, 0.09, SR),
        )
        return s
    elif event == "countdown_tick":
        s = _mix(_sine(440, 0.045, SR), _sine(550, 0.045, SR))
        return _envelope(s, 0.002, 0.018, 0.42, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.25, 0.08, SR)), 0.005, 0.03, 0.7, 0.1, SR)
            for f in [523, 659, 784]
        ])
        return s
    elif event == "personal_best":
        notes = [392, 494, 587, 698, 784, 880, 988, 1175, 1319]
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.07, SR), _sine(f * 1.25, 0.07, SR),
                           _sine(f * 1.5, 0.07, SR)), 0.005, 0.025, 0.72, 0.09, SR)
            for f in notes
        ])
        return s
    else:  # combo
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.055, SR), _sine(f * 1.25, 0.055, SR)), 0.004, 0.022, 0.62, 0.07, SR)
            for f in [330, 415, 494, 622, 740]
        ])
        return s


def _build_showtime(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        fanfare = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.25, 0.09, SR),
                           _sine(f * 2, 0.09, SR)), 0.008, 0.035, 0.7, 0.1, SR)
            for f in [392, 523, 659, 784, 1046]
        ])
        return fanfare
    elif event == "achievement_rare":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.25, 0.08, SR),
                           _sine(f * 2, 0.08, SR), _sine(f * 2.5, 0.08, SR)),
                      0.007, 0.03, 0.7, 0.1, SR)
            for f in [330, 392, 494, 587, 659, 784, 880, 1046, 1175, 1319]
        ])
        return s
    elif event == "challenge_start":
        drums = _concat(*[_envelope(_mix(_sine(80, 0.07, SR), _noise(0.07, SR)),
                                    0.001, 0.025, 0.5, 0.05, SR) for _ in range(3)])
        fanfare = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 2, 0.09, SR)), 0.007, 0.035, 0.68, 0.1, SR)
            for f in [330, 440, 523, 659]
        ])
        return _concat(drums, _silence(0.04, SR), fanfare)
    elif event == "challenge_complete":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.5, 0.08, SR),
                           _sine(f * 2, 0.08, SR)), 0.007, 0.03, 0.7, 0.1, SR)
            for f in [392, 523, 659, 784, 988, 1175]
        ])
        return s
    elif event == "challenge_fail":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.1, SR), _sine(f * 1.25, 0.1, SR)), 0.008, 0.04, 0.52, 0.12, SR)
            for f in [330, 277, 247, 220]
        ])
        return s
    elif event == "level_up":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.075, SR), _sine(f * 1.25, 0.075, SR),
                           _sine(f * 2, 0.075, SR)), 0.006, 0.028, 0.75, 0.1, SR)
            for f in [262, 330, 392, 494, 587, 659, 784, 880, 988, 1175, 1319]
        ])
        return s
    elif event == "toast_info":
        return _envelope(_mix(_sine(880, 0.1, SR), _sine(1100, 0.1, SR)), 0.008, 0.04, 0.55, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_mix(_sine(660, 0.09, SR), _sine(825, 0.09, SR)), 0.007, 0.035, 0.62, 0.08, SR),
            _silence(0.04, SR),
            _envelope(_mix(_sine(880, 0.09, SR), _sine(1100, 0.09, SR)), 0.007, 0.035, 0.68, 0.08, SR),
        )
        return s
    elif event == "countdown_tick":
        s = _mix(_sine(660, 0.045, SR), _sine(825, 0.045, SR))
        return _envelope(s, 0.002, 0.018, 0.45, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.5, 0.08, SR),
                           _sine(f * 2, 0.08, SR)), 0.005, 0.032, 0.72, 0.1, SR)
            for f in [523, 659, 784, 1046]
        ])
        return s
    elif event == "personal_best":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.075, SR), _sine(f * 1.25, 0.075, SR),
                           _sine(f * 2, 0.075, SR), _sine(f * 2.5, 0.075, SR)),
                      0.005, 0.028, 0.75, 0.1, SR)
            for f in [392, 494, 587, 698, 784, 880, 988, 1175, 1319, 1568]
        ])
        return s
    else:  # combo
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.055, SR), _sine(f * 1.5, 0.055, SR),
                           _sine(f * 2, 0.055, SR)), 0.004, 0.022, 0.65, 0.07, SR)
            for f in [330, 415, 523, 622, 784]
        ])
        return s


def _build_chrome_steel(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        metal = _ring(_sine(660, 0.22, SR), 440, SR)
        s = _concat(_sweep(200, 800, 0.1, SR), metal)
        return _envelope(s, 0.005, 0.04, 0.65, 0.2, SR)
    elif event == "achievement_rare":
        s = _mix(
            _ring(_sweep(200, 1200, 0.4, SR), 300, SR),
            _ring(_sine(880, 0.4, SR), 220, SR),
        )
        return _envelope(_tremolo(s, 8, 0.2, SR), 0.01, 0.06, 0.65, 0.25, SR)
    elif event == "challenge_start":
        clank = _mix(_ring(_sine(200, 0.12, SR), 160, SR), _noise(0.12, SR))
        clank = [s * 0.5 for s in clank]
        s = _concat(
            _envelope(clank, 0.002, 0.04, 0.45, 0.1, SR),
            _silence(0.04, SR),
            _envelope(_ring(_sine(660, 0.22, SR), 330, SR), 0.01, 0.06, 0.65, 0.18, SR),
        )
        return s
    elif event == "challenge_complete":
        s = _concat(
            _sweep(300, 1200, 0.12, SR),
            _ring(_sine(1200, 0.22, SR), 400, SR),
        )
        return _envelope(s, 0.01, 0.05, 0.68, 0.2, SR)
    elif event == "challenge_fail":
        s = _mix(_sweep(600, 60, 0.3, SR), _ring(_noise(0.3, SR), 100, SR))
        return _envelope([x * 0.55 for x in s], 0.005, 0.04, 0.42, 0.25, SR)
    elif event == "level_up":
        s = _concat(
            _sweep(100, 800, 0.18, SR),
            _ring(_sweep(800, 1600, 0.18, SR), 200, SR),
            _ring(_sine(1600, 0.22, SR), 400, SR),
        )
        return _envelope(s, 0.01, 0.05, 0.72, 0.22, SR)
    elif event == "toast_info":
        s = _ring(_sine(880, 0.1, SR), 440, SR)
        return _envelope(s, 0.005, 0.04, 0.5, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _ring(_sine(600, 0.09, SR), 300, SR),
            _silence(0.04, SR),
            _ring(_sine(800, 0.09, SR), 400, SR),
        )
        return _envelope(s, 0.005, 0.035, 0.58, 0.1, SR)
    elif event == "countdown_tick":
        s = _ring(_sine(500, 0.055, SR), 250, SR)
        return _envelope(s, 0.002, 0.02, 0.4, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(
            _ring(_sweep(300, 1200, 0.1, SR), 200, SR),
            _ring(_sine(1200, 0.2, SR), 300, SR),
        )
        return _envelope(s, 0.005, 0.04, 0.7, 0.18, SR)
    elif event == "personal_best":
        s = _mix(
            _ring(_sweep(200, 1400, 0.32, SR), 200, SR),
            _ring(_sweep(400, 1600, 0.32, SR), 300, SR),
        )
        return _envelope(s, 0.01, 0.06, 0.72, 0.25, SR)
    else:  # combo
        s = _concat(*[_ring(_sine(f, 0.055, SR), f // 2, SR) for f in [330, 440, 550, 660, 770]])
        return _envelope(s, 0.003, 0.025, 0.62, 0.1, SR)


def _build_treasure_hunt(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        coins = _concat(*[
            _envelope(_mix(_sine(f, 0.06, SR), _sine(f * 2, 0.06, SR)), 0.003, 0.02, 0.62, 0.08, SR)
            for f in [880, 1100, 1320, 1760]
        ])
        return coins
    elif event == "achievement_rare":
        coins = _concat(*[
            _envelope(_mix(_sine(f, 0.055, SR), _sine(f * 2, 0.055, SR),
                           _sine(f * 3, 0.055, SR)), 0.003, 0.018, 0.65, 0.08, SR)
            for f in [660, 784, 880, 988, 1100, 1175, 1320, 1568, 1760]
        ])
        return coins
    elif event == "challenge_start":
        drum = _envelope(_mix(_sine(80, 0.1, SR), _noise(0.1, SR)), 0.001, 0.03, 0.45, 0.08, SR)
        trumpet = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.25, 0.08, SR)), 0.007, 0.03, 0.65, 0.09, SR)
            for f in [330, 440, 523]
        ])
        return _concat(drum, _silence(0.04, SR), trumpet)
    elif event == "challenge_complete":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 2, 0.08, SR)), 0.006, 0.03, 0.68, 0.1, SR)
            for f in [392, 494, 587, 784, 988]
        ])
        return s
    elif event == "challenge_fail":
        s = _concat(*[
            _envelope(_sine(f, 0.1, SR), 0.007, 0.04, 0.5, 0.12, SR)
            for f in [330, 277, 247, 196]
        ])
        return s
    elif event == "level_up":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.07, SR), _sine(f * 2, 0.07, SR)), 0.005, 0.026, 0.72, 0.09, SR)
            for f in [262, 330, 392, 494, 587, 659, 784, 880, 1046, 1319]
        ])
        return s
    elif event == "toast_info":
        return _envelope(_mix(_sine(880, 0.09, SR), _sine(1760, 0.09, SR)), 0.007, 0.035, 0.52, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_sine(660, 0.08, SR), 0.006, 0.03, 0.58, 0.09, SR),
            _silence(0.04, SR),
            _envelope(_sine(880, 0.08, SR), 0.006, 0.03, 0.62, 0.09, SR),
        )
        return s
    elif event == "countdown_tick":
        return _envelope(_mix(_sine(880, 0.04, SR), _sine(1760, 0.04, SR)), 0.002, 0.015, 0.42, 0.025, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 2, 0.08, SR)), 0.004, 0.03, 0.7, 0.1, SR)
            for f in [659, 784, 988]
        ])
        return s
    elif event == "personal_best":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.065, SR), _sine(f * 2, 0.065, SR),
                           _sine(f * 3, 0.065, SR)), 0.004, 0.025, 0.72, 0.09, SR)
            for f in [392, 494, 587, 698, 784, 880, 988, 1175, 1319, 1568]
        ])
        return s
    else:  # combo
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.05, SR), _sine(f * 2, 0.05, SR)), 0.003, 0.02, 0.62, 0.07, SR)
            for f in [523, 659, 784, 880, 1046]
        ])
        return s


def _build_turbo_racer(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        engine = _sweep(200, 1600, 0.18, SR)
        s = _concat(engine, _sine(1600, 0.12, SR))
        return _envelope(s, 0.01, 0.04, 0.68, 0.15, SR)
    elif event == "achievement_rare":
        s = _mix(
            _sweep(100, 2000, 0.38, SR),
            _sweep(200, 1800, 0.38, SR),
            _sine(1000, 0.38, SR),
        )
        return _envelope(_tremolo(s, 12, 0.15, SR), 0.01, 0.06, 0.68, 0.22, SR)
    elif event == "challenge_start":
        rev = _concat(*[_sweep(200 + i * 200, 400 + i * 200, 0.07, SR) for i in range(3)])
        go = _concat(_silence(0.04, SR), _sweep(300, 1800, 0.2, SR))
        return _envelope(_concat(rev, go), 0.01, 0.04, 0.65, 0.15, SR)
    elif event == "challenge_complete":
        s = _concat(_sweep(400, 2000, 0.18, SR), _sine(2000, 0.15, SR))
        return _envelope(s, 0.01, 0.04, 0.7, 0.15, SR)
    elif event == "challenge_fail":
        s = _concat(_sweep(800, 100, 0.18, SR), _noise(0.15, SR))
        return _envelope([x * 0.55 for x in s], 0.005, 0.04, 0.45, 0.2, SR)
    elif event == "level_up":
        s = _concat(
            _sweep(100, 600, 0.1, SR),
            _sweep(600, 1200, 0.1, SR),
            _sweep(1200, 2400, 0.1, SR),
            _sine(2400, 0.18, SR),
        )
        return _envelope(s, 0.01, 0.04, 0.72, 0.2, SR)
    elif event == "toast_info":
        return _envelope(_sweep(600, 900, 0.1, SR), 0.005, 0.04, 0.52, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(_sweep(400, 700, 0.09, SR), _silence(0.04, SR), _sweep(400, 700, 0.09, SR))
        return _envelope(s, 0.005, 0.03, 0.6, 0.1, SR)
    elif event == "countdown_tick":
        return _envelope(_sweep(500, 300, 0.055, SR), 0.002, 0.02, 0.4, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(_sweep(300, 2000, 0.12, SR), _sine(2000, 0.15, SR))
        return _envelope(s, 0.005, 0.04, 0.72, 0.15, SR)
    elif event == "personal_best":
        s = _concat(
            _sweep(100, 1000, 0.12, SR),
            _sweep(1000, 2200, 0.1, SR),
            _sine(2200, 0.2, SR),
        )
        return _envelope(s, 0.01, 0.05, 0.75, 0.2, SR)
    else:  # combo
        s = _concat(*[_sweep(f, f * 1.6, 0.055, SR) for f in [200, 300, 400, 500, 600]])
        return _envelope(s, 0.004, 0.022, 0.65, 0.1, SR)


def _build_neon_lounge(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.1, SR), _sine(f * 1.5, 0.1, SR)), 0.01, 0.04, 0.62, 0.12, SR)
            for f in [330, 415, 494, 659, 784]
        ])
        return s
    elif event == "achievement_rare":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.25, 0.09, SR),
                           _sine(f * 1.5, 0.09, SR)), 0.008, 0.035, 0.65, 0.1, SR)
            for f in [277, 330, 415, 494, 587, 698, 784, 880, 988]
        ])
        return s
    elif event == "challenge_start":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.1, SR), _sine(f * 1.5, 0.1, SR)), 0.01, 0.04, 0.62, 0.12, SR)
            for f in [220, 294, 370]
        ])
        beat = _concat(
            _silence(0.04, SR),
            _envelope(_mix(_sine(200, 0.12, SR), _noise(0.12, SR)), 0.001, 0.04, 0.45, 0.1, SR),
        )
        return _concat(s, beat)
    elif event == "challenge_complete":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.25, 0.09, SR),
                           _sine(f * 1.5, 0.09, SR)), 0.008, 0.035, 0.65, 0.1, SR)
            for f in [330, 415, 523, 659, 784]
        ])
        return s
    elif event == "challenge_fail":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.11, SR), _sine(f * 1.25, 0.11, SR)), 0.01, 0.045, 0.5, 0.12, SR)
            for f in [330, 277, 247, 220]
        ])
        return s
    elif event == "level_up":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.25, 0.08, SR),
                           _sine(f * 1.5, 0.08, SR)), 0.007, 0.03, 0.7, 0.1, SR)
            for f in [220, 277, 330, 415, 494, 587, 659, 784, 880, 1047]
        ])
        return s
    elif event == "toast_info":
        return _envelope(_mix(_sine(660, 0.1, SR), _sine(990, 0.1, SR)), 0.01, 0.04, 0.52, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _envelope(_mix(_sine(494, 0.09, SR), _sine(740, 0.09, SR)), 0.008, 0.035, 0.6, 0.09, SR),
            _silence(0.04, SR),
            _envelope(_mix(_sine(587, 0.09, SR), _sine(880, 0.09, SR)), 0.008, 0.035, 0.62, 0.09, SR),
        )
        return s
    elif event == "countdown_tick":
        s = _mix(_sine(494, 0.045, SR), _sine(740, 0.045, SR))
        return _envelope(s, 0.002, 0.018, 0.42, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.09, SR), _sine(f * 1.5, 0.09, SR)), 0.006, 0.035, 0.68, 0.1, SR)
            for f in [523, 659, 784]
        ])
        return s
    elif event == "personal_best":
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.08, SR), _sine(f * 1.25, 0.08, SR),
                           _sine(f * 1.5, 0.08, SR), _sine(f * 2, 0.08, SR)),
                      0.006, 0.028, 0.72, 0.1, SR)
            for f in [277, 330, 415, 494, 587, 698, 784, 880, 988, 1175]
        ])
        return s
    else:  # combo
        s = _concat(*[
            _envelope(_mix(_sine(f, 0.06, SR), _sine(f * 1.5, 0.06, SR)), 0.004, 0.024, 0.62, 0.08, SR)
            for f in [330, 415, 494, 622, 784]
        ])
        return s


def _build_voltage(event: str) -> List[float]:
    SR = SAMPLE_RATE
    if event == "achievement_unlock":
        s = _concat(
            _ring(_sweep(200, 1000, 0.12, SR), 120, SR),
            _mix(_sine(1000, 0.2, SR), _ring(_sine(1000, 0.2, SR), 200, SR)),
        )
        return _envelope(s, 0.005, 0.04, 0.68, 0.18, SR)
    elif event == "achievement_rare":
        s = _mix(
            _ring(_sweep(100, 2000, 0.42, SR), 150, SR),
            _ring(_sweep(200, 1600, 0.42, SR), 200, SR),
            _sine(800, 0.42, SR),
        )
        return _envelope(_tremolo(s, 10, 0.18, SR), 0.01, 0.06, 0.68, 0.25, SR)
    elif event == "challenge_start":
        zap = _concat(*[
            _ring(_sine(200 + i * 100, 0.06, SR), 100 + i * 30, SR)
            for i in range(3)
        ])
        s = _concat(zap, _silence(0.04, SR), _ring(_sweep(300, 1200, 0.2, SR), 150, SR))
        return _envelope(s, 0.005, 0.04, 0.65, 0.15, SR)
    elif event == "challenge_complete":
        s = _mix(
            _ring(_sweep(400, 1600, 0.2, SR), 200, SR),
            _sine(800, 0.2, SR),
        )
        return _envelope(_concat(s, _sine(1600, 0.15, SR)), 0.01, 0.05, 0.7, 0.18, SR)
    elif event == "challenge_fail":
        s = _mix(_ring(_sweep(600, 60, 0.3, SR), 80, SR), _noise(0.3, SR))
        return _envelope([x * 0.5 for x in s], 0.005, 0.04, 0.42, 0.25, SR)
    elif event == "level_up":
        s = _concat(
            _ring(_sweep(100, 800, 0.15, SR), 120, SR),
            _ring(_sweep(800, 1600, 0.12, SR), 160, SR),
            _mix(_sine(1600, 0.22, SR), _ring(_sine(1600, 0.22, SR), 300, SR)),
        )
        return _envelope(s, 0.01, 0.05, 0.72, 0.22, SR)
    elif event == "toast_info":
        s = _ring(_sine(660, 0.1, SR), 130, SR)
        return _envelope(s, 0.005, 0.04, 0.52, 0.1, SR)
    elif event == "toast_warning":
        s = _concat(
            _ring(_sine(440, 0.09, SR), 110, SR),
            _silence(0.04, SR),
            _ring(_sine(600, 0.09, SR), 150, SR),
        )
        return _envelope(s, 0.005, 0.03, 0.6, 0.1, SR)
    elif event == "countdown_tick":
        s = _ring(_sine(500, 0.055, SR), 150, SR)
        return _envelope(s, 0.002, 0.02, 0.38, 0.03, SR)
    elif event == "countdown_final":
        s = _concat(
            _ring(_sweep(200, 1400, 0.1, SR), 150, SR),
            _mix(_sine(1400, 0.2, SR), _ring(_sine(1400, 0.2, SR), 280, SR)),
        )
        return _envelope(s, 0.005, 0.04, 0.72, 0.18, SR)
    elif event == "personal_best":
        s = _mix(
            _ring(_sweep(150, 1500, 0.32, SR), 150, SR),
            _ring(_sweep(300, 1800, 0.32, SR), 200, SR),
            _sine(900, 0.32, SR),
        )
        return _envelope(s, 0.01, 0.06, 0.72, 0.25, SR)
    else:  # combo
        s = _concat(*[_ring(_sine(f, 0.055, SR), f // 3, SR) for f in [300, 400, 500, 600, 700]])
        return _envelope(s, 0.003, 0.025, 0.62, 0.1, SR)


# ── Pack registry ─────────────────────────────────────────────────────────────

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

# ── Volume / cache / playback ─────────────────────────────────────────────────

def _volume_scale(cfg_volume) -> float:
    try:
        v = int(cfg_volume)
    except (TypeError, ValueError):
        v = DEFAULT_VOLUME
    return max(0.0, min(1.0, v / 100.0))


@lru_cache(maxsize=256)
def _get_wav(pack_id: str, event: str, volume: int) -> bytes:
    builder = _PACK_BUILDERS.get(pack_id) or _PACK_BUILDERS["arcade"]
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
    pack_id = str(ov.get("sound_pack", "arcade")).strip()
    if pack_id not in _PACK_BUILDERS:
        pack_id = "arcade"
    return pack_id


def play_sound(cfg, event_name: str) -> None:
    """Play a sound if the feature is enabled and the event is not muted."""
    try:
        ov = getattr(cfg, "OVERLAY", {}) or {}
        if not bool(ov.get("sound_enabled", True)):
            return
        events = ov.get("sound_events") or {}
        if isinstance(events, dict) and not bool(events.get(event_name, True)):
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
