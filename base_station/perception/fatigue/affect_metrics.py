from collections import Counter, defaultdict, deque

from base_station.perception.fatigue.face_metrics import evaluate_quality_gate


# Source of truth copied from demo2.py expression_labels on 2026-06-15:
# ["Neutral", "Happy", "Sad", "Surprise", "Fear", "Disgust", "Anger", "Contempt"].
EXPRESSION_LABELS = ["Neutral", "Happy", "Sad", "Surprise", "Fear", "Disgust", "Anger", "Contempt"]

# Provisional valence grouping for demo2.py's eight expression labels:
# Happy is positive; Neutral and Surprise are treated as neutral because the
# model label alone does not determine affect direction; threat/aversive labels
# are grouped negative.
LABEL_VALENCE = {
    "Neutral": "neutral",
    "Happy": "positive",
    "Sad": "negative",
    "Surprise": "neutral",
    "Fear": "negative",
    "Disgust": "negative",
    "Anger": "negative",
    "Contempt": "negative",
}

PRESENT_FACE_RATIO_MIN = 0.6
ABSENT_FACE_RATIO_MAX = 0.1
OBSERVATION_QUALITY_MIN = 0.5


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def _safe_ratio(numerator, denominator):
    if denominator <= 1e-6:
        return 0.0
    return float(numerator) / float(denominator)


def classify_valence(emotion_label):
    return LABEL_VALENCE.get(emotion_label, "uncertain")


class AffectWindow:
    def __init__(self, window_seconds=60.0):
        self.window_seconds = float(window_seconds)
        self._samples = deque()
        self._last_timestamp = 0.0

    def update(self, timestamp, face_detected, observation_quality, emotion_label=None, emotion_confidence=None):
        timestamp = float(timestamp)
        self._last_timestamp = timestamp
        sample = {
            "timestamp": timestamp,
            "face_detected": bool(face_detected),
            "observation_quality": _clamp01(observation_quality),
            "emotion_label": emotion_label,
            "emotion_confidence": None if emotion_confidence is None else _clamp01(emotion_confidence),
        }
        self._samples.append(sample)
        self._trim(timestamp)
        return self.affect_snapshot()

    def _trim(self, now):
        cutoff = float(now) - self.window_seconds
        self._samples = deque(sample for sample in self._samples if sample["timestamp"] >= cutoff)

    def affect_snapshot(self):
        observation_quality = self._latest_observation_quality()
        face_presence_ratio = self._face_presence_ratio()
        quality_gate = evaluate_quality_gate(observation_quality, q_min=OBSERVATION_QUALITY_MIN)

        if quality_gate.get("fatigue_level") == "insufficient_evidence":
            emotion_label = "uncertain"
            emotion_confidence = None
            valence = "uncertain"
            presence_state = "uncertain"
        else:
            emotion_label, emotion_confidence = self._smoothed_emotion()
            valence = classify_valence(emotion_label)
            presence_state = self._presence_state(face_presence_ratio, observation_quality)

        return {
            "timestamp_ms": int(round(self._last_timestamp * 1000.0)),
            "presence_state": presence_state,
            "face_presence_ratio": face_presence_ratio,
            "emotion_label": emotion_label,
            "emotion_confidence": emotion_confidence,
            "valence": valence,
            "observation_quality": observation_quality,
            "window_sec": self.window_seconds,
        }

    def _latest_observation_quality(self):
        if not self._samples:
            return 0.0
        return self._samples[-1]["observation_quality"]

    def _face_presence_ratio(self):
        if len(self._samples) < 2:
            return 0.0

        span = 0.0
        face_duration = 0.0
        previous = self._samples[0]
        for current in list(self._samples)[1:]:
            dt = max(0.0, current["timestamp"] - previous["timestamp"])
            span += dt
            if previous["face_detected"]:
                face_duration += dt
            previous = current

        return _safe_ratio(face_duration, span)

    def _presence_state(self, face_presence_ratio, observation_quality):
        # Provisional thresholds: present at >=0.6 face presence and >=0.5
        # observation quality; absent at <=0.1 face presence; otherwise uncertain.
        if face_presence_ratio <= ABSENT_FACE_RATIO_MAX:
            return "absent"
        if face_presence_ratio >= PRESENT_FACE_RATIO_MIN and observation_quality >= OBSERVATION_QUALITY_MIN:
            return "present"
        return "uncertain"

    def _smoothed_emotion(self):
        label_counts = Counter()
        confidence_by_label = defaultdict(list)
        for sample in self._samples:
            label = sample["emotion_label"]
            confidence = sample["emotion_confidence"]
            if (
                sample["face_detected"]
                and sample["observation_quality"] >= OBSERVATION_QUALITY_MIN
                and label in EXPRESSION_LABELS
                and confidence is not None
            ):
                label_counts[label] += 1
                confidence_by_label[label].append(confidence)

        if not label_counts:
            return "uncertain", None

        winning_label = sorted(label_counts.items(), key=lambda item: (-item[1], EXPRESSION_LABELS.index(item[0])))[0][0]
        confidences = confidence_by_label[winning_label]
        return winning_label, sum(confidences) / len(confidences)
