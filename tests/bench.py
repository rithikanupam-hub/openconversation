"""Steady-state latency: run the same utterance 3x after models are warm."""
import sys, time, logging, soundfile as sf
from backend.pipeline import pipeline, VoiceProfile
logging.basicConfig(level=logging.WARNING)
engine = sys.argv[1] if len(sys.argv) > 1 else "chatterbox_turbo"
audio, _ = sf.read("tests/it_sample.wav", dtype="float32")
pipeline.warmup(engine)
prof = VoiceProfile()
for i in range(3):
    t = time.time(); r = pipeline.run(audio, "auto", "en", engine, True, prof); tot = time.time() - t
    print(f"run{i} {engine}: {r.timings} total={tot:.1f}s clip={len(audio)/16000:.1f}s")
print("TGT:", r.target_text)
open(f"tests/out_{engine}_bench.wav","wb").write(r.audio_wav)
