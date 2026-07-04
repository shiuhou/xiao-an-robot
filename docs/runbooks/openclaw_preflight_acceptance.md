# OpenClaw Preflight Acceptance Runbook

Use this checklist before connecting the real OpenClaw decision loop. The goal
is to prove that every robot capability OpenClaw may call is stable, observable,
and has a clear completion signal.

For the broader base-station teammate handoff, including mic ownership,
speaker pins, TTS env vars, and OpenClaw context rules, start with
`docs/runbooks/base_station_openclaw_handoff.md`.

This runbook is intentionally ASCII-safe. For Chinese TTS, use the Python sender
below instead of passing raw Chinese text through PowerShell arguments.

## Current Baseline

Start the base station in streamed TTS mode:

```powershell
$env:XIAOAN_CONTROL_TTS_STREAM='1'
$env:XIAOAN_TTS_TARGET_PEAK='800'
$env:XIAOAN_TTS_VOICE='Microsoft Hanhan Desktop'
python -m base_station.ws_server.server
```

Current COM23 speaker firmware baseline:

```text
env: mergetesting_care_demo_face240_spoken_tts_din41
speaker pins: BCLK=39, LRC=40, DIN=41
stream gain: MERGETEST_SPEAKER_STREAM_GAIN=32
device_id: xiaoan_robot_01
```

On this Windows base-station PC, no zh-CN SAPI voice is currently installed.
Use `Microsoft Hanhan Desktop` as the temporary Mandarin-compatible fallback;
avoid zh-HK voices for the public demo.

Expected server evidence:

```text
Robot connected: xiaoan_robot_01 ...
Command ack: type=<command> status=ok|accepted
Audio playback done: status=ok bytes_written=... duration_ms=...
Motion completed: ... -> completed
```

## Unicode-Safe TTS Sender

Use this helper for Chinese phrases. The phrase values are Unicode escapes so
PowerShell encoding cannot corrupt them.

```powershell
@'
import asyncio
import json
import sys
import websockets

PHRASES = {
    "hello_intro": "\u4f60\u597d\uff0c\u6211\u662f\u5c0f\u5b89\u3002",
    "ack_help": "\u597d\u7684\uff0c\u6211\u6765\u5e2e\u4f60\u3002",
    "repeat": "\u8bf7\u4f60\u518d\u8bf4\u4e00\u6b21\u3002",
    "i_am_here": "\u6211\u5728\u8fd9\u91cc\u3002",
    "task_done": "\u4efb\u52a1\u5b8c\u6210\u4e86\u3002",
    "care": "\u522b\u62c5\u5fc3\uff0c\u6211\u4f1a\u966a\u7740\u4f60\u3002",
}

async def main():
    key = sys.argv[1]
    text = PHRASES[key]
    msg = {
        "type": "agent.command",
        "payload": {
            "command": "audio.play_tts",
            "device_id": "xiaoan_robot_01",
            "text": text,
        },
    }
    async with websockets.connect("ws://127.0.0.1:8765/agent", open_timeout=4) as ws:
        await ws.send(json.dumps(msg, ensure_ascii=False))
        print(await asyncio.wait_for(ws.recv(), timeout=30))

asyncio.run(main())
'@ | python - hello_intro
```

Replace the final key with `ack_help`, `repeat`, `i_am_here`, `task_done`, or
`care` for other phrases.

## P0 Must Pass

Do not connect OpenClaw until all P0 items pass.

Recommended one-command runner:

```powershell
python tools\run_openclaw_preflight_p0.py --device-id xiaoan_robot_01
```

The runner sends the P0 commands through `/agent` and then polls base-station
`agent.query` for robot-side `command.ack`, `audio.playback_done`, and heartbeat
evidence. The operator still needs to confirm the physical results: audible
speech/chime, face changes, and no unexpected motion.

| ID | Capability | Command | Physical result | Pass condition |
| --- | --- | --- | --- | --- |
| P0-1 | Robot online | Start base station and wait | ESP connects to hotspot/base station | Server logs `Robot connected: xiaoan_robot_01` and heartbeats continue |
| P0-2 | Spoken TTS intro | Run Unicode-safe sender with `hello_intro` | Xiao-An says "ni hao, wo shi xiao an" | `audio.play_tts accepted` + `audio.playback_done ok`; words understandable and not badly clipped |
| P0-3 | Spoken TTS arbitrary sentence | Run Unicode-safe sender with `ack_help` | Robot says a different sentence | Same as P0-2; proves arbitrary text, not fixed audio |
| P0-4 | Spoken TTS fallback phrase | Run Unicode-safe sender with `repeat` | Robot says a short fallback phrase | Same as P0-2 |
| P0-5 | Local wake sound | `python tools\send_robot_command.py --device-id xiaoan_robot_01 local wake_01` | Wake chime is audible | `audio.play_local status=ok` |
| P0-6 | Face thinking | `python tools\send_robot_command.py --device-id xiaoan_robot_01 expression thinking --duration-ms 1500` | Face changes to thinking | `display.expression status=ok` |
| P0-7 | Face speaking | `python tools\send_robot_command.py --device-id xiaoan_robot_01 expression speaking --duration-ms 1500` | Face changes to speaking | `display.expression status=ok` |
| P0-8 | Stop motion | `python tools\send_robot_command.py --device-id xiaoan_robot_01 motion stop --timeout-ms 500` | Robot stops or remains still | `motion.execute status=ok` and no unexpected movement |

## P1 Demo Quality

| ID | Capability | Command sequence | Physical result | Pass condition |
| --- | --- | --- | --- | --- |
| P1-1 | TTS plus face sequence | `expression speaking`, TTS `i_am_here`, then `expression caring` | Robot looks like it is speaking, then returns to caring | All three commands ack; TTS has playback_done |
| P1-2 | Success macro pieces | `local success_ding`, `expression happy`, then TTS `task_done` | Ding, happy face, spoken completion phrase | All acks and playback_done |
| P1-3 | Care response pieces | `expression caring`, then TTS `care` | Caring face and spoken care phrase | All acks and playback_done |
| P1-4 | No-motion bottom demo | `python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01 --tts-text "I can speak now."` plus one Unicode-safe TTS phrase afterward | Face, chimes, streamed speech, no wheel motion | Runner completes without stopping |

## P2 Motion Safety

Only run these when the robot is physically safe to move. If the robot is on a
table, lift the wheels and use `--bench` for manual motion checks.

| ID | Capability | Command | Physical result | Pass condition |
| --- | --- | --- | --- | --- |
| P2-1 | Short forward safe move | `python tools\send_robot_command.py --device-id xiaoan_robot_01 motion move_out_of_dock --speed 0.52 --duration-ms 500 --timeout-ms 900` | Robot moves forward briefly | `motion.execute status=ok` and `motion.completed` |
| P2-2 | Short turn | `python tools\send_robot_command.py --device-id xiaoan_robot_01 motion left --speed 0.52 --duration-ms 400 --timeout-ms 800` | Robot turns briefly | `motion.execute status=ok` and `motion.completed` |
| P2-3 | Full bottom demo with motion | `python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01 --include-motion` | Face, audio, speech, short motion sequence | Runner completes; no reset or cable snag |

## OpenClaw Allowed Action Set

Before the final demo, restrict OpenClaw to this exact command set:

```text
display.expression:
  neutral, thinking, speaking, caring, happy, listening, error

audio.play_tts:
  text: short spoken response, preferably under 30 Chinese characters

audio.play_local:
  wake_01, care_01, success_ding

motion.execute:
  stop, turn, move_out_of_dock, move_back_to_dock
```

OpenClaw should not directly invent GPIO, PWM, I2S, camera, or arbitrary motor
commands. It should choose from these tools and wait for ack/completion before
issuing the next action.

## Required Context From Base Station

Every OpenClaw call should include:

```json
{
  "transcript": "user original ASR text",
  "source": "base_station_mic",
  "timestamp": "ISO-8601 or epoch ms",
  "robot_state": {
    "online": true,
    "busy": false,
    "speaking": false,
    "moving": false,
    "battery": 87,
    "docked": false
  },
  "vision_context": {
    "person_present": true,
    "summary": "optional short visual observation"
  },
  "last_action": "last robot command or null",
  "demo_intent": "care_companion"
}
```

## Stop Conditions

Stop and debug before connecting OpenClaw if any of these happen:

- TTS has `accepted` but no `audio.playback_done`.
- TTS is audible but words are not understandable after setting
  `XIAOAN_TTS_TARGET_PEAK=800` and
  `XIAOAN_TTS_VOICE='Microsoft Hanhan Desktop'`.
- A command returns `agent.ack ok=false`.
- Motion starts but no `motion.completed` appears.
- Heartbeats stop during speech or motion.
- Robot resets or reconnects during a P0/P1 check.

## Final Go / No-Go

Go to OpenClaw only when:

- P0 is fully pass.
- At least P1-1 and P1-4 pass.
- P2 is either pass or explicitly disabled for the demo.
- The dashboard/log view shows transcript -> context -> OpenClaw action ->
  `/control` command -> robot ack/playback_done/motion_completed.
