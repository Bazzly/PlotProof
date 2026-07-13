"""
Shared coordinate parsing/validation helpers.
Used by both manual text input and OCR-extracted text, so extraction
logic only lives in one place.
"""

import re
from typing import List, Optional, Tuple

from utils import crs_utils, plan_vectors, traverse

# Lookaround guards on every alternative below prevent matching a partial
# prefix/suffix of a longer, malformed digit run (e.g. OCR mangling
# "750630.892" into "750630892" on a noisy phone photo) - without them,
# `\d{1,7}` greedily matches *some* 7-digit window inside a 9-digit run
# and silently returns a wrong number instead of correctly matching
# nothing. Confirmed against a real garbled-OCR case that produced a
# coordinate that was 60 degrees of latitude off.
_NUM_CORE = (
    r"(?<!\d)-?\d{1,3}(?:,\d{3})*\.\d+(?!\d)"  # decimal degrees or comma-grouped decimals
    r"|(?<!\d)-?\d{1,3}(?:,\d{3})+(?!\d)"  # comma-grouped integers
    r"|(?<!\d)-?\d{1,7}(?:\.\d+)?(?!\d)"  # plain integer/decimal
)

# Matches decimal-degree numbers, comma-grouped projected coordinates
# (e.g. "669,803.42"), and bare projected Easting/Northing values (e.g.
# "669803.42" or "669803"). Beacon/point labels ("B1", "Point 2") and
# small figures (areas, plot numbers) are short integers with no comma
# grouping or decimal point, so this naturally skips them.
_NUM_RE = re.compile(
    r"(?<!\d)-?\d{1,3}(?:,\d{3})*\.\d+(?!\d)"
    r"|(?<!\d)-?\d{1,3}(?:,\d{3})+(?!\d)"
    r"|(?<!\d)-?\d{5,7}(?:\.\d+)?(?!\d)"
)

# Explicit Northing/Easting labels (as used on Nigerian survey plan beacon
# tables) let us resolve axis order with certainty instead of guessing.
# Label must come *before* the number ("N: 279146.54") so this doesn't
# collide with hemisphere-suffix degree notation ("6.5244N").
_NORTHING_LABEL_RE = re.compile(r"\b(?:Northing|N)\s*[:=]?\s*(" + _NUM_CORE + r")", re.IGNORECASE)
_EASTING_LABEL_RE = re.compile(r"\b(?:Easting|E)\s*[:=]?\s*(" + _NUM_CORE + r")", re.IGNORECASE)

# The other common Nigerian convention prints the grid origin as
# "750615.672mN" / "515263.182mE" - number first, then a meters+direction
# suffix, usually on their own line. "m" lowercase, N/E uppercase, as
# printed by the surveying software that generates these plans.
_SUFFIX_NORTHING_RE = re.compile(r"(" + _NUM_CORE + r")\s*mN\b")
_SUFFIX_EASTING_RE = re.compile(r"(" + _NUM_CORE + r")\s*mE\b")

# Loose bounding box covering West/Central Africa, used only to flag
# coordinates that are clearly off (wrong hemisphere, swapped lat/lon).
WEST_AFRICA_BOUNDS = {"min_lat": 3.0, "max_lat": 15.0, "min_lon": -10.0, "max_lon": 16.0}


def is_valid_latlon(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def is_within_expected_region(lat: float, lon: float) -> bool:
    b = WEST_AFRICA_BOUNDS
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lon"] <= lon <= b["max_lon"]


def _parse_pairs(text: str) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """
    Splits lines into (easting, northing) pairs with a known axis order and
    "ambiguous" pairs read left-to-right with unknown order.

    A line with explicit Northing/Easting labels resolves order with
    certainty. An unlabeled line ("6.5244, 3.3792" or two bare projected
    numbers) is read in the order it appears; for unlabeled *projected*
    pairs we default to the Northing-first convention this app uses
    everywhere else for geographic pairs (lat/Y before lon/X) - documented
    here since it can't be verified from the text alone.
    """
    known_en: List[Tuple[float, float]] = []
    ambiguous: List[Tuple[float, float]] = []
    suffix_northings: List[float] = []
    suffix_eastings: List[float] = []

    for line in text.splitlines():
        n_match = _NORTHING_LABEL_RE.search(line)
        e_match = _EASTING_LABEL_RE.search(line)
        if n_match and e_match:
            northing = float(n_match.group(1).replace(",", ""))
            easting = float(e_match.group(1).replace(",", ""))
            known_en.append((easting, northing))
            continue

        suf_n = _SUFFIX_NORTHING_RE.search(line)
        if suf_n:
            suffix_northings.append(float(suf_n.group(1).replace(",", "")))
            continue
        suf_e = _SUFFIX_EASTING_RE.search(line)
        if suf_e:
            suffix_eastings.append(float(suf_e.group(1).replace(",", "")))
            continue

        nums = [float(n.replace(",", "")) for n in _NUM_RE.findall(line)]
        for i in range(0, len(nums) - 1, 2):
            ambiguous.append((nums[i], nums[i + 1]))

    # Suffix-labeled values appear on separate lines (northing line, then
    # easting line) but always in matching pairs, in order.
    for northing, easting in zip(suffix_northings, suffix_eastings):
        known_en.append((easting, northing))

    return known_en, ambiguous


def _legs_info(
    origin_en: Tuple[float, float], origin_latlon: Tuple[float, float], legs: List[Tuple[float, float]]
) -> dict:
    """Bundles a traverse's raw legs into the shape app_home.py's editable
    bearing/distance table expects (see also vision_extract.py, which
    builds the same shape from vision-read beacon data). No beacon codes
    are available from plain text extraction, so points get the "PL1",
    "PL2", ... convention old plans without printed beacon numbers use;
    each row is labeled as the *line* between two points ("PL1 -> PL2"),
    wrapping back to PL1 on the closing leg, since that's what a bearing
    and distance actually describe. origin_en/origin_latlon are surfaced
    separately - always vertex 0 of the resulting boundary and what every
    other point is calculated from, so the UI can show it distinctly
    above the leg table rather than leaving it as just the first,
    unlabeled line of the coordinates box."""
    n = len(legs)
    easting, northing = origin_en
    return {
        "origin_en": origin_en,
        "origin_label": f"{easting:.3f}mE / {northing:.3f}mN",
        "origin_latlon": origin_latlon,
        "rows": [
            {
                "beacon": f"PL{i + 1} → PL{(i + 1) % n + 1}",
                "bearing_text": traverse.format_bearing(bearing),
                "distance_m": distance,
            }
            for i, (bearing, distance) in enumerate(legs)
        ],
    }


def parse_coordinate_text(
    text: str, pdf_path: Optional[str] = None, forced_epsg: Optional[str] = None
) -> Tuple[List[Tuple[float, float]], Optional[str], Optional[dict]]:
    """
    Extract (lat, lon) pairs from free-form text, one or more per line.
    Handles both WGS84 decimal-degree pairs ("6.5244, 3.3792") and
    projected Easting/Northing pairs from Nigerian survey plans - the
    latter are auto-matched to a CRS and converted to WGS84.

    pdf_path: the source PDF, if any - enables vector-graphics-based
    boundary reconstruction (see plan_vectors.py) for plans that label
    multiple beacons individually, in addition to the pure text-based
    bearing/distance traverse (see traverse.py) tried either way.

    forced_epsg: a user-selected CRS override (see the UI's manual picker) -
    takes priority over both declared and auto-detected CRS, since "zone
    declared but datum unstated" can't always be resolved from the text
    alone and someone who knows their plan's real CRS should be able to
    just say so.

    Returns (points, crs_note, legs_info):
      - crs_note is None if input was already WGS84 degrees.
      - crs_note is "EPSG:xxxx (Name)" if a projected CRS was detected and converted.
      - crs_note is "undetected" if projected-looking numbers couldn't be matched
        to a known CRS (those pairs are dropped rather than guessed at).
      - legs_info is the raw bearing/distance traverse (see _legs_info()
        above) when text-based reconstruction was attempted, else None -
        text extraction can misread a digit the same way OCR/vision can,
        so the caller (app_home.py) surfaces this for the user to review
        and correct rather than trusting it silently. Never set for the
        vector-drawing method (plan_vectors.py), which reads beacon
        positions directly and has no bearing/distance to show.
    """
    known_en, ambiguous = _parse_pairs(text)

    geographic = [p for p in ambiguous if not crs_utils.looks_projected(p)]
    unlabeled_projected = [p for p in ambiguous if crs_utils.looks_projected(p)]
    # Default axis order for unlabeled projected pairs: (northing, easting) as read.
    unlabeled_en = [(easting, northing) for northing, easting in unlabeled_projected]

    projected_en = known_en + unlabeled_en
    if not projected_en:
        return [p for p in geographic if is_valid_latlon(*p)], None, None

    declared = None if forced_epsg else crs_utils.detect_declared_crs(text)

    # A single origin point plus a description of the rest of the boundary
    # is how these plans describe a plot's actual shape - reconstruct the
    # full polygon instead of falling back to a generic buffered-point
    # estimate. Try the higher-confidence vector-graphics method first
    # (plans that label each beacon individually), then the text-based
    # bearing/distance traverse (plans that only label the origin).
    if len(projected_en) == 1 and not geographic:
        origin_en = projected_en[0]
        polygon_en = None
        method = None
        legs = None

        if pdf_path:
            scale_ratio = traverse.parse_scale_ratio(text)
            if scale_ratio:
                polygon_en = plan_vectors.build_polygon_from_pdf(pdf_path, origin_en, scale_ratio, text)
                method = "beacon markers in the drawing"

        if not polygon_en:
            legs = traverse.build_legs_from_text(text)
            if legs:
                polygon_en = traverse.compute_traverse(origin_en, legs)
                if polygon_en and not traverse.area_within_tolerance(
                    traverse.shoelace_area(polygon_en), traverse.parse_area_sqm(text)
                ):
                    polygon_en = None
                method = f"a {len(legs)}-leg traverse"

        if polygon_en and len(polygon_en) >= 3:
            # A wrong starting beacon or traverse direction doesn't corrupt
            # any individual bearing/distance value, so nothing above would
            # catch it - check separately against the standard north-start,
            # clockwise convention before this goes into a note the user sees.
            convention_issue = traverse.check_traverse_convention(polygon_en)
            converted, crs_note = crs_utils.resolve_to_wgs84(polygon_en, declared=declared, forced_epsg=forced_epsg)
            valid_points = [p for p in converted if is_valid_latlon(*p)]
            if len(valid_points) >= 3:
                note = f"boundary reconstructed from {method}"
                if convention_issue:
                    note += (
                        f"; this traverse {convention_issue} - the standard convention starts at "
                        "the northernmost beacon and goes clockwise, so double-check the beacon "
                        "order and starting point below against your original document"
                    )
                crs_note = f"{crs_note}; {note}" if crs_note else note
                return valid_points, crs_note, (_legs_info(origin_en, valid_points[0], legs) if legs else None)

        # Strict reconstruction failed (didn't close, or area mismatch) -
        # for old or hand-surveyed plans this is common even when every
        # bearing and distance was read correctly, since decades-old
        # measurements drift. Deduce the boundary anyway from the raw legs
        # rather than collapsing to a single point - openly flagged as
        # approximate, so there's a real shape to check against the
        # original document instead of nothing at all.
        if legs and len(legs) >= 3:
            open_polygon_en, closure_error = traverse.build_open_polygon(origin_en, legs)
            if open_polygon_en:
                convention_issue = traverse.check_traverse_convention(open_polygon_en)
                converted, crs_note = crs_utils.resolve_to_wgs84(open_polygon_en, declared=declared, forced_epsg=forced_epsg)
                valid_points = [p for p in converted if is_valid_latlon(*p)]
                if len(valid_points) >= 3:
                    note = (
                        f"approximate boundary from a {len(legs)}-leg traverse - doesn't fully close "
                        f"(~{closure_error:.1f}m gap), review the bearings/distances below"
                    )
                    if convention_issue:
                        note += (
                            f"; also, this traverse {convention_issue} - the standard convention "
                            "starts at the northernmost beacon and goes clockwise, so double-check "
                            "the beacon order and starting point too"
                        )
                    crs_note = f"{crs_note}; {note}" if crs_note else note
                    return valid_points, crs_note, _legs_info(origin_en, valid_points[0], legs)

        # Not even an open shape was possible (fewer than 3 legs). Still
        # expose any raw legs we did parse so the UI can offer a chance to
        # fix a misread bearing/distance, rather than silently dropping to
        # a single-point estimate with no way to recover the real shape.
        if legs:
            converted, crs_note = crs_utils.resolve_to_wgs84([origin_en], declared=declared, forced_epsg=forced_epsg)
            valid_points = [p for p in converted if is_valid_latlon(*p)]
            return valid_points, crs_note, (_legs_info(origin_en, valid_points[0], legs) if valid_points else None)

    converted, crs_note = crs_utils.resolve_to_wgs84(projected_en, declared=declared, forced_epsg=forced_epsg)
    points = geographic + converted
    valid_points = [(lat, lon) for lat, lon in points if is_valid_latlon(lat, lon)]
    return valid_points, crs_note, None
