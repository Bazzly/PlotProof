"""
PlotProof - Instant Land Boundary Risk Check
Built by Alli Bazeet (@bazzlycodes)
"""

import os
import re
import time
import traceback
import urllib.parse
from datetime import date
from typing import Optional

import folium
import geopandas as gpd
import streamlit as st
import streamlit_sortables
from dotenv import load_dotenv
from folium.plugins import Fullscreen, MeasureControl
from streamlit_folium import st_folium

from utils import assistant, crs_utils, document_metadata, file_handler, gis_processing, nav, rate_limit, registry, report_generator, risk_calculator, training_data
from utils import icons, theme, traverse, vision_extract
from utils.coordinates import parse_coordinate_text
from utils.wizard import render_wizard, step_header

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
DAILY_ASSISTANT_LIMIT = int(os.environ.get("DAILY_ASSISTANT_LIMIT", "10"))
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


def show_crs_disclaimer() -> None:
    st.warning(
        "The coordinate system for this file couldn't be confirmed with certainty - only the "
        "UTM zone was stated on the plan, not the datum, and guessing wrong can shift every "
        "point by roughly 150m. Please confirm the correct coordinate system yourself using the "
        f"\"Coordinate system\" selector, or have it confirmed by us at "
        f"[@PlotProof]({TWITTER_LINK}) before relying on this result for any transaction or "
        "legal decision."
    )


def show_traverse_order_disclaimer() -> None:
    st.warning(
        "This boundary's beacon order or direction doesn't match the standard survey convention "
        "(starting at the northernmost beacon, proceeding clockwise). It could be a legitimate "
        "exception, or the beacons may have been read in the wrong order or direction, which "
        "would produce a rotated or mirrored shape without changing any individual bearing or "
        "distance value. Please check the beacon order in the table below against your original "
        f"document, or have it confirmed by us at [@PlotProof]({TWITTER_LINK}) before relying on "
        "this result for any transaction or legal decision."
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
nav.render_sidebar()
nav.render_floating_chat()

# ------------------------------
# LANDING PAGE - the first thing a visitor sees, before the tool itself.
# Gives the pitch (what this does, why it's trustworthy, one clear next
# step) instead of dropping them straight into an upload widget with no
# context. Sticky like the consent gate below it - once dismissed via the
# CTA, it stays dismissed for the rest of the session.
# ------------------------------
if not st.session_state.get("_entered_app"):
    with st.container(key="pp_stage_landing"):
        st.markdown(
            f"""
            <div class="pp-landing-hero">
              <div class="pp-logo">{icons.icon("logo", color="#ffffff", size=30, stroke_width=2.2)}</div>
              <h1 class="pp-landing-title">Know your land is safe<br>before you build on it.</h1>
              <p class="pp-landing-sub">Upload your survey plan or enter coordinates and get an
              instant boundary risk check against known neighboring plots - catching overlaps
              and boundary disputes before they become a legal problem.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="pp-landing-steps">
              <div class="pp-landing-step">
                <span class="pp-step-num">1</span>
                <h3>Upload or enter coordinates</h3>
                <p>A survey plan (PDF or photo), or paste boundary coordinates by hand - old,
                hand-surveyed plans work too.</p>
              </div>
              <div class="pp-landing-step">
                <span class="pp-step-num">2</span>
                <h3>We check the boundary</h3>
                <p>Your plot is compared against known neighboring plots for overlaps and
                boundary risks.</p>
              </div>
              <div class="pp-landing-step">
                <span class="pp-step-num">3</span>
                <h3>Get an instant risk report</h3>
                <p>A clear Low/Medium/High result with a map and a downloadable PDF report.</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <ul class="pp-list">
              <li>{check} No signup required</li>
              <li>{check} Works with old, hand-surveyed plans with no beacon numbers</li>
              <li>{check} Your data isn't shared without your consent</li>
            </ul>
            """.format(check=icons.icon("check-circle", color=theme.STATUS["good"], size=16)),
            unsafe_allow_html=True,
        )
        with st.container(key="pp_landing_cta"):
            if st.button("Check My Land Now", type="primary"):
                st.session_state["_entered_app"] = True
                st.rerun()
        st.markdown(
            '<p class="pp-landing-note">Takes under a minute. An automated preliminary '
            "screening tool, not a certified survey - always confirm with a licensed surveyor "
            "before a transaction.</p>",
            unsafe_allow_html=True,
        )
    st.stop()

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
    st.page_link("pages/about.py", label="Read the full Terms of Service & Privacy Policy", icon="📄")

    agreed = st.checkbox("I have read and agree to the Terms of Service and Privacy Policy above.")
    if st.button("Agree & Continue", type="primary", disabled=not agreed):
        st.session_state["_consent_accepted"] = True
        st.rerun()
    st.stop()

# Resolved once per script run - identifies this visitor for the daily
# check/extraction caps and burst limiter below (see utils/rate_limit.py).
CLIENT_ID = rate_limit.get_client_id()


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
                extracted_points, crs_note, extracted_text, legs_info, document_info = vision_extract.extract_points_from_image(
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
                extracted_points, crs_note, legs_info, document_info = parse_coordinate_text(
                    extracted_text, pdf_path=pdf_path, forced_epsg=forced_epsg
                )
            except Exception:
                traceback.print_exc()
                st.session_state[k("_upload_record")] = None
                show_error(
                    "Something went wrong reading this file automatically. The technical details "
                    "were logged for review - in the meantime, please enter coordinates manually below."
                )
                return

        # A fresh extraction invalidates any bearing/distance edits made
        # against the *previous* file/CRS - otherwise the legs editor below
        # would compare new rows against a stale prior edit and silently
        # skip re-applying them.
        st.session_state.pop(k("_last_applied_legs"), None)
        st.session_state[k("_upload_record")] = {
            "source_file_ref": saved_path,
            "pdf_path": pdf_path,
            "file_type": file_type,
            "extraction_method": extraction_method,
            "raw_extracted_text": extracted_text,
            "auto_detected_points": extracted_points,
            "auto_detected_crs_note": crs_note,
            "legs_info": legs_info,
            "document_info": document_info,
        }
        if extracted_points:
            st.session_state[k("coords_text")] = "\n".join(f"{lat}, {lon}" for lat, lon in extracted_points)
            msg = f"Found {len(extracted_points)} coordinate point(s) in your file."
            if crs_note and crs_note != "undetected":
                msg += f" Converted from {crs_note} to WGS84."
            st.success(f"{msg} Review below.")
            if crs_utils.crs_is_uncertain(crs_note):
                show_crs_disclaimer()
            if traverse.traverse_order_uncertain(crs_note):
                show_traverse_order_disclaimer()
        elif crs_note == "undetected":
            show_warning(
                "Found projected coordinates in this file but couldn't confidently match them "
                "to a known Nigerian coordinate system. Please double-check the source document, "
                "or enter WGS84 latitude/longitude manually below."
            )
        else:
            show_warning("Couldn't detect coordinates in this file automatically - please enter them below.")

    with st.container(key=k("pp_stage_upload")):
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
                if file_type in ("png", "jpg", "jpeg") and file_handler.storage_backend() == "local":
                    quality_issue = file_handler.check_image_quality(saved_path)
                    if quality_issue:
                        show_warning(quality_issue)

    # Progressive disclosure: the coordinate-confirmation step below only
    # appears once there's something to confirm - an upload, prior manual
    # entry, or an explicit "enter manually" click - rather than showing
    # every widget on the page at once. Sticky (never re-hides) once
    # revealed, and skipped entirely for a `disabled` slot (Plot B before
    # neighbor consent), which already can't be interacted with anyway.
    already_has_content = bool(st.session_state.get(k("_upload_record"))) or bool(
        (st.session_state.get(k("coords_text")) or "").strip()
    )
    stage2_revealed = disabled or already_has_content or st.session_state.get(k("_stage2_revealed"), False)
    if not stage2_revealed:
        if st.button("Or, enter coordinates manually", key=k("reveal_manual_entry")):
            stage2_revealed = True
    st.session_state[k("_stage2_revealed")] = stage2_revealed

    if not stage2_revealed:
        return {
            "coordinates_text": "",
            "forced_epsg": CRS_OPTIONS[st.session_state.get(k("_crs_override"), "Auto-detect")],
            "help_improve": help_improve,
            "upload_record": None,
        }

    with st.container(key=k("pp_stage_coords")):
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

        # Re-fetch: extract_and_store() above may have just replaced this.
        # Rendered before the coordinates box for the same reason as the CRS
        # override above - editing a row here rewrites coords_text before that
        # widget is instantiated this run.
        upload_record = st.session_state.get(k("_upload_record"))
        document_info = upload_record.get("document_info") if upload_record else None
        if document_info and document_metadata.has_any(document_info) and not disabled:
            detail_rows = [
                ("Survey number", document_info.get("survey_number")),
                ("Surveyor", document_info.get("surveyor_name")),
                ("Plan date", document_info.get("plan_date")),
                ("Scale", document_info.get("scale_text")),
                ("Area", f"{document_info['area_sqm']:,.1f} sqm" if document_info.get("area_sqm") else None),
            ]
            detail_html = "".join(
                f"<li>{icons.dot('#898781', size=8)}<span><strong>{label}:</strong> {value}</span></li>"
                for label, value in detail_rows
                if value
            )
            st.markdown(
                f"""
                <div class="pp-card">
                  <div class="pp-card-title">Document Details (auto-read - verify against your document)</div>
                  <ul class="pp-list">{detail_html}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

        legs_info = upload_record.get("legs_info") if upload_record else None
        if legs_info and legs_info.get("rows") and not disabled:
            with st.expander("Boundary bearings & distances (auto-read - review before trusting)", expanded=True):
                origin_lat, origin_lon = legs_info["origin_latlon"]
                st.markdown(
                    f"**Origin point (PL1)** - every other point below is calculated from this one: "
                    f"`{legs_info['origin_label']}` → `{origin_lat:.6f}, {origin_lon:.6f}` "
                    f"(also always the first line in the coordinates box below)."
                )
                st.warning(
                    "These bearing and distance values were read automatically from your file and can "
                    "be wrong, especially on handwritten plans or low-quality photos. Check each line "
                    "against your original document and correct anything that doesn't match. If you're "
                    "not confident reading a bearing or distance yourself, please have a licensed "
                    "surveyor confirm before relying on this for any transaction."
                )
                edited_rows = st.data_editor(
                    legs_info["rows"],
                    column_config={
                        "beacon": st.column_config.TextColumn(
                            "Line",
                            help="Which two boundary corners this row describes, e.g. \"PL1 → PL2\" "
                            "means the line from corner 1 to corner 2.",
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
                    },
                    column_order=["beacon", "bearing_text", "distance_m"],
                    hide_index=True,
                    key=k("legs_editor"),
                    disabled=disabled,
                )

                # Separate from value editing above - covers the case where
                # every individual bearing/distance was read correctly but in
                # the wrong sequence (confirmed real case: a plan's actual
                # first leg was read further down the list). st_sortables only
                # takes list[str], so each row becomes one descriptive,
                # uniquely-numbered line; dragging returns the same strings
                # reordered, which we map back to row dicts by that number.
                final_rows = edited_rows
                if len(edited_rows) > 1 and not disabled:
                    st.caption(
                        "Values correct but in the wrong order (e.g. the plan's real first leg turns "
                        "out to be further down)? Drag to rearrange:"
                    )
                    item_labels = [
                        f"{i + 1}. {row.get('beacon') or '?'}  —  {row.get('bearing_text') or '?'}  —  "
                        f"{row.get('distance_m')}m"
                        for i, row in enumerate(edited_rows)
                    ]
                    sorted_labels = streamlit_sortables.sort_items(item_labels, direction="vertical", key=k("legs_order"))
                    if sorted_labels != item_labels:
                        order = [item_labels.index(label) for label in sorted_labels]
                        final_rows = [edited_rows[i] for i in order]
                        # Auto-generated "PL1 -> PL2" labels describe a
                        # position in the walk, not a specific physical
                        # beacon, so relabel them to match the new order. Real
                        # beacon codes (read off the plan) travel with their
                        # row untouched instead - those describe an actual
                        # physical line regardless of where it falls in the walk.
                        if all(re.fullmatch(r"PL\d+ → PL\d+", row.get("beacon") or "") for row in final_rows):
                            n = len(final_rows)
                            final_rows = [
                                {**row, "beacon": f"PL{i + 1} → PL{(i + 1) % n + 1}"} for i, row in enumerate(final_rows)
                            ]

                if final_rows != st.session_state.get(k("_last_applied_legs")):
                    st.session_state[k("_last_applied_legs")] = final_rows
                    new_legs = []
                    all_parsed = True
                    for row in final_rows:
                        bearing = traverse.parse_bearing_string(row.get("bearing_text"))
                        distance = row.get("distance_m")
                        if bearing is None or distance is None:
                            all_parsed = False
                            break
                        new_legs.append((bearing, distance))

                    origin_latlon = upload_record["auto_detected_points"][0] if upload_record.get("auto_detected_points") else None
                    new_points, closed, new_diagonal = None, False, None
                    if all_parsed and origin_latlon and len(new_legs) >= 3:
                        # Per-vertex labels (not per-line) for the diagonal's
                        # target - each row's "beacon" describes the LINE
                        # from this vertex to the next ("PL1 → PL2" or a
                        # real beacon code), so its first half is this row's
                        # own vertex identifier.
                        vertex_labels = [
                            row["beacon"].split(" → ")[0] if " → " in (row.get("beacon") or "") else f"PL{i + 1}"
                            for i, row in enumerate(final_rows)
                        ]
                        new_points, closed, new_diagonal = traverse.resolve_recomputed_points(
                            legs_info["origin_en"], origin_latlon, new_legs, labels=vertex_labels
                        )

                    if new_points and len(new_points) >= 3:
                        st.session_state[k("coords_text")] = "\n".join(f"{lat}, {lon}" for lat, lon in new_points)
                        # Keeps resolve_points()'s upload-time-crs_note reuse
                        # working (see its docstring) - the CRS itself hasn't
                        # changed, just the boundary shape within it.
                        upload_record["auto_detected_points"] = new_points
                        # Otherwise the diagonal card below would keep
                        # showing the pre-edit boundary's diagonal.
                        legs_info["diagonal"] = new_diagonal
                        if not closed:
                            show_warning(
                                "Updated the boundary from your edits, but it doesn't fully close - common "
                                "on older or hand-surveyed plans. The shape shown is approximate; consider "
                                "having a licensed surveyor confirm it before relying on this for a transaction."
                            )
                    elif not all_parsed:
                        show_warning(
                            "One or more bearing/distance values couldn't be read - fix the format "
                            "(e.g. 52°30') to update the boundary."
                        )
                    else:
                        show_warning("At least 3 boundary legs are needed to build a shape.")

            diagonal = legs_info.get("diagonal")
            if diagonal:
                # Same CRS description already shown in the upload success
                # message/results pill (crs_note), trimmed to just the
                # "EPSG:xxxx (Name)" portion before its first "; ..." note -
                # the plan's own projected system, not the WGS84 conversion.
                crs_source_note = (upload_record.get("auto_detected_crs_note") or "").split(";")[0].strip()
                crs_label = crs_source_note or "local projected system"
                coord_lines = f'<p>Coordinate ({crs_label}): <strong>{diagonal["point_label"]}</strong></p>'
                if diagonal.get("point_latlon"):
                    diag_lat, diag_lon = diagonal["point_latlon"]
                    coord_lines += f"<p>Coordinate (WGS84): <strong>{diag_lat:.6f}, {diag_lon:.6f}</strong></p>"
                st.markdown(
                    f"""
                    <div class="pp-card">
                      <div class="pp-card-title">Diagonal Check</div>
                      <p>A straight-line distance and bearing from the origin (PL1) to the opposite
                      corner, calculated directly from the boundary above - not read from your
                      document (most plans don't print one), a reference you can pace out on-site
                      to sanity-check the plot's extent.</p>
                      <p><strong>PL1 → {diagonal['target_label']}: {traverse.format_bearing(diagonal['bearing'])}
                      · {diagonal['distance_m']:.2f}m</strong></p>
                      {coord_lines}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

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
    points, crs_note, _, _ = parse_coordinate_text(inputs["coordinates_text"], forced_epsg=inputs["forced_epsg"])
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
# General due-diligence steps for any Nigerian land purchase - not specific
# to this result (that's what result["recommendations"] is for), and not a
# substitute for the professional advice several of these items name.
PURCHASE_CHECKLIST = [
    "Verify the seller's identity and confirm they're the rightful owner or an authorized agent",
    "Visit the site in person and confirm the physical boundary matches what's shown here",
    "Have a licensed surveyor independently verify the boundary and beacons",
    "Confirm the land isn't under government acquisition or a right-of-way at the relevant land registry",
    "Get a lawyer to review the title documents (Certificate of Occupancy, Deed of Assignment, etc.)",
    "Confirm there's no existing encumbrance, lien, or dispute registered against the property",
]

def _risk_reason(result: dict) -> str:
    """One plain-English sentence naming the specific, primary driver of this
    result - mirrors utils/risk_calculator.py's own risk_level branching so it
    never contradicts the badge, but reads as a sentence rather than the raw
    findings list (which can lead with an unrelated data-quality flag, e.g.
    an off-region coordinate, before the actual risk driver)."""
    overlaps, proximate = result["overlaps"], result["proximate"]
    if overlaps:
        o = overlaps[0]
        extra = f" (and {len(overlaps) - 1} more)" if len(overlaps) > 1 else ""
        return f"Your boundary overlaps registered plot {o['plot_ref']} by about {o['overlap_area_sqm']:.0f} m²{extra}."
    if proximate:
        p = proximate[0]
        extra = f" (and {len(proximate) - 1} more)" if len(proximate) > 1 else ""
        return f"Your boundary is close to registered plot {p['plot_ref']} - about {p['distance_m']:.0f} m away{extra}."
    if result["risk_level"] == "Medium":
        return "Only 1-2 coordinates were provided, so the boundary shown is an estimate rather than your full surveyed shape."
    return "No overlaps or nearby boundaries were found against the plots currently on record."


def render_results(
    result: dict,
    points: list,
    user_gdf,
    neighbors_gdf,
    crs_note: Optional[str],
    show_registry_features: bool = True,
    map_caption: str = "Shows registered plots in the immediate surroundings, not the full registry.",
    use_context_radius: bool = True,
    pdf_neighbor_points: Optional[list] = None,
    key_prefix: str = "single",
    document_info: Optional[dict] = None,
) -> None:
    if crs_note and crs_note != "undetected":
        st.markdown(
            f"""<div class="pp-pill">{icons.icon("ruler", size=14)} Coordinates converted from
            {crs_note} to WGS84 for analysis.</div>""",
            unsafe_allow_html=True,
        )
        if crs_utils.crs_is_uncertain(crs_note):
            show_crs_disclaimer()
        if traverse.traverse_order_uncertain(crs_note):
            show_traverse_order_disclaimer()

    geometry_issue = gis_processing.check_boundary_validity(points)
    if geometry_issue:
        show_warning(("Your plot: " if pdf_neighbor_points else "") + geometry_issue)
    if pdf_neighbor_points:
        neighbor_geometry_issue = gis_processing.check_boundary_validity(pdf_neighbor_points)
        if neighbor_geometry_issue:
            show_warning(f"Neighboring plot: {neighbor_geometry_issue}")

    step_header(None, "Risk Assessment")
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
    st.markdown(
        f'<p class="pp-lede" style="margin:8px 0 var(--pp-space-4)">{_risk_reason(result)}</p>',
        unsafe_allow_html=True,
    )
    with st.expander("What does this risk level mean?"):
        st.markdown(theme.RISK_EXPLAINER[risk_level])

    if assistant.is_available():
        history_key = f"_assistant_history_{key_prefix}"
        question_key = f"_assistant_question_{key_prefix}"
        error_key = f"_assistant_error_{key_prefix}"

        def _handle_ask(
            history_key=history_key,
            question_key=question_key,
            error_key=error_key,
            result=result,
            points=points,
            crs_note=crs_note,
            document_info=document_info,
        ) -> None:
            # A st.button(on_click=...) callback, not inline code below the
            # button - runs (and can clear question_key) BEFORE the widget
            # is re-instantiated on the resulting rerun. Deleting/clearing
            # the key *after* the button in a normal script run (the more
            # obvious-looking approach) does not actually reset a
            # text_input in this Streamlit version - confirmed directly
            # against a minimal repro before settling on this pattern.
            question = (st.session_state.get(question_key) or "").strip()
            st.session_state[question_key] = ""
            st.session_state[error_key] = None
            if not question:
                return
            if not rate_limit.check_burst_limit(CLIENT_ID, BURST_MAX_REQUESTS, BURST_WINDOW_SECONDS):
                st.session_state[error_key] = "Too many requests in a short time. Please wait a minute and try again."
                return
            if not rate_limit.check_daily_limit(CLIENT_ID, "assistant_ask", DAILY_ASSISTANT_LIMIT)[0]:
                st.session_state[error_key] = f"You've reached today's limit of {DAILY_ASSISTANT_LIMIT} questions per day."
                return
            try:
                answer = assistant.ask(
                    question,
                    {
                        "risk_level": result["risk_level"],
                        "reason": _risk_reason(result),
                        "findings": result["findings"],
                        "recommendations": result["recommendations"],
                        "point_count": len(points),
                        "crs_note": crs_note,
                        "document_info": document_info,
                    },
                )
            except Exception:
                traceback.print_exc()
                fallback = assistant.fallback_answer(question)
                if fallback:
                    answer = fallback
                else:
                    answer = (
                        "The AI assistant is temporarily unavailable right now. Check the "
                        f"[Common Questions](faq) page, or [contact PlotProof]({WHATSAPP_LINK}) directly."
                    )
            st.session_state.setdefault(history_key, []).append((question, answer))

        with st.expander("Ask about this report"):
            for q, a in st.session_state.get(history_key, []):
                st.markdown(f"**You:** {q}")
                st.markdown(f"**PlotProof:** {a}")
                st.divider()
            if st.session_state.get(error_key):
                show_error(st.session_state[error_key])
            st.text_input(
                "Ask a question about this result",
                key=question_key,
                placeholder="Why is this High risk? What does overlap mean? What should I do next?",
                label_visibility="collapsed",
            )
            st.button("Ask", key=f"_assistant_ask_{key_prefix}", on_click=_handle_ask)

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

    step_header(None, "Purchase Readiness Checklist")
    st.caption(
        "General due-diligence steps for any Nigerian land purchase - not specific to this "
        "result, and not a substitute for the professional advice several of these name."
    )
    checked_count = 0
    for i, item in enumerate(PURCHASE_CHECKLIST):
        if st.checkbox(item, key=f"_checklist_{key_prefix}_{i}"):
            checked_count += 1
    st.progress(
        checked_count / len(PURCHASE_CHECKLIST),
        text=f"{checked_count}/{len(PURCHASE_CHECKLIST)} completed",
    )

    step_header(None, "Map View")
    st.caption(map_caption)
    overlap_refs = {o["plot_ref"] for o in result["overlaps"]}
    proximate_refs = {p["plot_ref"] for p in result["proximate"]}
    user_geom = user_gdf.geometry.iloc[0]
    centroid = user_geom.centroid
    context_gdf = gis_processing.nearby_plots_for_context(user_gdf, neighbors_gdf) if use_context_radius else neighbors_gdf

    fmap = folium.Map(location=[centroid.y, centroid.x], zoom_start=17, tiles=None)
    folium.TileLayer("OpenStreetMap", name="Street").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics",
        name="Satellite",
        show=False,
    ).add_to(fmap)
    Fullscreen(position="topright").add_to(fmap)
    MeasureControl(position="bottomleft", primary_length_unit="meters", primary_area_unit="sqmeters").add_to(fmap)
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

    folium.LayerControl(position="topright", collapsed=True).add_to(fmap)
    st_folium(fmap, width=700, height=400, key=f"risk_map_{key_prefix}")
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
    csv_buffer = report_generator.generate_csv_report(points)
    geojson_buffer = report_generator.generate_geojson_report(points, result)
    dl_pdf, dl_csv, dl_geojson = st.columns(3)
    with dl_pdf:
        st.download_button(
            label="PDF Report",
            data=pdf_buffer,
            file_name="PlotProof_Report.pdf",
            mime="application/pdf",
            key=f"download_pdf_{key_prefix}",
            help="A formatted report with the risk level, findings, map diagram, and coordinates.",
        )
    with dl_csv:
        st.download_button(
            label="CSV",
            data=csv_buffer,
            file_name="PlotProof_Coordinates.csv",
            mime="text/csv",
            key=f"download_csv_{key_prefix}",
            help="Just the boundary coordinates, for a spreadsheet.",
        )
    with dl_geojson:
        st.download_button(
            label="GeoJSON",
            data=geojson_buffer,
            file_name="PlotProof_Boundary.geojson",
            mime="application/geo+json",
            key=f"download_geojson_{key_prefix}",
            help="The boundary shape plus risk data, for your own GIS software.",
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
            st.markdown(
                f"""
                <div class="pp-card" style="margin-top:24px">
                  <div class="pp-card-title">{icons.icon("users", size=16)} Add This Plot to the Shared Registry</div>
                  <p>Only the boundary shape is stored - no name, address, or document, just the
                  outline and a generated reference. Once added, future uploads near this location
                  get checked against it too, the same way yours was just checked against others.
                  This is separate from the extraction option above, and is permanent once added -
                  contact me via WhatsApp below if you'd like a contributed plot removed.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            add_to_registry = st.checkbox("Add my plot's boundary to the shared registry", value=False)
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
    # SINGLE-PLOT CHECK - a 3-step wizard (Your Land -> Review & Analyze ->
    # Results) rather than one long page, so a first-time user only ever
    # sees the fields relevant to what they're doing right now. Step
    # reached via st.session_state["_wiz1"] (sticky - survives reruns,
    # only ever advanced/rewound by this flow's own Back/Continue buttons).
    # ------------------------------
    wiz1_step = st.session_state.get("_wiz1", 1)
    render_wizard(["Your Land", "Review & Analyze", "Results"], wiz1_step)

    if wiz1_step == 1:
        inputs = render_document_input("", (None, "Upload Your Survey Document"), (None, "Confirm or Enter Coordinates"))

        # Staged like the upload/coordinates steps above - the button only
        # appears once there's actually something to move forward with.
        if inputs["coordinates_text"].strip():
            with st.container(key="pp_stage_action"):
                if st.button("Continue to Review", type="primary"):
                    st.session_state["_wiz1_inputs"] = inputs
                    st.session_state["_wiz1"] = 2
                    st.rerun()

    elif wiz1_step == 2:
        inputs = st.session_state.get("_wiz1_inputs") or {}
        with st.container(key="pp_stage_review"):
            step_header(None, "Review Before Analyzing")
            preview_points, preview_crs_note = resolve_points(inputs)
            st.markdown(
                f"""
                <div class="pp-card">
                  <div class="pp-card-title">{len(preview_points)} coordinate point(s) ready to check</div>
                  <p>We'll check this boundary against known neighboring plots for overlaps and
                  proximity risks. Go back if anything below looks wrong.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if preview_crs_note and preview_crs_note != "undetected":
                st.markdown(
                    f"""<div class="pp-pill">{icons.icon("ruler", size=14)} Coordinates will be
                    converted from {preview_crs_note} to WGS84.</div>""",
                    unsafe_allow_html=True,
                )
            if crs_utils.crs_is_uncertain(preview_crs_note):
                show_crs_disclaimer()
            if traverse.traverse_order_uncertain(preview_crs_note):
                show_traverse_order_disclaimer()

            col_back, col_next = st.columns([1, 2])
            with col_back:
                if st.button("← Back"):
                    st.session_state["_wiz1"] = 1
                    st.rerun()
            with col_next:
                analyze_clicked = st.button("Analyze My Land", type="primary")

        if analyze_clicked:
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
                # A real (not staged/fake) step-by-step status instead of a
                # bare spinner - each line only appears once that actual
                # piece of work has run, so the user always knows what's
                # happening rather than staring at an opaque "Loading...".
                # Small pauses make each line legible instead of flashing by
                # (these calls are normally sub-second) without meaningfully
                # slowing anything down (well under a second added in total).
                with st.status("Analyzing your land boundaries...", expanded=True) as status:
                    st.write("Loading known plots in your area...")
                    neighbors_gdf = _load_neighbors()
                    time.sleep(0.2)
                    st.write("Checking boundary geometry...")
                    time.sleep(0.2)
                    st.write("Building your plot boundary...")
                    user_gdf = gis_processing.build_user_plot_gdf(points)
                    time.sleep(0.2)
                    st.write("Checking for overlaps with neighboring plots...")
                    overlap_result = gis_processing.analyze_overlap(user_gdf, neighbors_gdf)
                    time.sleep(0.2)
                    st.write("Calculating risk level...")
                    result = risk_calculator.calculate_risk(
                        points, overlap_result, boundary_is_measured=len(points) >= 3
                    )
                    status.update(label="Analysis complete", state="complete", expanded=False)

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
                st.session_state["document_info"] = upload_record.get("document_info") if upload_record else None
                st.session_state["_wiz1"] = 3
                st.rerun()

    elif wiz1_step == 3 and "result" in st.session_state:
        with st.container(key="pp_stage_results"):
            render_results(
                st.session_state["result"],
                st.session_state["points"],
                st.session_state["user_gdf"],
                st.session_state["neighbors_gdf"],
                st.session_state.get("crs_note"),
                show_registry_features=True,
                key_prefix="single",
                document_info=st.session_state.get("document_info"),
            )
        if st.button("Check Another Plot"):
            st.session_state["_wiz1"] = 1
            st.rerun()

else:
    # ------------------------------
    # TWO-PLOT COMPARISON - a 4-step wizard (Your Plot -> Neighbor's Plot ->
    # Review & Compare -> Results). Splitting "your plot" and "neighbor's
    # plot" into separate steps (rather than both stacked on one page)
    # keeps the neighbor-consent gate front and center on its own step
    # instead of buried below an unrelated upload widget.
    # ------------------------------
    wiz2_step = st.session_state.get("_wiz2", 1)
    render_wizard(["Your Plot", "Neighbor's Plot", "Review & Compare", "Results"], wiz2_step)

    if wiz2_step == 1:
        inputs_a = render_document_input("a", (None, "Upload or Enter Your Plot's Details"))
        if inputs_a["coordinates_text"].strip():
            with st.container(key="pp_stage_action"):
                if st.button("Continue to Neighbor's Plot", type="primary"):
                    st.session_state["_wiz2_inputs_a"] = inputs_a
                    st.session_state["_wiz2"] = 2
                    st.rerun()

    elif wiz2_step == 2:
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
            "and understands the result may be shared with me.",
            key="_neighbor_consent",
        )
        if not neighbor_consent:
            st.caption("Check the box above to enter your neighbor's plot details.")

        inputs_b = render_document_input("b", (None, "Neighboring Plot"), disabled=not neighbor_consent)

        col_back, col_next = st.columns([1, 2])
        with col_back:
            if st.button("← Back", key="_wiz2_back_2"):
                st.session_state["_wiz2"] = 1
                st.rerun()
        with col_next:
            if neighbor_consent and inputs_b["coordinates_text"].strip():
                with st.container(key="pp_stage_action"):
                    if st.button("Continue to Review", type="primary", key="_wiz2_next_2"):
                        st.session_state["_wiz2_inputs_b"] = inputs_b
                        st.session_state["_wiz2"] = 3
                        st.rerun()

    elif wiz2_step == 3:
        inputs_a = st.session_state.get("_wiz2_inputs_a") or {}
        inputs_b = st.session_state.get("_wiz2_inputs_b") or {}
        with st.container(key="pp_stage_review"):
            step_header(None, "Review Before Comparing")
            preview_a, crs_a = resolve_points(inputs_a)
            preview_b, crs_b = resolve_points(inputs_b)
            st.markdown(
                f"""
                <div class="pp-card">
                  <div class="pp-card-title">Ready to compare</div>
                  <p>Your plot: {len(preview_a)} coordinate point(s). Neighboring plot:
                  {len(preview_b)} coordinate point(s). Go back if either looks wrong.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if crs_utils.crs_is_uncertain(crs_a) or crs_utils.crs_is_uncertain(crs_b):
                show_crs_disclaimer()
            if traverse.traverse_order_uncertain(crs_a) or traverse.traverse_order_uncertain(crs_b):
                show_traverse_order_disclaimer()

            col_back, col_next = st.columns([1, 2])
            with col_back:
                if st.button("← Back", key="_wiz2_back_3"):
                    st.session_state["_wiz2"] = 2
                    st.rerun()
            with col_next:
                compare_clicked = st.button("Compare Plots", type="primary")

        if compare_clicked:
            points_a, crs_note_a = resolve_points(inputs_a)
            points_b, crs_note_b = resolve_points(inputs_b)
            if not points_a or not points_b:
                show_error("Please provide valid coordinates for both your plot and the neighboring plot.")
            elif not check_can_run_check():
                pass
            else:
                with st.status("Comparing the two plots...", expanded=True) as status:
                    st.write("Checking boundary geometry...")
                    time.sleep(0.2)
                    st.write("Building your plot boundary...")
                    user_gdf = gis_processing.build_user_plot_gdf(points_a)
                    time.sleep(0.2)
                    st.write("Building neighboring plot boundary...")
                    neighbor_geom_gdf = gis_processing.build_user_plot_gdf(points_b)
                    neighbor_gdf = gpd.GeoDataFrame(
                        {"plot_ref": ["Neighboring Plot"], "owner": ["Provided by you"]},
                        geometry=neighbor_geom_gdf.geometry,
                        crs="EPSG:4326",
                    )
                    time.sleep(0.2)
                    st.write("Checking for overlap...")
                    overlap_result = gis_processing.analyze_overlap(user_gdf, neighbor_gdf)
                    time.sleep(0.2)
                    st.write("Calculating risk level...")
                    result = risk_calculator.calculate_risk(
                        points_a, overlap_result, boundary_is_measured=len(points_a) >= 3
                    )
                    status.update(label="Comparison complete", state="complete", expanded=False)

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
                a_upload = inputs_a["upload_record"]
                st.session_state["_compare_document_info"] = a_upload.get("document_info") if a_upload else None
                st.session_state["_wiz2"] = 4
                st.rerun()

    elif wiz2_step == 4 and "_compare_result" in st.session_state:
        with st.container(key="pp_stage_results"):
            render_results(
                st.session_state["_compare_result"],
                st.session_state["_compare_points"],
                st.session_state["_compare_user_gdf"],
                st.session_state["_compare_neighbor_gdf"],
                st.session_state.get("_compare_crs_note"),
                show_registry_features=False,
                map_caption="Shows your plot against the neighboring plot you provided.",
                use_context_radius=False,
                document_info=st.session_state.get("_compare_document_info"),
                pdf_neighbor_points=st.session_state.get("_compare_neighbor_points"),
                key_prefix="compare",
            )
        if st.button("Compare Another Plot"):
            st.session_state["_wiz2"] = 1
            st.rerun()

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
st.page_link("pages/about.py", label="Terms of Service & Privacy Policy", icon="📄")
