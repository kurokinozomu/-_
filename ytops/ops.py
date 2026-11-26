"""毎日の自動運営 (スケジューラから 1 日 1〜数回呼ばれる)。

工程: 事前チェック → データ取得・分析 → 企画補充 → 制作 → 品質審査 → 非公開アップロード
      → 承認済みの予約投稿 → 公開状況の同期 → 日報 → ダッシュボード

安全装置:
  - 緊急停止: `ytops stop` (state/STOP ファイル)。停止中は制作・投稿を一切しない (分析と日報のみ)
  - 重複実行防止: state/daily.lock (6 時間で失効)
  - 途中再開: 動画ごとの状態 (status) を DB に保存し、次回は続きから
  - 再試行の上限: 1 本あたり制作 2 回まで。認証エラー・利用枠超過は即中止してオーナーに報告
  - ディスク残量 5GB 未満なら制作しない
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from . import db, ideas, qa
from .config import JST, ROOT, state_dir
from .youtube import AuthError, QuotaError, YouTube, is_configured, next_slots, sha256

MIN_FREE_GB = 5
MAX_ATTEMPTS = 2

# チャンネル共通の画風と時代考証 (映像審査で「現代風の服・照明」「中国風の屋根」「写実的な人物」を指摘されたため)
STYLE_ENV = {
    "AIVIDEO_STYLE": "calm",
    # 画像 AI は否定形 (no 〜) を無視しやすく、物の名前を書くと逆に描かれることがあるため、肯定形で指定する
    "AIVIDEO_PROMPT_SUFFIX": ("ukiyo-e inspired Japanese woodblock print style, flat muted colors, visible paper grain, "
                              "early 19th century Edo period Japan, wooden machiya townhouses with tiled roofs, "
                              "people in kimono with traditional topknot hairstyles drawn small in the distance, "
                              "lit only by paper andon lanterns and candlelight"),
}

KIND_ENV = {
    "short": {"AIVIDEO_TONE": "落ち着いた知的な語り口。最初の一文で意外な事実を示し、煽らずに理由を一つだけ説明する",
              "AIVIDEO_VOICE": "normal", "AIVIDEO_AI_EVERY": "1", "AIVIDEO_REUSE_AI": "1"},
    "long": {"AIVIDEO_TONE": "落ち着いた知的な教養番組の語り口。やさしく、誇張や煽りはせず、史料で確かめられることと諸説あることを区別して話す",
             "AIVIDEO_VOICE": "normal", "AIVIDEO_AI_EVERY": "2", "AIVIDEO_REUSE_AI": "1"},
    "sleep": {"AIVIDEO_TONE": "睡眠前に聞く、静かでゆっくりした朗読の語り口。驚かせる表現・大きな展開・問いかけの連発を避け、情景を穏やかに描写する",
              "AIVIDEO_VOICE": "bashful", "AIVIDEO_TTS_SPEED": "0.95", "AIVIDEO_AI_EVERY": "3",
              "AIVIDEO_REUSE_AI": "1"},
}


def stop_file() -> Path:
    return state_dir() / "STOP"


def is_paused() -> bool:
    return stop_file().exists()


def pause(reason: str) -> None:
    stop_file().write_text(f"{db.now()} {reason}\n", encoding="utf-8")
    db.log_event("critical", "ops", f"自動運転を停止: {reason}")


def resume() -> None:
    if stop_file().exists():
        stop_file().unlink()
    db.log_event("info", "ops", "自動運転を再開")


@contextmanager
def lock(name: str = "daily"):
    p = state_dir() / f"{name}.lock"
    if p.exists():
        age = time.time() - p.stat().st_mtime
        if age < 6 * 3600:
            raise RuntimeError(f"別の処理が実行中です ({p}、{age / 60:.0f} 分前に開始)")
        db.log_event("warn", "ops", "古いロックファイルを削除 (前回の処理が異常終了した可能性)")
    p.write_text(str(os.getpid()))
    try:
        yield
    finally:
        p.unlink(missing_ok=True)


def free_gb(path: Path = ROOT) -> float:
    return shutil.disk_usage(path).free / 1e9


# ---------------- 制作 ----------------
def produce(idea: dict, rules: dict) -> str:
    kind = idea["kind"]
    vid = f"{datetime.now(JST):%Y%m%d%H%M}-{kind}-{idea['id']}"
    out_root = state_dir() / "videos" / vid
    secs = {"short": rules["short_seconds"], "long": rules["long_minutes"] * 60,
            "sleep": rules["sleep_minutes"] * 60}[kind]
    db.upsert_video(id=vid, kind=kind, theme=idea["theme"], status="planned", idea_id=idea["id"],
                    series=idea.get("series"), dir=str(out_root))
    ideas.mark(idea["id"], "used")
    return _render(vid, idea["theme"], kind, secs, out_root)


def _render(vid: str, theme: str, kind: str, secs: float, out_root: Path, plan: Path | None = None) -> str:
    env = {**os.environ, **STYLE_ENV, **KIND_ENV[kind]}
    cmd = [sys.executable, "-m", "aivideo", "--theme", theme, "--seconds", str(int(secs)), "--out", str(out_root)]
    if kind == "short":
        cmd += ["--shorts", "--related"]
    if plan:
        cmd += ["--plan", str(plan)]
    v = db.video(vid) or {}
    db.upsert_video(id=vid, attempts=(v.get("attempts") or 0) + 1)
    log = state_dir() / "logs"
    log.mkdir(exist_ok=True)
    with open(log / f"{vid}.log", "a", encoding="utf-8") as lf:
        p = subprocess.run(cmd, cwd=ROOT, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=4 * 3600)
    dirs = sorted(d for d in out_root.glob("*") if (d / "video.mp4").exists())
    if p.returncode != 0 or not dirs:
        db.upsert_video(id=vid, status="error", notes=f"制作失敗 (exit {p.returncode})。ログ: {log / (vid + '.log')}")
        raise RuntimeError(f"{vid} の制作に失敗")
    d = dirs[-1]
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    db.upsert_video(id=vid, dir=str(d), title=(meta.get("titles") or [theme])[0], status="produced")
    return vid


def regenerate(old_id: str, rules: dict) -> str:
    old = db.video(old_id)
    plan = Path(old["dir"]) / "plan.json"
    vid = f"{datetime.now(JST):%Y%m%d%H%M}-{old['kind']}-re"
    out_root = state_dir() / "videos" / vid
    secs = json.loads(plan.read_text(encoding="utf-8")).get("target_seconds") or 60
    db.upsert_video(id=vid, kind=old["kind"], theme=old["theme"], status="planned", idea_id=old.get("idea_id"),
                    series=old.get("series"), dir=str(out_root), notes=f"{old_id} の作り直し")
    _render(vid, old["theme"], old["kind"], secs, out_root, plan=plan if plan.exists() else None)
    review(vid, rules)
    return vid


REVISE_PROMPT = """以下は YouTube 動画の台本データ (JSON) と、品質審査の指摘事項です。
指摘を反映して台本を修正し、同じ構造の JSON だけを出力してください。
- 事実誤り・未確認の主張は、削除するか「〜と言われています」など確かさに合った表現に直す (新しい事実を足すときは確実なものだけ)
- 構成 (chapters / scenes の数) と camera・transition はできるだけ維持する
- 映像の指摘があったシーン (およびナレーションと絵が合っていないシーン) は visual_prompt を書き直す:
  その時代の建物・衣服・道具を具体的に英語で書き、人物は遠景で小さく、現代の物・写実的な人物は描かない
- タイトル案 (titles) は 5 個以上、ハッシュタグは 3 個まで
- 文字数は元とほぼ同じ (尺を変えない)

指摘事項:
{issues}

台本 JSON:
{plan}
"""


def revise(vid: str, rules: dict, force: bool = False) -> str | None:
    """品質審査で基準未達 (fix) の動画を、指摘を反映した台本で 1 回だけ作り直して再審査する。"""
    import tempfile
    from aivideo.llm import extract_json
    v = db.video(vid)
    q = json.loads(v.get("qa_json") or "{}")
    if (q.get("verdict") != "fix" and not force) or not shutil.which("claude"):
        return None
    d = Path(v["dir"])
    plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
    issues = "\n".join([f"- [{s}] {m}" for s, m in q.get("issues", [])] + [f"- [要確認] {m}" for m in q.get("needs_human", [])]) or "- 合計点が基準未達"
    with tempfile.TemporaryDirectory() as tmp:
        p = subprocess.run(["claude", "-p", "--output-format", "text"], cwd=tmp, capture_output=True, text=True,
                           timeout=1800, input=REVISE_PROMPT.format(issues=issues, plan=json.dumps(plan, ensure_ascii=False)))
    new_plan = extract_json(p.stdout)
    if not isinstance(new_plan, dict) or not new_plan.get("chapters"):
        db.log_event("warn", "revise", f"{vid} 台本の修正に失敗")
        return None
    new_plan.setdefault("theme", plan.get("theme"))
    new_plan.setdefault("target_seconds", plan.get("target_seconds"))
    new_plan.setdefault("shorts", plan.get("shorts"))
    rp = state_dir() / "videos" / f"{vid}-revised-plan.json"
    rp.write_text(json.dumps(new_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    nid = f"{vid}-r1"
    out_root = state_dir() / "videos" / nid
    db.upsert_video(id=nid, kind=v["kind"], theme=v["theme"], status="planned", idea_id=v.get("idea_id"),
                    series=v.get("series"), dir=str(out_root), notes=f"{vid} を審査の指摘で修正")
    db.upsert_video(id=vid, status="rejected", notes=f"修正版 {nid} に置き換え")
    _render(nid, v["theme"], v["kind"], float(new_plan.get("target_seconds") or 60), out_root, plan=rp)
    review(nid, rules)
    return nid


def review(vid: str, rules: dict, use_llm: bool = True) -> dict:
    v = db.video(vid)
    if v["kind"] != "short":
        try:
            from . import thumbs
            thumbs.make(Path(v["dir"]))  # サムネイル候補 3 種 (作業用の画像を消す前に作る)
        except Exception as e:
            db.log_event("warn", "thumbs", f"{vid} サムネイル候補の作成に失敗: {e}")
    # 修正版は元の版 (ID の前方一致) と比べない (自分自身との重複判定を防ぐ)
    ancestors = [Path(a["dir"]) for a in db.videos() if a["id"] != vid and vid.startswith(a["id"]) and a.get("dir")]
    res = qa.review(Path(v["dir"]), use_llm=use_llm, min_score=rules["qa_min_score"], exclude=ancestors)
    try:
        from . import scriptsheet
        scriptsheet.write(Path(v["dir"]), vid)
    except Exception as e:
        db.log_event("warn", "script", f"{vid} 台本シートの作成に失敗: {e}")
    status = {"pass": "qa_passed", "fix": "qa_failed", "needs_review": "needs_review", "blocked": "qa_failed"}[res["verdict"]]
    db.upsert_video(id=vid, status=status, qa_score=res["total"], qa_json=json.dumps(res, ensure_ascii=False))
    db.log_event("info" if status == "qa_passed" else "warn", "qa",
                 f"{vid} {res['title']}: {res['total']}点 → {res['verdict']}")
    work = Path(v["dir"]) / "work"
    if status == "qa_passed" and work.exists():
        shutil.rmtree(work, ignore_errors=True)  # 中間ファイルは容量節約のため削除 (plan.json から作り直せる)
    return res


def upload_private(yt: YouTube, vid: str) -> str | None:
    v = db.video(vid)
    d = Path(v["dir"])
    video = d / "video.mp4"
    digest = sha256(video)
    with db.connect() as con:
        dup = con.execute("SELECT id, youtube_id FROM videos WHERE file_sha=? AND id<>?", (digest, vid)).fetchone()
    if dup:
        db.upsert_video(id=vid, status="rejected", notes=f"同じファイルが {dup['id']} でアップロード済み")
        return None
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
    title = meta["titles"][0]
    desc = meta["description"]
    # 生成 AI の画像を使った場合は、写実的に見える可能性を考えて「改変・合成コンテンツ」を申告する (保守的な運用)
    ai_images = "Pollinations" in desc or "画像生成" in desc
    desc += "\n\n※ この動画のナレーションは音声合成、映像の一部は画像生成 AI で制作しています。内容は資料で確認していますが、誤りに気づいた方はコメントでお知らせください。"
    yid = yt.upload(video, title, desc, meta.get("tags", []), category="27",
                    synthetic=ai_images or bool(plan.get("realistic")))
    db.upsert_video(id=vid, youtube_id=yid, file_sha=digest, status="uploaded_private")
    thumb = d / "thumbnail.png"
    tj = d / "thumbs" / "thumbs.json"
    if tj.exists():  # 評価が最も高い候補を使う (残りは Studio の「テストと比較」用)
        thumb = Path(json.loads(tj.read_text(encoding="utf-8"))[0]["path"])
    if thumb.exists() and v["kind"] != "short":
        try:
            yt.set_thumbnail(yid, thumb)
        except Exception as e:  # 電話番号の確認が済んでいないとカスタムサムネイルは使えない
            db.log_event("warn", "youtube", f"サムネイル設定失敗 ({yid}): {e}")
    db.log_event("info", "youtube", f"非公開でアップロード: {title} https://youtu.be/{yid}")
    return yid


def approve(vid: str, at: str | None = None) -> None:
    v = db.video(vid)
    if not v:
        raise ValueError(f"{vid} がありません")
    if v["status"] not in ("uploaded_private", "qa_passed", "held", "needs_review"):
        raise ValueError(f"{vid} は {v['status']} のため承認できません")
    if v["status"] == "needs_review":
        db.log_event("info", "ops", f"{vid}: 人間の確認済みとして承認 (オーナー判断)")
    db.upsert_video(id=vid, status="approved", publish_at=at)


def hold(vid: str, yt: YouTube | None = None) -> None:
    v = db.video(vid)
    if v.get("youtube_id") and v["status"] == "scheduled" and yt:
        yt.unschedule(v["youtube_id"])
    db.upsert_video(id=vid, status="held", publish_at=None)


def schedule_approved(yt: YouTube, rules: dict) -> list[str]:
    done = []
    approved = [v for v in db.videos("approved") if v.get("youtube_id")]
    taken = [v["publish_at"] for v in db.videos(["scheduled"]) if v.get("publish_at")]
    for v in approved:
        at = v.get("publish_at")
        if not at:
            hours = rules["publish_hours_jst"] if v["kind"] == "short" else [h for h in rules["publish_hours_jst"] if h >= 17] or [19]
            at = next_slots(1, hours, taken)[0]
        yt.schedule(v["youtube_id"], at)
        taken.append(at)
        db.upsert_video(id=v["id"], status="scheduled", publish_at=at)
        done.append(f"{v['title']} → {at}")
    return done


def sync_published(yt: YouTube) -> int:
    sched = [v for v in db.videos(["scheduled", "uploaded_private"]) if v.get("youtube_id")]
    if not sched:
        return 0
    n = 0
    for item in yt.get_videos([v["youtube_id"] for v in sched], "status,snippet"):
        if item["status"]["privacyStatus"] == "public":
            v = next(x for x in sched if x["youtube_id"] == item["id"])
            db.upsert_video(id=v["id"], status="public", published_at=item["snippet"].get("publishedAt", db.now())
                            .replace("Z", "+00:00"))
            n += 1
    return n


def plan_today(rules: dict, today: datetime | None = None) -> list[str]:
    """今日作る本数 (形式のリスト)。ストック (承認待ち + 予約済み) が多すぎるときは作らない。"""
    today = today or datetime.now(JST)
    pending = db.videos(["qa_passed", "uploaded_private", "approved", "scheduled", "needs_review"])
    if len(pending) >= 10:
        return []
    kinds = ["short"] * int(rules["shorts_per_day"])
    wd = today.weekday()
    long_days = {1: [2], 2: [1, 4], 3: [0, 2, 4]}.get(int(rules["longs_per_week"]), [])
    if wd in long_days:
        kinds.append("long")
    if int(rules["sleep_per_week"]) >= 1 and wd == 5:
        kinds.append("sleep")
    return kinds


def daily(produce_videos: bool = True, use_llm: bool = True) -> dict:
    summary = {"started": db.now(), "steps": {}, "errors": []}
    rules = db.active_rules()

    def step(name, fn):
        try:
            summary["steps"][name] = fn()
        except (AuthError, QuotaError) as e:
            summary["errors"].append(f"{name}: {e}")
            db.log_event("critical", name, str(e))
            raise
        except Exception as e:
            summary["errors"].append(f"{name}: {e}")
            db.log_event("error", name, str(e))

    with lock():
        yt = YouTube() if is_configured() else None
        try:
            if yt:
                from . import analytics
                step("sync", lambda: sync_published(yt))
                step("analytics", lambda: analytics.collect(yt))
                ins = analytics.insights()
                step("improve", lambda: analytics.apply_proposals(ins["proposals"]))
        except (AuthError, QuotaError):
            yt = None  # 投稿系は中止し、制作と日報は続ける

        if is_paused():
            summary["steps"]["paused"] = stop_file().read_text(encoding="utf-8").strip()
        elif produce_videos:
            if free_gb() < MIN_FREE_GB:
                db.log_event("critical", "ops", f"ディスク残量 {free_gb():.1f}GB。制作を中止")
            else:
                kinds = plan_today(rules)
                st = ideas.stock()
                if use_llm and sum(st.values()) < 20:
                    step("ideas", lambda: ideas.store(ideas.generate(30)))
                made = []
                # ダッシュボードで「作り直し」を指示された動画 (台本 plan.json から作り直す)
                for old in (db.get_kv("regenerate_queue", []) or [])[:2]:
                    try:
                        made.append(regenerate(old, rules))
                    except Exception as e:
                        summary["errors"].append(f"regenerate:{old}: {e}")
                    db.set_kv("regenerate_queue", [x for x in db.get_kv("regenerate_queue", []) if x != old])
                # 途中で止まった動画の再開
                for v in db.videos(["produced"]):
                    step(f"qa:{v['id']}", lambda v=v: review(v["id"], rules, use_llm))
                for kind in kinds:
                    idea = ideas.pick(kind)
                    if not idea:
                        db.log_event("warn", "ideas", f"{kind} の企画ストックがありません")
                        continue
                    try:
                        vid = produce(idea, rules)
                        made.append(vid)
                        step(f"qa:{vid}", lambda vid=vid: review(vid, rules, use_llm))
                        if use_llm and (db.video(vid) or {}).get("status") == "qa_failed":
                            step(f"revise:{vid}", lambda vid=vid: revise(vid, rules))  # 修正して再審査 (1 回まで)
                    except Exception as e:
                        summary["errors"].append(f"produce:{kind}: {e}")
                        db.log_event("error", "produce", str(e))
                summary["steps"]["produced"] = made
                if rules.get("auto_publish"):
                    for v in db.videos("qa_passed"):
                        approve(v["id"])
            if yt:
                try:
                    uploaded = 0
                    for v in db.videos(["qa_passed", "approved"]):
                        if uploaded >= rules["max_uploads_per_day"]:
                            break
                        if not v.get("youtube_id"):
                            step(f"upload:{v['id']}", lambda v=v: upload_private(yt, v["id"]))
                            if v["status"] == "approved":
                                db.upsert_video(id=v["id"], status="approved")
                            uploaded += 1
                    step("schedule", lambda: schedule_approved(yt, rules))
                except (AuthError, QuotaError):
                    pass
        from . import report, dashboard
        step("report", lambda: str(report.write_daily()))
        step("dashboard", lambda: str(dashboard.write()))
    summary["finished"] = db.now()
    db.set_kv("last_daily", summary)
    return summary
