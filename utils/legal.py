"""
Loads the Terms of Service / Privacy Policy markdown and fills in the
one runtime placeholder (the privacy contact address) so the rendered
policy never silently ships with a broken bracket placeholder in it.
"""

import os
from pathlib import Path

LEGAL_DIR = Path(__file__).resolve().parent.parent / "legal"

PRIVACY_CONTACT_EMAIL = os.environ.get("PRIVACY_CONTACT_EMAIL", "").strip()
_CONTACT_PLACEHOLDER = "[PRIVACY_CONTACT_EMAIL - to be configured]"
_CONTACT_FALLBACK = (
    "*(No privacy contact email has been configured for this deployment yet - "
    "use the WhatsApp/consultation links in the app in the meantime.)*"
)


def get_terms() -> str:
    return (LEGAL_DIR / "terms.md").read_text()


def get_privacy_policy() -> str:
    text = (LEGAL_DIR / "privacy.md").read_text()
    replacement = PRIVACY_CONTACT_EMAIL if PRIVACY_CONTACT_EMAIL else _CONTACT_FALLBACK
    return text.replace(_CONTACT_PLACEHOLDER, replacement)
