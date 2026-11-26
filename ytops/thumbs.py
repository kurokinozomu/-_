"""長尺動画のサムネイル候補を 3 種類作り、スマホでの見え方を機械的に評価する。

A: ブランド型 (左に藍の帯と大見出し、右に主役の絵)
B: 全面の絵 + 下部の帯に短い見出し
C: 問いかけ型 (絵を暗くして中央に大きな問い)
評価: 文字と背景のコントラスト比 (WCAG)・文字数・320px 幅に縮小したときの文字の高さ・右下 (再生時間表示) との重なり
YouTube Studio の「テストと比較」は API で操作できないため、上位 3 枚をオーナーが Studio で登録する運用にする。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from aivideo import assets

W, H = 1280, 720
INDIGO, KINARI, SHU, SUMI, KINCHA = (31, 58, 95), (244, 239, 228), (192, 57, 43), (29, 29, 31), (184, 134, 43)


def _font(kind: str, size: int):
    return ImageFont.truetype(assets.font(kind)[0], size)


def _lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _avg(im: Image.Image, box) -> tuple:
    return tuple(int(v) for v in im.crop(box).resize((1, 1), Image.BOX).getpixel((0, 0))[:3])


def _cover(src: Image.Image, w: int, h: int) -> Image.Image:
    r = max(w / src.width, h / src.height)
    im = src.resize((int(src.width * r) + 1, int(src.height * r) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _split(text: str, n: int = 7) -> list[str]:
    text = text.strip()
    if len(text) <= n:
        return [text]
    cut = min(len(text) - 1, max(2, len(text) // 2))
    for sep in ("の", "は", "が", "を", "に", "で", "と"):
        i = text.find(sep, 2)
        if 2 <= i <= n:
            cut = i + 1
            break
    return [text[:cut], text[cut:]]


def variant_a(src, main, sub, label):
    im = Image.new("RGB", (W, H), INDIGO)
    im.paste(_cover(src, 700, H), (580, 0))
    d = ImageDraw.Draw(im)
    lines = _split(main)
    size = 120 if max(len(l) for l in lines) <= 4 else 96
    y = 110
    boxes = []
    for i, l in enumerate(lines):
        col = SHU if i == len(lines) - 1 and len(lines) > 1 else KINARI
        d.text((40, y), l, font=_font("heavy", size), fill=col, stroke_width=5, stroke_fill=KINARI if col == SHU else INDIGO)
        boxes.append(((40, y, 560, y + size), col, INDIGO))
        y += size + 30
    if sub:
        d.text((40, y + 10), sub, font=_font("subtitle", 44), fill=(230, 214, 180))
    d.rectangle([40, 610, 40 + 34 * len(label) + 40, 664], fill=KINCHA)
    d.text((60, 637), label, font=_font("subtitle", 34), fill=SUMI, anchor="lm")
    return im, boxes, size


def variant_b(src, main, sub, label):
    im = _cover(src, W, H)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 470, W, H], fill=(*INDIGO,))
    text = main if len(main) <= 10 else _split(main, 10)[0]
    size = 130 if len(text) <= 7 else 104
    d.text((W // 2 - 80, 590), text, font=_font("heavy", size), fill=KINARI, anchor="mm", stroke_width=6, stroke_fill=SUMI)
    return im, [((80, 520, 1100, 660), KINARI, INDIGO)], size


def variant_c(src, main, sub, label):
    im = ImageEnhance.Brightness(_cover(src, W, H)).enhance(0.42)
    d = ImageDraw.Draw(im)
    q = (sub or main).strip()
    q = q if q.endswith(("?", "？")) else q + "？"
    lines = _split(q, 8)
    size = 128 if max(len(l) for l in lines) <= 6 else 100
    y = H // 2 - (len(lines) * (size + 20)) // 2 + size // 2 - 30
    for l in lines:
        d.text((W // 2, y), l, font=_font("heavy", size), fill=KINARI, anchor="mm", stroke_width=8, stroke_fill=SUMI)
        y += size + 20
    bg = _avg(im, (100, 100, W - 100, H - 100))
    return im, [((100, 150, W - 100, H - 150), KINARI, bg)], size


def score(im: Image.Image, boxes, size: int, text: str) -> dict:
    con = min(contrast(fg, bg) for _, fg, bg in boxes)
    px_phone = size * 320 / W  # スマホの小さい表示 (幅 320px) での文字の高さ
    chars = len(text.replace(" ", ""))
    s = 0.0
    s += min(40, con / 7 * 40)                  # コントラスト (7:1 で満点)
    s += 30 if px_phone >= 24 else 30 * px_phone / 24
    s += 20 if chars <= 10 else max(0, 20 - (chars - 10) * 3)
    s += 10  # 右下の時間表示領域には文字を置かないレイアウト
    return {"score": round(s, 1), "contrast": round(con, 2), "text_px_at_320w": round(px_phone, 1), "chars": chars}


def make(vdir: Path) -> list[dict]:
    vdir = Path(vdir)
    meta = json.loads((vdir / "metadata.json").read_text(encoding="utf-8"))
    th = meta.get("thumbnail", {})
    main = th.get("text") or (meta.get("titles") or [""])[0][:10]
    sub = th.get("sub_text", "")
    imgs = sorted((vdir / "work").glob("*.png")) if (vdir / "work").exists() else []
    src_path = next((p for p in imgs if p.stat().st_size > 200_000), None) or vdir / "thumbnail.png"
    src = Image.open(src_path).convert("RGB")
    out = vdir / "thumbs"
    out.mkdir(exist_ok=True)
    res = []
    for name, fn in (("A", variant_a), ("B", variant_b), ("C", variant_c)):
        im, boxes, size = fn(src, main, sub, "暮らしの謎解き")
        p = out / f"thumb_{name}.png"
        im.save(p)
        res.append({"variant": name, "path": str(p), **score(im, boxes, size, main if name != "C" else sub or main)})
    res.sort(key=lambda r: r["score"], reverse=True)
    (out / "thumbs.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    # 一覧画像 (スマホ幅での比較)
    sheet = Image.new("RGB", (3 * 330, 200), (245, 245, 245))
    for i, r in enumerate(res):
        sheet.paste(Image.open(r["path"]).resize((320, 180), Image.LANCZOS), (5 + i * 330, 10))
    sheet.save(out / "compare_phone.png")
    return res
