"""Streams tests/it_sample.wav to a running server over /ws, like the browser does, without a mic.
Plays the clip `--times` times so the second pass exercises the locked voice.
Run (server up via ./run.sh): .venv/bin/python -m tests.ws_client [--times 2] [--url ws://127.0.0.1:8765/ws]
Writes the streamed reply audio to tests/out_ws_<id>.wav and prints end-of-speech → first-audio latency.
"""
import argparse, asyncio, base64, io, json, time
import numpy as np, soundfile as sf, websockets

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="ws://127.0.0.1:8765/ws")
ap.add_argument("--times", type=int, default=2)
ap.add_argument("--clips", nargs="+", default=None,
                help="play these wavs in order as a conversation (overrides --times)")
ap.add_argument("--engine", default="pocket_tts")
ap.add_argument("--realtime", action="store_true", help="pace frames at real time (default 4x)")
args = ap.parse_args()


async def main():
    clips = args.clips or ["tests/it_sample.wav"] * args.times
    pcms = []
    for path in clips:
        audio, sr = sf.read(path, dtype="float32")
        assert sr == 16000, f"{path} must be 16 kHz mono"
        pcms.append((np.clip(audio, -1, 1) * 32767).astype(np.int16))
    silence = np.zeros(16000 * 2, np.int16)
    step = 1600  # 100 ms, as the browser worklet sends
    pace = 0.1 if args.realtime else 0.025
    async with websockets.connect(args.url, max_size=None) as ws:
        await ws.send(json.dumps({"type": "config", "source_lang": "auto", "target_lang": "en",
                                  "engine": args.engine, "clone": True, "consent": True}))
        spoke_end: dict = {}
        parts: dict = {}
        done = asyncio.Event()
        expected = len(clips)

        async def reader():
            finished = 0
            async for raw in ws:
                m = json.loads(raw)
                t = m["type"]
                if t == "level":
                    continue
                if t == "segment" and m.get("skipped"):
                    finished += 1  # e.g. English: transcribed, nothing to play
                    if finished >= expected:
                        done.set()
                if t == "audio":
                    uid = m["id"]
                    if m.get("final"):
                        a = np.concatenate(parts[uid]["audio"])
                        sf.write(f"tests/out_ws_{uid}.wav", a, parts[uid]["sr"])
                        print(f"  [{uid}] audio done: {m['part']} parts, {len(a)/parts[uid]['sr']:.1f}s -> tests/out_ws_{uid}.wav")
                        finished += 1
                        if finished >= expected:
                            done.set()
                        continue
                    a, asr = sf.read(io.BytesIO(base64.b64decode(m["wav_base64"])), dtype="float32")
                    p = parts.setdefault(uid, {"audio": [], "sr": asr})
                    if not p["audio"]:
                        lat = time.time() - spoke_end.get(uid, time.time())
                        print(f"  [{uid}] FIRST AUDIO {lat:.2f}s after end of speech")
                    p["audio"].append(a)
                    continue
                print(" ", {k: v for k, v in m.items() if k not in ("engines", "languages")})
                if t == "error":
                    done.set()

        rtask = asyncio.create_task(reader())
        for n, pcm in enumerate(pcms, 1):
            for i in range(0, len(pcm), step):
                await ws.send(pcm[i:i + step].tobytes())
                await asyncio.sleep(pace)
            spoke_end[n] = time.time()
            for i in range(0, len(silence), step):
                await ws.send(silence[i:i + step].tobytes())
                await asyncio.sleep(pace)
        await asyncio.wait_for(done.wait(), timeout=600)
        rtask.cancel()
        await ws.send(json.dumps({"type": "reset_voice"}))  # never leave the test voice locked


asyncio.run(main())
