"""日本語音声合成。文ごとに合成して、字幕の正確なタイミングを得る。

エンジン (AIVIDEO_TTS=auto):
  - VOICEVOX : 無料・高品質。ローカルで VOICEVOX ENGINE を起動している場合に使用。
               (利用規約によりクレジット表記が必要。metadata に自動で記載します)
  - OpenJTalk: 無料・完全オフライン (pyopenjtalk-plus)。
"""
from __future__ import annotations

import hashlib
import io
import re
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests

from .config import SAMPLE_RATE, Settings, log

SENT_GAP = 0.18  # 文と文の間の無音 (秒)


@dataclass
class Spoken:
    audio: np.ndarray              # float32, mono, SAMPLE_RATE
    sentences: list[tuple[str, float, float]]  # (表示テキスト, 開始秒, 終了秒)

    @property
    def duration(self) -> float:
        return len(self.audio) / SAMPLE_RATE


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    parts = re.findall(r"[^。！？!?]+[。！？!?」』]*", text)
    return [p.strip() for p in parts if p.strip(" 。、")]


def _resample(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SAMPLE_RATE:
        return x
    n = int(len(x) * SAMPLE_RATE / sr)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def _trim(x: np.ndarray, thresh: float = 0.01) -> np.ndarray:
    idx = np.where(np.abs(x) > thresh)[0]
    if len(idx) == 0:
        return x
    pad = int(0.03 * SAMPLE_RATE)
    return x[max(0, idx[0] - pad): idx[-1] + pad]


class OpenJTalkTTS:
    name = "openjtalk"
    credit = "音声: Open JTalk (HTS voice)"

    def __init__(self, speed: float):
        import pyopenjtalk
        self._pj = pyopenjtalk
        self.speed = speed

    def synth(self, text: str) -> np.ndarray:
        x, sr = self._pj.tts(text, speed=self.speed)
        return _resample((x / 32768.0).astype(np.float32), sr)


class VoicevoxTTS:
    name = "voicevox"

    def __init__(self, url: str, speaker: int, speed: float):
        self.url, self.speaker, self.speed = url.rstrip("/"), speaker, speed
        self.credit = f"音声: VOICEVOX (speaker id {speaker})"
        try:
            for sp in requests.get(f"{self.url}/speakers", timeout=5).json():
                for st in sp.get("styles", []):
                    if st.get("id") == speaker:
                        self.credit = f"VOICEVOX:{sp['name']}"
        except Exception:
            pass

    @staticmethod
    def available(url: str) -> bool:
        try:
            return requests.get(f"{url.rstrip('/')}/version", timeout=2).ok
        except Exception:
            return False

    def synth(self, text: str) -> np.ndarray:
        q = requests.post(f"{self.url}/audio_query", params={"text": text, "speaker": self.speaker},
                          timeout=60)
        q.raise_for_status()
        query = q.json()
        query["speedScale"] = self.speed
        query["outputSamplingRate"] = SAMPLE_RATE
        r = requests.post(f"{self.url}/synthesis", params={"speaker": self.speaker},
                          json=query, timeout=120)
        r.raise_for_status()
        with wave.open(io.BytesIO(r.content)) as w:
            sr = w.getframerate()
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            if w.getnchannels() == 2:
                data = data.reshape(-1, 2).mean(axis=1)
        return _resample((data / 32768.0).astype(np.float32), sr)


def get_tts(settings: Settings):
    if settings.tts in ("auto", "voicevox") and VoicevoxTTS.available(settings.voicevox_url):
        log("音声合成: VOICEVOX")
        return VoicevoxTTS(settings.voicevox_url, settings.voicevox_speaker,
                           1.0 + (settings.tts_speed - 1.0) * 0.8)
    if settings.tts == "voicevox":
        log("VOICEVOX ENGINE に接続できません。Open JTalk を使用します。")
    log("音声合成: Open JTalk (オフライン)")
    return OpenJTalkTTS(settings.tts_speed)


class Narrator:
    def __init__(self, engine, cache_dir: Path):
        self.engine = engine
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)

    def _sentence(self, text: str) -> np.ndarray:
        key = hashlib.sha1(f"{self.engine.name}|{getattr(self.engine, 'speaker', '')}|"
                           f"{self.engine.speed}|{text}".encode()).hexdigest()[:20]
        f = self.cache / f"{key}.npy"
        if f.exists():
            return np.load(f)
        x = _trim(self.engine.synth(text))
        np.save(f, x)
        return x

    def speak(self, narration: str) -> Spoken:
        chunks, sents, t = [], [], 0.0
        gap = np.zeros(int(SENT_GAP * SAMPLE_RATE), dtype=np.float32)
        for i, s in enumerate(split_sentences(narration)):
            x = self._sentence(s)
            if i:
                chunks.append(gap)
                t += SENT_GAP
            chunks.append(x)
            d = len(x) / SAMPLE_RATE
            sents.append((s, t, t + d))
            t += d
        audio = np.concatenate(chunks) if chunks else np.zeros(SAMPLE_RATE, dtype=np.float32)
        return Spoken(audio, sents)
