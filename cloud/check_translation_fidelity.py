"""Model-free checks of the actual speech path; no cloud, model imports or inference."""
import ast
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

source = ast.parse(Path(__file__).with_name('live.py').read_text())
constants = {'FILLER'}
nodes = [n for n in source.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
nodes += [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'target_only']
cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'LiveSession')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_speak')
nodes.append(method)
ns = dict(re=re, time=time, np=np, SR=16000, DEFAULT_VOICE='default', ID_LOCK_S=8, LOCK_SECONDS=12,
          ID_MAX_REF_S=15, RATES=[], VOICE_LANGS={'en': 'English'}, trim=lambda x, sr: x)
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'live.py', 'exec'), ns)


def speak(text, languages, backlog=4, diarized=False):
    sent, calls = [], []
    def translate(italian, **kw):
        calls.append(kw)
        return text, 0
    session = NS(cfg={'source_lang':'auto', 'target_lang':'en', 'clone':False, 'consent':False},
                 e=NS(gpu=threading.Lock(), tuning={'skip_same_language':True, 'filler_backlog':2.5, 'max_rate':1.15},
                      mt=NS(translate=translate), voice=NS(stream=lambda *a, **kw: iter([(np.ones(10), 16000, None)]))),
                 voice_lock=threading.RLock(), voice_epoch=0, next_id=0, identity=diarized, spk_voice={}, spk_audio={}, voice_name='default', voice_s=0,
                 history=[], rec=None, diarized=lambda:diarized, send_ts=sent.append, _flush_pieces=lambda r:None,
                 _send_audio=lambda *a:sent.append({'type':'received_test_audio'}))
    session._pair_italian = lambda *args: [('source', 0, 1, 1, 'p0', 'it')]
    session.phrase_identity = lambda *args: ('p0', 1, {})
    session.neutral_voice = lambda *args: ('default', None)
    run = NS(voice_epoch=0, samples=32000, t0=0, langs=[(1, language) for language in languages], clock=lambda:2,
             player=NS(backlog=lambda t:backlog, schedule=lambda *a:None))
    session.run = run
    ns['_speak'](session, run, [{'it':text if diarized else 'source', 'speaker':'p0' if diarized else None, 't_first_word':1, 't_last_word':1}], 1)
    if diarized:
        assert not calls, 'Soniox already supplies the translation'
    else:
        assert calls[0]['brief'] is False, 'backlog must not request a shortened translation'
    return any(m['type']=='received_test_audio' for m in sent)


for diarized in (False, True):
    for text in ['Yes.', 'Yes, yes.', 'Okay.', 'Exactly.', 'Sure.', 'Right.', 'No.', 'Not approved.',
                 'Well, yes.', 'And', 'But', 'I mean', 'You know', "Let's say", '€15,000 on Friday.']:
        assert speak(text, ['it'], diarized=diarized), (diarized, text)
    for text in ['Um.', 'Uh, uh.', 'Ehm…', 'Hmm.']:
        assert not speak(text, ['it'], diarized=diarized), (diarized, text)
        assert speak(text, ['it'], backlog=0, diarized=diarized), (diarized, text)
    assert not speak('English already understood.', ['en', 'en'], diarized=diarized)
    for languages in [['en', 'it', 'en'], ['en', None], [None], []]:
        assert speak('Preserve the translated content.', languages, diarized=diarized), (diarized, languages)
print('PASS: local + Soniox diarized branches; meaningful agreements, negation, amounts, mixed/unknown languages and no brief-backlog request')
