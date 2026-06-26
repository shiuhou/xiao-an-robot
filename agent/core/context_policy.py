"""Pure policy for deciding which compatibility scopes should be injected."""

from __future__ import annotations

from dataclasses import dataclass, field


SCOPE_ORDER = [
    "work",
    "notes",
    "tasks",
    "reminders",
    "summaries",
    "tool_runs",
    "care",
]


@dataclass
class ContextInjectionDecision:
    needs_work_context: bool
    reason: str
    matched_keywords: list[str]
    needs_notes_context: bool = False
    needs_tasks_context: bool = False
    needs_reminders_context: bool = False
    needs_summaries_context: bool = False
    needs_tool_runs_context: bool = False
    needs_care_context: bool = False
    requested_scopes: list[str] = field(default_factory=list)
    method: str = "keyword_heuristic"
    confidence: float = 0.0


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
    "当前工作",
    "写到哪",
    "做到哪",
]

NOTES_CONTEXT_KEYWORDS = [
    "笔记",
    "记了什么",
    "记录了什么",
    "我刚刚记",
    "我记了",
    "记一下",
    "备忘",
    "备注",
    "note",
    "notes",
    "让我记了什么",
    "让你记了什么",
    "最近有什么笔记",
]

TASKS_CONTEXT_KEYWORDS = [
    "任务",
    "待办",
    "todo",
    "to-do",
    "还有什么要做",
    "还要做什么",
    "完成了什么",
    "没完成",
    "已完成",
    "待完成",
    "task",
    "tasks",
    "有什么还没完成",
    "还没完成",
    "还有哪些任务",
    "哪些任务没完成",
    "把任务列一下",
]

REMINDERS_CONTEXT_KEYWORDS = [
    "提醒",
    "定时",
    "叫我",
    "几分钟后",
    "多久后",
    "闹钟",
    "reminder",
    "reminders",
    "有什么提醒",
    "明天有什么提醒",
]

SUMMARIES_CONTEXT_KEYWORDS = [
    "总结",
    "日报",
    "今日总结",
    "今天总结",
    "今天进展",
    "今天做了什么",
    "汇总",
    "summary",
    "summaries",
    "最近日报是什么",
]

TOOL_RUNS_CONTEXT_KEYWORDS = [
    "工具调用",
    "调用了什么工具",
    "用了什么工具",
    "tool run",
    "tool runs",
    "今天有哪些工具调用",
]

CARE_CONTEXT_KEYWORDS = [
    "关心过我",
    "关心我",
    "照顾我",
    "安慰我",
    "陪伴过我",
    "今天状态怎么样",
    "状态怎么样",
    "情绪怎么样",
    "疲劳状态",
]

KEYWORDS_BY_SCOPE = {
    "work": WORK_CONTEXT_KEYWORDS,
    "notes": NOTES_CONTEXT_KEYWORDS,
    "tasks": TASKS_CONTEXT_KEYWORDS,
    "reminders": REMINDERS_CONTEXT_KEYWORDS,
    "summaries": SUMMARIES_CONTEXT_KEYWORDS,
    "tool_runs": TOOL_RUNS_CONTEXT_KEYWORDS,
    "care": CARE_CONTEXT_KEYWORDS,
}


class ContextInjectionPolicy:
    """Keyword-based compatibility scope router for ContextBuilder."""

    def decide_for_text(self, text: str | None) -> ContextInjectionDecision:
        if text is None or not text.strip():
            return ContextInjectionDecision(
                needs_work_context=False,
                reason="empty_text",
                matched_keywords=[],
                requested_scopes=[],
                confidence=0.0,
            )

        matched_keyword_scopes: list[tuple[str, str]] = []
        matched_scopes: set[str] = set()
        for scope in SCOPE_ORDER:
            for keyword in KEYWORDS_BY_SCOPE[scope]:
                if keyword in text:
                    matched_keyword_scopes.append((scope, keyword))
                    matched_scopes.add(scope)

        if not matched_keyword_scopes:
            return ContextInjectionDecision(
                needs_work_context=False,
                reason="no_context_needed",
                matched_keywords=[],
                requested_scopes=[],
                confidence=0.0,
            )

        work_matches = [
            keyword
            for scope, keyword in matched_keyword_scopes
            if scope == "work"
        ]
        non_work_matched = any(scope != "work" for scope, _ in matched_keyword_scopes)
        if non_work_matched and work_matches and set(work_matches) <= {"刚刚", "刚才"}:
            matched_scopes.discard("work")
            matched_keyword_scopes = [
                (scope, keyword)
                for scope, keyword in matched_keyword_scopes
                if not (scope == "work" and keyword in {"刚刚", "刚才"})
            ]

        if "summaries" in matched_scopes:
            matched_scopes.update(SCOPE_ORDER)

        requested_scopes = [scope for scope in SCOPE_ORDER if scope in matched_scopes]
        matched_keywords = [keyword for _, keyword in matched_keyword_scopes]
        return ContextInjectionDecision(
            needs_work_context="work" in matched_scopes,
            needs_notes_context="notes" in matched_scopes,
            needs_tasks_context="tasks" in matched_scopes,
            needs_reminders_context="reminders" in matched_scopes,
            needs_summaries_context="summaries" in matched_scopes,
            needs_tool_runs_context="tool_runs" in matched_scopes,
            needs_care_context="care" in matched_scopes,
            reason="memory_keyword",
            matched_keywords=matched_keywords,
            requested_scopes=requested_scopes,
            confidence=0.7,
        )
