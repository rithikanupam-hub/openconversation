"""Live voice step for the cloud stacks: Qwen3-TTS 0.6B voice clone, streamed in small chunks.

What changed against the old one-shot call (qwen_tts.generate_voice_clone):
- Streaming: audio comes out every CHUNK_FRAMES codec frames (12 frames/s, so 4 frames = 0.33 s)
  instead of after the whole sentence.
- CUDA graphs + static KV cache (faster-qwen3-tts): the talker and the 15-step code predictor are
  recorded once and replayed each frame, and the cache is kept between frames instead of rebuilt.
- Voice caching: each speaker's clone prompt (speaker embedding + reference codes) is computed once,
  saved to disk, and reused for every sentence.
- Hard length cap: at most ~0.6 s of audio per word + 2 s, so a sentence can never run away for minutes.
- Sentence pipelining: speak() takes a list of sentences; the first can start while later ones wait.

    v = StreamingVoice(); v.add_voice("simona", "ref.wav", ref_text="...")
    for chunk, sr, info in v.stream("Hello there.", "simona"): ...
"""
import time
from pathlib import Path

import numpy as np, torch

MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
FRAMES_PER_S = 12
CHUNK_FRAMES = 4              # 0.33 s of audio per chunk
SECONDS_PER_WORD = 0.6        # generous: normal English speech is ~0.35-0.45 s/word
CAP_EXTRA_S = 2.0


def length_cap(text):
    """Max codec frames for this text."""
    return int(FRAMES_PER_S * (len(text.split()) * SECONDS_PER_WORD + CAP_EXTRA_S))


def sync():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


class StreamingVoice:
    def __init__(self, model=MODEL, cache_dir="voice_cache", attn="sdpa", clone_mode="icl"):
        from faster_qwen3_tts import FasterQwen3TTS
        self.tts = FasterQwen3TTS.from_pretrained(model, attn_implementation=attn)
        self.cache_dir = Path(cache_dir); self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.clone_mode = clone_mode      # "icl" (reference audio in context) or "xvec" (speaker embedding only)
        self.voices = {}                  # name -> dict(voice_clone_prompt=..., ref_text=...)

    def add_voice(self, name, ref_wav, ref_text="", sr=None, cache=True):
        """Compute (or load) the speaker's clone prompt once. ref_wav: a file path, or a float32 array with `sr`."""
        mode = self.clone_mode if ref_text else "xvec"
        path = self.cache_dir / f"{name}.{mode}.pt"
        if not isinstance(ref_wav, (str, Path)):
            item = self.tts.model.create_voice_clone_prompt(ref_audio=(np.asarray(ref_wav, np.float32), sr),
                                                            ref_text=None, x_vector_only_mode=True)[0]
            if cache:
                torch.save(item, path)
            self.voices[name] = {"voice_clone_prompt": [item], "ref_text": ""}
            return
        if path.exists():
            item = torch.load(path, weights_only=False)
        else:
            t0 = time.time()
            # ICL: append 0.5 s of silence so the reference's last phoneme doesn't bleed into the output
            ref = self.tts._load_ref_audio_with_silence(ref_wav, 0.5 if mode == "icl" else 0.0)
            items = self.tts.model.create_voice_clone_prompt(ref_audio=ref, ref_text=ref_text if mode == "icl" else None,
                                                             x_vector_only_mode=(mode == "xvec"))
            item = items[0]
            torch.save(item, path)
            print(f"voice {name} ({mode}) prepared in {time.time() - t0:.1f}s", flush=True)
        self.voices[name] = {"voice_clone_prompt": [item], "ref_text": ref_text if mode == "icl" else ""}

    def drop_voice(self, name):
        self.voices.pop(name, None)

    def warmup(self, voice):
        """First call captures the CUDA graphs; run it before timing anything."""
        for _ in self.stream("Warm up, one two three.", voice):
            pass

    def stream(self, text, voice, chunk_frames=CHUNK_FRAMES, language="English"):
        """Yield (audio_chunk float32, sample_rate, info). info on the last chunk has the totals."""
        v = self.voices[voice]
        def generate():
            cap = length_cap(text)
            sync(); t0 = time.time()
            first, n_samples, sr = None, 0, 24000
            for chunk, sr, _timing in self.tts.generate_voice_clone_streaming(
                    text=text, language=language, ref_text=v["ref_text"], voice_clone_prompt=v["voice_clone_prompt"],
                    max_new_tokens=cap, chunk_size=chunk_frames):
                chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
                if first is None:
                    sync(); first = time.time() - t0
                n_samples += len(chunk)
                yield chunk, sr, None
            sync(); total = time.time() - t0
            audio_s = n_samples / sr
            yield np.zeros(0, np.float32), sr, {
                "ttfa_s": round(first or total, 3), "gen_s": round(total, 3), "audio_s": round(audio_s, 2),
                "speed_x": round(audio_s / max(total, 1e-6), 2),                # >1 = faster than speech
                "hit_cap": audio_s >= cap / FRAMES_PER_S - 0.3, "cap_s": round(cap / FRAMES_PER_S, 1)}
        return generate()

    def speak(self, sentences, voice, chunk_frames=CHUNK_FRAMES):
        """Voice sentences one after another as a single stream. Returns (audio, sr, per-sentence info)."""
        out, infos, sr = [], [], 24000
        for s in sentences:
            for chunk, sr, info in self.stream(s, voice, chunk_frames):
                if info is None:
                    out.append(chunk)
                else:
                    infos.append({"text": s, **info})
        audio = np.concatenate(out) if out else np.zeros(0, np.float32)
        return audio, sr, infos
