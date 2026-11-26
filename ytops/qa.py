"""投稿前の品質審査 (100 点満点 + 公開禁止条件)。

配点 (オーナー指定):
  情報の正確性 20 / 独自性 20 / 台本 15 / 映像 15 / 音声 10 / 字幕 5 / タイトル・サムネ 5 / 規約・著作権 10

自動で測れるもの (解像度・コーデック・ラウドネス・無音・黒画面・字幕・メタデータ・過去動画との類似度) は
機械的に採点し、正確性・台本の質は LLM が Web 検索で裏取りして採点する。
自動審査で安全性を保証できないもの (高リスクの事実誤り・医療/法律の助言など) は needs_review にして人間に回す。
"""
from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

SPEC = {
    "short": {"w": 1080, "h": 1920, "min": 15, "max": 180},
    "long": {"w": 1920, "h": 1080, "min": 60, "max": 3 * 3600},
    "sleep": {"w": 1920, "h": 1080, "min": 600, "max": 4 * 3600},
}
HYPE_WORDS = ["絶対", "衝撃", "ヤバ", "やばすぎ", "閲覧注意", "99%", "９９％", "9割", "神", "必見", "完全版", "最強", "知らないと損"]
BANNED_PATTERNS = [r"相互(フォロー|登録)", r"フォロバ", r"sub4sub", r"登録してくれたら", r"高評価.{0,6}(お願い|押して).{0,10}(しないと|でないと)"]


@dataclass
class QAResult:
    scores: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)      # (重さ, 内容)
    blockers: list = field(default_factory=list)    # 公開禁止の理由
    needs_human: list = field(default_factory=list)
    sources: list = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(self.scores.values()), 1)

    def verdict(self, min_score: float = 85) -> str:
        if self.blockers:
            return "blocked"
        if self.needs_human:
            return "needs_review"
        return "pass" if self.total >= min_score else "fix"

    def to_json(self, min_score: float = 85) -> dict:
        return {"total": self.total, "verdict": self.verdict(min_score), "scores": self.scores,
                "issues": self.issues, "blockers": self.blockers, "needs_human": self.needs_human,
                "sources": self.sources}


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe(video: Path) -> dict:
    p = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(video)])
    return json.loads(p.stdout or "{}")


def loudness(video: Path) -> dict:
    """統合ラウドネス (LUFS) とトゥルーピーク (dBTP)。"""
    p = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn",
              "-af", "ebur128=peak=true", "-f", "null", "-"])
    txt = p.stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", txt)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", txt)
    return {"lufs": float(i[-1]) if i else None, "true_peak": float(tp[-1]) if tp else None}


def silences(video: Path, noise_db: int = -45, min_sec: float = 2.5) -> list[tuple[float, float]]:
    p = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn",
              "-af", f"silencedetect=noise={noise_db}dB:d={min_sec}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", p.stderr)]
    return list(zip(starts, ends))


def black_frames(video: Path, min_sec: float = 1.0) -> list[tuple[float, float]]:
    p = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
              "-vf", f"blackdetect=d={min_sec}:pix_th=0.08", "-an", "-f", "null", "-"])
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", p.stderr)]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s、。・!！?？「」『』()（）\-ー〜~,.]", "", s)


def ngrams(s: str, n: int = 4) -> set:
    s = _norm(s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def similarity(a: str, b: str) -> float:
    A, B = ngrams(a), ngrams(b)
    return len(A & B) / max(1, min(len(A), len(B))) if A and B else 0.0


def narration_of(plan: dict) -> str:
    return "\n".join(s.get("narration", "") for ch in plan.get("chapters", []) for s in ch.get("scenes", []))


def past_narrations(exclude_dir: Path, exclude: list | None = None) -> list[tuple[str, str]]:
    """過去に作った動画の台本 (plan.json) を集める。exclude: 比較しないフォルダ (修正前の版など)"""
    from aivideo import registry
    out = []
    skip = {Path(exclude_dir).resolve()} | {Path(e).resolve() for e in (exclude or [])}
    from .config import state_dir
    managed = (state_dir() / "videos").resolve()
    own_root = Path(exclude_dir).resolve().parent  # ytops 管理の動画は ID ごとのフォルダ。同じフォルダ内は作り直しの版
    for v in registry.load().get("videos", []):
        d = Path(v.get("dir", ""))
        if d.resolve() in skip:
            continue
        if own_root.parent == managed and d.resolve().parent == own_root:
            continue
        pj = d / "plan.json"
        if pj.exists():
            try:
                out.append((v.get("title", ""), narration_of(json.loads(pj.read_text(encoding="utf-8")))))
            except Exception:
                pass
        else:  # 台本ファイルがない古い記録は、登録された要約で比較
            out.append((v.get("title", ""), " ".join(i.get("fact", "") for i in v.get("items", []))))
    return out


# ---------------- 個別チェック ----------------
def check_technical(video: Path, kind: str, r: QAResult) -> dict:
    spec = SPEC[kind]
    info = probe(video)
    vs = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    au = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), {})
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    v_score = 15.0
    if not vs:
        r.blockers.append("映像ストリームがありません")
        return {"duration": dur}
    if (vs.get("width"), vs.get("height")) != (spec["w"], spec["h"]):
        r.issues.append(("high", f"解像度 {vs.get('width')}x{vs.get('height')} (期待 {spec['w']}x{spec['h']})"))
        v_score -= 6
    if vs.get("codec_name") != "h264":
        r.issues.append(("medium", f"映像コーデック {vs.get('codec_name')} (H.264 推奨)"))
        v_score -= 2
    fps = vs.get("r_frame_rate", "0/1").split("/")
    fps = float(fps[0]) / max(1.0, float(fps[1]))
    if abs(fps - 30) > 0.5:
        r.issues.append(("low", f"フレームレート {fps:.2f}fps (30fps 推奨)"))
        v_score -= 1
    if not (spec["min"] <= dur <= spec["max"]):
        r.issues.append(("high", f"長さ {dur:.0f}秒 が {kind} の範囲 ({spec['min']}〜{spec['max']}秒) 外"))
        v_score -= 4
    blacks = black_frames(video)
    if blacks:
        r.issues.append(("medium", f"黒画面 {len(blacks)} 箇所: {blacks[:3]}"))
        v_score -= min(4, len(blacks))
    r.scores["映像の品質"] = max(0.0, v_score)

    a_score = 10.0
    if not au:
        r.blockers.append("音声ストリームがありません")
        r.scores["音声の品質"] = 0
        return {"duration": dur}
    if au.get("codec_name") != "aac":
        r.issues.append(("low", f"音声コーデック {au.get('codec_name')} (AAC 推奨)"))
        a_score -= 1
    ld = loudness(video)
    if ld["lufs"] is None or not (-17.5 <= ld["lufs"] <= -11.5):
        r.issues.append(("medium", f"ラウドネス {ld['lufs']} LUFS (目標 -14 前後)"))
        a_score -= 3
    if ld["true_peak"] is not None and ld["true_peak"] > -0.5:
        r.issues.append(("medium", f"ピーク {ld['true_peak']} dBFS (クリッピングの恐れ)"))
        a_score -= 3
    sil = [s for s in silences(video) if s[0] > 1.0 and s[1] < dur - 3]
    if sil and kind != "sleep":
        r.issues.append(("medium", f"途中の無音 {len(sil)} 箇所 (2.5秒以上): {[(round(a,1), round(b,1)) for a, b in sil[:3]]}"))
        a_score -= min(4, 2 * len(sil))
    r.scores["音声の品質"] = max(0.0, a_score)
    return {"duration": dur, **ld}


def check_subtitles(vdir: Path, kind: str, r: QAResult) -> None:
    srt = vdir / "subtitles.srt"
    score = 5.0
    if not srt.exists() or srt.stat().st_size < 20:
        r.issues.append(("high", "字幕ファイル (subtitles.srt) がありません"))
        r.scores["字幕の品質"] = 0
        return
    lines = [l for l in srt.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.strip().isdigit() and "-->" not in l]
    limit = 16 if kind == "short" else 30
    long_lines = [l for l in lines if len(l) > limit]
    if long_lines:
        r.issues.append(("low", f"1 行 {limit} 文字超の字幕 {len(long_lines)} 行 (例: {long_lines[0][:30]})"))
        score -= min(2, len(long_lines) * 0.2)
    r.scores["字幕の品質"] = max(0.0, score)


def check_metadata(vdir: Path, kind: str, r: QAResult) -> dict:
    meta = json.loads((vdir / "metadata.json").read_text(encoding="utf-8")) if (vdir / "metadata.json").exists() else {}
    titles = meta.get("titles", [])
    desc = meta.get("description", "")
    score = 5.0
    if len(titles) < 5:
        r.issues.append(("medium", f"タイトル候補が {len(titles)} 個 (5 個以上必要)"))
        score -= 1.5
    t0 = titles[0] if titles else ""
    if not t0:
        r.blockers.append("タイトルがありません")
    if len(t0) > 100:
        r.blockers.append("タイトルが 100 文字を超えています (YouTube の上限)")
    elif len(re.sub(r"#\S+", "", t0)) > 42:
        r.issues.append(("low", "タイトルがスマホで切れる長さ (42 文字超)"))
        score -= 0.5
    hype = [w for w in HYPE_WORDS if w in t0]
    if hype:
        r.issues.append(("medium", f"煽り表現: {hype} (内容と一致しているか要確認)"))
        score -= 1
    if kind != "short" and not (vdir / "thumbnail.png").exists():
        r.issues.append(("medium", "サムネイルがありません"))
        score -= 1.5
    elif kind != "short" and len(list((vdir / "thumbs").glob("thumb_*.png"))) < 3:
        r.issues.append(("low", "サムネイル候補が 3 種類未満"))
        score -= 0.5
    th = meta.get("thumbnail", {})
    th_text = "".join(x for x in (th.get("line1"), th.get("line2")) if x) or th.get("text", "")
    if th_text and similarity(th_text, t0) >= 0.5:
        others = [t for t in titles[1:] if similarity(th_text, t) < 0.3]
        r.issues.append(("low", "サムネイルの文字がタイトルの繰り返しになっている"
                         + (f" (別案: 「{others[0]}」)" if others else "")))
        score -= 0.5
    tags = meta.get("tags", [])
    if sum(len(t) for t in tags) > 450:
        r.issues.append(("low", "タグの合計が長すぎます (500 文字上限)"))
    hashtags = re.findall(r"#\S+", t0 + " " + desc)
    if len(hashtags) > 5:
        r.issues.append(("medium", f"ハッシュタグが多すぎます ({len(hashtags)} 個。3〜5 個まで)"))
        score -= 1
    r.scores["タイトル・サムネイル"] = max(0.0, score)

    comp = 10.0
    text = " ".join(titles) + "\n" + desc
    for pat in BANNED_PATTERNS:
        if re.search(pat, text, re.I):
            r.blockers.append(f"規約違反のおそれがある表現 ({pat}): スパム・エンゲージメント誘導")
    if "使用素材" not in desc and "クレジット" not in desc:
        r.issues.append(("high", "概要欄に素材クレジットがありません"))
        comp -= 4
    if "VOICEVOX" in desc and not re.search(r"VOICEVOX[:：]", desc):
        r.issues.append(("high", "VOICEVOX のクレジット形式 (VOICEVOX:キャラ名) がありません"))
        comp -= 3
    r.scores["規約・著作権"] = max(0.0, comp)
    return meta


def check_originality(vdir: Path, plan: dict, r: QAResult, exclude: list | None = None) -> float:
    mine = narration_of(plan)
    best, best_title = 0.0, ""
    for title, text in past_narrations(vdir, exclude):
        s = similarity(mine, text)
        if s > best:
            best, best_title = s, title
    score = 20.0
    if best >= 0.6:
        r.blockers.append(f"過去動画「{best_title}」と台本が {best:.0%} 一致 (重複・再利用コンテンツ)")
        score = 0
    elif best >= 0.35:
        r.issues.append(("medium", f"過去動画「{best_title}」と台本の重なり {best:.0%}"))
        score -= 8
    elif best >= 0.2:
        r.issues.append(("low", f"過去動画「{best_title}」と一部重複 {best:.0%}"))
        score -= 3
    r.scores["独自性"] = score
    return best


REVIEW_PROMPT = """あなたは日本の教養系 YouTube の事実確認担当と編集長です。以下の動画台本を審査してください。
WebSearch を使って、重要な事実 (数字・年代・固有名詞・因果関係) を最大 6 件まで裏取りしてください。
裏取りできなかった主張は「未確認」とし、推測で出典を作らないでください。URL は実際に検索結果で見たものだけを書くこと。

出力は次の JSON のみ:
{{"accuracy": 0-20 の点数, "script": 0-15 の点数,
 "claims": [{{"claim": "主張", "status": "確認|誤り|諸説あり|未確認", "severity": "high|medium|low",
             "note": "根拠・修正案", "url": "確認に使った URL (なければ空)"}}],
 "script_notes": ["台本の改善点 (冒頭の引き・構成・繰り返し・尺稼ぎ・誤解を招く表現)"],
 "human_review": ["人間の確認が必要な理由 (医療・法律・金融の助言、実在の人物の名誉、確認できない重大な主張など)。なければ空配列"]}}

採点基準: accuracy は誤りが 1 件でもあれば 12 点以下、high の誤りがあれば 5 点以下。
script は冒頭 5 秒の引き・論理の流れ・具体性・繰り返しの少なさで評価。

タイトル: {title}
形式: {kind}
台本:
{narration}
"""


def llm_review(plan: dict, title: str, kind: str, r: QAResult, use_web: bool = True) -> None:
    """LLM による事実確認・台本審査。claude CLI が使えないときは人間の確認に回す。"""
    import shutil
    import tempfile
    from aivideo.llm import extract_json
    narration = narration_of(plan)
    if not shutil.which("claude"):
        r.needs_human.append("LLM が使えないため事実確認が未実施")
        r.scores.setdefault("情報の正確性", 10)
        r.scores.setdefault("台本の品質", 10)
        return
    cmd = ["claude", "-p", "--output-format", "text"]
    if use_web:
        cmd += ["--allowedTools", "WebSearch"]
    prompt = REVIEW_PROMPT.format(title=title, kind=kind, narration=narration[:24000])
    data = None
    for _ in range(2):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=900, cwd=tmp)
            data = extract_json(p.stdout)
            break
        except Exception as e:  # 回数制限つきで再試行
            err = e
    if not isinstance(data, dict):
        r.needs_human.append(f"事実確認に失敗: {err if data is None else 'JSON 不正'}")
        r.scores.setdefault("情報の正確性", 10)
        r.scores.setdefault("台本の品質", 10)
        return
    r.scores["情報の正確性"] = max(0.0, min(20.0, float(data.get("accuracy", 0))))
    r.scores["台本の品質"] = max(0.0, min(15.0, float(data.get("script", 0))))
    for c in data.get("claims", []):
        st, sev = c.get("status", ""), c.get("severity", "low")
        if st == "誤り" and sev == "high":
            r.blockers.append(f"重大な事実誤り: {c.get('claim')} → {c.get('note')}")
        elif st == "誤り":
            r.issues.append(("high", f"事実誤り: {c.get('claim')} → {c.get('note')}"))
        elif st == "未確認" and sev == "high":
            r.needs_human.append(f"重要な主張を裏取りできず: {c.get('claim')}")
        if c.get("url") and st in ("確認", "諸説あり"):
            r.sources.append({"claim": c.get("claim"), "url": c["url"], "status": st})
    for n in data.get("script_notes", [])[:6]:
        r.issues.append(("low", f"台本: {n}"))
    for h in data.get("human_review", []):
        if h:
            r.needs_human.append(h)


VISUAL_PROMPT = """あなたは教養系 YouTube チャンネル「{channel}」の映像監修者です。
カレントディレクトリにある frame_*.png は、動画から一定間隔で切り出した画面です。Read ツールで全部見てください。
各画面の時刻とその時点のナレーションは次のとおりです:
{timeline}

ブランドの方針: 落ち着いた教養番組の質感 (藍・生成り・朱を少し)。バラエティ番組風の派手さは避ける。
次の観点で採点し、JSON だけを出力:
{{"visual": 0-15 の点数, "issues": ["問題点 (どの画面で何が問題か)"], "human_review": ["人の確認が必要な点"]}}
減点の基準: ナレーションと絵が合わない / 時代に合わない物 (その時代にない道具・服装・建物、現代の文字や日付) /
本物と誤解されうる写実的な人物 / 読めない・崩れた文字 / 字幕が画面端やボタン位置に重なる / ブランドに合わない派手さ / 同じ絵の繰り返し
"""


def visual_review(vdir: Path, plan: dict, r: QAResult, kind: str, n: int = 6) -> None:
    """動画から n 枚のフレームを切り出し、LLM が絵の内容 (ナレーションとの一致・時代考証・ブランド) を審査する。"""
    import shutil
    import tempfile
    from aivideo.llm import extract_json
    from .config import Channel
    if not shutil.which("claude"):
        r.needs_human.append("映像の内容審査 (LLM) が未実施")
        return
    video = vdir / "video.mp4"
    dur = float(probe(video).get("format", {}).get("duration", 0) or 0)
    if dur <= 0:
        return
    srt = (vdir / "subtitles.srt").read_text(encoding="utf-8") if (vdir / "subtitles.srt").exists() else ""
    cues = []
    for m in re.finditer(r"(\d+):(\d+):(\d+),(\d+) --> [^\n]+\n([\s\S]*?)(?:\n\n|\Z)", srt):
        h, mi, se, ms, txt = m.groups()
        cues.append((int(h) * 3600 + int(mi) * 60 + int(se) + int(ms) / 1000, txt.replace("\n", "")))
    lines = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = dur * (i + 0.5) / n
            _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                  "-vf", "scale=640:-2", str(Path(tmp) / f"frame_{i}.png")])
            said = next((c[1] for c in reversed(cues) if c[0] <= t), "")
            lines.append(f"frame_{i}.png ({t:.0f}秒): {said}")
        prompt = VISUAL_PROMPT.format(channel=Channel.load().get("name", ""), timeline="\n".join(lines))
        try:
            p = subprocess.run(["claude", "-p", "--output-format", "text", "--allowedTools", "Read"], input=prompt,
                               capture_output=True, text=True, timeout=900, cwd=tmp)
            data = extract_json(p.stdout)
        except Exception as e:
            r.needs_human.append(f"映像の内容審査に失敗: {e}")
            return
    v = max(0.0, min(15.0, float(data.get("visual", 0))))
    r.scores["映像の品質"] = min(r.scores.get("映像の品質", 15.0), v)
    for it in data.get("issues", [])[:6]:
        r.issues.append(("medium", f"映像: {it}"))
    for h in data.get("human_review", []):
        if h:
            r.needs_human.append(f"映像: {h}")


def kind_of(vdir: Path, plan: dict) -> str:
    if plan.get("shorts"):
        return "short"
    if plan.get("sleep") or float(plan.get("target_seconds") or 0) >= 1200:
        return "sleep"
    return "long"


def review(vdir: Path, use_llm: bool = True, min_score: float = 85, exclude: list | None = None) -> dict:
    vdir = Path(vdir)
    plan = json.loads((vdir / "plan.json").read_text(encoding="utf-8"))
    kind = kind_of(vdir, plan)
    r = QAResult()
    tech = check_technical(vdir / "video.mp4", kind, r)
    check_subtitles(vdir, kind, r)
    meta = check_metadata(vdir, kind, r)
    sim = check_originality(vdir, plan, r, exclude)
    title = (meta.get("titles") or [plan.get("theme", "")])[0]
    if use_llm:
        llm_review(plan, title, kind, r)
        visual_review(vdir, plan, r, kind)
    else:
        r.needs_human.append("事実確認 (LLM) を省略")
        r.scores.setdefault("情報の正確性", 10)
        r.scores.setdefault("台本の品質", 10)
    out = r.to_json(min_score) | {"kind": kind, "title": title, "technical": tech, "max_similarity": round(sim, 3)}
    (vdir / "qa.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (vdir / "qa.md").write_text(render_md(out), encoding="utf-8")
    if r.sources:
        append_sources(vdir, r.sources)
    return out


def append_sources(vdir: Path, sources: list[dict]) -> None:
    """裏取りに使った実在の URL を概要欄の「出典」に追記する (検索で見つかったものだけ)。"""
    mp = vdir / "metadata.json"
    meta = json.loads(mp.read_text(encoding="utf-8"))
    urls = list(dict.fromkeys(s["url"] for s in sources if s.get("url", "").startswith("http")))[:8]
    if not urls:
        return
    desc = re.sub(r"\n\n■ 参考資料[\s\S]*?(?=\n\n■|\Z)", "", meta.get("description", ""))
    block = "■ 参考資料 (内容の確認に使用)\n" + "\n".join(f"・{u}" for u in urls)
    meta["description"] = desc.replace("\n\n■ 使用素材", f"\n\n{block}\n\n■ 使用素材", 1) if "■ 使用素材" in desc else desc + "\n\n" + block
    meta["sources"] = sources
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def render_md(q: dict) -> str:
    v = {"pass": "公開候補 (合格)", "fix": "要修正 (基準未達)", "needs_review": "人間の確認が必要", "blocked": "公開禁止"}[q["verdict"]]
    lines = [f"# 品質審査: {q['title']}", "", f"- 判定: **{v}**", f"- 合計: **{q['total']} / 100**",
             f"- 形式: {q['kind']} / 過去動画との最大類似度: {q['max_similarity']:.0%}", "", "## 内訳"]
    lines += [f"- {k}: {s}" for k, s in q["scores"].items()]
    for head, key in (("公開禁止の理由", "blockers"), ("人間の確認が必要", "needs_human")):
        if q[key]:
            lines += ["", f"## {head}", *[f"- {x}" for x in q[key]]]
    if q["issues"]:
        lines += ["", "## 指摘事項", *[f"- [{s}] {m}" for s, m in q["issues"]]]
    if q["sources"]:
        lines += ["", "## 裏取りに使った出典", *[f"- {s['claim']} ({s['status']}): {s['url']}" for s in q["sources"]]]
    return "\n".join(lines) + "\n"
