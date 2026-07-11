"""
CRS detection and conversion for survey plans that give beacon coordinates
as projected Easting/Northing (meters) instead of WGS84 decimal degrees.

Nigerian cadastral plans are almost always surveyed in the Minna-datum
Nigeria Belt system (three belts spanning the whole country), with modern
GPS-based surveys increasingly using WGS84 UTM instead. Plans rarely state
which CRS they're in, so we auto-detect it by trial: reproject the beacon
points through each candidate and see which one lands them inside Nigeria.

Callers are responsible for resolving axis order (Easting, Northing) before
calling in here - see coordinates.py, which uses explicit Northing/Easting
labels when present and falls back to a documented default order otherwise.
Guessing order *and* CRS simultaneously is how you get a confident, silent,
wrong answer (both orders can land "in Nigeria" by coincidence).
"""

from typing import Dict, List, Optional, Tuple

from pyproj import Transformer

# Minna belts cover onshore Nigeria end-to-end (west of 6°30'E, between
# 6°30'E-10°30'E, east of 10°30'E). WGS84 UTM zones are included for
# modern GPS-based surveys that skip the legacy belt system.
NIGERIA_CRS_CANDIDATES: Dict[str, str] = {
    "EPSG:26391": "Minna / Nigeria West Belt",
    "EPSG:26392": "Minna / Nigeria Mid Belt",
    "EPSG:26393": "Minna / Nigeria East Belt",
    "EPSG:32631": "WGS 84 / UTM zone 31N",
    "EPSG:32632": "WGS 84 / UTM zone 32N",
    "EPSG:32633": "WGS 84 / UTM zone 33N",
}

NIGERIA_BOUNDS = {"min_lat": 4.0, "max_lat": 14.0, "min_lon": 2.5, "max_lon": 14.8}

# Decimal-degree coordinates never exceed a few hundred; projected
# Easting/Northing in these systems run from the tens of thousands to
# low millions of meters. Anything past this threshold is projected.
PROJECTED_VALUE_THRESHOLD = 1000


def looks_projected(pair: Tuple[float, float]) -> bool:
    a, b = pair
    return abs(a) > PROJECTED_VALUE_THRESHOLD or abs(b) > PROJECTED_VALUE_THRESHOLD


def _in_nigeria(lat: float, lon: float) -> bool:
    b = NIGERIA_BOUNDS
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lon"] <= lon <= b["max_lon"]


def detect_crs(pairs_en: List[Tuple[float, float]]) -> Optional[Tuple[str, str]]:
    """
    pairs_en: (easting, northing) pairs in the correct axis order.
    Returns (epsg, crs_name) for the candidate CRS under which every point
    falls inside Nigeria, or a majority-fit candidate if none fits perfectly.
    """
    if not pairs_en:
        return None

    best = None  # (hits, epsg, name)
    total = len(pairs_en)
    for epsg, name in NIGERIA_CRS_CANDIDATES.items():
        transformer = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True)
        hits = sum(1 for x, y in pairs_en if _in_nigeria(*reversed(transformer.transform(x, y))))
        if hits == total:
            return epsg, name
        if best is None or hits > best[0]:
            best = (hits, epsg, name)

    # Nothing matched every point - accept a majority fit only, so one
    # stray misread digit doesn't block the whole plan.
    if best and best[0] >= max(1, round(total * 0.6)):
        return best[1], best[2]
    return None


def convert_pairs(pairs_en: List[Tuple[float, float]], epsg: str) -> List[Tuple[float, float]]:
    """Converts (easting, northing) pairs in the given CRS to (lat, lon) WGS84."""
    transformer = Transformer.from_crs(epsg, "EPSG:4326", always_xy=True)
    return [tuple(reversed(transformer.transform(x, y))) for x, y in pairs_en]


def resolve_to_wgs84(pairs_en: List[Tuple[float, float]]) -> Tuple[List[Tuple[float, float]], Optional[str]]:
    """
    pairs_en: (easting, northing) pairs already in the correct axis order.
    Returns (points in WGS84 lat/lon, a note describing what happened):
      - note is "EPSG:xxxx (Name)" if a CRS was matched and points converted.
      - note is "undetected" if these projected-looking points couldn't be
        matched to a known Nigerian CRS (dropped rather than guessed at).
    """
    if not pairs_en:
        return [], None

    match = detect_crs(pairs_en)
    if match is None:
        return [], "undetected"

    epsg, name = match
    return convert_pairs(pairs_en, epsg), f"{epsg} ({name})"
