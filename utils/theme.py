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
status hues (good/warning/critical) are fixed across light and dark and
carry meaning only together with an icon + text label, never as flat
color-on-text - see icon usage in app.py. These are intentionally NOT
tied to the brand palette above - a risk badge should read the same
regardless of what accent color the rest of the UI is wearing.
"""

# Fixed across light/dark - already validated to clear contrast on both surfaces.
STATUS = {
    "good": "#0ca30c",  # Low risk / no conflicting plot
    "warning": "#fab219",  # Medium risk / nearby plot
    "critical": "#d03b3b",  # High risk / overlapping plot
}

# Brand accent (deep green, oklch(38% 0.09 152) family) - the one thing
# that does need a light/dark swap, handled via prefers-color-scheme in
# the CSS below. Gold is the secondary/CTA accent (oklch(78% 0.13 80)),
# used sparingly for the strongest calls to action, matching the landing
# page's hero button.
ACCENT_LIGHT = "#104f29"
ACCENT_DARK = "#59ad73"
GOLD = "#e3ad4b"
GOLD_INK = "#201308"

RISK_TO_STATUS = {"Low": "good", "Medium": "warning", "High": "critical"}
RISK_TO_ICON = {"Low": "check-circle", "Medium": "alert-triangle", "High": "alert-octagon"}

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
@media (prefers-color-scheme: dark) {{
  :root {{
    --pp-surface: #1f160f;
    --pp-page: #120c07;
    --pp-ink-primary: #f1eee7;
    --pp-ink-secondary: #c4bdb0;
    --pp-ink-muted: #968364;
    --pp-gridline: #3b3129;
    --pp-border: #3b3129;
    --pp-accent: {ACCENT_DARK};
    --pp-step-num-bg: #103a21;
    --pp-step-num-ink: #7fd99b;
  }}
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
</style>
"""
