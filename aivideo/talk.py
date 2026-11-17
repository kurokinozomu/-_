"""掛け合い動画 (ゆっくり実況・解説風)。

画面下の左右にオリジナルの「顔キャラ」を 2 人置き、話している方だけ口が動いて弾む。
表情 (ふつう / 喜び / 驚き / 怒り / 困り / ドヤ) をセリフごとに切り替える。
キャラクターはこのプログラムが図形から描くオリジナル (既存作品の素材は使わない)。
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
from .animate import MOUTH_LEVELS, _camera
from .config import FPS

LINE = (60, 40, 35)
SKIN = (255, 228, 204)

# 見た目 (髪色, 髪型, 飾りの色)
LOOKS = {
    "ミカン": {"hair": (236, 138, 40), "style": "bob", "accent": (90, 180, 80)},
    "ソラ": {"hair": (70, 110, 200), "style": "twin", "accent": (250, 210, 60)},
}
EXPRESSIONS = ("normal", "happy", "surprised", "angry", "troubled", "smug")
DEFAULT_CAST = [{"name": "ミカン", "side": "left"}, {"name": "ソラ", "side": "right"}]
DEFAULT_VOICES = {"ミカン": 8, "ソラ": 14}          # 春日部つむぎ / 冥鳴ひまり
DEFAULT_COLORS = {"ミカン": "#E8590C", "ソラ": "#1C5FD4"}


@lru_cache(maxsize=256)
def head_sprite(name: str, size: int, mouth: int, blink: bool, expr: str, flip: bool) -> Image.Image:
    look = LOOKS.get(name) or list(LOOKS.values())[sum(map(ord, name)) % len(LOOKS)]
    hair, accent = look["hair"], look["accent"]
    S = size * 2
    W, H = int(S * 1.5), int(S * 1.3)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(5, S // 60)
    cx, cy = W / 2, H * 0.56
    rx, ry = S * 0.5, S * 0.43          # まんじゅう型の顔
    dark = tuple(int(v * 0.7) for v in hair)

    # 後ろ髪
    if look["style"] == "twin":
        for sx in (-1, 1):
            d.ellipse([cx + sx * rx * 1.05 - S * 0.16, cy - ry * 0.5, cx + sx * rx * 1.05 + S * 0.16, cy + ry * 1.15],
                      fill=hair, outline=LINE, width=lw)
            d.ellipse([cx + sx * rx * 0.9 - S * 0.07, cy - ry * 0.62, cx + sx * rx * 0.9 + S * 0.07, cy - ry * 0.36],
                      fill=accent, outline=LINE, width=lw)
    else:
        d.ellipse([cx - rx * 1.12, cy - ry * 1.05, cx + rx * 1.12, cy + ry * 1.0], fill=hair, outline=LINE, width=lw)
    # 顔
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=SKIN, outline=LINE, width=lw)
    # 前髪
    d.chord([cx - rx * 1.03, cy - ry * 1.12, cx + rx * 1.03, cy + ry * 0.35], 180, 360, fill=hair, outline=LINE, width=lw)
    for k in range(5):
        x0 = cx - rx * 0.95 + k * rx * 0.38
        d.polygon([(x0, cy - ry * 0.4), (x0 + rx * 0.38, cy - ry * 0.4), (x0 + rx * 0.16, cy - ry * 0.12)], fill=hair)
    d.arc([cx - rx * 0.6, cy - ry * 1.0, cx + rx * 0.3, cy - ry * 0.3], 200, 280, fill=dark, width=lw)
    if look["style"] == "bob":  # 葉っぱの髪飾り
        lx, ly = cx + rx * 0.55, cy - ry * 0.78
        d.ellipse([lx - S * 0.09, ly - S * 0.05, lx + S * 0.09, ly + S * 0.05], fill=accent, outline=LINE, width=lw)
        d.line([(lx - S * 0.08, ly), (lx + S * 0.08, ly)], fill=LINE, width=max(2, lw // 2))

    # 眉と目
    ey, ex = cy + ry * 0.12, rx * 0.42
    for sx in (-1, 1):
        x = cx + sx * ex
        tilt = {"angry": 1, "smug": 0.4, "troubled": -1}.get(expr, 0) * ry * 0.12
        by = ey - ry * 0.34
        d.line([(x - rx * 0.16, by + sx * tilt), (x + rx * 0.16, by - sx * tilt)], fill=LINE, width=lw + 2)
        if blink or expr == "happy":
            d.arc([x - rx * 0.15, ey - ry * 0.12, x + rx * 0.15, ey + ry * 0.2], 200, 340, fill=LINE, width=lw + 2)
        elif expr == "surprised":
            d.ellipse([x - rx * 0.15, ey - ry * 0.24, x + rx * 0.15, ey + ry * 0.24], fill=(255, 255, 255),
                      outline=LINE, width=lw)
            d.ellipse([x - rx * 0.04, ey - ry * 0.06, x + rx * 0.04, ey + ry * 0.06], fill=(30, 25, 25))
        elif expr == "smug":
            d.chord([x - rx * 0.13, ey - ry * 0.2, x + rx * 0.13, ey + ry * 0.2], 0, 180, fill=(30, 25, 25))
            d.line([(x - rx * 0.15, ey), (x + rx * 0.15, ey)], fill=LINE, width=lw)
        else:
            d.ellipse([x - rx * 0.11, ey - ry * 0.2, x + rx * 0.11, ey + ry * 0.2], fill=(30, 25, 25))
            d.ellipse([x - rx * 0.05, ey - ry * 0.15, x + rx * 0.02, ey - ry * 0.04], fill=(255, 255, 255))
        d.ellipse([x - rx * 0.2, ey + ry * 0.3, x + rx * 0.12, ey + ry * 0.46], fill=(255, 175, 175))
    if expr == "troubled":  # 汗
        d.polygon([(cx + rx * 0.78, cy - ry * 0.5), (cx + rx * 0.7, cy - ry * 0.22), (cx + rx * 0.86, cy - ry * 0.22)],
                  fill=(120, 190, 255), outline=LINE)
    if expr == "angry":     # 怒りマーク
        ax, ay = cx - rx * 0.72, cy - ry * 0.62
        for a in range(4):
            ang = a * math.pi / 2 + math.pi / 4
            d.line([(ax + math.cos(ang) * S * 0.02, ay + math.sin(ang) * S * 0.02),
                    (ax + math.cos(ang) * S * 0.06, ay + math.sin(ang) * S * 0.06)], fill=(230, 40, 40), width=lw + 2)
    # 口
    m = mouth / (MOUTH_LEVELS - 1)
    my = cy + ry * 0.55
    if m < 0.08:
        if expr in ("angry", "troubled"):
            d.arc([cx - rx * 0.14, my, cx + rx * 0.14, my + ry * 0.2], 200, 340, fill=LINE, width=lw)
        elif expr == "smug":
            d.arc([cx - rx * 0.2, my - ry * 0.16, cx + rx * 0.14, my + ry * 0.06], 10, 150, fill=LINE, width=lw)
        else:
            d.arc([cx - rx * 0.16, my - ry * 0.14, cx + rx * 0.16, my + ry * 0.06], 20, 160, fill=LINE, width=lw)
    else:
        big = 1.35 if expr == "surprised" else 1.0
        mw, mh = rx * (0.16 + 0.12 * m) * big, ry * (0.06 + 0.3 * m) * big
        d.ellipse([cx - mw, my - mh * 0.5, cx + mw, my + mh], fill=(150, 40, 50), outline=LINE, width=lw)
        d.ellipse([cx - mw * 0.55, my + mh * 0.35, cx + mw * 0.55, my + mh * 0.95], fill=(240, 120, 130))
    im = im.resize((W // 2, H // 2), Image.LANCZOS)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    a = im.split()[3].filter(ImageFilter.MaxFilter(9))
    out = Image.new("RGBA", im.size, (255, 255, 255, 0))
    out.putalpha(a)
    out.alpha_composite(im)
    return out


def render_talk_clip(image: Path, out: Path, duration: float, camera: str, overlay: Path | None,
                     t0: float, env: np.ndarray, talk: dict) -> None:
    """背景 + 左右の顔キャラ。talk = {cast, speaker, expr, seed}"""
    W, H = config.WIDTH, config.HEIGHT
    frames = int(round(duration * FPS))
    base = Image.open(image).convert("RGB")
    telop = Image.open(overlay).convert("RGBA") if overlay else None
    cast = talk.get("cast") or DEFAULT_CAST
    speaker, expr = talk.get("speaker", ""), talk.get("expr", "normal")
    if expr not in EXPRESSIONS:
        expr = "normal"
    size = int(min(W, H) * 0.26)
    rnd = random.Random(talk.get("seed", 0))
    blink_next = {c["name"]: rnd.uniform(0.8, 3.0) for c in cast}
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
         "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    try:
        for f in range(frames):
            t = f / FPS
            p = f / max(1, frames - 1)
            gi = min(len(env) - 1, int((t0 + t) * FPS))
            level = float(env[gi]) if gi >= 0 else 0.0
            x, y, cw, ch = _camera(camera, p, base.width, base.height, W, H)
            frame = base.resize((W, H), Image.BILINEAR, box=(x, y, x + cw, y + ch)).convert("RGBA")
            for c in cast:
                name = c["name"]
                active = name == speaker
                blink = False
                if t >= blink_next[name]:
                    blink = t < blink_next[name] + 0.12
                    if not blink:
                        blink_next[name] = t + rnd.uniform(2.0, 4.5)
                mouth = int(round(min(1.0, level * 1.2) * (MOUTH_LEVELS - 1))) if active else 0
                spr = head_sprite(name, size if active else int(size * 0.9), mouth, blink,
                                  expr if active else "normal", c.get("side") == "right")
                # 話し始めにぴょんと跳ねて、話している間は小さく弾む
                hop = max(0.0, 1 - t / 0.25) * 26 if active else 0
                bob = (abs(math.sin(t * math.pi * 3.2)) * 9 * min(1, level * 3) + hop) if active else 0
                cx = W * (0.115 if c.get("side") != "right" else 0.885)
                sx = int(cx - spr.width / 2)
                sy = int(H * 1.035 - spr.height - bob)
                if not active:  # 聞いている方は少し暗く
                    dim = Image.new("RGBA", spr.size, (0, 0, 0, 0))
                    dim.paste((0, 0, 0, 70), (0, 0), spr.split()[3])
                    spr = Image.alpha_composite(spr, dim)
                frame.alpha_composite(spr, (sx, sy))
            if telop is not None:
                slide = -W * (1 - min(1, t / 0.3)) ** 2 if talk.get("slide", True) else 0
                if slide > -W:
                    frame.alpha_composite(telop, (int(slide), 0))
            proc.stdin.write(frame.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"talk clip failed: {out}")
