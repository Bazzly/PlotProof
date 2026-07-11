"""
PlotProof - Instant Land Boundary Risk Check
Built by Alli Bazeet (@bazzlycodes)
"""

import os
import urllib.parse
from datetime import date

import folium
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from utils import file_handler, gis_processing, legal, registry, report_generator, risk_calculator, training_data
from utils import icons, theme
from utils.coordinates import parse_coordinate_text

load_dotenv()

WHATSAPP_LINK = os.environ.get("WHATSAPP_LINK", "https://chat.whatsapp.com/KrMfFgenA5u50QTASfyyro?s=cl&p=a&ilr=1")
CALENDLY_LINK = os.environ.get("CALENDLY_LINK", "https://calendly.com/bazeet4love")
APP_URL = os.environ.get("APP_URL", "https://plotproof.streamlit.app")

st.set_page_config(page_title="PlotProof - Check Your Land Risk", page_icon="assets/logo.svg", layout="centered")
st.markdown(theme.get_css(), unsafe_allow_html=True)

st.markdown(
    f"""
    <div class="pp-hero">
      <div class="pp-logo">{icons.icon("logo", color="#ffffff", size=24, stroke_width=2.2)}</div>
      <div>
        <h1>PlotProof</h1>
        <p>Instant Land Boundary Risk Check</p>
      </div>
    </div>
    <p class="pp-lede">Upload your survey plan or enter coordinates to get an instant boundary
    risk assessment against known neighboring plots.</p>
    """,
    unsafe_allow_html=True,
)

# ------------------------------
# CONSENT GATE - nothing past this point renders until accepted
# ------------------------------
if not st.session_state.get("_consent_accepted"):
    st.markdown(
        """
        <div class="pp-card">
          <div class="pp-card-title">Before you continue</div>
          <p>PlotProof is an automated preliminary screening tool, not a certified survey or
          legal opinion - always get a licensed surveyor's verification before a property
          transaction. Using the app is optional beyond the core check: extraction-improvement
          and shared-registry features are separately opt-in and off by default. The app uses
          one essential session cookie only - no tracking or advertising cookies, and built-in
          analytics telemetry is disabled.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Read the full Terms of Service"):
        st.markdown(legal.get_terms())
    with st.expander("Read the full Privacy Policy"):
        st.markdown(legal.get_privacy_policy())

    agreed = st.checkbox("I have read and agree to the Terms of Service and Privacy Policy above.")
    if st.button("Agree & Continue", type="primary", disabled=not agreed):
        st.session_state["_consent_accepted"] = True
        st.rerun()
    st.stop()


def step_header(number: int, label: str) -> None:
    st.markdown(
        f"""<div class="pp-step"><span class="pp-step-num">{number}</span><h2>{label}</h2></div>""",
        unsafe_allow_html=True,
    )


def _load_neighbors():
    # Not cached: the shared registry can grow between analyses (this
    # process, or another user's session against the same Supabase
    # backend), and a stale cache would silently hide newly-contributed
    # plots. The read itself is cheap (a small GeoJSON plus a local/DB lookup).
    return gis_processing.load_neighboring_plots()


# ------------------------------
# UPLOAD SECTION
# ------------------------------
step_header(1, "Upload Your Survey Document")

uploaded_file = st.file_uploader(
    "Upload Survey Plan (PDF or Image)",
    type=["pdf", "png", "jpg", "jpeg"],
    help="We'll try to read boundary coordinates straight from the file (text or OCR).",
)

help_improve = st.checkbox(
    "Help improve coordinate extraction",
    value=False,
    help=(
        "Survey plan formats vary a lot, and PlotProof gets better at reading them over time. "
        "If checked, we save this document's text, the coordinates we auto-detected, and whatever "
        "you confirm/correct below - used only to improve extraction on future formats, never shared. "
        "Leave unchecked if you'd rather not."
    ),
)

if uploaded_file is not None:
    file_key = (uploaded_file.name, uploaded_file.size)
    if st.session_state.get("_last_uploaded_key") != file_key:
        st.session_state["_last_uploaded_key"] = file_key
        with st.spinner("Reading coordinates from your file..."):
            saved_path = file_handler.save_uploaded_file(uploaded_file)
            file_type = os.path.splitext(uploaded_file.name)[1].lstrip(".").lower()
            extracted_text, extraction_method = file_handler.extract_text_from_file(saved_path)
            # Vector-based boundary reconstruction needs a real local PDF
            # file to open - not applicable to images or Supabase-hosted uploads.
            pdf_path = saved_path if file_type == "pdf" and file_handler.storage_backend() == "local" else None
            extracted_points, crs_note = parse_coordinate_text(extracted_text, pdf_path=pdf_path)
            st.session_state["_upload_record"] = {
                "source_file_ref": saved_path,
                "file_type": file_type,
                "extraction_method": extraction_method,
                "raw_extracted_text": extracted_text,
                "auto_detected_points": extracted_points,
                "auto_detected_crs_note": crs_note,
            }
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

step_header(2, "Confirm or Enter Coordinates")
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
    # The box shows clean WGS84 decimals after upload (for readability), which
    # no longer looks projected on re-parse - so re-detection legitimately finds
    # nothing here. Reuse the upload-time CRS note when the points are still
    # exactly what was auto-extracted (i.e. the user hasn't retyped them).
    upload_record_for_note = st.session_state.get("_upload_record")
    if crs_note is None and upload_record_for_note and points == upload_record_for_note["auto_detected_points"]:
        crs_note = upload_record_for_note["auto_detected_crs_note"]
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

        upload_record = st.session_state.get("_upload_record")
        if help_improve and upload_record:
            training_data.record_example(
                source_file_ref=upload_record["source_file_ref"],
                file_type=upload_record["file_type"],
                extraction_method=upload_record["extraction_method"],
                raw_extracted_text=upload_record["raw_extracted_text"],
                auto_detected_points=upload_record["auto_detected_points"],
                auto_detected_crs_note=upload_record["auto_detected_crs_note"],
                user_confirmed_points=points,
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

    crs_note = st.session_state.get("crs_note")
    if crs_note and crs_note != "undetected":
        st.markdown(
            f"""<div class="pp-pill">{icons.icon("ruler", size=14)} Coordinates converted from
            {crs_note} to WGS84 for analysis.</div>""",
            unsafe_allow_html=True,
        )

    step_header(3, "Risk Assessment")
    risk_level = result["risk_level"]
    status = theme.RISK_TO_STATUS[risk_level]
    st.markdown(
        f"""
        <div class="pp-badge-risk" style="--pp-status: var(--pp-{status});">
          {icons.icon(theme.RISK_TO_ICON[risk_level], size=22)}
          Risk Level: {risk_level}
        </div>
        """,
        unsafe_allow_html=True,
    )

    registry_count = registry.count()
    coverage_note = (
        f" checked against {registry_count} community-contributed plot(s) plus our sample data"
        if registry_count
        else ""
    )
    st.markdown(
        f"""<div class="pp-pill">{icons.icon("info", size=14)} This result reflects plots on
        record as of {date.today().strftime("%d %b %Y")}{coverage_note}. It isn't permanent -
        if a neighboring plot is added to the registry later, re-running this check could surface
        a different result. Re-check periodically, especially before finalizing a transaction.</div>""",
        unsafe_allow_html=True,
    )

    findings_html = "".join(
        f"<li>{icons.dot('#898781', size=8)}<span>{f}</span></li>" for f in result["findings"]
    )
    rec_html = "".join(
        f"<li>{icons.icon('check-circle', size=14)}<span>{r}</span></li>" for r in result["recommendations"]
    )
    st.markdown(
        f"""
        <div class="pp-card">
          <div class="pp-card-title">Key Findings</div>
          <ul class="pp-list">{findings_html}</ul>
          <div class="pp-card-title" style="margin-top:16px">Recommendations</div>
          <ul class="pp-list">{rec_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    step_header(4, "Map View")
    st.caption("Shows registered plots in the immediate surroundings, not the full registry.")
    overlap_refs = {o["plot_ref"] for o in result["overlaps"]}
    proximate_refs = {p["plot_ref"] for p in result["proximate"]}
    user_geom = user_gdf.geometry.iloc[0]
    centroid = user_geom.centroid
    context_gdf = gis_processing.nearby_plots_for_context(user_gdf, neighbors_gdf)

    fmap = folium.Map(location=[centroid.y, centroid.x], zoom_start=17)
    folium.GeoJson(
        user_gdf.geometry.iloc[0].__geo_interface__,
        name="Your Plot",
        style_function=lambda _: {"color": theme.ACCENT_LIGHT, "fillColor": theme.ACCENT_LIGHT, "fillOpacity": 0.3},
    ).add_to(fmap)

    for _, row in context_gdf.iterrows():
        ref = row.get("plot_ref", "unknown")
        if ref in overlap_refs:
            color = theme.STATUS["critical"]
        elif ref in proximate_refs:
            color = theme.STATUS["warning"]
        else:
            color = theme.STATUS["good"]
        folium.GeoJson(
            row.geometry.__geo_interface__,
            name=ref,
            style_function=lambda _, c=color: {"color": c, "fillColor": c, "fillOpacity": 0.25},
            tooltip=f"{ref} - {row.get('owner', 'unknown')}",
        ).add_to(fmap)

    st_folium(fmap, width=700, height=400, key="risk_map")
    st.markdown(
        f"""
        <div class="pp-legend">
          <span>{icons.dot(theme.ACCENT_LIGHT)} Your plot</span>
          <span>{icons.dot(theme.STATUS['critical'])} Overlapping plot</span>
          <span>{icons.dot(theme.STATUS['warning'])} Nearby plot</span>
          <span>{icons.dot(theme.STATUS['good'])} No conflict</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pdf_buffer = report_generator.generate_pdf_report(result, points)
    st.download_button(
        label="Download PDF Report",
        data=pdf_buffer,
        file_name="PlotProof_Report.pdf",
        mime="application/pdf",
    )

    # ------------------------------
    # SHARED REGISTRY OPT-IN
    # ------------------------------
    if user_gdf["source"].iloc[0] == "survey_polygon":
        added_ref = st.session_state.get("_registry_plot_ref")
        if added_ref:
            st.markdown(
                f"""<div class="pp-pill">{icons.icon("check-circle", size=14)} Added to the
                shared registry (ref: {added_ref}). Thank you for helping keep future checks
                in this area accurate.</div>""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("<div class='pp-card' style='margin-top:24px'>", unsafe_allow_html=True)
            st.markdown(
                f"""<div class="pp-card-title">{icons.icon("users", size=16)} Add This Plot to the Shared Registry</div>""",
                unsafe_allow_html=True,
            )
            st.markdown(
                "Only the boundary shape is stored - no name, address, or document, just the "
                "outline and a generated reference. Once added, future uploads near this location "
                "get checked against it too, the same way yours was just checked against others. "
                "This is separate from the extraction option above, and is permanent once added - "
                "contact me via WhatsApp below if you'd like a contributed plot removed."
            )
            add_to_registry = st.checkbox("Add my plot's boundary to the shared registry", value=False)
            st.markdown("</div>", unsafe_allow_html=True)
            if add_to_registry:
                st.session_state["_registry_plot_ref"] = registry.add_plot(points)
                st.rerun()

    # ------------------------------
    # VIRAL SHARING CTA
    # ------------------------------
    if risk_level == "Low":
        share_text = (
            "No boundary conflicts found on my land with PlotProof - but that's only because "
            "my neighbors haven't checked yet either. The more plots on record, the safer "
            "everyone's boundary check becomes. Check yours free:"
        )
    else:
        share_text = (
            f"PlotProof flagged a {risk_level.lower()} boundary risk on my land - a free tool "
            "that checks for overlapping plots. Worth checking yours too, especially if we're neighbors:"
        )
    whatsapp_share_link = f"https://wa.me/?text={urllib.parse.quote(share_text + ' ' + APP_URL)}"
    st.markdown(
        f"""
        <div class="pp-card">
          <div class="pp-card-title">{icons.icon("share", size=16)} Help Make Everyone's Check More Accurate</div>
          <p>{share_text}</p>
          <div class="pp-cta-row">
            <a class="pp-cta pp-cta--solid" href="{whatsapp_share_link}" target="_blank" rel="noopener">
              {icons.icon("chat", color="#ffffff", size=18)} Share on WhatsApp
            </a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.code(APP_URL, language=None)

# ------------------------------
# CONSULTATION CTA
# ------------------------------
st.markdown(
    f"""
    <div class="pp-card" style="margin-top:32px">
      <div class="pp-card-title">Need Professional Help?</div>
      <p>If the report shows any risks or you want a certified surveyor to review your land
      properly, book a consultation with me.</p>
      <div class="pp-cta-row">
        <a class="pp-cta pp-cta--solid" href="{CALENDLY_LINK}" target="_blank" rel="noopener">
          {icons.icon("calendar", color="#ffffff", size=18)} Book 30-min Consultation
        </a>
        <a class="pp-cta pp-cta--outline" href="{WHATSAPP_LINK}" target="_blank" rel="noopener">
          {icons.icon("chat", size=18)} Chat on WhatsApp
        </a>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------
# FOOTER
# ------------------------------
st.markdown(
    f"""
    <div class="pp-footer">
      <div>Built with {icons.icon("heart", color=theme.STATUS["critical"], size=14)}
      by Alli Bazeet (@bazzlycodes) | Geospatial Engineer &amp; Full-Stack Developer</div>
      <div>Protecting land rights in Africa through technology.</div>
    </div>
    """,
    unsafe_allow_html=True,
)
with st.expander("Terms of Service & Privacy Policy"):
    st.markdown(legal.get_terms())
    st.divider()
    st.markdown(legal.get_privacy_policy())
