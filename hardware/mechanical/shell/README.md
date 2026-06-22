# Shell

The shell should stay prototype-friendly until all hardware module dimensions are confirmed.

## Current Concept

| Area | Note |
| --- | --- |
| Base | Flat 2WD N20 chassis, about 12 cm x 10 cm x 3 cm for the prototype. |
| Upper body | Rounded shell or simple cylinder + half-sphere form. |
| Display opening | Front-facing TFT face screen. |
| Camera opening | OV2640 facing the user. |
| Mic opening | Small acoustic hole near front/top, away from speaker. |
| Speaker opening | Side or lower opening with enough volume and ventilation. |
| Service access | Keep USB, battery, and reset access reachable during bring-up. |

## Print Guidance

- Use PLA for early prototypes.
- Start with 0.2 mm layer height and about 20% infill.
- Keep wall thickness around 2 mm unless the mount flexes.
- Do not print the final shell before measuring the actual TFT, OV2640 adapter, motor driver, battery, and speaker.

## Integration Notes

- Keep camera and TFT wiring serviceable; the current firmware maps overlap and may change.
- Leave room for strain relief on motor and battery wires.
- Do not mount wireless charging parts until dock alignment is measured.
