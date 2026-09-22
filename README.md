# LingoSync AI

Real-time in-office translator with zero-shot voice cloning. Put your earphones in,
let the laptop mic listen to the room, and hear each colleague in your language,
in their own voice. Everything runs locally on Apple Silicon (MLX); nothing leaves the machine.

Built by merging the ideas of two open-source projects:
- **RTranslator** (niedev): the conversation pipeline shape, Whisper ASR → translation → TTS into a headset.
- **VoiceStudio** (debpalash): the Apple-Silicon voice-cloning stack, `mlx-whisper` + `mlx-audio` (Chatterbox / Qwen3-TTS / Kokoro).

## Pipeline

```
laptop mic ─► browser (AudioWorklet, 16 kHz PCM) ─► WebSocket
   ─► VAD segmenter ─► mlx-whisper (transcribe + detect language)
   ─► translate (Argos Translate, offline CTranslate2 models)
   ─► mlx-audio TTS with the speaker's own utterances as the cloning reference
   ─► WAV back over WebSocket ─► your earphones (output device picker)
```

If the speaker is already talking in your target language the segment is shown but
not re-spoken, so mixed Italian/English meetings work naturally.

## Run

```sh
./run.sh            # http://127.0.0.1:8765
```

First start downloads about 2.5 GB of models from Hugging Face
(`whisper-large-v3-turbo`, `chatterbox-turbo-fp16`). Later starts are offline.

Use Chrome or Edge: the output-device picker (`setSinkId`) is Chromium-only.
In the app: pick the laptop mic as input, your earphones as output, tick the consent
box, press **Start listening**.

## Engines

| id | clones voice | output languages | notes |
|----|--------------|------------------|-------|
| `chatterbox_turbo` | yes | English | default, fastest clone |
| `qwen3_tts` | yes | many | multilingual clone, slower |
| `kokoro` | no | en it es fr pt hi ja zh | generic voice, fastest |

Environment overrides: `LINGOSYNC_ASR_MODEL`, `LINGOSYNC_CHATTERBOX_MODEL`,
`LINGOSYNC_QWEN_MODEL`, `LINGOSYNC_ENGINE`, `PORT`, `HOST`.

## Consent and privacy

Cloning is off until the consent box is ticked. Voice references are held in memory
for the session only and are never written to disk. All models run on-device.

## Test without a microphone

```sh
.venv/bin/python -m tests.smoke            # Italian clip → English in cloned voice
.venv/bin/python -m tests.smoke kokoro
```

## Layout

- `backend/server.py` FastAPI + WebSocket session handling
- `backend/pipeline.py` ASR, translation, TTS engines, voice profile
- `backend/vad.py` energy-based utterance segmenter
- `frontend/` static web app (no build step)
