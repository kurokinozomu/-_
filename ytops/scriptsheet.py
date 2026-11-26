"""台本シート: 1 本ごとに「読み上げ時間・映像指示・字幕指示・効果音指示・事実確認結果・出典」をまとめる。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import PROJECT

SFX = {"none": "なし", "whoosh": "シュッ (場面転換)", "impact": "ドン (強調)", "pop": "ポン (要点)", "chime": "チャイム (章の始まり)"}


def write(vdir: Path, vid: str | None = None) -> Path:
    vdir = Path(vdir)
    plan = json.loads((vdir / "plan.json").read_text(encoding="utf-8"))
    meta = json.loads((vdir / "metadata.json").read_text(encoding="utf-8")) if (vdir / "metadata.json").exists() else {}
    qa = json.loads((vdir / "qa.json").read_text(encoding="utf-8")) if (vdir / "qa.json").exists() else {}
    times = {}
    mdp = vdir / "metadata.md"
    if mdp.exists():
        for m in re.finditer(r"- `([\d:]+)` (.+)", mdp.read_text(encoding="utf-8")):
            times.setdefault(m.group(2).strip()[:40], m.group(1))
    lines = [f"# 台本: {(meta.get('titles') or [plan.get('theme')])[0]}", "",
             f"- テーマ: {plan.get('theme')}", f"- 目標の長さ: {plan.get('target_seconds')} 秒 / 実際: {meta.get('duration_sec', '未計測')} 秒",
             f"- 映像の方針: {plan.get('visual_style', '')}", f"- BGM: {plan.get('bgm_mood', '')}",
             f"- 品質審査: {qa.get('total', '未実施')} 点 ({qa.get('verdict', '-')})", ""]
    for ci, ch in enumerate(plan.get("chapters", [])):
        lines += [f"## {ci + 1}. {ch.get('title', '')}", "",
                  "| 時刻 | ナレーション (読み上げ目安) | 映像指示 | 字幕指示 | 効果音 |", "|---|---|---|---|---|"]
        for s in ch.get("scenes", []):
            n = s.get("narration", "")
            t = times.get(n[:40], "")
            vis = f"{s.get('camera', '')} / 転換 {s.get('transition', '')} / {s.get('visual_prompt', '')[:120]}"
            sub = f"見出し「{s.get('onscreen_text', '')}」 強調: {'、'.join(s.get('highlight', []))}"
            lines.append(f"| {t} | {n} ({len(n) / 6:.1f}秒) | {vis} | {sub} | {SFX.get(s.get('sfx', 'none'), s.get('sfx'))} |")
        lines.append("")
    if qa:
        lines += ["## 事実確認の結果", ""]
        lines += [f"- 公開禁止: {b}" for b in qa.get("blockers", [])]
        lines += [f"- 要確認: {b}" for b in qa.get("needs_human", [])]
        lines += [f"- [{s}] {m}" for s, m in qa.get("issues", []) if "事実" in m or "台本" in m]
        lines += ["", "## 出典 (検索で実在を確認した URL)", ""]
        lines += [f"- {s['claim']} ({s['status']}): {s['url']}" for s in qa.get("sources", [])] or ["- なし (裏取りできた URL がない場合は公開前に人間が確認)"]
    p = vdir / "script_sheet.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if vid:
        (PROJECT / "scripts").mkdir(exist_ok=True)
        (PROJECT / "scripts" / f"{vid}.md").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return p
