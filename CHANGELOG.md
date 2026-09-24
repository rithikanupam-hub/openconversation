# Changelog

All v1 work happened between 2026-09-22 and 2026-09-24 on a 16 GB M4 MacBook.
Numbers are measured, not estimated.

## v2 M1: translator agent over WebRTC (2026-09-25)
- `backend/lk_agent.py`: the pipeline runs as a LiveKit participant ("translator"). It subscribes to each
  person's microphone track and publishes a translated audio track; transcripts and voice state go over
  the data channel; the interpreter lag moved from the browser into the agent.
- `frontend/lk.html` test page (`/lk`), `/api/lk-token` (dev keys), `run_lk.sh` (LiveKit server + web + agent).
- `tests/e2e_lk.py`: headless Chrome with a fake mic; reads WebRTC receive statistics.
- Measured on the 43 s Italian/English clip: 9 Italian stretches translated and spoken, English left silent,
  voice locked once, no queueing (wait 0.0 s), steady 2.0 s lag never had to grow; WebRTC jitter 1 ms,
  jitter buffer 77 ms, 0.16 s of audible concealment in 4 events over 59 s. Bitrate 84 kbps (target ≤ 64, for M2).
- Known: WebRTC's mic processing changes levels, so the energy VAD sometimes cuts mid-sentence
  ("…parliamo della." / "per il prossimo…"); M2 moves speech detection to Silero VAD on the device.

## v1.0: local prototype (2026-09-24)

### Continuous flow
- Interpreter-style playback: the English runs a steady 2.5 s behind the speaker, growing up to 8 s when
  processing is late, so it doesn't stop and start (`1e27cf3`).
- MLX memory cache capped: the server stays at ~1.55 GB instead of growing to 7.5 GB and pushing the Mac
  into swap (`1e27cf3`).
- Browser reports late parts, stalls and paused audio output to the server log; a watchdog restarts the
  output (`e2d7a29`).
- Keep-warm pass every 20 s while idle: the first sentence after a quiet period had waited 9.9–29.5 s (`2de6a37`, `e2d7a29`).
- Pocket TTS 4-bit replaces Chatterbox as default: 6 s of English in ~0.8 s instead of 9–16 s (`cfa4a00`).
- A backlog is merged into one pass, and the VAD cuts at a breath during long monologues (`cfa4a00`, `e2d7a29`).

### Voice
- One locked voice per conversation, surviving reconnects, reloads and restarts (`ce85f00`).
- Fixed: Start and Reset voice sent `[object Object]` and never reset the voice (`e2d7a29`).
- The voice is learned only from speech in another language, never from the listener (`f6de0cc`).
- Voice lock after 6 s of speech; later sentences reuse the cached fingerprint (`430a1c8`).

### Recognition and translation
- Parakeet v3 replaces Whisper: 0.3–0.9 s instead of ~6 s, and no invented "Grazie." from room noise (`4142d1e`).
- Language detection from the transcript (lingua); short fragments keep the conversation's language (`4142d1e`).
- English lines are shown but not spoken (`f6de0cc`).

### App
- Orange "device" UI: analog language wheels, tactile switches, settings drawer, live audio bars,
  colour transcript cards; phone layout (`eb773a7`).
- Phone mode over HTTPS on the local Wi-Fi (`062e64e`).
- Streamed speech played gaplessly through Web Audio, earphone routing kept (`430a1c8`, `7364219`).

### Tests
- `tests/ws_client.py`: streams clips over the WebSocket without a microphone.
- `tests/e2e_browser.py`: headless Chrome with a fake microphone; measures audible breaks.

## v0.1: first working pipeline (2026-09-22)
- Whisper → Argos → Chatterbox Turbo clone, web UI, smoke and bench tests (`5f838f9`).
