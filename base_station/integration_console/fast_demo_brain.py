"""Local deterministic decisions for Integration Console Fast Demo Mode."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from base_station.integration_console.story_demo import iter_story_demo_tts_texts

from agent.core.gateway import RobotGateway, RobotGatewayError


PUBLIC_LABEL = "智能大脑回复"
DECISION_SOURCE = "local_demo_brain"
SCHEMA_VERSION = "xiaoan.fast_demo_decision.v1"
VOICE_LINKS = {"fast1", "fast3"}
REMINDER_SCHEMA_VERSION = "xiaoan.fast_demo_reminder.v1"
POST_MOTION_TTS_SETTLE_SECONDS = 0.35
OPENCLAW_DASHBOARD_SCHEMA = "xiaoan.dashboard.v1"
DEFAULT_OPENCLAW_DASHBOARD_PATH = Path.home() / ".openclaw" / "workspace-xiaoan-runtime" / "state" / "dashboard.json"
SUPPORTED_EXPRESSIONS = ("happy", "caring", "tired", "thinking", "speaking", "idle", "sad", "surprised", "sleeping")
EXPRESSION_ALIASES = {
    "happy": ("开心", "高兴", "快乐", "微笑", "笑脸", "开心脸", "开心表情", "高兴表情", "happy"),
    "caring": ("关心", "关怀", "照顾", "陪伴", "温柔", "关心表情", "关怀表情", "caring"),
    "tired": ("疲惫", "累", "困", "疲劳", "困倦", "累脸", "疲惫表情", "tired"),
    "thinking": ("思考", "思考中", "想一想", "想想", "认真", "思考表情", "thinking", "listening"),
    "speaking": ("说话", "讲话", "播报", "发言", "说话表情", "speaking"),
    "idle": ("待机", "待命", "普通", "默认", "平静", "中性", "空闲", "idle", "neutral"),
    "sad": ("难过", "伤心", "悲伤", "委屈", "低落", "sad"),
    "surprised": ("惊讶", "吃惊", "惊喜", "震惊", "surprised", "error"),
    "sleeping": ("睡觉", "睡眠", "睡着", "休眠", "睡觉表情", "sleeping"),
}
EXPRESSION_COMMAND_MARKERS = (
    "表情",
    "脸",
    "切换",
    "换成",
    "换到",
    "变成",
    "显示",
    "做个",
    "做一个",
    "来个",
    "装作",
    "假装",
    "演一下",
    "表演",
)

LINK1_REPLIES = {
    "capture_schedule": (
        "日程我加上啦，到时候你看屏幕就能看到。",
        "收到，这个安排我放到今天日程里。",
        "好的，我把这件事排进日程。",
    ),
    "capture_reminder": (
        "我记好啦。到点我会带着小提醒出来找你。",
        "提醒已经收进小安的小闹钟啦，时间一到我就冒出来。",
        "好的，这件事先交给我，你不用一直挂在脑子里。",
    ),
    "capture_meeting": (
        "会议信息我先收好，重点我会帮你稳稳放住。",
        "收到，这是会议相关内容，我先帮你归到会议小格子里。",
        "会议笔记我记下啦，等会儿你继续说重点就好。",
    ),
    "capture_task": (
        "待办我收下啦，你先不用一直挂在脑子里。",
        "任务已加入小安清单，我会帮你盯住它。",
        "好的，这件事我先帮你放进待处理队列。",
    ),
    "capture_note": (
        "我先帮你记一下，小安的小本本已经翻开啦。",
        "收到，我把这句话先保存起来。",
        "这条笔记我记下啦，之后可以慢慢把它长成方案。",
    ),
    "capture_preference": (
        "我记住啦，你喜欢科幻故事。",
    ),
    "recall_preference": (
        "你喜欢科幻故事，所以我下次可以给你讲星际探险。",
    ),
    "recall_identity": (
        "我知道你是小安项目的负责人，正在带我准备今天的演示。",
    ),
    "recall_current_work": (
        "你最近正在准备小安机器人的成品演示，我会帮你把提醒、日程和互动环节稳稳记住。",
    ),
    "recall_demo_goal": (
        "你希望我展示语音记忆、主动提醒、视觉关怀和具身陪伴能力。",
    ),
    "no_speech": (
        "我刚刚没听清。你再叫我一声，我会竖起小耳朵认真听。",
        "好像有点太轻啦，再说一次，我把耳朵竖起来。",
        "我没抓到内容，我们再来一遍就好。",
    ),
    "reminder_due": (
        "到点啦，我出来提醒你：该处理刚才那件事啦。",
        "小安提醒时间到。先停一下，我们把这件事捡起来。",
        "你交给我的提醒到时间啦，我来乖乖报到。",
    ),
}

LINK2_REPLIES = {
    "visual_care": (
        "我看到你有点累啦。先眨眨眼，肩膀放下来，我陪你休息一分钟。",
        "你现在看起来有点疲惫。我们先把节奏放慢一点，我陪你缓一缓。",
        "小安检测到你可能累了。先喝口水，眼睛离屏幕远一点点。",
    ),
    "visual_uncertain": (
        "我这边还没看清你。你可以稍微靠近一点点，等我看清了再乖乖判断。",
        "画面有点不稳定，我先不乱判断。你调整一下位置，我再认真看。",
        "我好像没抓到清楚的人脸，先等等，我不急着打扰你。",
    ),
    "visual_normal": (
        "我看你状态还挺稳的。小安在线巡逻中，有需要我就马上冒出来。",
        "目前看起来还不错，我会继续安静陪跑。",
        "状态稳定，小安先乖乖待命，需要我时喊一声就好。",
    ),
}

LINK3_REPLIES = {
    "set_expression": (
        "好，表情换好啦。",
        "收到，我换个表情。",
        "可以，我现在切过去。",
    ),
    "companion_care": (
        "我来啦。你先别硬撑，肩膀松一点，我陪你待一会儿。",
        "听起来你需要缓一缓。小安出来陪你，我们先慢慢呼一口气。",
        "好，我靠近一点。你不用马上变好，我先陪你安静一下。",
    ),
    "greeting": (
        "我在呀。你一叫我，我的小灯就亮起来了。",
        "在呢在呢，小安收到召唤。",
        "嗨，我在这里。今天也准备好陪你一起工作啦。",
    ),
    "status_intro": (
        "我现在电量 87%，网络正常，今天已经准备好陪你开始工作。",
    ),
    "stop_motion": (
        "好，我停下啦。你一句话，我就乖乖刹住。",
        "收到，马上停住。",
        "我停好啦，先不动。",
    ),
    "return_to_dock": (
        "收到，我准备回去啦。走之前也会轻轻跟你说一声。",
        "好，我回窝啦，有事再叫我。",
        "明白，我先回去待命。",
    ),
    "gentle_ack": (
        "我听到啦。你慢慢说，我就在旁边陪着。",
        "收到，小安先帮你稳稳接住这句话。",
        "嗯嗯，我在听，你可以继续说。",
    ),
}

EXPRESSION_PERFORMANCE_REPLIES = {
    "happy": "嘿嘿，我现在是开心模式，准备把气氛点亮一点。",
    "caring": "我切到关心模式啦。你慢慢来，我会温柔一点陪着你。",
    "tired": "我现在装作有点困，眼睛都快要自动进入省电模式啦。",
    "thinking": "我进入思考模式。让我认真想一想，再给你一个稳妥答案。",
    "speaking": "我切到说话模式啦。现在轮到小安认真播报。",
    "idle": "我回到待命表情啦。安静在线，有事你叫我。",
    "sad": "我现在是难过表情。没关系，我会慢慢把情绪接住。",
    "surprised": "哇，我现在很惊讶。这个反应够明显了吗？",
    "sleeping": "我进入睡觉表情啦。呼，小安先假装休眠三秒钟。",
}


FAST_DEMO_REPLY_TABLES = {
    "fast1": LINK1_REPLIES,
    "fast2": LINK2_REPLIES,
    "fast3": LINK3_REPLIES,
}


def iter_fast_demo_tts_texts(*, include_visual_normal: bool = True) -> list[dict[str, str]]:
    """Return every deterministic Fast Demo sentence that may need local TTS."""

    items: list[dict[str, str]] = []
    for link, table in FAST_DEMO_REPLY_TABLES.items():
        for intent, replies in table.items():
            if not include_visual_normal and link == "fast2" and intent == "visual_normal":
                continue
            for index, text in enumerate(replies):
                items.append({
                    "link": link,
                    "intent": intent,
                    "variant": str(index),
                    "text": text,
                })
    for expression, text in EXPRESSION_PERFORMANCE_REPLIES.items():
        items.append({
            "link": "fast3",
            "intent": "set_expression",
            "variant": expression,
            "text": text,
        })
    items.extend(iter_story_demo_tts_texts())
    return items


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def decide_voice(link: str, transcript: str) -> dict[str, Any]:
    if link == "fast1":
        return _decide_link1(transcript)
    if link == "fast3":
        return _decide_link3(transcript)
    raise ValueError(f"unsupported_fast_demo_voice_link:{link}")


def build_fast_demo_voice_output(transcript: str, event: dict[str, Any], *, link: str) -> dict[str, Any]:
    decision = decide_voice(link, transcript)
    return {
        "text": transcript,
        "event_type": event.get("type") or "asr.transcript",
        "event": event,
        "handled": bool(decision.get("handled", True)),
        "route": f"fast_demo.{link}",
        "reason": decision.get("reason"),
        "display_text": decision.get("display_text"),
        "spoken_text": decision.get("spoken_text"),
        "reply_text": decision.get("reply_text"),
        "public_label": PUBLIC_LABEL,
        "fast_demo_decision": decision,
    }


def parse_reminder_due_at(transcript: str, *, now: datetime | None = None) -> dict[str, Any]:
    base = now or datetime.now().astimezone()
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    text = normalize_text(transcript)

    if "半小时后" in text:
        return _reminder_parse_result(base + timedelta(minutes=30), base, "半小时后", 0.86)

    relative = re.search(r"([0-9]+|[一二两三四五六七八九十]+)(秒钟?|分钟?|小时|钟头)后", text)
    if relative:
        amount = _parse_cn_number(relative.group(1))
        unit = relative.group(2)
        if amount is not None and amount > 0:
            if unit.startswith("秒"):
                due = base + timedelta(seconds=amount)
            elif unit.startswith("小时") or unit.startswith("钟头"):
                due = base + timedelta(hours=amount)
            else:
                due = base + timedelta(minutes=amount)
            return _reminder_parse_result(due, base, relative.group(0), 0.9)

    absolute = re.search(r"(今天|明天)?(上午|早上|下午|晚上|中午)?([0-9]{1,2}|[一二两三四五六七八九十]{1,3})点(半|([0-9]{1,2}|[一二两三四五六七八九十]{1,3})分?)?", text)
    if absolute:
        day_word = absolute.group(1) or ""
        meridiem = absolute.group(2) or ""
        hour = _parse_cn_number(absolute.group(3))
        if hour is not None:
            minute = 30 if absolute.group(4) == "半" else (_parse_cn_number(absolute.group(5)) if absolute.group(5) else 0)
            if 0 <= minute <= 59:
                if meridiem in {"下午", "晚上"} and hour < 12:
                    hour += 12
                elif meridiem == "中午" and hour < 11:
                    hour += 12
                if 0 <= hour <= 23:
                    due_date = base.date() + timedelta(days=1 if day_word == "明天" else 0)
                    due = datetime.combine(due_date, datetime.min.time(), tzinfo=base.tzinfo).replace(hour=hour, minute=minute)
                    if day_word != "明天" and due <= base:
                        due += timedelta(days=1)
                    return _reminder_parse_result(due, base, absolute.group(0), 0.82)

    return _reminder_parse_result(base + timedelta(minutes=1), base, "默认1分钟后", 0.35)


def build_reminder_record(
    decision: dict[str, Any],
    *,
    transcript: str,
    send_to_robot: bool,
    allow_motion: bool,
    gateway_url: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if decision.get("intent") != "capture_reminder":
        return None
    trigger = decision.get("trigger") if isinstance(decision.get("trigger"), dict) else {}
    reminder = trigger.get("reminder") if isinstance(trigger.get("reminder"), dict) else {}
    due_at = str(reminder.get("due_at") or "").strip()
    if not due_at:
        return None
    created_at = (now or datetime.now().astimezone()).isoformat()
    digest = hashlib.sha1(f"{created_at}|{transcript}|{due_at}".encode("utf-8")).hexdigest()[:12]
    return {
        "schema_version": REMINDER_SCHEMA_VERSION,
        "id": f"fast-reminder-{digest}",
        "status": "pending",
        "created_at": created_at,
        "due_at": due_at,
        "transcript": transcript,
        "reminder": reminder,
        "send_to_robot": bool(send_to_robot),
        "allow_motion": bool(allow_motion),
        "gateway_url": gateway_url,
        "reply_text": decision.get("reply_text"),
    }


def build_reminder_due_decision(record: dict[str, Any]) -> dict[str, Any]:
    transcript = str(record.get("transcript") or "")
    return _decision(
        link="fast1",
        intent="reminder_due",
        confidence=0.95,
        reason="fast_demo_reminder_due",
        reply=_pick_reply("reminder_due", transcript, LINK1_REPLIES["reminder_due"]),
        expression="speaking",
        motion=True,
        trigger={
            "reminder_id": record.get("id"),
            "due_at": record.get("due_at"),
            "transcript": transcript,
        },
    )


def decide_visual(visual_trace: dict[str, Any] | None) -> dict[str, Any]:
    trace = visual_trace if isinstance(visual_trace, dict) else {}
    observation = trace.get("observation") if isinstance(trace.get("observation"), dict) else {}
    cv = trace.get("cv_sample") if isinstance(trace.get("cv_sample"), dict) else {}
    gate = trace.get("gate") if isinstance(trace.get("gate"), dict) else {}
    gate_result = gate.get("result") if isinstance(gate.get("result"), dict) else {}
    vlm = trace.get("vlm") if isinstance(trace.get("vlm"), dict) else {}
    vlm_result = vlm.get("result") if isinstance(vlm.get("result"), dict) else {}
    fusion = vlm.get("fusion") if isinstance(vlm.get("fusion"), dict) else {}

    face_detected = bool(observation.get("face_detected", True))
    quality = _as_float(cv.get("observation_quality"), None)
    fatigue_score = _normalized_score(cv.get("fatigue_score"))
    cv_confidence = _normalized_score(cv.get("confidence"))
    emotion = str(cv.get("emotion_tag") or "").strip().lower()
    vlm_label = str(
        vlm_result.get("expression_label")
        or vlm_result.get("emotion_tag")
        or fusion.get("decision")
        or ""
    ).strip().lower()
    should_trigger = bool(gate_result.get("should_trigger"))

    if not face_detected or (quality is not None and quality < 0.35):
        return _decision(
            link="fast2",
            intent="visual_uncertain",
            confidence=0.55,
            reason="visual_quality_low",
            reply=_pick_reply("visual_uncertain", str(trace), LINK2_REPLIES["visual_uncertain"]),
            expression="thinking",
            motion=False,
            trigger={
                "face_detected": face_detected,
                "observation_quality": quality,
                "gate_should_trigger": should_trigger,
                "emotion_tag": emotion,
                "fatigue_score": fatigue_score,
                "vlm_label": vlm_label,
            },
        )

    negative_emotions = {"tired", "sad", "anxious", "stress", "stressed", "angry", "fear", "疲惫", "难过", "焦虑"}
    vlm_tired = any(token in vlm_label for token in ("tired", "fatigue", "sad", "stress", "困", "累", "疲惫", "难过"))
    cv_tired = emotion in negative_emotions and cv_confidence >= 0.6
    fatigue_high = fatigue_score >= 0.72

    if should_trigger or fatigue_high or cv_tired or vlm_tired:
        reasons = []
        if should_trigger:
            reasons.append(str(gate_result.get("reason") or "gate_trigger"))
        if fatigue_high:
            reasons.append("fatigue_high")
        if cv_tired:
            reasons.append(f"cv_{emotion}")
        if vlm_tired:
            reasons.append("vlm_tired_signal")
        return _decision(
            link="fast2",
            intent="visual_care",
            confidence=max(0.72, fatigue_score, cv_confidence),
            reason="+".join(reasons),
            reply=_pick_reply("visual_care", str(trace), LINK2_REPLIES["visual_care"]),
            expression="caring",
            motion=True,
            trigger={
                "face_detected": face_detected,
                "observation_quality": quality,
                "gate_should_trigger": should_trigger,
                "gate_reason": gate_result.get("reason"),
                "emotion_tag": emotion,
                "confidence": cv_confidence,
                "fatigue_score": fatigue_score,
                "vlm_label": vlm_label,
                "vlm_status": vlm.get("status"),
            },
        )

    return _decision(
        link="fast2",
        intent="visual_normal",
        confidence=max(0.62, cv_confidence),
        reason="visual_state_stable",
        reply=_pick_reply("visual_normal", str(trace), LINK2_REPLIES["visual_normal"]),
        expression="happy",
        motion=False,
        trigger={
            "face_detected": face_detected,
            "observation_quality": quality,
            "gate_should_trigger": should_trigger,
            "emotion_tag": emotion,
            "confidence": cv_confidence,
            "fatigue_score": fatigue_score,
            "vlm_label": vlm_label,
        },
    )


async def execute_robot_plan(
    decision: dict[str, Any],
    *,
    gateway_url: str,
    send_to_robot: bool = False,
    allow_motion: bool = False,
) -> dict[str, Any]:
    plan = decision.get("robot_plan") if isinstance(decision.get("robot_plan"), dict) else {}
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    executed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if not send_to_robot:
        return {
            "ok": True,
            "send_to_robot": False,
            "allow_motion": allow_motion,
            "executed_actions": executed,
            "skipped_actions": [{"kind": step.get("kind"), "reason": "send_to_robot_disabled"} for step in steps],
        }

    gateway = RobotGateway(gateway_url)
    for step in steps:
        if not isinstance(step, dict):
            continue
        kind = str(step.get("kind") or "")
        if kind == "motion" and not allow_motion:
            skipped.append({"kind": kind, "action": step.get("action"), "reason": "motion_disabled"})
            continue
        try:
            ack = await _execute_step(gateway, step)
        except (RobotGatewayError, ValueError) as exc:
            executed.append({
                "kind": kind,
                "action": step.get("action") or step.get("expression") or step.get("sound"),
                "ok": False,
                "error": str(exc),
            })
            continue
        executed.append({
            "kind": kind,
            "action": step.get("action") or step.get("expression") or step.get("sound") or "tts",
            "ok": True,
            "ack": _ack_summary(ack),
        })
        if kind == "motion" and step.get("action") != "stop":
            timeout_seconds = max(0.0, float(step.get("timeout_ms") or 1200) / 1000.0)
            await asyncio.sleep(timeout_seconds + POST_MOTION_TTS_SETTLE_SECONDS)
        if kind in {"local_sound", "tts"}:
            await asyncio.sleep(0.2)

    return {
        "ok": all(item.get("ok") for item in executed) if executed else True,
        "send_to_robot": True,
        "allow_motion": allow_motion,
        "executed_actions": executed,
        "skipped_actions": skipped,
    }


async def _execute_step(gateway: RobotGateway, step: dict[str, Any]) -> dict[str, Any]:
    kind = str(step.get("kind") or "")
    if kind == "expression":
        return await gateway.send_expression(
            str(step.get("expression") or "idle"),
            duration_ms=int(step.get("duration_ms") or 1500),
            loop=bool(step.get("loop", False)),
        )
    if kind == "motion":
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        return await gateway.send_motion(
            str(step.get("action") or "stop"),
            params=params,
            timeout_ms=int(step.get("timeout_ms") or 1200),
        )
    if kind == "tts":
        return await gateway.send_tts(str(step.get("text") or ""))
    if kind == "local_sound":
        return await gateway.send_local_audio(str(step.get("sound") or "success_ding"))
    raise ValueError(f"unsupported_fast_demo_step:{kind}")


def _decide_link1(transcript: str) -> dict[str, Any]:
    text = normalize_text(transcript)
    if not text:
        return _decision(
            link="fast1",
            intent="no_speech",
            confidence=0.2,
            reason="empty_transcript",
            reply=_pick_reply("no_speech", transcript, LINK1_REPLIES["no_speech"]),
            expression="thinking",
            motion=False,
        )
    if _has_any(text, ("我是谁", "知道我是谁", "记得我是谁", "认识我吗")):
        return _decision(
            link="fast1",
            intent="recall_identity",
            confidence=0.92,
            reason="matched_identity_memory_question",
            reply=LINK1_REPLIES["recall_identity"][0],
            expression="speaking",
            motion=False,
            trigger={"transcript": transcript, "memory_key": "identity"},
        )
    if _has_any(text, ("最近在做什么", "正在做什么", "我在做什么", "最近忙什么", "现在在做什么")):
        return _decision(
            link="fast1",
            intent="recall_current_work",
            confidence=0.92,
            reason="matched_current_work_memory_question",
            reply=LINK1_REPLIES["recall_current_work"][0],
            expression="speaking",
            motion=False,
            trigger={"transcript": transcript, "memory_key": "current_work"},
        )
    if _has_any(text, ("我的目标", "演示目标", "展示目标", "想展示什么", "要展示什么")):
        return _decision(
            link="fast1",
            intent="recall_demo_goal",
            confidence=0.9,
            reason="matched_demo_goal_memory_question",
            reply=LINK1_REPLIES["recall_demo_goal"][0],
            expression="speaking",
            motion=False,
            trigger={"transcript": transcript, "memory_key": "demo_goal"},
        )
    if _has_any(text, ("喜欢什么故事", "我喜欢什么故事", "记得我喜欢什么", "我喜欢什么类型", "喜欢什么类型")):
        return _decision(
            link="fast1",
            intent="recall_preference",
            confidence=0.93,
            reason="matched_preference_memory_question",
            reply=LINK1_REPLIES["recall_preference"][0],
            expression="speaking",
            motion=False,
            trigger={"transcript": transcript, "memory_key": "preference_story"},
        )
    if _has_any(text, ("我喜欢科幻故事", "喜欢科幻故事", "爱看科幻故事", "喜欢星际探险")):
        return _decision(
            link="fast1",
            intent="capture_preference",
            confidence=0.9,
            reason="matched_preference_memory_capture",
            reply=LINK1_REPLIES["capture_preference"][0],
            expression="happy",
            motion=False,
            trigger={"transcript": transcript, "memory_key": "preference_story", "value": "科幻故事"},
        )
    if _has_any(text, ("日程", "日历", "行程", "schedule", "calendar")):
        return _decision(
            link="fast1",
            intent="capture_schedule",
            confidence=0.88,
            reason="matched_schedule_keyword",
            reply=_pick_reply("capture_schedule", transcript, LINK1_REPLIES["capture_schedule"]),
            expression="happy",
            motion=False,
            trigger={"transcript": transcript, "schedule": parse_reminder_due_at(transcript)},
        )
    if _has_any(text, ("提醒", "待会", "等会", "过会", "明天", "几点", "秒后", "秒钟后", "分钟后", "小时后", "闹钟", "到点")):
        return _decision(
            link="fast1",
            intent="capture_reminder",
            confidence=0.9,
            reason="matched_reminder_keyword",
            reply=_pick_reply("capture_reminder", transcript, LINK1_REPLIES["capture_reminder"]),
            expression="happy",
            motion=False,
            trigger={"transcript": transcript, "reminder": parse_reminder_due_at(transcript)},
        )
    if _has_any(text, ("会议", "开会", "讨论", "meeting", "复盘", "周会")):
        return _decision(
            link="fast1",
            intent="capture_meeting",
            confidence=0.86,
            reason="matched_meeting_keyword",
            reply=_pick_reply("capture_meeting", transcript, LINK1_REPLIES["capture_meeting"]),
            expression="thinking",
            motion=False,
            trigger={"transcript": transcript},
        )
    if _has_any(text, ("任务", "待办", "todo", "安排", "处理")):
        return _decision(
            link="fast1",
            intent="capture_task",
            confidence=0.84,
            reason="matched_task_keyword",
            reply=_pick_reply("capture_task", transcript, LINK1_REPLIES["capture_task"]),
            expression="happy",
            motion=False,
            trigger={"transcript": transcript},
        )
    if _has_any(text, ("想法", "点子", "灵感", "idea", "方案", "笔记", "记一下", "记录", "保存", "备忘", "写下来")):
        return _decision(
            link="fast1",
            intent="capture_note",
            confidence=0.86,
            reason="matched_note_keyword",
            reply=_pick_reply("capture_note", transcript, LINK1_REPLIES["capture_note"]),
            expression="happy",
            motion=False,
            trigger={"transcript": transcript},
        )
    return _decision(
        link="fast1",
        intent="capture_note",
        confidence=0.72,
        reason="default_note_capture",
        reply=_pick_reply("capture_note", transcript, LINK1_REPLIES["capture_note"]),
        expression="thinking",
        motion=False,
        trigger={"transcript": transcript},
    )


def _decide_link3(transcript: str) -> dict[str, Any]:
    text = normalize_text(transcript)
    if _has_any(text, ("停", "停止", "别动", "不要动", "stop")):
        return _decision(
            link="fast3",
            intent="stop_motion",
            confidence=0.95,
            reason="matched_stop_keyword",
            reply=_pick_reply("stop_motion", transcript, LINK3_REPLIES["stop_motion"]),
            expression="idle",
            motion_step={"action": "stop", "params": {}, "timeout_ms": 800},
            trigger={"transcript": transcript},
        )
    if _has_any(text, ("回去", "回dock", "回家", "回窝", "回充电", "返回基站", "回基站", "去基站", "基站", "return")):
        return _decision(
            link="fast3",
            intent="return_to_dock",
            confidence=0.9,
            reason="matched_return_keyword",
            reply=_pick_reply("return_to_dock", transcript, LINK3_REPLIES["return_to_dock"]),
            expression="idle",
            motion_step={"action": "move_back_to_dock", "params": {"speed": 0.54}, "timeout_ms": 1200},
            trigger={"transcript": transcript},
        )
    expression = match_requested_expression(text)
    if expression is not None:
        return _decision(
            link="fast3",
            intent="set_expression",
            confidence=0.9,
            reason="matched_expression_name",
            reply=_pick_expression_reply(expression, transcript),
            expression=expression,
            motion=False,
            trigger={"transcript": transcript, "expression": expression},
        )
    if _has_any(text, ("状态怎么样", "现在状态", "电量", "网络正常", "准备好了吗", "准备好没有", "自我介绍")):
        return _decision(
            link="fast3",
            intent="status_intro",
            confidence=0.88,
            reason="matched_status_intro_keyword",
            reply=LINK3_REPLIES["status_intro"][0],
            expression="speaking",
            motion=False,
            trigger={"transcript": transcript, "preset": True},
        )
    if _has_any(text, ("累", "困", "压力", "难受", "焦虑", "陪我", "休息", "出来", "过来")):
        return _decision(
            link="fast3",
            intent="companion_care",
            confidence=0.88,
            reason="matched_care_keyword",
            reply=_pick_reply("companion_care", transcript, LINK3_REPLIES["companion_care"]),
            expression="caring",
            motion_step={"action": "move_out_of_dock", "params": {"speed": 1.0, "distance_cm": 8.0}, "timeout_ms": 1200},
            trigger={"transcript": transcript},
        )
    if _has_any(text, ("小安", "你好", "在吗", "hello", "嗨")):
        return _decision(
            link="fast3",
            intent="greeting",
            confidence=0.78,
            reason="matched_greeting_keyword",
            reply=_pick_reply("greeting", transcript, LINK3_REPLIES["greeting"]),
            expression="happy",
            motion=False,
            trigger={"transcript": transcript},
        )
    return _decision(
        link="fast3",
        intent="gentle_ack",
        confidence=0.62,
        reason="default_gentle_ack",
        reply=_pick_reply("gentle_ack", transcript, LINK3_REPLIES["gentle_ack"]),
        expression="thinking",
        motion=False,
        trigger={"transcript": transcript},
    )


def _decision(
    *,
    link: str,
    intent: str,
    confidence: float,
    reason: str,
    reply: str,
    expression: str,
    motion: bool | None = None,
    motion_step: dict[str, Any] | None = None,
    trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {"kind": "expression", "expression": expression, "duration_ms": 1500, "loop": False},
    ]
    if motion_step is not None:
        steps.append({"kind": "motion", **motion_step})
    elif motion:
        steps.append({
            "kind": "motion",
            "action": "move_out_of_dock",
            "params": {"speed": 1.0, "distance_cm": 8.0},
            "timeout_ms": 1200,
        })
    if intent not in {"visual_normal"}:
        steps.append({"kind": "tts", "text": reply, "duration_ms": 3000})
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "decision_source": DECISION_SOURCE,
        "public_label": PUBLIC_LABEL,
        "link": link,
        "intent": intent,
        "handled": True,
        "confidence": round(max(0.0, min(float(confidence), 1.0)), 3),
        "reason": reason,
        "reply_text": reply,
        "display_text": reply,
        "spoken_text": reply,
        "trigger": trigger or {},
        "robot_plan": {
            "allow_motion_required": bool(motion or motion_step),
            "steps": steps,
        },
    }


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def match_requested_expression(text: str) -> str | None:
    has_command_marker = _has_any(text, EXPRESSION_COMMAND_MARKERS)
    for expression in SUPPORTED_EXPRESSIONS:
        aliases = EXPRESSION_ALIASES.get(expression, ())
        if not any(alias in text for alias in aliases):
            continue
        if has_command_marker or any(f"{alias}表情" in text or f"{alias}脸" in text for alias in aliases):
            return expression
    return None


def _pick_expression_reply(expression: str, seed_text: str) -> str:
    reply = EXPRESSION_PERFORMANCE_REPLIES.get(expression)
    if reply:
        return reply
    return _pick_reply("set_expression", seed_text, LINK3_REPLIES["set_expression"])


def _pick_reply(intent: str, seed_text: str, replies: tuple[str, ...]) -> str:
    if not replies:
        return ""
    digest = hashlib.sha1(f"{intent}|{seed_text}".encode("utf-8")).digest()
    return replies[int.from_bytes(digest[:2], "big") % len(replies)]


def _reminder_parse_result(due: datetime, base: datetime, time_text: str, confidence: float) -> dict[str, Any]:
    delay_seconds = max(0, int((due - base).total_seconds()))
    return {
        "due_at": due.isoformat(),
        "delay_seconds": delay_seconds,
        "time_text": time_text,
        "time_parse_confidence": confidence,
    }


def publish_fast_demo_dashboard_capture(
    decision: dict[str, Any],
    transcript: str,
    *,
    dashboard_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Mirror Fast Link 1 captures into the dashboard state used by the dock UI."""

    if decision.get("link") != "fast1":
        return None
    intent = str(decision.get("intent") or "")
    if intent not in {"capture_task", "capture_schedule", "capture_reminder", "capture_note", "capture_meeting"}:
        return None

    path = Path(dashboard_path) if dashboard_path is not None else DEFAULT_OPENCLAW_DASHBOARD_PATH
    timestamp = (now or datetime.now().astimezone()).replace(microsecond=0).isoformat()
    data = _load_dashboard_state_file(path)
    item = _dashboard_item_for_decision(decision, transcript, timestamp=timestamp)
    if item is None:
        return None

    list_name = {
        "capture_task": "todos",
        "capture_schedule": "schedules",
        "capture_reminder": "reminders",
        "capture_note": "todos",
        "capture_meeting": "schedules",
    }[intent]
    data.setdefault(list_name, [])
    if not isinstance(data[list_name], list):
        data[list_name] = []
    data[list_name] = _upsert_dashboard_item(data[list_name], item)
    data["mode"] = "completed"
    data["status_text"] = str(decision.get("display_text") or decision.get("reply_text") or "小安已记录。")
    data["latest_reply"] = {
        "display_text": str(decision.get("display_text") or decision.get("reply_text") or ""),
        "source": "fast_link1",
        "updated_at": timestamp,
    }
    data["next_item"] = item
    _write_dashboard_state_file(path, data)
    return {"ok": True, "path": str(path), "list": list_name, "item": item}


def _load_dashboard_state_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    data = raw if isinstance(raw, dict) else {}
    if data.get("schema") != OPENCLAW_DASHBOARD_SCHEMA:
        data = {}
    data.setdefault("schema", OPENCLAW_DASHBOARD_SCHEMA)
    for key in ("todos", "schedules", "reminders"):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def _write_dashboard_state_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _upsert_dashboard_item(items: list[Any], item: dict[str, Any]) -> list[dict[str, Any]]:
    fingerprint = item.get("id")
    cleaned = [existing for existing in items if isinstance(existing, dict) and existing.get("id") != fingerprint]
    return [item, *cleaned][:20]


def _dashboard_item_for_decision(decision: dict[str, Any], transcript: str, *, timestamp: str) -> dict[str, Any] | None:
    intent = str(decision.get("intent") or "")
    title = _capture_title(transcript, intent)
    item_id = "fast-link1-" + hashlib.sha1(f"{intent}|{transcript}".encode("utf-8")).hexdigest()[:12]
    base = {
        "id": item_id,
        "title": title,
        "status": "pending",
        "source": "fast_link1",
        "created_at": timestamp,
        "transcript": transcript,
    }
    if intent == "capture_task":
        return {**base, "type": "todo", "priority": _priority_from_text(transcript)}
    if intent == "capture_note":
        return {**base, "type": "todo", "priority": "normal", "due_text": "语音笔记"}
    if intent == "capture_schedule" or intent == "capture_meeting":
        reminder = parse_reminder_due_at(transcript)
        due = _parse_iso_datetime(str(reminder.get("due_at") or ""))
        return {
            **base,
            "type": "schedule",
            "date": due.date().isoformat() if due else "",
            "time": due.strftime("%H:%M") if due else str(reminder.get("time_text") or "待补充"),
        }
    if intent == "capture_reminder":
        trigger = decision.get("trigger") if isinstance(decision.get("trigger"), dict) else {}
        reminder = trigger.get("reminder") if isinstance(trigger.get("reminder"), dict) else parse_reminder_due_at(transcript)
        due_at = str(reminder.get("due_at") or "")
        due = _parse_iso_datetime(due_at)
        return {
            **base,
            "type": "alarm",
            "due_at": due_at,
            "time": due.strftime("%H:%M") if due else str(reminder.get("time_text") or ""),
        }
    return None


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _priority_from_text(text: str) -> str:
    normalized = normalize_text(text)
    if _has_any(normalized, ("紧急", "重要", "优先", "高优先级", "p0", "p1")):
        return "high"
    if _has_any(normalized, ("不急", "低优先级", "有空", "p3")):
        return "low"
    return "normal"


def _capture_title(transcript: str, intent: str) -> str:
    title = str(transcript or "").strip()
    replacements = (
        "小安",
        "帮我",
        "请",
        "把",
        "加入todo list",
        "加入todolist",
        "加入todo",
        "加入待办清单",
        "加入待办",
        "加入任务",
        "加到todo list",
        "加到todolist",
        "加到待办",
        "加到日程",
        "加入日程",
        "加入日历",
        "放进日程",
        "添加到日程",
        "添加日程",
        "提醒我",
        "提醒",
        "记一下",
        "记录一下",
        "记录",
        "保存",
    )
    for token in replacements:
        title = title.replace(token, "")
    title = re.sub(r"[，。,.!！?？]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    if intent in {"capture_schedule", "capture_reminder", "capture_meeting"}:
        title = _strip_time_phrase(title).strip()
    return title or str(transcript or "").strip() or "语音事项"


def _strip_time_phrase(text: str) -> str:
    patterns = (
        r"(今天|明天)?(上午|早上|下午|晚上|中午)?([0-9]{1,2}|[一二两三四五六七八九十]{1,3})点(半|([0-9]{1,2}|[一二两三四五六七八九十]{1,3})分?)?",
        r"([0-9]+|[一二两三四五六七八九十]+)(秒钟?|分钟?|小时|钟头)后",
        r"半小时后",
    )
    result = text
    for pattern in patterns:
        result = re.sub(pattern, "", result)
    return re.sub(r"\s+", " ", result)


def _parse_cn_number(raw: str | None) -> int | None:
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if raw == "十":
        return 10
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones
    if len(raw) == 1:
        return digits.get(raw)
    return None


def _normalized_score(value: Any) -> float:
    score = _as_float(value, 0.0) or 0.0
    if score > 1.0:
        return max(0.0, min(score / 100.0, 1.0))
    return max(0.0, min(score, 1.0))


def _as_float(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ack_summary(ack: dict[str, Any]) -> dict[str, Any]:
    payload = ack.get("payload") if isinstance(ack.get("payload"), dict) else {}
    return {
        "type": ack.get("type"),
        "ok": payload.get("ok"),
        "status": payload.get("status"),
        "command_id": payload.get("command_id"),
    }
