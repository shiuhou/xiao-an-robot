"""Base station emotion monitoring runtime.

This is the formal base_station entry point for running an emotion source into
XiaoAnBrain. It currently supports fake sources used by the local MVP; real
camera/OpenVINO sources can replace them later without changing the event loop
contract.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from base_station.monitor.emotion_context_builder import EmotionContextBuilder
from base_station.monitor.emotion_event_loop import EmotionEventLoop
from base_station.perception.face_emotion_model import MockFaceEmotionModel
from base_station.perception.face_emotion_pipeline import CameraEmotionSource, FaceEmotionPipeline
from base_station.perception.fake_camera import FakeCameraFrameSource
from base_station.perception.fake_face_emotion import FakeFaceEmotionSource
from base_station.perception.opencv_camera import OpenCVCameraFrameSource
from base_station.perception.qwen_vl_emotion_model import FakeQwenVLEmotionModel
from base_station.perception.vlm_trigger_gate import VLMTriggerGate
from base_station.perception import valence_mapping as vm

OpenVINOFaceEmotionModel = None
OpenVINOQwenVLEmotionModel = None
QwenVLOpenVINORunner = None
VLMFaceAnalyzer = None
_build_openface_cv_pipeline = None


class BaseStationEmotionRuntime:
    """Run an emotion source through EmotionEventLoop into the Agent brain."""

    def __init__(
        self,
        source: Any,
        event_loop: EmotionEventLoop,
        verbose: bool = True,
        no_agent: bool = False,
    ):
        self.source = source
        self.event_loop = event_loop
        self.verbose = verbose
        self.no_agent = no_agent

    async def run(self) -> list[dict]:
        results = []
        async for sample in self.source.samples():
            if self.no_agent:
                result = self.event_loop.build_event(sample)
                print("[emotion.sample]", json.dumps(result, ensure_ascii=False))
            else:
                result = await self.event_loop.handle_sample(sample)
            results.append(result)
            if self.verbose:
                print(json.dumps({
                    "sample": sample,
                    "result": result,
                }, ensure_ascii=False, indent=2))
        return results


class LimitedEmotionSource:
    """Limit another emotion source to a finite number of samples."""

    def __init__(self, source: Any, count: int | None):
        self.source = source
        self.count = count

    async def samples(self):
        iterator = self.source.samples().__aiter__()
        emitted = 0
        try:
            while self.count is None or emitted < self.count:
                sample = await iterator.__anext__()
                emitted += 1
                yield sample
        finally:
            close = getattr(iterator, "aclose", None)
            if close is not None:
                await close()
            nested_source = self.source
            while nested_source is not None:
                frame_source = getattr(nested_source, "frame_source", None)
                frame_source_close = getattr(frame_source, "close", None)
                if frame_source_close is not None:
                    frame_source_close()
                    break
                nested_source = getattr(nested_source, "source", None)


class IntervalEmotionSource:
    """Add a delay after each emitted sample."""

    def __init__(self, source: Any, interval_seconds: float):
        self.source = source
        self.interval_seconds = interval_seconds

    async def samples(self):
        async for sample in self.source.samples():
            yield sample
            if self.interval_seconds > 0:
                await asyncio.sleep(self.interval_seconds)


class DirectModelEmotionPipeline:
    """Use a model that already returns a complete emotion sample."""

    def __init__(self, model: Any):
        self.model = model

    def process_frame(self, frame: dict) -> dict:
        return self.model.predict(frame).copy()


# Perception-only signals (the VLM does NOT produce these). On triggered frames
# the top level is the VLM verdict and cv_sample is nested, so these would only
# be reachable inside cv_sample; we promote them to the top level so the emitted
# sample has the same shape whether or not the VLM ran. Deliberately EXCLUDES:
#   - emotion_tag / confidence / fatigue_score: VLM owns these at the top level
#     on triggered frames (the final verdict); never overwrite them.
#   - au_json: AU semantics unconfirmed -> record-only, must not reach decisions.
#   - frame_b64 / algorithm_version: bulky / debug-only, stay nested in cv_sample.
#   - valence: on triggered frames polarity follows the VLM verdict tag (set
#     below); CV's valence would describe a different (CV) label, so it stays
#     nested in cv_sample as supporting evidence rather than top level.
_PERCEPTION_PROMOTE_FIELDS = (
    "fatigue_level",
    "observation_quality",
    "presence_state",
    "evidence_codes",
)


def _as_evidence_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalize_vlm_result(raw: dict | None, *, executed: bool, status: str) -> dict:
    """Normalize VLM output into the runtime delivery contract."""

    raw = raw or {}
    expression_label = (
        raw.get("expression_label")
        or raw.get("emotion_tag")
        or raw.get("emotion")
    )
    face_observation = (
        raw.get("face_observation")
        or raw.get("vlm_observation")
        or raw.get("visual_reason")
        or ""
    )
    evidence = raw.get("visible_evidence")
    if evidence is None:
        evidence = raw.get("evidence")
    return {
        "executed": bool(executed),
        "status": str(status),
        "expression_label": expression_label,
        "emotion_score": raw.get("emotion_score"),
        "confidence": raw.get("confidence"),
        "evidence": _as_evidence_list(evidence),
        "face_observation": face_observation,
        "message": raw.get("message") or "",
        "valid_observation": raw.get("valid_observation"),
    }


class VLMGatedCameraEmotionSource:
    """Run a lightweight CV sample first, then call VLM only when the gate asks."""

    def __init__(
        self,
        frame_source: Any,
        cv_pipeline: Any,
        gate: VLMTriggerGate,
        context_builder: EmotionContextBuilder,
        vlm_model: Any,
        memory: Any | None = None,
        force_vlm: bool = False,
    ):
        self.frame_source = frame_source
        self.cv_pipeline = cv_pipeline
        self.gate = gate
        self.context_builder = context_builder
        self.vlm_model = vlm_model
        self.memory = memory
        self.force_vlm = force_vlm

    async def samples(self):
        async for frame in self.frame_source.frames():
            cv_sample = self.cv_pipeline.process_frame(frame)
            gate_result = self.gate.evaluate(cv_sample, force_vlm=self.force_vlm)
            reason = str(gate_result.get("reason", "normal"))

            if not gate_result.get("should_trigger", False):
                frame_id = cv_sample.get("frame_id") or frame.get("frame_id")
                print(f"[gate.skip] frame_id={frame_id} reason={reason}")
                continue

            context = self.context_builder.build(
                cv_sample=cv_sample,
                vlm_sample=None,
                asr_text=None,
                history_summary=self._history_summary(),
            )
            try:
                prediction = await asyncio.to_thread(self.vlm_model.predict, frame, context)
                vlm_status = str(prediction.get("status", "ok")) if isinstance(prediction, dict) else "ok"
            except Exception as exc:
                prediction = {
                    "message": f"VLM failed: {exc}",
                    "valid_observation": None,
                }
                vlm_status = "model_error"
            final_sample = cv_sample.copy()
            final_sample["vlm_triggered"] = True
            final_sample["vlm_trigger_reason"] = reason
            final_sample["cv_sample"] = cv_sample.copy()
            final_sample["vlm"] = normalize_vlm_result(
                prediction,
                executed=True,
                status=vlm_status,
            )

            yield final_sample

    def _history_summary(self) -> dict | None:
        get_recent_summary = getattr(self.memory, "get_recent_summary", None)
        if callable(get_recent_summary):
            return get_recent_summary()
        return None


@contextmanager
def runtime_db_path(db_path: str, fresh_db: bool):
    if fresh_db:
        with tempfile.TemporaryDirectory(prefix="xiao_an_emotion_runtime_") as temp_dir:
            yield str(Path(temp_dir) / "xiao_an_runtime.db")
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    yield db_path


def create_face_emotion_model(
    model_backend: str,
    pattern: str,
    model_path: str | None = None,
    device: str = "CPU",
):
    if model_backend == "mock":
        return MockFaceEmotionModel(pattern=pattern)

    if model_backend == "openvino":
        OpenVINOFaceEmotionModel = _load_openvino_face_emotion_model()
        return OpenVINOFaceEmotionModel(model_path=model_path, device=device)

    if model_backend == "openvino_qwen_vl":
        if not model_path:
            raise ValueError("--model-path is required when --model-backend openvino_qwen_vl")
        QwenVLOpenVINORunner, OpenVINOQwenVLEmotionModel = _load_openvino_qwen_vl_components()
        runner = QwenVLOpenVINORunner(model_dir=model_path, device=device)
        return OpenVINOQwenVLEmotionModel(runner=runner)

    if model_backend == "qwen_vl":
        return FakeQwenVLEmotionModel(pattern=pattern)

    raise ValueError(
        "Unsupported model backend: "
        f"{model_backend}. Currently supported backends: mock, openvino, qwen_vl, openvino_qwen_vl."
    )


def create_vlm_emotion_model(
    vlm_backend: str,
    pattern: str,
    vlm_model_path: str | None = None,
    device: str = "CPU",
):
    if vlm_backend in {"fake", "qwen_vl"}:
        return FakeQwenVLEmotionModel(pattern=pattern)

    if vlm_backend == "vlm_face":
        VLMFaceAnalyzer = _load_vlm_face_analyzer()
        if vlm_model_path:
            return VLMFaceAnalyzer(model_dir=vlm_model_path, device=device)
        return VLMFaceAnalyzer(device=device)

    if vlm_backend == "openvino_qwen_vl":
        if not vlm_model_path:
            raise ValueError("--vlm-model-path is required when --vlm-backend openvino_qwen_vl")
        QwenVLOpenVINORunner, OpenVINOQwenVLEmotionModel = _load_openvino_qwen_vl_components()
        runner = QwenVLOpenVINORunner(model_dir=vlm_model_path, device=device)
        return OpenVINOQwenVLEmotionModel(runner=runner)

    raise ValueError(
        "Unsupported VLM backend: "
        f"{vlm_backend}. Currently supported VLM backends: fake, qwen_vl, vlm_face, openvino_qwen_vl."
    )


def _load_openvino_face_emotion_model():     
    global OpenVINOFaceEmotionModel
    if OpenVINOFaceEmotionModel is None:
        from base_station.perception.openvino_face_emotion_model import OpenVINOFaceEmotionModel as loaded

        OpenVINOFaceEmotionModel = loaded
    return OpenVINOFaceEmotionModel


def _load_openvino_qwen_vl_components():
    global OpenVINOQwenVLEmotionModel, QwenVLOpenVINORunner
    if QwenVLOpenVINORunner is None:
        from base_station.perception.qwen_vl_openvino_runner import QwenVLOpenVINORunner as loaded_runner

        QwenVLOpenVINORunner = loaded_runner
    if OpenVINOQwenVLEmotionModel is None:
        from base_station.perception.openvino_qwen_vl_emotion_model import (
            OpenVINOQwenVLEmotionModel as loaded_model,
        )

        OpenVINOQwenVLEmotionModel = loaded_model
    return QwenVLOpenVINORunner, OpenVINOQwenVLEmotionModel


def _load_vlm_face_analyzer():
    global VLMFaceAnalyzer
    if VLMFaceAnalyzer is None:
        from base_station.perception.vlm_face_analyzer import VLMFaceAnalyzer as loaded

        VLMFaceAnalyzer = loaded
    return VLMFaceAnalyzer


def _load_openface_ov_adapter():
    """Lazy import of the OpenFace OV adapter (pulls in torch/openvino only here)."""
    global _build_openface_cv_pipeline
    if _build_openface_cv_pipeline is None:
        from base_station.perception.openface_ov_adapter import (
            build_openface_cv_pipeline as loaded,
        )

        _build_openface_cv_pipeline = loaded
    return _build_openface_cv_pipeline


def create_emotion_pipeline(model_backend: str, model: Any, pattern: str):
    if model_backend in {"qwen_vl", "openvino_qwen_vl"}:
        return DirectModelEmotionPipeline(model=model)
    return FaceEmotionPipeline(pattern=pattern, model=model)


def build_cv_pipeline(
    model_backend: str,
    pattern: str,
    model_path: str | None,
    device: str,
    openface_repo: str | None = None,
    openface_models_dir: str | None = None,
):
    """Build the cv_pipeline (process_frame: frame -> cv_sample) for a camera source.

    The ``openface_ov`` backend wires OpenFace's in-process OpenVINO perceive
    (3 IR + host decode, from the OpenFace repo) into the OpenFaceCVPipeline that
    emits the perception contract sample (route A / Gate 4). All other backends
    keep the existing model + FaceEmotionPipeline/DirectModelEmotionPipeline path.
    """
    if model_backend == "openface_ov":
        build = _load_openface_ov_adapter()
        return build(
            openface_repo=openface_repo,
            models_dir=openface_models_dir,
            device=device,
        )

    model = create_face_emotion_model(
        model_backend=model_backend,
        pattern=pattern,
        model_path=model_path,
        device=device,
    )
    return create_emotion_pipeline(model_backend=model_backend, model=model, pattern=pattern)


def create_emotion_source(
    source: str,
    pattern: str,
    count: int | None,
    interval_seconds: float,
    camera_index: int = 0,
    camera_width: int | None = None,
    camera_height: int | None = None,
    model_backend: str = "mock",
    model_path: str | None = None,
    device: str = "CPU",
    enable_vlm_gate: bool = False,
    vlm_backend: str = "qwen_vl",
    vlm_model_path: str | None = None,
    force_vlm: bool = False,
    history_memory: Any | None = None,
    openface_repo: str | None = None,
    openface_models_dir: str | None = None,
):
    if source == "fake_face":
        return FakeFaceEmotionSource(
            pattern=pattern,
            count=count,
            interval_seconds=interval_seconds,
        )

    if source == "fake_camera":
        frame_source = FakeCameraFrameSource(
            count=count,
            interval_seconds=interval_seconds,
        )
        pipeline = build_cv_pipeline(
            model_backend=model_backend,
            pattern=pattern,
            model_path=model_path,
            device=device,
            openface_repo=openface_repo,
            openface_models_dir=openface_models_dir,
        )
        if enable_vlm_gate:
            vlm_model = create_vlm_emotion_model(
                vlm_backend=vlm_backend,
                pattern=pattern,
                vlm_model_path=vlm_model_path,
                device=device,
            )
            return VLMGatedCameraEmotionSource(
                frame_source=frame_source,
                cv_pipeline=pipeline,
                gate=VLMTriggerGate(),
                context_builder=EmotionContextBuilder(),
                vlm_model=vlm_model,
                memory=history_memory,
                force_vlm=force_vlm,
            )
        return CameraEmotionSource(frame_source=frame_source, pipeline=pipeline)

    if source == "opencv_camera":
        frame_source = OpenCVCameraFrameSource(
            camera_index=camera_index,
            width=camera_width,
            height=camera_height,
        )
        pipeline = build_cv_pipeline(
            model_backend=model_backend,
            pattern=pattern,
            model_path=model_path,
            device=device,
            openface_repo=openface_repo,
            openface_models_dir=openface_models_dir,
        )
        if enable_vlm_gate:
            vlm_model = create_vlm_emotion_model(
                vlm_backend=vlm_backend,
                pattern=pattern,
                vlm_model_path=vlm_model_path,
                device=device,
            )
            camera_source = VLMGatedCameraEmotionSource(
                frame_source=frame_source,
                cv_pipeline=pipeline,
                gate=VLMTriggerGate(),
                context_builder=EmotionContextBuilder(),
                vlm_model=vlm_model,
                memory=history_memory,
                force_vlm=force_vlm,
            )
        else:
            camera_source = CameraEmotionSource(frame_source=frame_source, pipeline=pipeline)
        interval_source = IntervalEmotionSource(source=camera_source, interval_seconds=interval_seconds)
        return LimitedEmotionSource(source=interval_source, count=count)

    raise ValueError(
        "Unsupported emotion source: "
        f"{source}. Currently supported sources: fake_face, fake_camera, opencv_camera."
    )


def create_runtime(
    source_name: str = "fake_face",
    pattern: str = "tired",
    count: int | None = 5,
    interval_seconds: float = 1.0,
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: str = "agent/data/xiao_an.db",
    verbose: bool = True,
    camera_index: int = 0,
    camera_width: int | None = None,
    camera_height: int | None = None,
    model_backend: str = "mock",
    model_path: str | None = None,
    device: str = "CPU",
    enable_vlm_gate: bool = False,
    vlm_backend: str = "qwen_vl",
    vlm_model_path: str | None = None,
    force_vlm: bool = False,
    openface_repo: str | None = None,
    openface_models_dir: str | None = None,
    no_agent: bool = False,
) -> BaseStationEmotionRuntime:
    gateway_url = f"ws://{host}:{port}/agent"
    brain = None
    history_memory = None
    if not no_agent:
        from agent.core.brain import XiaoAnBrain

        brain = XiaoAnBrain(
            gateway_url=gateway_url,
            db_path=db_path,
        )
        history_memory = brain.memory
    source = create_emotion_source(
        source=source_name,
        pattern=pattern,
        count=count,
        interval_seconds=interval_seconds,
        camera_index=camera_index,
        camera_width=camera_width,
        camera_height=camera_height,
        model_backend=model_backend,
        model_path=model_path,
        device=device,
        enable_vlm_gate=enable_vlm_gate,
        vlm_backend=vlm_backend,
        vlm_model_path=vlm_model_path,
        force_vlm=force_vlm,
        history_memory=history_memory,
        openface_repo=openface_repo,
        openface_models_dir=openface_models_dir,
    )
    event_loop = EmotionEventLoop(brain=brain)
    return BaseStationEmotionRuntime(
        source=source,
        event_loop=event_loop,
        verbose=verbose,
        no_agent=no_agent,
    )


def create_fake_face_runtime(
    pattern: str = "tired",
    count: int | None = 5,
    interval_seconds: float = 1.0,
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: str = "agent/data/xiao_an.db",
    verbose: bool = True,
) -> BaseStationEmotionRuntime:
    return create_runtime(
        source_name="fake_face",
        pattern=pattern,
        count=count,
        interval_seconds=interval_seconds,
        host=host,
        port=port,
        db_path=db_path,
        verbose=verbose,
    )


def parse_count(value: str) -> int | None:  #没啥用的鲁棒
    if value.lower() in {"none", "null", "infinite"}:
        return None
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--count must be non-negative or None")
    return parsed


EXPECTED_CLI_ERRORS = (ValueError, ImportError, FileNotFoundError, RuntimeError)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:   #解析命令行参数
    parser = argparse.ArgumentParser(description="Run Xiao An base station emotion monitoring runtime.")  #初始化参数解析器对象，并设置程序的描述信息
    parser.add_argument(
        "--source",
        default="opencv_camera",
        choices=["fake_face", "fake_camera", "opencv_camera"],
        help="Emotion source.",
    )
    parser.add_argument(
        "--pattern",
        choices=["neutral", "tired", "sad", "anxious", "mixed"],
        default="tired",
        help="Fake face pattern.",
    )
    parser.add_argument("--count", type=parse_count, default=5, help="Number of samples, or None for infinite.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between samples.")
    parser.add_argument("--host", default="127.0.0.1", help="Base station host.")
    parser.add_argument("--port", type=int, default=8765, help="Base station /agent port.")
    parser.add_argument("--db-path", default="agent/data/xiao_an.db", help="SQLite database path.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--camera-width", type=int, default=None, help="Optional OpenCV camera width.")
    parser.add_argument("--camera-height", type=int, default=None, help="Optional OpenCV camera height.")
    parser.add_argument(
        "--model-backend",
        choices=["mock", "openvino", "qwen_vl", "openvino_qwen_vl", "openface_ov"],  #有啥区别
        default="openface_ov",
        help="Face emotion model backend for camera sources.",
    )
    parser.add_argument(
        "--openface-repo",
        default=None,
        help="Path to the OpenFace 3.0 repo (for --model-backend openface_ov). "
        "Defaults to the bundled xiao-an runtime, or OPENFACE_REPO when set.",
    )
    parser.add_argument(
        "--openface-models-dir",
        default=None,
        help="Path to OpenFace OpenVINO IR models. Defaults to OPENFACE_OV_MODELS_DIR "
        "or base_station/models/openface_ov.",
    )
    parser.add_argument("--model-path", default=None, help="OpenVINO face emotion model path.")
    parser.add_argument("--model-root", dest="model_path", help=argparse.SUPPRESS)
    parser.add_argument("--device", default="CPU", help="OpenVINO device name.")
    parser.add_argument("--enable-vlm-gate", default = True , action="store_true", help="Run VLM only when the trigger gate fires.")
    parser.add_argument(
        "--vlm-backend",
        choices=["fake", "qwen_vl", "vlm_face", "openvino_qwen_vl"],   #哪个才是真的？
        default="vlm_face",
        help="VLM backend used when --enable-vlm-gate fires.",
    )
    parser.add_argument("--vlm-model-path", default=r"..\base_station\models\Qwen2.5-VL-3B-OV-int4", help="OpenVINO Qwen VL model directory.")
    parser.add_argument("--vlm-model-root", dest="vlm_model_path", help=argparse.SUPPRESS)
    parser.add_argument("--force-vlm", action="store_true", help="Force VLM analysis for every camera sample.")
    parser.add_argument("--fresh-db", action="store_true", help="Use a fresh temporary SQLite database for this run.")
    parser.add_argument("--verbose", action="store_true", help="Print each sample and result.")
    parser.add_argument("--no-agent", action="store_true", help="Run perception and emotion.sample output without Agent.")
    return parser.parse_args(argv)


async def main(args: argparse.Namespace | None = None) -> None:
    if args is None:
        args = parse_args()
    with runtime_db_path(args.db_path, args.fresh_db) as active_db_path:
        runtime = create_runtime(
            source_name=args.source,
            pattern=args.pattern,
            count=args.count,
            interval_seconds=args.interval,
            host=args.host,
            port=args.port,
            db_path=active_db_path,
            verbose=args.verbose,
            camera_index=args.camera_index,
            camera_width=args.camera_width,
            camera_height=args.camera_height,
            model_backend=args.model_backend,
            model_path=args.model_path,
            device=args.device,
            enable_vlm_gate=args.enable_vlm_gate,
            vlm_backend=args.vlm_backend,
            vlm_model_path=args.vlm_model_path,
            force_vlm=args.force_vlm,
            openface_repo=args.openface_repo,
            openface_models_dir=args.openface_models_dir,
            no_agent=args.no_agent,
        )
        try:
            await runtime.run()
        finally:
            brain = runtime.event_loop.brain
            if brain is not None:
                brain.close()


def run_cli(argv: list[str] | None = None) -> int:
    try:
        asyncio.run(main(parse_args(argv)))
    except KeyboardInterrupt:
        raise
    except EXPECTED_CLI_ERRORS as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
