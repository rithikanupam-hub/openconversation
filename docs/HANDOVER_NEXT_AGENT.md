# Handover: OpenConversation / LingoSync (for the next agent)

Written 2026-09-26. Read this first, then `docs/PRODUCTION_PLAN.md` (the build plan), `docs/PRD-v2.md`
(requirements) and `docs/ARCHITECTURE.md`. `HANDOVER.md` (repo root) is the older session-by-session log.

## 1. What the product is

Real-time spoken translation **in the speaker's own cloned voice**. An Italian colleague talks; the user
hears English in their earphones in that colleague's voice, as a continuous stream (interpreter-style: a
steady 2–3 s behind, never stopping). English speech is shown but not re-spoken. End goal: a cloud web app
(5 free minutes, then paywall), then a Chrome extension for Google Meet, then mobile; later two-way (the other
side hears Italian in the user's voice) and a team voice library (each colleague recognised and spoken in
their own voice).

The owner is non-technical-leaning: explain in plain words, give short concrete steps, confirm before
anything that costs money.

## 2. Where things are

| Item | Value |
|---|---|
| Local repo | `/Users/aayushanupam/Open Conversation/lingosync` |
| GitHub | `https://github.com/rithikanupam-hub/openconversation` (public) |
| Git identity for commits | `rithikanupam-hub <rithikanupam@gmail.com>` (set in the repo's git config) |
| Push status | local `main` is **8 commits ahead** of `origin/main`; push only when the owner asks. Push with the rithikanupam-hub account: `git -c credential.helper= -c "credential.helper=!f(){ echo username=x-access-token; echo password=\$(gh auth token -u rithikanupam-hub); }; f" push origin main` (the default `gh` account on this Mac is a different one) |
| Never push | branch `backup/pre-author-rewrite` (contains old email addresses) |
| Python env | `.venv/` (Python 3.12, uv). Models cached in `~/.cache/huggingface` |
| Machine | 16 GB M4 MacBook, often under heavy swap (OrbStack, VS Code, other apps). Numbers vary 3–10× with memory pressure |

## 3. What exists and works

**v1 local app** (`./run.sh`, http://127.0.0.1:8765): browser (orange "device" UI) → WebSocket → Python server
on the Mac: energy VAD → Parakeet v3 ASR (MLX) + lingua language ID → Argos translate (offline) → Pocket TTS
4-bit voice clone → streamed back, played with a steady interpreter lag. Phone mode: `./run.sh --phone`.

**v2 M1** (`./run_lk.sh`, http://127.0.0.1:8765/lk): the same pipeline as a LiveKit agent over WebRTC
(`backend/lk_agent.py`, local `livekit-server --dev`, test page `frontend/lk.html`). Tested end to end.

Current process state when this was written: `livekit-server` and the web server are running; the agent
(`backend.lk_agent`) was stopped for a benchmark. Restart everything with `./run_lk.sh`.

**Tests**
- `tests/ws_client.py`: streams WAV clips over the v1 WebSocket (`--engine`, `--realtime`, `--clips`).
- `tests/e2e_browser.py` (v1) and `tests/e2e_lk.py` (M1): headless Chrome with a fake microphone
  (`--use-file-for-fake-audio-capture`), report transcript, voice state and audible breaks.
- `tests/voice_eval/`: voice-clone benchmark (`run_model.py <model>`, `score.py`, `expressiveness.py`),
  two public-domain LibriVox Italian readers as references; outputs and refs are git-ignored.

## 4. Decisions already made (don't re-litigate)

| Decision | Why / evidence |
|---|---|
| Architecture v2: thin clients + one backend (LiveKit + agent + GPU services) | lean client for web/extension/mobile; see PRD v2 |
| **Voice: Qwen3-TTS 0.6B** (cloud GPU) | voice eval: similarity 0.97 avg (0.985 best; real person vs self = 0.98, different person = 0.78), best clarity (4 % WER), natural expressiveness (0.94), cheapest of the high-quality open models. 8-bit keeps quality (0.97/0.98). Too slow on the Mac (1.8× real time at 8-bit) → needs GPU |
| Local edition keeps Pocket TTS for live use | only model faster than real time on the M4 (0.23×) |
| Cloud speech + translation: **Soniox** at launch | $0.12/h, translation bundled in the same stream (research report) |
| Local ASR: NVIDIA Parakeet v3 | owner prefers it; 0.3–0.9 s, no hallucinations on noise |
| Transport: LiveKit (Cloud free tier first, self-host in the EU later) | SDKs for web/iOS/Android; jitter buffer; Python agents |
| Cloud: **AWS eu-central-1 (Frankfurt)** | owner's choice; EU data residency for biometric voice data |
| MiniMax ruled out for cloning | China-based, no EU adequacy → GDPR transfer problem |
| Voicebox (jamiepine/voicebox) | candidate voice layer/profile store (supports MLX and CUDA); not adopted yet |

Research: `reports/Realtime voice translation API stack.md` (deep research, cited), notes in
`research_notes/` (git-ignored).

## 5. AWS access, budget and rules

- Account `346560662986` (shared with the owner's other app "scrapbook"), SSO profile `scrapbook-eu`,
  role AdministratorAccess, region `eu-central-1`.
- CLI helper: `sh /Users/aayushanupam/scrapbook-web/ops/aws-cli.sh <args> --profile scrapbook-eu --region eu-central-1`
  (a permission rule in `lingosync/.claude/settings.local.json` allows it without prompts).
- If the SSO token expired, ask the owner to run in their prompt:
  `! sh /Users/aayushanupam/scrapbook-web/ops/aws-cli.sh sso login --profile scrapbook-eu --use-device-code`
- **Rules:** read-only checks any time. **Ask the owner before anything that costs money.** Tag every
  resource `Project=openconversation`. Log every change in `ops/AWS_LOG.md`. Never touch billing settings,
  payment methods, IAM Identity Center users or root settings.
- **Budget:** AWS budget `openconversation-monthly-10usd` ($10/month, email alerts 50/80/100 % + forecast;
  account-wide because the `Project` tag is not yet a cost-allocation tag). The owner wants to keep this app
  cheap (≈ half of a $100 credit, and the credits may have expired: ask the owner to confirm in Billing → Credits).
  Month-to-date spend at handover: $0.00.
- **GPU quota:** requests submitted 2026-09-26 for 8 vCPU "Running On-Demand G and VT instances" (L-DB2E81BA)
  and 8 vCPU "All G and VT Spot Instance Requests" (L-3819A6DF); status `CASE_OPENED` (AWS Support reviewing).
  Check: `… service-quotas list-requested-service-quota-change-history --service-code ec2 --query "RequestedQuotas[].[QuotaName,Status]" --output text`
- GPU pricing (approx.): g6.xlarge (1× L4) ~$0.9–1.1/h on-demand in Frankfurt; spot roughly half. RunPod L4
  ~$0.40/h is the cheaper alternative for pure testing.

## 6. What the owner still owes

| Item | Needed for |
|---|---|
| Reply to AWS Support if they ask about the GPU quota ("real-time speech translation prototype, one g6.xlarge in eu-central-1, a few hours per week") | GPU test |
| Soniox API key in `lingosync/.env` as `SONIOX_API_KEY=…` (`.env` is git-ignored) | cloud STT + translation |
| Later: Stripe account, domain, LiveKit Cloud account (free), Chrome Web Store dev account ($5), Google account for Meet tests | P3–P4 |
| Later: 2–3 consenting colleagues recording ~30 s each | team voice library (P5) |

## 7. The work, in order

Acceptance targets for all phases: `docs/PRODUCTION_PLAN.md` §1 (latency p50 ≤ 2.5 s / p95 ≤ 4 s speech-end →
voice-start, no audible breaks, clone similarity ≥ 0.95, 60-min session survives drops, client < 5 % CPU,
≤ 64 kbps each way, consent + "AI voice" disclosure).

### P1 — Core fixes (no AWS needed, start here)
1. **One voice per room.** `backend/lk_agent.py` and `backend/server.py` use a module-level `VOICE` shared by
   all sessions, persisted to `data/voice.wav`. Make it per room/session (key by LiveKit room name), persist
   per room under `data/voices/<room>.wav`, keep the reset rules (Reset voice, fresh Start, consent off).
2. **Speech detection in the browser.** Silero VAD via ONNX Runtime Web in `frontend/lk.html` (and later the
   orange UI); send audio only while speaking; keep the server energy VAD (`backend/vad.py`) as a backstop.
   Known issue it fixes: WebRTC mic processing makes the energy VAD cut mid-sentence.
3. **Context-aware translation.** Pass the previous 2–3 source/target sentences; per-team glossary. Cloud:
   Soniox streaming translation; local: keep Argos but add a small LLM option.
4. **Better clone reference.** Collect 20–30 s, choose the cleanest segments (energy/SNR), instead of the
   first 6 s (`VoiceProfile` in `backend/pipeline.py`).
5. **Graceful degradation.** If TTS is slow or down: keep captions, fall back to Pocket/Kokoro, tell the user.
6. **Bitrate ≤ 64 kbps**: set Opus max bitrate / DTX on the agent's published track (`TrackPublishOptions`).
7. Wire the orange UI (`frontend/index.html`, `app.js`, `ui.js`) onto LiveKit (today it speaks the v1
   WebSocket protocol); keep `lk.html` as the test page.
Done when: `tests/e2e_lk.py` shows no mid-word cuts on the test clip, 0 audible breaks, voice isolated per room.

### P2 — Qwen3-TTS on an AWS GPU (needs quota approval + owner OK, ~$3–5)
1. Build `services/tts/`: a small streaming TTS server (WebSocket or gRPC: text + voice id in, 24 kHz PCM
   chunks out) running **Qwen3-TTS 0.6B Base** with the official PyTorch/CUDA package (MLX is Mac-only),
   voice conditioning cached per voice id, batching across requests. Dockerfile included.
2. `ops/gpu.sh start|stop|status`: launch a tagged g6.xlarge (spot for tests) in eu-central-1 with a
   Deep Learning AMI, 60 GB gp3, security group open only to the owner's IP, user-data that starts the
   container, and an **idle auto-shutdown after 30 min**. Log it in `ops/AWS_LOG.md`.
3. Benchmark on the GPU: rerun `tests/voice_eval` (same references) to confirm similarity; measure
   real-time factor, time-to-first-audio, and **how many concurrent streams stay under 1.0× real time**.
4. Point the agent's pocket/qwen engine at the remote TTS service (`LINGOSYNC_ENGINE=qwen_remote`).
Deliverable: a short results table + cost per user-hour → decides pricing. Stop the GPU afterwards.

### P3 — Cloud web app (owner go-ahead + Stripe + domain)
Per `docs/PRODUCTION_PLAN.md` §3: API (grow FastAPI) with sign-in (Cognito or Clerk), LiveKit tokens only if
the account has minutes, agent-side usage metering (trial 5 min, then stop with a message), Stripe
webhooks to add minutes, Postgres (RDS) for users/usage/consent, S3 EU for voice samples with expiry,
agents on small CPU servers (ECS/Fargate) via LiveKit Agents dispatch, GPU TTS pool, Docker + IaC
(Terraform/CDK) + GitHub Actions + staging. Consent (GDPR Art. 9) and AI-voice disclosure (EU AI Act Art. 50)
in the UI.

### P4 — Chrome extension for Google Meet (listen mode)
MV3: `chrome.tabCapture` → offscreen document → same LiveKit client → translated voice in the user's
headphones, original call replayed quietly underneath (capture mutes the tab). Same accounts/minutes.

### P5 — Team voice library
Enrol colleagues (15–30 s, consent), store WavLM/ECAPA speaker embedding + clone reference per org; per
utterance compute the embedding (~20–50 ms) and pick the nearest voice above a threshold (eval shows 0.98
same-person vs 0.78 different-person). Overlapping speech: voice the dominant speaker.

### P6 — Meet extension (speak mode) and two-way
Your speech translated into the call in your voice (page-level `getUserMedia` override or virtual device;
fragile; consent from participants). Needs Italian output: Qwen3-TTS/Chatterbox Multilingual both speak Italian.

## 8. Gotchas learned the hard way

- **Never run tests while the owner is using the app live** (check the latest `utt N:` lines in the server
  log first). A test once competed with a live session; a server restart once wiped a live voice.
- **Tests must leave no voice behind**: `ws_client.py` and `e2e_*.py` send `reset_voice` at the end; the
  voice persists in `data/voice.wav` otherwise, and the next real session speaks in the test voice.
- **MLX rules**: load and use a model on the same thread (one-thread executor); cap the MLX cache
  (`LINGOSYNC_CACHE_MB`, default 256) or it grows to ~7 GB and pushes the Mac into swap; the server pins
  memory (`LINGOSYNC_WIRED_GB`) and runs a keep-warm pass every 20 s so idle models aren't paged out.
- `frontend/app.js` `wsSend` must JSON-stringify objects (a bug once sent `[object Object]`).
- Bump `?v=N` on the asset links in `frontend/index.html` after CSS/JS changes (cache); the server also sends
  `Cache-Control: no-cache`. Google Fonts load non-blocking (a blocking stylesheet delayed startup 48 s).
- `tests/ws_client.py` defaults to `--engine pocket_tts` (it was hard-coded to Chatterbox once, which
  skewed measurements).
- Argos/stanza logging floods the log; the logger is re-silenced after Argos import.
- The Claude-in-Chrome extension was not connected in this environment; headless Chrome via CDP works
  (`tests/e2e_*.py`). Installing third-party tools from GitHub archives was blocked by the safety
  classifier (Agent-Reach); ask the owner to run such installs themselves.
- Keep `lingosync/.env`, `data/`, `certs/`, `logs/`, `research_notes/`, voice-eval audio out of git (already ignored).
