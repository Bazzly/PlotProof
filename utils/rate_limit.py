"""
Per-client rate limiting - protects both the (paid) vision extraction API
and general server resources from a single visitor hammering the app.

Two independent layers:

  - Daily caps (check_daily_limit): a persistent per-client-per-day counter,
    e.g. "3 land checks per day." Survives restarts within the same day
    (stored like the rest of the app's data - local JSON by default,
    Supabase once configured), so it can't be bypassed by just reloading
    the page. This is the meaningful cost/abuse control.

  - Burst limiter (check_burst_limit): an in-memory sliding window, e.g.
    "no more than 10 actions per 60 seconds," to blunt rapid automated
    hammering within a single day's allowance. Deliberately NOT persisted -
    it only needs to catch bursts on the timescale of seconds/minutes, and
    an in-memory store keeps it fast. Caveat: this resets on process
    restart and doesn't share state across multiple app instances - fine
    for this app's expected single-instance deployment (Streamlit Community
    Cloud free tier), not a substitute for a real edge/WAF rate limiter if
    this ever runs behind a load balancer with multiple replicas.

Client identification (get_client_id): best-effort, since Streamlit has no
concept of a logged-in user. Prefers the X-Forwarded-For header (the real
client IP when running behind Streamlit Cloud's proxy), falls back to
st.context.ip_address, and falls back to a random ID persisted in
st.session_state as a last resort (weak - a new browser session gets a
fresh allowance - but better than no identifier at all, e.g. in local dev
where loopback requests have no usable IP).
"""

import json
import os
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import streamlit as st

RATE_LIMIT_DIR = Path(__file__).resolve().parent.parent / "data" / "rate_limits"
RATE_LIMIT_DIR.mkdir(parents=True, exist_ok=True)
USAGE_FILE = RATE_LIMIT_DIR / "daily_usage.json"

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# In-memory only, by design - see module docstring.
_burst_log: Dict[str, deque] = defaultdict(deque)


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def get_client_id() -> str:
    forwarded = st.context.headers.get("X-Forwarded-For") if st.context.headers else None
    if forwarded:
        # Left-most entry is the original client; proxies append their own after it.
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return f"ip:{candidate}"

    if st.context.ip_address:
        return f"ip:{st.context.ip_address}"

    if "_rate_limit_client_id" not in st.session_state:
        st.session_state["_rate_limit_client_id"] = f"session:{uuid.uuid4().hex}"
    return st.session_state["_rate_limit_client_id"]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_local_usage() -> dict:
    if not USAGE_FILE.exists():
        return {}
    try:
        return json.loads(USAGE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_local_usage(data: dict) -> None:
    # Re-asserted here, not just at module import - a long-running process
    # (Streamlit doesn't reload utils/ modules between reruns) would
    # otherwise keep failing to write once this directory's been deleted
    # out from under it, with no way to recover short of a process restart.
    RATE_LIMIT_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, indent=2))


def _row_key(client_id: str, bucket: str, day: str) -> str:
    return f"{client_id}|{bucket}|{day}"


def check_daily_limit(client_id: str, bucket: str, limit: int) -> Tuple[bool, int]:
    """
    Checks and, if allowed, increments today's usage count for
    (client_id, bucket). Returns (allowed, remaining_after_this_call).

    bucket namespaces the counter - e.g. "analyze" and "vision_extract" are
    tracked separately, so a generous extraction allowance (re-uploads,
    CRS-override re-tries are normal single-session behavior) doesn't have
    to share a pool with the stricter "full check" allowance.
    """
    day = _today()

    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        row_id = _row_key(client_id, bucket, day)
        response = client.table("rate_limit_usage").select("count").eq("id", row_id).execute()
        current = response.data[0]["count"] if response.data else 0
        if current >= limit:
            return False, 0
        new_count = current + 1
        client.table("rate_limit_usage").upsert(
            {"id": row_id, "client_id": client_id, "bucket": bucket, "day": day, "count": new_count}
        ).execute()
        return True, limit - new_count

    data = _read_local_usage()
    row_id = _row_key(client_id, bucket, day)
    current = data.get(row_id, 0)
    if current >= limit:
        return False, 0
    data[row_id] = current + 1
    _write_local_usage(data)
    return True, limit - data[row_id]


def check_burst_limit(client_id: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
    """True if this request is allowed under the short-window burst cap."""
    now = time.monotonic()
    log = _burst_log[client_id]
    while log and now - log[0] > window_seconds:
        log.popleft()
    if len(log) >= max_requests:
        return False
    log.append(now)
    return True
