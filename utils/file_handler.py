"""
File upload storage and text/coordinate extraction for PlotProof.

Storage: uses local disk under data/uploads/ by default. If SUPABASE_URL
and SUPABASE_KEY are set in the environment, uploads are pushed to
Supabase Storage instead. Local storage requires no external setup, so
it's the default until a Supabase project is wired up.

Extraction: survey plans are usually exported as either a text-based PDF
(coordinates are selectable text) or a scanned image/photo. We try direct
text extraction first (fast, accurate) and only fall back to OCR when the
document has no extractable text layer.
"""

import io
import os
import uuid
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def save_uploaded_file(uploaded_file) -> str:
    """
    Persist a Streamlit UploadedFile and return a path/reference to it.
    Falls back to local disk unless Supabase credentials are configured.
    """
    suffix = Path(uploaded_file.name).suffix
    filename = f"{uuid.uuid4().hex}{suffix}"
    file_bytes = uploaded_file.getvalue()

    if storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.storage.from_("survey-uploads").upload(filename, file_bytes)
        return f"supabase://survey-uploads/{filename}"

    dest = UPLOAD_DIR / filename
    dest.write_bytes(file_bytes)
    return str(dest)


def extract_text_from_pdf(file_path: str) -> str:
    """Extract selectable text from a PDF; falls back to OCR per-page if empty."""
    doc = fitz.open(file_path)
    text_parts = [page.get_text() for page in doc]
    text = "\n".join(text_parts).strip()

    if text:
        doc.close()
        return text

    # No text layer (scanned survey plan) - rasterize each page and OCR it.
    ocr_parts = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        ocr_parts.append(pytesseract.image_to_string(image))
    doc.close()
    return "\n".join(ocr_parts).strip()


def extract_text_from_image(file_path: str) -> str:
    image = Image.open(file_path)
    return pytesseract.image_to_string(image).strip()


def extract_text_from_file(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    if ext in (".png", ".jpg", ".jpeg"):
        return extract_text_from_image(file_path)
    return ""
