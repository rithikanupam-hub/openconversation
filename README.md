# OpenConversation (LingoSync prototype)

Real-time spoken translation in the speaker's own voice. Put your earphones in, let the laptop
listen to the room, and hear each colleague in your language, in their voice, as a continuous stream.

This repository is the **v1 local prototype**: everything runs on one Apple-Silicon Mac (MLX).
The next version moves the models to a server so the same product can run as a web app,
a Chrome extension for Google Meet, and a mobile app.

- Product: [PRD v1](docs/PRD-v1.md) (what was built and learned) → [PRD v2](docs/PRD-v2.md) (what's next)
- Design: [Architecture](docs/ARCHITECTURE.md), including how voice cloning works
- History: [CHANGELOG](CHANGELOG.md)

Built on ideas from **RTranslator** (niedev), the conversation pipeline shape, and **VoiceStudio**
(debpalash), the Apple-Silicon voice-cloning stack (`mlx-audio`).

## Pipeline (v1)

```
laptop mic ─► browser (AudioWorklet, 16 kHz PCM) ─► WebSocket
   ─► VAD segmenter ─► Parakeet v3 speech recognition + language detection
   ─► skip if already in your language ─► Argos Translate (offline)
   ─► Pocket TTS voice clone, streamed in 1 s parts
   ─► browser plays them gaplessly, a steady 2.5–8 s behind the speaker ─► your earphones
```

## Run

```sh
./run.sh            # http://127.0.0.1:8765
./run.sh --phone    # also https://<mac-ip>:8765 for a phone on the same Wi-Fi
```

The first start downloads the models from Hugging Face (a few GB). Later starts work offline.
Use Chrome or Edge on the Mac (the earphone picker uses `setSinkId`).
In the app: choose the microphone and your earphones in **settings**, switch on **consent** and
**clone voice**, and press the orange button.

## Voice engines

| id | clones voice | output | notes |
|----|--------------|--------|-------|
| `pocket_tts` | yes | English | default, ~7× faster than real time (4-bit) |
| `chatterbox_turbo` | yes | English | closer clone, slower than real time on a 16 GB Mac |
| `qwen3_tts` | yes | many | multilingual clone, slower (untested) |
| `kokoro` | no | en it es fr pt hi ja zh | generic voice, fastest |

Environment overrides: `LINGOSYNC_ENGINE`, `LINGOSYNC_ASR` (`parakeet` or `whisper`),
`LINGOSYNC_POCKET_MODEL`, `LINGOSYNC_CHATTERBOX_MODEL`, `LINGOSYNC_CACHE_MB`, `LINGOSYNC_WIRED_GB`,
`PORT`, `HOST`.

## Consent and privacy

- Cloning stays off until the consent switch is on.
- The voice is learned only from speech in another language, never from the listener.
- Once locked, the speaker's voice sample is saved on this Mac as `data/voice.wav`, so it survives a
  reconnect or restart. It is deleted by **Reset voice**, a fresh **Start**, or switching consent off.
  `data/` is never committed.
- All models run on this machine; no audio leaves it in v1.

## Tests

```sh
.venv/bin/python -m tests.smoke                       # Italian clip → English in the cloned voice
.venv/bin/python -m tests.ws_client --realtime --clips tests/it_sample.wav tests/en_sample.wav
.venv/bin/python -m tests.e2e_browser clip.wav 60     # headless Chrome with a fake microphone
```

The browser test reports audible breaks between played parts and the server log shows one line per
sentence (`utt N: … waited … | asr … tts … | it->en | text -> translation`).

## Layout

- `backend/server.py`: FastAPI + WebSocket sessions, backlog merging, keep-warm
- `backend/pipeline.py`: speech recognition, language ID, translation, voice engines, voice profile
- `backend/vad.py`: energy-based utterance segmenter
- `frontend/`: static web app (`app.js` logic, `ui.js` device UI), no build step
- `docs/`: PRDs and architecture
