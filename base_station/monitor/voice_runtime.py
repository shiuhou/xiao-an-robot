"""Resident voice runtime entry point for link-1 text transcripts.

The older asr_runtime module remains the single-shot test entry point. This
module owns the long-running loop that reuses one ApiRuntime instance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, TextIO

from base_station.api.runtime import ApiRuntime
from base_station.monitor.asr_runtime import build_asr_event, build_output


SUPPORTED_SOURCES = {"text_loop"}
RESERVED_SOURCES = {"local_mic", "audio_file_loop"}


def build_voice_output(text: str, event: dict, result: dict) -> dict:
    """Build a compact debug object for each looped transcript."""

    output = build_output(text, event, result)
    openclaw_result = result.get("openclaw_result") if isinstance(result, dict) else None
    for key in (
        "display_text",
        "spoken_text",
        "suppress_auto_tts",
        "executed_actions",
        "skipped_actions",
    ):
        if key in output:
            continue
        if isinstance(result, dict) and key in result:
            output[key] = result[key]
            continue
        if isinstance(openclaw_result, dict) and key in openclaw_result:
            output[key] = openclaw_result[key]
    return output


async def process_text(
    runtime: Any,
    text: str,
    *,
    session_id: str = "voice-runtime",
) -> dict:
    """Send one terminal transcript through link 1 using an existing runtime."""

    transcript = text.strip()
    event = build_asr_event(transcript, source="text_loop")
    event["payload"]["session_id"] = session_id
    result = await runtime.brain.handle_event(event)
    return build_voice_output(transcript, event, result)


async def run_text_loop(
    *,
    runtime_factory: Any = ApiRuntime,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
    db_path: str = "agent/data/xiao_an.db",
    gateway_url: str = "ws://127.0.0.1:8765/agent",
    session_id: str = "voice-runtime",
    verbose: bool = False,
    prompt: bool = True,
) -> int:
    """Run the resident text loop until EOF or Ctrl+C.

    Returns the number of non-empty transcript lines processed.
    """

    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    error_stream = error_stream or sys.stderr
    runtime = runtime_factory(
        db_path=db_path,
        robot_ws_url=gateway_url,
        verbose=verbose,
    )
    handled_count = 0
    try:
        while True:
            if prompt:
                print("voice> ", end="", file=output_stream, flush=True)
            try:
                line = input_stream.readline()
            except KeyboardInterrupt:
                print("\nvoice_runtime stopped.", file=error_stream, flush=True)
                return handled_count
            if line == "":
                return handled_count
            text = line.strip()
            if not text:
                continue
            output = await process_text(
                runtime,
                text,
                session_id=session_id,
            )
            handled_count += 1
            if verbose:
                print(json.dumps(output, ensure_ascii=False, indent=2), file=output_stream, flush=True)
            else:
                print(json.dumps(_compact_output(output), ensure_ascii=False), file=output_stream, flush=True)
    finally:
        close = getattr(runtime, "close", None)
        if callable(close):
            close()


def _compact_output(output: dict) -> dict:
    compact = {}
    for key in (
        "text",
        "handled",
        "route",
        "reason",
        "display_text",
        "spoken_text",
        "reply_text",
        "executed_actions",
        "skipped_actions",
        "openclaw_error",
    ):
        if key in output:
            compact[key] = output[key]
    return compact


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Xiao An's resident voice runtime.")
    parser.add_argument(
        "--source",
        choices=sorted(SUPPORTED_SOURCES | RESERVED_SOURCES),
        default="text_loop",
        help="Resident input source. Only text_loop is implemented in this step.",
    )
    parser.add_argument("--db-path", default="agent/data/xiao_an.db")
    parser.add_argument("--gateway-url", default="ws://127.0.0.1:8765/agent")
    parser.add_argument("--session-id", default="voice-runtime")
    parser.add_argument("--verbose", action="store_true", help="Print full JSON output for each transcript.")
    parser.add_argument("--no-prompt", action="store_true", help="Disable the interactive prompt.")
    return parser.parse_args(argv)


async def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    if args.source not in SUPPORTED_SOURCES:
        raise NotImplementedError(f"--source {args.source} is reserved but not implemented yet.")
    await run_text_loop(
        db_path=args.db_path,
        gateway_url=args.gateway_url,
        session_id=args.session_id,
        verbose=args.verbose,
        prompt=not args.no_prompt,
    )
    return 0


def run_cli(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(main(parse_args(argv)))
    except KeyboardInterrupt:
        print("\nvoice_runtime stopped.", file=sys.stderr)
        return 0
    except (ValueError, RuntimeError, ImportError, NotImplementedError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_cli())
