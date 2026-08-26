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
uploaded document; optional for manual entry), the boundary is also drawn
on a real map (see _render_click_map()) - clicking anywhere on it reads
off that point's coordinate directly, without needing to work out its
bearing/distance from the origin by hand first.

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

from utils import coordinates, crs_utils, file_handler, nav, rate_limit, theme, traverse, vision_extract

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

    area = traverse.shoelace_area(polygon_en)
    perimeter = sum(distance for _, distance in legs)

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

    diagonal = traverse.compute_diagonal(polygon_en, labels=labels)
    if not diagonal:
        st.info("A diagonal needs at least 4 boundary corners - a triangle has no non-adjacent vertex pair.")
        return

    points_latlon = None
    if origin_latlon:
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
    if legs_info and legs_info.get("rows"):
        st.markdown("**Boundary legs (auto-read - review before trusting)**")
        _render_legs_editor_and_result(
            legs_info["rows"],
            editor_key="_diag_upload_editor",
            origin_en=legs_info["origin_en"],
            origin_latlon=legs_info["origin_latlon"],
        )
