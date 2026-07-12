"""
Captures (document, extracted text, auto-detected guess, user-confirmed
ground truth) examples every time someone runs a survey plan through
PlotProof - opt-in only, never silent.

The extractor today is hand-written regexes and CRS heuristics; every new
plan format (a new surveyor's software, a different labeling convention)
means patching them by hand. This log is the raw material for eventually
training/fine-tuning a real extraction model instead - each record pairs
the source document/text with what a human actually confirmed as correct,
which is exactly what supervised training data looks like.

Storage mirrors file_handler.py: local JSON files by default, a Supabase
table once SUPABASE_URL/SUPABASE_KEY are configured. If you switch to
Supabase, create the table first:

    create table training_examples (
        id text primary key,
        timestamp timestamptz,
        source_file_ref text,
        file_type text,
        extraction_method text,
        raw_extracted_text text,
        auto_detected_points jsonb,
        auto_detected_crs_note text,
        user_confirmed_points jsonb,
        was_corrected boolean
    );
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

TRAINING_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "training_examples"
TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def record_example(
    source_file_ref: Optional[str],
    file_type: str,
    extraction_method: str,
    raw_extracted_text: str,
    auto_detected_points: List[Tuple[float, float]],
    auto_detected_crs_note: Optional[str],
    user_confirmed_points: List[Tuple[float, float]],
) -> None:
    record = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_file_ref": source_file_ref,
        "file_type": file_type,
        "extraction_method": extraction_method,
        "raw_extracted_text": raw_extracted_text,
        "auto_detected_points": auto_detected_points,
        "auto_detected_crs_note": auto_detected_crs_note,
        "user_confirmed_points": user_confirmed_points,
        "was_corrected": auto_detected_points != user_confirmed_points,
    }

    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("training_examples").insert(record).execute()
        return

    dest = TRAINING_DATA_DIR / f"{record['id']}.json"
    dest.write_text(json.dumps(record, indent=2))


def list_examples() -> List[dict]:
    """All opt-in examples collected so far, newest first - used by the
    admin review portal (pages/admin_review.py) to surface real-world
    extraction failures like a document that returned zero auto-detected
    points despite being legible, or one a user had to heavily correct."""
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        response = client.table("training_examples").select("*").order("timestamp", desc=True).execute()
        return response.data

    records = []
    for path in TRAINING_DATA_DIR.glob("*.json"):
        try:
            records.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records
