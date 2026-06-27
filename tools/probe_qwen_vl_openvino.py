"""Probe Qwen2.5-VL OpenVINO emotion analysis from a static image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from base_station.perception.openvino_qwen_vl_emotion_model import OpenVINOQwenVLEmotionModel
from base_station.perception.qwen_vl_emotion_model import PATTERN_PREDICTIONS
from base_station.perception.qwen_vl_openvino_runner import (
    QwenVLOpenVINORunner,
    build_emotion_analysis_prompt,
)
from base_station.perception.static_image_source import StaticImageFrameSource


class FakeOutputRunner:
    def __init__(self, pattern: str):
        if pattern not in PATTERN_PREDICTIONS:
            raise ValueError(f"Unsupported --fake-output pattern: {pattern}")
        self.pattern = pattern
        self.raw_output = json.dumps(PATTERN_PREDICTIONS[pattern], ensure_ascii=False)

    def generate(self, image, prompt: str, context: dict | None = None) -> str:
        return self.raw_output


class CapturingRunner:
    def __init__(self, runner):
        self.runner = runner
        self.raw_output = None

    def generate(self, image, prompt: str, context: dict | None = None) -> str:
        self.raw_output = self.runner.generate(image, prompt, context=context)
        return self.raw_output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-path", required=True, help="Local PNG/JPG/JPEG image path.")
    parser.add_argument("--model-dir", default="base_station/models/qwen2_5_vl_openvino")
    parser.add_argument("--device", default="AUTO")
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument(
        "--fake-output",
        choices=sorted(PATTERN_PREDICTIONS),
        default=None,
        help="Use deterministic fake Qwen JSON instead of loading a real model.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    frame = StaticImageFrameSource(args.image_path, count=1, interval_seconds=0).read_frame()
    prompt = build_emotion_analysis_prompt()

    if args.fake_output:
        runner = FakeOutputRunner(args.fake_output)
    else:
        runner = CapturingRunner(
            QwenVLOpenVINORunner(
                model_dir=args.model_dir,
                device=args.device,
                max_new_tokens=args.max_new_tokens,
            )
        )

    model = OpenVINOQwenVLEmotionModel(runner=runner)
    sample = model.predict(frame)
    raw_output = getattr(runner, "raw_output", None)

    output = {
        "image_path": str(args.image_path),
        "model_dir": None if args.fake_output else args.model_dir,
        "device": None if args.fake_output else args.device,
        "fake_output": args.fake_output,
        "prompt_summary": prompt.splitlines()[:4],
        "frame": {
            "source": frame["source"],
            "frame_id": frame["frame_id"],
            "timestamp_ms": frame["timestamp_ms"],
            "width": frame["width"],
            "height": frame["height"],
        },
        "raw_output": raw_output,
        "emotion_sample": sample,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2 if args.verbose else None))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except (ValueError, FileNotFoundError, ImportError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
