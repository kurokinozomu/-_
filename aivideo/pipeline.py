"""テーマ → 完成 MP4 までの全工程。"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import audio, render, subtitles
from . import animate as anim_mod
from . import registry
from . import talk as talk_mod
from . import config, visuals
from .config import ROOT, Settings, log
from .llm import get_llm
from .planner import all_scenes, make_plan
from .tts import Narrator, get_tts
from . import assets
from .visuals import SceneImager, vivid

TRANS = 0.6        # 場面転換の長さ (秒)
LEAD = 0.45        # シーン開始からナレーションまでの間
TAIL = 0.35        # ナレーション後の余韻
CHAPTER_PAUSE = 0.4
END_HOLD = 2.0


def use_profile(shorts: bool, talk: bool = False) -> None:
    """ショート (縦型・テンポ重視) / 通常 (横型) / 掛け合い の編集設定に切り替える。"""
    global TRANS, LEAD, TAIL, CHAPTER_PAUSE, END_HOLD
    config.set_vertical(shorts)
    visuals.set_canvas(config.WIDTH, config.HEIGHT)
    subtitles.configure(shorts, talk)
    if talk:  # セリフの応酬: 間を詰めて、転換はごく短く
        TRANS, LEAD, TAIL, CHAPTER_PAUSE, END_HOLD = 0.12, 0.06, 0.1, 0.25, 1.5
    elif shorts:
        TRANS, LEAD, TAIL, CHAPTER_PAUSE, END_HOLD = 0.3, 0.15, 0.12, 0.0, 1.2
    else:
        TRANS, LEAD, TAIL, CHAPTER_PAUSE, END_HOLD = 0.6, 0.45, 0.35, 0.4, 2.0


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
        dur = lead + sp.duration + float(sc.get("hold", 0) or 0) + (END_HOLD if last else TAIL + TRANS)
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
               plan_path: Path | None = None, workers: int = 3, shorts: bool = False,
               animate: bool = False) -> Path:
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
        shorts = shorts or bool(plan.get("shorts"))
        log(f"既存の台本を使用: {plan_path}")
    else:
        plan = make_plan(get_llm(settings), theme, seconds, shorts=shorts,
                         avoid=registry.used_items(limit=int(os.environ.get("AIVIDEO_AVOID_LIMIT", "400"))))
    from .planner import TALK_RE
    if plan.get("talk") or TALK_RE.search(plan.get("theme", "")) or any(
            s.get("expr") for ch in plan.get("chapters", []) for s in ch.get("scenes", [])):
        plan["talk"] = True
        plan.setdefault("cast", talk_mod.DEFAULT_CAST)
        plan.setdefault("voices", dict(talk_mod.DEFAULT_VOICES))
        plan.setdefault("colors", dict(talk_mod.DEFAULT_COLORS))
        names = [c["name"] for c in plan["cast"]]
        k = 0
        for ch in plan.get("chapters", []):
            for s in ch.get("scenes", []):
                if s.get("speaker") not in names:
                    s["speaker"] = names[k % len(names)]
                k += 1
                s["sfx"] = s.get("sfx") if s.get("onscreen_text") else "none"
    use_profile(shorts, bool(plan.get("talk")))
    if shorts:
        log("ショート動画 (縦 1080x1920) として制作します")
        settings.tts_speed = max(settings.tts_speed, 1.18)
    (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    scenes = all_scenes(plan)
    log(f"台本完成: {len(plan['chapters'])}章 / {len(scenes)}シーン / "
        f"{sum(len(s['narration']) for s in scenes)}文字")

    # 5. ナレーション (目標尺から大きくずれたら話速を調整して 1 回だけ再合成)
    engine = get_tts(settings)
    narrator = Narrator(engine, cache / "tts")
    voices = plan.get("voices") or {}
    cast_engines = {}
    if voices and engine.name == "voicevox":  # ドラマ: 役ごとに別の声
        from .tts import VoicevoxTTS
        for role, sid in voices.items():
            cast_engines[role] = Narrator(VoicevoxTTS(settings.voicevox_url, int(sid), engine.speed), cache / "tts")
        log("配役: " + " / ".join(f"{r}={n.engine.credit.replace('VOICEVOX:', '')}" for r, n in cast_engines.items()))
    elif voices:
        log("役ごとの声には VOICEVOX が必要です。全員同じ声で読み上げます。")

    def speak(sc):
        return cast_engines.get(sc.get("speaker", ""), narrator).speak(sc["narration"])

    log("ナレーション音声を合成中...")
    spoken = [speak(s) for s in scenes]
    est = build_timeline(scenes, spoken)[-1]
    est_total = est["start"] + est["duration"]
    ratio = est_total / seconds
    if not cast_engines and (ratio > 1.12 or ratio < 0.88):
        new_speed = max(0.9, min(1.2, engine.speed * (ratio ** 0.9)))
        log(f"推定 {est_total:.0f}秒 (目標 {seconds:.0f}秒) → 話速を {engine.speed:.2f}→{new_speed:.2f} に調整")
        engine.speed = new_speed
        spoken = [narrator.speak(s["narration"]) for s in scenes]

    tl = build_timeline(scenes, spoken)
    total = tl[-1]["start"] + tl[-1]["duration"]
    log(f"動画の長さ: {total:.1f}秒")

    # 4. シーン画像
    if plan.get("ranking"):  # ランキング: 文字が多いので、カメラは少し寄るだけ
        for sc in scenes:
            sc["camera"] = "push"
            sc["onscreen_text"] = ""
    if plan.get("hud"):
        for sc in scenes:
            sc["onscreen_text"] = ""
        os.environ.setdefault("AIVIDEO_AI_EVERY", "1")
    if plan.get("drama"):  # ドラマ: 全カット AI 画像
        os.environ.setdefault("AIVIDEO_AI_EVERY", "1")
    plan["_animate"] = animate  # キャラクターの居場所を空けたレイアウトにする
    imager = SceneImager(settings, plan, cache / "images")
    log("シーン画像を生成中...")
    img_paths = [work / f"{s['id']}.png" for s in scenes]
    telops = {}
    img_workers = 1 if imager.ai else workers

    # 掛け合い: セリフごとに背景を変えると落ち着かないので、話題 (見出し/イラスト) が変わるまで同じ背景を使う
    leader = list(range(len(scenes)))
    if plan.get("talk"):
        for k in range(1, len(scenes)):
            same = (not scenes[k].get("onscreen_text")) and (
                scenes[k].get("emoji") == scenes[leader[k - 1]].get("emoji") or k - leader[k - 1] < 3)
            if same and scenes[k].get("chapter") == scenes[k - 1].get("chapter"):
                leader[k] = leader[k - 1]
                scenes[k]["camera"] = "hold"
                scenes[k]["transition"] = "fade"
        for k in range(len(scenes)):
            if leader[k] == k:
                scenes[k]["camera"] = "push"

    def mk_img(k):
        if leader[k] != k:
            return
        telops[k] = imager.render(scenes[k], img_paths[k])

    with ThreadPoolExecutor(max_workers=img_workers) as ex:
        for i, _ in enumerate(ex.map(mk_img, range(len(scenes))), 1):
            if i % 5 == 0 or i == len(scenes):
                log(f"  画像 {i}/{len(scenes)}")

    # 8a. カメラワーク付きシーン映像
    log("シーン映像をレンダリング中 (カメラワーク)...")
    clip_paths = [work / f"{s['id']}.mp4" for s in scenes]
    for k in range(len(scenes)):  # 同じ背景を使うシーン
        if leader[k] != k:
            img_paths[k] = img_paths[leader[k]]
            telops[k] = telops.get(leader[k])
    if plan.get("talk"):
        log("掛け合い (左右のキャラクターが口パクで会話) で描画します")
        env = anim_mod.voice_envelope(total, [(tm["voice_start"], sp.audio) for tm, sp in zip(tl, spoken)])
        jobs = [(img_paths[k], clip_paths[k], tl[k]["duration"], sc["camera"], telops.get(k), tl[k]["start"], env,
                 {"cast": plan["cast"], "speaker": sc.get("speaker", ""), "expr": sc.get("expr", "normal"),
                  "seed": k, "slide": leader[k] == k})
                for k, sc in enumerate(scenes)]
        done = [0]

        def one_talk(job):
            talk_mod.render_talk_clip(*job)
            done[0] += 1
            if done[0] % 10 == 0 or done[0] == len(jobs):
                log(f"  シーン映像 {done[0]}/{len(jobs)}")

        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(one_talk, jobs))
    elif animate:
        log("アニメーション演出 (口パクするキャラクター・声のエフェクト) で描画します")
        env = anim_mod.voice_envelope(total, [(tm["voice_start"], sp.audio) for tm, sp in zip(tl, spoken)])
        hud = plan.get("hud") or {}
        end_sec = float(hud.get("end_sec") or 0) or max(
            [float(sc.get("at_sec", 0) or 0) for sc in scenes] + [1.0])

        def intensity(k):
            if not hud:
                return 0.0
            return max(0.0, min(1.0, float(scenes[k].get("at_sec", 0) or 0) / end_sec))

        jobs = []
        for k, sc in enumerate(scenes):
            i0 = intensity(k)
            i1 = intensity(k + 1) if k + 1 < len(scenes) else i0
            debris = [assets.emoji_image(e, int(config.WIDTH * 0.11)) for e in sc.get("emoji", [])]
            jobs.append((img_paths[k], clip_paths[k], tl[k]["duration"], sc["camera"], telops[k],
                         tl[k]["start"], env, {"intensity": (i0, max(i0, i1)), "debris": debris, "seed": k, "hud": bool(hud)}))
        done = [0]

        def one(job):
            anim_mod.render_animated_clip(*job)
            done[0] += 1
            if done[0] % 5 == 0 or done[0] == len(jobs):
                log(f"  シーン映像 {done[0]}/{len(jobs)}")

        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(one, jobs))
    else:
        render.render_clips([(img_paths[k], clip_paths[k], tl[k]["duration"], scenes[k]["camera"], telops[k])
                             for k in range(len(scenes))], workers=workers)

    # 6. BGM・効果音・ナレーションのミックス
    log("BGM・効果音を合成してミックス中...")
    mixed = audio.mix(total, [(tm["voice_start"], sp.audio) for tm, sp in zip(tl, spoken)],
                      sfx_events(scenes, tl), plan.get("bgm_mood", "calm"))
    wav = work / "mix.wav"
    audio.write_wav(wav, mixed)

    # 7. 字幕
    colors = plan.get("colors") or {}
    sents = [(txt, tm["voice_start"] + a, tm["voice_start"] + b, sc.get("highlight", []),
              colors.get(sc.get("speaker", "")))
             for sc, tm, sp in zip(scenes, tl, spoken) for txt, a, b in sp.sentences]
    events = subtitles.build_events(sents)
    ass = work / "subtitles.ass"
    sub_font = assets.font("subtitle")
    sub_font_path, sub_font_name = sub_font if sub_font else (settings.font_path, settings.font_family)
    outer = vivid(imager.palette[0], 0.2, 0.3, 0.7) if imager.palette else (20, 60, 140)
    if plan.get("hud"):
        outer = (0, 0, 0)  # ドキュメンタリー調: 色フチなしの白文字 + 黒フチ
    subtitles.write_ass(events, ass, sub_font_name, outer, config.WIDTH, config.HEIGHT)
    hud = plan.get("hud")
    if hud:  # 「1秒ごとに2倍」系: 経過秒数と倍率のカウンターを常に表示
        anchors = [(tm["voice_start"], float(sc["at_sec"]), str(sc.get("level", "")))
                   for sc, tm in zip(scenes, tl) if isinstance(sc.get("at_sec"), (int, float))]
        if anchors:
            serif = assets.font("serif")
            hud_ev = subtitles.hud_events(hud, anchors, total)
            subtitles.write_hud(ass, hud, hud_ev, serif[1] if serif else sub_font_name,
                                sub_font_name, config.WIDTH, config.HEIGHT)
    subtitles.write_srt(events, out_dir / "subtitles.srt")

    # 8b-9. 結合・書き出し
    final = out_dir / "video.mp4"
    render.assemble(clip_paths, [tm["duration"] for tm in tl], [s["transition"] for s in scenes],
                    TRANS, wav, ass, sub_font_path, final, total)

    # 10. サムネイル・メタデータ
    if not shorts:  # ショートはアプリ上で動画内のフレームを表紙に選ぶ
        imager.thumbnail(out_dir / "thumbnail.png")
    credits = set(imager.used) | ({n.engine.credit for n in cast_engines.values()} or {engine.credit})
    if sub_font or imager.heavy_font:
        credits.add("フォント: M PLUS Rounded 1c / Dela Gothic One (SIL Open Font License)")
    write_metadata(plan, scenes, tl, total, credits, out_dir)

    try:
        registry.register(plan, out_dir)  # ネタかぶり防止・投稿管理のために記録
    except Exception as e:
        log(f"記録の保存に失敗: {e}")
    info = render.probe(final)
    log(f"完成: {final}  ({float(info['format']['duration']):.1f}秒, "
        f"処理時間 {time.time() - t_start:.0f}秒)")
    return final
