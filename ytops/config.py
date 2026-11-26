"""運営設定。秘密情報は環境変数 / .env / 権限 600 のトークンファイルからのみ読む。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "youtube_automation"
JST = timezone(timedelta(hours=9))


def _load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def state_dir() -> Path:
    """運営データ (DB・ログ・レポート) の置き場所。リポジトリが公開のうちは git 管理外。"""
    d = Path(env("YTOPS_STATE_DIR") or (ROOT / "state"))
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Channel:
    """config/channel.json の内容 (チャンネルの方針。秘密情報は入れない)。"""
    data: dict

    @classmethod
    def load(cls) -> "Channel":
        p = PROJECT / "config" / "channel.json"
        return cls(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})

    def get(self, key: str, default=None):
        cur = self.data
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


# YPP の条件 (2026-11-26 に youtube.com/creators で確認。2027-02-01 から新規申請は 2 倍の報道あり)
YPP = {
    "current": {"subs": 1000, "watch_hours": 4000, "shorts_views": 10_000_000},
    "from_2027_02_01": {"subs": 1000, "watch_hours": 8000, "shorts_views": 20_000_000},
    "fan_funding": {"subs": 500, "watch_hours": 3000, "shorts_views": 3_000_000, "uploads_90d": 3},
    "change_date": "2027-02-01",
}
