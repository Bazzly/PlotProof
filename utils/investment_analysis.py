"""
Scoring and AI narrative for the Investment Analysis feature
(pages/investment_analysis.py).

compute_investment_score() is pure, deterministic arithmetic over the real
features utils/osm_service.py fetched - same flat-dict-return convention as
utils/risk_calculator.py's calculate_risk(), no framework/class machinery.
Every subscore is derived from something actually counted/measured (road
count, building density, amenity distance, tagged land-use area) - never
invented - so it stays honest about what it does and doesn't know.

generate_investment_narrative() is the one AI-reasoned part: a single
Claude call, grounded strictly in the scores/stats already computed above,
following the exact same call pattern as utils/assistant.py's ask() (same
MODEL constant, same app_config.get_anthropic_api_key() resolution) and the
same structured-JSON-output pattern as utils/vision_extract.py's
_call_vision_api() (output_config json_schema + json.loads). It raises on
failure like both of those do - the caller shows a "AI summary unavailable,
raw scores above are still real" fallback rather than a fabricated
narrative (see pages/investment_analysis.py).

The price/sqm estimate this produces has NO real transaction data behind
it anywhere in this app - there is no comps dataset to ground it in. It is
shown anyway (a deliberate product decision - see improv.md's brief and
the plan that scoped this feature), but the schema forces a caveat field
that the UI renders as a prominent warning, never as a plain number.
"""

import json
import math
from collections import Counter, defaultdict
from typing import List, Tuple

import anthropic
from shapely.geometry import Polygon

from utils import app_config, osm_service

MODEL = "claude-opus-4-8"

# Fixed, ordered list so the amenity breakdown always renders in the same
# order regardless of what happened to be found - easier to scan/compare
# across two different reports.
ALL_AMENITY_CATEGORIES = [
    "Schools", "Hospitals", "Police Stations", "Markets", "Banks", "Fuel Stations",
    "Shopping Centres", "Bus Stops", "Religious Centres", "Restaurants",
    "Government Offices", "Hotels",
]

LAND_USE_TAG_MAP = {
    "residential": "Residential",
    "commercial": "Commercial",
    "retail": "Commercial",
    "industrial": "Industrial",
    "farmland": "Agricultural",
    "farmyard": "Agricultural",
    "orchard": "Agricultural",
    "meadow": "Agricultural",
    "vineyard": "Agricultural",
    "education": "Institutional",
    "religious": "Institutional",
    "cemetery": "Institutional",
    "military": "Government",
    "government": "Government",
    "grass": "Undeveloped Land",
    "forest": "Undeveloped Land",
    "greenfield": "Undeveloped Land",
    "brownfield": "Undeveloped Land",
    "meadow_undeveloped": "Undeveloped Land",
}

MAJOR_ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary"}


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _polygon_area_m2(geometry: List[Tuple[float, float]]) -> float:
    """Local equirectangular approximation, accurate to well under 1% at
    the <=2km radius this feature operates at - avoids a geopandas/CRS
    round-trip for what's typically a few dozen small polygons per report."""
    if len(geometry) < 3:
        return 0.0
    mean_lat = sum(p[0] for p in geometry) / len(geometry)
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(mean_lat))
    origin_lat, origin_lon = geometry[0]
    coords_m = [((lon - origin_lon) * m_per_deg_lon, (lat - origin_lat) * m_per_deg_lat) for lat, lon in geometry]
    try:
        poly = Polygon(coords_m)
        return abs(poly.area) if poly.is_valid else 0.0
    except Exception:
        return 0.0


def score_status(value: int) -> str:
    """Maps a 0-100 score to good/warning/critical, matching
    utils/theme.py's STATUS keys - used by pages/investment_analysis.py
    to color the score card/subscore bars consistently with the rest of
    the app's status language."""
    if value >= 65:
        return "good"
    if value >= 35:
        return "warning"
    return "critical"


def _rating_from_score(score: int) -> str:
    if score >= 80:
        return "Excellent"
    if score >= 60:
        return "Good"
    if score >= 35:
        return "Average"
    return "Poor"


def _accessibility_subscore(roads: List[dict], radius_m: int) -> dict:
    road_count = len(roads)
    major_roads = [r for r in roads if r["tags"].get("highway") in MAJOR_ROAD_CLASSES]
    density = road_count / max(radius_m / 100, 1)  # roads per 100m of radius, a crude but real density proxy
    density_score = min(60, density * 6)
    major_bonus = 40 if major_roads else (20 if road_count else 0)
    score = min(100, round(density_score + major_bonus))
    return {
        "score": score,
        "rating": _rating_from_score(score),
        "road_count": road_count,
        "major_road_count": len(major_roads),
        "has_major_road": bool(major_roads),
    }


def _development_subscore(buildings: List[dict], radius_m: int) -> dict:
    building_count = len(buildings)
    area_km2 = math.pi * (radius_m / 1000) ** 2
    density_per_km2 = building_count / area_km2 if area_km2 else 0.0
    # ~2000 buildings/km2 is already dense urban infill in Lagos-scale
    # residential areas - used as the "fully built up" reference point.
    score = min(100, round((density_per_km2 / 2000) * 100))
    return {"score": score, "building_count": building_count, "density_per_km2": round(density_per_km2, 1)}


def _amenity_subscore(amenities: List[dict], center: Tuple[float, float]) -> dict:
    by_category: dict = defaultdict(list)
    for feature in amenities:
        if feature.get("lat") is None:
            continue
        category = osm_service.amenity_category(feature["tags"])
        if category:
            by_category[category].append(_haversine_m(center, (feature["lat"], feature["lon"])))

    breakdown = []
    for category in ALL_AMENITY_CATEGORIES:
        distances = by_category.get(category, [])
        breakdown.append({
            "category": category,
            "count": len(distances),
            "nearest_m": round(min(distances)) if distances else None,
        })

    categories_present = sum(1 for b in breakdown if b["count"] > 0)
    total_count = sum(b["count"] for b in breakdown)
    # Variety (how many different needs are covered nearby) matters more
    # for livability than raw count of any one type.
    variety_score = (categories_present / len(ALL_AMENITY_CATEGORIES)) * 70
    volume_score = min(30, total_count * 1.5)
    score = round(min(100, variety_score + volume_score))
    return {"score": score, "breakdown": breakdown, "categories_present": categories_present, "total_count": total_count}


def _land_use_analysis(landuse_features: List[dict], radius_m: int) -> dict:
    area_by_category: Counter = Counter()
    tagged_area_m2 = 0.0
    for feature in landuse_features:
        area = _polygon_area_m2(feature["geometry"])
        if area <= 0:
            continue
        tag = feature["tags"].get("landuse")
        category = LAND_USE_TAG_MAP.get(tag, "Mixed Use")
        area_by_category[category] += area
        tagged_area_m2 += area

    buffer_area_m2 = math.pi * radius_m ** 2
    breakdown = []
    if tagged_area_m2 > 0:
        for category, area in area_by_category.most_common():
            breakdown.append({"category": category, "percentage": round(area / tagged_area_m2 * 100, 1)})

    return {
        "breakdown": breakdown,
        # How much of the buffer OpenStreetMap actually has land-use tags
        # for - shown alongside the breakdown so it reads as "of the
        # tagged area" rather than implying full ground-truth coverage.
        "tag_coverage_percentage": round(min(100.0, tagged_area_m2 / buffer_area_m2 * 100), 1) if buffer_area_m2 else 0.0,
    }


def _availability_subscore(land_use: dict) -> dict:
    undeveloped_pct = next(
        (b["percentage"] for b in land_use["breakdown"] if b["category"] == "Undeveloped Land"), 0.0
    )
    score = min(100, round(undeveloped_pct * 1.2))
    return {"score": score, "undeveloped_percentage": undeveloped_pct}


def _growth_subscore(development: dict, availability: dict) -> dict:
    """Blends current development level (proof the area is viable) with
    available vacant land (room left to grow) - deliberately simple and
    explainable rather than a fitted/opaque formula."""
    score = round((development["score"] + availability["score"]) / 2)
    return {"score": score}


def compute_investment_score(location: dict, radius_m: int, features: dict) -> dict:
    """location: {"lat", "lon"[, "display_name"]}. features: the dict
    returned by utils/osm_service.fetch_nearby_features(). Returns a flat
    dict: overall_score (0-100), verdict, and every subscore's own dict -
    same shape style as utils/risk_calculator.calculate_risk()."""
    center = (location["lat"], location["lon"])

    accessibility = _accessibility_subscore(features["roads"], radius_m)
    development = _development_subscore(features["buildings"], radius_m)
    amenities = _amenity_subscore(features["amenities"], center)
    land_use = _land_use_analysis(features["landuse"], radius_m)
    availability = _availability_subscore(land_use)
    growth = _growth_subscore(development, availability)

    weights = {"accessibility": 0.25, "development": 0.20, "amenities": 0.25, "availability": 0.15, "growth": 0.15}
    overall = round(
        accessibility["score"] * weights["accessibility"]
        + development["score"] * weights["development"]
        + amenities["score"] * weights["amenities"]
        + availability["score"] * weights["availability"]
        + growth["score"] * weights["growth"]
    )

    if overall >= 80:
        verdict = "Excellent Investment Opportunity"
    elif overall >= 65:
        verdict = "Strong Investment Opportunity"
    elif overall >= 50:
        verdict = "Moderate Investment Opportunity"
    elif overall >= 30:
        verdict = "Below-Average Opportunity"
    else:
        verdict = "Weak Opportunity - Limited Infrastructure"

    return {
        "overall_score": overall,
        "verdict": verdict,
        "accessibility": accessibility,
        "development": development,
        "amenities": amenities,
        "land_use": land_use,
        "availability": availability,
        "growth": growth,
    }


_NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": (
                "3-5 sentence plain-English narrative like a professional property consultant would "
                "write, grounded strictly in the real stats given - no claims beyond what's in the data."
            ),
        },
        "price_estimate": {
            "type": "object",
            "properties": {
                "per_sqm_low": {"type": "number", "description": "Low end of estimated price per square meter, in Naira."},
                "per_sqm_high": {"type": "number", "description": "High end of estimated price per square meter, in Naira."},
                "reasoning": {
                    "type": "string",
                    "description": "1-2 sentences on which location factors (accessibility, amenities, development level) drove this range.",
                },
                "caveat": {
                    "type": "string",
                    "description": (
                        "Mandatory plain-language warning that this is an AI estimate from location "
                        "factors only, with no real sales/transaction data behind it, and a real agent "
                        "or valuer should be consulted before relying on it."
                    ),
                },
            },
            "required": ["per_sqm_low", "per_sqm_high", "reasoning", "caveat"],
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-6 short, actionable recommendations (e.g. 'Suitable for residential investment', 'Requires further due diligence').",
        },
    },
    "required": ["summary", "price_estimate", "recommendations"],
}

_NARRATIVE_SYSTEM_PROMPT = """You are a professional real estate investment consultant writing a report \
section for a Nigerian land-investment tool called PlotProof. You are given real, measured statistics \
about a location (from OpenStreetMap - road counts, building density, nearby amenities, land-use mix) \
and a computed investment score. Write the narrative, price estimate, and recommendations strictly from \
this data.

Rules:
- Never claim anything not supported by the stats given (no invented schools/hospitals/roads, no claims \
about crime, flooding, or legal status - none of that data is available here).
- The price estimate has no real transaction/comps data behind it anywhere - it must be reasoned only \
from the given location factors (accessibility, development, amenities), and the caveat field is \
mandatory, not optional.
- Keep the summary understandable by someone with no GIS/real-estate background.
- Recommendations must be concrete and specific to what the stats actually show (e.g. cite the real \
accessibility rating or amenity gaps), not generic filler.

Location stats:
{stats_context}"""


def _build_stats_context(location: dict, radius_m: int, score: dict) -> str:
    amenity_lines = "\n".join(
        f"  - {b['category']}: {b['count']} found"
        + (f", nearest {b['nearest_m']}m away" if b["nearest_m"] is not None else "")
        for b in score["amenities"]["breakdown"]
    )
    land_use_lines = "\n".join(
        f"  - {b['category']}: {b['percentage']}%" for b in score["land_use"]["breakdown"]
    ) or "  - No land-use data tagged in OpenStreetMap for this area"

    return f"""Location: {location.get('display_name', f"{location['lat']:.5f}, {location['lon']:.5f}")}
Analysis radius: {radius_m}m

Investment score: {score['overall_score']}/100 ({score['verdict']})

Accessibility: {score['accessibility']['rating']} (score {score['accessibility']['score']}/100) - \
{score['accessibility']['road_count']} roads found, {score['accessibility']['major_road_count']} of them \
major roads (primary/secondary/trunk/motorway).

Development: score {score['development']['score']}/100 - {score['development']['building_count']} buildings \
in the analysis radius (~{score['development']['density_per_km2']} buildings/km2).

Amenities: score {score['amenities']['score']}/100 - {score['amenities']['categories_present']} of \
{len(ALL_AMENITY_CATEGORIES)} amenity categories present nearby, {score['amenities']['total_count']} total \
amenities found:
{amenity_lines}

Land use (of the {score['land_use']['tag_coverage_percentage']}% of the area that has land-use data tagged \
in OpenStreetMap):
{land_use_lines}

Land availability: score {score['availability']['score']}/100 - approximately \
{score['availability']['undeveloped_percentage']}% of tagged land is undeveloped/vacant.

Growth potential: score {score['growth']['score']}/100 (blends current development level with available \
vacant land)."""


def generate_investment_narrative(location: dict, radius_m: int, score: dict) -> dict:
    """Raises on failure (network error, rate limit, low credit balance -
    same failure modes as utils/assistant.py's ask()) rather than
    swallowing the exception - the caller shows a clear fallback instead
    of a fabricated narrative (see pages/investment_analysis.py)."""
    client = anthropic.Anthropic(api_key=app_config.get_anthropic_api_key())
    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        thinking={"type": "adaptive"},
        system=_NARRATIVE_SYSTEM_PROMPT.format(stats_context=_build_stats_context(location, radius_m, score)),
        output_config={"format": {"type": "json_schema", "schema": _NARRATIVE_SCHEMA}},
        messages=[{"role": "user", "content": "Generate the investment report section from the location stats above."}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)
