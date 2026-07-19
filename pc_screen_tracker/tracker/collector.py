"""The sampling loop: snapshot foreground + input activity every interval."""
from __future__ import annotations

import re
import signal
import time

from .classify import Classifier
from .config import Config
from .content import browser_url
from .frames import FrameRecord
from .input_meter import InputMeter
from .store import Store
from .summary_push import SummaryPusher
from .surface import detect
from .ui_extract import extract
from .understand_loop import UnderstandLoop
from .window import foreground_window, idle_seconds


def _frame_mode(keys: int, scrolls: int, mouse_px: float, idle: float) -> str:
    """Coarse read/write signal for a frame (mirrors probe_trace)."""
    if keys >= 3:
        return "writing"
    if scrolls > 0 or mouse_px > 200:
        return "reading"
    if idle > 5:
        return "idle"
    return "active"


class Collector:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.store = Store(cfg.db_path)
        self.classifier = Classifier()
        self.meter = InputMeter()
        self._blocklist = [re.compile(p) for p in cfg.blocklist_apps]
        self._running = False
        self.pusher = SummaryPusher(cfg.db_path, cfg.board_base_url,
                                    cfg.summary_push_interval_sec)
        # understanding layer (off unless understand_enabled + board configured)
        self.understand = UnderstandLoop(cfg)
        self._frame_idx = 0
        self._last_hwnd = None
        self._dwell_start = time.monotonic()

    def _blocked(self, app: str, title: str) -> bool:
        hay = f"{app} | {title}"
        return any(p.search(hay) for p in self._blocklist)

    def _capture(self) -> dict:
        level = self.cfg.privacy_level
        idle = idle_seconds()
        win = foreground_window()
        app = win.app if win else None
        title = win.title if win else None
        domain = url = None

        blocked = bool(app and self._blocked(app or "", title or ""))

        # Layer-2 browser url/domain (L1+ gets domain, L2 gets full url)
        if win and not blocked and level in ("L1", "L2") \
                and app and app.lower() in [b.lower() for b in self.cfg.browser_procs]:
            full, dom = browser_url(win.hwnd)
            domain = dom
            if level == "L2":
                url = full

        # privacy redaction of stored fields
        if level == "L0" or blocked:
            title = None
            domain = None
            url = None

        category = self.classifier.classify(app, title, domain)
        delta = self.meter.snapshot()
        active = 1 if idle < self.cfg.idle_threshold_sec else 0

        row = {
            "ts_ms": int(time.time() * 1000),
            "app": app,
            "title": title,
            "category": "away" if not active else category,
            "domain": domain,
            "url": url,
            "idle_sec": round(idle, 1),
            "active": active,
            "keys": delta.keys,
            "clicks": delta.clicks,
            "scrolls": delta.scrolls,
            "mouse_px": round(delta.mouse_px, 1),
            "interval_s": self.cfg.sample_interval_sec,
        }
        frame = self._build_frame(row, win, app, title, domain, url,
                                  category, delta, idle, blocked)
        return row, frame

    def _build_frame(self, row, win, app, title, domain, url, category,
                     delta, idle, blocked) -> "FrameRecord | None":
        """Build the understanding-layer frame for this tick (or None when the
        layer is off). Body text is read via UIA only for `full` surfaces that
        aren't blocklisted; sensitive/IM surfaces and blocklist apps are never
        read (red line), independent of privacy tier."""
        if not self.cfg.understand_enabled:
            return None

        surf = detect(app or "", title or "", category=category)
        policy = "none" if blocked else surf.capture_policy

        snap = None
        if win and policy == "full":
            try:
                snap = extract(win.hwnd, app or "", kind="auto",
                               max_nodes=400, time_budget_sec=1.5)
            except Exception:  # noqa: BLE001 — extraction is best-effort
                snap = None

        self._frame_idx += 1
        hwnd = win.hwnd if win else 0
        if hwnd != self._last_hwnd:
            self._dwell_start = time.monotonic()
            self._last_hwnd = hwnd
        dwell = time.monotonic() - self._dwell_start

        if blocked:
            f_title = ""
            headline = ""
            f_url = ""
            texts: list[str] = []
        else:
            f_title = title or ""
            texts = list(snap.texts) if snap else []
            f_url = (snap.url if snap else "") or (url or domain or "")
            headline = (snap.headline if snap and snap.headline else (title or ""))
        kind = (snap.kind if snap and snap.kind.startswith("browser") else surf.kind)

        return FrameRecord(
            ts_ms=row["ts_ms"], frame=self._frame_idx, hwnd=hwnd,
            app=app or "", title=f_title, kind=kind, capture_policy=policy,
            url=f_url, headline=headline, content=texts,
            mode=_frame_mode(delta.keys, delta.scrolls, delta.mouse_px, idle),
            keys=delta.keys, clicks=delta.clicks, scrolls=delta.scrolls,
            mouse_px=round(delta.mouse_px, 1),
            dwell_s=round(dwell, 1), idle_s=round(idle, 1),
            uia_nodes=(snap.node_count if snap else 0),
            uia_docs=(snap.doc_count if snap else 0),
            elapsed_ms=(snap.elapsed_ms if snap else 0),
            truncated=bool(snap and snap.truncated),
        )

    def run(self) -> None:
        self._running = True
        self.meter.start()

        def _stop(*_a):
            self._running = False
        signal.signal(signal.SIGINT, _stop)
        try:
            signal.signal(signal.SIGTERM, _stop)
        except (ValueError, AttributeError):
            pass

        print(f"[tracker] running  privacy={self.cfg.privacy_level}  "
              f"interval={self.cfg.sample_interval_sec}s  db={self.cfg.db_path}")
        if self.understand.enabled:
            self.understand.start()
            print(f"[tracker] understanding layer on  backend={self.cfg.understander_backend}"
                  f"  every {self.cfg.understand_interval_sec}s -> {self.cfg.board_base_url}")
        print("[tracker] press Ctrl+C to stop")
        next_t = time.monotonic()
        while self._running:
            try:
                row, frame = self._capture()
                self.store.insert_sample(row)
                if frame is not None:
                    self.store.insert_frame(frame)
                tag = row["category"]
                extra = f" [{row['domain']}]" if row.get("domain") else ""
                print(f"  {time.strftime('%H:%M:%S')}  {row['app'] or '-':<18} "
                      f"{tag:<12} keys={row['keys']:>3} clk={row['clicks']:>2}"
                      f" idle={row['idle_sec']:>4}s{extra}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[tracker] sample error: {exc}")
            try:
                pushed = self.pusher.maybe_push()
                if pushed is not None:
                    print(f"[tracker] usage summary push -> {pushed}")
            except Exception as exc:  # noqa: BLE001
                print(f"[tracker] summary push error: {exc}")
            next_t += self.cfg.sample_interval_sec
            sleep = next_t - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.monotonic()

        self.understand.stop()
        self.meter.stop()
        self.store.close()
        print("\n[tracker] stopped, data saved.")


