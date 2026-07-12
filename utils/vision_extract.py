"""
Vision-LLM-based coordinate extraction for photographed/scanned survey plan
images, using Claude's vision capability directly instead of Tesseract OCR.

Why this exists: Tesseract's --psm 6 assumes one uniform horizontal text
block. Real phone-photographed Nigerian survey plans mix a horizontal
header, vertically-printed origin coordinates along the margin, and
diagonally-angled bearing labels along each traverse line - a layout
Tesseract reliably mangles. Confirmed against two real user-submitted
photos that produced zero extracted coordinates through the OCR pipeline
in file_handler.py despite being clearly legible to a human (and to
Claude's vision) - see scripts/vision_extract_prototype.py for the
standalone test this module was promoted from.

Only used for image uploads - PDFs already extract well via a real text
layer or page-rasterized OCR, and cost real money per call (roughly
$0.05-0.08/image on Opus 4.8 at 2026 pricing), so this is a deliberate
step up from free local OCR, not a blanket replacement.

Requires ANTHROPIC_API_KEY. Callers must check is_available() first and
fall back to the existing OCR path when it's unset.
"""

import base64
import json
import mimetypes
from pathlib import Path
from typing import List, Optional, Tuple

import anthropic

from utils import app_config, crs_utils, traverse

MODEL = "claude-opus-4-8"

_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "owner_name": {
            "type": ["string", "null"],
            "description": "Name of the plot owner printed on the plan, if visible.",
        },
        "declared_crs_text": {
            "type": ["string", "null"],
            "description": (
                "Verbatim text on the plan describing the coordinate system / "
                "UTM zone / datum, e.g. 'ORIGIN U.T.M ZONE 31' or "
                "'MINNA DATUM ZONE 31N'. Transcribe exactly as printed, "
                "including whether a datum name (Minna / WGS84) is stated."
            ),
        },
        "origin_point": {
            "type": "object",
            "description": "The single labeled origin/reference coordinate on the plan.",
            "properties": {
                "northing": {"type": ["number", "null"]},
                "easting": {"type": ["number", "null"]},
                "label_raw": {
                    "type": ["string", "null"],
                    "description": "The raw text the coordinate was printed as, e.g. '772359.053mN'.",
                },
            },
            "required": ["northing", "easting", "label_raw"],
            "additionalProperties": False,
        },
        "beacons": {
            "type": "array",
            "description": (
                "Each beacon/pillar point around the boundary in order, with the "
                "bearing and distance of the traverse leg FROM this beacon TO the "
                "next one, as printed on the plan."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": ["string", "null"], "description": "Beacon code, e.g. GB8564AHX."},
                    "bearing_to_next": {
                        "type": ["string", "null"],
                        "description": "Bearing to the next beacon as printed, e.g. 'N45°12'E' or '134°30'00\"'.",
                    },
                    "distance_to_next_m": {"type": ["number", "null"]},
                },
                "required": ["code", "bearing_to_next", "distance_to_next_m"],
                "additionalProperties": False,
            },
        },
        "area_sqm": {"type": ["number", "null"], "description": "The printed plot area in square metres."},
        "scale_text": {"type": ["string", "null"], "description": "The printed scale, e.g. '1:500'."},
        "extraction_notes": {
            "type": "string",
            "description": (
                "Anything ambiguous, illegible, or low-confidence - e.g. "
                "'beacon 4 bearing partially obscured, best guess given'. "
                "Empty string if nothing to flag."
            ),
        },
    },
    "required": [
        "owner_name",
        "declared_crs_text",
        "origin_point",
        "beacons",
        "area_sqm",
        "scale_text",
        "extraction_notes",
    ],
    "additionalProperties": False,
}

_PROMPT = """This is a photograph of a Nigerian land survey plan. It may be printed \
or hand-drawn, and the text may run in multiple orientations (horizontal header, \
vertically-printed origin coordinates along a margin, bearing labels angled along \
each boundary line).

Read the plan carefully, including rotated and vertical text, and extract:
- the owner's name
- the declared coordinate system / UTM zone / datum, verbatim
- the origin/reference coordinate (Northing and Easting, in metres)
- every beacon around the boundary, in order, with the bearing and distance \
of the traverse leg from each beacon to the next
- the printed plot area in square metres
- the printed scale

If a value is not visible or you are not confident, use null rather than \
guessing, and note the issue in extraction_notes."""

def is_available() -> bool:
    return bool(app_config.get_anthropic_api_key())


def _call_vision_api(image_path: str) -> dict:
    client = anthropic.Anthropic(api_key=app_config.get_anthropic_api_key())
    media_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    image_b64 = base64.standard_b64encode(Path(image_path).read_bytes()).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": _EXTRACTION_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def _summarize(data: dict) -> str:
    """Human-readable transcript for the training-data record and debug
    display - not meant for further regex parsing (unlike raw OCR text,
    which downstream code re-parses; this module returns structured
    points directly)."""
    origin = data.get("origin_point") or {}
    lines = [
        f"Owner: {data.get('owner_name') or '(not read)'}",
        f"Declared CRS text: {data.get('declared_crs_text') or '(not stated)'}",
        f"Origin: {origin.get('label_raw') or ''} (N={origin.get('northing')}, E={origin.get('easting')})",
        f"Area: {data.get('area_sqm')} sqm, Scale: {data.get('scale_text')}",
    ]
    for b in data.get("beacons") or []:
        lines.append(f"  {b.get('code') or '?'}: bearing {b.get('bearing_to_next')} distance {b.get('distance_to_next_m')}m")
    if data.get("extraction_notes"):
        lines.append(f"Notes: {data['extraction_notes']}")
    return "\n".join(lines)


def extract_points_from_image(
    image_path: str, forced_epsg: Optional[str] = None
) -> Tuple[List[Tuple[float, float]], Optional[str], str, Optional[dict]]:
    """
    Returns (points, crs_note, raw_summary, legs_info) - points/crs_note
    are in the same shape coordinates.parse_coordinate_text() produces, so
    callers can treat this as a drop-in alternative extraction path for
    images. raw_summary is a human-readable transcript, stored for the
    opt-in training-data record and for debugging, not for re-parsing.

    legs_info carries every beacon's bearing/distance as read by the
    model, in the same {"origin_en", "rows": [...]} shape
    coordinates.parse_coordinate_text() produces - even rows the model
    couldn't confidently read (null bearing/distance) are included, so the
    UI (see app_home.py's legs editor) can let the user fill in or correct
    exactly the beacons that need it, not just accept-or-reject the whole
    file. None only when there's no origin point at all to anchor a table to.
    """
    data = _call_vision_api(image_path)
    raw_summary = _summarize(data)

    origin = data.get("origin_point") or {}
    northing, easting = origin.get("northing"), origin.get("easting")
    if northing is None or easting is None:
        return [], None, raw_summary, None

    origin_en = (easting, northing)
    declared = None if forced_epsg else crs_utils.detect_declared_crs(data.get("declared_crs_text") or "")

    rows = []
    legs = []
    legs_complete = True
    for beacon in data.get("beacons") or []:
        bearing_text = beacon.get("bearing_to_next")
        bearing_deg = traverse.parse_bearing_string(bearing_text)
        distance = beacon.get("distance_to_next_m")
        rows.append({"beacon": beacon.get("code") or None, "bearing_text": bearing_text or "", "distance_m": distance})
        if bearing_deg is None or distance is None:
            legs_complete = False
        else:
            legs.append((bearing_deg, distance))

    polygon_en = None
    if legs_complete and len(legs) >= 3:
        polygon_en = traverse.compute_traverse(origin_en, legs)
        if polygon_en and not traverse.area_within_tolerance(traverse.shoelace_area(polygon_en), data.get("area_sqm")):
            polygon_en = None

    points_en = polygon_en if polygon_en and len(polygon_en) >= 3 else [origin_en]
    converted, crs_note = crs_utils.resolve_to_wgs84(points_en, declared=declared, forced_epsg=forced_epsg)
    valid_points = [(lat, lon) for lat, lon in converted if -90 <= lat <= 90 and -180 <= lon <= 180]

    legs_info = {"origin_en": origin_en, "rows": rows} if rows and valid_points else None

    if valid_points:
        note = (
            f"boundary reconstructed from a {len(legs)}-leg traverse (vision extraction)"
            if polygon_en
            else "origin point only (vision extraction; boundary not confidently reconstructed)"
        )
        crs_note = f"{crs_note}; {note}" if crs_note else note

    return valid_points, crs_note, raw_summary, legs_info
