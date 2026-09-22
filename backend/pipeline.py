"""LingoSync pipeline: ASR (mlx-whisper) -> translation -> voice-cloned TTS (mlx-audio).

Everything runs locally on Apple Silicon via MLX. Models are loaded lazily and
cached. All heavy calls go through one lock because MLX models are not safe to
drive from several threads at once.
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf

log = logging.getLogger("lingosync.pipeline")

ASR_MODEL = os.environ.get("LINGOSYNC_ASR_MODEL", "mlx-community/whisper-large-v3-turbo")
SR16 = 16_000

LANGUAGES = [
    ("auto", "Auto-detect"), ("it", "Italian"), ("en", "English"), ("es", "Spanish"),
    ("fr", "French"), ("de", "German"), ("pt", "Portuguese"), ("nl", "Dutch"),
    ("pl", "Polish"), ("ro", "Romanian"), ("tr", "Turkish"), ("ru", "Russian"),
    ("uk", "Ukrainian"), ("ar", "Arabic"), ("hi", "Hindi"), ("zh", "Chinese"),
    ("ja", "Japanese"), ("ko", "Korean"),
]

ENGINES = {
    "chatterbox_turbo": {
        "label": "Chatterbox Turbo (clone, English out, fastest)",
        "repo": os.environ.get("LINGOSYNC_CHATTERBOX_MODEL", "mlx-community/chatterbox-turbo-fp16"),
        "clones": True,
        "targets": ["en"],
    },
    "qwen3_tts": {
        "label": "Qwen3-TTS 0.6B (clone, multilingual)",
        "repo": os.environ.get("LINGOSYNC_QWEN_MODEL", "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"),
        "clones": True,
        "targets": [],
    },
    "kokoro": {
        "label": "Kokoro (generic voice, no clone, very fast)",
        "repo": "mlx-community/Kokoro-82M-bf16",
        "clones": False,
        "targets": ["en", "it", "es", "fr", "pt", "hi", "ja", "zh"],
    },
}

KOKORO_LANG = {"en": "a", "it": "i", "es": "e", "fr": "f", "pt": "p", "hi": "h", "ja": "j", "zh": "z"}

# Whisper hallucinations on near-silence / noise.
_HALLUCINATIONS = re.compile(
    r"(sottotitoli|sous-titres|subtitles|untertitel|amara\.org|qtss|grazie per aver guardato|"
    r"thanks for watching|thank you for watching)",
    re.I,
)


def wav_bytes(audio: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.asarray(audio, dtype=np.float32), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return audio.astype(np.float32)
    n = int(round(len(audio) * dst / src))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


@dataclass
class VoiceProfile:
    """Rolling reference audio for zero-shot cloning of the current speaker.

    Chatterbox needs > 5 s of reference. We stack the current utterance first
    (so the most recent speaker dominates the encoder window) followed by the
    previous ones until we have enough.
    """
    clips: list = field(default_factory=list)  # newest first, 16 kHz float32
    max_seconds: float = 12.0

    def add(self, clip: np.ndarray) -> None:
        self.clips.insert(0, clip)
        total = 0.0
        kept = []
        for c in self.clips:
            kept.append(c)
            total += len(c) / SR16
            if total >= self.max_seconds:
                break
        self.clips = kept

    def reference(self, min_seconds: float = 5.5) -> np.ndarray | None:
        if not self.clips:
            return None
        ref = np.concatenate(self.clips)
        if len(ref) / SR16 < min_seconds:
            # loop the audio to satisfy the length assertion; timbre is preserved
            reps = int(np.ceil(min_seconds * SR16 / len(ref)))
            ref = np.tile(ref, reps)
        return ref

    def clear(self) -> None:
        self.clips = []


@dataclass
class Result:
    source_text: str
    source_lang: str
    target_text: str | None
    target_lang: str
    audio_wav: bytes | None
    sample_rate: int
    timings: dict
    skipped: str | None = None


class Pipeline:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self._tts_id: str | None = None
        self._tts_model = None
        self._argos_ready: set[tuple[str, str]] = set()

    # ---------------------------------------------------------------- ASR
    def _whisper(self, audio16: np.ndarray, task: str, language: str | None) -> dict:
        import mlx_whisper

        opts = dict(path_or_hf_repo=ASR_MODEL, task=task, fp16=True, temperature=0.0,
                    condition_on_previous_text=False, no_speech_threshold=0.6,
                    logprob_threshold=-1.0, verbose=None)
        if language and language != "auto":
            opts["language"] = language
        return mlx_whisper.transcribe(audio16, **opts)

    @staticmethod
    def _clean(res: dict) -> str | None:
        text = (res.get("text") or "").strip()
        segs = res.get("segments") or []
        if not text or _HALLUCINATIONS.search(text):
            return None
        if segs:
            nsp = float(np.mean([s.get("no_speech_prob", 0.0) for s in segs]))
            if nsp > 0.75:
                return None
        return text

    # ------------------------------------------------------------ translate
    def _argos(self, text: str, src: str, dst: str) -> str:
        import argostranslate.package as pkg
        import argostranslate.translate as tr

        if (src, dst) not in self._argos_ready:
            installed = {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}
            if (src, dst) not in installed:
                log.info("Installing Argos package %s->%s", src, dst)
                pkg.update_package_index()
                avail = [p for p in pkg.get_available_packages() if p.from_code == src and p.to_code == dst]
                if not avail:
                    raise RuntimeError(f"No offline translation package for {src}->{dst}")
                pkg.install_from_path(avail[0].download())
            self._argos_ready.add((src, dst))
        return tr.translate(text, src, dst)

    def translate(self, text: str, src: str, dst: str, audio16: np.ndarray | None) -> str:
        if src == dst:
            return text
        try:
            if src != "en" and dst != "en":
                return self._argos(self._argos(text, src, "en"), "en", dst)  # pivot via English
            return self._argos(text, src, dst)
        except Exception as e:  # noqa: BLE001 - no package / offline
            log.warning("Argos translation failed (%s); falling back to Whisper translate", e)
            if dst == "en" and audio16 is not None:
                out = self._clean(self._whisper(audio16, task="translate", language=src))
                if out:
                    return out
            raise

    # ------------------------------------------------------------------ TTS
    def _load_tts(self, engine: str):
        if self._tts_id == engine and self._tts_model is not None:
            return self._tts_model
        from mlx_audio.tts.utils import load_model

        repo = ENGINES[engine]["repo"]
        log.info("Loading TTS engine %s (%s)", engine, repo)
        self._tts_model = None
        import mlx.core as mx
        mx.clear_cache()
        self._tts_model = load_model(repo)
        self._tts_id = engine
        return self._tts_model

    def synthesize(self, text: str, lang: str, engine: str, ref16: np.ndarray | None,
                   ref_text: str | None) -> tuple[np.ndarray, int]:
        model = self._load_tts(engine)
        sr = int(getattr(model, "sample_rate", 24_000))
        kwargs: dict = {}
        if engine == "chatterbox_turbo":
            if ref16 is not None:
                kwargs["ref_audio"] = _resample(ref16, SR16, sr)
                kwargs["sample_rate"] = sr
            kwargs.update(stream=False, max_tokens=800)
        elif engine == "qwen3_tts":
            if ref16 is not None:
                kwargs["ref_audio"] = _resample(ref16, SR16, sr)
                kwargs["ref_text"] = ref_text
            kwargs.update(lang_code=lang if lang else "auto", verbose=False)
        elif engine == "kokoro":
            kwargs.update(voice="af_heart", lang_code=KOKORO_LANG.get(lang, "a"))
        chunks = []
        for seg in model.generate(text, **kwargs):
            a = np.asarray(seg.audio, dtype=np.float32).reshape(-1)
            chunks.append(a)
            sr = int(getattr(seg, "sample_rate", sr) or sr)
        if not chunks:
            raise RuntimeError("TTS produced no audio")
        audio = np.concatenate(chunks)
        peak = float(np.max(np.abs(audio)) or 1.0)
        if peak > 0.98:
            audio = audio / peak * 0.95
        return audio, sr

    # ------------------------------------------------------------ pipeline
    def warmup(self, engine: str) -> None:
        with self.lock:
            t = time.time()
            self._whisper(np.zeros(SR16, np.float32), task="transcribe", language="en")
            log.info("ASR ready in %.1fs", time.time() - t)
            t = time.time()
            self._load_tts(engine)
            log.info("TTS %s ready in %.1fs", engine, time.time() - t)

    def run(self, audio16: np.ndarray, source_lang: str, target_lang: str, engine: str,
            clone: bool, profile: VoiceProfile, on_transcript=None) -> Result:
        timings: dict = {}
        with self.lock:
            t0 = time.time()
            res = self._whisper(audio16, task="transcribe", language=source_lang)
            timings["asr_ms"] = int((time.time() - t0) * 1000)
            text = self._clean(res)
            detected = res.get("language") or (source_lang if source_lang != "auto" else "en")
            if not text:
                return Result("", detected, None, target_lang, None, 0, timings, skipped="no_speech")
            if on_transcript:
                on_transcript(text, detected)

            if clone and ENGINES[engine]["clones"]:
                profile.add(audio16)

            if detected == target_lang:
                # Listener already understands this; no translation or TTS needed.
                return Result(text, detected, text, target_lang, None, 0, timings, skipped="same_language")

            t0 = time.time()
            target = self.translate(text, detected, target_lang, audio16)
            timings["mt_ms"] = int((time.time() - t0) * 1000)

            t0 = time.time()
            ref = profile.reference() if (clone and ENGINES[engine]["clones"]) else None
            audio, sr = self.synthesize(target, target_lang, engine, ref, text if ref is not None else None)
            timings["tts_ms"] = int((time.time() - t0) * 1000)
            return Result(text, detected, target, target_lang, wav_bytes(audio, sr), sr, timings)


pipeline = Pipeline()
