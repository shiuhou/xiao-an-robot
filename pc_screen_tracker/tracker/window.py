"""Layer-1 foreground window + idle capture via Win32 (no external content)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

import psutil
import win32gui
import win32process

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    _user32.GetLastInputInfo(ctypes.byref(lii))
    millis = _kernel32.GetTickCount() - lii.dwTime
    return max(0.0, millis / 1000.0)


@dataclass
class WindowInfo:
    hwnd: int
    app: str          # process image name, e.g. "chrome.exe"
    title: str        # window title (may be empty)


def foreground_window() -> WindowInfo | None:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    try:
        title = win32gui.GetWindowText(hwnd) or ""
    except Exception:  # noqa: BLE001
        title = ""
    app = "?"
    try:
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        app = psutil.Process(pid).name()
    except Exception:  # noqa: BLE001
        pass
    return WindowInfo(hwnd=hwnd, app=app, title=title)
