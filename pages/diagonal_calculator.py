"""
Diagonal Calculator - a standalone tool for the boundary "Diagonal Check"
(utils/traverse.py's compute_diagonal(): a straight-line bearing/distance
reference from a plot's origin corner to the corner directly opposite it,
useful for pacing out an on-site sanity check). Normally this only shows up
buried inside the main Land Risk Check's bearing/distance editor, after a
full document upload; this page exposes the same math directly, two ways -

  - Manual Entry: type a bearing/distance traverse by hand, no file at all -
    useful standing over a paper plan with nothing to upload.
  - Upload a Plan: reuses the same text/OCR/vision extraction as
    app_home.py's main flow to auto-fill that same table from a real
    document, still editable before computing.

Both feed the same traverse math (utils/traverse.py) and render the same
result card - editing a table is the one shared interaction, whichever tab
fills it first. Whenever a real-world origin is known (always true for an
uploaded document that extracted cleanly; optional for manual entry), the
boundary is also drawn on a real map (see _render_click_map()) - clicking
anywhere on it reads off that point's coordinate directly, without needing
to work out its bearing/distance from the origin by hand first.

When an uploaded file's automatic extraction finds nothing at all, three
fallbacks build the same bearing/distance table another way: trace the
boundary's rough shape by clicking corners on the document's own image/
PDF preview (_render_image_trace_picker(), utils/image_traverse_sketch.py -
shape only, no real scale), sketch it by clicking corners directly on a
real map (_render_map_sketch_picker(), utils/map_traverse_sketch.py - gets
real-world position too, live bearing/distance as you go), or type it in
by hand off the same preview. Whichever produces a shape with no real-world
origin yet, _render_georeference_picker() (utils/shape_georeferencer.py)
lets the user search their area and drag it onto the real map - the whole
shape via one origin marker, or any single corner independently, since a
traced shape in particular is only ever a rough starting guess.

Deliberately excludes everything the main flow does that isn't about the
diagonal itself: no shared-registry overlap check, no risk score, no PDF
report, no coordinate-list-only entry (the diagonal's bearing/distance only
means something in the plan's own projected meters, not raw lat/lon
degrees - see compute_diagonal()'s docstring). Reachable from the sidebar
(utils/nav.py) on every page, not part of the main flow's own step order.
"""

import os
import traceback

import folium
import streamlit as st
from dotenv import load_dotenv
from folium.plugins import Fullscreen
from streamlit_folium import st_folium

from utils import coordinates, crs_utils, file_handler, nav, osm_service, rate_limit, theme, traverse, vision_extract
from utils.image_traverse_sketch import image_traverse_sketch
from utils.map_traverse_sketch import map_traverse_sketch
from utils.shape_georeferencer import shape_georeferencer

load_dotenv()

st.set_page_config(page_title="Diagonal Calculator - PlotProof", page_icon="assets/logo.svg", layout="centered")
st.markdown(theme.get_css(), unsafe_allow_html=True)
nav.render_sidebar()
nav.render_floating_chat()

DAILY_VISION_LIMIT = int(os.environ.get("DAILY_VISION_LIMIT", "5"))
BURST_MAX_REQUESTS = int(os.environ.get("BURST_MAX_REQUESTS", "10"))
BURST_WINDOW_SECONDS = int(os.environ.get("BURST_WINDOW_SECONDS", "60"))
CLIENT_ID = rate_limit.get_client_id()

CRS_OPTIONS = {"Auto-detect": None}
CRS_OPTIONS.update({name: epsg for epsg, name in crs_utils.NIGERIA_CRS_CANDIDATES.items()})

_LEG_COLUMN_CONFIG = {
    "beacon": st.column_config.TextColumn(
        "Line",
        help='Which two boundary corners this row describes, e.g. "PL1 → PL2" means the line '
        "from corner 1 to corner 2.",
    ),
    "bearing_text": st.column_config.TextColumn(
        "Bearing",
        help="The compass direction of this line, as printed on your survey plan "
        "(e.g. 52°30' or 176°) - degrees clockwise from North, 0-360°.",
    ),
    "distance_m": st.column_config.NumberColumn(
        "Distance (m)",
        min_value=0.0,
        format="%.2f",
        help="The length of this line in meters, as printed on your survey plan.",
    ),
}
_LEG_COLUMN_ORDER = ["beacon", "bearing_text", "distance_m"]

_DEFAULT_MANUAL_ROWS = [
    {"beacon": f"PL{i + 1} → PL{i + 2 if i < 3 else 1}", "bearing_text": "", "distance_m": None} for i in range(4)
]

# Same fallback center investment_analysis.py uses for its own "click on
# map" location step - a Nigeria-wide default to zoom out from before a
# search narrows it down.
NIGERIA_CENTER = (9.0820, 8.6753)


st.markdown(
    """
    <div class="pp-hero">
      <div class="pp-logo">📐</div>
      <div>
        <h1>Diagonal Calculator</h1>
        <p>Straight-line distance and bearing across your plot, for an on-site sanity check.</p>
      </div>
    </div>
    <p class="pp-lede">A diagonal reference - bearing and distance in a straight line from your
    plot's origin corner to the corner directly opposite it - computed from a bearing/distance
    traverse the same way PlotProof's main Land Risk Check does it. Most Nigerian survey plans
    don't print this measurement; it's always derived, and useful for pacing out on-site as a
    sanity check. Not a substitute for a licensed surveyor.</p>
    """,
    unsafe_allow_html=True,
)


def _get_preview_bytes(saved_path: str, file_type: str) -> tuple:
    """A displayable reference image for the upload-failure fallbacks
    below (both st.image() and the image-trace component need raw bytes,
    not just a file path that might be a PDF) - the image file itself for
    a photo/scan, or the first page rasterized (utils/file_handler.py's
    render_pdf_first_page_png()) for a PDF. Returns (bytes, mime_type),
    (None, None) if there's nothing to show (an unreadable PDF)."""
    if file_type in ("png", "jpg", "jpeg") and os.path.isfile(saved_path):
        with open(saved_path, "rb") as f:
            return f.read(), f"image/{'jpeg' if file_type == 'jpg' else file_type}"
    if file_type == "pdf":
        png_bytes = file_handler.render_pdf_first_page_png(saved_path)
        if png_bytes:
            return png_bytes, "image/png"
    return None, None


def _parse_legs(rows: list) -> tuple:
    """Same all-or-nothing parsing app_home.py's legs editor uses - a
    traverse walk is sequential, so one unparseable row invalidates every
    vertex after it, not just its own leg. Returns (legs, labels, all_parsed)."""
    legs, labels, all_parsed = [], [], True
    for i, row in enumerate(rows):
        bearing = traverse.parse_bearing_string(row.get("bearing_text"))
        distance = row.get("distance_m")
        if bearing is None or distance is None:
            all_parsed = False
            break
        legs.append((bearing, distance))
        beacon = row.get("beacon") or f"PL{i + 1}"
        labels.append(beacon.split(" → ")[0] if " → " in beacon else beacon)
    return legs, labels, all_parsed


def _render_legs_editor_and_result(rows: list, editor_key: str, origin_en: tuple, origin_latlon: tuple = None) -> None:
    edited_rows = st.data_editor(
        rows,
        column_config=_LEG_COLUMN_CONFIG,
        column_order=_LEG_COLUMN_ORDER,
        num_rows="dynamic",
        hide_index=True,
        key=editor_key,
    )

    legs, labels, all_parsed = _parse_legs(edited_rows)

    if edited_rows and not all_parsed:
        st.info("Fill in every row's bearing and distance to compute the boundary below.")
        return
    if len(legs) < 3:
        st.info("Add at least 3 boundary legs (rows) to compute a shape.")
        return

    polygon_en = traverse.compute_traverse(origin_en, legs)
    closed = polygon_en is not None
    closure_error_m = 0.0
    if not closed:
        polygon_en, closure_error_m = traverse.build_open_polygon(origin_en, legs)

    if not polygon_en or len(polygon_en) < 3:
        st.warning("Couldn't build a shape from these legs - check your bearing/distance values.")
        return

    # A diagonal needs 4+ vertices (see compute_diagonal()'s docstring) -
    # gates the georeference picker below too, since there'd be nothing to
    # place a triangle's non-existent diagonal onto anyway. Vertex COUNT is
    # unaffected by anything the picker does (it repositions/redraws points,
    # never adds or removes one), so this check doesn't need repeating
    # after it runs.
    if len(polygon_en) < 4:
        st.info("A diagonal needs at least 4 boundary corners - a triangle has no non-adjacent vertex pair.")
        return

    # Per-vertex adjustment on the georeference-picker map can change the
    # shape itself, not just its position - when that happens, everything
    # below (area/perimeter/diagonal/WGS84 points) must come from the
    # ADJUSTED polygon, not the legs the user originally typed/traced.
    picker_result = None
    if origin_latlon is None:
        picker_result = _render_georeference_picker(polygon_en, origin_en, labels, key_prefix=editor_key)
        if picker_result:
            origin_latlon = picker_result["origin_latlon"]
            polygon_en = picker_result["polygon_en"]
            closed, closure_error_m = True, 0.0

    area = traverse.shoelace_area(polygon_en)
    perimeter = sum(distance for _, distance in traverse.legs_from_vertices(polygon_en, close=True))

    col1, col2, col3 = st.columns(3)
    col1.metric("Area", f"{area:,.1f} m²")
    col2.metric("Perimeter", f"{perimeter:,.1f} m")
    col3.metric("Closure", "Closed ✓" if closed else f"Off by {closure_error_m:.2f} m")

    if not closed:
        st.warning(
            "This traverse doesn't fully close within tolerance - common on older or "
            "hand-surveyed plans. The shape and diagonal below are approximate; double-check "
            "your bearing/distance values against the original document."
        )
    elif picker_result:
        st.caption(
            "Area/perimeter/diagonal below reflect your dragged map adjustment - the bearing/"
            "distance table above still shows the values it started from."
        )

    diagonal = traverse.compute_diagonal(polygon_en, labels=labels)

    points_latlon = None
    if origin_latlon and picker_result:
        # The adjusted shape is already final positions, not a legs walk -
        # convert it directly rather than through resolve_recomputed_points()
        # below, which would re-walk the PRE-adjustment legs and silently
        # discard the drag.
        points_latlon = [traverse.local_en_to_latlon(origin_en, origin_latlon, e, n) for e, n in polygon_en]
        diagonal["point_latlon"] = traverse.local_en_to_latlon(origin_en, origin_latlon, *diagonal["point_en"])
    elif origin_latlon:
        points_latlon, _, ll_diagonal = traverse.resolve_recomputed_points(origin_en, origin_latlon, legs, labels=labels)
        if ll_diagonal:
            diagonal["point_latlon"] = ll_diagonal.get("point_latlon")

    origin_label = labels[0] if labels else "PL1"
    coord_lines = f'<p>Coordinate (local grid): <strong>{diagonal["point_label"]}</strong></p>'
    if diagonal.get("point_latlon"):
        lat, lon = diagonal["point_latlon"]
        coord_lines += f"<p>Coordinate (WGS84): <strong>{lat:.6f}, {lon:.6f}</strong></p>"

    st.markdown(
        f"""
        <div class="pp-card">
          <div class="pp-card-title">Diagonal Check</div>
          <p>A straight-line distance and bearing from the origin ({origin_label}) to the opposite
          corner, calculated from the boundary above - a reference you can pace out on-site to
          sanity-check the plot's extent.</p>
          <p><strong>{origin_label} → {diagonal['target_label']}: {traverse.format_bearing(diagonal['bearing'])}
          · {diagonal['distance_m']:.2f}m</strong></p>
          {coord_lines}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if points_latlon and len(points_latlon) >= 3:
        _render_click_map(origin_en, origin_latlon, points_latlon, diagonal, labels, map_key=f"{editor_key}_map")


def _rows_from_legs(legs: list) -> list:
    """Bearing/distance legs (as (bearing_deg, distance_m) tuples, e.g.
    from traverse.legs_from_vertices()) to data_editor row dicts, in the
    same shape _parse_legs() reads back - shared by every fallback that
    derives a leg table from something other than typed/extracted text
    (a map sketch, an image trace)."""
    n = len(legs)
    return [
        {
            "beacon": f"PL{i + 1} → PL{i + 2 if i + 2 <= n else 1}",
            "bearing_text": traverse.format_bearing(bearing),
            "distance_m": round(distance, 2),
        }
        for i, (bearing, distance) in enumerate(legs)
    ]


# A rough starting size (meters) for a shape traced by clicking an
# unscaled document image - see _render_image_trace_picker()'s docstring
# for why this is deliberately not meant to be accurate; a typical
# residential plot's longest side is roughly in this range, which keeps
# the traced shape a sensible size to start fine-tuning from on a real
# map, rather than absurdly tiny or huge.
_IMAGE_TRACE_TARGET_SPAN_M = 40.0


def _render_image_trace_picker(image_bytes: bytes, mime_type: str, origin_en: tuple, key_prefix: str) -> dict:
    """Fallback for tracing a boundary's rough shape by clicking corners
    directly on the uploaded document's own image (see
    utils/image_traverse_sketch.py), for when the drawn shape is legible
    even though the printed bearing/distance numbers next to it aren't.

    Deliberately not distance-accurate: an unscaled scan has no reliable
    real-world measurement, so the clicked points are normalized to an
    arbitrary _IMAGE_TRACE_TARGET_SPAN_M starting size rather than treated
    as real meters - real accuracy comes from dragging the resulting shape
    (and fine-tuning individual corners) against satellite imagery on the
    georeference-picker map afterward, same as any other rough shape fed
    into _render_legs_editor_and_result() with no origin_latlon yet.

    Returns {"rows": [...]} once the user finishes (3+ points) - same row
    shape _render_map_sketch_picker() returns. Cached in session_state,
    same reasoning as the other pickers on this page."""
    result_key = f"{key_prefix}_trace_result"
    already = st.session_state.get(result_key)
    if already:
        return already

    with st.expander("Trace it on the image/PDF", expanded=True):
        st.caption(
            "Click your plot's first corner on the preview below, then each next corner in "
            "order, clockwise. This only needs to capture the rough shape - you'll drag it into "
            "position (and can fine-tune each corner) on a real map next."
        )
        trace = image_traverse_sketch(image_bytes, mime_type=mime_type, key=f"{key_prefix}_trace_widget")
        if trace and trace.get("points") and len(trace["points"]) >= 3:
            pts = trace["points"]
            xs = [p["x"] for p in pts]
            ys = [p["y"] for p in pts]
            span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
            scale = _IMAGE_TRACE_TARGET_SPAN_M / span
            x0, y0 = pts[0]["x"], pts[0]["y"]
            # Image y increases downward; northing increases north (up) -
            # inverted here so the traced shape isn't mirrored top-to-bottom
            # once it lands on a real map.
            vertices_en = [
                (origin_en[0] + (p["x"] - x0) * scale, origin_en[1] - (p["y"] - y0) * scale) for p in pts
            ]
            # close=True - the traced points describe a closed plot
            # boundary, so the last leg (back to the first point) is a
            # real edge, not something to omit. Without it,
            # compute_traverse()/build_open_polygon() would treat the
            # final clicked corner as an inaccurate "closing" vertex and
            # drop it, silently losing a real point.
            legs = traverse.legs_from_vertices(vertices_en, close=True)
            confirmed = {"rows": _rows_from_legs(legs)}
            st.session_state[result_key] = confirmed
            st.success(f"Traced {len(pts)} corner(s) - review the rough shape below, then place it on a map.")
            return confirmed
    return None


def _render_map_sketch_picker(key_prefix: str) -> dict:
    """Sketch-a-traverse fallback for when there's no bearing/distance to
    type in at all - an illegible scan, or the corners are just easier to
    place by eye against satellite imagery than to transcribe from a
    document. Click corners directly on a real map; utils/
    map_traverse_sketch.py works out each segment's bearing/distance live
    as you go, in the same whole-circle-bearing convention as the rest of
    this page.

    Returns {"origin_latlon": (lat, lon), "rows": [...]} once the user
    finishes (3+ points) - rows already in the shape the bearing/distance
    data_editor elsewhere on this page expects, so the result can feed
    straight into _render_legs_editor_and_result() same as a typed or
    extracted table. Cached in session_state so it survives reruns from
    unrelated widgets, same reasoning as _render_georeference_picker()."""
    result_key = f"{key_prefix}_sketch_result"
    already = st.session_state.get(result_key)
    if already:
        return already

    with st.expander("Sketch it directly on a map instead", expanded=True):
        st.caption(
            "Click your plot's first corner on the map, then each next corner in order - the "
            "bearing and distance between clicks are worked out for you and filled into the "
            "table below automatically."
        )
        search_key = f"{key_prefix}_sketch_search"
        center_key = f"{key_prefix}_sketch_center"
        query = st.text_input("Search for your area", placeholder="Lekki Phase 1, Lagos", key=search_key)
        if query and st.button("Search", key=f"{key_prefix}_sketch_search_btn"):
            with st.spinner("Searching..."):
                try:
                    result = osm_service.geocode_place(query)
                except osm_service.OSMServiceError as exc:
                    result = None
                    st.error(f"Couldn't search right now: {exc}")
            if result:
                st.session_state[center_key] = (result["lat"], result["lon"])
            else:
                st.warning("No match found - try a different search, or just pan/zoom the map below.")

        # Wide country-level view until a real search narrows it down -
        # same zoom convention pages/investment_analysis.py's own "click on
        # map" step uses for this same NIGERIA_CENTER fallback. Zooming in
        # tight on a rural default coordinate nobody actually searched for
        # just shows sparsely-mapped nothing until the user zooms out anyway.
        searched = center_key in st.session_state
        center_lat, center_lon = st.session_state.get(center_key, NIGERIA_CENTER)
        sketch = map_traverse_sketch(
            center_lat=center_lat, center_lon=center_lon,
            zoom=17 if searched else 6,
            key=f"{key_prefix}_sketch_widget",
        )
        if sketch:
            origin_latlon = (sketch["origin"]["lat"], sketch["origin"]["lon"])
            legs = [(leg["bearing"], leg["distance_m"]) for leg in sketch["legs"]]
            confirmed = {"origin_latlon": origin_latlon, "rows": _rows_from_legs(legs)}
            st.session_state[result_key] = confirmed
            st.success(f"Sketch captured - {len(legs)} boundary leg(s). Review below before computing.")
            return confirmed
    return None


def _render_georeference_picker(polygon_en: list, origin_en: tuple, labels: list, key_prefix: str) -> dict:
    """Fallback for when no real-world origin is known at all - extraction
    found nothing on an uploaded file, and there's no GPS reading to type
    in either. Lets the user search their general area, then drag the
    boundary shape onto the real map until it sits on their actual plot,
    with each corner also individually draggable for fine-tuning against
    satellite imagery - not just the whole shape's position, since a shape
    traced off an unscaled document image (see _render_image_trace_picker())
    is only ever a rough starting guess, not something to trust to the
    centimeter the way a real bearing/distance survey is. See
    utils/shape_georeferencer.py for the drag mechanics.

    Returns {"origin_latlon": (lat, lon), "polygon_en": [...]} once
    confirmed, else None - polygon_en is the FINAL shape after any
    per-vertex adjustment, in local EN meters anchored at the new origin,
    so the caller recomputes area/perimeter/diagonal from THIS rather than
    reusing the pre-adjustment legs it started with. Cached in
    session_state so it survives reruns from unrelated widgets (typing in
    the search box, editing the legs table again) without needing the
    component to keep re-reporting the same value."""
    confirmed_key = f"{key_prefix}_georef_confirmed"
    already = st.session_state.get(confirmed_key)
    if already:
        return already

    with st.expander("Don't know the coordinates? Place your shape on a map instead"):
        st.caption(
            "Your boundary's shape and size are already correct, from the bearings/distances above - "
            "search your general area, then drag the marker until the shape lines up with your actual "
            "plot on the satellite image."
        )
        search_key = f"{key_prefix}_georef_search"
        center_key = f"{key_prefix}_georef_center"
        query = st.text_input("Search for your area", placeholder="Lekki Phase 1, Lagos", key=search_key)
        if query and st.button("Search", key=f"{key_prefix}_georef_search_btn"):
            with st.spinner("Searching..."):
                try:
                    result = osm_service.geocode_place(query)
                except osm_service.OSMServiceError as exc:
                    result = None
                    st.error(f"Couldn't search right now: {exc}")
            if result:
                st.session_state[center_key] = (result["lat"], result["lon"])
            else:
                st.warning("No match found - try a different search, or just pan/zoom the map below.")

        # Wide country-level view until a real search narrows it down - see
        # _render_map_sketch_picker()'s identical comment for why.
        searched = center_key in st.session_state
        center_lat, center_lon = st.session_state.get(center_key, NIGERIA_CENTER)
        # Relative to the origin (vertex 0), not the plan's own local-grid
        # value - the dragged marker itself represents wherever the origin
        # ends up in real life, so only the shape's geometry matters here.
        vertices_relative = [(easting - origin_en[0], northing - origin_en[1]) for easting, northing in polygon_en]
        result = shape_georeferencer(
            vertices_en=vertices_relative,
            labels=labels,
            center_lat=center_lat,
            center_lon=center_lon,
            zoom=16 if searched else 6,
            key=f"{key_prefix}_georef_widget",
        )
        if result and result.get("vertices"):
            vertices_latlon = [(v["lat"], v["lon"]) for v in result["vertices"]]
            origin_latlon = vertices_latlon[0]
            adjusted_polygon_en = [
                traverse.latlon_to_local_en(origin_en, origin_latlon, lat, lon) for lat, lon in vertices_latlon
            ]
            confirmed = {"origin_latlon": origin_latlon, "polygon_en": adjusted_polygon_en}
            st.session_state[confirmed_key] = confirmed
            st.success(f"Position set: {origin_latlon[0]:.6f}, {origin_latlon[1]:.6f}")
            return confirmed
    return None


def _render_click_map(origin_en: tuple, origin_latlon: tuple, points_latlon: list, diagonal: dict, labels: list, map_key: str) -> None:
    """A real map (same folium/streamlit_folium stack as app_home.py's own
    risk-check map) with the computed boundary overlaid, georeferenced from
    origin_latlon - so you're not limited to the one bearing/distance-derived
    diagonal point above; click anywhere (a beacon, a spot inside the plot,
    anything) and read its coordinate off directly, in both WGS84 and the
    same local-grid units as the rest of this page."""
    st.markdown("**Click anywhere on the map to read off that point's coordinate**")
    centroid_lat = sum(lat for lat, _ in points_latlon) / len(points_latlon)
    centroid_lon = sum(lon for _, lon in points_latlon) / len(points_latlon)

    fmap = folium.Map(location=[centroid_lat, centroid_lon], zoom_start=19, tiles=None)
    folium.TileLayer("OpenStreetMap", name="Street").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics",
        name="Satellite",
        show=False,
    ).add_to(fmap)
    Fullscreen(position="topright").add_to(fmap)

    folium.Polygon(
        locations=points_latlon,
        color=theme.ACCENT_LIGHT,
        fill=True,
        fill_color=theme.ACCENT_LIGHT,
        fill_opacity=0.25,
        tooltip="Your plot boundary",
    ).add_to(fmap)
    for i, (lat, lon) in enumerate(points_latlon):
        folium.CircleMarker(
            location=[lat, lon], radius=5,
            color=theme.STATUS["good"], fill=True, fill_color=theme.STATUS["good"], fill_opacity=1,
            tooltip=labels[i] if i < len(labels) else f"point {i + 1}",
        ).add_to(fmap)
    if diagonal.get("point_latlon"):
        folium.Marker(
            location=diagonal["point_latlon"],
            tooltip=f"Diagonal target ({diagonal['target_label']})",
            icon=folium.Icon(color="red", icon="flag"),
        ).add_to(fmap)

    folium.LayerControl(position="topright", collapsed=True).add_to(fmap)
    map_data = st_folium(fmap, width=700, height=420, key=map_key, returned_objects=["last_clicked"])

    clicked = map_data.get("last_clicked") if map_data else None
    if clicked:
        lat, lon = clicked["lat"], clicked["lng"]
        easting, northing = traverse.latlon_to_local_en(origin_en, origin_latlon, lat, lon)
        st.markdown(
            f"""
            <div class="pp-card">
              <div class="pp-card-title">Clicked point</div>
              <p>Coordinate (local grid): <strong>{easting:.3f}mE / {northing:.3f}mN</strong></p>
              <p>Coordinate (WGS84): <strong>{lat:.6f}, {lon:.6f}</strong></p>
            </div>
            """,
            unsafe_allow_html=True,
        )


tab_manual, tab_upload = st.tabs(["Enter Manually", "Upload a Survey Plan"])

with tab_manual:
    st.caption(
        "Type in the boundary's bearing/distance traverse by hand - straight off a paper plan, "
        "no file needed. Same math as automatic extraction."
    )
    col_e, col_n = st.columns(2)
    origin_easting = col_e.number_input(
        "Origin (PL1) Easting (m)", value=0.0, format="%.3f", key="_diag_manual_e",
        help="The plan's own projected coordinate, if you have it. Leave at 0 to use an arbitrary "
        "local grid - the diagonal's distance and bearing come out the same either way.",
    )
    origin_northing = col_n.number_input(
        "Origin (PL1) Northing (m)", value=0.0, format="%.3f", key="_diag_manual_n",
    )

    with st.expander("Optional: real-world GPS starting point (also shows the diagonal's target as latitude/longitude)"):
        col_lat, col_lon = st.columns(2)
        origin_lat = col_lat.number_input("Origin latitude", value=None, format="%.6f", key="_diag_manual_lat")
        origin_lon = col_lon.number_input("Origin longitude", value=None, format="%.6f", key="_diag_manual_lon")

    st.markdown("**Boundary legs**")
    origin_latlon = (origin_lat, origin_lon) if origin_lat is not None and origin_lon is not None else None
    # _DEFAULT_MANUAL_ROWS only seeds the widget the first time this key is
    # created - st.data_editor persists edits under its own key across
    # reruns from then on, same as every other widget in this app.
    _render_legs_editor_and_result(
        _DEFAULT_MANUAL_ROWS,
        editor_key="_diag_manual_editor",
        origin_en=(origin_easting, origin_northing),
        origin_latlon=origin_latlon,
    )

with tab_upload:
    st.caption(
        "Upload a survey plan (PDF or photo) - PlotProof reads its bearings and distances the "
        "same way the main Land Risk Check does, then computes the diagonal below. Review and "
        "edit any row before computing, same as the Manual Entry tab."
    )

    selected_crs_label = st.selectbox(
        "Coordinate system (only needed if auto-detection looks wrong)",
        options=list(CRS_OPTIONS.keys()),
        key="_diag_crs_override",
    )
    forced_epsg = CRS_OPTIONS[selected_crs_label]

    uploaded_file = st.file_uploader(
        "Survey plan (PDF or image)", type=["pdf", "png", "jpg", "jpeg"], key="_diag_uploader",
    )

    if uploaded_file is not None:
        file_key = (uploaded_file.name, uploaded_file.size, forced_epsg)
        if st.session_state.get("_diag_last_upload_key") != file_key:
            st.session_state["_diag_last_upload_key"] = file_key
            with st.spinner("Reading your file..."):
                saved_path = file_handler.save_uploaded_file(uploaded_file)
                file_type = os.path.splitext(uploaded_file.name)[1].lstrip(".").lower()
                # Kept beyond this block (unlike the extraction result
                # below) so the manual-entry fallback further down can
                # still show the file for reference on later reruns, e.g.
                # while the user types into the legs table or drags the
                # georeference picker.
                st.session_state["_diag_upload_saved_path"] = saved_path
                st.session_state["_diag_upload_file_type"] = file_type
                # A new file invalidates any earlier fallback edits/
                # georeferencing done against the previous one.
                st.session_state.pop("_diag_upload_manual_editor", None)
                st.session_state.pop("_diag_upload_manual_editor_georef_confirmed", None)

                use_vision = (
                    file_type in ("png", "jpg", "jpeg")
                    and vision_extract.is_available()
                    and rate_limit.check_burst_limit(CLIENT_ID, BURST_MAX_REQUESTS, BURST_WINDOW_SECONDS)
                    and rate_limit.check_daily_limit(CLIENT_ID, "vision_extract", DAILY_VISION_LIMIT)[0]
                )
                if use_vision:
                    try:
                        _, _, _, legs_info, _ = vision_extract.extract_points_from_image(saved_path, forced_epsg=forced_epsg)
                    except Exception:
                        # Falls back to free OCR below rather than failing
                        # outright - same degradation app_home.py's upload
                        # flow uses (a vision API error/rate-limit shouldn't
                        # block extraction entirely when OCR can still try).
                        traceback.print_exc()
                        use_vision = False

                extraction_failed = False
                if not use_vision:
                    try:
                        extracted_text, _ = file_handler.extract_text_from_file(saved_path)
                        pdf_path = saved_path if file_type == "pdf" and file_handler.storage_backend() == "local" else None
                        _, _, legs_info, _ = coordinates.parse_coordinate_text(
                            extracted_text, pdf_path=pdf_path, forced_epsg=forced_epsg
                        )
                    except Exception:
                        traceback.print_exc()
                        extraction_failed = True

                if extraction_failed:
                    st.session_state["_diag_upload_legs_info"] = None
                    st.error(
                        "Something went wrong reading this file automatically. The technical details "
                        "were logged for review - please try the Manual Entry tab instead."
                    )
                else:
                    st.session_state["_diag_upload_legs_info"] = legs_info
                    # A fresh extraction must win over whatever the data_editor
                    # widget below already has persisted under its key from a
                    # previous file - otherwise the new rows would never show.
                    st.session_state.pop("_diag_upload_editor", None)
                    if legs_info and legs_info.get("rows"):
                        st.success(f"Found {len(legs_info['rows'])} boundary leg(s). Review and edit below before computing.")
                    else:
                        st.warning(
                            "Couldn't read a bearing/distance traverse from this file automatically - "
                            "try the Manual Entry tab instead, or a clearer photo/PDF."
                        )

    legs_info = st.session_state.get("_diag_upload_legs_info")
    saved_path = st.session_state.get("_diag_upload_saved_path")
    if legs_info and legs_info.get("rows"):
        st.markdown("**Boundary legs (auto-read - review before trusting)**")
        _render_legs_editor_and_result(
            legs_info["rows"],
            editor_key="_diag_upload_editor",
            origin_en=legs_info["origin_en"],
            origin_latlon=legs_info["origin_latlon"],
        )
    elif uploaded_file is not None and saved_path:
        # Extraction either failed outright or found no bearing/distance
        # traverse at all - rather than dead-ending, offer three fallbacks:
        # trace the boundary's rough shape by clicking corners on the
        # document's own image/PDF preview, sketch it by clicking corners
        # on a real map instead (gets both shape AND real-world position
        # in one step), or type values by hand off the preview. Only one
        # is active at a time (a radio, not three always-open expanders) -
        # switching clears whatever the other methods had already captured
        # against this same file, below.
        file_type = st.session_state.get("_diag_upload_file_type")
        st.caption("Automatic reading didn't find a bearing/distance traverse in this file.")

        preview_bytes, preview_mime = _get_preview_bytes(saved_path, file_type)

        col_e, col_n = st.columns(2)
        fallback_easting = col_e.number_input(
            "Origin Easting (m) - optional", value=0.0, format="%.3f", key="_diag_upload_fallback_e",
            help="If your document prints its own origin coordinate (e.g. \"517440.880mE, "
            "758074.766mN\"), enter it here - used for the local-grid numbers shown below. "
            "Leave at 0 if you don't have it; it has no effect on where the boundary ends up on "
            "the real map.",
        )
        fallback_northing = col_n.number_input(
            "Origin Northing (m) - optional", value=0.0, format="%.3f", key="_diag_upload_fallback_n",
        )
        fallback_origin_en = (fallback_easting, fallback_northing)

        method = st.radio(
            "How do you want to build the boundary?",
            ["Trace it on the image/PDF", "Sketch it on a real map", "Type it in by hand"],
            key="_diag_upload_fallback_method",
            horizontal=True,
        )
        # Switching methods invalidates whatever a *different* method had
        # already captured against this file - otherwise a stale sketch/
        # trace result could keep winning over a newly-chosen method
        # (_render_*_picker()'s own session_state caching would just
        # return its old answer forever).
        if st.session_state.get("_diag_upload_fallback_last_method") != method:
            st.session_state["_diag_upload_fallback_last_method"] = method
            st.session_state.pop("_diag_upload_manual_editor", None)
            st.session_state.pop("_diag_upload_manual_editor_georef_confirmed", None)
            st.session_state.pop("_diag_upload_manual_editor_sketch_result", None)
            st.session_state.pop("_diag_upload_manual_editor_trace_result", None)

        if method == "Trace it on the image/PDF":
            if preview_bytes:
                trace = _render_image_trace_picker(
                    preview_bytes, preview_mime, fallback_origin_en, key_prefix="_diag_upload_manual_editor"
                )
                if trace:
                    st.markdown("**Boundary legs (from your trace - a rough shape, review before trusting)**")
                    _render_legs_editor_and_result(
                        trace["rows"],
                        editor_key="_diag_upload_manual_editor",
                        origin_en=fallback_origin_en,
                        origin_latlon=None,
                    )
            else:
                st.warning("Couldn't generate a preview of this file to trace on - try Sketch or Type instead.")

        elif method == "Sketch it on a real map":
            sketch = _render_map_sketch_picker(key_prefix="_diag_upload_manual_editor")
            if sketch:
                st.markdown("**Boundary legs (from your sketch - review before trusting)**")
                _render_legs_editor_and_result(
                    sketch["rows"],
                    editor_key="_diag_upload_manual_editor",
                    origin_en=(0.0, 0.0),
                    origin_latlon=sketch["origin_latlon"],
                )

        else:
            st.caption("Use your uploaded file as reference below, and type the values in by hand.")
            if preview_bytes:
                st.image(preview_bytes, caption="Your uploaded file", use_container_width=True)
            _render_legs_editor_and_result(
                _DEFAULT_MANUAL_ROWS,
                editor_key="_diag_upload_manual_editor",
                origin_en=fallback_origin_en,
                origin_latlon=None,
            )
