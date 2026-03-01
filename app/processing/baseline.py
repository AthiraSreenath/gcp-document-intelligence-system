"""Baseline NLP methods (non-LLM): spaCy NER + TextRank summary.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import re
import time
from collections import Counter

import spacy

@dataclass
class BaselineResult:
    extractive_summary: Optional[str] = None
    spacy_entities: Optional[List[Dict[str, Any]]] = None
    latency_ms: Optional[Dict[str, int]] = None

_SPACY = None

def get_spacy(model: str = "en_core_web_sm"):
    global _SPACY
    if _SPACY is None:
        _SPACY = spacy.load(model)
    return _SPACY

def spacy_entities(text: str, max_entities: int = 50) -> List[Dict[str, Any]]:
    nlp = get_spacy()
    doc = nlp(text)
    out = []
    for ent in doc.ents[:max_entities]:
        out.append({"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char})
    return out

def simple_extractive_summary(text: str, max_sentences: int = 3) -> str:
    """
    Traditional baseline: frequency-based extractive summary.
    - Sentence split (regex)
    - Score sentences by token frequency
    - Pick top N sentences (keep original order)
    """
    # sentence split (keeps it dependency-light)
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sents) <= max_sentences:
        return " ".join(sents)

    # tokenize words
    words = re.findall(r"[A-Za-z][A-Za-z'-]{1,}", text.lower())
    if not words:
        return " ".join(sents[:max_sentences])

    freq = Counter(words)

    def score(sent: str) -> float:
        ws = re.findall(r"[A-Za-z][A-Za-z'-]{1,}", sent.lower())
        if not ws:
            return 0.0
        return sum(freq[w] for w in ws) / (len(ws) ** 0.5)

    scored = [(i, score(s), s) for i, s in enumerate(sents)]
    top = sorted(scored, key=lambda x: x[1], reverse=True)[:max_sentences]
    top_idx = sorted([i for i, _, _ in top])
    return " ".join(sents[i] for i in top_idx)

def run_baselines(text: str) -> BaselineResult:
    lat: Dict[str, int] = {}

    t0 = time.perf_counter()
    ents = spacy_entities(text)
    lat["spacy_ner"] = int((time.perf_counter() - t0) * 1000)

    t1 = time.perf_counter()
    summ = simple_extractive_summary(text, max_sentences=3)
    lat["extractive"] = int((time.perf_counter() - t1) * 1000)

    return BaselineResult(extractive_summary=summ, spacy_entities=ents, latency_ms=lat)