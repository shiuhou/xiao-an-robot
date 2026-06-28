"""Run WebSocket /video frames through the existing emotion runtime."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from base_station.monitor.emotion_context_builder import EmotionContextBuilder
from base_station.monitor.emotion_event_loop import EmotionEventLoop
from base_station.monitor.emotion_runtime import (
    BaseStationEmotionRuntime,
    VLMGatedCameraEmotionSource,
    build_cv_pipeline,
    create_vlm_emotion_model,
    runtime_db_path,
)
from base_station.perception.vlm_trigger_gate import VLMTriggerGate
from base_station.perception.ws_video_source import WebSocketVideoFrameSource
from base_station.ws_server import server as ws_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Xiao An WebSocket /video frames through the emotion runtime.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="WebSocket server host.")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket server port.")
    parser.add_argument("--queue-size", type=int, default=2, help="Decoded /video frame queue size.")
    parser.add_argument(
        "--model-backend",
        choices=["mock", "openvino", "qwen_vl", "openvino_qwen_vl", "openface_ov"],
        default="mock",
        help="CV model backend.",
    )
    parser.add_argument("--model-path", default=None, help="OpenVINO face emotion model path.")
    parser.add_argument("--device", default="CPU", help="OpenVINO device name.")
    parser.add_argument(
        "--openface-repo",
        default=None,
        help="Path to the OpenFace 3.0 repo for --model-backend openface_ov.",
    )
    parser.add_argument(
        "--openface-models-dir",
        default=None,
        help="Path to OpenFace OpenVINO IR models for --model-backend openface_ov.",
    )
    parser.add_argument(
        "--vlm-backend",
        choices=["fake", "qwen_vl", "vlm_face", "openvino_qwen_vl"],
        default="fake",
        help="VLM backend used when the gate triggers.",
    )
    parser.add_argument("--vlm-model-path", default=None, help="VLM model directory.")
    parser.add_argument("--force-vlm", action="store_true", help="Force VLM analysis for every frame.")
    parser.add_argument("--no-agent", action="store_true", help="Print emotion.sample output without Agent.")
    parser.add_argument("--verbose", action="store_true", help="Print each sample and result.")
    parser.add_argument("--db-path", default="agent/data/xiao_an.db", help="SQLite database path.")
    parser.add_argument("--fresh-db", action="store_true", help="Use a fresh temporary SQLite database.")
    parser.add_argument(
        "--pattern",
        choices=["neutral", "tired", "sad", "anxious", "mixed"],
        default="tired",
        help="Pattern for mock/fake backends.",
    )
    return parser.parse_args(argv)


def create_ws_video_runtime(
    args: argparse.Namespace,
    frame_source: WebSocketVideoFrameSource,
    active_db_path: str,
) -> tuple[BaseStationEmotionRuntime, object | None]:
    brain = None
    history_memory = None
    if not args.no_agent:
        from agent.core.brain import XiaoAnBrain

        brain = XiaoAnBrain(
            gateway_url=f"ws://127.0.0.1:{args.port}/agent",
            db_path=active_db_path,
        )
        history_memory = brain.memory

    cv_pipeline = build_cv_pipeline(
        model_backend=args.model_backend,
        pattern=args.pattern,
        model_path=args.model_path,
        device=args.device,
        openface_repo=args.openface_repo,
        openface_models_dir=args.openface_models_dir,
    )
    vlm_model = create_vlm_emotion_model(
        vlm_backend=args.vlm_backend,
        pattern=args.pattern,
        vlm_model_path=args.vlm_model_path,
        device=args.device,
    )
    source = VLMGatedCameraEmotionSource(
        frame_source=frame_source,
        cv_pipeline=cv_pipeline,
        gate=VLMTriggerGate(),
        context_builder=EmotionContextBuilder(),
        vlm_model=vlm_model,
        memory=history_memory,
        force_vlm=args.force_vlm,
    )
    event_loop = EmotionEventLoop(brain=brain)
    return (
        BaseStationEmotionRuntime(
            source=source,
            event_loop=event_loop,
            verbose=args.verbose,
            no_agent=args.no_agent,
        ),
        brain,
    )


async def main(args: argparse.Namespace | None = None) -> None:
    if args is None:
        args = parse_args()

    frame_source = WebSocketVideoFrameSource(maxsize=args.queue_size)
    ws_server.set_video_frame_source(frame_source)
    server = None
    heartbeat_task = None
    brain = None
    try:
        with runtime_db_path(args.db_path, args.fresh_db) as active_db_path:
            runtime, brain = create_ws_video_runtime(args, frame_source, active_db_path)
            server = await ws_server.start_server(args.host, args.port)
            heartbeat_task = asyncio.create_task(ws_server.heartbeat_monitor())
            print(f"[ws_video_runtime] listening on ws://{args.host}:{args.port}/video")
            print("[ws_video_runtime] waiting for robot JPEG frames...")
            await runtime.run()
    finally:
        ws_server.set_video_frame_source(None)
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        if server is not None:
            server.close()
            await server.wait_closed()
        if brain is not None:
            close = getattr(brain, "close", None)
            if callable(close):
                close()


def run_cli(argv: list[str] | None = None) -> int:
    try:
        asyncio.run(main(parse_args(argv)))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
