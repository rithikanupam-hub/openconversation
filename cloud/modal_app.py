"""LingoSync web app on Modal: the page is served from a small CPU endpoint; the interpreter runs on an L4 GPU
that starts when someone opens the page and stops a minute after they leave (billed per second while running).

    pip install modal && modal token new          # once: log in to your Modal account
    modal deploy cloud/modal_app.py               # prints the web page URL
    modal run cloud/modal_app.py::download        # once: fetch the model weights on a cheap CPU machine
    modal app logs lingosync                      # live logs

Models are downloaded once into the Modal Volume "lingosync-hf-cache", so later starts only load them.
Cost guard: at most MAX_GPUS interpreters run at once; the page connects only on Start, and a connection with
no microphone audio for IDLE_SECONDS is closed, which lets its GPU stop (scaledown 15 s).
"""
import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "tests" / "stack_compare"          # the engine measured in the stream tests
MAX_GPUS = 1          # testing phase: one GPU at most (a reconnecting page once queued 3; 2026-09-27)
IDLE_SECONDS = 15     # owner's rule: not in use (no mic audio) for 15 s -> close; the GPU stops 15 s later
MAX_SESSION_MINUTES = 60
PRICE_PER_HOUR = 1.00 # shown to users; roughly our cost (L4 ~$0.80/h + Soniox ~$0.18/h). Set the real price here.
# front end: "local" = Nemotron + Qwen translator on the GPU; "soniox" = Soniox recognises + translates (paid API,
# needs the Modal secret "soniox"). Change and `modal deploy` again (takes seconds).
FRONT = "soniox"
# owner testing: save every session (mic, translated audio, voice reference, all steps) to the Volume
# "lingosync-recordings" for review with cloud/review_session.py. Turn OFF before real customers use the app.
RECORD_SESSIONS = True
# A second copy for replay tests, never touching the live app:
#   LINGOSYNC_APP=lingosync-dev LINGOSYNC_TUNING=baseline|v1 modal deploy cloud/modal_app.py
APP_NAME = os.environ.get("LINGOSYNC_APP", "lingosync")
TUNING = os.environ.get("LINGOSYNC_TUNING", "id1")     # profiles in cloud/live.py (id1 = v1 + speaker tracker, 2026-10-03)
# GPU memory snapshot (Modal, experimental; on since 2026-10-01): saves the loaded GPU state, so a cold start
# restores it instead of loading the model again.
# Where the GPU runs: "" = Modal's default; "eu" keeps meeting audio in the EU (Modal EU regions cost ~1.15x).
# Pair it with LINGOSYNC_SONIOX_REGION=eu once Soniox has enabled their EU endpoint for the project.
REGION = os.environ.get("LINGOSYNC_REGION", "")
SONIOX_REGION = os.environ.get("LINGOSYNC_SONIOX_REGION", "")
SNAPSHOT = os.environ.get("LINGOSYNC_SNAPSHOT", "gpu")   # "off" to disable (tested 2026-10-01: 6-11 s starts)
# "Get ready" warm-up (owner, 2026-10-01): the page's button starts the GPU early and holds it at most WARM_HOLD_S;
# limits are enforced here, never in the page.
WARM_HOLD_S = 75
WARM_PER_CLIENT_S = 600       # one warm-up per browser per 10 minutes
WARM_PER_DAY = 30             # all browsers together

app = modal.App(APP_NAME)
hf_cache = modal.Volume.from_name("lingosync-hf-cache", create_if_missing=True)
recordings = modal.Volume.from_name(f"{APP_NAME}-recordings", create_if_missing=True)
warm_log = modal.Dict.from_name(f"{APP_NAME}-warm", create_if_missing=True)   # warm-up limits; "disabled" = kill switch
usage_log = modal.Dict.from_name("lingosync-usage", create_if_missing=True)   # client id -> seconds used

gpu_base = (                                            # packages only; local code is added last (Modal rule)
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libsndfile1")
    .pip_install("torch", "torchaudio", index_url="https://download.pytorch.org/whl/cu128")
    .pip_install("faster-qwen3-tts==0.5.2", "transformers==5.15.1",   # 5.17 breaks qwen-tts's codec (Session 8b)
                 "accelerate", "soundfile", "librosa", "audiotsm", "fastapi[standard]", "websockets")
    .apt_install("git")
    # speaker diarization (step 4) needs a newer transformers than Qwen3-TTS: its own copy, used only by the
    # diar_worker.py subprocess via PYTHONPATH=/opt/diar
    .run_commands("pip install --target /opt/diar 'transformers @ git+https://github.com/huggingface/transformers' librosa")
    .env({"HF_HOME": "/hf", "TOKENIZERS_PARALLELISM": "false", "HF_HUB_DISABLE_PROGRESS_BARS": "1",
          "HF_HUB_OFFLINE": "1"})            # weights are in the Volume: skip ~5 s of update checks per start
)


def with_engine(img):
    return (img
    .add_local_file(ENGINE / "asr_stream.py", "/root/asr_stream.py")
    .add_local_file(ENGINE / "mt.py", "/root/mt.py")
    .add_local_file(ENGINE / "voice_stream.py", "/root/voice_stream.py")
    .add_local_file(ENGINE / "stream_sim.py", "/root/stream_sim.py")
    .add_local_file(ENGINE / "soniox_front.py", "/root/soniox_front.py")
    .add_local_file(ROOT / "cloud" / "live.py", "/root/live.py")
    .add_local_file(ROOT / "cloud" / "recorder.py", "/root/recorder.py")
    .add_local_file(ROOT / "cloud" / "diar_worker.py", "/root/diar_worker.py")
    .add_local_file(ROOT / "cloud" / "terms.json", "/root/terms.json")
    .add_local_file(ROOT / "cloud" / "default_voice.wav", "/root/default_voice.wav")
    .add_local_file(ROOT / "cloud" / "neutral_male.wav", "/root/neutral_male.wav")
    .add_local_file(ROOT / "cloud" / "neutral_female.wav", "/root/neutral_female.wav"))


gpu_image = with_engine(gpu_base.env({"LINGOSYNC_FRONT": FRONT, "LINGOSYNC_APP": APP_NAME, "LINGOSYNC_TUNING": TUNING,
                                      "LINGOSYNC_SNAPSHOT": SNAPSHOT, "LINGOSYNC_SONIOX_REGION": SONIOX_REGION}))

web_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi[standard]")
    .env({"LINGOSYNC_APP": APP_NAME})
    .add_local_dir(ROOT / "frontend", "/root/frontend")
)


MODELS = ["nvidia/nemotron-3.5-asr-streaming-0.6b", "Qwen/Qwen3-4B-Instruct-2507", "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
          "nvidia/Nemotron-3-Diarization"]


@app.function(image=gpu_image, volumes={"/hf": hf_cache}, timeout=3600)
def download():
    """Fill the weights cache without paying for a GPU."""
    import os
    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import snapshot_download
    for m in MODELS:
        print("downloading", m, flush=True)
        snapshot_download(m)
    hf_cache.commit()


def record_usage(client_id, seconds):
    """Session time per browser (anonymous id kept in the page) for billing by time; read with
    `modal dict items lingosync-usage`."""
    import time as _t
    usage_log[client_id] = usage_log.get(client_id, 0) + seconds
    usage_log[f"session:{int(_t.time())}:{client_id}"] = round(seconds)


SNAP_KW = dict(enable_memory_snapshot=True, experimental_options={"enable_gpu_snapshot": True}) if SNAPSHOT == "gpu" else {}
if REGION:
    SNAP_KW["region"] = REGION


@app.cls(gpu="L4", image=gpu_image, volumes={"/hf": hf_cache, "/rec": recordings}, timeout=MAX_SESSION_MINUTES * 60,
         scaledown_window=15, max_containers=MAX_GPUS, secrets=[modal.Secret.from_name("soniox")],
         cpu=4.0, memory=16384, **SNAP_KW)   # Modal's default CPU slice starved the threads (Nemotron slower than on AWS)
@modal.concurrent(max_inputs=2)            # one conversation per GPU (guarded below) + the warm-up hold
class Interpreter:
    @modal.enter(snap=SNAPSHOT == "gpu")
    def load(self):
        import logging, sys, time
        t0 = time.time()
        logging.basicConfig(level=logging.INFO)
        sys.path.insert(0, "/root")
        from live import Engine
        t1 = time.time()
        self.engine = Engine("/root/default_voice.wav")
        self.active = False                # a conversation is running on this GPU
        logging.getLogger("lingosync.start").info("start stages: imports %.1fs, engine %.1fs", t1 - t0, time.time() - t1)

    @modal.enter(snap=False)
    def ready(self):
        import logging
        logging.getLogger("lingosync.start").info("container ready (snapshot=%s)", SNAPSHOT or "off")

    @modal.method()
    def warm(self, hold_s: int = WARM_HOLD_S):
        """Keeps this GPU for at most hold_s so a Start soon after is instant; ends as soon as a conversation starts."""
        import time
        end = time.time() + min(hold_s, WARM_HOLD_S)
        while time.time() < end and not self.active:
            time.sleep(1)
        return {"held_s": round(hold_s - max(0, end - time.time())), "conversation": self.active}

    @modal.asgi_app()
    def ws(self):
        import asyncio
        from fastapi import FastAPI, WebSocket
        from live import serve

        api = FastAPI()

        @api.websocket("/ws")
        async def endpoint(websocket: WebSocket):
            if self.active:                    # one conversation per GPU: a second tab is turned away
                await websocket.accept()
                await websocket.send_json({"type": "error", "message": "The translator is busy in another tab."})
                await websocket.close()
                return
            self.active = True
            try:
                await serve(websocket, self.engine, idle_s=IDLE_SECONDS, rate_per_hour=PRICE_PER_HOUR,
                            on_usage=record_usage, record_dir="/rec" if RECORD_SESSIONS else None,
                            on_record=lambda path: recordings.commit())
            finally:
                self.active = False

        @api.get("/health")
        async def health():
            return {"ok": True}

        return api


@app.function(image=web_image)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def web():
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, PlainTextResponse
    from fastapi.staticfiles import StaticFiles

    api = FastAPI(title="LingoSync")
    api.mount("/static", StaticFiles(directory="/root/frontend"), name="static")

    @api.get("/")
    async def index():
        return FileResponse("/root/frontend/index.html", headers={"Cache-Control": "no-cache"})

    @api.post("/warm")
    async def warm(client: str = ""):
        """'Get ready': start the GPU early. Limits: kill switch, one warm-up in flight, one per browser per
        10 minutes, WARM_PER_DAY in total. Never retried by the page."""
        import time
        now, day = time.time(), time.strftime("%Y-%m-%d")
        client = (client or "anonymous")[:64]
        if await warm_log.get.aio("disabled", False):
            return {"state": "disabled"}
        if await warm_log.get.aio("active_until", 0) > now:
            return {"state": "already", "seconds": round(await warm_log.get.aio("active_until", 0) - now)}
        if now - await warm_log.get.aio(f"client:{client}", 0) < WARM_PER_CLIENT_S:
            return {"state": "limited", "detail": "one warm-up per 10 minutes"}
        count = await warm_log.get.aio(f"day:{day}", 0)
        if count >= WARM_PER_DAY:
            return {"state": "limited", "detail": "daily warm-up limit reached"}
        await warm_log.put.aio(f"day:{day}", count + 1)
        await warm_log.put.aio(f"client:{client}", now)
        await warm_log.put.aio("active_until", now + WARM_HOLD_S + 60)     # + cold start
        await modal.Cls.from_name(APP_NAME, "Interpreter")().warm.spawn.aio(WARM_HOLD_S)
        return {"state": "warming", "seconds": WARM_HOLD_S}

    @api.get("/config.js")
    async def config():
        # tells the page where the GPU interpreter lives
        url = modal.Cls.from_name(APP_NAME, "Interpreter")().ws.get_web_url()
        ws = url.replace("https://", "wss://").rstrip("/") + "/ws"
        return PlainTextResponse(f"window.LINGOSYNC_WS = {ws!r};", media_type="application/javascript",
                                 headers={"Cache-Control": "no-cache"})

    return api
