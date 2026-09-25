"""Pitch expressiveness: how much the voice's pitch moves (std of F0 in semitones, voiced frames),
compared with the real reader. Flat, robotic speech scores low; the real reader is the target.
Adds `expr` to scores.json and prints a per-model summary."""
import json, os
import numpy as np, librosa
HERE = os.path.dirname(os.path.abspath(__file__))

def f0_semitone_std(path):
    y, sr = librosa.load(path, sr=16000)
    f0, voiced, _ = librosa.pyin(y, fmin=60, fmax=450, sr=sr, frame_length=1024)
    f0 = f0[voiced & ~np.isnan(f0)]
    if len(f0) < 20:
        return float("nan")
    st = 12 * np.log2(f0 / np.median(f0))
    return float(np.std(st))

S = json.load(open(f"{HERE}/scores.json"))
ref = {s: np.mean([f0_semitone_std(f"{HERE}/ref/{s}_{k}.wav") for k in ("ref", "holdout")]) for s in ("simona", "filippo")}
print("real readers:", {k: round(v, 2) for k, v in ref.items()})
for r in S["results"]:
    for row in r["rows"]:
        if "wav" in row:
            row["expr"] = round(f0_semitone_std(row["wav"]), 2)
            row["expr_ratio"] = round(row["expr"] / ref[row["speaker"]], 2)
    xs = [x["expr_ratio"] for x in r["rows"] if "expr_ratio" in x]
    print(f"{r['model']:18s} expressiveness vs real reader: {np.nanmean(xs):.2f}")
S["ref_expr"] = ref
json.dump(S, open(f"{HERE}/scores.json", "w"), indent=1, default=float)
