# LandVerify

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
git add app.py utils requirements.txt packages.txt .env.example .gitignore data/sample_data
git commit -m "LandVerify MVP"
git remote add origin https://github.com/<your-username>/landverify.git
git branch -M main
git push -u origin main
```

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
   WHATSAPP_LINK = "https://wa.me/2349051004636"
   CALENDLY_LINK = "https://calendly.com/bazzlycodes"
   ```
   Streamlit Cloud exposes these as environment variables at runtime - no code changes needed. Leave `SUPABASE_URL`/`SUPABASE_KEY` blank to keep using local disk storage.
5. Click **Deploy**. First build takes a few minutes (installs GeoPandas/Shapely/tesseract).

You'll get a live URL like `https://landverify.streamlit.app`.

### 4. Storage note

Streamlit Cloud's filesystem is ephemeral - uploaded survey files saved to `data/uploads/` won't persist across app restarts/redeploys. That's fine for now since the app only needs the file for the current session's analysis. To retain uploads long-term, create a Supabase project and set `SUPABASE_URL`/`SUPABASE_KEY` above - `utils/file_handler.py` switches to Supabase Storage automatically once those are set.

### 5. Custom domain (optional)

Streamlit Cloud apps can be pointed at a custom domain via a CNAME record once you have one picked.

## Project structure

```
landSuite/
├── app.py                      # Streamlit app
├── requirements.txt
├── packages.txt                # apt packages for cloud deploy (tesseract-ocr)
├── .env.example
├── utils/
│   ├── coordinates.py          # shared coordinate text parsing/validation
│   ├── file_handler.py         # upload storage + PDF/image text & OCR extraction
│   ├── gis_processing.py       # GeoPandas overlap/proximity analysis
│   ├── risk_calculator.py      # risk scoring from GIS results
│   └── report_generator.py     # PDF report generation
├── data/
│   ├── sample_data/            # synthetic neighboring-plot data for demo/testing
│   └── uploads/                # local upload storage (until Supabase is configured)
└── doc/                        # product spec, architecture notes, planning docs
```
