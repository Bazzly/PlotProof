"""
Shared sidebar navigation and floating chat, rendered identically on
every public-facing page (app_home.py, pages/about.py, pages/faq.py) so a
visitor always has a way back to the tool, the full Terms of
Service/Privacy Policy, or the FAQ, regardless of where they are in the
flow - all three used to sit inline on the main page (expanders); this is
what replaced that (see pages/about.py's and pages/faq.py's docstrings).

Deliberately doesn't touch the admin portal - that stays unlisted and
unlinked everywhere except its own direct URL, per app.py's docstring.
"""

import os
import traceback

import streamlit as st

from utils import icons, land_chat_match, land_chat_training, rate_limit

DAILY_LAND_CHAT_LIMIT = int(os.environ.get("DAILY_LAND_CHAT_LIMIT", "10"))
BURST_MAX_REQUESTS = int(os.environ.get("BURST_MAX_REQUESTS", "10"))
BURST_WINDOW_SECONDS = int(os.environ.get("BURST_WINDOW_SECONDS", "60"))


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


def render_floating_chat() -> None:
    """A floating chat bubble (pinned bottom-right via the
    st-key-pp_floating_chat CSS selector - utils/theme.py), available on
    every page once the consent gate's been accepted. Answers general
    land/PlotProof questions only, matched against admin-trained content
    (utils/land_chat_training.py, utils/land_chat_match.py) rather than a
    live model call - no external API, no document or result for this
    specific user, so every answer is followed by a real link back to
    the actual check rather than trying to answer anything plot-specific
    itself. Unlike the earlier Claude-backed version, answers are
    independent per question - there's no model to interpret a follow-up
    referring to a prior answer, so no conversation history is threaded
    into the match, even though the visible Q&A log below still shows
    the session's own questions/answers. Hidden entirely until at least
    one passage has been trained (land_chat_training.list_passages()) or
    before consent - see pages/admin_review.py's "Land Chat Training"
    tab for where that content comes from.

    The whole function - including the gating checks below, not just the
    render body - is wrapped in try/except - confirmed live (not
    hypothetical) that an unhandled error in here takes down every single
    page load for every visitor, since app.py's st.navigation().run()
    executes this at module level before the rest of the page renders.
    An optional add-on feature failing should never do that; it logs and
    silently doesn't render instead."""
    try:
        if not land_chat_training.list_passages() or not st.session_state.get("_consent_accepted"):
            return
        _render_floating_chat_body()
    except Exception:
        traceback.print_exc()


def _render_floating_chat_body() -> None:
    client_id = rate_limit.get_client_id()
    history_key = "_land_chat_history"
    question_key = "_land_chat_question"
    error_key = "_land_chat_error"

    def _handle_ask() -> None:
        # A st.button(on_click=...) callback, not inline code below the
        # button - runs (and can clear question_key) BEFORE the widget is
        # re-instantiated on the resulting rerun. See utils/assistant.py's
        # sibling feature (app_home.py's "Ask about this report") for why
        # clearing it after the button in a normal script run doesn't
        # actually reset a text_input in this Streamlit version.
        question = (st.session_state.get(question_key) or "").strip()
        st.session_state[question_key] = ""
        st.session_state[error_key] = None
        if not question:
            return
        if not rate_limit.check_burst_limit(client_id, BURST_MAX_REQUESTS, BURST_WINDOW_SECONDS):
            st.session_state[error_key] = "Too many requests in a short time. Please wait a minute and try again."
            return
        if not rate_limit.check_daily_limit(client_id, "land_chat", DAILY_LAND_CHAT_LIMIT)[0]:
            st.session_state[error_key] = f"You've reached today's limit of {DAILY_LAND_CHAT_LIMIT} chat questions per day."
            return

        result = land_chat_match.match(question)
        if result is None:
            answer = (
                "I haven't been trained on anything yet - check back soon, or use the link "
                "below to start a real check."
            )
        else:
            answer = result["passage"]["text"]
            if result["low_confidence"]:
                answer += "\n\n*(Closest topic I have - this may not directly answer your question.)*"

        history = st.session_state.get(history_key, [])
        history.append((question, answer))
        st.session_state[history_key] = history

    # st.popover (preferred - reads as a real floating panel) isn't in
    # every Streamlit version this app might end up running under
    # (requirements.txt pins a lower bound, not an exact version) -
    # st.expander is an always-available equivalent for this simple
    # question-box-plus-history use case if popover isn't present.
    trigger = st.popover if hasattr(st, "popover") else st.expander
    with st.container(key="pp_floating_chat"):
        with trigger("💬 Ask about land & PlotProof"):
            st.markdown("**Ask about land or PlotProof**")
            st.caption(
                "Answers come from trained topics, not a live model - each question is answered "
                "on its own, no follow-up memory. I don't have access to any document or result "
                "of yours. For a real check on your own land, upload a survey plan or enter "
                "coordinates."
            )
            for q, a in st.session_state.get(history_key, []):
                st.markdown(f"**You:** {q}")
                st.markdown(f"**PlotProof:** {a}")
                st.divider()
            if st.session_state.get(error_key):
                st.error(st.session_state[error_key])
            st.text_input(
                "Ask a question",
                key=question_key,
                placeholder="What is a survey plan? How does PlotProof work?",
                label_visibility="collapsed",
            )
            st.button("Ask", key="_land_chat_ask", on_click=_handle_ask)
            st.divider()
            st.page_link("app_home.py", label="Start using PlotProof - upload your document", icon="🧭")
