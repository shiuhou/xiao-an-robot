#!/usr/bin/env python3
"""Assistant capture demo: base-station mic -> OpenClaw-owned capture -> feedback."""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.core.gateway import RobotGateway
from agent.core.gateway_openclaw_adapter import (
    DEFAULT_OPENCLAW_AGENT,
    DEFAULT_OPENCLAW_GATEWAY_TIMEOUT_SEC,
    DEFAULT_OPENCLAW_GATEWAY_URL,
    GatewayOpenClawAdapter,
)
from agent.core.openclaw_adapter import OpenClawDecision, OpenClawEvent
from agent.core.xiaoan_tool_manifest import tool_manifest
from base_station.monitor.asr_runtime import run_once as run_asr_once
from tools.demo.demo1_usb_mic_to_agent_screen import (
    choose_input_device,
    list_input_devices,
    print_devices,
    record_wav,
    recording_sample_rate,
    write_transcript_text,
)


DEFAULT_RUNTIME_DIR = REPO_ROOT / "runtime"
DEFAULT_STATE_PATH = DEFAULT_RUNTIME_DIR / "assistant_capture_result.json"
DEFAULT_TEXT_PATH = DEFAULT_RUNTIME_DIR / "assistant_capture_transcript.txt"
DEFAULT_CONTEXT_PATH = DEFAULT_RUNTIME_DIR / "assistant_capture_context.json"
DEFAULT_LOG_PATH = DEFAULT_RUNTIME_DIR / "assistant_capture.log.jsonl"
DEFAULT_AUDIO_DIR = DEFAULT_RUNTIME_DIR / "assistant_capture_audio"
CONTEXT_SCHEMA_VERSION = "xiaoan.assistant_capture_context.v1"
RESULT_SCHEMA_VERSION = "xiaoan.assistant_capture_result.v1"
DEMO_INTENT = "assistant_capture"
CONTEXT_SOURCE = "base_station_mic"
OPENCLAW_SOURCE_OF_TRUTH = "openclaw_xiaoan_runtime"
CAPTURE_KINDS = ("note", "idea", "reminder", "task", "meeting")
CAPTURE_STATUSES = ("captured", "needs_clarification", "failed", "ignored")
LOCAL_COMPAT_TOOL_NAMES = {
    "note.add",
    "note.search",
    "reminder.add",
    "reminder.query",
    "reminder.cancel",
    "task.add",
    "task.query",
    "task.complete",
    "task.cancel",
}
FEEDBACK_EXPRESSIONS = ("happy", "thinking", "sad", "speaking", "idle")


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def write_json_artifact(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def append_log(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def build_state(
    *,
    status: str,
    transcript: str = "",
    source: str | None = None,
    capture: dict[str, Any] | None = None,
    reply_text: str = "",
    error: str | None = None,
    feedback: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": status,
        "timestamp": now_iso(),
        "transcript": transcript,
        "source": source,
        "source_of_truth": OPENCLAW_SOURCE_OF_TRUTH,
        "local_sqlite_is_product_source": False,
        "capture": capture or {},
        "reply_text": reply_text,
        "error": error,
        "feedback": feedback or {},
        "details": details or {},
    }


def write_state(path: str | Path, log_path: str | Path, state: dict[str, Any]) -> dict[str, Any]:
    write_json_artifact(path, state)
    append_log(log_path, state)
    return state


def audio_output_path(audio_dir: str | Path) -> Path:
    return Path(audio_dir) / f"assistant_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"


def infer_capture_hint(transcript: str) -> dict[str, Any]:
    text = transcript.strip()
    rules = [
        ("reminder", ("提醒", "待会", "待會", "等一下", "过会", "過會", "later")),
        ("meeting", ("会议", "會議", "开会", "開會", "meeting")),
        ("idea", ("点子", "點子", "想法", "idea", "灵感", "靈感")),
        ("task", ("待办", "待辦", "任务", "任務", "todo")),
        ("note", ("记一下", "記一下", "存一下", "记录", "記錄", "note")),
    ]
    matched: list[str] = []
    kind_hint = ""
    for kind, keywords in rules:
        hits = [keyword for keyword in keywords if keyword in text]
        if hits and not kind_hint:
            kind_hint = kind
        matched.extend(hits)
    return {
        "likely_capture": bool(matched),
        "kind_hint": kind_hint or "note",
        "matched_keywords": matched,
        "authority": "hint_only_openclaw_makes_final_decision",
    }


def assistant_capture_tool_manifest() -> list[dict[str, Any]]:
    allowed = {"xiaoan.robot.expression", "xiaoan.robot.say"}
    filtered: list[dict[str, Any]] = []
    for item in tool_manifest():
        name = str(item.get("name") or "")
        if name not in allowed:
            continue
        item_copy = deepcopy(item)
        if name == "xiaoan.robot.expression":
            expression = (
                item_copy.get("parameters", {})
                .get("properties", {})
                .get("expression")
            )
            if isinstance(expression, dict):
                expression["enum"] = list(FEEDBACK_EXPRESSIONS)
        filtered.append(item_copy)
    return filtered


def build_openclaw_context(
    *,
    transcript: str,
    transcript_source: str,
    audio_device: str | None = None,
    audio_path: str | None = None,
    asr_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "event_type": "asr.transcript",
        "demo_intent": DEMO_INTENT,
        "transcript": transcript,
        "source": CONTEXT_SOURCE,
        "transcript_source": transcript_source,
        "timestamp": now_iso(),
        "capture_policy": {
            "source_of_truth": OPENCLAW_SOURCE_OF_TRUTH,
            "local_sqlite_is_product_source": False,
            "legacy_local_tools_are_not_product_success": sorted(LOCAL_COMPAT_TOOL_NAMES),
        },
        "capture_expectation": {
            "allowed_kinds": list(CAPTURE_KINDS),
            "allowed_statuses": list(CAPTURE_STATUSES),
            "clarify_when_missing_required_info": True,
            "examples": [
                "帮我记一下，下星期有会议",
                "我突然想到一个点子，帮我记一下",
                "待会提醒我喝水",
                "这个想法先存一下",
            ],
        },
        "capture_hint": infer_capture_hint(transcript),
        "openclaw_owned_tools": [
            "memory_or_note_capture",
            "reminder_create_or_clarify",
            "task_create_or_clarify",
            "calendar_or_meeting_capture",
        ],
        "robot_feedback": {
            "local_owner": "xiao-an-robot",
            "available_tools": ["xiaoan.robot.expression", "xiaoan.robot.say"],
            "reliable_demo_feedback": ["dashboard", "display.expression", "audio.play_local"],
            "tts_reliable_demo_proof": False,
        },
        "audio": {
            "device": audio_device,
            "path": audio_path,
        },
        "asr_output": asr_output or {},
    }


def build_openclaw_event(*, transcript: str, context: dict[str, Any], session_id: str) -> OpenClawEvent:
    return OpenClawEvent(
        type="asr.transcript",
        text=transcript,
        source=CONTEXT_SOURCE,
        session_id=session_id,
        context=context,
    )


def _nested_dict(data: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, dict) else None


def capture_from_decision(decision: OpenClawDecision) -> dict[str, Any]:
    raw = decision.raw if isinstance(decision.raw, dict) else {}
    for candidate in (
        raw.get("capture"),
        _nested_dict(raw, "result", "capture"),
        _nested_dict(raw, "response", "capture"),
        _nested_dict(raw, "payload", "capture"),
        _nested_dict(raw, "payload", "result", "capture"),
    ):
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


def validate_capture_decision(decision: OpenClawDecision) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    capture = capture_from_decision(decision)

    if not decision.handled:
        errors.append("decision.handled must be true for assistant capture")
    if not capture:
        errors.append("decision.raw.capture is required; reply_text alone is not capture success")

    status = str(capture.get("status") or "")
    kind = str(capture.get("kind") or "")
    if capture:
        if status not in CAPTURE_STATUSES:
            errors.append(f"capture.status not allowed: {status}")
        if status in {"captured", "needs_clarification"} and kind not in CAPTURE_KINDS:
            errors.append(f"capture.kind not allowed: {kind}")
        if capture.get("source_of_truth") != OPENCLAW_SOURCE_OF_TRUTH:
            errors.append("capture.source_of_truth must be openclaw_xiaoan_runtime")
        if status == "needs_clarification" and not capture.get("missing_fields"):
            warnings.append("needs_clarification should include missing_fields")
        if status == "captured" and not (
            capture.get("title") or capture.get("content") or capture.get("summary")
        ):
            warnings.append("captured result should include title/content/summary")

    for index, tool_call in enumerate(decision.tool_calls):
        if tool_call.name in LOCAL_COMPAT_TOOL_NAMES:
            errors.append(
                f"tool_calls[{index}] uses local compatibility tool as product source: {tool_call.name}"
            )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "capture": capture,
    }


def status_from_capture_validation(validation: dict[str, Any]) -> str:
    if not validation.get("ok"):
        return "failed"
    capture = validation.get("capture") if isinstance(validation.get("capture"), dict) else {}
    status = str(capture.get("status") or "failed")
    return status if status in CAPTURE_STATUSES else "failed"


def feedback_plan(capture_status: str, reply_text: str = "") -> dict[str, Any]:
    if capture_status == "captured":
        return {
            "expression": "happy",
            "local_sound": "success_ding",
            "tts_text": reply_text or "已记录",
        }
    if capture_status == "needs_clarification":
        return {
            "expression": "thinking",
            "local_sound": None,
            "tts_text": reply_text or "还需要补充一点信息",
        }
    if capture_status == "ignored":
        return {
            "expression": "idle",
            "local_sound": None,
            "tts_text": reply_text or "",
        }
    return {
        "expression": "sad",
        "local_sound": None,
        "tts_text": reply_text or "这次没有保存成功",
    }


async def run_robot_feedback(
    *,
    gateway_url: str,
    capture_status: str,
    reply_text: str,
    include_tts: bool = False,
) -> dict[str, Any]:
    gateway = RobotGateway(url=gateway_url)
    plan = feedback_plan(capture_status, reply_text)
    actions: list[dict[str, Any]] = []
    ok = True

    async def run_action(name: str, coroutine) -> None:
        nonlocal ok
        try:
            result = await coroutine
        except Exception as exc:
            ok = False
            actions.append({"name": name, "ok": False, "error": str(exc)})
        else:
            actions.append({"name": name, "ok": True, "result": result})

    expression = plan.get("expression")
    if expression:
        await run_action(
            "display.expression",
            gateway.send_expression(str(expression), duration_ms=2200),
        )

    local_sound = plan.get("local_sound")
    if local_sound:
        await run_action("audio.play_local", gateway.send_local_audio(str(local_sound)))

    tts_text = str(plan.get("tts_text") or "").strip()
    if include_tts and tts_text:
        await run_action("audio.play_tts", gateway.send_tts(tts_text))

    return {
        "ok": ok,
        "plan": plan,
        "actions": actions,
        "tts_requested": bool(include_tts),
    }


async def transcribe_audio_file(args: argparse.Namespace, audio_path: Path) -> dict[str, Any]:
    trim_path = audio_path.with_name(f"{audio_path.stem}.trim.wav") if args.trim_speech else None
    return await run_asr_once(
        source="audio_file",
        audio_path=str(audio_path),
        vad_backend=args.vad_backend,
        vad_threshold=args.vad_threshold,
        asr_backend=args.asr_backend,
        asr_model_path=args.asr_model_path,
        device=args.asr_device,
        no_agent=True,
        trim_speech=args.trim_speech,
        speech_trim_path=str(trim_path) if trim_path else None,
        speech_trim_threshold=args.speech_trim_threshold,
        speech_trim_padding_ms=args.speech_trim_padding_ms,
    )


async def send_to_openclaw(
    args: argparse.Namespace,
    *,
    transcript: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    event = build_openclaw_event(
        transcript=transcript,
        context=context,
        session_id=args.openclaw_session_id,
    )
    adapter = GatewayOpenClawAdapter(
        gateway_url=args.openclaw_gateway_url,
        agent=args.openclaw_agent,
        timeout_sec=float(args.openclaw_timeout_sec),
        gateway_token=args.openclaw_gateway_token,
        tools=assistant_capture_tool_manifest(),
    )
    decision = await asyncio.to_thread(adapter.handle_event, event)
    validation = validate_capture_decision(decision)
    capture_status = status_from_capture_validation(validation)
    result = {
        "attempted": True,
        "ok": validation["ok"] and capture_status in {"captured", "needs_clarification"},
        "gateway_url": args.openclaw_gateway_url,
        "agent": args.openclaw_agent,
        "session_id": args.openclaw_session_id,
        "event": event.to_dict(),
        "decision": decision.to_dict(),
        "decision_validation": validation,
        "capture": validation.get("capture") or {},
        "capture_status": capture_status,
    }
    if decision.raw and isinstance(decision.raw, dict) and decision.raw.get("error"):
        result["openclaw_error"] = str(decision.raw.get("error"))
    return result


async def prepare_transcript(args: argparse.Namespace) -> tuple[str, str, dict[str, Any], str | None, str | None]:
    if args.mock_text is not None:
        transcript = args.mock_text.strip()
        if not transcript:
            raise RuntimeError("--mock-text must not be empty")
        return transcript, "mock", {"text": transcript}, None, None

    devices = list_input_devices()
    selected = choose_input_device(devices, args.device)
    device_name = str(selected["name"])
    sample_rate = recording_sample_rate(selected, args.sample_rate)
    wav_path = audio_output_path(args.audio_dir)
    print(f"Recording {args.duration:.1f}s from [{selected.get('index')}] {device_name}")
    record_wav(
        device=selected,
        output_path=wav_path,
        duration_seconds=args.duration,
        sample_rate=sample_rate,
        channels=1,
    )
    output = await transcribe_audio_file(args, wav_path)
    transcript = str(output.get("text") or "").strip()
    if not transcript:
        raise RuntimeError(f"ASR returned no transcript: {json.dumps(output, ensure_ascii=False)}")
    transcript_source = "asr" if args.asr_backend == "sensevoice" else "mock"
    return transcript, transcript_source, output, device_name, str(wav_path)


async def run_demo(args: argparse.Namespace) -> int:
    state_path = Path(args.state_path)
    log_path = Path(args.log_path)

    if args.list_devices:
        print_devices(list_input_devices())
        return 0

    write_state(
        state_path,
        log_path,
        build_state(
            status="idle",
            details={
                "route_openclaw": args.route_openclaw,
                "openclaw_gateway_url": args.openclaw_gateway_url,
                "openclaw_agent": args.openclaw_agent,
                "feedback_robot": args.feedback_robot,
                "feedback_tts": args.feedback_tts,
            },
        ),
    )

    try:
        if args.mock_text is None:
            write_state(
                state_path,
                log_path,
                build_state(status="listening", source="asr"),
            )
        transcript, transcript_source, asr_output, audio_device, audio_path = await prepare_transcript(args)
        write_transcript_text(args.text_path, transcript)

        context = build_openclaw_context(
            transcript=transcript,
            transcript_source=transcript_source,
            audio_device=audio_device,
            audio_path=audio_path,
            asr_output=asr_output,
        )
        write_json_artifact(args.context_path, context)

        route_result: dict[str, Any]
        capture_status = "ignored"
        reply_text = ""
        capture: dict[str, Any] = {}
        error: str | None = None
        if args.route_openclaw:
            write_state(
                state_path,
                log_path,
                build_state(
                    status="routing",
                    transcript=transcript,
                    source=transcript_source,
                    details={"context_path": str(args.context_path)},
                ),
            )
            route_result = await send_to_openclaw(args, transcript=transcript, context=context)
            decision = route_result.get("decision") if isinstance(route_result.get("decision"), dict) else {}
            reply_text = str(decision.get("reply_text") or "")
            capture = route_result.get("capture") if isinstance(route_result.get("capture"), dict) else {}
            capture_status = str(route_result.get("capture_status") or "failed")
            if not route_result.get("ok"):
                error = route_result.get("openclaw_error") or "; ".join(
                    route_result.get("decision_validation", {}).get("errors", [])
                )
        else:
            route_result = {
                "attempted": False,
                "ok": False,
                "reason": "route_openclaw_not_enabled",
            }
            capture_status = "ignored"
            capture = {
                "status": "ignored",
                "kind": infer_capture_hint(transcript).get("kind_hint"),
                "source_of_truth": OPENCLAW_SOURCE_OF_TRUTH,
                "reason": "route_openclaw_not_enabled",
            }

        feedback: dict[str, Any] = {}
        if args.feedback_robot and not args.openclaw_decision_only:
            feedback = await run_robot_feedback(
                gateway_url=args.gateway_url,
                capture_status=capture_status,
                reply_text=reply_text,
                include_tts=args.feedback_tts,
            )

        final_status = capture_status if capture_status in CAPTURE_STATUSES else "failed"
        if error and final_status not in {"captured", "needs_clarification"}:
            final_status = "failed"
        state = build_state(
            status=final_status,
            transcript=transcript,
            source=transcript_source,
            capture=capture,
            reply_text=reply_text,
            error=error,
            feedback=feedback,
            details={
                "text_path": str(args.text_path),
                "context_path": str(args.context_path),
                "route_result": route_result,
            },
        )
        write_state(state_path, log_path, state)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0 if final_status in {"captured", "needs_clarification", "ignored"} and not error else 1
    except Exception as exc:
        state = build_state(
            status="error",
            source="asr" if args.mock_text is None else "mock",
            error=str(exc),
        )
        write_state(state_path, log_path, state)
        print(json.dumps(state, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Xiao-An assistant capture demo")
    parser.add_argument("--list-devices", action="store_true", help="List audio input devices and exit.")
    parser.add_argument("--device", default=None, help="Audio input device index or name substring. Defaults to USB mic.")
    parser.add_argument("--duration", type=float, default=5.0, help="Recording window in seconds.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--asr-backend", choices=["sensevoice", "fake"], default="sensevoice")
    parser.add_argument("--asr-model-path", default="base_station/models/sensevoice-small")
    parser.add_argument("--asr-device", default="cpu")
    parser.add_argument("--vad-backend", choices=["fake", "energy", "silero"], default="energy")
    parser.add_argument("--vad-threshold", type=float, default=0.003)
    parser.add_argument("--trim-speech", action="store_true", default=True)
    parser.add_argument("--no-trim-speech", dest="trim_speech", action="store_false")
    parser.add_argument("--speech-trim-threshold", type=float, default=0.003)
    parser.add_argument("--speech-trim-padding-ms", type=int, default=250)
    parser.add_argument("--mock-text", default=None, help="Fallback transcript. Does not pretend to be real ASR.")
    parser.add_argument("--route-openclaw", action="store_true", help="Send capture context to OpenClaw Gateway.")
    parser.add_argument(
        "--openclaw-decision-only",
        action="store_true",
        help="Skip local robot feedback after OpenClaw returns. Useful when robot is offline.",
    )
    parser.add_argument("--feedback-robot", action="store_true", help="Send expression/local sound feedback to robot.")
    parser.add_argument(
        "--feedback-tts",
        action="store_true",
        help="Also send audio.play_tts, e.g. 已记录. TTS is not the reliable demo proof.",
    )
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/agent", help="Base station /agent URL.")
    parser.add_argument("--openclaw-gateway-url", default=DEFAULT_OPENCLAW_GATEWAY_URL)
    parser.add_argument("--openclaw-agent", default=DEFAULT_OPENCLAW_AGENT)
    parser.add_argument("--openclaw-timeout-sec", type=float, default=DEFAULT_OPENCLAW_GATEWAY_TIMEOUT_SEC)
    parser.add_argument("--openclaw-gateway-token", default=None)
    parser.add_argument("--openclaw-session-id", default="assistant-capture")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--text-path", default=str(DEFAULT_TEXT_PATH))
    parser.add_argument("--context-path", default=str(DEFAULT_CONTEXT_PATH))
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--audio-dir", default=str(DEFAULT_AUDIO_DIR))
    args = parser.parse_args(argv)
    if args.openclaw_decision_only and args.feedback_robot:
        parser.error("--openclaw-decision-only and --feedback-robot are mutually exclusive")
    if args.openclaw_decision_only and not args.route_openclaw:
        parser.error("--openclaw-decision-only requires --route-openclaw")
    if args.feedback_tts and not args.feedback_robot:
        parser.error("--feedback-tts requires --feedback-robot")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run_demo(parse_args(argv)))
    except KeyboardInterrupt:
        raise


if __name__ == "__main__":
    raise SystemExit(main())
