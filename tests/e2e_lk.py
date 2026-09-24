"""M1 end-to-end test: headless Chrome with a fake microphone joins the LiveKit room via /lk.

Reports what the listener gets: transcript, voice state, and WebRTC's own receive statistics for the
translated track (bitrate, jitter, and "concealment": audio WebRTC had to invent because packets were
missing or late, i.e. audible gaps; silent concealment is just silence between stretches).
Run with ./run_lk.sh up:  .venv/bin/python -m tests.e2e_lk clip.wav [seconds]
"""
import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGE = "http://127.0.0.1:8765/lk"
clip = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "frontend/_e2e_clip.wav")
seconds = float(sys.argv[2] if len(sys.argv) > 2 else 60)


async def cdp(ws, _id=[0], **msg):
    _id[0] += 1
    msg["id"] = _id[0]
    await ws.send(json.dumps(msg))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == _id[0]:
            return r.get("result", r)


async def main():
    port = 9334
    chrome = subprocess.Popen([
        CHROME, "--headless=new", f"--remote-debugging-port={port}",
        f"--user-data-dir={tempfile.mkdtemp(prefix='oc-e2e-')}",
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={clip}", "--autoplay-policy=no-user-gesture-required",
        "--disable-features=AudioServiceSandbox,AudioServiceOutOfProcess", "--no-first-run", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                break
            except Exception:
                time.sleep(0.2)
        page = next(t for t in tabs if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            ev = lambda expr: cdp(ws, method="Runtime.evaluate",
                                  params={"expression": expr, "awaitPromise": True, "returnByValue": True})
            await cdp(ws, method="Page.navigate", params={"url": PAGE})
            for _ in range(60):
                if (await ev("!!window.LivekitClient && !!window.__oc"))["result"].get("value"):
                    break
                await asyncio.sleep(0.5)
            await ev("document.getElementById('start').click()")
            print(f"listening for {seconds:.0f}s ...")
            await asyncio.sleep(seconds)
            data = (await ev("JSON.stringify(window.__oc)"))["result"]["value"]
            await ev("document.getElementById('reset').click()")  # never leave the test voice locked
            await asyncio.sleep(1)
            return json.loads(data)
    finally:
        chrome.terminate()


def report(d):
    segs = {}
    for t, m in d["events"]:
        if m["type"] == "segment":
            s = segs.setdefault(m["id"], {})
            if m.get("source_text"):
                s.update(src=m["source_text"], lang=m.get("source_lang"))
            if m.get("target_text"):
                s.update(tgt=m["target_text"], skipped=m.get("skipped"))
        elif m["type"] == "voice":
            print(f"  {t/1000:6.1f}s voice {m['state']} {m['seconds']}s")
        elif m["type"] == "error":
            print(f"  {t/1000:6.1f}s ERROR {m['message']}")
    print("\nTranscript:")
    for k, s in sorted(segs.items()):
        tag = " (not spoken)" if s.get("skipped") else ""
        print(f"  [{k}] {s.get('lang')}: {s.get('src', '')[:60]!r} -> {s.get('tgt', '')[:60]!r}{tag}")
    st = d["stats"]
    if not st:
        print("\nNo WebRTC stats: the translated track never arrived.")
        return
    last = st[-1]
    kbps = [r["kbps"] for r in st if r["kbps"] > 0]
    audible = (last["concealed"] - last["silentConcealed"]) / 48000
    print(f"\nWebRTC receive (translated track): {last['total']/48000:.1f}s received, "
          f"bitrate median {sorted(kbps)[len(kbps)//2] if kbps else 0} kbps, jitter {last['jitterMs']} ms, "
          f"jitter buffer {last['bufferMs']} ms")
    print(f"  audible concealment (gaps WebRTC had to fill): {audible:.2f}s in {last['events']} events")


if __name__ == "__main__":
    report(asyncio.run(main()))
