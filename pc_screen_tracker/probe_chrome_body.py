"""Feasibility spike: can we read Chrome page BODY text via UI Automation?

Focus a text-heavy Chrome tab, then run:  python -u probe_chrome_body.py

Tries activation methods least->most intrusive and reports, per method, how much
real body text it can read. Read-only: nothing stored, Chrome never killed.
"""
from __future__ import annotations

import ctypes
import io
import sys
import time
from ctypes import wintypes

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import uiautomation as auto
import win32con
import win32gui

from tracker.content import browser_url
from tracker.window import foreground_window

# window-chrome / nav labels that are NOT page body text
NOISE = {
    "最小化", "最大化", "还原", "恢复", "关闭", "系统", "新标签页", "返回",
    "前进", "重新加载", "翻译此页？", "Minimize", "Maximize", "Restore", "Close",
    "New Tab", "Back", "Forward", "Reload",
}
SUCCESS_CHARS = 200
WM_GETOBJECT = 0x003D


def _find_render_widgets(top_hwnd: int) -> list[int]:
    """Collect descendant windows of class Chrome_RenderWidgetHostHWND."""
    found: list[int] = []

    def _walk(parent: int) -> None:
        child = win32gui.FindWindowEx(parent, 0, None, None)
        while child:
            try:
                cls = win32gui.GetClassName(child)
            except Exception:  # noqa: BLE001
                cls = ""
            if cls == "Chrome_RenderWidgetHostHWND":
                found.append(child)
            _walk(child)
            child = win32gui.FindWindowEx(parent, child, None, None)

    _walk(top_hwnd)
    return found


def _activate_accessibility(top_hwnd: int) -> int:
    """Send WM_GETOBJECT with a custom object id to make Chromium think an AT
    is attached. Returns how many render-widget windows were poked."""
    widgets = _find_render_widgets(top_hwnd)
    for hwnd in widgets:
        # custom object id (lParam=1) is the documented AT-detection trigger
        try:
            win32gui.SendMessageTimeout(
                hwnd, WM_GETOBJECT, 0, 1, win32con.SMTO_ABORTIFHUNG, 800
            )
        except Exception:
            try:
                ctypes.windll.user32.SendMessageW(hwnd, WM_GETOBJECT, 0, 1)
            except Exception:  # noqa: BLE001
                pass
    return len(widgets)


def _find_documents(root: "auto.Control", budget_s: float = 2.5) -> list:
    """BFS for ALL DocumentControls (Chrome nests shell + real content + iframes)."""
    start = time.monotonic()
    docs = []
    queue = [(root, 0)]
    while queue and (time.monotonic() - start) < budget_s:
        ctrl, depth = queue.pop(0)
        try:
            if ctrl.ControlTypeName == "DocumentControl":
                docs.append(ctrl)
        except Exception:  # noqa: BLE001
            pass
        if depth < 30:
            try:
                for ch in ctrl.GetChildren():
                    queue.append((ch, depth + 1))
            except Exception:  # noqa: BLE001
                pass
    return docs


def _text_via_pattern(doc) -> str:
    try:
        tp = doc.GetTextPattern()
        if not tp:
            return ""
        rng = tp.DocumentRange
        return (rng.GetText(-1) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _text_via_walk(doc, budget_s: float = 2.5, max_nodes: int = 1500) -> str:
    start = time.monotonic()
    out: list[str] = []
    seen: set[str] = set()
    queue = [(doc, 0)]
    n = 0
    while queue and n < max_nodes and (time.monotonic() - start) < budget_s:
        ctrl, depth = queue.pop(0)
        n += 1
        try:
            name = " ".join((ctrl.Name or "").split()).strip()
        except Exception:  # noqa: BLE001
            name = ""
        if len(name) >= 2 and name not in seen and name not in NOISE:
            seen.add(name)
            out.append(name)
        if depth < 40:
            try:
                for ch in ctrl.GetChildren():
                    queue.append((ch, depth + 1))
            except Exception:  # noqa: BLE001
                pass
    return "\n".join(out).strip()


def _body_chars(text: str) -> int:
    """Count chars after removing pure-noise lines."""
    lines = [ln for ln in text.splitlines() if ln.strip() and ln.strip() not in NOISE]
    return sum(len(ln) for ln in lines)


def measure(top_hwnd: int, label: str) -> int:
    print(f"\n=== {label} ===")
    auto.SetGlobalSearchTimeout(2.0)
    root = auto.ControlFromHandle(top_hwnd)
    if not root:
        print("  (could not bind UIA to window)")
        return 0
    docs = _find_documents(root)
    print(f"  DocumentControls found: {len(docs)}")
    if not docs:
        return 0

    # measure every document, keep the richest (real content, not the shell)
    best_text, best_chars, via = "", 0, "-"
    tp_any = False
    for doc in docs:
        tp_text = _text_via_pattern(doc)
        if tp_text:
            tp_any = True
        for text, tag in ((tp_text, "TextPattern"), (_text_via_walk(doc), "walk")):
            c = _body_chars(text)
            if c > best_chars:
                best_text, best_chars, via = text, c, tag
    print(f"  TextPattern available : {'yes' if tp_any else 'no'}")
    preview = best_text.replace("\n", " ⏎ ")[:300]
    print(f"  BEST                  : {best_chars} chars via {via}")
    print(f"  preview> {preview}")
    return best_chars


def main() -> None:
    win = foreground_window()
    if not win:
        print("No foreground window."); return
    print(f"Foreground: {win.app}  |  {win.title[:60]}")
    if "chrome" not in win.app.lower():
        print("!! Focus a Chrome tab first, then re-run. (Detected non-Chrome app.)")
        return
    full, dom = browser_url(win.hwnd)
    print(f"URL: {full or dom or '(none)'}")
    if any(k in win.title for k in ("新标签页", "New Tab")) or not (full or dom):
        print("!! Looks like an empty new-tab page — focus a real article/content page "
              "(e.g. a zhihu answer or docs page) for a meaningful test.")

    m0 = measure(win.hwnd, "M0  baseline (no activation)")

    n = _activate_accessibility(win.hwnd)
    print(f"\n[M1] poked {n} Chrome_RenderWidgetHostHWND window(s) with WM_GETOBJECT; "
          f"waiting for tree to build...")
    time.sleep(0.8)
    m1 = measure(win.hwnd, "M1  after WM_GETOBJECT activation")
    # second settle in case first build was partial
    if m1 < SUCCESS_CHARS:
        time.sleep(1.2)
        m1 = max(m1, measure(win.hwnd, "M1' after extra settle"))

    print("\n" + "=" * 52)
    print("VERDICT")
    print(f"  M0 baseline           : {m0} body chars")
    print(f"  M1 WM_GETOBJECT       : {m1} body chars")
    if m1 >= SUCCESS_CHARS:
        print(f"  ==> SUCCESS: body text readable with ZERO user setup (>= {SUCCESS_CHARS}).")
    elif m0 >= SUCCESS_CHARS:
        print("  ==> Body text already readable without activation (a11y likely already on).")
    else:
        print(f"  ==> M0/M1 failed (< {SUCCESS_CHARS} chars). Try M2:")
        print("      1) fully close Chrome")
        print('      2) relaunch: chrome.exe --force-renderer-accessibility=complete')
        print("      3) focus a text page and re-run this probe")
    print("=" * 52)


if __name__ == "__main__":
    main()
