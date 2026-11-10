"""BGM・効果音の合成とミキシング。

BGM と効果音はすべてこのプログラムがその場で数式から合成するオリジナル音源のため、
著作権・ライセンスの問題がない（YouTube の Content ID にも該当しない）。
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .config import SAMPLE_RATE as SR

NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def chord(root: str, kind: str, octave: int = 4) -> list[int]:
    r = NOTE[root] + 12 * (octave + 1)
    iv = {"maj7": [0, 4, 7, 11], "m7": [0, 3, 7, 10], "maj": [0, 4, 7, 12], "min": [0, 3, 7, 12],
          "sus2": [0, 2, 7, 12], "7": [0, 4, 7, 10], "add9": [0, 4, 7, 14], "madd9": [0, 3, 7, 14]}[kind]
    return [r + i for i in iv]


MOODS = {
    "calm": dict(bpm=72, prog=[("C", "maj7"), ("A", "m7"), ("F", "maj7"), ("G", "add9")],
                 arp=True, drums=False, bass=True, bell=False),
    "upbeat": dict(bpm=112, prog=[("D", "maj"), ("A", "maj"), ("B", "min"), ("G", "maj")],
                   arp=True, drums=True, bass=True, bell=False),
    "mysterious": dict(bpm=68, prog=[("A", "madd9"), ("F", "maj7"), ("C", "sus2"), ("E", "7")],
                       arp=False, drums=False, bass=True, bell=True),
    "epic": dict(bpm=88, prog=[("D", "min"), ("A#", "maj"), ("F", "maj"), ("C", "maj")],
                 arp=True, drums=True, bass=True, bell=False),
    "warm": dict(bpm=84, prog=[("F", "maj7"), ("A", "m7"), ("A#", "maj7"), ("C", "add9")],
                 arp=True, drums=False, bass=True, bell=True),
}


def _env(n: int, a: float, r: float) -> np.ndarray:
    e = np.ones(n, dtype=np.float32)
    na, nr = min(n, int(a * SR)), min(n, int(r * SR))
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _tone(hz: float, n: int, harm=(1.0, 0.3, 0.12), detune=0.0) -> np.ndarray:
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    for k, amp in enumerate(harm, start=1):
        out += amp * np.sin(2 * np.pi * hz * (1 + detune) * k * t)
    return out


def make_bgm(mood: str, seconds: float) -> np.ndarray:
    """ステレオ BGM (shape: [n, 2])。8 小節のループを生成して必要な長さまで繰り返す。"""
    cfg = MOODS.get(mood, MOODS["calm"])
    beat = 60.0 / cfg["bpm"]
    bar = 4 * beat
    loop_bars = 8
    n_loop = int(loop_bars * bar * SR)
    L = np.zeros(n_loop, dtype=np.float32)
    R = np.zeros(n_loop, dtype=np.float32)
    rng = np.random.default_rng(7)

    def add(buf, start_s, sig):
        s = int(start_s * SR)
        e = min(len(buf), s + len(sig))
        if s < len(buf):
            buf[s:e] += sig[: e - s]

    for b in range(loop_bars):
        name, kind = cfg["prog"][(b // 2) % len(cfg["prog"])]
        notes = chord(name, kind, 3)
        t0 = b * bar
        if b % 2 == 0:  # パッド: 2 小節ごと
            n = int(2 * bar * SR)
            env = _env(n, 0.8, 1.2)
            for m in notes:
                add(L, t0, 0.07 * env * _tone(midi_hz(m), n, (1, .25, .08), -0.0015))
                add(R, t0, 0.07 * env * _tone(midi_hz(m), n, (1, .25, .08), +0.0015))
        if cfg["bass"]:
            for k in range(2 if cfg["bpm"] < 80 else 4):
                n = int((bar / (2 if cfg["bpm"] < 80 else 4)) * SR)
                env = _env(n, 0.01, 0.15) * np.exp(-np.arange(n) / SR * 1.5)
                sig = 0.16 * env * _tone(midi_hz(notes[0] - 12), n, (1, .4, .1))
                add(L, t0 + k * n / SR, sig)
                add(R, t0 + k * n / SR, sig)
        if cfg["arp"]:
            seq = notes + [notes[1] + 12, notes[2] + 12, notes[1] + 12, notes[2]]
            step = beat / 2
            for k in range(8):
                m = seq[k % len(seq)] + 12
                n = int(step * 1.8 * SR)
                env = np.exp(-np.arange(n) / SR * 6) * _env(n, 0.005, 0.05)
                sig = 0.06 * env * _tone(midi_hz(m), n, (1, .5, .2, .08))
                pan = 0.5 + 0.35 * np.sin(k)
                add(L, t0 + k * step, sig * (1 - pan) * 1.4)
                add(R, t0 + k * step, sig * pan * 1.4)
        if cfg["bell"] and b % 2 == 1:
            m = notes[rng.integers(1, 4)] + 24
            n = int(2.5 * SR)
            env = np.exp(-np.arange(n) / SR * 2.2)
            sig = 0.04 * env * (_tone(midi_hz(m), n, (1,)) + 0.4 * _tone(midi_hz(m) * 2.76, n, (1,)))
            add(L, t0 + 2 * beat, sig)
            add(R, t0 + 2 * beat, sig * 0.7)
        if cfg["drums"]:
            for k in range(4):
                add(L, t0 + k * beat, 0.25 * kick())
                add(R, t0 + k * beat, 0.25 * kick())
                h = 0.05 * hat(rng)
                add(L, t0 + k * beat + beat / 2, h)
                add(R, t0 + k * beat + beat / 2, h)

    loop = np.stack([L, R], axis=1)
    reps = int(np.ceil(seconds * SR / n_loop)) + 1
    out = np.tile(loop, (reps, 1))[: int(seconds * SR)]
    fade = min(len(out) // 4, int(2.5 * SR))
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    peak = np.abs(out).max() or 1
    return (out / peak * 0.9).astype(np.float32)


# ------------------------------------------------------------------ 効果音
def kick() -> np.ndarray:
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 45 + 80 * np.exp(-t * 30)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)).astype(np.float32)


def hat(rng) -> np.ndarray:
    n = int(0.06 * SR)
    x = np.diff(rng.normal(0, 1, n + 1))
    return (x * np.exp(-np.arange(n) / SR * 70) * 0.5).astype(np.float32)


def _bandpass_noise(n: int, lo: float, hi: float, seed: int = 0) -> np.ndarray:
    spec = np.fft.rfft(np.random.default_rng(seed).normal(0, 1, n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def sfx(kind: str) -> np.ndarray:
    if kind == "whoosh":
        n = int(0.75 * SR)
        t = np.linspace(0, 1, n)
        env = np.sin(np.pi * t ** 0.7) ** 2
        lo = _bandpass_noise(n, 200, 1500, 1)
        hi = _bandpass_noise(n, 1500, 6000, 2)
        return (0.6 * env * (lo * (1 - t) + hi * t)).astype(np.float32)
    if kind == "pop":
        n = int(0.16 * SR)
        t = np.arange(n) / SR
        f = 600 + 900 * (1 - np.exp(-t * 40))
        return (0.6 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 28)).astype(np.float32)
    if kind == "impact":
        n = int(1.2 * SR)
        t = np.arange(n) / SR
        f = 38 + 90 * np.exp(-t * 12)
        boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
        crack = _bandpass_noise(n, 100, 3000, 3) * np.exp(-t * 25)
        return (0.8 * boom + 0.35 * crack).astype(np.float32)
    if kind == "chime":
        n = int(1.6 * SR)
        t = np.arange(n) / SR
        x = sum(a * np.sin(2 * np.pi * 1046.5 * r * t) * np.exp(-t * d)
                for a, r, d in [(1, 1, 2.5), (.5, 2.76, 4), (.25, 5.4, 6), (.6, 1.5, 3)])
        return (0.35 * x).astype(np.float32)
    return np.zeros(1, dtype=np.float32)


# ------------------------------------------------------------------ ミックス
def mix(total_sec: float, narration: list[tuple[float, np.ndarray]],
        effects: list[tuple[float, str]], mood: str) -> np.ndarray:
    n = int(total_sec * SR) + SR
    voice = np.zeros(n, dtype=np.float32)
    for start, x in narration:
        s = int(start * SR)
        voice[s: s + len(x)] += x[: max(0, n - s)]
    peak = np.abs(voice).max() or 1
    voice = voice / peak * 0.85

    # ナレーション中は BGM を下げる (ダッキング)
    active = (np.abs(voice) > 0.02).astype(np.float32)
    win = int(0.35 * SR)
    kernel = np.ones(win, dtype=np.float32) / win
    active = np.clip(np.convolve(active, kernel, mode="same") * 4, 0, 1)
    duck = 1.0 - 0.55 * active

    bgm = make_bgm(mood, n / SR)
    bgm = bgm[:n] * (0.17 * duck)[: len(bgm), None]

    fx = np.zeros(n, dtype=np.float32)
    for t, kind in effects:
        x = sfx(kind)
        s = max(0, int(t * SR))
        fx[s: s + len(x)] += x[: max(0, n - s)]

    out = bgm + (voice + 0.32 * fx)[:, None]
    out = np.tanh(out * 1.1) / np.tanh(1.1)  # 簡易リミッタ
    return out[: int(total_sec * SR)].astype(np.float32)


def write_wav(path: Path, x: np.ndarray) -> None:
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    data = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
