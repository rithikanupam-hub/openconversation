"""Session recorder for owner testing: keeps everything one connection hears, does and sends, and writes it to a
folder when the connection ends, so a test can be reviewed afterwards (cloud/review_session.py).

    <dir>/events.jsonl   every step with "t" = seconds since the connection opened (words, phrases, voice, audio)
    <dir>/mic.wav        the microphone, placed at the time each chunk arrived (silence between runs)
    <dir>/heard.wav      the translated speech, parts played back to back from the time they were sent
    <dir>/review.wav     stereo: left = mic, right = heard (listen with headphones to judge lag and voice)
    <dir>/voice_<who>.wav  the audio each cloned voice was built from
    <dir>/summary.json   per-phrase timings and counts

Switched on by RECORD_SESSIONS in cloud/modal_app.py. The page is told ("recording": true in hello).
"""
from __future__ import annotations

import base64, io, json, os, threading, time

import numpy as np
import soundfile as sf

SR = 16000


class Recorder:
    def __init__(self, session_id, out_dir):
        self.id, self.out_dir = session_id, out_dir
        self.t0 = time.time()
        self.lock = threading.Lock()
        self.events, self.mic, self.out, self.voices = [], [], [], {}

    def at(self, wall):
        return round(wall - self.t0, 3)

    def ev(self, kind, **kw):
        with self.lock:
            self.events.append({"t": self.at(time.time()), "kind": kind, **kw})

    def mic_chunk(self, pcm16: bytes):
        with self.lock:
            self.mic.append((time.time() - self.t0, pcm16))

    def voice_ref(self, who, audio, sr=SR):
        with self.lock:
            self.voices[str(who)] = (np.asarray(audio, np.float32).copy(), sr)

    def sent(self, obj):
        """A message the page receives. Audio is kept as samples; meters are skipped."""
        t = obj.get("type")
        if t in ("level", "usage", "pong"):
            return
        if t == "audio" and obj.get("wav_base64"):
            x, sr = sf.read(io.BytesIO(base64.b64decode(obj["wav_base64"])), dtype="float32")
            with self.lock:
                self.out.append((time.time() - self.t0, x, sr, obj.get("id"), obj.get("part")))
            self.ev("sent_audio", id=obj.get("id"), part=obj.get("part"), dur=round(len(x) / sr, 3), age=obj.get("age"))
            return
        self.ev("sent", **obj)

    # --- writing --------------------------------------------------------------------------------------
    def save(self):
        os.makedirs(self.out_dir, exist_ok=True)
        with self.lock:
            events, mic, out, voices = list(self.events), list(self.mic), list(self.out), dict(self.voices)
        end = max([t + len(b) / 2 / SR for t, b in mic] + [t + len(x) / sr for t, x, sr, *_ in out] + [e["t"] for e in events] + [0])

        mic_track = np.zeros(int((end + 1) * SR), np.float32)
        pos = 0
        for t, b in mic:                                  # arrival time, never overlapping the previous chunk
            x = np.frombuffer(b, np.int16).astype(np.float32) / 32768.0
            i = max(int(t * SR) - len(x), pos)            # a chunk arrives when it ends
            mic_track = _put(mic_track, i, x)
            pos = i + len(x)

        heard = np.zeros_like(mic_track)
        pos, rows = 0, []
        for t, x, sr, uid, part in out:                   # the page plays parts back to back (server pacing)
            if sr != SR:
                x = np.interp(np.arange(0, len(x), sr / SR), np.arange(len(x)), x).astype(np.float32)
            i = max(int(t * SR), pos)
            heard = _put(heard, i, x)
            pos = i + len(x)
            rows.append({"id": uid, "part": part, "sent": round(t, 3), "starts": round(i / SR, 3),
                         "ends": round(pos / SR, 3), "waited": round(i / SR - t, 3)})
        n = max(len(mic_track), len(heard))
        mic_track, heard = np.pad(mic_track, (0, n - len(mic_track))), np.pad(heard, (0, n - len(heard)))

        sf.write(f"{self.out_dir}/mic.wav", mic_track, SR, subtype="PCM_16")
        sf.write(f"{self.out_dir}/heard.wav", np.clip(heard, -1, 1), SR, subtype="PCM_16")
        sf.write(f"{self.out_dir}/review.wav", np.clip(np.stack([mic_track, heard], 1), -1, 1), SR, subtype="PCM_16")
        for who, (x, sr) in voices.items():
            sf.write(f"{self.out_dir}/voice_{who}.wav", x, sr, subtype="PCM_16")
        with open(f"{self.out_dir}/events.jsonl", "w") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        summary = {"session": self.id, "started": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(self.t0)) + " UTC",
                   "seconds": round(end, 1), "mic_seconds": round(sum(len(b) / 2 for _, b in mic) / SR, 1),
                   "heard_seconds": round(sum(len(x) / sr for _, x, sr, *_ in out), 1),
                   "voices": sorted(voices), "playback": rows}
        with open(f"{self.out_dir}/summary.json", "w") as f:
            json.dump(summary, f, indent=1)
        return summary


def _put(track, i, x):
    if i + len(x) > len(track):
        track = np.pad(track, (0, i + len(x) - len(track) + SR))
    track[i:i + len(x)] += x
    return track
