"""ブランド素材を生成する (すべてプログラムで描画したオリジナル。外部素材なし)。

python youtube_automation/branding/make_assets.py
出力: youtube_automation/branding/out/
  icon_800.png (プロフィール 800x800・円形に切り抜かれても欠けない)
  banner_2560x1440.png (安全領域 1546x423 の中に文字)
  watermark_150.png (動画の透かし。透過 PNG)
  logo_1920.png (動画用ロゴ)
  thumb_template_1280x720.png (サムネイルの基本レイアウト)
  opening_1920x1080.png / ending_1920x1080.png (オープニング・エンディングの静止画)
  preview_devices.png (スマホ・PC・テレビでのバナーの見え方の確認)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from aivideo import assets  # noqa: E402

CH = json.loads((ROOT / "youtube_automation/config/channel.json").read_text(encoding="utf-8"))
C = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in CH["brand"]["colors"].items()}
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    f = assets.font(kind)
    return ImageFont.truetype(f[0], size)


def washi(w: int, h: int, base=C["kinari"]) -> Image.Image:
    """和紙風の生成り地 (ノイズ + 繊維)。"""
    import random
    rnd = random.Random(7)
    im = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(im)
    for _ in range(int(w * h / 900)):
        x, y = rnd.randrange(w), rnd.randrange(h)
        l = rnd.randint(4, 18)
        a = rnd.random() * math.pi
        shade = rnd.randint(-14, 8)
        col = tuple(max(0, min(255, c + shade)) for c in base)
        d.line([(x, y), (x + l * math.cos(a), y + l * math.sin(a))], fill=col, width=1)
    return im.filter(ImageFilter.GaussianBlur(0.6))


def seigaiha(d: ImageDraw.ImageDraw, box, color, r=46, width=3):
    """青海波 (伝統文様。著作権の対象外) を枠内に描く。"""
    x0, y0, x1, y1 = box
    row = 0
    y = y0
    while y < y1 + r:
        off = 0 if row % 2 == 0 else r
        x = x0 - r + off
        while x < x1 + r:
            for k in range(4):
                rr = r - k * r / 4
                d.arc([x - rr, y - rr, x + rr, y + rr], 180, 360, fill=color, width=width)
            x += 2 * r
        y += r / 2
        row += 1


def mark(size: int, bg=C["indigo"], fg=C["kinari"]) -> Image.Image:
    """シンボル: 円の中に「暮」と、屋根 (長屋) の線。"""
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, s - 1, s - 1], fill=bg)
    d.ellipse([s * 0.05, s * 0.05, s * 0.95, s * 0.95], outline=C["kincha"], width=int(s * 0.018))
    # 屋根
    d.line([(s * 0.2, s * 0.36), (s * 0.5, s * 0.2), (s * 0.8, s * 0.36)], fill=C["shu"], width=int(s * 0.05), joint="curve")
    f = font("serif", int(s * 0.46))
    d.text((s / 2, s * 0.62), "暮", font=f, fill=fg, anchor="mm")
    return im.resize((size, size), Image.LANCZOS)


def icon():
    im = mark(800)
    bg = Image.new("RGB", (800, 800), C["indigo"])
    bg.paste(im, (0, 0), im)
    bg.save(OUT / "icon_800.png")
    # 円形に切り抜いたときの確認用
    m = Image.new("L", (800, 800), 0)
    ImageDraw.Draw(m).ellipse([0, 0, 799, 799], fill=255)
    prev = Image.new("RGB", (800, 800), (255, 255, 255))
    prev.paste(bg, (0, 0), m)
    prev.resize((98, 98), Image.LANCZOS).save(OUT / "icon_preview_98px.png")


def banner():
    W, H = 2560, 1440
    im = washi(W, H)
    d = ImageDraw.Draw(im)
    seigaiha(d, (0, 0, W, H), (226, 216, 196), r=60, width=3)
    # 安全領域 1546x423 (中央)
    sx, sy = (W - 1546) // 2, (H - 423) // 2
    d.rectangle([0, sy - 30, W, sy + 423 + 30], fill=C["indigo"])
    d.line([(0, sy - 30), (W, sy - 30)], fill=C["kincha"], width=6)
    d.line([(0, sy + 453), (W, sy + 453)], fill=C["kincha"], width=6)
    m = mark(300)
    im.paste(m, (sx + 10, sy + 62), m)
    d.text((sx + 360, sy + 150), CH["name"], font=font("serif", 128), fill=C["kinari"], anchor="lm")
    d.text((sx + 364, sy + 300), CH["catchphrase"], font=font("subtitle", 52), fill=(230, 214, 180), anchor="lm")
    im.save(OUT / "banner_2560x1440.png")
    # 安全領域の確認用ガイド
    g = im.copy()
    gd = ImageDraw.Draw(g)
    gd.rectangle([sx, sy, sx + 1546, sy + 423], outline=(255, 0, 0), width=6)
    gd.rectangle([(W - 2560) // 2, (H - 423) // 2, W, (H + 423) // 2], outline=(0, 160, 255), width=3)
    g.resize((1280, 720)).save(OUT / "banner_safe_area_guide.png")
    return im, (sx, sy)


def watermark():
    m = mark(150)
    m.save(OUT / "watermark_150.png")


def logo():
    im = Image.new("RGBA", (1920, 400), (0, 0, 0, 0))
    m = mark(320)
    im.paste(m, (20, 40), m)
    d = ImageDraw.Draw(im)
    d.text((380, 200), CH["name"], font=font("serif", 150), fill=C["indigo"], anchor="lm")
    im.save(OUT / "logo_1920.png")


def thumb_template():
    W, H = 1280, 720
    im = washi(W, H)
    d = ImageDraw.Draw(im)
    # 右 55%: 主役の絵が入る領域
    d.rectangle([560, 0, W, H], fill=(205, 196, 178))
    d.text((920, 360), "主役の絵 (1 つ)", font=font("subtitle", 44), fill=(120, 110, 96), anchor="mm")
    # 左: 大見出し 2 行まで (8 文字 x 2 行)
    d.rectangle([0, 0, 600, H], fill=C["indigo"])
    d.text((40, 70), "江戸の", font=font("heavy", 96), fill=C["kinari"])
    d.text((40, 190), "銭湯は", font=font("heavy", 96), fill=C["kinari"])
    d.text((40, 320), "混浴?", font=font("heavy", 120), fill=C["shu"], stroke_width=6, stroke_fill=C["kinari"])
    d.rectangle([40, 600, 330, 660], fill=C["kincha"])
    d.text((185, 630), "暮らしの謎解き", font=font("subtitle", 34), fill=C["sumi"], anchor="mm")
    # 右下: 再生時間の表示に隠れる領域 (文字を置かない)
    d.rectangle([W - 190, H - 70, W, H], outline=(255, 0, 0), width=3)
    d.text((W - 95, H - 35), "時間表示", font=font("subtitle", 22), fill=(200, 0, 0), anchor="mm")
    im.save(OUT / "thumb_template_1280x720.png")
    im.resize((320, 180), Image.LANCZOS).save(OUT / "thumb_template_phone_320.png")


def card(title: str, sub: str, name: str):
    W, H = 1920, 1080
    im = washi(W, H)
    d = ImageDraw.Draw(im)
    seigaiha(d, (0, 760, W, H), (220, 208, 186), r=50)
    m = mark(360)
    im.paste(m, (W // 2 - 180, 170), m)
    d.text((W // 2, 640), title, font=font("serif", 96), fill=C["indigo"], anchor="mm")
    d.text((W // 2, 760), sub, font=font("subtitle", 46), fill=C["sumi"], anchor="mm")
    im.save(OUT / name)


def device_preview(ban: Image.Image, safe):
    """スマホ (1546x423 程度)・PC (2560x423)・テレビ (全体) でのバナーの見え方。"""
    sx, sy = safe
    W = 2400
    out = Image.new("RGB", (W, 1500), (250, 250, 250))
    d = ImageDraw.Draw(out)
    f = font("subtitle", 40)
    tv = ban.resize((1200, 675))
    out.paste(tv, (40, 80))
    d.text((40, 20), "テレビ (全体を表示)", font=f, fill=(0, 0, 0))
    pc = ban.crop((0, sy, 2560, sy + 423)).resize((1100, 182))
    out.paste(pc, (1280, 80))
    d.text((1280, 20), "PC (横長の帯)", font=f, fill=(0, 0, 0))
    ph = ban.crop((sx, sy, sx + 1546, sy + 423)).resize((700, 192))
    out.paste(ph, (1280, 360))
    d.text((1280, 300), "スマホ (安全領域のみ)", font=f, fill=(0, 0, 0))
    ic = Image.open(OUT / "icon_preview_98px.png")
    out.paste(ic, (1280, 640))
    d.text((1400, 670), "アイコン (98px 表示)", font=f, fill=(0, 0, 0))
    out.save(OUT / "preview_devices.png")


if __name__ == "__main__":
    icon()
    ban, safe = banner()
    watermark()
    logo()
    thumb_template()
    card(CH["name"], CH["catchphrase"], "opening_1920x1080.png")
    card("ご視聴ありがとうございました", "出典は概要欄に記載しています", "ending_1920x1080.png")
    device_preview(ban, safe)
    print("\n".join(sorted(p.name for p in OUT.iterdir())))
