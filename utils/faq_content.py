"""
Shared FAQ content - the single source of truth for pages/faq.py's static
page AND utils/assistant.py's fallback answers when the live Claude API
isn't reachable (credit balance, rate limit, network). One list so the
two can never drift, and so a fallback answer is only ever exactly what's
already reviewed and shown on the FAQ page - never improvised.
"""

from typing import List, Tuple

from utils import theme

FAQ_ENTRIES: List[Tuple[str, str]] = [
    (
        "What is a survey plan?",
        "The official document a licensed surveyor produces after measuring your land - it shows "
        "your plot's boundary, corner coordinates, and size. It's what PlotProof reads to check "
        "your boundary.",
    ),
    (
        "What are coordinates?",
        "Numbers that pinpoint each corner of your land on a map - usually latitude/longitude, or "
        "a local Easting/Northing pair tied to a specific coordinate system. Your survey plan "
        "normally lists these for every corner (\"beacon\").",
    ),
    (
        "Why might my land get flagged?",
        f"Low risk - {theme.RISK_EXPLAINER['Low']} Medium risk - {theme.RISK_EXPLAINER['Medium']} "
        f"High risk - {theme.RISK_EXPLAINER['High']}",
    ),
    (
        "Can I buy this land?",
        "PlotProof isn't a legal opinion and can't answer that directly. A Low risk result is a "
        "good sign, but it only reflects plots currently on record - always get a licensed "
        "surveyor's verification and proper legal due diligence (e.g. a title search) before any "
        "transaction.",
    ),
    (
        "What's in my downloaded report?",
        "The PDF includes your boundary coordinates, the risk level, the specific findings behind "
        "it, recommendations, and a map showing your plot against nearby registered plots - bring "
        "it to a licensed surveyor if you want a professional opinion on it. CSV and GeoJSON "
        "downloads (the raw coordinates/boundary, no formatting) are also available after a check "
        "completes.",
    ),
    (
        "What does PlotProof do?",
        "PlotProof reads a survey plan (or manually entered coordinates) and checks the boundary "
        "it describes against known neighboring plots for overlaps and close-proximity risks - an "
        "instant, automated first pass before you commit time or money to a land purchase.",
    ),
    (
        "How do I use PlotProof?",
        "Upload a survey plan (PDF or photo) or type in boundary coordinates, then click Analyze "
        "My Land. You'll get a Low/Medium/High risk result, a map, and a downloadable report - "
        "takes under a minute, no signup required.",
    ),
]
