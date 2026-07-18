"""Xiao An Agent Brain MVP.

This module is not an OpenClaw replacement. OpenClaw xiaoan-runtime owns user
profile, long-term memory, reply generation, and tool selection; this module
keeps local event routing and robot action compatibility paths.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent.core.action_executor import ActionExecutor
from agent.core.context_builder import ContextBuilder
from agent.core.gateway import RobotGateway
from agent.core.local_fast_path import LocalFastPathRouter
from agent.core.memory import XiaoAnMemoryStore
from agent.core.memory_recorder import MemoryRecorder
from agent.core.event_router import openclaw_base_context_for_asr
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawEvent
from agent.core.openclaw_adapter_factory import build_openclaw_adapter_from_env
from agent.core.work_mode import EpisodeLease, WorkModeStore
from agent.skills.companion_request import CompanionRequestSkill
from agent.skills.emotion_monitor import EmotionMonitorSkill
from agent.skills.robot_motion import RobotMotionSkill
from base_station.monitor.emotion_db import EmotionDB
from base_station.integration_console.fast_demo_brain import parse_reminder_due_at


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
        local_fast_path: Any | None = None,
        work_mode_store: Any | None = None,
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
        self.local_fast_path = (
            local_fast_path
            if local_fast_path is not None
            else LocalFastPathRouter()
        )
        self.work_mode_store = (
            work_mode_store
            if work_mode_store is not None
            else WorkModeStore.from_env()
        )

    async def handle_event(self, event: dict) -> dict:
        event_type = event.get("type")
        if event_type in SUPPORTED_EMOTION_EVENTS:
            trigger = event.get("payload") or event
            lease = self._acquire_episode(
                chain="link2",
                source="emotion",
                text=str(trigger.get("emotion_tag") or trigger.get("reason") or ""),
                requires_mic_recognition=False,
            )
            if not lease.acquired:
                return self._blocked_by_work_mode(lease)
            final_result: dict | None = None
            final_status = "completed"
            try:
                final_result = await self._handle_emotion_event(event, trigger)
                return final_result
            except Exception:
                final_status = "failed"
                raise
            finally:
                self._release_episode(lease, status=final_status, result=final_result)

        if event_type == ASR_TRANSCRIPT_EVENT:
            return await self._handle_asr_event(event)

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
            decision = self._rewrite_failed_reminder_for_local_fallback(decision, payload.get("text", ""))
            execution_result = await self.action_executor.execute(decision)
            execution_result["route"] = "frontend_openclaw"
            execution_result["reason"] = "openclaw_decision"
            return execution_result

        return {
            "handled": False,
            "reason": "unsupported_event",
            "message": f"Unsupported event type: {event_type}",
        }

    async def _handle_emotion_event(self, event: dict, trigger: dict) -> dict:
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

    async def _handle_asr_event(self, event: dict) -> dict:
        payload = event.get("payload") or {}
        text = payload.get("text")
        requires_mic_recognition = not bool(payload.get("completed_mic_segment"))
        chain_hint = self.local_fast_path.classify_chain(text)
        if chain_hint == "link3":
            lease = self._acquire_episode(
                chain="link3",
                source="asr",
                text=text,
                requires_mic_recognition=requires_mic_recognition,
            )
            if not lease.acquired:
                return self._blocked_by_work_mode(lease)
            final_result: dict | None = None
            final_status = "completed"
            try:
                local_result = await self.local_fast_path.try_handle_asr(
                    text=text,
                    payload=payload,
                    run_id=lease.run_id or "local-fast-path",
                    robot_motion=self.robot_motion,
                )
                if local_result.get("handled"):
                    local_result = await self._execute_local_fast_path_tts(
                        local_result,
                        source_event_type=ASR_TRANSCRIPT_EVENT,
                    )
                    final_result = local_result
                    return local_result
                final_status = "skipped"
            except Exception:
                final_status = "failed"
                raise
            finally:
                self._release_episode(lease, status=final_status, result=final_result)

        companion_disabled = bool(payload.get("disable_companion_fast_path"))
        companion_result = (
            {
                "handled": False,
                "reason": "companion_fast_path_disabled",
                "trigger_result": None,
            }
            if companion_disabled
            else await self.companion_request.handle_text(text)
        )
        if companion_result.get("handled", False):
            lease = self._acquire_episode(
                chain="link3",
                source="asr",
                text=text,
                requires_mic_recognition=requires_mic_recognition,
            )
            if not lease.acquired:
                return self._blocked_by_work_mode(lease)
            final_result = None
            final_status = "completed"
            try:
                final_result = await self._handle_companion_fast_path(
                    payload=payload,
                    companion_result=companion_result,
                    source="asr",
                )
                return final_result
            except Exception:
                final_status = "failed"
                raise
            finally:
                self._release_episode(lease, status=final_status, result=final_result)

        lease = self._acquire_episode(
            chain="link1",
            source="asr",
            text=text,
            requires_mic_recognition=requires_mic_recognition,
        )
        if not lease.acquired:
            return self._blocked_by_work_mode(lease)
        final_result = None
        final_status = "completed"
        try:
            local_result = await self.local_fast_path.try_handle_asr(
                text=text,
                payload=payload,
                run_id=lease.run_id or "local-fast-path",
                robot_motion=self.robot_motion,
            )
            if local_result.get("handled"):
                local_result = await self._execute_local_fast_path_tts(
                    local_result,
                    source_event_type=ASR_TRANSCRIPT_EVENT,
                )
                final_result = local_result
                return local_result

            base_context = openclaw_base_context_for_asr(
                payload=payload,
                companion_result=companion_result,
            )
            openclaw_context = self._build_openclaw_context(
                text=text,
                base_context=base_context,
                event_type=ASR_TRANSCRIPT_EVENT,
                source="asr",
            )
            openclaw_context["local_fast_path"] = local_result
            openclaw_event = OpenClawEvent(
                type=ASR_TRANSCRIPT_EVENT,
                text=text,
                source="asr",
                session_id=payload.get("session_id", "default"),
                context=openclaw_context,
            )
            decision = self.openclaw_adapter.handle_event(openclaw_event)
            decision = self._rewrite_failed_reminder_for_local_fallback(decision, text)
            execution_result = await self.action_executor.execute(decision)
            execution_result["route"] = "link_1_openclaw"
            execution_result["reason"] = "openclaw_decision"
            execution_result["companion_result"] = companion_result
            final_result = execution_result
            return execution_result
        except Exception:
            final_status = "failed"
            raise
        finally:
            self._release_episode(lease, status=final_status, result=final_result)

    def _acquire_episode(
        self,
        *,
        chain: str,
        source: str,
        text: str | None,
        requires_mic_recognition: bool,
    ) -> EpisodeLease:
        acquire = getattr(self.work_mode_store, "acquire_episode", None)
        if not callable(acquire):
            return EpisodeLease(True, None, chain, "no_work_mode_store")
        try:
            return acquire(
                chain=chain,
                source=source,
                text=text,
                requires_mic_recognition=requires_mic_recognition,
            )
        except Exception:
            return EpisodeLease(True, None, chain, "work_mode_unavailable")

    def _release_episode(
        self,
        lease: EpisodeLease,
        *,
        status: str,
        result: dict | None,
    ) -> None:
        if not lease.acquired or not lease.run_id:
            return
        release = getattr(self.work_mode_store, "release_episode", None)
        if not callable(release):
            return
        try:
            release(lease.run_id, status=status, result=result)
        except Exception:
            return

    @staticmethod
    def _blocked_by_work_mode(lease: EpisodeLease) -> dict:
        return {
            "handled": False,
            "route": "work_mode.blocked",
            "reason": lease.reason,
            "chain": lease.chain,
            "work_mode": lease.state or {},
        }

    async def _execute_local_fast_path_tts(
        self,
        result: dict,
        *,
        source_event_type: str | None = None,
    ) -> dict:
        if not result.get("handled"):
            return result
        if result.get("suppress_auto_tts"):
            result.setdefault("tts_text", "")
            result.setdefault("tts_source", "")
            return result
        if result.get("tts_text") or self._has_executed_tts(result):
            return result

        spoken_text = str(result.get("spoken_text") or "").strip()
        reply_text = str(result.get("reply_text") or "").strip()
        auto_tts_text = spoken_text or reply_text
        if not auto_tts_text:
            result.setdefault("tts_text", "")
            result.setdefault("tts_source", "")
            return result

        decision = OpenClawDecision(
            handled=True,
            display_text=result.get("display_text"),
            spoken_text=spoken_text,
            reply_text=reply_text,
            suppress_auto_tts=False,
        )
        tts_result = await self.action_executor.execute(
            decision,
            source_event_type=source_event_type,
        )
        merged = dict(result)
        merged["executed_actions"] = [
            *(result.get("executed_actions") or []),
            *(tts_result.get("executed_actions") or []),
        ]
        merged["skipped_actions"] = [
            *(result.get("skipped_actions") or []),
            *(tts_result.get("skipped_actions") or []),
        ]
        merged["tts_text"] = tts_result.get("tts_text", "")
        merged["tts_source"] = tts_result.get("tts_source", "")
        if tts_result.get("tts_tool"):
            merged["tts_tool"] = tts_result["tts_tool"]
        return merged

    @staticmethod
    def _has_executed_tts(result: dict) -> bool:
        for action in result.get("executed_actions") or []:
            name = str(action.get("name") or action.get("tool") or "")
            if name in {"robot.say", "xiaoan.robot.say", "audio.play_tts"}:
                return True
        return False

    def _rewrite_failed_reminder_for_local_fallback(
        self,
        decision: Any,
        text: str | None,
    ) -> Any:
        capture = self._decision_capture(decision)
        if not self._capture_needs_cron_fallback(capture):
            return decision

        reminder = parse_reminder_due_at(text or "")
        if not self._has_explicit_reminder_time(reminder):
            return decision
        due_at = str(reminder.get("due_at") or "").strip()
        if not due_at:
            return decision

        raw = deepcopy(getattr(decision, "raw", None)) if isinstance(getattr(decision, "raw", None), dict) else {}
        raw_capture = raw.get("capture") if isinstance(raw.get("capture"), dict) else {}
        title = (
            str(raw_capture.get("title") or "").strip()
            or self._reminder_title_from_text(text)
            or "这件事"
        )
        time_text = str(reminder.get("time_text") or "").strip() or "到点"
        display_text = f"好呀，{time_text}提醒你{title}。"
        spoken_text = f"好呀，{time_text}提醒你{title}，小安帮你看着。"

        raw_capture.update({
            "status": "captured",
            "kind": "reminder",
            "source_of_truth": "base_station_local_reminder_fallback",
            "title": title,
            "content": str(raw_capture.get("content") or text or "").strip(),
            "due_at": due_at,
            "time_text": time_text,
            "date": self._date_from_iso(due_at),
            "time": self._time_from_iso(due_at),
            "missing_fields": [],
            "metadata": {
                **(raw_capture.get("metadata") if isinstance(raw_capture.get("metadata"), dict) else {}),
                "fallback_reason": "openclaw_missing_cron_tool",
                "original_status": capture.get("status"),
            },
        })
        raw["capture"] = raw_capture
        raw["display_text"] = display_text
        raw["spoken_text"] = spoken_text
        raw["reply_text"] = display_text

        decision.display_text = display_text
        decision.spoken_text = spoken_text
        decision.reply_text = display_text
        decision.suppress_auto_tts = False
        decision.tool_calls = []
        decision.raw = raw
        return decision

    @staticmethod
    def _decision_capture(decision: Any) -> dict[str, Any] | None:
        raw = getattr(decision, "raw", None)
        if isinstance(raw, dict) and isinstance(raw.get("capture"), dict):
            return raw["capture"]
        return None

    @staticmethod
    def _capture_needs_cron_fallback(capture: dict[str, Any] | None) -> bool:
        if not isinstance(capture, dict):
            return False
        if str(capture.get("kind") or "").strip().lower() not in {"reminder", "alarm"}:
            return False
        if str(capture.get("status") or "").strip().lower() != "failed":
            return False
        missing_fields = capture.get("missing_fields")
        if not isinstance(missing_fields, list):
            return False
        return "cron_tool" in {str(item).strip().lower() for item in missing_fields}

    @staticmethod
    def _has_explicit_reminder_time(reminder: dict[str, Any]) -> bool:
        if not isinstance(reminder, dict):
            return False
        confidence = reminder.get("time_parse_confidence")
        try:
            score = float(confidence)
        except (TypeError, ValueError):
            score = 0.0
        return score >= 0.5 and str(reminder.get("time_text") or "") != "默认1分钟后"

    @staticmethod
    def _reminder_title_from_text(text: str | None) -> str:
        value = str(text or "").strip()
        for token in ("提醒我", "提醒"):
            if token in value:
                tail = value.split(token, 1)[1].strip(" ，。,.")
                if tail:
                    return tail
        return ""

    @staticmethod
    def _date_from_iso(value: str) -> str:
        return value[:10] if len(value) >= 10 else ""

    @staticmethod
    def _time_from_iso(value: str) -> str:
        return value[11:16] if len(value) >= 16 else ""

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
            "tool_profile": "companion",
            "route_hint": {
                "kind": "companion",
                "tool_profile": "companion",
                "intent_hint": "companion_care",
            },
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
        expression = motion = tts = None
        for item in care_result:
            action_type = self._care_action_type(item)
            if expression is None and action_type == "display.expression":
                expression = item
            elif motion is None and action_type == "motion.execute":
                motion = item
            elif tts is None and action_type == "audio.play_tts":
                tts = item
        if expression is None:
            expression = care_result[0] if len(care_result) > 0 else None
        if motion is None:
            motion = care_result[1] if len(care_result) > 1 else None
        if tts is None:
            tts = care_result[2] if len(care_result) > 2 else None
        return expression, motion, tts

    @staticmethod
    def _care_action_type(item: Any) -> str:
        if not isinstance(item, dict):
            return ""
        payload = item.get("payload")
        if isinstance(payload, dict):
            return str(payload.get("forwarded_type") or payload.get("command_type") or "")
        return str(item.get("type") or "")

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
