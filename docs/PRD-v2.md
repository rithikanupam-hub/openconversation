# PRD v2: OpenConversation, real-time voice translation on every device

Status: **draft for build**, 2026-09-24
Replaces: [PRD v1](PRD-v1.md) (local-only prototype)
Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

## Vision

Two people who don't share a language talk normally. Each hears the other in their own language,
**in the other person's own voice**, as a continuous stream, on a laptop, in a browser, inside
Google Meet, or on a phone.

## What changes from v1

| Topic | v1 | v2 |
|---|---|---|
| Where models run | On the user's laptop (~2.3 GB) | On a server; the device runs no models except a tiny speech detector |
| Platforms | Mac web page | Web app, Chrome extension (Google Meet), iOS/Android app |
| Direction | One way (Italian → English) | Two way (each side hears their own language) |
| Transport | WebSocket, raw PCM up, base64 WAV down | WebRTC with Opus (~24–32 kbps each way) |
| Voice cloning | Small on-device model | Server-side model or provider (e.g. MiniMax), same voice for the whole conversation |
| Flow | Built by hand (interpreter lag in the browser) | WebRTC jitter buffer + server-side pacing |
| Privacy | Nothing leaves the machine | Audio goes to our server; consent, retention and deletion become product requirements |

## Users and use cases

1. **In-person meeting** (from v1): the listener's phone or laptop hears the room and speaks the
   translation into their earphones.
2. **Google Meet call**: an extension translates the other participants for me, and optionally
   sends my speech to them translated in my voice.
3. **Face-to-face conversation on phones**: each person uses their own phone and earbuds.

## Functional requirements

| ID | Requirement |
|---|---|
| FR1 | Detect the spoken language automatically; never re-speak a line already in the listener's language |
| FR2 | Transcribe, translate and speak each stretch of speech as a continuous stream while the speaker keeps talking |
| FR3 | Clone each speaker's voice from their own speech, **only after that speaker's consent** |
| FR4 | Lock the voice once captured; keep it for the conversation until Reset voice, a new conversation, or consent withdrawn |
| FR5 | Show live transcripts (original and translation) alongside the audio |
| FR6 | Two-way: each participant hears everyone else in their chosen language |
| FR7 | Same backend for web app, Chrome extension and mobile app |
| FR8 | Delete a speaker's voice fingerprint and audio on request and at the end of a conversation (unless the user chooses to keep it) |

## Non-functional requirements (targets)

| ID | Target |
|---|---|
| NFR1 Client CPU | < 5 % of one core while listening on a mid-range phone; no ML models downloaded to the device except the speech detector (~2 MB) |
| NFR2 Bandwidth | ≤ 64 kbps up and ≤ 64 kbps down per participant |
| NFR3 Latency | Speaker pauses → translated speech starts: p50 ≤ 2.5 s, p95 ≤ 4 s |
| NFR4 Continuity | No audible break inside a stretch of translated speech (breaks only where the speaker paused) |
| NFR5 Voice | Listeners rate the clone "clearly the same person" in a blind A/B test against MiniMax (target: on par) |
| NFR6 Reliability | Survives network drops and reconnects without losing the locked voice |
| NFR7 Privacy | Consent per speaker; voice data encrypted at rest; retention defaults to the conversation only |

## Milestones

| M | Deliverable | Done when |
|---|---|---|
| M1 | Server agent on the Mac (LiveKit + current pipeline) | A browser test page hears Italian and plays English in the cloned voice over WebRTC |
| M2 | Lean web client (orange UI on LiveKit) | NFR1–NFR4 met on a laptop and on a phone browser |
| M3 | Voice store + pluggable voice engine | Switching Pocket / Chatterbox / MiniMax is one setting; FR3, FR4, FR8 met |
| M4 | Chrome extension for Google Meet | Hear other Meet participants translated in their voices |
| M5 | Mobile app (React Native or Flutter LiveKit SDK) | Face-to-face two-way on two phones |
| M6 | Cloud deployment (GPU server) | Runs without the Mac; cost per conversation-minute measured |

## Open questions

1. Voice engine: self-hosted GPU model (Chatterbox, CosyVoice) vs MiniMax API. This decides quality, cost per minute and data flow.
2. Cloud provider and region for the GPU server (EU for EU speakers' data?).
3. Translation engine: better than Argos for spoken language (NLLB, an LLM).
4. Consent flow for the *other* person in Meet and face-to-face (they must agree to be cloned).
5. Pricing and who pays for server time.

## Out of scope for v2

Offline mode on phones, more than ~4 participants per conversation, languages the chosen models don't support.
