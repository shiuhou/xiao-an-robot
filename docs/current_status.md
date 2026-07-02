# Current Status

Last updated: 2026-06-30
Branch: `20260628_merged`

## Main Demo Path

`robot/mergetesting` is the main DK-2500/base-station integration firmware.

```text
OpenClaw / Agent
-> base_station WebSocket /agent and /control
-> robot/mergetesting
-> face expression + motion + local sound
```

`robot/firmware` remains the robot-body bring-up and reusable-module lab. Do not add new DK-2500 `/control`, `/video`, or `/audio` integration entrypoints there.

## Current Baseline

| Area | Current status |
| --- | --- |
| Firmware target | `mergetesting_full_face240` |
| `/control` | Hardware path verified for expression, motion, local sound, ack, and completion waits |
| `/video` | Robot camera reaches base station as `runtime/latest.jpg`; OpenClaw can inspect the live frame |
| `/audio` | Robot microphone PCM reaches the base-station side as `runtime/latest_audio.pcm`; `runtime/audio_stats.json` now includes RMS/peak/DC/clipping for the latest window |
| Fixed-window ASR | `mergetesting_mic_only_shift18_asr` plus `base_station.monitor.asr_runtime --trim-speech` is the current calibrated demo path |
| Display | 2.4 inch face240 path is the current full-demo face path |
| Motor | DRV8833 motion works with practical demo speed around `0.56` |
| Speaker | Reliable demo sound is `audio.play_local care_01` |
| TTS | Real spoken TTS is not the reliable demo path yet; speaker PCM playback remains diagnostic |
| Dock dashboard | `python -m base_station.dashboard.dashboard_server` serves the 1024x600 kiosk dashboard at `/dashboard` |

Evidence:

- [status/2026-06-28.md](status/2026-06-28.md)
- [status/2026-06-30.md](status/2026-06-30.md)
- [status/2026-06-27.md](status/2026-06-27.md)
- [agents/03_mergetesting_registry.md](agents/03_mergetesting_registry.md)
- [agents/08_priority_queue_results.json](agents/08_priority_queue_results.json)

## Not Main Demo

- screen monitoring
- work activity tracking
- local reminder/task/memory APIs
- full autonomous ASR policy loop
- real spoken TTS playback
- legacy firmware-side DK-2500 integration snapshots

## Known Open Items

1. Confirm DK-2500/OpenClaw consistently observes matching `motion.completed` events after motion commands.
2. Keep `audio.play_local care_01` as the reliable audible proof until real spoken TTS is implemented and verified.
3. Investigate speaker PCM spoken playback with USB serial/backtrace before using it in a demo.
4. Calibrate physical route timing on charged battery before chaining autonomous movement.
5. Current fixed-window ASR demo path: use `mergetesting_mic_only_shift18_asr`, export the latest `/audio` WAV, then run `base_station.monitor.asr_runtime --trim-speech` before SenseVoice. Keep checking RMS/peak/DC/clipping from `base_station.perception.audio_diagnostics`.
6. Keep generated runtime files, logs, DBs, model binaries, `.pio/`, and local configs out of Git.

## Commands

Base station:

```powershell
python -m base_station.ws_server.server
```

Robot full-demo firmware:

```powershell
cd robot\mergetesting
pio run -e mergetesting_full_face240
pio run -e mergetesting_full_face240 -t upload --upload-port COM19
```

Direct smoke:

```powershell
python tools\send_robot_command.py --device-id xiaoan_robot_01 expression happy
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion forward --bench --speed 0.56 --duration-ms 2000 --timeout-ms 2200
python tools\send_robot_command.py --device-id xiaoan_robot_01 motion left --bench --speed 0.56 --duration-ms 500 --timeout-ms 700
python tools\send_robot_command.py --device-id xiaoan_robot_01 local care_01
```

Raw mic WAV/stat check:

```powershell
python -m base_station.perception.audio_diagnostics runtime\latest_audio.pcm --wav-out runtime\manual_samples\mic_20cm.wav --report-out runtime\manual_samples\mic_20cm_stats.json
```

Trimmed fixed-window ASR:

```powershell
python -m base_station.monitor.asr_runtime --source audio_file --audio-path runtime\manual_samples\mic_20cm.wav --asr-backend sensevoice --asr-model-path base_station\models\sensevoice-small --trim-speech --no-agent --verbose
```

Dock dashboard:

```powershell
python -m base_station.dashboard.dashboard_server
```

General verification:

```powershell
python -m unittest discover -s tests -p "test_*.py"
git diff --check
```
