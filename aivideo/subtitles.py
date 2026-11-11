"""字幕の生成 (焼き込み用 ASS と、YouTube アップロード用 SRT)。

文ごとに合成した音声の実測時間を使うため、ナレーションと字幕がずれない。
長い文は読点などで区切って複数の字幕に分け、文字数比で時間を配分する。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

LINE_MAX = 19      # 1 行の最大文字数 (大きめの文字に合わせる)
EVENT_MAX = 34     # 1 画面 (2 行) の最大文字数
PARTICLES = ("は", "が", "を", "に", "で", "と", "も", "へ", "の", "から", "まで", "より", "ので", "けど", "て")
NUM_UNITS = set(".,%万億兆京垓倍秒分時日年回個人円度キロメートル")
NO_LINE_START = set("、。！？!?」』）)ぁぃぅぇぉっゃゅょゎァィゥェォッャュョーヶ・…")


def clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[。]+$", "", text)        # 文末の句点は字幕では省略
    text = text.replace("。", "　")
    return text


@lru_cache(maxsize=4096)
def _boundaries(s: str) -> tuple[frozenset, frozenset]:
    """(単語の切れ目, 文節の切れ目) の文字位置。形態素解析 (pyopenjtalk) が使えなければ空。"""
    try:
        import pyopenjtalk
        nodes = pyopenjtalk.run_frontend(s)
    except Exception:
        return frozenset(), frozenset()
    words, phrases, pos = set(), set(), 0
    pending_phrase = False   # 数字など、読みに変換されて元の文字と対応しない部分
    for n in nodes:
        w = n.get("string", "")
        j = s.find(w, pos) if w else -1
        if j < 0 or j - pos > 6:
            if n.get("chain_flag") == 0 and pos not in phrases and not pending_phrase:
                phrases.add(pos)
                words.add(pos)
            pending_phrase = True
            continue
        if j > pos:  # 対応しなかった部分の終わりも単語の切れ目
            words.add(j)
        words.add(j)
        if n.get("chain_flag") == 0:
            phrases.add(j)
        pos = j + len(w)
        words.add(pos)
        pending_phrase = False
    return frozenset(words), frozenset(phrases)


def _break_score(s: str, i: int) -> float:
    """位置 i (s[:i] | s[i:]) で改行したときの良さ。"""
    if i <= 0 or i >= len(s) or s[i] in NO_LINE_START:
        return -1e9
    # 「115京倍」「3.6万」のような数字と単位の途中では改行しない
    if (s[i - 1].isdigit() or s[i - 1] in ".,") and (s[i].isdigit() or s[i] in NUM_UNITS):
        return -1e9
    prev = s[:i]
    score = 0.0
    words, phrases = _boundaries(s)
    if words:
        if i in phrases:
            score += 5      # 文節の頭 (「便利 | アプリ」より「入れるべき | 便利アプリ」)
        elif i not in words:
            score -= 6      # 単語の途中は避ける
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
    if best_v < -2:  # 範囲内に良い位置がなければ、少しはみ出しても単語や数字の途中は避ける
        for i in range(max(1, lo - 4), min(len(s) - 1, hi + 4) + 1):
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


def configure(vertical: bool) -> None:
    """縦型ショートでは 1 行を短く、2 行までに収める。"""
    global LINE_MAX, EVENT_MAX
    LINE_MAX, EVENT_MAX = (11, 22) if vertical else (19, 34)


def write_ass(events, path: Path, font_family: str, outer: tuple[int, int, int] = (20, 60, 140),
              width=1920, height=1080) -> None:
    """テレビ・YouTube でよく使われる「二重縁取り」の字幕。

    レイヤー0: 太い色付きの外縁 / レイヤー1: 白文字 + 黒の内縁 + 影。強調語は黄色。
    """
    oc = _ass_color(outer)
    tall = height > width
    fs = 82 if tall else 86
    mv = int(height * 0.27) if tall else 46   # 縦型はショートの下部 UI を避けて少し上に
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Outer,{font_family},{fs},{oc},{oc},{oc},&H64000000,0,0,0,0,100,100,1,0,1,15,4,2,70,70,{mv},1
Style: Inner,{font_family},{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,6,0,2,70,70,{mv},1

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
        longest = max(len(ln) for ln in wrapped.split("\\N"))
        fit = f"\\fs{int(fs * (LINE_MAX + 0.5) / longest)}" if longest > LINE_MAX else ""  # はみ出す行は少し小さく
        lines.append(f"Dialogue: 0,{t0},{t1},Outer,,0,0,0,,{{\\fad(70,70)\\blur1.5{fit}}}{wrapped}\n")
        lines.append(f"Dialogue: 1,{t0},{t1},Inner,,0,0,0,,{{\\fad(70,70){fit}}}{inner}\n")
    path.write_text("".join(lines), encoding="utf-8")


def write_srt(events, path: Path) -> None:
    out = []
    for k, ev in enumerate(events, 1):
        text, s, e = ev[:3]
        out.append(f"{k}\n{_srt_time(s)} --> {_srt_time(e)}\n{wrap(text).replace(chr(92) + 'N', chr(10))}\n")
    path.write_text("\n".join(out), encoding="utf-8")


# ------------------------------------------------------------------ カウンター (HUD)
JP_UNITS = [(10 ** 24, "じょ"), (10 ** 20, "垓"), (10 ** 16, "京"), (10 ** 12, "兆"), (10 ** 8, "億"), (10 ** 4, "万")]


def jp_number(x: float) -> str:
    """6.6万 / 2,749億 / 115京 のような日本語の大きな数の表記。"""
    for unit, name in JP_UNITS:
        if x >= unit:
            v = x / unit
            if v >= 1000:
                return f"{int(round(v)):,}{name}"
            if v >= 100:
                return f"{int(round(v))}{name}"
            return f"{v:.1f}".rstrip("0").rstrip(".") + name
    return f"{int(round(x)):,}"


def hud_events(hud: dict, anchors: list[tuple[float, float, str]], total: float, step: float = 0.1):
    """動画時刻 → 経過秒数の対応 (anchors: (動画秒, 経過秒, レベル)) からカウンター表示を作る。"""
    anchors = sorted(anchors)
    end_sec = float(hud.get("end_sec") or anchors[-1][1])
    pts = [(0.0, anchors[0][1], anchors[0][2])] + anchors + [(total, max(end_sec, anchors[-1][1]), anchors[-1][2])]

    def story(t):
        for (t0, s0, lv), (t1, s1, _) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                return s0 + (s1 - s0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0), lv
        return pts[-1][1], pts[-1][2]

    base = float(hud.get("base") or 2)
    interval = float(hud.get("interval_sec") or 1)
    events, cur, t = [], None, 0.0
    while t < total:
        sec, lv = story(t)
        sec_i = int(sec)
        key = (sec_i, lv)
        if key != cur:
            if events:
                events[-1][1] = t
            mult = base ** (sec_i / interval)
            events.append([t, total, sec_i, jp_number(mult), lv])
            cur = key
        t += step
    return events


def write_hud(path: Path, hud: dict, events, serif_family: str, gothic_family: str,
              width: int, height: int) -> None:
    """画面上部に、問い・経過秒数・倍率・レベル・注意書きを常に表示する (ニュース風の明朝体)。"""
    q = hud.get("question", "")
    for kw in hud.get("keywords", []) or []:
        if kw and kw in q:
            q = q.replace(kw, "{\\1c&H00FFC87A&}" + kw + "{\\1c&H00FFFFFF&}")
    q = q.replace("、", "、\\N", 1) if len(hud.get("question", "")) > 14 else q
    cx = width // 2
    y0 = int(height * 0.085)
    styles = f"""
Style: HudQ,{serif_family},58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,1,0,1,3,2,8,40,40,0,1
Style: HudBig,{serif_family},124,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,1,0,1,4,3,8,40,40,0,1
Style: HudLabel,{gothic_family},42,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,1,0,1,3,2,8,40,40,0,1
Style: HudBadge,{gothic_family},40,&H00FFFFFF,&H00FFFFFF,&H50000000,&H50000000,0,0,0,0,100,100,1,0,3,10,0,8,40,40,0,1
Style: HudNote,{gothic_family},26,&H00DDDDDD,&H00DDDDDD,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,0,1
"""
    text = path.read_text(encoding="utf-8")
    text = text.replace("\n[Events]", styles + "\n[Events]", 1)
    lines = []
    T = _ass_time
    end = events[-1][1] if events else 0
    lines.append(f"Dialogue: 2,{T(0)},{T(end)},HudQ,,0,0,0,,{{\\pos({cx},{y0})}}{q}\n")
    for s, e, sec, mult, lv in events:
        y = y0 + 170
        lines.append(f"Dialogue: 2,{T(s)},{T(e)},HudBig,,0,0,0,,{{\\pos({cx},{y})}}{sec}{{\\fs60}}秒目\n")
        lines.append(f"Dialogue: 2,{T(s)},{T(e)},HudLabel,,0,0,0,,{{\\pos({cx},{y + 150})}}{hud.get('label', '')}\n")
        lines.append(f"Dialogue: 2,{T(s)},{T(e)},HudBig,,0,0,0,,{{\\pos({cx},{y + 200})}}{mult}{{\\fs60}}倍\n")
        if lv:
            lines.append(f"Dialogue: 2,{T(s)},{T(e)},HudBadge,,0,0,0,,{{\\pos({cx},{y + 362})}}{lv}\n")
    if hud.get("disclaimer"):
        lines.append(f"Dialogue: 2,{T(0)},{T(end)},HudNote,,0,0,0,,{{\\an2\\pos({cx},{height - 40})}}{hud['disclaimer']}\n")
    path.write_text(text + "".join(lines), encoding="utf-8")
