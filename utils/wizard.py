"""
Shared step-indicator components for multi-step flows - used by
app_home.py's single-check/compare flows and pages/investment_analysis.py.

Extracted out of app_home.py (a script, not an importable module - importing
from it directly would re-execute its whole top-level flow) so any page can
reuse the exact same stepper without duplicating it.
"""

from typing import List, Optional

import streamlit as st


def step_header(number: Optional[int], label: str) -> None:
    badge = f'<span class="pp-step-num">{number}</span>' if number is not None else ""
    st.markdown(f'<div class="pp-step">{badge}<h2>{label}</h2></div>', unsafe_allow_html=True)


def render_wizard(labels: List[str], current: int) -> None:
    """Horizontal stepper shown at the top of a multi-step flow - done/
    active/upcoming steps styled distinctly via utils/theme.py's
    .pp-wizard-* classes, so a user always sees where they are and how
    much is left, TurboTax/Stripe-onboarding style, rather than one long
    page of every field at once."""
    parts = []
    for i, label in enumerate(labels, start=1):
        if i < current:
            step_css, circle = "pp-wizard-step--done", "&#10003;"
        elif i == current:
            step_css, circle = "pp-wizard-step--active", str(i)
        else:
            step_css, circle = "", str(i)
        parts.append(
            f'<div class="pp-wizard-step {step_css}"><div class="pp-wizard-step-circle">{circle}</div>'
            f'<div class="pp-wizard-step-label">{label}</div></div>'
        )
        if i < len(labels):
            connector_css = "pp-wizard-connector--done" if i < current else ""
            parts.append(f'<div class="pp-wizard-connector {connector_css}"></div>')
    st.markdown(f'<div class="pp-wizard">{"".join(parts)}</div>', unsafe_allow_html=True)
