"""
Common Questions - New to Land Surveys? Hand-written answers, not a live
model call - fixed and reviewable, no per-question API cost, and can't
drift or hallucinate. Content lives in utils/faq_content.py, shared with
utils/assistant.py's fallback_answer() - the same reviewed Q&A this page
shows is also what the floating chat falls back to when the live Claude
API isn't reachable, so a fallback answer is never something improvised
just for that moment.

Broken out to its own page (rather than an expander on the main page or
in the sidebar) for the same reason as pages/about.py's Terms/Privacy
content - keeps the main tool focused on the actual land-boundary check;
reachable from the sidebar (utils/nav.py) on every page.
"""

import streamlit as st
from dotenv import load_dotenv

from utils import faq_content, icons, nav, theme

load_dotenv()

st.set_page_config(page_title="Common Questions - PlotProof", page_icon="assets/logo.svg", layout="centered")
st.markdown(theme.get_css(), unsafe_allow_html=True)
nav.render_sidebar()
nav.render_floating_chat()

st.markdown(
    f"""
    <div class="pp-hero">
      <div class="pp-logo">{icons.icon("logo", color="#ffffff", size=24, stroke_width=2.2)}</div>
      <div>
        <h1>Common Questions</h1>
        <p>New to land surveys? Start here.</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

for question, answer in faq_content.FAQ_ENTRIES:
    st.markdown(f"**{question}**\n\n{answer}")

st.page_link("app_home.py", label="← Back to the land risk check", icon="🧭")
