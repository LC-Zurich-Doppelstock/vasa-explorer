"""
In-memory conversation session store.

Each session holds a message list and a last-active timestamp.
Sessions are cleaned up after SESSION_TTL seconds of inactivity.
"""

import time
import uuid

from config import SESSION_TTL

sessions: dict[str, dict] = {}


def cleanup_sessions():
    """Remove sessions older than SESSION_TTL."""
    now = time.time()
    expired = [
        sid for sid, s in sessions.items() if now - s["last_active"] > SESSION_TTL
    ]
    for sid in expired:
        del sessions[sid]


def get_or_create_session(session_id: str | None) -> tuple[str, list]:
    """Return (session_id, messages) for the given or a new session."""
    cleanup_sessions()
    if session_id and session_id in sessions:
        sessions[session_id]["last_active"] = time.time()
        return session_id, sessions[session_id]["messages"]
    sid = session_id or str(uuid.uuid4())
    sessions[sid] = {"messages": [], "last_active": time.time()}
    return sid, sessions[sid]["messages"]
