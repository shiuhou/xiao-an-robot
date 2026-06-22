# Power

This page tracks the current bench power plan. Do not treat it as final production wiring until rails and currents are measured on the actual chassis.

## Planned Rails

| Rail | Source | Consumers | Current Status |
| --- | --- | --- | --- |
| Battery | 3.7V Li-ion/LiPo pack with protection | Motors, regulators, robot power | Capacity and connector still need final selection. |
| Motor VM | Battery or regulated motor rail approved for N20 motors | DRV8833 VM | Measure stall and moving current before full chassis tests. |
| 5V | Boost/regulator or USB during bench tests | TFT backlight, MAX98357A amp, some modules | Confirm current budget before combining display and audio. |
| 3.3V | ESP32-S3 board regulator | ESP32-S3 logic, OV2640 logic, INMP441 | Confirm regulator margin with camera active. |
| GND | Common ground | All modules | All signal modules must share ground with ESP32-S3. |

## Wireless Charging Direction

The product direction is a **wireless charging dock**, not a TP4056 wired-charge-first design. Validate the wireless charging transmitter/receiver pair separately before mounting it in the dock.

Bench checks:

1. Test transmitter/receiver alignment with a dummy load.
2. Measure output voltage with no robot attached.
3. Measure loaded voltage and temperature.
4. Confirm charging behavior does not brown out the ESP32-S3.
5. Add dock limit switch sensing only after charging alignment is stable.

## First Power-On Sequence

1. ESP32-S3 alone over USB.
2. DRV8833 logic connected, motor VM disconnected.
3. DRV8833 motor VM connected with wheels unloaded.
4. OV2640 camera only.
5. TFT display only.
6. INMP441 mic only.
7. MAX98357A speaker amp at low amplitude.
8. Combine subsystems one at a time while measuring current.

## Safety Checks

- Verify polarity before connecting a battery.
- Use a current-limited supply for early motor tests when possible.
- Keep motors unloaded for first direction tests.
- Check DRV8833 and regulator temperature after repeated pulses.
- Do not run motor, speaker amp, display backlight, and camera together until individual current draw is known.
