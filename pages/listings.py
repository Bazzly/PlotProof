"""
Land Listings marketplace - a seller pastes their raw sales message into
one box, PlotProof auto-formats it into a listing (utils/listing_format.py
- a Python port of the field-extraction the standalone
plotproof-generator.html prototype demonstrated client-side), optionally
runs the same real risk-check pipeline app_home.py uses against submitted
coordinates, and every submission starts hidden ("pending") until an
admin reviews and publishes it from pages/admin_review.py's "Listings"
tab - same trust gate this app already applies to other shared data
(the plot registry, land-chat training content).

Published listings show here on the Browse tab, PlotProof-Verified ones
ranked above unverified ones (utils/listings.list_published_ranked()).
"Verified" is a paid, admin-confirmed status - there's no in-app payment
processing (see utils/listings.py's module docstring); a seller requests
it, an admin follows up and marks it once paid.

The third tab, Property Requests, is the inverse: a verified buyer's ask
("looking for land in this price range/location"), posted only by an
admin (utils/property_requests.py) - not a public submission form, since
there's no external submitter to review here, PlotProof already vetted
the buyer before posting on their behalf. Anyone with matching land
contacts PlotProof (same intermediary model as Land Listings) to arrange
a physical meeting.

Broken out to its own page (not the sidebar/inline on the main flow) for
the same reason as pages/about.py, pages/faq.py, pages/investment_analysis.py
- reachable from the sidebar (utils/nav.py) on every page.
"""

import os
import traceback

import streamlit as st
from dotenv import load_dotenv

from utils import app_config, coordinates, crs_utils, file_handler, gis_processing, icons, listing_format, listings, nav, property_requests, rate_limit, risk_calculator, theme

load_dotenv()

st.set_page_config(page_title="Land Listings - PlotProof", page_icon="assets/logo.svg", layout="centered")
st.markdown(theme.get_css(), unsafe_allow_html=True)
nav.render_sidebar()
nav.render_floating_chat()

DAILY_LISTING_LIMIT = int(os.environ.get("DAILY_LISTING_LIMIT", "3"))
MAX_LISTING_PHOTOS = 6
BURST_MAX_REQUESTS = int(os.environ.get("BURST_MAX_REQUESTS", "10"))
BURST_WINDOW_SECONDS = int(os.environ.get("BURST_WINDOW_SECONDS", "60"))
CLIENT_ID = rate_limit.get_client_id()

# Most Nigerian survey plans give Northing/Easting on the Minna datum, UTM
# zone 31N - not GPS latitude/longitude - so that's the default projection
# here (unlike app_home.py's picker, which defaults to Auto-detect: a
# seller pasting raw plan coordinates usually knows they're local, not
# GPS, even if they don't know the exact zone/belt). A pair that's
# actually already plain lat/lon is detected by magnitude
# (utils/crs_utils.looks_projected()) before any projection is ever
# applied, so this default is safe either way - see
# utils/coordinates.parse_coordinate_text()'s docstring.
CRS_OPTIONS = {"Minna / UTM zone 31N (most common)": "EPSG:26331", "I have GPS coordinates already": None}
CRS_OPTIONS.update({name: epsg for epsg, name in crs_utils.NIGERIA_CRS_CANDIDATES.items() if epsg != "EPSG:26331"})

st.markdown(
    f"""
    <div class="pp-hero">
      <div class="pp-logo">{icons.icon("map-pin", color="#ffffff", size=24, stroke_width=2.2)}</div>
      <div>
        <h1>Land Listings</h1>
        <p>Browse land for sale, or list your own - paste your sales message and we'll format
        and (optionally) risk-check it for you.</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_browse, tab_sell, tab_requests = st.tabs(["Browse Listings", "Sell Your Land", "Property Requests"])

with tab_browse:
    published = listings.list_published_ranked()
    if not published:
        st.info("No listings published yet - check back soon, or be the first to list on the Sell Your Land tab.")
    else:
        for listing in published:
            risk_level = listings.effective_risk_level(listing)
            sold = bool(listing.get("sold"))
            ribbons = ""
            if listing.get("verified"):
                ribbons += f'<div class="pp-verified-ribbon">{icons.icon("check-circle", size=12)}Verified</div>'
            if sold:
                ribbons += '<div class="pp-sold-ribbon">Sold</div>'
            risk_html = ""
            if risk_level:
                status = theme.RISK_TO_STATUS.get(risk_level, "warning")
                risk_icon = theme.RISK_TO_ICON.get(risk_level, "info")
                risk_html = (
                    f'<div class="pp-badge-risk" style="--pp-status: var(--pp-{status}); '
                    f'margin-top: var(--pp-space-3);">{icons.icon(risk_icon, size=16)} {risk_level} Risk</div>'
                )
            card_class = "pp-listing-card pp-listing-card--sold" if sold else "pp-listing-card"
            st.markdown(
                f"""
                <div class="{card_class}">
                  <div class="pp-listing-ribbons">{ribbons}</div>
                  <div class="pp-listing-heading">{listing.get('heading') or 'Land for sale'}</div>
                  <p class="pp-listing-meta"><strong>Size:</strong> {listing.get('size') or '—'}</p>
                  <p class="pp-listing-meta"><strong>Price:</strong> {listing.get('price') or '—'}</p>
                  <p class="pp-listing-meta"><strong>Location:</strong> {listing.get('location') or '—'}</p>
                  <p class="pp-listing-meta"><strong>Title:</strong> {listing.get('title_type') or '—'}</p>
                  {risk_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

            photo_paths = listing.get("photo_paths") or []
            if photo_paths:
                photo_cols = st.columns(min(len(photo_paths), 4))
                for i, photo_path in enumerate(photo_paths[:4]):
                    photo_url = file_handler.resolve_photo_url(photo_path)
                    if photo_url:
                        photo_cols[i % len(photo_cols)].image(photo_url, use_container_width=True)

            if listing.get("video_url"):
                st.markdown(f"🎥 [Watch video]({listing['video_url']})")

            # PlotProof's own number, not the seller's - PlotProof stays
            # the point of contact on both sides (see
            # utils/app_config.get_plotproof_contact_number()'s docstring).
            contact_link = listing_format.plotproof_contact_link(listing, app_config.get_plotproof_contact_number() or "")
            with st.container(key=f"pp_listing_contact_{listing['id']}"):
                if sold:
                    st.caption("This listing has been marked sold.")
                elif contact_link:
                    st.markdown(
                        f"""<div class="pp-cta-row"><a class="pp-cta pp-cta--solid" href="{contact_link}"
                        target="_blank">{icons.icon("chat", color="#ffffff", size=16)} Enquire about this listing</a></div>""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("Contact details unavailable right now - please check back soon.")
            st.divider()

with tab_sell:
    st.caption(
        "Paste your sales message below - we'll pull out the size, price, location, and title "
        "automatically. Add coordinates if you have them for a real PlotProof risk check. Every "
        "listing is reviewed by an admin before it goes live."
    )

    raw_text = st.text_area(
        "Paste your sales message",
        height=150,
        placeholder=(
            "Residential Land for Sale !!!\nSize: 1,200 Sqm\nPrice: 450M Naira\n"
            "Location: Kado - Abuja (Tarred Road)\nTitle: C of O\nBrokers fee applies"
        ),
        key="_listing_raw_text",
    )
    if st.button("Parse fields"):
        parsed = listing_format.parse_listing_text(raw_text)
        for field, value in parsed.items():
            st.session_state[f"_listing_{field}"] = value
        st.rerun()

    st.markdown("**Fields (edit if parsing missed anything)**")
    heading = st.text_input("Heading", key="_listing_heading")
    col1, col2 = st.columns(2)
    size = col1.text_input("Size", key="_listing_size")
    price = col2.text_input("Price", key="_listing_price")
    location = st.text_input("Location", key="_listing_location")
    col3, col4 = st.columns(2)
    title_type = col3.text_input("Title", key="_listing_title_type")
    fee_note = col4.text_input("Fee note (optional)", key="_listing_fee_note")
    seller_contact = st.text_input(
        "Your WhatsApp/phone number",
        key="_listing_seller_contact",
        help=(
            "Not shown publicly. Buyers enquire through PlotProof, and an admin uses this to "
            "reach you - PlotProof stays the point of contact on both sides."
        ),
    )

    st.divider()
    st.markdown("**Add coordinates for a real risk check (optional)**")
    st.caption(
        "Paste boundary coordinates or upload your survey plan - this runs the same overlap/"
        "proximity check used on the main Land Risk Check, and shows the real result on your "
        "listing instead of an unverified claim. Most survey plans give local Northing/Easting "
        "coordinates, not GPS - paste those directly and pick the projection below; PlotProof "
        "converts them to real-world coordinates automatically."
    )
    selected_crs_label = st.selectbox(
        "Projection",
        options=list(CRS_OPTIONS.keys()),
        index=0,
        key="_listing_crs_override",
        help=(
            "Most Nigerian survey plans are drawn on the Minna datum, UTM zone 31N - the default "
            "here. Only change this if your plan states a different zone/belt, or select \"I have "
            "GPS coordinates already\" if you're pasting plain latitude/longitude instead."
        ),
    )
    forced_epsg = CRS_OPTIONS[selected_crs_label]
    coords_text = st.text_area(
        "Coordinates (one pair per line: Northing, Easting - or latitude, longitude if you selected GPS above)",
        height=100,
        key="_listing_coords_text",
        placeholder="746412.50, 547890.20\n746420.10, 547895.60\n...\n\nor GPS: 6.5244, 3.3792",
    )
    uploaded_plan = st.file_uploader(
        "Or upload a survey plan (PDF or image)", type=["pdf", "png", "jpg", "jpeg"], key="_listing_plan_upload"
    )

    st.divider()
    st.markdown(f"**Photos & video (optional, up to {MAX_LISTING_PHOTOS} photos)**")
    st.caption("Photos are automatically resized and compressed - no need to shrink them yourself first.")
    uploaded_photos = st.file_uploader(
        "Photos of the land",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="_listing_photos",
    )
    if uploaded_photos and len(uploaded_photos) > MAX_LISTING_PHOTOS:
        st.warning(f"Only the first {MAX_LISTING_PHOTOS} photos will be used.")
    video_url = st.text_input(
        "Video link", key="_listing_video_url",
        placeholder="YouTube, Instagram, TikTok, etc.",
    )

    st.divider()
    verification_requested = st.checkbox(
        "Request PlotProof Verification (paid)",
        key="_listing_verification_requested",
        help=(
            "An admin will review your listing and follow up to arrange payment - nothing is "
            "charged here. Verified listings rank higher and get a Verified badge."
        ),
    )

    if st.button("Submit listing", type="primary"):
        if not rate_limit.check_burst_limit(CLIENT_ID, BURST_MAX_REQUESTS, BURST_WINDOW_SECONDS):
            st.error("Too many requests in a short time. Please wait a minute and try again.")
        elif not rate_limit.check_daily_limit(CLIENT_ID, "listing_submit", DAILY_LISTING_LIMIT)[0]:
            st.error(f"You've reached today's limit of {DAILY_LISTING_LIMIT} listing submissions per day.")
        elif not (heading.strip() or raw_text.strip()):
            st.error("Please paste your sales message or fill in at least a heading.")
        elif not seller_contact.strip():
            st.error("Please add a contact number so buyers can reach you.")
        else:
            points, risk_level, risk_result, crs_note = None, None, None, None
            text_for_parsing = coords_text
            pdf_path = None

            try:
                if uploaded_plan is not None:
                    saved_path = file_handler.save_uploaded_file(uploaded_plan)
                    extracted_text, _ = file_handler.extract_text_from_file(saved_path)
                    text_for_parsing = f"{text_for_parsing}\n{extracted_text}" if text_for_parsing else extracted_text
                    if saved_path.lower().endswith(".pdf") and file_handler.storage_backend() == "local":
                        pdf_path = saved_path

                if text_for_parsing and text_for_parsing.strip():
                    parsed_points, crs_note, _, _ = coordinates.parse_coordinate_text(
                        text_for_parsing, pdf_path=pdf_path, forced_epsg=forced_epsg
                    )
                    if parsed_points:
                        points = parsed_points
                        boundary_issue = gis_processing.check_boundary_validity(points) if len(points) >= 3 else None
                        if not boundary_issue:
                            neighbors_gdf = gis_processing.load_neighboring_plots()
                            user_gdf = gis_processing.build_user_plot_gdf(points)
                            overlap_result = gis_processing.analyze_overlap(user_gdf, neighbors_gdf)
                            risk_result = risk_calculator.calculate_risk(
                                points, overlap_result, boundary_is_measured=len(points) >= 3
                            )
                            risk_level = risk_result["risk_level"]
            except Exception:
                traceback.print_exc()
                st.warning(
                    "Couldn't process the coordinates/plan - your listing will still be submitted "
                    "without a risk check; an admin can add one later."
                )

            photo_paths = []
            for photo in (uploaded_photos or [])[:MAX_LISTING_PHOTOS]:
                try:
                    photo_paths.append(file_handler.save_listing_photo(photo))
                except Exception:
                    traceback.print_exc()
                    st.warning(f"Couldn't process one of the photos ({photo.name}) - skipped it.")

            listing_id = listings.add_listing(
                raw_text=raw_text,
                heading=heading.strip() or "Land for sale",
                size=size.strip(),
                price=price.strip(),
                location=location.strip(),
                title_type=title_type.strip(),
                fee_note=fee_note.strip(),
                seller_contact=seller_contact.strip(),
                coordinates_text=text_for_parsing or None,
                coordinate_epsg=forced_epsg,
                points=points,
                photo_paths=photo_paths,
                video_url=video_url.strip() or None,
                risk_level=risk_level,
                risk_result=risk_result,
                verification_requested=verification_requested,
            )
            success_message = (
                "Your listing has been submitted and is under review - it'll appear on the "
                "Browse Listings tab once an admin approves it."
            )
            if risk_level:
                success_message += f" Real risk check completed: **{risk_level}**."
                if crs_note:
                    success_message += f" Coordinates converted from {crs_note}."
            st.success(success_message)

with tab_requests:
    st.caption(
        "Verified buyers PlotProof is actively working with, looking for land in a specific "
        "price range or location. Have property that matches? Contact PlotProof below to arrange "
        "a physical meeting - these are posted by PlotProof directly, not open submissions."
    )
    public_requests = property_requests.list_public_ranked()
    if not public_requests:
        st.info("No property requests right now - check back soon.")
    else:
        for request in public_requests:
            closed = request["status"] == property_requests.STATUS_CLOSED
            ribbons = ""
            if request.get("verified_buyer"):
                ribbons += f'<div class="pp-verified-ribbon">{icons.icon("check-circle", size=12)}Verified Buyer</div>'
            if closed:
                ribbons += '<div class="pp-sold-ribbon">Closed</div>'
            card_class = "pp-listing-card pp-listing-card--sold" if closed else "pp-listing-card"
            st.markdown(
                f"""
                <div class="{card_class}">
                  <div class="pp-listing-ribbons">{ribbons}</div>
                  <div class="pp-listing-heading">{request.get('heading') or 'Property wanted'}</div>
                  <p class="pp-listing-meta"><strong>Budget:</strong> {request.get('price_range') or '—'}</p>
                  <p class="pp-listing-meta"><strong>Location wanted:</strong> {request.get('location') or '—'}</p>
                  <p class="pp-listing-meta"><strong>Size wanted:</strong> {request.get('size') or '—'}</p>
                  {f'<p class="pp-listing-meta">{request["requirements"]}</p>' if request.get('requirements') else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )
            request_contact_link = listing_format.property_request_contact_link(
                request, app_config.get_plotproof_contact_number() or ""
            )
            with st.container(key=f"pp_request_contact_{request['id']}"):
                if closed:
                    st.caption("This request has been closed.")
                elif request_contact_link:
                    st.markdown(
                        f"""<div class="pp-cta-row"><a class="pp-cta pp-cta--solid" href="{request_contact_link}"
                        target="_blank">{icons.icon("chat", color="#ffffff", size=16)} I have matching land</a></div>""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("Contact details unavailable right now - please check back soon.")
            st.divider()
