"""Entry point.

  python run.py track                 # start collecting (Ctrl+C to stop)
  python run.py report                # today's report to console
  python run.py report --hours 3      # last 3 hours
  python run.py report --html out.html
  python run.py init                  # write a config.json template
"""
from __future__ import annotations

import argparse
import io
import sys
import time

# ensure UTF-8 console on Windows so Chinese titles print correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from tracker.config import Config
from tracker.collector import Collector
from tracker.report import build_report, render_console, render_html
from tracker.store import Store


def _start_of_today_ms() -> int:
    lt = time.localtime()
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return int(midnight * 1000)


def cmd_track(cfg: Config, _args) -> None:
    Collector(cfg).run()


def cmd_report(cfg: Config, args) -> None:
    store = Store(cfg.db_path)
    if args.hours:
        since = int(time.time() * 1000) - int(args.hours * 3600 * 1000)
    else:
        since = _start_of_today_ms()
    rep = build_report(store, since)
    print(render_console(rep))
    if args.html:
        path = render_html(rep, args.html)
        print(f"\nHTML report written to: {path}")
    store.close()


def cmd_init(cfg: Config, _args) -> None:
    cfg.save_template()
    print("Wrote config.json template. Edit privacy_level / interval as needed.")


def main() -> None:
    p = argparse.ArgumentParser(description="Xiao An screen usage tracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("track")
    rp = sub.add_parser("report")
    rp.add_argument("--hours", type=float, default=0, help="look back N hours (default: today)")
    rp.add_argument("--html", type=str, default="", help="also write an HTML report to this path")
    sub.add_parser("init")

    args = p.parse_args()
    cfg = Config.load()
    {"track": cmd_track, "report": cmd_report, "init": cmd_init}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
