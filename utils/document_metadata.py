"""
Best-effort extraction of a survey plan's document-level metadata (survey
number, surveyor name, plan date, scale, area) from OCR/PDF-extracted text -
the "who/when/what plan is this" details, separate from the coordinates
themselves.

This is regex pattern-matching against free-form OCR text, not a layout-aware
reader, so it inherits the same reliability limits as the rest of the
text-extraction pipeline (see coordinates.py's module docstring) - fields
come back None rather than a guess when a pattern doesn't match cleanly.
Always shown to the user as "as read from your document, please verify"
rather than trusted silently, same framing as the bearing/distance table.

The vision-extraction path (vision_extract.py, image uploads via Claude) has
its own equivalent fields read directly from the image, generally more
reliable than this regex pass for the plan types it's used on.
"""

import re
from typing import Optional

from utils.traverse import parse_area_sqm, parse_scale_ratio

# "SURVEY No: LA 12345" / "PLAN NO. OG/1234/2020" / "FILE No:- KW/5678"
_SURVEY_NUMBER_RE = re.compile(
    r"(?:SURVEY|PLAN|FILE)\s*NO\.?\s*[:\-]?\s*([A-Z]{0,4}[/\-]?\d[A-Z0-9/\-]{2,20})", re.IGNORECASE
)

# "SURVEYOR: JANE DOE" / "SURVEYED BY: JOHN A. SMITH" - deliberately narrow
# (exact label, then a short run of name-shaped tokens, same line only via
# [ \t] rather than \s so it can't bleed into the next line/field on OCR
# text with no blank-line separators) to avoid matching unrelated phrases
# like "surveyor's beacon" or "licensed surveyor" alone.
_SURVEYOR_RE = re.compile(
    r"SURVEYED[ \t]+BY\s*[:\-]?[ \t]*([A-Z][A-Za-z.'\-]*(?:[ \t]+[A-Z][A-Za-z.'\-]*){0,3})"
    r"|SURVEYOR\s*[:\-][ \t]*([A-Z][A-Za-z.'\-]*(?:[ \t]+[A-Z][A-Za-z.'\-]*){0,3})",
    re.IGNORECASE,
)

_MONTHS = (
    "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
)
# "12TH DAY OF MARCH, 2020" / "3RD MARCH 2020"
_DATE_WORDS_RE = re.compile(
    r"\b(\d{1,2})(?:ST|ND|RD|TH)?\s*(?:DAY\s+OF\s+)?(" + _MONTHS + r")\.?,?\s*(\d{4})\b", re.IGNORECASE
)
# "12/03/2020" or "12-03-2020"
_DATE_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b")


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = " ".join(s.split()).strip(" :-.")
    return s or None


def parse_survey_number(text: str) -> Optional[str]:
    match = _SURVEY_NUMBER_RE.search(text)
    return _clean(match.group(1)) if match else None


# Guards against the common OCR failure mode where a line break was lost
# and the next field's label ran on immediately after the name with only a
# space between them ("SURVEYED BY JOHN SMITH AREA:- 621.072SQ.MTS").
_TRAILING_LABEL_WORDS = {"AREA", "SCALE", "DATE", "DATED", "PLAN", "SURVEY", "LICENCE", "LICENSE", "REG", "NO"}


def parse_surveyor_name(text: str) -> Optional[str]:
    match = _SURVEYOR_RE.search(text)
    if not match:
        return None
    name = _clean(match.group(1) or match.group(2))
    if not name:
        return None
    words = name.split()
    while words and words[-1].upper().rstrip(":.-") in _TRAILING_LABEL_WORDS:
        words.pop()
    return " ".join(words) or None


def parse_plan_date(text: str) -> Optional[str]:
    match = _DATE_WORDS_RE.search(text)
    if match:
        day, month, year = match.groups()
        return f"{int(day)} {month.title()} {year}"
    match = _DATE_NUMERIC_RE.search(text)
    if match:
        return match.group(0)
    return None


def extract_from_text(text: str) -> dict:
    """Returns a dict with the same keys extract_points_from_image()'s
    document_info carries, so app_home.py can display either path's result
    through one code path regardless of which extraction method ran."""
    scale_ratio = parse_scale_ratio(text)
    return {
        "survey_number": parse_survey_number(text),
        "surveyor_name": parse_surveyor_name(text),
        "plan_date": parse_plan_date(text),
        "scale_text": f"1:{scale_ratio:.0f}" if scale_ratio else None,
        "area_sqm": parse_area_sqm(text),
    }


def has_any(document_info: Optional[dict]) -> bool:
    return bool(document_info) and any(document_info.get(k) for k in
        ("survey_number", "surveyor_name", "plan_date", "scale_text", "area_sqm"))
