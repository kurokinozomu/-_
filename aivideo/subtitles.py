"""字幕の生成 (焼き込み用 ASS と、YouTube アップロード用 SRT)。

文ごとに合成した音声の実測時間を使うため、ナレーションと字幕がずれない。
長い文は読点などで区切って複数の字幕に分け、文字数比で時間を配分する。
"""
from __future__ import annotations

import re
from pathlib import Path

LINE_MAX = 19      # 1 行の最大文字数 (大きめの文字に合わせる)
EVENT_MAX = 34     # 1 画面 (2 行) の最大文字数
PARTICLES = ("は", "が", "を", "に", "で", "と", "も", "へ", "の", "から", "まで", "より", "ので", "けど", "て")
NO_LINE_START = set("、。！？!?」』）)ぁぃぅぇぉっゃゅょゎァィゥェォッャュョーヶ・…")


def clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[。]+$", "", text)        # 文末の句点は字幕では省略
    text = text.replace("。", "　")
    return text


def _break_score(s: str, i: int) -> float:
    """位置 i (s[:i] | s[i:]) で改行したときの良さ。"""
    if i <= 0 or i >= len(s) or s[i] in NO_LINE_START:
        return -1e9
    prev = s[:i]
    score = 0.0
    if prev.endswith(("、", "　", " ", "」", "』", "！", "？")):
        score += 10
    elif prev.endswith(PARTICLES):
        score += 6
    elif _kind(s[i - 1]) != _kind(s[i]):
        score += 2
    return score


def _kind(c: str) -> str:
    if "぀" <= c <= "ゟ":
        return "h"
    if "゠" <= c <= "ヿ":
        return "k"
    if "一" <= c <= "鿿":
        return "c"
    return "o"


def best_split(s: str, target: int, lo: int, hi: int) -> int:
    best, best_v = target, -1e18
    for i in range(max(1, lo), min(len(s) - 1, hi) + 1):
        v = _break_score(s, i) - abs(i - target) * 0.8
        if v > best_v:
            best, best_v = i, v
    return best


def wrap(s: str) -> str:
    if len(s) <= LINE_MAX:
        return s
    mid = len(s) // 2
    i = best_split(s, mid, len(s) - LINE_MAX, LINE_MAX)
    return s[:i].rstrip("　 ") + "\\N" + s[i:].lstrip("　 ")


def chunk(s: str) -> list[str]:
    if len(s) <= EVENT_MAX:
        return [s]
    n = -(-len(s) // EVENT_MAX)
    target = len(s) // n
    i = best_split(s, target, max(8, target - 12), min(EVENT_MAX, target + 12))
    return [s[:i].rstrip("　 ")] + chunk(s[i:].lstrip("　 "))


def build_events(sentences) -> list[tuple[str, float, float, list[str]]]:
    """sentences: (テキスト, 開始, 終了[, 強調語リスト])"""
    events = []
    for item in sentences:
        text, start, end = item[:3]
        hl = list(item[3]) if len(item) > 3 else []
        parts = chunk(clean(text))
        total = sum(len(p) for p in parts) or 1
        t = start
        for p in parts:
            d = (end - start) * len(p) / total
            events.append((p, t, t + d, hl))
            t += d
    # 隙間が短い字幕はつなげてチラつきを防ぐ
    for k in range(len(events) - 1):
        a, b = events[k], events[k + 1]
        if 0 < b[1] - a[2] < 0.35:
            events[k] = (a[0], a[1], b[1], a[3])
    return events


def _ass_time(t: float) -> str:
    cs = int(round(max(0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_time(t: float) -> str:
    ms = int(round(max(0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_color(rgb: tuple[int, int, int], alpha: int = 0) -> str:
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


HIGHLIGHT = (255, 230, 0)   # 強調語は黄色


def _highlight(line: str, words: list[str]) -> str:
    for w in sorted(set(words), key=len, reverse=True):
        if w and w in line:
            line = line.replace(w, "{\\1c" + _ass_color(HIGHLIGHT) + "&}" + w + "{\\1c&H00FFFFFF&}")
    return line


def write_ass(events, path: Path, font_family: str, outer: tuple[int, int, int] = (20, 60, 140),
              width=1920, height=1080) -> None:
    """テレビ・YouTube でよく使われる「二重縁取り」の字幕。

    レイヤー0: 太い色付きの外縁 / レイヤー1: 白文字 + 黒の内縁 + 影。強調語は黄色。
    """
    oc = _ass_color(outer)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Outer,{font_family},86,{oc},{oc},{oc},&H64000000,0,0,0,0,100,100,1,0,1,15,4,2,70,70,46,1
Style: Inner,{font_family},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,6,0,2,70,70,46,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [head]
    for ev in events:
        text, s, e = ev[:3]
        hl = ev[3] if len(ev) > 3 else []
        wrapped = wrap(text)
        inner = "\\N".join(_highlight(ln, hl) for ln in wrapped.split("\\N"))
        t0, t1 = _ass_time(s), _ass_time(e)
        lines.append(f"Dialogue: 0,{t0},{t1},Outer,,0,0,0,,{{\\fad(70,70)\\blur1.5}}{wrapped}\n")
        lines.append(f"Dialogue: 1,{t0},{t1},Inner,,0,0,0,,{{\\fad(70,70)}}{inner}\n")
    path.write_text("".join(lines), encoding="utf-8")


def write_srt(events, path: Path) -> None:
    out = []
    for k, ev in enumerate(events, 1):
        text, s, e = ev[:3]
        out.append(f"{k}\n{_srt_time(s)} --> {_srt_time(e)}\n{wrap(text).replace(chr(92) + 'N', chr(10))}\n")
    path.write_text("\n".join(out), encoding="utf-8")
