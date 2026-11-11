"""無料のアニメーション演出 (--animate)。

静止画にカメラワークをつけるだけでなく、1 コマずつ絵を描いて動きのある映像にする。
- しゃべるキャラクター (立ち絵): ナレーションの音量に合わせて口が動き、まばたき・体の揺れもする
- 声のエフェクト: 口から音の輪が広がる。「1秒ごとに2倍」系では時間とともに輪が大きく速く、画面も揺れる
- 吹き飛ぶ物: 後半はシーンのイラスト (絵文字) が口元から吹き飛んでいく
キャラクターはこのプログラムが図形から描くオリジナル。
"""
from __future__ import annotations

import math
import random
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import config
from .config import FPS, SAMPLE_RATE

MOUTH_LEVELS = 8


# ------------------------------------------------------------------ 口パク用の音量
def voice_envelope(total: float, narration: list[tuple[float, np.ndarray]]) -> np.ndarray:
    """ナレーションの音量を 1 コマごと (0〜1) にしたもの。"""
    n = int(total * SAMPLE_RATE) + SAMPLE_RATE
    v = np.zeros(n, dtype=np.float32)
    for start, x in narration:
        s = int(start * SAMPLE_RATE)
        v[s: s + len(x)] += x[: max(0, n - s)]
    hop = SAMPLE_RATE // FPS
    frames = len(v) // hop
    rms = np.sqrt(np.mean(v[: frames * hop].reshape(frames, hop) ** 2, axis=1))
    ref = np.percentile(rms[rms > 1e-4], 90) if np.any(rms > 1e-4) else 1.0
    env = np.clip(rms / (ref + 1e-9), 0, 1)
    out = np.zeros_like(env)
    level = 0.0
    for i, e in enumerate(env):  # 口はすぐ開いて、少しゆっくり閉じる
        level = e if e > level else level * 0.6 + e * 0.4
        out[i] = level
    return out


# ------------------------------------------------------------------ キャラクター
SKIN, LINE = (255, 226, 200), (70, 45, 35)
HAIR, SHIRT = (60, 40, 32), (40, 70, 140)


@lru_cache(maxsize=64)
def character_sprite(size: int, mouth: int, blink: bool, shout: bool) -> Image.Image:
    """オリジナルのキャラクター (少年)。mouth: 0(閉)〜MOUTH_LEVELS-1(全開)。"""
    S = size * 2  # 2 倍で描いて縮小し、線をなめらかに
    W, H = int(S * 1.0), int(S * 1.25)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(4, S // 70)
    cx, cy, r = W / 2, S * 0.48, S * 0.36
    # 体
    d.rounded_rectangle([cx - S * 0.3, cy + r * 0.8, cx + S * 0.3, H - 2], radius=int(S * 0.12),
                        fill=SHIRT, outline=LINE, width=lw)
    d.polygon([(cx - S * 0.08, cy + r * 0.8), (cx + S * 0.08, cy + r * 0.8), (cx, cy + r * 1.05)],
              fill=(240, 240, 240), outline=LINE)
    # 頭
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SKIN, outline=LINE, width=lw)
    # 髪
    d.chord([cx - r * 1.04, cy - r * 1.08, cx + r * 1.04, cy + r * 0.5], 180, 360, fill=HAIR)
    for k in range(4):  # 前髪
        x0 = cx - r * 0.86 + k * r * 0.43
        d.polygon([(x0, cy - r * 0.34), (x0 + r * 0.43, cy - r * 0.34), (x0 + r * 0.2, cy - r * 0.16)], fill=HAIR)
    # 眉・目
    ey, ex = cy + r * 0.05, r * 0.38
    for sx in (-1, 1):
        x = cx + sx * ex
        tilt = r * 0.08 if shout else 0
        d.line([(x - r * 0.15, ey - r * 0.2 + sx * tilt), (x + r * 0.15, ey - r * 0.2 - sx * tilt)],
               fill=HAIR, width=lw + 2)
        if blink:
            d.arc([x - r * 0.13, ey - r * 0.06, x + r * 0.13, ey + r * 0.1], 200, 340, fill=LINE, width=lw)
        else:
            d.ellipse([x - r * 0.1, ey - r * 0.14, x + r * 0.1, ey + r * 0.14], fill=(30, 25, 25))
            d.ellipse([x - r * 0.04, ey - r * 0.1, x + r * 0.03, ey - r * 0.03], fill=(255, 255, 255))
        d.ellipse([x - r * 0.16, ey + r * 0.2, x + r * 0.12, ey + r * 0.32], fill=(255, 170, 170))
    # 口
    m = mouth / (MOUTH_LEVELS - 1)
    my = cy + r * 0.52
    if m < 0.08:
        d.arc([cx - r * 0.18, my - r * 0.12, cx + r * 0.18, my + r * 0.06], 20, 160, fill=LINE, width=lw)
    else:
        mw, mh = r * (0.22 + 0.16 * m), r * (0.06 + 0.42 * m)
        d.ellipse([cx - mw, my - mh * 0.5, cx + mw, my + mh], fill=(150, 40, 50), outline=LINE, width=lw)
        d.ellipse([cx - mw * 0.55, my + mh * 0.35, cx + mw * 0.55, my + mh * 0.95], fill=(240, 120, 130))
    im = im.resize((W // 2, H // 2), Image.LANCZOS)
    # 白フチ (イラストと同じステッカー風)
    a = im.split()[3].filter(ImageFilter.MaxFilter(9))
    out = Image.new("RGBA", im.size, (255, 255, 255, 0))
    out.putalpha(a)
    out.alpha_composite(im)
    return out


# ------------------------------------------------------------------ 1 シーンの描画
def _camera(camera: str, p: float, iw: int, ih: int, ow: int, oh: int, zmax: float = 1.16):
    p = 0.7 * p + 0.3 * (1 - math.cos(math.pi * p)) / 2
    if camera == "push":
        z = 1 + 0.04 * p
        fx, fy = 0.5, 0.5
    elif camera == "zoom_in":
        z = 1 + (zmax - 1) * p
        fx, fy = 0.5, 0.5
    elif camera == "zoom_out":
        z = zmax - (zmax - 1) * p
        fx, fy = 0.5, 0.5
    else:
        z = zmax
        fx = {"pan_left": 1 - p, "pan_right": p}.get(camera, 0.5)
        fy = {"pan_up": 1 - p, "pan_down": p}.get(camera, 0.5)
    cw, ch = iw / z, ih / z
    x, y = (iw - cw) * fx, (ih - ch) * fy
    return x, y, cw, ch


def render_animated_clip(image: Path, out: Path, duration: float, camera: str, overlay: Path | None,
                         t0: float, env: np.ndarray, anim: dict) -> None:
    """背景のカメラワーク + キャラクター + 声のエフェクトを 1 コマずつ描いて書き出す。"""
    W, H = config.WIDTH, config.HEIGHT
    tall = H > W
    frames = int(round(duration * FPS))
    base = Image.open(image).convert("RGB")
    telop = Image.open(overlay).convert("RGBA") if overlay else None
    rnd = random.Random(anim.get("seed", 0))
    size = int(W * (0.34 if tall else 0.17))
    if tall:
        ccx, cbottom = W * 0.24, H * 0.62
    else:
        ccx, cbottom = W * 0.9, H * 0.99
    debris_imgs = [im for im in (anim.get("debris") or []) if im is not None]
    i0, i1 = anim.get("intensity", (0.0, 0.0))
    shake_max = 26 if tall else 20
    top_clear = bool(anim.get("hud"))
    top_mask = np.clip((np.arange(H) - H * 0.34) / (H * 0.06), 0, 1).astype(np.float32)

    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
         "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    blink_next = rnd.uniform(1.0, 3.0)
    flyers: list[dict] = []
    try:
        for f in range(frames):
            t = f / FPS
            p = f / max(1, frames - 1)
            inten = i0 + (i1 - i0) * p
            gi = min(len(env) - 1, int((t0 + t) * FPS))
            level = float(env[gi]) if gi >= 0 else 0.0
            # 背景 (カメラワーク + 揺れ)
            x, y, cw, ch = _camera(camera, p, base.width, base.height, W, H)
            sh = shake_max * inten ** 2 * (0.4 + level)
            dx, dy = sh * math.sin(t * 53.0), sh * math.cos(t * 41.0)
            x = min(max(0, x + dx), base.width - cw)
            y = min(max(0, y + dy), base.height - ch)
            frame = base.resize((W, H), Image.BILINEAR, box=(x, y, x + cw, y + ch)).convert("RGBA")
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            # キャラクター
            mouth = int(round(min(1.0, level * 1.15 + inten * 0.35 * (level > 0.05)) * (MOUTH_LEVELS - 1)))
            blink = False
            if t >= blink_next:
                blink = t < blink_next + 0.12
                if not blink:
                    blink_next = t + rnd.uniform(2.0, 4.5)
            spr = character_sprite(size, mouth, blink, inten > 0.45)
            bob = math.sin(t * 2 * math.pi * 1.1) * 4 + level * 10
            sx = int(ccx - spr.width / 2 + dx * 0.5)
            sy = int(cbottom - spr.height - bob + dy * 0.5)
            mouth_xy = (sx + spr.width / 2, sy + spr.height * 0.49)
            # 音の輪 (声が出ているとき・「2倍」系は時間とともに大きく)
            if level > 0.08 or inten > 0.3:
                rings = 2 + int(inten * 4)
                speed = 0.9 + inten * 1.6
                rmax = W * (0.25 + inten * 1.2)
                for k in range(rings):
                    ph = (t * speed + k / rings) % 1.0
                    rr = 20 + ph * rmax
                    alpha = int(220 * (1 - ph) * min(1.0, 0.3 + level + inten))
                    wd = max(3, int(6 + inten * 14))
                    d.ellipse([mouth_xy[0] - rr, mouth_xy[1] - rr * 0.8, mouth_xy[0] + rr, mouth_xy[1] + rr * 0.8],
                              outline=(255, 255, 255, alpha), width=wd)
            # 吹き飛ぶ物
            if debris_imgs and inten > 0.35 and rnd.random() < 0.08 + inten * 0.25:
                # 上部のカウンターにかからないよう、横〜下向きに飛ばす
                ang = rnd.choice([rnd.uniform(-0.15, 0.45), rnd.uniform(math.pi - 0.45, math.pi + 0.15)])
                flyers.append(dict(img=rnd.choice(debris_imgs), x=mouth_xy[0], y=mouth_xy[1],
                                   vx=math.cos(ang) * (300 + 900 * inten), vy=math.sin(ang) * (300 + 900 * inten),
                                   rot=rnd.uniform(-1, 1) * 400, a=rnd.uniform(0, 360), born=t))
            if top_clear:  # 上部 (カウンター) では音の輪を消す
                la = np.asarray(layer).copy()
                la[..., 3] = (la[..., 3] * top_mask[:, None]).astype(np.uint8)
                layer = Image.fromarray(la, "RGBA")
            frame.alpha_composite(layer)
            for fl in flyers:
                age = t - fl["born"]
                px, py = fl["x"] + fl["vx"] * age, fl["y"] + fl["vy"] * age + 500 * age * age
                im = fl["img"].rotate(fl["a"] + fl["rot"] * age, expand=True)
                if -200 < px < W + 200 and -200 < py < H + 200:
                    frame.alpha_composite(im, (int(px - im.width / 2), int(py - im.height / 2)))
            flyers = [fl for fl in flyers if t - fl["born"] < 2.5]
            frame.alpha_composite(spr, (sx, sy))
            if telop is not None:
                slide = -W * (1 - min(1, t / 0.35)) ** 2
                frame.alpha_composite(telop, (int(slide), 0)) if slide > -W else None
            proc.stdin.write(frame.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"animated clip failed: {out}")
