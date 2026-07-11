"""
Shared coordinate parsing/validation helpers.
Used by both manual text input and OCR-extracted text, so extraction
logic only lives in one place.
"""

import re
from typing import List, Optional, Tuple

from utils import crs_utils

_NUM_CORE = (
    r"-?\d{1,3}(?:,\d{3})*\.\d+"  # decimal degrees or comma-grouped decimals
    r"|-?\d{1,3}(?:,\d{3})+"  # comma-grouped integers
    r"|-?\d{1,7}(?:\.\d+)?"  # plain integer/decimal
)

# Matches decimal-degree numbers, comma-grouped projected coordinates
# (e.g. "669,803.42"), and bare projected Easting/Northing values (e.g.
# "669803.42" or "669803"). Beacon/point labels ("B1", "Point 2") and
# small figures (areas, plot numbers) are short integers with no comma
# grouping or decimal point, so this naturally skips them.
_NUM_RE = re.compile(r"-?\d{1,3}(?:,\d{3})*\.\d+|-?\d{1,3}(?:,\d{3})+|-?\d{5,7}(?:\.\d+)?")

# Explicit Northing/Easting labels (as used on Nigerian survey plan beacon
# tables) let us resolve axis order with certainty instead of guessing.
# Label must come *before* the number ("N: 279146.54") so this doesn't
# collide with hemisphere-suffix degree notation ("6.5244N").
_NORTHING_LABEL_RE = re.compile(r"\b(?:Northing|N)\s*[:=]?\s*(" + _NUM_CORE + r")", re.IGNORECASE)
_EASTING_LABEL_RE = re.compile(r"\b(?:Easting|E)\s*[:=]?\s*(" + _NUM_CORE + r")", re.IGNORECASE)

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

    for line in text.splitlines():
        n_match = _NORTHING_LABEL_RE.search(line)
        e_match = _EASTING_LABEL_RE.search(line)
        if n_match and e_match:
            northing = float(n_match.group(1).replace(",", ""))
            easting = float(e_match.group(1).replace(",", ""))
            known_en.append((easting, northing))
            continue

        nums = [float(n.replace(",", "")) for n in _NUM_RE.findall(line)]
        for i in range(0, len(nums) - 1, 2):
            ambiguous.append((nums[i], nums[i + 1]))

    return known_en, ambiguous


def parse_coordinate_text(text: str) -> Tuple[List[Tuple[float, float]], Optional[str]]:
    """
    Extract (lat, lon) pairs from free-form text, one or more per line.
    Handles both WGS84 decimal-degree pairs ("6.5244, 3.3792") and
    projected Easting/Northing pairs from Nigerian survey plans - the
    latter are auto-matched to a CRS and converted to WGS84.

    Returns (points, crs_note):
      - crs_note is None if input was already WGS84 degrees.
      - crs_note is "EPSG:xxxx (Name)" if a projected CRS was detected and converted.
      - crs_note is "undetected" if projected-looking numbers couldn't be matched
        to a known CRS (those pairs are dropped rather than guessed at).
    """
    known_en, ambiguous = _parse_pairs(text)

    geographic = [p for p in ambiguous if not crs_utils.looks_projected(p)]
    unlabeled_projected = [p for p in ambiguous if crs_utils.looks_projected(p)]
    # Default axis order for unlabeled projected pairs: (northing, easting) as read.
    unlabeled_en = [(easting, northing) for northing, easting in unlabeled_projected]

    projected_en = known_en + unlabeled_en
    crs_note: Optional[str] = None
    converted: List[Tuple[float, float]] = []
    if projected_en:
        converted, crs_note = crs_utils.resolve_to_wgs84(projected_en)

    points = geographic + converted
    valid_points = [(lat, lon) for lat, lon in points if is_valid_latlon(lat, lon)]
    return valid_points, crs_note
