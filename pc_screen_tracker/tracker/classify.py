"""Rule-based activity categorization (inspired by ActivityWatch category rules).

Deepest / first matching rule wins. Rules match against a combined
"app | title | domain" string, case-insensitive regex.
"""
from __future__ import annotations

import re

# (category, regex) — order matters: earlier, more specific rules win.
DEFAULT_RULES: list[tuple[str, str]] = [
    ("coding",        r"(?i)\b(code\.exe|pycharm|idea|goland|clion|sublime_text|"
                      r"windsurf|cursor|devenv|vim|nvim|neovim)\b"),
    ("coding",        r"(?i)(github\.com|gitlab|stackoverflow|localhost:\d+|"
                      r"\.py |\.ts |\.cpp |\.rs )"),
    ("terminal",      r"(?i)\b(windowsterminal|cmd\.exe|powershell|pwsh|wt\.exe|"
                      r"conhost|bash|wsl)\b"),
    ("meeting",       r"(?i)(zoom|tencent.?meeting|腾讯会议|teams|webex|voov|"
                      r"飞书会议|lark.?meeting|google meet)"),
    ("writing",       r"(?i)\b(winword|word|wps|et\.exe|powerpnt|notion|obsidian|"
                      r"typora|onenote|texstudio|latex|overleaf)\b"),
    ("communication", r"(?i)\b(wechat|weixin|微信|qq\.exe|dingtalk|钉钉|feishu|"
                      r"lark|slack|discord|telegram|outlook|foxmail|doubao)\b"),
    ("entertainment", r"(?i)(bilibili|哔哩|youtube|netflix|iqiyi|爱奇艺|优酷|"
                      r"腾讯视频|douyin|抖音|spotify|music|steam|game)"),
    ("browsing",      r"(?i)\b(chrome|msedge|firefox|brave|vivaldi)\b"),
    ("design",       r"(?i)\b(photoshop|figma|illustrator|blender|premiere|"
                      r"afterfx|clip.?studio|krita)\b"),
    ("file",          r"(?i)\b(explorer\.exe|totalcmd|files\.exe)\b"),
]


class Classifier:
    def __init__(self, rules: list[tuple[str, str]] | None = None):
        self._rules = [(cat, re.compile(pat)) for cat, pat in (rules or DEFAULT_RULES)]

    def classify(self, app: str | None, title: str | None,
                 domain: str | None = None) -> str:
        haystack = " | ".join(x for x in (app, title, domain) if x)
        if not haystack:
            return "unknown"
        for cat, pat in self._rules:
            if pat.search(haystack):
                return cat
        return "other"
