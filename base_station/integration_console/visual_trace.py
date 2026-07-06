"""Publish failure-isolated Route A snapshots for the Integration Console."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from base_station.perception.fatigue.face_metrics import (
    DEFAULT_EAR_CLOSED_THRESHOLD,
    DEFAULT_MAR_YAWN_THRESHOLD,
    WFLW98_INNER_LIP,
    WFLW98_LEFT_EYE,
    WFLW98_OUTER_LIP,
    WFLW98_RIGHT_EYE,
    compute_ear,
    compute_mar,
)


SCHEMA_VERSION = "visual_console_v1"
OWNED_FILENAMES = {
    "latest_annotated.jpg",
    "latest_state.json",
    "vlm_trigger.jpg",
    "vlm_state.json",
}


def project_landmarks_to_frame(observation: dict[str, Any] | None) -> np.ndarray | None:
    if not observation or observation.get("landmarks") is None:
        return None
    points = np.asarray(observation["landmarks"], dtype=np.float32)
    if points.ndim != 2 or points.shape[0] < 98 or points.shape[1] != 2:
        return None
    projected = points.copy()
    bbox = observation.get("face_bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        projected[:, 0] += float(bbox[0])
        projected[:, 1] += float(bbox[1])
    return projected


def _draw_contour(image: np.ndarray, points: np.ndarray, indices, color) -> None:
    contour = points[list(indices)].reshape((-1, 1, 2))
    cv2.polylines(image, [contour], True, color, 2, cv2.LINE_AA)


def render_annotated_frame(
    frame: dict[str, Any],
    observation: dict[str, Any] | None,
    cv_sample: dict[str, Any],
    gate_diagnostics: dict[str, Any],
) -> np.ndarray:
    payload = frame.get("payload") if isinstance(frame, dict) else None
    if not isinstance(payload, np.ndarray) or payload.ndim != 3:
        raise ValueError("visual trace frame payload must be a BGR image")
    image = payload.copy()
    points = project_landmarks_to_frame(observation)
    if points is None:
        cv2.putText(
            image, "NO FACE", (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
            0.65, (0, 200, 255), 2, cv2.LINE_AA,
        )
        return image

    bbox = observation.get("face_bbox") if observation else None
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
        cv2.rectangle(image, (x1, y1), (x2, y2), (40, 210, 90), 2, cv2.LINE_AA)

    rounded = np.rint(points).astype(np.int32)
    for x, y in rounded:
        cv2.circle(image, (int(x), int(y)), 1, (80, 210, 130), -1, cv2.LINE_AA)

    evidence = {str(code) for code in cv_sample.get("evidence_codes") or []}
    try:
        ear = compute_ear(observation["landmarks"])
        mar = compute_mar(observation["landmarks"])
    except (KeyError, TypeError, ValueError):
        ear = mar = None
    eyes_alert = (ear is not None and ear < DEFAULT_EAR_CLOSED_THRESHOLD) or bool(
        evidence.intersection({"LONG_CLOSURE", "PERCLOS_HIGH", "PERCLOS_MID"})
    )
    mouth_alert = (mar is not None and mar > DEFAULT_MAR_YAWN_THRESHOLD) or "YAWN" in evidence
    eye_color = (30, 30, 235) if eyes_alert else (0, 220, 255)
    mouth_color = (30, 30, 235) if mouth_alert else (255, 120, 60)
    _draw_contour(image, rounded, WFLW98_RIGHT_EYE, eye_color)
    _draw_contour(image, rounded, WFLW98_LEFT_EYE, eye_color)
    _draw_contour(image, rounded, WFLW98_OUTER_LIP, mouth_color)
    _draw_contour(image, rounded, WFLW98_INNER_LIP, mouth_color)

    frame_id = cv_sample.get("frame_id", frame.get("frame_id", "-"))
    reason = (gate_diagnostics.get("result") or {}).get("reason", "normal")
    cv2.putText(
        image, f"frame {frame_id} | gate {reason}", (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 255), 2, cv2.LINE_AA,
    )
    return image


class VisualTracePublisher:
    """Atomically publish the latest bounded visual trace state."""

    def __init__(
        self,
        output_dir: str | Path,
        max_fps: float = 2.0,
        wall_clock: Callable[[], float] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        if max_fps <= 0:
            raise ValueError("max_fps must be positive")
        self.output_dir = Path(output_dir)
        self.min_interval_seconds = 1.0 / float(max_fps)
        self.wall_clock = wall_clock or time.time
        self.monotonic_clock = monotonic_clock or time.monotonic
        self._last_published_monotonic = float("-inf")
        self._latest_state: dict[str, Any] = {}
        self._vlm_state: dict[str, Any] = {"status": "idle"}
        self._active_request_id: str | None = None

    def observe_frame(
        self,
        *,
        frame: dict[str, Any],
        observation: dict[str, Any] | None,
        cv_sample: dict[str, Any],
        gate_diagnostics: dict[str, Any],
    ) -> dict[str, Any] | None:
        now_monotonic = self.monotonic_clock()
        triggered = bool((gate_diagnostics.get("result") or {}).get("should_trigger"))
        if (
            not triggered
            and now_monotonic - self._last_published_monotonic < self.min_interval_seconds
        ):
            return None

        image = render_annotated_frame(frame, observation, cv_sample, gate_diagnostics)
        ok, encoded = cv2.imencode(".jpg", image)
        if not ok:
            raise RuntimeError("failed to encode visual trace JPEG")
        jpeg = encoded.tobytes()
        published_at_ms = int(self.wall_clock() * 1000)
        frame_id = int(cv_sample.get("frame_id") or frame.get("frame_id") or 0)
        snapshot_id = f"frame-{frame_id}-{published_at_ms}"
        state = self._build_latest_state(
            snapshot_id=snapshot_id,
            frame_id=frame_id,
            published_at_ms=published_at_ms,
            frame=frame,
            observation=observation,
            cv_sample=cv_sample,
            gate_diagnostics=gate_diagnostics,
        )
        self._atomic_write_bytes(self.output_dir / "latest_annotated.jpg", jpeg)
        self._atomic_write_json(self.output_dir / "latest_state.json", state)
        self._latest_state = state
        self._last_published_monotonic = now_monotonic
        token: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "frame_id": frame_id,
            "jpeg": jpeg,
        }
        return token

    def vlm_started(self, token: dict[str, Any] | None, reason: str) -> str | None:
        if not isinstance(token, dict) or not token.get("jpeg"):
            return None
        request_id = f"vlm-{uuid.uuid4().hex[:12]}"
        self._atomic_write_bytes(self.output_dir / "vlm_trigger.jpg", token["jpeg"])
        self._write_vlm_state(request_id, token, status="running", reason=reason)
        return request_id

    def vlm_finished(
        self,
        request_id: str | None,
        *,
        status: str,
        vlm_result: dict[str, Any],
        final_sample: dict[str, Any] | None,
        latency_ms: float,
    ) -> None:
        if not request_id or request_id != self._active_request_id:
            return
        state = dict(self._vlm_state)
        state.update({
            "status": status,
            "completed_at_ms": int(self.wall_clock() * 1000),
            "latency_ms": round(float(latency_ms), 1),
            "result": self._json_safe(vlm_result),
            "fusion": self._json_safe((final_sample or {}).get("fusion")),
        })
        self._vlm_state = state
        self._atomic_write_json(self.output_dir / "vlm_state.json", state)
        self._sync_vlm_to_latest()

    def _build_latest_state(
        self,
        *,
        snapshot_id: str,
        frame_id: int,
        published_at_ms: int,
        frame: dict[str, Any],
        observation: dict[str, Any] | None,
        cv_sample: dict[str, Any],
        gate_diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        metrics = self._observation_metrics(observation)
        return {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "frame_id": frame_id,
            "timestamp_ms": int(cv_sample.get("timestamp_ms") or frame.get("timestamp_ms") or 0),
            "published_at_ms": published_at_ms,
            "image": {
                "width": int(frame.get("width") or 0),
                "height": int(frame.get("height") or 0),
                "annotated": True,
            },
            "observation": metrics,
            "cv_sample": self._json_safe(cv_sample),
            "gate": self._json_safe(gate_diagnostics),
            "vlm": self._json_safe(self._vlm_state),
        }

    @staticmethod
    def _observation_metrics(observation: dict[str, Any] | None) -> dict[str, Any]:
        if not observation or observation.get("landmarks") is None:
            return {
                "face_detected": False,
                "ear": None,
                "mar": None,
            }
        try:
            ear = compute_ear(observation["landmarks"])
            mar = compute_mar(observation["landmarks"])
        except (TypeError, ValueError):
            ear = mar = None
        return {
            "face_detected": True,
            "face_bbox": VisualTracePublisher._json_safe(observation.get("face_bbox")),
            "face_confidence": observation.get("face_confidence"),
            "emotion_label": observation.get("emotion_label"),
            "emotion_confidence": observation.get("emotion_confidence"),
            "ear": ear,
            "mar": mar,
            "au": VisualTracePublisher._json_safe(observation.get("au")),
        }

    def _write_vlm_state(
        self,
        request_id: str,
        token: dict[str, Any],
        *,
        status: str,
        reason: str | None = None,
    ) -> None:
        previous = self._vlm_state if request_id == self._active_request_id else {}
        state = {
            **previous,
            "request_id": request_id,
            "trigger_snapshot_id": token.get("snapshot_id"),
            "trigger_frame_id": token.get("frame_id"),
            "reason": reason or previous.get("reason") or "",
            "status": status,
        }
        if status == "queued":
            state["queued_at_ms"] = int(self.wall_clock() * 1000)
        if status == "running":
            state["started_at_ms"] = int(self.wall_clock() * 1000)
        self._active_request_id = request_id
        self._vlm_state = state
        self._atomic_write_json(self.output_dir / "vlm_state.json", state)
        self._sync_vlm_to_latest()

    def _sync_vlm_to_latest(self) -> None:
        if not self._latest_state:
            return
        self._latest_state["vlm"] = self._json_safe(self._vlm_state)
        self._atomic_write_json(self.output_dir / "latest_state.json", self._latest_state)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, dict):
            return {
                str(key): VisualTracePublisher._json_safe(item)
                for key, item in value.items()
                if key not in {"payload", "frame_b64", "landmarks"}
            }
        if isinstance(value, (list, tuple)):
            return [VisualTracePublisher._json_safe(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _atomic_write_bytes(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, path)

    @classmethod
    def _atomic_write_json(cls, path: Path, value: dict[str, Any]) -> None:
        payload = json.dumps(
            cls._json_safe(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        cls._atomic_write_bytes(path, payload)
