"""Unit tests for OpenVINOQwenVLEmotionModel."""

from __future__ import annotations

import json
import unittest

from base_station.perception.openvino_qwen_vl_emotion_model import OpenVINOQwenVLEmotionModel


class FakeRunner:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def generate(self, image, prompt: str, context: dict | None = None) -> str:
        self.calls.append({
            "image": image,
            "prompt": prompt,
            "context": context,
        })
        return self.response


def make_frame(payload: object = "image") -> dict:
    frame = {
        "source": "opencv_camera",
        "frame_id": 42,
        "timestamp_ms": 123456,
        "width": 640,
        "height": 480,
    }
    if payload is not None:
        frame["payload"] = payload
    return frame


def qwen_json(**overrides) -> str:
    payload = {
        "emotion_tag": "tired",
        "confidence": 0.9,
        "fatigue_score": 0.85,
        "visual_reason": "Eyes look heavy.",
        "vlm_observation": "The user appears tired.",
    }
    payload.update(overrides)
    return json.dumps(payload)


class OpenVINOQwenVLEmotionModelTest(unittest.TestCase):
    def test_predict_calls_runner_generate(self) -> None:
        runner = FakeRunner(qwen_json())
        model = OpenVINOQwenVLEmotionModel(runner)

        model.predict(make_frame())

        self.assertEqual(len(runner.calls), 1)
        self.assertIn("Return JSON only", runner.calls[0]["prompt"])

    def test_plain_json_is_parsed_into_emotion_sample(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner(qwen_json()))

        sample = model.predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "tired")
        self.assertEqual(sample["confidence"], 0.9)
        self.assertEqual(sample["fatigue_score"], 0.85)
        self.assertEqual(sample["visual_reason"], "Eyes look heavy.")
        self.assertEqual(sample["vlm_observation"], "The user appears tired.")
        self.assertEqual(sample["source"], "openvino_qwen_vl")

    def test_markdown_fenced_json_is_parsed(self) -> None:
        response = "```json\n" + qwen_json(emotion_tag="sad") + "\n```"
        model = OpenVINOQwenVLEmotionModel(FakeRunner(response))

        sample = model.predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "sad")

    def test_text_around_json_is_parsed(self) -> None:
        response = "Here is the result:\n" + qwen_json(emotion_tag="anxious") + "\nThanks."
        model = OpenVINOQwenVLEmotionModel(FakeRunner(response))

        sample = model.predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "anxious")

    def test_frame_metadata_is_preserved(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner(qwen_json()))

        sample = model.predict(make_frame())

        self.assertEqual(sample["frame_source"], "opencv_camera")
        self.assertEqual(sample["frame_id"], 42)
        self.assertEqual(sample["timestamp_ms"], 123456)

    def test_payload_is_passed_as_image_to_runner(self) -> None:
        runner = FakeRunner(qwen_json())
        model = OpenVINOQwenVLEmotionModel(runner)
        image = object()

        model.predict(make_frame(payload=image))

        self.assertIs(runner.calls[0]["image"], image)

    def test_frame_is_passed_as_image_when_payload_missing(self) -> None:
        runner = FakeRunner(qwen_json())
        model = OpenVINOQwenVLEmotionModel(runner)
        frame = make_frame(payload=None)

        model.predict(frame)

        self.assertIs(runner.calls[0]["image"], frame)

    def test_confidence_and_fatigue_are_clamped(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner(qwen_json(confidence=1.5, fatigue_score=-0.2)))

        sample = model.predict(make_frame())

        self.assertEqual(sample["confidence"], 1.0)
        self.assertEqual(sample["fatigue_score"], 0.0)

    def test_string_confidence_is_coerced_and_invalid_fatigue_defaults(self) -> None:
        model = OpenVINOQwenVLEmotionModel(
            FakeRunner(qwen_json(confidence="0.9", fatigue_score="high"))
        )

        sample = model.predict(make_frame())

        self.assertEqual(sample["confidence"], 0.9)
        self.assertEqual(sample["fatigue_score"], 0.0)

    def test_sleepy_emotion_tag_is_normalized_to_tired(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner(qwen_json(emotion_tag="sleepy")))

        sample = model.predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "tired")

    def test_frustrated_emotion_tag_is_normalized_to_stressed(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner(qwen_json(emotion_tag="frustrated")))

        sample = model.predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "stressed")

    def test_unknown_emotion_tag_is_normalized_to_unknown(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner(qwen_json(emotion_tag="excited")))

        sample = model.predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "unknown")

    def test_missing_fields_use_defaults(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner("{}"))

        sample = model.predict(make_frame())

        self.assertEqual(sample["emotion_tag"], "unknown")
        self.assertEqual(sample["confidence"], 0.0)
        self.assertEqual(sample["fatigue_score"], 0.0)
        self.assertEqual(sample["visual_reason"], "")
        self.assertEqual(sample["vlm_observation"], "")

    def test_invalid_json_raises_value_error(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner("not json"))

        with self.assertRaisesRegex(ValueError, "Failed to parse Qwen VL JSON output"):
            model.predict(make_frame())

    def test_non_object_json_raises_value_error(self) -> None:
        model = OpenVINOQwenVLEmotionModel(FakeRunner("[1, 2, 3]"))

        with self.assertRaisesRegex(ValueError, "must be an object"):
            model.predict(make_frame())

    def test_empty_runner_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "runner"):
            OpenVINOQwenVLEmotionModel(None)

    def test_context_is_passed_to_runner_and_prompt(self) -> None:
        runner = FakeRunner(qwen_json())
        model = OpenVINOQwenVLEmotionModel(runner)
        context = {
            "cv": {"emotion_tag": "tired"},
            "asr": {"text": "我有点累"},
            "history": {"count": 2},
        }

        model.predict(make_frame(), context=context)

        self.assertIs(runner.calls[0]["context"], context)
        self.assertIn("cv:", runner.calls[0]["prompt"])
        self.assertIn("我有点累", runner.calls[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
