# Xiao An Project Status - 2026-06-18

This document is the current push-prep snapshot for the Xiao An robot repository.
It combines the local repo state, recent Codex work, and relevant project memory.

## GitHub Sync

- `origin/main` has been fetched and checked.
- Local `main` is up to date with `origin/main` and is currently **ahead by 1 commit**.
- No commit from `origin/main` is missing locally.
- New remote branches were fetched, but they are not merged into `main`:
  - `origin/feature/asr-emotion-trigger`: memory recorder, daily summaries, reminders, work activity, and ASR/emotion memory tests.
  - `origin/feature/openface-ov-integration`: OpenFace/OpenVINO fatigue and affect perception route.
  - `origin/integration/perception-memory`: combined perception + memory integration, including model files and vendored OpenFace runtime.
- These branches should be reviewed deliberately before merging. Some branch diffs touch or delete existing OpenClaw adapter files, so they should not be blindly merged into the current hardware-control branch.

## Current Local Repo Shape

Main folders:

| Area | Current role |
| --- | --- |
| `robot/firmware` | ESP32-S3 firmware and isolated hardware bring-up envs |
| `base_station` | DK-2500 WebSocket server, perception runtime, emotion/ASR monitoring |
| `agent` | Brain, OpenClaw adapter path, local tools, memory/context shell, robot skills |
| `shared` | Shared protocol constants, schemas, and examples |
| `tests` | Unit/integration tests plus mock robot |
| `tools` | Runtime probes and command senders |
| `docs` | Protocol, deployment, hardware, troubleshooting, and minimum-loop route docs |
| `hardware` | BOM, wiring, DK-2500, mechanical, and dock notes |
| `frontend` | Early base-station UI placeholder |

Local generated/private items that should not be pushed:

- `.agents/`
- `.venv/`
- `.vision-venv/`
- `.pio/`
- `robot/firmware/compile_commands.json`
- downloaded model files and local databases

`.gitignore` now excludes `.agents/` and `robot/firmware/compile_commands.json`.

## What Is Working Now

### Base Station / Agent

- `/control`, `/agent`, `/audio`, and `/video` WebSocket routes exist.
- `/agent` can forward local Agent commands to the online robot session.
- `RobotGateway` and `RobotMotionSkill` can send expression, motion, and TTS command messages.
- `care_for_user()` can produce the core demo command sequence.
- `XiaoAnBrain` has MVP routing for emotion, ASR, frontend, and OpenClaw/tool-call style events.
- `CompanionRequestSkill`, `asr_runtime`, and `asr_emotion_trigger` are now present and tested.
- `EmotionDB`, `EmotionEventLoop`, and `emotion_runtime` support fake/mock/OpenCV-source active-care simulation.
- Qwen/VLM gate and wrapper paths exist, with real OpenVINO Qwen generation still pending.

### ESP32-S3 Firmware

- Main `/control` WebSocket client exists in `ws_client.cpp/.h`.
- Firmware sends:
  - `device.hello`
  - `device.heartbeat`
  - `device.status`
  - `motion.completed`
  - `error.report`
- Firmware receives and dispatches:
  - `system.welcome`
  - `display.expression`
  - `motion.execute`
  - `audio.play_tts`
  - `audio.play_local`
  - `config.update`
  - `system.shutdown`
- `motion.execute` can now read either legacy `payload.param` or nested `payload.params` fields.
- ESP32 echoes `action_id` back in `motion.completed`.
- Audio commands intentionally return `AUDIO_UNSUPPORTED` until MAX98357A/TTS playback is implemented.

### Hardware Bring-Up Assets

Dedicated PlatformIO envs now support isolated tests:

| Env | Purpose |
| --- | --- |
| `esp32-s3-devkitc-1` | Main firmware build |
| `camtesting` | OV2640 camera capture test |
| `motor_bench_once` | One-shot forward/back/left/right motor validation |
| `motor_manual` | WASD-style manual motor control |
| `keepfacecenter` | Camera + motor pulse demo for target centering |
| `serialqrservo` | ESP32 camera frame over serial + PC-side QR visual servoing |
| `display_test` / `tfttest` | TFT face/status screen bring-up |
| `voice_recognition_test` | INMP441 I2S RMS/voice activity test |

Related tools:

- `robot/firmware/tools/motor_keyboard.ps1`
- `robot/firmware/tools/qr_visual_servo.py`
- `tools/serial_camera_viewer.py`
- `tools/serial_camera_viewer.ps1`

## Recent Verification

Verified after the `/control` feedback update:

```powershell
py -m unittest discover -s tests -p "test_*.py"
```

Result:

```text
Ran 325 tests
OK
```

Firmware build:

```powershell
pio run -e esp32-s3-devkitc-1
```

Result:

```text
SUCCESS
```

## Current Main Gaps

### Hardware Integration

- Main firmware still does not run camera streaming in the loop.
- `/video` and `/audio` are present on the server side but not yet integrated into the ESP32 main firmware as live data channels.
- TFT, camera, motor, speaker, and microphone tests exist as isolated envs; full-body integration still needs bench validation.
- Limit switches are disabled in the current motor bench mapping and need final GPIO assignment.
- WiFi SSID/password/base-station IP are still hardcoded placeholders.

### AI / DK-2500

- Real OpenVINO face emotion postprocessing is not completed on `main`.
- Qwen2.5-VL OpenVINO generation is still placeholder-level on `main`.
- Real ASR/VAD/TTS model execution still needs deployment wiring.
- OpenFace/OpenVINO work exists on remote branches but has not been reconciled into `main`.

### Product / Demo

- Frontend is still early.
- Full Dock behavior and wireless charging are still hardware-stage tasks.
- Audio playback should be treated as a second-stage feature after the visible control loop is stable.

## Next Route

The next push should communicate a focused direction:

1. Finish and test the live `/control` minimum loop on real hardware.
2. Flash main firmware and confirm:
   - ESP32 sends `device.hello`.
   - DK-2500 sends `system.welcome`.
   - ESP32 sends `device.status`.
   - `display.expression` changes the TFT.
   - `motion.execute` moves the robot briefly and returns `motion.completed`.
   - unsupported audio/unknown command returns `error.report`.
3. Add low-rate `/video` JPEG transport only after the control loop is stable.
4. Use OpenCV/mock trigger first, then swap in OpenVINO/OpenFace perception.
5. Review and merge remote perception/memory branches in a controlled integration pass.
6. Build the Intel Cup demo story around:

```text
Perception trigger -> Agent decision -> caring expression -> short safe movement -> robot feedback
```

## Push Readiness Checklist

- [x] `origin/main` fetched and checked.
- [x] Local main has no missing remote-main commit.
- [x] README updated with current progress.
- [x] Protocol docs include `device.status`.
- [x] Test suite passed locally.
- [x] Main firmware env compiled.
- [x] User confirmed pushing the hardware test files and route docs.
- [x] Push target is `origin/main` using a normal non-force push.
