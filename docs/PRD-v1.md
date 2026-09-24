# PRD v1: LingoSync, local in-office translator (prototype)

Status: **built and tested, superseded by [PRD v2](PRD-v2.md)**
Period: 2026-09-22 to 2026-09-24
Note: there was no written PRD at the start. This document records the v1 intent as built
(first commit `5f838f9`) and what testing showed.

## Problem

In a meeting with colleagues who speak Italian, an English speaker misses what is said.
Human interpreters are expensive and generic machine voices make it hard to follow who is speaking.

## Goal

Put in earphones, let the laptop listen to the room, and hear each colleague in your language,
**in their own voice**, with everything running **locally on the laptop** and nothing leaving it.

## Users

One listener (English) in an in-person meeting with Italian speakers, using a MacBook (Apple Silicon).

## Scope (v1)

| Area | v1 requirement |
|---|---|
| Capture | Laptop microphone, chosen in the browser |
| Pipeline | Speech recognition → translation → voice-cloned speech |
| Output | Translated speech in the listener's earphones (output device picker) |
| Language handling | Auto-detect the source; do not re-speak lines already in the listener's language |
| Cloning | Zero-shot clone from the speaker's own speech, only after a consent checkbox |
| Privacy | All models on-device; voice reference held in memory only |
| UI | Web page: mic and output pickers, consent, live transcript |

## Out of scope (v1)

Cloud processing, mobile apps, browser extensions, two-way translation (the other side hearing
Italian), several speakers with separate voices.

## Stack chosen

Whisper (`mlx-whisper`) → Argos Translate → Chatterbox Turbo (`mlx-audio`), a FastAPI + WebSocket
server and a browser client. The shape came from RTranslator; the Apple-Silicon voice stack came
from VoiceStudio.

## What testing showed (the reasons for v2)

Measured on a 16 GB M4 MacBook, in tests and two live sessions:

| Finding | Evidence | Consequence |
|---|---|---|
| Whisper was slow and invented phrases | ~6 s per sentence; "Grazie." ×5 from room noise | Replaced by Parakeet v3 (0.3–0.9 s, silent on noise) |
| Chatterbox clones well but is slower than speech | 6 s of English took 9–16 s | The English fell further behind (27 s wait); replaced by Pocket TTS (~0.15× real time) |
| Stopping and starting playback | Per-sentence start and stop, queueing | Streaming, merged backlog, interpreter-style steady lag |
| Memory | Models ~2.3 GB; MLX cache grew to 7.5 GB in 10 min; Mac in full swap | Cache capped; but **every device needs GBs of models** |
| Voice quality | Pocket clone judged below MiniMax by the user | Small on-device models limit clone quality |
| Target platforms | Web app, Chrome extension (Meet), mobile planned | A 2.3 GB, CPU/GPU-heavy client cannot ship there |

**Conclusion:** the pipeline works and the continuous-flow design is proven, but running the models on
each user's device cannot meet the quality, battery and platform goals. v2 moves the heavy work to a
server and makes every client thin.
