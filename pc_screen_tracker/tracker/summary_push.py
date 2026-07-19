"""Periodic usage-summary push to the board (语音"汇总屏幕使用"场景的数据通道).

The board never queries the PC. Instead, while `run.py track` is running, the
PC periodically compresses today's `report.build_report` output into a small
JSON payload and POSTs it to the board's `POST /api/screen-usage-summary`
endpoint. The board caches the latest payload; the voice-triggered screen
report is built from that cache.

Transport mirrors `bridge.post_note`: stdlib urllib only, returns a status
dict instead of raising, so the tracker loop never crashes on network errors.

Privacy: the payload carries only aggregates already allowed off-machine at
the configured privacy level (app names, categories, browser domains,
durations, input totals) — never titles, urls or content.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .report import Report, build_report
from .store import Store

TOP_APPS = 10
TOP_DOMAINS = 8


def _start_of_today_ms() -> int:
    lt = time.localtime()
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return int(midnight * 1000)


def summary_payload(rep: Report) -> dict:
    """Compress a Report into the JSON payload sent to the board."""
    switches = sum(1 for s in rep.timeline if s["seconds"] >= 30)
    longest = max((s["seconds"] for s in rep.timeline), default=0.0)
    return {
        "source": "screen",
        "generated_at_ms": int(time.time() * 1000),
        "span_start_ms": rep.span_start_ms,
        "span_end_ms": rep.span_end_ms,
        "active_seconds": round(rep.active_seconds),
        "away_seconds": round(rep.away_seconds),
        "total_keys": rep.total_keys,
        "total_clicks": rep.total_clicks,
        "total_scrolls": rep.total_scrolls,
        "session_count": switches,
        "longest_session_seconds": round(longest),
        "by_app": [
            {"app": a, "seconds": round(b.seconds), "keys": b.keys}
            for a, b in sorted(rep.by_app.items(), key=lambda kv: -kv[1].seconds)[:TOP_APPS]
        ],
        "by_category": [
            {"category": c, "seconds": round(b.seconds)}
            for c, b in sorted(rep.by_category.items(), key=lambda kv: -kv[1].seconds)
        ],
        "by_domain": [
            {"domain": d, "seconds": round(s)}
            for d, s in sorted(rep.by_domain.items(), key=lambda kv: -kv[1])[:TOP_DOMAINS]
        ],
    }


def post_summary(payload: dict, base_url: str, *,
                 path: str = "/api/screen-usage-summary",
                 timeout: float = 5.0) -> dict:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"posted": True, "status": resp.status}
    except urllib.error.HTTPError as exc:
        return {"posted": False, "reason": "http_error", "status": exc.code}
    except urllib.error.URLError as exc:
        return {"posted": False, "reason": "unreachable", "error": str(exc.reason)}


class SummaryPusher:
    """Called from the collector loop each tick; pushes at most every
    `interval_s` seconds. Disabled when `base_url` is empty."""

    def __init__(self, db_path: str, base_url: str, interval_s: float = 1800.0):
        self.db_path = db_path
        self.base_url = base_url
        self.interval_s = interval_s
        self._next_t = time.monotonic()  # first push as soon as tracking starts

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def maybe_push(self) -> dict | None:
        if not self.enabled or time.monotonic() < self._next_t:
            return None
        self._next_t = time.monotonic() + self.interval_s
        # own short-lived connection: the collector's Store is not shared
        store = Store(self.db_path)
        try:
            rep = build_report(store, _start_of_today_ms())
        finally:
            store.close()
        return post_summary(summary_payload(rep), self.base_url)
