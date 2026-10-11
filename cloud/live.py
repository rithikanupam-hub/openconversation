"""Live Italian -> English interpreting for the web app, on one GPU (deployed by cloud/modal_app.py).

Speaks the same WebSocket protocol as backend/server.py, so frontend/ works unchanged:
  browser -> server: binary 16 kHz int16 mic chunks; JSON {type: config|flush|stop|reset_voice|playback|ping}
  server -> browser: hello, status, level, segment (Italian / English text), audio (wav chunks + "age"), voice, error

Pipeline per connection (the same engine that was measured in tests/stack_compare/stream_sim.py):
  mic -> Nemotron streaming recogniser -> Segmenter (punctuation / real pause / comma / deadline)
      -> Translator (short memory, this user only) -> Qwen3-TTS voice, streamed -> browser
The English plays in the speaker's own voice once they have spoken ~12 s AND ticked consent; until then a
neutral voice is used. Their voice profile lives in memory for this connection only and is never saved.
"""
from __future__ import annotations

import asyncio, base64, io, json, logging, os, queue, re, threading, time, uuid
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from asr_stream import LiveNemotron
from mt import Translator
from stream_sim import Segmenter, Player, stretch, trim, RATES
from voice_stream import StreamingVoice

log = logging.getLogger("lingosync.live")
SR = 16000
LOCK_SECONDS = 12.0          # voiced speech needed before the voice is cloned
# what people can speak (Soniox recognises 60+; these are offered in the menu) and what the voice can speak
LANGUAGES = [("auto", "Auto-detect"), ("it", "Italian"), ("en", "English"), ("zh", "Chinese"), ("es", "Spanish"),
             ("ja", "Japanese"), ("fr", "French"), ("de", "German"), ("ko", "Korean"), ("pt", "Portuguese"),
             ("ru", "Russian"), ("nl", "Dutch")]
VOICE_LANGS = {"en": "English", "zh": "Chinese", "es": "Spanish", "ja": "Japanese", "it": "Italian",   # Qwen3-TTS
               "fr": "French", "de": "German", "ko": "Korean", "pt": "Portuguese", "ru": "Russian"}
DEFAULT_VOICE = "default"
# Neutral voices used until a speaker's own voice is ready, matched to the speaker's pitch (owner, 2026-10-01):
# men get a male voice, women a female one. Public-domain LibriVox readers, see cloud/VOICES.md.
NEUTRAL = {"male": "neutral_male", "female": "neutral_female"}
PITCH_MALE, PITCH_FEMALE, PITCH_SPLIT = 145.0, 185.0, 165.0   # Hz: clearly low / clearly high / tie-break
# identity (tuning "identity"): a person's voice is cloned from >= ID_LOCK_S of their clean single-speaker speech
ID_LOCK_S, ID_MIN_RUN_S, ID_MAX_PIECE_S, ID_MIN_SHARE, ID_MAX_REF_S = 8.0, 1.5, 4.0, 0.6, 15.0
ID_OWN_MAX_S = 4.0                                        # own-words fallback: only the last 4 s of paired source
ID_MIN_SPAN_S = 0.5                                       # a shorter word stretch is widened to this, centred on it
ID_MIN_TOK_PER_S = 2.0       # a clone piece needs >= 2 recognised source tokens/s (speech, not pause/noise; 2026-10-04)
ID_TOK_WAIT_S = 6.0          # wait at most this long after a piece for its recognised words, then judge it


class Diarizer:
    """Runs cloud/diar_worker.py (its own transformers in /opt/diar) and hands each chunk's speaker masks to the
    current session. Started on first use and kept for the container's life; reset per listening run."""

    def __init__(self):
        import subprocess, sys
        env = dict(os.environ, PYTHONPATH="/opt/diar", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")   # leave CPUs to TTS
        self.p = subprocess.Popen([sys.executable, "/root/diar_worker.py"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, env=env, bufsize=0)
        self.ready, self.sink = False, None
        self.q = queue.Queue()                            # never block the WebSocket loop on the pipe
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._write, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("ready"):
                self.ready = True
                log.info("diarizer ready (latency %s ms)", m.get("latency_ms"))
            elif self.sink:
                self.sink(m["start"], np.frombuffer(base64.b64decode(m["mask"]), np.uint8))

    def _write(self):
        import struct
        while True:
            kind, payload = self.q.get()
            try:
                self.p.stdin.write(kind + struct.pack("<I", len(payload)) + payload)
            except (BrokenPipeError, OSError):
                return

    def _send(self, kind, payload=b""):
        self.q.put((kind, payload))

    def reset(self, sink):
        self.sink = sink
        self._send(b"R")

    def feed(self, pcm16: bytes):
        self._send(b"A", pcm16)


def pitch_hz(x, sr=SR):
    """Median pitch of the voiced part of x (YIN, ~5 ms for 3 s), or None if there is too little speech."""
    import librosa
    if len(x) < sr // 2:
        return None
    f = librosa.yin(x, fmin=70, fmax=320, sr=sr, frame_length=1024)
    rms = librosa.feature.rms(y=x, frame_length=1024, hop_length=256)[0][:len(f)]
    v = f[:len(rms)][rms > max(0.01, 0.3 * float(np.percentile(rms, 90)))]
    return float(np.median(v)) if len(v) >= 10 else None

# Tuning profiles (LINGOSYNC_TUNING), so a replay of the same meeting can compare them. "baseline" = behaviour
# before 2026-10-01; "v1" = whole-sentence phrases, Soniox low-latency endpointing, English stays silent,
# fillers dropped when behind, speed-ups capped. See research/2026-09-30/06_brainstorm_and_plan.md.
TUNING = {
    "baseline": {"seg": dict(comma_words=1, deadline=4.0, phrase_min=3, use_pause=False),
                 "soniox": {}, "max_rate": 1.3, "filler_backlog": None, "skip_same_language": False, "terms": False},
    "v1": {"seg": dict(comma_words=8, deadline=5.0, phrase_min=3, use_pause=False, quiet_s=1.2, end_quiet_s=0.35),
           "soniox": {"max_endpoint_delay_ms": 1500, "endpoint_latency_adjustment_level": 2,
                      "endpoint_sensitivity": 0.3},
           "max_rate": 1.15, "filler_backlog": 2.5, "skip_same_language": True},
    # id1 = v1 + who-is-speaking from NVIDIA Nemotron-3-Diarization (step 4): clones per diarized person from their
    # clean single-speaker stretches, Soniox labels ignored; unclear phrases get the pitch-matched neutral voice
    "id1": {"seg": dict(comma_words=8, deadline=5.0, phrase_min=3, use_pause=False, quiet_s=1.2, end_quiet_s=0.35),
            "soniox": {"max_endpoint_delay_ms": 1500, "endpoint_latency_adjustment_level": 2,
                       "endpoint_sensitivity": 0.3},
            "max_rate": 1.15, "filler_backlog": 2.5, "skip_same_language": True, "identity": True},
    # v2: wait a little longer before cutting (fuller sentences, ~0.3 s more lag)
    "v2": {"seg": dict(comma_words=10, deadline=6.0, phrase_min=4, use_pause=False, quiet_s=1.6, end_quiet_s=0.6),
           "soniox": {"max_endpoint_delay_ms": 1500, "endpoint_latency_adjustment_level": 2,
                      "endpoint_sensitivity": 0.3},
           "max_rate": 1.15, "filler_backlog": 2.5, "skip_same_language": True},
}
# Agreements and discourse words carry meaning even when the playback queue is late.
FILLER = re.compile(r"^(?:\W*\b(?:u+m+|u+h+|uhm|e+h+|ehm|m+h*|hmm)\b\W*)+$", re.I)


def target_only(languages, target):
    """Unknown or mixed source-language evidence must not silence a translated phrase."""
    return bool(languages) and all(language == target for language in languages)



def load_terms(path="/root/terms.json"):
    """Names and words Soniox should know (cloud/terms.json): {"terms": [...], "general": [...]}."""
    try:
        with open(path) as f:
            t = json.load(f)
    except (OSError, ValueError):
        return {}
    ctx = {k: t[k] for k in ("terms", "general", "text", "translation_terms") if t.get(k)}
    return {"context": ctx} if ctx else {}


class Engine:
    """The three models, loaded once per GPU container and shared by its (single) connection."""

    def __init__(self, default_voice_wav, cache_dir="/tmp/voice_cache", front=None):
        """front: "local" (Nemotron recogniser + Qwen translator on this GPU) or "soniox" (Soniox recognises and
        translates; only the voice runs here). Default from LINGOSYNC_FRONT."""
        t0 = time.time()
        self.front = front or os.environ.get("LINGOSYNC_FRONT", "local")
        self.voice = StreamingVoice(cache_dir=cache_dir, clone_mode="xvec")
        self.voice.add_voice(DEFAULT_VOICE, default_voice_wav)
        here = os.path.dirname(os.path.abspath(default_voice_wav))
        for g, name in NEUTRAL.items():
            self.voice.add_voice(name, os.path.join(here, f"neutral_{g}.wav"))
        self.voice.warmup(DEFAULT_VOICE)                  # captures the CUDA graphs
        pitch_hz(np.zeros(SR, np.float32) + 0.1 * np.sin(np.arange(SR) / 10).astype(np.float32))   # load librosa now
        self.tuning_name = os.environ.get("LINGOSYNC_TUNING", "v1")
        self.tuning = TUNING[self.tuning_name]
        if self.front == "soniox":
            from soniox_front import SonioxFront
            self.mt, self.asr = None, SonioxFront()
            self.asr.pass_language = True
            self.asr.extra_config = {**self.tuning["soniox"], **(load_terms() if self.tuning.get("terms", True) else {})}
        else:
            self.mt = Translator(); self.mt.warmup()
            self.asr = LiveNemotron(lookahead=3)
            self.asr.warmup()
        self.gpu = threading.Lock()                       # one phrase through MT + TTS at a time
        self.diarizer = None                              # started on first use (tuning "identity")
        log.info("engine ready in %.0fs (front: %s, tuning: %s)", time.time() - t0, self.front, self.tuning_name)


class LiveVAD:
    """Speech / silence per 20 ms frame from the incoming mic audio, with a threshold that follows the room."""

    def __init__(self, frame=320):
        self.frame, self.pending, self.voiced, self.rms_hist = frame, np.zeros(0, np.float32), [], []

    def feed(self, x):
        self.pending = np.concatenate([self.pending, x])
        n = len(self.pending) // self.frame
        if not n:
            return 0.0
        f = self.pending[:n * self.frame].reshape(n, self.frame)
        self.pending = self.pending[n * self.frame:]
        rms = np.sqrt((f ** 2).mean(1))
        self.rms_hist = (self.rms_hist + rms.tolist())[-1500:]          # last 30 s
        thr = max(0.004, 0.1 * float(np.percentile(self.rms_hist, 95)))
        self.voiced += (rms > thr).tolist()
        return float(rms.max())

    def silence_before(self, t):
        i = min(int(t / 0.02), len(self.voiced))
        j = i
        while j > 0 and not self.voiced[j - 1]:
            j -= 1
        return (i - j) * 0.02


def wav_b64(audio, sr):
    buf = io.BytesIO()
    sf.write(buf, np.clip(audio, -1, 1), sr, format="WAV", subtype="PCM_16")
    return base64.b64encode(buf.getvalue()).decode()


class LiveSession:
    def __init__(self, ws, engine: Engine, rec=None):
        self.ws, self.e, self.rec = ws, engine, rec       # rec: optional recorder.Recorder (owner testing)
        self.loop = asyncio.get_running_loop()
        self.id = uuid.uuid4().hex[:8]
        self.cfg = {"source_lang": "auto", "target_lang": "en", "engine": "cloud", "clone": False, "consent": False}
        self.history = []                                  # translator memory, this user only
        self.voice_name = DEFAULT_VOICE
        self.voice_lock, self.voice_epoch = threading.RLock(), 0
        self.voice_audio, self.voice_s = [], 0.0
        self.spk_voice = {}          # speaker label -> cloned voice name (Soniox labels who is talking)
        self.spk_audio = {}          # speaker label -> [audio arrays] collected towards their clone
        self.spk_pitch = {}          # speaker label -> recent phrase pitches (Hz), for the neutral voice choice
        self.identity = bool(engine.tuning.get("identity")) and getattr(engine.asr, "translates", False)
        self.running = False
        self.level_tick = 0.0
        self.next_id = 0

    # --- messages -------------------------------------------------------------------------------------
    async def send(self, obj):
        if self.rec:
            try:
                self.rec.sent(obj)
            except Exception:
                log.exception("recorder")
        try:
            await self.ws.send_text(json.dumps(obj))
        except Exception:
            pass

    def send_ts(self, obj):
        asyncio.run_coroutine_threadsafe(self.send(obj), self.loop)

    def voice_state(self, spk=None):
        if spk is not None:
            locked, need = spk in self.spk_voice, ID_LOCK_S if self.identity else LOCK_SECONDS
            secs = need if locked else sum(len(a) for a in self.spk_audio.get(spk, [])) / SR
            return {"type": "voice", "speaker": spk, "state": "locked" if locked else "collecting",
                    "seconds": round(secs, 1), "needed": need}
        locked = self.voice_name != DEFAULT_VOICE
        return {"type": "voice", "state": "locked" if locked else "collecting",
                "seconds": round(LOCK_SECONDS if locked else self.voice_s, 1), "needed": LOCK_SECONDS}

    def diarized(self):
        return getattr(self.e.asr, "translates", False)        # Soniox: tokens come with speaker labels

    def hello(self):
        if self.diarized():          # Soniox: any language in, any voice language out
            langs, targets = LANGUAGES, list(VOICE_LANGS)
        else:                        # local front end: Italian -> English only
            langs, targets = [("it", "Italian"), ("en", "English")], ["en"]
        return {"type": "hello", "engines": [{"id": "cloud", "label": "Cloud (streaming)", "clones": True, "targets": targets}],
                "languages": [{"code": c, "name": n} for c, n in langs],
                "default_engine": "cloud", "models_ready": True, "server_pacing": True, "recording": bool(self.rec)}

    def apply_config(self, m):
        for k in ("clone", "consent"):
            if k in m:
                self.cfg[k] = bool(m[k])
        if self.diarized():
            src = m.get("source_lang", self.cfg["source_lang"])
            tgt = m.get("target_lang", self.cfg["target_lang"])
            src = src if src in dict(LANGUAGES) else "auto"
            tgt = tgt if tgt in VOICE_LANGS else "en"
            if (src, tgt) != (self.cfg["source_lang"], self.cfg["target_lang"]):
                self.cfg["source_lang"], self.cfg["target_lang"] = src, tgt
                self.stop_run()       # the next mic chunk starts a new run with the new languages
        if not (self.cfg["consent"] and self.cfg["clone"]):
            self.reset_voice()

    def reset_voice(self):
        with self.voice_lock:
            self.voice_epoch += 1
            if self.voice_name != DEFAULT_VOICE:
                self.e.voice.drop_voice(self.voice_name)
            for name in self.spk_voice.values():
                self.e.voice.drop_voice(name)
            self.voice_name, self.voice_audio, self.voice_s = DEFAULT_VOICE, [], 0.0
            self.spk_voice, self.spk_pitch = {}, {}
            r = getattr(self, "run", None)
            if r is not None:
                r.voice_epoch = self.voice_epoch
            if r is not None and hasattr(r, "id_lock"):
                with r.id_lock:
                    r.id_pending = []
                    r.id_reference_start = r.samples / SR
                    self.spk_audio = {}
            else:
                self.spk_audio = {}


    # --- one listening run (from the first mic chunk until "stop") ---------------------------------------
    def start_run(self):
        """Each run has its own queues, so threads of a stopped run can't pick up the next run's audio."""
        self.reset_voice()  # tracker labels are new identities on every listening run
        self.running = True
        r = self.run = SimpleNamespace(audio_q=queue.Queue(), events=queue.Queue(), phrases=queue.Queue(),
                                       vad=LiveVAD(), player=Player(), t0=time.time(), used=set(),
                                       seg=Segmenter(**self.e.tuning["seg"]) if self.diarized() else Segmenter(),
                                       langs=[],                     # (arrival, source language) per word
                                       last_release=time.time(), ended=False,
                                       hist=[], hist_start=0, samples=0, voice_epoch=self.voice_epoch)   # last ~90 s of mic audio
        r.clock = lambda: time.time() - r.t0
        if self.rec:
            self.rec.ev("run_start", run_t0=self.rec.at(r.t0), cfg=dict(self.cfg), tuning=self.e.tuning_name)
        if hasattr(self.e.asr, "sent"):                   # word times count from the start of this run
            self.e.asr.sent, self.e.asr.italian = 0, []
            self.e.asr.source, self.e.asr.target = self.cfg["source_lang"], self.cfg["target_lang"]
        if self.identity:
            if self.e.diarizer is None:
                self.e.diarizer = Diarizer()
            r.dmask = np.zeros(0, np.uint8)               # speaker bits per 10 ms of this run's audio
            r.dscan, r.prev_wall, r.prev_who, r.prev_msg, r.diar_first = 0, 0.0, None, None, None
            r.id_reference_start = 0.0
            r.id_pending, r.id_lock = [], threading.Lock()   # clone pieces waiting for their recognised words
            self.e.diarizer.reset(lambda start, mask, r=r: self._on_diar(r, start, mask))
        for target in (self._asr, self._segmenter, self._interpreter):
            threading.Thread(target=target, args=(r,), daemon=True).start()

    def on_audio(self, pcm16: bytes):
        x = np.frombuffer(pcm16, np.int16).astype(np.float32) / 32768.0
        if not self.running:
            self.start_run()
        r = self.run
        if self.identity:
            self.e.diarizer.feed(pcm16)
        peak = r.vad.feed(x)
        r.audio_q.put(x)
        r.hist.append(x); r.samples += len(x)
        while r.hist and r.samples - r.hist_start - len(r.hist[0]) > 90 * SR:
            r.hist_start += len(r.hist.pop(0))
        if self.cfg["consent"] and self.cfg["clone"] and self.voice_name == DEFAULT_VOICE and not self.diarized():
            if peak > 0.02:                                  # collect clear speech for the voice profile
                self.voice_audio.append(x); self.voice_s += len(x) / SR
                if int(self.voice_s) != int(self.voice_s - len(x) / SR):      # progress for the page, once a second
                    self.send_ts(self.voice_state())
        now = time.time()
        if now - self.level_tick > 0.1:
            self.level_tick = now
            self.send_ts({"type": "level", "rms": min(1.0, peak * 8), "speech": bool(r.vad.voiced[-1:] == [True])})

    def stop_run(self):
        if self.running:
            self.run.audio_q.put(None)
            self.running = False

    def audio_span(self, r, a, b):
        """Mic audio between session seconds a and b (if still in the last ~90 s)."""
        if not r.hist:
            return np.zeros(0, np.float32)
        allx = np.concatenate(r.hist)
        i, j = int(a * SR) - r.hist_start, int(b * SR) - r.hist_start
        return allx[max(0, i):max(0, j)]

    def _asr(self, r):
        keepalive = getattr(self.e.asr, "keepalive", False)

        def chunks():
            while True:
                try:
                    x = r.audio_q.get(timeout=5)
                except queue.Empty:
                    if keepalive:
                        yield "keepalive"              # silence: keep the Soniox session open
                    continue
                if x is None:
                    r.ended = True
                    return
                yield x

        def emit(text, wall, spk=None, lang=None):
            if self.rec and text is not None:
                self.rec.ev("asr", text=text, wall=self.rec.at(wall), speaker=spk, lang=lang)
            if text is not None and text != "<end>":
                r.langs.append((wall, lang))
            r.events.put((text, wall, spk))
        while True:
            try:
                self.e.asr.run_live(chunks(), emit)
                return
            except Exception as e:                       # dropped connection: tell the page, reconnect
                log.warning("recogniser stopped (%s); reconnecting", type(e).__name__)
                if r.ended:
                    emit(None, time.time()); return
                self.send_ts({"type": "status", "state": "listening", "detail": "reconnecting the translator…"})
                time.sleep(1)

    def _segmenter(self, r):
        lat = self.e.asr.latency_s
        while True:
            try:
                text, wall, spk = r.events.get(timeout=0.05)
            except queue.Empty:
                now = r.clock()
                for s in r.seg.tick(now, silence_s=r.vad.silence_before(now - lat)):
                    r.phrases.put(s)
                continue
            if text == "<end>":
                r.seg.mark_endpoint()
                continue
            if text is None:
                for s in r.seg.tick(r.clock(), final=True):
                    r.phrases.put(s)
                r.phrases.put(None)
                return
            for s in r.seg.feed(text, wall - r.t0, spk):
                r.phrases.put(s)

    def _interpreter(self, r):
        lat = self.e.asr.latency_s
        while True:
            batch = [r.phrases.get()]
            while not r.phrases.empty():
                batch.append(r.phrases.get())
            end = batch[-1] is None
            batch = [b for b in batch if b is not None]
            runs = []
            for b in batch:
                if runs and runs[-1][-1].get("speaker") == b.get("speaker"):
                    runs[-1].append(b)
                else:
                    runs.append([b])
            for run in runs:
                self._speak(r, run, src_end=run[-1]["t_last_word"] - lat)
            if end:
                if self.rec:                              # the recognised source words of this run, with audio times
                    self.rec.ev("source_tokens", run_t0=self.rec.at(r.t0), tokens=[
                        {"text": t[0], "start": round(t[1], 3), "end": round(t[2], 3), "wall": self.rec.at(t[3]),
                         "speaker": t[4] if len(t) > 4 else None, "lang": t[5] if len(t) > 5 else None}
                        for t in list(getattr(self.e.asr, "italian", []))])
                    if self.identity and len(getattr(r, "dmask", ())):   # the live diarizer frames, for exact checks
                        import zlib                       # (cloud/check_attribution.py); bit k = person pk, 10 ms
                        self.rec.ev("diar_mask", run_t0=self.rec.at(r.t0), frame_s=0.01,
                                    mask_zlib_b64=base64.b64encode(zlib.compress(r.dmask.tobytes(), 9)).decode())
                self.send_ts({"type": "status", "state": "listening", "detail": ""})
                return

    def _speak(self, r, batch, src_end):
        with self.voice_lock:
            if r is not self.run:
                return
            voice_epoch = r.voice_epoch
        italian = " ".join(b["it"] for b in batch)
        english, spk = None, batch[0].get("speaker")
        own = []
        if self.diarized():                               # Soniox: the phrase is already English
            english = italian
            own = self._pair_italian(r, spk, english, r.t0 + batch[0]["t_first_word"])
            italian = "".join(t[0] for t in own).strip()
            if own:
                src_end = own[-1][2] - (r.samples / SR - r.clock())    # run audio time -> run clock
            if self.identity:
                who, share, info = self.phrase_identity(r, batch, own)
                if self.rec:
                    self.rec.ev("identity", soniox=spk, who=who, share=round(share, 2), **info)
                spk = who                                 # None = unclear -> neutral voice, no clone
            else:
                self._collect_voice(r, spk, own)
        a, b = r.t0 + batch[0]["t_first_word"] - 0.01, r.t0 + batch[-1]["t_last_word"] + 0.01
        langs = [l for w, l in list(r.langs) if a <= w <= b]
        lang = langs[0] if langs and all(l == langs[0] for l in langs) else None
        self.next_id += 1
        uid = self.next_id
        src_lang = self.cfg["source_lang"] if self.cfg["source_lang"] != "auto" else None
        tgt_lang = self.cfg["target_lang"]
        self.send_ts({"type": "segment", "id": uid, "speaker": spk, "source_text": italian, "source_lang": src_lang,
                      "target_text": None, "target_lang": tgt_lang, "timings": {}})
        if self.rec:
            self.rec.ev("phrase", id=uid, speaker=spk, source=italian, target=english,
                        first_word=self.rec.at(r.t0 + batch[0]["t_first_word"]),
                        last_word=self.rec.at(r.t0 + batch[-1]["t_last_word"]), src_end=self.rec.at(r.t0 + src_end),
                        # the source words this phrase translates, in session audio time (for the Whisper check)
                        src_audio=[round(self.rec.at(r.t0) + own[0][1], 2), round(self.rec.at(r.t0) + own[-1][2], 2)]
                        if own else None,
                        voice_seconds={k: round(sum(len(a) for a in v) / SR, 1) for k, v in self.spk_audio.items()},
                        lang=lang, reason=batch[-1].get("reason"))
        neutral, hz = self.neutral_voice(r, spk, own) if self.diarized() else (DEFAULT_VOICE, None)
        self._flush_pieces(r)
        t_wait = time.time()
        with self.e.gpu:
            gpu_wait = time.time() - t_wait
            with self.voice_lock:
                if r is not self.run or voice_epoch != self.voice_epoch:
                    return
                need = ID_LOCK_S if self.identity else LOCK_SECONDS
                name, ref, clone_spk = None, None, None
                if self.cfg["consent"] and self.cfg["clone"]:
                    # Same lock order as reset: voice state, then the reference collector's lock.
                    with getattr(r, "id_lock", self.voice_lock):
                        if spk is not None and spk not in self.spk_voice \
                                and sum(len(a) for a in self.spk_audio.get(spk, [])) >= need * SR:
                            clone_spk = spk
                            name = f"user-{self.id}-{voice_epoch}-{spk}"
                            ref = np.concatenate(self.spk_audio.pop(spk))
                            if self.identity:
                                ref = ref[:int(ID_MAX_REF_S * SR)]
                        elif not self.diarized() and self.voice_name == DEFAULT_VOICE and self.voice_s >= LOCK_SECONDS:
                            name = f"user-{self.id}-{voice_epoch}"
                            ref = np.concatenate(self.voice_audio)
            if name is not None:
                t_v = time.time()
                self.e.voice.add_voice(name, ref, sr=SR, cache=False)
                with self.voice_lock:
                    if r is not self.run or voice_epoch != self.voice_epoch or not (self.cfg["consent"] and self.cfg["clone"]):
                        self.e.voice.drop_voice(name)
                        return
                    if clone_spk is not None:
                        self.spk_voice[clone_spk] = name
                    else:
                        self.voice_name, self.voice_audio = name, []
                    if self.rec:
                        self.rec.voice_ref(clone_spk if clone_spk is not None else "single", ref)
                        self.rec.ev("voice_locked", speaker=clone_spk, ref_seconds=round(len(ref) / SR, 1),
                                    build_s=round(time.time() - t_v, 3))
                    self.send_ts(self.voice_state(clone_spk))
            backlog = r.player.backlog(r.clock())
            if english is None:
                english, mt_s = self.e.mt.translate(italian, brief=False, history=self.history)
            else:
                mt_s = 0.0
            self.send_ts({"type": "segment", "id": uid, "speaker": spk, "source_text": italian, "source_lang": src_lang,
                          "target_text": english, "target_lang": tgt_lang, "timings": {"mt": round(mt_s, 2)}})
            if not re.search(r"\w", english):
                return
            tun = self.e.tuning
            skip = None
            if tun["skip_same_language"] and target_only(langs, tgt_lang):
                skip = "same_language"                    # the listener understands it: stay silent
            elif tun["filler_backlog"] is not None and backlog > tun["filler_backlog"] and FILLER.match(english):
                skip = "filler_behind"                    # only non-semantic hesitation may be omitted
            if skip:
                if self.rec:
                    self.rec.ev("skipped", id=uid, why=skip, backlog=round(backlog, 2), target=english)
                self.send_ts({"type": "audio", "id": uid, "part": 0, "final": True})
                return
            rate = min(tun["max_rate"], next((r for b, r in RATES if backlog > b), 1.0))
            part, held, first_t, total = 0, None, None, 0.0
            parts = []
            with self.voice_lock:
                if r is not self.run or voice_epoch != self.voice_epoch:
                    return
                voice = self.spk_voice.get(spk, neutral) if self.diarized() else self.voice_name
                # stream snapshots its prompt now; generation begins after releasing this lock.
                stream = self.e.voice.stream(english, voice, language=VOICE_LANGS.get(self.cfg["target_lang"], "English"))
            if self.rec:
                self.rec.ev("speak", id=uid, voice=voice, rate=rate, backlog=round(backlog, 2), pitch=hz and round(hz),
                            gpu_wait=round(gpu_wait, 3), target=english)
            t_tts = time.time()
            for chunk, sr, info in stream:
                with self.voice_lock:
                    if r is not self.run or voice_epoch != self.voice_epoch:
                        return
                if info is not None or not len(chunk):
                    continue
                if rate > 1:                                  # behind: gather, speed up, send in one go
                    parts.append(chunk); continue
                if held is None:                              # first chunk: cut the model's silent lead-in
                    idx = np.flatnonzero(np.abs(chunk) > 0.01)
                    chunk = chunk[max(0, idx[0] - int(0.06 * sr)):] if len(idx) else chunk
                else:
                    self._send_audio(r, uid, part, held, sr, src_end, voice_epoch); part += 1; total += len(held) / sr
                first_t = first_t or r.clock()
                held = chunk                                  # hold one chunk back to trim the tail
            if rate > 1 and parts:
                audio = stretch(trim(np.concatenate(parts), sr), sr, rate)
                first_t = r.clock()
                self._send_audio(r, uid, part, audio, sr, src_end, voice_epoch); part += 1; total += len(audio) / sr
            elif held is not None:
                tail = trim(held, sr) if np.abs(held).max() > 0.01 else held[:0]
                self._send_audio(r, uid, part, tail, sr, src_end, voice_epoch); part += 1; total += len(tail) / sr
            if first_t is not None:
                r.player.schedule(first_t, r.clock(), total)
            if self.rec:
                self.rec.ev("spoken", id=uid, tts_s=round(time.time() - t_tts, 3), audio_s=round(total, 2),
                            first_audio=self.rec.at(r.t0 + first_t) if first_t is not None else None)
            self.send_ts({"type": "audio", "id": uid, "part": part, "final": True})

    # --- who is speaking (tuning "identity") ------------------------------------------------------------
    def _on_diar(self, r, start, mask):
        """New speaker masks from the diarizer: store them, then collect finished clean single-speaker stretches
        towards each person's voice."""
        if r.diar_first is None:
            r.diar_first = r.clock()
            if self.rec:
                self.rec.ev("diar_first_frames", run_clock=round(r.diar_first, 3), start=int(start))
        if start + len(mask) > len(r.dmask):
            r.dmask = np.concatenate([r.dmask, np.zeros(start + len(mask) - len(r.dmask), np.uint8)])
        r.dmask[start:start + len(mask)] = mask
        m, i = r.dmask, r.dscan
        single = (m != 0) & ((m & (m - 1)) == 0)          # exactly one speaker bit set
        while i < len(m):
            if not single[i]:
                i += 1; continue
            j = i
            while j < len(m) and m[j] == m[i]:
                j += 1
            if j == len(m):                               # still talking: take full pieces now, the rest later
                if (j - i) / 100 >= ID_MAX_PIECE_S + 0.3:
                    k = i + int(ID_MAX_PIECE_S * 100)
                    self._collect_identity(r, f"p{int(m[i]).bit_length() - 1}", i / 100, k / 100 + 0.15)
                    i = k
                    continue
                break
            if (j - i) / 100 >= ID_MIN_RUN_S:
                self._collect_identity(r, f"p{int(m[i]).bit_length() - 1}", i / 100, j / 100)
            i = j
        r.dscan = i

    def _reference_quality(self, x):
        """Provisional PCM hygiene and speech occupancy, not a calibrated SNR/voice-quality score."""
        if not len(x) or not np.isfinite(x).all():
            return None, "nonfinite_or_empty"
        if float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) < 0.004:
            return None, "quiet"
        if np.mean(np.abs(x) >= 0.99) >= 0.01:
            return None, "clipped"
        # shortcut: activity cannot distinguish speech from noise; calibrate on held-out meetings before release.
        frames = x[:len(x) // 320 * 320].reshape(-1, 320)
        active = float(np.mean(np.sqrt(np.mean(frames ** 2, axis=1)) >= 0.004)) if len(frames) else 0.0
        return active, None

    def _collect_identity(self, r, who, a, b):
        with r.id_lock:
            if r is not self.run or who in self.spk_voice or not (self.cfg["consent"] and self.cfg["clone"]):
                return
            t = max(a + 0.15, getattr(r, "id_reference_start", 0.0))   # trim turn edges and pre-reset audio
            while t + ID_MIN_RUN_S <= b - 0.15:
                u = min(b - 0.15, t + ID_MAX_PIECE_S)
                if u > r.samples / SR:
                    break                                 # diarizer callback can precede audio history storage
                x = self.audio_span(r, t, u)
                quality, rejection = self._reference_quality(x)
                if len(x) < int((u - t) * SR) - 1:
                    rejection = "incomplete_audio"
                if rejection is None:
                    r.id_pending.append((who, t, u, x.copy()))
                elif self.rec:
                    self.rec.ev("identity_piece_rejected", who=who, start=round(t, 2), end=round(u, 2),
                                rejection=rejection, activity=quality)
                t = u
            # Bound delayed-token storage across all speakers, even when no phrase is attributed yet.
            pending_samples = sum(len(p[3]) for p in r.id_pending)
            while pending_samples > 4 * ID_MAX_REF_S * SR:
                pending_samples -= len(r.id_pending.pop(0)[3])
        if self.rec:
            self.rec.ev("identity_piece", who=who, start=round(a, 2), end=round(b, 2),
                        total=round(sum(len(x) for x in self.spk_audio.get(who, [])) / SR, 1))
        self._flush_pieces(r)

    def _flush_pieces(self, r, final=False):
        """Keep the best available speech pieces within the reference budget, after source words arrive."""
        if not self.identity or not getattr(r, "id_pending", None):
            return
        now = r.clock()
        toks = [t for t in list(self.e.asr.italian) if t[3] <= r.t0 + now]
        heard_to = max((t[2] for t in toks), default=0.0)
        changed = set()
        with r.id_lock:
            if r is not self.run or not (self.cfg["consent"] and self.cfg["clone"]):
                r.id_pending = []
                return
            keep = []
            for who, a, b, x in r.id_pending:
                if a < getattr(r, "id_reference_start", 0.0) or b > r.samples / SR or who in self.spk_voice:
                    continue
                if not final and heard_to < b + 1.0 and now - b < ID_TOK_WAIT_S:
                    keep.append((who, a, b, x)); continue  # its words may still be on the way
                n = sum(1 for t in toks if a <= t[1] < b)
                quality, rejection = self._reference_quality(x)
                ok = n >= ID_MIN_TOK_PER_S * (b - a) and quality is not None
                if ok:
                    pieces = self.spk_audio.get(who, []) + [x]
                    pieces.sort(key=lambda piece: self._reference_quality(piece)[0], reverse=True)
                    selected, total = [], 0
                    for piece in pieces:
                        if total + len(piece) <= ID_MAX_REF_S * SR:
                            selected.append(piece); total += len(piece)
                    self.spk_audio[who] = selected
                    ok = any(piece is x for piece in selected)
                    changed.add(who)
                if self.rec:
                    self.rec.ev("identity_piece_check", who=who, start=round(a, 2), end=round(b, 2), tokens=n,
                                kept=bool(ok), activity=quality, rejection=rejection)
            r.id_pending = keep
        for who in changed:
            self.send_ts(self.voice_state(who))

    def phrase_identity(self, r, batch, own=()):
        """The person who spoke this phrase's source words: majority of single-speaker diarizer frames over the
        stretch of speech from the first to the last source word (not only inside each ~60 ms sub-word stamp).
        Tried in order: (1) the source words that arrived since the previous phrase; (2) the phrase's own paired
        source words (`own`, last ID_OWN_MAX_S only), when (1) is empty or too short; (3) the previous phrase's person,
        when this phrase's English came in the same Soniox message with the same Soniox speaker (one message split
        into two phrases). A "mixed" vote is final: unclear speech stays neutral, no fallback overrides it. Returns
        (who or None, share, info) with info = how it was decided, or why not (diagnosis 2026-10-03, research 13;
        review fixes 2026-10-04)."""
        last = r.t0 + batch[-1]["t_last_word"] + 0.05
        toks = [t for t in list(self.e.asr.italian) if r.prev_wall < t[3] <= last]
        # message identity: every word of one Soniox message carries that message's single arrival stamp (`now` in
        # soniox_front), so equal stamps = same message; a different Soniox speaker means a split, never a reuse
        msg, sspk = batch[-1]["t_last_word"], batch[0].get("speaker")
        same_msg = (r.prev_msg is not None and batch[0]["t_first_word"] == msg == r.prev_msg[0]   # whole phrase
                    and sspk is not None and all(b.get("speaker") == sspk for b in batch) and sspk == r.prev_msg[1])
        r.prev_wall, r.prev_msg = last, (batch[-1]["t_last_word"], batch[-1].get("speaker"))
        m = r.dmask
        info = {"words": len(toks), "own_words": len(own), "frames": 0, "via": None, "reason": None,
                "mask_len": len(m),                       # diarizer frames available at decision time
                "same_msg": same_msg}

        def vote(a, b):
            if b - a < ID_MIN_SPAN_S:                     # e.g. "No, no, chiaro." = 0.24 s: widen around the words
                c = (a + b) / 2                           # before any fallback to older words (phrase #88)
                a, b = c - ID_MIN_SPAN_S / 2, c + ID_MIN_SPAN_S / 2
            counts = {}
            for f in m[max(0, int(a * 100)):max(0, int(b * 100) + 1)]:
                if f and not (f & (f - 1)):
                    counts[int(f)] = counts.get(int(f), 0) + 1
            total = sum(counts.values())
            if total < 30:                                # < 0.3 s of clear single-speaker frames
                return None, 0.0, total, "too_few_frames"
            best = max(counts, key=counts.get)
            share = counts[best] / total
            if share < ID_MIN_SHARE:
                return None, share, total, "mixed"
            return f"p{best.bit_length() - 1}", share, total, None

        old = {}                                          # the pre-2026-10-04 rule (frames inside word stamps only),
        for t in toks:                                    # logged so a replay shows whether any owner changed
            for f in m[int(t[1] * 100):int(t[2] * 100) + 1]:
                if f and not (f & (f - 1)):
                    old[int(f)] = old.get(int(f), 0) + 1
        if sum(old.values()) >= 30:
            b0 = max(old, key=old.get)
            info["old_who"] = f"p{b0.bit_length() - 1}" if old[b0] / sum(old.values()) >= ID_MIN_SHARE else None
        else:
            info["old_who"] = None
        who, share = None, 0.0
        if not len(m):
            info["reason"] = "no_frames_yet"
        else:
            tries = []
            if toks:
                tries.append(("arrived", min(t[1] for t in toks), max(t[2] for t in toks)))
            if own:
                b = max(t[2] for t in own)                # recent own words only: pairing can reach back
                tries.append(("own", max(min(t[1] for t in own), b - ID_OWN_MAX_S), b))   # ~15 s (phrase #88)
            if not tries:
                info["reason"] = "no_words"
            for via, a, b in tries:
                who, share, total, why = vote(a, b)
                info["frames"] = max(info["frames"], total)
                if who:
                    info["via"], info["reason"] = via, None
                    break
                info["reason"] = why
                if why == "mixed":                        # clear evidence of two people: stay neutral
                    break
        if who is None and info["reason"] != "mixed" and same_msg and r.prev_who:
            who, info["via"] = r.prev_who, "same_message"
        r.prev_who = who
        return who, share, info

    def neutral_voice(self, r, spk, own):
        """Male or female neutral voice from this phrase's own audio; unclear pitch -> the speaker's recent average."""
        hz = None
        if own:
            hz = pitch_hz(self.audio_span(r, max(own[0][1], own[-1][2] - 4.0), own[-1][2]))
        hist = self.spk_pitch.setdefault(spk, [])
        if hz is not None:
            hist.append(hz); del hist[:-10]
        if hz is not None and (hz < PITCH_MALE or hz > PITCH_FEMALE):
            g = "male" if hz < PITCH_MALE else "female"
        elif len(hist) >= 3:
            g = "male" if float(np.median(hist)) < PITCH_SPLIT else "female"
        elif hz is not None:
            g = "male" if hz < PITCH_SPLIT else "female"
        else:
            g = None
        return (NEUTRAL[g] if g else DEFAULT_VOICE), hz

    def _pair_italian(self, r, spk, english, first_wall):
        """This speaker's Italian words that this English translates. Soniox sends a clause's Italian first and
        its translation right after, clause by clause, so take their not-yet-used words in order, one Italian
        clause per clause-ending mark in the English."""
        avail = [t for t in list(self.e.asr.italian) if id(t) not in r.used and t[3] <= first_wall + 0.5
                 and (spk is None or t[4] == spk)]
        need = max(1, len(re.findall(r"[.,;:?!](?:\s|$)", english)))
        take, ends = [], 0
        for t in avail:
            take.append(t)
            if re.search(r"[.,;:?!]\s*$", t[0]):
                ends += 1
                if ends >= need:
                    break
        r.used.update(id(t) for t in take)
        return take

    def _collect_voice(self, r, spk, toks):
        """Add this speaker's words (by Soniox's word times) to the audio their voice is cloned from."""
        if spk is None or spk in self.spk_voice or not (self.cfg["consent"] and self.cfg["clone"]):
            return
        got = self.spk_audio.setdefault(spk, [])
        before = sum(len(a) for a in got) / SR
        for t in toks:
            x = self.audio_span(r, t[1], t[2])
            if len(x):
                got.append(x)
        if int(sum(len(a) for a in got) / SR) != int(before):
            self.send_ts(self.voice_state(spk))

    def _send_audio(self, r, uid, part, audio, sr, src_end, voice_epoch):
        if not len(audio):
            return
        encoded = wav_b64(audio, sr)
        with self.voice_lock:
            if r is not self.run or voice_epoch != self.voice_epoch:
                return
            # "age": seconds since the speaker finished this phrase; the browser keeps a steady lag behind it
            self.send_ts({"type": "audio", "id": uid, "part": part, "final": False, "sample_rate": sr,
                          "age": round(max(0.0, r.clock() - src_end), 3), "wav_base64": encoded})


async def serve(ws, engine: Engine, idle_s=15, rate_per_hour=1.0, on_usage=None, record_dir=None, on_record=None):
    """Run one browser connection (FastAPI WebSocket).
    Not in use = no microphone audio for idle_s seconds (Stop pressed, tab closed or hidden): the connection is
    closed so the GPU can switch off; pressing Start reconnects. The page gets a usage meter every 5 s, and
    on_usage(client_id, seconds) records the session time for billing. With record_dir, the whole session
    (mic, sent audio, every step) is saved to record_dir/<date>/<time>_<session> and on_record(path) is called."""
    await ws.accept()
    rec = None
    if record_dir:
        from recorder import Recorder
        sid = uuid.uuid4().hex[:8]
        rec = Recorder(sid, f"{record_dir}/{time.strftime('%Y-%m-%d')}/{time.strftime('%H%M%S')}_{sid}")
    s = LiveSession(ws, engine, rec)
    if rec:
        s.id = rec.id
    started = last_audio = last_meter = time.time()
    client_id = "anonymous"
    await s.send(s.hello())
    await s.send(s.voice_state())
    await s.send({"type": "status", "state": "listening", "detail": ""})
    try:
        while True:
            now = time.time()
            if now - last_meter >= 5:
                last_meter = now
                await s.send({"type": "usage", "session_s": round(now - started), "rate_per_hour": rate_per_hour})
            if now - last_audio > idle_s:
                await s.send({"type": "status", "state": "idle", "detail": "translator switched off (not in use)"})
                await ws.close()
                break
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                last_audio = time.time()
                if rec:
                    rec.mic_chunk(msg["bytes"])
                s.on_audio(msg["bytes"])
                continue
            try:
                m = json.loads(msg.get("text") or "{}")
            except json.JSONDecodeError:
                continue
            t = m.get("type")
            if rec and t != "ping":
                rec.ev("client", **m)
            if t == "config":
                client_id = str(m.get("client_id") or client_id)[:64]
                s.apply_config(m)
                await s.send({"type": "config", **s.cfg}); await s.send(s.voice_state())
            elif t in ("stop", "flush"):
                s.stop_run()
                if t == "stop":
                    await s.send({"type": "status", "state": "idle", "detail": "stopped"})
            elif t == "reset_voice":
                s.reset_voice(); await s.send(s.voice_state())
            elif t == "playback":
                log.info("client playback: %s", {k: v for k, v in m.items() if k != "type"})
            elif t == "ping":
                await s.send({"type": "pong"})
    finally:
        s.stop_run()
        s.reset_voice()                                   # the voice profile never outlives the connection
        seconds = time.time() - started
        log.info("session %s client %s: %.0f s on the GPU", s.id, client_id, seconds)
        if on_usage:
            try:
                await asyncio.to_thread(on_usage, client_id, seconds)
            except Exception:
                log.exception("usage logging failed")
        if rec:
            try:
                await asyncio.sleep(1.0)                  # let the last phrase's events land
                if not any(e["kind"] == "source_tokens" for e in rec.events):   # run still draining: take them now
                    rec.ev("source_tokens", run_t0=rec.at(s.run.t0) if hasattr(s, "run") else 0.0, tokens=[
                        {"text": t[0], "start": round(t[1], 3), "end": round(t[2], 3), "wall": rec.at(t[3]),
                         "speaker": t[4] if len(t) > 4 else None, "lang": t[5] if len(t) > 5 else None}
                        for t in list(getattr(engine.asr, "italian", []))])
                summary = await asyncio.to_thread(rec.save)
                log.info("session %s recorded: %s (%.0f s, %d parts)", s.id, rec.out_dir, summary["seconds"],
                         len(summary["playback"]))
                if on_record:
                    await asyncio.to_thread(on_record, rec.out_dir)
            except Exception:
                log.exception("session recording failed")
