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

## Session 2 (2026-09-22 evening): next steps 1–5 done
- Default TTS = `chatterbox-turbo-4bit`. VAD `end_silence` 0.5, `max_utterance` 8.
- Voice lock: `VoiceProfile.conds` caches Chatterbox conditionals once ≥ 6 s is captured (~0.7 s one-off);
  later utterances reuse it. ws: server→`{"type":"voice","state","seconds","needed"}`, client→`{"type":"reset_voice"}`.
  UI: voice status line + "Reset voice" button under the consent block.
- Streaming TTS (`streaming_interval=1.0`): server sends `audio` parts `{id,part,final:false,wav_base64}` then
  `{id,part:n,final:true}`. Translation text is pushed (`on_translation`) before TTS starts.
- Frontend playback is now Web Audio: parts decoded and scheduled gaplessly into a MediaStreamDestination
  that feeds the hidden `<audio>` (so `setSinkId` earphone routing still works). "Play again" replays all parts.
- `tests/ws_client.py` streams the Italian clip over /ws with no mic (`--times 2`, `--realtime`).

Measured via ws_client (still ~12 GB swap in use):
| | ASR | MT | TTS first audio | TTS total |
|---|---|---|---|---|
| utt 1 (locks voice) | 6.2 s | 2.2 s (Argos first load) | 2.0 s | 9.8 s |
| utt 2 (locked) | 6.9 s | ~0 | 1.4 s | 9.9 s |
Now ASR is the bottleneck. End of speech → first audio ≈ 8–10 s under swap.

## Session 3 (2026-09-22 night): Parakeet ASR, fewer false translations
Live test log showed (1) Whisper inventing "Grazie." / "Grazie a tutti." from room noise (5x), each spoken aloud,
(2) English speech forced into broken Italian, (3) ASR ~6 s. Changes:
- ASR default = NVIDIA Parakeet TDT 0.6B v3 (`parakeet-mlx`, 25 European langs). Returns nothing on silence/noise.
  Language from the transcript via `lingua` (restricted to Parakeet's languages); P(en) >= 0.3 => treated as English (silent).
  Short lines (<= 3 words) keep the conversation's language (`VoiceProfile.last_lang`) — "Campania." was scored Romanian.
  Whisper remains for non-European sources or `LINGOSYNC_ASR=whisper`, with a noise-phrase filter.
- Argos warmed at startup. Argos logging silenced.
Measured (ws_client --realtime, IT/EN/IT): ASR 0.3–0.9 s (was 6 s), end of speech -> first audio 1.6–3.4 s (was 9.7 s).
Chatterbox generates slower than real time here (6 s of audio takes ~9–10 s). Client pre-buffer added (session 3b):
first part of each utterance waits `App.prebuffer` (starts 1.0 s, +gap on a mid-sentence stall, -0.1 s per smooth one, 0.5–3 s).
Was: streamed playback may pause
between parts on long sentences. Options: small client pre-buffer, or free memory (swap ~14 GB).

## Session 4 (2026-09-23): device UI + phone
- New UI: orange "device" (index.html/style.css), `frontend/ui.js` drives it (analog wheels over the hidden
  `<select>`s, settings drawer, audio bars from #levelBar, palette cards, voice arc). app.js logic unchanged
  apart from the playback route. Asset links carry `?v=N`: bump it when changing CSS/JS; server also sends no-cache.
- Phone: `./run.sh --phone` → https://<mac-ip>:8765 (self-signed cert in certs/). Without setSinkId (iOS),
  playback goes straight to AudioContext.destination; volume is a GainNode on every route.
  Not yet tried on a real phone.

## Session 5 (2026-09-23 evening): continuous flow
Live meeting log (18:16–18:32) showed the English falling further behind (waits up to 27 s, "si salta un po'")
because the browser still used Chatterbox (RTF ~1.5–1.8, slower than speech). Changes:
- New default TTS `pocket_tts` = Kyutai Pocket TTS, `mlx-community/pocket-tts-4bit`: clones, streams 1 s parts,
  RTF ~0.15 (6 s of English in ~0.8 s). Chatterbox stays selectable in settings.
- Voice lock is engine-independent: `VoiceProfile.locked_ref` + per-engine `conds` cache.
- Worker merges everything queued while busy into one pass (never falls behind in steps).
- VAD soft cut: after 3 s, a 0.2 s breath closes the utterance (translation starts mid-monologue); hard cut 8 s.
- Unsure short lines in an unheard language keep the conversation language (a lone "Um" had triggered a Latvian
  package download mid-meeting).
- One log line per utterance (`utt N: … waited … | asr … tts … | it->en | src -> tgt`); argos/stanza silenced.
- MLX memory pinned (`LINGOSYNC_WIRED_GB`, default 4) + TTS warm-up generation at startup.
- Frontend settings v2 moves saved `chatterbox_turbo` to the new default once; prebuffer starts at 0.6 s.
- tests/ws_client.py now takes `--engine` (it was hard-coded to Chatterbox, which skewed earlier measurements).
Measured (ws_client --realtime, 3 Italian clips back to back, Pocket 4-bit): end of speech -> first English
0.5–0.8 s (2.2 s first sentence), TTS 0.8 s per 6 s, no queue wait.

## Session 6 (2026-09-24): breaks in live use
- Bug: Start/Reset voice sent "[object Object]" (wsSend didn't stringify) -> the voice never reset; the 15:28
  session spoke in the voice my e2e test had locked. wsSend now stringifies; tests reset the voice at the end.
- MLX buffer cache grew to ~7 GB in 10 min live -> full swap, MT 0.7–4.6 s, TTS 4–10 s, queue 7–13 s.
  `mx.set_cache_limit` (LINGOSYNC_CACHE_MB, 256) keeps the server at ~1.55 GB (`mem` in the utt log).
- Interpreter-style playback: server sends `age` (s since the speaker finished) with every audio part; the
  browser starts each stretch at speech_end + App.lag (2.5 s start, grows on late/stall up to 8 s, eases 0.1 s).
- Browser reports `late` / `stall` / `revived` / `context` as `client playback:` lines in the server log.
- VAD soft cut 4.5 s / 0.3 s breath, hard 9 s. Keep-warm runs even with no page open.
- tests/e2e_browser.py: headless Chrome with a fake mic (file) — measures gaps between played parts.
- The Mac itself is the limit when OrbStack/Docker + IDEs fill swap (16/16.4 GB used): every stage 3–10x slower.

## Next steps
1. Live test in Chrome: `./run.sh`, http://127.0.0.1:8765, laptop mic + earphones, consent on. Not yet done
   (needs a person and a mic). Listen to `tests/out_ws_*.wav` for voice quality.
2. Cut ASR: retest `whisper-large-v3-turbo` with Chrome closed; else `LINGOSYNC_ASR_MODEL=mlx-community/whisper-small-mlx`
   (2.5 s under swap). Consider warming Argos at startup (first MT was 2.2 s).
3. Optional: Kokoro no-clone fast mode; `qwen3_tts` for non-English targets (untested).

## Run
`./run.sh` (models already cached in ~/.cache/huggingface, ~7 GB). Smoke: `.venv/bin/python -m tests.smoke`.
Bench: `.venv/bin/python -m tests.bench [engine]`.
