"""
GIS Processing Module for PlotProof.

Builds a geometry for the user's plot from the coordinates they provided
(a closed boundary if 3+ points were given, otherwise a buffered point/line
representing the approximate plot extent), then checks it against a set of
neighboring plots for overlaps and close-proximity boundaries.

Neighboring-plot data is synthetic sample data for now (see
data/sample_data/neighboring_plots.geojson) - swap load_neighboring_plots()
for a real land-records source later.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, Polygon
from shapely.validation import explain_validity

from utils import registry

SAMPLE_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "sample_data" / "neighboring_plots.geojson"
)

DEFAULT_POINT_BUFFER_M = 100  # assumed plot radius when only 1-2 points are given
DEFAULT_PROXIMITY_BUFFER_M = 150  # "too close for comfort" distance to a neighboring plot
DEFAULT_CONTEXT_RADIUS_M = 800  # how far out the map shows surrounding registered plots


def load_neighboring_plots(path: Path = SAMPLE_DATA_PATH) -> gpd.GeoDataFrame:
    """Synthetic sample plots plus whatever real plots users have opted to
    add to the shared registry (utils/registry.py) - not cached, so a
    newly-contributed plot is visible to the very next analysis."""
    sample = gpd.read_file(path)
    contributed = registry.load_registry_gdf()
    if contributed.empty:
        return sample
    return gpd.GeoDataFrame(pd.concat([sample, contributed], ignore_index=True), crs="EPSG:4326")


def nearby_plots_for_context(
    user_gdf: gpd.GeoDataFrame,
    neighbors_gdf: gpd.GeoDataFrame,
    radius_m: float = DEFAULT_CONTEXT_RADIUS_M,
) -> gpd.GeoDataFrame:
    """Neighbors within radius_m of the user's plot, for map display - as
    the registry grows this keeps the map showing immediate surroundings
    instead of every registered plot nationwide."""
    if neighbors_gdf.empty:
        return neighbors_gdf
    utm_crs = user_gdf.estimate_utm_crs()
    user_geom_m = user_gdf.to_crs(utm_crs).geometry.iloc[0]
    neighbors_m = neighbors_gdf.to_crs(utm_crs)
    within = neighbors_m.geometry.distance(user_geom_m) <= radius_m
    return neighbors_gdf[within.values]


def check_boundary_validity(points: List[Tuple[float, float]]) -> Optional[str]:
    """A self-intersecting ("bowtie") boundary is geometrically impossible
    as a real plot outline - it's either a data-entry/reading error (wrong
    beacon order, a transposed coordinate) or, less commonly, a sign of a
    manipulated document. Either way it's worth surfacing before the user
    trusts the shape shown. Checked on the raw ring here (via shapely,
    before build_user_plot_gdf() closes it into a GeoDataFrame) since
    that's real, checkable geometry - not a guess about intent. Only
    meaningful for an actual boundary (3+ points); a 1-2 point buffer
    estimate has no ring to self-intersect."""
    if len(points) < 3:
        return None
    coords_lonlat = [(lon, lat) for lat, lon in points]
    if coords_lonlat[0] != coords_lonlat[-1]:
        coords_lonlat.append(coords_lonlat[0])
    geom = Polygon(coords_lonlat)
    if geom.is_valid:
        return None
    return (
        f"This boundary's outline crosses itself ({explain_validity(geom)}), which isn't a "
        "geometrically possible plot shape - it usually means a beacon is out of order or a "
        "coordinate was misread/mistyped. Please check the order and values of your coordinates."
    )


def build_user_plot_gdf(
    points: List[Tuple[float, float]],
    point_buffer_m: float = DEFAULT_POINT_BUFFER_M,
) -> gpd.GeoDataFrame:
    """
    points: list of (lat, lon) pairs, e.g. survey beacon corners.
    3+ points form the actual plot boundary. 1-2 points (manual entry,
    or a sparse OCR read) are buffered to approximate a plot extent.
    """
    if not points:
        raise ValueError("At least one coordinate point is required.")

    coords_lonlat = [(lon, lat) for lat, lon in points]

    if len(points) >= 3:
        if coords_lonlat[0] != coords_lonlat[-1]:
            coords_lonlat.append(coords_lonlat[0])
        geom = Polygon(coords_lonlat)
        return gpd.GeoDataFrame({"source": ["survey_polygon"]}, geometry=[geom], crs="EPSG:4326")

    geom = Point(coords_lonlat[0]) if len(points) == 1 else LineString(coords_lonlat)
    source = "point_buffer" if len(points) == 1 else "two_point_buffer"

    gdf_4326 = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    utm_crs = gdf_4326.estimate_utm_crs()
    buffered_geom = gdf_4326.to_crs(utm_crs).buffer(point_buffer_m).to_crs("EPSG:4326").iloc[0]
    return gpd.GeoDataFrame({"source": [source]}, geometry=[buffered_geom], crs="EPSG:4326")


def analyze_overlap(
    user_gdf: gpd.GeoDataFrame,
    neighbors_gdf: gpd.GeoDataFrame,
    proximity_buffer_m: float = DEFAULT_PROXIMITY_BUFFER_M,
) -> Dict[str, Any]:
    """Reprojects to a local metric CRS and checks the user's plot against every neighbor."""
    utm_crs = user_gdf.estimate_utm_crs()
    user_geom_m = user_gdf.to_crs(utm_crs).geometry.iloc[0]
    neighbors_m = neighbors_gdf.to_crs(utm_crs)

    overlaps, proximate = [], []
    for _, row in neighbors_m.iterrows():
        distance = user_geom_m.distance(row.geometry)
        info = {"plot_ref": row.get("plot_ref", "unknown"), "owner": row.get("owner", "unknown")}
        if distance <= 0:
            info["overlap_area_sqm"] = round(user_geom_m.intersection(row.geometry).area, 1)
            overlaps.append(info)
        elif distance <= proximity_buffer_m:
            info["distance_m"] = round(distance, 1)
            proximate.append(info)

    return {"overlaps": overlaps, "proximate": proximate}
