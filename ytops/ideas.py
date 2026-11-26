"""ネタ発掘と企画評価 (100 点満点)。

情報源: 自チャンネルの実績 (DB) / 過去に作った動画 (重複除外) / 季節・記念日 / LLM の Web 検索 (公開情報のみ)。
SNS のスクレイピングや規約で禁止された取得は行わない。

評価配点: 興味 20 / 冒頭の引き 15 / 独自性 20 / 情報の信頼性 15 / 視聴維持 10 / シリーズ性 5 / 実現性 5 / 収益化相性 10
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime

from . import db
from .config import JST, Channel
from .qa import similarity

WEIGHTS = {"interest": 20, "hook": 15, "originality": 20, "reliability": 15, "retention": 10,
           "series": 5, "feasibility": 5, "monetization": 10}

PROMPT = """あなたは YouTube チャンネル「{channel}」の企画責任者です。
チャンネルのコンセプト: {concept}
シリーズ: {series}
今日の日付: {today} (季節・年末年始・記念日も考慮)

{web_note}
条件:
- 新しい動画企画を {n} 本提案する。形式の内訳: short {n_short} 本 / long {n_long} 本 / sleep {n_sleep} 本
  - short: 30〜50 秒の縦型。1 つの意外な事実と、その理由を 1 つだけ。関連する長尺へ誘導できるもの
  - long: 8〜12 分の解説。暮らしの「なぜ」を史料・研究に基づいて解き明かす
  - sleep: 30〜60 分の睡眠用・聞き流し朗読。穏やかで刺激が少ない「暮らしの情景」を順にたどる
- 既存の動画・企画と重複しない (下の一覧を参照)。同じ型の言い換えで量産しない
- 史料・研究・公的機関の情報で裏付けられるテーマに限る。都市伝説・陰謀論・未確認情報は除外
- 実在の個人の名誉を傷つける内容、残酷描写が中心の内容は除外
- 各企画を次の基準で採点する (整数): interest(0-20) hook(0-15) originality(0-20) reliability(0-15)
  retention(0-10) series(0-5) feasibility(0-5) monetization(0-10)

既存の動画・企画 (重複禁止):
{existing}

出力は JSON 配列のみ:
[{{"theme": "動画のテーマ (指示文としてそのまま使える 1 文)", "kind": "short|long|sleep", "series": "シリーズ名",
  "hook": "冒頭 5 秒のひとこと", "angle": "独自の切り口 (他チャンネルとの違い)",
  "sources": ["裏付けに使える資料の種類や機関名 (例: 国立国会図書館デジタルコレクションの〇〇、〇〇博物館の解説)。URL は実際に確認したものだけ"],
  "scores": {{"interest": 0, "hook": 0, "originality": 0, "reliability": 0, "retention": 0, "series": 0,
             "feasibility": 0, "monetization": 0}}}}]
"""


def existing_themes(limit: int = 300) -> list[str]:
    from aivideo import registry
    with db.connect() as con:
        ideas = [r["theme"] for r in con.execute("SELECT theme FROM ideas ORDER BY id DESC LIMIT ?", (limit,))]
    vids = [v.get("title") or v.get("theme") for v in registry.load().get("videos", [])]
    return list(dict.fromkeys(ideas + vids))[:limit]


def total_score(scores: dict) -> float:
    return float(sum(max(0, min(WEIGHTS[k], float(scores.get(k, 0)))) for k in WEIGHTS))


def generate(n: int = 30, mix: tuple[int, int, int] | None = None, web: bool = True) -> list[dict]:
    from aivideo.llm import extract_json
    ch = Channel.load()
    if not shutil.which("claude"):
        raise RuntimeError("claude CLI がないため企画を自動生成できません")
    mix = mix or (round(n * 0.6), round(n * 0.3), n - round(n * 0.6) - round(n * 0.3))
    existing = existing_themes()
    prompt = PROMPT.format(
        channel=ch.get("name", "(未定)"), concept=ch.get("concept", ""),
        series=" / ".join(s["name"] + ": " + s["desc"] for s in ch.get("series", [])),
        today=datetime.now(JST).strftime("%Y-%m-%d"),
        web_note="WebSearch で最近の話題 (展示・発見・記念日) を 2〜3 回だけ調べ、関連する企画を数本混ぜてよい。" if web else "",
        n=n, n_short=mix[0], n_long=mix[1], n_sleep=mix[2],
        existing="\n".join(f"- {t}" for t in existing[:200]) or "(なし)")
    cmd = ["claude", "-p", "--output-format", "text"] + (["--allowedTools", "WebSearch"] if web else [])
    with tempfile.TemporaryDirectory() as tmp:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=1800, cwd=tmp)
    items = extract_json(p.stdout)
    return [i for i in items if isinstance(i, dict) and i.get("theme")]


def store(items: list[dict], min_score: float = 70) -> tuple[int, int]:
    """重複を除いて保存する。基準点未満・既存と似すぎる企画は rejected として記録 (理由つき)。"""
    added = rejected = 0
    existing = existing_themes(1000)
    for it in items:
        sc = it.get("scores", {})
        total = total_score(sc)
        dup = max((similarity(it["theme"], e) for e in existing), default=0)
        status = "new"
        if dup >= 0.6:
            status, it["reject_reason"] = "rejected", f"既存と重複 ({dup:.0%})"
        elif total < min_score:
            status, it["reject_reason"] = "rejected", f"評価 {total} 点 (基準 {min_score} 点未満)"
        with db.connect() as con:
            try:
                con.execute("""INSERT INTO ideas(theme,kind,series,hook,angle,sources,score,score_json,status,created_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            (it["theme"], it.get("kind", "short"), it.get("series", ""), it.get("hook", ""),
                             it.get("angle", ""), json.dumps(it.get("sources", []), ensure_ascii=False), total,
                             json.dumps(sc | ({"reject_reason": it["reject_reason"]} if status == "rejected" else {}),
                                        ensure_ascii=False), status, db.now()))
            except Exception:
                continue
        existing.append(it["theme"])
        added += status == "new"
        rejected += status == "rejected"
    return added, rejected


def stock() -> dict:
    with db.connect() as con:
        return {r["kind"]: r["n"] for r in con.execute(
            "SELECT kind, COUNT(*) n FROM ideas WHERE status='new' GROUP BY kind")}


def pick(kind: str) -> dict | None:
    """評価の高い順。人気シリーズ (改善ルールで指定) を優先。"""
    rules = db.active_rules()
    boost = rules.get("boost_series") or []
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM ideas WHERE status='new' AND kind=? ORDER BY score DESC LIMIT 30", (kind,))]
    if not rows:
        return None
    rows.sort(key=lambda r: (r["series"] in boost, r["score"]), reverse=True)
    return rows[0]


def mark(idea_id: int, status: str) -> None:
    with db.connect() as con:
        con.execute("UPDATE ideas SET status=? WHERE id=?", (status, idea_id))


def export_markdown(path) -> None:
    with db.connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM ideas ORDER BY status, kind, score DESC")]
    lines = ["# 企画ストック", "", f"更新: {db.now()} / 未使用 {stock()}", "",
             "| # | 状態 | 形式 | 点 | シリーズ | テーマ | 冒頭の引き |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['status']} | {r['kind']} | {r['score']:.0f} | {r['series']} | "
                     f"{r['theme']} | {(r['hook'] or '').replace('|', '／')} |")
    from pathlib import Path
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
