# AGENTS.md

These instructions apply to the whole repository.

## Communication

- Prefer Chinese replies unless the user writes in English or asks otherwise.
- Be direct and practical. For hardware work, include exact commands, wiring assumptions, expected serial/status behavior, and verification results.
- Do not present old documentation as current truth. Check live files and current Git state first.

## Repo Safety

- The worktree may already be dirty. Do not revert, delete, or overwrite changes you did not make.
- Before any commit, push, or PR work, run fetch/status/divergence checks and do not force-push unless the user explicitly requests it.
- Keep secrets, real logs, SQLite databases, `.env` files, model binaries, virtualenvs, `node_modules`, and PlatformIO build output out of Git.

## Project Shape

- `robot/firmware` is the ESP32-S3 robot-body firmware and isolated hardware bring-up area.
- `robot/mergetesting` is the DK-2500/base-station integration firmware (WebSocket `/control` `/video` `/audio`).
- `robot/mergetesting` may copy or sync proven modules from `robot/firmware`, but DK-2500 integration behavior belongs in `robot/mergetesting`.
- `base_station` is the DK-2500 WebSocket, perception, ASR/emotion runtime area.
- `agent` contains Agent brain, gateway, skills, memory/context shell, and local tools.
- `shared` contains protocol constants, schema, and examples.
- `docs` and `hardware` must stay aligned with actual firmware envs and wiring.
- **`docs/agents/README.md`** is the entry point for AI agents (file registry, test matrix, snapshots).

## Firmware Rules

- Keep `robot/firmware/src/main.cpp` as the robot-body baseline entrypoint, not the DK-2500 demo entrypoint.
- DK-2500/base-station integration work belongs in `robot/mergetesting`; do not add new `/control` `/video` `/audio` integration entrypoints to `robot/firmware`.
- New hardware experiments should use a dedicated `*_main.cpp` or test file plus a dedicated PlatformIO env in `robot/firmware/platformio.ini`.
- Use `build_src_filter` so isolated test entrypoints are excluded from `esp32-s3-devkitc-1`.
- Do not collapse isolated hardware experiments into `main.cpp`.
- If `mergetesting` needs a robot feature, first validate it in `robot/firmware`, then copy/sync the minimal proven module into `robot/mergetesting`.
- Validate firmware with specific envs, not broad `pio run`.
- Do not run multiple PlatformIO builds in parallel from the same `robot/firmware` workspace because they share `.pio/build`.

Current important envs:

- `esp32-s3-devkitc-1`: main `/control` firmware.
- `motor_manual`: serial WASD motor bring-up.
- `motor_bench_once`: one-shot motor direction test.
- `motor_wifi_manual`: browser motor control over ESP32 AP.
- `serialqrservo`: ESP32 serial JPEG stream plus PC-side QR servo.
- `motor_cam_wifi_manual`: integrated WiFi motor + camera stream + on-device QR overlay demo.
- `display_test`: 128x160 TFT test (`tfttest` alias removed 2026-06-23).
- `face240_integrated`: alias of `face240_wiretest` (integrated harness).
- `face240_roboeyes`: canonical 2.4" RoboEyes demo; `face240` extends it.
- `face240_9expr_merged`: nine-expression product path (mergetesting uses this).
- `tftprobe_hybrid_rawinit`: ST7789 diagnostic (other `tftprobe_*` envs removed).
- `face240_legacy`, `display_test_legacy`: old GPIO9–12 bench harness only.
- Archived sources: `robot/firmware/archive/`, experiments: `robot/firmware/experiments/`.
- `voice_recognition_test`: INMP441 electrical/RMS test, not real ASR.
- `speaker_amp_test`: MAX98357A tone test.
- `esp32-s3-integrated_legacy`: historical firmware-side DK-2500 integration snapshot; do not use for new burns. Use `robot/mergetesting` instead.

Current mergetesting envs:

- `mergetesting`: DK-2500 integration baseline.
- `mergetesting_display_only`: Phase 1-2 display/motor/speaker/WebSocket path.
- `mergetesting_face240_only`: Phase 2 2.4" face path.
- `mergetesting_cam_only`: Phase 3 OV2640 JPEG `/video` path.
- `mergetesting_mic_only`: INMP441 PCM `/audio` path.
- `mergetesting_base64_video`: `/video` base64 fallback.

## Hardware Assumptions

- Current motor wiring is DRV8833: left IN1/IN2 = GPIO1/GPIO2, right IN1/IN2 = GPIO3/GPIO48.
- Fix motor direction with `MOTOR_LEFT_FORWARD_USES_IN1` and `MOTOR_RIGHT_FORWARD_USES_IN1` before rewiring.
- Limit switch GPIOs are not final.
- Integrated TFT map (default): SCK=14, MOSI=21, CS=42, DC=43, RST=44, BL tied to 3V3 (`TFT_BL=-1`) via `board_pins.h`.
- Legacy bench TFT (`face240_legacy`, `display_test_legacy`): GPIO9/10/11/12 — camera must stay disconnected.
- `motor_cam_wifi_manual` uses SSID `XiaoAn-Motor`, UI `http://192.168.4.1/`, and stream `http://192.168.4.1:81/stream`.

## Verification

Run only the checks relevant to the change, and report exact results.

General Python:

```powershell
python -m unittest discover -s tests -p "test_*.py"
python tools/check_runtime_env.py
```

Firmware:

```powershell
cd robot\firmware
pio run -e esp32-s3-devkitc-1
pio run -e motor_cam_wifi_manual
pio run -e face240_integrated
pio run -e face240_wiretest
pio run -e face240_9expr_merged
```

Mergetesting:

```powershell
cd robot\mergetesting
pio run -e mergetesting_display_only
pio run -e mergetesting_face240_only
pio run -e mergetesting_cam_only
pio run -e mergetesting_mic_only
```

Face display helper:

```powershell
python robot\firmware\tools\test_face240_raw_dirty_rect.py
```

Before finishing:

```powershell
git diff --check
```

## Documentation Rules

- Update `README.md`, `docs/project_status_*.md`, `docs/hardware_setup.md`, and `hardware/wiring/*` when changing env names, wiring, commands, or hardware assumptions.
- Prefer dated status snapshots for handoff documents.
- Keep model download notes as placement/setup guidance unless the actual DK-2500 model source has been verified.
