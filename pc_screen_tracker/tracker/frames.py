"""Frame record schema — the replayable unit of the frame stream.

One FrameRecord = one sampling tick from the extraction layer. It is the shared
contract between the *writer* (probe_trace / collector) and the *readers*
(segmenter, replay). Persisted as JSONL (one JSON object per line, UTF-8, Chinese
kept readable) so a real session can be replayed offline into the understanding
layer without any live capture.

Keep this schema stable; the segmenter and replay depend on the field names.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Iterator, TextIO

SCHEMA_VERSION = 1


@dataclass
class FrameRecord:
    ts_ms: int                       # wall-clock epoch ms (replay ordering key)
    frame: int                       # 1-based index within the session
    hwnd: int = 0                    # foreground window handle (stable id for dwell)
    app: str = ""                    # process image name, e.g. "chrome.exe"
    title: str = ""                  # window title
    kind: str = ""                   # surface kind: browser_page/chat/im/...
    capture_policy: str = "full"     # full | meta_only | none
    url: str = ""                    # browser url/domain (browser surfaces)
    headline: str = ""               # article title / chat contact / doc name
    content: list[str] = field(default_factory=list)  # de-noised body excerpt
    mode: str = ""                   # reading | writing | idle | ·
    keys: int = 0                    # per-tick counts (never key identities)
    clicks: int = 0
    scrolls: int = 0
    mouse_px: float = 0.0
    dwell_s: float = 0.0             # continuous dwell on this window so far
    idle_s: float = 0.0             # seconds since last user input
    # lightweight extraction diagnostics (optional, for quality debugging)
    uia_nodes: int = 0
    uia_docs: int = 0
    elapsed_ms: int = 0
    truncated: bool = False

    def content_chars(self) -> int:
        return sum(len(t) for t in self.content)


class FrameWriter:
    """Append-only JSONL writer. First line is a header with schema version."""

    def __init__(self, path: str):
        self.path = path
        self._fp: TextIO | None = None
        self._count = 0

    def __enter__(self) -> "FrameWriter":
        self._fp = open(self.path, "w", encoding="utf-8", newline="\n")
        self._fp.write(json.dumps(
            {"_header": True, "schema": SCHEMA_VERSION}, ensure_ascii=False) + "\n")
        self._fp.flush()
        return self

    def write(self, rec: FrameRecord) -> None:
        assert self._fp is not None
        self._fp.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
        self._fp.flush()  # crash-safe: never lose captured frames
        self._count += 1

    @property
    def count(self) -> int:
        return self._count

    def __exit__(self, *exc) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None


def read_frames(path: str) -> Iterator[FrameRecord]:
    """Yield FrameRecords from a JSONL file, skipping the header line."""
    with open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("_header"):
                continue
            known = {k: obj[k] for k in obj if k in FrameRecord.__annotations__}
            yield FrameRecord(**known)
