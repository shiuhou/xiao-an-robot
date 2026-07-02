"""Compatibility wrapper for `base_station.monitor.fixed_window_asr_demo`."""

from base_station.monitor.fixed_window_asr_demo import *  # noqa: F401,F403
from base_station.monitor.fixed_window_asr_demo import main


if __name__ == "__main__":
    raise SystemExit(main())
