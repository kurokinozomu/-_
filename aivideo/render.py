"""FFmpeg による映像編集。

1. 各シーン画像を、カメラワーク (ズーム/パン) 付きの動画クリップに変換
2. xfade で場面転換をつけて結合し、ASS 字幕を焼き込み、音声 (ラウドネス正規化) と合わせて MP4 に書き出す
"""
from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import FPS, HEIGHT, WIDTH, log

ZMAX = 1.16  # ズーム量


def check_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError(
            "FFmpeg が見つかりません。インストールしてください:\n"
            "  Ubuntu/Debian: sudo apt install ffmpeg\n"
            "  macOS: brew install ffmpeg\n"
            "  Windows: winget install Gyan.FFmpeg")


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd)[:600]}\n{proc.stderr[-2500:]}")


def _camera_expr(camera: str, frames: int) -> tuple[str, str, str]:
    n = max(1, frames - 1)
    # 緩やかなイージング (線形 70% + コサイン 30%)
    p = f"(0.7*min(on/{n},1)+0.3*(1-cos(PI*min(on/{n},1)))/2)"
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    if camera == "zoom_in":
        return f"1+{ZMAX - 1}*{p}", cx, cy
    if camera == "zoom_out":
        return f"{ZMAX}-{ZMAX - 1}*{p}", cx, cy
    if camera == "pan_left":
        return f"{ZMAX}", f"(iw-iw/zoom)*(1-{p})", cy
    if camera == "pan_right":
        return f"{ZMAX}", f"(iw-iw/zoom)*{p}", cy
    if camera == "pan_up":
        return f"{ZMAX}", cx, f"(ih-ih/zoom)*(1-{p})"
    if camera == "pan_down":
        return f"{ZMAX}", cx, f"(ih-ih/zoom)*{p}"
    return "1.0", cx, cy


def render_scene_clip(image: Path, out: Path, duration: float, camera: str) -> None:
    frames = int(round(duration * FPS))
    z, x, y = _camera_expr(camera, frames)
    vf = (f"scale={WIDTH * 2}:{HEIGHT * 2}:flags=lanczos,"
          f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={WIDTH}x{HEIGHT}:fps={FPS},"
          f"format=yuv420p,setsar=1")
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(image),
         "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "16", "-r", str(FPS), str(out)])


def render_clips(jobs: list[tuple[Path, Path, float, str]], workers: int = 3) -> None:
    done = 0

    def one(job):
        render_scene_clip(*job)
        return job[1]

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in ex.map(one, jobs):
            done += 1
            if done % 5 == 0 or done == len(jobs):
                log(f"  シーン映像 {done}/{len(jobs)}")


def _escape_filter_path(p: Path) -> str:
    s = str(p.resolve()).replace("\\", "/")
    return s.replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")


def assemble(clips: list[Path], durations: list[float], transitions: list[str], trans_dur: float,
             audio: Path, ass: Path, font_path: str, out: Path, total: float) -> None:
    """xfade で全クリップをつなぎ、字幕と音声を合わせて書き出す。"""
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    inputs += ["-i", str(audio)]

    parts = []
    last = "[0:v]"
    offset = 0.0
    for k in range(1, len(clips)):
        offset += durations[k - 1] - trans_dur
        lbl = f"[v{k}]"
        parts.append(f"{last}[{k}:v]xfade=transition={transitions[k]}:duration={trans_dur}:"
                     f"offset={offset:.3f}{lbl}")
        last = lbl
    fontsdir = _escape_filter_path(Path(font_path).parent)
    parts.append(f"{last}ass='{_escape_filter_path(ass)}':fontsdir='{fontsdir}',"
                 f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0, total - 0.8):.3f}:d=0.8,format=yuv420p[vout]")
    parts.append(f"[{len(clips)}:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    filt = ";\n".join(parts)
    script = out.with_suffix(".filter.txt")
    script.write_text(filt, encoding="utf-8")
    log("最終書き出し中 (場面転換・字幕・音声)...")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt,
         "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
         "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)])


def probe(path: Path) -> dict:
    import json
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    return json.loads(out)
