"""企画・台本・シーン分割・YouTube メタデータを作る。

長尺でも破綻しないよう 2 段階で生成する:
  1. 企画 + 章立て (タイトル案・概要欄・サムネ案・BGM ムードも同時に)
  2. 章ごとにシーン (ナレーション / 画像プロンプト / カメラワーク / 転換) を生成
"""
from __future__ import annotations

import math
import os
from typing import Any

from .config import log
from .llm import complete_json

# 合成音声の読み上げ速度 (文字/秒) と、尺に占めるナレーションの割合
CHARS_PER_SEC = 6.0
NARRATION_RATIO = 0.86

CAMERAS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]
TRANSITIONS = ["fade", "slideleft", "slideright", "circleopen",
               "wipeleft", "smoothleft", "fadeblack", "radial", "zoomin"]
MOODS = ["calm", "upbeat", "mysterious", "epic", "warm"]

SYSTEM_TEMPLATE = """あなたは登録者数100万人超の日本の教養・エンタメ系YouTubeチャンネルを手がける
トップクラスのプロデューサー兼構成作家です。視聴維持率を最大化する台本を書きます。

原則:
- 冒頭5秒で強いフック（意外な事実・問い・矛盾）を提示し、最後まで見る理由を作る
- 「実は」「ところが」など展開の変化を定期的に入れ、単調さを避ける
- 各章の終わりに次章への小さな引き（オープンループ）を置く
- 一文は短く、耳で聞いて分かる日本語。専門用語には一言で説明を添える
- 語り口は「{tone}」。視聴者に語りかけるように、
  「〜なんです」「〜ですよね」「〜みましょう」などを自然に混ぜ、硬い断定や命令口調を避ける
- 事実関係は一般に確立された内容のみ。不確かな数字や断定は避ける
- 実在の人物・企業・作品の画像やロゴ、著作物を素材として要求しない
- チャンネル名を勝手に作らない（指定がある場合のみ名乗る）
- 指定された文字数の目安を ±10% 以内で守る（尺に直結するため）
- 出力は指定された JSON のみ。前置きや説明文は書かない"""


DEFAULT_TONE = "やさしく親しみやすい、柔らかい語り口"


def system_prompt() -> str:
    return SYSTEM_TEMPLATE.replace("{tone}", os.environ.get("AIVIDEO_TONE", "").strip() or DEFAULT_TONE)


def _chapter_count(target_sec: float) -> int:
    if target_sec <= 75:
        return 1
    return max(3, min(12, round(target_sec / 75)))


def _concept_prompt(theme: str, target_sec: float, n_chapters: int) -> str:
    total_chars = int(target_sec * NARRATION_RATIO * CHARS_PER_SEC)
    return f"""テーマ「{theme}」で、長さ約{target_sec:.0f}秒のYouTube動画を企画してください。
ナレーション総文字数の目安は約{total_chars}文字です（合成音声で毎秒約{CHARS_PER_SEC:.0f}文字）。
章の数は{n_chapters}個にしてください（1個目は導入フック、最後はまとめ。1個だけなら全体で1章）。

次の JSON を出力:
{{
  "concept": {{
    "angle": "この動画ならではの切り口（1文）",
    "hook": "冒頭で視聴者を掴む一言",
    "target_audience": "想定視聴者",
    "promise": "視聴者が最後まで見ると得られるもの"
  }},
  "visual_style": "全シーン共通の画像スタイル（英語。例: cinematic digital painting, soft volumetric light, rich colors）",
  "bgm_mood": "{'|'.join(MOODS)} のいずれか",
  "palette": ["#RRGGBB", "#RRGGBB", "#RRGGBB"],
  "titles": ["YouTubeタイトル案を5個（32文字以内、数字や意外性を活用、釣りすぎない）"],
  "description": "概要欄の本文（300〜500文字、改行あり、ハッシュタグ3個を末尾に）",
  "tags": ["タグを10〜15個"],
  "thumbnail": {{
    "label": "左上の見出しラベル（6文字以内。例: 歴史IF / 衝撃の事実 / 徹底解説）",
    "line1": "1行目の大見出し（9文字以内。白文字で最も目立つ一言）",
    "line2": "2行目の大見出し（9文字以内。黄色文字。疑問や数字で好奇心をあおる）",
    "emphasis": "line1かline2の中の、赤で強調する語（そのまま含まれる2〜4文字）",
    "sub_text": "下帯の補足（16文字以内）",
    "badge": "丸いバッジの語（2〜4文字。例: 必見 / 衝撃 / 新説）",
    "emoji": ["サムネイルに大きく置くイラストの絵文字を2個（内容に直結する物。時代・国に合うもの）"],
    "image_prompt": "AI画像生成用のサムネイル背景（英語、文字なし、被写体が右側）",
    "ideas": ["サムネイル構図案を3個（日本語）"]
  }},
  "chapters": [
    {{"title": "章タイトル（15文字以内）", "goal": "この章で伝えること・展開", "seconds": 章の秒数}}
  ]
}}
chapters の seconds の合計は約{target_sec:.0f}にしてください。"""


def _scenes_prompt(theme: str, plan: dict, idx: int, prev_tail: str) -> str:
    ch = plan["chapters"][idx]
    secs = float(ch.get("seconds") or 30)
    chars = int(secs * NARRATION_RATIO * CHARS_PER_SEC)
    n_scenes = max(2, round(secs / 7))
    outline = "\n".join(
        f"{i + 1}. {c['title']} — {c.get('goal', '')}" for i, c in enumerate(plan["chapters"]))
    channel = os.environ.get("AIVIDEO_CHANNEL_NAME", "").strip()
    greet = f"チャンネル名は「{channel}」です。挨拶は一言だけ。" if channel else "チャンネル名は名乗らないでください。"
    position = (f"動画の冒頭です。最初の一文で強烈なフックを入れてください。{greet}"
                if idx == 0 else "")
    if idx == len(plan["chapters"]) - 1:
        position += "動画の最後です。要点を印象的にまとめ、最後に短く高評価・チャンネル登録を促してください。"
    cont = f"\n直前の章の最後のナレーション: 「{prev_tail}」\n自然に続けてください。" if prev_tail else ""
    return f"""テーマ「{theme}」の動画台本の一部を書きます。
企画の切り口: {plan['concept'].get('angle', '')}
全体の章立て:
{outline}

今回書くのは 第{idx + 1}章「{ch['title']}」（目標 約{secs:.0f}秒、ナレーション約{chars}文字）。
章の狙い: {ch.get('goal', '')}
{position}{cont}

これを約{n_scenes}個のシーンに分割してください。1シーンは4〜10秒（ナレーション25〜60文字、1〜3文）。
画像はシーンごとにAIで生成します。visual_prompt は英語で、具体的な被写体・構図・光・雰囲気を書き、
文字・ロゴ・実在の人物や作品は含めないでください（画面に文字を入れたい場合は onscreen_text を使う）。

次の JSON を出力:
{{
  "scenes": [
    {{
      "narration": "読み上げる日本語ナレーション（句読点で区切る。数字は読みやすく）",
      "onscreen_text": "画面に大きく出すキーワード（12文字以内、不要なら空文字）",
      "visual_prompt": "English image prompt",
      "camera": "{'|'.join(CAMERAS)} のいずれか（単調にならないよう変化をつける）",
      "transition": "{'|'.join(TRANSITIONS)} のいずれか（このシーンに入るときの転換）",
      "sfx": "none|whoosh|pop|impact|chime のいずれか（強調したい所だけ）",
      "emoji": ["このシーンの内容を表すイラスト用の絵文字を1〜3個（具体的な物・人・場所。例: 🏯🔥⚔️🚢）。テーマの時代・国に合わないもの（昔の日本の話で💲🏙️🛢️📱など）は選ばない"],
      "highlight": ["字幕で黄色く強調する語（narration にそのまま含まれる2〜8文字、0〜2個）"]
    }}
  ]
}}"""


def _shorts_prompt(theme: str, target_sec: float) -> str:
    chars = int(target_sec * 0.8 * 6.6)
    n = max(8, round(target_sec / 3.5))
    return f"""テーマ「{theme}」で、YouTubeショート（縦型・約{target_sec:.0f}秒）の台本を書いてください。
ナレーションは合計約{chars}文字（±10%）、約{n}シーン。1シーンは2〜4秒（ナレーション10〜25文字、1文）。

ショートの鉄則:
- 最初の1文（1〜2秒）で結論か強烈な問いを出す。挨拶・前置きは入れない
- 1シーン1情報。テンポよく畳みかけ、途中で「実は」「しかも」で展開を変える
- 最後は答えを言い切ってスッキリさせ、「詳しくは関連動画で」と一言だけ添える
- onscreen_text は全シーンに入れる（8文字以内、画面上部の大きな見出しになる）

次の JSON を出力:
{{
  "concept": {{"angle": "切り口（1文）", "hook": "最初の1文"}},
  "visual_style": "共通の画像スタイル（英語、縦構図 vertical composition を含める）",
  "bgm_mood": "{'|'.join(MOODS)} のいずれか（ショートは upbeat か mysterious が向く）",
  "palette": ["#RRGGBB", "#RRGGBB", "#RRGGBB"],
  "titles": ["ショートのタイトル案を5個（30文字以内、末尾に #shorts）"],
  "description": "概要欄（100〜200文字、ハッシュタグ3〜5個、#shorts を含む）",
  "tags": ["タグを8〜12個"],
  "thumbnail": {{"text": "表紙の短文（10文字以内）", "ideas": []}},
  "chapters": [{{"title": "{theme[:14]}", "goal": "", "scenes": [
    {{
      "narration": "読み上げる日本語（1文）",
      "onscreen_text": "見出し（8文字以内）",
      "visual_prompt": "English image prompt, vertical composition",
      "camera": "{'|'.join(CAMERAS)}",
      "transition": "{'|'.join(TRANSITIONS)}",
      "sfx": "none|whoosh|pop|impact|chime",
      "emoji": ["内容を表す絵文字1〜3個（時代・国に合うもの）"],
      "highlight": ["字幕で黄色く強調する語（narration にそのまま含まれる、0〜1個）"]
    }}
  ]}}]
}}"""


def make_plan(llm, theme: str, target_sec: float, shorts: bool = False) -> dict[str, Any]:
    if llm is None:
        log("LLM が利用できないため、オフラインテンプレートで台本を作成します（品質は限定的）。")
        plan = offline_plan(theme, target_sec)
        plan["shorts"] = shorts
        return plan

    if shorts:
        log(f"ショート動画の台本を生成中 ({llm.name})...")
        plan = complete_json(llm, system_prompt(), _shorts_prompt(theme, target_sec))
        plan.update(theme=theme, target_seconds=target_sec, shorts=True)
        for ch in plan.get("chapters", []):
            ch["scenes"] = [x for x in ch.get("scenes", []) if x.get("narration", "").strip()]
            ch["seconds"] = target_sec
        return normalize_plan(plan)

    n_ch = _chapter_count(target_sec)
    log(f"企画・章立てを生成中 ({llm.name}, {n_ch}章)...")
    plan = complete_json(llm, system_prompt(), _concept_prompt(theme, target_sec, n_ch))
    plan["theme"] = theme
    plan["target_seconds"] = target_sec
    _rescale_chapters(plan, target_sec)

    prev_tail = ""
    for i, ch in enumerate(plan["chapters"]):
        log(f"第{i + 1}/{len(plan['chapters'])}章「{ch['title']}」のシーンを生成中...")
        res = complete_json(llm, system_prompt(), _scenes_prompt(theme, plan, i, prev_tail))
        scenes = res["scenes"] if isinstance(res, dict) else res
        ch["scenes"] = [s for s in scenes if s.get("narration", "").strip()]
        if ch["scenes"]:
            prev_tail = ch["scenes"][-1]["narration"]
    return normalize_plan(plan)


def _rescale_chapters(plan: dict, target_sec: float) -> None:
    chs = plan.get("chapters") or [{"title": plan.get("theme", ""), "goal": ""}]
    total = sum(float(c.get("seconds") or 0) for c in chs) or len(chs)
    for c in chs:
        c["seconds"] = (float(c.get("seconds") or 1) / total) * target_sec
    plan["chapters"] = chs


def normalize_plan(plan: dict) -> dict:
    """LLM 出力の値を検証し、欠けている値を補う。"""
    plan.setdefault("visual_style", "cinematic digital illustration, soft light, rich colors")
    if plan.get("bgm_mood") not in MOODS:
        plan["bgm_mood"] = "calm"
    plan.setdefault("titles", [plan.get("theme", "")])
    plan.setdefault("tags", [])
    plan.setdefault("description", "")
    th = plan.setdefault("thumbnail", {})
    th.setdefault("text", plan.get("theme", "")[:12])
    th.setdefault("line1", th.get("text", "")[:9])
    th.setdefault("line2", "")
    th.setdefault("label", "")
    th.setdefault("badge", "")
    th.setdefault("emphasis", "")
    th.setdefault("ideas", [])
    th["emoji"] = [e for e in (th.get("emoji") or []) if isinstance(e, str)][:2]
    n = 0
    for ci, ch in enumerate(plan["chapters"]):
        for s in ch.get("scenes", []):
            s["id"] = f"s{n:03d}"
            s["chapter"] = ci
            if s.get("camera") not in CAMERAS:
                s["camera"] = CAMERAS[n % len(CAMERAS)]
            if s.get("transition") not in TRANSITIONS:
                s["transition"] = "fade"
            if s.get("sfx") not in ("none", "whoosh", "pop", "impact", "chime"):
                s["sfx"] = "none"
            s.setdefault("onscreen_text", "")
            s["emoji"] = [e for e in (s.get("emoji") or []) if isinstance(e, str)][:3]
            s["highlight"] = [h for h in (s.get("highlight") or [])
                              if isinstance(h, str) and h and h in s.get("narration", "")][:2]
            s.setdefault("visual_prompt", plan.get("theme", ""))
            n += 1
    # 章の頭は少し強めの演出
    for ch in plan["chapters"]:
        if ch.get("scenes"):
            first = ch["scenes"][0]
            first["_chapter_first"] = True
            if first["sfx"] == "none":
                first["sfx"] = "impact" if first["id"] == "s000" else "whoosh"
            if not first["onscreen_text"]:
                first["onscreen_text"] = ch["title"][:14]
    if n == 0:
        raise ValueError("台本にシーンがありません")
    return plan


def all_scenes(plan: dict) -> list[dict]:
    return [s for ch in plan["chapters"] for s in ch.get("scenes", [])]


# ---------------------------------------------------------------- オフライン
def offline_plan(theme: str, target_sec: float) -> dict:
    """LLM なしで動く最低限のテンプレート台本（動作確認・非常用）。"""
    n_body = max(1, math.ceil((target_sec - 20) / 30))
    intro = [
        (f"今日のテーマは、{theme}です。", theme[:12], "zoom_in", "fade", "impact"),
        (f"実は{theme}には、多くの人が知らない意外な一面があります。", "意外な一面", "pan_right", "dissolve", "none"),
        ("この動画を最後まで見れば、その理由がきっと分かるはずです。", "最後まで注目", "zoom_out", "slideleft", "pop"),
    ]
    body = []
    for i in range(n_body):
        k = i + 1
        body += [
            (f"ポイント{k}つ目。{theme}を理解するうえで大切な視点があります。", f"ポイント{k}", "zoom_in", "circleopen", "whoosh"),
            ("身近な例に置き換えて考えてみると、ぐっとイメージしやすくなります。", "身近な例で", "pan_left", "dissolve", "none"),
            ("ここを押さえておくと、次の話がもっと面白くなります。", "", "pan_up", "smoothleft", "none"),
        ]
    outro = [
        (f"いかがでしたか。{theme}は、知れば知るほど奥が深いテーマです。", "まとめ", "zoom_out", "fadeblack", "chime"),
        ("面白かったら、高評価とチャンネル登録をお願いします。また次の動画でお会いしましょう。", "チャンネル登録", "zoom_in", "fade", "pop"),
    ]

    def mk(items):
        return [dict(narration=n, onscreen_text=t, visual_prompt=f"{theme}, abstract concept art",
                     camera=c, transition=tr, sfx=sf) for n, t, c, tr, sf in items]

    chapters = [{"title": "導入", "goal": "", "scenes": mk(intro)}]
    if target_sec > 30:
        chapters.append({"title": "本編", "goal": "", "scenes": mk(body)})
    chapters.append({"title": "まとめ", "goal": "", "scenes": mk(outro)})
    plan = {
        "theme": theme, "target_seconds": target_sec,
        "concept": {"angle": "", "hook": "", "target_audience": "", "promise": ""},
        "visual_style": "abstract", "bgm_mood": "calm", "palette": [],
        "titles": [f"【解説】{theme}の意外な真実", f"知らないと損する{theme}の話"],
        "description": f"{theme}について分かりやすく解説します。\n\n#{theme.replace(' ', '')} #解説 #雑学",
        "tags": [theme, "解説", "雑学"],
        "thumbnail": {"text": theme[:12], "sub_text": "意外な真実", "ideas": []},
        "chapters": chapters,
    }
    return normalize_plan(plan)
