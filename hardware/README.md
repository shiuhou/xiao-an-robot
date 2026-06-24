# Hardware Notes

This directory collects hardware setup notes for Xiao An. Keep notes practical, measurable, and tied to the current firmware envs.

## Main Files

| File | Purpose |
| --- | --- |
| [bom/bom.md](bom/bom.md) | Current parts list and selection status. |
| [wiring/esp32_pinout.md](wiring/esp32_pinout.md) | ESP32-S3 pin map, power distribution, integrated vs legacy TFT wiring |
| [wiring/motor_driver.md](wiring/motor_driver.md) | DRV8833 wiring and motor test checklist. |
| [wiring/power.md](wiring/power.md) | Rails, wireless charging direction, and power safety checks. |
| [dk2500/device_checklist.md](dk2500/device_checklist.md) | DK-2500 readiness checklist. |
| [dk2500/peripheral_test.md](dk2500/peripheral_test.md) | Target-side peripheral commands. |
| [mechanical/shell/README.md](mechanical/shell/README.md) | Shell dimensions and mounting notes. |
| [mechanical/dock/README.md](mechanical/dock/README.md) | Dock and wireless charging notes. |

## Bench Workflow

1. Record wiring before powering a new peripheral.
2. Flash only the matching PlatformIO env.
3. Verify serial output and physical behavior.
4. Update the wiring note if the actual harness differs from firmware.
5. Combine subsystems only after each isolated test is stable.
