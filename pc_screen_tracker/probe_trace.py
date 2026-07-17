"""Live trace probe: print all seven signal types per frame.

Run it, then over ~60s do a natural workflow:
  1. type some code in VS Code
  2. switch to a browser, type a question in the search box
  3. open two result pages and read them
Watch what each frame captures. Ctrl+C to stop.

By default nothing is stored; this only prints to the console. Pass
`--out frames.jsonl` to ALSO record a replayable frame stream (JSONL) for the
understanding layer (segmenter/replay). `--interval N` changes the sample gap.

  python -u probe_trace.py --out frames.jsonl
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from tracker.classify import Classifier
from tracker.frames import FrameRecord, FrameWriter
from tracker.input_meter import InputMeter
from tracker.surface import BROWSER_PROCS as BROWSERS, detect
from tracker.ui_extract import extract
from tracker.window import foreground_window, idle_seconds

INTERVAL = 2.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Live frame trace probe")
    parser.add_argument("--out", metavar="PATH",
                        help="also record a replayable JSONL frame stream")
    parser.add_argument("--interval", type=float, default=INTERVAL,
                        help=f"seconds between samples (default {INTERVAL})")
    args = parser.parse_args()
    interval = args.interval

    meter = InputMeter()
    meter.start()
    classifier = Classifier()

    last_hwnd = None
    dwell_start = time.monotonic()
    frame = 0
    writer_cm = FrameWriter(args.out) if args.out else contextlib.nullcontext()
    if args.out:
        print(f"[trace] recording frames -> {args.out}")
    print(f"[trace] sampling every {interval}s — do your VS Code -> browser workflow now. Ctrl+C to stop.\n")
    try:
        writer = writer_cm.__enter__()
        while True:
            t0 = time.monotonic()
            frame += 1
            win = foreground_window()
            delta = meter.snapshot()
            idle = idle_seconds()

            # (4) dwell time on current foreground window
            if win and win.hwnd != last_hwnd:
                dwell_start = time.monotonic()
                last_hwnd = win.hwnd
            dwell = time.monotonic() - dwell_start

            app = win.app if win else "-"
            title = win.title if win else "-"

            # surface + capture policy decide whether content is read at all
            category = classifier.classify(app, title)
            surf = detect(app, title, category=category)

            # (2)(3) content + url via UIA — skipped for meta_only/none surfaces
            snap = None
            if win and surf.capture_policy == "full":
                snap = extract(win.hwnd, app, kind="auto",
                               max_nodes=400, time_budget_sec=1.5)
            url = snap.url if snap else ""
            texts = snap.texts if snap else []
            # browser path resolves page-vs-chat itself; otherwise surface wins
            kind = (snap.kind if snap and snap.kind.startswith("browser") else surf.kind)
            headline = (snap.headline if snap and snap.headline else title)

            # read/write inference from signals
            if delta.keys >= 3:
                mode = "WRITING"
            elif delta.scrolls > 0 or delta.mouse_px > 200:
                mode = "READING"
            elif idle > 5:
                mode = "idle"
            else:
                mode = "·"

            is_browser = app.lower() in BROWSERS
            print(f"── frame {frame}  {time.strftime('%H:%M:%S')}  [{mode}]"
                  f"  kind={kind}  policy={surf.capture_policy} ─────")
            print(f"  ①app/title : {app}  |  {title[:56]}")
            if is_browser:
                print(f"  ③url       : {url or '(not read)'}")
            if headline and headline != title:
                print(f"  ★headline  : {headline[:56]}")
            print(f"  ④dwell     : {dwell:4.0f}s   idle {idle:.0f}s")
            print(f"  ⑤⑥input   : keys={delta.keys:>3}  clicks={delta.clicks:>2}"
                  f"  scroll={delta.scrolls:>2}  mouse={delta.mouse_px:>5.0f}px")
            if surf.capture_policy == "meta_only":
                print(f"  ②content   : (skipped — meta_only，正文未读取)")
            elif surf.capture_policy == "none":
                print(f"  ②content   : (skipped — sensitive)")
            else:
                n_chars = sum(len(t) for t in texts)
                print(f"  ②content   ({n_chars} chars / {len(texts)} 段):")
                for t in texts:
                    print(f"      {t[:120]}")
                if not texts:
                    print("      (empty)")
                print(f"     (uia nodes={snap.node_count if snap else 0}"
                      f" docs={snap.doc_count if snap else 0}"
                      f" {snap.elapsed_ms if snap else 0}ms"
                      f"{' TRUNC' if snap and snap.truncated else ''})")

            if args.out:
                writer.write(FrameRecord(
                    ts_ms=int(time.time() * 1000), frame=frame,
                    hwnd=(win.hwnd if win else 0), app=app, title=title,
                    kind=kind, capture_policy=surf.capture_policy,
                    url=url, headline=headline,
                    content=list(texts),
                    mode={"WRITING": "writing", "READING": "reading",
                          "idle": "idle"}.get(mode, "active"),
                    keys=delta.keys, clicks=delta.clicks, scrolls=delta.scrolls,
                    mouse_px=round(delta.mouse_px, 1),
                    dwell_s=round(dwell, 1), idle_s=round(idle, 1),
                    uia_nodes=(snap.node_count if snap else 0),
                    uia_docs=(snap.doc_count if snap else 0),
                    elapsed_ms=(snap.elapsed_ms if snap else 0),
                    truncated=bool(snap and snap.truncated),
                ))

            sleep = interval - (time.monotonic() - t0)
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        pass
    finally:
        meter.stop()
        with contextlib.suppress(Exception):
            writer_cm.__exit__(None, None, None)
        n = writer_cm.count if args.out else 0
        if args.out:
            print(f"\n[trace] stopped. wrote {n} frames -> {args.out}")
        else:
            print("\n[trace] stopped.")


if __name__ == "__main__":
    main()
