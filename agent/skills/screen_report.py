"""Voice-triggered screen usage report.

"汇总屏幕使用记录/使用时间" -> assemble a Markdown report from the Local Event
Store (PC-pushed usage summary cache + today's work_activities gists), which the
brain then hands to OpenClaw in push mode: OpenClaw only creates a new Feishu
doc and writes the prepared content, it does not gather anything itself.
"""

from __future__ import annotations

import re
import time
from typing import Any

TRIGGER_KEYWORDS = (
    "汇总屏幕",
    "屏幕使用时间",
    "屏幕使用记录",
    "屏幕使用情况",
    "屏幕报告",
    "屏幕使用报告",
)

USAGE_SUMMARY_EVENT_TYPE = "screen.usage_summary"


def _fmt_dur(seconds: float | int | None) -> str:
    total = int(seconds or 0)
    h, rem = divmod(total, 3600)
    m = rem // 60
    if h:
        return f"{h}小时{m:02d}分"
    if m:
        return f"{m}分钟"
    return f"{total}秒"


def _start_of_today_ms() -> int:
    lt = time.localtime()
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return int(midnight * 1000)


class ScreenReportSkill:
    name = "screen_report"

    def __init__(self, memory_store: Any):
        self.memory_store = memory_store

    @staticmethod
    def matches(text: str | None) -> bool:
        normalized = re.sub(r"\s+", "", str(text or "").lower())
        return any(keyword in normalized for keyword in TRIGGER_KEYWORDS)

    def build_report(self) -> dict[str, Any]:
        """Assemble the report content. Never raises: missing data sources just
        degrade the report, so the voice flow always gets something to send."""
        usage = self._latest_usage_summary()
        activities = self._today_activities()
        today = time.strftime("%Y-%m-%d")
        title = f"屏幕使用报告 {today}"

        lines: list[str] = [f"# {title}", ""]

        if usage:
            generated_ms = usage.get("generated_at_ms")
            if generated_ms:
                lines.append(
                    f"数据截至 {time.strftime('%H:%M', time.localtime(int(generated_ms) / 1000))}"
                )
                lines.append("")
            lines.append("## 总览")
            lines.append(f"- 活跃时长：{_fmt_dur(usage.get('active_seconds'))}")
            lines.append(f"- 离开时长：{_fmt_dur(usage.get('away_seconds'))}")
            lines.append(
                f"- 最长连续专注：{_fmt_dur(usage.get('longest_session_seconds'))}"
            )
            lines.append(f"- 窗口切换次数：{usage.get('session_count', 0)}")
            lines.append(f"- 敲键次数：{usage.get('total_keys', 0)}")
            lines.append("")
            by_app = usage.get("by_app") or []
            if by_app:
                lines.append("## 应用分布")
                for item in by_app:
                    lines.append(
                        f"- {item.get('app', 'unknown')}：{_fmt_dur(item.get('seconds'))}"
                    )
                lines.append("")
            by_category = usage.get("by_category") or []
            if by_category:
                lines.append("## 类别分布")
                for item in by_category:
                    lines.append(
                        f"- {item.get('category', 'other')}：{_fmt_dur(item.get('seconds'))}"
                    )
                lines.append("")
            by_domain = usage.get("by_domain") or []
            if by_domain:
                lines.append("## 主要网站")
                for item in by_domain:
                    lines.append(
                        f"- {item.get('domain', '-')}：{_fmt_dur(item.get('seconds'))}"
                    )
                lines.append("")
        else:
            lines.append("_今天还没有收到 PC 端的使用时长汇总（tracker 未运行或未配置 board_base_url）。_")
            lines.append("")

        if activities:
            lines.append(f"## 今天做了 {len(activities)} 件事")
            for row in activities:
                gist = row.get("note") or row.get("project_hint") or row.get("activity_type") or ""
                app_name = row.get("app_name") or "-"
                dur = row.get("duration_seconds")
                dur_text = f"，{_fmt_dur(dur)}" if dur else ""
                lines.append(f"- {gist}（{app_name}{dur_text}）")
            lines.append("")

        return {
            "title": title,
            "markdown": "\n".join(lines).rstrip() + "\n",
            "has_usage": bool(usage),
            "activity_count": len(activities),
        }

    def _latest_usage_summary(self) -> dict[str, Any]:
        try:
            events = self.memory_store.query_recent_events(
                limit=1,
                event_type=USAGE_SUMMARY_EVENT_TYPE,
            )
        except Exception:
            return {}
        if not events:
            return {}
        payload = events[0].get("payload")
        return payload if isinstance(payload, dict) else {}

    def _today_activities(self) -> list[dict[str, Any]]:
        try:
            rows = self.memory_store.query_recent_work_activities(limit=50)
        except Exception:
            return []
        since = _start_of_today_ms()
        today_rows = [
            row for row in rows
            if isinstance(row.get("timestamp_ms"), (int, float))
            and int(row["timestamp_ms"]) >= since
        ]
        return today_rows[:15]
