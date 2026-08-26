"""
Custom Streamlit component: drag-to-position georeferencing for a
boundary shape onto a real map, for when no real-world coordinate is
known at all - extraction found nothing on the uploaded document, and the
user has no GPS reading for the plot either. Two kinds of drag:

  - The origin (blue) marker moves the WHOLE shape rigidly - for placing
    it in roughly the right spot to start with.
  - Every other (green) vertex marker moves independently - for
    fine-tuning one corner at a time against real satellite/street
    imagery, since the input shape isn't always trustworthy to the
    centimeter (see pages/diagonal_calculator.py's callers: one passes a
    survey-accurate shape from real bearings/distances, the other a rough
    shape traced by clicking an unscaled document image - the latter
    specifically NEEDS per-corner correction, not just repositioning).

Confirming returns every vertex's final position, not just the origin -
the shape itself may have changed from per-corner drags, so the caller
recomputes bearings/distances from these positions directly rather than
reusing whatever it started with. Each edge shows its own live bearing/
distance label on the map too (same convention as
utils/map_traverse_sketch.py's own segment labels), recomputed from the
CURRENT positions after every drag - so what you see on the map always
matches what confirming will return, not the pre-drag numbers.

A static component (frontend/index.html) - no React/webpack build step,
since this is one self-contained widget, not a design system. It talks to
Streamlit's parent frame directly via the documented postMessage protocol
(componentReady / render / setComponentValue / setFrameHeight) rather than
pulling in the streamlit-component-lib package, which is meant for
bundling, not direct browser use. Leaflet itself loads from a CDN inside
that static page - this runs in the user's own real browser (not a
sandboxed preview), so that's unrestricted here, same as folium's own
tile-layer URLs elsewhere in this app.
"""

import os
from typing import List, Optional, Sequence, Tuple

import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
_component_func = components.declare_component("shape_georeferencer", path=_FRONTEND_DIR)


def shape_georeferencer(
    vertices_en: Sequence[Tuple[float, float]],
    labels: List[str],
    center_lat: float,
    center_lon: float,
    zoom: int = 16,
    height: int = 480,
    key: Optional[str] = None,
) -> Optional[dict]:
    """
    vertices_en: [(easting, northing), ...] in meters, relative to the
      origin (vertex 0) at local (0, 0) - the shape's own geometry, not the
      plan's real projected coordinates (those aren't needed here, only
      the shape matters).
    center_lat/center_lon: where to initially center the map and place the
      draggable origin marker - a rough guess (e.g. a searched place, or
      Nigeria's centroid) to pan/zoom from, not a precise value.
    Returns None until the user clicks "Confirm this position" in the
    widget, then {"vertices": [{"lat": float, "lon": float}, ...]} - every
    vertex's final position, same order as vertices_en/labels.
    """
    return _component_func(
        vertices_en=[list(v) for v in vertices_en],
        labels=labels,
        center_lat=center_lat,
        center_lon=center_lon,
        zoom=zoom,
        height=height,
        key=key,
        default=None,
    )
