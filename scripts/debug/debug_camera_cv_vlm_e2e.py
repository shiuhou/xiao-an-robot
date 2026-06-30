"""Debug camera -> CV -> trigger1 -> VLM -> EventLoop -> temp DB flow.

This runner is intentionally explicit and narrow. It does not connect ESP32,
WebSocket, UI, robot motion, or the production DB. It prints each boundary so
the current frame/sample contract can be inspected end to end.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class NoopGateway:
    async def send(self, command: dict) -> dict:
        return {"sent": False, "reason": "debug_noop", "command": command}

    async def send_expression(self, expression: str, **params) -> dict:
        return {"sent": False, "reason": "debug_noop", "type": "expression", "expression": expression, "params": params}

    async def send_motion(self, action: str, **params) -> dict:
        return {"sent": False, "reason": "debug_noop", "type": "motion", "action": action, "params": params}

    async def send_tts(self, text: str, **params) -> dict:
        return {"sent": False, "reason": "debug_noop", "type": "tts", "text": text, "params": params}


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def print_json(label: str, data: Any) -> None:
    print(f"{label} {json.dumps(json_safe(data), ensure_ascii=False)}", flush=True)


def save_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(json_safe(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug camera/CV/VLM/DB data flow.")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--num-frames", type=int, default=5)
    parser.add_argument("--vlm-backend", choices=["fake", "real"], default="fake")
    parser.add_argument("--force-vlm", action="store_true")
    parser.add_argument("--save-dir", default=None, help="Optional directory for per-frame jpg/json debug output.")
    parser.add_argument("--model-root", default=None, help="Override OpenVINO CV model root.")
    parser.add_argument("--vlm-model-path", default=None, help="Override real VLM model dir.")
    parser.add_argument("--device", default="CPU")
    parser.add_argument("--fake-vlm-pattern", default="neutral")
    return parser.parse_args()


def make_vlm_model(args: argparse.Namespace):
    if args.vlm_backend == "fake":
        from base_station.perception.qwen_vl_emotion_model import FakeQwenVLEmotionModel

        return FakeQwenVLEmotionModel(pattern=args.fake_vlm_pattern)

    from base_station.perception.vlm_face_analyzer import VLMFaceAnalyzer

    if args.vlm_model_path:
        return VLMFaceAnalyzer(model_dir=args.vlm_model_path, device=args.device)
    return VLMFaceAnalyzer(device=args.device)


async def main_async() -> int:
    args = parse_args()
    save_dir = Path(args.save_dir) if args.save_dir else None
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)

    from agent.core.brain import XiaoAnBrain
    from base_station.monitor.emotion_context_builder import EmotionContextBuilder
    from base_station.monitor.emotion_db import EmotionDB
    from base_station.monitor.emotion_event_loop import EmotionEventLoop
    from base_station.perception.face_emotion_pipeline import FaceEmotionPipeline
    from base_station.perception.opencv_camera import OpenCVCameraFrameSource
    from base_station.perception.openvino_face_emotion_model import OpenVINOFaceEmotionModel
    from base_station.perception.vlm_trigger_gate import VLMTriggerGate

    with tempfile.TemporaryDirectory(prefix="xiao_an_e2e_debug_") as temp_dir:
        db_path = str(Path(temp_dir) / "debug.db")
        memory = EmotionDB(db_path=db_path)
        brain = XiaoAnBrain(gateway=NoopGateway(), memory=memory)
        event_loop = EmotionEventLoop(brain=brain)
        context_builder = EmotionContextBuilder()
        gate = VLMTriggerGate()

        camera = OpenCVCameraFrameSource(camera_index=args.camera_index)
        try:
            try:
                camera.open()
            except Exception as exc:
                print(f"[FAIL][CAMERA] open failed: {exc}", flush=True)
                return 1
            print("[OK][CAMERA] opened", flush=True)

            try:
                cv_model = OpenVINOFaceEmotionModel(model_root=args.model_root, device=args.device)
            except Exception as exc:
                print(f"[FAIL][CV] OpenVINO model load failed: {exc}", flush=True)
                return 1
            cv_pipeline = FaceEmotionPipeline(model=cv_model)
            print("[OK][CV] OpenVINO model loaded", flush=True)

            try:
                vlm_model = make_vlm_model(args)
            except Exception as exc:
                print(f"[FAIL][VLM] model load failed: {exc}", flush=True)
                return 1
            print(f"[OK][VLM] backend={args.vlm_backend} loaded", flush=True)

            for index in range(args.num_frames):
                try:
                    frame = camera.read_frame()
                except Exception as exc:
                    print(f"[FAIL][CAMERA] frame capture failed at frame {index}: {exc}", flush=True)
                    return 1

                payload = frame.get("payload")
                print(
                    f"[CAMERA] index={index} frame_id={frame.get('frame_id')} "
                    f"shape={getattr(payload, 'shape', None)}",
                    flush=True,
                )
                image_path = None
                if save_dir is not None:
                    import cv2

                    image_path = save_dir / f"frame_{index + 1:03d}.jpg"
                    if not cv2.imwrite(str(image_path), payload):
                        print(f"[FAIL][SAVE] image save failed: {image_path}", flush=True)
                        return 1
                    print(f"[SAVE] image={image_path}", flush=True)

                try:
                    cv_sample = cv_pipeline.process_frame(frame)
                except Exception as exc:
                    print(f"[FAIL][CV] sample generation failed at frame {index}: {exc}", flush=True)
                    return 1
                print_json("[CV]", {
                    "emotion_tag": cv_sample.get("emotion_tag"),
                    "cv_emotion_raw": cv_sample.get("cv_emotion_raw"),
                    "confidence": cv_sample.get("confidence"),
                    "fatigue_score": cv_sample.get("fatigue_score"),
                    "face_detected": cv_sample.get("face_detected"),
                    "source": cv_sample.get("source"),
                })

                gate_result = gate.evaluate(cv_sample)
                trigger1_debug = gate_result | {
                    "db_used": False,
                    "polarity_used": False,
                }
                print_json("[TRIGGER1]", trigger1_debug)

                should_run_vlm = bool(gate_result.get("should_trigger")) or args.force_vlm
                if args.force_vlm and not gate_result.get("should_trigger"):
                    print("[TRIGGER1] force_vlm=True, running VLM despite trigger1=False", flush=True)

                if should_run_vlm:
                    context = context_builder.build(
                        cv_sample=cv_sample,
                        vlm_sample=None,
                        asr_text=None,
                        history_summary=memory.get_recent_summary(),
                    )
                    try:
                        t0 = time.perf_counter()
                        vlm_sample = await asyncio.to_thread(vlm_model.predict, frame, context)
                        vlm_elapsed_ms = (time.perf_counter() - t0) * 1000
                    except Exception as exc:
                        print(f"[FAIL][VLM] predict failed at frame {index}: {exc}", flush=True)
                        return 1
                    vlm_sample = vlm_sample.copy()
                    vlm_sample["vlm_triggered"] = True
                    vlm_sample["vlm_trigger_reason"] = str(gate_result.get("reason", "force"))
                    vlm_sample["cv_sample"] = cv_sample.copy()
                    final_sample = vlm_sample
                    print_json("[VLM]", {
                        "backend": args.vlm_backend,
                        "input_frame_ok": payload is not None,
                        "polarity": vlm_sample.get("polarity"),
                        "emotion_tag": vlm_sample.get("emotion_tag"),
                        "emotion": vlm_sample.get("emotion"),
                        "confidence": vlm_sample.get("confidence"),
                        "fatigue_score": vlm_sample.get("fatigue_score"),
                        "message": vlm_sample.get("message"),
                    })
                    vlm_debug = {
                        "backend": args.vlm_backend,
                        "input_frame_ok": payload is not None,
                        "skipped": False,
                        "output": vlm_sample,
                    }
                    print(
                        f"[PERF][VLM] frame_id={frame.get('frame_id')} "
                        f"backend={args.vlm_backend} vlm_elapsed_ms={vlm_elapsed_ms:.2f}",
                        flush=True,
                    )
                else:
                    final_sample = cv_sample.copy()
                    final_sample["vlm_triggered"] = False
                    final_sample["vlm_trigger_reason"] = str(gate_result.get("reason", "normal"))
                    print("[VLM] skipped because trigger1=False", flush=True)
                    vlm_elapsed_ms = 0.0
                    vlm_debug = {
                        "backend": args.vlm_backend,
                        "input_frame_ok": payload is not None,
                        "skipped": True,
                        "output": None,
                    }
                    print(
                        f"[PERF][VLM] frame_id={frame.get('frame_id')} "
                        "skipped=true vlm_elapsed_ms=0",
                        flush=True,
                    )

                event = event_loop.build_event(final_sample)
                print_json("[EVENT]", event.get("payload"))

                try:
                    result = await event_loop.handle_sample(final_sample)
                except Exception as exc:
                    print(f"[FAIL][EVENT] handling failed at frame {index}: {exc}", flush=True)
                    return 1

                summary = memory.get_recent_summary()
                db_debug = {
                    "negative_count": summary.get("negative_count"),
                    "summary": summary,
                    "trigger2_result": result,
                    "temp_db": db_path,
                }
                print_json("[DB]", db_debug)

                if save_dir is not None:
                    result_path = save_dir / f"frame_{index + 1:03d}_result.json"
                    save_json(result_path, {
                        "cv": cv_sample,
                        "trigger1": trigger1_debug,
                        "vlm": vlm_debug,
                        "event": event.get("payload"),
                        "db": db_debug,
                        "trigger2_result": result,
                        "vlm_elapsed_ms": vlm_elapsed_ms,
                    })
                    print(f"[SAVE] result={result_path}", flush=True)

            return 0
        finally:
            camera.close()
            memory.close()


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
