"""In-process OpenFace CV pipeline: camera frame -> contract cv_sample.

Heavy model inference (RetinaFace face box, STAR 98-pt landmarks, MTL
emotion/gaze/AU) is INJECTED as a single ``perceive(frame) -> dict`` callable, so
this assembly layer is fully unit-testable without OpenVINO or real models.

The production ``perceive`` wraps tools/ov_runner.OVModelRunner (3 OV IR models)
+ RetinaFace/STAR host-side decode, and is wired on the conda 'openface' env
(that wiring + real-frame parity is a user verification gate).

``perceive`` must return a dict with (all optional, absent => treated as no-signal):
    landmarks        : np.ndarray (98, 2) WFLW points, or None if no face
    face_confidence  : float 0..1
    emotion_label    : str (one of EXPRESSION_LABELS) or None
    emotion_confidence: float 0..1 or None
    au               : the 8-dim AU vector/dict (recorded only; not used in judgment)

process_frame() returns the perception contract (docs/perception_contract.md):
    source/timestamp_ms/frame_id/emotion_tag/confidence/fatigue_score/polarity/
    fatigue_level/observation_quality/evidence_codes/algorithm_version/
    presence_state/valence/au_json/frame_b64
Plugs in as the `cv_pipeline.process_frame` consumed by VLMGatedCameraEmotionSource.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable

from base_station.perception import valence_mapping as vm
from base_station.perception.fatigue.affect_metrics import AffectWindow
from base_station.perception.fatigue.face_metrics import (
    DEFAULT_EAR_CLOSED_THRESHOLD,
    DEFAULT_MAR_YAWN_THRESHOLD,
    WindowAccumulator,
    classify_fatigue_v0,
    compute_ear,
    compute_mar,
)


class OpenFaceCVPipeline:
    def __init__(
        self,
        perceive: Callable[[Any], dict],
        window_seconds: float = 20.0,
        ear_threshold: float = DEFAULT_EAR_CLOSED_THRESHOLD,
        mar_yawn_threshold: float = DEFAULT_MAR_YAWN_THRESHOLD,
        long_closure_s: float = 1.0,
    ):
        self.perceive = perceive
        self.window_seconds = float(window_seconds)
        self.ear_threshold = float(ear_threshold)
        self.mar_yawn_threshold = float(mar_yawn_threshold)
        self.long_closure_s = float(long_closure_s)

        self._window = WindowAccumulator(window_seconds=self.window_seconds)
        self._affect = AffectWindow(window_seconds=self.window_seconds)
        self._closed_since: float | None = None
        self._yawn_active = False
        self._yawn_onsets: deque[float] = deque()
        self._frame_id = 0

    def process_frame(self, frame: Any, timestamp_ms: int | None = None) -> dict:
        ts_ms = int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms)
        ts_s = ts_ms / 1000.0
        self._frame_id += 1

        obs = self.perceive(frame) or {}
        landmarks = obs.get("landmarks")
        face_confidence = float(obs.get("face_confidence", 0.0) or 0.0)
        raw_emotion_label = obs.get("emotion_label")
        raw_emotion_conf = obs.get("emotion_confidence")
        au = obs.get("au")

        face_detected = landmarks is not None
        landmarks_valid = face_detected
        ear = mar = None
        eye_closed = False
        if face_detected:
            ear = compute_ear(landmarks)
            mar = compute_mar(landmarks)
            eye_closed = ear is not None and ear < self.ear_threshold

        # continuous eye-closure timer (real timestamps, not frame count)
        if eye_closed:
            if self._closed_since is None:
                self._closed_since = ts_s
            continuous_closure_s = max(0.0, ts_s - self._closed_since)
        else:
            self._closed_since = None
            continuous_closure_s = 0.0

        # yawn onsets within the time window
        yawning = (mar is not None) and (mar > self.mar_yawn_threshold)
        if yawning and not self._yawn_active:
            self._yawn_onsets.append(ts_s)
        self._yawn_active = yawning
        cutoff = ts_s - self.window_seconds
        while self._yawn_onsets and self._yawn_onsets[0] < cutoff:
            self._yawn_onsets.popleft()
        yawn_count_window = len(self._yawn_onsets)

        snap = self._window.update(ts_s, face_detected, landmarks_valid, face_confidence, eye_closed)
        observation_quality = snap["observation_quality"]
        perclos = snap["perclos"]

        fatigue = classify_fatigue_v0(
            observation_quality,
            perclos,
            continuous_closure_s,
            yawn_count_window,
            long_closure_s=self.long_closure_s,
        )
        fatigue_level = str(fatigue["level"]).lower()  # contract is lowercase

        affect = self._affect.update(
            ts_s, face_detected, observation_quality,
            emotion_label=raw_emotion_label, emotion_confidence=raw_emotion_conf,
        )
        smoothed_label = affect.get("emotion_label")
        valence = affect.get("valence", "uncertain")

        # Legacy-compatible emotion fields so the UNCHANGED VLMTriggerGate still fires.
        emotion_tag = vm.to_gate_emotion_tag(smoothed_label) if smoothed_label else "neutral"
        confidence = float(affect.get("emotion_confidence") or 0.0)

        return {
            "source": "openface_fatigue_metrics",
            "timestamp_ms": ts_ms,
            "frame_id": self._frame_id,
            # legacy fields
            "emotion_tag": emotion_tag,
            "confidence": confidence,
            "fatigue_score": fatigue["score"],          # None when insufficient_evidence
            "polarity": vm.valence_to_polarity(valence),
            # new engine fields
            "fatigue_level": fatigue_level,
            "observation_quality": observation_quality,
            "evidence_codes": fatigue["evidence"],
            "algorithm_version": "rule_v0",
            "presence_state": affect.get("presence_state", "uncertain"),
            "valence": valence,
            "au_json": au,                              # recorded only (not in judgment)
            "frame_b64": None,                          # attached later only on VLM-trigger frames
        }
