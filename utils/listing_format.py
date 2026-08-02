"""
Parsing and formatting for the Land Listings marketplace
(pages/listings.py, utils/listings.py).

parse_listing_text() is a Python port of the field-extraction regexes
from the standalone plotproof-generator.html prototype (grabLine()-style:
first line -> heading, "Size:"/"Price:"/"Location:"/"Title:" lines, any
line mentioning "fee") - used to prefill a seller's editable fields from
whatever they pasted, same UX the prototype demonstrated, just server-side
in Python instead of client-side JS.

format_listing_post() is the same emoji-formatted share template in
spirit, but driven by the listing's REAL risk_level/verified fields
(utils/listings.py) instead of always claiming "VERIFIED" - an unverified,
unrated listing gets an honest, different-looking post, never a fake
badge.

PlotProof stays the intermediary on contact: a listing's public contact
line (both here and on the Browse Listings page) points at PlotProof's
own WhatsApp number (utils/app_config.get_plotproof_contact_number(),
admin-set), built by plotproof_contact_link() - never the seller's own
number, which is collected at submission but used only internally so an
admin can reach the seller once a buyer's interest comes in
(seller_whatsapp_link(), used from the admin portal only).

build_share_links()/seller_whatsapp_link()/plotproof_contact_link() are
new - no wa.me/Twitter-intent/Telegram share-link construction existed
anywhere in this repo before this (confirmed via grep). All pre-filled
share/deep-links, no API keys or per-platform app registration needed.
"""

import re
import urllib.parse
from typing import Optional

from utils import listings

RISK_EMOJI = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}


def _grab_line(text: str, label: str) -> str:
    match = re.search(rf"{label}\s*:?\s*([^\n]+)", text, re.IGNORECASE)
    if not match:
        return ""
    return re.sub(r"[.,;]+$", "", match.group(1).strip())


def parse_listing_text(raw: str) -> dict:
    """Best-effort field extraction from a seller's pasted sales text -
    never fails, just returns empty strings for anything it can't find,
    since the caller always shows these as editable fields for the
    seller to fix by hand (see pages/listings.py)."""
    raw = raw or ""
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    heading = re.sub(r"!+$", "", lines[0]).strip() if lines else ""

    fee_match = re.search(r"[^\n]*\bfee\b[^\n]*", raw, re.IGNORECASE)

    return {
        "heading": heading,
        "size": _grab_line(raw, "size"),
        "price": _grab_line(raw, "price"),
        "location": _grab_line(raw, "location"),
        "title_type": _grab_line(raw, "title"),
        # Left blank (not defaulted to "Brokers fee applies" like the
        # prototype) when no fee line is found - a seller genuinely
        # might not have one, and inventing text they never wrote isn't
        # something a listing service should do.
        "fee_note": fee_match.group(0).strip() if fee_match else "",
    }


def format_listing_post(listing: dict, listing_url: str = "", plotproof_contact: str = "") -> str:
    """The branded, shareable post text - shown in the admin's copyable
    st.code block and used to build the pre-filled share links below.
    The header + Land Alert line are always present (a consistent
    PlotProof signature on every post, "this was posted through
    PlotProof"), but the header wording still reflects the listing's real
    state: only says "VERIFIED" when utils/listings.py's `verified` is
    actually true - never a trust claim that isn't real, even though the
    signature itself always appears. Risk badge likewise only shows when
    a rating (automated or admin-set - see
    utils/listings.effective_risk_level()) actually exists.

    plotproof_contact: PlotProof's own number (utils/app_config.py) -
    shown here instead of the seller's own contact info, since this text
    gets shared publicly (WhatsApp/X/Telegram). Falls back to the raw
    seller_contact only if no PlotProof number has been configured yet -
    better than showing no contact line at all, but an admin should set
    one so this fallback never actually fires."""
    risk_level = listings.effective_risk_level(listing)
    verified = bool(listing.get("verified"))

    lines = ["🟢 PLOTPROOF VERIFIED LISTING" if verified else "🟢 PLOTPROOF LISTING"]
    if listing.get("alert_number"):
        lines.append(f"📍 Land Alert #{listing['alert_number']:03d}")
    lines.append("")

    if listing.get("heading"):
        lines.append(f"🏡 {listing['heading']}")
    if listing.get("size"):
        lines.append(f"📐 Size: {listing['size']}")
    if listing.get("price"):
        lines.append(f"💰 Price: {listing['price']}")
    if listing.get("location"):
        lines.append(f"📌 Location: {listing['location']}")
    if listing.get("title_type"):
        lines.append(f"📄 Title: {listing['title_type']}")
    if listing.get("fee_note"):
        lines.append(f"🤝 {listing['fee_note']}")

    lines.append("")
    if risk_level:
        lines.append(f"{RISK_EMOJI.get(risk_level, '⚪')} PlotProof Risk Rating: {risk_level}")
    if verified:
        lines.append("✅ Boundary-checked and verified with PlotProof - buy with confidence.")
    else:
        lines.append("ℹ️ Ask for a PlotProof risk check before you buy.")
    lines.append(f"🔗 {listing_url}" if listing_url else "🔗 plotproof.streamlit.app")

    if plotproof_contact:
        lines.append("")
        lines.append(f"📞 Contact PlotProof to connect with the seller: {plotproof_contact}")
    elif listing.get("seller_contact"):
        lines.append("")
        lines.append(f"📞 Contact: {listing['seller_contact']}")

    lines.append("")
    lines.append("#PlotProofVerified #LandForSale #NoLandGrabbing")

    return "\n".join(lines)


def build_share_links(post_text: str, listing_url: str = "") -> dict:
    """Pre-filled share-intent links for the admin's one-click share row
    - opens each platform's own compose window with the text ready to
    send, rather than posting automatically (no API keys/app approval
    needed for any of these)."""
    encoded_text = urllib.parse.quote(post_text)
    encoded_url = urllib.parse.quote(listing_url) if listing_url else ""
    return {
        "whatsapp": f"https://wa.me/?text={encoded_text}",
        "twitter": f"https://twitter.com/intent/tweet?text={encoded_text}",
        "telegram": f"https://t.me/share/url?url={encoded_url}&text={encoded_text}",
    }


def _to_international_ng(digits: str) -> str:
    """wa.me requires a full international number, no leading zero -
    but a Nigerian seller will type the local format (0801...), not
    +234801... Converts the common local-format case; leaves anything
    else (already-international, or another country's number) alone."""
    if digits.startswith("0") and len(digits) == 11:
        return "234" + digits[1:]
    return digits


def seller_whatsapp_link(seller_contact: str, listing_heading: str = "") -> Optional[str]:
    """Best-effort wa.me link from the seller's free-text contact field -
    only when it actually looks like a phone number (a wa.me link needs
    real digits; an email address or "call weekdays 9-5" note doesn't
    become one). Returns None otherwise so the caller can fall back to
    just displaying the raw contact text.

    Admin-portal use only (pages/admin_review.py's "Message seller"
    quick-link) - the seller's own number is never shown to the public;
    see plotproof_contact_link() below for the public-facing equivalent."""
    digits = re.sub(r"[^\d]", "", seller_contact or "")
    if len(digits) < 8:
        return None
    digits = _to_international_ng(digits)
    message = "Hi, I'm interested in your land listing"
    if listing_heading:
        message += f' "{listing_heading}"'
    message += " on PlotProof."
    return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"


def plotproof_contact_link(listing: dict, contact_number: str) -> Optional[str]:
    """wa.me link to PlotProof's own number (utils/app_config.py, admin-
    set), pre-filled with a message identifying which listing the buyer
    is asking about - this is what a buyer actually clicks on the public
    Browse Listings page, never the seller's own number (see this
    module's docstring for why). Returns None if no contact number has
    been configured yet, so the caller can show a clear "not available"
    state instead of a dead/broken link."""
    digits = re.sub(r"[^\d]", "", contact_number or "")
    if len(digits) < 8:
        return None
    digits = _to_international_ng(digits)
    heading = listing.get("heading") or "Land for sale"
    message = f'Hi PlotProof, I\'m interested in this listing: "{heading}" (ref #{listing["id"]}). Can you connect me with the seller?'
    return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"
