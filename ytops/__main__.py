"""使い方: python -m ytops <コマンド>

  status                    現在の状況 (収益化進捗・動画の状態・オーナーの作業)
  daily [--no-produce]      毎日の自動運営を 1 回実行 (スケジューラから呼ぶ)
  ideas [--n 30]            企画を生成・評価して保存 / ideas --list で一覧
  add <動画フォルダ> [--kind short|long|sleep]  手動で作った動画を管理対象に追加
  qa <ID または動画フォルダ>  品質審査
  list [状態]               動画一覧
  approve <ID> [--at ISO]   公開を承認 (予約投稿の対象にする)
  hold <ID>                 保留 (予約を取り消し非公開のまま)
  stop "理由" / resume      自動運転の緊急停止 / 再開
  rules [--set k=v] [--rollback N]   改善ルールの表示・変更・ロールバック
  auth [--manual]           YouTube API の認証 (最初の 1 回)
  report [--weekly]         日報 / 週次経営会議
  simulate                  90 日間の収益化シミュレーション
  dashboard [--serve] [--host 127.0.0.1] [--port 8787]
  import-studio <csv>       YouTube Studio のエクスポート (インプレッション・CTR) を取り込む
  backup                    運営データベースのバックアップ
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from . import db
from .config import JST, PROJECT, state_dir


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ytops", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status")
    d = sub.add_parser("daily"); d.add_argument("--no-produce", action="store_true"); d.add_argument("--no-llm", action="store_true")
    i = sub.add_parser("ideas"); i.add_argument("--n", type=int, default=30); i.add_argument("--list", action="store_true")
    i.add_argument("--no-web", action="store_true"); i.add_argument("--export", type=Path)
    a = sub.add_parser("add"); a.add_argument("dir", type=Path); a.add_argument("--kind")
    q = sub.add_parser("qa"); q.add_argument("target"); q.add_argument("--no-llm", action="store_true")
    l = sub.add_parser("list"); l.add_argument("status", nargs="?")
    ap_ = sub.add_parser("approve"); ap_.add_argument("id"); ap_.add_argument("--at")
    h = sub.add_parser("hold"); h.add_argument("id")
    s = sub.add_parser("stop"); s.add_argument("reason", nargs="?", default="オーナーが停止")
    sub.add_parser("resume")
    r = sub.add_parser("rules"); r.add_argument("--set", action="append", default=[]); r.add_argument("--rollback", type=int)
    au = sub.add_parser("auth"); au.add_argument("--manual", action="store_true")
    rp = sub.add_parser("report"); rp.add_argument("--weekly", action="store_true")
    sub.add_parser("simulate")
    dsh = sub.add_parser("dashboard"); dsh.add_argument("--serve", action="store_true")
    dsh.add_argument("--host", default="127.0.0.1"); dsh.add_argument("--port", type=int, default=8787)
    im = sub.add_parser("import-studio"); im.add_argument("csv", type=Path)
    sub.add_parser("backup")
    sub.add_parser("competitors")
    sv = sub.add_parser("save-state"); sv.add_argument("--force", action="store_true")
    sub.add_parser("load-state")
    x = ap.parse_args(argv)

    if x.cmd == "status":
        from . import analytics, ideas, ops
        from .report import owner_tasks, project_day
        prog = analytics.monetization_progress()
        print(f"Day {project_day()} / 90  自動運転: {'停止中' if ops.is_paused() else '稼働'}")
        print(f"収益化: 登録者 {prog['subs']} / 長尺視聴 {prog['watch_hours']}h / ショート90日 {prog['shorts_views']} "
              f"→ 達成率 {prog['overall']}% (基準 {prog['tier']})")
        counts = {}
        for v in db.videos():
            counts[v["status"]] = counts.get(v["status"], 0) + 1
        print("動画:", counts or "なし", " 企画ストック:", ideas.stock())
        print("オーナーの作業:", " / ".join(owner_tasks()) or "確認事項なし")
    elif x.cmd == "daily":
        from . import ops
        print(json.dumps(ops.daily(produce_videos=not x.no_produce, use_llm=not x.no_llm), ensure_ascii=False, indent=1))
    elif x.cmd == "ideas":
        from . import ideas
        if not x.list:
            items = ideas.generate(x.n, web=not x.no_web)
            print("保存 / 除外:", ideas.store(items))
        out = x.export or PROJECT / "ideas" / "backlog.md"
        ideas.export_markdown(out)
        print("企画ストック:", ideas.stock(), "→", out)
    elif x.cmd == "add":
        from aivideo import registry
        dd = x.dir.resolve()
        plan = json.loads((dd / "plan.json").read_text(encoding="utf-8"))
        from .qa import kind_of
        kind = x.kind or kind_of(dd, plan)
        meta = json.loads((dd / "metadata.json").read_text(encoding="utf-8"))
        vid = f"{datetime.now(JST):%Y%m%d%H%M}-{kind}-manual"
        db.upsert_video(id=vid, kind=kind, theme=plan.get("theme"), title=meta["titles"][0], dir=str(dd), status="produced")
        print("追加:", vid)
    elif x.cmd == "qa":
        from . import ops, qa
        if db.video(x.target):
            res = ops.review(x.target, db.active_rules(), use_llm=not x.no_llm)
        else:
            res = qa.review(Path(x.target), use_llm=not x.no_llm)
        print(f"{res['title']}: {res['total']}点 → {res['verdict']}")
        for b in res["blockers"] + res["needs_human"]:
            print("  !", b)
    elif x.cmd == "list":
        for v in db.videos(x.status):
            print(f"{v['id']:28} {v['status']:16} {v['qa_score'] or '':>5} {v['title'] or v['theme']}")
    elif x.cmd == "approve":
        from . import ops
        ops.approve(x.id, x.at)
        print("承認しました。次回の自動実行で予約投稿します。")
    elif x.cmd == "hold":
        from . import ops
        from .youtube import YouTube, is_configured
        ops.hold(x.id, YouTube() if is_configured() else None)
        print("保留にしました。")
    elif x.cmd == "stop":
        from . import ops
        ops.pause(x.reason)
        print("自動運転を停止しました。再開: python -m ytops resume")
    elif x.cmd == "resume":
        from . import ops
        ops.resume()
        print("再開しました。")
    elif x.cmd == "rules":
        if x.rollback:
            db.rollback_rules(x.rollback)
        if x.set:
            cur = db.active_rules()
            for kv in x.set:
                k, v = kv.split("=", 1)
                if k == "auto_publish" and v.lower() in ("1", "true"):
                    print("注意: 自動公開はオーナーの明示的な承認が必要です (DECISIONS.md に記録してください)")
                cur[k] = json.loads(v) if v[:1] in "[{0123456789tf" else v
            db.set_rules(cur, "手動変更: " + ", ".join(x.set))
        print(json.dumps(db.active_rules(), ensure_ascii=False, indent=1))
        for r in db.rules_history(5):
            print(f"v{r['version']} {'*' if r['active'] else ' '} {r['created_at'][:16]} {r['reason']}")
    elif x.cmd == "auth":
        from .youtube import authorize
        print("保存しました:", authorize(manual=x.manual))
    elif x.cmd == "report":
        from . import report
        p = report.write_weekly() if x.weekly else report.write_daily()
        print(p.read_text(encoding="utf-8"))
    elif x.cmd == "simulate":
        from . import simulate
        start = date.fromisoformat("2026-11-26")
        md = simulate.to_markdown(simulate.run(start), start)
        out = PROJECT / "strategy" / "monetization_simulation.md"
        out.write_text(md, encoding="utf-8")
        print(md)
    elif x.cmd == "dashboard":
        from . import dashboard
        if x.serve:
            dashboard.serve(x.host, x.port)
        else:
            print(dashboard.write())
    elif x.cmd == "import-studio":
        from . import analytics
        print("取り込み:", analytics.import_studio_csv(x.csv), "件")
    elif x.cmd == "backup":
        dst = state_dir() / "backups"
        dst.mkdir(exist_ok=True)
        out = dst / f"ytops_{datetime.now(JST):%Y%m%d_%H%M}.sqlite3"
        with db.connect() as con:
            import sqlite3
            b = sqlite3.connect(out)
            con.backup(b)
            b.close()
        for old in sorted(dst.glob("ytops_*.sqlite3"))[:-14]:
            old.unlink()
        print("バックアップ:", out)
    elif x.cmd == "competitors":
        from . import competitors
        print(competitors.run())
    elif x.cmd == "save-state":
        # クラウド実行では作業環境が毎回消えるため、運営データをリポジトリに保存する。公開リポジトリでは実行しない
        import os
        if os.environ.get("YTOPS_REPO_PRIVATE") != "1" and not x.force:
            print("リポジトリが非公開であることを確認してから YTOPS_REPO_PRIVATE=1 を設定してください (運営データの公開を防ぐため)")
            return 1
        dst = PROJECT / "database"
        dst.mkdir(exist_ok=True)
        import sqlite3
        with db.connect() as con:
            b = sqlite3.connect(dst / "ytops.sqlite3")
            con.backup(b)
            b.close()
        rep = PROJECT / "reports"
        for f in (state_dir() / "reports").glob("*.md"):
            shutil.copy2(f, rep / f.name)
        shutil.copy2(state_dir() / "dashboard" / "index.html", PROJECT / "dashboard" / "index.html") \
            if (state_dir() / "dashboard" / "index.html").exists() else None
        print("保存しました:", dst)
    elif x.cmd == "load-state":
        src = PROJECT / "database" / "ytops.sqlite3"
        if src.exists() and not db.path().exists():
            shutil.copy2(src, db.path())
            print("復元しました:", db.path())
        else:
            print("復元不要 (既存の DB あり、または保存データなし)")
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
