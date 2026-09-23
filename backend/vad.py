"""Energy-based voice activity detection and utterance segmentation.

Runs on 16 kHz mono float32 audio. Cheap enough to run on every ~100 ms frame
from the browser. Tracks an adaptive noise floor so it works with laptop mics
in a quiet meeting room without any model download.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SAMPLE_RATE = 16_000


@dataclass
class Utterance:
    audio: np.ndarray  # float32, 16 kHz
    forced: bool = False  # cut by max-length or a manual flush


@dataclass
class Segmenter:
    # tuning (seconds)
    min_speech: float = 0.35
    end_silence: float = 0.5
    pre_roll: float = 0.3
    max_utterance: float = 8.0
    # Continuous flow: once an utterance is this long, a short breath (soft_silence) is enough
    # to close it, so translation starts while the speaker is still talking.
    soft_after: float = 3.0
    soft_silence: float = 0.2
    # thresholds relative to the adaptive noise floor
    start_ratio: float = 3.0
    keep_ratio: float = 1.8
    abs_floor: float = 0.006

    noise: float = 0.01
    in_speech: bool = False
    speech_frames: list = field(default_factory=list)
    pre_frames: list = field(default_factory=list)
    speech_dur: float = 0.0
    silence_dur: float = 0.0
    last_rms: float = 0.0

    def _rms(self, frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2) + 1e-12))

    def feed(self, frame: np.ndarray) -> Utterance | None:
        """Feed one frame (any length) of float32 16 kHz audio.

        Returns a finished Utterance when one closes, else None.
        """
        rms = self._rms(frame)
        self.last_rms = rms
        dur = len(frame) / SAMPLE_RATE
        start_thr = max(self.abs_floor, self.noise * self.start_ratio)
        keep_thr = max(self.abs_floor * 0.7, self.noise * self.keep_ratio)

        if not self.in_speech:
            # slowly track the noise floor while quiet
            self.noise = 0.95 * self.noise + 0.05 * rms if rms < start_thr else self.noise
            self.pre_frames.append(frame)
            keep = int(self.pre_roll * SAMPLE_RATE)
            while sum(len(f) for f in self.pre_frames) > keep and len(self.pre_frames) > 1:
                self.pre_frames.pop(0)
            if rms >= start_thr:
                self.in_speech = True
                self.speech_frames = list(self.pre_frames)
                self.pre_frames = []
                self.speech_dur = dur
                self.silence_dur = 0.0
            return None

        self.speech_frames.append(frame)
        if rms >= keep_thr:
            self.speech_dur += dur
            self.silence_dur = 0.0
        else:
            self.silence_dur += dur

        total = sum(len(f) for f in self.speech_frames) / SAMPLE_RATE
        if self.silence_dur >= self.end_silence:
            return self._close(forced=False)
        if total >= self.soft_after and self.silence_dur >= self.soft_silence:
            return self._close(forced=False, silence=self.silence_dur)
        if total >= self.max_utterance:
            return self._close(forced=True)
        return None

    def flush(self) -> Utterance | None:
        if self.in_speech:
            return self._close(forced=True)
        return None

    def _close(self, forced: bool, silence: float | None = None) -> Utterance | None:
        audio = np.concatenate(self.speech_frames) if self.speech_frames else np.zeros(0, np.float32)
        spoken = self.speech_dur
        self.in_speech = False
        self.speech_frames = []
        self.speech_dur = 0.0
        self.silence_dur = 0.0
        if spoken < self.min_speech:
            return None
        # trim trailing silence but leave ~150 ms
        tail = self.end_silence if silence is None else silence
        trim = int(max(0.0, tail - 0.15) * SAMPLE_RATE) if not forced else 0
        if trim and len(audio) > trim:
            audio = audio[:-trim]
        return Utterance(audio=audio.astype(np.float32), forced=forced)

    @property
    def speaking(self) -> bool:
        return self.in_speech
