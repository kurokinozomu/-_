"""python -m unittest discover tests  (E2E も含めるには AIVIDEO_E2E=1)"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aivideo import audio, subtitles  # noqa: E402
from aivideo.__main__ import parse_request  # noqa: E402
from aivideo.planner import all_scenes, offline_plan  # noqa: E402


class ParseTest(unittest.TestCase):
    def test_requests(self):
        self.assertEqual(parse_request("宇宙の謎というテーマで8分の動画を作って"), ("宇宙の謎", 480.0))
        self.assertEqual(parse_request("睡眠の科学について30秒の動画"), ("睡眠の科学", 30.0))
        self.assertEqual(parse_request("テーマ：深海生物で1分30秒の動画を作って"), ("深海生物", 90.0))
        self.assertEqual(parse_request("もしもオナラが1秒ごとに2倍臭くなったらというテーマでショート動画を作って"),
                         ("もしもオナラが1秒ごとに2倍臭くなったら", None))
        self.assertEqual(parse_request("猫の不思議 3分"), ("猫の不思議", 180.0))


class SubtitleTest(unittest.TestCase):
    def test_wrap_and_chunk(self):
        s = "太陽の光は七色の光が混ざり合ったもので、その中でも青い光は空気の粒にぶつかって散らばりやすい性質を持っているのです"
        parts = subtitles.chunk(s)
        self.assertEqual("".join(parts), s)
        for p in parts:
            self.assertLessEqual(len(p), subtitles.EVENT_MAX)
            for line in subtitles.wrap(p).split("\\N"):
                self.assertLessEqual(len(line), subtitles.LINE_MAX + 2)

    def test_vertical_line_length(self):
        subtitles.configure(True)
        try:
            for line in subtitles.wrap("江戸の庶民は昼すぎには仕事を終えていたんです").split("\\N"):
                self.assertLessEqual(len(line), subtitles.LINE_MAX + 2)
        finally:
            subtitles.configure(False)

    def test_no_break_inside_number(self):
        subtitles.configure(True)
        try:
            w = subtitles.wrap("1分後、オナラが115京倍臭くなったら？")
            self.assertIn("115京倍", w.replace("\\N", "|").split("|")[-1] + w.split("\\N")[0])
        finally:
            subtitles.configure(False)

    def test_events_cover_sentence_time(self):
        ev = subtitles.build_events([("短い文です。", 1.0, 2.0), ("次の文。", 2.5, 3.5)])
        self.assertAlmostEqual(ev[0][1], 1.0)
        self.assertAlmostEqual(ev[-1][2], 3.5)


class PlanTest(unittest.TestCase):
    def test_offline_plan_scales_with_length(self):
        short = all_scenes(offline_plan("テスト", 30))
        long = all_scenes(offline_plan("テスト", 480))
        self.assertGreater(len(long), len(short))
        self.assertTrue(all(s["narration"] for s in long))
        self.assertEqual(len({s["id"] for s in long}), len(long))


class AudioTest(unittest.TestCase):
    def test_mix_length_and_range(self):
        import numpy as np
        voice = np.sin(np.linspace(0, 2000, 48000)).astype("float32") * 0.5
        out = audio.mix(5.0, [(1.0, voice)], [(0.5, "whoosh"), (2.0, "chime")], "upbeat")
        self.assertEqual(out.shape, (5 * 48000, 2))
        self.assertLessEqual(float(abs(out).max()), 1.0)


@unittest.skipUnless(os.environ.get("AIVIDEO_E2E"), "set AIVIDEO_E2E=1 to run the end-to-end render")
class EndToEndTest(unittest.TestCase):
    def test_offline_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, "-m", "aivideo", "テスト動画", "--seconds", "20",
                            "--llm", "offline", "--visuals", "procedural", "--tts", "openjtalk",
                            "--out", tmp], cwd=ROOT, check=True)
            d = next(Path(tmp).iterdir())
            info = json.loads(subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                 str(d / "video.mp4")], capture_output=True, text=True).stdout)
            v = next(s for s in info["streams"] if s["codec_type"] == "video")
            self.assertEqual((v["width"], v["height"]), (1920, 1080))
            self.assertTrue(any(s["codec_type"] == "audio" for s in info["streams"]))
            for f in ("thumbnail.png", "metadata.md", "subtitles.srt", "plan.json"):
                self.assertTrue((d / f).exists(), f)


if __name__ == "__main__":
    unittest.main()
