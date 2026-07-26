"""
Two Q&A assistants, both scoped narrowly rather than general chatbots:

  - ask() - grounded in the user's own, already-computed result (risk
    level, findings, coordinates). Used by the "Ask about this report"
    expander on the results page (see app_home.py).
  - ask_general() - no specific result to ground in; answers general
    questions about Nigerian land/surveys and about PlotProof itself.
    Used by the floating chat (utils/nav.py's render_floating_chat()),
    available from every page. Explicitly instructed not to claim
    anything about "your land" specifically, since it has no document to
    read - that's the whole reason the floating chat always points back
    to the real upload/coordinates flow instead of trying to answer
    plot-specific questions itself.

Uses the same Claude client/API key resolution as utils/vision_extract.py
(utils/app_config.py's admin-override-then-env-var lookup). Text-only, no
image, so a single non-streaming call is fine for the short answers this
produces.

Both raise on failure (network error, rate limit, or - confirmed as a
real recurring failure mode for this project - the account's credit
balance running out) rather than swallowing the exception; callers
already wrap each call in a try/except (see app_home.py, utils/nav.py)
and now use fallback_answer() below when it fails, instead of a dead-end
"something went wrong" with no useful next step.
"""

import re
from typing import List, Optional, Tuple

import anthropic

from utils import app_config, faq_content

MODEL = "claude-opus-4-8"

_SYSTEM_PROMPT = """You are the assistant embedded in a PlotProof land boundary risk report for a \
Nigerian property buyer. Answer questions about THIS SPECIFIC report only - you are not a general \
chatbot. Ground every answer strictly in the report data given below, plus general, widely-known \
facts about how Nigerian land surveying/buying works (e.g. what a survey plan is, what a licensed \
surveyor does, why title verification matters).

Rules:
- Keep answers short - 2-4 sentences, plain English, no unexplained jargon.
- Never state or imply anything about this specific plot that isn't in the report data below. If \
the answer isn't in the data, say so plainly and suggest who could actually answer it (a licensed \
surveyor, a lawyer, the land registry) rather than guessing.
- PlotProof is an automated preliminary screening tool, not a certified survey or legal opinion. \
If a question is really "should I buy this land / is this a good deal", say that's a decision for \
the buyer with professional advice, not something this tool can answer - point back to the risk \
level and recommendations already shown instead.
- If asked something entirely unrelated to this report or land verification, politely decline and \
redirect to what you can help with.

Report data:
{report_context}"""


_GENERAL_SYSTEM_PROMPT = """You are PlotProof's floating chat assistant, available on every page of the \
site. Answer only two kinds of questions:

1. General questions about Nigerian land, surveys, and property ownership - what a survey plan is, \
what a Certificate of Occupancy is, common land-fraud patterns, what "beacon"/"coordinates"/"boundary \
overlap" mean, what to check before buying land, how to engage a licensed surveyor, and similar. \
General education, not advice about any specific plot.
2. Questions about what PlotProof itself does and how to use it - the instant risk check, comparing \
two specific plots directly, uploading a survey plan (PDF or photo) vs. typing coordinates by hand, \
the downloadable PDF/CSV/GeoJSON report, the bearing/distance review table, the diagonal check.

Rules:
- Keep answers short - 2-4 sentences, plain English, no unexplained jargon.
- You have no document, coordinates, or result for this specific user - you cannot see any land \
they own or have checked. Never state or imply anything about "your land" or "your plot" \
specifically. If asked something like "is my land safe" or "should I buy this plot", explain that \
this needs their actual survey plan or coordinates run through the real check, not general chat.
- If asked something with no connection to land, property, surveying, or PlotProof, politely decline \
and redirect to what you can help with instead.
- End on a natural note encouraging them to try the actual check (upload a survey plan or enter \
coordinates) rather than just chatting - but vary the phrasing, don't repeat a canned sentence \
verbatim every time."""


def is_available() -> bool:
    return bool(app_config.get_anthropic_api_key())


# Common short words that would otherwise dominate the overlap score
# without actually indicating topic similarity ("what is a survey plan"
# vs "what is a coordinate" share 3 of 4 words this way, none of them
# meaningful) - trimmed before scoring, not because they're wrong to ask,
# just not useful signal for which FAQ entry matches.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "what", "how", "why", "can", "could", "should", "would", "will",
    "i", "my", "me", "you", "your", "it", "its", "this", "that",
    "of", "in", "on", "for", "to", "and", "or", "about",
}

# Jaccard similarity (intersection / union), not intersection / len(faq
# words) - dividing by the FAQ side alone let a single shared common word
# ("land") "match" a short FAQ question almost by accident, e.g. a
# genuinely report-specific "why is my land high risk" scoring 0.5
# against "Can I buy this land?" on the word "land" alone (confirmed as a
# real false positive before switching to Jaccard). Dividing by the union
# instead means extra words in the question that aren't in the FAQ
# question (like "high risk" there) correctly drag the score down.
_FALLBACK_MATCH_THRESHOLD = 0.5


def _keywords(text: str) -> set:
    # No apostrophe in the character class (unlike vision_extract.py's
    # bearing regexes, which need it) - "what's"/"it's" would otherwise
    # survive as one token distinct from "what"/"it" and slip past
    # _STOPWORDS, which only lists the unquoted forms.
    return set(re.findall(r"[a-z]+", text.lower())) - _STOPWORDS


def fallback_answer(question: str) -> Optional[str]:
    """Best-effort static answer from the FAQ (utils/faq_content.py) for
    when the live Claude API isn't reachable (credit balance, rate limit,
    network) - a real fallback, not an improvised one: only ever returns
    text that's already reviewed and shown on the Common Questions page.
    Returns None if nothing matches well enough, so the caller falls back
    further still (a plain "temporarily unavailable" message) rather than
    force a bad match."""
    question_words = _keywords(question)
    if not question_words:
        return None

    best_score, best_answer = 0.0, None
    for faq_question, faq_answer in faq_content.FAQ_ENTRIES:
        faq_words = _keywords(faq_question)
        if not faq_words:
            continue
        union = question_words | faq_words
        score = len(question_words & faq_words) / len(union) if union else 0.0
        if score > best_score:
            best_score, best_answer = score, faq_answer

    return best_answer if best_score >= _FALLBACK_MATCH_THRESHOLD else None


def _build_context(context: dict) -> str:
    lines = [
        f"- Risk level: {context.get('risk_level')}",
        f"- Why: {context.get('reason')}",
        f"- Key findings: {'; '.join(context.get('findings') or []) or '(none)'}",
        f"- Recommendations: {'; '.join(context.get('recommendations') or []) or '(none)'}",
        f"- Coordinate points assessed: {context.get('point_count')}",
        f"- Coordinate system note: {context.get('crs_note') or 'already WGS84 latitude/longitude'}",
    ]
    doc = context.get("document_info") or {}
    doc_bits = [f"{k.replace('_', ' ')}: {v}" for k, v in doc.items() if v]
    if doc_bits:
        lines.append(f"- Document details (auto-read, may be incomplete): {', '.join(doc_bits)}")
    return "\n".join(lines)


def ask(question: str, context: dict) -> str:
    client = anthropic.Anthropic(api_key=app_config.get_anthropic_api_key())
    response = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=_SYSTEM_PROMPT.format(report_context=_build_context(context)),
        messages=[{"role": "user", "content": question}],
    )
    return next(b.text for b in response.content if b.type == "text")


def ask_general(question: str, history: Optional[List[Tuple[str, str]]] = None) -> str:
    """history: recent (question, answer) pairs, oldest first - sent as
    real prior turns (not just summarized in text) so the floating chat
    can hold an actual back-and-forth, e.g. a follow-up "what about..."
    referring to the previous answer. Callers only need to pass the last
    few exchanges; unlike ask() above there's no per-report data to stay
    grounded in, so there's no correctness reason to cap this tightly -
    it's capped by the caller purely to bound token cost."""
    client = anthropic.Anthropic(api_key=app_config.get_anthropic_api_key())
    messages = []
    for prior_question, prior_answer in history or []:
        messages.append({"role": "user", "content": prior_question})
        messages.append({"role": "assistant", "content": prior_answer})
    messages.append({"role": "user", "content": question})

    response = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=_GENERAL_SYSTEM_PROMPT,
        messages=messages,
    )
    return next(b.text for b in response.content if b.type == "text")
