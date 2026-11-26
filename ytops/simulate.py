"""90 日間の収益化シミュレーション (楽観・標準・悲観)。

前提値はすべて仮定 (自チャンネルの実績が出たら config/simulation.json を実績で上書きする)。
2027-02-01 以降の新規申請は条件が 2 倍になる (8,000 時間 / 2,000 万回) ため、日付ごとに判定する。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from .config import PROJECT, YPP

SCENARIOS = {
    # 1 本あたりの数字はすべて「公開から 90 日以内に積み上がる量」の仮定
    "悲観": {"short_views": 200, "short_subs_per_1k": 1.0, "long_views": 60, "long_avd_min": 2.5,
             "sleep_views": 60, "sleep_avd_min": 10, "long_subs_per_1k": 4, "growth": 1.010, "cap": 2.5},
    "標準": {"short_views": 800, "short_subs_per_1k": 1.5, "long_views": 250, "long_avd_min": 3.5,
             "sleep_views": 300, "sleep_avd_min": 18, "long_subs_per_1k": 6, "growth": 1.020, "cap": 4.0},
    "楽観": {"short_views": 5000, "short_subs_per_1k": 2.0, "long_views": 1500, "long_avd_min": 4.5,
             "sleep_views": 2000, "sleep_avd_min": 25, "long_subs_per_1k": 8, "growth": 1.030, "cap": 6.0},
}
CADENCE = {"shorts_per_day": 2, "longs_per_week": 2, "sleep_per_week": 1}


def load_overrides() -> dict:
    p = PROJECT / "config" / "simulation.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def run(start: date, days: int = 90, cadence: dict | None = None, scenarios: dict | None = None) -> dict:
    cadence = cadence or CADENCE
    scenarios = scenarios or {**SCENARIOS, **load_overrides()}
    out = {}
    for name, s in scenarios.items():
        subs = hours = 0.0
        shorts_log = []  # (day, views)
        hit = None
        rows = []
        for d in range(days):
            day = start + timedelta(days=d)
            q = min(s.get("cap", 4.0), s["growth"] ** d)  # チャンネルの成長で 1 本あたりの数字が伸びる仮定 (上限つき)
            sv = cadence["shorts_per_day"] * s["short_views"] * q
            longs = cadence["longs_per_week"] / 7
            sleeps = cadence["sleep_per_week"] / 7
            lv, slv = longs * s["long_views"] * q, sleeps * s["sleep_views"] * q
            hours += (lv * s["long_avd_min"] + slv * s["sleep_avd_min"]) / 60
            subs += sv / 1000 * s["short_subs_per_1k"] + (lv + slv) / 1000 * s["long_subs_per_1k"]
            shorts_log.append(sv)
            sv90 = sum(shorts_log[-90:])
            req = YPP["current"] if day.isoformat() < YPP["change_date"] else YPP["from_2027_02_01"]
            ok_a = subs >= req["subs"] and hours >= req["watch_hours"]
            ok_b = subs >= req["subs"] and sv90 >= req["shorts_views"]
            if hit is None and (ok_a or ok_b):
                hit = (d + 1, day.isoformat(), "A(長尺)" if ok_a else "B(ショート)")
            if (d + 1) % 15 == 0 or d == days - 1:
                rows.append({"day": d + 1, "date": day.isoformat(), "subs": round(subs),
                             "watch_hours": round(hours), "shorts_views_90d": round(sv90)})
        out[name] = {"assumptions": s, "milestones": rows, "eligible": hit}
    return out


def to_markdown(res: dict, start: date) -> str:
    lines = [f"# 収益化シミュレーション (開始日 {start}, {CADENCE})", "",
             "数字はすべて仮定に基づく推計であり、実績ではありません。", ""]
    for name, r in res.items():
        a = r["assumptions"]
        lines += [f"## {name}", "",
                  f"仮定: ショート1本 {a['short_views']}回 / 長尺1本 {a['long_views']}回 (平均視聴 {a['long_avd_min']}分) / "
                  f"睡眠用1本 {a['sleep_views']}回 (平均視聴 {a['sleep_avd_min']}分) / 日次成長 {a['growth']} (上限 {a.get('cap', 4)}倍)", "",
                  "| Day | 日付 | 登録者 | 長尺の総再生時間 | ショート90日再生 |", "|---|---|---|---|---|"]
        lines += [f"| {m['day']} | {m['date']} | {m['subs']} | {m['watch_hours']} h | {m['shorts_views_90d']:,} |"
                  for m in r["milestones"]]
        e = r["eligible"]
        lines += ["", f"**収益化条件の達成: {'Day %d (%s) ルート%s' % e if e else '90日以内は未達'}**", ""]
    return "\n".join(lines)
