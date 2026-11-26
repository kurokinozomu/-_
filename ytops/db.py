"""運営データベース (SQLite)。動画・企画・指標・改善ルール (履歴つき)・イベントログ・API 利用枠。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import JST, state_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  id TEXT PRIMARY KEY, kind TEXT, theme TEXT, title TEXT, dir TEXT, file_sha TEXT,
  status TEXT, qa_score REAL, qa_json TEXT, youtube_id TEXT, publish_at TEXT,
  idea_id INTEGER, series TEXT, attempts INTEGER DEFAULT 0, notes TEXT,
  created_at TEXT, updated_at TEXT, published_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS videos_sha ON videos(file_sha) WHERE file_sha IS NOT NULL;
CREATE TABLE IF NOT EXISTS ideas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, theme TEXT UNIQUE, kind TEXT, series TEXT, hook TEXT,
  angle TEXT, sources TEXT, score REAL, score_json TEXT, status TEXT DEFAULT 'new', created_at TEXT);
CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT, youtube_id TEXT, taken_at TEXT,
  checkpoint TEXT, views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER,
  minutes_watched REAL, avg_view_duration REAL, avg_view_pct REAL, subs_gained INTEGER,
  impressions INTEGER, ctr REAL, source TEXT, raw_json TEXT);
CREATE TABLE IF NOT EXISTS channel_stats (
  taken_at TEXT PRIMARY KEY, subscribers INTEGER, views INTEGER, videos INTEGER,
  long_watch_hours_365 REAL, shorts_views_90 INTEGER, source TEXT);
CREATE TABLE IF NOT EXISTS rules (
  version INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, body TEXT, reason TEXT, active INTEGER);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, component TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, units INTEGER);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""

STATUSES = ["planned", "produced", "qa_failed", "needs_review", "qa_passed", "uploaded_private",
            "approved", "scheduled", "public", "held", "rejected", "error"]

DEFAULT_RULES = {
    "shorts_per_day": 2,
    "longs_per_week": 2,
    "sleep_per_week": 1,
    "publish_hours_jst": [7, 12, 18, 21],
    "short_seconds": 45,
    "long_minutes": 9,
    "sleep_minutes": 40,
    "qa_min_score": 85,
    "auto_publish": False,
    "max_uploads_per_day": 4,
    "notes": "初期値。7日分のデータが揃うまでは変更しない。",
}


def now() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def path() -> Path:
    return state_dir() / "ytops.sqlite3"


@contextmanager
def connect(p: Path | None = None):
    con = sqlite3.connect(p or path(), timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def log_event(level: str, component: str, message: str) -> None:
    with connect() as con:
        con.execute("INSERT INTO events(ts,level,component,message) VALUES(?,?,?,?)",
                    (now(), level, component, message[:2000]))
    print(f"[ytops:{component}] {level.upper()} {message}", flush=True)


def get_kv(key: str, default=None):
    with connect() as con:
        r = con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_kv(key: str, value) -> None:
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO kv(key,value) VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))


# ---- 改善ルール (履歴・ロールバックつき) ----
def active_rules() -> dict:
    with connect() as con:
        r = con.execute("SELECT body FROM rules WHERE active=1 ORDER BY version DESC LIMIT 1").fetchone()
    if not r:
        set_rules(DEFAULT_RULES, "初期ルール")
        return dict(DEFAULT_RULES)
    return {**DEFAULT_RULES, **json.loads(r["body"])}


def set_rules(body: dict, reason: str) -> int:
    with connect() as con:
        con.execute("UPDATE rules SET active=0")
        cur = con.execute("INSERT INTO rules(created_at,body,reason,active) VALUES(?,?,?,1)",
                          (now(), json.dumps(body, ensure_ascii=False), reason))
        return cur.lastrowid


def rollback_rules(version: int) -> None:
    with connect() as con:
        r = con.execute("SELECT body FROM rules WHERE version=?", (version,)).fetchone()
    if not r:
        raise ValueError(f"ルール version {version} はありません")
    set_rules(json.loads(r["body"]), f"version {version} にロールバック")


def rules_history(limit: int = 20) -> list[dict]:
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT version,created_at,reason,active,body FROM rules ORDER BY version DESC LIMIT ?", (limit,))]


# ---- 動画 ----
def upsert_video(**f) -> None:
    f.setdefault("updated_at", now())
    with connect() as con:
        exists = con.execute("SELECT 1 FROM videos WHERE id=?", (f["id"],)).fetchone()
        if exists:
            keys = [k for k in f if k != "id"]
            con.execute(f"UPDATE videos SET {','.join(k + '=?' for k in keys)} WHERE id=?",
                        [f[k] for k in keys] + [f["id"]])
        else:
            f.setdefault("created_at", now())
            con.execute(f"INSERT INTO videos({','.join(f)}) VALUES({','.join('?' * len(f))})", list(f.values()))


def videos(status: str | list | None = None) -> list[dict]:
    q, args = "SELECT * FROM videos", []
    if status:
        sts = [status] if isinstance(status, str) else status
        q += f" WHERE status IN ({','.join('?' * len(sts))})"
        args = sts
    with connect() as con:
        return [dict(r) for r in con.execute(q + " ORDER BY created_at", args)]


def video(vid: str) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    return dict(r) if r else None


# ---- API 利用枠 ----
def quota_used(day: str) -> int:
    with connect() as con:
        r = con.execute("SELECT units FROM quota WHERE day=?", (day,)).fetchone()
    return r["units"] if r else 0


def add_quota(day: str, units: int) -> None:
    with connect() as con:
        con.execute("INSERT INTO quota(day,units) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET units=units+?",
                    (day, units, units))
