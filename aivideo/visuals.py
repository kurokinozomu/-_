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
import random
import time
import urllib.parse
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import Settings, log

# 画面に焼き込む画像は 1.2 倍の解像度で作り、ズーム時も文字がぼやけないようにする
IMG_W, IMG_H = 2304, 1296

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
    name = "pollinations"
    credit = "画像: AI生成 (Pollinations.ai / FLUX)"
    BASE = "https://image.pollinations.ai/prompt/"

    @classmethod
    def available(cls) -> bool:
        try:
            r = requests.get(cls.BASE + "test?width=64&height=64&nologo=true", timeout=15)
            return r.ok and r.headers.get("content-type", "").startswith("image")
        except Exception:
            return False

    def generate(self, prompt: str, seed: int) -> Image.Image:
        url = (self.BASE + urllib.parse.quote(prompt[:900])
               + f"?width=1920&height=1080&nologo=true&model=flux&seed={seed}")
        last = None
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=180)
                if r.ok and r.headers.get("content-type", "").startswith("image"):
                    return Image.open(io.BytesIO(r.content)).convert("RGB")
                last = f"HTTP {r.status_code}"
            except Exception as e:
                last = e
            time.sleep(3 * (attempt + 1))
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
def _fit_font(draw, text, font_path, max_w, start, min_size=40):
    size = start
    while size > min_size:
        f = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 6
    return ImageFont.truetype(font_path, min_size)


def compose_scene(base: Image.Image, text: str, font_path: str, accent: tuple, big: bool) -> Image.Image:
    """背景画像に字幕用の下部グラデーションとキーワードを重ねる。"""
    img = base.resize((IMG_W, IMG_H), Image.LANCZOS).convert("RGBA")
    W, H = img.size
    # 下部 (字幕エリア) を暗くして可読性を確保
    grad = np.zeros((H, W, 4), dtype=np.uint8)
    ys = np.clip((np.arange(H) - H * 0.62) / (H * 0.38), 0, 1) ** 1.4
    grad[..., 3] = (ys * 170).astype(np.uint8)[:, None]
    img = Image.alpha_composite(img, Image.fromarray(grad, "RGBA"))
    text = (text or "").strip()
    if text:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        if big:  # オフライン背景: 画面中央に大きく
            f = _fit_font(d, text, font_path, W * 0.82, 190)
            tw = d.textlength(text, font=f)
            x, y = (W - tw) / 2, H * 0.36
            bar_w = min(tw, W * 0.5)
            d.rounded_rectangle([W / 2 - bar_w / 2, y + f.size * 1.25, W / 2 + bar_w / 2,
                                 y + f.size * 1.25 + 14], 7, fill=(*accent, 255))
            d.text((x, y), text, font=f, fill=(255, 255, 255, 255),
                   stroke_width=max(4, f.size // 22), stroke_fill=(0, 0, 0, 200))
        else:  # AI 画像: 左上にラベル
            f = _fit_font(d, text, font_path, W * 0.6, 92)
            tw = d.textlength(text, font=f)
            x, y, p = W * 0.05, H * 0.07, 34
            d.rounded_rectangle([x - p, y - p * 0.6, x + tw + p, y + f.size * 1.2 + p * 0.4],
                                22, fill=(0, 0, 0, 150))
            d.rectangle([x - p, y - p * 0.6, x - p + 12, y + f.size * 1.2 + p * 0.4], fill=(*accent, 255))
            d.text((x, y), text, font=f, fill=(255, 255, 255, 255))
        img = Image.alpha_composite(img, layer)
    return img.convert("RGB")


def make_thumbnail(base: Image.Image, text: str, sub: str, font_path: str, out: Path) -> None:
    W, H = 1280, 720
    img = base.resize((W, H), Image.LANCZOS).convert("RGBA")
    shade = np.zeros((H, W, 4), dtype=np.uint8)
    shade[..., 3] = (np.clip(1.1 - np.linspace(0, 1, W), 0, 1) * 190).astype(np.uint8)[None, :]
    img = Image.alpha_composite(img, Image.fromarray(shade, "RGBA"))
    d = ImageDraw.Draw(img)
    text = (text or "").strip()
    lines = [text] if len(text) <= 7 else [text[: (len(text) + 1) // 2], text[(len(text) + 1) // 2:]]
    fonts = [_fit_font(d, ln, font_path, W * 0.86, 190, 60) for ln in lines]
    sf = _fit_font(d, sub, font_path, W * 0.8, 76, 36) if sub else None
    block = sum(int(f.size * 1.12) for f in fonts) + (int(sf.size * 1.35) + 20 if sf else 0)
    y = max(30, (H - block) // 2 - 10)
    for ln, f in zip(lines, fonts):
        d.text((56, y), ln, font=f, fill=(255, 230, 0), stroke_width=12, stroke_fill=(0, 0, 0))
        y += int(f.size * 1.12)
    if sub:
        f = sf
        tw = d.textlength(sub, font=f)
        d.rectangle([40, y + 20, 40 + tw + 40, y + 20 + f.size * 1.35], fill=(220, 20, 40))
        d.text((60, y + 20 + f.size * 0.12), sub, font=f, fill=(255, 255, 255))
    img.convert("RGB").save(out, quality=92)


class SceneImager:
    def __init__(self, settings: Settings, plan: dict, cache_dir: Path):
        self.settings = settings
        self.plan = plan
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        pal = plan.get("palette") or MOOD_PALETTES.get(plan.get("bgm_mood", "calm"))
        pal = [c for c in pal if isinstance(c, str) and c.startswith("#")] or MOOD_PALETTES["calm"]
        self.accent = _lighten(hex_rgb(pal[-1]), 0.1)
        self.procedural = ProceduralProvider(pal)
        self.ai = None
        if settings.visuals in ("auto", "pollinations"):
            log("AI画像生成 (Pollinations) の接続を確認中...")
            if PollinationsProvider.available():
                self.ai = PollinationsProvider()
                log("映像: Pollinations AI 画像生成")
            else:
                log("Pollinations に接続できないため、オフライン生成グラフィックを使用します。")
        self.used: set[str] = set()

    def base_image(self, scene: dict) -> Image.Image:
        prompt = f"{scene.get('visual_prompt', '')}, {self.plan.get('visual_style', '')}, no text, no watermark"
        seed = int(hashlib.sha1(scene["id"].encode() + prompt.encode()).hexdigest()[:7], 16)
        provider = self.ai or self.procedural
        key = hashlib.sha1(f"{provider.name}|{prompt}|{seed}".encode()).hexdigest()[:20]
        f = self.cache / f"{key}.png"
        if f.exists():
            self.used.add(provider.credit)
            return Image.open(f).convert("RGB")
        try:
            img = provider.generate(prompt, seed)
        except Exception as e:
            log(f"{scene['id']}: AI画像生成に失敗 ({e})。オフライン生成に切り替えます。")
            provider = self.procedural
            img = provider.generate(prompt, seed)
        self.used.add(provider.credit)
        img.save(f)
        return img

    def render(self, scene: dict, out: Path) -> Image.Image:
        base = self.base_image(scene)
        is_ai = self.ai is not None and base.size == (1920, 1080)
        compose_scene(base, scene.get("onscreen_text", ""), self.settings.font_path,
                      self.accent, big=not is_ai).save(out)
        return base
