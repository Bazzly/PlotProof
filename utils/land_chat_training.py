"""
Admin-managed training content for the floating "land chat"
(utils/nav.py's render_floating_chat(), matched by utils/land_chat_match.py).

Each record is a free-text passage the admin writes (not a rigid Q&A pair)
- the chat answers a visitor's question by finding the closest-matching
passage and returning its text verbatim. Managed entirely from the admin
portal's "Land Chat Training" tab (pages/admin_review.py) - there is no
other way to add content, and no external API is involved anywhere in
this path.

Storage mirrors the rest of the app: local JSON by default, a Supabase
table once SUPABASE_URL/SUPABASE_KEY are configured (create the table
first - schema below). Kept as a single record-list file (like
utils/registry.py), not one-file-per-record (like utils/training_data.py),
because this needs real update/delete - a whole-list read/write handles
both trivially.

    create table land_chat_passages (
        id text primary key,
        title text,
        text text,
        added_at timestamptz
    );
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

LAND_CHAT_DIR = Path(__file__).resolve().parent.parent / "data" / "land_chat"
LAND_CHAT_FILE = LAND_CHAT_DIR / "passages.json"

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def _load_local_records() -> list:
    if not LAND_CHAT_FILE.exists():
        return []
    try:
        return json.loads(LAND_CHAT_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_local_records(records: list) -> None:
    # Re-asserted here, not just at module import - a long-running process
    # (Streamlit doesn't reload utils/ modules between reruns) would
    # otherwise keep failing to write once this directory's been deleted
    # out from under it, with no way to recover short of a process restart.
    LAND_CHAT_DIR.mkdir(parents=True, exist_ok=True)
    LAND_CHAT_FILE.write_text(json.dumps(records, indent=2))


def list_passages() -> List[dict]:
    """Newest first."""
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        response = client.table("land_chat_passages").select("*").order("added_at", desc=True).execute()
        return response.data or []

    return sorted(_load_local_records(), key=lambda r: r.get("added_at", ""), reverse=True)


def add_passage(title: str, text: str) -> str:
    passage_id = uuid.uuid4().hex
    record = {
        "id": passage_id,
        "title": title.strip(),
        "text": text.strip(),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }

    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("land_chat_passages").insert(record).execute()
        return passage_id

    records = _load_local_records()
    records.append(record)
    _save_local_records(records)
    return passage_id


def update_passage(passage_id: str, title: str, text: str) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("land_chat_passages").update({"title": title.strip(), "text": text.strip()}).eq(
            "id", passage_id
        ).execute()
        return

    records = _load_local_records()
    for record in records:
        if record["id"] == passage_id:
            record["title"] = title.strip()
            record["text"] = text.strip()
            break
    _save_local_records(records)


def delete_passage(passage_id: str) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("land_chat_passages").delete().eq("id", passage_id).execute()
        return

    records = [r for r in _load_local_records() if r["id"] != passage_id]
    _save_local_records(records)
