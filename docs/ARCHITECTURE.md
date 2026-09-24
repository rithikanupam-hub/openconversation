# Architecture

Two parts: **v1 as built** (this repository today) and **v2 target** ([PRD v2](PRD-v2.md)),
plus what moves where.

## How voice cloning works (both versions)

1. **Capture a voice fingerprint once.** A speaker encoder listens to 6–60 s of the speaker and turns it
   into a compact representation: a *speaker embedding* (a few hundred numbers for timbre, pitch range,
   accent), and in some models a short *acoustic prompt* that carries speaking style.
2. **Speak any text in that voice.** The text-to-speech model gets the translated text plus the
   fingerprint and generates new speech in that voice. The person is not retrained on; this is
   "zero-shot" cloning.

The fingerprint is computed once per speaker and reused for every sentence. It is biometric data,
so it needs consent, clear storage and deletion.

---

## v1: local prototype (as built)

Everything runs on one Apple-Silicon Mac. The browser is the microphone, the screen and the speaker.

```
Browser (Chrome)                                   Python server on the Mac (FastAPI, one worker thread)
┌─────────────────────────────┐   WebSocket         ┌─────────────────────────────────────────────────────┐
│ mic → AudioWorklet 16 kHz   │ ── raw PCM ───────▶ │ VAD segmenter (energy based, soft cut 4.5 s/0.3 s)  │
│                             │                     │   ↓ queue (backlog merged into one pass)            │
│ orange device UI (ui.js)    │ ◀─ JSON: transcript │ Parakeet TDT v3 (ASR) + lingua (language ID)        │
│ Web Audio scheduler         │ ◀─ base64 WAV parts │   ↓ skip if already English                        │
│  (interpreter lag 2.5–8 s)  │    + "age"          │ Argos Translate (it→en, offline)                    │
│ → earphones (setSinkId)     │ ── control JSON ──▶ │   ↓                                                 │
└─────────────────────────────┘   (config, reset)   │ Pocket TTS 4-bit clone, streamed in 1 s parts       │
                                                    │ Voice profile: locked fingerprint, data/voice.wav   │
                                                    │ keep-warm every 20 s; MLX cache capped at 256 MB    │
                                                    └─────────────────────────────────────────────────────┘
```

| Component | File | Measured (16 GB M4) |
|---|---|---|
| Speech detection (VAD) | `backend/vad.py` | negligible |
| Speech recognition: Parakeet v3 (MLX) | `backend/pipeline.py` | 0.3–0.9 s per sentence warm; +2.4 GB |
| Language ID: lingua | `backend/pipeline.py` | < 0.2 s |
| Translation: Argos + Stanza | `backend/pipeline.py` | ~0.05 s warm; +0.4 GB; 69 s cold start under swap |
| Voice: Pocket TTS 4-bit (MLX) | `backend/pipeline.py` | 6 s of speech in ~0.8 s; first sound 0.2–0.5 s |
| Server, sessions, pacing | `backend/server.py` | whole app ~1.55 GB with the cache cap |
| Browser UI and playback | `frontend/` | gapless in the headless Chrome test |

**Limits that drove v2:** every device needs ~2.3 GB of models and a strong GPU; quality is capped by
small models; one Mac under memory pressure slows every stage 3–10×; 256 kbps raw audio up and ~500 kbps down.

---

## v2: thin clients + one server (target)

```
 CLIENTS (web, Chrome extension, iOS/Android)          SERVER (Mac for M1–M5, cloud GPU from M6)
 ┌──────────────────────────────────┐   WebRTC        ┌───────────────────────────────────────────────┐
 │ mic / Meet tab audio             │ ─ Opus 24 kbps ▶│ LiveKit server (rooms, WebRTC, reconnects)     │
 │ Silero VAD on device (~2 MB):    │                 │        │ audio track per participant           │
 │   silence is never sent          │                 │ Translator agent (Python, LiveKit Agents)     │
 │                                  │                 │  ├ streaming ASR (Parakeet or a service)       │
 │ plays translated track ◀─────────│◀─ Opus 24 kbps ─│  ├ translation (better than Argos: NLLB / LLM) │
 │ (WebRTC jitter buffer = smooth)  │                 │  ├ voice engine (pluggable):                  │
 │ transcripts, voice state ◀───────│◀─ data channel ─│  │    Pocket / Chatterbox / CosyVoice / MiniMax│
 │ start, reset voice, consent ────▶│── data channel ▶│  └ pacing (interpreter lag, never stop)        │
 └──────────────────────────────────┘                 │ Voice store: fingerprint or provider voice_id,│
                                                      │   consent record, deletion                     │
                                                      └───────────────────────────────────────────────┘
```

**Two-way:** each participant publishes one audio track. The agent translates each track into every
other participant's language using *that speaker's* fingerprint, and publishes one translated track per
listener. You hear English in their voice; they hear Italian in yours.

**Why LiveKit:** open-source WebRTC server with the jitter buffer, echo cancellation and reconnects we
built by hand in v1; client SDKs for web, iOS, Android, React Native and Flutter (one backend for every
platform); a Python Agents framework made for speech-in / speech-out pipelines.

### What happens to each v1 part

| v1 part | v2 |
|---|---|
| Browser AudioWorklet + raw PCM over WebSocket | LiveKit client SDK, Opus over WebRTC |
| Energy VAD on the server | Silero VAD on the device (no silence sent), server VAD as backstop |
| Parakeet / lingua / Argos (MLX, local) | Server-side; Argos to be replaced by a stronger translator |
| Voice stack from VoiceStudio (`mlx-audio`: Pocket, Chatterbox, Qwen3-TTS, Kokoro) | **MLX only runs on Apple Silicon.** Kept for Mac-hosted M1–M5. On a cloud NVIDIA GPU, the same model families run in their PyTorch versions (Chatterbox, CosyVoice), or the voice goes to MiniMax |
| Hand-built interpreter lag and gapless scheduler | WebRTC jitter buffer; pacing moves to the agent |
| Voice profile (`data/voice.wav`) | Voice store per speaker with consent record and retention |
| Orange device UI | Kept; rebuilt on the LiveKit client |

### Voicebox as the voice layer (candidate for M3)

[Voicebox](https://github.com/jamiepine/voicebox) (Jamie Pine, MIT) is a local-first voice studio with a
FastAPI backend and a REST API (`/generate`, `/transcribe`, `/profiles`). It fits v2 as the **voice engine
and voice-profile store** behind the translator agent, not as the transport or the real-time loop:

| Voicebox gives us | Why it matters for v2 |
|---|---|
| Seven voice engines behind one API: Qwen3-TTS, Chatterbox Multilingual (23 languages), Chatterbox Turbo, LuxTTS, TADA, Kokoro, Qwen CustomVoice | One switch between engines; **Chatterbox Multilingual speaks Italian**, needed for two-way |
| MLX on Apple Silicon **and** PyTorch CUDA/ROCm on Linux | The same voice layer runs on the Mac now and on a cloud GPU later (our `mlx-audio` code is Mac-only) |
| Voice profiles from **several samples**, import/export | Better clones than our single 6–12 s reference; a ready profile store |
| LuxTTS, advertised as ~150× real time on CPU | A lean option for a cheap server; to be benchmarked for clone quality |

Gaps to cover ourselves: its generation is an async queue, not a streaming real-time API (streaming is on its
roadmap), so the agent keeps the pacing, sentence splitting and interpreter lag; and its own Whisper
transcription is slower than Parakeet for our use.
