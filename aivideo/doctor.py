"""実行環境のチェック: python -m aivideo --check"""
from __future__ import annotations

import os
import shutil
import subprocess

from .config import find_japanese_font, load_dotenv


def check() -> int:
    load_dotenv()
    ok_all = True

    def row(ok, name, detail, fix=""):
        nonlocal ok_all
        mark = "OK " if ok else ("-- " if ok is None else "NG ")
        print(f"[{mark}] {name}: {detail}")
        if fix and not ok:
            print(f"       → {fix}")
        if ok is False:
            ok_all = False

    print("=== aivideo 環境チェック ===")
    ff = shutil.which("ffmpeg")
    libass = False
    if ff:
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        libass = " ass " in filters and " xfade " in filters and " zoompan " in filters
    row(bool(ff) and libass, "FFmpeg (必須)", ff or "未インストール",
        "Ubuntu: sudo apt install ffmpeg / macOS: brew install ffmpeg / Windows: winget install Gyan.FFmpeg"
        + ("" if not ff else " (libass・xfade 対応版が必要)"))
    try:
        path, fam = find_japanese_font()
        row(True, "日本語フォント (必須)", f"{fam} ({path})")
    except RuntimeError as e:
        row(False, "日本語フォント (必須)", "見つかりません", str(e))
    try:
        import pyopenjtalk  # noqa: F401
        row(True, "Open JTalk 音声合成 (必須)", "pyopenjtalk 利用可")
    except ImportError:
        row(False, "Open JTalk 音声合成 (必須)", "未インストール", "pip install -r requirements.txt")

    from .tts import VoicevoxTTS
    url = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")
    vv = VoicevoxTTS.available(url)
    row(True if vv else None, "VOICEVOX (任意・高音質)", "起動中" if vv else "未起動 (Open JTalk を使用)",
        "https://voicevox.hiroshiba.jp/ からインストールして起動")

    cl = shutil.which("claude")
    row(True if cl else None, "Claude CLI (推奨・台本作成)", cl or "未インストール",
        "npm install -g @anthropic-ai/claude-code して `claude` でログイン")
    key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    paid = os.environ.get("AIVIDEO_ALLOW_PAID", "0") in ("1", "true", "yes")
    row(None, "Anthropic API (任意・有料)",
        ("キー設定済み" if key else "キー未設定") + (" / 有料利用: 許可" if paid else " / 有料利用: 未許可"))
    if not cl and not (key and paid):
        print("       ※ 台本 AI が使えないため、オフラインのテンプレート台本になります")

    from .visuals import PollinationsProvider
    pol = PollinationsProvider.available()
    row(True if pol else None, "Pollinations AI画像 (任意・無料)",
        "接続可" if pol else "接続不可 (オフライン生成グラフィックを使用)")
    print("=== 結果:", "動画を生成できます" if ok_all else "必須ツールが不足しています", "===")
    return 0 if ok_all else 1
