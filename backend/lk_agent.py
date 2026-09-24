"""OpenConversation translator agent (PRD v2, milestone M1).

Joins a LiveKit room as the participant "translator", listens to each person's microphone track,
runs the same pipeline as v1 (VAD -> Parakeet -> Argos -> Pocket TTS clone) and publishes the
translated speech as a WebRTC audio track. Transcripts and voice state go over the data channel.

WebRTC now carries the audio (Opus, jitter buffer, reconnects); this agent only keeps the English a
steady interval behind the speaker and feeds it into the track at playback speed.

Run with a LiveKit server up (see run_lk.sh):  .venv/bin/python -m backend.lk_agent
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from livekit import api, rtc

from .pipeline import ENGINES, VoiceProfile, pipeline
from .vad import SAMPLE_RATE, Segmenter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
for _noisy in ("argostranslate", "argostranslate.utils", "stanza"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger("openconversation.agent")

LK_URL = os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880")
LK_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")        # livekit-server --dev defaults
LK_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
ROOM = os.environ.get("OC_ROOM", "openconversation")
ENGINE = os.environ.get("LINGOSYNC_ENGINE", "pocket_tts")
OUT_RATE = 24_000          # Pocket / Chatterbox output rate
FRAME_MS = 20              # size of the frames pushed into the WebRTC track
LAG_START, LAG_MIN, LAG_MAX = 2.0, 1.5, 8.0

executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")  # MLX: one thread only
VOICE = VoiceProfile.restore()  # one voice per conversation, survives agent restarts


class Listener:
    """One person whose speech we translate: their mic in, their translation track out."""

    def __init__(self, room: rtc.Room, identity: str, source: rtc.AudioSource):
        self.room = room
        self.identity = identity
        self.source = source
        self.cfg = {"source_lang": "auto", "target_lang": "en", "clone": True, "consent": False}
        self.seg = Segmenter()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.play: asyncio.Queue = asyncio.Queue()  # (kind, payload) for the pacer
        self.lag = LAG_START
        self.next_id = 0
        self.loop = asyncio.get_running_loop()
        self.tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------ data channel
    async def send(self, obj: dict) -> None:
        try:
            await self.room.local_participant.publish_data(
                json.dumps(obj), reliable=True, destination_identities=[self.identity], topic="events")
        except Exception:  # participant left
            pass

    def send_threadsafe(self, obj: dict) -> None:
        asyncio.run_coroutine_threadsafe(self.send(obj), self.loop)

    async def on_control(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "config":
            for k in ("source_lang", "target_lang", "clone", "consent"):
                if k in msg:
                    self.cfg[k] = msg[k]
            if not self.cfg["consent"]:
                self.cfg["clone"] = False
                VOICE.clear()
            await self.send({"type": "config", **self.cfg})
            await self.send(VOICE.state())
        elif t == "reset_voice":
            VOICE.clear()
            await self.send(VOICE.state())
        elif t == "flush":
            utt = self.seg.flush()
            if utt is not None:
                await self.enqueue(utt.audio)

    # ------------------------------------------------------------ audio in
    async def consume(self, track: rtc.Track) -> None:
        """Mic frames (10 ms from WebRTC) -> 100 ms chunks -> VAD -> utterance queue."""
        stream = rtc.AudioStream.from_track(track=track, sample_rate=SAMPLE_RATE, num_channels=1)
        buf: list[np.ndarray] = []
        n = 0
        async for ev in stream:
            pcm = np.frombuffer(ev.frame.data, dtype=np.int16).astype(np.float32) / 32768.0
            buf.append(pcm)
            n += len(pcm)
            if n >= SAMPLE_RATE // 10:
                utt = self.seg.feed(np.concatenate(buf))
                buf, n = [], 0
                if utt is not None:
                    await self.enqueue(utt.audio)

    async def enqueue(self, audio: np.ndarray) -> None:
        self.next_id += 1
        await self.queue.put((self.next_id, audio, time.monotonic()))
        await self.send({"type": "status", "state": "speech", "detail": f"utterance {self.next_id}"})

    # ------------------------------------------------------------ pipeline
    async def worker(self) -> None:
        while True:
            uid, audio, speech_end = await self.queue.get()
            merged = 1
            while not self.queue.empty():  # catch up: join everything that queued meanwhile
                _, more, speech_end = self.queue.get_nowait()
                audio = np.concatenate([audio, np.zeros(SAMPLE_RATE // 5, np.float32), more])
                merged += 1
            waited = time.monotonic() - speech_end
            cfg = dict(self.cfg)
            clone = bool(cfg["clone"] and cfg["consent"])

            def on_transcript(text, lang):
                self.send_threadsafe({"type": "segment", "id": uid, "source_text": text, "source_lang": lang,
                                      "target_text": None, "target_lang": cfg["target_lang"]})

            def on_translation(target, timings):
                self.send_threadsafe({"type": "segment", "id": uid, "source_text": None, "source_lang": None,
                                      "target_text": target, "target_lang": cfg["target_lang"], "timings": timings})

            def on_chunk(chunk, sr):
                asyncio.run_coroutine_threadsafe(self.play.put(("audio", (uid, speech_end, chunk, sr))), self.loop)

            try:
                res = await self.loop.run_in_executor(
                    executor, pipeline.run, audio, cfg["source_lang"], cfg["target_lang"], ENGINE,
                    clone, VOICE, on_transcript, on_translation, on_chunk)
            except Exception as e:  # noqa: BLE001
                log.exception("pipeline failed")
                await self.send({"type": "error", "message": f"Pipeline error: {e}"})
                continue
            await self.play.put(("end", uid))
            log.info("%s utt %d: %.1fs audio%s, waited %.1fs | %s | %s->%s%s | %r -> %r | lag %.1fs",
                     self.identity, uid, len(audio) / SAMPLE_RATE, f" ({merged} merged)" if merged > 1 else "",
                     waited, " ".join(f"{k[:-3]} {v}" for k, v in res.timings.items()), res.source_lang,
                     res.target_lang, f" [{res.skipped}]" if res.skipped else "", res.source_text[:70],
                     (res.target_text or "")[:70], self.lag)
            if res.skipped != "no_speech":
                await self.send({"type": "segment", "id": uid, "source_text": res.source_text,
                                 "source_lang": res.source_lang, "target_text": res.target_text,
                                 "target_lang": res.target_lang, "timings": res.timings, "skipped": res.skipped})
            if clone:
                await self.send(VOICE.state())

    # ------------------------------------------------------------ audio out (pacing)
    async def pacer(self) -> None:
        """Feeds translated speech into the WebRTC track, a steady `lag` behind the speaker.

        The AudioSource plays out in real time from its queue; WebRTC's jitter buffer smooths the
        network. Here we only decide *when* each stretch starts, like an interpreter.
        """
        current = None  # utterance id being played
        frame = OUT_RATE * FRAME_MS // 1000
        while True:
            kind, item = await self.play.get()
            if kind == "end":
                current = None if item == current else current
                continue
            uid, speech_end, chunk, sr = item
            if sr != OUT_RATE:
                chunk = np.interp(np.linspace(0, len(chunk), int(len(chunk) * OUT_RATE / sr), endpoint=False),
                                  np.arange(len(chunk)), chunk).astype(np.float32)
            idle = self.source.queued_duration <= 0.02
            if uid != current:
                current = uid
                slot = speech_end + self.lag
                now = time.monotonic()
                if idle and now < slot:
                    await asyncio.sleep(slot - now)  # hold until our steady distance behind the speaker
                elif idle and now > slot + 0.1:
                    late = now - slot
                    self.lag = min(LAG_MAX, self.lag + late + 0.3)
                    log.info("%s utt %d late by %.2fs -> lag %.1fs", self.identity, uid, late, self.lag)
                elif not idle and slot - now > 2.5:
                    self.lag = max(LAG_MIN, self.lag - 0.1)
            elif idle:
                # the track ran dry inside one stretch: an audible gap; keep more in hand next time
                self.lag = min(LAG_MAX, self.lag + 0.5)
                log.info("%s utt %d stalled inside a stretch -> lag %.1fs", self.identity, uid, self.lag)
            pcm = (np.clip(chunk, -1, 1) * 32767).astype(np.int16)
            for i in range(0, len(pcm), frame):
                part = pcm[i:i + frame]
                if len(part) < frame:
                    part = np.concatenate([part, np.zeros(frame - len(part), np.int16)])
                await self.source.capture_frame(rtc.AudioFrame(part.tobytes(), OUT_RATE, 1, frame))

    def start(self, track: rtc.Track) -> None:
        self.tasks += [asyncio.create_task(self.consume(track)), asyncio.create_task(self.worker()),
                       asyncio.create_task(self.pacer())]

    def stop(self) -> None:
        for t in self.tasks:
            t.cancel()


async def keep_warm_loop(listeners: dict) -> None:
    while True:
        await asyncio.sleep(20)
        if any(not li.queue.empty() for li in listeners.values()):
            continue
        await asyncio.get_running_loop().run_in_executor(executor, pipeline.keep_warm, ENGINE)


async def main() -> None:
    loop = asyncio.get_running_loop()
    log.info("Loading models ...")
    await loop.run_in_executor(executor, pipeline.warmup, ENGINE)

    room = rtc.Room()
    listeners: dict[str, Listener] = {}

    @room.on("track_subscribed")
    def _on_track(track: rtc.Track, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if track.kind != rtc.TrackKind.KIND_AUDIO or participant.identity in listeners:
            return
        asyncio.ensure_future(_add_listener(track, participant))

    async def _add_listener(track, participant):
        source = rtc.AudioSource(OUT_RATE, 1, queue_size_ms=30_000)  # room for a whole stretch
        out = rtc.LocalAudioTrack.create_audio_track(f"translation-{participant.identity}", source)
        opts = rtc.TrackPublishOptions()
        opts.source = rtc.TrackSource.SOURCE_MICROPHONE
        await room.local_participant.publish_track(out, opts)
        li = Listener(room, participant.identity, source)
        listeners[participant.identity] = li
        li.start(track)
        log.info("Translating %s", participant.identity)
        await li.send(VOICE.state())

    @room.on("participant_disconnected")
    def _on_left(participant: rtc.RemoteParticipant):
        li = listeners.pop(participant.identity, None)
        if li:
            li.stop()
            log.info("%s left", participant.identity)

    @room.on("data_received")
    def _on_data(packet: rtc.DataPacket):
        if packet.topic != "control" or packet.participant is None:
            return
        li = listeners.get(packet.participant.identity)
        try:
            msg = json.loads(packet.data)
        except ValueError:
            return
        if li:
            asyncio.ensure_future(li.on_control(msg))
        else:  # config can arrive before the mic track; keep it for later
            pending[packet.participant.identity] = msg

    pending: dict[str, dict] = {}

    token = (api.AccessToken(LK_KEY, LK_SECRET).with_identity("translator").with_name("Translator")
             .with_kind("agent")
             .with_grants(api.VideoGrants(room_join=True, room=ROOM, can_publish=True, can_subscribe=True,
                                          can_publish_data=True)).to_jwt())
    await room.connect(LK_URL, token)
    log.info("Translator joined room %r at %s (engine %s)", ROOM, LK_URL, ENGINE)
    asyncio.create_task(keep_warm_loop(listeners))

    while True:  # apply configs that arrived before the listener existed
        await asyncio.sleep(0.5)
        for ident in list(pending):
            if ident in listeners:
                await listeners[ident].on_control(pending.pop(ident))


if __name__ == "__main__":
    asyncio.run(main())
