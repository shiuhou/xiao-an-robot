"""Background keyboard/mouse activity meter using pynput.

Listeners run on their own threads and accumulate counters. The collector calls
`snapshot()` once per interval to read and reset the deltas, giving per-interval
rates without storing any key identities (only counts) -> not a keylogger.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass

from pynput import keyboard, mouse


@dataclass
class InputDelta:
    keys: int
    clicks: int
    scrolls: int
    mouse_px: float


class InputMeter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys = 0
        self._clicks = 0
        self._scrolls = 0
        self._mouse_px = 0.0
        self._last_pos: tuple[int, int] | None = None
        self._kb = keyboard.Listener(on_press=self._on_press)
        self._ms = mouse.Listener(
            on_click=self._on_click, on_move=self._on_move, on_scroll=self._on_scroll
        )

    # --- callbacks (count only, never the key value) ---
    def _on_press(self, _key) -> None:
        with self._lock:
            self._keys += 1

    def _on_click(self, _x, _y, _button, pressed) -> None:
        if pressed:
            with self._lock:
                self._clicks += 1

    def _on_scroll(self, _x, _y, _dx, _dy) -> None:
        with self._lock:
            self._scrolls += 1

    def _on_move(self, x, y) -> None:
        with self._lock:
            if self._last_pos is not None:
                dx = x - self._last_pos[0]
                dy = y - self._last_pos[1]
                self._mouse_px += math.hypot(dx, dy)
            self._last_pos = (x, y)

    # --- lifecycle ---
    def start(self) -> None:
        self._kb.start()
        self._ms.start()

    def stop(self) -> None:
        self._kb.stop()
        self._ms.stop()

    def snapshot(self) -> InputDelta:
        with self._lock:
            delta = InputDelta(self._keys, self._clicks, self._scrolls, self._mouse_px)
            self._keys = self._clicks = self._scrolls = 0
            self._mouse_px = 0.0
            return delta
