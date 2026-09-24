"""End-to-end test in a real (headless) Chrome with a fake microphone playing a WAV file.

Measures what the listener experiences: when each translated part is scheduled to play, gaps
between consecutive parts (audible breaks), voice lock state, and the transcript.
Run with the server up:  .venv/bin/python -m tests.e2e_browser [clip.wav] [seconds]
The clip must be reachable by Chrome as a file; default frontend/_e2e_clip.wav.
"""
import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
APP = "http://127.0.0.1:8765/"
clip = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "frontend/_e2e_clip.wav")
seconds = float(sys.argv[2] if len(sys.argv) > 2 else 50)

# Installed before app.js runs: log every server message and every scheduled audio part.
PATCH = r"""
window.__e2e = {msgs: [], parts: [], logs: [], levels: 0, maxRms: 0, t0: performance.now()};
for (const k of ["error", "warn"]) {
  const orig = console[k];
  console[k] = (...a) => { window.__e2e.logs.push(k + ": " + a.map(String).join(" ")); orig.apply(console, a); };
}
window.addEventListener("error", (e) => window.__e2e.logs.push("onerror: " + e.message));
window.addEventListener("unhandledrejection", (e) => window.__e2e.logs.push("rejection: " + e.reason));
const now = () => +(performance.now() - window.__e2e.t0).toFixed(0);
const WS = window.WebSocket;
window.WebSocket = function (...a) {
  const ws = new WS(...a);
  ws.addEventListener("message", (ev) => {
    try {
      const m = JSON.parse(ev.data);
      if (m.type === "level") { window.__e2e.levels++; window.__e2e.maxRms = Math.max(window.__e2e.maxRms, m.rms); return; }
      if (m.wav_base64) m.wav_base64 = m.wav_base64.length;
      window.__e2e.msgs.push([now(), m]);
    } catch (e) {}
  });
  return ws;
};
window.WebSocket.prototype = WS.prototype;
Object.assign(window.WebSocket, {OPEN: 1, CLOSED: 3, CONNECTING: 0, CLOSING: 2});
const start = AudioBufferSourceNode.prototype.start;
AudioBufferSourceNode.prototype.start = function (when, ...rest) {
  window.__e2e.parts.push({at: now(), when, ctxNow: this.context.currentTime, dur: this.buffer ? this.buffer.duration : 0});
  return start.call(this, when, ...rest);
};
try {
  localStorage.setItem("lingosync:settings", JSON.stringify({
    v: 2, consent: true, clone: true, engine: "pocket_tts", sourceLang: "auto", targetLang: "en", muted: true}));
} catch (e) {}
"""


async def cdp(ws, _id=[0], **msg):
    _id[0] += 1
    msg["id"] = _id[0]
    await ws.send(json.dumps(msg))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == _id[0]:
            return r.get("result", r)


async def main():
    prof = tempfile.mkdtemp(prefix="lingosync-e2e-")
    port = 9333
    chrome = subprocess.Popen([
        CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={prof}",
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={clip}", "--autoplay-policy=no-user-gesture-required",
        "--disable-features=AudioServiceSandbox,AudioServiceOutOfProcess",
        "--no-first-run", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                break
            except Exception:
                time.sleep(0.2)
        page = next(t for t in tabs if t["type"] == "page")
        async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            await cdp(ws, method="Page.enable")
            await cdp(ws, method="Runtime.enable")
            await cdp(ws, method="Page.addScriptToEvaluateOnNewDocument", params={"source": PATCH})
            await cdp(ws, method="Page.navigate", params={"url": APP})
            ev = lambda expr: cdp(ws, method="Runtime.evaluate",
                                  params={"expression": expr, "awaitPromise": True, "returnByValue": True})
            for _ in range(120):  # wait until the app is connected and has its engine list
                ok = await ev("document.getElementById('connState').dataset.state === 'open' && !!document.getElementById('engineSelect').value")
                if ok["result"]["value"]:
                    break
                await asyncio.sleep(0.5)
            state = await ev("JSON.stringify({consent: document.getElementById('consentCheckbox').checked,"
                             " clone: document.getElementById('cloneToggle').checked,"
                             " engine: document.getElementById('engineSelect').value,"
                             " conn: document.getElementById('connState').dataset.state})")
            print("page:", state["result"]["value"])
            await ev("document.getElementById('startStopBtn').click()")
            t_start = time.time()
            print(f"listening for {seconds:.0f}s ...")
            await asyncio.sleep(seconds)
            await ev("document.getElementById('startStopBtn').click()")
            await asyncio.sleep(1)
            data = (await ev("JSON.stringify(window.__e2e)"))["result"]["value"]
            # never leave the test clip's voice locked for the real user
            await ev("document.getElementById('resetVoiceBtn').click()")
            await asyncio.sleep(0.5)
            errs = await ev("JSON.stringify([...document.querySelectorAll('.toast')].map(t=>t.textContent))")
            print("toasts:", errs["result"]["value"])
            return json.loads(data)
    finally:
        chrome.terminate()


def report(d):
    msgs, parts = d["msgs"], d["parts"]
    print(f"mic level messages: {d['levels']}, loudest: {d['maxRms']:.2f}; page errors: {d['logs'][:5]}")
    segs = {}
    for t, m in msgs:
        if m["type"] == "segment":
            s = segs.setdefault(m["id"], {})
            if m.get("source_text"):
                s.update(src=m["source_text"], lang=m.get("source_lang"), t_src=s.get("t_src", t))
            if m.get("target_text"):
                s.update(tgt=m["target_text"], skipped=m.get("skipped"))
        elif m["type"] == "voice":
            print(f"  {t/1000:6.1f}s voice {m['state']} {m['seconds']}s")
        elif m["type"] == "error":
            print(f"  {t/1000:6.1f}s ERROR {m['message']}")
    print("\nTranscript:")
    for k, s in sorted(segs.items()):
        tag = " (not spoken)" if s.get("skipped") else ""
        print(f"  [{k}] {s.get('lang')}: {s.get('src','')[:70]!r}\n       -> {s.get('tgt','')[:70]!r}{tag}")
    print(f"\nPlayback: {len(parts)} parts, {sum(p['dur'] for p in parts):.1f}s of English")
    gaps = []
    for a, b in zip(parts, parts[1:]):
        gap = b["when"] - (a["when"] + a["dur"])
        gaps.append(gap)
    breaks = [g for g in gaps if 0.05 < g < 1.5]  # audible stalls inside a stretch of speech
    pauses = [g for g in gaps if g >= 1.5]         # silences between separate turns
    late = [p for p in parts if p["when"] < p["ctxNow"] - 0.01]
    print(f"  back-to-back joins: {sum(1 for g in gaps if g <= 0.05)}, audible breaks (0.05–1.5s): {len(breaks)}"
          f" {[round(g, 2) for g in breaks]}, pauses between turns: {len(pauses)}")
    print(f"  parts scheduled in the past (clipped): {len(late)}")
    print("  ctx timeline (start–end):", " ".join(f"{p['when']:.1f}-{p['when']+p['dur']:.1f}" for p in parts))


if __name__ == "__main__":
    report(asyncio.run(main()))
