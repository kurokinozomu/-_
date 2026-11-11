"""使い方:
    python -m aivideo "宇宙の謎というテーマで8分の動画を作って"
    python -m aivideo --theme "睡眠の科学" --minutes 3
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from .config import Settings, log


MARKER = r"というテーマ|をテーマに|についての|について|のテーマで|テーマで"


def _duration(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*分(?:\s*(\d+)\s*秒)?", text)
    if m:
        return float(m.group(1)) * 60 + (float(m.group(2)) if m.group(2) else 0)
    m = re.search(r"(\d+)\s*秒", text)
    return float(m.group(1)) if m else None


def parse_request(text: str) -> tuple[str, float | None]:
    """「〇〇というテーマで8分の動画を作って」からテーマと秒数を取り出す。

    テーマ部分の数字 (例:「1秒ごとに2倍」) を長さと取り違えないよう、
    「というテーマで」などの区切りがあれば、長さはその後ろからだけ読む。
    """
    parts = re.split(MARKER, text, maxsplit=1)
    if len(parts) == 2:
        theme, rest = parts
        secs = _duration(rest)
    else:
        secs = _duration(text)
        theme = re.sub(r"(で)?\s*\d+(\.\d+)?\s*(分|秒).*$", "", text)
    theme = re.sub(r"^(テーマ[:：は]?)", "", theme).strip(" 「」『』\"'、。")
    return theme or text.strip(), secs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aivideo", description="テーマを入れるだけで YouTube 動画 (MP4) を自動生成")
    ap.add_argument("request", nargs="?", help="例: 「宇宙の謎というテーマで8分の動画を作って」")
    ap.add_argument("--theme", help="テーマ (request の代わりに指定)")
    ap.add_argument("--minutes", type=float, help="動画の長さ (分)")
    ap.add_argument("--seconds", type=float, help="動画の長さ (秒)")
    ap.add_argument("--llm", choices=["auto", "claude-cli", "anthropic", "offline"])
    ap.add_argument("--visuals", choices=["auto", "pollinations", "procedural"])
    ap.add_argument("--tts", choices=["auto", "voicevox", "openjtalk"])
    ap.add_argument("--allow-paid", action="store_true", help="有料 API (Anthropic API) の利用を許可")
    ap.add_argument("--plan", type=Path, help="既存の plan.json から作り直す (台本を手直ししたい場合)")
    ap.add_argument("--out", type=Path, help="出力先ディレクトリ")
    ap.add_argument("--workers", type=int, default=3, help="並列レンダリング数")
    ap.add_argument("--check", action="store_true", help="実行環境をチェックして終了")
    ap.add_argument("--shorts", action="store_true", help="縦型ショート動画 (1080x1920) を作る")
    ap.add_argument("--animate", action="store_true",
                    help="口パクするキャラクターと声のエフェクトでアニメーションにする (無料)")
    ap.add_argument("--related", action="store_true", help="ショートの最後を「詳しくは関連動画で」にする (長尺がある場合)")
    a = ap.parse_args(argv)
    if a.check:
        from .doctor import check
        return check()

    theme, secs = (parse_request(a.request) if a.request else (None, None))
    theme = a.theme or theme
    shorts = a.shorts or bool(a.request and re.search(r"ショート|shorts|縦型", a.request, re.I))
    if theme:
        theme = re.sub(r"(の)?(ショート動画|ショート|縦型動画)$", "", theme).strip(" 「」") or theme
    if a.minutes:
        secs = a.minutes * 60
    if a.seconds:
        secs = a.seconds
    if not theme and not a.plan:
        ap.print_help()
        return 2
    if a.plan and not secs:
        import json
        secs = float(json.loads(a.plan.read_text(encoding="utf-8")).get("target_seconds") or 60)
    secs = secs or (50.0 if shorts else 60.0)
    if shorts and secs > 180:
        log("ショート動画は 3 分以内です。50秒で作ります。")
        secs = 50.0
    if secs < 15 or secs > 3600:
        log("動画の長さは 15秒〜60分 の範囲で指定してください。")
        return 2

    settings = Settings.from_env()
    if a.llm:
        settings.llm = a.llm
    if a.visuals:
        settings.visuals = a.visuals
    if a.tts:
        settings.tts = a.tts
    if a.related or (a.request and re.search(r"関連動画|長尺", a.request)):
        os.environ["AIVIDEO_SHORTS_RELATED"] = "1"
    if a.allow_paid:
        settings.allow_paid = True

    if a.plan and not theme:
        import json
        theme = json.loads(a.plan.read_text(encoding="utf-8")).get("theme", "video")
    log(f"テーマ: {theme} / 目標の長さ: {secs:.0f}秒")
    from .pipeline import make_video
    make_video(theme, secs, settings, out_root=a.out, plan_path=a.plan, workers=a.workers, shorts=shorts,
               animate=a.animate or bool(a.request and re.search(r"アニメ", a.request))
               or os.environ.get("AIVIDEO_ANIMATE", "") in ("1", "true", "yes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
