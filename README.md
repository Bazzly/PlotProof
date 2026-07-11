# PlotProof

Instant land boundary risk check for property owners in Africa. Upload a survey plan (or enter coordinates) and get a Low/Medium/High risk report, checked against known neighboring plots, with a downloadable PDF and a consultation CTA.

Full product spec, landing page copy, and marketing plan: [doc/LandVerify_README-1.md](doc/LandVerify_README-1.md). Architecture notes: [doc/TECHNICAL_ARCHITECTURE.md](doc/TECHNICAL_ARCHITECTURE.md).

## Run it locally

```bash
# 1. System dependency for OCR
brew install tesseract

# 2. Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install app dependencies
pip install -r requirements.txt

# 4. (Optional) configure Supabase / CTA links
cp .env.example .env
# edit .env if you have Supabase credentials or custom WhatsApp/Calendly links

# 5. Run it
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Deploy it live

Recommended: **Streamlit Community Cloud** (free, no server to manage, matches this stack). Render is an alternative but needs a Dockerfile just to install the `tesseract-ocr` system package.

### 1. Push to GitHub

```bash
git init
git add app.py utils legal requirements.txt packages.txt .env.example .gitignore .streamlit/config.toml data/sample_data
git commit -m "PlotProof MVP"
git remote add origin https://github.com/<your-username>/plotproof.git
git branch -M main
git push -u origin main
```

`.streamlit/config.toml` is explicitly `git add`-ed above because `.streamlit/` is otherwise gitignored (it's where local secrets would live) - only `secrets.toml` inside it is actually ignored; the non-secret `config.toml` (disables Streamlit's usage telemetry - see [Terms & Privacy](#terms-of-service--privacy-policy) below) needs to ship with the app.

### 2. OCR system dependency

`packages.txt` (already in the repo) tells Streamlit Cloud to `apt-get install tesseract-ocr` before the app starts, so OCR works live the same as it does locally.

### 3. Deploy on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **New app** → pick the repo, branch `main`, main file path `app.py`.
3. Under **Advanced settings**, set Python version to **3.11**.
4. Under **Secrets**, paste (TOML format):
   ```toml
   SUPABASE_URL = ""
   SUPABASE_KEY = ""
   WHATSAPP_LINK = "https://chat.whatsapp.com/KrMfFgenA5u50QTASfyyro?s=cl&p=a&ilr=1"
   CALENDLY_LINK = "https://calendly.com/bazeet4love"
   APP_URL = "https://plotproof.streamlit.app"
   PRIVACY_CONTACT_EMAIL = ""
   ```
   Streamlit Cloud exposes these as environment variables at runtime - no code changes needed. Leave `SUPABASE_URL`/`SUPABASE_KEY` blank to keep using local disk storage. **Set `PRIVACY_CONTACT_EMAIL` before directing real users here** - without it, the Privacy Policy honestly (but unprofessionally) says no contact address is configured yet.
5. Click **Deploy**. First build takes a few minutes (installs GeoPandas/Shapely/tesseract).

You'll get a live URL like `https://plotproof.streamlit.app`.

### 4. Storage note

Streamlit Cloud's filesystem is ephemeral - uploaded survey files saved to `data/uploads/` won't persist across app restarts/redeploys. That's fine for now since the app only needs the file for the current session's analysis. To retain uploads long-term, create a Supabase project and set `SUPABASE_URL`/`SUPABASE_KEY` above - `utils/file_handler.py` switches to Supabase Storage automatically once those are set.

This matters more for the **shared land registry** (below): without Supabase, contributed plots live in a local file that resets on every redeploy, so the registry never actually grows in production. Set up Supabase before relying on this feature for real.

### 5. Custom domain (optional)

Streamlit Cloud apps can be pointed at a custom domain via a CNAME record once you have one picked.

## Coordinate extraction & training data

Survey plans come from many different surveyors' software with no shared format - `utils/coordinates.py` and `utils/crs_utils.py` handle plain WGS84 degrees, labeled Northing/Easting (`N: ... E: ...`), the `123.45mN`/`123.45mE` suffix style, and CRS auto-detection/declaration (Minna belts + WGS84 UTM) for Nigerian projected coordinates. New formats will keep showing up.

When a user checks **"Help improve coordinate extraction"** before analyzing an uploaded file, `utils/training_data.py` saves the document's extracted text, what was auto-detected, and what the user actually confirmed/corrected - opt-in only, never collected silently. This is meant as labeled data (input → ground truth) for eventually training or fine-tuning a real extraction model instead of hand-patching regexes for every new format. Records land in `data/training_examples/*.json` locally, or in a `training_examples` table in Supabase once `SUPABASE_URL`/`SUPABASE_KEY` are set (see the schema documented at the top of `utils/training_data.py` - create that table yourself before switching over). Both locations can contain personal property/owner details from uploaded plans, so they're gitignored and shouldn't be shared outside your own review.

## Polygon reconstruction

Most survey plans only print one absolute coordinate plus a description of the rest of the boundary (bearings/distances, or individually-labeled beacons) rather than a table of corner coordinates. `utils/traverse.py` walks a text-based bearing/distance traverse from that origin; `utils/plan_vectors.py` reconstructs the boundary directly from the PDF's vector drawing when the plan labels each beacon individually (higher confidence, tried first). Both are cross-checked against the plan's own printed `AREA:-` figure before being trusted - a reconstruction that doesn't match within 15% is discarded in favor of the simpler single-point estimate, rather than showing a confidently wrong shape.

## Shared land registry

`utils/registry.py` lets a user opt in (a separate, explicit checkbox shown after analysis - never bundled with the extraction consent above, never on by default) to add their analyzed plot's **boundary geometry only** to a shared registry that future uploads get checked against too. No owner name, address, or source document is stored - just the polygon and a generated reference (`PP-XXXXXXXX`). `gis_processing.load_neighboring_plots()` merges this registry with the synthetic sample data on every call (not cached, so a newly-contributed plot is visible to the very next analysis), and the map (`gis_processing.nearby_plots_for_context()`) only shows registry plots within ~800m of the plot being checked, so it stays readable as the registry grows.

Because a "no risk" result only reflects what's on record at that moment, the results view says so explicitly and includes a share CTA - the registry's value compounds with more contributors, so the messaging leans into inviting neighbors rather than treating a clean result as a final answer.

Records land in `data/registry/registry_plots.json` locally, or a `registry_plots` table in Supabase once configured (schema in `utils/registry.py`) - gitignored either way, since it's user-contributed data that shouldn't live in source control.

## Terms of Service & Privacy Policy

The app is gated behind a consent screen (`app.py`, right after the hero) - nothing else renders until a user checks "I have read and agree" and clicks through. `legal/terms.md` and `legal/privacy.md` hold the actual text (loaded via `utils/legal.py`), written around Nigeria's NDPA 2023 (the law that actually governs this app's users) plus GDPR-equivalent language for any EU users. Both are also re-readable anytime via an expander in the footer.

**This is a drafted starting point based on what the app actually does, not a substitute for a lawyer's review** - especially given real users' personal property data is involved. Before directing real users here:

- Set `PRIVACY_CONTACT_EMAIL` (see above) - the policy currently discloses that it isn't configured.
- Have someone with NDPA/GDPR expertise review `legal/terms.md` and `legal/privacy.md` for your specific situation (e.g. if you add Supabase, its hosting region and data processing terms should be reflected in Section 9 of the privacy policy).
- Consent is session-only right now (resets each new browser session) - no cookie/localStorage persistence, so returning users see the gate again. That was a deliberate simplicity trade-off; revisit it if the re-prompt becomes a real friction point.

Streamlit's own built-in usage telemetry is disabled via `.streamlit/config.toml` (`gatherUsageStats = false`), so the only cookie in play is Streamlit's own essential session cookie - no separate cookie-consent banner is needed because there's nothing non-essential to consent to.

## Project structure

```
landSuite/
├── app.py                      # Streamlit app
├── requirements.txt
├── packages.txt                # apt packages for cloud deploy (tesseract-ocr)
├── .env.example
├── .streamlit/
│   └── config.toml             # disables Streamlit's usage telemetry (not a secret - committed)
├── legal/
│   ├── terms.md                # Terms of Service
│   └── privacy.md              # Privacy Policy (NDPA + GDPR)
├── utils/
│   ├── coordinates.py          # shared coordinate text parsing/validation
│   ├── crs_utils.py            # Nigerian CRS auto-detection/declaration + conversion to WGS84
│   ├── traverse.py             # text-based bearing/distance boundary reconstruction
│   ├── plan_vectors.py         # vector-drawing-based boundary reconstruction (higher confidence)
│   ├── file_handler.py         # upload storage + PDF/image text & OCR extraction
│   ├── gis_processing.py       # GeoPandas overlap/proximity analysis
│   ├── risk_calculator.py      # risk scoring from GIS results
│   ├── report_generator.py     # PDF report generation
│   ├── registry.py             # opt-in shared land registry (geometry only)
│   ├── training_data.py        # opt-in extraction examples for future model training
│   └── legal.py                # loads/renders the Terms & Privacy Policy
├── data/
│   ├── sample_data/            # synthetic neighboring-plot data for demo/testing
│   ├── uploads/                # local upload storage (until Supabase is configured)
│   ├── registry/               # opt-in shared registry plots (gitignored)
│   └── training_examples/      # opt-in labeled extraction examples (gitignored)
└── doc/                        # product spec, architecture notes, planning docs
```
