"""
Navigation entrypoint - kept deliberately thin.

The actual app content lives in app_home.py/pages/about.py/pages/faq.py/
pages/investment_analysis.py/pages/listings.py;
this file only wires up st.navigation(). position="hidden" turns off
Streamlit's own built-in nav UI (which would otherwise auto-list every
page, including the admin portal, in a visible sidebar for any visitor) -
the public-facing sidebar nav visitors actually see (Home / About & Legal
/ Common Questions) is rendered manually instead, via utils/nav.py's
render_sidebar(), called from each public page and deliberately omitting
the admin page. The admin portal is reachable by direct URL only. The URL
slug comes from ADMIN_URL_PATH (env var, not committed - see
.env.example) so it isn't guessable from reading this public repo
either; content access is still separately gated by ADMIN_PASSWORD
inside pages/admin_review.py.

See ADMIN_ACCESS.md (gitignored, not in this repo) for this deployment's
actual admin URL and login instructions.
"""

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

ADMIN_URL_PATH = os.environ.get("ADMIN_URL_PATH", "admin-review")

home = st.Page("app_home.py", title="PlotProof", default=True)
about = st.Page("pages/about.py", title="About & Legal", url_path="about")
faq = st.Page("pages/faq.py", title="Common Questions", url_path="faq")
investment = st.Page("pages/investment_analysis.py", title="Investment Analysis", url_path="investment-analysis")
listings = st.Page("pages/listings.py", title="Land Listings", url_path="listings")
diagonal_calculator = st.Page("pages/diagonal_calculator.py", title="Diagonal Calculator", url_path="diagonal-calculator")
admin = st.Page("pages/admin_review.py", title="Admin", url_path=ADMIN_URL_PATH)

st.navigation([home, about, faq, investment, listings, diagonal_calculator, admin], position="hidden").run()
