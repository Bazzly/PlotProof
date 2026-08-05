"""
Storage for the Land Listings marketplace (pages/listings.py) - a seller
submits a listing (raw text + optional coordinates), it starts "pending"
and is invisible to the public until an admin reviews and publishes it
from pages/admin_review.py's "Listings" tab - same trust gate this app
already applies to other shared/public data (utils/registry.py's plots,
utils/land_chat_training.py's chat content).

Risk rating: risk_level/risk_result are set automatically when the seller
supplied coordinates (the real utils/risk_calculator.py pipeline, not a
guess - see pages/listings.py). admin_risk_override lets an admin set or
correct the rating by hand (e.g. no coordinates were given, or the admin
disagrees) - list_published_ranked() below prefers the override when
present, falling back to the automated result.

verification_requested/verified are separate: a seller can ask for paid
"PlotProof Verified" status, but nothing is charged in-app - an admin
marks `verified` true only after confirming payment out-of-band (see
utils/investment_analysis.py-style modules elsewhere in this app for why:
no payment gateway exists in this project). Ranking rewards `verified`
independently of risk_level, since they answer different questions
("is this real money-backed trust" vs "did the boundary check pass").

Storage mirrors the rest of the app: local JSON by default, a Supabase
table once SUPABASE_URL/SUPABASE_KEY are configured (create the table
first - schema below).

    create table listings (
        id text primary key,
        status text,
        raw_text text,
        heading text,
        size text,
        price text,
        location text,
        title_type text,
        fee_note text,
        seller_contact text,
        coordinates_text text,
        coordinate_epsg text,
        points jsonb,
        photo_paths jsonb,
        video_url text,
        risk_level text,
        risk_result jsonb,
        admin_risk_override text,
        verification_requested boolean,
        verified boolean,
        alert_number integer,
        sold boolean,
        sold_at timestamptz,
        submitted_at timestamptz,
        reviewed_at timestamptz
    );
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

LISTINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "listings"
LISTINGS_FILE = LISTINGS_DIR / "listings.json"

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

STATUS_PENDING = "pending"
STATUS_PUBLISHED = "published"
STATUS_REJECTED = "rejected"

# Higher first. A rating not in this map (i.e. None/unrated) sorts last.
_RISK_RANK = {"Low": 3, "Medium": 2, "High": 1}


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def _load_local_records() -> list:
    if not LISTINGS_FILE.exists():
        return []
    try:
        return json.loads(LISTINGS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_local_records(records: list) -> None:
    LISTINGS_DIR.mkdir(parents=True, exist_ok=True)
    LISTINGS_FILE.write_text(json.dumps(records, indent=2))


def list_listings(status: Optional[str] = None) -> List[dict]:
    """Newest first. status=None returns everything (admin view);
    pass STATUS_PENDING/PUBLISHED/REJECTED to filter."""
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        query = client.table("listings").select("*")
        if status:
            query = query.eq("status", status)
        response = query.order("submitted_at", desc=True).execute()
        return response.data or []

    records = _load_local_records()
    if status:
        records = [r for r in records if r.get("status") == status]
    return sorted(records, key=lambda r: r.get("submitted_at", ""), reverse=True)


def effective_risk_level(listing: dict) -> Optional[str]:
    """admin_risk_override wins when set - an admin correcting/assigning
    a rating by hand should always take precedence over the automated
    result, per this feature's design (see module docstring)."""
    return listing.get("admin_risk_override") or listing.get("risk_level")


def next_alert_number() -> int:
    """The next sequential "Land Alert #NNN" number (utils/listing_format.
    format_listing_post()) - derived from the highest number already
    assigned rather than a dedicated counter row/file, since this app's
    publish volume is low and a rare duplicate on a genuine race is a
    cosmetic, not correctness, issue. Assign once per listing (at publish
    time - see pages/admin_review.py) and never reassign, so a listing's
    number - its public signature - stays stable across edits/republishing."""
    existing = [r["alert_number"] for r in list_listings() if r.get("alert_number")]
    return (max(existing) + 1) if existing else 1


def list_published_ranked() -> List[dict]:
    """Unsold, verified listings first, then by risk (Low > Medium > High
    > unrated), then newest - the public Browse Listings ranking.
    Listings an admin has marked sold (pages/admin_review.py's "Mark as
    Sold") stay visible here too (tagged SOLD by the caller - see
    pages/listings.py), just sorted to the bottom regardless of their
    other rankings, since they're no longer actionable but are still
    real, useful signal (recent activity, a sense of what sells)."""
    published = list_listings(status=STATUS_PUBLISHED)

    def sort_key(listing: dict):
        return (
            1 if listing.get("sold") else 0,
            0 if listing.get("verified") else 1,
            -_RISK_RANK.get(effective_risk_level(listing), 0),
            listing.get("submitted_at", ""),
        )

    return sorted(published, key=sort_key)


def get_listing(listing_id: str) -> Optional[dict]:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        response = client.table("listings").select("*").eq("id", listing_id).execute()
        return response.data[0] if response.data else None

    return next((r for r in _load_local_records() if r["id"] == listing_id), None)


def add_listing(**fields) -> str:
    listing_id = uuid.uuid4().hex[:10]
    record = {
        "id": listing_id,
        "status": STATUS_PENDING,
        "raw_text": "",
        "heading": "",
        "size": "",
        "price": "",
        "location": "",
        "title_type": "",
        "fee_note": "",
        "seller_contact": "",
        "coordinates_text": None,
        "coordinate_epsg": None,
        "points": None,
        "photo_paths": [],
        "video_url": None,
        "risk_level": None,
        "risk_result": None,
        "admin_risk_override": None,
        "verification_requested": False,
        "verified": False,
        "alert_number": None,
        "sold": False,
        "sold_at": None,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_at": None,
        **fields,
    }

    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("listings").insert(record).execute()
        return listing_id

    records = _load_local_records()
    records.append(record)
    _save_local_records(records)
    return listing_id


def update_listing(listing_id: str, **fields) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("listings").update(fields).eq("id", listing_id).execute()
        return

    records = _load_local_records()
    for record in records:
        if record["id"] == listing_id:
            record.update(fields)
            break
    _save_local_records(records)


def delete_listing(listing_id: str) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("listings").delete().eq("id", listing_id).execute()
        return

    records = [r for r in _load_local_records() if r["id"] != listing_id]
    _save_local_records(records)
