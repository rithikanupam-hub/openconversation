"""Replay a recorded meeting (mic.wav) through a deployed copy of the app, at real speed, like the browser does.
The server-side recorder saves the new session, so the result can be reviewed and compared with the original.

    LINGOSYNC_APP=lingosync-dev LINGOSYNC_TUNING=v1 ~/.local/bin/modal deploy cloud/modal_app.py
    .venv/bin/python cloud/replay_session.py recordings/2026-09-30/155528_4c0899f5/mic.wav
    .venv/bin/python cloud/review_session.py --volume lingosync-dev-recordings

Only the dev copy is allowed by default (the live app is for people). Costs GPU time for the length of the
recording plus Soniox (~$0.25 for 11 minutes).
"""
from __future__ import annotations

import argparse, asyncio, base64, contextlib, io, json, time
from pathlib import Path

import numpy as np
import soundfile as sf
import websockets

DEV_WS = "wss://aayushanupam1--lingosync-dev-interpreter-ws.modal.run/ws"
CHUNK_S = 0.1


def validate_output(messages):
    errors = [m for m in messages if m.get("type") == "error"]
    translated = {m["id"] for m in messages if m.get("type") == "segment" and (m.get("target_text") or "").strip()}
    audio = {m["id"] for m in messages if m.get("type") == "audio" and m.get("wav_base64")}
    finished = {m["id"] for m in messages if m.get("type") == "audio" and m.get("final")}
    for m in messages:
        if m.get("type") == "audio" and m.get("wav_base64"):
            try:
                samples, rate = sf.read(io.BytesIO(base64.b64decode(m["wav_base64"], validate=True)))
            except Exception as exc:
                raise RuntimeError(f"invalid audio for phrase {m.get('id')}") from exc
            if not len(samples) or not np.isfinite(samples).all() or rate <= 0:
                raise RuntimeError(f"empty/nonfinite audio for phrase {m.get('id')}")
    if errors or not translated or not audio or translated - finished:
        raise RuntimeError(f"replay incomplete: errors={errors}, translated={len(translated)}, "
                           f"audio={len(audio)}, unfinished={sorted(translated - finished)}")
    return {"translated_phrases": len(translated), "audio_phrases": len(audio)}


async def replay(path, url, src, tgt, clone, seconds, out=None):
    x, sr = sf.read(path, dtype="int16")
    if sr != 16000 or x.ndim != 1 or not len(x):
        raise ValueError("needs nonempty 16 kHz mono")
    if seconds is not None and seconds <= 0:
        raise ValueError("seconds must be positive")
    if seconds:
        x = x[:int(seconds * sr)]
    n = int(CHUNK_S * sr)
    counts, last_msg, messages = {}, time.monotonic(), []
    event_file = None
    if out is not None:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        event_file = Path(out).open("x")
    t_connect = time.monotonic()
    try:
        async with websockets.connect(url, open_timeout=300, max_size=None, ping_interval=None) as ws:
            print(f"connected after {time.monotonic() - t_connect:.1f} s (GPU start)", flush=True)
            await ws.send(json.dumps({"type": "config", "source_lang": src, "target_lang": tgt, "engine": "cloud",
                                      "clone": clone, "consent": clone, "client_id": "replay"}))
            t0 = time.monotonic()

            async def reader():
                nonlocal last_msg
                async for raw in ws:
                    if not isinstance(raw, str):
                        continue
                    m = json.loads(raw)
                    kind = m.get("type")
                    counts[kind] = counts.get(kind, 0) + 1
                    if kind not in {"segment", "audio", "error", "hello"}:
                        continue
                    messages.append(m)
                    if kind in {"segment", "audio", "error"}:
                        last_msg = time.monotonic()
                    if event_file:
                        event_file.write(json.dumps({"received_s": time.monotonic() - t0, **m}, ensure_ascii=False) + "\n")
                        event_file.flush()
                    if kind == "error":
                        raise RuntimeError(f"server error: {m}")

            rd = asyncio.create_task(reader())
            try:
                for i in range(0, len(x), n):
                    if rd.done():
                        await rd
                        raise RuntimeError("server disconnected before replay finished")
                    await asyncio.sleep(max(0.0, t0 + i / sr - time.monotonic()))
                    await ws.send(x[i:i + n].tobytes())
                    if i % (60 * sr) < n:
                        print(f"  {i / sr:5.0f} s sent, messages so far {counts}", flush=True)
                await ws.send(json.dumps({"type": "stop"}))
                drain_start = last_msg = time.monotonic()
                while time.monotonic() - last_msg < 10:
                    if rd.done():
                        await rd
                        break
                    if time.monotonic() - drain_start > 60:
                        raise RuntimeError("translation did not drain within 60 seconds")
                    await asyncio.sleep(0.1)
            finally:
                rd.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await rd
        result = validate_output(messages)
        print("done (received audio; not browser playout):", result, counts)
        return result
    finally:
        if event_file:
            event_file.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--url", default=DEV_WS)
    ap.add_argument("--source", default="it")
    ap.add_argument("--target", default="en")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--clone", action="store_true", help="clone only speakers whose voice use is authorized")
    mode.add_argument("--no-clone", action="store_true", help="neutral voice (default)")
    ap.add_argument("--out", help="new JSONL file for received text/audio; refuses overwrite")
    ap.add_argument("--seconds", type=float, help="replay only the first N seconds")
    ap.add_argument("--allow-live", action="store_true", help="permit a URL other than the dev copy")
    a = ap.parse_args()
    if a.url != DEV_WS and not a.allow_live:
        raise SystemExit("refusing a non-dev URL without --allow-live")
    asyncio.run(replay(a.wav, a.url, a.source, a.target, a.clone, a.seconds, a.out))
