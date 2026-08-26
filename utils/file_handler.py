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
from PIL import Image, ImageFilter, ImageOps, ImageStat

# Below this on the shorter side, extraction (OCR or vision) is working
# with too few pixels per printed character to read reliably regardless of
# focus - a real, checkable floor, not a blur heuristic.
_MIN_DIMENSION_PX = 600

# Standard-deviation-of-edges-after-FIND_EDGES is a coarse, PIL-only stand-in
# for the classic "variance of Laplacian" blur metric (no numpy/opencv
# dependency needed) - a sharp, in-focus photo has strong edges and high
# variance; a blurry one's edges are smeared out and the variance is low.
# This threshold is a rough heuristic, not a calibrated measurement -
# labeled as such wherever it's shown to the user.
_BLUR_STDDEV_THRESHOLD = 8.0


def check_image_quality(image_path: str) -> Optional[str]:
    """Returns a plain-English warning if the image looks too low-resolution
    or too blurry for extraction to read reliably, else None. Best-effort
    heuristic (see _BLUR_STDDEV_THRESHOLD) - flags "this might be hard to
    read", not a certified image-quality measurement."""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if min(width, height) < _MIN_DIMENSION_PX:
                return (
                    f"This image is quite low-resolution ({width}x{height}px), which can make "
                    "coordinates and text hard to read accurately. A higher-resolution photo or "
                    "scan, if you have one, would give a more reliable result."
                )
            edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
            stddev = ImageStat.Stat(edges).stddev[0]
            if stddev < _BLUR_STDDEV_THRESHOLD:
                return (
                    "This image looks like it might be blurry or out of focus, which can make "
                    "coordinates and text hard to read accurately. A sharper photo or scan, if you "
                    "have one, would give a more reliable result."
                )
    except Exception:
        return None
    return None

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

    # Re-asserted here, not just at module import - a long-running process
    # (Streamlit doesn't reload utils/ modules between reruns) would
    # otherwise keep writing to a directory that's since been deleted out
    # from under it (log rotation, a deploy reset, manual cleanup) with no
    # way to recover short of a process restart.
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / filename
    dest.write_bytes(file_bytes)
    return str(dest)


LISTING_PHOTOS_DIR = Path(__file__).resolve().parent.parent / "data" / "listing_photos"
LISTING_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

# A listing card only ever needs web-display resolution, but sellers
# routinely upload multi-MB phone photos straight from the camera -
# every photo is re-encoded to this cap regardless of its original size/
# format, which is where the real storage savings come from (a typical
# 4-8MB phone photo becomes a few hundred KB).
_LISTING_PHOTO_MAX_DIMENSION = 1600
_LISTING_PHOTO_JPEG_QUALITY = 78


def save_listing_photo(uploaded_file) -> str:
    """Compresses and persists a Land Listing photo (pages/listings.py's
    "Sell Your Land" tab) - always re-encoded as a resized JPEG, same
    local-disk-unless-Supabase-configured fallback as save_uploaded_file(),
    but its own bucket/directory (listing-photos, not survey-uploads)
    since these are meant to be public-facing images, unlike a seller's
    private survey document."""
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)  # bake in phone-stored rotation before resizing
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if max(image.size) > _LISTING_PHOTO_MAX_DIMENSION:
        scale = _LISTING_PHOTO_MAX_DIMENSION / max(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=_LISTING_PHOTO_JPEG_QUALITY, optimize=True)
    file_bytes = buffer.getvalue()
    filename = f"{uuid.uuid4().hex}.jpg"

    if storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.storage.from_("listing-photos").upload(filename, file_bytes, {"content-type": "image/jpeg"})
        return f"supabase://listing-photos/{filename}"

    LISTING_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    dest = LISTING_PHOTOS_DIR / filename
    dest.write_bytes(file_bytes)
    return str(dest)


def resolve_photo_url(photo_ref: str) -> Optional[str]:
    """A local path already works directly with st.image(); a
    "supabase://bucket/filename" reference (see save_listing_photo())
    needs resolving to a real public URL first - the listing-photos
    bucket is expected to be public (these are meant to be shown to
    every visitor), unlike survey-uploads."""
    if photo_ref.startswith("supabase://"):
        _, _, rest = photo_ref.partition("supabase://")
        bucket, _, filename = rest.partition("/")
        if storage_backend() != "supabase":
            return None
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        return client.storage.from_(bucket).get_public_url(filename)
    return photo_ref if os.path.isfile(photo_ref) else None


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


def render_pdf_first_page_png(file_path: str) -> Optional[bytes]:
    """Rasterizes just the first page as PNG bytes - for on-screen preview
    (e.g. the diagonal calculator's click-to-trace fallback, pages/
    diagonal_calculator.py) when a PDF's automatic extraction found
    nothing, so there's still something to look at and trace corners
    against. 150dpi (vs. extract_text_from_pdf()'s 300dpi for OCR
    accuracy) - plenty sharp for display, keeps the rendered image small.
    Returns None if the file can't be opened as a PDF at all."""
    try:
        doc = fitz.open(file_path)
    except Exception:
        return None
    try:
        if doc.page_count == 0:
            return None
        pix = doc[0].get_pixmap(dpi=150)
        return pix.tobytes("png")
    finally:
        doc.close()
