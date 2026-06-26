"""Small recorder helpers for writing high-level agent events to the event store."""

from __future__ import annotations

import time
from typing import Any

from agent.core.memory import XiaoAnMemoryStore


class MemoryRecorder:
    """Record agent route events through the existing Local Event Store API."""

    def __init__(
        self,
        memory_store: Any | None = None,
        db_path: str | None = None,
    ):
        self._owns_memory_store = memory_store is None
        self.memory_store = memory_store or XiaoAnMemoryStore(db_path=db_path)

    def close(self) -> None:
        if self._owns_memory_store:
            close = getattr(self.memory_store, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> "MemoryRecorder":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def record_companion_request(
        self,
        *,
        content: str | None = None,
        summary: str | None = None,
        route: str | None = None,
        trigger: dict[str, Any] | None = None,
        asr_text: str | None = None,
        reply_text: str | None = None,
        companion_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        source: str = "companion_request",
        timestamp_ms: int | None = None,
        session_id: str | None = None,
        project_id: int | None = None,
        privacy_level: str = "normal",
    ) -> int:
        event_summary = summary or content or reply_text or asr_text or "companion request"
        event_metadata = self._build_metadata(
            metadata,
            route=route,
            trigger=trigger,
            asr_text=asr_text,
            reply_text=reply_text,
            companion_result=companion_result,
        )
        return self._record_event(
            event_type="companion.request",
            source=source,
            summary=event_summary,
            metadata=event_metadata,
            timestamp_ms=timestamp_ms,
            session_id=session_id,
            project_id=project_id,
            privacy_level=privacy_level,
        )

    def record_emotion_intervention(
        self,
        *,
        content: str | None = None,
        summary: str | None = None,
        route: str | None = None,
        trigger: dict[str, Any] | None = None,
        emotion_tag: str | None = None,
        confidence: float | None = None,
        fatigue_score: float | None = None,
        asr_text: str | None = None,
        reply_text: str | None = None,
        intervention_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        source: str = "emotion_monitor",
        timestamp_ms: int | None = None,
        session_id: str | None = None,
        project_id: int | None = None,
        privacy_level: str = "normal",
    ) -> int:
        event_summary = (
            summary
            or content
            or self._emotion_summary(emotion_tag, confidence, fatigue_score)
        )
        event_metadata = self._build_metadata(
            metadata,
            route=route,
            trigger=trigger,
            emotion_tag=emotion_tag,
            confidence=confidence,
            fatigue_score=fatigue_score,
            asr_text=asr_text,
            reply_text=reply_text,
            intervention_result=intervention_result,
        )
        return self._record_event(
            event_type="emotion.intervention",
            source=source,
            summary=event_summary,
            metadata=event_metadata,
            timestamp_ms=timestamp_ms,
            session_id=session_id,
            project_id=project_id,
            privacy_level=privacy_level,
        )

    def record_robot_care_action(
        self,
        *,
        content: str | None = None,
        summary: str | None = None,
        route: str | None = None,
        trigger: dict[str, Any] | None = None,
        action_name: str | None = None,
        emotion_tag: str | None = None,
        confidence: float | None = None,
        fatigue_score: float | None = None,
        asr_text: str | None = None,
        reply_text: str | None = None,
        robot_action_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        source: str = "robot_care",
        timestamp_ms: int | None = None,
        session_id: str | None = None,
        project_id: int | None = None,
        privacy_level: str = "normal",
    ) -> int:
        event_summary = summary or content or action_name or "robot care action"
        event_metadata = self._build_metadata(
            metadata,
            route=route,
            trigger=trigger,
            action_name=action_name,
            emotion_tag=emotion_tag,
            confidence=confidence,
            fatigue_score=fatigue_score,
            asr_text=asr_text,
            reply_text=reply_text,
            robot_action_result=robot_action_result,
        )
        return self._record_event(
            event_type="robot.care_action",
            source=source,
            summary=event_summary,
            metadata=event_metadata,
            timestamp_ms=timestamp_ms,
            session_id=session_id,
            project_id=project_id,
            privacy_level=privacy_level,
        )

    def _record_event(
        self,
        *,
        event_type: str,
        source: str,
        summary: str,
        metadata: dict[str, Any],
        timestamp_ms: int | None,
        session_id: str | None,
        project_id: int | None,
        privacy_level: str,
    ) -> int:
        payload = {
            "summary": summary,
            "content": summary,
            "metadata": self._json_safe(metadata),
        }
        insert_event = getattr(self.memory_store, "insert_event")
        return int(insert_event(
            event_type=event_type,
            source=source,
            text=summary,
            payload=payload,
            timestamp_ms=timestamp_ms,
            session_id=session_id,
            project_id=project_id,
            privacy_level=privacy_level,
        ))

    def _build_metadata(
        self,
        metadata: dict[str, Any] | None,
        **fields: Any,
    ) -> dict[str, Any]:
        active_metadata = dict(metadata or {})
        for key, value in fields.items():
            if value is not None:
                active_metadata[key] = value
        active_metadata.setdefault("recorded_at_ms", int(time.time() * 1000))
        return active_metadata

    def _emotion_summary(
        self,
        emotion_tag: str | None,
        confidence: float | None,
        fatigue_score: float | None,
    ) -> str:
        parts = []
        if emotion_tag is not None:
            parts.append(f"emotion={emotion_tag}")
        if fatigue_score is not None:
            parts.append(f"fatigue_score={fatigue_score}")
        if confidence is not None:
            parts.append(f"confidence={confidence}")
        return " ".join(parts) if parts else "emotion intervention"

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(item) for item in value]
        return str(value)
