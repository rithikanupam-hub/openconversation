# Public translation comparison — 11 October 2026

Five public clips, 94.7 seconds total, replayed at original speed once per version; neutral English voices. Three development clips and two frozen holdouts. Baseline: deployed dev as found (deployment ap-ID7Nv6Mq6e2L9uBCMJ4xeX), not a recovered code snapshot. Candidate: candidate-fingerprints.json. Production was not deployed.

**Translation text was identical on 5/5 clips. This run does not demonstrate improved translation accuracy.** The deterministic code checks establish fixes for agreements, mixed-language gating, reference selection and reset races; these short neutral-voice clips do not exercise all those fixes.

Corpus source, revision, transcript metadata and input hashes: [VoxPopuli manifest](voxpopuli-selection.json). Audio files listed in the manifest are not bundled.

## Measured results

| Metric | Baseline | Candidate | Interpretation |
|---|---:|---:|---|
| Clips with validated translated audio | 5 / 5 | 5 / 5 | Transport completion, not correctness |
| Translated / voiced phrases | 36 | 36 | Different segmentation can change this count |
| Median first audio receipt from clip start | 4.82 s | 4.74 s | Excludes connection/GPU startup |
| Largest modeled playback queue | 2.69 s | 3.95 s | Serial playback reconstructed from received chunks; not browser telemetry |
| Median modeled finish after source clip ends | 5.02 s | 4.69 s | Not measured headphone playback |

Source transcript disagreement against the supplied corpus text is a diagnostic only. It is not reported as translation accuracy: clip 5 recognition includes a Greek introduction absent from its Italian reference; other clip edges and reference words need audio validation. The English reference translations were drafted by the agent, not independently bilingual-validated gold.

## Per-clip translations and audio

The linked received WAVs reconstruct serial playback at arrival times. Their silence/queue timing is modeled; they are provided to compare generated speech, not as a recording of browser output.

### 1. Victims and stalking (development)

Input: 19.22 s. First audio receipt: 4.63 → 4.51 s.

**Corpus Italian reference:** Sofferenze e disagio delle vittime, che per certi versi ancora alcuni Stati faticano a riconoscere nei propri codici penali, ne abbiamo discusso anche poco fa, per quanto riguarda il tema dello stalking un reato che non è riconosciuto in tutti gli Stati membri all'interno dell'Unione.

**Baseline English:** Without the suffering and discomfort of the victims who, in some ways, some states still struggle to recognize in their own criminal codes. We also discussed it a little while ago regarding the topic of stalking: a crime that is not recognized in all the member states within the Union.

**Candidate English:** Without the suffering and discomfort of the victims who, in some ways, some states still struggle to recognize in their own criminal codes. We also discussed it a little while ago regarding the topic of stalking: a crime that is not recognized in all the member states within the Union.

Audio artifacts are retained locally and are not included in this source publication.

### 2. Council negotiations (development)

Input: 17.54 s. First audio receipt: 4.82 → 4.74 s.

**Corpus Italian reference:** Desidero sottolineare che, nell'ultima fase, siamo riusciti a imporre al Consiglio di negoziare anche quei temi legati all'accordo sulle Prospettive finanziarie, temi che i capi di Stato e di governo avevano, in maniera arbitraria, inserito nella famosa negotiation box

**Baseline English:** I want to emphasize that in the final phase we managed to impose on the Council to negotiate those issues as well related to the financial outlook agreement, those issues that the heads of state and government had arbitrarily included in the famous "negotiazione box."

**Candidate English:** I want to emphasize that in the final phase we managed to impose on the Council to negotiate those issues as well related to the financial outlook agreement, those issues that the heads of state and government had arbitrarily included in the famous "negotiazione box."

Audio artifacts are retained locally and are not included in this source publication.

### 3. Institutional duty (development)

Input: 15.20 s. First audio receipt: 6.14 → 6.29 s.

**Corpus Italian reference:** Ho voluto prendere la parola questa sera perché le istituzioni tutte hanno il dovere di accendere i riflettori su questo fenomeno orribile e vergognoso, perché non sia solo oggetto di studi e approfondimenti, ma soprattutto oggetto di politiche di prevenzione e di contrasto.

**Baseline English:** Tonight, because all institutions have the duty to shine the spotlight on this horrible, shameful phenomenon, so that it is not only the subject of studies and in-depth examinations, but above all the subject of prevention policies and countermeasures. We must.

**Candidate English:** Tonight, because all institutions have the duty to shine the spotlight on this horrible, shameful phenomenon, so that it is not only the subject of studies and in-depth examinations, but above all the subject of prevention policies and countermeasures. We must.

Audio artifacts are retained locally and are not included in this source publication.

### 4. 40 / 2030 emissions target (holdout)

Input: 17.14 s. First audio receipt: 4.96 → 4.97 s.

**Corpus Italian reference:** L'obiettivo europeo di ridurre del 40 le emissioni entro il 2030 passa attraverso impegni trasversali a tutti i settori dell'economia e a tutti i livelli istituzionali, dagli Stati alle comunità locali.

**Baseline English:** The European goal of cutting by 40% emissions by 2030 requires cross-cutting commitments across all sectors of the economy, and at all institutional levels, from the states to local communities.

**Candidate English:** The European goal of cutting by 40% emissions by 2030 requires cross-cutting commitments across all sectors of the economy, and at all institutional levels, from the states to local communities.

Audio artifacts are retained locally and are not included in this source publication.

### 5. Transport and mixed-language introduction (holdout)

Input: 25.62 s. First audio receipt: 4.07 → 3.91 s.

**Corpus Italian reference:** Signor Presidente, onorevoli colleghi, la partita del trasporto, in particolare del trasporto su strada, sarà una delle più interessanti per verificare la capacità di innovazione dell'Unione europea. Abbiamo parlato con dovizia di particolari di tutte le sfide legate ai nuovi carburanti, alla necessità di limitare le emissioni

**Baseline English:** Thank you. He has the floor for 1.5 minutes Mr. Salinis. Thank you, Mr. President. The transport sector, in particular, road transport, will be one of those most interesting ways to assess the ability of the European Union to innovate. We discussed plenty of details about all the challenges related to new fuels.

**Candidate English:** Thank you. He has the floor for 1.5 minutes Mr. Salinis. Thank you, Mr. President. The transport sector, in particular, road transport, will be one of those most interesting ways to assess the ability of the European Union to innovate. We discussed plenty of details about all the challenges related to new fuels.

Audio artifacts are retained locally and are not included in this source publication.

## Meaning review and remaining gaps

- Victims/stalking: both outputs add “Without” at the opening, following the recognizer’s “Senze” instead of the corpus “Sofferenze.” Treat this as an unresolved opening-recognition/meaning defect; do not patch the translator with this expected sentence.
- Council: core negotiation, institutional actors and arbitrary inclusion survive. “Impose on the Council to negotiate” is awkward; “negotiazione box” is a terminology error. No improvement in this run.
- Institutional duty: obligation, prevention and “not only … but above all” survive. Opening and closing differ from the supplied reference; validate original audio boundaries before deciding omission versus annotation mismatch.
- Emissions: reduction direction, 40 and 2030 are preserved. The corpus transcript omits the percent unit; recognition and translation both supply it, so that unit requires an audio check rather than automatic credit or penalty.
- Transport: the recognizer logs a Greek introduction, followed by Italian; it is translated. The supplied reference does not cover that introduction and includes an ending not present in the recognized stream. Exclude this clip from a clean ASR-WER score until boundaries are verified.

## Metrics to continue tracking

| Metric | Current status | Acceptance / next measurement |
|---|---|---|
| Critical meaning: numbers, negation, obligations, agreements | Agent text review above; no independent accuracy percentage | Bilingual audio-grounded review and explicit omission/addition counts |
| Recognition WER | Reference mismatch diagnostic only | Verify audio/transcript boundaries first |
| First translated sound | Socket receipt measured | Add actual browser playout timestamps |
| Sustained meaning lag, median / p95 | Not established by these short clips | Existing provisional goals ≤2.5s / ≤4s with independently aligned meaning |
| Playback backlog and finish delay | Reconstructed above | Long continuous speech with actual render telemetry |
| Speaker attribution and neutral fallback coverage | Not evaluated here | Four-speaker AMI acoustic test; Italian room test still separate |
| Clone resemblance and naturalness | Not evaluated; neutral voices used | Consented voice test with human review |
| Reset, consent, missing/corrupt output | Model-free checks pass; all ten real clip runs complete | Browser cancellation/reconnect/long-session tests remain |
| Startup and cost | Recorded in logs and cost-and-shutdown.json | Separate first-deploy snapshot from warm starts; retain budget cap |

## Decision

Keep this as a candidate, not a claimed translation-quality upgrade. The next accuracy work is source-onset/clip-boundary diagnosis and terminology, followed by a long independent replay. The owned-model architecture review remains a proposal; this run did not compare alternative models. The separate architecture research is retained locally.

No human listening verdict, generated-speech word-error score, broad language claim or production release is established by this test.

## Cost and shutdown

Dev stopped; zero containers verified. Allocated compute estimate **$0.15**, plus $0.10 Soniox and $0.50 build/snapshot/storage/network allowances gives **$0.75 conservative accounting**, below the approved $2 cap. This is not an invoice. Exact windows and assumptions: [ledger](cost-and-shutdown.json). All ten server summaries confirm no cloned voices. Baseline first connection 11.9s; candidate fresh-snapshot connection 80.8s; subsequent connections approximately 0.4–0.6s. First-deploy snapshot creation is not a like-for-like cold-start regression.

## Publication scope

The source branch preserves the fingerprinted Python candidate. `cloud/terms.json` is a generic public example; the private test vocabulary is excluded, so this checkout is not a byte-identical deployment bundle. Raw recordings, transport logs, private data and credentials are excluded. Neutral voice asset provenance is in `../../cloud/VOICES.md`; the legacy default is byte-identical to the already-tracked `tests/en_sample.wav`, but its provenance remains unresolved. Do not treat publication as approval to use that voice commercially.
