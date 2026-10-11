"""Streaming speaker diarization worker (NVIDIA Nemotron-3-Diarization), run as a separate process because it needs
a newer transformers than Qwen3-TTS. Started by cloud/live.py with PYTHONPATH=/opt/diar (its own packages).

stdin:  messages of [1 byte type][4 bytes little-endian length][payload]
        type b"A": int16 16 kHz mono audio;  type b"R": reset (new listening run)
stdout: one JSON line per processed chunk: {"start": first frame index, "mask": base64 uint8 per 10 ms frame}
        bit k of a frame's mask = speaker k (0-7) is talking. Also {"ready": true, "latency_ms": ...} once loaded.
"""
import base64, json, os, struct, sys

import numpy as np
import torch
from transformers import AutoModelForAudioFrameClassification, AutoProcessor

MODEL = "nvidia/Nemotron-3-Diarization"
MODE = os.environ.get("DIAR_MODE", "low_latency")       # 1.04 s; "very_low_latency" 0.64 s
SR = 16000


def main():
    torch.set_num_threads(1)
    model = AutoModelForAudioFrameClassification.from_pretrained(MODEL, device_map="cuda", dtype=torch.float16)
    proc = AutoProcessor.from_pretrained(MODEL)
    proc.set_streaming_mode(MODE)
    out = sys.stdout
    out.write(json.dumps({"ready": True, "latency_ms": proc.streaming_latency_ms}) + "\n"); out.flush()
    inp = sys.stdin.buffer

    def reset():
        return {"audio": np.zeros(0, np.float32), "cache": None, "first": True, "mel": 0, "start": 0, "frames": 0}

    st = reset()

    def run(x, first=False, last=False):
        p = proc(x, sampling_rate=SR, is_streaming=True, is_first_audio_chunk=first, is_last_audio_chunk=last)
        with torch.inference_mode():
            o = model(**p.to(model.device, dtype=model.dtype), speaker_cache=st["cache"])
        st["cache"] = getattr(o, "speaker_cache", None)
        m = (torch.sigmoid(o.logits[0].float()) > 0.5).cpu().numpy()            # (frames, 8)
        mask = (m * (1 << np.arange(m.shape[1]))).sum(1).astype(np.uint8)    # bit k = speaker k
        out.write(json.dumps({"start": st["frames"], "mask": base64.b64encode(mask.tobytes()).decode()}) + "\n")
        out.flush()
        st["frames"] += len(mask)

    while True:
        head = inp.read(5)
        if len(head) < 5:
            return
        kind, n = head[:1], struct.unpack("<I", head[1:])[0]
        payload = inp.read(n) if n else b""
        if kind == b"R":
            st = reset()
            continue
        st["audio"] = np.concatenate([st["audio"], np.frombuffer(payload, np.int16).astype(np.float32) / 32768])
        a = st["audio"]
        if st["first"]:
            if len(a) >= proc.num_samples_first_audio_chunk:
                run(a[:proc.num_samples_first_audio_chunk], first=True)
                st["first"] = False
                st["mel"] = proc.num_mel_frames_per_step
                st["start"] = proc.audio_chunk_start(st["mel"])
            continue
        while st["start"] + proc.num_samples_per_audio_chunk <= len(a):
            run(a[st["start"]:st["start"] + proc.num_samples_per_audio_chunk])
            st["mel"] += proc.num_mel_frames_per_step
            st["start"] = proc.audio_chunk_start(st["mel"])


if __name__ == "__main__":
    main()
