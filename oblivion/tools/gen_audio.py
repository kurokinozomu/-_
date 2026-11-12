#!/usr/bin/env python3
"""忘却都市の BGM・環境音・効果音をすべて数式から合成する (外部素材なし)。

    python3 tools/gen_audio.py      # → assets/audio/*.ogg  (ffmpeg + libvorbis が必要)

曲は「2周分レンダリングして後半を切り出す」ことで、リバーブの残響まで含めて
ループの継ぎ目が自然につながるようにしている。乱数は固定シードなので毎回同じ音になる。
"""
import os
import subprocess
import tempfile
import wave

import numpy as np

SR = 22050
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "audio")
rng = np.random.default_rng(20261112)


# ------------------------------------------------------------------ primitives
def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def t_axis(sec):
    return np.arange(int(sec * SR)) / SR


def env_adsr(n, a=0.01, d=0.1, s=0.7, r=0.2):
    e = np.ones(n) * s
    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)
    na = max(1, min(na, n))
    e[:na] = np.linspace(0, 1, na)
    nd = max(1, min(nd, n - na))
    e[na:na + nd] = np.linspace(1, s, nd)
    if nr > 0 and nr < n:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def env_decay(n, tau):
    return np.exp(-np.arange(n) / SR / tau)


def lowpass(x, cutoff):
    # 1次ローパス (ベクトル化できないので短めの信号向け)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def lowpass_fast(x, cutoff, passes=2):
    # 移動平均の多段がけで近似したローパス (長い信号向け・高速)
    w = max(1, int(SR / cutoff / 2))
    k = np.ones(w) / w
    for _ in range(passes):
        x = np.convolve(x, k, mode="same")
    return x


def reverb(x, mix=0.3, size=1.0):
    # 簡易シュレーダー型リバーブ (くし形フィルタをFFT畳み込みで)
    ir_len = int(SR * 2.5 * size)
    ir = np.zeros(ir_len)
    for delay, g in [(0.0297, 0.8), (0.0371, 0.78), (0.0411, 0.77), (0.0437, 0.75)]:
        d = int(delay * SR * size)
        k = 1
        while d * k < ir_len:
            ir[d * k] += g ** k
            k += 1
    ir *= np.exp(-np.arange(ir_len) / SR / (1.2 * size))
    ir = lowpass_fast(ir, 3000, 1)
    ir /= np.max(np.abs(ir)) + 1e-9
    wet = fft_convolve(x, ir)[: len(x)]
    wet /= np.max(np.abs(wet)) + 1e-9
    return x * (1 - mix) + wet * mix * np.max(np.abs(x))


def fft_convolve(a, b):
    n = len(a) + len(b) - 1
    nfft = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, nfft) * np.fft.rfft(b, nfft), nfft)[:n]


def soft_saw(f, t, harmonics=8):
    y = np.zeros_like(t)
    for h in range(1, harmonics + 1):
        y += np.sin(2 * np.pi * f * h * t) / h * (0.85 ** h)
    return y


def pad_note(m, sec, detune=0.12, harmonics=6):
    t = t_axis(sec)
    f = midi(m)
    y = soft_saw(f * (1 + detune / 100), t, harmonics) + soft_saw(f * (1 - detune / 100), t, harmonics)
    return y * env_adsr(len(t), a=sec * 0.3, d=0.1, s=1.0, r=sec * 0.35)


def bell(m, sec=2.5, bright=1.0):
    t = t_axis(sec)
    f = midi(m)
    y = (np.sin(2 * np.pi * f * t) + 0.4 * bright * np.sin(2 * np.pi * f * 2.76 * t) * env_decay(len(t), 0.4)
         + 0.2 * bright * np.sin(2 * np.pi * f * 5.4 * t) * env_decay(len(t), 0.15))
    return y * env_decay(len(t), sec / 3.5) * env_adsr(len(t), a=0.003, d=0.01, s=1, r=0.05)


def epiano(m, sec=1.6):
    t = t_axis(sec)
    f = midi(m)
    y = np.sin(2 * np.pi * f * t + 0.8 * np.sin(2 * np.pi * f * t) * env_decay(len(t), 0.3))
    y += 0.25 * np.sin(2 * np.pi * f * 4 * t) * env_decay(len(t), 0.08)
    return y * env_decay(len(t), sec / 2.2) * env_adsr(len(t), a=0.004, d=0.01, s=1, r=0.08)


def place(buf, sig, at_sec, gain=1.0):
    i = int(at_sec * SR) % len(buf)
    end = i + len(sig)
    if end <= len(buf):
        buf[i:end] += sig * gain
    else:
        k = len(buf) - i
        buf[i:] += sig[:k] * gain
        buf[: end - len(buf)] += sig[k:] * gain   # ループの先頭へ回り込ませる


def normalize(x, peak=0.8):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def render_loop(fn, sec):
    """2周分を作って後半を取り出す (残響込みでシームレスにループする)"""
    buf = np.zeros(int(sec * SR) * 2)
    fn(buf, sec, 0.0)
    fn(buf, sec, sec)
    return buf, len(buf) // 2


# ------------------------------------------------------------------ BGM
def bgm_title():
    L = 24.0
    def fn(buf, L, o):
        chords = [[57, 60, 64, 71], [53, 57, 60, 64], [48, 55, 59, 64], [47, 55, 59, 62]]   # Am9 Fmaj7 Cmaj7 G/B
        for i, ch in enumerate(chords):
            for m in ch:
                place(buf, pad_note(m - 12, 7.5, harmonics=5) * 0.10, o + i * 6.0)
        mel = [(0, 76), (1.5, 72), (3, 74), (4.5, 69), (6, 72), (7.5, 71), (9, 67), (12, 76), (13.5, 79),
               (15, 77), (16.5, 76), (18, 72), (19.5, 74), (21, 71)]
        for at, m in mel:
            place(buf, bell(m, 3.0, 0.6) * 0.16, o + at)
    buf, n = render_loop(fn, L)
    buf = reverb(buf, 0.45, 1.3)
    return normalize(buf[n:], 0.55)


def bgm_town():
    L = 32.0
    def fn(buf, L, o):
        chords = [[45, 52, 55, 59, 60], [41, 48, 52, 55, 57], [38, 45, 48, 53, 57], [40, 47, 50, 52, 56]]
        for i, ch in enumerate(chords):
            for m in ch:
                place(buf, pad_note(m, 9.5, 0.2, 5) * 0.07, o + i * 8.0)
            place(buf, np.sin(2 * np.pi * midi(ch[0] - 12) * t_axis(8.0)) * env_adsr(int(8 * SR), 1.5, 0.1, 1, 2.0) * 0.18, o + i * 8.0)
        motif = [(2, 72), (2.6, 69), (4.2, 64), (10, 72), (10.6, 69), (12.2, 65), (18, 74), (18.6, 72), (20.2, 69), (26, 71), (26.6, 68), (28.2, 64)]
        for at, m in motif:
            place(buf, bell(m, 3.5, 0.8) * 0.10, o + at)
    buf, n = render_loop(fn, L)
    buf = reverb(buf, 0.5, 1.6)
    return normalize(buf[n:], 0.5)


def bgm_home():
    L = 27.4   # 70bpm × 32拍
    beat = 60 / 70
    def fn(buf, L, o):
        chords = [[50, 54, 57, 61], [47, 50, 54, 57], [43, 47, 50, 54], [45, 49, 52, 54]]   # Dmaj7 Bm7 Gmaj7 A6
        for bar, ch in enumerate(chords):
            base = o + bar * 8 * beat
            for k, m in enumerate([ch[0], ch[2], ch[1], ch[3], ch[2], ch[1], ch[3], ch[2]]):
                place(buf, epiano(m + 12, 1.8) * 0.12, base + k * beat)
            place(buf, epiano(ch[0], 4.0) * 0.18, base)
            place(buf, epiano(ch[0], 4.0) * 0.12, base + 4 * beat)
        # レコードのノイズ
        n = int(L * SR)
        crackle = np.zeros(n)
        idx = rng.integers(0, n, 140)
        crackle[idx] = rng.uniform(-0.25, 0.25, 140)
        place(buf, crackle, o)
    buf, n = render_loop(fn, L)
    buf = reverb(buf, 0.3, 0.8)
    out = buf[n:]
    out += lowpass_fast(rng.normal(0, 0.01, len(out)), 1200)
    return normalize(out, 0.5)


def bgm_shop():
    L = 24.0
    def fn(buf, L, o):
        t = t_axis(L)
        drone = np.sin(2 * np.pi * midi(33) * t) + 0.8 * np.sin(2 * np.pi * midi(34) * t) + 0.4 * np.sin(2 * np.pi * midi(45) * t)
        drone *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.25 * t)
        place(buf, drone * 0.12, o)
        for k in range(16):
            m = int(rng.choice([81, 82, 84, 85, 88, 89, 91, 93]))
            place(buf, bell(m, 5.0, 1.2) * 0.05, o + k * 1.5 + rng.uniform(0, 0.4))
        # 逆再生のうねり
        for at in (5.0, 17.0):
            sw = pad_note(57, 3.0, 0.5, 4)[::-1] * np.linspace(0, 1, int(3.0 * SR)) * 0.08
            place(buf, sw, o + at)
    buf, n = render_loop(fn, L)
    buf = reverb(buf, 0.55, 1.8)
    return normalize(buf[n:], 0.5)


def bgm_work():
    L = 16.0   # 120bpm × 32拍
    beat = 0.5
    def fn(buf, L, o):
        kick_t = t_axis(0.25)
        kick = np.sin(2 * np.pi * (50 + 80 * np.exp(-kick_t * 30)) * kick_t) * env_decay(len(kick_t), 0.08)
        hat = rng.normal(0, 1, int(0.04 * SR))
        hat = (hat - lowpass_fast(hat, 4000)) * env_decay(len(hat), 0.01)
        bassline = [40, 40, 43, 40, 45, 43, 38, 40]
        for b in range(32):
            place(buf, kick * 0.35, o + b * beat)
            place(buf, hat * 0.10, o + b * beat + beat / 2)
        for b in range(64):
            m = bassline[(b // 8) % len(bassline)]
            n = int(0.2 * SR)
            tt = np.arange(n) / SR
            note = soft_saw(midi(m), tt, 5) * env_decay(n, 0.08)
            place(buf, note * 0.10, o + b * beat / 2)
        stabs = [(0, [64, 67, 71]), (4, [62, 67, 69]), (8, [64, 67, 71]), (12, [60, 64, 67])]
        for at, ch in stabs:
            for m in ch:
                place(buf, epiano(m, 1.2) * 0.06, o + at + 0.75)
    buf, n = render_loop(fn, L)
    buf = reverb(buf, 0.15, 0.6)
    return normalize(buf[n:], 0.5)


def bgm_ending():
    L = 32.0
    def fn(buf, L, o):
        chords = [[41, 48, 52, 57], [43, 50, 55, 59], [40, 47, 52, 55], [45, 52, 57, 60]]   # Fmaj7 G Em7 Am
        for i, ch in enumerate(chords):
            for k, m in enumerate(ch):
                place(buf, epiano(m + 12, 5.0) * 0.10, o + i * 8.0 + k * 0.12)
            place(buf, pad_note(ch[0], 9.0, 0.1, 4) * 0.05, o + i * 8.0)
        mel = [(1, 72), (2.5, 74), (4, 76), (9, 79), (10.5, 76), (12, 74), (17, 76), (18.5, 71), (20, 72), (25, 72), (26.5, 69), (29, 69)]
        for at, m in mel:
            place(buf, epiano(m + 12, 3.0) * 0.12, o + at)
    buf, n = render_loop(fn, L)
    buf = reverb(buf, 0.45, 1.5)
    return normalize(buf[n:], 0.55)


def amb_rain():
    L = 8.0
    def fn(buf, L, o):
        n = int(L * SR)
        noise = rng.normal(0, 1, n)
        body = lowpass_fast(noise, 1800, 3) * 0.6 + (noise - lowpass_fast(noise, 5000, 1)) * 0.08
        mod = 0.85 + 0.15 * np.sin(2 * np.pi * np.arange(n) / SR * 0.37)
        place(buf, body * mod, o)
        for _ in range(500):
            d = rng.normal(0, 1, int(0.01 * SR)) * env_decay(int(0.01 * SR), 0.002)
            place(buf, d * rng.uniform(0.2, 0.8), o + rng.uniform(0, L))
    buf, n = render_loop(fn, L)
    return normalize(buf[n:], 0.5)


# ------------------------------------------------------------------ SFX
def sfx_select():
    n = int(0.06 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * 880 * t) * env_decay(n, 0.02) * 0.5


def sfx_confirm():
    a = sfx_tone(988, 0.08); b = sfx_tone(1319, 0.14)
    return np.concatenate([a, b]) * 0.5


def sfx_cancel():
    return np.concatenate([sfx_tone(660, 0.07), sfx_tone(440, 0.12)]) * 0.4


def sfx_tone(f, sec, tau=None):
    n = int(sec * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * env_decay(n, tau or sec / 3) * env_adsr(n, 0.002, 0.01, 1, 0.01)


def sfx_text():
    n = int(0.03 * SR); t = np.arange(n) / SR
    return (np.sign(np.sin(2 * np.pi * 520 * t)) * 0.3 + np.sin(2 * np.pi * 1040 * t) * 0.2) * env_decay(n, 0.008) * 0.25


def sfx_correct():
    return np.concatenate([sfx_tone(1047, 0.06), sfx_tone(1568, 0.18)]) * 0.45


def sfx_wrong():
    n = int(0.25 * SR); t = np.arange(n) / SR
    return np.sign(np.sin(2 * np.pi * 110 * t)) * env_decay(n, 0.1) * 0.25


def sfx_coin():
    return (np.concatenate([sfx_tone(1976, 0.05, 0.05), sfx_tone(2637, 0.4, 0.15)])) * 0.35


def sfx_door():
    n = int(0.35 * SR); t = np.arange(n) / SR
    thud = np.sin(2 * np.pi * (70 + 60 * np.exp(-t * 20)) * t) * env_decay(n, 0.08)
    creak = lowpass_fast(rng.normal(0, 1, n), 900) * env_decay(n, 0.12) * 0.6
    return normalize(thud + creak, 0.6)


def sfx_paper():
    n = int(0.3 * SR)
    x = rng.normal(0, 1, n)
    x = x - lowpass_fast(x, 1500)
    e = np.sin(np.linspace(0, np.pi, n)) ** 2
    return normalize(x * e, 0.35)


def sfx_ring():
    out = []
    for _ in range(2):
        n = int(0.4 * SR); t = np.arange(n) / SR
        tone = (np.sin(2 * np.pi * 1300 * t) + np.sin(2 * np.pi * 1700 * t)) * (np.sin(2 * np.pi * 20 * t) > 0)
        out += [tone * 0.25, np.zeros(int(0.2 * SR))]
    return np.concatenate(out)


def sfx_glitch():
    n = int(0.45 * SR)
    x = rng.normal(0, 1, n)
    crush = np.repeat(x[::40], 40)[:n]
    t = np.arange(n) / SR
    tone = np.sign(np.sin(2 * np.pi * (200 + 1800 * rng.random()) * t * (1 + 3 * t)))
    gate = (rng.random(n // 400 + 1) > 0.4).repeat(400)[:n]
    return normalize((crush * 0.6 + tone * 0.3) * gate * env_decay(n, 0.25), 0.5)


def sfx_sell():
    n = int(2.5 * SR); t = np.arange(n) / SR
    sweep = np.sin(2 * np.pi * (200 * np.exp(t * 1.6)) * t) * np.linspace(0, 1, n) ** 2
    noise = lowpass_fast(rng.normal(0, 1, n), 2500) * np.linspace(0, 1, n) ** 3
    return reverb(normalize(sweep * 0.5 + noise * 0.5, 0.5), 0.4, 1.0)


def sfx_atm():
    return np.concatenate([sfx_tone(1760, 0.07, 0.2), np.zeros(int(0.05 * SR)), sfx_tone(1760, 0.07, 0.2)]) * 0.35


def sfx_heartbeat():
    def beat():
        n = int(0.18 * SR); t = np.arange(n) / SR
        return np.sin(2 * np.pi * (55 + 30 * np.exp(-t * 25)) * t) * env_decay(n, 0.05)
    return np.concatenate([beat(), np.zeros(int(0.12 * SR)), beat() * 0.7, np.zeros(int(0.5 * SR))]) * 0.7


# ------------------------------------------------------------------ write
def write_ogg(name, x):
    os.makedirs(OUT, exist_ok=True)
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype(np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    dst = os.path.join(OUT, name + ".ogg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c:a", "libvorbis", "-q:a", "2", dst], check=True)
    os.remove(path)
    print(f"{name:14s} {len(x) / SR:5.1f}s  {os.path.getsize(dst) // 1024:4d} KB")


if __name__ == "__main__":
    for name, fn in [("bgm_title", bgm_title), ("bgm_town", bgm_town), ("bgm_home", bgm_home),
                     ("bgm_shop", bgm_shop), ("bgm_work", bgm_work), ("bgm_ending", bgm_ending),
                     ("amb_rain", amb_rain)]:
        write_ogg(name, fn())
    for name, fn in [("se_select", sfx_select), ("se_confirm", sfx_confirm), ("se_cancel", sfx_cancel),
                     ("se_text", sfx_text), ("se_correct", sfx_correct), ("se_wrong", sfx_wrong),
                     ("se_coin", sfx_coin), ("se_door", sfx_door), ("se_paper", sfx_paper),
                     ("se_ring", sfx_ring), ("se_glitch", sfx_glitch), ("se_sell", sfx_sell),
                     ("se_atm", sfx_atm), ("se_heartbeat", sfx_heartbeat)]:
        write_ogg(name, fn())
