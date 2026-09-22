"""End-to-end smoke test without a microphone: feeds a spoken Italian clip through
the VAD segmenter and the pipeline, writes the translated cloned audio to tests/out_*.wav.
Run: .venv/bin/python -m tests.smoke [engine]
"""
import sys, time, logging
import numpy as np, soundfile as sf
from backend.vad import Segmenter, SAMPLE_RATE
from backend.pipeline import pipeline, VoiceProfile, ENGINES

logging.basicConfig(level=logging.INFO)
engine = sys.argv[1] if len(sys.argv) > 1 else "chatterbox_turbo"
audio, sr = sf.read("tests/it_sample.wav", dtype="float32")
assert sr == SAMPLE_RATE
# stream in 100 ms frames like the browser does, then a trailing second of silence
seg = Segmenter()
utts = []
frames = np.concatenate([audio, np.zeros(SAMPLE_RATE, np.float32)])
for i in range(0, len(frames), 1600):
    u = seg.feed(frames[i:i+1600])
    if u: utts.append(u)
u = seg.flush()
if u: utts.append(u)
print(f"VAD produced {len(utts)} utterance(s): {[round(len(u.audio)/SAMPLE_RATE,2) for u in utts]}")
assert utts, "VAD found no speech"
profile = VoiceProfile()
for n, u in enumerate(utts):
    t = time.time()
    res = pipeline.run(u.audio, "auto", "en", engine, True, profile, on_transcript=lambda t, l: print("  ASR:", l, "|", t))
    print(f"[{n}] lang={res.source_lang} skipped={res.skipped} timings={res.timings} total={time.time()-t:.1f}s")
    print("  SRC:", res.source_text)
    print("  TGT:", res.target_text)
    if res.audio_wav:
        out = f"tests/out_{engine}_{n}.wav"
        open(out, "wb").write(res.audio_wav)
        print("  audio ->", out, f"{res.sample_rate} Hz")
print("SMOKE_OK")
