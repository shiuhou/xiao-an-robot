"""Surface detection: which extraction profile & capture policy a frame gets.

Maps (app, title, domain, category) -> Surface(kind, capture_policy).
Reuses the Classifier category as the coarse signal and only adds what it
cannot express: AI-chat domains, the IM privacy red line, sensitive apps.

Capture policies:
  full      normal content extraction (per-profile caps in ui_extract)
  meta_only headline (e.g. chat contact) + dwell/input meters only —
            message/content text is NEVER read into memory
  none      nothing beyond app name + category
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Chromium browsers (keep in sync with config.browser_procs / ui_extract)
BROWSER_PROCS = {"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe"}

# AI chat sites -> dialog-focused extraction (MVP: hardcoded, move to config later)
AI_CHAT_DOMAINS = {
    "chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com",
    "doubao.com", "yuanbao.tencent.com", "kimi.moonshot.cn", "kimi.com",
    "tongyi.aliyun.com", "chatglm.cn", "chat.deepseek.com", "deepseek.com",
    "perplexity.ai", "poe.com", "copilot.microsoft.com", "grok.com",
}

# Apps/titles whose content must never be captured (finance / password vaults)
_SENSITIVE = re.compile(
    r"(?i)keepass|1password|bitwarden|bank|银行|证券|同花顺|东方财富|支付宝|alipay"
)


@dataclass(frozen=True)
class Surface:
    kind: str            # browser_chat | browser_page | im | sensitive | os_shell | generic
    capture_policy: str  # full | meta_only | none


def is_chat_domain(domain: str) -> bool:
    d = (domain or "").lower()
    return bool(d) and any(d == c or d.endswith("." + c) for c in AI_CHAT_DOMAINS)


def detect(app: str, title: str = "", domain: str = "",
           category: str = "") -> Surface:
    """Pick the extraction surface for a frame.

    `category` is the Classifier output; `domain` may be empty for browser
    frames (the browser path resolves page-vs-chat itself once it has the url).
    """
    app_l = (app or "").lower()
    if _SENSITIVE.search(f"{app} | {title}"):
        return Surface("sensitive", "none")
    if app_l in BROWSER_PROCS:
        if is_chat_domain(domain):
            return Surface("browser_chat", "full")
        return Surface("browser_page", "full")
    if category == "communication":
        # IM red line: contact + dwell only, message text is never read
        return Surface("im", "meta_only")
    if category in ("terminal", "file"):
        return Surface("os_shell", "full")
    return Surface("generic", "full")
