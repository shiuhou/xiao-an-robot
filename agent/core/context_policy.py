"""Pure policy for deciding whether work context should be injected."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextInjectionDecision:
    needs_work_context: bool
    reason: str
    matched_keywords: list[str]


WORK_CONTEXT_KEYWORDS = [
    "刚刚",
    "刚才",
    "刚才在做什么",
    "在做什么",
    "继续",
    "继续刚才",
    "工作",
    "项目",
    "代码",
    "开发",
    "调试",
    "进度",
    "总结今天",
    "今天做了什么",
    "今天开发",
    "日报",
    "晨报",
    "会议",
    "纪要",
    "任务",
    "待办",
    "记录当前工作",
    "当前工作",
    "写到哪",
    "做到哪",
]


class ContextInjectionPolicy:
    """Keyword-based work-context injection policy."""

    def decide_for_text(self, text: str | None) -> ContextInjectionDecision:
        if text is None or not text.strip():
            return ContextInjectionDecision(
                needs_work_context=False,
                reason="empty_text",
                matched_keywords=[],
            )

        matched_keywords = [
            keyword
            for keyword in WORK_CONTEXT_KEYWORDS
            if keyword in text
        ]
        if matched_keywords:
            return ContextInjectionDecision(
                needs_work_context=True,
                reason="work_keyword",
                matched_keywords=matched_keywords,
            )

        return ContextInjectionDecision(
            needs_work_context=False,
            reason="no_context_needed",
            matched_keywords=[],
        )
