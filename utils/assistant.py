"""
A small Q&A assistant scoped to the user's own, already-computed result -
"explain this report" in plain English, not a general chatbot. Every answer
is grounded in the actual risk_level/findings/recommendations/coordinates
already shown on the page (passed in as `context`), plus the report never
claims anything about the specific plot beyond that data - it's instructed
to say "ask a licensed surveyor" rather than guess when a question needs
information PlotProof doesn't have.

Uses the same Claude client/API key resolution as utils/vision_extract.py
(utils/app_config.py's admin-override-then-env-var lookup). Text-only, no
image, so a single non-streaming call is fine for the short answers this
produces.
"""

from typing import Optional

import anthropic

from utils import app_config

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


def is_available() -> bool:
    return bool(app_config.get_anthropic_api_key())


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
