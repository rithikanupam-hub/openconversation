"""Deterministic model-free checks of clone installation/reset and prompt snapshots.

    .venv/bin/python cloud/check_voice_lifecycle.py
"""
import ast
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np


def load():
    tree = ast.parse(Path(__file__).with_name('live.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LiveSession')
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                and n.name in {'_speak', 'reset_voice', '_send_audio', 'diarized'}]
    names = {'SR', 'DEFAULT_VOICE', 'LOCK_SECONDS', 'FILLER', 'VOICE_LANGS'}
    nodes = [n for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and (t.id in names or t.id.startswith('ID_'))
                     for target in n.targets for t in ast.walk(target))]
    nodes += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'target_only']
    env = dict(np=np, re=re, time=time, RATES=[], trim=lambda x, sr: x,
               wav_b64=lambda audio, sr: 'test-pcm')
    exec(compile(ast.Module(body=nodes + [cls], type_ignores=[]), 'live.py', 'exec'), env)
    return env['LiveSession']


def fixture(diarized):
    Session = load()
    s = Session.__new__(Session)
    s.voice_lock, s.voice_epoch = threading.RLock(), 0
    s.id, s.next_id, s.identity, s.rec = 'fixture', 0, diarized, None
    s.cfg = dict(clone=True, consent=True, source_lang='it', target_lang='en')
    s.history, s.voice_name, s.voice_audio, s.voice_s = [], 'default', [np.ones(12 * 16000)], 12
    s.spk_voice, s.spk_pitch = {}, {}
    s.spk_audio = {'p0': [np.ones(8 * 16000)]} if diarized else {}
    sent, built, dropped, voices = [], [], [], {'default': {}, 'neutral': {}}
    def add(name, ref, **kw):
        built.append(name); voices[name] = {}
    def drop(name):
        dropped.append(name); voices.pop(name, None)
    s.e = NS(gpu=threading.Lock(), asr=NS(translates=diarized, latency_s=0),
             tuning=dict(skip_same_language=True, filler_backlog=None, max_rate=1),
             mt=NS(translate=lambda *a, **kw: ('Words.', 0)),
             voice=NS(add_voice=add, drop_voice=drop,
                      stream=lambda *a, **kw: iter([(np.ones(10), 16000, None)])))
    s.run = NS(voice_epoch=0, t0=0, langs=[(1, 'it')], clock=lambda:2, samples=0,
               id_lock=threading.Lock(), id_pending=[],
               player=NS(backlog=lambda t:0, schedule=lambda *a:None))
    s.send_ts, s.voice_state = sent.append, lambda spk=None: {'type':'voice'}
    s._flush_pieces = lambda r: None
    s._pair_italian = lambda *args: []
    s.phrase_identity = lambda *args: ('p0', 1, {})
    s.neutral_voice = lambda *args: ('neutral', None)
    batch = [dict(it='Words.', speaker='p0' if diarized else None, t_first_word=1, t_last_word=1)]
    return s, batch, sent, built, dropped, voices


def main():
    for diarized in (False, True):
        # Reset after GPU construction and immediately before atomic installation.
        s, batch, sent, built, dropped, voices = fixture(diarized)
        add = s.e.voice.add_voice
        def reset_after_build(*args, **kwargs):
            acquired = []
            def probe():
                with s.voice_lock:
                    acquired.append(True)
            worker = threading.Thread(target=probe, daemon=True); worker.start(); worker.join(1)
            assert acquired, 'GPU build must not hold the voice state lock'
            add(*args, **kwargs)
            s.reset_voice()
        s.e.voice.add_voice = reset_after_build
        s._speak(s.run, batch, 1)
        assert built and dropped == built and not s.spk_voice and s.voice_name == 'default'
        assert all(name not in voices for name in built)
        assert not any(m.get('type') == 'audio' for m in sent)

        # A phrase waiting for GPU access cannot build with a superseded generation.
        s, batch, sent, built, dropped, voices = fixture(diarized)
        class ResetOnAcquire:
            def __enter__(self): s.reset_voice()
            def __exit__(self, *args): pass
        s.e.gpu = ResetOnAcquire()
        s._speak(s.run, batch, 1)
        assert not built

        # Valid build installs, and a later reset removes its epoch-specific name.
        s, batch, sent, built, dropped, voices = fixture(diarized)
        s._speak(s.run, batch, 1)
        assert len(built) == 1 and '-0' in built[0]
        assert any(m.get('wav_base64') for m in sent)
        s.reset_voice()
        assert dropped == built and not s.spk_voice and s.voice_name == 'default'
        # Old queued run does not adopt a fresh epoch or emit its audio.
        old_run = s.run
        s.run = NS(voice_epoch=s.voice_epoch)
        sent.clear(); s._speak(old_run, batch, 1)
        s._send_audio(old_run, 1, 0, np.ones(10), 16000, 1, s.voice_epoch)
        assert not sent
        s.run = old_run
        s._send_audio(old_run, 1, 0, np.ones(10), 16000, 1, 0)
        assert not sent

    # The actual stream method captures the prompt before returning its lazy iterator.
    tree = ast.parse((Path(__file__).parents[1] / 'tests/stack_compare/voice_stream.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'StreamingVoice')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'stream')
    env = dict(np=np, time=time, sync=lambda:None, length_cap=lambda text:10, CHUNK_FRAMES=8, FRAMES_PER_S=12)
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'voice_stream.py', 'exec'), env)
    prompt = {'ref_text':'', 'voice_clone_prompt':['original']}
    used = []
    def generate(**kw):
        used.append(kw['voice_clone_prompt'])
        yield np.ones(10), 16000, None
    voice = NS(voices={'custom':prompt}, tts=NS(generate_voice_clone_streaming=generate))
    stream = env['stream'](voice, 'Hello.', 'custom')
    voice.voices.pop('custom')
    list(stream)
    assert used == [['original']]
    print('PASS: diarized/single clone reset during build and GPU wait, installation/removal, stale-run audio, prompt snapshot')


if __name__ == '__main__':
    main()
