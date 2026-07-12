"""
COGO (coordinate geometry) traverse calculator.

Nigerian survey plans describe a plot's boundary as one known reference
coordinate (see coordinates.py's mN/mE suffix and N:/E: prefix parsing)
plus a sequence of whole-circle bearing/distance legs walking around the
boundary back to the start - not a table of absolute corner coordinates.
This reconstructs the full polygon from that description, so a single
extracted origin point can drive a real boundary overlay instead of a
generic buffered-point estimate.

Bearing/distance labels land in the extracted text in whatever order the
source PDF's content stream happens to store them (not necessarily
reading order - confirmed against real plans), but each value's position
*within its own kind* (the Nth bearing found, the Nth distance found)
reliably corresponds to the Nth leg of the traverse. So legs are built by
zipping the two sequences by index, not by textual adjacency.
"""

import math
import re
from typing import List, Optional, Tuple

# "32° 19'" or "32° 19' 30"" - degrees/minutes, optional seconds.
_BEARING_RE = re.compile(r"(\d{1,3})\s*°\s*(\d{1,2})\s*'(?:\s*(\d{1,2})\s*\")?")

# "18.01m" - a decimal is required so this doesn't match the plan's
# graphical scale bar ("...20  30  40m"), which only has bare integers.
_DISTANCE_RE = re.compile(r"(\d{1,4}\.\d{1,3})\s*m\b")

# Accept a closed traverse if the walk returns within this tolerance of
# where it started - generous enough for rounding/reading noise (real
# plans validated at ~1cm and ~2m closure), tight enough to reject a
# genuinely wrong bearing/distance pairing rather than silently drawing
# a bogus shape.
MAX_CLOSURE_ERROR_M = 2.5
MAX_CLOSURE_FRACTION = 0.03

# "AREA:- 621.072SQ.MTS" / "AREA:- 2,349.630 SQ.MTS"
_AREA_RE = re.compile(r"AREA\s*:?-?\s*([\d,]+\.?\d*)\s*SQ\.?\s*MTS", re.IGNORECASE)

# "SCALE:-1:500"
_SCALE_RE = re.compile(r"SCALE\s*:?-?\s*1\s*:\s*([\d,]+)", re.IGNORECASE)

# A closed traverse can pass the closure check on a badly-mispaired
# bearing/distance set and still draw a real (if wrong) polygon - closure
# alone isn't proof the *shape* is right. The plan's own printed area is
# an independent check: reject anything too far off it.
MAX_AREA_RELATIVE_ERROR = 0.15


def parse_area_sqm(text: str) -> Optional[float]:
    match = _AREA_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_scale_ratio(text: str) -> Optional[float]:
    match = _SCALE_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def shoelace_area(vertices: List[Tuple[float, float]]) -> float:
    n = len(vertices)
    total = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def area_within_tolerance(computed_area: float, printed_area: Optional[float]) -> bool:
    """True if there's nothing to check against, or the computed area is
    close enough to what the plan itself claims."""
    if not printed_area:
        return True
    return abs(computed_area - printed_area) <= MAX_AREA_RELATIVE_ERROR * printed_area


def parse_bearings(text: str) -> List[float]:
    bearings = []
    for deg, minute, sec in _BEARING_RE.findall(text):
        value = int(deg) + int(minute) / 60 + (int(sec) / 3600 if sec else 0)
        if 0 <= value <= 360:
            bearings.append(value)
    return bearings


def parse_distances(text: str) -> List[float]:
    return [float(m) for m in _DISTANCE_RE.findall(text)]


# Looser than _BEARING_RE above (which requires a full "deg° min'" match) -
# also accepts a bare "176°" with no minutes/seconds, since that's a valid
# whole-circle bearing some plans print, and it's what a user editing the
# table by hand (or the vision extraction pipeline transcribing exactly
# what's printed - see vision_extract.py) might reasonably enter.
_BEARING_STR_RE = re.compile(r"(\d{1,3})\s*°\s*(?:(\d{1,2})\s*'\s*)?(?:(\d{1,2})\s*\"?)?")


def parse_bearing_string(raw: Optional[str]) -> Optional[float]:
    """Parses a single bearing given as free text ("52°30'", "52°30'00\"",
    or bare "176°") into whole-circle degrees. Shared by the vision
    extraction pipeline and the user-editable bearing/distance table (see
    app_home.py's legs editor) so both accept the same input grammar."""
    if not raw:
        return None
    match = _BEARING_STR_RE.search(raw)
    if not match:
        return None
    deg, minute, sec = match.groups()
    value = int(deg) + (int(minute) / 60 if minute else 0) + (int(sec) / 3600 if sec else 0)
    return value if 0 <= value <= 360 else None


def format_bearing(deg: float) -> str:
    """Whole-circle degrees back to the plan's own "52°30'" convention -
    used to pre-fill the editable bearing table when only a parsed float is
    available (the text-based extraction path doesn't retain the original
    printed substring, unlike vision extraction which reads it verbatim)."""
    whole = int(deg)
    minutes = round((deg - whole) * 60)
    if minutes == 60:
        whole += 1
        minutes = 0
    return f"{whole}°{minutes:02d}'"


def compute_traverse(
    origin_en: Tuple[float, float],
    legs: List[Tuple[float, float]],
) -> Optional[List[Tuple[float, float]]]:
    """
    origin_en: (easting, northing) starting point.
    legs: (bearing_degrees, distance_m) pairs, in traverse order.
    Returns the (easting, northing) vertices - the closing point is
    dropped, not repeated - if the walk closes within tolerance, else None.
    """
    if not legs:
        return None

    easting, northing = origin_en
    vertices = [(easting, northing)]
    for bearing, distance in legs:
        rad = math.radians(bearing)
        easting += distance * math.sin(rad)
        northing += distance * math.cos(rad)
        vertices.append((easting, northing))

    closure_error = math.hypot(vertices[-1][0] - vertices[0][0], vertices[-1][1] - vertices[0][1])
    perimeter = sum(d for _, d in legs)
    tolerance = max(MAX_CLOSURE_ERROR_M, MAX_CLOSURE_FRACTION * perimeter)
    if closure_error > tolerance:
        return None

    return vertices[:-1]


def build_legs_from_text(text: str) -> Optional[List[Tuple[float, float]]]:
    """Returns (bearing_degrees, distance_m) leg pairs in traverse order, or
    None if the text doesn't contain a matching bearing/distance count.
    Exposed separately from build_polygon_from_text so a caller can show
    the raw legs to a user for review/correction (see app_home.py's legs
    editor) even when they don't - yet - close into a valid polygon."""
    bearings = parse_bearings(text)
    distances = parse_distances(text)
    if not bearings or len(bearings) != len(distances):
        return None
    return list(zip(bearings, distances))


def build_polygon_from_text(
    text: str,
    origin_en: Tuple[float, float],
) -> Optional[List[Tuple[float, float]]]:
    """Returns (easting, northing) polygon vertices, or None if the text
    doesn't contain a matching, closing, area-consistent bearing/distance
    traverse."""
    legs = build_legs_from_text(text)
    if legs is None:
        return None

    polygon = compute_traverse(origin_en, legs)
    if polygon is None:
        return None

    if not area_within_tolerance(shoelace_area(polygon), parse_area_sqm(text)):
        return None

    return polygon


# Good to well under a centimeter of error at plot-boundary scale (tens to
# a few hundred metres) - the flat-earth approximation this app already
# uses in resolve_recomputed_points() below, rather than a full geodesic
# projection, which would mean threading the original EPSG code through
# every layer just to re-run the exact conversion after a one-line edit.
_METERS_PER_DEG_LAT = 111_320.0


def resolve_recomputed_points(
    origin_en: Tuple[float, float],
    origin_latlon: Tuple[float, float],
    legs: List[Tuple[float, float]],
) -> Optional[List[Tuple[float, float]]]:
    """
    Rebuilds a WGS84 polygon after a user edits the bearing/distance table
    (see app_home.py's legs editor). Walks the traverse in projected
    metres as usual via compute_traverse(), then converts each vertex's
    *offset* from the already-known origin_latlon using a flat-earth
    approximation - see _METERS_PER_DEG_LAT above for why this doesn't need
    the original EPSG code at all.

    Returns None if the edited legs don't close within compute_traverse()'s
    tolerance - the caller should keep showing the last valid result rather
    than a confidently wrong shape from a bad edit.
    """
    polygon_en = compute_traverse(origin_en, legs)
    if not polygon_en or len(polygon_en) < 3:
        return None

    origin_easting, origin_northing = origin_en
    lat0, lon0 = origin_latlon
    meters_per_deg_lon = _METERS_PER_DEG_LAT * math.cos(math.radians(lat0))
    if meters_per_deg_lon <= 0:
        return None

    points = []
    for easting, northing in polygon_en:
        d_lat = (northing - origin_northing) / _METERS_PER_DEG_LAT
        d_lon = (easting - origin_easting) / meters_per_deg_lon
        points.append((lat0 + d_lat, lon0 + d_lon))
    return points
