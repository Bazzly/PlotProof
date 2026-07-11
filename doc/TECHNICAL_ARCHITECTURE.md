# LandVerify - Technical Architecture (MVP & Beyond)

## 1. High-Level Architecture

```
User (Browser)
    ↓
Streamlit Frontend (or Next.js later)
    ↓
FastAPI Backend (optional for scaling)
    ↓
GIS Processing Layer (GeoPandas + Shapely)
    ↓
Database (Supabase Postgres)
    ↓
File Storage (Supabase Storage / Cloudinary)
```

For **MVP**, we keep everything in one Streamlit app for speed.

---

## 2. Core Components

### 2.1 Frontend (Streamlit)
- Simple, fast UI
- File upload (PDF/Image)
- Coordinate input
- Results display + PDF download
- Consultation booking CTA

### 2.2 GIS Processing Module (`utils/gis_processing.py`)
Responsibilities:
- Parse uploaded survey plans (basic coordinate extraction first)
- Convert to GeoDataFrame
- Perform spatial operations:
  - Buffer / overlay checks
  - Overlap detection with neighboring plots
  - Coordinate system validation (CRS)
- Return structured risk assessment

**Future improvements**:
- OCR for PDF/image text extraction
- Integration with public land records (when available)
- Satellite imagery comparison

### 2.3 Report Generation (`utils/report_generator.py`)
- Generate clean PDF reports using ReportLab
- Include:
  - Risk score
  - Key findings
  - Recommendations
  - Timestamp + user reference

### 2.4 Data Storage
- **Supabase Postgres**: Store user uploads metadata + analysis results
- **Supabase Storage**: Store uploaded survey plans and generated reports
- Later: User accounts + history

---

## 3. Data Flow (MVP)

1. User uploads file or enters coordinates
2. File is temporarily stored
3. Coordinates are extracted or used directly
4. GeoPandas performs spatial analysis
5. Risk score + findings are generated
6. PDF report is created
7. Results shown to user + option to download
8. (Optional) Save anonymized data for improvement

---

## 4. Technology Choices (MVP)

| Component            | Technology              | Reason                              |
|----------------------|-------------------------|-------------------------------------|
| Frontend             | Streamlit               | Fastest way to build usable MVP     |
| GIS Engine           | GeoPandas + Shapely     | You already have experience         |
| PDF Generation       | ReportLab               | Simple and reliable                 |
| Database + Auth      | Supabase                | Easy setup, Postgres + Storage      |
| Hosting              | Render.com              | Free tier + easy Python deployment  |
| Version Control      | Git + GitHub            | Standard                            |

**Alternative stack** (if you prefer):
- Next.js + Tailwind (frontend)
- FastAPI (backend)
- Same GIS layer

---

## 5. Folder Structure (Recommended)

```
landverify/
├── app.py                      # Main Streamlit app
├── requirements.txt
├── .env.example
├── utils/
│   ├── __init__.py
│   ├── gis_processing.py       # Core spatial analysis logic
│   ├── report_generator.py     # PDF report creation
│   ├── file_handler.py         # Upload & storage helpers
│   └── risk_calculator.py      # Risk scoring logic
├── data/
│   └── sample_data/            # Test shapefiles or coordinates
├── assets/
│   └── logo.png
├── docs/
│   └── TECHNICAL_ARCHITECTURE.md
└── README.md
```

---

## 6. Environment Variables (.env)

Create a `.env` file with:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
```

---

## 7. Development Roadmap

### Phase 1 (Current - MVP)
- Basic upload + coordinate input
- Dummy / simple GeoPandas analysis
- Risk score + PDF report
- Consultation CTA

### Phase 2
- Real spatial overlap detection
- Better PDF reports with maps
- Basic user session (email collection)
- Deployed version on Render

### Phase 3
- OCR support for PDFs/images
- Historical satellite comparison
- User accounts + saved reports
- Premium monitoring features

---

## 8. Key Technical Challenges & Solutions

| Challenge                        | Solution (MVP)                          | Future Improvement                     |
|----------------------------------|-----------------------------------------|----------------------------------------|
| Extracting coordinates from PDF  | Ask user to enter manually first        | OCR + LLM parsing                      |
| Getting neighboring plot data    | Use sample/test data                    | Integrate public land records          |
| Handling different CRS           | Standardize to WGS84                    | Auto-detection + transformation        |
| Performance with large files     | Limit file size + async processing      | Background jobs (Celery / RQ)          |

---

## 9. Next Immediate Technical Tasks

1. Set up Supabase project
2. Install requirements: `pip install -r requirements.txt`
3. Run the starter `app.py` and test the flow
4. Replace dummy risk logic in `app.py` with real GeoPandas code in `utils/gis_processing.py`
5. Improve the PDF report generation

---

**This architecture keeps things simple for the MVP while leaving room to scale.**

You can evolve from Streamlit → full web app later without rewriting everything.

Good luck with development! 🚀

— Generated for @bazzlycodes