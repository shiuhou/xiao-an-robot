"""Offline replay: frames.jsonl -> segments -> activity notes -> day report.

The quality magnifier for the understanding layer. Nothing live, nothing on the
robot — feed a recorded session and watch it become a handful of work_activities
rows plus a report draft. Iterate the prompt, re-run, compare.

  python -u replay.py frames.jsonl                  # offline rule backend (free)
  python -u replay.py frames.jsonl --backend qwen   # Qwen (full-content segments
                                                    # leave the machine)
  python -u replay.py frames.jsonl --backend qwen --store data/xiao_an_local.db
                                                    # also land notes into a local
                                                    # xiao_an.db (no board, no HTTP)

Backend / model / key default from config.json (Config.load); --backend overrides.
--backend qwen honours the red line: im/sensitive segments are associated
locally and never leave the machine (see understander.QwenUnderstander).
"""
from __future__ import annotations

import argparse
import io
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from tracker.config import Config
from tracker.frames import read_frames
from tracker.segmenter import segment_frames
from tracker.understander import ActivityNote, make_understander


def _fmt_dur(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


def _store_notes(notes: list[ActivityNote], db_path: str) -> int:
    """Minimal delivery: land every note into a local xiao_an.db via the bridge.
    No board, no HTTP, no dedup, no transport filtering — see ARCHITECTURE §12 for
    the delivery logic still to add (idempotency / incremental / transport red line)."""
    import os
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from agent.core.memory import XiaoAnMemoryStore
    from tracker.bridge import note_to_kwargs

    store = XiaoAnMemoryStore(db_path)
    for n in notes:
        store.insert_work_activity(**note_to_kwargs(n))
    total = len(store.query_recent_work_activities(limit=100000))
    store.close()
    return total


def _post_notes(notes: list[ActivityNote], url: str) -> tuple[int, int, int]:
    """Minimal HTTP delivery: POST each note to a running board API via the bridge
    (real HTTP; red line enforced — sensitive notes are dropped locally, never sent)."""
    from tracker.bridge import post_note

    posted = skipped = failed = 0
    for n in notes:
        r = post_note(n, url)
        if r.get("posted"):
            posted += 1
        elif r.get("reason") == "sensitive_not_transported":
            skipped += 1
        else:
            failed += 1
            print(f"  [post 失败] {r}")
    return posted, skipped, failed


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay a frame stream into activity notes")
    ap.add_argument("frames", help="path to frames.jsonl")
    ap.add_argument("--backend", choices=["rule", "qwen"],
                    help="override config: rule = offline/free, qwen = cloud")
    ap.add_argument("--store", metavar="DB",
                    help="also land notes into a local xiao_an.db via the bridge "
                         "(no board, no HTTP)")
    ap.add_argument("--post", metavar="URL",
                    help="also POST notes over real HTTP to a running board API "
                         "(e.g. http://127.0.0.1:8787); red line enforced")
    args = ap.parse_args()

    cfg = Config.load()
    backend = args.backend or cfg.understander_backend

    frames = list(read_frames(args.frames))
    segs = segment_frames(frames)
    print(f"{len(frames)} frames -> {len(segs)} segments  (backend={backend})\n")
    if backend == "qwen":
        print("  [!] cloud: full 内容段会离开本机;im/sensitive 段留本地不外发。\n")

    understander = make_understander(
        backend, api_key=cfg.qwen_api_key, model=cfg.qwen_model,
        base_url=cfg.qwen_base_url,
    )

    notes: list[ActivityNote] = []
    print("── activity notes (work_activities rows) ──")
    for seg in segs:
        note = understander.ingest(seg)
        notes.append(note)
        print(f"[{note.project_id}] {note.activity_type:<13} "
              f"{_fmt_dur(note.duration_seconds):>6} {note.app_name:<16} "
              f"conf={note.confidence:.2f}")
        print(f"        {note.gist}")

    # --- day-report draft: group by project ---
    print("\n── 日报草稿 ──")
    by_task: dict[str, list[ActivityNote]] = defaultdict(list)
    for n in notes:
        by_task[n.project_id].append(n)
    order = sorted(by_task, key=lambda p: -sum(n.duration_seconds for n in by_task[p]))
    for pid in order:
        rows = by_task[pid]
        total = sum(n.duration_seconds for n in rows)
        title = rows[0].project_hint
        apps = " / ".join(dict.fromkeys(n.app_name for n in rows))
        print(f"\n● {title}  ({_fmt_dur(total)}, {len(rows)} 段, {apps})")
        for n in rows:
            print(f"    - {n.gist}")

    # --- minimal delivery: land into a local xiao_an.db (no board) ---
    if args.store:
        landed = _store_notes(notes, args.store)
        print(f"\n── 落库 ── {len(notes)} 条 note 已写入 {args.store}"
              f"(库内共 {landed} 行 work_activities)")

    # --- minimal HTTP delivery: POST to a running board API (real HTTP) ---
    if args.post:
        posted, skipped, failed = _post_notes(notes, args.post)
        print(f"\n── POST ── {posted} 条已发到 {args.post}"
              f"({skipped} 条 sensitive 未发,{failed} 条失败)")


if __name__ == "__main__":
    main()
