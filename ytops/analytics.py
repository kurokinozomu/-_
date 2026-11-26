"""投稿後の自動分析と自己改善。

- 公開 1 時間 / 24 時間 / 72 時間 / 7 日 / 30 日後にスナップショットを取る (期限を過ぎた分だけ取得)
- Analytics API のデータは反映に 1〜3 日かかるため、未反映 (0 / 欠損) は「取得待ち」として次回に再取得
- インプレッション数・クリック率は API で安定して取れないため、YouTube Studio の CSV を取り込む (import_studio_csv)
- 結論は「自チャンネルの実績」から、十分な本数 (MIN_N) が揃ったときだけ出す
"""
from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from . import db
from .config import JST, YPP

CHECKPOINTS = [("1h", timedelta(hours=1)), ("24h", timedelta(hours=24)), ("72h", timedelta(hours=72)),
               ("7d", timedelta(days=7)), ("30d", timedelta(days=30))]
MIN_N = 5  # 比較に必要な最低本数


def due_checkpoints(video: dict, taken: set[str], now: datetime | None = None) -> list[str]:
    if not video.get("published_at"):
        return []
    now = now or datetime.now(JST)
    pub = datetime.fromisoformat(video["published_at"])
    return [name for name, dt in CHECKPOINTS if now >= pub + dt and name not in taken]


def collect(yt) -> dict:
    """チャンネル統計と、期限が来た動画のスナップショットを保存する。"""
    ch = yt.channel()
    st = ch["statistics"]
    today = datetime.now(JST).date()
    long_hours, shorts_views = None, None
    try:
        ids = {v["youtube_id"]: v for v in db.videos() if v.get("youtube_id")}
        rep = yt.analytics((today - timedelta(days=365)).isoformat(), today.isoformat(),
                           "views,estimatedMinutesWatched", dimensions="video", sort="-views", max_results=200)
        long_m = sum(r["estimatedMinutesWatched"] for r in rep["rows"]
                     if ids.get(r["video"], {}).get("kind") != "short")
        long_hours = round(long_m / 60, 1)
        rep90 = yt.analytics((today - timedelta(days=90)).isoformat(), today.isoformat(), "views",
                             dimensions="video", sort="-views", max_results=200)
        shorts_views = sum(r["views"] for r in rep90["rows"] if ids.get(r["video"], {}).get("kind") == "short")
    except Exception as e:  # 分析 API が使えなくても統計だけは保存
        db.log_event("warn", "analytics", f"Analytics API 取得失敗: {e}")
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO channel_stats VALUES(?,?,?,?,?,?,?)",
                    (db.now(), int(st.get("subscriberCount", 0)), int(st.get("viewCount", 0)),
                     int(st.get("videoCount", 0)), long_hours, shorts_views, "api(推定値。正式な値は Studio の収益化タブ)"))
    n = 0
    for v in db.videos(["public"]):
        with db.connect() as con:
            taken = {r["checkpoint"] for r in con.execute(
                "SELECT checkpoint FROM metrics WHERE video_id=? AND views IS NOT NULL", (v["id"],))}
        for cp in due_checkpoints(v, taken):
            snapshot(yt, v, cp)
            n += 1
    return {"subscribers": int(st.get("subscriberCount", 0)), "snapshots": n}


def snapshot(yt, v: dict, checkpoint: str) -> None:
    vid = v["youtube_id"]
    stats = (yt.get_videos([vid], "statistics") or [{}])[0].get("statistics", {})
    pub = datetime.fromisoformat(v["published_at"]).date()
    rows = []
    try:
        rep = yt.analytics(pub.isoformat(), datetime.now(JST).date().isoformat(),
                           "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                           "subscribersGained,likes,comments,shares", filters=f"video=={vid}")
        rows = rep["rows"]
    except Exception as e:
        db.log_event("warn", "analytics", f"{vid} の分析データ未取得 (反映待ちの可能性): {e}")
    a = rows[0] if rows else {}
    with db.connect() as con:
        con.execute("""INSERT INTO metrics(video_id,youtube_id,taken_at,checkpoint,views,likes,comments,shares,
            minutes_watched,avg_view_duration,avg_view_pct,subs_gained,source,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (v["id"], vid, db.now(), checkpoint, int(stats.get("viewCount", 0)),
                     int(stats.get("likeCount", 0) or 0), int(stats.get("commentCount", 0) or 0),
                     a.get("shares"), a.get("estimatedMinutesWatched"), a.get("averageViewDuration"),
                     a.get("averageViewPercentage"), a.get("subscribersGained"),
                     "data_api+analytics_api" if a else "data_api(分析は反映待ち)", json.dumps(a)))


def import_studio_csv(path: Path) -> int:
    """YouTube Studio > アナリティクス > 詳細 > エクスポート (表データ.csv) のインプレッション・CTR を取り込む。"""
    n = 0
    by_yt = {v["youtube_id"]: v for v in db.videos() if v.get("youtube_id")}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            vid = row.get("コンテンツ") or row.get("Content") or row.get("動画") or ""
            imp = row.get("インプレッション数") or row.get("Impressions")
            ctr = row.get("インプレッションのクリック率 (%)") or row.get("Impressions click-through rate (%)")
            if vid in by_yt and imp:
                with db.connect() as con:
                    con.execute("""INSERT INTO metrics(video_id,youtube_id,taken_at,checkpoint,impressions,ctr,source)
                                   VALUES(?,?,?,?,?,?,?)""",
                                (by_yt[vid]["id"], vid, db.now(), "studio", int(float(imp)),
                                 float(ctr) if ctr else None, f"studio_csv:{Path(path).name}"))
                n += 1
    return n


def latest_channel() -> dict:
    with db.connect() as con:
        r = con.execute("SELECT * FROM channel_stats ORDER BY taken_at DESC LIMIT 1").fetchone()
        prev = con.execute("SELECT * FROM channel_stats WHERE taken_at < date('now','-20 hours') "
                           "ORDER BY taken_at DESC LIMIT 1").fetchone()
    cur = dict(r) if r else {}
    if cur and prev:
        cur["subs_delta"] = cur["subscribers"] - prev["subscribers"]
        cur["views_delta"] = cur["views"] - prev["views"]
    return cur


def monetization_progress(ch: dict | None = None, today: datetime | None = None) -> dict:
    ch = ch or latest_channel()
    today = today or datetime.now(JST)
    tier = "current" if today.date().isoformat() < YPP["change_date"] else "from_2027_02_01"
    req = YPP[tier]
    subs = ch.get("subscribers") or 0
    hours = ch.get("long_watch_hours_365") or 0
    sv = ch.get("shorts_views_90") or 0
    p_subs = min(1.0, subs / req["subs"])
    p_hours = min(1.0, hours / req["watch_hours"])
    p_shorts = min(1.0, sv / req["shorts_views"])
    return {"tier": tier, "requirements": req, "subs": subs, "watch_hours": hours, "shorts_views": sv,
            "route_a": round(100 * min(p_subs, p_hours), 1), "route_b": round(100 * min(p_subs, p_shorts), 1),
            "overall": round(100 * max(min(p_subs, p_hours), min(p_subs, p_shorts)), 1)}


def video_table() -> list[dict]:
    """動画ごとの最新指標。"""
    out = []
    with db.connect() as con:
        for v in db.videos(["public"]):
            m = con.execute("SELECT * FROM metrics WHERE video_id=? AND views IS NOT NULL ORDER BY taken_at DESC LIMIT 1",
                            (v["id"],)).fetchone()
            s = con.execute("SELECT impressions, ctr FROM metrics WHERE video_id=? AND checkpoint='studio' "
                            "ORDER BY taken_at DESC LIMIT 1", (v["id"],)).fetchone()
            row = {**v, **(dict(m) if m else {})}
            if s:
                row.update(impressions=s["impressions"], ctr=s["ctr"])
            out.append(row)
    return out


def insights() -> dict:
    """事実 (データで確認できたこと) と仮説 (分析上の推測) を分けて返す。"""
    rows = [r for r in video_table() if r.get("views") is not None]
    facts, hyps, proposals = [], [], []
    for kind in ("short", "long", "sleep"):
        grp = [r for r in rows if r.get("kind") == kind]
        if not grp:
            continue
        med = statistics.median(r["views"] for r in grp)
        facts.append(f"{kind}: 公開 {len(grp)} 本、再生数の中央値 {med:.0f}")
        if len(grp) >= MIN_N:
            top = sorted(grp, key=lambda r: r["views"], reverse=True)[:3]
            facts.append(f"{kind} 上位: " + " / ".join(f"{t['title']} ({t['views']})" for t in top))
            series = {}
            for r in grp:
                series.setdefault(r.get("series") or "単発", []).append(r["views"])
            good = [(s, statistics.median(v)) for s, v in series.items() if len(v) >= 3]
            for s, m in good:
                if m > med * 1.5:
                    hyps.append(f"シリーズ「{s}」は {kind} の中央値の {m / max(med, 1):.1f} 倍 (n={len(series[s])})。"
                                "テーマへの需要が強い可能性")
                    proposals.append({"type": "series_boost", "series": s, "kind": kind})
            pcts = [r["avg_view_pct"] for r in grp if r.get("avg_view_pct")]
            if len(pcts) >= MIN_N and kind != "short" and statistics.median(pcts) < 30:
                hyps.append(f"{kind} の平均視聴率の中央値が {statistics.median(pcts):.0f}%。冒頭で離脱している可能性")
                proposals.append({"type": "shorten_intro", "kind": kind})
        else:
            hyps.append(f"{kind} はまだ {len(grp)} 本。{MIN_N} 本揃うまで結論を出さない")
    by_hour = {}
    for r in rows:
        if r.get("published_at") and r.get("kind") == "short":
            by_hour.setdefault(datetime.fromisoformat(r["published_at"]).hour, []).append(r["views"])
    if sum(len(v) for v in by_hour.values()) >= 12 and len(by_hour) >= 2:
        best = max(by_hour.items(), key=lambda kv: statistics.median(kv[1]) if len(kv[1]) >= 3 else -1)
        if len(best[1]) >= 3:
            hyps.append(f"ショートは {best[0]} 時台の公開が最も良い (中央値 {statistics.median(best[1]):.0f}, n={len(best[1])})")
            proposals.append({"type": "publish_hour", "hour": best[0]})
    return {"facts": facts, "hypotheses": hyps, "proposals": proposals}


def apply_proposals(proposals: list[dict], auto: bool = True) -> list[str]:
    """改善提案のうち、取り消し可能で小さな変更だけ自動反映する (1 回に 1 変数まで)。履歴は rules テーブル。"""
    applied = []
    rules = db.active_rules()
    for p in proposals:
        if p["type"] == "publish_hour" and auto:
            hours = list(rules["publish_hours_jst"])
            if p["hour"] not in hours:
                hours = sorted(hours[:-1] + [p["hour"]])
                db.set_rules({**rules, "publish_hours_jst": hours}, f"自動: ショートの好調な時間帯 {p['hour']} 時を枠に追加")
                applied.append(f"投稿時間枠に {p['hour']} 時を追加")
                break  # 一度に複数の変数を変えない
    return applied
