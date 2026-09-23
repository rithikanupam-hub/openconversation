"""LingoSync AI server: serves the web app and the real-time WebSocket pipeline."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .pipeline import ENGINES, LANGUAGES, VoiceProfile, pipeline, wav_bytes
from .vad import SAMPLE_RATE, Segmenter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("lingosync.server")
logging.getLogger("argostranslate").setLevel(logging.WARNING)  # logs every token otherwise

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DEFAULT_ENGINE = os.environ.get("LINGOSYNC_ENGINE", "chatterbox_turbo")

app = FastAPI(title="LingoSync AI")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.middleware("http")
async def _no_stale_ui(request, call_next):
    # Browsers (and phones) must revalidate the UI files, or a redesign keeps loading old CSS/JS.
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response
# One worker: MLX models must not be driven concurrently.
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")
warm = {"ready": False, "error": None}


@app.on_event("startup")
async def _warm():
    if os.environ.get("LINGOSYNC_NO_WARMUP"):
        return

    def go():
        try:
            pipeline.warmup(DEFAULT_ENGINE)
            warm["ready"] = True
        except Exception as e:  # noqa: BLE001
            log.exception("warmup failed")
            warm["error"] = str(e)

    asyncio.get_event_loop().run_in_executor(executor, go)


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "models_ready": warm["ready"], "error": warm["error"],
            "engines": list(ENGINES), "default_engine": DEFAULT_ENGINE}


def hello_payload() -> dict:
    return {
        "type": "hello",
        "engines": [{"id": k, "label": v["label"], "clones": v["clones"], "targets": v["targets"]}
                    for k, v in ENGINES.items()],
        "languages": [{"code": c, "name": n} for c, n in LANGUAGES],
        "default_engine": DEFAULT_ENGINE,
        "models_ready": warm["ready"],
    }


class Session:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.cfg = {"source_lang": "auto", "target_lang": "en", "engine": DEFAULT_ENGINE,
                    "clone": True, "consent": False}
        self.seg = Segmenter()
        self.profile = VoiceProfile()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.next_id = 0
        self.loop = asyncio.get_event_loop()
        self.level_tick = 0.0

    async def send(self, obj: dict):
        try:
            await self.ws.send_text(json.dumps(obj))
        except Exception:  # connection gone
            pass

    def send_threadsafe(self, obj: dict):
        asyncio.run_coroutine_threadsafe(self.send(obj), self.loop)

    async def status(self, state: str, detail: str = ""):
        await self.send({"type": "status", "state": state, "detail": detail})

    def apply_config(self, msg: dict):
        for k in ("source_lang", "target_lang", "engine", "clone", "consent"):
            if k in msg:
                self.cfg[k] = msg[k]
        if self.cfg["engine"] not in ENGINES:
            self.cfg["engine"] = DEFAULT_ENGINE
        if not self.cfg["consent"]:
            self.cfg["clone"] = False
            self.profile.clear()
        targets = ENGINES[self.cfg["engine"]]["targets"]
        if targets and self.cfg["target_lang"] not in targets:
            self.cfg["target_lang"] = targets[0]

    async def worker(self):
        """Processes utterances strictly in order so playback never overlaps."""
        while True:
            uid, audio = await self.queue.get()
            cfg = dict(self.cfg)
            await self.status("transcribing", f"utterance {uid}: {len(audio)/SAMPLE_RATE:.1f}s")

            def on_transcript(text, lang):
                self.send_threadsafe({"type": "segment", "id": uid, "source_text": text, "source_lang": lang,
                                      "target_text": None, "target_lang": cfg["target_lang"], "timings": {}})
                self.send_threadsafe({"type": "status", "state": "translating",
                                      "detail": f"{lang} → {cfg['target_lang']}"})

            def on_translation(target, timings):
                self.send_threadsafe({"type": "segment", "id": uid, "source_text": None, "source_lang": None,
                                      "target_text": target, "target_lang": cfg["target_lang"], "timings": timings})
                self.send_threadsafe({"type": "status", "state": "synthesizing", "detail": ""})

            part = [0]

            def on_chunk(audio, sr):
                self.send_threadsafe({"type": "audio", "id": uid, "part": part[0], "final": False,
                                      "sample_rate": sr,
                                      "wav_base64": base64.b64encode(wav_bytes(audio, sr)).decode()})
                part[0] += 1

            try:
                res = await self.loop.run_in_executor(
                    executor, pipeline.run, audio, cfg["source_lang"], cfg["target_lang"], cfg["engine"],
                    bool(cfg["clone"] and cfg["consent"]), self.profile, on_transcript, on_translation, on_chunk)
            except Exception as e:  # noqa: BLE001
                log.exception("pipeline failed")
                await self.send({"type": "error", "message": f"Pipeline error: {e}"})
                await self.status("listening", "")
                continue

            if res.skipped == "no_speech":
                await self.status("listening", "no speech detected")
                continue
            await self.send({"type": "segment", "id": uid, "source_text": res.source_text,
                             "source_lang": res.source_lang, "target_text": res.target_text,
                             "target_lang": res.target_lang, "timings": res.timings,
                             "skipped": res.skipped})
            if part[0]:
                await self.send({"type": "audio", "id": uid, "part": part[0], "final": True})
            if cfg["clone"] and cfg["consent"]:
                await self.send(self.profile.state())
            await self.status("listening", "")

    async def on_audio(self, data: bytes):
        frame = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        utt = self.seg.feed(frame)
        now = self.loop.time()
        if now - self.level_tick > 0.1:
            self.level_tick = now
            await self.send({"type": "level", "rms": min(1.0, self.seg.last_rms * 8), "speech": self.seg.speaking})
        if utt is not None:
            await self.enqueue(utt.audio)

    async def enqueue(self, audio: np.ndarray):
        self.next_id += 1
        await self.queue.put((self.next_id, audio))
        await self.status("speech", f"queued utterance {self.next_id}")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    s = Session(ws)
    await s.send(hello_payload())
    if warm["error"]:
        await s.send({"type": "error", "message": f"Model warmup failed: {warm['error']}"})
    await s.status("loading" if not warm["ready"] else "listening",
                   "downloading / loading models (first run takes a few minutes)" if not warm["ready"] else "")
    task = asyncio.create_task(s.worker())
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                await s.on_audio(msg["bytes"])
            elif msg.get("text"):
                try:
                    m = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                t = m.get("type")
                if t == "config":
                    s.apply_config(m)
                    await s.send({"type": "config", **s.cfg})
                    await s.send(s.profile.state())
                elif t == "flush":
                    utt = s.seg.flush()
                    if utt is not None:
                        await s.enqueue(utt.audio)
                elif t == "stop":
                    utt = s.seg.flush()
                    if utt is not None:
                        await s.enqueue(utt.audio)
                    await s.status("idle", "stopped")
                elif t == "reset_voice":
                    s.profile.clear()
                    await s.send(s.profile.state())
                elif t == "ping":
                    await s.send({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
