"""
PlotProof - Instant Land Boundary Risk Check
Built by Alli Bazeet (@bazzlycodes)
"""

import os
import traceback
import urllib.parse
from datetime import date
from typing import Optional

import folium
import geopandas as gpd
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from utils import crs_utils, file_handler, gis_processing, legal, rate_limit, registry, report_generator, risk_calculator, training_data
from utils import icons, theme, vision_extract
from utils.coordinates import parse_coordinate_text

load_dotenv()

WHATSAPP_LINK = os.environ.get("WHATSAPP_LINK", "https://chat.whatsapp.com/KrMfFgenA5u50QTASfyyro?s=cl&p=a&ilr=1")
CALENDLY_LINK = os.environ.get("CALENDLY_LINK", "https://calendly.com/bazeet4love")
APP_URL = os.environ.get("APP_URL", "https://plotproof.streamlit.app")
TWITTER_LINK = os.environ.get("TWITTER_LINK", "https://x.com/bazzlycodes")

# Daily per-client caps and burst protection - see utils/rate_limit.py.
# "Checks" (Analyze/Compare) are the core paid-adjacent action a user takes;
# vision extraction gets its own, slightly more generous cap since a normal
# single real check can involve a re-upload or a CRS-override re-extraction.
DAILY_CHECK_LIMIT = int(os.environ.get("DAILY_CHECK_LIMIT", "3"))
DAILY_VISION_LIMIT = int(os.environ.get("DAILY_VISION_LIMIT", "5"))
BURST_MAX_REQUESTS = int(os.environ.get("BURST_MAX_REQUESTS", "10"))
BURST_WINDOW_SECONDS = int(os.environ.get("BURST_WINDOW_SECONDS", "60"))


def show_error(message: str) -> None:
    """st.error, with a standing offer to talk to a human when the app can't
    resolve something on its own."""
    st.error(f"{message} Or [contact PlotProof for a consultation]({WHATSAPP_LINK}).")


def show_warning(message: str) -> None:
    """st.warning, with the same contact offer - for partial/uncertain
    results, not just outright failures."""
    st.warning(f"{message} Or [contact PlotProof for a consultation]({WHATSAPP_LINK}).")


def crs_is_uncertain(crs_note: Optional[str]) -> bool:
    """True when the CRS used was a guess (zone stated, datum wasn't) rather
    than something declared, selected, or matched with certainty - see
    crs_utils.resolve_to_wgs84()."""
    return bool(crs_note) and "- assumed" in crs_note


def show_crs_disclaimer() -> None:
    st.warning(
        "The coordinate system for this file couldn't be confirmed with certainty - only the "
        "UTM zone was stated on the plan, not the datum, and guessing wrong can shift every "
        "point by roughly 150m. Please confirm the correct coordinate system yourself using the "
        f"\"Coordinate system\" selector, or have it confirmed by us at "
        f"[@PlotProof]({TWITTER_LINK}) before relying on this result for any transaction or "
        "legal decision."
    )


def check_can_run_check() -> bool:
    """Gate for the core "Analyze My Land" / "Compare Plots" action - the
    literal per-visitor daily cap, plus a burst check so rapid repeated
    clicks can't be used to hammer the server. Shows its own error and
    returns False when blocked; callers should skip the analysis entirely
    in that case."""
    if not rate_limit.check_burst_limit(CLIENT_ID, BURST_MAX_REQUESTS, BURST_WINDOW_SECONDS):
        show_error("Too many requests in a short time. Please wait a minute and try again.")
        return False
    allowed, _ = rate_limit.check_daily_limit(CLIENT_ID, "analyze", DAILY_CHECK_LIMIT)
    if not allowed:
        show_error(
            f"You've reached today's limit of {DAILY_CHECK_LIMIT} land checks per day. "
            "Please try again tomorrow."
        )
        return False
    return True


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

# Resolved once per script run - identifies this visitor for the daily
# check/extraction caps and burst limiter below (see utils/rate_limit.py).
CLIENT_ID = rate_limit.get_client_id()


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


CRS_OPTIONS = {"Auto-detect": None}
CRS_OPTIONS.update({name: epsg for epsg, name in crs_utils.NIGERIA_CRS_CANDIDATES.items()})


# ------------------------------
# SHARED: one document's upload + CRS override + coordinates input.
# Used once for the standard single-plot check, and twice (Plot A / Plot
# B) for the two-plot comparison mode below. Session state and widget
# keys are namespaced by `slot` so the two instances never collide -
# slot="" reuses the original unprefixed keys so the standard flow's
# behavior is unchanged.
# ------------------------------
def render_document_input(
    slot: str,
    upload_step: tuple,
    coords_step: Optional[tuple] = None,
    disabled: bool = False,
) -> dict:
    def k(base: str) -> str:
        return base if not slot else f"{base}_{slot}"

    def extract_and_store(saved_path: str, file_type: str, forced_epsg: Optional[str] = None) -> None:
        """(Re-)runs extraction from the uploaded file and stores the result,
        used both on first upload and whenever the CRS override changes.
        Extraction touches unpredictable third-party file content (PDF
        internals, OCR), so failures here must degrade to manual entry
        rather than crash the app - the full exception is logged
        server-side either way."""
        # Phone photos of survey plans mix horizontal, vertical, and
        # diagonally-angled text that Tesseract's single-block OCR mode
        # reliably mangles (confirmed against real user uploads that OCR
        # read as zero coordinates despite being legible to the eye) -
        # Claude's vision reads these correctly, so prefer it for images
        # when an API key is configured. PDFs already extract well via a
        # real text layer or page-rasterized OCR, so this path is
        # image-only, and a vision-call failure (rate limit, API error)
        # falls back to OCR rather than dropping straight to manual entry.
        # Also gated behind its own daily cap + burst limiter, since this
        # is the one call in the app with a real per-request $ cost - a
        # visitor who hits either limit silently falls back to free OCR
        # rather than being blocked outright (re-uploads/CRS-override
        # re-tries within one real session are normal, so this shouldn't
        # feel like a wall for a legitimate user).
        use_vision = (
            file_type in ("png", "jpg", "jpeg")
            and vision_extract.is_available()
            and rate_limit.check_burst_limit(CLIENT_ID, BURST_MAX_REQUESTS, BURST_WINDOW_SECONDS)
            and rate_limit.check_daily_limit(CLIENT_ID, "vision_extract", DAILY_VISION_LIMIT)[0]
        )
        if use_vision:
            try:
                extracted_points, crs_note, extracted_text = vision_extract.extract_points_from_image(
                    saved_path, forced_epsg=forced_epsg
                )
                extraction_method = "vision"
                pdf_path = None
            except Exception:
                traceback.print_exc()
                use_vision = False

        if not use_vision:
            try:
                extracted_text, extraction_method = file_handler.extract_text_from_file(saved_path)
                # Vector-based boundary reconstruction needs a real local PDF
                # file to open - not applicable to images or Supabase-hosted uploads.
                pdf_path = saved_path if file_type == "pdf" and file_handler.storage_backend() == "local" else None
                extracted_points, crs_note = parse_coordinate_text(extracted_text, pdf_path=pdf_path, forced_epsg=forced_epsg)
            except Exception:
                traceback.print_exc()
                st.session_state[k("_upload_record")] = None
                show_error(
                    "Something went wrong reading this file automatically. The technical details "
                    "were logged for review - in the meantime, please enter coordinates manually below."
                )
                return

        st.session_state[k("_upload_record")] = {
            "source_file_ref": saved_path,
            "pdf_path": pdf_path,
            "file_type": file_type,
            "extraction_method": extraction_method,
            "raw_extracted_text": extracted_text,
            "auto_detected_points": extracted_points,
            "auto_detected_crs_note": crs_note,
        }
        if extracted_points:
            st.session_state[k("coords_text")] = "\n".join(f"{lat}, {lon}" for lat, lon in extracted_points)
            msg = f"Found {len(extracted_points)} coordinate point(s) in your file."
            if crs_note and crs_note != "undetected":
                msg += f" Converted from {crs_note} to WGS84."
            st.success(f"{msg} Review below.")
            if crs_is_uncertain(crs_note):
                show_crs_disclaimer()
        elif crs_note == "undetected":
            show_warning(
                "Found projected coordinates in this file but couldn't confidently match them "
                "to a known Nigerian coordinate system. Please double-check the source document, "
                "or enter WGS84 latitude/longitude manually below."
            )
        else:
            show_warning("Couldn't detect coordinates in this file automatically - please enter them below.")

    step_header(*upload_step)
    uploaded_file = st.file_uploader(
        "Upload Survey Plan (PDF or Image)",
        type=["pdf", "png", "jpg", "jpeg"],
        help="We'll try to read boundary coordinates straight from the file (text or OCR).",
        key=k("file_uploader"),
        disabled=disabled,
    )
    help_improve = st.checkbox(
        "Help improve coordinate extraction",
        value=False,
        key=k("help_improve"),
        disabled=disabled,
        help=(
            "Survey plan formats vary a lot, and PlotProof gets better at reading them over time. "
            "If checked, we save this document's text, the coordinates we auto-detected, and "
            "whatever you confirm/correct below - used only to improve extraction on future "
            "formats, never shared. Leave unchecked if you'd rather not."
        ),
    )

    if uploaded_file is not None and not disabled:
        file_key = (uploaded_file.name, uploaded_file.size)
        if st.session_state.get(k("_last_uploaded_key")) != file_key:
            st.session_state[k("_last_uploaded_key")] = file_key
            st.session_state[k("_crs_override")] = "Auto-detect"
            st.session_state[k("_last_applied_override")] = "Auto-detect"
            with st.spinner("Reading coordinates from your file..."):
                saved_path = file_handler.save_uploaded_file(uploaded_file)
                file_type = os.path.splitext(uploaded_file.name)[1].lstrip(".").lower()
                extract_and_store(saved_path, file_type)

    if coords_step:
        step_header(*coords_step)

    # Rendered before the coordinates box below so that, if this changes,
    # extract_and_store() can update coords_text before that widget is
    # instantiated (Streamlit forbids writing to a widget's session_state
    # key after it's already rendered in the current run) - no st.rerun()
    # needed, the script just continues on and renders the text_area with
    # the fresh value, the same way the initial upload flow already works.
    selected_crs_label = st.selectbox(
        "Coordinate system (only needed if auto-detection looks wrong)",
        options=list(CRS_OPTIONS.keys()),
        key=k("_crs_override"),
        disabled=disabled,
        help=(
            "PlotProof tries to detect this automatically from the document, but a plan that "
            "only states a UTM zone (not the datum) can't always be resolved with certainty. If "
            "the detected system looks wrong, select the correct one here - if you uploaded a "
            "file, coordinates are re-extracted from it using your selection. Doesn't apply if "
            "your coordinates are already plain latitude/longitude - those need no CRS at all."
        ),
    )
    forced_epsg = CRS_OPTIONS[selected_crs_label]
    upload_record = st.session_state.get(k("_upload_record"))
    if upload_record and not disabled and st.session_state.get(k("_last_applied_override")) != selected_crs_label:
        st.session_state[k("_last_applied_override")] = selected_crs_label
        extract_and_store(upload_record["source_file_ref"], upload_record["file_type"], forced_epsg=forced_epsg)

    st.caption("One point per line: latitude, longitude. Add all boundary corners (3+) for an accurate plot outline.")
    coordinates_text = st.text_area(
        "Coordinates",
        key=k("coords_text"),
        placeholder="6.5244, 3.3792\n6.5246, 3.3799\n6.5251, 3.3797",
        height=120,
        label_visibility="collapsed",
        disabled=disabled,
    )

    return {
        "coordinates_text": coordinates_text,
        "forced_epsg": forced_epsg,
        "help_improve": help_improve,
        "upload_record": st.session_state.get(k("_upload_record")),
    }


def resolve_points(inputs: dict) -> tuple:
    """Parses an input dict's coordinates box, reusing the upload-time CRS
    note when the box still holds exactly what was auto-extracted (see the
    comment at the original call site - the box shows converted WGS84
    decimals after upload, which no longer look projected on re-parse)."""
    points, crs_note = parse_coordinate_text(inputs["coordinates_text"], forced_epsg=inputs["forced_epsg"])
    upload_record = inputs["upload_record"]
    if crs_note is None and upload_record and points == upload_record["auto_detected_points"]:
        crs_note = upload_record["auto_detected_crs_note"]
    return points, crs_note


# ------------------------------
# SHARED: results rendering (risk badge, findings, map, PDF). Used for
# both the standard registry-wide check and the two-plot direct
# comparison - `context_note`/`show_registry_features` tune the parts
# that only make sense for one or the other.
# ------------------------------
def render_results(
    result: dict,
    points: list,
    user_gdf,
    neighbors_gdf,
    crs_note: Optional[str],
    step_num: int,
    map_step_num: int,
    show_registry_features: bool = True,
    map_caption: str = "Shows registered plots in the immediate surroundings, not the full registry.",
    use_context_radius: bool = True,
    pdf_neighbor_points: Optional[list] = None,
) -> None:
    if crs_note and crs_note != "undetected":
        st.markdown(
            f"""<div class="pp-pill">{icons.icon("ruler", size=14)} Coordinates converted from
            {crs_note} to WGS84 for analysis.</div>""",
            unsafe_allow_html=True,
        )
        if crs_is_uncertain(crs_note):
            show_crs_disclaimer()

    step_header(step_num, "Risk Assessment")
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

    if show_registry_features:
        registry_count = registry.count()
        coverage_note = (
            f" checked against {registry_count} community-contributed plot(s) plus our sample data"
            if registry_count
            else ""
        )
        st.markdown(
            f"""<div class="pp-pill">{icons.icon("info", size=14)} This result reflects plots on
            record as of {date.today().strftime("%d %b %Y")}{coverage_note}. It isn't permanent -
            if a neighboring plot is added to the registry later, re-running this check could
            surface a different result. Re-check periodically, especially before finalizing a
            transaction.</div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""<div class="pp-pill">{icons.icon("info", size=14)} This compares only the two
            plots you provided, as of {date.today().strftime("%d %b %Y")} - it does not check
            either plot against the shared registry or sample data.</div>""",
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

    step_header(map_step_num, "Map View")
    st.caption(map_caption)
    overlap_refs = {o["plot_ref"] for o in result["overlaps"]}
    proximate_refs = {p["plot_ref"] for p in result["proximate"]}
    user_geom = user_gdf.geometry.iloc[0]
    centroid = user_geom.centroid
    context_gdf = gis_processing.nearby_plots_for_context(user_gdf, neighbors_gdf) if use_context_radius else neighbors_gdf

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

    st_folium(fmap, width=700, height=400, key=f"risk_map_{step_num}")
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

    pdf_neighbor_plots = []
    if pdf_neighbor_points:
        neighbor_ref = neighbors_gdf.iloc[0].get("plot_ref", "Neighboring Plot")
        if neighbor_ref in overlap_refs:
            neighbor_status = "critical"
        elif neighbor_ref in proximate_refs:
            neighbor_status = "warning"
        else:
            neighbor_status = "good"
        pdf_neighbor_plots.append({"label": neighbor_ref, "points": pdf_neighbor_points, "status": neighbor_status})

    pdf_buffer = report_generator.generate_pdf_report(result, points, neighbor_plots=pdf_neighbor_plots)
    st.download_button(
        label="Download PDF Report",
        data=pdf_buffer,
        file_name="PlotProof_Report.pdf",
        mime="application/pdf",
        key=f"download_{step_num}",
    )

    if show_registry_features and user_gdf["source"].iloc[0] == "survey_polygon":
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

    if show_registry_features:
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
# MODE SELECTOR
# ------------------------------
mode = st.radio(
    "What would you like to do?",
    ["Check my land against known plots", "Compare two specific plots"],
    key="_mode",
    help=(
        "\"Check my land\" compares your plot against our sample data and the shared registry. "
        "\"Compare two specific plots\" checks your plot directly against one specific "
        "neighboring plot you provide - useful when you already have (or can get) your "
        "neighbor's survey plan and want a direct answer."
    ),
)

if mode == "Check my land against known plots":
    # ------------------------------
    # SINGLE-PLOT CHECK
    # ------------------------------
    inputs = render_document_input("", (1, "Upload Your Survey Document"), (2, "Confirm or Enter Coordinates"))

    if st.button("Analyze My Land", type="primary"):
        points, crs_note = resolve_points(inputs)
        if not points:
            if crs_note == "undetected":
                show_error(
                    "These look like projected (Easting/Northing) coordinates, but they couldn't "
                    "be confidently matched to a known Nigerian coordinate system. Please enter "
                    "WGS84 latitude/longitude instead."
                )
            else:
                show_error("Please upload a file or enter at least one coordinate.")
        elif not check_can_run_check():
            pass
        else:
            with st.spinner("Analyzing your land boundaries..."):
                neighbors_gdf = _load_neighbors()
                user_gdf = gis_processing.build_user_plot_gdf(points)
                overlap_result = gis_processing.analyze_overlap(user_gdf, neighbors_gdf)
                result = risk_calculator.calculate_risk(
                    points, overlap_result, boundary_is_measured=len(points) >= 3
                )

            upload_record = inputs["upload_record"]
            if inputs["help_improve"] and upload_record:
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

    if "result" in st.session_state:
        render_results(
            st.session_state["result"],
            st.session_state["points"],
            st.session_state["user_gdf"],
            st.session_state["neighbors_gdf"],
            st.session_state.get("crs_note"),
            step_num=3,
            map_step_num=4,
            show_registry_features=True,
        )

else:
    # ------------------------------
    # TWO-PLOT COMPARISON
    # ------------------------------
    st.markdown(
        """
        <div class="pp-card">
          <div class="pp-card-title">Before you compare</div>
          <p>This checks your plot directly against a specific neighboring plot - which means
          uploading or entering <strong>your neighbor's</strong> survey data, not just your own.
          Their survey plan is personal property information, the same as yours, and they need to
          have agreed to it being uploaded and compared here. PlotProof doesn't verify this
          consent independently - you're responsible for having it before continuing.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    neighbor_consent = st.checkbox(
        "I confirm my neighbor has agreed to have their survey plan uploaded and compared, "
        "and understands the result may be shared with me."
    )
    if not neighbor_consent:
        st.caption("Check the box above to enter your neighbor's plot details.")

    inputs_a = render_document_input("a", (1, "Your Plot"))
    inputs_b = render_document_input("b", (2, "Neighboring Plot"), disabled=not neighbor_consent)

    if st.button("Compare Plots", type="primary", disabled=not neighbor_consent):
        points_a, crs_note_a = resolve_points(inputs_a)
        points_b, crs_note_b = resolve_points(inputs_b)
        if not points_a or not points_b:
            show_error("Please provide valid coordinates for both your plot and the neighboring plot.")
        elif not check_can_run_check():
            pass
        else:
            with st.spinner("Comparing the two plots..."):
                user_gdf = gis_processing.build_user_plot_gdf(points_a)
                neighbor_geom_gdf = gis_processing.build_user_plot_gdf(points_b)
                neighbor_gdf = gpd.GeoDataFrame(
                    {"plot_ref": ["Neighboring Plot"], "owner": ["Provided by you"]},
                    geometry=neighbor_geom_gdf.geometry,
                    crs="EPSG:4326",
                )
                overlap_result = gis_processing.analyze_overlap(user_gdf, neighbor_gdf)
                result = risk_calculator.calculate_risk(
                    points_a, overlap_result, boundary_is_measured=len(points_a) >= 3
                )

            for inputs, points in ((inputs_a, points_a), (inputs_b, points_b)):
                upload_record = inputs["upload_record"]
                if inputs["help_improve"] and upload_record:
                    training_data.record_example(
                        source_file_ref=upload_record["source_file_ref"],
                        file_type=upload_record["file_type"],
                        extraction_method=upload_record["extraction_method"],
                        raw_extracted_text=upload_record["raw_extracted_text"],
                        auto_detected_points=upload_record["auto_detected_points"],
                        auto_detected_crs_note=upload_record["auto_detected_crs_note"],
                        user_confirmed_points=points,
                    )

            st.session_state["_compare_result"] = result
            st.session_state["_compare_points"] = points_a
            st.session_state["_compare_neighbor_points"] = points_b
            st.session_state["_compare_crs_note"] = crs_note_a
            st.session_state["_compare_user_gdf"] = user_gdf
            st.session_state["_compare_neighbor_gdf"] = neighbor_gdf

    if "_compare_result" in st.session_state:
        render_results(
            st.session_state["_compare_result"],
            st.session_state["_compare_points"],
            st.session_state["_compare_user_gdf"],
            st.session_state["_compare_neighbor_gdf"],
            st.session_state.get("_compare_crs_note"),
            step_num=3,
            map_step_num=4,
            show_registry_features=False,
            map_caption="Shows your plot against the neighboring plot you provided.",
            use_context_radius=False,
            pdf_neighbor_points=st.session_state.get("_compare_neighbor_points"),
        )

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
