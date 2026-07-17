"""Enumerate visible top-level windows for whitelist selection."""
from __future__ import annotations

from dataclasses import dataclass

import psutil
import win32gui
import win32process


@dataclass
class AppWindow:
    app: str
    title: str
    hwnd: int


def list_windowed_apps() -> list[AppWindow]:
    """One entry per process that currently owns a visible, titled window."""
    seen: dict[str, AppWindow] = {}

    def _cb(hwnd: int, _extra) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            app = psutil.Process(pid).name()
        except Exception:  # noqa: BLE001
            return
        # keep the first (usually main) window title per app
        seen.setdefault(app, AppWindow(app=app, title=title, hwnd=hwnd))

    win32gui.EnumWindows(_cb, None)
    return sorted(seen.values(), key=lambda a: a.app.lower())
