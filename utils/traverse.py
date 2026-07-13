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


def signed_area(vertices: List[Tuple[float, float]]) -> float:
    """Shoelace area WITHOUT taking the absolute value - positive when the
    vertices wind counter-clockwise in standard map orientation (easting
    as x, northing as y - north up, east right), negative when clockwise.
    Same magnitude as shoelace_area()."""
    n = len(vertices)
    total = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2


def shoelace_area(vertices: List[Tuple[float, float]]) -> float:
    return abs(signed_area(vertices))


def area_within_tolerance(computed_area: float, printed_area: Optional[float]) -> bool:
    """True if there's nothing to check against, or the computed area is
    close enough to what the plan itself claims."""
    if not printed_area:
        return True
    return abs(computed_area - printed_area) <= MAX_AREA_RELATIVE_ERROR * printed_area


# Nigerian cadastral plans conventionally start a traverse at the
# northernmost beacon (westernmost as tiebreak) and proceed clockwise.
# Getting the starting beacon or direction wrong doesn't change any
# individual bearing/distance reading, but produces a boundary that's
# rotated to the wrong starting corner or mirrored - a real, silent
# accuracy risk distinct from a misread digit. This is a tolerance, not a
# hard rule: reading noise can make two beacons nearly tie for
# "northernmost," and it only makes sense to check once there's an actual
# polygon (3+ vertices) to evaluate.
_ORIGIN_NORTHING_TOLERANCE_M = 5.0


def check_traverse_convention(vertices: List[Tuple[float, float]]) -> Optional[str]:
    """
    Flags a traverse that doesn't follow the standard north-start,
    clockwise convention. Returns a human-readable description of what's
    off (to fold into a crs_note/warning), or None if it matches
    convention or there are too few vertices to judge.

    This is a review flag, not proof of an error - some real plans
    legitimately start elsewhere, and reading noise can shift which point
    is technically northernmost. It exists so a beacon-order or direction
    mistake (which doesn't corrupt any individual bearing/distance value,
    so nothing else in this pipeline would catch it) gets surfaced to the
    user instead of silently producing a rotated or mirrored shape.
    """
    if len(vertices) < 3:
        return None

    issues = []

    max_northing = max(v[1] for v in vertices)
    origin_northing = vertices[0][1]
    if max_northing - origin_northing > _ORIGIN_NORTHING_TOLERANCE_M:
        issues.append("doesn't start at the northernmost point")

    if signed_area(vertices) > 0:
        issues.append("runs counter-clockwise rather than clockwise")

    return " and ".join(issues) if issues else None


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


def walk_traverse(
    origin_en: Tuple[float, float],
    legs: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    """
    origin_en: (easting, northing) starting point.
    legs: (bearing_degrees, distance_m) pairs, in traverse order.
    Walks every leg unconditionally and returns all len(legs)+1 vertices
    (the origin, each beacon in between, and finally wherever the last leg
    ends up - which should coincide with the origin for an accurate closed
    traverse, but isn't checked or enforced here). See compute_traverse()
    for the gated version that validates and drops that final vertex.
    """
    easting, northing = origin_en
    vertices = [(easting, northing)]
    for bearing, distance in legs:
        rad = math.radians(bearing)
        easting += distance * math.sin(rad)
        northing += distance * math.cos(rad)
        vertices.append((easting, northing))
    return vertices


def compute_traverse(
    origin_en: Tuple[float, float],
    legs: List[Tuple[float, float]],
) -> Optional[List[Tuple[float, float]]]:
    """
    Returns the (easting, northing) vertices - the closing point is
    dropped, not repeated - if the walk closes within tolerance, else None.
    See build_open_polygon() for the graceful-degradation fallback used
    when a real (if imperfect) shape is preferable to discarding it.
    """
    if not legs:
        return None

    vertices = walk_traverse(origin_en, legs)
    closure_error = math.hypot(vertices[-1][0] - vertices[0][0], vertices[-1][1] - vertices[0][1])
    perimeter = sum(d for _, d in legs)
    tolerance = max(MAX_CLOSURE_ERROR_M, MAX_CLOSURE_FRACTION * perimeter)
    if closure_error > tolerance:
        return None

    return vertices[:-1]


def build_open_polygon(
    origin_en: Tuple[float, float],
    legs: List[Tuple[float, float]],
) -> Tuple[List[Tuple[float, float]], float]:
    """
    Walks the full traverse and returns it as a usable shape even when it
    doesn't close within compute_traverse()'s tolerance - dropping only the
    final (possibly non-coincident) closing vertex, same as
    compute_traverse(). Returns (vertices, closure_error_m).

    This is the deliberate fallback for old or hand-surveyed plans: small
    historical measurement drift (decades-old chain-and-compass surveys,
    hand-copied figures, a beacon that's shifted slightly since) is common
    even when every bearing and distance was read correctly, and silently
    collapsing to a single point in that case throws away real information.
    An approximate shape, openly flagged as unclosed by the caller, gives a
    reviewer something concrete to check against the original document -
    exactly what the bearing/distance editor (see app_home.py) is for.
    """
    if len(legs) < 3:
        return [], 0.0
    vertices = walk_traverse(origin_en, legs)
    closure_error = math.hypot(vertices[-1][0] - vertices[0][0], vertices[-1][1] - vertices[0][1])
    return vertices[:-1], closure_error


def build_legs_from_text(text: str) -> Optional[List[Tuple[float, float]]]:
    """Returns (bearing_degrees, distance_m) leg pairs in traverse order, or
    None if the text doesn't contain a matching bearing/distance count.
    Exposed separately so a caller can show the raw legs to a user for
    review/correction (see app_home.py's legs editor) even when they don't
    - yet - close into a valid polygon."""
    bearings = parse_bearings(text)
    distances = parse_distances(text)
    if not bearings or len(bearings) != len(distances):
        return None
    return list(zip(bearings, distances))


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
) -> Tuple[Optional[List[Tuple[float, float]]], bool]:
    """
    Rebuilds a WGS84 polygon after a user edits the bearing/distance table
    (see app_home.py's legs editor). Walks the traverse in projected
    metres as usual via compute_traverse(), then converts each vertex's
    *offset* from the already-known origin_latlon using a flat-earth
    approximation - see _METERS_PER_DEG_LAT above for why this doesn't need
    the original EPSG code at all.

    Returns (points, closed). If the edited legs don't close within
    compute_traverse()'s tolerance, falls back to build_open_polygon()
    instead of discarding the edit outright - old/hand-surveyed plans
    often don't close exactly even when every value was transcribed
    correctly, and an openly-flagged approximate shape (closed=False) is
    more useful to a reviewer than losing their edit. points is None only
    when there are too few legs to form a shape at all.
    """
    polygon_en = compute_traverse(origin_en, legs)
    closed = polygon_en is not None
    if not closed:
        polygon_en, _ = build_open_polygon(origin_en, legs)

    if not polygon_en or len(polygon_en) < 3:
        return None, False

    origin_easting, origin_northing = origin_en
    lat0, lon0 = origin_latlon
    meters_per_deg_lon = _METERS_PER_DEG_LAT * math.cos(math.radians(lat0))
    if meters_per_deg_lon <= 0:
        return None, False

    points = []
    for easting, northing in polygon_en:
        d_lat = (northing - origin_northing) / _METERS_PER_DEG_LAT
        d_lon = (easting - origin_easting) / meters_per_deg_lon
        points.append((lat0 + d_lat, lon0 + d_lon))
    return points, closed
