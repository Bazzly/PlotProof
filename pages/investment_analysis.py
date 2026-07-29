"""
Investment Analysis - pick a location (search by place name, enter
coordinates, or click a map), pick a radius, and get an investment report
built from real OpenStreetMap data (roads, amenities, land use, buildings)
plus an AI narrative grounded in those real stats. See utils/osm_service.py
and utils/investment_analysis.py's module docstrings for exactly what's
real data vs. AI reasoning, and utils/investment_analysis.py's docstring
for why the price/sqm estimate is shown despite having no real transaction
data behind it (rendered as a prominent warning, never a plain number).

Deliberately excludes anything this app has no real data source for:
satellite/drone imagery, flood/elevation/environmental analysis, real
population/road-quality/climate datasets, async job queues (a single
analysis is a few seconds of work, run synchronously behind a spinner).

A 4-step wizard (utils/wizard.py, same component app_home.py's flows use):
Choose Location -> Select Radius -> Run Analysis -> Results. A completed
result can be saved (utils/investment_reports.py) for a real, working
"Shareable Report Link" - this page also renders that saved, read-only
view when loaded with ?report=<id> in the URL.

Broken out to its own page (not the sidebar/inline on the main flow) for
the same reason as pages/about.py and pages/faq.py - keeps the core land
boundary check focused on its own thing; reachable from the sidebar
(utils/nav.py) on every page.
"""

import os
import traceback
from typing import Optional

import folium
import streamlit as st
from dotenv import load_dotenv
from folium.plugins import Fullscreen, HeatMap, MeasureControl
from streamlit_folium import st_folium

from utils import coordinates, icons, investment_analysis, investment_fallback_data, investment_reports, nav, osm_service, rate_limit, report_generator, theme
from utils.wizard import render_wizard, step_header

load_dotenv()

st.set_page_config(page_title="Investment Analysis - PlotProof", page_icon="assets/logo.svg", layout="centered")
st.markdown(theme.get_css(), unsafe_allow_html=True)
nav.render_sidebar()
nav.render_floating_chat()

APP_URL = os.environ.get("APP_URL", "https://plotproof.streamlit.app")
DAILY_INVESTMENT_LIMIT = int(os.environ.get("DAILY_INVESTMENT_LIMIT", "5"))
BURST_MAX_REQUESTS = int(os.environ.get("BURST_MAX_REQUESTS", "10"))
BURST_WINDOW_SECONDS = int(os.environ.get("BURST_WINDOW_SECONDS", "60"))
CLIENT_ID = rate_limit.get_client_id()

RADIUS_OPTIONS = [100, 250, 500, 1000]
NIGERIA_CENTER = [9.0820, 8.6753]

AMENITY_MAP_COLORS = {
    "Schools": "#2b6cb0", "Hospitals": "#d03b3b", "Police Stations": "#1a1a2e",
    "Markets": "#e3ad4b", "Banks": "#104f29", "Fuel Stations": "#7c2d12",
    "Shopping Centres": "#805ad5", "Bus Stops": "#0ca30c", "Religious Centres": "#b83280",
    "Restaurants": "#dd6b20", "Government Offices": "#2c5282", "Hotels": "#0987a0",
}


def _fetch_features_with_fallback(location: dict, radius_m: int) -> tuple:
    """Tries live OpenStreetMap first, then blends in any admin-uploaded
    dataset covering this location (utils/investment_fallback_data.py) -
    which overrides live results per category where it has data, and is
    the only source used for a category if OSM failed outright. Returns
    (merged_features, osm_ok, used_fallback) - merged_features is always
    a valid dict (never None); callers should only treat this as a real
    failure when osm_ok is False AND every category in merged_features
    is still empty (i.e. nothing - live or admin - was available)."""
    try:
        raw = osm_service.fetch_nearby_features(location["lat"], location["lon"], radius_m)
        osm_ok = True
    except osm_service.OSMServiceError:
        traceback.print_exc()
        raw = None
        osm_ok = False

    dataset = investment_fallback_data.find_covering_dataset(location["lat"], location["lon"])
    merged = investment_fallback_data.apply_fallback(raw, location["lat"], location["lon"])
    return merged, osm_ok, dataset is not None


def _render_score_card(score: dict) -> None:
    status = investment_analysis.score_status(score["overall_score"])
    st.markdown(
        f"""
        <div class="pp-score-card" style="--pp-status: var(--pp-{status});">
          <div class="pp-score-number">{score['overall_score']}<span>/100</span></div>
          <div class="pp-score-verdict">{score['verdict']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_subscore_bars(score: dict) -> None:
    rows = [
        ("Accessibility", score["accessibility"]["score"], f"{score['accessibility']['rating']} - {score['accessibility']['road_count']} roads found"),
        ("Development", score["development"]["score"], f"{score['development']['building_count']} buildings (~{score['development']['density_per_km2']}/km²)"),
        ("Amenities", score["amenities"]["score"], f"{score['amenities']['categories_present']}/{len(investment_analysis.ALL_AMENITY_CATEGORIES)} categories nearby"),
        ("Land Availability", score["availability"]["score"], f"~{score['availability']['undeveloped_percentage']}% undeveloped (of tagged land)"),
        ("Growth Potential", score["growth"]["score"], "Blends current development with room to grow"),
    ]
    for label, value, detail in rows:
        status = investment_analysis.score_status(value)
        st.markdown(
            f"""
            <div class="pp-subscore" style="--pp-status: var(--pp-{status});">
              <div class="pp-subscore-row"><span>{label}</span><span>{value}/100</span></div>
              <div class="pp-subscore-track"><div class="pp-subscore-fill" style="width:{value}%"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(detail)


def _render_map(location: dict, radius_m: int, features: dict) -> None:
    fmap = folium.Map(location=[location["lat"], location["lon"]], zoom_start=16, tiles=None)
    folium.TileLayer("OpenStreetMap", name="Street").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics",
        name="Satellite",
        show=False,
    ).add_to(fmap)
    Fullscreen(position="topright").add_to(fmap)
    MeasureControl(position="bottomleft", primary_length_unit="meters", primary_area_unit="sqmeters").add_to(fmap)

    folium.Circle(
        location=[location["lat"], location["lon"]],
        radius=radius_m,
        color=theme.ACCENT_LIGHT,
        fill=True,
        fill_opacity=0.08,
        name=f"{radius_m}m radius",
    ).add_to(fmap)
    folium.Marker(
        [location["lat"], location["lon"]],
        tooltip=location.get("display_name", "Selected location"),
        icon=folium.Icon(color="green", icon="map-pin", prefix="fa"),
    ).add_to(fmap)

    roads_group = folium.FeatureGroup(name="Roads", show=True)
    for road in features["roads"]:
        if len(road["geometry"]) >= 2:
            folium.PolyLine(road["geometry"], color="#555555", weight=2, opacity=0.7).add_to(roads_group)
    roads_group.add_to(fmap)

    landuse_group = folium.FeatureGroup(name="Land Use", show=False)
    for parcel in features["landuse"]:
        if len(parcel["geometry"]) >= 3:
            folium.Polygon(
                parcel["geometry"], color="#e3ad4b", weight=1, fill=True, fill_opacity=0.2,
                tooltip=parcel["tags"].get("landuse"),
            ).add_to(landuse_group)
    landuse_group.add_to(fmap)

    amenities_group = folium.FeatureGroup(name="Amenities", show=True)
    for feature in features["amenities"]:
        if feature.get("lat") is None:
            continue
        category = osm_service.amenity_category(feature["tags"]) or "Other"
        color = AMENITY_MAP_COLORS.get(category, "#555555")
        name = feature["tags"].get("name", category)
        folium.CircleMarker(
            [feature["lat"], feature["lon"]], radius=5, color=color, fill=True, fill_opacity=0.9,
            tooltip=f"{name} ({category})",
        ).add_to(amenities_group)
    amenities_group.add_to(fmap)

    building_points = [[b["lat"], b["lon"]] for b in features["buildings"] if b.get("lat") is not None]
    if building_points:
        heat_group = folium.FeatureGroup(name="Development Density", show=False)
        HeatMap(building_points, radius=14, blur=18, name="Development Density").add_to(heat_group)
        heat_group.add_to(fmap)

    folium.LayerControl(position="topright", collapsed=True).add_to(fmap)
    st_folium(fmap, width=700, height=420, key="_invest_result_map", returned_objects=[])


def _render_dashboard(location: dict, radius_m: int, score: dict, narrative: Optional[dict], report_id: Optional[str] = None, read_only: bool = False, used_fallback: bool = False) -> None:
    place_label = location.get("display_name") or f"{location['lat']:.5f}, {location['lon']:.5f}"
    st.markdown(
        f'<div class="pp-pill">{icons.icon("map-pin", size=14)} {place_label} - {radius_m}m radius</div>',
        unsafe_allow_html=True,
    )
    if used_fallback:
        st.caption("📍 Enhanced with admin-verified local data for this area (see the admin portal's Investment Fallback Data tab).")

    step_header(None, "Investment Score")
    _render_score_card(score)
    _render_subscore_bars(score)

    if narrative:
        step_header(None, "Summary")
        st.markdown(f'<div class="pp-card"><p>{narrative["summary"]}</p></div>', unsafe_allow_html=True)

        price = narrative["price_estimate"]
        low, high = price.get("per_sqm_low"), price.get("per_sqm_high")
        price_line = f"₦{low:,.0f} - ₦{high:,.0f} per m²" if low is not None and high is not None else "Not available"
        st.markdown(
            f"""
            <div class="pp-price-card">
              <div class="pp-card-title">Estimated Price Potential</div>
              <div class="pp-price-value">{price_line}</div>
              <p>{price.get('reasoning', '')}</p>
              <div class="pp-price-caveat">⚠ {price.get('caveat', 'AI estimate only - not based on real transaction data. Always confirm with a licensed real estate valuer.')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        step_header(None, "Recommendations")
        rec_html = "".join(f"<li>{icons.icon('check-circle', size=14)}{rec}</li>" for rec in narrative["recommendations"])
        st.markdown(f'<div class="pp-card"><ul class="pp-list">{rec_html}</ul></div>', unsafe_allow_html=True)
    else:
        st.warning(
            "The AI summary wasn't available when this report was generated - the scores above "
            "are still real, computed data from OpenStreetMap. Try again shortly for the narrative "
            "and price estimate."
        )

    step_header(None, "Nearby Amenities")
    amenity_lines = [
        f"**{b['category']}**: {b['count']} found" + (f", nearest {b['nearest_m']}m away" if b["nearest_m"] is not None else "")
        for b in score["amenities"]["breakdown"] if b["count"] > 0
    ]
    if amenity_lines:
        for line in amenity_lines:
            st.markdown(f"- {line}")
    else:
        st.caption("No tracked amenities found within this radius in OpenStreetMap.")

    if score["land_use"]["breakdown"]:
        step_header(None, "Land Use Mix")
        st.caption(f"Of the {score['land_use']['tag_coverage_percentage']}% of this area that has land-use data tagged in OpenStreetMap:")
        st.bar_chart({b["category"]: b["percentage"] for b in score["land_use"]["breakdown"]}, horizontal=True)

    step_header(None, "Map")
    st.caption("Toggle layers (top-right) to show roads, land use, amenities, or development density.")
    map_features, _, _ = _fetch_features_with_fallback(location, radius_m)
    if any(map_features.values()):
        _render_map(location, radius_m, map_features)
    else:
        st.info("Map data temporarily unavailable.")

    if not read_only:
        step_header(None, "Download & Share")
        if report_id is None:
            report_id = investment_reports.save_report(location, radius_m, score, narrative, used_fallback=used_fallback)
            st.session_state["_invest_report_id"] = report_id
        share_url = f"{APP_URL}/investment-analysis?report={report_id}"

        pdf = report_generator.generate_investment_pdf_report(location, radius_m, score, narrative, share_url=share_url)
        csv_buf = report_generator.generate_investment_csv(location, radius_m, score)
        geojson_buf = report_generator.generate_investment_geojson(location, radius_m, score)

        col_pdf, col_csv, col_geo = st.columns(3)
        col_pdf.download_button("📄 PDF Report", data=pdf, file_name="investment_report.pdf", mime="application/pdf", use_container_width=True)
        col_csv.download_button("📊 CSV Summary", data=csv_buf, file_name="investment_summary.csv", mime="text/csv", use_container_width=True)
        col_geo.download_button("🗺 GeoJSON", data=geojson_buf, file_name="investment_location.geojson", mime="application/geo+json", use_container_width=True)

        st.text_input("Shareable report link", value=share_url, disabled=True, key="_invest_share_url")
        st.caption("Anyone with this link can view this report (read-only) - no login required.")

        if st.button("Start a new analysis"):
            for key in ["_wiz_invest", "_invest_location", "_invest_radius", "_invest_score", "_invest_narrative", "_invest_report_id"]:
                st.session_state.pop(key, None)
            st.rerun()


# ------------------------------
# Shared, read-only view - ?report=<id>. Checked before the wizard so a
# fresh visitor with a shared link sees the report immediately. No
# st.stop() anywhere on this page (including here) - a hidden-nav page
# hitting st.stop() on a cold direct load has caused a real client-side
# routing bug elsewhere in this app (see pages/admin_review.py's history),
# so this uses if/else instead.
# ------------------------------
_shared_report_id = st.query_params.get("report")
_shared_report = investment_reports.get_report(_shared_report_id) if _shared_report_id else None

st.markdown(
    f"""
    <div class="pp-hero">
      <div class="pp-logo">{icons.icon("trending-up", color="#ffffff", size=24, stroke_width=2.2)}</div>
      <div>
        <h1>Investment Analysis</h1>
        <p>Pick a location and get an instant investment-potential report, built from real
        OpenStreetMap data - roads, amenities, land use, and development density - plus an
        AI narrative grounded in those real numbers.</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if _shared_report_id and not _shared_report:
    st.warning("This report link doesn't exist or has expired.")

if _shared_report:
    _render_dashboard(
        _shared_report["location"], _shared_report["radius_m"], _shared_report["score"],
        _shared_report.get("narrative"), report_id=_shared_report["id"], read_only=True,
        used_fallback=_shared_report.get("used_fallback", False),
    )
    st.page_link("app_home.py", label="← Back to the land risk check", icon="🧭")
else:
    step = st.session_state.get("_wiz_invest", 1)
    render_wizard(["Choose Location", "Select Radius", "Run Analysis", "Results"], min(step, 4))

    if step == 1:
        step_header(None, "Choose a Location")
        method = st.radio(
            "How do you want to pick a location?",
            ["Search by place name", "Enter coordinates", "Click on map"],
            key="_invest_location_method",
        )

        if method == "Search by place name":
            query = st.text_input("Place name or address", placeholder="Lekki Phase 1, Lagos")
            if query and st.button("Search"):
                with st.spinner("Searching..."):
                    try:
                        result = osm_service.geocode_place(query)
                    except osm_service.OSMServiceError as exc:
                        result = None
                        st.error(f"Couldn't search right now: {exc}")
                if result:
                    st.session_state["_invest_location"] = result
                else:
                    st.warning("No match found - try a different search, or enter coordinates directly.")

        elif method == "Enter coordinates":
            col1, col2 = st.columns(2)
            lat = col1.number_input("Latitude", value=6.5244, format="%.6f")
            lon = col2.number_input("Longitude", value=3.3792, format="%.6f")
            if coordinates.is_valid_latlon(lat, lon):
                st.session_state["_invest_location"] = {"lat": lat, "lon": lon, "display_name": f"{lat:.5f}, {lon:.5f}"}
            else:
                st.error("Enter a valid latitude (-90 to 90) and longitude (-180 to 180).")

        else:
            st.caption("Click anywhere on the map to select that location.")
            pick_map = folium.Map(location=NIGERIA_CENTER, zoom_start=6)
            clicked = st_folium(pick_map, width=700, height=400, key="_invest_pick_map")
            if clicked and clicked.get("last_clicked"):
                lat, lon = clicked["last_clicked"]["lat"], clicked["last_clicked"]["lng"]
                st.session_state["_invest_location"] = {"lat": lat, "lon": lon, "display_name": f"{lat:.5f}, {lon:.5f}"}

        current = st.session_state.get("_invest_location")
        if current:
            st.markdown(
                f'<div class="pp-pill">{icons.icon("map-pin", size=14)} Selected: {current["display_name"]}</div>',
                unsafe_allow_html=True,
            )
            if st.button("Continue to Radius", type="primary"):
                st.session_state["_wiz_invest"] = 2
                st.rerun()

    elif step == 2:
        location = st.session_state.get("_invest_location")
        if not location:
            st.session_state["_wiz_invest"] = 1
            st.rerun()
        else:
            step_header(None, "Select Analysis Radius")
            st.markdown(
                f'<div class="pp-pill">{icons.icon("map-pin", size=14)} {location["display_name"]}</div>',
                unsafe_allow_html=True,
            )
            radius_choice = st.radio(
                "Radius", [f"{r}m" for r in RADIUS_OPTIONS] + ["Custom"], horizontal=True, key="_invest_radius_choice"
            )
            if radius_choice == "Custom":
                radius_m = st.slider("Custom radius (meters)", min_value=50, max_value=osm_service.MAX_RADIUS_M, value=500, step=50)
            else:
                radius_m = int(radius_choice.rstrip("m"))
            st.session_state["_invest_radius"] = radius_m

            col_back, col_next = st.columns([1, 2])
            with col_back:
                if st.button("← Back"):
                    st.session_state["_wiz_invest"] = 1
                    st.rerun()
            with col_next:
                if st.button("Run AI Analysis", type="primary"):
                    st.session_state["_wiz_invest"] = 3
                    st.rerun()

    elif step == 3:
        location = st.session_state.get("_invest_location")
        radius_m = st.session_state.get("_invest_radius", 500)
        if not location:
            st.session_state["_wiz_invest"] = 1
            st.rerun()
        else:
            step_header(None, "Running Analysis")
            if not rate_limit.check_burst_limit(CLIENT_ID, BURST_MAX_REQUESTS, BURST_WINDOW_SECONDS):
                st.error("Too many requests in a short time. Please wait a minute and try again.")
                if st.button("← Back"):
                    st.session_state["_wiz_invest"] = 2
                    st.rerun()
            elif not rate_limit.check_daily_limit(CLIENT_ID, "investment_analysis", DAILY_INVESTMENT_LIMIT)[0]:
                st.error(f"You've reached today's limit of {DAILY_INVESTMENT_LIMIT} investment analyses per day. Please try again tomorrow.")
                if st.button("← Back"):
                    st.session_state["_wiz_invest"] = 2
                    st.rerun()
            else:
                with st.spinner("Fetching real map data from OpenStreetMap..."):
                    features, osm_ok, used_fallback = _fetch_features_with_fallback(location, radius_m)

                if not osm_ok and not any(features.values()):
                    st.error("Couldn't fetch map data right now - OpenStreetMap's service may be busy. Please try again in a moment.")
                    if st.button("← Back"):
                        st.session_state["_wiz_invest"] = 2
                        st.rerun()
                else:
                    with st.spinner("Computing investment score..."):
                        score = investment_analysis.compute_investment_score(location, radius_m, features)

                    narrative = None
                    try:
                        with st.spinner("Generating AI summary..."):
                            narrative = investment_analysis.generate_investment_narrative(location, radius_m, score)
                    except Exception:
                        traceback.print_exc()
                        narrative = None

                    st.session_state["_invest_score"] = score
                    st.session_state["_invest_narrative"] = narrative
                    # Carried through to the results page (step 4) rather
                    # than shown here - this block always immediately
                    # reruns into step 4, so a message shown only here
                    # would flash for a single frame and never actually
                    # be seen.
                    st.session_state["_invest_used_fallback"] = used_fallback
                    st.session_state["_invest_osm_ok"] = osm_ok
                    st.session_state["_wiz_invest"] = 4
                    st.rerun()

    elif step == 4:
        location = st.session_state.get("_invest_location")
        radius_m = st.session_state.get("_invest_radius", 500)
        score = st.session_state.get("_invest_score")
        narrative = st.session_state.get("_invest_narrative")
        if not (location and score):
            st.session_state["_wiz_invest"] = 1
            st.rerun()
        else:
            step_header(None, "Results")
            _render_dashboard(
                location, radius_m, score, narrative,
                report_id=st.session_state.get("_invest_report_id"),
                used_fallback=st.session_state.get("_invest_used_fallback", False),
            )
