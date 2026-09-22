# LingoSync AI — handover (paused 2026-09-22, resume 2026-09-24)

## State: end-to-end pipeline WORKS, browser UI written, not yet tested together

Verified with `.venv/bin/python -m tests.smoke` (Italian clip → English text → cloned-voice WAV):
- VAD segmenter → mlx-whisper (`whisper-large-v3-turbo`, detects `it`) → Argos it→en →
  Chatterbox Turbo clone → `tests/out_chatterbox_turbo_*.wav`. Output text was correct.
- Whisper turbo's own `task=translate` returned Italian unchanged (turbo is weak at translation),
  so translation now uses Argos Translate (offline), Whisper-translate only as fallback.

Frontend (`frontend/index.html`, `app.js`, `style.css`) was built by a Sonnet subagent against the
WebSocket protocol in `backend/server.py`; it has NOT yet been opened against the running server.

## Measured latency (steady state, 6.5 s Italian clip) — machine was heavily swapping

| model | ASR | MT | TTS |
|---|---|---|---|
| chatterbox-turbo-fp16 | 6–17 s | ~0 | 17–35 s |
| chatterbox-turbo-4bit | 6–8 s | ~0 | 9–16 s |

Root cause of slowness: 16 GB M4 with swap 17.5/18 GB used (Chrome etc.). Normal numbers for
these models are ~10x faster. Retest with other apps closed before optimising further.
`mlx-community/whisper-large-v3-turbo-4bit` repo is broken (npz load error); `whisper-small-mlx`
works (2.5 s under swap).

## Next steps (user asked for LOW latency + reuse a voice once captured)
1. `backend/pipeline.py`: default `LINGOSYNC_CHATTERBOX_MODEL` → `mlx-community/chatterbox-turbo-4bit`.
2. Voice lock: once `VoiceProfile` has ≥ 6 s, call `model.prepare_conditionals(ref, sample_rate=sr)`
   ONCE, then `generate(text)` with no `ref_audio` (reuses `model._conds`). Stop adding clips when
   locked. Add ws messages: server→client `{"type":"voice","state":"collecting|locked","seconds":x}`,
   client→server `{"type":"reset_voice"}`. Add a "Reset voice" button + status line in the UI
   (consent block is at `frontend/index.html:138`; message switch at `frontend/app.js:240`).
3. Streaming TTS: `model.generate(..., stream=True, streaming_interval=1.0)` yields chunks
   (`GenerationResult.audio`, `is_final_chunk`). Send each as `{"type":"audio","id",part,final,...}`
   via a callback from `Pipeline.run` → `Session.worker` (`send_threadsafe`). In `app.js`
   `handleAudio` (line ~421) store parts as a list per id; `replaySegment` should enqueue all parts.
4. `backend/vad.py`: `end_silence` 0.7→0.5, `max_utterance` 14→8 to bound turnaround.
5. Run `./run.sh`, open http://127.0.0.1:8765 in Chrome, pick laptop mic + earphones output, test
   live. Also write `tests/ws_client.py` that streams `tests/it_sample.wav` over `/ws` to test the
   server without a mic.
6. Optional: Kokoro engine (`kokoro`) for a no-clone ultra-fast mode; `qwen3_tts` for non-English targets
   (both untested, repos in `ENGINES`).

## Run
`./run.sh` (models already cached in ~/.cache/huggingface, ~7 GB). Smoke: `.venv/bin/python -m tests.smoke`.
Bench: `.venv/bin/python -m tests.bench [engine]`.
