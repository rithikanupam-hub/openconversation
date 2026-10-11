"""Model-free checks of actual live reference methods: python cloud/check_reference_quality.py.

AST extraction avoids loading GPU engines; only transport/model side effects are stubbed.
Synthetic PCM validates guards and selection, not voice resemblance or real-world speech quality.
"""
import ast
import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np


def load_session():
    tree = ast.parse(Path(__file__).with_name('live.py').read_text())
    methods = {'_reference_quality', '_collect_identity', '_flush_pieces', 'audio_span',
               'reset_voice', 'start_run', 'diarized'}
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LiveSession')
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    constants = [n for n in tree.body if isinstance(n, ast.Assign)
                 and all(isinstance(t, (ast.Name, ast.Tuple)) for t in n.targets)
                 and any(isinstance(t, ast.Name) and (t.id.startswith('ID_') or t.id in {'SR', 'DEFAULT_VOICE'})
                         for target in n.targets for t in ast.walk(target))]
    env = dict(np=np, SimpleNamespace=NS, queue=queue, time=time,
               threading=NS(Lock=threading.Lock, Thread=lambda **kw: NS(start=lambda: None)),
               LiveVAD=lambda: None, Player=lambda: None, Segmenter=lambda **kw: None)
    exec(compile(ast.Module(body=constants + [cls], type_ignores=[]), 'live.py', 'exec'), env)
    return env['LiveSession'], env['SR']


def main():
    Session, sr = load_session()
    s = Session.__new__(Session)
    s.voice_lock, s.voice_epoch = threading.RLock(), 0
    s.identity, s.rec = True, None
    s.cfg = dict(consent=True, clone=True, source_lang='it', target_lang='en')
    s.spk_audio, s.spk_voice, s.spk_pitch = {}, {}, {}
    s.voice_name, s.voice_audio, s.voice_s = 'default', [], 0
    s.send_ts, s.voice_state = lambda msg: None, lambda who: {}
    s.e = NS(asr=NS(italian=[], sent=0, translates=True), voice=NS(drop_voice=lambda name: None),
             tuning={'seg': {}}, diarizer=NS(reset=lambda callback: None))
    s._asr = s._segmenter = s._interpreter = lambda r: None
    seconds = 160
    clear = (0.1 * np.sin(np.arange(4 * sr) * 0.09)).astype(np.float32)
    r = NS(id_lock=threading.Lock(), id_pending=[], id_reference_start=0.0,
           t0=1000, clock=lambda: seconds, samples=seconds * sr,
           hist=[np.tile(clear, seconds // 4)], hist_start=0)
    s.run = r

    def pending(x, a=0, who='p0', future=False):
        b = a + len(x) / sr
        r.id_pending.append((who, a, b, x))
        s.e.asr.italian.extend(('word', float(t), float(t) + .1, r.t0 + (seconds + 1 if future else b))
                               for t in np.arange(a, b, .25))

    assert s._reference_quality(clear)[0] == 1
    for x, why in [(np.zeros_like(clear), 'quiet'), (clear * .001, 'quiet'), (np.ones(4 * sr, np.float32), 'clipped'),
                   (np.full(4 * sr, np.nan), 'nonfinite_or_empty'),
                   (np.full(4 * sr, np.inf), 'nonfinite_or_empty')]:
        assert s._reference_quality(x)[1] == why
        pending(x)
        s._flush_pieces(r, final=True)
        assert not s.spk_audio
    # A future source token cannot qualify present audio, including a final flush.
    s.e.asr.italian = []
    pending(clear, future=True)
    s._flush_pieces(r, final=True)
    assert not s.spk_audio
    # Replace a lower-occupancy piece with later clear speech, never exceed 15 seconds.
    sparse = clear.copy(); sparse[:2 * sr] = 0
    pending(sparse, a=5)
    for a in [10, 15, 20, 25, 30, 35]:
        pending(clear.copy(), a=a)
    s._flush_pieces(r, final=True)
    assert sum(map(len, s.spk_audio['p0'])) <= 15 * sr
    assert len(s.spk_audio['p0']) == 3
    assert all(s._reference_quality(x)[0] == 1 for x in s.spk_audio['p0'])
    # The collector admits available clean speech, preserving the trimmed duration.
    r.id_pending = []; s.spk_audio = {}; s.e.asr.italian = []
    pending(clear, a=0)
    r.id_pending = []
    s._collect_identity(r, 'p0', 0, 4)
    assert 3.6 * sr < sum(map(len, s.spk_audio['p0'])) < 3.8 * sr
    # No future or expired-history PCM is admitted by the actual collector.
    r.id_pending = []; s.spk_audio = {}; s.e.asr.italian = []
    s._collect_identity(r, 'p0', seconds + 1, seconds + 6)
    assert not r.id_pending and not s.spk_audio
    r.hist_start = 10 * sr; r.hist = [r.hist[0][10 * sr:]]
    s._collect_identity(r, 'p0', 0, 4)
    assert not r.id_pending and not s.spk_audio
    r.hist_start = 0; r.hist = [np.tile(clear, seconds // 4)]
    # Pending storage stays bounded even with source tokens indefinitely delayed.
    r.clock = lambda: 0
    s._collect_identity(r, 'p0', 0, 150)
    assert 0 < sum(len(p[3]) for p in r.id_pending) <= 60 * sr
    r.clock = lambda: seconds
    # Revoke consent between collection and token arrival.
    s.cfg['consent'] = False
    s._flush_pieces(r, final=True)
    assert not r.id_pending and not s.spk_audio
    s.cfg['consent'] = True
    pending(clear)
    s.reset_voice()
    assert not r.id_pending and r.id_reference_start == seconds
    s._collect_identity(r, 'p0', 0, 4)
    assert not r.id_pending
    pending(clear)  # a delayed old callback cannot bypass the reset cutoff
    s._flush_pieces(r, final=True)
    assert not s.spk_audio
    # A fresh run clears accepted references and old callbacks cannot repopulate them.
    s.spk_audio = {'p0': [clear]}
    s.start_run()
    assert not s.spk_audio and s.run is not r and s.run.id_reference_start == 0
    r.id_pending = []; pending(clear)
    s._flush_pieces(r, final=True)
    s._collect_identity(r, 'p0', 0, 4)
    assert not s.spk_audio and not r.id_pending
    print('PASS: actual reference methods; PCM guards, best available/bounded selection, causal tokens/audio, reset/consent/new-run exclusion')


if __name__ == '__main__':
    main()
