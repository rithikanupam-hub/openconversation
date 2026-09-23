"""LingoSync pipeline: ASR (mlx-whisper) -> translation -> voice-cloned TTS (mlx-audio).

Everything runs locally on Apple Silicon via MLX. Models are loaded lazily and
cached. All heavy calls go through one lock because MLX models are not safe to
drive from several threads at once.
"""
from __future__ import annotations

import difflib
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

# ASR: NVIDIA Parakeet TDT v3 (fast, 25 European languages, no silence hallucinations) by default;
# Whisper is used for languages Parakeet does not cover, or everywhere with LINGOSYNC_ASR=whisper.
ASR_ENGINE = os.environ.get("LINGOSYNC_ASR", "parakeet")
PARAKEET_MODEL = os.environ.get("LINGOSYNC_PARAKEET_MODEL", "mlx-community/parakeet-tdt-0.6b-v3")
ASR_MODEL = os.environ.get("LINGOSYNC_ASR_MODEL", "mlx-community/whisper-large-v3-turbo")
PARAKEET_LANGS = {"bg", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "de", "el", "hu", "it", "lv", "lt",
                  "mt", "pl", "pt", "ro", "sk", "sl", "es", "sv", "ru", "uk"}
# Below this confidence that a line is English (the listener's language) we still translate it.
NATIVE_MIN_CONF = 0.3
SR16 = 16_000
# The locked voice is kept here so it survives reconnects and server restarts until "Reset voice",
# a new "Start listening", or consent being withdrawn (all of which delete it).
VOICE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "voice.wav")

LANGUAGES = [
    ("auto", "Auto-detect"), ("it", "Italian"), ("en", "English"), ("es", "Spanish"),
    ("fr", "French"), ("de", "German"), ("pt", "Portuguese"), ("nl", "Dutch"),
    ("pl", "Polish"), ("ro", "Romanian"), ("tr", "Turkish"), ("ru", "Russian"),
    ("uk", "Ukrainian"), ("ar", "Arabic"), ("hi", "Hindi"), ("zh", "Chinese"),
    ("ja", "Japanese"), ("ko", "Korean"),
]

ENGINES = {
    "pocket_tts": {
        "label": "Pocket TTS (clone, English out, faster than real time)",
        "repo": os.environ.get("LINGOSYNC_POCKET_MODEL", "mlx-community/pocket-tts-4bit"),
        "clones": True,
        "targets": ["en"],
    },
    "chatterbox_turbo": {
        "label": "Chatterbox Turbo (clone, English out, richer but slower)",
        "repo": os.environ.get("LINGOSYNC_CHATTERBOX_MODEL", "mlx-community/chatterbox-turbo-4bit"),
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
    r"grazie per la visione|thanks for watching|thank you for watching)",
    re.I,
)
# Whole-utterance phrases Whisper invents from background noise (seen live: "Grazie.", "Grazie a tutti.").
_NOISE_PHRASES = re.compile(r"^(grazie( a tutti| mille)?|thank you( all)?|thanks|merci|danke|gracias|obrigad[oa]|"
                            r"ciao|you|bye)$", re.I)


def _junk(text: str) -> bool:
    """True for transcripts that are not worth translating: no words, one letter, bare filler."""
    words = re.findall(r"\w+", text)
    return not words or (len(words) == 1 and len(words[0]) <= 1)


def _same_text(a: str, b: str) -> bool:
    norm = lambda t: re.sub(r"[^\w\s]", "", t.lower()).split()
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() >= 0.8


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
    """Reference audio for zero-shot cloning of the current speaker.

    While collecting, clips are stacked newest first and looped to satisfy
    Chatterbox's > 5 s assertion. Once `lock_seconds` of real speech is
    gathered the voice is locked: the reference is frozen, and each engine's
    conditioning is computed from it once and reused until `clear()` ("Reset voice").
    """
    clips: list = field(default_factory=list)  # newest first, 16 kHz float32
    max_seconds: float = 12.0
    lock_seconds: float = 6.0
    locked_ref: np.ndarray | None = None  # frozen 16 kHz reference once locked
    conds: dict = field(default_factory=dict)  # engine -> cached conditioning for locked_ref
    last_lang: str | None = None  # the foreign language this conversation has been in

    @property
    def seconds(self) -> float:
        return sum(len(c) for c in self.clips) / SR16

    @property
    def locked(self) -> bool:
        return self.locked_ref is not None

    def add(self, clip: np.ndarray) -> None:
        if self.locked:
            return
        self.clips.insert(0, clip)
        total = 0.0
        kept = []
        for c in self.clips:
            kept.append(c)
            total += len(c) / SR16
            if total >= self.max_seconds:
                break
        self.clips = kept

    def ready_to_lock(self) -> bool:
        return not self.locked and self.seconds >= self.lock_seconds

    def lock(self) -> None:
        self.locked_ref = self.reference()
        log.info("Voice locked from %.1fs of speech", self.seconds)
        try:
            os.makedirs(os.path.dirname(VOICE_FILE), exist_ok=True)
            sf.write(VOICE_FILE, self.locked_ref, SR16)
        except OSError as e:
            log.warning("Could not save the locked voice: %s", e)

    @classmethod
    def restore(cls) -> "VoiceProfile":
        """The profile saved by an earlier lock, or an empty one."""
        prof = cls()
        if os.path.exists(VOICE_FILE):
            try:
                ref, sr = sf.read(VOICE_FILE, dtype="float32")
                prof.clips = [ref if sr == SR16 else _resample(ref, sr, SR16)]
                prof.locked_ref = prof.clips[0]
                log.info("Restored locked voice (%.1fs)", prof.seconds)
            except Exception as e:  # noqa: BLE001 - unreadable file: start fresh
                log.warning("Ignoring unreadable saved voice: %s", e)
        return prof

    def reference(self, min_seconds: float = 5.5) -> np.ndarray | None:
        if self.locked_ref is not None:
            return self.locked_ref
        if not self.clips:
            return None
        ref = np.concatenate(self.clips)
        if len(ref) / SR16 < min_seconds:
            # loop the audio to satisfy the length assertion; timbre is preserved
            reps = int(np.ceil(min_seconds * SR16 / len(ref)))
            ref = np.tile(ref, reps)
        return ref

    def state(self) -> dict:
        return {"type": "voice", "state": "locked" if self.locked else "collecting",
                "seconds": round(self.seconds, 1),
                "needed": self.lock_seconds}

    def clear(self) -> None:
        self.clips = []
        self.locked_ref = None
        self.conds = {}
        self.last_lang = None
        try:
            os.remove(VOICE_FILE)
        except FileNotFoundError:
            pass


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
        self._parakeet_model = None
        self._lid = None

    # ---------------------------------------------------------------- ASR
    def _parakeet(self, audio16: np.ndarray) -> str:
        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel

        if self._parakeet_model is None:
            from parakeet_mlx import from_pretrained
            log.info("Loading Parakeet ASR (%s)", PARAKEET_MODEL)
            self._parakeet_model = from_pretrained(PARAKEET_MODEL)
        m = self._parakeet_model
        return m.generate(get_logmel(mx.array(audio16), m.preprocessor_config))[0].text.strip()

    def _detect_lang(self, text: str, hint: str | None = None) -> tuple[str, float]:
        """Language of a transcript (Parakeet gives none). Returns (code, P(english)).

        Short fragments are ambiguous ("Campania." scored Romanian), so for <= 3 words the
        conversation's current language wins whenever it is at all plausible.
        """
        if self._lid is None:
            from lingua import IsoCode639_1, LanguageDetectorBuilder
            # lingua lacks a few (e.g. Maltese); those are simply not candidates
            codes = [getattr(IsoCode639_1, c.upper()) for c in sorted(PARAKEET_LANGS) if hasattr(IsoCode639_1, c.upper())]
            self._lid = LanguageDetectorBuilder.from_iso_codes_639_1(*codes).with_preloaded_language_models().build()
        conf = self._lid.compute_language_confidence_values(text)
        if not conf:
            return hint or "en", 0.0
        score = {c.language.iso_code_639_1.name.lower(): c.value for c in conf}
        best = conf[0].language.iso_code_639_1.name.lower()
        if hint and hint != best and len(text.split()) <= 3 and score.get(hint, 0.0) >= 0.05:
            best = hint
        elif best not in ("en", hint) and (len(text.split()) < 4 or score[best] < 0.6):
            # Unsure about a language we haven't heard yet (e.g. "Um" scored Latvian and triggered a
            # mid-meeting package download): stay with the conversation's language instead.
            best = hint or best
        return best, score.get("en", 0.0)

    def transcribe(self, audio16: np.ndarray, source_lang: str, target_lang: str,
                   hint: str | None = None) -> tuple[str | None, str]:
        """Returns (text or None if nothing worth translating, language code)."""
        use_parakeet = ASR_ENGINE == "parakeet" and (source_lang == "auto" or source_lang in PARAKEET_LANGS)
        if use_parakeet:
            text = self._parakeet(audio16)
            if not text or _junk(text):
                return None, source_lang
            if source_lang != "auto":
                return text, source_lang
            lang, p_target = self._detect_lang(text, hint)
            if target_lang == "en" and p_target >= NATIVE_MIN_CONF:
                lang = "en"  # mixed or unsure lines lean towards "already understood": stay silent
            return text, lang
        res = self._whisper(audio16, task="transcribe", language=source_lang)
        text = self._clean(res)
        lang = res.get("language") or (source_lang if source_lang != "auto" else "en")
        if text and (_junk(text) or _NOISE_PHRASES.match(re.sub(r"[^\w\s]", "", text).strip())):
            log.info("Dropping likely Whisper noise hallucination: %r", text)
            text = None
        return text, lang

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
        logging.getLogger("argostranslate.utils").setLevel(logging.WARNING)  # re-set: it logs every token

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

    def _chatterbox_conds(self, model, profile: VoiceProfile | None, sr: int) -> dict:
        """Returns generate() kwargs for Chatterbox, using/locking the profile's cached conditionals."""
        if profile is None or not profile.clips:
            return {}  # model's built-in default voice
        if profile.ready_to_lock():
            profile.lock()
        if profile.locked:
            if "chatterbox_turbo" not in profile.conds:
                t = time.time()
                model.prepare_conditionals(_resample(profile.locked_ref, SR16, sr), sample_rate=sr)
                profile.conds["chatterbox_turbo"] = model._conds
                log.info("Chatterbox conditionals ready (%.0f ms)", (time.time() - t) * 1000)
            model._conds = profile.conds["chatterbox_turbo"]
            return {}
        return {"ref_audio": _resample(profile.reference(), SR16, sr), "sample_rate": sr}

    def synthesize(self, text: str, lang: str, engine: str, profile: VoiceProfile | None,
                   ref_text: str | None, on_chunk=None) -> tuple[np.ndarray, int]:
        """Synthesises `text`. If `on_chunk(audio, sr)` is given, audio is streamed to it as it is made."""
        model = self._load_tts(engine)
        sr = int(getattr(model, "sample_rate", 24_000))
        kwargs: dict = {}
        if engine == "chatterbox_turbo":
            kwargs.update(self._chatterbox_conds(model, profile, sr))
            kwargs.update(max_tokens=800)
            if on_chunk:
                kwargs.update(stream=True, streaming_interval=1.0)
        elif engine == "pocket_tts":
            import mlx.core as mx
            if profile is not None and profile.clips:
                if profile.ready_to_lock():
                    profile.lock()
                key = "pocket_tts"
                ref = profile.conds.get(key) if profile.locked else None
                if ref is None:
                    ref = mx.array(_resample(profile.reference(), SR16, sr))
                    if profile.locked:
                        profile.conds[key] = ref
                kwargs["ref_audio"] = ref
            if on_chunk:
                kwargs.update(stream=True, streaming_interval=1.0)
        elif engine == "qwen3_tts":
            ref16 = profile.reference() if profile is not None else None
            if ref16 is not None:
                kwargs["ref_audio"] = _resample(ref16, SR16, sr)
                kwargs["ref_text"] = ref_text
            kwargs.update(lang_code=lang if lang else "auto", verbose=False)
        elif engine == "kokoro":
            kwargs.update(voice="af_heart", lang_code=KOKORO_LANG.get(lang, "a"))
        chunks = []
        for seg in model.generate(text, **kwargs):
            a = np.asarray(seg.audio, dtype=np.float32).reshape(-1)
            sr = int(getattr(seg, "sample_rate", sr) or sr)
            if on_chunk:
                # chunks are played as they arrive, so clip rather than normalise the whole take
                a = np.clip(a, -0.98, 0.98)
                on_chunk(a, sr)
            chunks.append(a)
        if not chunks:
            raise RuntimeError("TTS produced no audio")
        audio = np.concatenate(chunks)
        peak = float(np.max(np.abs(audio)) or 1.0)
        if peak > 0.98:
            audio = audio / peak * 0.95
        return audio, sr

    # ------------------------------------------------------------ pipeline
    def keep_warm(self, engine: str) -> None:
        """A tiny pass through every stage so macOS doesn't page the models out while idle.

        After 25 idle minutes the first sentence spent 29.5 s in ASR (language detector and
        Parakeet paged out), and everything said meanwhile piled up behind it.
        """
        if not self.lock.acquire(blocking=False):
            return  # real work is running; that keeps things warm anyway
        try:
            rng = np.random.default_rng()
            if ASR_ENGINE == "parakeet":
                self._parakeet((rng.standard_normal(SR16) * 1e-3).astype(np.float32))
                self._detect_lang("buongiorno a tutti")
            try:
                self._argos("Ciao", "it", "en")
            except Exception:  # noqa: BLE001
                pass
            self.synthesize("Hi.", "en", engine, None, None)
        finally:
            self.lock.release()

    def warmup(self, engine: str) -> None:
        import mlx.core as mx

        # Pin model memory in RAM. On a 16 GB Mac under swap, idle model buffers were paged out
        # (1.5 GB of GPU buffers swapped), making each sentence's TTS 5-8x slower than benchmarks.
        wired_gb = float(os.environ.get("LINGOSYNC_WIRED_GB", "4"))
        if wired_gb > 0:
            try:
                mx.set_wired_limit(int(wired_gb * 2**30))
                log.info("Pinned up to %.1f GB of model memory", wired_gb)
            except Exception as e:  # noqa: BLE001 - older macOS / MLX
                log.warning("Could not pin model memory: %s", e)
        with self.lock:
            t = time.time()
            if ASR_ENGINE == "parakeet":
                self._parakeet(np.zeros(SR16, np.float32))
                self._detect_lang("warm up the language detector")
            else:
                self._whisper(np.zeros(SR16, np.float32), task="transcribe", language="en")
            log.info("ASR (%s) ready in %.1fs", ASR_ENGINE, time.time() - t)
            t = time.time()
            try:
                self._argos("Buongiorno", "it", "en")  # first translation otherwise costs ~2 s
            except Exception as e:  # noqa: BLE001 - offline without the package is fine
                log.warning("Argos warmup skipped: %s", e)
            log.info("Translation ready in %.1fs", time.time() - t)
            t = time.time()
            self._load_tts(engine)
            # One real generation compiles the kernels; otherwise the first sentence pays 2-5 s.
            self.synthesize("Ready.", "en", engine, None, None)
            log.info("TTS %s ready in %.1fs", engine, time.time() - t)

    def run(self, audio16: np.ndarray, source_lang: str, target_lang: str, engine: str,
            clone: bool, profile: VoiceProfile, on_transcript=None, on_translation=None,
            on_chunk=None) -> Result:
        """Runs one utterance. Callbacks fire as each stage finishes so the UI can update early.

        With `on_chunk(audio, sr)` set, TTS audio is streamed and Result.audio_wav is None.
        """
        timings: dict = {}
        with self.lock:
            t0 = time.time()
            text, detected = self.transcribe(audio16, source_lang, target_lang, profile.last_lang)
            timings["asr_ms"] = int((time.time() - t0) * 1000)
            if not text:
                return Result("", detected, None, target_lang, None, 0, timings, skipped="no_speech")
            if on_transcript:
                on_transcript(text, detected)

            if detected == target_lang:
                # Listener already understands this; no translation or TTS needed.
                return Result(text, detected, text, target_lang, None, 0, timings, skipped="same_language")

            t0 = time.time()
            target = self.translate(text, detected, target_lang, audio16)
            timings["mt_ms"] = int((time.time() - t0) * 1000)
            if _same_text(text, target):
                # Whisper often mislabels short English as it/es/...; "translating" it changes nothing.
                log.info("Treating %s utterance as %s (translation unchanged): %r", detected, target_lang, text)
                return Result(text, target_lang, text, target_lang, None, 0, timings, skipped="same_language")

            profile.last_lang = detected
            # Learn the voice only from foreign speech, so the listener's own voice never leaks in.
            cloning = clone and ENGINES[engine]["clones"]
            if cloning:
                profile.add(audio16)
            if on_translation:
                on_translation(target, dict(timings))

            t0 = time.time()
            first = {}

            def chunk(a, sr):
                first.setdefault("ms", int((time.time() - t0) * 1000))
                on_chunk(a, sr)

            audio, sr = self.synthesize(target, target_lang, engine, profile if cloning else None,
                                        text if cloning else None, chunk if on_chunk else None)
            timings["tts_ms"] = int((time.time() - t0) * 1000)
            if "ms" in first:
                timings["tts_first_ms"] = first["ms"]
            wav = None if on_chunk else wav_bytes(audio, sr)
            return Result(text, detected, target, target_lang, wav, sr, timings)


pipeline = Pipeline()
