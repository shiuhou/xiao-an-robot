"""Xiao An Agent Brain MVP.

This module is still not an OpenClaw replacement. For the local simulation MVP,
it acts as a small event router: emotion events go to EmotionMonitorSkill, which
can use RobotGateway and EmotionDB to trigger robot care actions.
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
    """Minimal Agent brain for routing local MVP events to skills."""

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
            self._record_emotion_intervention(trigger_context, emotion_result)
            openclaw_context = {
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
                    text="User emotion intervention triggered.",
                    source="emotion_monitor",
                    session_id=trigger_context.get("session_id", "default"),
                    context=openclaw_context,
                )
                decision = self.openclaw_adapter.handle_event(openclaw_event)
                emotion_result["openclaw_result"] = await self.action_executor.execute(decision)
            except Exception as exc:
                emotion_result["openclaw_error"] = str(exc)
            return emotion_result

        if event_type == ASR_TRANSCRIPT_EVENT:
            payload = event.get("payload") or {}
            text = payload.get("text")
            companion_result = await self.companion_request.handle_text(text)
            if companion_result.get("handled", False):
                companion_result["route"] = "link_3_companion_fast_path"
                companion_result["openclaw_event_type"] = "companion.request"
                self._record_companion_request(payload, companion_result)
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
                        source="asr",
                        session_id=payload.get("session_id", "default"),
                        context=companion_context,
                    )
                    decision = self.openclaw_adapter.handle_event(openclaw_event)
                    companion_result["openclaw_result"] = await self.action_executor.execute(decision)
                except Exception as exc:
                    companion_result["openclaw_error"] = str(exc)
                return companion_result

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
