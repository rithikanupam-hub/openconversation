"""Real-time test of the full stack on the GPU box:  python stream_sim.py --asr nemotron-320 [--only L1_workshop]

Each recording is fed at speaking pace. Three workers run at once, as they would live:
  recogniser  -> stable Italian text as it is spoken (asr_stream.py)
  segmenter   -> releases a phrase when it is safe to translate: punctuation, a pause, a long clause at a comma,
                 or a deadline so nothing waits too long (a deadline cut is counted as "forced")
  interpreter -> translates the phrase with a short memory (mt.py), voices it (voice_stream.py, speaker profile),
                 and queues it for playback. Phrases that pile up are merged into one. When the queue of unplayed
                 English grows, the English is asked to be brief and is played up to 1.25x faster.
Playback is simulated on the same clock: a phrase plays when it's ready and the previous one has finished.

Delay of meaning, per phrase: max(play start - when its Italian began, play end - when its Italian ended),
using the word timeline of the real recording. Targets (owner, 2026-09-27): English starts <= 5 s after the
speaker starts; trailing ~5 s is accepted for launch, "never more than 5 s behind" is the goal (finish-time target dropped).
Writes out/stream_<asr>/<id>/{segments.json, metrics.json, english.wav (as heard), stereo.wav (L Italian, R English)}.
"""
import argparse, json, queue, re, threading, time
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np, soundfile as sf

HERE = Path(__file__).parent
HS = HERE / "humanset"
SR16 = 16000

# segmenter settings
MIN_WORDS, PHRASE_MIN, COMMA_WORDS, MAX_WORDS = 3, 5, 6, 14
PAUSE_S, DEADLINE_S = 0.45, 2.5       # pause = real silence in the audio (not a gap in the recogniser's output)
LONG_PAUSE_S = 1.0                    # a short pause ends a phrase only once it has PHRASE_MIN words
# playback queue control: (backlog above, playback rate)
BRIEF_BACKLOG_S = 1.5
RATES = ((3.5, 1.3), (2.0, 1.2), (1.0, 1.1))
RATE_PROFILES = {"gentle": RATES, "eager": ((2.5, 1.3), (1.5, 1.2), (0.5, 1.1))}   # eager: drain the queue sooner


def norm_words(text):
    return [w for w in (re.sub(r"[^\w]", "", x.lower()) for x in text.replace("'", " ").replace("’", " ").split()) if w]


class Segmenter:
    """Turns a stream of stable text into phrases. Pure logic: feed()/tick() return released phrases."""

    def __init__(self, comma_words=None, deadline=None, phrase_min=None, use_pause=True, quiet_s=None,
                 end_quiet_s=None):
        """Defaults: module settings. Soniox mode: comma_words=1, deadline=4 (its English already comes in
        clean clauses, so cut at its punctuation and only fall back to a deadline rarely)."""
        self.comma_words = COMMA_WORDS if comma_words is None else comma_words
        self.deadline = DEADLINE_S if deadline is None else deadline
        self.phrase_min = PHRASE_MIN if phrase_min is None else phrase_min
        self.use_pause = use_pause     # off for Soniox: its English lags the audio, so silence doesn't mark its ends
        # web app (Soniox): release when the translation has gone quiet for quiet_s, or end_quiet_s after Soniox
        # signalled an endpoint (<end>) - whole sentences instead of comma fragments (2026-10-01)
        self.quiet_s, self.end_quiet_s, self.endpoint = quiet_s, end_quiet_s, False
        self.raw = ""            # text not yet split into complete words
        self.pending = []        # [(word, arrival_time)]
        self.last_arrival = None
        self.speaker = None

    def feed(self, text, t, speaker=None):
        out = []
        if speaker is not None and speaker != self.speaker:
            if self.raw.strip():                       # a half-received word belongs to the previous speaker
                self.pending.append((self.raw.strip(), t)); self.raw = ""
            if self.pending:                           # a new speaker always starts a new phrase
                out.append(self._release(len(self.pending), "speaker", t))
            self.speaker = speaker
        self.raw += text
        parts = self.raw.split()
        complete = parts if self.raw[-1:].isspace() else parts[:-1]
        self.raw = "" if self.raw[-1:].isspace() else (parts[-1] if parts else "")
        for w in complete:
            self.pending.append((w, t))
        self.last_arrival = t
        return out + self._cut_on_text()

    def mark_endpoint(self):
        self.endpoint = bool(self.pending or self.raw.strip())     # only ends words already received

    def _release(self, n, reason, t):
        words, self.pending = self.pending[:n], self.pending[n:]
        if not self.pending:
            self.endpoint = False
        return {"it": " ".join(w for w, _ in words), "reason": reason, "t_first_word": words[0][1],
                "t_last_word": words[-1][1], "t_release": t, "speaker": self.speaker}

    def _cut_on_text(self):
        out = []
        while True:
            ends = [i for i, (w, _) in enumerate(self.pending) if re.search(r"[.?!;:]$", w) and i + 1 >= MIN_WORDS]
            if ends:
                out.append(self._release(ends[0] + 1, "punctuation", self.pending[ends[0]][1])); continue
            if len(self.pending) >= MAX_WORDS:
                commas = [i for i, (w, _) in enumerate(self.pending) if w.endswith(",") and i + 1 >= MIN_WORDS]
                n = commas[-1] + 1 if commas else MAX_WORDS
                out.append(self._release(n, "comma" if commas else "long", self.pending[n - 1][1])); continue
            if len(self.pending) >= self.comma_words and self.pending[-1][0].endswith(","):
                out.append(self._release(len(self.pending), "comma", self.pending[-1][1])); continue
            return out

    def tick(self, t, final=False, silence_s=0.0):
        """silence_s: how long the speaker has been silent (from the audio), counted up to the point the
        recogniser has had time to deliver the words spoken before the silence."""
        n = len(self.pending) + bool(self.raw.strip())
        paused = self.use_pause and (silence_s >= LONG_PAUSE_S or (silence_s >= PAUSE_S and n >= self.phrase_min))
        if (final or paused) and self.raw.strip():
            self.pending.append((self.raw.strip(), t)); self.raw = ""
        if not self.pending:
            return []
        if final:
            return [self._release(len(self.pending), "end", t)]
        if paused:
            return [self._release(len(self.pending), "pause", t)]
        if self.quiet_s is not None and self.last_arrival is not None:
            quiet = t - self.last_arrival
            if self.raw.strip() and (quiet >= self.quiet_s or (self.endpoint and quiet >= self.end_quiet_s)):
                self.pending.append((self.raw.strip(), self.last_arrival)); self.raw = ""
            if self.endpoint and quiet >= self.end_quiet_s:
                return [self._release(len(self.pending), "endpoint", t)]
            if quiet >= self.quiet_s and (len(self.pending) >= self.phrase_min
                                          or re.search(r"[.?!,;:]$", self.pending[-1][0])):
                return [self._release(len(self.pending), "quiet", t)]
        if t - self.pending[0][1] >= self.deadline and len(self.pending) >= self.phrase_min:
            if self.quiet_s is not None:                 # cut at the last clause mark, keep the rest growing
                marks = [i for i, (w, _) in enumerate(self.pending) if re.search(r"[,;:]$", w) and i + 1 >= MIN_WORDS]
                if marks:
                    return [self._release(marks[-1] + 1, "deadline", t)]
            return [self._release(len(self.pending), "deadline", t)]
        return []


class Player:
    """Simulated playback on the shared clock (seconds from the start of the recording)."""

    def __init__(self):
        self.end = 0.0

    def backlog(self, t):
        return max(0.0, self.end - t)

    def schedule(self, ready_t, gen_end_t, dur):
        start = max(self.end, ready_t)
        end = max(start + dur, gen_end_t)          # if generation were slower than speech, playback would stall
        self.end = end
        return start, end


def align(segments, timeline):
    """Give each released phrase its Italian time span from the word timeline of the recording."""
    ref = [t[0] for t in timeline]          # [word, start, end] or [word, start, end, speaker]
    p = 0
    for s in segments:
        tgt = norm_words(s["it"])
        lo, hi = max(0, p - 5), min(len(ref), p + 2 * len(tgt) + 20)
        blocks = [b for b in SequenceMatcher(None, tgt, ref[lo:hi], autojunk=False).get_matching_blocks() if b.size]
        matched = sum(b.size for b in blocks)
        if tgt and matched / len(tgt) >= 0.4:
            i, j = lo + blocks[0].b, lo + blocks[-1].b + blocks[-1].size
            s["src_start"], s["src_end"], s["aligned"] = timeline[i][1], timeline[j - 1][2], True
            p = j
        else:       # fall back to arrival times; words arrive after they are spoken, so this understates the lag
            s["src_start"], s["src_end"], s["aligned"] = s["t_first_word"], s["t_last_word"], False
    return segments


def voiced_frames(a16, frame=0.02):
    """True for 20 ms frames with speech energy (threshold relative to the recording's loud frames)."""
    n = int(frame * SR16)
    rms = np.sqrt(np.mean(a16[:len(a16) // n * n].reshape(-1, n) ** 2, 1))
    return rms > 0.1 * np.percentile(rms, 95)


def silence_before(voiced, t, frame=0.02):
    """Seconds of silence immediately before audio time t."""
    i = min(int(t / frame), len(voiced))
    j = i
    while j > 0 and not voiced[j - 1]:
        j -= 1
    return (i - j) * frame


def trim(audio, sr, keep=0.06, thr=0.01):
    """Cut the voice model's silent lead-in and tail (they add up to seconds over a conversation)."""
    idx = np.flatnonzero(np.abs(audio) > thr)
    if not len(idx):
        return audio
    k = int(keep * sr)
    return audio[max(0, idx[0] - k):idx[-1] + k]


def speaker_at(turns, t):
    """Speaker talking at time t (turns: [start, end, speaker]); nearest turn if t falls in a gap."""
    for a, b, k in turns:
        if a <= t <= b:
            return k
    return min(turns, key=lambda x: min(abs(t - x[0]), abs(t - x[1])))[2]


def wer(ref, hyp):
    r, h = norm_words(ref), norm_words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(len(r), 1)


def stretch(audio, sr, rate):
    """Play faster without raising the pitch (WSOLA)."""
    from audiotsm import wsola
    from audiotsm.io.array import ArrayReader, ArrayWriter
    reader, writer = ArrayReader(audio[None, :].astype(np.float32)), ArrayWriter(1)
    wsola(1, speed=rate).run(reader, writer)
    return writer.data[0].astype(np.float32)


def run_recording(cid, meta, rec, translator, voice, out):
    a, sr = sf.read(HS / "clips" / f"{cid}.wav", dtype="float32")
    a = a if a.ndim == 1 else a.mean(1)
    a16 = np.interp(np.arange(0, len(a), sr / SR16), np.arange(len(a)), a).astype(np.float32)
    timeline = json.loads((HS / "timelines" / f"{cid}.json").read_text())
    turns = meta.get("turns")
    voiced = voiced_frames(a16)
    translator.reset()

    events, phrases, segments = queue.Queue(), queue.Queue(), []
    player, seg = Player(), Segmenter()
    t0 = time.time() + 0.5
    clock = lambda: time.time() - t0

    def segmenter_loop():
        done = False
        while not done:
            try:
                text, wall = events.get(timeout=0.05)
            except queue.Empty:
                now = clock()
                for s in seg.tick(now, silence_s=silence_before(voiced, now - rec.latency_s)):
                    phrases.put(s)
                continue
            if text is None:
                for s in seg.tick(clock(), final=True):
                    phrases.put(s)
                phrases.put(None); done = True
            else:
                # who is talking: in a meeting each person has their own microphone; here the podcast's speaker
                # labels stand in for that (looked up at the time the words were spoken, not when they arrived)
                spk = speaker_at(turns, wall - t0 - rec.latency_s) if turns else None
                for s in seg.feed(text, wall - t0, spk):
                    phrases.put(s)

    def interpreter_loop():
        end = False
        while not end:
            batch = [phrases.get()]
            while not phrases.empty():
                batch.append(phrases.get())
            if batch[-1] is None:
                end = True; batch = batch[:-1]
            if not batch:
                break
            runs = []                                   # merge queued phrases, but never across speakers
            for b in batch:
                if runs and runs[-1][-1].get("speaker") == b.get("speaker"):
                    runs[-1].append(b)
                else:
                    runs.append([b])
            for run in runs:
                speak(run)

    pre = getattr(rec, "translates", False)            # e.g. Soniox: the phrases are already English
    last_release = [t0 - 1]

    def speak(batch):
            italian = " ".join(b["it"] for b in batch)
            who = batch[0].get("speaker") or meta["voice"]
            src = None
            if pre:                                     # the "it" field holds English; fetch the Italian it came from
                release_wall = t0 + batch[-1]["t_release"]
                src = rec.italian_between(last_release[0], release_wall)
                last_release[0] = release_wall
            now = clock()
            brief = player.backlog(now) > BRIEF_BACKLOG_S
            if pre:
                english, mt_s = italian, 0.0
                italian = src[0]
            else:
                english, mt_s = translator.translate(italian, brief=brief, speaker=batch[0].get("speaker"))
            if not re.search(r"\w", english):       # nothing to say (e.g. a filler word)
                return
            chunks, ready, info = [], None, None
            for chunk, csr, inf in voice.stream(english, who):
                if inf is None:
                    chunks.append(chunk); ready = ready if ready is not None else clock()
                else:
                    info, vsr = inf, csr
            gen_end = clock()
            audio = trim(np.concatenate(chunks), vsr) if chunks else np.zeros(0, np.float32)
            backlog = player.backlog(gen_end)
            rate = next((r for b, r in RATES if backlog > b), 1.0)
            if rate > 1 and len(audio):
                audio, ready = stretch(audio, vsr, rate), gen_end
            start, stop = player.schedule(ready if ready is not None else gen_end, gen_end, len(audio) / vsr)
            segments.append({**batch[0], "it": italian, "merged": len(batch), "reasons": [b["reason"] for b in batch],
                             "t_last_word": batch[-1]["t_last_word"], "voice": who, "en": english, "brief": brief, "mt_s": round(mt_s, 3),
                             "t_mt_start": round(now, 3), "ttfa_s": info["ttfa_s"], "gen_s": info["gen_s"],
                             "audio_s": info["audio_s"], "hit_cap": info["hit_cap"], "rate": rate,
                             "backlog_before_s": round(backlog, 2), "play_start": round(start, 3),
                             "play_end": round(stop, 3), "_audio": audio, "_sr": vsr,
                             **({"src_start": src[1], "src_end": src[2], "aligned": True} if pre and src[1] is not None else {})})

    threads = [threading.Thread(target=segmenter_loop), threading.Thread(target=interpreter_loop)]
    for th in threads:
        th.start()
    rec.run(a16, t0, lambda text, wall, *speaker: events.put((text, wall)))
    for th in threads:
        th.join()

    # "as heard" audio: English placed where it would play, next to the Italian
    vsr = segments[0]["_sr"] if segments else 24000
    total = max([s["play_end"] for s in segments] + [len(a16) / SR16]) + 0.5
    en = np.zeros(int(total * vsr), np.float32)
    for s in segments:
        i = int(s["play_start"] * vsr); en[i:i + len(s["_audio"])] += s["_audio"][:len(en) - i]
    it = np.interp(np.arange(0, len(en)) * (SR16 / vsr), np.arange(len(a16)), a16, right=0).astype(np.float32)
    out.mkdir(parents=True, exist_ok=True)
    sf.write(out / "english.wav", en, vsr)
    sf.write(out / "stereo.wav", np.stack([it, en], 1), vsr)
    for s in segments:
        s.pop("_audio"); s.pop("_sr")

    align([s for s in segments if "src_start" not in s], timeline)
    speech_start, speech_end = timeline[0][1], timeline[-1][2]
    for s in segments:
        s["lag_s"] = round(max(s["play_start"] - s["src_start"], s["play_end"] - s["src_end"]), 2)
    lags = [s["lag_s"] for s in segments]
    mid = [(s["src_start"] + s["src_end"]) / 2 for s in segments]
    slope = float(np.polyfit(mid, lags, 1)[0] * 60) if len(segments) >= 3 else 0.0
    gen = sum(s["gen_s"] for s in segments)
    m = {
        "id": cid, "asr": rec.name, "speech_s": round(speech_end - speech_start, 1), "phrases": len(segments),
        "first_audio_after_start_s": round(segments[0]["play_start"] - speech_start, 2) if segments else None,
        "max_lag_s": round(max(lags), 2) if lags else None,
        "median_lag_s": round(float(np.median(lags)), 2) if lags else None,
        "lag_drift_s_per_min": round(slope, 2),
        "finish_after_end_s": round(segments[-1]["play_end"] - speech_end, 2) if segments else None,
        "last_start_after_end_s": round(segments[-1]["play_start"] - speech_end, 2) if segments else None,
        "max_backlog_s": max((s["backlog_before_s"] for s in segments), default=0),
        "forced_cuts": sum(r in ("deadline", "long") for s in segments for r in s["reasons"]),
        "cuts": {r: sum(r in s["reasons"] for s in segments) for r in ("punctuation", "comma", "pause", "speaker", "deadline", "long", "end")},
        "sped_up_phrases": sum(s["rate"] > 1 for s in segments), "unaligned_phrases": sum(not s["aligned"] for s in segments),
        "voice_speed_x": round(sum(s["audio_s"] for s in segments) / max(gen, 1e-6), 2),
        "any_hit_cap": any(s["hit_cap"] for s in segments),
        "italian_heard": " ".join(s["it"] for s in segments), "english": " ".join(s["en"] for s in segments),
        "asr_wer_vs_text": round(wer(meta["it"], " ".join(s["it"] for s in segments)), 3) if meta.get("it") else None,
    }
    m["targets"] = {"start_within_5s": m["first_audio_after_start_s"] is not None and m["first_audio_after_start_s"] <= 5,
                    "never_more_than_5s_behind": m["max_lag_s"] is not None and m["max_lag_s"] <= 5}
    (out / "segments.json").write_text(json.dumps(segments, indent=1, ensure_ascii=False))
    (out / "metrics.json").write_text(json.dumps(m, indent=1, ensure_ascii=False))
    print(f"[{rec.name} {cid}] start +{m['first_audio_after_start_s']}s lag median {m['median_lag_s']} max {m['max_lag_s']}s "
          f"drift {m['lag_drift_s_per_min']}s/min finish +{m['finish_after_end_s']}s backlog max {m['max_backlog_s']}s "
          f"forced {m['forced_cuts']}/{len(segments)} WER {m['asr_wer_vs_text']} | {m['english'][:160]}", flush=True)
    return m


def main():
    global DEADLINE_S, RATES
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr", default="nemotron-320")
    ap.add_argument("--only", default="")
    ap.add_argument("--mt", default="")
    ap.add_argument("--deadline", type=float, default=DEADLINE_S, help="max seconds a phrase may wait (default 2.5)")
    ap.add_argument("--rates", default="gentle", choices=list(RATE_PROFILES))
    a = ap.parse_args()
    DEADLINE_S, RATES = a.deadline, RATE_PROFILES[a.rates]
    from asr_stream import make
    from mt import Translator, MODEL
    from voice_stream import StreamingVoice

    recs = {**json.loads((HS / "long.json").read_text()), **json.loads((HS / "cases.json").read_text())}
    if a.only:
        recs = {k: v for k, v in recs.items() if k in a.only.split(",")}
    ref_text = json.loads((HERE / "voice_eval/ref/ref_text.json").read_text())

    voice = StreamingVoice(cache_dir=HERE / "voice_cache", clone_mode="xvec")
    for v in recs.values():
        for name, spk in (v.get("speakers") or {v["voice"]: v}).items():
            if name not in voice.voices:
                voice.add_voice(name, HS / spk["ref"], spk.get("ref_text") or ref_text.get(name, ""))
    voice.warmup(next(iter(voice.voices)))
    translator = Translator(a.mt or MODEL); translator.warmup()
    rec = make(a.asr); rec.name = a.asr; rec.warmup()

    tag = a.asr + (f"_{Path(a.mt).name}" if a.mt else "") + (f"_d{a.deadline:g}" if a.deadline != 2.5 else "") \
        + (f"_{a.rates}" if a.rates != "gentle" else "")
    allm = []
    for cid, meta in recs.items():
        try:
            allm.append(run_recording(cid, meta, rec, translator, voice, HERE / "out" / f"stream_{tag}" / cid))
        except Exception as e:          # one broken recording must not stop the rest
            import traceback; traceback.print_exc()
            print(f"[{a.asr} {cid}] FAILED: {e!r}", flush=True)
    (HERE / "out" / f"stream_{tag}" / "all_metrics.json").write_text(json.dumps(allm, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
