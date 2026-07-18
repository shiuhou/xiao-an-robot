"""Deterministic local fast-path routing before OpenClaw escalation."""

from __future__ import annotations

import inspect
from pathlib import Path
import re
from typing import Any

from agent.core.runtime_workspace_docs import RuntimeWorkspaceDocs, clean_capture_title
from base_station.integration_console.fast_demo_brain import (
    EXPRESSION_ALIASES,
    match_requested_expression,
    parse_reminder_due_at,
)


OPENCLAW_OWNED_KEYWORDS = (
    "天气",
    "下雨",
    "多少度",
    "气温",
    "笔记",
    "记笔记",
    "查笔记",
    "notes",
    "note",
)


class LocalFastPathRouter:
    """Handle only high-confidence, no-memory, no-network requests locally."""

    def __init__(self, docs: RuntimeWorkspaceDocs | None = None):
        self.docs = docs or RuntimeWorkspaceDocs()

    async def try_handle_asr(
        self,
        *,
        text: str | None,
        payload: dict[str, Any] | None = None,
        run_id: str,
        robot_motion: Any = None,
    ) -> dict[str, Any]:
        transcript = str(text or "").strip()
        normalized = _normalize(transcript)
        payload = payload or {}
        if not normalized:
            return self._miss("empty")

        if _has_any(normalized, OPENCLAW_OWNED_KEYWORDS):
            return self._miss("openclaw_owned_intent")

        robot_result = await self._try_robot_fast_path(
            normalized,
            transcript=transcript,
            run_id=run_id,
            robot_motion=robot_motion,
        )
        if robot_result.get("handled"):
            return robot_result

        work_result = self._try_work_fast_path(
            normalized,
            transcript=transcript,
            run_id=run_id,
            payload=payload,
        )
        if work_result.get("handled"):
            return work_result

        return self._miss("no_fast_path_match")

    def classify_chain(self, text: str | None) -> str:
        normalized = _normalize(text or "")
        if self._looks_like_robot_fast_path(normalized):
            return "link3"
        return "link1"

    async def _try_robot_fast_path(
        self,
        normalized: str,
        *,
        transcript: str,
        run_id: str,
        robot_motion: Any,
    ) -> dict[str, Any]:
        if not self._looks_like_robot_fast_path(normalized):
            return self._miss("not_robot_fast_path")

        if _is_greeting(normalized):
            return self._handled(
                route="local_fast_path.link3.greeting",
                intent="greeting",
                reply="我在。工作模式已经准备好，你可以直接说任务、提醒或者机器人动作。",
                run_id=run_id,
                confidence=0.94,
                actions=[],
                storage=[],
                extra={"transcript": transcript},
            )

        if _is_breathing_guide(normalized):
            return self._handled(
                route="local_fast_path.link3.breathing_guide",
                intent="breathing_guide",
                reply="好，我们来一轮简单呼吸。吸气四秒，停一秒，呼气六秒。再来一次，慢慢吸气，停住，慢慢呼出去。",
                run_id=run_id,
                confidence=0.9,
                actions=[],
                storage=[],
                extra={"transcript": transcript},
            )

        if _is_robot_status_query(normalized):
            gateway = getattr(robot_motion, "gateway", None)
            gateway_url = getattr(gateway, "url", None)
            return self._handled(
                route="local_fast_path.link3.robot_status",
                intent="robot_status_query",
                reply="我能看到本地机器人通道配置，但当前没有从机器人心跳里拿到电量或 Dock 状态。接上机器人后这里会显示真实状态。",
                run_id=run_id,
                confidence=0.86,
                actions=[],
                storage=[],
                extra={
                    "transcript": transcript,
                    "robot_status": {
                        "gateway_url": gateway_url,
                        "connected": False,
                        "battery": None,
                        "dock": None,
                        "work_state": "unknown_without_robot_heartbeat",
                    },
                },
            )

        if robot_motion is None:
            return self._handled(
                route="local_fast_path.link3.robot",
                intent="robot_unavailable",
                reply="我识别到机器人动作指令了，但本地机器人通道还没接上。",
                run_id=run_id,
                confidence=0.7,
                actions=[],
                storage=[],
                extra={"error": "robot_motion_unavailable"},
            )

        actions: list[dict[str, Any]] = []
        reply = "收到。"
        intent = "robot_action"
        try:
            if _has_any(normalized, _ROBOT_STOP_KEYWORDS):
                result = await _call(robot_motion.run, "stop", {})
                actions.append(_action("motion.stop", result))
                reply = "好，我停下。"
                intent = "stop_motion"
            elif _has_any(normalized, _ROBOT_RETURN_KEYWORDS):
                result = await _call(robot_motion.return_to_dock, speed=0.54, timeout_ms=1200)
                actions.append(_action("xiaoan.robot.return_to_dock", result))
                reply = "好，我回去待命。"
                intent = "return_to_dock"
            elif _has_any(normalized, _ROBOT_TURN_LEFT_KEYWORDS):
                result = await _call(robot_motion.turn, direction="left", angle_deg=_angle_or_default(normalized))
                actions.append(_action("xiaoan.robot.turn", result))
                reply = "好，向左转。"
                intent = "turn_left"
            elif _has_any(normalized, _ROBOT_TURN_RIGHT_KEYWORDS):
                result = await _call(robot_motion.turn, direction="right", angle_deg=_angle_or_default(normalized))
                actions.append(_action("xiaoan.robot.turn", result))
                reply = "好，向右转。"
                intent = "turn_right"
            else:
                expression = _requested_expression(normalized)
                if expression is not None:
                    result = await _call(robot_motion.show_expression, expression, duration_ms=1500, loop=False)
                    actions.append(_action("xiaoan.robot.expression", result))
                    reply = f"好，表情换成 {expression}。"
                    intent = "set_expression"
                elif _has_any(normalized, _ROBOT_MOVE_OUT_KEYWORDS):
                    result = await _call(robot_motion.move_out_of_dock, speed=1.0, distance_cm=8.0, timeout_ms=1200)
                    actions.append(_action("xiaoan.robot.move_out", result))
                    reply = "好，我出来一点。"
                    intent = "move_out"
                else:
                    return self._miss("robot_fast_path_unclear")
        except Exception as exc:
            return self._handled(
                route=f"local_fast_path.link3.{intent}",
                intent=intent,
                reply=f"动作指令收到了，但机器人执行失败：{exc}",
                run_id=run_id,
                confidence=0.88,
                actions=actions,
                storage=[],
                extra={"ok": False, "error": str(exc)},
            )

        return self._handled(
            route=f"local_fast_path.link3.{intent}",
            intent=intent,
            reply=reply,
            run_id=run_id,
            confidence=0.92,
            actions=actions,
            storage=[],
            extra={"transcript": transcript},
        )

    def _try_work_fast_path(
        self,
        normalized: str,
        *,
        transcript: str,
        run_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        del payload
        if _has_any(normalized, _TASK_QUERY_KEYWORDS):
            items = self.docs.today_tasks()
            reply = "当前没有待办。" if not items else "当前待办：" + "；".join(items[:5])
            return self._handled("local_fast_path.link1.task_query", "task_query", reply, run_id, 0.88, [], [])

        if _has_any(normalized, _TASK_COMPLETE_KEYWORDS):
            title = _match_title(transcript, kind="task")
            if not title:
                return self._miss("task_match_unclear")
            write = self.docs.complete_task(title, transcript=transcript, run_id=run_id)
            if not write.ok:
                return self._miss(f"task_complete_{write.error or 'failed'}")
            return self._handled(
                "local_fast_path.link1.task_complete",
                "task_complete",
                f"好，待办已完成：{write.title}。",
                run_id,
                0.86,
                [],
                [write.__dict__],
            )

        if _has_any(normalized, _TASK_CANCEL_KEYWORDS):
            title = _match_title(transcript, kind="task")
            if not title:
                return self._miss("task_match_unclear")
            write = self.docs.cancel_task(title, transcript=transcript, run_id=run_id)
            if not write.ok:
                return self._miss(f"task_cancel_{write.error or 'failed'}")
            return self._handled(
                "local_fast_path.link1.task_cancel",
                "task_cancel",
                f"好，待办已取消：{write.title}。",
                run_id,
                0.84,
                [],
                [write.__dict__],
            )

        if _has_any(normalized, _REMINDER_QUERY_KEYWORDS):
            items = self.docs.pending_reminders()
            reply = "当前没有待触发提醒。" if not items else "当前提醒：" + "；".join(items[:5])
            return self._handled("local_fast_path.link1.reminder_query", "reminder_query", reply, run_id, 0.88, [], [])

        if _is_cancel_reminder(normalized):
            title = _match_title(transcript, kind="reminder")
            if not title:
                return self._miss("reminder_match_unclear")
            write = self.docs.cancel_reminder(title, transcript=transcript, run_id=run_id)
            if not write.ok:
                return self._miss(f"reminder_cancel_{write.error or 'failed'}")
            return self._handled(
                "local_fast_path.link1.reminder_cancel",
                "reminder_cancel",
                f"好，提醒已取消：{write.title}。",
                run_id,
                0.84,
                [],
                [write.__dict__],
            )

        if _looks_like_reminder_add(normalized):
            reminder = _parse_due_at(transcript)
            if not _explicit_time(reminder):
                return self._miss("reminder_time_unclear")
            title = clean_capture_title(transcript, kind="reminder")
            index_write = self.docs.add_schedule(
                title,
                transcript=transcript,
                run_id=run_id,
                due_at=str(reminder.get("due_at") or ""),
                kind="reminder",
            )
            reminder_write = self.docs.add_local_reminder(
                title,
                transcript=transcript,
                run_id=run_id,
                due_at=str(reminder.get("due_at") or ""),
            )
            return self._handled(
                "local_fast_path.link1.reminder_add",
                "reminder_add",
                f"好，{reminder.get('time_text') or '到点'}提醒你{title}。",
                run_id,
                0.9,
                [],
                [index_write.__dict__, reminder_write.__dict__],
                {"reminder": reminder},
            )

        if _looks_like_schedule_add(normalized):
            schedule = _parse_due_at(transcript)
            if not _explicit_time(schedule):
                return self._miss("schedule_time_unclear")
            title = clean_capture_title(transcript, kind="schedule")
            write = self.docs.add_schedule(
                title,
                transcript=transcript,
                run_id=run_id,
                due_at=str(schedule.get("due_at") or ""),
                kind="schedule",
            )
            return self._handled(
                "local_fast_path.link1.schedule_add",
                "schedule_add",
                f"好，我把{title}加入日程。",
                run_id,
                0.88,
                [],
                [write.__dict__],
                {"schedule": schedule},
            )

        if _has_any(normalized, _TASK_ADD_KEYWORDS) and not _has_any(normalized, _QUERY_HINT_KEYWORDS):
            title = clean_capture_title(transcript, kind="task")
            write = self.docs.add_task(title, transcript=transcript, run_id=run_id)
            return self._handled(
                "local_fast_path.link1.task_add",
                "task_add",
                f"好，待办我加上：{title}。",
                run_id,
                0.86,
                [],
                [write.__dict__],
            )

        return self._miss("not_work_fast_path")

    def _looks_like_robot_fast_path(self, normalized: str) -> bool:
        if _has_any(normalized, _ROBOT_ACTION_HINT_KEYWORDS):
            return True
        if _is_greeting(normalized) or _is_breathing_guide(normalized) or _is_robot_status_query(normalized):
            return True
        if _requested_expression(normalized) is not None:
            return True
        return any(alias in normalized for aliases in EXPRESSION_ALIASES.values() for alias in aliases)

    def _handled(
        self,
        route: str,
        intent: str,
        reply: str,
        run_id: str,
        confidence: float,
        actions: list[dict[str, Any]],
        storage: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "handled": True,
            "route": route,
            "reason": "local_fast_path",
            "intent": intent,
            "confidence": confidence,
            "display_text": reply,
            "spoken_text": reply,
            "reply_text": reply,
            "suppress_auto_tts": False,
            "executed_actions": actions,
            "skipped_actions": [],
            "storage": storage,
            "run_id": run_id,
        }
        if extra:
            result.update(extra)
        dashboard_write = self.docs.update_dashboard_snapshot(
            run_id=run_id,
            route=route,
            intent=intent,
            transcript=str((extra or {}).get("transcript") or ""),
            reply=reply,
            storage=storage,
            actions=actions,
        )
        result["storage"] = [*storage, dashboard_write.__dict__]
        return result

    @staticmethod
    def _miss(reason: str) -> dict[str, Any]:
        return {"handled": False, "reason": reason}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _explicit_time(parsed: dict[str, Any]) -> bool:
    try:
        confidence = float(parsed.get("time_parse_confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return confidence >= 0.5 and str(parsed.get("time_text") or "") != "默认1分钟后" and bool(parsed.get("due_at"))


_ROBOT_RETURN_KEYWORDS = (
    "回dock",
    "回到dock",
    "回去dock",
    "回去",
    "回家",
    "回窝",
    "回充电",
    "回到充电",
    "回去充电",
    "回充电座",
    "回到充电座",
    "充电座",
    "充电桩",
    "充电底座",
    "底座",
    "返回基站",
    "回基站",
    "回到基站",
    "返回底座",
    "回去待命",
    "回去休息",
)
_ROBOT_TURN_LEFT_KEYWORDS = ("左转", "向左", "往左", "转左", "左边转", "向左转", "往左转", "转向左边", "左转一点")
_ROBOT_TURN_RIGHT_KEYWORDS = ("右转", "向右", "往右", "转右", "右边转", "向右转", "往右转", "转向右边", "右转一点")
_ROBOT_STOP_KEYWORDS = (
    "停",
    "停止",
    "停一下",
    "暂停",
    "别动",
    "不要动",
    "别走",
    "先停",
    "刹车",
    "stop",
)
_ROBOT_MOVE_OUT_KEYWORDS = (
    "出来",
    "出来一下",
    "出来一点",
    "走出来",
    "出dock",
    "离开dock",
    "离开充电座",
    "过来",
    "过来一下",
    "靠近",
    "靠近我",
    "到我这边",
)
_ROBOT_ACTION_HINT_KEYWORDS = (
    *_ROBOT_STOP_KEYWORDS,
    *_ROBOT_MOVE_OUT_KEYWORDS,
    *_ROBOT_RETURN_KEYWORDS,
    *_ROBOT_TURN_LEFT_KEYWORDS,
    *_ROBOT_TURN_RIGHT_KEYWORDS,
)
_TASK_QUERY_KEYWORDS = (
    "今天待办",
    "待办有哪些",
    "任务有哪些",
    "todo有哪些",
    "查待办",
    "查询待办",
    "看一下待办",
    "看看待办",
    "看待办",
    "看看任务",
    "看一下任务",
    "待办列表",
    "任务列表",
    "todo列表",
    "我的待办",
    "我的任务",
    "还有什么待办",
    "还有哪些待办",
    "今天有什么待办",
    "今天有什么任务",
)
_TASK_COMPLETE_KEYWORDS = (
    "完成待办",
    "完成任务",
    "办完",
    "已完成",
    "做完",
    "搞定了",
    "标记完成",
    "设为完成",
    "打勾",
    "划掉",
)
_TASK_CANCEL_KEYWORDS = (
    "取消待办",
    "取消任务",
    "删除待办",
    "删除任务",
    "删掉待办",
    "删掉任务",
    "移除待办",
    "移除任务",
    "不用做了",
)
_REMINDER_QUERY_KEYWORDS = (
    "查询提醒",
    "查提醒",
    "有什么提醒",
    "提醒有哪些",
    "我的提醒",
    "看看提醒",
    "看一下提醒",
    "提醒列表",
    "待触发提醒",
    "还有什么提醒",
    "还有哪些提醒",
)
_TASK_ADD_KEYWORDS = (
    "待办",
    "任务",
    "todo",
    "to-do",
    "加个事",
    "记个任务",
)
_QUERY_HINT_KEYWORDS = ("查询", "查", "看看", "看一下", "哪些", "有什么", "列表")


def _angle_or_default(text: str) -> float:
    match = re.search(r"(\d{1,3})度", text)
    if not match:
        return 25.0
    return min(45.0, max(1.0, float(match.group(1))))


def _is_greeting(text: str) -> bool:
    return text in {"你好", "嗨", "hi", "hello", "小安在吗", "小安你好", "小安", "在吗", "喂小安"} or _has_any(
        text,
        (
            "小安在吗",
            "小安你在吗",
            "小安在不在",
            "你好小安",
            "小安你好",
            "能听到我吗",
            "听得到我吗",
            "听得见我吗",
            "听见我吗",
            "听得到吗",
            "听得见吗",
            "你在吗",
            "在不在",
            "在线吗",
            "还在线吗",
            "收到请回答",
            "能不能听到",
            "你醒着吗",
        ),
    )


def _is_breathing_guide(text: str) -> bool:
    return _has_any(
        text,
        (
            "呼吸引导",
            "带我呼吸",
            "陪我呼吸",
            "做个呼吸",
            "呼吸练习",
            "深呼吸",
            "带我放松",
            "陪我放松",
            "放松一下",
            "缓一缓",
            "冷静一下",
        ),
    )


def _is_robot_status_query(text: str) -> bool:
    return _has_any(
        text,
        (
            "机器人状态",
            "你的状态",
            "小安状态",
            "电量",
            "电池",
            "剩余电量",
            "有电吗",
            "连接状态",
            "连上了吗",
            "机器人连上了吗",
            "在线状态",
            "在dock",
            "在基站",
            "在充电座",
            "工作状态",
        ),
    )


def _is_cancel_reminder(text: str) -> bool:
    return _has_any(text, ("取消提醒", "删除提醒", "删掉提醒", "关掉提醒", "取消闹钟", "删除闹钟", "关掉闹钟")) or (
        _has_any(text, ("取消", "删除", "删掉", "关掉", "不用")) and _has_any(text, ("提醒", "闹钟"))
    )


def _requested_expression(text: str) -> str | None:
    expression = match_requested_expression(text)
    if expression is not None:
        return expression
    if _has_any(text, ("笑一个", "笑一下", "笑笑", "笑脸", "开心一点", "高兴一点", "快乐一点")):
        return "happy"
    return None


def _looks_like_reminder_add(text: str) -> bool:
    return _has_any(
        text,
        (
            "提醒",
            "提醒我",
            "帮我提醒",
            "记得提醒",
            "设个提醒",
            "设置提醒",
            "待会",
            "等会",
            "过会",
            "秒后",
            "秒钟后",
            "分钟后",
            "小时后",
            "之后",
            "以后",
            "闹钟",
            "设个闹钟",
            "定个闹钟",
            "设置闹钟",
            "到点",
            "到时候",
            "到时",
            "叫我",
            "喊我",
            "叫一下我",
            "喊一下我",
            "叫醒我",
            "通知我",
        ),
    )


def _looks_like_schedule_add(text: str) -> bool:
    return _has_any(
        text,
        (
            "加入日程",
            "加到日程",
            "添加日程",
            "新增日程",
            "记到日程",
            "放进日程",
            "写进日程",
            "日程里",
            "日历",
            "行程",
            "schedule",
            "calendar",
        ),
    ) or (
        _has_any(text, ("安排", "会议", "开会", "约个会", "排个会")) and _explicit_time(_parse_due_at(text))
    )


def _parse_due_at(transcript: str) -> dict[str, Any]:
    parsed = parse_reminder_due_at(transcript)
    if _explicit_time(parsed):
        return parsed
    normalized = _normalize_relative_time_text(transcript)
    if normalized == transcript:
        return parsed
    reparsed = parse_reminder_due_at(normalized)
    return reparsed if _explicit_time(reparsed) else parsed


def _normalize_relative_time_text(text: str) -> str:
    value = str(text or "")
    amount = r"([0-9]+|[一二两三四五六七八九十]+)"
    unit = r"(秒钟?|分钟?|小时|钟头)"
    value = re.sub(amount + unit + r"(之后|以后)", r"\1\2后", value)
    value = re.sub(r"过" + amount + unit, r"\1\2后", value)
    return value


def _match_title(text: str, *, kind: str) -> str:
    value = clean_capture_title(text, kind=kind).strip()
    for token in (
        "完成",
        "取消",
        "删除",
        "删掉",
        "查询",
        "查一下",
        "查",
        "已完成",
        "做完",
        "办完",
        "搞定了",
        "标记完成",
        "设为完成",
        "打勾",
        "划掉",
        "移除",
        "不用做了",
    ):
        value = value.replace(token, "")
    return value.strip(" ，。,.：:;；")


def _action(name: str, result: Any) -> dict[str, Any]:
    return {
        "name": name,
        "source": "local_fast_path",
        "result": result if isinstance(result, dict) else {"value": result},
    }


async def _call(function: Any, *args: Any, **kwargs: Any) -> Any:
    result = function(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result
