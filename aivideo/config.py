"""設定の読み込み。APIキーは環境変数または .env からのみ読み込み、ソースコードには書かない。"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WIDTH, HEIGHT, FPS = 1920, 1080, 30
SAMPLE_RATE = 48000


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """依存ライブラリなしの最小 .env ローダー（既存の環境変数を優先）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


_FONT_CANDIDATES = [
    # Linux
    "Noto Sans CJK JP:style=Bold", "Noto Sans JP:style=Bold", "Noto Sans CJK JP",
    "IPAexGothic", "IPAGothic", "TakaoGothic", "VL Gothic",
    # macOS / Windows
    "Hiragino Sans:style=W6", "Hiragino Kaku Gothic ProN", "Yu Gothic:style=Bold",
    "Meiryo", "MS Gothic",
]


def find_japanese_font() -> tuple[str, str]:
    """(フォントファイルパス, フォントファミリー名) を返す。"""
    override = env("AIVIDEO_FONT")
    if override and Path(override).exists():
        return override, Path(override).stem
    if shutil.which("fc-match"):
        for cand in _FONT_CANDIDATES:
            try:
                out = subprocess.run(
                    ["fc-match", "-f", "%{file}|%{family[0]}", cand],
                    capture_output=True, text=True, timeout=10,
                ).stdout
            except Exception:
                continue
            if "|" in out:
                path, fam = out.split("|", 1)
                if cand.split(":")[0].lower() in fam.lower() and Path(path).exists():
                    return path, fam
    for p in [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothB.ttc",
    ]:
        if Path(p).exists():
            return p, Path(p).stem
    raise RuntimeError(
        "日本語フォントが見つかりません。Ubuntu: sudo apt install fonts-noto-cjk / "
        "または AIVIDEO_FONT にフォントファイルのパスを設定してください。"
    )


@dataclass
class Settings:
    llm: str = "auto"
    visuals: str = "auto"
    tts: str = "auto"
    allow_paid: bool = False
    claude_model: str = "claude-opus-5-5"
    voicevox_url: str = "http://127.0.0.1:50021"
    voicevox_speaker: int = 13
    tts_speed: float = 1.1
    font_path: str = ""
    font_family: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        fp, ff = find_japanese_font()
        return cls(
            llm=env("AIVIDEO_LLM", "auto"),
            visuals=env("AIVIDEO_VISUALS", "auto"),
            tts=env("AIVIDEO_TTS", "auto"),
            allow_paid=env("AIVIDEO_ALLOW_PAID", "0") in ("1", "true", "yes"),
            claude_model=env("AIVIDEO_CLAUDE_MODEL", "claude-opus-5-5"),
            voicevox_url=env("VOICEVOX_URL", "http://127.0.0.1:50021"),
            voicevox_speaker=int(env("VOICEVOX_SPEAKER", "13") or 13),
            tts_speed=float(env("AIVIDEO_TTS_SPEED", "1.1") or 1.1),
            font_path=fp,
            font_family=ff,
        )


def log(msg: str) -> None:
    print(f"[aivideo] {msg}", flush=True)
