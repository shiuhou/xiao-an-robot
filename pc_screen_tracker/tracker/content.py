"""Layer-2 content capture via UI Automation.

Currently: read the address bar of Chromium browsers to recover the URL/domain.
This is best-effort and defensive: any failure returns (None, None) rather than
raising, so the collector never stalls on a slow/again UIA call.
"""
from __future__ import annotations

from urllib.parse import urlparse

import uiautomation as auto

# Names the Chromium/Edge address bar exposes across locales.
_ADDRESS_NAMES = ("address and search bar", "address", "地址和搜索栏", "地址栏")


def _domain_from_text(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "http://" + text
    try:
        host = urlparse(text).netloc.lower()
    except Exception:  # noqa: BLE001
        return None
    if host.startswith("www."):
        host = host[4:]
    if "." not in host:
        return None  # half-typed omnibox input ("multica-a"), not a domain
    return host or None


def browser_url(hwnd: int, timeout_sec: float = 1.0) -> tuple[str | None, str | None]:
    """Return (full_url, domain) for a Chromium window, or (None, None)."""
    old = auto.uiautomation.TIME_OUT_SECOND
    auto.SetGlobalSearchTimeout(timeout_sec)
    try:
        win = auto.ControlFromHandle(hwnd)
        if not win:
            return None, None
        edit = win.EditControl(searchDepth=12)
        if not edit.Exists(maxSearchSeconds=timeout_sec):
            return None, None
        name = (edit.Name or "").lower()
        if not any(key in name for key in _ADDRESS_NAMES):
            # fall back: first edit control is usually the omnibox anyway
            pass
        value = ""
        try:
            value = edit.GetValuePattern().Value or ""
        except Exception:  # noqa: BLE001
            try:
                value = edit.GetLegacyIAccessiblePattern().Value or ""
            except Exception:  # noqa: BLE001
                value = ""
        value = value.strip()
        if not value:
            return None, None
        full = value if "://" in value else None
        return full, _domain_from_text(value)
    except Exception:  # noqa: BLE001
        return None, None
    finally:
        auto.SetGlobalSearchTimeout(old)
