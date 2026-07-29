"""
Free/open geodata for the Investment Analysis feature
(pages/investment_analysis.py) - OpenStreetMap only, no paid provider:

  - geocode_place() - Nominatim, for "search by place name".
  - fetch_nearby_features() - Overpass API, one query per (point, radius)
    returning categorized amenities/roads/landuse/buildings around it.

Both are shared public infrastructure with real usage policies (Nominatim:
max ~1 request/second, a real identifying User-Agent required; Overpass
public instances rate-limit too) - so both are wrapped in st.cache_data,
issue a single request with a timeout (no retry loops), and identify this
app via OSM_USER_AGENT rather than posing as a browser.

Deliberately does NOT fetch satellite imagery, flood/elevation, population,
or road-quality data - none of that is available from OSM, and PlotProof
has no other data source for it (see pages/investment_analysis.py's
docstring for the full scope decision).
"""

import os
from typing import List, Optional, Tuple

import requests
import streamlit as st

OSM_USER_AGENT = os.environ.get(
    "OSM_USER_AGENT", "PlotProof/1.0 (Nigerian land investment analysis; https://plotproof.streamlit.app)"
)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Safety cap independent of whatever the UI offers - a 1km+ radius in a
# dense city can return an enormous building count otherwise.
MAX_RADIUS_M = 2000

# amenity=* values fetched as point features, and the human-readable
# category each rolls up into - reused by utils/investment_analysis.py to
# build the Amenity Score/breakdown without re-deriving this mapping.
AMENITY_TAG_CATEGORY = {
    "school": "Schools",
    "college": "Schools",
    "university": "Schools",
    "hospital": "Hospitals",
    "clinic": "Hospitals",
    "doctors": "Hospitals",
    "police": "Police Stations",
    "marketplace": "Markets",
    "bank": "Banks",
    "atm": "Banks",
    "fuel": "Fuel Stations",
    "place_of_worship": "Religious Centres",
    "restaurant": "Restaurants",
    "fast_food": "Restaurants",
    "cafe": "Restaurants",
    "townhall": "Government Offices",
    "courthouse": "Government Offices",
    "bus_station": "Bus Stops",
}
# shop=*/tourism=*/office=*/highway=* values that also map to a category,
# checked after the amenity=* table above.
OTHER_TAG_CATEGORY = {
    ("shop", "mall"): "Shopping Centres",
    ("shop", "supermarket"): "Markets",
    ("tourism", "hotel"): "Hotels",
    ("tourism", "guest_house"): "Hotels",
    ("office", "government"): "Government Offices",
    ("highway", "bus_stop"): "Bus Stops",
}


class OSMServiceError(Exception):
    """Raised when Nominatim/Overpass can't be reached or returns something
    unparseable - callers should show a clear "try again" message, never a
    silently-empty or fabricated result."""


def geocode_place(query: str) -> Optional[dict]:
    """Best-effort forward geocode via Nominatim, restricted to Nigeria
    (this app's whole audience). Returns None for no match - that's a
    normal, expected outcome, not an error. Raises OSMServiceError only
    when Nominatim itself couldn't be reached at all."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "ng"},
            headers={"User-Agent": OSM_USER_AGENT},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OSMServiceError(f"Couldn't reach the place-search service: {exc}") from exc

    if not results:
        return None
    top = results[0]
    return {"lat": float(top["lat"]), "lon": float(top["lon"]), "display_name": top.get("display_name", query)}


def _point_feature(el: dict, tags: dict) -> dict:
    lat = el.get("lat")
    lon = el.get("lon")
    if lat is None or lon is None:
        center = el.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    return {"lat": lat, "lon": lon, "tags": tags}


def _line_feature(el: dict, tags: dict) -> dict:
    geometry: List[Tuple[float, float]] = [(pt["lat"], pt["lon"]) for pt in el.get("geometry", []) if "lat" in pt]
    return {"geometry": geometry, "tags": tags}


def amenity_category(tags: dict) -> Optional[str]:
    """The human-readable category a feature's tags roll up into, or None
    if it doesn't match any tracked category - shared with
    utils/investment_analysis.py so the fetch and scoring logic can't
    silently drift apart on what counts as which category."""
    amenity = tags.get("amenity")
    if amenity in AMENITY_TAG_CATEGORY:
        return AMENITY_TAG_CATEGORY[amenity]
    for (key, value), category in OTHER_TAG_CATEGORY.items():
        if tags.get(key) == value:
            return category
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_nearby_features(lat: float, lon: float, radius_m: int) -> dict:
    """One Overpass query around (lat, lon), returning real OSM features
    grouped by kind:

      amenities: point features (schools, hospitals, banks, etc. - see
        AMENITY_TAG_CATEGORY/OTHER_TAG_CATEGORY) with lat/lon + tags.
      roads: highway=* ways with full line geometry + tags (class, name).
      landuse: landuse=* ways with full polygon geometry + tags.
      buildings: building=* ways, center point only (capped at 2000) -
        footprint outlines aren't needed, just density/location for the
        development-density stats and the map's heatmap layer.

    Raises OSMServiceError on network/parse failure - callers should show
    a clear "couldn't fetch map data, try again" message, never proceed
    with an empty/fabricated result."""
    radius_m = max(50, min(int(radius_m), MAX_RADIUS_M))
    amenity_values = "|".join(AMENITY_TAG_CATEGORY)
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"~"^({amenity_values})$"](around:{radius_m},{lat},{lon});
      node["shop"="mall"](around:{radius_m},{lat},{lon});
      node["shop"="supermarket"](around:{radius_m},{lat},{lon});
      node["tourism"~"^(hotel|guest_house)$"](around:{radius_m},{lat},{lon});
      node["office"="government"](around:{radius_m},{lat},{lon});
      node["highway"="bus_stop"](around:{radius_m},{lat},{lon});
    )->.amenities;
    (
      way["highway"](around:{radius_m},{lat},{lon});
    )->.roads;
    (
      way["landuse"](around:{radius_m},{lat},{lon});
    )->.landuse;
    (
      way["building"](around:{radius_m},{lat},{lon});
    )->.buildings;
    .amenities out tags center;
    .roads out tags geom;
    .landuse out tags geom;
    .buildings out tags center 2000;
    """
    try:
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"User-Agent": OSM_USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OSMServiceError(f"Couldn't reach OpenStreetMap's Overpass API: {exc}") from exc

    amenities, roads, landuse, buildings = [], [], [], []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        if not tags:
            continue
        if "landuse" in tags:
            landuse.append(_line_feature(el, tags))
        elif "highway" in tags and el.get("type") == "way":
            roads.append(_line_feature(el, tags))
        elif "building" in tags:
            buildings.append(_point_feature(el, tags))
        else:
            amenities.append(_point_feature(el, tags))

    return {"amenities": amenities, "roads": roads, "landuse": landuse, "buildings": buildings}
