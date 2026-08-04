"""
Storage for Property Requests - the inverse of Land Listings
(utils/listings.py): instead of a seller posting land for sale, this is
PlotProof posting a specific, verified buyer's request ("looking for
land in this price range/location") for anyone with matching property to
respond to. Shown on the "Property Requests" tab of pages/listings.py.

Admin-only by design (there's no public submission form for these, unlike
Land Listings) - a request goes live the moment an admin posts it from
pages/admin_review.py's "Property Requests" tab, since the admin already
is the vetting step (there's no external submitter to review, unlike a
seller's listing). status is just active/closed, not
pending/published/rejected.

verified_buyer defaults true (admin is expected to have actually spoken
to/vetted the buyer before posting a request on their behalf), but stays
a real field rather than being hardcoded, in case an admin wants to post
a lead that isn't fully vetted yet.

Contact is the same PlotProof-as-intermediary model as Land Listings
(utils/app_config.get_plotproof_contact_number()) - anyone who has
matching land contacts PlotProof, not the buyer directly, to arrange a
physical meeting.

Storage mirrors the rest of the app: local JSON by default, a Supabase
table once SUPABASE_URL/SUPABASE_KEY are configured (create the table
first - schema below).

    create table property_requests (
        id text primary key,
        status text,
        raw_text text,
        heading text,
        price_range text,
        location text,
        size text,
        requirements text,
        verified_buyer boolean,
        request_number integer,
        posted_at timestamptz,
        closed_at timestamptz
    );
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

REQUESTS_DIR = Path(__file__).resolve().parent.parent / "data" / "property_requests"
REQUESTS_FILE = REQUESTS_DIR / "requests.json"

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

STATUS_ACTIVE = "active"
STATUS_CLOSED = "closed"


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def _load_local_records() -> list:
    if not REQUESTS_FILE.exists():
        return []
    try:
        return json.loads(REQUESTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_local_records(records: list) -> None:
    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    REQUESTS_FILE.write_text(json.dumps(records, indent=2))


def list_requests(status: Optional[str] = None) -> List[dict]:
    """Newest first. status=None returns everything (admin view); pass
    STATUS_ACTIVE/STATUS_CLOSED to filter."""
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        query = client.table("property_requests").select("*")
        if status:
            query = query.eq("status", status)
        response = query.order("posted_at", desc=True).execute()
        return response.data or []

    records = _load_local_records()
    if status:
        records = [r for r in records if r.get("status") == status]
    return sorted(records, key=lambda r: r.get("posted_at", ""), reverse=True)


def list_active_ranked() -> List[dict]:
    """Verified-buyer requests first, then newest - the public Property
    Requests tab ranking."""
    active = list_requests(status=STATUS_ACTIVE)
    return sorted(active, key=lambda r: (0 if r.get("verified_buyer") else 1, r.get("posted_at", "")))


def next_request_number() -> int:
    """Own sequence, independent of Land Listings' "Land Alert #NNN"
    (utils/listings.next_alert_number()) - these are two different public
    streams (land for sale vs. buyers looking), and sharing one counter
    would just make each series' numbers look like they have unexplained
    gaps. Same derive-from-existing-max approach and same rationale for
    why that's good enough here - see next_alert_number()'s docstring."""
    existing = [r["request_number"] for r in list_requests() if r.get("request_number")]
    return (max(existing) + 1) if existing else 1


def get_request(request_id: str) -> Optional[dict]:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        response = client.table("property_requests").select("*").eq("id", request_id).execute()
        return response.data[0] if response.data else None

    return next((r for r in _load_local_records() if r["id"] == request_id), None)


def add_request(**fields) -> str:
    request_id = uuid.uuid4().hex[:10]
    record = {
        "id": request_id,
        "status": STATUS_ACTIVE,
        "raw_text": "",
        "heading": "",
        "price_range": "",
        "location": "",
        "size": "",
        "requirements": "",
        "verified_buyer": True,
        "request_number": None,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": None,
        **fields,
    }

    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("property_requests").insert(record).execute()
        return request_id

    records = _load_local_records()
    records.append(record)
    _save_local_records(records)
    return request_id


def update_request(request_id: str, **fields) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("property_requests").update(fields).eq("id", request_id).execute()
        return

    records = _load_local_records()
    for record in records:
        if record["id"] == request_id:
            record.update(fields)
            break
    _save_local_records(records)


def delete_request(request_id: str) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("property_requests").delete().eq("id", request_id).execute()
        return

    records = [r for r in _load_local_records() if r["id"] != request_id]
    _save_local_records(records)
