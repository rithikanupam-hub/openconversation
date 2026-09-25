"""Score the voice-clone eval and build a listening page.

- Similarity: cosine of WavLM speaker-verification embeddings (microsoft/wavlm-base-plus-sv) between each
  cloned output and a *held-out* clip of the real reader (not the clip the model cloned from).
  Anchors: the real reader vs their own held-out clip (ceiling) and reader A vs reader B (different person).
- Intelligibility: Parakeet transcribes each output; word error rate against the intended text.
Writes tests/voice_eval/results.md and tests/voice_eval/index.html.
Usage: PYTHONPATH=. .venv/bin/python -m tests.voice_eval.score
"""
import glob, html, json, logging, os, re
import numpy as np, soundfile as sf, torch
from transformers import AutoFeatureExtractor, WavLMForXVector

logging.basicConfig(level=logging.ERROR)
HERE = os.path.dirname(os.path.abspath(__file__))
from tests.voice_eval.run_model import MODELS, TEXTS  # noqa: E402
from backend.pipeline import pipeline, _resample  # noqa: E402

fe = AutoFeatureExtractor.from_pretrained("microsoft/wavlm-base-plus-sv")
sv = WavLMForXVector.from_pretrained("microsoft/wavlm-base-plus-sv").eval()


def load16(path):
    a, sr = sf.read(path, dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    return _resample(a, sr, 16000)


def embed(path):
    a = load16(path)
    with torch.no_grad():
        x = fe(a, sampling_rate=16000, return_tensors="pt")
        e = sv(**x).embeddings[0]
    return torch.nn.functional.normalize(e, dim=-1)


def sim(a, b):
    return float((a * b).sum())


def words(t):
    t = t.lower().replace("’", "'")
    return re.findall(r"[a-zàèéìòù0-9']+", t)


def wer(ref, hyp):
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


speakers = ["simona", "filippo"]
hold = {s: embed(f"{HERE}/ref/{s}_holdout.wav") for s in speakers}
refe = {s: embed(f"{HERE}/ref/{s}_ref.wav") for s in speakers}
anchors = {
    "same real reader, other clip (ceiling)": np.mean([sim(refe[s], hold[s]) for s in speakers]),
    "the two readers vs each other (different person)": np.mean([sim(refe["simona"], hold["filippo"]),
                                                                 sim(refe["filippo"], hold["simona"])]),
}
print("anchors", {k: round(v, 3) for k, v in anchors.items()})

results = []
for key in MODELS:
    f = f"{HERE}/out/{key}/results.json"
    if not os.path.exists(f):
        continue
    r = json.load(open(f))
    for row in r["rows"]:
        if "wav" not in row:
            continue
        row["sim"] = round(sim(embed(row["wav"]), hold[row["speaker"]]), 3)
        a = load16(row["wav"])
        hyp = pipeline._parakeet(a)
        row["asr"] = hyp
        row["wer"] = round(wer(TEXTS[row["text"]], hyp), 2)
        print(key, row["speaker"], row["text"], "sim", row["sim"], "wer", row["wer"], flush=True)
    results.append(r)
json.dump({"anchors": anchors, "results": results}, open(f"{HERE}/scores.json", "w"), indent=1, default=float)

# ---------------------------------------------------------------- summary table
lines = ["| Model | Voice similarity EN (0–1) | Similarity IT | Word errors EN | Speed (RTF, lower = faster) | Memory | Speaks Italian |",
         "|---|---|---|---|---|---|---|"]
for r in results:
    rows = [x for x in r["rows"] if "sim" in x]
    en = [x for x in rows if x["lang"] == "en"]
    it = [x for x in rows if x["lang"] == "it"]
    m = lambda xs, k: f"{np.mean([x[k] for x in xs]):.2f}" if xs else "–"
    errs = [x for x in r["rows"] if "error" in x]
    lines.append(f"| {r['model']} | {m(en,'sim')} | {m(it,'sim')} | {m(en,'wer')} | {m(rows,'rtf')} | "
                 f"{r['peak_gb']} GB | {'yes' if 'it' in r['langs'] else 'no'}{' ⚠ ' + str(len(errs)) + ' errors' if errs else ''} |")
anchor_md = "\n".join(f"- {k}: **{v:.2f}**" for k, v in anchors.items())
md = f"# Voice-clone eval\n\nAnchors (same WavLM similarity scale):\n{anchor_md}\n\n" + "\n".join(lines) + "\n"
open(f"{HERE}/results.md", "w").write(md)
print(md)

# ---------------------------------------------------------------- listening page
rel = lambda p: os.path.relpath(p, HERE)
cells = []
for r in results:
    for row in r["rows"]:
        if "wav" not in row:
            continue
        cells.append(f"<tr><td>{r['model']}</td><td>{row['speaker']}</td><td>{row['text']}</td>"
                     f"<td><audio controls preload='none' src='{rel(row['wav'])}'></audio></td>"
                     f"<td>{row['sim']:.2f}</td><td>{row['wer']:.2f}</td><td>{row['rtf']:.2f}</td>"
                     f"<td class='asr'>{html.escape(row['asr'])}</td></tr>")
refs = "".join(f"<p><b>{s}</b> (real reader, cloned from this clip): <audio controls src='ref/{s}_ref.wav'></audio></p>"
               for s in speakers)
page = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Voice clone test</title><style>
:root{{--bg:#ece9e2;--ink:#17140f;--dim:#6b655c;--card:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141210;--ink:#f2eee8;--dim:#a39d94;--card:#201d1a}}}}
body{{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px}}
table{{border-collapse:collapse;background:var(--card);width:100%}}td,th{{padding:6px 8px;border-bottom:1px solid #8883;text-align:left;vertical-align:middle}}
.asr{{color:var(--dim);font-size:12px;max-width:320px}}audio{{height:32px}}pre{{white-space:pre-wrap}}
</style></head><body><h1>Open-source voice clone test</h1>
<p>Texts: {html.escape(json.dumps(TEXTS, ensure_ascii=False))}</p>{refs}
<h2>Scores</h2><pre>{html.escape(md)}</pre>
<h2>Listen</h2><table><tr><th>Model</th><th>Voice of</th><th>Text</th><th>Audio</th><th>Similarity</th><th>Word errors</th><th>RTF</th><th>What Parakeet heard</th></tr>
{''.join(cells)}</table></body></html>"""
open(f"{HERE}/index.html", "w").write(page)
print("wrote", f"{HERE}/index.html")
