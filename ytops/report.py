"""日報・週次経営会議レポート。取得できなかった値は「未取得」と書き、推測値で埋めない。"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import analytics, db, ideas
from .config import JST, Channel, state_dir


def project_day(today: date | None = None) -> int:
    start = Channel.load().get("start_date") or "2026-11-26"
    today = today or datetime.now(JST).date()
    return (today - date.fromisoformat(start)).days + 1


def _fmt(v, unit=""):
    return "未取得" if v is None else f"{v:,}{unit}" if isinstance(v, int) else f"{v}{unit}"


def owner_tasks() -> list[str]:
    tasks = []
    from .youtube import is_configured
    if not is_configured():
        tasks.append("YouTube API の認証 (OWNER_TASKS.md 手順 3〜4)")
    review = db.videos("needs_review")
    if review:
        tasks.append(f"人間の確認が必要な動画 {len(review)} 本 (`python -m ytops list needs_review`)")
    waiting = db.videos(["uploaded_private", "qa_passed"])
    if waiting:
        tasks.append(f"公開承認待ち {len(waiting)} 本 (ダッシュボードまたは `python -m ytops approve <ID>`)")
    with db.connect() as con:
        crit = con.execute("SELECT message FROM events WHERE level='critical' AND ts > ? ORDER BY ts DESC LIMIT 3",
                           ((datetime.now(JST) - timedelta(days=1)).isoformat(),)).fetchall()
    tasks += [f"重大: {r['message']}" for r in crit]
    return tasks


def write_daily(today: date | None = None) -> Path:
    today = today or datetime.now(JST).date()
    ch = analytics.latest_channel()
    prog = analytics.monetization_progress(ch)
    rows = analytics.video_table()
    with_views = [r for r in rows if r.get("views") is not None]
    best = max(with_views, key=lambda r: r["views"], default=None)
    worst = min(with_views, key=lambda r: r["views"], default=None)
    ins = analytics.insights()
    day = today.isoformat()
    published_today = [v for v in db.videos("public") if (v.get("published_at") or "").startswith(day)]
    made_today = [v for v in db.videos() if (v.get("created_at") or "").startswith(day)]
    tomorrow = (today + timedelta(days=1)).isoformat()
    sched = [v for v in db.videos("scheduled") if (v.get("publish_at") or "").startswith(tomorrow)]
    with db.connect() as con:
        recent_rules = [dict(r) for r in con.execute(
            "SELECT version, created_at, reason FROM rules WHERE created_at >= ? ORDER BY version DESC",
            (day,))]
    tasks = owner_tasks()
    with db.connect() as con:
        errors = con.execute("SELECT COUNT(*) FROM events WHERE level IN ('error','critical') AND ts >= ?",
                             (day,)).fetchone()[0]
    overall = "要対応" if errors else ("順調" if ch else "準備中 (API 未接続)")
    lines = [
        "【YouTube運営日報】", "",
        f"運営日数：Day {project_day(today)} / 90",
        f"総合評価：{overall}",
        f"現在の登録者数：{_fmt(ch.get('subscribers'))}",
        f"登録者増加数：{_fmt(ch.get('subs_delta'))}",
        f"本日の再生数：{_fmt(ch.get('views_delta'))} (チャンネル総再生の前日差)",
        f"有効視聴時間：{_fmt(ch.get('long_watch_hours_365'), ' 時間')} (API 推定。正式値は Studio の収益化タブ)",
        f"有効ショート視聴回数：{_fmt(ch.get('shorts_views_90'))} (直近90日・API 推定)",
        f"収益化達成率：{prog['overall']}% (ルートA {prog['route_a']}% / ルートB {prog['route_b']}%・基準 {prog['tier']})",
        f"本日の投稿本数：{len(published_today)}",
        f"本日の制作本数：{len(made_today)}",
        f"最も成績が良かった動画：{best['title'] + ' (' + str(best['views']) + '回)' if best else '該当なし'}",
        f"成績が悪かった動画：{worst['title'] + ' (' + str(worst['views']) + '回)' if worst and worst is not best else '該当なし'}",
        "確認できた成功要因：" + (" / ".join(ins["facts"]) or "データ不足"),
        "現在の課題：" + (" / ".join(ins["hypotheses"]) or "データ不足 (仮説なし)"),
        "実施した改善：" + (" / ".join(r["reason"] for r in recent_rules) or "なし"),
        "明日の投稿予定：" + (" / ".join(f"{v['publish_at'][11:16]} {v['title']}" for v in sched) or "なし"),
        "明日の自動実行タスク：データ取得・分析 → 企画補充 → 制作 → 品質審査 → 非公開アップロード → 承認済みの予約 → 日報",
        f"収益化到達予測：{forecast_text(ch)}",
        "現在までの運営費：0円 (有料サービスの利用なし)",
        "オーナーに必要な作業：" + (" / ".join(tasks) if tasks else "確認事項なし"),
        "", f"企画ストック：{ideas.stock()}",
    ]
    out = state_dir() / "reports"
    out.mkdir(exist_ok=True)
    p = out / f"daily_{day}.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def forecast_text(ch: dict) -> str:
    with db.connect() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM channel_stats ORDER BY taken_at DESC LIMIT 14")]
    if len(rows) < 7:
        return "実績 7 日分が揃うまで予測しない (シミュレーションは strategy/monetization_simulation.md)"
    new, old = rows[0], rows[-1]
    days = max(1, (datetime.fromisoformat(new["taken_at"]) - datetime.fromisoformat(old["taken_at"])).days)
    sub_rate = (new["subscribers"] - old["subscribers"]) / days
    hr_rate = ((new["long_watch_hours_365"] or 0) - (old["long_watch_hours_365"] or 0)) / days
    prog = analytics.monetization_progress(new)
    need_s = max(0, prog["requirements"]["subs"] - new["subscribers"])
    need_h = max(0, prog["requirements"]["watch_hours"] - (new["long_watch_hours_365"] or 0))
    ds = need_s / sub_rate if sub_rate > 0 else float("inf")
    dh = need_h / hr_rate if hr_rate > 0 else float("inf")
    d = max(ds, dh)
    return "現在のペースでは到達見込みなし" if d == float("inf") else f"現在のペースで約 {d:.0f} 日後 (登録者 {sub_rate:.1f}/日, 視聴時間 {hr_rate:.1f}h/日)"


WEEKLY_PROMPT = """あなたは YouTube 事業の統括責任者です。以下の 1 週間のデータから週次経営会議の議事録を作成してください。
決定事項ごとに根拠 (データ) を書き、データで確認できる事実と仮説を分けること。
再生数が伸びないという理由だけで短期間にジャンルを変えないこと。変数は一度に 1 つだけ変えること。

決めること: 戦略の継続/変更・投稿頻度・動画の長さ・テーマ・成功シリーズの増減・長尺とショートの比率・
制作システムの改善・90 日以内の達成見込み・予算を変更する価値・次の 7 日間の具体的なタスク

最後に、改善ルールの変更案を JSON で 1 つだけ (変更しない場合は null) 出力:
```json
{{"change": {{"key": "shorts_per_day など", "value": 新しい値}}, "reason": "理由"}}
```

データ:
{data}
"""


def write_weekly(use_llm: bool = True) -> Path:
    data = {"channel_history": [], "videos": analytics.video_table()[-60:], "insights": analytics.insights(),
            "rules": db.active_rules(), "progress": analytics.monetization_progress(), "day": project_day()}
    with db.connect() as con:
        data["channel_history"] = [dict(r) for r in con.execute(
            "SELECT * FROM channel_stats ORDER BY taken_at DESC LIMIT 14")]
    body = "LLM 未使用のため、データのみ掲載します。\n\n```json\n" + json.dumps(data, ensure_ascii=False, indent=1, default=str)[:20000] + "\n```"
    if use_llm:
        import shutil
        import subprocess
        import tempfile
        if shutil.which("claude"):
            with tempfile.TemporaryDirectory() as tmp:
                p = subprocess.run(["claude", "-p", "--output-format", "text"], cwd=tmp, capture_output=True,
                                   text=True, timeout=1200,
                                   input=WEEKLY_PROMPT.format(data=json.dumps(data, ensure_ascii=False, default=str)[:60000]))
            if p.returncode == 0 and p.stdout.strip():
                body = p.stdout
    out = state_dir() / "reports"
    out.mkdir(exist_ok=True)
    p = out / f"weekly_{datetime.now(JST):%Y-%m-%d}.md"
    p.write_text(f"# 週次経営会議 (Day {project_day()})\n\n{body}\n", encoding="utf-8")
    return p
