# Robot Body Firmware Bring-Up Lab

This is **not** the main DK-2500 demo firmware.

Main DK-2500/base-station integration firmware lives in [../mergetesting](../mergetesting/). This directory is for isolated hardware bring-up and reusable robot-body modules.

## Read First

- [platformio.ini](platformio.ini) is the env/build truth.
- [../../docs/agents/02_firmware_registry.md](../../docs/agents/02_firmware_registry.md) explains file roles.
- [MIGRATION_FROM_MERGETESTING.md](MIGRATION_FROM_MERGETESTING.md) explains the boundary with `robot/mergetesting`.
- [../../hardware/wiring/esp32_pinout.md](../../hardware/wiring/esp32_pinout.md) documents current pin assumptions.

## Env Groups

### Keep: Hardware Bring-Up

Use these for single-feature validation and bench checks:

| Env | Purpose |
| --- | --- |
| `esp32-s3-devkitc-1` | robot-body baseline `/control` firmware |
| `motor_manual` | serial WASD motor bring-up |
| `motor_bench_once` | one-shot motor direction test |
| `motor_wifi_manual` | browser motor control over ESP32 AP |
| `motor_cam_wifi_manual` | WiFi motor + camera stream + on-device QR overlay demo |
| `display_test` | 128x160 TFT test |
| `face240_wiretest` / `face240_integrated` | 2.4 inch ST7789 wiring/color harness |
| `face240_roboeyes` / `face240` | canonical 2.4 inch RoboEyes demo |
| `face240_9expr_merged` | nine-expression product face path |
| `voice_recognition_test` | INMP441 electrical/RMS test, not real ASR |
| `speaker_amp_test` | MAX98357A tone test |
| `ota_bootstrap` / `ota_bootstrap_wifi` | OTA bootstrap bridge only |

### Keep: Reusable Module Source

These modules may be copied or synced into `robot/mergetesting` after validation:

| Module | Notes |
| --- | --- |
| `motor_ctrl.cpp/h` | DRV8833 motion control |
| `display.cpp/h` | 128x160 display path |
| `peripherals/face240_display.cpp/h` | 2.4 inch face display module |
| `peripherals/speaker.cpp/h` | MAX98357A local sound module |
| `cam_stream.cpp/h` and camera config | OV2640 bring-up source |
| `mic_stream.cpp/h` / `inmp441_rms_check_main.cpp` | INMP441 bring-up source |

### Legacy: Do Not Use For New Demo Burns

| Env | Reason |
| --- | --- |
| `esp32-s3-integrated_legacy` | historical firmware-side DK-2500 integration snapshot |
| `face240_legacy` | old GPIO9-12 bench harness |
| `display_test_legacy` | old GPIO9-12 bench harness |

### Experimental / Optional

| Env | Purpose |
| --- | --- |
| `redtracker` | on-device red target tracker |
| `serialredtracker` | serial red target tracker |
| `serialqrservo` | serial JPEG stream plus PC-side QR servo |
| `keepfacecenter` | camera + motor pulse centering demo |
| `camtesting` | standalone camera AP stream |
| `tftprobe_hybrid_rawinit` | ST7789 diagnostic |

## Common Commands

Run commands from this directory:

```powershell
pio run -e motor_manual
pio run -e motor_cam_wifi_manual
pio run -e face240_integrated
pio run -e face240_9expr_merged
pio run -e voice_recognition_test
pio run -e speaker_amp_test
```

Do not run broad `pio run` when validating a specific feature. Env-specific builds are the useful signal.

## Local Config

Keep real WiFi, OTA credentials, and local IPs in ignored local config files. Use `src/config.local.example.h` as the template and do not commit `src/config.local.h`.
