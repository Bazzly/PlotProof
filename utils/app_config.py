"""
Runtime-editable app configuration - currently just the Anthropic API key.

Why this exists: this repo is public, so ANTHROPIC_API_KEY can't live in
committed source, and rotating an env-var-based key normally means editing
Streamlit Cloud's Secrets panel and waiting for a redeploy. This module lets
the key be viewed (masked) and rotated from the admin portal
(pages/admin_review.py) instead, taking effect immediately for the running
process - no redeploy, no code/secrets-panel access needed for routine
rotation.

Resolution order: a key set via the admin portal always wins over the
ANTHROPIC_API_KEY environment variable, so a compromised/leaked key (e.g.
accidentally pasted somewhere public) can be overridden here without
touching deployment config at all.

Storage mirrors the rest of the app: local JSON by default, a Supabase
table once SUPABASE_URL/SUPABASE_KEY are configured (create the table
first - schema below). Either way this holds a live secret, so the local
file is gitignored and the Supabase table should have restrictive RLS.

    create table app_config (
        key text primary key,
        value text
    );
"""

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(__file__).resolve().parent.parent / "data" / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "app_config.json"

_SUPABASE_URL = os.environ.get("SUPABASE_URL")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

ANTHROPIC_API_KEY_SETTING = "anthropic_api_key"


def _storage_backend() -> str:
    return "supabase" if (_SUPABASE_URL and _SUPABASE_KEY) else "local"


def _read_local() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def get_setting(key: str) -> Optional[str]:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        response = client.table("app_config").select("value").eq("key", key).execute()
        if response.data:
            return response.data[0]["value"] or None
        return None

    return _read_local().get(key) or None


def set_setting(key: str, value: str) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("app_config").upsert({"key": key, "value": value}).execute()
        return

    data = _read_local()
    data[key] = value
    # Re-asserted here, not just at module import - a long-running process
    # (Streamlit doesn't reload utils/ modules between reruns) would
    # otherwise keep failing to write once this directory's been deleted
    # out from under it, with no way to recover short of a process restart.
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def clear_setting(key: str) -> None:
    if _storage_backend() == "supabase":
        from supabase import create_client

        client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        client.table("app_config").delete().eq("key", key).execute()
        return

    data = _read_local()
    data.pop(key, None)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def get_anthropic_api_key() -> Optional[str]:
    """An admin-set key (via the admin portal) always wins over the
    environment variable, so a rotated/revoked key doesn't require
    touching deployment config at all."""
    return get_setting(ANTHROPIC_API_KEY_SETTING) or os.environ.get("ANTHROPIC_API_KEY") or None


def set_anthropic_api_key(value: str) -> None:
    set_setting(ANTHROPIC_API_KEY_SETTING, value.strip())


def clear_anthropic_api_key() -> None:
    """Removes the admin-set override, falling back to ANTHROPIC_API_KEY
    from the environment (if any)."""
    clear_setting(ANTHROPIC_API_KEY_SETTING)


def mask_key(value: Optional[str]) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:7]}...{value[-4:]}"
