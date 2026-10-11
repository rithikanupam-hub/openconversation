"""Model-free replay checks with a fake transport; no services, network or GPU."""
import asyncio
import base64
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

import replay_session as replay

audio = io.BytesIO()
sf.write(audio, np.ones(160)*0.1, 16000, format='WAV', subtype='PCM_16')
encoded = base64.b64encode(audio.getvalue()).decode()
GOOD = [{'type':'segment', 'id':1, 'target_text':None},
        {'type':'segment', 'id':1, 'target_text':'Agreement retained.'},
        {'type':'audio', 'id':1, 'wav_base64':encoded},
        {'type':'audio', 'id':1, 'final':True}]
assert replay.validate_output(GOOD)['translated_phrases'] == 1
for messages in [[], GOOD[:2], GOOD[:3], GOOD + [{'type':'error', 'detail':'tts failed'}], GOOD + [{'type':'audio', 'id':2, 'wav_base64':'corrupt'}]]:
    try:
        replay.validate_output(messages)
    except RuntimeError:
        pass
    else:
        raise AssertionError('accepted failed/incomplete replay')

class Socket:
    def __init__(self, messages):
        self.messages, self.queue, self.config = messages, asyncio.Queue(), None
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def __aiter__(self): return self
    async def __anext__(self):
        value = await self.queue.get()
        if value is None: raise StopAsyncIteration
        return json.dumps(value)
    async def send(self, raw):
        if isinstance(raw, bytes): return
        value = json.loads(raw)
        if value['type'] == 'config': self.config = value
        if value['type'] == 'stop':
            for m in self.messages: await self.queue.put(m)
            await self.queue.put(None)

async def check():
    with tempfile.TemporaryDirectory() as folder:
        wav, out = Path(folder)/'source.wav', Path(folder)/'events.jsonl'
        sf.write(wav, np.ones(1600)*0.1, 16000, subtype='PCM_16')
        sock = Socket(GOOD)
        with patch.object(replay.websockets, 'connect', return_value=sock):
            result = await replay.replay(wav, 'fake', 'it', 'en', False, None, out)
        assert result['audio_phrases'] == 1
        assert sock.config['consent'] is False and sock.config['clone'] is False
        assert len(out.read_text().splitlines()) == len(GOOD)
        with patch.object(replay.websockets, 'connect', return_value=Socket([])):
            try: await replay.replay(wav, 'fake', 'it', 'en', False, None)
            except RuntimeError: pass
            else: raise AssertionError('empty connection passed')
        try: await replay.replay(wav, 'fake', 'it', 'en', False, None, out)
        except FileExistsError: pass
        else: raise AssertionError('overwrote evidence')
asyncio.run(check())
print('PASS: received evidence, neutral consent config, empty/error/incomplete rejection, no overwrite')
