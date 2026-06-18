"""Map OpenFace 8-class emotion labels / valence to the legacy gate + DB vocabulary.

Kept in sync with OpenFace ``affect_metrics.classify_valence`` (EXPRESSION_LABELS
from demo2.py). Provisional groupings; see docs/fatigue_metrics_decisions.md.

Purpose: let the UNCHANGED ``VLMTriggerGate`` (which checks emotion_tag against
NEGATIVE_EMOTIONS = {tired, sad, anxious, stressed}) keep firing on OpenFace's
8-class labels, and derive the legacy ``polarity`` (正面/负面) for emotion.sample.
"""

from __future__ import annotations

# OpenFace MTL expression head labels (demo2.py expression_labels).
EXPRESSION_LABELS = ["Neutral", "Happy", "Sad", "Surprise", "Fear", "Disgust", "Anger", "Contempt"]

# Provisional valence grouping (mirrors affect_metrics.LABEL_VALENCE):
# Happy=positive; Neutral/Surprise=neutral (label alone does not fix direction);
# threat/aversive labels=negative.
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

# Map OpenFace negative labels onto the legacy gate vocabulary so the UNCHANGED
# gate fires. (No label maps to "tired" — fatigue is handled via fatigue_score.)
_NEGATIVE_LABEL_TO_GATE_TAG = {
    "Sad": "sad",
    "Fear": "anxious",
    "Anger": "stressed",
    "Disgust": "stressed",
    "Contempt": "stressed",
}


# Legacy gate negative vocabulary (mirrors VLMTriggerGate.NEGATIVE_EMOTIONS).
# Used to derive polarity for frames whose emotion_tag is ALREADY gate vocab
# (lowercase) but which carry no valence -- notably VLM-verdict frames, where the
# VLM emits a gate-vocab tag + no polarity.
GATE_NEGATIVE_TAGS = {"tired", "sad", "anxious", "stressed"}


def classify_valence(emotion_label):
    """OpenFace label -> positive/negative/neutral; unknown -> uncertain."""
    return LABEL_VALENCE.get(emotion_label, "uncertain")


def gate_tag_to_polarity(emotion_tag):
    """Gate-vocab tag (lowercase) -> legacy polarity (负面 if in the gate's
    negative set, else 正面). For tags already in gate vocabulary; does NOT go
    through the capitalized OpenFace LABEL_VALENCE map."""
    return "负面" if str(emotion_tag).lower() in GATE_NEGATIVE_TAGS else "正面"


def valence_to_polarity(valence):
    """valence -> legacy polarity. uncertain -> 正面 (conservative; never triggers负面)."""
    return "负面" if valence == "negative" else "正面"


def label_to_polarity(emotion_label):
    return valence_to_polarity(classify_valence(emotion_label))


def is_negative(emotion_label):
    return classify_valence(emotion_label) == "negative"


def to_gate_emotion_tag(emotion_label):
    """Token the legacy gate's NEGATIVE_EMOTIONS recognizes when the label is
    negative; otherwise the lowercased label (which won't match NEGATIVE set)."""
    if emotion_label in _NEGATIVE_LABEL_TO_GATE_TAG:
        return _NEGATIVE_LABEL_TO_GATE_TAG[emotion_label]
    return str(emotion_label).lower()
