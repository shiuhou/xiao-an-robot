# Current Status

Last updated: 2026-07-04
Branch: `0703` local integration branch with `origin/0704` spoken-TTS handoff merged

## Main Demo Path

`robot/mergetesting` is the main DK-2500/base-station integration firmware.

```text
DK-2500 base-station microphone / camera
-> base_station ASR / vision context
-> OpenClaw Gateway / xiaoan-runtime decision
-> local ActionExecutor / Agent
-> base_station WebSocket /agent and /control
-> robot/mergetesting
-> face expression + motion + local sound / spoken TTS
```

For the nine-day demo sprint, the primary voice input is the DK-2500/base-station microphone. The robot `/audio` path remains a fallback and diagnostics path for PCM capture, not the primary public-demo microphone.

`robot/firmware` remains the robot-body bring-up and reusable-module lab. Do not add new DK-2500 `/control`, `/video`, or `/audio` integration entrypoints there.

## Current Baseline

| Area | Current status |
| --- | --- |
| Firmware target | P0 spoken TTS baseline: `mergetesting_care_demo_face240_spoken_tts_din41`; full product candidate: `mergetesting_full_face240_spoken_tts` |
| `/control` | Hardware path verified for expression, motion, local sound, ack, and completion waits |
| `/video` | Robot camera reaches base station as `runtime/latest.jpg`; OpenClaw can inspect the live frame |
| Base-station mic | **Primary demo input target**: DK-2500 mic captures user speech, ASR turns it into `asr.transcript`; Demo 1 uses `--route-openclaw` to send context to OpenClaw Gateway `ws://127.0.0.1:18789` / `xiaoan-runtime`; full hardware pass verified mic -> ASR -> OpenClaw -> `/agent` -> `/control` -> expression ack, motion ack, and `motion.completed`; `--openclaw-decision-only` remains available when robot `/agent` is intentionally out of the loop |
| Assistant capture | P software path: `tools/demo/demo_assistant_capture.py` builds `assistant_capture_context.v1` for casual notes/ideas/reminders/tasks/meetings, requires OpenClaw-owned `capture` result as success evidence, writes `runtime/assistant_capture_result.json`, and exposes it on the dashboard; robot expression/local sound/TTS feedback is optional and separate from capture success |
| Visual chain | Stage 3 synthetic `/video` smoke passed through real OpenClaw and `mock_robot`; camera-free preflight now passes static image decode, mock image runtime, OpenFace OV readiness, and real `--run-openface` on `runtime/manual_samples/vision_real_camera_0703.jpg`; Qwen OpenVINO remains blocked by partial model download missing 3 large `.bin` files. See `docs/runbooks/demo1_visual_chain_handoff.md` |
| `/audio` robot mic | Fallback/diagnostic path: robot microphone PCM reaches the base-station side as `runtime/latest_audio.pcm`; `runtime/audio_stats.json` includes RMS/peak/DC/clipping |
| Fixed-window ASR | Current reusable ASR path is file-first: WAV/audio_file -> `base_station.monitor.asr_runtime --trim-speech`; robot `/audio` can still feed this path for diagnostics |
| Display | 2.4 inch face240 path is the current full-demo face path |
| Motor | DRV8833 motion works with practical demo speed around `0.56` |
| Speaker | Local speaker minimal loop passed for `audio.play_local care_01` and `success_ding`; current P0 spoken TTS speaker wiring is MAX98357A BCLK=39, LRC=40, DIN=41, robot mic disabled; product candidate with robot mic uses DIN=47 |
| TTS | Current best spoken TTS path uses the replaced `4 ohm 3 W, 500-5000 Hz` speaker, DIN41 buffered PCM firmware, `XIAOAN_TTS_TARGET_PEAK=500`, and robot `MERGETEST_SPEAKER_STREAM_GAIN=32`; the robot buffers the full PCM stream before I2S playback |
| Dock dashboard | `python -m base_station.dashboard.dashboard_server` serves the 1024x600 kiosk dashboard at `/dashboard` |
| Integration Console | `python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090` serves the hardware bring-up console at `/console`; software tests cover health/state/command payloads/scenario sequencing/tool guardrails, real hardware validation still pending |

Evidence:

- [status/2026-07-03.md](status/2026-07-03.md)
- [status/2026-06-28.md](status/2026-06-28.md)
- [status/2026-06-30.md](status/2026-06-30.md)
- [status/2026-07-04-openclaw-p0-preflight.md](status/2026-07-04-openclaw-p0-preflight.md)
- [runbooks/base_station_openclaw_handoff.md](runbooks/base_station_openclaw_handoff.md)
- [runbooks/openclaw_preflight_acceptance.md](runbooks/openclaw_preflight_acceptance.md)
- [status/2026-06-27.md](status/2026-06-27.md)
- [agents/03_mergetesting_registry.md](agents/03_mergetesting_registry.md)
- [agents/08_priority_queue_results.json](agents/08_priority_queue_results.json)

## Not Main Demo

- screen monitoring
- work activity tracking
- local reminder/task/memory APIs
- free-form/full-quality spoken TTS beyond the current P0 OS-specific TTS backend baseline
- legacy firmware-side DK-2500 integration snapshots

## Known Open Items

1. Add sequencing or suppression around `robot.say` / `audio.play_tts` before `audio.play_local`; the complete care run hit `AUDIO_UNSUPPORTED: speaker not ready`, while local sound passed in isolation.
2. Connect real OpenClaw to the P0 allowed action set and verify it forwards through `/agent` without local keyword-rule shortcuts.
3. Confirm DK-2500/OpenClaw consistently observes matching `motion.completed` events after non-stop motion commands.
4. Continue visual verification from one fixed real camera image and keep Qwen/OpenVINO visual output tied to verified local model completeness.
5. Improve Mandarin TTS quality if time permits; current backend voice is OS-specific and demo-acceptable, not product quality.
6. Calibrate physical route timing on charged battery before chaining autonomous movement.
7. Keep the base-station mic demo path explicit: base mic WAV/capture -> ASR -> context -> OpenClaw/Agent -> `/agent` -> `/control` commands -> ack/completed evidence.
8. Keep the OpenClaw decision-only route for ASR/OpenClaw validation when the robot network is intentionally disconnected.
9. Keep robot `/audio` available as a fallback/diagnostic source: use `mergetesting_mic_only_shift18_asr`, export the latest `/audio` WAV, then run `base_station.monitor.asr_runtime --trim-speech` before SenseVoice. Keep checking RMS/peak/DC/clipping from `base_station.perception.audio_diagnostics`.
10. Keep generated runtime files, logs, DBs, model binaries, `.pio/`, and local configs out of Git.

## Commands

Base station:

```powershell
$env:XIAOAN_CONTROL_TTS_STREAM='1'
$env:XIAOAN_TTS_TARGET_PEAK='500'
python -m base_station.ws_server.server
```

Base-station mic demo target:

```text
DK-2500 mic -> WAV/audio_file -> ASR -> asr.transcript -> OpenClaw Gateway/xiaoan-runtime -> ActionExecutor -> /agent -> /control robot commands
```

Demo 1 OpenClaw route:

```powershell
tools\demo\run_demo1_mic_to_robot.sh --once --no-screen
```

Assistant capture OpenClaw decision-only route:

```powershell
python tools\demo\demo_assistant_capture.py --mock-text "帮我记一下，下星期有会议" --route-openclaw --openclaw-decision-only
```

Robot current P0 spoken-TTS firmware:

```powershell
cd robot\mergetesting
pio run -e mergetesting_care_demo_face240_spoken_tts_din41
pio run -e mergetesting_care_demo_face240_spoken_tts_din41 -t upload --upload-port COM23
```

P0 preflight:

```powershell
python tools\run_openclaw_preflight_p0.py --device-id xiaoan_robot_01
```

Full product candidate, when MAX98357A DIN is moved to GPIO47 and robot mic is
needed:

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240_spoken_tts
pio run -e mergetesting_full_face240_spoken_tts -t upload --upload-port COMxx
```

Direct smoke:

```powershell
python tools\ops\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\ops\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\ops\send_robot_command.py --device-id xiaoan_robot_01 motion left --bench --speed 0.56 --duration-ms 500 --timeout-ms 700
python tools\ops\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

Robot `/audio` fallback WAV/stat check:

```powershell
python -m base_station.perception.audio_diagnostics runtime\latest_audio.pcm --wav-out runtime\manual_samples\mic_20cm.wav --report-out runtime\manual_samples\mic_20cm_stats.json
```

Trimmed fixed-window ASR from an audio file:

```powershell
python -m base_station.monitor.asr_runtime --source audio_file --audio-path runtime\manual_samples\mic_20cm.wav --asr-backend sensevoice --asr-model-path base_station\models\sensevoice-small --trim-speech --no-agent --verbose
```

Dock dashboard:

```powershell
python -m base_station.dashboard.dashboard_server
```

Integration Console:

```powershell
python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090 --ws-url ws://127.0.0.1:8765/agent --runtime-dir runtime
```

General verification:

```powershell
python -m unittest discover -s tests -p "test_*.py"
git diff --check
```

Visual-chain preflight:

```powershell
python tools\prepare_visual_chain_preflight.py --image-path runtime\manual_samples\vision_real_camera_0703.jpg --run-openface
python tools\setup_models.py --only qwen_vl --check
```
