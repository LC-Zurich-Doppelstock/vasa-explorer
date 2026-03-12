"""
Application configuration — environment variables, constants, API key resolution.
"""

import os

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Executor connection
# ---------------------------------------------------------------------------
EXECUTOR_URL = os.environ.get("EXECUTOR_URL", "http://executor:9000")

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
MAX_RETRIES = 2
SESSION_TTL = 1800  # 30 minutes

# ---------------------------------------------------------------------------
# Server-side API keys (optional).  When present the frontend can use the
# app without the user having to supply their own key.
# ---------------------------------------------------------------------------
SERVER_KEYS: dict[str, str] = {}
for _prov, _env in [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")]:
    _val = os.environ.get(_env, "").strip()
    if _val:
        SERVER_KEYS[_prov] = _val

SERVER_KEY_SENTINEL = "__server__"

# ---------------------------------------------------------------------------
# Default model per provider
# ---------------------------------------------------------------------------
PROVIDER_MODEL_DEFAULTS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
}
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "").strip()


def resolve_api_key(provider_name: str, request_key: str) -> str:
    """Return the actual API key to use.

    If the request carries the sentinel (or is empty) and a server key exists
    for this provider, use the server key.  Otherwise use whatever the request
    sent.  Raises HTTPException if nothing is available.
    """
    if request_key and request_key != SERVER_KEY_SENTINEL:
        return request_key
    server_key = SERVER_KEYS.get(provider_name)
    if server_key:
        return server_key
    raise HTTPException(
        status_code=400,
        detail="API key is required. Please configure it in Settings.",
    )
