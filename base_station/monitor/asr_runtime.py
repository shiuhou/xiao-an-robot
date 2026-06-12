"""Standalone ASR transcript runtime for local companion request testing."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from agent.core.brain import XiaoAnBrain


ASR_TRANSCRIPT_EVENT = "asr.transcript"
PATTERN_TEXT = {
    "tired": "我有点累",
    "negative": "我今天好烦",
    "normal": "帮我查一下天气",
    "openclaw": "帮我查一下天气",
    "greeting": "你好小安",
    "summary": "生成今天总结",
    "work": "我刚刚在写项目代码",
}


def resolve_transcript(text: str | None = None, pattern: str | None = None) -> str:
    """Resolve transcript text, with explicit text taking priority over pattern."""

    if text is not None:
        return text

    selected_pattern = pattern or "normal"
    try:
        return PATTERN_TEXT[selected_pattern]
    except KeyError as exc:
        supported = ", ".join(sorted(PATTERN_TEXT))
        raise ValueError(f"Unsupported ASR pattern: {selected_pattern}. Supported patterns: {supported}.") from exc


def build_asr_event(text: str) -> dict:
    return {
        "type": ASR_TRANSCRIPT_EVENT,
        "payload": {
            "text": text,
        },
    }


def build_output(text: str, event: dict, result: dict) -> dict:
    output = {
        "text": text,
        "event_type": event.get("type"),
        "handled": result.get("handled", False),
        "reason": result.get("reason"),
        "trigger_result": result.get("trigger_result"),
    }
    for key in (
        "route",
        "reply_text",
        "executed_actions",
        "skipped_actions",
        "companion_result",
    ):
        if key in result:
            output[key] = result[key]
    return output


async def run_once(
    text: str | None = None,
    pattern: str | None = None,
    gateway_url: str = "ws://127.0.0.1:8765/agent",
    brain: Any | None = None,
) -> dict:
    transcript = resolve_transcript(text=text, pattern=pattern)
    event = build_asr_event(transcript)
    active_brain = brain or XiaoAnBrain(gateway_url=gateway_url)

    try:
        result = await active_brain.handle_event(event)
    finally:
        if brain is None:
            active_brain.close()

    return build_output(transcript, event, result)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local ASR transcript event through XiaoAnBrain.")
    parser.add_argument("--text", default=None, help="Direct ASR transcript text.")
    parser.add_argument(
        "--pattern",
        choices=sorted(PATTERN_TEXT),
        default=None,
        help="Preset transcript pattern.",
    )
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/agent", help="Base station /agent URL.")
    parser.add_argument("--verbose", action="store_true", help="Print JSON result.")
    return parser.parse_args(argv)


async def main(args: argparse.Namespace | None = None) -> dict:
    if args is None:
        args = parse_args()
    output = await run_once(
        text=args.text,
        pattern=args.pattern,
        gateway_url=args.gateway_url,
    )
    if args.verbose:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


def run_cli(argv: list[str] | None = None) -> int:
    try:
        asyncio.run(main(parse_args(argv)))
    except KeyboardInterrupt:
        raise
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
