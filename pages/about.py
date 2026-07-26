"""
About & Legal - the long-form content (what PlotProof is, the full Terms
of Service, the full Privacy Policy) that used to sit inline in
app_home.py behind expanders - once in the consent gate, again at the
bottom of the results flow. Broken out to its own page so the main tool
stays focused on the actual land-boundary check rather than legal
boilerplate; reachable from the sidebar (utils/nav.py) on every page, and
specifically linked from the consent gate before a user agrees.
"""

import streamlit as st
from dotenv import load_dotenv

from utils import icons, legal, nav, theme

load_dotenv()

st.set_page_config(page_title="About & Legal - PlotProof", page_icon="assets/logo.svg", layout="centered")
st.markdown(theme.get_css(), unsafe_allow_html=True)
nav.render_sidebar()
nav.render_floating_chat()

st.markdown(
    f"""
    <div class="pp-hero">
      <div class="pp-logo">{icons.icon("logo", color="#ffffff", size=24, stroke_width=2.2)}</div>
      <div>
        <h1>About PlotProof</h1>
        <p>What this tool is, and the fine print</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="pp-card">
      <div class="pp-card-title">What PlotProof does</div>
      <p>PlotProof reads a survey plan (or manually entered coordinates) and checks the
      boundary it describes against known neighboring plots for overlaps and close-proximity
      risks - an instant, automated first pass before you commit time or money to a land
      purchase. It's an automated preliminary screening tool, not a certified survey or legal
      opinion - always get a licensed surveyor's verification and proper legal due diligence
      before any property transaction.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("## Terms of Service")
st.markdown(legal.get_terms())

st.markdown("## Privacy Policy")
st.markdown(legal.get_privacy_policy())

st.page_link("app_home.py", label="← Back to the land risk check", icon="🧭")
