"""ActivityNote -> xiao-an-robot work_activities field mapping (衔接层核心).

This module is the SINGLE source of truth for how an understanding-layer
`ActivityNote` becomes a `work_activities` row. It is reused unchanged by:
  * phase 1 — offline validation: calls `insert_work_activity(**note_to_kwargs(n))`
    against a *copy* of xiao_an.db.
  * phase 2 — production: POSTs the same dict to the base station's
    `POST /api/work-activities` ingest endpoint.

Locking the mapping here (not at each call site) guarantees "what we validate
offline is exactly what we ship". Keep it pure and dependency-free.

Mapping decisions (locked with the user):
  * project_id -> None. The schema column is INTEGER; our in-batch string ids
    ("t_001") are only for day-report grouping and are NOT stored. Cross-session
    task identity rides on `project_hint` (the text title), which is also the
    field ContextBuilder surfaces at ask-time.
  * gist -> `note`. Carried in a dedicated `work_activities.note` column added in
    phase 1, so the one-line summary reaches OpenClaw when the user asks for help.
  * source -> "screen" (distinguishes these rows from face/voice sources).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from tracker.understander import ActivityNote

# Transport red line: a note derived from a `sensitive` segment (capture_policy
# "none") NEVER leaves the PC. `full` and `meta_only` notes carry only metadata +
# the one-line gist (raw body was never captured for them), so they may be sent to
# the user's own board over the LAN.
_TRANSPORTABLE = {"full", "meta_only"}


def note_to_kwargs(note: ActivityNote) -> dict:
    """Map one ActivityNote to keyword args for `XiaoAnMemoryStore.insert_work_activity`."""
    return {
        "source": note.source or "screen",
        "app_name": note.app_name,
        "window_title": note.window_title,
        "activity_type": note.activity_type,
        "project_hint": note.project_hint,
        "note": note.gist,
        "confidence": note.confidence,
        "duration_seconds": note.duration_seconds,
        "timestamp_ms": note.timestamp_ms,
        "project_id": None,
    }


def should_transport(note: ActivityNote) -> bool:
    """Red line: only full / meta_only notes may leave the PC; sensitive stays local."""
    return getattr(note, "capture_policy", "full") in _TRANSPORTABLE


def post_note(
    note: ActivityNote,
    base_url: str,
    *,
    path: str = "/api/work-activities",
    timeout: float = 5.0,
) -> dict:
    """POST one note to the board's ingest endpoint. Enforces the transport red
    line first (sensitive notes are dropped locally, never sent). Returns a small
    status dict instead of raising, so a long-running sender never crashes on a
    transient network/HTTP error."""
    if not should_transport(note):
        return {"posted": False, "reason": "sensitive_not_transported"}
    payload = json.dumps(note_to_kwargs(note)).encode("utf-8")
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {"posted": True, "status": resp.status, "response": body}
    except urllib.error.HTTPError as exc:
        return {"posted": False, "reason": "http_error", "status": exc.code}
    except urllib.error.URLError as exc:
        return {"posted": False, "reason": "unreachable", "error": str(exc.reason)}
