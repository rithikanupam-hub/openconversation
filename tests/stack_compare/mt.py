"""Italian -> English translation step for the cloud stacks (Qwen3 instruct on the GPU).

Translates one segment at a time with a short memory of the conversation, so pronouns, names and terms
stay consistent. Segments can be unpunctuated fragments of a sentence that continues later.
"""
import re, time

import torch

MODEL = "Qwen/Qwen3-4B-Instruct-2507"
HISTORY = 3          # previous (Italian, English) pairs shown to the model

SYSTEM = ("You are a simultaneous interpreter from Italian to English. You get the conversation so far and a NEW "
          "Italian segment. The segment may have no punctuation and may be an unfinished part of a sentence that "
          "continues in the next segment. Translate ONLY the new segment into natural spoken English that follows on "
          "from the English so far. Be faithful: keep every number, name, negation and pronoun, and keep the "
          "speaker's meaning, not a looser paraphrase. Do not repeat earlier text, do not finish unfinished thoughts, "
          "do not answer or comment. Output only the English.")
BRIEF = " Be as brief as you can without losing any meaning."


class Translator:
    def __init__(self, model=MODEL):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(model)
        self.llm = AutoModelForCausalLM.from_pretrained(model, dtype=torch.bfloat16, device_map="cuda:0")
        self.history = []

    def reset(self):
        self.history = []

    def warmup(self):
        for seg in ("Buongiorno a tutti.", "Il fatturato è cresciuto del 18 per cento"):
            self.translate(seg, remember=False)
        self.reset()

    def translate(self, italian, brief=False, remember=True, speaker=None, max_new_tokens=160, history=None):
        """Return (english, seconds). speaker: label when several people talk, so the memory shows who said what.
        history: a list to use as this conversation's memory (one per user when several share the model)."""
        t0 = time.time()
        hist = self.history if history is None else history
        tag = lambda k: f" ({k})" if k else ""
        past = "\n".join(f"IT{tag(k)}: {i}\nEN{tag(k)}: {e}" for k, i, e in hist[-HISTORY:]) \
            or "(start of the conversation)"
        msgs = [{"role": "system", "content": SYSTEM + (BRIEF if brief else "")},
                {"role": "user", "content": f"Conversation so far:\n{past}\n\nNEW Italian segment{tag(speaker)}:\n{italian}"}]
        enc = self.tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                                           return_dict=True).to("cuda")
        gen = self.llm.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False)
        english = self.tok.decode(gen[0, enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        english = re.sub(r"^EN(\s*\([^)]*\))?:\s*", "", english).strip()     # drop an echoed "EN (speaker):"
        torch.cuda.synchronize()
        if remember:
            hist.append((speaker, italian, english))
        return english, time.time() - t0
