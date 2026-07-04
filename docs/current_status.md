# Current Status

Last updated: 2026-07-04
Branch: `0703` local integration branch

## Main Demo Path

`robot/mergetesting` is the main DK-2500/base-station integration firmware.

```text
DK-2500 base-station microphone / camera
-> base_station ASR / vision context
-> OpenClaw Gateway / xiaoan-runtime decision
-> local ActionExecutor / Agent
-> base_station WebSocket /agent and /control
-> robot/mergetesting
-> face expression + motion + local sound
```

For the nine-day demo sprint, the primary voice input is the DK-2500/base-station microphone. The robot `/audio` path remains a fallback and diagnostics path for PCM capture, not the primary public-demo microphone.

`robot/firmware` remains the robot-body bring-up and reusable-module lab. Do not add new DK-2500 `/control`, `/video`, or `/audio` integration entrypoints there.

## Current Baseline

| Area | Current status |
| --- | --- |
| Firmware target | `mergetesting_full_face240` |
| `/control` | Hardware path verified for expression, motion, local sound, ack, and completion waits |
| `/video` | Robot camera reaches base station as `runtime/latest.jpg`; OpenClaw can inspect the live frame |
| Base-station mic | **Primary demo input target**: DK-2500 mic captures user speech, ASR turns it into `asr.transcript`; Demo 1 uses `--route-openclaw` to send context to OpenClaw Gateway `ws://127.0.0.1:18789` / `xiaoan-runtime`; full hardware pass verified mic -> ASR -> OpenClaw -> `/agent` -> `/control` -> expression ack, motion ack, and `motion.completed`; `--openclaw-decision-only` remains available when robot `/agent` is intentionally out of the loop |
| Assistant capture | P software path: `tools/demo/demo_assistant_capture.py` builds `assistant_capture_context.v1` for casual notes/ideas/reminders/tasks/meetings, requires OpenClaw-owned `capture` result as success evidence, writes `runtime/assistant_capture_result.json`, and exposes it on the dashboard; robot expression/local sound/TTS feedback is optional and separate from capture success |
| Visual chain | Stage 3 synthetic `/video` smoke passed through real OpenClaw and `mock_robot`; camera-free preflight now passes static image decode, mock image runtime, OpenFace OV readiness, and real `--run-openface` on `runtime/manual_samples/vision_real_camera_0703.jpg`; Qwen OpenVINO remains blocked by partial model download missing 3 large `.bin` files. See `docs/runbooks/demo1_visual_chain_handoff.md` |
| `/audio` robot mic | Fallback/diagnostic path: robot microphone PCM reaches the base-station side as `runtime/latest_audio.pcm`; `runtime/audio_stats.json` includes RMS/peak/DC/clipping |
| Fixed-window ASR | Current reusable ASR path is file-first: WAV/audio_file -> `base_station.monitor.asr_runtime --trim-speech`; robot `/audio` can still feed this path for diagnostics |
| Display | 2.4 inch face240 path is the current full-demo face path |
| Motor | DRV8833 motion works with practical demo speed around `0.56` |
| Speaker | Local speaker minimal loop passed for `audio.play_local care_01` and `success_ding`; complete care sequence still needs audio-channel sequencing when TTS and local sound are sent back to back |
| TTS | Real spoken TTS is not the reliable demo proof yet; avoid sending TTS immediately before local sound until audio-channel readiness is stabilized |
| Dock dashboard | `python -m base_station.dashboard.dashboard_server` serves the 1024x600 kiosk dashboard at `/dashboard` |
| Integration Console | `python -m base_station.integration_console.console_server --host 0.0.0.0 --port 8090` serves the hardware bring-up console at `/console`; software tests cover health/state/command payloads/scenario sequencing/tool guardrails, real hardware validation still pending |

Evidence:

- [status/2026-07-03.md](status/2026-07-03.md)
- [status/2026-06-28.md](status/2026-06-28.md)
- [status/2026-06-30.md](status/2026-06-30.md)
- [status/2026-06-27.md](status/2026-06-27.md)
- [agents/03_mergetesting_registry.md](agents/03_mergetesting_registry.md)
- [agents/08_priority_queue_results.json](agents/08_priority_queue_results.json)

## Not Main Demo

- screen monitoring
- work activity tracking
- local reminder/task/memory APIs
- real spoken TTS playback
- legacy firmware-side DK-2500 integration snapshots

## Known Open Items

1. Add sequencing or suppression around `robot.say` / `audio.play_tts` before `audio.play_local`; the complete care run hit `AUDIO_UNSUPPORTED: speaker not ready`, while local sound passed in isolation.
2. Continue visual verification from one fixed real camera image; OpenFace OV fixed-image runtime now passes, but Qwen VLM still needs `openvino_language_model.bin`, `openvino_text_embeddings_model.bin`, and `openvino_vision_embeddings_merger_model.bin` before using Qwen/OpenClaw visual output as proof.
3. Keep `audio.play_local care_01` as the reliable audible proof until real spoken TTS is implemented and verified.
4. Calibrate physical route timing on charged battery before chaining longer autonomous movement.
5. Keep the OpenClaw decision-only route for ASR/OpenClaw validation when the robot network is intentionally disconnected.
6. Keep robot `/audio` available as a fallback/diagnostic source: use `mergetesting_mic_only_shift18_asr`, export the latest `/audio` WAV, then run `base_station.monitor.asr_runtime --trim-speech` before SenseVoice. Keep checking RMS/peak/DC/clipping from `base_station.perception.audio_diagnostics`.
7. Keep generated runtime files, logs, DBs, model binaries, `.pio/`, and local configs out of Git.

## Commands

Base station:

```powershell
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

Robot full-demo firmware:

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240
pio run -e mergetesting_full_face240 -t upload --upload-port COM19
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
