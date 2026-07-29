"""
Admin-uploaded GeoJSON datasets that supplement/replace live OpenStreetMap
data for the Investment Analysis feature (pages/investment_analysis.py),
for areas where OpenStreetMap's tagging is sparse or Overpass is
unreachable - see data/sample_data/investment_fallback_sample.geojson for
the expected file format and utils/osm_service.py's module docstring for
the live-data path this supplements.

Format (see the sample file): a GeoJSON FeatureCollection with a top-level
`properties` block declaring what area/radius this dataset covers
(`center`, `radius_m`) plus metadata (`dataset_name`, `captured_at`,
`source`, `notes`), and each Feature tagged `properties.category` in
"amenity"/"road"/"landuse"/"building" with real OSM-style tags in the rest
of its `properties` (amenity=, highway=, landuse=, shop=, tourism=, etc.)
- deliberately the same tag vocabulary utils/osm_service.py's Overpass
results use, so a parsed upload converts into the exact same
{"amenities": [...], "roads": [...], "landuse": [...], "buildings": [...]}
shape utils/investment_analysis.compute_investment_score() already
expects, with zero new scoring logic needed.

Coverage matching: a query location "matches" a dataset if it falls
within that dataset's own declared center + radius_m circle - an admin
draws the boundary of what they're vouching for, rather than the app
guessing. apply_fallback() below merges per category: any category the
matching dataset has features for overrides that category's live OSM
result (admin data wins where it exists); categories the dataset is
silent on still fall back to whatever OSM returned.

Storage mirrors the rest of the app: local JSON by default, a Supabase
table once SUPABASE_URL/SUPABASE_KEY are configured (create the table
first - schema below).

    create table investment_fallback_datasets (
        id text primary key,
        name text,
        center jsonb,
        radius_m integer,
        captured_at text,
        source text,
        notes text,
        features jsonb,
        uploaded_at timestamptz
    );
"""

import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATASETS_DIR = Path(__file__).resolve().parent.parent / "data" / "investment_fallback"
DATASETS_FILE = DATASETS_DIR / "datasets.json"

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

_KNOWN_CATEGORIES = {"amenity": "amenities", "road": "roads", "landuse": "landuse", "building": "buildings"}
_GEOMETRY_TYPE_BY_CATEGORY = {
    "amenity": {"Point"},
    "building": {"Point"},
    "road": {"LineString"},
    "landuse": {"Polygon"},
}


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def parse_geojson(raw: dict) -> dict:
    """Validates and converts an uploaded GeoJSON FeatureCollection into
    this module's storage shape. Raises ValueError with a specific,
    admin-facing message on any structural problem - never silently
    drops or guesses at malformed input, since this data feeds directly
    into a report someone might make a real financial decision from."""
    if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
        raise ValueError("Not a GeoJSON FeatureCollection (missing or wrong \"type\").")

    meta = raw.get("properties") or {}
    center = meta.get("center")
    if not isinstance(center, dict) or "lat" not in center or "lon" not in center:
        raise ValueError("Missing top-level properties.center (needs {\"lat\": ..., \"lon\": ...}).")
    try:
        center = {"lat": float(center["lat"]), "lon": float(center["lon"])}
    except (TypeError, ValueError) as exc:
        raise ValueError("properties.center.lat/lon must be numbers.") from exc

    radius_m = meta.get("radius_m")
    if not isinstance(radius_m, (int, float)) or radius_m <= 0:
        raise ValueError("Missing or invalid top-level properties.radius_m (must be a positive number).")

    features = {"amenities": [], "roads": [], "landuse": [], "buildings": []}
    raw_features = raw.get("features")
    if not isinstance(raw_features, list) or not raw_features:
        raise ValueError("No features found in the file.")

    for i, feature in enumerate(raw_features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"Feature #{i + 1} isn't a valid GeoJSON Feature.")
        props = feature.get("properties") or {}
        category = props.get("category")
        if category not in _KNOWN_CATEGORIES:
            raise ValueError(
                f"Feature #{i + 1} has properties.category={category!r} - must be one of "
                f"{sorted(_KNOWN_CATEGORIES)}."
            )
        geometry = feature.get("geometry") or {}
        geom_type = geometry.get("type")
        if geom_type not in _GEOMETRY_TYPE_BY_CATEGORY[category]:
            raise ValueError(
                f"Feature #{i + 1} (category={category}) has geometry type {geom_type!r} - expected "
                f"{sorted(_GEOMETRY_TYPE_BY_CATEGORY[category])}."
            )

        tags = {k: v for k, v in props.items() if k != "category"}
        bucket = _KNOWN_CATEGORIES[category]
        if geom_type == "Point":
            lon, lat = geometry["coordinates"]
            features[bucket].append({"lat": lat, "lon": lon, "tags": tags})
        elif geom_type == "LineString":
            line = [(lat, lon) for lon, lat in geometry["coordinates"]]
            features[bucket].append({"geometry": line, "tags": tags})
        elif geom_type == "Polygon":
            ring = geometry["coordinates"][0]
            line = [(lat, lon) for lon, lat in ring]
            features[bucket].append({"geometry": line, "tags": tags})

    return {
        "name": meta.get("dataset_name") or "Untitled dataset",
        "center": center,
        "radius_m": radius_m,
        "captured_at": meta.get("captured_at"),
        "source": meta.get("source"),
        "notes": meta.get("notes"),
        "features": features,
    }


def _load_local_records() -> list:
    if not DATASETS_FILE.exists():
        return []
    try:
        return json.loads(DATASETS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_local_records(records: list) -> None:
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    DATASETS_FILE.write_text(json.dumps(records, indent=2))


def list_datasets() -> list:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        response = client.table("investment_fallback_datasets").select("*").order("uploaded_at", desc=True).execute()
        return response.data or []

    return sorted(_load_local_records(), key=lambda r: r.get("uploaded_at", ""), reverse=True)


def add_dataset(raw_geojson: dict) -> str:
    """raw_geojson: the parsed JSON content of an uploaded .geojson file.
    Raises ValueError (from parse_geojson) on invalid input - callers
    should show that message directly, it's already admin-facing."""
    parsed = parse_geojson(raw_geojson)
    dataset_id = uuid.uuid4().hex[:10]
    record = {"id": dataset_id, "uploaded_at": datetime.now(timezone.utc).isoformat(), **parsed}

    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("investment_fallback_datasets").insert(record).execute()
        return dataset_id

    records = _load_local_records()
    records.append(record)
    _save_local_records(records)
    return dataset_id


def delete_dataset(dataset_id: str) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("investment_fallback_datasets").delete().eq("id", dataset_id).execute()
        return

    records = [r for r in _load_local_records() if r["id"] != dataset_id]
    _save_local_records(records)


def find_covering_dataset(lat: float, lon: float) -> Optional[dict]:
    """The first uploaded dataset whose own center+radius circle contains
    (lat, lon), or None. If more than one covers the same point, the most
    recently uploaded one wins (list_datasets() is newest-first) - an
    admin re-uploading a corrected dataset for the same area should take
    over immediately without needing to delete the old one first."""
    for dataset in list_datasets():
        center = dataset["center"]
        if _haversine_m(lat, lon, center["lat"], center["lon"]) <= dataset["radius_m"]:
            return dataset
    return None


def apply_fallback(features: Optional[dict], lat: float, lon: float) -> dict:
    """features: the result of utils/osm_service.fetch_nearby_features(),
    or None if that call failed entirely. Returns the feature set to
    actually score/map: for each category, an admin-uploaded dataset
    covering (lat, lon) overrides that category if it has any features
    for it; a category the dataset is silent on falls back to whatever
    OSM returned (or stays empty if OSM also failed/had nothing)."""
    merged = dict(features) if features else {"amenities": [], "roads": [], "landuse": [], "buildings": []}
    dataset = find_covering_dataset(lat, lon)
    if dataset:
        for bucket in ("amenities", "roads", "landuse", "buildings"):
            if dataset["features"].get(bucket):
                merged[bucket] = dataset["features"][bucket]
    return merged
