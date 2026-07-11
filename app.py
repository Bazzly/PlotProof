"""
PlotProof - Instant Land Boundary Risk Check
Built by Alli Bazeet (@bazzlycodes)
"""

import os

import folium
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from utils import file_handler, gis_processing, report_generator, risk_calculator
from utils.coordinates import parse_coordinate_text

load_dotenv()

WHATSAPP_LINK = os.environ.get("WHATSAPP_LINK", "https://wa.me/2348064250232")
CALENDLY_LINK = os.environ.get("CALENDLY_LINK", "https://calendly.com/bazeet4love")

st.set_page_config(page_title="PlotProof - Check Your Land Risk", page_icon="🗺️", layout="centered")

st.title("🗺️ PlotProof")
st.subheader("Instant Land Boundary Risk Check")
st.markdown(
    "Upload your survey plan or enter coordinates to get an instant boundary risk "
    "assessment against known neighboring plots."
)


@st.cache_resource
def _load_neighbors():
    return gis_processing.load_neighboring_plots()


# ------------------------------
# UPLOAD SECTION
# ------------------------------
st.header("1. Upload Your Survey Document")

uploaded_file = st.file_uploader(
    "Upload Survey Plan (PDF or Image)",
    type=["pdf", "png", "jpg", "jpeg"],
    help="We'll try to read boundary coordinates straight from the file (text or OCR).",
)

if uploaded_file is not None:
    file_key = (uploaded_file.name, uploaded_file.size)
    if st.session_state.get("_last_uploaded_key") != file_key:
        st.session_state["_last_uploaded_key"] = file_key
        with st.spinner("Reading coordinates from your file..."):
            saved_path = file_handler.save_uploaded_file(uploaded_file)
            st.session_state["_saved_file_path"] = saved_path
            extracted_text = file_handler.extract_text_from_file(saved_path)
            extracted_points, crs_note = parse_coordinate_text(extracted_text)
            if extracted_points:
                st.session_state["coords_text"] = "\n".join(
                    f"{lat}, {lon}" for lat, lon in extracted_points
                )
                msg = f"Found {len(extracted_points)} coordinate point(s) in your file."
                if crs_note and crs_note != "undetected":
                    msg += f" Converted from {crs_note} to WGS84."
                st.success(f"{msg} Review below.")
            elif crs_note == "undetected":
                st.warning(
                    "Found projected coordinates in this file but couldn't confidently match them "
                    "to a known Nigerian coordinate system. Please double-check the source document, "
                    "or enter WGS84 latitude/longitude manually below."
                )
            else:
                st.warning("Couldn't detect coordinates in this file automatically - please enter them below.")

st.header("2. Confirm or Enter Coordinates")
st.caption("One point per line: latitude, longitude. Add all boundary corners (3+) for an accurate plot outline.")
coordinates_text = st.text_area(
    "Coordinates",
    key="coords_text",
    placeholder="6.5244, 3.3792\n6.5246, 3.3799\n6.5251, 3.3797",
    height=120,
    label_visibility="collapsed",
)

# ------------------------------
# ANALYZE
# ------------------------------
if st.button("Analyze My Land", type="primary"):
    points, crs_note = parse_coordinate_text(coordinates_text)
    if not points:
        if crs_note == "undetected":
            st.error(
                "These look like projected (Easting/Northing) coordinates, but they couldn't be "
                "confidently matched to a known Nigerian coordinate system. Please enter WGS84 "
                "latitude/longitude instead."
            )
        else:
            st.error("Please upload a file or enter at least one coordinate.")
    else:
        with st.spinner("Analyzing your land boundaries..."):
            neighbors_gdf = _load_neighbors()
            user_gdf = gis_processing.build_user_plot_gdf(points)
            overlap_result = gis_processing.analyze_overlap(user_gdf, neighbors_gdf)
            result = risk_calculator.calculate_risk(
                points, overlap_result, boundary_is_measured=len(points) >= 3
            )
        st.session_state["result"] = result
        st.session_state["points"] = points
        st.session_state["crs_note"] = crs_note
        st.session_state["user_gdf"] = user_gdf
        st.session_state["neighbors_gdf"] = neighbors_gdf

# ------------------------------
# RESULTS
# ------------------------------
if "result" in st.session_state:
    result = st.session_state["result"]
    points = st.session_state["points"]
    user_gdf = st.session_state["user_gdf"]
    neighbors_gdf = st.session_state["neighbors_gdf"]

    st.success("Analysis Complete!")

    crs_note = st.session_state.get("crs_note")
    if crs_note and crs_note != "undetected":
        st.caption(f"📐 Coordinates converted from {crs_note} to WGS84 for analysis.")

    st.subheader("Risk Assessment")
    risk_level = result["risk_level"]
    if risk_level == "Low":
        st.success(f"**Risk Level: {risk_level}**")
    elif risk_level == "Medium":
        st.warning(f"**Risk Level: {risk_level}**")
    else:
        st.error(f"**Risk Level: {risk_level}**")

    st.subheader("Key Findings")
    for finding in result["findings"]:
        st.write(f"- {finding}")

    st.subheader("Recommendations")
    for rec in result["recommendations"]:
        st.write(f"- {rec}")

    st.subheader("Map View")
    overlap_refs = {o["plot_ref"] for o in result["overlaps"]}
    proximate_refs = {p["plot_ref"] for p in result["proximate"]}
    user_geom = user_gdf.geometry.iloc[0]
    centroid = user_geom.centroid

    fmap = folium.Map(location=[centroid.y, centroid.x], zoom_start=17)
    folium.GeoJson(
        user_gdf.geometry.iloc[0].__geo_interface__,
        name="Your Plot",
        style_function=lambda _: {"color": "#2563eb", "fillColor": "#2563eb", "fillOpacity": 0.3},
    ).add_to(fmap)

    for _, row in neighbors_gdf.iterrows():
        ref = row.get("plot_ref", "unknown")
        color = "#dc2626" if ref in overlap_refs else "#f59e0b" if ref in proximate_refs else "#6b7280"
        folium.GeoJson(
            row.geometry.__geo_interface__,
            name=ref,
            style_function=lambda _, c=color: {"color": c, "fillColor": c, "fillOpacity": 0.25},
            tooltip=f"{ref} - {row.get('owner', 'unknown')}",
        ).add_to(fmap)

    st_folium(fmap, width=700, height=400, key="risk_map")
    st.caption("🔵 Your plot · 🔴 Overlapping plot · 🟠 Nearby plot · ⚪ No conflict")

    pdf_buffer = report_generator.generate_pdf_report(result, points)
    st.download_button(
        label="⬇️ Download PDF Report",
        data=pdf_buffer,
        file_name="PlotProof_Report.pdf",
        mime="application/pdf",
    )

# ------------------------------
# CONSULTATION CTA
# ------------------------------
st.divider()
st.subheader("Need Professional Help?")
st.info(
    "If the report shows any risks or you want a certified surveyor to review your land "
    "properly, book a consultation with me."
)

col1, col2 = st.columns(2)
with col1:
    st.link_button("📅 Book 30-min Consultation", CALENDLY_LINK, use_container_width=True)
with col2:
    st.link_button("💬 Chat on WhatsApp", WHATSAPP_LINK, use_container_width=True)

# ------------------------------
# FOOTER
# ------------------------------
st.divider()
st.caption("Built with ❤️ by Alli Bazeet (@bazzlycodes) | Geospatial Engineer & Full-Stack Developer")
st.caption("Protecting land rights in Africa through technology.")
