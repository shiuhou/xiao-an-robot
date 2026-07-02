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

Canonical pin table: [hardware/wiring/esp32_pinout.md](../../hardware/wiring/esp32_pinout.md).

Integrated harness (2026-06-24): TFT SPI defaults to GPIO14/21/42/43/44 with LED/BL tied to 3V3 (`TFT_BL=-1`) via `robot/firmware/src/board_pins.h` and PlatformIO `tft_integrated_pins`. Legacy GPIO9–12 remains only on `face240_legacy` / `display_test_legacy`.

## WiFi OTA Bootstrap

Use `ota_bootstrap` as the first wireless-upload bridge before adding OTA to larger demos. It keeps camera, mic, speaker, WebSocket, and face display disabled, and holds DRV8833 motor pins low while OTA is active.

Local WiFi and OTA secrets belong in ignored `robot/firmware/src/config.local.h`; `robot/firmware/src/config.local.example.h` documents the expected macros.

Initial USB flash:

```powershell
cd robot\firmware
pio run -e ota_bootstrap
pio run -e ota_bootstrap -t upload --upload-port COMxx
```

Expected serial behavior: the firmware scans for `WIFI_SSID`, prints `WiFi connected IP=...`, prints `[OTA] Ready hostname=xiao-an-esp32 auth=...`, then prints an `alive` line every 5 seconds.

Wireless upload after the bridge is running:

```powershell
cd robot\firmware
pio run -e ota_bootstrap_wifi -t upload --upload-port <board-ip>
```

Important limitation for future firmware work: `ota_bootstrap_wifi` uploads only the bootstrap image. If an agent wants to wirelessly upload a different env, that env needs its own OTA-enabled upload target and the firmware itself must keep OTA alive after boot. Minimum requirements are WiFi STA connection, `ENABLE_ARDUINO_OTA=1`, the `ota_update.cpp/h` wrapper or equivalent ArduinoOTA setup, and a regular `ota_loop()` call in the runtime loop. If those are missing, the first wireless upload can replace the bootstrap, but the next upload will require USB recovery.

Mergetesting functional OTA targets now follow that rule. Use
`robot/mergetesting` `mergetesting_display_only_ota` for the Phase 1-2
`/control` firmware, and `mergetesting_cam_only_ota` for the verified
camera-only `/video` smoke firmware. Do not use `ota_bootstrap_wifi` for either
functional firmware.

Verified 2026-06-25 on the Windows-hotspot route:

```powershell
cd robot\firmware
pio run -e ota_bootstrap -t upload --upload-port COM19
pio run -e ota_bootstrap_wifi -t upload --upload-port 192.168.137.197
```

The OTA upload returned `Result: OK`, and the ESP32 rebooted back onto WiFi at `192.168.137.197`. A public WiFi can also work if it keeps the robot and base station on the same reachable LAN and does not block OTA port `3232`.

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
pio run -e tftprobe_hybrid_rawinit
```

If the 2.4 inch ST7789 module shows wrong colors, blank screen, or inverted output, use `tftprobe_hybrid_rawinit` to isolate driver variant, RGB/BGR order, inversion, and raw init behavior.

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

Current shared-clock diagnostic mapping:

| MAX98357A signal | ESP32-S3 GPIO |
| --- | ---: |
| BCLK | GPIO39, shared with INMP441 SCK/BCLK |
| LRC/WS | GPIO40, shared with INMP441 WS/LRCL |
| DIN | GPIO47 |
| VIN | 5V |
| GND | GND |

Do not use GPIO35/36/37 for MAX98357A on the current ESP32-S3 Octal PSRAM module. The 2026-06-29 speaker diagnostics showed that long embedded PCM playback on GPIO35/36/37 can reset at the first I2S write with `TG1WDT_SYS_RST`.

Shared mic+speaker half-duplex diagnostic:

```powershell
cd robot\mergetesting
pio run -e mergetesting_audio_shared_i2s_diag
pio run -e mergetesting_audio_shared_i2s_diag -t upload --upload-port COM19
pio device monitor -b 115200 --port COM19
```

Expected serial behavior:

```text
[AudioDiag] mode=LISTEN start
[AudioDiag] i2s_rx_init ok
[AudioDiag] rms=... peak=... voice_detected=...
[AudioDiag] i2s_rx_stop ok
[AudioDiag] mode=SPEAK start
[AudioDiag] i2s_tx_init ok
[AudioDiag] output_probe_tone frequency_hz=1000 amplitude=30000 duration_ms=260
[AudioDiag] output_probe_tone done bytes_written=...
[AudioDiag] pcm_samples=... gain=...
[AudioDiag] i2s_write return code=...
[AudioDiag] bytes_written=...
[AudioDiag] playback_done ok
[AudioDiag] i2s_tx_stop ok
```

Speaker-only PSRAM-conflict diagnostic confirmed on 2026-06-29:

| MAX98357A signal | Temporary ESP32-S3 GPIO |
| --- | ---: |
| BCLK | GPIO39 |
| LRC/WS | GPIO40 |
| DIN | GPIO41 |

Use only `robot/mergetesting` diagnostic envs `mergetesting_speaker_altpins_only` and `mergetesting_speaker_altpins_phrase_only` with camera/mic/motor disabled. OTA upload variants are `mergetesting_speaker_altpins_only_ota` and `mergetesting_speaker_altpins_phrase_only_ota`. GPIO39/40/41 are also the default INMP441 pins, so this is not a permanent combined mic+speaker map. The A/B test showed the original GPIO35/36/37 path resets at embedded PCM playback, while GPIO39/40/41 completes the same PCM path without WDT.

The product-candidate shared-clock wiring keeps GPIO39/40 shared but separates data pins: INMP441 SD/DOUT on GPIO41, MAX98357A DIN on GPIO47. The diagnostic env `mergetesting_audio_shared_i2s_diag` intentionally disables camera, TFT, motor, WiFi/WebSocket app flow, and full-duplex audio. It runs `LISTEN_MODE -> STOP_LISTEN -> SPEAK_MODE -> STOP_SPEAK`, using I2S0 for mic RX and I2S1 for speaker TX, and uninstalls the active driver before switching modes. A 2026-06-29 COM19 run of the earlier I2S0-TX version wrote PCM successfully but produced low-frequency noise instead of speech; switching TX to I2S1 fixed the sentence audio. Current diagnostic phrase gain is 20, and SPEAK mode first emits a short full-scale-ish 1 kHz probe tone (`amplitude=30000`, `duration_ms=260`) before the embedded phrase so the hardware output path can be checked independently of phrase loudness.

When using the CH340 adapter path (`COM22`), this diagnostic routes app logs to UART0 (`Serial0`, RX=GPIO44, TX=GPIO43) instead of native USB `Serial`. COM22 can now show `[AudioDiag]` app logs, successful probe-tone writes, and successful embedded-phrase I2S writes. If COM22 logs show `output_probe_tone done`, `playback_done ok`, and no sound, inspect the MAX98357A hardware side first: VIN 5V, common GND with ESP32, GAIN/SD state, speaker connected to amp `+/-` outputs, speaker impedance/power, or a damaged MAX98357A module.

## DK-2500 Setup

DK-2500 deployment notes are in [setup/dk2500_deployment.md](dk2500_deployment.md).

Minimum local checks:

```powershell
python tools\check_runtime_env.py
python tools\check_runtime_env.py --check-camera
python -m unittest discover -s tests -p "test_*.py"
```

Target-side checks are listed in [hardware/dk2500/device_checklist.md](../../hardware/dk2500/device_checklist.md) and [hardware/dk2500/peripheral_test.md](../../hardware/dk2500/peripheral_test.md).

## Power / Dock

Use [hardware/wiring/power.md](../../hardware/wiring/power.md) as the power checklist. The project direction is wireless charging dock alignment, not a TP4056 wired-charge-first design.

Do not connect motors, speaker amp, display backlight, and camera all at once on first power-on. Bring rails up in stages and measure idle/moving current.
