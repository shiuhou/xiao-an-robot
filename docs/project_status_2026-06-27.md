# Project Status - 2026-06-27

This file records the 2026-06-27 Xiao-An hardware bring-up, full mergetesting demo, and DK2500/OpenClaw handoff. The session continued past midnight locally, but the work described here happened on the 2026-06-27 hardware validation day.

## Summary

Status at end of day:

- Split mergetesting envs had already reached hardware PASS_H.
- `mergetesting_full_face240` became the active full robot firmware for the DK2500/base-station loop.
- Local Windows base-station demo passed with `/control`, `/video`, and `/audio` all connected.
- Physical demo passed: robot moved forward out of the dock area, turned left, changed expression, and played an audible local sound.
- DK2500/OpenClaw handoff started: expression and motion commands reached the robot, but the DK2500/OpenClaw side still needs `motion.completed` chain verification.

## Firmware In Use

Active firmware target:

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240 -t upload --upload-port COM19
```

Observed upload notes:

- USB upload on `COM19` was reliable at `460800`.
- `921600` had been unstable during full firmware flashing.
- `robot/mergetesting/src/config.local.h` was updated locally for the active WiFi/base-station IP before reflashing. This file remains local-only and must not be committed.
- OTA remains useful for split envs, but full handoff reflashes used USB when the robot had just been overwritten or the target IP changed.

Enabled in `mergetesting_full_face240`:

- Face240 display.
- DRV8833 motor control.
- MAX98357A speaker path.
- OV2640 `/video` stream.
- INMP441 `/audio` PCM stream.
- WebSocket `/control`.

## Verified Hardware Results

Local full demo on the Windows base station reached hardware PASS_H for:

| Function | Status | Evidence |
| --- | --- | --- |
| `/control` connect | PASS_H | Robot connected, `device.hello`, heartbeat, command ack path active |
| Face expression | PASS_H | User confirmed expression change |
| Motor forward | PASS_H | User confirmed physical forward movement |
| Motor turn | PASS_H | User confirmed left turn |
| Speaker local sound | PASS_H | User confirmed audible sound |
| `/video` | PASS_P/H | Server received stream and `runtime/latest.jpg` updated |
| `/audio` | PASS_P/H | Server received PCM and `runtime/latest_audio.pcm` updated |

The final local demo used condition-based waits for matching `motion.completed`, not fixed sleeps.

## Final Local Demo Sequence

Working command sequence:

1. Send `motion move_out_of_dock` with:
   - `speed=0.56`
   - `duration_ms=2000`
   - `timeout_ms=2200`
2. Wait for `motion.completed` with the same `action_id`.
3. Send left turn with:
   - `speed=0.56`
   - `angle_deg=-30`
   - `duration_ms=500`
   - `timeout_ms=700`
4. Wait for `motion.completed` with the same `action_id`.
5. Send `display.expression happy`.
6. Send `audio.play_local care_01`.

User-visible result:

- Forward motion worked.
- Left turn worked.
- Face expression changed.
- Local audio played.

## Motor Calibration

Practical calibration found during floor testing:

- Speeds below about `0.5` are unreliable on the floor.
- `speed=0.52` is the current minimum effective positive safety floor.
- `speed=0.56` is the current reliable demo forward setting.
- `speed=0.56`, `duration_ms=1000` was observed around the 10 cm scale in one test.
- `speed=0.56`, `duration_ms=2000` is the current dock-exit demo setting.
- `speed=0.8` also moved after battery/power recovery.
- Earlier `0.2`, `distance_cm=2`, and `timeout_ms=500` settings only produced short vibration or no visible motion.

Code/docs already aligned in the current branch through the earlier 2026-06-27 commit:

- `tools/send_robot_command.py`
- `base_station/ws_server/server.py`
- `agent/skills/robot_motion.py`
- `robot/mergetesting/src/services/motion_service.cpp`
- relevant tests and agent docs

## Audio Notes

Reliable audible cue:

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

Important limitation:

- `audio.play_tts` is still a mock tone path, not spoken TTS.
- For demos that must clearly prove sound output, use `audio.play_local care_01`.
- SenseVoice/ASR model staging is separate from robot speaker playback; it does not make `audio.play_tts` produce spoken audio by itself.

## DK2500/OpenClaw Handoff

The DK2500 side was connected to the same hotspot and could send `/control` through its server/OpenClaw path after the robot was reflashed with the DK2500 base-station IP.

Observed DK2500/OpenClaw report:

- `display.expression happy` reached the robot.
- `agent.ack` returned ok.
- Robot returned `Command ack: type=display.expression status=ok`.
- A left-turn command reached the robot:
  - `action_id=manual-turn-left-2318`
  - `speed=0.56`
  - `angle_deg=-30`
  - `duration_ms=500`
  - `timeout_ms=700`
- DK2500 saw status change to `motion=turn`.
- DK2500 did not observe `motion.completed: manual-turn-left-2318` before reconnects.

Current diagnosis:

- If ESP32 serial shows matching `motion.completed`, then the remaining issue is DK server parsing/forwarding or OpenClaw waiting.
- If ESP32 serial does not show matching `motion.completed` and the robot reconnects, inspect firmware reset/power/watchdog.
- If DK server logs have `motion.completed` but OpenClaw does not, inspect the OpenClaw Gateway/agent event forwarding layer.

## Recommended DK2500 Direct Smoke

Before testing OpenClaw's higher-level tool path, bypass OpenClaw and run direct repo commands on the DK2500 base-station checkout:

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion left --bench --speed 0.56 --duration-ms 500 --timeout-ms 700
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

For raw `/agent` payloads:

- Include an explicit `action_id`.
- Wait for the matching `motion.completed` before sending the next motion.
- Do not infer hardware PASS_H from `agent.ack` alone.

## Remaining Work

Next concrete items:

1. Run the DK2500 direct smoke commands above and confirm `command.ack` plus matching `motion.completed`.
2. If direct DK2500 commands pass, retest OpenClaw Gateway forwarding and event wait behavior.
3. Keep `audio.play_local care_01` as the demo sound until real spoken TTS is implemented.
4. Continue Phase 4 real perception path only after DK2500 command completion reporting is stable.

## Validation Commands Used

Relevant validation commands during the 2026-06-27 loop included:

```powershell
python -m unittest discover -s tests -p "test_*.py"
cd robot\mergetesting
pio run -e mergetesting_full_face240
pio run -e mergetesting_full_face240 -t upload --upload-port COM19
python -m base_station.ws_server.server
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion left --bench --speed 0.56 --duration-ms 500 --timeout-ms 700
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

Do not commit generated runtime files such as `runtime/latest.jpg`, `runtime/latest_audio.pcm`, logs, databases, PlatformIO `.pio/`, or local secrets.
