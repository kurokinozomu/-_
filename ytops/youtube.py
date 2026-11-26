"""YouTube Data API v3 / Analytics API v2 (公式 API のみ。ブラウザ操作・認証回避は行わない)。

認証: OAuth 2.0 (デスクトップアプリ型)。
  - クライアント ID / シークレット: 環境変数 YT_CLIENT_ID / YT_CLIENT_SECRET (または .env)
  - リフレッシュトークン: 環境変数 YT_REFRESH_TOKEN、または ~/.config/ytops/token.json (権限 600)
  どれもリポジトリにはコミットしない。

方針:
  - アップロードは必ず「非公開」。公開はオーナーの承認後に publishAt (予約) で行う
  - 同じファイル (SHA-256) は二度アップロードしない
  - 1 日の API 利用枠を記録し、上限の手前で止める
  - 一時的なエラー (5xx / 429 / 通信断) は回数制限つきで再試行。認証エラーは即停止して報告
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import secrets
import stat
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path

import requests

from . import db
from .config import JST, env

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"

# 公式ドキュメントの記載が改訂で揺れているため、利用枠は保守的 (多め) に見積もる
COST = {"videos.insert": 1600, "videos.update": 50, "thumbnails.set": 50, "playlistItems.insert": 50,
        "playlists.insert": 50, "videos.list": 1, "channels.list": 1, "playlists.list": 1, "search.list": 100,
        "commentThreads.list": 1}
DAILY_QUOTA = int(env("YT_DAILY_QUOTA", "10000") or 10000)
SAFETY = 0.9


class AuthError(RuntimeError):
    """認証の問題。自動では直せないのでオーナーに報告する。"""


class QuotaError(RuntimeError):
    pass


def token_file() -> Path:
    return Path(env("YT_TOKEN_FILE") or Path.home() / ".config" / "ytops" / "token.json")


def _client() -> tuple[str, str]:
    cid, sec = env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET")
    if not cid or not sec:
        raise AuthError("YT_CLIENT_ID / YT_CLIENT_SECRET が未設定です (youtube_automation/OWNER_TASKS.md の手順 3)")
    return cid, sec


def _refresh_token() -> str:
    if env("YT_REFRESH_TOKEN"):
        return env("YT_REFRESH_TOKEN")
    p = token_file()
    if p.exists():
        return json.loads(p.read_text())["refresh_token"]
    raise AuthError("YouTube の認証が未完了です。`python -m ytops auth` を実行してください")


def is_configured() -> bool:
    try:
        _client()
        _refresh_token()
        return True
    except AuthError:
        return False


def save_token(tok: dict) -> Path:
    p = token_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"refresh_token": tok["refresh_token"], "scope": tok.get("scope", ""),
                             "saved_at": db.now()}))
    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    return p


def authorize(manual: bool = False, port: int = 8765) -> Path:
    """OAuth 同意画面を開いてリフレッシュトークンを保存する (最初の 1 回だけオーナーが操作)。

    manual=True: スマホ等で同意後、ブラウザのアドレス欄の URL (http://127.0.0.1:8765/?code=...) を貼り付ける方式。
    """
    cid, sec = _client()
    redirect = f"http://127.0.0.1:{port}/"
    state = secrets.token_urlsafe(16)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent", "state": state})
    code = None
    if manual:
        print("次の URL をブラウザで開き、チャンネルのアカウントで許可してください:\n\n" + url + "\n")
        print("許可後に表示される「接続できません」ページのアドレス (http://127.0.0.1...) を丸ごと貼り付けてください。")
        back = input("URL: ").strip()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
        if q.get("state", [""])[0] != state:
            raise AuthError("state が一致しません (別の URL が貼り付けられた可能性)")
        code = q.get("code", [None])[0]
    else:
        got = {}

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                got.update({k: v[0] for k, v in q.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("認証が完了しました。この画面は閉じてかまいません。".encode())

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        print("ブラウザで同意画面を開きます。開かない場合は次の URL を開いてください:\n" + url)
        webbrowser.open(url)
        for _ in range(600):
            if got:
                break
            time.sleep(0.5)
        srv.server_close()
        if got.get("state") != state:
            raise AuthError("認証がタイムアウトしたか、state が一致しません")
        code = got.get("code")
    if not code:
        raise AuthError("認可コードを取得できませんでした")
    r = requests.post(TOKEN_URL, data={"code": code, "client_id": cid, "client_secret": sec,
                                       "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=30)
    tok = r.json()
    if "refresh_token" not in tok:
        raise AuthError(f"トークン取得に失敗: {tok.get('error_description') or tok}")
    return save_token(tok)


class YouTube:
    def __init__(self):
        self._access, self._exp = None, 0.0

    # ---- 認証 ----
    def token(self) -> str:
        if self._access and time.time() < self._exp - 60:
            return self._access
        cid, sec = _client()
        r = requests.post(TOKEN_URL, data={"client_id": cid, "client_secret": sec,
                                           "refresh_token": _refresh_token(), "grant_type": "refresh_token"},
                          timeout=30)
        d = r.json()
        if "access_token" not in d:
            # invalid_grant: トークン失効 (同意画面が「テスト」のままだと 7 日で失効する)
            raise AuthError(f"アクセストークンを更新できません: {d.get('error')} {d.get('error_description', '')}")
        self._access, self._exp = d["access_token"], time.time() + float(d.get("expires_in", 3600))
        return self._access

    # ---- 利用枠 ----
    @staticmethod
    def _today() -> str:
        # API の利用枠は太平洋時間の 0 時にリセットされる。概算として UTC-8 の日付で数える
        return datetime.utcfromtimestamp(time.time() - 8 * 3600).strftime("%Y-%m-%d")

    def _spend(self, op: str) -> None:
        units = COST.get(op, 1)
        used = db.quota_used(self._today())
        if used + units > DAILY_QUOTA * SAFETY:
            raise QuotaError(f"本日の API 利用枠が上限に近いため {op} を中止 (使用 {used} / {DAILY_QUOTA})")
        db.add_quota(self._today(), units)

    # ---- 共通リクエスト (回数制限つき再試行) ----
    def request(self, method: str, url: str, op: str, retries: int = 4, **kw) -> requests.Response:
        self._spend(op)
        for attempt in range(retries + 1):
            try:
                h = kw.pop("headers", {}) | {"Authorization": f"Bearer {self.token()}"}
                r = requests.request(method, url, headers=h, timeout=kw.pop("timeout", 120), **kw)
            except requests.RequestException as e:
                if attempt == retries:
                    raise
                time.sleep(min(60, 2 ** attempt * 3))
                db.log_event("warn", "youtube", f"{op} 通信エラー、再試行 {attempt + 1}: {e}")
                continue
            if r.status_code in (401,):
                self._access = None
                if attempt == 0:
                    continue
                raise AuthError(f"{op}: 認証エラー 401")
            if r.status_code == 403 and "quota" in r.text.lower():
                raise QuotaError(f"{op}: YouTube 側で利用枠超過 ({r.text[:200]})")
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(min(120, 2 ** attempt * 5))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"{op} 失敗 HTTP {r.status_code}: {r.text[:500]}")
            return r
        raise RuntimeError(f"{op} 再試行の上限")

    # ---- アップロード (再開可能アップロード) ----
    def upload(self, video: Path, title: str, description: str, tags: list[str], category: str = "27",
               synthetic: bool = True, language: str = "ja", publish_at: str | None = None) -> str:
        body = {
            "snippet": {"title": title[:100], "description": description[:5000], "tags": tags[:30],
                        "categoryId": category, "defaultLanguage": language, "defaultAudioLanguage": language},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                       "embeddable": True, "containsSyntheticMedia": bool(synthetic)},
        }
        if publish_at:
            body["status"]["publishAt"] = publish_at
        size = video.stat().st_size
        init = self.request("POST", f"{UPLOAD}/videos?uploadType=resumable&part=snippet,status", "videos.insert",
                            json=body, headers={"X-Upload-Content-Type": "video/mp4",
                                                "X-Upload-Content-Length": str(size)})
        loc = init.headers["Location"]
        chunk = 16 * 1024 * 1024
        pos, fails = 0, 0
        with open(video, "rb") as f:
            while pos < size:
                f.seek(pos)
                data = f.read(chunk)
                end = pos + len(data) - 1
                try:
                    r = requests.put(loc, data=data, timeout=600, headers={
                        "Authorization": f"Bearer {self.token()}", "Content-Length": str(len(data)),
                        "Content-Range": f"bytes {pos}-{end}/{size}"})
                except requests.RequestException as e:
                    r, err = None, e
                if r is not None and r.status_code in (200, 201):
                    return r.json()["id"]
                if r is not None and r.status_code == 308:
                    rng = r.headers.get("Range")
                    pos = int(rng.split("-")[1]) + 1 if rng else 0
                    fails = 0
                    continue
                fails += 1
                if fails > 6:
                    raise RuntimeError(f"アップロード失敗: {getattr(r, 'status_code', err)}")
                time.sleep(min(120, 2 ** fails * 3))
                q = requests.put(loc, timeout=60, headers={"Authorization": f"Bearer {self.token()}",
                                                           "Content-Range": f"bytes */{size}"})
                if q.status_code in (200, 201):
                    return q.json()["id"]
                rng = q.headers.get("Range")
                pos = int(rng.split("-")[1]) + 1 if rng else 0
        raise RuntimeError("アップロードが完了しませんでした")

    def set_thumbnail(self, video_id: str, image: Path) -> None:
        self.request("POST", f"{UPLOAD}/thumbnails/set?videoId={video_id}", "thumbnails.set",
                     data=image.read_bytes(), headers={"Content-Type": "image/png"})

    def get_videos(self, ids: list[str], parts: str = "snippet,status,statistics,contentDetails") -> list[dict]:
        out = []
        for i in range(0, len(ids), 50):
            r = self.request("GET", f"{API}/videos", "videos.list",
                             params={"part": parts, "id": ",".join(ids[i:i + 50])})
            out += r.json().get("items", [])
        return out

    def schedule(self, video_id: str, publish_at_iso: str) -> dict:
        """非公開動画を指定時刻に自動公開する予約を入れる。"""
        cur = self.get_videos([video_id], "status")
        if not cur:
            raise RuntimeError(f"動画 {video_id} が見つかりません")
        st = cur[0]["status"]
        st.update({"privacyStatus": "private", "publishAt": publish_at_iso})
        r = self.request("PUT", f"{API}/videos?part=status", "videos.update",
                         json={"id": video_id, "status": {k: st[k] for k in (
                             "privacyStatus", "publishAt", "selfDeclaredMadeForKids", "embeddable",
                             "containsSyntheticMedia") if k in st}})
        return r.json()

    def unschedule(self, video_id: str) -> None:
        """予約を取り消して非公開のままにする (保留)。"""
        self.request("PUT", f"{API}/videos?part=status", "videos.update",
                     json={"id": video_id, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}})

    def channel(self) -> dict:
        r = self.request("GET", f"{API}/channels", "channels.list",
                         params={"part": "snippet,statistics,status,contentDetails", "mine": "true"})
        items = r.json().get("items", [])
        if not items:
            raise RuntimeError("このアカウントに YouTube チャンネルがありません")
        return items[0]

    def ensure_playlist(self, title: str) -> str:
        r = self.request("GET", f"{API}/playlists", "playlists.list",
                         params={"part": "snippet", "mine": "true", "maxResults": 50})
        for p in r.json().get("items", []):
            if p["snippet"]["title"] == title:
                return p["id"]
        r = self.request("POST", f"{API}/playlists?part=snippet,status", "playlists.insert",
                         json={"snippet": {"title": title}, "status": {"privacyStatus": "public"}})
        return r.json()["id"]

    def add_to_playlist(self, playlist_id: str, video_id: str) -> None:
        self.request("POST", f"{API}/playlistItems?part=snippet", "playlistItems.insert",
                     json={"snippet": {"playlistId": playlist_id,
                                       "resourceId": {"kind": "youtube#video", "videoId": video_id}}})

    def analytics(self, start: str, end: str, metrics: str, dimensions: str = "", filters: str = "",
                  sort: str = "", max_results: int = 0) -> dict:
        p = {"ids": "channel==MINE", "startDate": start, "endDate": end, "metrics": metrics}
        if dimensions:
            p["dimensions"] = dimensions
        if filters:
            p["filters"] = filters
        if sort:
            p["sort"] = sort
        if max_results:
            p["maxResults"] = max_results
        # Analytics API は Data API の利用枠とは別。記録だけする
        for attempt in range(4):
            r = requests.get(ANALYTICS, params=p, headers={"Authorization": f"Bearer {self.token()}"}, timeout=60)
            if r.status_code in (429, 500, 503) and attempt < 3:
                time.sleep(5 * 2 ** attempt)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Analytics API 失敗 HTTP {r.status_code}: {r.text[:300]}")
            d = r.json()
            cols = [h["name"] for h in d.get("columnHeaders", [])]
            return {"columns": cols, "rows": [dict(zip(cols, row)) for row in d.get("rows", [])]}
        return {"columns": [], "rows": []}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def next_slots(n: int, hours: list[int], taken: list[str], start: datetime | None = None) -> list[str]:
    """投稿枠 (JST の時刻リスト) から、まだ埋まっていない直近の枠を n 個返す (ISO8601)。"""
    from datetime import timedelta
    start = start or datetime.now(JST) + timedelta(minutes=60)
    out, day = [], start.replace(minute=0, second=0, microsecond=0)
    taken_set = set(t[:13] for t in taken if t)
    for d in range(0, 30):
        base = (day + timedelta(days=d))
        for h in sorted(hours):
            t = base.replace(hour=h)
            if t <= start:
                continue
            iso = t.isoformat()
            if iso[:13] in taken_set:
                continue
            out.append(iso)
            if len(out) >= n:
                return out
    return out
