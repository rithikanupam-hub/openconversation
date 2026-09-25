"""Voice-clone eval, one model per process (clean memory and timing).

Clones two real Italian LibriVox readers (public domain) and speaks English (and Italian where the
model supports it). Writes WAVs + timings to tests/voice_eval/out/<model>/.
Usage: .venv/bin/python -m tests.voice_eval.run_model <model_key>
"""
import json, os, sys, time, resource
import numpy as np, soundfile as sf
import mlx.core as mx
from mlx_audio.tts.utils import load_model

HERE = os.path.dirname(os.path.abspath(__file__))
REF = {"simona": f"{HERE}/ref/simona_ref.wav", "filippo": f"{HERE}/ref/filippo_ref.wav"}
REF_TEXT = json.load(open(f"{HERE}/ref/ref_text.json"))
TEXTS = {
    "en1": "Good morning everyone. Today we are going to talk about the marketing strategy for the next quarter.",
    "en2": "The payments of fifteen hundred euros were due on the seventeenth, but nobody has received them yet.",
    "it1": "Buongiorno a tutti, oggi parliamo della strategia di marketing per il prossimo trimestre.",
}
MODELS = {  # key: (repo, languages it can speak, how to call it)
    "pocket": ("mlx-community/pocket-tts-4bit", ["en"], "pocket"),
    "chatterbox_turbo": ("mlx-community/chatterbox-turbo-4bit", ["en"], "cb_turbo"),
    "chatterbox_multi": ("mlx-community/chatterbox-multilingual-v3", ["en", "it"], "cb_multi"),
    "qwen3_0.6b": ("mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16", ["en", "it"], "qwen"),
    "qwen3_1.7b": ("mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16", ["en", "it"], "qwen"),
    "voxcpm2": ("mlx-community/VoxCPM2-4bit", ["en", "it"], "voxcpm"),
}


def kwargs_for(kind, speaker, lang):
    ref = REF[speaker]
    if kind == "pocket":
        return {"ref_audio": ref}
    if kind == "cb_turbo":
        return {"ref_audio": ref}
    if kind == "cb_multi":
        return {"ref_audio": ref, "lang_code": lang}
    if kind == "qwen":
        return {"ref_audio": ref, "ref_text": REF_TEXT[speaker], "lang_code": {"en": "english", "it": "italian"}[lang]}
    if kind == "voxcpm":
        return {"ref_audio": ref, "ref_text": REF_TEXT[speaker]}
    raise ValueError(kind)


def main(key):
    repo, langs, kind = MODELS[key]
    out = f"{HERE}/out/{key}"
    os.makedirs(out, exist_ok=True)
    t = time.time()
    model = load_model(repo)
    load_s = time.time() - t
    sr = int(getattr(model, "sample_rate", 24000))
    rows = []
    for speaker in REF:
        for tid, text in TEXTS.items():
            lang = tid[:2]
            if lang not in langs:
                continue
            for attempt in range(2):  # first run of a model includes kernel compilation; keep the 2nd
                t = time.time()
                chunks = []
                try:
                    for seg in model.generate(text, **kwargs_for(kind, speaker, lang)):
                        chunks.append(np.asarray(seg.audio, dtype=np.float32).reshape(-1))
                        sr = int(getattr(seg, "sample_rate", sr) or sr)
                    err = None
                except Exception as e:  # noqa: BLE001
                    err = f"{type(e).__name__}: {e}"[:200]
                gen_s = time.time() - t
                if err or speaker != "simona" or tid != "en1":
                    break  # only repeat the very first generation (warm-up)
            if err:
                rows.append({"speaker": speaker, "text": tid, "error": err})
                print(key, speaker, tid, "ERROR", err, flush=True)
                continue
            audio = np.concatenate(chunks)
            path = f"{out}/{speaker}_{tid}.wav"
            sf.write(path, audio, sr)
            dur = len(audio) / sr
            rows.append({"speaker": speaker, "text": tid, "lang": lang, "wav": path, "gen_s": round(gen_s, 2),
                         "audio_s": round(dur, 2), "rtf": round(gen_s / max(dur, 0.01), 3)})
            print(key, speaker, tid, f"gen {gen_s:.2f}s audio {dur:.1f}s RTF {gen_s/max(dur,.01):.2f}", flush=True)
            mx.clear_cache()
    peak_gb = max(mx.get_peak_memory() / 2**30, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30)
    json.dump({"model": key, "repo": repo, "load_s": round(load_s, 1), "peak_gb": round(peak_gb, 2),
               "langs": langs, "rows": rows}, open(f"{out}/results.json", "w"), indent=1)
    print(key, f"load {load_s:.1f}s peak {peak_gb:.2f} GB", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
