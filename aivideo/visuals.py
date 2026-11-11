"""シーン画像の生成。

プロバイダ (AIVIDEO_VISUALS=auto):
  - pollinations : 無料・APIキー不要の AI 画像生成 (FLUX)。ネットワーク接続が必要。
  - procedural   : 完全オフライン。グラデーション/光/幾何学模様のモーショングラフィックス風背景を生成。
いずれも生成物のみを使うため、第三者の著作物は含まれない。
"""
from __future__ import annotations

import colorsys
import hashlib
import io
import math
import os
import random
import re
import time
import urllib.parse
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config
from .config import Settings, log

# 画面に焼き込む画像は 1.2 倍の解像度で作り、ズーム時も文字がぼやけないようにする
IMG_W, IMG_H = 2304, 1296


def set_canvas(width: int, height: int) -> None:
    """出力解像度に合わせて、画像の作成サイズ (1.2 倍) を切り替える。"""
    global IMG_W, IMG_H
    IMG_W, IMG_H = int(width * 1.2), int(height * 1.2)

MOOD_PALETTES = {
    "calm": ["#0f2b46", "#1f6f8b", "#99d6ea"],
    "upbeat": ["#ff6b6b", "#feca57", "#48dbfb"],
    "mysterious": ["#0b0b2b", "#3a1c71", "#b06ab3"],
    "epic": ["#1a0a00", "#8e2de2", "#ff512f"],
    "warm": ["#3e1f0d", "#e1703d", "#ffd28a"],
}


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore
    except ValueError:
        return (40, 60, 120)


class PollinationsProvider:
    """Pollinations.ai の無料枠 (登録不要)。

    無料枠の制限: 1 枚 / 45 秒 (IP ごと)、最大 1024x576、右下に小さなロゴ。
    制限に当たったら、サーバーが返す待ち時間だけ待って再試行する。
    """
    name = "pollinations"
    BASE = "https://image.pollinations.ai/prompt/"
    MIN_INTERVAL = 46.0

    def __init__(self):
        self.model = "sana"
        try:
            models = requests.get("https://image.pollinations.ai/models", timeout=15).json()
            if isinstance(models, list) and models:
                self.model = "flux" if "flux" in models else str(models[0])
        except Exception:
            pass
        self.credit = f"画像: AI生成 (Pollinations.ai / {self.model})"
        self._last = 0.0

    @classmethod
    def available(cls) -> bool:
        # 画像生成は無料枠を消費するため、モデル一覧で接続だけ確認する
        try:
            r = requests.get("https://image.pollinations.ai/models", timeout=15)
            return r.ok
        except Exception:
            return False

    def generate(self, prompt: str, seed: int) -> Image.Image:
        url = (self.BASE + urllib.parse.quote(prompt[:900])
               + f"?width={config.WIDTH}&height={config.HEIGHT}&nologo=true&model={self.model}&seed={seed}")
        last = None
        for attempt in range(6):
            wait = self.MIN_INTERVAL - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(url, timeout=180)
                self._last = time.time()
                if r.ok and r.headers.get("content-type", "").startswith("image"):
                    return Image.open(io.BytesIO(r.content)).convert("RGB")
                last = f"HTTP {r.status_code}"
                if r.status_code in (402, 429):
                    m = re.search(r"Retry after (\d+)", r.text)
                    time.sleep(int(m.group(1)) + 2 if m else 20)
                    self._last = 0.0
                    continue
            except Exception as e:
                last = e
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"pollinations failed: {last}")


class ProceduralProvider:
    name = "procedural"
    credit = "映像: 本システムによる自動生成グラフィック"

    def __init__(self, palette: list[str]):
        self.palette = [hex_rgb(c) for c in palette] or [hex_rgb(c) for c in MOOD_PALETTES["calm"]]

    def generate(self, prompt: str, seed: int) -> Image.Image:
        rnd = random.Random(seed)
        W, H = IMG_W, IMG_H
        pal = self.palette[:]
        rnd.shuffle(pal)
        c1, c2 = _darken(pal[0], 0.45), _darken(pal[1 % len(pal)], 0.8)
        accent = _lighten(pal[2 % len(pal)], 0.2)

        # 斜めグラデーション
        ang = rnd.uniform(0, np.pi)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        t = (xx / W) * np.cos(ang) + (yy / H) * np.sin(ang)
        t = (t - t.min()) / (np.ptp(t) + 1e-6)
        img = (np.array(c1)[None, None] * (1 - t[..., None]) + np.array(c2)[None, None] * t[..., None])
        base = Image.fromarray(img.astype(np.uint8))

        # 大きな光のにじみ
        glow = Image.new("RGB", (W, H), (0, 0, 0))
        g = ImageDraw.Draw(glow)
        for _ in range(rnd.randint(3, 6)):
            r = rnd.randint(H // 6, H // 2)
            x, y = rnd.randint(0, W), rnd.randint(0, H)
            col = _lighten(rnd.choice(pal), rnd.uniform(0.0, 0.4))
            g.ellipse([x - r, y - r, x + r, y + r], fill=col)
        glow = glow.filter(ImageFilter.GaussianBlur(160))
        base = Image.blend(base, Image.composite(glow, base, glow.convert("L")), 0.55)

        # モチーフ（シーンごとに変化）
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        motif = rnd.choice(["rings", "grid", "particles", "waves", "diagonal", "hexes"])
        a = (*accent, 70)
        if motif == "rings":
            cx, cy = rnd.randint(W // 4, 3 * W // 4), rnd.randint(H // 4, 3 * H // 4)
            for k in range(1, 14):
                r = k * rnd.randint(70, 110)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=a, width=3)
        elif motif == "grid":
            step = rnd.randint(90, 150)
            for x in range(0, W, step):
                d.line([(x, 0), (x, H)], fill=(*accent, 40), width=2)
            for y in range(0, H, step):
                d.line([(0, y), (W, y)], fill=(*accent, 40), width=2)
            for _ in range(25):
                x, y = rnd.randrange(0, W, step), rnd.randrange(0, H, step)
                d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(*accent, 180))
        elif motif == "particles":
            for _ in range(260):
                r = rnd.choice([2, 3, 4, 6, 10])
                x, y = rnd.randint(0, W), rnd.randint(0, H)
                d.ellipse([x - r, y - r, x + r, y + r], fill=(*accent, rnd.randint(40, 200)))
        elif motif == "waves":
            for k in range(14):
                pts = []
                off, amp, fr = rnd.uniform(0, 6), rnd.uniform(30, 90), rnd.uniform(1.5, 3.5)
                y0 = H * (0.15 + 0.05 * k)
                for x in range(0, W + 20, 20):
                    pts.append((x, y0 + amp * np.sin(off + fr * x / W * 2 * np.pi)))
                d.line(pts, fill=a, width=3)
        elif motif == "diagonal":
            for k in range(-H, W, rnd.randint(60, 120)):
                d.line([(k, 0), (k + H, H)], fill=(*accent, 35), width=rnd.choice([2, 4, 10]))
        else:  # hexes
            s = rnd.randint(70, 110)
            for row in range(-1, H // s + 2):
                for col in range(-1, W // s + 2):
                    if rnd.random() < 0.55:
                        continue
                    cx = col * s * 1.73 + (row % 2) * s * 0.87
                    cy = row * s * 1.5
                    pts = [(cx + s * np.cos(np.pi / 3 * i + np.pi / 6),
                            cy + s * np.sin(np.pi / 3 * i + np.pi / 6)) for i in range(6)]
                    d.polygon(pts, outline=a, width=3)
        layer = layer.filter(ImageFilter.GaussianBlur(1.2))
        base = Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")

        # 粒子感 + ビネット
        arr = np.asarray(base).astype(np.float32)
        arr += np.random.default_rng(seed).normal(0, 4, arr.shape)
        v = ((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2)
        arr *= (1 - 0.9 * v)[..., None]
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _darken(c, f):
    return tuple(int(v * f) for v in c)


def _lighten(c, f):
    h, l, s = colorsys.rgb_to_hls(*[v / 255 for v in c])
    r, g, b = colorsys.hls_to_rgb(h, min(1, l + f), s)
    return (int(r * 255), int(g * 255), int(b * 255))


# ------------------------------------------------------------------ 合成
def vivid(c, l_min=0.32, l_max=0.5, s_min=0.7):
    h, l, s = colorsys.rgb_to_hls(*[v / 255 for v in c])
    r, g, b = colorsys.hls_to_rgb(h, min(l_max, max(l_min, l)), max(s, s_min))
    return (int(r * 255), int(g * 255), int(b * 255))


def _fit_font(draw, text, font_path, max_w, start, min_size=40):
    size = start
    while size > min_size:
        f = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return ImageFont.truetype(font_path, min_size)


def sticker(img: Image.Image, border: int = 14, shadow: int = 18) -> Image.Image:
    """イラストに白フチとドロップシャドウをつける (ステッカー風)。"""
    pad = border + shadow * 2
    W, H = img.size
    canvas = Image.new("RGBA", (W + pad * 2, H + pad * 2), (0, 0, 0, 0))
    alpha = Image.new("L", canvas.size, 0)
    alpha.paste(img.split()[3], (pad, pad))
    edge = alpha.filter(ImageFilter.MaxFilter(border * 2 + 1)).filter(ImageFilter.GaussianBlur(1.5))
    sh = edge.filter(ImageFilter.GaussianBlur(shadow)).point(lambda v: int(v * 0.55))
    canvas.paste((0, 0, 0, 255), (shadow // 2, shadow), sh)
    canvas.paste((255, 255, 255, 255), (0, 0), edge)
    canvas.alpha_composite(img, (pad, pad))
    return canvas


def sunburst(size, center, c1, c2, rays=22, rot=0.0) -> Image.Image:
    """バラエティ番組風の集中線 (放射状の背景)。"""
    W, H = size
    img = Image.new("RGB", size, c1)
    d = ImageDraw.Draw(img)
    R = int(np.hypot(W, H))
    cx, cy = center
    step = 2 * np.pi / rays
    for k in range(rays):
        if k % 2:
            continue
        a0, a1 = rot + k * step, rot + (k + 1) * step
        d.polygon([(cx, cy), (cx + R * np.cos(a0), cy + R * np.sin(a0)),
                   (cx + R * np.cos(a1), cy + R * np.sin(a1))], fill=c2)
    return img


def radial_glow(size, center, color, radius, strength=0.8) -> Image.Image:
    W, H = size
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.hypot(xx - center[0], yy - center[1]) / radius
    a = np.clip(1 - dist, 0, 1) ** 1.6 * strength
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    arr[..., :3] = color
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def illustration_scene(emojis: list[str], palette: list[tuple], seed: int,
                       size=None) -> Image.Image | None:
    """絵文字イラストを使った、シーン内容に合わせた背景イラスト。"""
    from . import assets
    rnd = random.Random(seed)
    W, H = size = size or (IMG_W, IMG_H)
    tall = H > W
    main_size = int(W * 0.52) if tall else int(H * 0.46)
    side_ratio = 0.45 if H > W else 0.55
    imgs = [assets.emoji_image(e, main_size if i == 0 else int(main_size * side_ratio))
            for i, e in enumerate(emojis[:3])]
    imgs = [im for im in imgs if im is not None]
    if not imgs:
        return None
    base_c = vivid(palette[rnd.randrange(len(palette))], 0.2, 0.32, 0.55)
    ray_c = _lighten(base_c, 0.07)
    layout = "center" if tall else rnd.choice(["center", "left", "right"])
    cx = {"center": W * 0.5, "left": W * 0.36, "right": W * 0.64}[layout]
    cy = H * (0.47 if tall else 0.49)
    style = rnd.choice(["rays", "rays", "dots", "plain"])
    if style == "rays":
        bg = sunburst(size, (cx, cy), base_c, ray_c, rays=rnd.choice([20, 24, 28]), rot=rnd.random())
    else:
        bg = Image.new("RGB", size, base_c)
        if style == "dots":
            d = ImageDraw.Draw(bg)
            step = 64
            for y in range(0, H + step, step):
                for x in range((y // step % 2) * step // 2, W + step, step):
                    d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=ray_c)
    bg = bg.convert("RGBA")
    bg.alpha_composite(radial_glow(size, (cx, cy), _lighten(base_c, 0.45), H * 0.62, 0.75))
    # 周辺を少し暗く
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = ((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2)
    vig = np.zeros((H, W, 4), dtype=np.uint8)
    vig[..., 3] = np.clip(v * 1.6 * 255, 0, 200).astype(np.uint8)
    bg.alpha_composite(Image.fromarray(vig, "RGBA"))

    main = sticker(imgs[0])
    bg.alpha_composite(main, (int(cx - main.width / 2), int(cy - main.height / 2)))
    if tall:  # 縦長: 上下に散らす (中央は字幕、右下はショートのボタン類)
        side = [(W * 0.2, H * 0.29), (W * 0.8, H * 0.29)]
    elif layout == "center":
        side = [(W * 0.17, H * 0.4), (W * 0.83, H * 0.4)]
    else:
        sx = W * 0.79 if layout == "left" else W * 0.21
        side = [(sx, H * 0.3), (sx, H * 0.62)] if len(imgs) > 2 else [(sx, H * 0.42)]
    for im, (sx, sy) in zip(imgs[1:], side):
        st = sticker(im, 10, 12).rotate(rnd.uniform(-12, 12), resample=Image.BICUBIC, expand=True)
        bg.alpha_composite(st, (int(sx - st.width / 2), int(sy - st.height / 2)))
    return bg.convert("RGB")


def telop(img: Image.Image, text: str, font_path: str, color: tuple) -> None:
    """テレビ番組風の見出しテロップ (左上の色帯 + 白文字)。"""
    if not text:
        return
    W, H = img.size
    d = ImageDraw.Draw(img)
    tall = H > W
    f = _fit_font(d, text, font_path, W * (0.82 if tall else 0.62),
                  int(min(H * 0.085, W * 0.1)), 36)
    tw = d.textlength(text, font=f)
    x, y = int(W * 0.06), int(H * (0.12 if tall else 0.07))
    px, py = int(f.size * 0.45), int(f.size * 0.28)
    box = [x - px, y - py, x + tw + px, y + f.size * 1.1 + py]
    d.polygon([(box[0] + 4, box[1] + 10), (box[2] + 24, box[1] + 10), (box[2] + 4, box[3] + 10),
               (box[0] - 16, box[3] + 10)], fill=(0, 0, 0, 110))
    d.polygon([(box[0], box[1]), (box[2] + 20, box[1]), (box[2], box[3]), (box[0] - 20, box[3])],
              fill=(*color, 255))
    d.rectangle([box[0] - 20, box[3] - 10, box[2], box[3]], fill=(255, 255, 255, 255))
    d.text((x, y), text, font=f, fill=(255, 255, 255, 255), stroke_width=max(3, f.size // 16),
           stroke_fill=(0, 0, 0, 255))


def compose_scene(base: Image.Image, text: str, font_path: str, accent: tuple, big: bool,
                  heavy_font: str | None = None, top_shade: bool = False) -> Image.Image:
    """背景に字幕エリアのグラデーションを重ねる (テロップは telop_overlay で別に作る)。"""
    img = base.resize((IMG_W, IMG_H), Image.LANCZOS)
    if base.width < IMG_W * 0.6:  # 小さい画像 (無料枠の AI 画像) は拡大後に軽くシャープに
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    img = img.convert("RGBA")
    W, H = img.size
    grad = np.zeros((H, W, 4), dtype=np.uint8)
    ys = np.clip((np.arange(H) - H * 0.7) / (H * 0.3), 0, 1) ** 1.5
    if top_shade:  # 上部のカウンターを読みやすく
        ys = np.maximum(ys, np.clip((H * 0.42 - np.arange(H)) / (H * 0.42), 0, 1) ** 1.2 * 1.1)
    grad[..., 3] = (np.clip(ys, 0, 1) * 130).astype(np.uint8)[:, None]
    img = Image.alpha_composite(img, Image.fromarray(grad, "RGBA"))
    text = (text or "").strip()
    if text and big:  # イラストなしのオフライン背景: 中央に大きく
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        f = _fit_font(d, text, heavy_font or font_path, W * 0.82, 190)
        tw = d.textlength(text, font=f)
        d.text(((W - tw) / 2, H * 0.36), text, font=f, fill=(255, 255, 255, 255),
               stroke_width=max(5, f.size // 18), stroke_fill=(0, 0, 0, 230))
        img = Image.alpha_composite(img, layer)
    return img.convert("RGB")


def telop_overlay(text: str, font_path: str, accent: tuple, out: Path) -> bool:
    """カメラの動きに影響されない、画面固定の見出しテロップ (透過 PNG, 出力解像度)。"""
    text = (text or "").strip()
    if not text:
        return False
    img = Image.new("RGBA", (config.WIDTH, config.HEIGHT), (0, 0, 0, 0))
    telop(img, text, font_path, vivid(accent, 0.38, 0.48, 0.8))
    img.save(out)
    return True


def _draw_runs(d, x, y, runs, f, outer_w):
    """[(文字列, 塗り, 内フチ, 外フチ)] を横に並べて描く (二重フチ文字)。"""
    cx = x
    for txt, fill, inner, outer in runs:
        d.text((cx, y), txt, font=f, fill=outer, stroke_width=outer_w, stroke_fill=outer)
        cx += d.textlength(txt, font=f)
    cx = x
    for txt, fill, inner, outer in runs:
        d.text((cx, y), txt, font=f, fill=fill, stroke_width=max(4, outer_w // 2), stroke_fill=inner)
        cx += d.textlength(txt, font=f)


def make_thumbnail(base: Image.Image | None, th: dict, font_path: str, heavy_font: str | None,
                   palette: list[tuple], out: Path) -> None:
    """情報量が多く目を引くサムネイル: ラベル / 二段の大見出し / 強調語 / バッジ / イラスト / 下帯。"""
    from . import assets
    W, H = 1280, 720
    hf = heavy_font or font_path
    red, yellow, white, black = (225, 20, 40), (255, 228, 0), (255, 255, 255), (0, 0, 0)
    main_c = vivid(palette[0] if palette else (200, 30, 40), 0.3, 0.42, 0.75)
    if base is not None:
        img = base.resize((W, H), Image.LANCZOS).convert("RGBA")
    else:
        img = sunburst((W, H), (W * 0.74, H * 0.45), main_c, _lighten(main_c, 0.1), 26, 0.2).convert("RGBA")
        img.alpha_composite(radial_glow((W, H), (W * 0.74, H * 0.45), _lighten(main_c, 0.4), 520, 0.85))
    # イラスト (右側)
    emojis = th.get("emoji") or []
    for i, e in enumerate(emojis[:2]):
        em = assets.emoji_image(e, 400 if i == 0 else 230)
        if em is None:
            continue
        st = sticker(em, 12, 14)
        if i:
            st = st.rotate(-10, resample=Image.BICUBIC, expand=True)
        pos = (W - st.width + 10, H // 2 - st.height // 2 + 70) if i == 0 else (W - 560, H - st.height - 60)
        img.alpha_composite(st, pos)
    # 左側を暗くして文字を読みやすく
    shade = np.zeros((H, W, 4), dtype=np.uint8)
    shade[..., 3] = (np.clip(1.0 - np.linspace(0, 1.35, W), 0, 1) * 200).astype(np.uint8)[None, :]
    img.alpha_composite(Image.fromarray(shade, "RGBA"))
    d = ImageDraw.Draw(img)

    y = 26
    label = (th.get("label") or "").strip()
    if label:
        f = ImageFont.truetype(hf, 50)
        tw = d.textlength(label, font=f)
        d.rectangle([28, y, 28 + tw + 44, y + 74], fill=yellow)
        d.rectangle([22, y - 6, 22 + tw + 44, y + 68], fill=red)
        d.text((44, y + 2), label, font=f, fill=white)
        y += 96
    emph = (th.get("emphasis") or "").strip()
    lines = [(th.get("line1") or th.get("text") or "").strip(), (th.get("line2") or "").strip()]
    styles = [(white, black, main_c), (yellow, black, black)]
    max_w = W * (0.64 if emojis else 0.9)
    sub_h = 120 if (th.get("sub_text") or "").strip() else 30
    fonts = [_fit_font(d, ln, hf, max_w, 170, 60) if ln else None for ln in lines]
    block = sum(int(f.size * 1.18) for f in fonts if f)
    y = y + max(0, (H - sub_h - y - block) // 2)
    for ln, f, (fill, inner, outer) in zip(lines, fonts, styles):
        if not ln:
            continue
        runs = []
        if emph and emph in ln:
            a, b = ln.split(emph, 1)
            runs = [(a, fill, inner, outer), (emph, red, white, black), (b, fill, inner, outer)]
        else:
            runs = [(ln, fill, inner, outer)]
        _draw_runs(d, 40, y, [r for r in runs if r[0]], f, 18)
        y += int(f.size * 1.18)
    # 下帯
    sub = (th.get("sub_text") or "").strip()
    if sub:
        f = _fit_font(d, sub, hf, W * 0.8, 58, 30)
        tw = d.textlength(sub, font=f)
        bh = int(f.size * 1.5)
        d.rectangle([0, H - bh - 22, tw + 90, H - 22], fill=(0, 0, 0))
        d.rectangle([0, H - bh - 22, 16, H - 22], fill=red)
        d.text((48, H - bh - 22 + (bh - f.size) // 2 - 4), sub, font=f, fill=yellow)
    # バッジ
    badge = (th.get("badge") or "").strip()[:4]
    if badge:
        r = 92
        bd = Image.new("RGBA", (r * 2 + 20, r * 2 + 20), (0, 0, 0, 0))
        b = ImageDraw.Draw(bd)
        b.ellipse([10, 10, 10 + 2 * r, 10 + 2 * r], fill=red, outline=white, width=8)
        rows = [badge] if len(badge) <= 2 else [badge[:2], badge[2:]]
        f = ImageFont.truetype(hf, 62 if len(rows) == 1 else 50)
        ty = 10 + r - len(rows) * f.size * 0.58
        for row in rows:
            tw = b.textlength(row, font=f)
            b.text((10 + r - tw / 2, ty), row, font=f, fill=white)
            ty += f.size * 1.1
        bd = bd.rotate(12, resample=Image.BICUBIC, expand=True)
        img.alpha_composite(bd, (W - bd.width - 18, 8))
    img.convert("RGB").save(out, quality=92)


# ------------------------------------------------------------------ ランキング (〇〇10選)
RANK_YELLOW, RANK_YELLOW2, RANK_RED = (255, 232, 70), (255, 214, 30), (225, 25, 40)


def _wrap_px(d, text: str, font, max_w: float) -> list[str]:
    """表示幅で折り返す。読点や助詞の後など、自然な位置で改行する。"""
    from .subtitles import best_split
    cap = max(4, int(max_w / font.size))
    lines = []
    while len(text) > cap:
        i = best_split(text, cap, max(2, cap - 6), cap)
        lines.append(text[:i])
        text = text[i:].lstrip("　 ")
    if text:
        lines.append(text)
    return lines


def _phrase_lines(text: str, per: int) -> list[str]:
    from .subtitles import best_split
    out = []
    while len(text) > per:
        i = best_split(text, per, max(2, per - 3), per)
        out.append(text[:i])
        text = text[i:]
    return out + ([text] if text else [])


def _outlined(d, xy, text, font, fill, inner=(0, 0, 0), outer=None, w=10, anchor="mm"):
    if outer:
        d.text(xy, text, font=font, fill=outer, stroke_width=w * 2, stroke_fill=outer, anchor=anchor)
    d.text(xy, text, font=font, fill=fill, stroke_width=w, stroke_fill=inner, anchor=anchor)


def ranking_scene(scene: dict, plan: dict, heavy: str, rounded: str, all_emoji: list[str]) -> Image.Image:
    """掲示板まとめ風ランキングの 1 画面 (黄色の集中線 / 第N位 / 品名 / 書き込み / イラスト)。"""
    from . import assets
    W, H = IMG_W, IMG_H
    tall = H > W
    img = sunburst((W, H), (W / 2, H * 0.5), RANK_YELLOW, RANK_YELLOW2, rays=30).convert("RGBA")
    img.alpha_composite(radial_glow((W, H), (W / 2, H * 0.5), (255, 250, 210), H * 0.45, 0.6))
    d = ImageDraw.Draw(img)
    rk = plan.get("ranking", {})
    rank = scene.get("rank")
    if rank in (None, "", 0):  # タイトル画面
        title = (rk.get("title") or plan.get("theme", ""))[:20]
        per = 6 if tall else 10
        lines = _phrase_lines(title, per)
        y = H * (0.12 if tall else 0.14)
        for ln in lines + ([rk["sub"]] if rk.get("sub") else []):
            is_sub = ln == rk.get("sub")
            f = _fit_font(d, ln, heavy, W * 0.9, int(W * (0.15 if tall else 0.08)), 40)
            _outlined(d, (W / 2, y + f.size / 2), ln, f, (20, 20, 20) if is_sub else RANK_RED,
                      inner=(255, 255, 255), outer=(0, 0, 0) if not is_sub else None, w=max(6, f.size // 14))
            y += f.size * 1.15
        # イラストを寄せ集めて置く
        rnd = random.Random(len(title))
        picks = [e for e in dict.fromkeys(all_emoji) if e][:7]
        top, bottom = y + H * 0.02, H * (0.62 if tall else 0.85)
        cx0, cy0 = W / 2, (top + bottom) / 2
        span = max(80.0, bottom - top)
        isz = int(min(W * (0.24 if tall else 0.12), span * 0.36))
        for i, e in enumerate(picks):
            em = assets.emoji_image(e, isz)
            if em is None:
                continue
            ang = (i - 1) / max(1, len(picks) - 1) * 2 * math.pi
            rad = (span * 0.32) * (0 if i == 0 else 1)
            st = sticker(em, 8, 10).rotate(rnd.uniform(-15, 15), resample=Image.BICUBIC, expand=True)
            img.alpha_composite(st, (int(cx0 + rad * 1.5 * math.cos(ang) - st.width / 2),
                                     int(cy0 + rad * math.sin(ang) - st.height / 2)))
        return img.convert("RGB")

    # 第N位
    f = ImageFont.truetype(heavy, int(W * (0.16 if tall else 0.085)))
    y_rank = H * (0.12 if tall else 0.13)
    _outlined(d, (W / 2, y_rank), f"第{rank}位", f, (255, 255, 255), inner=(0, 0, 0), w=max(8, f.size // 16))
    # 品名
    item = str(scene.get("item") or "")
    fi = _fit_font(d, item, heavy, W * 0.9, int(W * (0.11 if tall else 0.06)), 40)
    y_item = y_rank + f.size * 0.62 + fi.size * 0.75
    _outlined(d, (W / 2, y_item), item, fi, RANK_RED, inner=(255, 255, 255), outer=(0, 0, 0),
              w=max(6, fi.size // 14))
    # 書き込み風コメント (白い箱・赤枠)
    comment = str(scene.get("comment") or "")
    y = y_item + fi.size * 0.85
    if comment:
        fc = ImageFont.truetype(rounded, int(W * (0.055 if tall else 0.03)))
        bw = W * (0.8 if tall else 0.5)
        lines = _wrap_px(d, comment, fc, bw - fc.size * 1.2)[:3]
        bh = len(lines) * fc.size * 1.35 + fc.size * 0.9
        x0 = (W - bw) / 2
        d.rectangle([x0 + 10, y + 10, x0 + bw + 10, y + bh + 10], fill=(0, 0, 0, 90))
        d.rectangle([x0, y, x0 + bw, y + bh], fill=(255, 255, 255), outline=RANK_RED, width=max(6, W // 160))
        ty = y + fc.size * 0.45
        for ln in lines:
            d.text((x0 + fc.size * 0.6, ty), ln, font=fc, fill=(20, 20, 20))
            ty += fc.size * 1.35
        y += bh
    # イラスト: コメント箱の下から字幕の上までの空きに収まる大きさで置く
    bottom_limit = H * (0.62 if tall else 0.8)
    space = bottom_limit - y - H * 0.03
    size = int(min(W * (0.5 if tall else 0.24), space - 60))
    em = None
    for e in scene.get("emoji") or []:
        em = assets.emoji_image(e, max(120, size))
        if em is not None:
            break
    if em is not None:
        st = sticker(em, 14, 18)
        cy = y + H * 0.02 + (bottom_limit - y - H * 0.02) / 2
        img.alpha_composite(st, (int(W / 2 - st.width / 2), int(cy - st.height / 2)))
    return img.convert("RGB")


class SceneImager:
    def __init__(self, settings: Settings, plan: dict, cache_dir: Path):
        from . import assets
        self.settings = settings
        self.plan = plan
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        pal = plan.get("palette") or MOOD_PALETTES.get(plan.get("bgm_mood", "calm"))
        pal = [c for c in pal if isinstance(c, str) and c.startswith("#")] or MOOD_PALETTES["calm"]
        self.palette = [hex_rgb(c) for c in pal]
        self.accent = _lighten(hex_rgb(pal[-1]), 0.1)
        self.procedural = ProceduralProvider(pal)
        hv = assets.font("heavy")
        self.heavy_font = hv[0] if hv else None
        self.illustrations = settings.visuals in ("auto", "procedural", "illustration") and assets.emoji_available()
        self.ai = None
        if settings.visuals in ("auto", "pollinations"):
            log("AI画像生成 (Pollinations) の接続を確認中...")
            if PollinationsProvider.available():
                self.ai = PollinationsProvider()
                log("映像: Pollinations AI 画像生成")
            else:
                log("Pollinations に接続できないため、"
                    + ("シーン内容に合わせたイラストを使用します。" if self.illustrations
                       else "オフライン生成グラフィックを使用します。"))
        self.used: set[str] = set()
        self.first_ai: Image.Image | None = None

    def plan_scenes(self) -> list[dict]:
        return [sc for ch in self.plan.get("chapters", []) for sc in ch.get("scenes", [])]

    def _use_ai(self, scene: dict) -> bool:
        """無料枠は 45 秒に 1 枚なので、AI 画像は章の頭と 2 シーンに 1 回にして、
        残りはシーン内容に合わせたイラストにする (AIVIDEO_AI_EVERY で変更可)。"""
        every = max(1, int(os.environ.get("AIVIDEO_AI_EVERY", "2") or 2))
        if not self.illustrations or not scene.get("emoji"):
            return True
        idx = int(scene["id"].lstrip("s") or 0)
        return scene.get("_chapter_first", False) or idx % every == 0

    def _ai_image(self, prompt: str, seed: int) -> Image.Image | None:
        key = hashlib.sha1(f"pollinations|{prompt}|{seed}".encode()).hexdigest()[:20]
        f = self.cache / f"{key}.png"
        if f.exists():
            return Image.open(f).convert("RGB")
        try:
            img = self.ai.generate(prompt, seed)
        except Exception as e:
            log(f"AI画像生成に失敗 ({e})。イラストに切り替えます。")
            return None
        img.save(f)
        return img

    def base_image(self, scene: dict) -> tuple[Image.Image, str]:
        """(画像, 種類 'ai' | 'illustration' | 'procedural') を返す。"""
        prompt = f"{scene.get('visual_prompt', '')}, {self.plan.get('visual_style', '')}, no text, no watermark"
        seed = int(hashlib.sha1(scene["id"].encode() + prompt.encode()).hexdigest()[:7], 16)
        if self.ai and self._use_ai(scene):
            img = self._ai_image(prompt, seed)
            if img is not None:
                self.used.add(self.ai.credit)
                if self.first_ai is None:
                    self.first_ai = img
                return img, "ai"
        if self.illustrations and scene.get("emoji"):
            img = illustration_scene(scene["emoji"], self.palette, seed)
            if img is not None:
                self.used.add(ILLUSTRATION_CREDIT)
                return img, "illustration"
        self.used.add(self.procedural.credit)
        return self.procedural.generate(prompt, seed), "procedural"

    def render(self, scene: dict, out: Path) -> Path | None:
        """背景画像を out に保存し、テロップがあればその透過 PNG のパスを返す。"""
        if self.plan.get("ranking"):
            from . import assets
            rb = assets.font("rounded_black") or assets.font("subtitle")
            all_emoji = [e for sc in self.plan_scenes() for e in (sc.get("emoji") or [])[:1]]
            ranking_scene(scene, self.plan, self.heavy_font or self.settings.font_path,
                          rb[0] if rb else self.settings.font_path, all_emoji).save(out)
            self.used.add(ILLUSTRATION_CREDIT)
            return None
        base, kind = self.base_image(scene)
        big = kind == "procedural"
        compose_scene(base, scene.get("onscreen_text", ""), self.settings.font_path,
                      self.accent, big=big and not self.plan.get("hud"), heavy_font=self.heavy_font,
                      top_shade=bool(self.plan.get("hud"))).save(out)
        tel = out.with_name(out.stem + "_telop.png")
        if not big and telop_overlay(scene.get("onscreen_text", ""), self.heavy_font or self.settings.font_path,
                                     self.accent, tel):
            return tel
        return None

    def thumbnail(self, out: Path) -> None:
        th = self.plan.get("thumbnail", {})
        # 冒頭シーンの AI 画像を優先 (テーマに直結し、無料枠も節約できる)
        base = self.first_ai
        if base is None and self.ai and th.get("image_prompt"):
            base = self._ai_image(f"{th['image_prompt']}, {self.plan.get('visual_style', '')}, "
                                  "no text, no watermark", 7)
        make_thumbnail(base, th, self.settings.font_path, self.heavy_font, self.palette, out)


ILLUSTRATION_CREDIT = "イラスト: Noto Emoji (Google, Apache License 2.0)"
