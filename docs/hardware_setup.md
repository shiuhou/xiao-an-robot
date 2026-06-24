# Hardware Setup Guide

This guide tracks the current Xiao An bench hardware route. It is written for the current isolated firmware envs, not for a fully integrated final PCB.

## Build Strategy

Do not assemble the final shell first. Validate every peripheral on the bench, then measure the real parts before printing the shell and dock.

Recommended order:

1. ESP32-S3 serial/upload.
2. DRV8833 + N20 motors without wheels.
3. Browser motor control over ESP32 AP.
4. OV2640 camera capture.
5. Camera + motor + QR overlay demo.
6. TFT face screen.
7. INMP441 mic.
8. MAX98357A speaker amp.
9. Dock limit switches and wireless charging alignment.
10. Temporary chassis drive test.
11. Final shell/dock integration.

## Current Mechanical Concept

### Chassis

- Approximate prototype base: 12 cm x 10 cm x 3 cm.
- Two N20 gear motors are fixed on the left and right side, with wheels exposed.
- ESP32-S3, motor driver, battery, regulator, and wiring sit on the flat base.
- Front/back micro switches are planned for collision/dock detection, but their GPIOs are not assigned in firmware yet.

### Upper Body

- Rounded shell or egg-shaped upper body.
- Front display opening for the face TFT.
- OV2640 camera opening facing the user.
- Internal INMP441 mic and MAX98357A speaker amp.
- Optional SG90 servos for ears/head movement after the minimum drive/display loop is stable.

For quick prototypes, start from an open 2WD N20 chassis model and edit mounting holes in Fusion 360 or TinkerCAD. Avoid printing the final decorative shell before the actual module dimensions are measured.

## ESP32-S3 Wiring Summary

Canonical pin table: [hardware/wiring/esp32_pinout.md](../hardware/wiring/esp32_pinout.md).

Integrated harness (2026-06-24): TFT SPI defaults to GPIO14/21/42/43/44 with LED/BL tied to 3V3 (`TFT_BL=-1`) via `robot/firmware/src/board_pins.h` and PlatformIO `tft_integrated_pins`. Legacy GPIO9–12 remains only on `face240_legacy` / `display_test_legacy`.

## DRV8833 Motor Driver

Current firmware mapping:

| DRV8833 input | ESP32-S3 GPIO |
| --- | ---: |
| Left IN1 | GPIO1 |
| Left IN2 | GPIO2 |
| Right IN1 | GPIO3 |
| Right IN2 | GPIO48 |

Initial tests:

```powershell
cd robot\firmware
pio run -e motor_bench_once
pio run -e motor_manual
pio run -e motor_wifi_manual
```

Manual WiFi control:

1. Flash `motor_wifi_manual`.
2. Connect phone/laptop WiFi to `XiaoAn-Motor`, password `12345678`.
3. Open `http://192.168.4.1/`.
4. Hold W/A/S/D only while the robot is raised or wheels are unloaded.
5. Release the button and confirm the deadman timeout stops the motors.

If the correct wheel spins but forward/backward is reversed, flip `MOTOR_LEFT_FORWARD_USES_IN1` or `MOTOR_RIGHT_FORWARD_USES_IN1` in `robot/firmware/src/motor_ctrl.h`. If the wrong physical wheel moves, change the pin mapping instead.

## OV2640 Camera

Current GOOUUU ESP32-S3-CAM v1.5 map is used by `cam_stream.cpp`, `camtesting_program.cpp`, and `motor_cam_wifi_manual_main.cpp`:

| Camera signal | ESP32-S3 GPIO |
| --- | ---: |
| XCLK | GPIO15 |
| SIOD/SDA | GPIO4 |
| SIOC/SCL | GPIO5 |
| D0 | GPIO11 |
| D1 | GPIO9 |
| D2 | GPIO8 |
| D3 | GPIO10 |
| D4 | GPIO12 |
| D5 | GPIO18 |
| D6 | GPIO17 |
| D7 | GPIO16 |
| VSYNC | GPIO6 |
| HREF | GPIO7 |
| PCLK | GPIO13 |
| PWDN | not connected |
| RESET | not connected |

Test commands:

```powershell
cd robot\firmware
pio run -e camtesting
pio run -e motor_cam_wifi_manual
```

`motor_cam_wifi_manual` exposes:

- Control UI: `http://192.168.4.1/`
- MJPEG stream: `http://192.168.4.1:81/stream`
- Single JPEG fallback: `http://192.168.4.1/jpg`

## TFT Display

### Integrated map (recommended — camera + TFT together)

Use this wiring on the full robot harness. Constants also live in `robot/firmware/src/board_pins.h` and PlatformIO `[tft_integrated_pins]`.

| TFT signal | ESP32-S3 GPIO |
| --- | ---: |
| SCK | GPIO14 |
| MOSI (SDI) | GPIO21 |
| CS | GPIO42 |
| DC | GPIO43 |
| RESET | GPIO44 |
| LED (BL) | 3V3 (`TFT_BL=-1`) |
| VCC | Distribution 5V |
| GND | Distribution GND |
| MISO | not connected |

Integrated test command:

```powershell
cd robot\firmware
pio run -e face240_integrated
```

Do not connect TFT RESET to the ESP32 board RST pin.

### Legacy bench map (128x160 and old 2.4 inch harnesses only)

Conflicts with OV2640 on GPIO9/10/11/12. Use only when the camera FPC harness is disconnected.

| TFT signal | ESP32-S3 GPIO |
| --- | ---: |
| MOSI | GPIO11 |
| MISO | not connected |
| SCLK | GPIO12 |
| CS | GPIO10 |
| DC | GPIO9 |
| RST | GPIO14 |
| BL | GPIO21 |

Legacy test commands:

```powershell
cd robot\firmware
pio run -e display_test
pio run -e face240_wiretest
pio run -e face240_roboeyes
pio run -e face240_9expr_merged
pio run -e face240
pio run -e face240_espi
```

If the 2.4 inch ST7789 module shows wrong colors, blank screen, or inverted output, use the legacy `tftprobe_*` envs on the old harness to isolate driver variant, RGB/BGR order, inversion, and raw init behavior.

## INMP441 Microphone

Current test mapping:

| INMP441 signal | ESP32-S3 GPIO |
| --- | ---: |
| SCK/BCLK | GPIO39 |
| WS/LRCL | GPIO40 |
| SD/DOUT | GPIO41 |
| L/R | GND |
| VDD | 3V3 |
| GND | GND |

Test command:

```powershell
cd robot\firmware
pio run -e voice_recognition_test
```

Expected serial behavior: the firmware prints calibration information and then RMS/voice activity status. Treat this as a mic electrical test, not real ASR.

## MAX98357A Speaker Amp

Current test mapping:

| MAX98357A signal | ESP32-S3 GPIO |
| --- | ---: |
| BCLK | GPIO35 |
| LRC/WS | GPIO36 |
| DIN | GPIO37 |
| VIN | 5V or board-approved amp supply |
| GND | GND |

Test command:

```powershell
cd robot\firmware
pio run -e speaker_amp_test
```

Keep volume and amplitude conservative during first power-on. Confirm amp power, speaker impedance, and heat before repeated tests.

## DK-2500 Setup

DK-2500 deployment notes are in [docs/deployment_dk2500.md](deployment_dk2500.md).

Minimum local checks:

```powershell
python tools\check_runtime_env.py
python tools\check_runtime_env.py --check-camera
python -m unittest discover -s tests -p "test_*.py"
```

Target-side checks are listed in [hardware/dk2500/device_checklist.md](../hardware/dk2500/device_checklist.md) and [hardware/dk2500/peripheral_test.md](../hardware/dk2500/peripheral_test.md).

## Power / Dock

Use [hardware/wiring/power.md](../hardware/wiring/power.md) as the power checklist. The project direction is wireless charging dock alignment, not a TP4056 wired-charge-first design.

Do not connect motors, speaker amp, display backlight, and camera all at once on first power-on. Bring rails up in stages and measure idle/moving current.
