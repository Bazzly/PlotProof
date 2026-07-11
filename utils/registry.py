"""
Opt-in shared land registry.

A single-user risk check is only ever as good as what it's compared
against. This lets a user add their analyzed plot's *boundary geometry
only* (no owner name, no source document) to a shared pool that future
uploads get checked against too - so the system's coverage grows with
usage instead of staying fixed to the synthetic sample data.

This is a distinct consent from utils/training_data.py: that one is about
improving extraction accuracy on your own document. This one is about
your plot's shape being used to check *other people's* land, indefinitely,
which is why it's a separate opt-in with its own explicit copy in the UI
- never bundled into another checkbox, never on by default.

Storage mirrors the existing local/Supabase pattern. Supabase table:

    create table registry_plots (
        plot_ref text primary key,
        geometry jsonb,
        added_at timestamptz
    );
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import geopandas as gpd
from shapely.geometry import Polygon, mapping, shape

REGISTRY_DIR = Path(__file__).resolve().parent.parent / "data" / "registry"
REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_FILE = REGISTRY_DIR / "registry_plots.json"

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Shown as the "owner" on the map/findings for registry-contributed plots,
# since no owner name is ever stored.
CONTRIBUTOR_LABEL = "Registry contributor"


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def _new_plot_ref() -> str:
    return f"PP-{uuid.uuid4().hex[:8].upper()}"


def _load_local_records() -> list:
    if not REGISTRY_FILE.exists():
        return []
    return json.loads(REGISTRY_FILE.read_text())


def _save_local_records(records: list) -> None:
    REGISTRY_FILE.write_text(json.dumps(records, indent=2))


def add_plot(points: List[Tuple[float, float]]) -> str:
    """
    points: 3+ (lat, lon) WGS84 boundary vertices - a real surveyed/
    reconstructed boundary, not a buffered single-point estimate.
    Returns the generated plot_ref.
    """
    if len(points) < 3:
        raise ValueError("Only real boundary polygons (3+ points) can be added to the registry.")

    plot_ref = _new_plot_ref()
    polygon = Polygon([(lon, lat) for lat, lon in points])
    record = {
        "plot_ref": plot_ref,
        "geometry": mapping(polygon),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }

    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("registry_plots").insert(record).execute()
        return plot_ref

    records = _load_local_records()
    records.append(record)
    _save_local_records(records)
    return plot_ref


def load_registry_gdf() -> gpd.GeoDataFrame:
    """Returns a GeoDataFrame with plot_ref + a generic owner label - empty
    (not None) if nothing has been contributed yet, so callers can always
    concat it with other neighbor data."""
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        rows = client.table("registry_plots").select("plot_ref,geometry").execute().data
    else:
        rows = _load_local_records()

    if not rows:
        return gpd.GeoDataFrame({"plot_ref": [], "owner": []}, geometry=[], crs="EPSG:4326")

    return gpd.GeoDataFrame(
        {
            "plot_ref": [r["plot_ref"] for r in rows],
            "owner": [CONTRIBUTOR_LABEL] * len(rows),
        },
        geometry=[shape(r["geometry"]) for r in rows],
        crs="EPSG:4326",
    )


def count() -> int:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        result = client.table("registry_plots").select("plot_ref", count="exact").execute()
        return result.count or 0
    return len(_load_local_records())
