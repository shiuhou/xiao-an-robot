# Dock

The current product direction is a wireless charging dock with physical alignment guides and a back/dock limit switch. Do not design around a TP4056 wired plug as the primary user flow.

## Prototype Fields

| Field | Current Note |
| --- | --- |
| Dock version | Prototype, not frozen. |
| Charging style | Wireless charging transmitter + receiver pair. |
| Alignment guide | Rails or funnel shape to center the receiver coil. |
| Detection | Back/dock micro switch planned; firmware GPIO unassigned. |
| Cable route | Keep transmitter cable away from motor path. |
| Safety checks | Measure heat and loaded voltage before enclosing. |

## Test Order

1. Test wireless charging module with a dummy load.
2. Mark best coil alignment and tolerance.
3. Add a simple rail/funnel dock mockup.
4. Add back switch detection after mechanical alignment works.
5. Integrate `move_back_to_dock` only after the switch GPIO is assigned.

## Known Risks

- Coil misalignment can create heat or unstable charging.
- Motor reverse motion into the dock needs a physical stop and a timeout.
- Limit switch wiring is not yet present in the firmware pin map.
