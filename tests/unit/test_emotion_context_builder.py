"""Unit tests for EmotionContextBuilder."""

from __future__ import annotations

import copy
import unittest

from base_station.monitor.emotion_context_builder import EmotionContextBuilder


def make_cv_sample() -> dict:
    return {
        "emotion_tag": "tired",
        "confidence": 0.9,
        "fatigue_score": 0.85,
        "source": "fake_face",
        "frame_source": "opencv_camera",
        "frame_id": 12,
        "timestamp_ms": 123456,
        "extra": "ignored",
    }


def make_vlm_sample() -> dict:
    return {
        "emotion_tag": "sad",
        "confidence": 0.84,
        "fatigue_score": 0.35,
        "visual_reason": "Facial expression appears downcast.",
        "vlm_observation": "The user may be feeling sad or low.",
        "source": "fake_qwen_vl",
        "frame_source": "opencv_camera",
        "frame_id": 12,
        "timestamp_ms": 123456,
        "extra": "ignored",
    }


def make_history_summary() -> dict:
    return {
        "count": 3,
        "avg_fatigue_score": 0.5,
        "top_emotion": "tired",
        "emotions_count": {"tired": 2, "neutral": 1},
    }


def make_asr_trigger_result() -> dict:
    return {
        "should_trigger": True,
        "reason": "fatigue_keyword",
        "matched_keyword": "累",
        "emotion_tag": "tired",
        "confidence": 0.75,
        "fatigue_score": 0.8,
    }


class EmotionContextBuilderTest(unittest.TestCase):
    def test_full_input_builds_full_context(self) -> None:
        context = EmotionContextBuilder().build(
            cv_sample=make_cv_sample(),
            vlm_sample=make_vlm_sample(),
            asr_text="我有点累",
            history_summary=make_history_summary(),
        )

        self.assertEqual(set(context), {"cv", "vlm", "asr", "history"})
        self.assertEqual(context["cv"]["emotion_tag"], "tired")
        self.assertEqual(context["vlm"]["emotion_tag"], "sad")
        self.assertEqual(context["asr"], {"text": "我有点累"})
        self.assertEqual(context["history"]["count"], 3)

    def test_cv_sample_metadata_is_preserved(self) -> None:
        context = EmotionContextBuilder().build(cv_sample=make_cv_sample())

        self.assertEqual(context["cv"]["source"], "fake_face")
        self.assertEqual(context["cv"]["frame_source"], "opencv_camera")
        self.assertEqual(context["cv"]["frame_id"], 12)
        self.assertEqual(context["cv"]["timestamp_ms"], 123456)
        self.assertNotIn("extra", context["cv"])

    def test_vlm_reason_and_observation_are_preserved(self) -> None:
        context = EmotionContextBuilder().build(vlm_sample=make_vlm_sample())

        self.assertEqual(context["vlm"]["visual_reason"], "Facial expression appears downcast.")
        self.assertEqual(context["vlm"]["vlm_observation"], "The user may be feeling sad or low.")

    def test_asr_none_outputs_empty_text(self) -> None:
        context = EmotionContextBuilder().build(asr_text=None)

        self.assertEqual(context["asr"], {"text": ""})

    def test_asr_text_without_trigger_keeps_old_shape(self) -> None:
        context = EmotionContextBuilder().build(asr_text="我有点累")

        self.assertEqual(context["asr"], {"text": "我有点累"})

    def test_asr_text_with_trigger_result_preserves_trigger(self) -> None:
        trigger_result = make_asr_trigger_result()

        context = EmotionContextBuilder().build(
            asr_text="我有点累",
            asr_trigger_result=trigger_result,
        )

        self.assertEqual(context["asr"]["text"], "我有点累")
        self.assertEqual(context["asr"]["trigger"], trigger_result)

    def test_asr_trigger_fields_are_preserved(self) -> None:
        context = EmotionContextBuilder().build(
            asr_text="我有点累",
            asr_trigger_result=make_asr_trigger_result(),
        )

        trigger = context["asr"]["trigger"]
        self.assertEqual(trigger["should_trigger"], True)
        self.assertEqual(trigger["reason"], "fatigue_keyword")
        self.assertEqual(trigger["matched_keyword"], "累")
        self.assertEqual(trigger["emotion_tag"], "tired")
        self.assertEqual(trigger["confidence"], 0.75)
        self.assertEqual(trigger["fatigue_score"], 0.8)

    def test_missing_asr_trigger_result_does_not_error(self) -> None:
        context = EmotionContextBuilder().build(asr_text="帮我查一下天气")

        self.assertEqual(context["asr"]["text"], "帮我查一下天气")
        self.assertNotIn("trigger", context["asr"])

    def test_asr_trigger_without_text_does_not_crash(self) -> None:
        trigger_result = make_asr_trigger_result()

        context = EmotionContextBuilder().build(asr_trigger_result=trigger_result)

        self.assertEqual(context["asr"]["text"], "")
        self.assertEqual(context["asr"]["trigger"], trigger_result)

    def test_missing_history_outputs_default_history(self) -> None:
        context = EmotionContextBuilder().build(history_summary=None)

        self.assertEqual(context["history"], {
            "count": 0,
            "avg_fatigue_score": 0.0,
            "top_emotion": None,
            "emotions_count": {},
        })

    def test_missing_cv_sample_outputs_none(self) -> None:
        context = EmotionContextBuilder().build(cv_sample=None)

        self.assertIsNone(context["cv"])

    def test_missing_vlm_sample_outputs_none(self) -> None:
        context = EmotionContextBuilder().build(vlm_sample=None)

        self.assertIsNone(context["vlm"])

    def test_partial_inputs_do_not_raise(self) -> None:
        context = EmotionContextBuilder().build(
            cv_sample={"emotion_tag": "neutral"},
            vlm_sample={"visual_reason": "No clear signal."},
            history_summary={"count": 1},
        )

        self.assertEqual(context["cv"]["emotion_tag"], "neutral")
        self.assertIsNone(context["cv"]["confidence"])
        self.assertEqual(context["vlm"]["visual_reason"], "No clear signal.")
        self.assertIsNone(context["vlm"]["emotion_tag"])
        self.assertEqual(context["history"]["count"], 1)
        self.assertEqual(context["history"]["avg_fatigue_score"], 0.0)

    def test_build_does_not_modify_inputs(self) -> None:
        cv_sample = make_cv_sample()
        vlm_sample = make_vlm_sample()
        history_summary = make_history_summary()
        original_cv = copy.deepcopy(cv_sample)
        original_vlm = copy.deepcopy(vlm_sample)
        original_history = copy.deepcopy(history_summary)

        EmotionContextBuilder().build(
            cv_sample=cv_sample,
            vlm_sample=vlm_sample,
            asr_text="hello",
            asr_trigger_result=make_asr_trigger_result(),
            history_summary=history_summary,
        )

        self.assertEqual(cv_sample, original_cv)
        self.assertEqual(vlm_sample, original_vlm)
        self.assertEqual(history_summary, original_history)


if __name__ == "__main__":
    unittest.main()
