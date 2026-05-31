# Power

Record power architecture and safety checks here.

## Rails

| Rail | Source | Consumers | Notes |
| --- | --- | --- | --- |
| Battery | TBD | Motors, regulators | Record capacity and connector. |
| 5V | TBD | Display, audio, sensors | Confirm current budget. |
| 3.3V | TBD | ESP32-S3, logic | Confirm regulator margin. |

## Safety Checks

- Verify polarity before connecting the battery.
- Measure idle and moving current.
- Confirm charging and dock behavior separately.

