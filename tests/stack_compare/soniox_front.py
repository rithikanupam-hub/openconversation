"""Soniox as a drop-in front end: streaming Italian recognition AND English translation in one service.

Same shape as the recognisers in asr_stream.py, so swapping is one setting (stream_sim --asr soniox,
cloud/live.py LINGOSYNC_FRONT=soniox). Differences the callers handle:
  - `translates = True`: emit() receives ENGLISH text (final translation tokens); no Qwen translation step.
  - `italian_between(t_a, t_b)`: the Italian heard in that stretch, with its audio times (Soniox gives
    start/end ms per token), used for display and for measuring the lag.
Needs SONIOX_API_KEY in the environment. Paid: about $0.18 per hour of audio (research, 2026-09).
"""
import json, os, threading, time

import numpy as np

# EU data residency: Soniox EU region (separate EU project + API key, enabled on request by Soniox support), LINGOSYNC_SONIOX_REGION=eu.
URL = ("wss://stt-rt.eu.soniox.com/transcribe-websocket" if os.environ.get("LINGOSYNC_SONIOX_REGION") == "eu"
       else "wss://stt-rt.soniox.com/transcribe-websocket")
SR = 16000
KEEPALIVE = "keepalive"      # yield this from `chunks` during silence so Soniox keeps the session open


class SonioxFront:
    """translate=True: Soniox recognises AND translates (emit gets English).
    translate=False ("soniox-asr"): Soniox only recognises (emit gets Italian, like Nemotron); our segmenter and
    translator do the rest, so English can start before a sentence ends."""
    latency_s = 0.0          # words carry their own audio times; nothing to subtract

    def __init__(self, key=None, model="stt-rt-v5", translate=True):
        self.key = key or os.environ["SONIOX_API_KEY"]
        self.model = model
        self.translates = translate
        self.source, self.target = "it", "en"       # language codes; source "auto" = detect (any of 60+)
        self.keepalive = True
        self.sent = 0        # samples sent over all connections of this front end (token times -> session time)
        if not translate:
            self.latency_s = 0.8     # final words arrive ~a second after they're spoken; the pause check waits for them
        self.italian = []    # [(text, start_s, end_s, wall_time, speaker, language)] final source tokens of this run
        # web app extras (cloud/live.py): emit(text, wall, spk, lang) incl. "<end>" endpoint markers, plus extra
        # session settings (endpoint tuning, context terms) merged into Soniox's config
        self.pass_language = False
        self.extra_config = {}

    def warmup(self):
        pass

    def italian_between(self, wall_a, wall_b):
        toks = self.tokens_between(wall_a, wall_b)
        if not toks:
            return "", None, None
        return "".join(t[0] for t in toks).strip(), min(t[1] for t in toks), max(t[2] for t in toks)

    def tokens_between(self, wall_a, wall_b):
        """Final Italian tokens that arrived in (wall_a, wall_b]: (text, start_s, end_s, wall, speaker)."""
        return [t for t in self.italian if wall_a < t[3] <= wall_b]

    def _stream(self, chunks, emit):
        from websockets.sync.client import connect
        self.italian = self.italian[-12000:]   # ~1 h of words; the recorder keeps them all
        base = self.sent / SR                       # Soniox times restart at 0 on every connection
        # ping_interval=None: websockets' own keepalive pings timed out on Soniox and killed the session
        # (web app, 2026-09-27); Soniox's keepalive message covers silences instead
        with connect(URL, open_timeout=15, max_size=None, ping_interval=None) as ws:
            ws.send(json.dumps(dict(api_key=self.key, model=self.model, audio_format="pcm_s16le", sample_rate=SR,
                                    num_channels=1, enable_endpoint_detection=True, enable_speaker_diarization=True,
                                    enable_language_identification=True,
                                    **({"language_hints": [self.source]} if self.source not in (None, "auto") else {}),
                                    **({"translation": dict(type="one_way", target_language=self.target)}
                                       if self.translates else {}), **self.extra_config)))

            def sender():
                try:
                    for x in chunks:
                        if isinstance(x, str):          # KEEPALIVE during silence
                            ws.send(json.dumps({"type": "keepalive"}))
                            continue
                        ws.send((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
                        self.sent += len(x)
                    ws.send("")                      # end of audio
                except Exception:
                    pass
            th = threading.Thread(target=sender, daemon=True)
            th.start()
            for raw in ws:
                ev = json.loads(raw)
                if ev.get("error_code") is not None:
                    # never print provider messages: they could echo request details
                    raise RuntimeError(f"Soniox error {ev['error_code']} ({ev.get('error_type', '')})")
                now = time.time()
                for t in ev.get("tokens", []):
                    if not t.get("is_final"):
                        continue
                    if t["text"].startswith("<"):
                        if self.pass_language and t["text"] == "<end>":    # Soniox endpoint: the speaker paused
                            emit("<end>", now, None, None)
                        continue
                    spk = str(t["speaker"]) if t.get("speaker") is not None else None
                    if t.get("translation_status") == "translation":
                        if self.pass_language:
                            emit(t["text"], now, spk, t.get("source_language"))
                        else:
                            emit(t["text"], now, spk)
                    else:
                        self.italian.append((t["text"], base + t.get("start_ms", 0) / 1000,
                                             base + t.get("end_ms", 0) / 1000, now, spk, t.get("language")))
                        if not self.translates:
                            emit(t["text"], now, spk)
                if ev.get("finished"):
                    break
            th.join(timeout=1)
        emit(None, time.time())

    def run(self, audio16, t0, emit):
        """Recorded audio, fed at speaking pace from wall-clock t0 (the test harness)."""
        def chunks():
            for i in range(0, len(audio16), SR // 10):
                time.sleep(max(0.0, t0 + (i + SR // 10) / SR - time.time()))
                yield audio16[i:i + SR // 10]
        self._stream(chunks(), emit)

    def run_live(self, chunks, emit):
        """Live microphone: `chunks` yields float32 16 kHz arrays as they arrive (the web app)."""
        self._stream(chunks, emit)
