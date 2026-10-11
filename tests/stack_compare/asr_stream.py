"""Streaming Italian speech recognisers for the real-time harness. Each emits only text it will not change.

    rec = make("nemotron-320")          # or "nemotron-560", "whisper-turbo"
    rec.run(audio16, t0, emit)          # blocks; audio is fed at speaking pace from wall-clock time t0;
                                        # emit(text, wall_time) for each piece of stable text, emit(None, t) at the end
"""
import re, time

import numpy as np
import torch

SR = 16000


def norm(w):
    return re.sub(r"[^\w]", "", w.lower())


def agreed_prefix(a, b):
    """Number of leading words two hypotheses agree on (LocalAgreement-2)."""
    n = 0
    for x, y in zip(a, b):
        if norm(x[0]) != norm(y[0]) or not norm(x[0]):
            break
        n += 1
    return n


class WhisperLA:
    """faster-whisper re-run on the unconfirmed audio every STEP s; words confirmed by two runs in a row are final."""
    STEP = 1.0
    MAX_BUF = 20.0

    def __init__(self, model="large-v3-turbo"):
        from faster_whisper import WhisperModel
        self.m = WhisperModel(model, device="cuda", compute_type="float16")
        self.latency_s = 2 * self.STEP      # a word is final after two runs agree

    def warmup(self):
        list(self.m.transcribe(np.zeros(SR, np.float32), language="it")[0])

    def _hyp(self, audio16, start, end, prompt):
        segs, _ = self.m.transcribe(audio16[int(start * SR):int(end * SR)], language="it", word_timestamps=True,
                                    beam_size=1, vad_filter=False, condition_on_previous_text=False,
                                    initial_prompt=prompt or None)
        return [(w.word.strip(), start + w.start, start + w.end) for s in segs for w in s.words if w.word.strip()]

    def run(self, audio16, t0, emit):
        dur = len(audio16) / SR
        done, buf_start, prev, last = [], 0.0, [], 0.0
        while True:
            avail = min(time.time() - t0, dur)
            final = avail >= dur
            if avail - last < self.STEP and not final:
                time.sleep(0.02); continue
            last = avail
            hyp = self._hyp(audio16, buf_start, avail, " ".join(done[-30:]))
            if final:
                new = hyp
            else:
                new = hyp[:agreed_prefix(hyp, prev)]
                if not new and avail - buf_start > self.MAX_BUF:     # never let the buffer grow without bound
                    new = [w for w in hyp if w[2] < avail - 2.0]
            if new:
                emit(" ".join(w[0] for w in new) + " ", time.time())
                done += [w[0] for w in new]
                buf_start = new[-1][2]
            prev = hyp[len(new):]
            if final:
                emit(None, time.time()); return


class Nemotron:
    """nvidia/nemotron-3.5-asr-streaming-0.6b, cache-aware streaming (its output is final as it is emitted)."""

    def __init__(self, lookahead=3, model="nvidia/nemotron-3.5-asr-streaming-0.6b"):
        from transformers import AutoModelForRNNT, AutoProcessor
        self.proc = AutoProcessor.from_pretrained(model)
        self.m = AutoModelForRNNT.from_pretrained(model, device_map="cuda:0")
        self.proc.set_num_lookahead_tokens(lookahead)       # right context: 3 -> 320 ms chunks, 6 -> 560 ms
        self.latency_s = self.proc.streaming_latency_ms / 1000

    def warmup(self):
        self.run(np.zeros(2 * SR, np.float32), time.time() - 10, lambda *a: None)

    def run(self, audio16, t0, emit):
        from threading import Thread
        from transformers import TextIteratorStreamer
        p = self.proc
        kw = dict(sampling_rate=SR, is_streaming=True, language="it-IT", return_tensors="pt")

        def wait_until(sample):             # audio can't be processed before it has been spoken
            time.sleep(max(0.0, t0 + sample / SR - time.time()))

        first = p(audio16[:p.num_samples_first_audio_chunk], is_first_audio_chunk=True, **kw).to("cuda:0", dtype=self.m.dtype)

        def features():
            wait_until(p.num_samples_first_audio_chunk)
            yield first.input_features[:, :p.num_mel_frames_first_audio_chunk, :]
            idx = p.num_mel_frames_first_audio_chunk
            hop, n_fft = p.feature_extractor.hop_length, p.feature_extractor.n_fft
            start = idx * hop - n_fft // 2
            while (end := start + p.num_samples_per_audio_chunk) < len(audio16) + p.num_samples_per_audio_chunk:
                chunk = audio16[start:end]
                if len(chunk) < p.num_samples_per_audio_chunk:          # pad the tail so the last words come out
                    chunk = np.pad(chunk, (0, p.num_samples_per_audio_chunk - len(chunk)))
                wait_until(min(end, len(audio16)))
                yield p(chunk, is_first_audio_chunk=False, **kw).to("cuda:0", dtype=self.m.dtype).input_features
                idx += p.num_mel_frames_per_audio_chunk
                start = idx * hop - n_fft // 2

        streamer = TextIteratorStreamer(p.tokenizer, skip_special_tokens=True)
        th = Thread(target=self.m.generate, kwargs={**first, "input_features": features(), "streamer": streamer})
        th.start()
        for piece in streamer:
            if piece:
                emit(piece, time.time())
        th.join()
        emit(None, time.time())


class LiveNemotron(Nemotron):
    """Same model, fed from a live microphone: `chunks` yields float32 16 kHz arrays as they arrive and ends
    (StopIteration / None) when the user stops."""

    def run_live(self, chunks, emit):
        from threading import Thread
        from transformers import TextIteratorStreamer
        p = self.proc
        kw = dict(sampling_rate=SR, is_streaming=True, language="it-IT", return_tensors="pt")
        it = iter(chunks)
        state = {"buf": np.zeros(0, np.float32), "base": 0}      # buf holds samples from absolute index `base`

        def have(n):                        # block until absolute sample n has arrived; False if the stream ended
            while state["base"] + len(state["buf"]) < n:
                c = next(it, None)
                if c is None:
                    return False
                state["buf"] = np.concatenate([state["buf"], c])
            return True

        def take(a, b):                     # samples [a, b), zero-padded past the end
            x = state["buf"][a - state["base"]:b - state["base"]]
            return np.pad(x, (0, (b - a) - len(x)))

        def feats(x, first=False):
            return p(x, is_first_audio_chunk=first, **kw).to(self.m.device, dtype=self.m.dtype)

        n1 = p.num_samples_first_audio_chunk
        if not have(n1) and len(state["buf"]) == 0:
            emit(None, time.time()); return
        first = feats(take(0, n1), first=True)

        def features():
            yield first.input_features[:, :p.num_mel_frames_first_audio_chunk, :]
            idx = p.num_mel_frames_first_audio_chunk
            hop, n_fft = p.feature_extractor.hop_length, p.feature_extractor.n_fft
            start = idx * hop - n_fft // 2
            while True:
                end = start + p.num_samples_per_audio_chunk
                more = have(end)
                yield feats(take(start, end)).input_features
                if not more:
                    return
                idx += p.num_mel_frames_per_audio_chunk
                start = idx * hop - n_fft // 2
                drop = start - state["base"] - SR                # keep 1 s of history, drop the rest
                if drop > 0:
                    state["buf"], state["base"] = state["buf"][drop:], state["base"] + drop

        streamer = TextIteratorStreamer(p.tokenizer, skip_special_tokens=True)
        th = Thread(target=self.m.generate, kwargs={**first, "input_features": features(), "streamer": streamer})
        th.start()
        for piece in streamer:
            if piece:
                emit(piece, time.time())
        th.join()
        emit(None, time.time())


def make(name):
    if name in ("soniox", "soniox-asr"):
        from soniox_front import SonioxFront
        return SonioxFront(translate=(name == "soniox"))
    if name == "whisper-turbo":
        return WhisperLA()
    if name.startswith("nemotron"):
        return Nemotron(lookahead={"nemotron-160": 1, "nemotron-320": 3, "nemotron-560": 6}[name])
    raise ValueError(name)
