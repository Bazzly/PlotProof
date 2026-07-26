"""
Common Questions - New to Land Surveys? Hand-written answers, not a live
model call - fixed and reviewable, no per-question API cost, and can't
drift or hallucinate. Shares RISK_EXPLAINER with the results page's own
"What does this risk level mean?" expander (utils/theme.py) so the two
can never end up disagreeing.

Broken out to its own page (rather than an expander on the main page or
in the sidebar) for the same reason as pages/about.py's Terms/Privacy
content - keeps the main tool focused on the actual land-boundary check;
reachable from the sidebar (utils/nav.py) on every page.
"""

import streamlit as st
from dotenv import load_dotenv

from utils import icons, nav, theme

load_dotenv()

st.set_page_config(page_title="Common Questions - PlotProof", page_icon="assets/logo.svg", layout="centered")
st.markdown(theme.get_css(), unsafe_allow_html=True)
nav.render_sidebar()

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

st.markdown(
    f"""
**What is a survey plan?**
The official document a licensed surveyor produces after measuring your land - it shows your
plot's boundary, corner coordinates, and size. It's what PlotProof reads to check your boundary.

**What are coordinates?**
Numbers that pinpoint each corner of your land on a map - usually latitude/longitude, or a local
Easting/Northing pair tied to a specific coordinate system. Your survey plan normally lists these
for every corner ("beacon").

**Why might my land get flagged?**
- **Low risk** - {theme.RISK_EXPLAINER['Low']}
- **Medium risk** - {theme.RISK_EXPLAINER['Medium']}
- **High risk** - {theme.RISK_EXPLAINER['High']}

**Can I buy this land?**
PlotProof isn't a legal opinion and can't answer that directly. A Low risk result is a good sign,
but it only reflects plots currently on record - always get a licensed surveyor's verification and
proper legal due diligence (e.g. a title search) before any transaction.

**What's in my downloaded report?**
The PDF includes your boundary coordinates, the risk level, the specific findings behind it,
recommendations, and a map showing your plot against nearby registered plots - bring it to a
licensed surveyor if you want a professional opinion on it. CSV and GeoJSON downloads (the raw
coordinates/boundary, no formatting) are also available after a check completes.
    """
)

st.page_link("app_home.py", label="← Back to the land risk check", icon="🧭")
