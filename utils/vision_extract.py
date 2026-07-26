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
        "survey_number": {
            "type": ["string", "null"],
            "description": "The survey/plan/file number printed on the plan, e.g. 'OG/12345/2020'.",
        },
        "surveyor_name": {
            "type": ["string", "null"],
            "description": "Name of the licensed surveyor who prepared/signed the plan, if visible.",
        },
        "plan_date": {
            "type": ["string", "null"],
            "description": "The date the plan was made/signed, as printed (any format).",
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
                        "description": (
                            "Bearing to the next beacon as printed, e.g. 'N45°12'E' or '134°30'00\"'. "
                            "Give your best-effort reading even if faint, angled, or handwritten - "
                            "only use null if truly nothing is legible at that spot. A low-confidence "
                            "guess is far more useful here than null: the app shows this value to the "
                            "user in an editable table for them to correct, so a guess they can fix "
                            "beats a blank they can't."
                        ),
                    },
                    "distance_to_next_m": {
                        "type": ["number", "null"],
                        "description": (
                            "Distance in metres to the next beacon. Same guidance as bearing_to_next: "
                            "give your best-effort reading rather than null whenever any digits are "
                            "legible, and use extraction_notes for anything genuinely uncertain."
                        ),
                    },
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
        "survey_number",
        "surveyor_name",
        "plan_date",
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
- the survey/plan/file number
- the licensed surveyor's name, if signed/printed
- the date the plan was made or signed
- the declared coordinate system / UTM zone / datum, verbatim
- the origin/reference coordinate (Northing and Easting, in metres)
- every beacon around the boundary, in order, with the bearing and distance \
of the traverse leg from each beacon to the next
- the printed plot area in square metres
- the printed scale

The beacon order matters as much as the individual values: list beacons in \
the exact sequence printed on the plan (this is what the bearings and \
distances are relative to), not reordered or grouped by your own judgement. \
Nigerian cadastral plans conventionally start the traverse at the \
northernmost beacon and proceed clockwise - if the plan's printed order \
looks like it does something else (starts elsewhere, runs counter-clockwise), \
transcribe it exactly as printed anyway and flag this in extraction_notes \
rather than silently reordering it to match the convention. Also note in \
extraction_notes if the labeled origin coordinate is a separate reference \
point rather than the same physical location as the first beacon.

For owner name, survey number, surveyor name, plan date, declared CRS text, \
area, and scale: if a value is genuinely not visible, use null rather than \
guessing.

For each beacon's bearing and distance specifically, this does NOT apply - \
always give your best-effort numeric reading, even from faint, angled, or \
handwritten figures, rather than null. These values are shown to the user \
afterward in an editable table for review and correction, so a low-confidence \
guess they can fix is far more useful than a blank they can't. Only use null \
for a bearing or distance if literally nothing is legible at that spot on the \
page. Note anything you're unsure about in extraction_notes either way."""

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
        f"Survey number: {data.get('survey_number') or '(not read)'}",
        f"Surveyor: {data.get('surveyor_name') or '(not read)'}",
        f"Plan date: {data.get('plan_date') or '(not read)'}",
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
) -> Tuple[List[Tuple[float, float]], Optional[str], str, Optional[dict], dict]:
    """
    Returns (points, crs_note, raw_summary, legs_info, document_info) -
    points/crs_note are in the same shape coordinates.parse_coordinate_text()
    produces, so callers can treat this as a drop-in alternative extraction
    path for images. raw_summary is a human-readable transcript, stored for
    the opt-in training-data record and for debugging, not for re-parsing.

    legs_info carries every beacon's bearing/distance as read by the
    model, in the same {"origin_en", "rows": [...]} shape
    coordinates.parse_coordinate_text() produces - even rows the model
    couldn't confidently read (null bearing/distance) are included, so the
    UI (see app_home.py's legs editor) can let the user fill in or correct
    exactly the beacons that need it, not just accept-or-reject the whole
    file. None only when there's no origin point at all to anchor a table to.

    document_info carries the plan's own metadata (survey_number,
    surveyor_name, plan_date, scale_text, area_sqm) in the same shape
    utils/document_metadata.py's text-based extractor produces, so
    app_home.py can display either extraction path's result through one
    code path. Always returned (never None) - individual fields are None
    when not visible on the plan.
    """
    data = _call_vision_api(image_path)
    raw_summary = _summarize(data)
    document_info = {
        "survey_number": data.get("survey_number"),
        "surveyor_name": data.get("surveyor_name"),
        "plan_date": data.get("plan_date"),
        "scale_text": data.get("scale_text"),
        "area_sqm": data.get("area_sqm"),
    }

    origin = data.get("origin_point") or {}
    northing, easting = origin.get("northing"), origin.get("easting")
    if northing is None or easting is None:
        return [], None, raw_summary, None, document_info

    origin_en = (easting, northing)
    declared = None if forced_epsg else crs_utils.detect_declared_crs(data.get("declared_crs_text") or "")

    beacons = data.get("beacons") or []
    # "PL1", "PL2", ... for any beacon with no printed/legible code - common
    # on old plans, which often predate the beacon-numbering convention
    # newer plans use. Collected up front (not inline in the loop below) so
    # each row's line label can reference the *next* beacon's code too.
    codes = [b.get("code") or f"PL{i + 1}" for i, b in enumerate(beacons)]

    rows = []
    legs = []
    legs_complete = True
    for i, beacon in enumerate(beacons):
        bearing_text = beacon.get("bearing_to_next")
        bearing_deg = traverse.parse_bearing_string(bearing_text)
        distance = beacon.get("distance_to_next_m")
        # Each row's bearing/distance describes the LINE from this beacon to
        # the next one (wrapping back to the first beacon on the closing
        # leg), not a single point - label it as such.
        next_code = codes[(i + 1) % len(codes)]
        rows.append(
            {"beacon": f"{codes[i]} → {next_code}", "bearing_text": bearing_text or "", "distance_m": distance}
        )
        if bearing_deg is None or distance is None:
            legs_complete = False
        else:
            legs.append((bearing_deg, distance))

    polygon_en = None
    if legs_complete and len(legs) >= 3:
        polygon_en = traverse.compute_traverse(origin_en, legs)
        if polygon_en and not traverse.area_within_tolerance(traverse.shoelace_area(polygon_en), data.get("area_sqm")):
            polygon_en = None

    # Strict reconstruction failed (didn't close, or area mismatch) - for
    # old or hand-surveyed plans this is common even with correctly-read
    # values, since decades-old measurements drift. Deduce the boundary
    # anyway rather than collapsing to a single point, openly flagged as
    # approximate so there's a real shape to check against the original
    # document instead of nothing at all.
    closure_error = None
    if not polygon_en and legs_complete and len(legs) >= 3:
        polygon_en, closure_error = traverse.build_open_polygon(origin_en, legs)

    points_en = polygon_en if polygon_en and len(polygon_en) >= 3 else [origin_en]
    # A wrong starting beacon or traverse direction doesn't corrupt any
    # individual bearing/distance value, so nothing above would catch it -
    # check separately against the standard north-start, clockwise
    # convention (see traverse.check_traverse_convention()) before this
    # goes into a note the user sees.
    convention_issue = traverse.check_traverse_convention(points_en)

    # A diagonal reference - bearing/distance in a straight line from the
    # origin to the farthest other point - computed purely from the
    # coordinates just reconstructed above, not read off the plan (real
    # Nigerian survey plans don't print one - confirmed against real
    # sample plans, so nothing here depends on the model finding one).
    diagonal_result = traverse.compute_diagonal(points_en, labels=codes) if len(points_en) >= 3 else None

    # The diagonal's own target point is appended to the same conversion
    # call (not run through resolve_to_wgs84() separately) so it goes
    # through the exact same declared/forced/auto-detected CRS as the rest
    # of the boundary, then split back off - one converted point per input
    # point, same order, so converted[-1] is always the diagonal's.
    points_to_convert = points_en + ([diagonal_result["point_en"]] if diagonal_result else [])
    converted, crs_note = crs_utils.resolve_to_wgs84(points_to_convert, declared=declared, forced_epsg=forced_epsg)
    if diagonal_result:
        diag_lat, diag_lon = converted[-1]
        if -90 <= diag_lat <= 90 and -180 <= diag_lon <= 180:
            diagonal_result["point_latlon"] = (diag_lat, diag_lon)
        converted = converted[:-1]
    valid_points = [(lat, lon) for lat, lon in converted if -90 <= lat <= 90 and -180 <= lon <= 180]

    # The origin (always vertex 0 - see traverse.walk_traverse()) is what
    # every other point in valid_points is calculated FROM, so the UI
    # surfaces it distinctly above the leg table rather than leaving it as
    # just the first, unlabeled line of the coordinates box. Built from the
    # verified numeric easting/northing fields, NOT origin["label_raw"] -
    # label_raw is the model's own free-text transcription of the printed
    # label and can contain its own misreads (confirmed: a real plan's
    # "517440.880" got transcribed as "S17 440.880", a visual 5/S mix-up)
    # independent of the structured numeric fields, which is all this
    # calculation actually uses - showing the transcription here would
    # describe the origin differently than what was actually computed.
    legs_info = (
        {
            "origin_en": origin_en,
            "origin_label": f"{easting:.3f}mE / {northing:.3f}mN",
            "origin_latlon": valid_points[0],
            "rows": rows,
            "diagonal": diagonal_result,
        }
        if rows and valid_points
        else None
    )

    if valid_points:
        if closure_error is not None:
            note = (
                f"approximate boundary from a {len(legs)}-leg traverse (vision extraction) - doesn't "
                f"fully close (~{closure_error:.1f}m gap), review the bearings/distances below"
            )
        elif polygon_en and len(polygon_en) >= 3:
            note = f"boundary reconstructed from a {len(legs)}-leg traverse (vision extraction)"
        else:
            note = "origin point only (vision extraction; boundary not confidently reconstructed)"
        if convention_issue:
            note += (
                f"; this traverse {convention_issue} - the standard convention starts at the "
                "northernmost beacon and goes clockwise, so double-check the beacon order and "
                "starting point below against your original document"
            )
        crs_note = f"{crs_note}; {note}" if crs_note else note

    return valid_points, crs_note, raw_summary, legs_info, document_info
