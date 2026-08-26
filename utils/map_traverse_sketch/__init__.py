"""
Custom Streamlit component: sketch a boundary traverse by clicking corners
directly on a real map, for when a survey plan's bearings/distances can't
be read at all (illegible scan, or the plot's corners are just easier to
place by eye against satellite imagery/visible fence lines than to
transcribe from a document). Click the first corner, then each next corner
in order - the bearing and distance between clicks are worked out
automatically (same whole-circle-bearing convention as utils/traverse.py)
and shown live as you move the mouse toward the next point, the same way a
CAD/GIS "add feature" tool tracks the next segment's length before you
commit it.

A static component (frontend/index.html), same approach as
utils/shape_georeferencer.py - see that module's docstring for why (no
React/webpack build step, hand-rolled Streamlit postMessage protocol,
Leaflet from a CDN). The two are separate components rather than one with
a mode flag: this one owns an accumulating points list and live
mouse-tracked preview, shape_georeferencer owns a single drag - different
enough interaction state that combining them would just be a mode branch
wrapped around two unrelated implementations.
"""

import os
from typing import Optional

import streamlit.components.v1 as components

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
_component_func = components.declare_component("map_traverse_sketch", path=_FRONTEND_DIR)


def map_traverse_sketch(
    center_lat: float,
    center_lon: float,
    zoom: int = 17,
    height: int = 480,
    key: Optional[str] = None,
) -> Optional[dict]:
    """
    center_lat/center_lon: where to initially center the map - a rough
      guess (e.g. a searched place, or Nigeria's centroid) to pan/zoom from.
    Returns None until the user clicks "Finish" (needs 3+ points placed),
    then:
      {
        "origin": {"lat": float, "lon": float},
        "legs": [{"bearing": float, "distance_m": float}, ...],
      }
    legs are in click order, whole-circle bearing degrees (0-360, clockwise
    from north) - the same convention traverse.parse_bearing_string()/
    format_bearing() use, so the result can be dropped straight into the
    same bearing/distance table the rest of this app already uses.
    """
    return _component_func(
        center_lat=center_lat,
        center_lon=center_lon,
        zoom=zoom,
        height=height,
        key=key,
        default=None,
    )
