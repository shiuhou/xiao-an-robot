# Bill of Materials

Track hardware parts here. Avoid committing private purchase records, personal addresses, or order screenshots.

| Part | Current Model / Direction | Quantity | Status | Notes |
| --- | --- | ---: | --- | --- |
| Base station | Intel DK-2500 / Core Ultra | 1 | Known target | Local AI, OpenVINO, WebSocket server, Agent runtime. |
| Robot MCU | ESP32-S3 DevKitC-1 or current ESP32-S3 bring-up board | 1 | In use | Main robot controller. |
| Camera | OV2640 with 24-pin FPC adapter / GOOUUU ESP32-S3-CAM v1.5 pin map | 1 | Bench test path exists | Used by `camtesting` and `motor_cam_wifi_manual`. |
| Motor driver | DRV8833 dual H-bridge | 1 | In firmware wiring map | Drives two N20 motors. |
| Motors | N20 gear motor, 3V-6V, about 150-200 RPM | 2 | Planned / bench target | Differential drive. |
| Display | 2.4 inch 320x240 ST7789 TFT | 1 | Integrated harness | GPIO14/21/42/43/44/48; see `board_pins.h` |
| Microphone | INMP441 I2S mic | 1 | Test env exists | `voice_recognition_test`, not real ASR. |
| Speaker amp | MAX98357A I2S amplifier | 1 | Test env exists | `speaker_amp_test`. |
| Speaker | 8 ohm small speaker, about 1W | 1 | Planned | Match amp and enclosure. |
| Servos | SG90 micro servo | 2 | Later stage | Ears/head movement after drive/display loop. |
| Battery | Protected 3.7V Li-ion/LiPo | 1 | Need final selection | Capacity and connector must be chosen after current measurements. |
| Charging | Wireless charging transmitter + receiver | 1 set | Product direction | Validate alignment and heat separately. |
| Limit switches | Micro switches | 2 | Planned | Dock/front/back detection; GPIOs unassigned. |
| Mechanical | 3D-printed chassis, shell, dock | 1 set | Prototype | Print after measuring real modules. |

## Purchase / Selection Rules

- Pick modules that match [hardware/wiring/esp32_pinout.md](wiring/esp32_pinout.md) and `robot/firmware/src/board_pins.h`.
- Confirm voltage/current ratings before combining rails.
- Keep spare motor driver and ESP32-S3 boards for bring-up failures.
- Record final dimensions before shell/dock print.
