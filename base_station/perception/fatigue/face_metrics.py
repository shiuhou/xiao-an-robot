from collections import deque

import numpy as np


WFLW98_RIGHT_EYE = tuple(range(60, 68))
WFLW98_LEFT_EYE = tuple(range(68, 76))
WFLW98_OUTER_LIP = tuple(range(76, 88))
WFLW98_INNER_LIP = tuple(range(88, 96))
WFLW98_LEFT_PUPIL = 96
WFLW98_RIGHT_PUPIL = 97
DEFAULT_EAR_CLOSED_THRESHOLD = 0.15
DEFAULT_MAR_YAWN_THRESHOLD = 0.9


def _as_landmarks_array(landmarks):
    points = np.asarray(landmarks, dtype=np.float32)
    if points.shape[0] < 98 or points.shape[1] != 2:
        raise ValueError(f"Expected landmark array shaped at least (98, 2), got {points.shape}")
    return points


def _distance(point_a, point_b):
    return float(np.linalg.norm(point_a - point_b))


def _ratio(numerator, denominator):
    if denominator <= 1e-6:
        return None
    return numerator / denominator


def _safe_ratio(numerator, denominator):
    if denominator <= 1e-6:
        return 0.0
    return float(numerator) / float(denominator)


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def _eye_aspect_ratio(points, indices):
    p = points
    horizontal = _distance(p[indices[0]], p[indices[4]])
    vertical = (
        _distance(p[indices[1]], p[indices[7]])
        + _distance(p[indices[2]], p[indices[6]])
        + _distance(p[indices[3]], p[indices[5]])
    ) / 3.0
    return _ratio(vertical, horizontal)


def compute_ear(landmarks):
    points = _as_landmarks_array(landmarks)
    right_ear = _eye_aspect_ratio(points, WFLW98_RIGHT_EYE)
    left_ear = _eye_aspect_ratio(points, WFLW98_LEFT_EYE)
    values = [value for value in (right_ear, left_ear) if value is not None]
    if not values:
        return None
    return float(np.mean(values))


def compute_mar(landmarks):
    points = _as_landmarks_array(landmarks)
    horizontal = _distance(points[88], points[92])
    vertical = (
        _distance(points[89], points[95])
        + _distance(points[90], points[94])
        + _distance(points[91], points[93])
    ) / 3.0
    return _ratio(vertical, horizontal)


def classify_face_metrics(
    ear,
    mar,
    ear_closed_threshold=DEFAULT_EAR_CLOSED_THRESHOLD,
    mar_yawn_threshold=DEFAULT_MAR_YAWN_THRESHOLD,
):
    return {
        "eye_closed": ear is not None and float(ear) < float(ear_closed_threshold),
        "yawning": mar is not None and float(mar) > float(mar_yawn_threshold),
    }


def should_run_periodic_task(update_count, every_n, enabled=True):
    if not enabled or every_n <= 0:
        return False
    return update_count == 1 or update_count % every_n == 0


def evaluate_quality_gate(observation_quality, q_min=0.5):
    if float(observation_quality) < float(q_min):
        return {"fatigue_level": "insufficient_evidence", "fatigue_risk_score": None}
    return {"gate": "pass"}


def classify_fatigue_v0(
    observation_quality,
    perclos,
    continuous_closure_s,
    yawn_count_window,
    q_min=0.5,
    perclos_high=0.20,
    perclos_mid=0.10,
    long_closure_s=1.0,
):
    # Provisional demo-only thresholds and scores. This is not a validated
    # accuracy model; it exists to make realtime evidence visible on screen.
    observation_quality = float(observation_quality)
    perclos = float(perclos)
    continuous_closure_s = float(continuous_closure_s)
    yawn_count_window = int(yawn_count_window)
    q_min = float(q_min)
    perclos_high = float(perclos_high)
    perclos_mid = float(perclos_mid)
    long_closure_s = float(long_closure_s)

    rules = [
        {
            "code": "LONG_CLOSURE",
            "label": "Long closure",
            "value": continuous_closure_s,
            "threshold": long_closure_s,
            "unit": "s",
            "tier": "strong",
            "fired": continuous_closure_s >= long_closure_s,
        },
        {
            "code": "PERCLOS_HIGH",
            "label": "PERCLOS high",
            "value": perclos,
            "threshold": perclos_high,
            "unit": "%",
            "tier": "strong",
            "fired": perclos >= perclos_high,
        },
        {
            "code": "PERCLOS_MID",
            "label": "PERCLOS mid",
            "value": perclos,
            "threshold": perclos_mid,
            "unit": "%",
            "tier": "aux",
            "fired": perclos >= perclos_mid,
        },
        {
            "code": "YAWN",
            "label": "Yawn",
            "value": yawn_count_window,
            "threshold": 1,
            "unit": "",
            "tier": "aux",
            "fired": yawn_count_window >= 1,
        },
        {
            "code": "QUALITY",
            "label": "Quality",
            "value": observation_quality,
            "threshold": q_min,
            "unit": "",
            "tier": "gate",
            "fired": observation_quality >= q_min,
        },
    ]

    if observation_quality < q_min:
        return {"level": "insufficient_evidence", "score": None, "evidence": [], "rules": rules}

    high_evidence = []
    if continuous_closure_s >= long_closure_s:
        high_evidence.append("LONG_CLOSURE")
    if perclos >= perclos_high:
        high_evidence.append("PERCLOS_HIGH")
    if high_evidence:
        score = 67 + min(33, int(round(max(perclos - perclos_high, 0.0) * 100)))
        return {"level": "HIGH", "score": score, "evidence": high_evidence, "rules": rules}

    medium_evidence = []
    if yawn_count_window >= 1:
        medium_evidence.append("YAWN")
    if perclos >= perclos_mid:
        medium_evidence.append("PERCLOS_MID")
    if medium_evidence:
        score = 34 + min(32, int(round(max(perclos - perclos_mid, 0.0) * 100)))
        return {"level": "MEDIUM", "score": score, "evidence": medium_evidence, "rules": rules}

    score = min(33, int(round(max(perclos, 0.0) * 100)))
    return {"level": "LOW", "score": score, "evidence": [], "rules": rules}


class WindowAccumulator:
    def __init__(self, window_seconds=60.0):
        self.window_seconds = float(window_seconds)
        self.min_span_seconds = 5.0
        self._samples = deque()

    def update(self, timestamp, face_detected, landmarks_valid, face_confidence, eye_closed):
        sample = {
            "timestamp": float(timestamp),
            "face_detected": bool(face_detected),
            "landmarks_valid": bool(landmarks_valid),
            "face_confidence": _clamp01(face_confidence),
            "eye_closed": bool(eye_closed),
        }
        self._samples.append(sample)
        self._trim(sample["timestamp"])
        return self.snapshot

    def _trim(self, now):
        cutoff = float(now) - self.window_seconds
        self._samples = deque(sample for sample in self._samples if sample["timestamp"] >= cutoff)

    @property
    def snapshot(self):
        if len(self._samples) < 2:
            return self._empty_snapshot()

        face_duration = 0.0
        valid_duration = 0.0
        landmark_valid_duration = 0.0
        closed_duration = 0.0
        confidence_weighted_sum = 0.0
        confidence_duration = 0.0
        window_span = 0.0

        previous = self._samples[0]
        for current in list(self._samples)[1:]:
            dt = max(0.0, current["timestamp"] - previous["timestamp"])
            window_span += dt

            if previous["face_detected"]:
                face_duration += dt
                confidence_weighted_sum += previous["face_confidence"] * dt
                confidence_duration += dt
                if previous["landmarks_valid"]:
                    landmark_valid_duration += dt
                    valid_duration += dt
                    if previous["eye_closed"]:
                        closed_duration += dt

            previous = current

        face_presence_ratio = _safe_ratio(face_duration, window_span)
        landmark_valid_ratio = _safe_ratio(landmark_valid_duration, face_duration)
        valid_frame_ratio = _safe_ratio(valid_duration, window_span)
        perclos = _safe_ratio(closed_duration, valid_duration)
        mean_face_confidence = _clamp01(_safe_ratio(confidence_weighted_sum, confidence_duration))

        observation_quality = min(
            valid_frame_ratio,
            face_presence_ratio,
            landmark_valid_ratio,
            mean_face_confidence,
        )
        if window_span < self.min_span_seconds:
            observation_quality = 0.0

        return {
            "window_span_seconds": window_span,
            "face_duration": face_duration,
            "valid_duration": valid_duration,
            "closed_duration": closed_duration,
            "face_presence_ratio": face_presence_ratio,
            "landmark_valid_ratio": landmark_valid_ratio,
            "valid_frame_ratio": valid_frame_ratio,
            "mean_face_confidence": mean_face_confidence,
            "perclos": perclos,
            "observation_quality": observation_quality,
            "quality_gate": evaluate_quality_gate(observation_quality),
        }

    def _empty_snapshot(self):
        return {
            "window_span_seconds": 0.0,
            "face_duration": 0.0,
            "valid_duration": 0.0,
            "closed_duration": 0.0,
            "face_presence_ratio": 0.0,
            "landmark_valid_ratio": 0.0,
            "valid_frame_ratio": 0.0,
            "mean_face_confidence": 0.0,
            "perclos": 0.0,
            "observation_quality": 0.0,
            "quality_gate": evaluate_quality_gate(0.0),
        }


class EyeClosureTracker:
    def __init__(self, ear_threshold=DEFAULT_EAR_CLOSED_THRESHOLD, window_seconds=30.0):
        self.ear_threshold = float(ear_threshold)
        self.window_seconds = float(window_seconds)
        self._window = WindowAccumulator(window_seconds=window_seconds)
        self._snapshot = self._window.snapshot

    def update(self, timestamp, ear, face_found=True):
        face_detected = bool(face_found)
        landmarks_valid = face_detected and ear is not None
        eye_closed = landmarks_valid and float(ear) < self.ear_threshold
        self._snapshot = self._window.update(
            timestamp=float(timestamp),
            face_detected=face_detected,
            landmarks_valid=landmarks_valid,
            face_confidence=1.0 if face_detected else 0.0,
            eye_closed=eye_closed,
        )
        return self.perclos

    def _trim(self, now):
        self._window._trim(now)
        self._snapshot = self._window.snapshot

    @property
    def perclos(self):
        return self._snapshot["perclos"]


class FaceEventCounter:
    def __init__(self, max_blink_seconds=0.8):
        self.blink_count = 0
        self.yawn_count = 0
        self._was_eye_closed = False
        self._was_yawning = False
        self._eye_closed_since = None
        self.max_blink_seconds = float(max_blink_seconds)

    def update(self, states, timestamp=None):
        timestamp = 0.0 if timestamp is None else float(timestamp)
        if not states:
            self._was_eye_closed = False
            self._was_yawning = False
            self._eye_closed_since = None
            return self.snapshot

        eye_closed = bool(states.get("eye_closed"))
        yawning = bool(states.get("yawning"))

        if eye_closed and not self._was_eye_closed:
            self._eye_closed_since = timestamp
        elif not eye_closed and self._was_eye_closed and self._eye_closed_since is not None:
            closed_seconds = timestamp - self._eye_closed_since
            if 0.0 <= closed_seconds <= self.max_blink_seconds:
                self.blink_count += 1
            self._eye_closed_since = None

        if yawning and not self._was_yawning:
            self.yawn_count += 1

        self._was_eye_closed = eye_closed
        self._was_yawning = yawning
        return self.snapshot

    @property
    def snapshot(self):
        return {
            "blink_count": self.blink_count,
            "yawn_count": self.yawn_count,
        }
