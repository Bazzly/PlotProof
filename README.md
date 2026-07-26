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

`app.py` is a thin `st.navigation()` entrypoint - the actual app content lives in `app_home.py`, and `st.navigation([...], position="hidden")` means **no sidebar nav is rendered at all**, for either page. This is deliberate: Streamlit's default behavior would auto-list anything under `pages/` (including the admin portal) in a visible sidebar for every visitor. `pages/admin_review.py` is only reachable by going directly to `<APP_URL>/<ADMIN_URL_PATH>` - a URL slug set via the `ADMIN_URL_PATH` env var (default `admin-review`, which is guessable from this public repo, so **set a random one before directing real users here** - see `.env.example`). Once there, it has three tabs:

- **API Key** - view (masked) and rotate the Anthropic API key at runtime, via `utils/app_config.py`. This repo is public, so the key can never be committed; a key set here overrides the `ANTHROPIC_API_KEY` env var immediately for every future request, no redeploy or Streamlit Cloud secrets-panel access needed. Storage mirrors the rest of the app (local JSON by default, a Supabase `app_config` table if configured - schema at the top of that file) - either way it holds a live secret, so the local file is gitignored and a Supabase-backed deployment should restrict the table with RLS. Use "Clear admin override" to fall back to the env var again (e.g. after rotating it there instead).
- **Extraction Review** - browses every opt-in record `utils/training_data.py` has collected: source image thumbnail, the raw extracted text or vision summary, auto-detected CRS note, and auto-detected vs. user-confirmed points side by side. Exists to give visibility into real-world extraction failures (a document that returned zero points despite being legible, or one a user had to significantly correct) rather than only finding out about them anecdotally. Filter by extraction method, "failures only" (zero auto-detected points), or "corrected only" to jump straight to the cases worth looking at.
- **Bulk Add Plans** - upload several survey plans at once (up to `MAX_BULK_FILES`, default 30) to seed the shared registry faster than waiting for individual users to opt in one plot at a time via the main flow. Runs each file through the exact same extraction pipeline as the main app (OCR/text by default; vision extraction is an explicit opt-in checkbox, off by default, since a large batch of photos adds up in real API cost fast) - only reuses existing functions, no separate extraction logic to keep in sync. A boundary is only auto-added if it extracts as a clean, closed shape *and* the extraction pipeline itself raised no uncertainty flag - not enough points, an unconfirmed CRS datum (`crs_utils.crs_is_uncertain()`), a beacon-order/direction mismatch (`traverse.traverse_order_uncertain()`), or a traverse that didn't fully close (`traverse.boundary_is_approximate()`) are all skipped rather than added unattended, with the reason shown in a per-file results table. This matters more here than in the main flow's single-plot opt-in: a bad shape added here would be silently checked against by *every other user's* overlap analysis, not just corrupt one person's own result - so nothing gets in without either real confidence or a human reviewing it through the main flow instead. Added plots go through the same `registry.add_plot()` as the main app's opt-in checkbox and carry the same privacy shape - boundary geometry only, no owner name or source document, regardless of what the uploaded file contained.

  `crs_is_uncertain()` and `traverse_order_uncertain()` used to be private helpers inside `app_home.py`; moved to `utils/crs_utils.py`/`utils/traverse.py` respectively (alongside `boundary_is_approximate()`, new) so this admin tool and the main app check "is this trustworthy enough" the same way from one definition, rather than duplicating the marker-substring logic and risking the two drifting apart.

Content access is separately gated behind `ADMIN_PASSWORD` (env var) - the whole page refuses to render at all, even the password prompt, if that's unset, so it can't be accidentally left open with no gate. The URL slug and the password are two independent layers: knowing one without the other gets you nowhere. See `ADMIN_ACCESS.md` (gitignored, not in this repo - a local template is created for you) for a place to record this deployment's actual URL/password without it ever touching git history or chat logs.

## Rate limiting & abuse protection

Because this repo (and its `ANTHROPIC_API_KEY`) is public, and vision extraction has a real per-call cost, `utils/rate_limit.py` enforces two independent layers on every "Analyze My Land"/"Compare Plots" click and every vision-extraction attempt:

- **Daily per-visitor caps** - `DAILY_CHECK_LIMIT` (default 3) on the core "run a check" action, `DAILY_VISION_LIMIT` (default 5, slightly more generous since a normal single real check can involve a re-upload or a CRS-override re-extraction) on the vision API call specifically. Persisted the same way as the rest of the app's data (local JSON by default, a Supabase `rate_limit_usage` table if configured), so it survives restarts within the same day and can't be bypassed by just reloading the page. Hitting the check cap shows an error and blocks the action; hitting the vision cap silently falls back to free OCR instead of blocking outright.
- **Burst limiter** - `BURST_MAX_REQUESTS` per `BURST_WINDOW_SECONDS` (default 10 per 60s), in-memory only, to blunt rapid automated hammering within a day's allowance. Resets on process restart and doesn't share state across multiple app instances - a reasonable single-instance DoS mitigation for this app's expected deployment (Streamlit Community Cloud), not a substitute for an edge/WAF rate limiter behind a load balancer.

A visitor is identified (`rate_limit.get_client_id()`) by the `X-Forwarded-For` header first (the real client IP behind Streamlit Cloud's proxy), falling back to `st.context.ip_address`, falling back to a random per-browser-session ID as a last resort (weak - a new session gets a fresh allowance - but this only matters in local dev, where loopback requests have no usable IP). All four limits are configurable via env var - see `.env.example`.

## Polygon reconstruction

Most survey plans only print one absolute coordinate plus a description of the rest of the boundary (bearings/distances, or individually-labeled beacons) rather than a table of corner coordinates. `utils/traverse.py` walks a text-based bearing/distance traverse from that origin; `utils/plan_vectors.py` reconstructs the boundary directly from the PDF's vector drawing when the plan labels each beacon individually (higher confidence, tried first). Both are cross-checked against the plan's own printed `AREA:-` figure before being trusted - a reconstruction that doesn't match within 15% is discarded in favor of the simpler single-point estimate, rather than showing a confidently wrong shape.

### Bearing/distance review & editing

Text OCR and vision extraction can both misread a bearing or distance the same way they can misread a coordinate, so whenever a traverse-based reconstruction was attempted (text-based via `traverse.py`, or vision-based via `vision_extract.py` - not the vector-drawing method, which reads beacon positions directly and has no bearing/distance to show), `render_document_input()` in `app_home.py` shows every leg in an editable table right above the coordinates box - line, bearing, distance - with a caution to check each line against the original document and to have a licensed surveyor confirm if the user isn't confident reading one themselves. This applies to both the standard check and each side of the two-plot comparison (the table is part of the shared upload component, not duplicated per mode). Beacons with no printed code (common on older plans, which often predate the beacon-numbering convention newer ones use) get auto-labeled `PL1`, `PL2`, ....

A bearing and distance describe a *line* between two points, not a single point, so each row is labeled as the line it represents - `PL1 → PL2`, `PL2 → PL3`, ..., wrapping back to `PLn → PL1` on the closing leg (same convention for real beacon codes: `GB8564AHX → GB8565AHX`). The origin - always vertex 0, and what every other point is calculated *from* - is surfaced as its own line above the table (`legs_info["origin_label"]`/`["origin_latlon"]` in `vision_extract.py`/`coordinates.py`) rather than left as just the first, unlabeled line of the coordinates box below it.

**Old and hand-surveyed plans routinely don't close within a strict tolerance even when every value was read correctly** - decades-old chain-and-compass measurements drift, figures get hand-copied across re-surveys, a beacon shifts slightly over the years. Rather than collapsing to a single point whenever that happens, `traverse.build_open_polygon()` deduces the boundary anyway by walking the same bearings/distances without enforcing closure, and the result is shown with an explicit "doesn't fully close (~Xm gap), review the bearings/distances below" note. A real, approximate, openly-flagged shape is more useful to check against the original document than nothing at all - `traverse.compute_traverse()` (the strict, closure-validated version) is still tried first and used whenever it succeeds; the open fallback only kicks in when it doesn't.

**A wrong starting beacon or traverse direction doesn't corrupt any individual bearing/distance value, so nothing above would catch it** - the shape would just come out rotated to the wrong starting corner or mirrored, silently. Nigerian cadastral plans conventionally start the traverse at the northernmost beacon and proceed clockwise; `traverse.check_traverse_convention()` checks the reconstructed polygon (open or closed) against that convention and, if it doesn't match, adds an explicit warning (`app_home.py`'s `traverse_order_uncertain()`/`show_traverse_order_disclaimer()`, mirroring the existing CRS-uncertainty disclaimer pattern) rather than silently trusting whatever order the model or OCR returned. This is a review flag, not proof of an error - some real plans legitimately start elsewhere, and reading noise can make two beacons nearly tie for "northernmost" - so it doesn't block or alter the result, just calls out that the beacon order is worth double-checking. The vision extraction prompt also explicitly tells the model to transcribe beacons in the exact order printed on the plan rather than reordering them to match the expected convention itself.

**When every individual value was read correctly but the rows are in the wrong sequence**, editing cells one at a time in the table above can't fix that - so right below it, `render_document_input()` renders a second, drag-and-drop view of the same legs (via [`streamlit-sortables`](https://pypi.org/project/streamlit-sortables/), one draggable item per leg, numbered and labeled the same way as the table rows). Dropping a row into a new position reorders the underlying legs and triggers the same recompute as a value edit (`traverse.resolve_recomputed_points()`); `PL1 → PL2`-style auto-generated labels are relabeled to match the new position (since they describe "how many legs from the origin," not a specific real beacon), while real beacon codes read off the plan (`GB8564AHX → GB8565AHX`) travel with their row untouched, since those describe an actual physical line regardless of where it falls in the walk order.

Editing a cell re-walks the traverse from the same origin and re-populates the coordinates box immediately - no separate "apply" step, same pattern as the CRS-override re-extraction above it. `traverse.resolve_recomputed_points()` tries a strict, closed reconstruction first and falls back to the same open/approximate deduction (flagged with a warning) rather than rejecting the edit outright - only genuinely too-few-legs (fewer than 3) or unparseable bearing/distance text blocks an update. The re-projection back to WGS84 after an edit uses a flat-earth (local ENU) approximation anchored on the already-known origin coordinate rather than re-running the full CRS pipeline - accurate to well under a centimeter at plot-boundary scale, and avoids threading the original EPSG code through every layer just for a one-line edit.

### Diagonal check

A straight-line bearing and distance from the origin (PL1) to the vertex directly opposite it in the boundary's own sequence - `traverse.compute_diagonal()`. Computed **purely from the coordinates PlotProof itself already generated**, always, for every boundary with 4+ vertices - not read off the plan. An earlier version of this tried to detect a printed "DIAGONAL" label and cross-check against it, on the (wrong) assumption that Nigerian survey plans commonly print one as an independent verification measurement; checking against the two real sample plans in this project showed neither has one, and in general they don't - so that detection would have simply never fired on a real document, which is exactly why it wasn't showing up. Replaced with always-computed geometry instead of label-detection, since there's nothing reliable to detect.

The target is `len(vertices) // 2` steps around from the origin - a diagonal connects *non-adjacent* vertices, so a 4-pillar plot's diagonal from PL1 is PL3, a 6-pillar plot's is PL4, and so on. The first version of this picked whichever vertex was simply farthest away by straight-line distance, which for an irregular quadrilateral can land on an *adjacent* vertex (PL2) - still connected to the origin by a real boundary edge, not a diagonal at all, confirmed as a real bug against an actual reconstructed plot before switching to the "opposite in sequence" definition. Triangles (3 vertices) have no non-adjacent vertex pair, so `compute_diagonal()` returns `None` for one - there's no real diagonal to show.

`traverse.project_point()` (factored out of `walk_traverse()`'s per-leg loop - the same one-step COGO forward calculation, `origin + distance` along a bearing) and basic trigonometry (`atan2`/`hypot`) on the already-reconstructed vertices are all `compute_diagonal()` needs - no text parsing, no schema field, no LLM involvement. Both extraction paths (`coordinates.py`'s text/OCR path, `vision_extract.py`'s vision path) call it the same way once they have a real polygon, passing beacon codes or `PL{n}` labels so the result names which corner it's measuring to (e.g. "PL1 → PL3").

Shown as its own always-visible "Diagonal Check" card directly below the bearing/distance editor in `app_home.py` - not buried inside the `crs_note` warning-note paragraph the way the first version of this was, which is what actually made it hard to find in the first place. Recomputed live when the user edits or drag-reorders the bearing/distance table (`traverse.resolve_recomputed_points()` now also returns the diagonal, using each row's own beacon/PL identifier as the label), so it never goes stale and keeps describing a boundary shape that's no longer on screen.

The card shows the diagonal target's coordinate in **both** systems - the plan's own local projected system (`point_label`, e.g. `"500103.586mE / 700017.325mN"`, same `"<easting>mE / <northing>mN"` convention as `legs_info`'s own `origin_label`) and WGS84 (`point_latlon`), not just one or the other. The local-system value comes for free from `compute_diagonal()` (it's just formatting the `point_en` it already computed while finding the opposite vertex); the WGS84 value is produced by appending that same point to the *same* `crs_utils.resolve_to_wgs84()` call already converting the main polygon (not a separate conversion), so it goes through the identical declared/forced/auto-detected CRS, then splits back off by position - the edit-path (`resolve_recomputed_points()`) reuses the same flat-earth offset-from-origin approximation it already applies to every other vertex. `legs_info["diagonal"]["point_latlon"]` stays unset only if the converted point itself falls outside valid lat/lon range - vanishingly unlikely for a real point derived from an already-valid boundary, but checked rather than assumed.

## Design system

PlotProof's visual identity (Newsreader serif headings, Work Sans body, warm cream/deep-green/gold editorial palette) originated in a standalone static marketing page, since removed once its design was fully absorbed into the app itself - `utils/theme.py` is now the source of truth. Every surface matches it in two layers, both driven from the same hex values:

- **`utils/theme.py`** - `STATUS`/`ACCENT_LIGHT`/`GOLD`/`INK` constants (hex conversions of the landing page's `oklch()` colors - ReportLab has no oklch support, and one color space keeps the CSS and the PDF from silently drifting apart) plus `get_css()`, a hand-written stylesheet injected via `st.markdown()` that skins PlotProof's own custom markup (`.pp-hero`, `.pp-step`, `.pp-card`, `.pp-badge-risk`, `.pp-cta`, etc.) and a few Streamlit `data-testid` hooks.
- **`.streamlit/config.toml`'s `[theme]` section** - native Streamlit theming (same hex values again) for everything `get_css()` structurally can't reach: radio buttons, checkboxes, tabs, sliders, native `st.error`/`st.warning`/`st.success`/`st.info` alert boxes, dataframe/`st.data_editor` headers, and every button (including ones without a custom CSS selector, like `pages/admin_review.py`'s form buttons). Without this, those widgets silently fall back to Streamlit's own default theme (a very visible mismatch - default red radio dots, blue `st.info` boxes, square buttons - against the rest of the page). `buttonRadius = "full"` and `baseRadius = "1rem"` give every native widget the landing page's pill/rounded-corner language for free; `font`/`headingFont` load Work Sans/Newsreader directly from Google Fonts via Streamlit's `"<name>:<url>"` config syntax, no custom font-face hosting needed.

Risk-status colors (`STATUS`/`greenColor`/`orangeColor`/`redColor`) are deliberately independent of the brand accent - they were validated for accessibility (colorblind-safe, contrast-checked) separately, and a risk badge should read the same regardless of what the brand's accent color happens to be. `blueColor` (Streamlit's separate "info" semantic, used by `st.info()`) is retuned to `INK["muted"]` rather than left at Streamlit's default blue, which otherwise clashes with everything else on the page.

If the palette or fonts ever change, update the hex values in both `utils/theme.py` and `.streamlit/config.toml` - they're not derived from each other.

### Deliberately light-only, no dark mode

`.streamlit/config.toml` sets `base = "light"` with a fixed, non-reactive `textColor` - Streamlit's `[theme]` config is static, it has no way to also define a dark variant that activates automatically. `utils/theme.py`'s custom CSS used to independently darken `.pp-*` backgrounds via `@media (prefers-color-scheme: dark)` when the OS/browser preferred dark - but every *native* Streamlit widget (radio labels, checkboxes, captions, the footer text) kept rendering with config.toml's fixed light-mode `textColor`, since that CSS variable swap only reached the custom markup this file controls, not Streamlit's own rendering. The result was dark text on a dark background for a large share of the page - confirmed live with Playwright's dark `color_scheme` emulation before the fix, and re-confirmed clean afterward.

Removed the reactive override rather than patching it - making this genuinely dark-mode-safe would mean re-deriving and maintaining a full parallel palette for every native widget Streamlit itself renders (not just custom `.pp-*` markup), which `.streamlit/config.toml`'s static `[theme]` format can't express conditionally anyway. The app now renders identically regardless of OS/browser color-scheme preference, matching what its native Streamlit chrome was already doing.

Both flows are a TurboTax/Stripe-onboarding-style wizard rather than one long page: single check is **Your Land → Review & Analyze → Results**, compare is **Your Plot → Neighbor's Plot → Review & Compare → Results**. Current step is a plain int in `st.session_state` (`_wiz1` / `_wiz2`, one namespace per flow so switching the mode radio doesn't lose either flow's progress), advanced only by that flow's own Back/Continue buttons - never by a bare rerun - so a step never silently jumps. `render_wizard()` in `app_home.py` draws the stepper header (done/active/upcoming circles + connecting line, `.pp-wizard-*` classes in `utils/theme.py`) from that same int, so the visual state and the actual gating logic can never disagree.

Splitting comparison into two separate steps (rather than both plots stacked on one page, Plot B merely disabled pre-consent) puts the neighbor-consent gate on its own screen instead of buried under an unrelated upload widget - a real reduction in what's on screen at once, not just a re-skin. The review step in both flows (before the destructive/costly action - analyzing or comparing) previews what's about to run (point counts, CRS conversion, any beacon-order/CRS-confidence warnings) and gives a Back button to fix something before committing, rather than only finding out something was wrong from an error after the fact.

### Staged, animated reveal (within a step)

Within the "Your Land" / "Your Plot" / "Neighbor's Plot" steps, the coordinate-confirmation section (CRS override, bearing/distance review, the coordinates box) stays hidden until there's actually something to confirm - a file upload, prior manual entry, or an explicit "Or, enter coordinates manually" click - rather than showing every widget at once. Sticky per section (`k("_stage2_revealed")` in `st.session_state`, only ever set `True`) so nothing already shown ever disappears again mid-edit.

Each of these sections, plus the wizard's own Continue/action buttons and results, is wrapped in `st.container(key="pp_stage_...")`, which Streamlit renders as a `<div class="st-key-pp_stage_...">` - `utils/theme.py`'s `get_css()` targets that class with an attribute-substring selector (`[class*="st-key-pp_stage_"]`) and a `ppFadeInUp` keyframe animation (fades in, slides up 14px), so newly-revealed content animates in rather than snapping into place; `prefers-reduced-motion` is respected.

### Animated analysis progress

The "Analyze My Land" / "Compare Plots" action runs inside `st.status(..., expanded=True)` instead of a bare `st.spinner`, writing one line per real step as it actually happens (loading known plots, building the boundary, checking overlaps, calculating risk) rather than a single opaque "Loading...". Every line reflects work that's genuinely running at that moment - nothing is faked - though since these particular steps normally finish in well under a second combined, a short `time.sleep(0.2)` between lines paces them so they're readable instead of flashing past faster than anyone could follow; total added latency is under a second.

### Plain-language results

Right under the risk badge, `render_results()` shows one sentence naming the *specific* reason for that result (`_risk_reason()` in `app_home.py` - "Your boundary overlaps registered plot LOS-0142 by about 2383 m²", mirroring `utils/risk_calculator.py`'s own Low/Medium/High branching so it can never contradict the badge above it), plus a collapsed "What does this risk level mean?" expander with a generic explanation of that level for someone who's never seen a risk report before. The existing Key Findings/Recommendations list still follows for full detail - this is a lead sentence in front of it, not a replacement.

### Help panel

A static "Common Questions" page (`pages/faq.py`, linked from the sidebar - see "Sidebar nav" below, reachable from every page) answers what a first-time, non-surveyor visitor is most likely to wonder - what a survey plan is, what coordinates are, why a result might get flagged (reusing the same `RISK_EXPLAINER` copy as the results page's own "What does this risk level mean?" expander - both now live in `utils/theme.py` - so the two can never disagree), and what's actually in the downloadable report. Answers are hand-written directly in `pages/faq.py`, not a live model call - fixed, reviewable, no per-question API cost, and can't hallucinate. Originally an expander embedded in the sidebar itself; moved to its own page (same reasoning as the Terms/Privacy content below) so the sidebar stays a short, fixed set of links rather than growing a variable-height content block.

### Extended document extraction

Beyond coordinates, both extraction paths now read the plan's own document-level metadata - survey number, surveyor name, plan date, scale, area - shown in a "Document Details" card above the coordinates box (`render_document_input()` in `app_home.py`). The vision path (`utils/vision_extract.py`, Claude reading an image) reads these directly off the page, same reliability as the coordinates it already extracts. The text/OCR path (PDFs, or images without a vision call) uses a new `utils/document_metadata.py` - regex pattern-matching against common Nigerian survey-plan phrasing ("SURVEY No:", "SURVEYED BY:", "SCALE:-1:500", etc.), inherently more fragile than the vision path (same caveat as the rest of text extraction - see "Image OCR quality" above), so fields come back `None` rather than a guess when a pattern doesn't match cleanly, and the card is labeled "auto-read - verify against your document" rather than presented as certain.

### Report-grounded AI assistant

An "Ask about this report" expander on the results page (`utils/assistant.py`) answers plain-English questions about *this specific result* using Claude, grounded in the actual computed data (risk level, why, findings, recommendations, coordinate count, CRS note, document details) passed in as context - never general chat, and instructed to say "ask a licensed surveyor/lawyer" rather than guess when a question needs something PlotProof doesn't have. Hidden entirely when no API key is configured (`assistant.is_available()`), and gated behind its own daily cap (`DAILY_ASSISTANT_LIMIT`, default 10) plus the existing burst limiter, since like vision extraction this is a real per-request API cost.

The question box is cleared via the `st.button(..., on_click=...)` callback pattern, not the more obvious-looking `del st.session_state[key]` immediately followed by `st.rerun()` right after the button - confirmed directly (a minimal repro script) that the latter does not actually reset a `text_input` in the Streamlit version this app runs on, so the callback clears it instead, which does work.

### Automated integrity checks

Two real, checkable heuristics, clearly labeled as automated rather than a certified finding - deliberately narrower than a full "fraud detection" system, since inventing signal where there's no real data behind it would be actively misleading on a tool people use to avoid land fraud:

- **Impossible/self-intersecting geometry** (`gis_processing.check_boundary_validity()`) - a "bowtie" boundary (shapely `is_valid` false) isn't a geometrically possible plot outline, and usually means a beacon is out of order or a coordinate was mistyped. Checked on every analysis and comparison, shown via `render_results()` (recomputed there specifically, not passed through from the analysis step, since a warning shown mid-`st.status()` right before `st.rerun()` gets wiped before it's ever visible - confirmed as a real bug during testing, not just a hypothetical).
- **Low image quality** (`file_handler.check_image_quality()`) - flags a photo under 600px on its shorter side, or one that looks blurry (PIL-only stand-in for "variance of Laplacian": edge-detect via `ImageFilter.FIND_EDGES`, low result-stddev suggests smeared/out-of-focus edges). A rough heuristic, not a calibrated measurement.

A third check from the original wishlist - flagging a *duplicate* survey number against previously-seen plans - was deliberately **not** built. The only two persistent, consented data stores in this app (the shared registry, `utils/registry.py`; the extraction-improvement training data, `utils/training_data.py`) each have their own narrow, already-disclosed purpose in their consent copy ("only the boundary shape is stored, no document" for the registry; "used only to improve extraction, never shared" for training data) - repurposing either to cross-reference survey numbers across users would contradict a promise already shown to users, which needs its own explicit consent/copy change, not a silent side effect of a UX pass.

### Purchase-readiness checklist

A general, result-independent due-diligence checklist (`PURCHASE_CHECKLIST` in `app_home.py` - verify seller identity, visit the site, engage a surveyor, confirm no government acquisition, get legal review, confirm no encumbrance) on the results page, each item a plain checkbox with a completed-count progress bar. Distinct from `result["recommendations"]`, which is specific to what this particular check found - this is the same six items regardless of risk level, framed as "things to do before any purchase," not proof of anything about this plot.

### Map layers, measurement, and export formats

The results map (`render_results()` in `app_home.py`) now carries a Street/Satellite layer toggle (`folium.TileLayer` - OpenStreetMap plus Esri World Imagery, `folium.LayerControl` to switch), a fullscreen control, and a measure-distance/area tool (`folium.plugins.Fullscreen`/`MeasureControl`), on top of the existing zoom and legend. Street stays the default (`show=False` on the satellite layer) since it reads plot boundaries and labels more clearly at a glance; satellite is a one-click toggle for visual context (rooftops, vegetation, actual site conditions).

Downloads expand from PDF-only to three side-by-side buttons - PDF (the formatted report), CSV (just the boundary coordinates, for a spreadsheet), and GeoJSON (the boundary as a Polygon/Point feature with risk_level/findings/recommendations as properties, for a user's own GIS software). `utils/report_generator.py`'s `generate_csv_report()`/`generate_geojson_report()` are pure-stdlib (`csv`/`json`), no new dependency. The PDF itself gains a report ID (`generate_report_id()` - a timestamp plus a short random suffix, not a lookup key into anything stored server-side, since no report is persisted) shown in the header, and a QR code (`qrcode`, new dependency) in the footer area linking back to the app itself - not to "this report" specifically, since there's nowhere to host a per-report page without adding real backend storage.

### Accessibility & mobile

`utils/theme.py` sets a 44px minimum height on every button (WCAG 2.5.5 / Apple HIG's comfortable tap-target size - Streamlit's default runs smaller) and redraws a visible `:focus-visible` outline on interactive elements, since the app's custom border-radius styling can otherwise visually suppress the browser's default focus ring for keyboard users. A `max-width: 480px` media query keeps the landing hero, wizard stepper labels, and CTA buttons legible and full-width rather than cramped at phone width.

Fixing this surfaced two real layout bugs, not just phone-sized versions of the desktop layout: `.pp-cta-row`'s mobile column stacking reinterpreted each link's `flex: 1 1 200px` as a *height* instead of a width, ballooning the WhatsApp/Calendly buttons into ovals - fixed by pinning `.pp-cta` to `flex: none; width: 100%` on mobile. And `.pp-pill` (designed for short one-line badges, at `border-radius: 999px`) was also being used for multi-sentence coverage notes; at mobile width those wrap into enough lines that the uncapped pill radius rendered as a distorted egg shape rather than rounded corners - fixed by capping it to the standard `--pp-radius` below 480px. Verified via Playwright at a 390×844 mobile viewport across every step of both flows with `document.documentElement.scrollWidth` checked against `clientWidth` for horizontal overflow (none) alongside visual screenshots.

While in this file, also fixed a pre-existing bug in the "Add This Plot to the Shared Registry" card: it opened a `<div class="pp-card">` in one `st.markdown()` call and closed it in another, with the real `st.checkbox()` widget in between - but each `st.markdown()`/widget call renders as its own sibling DOM node in Streamlit, so the "wrapping" never actually nested anything. It rendered as an empty bordered box followed by unstyled floating text. Fixed by folding the title and paragraph into one `st.markdown()` call (closed properly) and leaving the checkbox as a plain widget after it, the same working pattern already used for the neighbor-consent card elsewhere in this file.

### Landing page

The first thing a visitor sees is a plain value-proposition splash, not the upload widget - `app_home.py` gates on a sticky `st.session_state["_entered_app"]` flag (same pattern as the consent gate right after it, and `st.stop()`s the rest of the script on that run) and shows a hero headline, a 3-step "how it works" (`.pp-landing-step`), a short trust checklist, and a single "Check My Land Now" button. Clicking it sets the flag and reruns straight into the existing consent gate and tool. It's built from the same `.pp-*` design-system classes as the rest of the app (plus a few `.pp-landing-*` additions in `utils/theme.py` for the larger centered hero and step-card grid) rather than embedding a separate static HTML file, so it can never visually drift from the tool it leads into.

### Sidebar nav, the About & Legal page, and the FAQ page

A persistent sidebar (`utils/nav.py`'s `render_sidebar()`, called from `app_home.py`, `pages/about.py`, and `pages/faq.py`) links "Land Risk Check", "About & Legal", and "Common Questions" - present on every page and every flow state (landing, consent gate, mid-wizard, results), not just the tool itself. Deliberately built by hand with `st.page_link()` rather than turning on `st.navigation()`'s own built-in nav UI, since that would list *every* registered page including the admin portal - `app.py` still runs with `position="hidden"` for exactly that reason (see its docstring), and the hand-rolled sidebar simply never includes a link to admin. Collapses automatically on mobile (Streamlit's native sidebar behavior), so it doesn't cost anything on small screens. The sidebar itself stays just those three fixed-height links - no expander or variable-height content lives in it directly, so it can't crowd out the nav below it regardless of how long any one page's content grows.

The full Terms of Service and Privacy Policy - genuinely long-form legal text (130+ lines combined) - used to sit inline in `app_home.py` behind expanders in two places (the consent gate, and again at the bottom of every results page). Both now link to `pages/about.py` instead (`st.page_link(...)`), which holds the actual long-form content once: a short "what PlotProof does" blurb plus the full Terms and Privacy Policy (`utils/legal.py`, unchanged). Keeps the main flow's own screen space for the tool itself rather than legal boilerplate, without removing the ability to read it before agreeing - the consent checkbox and gate logic are otherwise unchanged.

The FAQ (`pages/faq.py`) moved out of the main flow the same way, for the same reason - first into the sidebar as an expander, then (once that made the sidebar's own height vary depending on whether it was open) to its own page, exactly parallel to `pages/about.py`. `RISK_EXPLAINER` (previously private to `app_home.py`) now lives in `utils/theme.py` alongside the rest of the risk-level presentation constants, so the FAQ page and the results page's own risk explanation share one copy and can't disagree.

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
├── PlotProof Landing (standalone).html  # marketing page - source of truth for the design system
├── ADMIN_ACCESS.md             # local-only admin URL/password notes (gitignored, not in repo)
├── pages/
│   └── admin_review.py         # password-gated admin portal (API key + extraction review)
├── scripts/
│   └── vision_extract_prototype.py  # standalone CLI for testing vision extraction
├── requirements.txt
├── packages.txt                # apt packages for cloud deploy (tesseract-ocr)
├── .env.example
├── .streamlit/
│   └── config.toml             # disables usage telemetry + [theme] section (not a secret - committed)
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
