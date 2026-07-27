"""
Matches a visitor's question to the closest admin-trained passage
(utils/land_chat_training.py) for the floating land chat
(utils/nav.py's render_floating_chat()) - no external API involved.

Pure stdlib TF-IDF cosine similarity, not an embedding model - the
passage corpus is small and admin-curated, so recomputing term
frequencies fresh on every question is cheap, needs no new dependency
(unlike sentence-transformers/torch, which would be heavy for Streamlit
Cloud's free tier), and stays fully deterministic and debuggable. Weights
rare/distinctive words higher than common ones, e.g. "beacon" matters
more than "land" - a real improvement over plain keyword overlap
(utils/assistant.py's fallback_answer(), which stays as-is for the
separate report-grounded chat it serves).

By product decision, match() always returns the closest passage once at
least one is trained (never a dead "I don't know") - low_confidence is
the caller's signal to caveat a weak match rather than withhold it.
"""

import math
import re
from collections import Counter
from typing import Dict, List, Optional

from utils import land_chat_training

# Small and self-contained, not shared with utils/assistant.py's
# _STOPWORDS - that one backs a Jaccard set-overlap score, this one backs
# term *counts* (a word appearing twice should count twice), so the two
# tokenizers aren't interchangeable even though the word lists look
# similar. Not worth coupling two independent features over a ~25-word
# literal.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "what", "how", "why", "can", "could", "should", "would", "will",
    "i", "my", "me", "you", "your", "it", "its", "this", "that",
    "of", "in", "on", "for", "to", "and", "or", "about",
}

# Cosine similarity on a small, sparse, TF-IDF-weighted vocabulary rarely
# exceeds ~0.5 even for a strong match, and off-topic questions typically
# land under 0.1 (no shared distinctive terms at all) - this sits between
# the two, tuned against representative on/off-topic questions during
# development rather than derived analytically.
LOW_CONFIDENCE_THRESHOLD = 0.15


def _tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOPWORDS and len(w) > 1]


def _build_idf(documents: List[List[str]]) -> Dict[str, float]:
    doc_count = len(documents)
    doc_freq: Counter = Counter()
    for doc in documents:
        for term in set(doc):
            doc_freq[term] += 1
    return {term: math.log((doc_count + 1) / (freq + 1)) + 1 for term, freq in doc_freq.items()}


def _tfidf_vector(tokens: List[str], idf: Dict[str, float]) -> Dict[str, float]:
    if not tokens:
        return {}
    term_freq = Counter(tokens)
    total = len(tokens)
    return {term: (count / total) * idf.get(term, 0.0) for term, count in term_freq.items()}


def _cosine(vector_a: Dict[str, float], vector_b: Dict[str, float]) -> float:
    shared = set(vector_a) & set(vector_b)
    if not shared:
        return 0.0
    numerator = sum(vector_a[t] * vector_b[t] for t in shared)
    norm_a = math.sqrt(sum(v * v for v in vector_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vector_b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return numerator / (norm_a * norm_b)


def rank_passages(question: str) -> List[dict]:
    """Every trained passage with its match score against `question`,
    best first. Used both by match() below and by the admin portal's
    "test a question" tool (shows the top few so the admin can judge
    match quality while training)."""
    passages = land_chat_training.list_passages()
    if not passages:
        return []

    corpus_tokens = [_tokenize(f"{p.get('title', '')} {p.get('text', '')}") for p in passages]
    question_tokens = _tokenize(question)
    idf = _build_idf(corpus_tokens + [question_tokens])
    question_vector = _tfidf_vector(question_tokens, idf)

    scored = [
        {"passage": passage, "score": _cosine(question_vector, _tfidf_vector(tokens, idf))}
        for passage, tokens in zip(passages, corpus_tokens)
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored


def match(question: str) -> Optional[dict]:
    """Best-matching trained passage for `question`, or None if nothing's
    been trained yet. Returns {"passage": {...}, "score": float,
    "low_confidence": bool}."""
    ranked = rank_passages(question)
    if not ranked:
        return None
    best = ranked[0]
    return {
        "passage": best["passage"],
        "score": best["score"],
        "low_confidence": best["score"] < LOW_CONFIDENCE_THRESHOLD,
    }
