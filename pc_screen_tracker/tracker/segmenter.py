"""Frame stream -> atomic segments (pure state machine, zero LLM).

An *atomic segment* is one continuous stretch of the user sitting on the same
window/page. Boundaries are drawn on:
  * app switch, or a material change of page/document identity
  * an idle/away gap (idle_s >= idle_break_s)
  * a hard cap (max_seg_s) so a long unbroken session still gets chunked

Then a *minimum-duration gate* absorbs sub-`min_seg_s` glances into their
neighbour so flipping A-B-A-B doesn't spray micro-segments (this is what keeps
the per-segment LLM cadence in §6.5 from thrashing). Finally adjacent segments
that ended up with the same identity are coalesced.

This layer is deterministic and offline-testable: feed it a frames.jsonl and
eyeball the segments — no capture, no network, no cost.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Iterable

from tracker.frames import FrameRecord, read_frames

# tuning knobs (seconds)
IDLE_BREAK_S = 60.0     # gap >= this ends a segment (user stepped away)
MAX_SEG_S = 600.0       # 10-min hard cap even without an identity change
MIN_SEG_S = 8.0         # shorter than this = incidental glance, absorbed

_BROWSER = {"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe"}
# notification-count prefix zhihu/webmail put in titles: "(54 封私信 / 80 条消息) "
_NOTIF_PREFIX = re.compile(r"^\(\d+[^)]*(?:私信|消息|未读)[^)]*\)\s*")
_BROWSER_SUFFIX = re.compile(
    r"\s*[-–]\s*(?:Google Chrome|Microsoft.?\s*Edge|Brave|Vivaldi)\s*$")


def _norm_title(title: str) -> str:
    t = _NOTIF_PREFIX.sub("", title or "")
    t = _BROWSER_SUFFIX.sub("", t)
    return " ".join(t.split()).strip()


def _identity(f: FrameRecord) -> tuple[str, str]:
    """Stable key for 'same window/page'. Notification-count churn in the title
    must NOT split a segment; a different article/page MUST."""
    nt = _norm_title(f.title)
    if f.app.lower() in _BROWSER or f.kind.startswith("browser"):
        return (f.app.lower(), f"{f.url}|{nt}")  # domain + page distinguishes articles
    return (f.app.lower(), nt)


def _is_away(f: FrameRecord, idle_break_s: float) -> bool:
    return f.mode == "idle" or f.idle_s >= idle_break_s


# --- content-drift detection (L2 optimization, ARCHITECTURE §14) ---
# Same (app, url|title) identity can still cover a genuinely different topic
# (SPA / infinite-scroll page whose URL never changes). Catch that by comparing
# each new full-content frame against the run's ANCHOR content (its first
# non-empty capture) rather than just the identity key.
_TOKEN_RE = re.compile(r"[一-鿿]{2,}|[A-Za-z0-9]{3,}")
DRIFT_MIN_CHARS = 40        # too little text to judge drift reliably -> skip
DRIFT_SIMILARITY_FLOOR = 0.12  # Jaccard below this = treat as a topic change


def _tokens(content: list[str]) -> set[str]:
    return set(_TOKEN_RE.findall(" ".join(content)))


def _content_drifted(anchor: list[str], candidate: list[str]) -> bool:
    if not anchor or not candidate:
        return False
    if sum(len(c) for c in anchor) < DRIFT_MIN_CHARS or sum(len(c) for c in candidate) < DRIFT_MIN_CHARS:
        return False
    a, b = _tokens(anchor), _tokens(candidate)
    if not a or not b:
        return False
    jaccard = len(a & b) / len(a | b)
    return jaccard < DRIFT_SIMILARITY_FLOOR


ANCHOR_MIN_RICHNESS = 0.5   # anchor candidate must have >= this fraction of the
                            # run's richest full-content frame's char count


def _richest_full_content_index(frames: list[FrameRecord]) -> int | None:
    candidates = [
        i for i, f in enumerate(frames)
        if f.capture_policy == "full" and f.content
    ]
    if not candidates:
        return None
    # FIRST candidate good enough to anchor on (chronological — scanning
    # stays forward-only and correct), skipping a shallow/failed extraction
    # (e.g. UIA only caught the tab-bar title + a notification toast, not
    # the real editor body — a real case found on real data) that would
    # otherwise anchor the topic judgment and spuriously "drift" once real
    # content shows up. Picking the single richest frame instead (rather
    # than "good enough") would break chronological ordering when two
    # genuinely different topics happen to have similar lengths.
    richest_chars = max(frames[i].content_chars() for i in candidates)
    floor = richest_chars * ANCHOR_MIN_RICHNESS
    return next(i for i in candidates if frames[i].content_chars() >= floor)


def _split_one_run(frames: list[FrameRecord], hard: bool
                    ) -> list[tuple[list[FrameRecord], bool]]:
    anchor_idx = _richest_full_content_index(frames)
    if anchor_idx is None:
        return [(frames, hard)]
    anchor = frames[anchor_idx].content

    streak_start = None   # index of the first (unconfirmed) divergent frame
    for i in range(anchor_idx + 1, len(frames)):
        f = frames[i]
        if f.capture_policy != "full" or not f.content:
            continue
        if _content_drifted(anchor, f.content):
            if streak_start is None:
                streak_start = i
                continue
            # second divergent full-content frame confirms a sustained topic
            # change -> split here (recurse: the tail may drift again later)
            head, tail = frames[:streak_start], frames[streak_start:]
            return [(head, hard)] + _split_one_run(tail, True)
        else:
            streak_start = None   # back on-topic: the earlier blip wasn't real drift
    return [(frames, hard)]


def _split_drifted_runs(runs: list[tuple[list[FrameRecord], bool]]
                         ) -> list[tuple[list[FrameRecord], bool]]:
    out: list[tuple[list[FrameRecord], bool]] = []
    for frames, hard in runs:
        out.extend(_split_one_run(frames, hard))
    return out


def _mode_of(keys: int, scrolls: int, mouse_px: float) -> str:
    if keys >= 5:
        return "writing"
    if scrolls > 0 or mouse_px >= 400:
        return "reading"
    return "active"


@dataclass
class Segment:
    seg_id: int
    start_ms: int
    end_ms: int
    app: str = ""
    title: str = ""
    url: str = ""
    kind: str = ""
    capture_policy: str = "full"
    headline: str = ""
    content: list[str] = field(default_factory=list)
    keys: int = 0
    clicks: int = 0
    scrolls: int = 0
    mouse_px: float = 0.0
    frame_count: int = 0
    _key: tuple[str, str] = ("", "")
    _hard_before: bool = False   # preceded by an idle/cap split — never coalesce across

    @property
    def duration_s(self) -> float:
        return max(0.0, (self.end_ms - self.start_ms) / 1000.0)

    @property
    def mode(self) -> str:
        return _mode_of(self.keys, self.scrolls, self.mouse_px)

    def content_chars(self) -> int:
        return sum(len(t) for t in self.content)

    def to_dict(self) -> dict:
        return {
            "seg_id": self.seg_id,
            "start_ms": self.start_ms, "end_ms": self.end_ms,
            "duration_s": round(self.duration_s, 1),
            "app": self.app, "title": self.title, "url": self.url,
            "kind": self.kind, "capture_policy": self.capture_policy,
            "headline": self.headline, "content": self.content,
            "keys": self.keys, "clicks": self.clicks, "scrolls": self.scrolls,
            "mouse_px": round(self.mouse_px, 1), "mode": self.mode,
            "frame_count": self.frame_count,
        }


def _seg_from_run(seg_id: int, run: list[FrameRecord], tail_ms: int,
                  hard_before: bool) -> Segment:
    first, last = run[0], run[-1]
    richest = max(run, key=lambda f: f.content_chars())
    end_ms = last.ts_ms + tail_ms
    seg = Segment(
        seg_id=seg_id, start_ms=first.ts_ms, end_ms=end_ms,
        app=first.app, title=_norm_title(richest.title) or richest.title,
        url=richest.url, kind=richest.kind, capture_policy=first.capture_policy,
        headline=richest.headline, content=list(richest.content),
        keys=sum(f.keys for f in run), clicks=sum(f.clicks for f in run),
        scrolls=sum(f.scrolls for f in run),
        mouse_px=sum(f.mouse_px for f in run), frame_count=len(run),
        _key=_identity(first), _hard_before=hard_before,
    )
    return seg


def _absorb(dst: Segment, src: Segment, *, merge_content: bool = False) -> None:
    """Fold src's time+counts into dst. Descriptive fields (title/content/url/
    kind) stay dst's own — overwriting them from a *different* window is how a
    chrome segment ended up wearing a terminal's title. Only same-identity
    coalescing (pass 3) sets merge_content, to keep the richer body."""
    dst.start_ms = min(dst.start_ms, src.start_ms)
    dst.end_ms = max(dst.end_ms, src.end_ms)
    dst.keys += src.keys
    dst.clicks += src.clicks
    dst.scrolls += src.scrolls
    dst.mouse_px += src.mouse_px
    dst.frame_count += src.frame_count
    if merge_content and src.content_chars() > dst.content_chars():
        dst.content = src.content
        dst.title, dst.url, dst.headline = src.title, src.url, src.headline
        dst.kind = src.kind


def segment_frames(frames: Iterable[FrameRecord], *,
                   idle_break_s: float = IDLE_BREAK_S,
                   max_seg_s: float = MAX_SEG_S,
                   min_seg_s: float = MIN_SEG_S) -> list[Segment]:
    frames = list(frames)
    if not frames:
        return []
    # nominal tail per frame = median inter-frame gap (so last frame has weight)
    gaps = [frames[i + 1].ts_ms - frames[i].ts_ms for i in range(len(frames) - 1)]
    tail_ms = int(sorted(gaps)[len(gaps) // 2]) if gaps else 2000

    # --- pass 1: runs by identity / idle / cap; tag idle & cap as HARD breaks ---
    runs: list[tuple[list[FrameRecord], bool]] = []   # (frames, hard_before)
    cur: list[FrameRecord] = []
    cur_hard = False
    pending_hard = False        # an idle gap makes whatever starts next hard-broken
    for f in frames:
        if _is_away(f, idle_break_s):
            if cur:
                runs.append((cur, cur_hard)); cur = []
            pending_hard = True
            continue
        if not cur:
            cur = [f]; cur_hard = pending_hard; pending_hard = False; continue
        same = _identity(f) == _identity(cur[0])
        over_cap = (f.ts_ms - cur[0].ts_ms) / 1000.0 >= max_seg_s
        if same and not over_cap:
            cur.append(f)
        else:
            runs.append((cur, cur_hard))
            cur = [f]
            cur_hard = pending_hard or over_cap   # cap split is a hard boundary
            pending_hard = False
    if cur:
        runs.append((cur, cur_hard))

    # --- pass 1b: content-drift split (L2 optimization, ARCHITECTURE §14).
    #     Same identity can still cover a genuinely different topic (SPA /
    #     infinite-scroll page whose URL never changes). Requires TWO
    #     confirming divergent full-content frames (not just one) so a
    #     single noisy/shallow extraction (L1 quality flicker — e.g. one
    #     frame only caught tab-bar chrome text) can't spuriously fragment
    #     a segment; a real topic change is sustained across samples. ---
    runs = _split_drifted_runs(runs)

    segs = [_seg_from_run(i + 1, r, tail_ms, hard)
            for i, (r, hard) in enumerate(runs)]

    # --- pass 2: fold away *transient* glances (Alt-Tab task-switcher, a flash
    #     of an empty page). Only a sub-threshold, full-policy, EMPTY-content
    #     segment is noise — a short segment that DID capture body text (a quick
    #     zhihu search) is a real activity and is kept; so are im/sensitive
    #     segments (empty by policy, not by being transient). Time-only fold, so
    #     no descriptive field bleeds across windows. ---
    out: list[Segment] = []
    for s in segs:
        transient = (s.duration_s < min_seg_s and s.capture_policy == "full"
                     and s.content_chars() == 0)
        if transient and out:
            _absorb(out[-1], s)   # fold its seconds into the prior segment
        else:
            out.append(s)

    # --- pass 3: coalesce adjacent same-identity segments (e.g. a page split by
    #     a folded glance) — but NEVER across a hard (idle/cap) boundary ---
    coalesced: list[Segment] = []
    for s in out:
        if coalesced and coalesced[-1]._key == s._key and not s._hard_before:
            _absorb(coalesced[-1], s, merge_content=True)
        else:
            coalesced.append(s)

    for i, s in enumerate(coalesced):  # renumber after merges
        s.seg_id = i + 1
    return coalesced


def _fmt(s: Segment) -> str:
    body = " ⏎ ".join(s.content[:3])
    if len(body) > 90:
        body = body[:90] + "…"
    head = f"[{s.seg_id}] {s.duration_s:5.0f}s  {s.app:<18} {s.kind:<12} {s.mode:<8}"
    line2 = f"      title: {s.title[:60]}"
    line3 = f"      url:   {s.url}" if s.url else ""
    line4 = (f"      keys={s.keys} clk={s.clicks} scr={s.scrolls} "
             f"frames={s.frame_count}")
    if s.capture_policy != "full":
        line5 = f"      content: (—, policy={s.capture_policy})"
    else:
        line5 = f"      content({s.content_chars()}c): {body or '(empty)'}"
    return "\n".join(x for x in (head, line2, line3, line4, line5) if x)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("usage: python -m tracker.segmenter <frames.jsonl>")
        return
    frames = list(read_frames(sys.argv[1]))
    segs = segment_frames(frames)
    print(f"{len(frames)} frames -> {len(segs)} atomic segments\n")
    for s in segs:
        print(_fmt(s))
        print()


if __name__ == "__main__":
    main()
