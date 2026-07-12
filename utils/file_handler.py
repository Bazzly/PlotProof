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
from typing import Optional, Tuple

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageFilter, ImageOps

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


_OCR_TARGET_SIZE_PX = 2400  # long-side target; phone photos are often smaller
# or over-compressed relative to what Tesseract wants (~300 DPI equivalent).


def _correct_orientation(image: Image.Image) -> Image.Image:
    """Rotates upright using Tesseract's own orientation detection - phone
    photos are routinely sideways/upside-down in ways EXIF doesn't capture
    (or that get stripped on upload). Falls back to the original image if
    OSD can't find enough text to judge orientation (common on sparse
    drawings), rather than failing the whole extraction over it."""
    try:
        osd = pytesseract.image_to_osd(image, config="--psm 0")
        rotate = int(next(line for line in osd.splitlines() if line.startswith("Rotate:")).split(":")[1])
        if rotate:
            return image.rotate(-rotate, expand=True)
    except Exception:
        pass
    return image


def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Cleans up a phone-photo-quality image before OCR. Survey plan photos
    typically arrive blurry, low-contrast, and undersized compared to the
    crisp, computer-rendered pages this pipeline was originally tuned on -
    plain OCR on the raw photo silently drops or mangles digits (confirmed:
    "750615.672" reads back as "750615672", losing the decimal point and
    therefore the whole coordinate, since the number regex requires one)."""
    image = ImageOps.exif_transpose(image)  # bake in phone-stored rotation, if present
    image = _correct_orientation(image)
    image = image.convert("L")  # grayscale

    if max(image.size) < _OCR_TARGET_SIZE_PX:
        scale = _OCR_TARGET_SIZE_PX / max(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)

    image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=2))
    image = ImageOps.autocontrast(image, cutoff=1)
    return image


def _ocr(image: Image.Image) -> str:
    # psm 6 ("a single uniform block of text") consistently kept multi-digit
    # coordinates on one line better than the default automatic segmentation
    # or sparse-text modes, which tended to split long numbers across lines.
    return pytesseract.image_to_string(_preprocess_for_ocr(image), config="--psm 6")


def extract_text_from_pdf(file_path: str) -> Tuple[str, str]:
    """Extract selectable text from a PDF; falls back to OCR per-page if empty.
    Returns (text, method) where method is "pdf_text" or "ocr" - useful to
    know later, since OCR output is noisier than a real text layer."""
    doc = fitz.open(file_path)
    text_parts = [page.get_text() for page in doc]
    text = "\n".join(text_parts).strip()

    if text:
        doc.close()
        return text, "pdf_text"

    # No text layer (scanned survey plan) - rasterize each page and OCR it.
    ocr_parts = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        ocr_parts.append(_ocr(image))
    doc.close()
    return "\n".join(ocr_parts).strip(), "ocr"


def extract_text_from_image(file_path: str) -> Tuple[str, str]:
    image = Image.open(file_path)
    return _ocr(image).strip(), "ocr"


def extract_text_from_file(file_path: str) -> Tuple[str, str]:
    """Returns (text, method); method is "" when the extension isn't supported."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    if ext in (".png", ".jpg", ".jpeg"):
        return extract_text_from_image(file_path)
    return "", ""
