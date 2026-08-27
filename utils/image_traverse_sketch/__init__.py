"""
Custom Streamlit component: trace a boundary's rough shape by clicking
corners directly on an uploaded document's own image (a photographed/
scanned survey plan, or a rasterized PDF page - see
utils/file_handler.py's render_pdf_first_page_png()), for when automatic
extraction couldn't read a bearing/distance traverse from it at all.

Deliberately shape-only, not distance-accurate: an unscaled scan carries
no reliable real-world measurement (no scale bar most of the time, and
even where there is one, reading it introduces its own error) - see
pages/diagonal_calculator.py's docstring for how the resulting rough
shape gets placed on a real map afterward (utils/shape_georeferencer.py),
where per-corner dragging against real satellite imagery is what actually
establishes accuracy, not this step. This step exists purely to skip
typing a whole bearing/distance table by hand when the drawn shape itself
is legible even though the printed numbers next to it aren't.

A static component (frontend/index.html), same approach as
utils/shape_georeferencer.py and utils/map_traverse_sketch.py - see
either's docstring for why (no React/webpack build step, hand-rolled
Streamlit postMessage protocol). Plain HTML/SVG over an <img>, not
Leaflet - there's no tiling, panning basemap, or geographic CRS involved,
just click positions relative to one static image.
"""

import base64
import os
from typing import Optional

import streamlit.components.v1 as components

from utils._shared_map_component import sync_into

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
sync_into(_FRONTEND_DIR)
_component_func = components.declare_component("image_traverse_sketch", path=_FRONTEND_DIR)


def image_traverse_sketch(
    image_bytes: bytes,
    mime_type: str = "image/png",
    height: int = 480,
    key: Optional[str] = None,
) -> Optional[dict]:
    """
    image_bytes: the reference image's raw bytes (the uploaded photo/scan,
      or a rasterized PDF page) - sent as a data: URI, not a URL, since the
      file lives in this session's own upload storage, not somewhere the
      browser can otherwise reach.
    Returns None until "Finish" is clicked (3+ points), then
      {"points": [{"x": float, "y": float}, ...]}
    x/y are fractions (0-1) of the image's displayed width/height, in
    click order - resolution-independent shape only, no real-world scale
    (see this module's docstring for why).
    """
    data_uri = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    return _component_func(image_data_uri=data_uri, height=height, key=key, default=None)
