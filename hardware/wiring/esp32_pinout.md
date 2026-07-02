# ESP32-S3 Pinout

This page is the canonical wiring reference for Xiao An bench and integrated harnesses.

Updated: **2026-06-30 audio wiring sync over the 2026-06-22 integrated map**. Power distribution details: [power.md](power.md).

Hardware target:

- **MCU**: GOOUUU ESP32-S3-CAM v1.5
- **Display**: 2.4 inch ST7789 SPI 240x320 V1.3
- **Camera**: OV2640 (FPC on ESP32-S3-CAM board)
- **Motor driver**: DRV8833 + 2x N20
- **Mic**: INMP441
- **Speaker amp**: MAX98357A

## Wiring Strategy

- **Camera pins are fixed** by the GOOUUU FPC layout. Do not repin OV2640 DVP signals.
- **TFT SPI uses the integrated map** (GPIO14/21/42/43/44, LED tied to 3V3) as the default in firmware and PlatformIO envs.
- **Legacy TFT bench map** (GPIO9/10/11/12) remains only for explicit `face240_legacy` / `display_test_legacy` envs on old harnesses.
- **Motor VM** comes from the battery rail, not the 5V distribution bus.
- **Speaker + mic audio** uses the shared-clock candidate map in `robot/mergetesting`: INMP441 BCLK/WS/SD = GPIO39/40/41 and MAX98357A BCLK/WS/DIN = GPIO39/40/47. Do not use GPIO35/36/37 for the current MAX98357A path on the Octal PSRAM module.

## Power System

| From | To | Wire | Notes |
| --- | --- | --- | --- |
| Dock transmitter | Green wireless receiver coil | — | Transmitter stays on dock only |
| Green board WOUT+ | Black charge board VIN | Red | Do **not** wire green board BAT to the battery |
| Green board WOUT- | Black charge board GND | Black | |
| Li-ion battery + | Black charge board BAT+ | Red, heavy | |
| Li-ion battery - | Black charge board GND | Black, heavy | Common ground for whole robot |
| Black board OUT 5V | Distribution board IN_5V | Red | Main 5V rail |
| Black board OUT GND | Distribution board IN_GND | Black | |
| Battery + | DRV8833 VM | Red, heavy | **Not** through 5V distribution |
| Distribution 5V | ESP32 5V pin | Red | |
| Distribution 5V | TFT VCC | Red | |
| Distribution 5V | MAX98357A VIN | Red | |
| Distribution GND | ESP32 / TFT / DRV8833 / INMP441 / amp GND | Black | Five GND branches |
| ESP32 3V3 pin | INMP441 VDD | Orange | Fly wire, not from distribution board |
| ESP32 3V3 pin | DRV8833 VCC | Orange | Logic supply |

### Distribution Board Capacitors

| Location | Parts | Connection |
| --- | --- | --- |
| Input (IN_5V / IN_GND) | 1000 uF electrolytic + 0.1 uF ceramic | Parallel across 5V and GND buses |
| Near ESP32 5V tap | 470 uF electrolytic | Parallel across 5V and GND buses |
| At DRV8833 module | 470–1000 uF electrolytic | **VM to GND** on the driver board |

### Distribution Board Terminals

| Terminal | Connects to |
| --- | --- |
| IN_5V | Black board OUT 5V |
| IN_GND | Black board OUT GND |
| 5V_ESP | ESP32 5V |
| 5V_TFT | TFT VCC |
| 5V_AMP | MAX98357A VIN |
| GND_ESP | ESP32 GND |
| GND_TFT | TFT GND |
| GND_MOT | DRV8833 GND |
| GND_MIC | INMP441 GND and L/R |
| GND_AMP | MAX98357A GND |

## Signal Wiring (ESP32 to Peripherals)

### TFT 2.4 inch ST7789 — Integrated Map (Recommended)

| TFT pin | ESP32-S3 GPIO | GOOUUU header | Firmware define |
| --- | ---: | --- | --- |
| SCK | 14 | Left row | `TFT_SCLK=14` |
| SDI (MOSI) | 21 | Right row | `TFT_MOSI=21` |
| CS | 42 | Right row | `TFT_CS=42` |
| DC | 43 | Right row | `TFT_DC=43` |
| RESET | 44 | Right row | `TFT_RST=44` |
| LED (BL) | 3V3 | 3V3 | Always-on backlight; `TFT_BL=-1` |
| VCC | Distribution 5V | Left row 5V | |
| GND | Distribution GND | Right row GND | |
| SDO (MISO) | Not connected | — | `TFT_MISO=-1` |
| Touch / SD pins | Not connected | — | Optional; not used in current firmware |

Do **not** connect TFT RESET to the ESP32 board RST pin. That pin resets the MCU, not a display GPIO.

### TFT 2.4 inch ST7789 — Legacy Bench Map (Camera Must Be Disconnected)

Used by older `face240_*`, `display_test`, and `tftprobe_*` envs on pre-integration harnesses.

| TFT pin | ESP32-S3 GPIO | Notes |
| --- | ---: | --- |
| MOSI | 11 | Conflicts with OV2640 D0 |
| SCLK | 12 | Conflicts with OV2640 D4 |
| CS | 10 | Conflicts with OV2640 D3 |
| DC | 9 | Conflicts with OV2640 D1 |
| RST | 14 | |
| BL | 21 | |
| MISO | Not connected | `TFT_MISO=-1` |

### OV2640 Camera — Fixed GOOUUU Map

| Camera signal | ESP32-S3 GPIO | Notes |
| --- | ---: | --- |
| XCLK | 15 | Camera clock |
| SIOD / SDA | 4 | SCCB data |
| SIOC / SCL | 5 | SCCB clock |
| D0 | 11 | Parallel data |
| D1 | 9 | Parallel data |
| D2 | 8 | Parallel data |
| D3 | 10 | Parallel data |
| D4 | 12 | Parallel data |
| D5 | 18 | Parallel data |
| D6 | 17 | Parallel data |
| D7 | 16 | Parallel data |
| VSYNC | 6 | Frame sync |
| HREF | 7 | Line reference |
| PCLK | 13 | Pixel clock |
| PWDN | Not connected | `-1` in firmware |
| RESET | Not connected | `-1` in firmware |

### DRV8833 Motor Driver

| DRV8833 pin | Connect to | ESP32 / power |
| --- | --- | --- |
| VM | Battery + | Heavy wire; not from 5V distribution |
| VCC | Logic | ESP32 3V3 |
| GND | Common ground | Distribution GND |
| nSLEEP / STBY | Enable | Tie to 3V3 or leave high per module |
| AIN1 | Left motor | GPIO1 |
| AIN2 | Left motor | GPIO2 |
| BIN1 | Right motor | GPIO3 |
| BIN2 | Right motor | GPIO48 |
| AOUT1 / AOUT2 | Left N20 motor | |
| BOUT1 / BOUT2 | Right N20 motor | |

Direction fix: if the correct wheel spins backward, flip `MOTOR_LEFT_FORWARD_USES_IN1` or `MOTOR_RIGHT_FORWARD_USES_IN1` in `robot/firmware/src/motor_ctrl.h`. If the wrong wheel moves, change `PIN_MOTOR_*` instead.

| Function | ESP32-S3 GPIO | Firmware constant |
| --- | ---: | --- |
| Left motor IN1 | 1 | `PIN_MOTOR_L_IN1` |
| Left motor IN2 | 2 | `PIN_MOTOR_L_IN2` |
| Right motor IN1 | 3 | `PIN_MOTOR_R_IN1` |
| Right motor IN2 | 48 | `PIN_MOTOR_R_IN2` |
| Front limit switch | Unassigned | `PIN_LIMIT_FRONT = -1` |
| Back / dock limit switch | Unassigned | `PIN_LIMIT_BACK = -1` |

### INMP441 Microphone

| INMP441 pin | Connect to |
| --- | --- |
| VDD | ESP32 3V3 |
| GND | Distribution GND |
| L/R | GND (left channel) |
| SCK / BCLK | GPIO39 |
| WS / LRCL | GPIO40 |
| SD / DOUT | GPIO41 |

Env: `voice_recognition_test` (electrical / RMS test, not real ASR).

### MAX98357A Speaker Amplifier

| MAX98357A pin | Connect to |
| --- | --- |
| VIN | Distribution 5V |
| GND | Distribution GND |
| BCLK | GPIO39, shared with INMP441 SCK / BCLK |
| LRC / WS | GPIO40, shared with INMP441 WS / LRCL |
| DIN | GPIO47 |
| GAIN | Float or GND |
| SD | 3V3 (enable) or float |
| SPK +/- | 8 ohm speaker |

Current product-candidate diagnostic env: `mergetesting_audio_shared_i2s_diag` in `robot/mergetesting`. It runs half-duplex audio only: LISTEN installs mic RX on I2S0, SPEAK installs speaker TX on I2S1, and the active I2S driver is uninstalled before switching modes. It also emits a 1 kHz probe tone before the embedded phrase so the amp/speaker output path can be checked independently of spoken phrase loudness.

Do **not** use GPIO35/36/37 for MAX98357A on the current ESP32-S3 Octal PSRAM module. The 2026-06-29 A/B tests showed GPIO35/36/37 can reset at the first embedded PCM write with `TG1WDT_SYS_RST`.

Temporary speaker-only diagnostic for ESP32-S3 Octal PSRAM pin conflict confirmed on 2026-06-29:

| MAX98357A pin | Temporary connect to |
| --- | --- |
| BCLK | GPIO39 |
| LRC / WS | GPIO40 |
| DIN | GPIO41 |

Use `mergetesting_speaker_altpins_only` first, then `mergetesting_speaker_altpins_phrase_only` for the embedded-sentence retest. OTA variants are `mergetesting_speaker_altpins_only_ota` and `mergetesting_speaker_altpins_phrase_only_ota`. Do not use this map with INMP441 connected; GPIO39/40/41 are the default mic pins. The A/B result is: GPIO35/36/37 resets during embedded PCM playback, GPIO39/40/41 completes the same PCM path without WDT.

Legacy isolated amp env `speaker_amp_test` remains a robot-body bring-up target, not the current DK-2500 integrated audio path. Before using it, verify its pin map against `robot/firmware/platformio.ini` and the actual harness.

## GPIO Allocation Summary

```text
GPIO    Function
──────────────────────────────────
1, 2      Left motor IN1 / IN2
4, 5      Camera SCCB (SDA / SCL)
6, 7      Camera VSYNC / HREF
8–13      Camera D2–D7, PCLK, D0, D1, D3, D4
14        TFT SCK (integrated map)
15        Camera XCLK
16–18     Camera D7, D6, D5
21        TFT MOSI (integrated map)
35–37     Avoid for current MAX98357A on Octal PSRAM module
3         Right motor IN1
38        Previously right motor IN2; avoid for motor after reset-spin issue
39–41     INMP441 I2S; 39/40 also shared with MAX98357A clock in half-duplex diag
42–44     TFT CS / DC / RST (integrated map)
47        MAX98357A DIN in current shared-clock diagnostic
48        Right motor IN2
──────────────────────────────────
Unused    0, 19, 20, 45, 46, … (strapping / spare — leave unconnected for now)
```

## Wire Count Checklist

| Category | Count |
| --- | ---: |
| 5V power branches | 3 (ESP32, TFT, speaker amp) |
| GND power branches | 5 (ESP32, TFT, DRV8833, mic, amp) |
| 3V3 fly wires | 2 (INMP441 VDD, DRV8833 VCC) |
| VM heavy wire | 1 (battery to DRV8833) |
| TFT signal wires | 6 (or 5 if BL tied to 3V3) |
| Motor signal wires | 4 |
| Microphone I2S wires | 3 |
| Speaker I2S wires | 3 |
| **Total signal wires** | **16–17** |

## PlatformIO Env Reference

| Goal | Env | Notes |
| --- | --- | --- |
| TFT / face tests (integrated harness) | `face240_wiretest`, `face240`, `face240_9expr_merged`, `tftprobe_hybrid_rawinit`, `display_test` | Camera + TFT can coexist |
| Legacy TFT bench (old harness) | `face240_legacy`, `display_test_legacy` | Do not use with camera on GPIO9–12 |
| Alias | `face240_integrated` | Same as `face240_wiretest` |
| Camera + motor + WiFi demo | `motor_cam_wifi_manual` | SSID `XiaoAn-Motor`, password `12345678`, UI `http://192.168.4.1/` |
| Microphone electrical test | `voice_recognition_test` | |
| Speaker electrical test | `speaker_amp_test` | Robot-body bring-up only; verify pins before use |
| Shared mic/speaker diagnostic | `mergetesting_audio_shared_i2s_diag` | In `robot/mergetesting`; BCLK=39, WS=40, mic SD=41, speaker DIN=47 |
| Fixed-window mic ASR calibration | `mergetesting_mic_only_shift18_asr` | In `robot/mergetesting`; current ASR demo gain path |
| Motor bench | `motor_bench_once`, `motor_manual`, `motor_wifi_manual` | |
| Main `/control` firmware | `esp32-s3-devkitc-1` | |
| DK-2500 `/control` Phase 1-2 | `mergetesting_display_only`, `mergetesting_display_only_ota` | In `robot/mergetesting`; OTA target requires OTA-enabled firmware already running |
| DK-2500 `/video` camera smoke | `mergetesting_cam_only`, `mergetesting_cam_only_ota` | Camera-only target; preserves verified JPEG WebSocket route |

## Integrated vs Legacy TFT Pins

| TFT signal | Legacy bench (conflicts camera) | Integrated (recommended) |
| --- | ---: | ---: |
| SCK | 12 | **14** |
| MOSI | 11 | **21** |
| CS | 10 | **42** |
| DC | 9 | **43** |
| RST | 14 | **44** |
| BL | 21 | **48** or 3V3 |

## Do Not

| Rule | Reason |
| --- | --- |
| Wire green receiver BAT in parallel with black board BAT | Dual charge path |
| Connect motor VM to the 5V boost rail | N20 motors need battery voltage |
| Connect TFT RESET to ESP32 RST | Resets the whole MCU |
| Use legacy TFT map (GPIO9–12) with camera connected | GPIO conflict on DVP data lines |

## Related Files

- [power.md](power.md) — rails, first power-on order, safety checks
- [motor_driver.md](motor_driver.md) — DRV8833 bench checklist
- [../docs/xiao_an_power_wiring_diagram.svg](../../docs/xiao_an_power_wiring_diagram.svg) — power topology diagram
- [../../robot/firmware/src/board_pins.h](../../robot/firmware/src/board_pins.h) — integrated pin constants for firmware
- [../../docs/setup/hardware_setup.md](../../docs/setup/hardware_setup.md) — bench bring-up order
