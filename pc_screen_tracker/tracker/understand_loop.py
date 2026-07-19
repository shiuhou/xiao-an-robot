"""Live understanding loop: frames table -> ActivityNotes -> board ingest.

This is the piece that wires the (previously offline-only) segmenter /
understander / bridge into `track`. A background daemon thread wakes every
`understand_interval_sec`, reads the frames captured since a persisted cursor,
segments them, sends each *closed* segment through the understander (Qwen, with
the built-in rule fallback), and posts the resulting note to the board.

Why a thread, not the sampling loop: a Qwen call blocks 2-5s per segment, so
running it inline would punch multi-second holes in the 5s sampling cadence and
corrupt the active/away stats. The loop owns its own short-lived Store per cycle
(same convention as SummaryPusher).

Crash/idempotency model:
  * the LAST segment of each batch is held back — the window may still be open,
    so it isn't final yet; next cycle re-reads and re-segments it (its fingerprint
    is stable, so it is never double-posted once it does close).
  * the delivery ledger + task state are saved BEFORE the cursor advances, so a
    crash re-runs a cycle rather than skipping notes.
  * on an unreachable board the cursor is left at the first failed segment so the
    batch is retried next cycle; already-delivered segments are not re-read.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from tracker.bridge import DeliveryLedger, post_note
from tracker.config import Config
from tracker.segmenter import segment_frames
from tracker.store import Store
from tracker.understander import make_understander


def _start_of_today_ms() -> int:
    lt = time.localtime()
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return int(midnight * 1000)


class UnderstandLoop:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        state_dir = Path(cfg.db_path).parent
        self._cursor_path = str(state_dir / "understand_cursor.json")
        self._task_state_path = str(state_dir / "task_state.json")
        self._ledger_path = str(state_dir / "delivery_ledger.json")

        self.understander = make_understander(
            cfg.understander_backend,
            api_key=cfg.qwen_api_key,
            model=cfg.qwen_model,
            base_url=cfg.qwen_base_url,
            state_path=self._task_state_path,
        )
        self.ledger = DeliveryLedger()
        self.ledger.load(self._ledger_path)

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.understand_enabled and self.cfg.board_base_url)

    # --- thread lifecycle --------------------------------------------------- #
    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="understand", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def _loop(self) -> None:
        interval = max(30.0, float(self.cfg.understand_interval_sec))
        while not self._stop.wait(interval):
            try:
                stats = self.run_cycle()
                if stats.get("posted") or stats.get("dropped") or stats.get("unreachable"):
                    print(f"[understand] cycle -> {stats}")
            except Exception as exc:  # noqa: BLE001 — a bad cycle must not kill the thread
                print(f"[understand] cycle error: {exc}")

    # --- cursor persistence ------------------------------------------------- #
    def _read_cursor(self, now_ms: int) -> int:
        default = max(_start_of_today_ms(),
                      now_ms - int(self.cfg.understand_interval_sec * 1000))
        if not os.path.exists(self._cursor_path):
            return default
        try:
            with open(self._cursor_path, encoding="utf-8") as fh:
                return int(json.load(fh).get("cursor_ms", default))
        except (ValueError, OSError, json.JSONDecodeError):
            return default

    def _save_cursor(self, cursor_ms: int) -> None:
        with open(self._cursor_path, "w", encoding="utf-8") as fh:
            json.dump({"cursor_ms": int(cursor_ms)}, fh)

    # --- one cycle (synchronously testable) --------------------------------- #
    def run_cycle(self, now_ms: int | None = None) -> dict:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        cursor = self._read_cursor(now_ms)

        store = Store(self.cfg.db_path)
        try:
            frames = store.query_frames(cursor + 1, now_ms)
        finally:
            store.close()

        if not frames:
            self._save_cursor(now_ms)
            return {"frames": 0, "segments": 0, "posted": 0, "skipped": 0}

        segments = segment_frames(frames)
        if len(segments) <= 1:
            # nothing has closed yet (only the still-open tail); leave the cursor
            # where it is so this tail is re-read and re-segmented next cycle.
            return {"frames": len(frames), "segments": len(segments),
                    "posted": 0, "skipped": 0}

        closed, held = segments[:-1], segments[-1]
        posted = skipped = dropped = 0
        first_failed = None
        for seg in closed:
            # (b) skip segments already delivered BEFORE ingesting, so a restart /
            # replay / cursor reset that re-reads delivered frames doesn't pay for
            # a second Qwen call. The probe mirrors bridge.note_fingerprint's fields
            # (timestamp_ms | source | app_name | window_title) for the note this
            # segment will become.
            probe = SimpleNamespace(timestamp_ms=seg.start_ms, source="screen",
                                    app_name=seg.app, window_title=seg.title)
            if self.ledger.seen(probe):
                skipped += 1
                continue
            note = self.understander.ingest(seg)
            result = post_note(note, self.cfg.board_base_url, ledger=self.ledger)
            reason = result.get("reason")
            if result.get("posted"):
                posted += 1
            elif reason in ("already_delivered", "sensitive_not_transported"):
                skipped += 1
            elif reason == "unreachable":
                first_failed = seg
                break
            else:
                # (a) http_error etc.: a board 4xx (e.g. missing_app_name for an
                # empty-app segment) is a permanently-undeliverable note — dropping
                # it and advancing is correct (retrying a 4xx would poison the
                # cursor), but surface it instead of failing silently.
                dropped += 1
                print(f"[understand] dropped seg ts={seg.start_ms} "
                      f"app={seg.app!r}: {result}")

        # persist ledger + task state BEFORE moving the cursor (crash-safe).
        self.understander.state.save(self._task_state_path)
        self.ledger.save(self._ledger_path)

        if first_failed is not None:
            # retry this batch from the first undelivered segment next cycle.
            self._save_cursor(first_failed.start_ms - 1)
        else:
            # advance up to (not into) the still-open tail segment.
            self._save_cursor(held.start_ms - 1)

        return {"frames": len(frames), "segments": len(segments),
                "posted": posted, "skipped": skipped, "dropped": dropped,
                "unreachable": first_failed is not None}
