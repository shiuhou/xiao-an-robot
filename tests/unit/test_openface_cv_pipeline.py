"""Unit tests for OpenFaceCVPipeline assembly (Phase III).

Uses synthetic WFLW-98 landmarks (open/closed eye, open/closed mouth) and a fake
`perceive` so the contract-assembly logic is tested without OV / real models.
"""

from __future__ import annotations

import unittest

import numpy as np

from base_station.perception.openface_cv_pipeline import OpenFaceCVPipeline
from base_station.perception.vlm_trigger_gate import NEGATIVE_EMOTIONS

CONTRACT_KEYS = {
    "source", "timestamp_ms", "frame_id", "emotion_tag", "confidence",
    "fatigue_score", "polarity", "fatigue_level", "observation_quality",
    "evidence_codes", "algorithm_version", "presence_state", "valence",
    "au_json", "frame_b64",
}


def make_landmarks(eye_open: bool, mouth_open: bool) -> np.ndarray:
    """Build a (98,2) array with controllable EAR (eyes) and MAR (mouth)."""
    pts = np.zeros((98, 2), dtype=np.float32)
    ev = 4.0 if eye_open else 0.0      # EAR ~= ev/10  -> open 0.4, closed 0.0
    mv = 12.0 if mouth_open else 2.0   # MAR ~= mv/10  -> open 1.2, closed 0.2

    def eye(base_idx, x0):
        # indices order: [0]=corner, [4]=corner (horizontal); (1,7)(2,6)(3,5) vertical
        pts[base_idx + 0] = (x0, 0.0)
        pts[base_idx + 4] = (x0 + 10.0, 0.0)
        for k, x in zip((1, 2, 3), (3.0, 5.0, 7.0)):
            pts[base_idx + k] = (x0 + x, ev / 2)
        for k, x in zip((7, 6, 5), (3.0, 5.0, 7.0)):
            pts[base_idx + k] = (x0 + x, -ev / 2)

    eye(60, 0.0)    # right eye 60..67
    eye(68, 20.0)   # left eye 68..75

    # inner lip 88..95: 88/92 horizontal; (89,95)(90,94)(91,93) vertical
    pts[88] = (0.0, 40.0)
    pts[92] = (10.0, 40.0)
    for k, x in zip((89, 90, 91), (3.0, 5.0, 7.0)):
        pts[k] = (x, 40.0 + mv / 2)
    for k, x in zip((95, 94, 93), (3.0, 5.0, 7.0)):
        pts[k] = (x, 40.0 - mv / 2)
    return pts


def perceive_factory(face=True, eye_open=True, mouth_open=False, conf=0.9,
                     emotion="Neutral", emo_conf=0.9):
    def perceive(_frame):
        if not face:
            return {"landmarks": None, "face_confidence": 0.0}
        return {
            "landmarks": make_landmarks(eye_open, mouth_open),
            "face_confidence": conf,
            "emotion_label": emotion,
            "emotion_confidence": emo_conf,
            "au": {"AU45": 0.5},
        }
    return perceive


def run(pipeline, n, *, start_ms=0, step_ms=200):
    last = None
    for i in range(n):
        last = pipeline.process_frame(object(), timestamp_ms=start_ms + i * step_ms)
    return last


class OpenFaceCVPipelineTest(unittest.TestCase):
    def test_contract_has_all_fields(self):
        p = OpenFaceCVPipeline(perceive_factory())
        out = run(p, 4)
        self.assertEqual(set(out), CONTRACT_KEYS)
        self.assertEqual(out["source"], "openface_fatigue_metrics")
        self.assertEqual(out["algorithm_version"], "rule_v0")

    def test_no_face_is_insufficient_and_none_score(self):
        p = OpenFaceCVPipeline(perceive_factory(face=False))
        out = run(p, 6)
        self.assertEqual(out["fatigue_level"], "insufficient_evidence")
        self.assertIsNone(out["fatigue_score"])
        self.assertIn(out["presence_state"], {"absent", "uncertain"})

    def test_long_eye_closure_triggers_high(self):
        # eyes closed; need window span >= 5s (min_span_seconds) for trusted quality
        p = OpenFaceCVPipeline(perceive_factory(eye_open=False))
        out = run(p, 30)  # ts 0..5.8s
        self.assertEqual(out["fatigue_level"], "high")
        self.assertIn("LONG_CLOSURE", out["evidence_codes"])
        self.assertIsNotNone(out["fatigue_score"])
        self.assertGreaterEqual(out["observation_quality"], 0.5)

    def test_open_eyes_good_quality_is_low(self):
        p = OpenFaceCVPipeline(perceive_factory(eye_open=True))
        out = run(p, 30)  # ts 0..5.8s
        self.assertEqual(out["fatigue_level"], "low")
        self.assertIsNotNone(out["fatigue_score"])

    def test_negative_emotion_sets_valence_and_gate_tag(self):
        p = OpenFaceCVPipeline(perceive_factory(emotion="Sad"))
        out = run(p, 30)  # ts 0..5.8s
        self.assertEqual(out["valence"], "negative")
        self.assertEqual(out["polarity"], "负面")
        # the UNCHANGED VLMTriggerGate must recognize this emotion_tag as negative
        self.assertIn(out["emotion_tag"], NEGATIVE_EMOTIONS)


if __name__ == "__main__":
    unittest.main()
