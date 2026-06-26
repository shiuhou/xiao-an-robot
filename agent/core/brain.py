"""Xiao An Agent Brain MVP.

This module is not an OpenClaw replacement. OpenClaw xiaoan-runtime owns user
profile, long-term memory, reply generation, and tool selection; this module
keeps local event routing and robot action compatibility paths.
"""

from __future__ import annotations

from typing import Any

from agent.core.action_executor import ActionExecutor
from agent.core.context_builder import ContextBuilder
from agent.core.gateway import RobotGateway
from agent.core.memory import XiaoAnMemoryStore
from agent.core.memory_recorder import MemoryRecorder
from agent.core.openclaw_adapter import OpenClawEvent
from agent.core.openclaw_adapter_factory import build_openclaw_adapter_from_env
from agent.skills.companion_request import CompanionRequestSkill
from agent.skills.emotion_monitor import EmotionMonitorSkill
from agent.skills.robot_motion import RobotMotionSkill
from base_station.monitor.emotion_db import EmotionDB


SUPPORTED_EMOTION_EVENTS = {"emotion.sample", "emotion.alert"}
ASR_TRANSCRIPT_EVENT = "asr.transcript"
FRONTEND_MESSAGE_EVENT = "frontend.message"


class XiaoAnBrain:
    """Minimal local router for robot events and compatibility skills."""

    def __init__(
        self,
        gateway: Any | None = None,
        memory: Any | None = None,
        gateway_url: str = "ws://127.0.0.1:8765/agent",
        db_path: str = "agent/data/xiao_an.db",
        window_seconds: int = 300,
        openclaw_adapter: Any | None = None,
        action_executor: Any | None = None,
        context_builder: Any | None = None,
        context_memory: Any | None = None,
        memory_recorder: Any | None = None,
    ):
        self.gateway = gateway or RobotGateway(url=gateway_url)
        self.memory = memory or EmotionDB(db_path=db_path)
        self._owns_context_memory = False
        if context_builder is not None:
            self.context_builder = context_builder
            self.context_memory = context_memory
        else:
            if context_memory is None:
                context_memory = XiaoAnMemoryStore(db_path=db_path)
                self._owns_context_memory = True
            self.context_memory = context_memory
            self.context_builder = ContextBuilder(memory_store=context_memory)
        self.robot_motion = RobotMotionSkill(gateway=self.gateway)
        self.emotion_monitor = EmotionMonitorSkill(
            gateway=self.gateway,
            memory=self.memory,
            window_seconds=window_seconds,
            execute_local_care=False,
        )
        self.companion_request = CompanionRequestSkill(
            robot_motion=self.robot_motion,
        )
        self.openclaw_adapter = (
            openclaw_adapter
            if openclaw_adapter is not None
            else build_openclaw_adapter_from_env()
        )
        self.action_executor = (
            action_executor
            if action_executor is not None
            else ActionExecutor(self.robot_motion, memory_store=self.context_memory)
        )
        if memory_recorder is not None:
            self.memory_recorder = memory_recorder
        elif self.context_memory is not None:
            self.memory_recorder = MemoryRecorder(memory_store=self.context_memory)
        else:
            self.memory_recorder = None

    async def handle_event(self, event: dict) -> dict:
        event_type = event.get("type")
        if event_type in SUPPORTED_EMOTION_EVENTS:
            trigger = event.get("payload") or event
            emotion_result = await self.emotion_monitor.run(trigger)
            if not emotion_result.get("handled", False):
                return emotion_result

            emotion_result["route"] = "link_2_emotion_fast_path"
            emotion_result["openclaw_event_type"] = "emotion.intervention"
            trigger_context = trigger if isinstance(trigger, dict) else {}
            intervention_payload = self._build_emotion_intervention_payload(
                trigger_context,
                emotion_result,
            )
            emotion_result["payload"] = intervention_payload
            self._record_emotion_intervention(trigger_context, emotion_result)
            openclaw_context = {
                "payload": intervention_payload,
                "event": event,
                "trigger": trigger,
                "emotion_result": dict(emotion_result),
            }
            if "reason" in emotion_result:
                openclaw_context["reason"] = emotion_result["reason"]
                openclaw_context["trigger_reason"] = emotion_result["reason"]
            for key in ("emotion_tag", "fatigue_score", "confidence"):
                if key in trigger_context:
                    openclaw_context[key] = trigger_context[key]

            try:
                openclaw_event = OpenClawEvent(
                    type="emotion.intervention",
                    text=emotion_result.get("message") or "User emotion intervention triggered.",
                    source="emotion_monitor",
                    session_id=trigger_context.get("session_id", "default"),
                    context=openclaw_context,
                )
                decision = self.openclaw_adapter.handle_event(openclaw_event)
                openclaw_result = await self.action_executor.execute(
                    decision,
                    source_event_type="emotion.intervention",
                )
                emotion_result["openclaw_result"] = openclaw_result
                self._record_robot_care_action(
                    route=emotion_result.get("route"),
                    source_event_type=emotion_result.get("openclaw_event_type"),
                    trigger=trigger_context,
                    result=openclaw_result,
                    reply_text=openclaw_result.get("reply_text") or decision.reply_text,
                    timestamp_ms=intervention_payload.get("timestamp_ms"),
                    session_id=trigger_context.get("session_id", "default"),
                )
            except Exception as exc:
                emotion_result["openclaw_error"] = str(exc)
            return emotion_result

        if event_type == ASR_TRANSCRIPT_EVENT:
            payload = event.get("payload") or {}
            text = payload.get("text")
            companion_result = await self.companion_request.handle_text(text)
            if companion_result.get("handled", False):
                return await self._handle_companion_fast_path(
                    payload=payload,
                    companion_result=companion_result,
                    source="asr",
                )

            base_context = {
                "payload": payload,
                "companion_result": companion_result,
            }
            openclaw_context = self._build_openclaw_context(
                text=text,
                base_context=base_context,
                event_type=ASR_TRANSCRIPT_EVENT,
                source="asr",
            )
            openclaw_event = OpenClawEvent(
                type=ASR_TRANSCRIPT_EVENT,
                text=text,
                source="asr",
                session_id=payload.get("session_id", "default"),
                context=openclaw_context,
            )
            decision = self.openclaw_adapter.handle_event(openclaw_event)
            execution_result = await self.action_executor.execute(decision)
            execution_result["route"] = "link_1_openclaw"
            execution_result["reason"] = "openclaw_decision"
            execution_result["companion_result"] = companion_result
            return execution_result

        if event_type == FRONTEND_MESSAGE_EVENT:
            payload = event.get("payload") or {}
            companion_result = await self.companion_request.handle_text(payload.get("text"))
            if companion_result.get("handled", False):
                return await self._handle_companion_fast_path(
                    payload=payload,
                    companion_result=companion_result,
                    source="frontend",
                )

            base_context = {
                "payload": payload,
            }
            openclaw_context = self._build_openclaw_context(
                text=payload.get("text", ""),
                base_context=base_context,
                event_type=FRONTEND_MESSAGE_EVENT,
                source="frontend",
            )
            openclaw_event = OpenClawEvent(
                type=FRONTEND_MESSAGE_EVENT,
                text=payload.get("text", ""),
                source="frontend",
                session_id=payload.get("session_id", "default"),
                context=openclaw_context,
            )
            decision = self.openclaw_adapter.handle_event(openclaw_event)
            execution_result = await self.action_executor.execute(decision)
            execution_result["route"] = "frontend_openclaw"
            execution_result["reason"] = "openclaw_decision"
            return execution_result

        return {
            "handled": False,
            "reason": "unsupported_event",
            "message": f"Unsupported event type: {event_type}",
        }

    async def _handle_companion_fast_path(
        self,
        *,
        payload: dict,
        companion_result: dict,
        source: str,
    ) -> dict:
        companion_result["route"] = "link_3_companion_fast_path"
        companion_result["openclaw_event_type"] = "companion.request"
        self._record_companion_request(payload, companion_result)
        self._record_robot_care_action(
            route=companion_result.get("route"),
            source_event_type=companion_result.get("openclaw_event_type"),
            trigger=companion_result.get("trigger_result"),
            result=companion_result,
            reply_text=companion_result.get("reply_text"),
            timestamp_ms=payload.get("timestamp_ms"),
            session_id=payload.get("session_id", "default"),
        )
        companion_context = {
            "payload": payload,
            "companion_result": dict(companion_result),
        }
        if "trigger_result" in companion_result:
            companion_context["trigger_result"] = companion_result["trigger_result"]

        try:
            openclaw_event = OpenClawEvent(
                type="companion.request",
                text=payload.get("text", "") or "",
                source=source,
                session_id=payload.get("session_id", "default"),
                context=companion_context,
            )
            decision = self.openclaw_adapter.handle_event(openclaw_event)
            companion_result["openclaw_result"] = await self.action_executor.execute(
                decision,
                source_event_type="companion.request",
            )
        except Exception as exc:
            companion_result["openclaw_error"] = str(exc)
        return companion_result

    def _build_openclaw_context(
        self,
        text: str | None,
        base_context: dict,
        event_type: str,
        source: str,
    ) -> dict:
        try:
            return self.context_builder.build_for_text(
                text,
                base_context=base_context,
                event_type=event_type,
                source=source,
            )
        except Exception as exc:
            context = dict(base_context)
            context.setdefault("context_errors", []).append({
                "scope": "context_builder",
                "error": str(exc),
            })
            return context

    def _record_companion_request(self, payload: dict, companion_result: dict) -> None:
        recorder = getattr(self, "memory_recorder", None)
        record = getattr(recorder, "record_companion_request", None)
        if not callable(record):
            return

        trigger_result = companion_result.get("trigger_result")
        trigger = trigger_result if isinstance(trigger_result, dict) else {}
        text = payload.get("text", "") or ""
        metadata = {
            "route": companion_result.get("route"),
            "asr_text": text,
            "user_text": text,
            "trigger": trigger,
            "matched_keyword": trigger.get("matched_keyword"),
            "reason": companion_result.get("reason") or trigger.get("reason"),
            "fatigue_score": trigger.get("fatigue_score"),
            "emotion_tag": trigger.get("emotion_tag"),
            "openclaw_event_type": companion_result.get("openclaw_event_type"),
            "handled": companion_result.get("handled"),
        }
        try:
            record(
                content=text or "companion request",
                route=companion_result.get("route"),
                trigger=trigger,
                asr_text=text,
                companion_result=companion_result,
                metadata=metadata,
                source="brain",
                timestamp_ms=payload.get("timestamp_ms"),
                session_id=payload.get("session_id", "default"),
            )
        except Exception:
            return

    def _record_robot_care_action(
        self,
        *,
        route: str | None,
        source_event_type: str | None,
        trigger: dict | None,
        result: dict,
        reply_text: str | None,
        timestamp_ms: int | None,
        session_id: str | None,
    ) -> None:
        care_result = result.get("actions")
        action_name = "care_for_user"
        if not care_result:
            care_result = self._care_actions_from_execution_result(result)
            if care_result:
                action_name = "xiaoan.robot.care"
        if not care_result:
            return

        recorder = getattr(self, "memory_recorder", None)
        record = getattr(recorder, "record_robot_care_action", None)
        if not callable(record):
            return

        expression, motion, tts = self._split_care_result(care_result)
        metadata = {
            "route": route,
            "source_event_type": source_event_type,
            "robot_action_result": care_result,
            "care_result": care_result,
            "reply_text": reply_text,
            "expression": expression,
            "motion": motion,
            "tts": tts,
            "handled": result.get("handled"),
            "success": self._care_result_success(care_result),
        }
        try:
            record(
                content=action_name,
                route=route,
                trigger=trigger if isinstance(trigger, dict) else None,
                action_name=action_name,
                reply_text=reply_text,
                robot_action_result={"actions": care_result},
                metadata=metadata,
                source="brain",
                timestamp_ms=timestamp_ms,
                session_id=session_id,
            )
        except Exception:
            return

    def _care_actions_from_execution_result(self, result: dict) -> Any:
        if not isinstance(result, dict):
            return None
        executed_actions = result.get("executed_actions")
        if not isinstance(executed_actions, list):
            return None
        for action in executed_actions:
            if not isinstance(action, dict):
                continue
            if action.get("name") not in {
                "xiaoan.robot.care",
                "robot.care",
                "robot.care_for_user",
            }:
                continue
            action_result = action.get("result")
            if isinstance(action_result, dict) and isinstance(action_result.get("actions"), list):
                return action_result["actions"]
        return None

    def _build_emotion_intervention_payload(self, trigger: dict, emotion_result: dict) -> dict:
        existing_payload = emotion_result.get("payload")
        payload = dict(existing_payload) if isinstance(existing_payload, dict) else {}
        timestamp = (
            payload.get("timestamp_ms")
            or payload.get("timestamp")
            or trigger.get("timestamp_ms")
            or trigger.get("timestamp")
        )
        payload.update({
            "emotion_tag": payload.get("emotion_tag") or trigger.get("emotion_tag") or trigger.get("emotion"),
            "confidence": payload.get("confidence", trigger.get("confidence")),
            "fatigue_score": payload.get("fatigue_score", trigger.get("fatigue_score")),
            "reason": payload.get("reason") or emotion_result.get("reason"),
            "timestamp": payload.get("timestamp") or timestamp,
            "timestamp_ms": payload.get("timestamp_ms") or timestamp,
            "source": payload.get("source") or trigger.get("source"),
        })
        if "frame_source" not in payload and "frame_source" in trigger:
            payload["frame_source"] = trigger.get("frame_source")
        return payload

    def _split_care_result(self, care_result: Any) -> tuple[Any | None, Any | None, Any | None]:
        if not isinstance(care_result, list):
            return None, None, None
        expression = care_result[0] if len(care_result) > 0 else None
        motion = care_result[1] if len(care_result) > 1 else None
        tts = care_result[2] if len(care_result) > 2 else None
        return expression, motion, tts

    def _care_result_success(self, care_result: Any) -> bool:
        if not isinstance(care_result, list) or not care_result:
            return False
        for item in care_result:
            if isinstance(item, dict):
                payload = item.get("payload")
                if isinstance(payload, dict) and payload.get("ok") is False:
                    return False
                if item.get("ok") is False:
                    return False
        return True

    def _record_emotion_intervention(self, trigger: dict, emotion_result: dict) -> None:
        recorder = getattr(self, "memory_recorder", None)
        record = getattr(recorder, "record_emotion_intervention", None)
        if not callable(record):
            return

        emotion_tag = trigger.get("emotion_tag") or trigger.get("emotion")
        confidence = trigger.get("confidence")
        fatigue_score = trigger.get("fatigue_score")
        source = trigger.get("source")
        frame_source = trigger.get("frame_source", source)
        vlm_triggered = (
            trigger["vlm_triggered"]
            if "vlm_triggered" in trigger
            else emotion_result.get("vlm_triggered")
        )
        vlm_trigger_reason = (
            trigger["vlm_trigger_reason"]
            if "vlm_trigger_reason" in trigger
            else emotion_result.get("vlm_trigger_reason")
        )
        visual_reason = (
            trigger["visual_reason"]
            if "visual_reason" in trigger
            else emotion_result.get("visual_reason")
        )
        timestamp_ms = (
            trigger["timestamp_ms"]
            if "timestamp_ms" in trigger
            else trigger.get("timestamp")
        )
        metadata = {
            "route": emotion_result.get("route"),
            "emotion_tag": emotion_tag,
            "confidence": confidence,
            "fatigue_score": fatigue_score,
            "source": source,
            "frame_source": frame_source,
            "frame_id": trigger.get("frame_id"),
            "timestamp_ms": timestamp_ms,
            "reason": emotion_result.get("reason"),
            "trigger_reason": emotion_result.get("reason"),
            "vlm_triggered": vlm_triggered,
            "vlm_trigger_reason": vlm_trigger_reason,
            "visual_reason": visual_reason,
            "vlm_observation": trigger.get("vlm_observation"),
            "cv_sample": trigger.get("cv_sample"),
            "openclaw_event_type": emotion_result.get("openclaw_event_type"),
            "handled": emotion_result.get("handled"),
        }
        try:
            record(
                content=emotion_result.get("message") or "emotion intervention",
                route=emotion_result.get("route"),
                trigger=trigger,
                emotion_tag=emotion_tag,
                confidence=confidence,
                fatigue_score=fatigue_score,
                intervention_result=emotion_result,
                metadata=metadata,
                source="brain",
                timestamp_ms=timestamp_ms,
                session_id=trigger.get("session_id", "default"),
            )
        except Exception:
            return

    def close(self) -> None:
        close = getattr(self.memory, "close", None)
        if callable(close):
            close()
        if self._owns_context_memory:
            close = getattr(self.context_memory, "close", None)
            if callable(close):
                close()


# Backward-compatible alias for older imports.
Brain = XiaoAnBrain


if __name__ == "__main__":
    print("XiaoAnBrain MVP is available. Import XiaoAnBrain and call handle_event(event).")
