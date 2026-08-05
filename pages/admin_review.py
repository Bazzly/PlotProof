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
  3. Bulk-add known survey plans to the shared registry (see
     utils/registry.py) - lets an admin seed real coverage for an area
     (e.g. plans they have legitimate access to) faster than waiting for
     individual users to opt in one plot at a time via the main flow.
  4. Train the floating "land chat" (see utils/land_chat_training.py,
     utils/land_chat_match.py, utils/nav.py's render_floating_chat()) by
     adding/editing/deleting free-text passages it matches visitor
     questions against - no external API involved in that chat at all,
     by design, so it can't go down the way the old Claude-backed
     version repeatedly did.
  5. Upload GeoJSON fallback datasets for Investment Analysis (see
     utils/investment_fallback_data.py) - real, admin-verified amenities/
     roads/land-use/buildings for a specific area, used to enhance or
     replace live OpenStreetMap data there when OSM's own tagging is
     sparse or Overpass is unreachable.
  6. Review, rate, and publish Land Listings submissions (see
     utils/listings.py, pages/listings.py) - every listing starts hidden
     until approved here; set/override the risk rating by hand, mark
     paid "PlotProof Verified" status (no in-app payment - see
     utils/listings.py's docstring for why), and get pre-filled share
     links (utils/listing_format.py) for a published listing.
  7. Post Property Requests (see utils/property_requests.py) - the
     inverse of a Land Listing: a verified buyer's ask, posted only from
     here (no public submission form - PlotProof is vetting the buyer,
     not reviewing an outside submission). Paste the buyer's brief, same
     parse-then-edit flow as Land Listings, and it's live immediately.

Gated behind ADMIN_PASSWORD (env var), and refuses to render at all if no
password is configured, so it can never be accidentally exposed with no
gate. Not linked from the main app and never listed in any sidebar/nav -
see app.py's st.navigation(..., position="hidden") setup - only reachable
by going directly to the URL slug set via ADMIN_URL_PATH.
"""

import json
import os
import traceback
from datetime import datetime, timezone

import streamlit as st

from utils import (
    app_config,
    coordinates,
    crs_utils,
    faq_content,
    file_handler,
    gis_processing,
    investment_fallback_data,
    land_chat_match,
    land_chat_training,
    listing_format,
    listings,
    property_requests,
    registry,
    risk_calculator,
    theme,
    training_data,
    traverse,
    vision_extract,
)

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

tab_key, tab_review, tab_bulk, tab_chat, tab_invest, tab_listings, tab_requests = st.tabs(
    [
        "API Key", "Extraction Review", "Bulk Add Plans", "Land Chat Training",
        "Investment Fallback Data", "Listings", "Property Requests",
    ]
)

# Files that get skipped from auto-add rather than flagged as an outright
# failure - anything the main app itself treats as "needs a human to
# confirm" (see app_home.py's disclaimers) shouldn't be added to a SHARED
# registry unattended, since other users' overlap checks depend on it
# being right. A processing exception or zero/insufficient points is a
# separate "Failed" outcome, handled inline below.
MAX_BULK_FILES = 30

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
    else:
        # ---- summary metrics ----
        total = len(records)
        failures = [r for r in records if not r.get("auto_detected_points")]
        corrected = [r for r in records if r.get("was_corrected")]

        col1, col2, col3 = st.columns(3)
        col1.metric("Total examples", total)
        col2.metric(
            "Zero points detected", len(failures), help="Extraction found nothing at all - the worst failure mode."
        )
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

with tab_bulk:
    st.caption(
        "Upload multiple survey plans at once. Each is auto-extracted the same way the main "
        "app does, and boundaries that extract as a clean, closed shape with a certain "
        "coordinate system are added directly to the shared registry (utils/registry.py) - "
        "only the boundary geometry, same as the main app's opt-in flow, no owner name or "
        "source document. Anything the extraction itself flags as uncertain (unconfirmed "
        "datum, beacon order/direction issue, or a boundary that didn't fully close) is "
        "skipped rather than added unattended - other users' overlap checks depend on this "
        "data being right, so nothing gets in without either real confidence or a human "
        "reviewing it through the main flow instead."
    )

    registry_count_before = registry.count()
    st.metric("Plots currently in shared registry", registry_count_before)

    use_vision = st.checkbox(
        "Use AI vision extraction for photos",
        value=False,
        help=(
            "Costs roughly $0.05-0.08 per image on the configured Anthropic API key (same "
            "vision path as the main app - utils/vision_extract.py). Off by default since a "
            "large batch of photos adds up fast. PDFs always use free text extraction, "
            "unaffected by this."
        ),
    )
    if use_vision and not vision_extract.is_available():
        st.warning("No Anthropic API key configured (see the API Key tab) - photos will fall back to free OCR instead.")

    uploaded_files = st.file_uploader(
        "Survey plans (PDF or image)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    if uploaded_files and len(uploaded_files) > MAX_BULK_FILES:
        st.error(f"Please upload {MAX_BULK_FILES} files or fewer at a time.")
    elif uploaded_files and st.button("Process and add to registry", type="primary"):
        rows = []
        progress = st.progress(0.0)
        for i, uploaded_file in enumerate(uploaded_files):
            filename = uploaded_file.name
            file_type = os.path.splitext(filename)[1].lstrip(".").lower()
            row = {"file": filename, "status": None, "detail": None, "points": 0, "plot_ref": None}
            try:
                saved_path = file_handler.save_uploaded_file(uploaded_file)
                points, crs_note, legs_info = None, None, None
                pdf_path = None

                if file_type in ("png", "jpg", "jpeg") and use_vision and vision_extract.is_available():
                    points, crs_note, _, legs_info, _ = vision_extract.extract_points_from_image(saved_path)
                else:
                    extracted_text, _ = file_handler.extract_text_from_file(saved_path)
                    pdf_path = saved_path if file_type == "pdf" and file_handler.storage_backend() == "local" else None
                    points, crs_note, legs_info, _ = coordinates.parse_coordinate_text(extracted_text, pdf_path=pdf_path)

                row["points"] = len(points or [])

                if not points or len(points) < 3:
                    row["status"] = "Skipped"
                    row["detail"] = "Not enough points for a real boundary (need 3+)."
                elif crs_note == "undetected":
                    row["status"] = "Skipped"
                    row["detail"] = "Projected coordinates found but couldn't be matched to a known Nigerian CRS."
                elif crs_utils.crs_is_uncertain(crs_note):
                    row["status"] = "Skipped"
                    row["detail"] = "Coordinate system datum wasn't confirmed - needs manual review."
                elif traverse.traverse_order_uncertain(crs_note):
                    row["status"] = "Skipped"
                    row["detail"] = "Beacon order/direction doesn't match the standard convention - needs manual review."
                elif traverse.boundary_is_approximate(crs_note):
                    row["status"] = "Skipped"
                    row["detail"] = "Boundary traverse didn't fully close - needs manual review."
                else:
                    plot_ref = registry.add_plot(points)
                    row["status"] = "Added"
                    row["detail"] = crs_note or "WGS84 as provided"
                    row["plot_ref"] = plot_ref
            except Exception as exc:
                traceback.print_exc()
                row["status"] = "Failed"
                row["detail"] = str(exc)
            rows.append(row)
            progress.progress((i + 1) / len(uploaded_files))

        added = sum(1 for r in rows if r["status"] == "Added")
        skipped = sum(1 for r in rows if r["status"] == "Skipped")
        failed = sum(1 for r in rows if r["status"] == "Failed")
        col_a, col_s, col_f = st.columns(3)
        col_a.metric("Added", added)
        col_s.metric("Skipped (needs review)", skipped)
        col_f.metric("Failed", failed)
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if added:
            st.success(f"Added {added} plot(s) to the shared registry - now {registry.count()} total.")

with tab_chat:
    st.caption(
        "Trains the floating land chat every visitor sees (utils/nav.py) - it answers purely "
        "from the passages below, verbatim, with no external API call and no conversational "
        "memory. Write short, focused passages (a paragraph or two, one topic each) rather "
        "than one giant document - the chat always returns whichever single passage matches "
        "a question best."
    )

    passages = land_chat_training.list_passages()
    st.metric("Trained passages", len(passages))

    if not passages:
        st.info("Nothing trained yet - the floating chat stays hidden until at least one passage exists.")
        if st.button("Seed starter content from the FAQ page"):
            for question, answer in faq_content.FAQ_ENTRIES:
                land_chat_training.add_passage(question, answer)
            st.success(f"Added {len(faq_content.FAQ_ENTRIES)} starter passage(s).")
            st.rerun()

    st.divider()
    st.markdown("**Test a question**")
    test_question = st.text_input("Ask a question the way a visitor would", key="_admin_chat_test_q")
    if test_question:
        ranked = land_chat_match.rank_passages(test_question)
        for entry in ranked[:5]:
            score = entry["score"]
            flag = " (low confidence)" if score < land_chat_match.LOW_CONFIDENCE_THRESHOLD else ""
            st.caption(f"{score:.3f}{flag} - {entry['passage'].get('title') or '(untitled)'}")

    st.divider()
    st.markdown("**Add a passage**")
    with st.form("add_land_chat_passage", clear_on_submit=True):
        new_title = st.text_input("Title (helps matching and your own organization)")
        new_text = st.text_area("Passage text - shown to visitors verbatim", height=140)
        if st.form_submit_button("Add passage", type="primary"):
            if new_text.strip():
                land_chat_training.add_passage(new_title, new_text)
                st.success("Passage added.")
                st.rerun()
            else:
                st.error("Enter passage text before saving.")

    if passages:
        st.divider()
        st.markdown("**Existing passages**")
        for passage in passages:
            label = passage.get("title") or (passage.get("text", "")[:60])
            with st.expander(label):
                edited_title = st.text_input("Title", value=passage.get("title", ""), key=f"lc_title_{passage['id']}")
                edited_text = st.text_area(
                    "Text", value=passage.get("text", ""), height=140, key=f"lc_text_{passage['id']}"
                )
                col_save, col_delete = st.columns(2)
                if col_save.button("Save changes", key=f"lc_save_{passage['id']}"):
                    land_chat_training.update_passage(passage["id"], edited_title, edited_text)
                    st.success("Saved.")
                    st.rerun()
                if col_delete.button("Delete", key=f"lc_delete_{passage['id']}"):
                    land_chat_training.delete_passage(passage["id"])
                    st.rerun()

with tab_invest:
    st.caption(
        "Real, admin-verified data for a specific area - amenities, roads, land use, buildings - "
        "used by Investment Analysis (pages/investment_analysis.py) to enhance or replace live "
        "OpenStreetMap data there. Any category this dataset covers overrides OpenStreetMap's "
        "result for that category when a query falls inside the dataset's radius; OpenStreetMap "
        "is still used for anything the dataset doesn't cover, and stays the only source anywhere "
        "not covered by an upload at all."
    )

    sample_path = os.path.join("data", "sample_data", "investment_fallback_sample.geojson")
    if os.path.isfile(sample_path):
        with open(sample_path, "rb") as f:
            st.download_button(
                "Download sample template (.geojson)", data=f.read(),
                file_name="investment_fallback_sample.geojson", mime="application/geo+json",
            )

    st.divider()
    st.markdown("**Upload a dataset**")
    uploaded = st.file_uploader("GeoJSON file", type=["geojson", "json"], key="_invest_fallback_upload")
    if uploaded is not None:
        try:
            raw_geojson = json.loads(uploaded.getvalue().decode("utf-8"))
            preview = investment_fallback_data.parse_geojson(raw_geojson)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(f"Not a valid JSON file: {exc}")
        except ValueError as exc:
            st.error(str(exc))
        else:
            counts = {k: len(v) for k, v in preview["features"].items()}
            st.success(
                f"\"{preview['name']}\" - center {preview['center']['lat']:.5f}, {preview['center']['lon']:.5f}, "
                f"{preview['radius_m']}m radius. {counts['amenities']} amenities, {counts['roads']} roads, "
                f"{counts['landuse']} land-use polygons, {counts['buildings']} buildings."
            )
            if st.button("Save this dataset", type="primary"):
                investment_fallback_data.add_dataset(raw_geojson)
                st.success("Saved.")
                st.rerun()

    st.divider()
    st.markdown("**Existing datasets**")
    datasets = investment_fallback_data.list_datasets()
    if not datasets:
        st.info("No fallback datasets uploaded yet - Investment Analysis runs on live OpenStreetMap data only.")
    else:
        for dataset in datasets:
            counts = {k: len(v) for k, v in dataset["features"].items()}
            label = f"{dataset['name']} - {dataset['radius_m']}m radius"
            with st.expander(label):
                st.caption(
                    f"Center: {dataset['center']['lat']:.5f}, {dataset['center']['lon']:.5f}  |  "
                    f"Uploaded: {dataset.get('uploaded_at', '?')}"
                )
                if dataset.get("source"):
                    st.markdown(f"**Source:** {dataset['source']}")
                if dataset.get("captured_at"):
                    st.markdown(f"**Captured:** {dataset['captured_at']}")
                if dataset.get("notes"):
                    st.markdown(f"**Notes:** {dataset['notes']}")
                st.markdown(
                    f"**Coverage:** {counts['amenities']} amenities, {counts['roads']} roads, "
                    f"{counts['landuse']} land-use polygons, {counts['buildings']} buildings"
                )
                if st.button("Delete dataset", key=f"inv_delete_{dataset['id']}"):
                    investment_fallback_data.delete_dataset(dataset["id"])
                    st.rerun()


def _render_admin_listing(listing: dict, app_url: str) -> None:
    risk_level = listings.effective_risk_level(listing)
    badges = [listing["status"]]
    if listing.get("alert_number"):
        badges.append(f"Alert #{listing['alert_number']:03d}")
    if listing.get("verification_requested"):
        badges.append("verification requested")
    if listing.get("verified"):
        badges.append("VERIFIED")
    if listing.get("sold"):
        badges.append("SOLD")
    if risk_level:
        badges.append(f"{risk_level} risk")
    label = f"{listing.get('heading') or 'Land for sale'} - {' | '.join(badges)}"

    with st.expander(label):
        st.text_area(
            "Raw text pasted by seller", value=listing.get("raw_text", ""), height=100,
            disabled=True, key=f"raw_{listing['id']}",
        )

        col1, col2 = st.columns(2)
        col1.markdown(f"**Size:** {listing.get('size') or '—'}")
        col1.markdown(f"**Price:** {listing.get('price') or '—'}")
        col2.markdown(f"**Location:** {listing.get('location') or '—'}")
        col2.markdown(f"**Title:** {listing.get('title_type') or '—'}")
        if listing.get("fee_note"):
            st.markdown(f"**Fee note:** {listing['fee_note']}")
        st.markdown(f"**Contact:** {listing.get('seller_contact') or '—'}")
        seller_wa_link = listing_format.seller_whatsapp_link(listing.get("seller_contact", ""), listing.get("heading", ""))
        if seller_wa_link:
            st.markdown(f"[Message seller on WhatsApp]({seller_wa_link})")
        if listing.get("video_url"):
            st.markdown(f"🎥 [Video]({listing['video_url']})")
        photo_paths = listing.get("photo_paths") or []
        if photo_paths:
            st.markdown(f"**Photos ({len(photo_paths)}):**")
            photo_cols = st.columns(min(len(photo_paths), 4))
            for i, photo_path in enumerate(photo_paths):
                photo_url = file_handler.resolve_photo_url(photo_path)
                if photo_url:
                    photo_cols[i % len(photo_cols)].image(photo_url, use_container_width=True)
        st.caption(f"Submitted {listing.get('submitted_at', '?')}")

        if listing.get("risk_result"):
            st.markdown(f"**Automated risk check: {listing['risk_level']}**")
            for finding in listing["risk_result"].get("findings", []):
                st.caption(f"- {finding}")
        elif listing.get("coordinates_text"):
            if st.button("Run risk check now", key=f"run_check_{listing['id']}"):
                try:
                    # Reuses the exact projection the seller picked at
                    # submission (utils/listings.py's coordinate_epsg) -
                    # re-guessing here could silently convert the same
                    # Northing/Easting pair to a different real-world
                    # location than what the seller actually meant.
                    points, _, _, _ = coordinates.parse_coordinate_text(
                        listing["coordinates_text"], forced_epsg=listing.get("coordinate_epsg")
                    )
                    if not points:
                        st.error("Couldn't extract coordinates from the submitted text.")
                    else:
                        boundary_issue = gis_processing.check_boundary_validity(points) if len(points) >= 3 else None
                        if boundary_issue:
                            st.error(boundary_issue)
                        else:
                            neighbors_gdf = gis_processing.load_neighboring_plots()
                            user_gdf = gis_processing.build_user_plot_gdf(points)
                            overlap_result = gis_processing.analyze_overlap(user_gdf, neighbors_gdf)
                            risk_result = risk_calculator.calculate_risk(
                                points, overlap_result, boundary_is_measured=len(points) >= 3
                            )
                            listings.update_listing(
                                listing["id"], points=points,
                                risk_level=risk_result["risk_level"], risk_result=risk_result,
                            )
                            st.success(f"Risk check complete: {risk_result['risk_level']}")
                            st.rerun()
                except Exception as exc:
                    traceback.print_exc()
                    st.error(f"Risk check failed: {exc}")
        else:
            st.caption("No coordinates were submitted - use the override below to set a rating by hand.")

        override_options = ["(none)", "Low", "Medium", "High"]
        current_override = listing.get("admin_risk_override")
        override = st.selectbox(
            "Risk rating override", override_options,
            index=override_options.index(current_override) if current_override in override_options else 0,
            key=f"override_{listing['id']}",
        )
        if st.button("Save override", key=f"save_override_{listing['id']}"):
            listings.update_listing(listing["id"], admin_risk_override=None if override == "(none)" else override)
            st.rerun()

        verified = st.checkbox(
            "Mark PlotProof Verification as paid", value=listing.get("verified", False), key=f"verified_{listing['id']}"
        )
        if verified != listing.get("verified", False):
            listings.update_listing(listing["id"], verified=verified)
            st.rerun()

        if listing["status"] == listings.STATUS_PUBLISHED:
            sold = st.checkbox(
                "Mark as Sold (removes it from the public Browse Listings page)",
                value=listing.get("sold", False), key=f"sold_{listing['id']}",
            )
            if sold != listing.get("sold", False):
                listings.update_listing(
                    listing["id"], sold=sold,
                    sold_at=datetime.now(timezone.utc).isoformat() if sold else None,
                )
                st.rerun()

        col_pub, col_rej, col_del = st.columns(3)
        if listing["status"] != listings.STATUS_PUBLISHED:
            if col_pub.button("Publish", key=f"publish_{listing['id']}", type="primary"):
                listings.update_listing(
                    listing["id"], status=listings.STATUS_PUBLISHED,
                    reviewed_at=datetime.now(timezone.utc).isoformat(),
                    # Assigned once, kept forever after - a listing's Land
                    # Alert number is its public signature, so re-publishing
                    # (e.g. after a reject/undo) must never hand out a new
                    # one if it already has one.
                    alert_number=listing.get("alert_number") or listings.next_alert_number(),
                )
                st.rerun()
        if listing["status"] != listings.STATUS_REJECTED:
            if col_rej.button("Reject", key=f"reject_{listing['id']}"):
                listings.update_listing(
                    listing["id"], status=listings.STATUS_REJECTED,
                    reviewed_at=datetime.now(timezone.utc).isoformat(),
                )
                st.rerun()
        if col_del.button("Delete", key=f"delete_{listing['id']}"):
            listings.delete_listing(listing["id"])
            st.rerun()

        if listing["status"] == listings.STATUS_PUBLISHED:
            st.divider()
            st.markdown("**Share this listing**")
            listing_url = f"{app_url}/listings"
            plotproof_contact = app_config.get_plotproof_contact_number() or ""
            post_text = listing_format.format_listing_post(listing, listing_url, plotproof_contact)
            st.code(post_text, language=None)
            share_links = listing_format.build_share_links(post_text, listing_url)
            st.markdown(
                f"""
                <div class="pp-cta-row">
                  <a class="pp-cta pp-cta--solid" href="{share_links['whatsapp']}" target="_blank">WhatsApp</a>
                  <a class="pp-cta pp-cta--outline" href="{share_links['twitter']}" target="_blank">X / Twitter</a>
                  <a class="pp-cta pp-cta--outline" href="{share_links['telegram']}" target="_blank">Telegram</a>
                </div>
                """,
                unsafe_allow_html=True,
            )


with tab_listings:
    LISTINGS_APP_URL = os.environ.get("APP_URL", "https://plotproof.streamlit.app")
    st.caption(
        "Every submitted listing starts hidden until published here. Set/override the risk "
        "rating, mark verification as paid, then publish - published listings get pre-filled "
        "share links below."
    )

    st.markdown("**PlotProof contact number**")
    st.caption(
        "Shown to buyers on every public listing (never the seller's own number) - PlotProof "
        "stays the point of contact on both sides. A seller's own contact info is still "
        "collected at submission (visible per-listing below) so an admin can reach them once a "
        "buyer's interest comes in."
    )
    current_contact = app_config.get_plotproof_contact_number()
    st.text_input("Current number", value=current_contact or "(not set)", disabled=True)
    with st.form("plotproof_contact_form", clear_on_submit=True):
        new_contact = st.text_input("New number", placeholder="0801 234 5678")
        if st.form_submit_button("Save number", type="primary"):
            if new_contact.strip():
                app_config.set_plotproof_contact_number(new_contact)
                st.success("Contact number updated.")
                st.rerun()
            else:
                st.error("Enter a number before saving.")
    if current_contact and st.button("Clear contact number"):
        app_config.clear_plotproof_contact_number()
        st.rerun()

    st.divider()
    all_listings = listings.list_listings()
    pending_listings = [l for l in all_listings if l["status"] == listings.STATUS_PENDING]
    other_listings = [l for l in all_listings if l["status"] != listings.STATUS_PENDING]

    st.markdown(f"**Pending review ({len(pending_listings)})**")
    if not pending_listings:
        st.info("No listings waiting for review.")
    for pending_listing in pending_listings:
        _render_admin_listing(pending_listing, LISTINGS_APP_URL)

    st.divider()
    st.markdown(f"**Published / rejected ({len(other_listings)})**")
    if not other_listings:
        st.caption("Nothing here yet.")
    for other_listing in other_listings:
        _render_admin_listing(other_listing, LISTINGS_APP_URL)


def _render_admin_request(request: dict, app_url: str) -> None:
    badges = [request["status"]]
    if request.get("request_number"):
        badges.append(f"Request #{request['request_number']:03d}")
    if request.get("verified_buyer"):
        badges.append("VERIFIED BUYER")
    label = f"{request.get('heading') or 'Property wanted'} - {' | '.join(badges)}"

    with st.expander(label):
        st.text_area(
            "Raw text pasted by admin", value=request.get("raw_text", ""), height=80,
            disabled=True, key=f"req_raw_{request['id']}",
        )
        col1, col2 = st.columns(2)
        col1.markdown(f"**Budget:** {request.get('price_range') or '—'}")
        col1.markdown(f"**Size wanted:** {request.get('size') or '—'}")
        col2.markdown(f"**Location wanted:** {request.get('location') or '—'}")
        if request.get("requirements"):
            st.markdown(f"**Notes:** {request['requirements']}")
        st.caption(f"Posted {request.get('posted_at', '?')}")

        if request["status"] == property_requests.STATUS_ACTIVE:
            if st.button("Mark as Closed", key=f"close_req_{request['id']}"):
                property_requests.update_request(
                    request["id"], status=property_requests.STATUS_CLOSED,
                    closed_at=datetime.now(timezone.utc).isoformat(),
                )
                st.rerun()
        else:
            if st.button("Re-activate", key=f"reopen_req_{request['id']}"):
                property_requests.update_request(request["id"], status=property_requests.STATUS_ACTIVE, closed_at=None)
                st.rerun()
        if st.button("Delete", key=f"delete_req_{request['id']}"):
            property_requests.delete_request(request["id"])
            st.rerun()

        st.divider()
        st.markdown("**Share this request**")
        request_url = f"{app_url}/listings"
        plotproof_contact = app_config.get_plotproof_contact_number() or ""
        post_text = listing_format.format_property_request_post(request, request_url, plotproof_contact)
        st.code(post_text, language=None)
        share_links = listing_format.build_share_links(post_text, request_url)
        st.markdown(
            f"""
            <div class="pp-cta-row">
              <a class="pp-cta pp-cta--solid" href="{share_links['whatsapp']}" target="_blank">WhatsApp</a>
              <a class="pp-cta pp-cta--outline" href="{share_links['twitter']}" target="_blank">X / Twitter</a>
              <a class="pp-cta pp-cta--outline" href="{share_links['telegram']}" target="_blank">Telegram</a>
            </div>
            """,
            unsafe_allow_html=True,
        )


with tab_requests:
    st.caption(
        "Post a verified buyer's request directly - there's no public submission form for these, "
        "since PlotProof is vetting the buyer, not reviewing an outside submission. Paste the "
        "buyer's brief, review the parsed fields, and post - it's live on the public Property "
        "Requests tab immediately."
    )

    st.markdown("**Post a new request**")
    request_raw = st.text_area(
        "Paste the buyer's request",
        height=120,
        placeholder=(
            "Serious Buyer Seeking Land Along Lekki-Epe Expressway\nBudget: 80M - 150M Naira\n"
            "Location: Lekki-Epe Expressway corridor\nSize: 500-1000 Sqm\n"
            "Buyer wants C of O title, ready to inspect this week."
        ),
        key="_req_raw_text",
    )
    if st.button("Parse fields", key="_req_parse_btn"):
        parsed = listing_format.parse_property_request_text(request_raw)
        for field, value in parsed.items():
            st.session_state[f"_req_{field}"] = value
        st.rerun()

    st.markdown("**Fields (edit if parsing missed anything)**")
    req_heading = st.text_input("Heading", key="_req_heading")
    col_a, col_b = st.columns(2)
    req_price_range = col_a.text_input("Budget / price range", key="_req_price_range")
    req_size = col_b.text_input("Size wanted (optional)", key="_req_size")
    req_location = st.text_input("Location wanted", key="_req_location")
    req_requirements = st.text_area("Additional notes (optional)", key="_req_requirements", height=80)
    req_verified_buyer = st.checkbox("Verified buyer (PlotProof has vetted this buyer)", value=True, key="_req_verified_buyer")

    if st.button("Post request", type="primary", key="_req_post_btn"):
        if not req_heading.strip() and not request_raw.strip():
            st.error("Paste the buyer's request or fill in at least a heading.")
        else:
            new_request_id = property_requests.add_request(
                raw_text=request_raw,
                heading=req_heading.strip() or "Property wanted",
                price_range=req_price_range.strip(),
                location=req_location.strip(),
                size=req_size.strip(),
                requirements=req_requirements.strip(),
                verified_buyer=req_verified_buyer,
                request_number=property_requests.next_request_number(),
            )
            st.success("Request posted - now live on the public Property Requests tab.")

    st.divider()
    all_requests = property_requests.list_requests()
    active_reqs = [r for r in all_requests if r["status"] == property_requests.STATUS_ACTIVE]
    closed_reqs = [r for r in all_requests if r["status"] != property_requests.STATUS_ACTIVE]

    st.markdown(f"**Active requests ({len(active_reqs)})**")
    if not active_reqs:
        st.info("No active requests.")
    for active_req in active_reqs:
        _render_admin_request(active_req, LISTINGS_APP_URL)

    st.divider()
    st.markdown(f"**Closed requests ({len(closed_reqs)})**")
    if not closed_reqs:
        st.caption("Nothing here yet.")
    for closed_req in closed_reqs:
        _render_admin_request(closed_req, LISTINGS_APP_URL)
