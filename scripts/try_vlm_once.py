"""Manual real-model smoke test for VLMFaceAnalyzer.

Usage:
    python scripts/try_vlm_once.py --image path/to/face.jpg --model-path path/to/Qwen2.5-VL-3B-OV-int4
    python scripts/try_vlm_once.py --camera 0 --model-path path/to/Qwen2.5-VL-3B-OV-int4
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def grab_frame(camera_index: int):
    import cv2  # type: ignore[import-not-found]

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {camera_index}")
    for _ in range(5):
        cap.read()
        time.sleep(0.05)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("Failed to read a frame from camera")
    return frame


def load_image(path: str):
    import cv2  # type: ignore[import-not-found]

    image = cv2.imread(path)
    if image is None:
        raise RuntimeError(f"Cannot read image: {path}")
    return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run VLMFaceAnalyzer once.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--image", default=None, help="Use a static image instead of a webcam.")
    parser.add_argument("--model-path", default=None, help="Qwen2.5-VL OpenVINO model directory.")
    parser.add_argument("--device", default="CPU")
    parser.add_argument("--face-crop", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from base_station.perception.vlm_face_analyzer import VLMFaceAnalyzer

    print("Loading VLMFaceAnalyzer...", flush=True)
    start = time.time()
    analyzer = (
        VLMFaceAnalyzer(model_dir=args.model_path, device=args.device, face_crop=args.face_crop)
        if args.model_path
        else VLMFaceAnalyzer(device=args.device, face_crop=args.face_crop)
    )
    print(f"Loaded in {time.time() - start:.1f}s", flush=True)

    bgr = load_image(args.image) if args.image else grab_frame(args.camera)
    print(f"Image shape: {getattr(bgr, 'shape', None)}", flush=True)

    infer_start = time.time()
    parsed = analyzer.analyze_image(bgr)
    print(f"\n=== inference {time.time() - infer_start:.1f}s ===")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))

    frame = {
        "source": "manual",
        "frame_id": 1,
        "timestamp_ms": int(time.time() * 1000),
        "payload": bgr,
    }
    print("\n=== predict() sample ===")
    print(json.dumps(analyzer.predict(frame), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
