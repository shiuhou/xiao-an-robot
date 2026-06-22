# ESP32-S3 Pinout

This table records the pin assignments currently used by `robot/firmware/platformio.ini` and the firmware source files.

## Motor Driver

| Function | ESP32-S3 Pin | Connected Part | Notes |
| --- | ---: | --- | --- |
| Left motor IN1 | GPIO1 | DRV8833 left IN1 | Forward by default when `MOTOR_LEFT_FORWARD_USES_IN1=true`. |
| Left motor IN2 | GPIO2 | DRV8833 left IN2 | Reverse side of left H-bridge. |
| Right motor IN1 | GPIO47 | DRV8833 right IN1 | Forward by default when `MOTOR_RIGHT_FORWARD_USES_IN1=true`. |
| Right motor IN2 | GPIO38 | DRV8833 right IN2 | Reverse side of right H-bridge. |
| Front limit | Unassigned | Micro switch | Firmware uses `-1` during bench bring-up. |
| Back limit | Unassigned | Dock switch | Firmware uses `-1` during bench bring-up. |

## OV2640 Camera

Current GOOUUU ESP32-S3-CAM v1.5 map:

| Camera Signal | ESP32-S3 Pin | Notes |
| --- | ---: | --- |
| XCLK | GPIO15 | Camera clock. |
| SIOD / SDA | GPIO4 | SCCB data. |
| SIOC / SCL | GPIO5 | SCCB clock. |
| D0 | GPIO11 | Parallel data. |
| D1 | GPIO9 | Parallel data. |
| D2 | GPIO8 | Parallel data. |
| D3 | GPIO10 | Parallel data. |
| D4 | GPIO12 | Parallel data. |
| D5 | GPIO18 | Parallel data. |
| D6 | GPIO17 | Parallel data. |
| D7 | GPIO16 | Parallel data. |
| VSYNC | GPIO6 | Frame sync. |
| HREF | GPIO7 | Line reference. |
| PCLK | GPIO13 | Pixel clock. |
| PWDN | Not connected | `-1` in firmware. |
| RESET | Not connected | `-1` in firmware. |

## TFT Display Tests

The current display tests are isolated from the camera tests because they reuse several GPIOs.

| TFT Signal | ESP32-S3 Pin | Used By | Notes |
| --- | ---: | --- | --- |
| MOSI | GPIO11 | `display_test`, `face240*`, `tftprobe_*` | Conflicts with OV2640 D0. |
| MISO | Not connected | TFT tests | Configured as `-1`. |
| SCLK | GPIO12 | TFT tests | Conflicts with OV2640 D4. |
| CS | GPIO10 | TFT tests | Conflicts with OV2640 D3. |
| DC | GPIO9 | TFT tests | Conflicts with OV2640 D1. |
| RST | GPIO14 | TFT tests | Dedicated reset pin in display envs. |
| BL | GPIO21 | TFT tests | Backlight enable. |

## Audio

| Function | ESP32-S3 Pin | Connected Part | Notes |
| --- | ---: | --- | --- |
| Mic BCLK/SCK | GPIO39 | INMP441 | `voice_recognition_test`. |
| Mic WS/LRCL | GPIO40 | INMP441 | `voice_recognition_test`. |
| Mic DIN/SD | GPIO41 | INMP441 | INMP441 `L/R` tied to GND. |
| Speaker BCLK | GPIO35 | MAX98357A | `speaker_amp_test`. |
| Speaker LRC/WS | GPIO36 | MAX98357A | `speaker_amp_test`. |
| Speaker DIN | GPIO37 | MAX98357A | `speaker_amp_test`. |

## Integration Warning

The camera and TFT maps are not currently compatible on the same wiring harness because GPIO9/10/11/12 are reused. Keep `camtesting`, `motor_cam_wifi_manual`, `display_test`, `face240*`, and `tftprobe_*` as isolated bring-up envs until a final integrated pin map is chosen.
