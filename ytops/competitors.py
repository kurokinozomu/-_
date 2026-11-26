"""競合チャンネルの公開データを YouTube Data API で取得する (スクレイピングはしない)。

必要: YT_API_KEY (Google Cloud の API キー。無料・課金設定不要。OWNER_TASKS.md 手順 3)
入力: youtube_automation/research/competitors.json の "channels" (handle または channel_id)
出力: research/competitors_metrics.json / .md
API で取れない項目 (開設日以外の登録者推移・視聴維持率・収益など) は「取得不能」と明記する。
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import PROJECT, env

API = "https://www.googleapis.com/youtube/v3"


def _get(path: str, **params) -> dict:
    key = env("YT_API_KEY")
    if not key:
        raise RuntimeError("YT_API_KEY が未設定です")
    r = requests.get(f"{API}/{path}", params={**params, "key": key}, timeout=30)
    r.raise_for_status()
    return r.json()


def _iso_dur(s: str) -> int:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    d, h, mi, se = (int(x or 0) for x in m.groups()) if m else (0, 0, 0, 0)
    return d * 86400 + h * 3600 + mi * 60 + se


def channel(ref: str) -> dict:
    q = {"forHandle": ref} if ref.startswith("@") else {"id": ref}
    items = _get("channels", part="snippet,statistics,contentDetails", **q).get("items", [])
    if not items:
        return {"ref": ref, "error": "見つかりません"}
    c = items[0]
    uploads = c["contentDetails"]["relatedPlaylists"]["uploads"]
    vids = _get("playlistItems", part="contentDetails", playlistId=uploads, maxResults=50).get("items", [])
    ids = [v["contentDetails"]["videoId"] for v in vids]
    details = _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids)).get("items", []) if ids else []
    rows = [{"title": d["snippet"]["title"], "published": d["snippet"]["publishedAt"],
             "views": int(d["statistics"].get("viewCount", 0)), "sec": _iso_dur(d["contentDetails"]["duration"])}
            for d in details]
    now = datetime.now(timezone.utc)
    recent = [r for r in rows if (now - datetime.fromisoformat(r["published"].replace("Z", "+00:00"))).days <= 90]
    st = c["statistics"]
    return {
        "ref": ref, "id": c["id"], "title": c["snippet"]["title"], "url": f"https://www.youtube.com/channel/{c['id']}",
        "created": c["snippet"]["publishedAt"][:10],
        "subscribers": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
        "total_views": int(st.get("viewCount", 0)), "videos": int(st.get("videoCount", 0)),
        "uploads_last_90d": len(recent),
        "median_views_recent50": statistics.median([r["views"] for r in rows]) if rows else None,
        "median_length_min": round(statistics.median([r["sec"] for r in rows]) / 60, 1) if rows else None,
        "shorts_ratio_recent50": round(sum(r["sec"] <= 180 for r in rows) / len(rows), 2) if rows else None,
        "top_recent": sorted(rows, key=lambda r: r["views"], reverse=True)[:3],
        "views_per_sub_recent": None,
        "not_available": "登録者推移・視聴維持率・収益・インプレッションは非公開のため取得不能",
        "fetched_at": now.isoformat(timespec="seconds"),
    }


def run() -> Path:
    src = json.loads((PROJECT / "research" / "competitors.json").read_text(encoding="utf-8"))
    out = []
    for c in src["channels"]:
        ref = c.get("handle") or c.get("channel_id")
        if not ref:
            out.append({**c, "error": "handle / channel_id 未特定"})
            continue
        try:
            out.append({**c, **channel(ref)})
        except Exception as e:
            out.append({**c, "error": str(e)[:200]})
    p = PROJECT / "research" / "competitors_metrics.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["| チャンネル | 開設 | 登録者 | 総再生 | 本数 | 直近90日投稿 | 直近50本の再生中央値 | 長さ中央値(分) | ショート比率 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in out:
        if r.get("error"):
            lines.append(f"| {r.get('name', r.get('ref'))} | 取得不能: {r['error']} |||||||| ")
        else:
            lines.append(f"| [{r['title']}]({r['url']}) | {r['created']} | {r['subscribers'] if r['subscribers'] is not None else '非公開'} | "
                         f"{r['total_views']:,} | {r['videos']} | {r['uploads_last_90d']} | {r['median_views_recent50']} | "
                         f"{r['median_length_min']} | {r['shorts_ratio_recent50']} |")
    (PROJECT / "research" / "competitors_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
