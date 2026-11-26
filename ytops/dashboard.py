"""運営管理ダッシュボード (スマホ対応)。

- write(): 現在の状況を 1 枚の HTML (state/dashboard/index.html) に書き出す (閲覧専用・どこでも開ける)
- serve(): 操作できる管理画面。既定は 127.0.0.1 のみで待ち受け、操作にはトークンが必要
    承認 / 保留 / 予約時刻の変更 / 作り直し / 自動運転の停止・再開 / 投稿頻度の変更 / 動画・サムネのプレビュー
  外部 (スマホ) から使う場合は、Tailscale などの VPN 経由にし、インターネットへ直接公開しない
"""
from __future__ import annotations

import html
import json
import secrets
import stat
import urllib.parse
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import analytics, db, ideas, ops
from .config import JST, YPP, state_dir
from .report import owner_tasks, project_day

CSS = """
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d2433;--muted:#6b7280;--line:#e5e1d8;--accent:#b3462e;--ok:#2f7d4f;--warn:#b7791f;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14161b;--card:#1d2027;--ink:#eceae4;--muted:#9aa0aa;--line:#2c3039;--accent:#e07a5f;--ok:#5fb37f;--warn:#e0a84a;--bad:#ef6b62}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:980px;margin:auto;padding:16px}h1{font-size:20px;margin:4px 0 12px}h2{font-size:16px;margin:22px 0 8px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.k{color:var(--muted);font-size:12px}.v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;background:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.wrap{overflow-x:auto}.tag{font-size:11px;padding:1px 6px;border-radius:8px;border:1px solid var(--line);white-space:nowrap}
.pass{color:var(--ok)}.fail{color:var(--bad)}.warn{color:var(--warn)}
button,select,input{font:inherit;padding:6px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
button.p{background:var(--accent);color:#fff;border-color:var(--accent)}form{display:inline}
.row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px}img.t{max-width:220px;width:100%;border-radius:6px}
"""

LABEL = {"planned": "企画済", "produced": "制作済", "qa_failed": "審査不合格", "needs_review": "要人間確認",
         "qa_passed": "審査合格", "uploaded_private": "承認待ち(非公開UP済)", "approved": "承認済",
         "scheduled": "予約済", "public": "公開中", "held": "保留", "rejected": "不採用", "error": "エラー"}


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def build(token: str | None = None) -> str:
    ch = analytics.latest_channel()
    prog = analytics.monetization_progress(ch)
    rules = db.active_rules()
    vids = db.videos()
    table = analytics.video_table()
    ranked = sorted([r for r in table if r.get("views") is not None], key=lambda r: r["views"], reverse=True)
    deadline = date.fromisoformat(YPP["change_date"])
    end = date.fromisoformat("2026-11-26")
    from datetime import timedelta
    end = end + timedelta(days=89)
    today = datetime.now(JST).date()
    with db.connect() as con:
        events = [dict(r) for r in con.execute(
            "SELECT * FROM events WHERE level IN ('warn','error','critical') ORDER BY ts DESC LIMIT 12")]
        rule_hist = [dict(r) for r in con.execute("SELECT version,created_at,reason,active FROM rules ORDER BY version DESC LIMIT 6")]
    paused = ops.is_paused()

    def stat_card(k, v, pct=None):
        b = f'<div class="bar"><i style="width:{min(100, pct or 0)}%"></i></div>' if pct is not None else ""
        return f'<div class="card"><div class="k">{_e(k)}</div><div class="v">{_e(v)}</div>{b}</div>'

    def action(vid, act, label, extra="", cls=""):
        if not token:
            return ""
        return (f'<form method="post" action="/action"><input type="hidden" name="t" value="{_e(token)}">'
                f'<input type="hidden" name="id" value="{_e(vid)}"><input type="hidden" name="a" value="{act}">{extra}'
                f'<button class="{cls}">{label}</button></form>')

    req = prog["requirements"]
    h = [f"<!doctype html><html lang=ja><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>運営ダッシュボード</title><style>{CSS}</style></head><body><main>",
         f"<h1>YouTube 運営ダッシュボード <span class=tag>Day {project_day()} / 90</span> "
         f"<span class='tag {'fail' if paused else 'pass'}'>{'自動運転 停止中' if paused else '自動運転中'}</span></h1>",
         f'<div class=k>更新 {db.now()} / 90日目 {end} まで残り {(end - today).days} 日 / '
         f'旧基準での申請期限 {deadline} まで残り {(deadline - today).days} 日</div>',
         '<h2>収益化までの進捗</h2><div class="grid">',
         stat_card("登録者数", f"{prog['subs']:,} / {req['subs']:,}", 100 * prog["subs"] / req["subs"]),
         stat_card("長尺の公開視聴時間 (推定)", f"{prog['watch_hours']:,.0f} / {req['watch_hours']:,} h",
                   100 * prog["watch_hours"] / req["watch_hours"]),
         stat_card("ショート視聴 90日 (推定)", f"{prog['shorts_views']:,} / {req['shorts_views'] / 1e6:.0f}M",
                   100 * prog["shorts_views"] / req["shorts_views"]),
         stat_card("収益化達成率", f"{prog['overall']}%", prog["overall"]),
         stat_card("本日の再生数", ch.get("views_delta", "未取得")),
         stat_card("本日の登録者増加", ch.get("subs_delta", "未取得")),
         stat_card("運営コスト", "0 円"),
         stat_card("企画ストック", sum(ideas.stock().values())),
         "</div>"]
    tasks = owner_tasks()
    h.append("<h2>オーナーの作業</h2><div class=card>" + ("<br>".join(_e(t) for t in tasks) or "確認事項なし") + "</div>")

    def vrow(v):
        q = json.loads(v["qa_json"]) if v.get("qa_json") else {}
        thumb = Path(v["dir"] or "") / "thumbnail.png"
        prev = ""
        if token and (Path(v["dir"] or "") / "video.mp4").exists():
            prev = f'<a href="/file/{_e(v["id"])}/video.mp4?t={_e(token)}">動画</a> '
            if thumb.exists():
                prev += f'<a href="/file/{_e(v["id"])}/thumbnail.png?t={_e(token)}">サムネ</a> '
            prev += f'<a href="/file/{_e(v["id"])}/qa.md?t={_e(token)}">審査</a>'
        yt = f' <a href="https://studio.youtube.com/video/{_e(v["youtube_id"])}/edit">Studio</a>' if v.get("youtube_id") else ""
        acts = ""
        if v["status"] in ("uploaded_private", "qa_passed", "needs_review", "held"):
            acts += action(v["id"], "approve", "承認", cls="p")
        if v["status"] in ("approved", "scheduled", "uploaded_private", "qa_passed"):
            acts += action(v["id"], "hold", "保留")
        if v["status"] in ("approved", "scheduled"):
            acts += action(v["id"], "reschedule", "時刻変更", '<input type="datetime-local" name="at">')
        if v["status"] in ("qa_failed", "error", "held", "needs_review"):
            acts += action(v["id"], "regenerate", "作り直し")
        verdict = q.get("verdict", "")
        cls = {"pass": "pass", "blocked": "fail", "fix": "warn", "needs_review": "warn"}.get(verdict, "")
        return (f"<tr><td><span class=tag>{_e(v['kind'])}</span><br><span class=tag>{_e(LABEL.get(v['status'], v['status']))}</span></td>"
                f"<td>{_e(v['title'] or v['theme'])}<br><span class=k>{_e(v['id'])} {_e(v.get('publish_at') or '')}</span>"
                f"<div class=row>{prev}{yt}</div><div class=row>{acts}</div></td>"
                f"<td class={cls}>{_e(v.get('qa_score') or '')}</td></tr>")

    groups = [("承認待ち・確認待ち", ["uploaded_private", "qa_passed", "needs_review"]),
              ("投稿予定", ["approved", "scheduled"]), ("制作中・要修正", ["planned", "produced", "qa_failed", "error", "held"])]
    for title, sts in groups:
        rows = [v for v in vids if v["status"] in sts]
        h.append(f"<h2>{title} ({len(rows)})</h2><div class='card wrap'><table><tr><th>形式</th><th>動画</th><th>審査</th></tr>"
                 + "".join(vrow(v) for v in rows) + "</table></div>")
    h.append(f"<h2>人気動画ランキング</h2><div class='card wrap'><table><tr><th>動画</th><th>再生</th><th>視聴率</th><th>登録</th><th>CTR</th></tr>"
             + "".join(f"<tr><td>{_e(r['title'])}</td><td>{_e(r['views'])}</td><td>{_e(r.get('avg_view_pct') or '—')}</td>"
                       f"<td>{_e(r.get('subs_gained') or '—')}</td><td>{_e(r.get('ctr') or '—')}</td></tr>" for r in ranked[:10])
             + "</table></div>")
    if len(ranked) > 3:
        h.append("<h2>低成績動画</h2><div class=card>" + "<br>".join(f"{_e(r['title'])} ({r['views']})" for r in ranked[-3:]) + "</div>")
    h.append("<h2>最近の改善 (ルール履歴)</h2><div class='card wrap'><table>" + "".join(
        f"<tr><td>v{r['version']}{' (適用中)' if r['active'] else ''}</td><td>{_e(r['created_at'][:16])}</td><td>{_e(r['reason'])}</td>"
        f"<td>{action(str(r['version']), 'rollback', 'この版に戻す') if not r['active'] else ''}</td></tr>" for r in rule_hist) + "</table></div>")
    h.append("<h2>エラー・警告</h2><div class='card wrap'><table>" + "".join(
        f"<tr><td>{_e(e['ts'][5:16])}</td><td class={'fail' if e['level'] != 'warn' else 'warn'}>{_e(e['level'])}</td>"
        f"<td>{_e(e['component'])}</td><td>{_e(e['message'][:200])}</td></tr>" for e in events) + "</table></div>")
    if token:
        h.append("<h2>運転設定</h2><div class=card><div class=row>"
                 + (action("-", "resume", "自動運転を再開", cls="p") if paused else action("-", "pause", "自動運転を停止"))
                 + "</div><div class=row>"
                 + action("-", "freq", "投稿頻度を変更",
                          f'ショート/日 <input name=shorts type=number min=0 max=3 value={rules["shorts_per_day"]} style="width:4em"> '
                          f'長尺/週 <input name=longs type=number min=0 max=3 value={rules["longs_per_week"]} style="width:4em"> ')
                 + f"</div><div class=k>投稿時間枠 (JST): {rules['publish_hours_jst']} / 自動公開: {'許可' if rules['auto_publish'] else '未許可 (承認制)'}</div></div>")
    h.append("</main></body></html>")
    return "\n".join(h)


def write() -> Path:
    d = state_dir() / "dashboard"
    d.mkdir(exist_ok=True)
    p = d / "index.html"
    p.write_text(build(None), encoding="utf-8")
    return p


def token() -> str:
    p = state_dir() / "dashboard_token"
    if not p.exists():
        p.write_text(secrets.token_urlsafe(24))
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return p.read_text().strip()


def handle_action(form: dict) -> str:
    a, vid = form.get("a"), form.get("id")
    yt = None
    from .youtube import YouTube, is_configured
    if is_configured():
        yt = YouTube()
    if a == "approve":
        ops.approve(vid)
    elif a == "hold":
        ops.hold(vid, yt)
    elif a == "reschedule":
        at = form.get("at")
        if not at:
            return "時刻が空です"
        iso = datetime.fromisoformat(at).replace(tzinfo=JST).isoformat()
        v = db.video(vid)
        if yt and v.get("youtube_id") and v["status"] == "scheduled":
            yt.schedule(v["youtube_id"], iso)
        db.upsert_video(id=vid, publish_at=iso)
    elif a == "regenerate":
        v = db.video(vid)
        db.upsert_video(id=vid, status="rejected", notes="作り直し指示")
        db.set_kv("regenerate_queue", (db.get_kv("regenerate_queue", []) or []) + [vid])
        return f"{v['title']} を作り直し待ちにしました (次回の自動実行で制作)"
    elif a == "pause":
        ops.pause("ダッシュボードから停止")
    elif a == "resume":
        ops.resume()
    elif a == "freq":
        r = db.active_rules()
        db.set_rules({**r, "shorts_per_day": max(0, min(3, int(form.get("shorts", r["shorts_per_day"])))),
                      "longs_per_week": max(0, min(3, int(form.get("longs", r["longs_per_week"]))))},
                     "ダッシュボードから投稿頻度を変更 (オーナー)")
    elif a == "rollback":
        db.rollback_rules(int(vid))
    else:
        return "不明な操作"
    db.log_event("info", "dashboard", f"操作: {a} {vid}")
    return "OK"


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    tok = token()

    class H(BaseHTTPRequestHandler):
        def _ok(self, body: bytes, ctype="text/html; charset=utf-8", code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authed(self, q: dict) -> bool:
            return secrets.compare_digest(q.get("t", [""])[0], tok)

        def do_GET(self):  # noqa: N802
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._authed(q):
                return self._ok("トークンが必要です (?t=...)".encode(), code=403)
            if u.path.startswith("/file/"):
                _, _, vid, name = u.path.split("/", 3)
                v = db.video(urllib.parse.unquote(vid))
                if not v or name not in ("video.mp4", "thumbnail.png", "qa.md", "metadata.md"):
                    return self._ok(b"not found", code=404)
                f = Path(v["dir"]) / name
                if not f.exists():
                    return self._ok(b"not found", code=404)
                ct = {"mp4": "video/mp4", "png": "image/png", "md": "text/plain; charset=utf-8"}[name.rsplit(".", 1)[1]]
                return self._ok(f.read_bytes(), ct)
            self._ok(build(tok).encode())

        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length", 0))
            form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
            if not secrets.compare_digest(form.get("t", ""), tok):
                return self._ok(b"forbidden", code=403)
            try:
                msg = handle_action(form)
            except Exception as e:
                msg = f"エラー: {e}"
            self._ok(f"<meta http-equiv=refresh content='1;url=/?t={tok}'><p>{_e(msg)}</p>".encode())

        def log_message(self, *a):
            pass

    if host not in ("127.0.0.1", "localhost"):
        print("注意: ローカル以外で待ち受けます。VPN (Tailscale 等) の内側だけで使い、インターネットに直接公開しないでください。")
    print(f"管理画面: http://{host}:{port}/?t={tok}")
    ThreadingHTTPServer((host, port), H).serve_forever()
