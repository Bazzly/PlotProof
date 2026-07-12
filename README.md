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
git add app.py app_home.py pages utils legal requirements.txt packages.txt .env.example .gitignore .streamlit/config.toml data/sample_data
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
   ANTHROPIC_API_KEY = ""
   ADMIN_PASSWORD = ""
   ADMIN_URL_PATH = ""
   ```
   Streamlit Cloud exposes these as environment variables at runtime - no code changes needed. Leave `SUPABASE_URL`/`SUPABASE_KEY` blank to keep using local disk storage. **Set `PRIVACY_CONTACT_EMAIL` before directing real users here** - without it, the Privacy Policy honestly (but unprofessionally) says no contact address is configured yet. Leave `ANTHROPIC_API_KEY` blank to keep image extraction on the free OCR path instead of vision (see below); leave `ADMIN_PASSWORD` blank to keep the admin portal disabled. **Set `ADMIN_URL_PATH` to something random** (not the default) before directing real users here too - see [Admin portal](#admin-portal) below. Write down the URL/password combo in your own local `ADMIN_ACCESS.md` (gitignored - see the template instructions there), not anywhere that ends up in git history or chat logs.
5. Click **Deploy**. First build takes a few minutes (installs GeoPandas/Shapely/tesseract).

You'll get a live URL like `https://plotproof.streamlit.app`.

### 4. Storage note

Streamlit Cloud's filesystem is ephemeral - uploaded survey files saved to `data/uploads/` won't persist across app restarts/redeploys. That's fine for now since the app only needs the file for the current session's analysis. To retain uploads long-term, create a Supabase project and set `SUPABASE_URL`/`SUPABASE_KEY` above - `utils/file_handler.py` switches to Supabase Storage automatically once those are set.

This matters more for the **shared land registry** (below): without Supabase, contributed plots live in a local file that resets on every redeploy, so the registry never actually grows in production. Set up Supabase before relying on this feature for real.

### 5. Custom domain (optional)

Streamlit Cloud apps can be pointed at a custom domain via a CNAME record once you have one picked.

## Coordinate extraction & training data

Survey plans come from many different surveyors' software with no shared format - `utils/coordinates.py` and `utils/crs_utils.py` handle plain WGS84 degrees, labeled Northing/Easting (`N: ... E: ...`), the `123.45mN`/`123.45mE` suffix style, and CRS auto-detection/declaration (Minna belts, Minna UTM zones, and WGS84 UTM) for Nigerian projected coordinates. New formats will keep showing up.

A plan that states "U.T.M (ZONE 31)" without naming a datum is genuinely ambiguous - it could mean WGS84 UTM or the older Minna-datum UTM, and guessing wrong is a real error (confirmed against a real plan: ~150m off, easily enough to flip an overlap result). `detect_declared_crs()` only claims certainty when the text names a datum explicitly (`"WGS84"` or `"MINNA"`); otherwise it picks a default but labels the result "assumed" rather than "declared," and the app's **"Coordinate system"** selector (step 2) lets a user who knows their plan's real CRS override the guess directly - re-extracting from the source file with that CRS forced, no re-upload needed.

### Image OCR quality (phone photos)

Most users photograph their survey plan with a phone rather than upload a clean PDF, and plain OCR on a raw photo is meaningfully worse than on a computer-rendered PDF page - confirmed directly: an unprocessed phone-photo-quality image read `750615.672` back as `750615672`, silently losing the decimal point (and with it, the whole coordinate, since the number regex requires one). `file_handler._preprocess_for_ocr()` fixes this before OCR runs: bakes in EXIF rotation, auto-corrects sideways/upside-down photos via Tesseract's own orientation detection (`_correct_orientation()`, gracefully skipped if OSD can't find enough text to judge - common on sparse drawings), upscales undersized images, and applies grayscale/sharpen/contrast. `--psm 6` (uniform text block) consistently kept multi-digit coordinates on one line better than the default or sparse-text modes, which tended to split long numbers across lines.

This materially improves but doesn't guarantee OCR accuracy on a genuinely degraded photo - that's why `utils/coordinates.py`'s number regex requires digit runs to be bounded by non-digit characters on both sides (`(?<!\d)...(?!\d)`), so a garbled run like `750630892` (missing its decimal point) is dropped entirely rather than greedily prefix-matched into a wrong-but-plausible-looking number (confirmed directly: this exact failure mode produced a coordinate 60+ degrees of latitude off before the fix). Losing an unparseable point is recoverable - the user sees "found N of however-many-expected points" and can add it manually; silently returning a wrong one isn't.

When a user checks **"Help improve coordinate extraction"** before analyzing an uploaded file, `utils/training_data.py` saves the document's extracted text, what was auto-detected, and what the user actually confirmed/corrected - opt-in only, never collected silently. This is meant as labeled data (input → ground truth) for eventually training or fine-tuning a real extraction model instead of hand-patching regexes for every new format. Records land in `data/training_examples/*.json` locally, or in a `training_examples` table in Supabase once `SUPABASE_URL`/`SUPABASE_KEY` are set (see the schema documented at the top of `utils/training_data.py` - create that table yourself before switching over). Both locations can contain personal property/owner details from uploaded plans, so they're gitignored and shouldn't be shared outside your own review.

### Vision-based extraction for photos

Even with the OCR preprocessing above, Tesseract's `--psm 6` mode assumes one uniform horizontal text block - a real assumption survey plan photos routinely violate: a horizontal header, origin coordinates printed vertically along a margin, and bearing labels angled diagonally along each boundary line. Confirmed against two real user-submitted photos (one printed, one hand-drawn) that both OCR'd to **zero** detected coordinates despite being clearly legible by eye.

`utils/vision_extract.py` sends the image directly to Claude (`claude-opus-4-8`, vision + structured JSON output) instead, asking it to read the owner name, declared CRS text, origin coordinate, and every beacon's bearing/distance to the next - the same fields `utils/traverse.py` needs to reconstruct the boundary, so the result flows through the existing CRS-resolution and traverse/closure-validation logic unchanged. Both test photos extracted correctly (all 9 beacons on the printed plan; origin + partial traverse on the hand-drawn one, with low-confidence bearings honestly flagged rather than guessed).

This only runs for image uploads (PDFs already extract well without it) and only when `ANTHROPIC_API_KEY` is set - without it, images fall back to the OCR path above unchanged. It's a real per-call cost (roughly $0.05-0.08/image on Opus 4.8 at 2026 pricing) and adds noticeable latency (~10-25s), so it's a deliberate step up from free local OCR, not a silent swap. A vision-call failure (rate limit, API error) also falls back to OCR rather than dropping straight to manual entry. `scripts/vision_extract_prototype.py` is a standalone CLI for testing this module directly against a photo without going through the app.

## Admin portal

`app.py` is a thin `st.navigation()` entrypoint - the actual app content lives in `app_home.py`, and `st.navigation([...], position="hidden")` means **no sidebar nav is rendered at all**, for either page. This is deliberate: Streamlit's default behavior would auto-list anything under `pages/` (including the admin portal) in a visible sidebar for every visitor. `pages/admin_review.py` is only reachable by going directly to `<APP_URL>/<ADMIN_URL_PATH>` - a URL slug set via the `ADMIN_URL_PATH` env var (default `admin-review`, which is guessable from this public repo, so **set a random one before directing real users here** - see `.env.example`). Once there, it has two tabs:

- **API Key** - view (masked) and rotate the Anthropic API key at runtime, via `utils/app_config.py`. This repo is public, so the key can never be committed; a key set here overrides the `ANTHROPIC_API_KEY` env var immediately for every future request, no redeploy or Streamlit Cloud secrets-panel access needed. Storage mirrors the rest of the app (local JSON by default, a Supabase `app_config` table if configured - schema at the top of that file) - either way it holds a live secret, so the local file is gitignored and a Supabase-backed deployment should restrict the table with RLS. Use "Clear admin override" to fall back to the env var again (e.g. after rotating it there instead).
- **Extraction Review** - browses every opt-in record `utils/training_data.py` has collected: source image thumbnail, the raw extracted text or vision summary, auto-detected CRS note, and auto-detected vs. user-confirmed points side by side. Exists to give visibility into real-world extraction failures (a document that returned zero points despite being legible, or one a user had to significantly correct) rather than only finding out about them anecdotally. Filter by extraction method, "failures only" (zero auto-detected points), or "corrected only" to jump straight to the cases worth looking at.

Content access is separately gated behind `ADMIN_PASSWORD` (env var) - the whole page refuses to render at all, even the password prompt, if that's unset, so it can't be accidentally left open with no gate. The URL slug and the password are two independent layers: knowing one without the other gets you nowhere. See `ADMIN_ACCESS.md` (gitignored, not in this repo - a local template is created for you) for a place to record this deployment's actual URL/password without it ever touching git history or chat logs.

## Rate limiting & abuse protection

Because this repo (and its `ANTHROPIC_API_KEY`) is public, and vision extraction has a real per-call cost, `utils/rate_limit.py` enforces two independent layers on every "Analyze My Land"/"Compare Plots" click and every vision-extraction attempt:

- **Daily per-visitor caps** - `DAILY_CHECK_LIMIT` (default 3) on the core "run a check" action, `DAILY_VISION_LIMIT` (default 5, slightly more generous since a normal single real check can involve a re-upload or a CRS-override re-extraction) on the vision API call specifically. Persisted the same way as the rest of the app's data (local JSON by default, a Supabase `rate_limit_usage` table if configured), so it survives restarts within the same day and can't be bypassed by just reloading the page. Hitting the check cap shows an error and blocks the action; hitting the vision cap silently falls back to free OCR instead of blocking outright.
- **Burst limiter** - `BURST_MAX_REQUESTS` per `BURST_WINDOW_SECONDS` (default 10 per 60s), in-memory only, to blunt rapid automated hammering within a day's allowance. Resets on process restart and doesn't share state across multiple app instances - a reasonable single-instance DoS mitigation for this app's expected deployment (Streamlit Community Cloud), not a substitute for an edge/WAF rate limiter behind a load balancer.

A visitor is identified (`rate_limit.get_client_id()`) by the `X-Forwarded-For` header first (the real client IP behind Streamlit Cloud's proxy), falling back to `st.context.ip_address`, falling back to a random per-browser-session ID as a last resort (weak - a new session gets a fresh allowance - but this only matters in local dev, where loopback requests have no usable IP). All four limits are configurable via env var - see `.env.example`.

## Polygon reconstruction

Most survey plans only print one absolute coordinate plus a description of the rest of the boundary (bearings/distances, or individually-labeled beacons) rather than a table of corner coordinates. `utils/traverse.py` walks a text-based bearing/distance traverse from that origin; `utils/plan_vectors.py` reconstructs the boundary directly from the PDF's vector drawing when the plan labels each beacon individually (higher confidence, tried first). Both are cross-checked against the plan's own printed `AREA:-` figure before being trusted - a reconstruction that doesn't match within 15% is discarded in favor of the simpler single-point estimate, rather than showing a confidently wrong shape.

## PDF report design

`utils/report_generator.py` builds the downloadable report with ReportLab's canvas API, styled to match the web app rather than as plain black-and-white text: a colored header band, a risk badge with the same status icon shapes used on the page, a Low/Medium/High gauge with a pointer, a schematic diagram of the plot boundary (the actual polygon, scaled to fit - or a dashed circle for the buffered-estimate case when fewer than 3 points were given), a conflicting/nearby-plots table, a proper coordinates table, and a footer with real clickable links (WhatsApp/Calendly, via `canvas.linkURL()`). Colors are imported from `utils/theme.py` (`theme.STATUS`, `theme.ACCENT_LIGHT`, `theme.INK`) rather than redefined, so the report never drifts from the app's palette.

## Shared land registry

`utils/registry.py` lets a user opt in (a separate, explicit checkbox shown after analysis - never bundled with the extraction consent above, never on by default) to add their analyzed plot's **boundary geometry only** to a shared registry that future uploads get checked against too. No owner name, address, or source document is stored - just the polygon and a generated reference (`PP-XXXXXXXX`). `gis_processing.load_neighboring_plots()` merges this registry with the synthetic sample data on every call (not cached, so a newly-contributed plot is visible to the very next analysis), and the map (`gis_processing.nearby_plots_for_context()`) only shows registry plots within ~800m of the plot being checked, so it stays readable as the registry grows.

Because a "no risk" result only reflects what's on record at that moment, the results view says so explicitly and includes a share CTA - the registry's value compounds with more contributors, so the messaging leans into inviting neighbors rather than treating a clean result as a final answer.

Records land in `data/registry/registry_plots.json` locally, or a `registry_plots` table in Supabase once configured (schema in `utils/registry.py`) - gitignored either way, since it's user-contributed data that shouldn't live in source control.

## Two-plot comparison mode

Alongside the standard "check against known plots" flow, a mode selector (top of `app_home.py`) offers **"Compare two specific plots"** - checks a user's plot directly against one specific neighboring plot they provide, instead of against the registry/sample data. This means processing a second person's survey document, not just the uploader's own, so it's gated behind its own explicit consent checkbox ("I confirm my neighbor has agreed...") - the neighboring-plot inputs stay `disabled=True` until that's checked, and the Compare button stays disabled too. PlotProof doesn't and can't verify this consent independently; the uploader is attesting to having it.

Both flows share the same upload/CRS-override machinery (`render_document_input()`, namespaced by a `slot` argument so Plot A/B's session state and widget keys never collide) and the same results rendering (`render_results()`), just pointed at a single ad-hoc neighbor GeoDataFrame instead of `load_neighboring_plots()`. Comparison results skip the shared-registry opt-in and viral-sharing CTA - those are framed around a plot's relationship to the wider registry, which doesn't apply to a one-off direct comparison.

Unlike the standard mode, the neighbor here is a real document the user provided (not an anonymous registry entry), so its full details belong in the PDF too: `generate_pdf_report()`'s optional `neighbor_plots` argument (only populated in compare mode) draws the neighbor's boundary on the *same shared scale* as the user's plot - critical for the diagram to actually show an overlap when one exists, rather than each polygon being independently normalized to fill the box and losing their real relative position - plus its own "Neighboring Plot - Coordinates Provided" table alongside the user's own.

## Terms of Service & Privacy Policy

The app is gated behind a consent screen (`app_home.py`, right after the hero) - nothing else renders until a user checks "I have read and agree" and clicks through. `legal/terms.md` and `legal/privacy.md` hold the actual text (loaded via `utils/legal.py`), written around Nigeria's NDPA 2023 (the law that actually governs this app's users) plus GDPR-equivalent language for any EU users. Both are also re-readable anytime via an expander in the footer.

**This is a drafted starting point based on what the app actually does, not a substitute for a lawyer's review** - especially given real users' personal property data is involved. Before directing real users here:

- Set `PRIVACY_CONTACT_EMAIL` (see above) - the policy currently discloses that it isn't configured.
- Have someone with NDPA/GDPR expertise review `legal/terms.md` and `legal/privacy.md` for your specific situation (e.g. if you add Supabase, its hosting region and data processing terms should be reflected in Section 9 of the privacy policy).
- Consent is session-only right now (resets each new browser session) - no cookie/localStorage persistence, so returning users see the gate again. That was a deliberate simplicity trade-off; revisit it if the re-prompt becomes a real friction point.

Streamlit's own built-in usage telemetry is disabled via `.streamlit/config.toml` (`gatherUsageStats = false`), so the only cookie in play is Streamlit's own essential session cookie - no separate cookie-consent banner is needed because there's nothing non-essential to consent to.

## Project structure

```
landSuite/
├── app.py                      # thin st.navigation() entrypoint (hides the admin page from any nav)
├── app_home.py                 # the actual app - upload, coordinates, risk check, results
├── ADMIN_ACCESS.md             # local-only admin URL/password notes (gitignored, not in repo)
├── pages/
│   └── admin_review.py         # password-gated admin portal (API key + extraction review)
├── scripts/
│   └── vision_extract_prototype.py  # standalone CLI for testing vision extraction
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
│   ├── vision_extract.py       # Claude-vision-based extraction for photographed plans
│   ├── app_config.py           # admin-editable runtime config (Anthropic API key)
│   ├── rate_limit.py           # per-visitor daily caps + burst limiter
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
│   ├── training_examples/      # opt-in labeled extraction examples (gitignored)
│   ├── config/                 # admin-set runtime config, e.g. rotated API key (gitignored)
│   └── rate_limits/            # daily per-visitor usage counters (gitignored)
└── doc/                        # product spec, architecture notes, planning docs
```
