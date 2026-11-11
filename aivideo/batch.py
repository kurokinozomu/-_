"""量産用: まとめて制作 / 事実チェック / 投稿管理表 / タイトル提案。

    python -m aivideo --batch titles.txt --shorts --seconds 40
    python -m aivideo --suggest "雑学" --count 30
    python -m aivideo --sheet output/batch_xxx
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from . import registry
from .config import ROOT, Settings, log
from .llm import complete_json, get_llm

FACT_SYSTEM = """あなたは厳格なファクトチェッカーです。動画台本の事実関係を確認し、
誤り・誇張・根拠の弱い俗説・安全上問題のある助言を指摘します。出力は JSON のみ。"""


def read_titles(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t = re.sub(r"^\s*\d+\s*[.．、)）]\s*", "", line).strip()
        if t and not t.startswith("#"):
            out.append(t)
    return out


def _video_dir(out_root: Path, title: str) -> Path | None:
    from .pipeline import slugify
    cands = sorted(p for p in out_root.glob(f"*_{slugify(title)}") if (p / "video.mp4").exists())
    return cands[-1] if cands else None


def fact_check(llm, plan: dict) -> list[dict]:
    lines = []
    for ch in plan.get("chapters", []):
        for s in ch.get("scenes", []):
            head = f"第{s['rank']}位 {s.get('item', '')}" if s.get("rank") else (s.get("item") or "")
            lines.append(f"- {head}: {s.get('narration', '')} / コメント: {s.get('comment', '')}")
    prompt = f"""テーマ「{plan.get('theme', '')}」の動画台本です。各項目の事実関係を確認してください。

{chr(10).join(lines)}

次の JSON を出力（問題がなければ issues は空配列）:
{{"issues": [{{"item": "項目名", "severity": "high|medium|low",
  "problem": "何が問題か（誤り・誇張・俗説・危険な助言など）", "suggestion": "直し方"}}]}}
high = 明らかな誤り・危険な助言、medium = 誇張や異説あり、low = 言い回しの改善程度。"""
    res = complete_json(llm, FACT_SYSTEM, prompt)
    return res.get("issues", []) if isinstance(res, dict) else []


def run_batch(titles_file: Path, out_root: Path, seconds: float | None, shorts: bool,
              extra_args: list[str] | None = None, check: bool = True) -> Path:
    titles = read_titles(titles_file)
    out_root.mkdir(parents=True, exist_ok=True)
    report = out_root / "check_report.json"
    results = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    settings = Settings.from_env()
    llm = get_llm(settings) if check else None
    log(f"まとめて制作: {len(titles)}本 → {out_root}")
    for i, title in enumerate(titles, 1):
        d = _video_dir(out_root, title)
        if d is None:
            log(f"[{i}/{len(titles)}] {title}")
            cmd = [sys.executable, "-m", "aivideo", "--theme", title, "--out", str(out_root)]
            if shorts:
                cmd.append("--shorts")
            if seconds:
                cmd += ["--seconds", str(seconds)]
            cmd += extra_args or []
            t0 = time.time()
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, cwd=ROOT)
            d = _video_dir(out_root, title)
            if proc.returncode != 0 or d is None:
                log(f"  失敗しました: {title}")
                results[title] = {"error": f"exit {proc.returncode}"}
                report.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
                continue
            log(f"  完成 ({time.time() - t0:.0f}秒)")
        else:
            log(f"[{i}/{len(titles)}] 作成済み: {title}")
        if title in results and "issues" in results[title]:
            continue
        plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
        entry = {"dir": str(d), "duplicates": [list(x) for x in registry.duplicates(plan, str(d.resolve()))]}
        if llm is not None:
            try:
                entry["issues"] = fact_check(llm, plan)
            except Exception as e:
                entry["issues"] = [{"item": "-", "severity": "medium", "problem": f"自動チェック失敗: {e}",
                                    "suggestion": "手動で確認"}]
        results[title] = entry
        report.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        n_hi = sum(1 for x in entry.get("issues", []) if x.get("severity") == "high")
        log(f"  チェック: 要確認 {len(entry.get('issues', []))}件 (重大 {n_hi}) / 重複候補 {len(entry['duplicates'])}件")
    write_sheet(out_root, titles)
    return out_root


def write_sheet(out_root: Path, titles: list[str] | None = None) -> Path:
    """投稿管理表 (Excel で開ける CSV) と、要確認の一覧 (Markdown) を作る。"""
    report_p = out_root / "check_report.json"
    results = json.loads(report_p.read_text(encoding="utf-8")) if report_p.exists() else {}
    if titles is None:
        titles = list(results)
    rows, md = [], [f"# 投稿管理表 ({datetime.now():%Y-%m-%d})", ""]
    for i, title in enumerate(titles, 1):
        d = _video_dir(out_root, title)
        r = results.get(title, {})
        if d is None:
            rows.append([i, title, "", "", "", "", "", "未完成", r.get("error", "")])
            continue
        meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        issues = r.get("issues", [])
        dups = r.get("duplicates", [])
        note = " / ".join(f"[{x.get('severity')}] {x.get('item')}: {x.get('problem')}" for x in issues)
        if dups:
            note += (" / " if note else "") + "重複候補: " + "、".join(f"{a}≒{b}({t})" for a, b, t in dups[:5])
        rows.append([i, (meta.get("titles") or [title])[0], title, str((d / "video.mp4").relative_to(ROOT)),
                     meta.get("duration_sec", ""), meta.get("description", ""), ", ".join(meta.get("tags", [])),
                     "要確認" if any(x.get("severity") == "high" for x in issues) or dups else "OK", note])
        md.append(f"## {i}. {title}")
        md.append(f"- 動画: `{(d / 'video.mp4').relative_to(ROOT)}` ({meta.get('duration_sec', '')}秒)")
        md.append(f"- タイトル案: {(meta.get('titles') or [''])[0]}")
        for x in issues:
            md.append(f"- **[{x.get('severity')}] {x.get('item')}**: {x.get('problem')} → {x.get('suggestion')}")
        for a, b, t in dups:
            md.append(f"- 重複候補: 「{a}」≒「{b}」（{t}）")
        md.append("")
    csv_p = out_root / "posting_sheet.csv"
    with open(csv_p, "w", encoding="utf-8-sig", newline="") as f:  # BOM 付き: Excel で文字化けしない
        w = csv.writer(f)
        w.writerow(["番号", "投稿タイトル", "テーマ", "動画ファイル", "長さ(秒)", "概要欄", "タグ", "判定", "要確認メモ"])
        w.writerows(rows)
    (out_root / "posting_sheet.md").write_text("\n".join(md), encoding="utf-8")
    log(f"投稿管理表: {csv_p}")
    return csv_p


def suggest_titles(genre: str, count: int = 30, form: str = "5選") -> list[str]:
    settings = Settings.from_env()
    llm = get_llm(settings)
    if llm is None:
        raise RuntimeError("タイトル提案には台本AI (claude CLI など) が必要です")
    used = registry.used_titles()
    prompt = f"""YouTubeショート向けの「{form}」形式のタイトルを、ジャンル「{genre}」で{count}個考えてください。
- 思わずタップしたくなる、具体的で意外性のあるタイトル（例: 99%の人が知らない衝撃の雑学5選）
- 確かな事実で中身を作れるテーマにする（都市伝説頼みにしない）
- 次の作成済みテーマと重複・言い換えにならないこと:
{chr(10).join('・' + t for t in used[-200:])}

JSON で出力: {{"titles": ["...", "..."]}}"""
    res = complete_json(llm, "あなたはYouTubeショートの企画担当です。出力はJSONのみ。", prompt)
    titles = [t for t in (res.get("titles", []) if isinstance(res, dict) else []) if isinstance(t, str)]
    out = ROOT / "output" / f"title_ideas_{datetime.now():%Y%m%d_%H%M%S}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(titles) + "\n", encoding="utf-8")
    log(f"タイトル案を保存: {out}")
    return titles
