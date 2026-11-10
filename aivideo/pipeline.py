"""テーマ → 完成 MP4 までの全工程。"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import audio, render, subtitles
from .config import ROOT, Settings, log
from .llm import get_llm
from .planner import all_scenes, make_plan
from .tts import Narrator, get_tts
from .visuals import SceneImager, make_thumbnail

TRANS = 0.6        # 場面転換の長さ (秒)
LEAD = 0.45        # シーン開始からナレーションまでの間
TAIL = 0.35        # ナレーション後の余韻
CHAPTER_PAUSE = 0.4
END_HOLD = 2.0


def slugify(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", s).strip("_")
    return s[:40] or "video"


def fmt_ts(t: float) -> str:
    t = int(t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_timeline(scenes: list[dict], spoken: list) -> list[dict]:
    """各シーンの開始時刻・長さ・ナレーション開始時刻を決める (xfade の重なりを考慮)。"""
    tl, t = [], 0.0
    prev_ch = None
    for k, (sc, sp) in enumerate(zip(scenes, spoken)):
        lead = LEAD + (0.3 if k == 0 else 0) + (CHAPTER_PAUSE if prev_ch is not None and sc["chapter"] != prev_ch else 0)
        last = k == len(scenes) - 1
        dur = lead + sp.duration + (END_HOLD if last else TAIL + TRANS)
        tl.append({"start": t, "duration": dur, "voice_start": t + lead})
        t += dur - (0 if last else TRANS)
        prev_ch = sc["chapter"]
    return tl


def sfx_events(scenes, tl) -> list[tuple[float, str]]:
    ev = []
    for sc, tm in zip(scenes, tl):
        kind = sc.get("sfx", "none")
        if kind == "whoosh":
            ev.append((max(0, tm["start"] - 0.15), "whoosh"))
        elif kind == "impact":
            ev.append((tm["start"] + 0.05, "impact"))
        elif kind == "pop":
            ev.append((tm["voice_start"] - 0.1, "pop"))
        elif kind == "chime":
            ev.append((tm["start"] + 0.15, "chime"))
    return ev


def write_metadata(plan, scenes, tl, total, credits, out_dir: Path) -> None:
    chapters = []
    for ci, ch in enumerate(plan["chapters"]):
        idx = next((k for k, s in enumerate(scenes) if s["chapter"] == ci), None)
        if idx is not None:
            chapters.append((0.0 if not chapters else tl[idx]["start"], ch["title"]))
    # YouTube のチャプター条件: 0:00 開始・3 個以上・各 10 秒以上
    valid = len(chapters) >= 3 and all(
        b[0] - a[0] >= 10 for a, b in zip(chapters, chapters[1:] + [(total, "")]))
    chap_txt = "\n".join(f"{fmt_ts(t)} {title}" for t, title in chapters) if valid else ""

    desc = plan.get("description", "").strip()
    body = desc
    if chap_txt:
        body += "\n\n■ チャプター\n" + chap_txt
    body += "\n\n■ 使用素材\n" + "\n".join(f"・{c}" for c in sorted(credits))
    body += "\n・BGM・効果音: 本システムによるオリジナル自動生成"

    meta = {
        "titles": plan.get("titles", []),
        "description": body,
        "tags": plan.get("tags", []),
        "thumbnail": plan.get("thumbnail", {}),
        "chapters": [{"time": fmt_ts(t), "title": ti} for t, ti in chapters],
        "duration_sec": round(total, 2),
        "concept": plan.get("concept", {}),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    th = plan.get("thumbnail", {})
    md = [f"# {plan.get('theme', '')}", "", f"動画の長さ: {fmt_ts(total)}", "",
          "## タイトル案", *[f"{i}. {t}" for i, t in enumerate(plan.get("titles", []), 1)], "",
          "## 概要欄（そのままコピーして使えます）", "", "```", body, "```", "",
          "## タグ", ", ".join(plan.get("tags", [])), "",
          "## サムネイル案", f"- 文字: 「{th.get('text', '')}」 / 「{th.get('sub_text', '')}」",
          *[f"- {i}" for i in th.get("ideas", [])], "- 生成済みサムネイル: thumbnail.png", "",
          "## 企画", *[f"- {k}: {v}" for k, v in plan.get("concept", {}).items()], "",
          "## 台本", ""]
    for ci, ch in enumerate(plan["chapters"]):
        md.append(f"### {ch['title']}")
        for sc in ch.get("scenes", []):
            k = scenes.index(sc)
            md.append(f"- `{fmt_ts(tl[k]['start'])}` {sc['narration']}")
        md.append("")
    (out_dir / "metadata.md").write_text("\n".join(md), encoding="utf-8")


def make_video(theme: str, seconds: float, settings: Settings, out_root: Path | None = None,
               plan_path: Path | None = None, workers: int = 3) -> Path:
    t_start = time.time()
    render.check_ffmpeg()
    out_root = out_root or ROOT / "output"
    out_dir = out_root / f"{datetime.now():%Y%m%d_%H%M%S}_{slugify(theme)}"
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    cache = ROOT / ".cache"
    log(f"出力先: {out_dir}")

    # 1-3. 企画・台本・シーン分割
    if plan_path:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        log(f"既存の台本を使用: {plan_path}")
    else:
        plan = make_plan(get_llm(settings), theme, seconds)
    (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    scenes = all_scenes(plan)
    log(f"台本完成: {len(plan['chapters'])}章 / {len(scenes)}シーン / "
        f"{sum(len(s['narration']) for s in scenes)}文字")

    # 5. ナレーション (目標尺から大きくずれたら話速を調整して 1 回だけ再合成)
    engine = get_tts(settings)
    narrator = Narrator(engine, cache / "tts")
    log("ナレーション音声を合成中...")
    spoken = [narrator.speak(s["narration"]) for s in scenes]
    est = build_timeline(scenes, spoken)[-1]
    est_total = est["start"] + est["duration"]
    ratio = est_total / seconds
    if not plan_path and (ratio > 1.12 or ratio < 0.88):
        new_speed = max(0.9, min(1.2, engine.speed * (ratio ** 0.9)))
        log(f"推定 {est_total:.0f}秒 (目標 {seconds:.0f}秒) → 話速を {engine.speed:.2f}→{new_speed:.2f} に調整")
        engine.speed = new_speed
        spoken = [narrator.speak(s["narration"]) for s in scenes]

    tl = build_timeline(scenes, spoken)
    total = tl[-1]["start"] + tl[-1]["duration"]
    log(f"動画の長さ: {total:.1f}秒")

    # 4. シーン画像
    imager = SceneImager(settings, plan, cache / "images")
    log("シーン画像を生成中...")
    img_paths = [work / f"{s['id']}.png" for s in scenes]
    bases = {}
    img_workers = 1 if imager.ai else workers

    def mk_img(k):
        bases[k] = imager.render(scenes[k], img_paths[k])

    with ThreadPoolExecutor(max_workers=img_workers) as ex:
        for i, _ in enumerate(ex.map(mk_img, range(len(scenes))), 1):
            if i % 5 == 0 or i == len(scenes):
                log(f"  画像 {i}/{len(scenes)}")

    # 8a. カメラワーク付きシーン映像
    log("シーン映像をレンダリング中 (カメラワーク)...")
    clip_paths = [work / f"{s['id']}.mp4" for s in scenes]
    render.render_clips([(img_paths[k], clip_paths[k], tl[k]["duration"], scenes[k]["camera"])
                         for k in range(len(scenes))], workers=workers)

    # 6. BGM・効果音・ナレーションのミックス
    log("BGM・効果音を合成してミックス中...")
    mixed = audio.mix(total, [(tm["voice_start"], sp.audio) for tm, sp in zip(tl, spoken)],
                      sfx_events(scenes, tl), plan.get("bgm_mood", "calm"))
    wav = work / "mix.wav"
    audio.write_wav(wav, mixed)

    # 7. 字幕
    sents = [(txt, tm["voice_start"] + a, tm["voice_start"] + b)
             for tm, sp in zip(tl, spoken) for txt, a, b in sp.sentences]
    events = subtitles.build_events(sents)
    ass = work / "subtitles.ass"
    subtitles.write_ass(events, ass, settings.font_family)
    subtitles.write_srt(events, out_dir / "subtitles.srt")

    # 8b-9. 結合・書き出し
    final = out_dir / "video.mp4"
    render.assemble(clip_paths, [tm["duration"] for tm in tl], [s["transition"] for s in scenes],
                    TRANS, wav, ass, settings.font_path, final, total)

    # 10. サムネイル・メタデータ
    th = plan.get("thumbnail", {})
    make_thumbnail(bases[0], th.get("text", theme), th.get("sub_text", ""), settings.font_path,
                   out_dir / "thumbnail.png")
    credits = set(imager.used) | {engine.credit}
    write_metadata(plan, scenes, tl, total, credits, out_dir)

    info = render.probe(final)
    log(f"完成: {final}  ({float(info['format']['duration']):.1f}秒, "
        f"処理時間 {time.time() - t_start:.0f}秒)")
    return final
