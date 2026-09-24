# Changelog

All v1 work happened between 2026-09-22 and 2026-09-24 on a 16 GB M4 MacBook.
Numbers are measured, not estimated.

## v1.0: local prototype (2026-09-24)

### Continuous flow
- Interpreter-style playback: the English runs a steady 2.5 s behind the speaker, growing up to 8 s when
  processing is late, so it doesn't stop and start (`8d9c823`).
- MLX memory cache capped: the server stays at ~1.55 GB instead of growing to 7.5 GB and pushing the Mac
  into swap (`8d9c823`).
- Browser reports late parts, stalls and paused audio output to the server log; a watchdog restarts the
  output (`d2adb3c`).
- Keep-warm pass every 20 s while idle: the first sentence after a quiet period had waited 9.9–29.5 s (`39ab5cb`, `d2adb3c`).
- Pocket TTS 4-bit replaces Chatterbox as default: 6 s of English in ~0.8 s instead of 9–16 s (`2727706`).
- A backlog is merged into one pass, and the VAD cuts at a breath during long monologues (`2727706`, `d2adb3c`).

### Voice
- One locked voice per conversation, surviving reconnects, reloads and restarts (`be65357`).
- Fixed: Start and Reset voice sent `[object Object]` and never reset the voice (`d2adb3c`).
- The voice is learned only from speech in another language, never from the listener (`c6de11d`).
- Voice lock after 6 s of speech; later sentences reuse the cached fingerprint (`edb4ab5`).

### Recognition and translation
- Parakeet v3 replaces Whisper: 0.3–0.9 s instead of ~6 s, and no invented "Grazie." from room noise (`97db3ec`).
- Language detection from the transcript (lingua); short fragments keep the conversation's language (`97db3ec`).
- English lines are shown but not spoken (`c6de11d`).

### App
- Orange "device" UI: analog language wheels, tactile switches, settings drawer, live audio bars,
  colour transcript cards; phone layout (`1fc48d8`).
- Phone mode over HTTPS on the local Wi-Fi (`b729479`).
- Streamed speech played gaplessly through Web Audio, earphone routing kept (`edb4ab5`, `249b39f`).

### Tests
- `tests/ws_client.py`: streams clips over the WebSocket without a microphone.
- `tests/e2e_browser.py`: headless Chrome with a fake microphone; measures audible breaks.

## v0.1: first working pipeline (2026-09-22)
- Whisper → Argos → Chatterbox Turbo clone, web UI, smoke and bench tests (`f5e5c30`).
