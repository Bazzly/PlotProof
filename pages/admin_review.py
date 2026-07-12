"""
Admin portal:
  1. Rotate the Anthropic API key at runtime, without touching deployment
     config - see utils/app_config.py. This repo is public, so the key
     can't live in committed source, and this lets it be viewed (masked)
     and replaced immediately if it's ever exposed.
  2. Browse opt-in extraction training-data records (see
     utils/training_data.py) collected via the "Help improve coordinate
     extraction" checkbox on the main flow - visibility into real-world
     extraction failures, the same class of failure that motivated
     building utils/vision_extract.py in the first place.

Gated behind ADMIN_PASSWORD (env var). Not linked from the main app; only
reachable via Streamlit's page nav or a direct URL, and refuses to render
at all if no password is configured, so it can never be accidentally
exposed with no gate.
"""

import os

import streamlit as st

from utils import app_config, theme, training_data

st.set_page_config(page_title="PlotProof Admin", layout="wide")
st.markdown(theme.get_css(), unsafe_allow_html=True)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

st.title("PlotProof Admin")

if not ADMIN_PASSWORD:
    st.error(
        "This admin portal is disabled because ADMIN_PASSWORD is not set. "
        "Set it in your environment (or .env) to enable it."
    )
    st.stop()

if not st.session_state.get("_admin_authed"):
    st.text_input("Admin password", type="password", key="_admin_pw_input")
    if st.button("Sign in", type="primary"):
        if st.session_state["_admin_pw_input"] == ADMIN_PASSWORD:
            st.session_state["_admin_authed"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

tab_key, tab_review = st.tabs(["API Key", "Extraction Review"])

with tab_key:
    st.subheader("Anthropic API key")
    st.caption(
        "Powers vision-based extraction for photographed survey plans "
        "(utils/vision_extract.py). A key set here overrides the "
        "ANTHROPIC_API_KEY environment variable immediately, for this and "
        "every future request - no redeploy needed. Use this to rotate the "
        "key right away if it's ever exposed (e.g. pasted somewhere public)."
    )

    current_key = app_config.get_anthropic_api_key()
    source = "admin override" if app_config.get_setting(app_config.ANTHROPIC_API_KEY_SETTING) else "environment variable"
    st.text_input("Current key", value=app_config.mask_key(current_key), disabled=True)
    if current_key:
        st.caption(f"Source: {source}")

    with st.form("api_key_form", clear_on_submit=True):
        new_key = st.text_input("New key", type="password", placeholder="sk-ant-...")
        submitted = st.form_submit_button("Save key", type="primary")
        if submitted:
            if new_key.strip():
                app_config.set_anthropic_api_key(new_key)
                st.success("API key updated.")
                st.rerun()
            else:
                st.error("Enter a key before saving.")

    if app_config.get_setting(app_config.ANTHROPIC_API_KEY_SETTING):
        if st.button("Clear admin override (fall back to environment variable)"):
            app_config.clear_anthropic_api_key()
            st.rerun()

with tab_review:
    st.caption(
        "Opt-in examples from the \"Help improve coordinate extraction\" checkbox - "
        "source document, what auto-detection found, and what the user confirmed."
    )

    records = training_data.list_examples()

    if not records:
        st.info("No training examples recorded yet.")
        st.stop()

    # ---- summary metrics ----
    total = len(records)
    failures = [r for r in records if not r.get("auto_detected_points")]
    corrected = [r for r in records if r.get("was_corrected")]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total examples", total)
    col2.metric("Zero points detected", len(failures), help="Extraction found nothing at all - the worst failure mode.")
    col3.metric("User corrected", len(corrected), help="Auto-detected points differed from what the user confirmed.")

    # ---- filters ----
    methods = sorted({r.get("extraction_method", "unknown") for r in records})
    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        method_filter = st.multiselect("Extraction method", methods, default=methods)
    with col_b:
        failures_only = st.checkbox("Failures only (zero points)")
    with col_c:
        corrected_only = st.checkbox("Corrected only")

    filtered = [r for r in records if r.get("extraction_method", "unknown") in method_filter]
    if failures_only:
        filtered = [r for r in filtered if not r.get("auto_detected_points")]
    if corrected_only:
        filtered = [r for r in filtered if r.get("was_corrected")]

    st.caption(f"Showing {len(filtered)} of {total} example(s).")

    for record in filtered:
        auto_points = record.get("auto_detected_points") or []
        confirmed_points = record.get("user_confirmed_points") or []
        method = record.get("extraction_method", "unknown")

        badges = [method]
        if not auto_points:
            badges.append("ZERO POINTS")
        if record.get("was_corrected"):
            badges.append("corrected")

        title = f"{record.get('timestamp', '?')} - {record.get('file_type', '?')} - {' | '.join(badges)}"

        with st.expander(title):
            left, right = st.columns([1, 1])

            with left:
                source_ref = record.get("source_file_ref")
                file_type = record.get("file_type")
                if source_ref and file_type in ("png", "jpg", "jpeg") and os.path.isfile(source_ref):
                    st.image(source_ref, use_container_width=True)
                elif source_ref:
                    st.caption(f"Source: {source_ref}")
                else:
                    st.caption("No source file reference stored.")

                st.markdown("**Auto-detected CRS note**")
                st.code(record.get("auto_detected_crs_note") or "(none)", language=None)

            with right:
                st.markdown("**Extracted text / vision summary**")
                st.text_area(
                    "raw_extracted_text",
                    value=record.get("raw_extracted_text") or "(empty)",
                    height=180,
                    label_visibility="collapsed",
                    key=f"raw_{record['id']}",
                )

            col_auto, col_confirmed = st.columns(2)
            with col_auto:
                st.markdown(f"**Auto-detected points ({len(auto_points)})**")
                st.dataframe(auto_points, use_container_width=True, hide_index=True)
            with col_confirmed:
                st.markdown(f"**User-confirmed points ({len(confirmed_points)})**")
                st.dataframe(confirmed_points, use_container_width=True, hide_index=True)
