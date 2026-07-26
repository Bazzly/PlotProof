"""
Shared sidebar navigation, rendered identically on every public-facing
page (app_home.py, pages/about.py, pages/faq.py) so a visitor always has
a way back to the tool, the full Terms of Service/Privacy Policy, or the
FAQ, regardless of where they are in the flow - all three used to sit
inline on the main page (expanders); this is what replaced that (see
pages/about.py's and pages/faq.py's docstrings).

Deliberately doesn't touch the admin portal - that stays unlisted and
unlinked everywhere except its own direct URL, per app.py's docstring.
"""

import streamlit as st

from utils import icons


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            f"""
            <div class="pp-sidebar-brand">
              <div class="pp-logo">{icons.icon("logo", color="#ffffff", size=18, stroke_width=2.2)}</div>
              <span>PlotProof</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link("app_home.py", label="Land Risk Check", icon="🧭")
        st.page_link("pages/about.py", label="About & Legal", icon="📄")
        st.page_link("pages/faq.py", label="Common Questions", icon="❓")
