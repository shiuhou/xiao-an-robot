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

import hashlib
import json
import os
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


# --- idempotent delivery (§14 L4) -------------------------------------- #
# No unique constraint exists on work_activities (adding one means another
# schema migration on the original repo); dedup is done client-side instead,
# by fingerprinting each note and remembering what's already been delivered.
# A note is uniquely identified by WHEN it happened + WHERE it came from —
# re-running replay over the same frames.jsonl reproduces the exact same
# (timestamp_ms, source, app_name, window_title) for a given segment, so
# this fingerprint is stable across repeats without needing seg/task ids.
def note_fingerprint(note: ActivityNote) -> str:
    raw = f"{note.timestamp_ms}|{note.source}|{note.app_name}|{note.window_title}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class DeliveryLedger:
    """Remembers which notes have already been stored/posted, so re-running
    replay (or retrying a delivery after a network blip) doesn't create
    duplicate work_activities rows. Persisted the same way as the understander's
    task state (§14 L3) — load-if-exists, mutate in memory, save explicitly."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def seen(self, note: ActivityNote) -> bool:
        return note_fingerprint(note) in self._seen

    def mark(self, note: ActivityNote) -> None:
        self._seen.add(note_fingerprint(note))

    def to_dict(self) -> dict:
        return {"seen": sorted(self._seen)}

    def load(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as fh:
            self._seen = set(json.load(fh).get("seen", []))
        return True

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)


def post_note(
    note: ActivityNote,
    base_url: str,
    *,
    path: str = "/api/work-activities",
    timeout: float = 5.0,
    ledger: DeliveryLedger | None = None,
) -> dict:
    """POST one note to the board's ingest endpoint. Enforces the transport red
    line first (sensitive notes are dropped locally, never sent), then the
    idempotency ledger if given (already-delivered notes are skipped, not
    re-sent). Returns a small status dict instead of raising, so a long-running
    sender never crashes on a transient network/HTTP error."""
    if not should_transport(note):
        return {"posted": False, "reason": "sensitive_not_transported"}
    if ledger is not None and ledger.seen(note):
        return {"posted": False, "reason": "already_delivered"}
    payload = json.dumps(note_to_kwargs(note)).encode("utf-8")
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if ledger is not None:
                ledger.mark(note)
            return {"posted": True, "status": resp.status, "response": body}
    except urllib.error.HTTPError as exc:
        return {"posted": False, "reason": "http_error", "status": exc.code}
    except urllib.error.URLError as exc:
        return {"posted": False, "reason": "unreachable", "error": str(exc.reason)}
