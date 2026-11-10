"""素材（フォント・絵文字イラスト・音声）の取得とキャッシュ。

- フォント : Google Fonts (SIL Open Font License) を初回に自動ダウンロード
    字幕      … M PLUS Rounded 1c ExtraBold (丸ゴシック。YouTube の字幕で定番)
    サムネ    … Dela Gothic One (極太。サムネイル・テロップで定番)
- イラスト : Noto Emoji (Apache License 2.0) の SVG を初回に自動ダウンロード
- 音声     : HTS Voice "Mei" (CC BY 3.0) をリポジトリに同梱 (assets/voices)
いずれも商用利用・YouTube 投稿が可能なライセンス。
"""
from __future__ import annotations

import io
import json
import tarfile
from functools import lru_cache
from pathlib import Path

import requests

from .config import ROOT, log

CACHE = ROOT / ".cache" / "assets"
VOICES = ROOT / "assets" / "voices"

FONTS = {
    "subtitle": ("MPLUSRounded1c-ExtraBold.ttf", "mplusrounded1c", "Rounded Mplus 1c ExtraBold"),
    "heavy": ("DelaGothicOne-Regular.ttf", "delagothicone", "Dela Gothic One"),
    "rounded_black": ("MPLUSRounded1c-Black.ttf", "mplusrounded1c", "Rounded Mplus 1c Black"),
}
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/{dir}/{file}"
EMOJI_URL = "https://registry.npmjs.org/@iconify-json/noto/-/noto-1.2.10.tgz"


def _download(url: str, timeout: int = 120) -> bytes:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def font(kind: str) -> tuple[str, str] | None:
    """(フォントファイルのパス, ASS 用フォント名)。取得できなければ None。"""
    file, d, name = FONTS[kind]
    path = CACHE / "fonts" / kind / file
    if not path.exists():
        try:
            log(f"フォントをダウンロード中: {file}")
            data = _download(FONT_URL.format(dir=d, file=file))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except Exception as e:
            log(f"フォントを取得できませんでした ({e})。システムのフォントを使います。")
            return None
    return str(path), name


@lru_cache(maxsize=1)
def _emoji_set() -> tuple[dict, dict] | None:
    base = CACHE / "noto-emoji"
    icons, chars = base / "icons.json", base / "chars.json"
    if not icons.exists():
        try:
            log("イラスト素材 (Noto Emoji) をダウンロード中...")
            data = _download(EMOJI_URL, timeout=300)
            base.mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                for name, dest in (("package/icons.json", icons), ("package/chars.json", chars)):
                    dest.write_bytes(tf.extractfile(name).read())
        except Exception as e:
            log(f"イラスト素材を取得できませんでした ({e})。")
            return None
    try:
        import resvg_py  # noqa: F401
    except ImportError:
        log("resvg-py が未インストールのためイラストを使えません: pip install resvg-py")
        return None
    return json.loads(icons.read_text()), json.loads(chars.read_text())


def emoji_available() -> bool:
    return _emoji_set() is not None


def _emoji_name(ch: str, chars: dict, icons: dict) -> str | None:
    ch = ch.strip()
    if not ch:
        return None
    if ch in icons["icons"] or ch in icons.get("aliases", {}):
        return ch  # 名前で指定された場合
    cps = [f"{ord(c):x}" for c in ch]
    for key in ("-".join(cps), "-".join(c for c in cps if c != "fe0f"), cps[0]):
        if key in chars:
            return chars[key]
    return None


def emoji_image(ch: str, size: int):
    """絵文字 1 文字を size×size の RGBA 画像にする。見つからなければ None。"""
    from PIL import Image
    import resvg_py

    es = _emoji_set()
    if not es:
        return None
    icons, chars = es
    name = _emoji_name(ch, chars, icons)
    if not name:
        return None
    alias = icons.get("aliases", {}).get(name)
    ic = icons["icons"].get(name) or (icons["icons"].get(alias["parent"]) if alias else None)
    if not ic:
        return None
    w, h = ic.get("width", icons.get("width", 128)), ic.get("height", icons.get("height", 128))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
           f'width="{size}" height="{size}">{ic["body"]}</svg>')
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
    return Image.open(io.BytesIO(png)).convert("RGBA")


def mei_voice(style: str) -> Path | None:
    p = VOICES / f"mei_{style}.htsvoice"
    return p if p.exists() else None
