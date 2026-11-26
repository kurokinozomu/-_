"""ytops (運営レイヤー) のテスト。ネットワーク・LLM・YouTube API は使わない。"""
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

os.environ["YTOPS_STATE_DIR"] = tempfile.mkdtemp(prefix="ytops_test_")

from ytops import analytics, db, ideas, ops, qa, simulate, thumbs  # noqa: E402
from ytops.config import JST  # noqa: E402
from ytops.youtube import next_slots  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setenv("YTOPS_STATE_DIR", str(tmp_path))
    yield


def test_rules_history_and_rollback():
    r = db.active_rules()
    assert r["shorts_per_day"] == 2
    v2 = db.set_rules({**r, "shorts_per_day": 3}, "test")
    assert db.active_rules()["shorts_per_day"] == 3
    db.rollback_rules(v2 - 1)
    assert db.active_rules()["shorts_per_day"] == 2
    assert len(db.rules_history()) == 3


def test_next_slots_skip_taken():
    start = datetime(2026, 12, 1, 8, 30, tzinfo=JST)
    s = next_slots(3, [7, 12, 18], ["2026-12-01T12:00:00+09:00"], start)
    assert s == ["2026-12-01T18:00:00+09:00", "2026-12-02T07:00:00+09:00", "2026-12-02T12:00:00+09:00"]


def test_similarity_detects_duplicates():
    a = "江戸の銭湯では、湯船の手前に柘榴口という低い入口がありました。湯気を逃がさない工夫です。"
    assert qa.similarity(a, a) > 0.95
    assert qa.similarity(a, "宇宙の果てには何があるのでしょうか。光の速さで進んでも届きません。") < 0.1


def test_ypp_threshold_switches_on_2027_02_01():
    ch = {"subscribers": 1000, "long_watch_hours_365": 5000, "shorts_views_90": 0}
    before = analytics.monetization_progress(ch, datetime(2027, 1, 31, tzinfo=JST))
    after = analytics.monetization_progress(ch, datetime(2027, 2, 1, tzinfo=JST))
    assert before["route_a"] == 100 and before["tier"] == "current"
    assert after["route_a"] == 62.5 and after["requirements"]["watch_hours"] == 8000


def test_simulation_is_monotonic_and_scenarios_ordered():
    res = simulate.run(date(2026, 11, 26))
    last = {k: v["milestones"][-1] for k, v in res.items()}
    assert last["悲観"]["subs"] < last["標準"]["subs"] < last["楽観"]["subs"]
    hrs = [m["watch_hours"] for m in res["標準"]["milestones"]]
    assert hrs == sorted(hrs)


def test_due_checkpoints():
    pub = datetime(2026, 12, 1, 12, tzinfo=JST)
    v = {"published_at": pub.isoformat()}
    assert analytics.due_checkpoints(v, set(), pub + timedelta(hours=2)) == ["1h"]
    assert analytics.due_checkpoints(v, {"1h"}, pub + timedelta(days=8)) == ["24h", "72h", "7d"]


def test_idea_score_and_dedupe(monkeypatch):
    monkeypatch.setattr(ideas, "existing_themes", lambda limit=300: ["江戸の銭湯はどんな場所だった？"])
    items = [
        {"theme": "江戸の銭湯はどんな場所だった？", "kind": "long", "scores": {k: v for k, v in ideas.WEIGHTS.items()}},
        {"theme": "江戸の長屋の家賃はいくら？", "kind": "short", "scores": {k: v for k, v in ideas.WEIGHTS.items()}},
        {"theme": "明治の駅弁のはじまり", "kind": "short", "scores": {"interest": 5}},
    ]
    added, rejected = ideas.store(items)
    assert (added, rejected) == (1, 2)
    assert ideas.pick("short")["theme"] == "江戸の長屋の家賃はいくら？"
    assert ideas.total_score({k: 999 for k in ideas.WEIGHTS}) == 100


def test_metadata_blocks_sub4sub(tmp_path):
    (tmp_path / "metadata.json").write_text(json.dumps({
        "titles": ["相互フォロー募集中 フォロバ100%"] * 5, "description": "■ 使用素材\n・x", "tags": []},
        ensure_ascii=False), encoding="utf-8")
    r = qa.QAResult()
    qa.check_metadata(tmp_path, "short", r)
    assert r.blockers and r.verdict() == "blocked"


def test_lock_prevents_double_run():
    with ops.lock("t"):
        with pytest.raises(RuntimeError):
            with ops.lock("t"):
                pass


def test_pause_resume():
    ops.pause("test")
    assert ops.is_paused()
    ops.resume()
    assert not ops.is_paused()


def test_plan_today_respects_backlog():
    rules = db.active_rules()
    sat = datetime(2026, 11, 28, tzinfo=JST)  # 土曜
    assert ops.plan_today(rules, sat) == ["short", "short", "sleep"]
    for i in range(10):
        db.upsert_video(id=f"v{i}", kind="short", status="scheduled")
    assert ops.plan_today(rules, sat) == []


def test_contrast_ratio():
    assert thumbs.contrast((255, 255, 255), (0, 0, 0)) == pytest.approx(21, 0.01)
    assert thumbs.contrast((244, 239, 228), (31, 58, 95)) > 7


def test_dashboard_builds_without_data():
    html = __import__("ytops.dashboard", fromlist=["build"]).build("tok")
    assert "収益化までの進捗" in html and "tok" in html
