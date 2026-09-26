# Voice-clone eval

Anchors (same WavLM similarity scale):
- same real reader, other clip (ceiling): **0.98**
- the two readers vs each other (different person): **0.78**

| Model | Voice similarity EN (0–1) | Similarity IT | Word errors EN | Speed (RTF, lower = faster) | Memory | Speaks Italian |
|---|---|---|---|---|---|---|
| pocket | 0.92 | – | 0.09 | 0.23 | 1.5 GB | no |
| chatterbox_turbo | 0.93 | – | 0.10 | 1.27 | 1.76 GB | no |
| chatterbox_multi | 0.96 | 0.97 | 0.10 | 4.70 | 4.39 GB | yes |
| qwen3_0.6b | 0.97 | 0.97 | 0.04 | 3.43 | 5.91 GB | yes |
| qwen3_0.6b_8bit | 0.97 | 0.98 | 0.10 | 1.79 | 5.33 GB | yes |
| qwen3_0.6b_4bit | 0.97 | 0.97 | 0.09 | 1.82 | 5.21 GB | yes |
| qwen3_1.7b | 0.96 | 0.96 | 0.09 | 10.39 | 7.57 GB | yes |
| voxcpm2 | 0.97 | 0.96 | 0.06 | 5.46 | 4.77 GB | yes |
