"""The sampling loop: snapshot foreground + input activity every interval."""
from __future__ import annotations

import re
import signal
import time

from .classify import Classifier
from .config import Config
from .content import browser_url
from .input_meter import InputMeter
from .store import Store
from .window import foreground_window, idle_seconds


class Collector:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.store = Store(cfg.db_path)
        self.classifier = Classifier()
        self.meter = InputMeter()
        self._blocklist = [re.compile(p) for p in cfg.blocklist_apps]
        self._running = False

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

        return {
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
        print("[tracker] press Ctrl+C to stop")
        next_t = time.monotonic()
        while self._running:
            try:
                row = self._capture()
                self.store.insert_sample(row)
                tag = row["category"]
                extra = f" [{row['domain']}]" if row.get("domain") else ""
                print(f"  {time.strftime('%H:%M:%S')}  {row['app'] or '-':<18} "
                      f"{tag:<12} keys={row['keys']:>3} clk={row['clicks']:>2}"
                      f" idle={row['idle_sec']:>4}s{extra}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[tracker] sample error: {exc}")
            next_t += self.cfg.sample_interval_sec
            sleep = next_t - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.monotonic()

        self.meter.stop()
        self.store.close()
        print("\n[tracker] stopped, data saved.")


