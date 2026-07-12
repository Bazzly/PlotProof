"""
Navigation entrypoint - kept deliberately thin.

The actual app content lives in app_home.py; this file only wires up
st.navigation() with position="hidden" so the admin portal's page is
reachable by direct URL but never appears in a sidebar nav for public
visitors to stumble onto (Streamlit's default pages/ auto-discovery would
otherwise list it as "admin review" for anyone). The URL slug itself comes
from ADMIN_URL_PATH (env var, not committed - see .env.example) so it
isn't guessable from reading this public repo either; content access is
still separately gated by ADMIN_PASSWORD inside pages/admin_review.py.

See ADMIN_ACCESS.md (gitignored, not in this repo) for this deployment's
actual admin URL and login instructions.
"""

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

ADMIN_URL_PATH = os.environ.get("ADMIN_URL_PATH", "admin-review")

home = st.Page("app_home.py", title="PlotProof", default=True)
admin = st.Page("pages/admin_review.py", title="Admin", url_path=ADMIN_URL_PATH)

st.navigation([home, admin], position="hidden").run()
