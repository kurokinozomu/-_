"""作った動画とネタの記録 (ネタかぶり防止・投稿管理用)。

data/registry.json に、動画ごとのタイトル・テーマ・使った項目を保存する。
新しい台本を作るときは使用済みの項目を台本 AI に渡し、完成後は重複をチェックする。
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from .config import ROOT

PATH = ROOT / "data" / "registry.json"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s、。・!！?？「」『』()（）\-ー〜~]", "", s)


def load() -> dict:
    if PATH.exists():
        return json.loads(PATH.read_text(encoding="utf-8"))
    return {"videos": []}


def save(reg: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def items_of(plan: dict) -> list[dict]:
    """台本から「ネタ」を取り出す (ランキングは項目、それ以外は見出し)。"""
    out = []
    is_rank = "ranking" in plan or any("rank" in s for ch in plan.get("chapters", []) for s in ch.get("scenes", []))
    for ch in plan.get("chapters", []):
        for s in ch.get("scenes", []):
            name = (s.get("item") if is_rank else s.get("onscreen_text")) or ""
            if is_rank and s.get("rank") in (None, "", 0):
                continue
            if name.strip():
                out.append({"item": name.strip(), "fact": s.get("narration", "")[:80]})
    return out


def register(plan: dict, out_dir: Path, title: str = "") -> None:
    reg = load()
    key = str(out_dir.resolve())
    reg["videos"] = [v for v in reg["videos"] if v.get("dir") != key]
    reg["videos"].append({
        "theme": plan.get("theme", ""),
        "title": title or (plan.get("titles") or [plan.get("theme", "")])[0],
        "dir": key,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "shorts": bool(plan.get("shorts")),
        "items": items_of(plan),
    })
    save(reg)


def used_items(limit: int = 400, exclude_dir: str | None = None) -> list[str]:
    seen, out = set(), []
    for v in reversed(load()["videos"]):
        if exclude_dir and v.get("dir") == exclude_dir:
            continue
        for it in v.get("items", []):
            k = _norm(it["item"])
            if k and k not in seen:
                seen.add(k)
                out.append(it["item"])
    return out[:limit]


def used_titles() -> list[str]:
    return [v.get("theme") or v.get("title", "") for v in load()["videos"]]


def duplicates(plan: dict, exclude_dir: str | None = None) -> list[tuple[str, str, str]]:
    """(この動画の項目, 既存の項目, 既存のテーマ) の重複候補。"""
    mine = items_of(plan)
    found = []
    for v in load()["videos"]:
        if exclude_dir and v.get("dir") == exclude_dir:
            continue
        for old in v.get("items", []):
            a = _norm(old["item"])
            for it in mine:
                b = _norm(it["item"])
                if not a or not b:
                    continue
                if a == b or (min(len(a), len(b)) >= 3 and (a in b or b in a)) \
                        or SequenceMatcher(None, a, b).ratio() >= 0.8:
                    found.append((it["item"], old["item"], v.get("theme", "")))
    return found


def rebuild_from(folder: Path) -> int:
    """既存の出力フォルダ (plan.json) から記録を作り直す。"""
    n = 0
    for p in sorted(folder.rglob("plan.json")):
        try:
            plan = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (p.parent / "video.mp4").exists():
            register(plan, p.parent)
            n += 1
    return n
