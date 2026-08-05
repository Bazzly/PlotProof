"""
Design tokens and injected CSS for PlotProof's UI.

Streamlit doesn't give real HTML/CSS control over its own widgets, so this
takes the practical middle path: a hand-written, Tailwind-style utility
theme (consistent color/spacing/radius scale) injected as a single <style>
block, plus CSS overrides targeting Streamlit's stable data-testid hooks
to reskin file upload/text area/buttons/checkboxes.

Palette and typography match the marketing landing page
("PlotProof Landing (standalone).html") - a warm cream/deep-green/gold
editorial look (Newsreader serif for headings, Work Sans for body), rather
than a generic dashboard blue. Values below are hex conversions of that
page's oklch() colors (ReportLab, used for the PDF report, has no oklch
support, and keeping one color space avoids the CSS and the PDF silently
drifting apart - see INK's docstring).

Color roles follow a validated status palette (see the dataviz skill):
status hues (good/warning/critical) carry meaning only together with an
icon + text label, never as flat color-on-text - see icon usage in
app.py. These are intentionally NOT tied to the brand palette above - a
risk badge should read the same regardless of what accent color the rest
of the UI is wearing.

Deliberately single-theme (light only), matching .streamlit/config.toml's
`base = "light"` - that config has no dark variant (Streamlit's [theme]
section is static, not reactive), so an earlier `@media
(prefers-color-scheme: dark)` override here that darkened custom .pp-*
backgrounds while every native Streamlit widget (checkboxes, radio
labels, captions, the footer) stayed on config.toml's fixed light-mode
text color produced dark-on-dark, barely-readable text - confirmed live
with Playwright's dark color-scheme emulation. Removed rather than fixed
piecemeal: making this genuinely dark-mode-safe would mean re-deriving a
full parallel palette for every native widget Streamlit itself renders,
not just the custom markup this file controls.
"""

# Fixed across light/dark - already validated to clear contrast on both surfaces.
STATUS = {
    "good": "#0ca30c",  # Low risk / no conflicting plot
    "warning": "#fab219",  # Medium risk / nearby plot
    "critical": "#d03b3b",  # High risk / overlapping plot
}

# Brand accent (deep green, oklch(38% 0.09 152) family). Gold is the
# secondary/CTA accent (oklch(78% 0.13 80)), used sparingly for the
# strongest calls to action, matching the landing page's hero button.
ACCENT_LIGHT = "#104f29"
GOLD = "#e3ad4b"
GOLD_INK = "#201308"

RISK_TO_STATUS = {"Low": "good", "Medium": "warning", "High": "critical"}
RISK_TO_ICON = {"Low": "check-circle", "Medium": "alert-triangle", "High": "alert-octagon"}

# Shared between the results page's "What does this risk level mean?"
# expander and the sidebar FAQ (utils/nav.py) - one copy so the two can
# never end up disagreeing about what a risk level means.
RISK_EXPLAINER = {
    "Low": "No known conflicts were found. This is a good sign, though it only reflects plots "
    "that are currently on record - it isn't a guarantee.",
    "Medium": "Something here is worth a closer look before you commit - either your boundary "
    "sits close to another plot, or there wasn't enough data to be fully certain.",
    "High": "Your boundary overlaps a plot that's already on record. This is a serious conflict "
    "that needs to be resolved before any transaction.",
}

# Light-mode chrome/ink tokens, factored out so anything that only ever
# renders on a white background (the PDF report - paper doesn't have a
# dark mode) can match the app's palette instead of hardcoding its own.
INK = {
    "surface": "#fbf8f1",
    "page": "#f9f5ec",
    "primary": "#25170c",
    "secondary": "#3b3129",
    "muted": "#845a0f",
    "gridline": "#ddd7c9",
    "border": "#d4cdbf",
}

FONT_HEADING = "'Newsreader', Georgia, serif"
FONT_BODY = "'Work Sans', -apple-system, BlinkMacSystemFont, sans-serif"


def get_css() -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,400;0,500;0,600;1,500&family=Work+Sans:wght@400;500;600;700&display=swap');

:root {{
  --pp-surface: {INK['surface']};
  --pp-page: {INK['page']};
  --pp-ink-primary: {INK['primary']};
  --pp-ink-secondary: {INK['secondary']};
  --pp-ink-muted: {INK['muted']};
  --pp-gridline: {INK['gridline']};
  --pp-border: {INK['border']};
  --pp-accent: {ACCENT_LIGHT};
  --pp-gold: {GOLD};
  --pp-gold-ink: {GOLD_INK};
  --pp-step-num-bg: #ddf1e1;
  --pp-step-num-ink: #034721;
  --pp-good: {STATUS['good']};
  --pp-warning: {STATUS['warning']};
  --pp-critical: {STATUS['critical']};
  --pp-font-heading: {FONT_HEADING};
  --pp-font-body: {FONT_BODY};
  --pp-radius: 16px;
  --pp-radius-pill: 999px;
  --pp-space-1: 4px;
  --pp-space-2: 8px;
  --pp-space-3: 12px;
  --pp-space-4: 16px;
  --pp-space-6: 24px;
}}
/* ---- staged reveal animation ---- */
/* Applied to any st.container(key="pp_stage_...") via substring match, so
   callers don't need a matching CSS rule per stage key - see app_home.py's
   progressive-disclosure flow (upload -> confirm coordinates -> analyze ->
   results), each wrapped in one of these containers so it fades/slides in
   the moment it first appears rather than the whole page being static. Runs
   once per mount - Streamlit keeps the same DOM node across reruns for a
   stable key, so editing something inside an already-revealed stage doesn't
   re-trigger it. prefers-reduced-motion turns it into an instant show,
   respecting that accessibility setting rather than forcing motion on everyone.
*/
@keyframes ppFadeInUp {{
  from {{ opacity: 0; transform: translateY(14px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
[class*="st-key-pp_stage_"] {{
  animation: ppFadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
}}
@media (prefers-reduced-motion: reduce) {{
  [class*="st-key-pp_stage_"] {{ animation-duration: 0.001ms !important; }}
}}

/* ---- global typography ---- */
.stApp, [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"],
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input,
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button,
[data-testid="stSelectbox"], [data-testid="stFileUploader"] {{
  font-family: var(--pp-font-body);
}}

/* ---- page shell ---- */
[data-testid="stAppViewContainer"], .stApp {{
  background: var(--pp-page);
}}
[data-testid="stMainBlockContainer"] {{
  max-width: 760px;
  padding-top: var(--pp-space-6);
}}

/* ---- landing hero (first-visit splash, before the tool itself) ---- */
.pp-landing-hero {{
  text-align: center;
  padding: var(--pp-space-6) 0 var(--pp-space-4);
}}
.pp-landing-hero .pp-logo {{
  width: 72px;
  height: 72px;
  border-radius: var(--pp-radius);
  margin: 0 auto var(--pp-space-4);
}}
.pp-landing-title {{
  font-family: var(--pp-font-heading);
  font-size: 2.1rem;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.01em;
  color: var(--pp-ink-primary);
  margin: 0 0 var(--pp-space-3);
}}
.pp-landing-sub {{
  font-size: 1.05rem;
  line-height: 1.55;
  color: var(--pp-ink-secondary);
  max-width: 46ch;
  margin: 0 auto;
}}
.pp-landing-steps {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--pp-space-4);
  margin: var(--pp-space-4) 0 var(--pp-space-6);
}}
@media (max-width: 640px) {{
  .pp-landing-steps {{ grid-template-columns: 1fr; }}
}}
.pp-landing-step {{
  background: var(--pp-surface);
  border: 1px solid var(--pp-border);
  border-radius: var(--pp-radius);
  padding: var(--pp-space-4);
}}
.pp-landing-step .pp-step-num {{ margin-bottom: var(--pp-space-2); }}
.pp-landing-step h3 {{
  font-family: var(--pp-font-heading);
  font-size: 1rem;
  font-weight: 600;
  color: var(--pp-ink-primary);
  margin: 0 0 4px;
}}
.pp-landing-step p {{
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--pp-ink-secondary);
  margin: 0;
}}
[class*="st-key-pp_landing_cta"] {{ text-align: center; margin: var(--pp-space-2) 0 var(--pp-space-4); }}
[class*="st-key-pp_landing_cta"] [data-testid="stButton"] button {{
  padding: 0.7rem 2.2rem;
  font-size: 1.02rem;
}}
.pp-landing-note {{
  text-align: center;
  color: var(--pp-ink-muted);
  font-size: 0.85rem;
  margin-top: var(--pp-space-2);
}}

/* ---- wizard stepper (multi-step flows: single check, compare) ---- */
.pp-wizard {{
  display: flex;
  align-items: flex-start;
  margin: var(--pp-space-2) 0 var(--pp-space-6);
}}
.pp-wizard-step {{
  flex: 0 1 130px;
  text-align: center;
  color: var(--pp-ink-muted);
}}
.pp-wizard-step-circle {{
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 6px;
  font-family: var(--pp-font-heading);
  font-weight: 600;
  font-size: 0.85rem;
  background: var(--pp-surface);
  border: 1.5px solid var(--pp-border);
  color: var(--pp-ink-muted);
}}
.pp-wizard-step-label {{
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.3;
}}
.pp-wizard-step--active .pp-wizard-step-circle {{
  background: var(--pp-accent);
  border-color: var(--pp-accent);
  color: #ffffff;
}}
.pp-wizard-step--active .pp-wizard-step-label {{ color: var(--pp-ink-primary); }}
.pp-wizard-step--done .pp-wizard-step-circle {{
  background: var(--pp-step-num-bg);
  border-color: var(--pp-step-num-bg);
  color: var(--pp-step-num-ink);
}}
.pp-wizard-step--done .pp-wizard-step-label {{ color: var(--pp-ink-secondary); }}
.pp-wizard-connector {{
  flex: 1 1 auto;
  min-width: 12px;
  height: 1.5px;
  background: var(--pp-border);
  margin-top: 14px;
}}
.pp-wizard-connector--done {{ background: var(--pp-accent); }}

/* ---- sidebar nav (utils/nav.py, every public page) ---- */
[data-testid="stSidebar"] {{
  background: var(--pp-surface);
  border-right: 1px solid var(--pp-border);
}}
.pp-sidebar-brand {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: var(--pp-space-4);
  font-family: var(--pp-font-heading);
  font-weight: 600;
  font-size: 1.05rem;
  color: var(--pp-ink-primary);
}}
.pp-sidebar-brand .pp-logo {{ width: 32px; height: 32px; border-radius: 10px; flex-shrink: 0; }}
[data-testid="stSidebar"] [data-testid="stPageLink"] {{
  border-radius: var(--pp-radius);
}}

/* ---- floating chat (utils/nav.py's render_floating_chat()) ----
   Pinned to the viewport regardless of scroll position - the trigger is
   an st.popover, which Streamlit positions its floating panel relative
   to via its own floating-ui layer, so pinning just this container is
   enough; the panel follows automatically. */
[class*="st-key-pp_floating_chat"] {{
  position: fixed;
  bottom: var(--pp-space-6);
  right: var(--pp-space-6);
  z-index: 999;
  width: auto;
}}
[class*="st-key-pp_floating_chat"] [data-testid="stPopover"] button {{
  border-radius: var(--pp-radius-pill);
  background: var(--pp-accent);
  color: #ffffff;
  border-color: var(--pp-accent);
  font-weight: 600;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
}}

/* ---- hero header ---- */
.pp-hero {{
  display: flex;
  align-items: center;
  gap: var(--pp-space-3);
  margin-bottom: var(--pp-space-2);
}}
.pp-logo {{
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--pp-radius);
  background: var(--pp-accent);
  color: #ffffff;
  flex-shrink: 0;
}}
.pp-hero h1 {{
  margin: 0;
  font-family: var(--pp-font-heading);
  font-size: 1.7rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--pp-ink-primary);
  line-height: 1.2;
}}
.pp-hero p {{
  margin: 2px 0 0;
  color: var(--pp-ink-secondary);
  font-size: 0.95rem;
}}
.pp-lede {{
  color: var(--pp-ink-secondary);
  margin: var(--pp-space-2) 0 var(--pp-space-6);
  line-height: 1.5;
}}

/* ---- step headers ---- */
.pp-step {{
  display: flex;
  align-items: center;
  gap: var(--pp-space-2);
  margin: var(--pp-space-6) 0 var(--pp-space-2);
}}
.pp-step-num {{
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: var(--pp-step-num-bg);
  color: var(--pp-step-num-ink);
  font-family: var(--pp-font-heading);
  font-size: 0.9rem;
  font-weight: 600;
  flex-shrink: 0;
}}
.pp-step h2 {{
  margin: 0;
  font-family: var(--pp-font-heading);
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--pp-ink-primary);
}}

/* ---- cards ---- */
.pp-card {{
  background: var(--pp-surface);
  border: 1px solid var(--pp-border);
  border-radius: var(--pp-radius);
  padding: var(--pp-space-4);
  margin-bottom: var(--pp-space-4);
  color: var(--pp-ink-secondary);
}}
.pp-card-title {{
  font-weight: 700;
  color: var(--pp-ink-primary);
  margin-bottom: var(--pp-space-2);
}}
.pp-card p {{ margin: 0 0 var(--pp-space-2); line-height: 1.5; }}

/* ---- risk badge ---- */
.pp-badge-risk {{
  display: flex;
  align-items: center;
  gap: var(--pp-space-2);
  padding: var(--pp-space-3) var(--pp-space-4);
  border-radius: var(--pp-radius);
  border-left: 4px solid var(--pp-status);
  background: color-mix(in srgb, var(--pp-status) 12%, var(--pp-surface));
  font-weight: 700;
  font-size: 1.05rem;
  color: var(--pp-ink-primary);
}}
.pp-badge-risk svg {{ color: var(--pp-status); flex-shrink: 0; }}

/* ---- lists ---- */
.pp-list {{ list-style: none; margin: 0; padding: 0; }}
.pp-list li {{
  display: flex;
  gap: var(--pp-space-2);
  align-items: flex-start;
  padding: var(--pp-space-1) 0;
  color: var(--pp-ink-secondary);
  line-height: 1.5;
}}
.pp-list li svg {{ margin-top: 3px; flex-shrink: 0; color: var(--pp-ink-muted); }}

/* ---- CRS note pill ---- */
.pp-pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--pp-surface);
  border: 1px solid var(--pp-border);
  color: var(--pp-ink-secondary);
  font-size: 0.85rem;
  margin-bottom: var(--pp-space-3);
}}

/* ---- map legend ---- */
.pp-legend {{
  display: flex;
  flex-wrap: wrap;
  gap: var(--pp-space-4);
  margin-top: var(--pp-space-2);
  font-size: 0.9rem;
  color: var(--pp-ink-secondary);
}}
.pp-legend span {{ display: inline-flex; align-items: center; gap: 6px; }}

/* ---- CTA links (replace st.link_button so we can use real SVG icons) ---- */
.pp-cta-row {{ display: flex; gap: var(--pp-space-3); flex-wrap: wrap; }}
.pp-cta {{
  flex: 1 1 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--pp-space-2);
  padding: 10px var(--pp-space-4);
  border-radius: var(--pp-radius-pill);
  font-weight: 600;
  text-decoration: none;
  border: 1px solid var(--pp-border);
  transition: opacity 0.15s ease;
}}
.pp-cta:hover {{ opacity: 0.85; }}
.pp-cta--solid {{ background: var(--pp-accent); color: #ffffff !important; border-color: transparent; }}
.pp-cta--outline {{ background: var(--pp-surface); color: var(--pp-ink-primary) !important; }}
.pp-cta--gold {{ background: var(--pp-gold); color: var(--pp-gold-ink) !important; border-color: transparent; font-weight: 700; }}

/* ---- investment score (pages/investment_analysis.py) ---- */
.pp-score-card {{
  display: flex;
  align-items: center;
  gap: var(--pp-space-4);
  padding: var(--pp-space-4) var(--pp-space-5);
  border-radius: var(--pp-radius);
  border-left: 4px solid var(--pp-status);
  background: color-mix(in srgb, var(--pp-status) 12%, var(--pp-surface));
  margin-bottom: var(--pp-space-4);
}}
.pp-score-number {{
  font-family: var(--pp-font-heading);
  font-size: 2.6rem;
  font-weight: 800;
  color: var(--pp-status);
  line-height: 1;
  white-space: nowrap;
}}
.pp-score-number span {{ font-size: 1.1rem; font-weight: 500; color: var(--pp-ink-muted); }}
.pp-score-verdict {{ font-weight: 700; font-size: 1.1rem; color: var(--pp-ink-primary); }}

.pp-subscore {{ margin-bottom: var(--pp-space-3); }}
.pp-subscore-row {{
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 0.9rem;
  color: var(--pp-ink-secondary);
}}
.pp-subscore-track {{
  height: 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--pp-ink-muted) 18%, var(--pp-surface));
  overflow: hidden;
}}
.pp-subscore-fill {{ height: 100%; border-radius: 999px; background: var(--pp-status); }}

/* ---- AI price-potential estimate - deliberately styled as a warning,
   never a plain metric, since it has no real transaction data behind it
   anywhere in the app (see utils/investment_analysis.py) ---- */
.pp-price-card {{
  border: 1.5px solid var(--pp-warning);
  background: color-mix(in srgb, var(--pp-warning) 10%, var(--pp-surface));
  border-radius: var(--pp-radius);
  padding: var(--pp-space-4);
  margin-bottom: var(--pp-space-4);
}}
.pp-price-value {{ font-size: 1.4rem; font-weight: 800; color: var(--pp-ink-primary); margin: var(--pp-space-2) 0; }}
.pp-price-caveat {{ font-style: italic; font-weight: 600; color: #8a5a00; margin-top: var(--pp-space-2); }}

/* ---- land listings (pages/listings.py) - extends .pp-card, same
   light theme and status colors as the rest of the app, not a separate
   visual language ---- */
.pp-listing-card {{
  position: relative;
  background: var(--pp-surface);
  border: 1px solid var(--pp-border);
  border-radius: var(--pp-radius);
  padding: var(--pp-space-4);
  margin-bottom: var(--pp-space-4);
}}
.pp-listing-heading {{
  font-family: var(--pp-font-heading);
  font-weight: 700;
  font-size: 1.05rem;
  color: var(--pp-ink-primary);
  margin: 0 0 var(--pp-space-2);
  padding-right: 90px;
}}
.pp-listing-meta {{ color: var(--pp-ink-secondary); font-size: 0.92rem; margin: 2px 0; }}
.pp-listing-meta strong {{ color: var(--pp-ink-primary); }}
/* Holds one or more status ribbons (verified/sold/closed) top-right, side
   by side - a flex container rather than each ribbon positioning itself,
   so multiple badges (e.g. a sold listing that was also verified) stack
   cleanly instead of overlapping. */
.pp-listing-ribbons {{
  position: absolute;
  top: var(--pp-space-4);
  right: var(--pp-space-4);
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
  max-width: 60%;
}}
.pp-verified-ribbon, .pp-sold-ribbon {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  white-space: nowrap;
}}
.pp-verified-ribbon {{
  background: color-mix(in srgb, var(--pp-good) 14%, var(--pp-surface));
  border: 1px solid var(--pp-good);
  color: var(--pp-good);
}}
/* Neutral, not a warning color - a sold listing/closed request isn't a
   problem, just no longer actionable (see utils/listings.py's
   list_published_ranked() docstring for why it stays visible at all). */
.pp-sold-ribbon {{
  background: var(--pp-ink-primary);
  border: 1px solid var(--pp-ink-primary);
  color: #ffffff;
}}
.pp-listing-card--sold {{ opacity: 0.72; }}

/* ---- footer ---- */
.pp-footer {{
  text-align: center;
  color: var(--pp-ink-muted);
  font-size: 0.85rem;
  margin-top: var(--pp-space-6);
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}}
.pp-footer .pp-heart {{ color: var(--pp-critical); }}

/* ---- Streamlit widget reskin ---- */
[data-testid="stFileUploaderDropzone"] {{
  background: var(--pp-surface);
  border: 1.5px dashed var(--pp-border);
  border-radius: var(--pp-radius);
}}
[data-testid="stTextArea"] textarea {{
  border-radius: var(--pp-radius);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.9rem;
}}
[data-testid="stCheckbox"] input {{ accent-color: var(--pp-accent); }}
[data-testid="stButton"] button[kind="primary"] {{
  background: var(--pp-accent);
  border-color: var(--pp-accent);
  border-radius: var(--pp-radius-pill);
  font-weight: 600;
}}
[data-testid="stDownloadButton"] button {{
  border-radius: var(--pp-radius-pill);
  font-weight: 600;
}}
[data-testid="stAlert"] {{ border-radius: var(--pp-radius); }}

/* ---- accessibility: touch targets + visible keyboard focus ----
   44px is the WCAG 2.5.5 / Apple HIG minimum comfortable tap target -
   Streamlit's default button/checkbox sizing runs smaller. Custom
   border-radius styling elsewhere can visually suppress the browser's
   default focus ring, so it's redrawn explicitly rather than relying on
   the default surviving every override. */
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button {{
  min-height: 44px;
}}
[data-testid="stCheckbox"] label {{ min-height: 28px; align-items: center; }}
[data-testid="stButton"] button:focus-visible,
[data-testid="stDownloadButton"] button:focus-visible,
[data-testid="stCheckbox"] input:focus-visible,
[data-testid="stTextArea"] textarea:focus-visible,
[data-testid="stTextInput"] input:focus-visible,
[data-testid="stSelectbox"] div[tabindex]:focus-visible,
a:focus-visible {{
  outline: 2px solid var(--pp-accent);
  outline-offset: 2px;
}}

/* ---- mobile: no horizontal scroll, comfortable spacing ---- */
@media (max-width: 480px) {{
  [data-testid="stMainBlockContainer"] {{ padding-left: var(--pp-space-3); padding-right: var(--pp-space-3); }}
  .pp-landing-title {{ font-size: 1.6rem; }}
  .pp-wizard-step {{ flex-basis: 70px; }}
  .pp-wizard-step-label {{ font-size: 0.68rem; }}
  .pp-cta-row {{ flex-direction: column; }}
  .pp-cta {{ flex: none; width: 100%; }}
  /* .pp-pill holds multi-sentence notes as well as short badges - a full
     pill radius on a box this tall (more text wrapping at mobile width)
     renders as a distorted oval rather than rounded corners. */
  .pp-pill {{ display: flex; border-radius: var(--pp-radius); }}
}}
</style>
"""
