# Production plan: from prototype to web app to Google Meet extension

Status: draft, 2026-09-26. Builds on [PRD v2](PRD-v2.md) and [ARCHITECTURE.md](ARCHITECTURE.md).
Principle: **one backend, many thin clients.** The web app is built first; the Chrome extension is a
second client of the same backend, not a second product.

## 1. What "working properly" means (acceptance targets)

These are the numbers every release is tested against, automatically where possible.

| Area | Target | How we measure |
|---|---|---|
| Latency | Speaker pauses → translated voice starts: p50 ≤ 2.5 s, p95 ≤ 4 s | per-sentence timing in the agent log + browser test |
| Continuity | No audible break inside a stretch of translated speech | WebRTC concealment stats in `tests/e2e_lk.py` |
| Voice | Clone similarity ≥ 0.95 to the real speaker; natural expressiveness 0.85–1.15 | `tests/voice_eval` on every voice-model change |
| Recognition | Italian word error ≤ 8 %; English lines never re-spoken | Parakeet/Soniox on test clips; language-ID test set |
| Reliability | A 60-minute session survives network drops and provider reconnects without losing the voice | long-session soak test |
| Client | < 5 % CPU on a mid-range laptop or phone; ≤ 64 kbps each way | browser performance trace, WebRTC stats |
| Privacy | Explicit consent before any cloning; voice data deleted at session end unless saved; "AI voice" disclosure always visible | checklist + test |

## 2. Fix the core first (the translator itself)

1. **Speech detection on the device** (Silero VAD in the browser). Silence is never sent, and cuts land
   between words, not inside them. Server-side turn detection stays as a backstop.
2. **Sentence-aware chunking.** Translate at natural boundaries; carry the previous 2–3 sentences as
   context so pronouns, numbers and idioms come out right.
3. **Better translation.** Cloud: Soniox's streaming translation (no extra hop). Fallback: a small LLM with
   the running context and a per-team glossary (product names, people's names).
4. **Better voice.** Qwen3-TTS 0.6B on a GPU, streaming. Clone from 20–30 s of the cleanest speech
   (select segments, remove noise), not the first 6 s.
5. **One voice per room** (today the prototype has one voice per server), then per speaker (the team
   voice library, PRD v2 FR9).
6. **Graceful degradation.** If the GPU is busy or down: keep captions, switch to a light voice (Pocket or
   Kokoro), and tell the user. Never go silent without saying why.

## 3. Cloud backend (web app)

```
Browser / extension ──HTTPS──▶ Web app + API (auth, billing, session tokens)
        │                              │
        └──WebRTC (LiveKit)──▶ LiveKit ─┴─▶ Agent workers (CPU, one job per room, autoscaled)
                                              ├─▶ Soniox (speech + translation, API)
                                              ├─▶ TTS service (Qwen3-TTS on GPU pool, streaming, batched)
                                              └─▶ Postgres (users, orgs, usage, consent, voice metadata)
                                                  S3 EU (encrypted voice samples, auto-expiry) · Redis (session state)
```

| Component | Choice | Why |
|---|---|---|
| Web app + API | the existing FastAPI backend, grown into an API; static frontend on S3 + CloudFront | we already have it; no new framework needed yet |
| Sign-in | Amazon Cognito (or Clerk) | email and Google sign-in; Google sign-in helps the Meet extension later |
| Payments | Stripe: 5 free minutes, then subscription or per-hour credits | metering comes from the agent, not the browser |
| Real-time audio | LiveKit Cloud free tier at first (1,000 agent-min/month), self-hosted in the EU later | no ops at the start, same code later |
| Agents | LiveKit Agents framework on small CPU servers (ECS/Fargate), one job per room | isolation per meeting and team; scale by adding workers |
| Voice | a separate TTS service on GPU (EC2 g6 L4 in eu-central-1), streaming over a socket | GPUs scale independently of agents; one GPU serves several rooms |
| Speech + translation | Soniox API at launch; Parakeet on the same GPUs once they are busy enough | pay-per-use while small, cheaper at scale |
| Data | Postgres (RDS), S3 in the EU, Redis | usage metering, consent records, voice library |

**Trial and paywall:** the API issues a LiveKit token only if the account has minutes left; the agent
counts spoken minutes per session and stops translating when the trial runs out (with a clear message);
Stripe webhooks top up minutes. Abuse control: one trial per verified account and device.

**Scaling:** rooms are independent, so capacity = agent workers (cheap CPU) + GPU TTS workers.
The GPU pool scales on queue depth. The number that sets prices, *rooms per GPU*, comes from the
AWS GPU test. GPUs run only during active hours until paying users cover 24/7.

**Operations:** Docker images for every component, infrastructure as code (Terraform or AWS CDK), GitHub
Actions for tests and deploys, a staging environment, and per-stage latency tracing (OpenTelemetry) with
alerts on the targets in section 1.

## 4. Privacy and law (EU)

- **GDPR Art. 9:** a voice fingerprint for cloning is biometric data. Explicit, separate consent from
  *each* person whose voice is cloned; withdrawal deletes it immediately.
- **EU AI Act Art. 50** (in force since 2 Aug 2026): translated speech in a cloned voice must be disclosed as
  AI-generated: an "AI voice" label in the app, and a spoken or visual notice to the other party.
- **Data residency:** EU region (Frankfurt), EU vendors or signed data processing agreements; no voice data
  to non-EU jurisdictions without legal safeguards (this ruled out MiniMax for cloning).
- **Retention:** audio is processed in memory; voice samples expire with the session unless the user saves
  them to their team library.

## 5. Chrome extension for Google Meet (same backend)

| Step | How |
|---|---|
| Hear the meeting | `chrome.tabCapture` gives the Meet tab's audio (everyone else in the call) to an offscreen document (Manifest V3) |
| Send it for translation | the offscreen document runs the same LiveKit client as the web app and publishes the tab audio to the agent |
| Hear the translation | the translated voice plays in the user's headphones; the original call audio is replayed quietly underneath ("ducking"), because capturing the tab mutes it |
| Who is speaking | Meet mixes all voices into one stream, so the team voice library (voice fingerprints) tells speakers apart |
| Sign-in and minutes | the same account, trial and paywall as the web app |
| Your voice to them (later) | replacing the microphone inside Meet has no official API (page-level `getUserMedia` override or a virtual audio device); fragile and needs the other side's consent, so it comes after the listening mode works |
| Consent in calls | other participants must agree before their voice is cloned; until then they are translated in a neutral voice |

## 6. Order of work

| Phase | Deliverable | Done when |
|---|---|---|
| **P1 Core** | on-device VAD, sentence chunking with context, one voice per room, graceful degradation | local targets in section 1 met on the Mac |
| **P2 GPU voice** | Qwen3-TTS service on an AWS L4 GPU, streaming; measured rooms-per-GPU and cost per hour | voice targets met; price model known |
| **P3 Cloud web app** | sign-in, Soniox, LiveKit Cloud, agents on AWS, trial metering, Stripe, staging + production | a stranger can sign up, get 5 free minutes, pay, and use it |
| **P4 Meet extension (listen)** | tab capture → translation in your headphones with speaker voices | a real Meet call with an Italian speaker works end to end |
| **P5 Team voice library** | enrolment, live speaker matching, per-org library with consent | a 4-person meeting keeps 4 distinct voices |
| **P6 Meet extension (speak)** | your speech translated into the call in your voice | tested with consenting participants |

## 7. What we need from the owner

| When | Item |
|---|---|
| now | AWS set-up (credits, budget alert, GPU quota in Frankfurt, `aws configure`) |
| P2–P3 | Soniox API key |
| P3 | Stripe account; a domain name; LiveKit Cloud account (free) |
| P4 | Chrome Web Store developer account ($5); a Google account for test meetings |
| P5 | 2–3 colleagues who consent to record ~30 s each for testing |
