# 2026-07-03 Spoken TTS Demo Preparation

## Scope

Prepared the robot-side bottom-capability path for the base-station mic and
OpenClaw demo. This is a preflight layer: it validates the exact robot actions
that the real ASR -> context -> OpenClaw path should call.

## Added Firmware Envs

| env | Purpose | Verification |
| --- | --- | --- |
| `mergetesting_full_face240_spoken_tts` | Full face240 + camera + robot mic fallback + motor + speaker + embedded spoken TTS phrase | `pio run -e mergetesting_full_face240_spoken_tts` passed |
| `mergetesting_full_face240_spoken_tts_ota` | OTA variant of the full spoken TTS env | Defined |
| `mergetesting_care_demo_face240_spoken_tts` | Safer care-demo spoken TTS path without camera/robot mic | Defined |
| `mergetesting_care_demo_face240_spoken_tts_ota` | OTA variant of the care-demo spoken TTS env | Defined |
| `mergetesting_care_demo_face240_spoken_tts_din41` | Temporary fallback for MAX98357A DIN on GPIO41; robot mic disabled | `pio run -e mergetesting_care_demo_face240_spoken_tts_din41` passed |

Main product speaker wiring remains BCLK=GPIO39, LRC=GPIO40, DIN=GPIO47.
The GPIO41 env is only a fallback while the standalone speaker test wiring is
still using GPIO41.

## Added Runner

```powershell
python tools\run_spoken_tts_demo.py --dry-run
python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01
python tools\run_spoken_tts_demo.py --device-id xiaoan_robot_01 --include-motion
```

The runner sends these commands through `/agent`:

1. `display.expression listening`
2. `audio.play_local wake_01`
3. `display.expression speaking`
4. `audio.play_tts "I can speak now."`
5. `display.expression caring`
6. `audio.play_local care_01`
7. optional `motion.execute move_out_of_dock`
8. optional `motion.execute turn`
9. `display.expression happy`
10. `audio.play_local success_ding`

Expected server evidence:

```text
Command ack: type=display.expression status=ok
Command ack: type=audio.play_local status=ok
Command ack: type=audio.play_tts status=accepted
Audio playback done: status=ok bytes_written=97520 duration_ms=...
Motion completed: agent-... -> completed
```

## Runbook

Operator-facing steps are in:

```text
docs/runbooks/spoken_tts_demo_smoke.md
```
