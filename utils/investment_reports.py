"""
Storage for completed Investment Analysis reports, so a report can have a
real "Shareable Report Link" (pages/investment_analysis.py reads
?report=<id> from st.query_params to render a saved one read-only) instead
of the export just being a stub.

Stores the location/radius/score/narrative snapshot only - NOT the raw
OpenStreetMap features (roads/amenities/landuse geometry), which would
bloat every saved record for no real benefit: the shared view re-fetches
those from utils/osm_service.fetch_nearby_features() on demand, which is
itself cached by (lat, lon, radius) and typically a cache hit anyway.

Storage mirrors the rest of the app: local JSON by default, a Supabase
table once SUPABASE_URL/SUPABASE_KEY are configured (create the table
first - schema below). Reports are immutable snapshots once saved - no
update, only add/get, unlike utils/land_chat_training.py's admin-editable
passages.

    create table investment_reports (
        id text primary key,
        location jsonb,
        radius_m integer,
        score jsonb,
        narrative jsonb,
        created_at timestamptz
    );
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "investment_reports"
REPORTS_FILE = REPORTS_DIR / "reports.json"

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def _load_local_records() -> dict:
    if not REPORTS_FILE.exists():
        return {}
    try:
        return json.loads(REPORTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_local_records(records: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_FILE.write_text(json.dumps(records, indent=2))


def save_report(
    location: dict, radius_m: int, score: dict, narrative: Optional[dict], used_fallback: bool = False
) -> str:
    report_id = uuid.uuid4().hex[:10]
    record = {
        "id": report_id,
        "location": location,
        "radius_m": radius_m,
        "score": score,
        "narrative": narrative,
        "used_fallback": used_fallback,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("investment_reports").insert(record).execute()
        return report_id

    records = _load_local_records()
    records[report_id] = record
    _save_local_records(records)
    return report_id


def get_report(report_id: str) -> Optional[dict]:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        response = client.table("investment_reports").select("*").eq("id", report_id).execute()
        return response.data[0] if response.data else None

    return _load_local_records().get(report_id)
