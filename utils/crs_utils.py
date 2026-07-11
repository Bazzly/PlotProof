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

import re
from typing import Dict, List, Optional, Tuple

from pyproj import Transformer

# Minna belts cover onshore Nigeria end-to-end (west of 6°30'E, between
# 6°30'E-10°30'E, east of 10°30'E). Minna UTM zones 31N/32N are the same
# UTM zone framework as the WGS84 ones below, but on the older Minna datum
# - some plans/GPS setups use this instead of either the belt system or
# WGS84 (their EPSG registry "area of use" says offshore, but the zone's
# projection math is the same across its whole longitude band, so it's a
# real candidate for onshore western/mid Nigeria too - confirmed against
# a real plan that was wrongly converted as WGS84 UTM 31N, ~150m off).
NIGERIA_CRS_CANDIDATES: Dict[str, str] = {
    "EPSG:26391": "Minna / Nigeria West Belt",
    "EPSG:26392": "Minna / Nigeria Mid Belt",
    "EPSG:26393": "Minna / Nigeria East Belt",
    "EPSG:26331": "Minna / UTM zone 31N",
    "EPSG:26332": "Minna / UTM zone 32N",
    "EPSG:32631": "WGS 84 / UTM zone 31N",
    "EPSG:32632": "WGS 84 / UTM zone 32N",
    "EPSG:32633": "WGS 84 / UTM zone 33N",
}

NIGERIA_BOUNDS = {"min_lat": 4.0, "max_lat": 14.0, "min_lon": 2.5, "max_lon": 14.8}

# Decimal-degree coordinates never exceed a few hundred; projected
# Easting/Northing in these systems run from the tens of thousands to
# low millions of meters. Anything past this threshold is projected.
PROJECTED_VALUE_THRESHOLD = 1000


# Nigerian survey plans commonly state their own CRS right on the drawing
# (e.g. "ORIGIN:- U.T.M (ZONE 31)" or "MINNA WEST BELT"). Trusting that
# beats trial-and-error every time it's present - but "ZONE N" alone
# doesn't say which datum, and guessing wrong is a ~150m error (confirmed
# against a real plan), so a datum keyword is required for certainty.
_UTM_ZONE_RE = re.compile(r"U\.?\s*T\.?\s*M\.?\s*\(?\s*ZONE\s*(\d{1,2})\)?", re.IGNORECASE)
_BELT_RE = re.compile(r"(WEST|MID(?:DLE)?|EAST)\s*BELT", re.IGNORECASE)
_WGS84_RE = re.compile(r"WGS\s*-?\s*84", re.IGNORECASE)
_MINNA_RE = re.compile(r"MINNA", re.IGNORECASE)
_ZONE_TO_WGS84_EPSG = {31: "EPSG:32631", 32: "EPSG:32632", 33: "EPSG:32633"}
_ZONE_TO_MINNA_EPSG = {31: "EPSG:26331", 32: "EPSG:26332"}
_BELT_TO_EPSG = {"WEST": "EPSG:26391", "MID": "EPSG:26392", "MIDDLE": "EPSG:26392", "EAST": "EPSG:26393"}


def detect_declared_crs(text: str) -> Optional[Tuple[str, str, bool]]:
    """
    Looks for an explicit CRS declaration on the document itself.
    Returns (epsg, name, certain) - certain=False means the zone was
    stated but the datum (WGS84 vs Minna) had to be assumed, so this
    should be shown to the user as a guess, not a fact.
    """
    zone_match = _UTM_ZONE_RE.search(text)
    if zone_match:
        zone = int(zone_match.group(1))
        if _MINNA_RE.search(text) and zone in _ZONE_TO_MINNA_EPSG:
            epsg = _ZONE_TO_MINNA_EPSG[zone]
            return epsg, NIGERIA_CRS_CANDIDATES[epsg], True
        epsg = _ZONE_TO_WGS84_EPSG.get(zone)
        if epsg:
            certain = bool(_WGS84_RE.search(text))
            return epsg, NIGERIA_CRS_CANDIDATES[epsg], certain

    belt_match = _BELT_RE.search(text)
    if belt_match:
        epsg = _BELT_TO_EPSG.get(belt_match.group(1).upper())
        if epsg:
            return epsg, NIGERIA_CRS_CANDIDATES[epsg], True

    return None


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


def resolve_to_wgs84(
    pairs_en: List[Tuple[float, float]],
    declared: Optional[Tuple[str, str, bool]] = None,
    forced_epsg: Optional[str] = None,
) -> Tuple[List[Tuple[float, float]], Optional[str]]:
    """
    pairs_en: (easting, northing) pairs already in the correct axis order.
    declared: (epsg, name, certain) from detect_declared_crs() - certain=False
      means the zone was stated but the datum (WGS84 vs Minna) was assumed,
      not confirmed, since guessing wrong is a ~150m error.
    forced_epsg: a user-selected override (see the UI's manual CRS picker),
      which always wins - nothing beats someone who actually knows their
      plan's CRS telling us directly.
    Returns (points in WGS84 lat/lon, a note describing what happened):
      - note is "EPSG:xxxx (Name) - selected" if forced_epsg was used.
      - note is "EPSG:xxxx (Name) - declared on document" if certain.
      - note is "EPSG:xxxx (Name) - assumed; zone declared but datum not
        stated, confirm below if this looks off" if uncertain.
      - note is "EPSG:xxxx (Name)" if auto-detected by trial.
      - note is "undetected" if nothing matched a known Nigerian CRS
        (dropped rather than guessed at).
    """
    if not pairs_en:
        return [], None

    if forced_epsg:
        name = NIGERIA_CRS_CANDIDATES.get(forced_epsg, forced_epsg)
        return convert_pairs(pairs_en, forced_epsg), f"{forced_epsg} ({name}) - selected"

    if declared:
        epsg, name, certain = declared
        suffix = "declared on document" if certain else "assumed; zone declared but datum not stated, confirm below if this looks off"
        return convert_pairs(pairs_en, epsg), f"{epsg} ({name}) - {suffix}"

    match = detect_crs(pairs_en)
    if match is None:
        return [], "undetected"

    epsg, name = match
    return convert_pairs(pairs_en, epsg), f"{epsg} ({name})"
