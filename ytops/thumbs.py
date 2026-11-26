"""長尺動画のサムネイル候補を 3 種類作り、スマホでの見え方を機械的に評価する。

A: ブランド型 (左に藍の帯と 2 行の見出し、右に主役の絵)
B: 全面の絵 + 下部の藍の帯に 1 行目の見出し
C: 問いかけ型 (絵を暗くして中央に 2 行)
見出しは台本 AI が作った line1 / line2 / emphasis (強調語は朱) を使い、枠に収まる大きさに自動で縮める。
評価: 文字と背景のコントラスト比 (WCAG)・320px 幅に縮小したときの文字の高さ・文字数・はみ出し / 欠け
YouTube Studio の「テストと比較」は API で操作できないため、上位 3 枚をオーナーが Studio で登録する運用にする。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from aivideo import assets

W, H = 1280, 720
INDIGO, KINARI, SHU, SUMI, KINCHA = (31, 58, 95), (244, 239, 228), (192, 57, 43), (29, 29, 31), (184, 134, 43)
SHU_LIGHT = (236, 112, 88)  # 藍の上でも読める明るい朱


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


def _fit(d, lines, max_w, max_size, min_size=48):
    """全行が max_w に収まる最大のフォントサイズ。収まらなければ最小サイズ (fits=False)。"""
    size = max_size
    while size >= min_size:
        f = _font("heavy", size)
        if all(d.textlength(l, font=f) <= max_w for l in lines):
            return f, True
        size -= 6
    return _font("heavy", min_size), False


def _draw_line(d, xy, line, f, emphasis, base_col, emph_col, stroke, anchor="la"):
    """強調語だけ色を変えて 1 行描く。"""
    x, y = xy
    if anchor == "ma":
        x -= d.textlength(line, font=f) / 2
    parts = [line] if not emphasis or emphasis not in line else list(line.partition(emphasis))
    for p in parts:
        if not p:
            continue
        d.text((x, y), p, font=f, fill=emph_col if p == emphasis else base_col, stroke_width=max(3, f.size // 18),
               stroke_fill=stroke)
        x += d.textlength(p, font=f)


def variant_a(src, lines, emph, label):
    im = Image.new("RGB", (W, H), INDIGO)
    im.paste(_cover(src, 700, H), (580, 0))
    d = ImageDraw.Draw(im)
    f, fits = _fit(d, lines, 500, 116)
    y = 120
    for l in lines:
        _draw_line(d, (40, y), l, f, emph, KINARI, SHU_LIGHT, INDIGO)
        y += int(f.size * 1.25)
    d.rectangle([40, 610, 40 + 34 * len(label) + 40, 664], fill=KINCHA)
    d.text((60, 637), label, font=_font("subtitle", 34), fill=SUMI, anchor="lm")
    return im, [(KINARI, INDIGO), (SHU_LIGHT, INDIGO)], f.size, fits


def variant_b(src, lines, emph, label):
    im = _cover(src, W, H)
    d = ImageDraw.Draw(im)
    text = "".join(lines) if len("".join(lines)) <= 12 else lines[-1]
    d.rectangle([0, 500, W, H], fill=INDIGO)
    f, fits = _fit(d, [text], W - 260, 130)
    _draw_line(d, (W // 2 - 80, 610 - f.size // 2), text, f, emph, KINARI, SHU_LIGHT, SUMI, anchor="ma")
    return im, [(KINARI, INDIGO), (SHU_LIGHT, INDIGO)], f.size, fits


def variant_c(src, lines, emph, label):
    im = ImageEnhance.Brightness(_cover(src, W, H)).enhance(0.42)
    d = ImageDraw.Draw(im)
    f, fits = _fit(d, lines, W - 200, 128)
    y = H // 2 - len(lines) * int(f.size * 1.2) // 2
    for l in lines:
        _draw_line(d, (W // 2, y), l, f, emph, KINARI, (255, 150, 120), SUMI, anchor="ma")
        y += int(f.size * 1.2)
    bg = _avg(im, (100, 100, W - 100, H - 100))
    return im, [(KINARI, bg)], f.size, fits


def score(boxes, size: int, text: str, fits: bool, complete: bool) -> dict:
    con = min(contrast(fg, bg) for fg, bg in boxes)
    px_phone = size * 320 / W  # スマホの小さい表示 (幅 320px) での文字の高さ
    chars = len(text.replace(" ", ""))
    s = min(35, con / 7 * 35)
    s += 25 if px_phone >= 22 else 25 * px_phone / 22
    s += 15 if chars <= 12 else max(0, 15 - (chars - 12) * 3)
    s += 15 if fits else 0          # 枠からはみ出していない
    s += 10 if complete else 0      # 見出しを途中で切っていない
    return {"score": round(s, 1), "contrast": round(con, 2), "text_px_at_320w": round(px_phone, 1),
            "chars": chars, "fits": fits, "complete": complete}


def headline(meta: dict) -> tuple[list[str], str]:
    from aivideo.visuals import safe_text
    th = meta.get("thumbnail", {})
    heavy = assets.font("heavy")[0]
    lines = [safe_text(x, heavy) for x in (th.get("line1"), th.get("line2")) if x]
    if not lines:
        t = safe_text(th.get("text") or (meta.get("titles") or [""])[0], heavy)
        lines = [t[:8], t[8:16]] if len(t) > 8 else [t]
    return [l for l in lines if l], th.get("emphasis", "")


def make(vdir: Path) -> list[dict]:
    vdir = Path(vdir)
    meta = json.loads((vdir / "metadata.json").read_text(encoding="utf-8"))
    lines, emph = headline(meta)
    imgs = sorted((vdir / "work").glob("s*.png")) if (vdir / "work").exists() else []
    imgs = [p for p in imgs if "_telop" not in p.name]
    src_path = next((p for p in imgs if p.stat().st_size > 200_000), None) or vdir / "thumbnail.png"
    src = Image.open(src_path).convert("RGB")
    out = vdir / "thumbs"
    out.mkdir(exist_ok=True)
    res = []
    for name, fn in (("A", variant_a), ("B", variant_b), ("C", variant_c)):
        im, boxes, size, fits = fn(src, lines, emph, "暮らしの謎解き")
        p = out / f"thumb_{name}.png"
        im.save(p)
        shown = "".join(lines) if name != "B" or len("".join(lines)) <= 12 else lines[-1]
        complete = name != "B" or shown == "".join(lines) or len(lines) > 1 and shown == lines[-1] and len(lines[-1]) >= 5
        res.append({"variant": name, "path": str(p), **score(boxes, size, shown, fits, complete)})
    res.sort(key=lambda r: r["score"], reverse=True)
    (out / "thumbs.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    sheet = Image.new("RGB", (3 * 330, 200), (245, 245, 245))
    for i, r in enumerate(res):
        sheet.paste(Image.open(r["path"]).resize((320, 180), Image.LANCZOS), (5 + i * 330, 10))
    sheet.save(out / "compare_phone.png")
    return res
