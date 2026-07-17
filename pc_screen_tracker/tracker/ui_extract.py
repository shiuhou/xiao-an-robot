"""Layer-2 visible-text extraction via UI Automation.

Two extraction paths, chosen by `mode`:

* browser path (default for Chromium browsers): wake Chromium's lazily-built
  accessibility tree via a WM_GETOBJECT poke, locate the richest DocumentControl
  (the real web content, not the window shell) and read body text from within it.
  This is what makes signal ② (page body text) actually land — verified by
  probe_chrome_body.py.
* legacy path (default for every other app, and available via mode="legacy"):
  the original whole-window BFS walk. Kept verbatim so behavior can be rolled
  back by flipping `mode` without restoring the file.

Everything is best-effort and defensive: any failure yields an empty/partial
snapshot rather than raising, so the collector never stalls.
"""
from __future__ import annotations

import ctypes
import re
import time
from dataclasses import dataclass, field

import uiautomation as auto

try:  # win32 is optional; browser activation degrades gracefully without it
    import win32con
    import win32gui
except Exception:  # noqa: BLE001  # pragma: no cover
    win32con = None
    win32gui = None

# Control types that typically carry meaningful visible text.
_TEXT_TYPES = {
    "TextControl", "DocumentControl", "EditControl", "HyperlinkControl",
    "ButtonControl", "ListItemControl", "TreeItemControl", "TabItemControl",
    "MenuItemControl", "HeaderItemControl", "DataItemControl",
}
# Types worth reading a ValuePattern from (address bar, editors, inputs).
_VALUE_TYPES = {"EditControl", "DocumentControl", "ComboBoxControl"}

# Chromium browsers we run the document-targeted path for.
BROWSER_PROCS = {"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe"}

# window-chrome / nav labels that are NOT page body text
_NOISE = {
    "最小化", "最大化", "还原", "恢复", "关闭", "系统", "新标签页", "返回",
    "前进", "重新加载", "翻译此页？", "Minimize", "Maximize", "Restore", "Close",
    "New Tab", "Back", "Forward", "Reload", "搜索", "Search", "分享", "Share",
    "登录", "注册", "Sign in", "Log in",
    # engagement / action labels living INSIDE the content column (zhihu etc.)
    "关注", "关注他", "关注她", "送礼物", "赞同", "反对", "收藏", "喜欢",
    "申请转载", "举报", "换一换", "大家都在搜", "跳到主要内容", "用户还搜索了",
    "邀请回答", "写回答", "写文章", "发想法", "提问题", "关注问题", "更多",
    "更多回答", "查看详情", "评论", "点赞",
}
# substrings that mark a text as noise (a11y banner from the WM_GETOBJECT poke, etc.)
_NOISE_SUBSTR = (
    "盲人", "智能引导", "Ctrl+Alt+R", "读屏", "无障碍", "screen reader",
    "的广告", "屏幕阅读器",
)
# shape-based noise: shortcut labels, bare urls, hot-list heat tails, counters
_NOISE_RE = re.compile(
    r"\((?:Ctrl|Alt|Shift|Del|F\d)[^)]*\)"   # (Ctrl+B) style shortcut labels
    r"|^[A-Za-z][\w+.-]*://\S+$"               # bare url lines (vscode-file://…)
    r"|\d+(?:\.\d+)?\s*万(?:热度)?$"           # zhihu hot-list heat tails
    r"|^(?:编辑于|发布于|更新于)\b"            # timestamp-of-post lines
    r"|^\d+\s*条评论$|^赞同\s*\d+$"            # bare engagement counters
    r"|^查看全部 .{0,20}(?:回答|评论|结果)$"
    r"|^还没有人送礼物"
    r"|广告$"                                  # ad cards ("… 的广告", "… 广告")
)

# structural pruning: whole subtrees that never contain page/document body
_PRUNE_TYPES = {
    "MenuBarControl", "MenuControl", "ToolBarControl", "StatusBarControl",
    "TabControl", "TreeControl", "TitleBarControl", "ScrollBarControl",
    "SliderControl",
}
# aria landmarks (Chromium) whose subtrees are nav/sidebar/footer, not body
_PRUNE_ROLES = {
    "navigation", "banner", "complementary", "contentinfo", "toolbar",
    "menubar", "tablist", "search", "alert", "alertdialog",
}
# only these control types are worth an aria-role COM call
_ROLE_CHECK_TYPES = {"GroupControl", "CustomControl", "PaneControl"}

# per-profile body char caps: a small excerpt is enough to know the topic;
# full text is fetched on demand (full=True) only when the user asks for it
_PROFILE_CAPS = {"page": 500, "chat": 600}
_FULL_CAP = 4000

_ARIA_ROLE_PROP = 30101  # UIA_AriaRolePropertyId


def _is_noise(s: str) -> bool:
    return (s in _NOISE or any(k in s for k in _NOISE_SUBSTR)
            or bool(_NOISE_RE.search(s)))


def _aria_role(ctrl) -> str:
    try:
        return (ctrl.GetPropertyValue(_ARIA_ROLE_PROP) or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _should_prune(ctrl, ctype: str) -> bool:
    """True if this control's whole subtree is chrome/nav, never body text."""
    if ctype in _PRUNE_TYPES:
        return True
    if ctype in _ROLE_CHECK_TYPES and _aria_role(ctrl) in _PRUNE_ROLES:
        return True
    return False

WM_GETOBJECT = 0x003D
# top-level hwnds already poked for accessibility (poke persists per process)
_ACTIVATED: set[int] = set()


@dataclass
class Snapshot:
    hwnd: int
    app: str
    title: str = ""
    url: str = ""
    texts: list[str] = field(default_factory=list)   # ordered, deduplicated
    node_count: int = 0
    truncated: bool = False
    elapsed_ms: int = 0
    mode: str = ""          # "browser" | "legacy"
    doc_count: int = 0      # DocumentControls seen (browser path)
    kind: str = ""          # browser_page | browser_chat | generic | ...
    capture_policy: str = "full"
    headline: str = ""      # article title / chat contact / doc name

    def as_text(self, max_chars: int = 4000) -> str:
        body = "\n".join(self.texts)
        if len(body) > max_chars:
            body = body[:max_chars] + " …"
        return body

    def to_dict(self) -> dict:
        return {
            "app": self.app,
            "title": self.title,
            "url": self.url,
            "text": self.as_text(),
            "node_count": self.node_count,
            "truncated": self.truncated,
            "elapsed_ms": self.elapsed_ms,
            "mode": self.mode,
            "doc_count": self.doc_count,
            "kind": self.kind,
            "capture_policy": self.capture_policy,
            "headline": self.headline,
        }


_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿⁠"))


def _clean(s: str | None) -> str:
    if not s:
        return ""
    return " ".join(s.translate(_ZERO_WIDTH).split()).strip()


def _body_chars(texts: list[str]) -> int:
    return sum(len(t) for t in texts if t and not _is_noise(t))


def _trim(texts: list[str], cap_chars: int, from_tail: bool = False) -> list[str]:
    """Keep texts up to ~cap_chars. from_tail keeps the LAST ones (newest chat turns)."""
    out: list[str] = []
    total = 0
    for t in (reversed(texts) if from_tail else texts):
        out.append(t)
        total += len(t)
        if total >= cap_chars:
            break
    if from_tail:
        out.reverse()
    return out


def _para_like(t: str) -> bool:
    """Body-paragraph heuristic: real sentences are long; UI labels are short."""
    return len(t) >= 20 and not _is_noise(t)


def _para_chars(texts: list[str]) -> int:
    return sum(len(t) for t in texts if _para_like(t))


def _dedup_contained(texts: list[str]) -> list[str]:
    """Drop texts fully contained in another (card aggregates repeat their
    children: '图片 <title> <excerpt> 用户头像 <author>' + the parts again)."""
    out: list[str] = []
    for t in texts:
        if any(t in u for u in out):
            continue
        out = [u for u in out if u not in t]
        out.append(t)
    return out


def _rank_page(texts: list[str], cap_chars: int) -> list[str]:
    """Page excerpt: prefer paragraph-like blocks (in document order) over
    metadata/action labels that happen to come first in tree order."""
    paras = _dedup_contained([t for t in texts if _para_like(t)])
    if sum(len(t) for t in paras) >= 80:
        return _trim(paras, cap_chars)
    return _trim(_dedup_contained(texts), cap_chars)


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def extract(hwnd: int, app: str = "", *, mode: str = "auto", kind: str = "",
            full: bool = False, max_nodes: int = 800,
            max_depth: int = 40, time_budget_sec: float = 2.5,
            min_len: int = 2, max_texts: int = 600) -> Snapshot:
    """Extract a text snapshot from a window.

    kind: ""/"auto"        browser path for Chromium browsers (profile resolved
                           page-vs-chat by domain), legacy path otherwise
          "browser_page"   force browser path, page profile (title + lead)
          "browser_chat"   force browser path, chat profile (latest turns)
          "legacy"         force the original whole-window walk
    mode is the pre-MVP alias ("auto"/"browser"/"legacy") kept for rollback.
    full=True lifts the per-profile excerpt caps to _FULL_CAP (on-demand read).
    """
    kind = kind or mode  # kind wins when given; mode kept for back-compat
    is_browser = app.lower() in BROWSER_PROCS
    profile = {"browser_page": "page", "browser_chat": "chat",
               "browser": "auto"}.get(kind)
    if profile is None and kind == "auto" and is_browser:
        profile = "auto"
    if profile is None:
        snap = _extract_legacy(
            hwnd, app, max_nodes=max_nodes, max_depth=max_depth,
            time_budget_sec=time_budget_sec, min_len=min_len, max_texts=max_texts,
        )
        snap.kind = "generic"
        snap.headline = snap.title
        return snap
    return _extract_browser(
        hwnd, app, profile=profile, full=full, max_depth=max_depth,
        time_budget_sec=time_budget_sec, min_len=min_len, max_texts=max_texts,
    )


# --------------------------------------------------------------------------- #
# browser path (new)
# --------------------------------------------------------------------------- #
def _find_render_widgets(top_hwnd: int) -> list[int]:
    if win32gui is None:
        return []
    found: list[int] = []

    def _walk(parent: int) -> None:
        child = win32gui.FindWindowEx(parent, 0, None, None)
        while child:
            try:
                if win32gui.GetClassName(child) == "Chrome_RenderWidgetHostHWND":
                    found.append(child)
            except Exception:  # noqa: BLE001
                pass
            _walk(child)
            child = win32gui.FindWindowEx(parent, child, None, None)

    try:
        _walk(top_hwnd)
    except Exception:  # noqa: BLE001
        pass
    return found


def _activate_accessibility(top_hwnd: int) -> bool:
    """Poke Chromium's render widgets so it builds its a11y tree. Returns True
    only the first time a given window is poked (caller may then wait briefly)."""
    if top_hwnd in _ACTIVATED or win32gui is None:
        return False
    widgets = _find_render_widgets(top_hwnd)
    for hwnd in widgets:
        try:
            win32gui.SendMessageTimeout(
                hwnd, WM_GETOBJECT, 0, 1, win32con.SMTO_ABORTIFHUNG, 400
            )
        except Exception:  # noqa: BLE001
            try:
                ctypes.windll.user32.SendMessageW(hwnd, WM_GETOBJECT, 0, 1)
            except Exception:  # noqa: BLE001
                pass
    _ACTIVATED.add(top_hwnd)
    return bool(widgets)


def _focused_in_window(hwnd: int):
    """The focused control, if it belongs to this top-level window."""
    try:
        focused = auto.GetFocusedControl()
        if not focused:
            return None
        top = focused.GetTopLevelControl()
        if top and top.NativeWindowHandle == hwnd:
            return focused
    except Exception:  # noqa: BLE001
        pass
    return None


def _doc_of_focus(hwnd: int):
    """Ascend from the focused control to its DocumentControl (browser: the
    document the user is actually in — skips reading the other 5 shells)."""
    ctrl = _focused_in_window(hwnd)
    for _ in range(40):
        if ctrl is None:
            return None
        try:
            if ctrl.ControlTypeName == "DocumentControl":
                return ctrl
            ctrl = ctrl.GetParentControl()
        except Exception:  # noqa: BLE001
            return None
    return None


def _focus_texts(hwnd: int, max_chars: int = 2000) -> list[str]:
    """Read text straight from the focused control (caret area): its Value
    and/or TextPattern document. This is 'where the user is typing'."""
    focused = _focused_in_window(hwnd)
    if focused is None:
        return []
    out: list[str] = []
    try:
        val = _clean(focused.GetValuePattern().Value)
        if val and not _is_noise(val):
            out.append(val[:max_chars])
    except Exception:  # noqa: BLE001
        pass
    try:
        tp = focused.GetTextPattern()
        if tp:
            txt = _clean(tp.DocumentRange.GetText(max_chars))
            if txt and not _is_noise(txt) and txt not in out:
                out.append(txt)
    except Exception:  # noqa: BLE001
        pass
    return out


def _find_documents(root: "auto.Control", budget_s: float) -> list:
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


def _walk_doc(doc, *, max_depth: int, budget_s: float, min_len: int,
              max_texts: int) -> tuple[list[str], int, bool]:
    start = time.monotonic()
    texts: list[str] = []
    seen: set[str] = set()
    n = 0
    truncated = False
    queue = [(doc, 0)]
    while queue:
        if len(texts) >= max_texts or (time.monotonic() - start) > budget_s:
            truncated = True
            break
        ctrl, depth = queue.pop(0)
        n += 1
        try:
            ctype = ctrl.ControlTypeName
        except Exception:  # noqa: BLE001
            ctype = ""
        if _should_prune(ctrl, ctype):
            continue  # skip the whole nav/toolbar/sidebar subtree
        if ctype in _TEXT_TYPES:
            name = _clean(getattr(ctrl, "Name", ""))
            if len(name) >= min_len and name not in seen and not _is_noise(name):
                seen.add(name)
                texts.append(name)
        if ctype in _VALUE_TYPES:
            try:
                val = _clean(ctrl.GetValuePattern().Value)
            except Exception:  # noqa: BLE001
                val = ""
            if val and val not in seen and not _is_noise(val):
                seen.add(val)
                texts.append(val)
        if depth < max_depth:
            try:
                for ch in ctrl.GetChildren():
                    queue.append((ch, depth + 1))
            except Exception:  # noqa: BLE001
                pass
    return texts, n, truncated


def _find_main_region(doc, budget_s: float = 1.2):
    """Find the ARIA main/article landmark inside a document, if exposed.
    Prunes nav/sidebar/footer subtrees while searching so the budget is spent
    on branches that can actually contain the landmark."""
    start = time.monotonic()
    queue = [(doc, 0)]
    while queue and (time.monotonic() - start) < budget_s:
        ctrl, depth = queue.pop(0)
        try:
            ctype = ctrl.ControlTypeName
        except Exception:  # noqa: BLE001
            ctype = ""
        role = _aria_role(ctrl) if ctype in _ROLE_CHECK_TYPES else ""
        if role in ("main", "article"):
            return ctrl
        if role in _PRUNE_ROLES or ctype in _PRUNE_TYPES:
            continue  # landmark never nests inside nav/sidebar/footer
        if depth < 20:
            try:
                for ch in ctrl.GetChildren():
                    queue.append((ch, depth + 1))
            except Exception:  # noqa: BLE001
                pass
    return None


def _extract_browser(hwnd: int, app: str, *, max_depth: int, time_budget_sec: float,
                     min_len: int, max_texts: int, profile: str = "auto",
                     full: bool = False) -> Snapshot:
    start = time.monotonic()
    snap = Snapshot(hwnd=hwnd, app=app, mode="browser")
    old_timeout = auto.uiautomation.TIME_OUT_SECOND
    auto.SetGlobalSearchTimeout(1.5)
    try:
        # wake the a11y tree (once per window); brief settle only on first poke
        if _activate_accessibility(hwnd):
            time.sleep(0.6)

        root = auto.ControlFromHandle(hwnd)
        if not root:
            return snap
        snap.title = _clean(root.Name)
        snap.headline = snap.title

        # url from the address bar (window chrome, not inside the document)
        dom = None
        try:
            from tracker.content import browser_url
            full_url, dom = browser_url(hwnd)
            snap.url = full_url or dom or ""
        except Exception:  # noqa: BLE001
            pass

        # resolve page-vs-chat by domain when the caller didn't force one
        if profile == "auto":
            try:
                from tracker.surface import is_chat_domain
                profile = "chat" if is_chat_domain(dom or "") else "page"
            except Exception:  # noqa: BLE001
                profile = "page"
        snap.kind = "browser_chat" if profile == "chat" else "browser_page"

        best: list[str] = []
        best_chars = -1

        def _walk_docs(dlist: list) -> None:
            nonlocal best, best_chars
            for doc in dlist:
                region = _find_main_region(doc) or doc
                texts, n, truncated = _walk_doc(
                    region, max_depth=max_depth,
                    budget_s=max(0.8, time_budget_sec / max(1, len(dlist))),
                    min_len=min_len, max_texts=max_texts,
                )
                snap.node_count += n
                c = _para_chars(texts) * 3 + _body_chars(texts)  # paragraphs win
                if c > best_chars:
                    best, best_chars, snap.truncated = texts, c, truncated

        # prefer the document that HAS FOCUS (the one the user is in) — it
        # skips scanning the 5 shell documents; but do NOT trust it blindly:
        # focus may sit in an iframe/empty doc, so fall back on poor quality
        fdoc = _doc_of_focus(hwnd)
        if fdoc is not None:
            snap.doc_count = 1
            _walk_docs([fdoc])
        if _para_chars(best) < 80:
            docs = _find_documents(root, budget_s=min(1.5, time_budget_sec))
            snap.doc_count = len(docs)
            _walk_docs(docs)

        # excerpt: small cap per profile; full=True is the on-demand read
        cap = _FULL_CAP if full else _PROFILE_CAPS.get(profile, _FULL_CAP)
        if profile == "chat":
            snap.texts = _trim(best, cap, from_tail=True)
        else:
            snap.texts = _rank_page(best, cap)
    except Exception:  # noqa: BLE001
        pass
    finally:
        auto.SetGlobalSearchTimeout(old_timeout)
        snap.elapsed_ms = int((time.monotonic() - start) * 1000)
    return snap


# --------------------------------------------------------------------------- #
# legacy path (original whole-window walk, unchanged behavior)
# --------------------------------------------------------------------------- #
def _extract_legacy(hwnd: int, app: str, *, max_nodes: int, max_depth: int,
                    time_budget_sec: float, min_len: int, max_texts: int) -> Snapshot:
    start = time.monotonic()
    snap = Snapshot(hwnd=hwnd, app=app, mode="legacy")
    old_timeout = auto.uiautomation.TIME_OUT_SECOND
    auto.SetGlobalSearchTimeout(1.0)
    try:
        root = auto.ControlFromHandle(hwnd)
        if not root:
            return snap
        snap.title = _clean(root.Name)

        # focus anchor: read where the user's caret actually is (editor body,
        # input box). If it yields real text, that IS the content — done.
        ftexts = _focus_texts(hwnd)
        if _body_chars(ftexts) >= 40:
            snap.texts = ftexts
            snap.mode = "focus"
            return snap

        seen: set[str] = set()

        queue: list[tuple[auto.Control, int]] = [(root, 0)]
        while queue:
            if snap.node_count >= max_nodes or \
                    (time.monotonic() - start) > time_budget_sec or \
                    len(snap.texts) >= max_texts:
                snap.truncated = True
                break
            ctrl, depth = queue.pop(0)
            snap.node_count += 1
            ctype = ""
            try:
                ctype = ctrl.ControlTypeName
            except Exception:  # noqa: BLE001
                pass
            if _should_prune(ctrl, ctype):
                continue  # skip menus/toolbars/status bars/file trees wholesale

            if ctype in _TEXT_TYPES:
                name = _clean(getattr(ctrl, "Name", ""))
                if len(name) >= min_len and name not in seen and not _is_noise(name):
                    seen.add(name)
                    snap.texts.append(name)

            if ctype in _VALUE_TYPES:
                try:
                    val = _clean(ctrl.GetValuePattern().Value)
                except Exception:  # noqa: BLE001
                    val = ""
                if val:
                    low = (getattr(ctrl, "Name", "") or "").lower()
                    if not snap.url and ("address" in low or "地址" in low or
                                         val.startswith(("http://", "https://"))):
                        snap.url = val
                    elif val not in seen:
                        seen.add(val)
                        snap.texts.append(val)

            if depth < max_depth:
                try:
                    for child in ctrl.GetChildren():
                        queue.append((child, depth + 1))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        auto.SetGlobalSearchTimeout(old_timeout)
        snap.elapsed_ms = int((time.monotonic() - start) * 1000)
    return snap
